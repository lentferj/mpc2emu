<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->
# E-mu EOS hard-disk filesystems (FAT + EMU-fs) — RE notes

Reverse-engineered 2026-06-14 from two reference images formatted by an **E4XT
running EOS 4.7** itself (the authoritative source — not a PC tool):

| Reference | Path | Format |
|---|---|---|
| FAT      | `/home/lentferj/temp/hda-images/HD1-FEATUREDEMO.hda`        | FAT16, MBR |
| EMU-fs   | `/home/lentferj/temp/hda-images/HD1-FEATUREDEMO_emufs.hda`  | EMU3/EMU4  |

Context: the EMU-fs `.hda` produced by reusing the CD ISO builder **works** on
the E4XT (reads its banks); the first FAT attempt (partitionless FAT32) did
**not** ("No Banks Exist in Folder!").  Both formats are now understood.

---

## 1. FAT hard disk (EOS 4.7+)  — IMPLEMENTED in `build_hda_fat`

EOS does **not** use a partitionless superfloppy.  It writes a real MBR:

```
Sector 0 (MBR):  boot code = all zero, 0x55AA at [510:512]
  Partition 1 @ 0x1BE:  status=0x80 (bootable)  type=0x06 (FAT16)
                        start LBA = 63   count = (disk_sectors - 63)
```

Partition boot sector (at LBA 63):

| Field            | Value                               |
|------------------|-------------------------------------|
| OEM name (off 3) | `E-MU SYS`                          |
| bytes/sector     | 512                                 |
| sectors/cluster  | **64** (32 KB clusters)             |
| reserved sectors | **32** (not the usual 1)            |
| FAT count        | 2                                   |
| root entries     | 512 (FAT16 fixed root dir)          |
| FAT type         | **FAT16**                           |

Banks live in the partition **root** as `B.NNN-NAME.E4B`, and may also live in
sub-folders (the reference had a user-made `B.000-Test_Folder/` holding two more
banks).  EOS reads banks **copied** onto the disk — they need not be saved by
EOS itself (confirmed by the working EMU-fs case; FAT pending final HW confirm).

**Reproduce** (now pure-Python `writers/fat16.py`, no mtools): MBR by hand, FAT16
BPB (32 KB clusters, 32 reserved, OEM `E-MU SYS`), VFAT long names.  For FAT16
(not FAT12) the volume must be **≥512 MB**.

**FAT type by capacity — confirmed by the EOS 4.7 addendum (p.3):** *"EOS
automatically chooses … FAT12 always for floppy; FAT16 for disk capacity close
to or less than 1 GB; FAT32 for disk capacity above or close to 1 GB."*  So the
RE'd **FAT16 (from the 1 GB reference) is exactly right for ≤1 GB**; EOS formats
**FAT32 above 1 GB**.  `fat16.py` writes FAT16 (valid to ~2 GB, which EOS reads,
since the addendum says EOS supports FAT12/16/32); for larger disks use the
EMU-fs HDD (it scales) or add a FAT32 writer.

---

## 2. EMU-fs hard disk (all EOS versions)  — IMPLEMENTED in `build_emu_hdd`

**Status (2026-06-14):** geometry confirmed across **1/2/4 GB** EOS-formatted
references; `iso_builder.build_emu_hdd` generates images whose **superblock and
"Default Folder" entry are byte-identical** to the references.  Wired into
`build_hda_emu` / `convert.py --hda-fs emu` (honours `--hda-size`).

The EMU-fs **HDD** uses the same EMU3 magic/superblock as the CD, but a different
**fixed** geometry — the *directory* layout is constant across disk sizes; only
the **cluster size scales** to keep the count ≤ 1023.  1 GB reference superblock:

| Superblock field (LE u32)     | CD (build_iso) | **HDD ref (1 GB)** |
|-------------------------------|----------------|--------------------|
| total_blocks − 1              | data-sized     | **2097151** (full 1 GB disk) |
| start_fat                     | 2              | 2                  |
| fat_blocks                    | 5 (fixed)      | **4**              |
| start_root                    | 7              | **6**  (= 2+fat)   |
| root_blocks                   | 4              | **7**              |
| start_dircon                  | 11             | **13** (= 6+root)  |
| dircon_blocks                 | 125            | **169**            |
| start_data                    | 136            | **182** (= 13+dircon) |
| total_clusters                | data-sized     | **1023**           |
| cluster_size_extra (byte @0x28)| 4 (512 KB)    | **5 (1 MB)**       |

Confirmed rules (1/2/4 GB references all agree):
- **Directory geometry is CONSTANT** regardless of disk size:
  `fat_blocks=4, root_blocks=7, dircon_blocks=169, start_data=182,
  total_clusters=1023` (= 4 FAT blocks × 256 − 1).  It is a *second fixed
  profile* of the same EMU3 fs as the CD — not variable geometry.
- **Only the cluster size scales**, chosen as the smallest cse whose clusters
  span the whole disk within the 1023-cluster cap:

  | disk  | cse | cluster | clusters | HW-verified |
  |-------|-----|---------|----------|-------------|
  | 512 MB| 4   | 512 KB  | 1023     | (extrapolated) |
  | 1 GB  | 5   | 1 MB    | 1023     | ✓ |
  | 2 GB  | 6   | 2 MB    | 1023     | ✓ |
  | 4 GB  | 7   | 4 MB    | 1023     | ✓ |
  | 8 GB  | 8   | 8 MB    | 1023     | (extrapolated) |
  | 18 GB | 10  | 32 MB   | 575      | (extrapolated; max disk) |

  i.e. `cse = smallest c in {4..} with (total_blocks−182)//(2^(c+6)) ≤ 1023`.
- **total_blocks** = full disk in 512-byte blocks (the image is the full
  `--hda-size`, with the unused clusters left **free** so EOS can save onto it).

### Directory structure (folder hierarchy — richer than the CD)
- **ROOT block(s)** hold *folder* entries:
  - `Default Folder` — id byte **0x80** (system/default folder).
  - user folders — id **0x40**, with a **`block_list[7]`** of LE s16 dircon
    block indices (−1 = unused) → **up to 7 dircon blocks ≈ 100 banks/folder**
    (matches Jan's observation that EMU-fs allows only B00–B99 per folder).
- **DIRCON blocks** hold the *bank* entries of each folder:
  - 32-byte dentry: `name[16]`, unknown u8, **id u8 = the 2-digit folder slot
    (0-99)**, then `start_cluster, clusters, blocks_in_last_cluster,
    bytes_in_last_block` (LE u16), `type=0x81`, props ending **`E4B0`**.

### Bank numbering convention (important)
- **EMU-fs: 2-digit** — banks are numbered by their **folder slot (B00–B99)**,
  stored in the dentry `id` byte; the *name* field carries no number prefix.
  Max **100 banks/folder**.  `build_emu_hdd` strips any `B.NNN-`/`B.NN-` prefix
  from the source filename (`_emu_bank_name`) and uses the slot as the id.
- **FAT: 3-digit** — banks are files named **`B.NNN-NAME.E4B`** in the root.

### Builder — implemented
`iso_builder.build_emu_hdd(e4b_files, output, label, size_mb)` does exactly this:
fixed HDD geometry above, cse from the size, full-disk `total_blocks`, FAT =
bank chains **+ free clusters**, a `Default Folder` (id 0x80) in the root, bank
dentries in one dircon block.  `_superblock`/`_root_block` were parameterised
with a `geom`/`dtype` (CD path byte-identical).  Verified: 1 GB output's
superblock + Default-Folder entry match the reference byte-for-byte.

### Bank count per folder — RE'd & IMPLEMENTED (2026-06-14)
Confirmed from **emu3fs** (`emu3_fs.h`) + the hardware references:
- `emu3_dir_attrs.block_list[EMU3_BLOCKS_PER_DIR]`, **`EMU3_BLOCKS_PER_DIR = 7`**.
- `EMU3_ENTRIES_PER_BLOCK = 512/32 = 16`; structural max
  `EMU3_MAX_FILES_PER_DIR = 7 × 16 = 112`.
- **EOS UI caps a folder at 100 banks** (B00–B99; the `id` byte is the 2-digit
  per-folder slot, sparse/arbitrary — e.g. the 1 GB ref placed banks at slots
  0, 9 and (other folder) 0, 99).
- dircon blocks are allocated **sequentially** from the pool; the next-free
  block index lives at **block 1, byte 0** (e.g. 0x0F = 15 after blocks 13,14).

`build_emu_hdd` now spans `ceil(N/16)` dircon blocks for the Default Folder,
listing them in `block_list[7]`, numbering slots 0..N-1 across blocks, and
setting the next-free pointer.  Verified: 20 banks → block_list=[13,14], slots
0–15 / 16–19.  **HW-CONFIRMED 2026-06-14**: on `MULTIBLOCK20_emu.hda`, banks
SLOT16 & SLOT19 (which live *only* in the 2nd dircon block, reached via
`block_list[1]`) loaded on the E4XT with working presets.

**Multi-folder (>100 banks) — IMPLEMENTED 2026-06-14:** banks spill from the
system "Default Folder" (id 0x80, banks 0–99) into additional root folders
"Folder 2", "Folder 3", … (id 0x40), each ≤100 banks with per-folder slots
reset to 0.  dircon blocks are laid out sequentially across folders and the
next-free pointer set.  Bounded by disk capacity (≤1023 clusters), root entries
(`root_blocks`×16 = 112 folders) and the dircon pool (169 blocks).  Verified:
150 banks → Default Folder(100, blocks 13–19) + Folder 2(50, blocks 20–23).
(Append `emu_hdd_append` still targets one `--folder` and caps it at 100;
distribute across folders by appending with different `--folder` names.)
