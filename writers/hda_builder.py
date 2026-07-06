# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
#
# This file is part of mpc2emu.
# EMU4 filesystem structure informed by emu3fs:
#   Copyright (C) 2014-2024  David García Goñi and contributors
#   https://github.com/dagargo/emu3fs  —  GPL-2.0-or-later
# No source code was copied; this is an independent Python implementation
# of the documented on-disk structures.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# mpc2emu is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
SCSI Hard Disk Image Builder (.hda) for ZuluSCSI
--------------------------------------------------
Produces a raw sector image that ZuluSCSI presents to the E4XT as a
SCSI hard disk drive.  The image contains a minimal EMU4 filesystem
skeleton so the E4XT OS recognises the volume immediately.

EMU4 filesystem overview
------------------------
The E-mu EIV series (E4XT, E4K, ESI-4000, …) uses a proprietary
block-based filesystem with 512-byte sectors.  The on-disk layout is:

  Sector 0:         EMU4 volume descriptor / superblock
  Sector 1:         Root directory block (EIV) or first-bank block (EIII)
  Sectors 2…N:      Directory and file data blocks
  Remaining space:  Free blocks (zeroed)

Key superblock fields (all little-endian 16/32-bit):
  Offset  Size  Description
   0       4    Magic: 0x454D5533  ("EMU3")  — same magic for both EIII and EIV
   4       2    Version: 0x0100 = EIV
   6       2    Block size: 0x0200 = 512 bytes
   8       4    Total blocks on device
  12       4    First free block index
  16       2    Root directory block index (EIV: 1)
  18       2    Number of root entries
  20      12    Volume name (null-padded, ASCII)
  32     480    Reserved / zeroed

Directory entry (32 bytes each, packed in directory blocks):
  Offset  Size  Description
   0       2    Entry type: 0x0000=empty, 0x0001=bank-file, 0x0002=subdirectory
   2       2    Flags
   4       4    First block of file data
   8       4    File size in bytes
  12       2    Modification date (DOS date format)
  14       2    Modification time (DOS time format)
  16      16    Filename (null-padded, uppercase ASCII, max 15 chars + null)

This implementation writes a valid superblock and an empty root
directory.  E4B files are NOT embedded directly; instead the image
is sized and structured so that emu3fs can mount it and the user
(or a subsequent tool invocation) can copy E4B files into the
mounted filesystem.

References:
  - emu3fs kernel module source (GPL-2.0-or-later),
    David García Goñi, https://github.com/dagargo/emu3fs
  - E-mu EOS 4.x service documentation (community-sourced)
  - SCSI2SD / ZuluSCSI documentation: https://www.zuluscs i.net/

IMPORTANT — DISCLAIMER
----------------------
The EMU4 filesystem format is proprietary and was never officially
documented by E-mu Systems / Creative Technology Ltd.  This
implementation is based on community reverse-engineering and the
emu3fs open-source kernel module.  The resulting .hda image should
always be tested on a ZuluSCSI / SCSI2SD device before use in
production.  The authors accept no responsibility for data loss or
hardware damage.
"""

import struct
import time
from pathlib import Path
from typing import List, Optional


# ── Constants ─────────────────────────────────────────────────────────────────

SECTOR_SIZE      = 512
EMU3_MAGIC       = 0x454D5533   # "EMU3" — used by both EIII and EIV
EIV_VERSION      = 0x0100
EIII_VERSION     = 0x0000

ENTRY_EMPTY      = 0x0000
ENTRY_BANK       = 0x0001
ENTRY_SUBDIR     = 0x0002

SUPERBLOCK_SEC   = 0            # Sector index of superblock
ROOT_DIR_SEC     = 1            # Sector index of root directory (EIV)
FIRST_DATA_SEC   = 2            # First sector available for file data

ENTRIES_PER_BLOCK = SECTOR_SIZE // 32  # 16 directory entries per sector

# Maximum volume size the ESI/EIV OS supports (14 GiB in sectors)
MAX_SECTORS      = (14 * 1024 * 1024 * 1024) // SECTOR_SIZE


# ── DOS date/time helpers ─────────────────────────────────────────────────────

def _dos_datetime(t: Optional[time.struct_time] = None):
    """Return (dos_date, dos_time) for the given time (default: now)."""
    if t is None:
        t = time.localtime()
    dos_date = ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    dos_time = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    return dos_date & 0xFFFF, dos_time & 0xFFFF


# ── Block builders ────────────────────────────────────────────────────────────

def _build_superblock(total_sectors: int, volume_name: str,
                      eiv: bool = True) -> bytes:
    """
    Build the 512-byte EMU4 superblock (sector 0).

    total_sectors: total number of 512-byte sectors in the image
    volume_name:   up to 12 ASCII characters, will be uppercased
    eiv:           True = EIV layout (supports root directory);
                   False = EIII layout (only first-bank access)
    """
    version    = EIV_VERSION if eiv else EIII_VERSION
    name_bytes = volume_name.upper().encode('ascii', errors='replace')[:12]
    name_bytes = name_bytes.ljust(12, b'\x00')

    # Pack fixed fields (32 bytes)
    header = struct.pack(
        '<IHHIIHH12s',
        EMU3_MAGIC,          # 0   magic
        version,             # 4   version
        SECTOR_SIZE,         # 6   block size
        total_sectors,       # 8   total blocks
        FIRST_DATA_SEC,      # 12  first free block
        ROOT_DIR_SEC,        # 16  root dir block (EIV)
        0,                   # 18  number of root entries (0 = empty)
        name_bytes,          # 20  volume name
    )
    assert len(header) == 32
    return header + b'\x00' * (SECTOR_SIZE - 32)


def _build_empty_dir_block() -> bytes:
    """Build a 512-byte directory block with all entries marked empty."""
    entry = struct.pack('<HHIIHHs16x', ENTRY_EMPTY, 0, 0, 0, 0, 0, b'\x00')
    # Each entry is 32 bytes; 16 entries per sector
    entry = b'\x00' * 32          # simpler: just zero the whole block
    return entry * ENTRIES_PER_BLOCK   # 16 × 32 = 512


def _dir_entry(name: str, first_block: int, file_size: int,
               entry_type: int = ENTRY_BANK) -> bytes:
    """Build a single 32-byte directory entry for a bank file."""
    name_bytes = name.upper().encode('ascii', errors='replace')[:15]
    name_bytes = name_bytes.ljust(16, b'\x00')
    dos_date, dos_time = _dos_datetime()
    return struct.pack(
        '<HHIIHH16s',
        entry_type,    # 0   type
        0,             # 2   flags
        first_block,   # 4   first data block
        file_size,     # 8   file size bytes
        dos_date,      # 12  date
        dos_time,      # 14  time
        name_bytes,    # 16  name
    )


# ── Main builder ──────────────────────────────────────────────────────────────

def build_hda(
    output_path: str,
    size_mb: int = 100,
    volume_name: str = "EMU_BANK",
    e4b_files: Optional[List[str]] = None,
    eiv: bool = True,
) -> None:
    """
    Build a raw SCSI hard disk image (.hda) for ZuluSCSI.

    The image contains:
      - A valid EMU4 superblock
      - An empty root directory block
      - All provided E4B files embedded as consecutive data blocks
      - Remaining space zeroed (free blocks)

    After creation the image can alternatively be mounted with emu3fs
    (see printed instructions) to add or manage files via the Linux
    filesystem interface.

    Args:
        output_path:  Path for the output .hda file
        size_mb:      Total image size in MB (default 100, max 14336)
        volume_name:  EMU4 volume label (max 12 chars, uppercased)
        e4b_files:    Optional list of E4B file paths to embed
        eiv:          True = EIV layout (E4XT/E4K), False = EIII

    Raises:
        ValueError: if size_mb exceeds the EIV OS limit of 14 GB
    """
    if size_mb > 14 * 1024:
        raise ValueError(
            f"size_mb={size_mb} exceeds the EIV OS limit of 14336 MB (14 GiB).")

    total_sectors = (size_mb * 1024 * 1024) // SECTOR_SIZE
    e4b_files     = e4b_files or []

    print(f"\nBuilding HDA image: {output_path}")
    print(f"  Volume name:   {volume_name.upper()}")
    print(f"  Image size:    {size_mb} MB  ({total_sectors} sectors)")
    print(f"  Filesystem:    {'EIV' if eiv else 'EIII'}")
    print(f"  E4B files:     {len(e4b_files)}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Validate E4B files and compute layout
    entries: List[dict] = []
    current_sector = FIRST_DATA_SEC

    for e4b_path in e4b_files:
        p = Path(e4b_path)
        if not p.exists():
            print(f"  [WARN] E4B not found, skipping: {p}")
            continue
        size = p.stat().st_size
        n_sectors = (size + SECTOR_SIZE - 1) // SECTOR_SIZE
        if current_sector + n_sectors > total_sectors:
            print(f"  [WARN] Not enough space for '{p.name}' "
                  f"({size / 1024 / 1024:.1f} MB), skipping")
            continue
        entries.append({
            'path':         str(p),
            'name':         p.stem[:15],
            'size':         size,
            'first_sector': current_sector,
            'n_sectors':    n_sectors,
        })
        current_sector += n_sectors
        print(f"  Embed: {p.name}  ({size / 1024 / 1024:.2f} MB, "
              f"sectors {entries[-1]['first_sector']}–"
              f"{current_sector - 1})")

    # The EMU4 root directory is a single 512-byte block: at most
    # ENTRIES_PER_BLOCK (16) entries of 32 bytes each.  Files beyond that would
    # be written to disk but have no directory entry, so the E4XT cannot see
    # them — silent data loss.  Warn and drop the excess instead of writing
    # dead sectors.  (Multi-block directory chaining is a future enhancement.)
    if len(entries) > ENTRIES_PER_BLOCK:
        dropped = entries[ENTRIES_PER_BLOCK:]
        print(f"  [ERROR] HDA directory holds at most {ENTRIES_PER_BLOCK} files; "
              f"{len(entries)} provided.  Dropping {len(dropped)} excess file(s):")
        for e in dropped:
            print(f"            {Path(e['path']).name}")
        print(f"          Split the banks across multiple HDA images "
              f"(≤{ENTRIES_PER_BLOCK} each).")
        entries = entries[:ENTRIES_PER_BLOCK]

    # Build directory block with entries
    dir_block = bytearray(SECTOR_SIZE)
    for i, e in enumerate(entries[:ENTRIES_PER_BLOCK]):
        entry_bytes = _dir_entry(e['name'], e['first_sector'], e['size'])
        dir_block[i * 32 : i * 32 + 32] = entry_bytes

    # Update superblock with actual entry count
    superblock = bytearray(_build_superblock(total_sectors, volume_name, eiv))
    struct.pack_into('<H', superblock, 18, len(entries))

    # Write image
    with open(str(out), 'wb') as f:
        # Sector 0: superblock
        f.write(bytes(superblock))
        # Sector 1: root directory
        f.write(bytes(dir_block))
        # Sectors 2…: E4B file data.  CR-16: copy in 1 MB chunks and pad
        # separately — was reading each whole file into RAM and then building a
        # second padded copy of it.
        for e in entries:
            total = 0
            with open(e['path'], 'rb') as src:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
            pad = (-total) % SECTOR_SIZE
            if pad:
                f.write(b'\x00' * pad)
        # Fill remaining space with zeros
        written_sectors = FIRST_DATA_SEC + sum(e['n_sectors'] for e in entries)
        remaining = total_sectors - written_sectors
        if remaining > 0:
            # Write in 1 MB chunks to avoid huge memory allocation
            chunk = b'\x00' * min(2048, remaining) * SECTOR_SIZE
            full_chunks, leftover = divmod(remaining, min(2048, remaining))
            # Simpler: write sector by sector in 512-KB batches
            BATCH = 1024  # sectors per write
            remaining_to_write = remaining
            while remaining_to_write > 0:
                n = min(BATCH, remaining_to_write)
                f.write(b'\x00' * (n * SECTOR_SIZE))
                remaining_to_write -= n

    actual_size = out.stat().st_size
    print(f"  Written: {out}  ({actual_size / 1024 / 1024:.1f} MB)")
    _print_zuluscs_instructions(out, entries)


def _print_zuluscs_instructions(out: Path, entries: List[dict]) -> None:
    """Print ZuluSCSI usage instructions and emu3fs workflow."""
    n = len(entries)
    print()
    print("─" * 60)
    print("  ZuluSCSI — SCSI Hard Disk (.hda) Usage")
    print("─" * 60)
    print()
    print("  1. Copy the image to the ZuluSCSI SD card:")
    print(f"       cp {out.name} <SD_CARD>/HD10_512.hda")
    print()
    print("     Naming convention: HD<ID>_<BLOCK_SIZE>.hda")
    print("     Example: HD10_512.hda  →  SCSI ID 0, 512-byte blocks")
    print("     Use HD20_512.hda for SCSI ID 1, etc.")
    print()
    print("  2. Power on E4XT.  The drive appears in:")
    print("       Load  →  Hard Disk  →  (select bank)")
    print()
    if n > 0:
        print(f"  {n} E4B file(s) are already embedded at the correct")
        print("  sector offsets and will be immediately accessible.")
    else:
        print("  The image contains an empty EMU4 filesystem.")
        print("  Use emu3fs (see below) to copy E4B files into it.")
    print()
    print("─" * 60)
    print("  emu3fs — Adding files after creation (Linux only)")
    print("─" * 60)
    print()
    print("  Requirements: Linux kernel module emu3fs")
    print("    https://github.com/dagargo/emu3fs")
    print()
    print("  Mount the image:")
    print(f"    sudo losetup /dev/loop0 {out.name}")
    print("    mkdir -p /mnt/emu4")
    print("    sudo mount -t emu4 /dev/loop0 /mnt/emu4")
    print()
    print("  Copy E4B files:")
    print("    sudo cp MyBank.E4B /mnt/emu4/")
    print()
    print("  Unmount:")
    print("    sudo umount /mnt/emu4")
    print("    sudo losetup -d /dev/loop0")
    print()
    print("  NOTE: emu3fs uses 512-byte block size.  If your loop device")
    print("  defaults to 4096-byte blocks, add: losetup -b 512 /dev/loop0")
    print("─" * 60)
    print()


# ── FAT-formatted .hda (EOS 4.7+, which has FAT support) ──────────────────────
# Reproduces the exact on-disk layout EOS 4.7 produces when it formats a SCSI
# disk as FAT (reverse-engineered from a drive formatted by the E4XT itself —
# see docs/re_procedures/emu_hdd_fs.md): MBR partition at LBA 63 (type 0x06),
# FAT16, 32 KB clusters, 32 reserved sectors, 2 FATs, 512 root entries, OEM
# "E-MU SYS", banks B.NNN-NAME.E4B (VFAT long names) in the root.  Built with the
# pure-Python writers/fat16.py — no external tools (works on Windows too).

def build_hda_fat(output_path: str, size_mb: int, volume_name: str,
                  e4b_files: List[str]) -> None:
    """Build a FAT ZuluSCSI hard-disk image in EOS's native layout.  EOS picks
    the FAT type by capacity (4.7 addendum p.3): **FAT16 ≤~1 GB, FAT32 above** —
    so this writes FAT16 at ≤1 GB and FAT32 above."""
    fat32 = size_mb > 1024
    from writers.fat32 import format_new as _fmt32
    from writers.fat16 import format_new as _fmt16
    format_new = _fmt32 if fat32 else _fmt16
    fstype = 'FAT32' if fat32 else 'FAT16'

    out = Path(output_path)
    label = (volume_name or 'MPC2EMU').upper().replace(' ', '')[:11]
    total_bytes = sum(Path(f).stat().st_size for f in e4b_files)
    if not fat32 and size_mb < 512:
        print(f"  [WARN] --hda-size {size_mb} MB is small; EOS's FAT16/32 KB-cluster "
              f"layout needs >=512 MB to land in the FAT16 range.")
    if total_bytes > 0.95 * size_mb * 1024 * 1024:
        print(f"  [WARN] bank files ({total_bytes/1024/1024:.0f} MB) nearly fill "
              f"the {size_mb} MB image — consider a larger --hda-size")

    print(f"\n[HDA] Building {fstype} ZuluSCSI disk image, EOS native layout "
          f"({size_mb} MB, label {label})...")
    if out.exists():
        out.unlink()

    fs = format_new(str(out), size_mb, label)
    try:
        for i, f in enumerate(e4b_files):
            src = Path(f).name
            dest = src if (src[:2] == 'B.' and '-' in src) else f"B.{i:03d}-{Path(f).stem}.E4B"
            fs.add_file(str(f), dest)
            print(f"  + {dest}")
    finally:
        fs.close()
    print(f"  Written: {out}  ({out.stat().st_size/1024/1024:.0f} MB, {fstype}, MBR @ LBA 63)")
    print(f"  → copy to the ZuluSCSI SD card as HD<ID>_512.hda (e.g. HD10_512.hda)")


# ── EMU-fs (EMU3) .hda — proper hard-disk image via iso_builder.build_emu_hdd ─
# Uses the hard-disk EMU3 geometry profile RE'd from E4XT-formatted references
# (docs/re_procedures/emu_hdd_fs.md): a real disk-sized image (full --hda-size)
# with the banks in a "Default Folder" and the remaining clusters FREE, so EOS
# can save onto it.  Read by all EOS versions (the only path for EOS <=4.62,
# which has no FAT).  Cluster size scales with the disk (cse 4/5/6/7 for
# 512 MB/1/2/4 GB), keeping the count within the 1023-cluster (4-FAT-block) cap.

def build_hda_emu(output_path: str, volume_name: str,
                  e4b_files: List[str], size_mb: int = 1024) -> None:
    """Build a properly-sized EMU-fs (EMU3) ZuluSCSI hard-disk image."""
    from writers.iso_builder import build_emu_hdd
    print(f"\n[HDA] Building EMU-fs (EMU3) hard-disk image ({size_mb} MB)...")
    build_emu_hdd(e4b_files, output_path, volume_name, size_mb)
    print(f"  → copy to the ZuluSCSI SD card as HD<ID>_512.hda (e.g. HD20_512.hda)")


# ── Detect the filesystem of an existing .hda, and append banks to it ──────────

def detect_hda_fs(image: str) -> str:
    """Return 'emu' or 'fat' for an existing .hda image (raises if neither)."""
    with open(image, 'rb') as f:
        s0 = f.read(512)
    if s0[:4] == b'EMU3':
        return 'emu'
    if s0[510:512] == b'\x55\xAA':
        for i in range(4):
            ptype = s0[0x1BE + i * 16 + 4]
            if ptype in (0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E):
                return 'fat'
    if b'FAT1' in s0[0x36:0x3F] or b'FAT32' in s0[0x52:0x5B]:
        return 'fat'          # partitionless FAT (superfloppy)
    raise ValueError(f"{image}: unrecognized filesystem (neither EMU3 nor FAT)")


def _resolve_duplicate(name: str, policy: str) -> str:
    """Resolve a name collision → 'add-new' / 'skip' / 'overwrite'."""
    if policy in ('add-new', 'skip', 'overwrite'):
        return policy
    while True:
        ans = input(f"  Bank '{name}' already exists — [a]dd as new / [s]kip / "
                    f"[o]verwrite? ").strip().lower()
        if ans in ('a', 'add', 'add-new'):  return 'add-new'
        if ans in ('s', 'skip', ''):        return 'skip'
        if ans in ('o', 'overwrite'):       return 'overwrite'


def fat_hda_append(image: str, e4b_files: List[str], folder: str = None,
                   on_duplicate: str = 'prompt') -> int:
    """Add bank(s) to an existing FAT .hda without overwriting existing banks.
    `folder` targets (and creates if absent) a sub-folder; banks are named
    B.NNN-NAME.E4B with the next free 3-digit number.  Returns the count added.
    Pure Python (writers/fat16.py + fat32.py) — no external tools."""
    import re
    import struct as _st
    from writers.fat16 import Fat16
    from writers.fat32 import Fat32

    # detect FAT16 vs FAT32 from the partition boot sector's fs-type string
    with open(image, 'rb') as _f:
        _s0 = _f.read(512)
        _lba = next((_st.unpack_from('<I', _s0, 0x1BE + i * 16 + 8)[0]
                     for i in range(4)
                     if _s0[0x1BE + i * 16 + 4] in (0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E)
                     and _st.unpack_from('<I', _s0, 0x1BE + i * 16 + 8)[0]), 0)
        _f.seek(_lba * 512); _bs = _f.read(512)
    fs = Fat32(image) if _bs[82:87] == b'FAT32' else Fat16(image)
    try:
        target = None
        if folder:
            target = fs.find_dir(folder)
            if target is None:
                target = fs.makedir(folder)
                print(f"  + created folder '{folder}'")

        existing = [n for n in fs.list_dir(target) if n.upper().endswith('.E4B')]
        existing_stems = {re.sub(r'^B\.\d+-', '', n[:-4]) for n in existing}
        used_nums = {int(m.group(1)) for n in existing
                     if (m := re.match(r'B\.(\d+)-', n))}

        def next_num():
            n = 0
            while n in used_nums:
                n += 1
            used_nums.add(n)
            return n

        added = 0
        for path in e4b_files:
            stem = re.sub(r'^B\.\d+-', '', Path(path).stem)
            if stem in existing_stems:
                act = _resolve_duplicate(stem, on_duplicate)
                if act == 'skip':
                    print(f"  skip '{stem}' (already present)")
                    continue
                if act == 'overwrite':
                    for n in [x for x in existing
                              if re.sub(r'^B\.\d+-', '', x[:-4]) == stem]:
                        fs.delete_file(n, target)
                        existing.remove(n)
            dest = f"B.{next_num():03d}-{stem}.E4B"
            fs.add_file(str(path), dest, target)
            existing.append(dest)
            existing_stems.add(stem)
            added += 1
            print(f"  + {dest}  (folder '{folder or 'root'}')")
    finally:
        fs.close()
    print(f"  Appended {added} bank(s) to {image}")
    return added


# ── Minimal image sizing ──────────────────────────────────────────────────────
# Copying a .hda to the ZuluSCSI SD over USB is slow and copies empty space too,
# so size images to the smallest 128 MB step that actually holds the banks.

def auto_hda_size_mb(e4b_files: List[str], fs: str = 'emu', step_mb: int = 128) -> int:
    """Smallest `step_mb`-multiple size (MB) that fits the banks for the given fs.

    EMU-fs floor 128 MB; FAT16 floor 256 MB (keeps it safely in the FAT16
    cluster range).  Returns a size, never raises."""
    import os
    sizes = [os.path.getsize(f) for f in e4b_files] or [0]
    floor = 128 if fs == 'emu' else 256
    mb = max(step_mb, floor)
    while mb < 64 * 1024:                       # hard ceiling well above any disk
        cap = mb * 1024 * 1024
        if fs == 'emu':
            blk = cap // SECTOR_SIZE
            cse = 4
            while (blk - 182) // (1 << (15 + cse - 9)) > 1023:
                cse += 1
            clust = 1 << (15 + cse)
            disk_clusters = min((blk - 182) // (clust // SECTOR_SIZE), 1023)
            need = sum((s + clust - 1) // clust for s in sizes)
            if need <= disk_clusters:
                return mb
        else:                                   # FAT16, 32 KB clusters
            clust = 32 * 1024
            need = sum((s + clust - 1) // clust for s in sizes)
            if need * clust <= cap * 0.95:
                return mb
        mb += step_mb
    return mb
