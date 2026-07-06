<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# EMU3 CD-ROM Filesystem — Reverse-Engineered Reference

This document describes the on-disk layout of the **raw EMU3 filesystem
image** that mpc2emu produces for **ZuluSCSI CD-ROM emulation** on the
**E-MU Emulator 4 / E4XT / E4K (EOS 4.x)**, as reverse-engineered by the
mpc2emu project. It is the CD-ROM-side counterpart to
[`docs/E4B_FORMAT.md`](E4B_FORMAT.md) — that document covers what's *inside*
an `.E4B` file, this one covers the filesystem container that lets the
hardware *find and load* it from a simulated CD.

It is **not** official E-MU documentation — it is the result of differential
analysis of working reference images saved on E4XT hardware and commercial
E-mu CD-ROM libraries, cross-checked against the open-source `emu3fs` kernel
module (see [Sources & Attribution](#sources--attribution)).

> **Implementation reference:** the canonical, always-up-to-date version of
> this layout lives in [`writers/iso_builder.py`](../writers/iso_builder.py)
> — that file's doc-comments and this document should be kept in sync. Where
> they disagree, trust the code (and file an issue).

---

## 1. Overview: two unrelated formats behind one `--iso` flag

mpc2emu's `--iso` option produces **two completely different filesystems**
depending on the target machine, because the two emulators' CD-ROM
subsystems are unrelated:

| Target            | Filesystem              | Builder              |
|-------------------|-------------------------|----------------------|
| E4XT / E4K (EOS)  | **EMU3** (proprietary)  | `build_iso()`        |
| K2000/K2500/K2600 | **ISO 9660** (standard) | `build_iso_9660()`   |

The **E4XT's OS reads the EMU3 filesystem directly off the simulated disc —
it does NOT understand ISO 9660.** ZuluSCSI just streams the raw image
bytes; the filesystem inside has to be exactly what the EOS firmware expects
for a "CD-ROM" volume. This document covers that EMU3 image. The Kurzweil
side uses a textbook ISO 9660 Level 1 image (§[5](#5-iso-9660-mode-kurzweil-k2000)),
since the K2000 has a conventional SCSI CD-ROM drive.

Despite the `.iso` extension and the "Build … ISO image" terminology used
throughout the codebase and CLI (kept for user familiarity — these files get
renamed to `CDx.iso` on a ZuluSCSI SD card either way), the EMU3 image is
**not** an ISO 9660 image at all — it is a raw block-device dump of E-mu's
own filesystem, captured byte-for-byte as the firmware would write it to a
real CD-ROM-formatted disc.

---

## 2. EMU3 image layout

```
Block 0:               EMU3 superblock           (512 bytes)
Block 1:               padding                   (zeroed, byte 0 = next-free dircon pointer)
Blocks  2 …  6:        FAT (cluster chain list)  — _FAT_START=2,    _FAT_BLOCKS=5
Blocks  7 … 10:        Root directory            — _ROOT_START=7,   _ROOT_BLOCKS=4
Blocks 11 … 135:       Dir-content blocks        — _DIRCON_START=11, _DIRCON_BLOCKS=125
Blocks 136 … :         E4B file data (clusters)  — _DATA_START=136
```

All blocks are **512 bytes**. This geometry is *fixed* — it is not computed
from the data size, but copied verbatim from working reference images
(Post Industrial, Formula 4000, EII, Vol 10, Platinum, Vol 1 Std). The EOS
firmware appears to expect superblock parameters that match this exact
layout; deviating from it (even while keeping the parameters internally
consistent) produced `FS:??` / `Capacity 0.0mb` errors on hardware during
development. Only the **data area** grows with the number/size of files.

This maps directly onto `build_iso()` in
[`writers/iso_builder.py`](../writers/iso_builder.py):

```
build_iso(e4b_files, output_iso, volume_label)
 ├─ choose cluster size (cse)            §3.1
 ├─ _superblock()                        §2.1
 ├─ pad1  (next-free dircon pointer)     §2 (block 1)
 ├─ _fat_blocks()                        §2.2
 ├─ _root_block()                        §2.3
 ├─ _dircon_block()                      §2.4
 └─ raw E4B file bytes, cluster-padded   §3.2
```

---

## 2.1 Superblock (block 0, 512 bytes)

Ten little-endian `u32` parameters at 4-byte offsets, followed by a handful
of single-byte flags and a checksum:

| Offset  | Field                   | Value in mpc2emu output            |
|---------|-------------------------|-------------------------------------|
| `0x00`  | magic                   | `'EMU3'` (read as LE u32)           |
| `0x04`  | total_blocks - 1        | computed from data size             |
| `0x08`  | start_root_block        | `_ROOT_START` = 7                   |
| `0x0C`  | root_blocks             | `_ROOT_BLOCKS` = 4                  |
| `0x10`  | start_dir_content_block | `_DIRCON_START` = 11                |
| `0x14`  | dir_content_blocks      | `_DIRCON_BLOCKS` = 125              |
| `0x18`  | start_cluster_list_block| `_FAT_START` = 2                    |
| `0x1C`  | cluster_list_blocks     | `_FAT_BLOCKS` = 5                   |
| `0x20`  | start_data_block        | `_DATA_START` = 136                 |
| `0x24`  | total clusters          | computed from data size             |
| `0x28`  | cluster_size_extra (cse)| `4`, `5`, or `6` — see §[3.1](#31-cluster-size-selection) |
| `0x29`  | format flag             | `0x01` — "ALL working ISOs = 1"     |
| `0x2D`  | unknown                 | `0x08` — present in all cse=4/5 working ISOs |
| `0x32`  | disc/format subversion  | `0x01`                              |
| `0x33`  | mandatory constant      | `0x0D` (13)                         |
| `0x1FE` | checksum (LE u16)       | see below                           |

`cluster_size_shift = 15 + cluster_size_extra`, so `cse=4` → 512 KB
clusters, `cse=5` → 1 MB, `cse=6` → 2 MB.

**Checksum** (offset `0x1FE`–`0x1FF`): the sum, modulo 2¹⁶, of all 255
little-endian `u16` words spanning bytes `0x000`–`0x1FD`. Present in every
working reference superblock; without it, the E4XT reports
`FS:?? Capacity 0.0mb` and refuses to mount the volume.

The flag bytes at `0x29`, `0x2D`, `0x32`, `0x33` have no documented meaning —
their *values* were determined purely by byte-diffing six different working
commercial/hardware-saved images (Post Industrial, EII, Vol 10, Platinum,
Vol 1 Std, Formula 4000 Vol. 2) and copying whatever was constant across all
of them. Treat them as "magic constants the firmware checks for", not as
fields with a known semantic role.

## 2.2 FAT / cluster chain list (blocks 2–6)

A flat array of little-endian `u16`/`s16` cluster-chain entries — exactly
the structure a classic FAT filesystem uses, just EMU's own variant:

- `fat[0] = 0x8000` — reserved / media-descriptor entry (matches reference
  images; never allocated to a file).
- For each file, a **sequential** chain: `cluster[i] → cluster[i+1] → … →
  EMU3_LAST_CLUSTER (0x7FFF)`. Because mpc2emu always writes files
  contiguously (cluster `N`, `N+1`, `N+2`, …), the chain is just an
  incrementing run terminated by the end-of-chain marker — there is no
  fragmentation to encode.

5 FAT blocks hold `5 × 256 = 1280` `u16` entries; entry 0 is reserved, so
**1279 clusters** is the hard ceiling for a single image (§[6](#6-known-limits)).

## 2.3 Root directory (blocks 7–10)

One 32-byte folder entry (all further root blocks are zero-filled):

```
name[16]       'Default Folder  '   (space-padded ASCII)
unknown (u8)   0x00
id (u8)        EMU3_DTYPE_1 = 0x40        ← folder marker
block_list[7]  LE s16 each: [first_dircon_block, -1, -1, -1, -1, -1, -1]
```

`-1` (`0xFFFF`) marks an unused slot in the folder's block list — a folder
can reference up to 7 dir-content blocks this way, but mpc2emu only ever
needs one (all E4B files are written into a single flat "Default Folder").

## 2.4 Dir-content block (block 11)

Up to 16 file entries per 512-byte block (`32 bytes × 16 = 512`):

```
name[16]         space-padded ASCII, derived from the E4B filename's stem
unknown (u8)     0x00
id (u8)          sequential file id (0, 1, 2, …)
start_cluster    LE u16 — first cluster of the file's data
clusters         LE u16 — total clusters allocated to the file
blks             LE u16 — blocks used in the LAST cluster   ⚠ see §4.1
brem             LE u16 — bytes used in the last block of the last cluster
type (u8)        EMU3_FTYPE_STD = 0x81
props[5]         b'\x00E4B0'                                ← EIV/E4XT marker
```

`build_iso()` only ever fills the first dir-content block — with one E4B
file per CD image (the normal case), 16 slots is more than enough. Block 1
(the padding block right after the superblock) carries a single non-zero
byte at offset 0: the index of the *next free* dir-content block
(`_DIRCON_START + 1`), mirroring what reference images contain even though
mpc2emu never needs a second one.

---

## 3. Cluster allocation

### 3.1 Cluster size selection

`build_iso()` doesn't hardcode a cluster size — it calls `_choose_cse()` to
pick the **smallest** size (`cse` 4 → 5 → 6, i.e. 512 KB → 1 MB → 2 MB) that
keeps the total cluster count within the 1279-cluster ceiling imposed by the
fixed 5-block FAT (§[2.2](#22-fat--cluster-chain-list-blocks-2-6)):

```python
for cse in (4, 5, 6):
    cluster_size = (1 << (15 + cse - BSIZE_BITS)) * BSIZE
    if ceil(total_data_bytes / cluster_size) <= 1279:
        return cse
```

This choice isn't just about fitting the FAT — it also works around a
**hardware buffering limit**: 1 MB clusters (`cse=5`) reliably caused
`"end of file"` read errors at roughly 60–70% through loading on a real
E4XT, even though the filesystem structure was otherwise valid. 512 KB
clusters (`cse=4`, matching the "Post Industrial" reference disc) load
cleanly. mpc2emu therefore prefers `cse=4` whenever the data fits, and only
steps up to `cse=5`/`cse=6` for larger banks where the FAT-size ceiling
forces it.

### 3.2 File data layout & the `blks`/ceiling trap

Each E4B file is allocated **consecutive** clusters starting at cluster 1
(cluster 0 is reserved by the FAT's `0x8000` sentinel), and its raw bytes
are zero-padded out to a full cluster boundary before being written
(`_pad(raw, cluster_size)`). `_alloc()` then derives the three size fields
that go into the directory entry:

```python
n_clusters = ceil(file_size / cluster_size)
last_used  = file_size - (n_clusters - 1) * cluster_size
brem       = last_used % BSIZE
blks       = ceil(last_used / BSIZE)        # NOT floor!
```

⚠ **The `blks` field must be a ceiling, not a floor — this was the single
hardest-won lesson in this builder.** Using `last_used // BSIZE` (floor)
produces a file that loads to ~99% and then fails with `"end of file"` on
real E4XT hardware: the firmware reads *exactly* `blks` blocks from the
file's last cluster, so under-counting by one leaves the final partial
(< 512-byte) block unread — and that block typically contains the tail of
the sample data or the chunk that the firmware checks last. The fix
(`blks = last_used // BSIZE + (1 if brem else 0)`) matches `emu3fs`'s
`emu3_set_fattrs()`, which increments the block count whenever there's a
remainder — i.e. **a partially-filled final block still counts as a whole
block** for loading purposes, with `brem` separately recording how many of
its bytes are "real" data versus padding.

---

## 4. Encoding conventions & hard-won lessons

### 4.1 Fixed geometry, not computed geometry

It would be natural to assume an EMU3 filesystem builder should compute FAT
size, root size, and dir-content size from the number and size of files —
that's how most FAT-like filesystems work in the abstract. **It doesn't
work that way here.** Every working reference image — regardless of how
many banks or how much data it carries — uses the *exact same* fixed block
offsets (`fat=2+5 root=7+4 dircon=11+125 data=136`). Computing a "tighter"
layout for a small image produced filesystems the E4XT couldn't mount.
**Treat the geometry as a firmware contract, not a filesystem-design
choice** — only the data area's length varies.

### 4.2 The superblock checksum is mandatory

Many filesystem superblocks carry a checksum that's effectively
informational (some drivers don't even verify it). **This one is checked at
mount time.** Omitting it, or getting the summation range/modulus wrong,
produces the exact same `FS:?? Capacity 0.0mb` symptom as a structurally
broken superblock — there is no intermediate "loads with a warning" state.
If you're debugging a `FS:??` error and the rest of the layout looks right,
recompute the checksum over bytes `0x000`–`0x1FD` first.

### 4.3 "ISO" is a misnomer for the EMU3 image — don't let it mislead you

Because the output file is named `*.iso` and the CLI prints "Building …
image", it's tempting to assume there's an ISO 9660 layer somewhere
underneath (volume descriptors, path tables, `;1` version suffixes, etc.).
**There isn't, for the E4XT path.** The EMU3 image is a flat block dump of
E-mu's proprietary filesystem; the `.iso` naming is purely a ZuluSCSI/SD-card
convention (`CDx.iso`) for "this file should be presented as an optical
disc", not a format declaration. Don't go looking for ISO 9660 structures
when debugging an EMU3 image — you won't find any. (The *Kurzweil* path,
§[5](#5-iso-9660-mode-kurzweil-k2000), is the one that's genuinely ISO 9660.)

---

## 5. ISO 9660 mode (Kurzweil K2000)

`build_iso_9660()` is a separate, much simpler code path used when
`--format krz` (or auto-detected K2000/K2500/K2600 output) is combined with
`--iso`. The K2000 has a conventional SCSI CD-ROM drive and reads a
**standard ISO 9660 Level 1** image directly — no proprietary filesystem
involved, and consequently far fewer surprises:

- 2048-byte sectors. Layout: sectors 0–15 reserved (system area, zeroed),
  sector 16 = Primary Volume Descriptor, sector 17 = path table, sector 18
  = root directory extent, sectors 19+ = file data — each file padded out
  to a whole-sector boundary.
- The Volume Descriptor Set occupies the mandatory consecutive run starting
  at LSN 16 (ECMA-119 §8.2): sector 16 = Primary Volume Descriptor, sector
  17 = Volume Descriptor Set Terminator (`vdst`, type `0xFF`). Path table
  (sector 18), root directory extent (sector 19), and file data (sector 20+)
  follow. *(Two structural bugs were found and fixed here on 2026-06-07: the
  VDST was built but never written, and the both-endian 16-bit PVD fields —
  Volume Set Size / Sequence Number / Logical Block Size at offsets
  120-131 — were assigned into 2-byte slices instead of their correct
  4-byte spans, silently growing the PVD by 6 bytes and misaligning every
  sector after it. Neither had been caught because no K2000 hardware test
  had been run yet.)*
- The root directory extent (sector 18) contains the mandatory `.`/`..`
  self-reference records followed by one record per E4B file.
- Filenames are normalized to **unique uppercase 8.3 names** with the
  `;1` ISO 9660 version suffix (`_iso9660_unique_names()`): each input
  filename's stem is uppercased, non-alphanumeric characters become `_`,
  truncated to 5 characters, and suffixed with a zero-padded 3-digit index
  plus `.E4B;1` — e.g. `Inst-Piano-F9 Grand Piano.E4B` → `INST001.E4B;1`.
- Both-endian (`_iso9660_both16`/`_iso9660_both32`) fields are written as
  required by the spec (LE then BE, back to back) — a detail that's easy to
  get backwards and produces a disc that *some* readers tolerate and others
  reject outright.

Because this is a standards-compliant format with widely available
reference implementations and documentation, it required none of the
hardware-differential reverse-engineering that the EMU3 path did — the
`_iso9660_*` helpers are a direct, minimal implementation of ECMA-119
("ISO 9660") Level 1.

---

## 6. Known limits

| Limit                                  | Value                          | Source / reason |
|----------------------------------------|--------------------------------|-----------------|
| Max clusters per EMU3 image            | 1279                           | `5 FAT blocks × 256 entries/block - 1` reserved entry — §[2.2](#22-fat--cluster-chain-list-blocks-2-6) |
| Max EMU3 image size (cse=4, 512 KB)    | ≈ 624 MB (`1279 × 512 KB`)     | derived |
| Max EMU3 image size (cse=6, 2 MB)      | ≈ 2.5 GB (`1279 × 2 MB`)       | derived; `_choose_cse()` fallback |
| File entries per dir-content block     | 16                             | `512 / 32` — §[2.4](#24-dir-content-block-block-11) |
| Cluster size causing hardware EOF bug  | 1 MB (`cse=5`)                 | confirmed on real E4XT — §[3.1](#31-cluster-size-selection) |
| ISO 9660 filename length               | 8.3 (+ `;1` version)           | ECMA-119 Level 1 — §[5](#5-iso-9660-mode-kurzweil-k2000) |

In practice, mpc2emu's `--bank-size` option keeps individual `.E4B` files
within vintage sample-RAM budgets (typically ≤ 32 MB), so the EMU3 image
ceilings above are rarely a practical constraint — one CD image normally
holds exactly one bank.

---

## Sources & Attribution

This reverse-engineering effort drew on:

- **Hardware-saved EMU3 CD images** created and dumped by Jan Lentfer
  (Post Industrial, Formula 4000, EII, Vol 10, Platinum, Vol 1 Std, and
  others referenced by name above) — the primary source for the fixed
  geometry, superblock flag bytes, checksum algorithm, and the `blks`
  ceiling-vs-floor behaviour, all confirmed by loading mpc2emu-built images
  on real E4XT hardware via ZuluSCSI.
- **emu3fs** by David García Goñi —
  <https://github.com/dagargo/emu3fs> (GPL-2.0-or-later) — the Linux kernel
  module that documents the EMU3 on-disk structures in source form; in
  particular `emu3_set_fattrs()` is the reference for the `blks`/`brem`
  ceiling convention described in §[3.2](#32-file-data-layout--the-blksfloor-trap).
- **ECMA-119 ("ISO 9660")** — the public standard underlying
  `build_iso_9660()` (§[5](#5-iso-9660-mode-kurzweil-k2000)); no
  reverse-engineering was needed for this path.

No third-party source code was copied into mpc2emu; this document and the
corresponding builder (`writers/iso_builder.py`) are independent
implementations informed by the above sources plus original hardware
differential analysis.
