# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
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
Pure-Python FAT16 reader/writer for EOS-native ZuluSCSI hard-disk images.

Replaces the external `mtools` dependency so the FAT `.hda` path runs anywhere
(Windows included) with no extra tools.  Produces the exact on-disk layout an
E4XT (EOS 4.7) formats — reverse-engineered in docs/re_procedures/emu_hdd_fs.md:

  * MBR partition table, partition 1 at LBA 63, type 0x06 (FAT16)
  * FAT16, 32 KB clusters (64 sectors/cluster), 32 reserved sectors, 2 FATs,
    512 root entries, OEM string "E-MU SYS"
  * VFAT long filenames for the B.NNN-NAME.E4B banks (+ 8.3 short aliases)

Scope: just what the converter needs — format a new image, open an existing one,
make a sub-folder, add a file with a long name, and list a directory.  Supports
the fixed root directory and single-cluster sub-directories (ample for the
EOS 100-banks-per-folder limit: a 32 KB cluster holds 1024 dir entries).
"""

import os
import struct
from pathlib import Path
from typing import List, Optional

SECTOR = 512
_ATTR_VOLUME = 0x08
_ATTR_DIR    = 0x10
_ATTR_LFN    = 0x0F
_FREE        = 0x00
_DELETED     = 0xE5
# Characters allowed unescaped in an 8.3 short name
_SFN_OK = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'()-@^_`{}~")


def _chs(lba: int, heads: int = 255, spt: int = 63) -> bytes:
    cyl = lba // (heads * spt)
    head = (lba // spt) % heads
    sec = lba % spt + 1
    if cyl > 1023:
        cyl, head, sec = 1023, 254, 63
    return bytes([head & 0xFF, (sec & 0x3F) | ((cyl >> 2) & 0xC0), cyl & 0xFF])


def _lfn_checksum(short11: bytes) -> int:
    s = 0
    for c in short11:
        s = (((s & 1) << 7) + (s >> 1) + c) & 0xFF
    return s


class Fat16:
    """A FAT16 filesystem inside a (partitioned) disk image, opened read/write."""

    # ── construction ─────────────────────────────────────────────────────────
    def __init__(self, path: str):
        self.path = str(path)
        self.f = open(self.path, 'r+b')
        self._read_bpb()

    def close(self):
        if self.f:
            self.f.flush()
            self.f.close()
            self.f = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _part_offset(self) -> int:
        self.f.seek(0)
        s0 = self.f.read(SECTOR)
        if s0[510:512] == b'\x55\xAA':
            for i in range(4):
                e = s0[0x1BE + i * 16:0x1BE + i * 16 + 16]
                if e[4] in (0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E):
                    lba = struct.unpack_from('<I', e, 8)[0]
                    if lba:
                        return lba * SECTOR
        return 0

    def _read_bpb(self):
        self.part_off = self._part_offset()
        self.f.seek(self.part_off)
        b = self.f.read(SECTOR)
        self.bps   = struct.unpack_from('<H', b, 11)[0]
        self.spc   = b[13]
        self.rsvd  = struct.unpack_from('<H', b, 14)[0]
        self.nfats = b[16]
        self.root_ents = struct.unpack_from('<H', b, 17)[0]
        self.fatsz = struct.unpack_from('<H', b, 22)[0]
        self.cluster_bytes = self.bps * self.spc
        self.root_sectors = (self.root_ents * 32 + self.bps - 1) // self.bps
        self.fat_start  = self.rsvd
        self.root_start = self.rsvd + self.nfats * self.fatsz
        self.data_start = self.root_start + self.root_sectors      # sector of cluster 2
        total = struct.unpack_from('<I', b, 32)[0] or struct.unpack_from('<H', b, 19)[0]
        self.n_clusters = (total - self.data_start) // self.spc
        # load FAT #1 into memory (list of u16)
        self.f.seek(self.part_off + self.fat_start * SECTOR)
        raw = self.f.read(self.fatsz * SECTOR)
        self.fat = list(struct.unpack_from('<%dH' % (len(raw) // 2), raw))

    def _abs(self, sector: int) -> int:
        return self.part_off + sector * SECTOR

    def _cluster_offset(self, cluster: int) -> int:
        return self._abs(self.data_start + (cluster - 2) * self.spc)

    # ── FAT cluster allocation ───────────────────────────────────────────────
    def _alloc_chain(self, n: int) -> List[int]:
        free = [c for c in range(2, self.n_clusters + 2) if self.fat[c] == 0][:n]
        if len(free) < n:
            raise ValueError(f"FAT image full: need {n} clusters, {len(free)} free")
        for j, c in enumerate(free):
            self.fat[c] = free[j + 1] if j < n - 1 else 0xFFFF
        return free

    def _flush_fat(self):
        raw = struct.pack('<%dH' % len(self.fat), *[v & 0xFFFF for v in self.fat])
        for i in range(self.nfats):
            self.f.seek(self.part_off + (self.fat_start + i * self.fatsz) * SECTOR)
            self.f.write(raw[:self.fatsz * SECTOR])

    # ── directory access (root = fixed area; sub-dir = one cluster) ───────────
    def _read_dir(self, folder_cluster: Optional[int]):
        """Return (bytearray, writeback_fn) for the root (None) or a sub-dir."""
        if folder_cluster is None:
            self.f.seek(self._abs(self.root_start))
            data = bytearray(self.f.read(self.root_sectors * SECTOR))

            def wb(d):
                self.f.seek(self._abs(self.root_start)); self.f.write(d)
            return data, wb
        off = self._cluster_offset(folder_cluster)
        self.f.seek(off)
        data = bytearray(self.f.read(self.cluster_bytes))

        def wb(d):
            self.f.seek(off); self.f.write(d)
        return data, wb

    @staticmethod
    def _iter_entries(data: bytearray):
        """Yield (offset, longname, attr, cluster, size) for real entries."""
        lfn = []
        for o in range(0, len(data), 32):
            first = data[o]
            if first == _FREE:
                break
            if first == _DELETED:
                lfn = []
                continue
            attr = data[o + 11]
            if attr == _ATTR_LFN:
                seq = first & 0x1F
                chars = (data[o+1:o+11] + data[o+14:o+26] + data[o+28:o+32])
                lfn.append((seq, chars))
                continue
            if attr & _ATTR_VOLUME and not (attr & _ATTR_DIR):
                lfn = []
                continue
            # assemble long name from collected LFN parts
            name = ''
            if lfn:
                for _seq, chars in sorted(lfn):
                    name += chars.decode('utf-16-le', 'ignore')
                name = name.split('\x00', 1)[0].rstrip('￿')
            if not name:
                base = data[o:o+8].decode('latin-1').rstrip()
                ext = data[o+8:o+11].decode('latin-1').rstrip()
                name = base + ('.' + ext if ext else '')
            cl = struct.unpack_from('<H', data, o + 26)[0]
            sz = struct.unpack_from('<I', data, o + 28)[0]
            yield o, name, attr, cl, sz
            lfn = []

    def list_dir(self, folder_cluster: Optional[int]) -> List[str]:
        data, _ = self._read_dir(folder_cluster)
        return [name for _o, name, attr, _c, _s in self._iter_entries(data)
                if not (attr & _ATTR_DIR)]

    def _used_shortnames(self, data: bytearray) -> set:
        out = set()
        for o in range(0, len(data), 32):
            first = data[o]
            if first == _FREE:
                break
            if first == _DELETED or data[o + 11] == _ATTR_LFN:
                continue
            out.add(bytes(data[o:o + 11]))
        return out

    def find_dir(self, name: str) -> Optional[int]:
        """Return a sub-folder's start cluster (root-level only), or None."""
        data, _ = self._read_dir(None)
        for _o, nm, attr, cl, _s in self._iter_entries(data):
            if (attr & _ATTR_DIR) and nm.strip().lower() == name.strip().lower():
                return cl
        return None

    # ── short-name (8.3) generation + entry building ─────────────────────────
    @staticmethod
    def _try_83(name: str) -> Optional[bytes]:
        """If `name` is already a valid uppercase 8.3 name, return its 11-byte
        padded form (so we can write a clean short entry with NO VFAT long-name
        entries — the K2000 reads 8.3 short names, so long names would show as
        mangled ``NAME~1`` aliases).  Otherwise return None."""
        stem, _, ext = name.rpartition('.')
        if not stem:
            stem, ext = ext, ''
        if len(stem) > 8 or len(ext) > 3 or not stem:
            return None
        s = stem.upper().encode('latin-1', 'replace')
        e = ext.upper().encode('latin-1', 'replace')
        if any(c not in _SFN_OK for c in s) or any(c not in _SFN_OK for c in e):
            return None
        return s.ljust(8, b' ') + e.ljust(3, b' ')

    @staticmethod
    def _short_name(longname: str, used: set) -> bytes:
        stem, _, ext = longname.rpartition('.')
        if not stem:
            stem, ext = ext, ''
        def clean(s):
            return bytes(c if c in _SFN_OK else ord('_')
                         for c in s.upper().replace('.', '').encode('latin-1', 'replace'))
        cbase = clean(stem) or b'BANK'
        cext = clean(ext)[:3]
        for n in range(1, 1000):
            suffix = b'~' + str(n).encode()
            base = (cbase[:8 - len(suffix)] + suffix)
            short = base.ljust(8, b' ') + cext.ljust(3, b' ')
            if short not in used:
                return short
        raise ValueError("could not generate a unique 8.3 name")

    @staticmethod
    def _lfn_entries(longname: str, short11: bytes) -> List[bytes]:
        cks = _lfn_checksum(short11)
        u = longname.encode('utf-16-le')
        chars = list(u) + [0x00, 0x00]          # NUL terminator
        # pad to a multiple of 26 bytes (13 UTF-16 chars) with 0xFF
        while len(chars) % 26:
            chars.append(0xFF)
        parts = [bytes(chars[i:i + 26]) for i in range(0, len(chars), 26)]
        out = []
        n = len(parts)
        for idx, p in enumerate(parts):
            seq = idx + 1
            if idx == n - 1:
                seq |= 0x40
            e = bytearray(32)
            e[0] = seq
            e[1:11]  = p[0:10]
            e[11] = _ATTR_LFN
            e[12] = 0
            e[13] = cks
            e[14:26] = p[10:22]
            e[26:28] = b'\x00\x00'
            e[28:32] = p[22:26]
            out.append(bytes(e))
        return out[::-1]            # entries stored highest-seq first

    @staticmethod
    def _short_entry(short11: bytes, attr: int, cluster: int, size: int) -> bytes:
        e = bytearray(32)
        e[0:11] = short11
        e[11] = attr
        struct.pack_into('<H', e, 26, cluster & 0xFFFF)
        struct.pack_into('<I', e, 28, size)
        return bytes(e)

    @staticmethod
    def _find_free_run(data: bytearray, count: int) -> Optional[int]:
        run = 0
        start = None
        for o in range(0, len(data), 32):
            if data[o] in (_FREE, _DELETED):
                if run == 0:
                    start = o
                run += 1
                if run >= count:
                    return start
            else:
                run = 0
                start = None
        return None

    # ── public mutators ──────────────────────────────────────────────────────
    def makedir(self, name: str) -> int:
        """Create a root-level sub-folder, returning its start cluster."""
        existing = self.find_dir(name)
        if existing is not None:
            return existing
        cl = self._alloc_chain(1)[0]
        # initialise the directory cluster with "." and ".." then zeros
        block = bytearray(self.cluster_bytes)
        block[0:32]  = self._short_entry(b'.          ', _ATTR_DIR, cl, 0)
        block[32:64] = self._short_entry(b'..         ', _ATTR_DIR, 0, 0)
        self.f.seek(self._cluster_offset(cl)); self.f.write(block)
        # add the folder entry to the root
        data, wb = self._read_dir(None)
        used = self._used_shortnames(data)
        short83 = self._try_83(name)
        if short83 is not None and short83 not in used:
            entries = [self._short_entry(short83, _ATTR_DIR, cl, 0)]
        else:
            short = self._short_name(name, used)
            entries = self._lfn_entries(name, short) + \
                      [self._short_entry(short, _ATTR_DIR, cl, 0)]
        off = self._find_free_run(data, len(entries))
        if off is None:
            raise ValueError("root directory is full")
        for i, e in enumerate(entries):
            data[off + i * 32:off + i * 32 + 32] = e
        wb(data)
        self._flush_fat()
        return cl

    def add_file(self, src_path: str, longname: str,
                 folder_cluster: Optional[int] = None) -> None:
        """Write a file (from src_path) into the given folder under `longname`."""
        size = os.path.getsize(src_path)
        need = max(1, (size + self.cluster_bytes - 1) // self.cluster_bytes)
        clusters = self._alloc_chain(need)
        with open(src_path, 'rb') as s:
            for c in clusters:
                chunk = s.read(self.cluster_bytes)
                self.f.seek(self._cluster_offset(c))
                self.f.write(chunk)
                if len(chunk) < self.cluster_bytes:
                    self.f.write(b'\x00' * (self.cluster_bytes - len(chunk)))
        data, wb = self._read_dir(folder_cluster)
        used = self._used_shortnames(data)
        short83 = self._try_83(longname)
        if short83 is not None and short83 not in used:
            entries = [self._short_entry(short83, 0x20, clusters[0], size)]
        else:
            short = self._short_name(longname, used)
            entries = self._lfn_entries(longname, short) + \
                      [self._short_entry(short, 0x20, clusters[0], size)]
        off = self._find_free_run(data, len(entries))
        if off is None:
            raise ValueError("directory is full (no room for the new file)")
        for i, e in enumerate(entries):
            data[off + i * 32:off + i * 32 + 32] = e
        wb(data)
        self._flush_fat()

    def delete_file(self, longname: str, folder_cluster: Optional[int] = None) -> bool:
        """Free a file's clusters and mark its dir entries deleted. Returns hit."""
        data, wb = self._read_dir(folder_cluster)
        target = None
        for o, nm, attr, cl, _s in self._iter_entries(data):
            if not (attr & _ATTR_DIR) and nm == longname:
                target = (o, cl); break
        if target is None:
            return False
        o, cl = target
        # free clusters
        while 2 <= cl < 0xFFF8:
            nxt = self.fat[cl]; self.fat[cl] = 0; cl = nxt
        # mark the short entry + preceding LFN entries deleted
        i = o
        data[i] = _DELETED
        j = o - 32
        while j >= 0 and data[j + 11] == _ATTR_LFN:
            data[j] = _DELETED; j -= 32
        wb(data)
        self._flush_fat()
        return True


# ── formatting a brand-new image ─────────────────────────────────────────────

def format_new(path: str, size_mb: int, label: str = 'MPC2EMU',
               oem: bytes = b'E-MU SYS', serial: int = 0x12345678,
               partition: bool = True, spc: Optional[int] = None,
               rsvd: Optional[int] = None) -> 'Fat16':
    """Create a new FAT16 image and return it open.

    Two layouts:
      * ``partition=True`` (default) — EOS-native E4XT ``.hda``: MBR + one FAT16
        partition at LBA 63, 32 KB clusters, OEM ``E-MU SYS``.
      * ``partition=False`` — Kurzweil K2000/K2500 "pseudo-DOS" disk/CD image: the
        FAT16 BPB sits at sector 0 with **no partition table** (the K2000 does not
        support partitions — see docs and the working CD reference, OEM ``KCDM1.2``,
        rsvd=1).  This is the disk-image-copy form every K2000 OS can read (older
        OS can't read ISO 9660).

    ``spc``/``rsvd`` default per layout but can be overridden (e.g. spc=16 keeps a
    ~360 MB no-partition image inside the FAT16 4085..65524 cluster range)."""
    disk_sectors = (int(size_mb) * 1024 * 1024) // SECTOR
    part_lba = 63 if partition else 0
    part_sectors = disk_sectors - part_lba
    bps, nfats, root_ents = 512, 2, 512
    if spc is None:
        spc = 64 if partition else 16
    if rsvd is None:
        rsvd = 32 if partition else 1
    root_sectors = (root_ents * 32 + bps - 1) // bps               # 32
    tmp1 = part_sectors - (rsvd + root_sectors)
    tmp2 = 256 * spc + nfats                                       # FAT16 estimate
    fatsz = (tmp1 + tmp2 - 1) // tmp2
    data_sectors = part_sectors - (rsvd + nfats * fatsz + root_sectors)
    n_clusters = data_sectors // spc
    if not (4085 <= n_clusters < 65525):
        # EOS picks the FAT type by capacity (EOS 4.7 addendum p.3): FAT12 floppy,
        # FAT16 ≤~1 GB, FAT32 above.  This pure-Python writer does FAT16 only
        # (valid up to ~2 GB, which EOS reads); use --hda-fs emu for larger disks.
        raise ValueError(
            f"size {size_mb} MB → {n_clusters} clusters is outside the FAT16 "
            f"range (~512 MB..2 GB). EOS uses FAT32 above ~1 GB; for a large disk "
            f"use --hda-fs emu (the EMU-fs HDD scales to any size).")

    lab = label.upper().encode('ascii', 'replace')[:11].ljust(11, b' ')

    # MBR
    mbr = bytearray(SECTOR)
    entry = (bytes([0x80]) + _chs(part_lba) + bytes([0x06])
             + _chs(part_lba + part_sectors - 1)
             + struct.pack('<II', part_lba, part_sectors))
    mbr[0x1BE:0x1BE + 16] = entry
    mbr[510:512] = b'\x55\xAA'

    # boot sector / BPB
    bs = bytearray(SECTOR)
    bs[0:3] = b'\xE9\x00\x00'
    bs[3:11] = oem[:8].ljust(8, b' ')
    struct.pack_into('<H', bs, 11, bps)
    bs[13] = spc
    struct.pack_into('<H', bs, 14, rsvd)
    bs[16] = nfats
    struct.pack_into('<H', bs, 17, root_ents)
    struct.pack_into('<H', bs, 19, 0)              # TotSec16 = 0 (use 32-bit)
    bs[21] = 0xF8                                   # media
    struct.pack_into('<H', bs, 22, fatsz)
    struct.pack_into('<H', bs, 24, 63)             # sectors/track
    struct.pack_into('<H', bs, 26, 255)            # heads
    struct.pack_into('<I', bs, 28, part_lba)       # hidden sectors
    struct.pack_into('<I', bs, 32, part_sectors)   # TotSec32
    bs[36] = 0x80                                   # drive number
    bs[38] = 0x29                                   # extended boot sig
    struct.pack_into('<I', bs, 39, serial)
    bs[43:54] = lab
    bs[54:62] = b'FAT16   '
    bs[510:512] = b'\x55\xAA'

    # FAT #1/#2: reserved entries 0,1
    fat = bytearray(fatsz * SECTOR)
    struct.pack_into('<HH', fat, 0, 0xFFF8, 0xFFFF)

    # root: a volume-label entry
    root = bytearray(root_sectors * SECTOR)
    root[0:11] = lab
    root[11] = _ATTR_VOLUME

    with open(path, 'wb') as f:
        if partition:
            f.write(mbr)                            # sector 0: MBR
        f.seek(part_lba * SECTOR)                   # part_lba=0 → boot sector at 0
        f.write(bs)
        f.seek((part_lba + rsvd) * SECTOR)
        f.write(fat)                                # FAT1
        f.write(fat)                                # FAT2
        f.write(root)
        f.truncate(disk_sectors * SECTOR)           # zero-fill data region

    return Fat16(path)
