# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# EMU3 filesystem structure informed by emu3fs:
#   Copyright (C) 2014-2024  David García Goñi <dagargo@gmail.com>
#   https://github.com/dagargo/emu3fs  —  GPL-2.0-or-later
# No source code was copied; this is an independent Python implementation
# of the documented on-disk structures, verified against reference images
# saved on E4XT hardware and commercial E-mu CD-ROM libraries.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
EMU3 Filesystem Image Builder for ZuluSCSI CD-ROM Emulation
------------------------------------------------------------
Produces a raw EMU3 filesystem image that ZuluSCSI presents to the E4XT
as a CD-ROM drive.  The E4XT's OS reads this filesystem directly —
it does NOT use ISO 9660.

Verified structure (confirmed from working reference images):

  Block 0:               EMU3 superblock
  Block 1:               padding (zeros)
  Blocks fat_start …:    FAT (cluster chain list, LE u16 per entry)
  Blocks root_start …:   Root directory (EMU3 folder entries)
  Blocks dircon_start …: Dir-content blocks (EMU3 file entries)
  Blocks data_start …:   E4B file data (consecutive clusters)

Superblock (512 bytes, LE u32 parameters at 4-byte offsets):
  [0]  'EMU3' magic
  [1]  total_blocks - 1
  [2]  start_root_block
  [3]  root_blocks
  [4]  start_dir_content_block
  [5]  dir_content_blocks
  [6]  start_cluster_list_block
  [7]  cluster_list_blocks
  [8]  start_data_block
  [9]  total clusters
  [0x28] cluster_size_extra  (cluster_size_shift = 15 + this)

Directory entry (emu3_dentry, 32 bytes):
  name[16]      — space-padded ASCII
  unknown (u8)  — 0
  id (u8)       — 0x40 for folder, sequential file id for files
  union (14 bytes):
    folder: block_list[7] (LE s16, -1 = free)
    file:   start_cluster, clusters, blks, bytes (LE u16 each)
            type (u8), props[5] ('\0E4B0' for EIV/E4XT)
            blks = ceil(last_cluster_bytes / 512)  ← MUST be ceiling, not floor.
            Using floor causes "end of file" at ~99% on E4XT (confirmed fix:
            matches emu3fs emu3_set_fattrs() which increments blocks when
            there is a remainder, i.e. the last block is partially filled).

Fixed filesystem geometry matching working reference images (Post Industrial,
Protozoa):  start_fat=2, fat_blocks=5, start_root=7, root_blocks=4,
start_dircon=11, dircon_blocks=125, start_data=136.
Cluster size 1 MB (cse=5) fits within 5 FAT blocks and produces the
identical fixed-position layout the EOS firmware expects.
"""

import struct
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BSIZE            = 512
BSIZE_BITS       = 9
EMU3_MAGIC       = b'EMU3'
EMU3_FTYPE_STD   = 0x81
EMU3_DTYPE_1     = 0x40       # directory type marker (CD: user folder)
EMU3_DTYPE_DEFAULT = 0x80     # HDD "Default Folder" marker (system/default)
EMU3_LAST_CLUSTER = 0x7FFF    # end-of-chain marker in FAT
EMU3_BLOCKS_PER_DIR   = 7     # dir uses up to 7 dir-content blocks (emu3fs)
EMU3_ENTRIES_PER_BLOCK = BSIZE // 32   # 16 entries per 512-byte block
EMU3_MAX_FILES_PER_DIR = EMU3_BLOCKS_PER_DIR * EMU3_ENTRIES_PER_BLOCK  # 112 (structural)
EMU3_BANKS_PER_FOLDER  = 100  # EOS UI limit: 2-digit folder slots B00..B99

# Fixed filesystem geometry — must match what the EOS/E4XT firmware expects.
# Reference images (PostInd, Formula 4000, etc.) all use:
#   start_fat=2  fat_blocks=5  start_root=7  root_blocks=4
#   start_dircon=11  dircon_blocks=125  start_data=136
#
# CLUSTER SIZE: use the SMALLEST cse that fits all data within 5 FAT blocks.
# The E4XT CD reader has a limited buffer; 1 MB clusters (cse=5) cause
# "end of file" at ~60-70% load.  cse=4 (512 KB) matches PostInd and works.
# build_iso() selects cse dynamically: 4 → 5 → 6 as data grows.

_FAT_START    = 2
_FAT_BLOCKS   = 5    # 5 × 256 = 1280 FAT entries → 1279 usable clusters
_ROOT_START   = 7    # = _FAT_START + _FAT_BLOCKS
_ROOT_BLOCKS  = 4
_DIRCON_START = 11   # = _ROOT_START + _ROOT_BLOCKS
_DIRCON_BLOCKS = 125
_DATA_START   = 136  # = _DIRCON_START + _DIRCON_BLOCKS

# Maximum clusters per image with 5 FAT blocks
_MAX_CLUSTERS = _FAT_BLOCKS * (BSIZE // 2) - 1  # = 1279

# ── EMU3 geometry profiles ────────────────────────────────────────────────────
# The same EMU3 filesystem is laid out with two *fixed* geometries: the CD/ISO
# profile (data-sized image) and the hard-disk profile.  RE'd from E4XT-formatted
# 1/2/4 GB references (docs/re_procedures/emu_hdd_fs.md): the HDD directory
# geometry is constant across disk sizes; only the cluster size scales (cse
# 5→6→7 at 1→2→4 GB) to keep the cluster count ≤ 1023 (= 4 FAT blocks × 256 − 1).
from collections import namedtuple as _namedtuple
_Geom = _namedtuple('_Geom', 'fat_start fat_blocks root_start root_blocks '
                             'dircon_start dircon_blocks data_start max_clusters')
_CD_GEOM  = _Geom(_FAT_START, _FAT_BLOCKS, _ROOT_START, _ROOT_BLOCKS,
                  _DIRCON_START, _DIRCON_BLOCKS, _DATA_START, _MAX_CLUSTERS)
_HDD_GEOM = _Geom(fat_start=2, fat_blocks=4, root_start=6, root_blocks=7,
                  dircon_start=13, dircon_blocks=169, data_start=182,
                  max_clusters=4 * (BSIZE // 2) - 1)   # = 1023

def _choose_cse(file_sizes) -> int:
    """Return the smallest cse value whose clusters fit all files in 5 FAT blocks.

    CR-9: clusters are allocated **per file** (ceil(size/cluster)), so the real
    count is sum(ceil(size_i/cluster)) — which exceeds ceil(sum/cluster) by up to
    one cluster per file.  Summing the per-file ceilings (not the total) is what
    prevents `fat[cluster]` overrunning `_MAX_CLUSTERS`.
    """
    # Accept either a total int (legacy) or an iterable of file sizes.
    sizes = [file_sizes] if isinstance(file_sizes, int) else list(file_sizes)
    for cse in (4, 5, 6):
        cluster_size = (1 << (15 + cse - BSIZE_BITS)) * BSIZE
        clusters = sum((s + cluster_size - 1) // cluster_size for s in sizes)
        if clusters <= _MAX_CLUSTERS:
            return cse
    raise ValueError(
        f"Bank too large for one EMU3 image: {sum(sizes)} bytes across "
        f"{len(sizes)} file(s) needs more than {_MAX_CLUSTERS} clusters even at "
        f"the largest cluster size. Split the bank into more / smaller images.")
    return 6  # fallback (handles up to ~5 GB)

# Module-level defaults (used by helpers; overridden per-call in build_iso)
CLUSTER_SIZE_EXTRA = 4
CLUSTER_SIZE_SHIFT = 15 + CLUSTER_SIZE_EXTRA
BLOCKS_PER_CLUSTER = 1 << (CLUSTER_SIZE_SHIFT - BSIZE_BITS)
CLUSTER_SIZE       = BLOCKS_PER_CLUSTER * BSIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alloc(file_size: int, cluster_sz: int = CLUSTER_SIZE):
    """Return (clusters, blks, bytes_rem) matching the EOS on-disk convention.

    Mirrors emu3fs emu3_set_fattrs():
      clusters = ceil(size / cluster_size)
      blks     = ceil(last_cluster_bytes / BSIZE)   ← emu3fs uses +1 when remainder > 0
      brem     = last_cluster_bytes % BSIZE          ← bytes used in the last partial block

    Using floor instead of ceil for blks causes "end of file" errors on E4XT:
    the hardware reads exactly blks blocks from the last cluster, so being 1 short
    leaves the final 512 bytes unread.
    """
    if file_size == 0:
        return 1, 0, 0
    n_clust   = (file_size + cluster_sz - 1) // cluster_sz
    last_used = file_size - (n_clust - 1) * cluster_sz
    brem      = last_used % BSIZE
    blks      = last_used // BSIZE + (1 if brem else 0)  # ceil, like emu3fs
    return n_clust, blks, brem


def _pad(data: bytes, block_align: int = BSIZE) -> bytes:
    """Pad bytes to a multiple of block_align."""
    rem = len(data) % block_align
    return data + b'\x00' * ((-rem) % block_align)


# ---------------------------------------------------------------------------
# EMU3 structure builders
# ---------------------------------------------------------------------------

def _superblock(total_blocks: int, n_clusters: int, volume_label: str,
                cse: int = CLUSTER_SIZE_EXTRA, geom: _Geom = _CD_GEOM) -> bytes:
    sb = bytearray(BSIZE)
    params = [
        struct.unpack('<I', EMU3_MAGIC)[0],  # [0] 'EMU3'
        total_blocks - 1,                    # [1]
        geom.root_start,                     # [2]
        geom.root_blocks,                    # [3]
        geom.dircon_start,                   # [4]
        geom.dircon_blocks,                  # [5]
        geom.fat_start,                      # [6]
        geom.fat_blocks,                     # [7]
        geom.data_start,                     # [8]
        n_clusters,                          # [9]
    ]
    for i, v in enumerate(params):
        struct.pack_into('<I', sb, i * 4, v)

    # Bytes beyond the known parameters — present in every working reference ISO,
    # absent from ours, and coincide exactly with "FS:??" on the E4XT hardware.
    # Verified across 6 different working ISOs (PostInd, EII, Vol10, Platinum,
    # Vol1Std, Formula4000 Vol.2):
    sb[0x28] = cse                 # cluster size shift (always set)
    sb[0x29] = 0x01                # EIV/EMU4 format flag — ALL working ISOs = 1
    sb[0x2D] = 0x08                # present in all cse=4/5 working ISOs
    sb[0x32] = 0x01                # disc/format subversion
    sb[0x33] = 0x0D                # mandatory constant = 13

    # Superblock checksum at bytes 0x1FE-0x1FF:
    # sum of all 255 LE u16 words in bytes 0x000-0x1FD, modulo 2^16.
    # Present in every working ISO; absent = E4XT reports 'FS:?? Capacity 0.0mb'.
    ck = 0
    for i in range(0, 0x1FE, 2):
        ck = (ck + struct.unpack_from('<H', sb, i)[0]) & 0xFFFF
    struct.pack_into('<H', sb, 0x1FE, ck)
    return bytes(sb)


def _fat_blocks(file_allocs: List[int], n_clusters: int,
                fat_blk_count: int) -> bytes:
    """
    Build the FAT (cluster chain list).
    fat[0] = 0x8000 (reserved, matches reference images)
    For each file: sequential chain cluster_start → … → EOF
    """
    fat = [0] * (fat_blk_count * (BSIZE // 2))
    fat[0] = 0x8000  # reserved / media descriptor

    cluster = 1
    for n_clust in file_allocs:
        for j in range(n_clust):
            if j < n_clust - 1:
                fat[cluster] = cluster + 1
            else:
                fat[cluster] = EMU3_LAST_CLUSTER
            cluster += 1

    out = bytearray()
    for v in fat[:fat_blk_count * (BSIZE // 2)]:
        # Signed short LE (EMU_LAST_CLUSTER = 0x7FFF fits in u16/s16)
        out += struct.pack('<H', v & 0xFFFF)
    return bytes(out)


def _folder_entry(dir_name: str, dircon_blocks, dtype: int = EMU3_DTYPE_1) -> bytes:
    """A 32-byte root directory entry for one folder.
    dircon_blocks: int or list of the folder's dir-content block indices, stored
                   in block_list[7] (unused slots = 0xFFFF / -1).
    dtype: 0x40 = user folder, 0x80 = HDD system "Default Folder".
    """
    name = dir_name.encode('ascii', errors='replace')[:16].ljust(16, b' ')
    if isinstance(dircon_blocks, int):
        dircon_blocks = [dircon_blocks]
    block_list = (list(dircon_blocks)[:EMU3_BLOCKS_PER_DIR]
                  + [0xFFFF] * (EMU3_BLOCKS_PER_DIR - len(dircon_blocks)))
    entry = name + bytes([0x00, dtype])
    for b in block_list:
        entry += struct.pack('<H', b & 0xFFFF)
    assert len(entry) == 32
    return entry


def _root_block(dir_name: str, dircon_blocks, dtype: int = EMU3_DTYPE_1) -> bytes:
    """One 512-byte root directory block with a single folder entry (the rest of
    the root blocks are written as zeros by the caller)."""
    return _folder_entry(dir_name, dircon_blocks, dtype) + b'\x00' * (BSIZE - 32)


def _dircon_block(files: List[dict]) -> bytes:
    """
    One 512-byte dir-content block containing up to 16 file entries.
    files: list of dicts with keys: name, start_cluster, clusters, blks, brem,
           and optionally 'slot' (the per-folder 2-digit id byte, 0-99).  When
           'slot' is absent the entry index is used (CD: ≤16 banks → same value).
    """
    block = bytearray(BSIZE)
    for i, f in enumerate(files[:EMU3_ENTRIES_PER_BLOCK]):
        off  = i * 32
        name = f['name'].encode('ascii', errors='replace')[:16].ljust(16, b' ')
        block[off:off+16] = name
        block[off+16] = 0x00                  # unknown
        block[off+17] = f.get('slot', i) & 0xFF   # 2-digit folder slot / file id
        struct.pack_into('<H', block, off+18, f['start_cluster'])
        struct.pack_into('<H', block, off+20, f['clusters'])
        struct.pack_into('<H', block, off+22, f['blks'])
        struct.pack_into('<H', block, off+24, f['brem'])
        block[off+26] = EMU3_FTYPE_STD
        block[off+27:off+32] = b'\x00E4B0'   # props: EIV/E4XT marker
    return bytes(block)


# ---------------------------------------------------------------------------
# ISO 9660 builder — for K2000 / standard CD-ROM readers
# ---------------------------------------------------------------------------

def _iso9660_date(t) -> bytes:
    import time as _time
    t = t or _time.gmtime()
    return bytes([t.tm_year - 1900, t.tm_mon, t.tm_mday,
                  t.tm_hour, t.tm_min, t.tm_sec, 0])

def _iso9660_pvd_date(t) -> bytes:
    import time as _time
    t = t or _time.gmtime()
    s = f"{t.tm_year:04d}{t.tm_mon:02d}{t.tm_mday:02d}{t.tm_hour:02d}{t.tm_min:02d}{t.tm_sec:02d}00"
    return s.encode('ascii') + b'\x00'

def _iso9660_both32(n: int) -> bytes:
    return struct.pack('<I', n) + struct.pack('>I', n)

def _iso9660_both16(n: int) -> bytes:
    return struct.pack('<H', n) + struct.pack('>H', n)

def _iso9660_dir_record(name: bytes, extent: int, size: int, is_dir: bool,
                         ts) -> bytes:
    flags    = 0x02 if is_dir else 0x00
    name_len = len(name)
    rec_len  = 33 + name_len + (name_len % 2 == 0)   # even padding
    rec = bytes([rec_len, 0])
    rec += _iso9660_both32(extent)
    rec += _iso9660_both32(size)
    rec += _iso9660_date(ts)
    rec += bytes([flags, 0, 0])
    rec += _iso9660_both16(1)
    rec += bytes([name_len]) + name
    if name_len % 2 == 0:
        rec += b'\x00'
    return rec

def _iso9660_unique_names(filenames: List[str]) -> List[str]:
    """Unique uppercase 8.3 names for ISO 9660 Level 1.

    The extension is taken from each source file (``.KRZ`` for K2000 banks,
    ``.E4B`` for E4XT banks) so the K2000/E4XT recognises the bank type — it must
    not be hardcoded."""
    names = []
    for i, fn in enumerate(filenames):
        ext = (Path(fn).suffix.lstrip('.').upper() or 'E4B')[:3]
        stem = Path(fn).stem.upper()
        stem = ''.join(c if c.isalnum() or c == '_' else '_' for c in stem)
        prefix = stem[:5].rstrip('_') or 'BANK'
        names.append(f"{prefix}{i+1:03d}.{ext};1")
    return names

def build_k2000_disk(krz_files: List[str], output_img: str,
                     volume_label: str = "K2000", subdir: str = "BANKS") -> None:
    """Build a Kurzweil K2000/K2500 SCSI **disk-image copy** (FAT16, no partition).

    This is the universally-compatible CD/disk form: every K2000 OS reads it.
    (ISO 9660 — `build_iso_9660` — only works on K2000 OS **v3.87+** / K2500 2.96+;
    older OS "require an image of a Kurzweil/DOS-formatted disk" — see the Kurzweil
    SCSI doc + the v3.87 release notes.)  Layout mirrors a real K2000 CD (verified
    against a working factory CD): FAT16, BPB at sector 0, **no MBR/partition**, OEM
    ``KCDM1.2``, KRZ files in a sub-directory with clean 8.3 names.  ZuluSCSI serves
    the image as a CD regardless of the internal filesystem (hence the .iso ext)."""
    from writers.fat16 import format_new
    total = sum(Path(f).stat().st_size for f in krz_files)
    img_mb = max(16, int(total / 1024 / 1024 * 1.08) + 8)
    print(f"\nBuilding K2000 FAT16 disk image: {output_img}")
    print(f"  Volume label: {volume_label.upper()[:11]}  files: {len(krz_files)}  "
          f"size: {img_mb} MB")
    # Pick sectors/cluster keeping the FAT16 cluster count in 4085..65524.
    fs = None
    for spc in (8, 16, 32, 64):
        try:
            fs = format_new(output_img, img_mb, label=volume_label,
                            oem=b'KCDM1.2', partition=False, spc=spc)
            break
        except ValueError:
            continue
    if fs is None:
        raise ValueError(f"cannot fit {img_mb} MB in a single FAT16 volume "
                         f"(max ~2 GB); split into multiple CDs.")
    folder = fs.makedir(subdir) if subdir else None
    pfx = ''.join(c for c in volume_label.upper() if c.isalnum())[:5] or 'BANK'
    for i, kf in enumerate(krz_files, 1):
        fs.add_file(str(kf), f"{pfx}_{i:02d}.KRZ", folder_cluster=folder)
        print(f"  + {subdir}/{pfx}_{i:02d}.KRZ  ({Path(kf).stat().st_size/1024/1024:.1f} MB)")
    fs.close()
    print(f"  → ZuluSCSI: copy to SD card, rename to CDx.iso")


def build_iso_9660(e4b_files: List[str], output_iso: str,
                   volume_label: str = "EMU_BANK") -> None:
    """
    Build a standard ISO 9660 CD-ROM image for the Kurzweil K2000/K2500/K2600.
    NOTE: only K2000 OS **v3.87+** (K2500 2.96+/4.32+, any K2600) can read ISO 9660;
    older OS need `build_k2000_disk` (FAT16 disk-image copy) instead.
    (The E4XT uses EMU3 filesystem instead — use build_iso() for that.)
    """
    import time as _time
    print(f"\nBuilding ISO 9660 image: {output_iso}")
    print(f"  Volume label: {volume_label.upper()[:32]}")
    print(f"  Files: {len(e4b_files)}")

    SEC  = 2048
    ts   = _time.gmtime()
    label = volume_label[:32].upper().encode('ascii')

    iso_names = _iso9660_unique_names([Path(f).name for f in e4b_files])

    # Volume Descriptor Set occupies consecutive sectors starting at LSN 16
    # and must end with a Volume Descriptor Set Terminator (ECMA-119 §8.2):
    #   sector 16 = PVD, sector 17 = VDST.
    # Everything else (path table, root directory, file data) follows.
    path_table_sec = 18
    root_sec       = 19

    # Lay out files starting right after the root directory extent
    files = []
    cur = root_sec + 1
    for path, iso_name in zip(e4b_files, iso_names):
        p    = Path(path)
        size = p.stat().st_size
        files.append((str(p), iso_name.encode('ascii'), cur, size))
        cur += (size + SEC - 1) // SEC

    # Root directory record
    dot      = _iso9660_dir_record(b'\x00', root_sec, SEC, True, ts)
    dotdot   = _iso9660_dir_record(b'\x01', root_sec, SEC, True, ts)
    dir_data = dot + dotdot
    for _, iso_name, sec, size in files:
        dir_data += _iso9660_dir_record(iso_name, sec, size, False, ts)
    dir_data = dir_data.ljust(SEC, b'\x00')

    # PVD
    pvd = bytearray(SEC)
    pvd[0]      = 0x01;  pvd[1:6] = b'CD001';  pvd[6] = 0x01
    pvd[8:40]   = b' ' * 32
    pvd[40:40+len(label)] = label
    pvd[40+len(label):72] = b' ' * (32 - len(label))
    pvd[80:88]  = _iso9660_both32(cur)
    # Both-endian 16-bit fields occupy 4 bytes each (LE u16 + BE u16):
    # Volume Set Size (120-123), Volume Sequence Number (124-127),
    # Logical Block Size (128-131) — per ECMA-119 §8.4.
    pvd[120:124]= _iso9660_both16(1)
    pvd[124:128]= _iso9660_both16(1)
    pvd[128:132]= _iso9660_both16(SEC)
    pvd[132:140]= _iso9660_both32(10)
    pvd[140:144]= struct.pack('<I', path_table_sec)
    pvd[148:152]= struct.pack('>I', path_table_sec)
    root_rec = _iso9660_dir_record(b'\x00', root_sec, len(dir_data), True, ts)
    pvd[156:156+34] = root_rec[:34]
    pvd[190:574] = b' ' * 384
    pvd[813:830] = _iso9660_pvd_date(ts)
    pvd[830:847] = _iso9660_pvd_date(ts)
    pvd[847:864] = b'0' * 16 + b'\x00'
    pvd[864:881] = _iso9660_pvd_date(ts)
    pvd[881]     = 0x01

    # VDST
    vdst = bytearray(SEC)
    vdst[0] = 0xFF;  vdst[1:6] = b'CD001';  vdst[6] = 0x01

    # Path table
    ptl = struct.pack('<BIBB', 1, root_sec, 1, 1) + b'\x00'
    ptl = ptl.ljust(SEC, b'\x00')

    with open(output_iso, 'wb') as f:
        f.write(b'\x00' * (SEC * 16))   # system area
        f.write(bytes(pvd))              # sector 16 — Primary Volume Descriptor
        f.write(bytes(vdst))             # sector 17 — Volume Descriptor Set Terminator
        f.write(ptl)                     # sector 18 — path table
        f.write(dir_data)                # sector 19 — root directory extent
        for path, iso_name, sec, size in files:
            name_str = iso_name.decode().split(';')[0]
            print(f"  {Path(path).name} → /{name_str}  (sector {sec})")
            total = 0     # CR-16: stream in chunks + pad separately
            with open(path, 'rb') as src:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
            pad = (-total) % SEC
            if pad:
                f.write(b'\x00' * pad)

    size_mb = Path(output_iso).stat().st_size / 1024 / 1024
    print(f"  Done: {output_iso} ({size_mb:.1f} MB)")
    print()
    print("  ZuluSCSI usage (K2000):")
    print(f"    1. Copy {Path(output_iso).name} to SD card root")
    print(f"    2. Rename to CDx.iso (e.g. CD1.iso)")
    print(f"    3. Power on K2000 → Load → CD-ROM → select bank")


# ---------------------------------------------------------------------------
# EMU3 Public API  (E4XT / ZuluSCSI CD emulation)
# ---------------------------------------------------------------------------

def build_iso(e4b_files: List[str], output_iso: str,
              volume_label: str = "EMU_BANK") -> None:
    """
    Build an EMU3 filesystem image containing the given E4B files.
    The image can be renamed to CDx.iso and placed on a ZuluSCSI SD card.

    Args:
        e4b_files:    List of paths to .E4B files to include
        output_iso:   Output path for the image file
        volume_label: Volume label (max 16 chars, will be uppercased)
    """
    print(f"\nBuilding EMU3 image: {output_iso}")
    label = volume_label[:16].upper()
    print(f"  Volume label: {label}")
    print(f"  Files: {len(e4b_files)}")

    # ── choose cluster size: smallest cse whose clusters fit in 5 FAT blocks ──
    file_sizes = [Path(p).stat().st_size for p in e4b_files]
    cse        = _choose_cse(file_sizes)   # CR-9: per-file cluster ceilings
    clust_sz   = (1 << (15 + cse - BSIZE_BITS)) * BSIZE
    bpc        = clust_sz // BSIZE   # blocks per cluster

    # ── per-file layout ──────────────────────────────────────────────────────
    file_infos = []
    allocs     = []
    for path in e4b_files:
        p    = Path(path)
        size = p.stat().st_size
        n_c, blks, brem = _alloc(size, clust_sz)
        allocs.append(n_c)
        file_infos.append({
            'path':     str(p),
            'name':     p.stem[:16],
            'size':     size,
            'clusters': n_c,
            'blks':     blks,
            'brem':     brem,
        })

    n_clusters   = sum(allocs)
    total_blocks = _DATA_START + n_clusters * bpc

    # ── assign start clusters ────────────────────────────────────────────────
    cluster = 1
    for fi in file_infos:
        fi['start_cluster'] = cluster
        cluster += fi['clusters']

    # ── build filesystem blocks ──────────────────────────────────────────────
    sb   = _superblock(total_blocks, n_clusters, label, cse)

    pad1 = bytearray(BSIZE)
    pad1[0] = _DIRCON_START + 1   # next-free dircon block pointer

    fat    = _fat_blocks(allocs, n_clusters, _FAT_BLOCKS)
    root   = _root_block("Default Folder  ", _DIRCON_START)
    root  += b'\x00' * BSIZE * (_ROOT_BLOCKS - 1)
    dircon = _dircon_block(file_infos)
    dircon += b'\x00' * BSIZE * (_DIRCON_BLOCKS - 1)

    print(f"  Layout: fat={_FAT_START}+{_FAT_BLOCKS}  root={_ROOT_START}+{_ROOT_BLOCKS}"
          f"  dircon={_DIRCON_START}+{_DIRCON_BLOCKS}  data={_DATA_START}"
          f"  clusters={n_clusters}  cse={cse}  cluster_size={clust_sz//1024}KB")

    # ── write image ──────────────────────────────────────────────────────────
    with open(output_iso, 'wb') as f:
        f.write(bytes(sb))
        f.write(bytes(pad1))
        f.write(fat)
        f.write(root)
        f.write(dircon)
        for fi in file_infos:
            # CR-16: stream in 1 MB chunks + pad separately (was read-whole-file
            # then build a second padded copy).
            total = 0
            with open(fi['path'], 'rb') as src:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
            pad = (-total) % clust_sz
            if pad:
                f.write(b'\x00' * pad)
            print(f"  {fi['name']:16s}  start_cluster={fi['start_cluster']:5d}  "
                  f"clusters={fi['clusters']:4d}  "
                  f"({fi['size']/1024/1024:.1f} MB)")

    size_mb = Path(output_iso).stat().st_size / 1024 / 1024
    print(f"  Done: {output_iso} ({size_mb:.1f} MB)")
    print()
    print("  ZuluSCSI usage:")
    print(f"    1. Copy {Path(output_iso).name} to SD card root")
    print(f"    2. Rename to CDx.iso (e.g. CD1.iso) on the SD card")
    print(f"    3. Power on E4XT → Load → CD-ROM → select bank")


def _emu_bank_name(path) -> str:
    """Clean bank name for an EMU-fs dircon entry.  EMU-fs numbers banks by a
    2-digit folder slot (the dircon `id` byte, 0-99), NOT by a name prefix — so
    strip any FAT-style `B.NNN-` / `B.NN-` prefix the file may carry."""
    import re
    stem = re.sub(r'^B\.\d{2,3}-', '', Path(path).stem)
    return stem[:16]


def build_emu_hdd(e4b_files: List[str], output_path: str,
                  volume_label: str = "EMU_DISK", size_mb: int = 1024) -> None:
    """Build a hard-disk EMU-fs (EMU3) image of the requested size with the banks
    in a "Default Folder" and the remaining clusters free (so EOS can save onto
    it).  Uses the HDD geometry profile RE'd from E4XT-formatted 1/2/4 GB
    references (docs/re_procedures/emu_hdd_fs.md): fixed directory geometry,
    full-disk total_blocks, 1023-cluster cap, cluster size scaled to the disk
    (cse 4/5/6/7 HW-verified for 512 MB/1/2/4 GB; larger extrapolated)."""
    geom        = _HDD_GEOM
    label       = volume_label[:16].upper()
    disk_blocks = (int(size_mb) * 1024 * 1024) // BSIZE

    # cluster size: smallest cse whose clusters span the whole disk within the
    # 1023-cluster cap (so total_clusters = 4 FAT blocks × 256 − 1).
    cse = None
    for c in range(4, 16):
        bpc_try = 1 << (15 + c - BSIZE_BITS)
        if (disk_blocks - geom.data_start) // bpc_try <= geom.max_clusters:
            cse = c
            break
    if cse is None:
        raise ValueError(f"--hda-size {size_mb} MB too large for the EMU-fs HDD "
                         f"geometry (max {geom.max_clusters} clusters).")
    clust_sz      = (1 << (15 + cse - BSIZE_BITS)) * BSIZE
    bpc           = clust_sz // BSIZE
    disk_clusters = min((disk_blocks - geom.data_start) // bpc, geom.max_clusters)

    print(f"\nBuilding EMU-fs hard-disk image: {output_path}")
    print(f"  Volume label: {label}   size: {size_mb} MB")

    file_infos, allocs = [], []
    for path in e4b_files:
        size = Path(path).stat().st_size
        n_c, blks, brem = _alloc(size, clust_sz)
        allocs.append(n_c)
        file_infos.append({'path': str(Path(path)), 'name': _emu_bank_name(path),
                           'size': size, 'clusters': n_c, 'blks': blks, 'brem': brem})
    n_used = sum(allocs)
    if n_used > disk_clusters:
        raise ValueError(f"banks need {n_used} clusters but the {size_mb} MB disk "
                         f"holds only {disk_clusters} at {clust_sz//1024} KB/cluster.")

    cluster = 1
    for fi in file_infos:
        fi['start_cluster'] = cluster
        cluster += fi['clusters']

    # Split banks into folders of <=100 (B00..B99); first folder is the system
    # "Default Folder", the rest are user folders ("Folder 2", "Folder 3", ...).
    folders = []                       # (name, dtype, [bank dicts])
    for fi_start in range(0, len(file_infos), EMU3_BANKS_PER_FOLDER):
        idx = len(folders)
        banks = file_infos[fi_start:fi_start + EMU3_BANKS_PER_FOLDER]
        for slot, fi in enumerate(banks):
            fi['slot'] = slot          # 2-digit per-folder slot (resets per folder)
        name  = "Default Folder" if idx == 0 else f"Folder {idx + 1}"
        dtype = EMU3_DTYPE_DEFAULT if idx == 0 else EMU3_DTYPE_1
        folders.append((name, dtype, banks))
    if not folders:                    # empty bank set → one empty Default Folder
        folders = [("Default Folder", EMU3_DTYPE_DEFAULT, [])]

    # lay dircon blocks out sequentially; each folder spans ceil(n/16) of them
    root_bytes = bytearray()
    dircon_bytes = bytearray()
    next_dircon = geom.dircon_start
    for name, dtype, banks in folders:
        n_blk = max(1, (len(banks) + EMU3_ENTRIES_PER_BLOCK - 1) // EMU3_ENTRIES_PER_BLOCK)
        ids = list(range(next_dircon, next_dircon + n_blk))
        next_dircon += n_blk
        root_bytes += _folder_entry(name, ids, dtype)
        for i in range(0, max(len(banks), 1), EMU3_ENTRIES_PER_BLOCK):
            dircon_bytes += _dircon_block(banks[i:i + EMU3_ENTRIES_PER_BLOCK])
    used_dircon = next_dircon - geom.dircon_start
    if len(folders) > geom.root_blocks * EMU3_ENTRIES_PER_BLOCK:
        raise ValueError(f"{len(folders)} folders exceeds the root capacity "
                         f"({geom.root_blocks * EMU3_ENTRIES_PER_BLOCK}).")
    if used_dircon > geom.dircon_blocks:
        raise ValueError(f"{len(file_infos)} banks need {used_dircon} dircon blocks "
                         f"but only {geom.dircon_blocks} are available.")

    sb     = _superblock(disk_blocks, disk_clusters, label, cse, geom)
    pad1   = bytearray(BSIZE)
    pad1[0] = next_dircon                       # next-free dircon block pointer
    fat    = _fat_blocks(allocs, n_used, geom.fat_blocks)
    root   = bytes(root_bytes) + b'\x00' * (geom.root_blocks * BSIZE - len(root_bytes))
    dircon = bytes(dircon_bytes) + b'\x00' * (geom.dircon_blocks * BSIZE - len(dircon_bytes))

    folder_summary = ", ".join(f"{n}:{len(b)}" for n, _d, b in folders)
    print(f"  Layout: fat={geom.fat_start}+{geom.fat_blocks}  "
          f"root={geom.root_start}+{geom.root_blocks}  "
          f"dircon={geom.dircon_start}+{geom.dircon_blocks}  data={geom.data_start}"
          f"  cse={cse}  cluster={clust_sz//1024}KB  used={n_used}/{disk_clusters} clusters")
    print(f"  Folders ({len(folders)}): {folder_summary}")

    with open(output_path, 'wb') as f:
        f.write(bytes(sb)); f.write(bytes(pad1)); f.write(fat); f.write(root); f.write(dircon)
        for fi in file_infos:
            total = 0
            with open(fi['path'], 'rb') as src:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk); total += len(chunk)
            pad = (-total) % clust_sz
            if pad:
                f.write(b'\x00' * pad)
            print(f"  {fi['name']:16s}  start_cluster={fi['start_cluster']:5d}  "
                  f"clusters={fi['clusters']:4d}  ({fi['size']/1024/1024:.1f} MB)")
        # pad out to the full disk size — the remaining clusters are free space.
        f.truncate(disk_blocks * BSIZE)

    actual_mb = Path(output_path).stat().st_size / 1024 / 1024
    print(f"  Done: {output_path} ({actual_mb:.0f} MB, "
          f"{disk_clusters - n_used} free clusters)")


# ── Append banks to an existing EMU-fs hard-disk image ────────────────────────
# Read-modify-write of the EMU3 fs: parse the superblock geometry, find free
# clusters (FAT == 0) and free folder slots, write the new bank data into the
# free clusters, add dircon entries (spilling to a new dircon block via the
# folder's block_list[7] when needed), and bump the next-free pointer.  The
# superblock (block 0, incl. its checksum) is never touched — only the FAT,
# root, dircon and data regions change.  Targets disk-sized images with free
# space (build_emu_hdd output); a data-sized CD image has no room to append.

def _emu_resolve_duplicate(name: str, policy: str) -> str:
    """Resolve a name collision → 'add-new' / 'skip' / 'overwrite'."""
    if policy in ('add-new', 'skip', 'overwrite'):
        return policy
    while True:
        ans = input(f"  Bank '{name}' already exists — [a]dd as new / [s]kip / "
                    f"[o]verwrite? ").strip().lower()
        if ans in ('a', 'add', 'add-new'):  return 'add-new'
        if ans in ('s', 'skip', ''):        return 'skip'
        if ans in ('o', 'overwrite'):       return 'overwrite'


def emu_hdd_append(image: str, e4b_files: List[str], folder: str = None,
                   on_duplicate: str = 'prompt') -> int:
    """Add bank(s) to an existing EMU-fs hard-disk image without overwriting
    existing banks/folders.  `folder` targets (and creates if absent) a named
    folder; default = the system "Default Folder".  Returns the count added."""
    import os
    with open(image, 'r+b') as f:
        sb = f.read(BSIZE)
        if sb[:4] != EMU3_MAGIC:
            raise ValueError(f"{image}: not an EMU3 filesystem")
        g = lambda i: struct.unpack_from('<I', sb, i * 4)[0]
        root_start, root_blocks       = g(2), g(3)
        dircon_start, dircon_blocks   = g(4), g(5)
        fat_start, fat_blocks         = g(6), g(7)
        data_start, total_clusters    = g(8), g(9)
        cse      = sb[0x28]
        clust_sz = (1 << (15 + cse - BSIZE_BITS)) * BSIZE
        bpc      = clust_sz // BSIZE

        f.seek(0)
        meta = bytearray(f.read(data_start * BSIZE))        # whole metadata region

        fat_off = fat_start * BSIZE
        n_fat   = fat_blocks * (BSIZE // 2)
        fat     = list(struct.unpack_from('<%dH' % n_fat, meta, fat_off))
        next_free_dircon = struct.unpack_from('<H', meta, BSIZE)[0] or (dircon_start + 1)
        root_off = root_start * BSIZE
        root_entries = root_blocks * (BSIZE // 32)

        def parse_folders():
            out = []
            for i in range(root_entries):
                eo = root_off + i * 32
                nm = meta[eo:eo+16].rstrip(b' \x00')
                if not nm and meta[eo+17] == 0:
                    continue
                bl = [b for b in struct.unpack_from('<7h', meta, eo+18) if b != -1]
                out.append({'name': nm.decode('latin-1'), 'dtype': meta[eo+17],
                            'off': eo, 'blocks': bl})
            return out
        folders = parse_folders()

        # ── choose / create the target folder ────────────────────────────────
        if folder:
            tgt = next((fo for fo in folders
                        if fo['name'].strip().lower() == folder.strip().lower()), None)
            if tgt is None:
                free_root = next((root_off + i*32 for i in range(root_entries)
                                  if meta[root_off+i*32:root_off+i*32+16].rstrip(b' \x00') == b''
                                  and meta[root_off+i*32+17] == 0), None)
                if free_root is None:
                    raise ValueError("root directory is full — no room for a new folder")
                if next_free_dircon >= dircon_start + dircon_blocks:
                    raise ValueError("dircon area full — cannot allocate a folder block")
                newblk = next_free_dircon; next_free_dircon += 1
                meta[free_root:free_root+16] = folder.encode('ascii','replace')[:16].ljust(16,b' ')
                meta[free_root+16] = 0x00
                meta[free_root+17] = EMU3_DTYPE_1     # user folder
                struct.pack_into('<7h', meta, free_root+18, newblk, -1,-1,-1,-1,-1,-1)
                meta[newblk*BSIZE:newblk*BSIZE+BSIZE] = b'\x00' * BSIZE
                tgt = {'name': folder, 'dtype': EMU3_DTYPE_1, 'off': free_root,
                       'blocks': [newblk]}
                print(f"  + created folder '{folder}' (dircon block {newblk})")
        else:
            tgt = next((fo for fo in folders if fo['dtype'] == EMU3_DTYPE_DEFAULT),
                       folders[0] if folders else None)
            if tgt is None:
                raise ValueError("no folder found on the image")

        # ── existing banks + used slots in the target folder ─────────────────
        used_slots, existing = set(), {}
        for blk in tgt['blocks']:
            for e in range(EMU3_ENTRIES_PER_BLOCK):
                eo = blk * BSIZE + e * 32
                nm = meta[eo:eo+16].rstrip(b' \x00')
                if nm:
                    used_slots.add(meta[eo+17])
                    existing[nm.decode('latin-1')] = eo

        def find_free_entry():
            nonlocal next_free_dircon
            for blk in tgt['blocks']:
                for e in range(EMU3_ENTRIES_PER_BLOCK):
                    eo = blk * BSIZE + e * 32
                    if meta[eo:eo+16].rstrip(b' \x00') == b'':
                        return eo
            if len(tgt['blocks']) >= EMU3_BLOCKS_PER_DIR \
               or next_free_dircon >= dircon_start + dircon_blocks:
                return None
            newblk = next_free_dircon; next_free_dircon += 1
            tgt['blocks'].append(newblk)
            struct.pack_into('<7h', meta, tgt['off']+18,
                             *(tgt['blocks'] + [-1]*(EMU3_BLOCKS_PER_DIR - len(tgt['blocks']))))
            meta[newblk*BSIZE:newblk*BSIZE+BSIZE] = b'\x00' * BSIZE
            return newblk * BSIZE

        added, pending = 0, []
        for path in e4b_files:
            name = _emu_bank_name(path)
            size = os.path.getsize(path)
            if name in existing:
                act = _emu_resolve_duplicate(name, on_duplicate)
                if act == 'skip':
                    print(f"  skip '{name}' (already present)"); continue
                if act == 'overwrite':
                    eo = existing.pop(name)
                    c = struct.unpack_from('<H', meta, eo+18)[0]
                    while c and c != EMU3_LAST_CLUSTER and c < len(fat):
                        c, fat[c] = fat[c], 0
                    used_slots.discard(meta[eo+17])
                    meta[eo:eo+32] = b'\x00' * 32
            need = max(1, (size + clust_sz - 1) // clust_sz)
            free = [c for c in range(1, total_clusters + 1)
                    if c < len(fat) and fat[c] == 0][:need]
            if len(free) < need:
                raise ValueError(f"not enough free clusters for '{name}' "
                                 f"(need {need}, free {len(free)})")
            for j, c in enumerate(free):
                fat[c] = free[j+1] if j < need - 1 else EMU3_LAST_CLUSTER
            slot = next((s for s in range(EMU3_BANKS_PER_FOLDER) if s not in used_slots), None)
            eo = find_free_entry()
            if slot is None or eo is None:
                raise ValueError(f"folder '{tgt['name']}' is full "
                                 f"({EMU3_BANKS_PER_FOLDER} banks max)")
            used_slots.add(slot)
            n_c, blks, brem = _alloc(size, clust_sz)
            meta[eo:eo+16] = name.encode('ascii','replace')[:16].ljust(16,b' ')
            meta[eo+16] = 0x00
            meta[eo+17] = slot & 0xFF
            struct.pack_into('<H', meta, eo+18, free[0])
            struct.pack_into('<H', meta, eo+20, n_c)
            struct.pack_into('<H', meta, eo+22, blks)
            struct.pack_into('<H', meta, eo+24, brem)
            meta[eo+26] = EMU3_FTYPE_STD
            meta[eo+27:eo+32] = b'\x00E4B0'
            existing[name] = eo
            pending.append((free, path))
            added += 1
            print(f"  + {name}  folder='{tgt['name']}'  slot={slot}  "
                  f"start_cluster={free[0]}  clusters={need}")

        # write back metadata (FAT + next-free pointer included), then bank data
        struct.pack_into('<%dH' % n_fat, meta, fat_off, *[v & 0xFFFF for v in fat])
        struct.pack_into('<H', meta, BSIZE, next_free_dircon & 0xFFFF)
        f.seek(0); f.write(meta)
        for clusters, path in pending:
            with open(path, 'rb') as src:
                for c in clusters:
                    chunk = src.read(clust_sz)
                    f.seek((data_start + (c-1)*bpc) * BSIZE)
                    f.write(chunk)
                    if len(chunk) < clust_sz:
                        f.write(b'\x00' * (clust_sz - len(chunk)))
    print(f"  Appended {added} bank(s) to {image}")
    return added
