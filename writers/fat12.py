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
Pure-Python FAT12 floppy-image writer for Kurzweil K2000/K2500/K2600 via a
Gotek / FlashFloppy emulator.

The K2000R reads standard DOS **720 KB / 1.44 MB FAT12** floppies; a Gotek
presents a raw sector image (`.img`) of exactly such a floppy.  A K2000 bank is
a single `.KRZ` file written to the floppy's root (e.g. a 1.39 MB SYNTHEX_2.KRZ
fills a 1.44 MB disk).  This module formats a blank FAT12 floppy image (no MBR —
the boot sector is at LBA 0) and copies `.KRZ` files in, with VFAT long names +
8.3 short names (DOS/K2000 reads the 8.3; PCs show the long name).

Reuses the VFAT/8.3 + directory helpers from `writers/fat16.py`.
"""

import os
import struct
from pathlib import Path
from typing import List, Optional

from writers.fat16 import (SECTOR, _ATTR_VOLUME, _ATTR_DIR, _ATTR_LFN,
                           _FREE, _DELETED, Fat16)

# Standard floppy geometries: kind -> (sectors, spc, root_ents, fatsz, media, spt)
_GEOM = {
    '1440': dict(total=2880, spc=1, root=224, fatsz=9, media=0xF0, spt=18, heads=2),
    '720':  dict(total=1440, spc=2, root=112, fatsz=3, media=0xF9, spt=9,  heads=2),
}
_EOC = 0xFF8                      # FAT12 end-of-chain (>= 0xFF8)


def _fat12_get(fat: bytearray, n: int) -> int:
    o = (n * 3) // 2
    if n & 1:
        return ((fat[o] >> 4) | (fat[o + 1] << 4)) & 0xFFF
    return (fat[o] | ((fat[o + 1] & 0x0F) << 8)) & 0xFFF


def _fat12_set(fat: bytearray, n: int, v: int):
    o = (n * 3) // 2
    v &= 0xFFF
    if n & 1:
        fat[o] = (fat[o] & 0x0F) | ((v & 0x0F) << 4)
        fat[o + 1] = (v >> 4) & 0xFF
    else:
        fat[o] = v & 0xFF
        fat[o + 1] = (fat[o + 1] & 0xF0) | ((v >> 8) & 0x0F)


class Fat12:
    """A FAT12 floppy filesystem (boot sector at LBA 0, fixed root dir)."""

    def __init__(self, path: str):
        self.path = str(path)
        self.f = open(self.path, 'r+b')
        self._read_bpb()

    def close(self):
        if self.f:
            self.f.flush(); self.f.close(); self.f = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _read_bpb(self):
        self.f.seek(0); b = self.f.read(SECTOR)
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
        self.data_start = self.root_start + self.root_sectors
        total = struct.unpack_from('<H', b, 19)[0]
        self.n_clusters = (total - self.data_start) // self.spc
        self.f.seek(self.fat_start * SECTOR)
        self.fat = bytearray(self.f.read(self.fatsz * SECTOR))

    def _cluster_offset(self, cluster: int) -> int:
        return (self.data_start + (cluster - 2) * self.spc) * SECTOR

    # ── FAT ───────────────────────────────────────────────────────────────────
    def _alloc_chain(self, n: int) -> List[int]:
        free = [c for c in range(2, self.n_clusters + 2) if _fat12_get(self.fat, c) == 0][:n]
        if len(free) < n:
            raise ValueError(f"floppy full: need {n} clusters, {len(free)} free "
                             f"({self.n_clusters * self.cluster_bytes // 1024} KB total)")
        for j, c in enumerate(free):
            _fat12_set(self.fat, c, free[j + 1] if j < n - 1 else 0xFFF)
        return free

    def _flush_fat(self):
        for i in range(self.nfats):
            self.f.seek((self.fat_start + i * self.fatsz) * SECTOR)
            self.f.write(self.fat[:self.fatsz * SECTOR])

    # ── root directory (fixed area) ───────────────────────────────────────────
    def _read_dir(self):
        self.f.seek(self.root_start * SECTOR)
        data = bytearray(self.f.read(self.root_sectors * SECTOR))

        def wb(d):
            self.f.seek(self.root_start * SECTOR); self.f.write(d)
        return data, wb

    def list_dir(self, _folder=None) -> List[str]:
        data, _ = self._read_dir()
        return [name for _o, name, attr, _c, _s in Fat16._iter_entries(data)
                if not (attr & _ATTR_DIR)]

    def find_dir(self, name):          # floppies here are flat (root only)
        return None

    def add_file(self, src_path: str, longname: str, _folder=None) -> None:
        size = os.path.getsize(src_path)
        need = max(1, (size + self.cluster_bytes - 1) // self.cluster_bytes)
        clusters = self._alloc_chain(need)
        with open(src_path, 'rb') as s:
            for c in clusters:
                chunk = s.read(self.cluster_bytes)
                self.f.seek(self._cluster_offset(c)); self.f.write(chunk)
                if len(chunk) < self.cluster_bytes:
                    self.f.write(b'\x00' * (self.cluster_bytes - len(chunk)))
        data, wb = self._read_dir()
        used = {bytes(data[o:o + 11]) for o in range(0, len(data), 32)
                if data[o] not in (_FREE, _DELETED) and data[o + 11] != _ATTR_LFN}
        # Clean 8.3 name (no VFAT long-name entries) when it already fits, so the
        # K2000 shows the real name rather than a mangled NAME~1 alias.
        short83 = Fat16._try_83(longname)
        if short83 is not None and short83 not in used:
            entries = [Fat16._short_entry(short83, 0x20, clusters[0], size)]
        else:
            short = Fat16._short_name(longname, used)
            entries = Fat16._lfn_entries(longname, short) + \
                      [Fat16._short_entry(short, 0x20, clusters[0], size)]
        off = Fat16._find_free_run(data, len(entries))
        if off is None:
            raise ValueError("floppy root directory is full")
        for i, e in enumerate(entries):
            data[off + i * 32:off + i * 32 + 32] = e
        wb(data)
        self._flush_fat()


# ── formatting a blank floppy ─────────────────────────────────────────────────

def format_new(path: str, kind: str = '1440', label: str = '',
               oem: bytes = b'MSWIN4.1', serial: int = 0x12345678) -> 'Fat12':
    """Create a blank DOS FAT12 floppy image ('1440' = 1.44 MB, '720' = 720 KB)."""
    if str(kind) not in _GEOM:
        raise ValueError(f"floppy kind must be one of {list(_GEOM)} (KB)")
    g = _GEOM[str(kind)]
    bps = 512
    total = g['total']; spc = g['spc']; rsvd = 1; nfats = 2
    root_ents = g['root']; fatsz = g['fatsz']
    root_sectors = (root_ents * 32 + bps - 1) // bps
    lab = (label or 'NO NAME').upper().encode('ascii', 'replace')[:11].ljust(11, b' ')

    bs = bytearray(SECTOR)
    bs[0:3] = b'\xEB\x3C\x90'
    bs[3:11] = oem[:8].ljust(8, b' ')
    struct.pack_into('<H', bs, 11, bps)
    bs[13] = spc
    struct.pack_into('<H', bs, 14, rsvd)
    bs[16] = nfats
    struct.pack_into('<H', bs, 17, root_ents)
    struct.pack_into('<H', bs, 19, total)          # TotSec16
    bs[21] = g['media']
    struct.pack_into('<H', bs, 22, fatsz)
    struct.pack_into('<H', bs, 24, g['spt'])
    struct.pack_into('<H', bs, 26, g['heads'])
    struct.pack_into('<I', bs, 28, 0)              # hidden sectors (none on floppy)
    bs[36] = 0x00                                  # drive number
    bs[38] = 0x29                                  # extended boot sig
    struct.pack_into('<I', bs, 39, serial)
    bs[43:54] = lab
    bs[54:62] = b'FAT12   '
    bs[510:512] = b'\x55\xAA'

    fat = bytearray(fatsz * bps)
    fat[0] = g['media']; fat[1] = 0xFF; fat[2] = 0xFF   # FAT12 reserved entries

    root = bytearray(root_sectors * bps)
    if label:
        root[0:11] = lab
        root[11] = _ATTR_VOLUME

    with open(path, 'wb') as f:
        f.write(bs)
        f.seek(rsvd * bps);                  f.write(fat)        # FAT1
        f.write(fat)                                             # FAT2
        f.write(root)
        f.truncate(total * bps)

    return Fat12(path)
