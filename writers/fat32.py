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
Pure-Python FAT32 reader/writer for EOS-native ZuluSCSI hard-disk images > 1 GB.

EOS 4.7 (addendum p.3) picks the FAT type by capacity: FAT12 floppy,
**FAT16 ≤~1 GB, FAT32 above ~1 GB**.  This is the FAT32 counterpart to
`writers/fat16.py` (which it reuses for the MBR + VFAT long-name + 8.3 helpers):
MBR partition at LBA 63 (type 0x0C, FAT32 LBA), OEM "E-MU SYS", 32 KB clusters,
FSInfo + backup boot sector, cluster-chain root directory.

API mirrors `Fat16` (format_new / add_file / makedir / find_dir / list_dir /
delete_file) so `build_hda_fat` and `fat_hda_append` can pick FAT16 or FAT32 by
size with no other changes.
"""

import os
import struct
from pathlib import Path
from typing import List, Optional

from writers.fat16 import (SECTOR, _chs, _ATTR_VOLUME, _ATTR_DIR, _ATTR_LFN,
                           _FREE, _DELETED, Fat16)

_EOC = 0x0FFFFFF8          # end-of-chain (any value >= this is EOC)


class Fat32:
    """A FAT32 filesystem inside an MBR-partitioned disk image, read/write."""

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

    # ── geometry ──────────────────────────────────────────────────────────────
    def _part_offset(self) -> int:
        self.f.seek(0); s0 = self.f.read(SECTOR)
        if s0[510:512] == b'\x55\xAA':
            for i in range(4):
                e = s0[0x1BE + i * 16:0x1BE + i * 16 + 16]
                if e[4] in (0x0B, 0x0C, 0x06, 0x0E):
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
        self.fatsz = struct.unpack_from('<I', b, 36)[0]      # FATSz32
        self.root_clus = struct.unpack_from('<I', b, 44)[0]  # usually 2
        self.cluster_bytes = self.bps * self.spc
        self.fat_start  = self.rsvd
        self.data_start = self.rsvd + self.nfats * self.fatsz   # sector of cluster 2
        total = struct.unpack_from('<I', b, 32)[0]
        self.n_clusters = (total - self.data_start) // self.spc
        # load FAT #1 (32-bit entries, low 28 bits significant)
        import array
        self.f.seek(self.part_off + self.fat_start * SECTOR)
        raw = self.f.read(self.fatsz * SECTOR)
        self.fat = array.array('I', raw[:(len(raw) // 4) * 4])

    def _abs(self, sector: int) -> int:
        return self.part_off + sector * SECTOR

    def _cluster_offset(self, cluster: int) -> int:
        return self._abs(self.data_start + (cluster - 2) * self.spc)

    # ── FAT chains ────────────────────────────────────────────────────────────
    def _chain(self, start: int) -> List[int]:
        out, c = [], start
        while 2 <= c < _EOC and c < len(self.fat):
            out.append(c)
            c = self.fat[c] & 0x0FFFFFFF
        return out

    def _alloc_chain(self, n: int) -> List[int]:
        free = [c for c in range(2, self.n_clusters + 2)
                if c < len(self.fat) and (self.fat[c] & 0x0FFFFFFF) == 0][:n]
        if len(free) < n:
            raise ValueError(f"FAT32 image full: need {n} clusters, {len(free)} free")
        for j, c in enumerate(free):
            self.fat[c] = (free[j + 1] if j < n - 1 else 0x0FFFFFFF)
        return free

    def _extend_chain(self, last: int) -> int:
        nc = self._alloc_chain(1)[0]
        self.fat[last] = nc
        return nc

    def _flush_fat(self):
        raw = self.fat.tobytes()
        for i in range(self.nfats):
            self.f.seek(self.part_off + (self.fat_start + i * self.fatsz) * SECTOR)
            self.f.write(raw[:self.fatsz * SECTOR])

    # ── directories (cluster chains) ──────────────────────────────────────────
    def _read_dir(self, start_cluster: int):
        clusters = self._chain(start_cluster)
        data = bytearray()
        for c in clusters:
            self.f.seek(self._cluster_offset(c)); data += self.f.read(self.cluster_bytes)

        def wb(d):
            # write back, growing the chain if the (32-byte-padded) data outgrew it
            need = (len(d) + self.cluster_bytes - 1) // self.cluster_bytes
            chain = list(clusters)
            while len(chain) < need:
                nc = self._extend_chain(chain[-1])
                self.f.seek(self._cluster_offset(nc))
                self.f.write(b'\x00' * self.cluster_bytes)
                chain.append(nc)
            for i, c in enumerate(chain):
                self.f.seek(self._cluster_offset(c))
                self.f.write(d[i * self.cluster_bytes:(i + 1) * self.cluster_bytes]
                             .ljust(self.cluster_bytes, b'\x00'))
        return data, wb

    def list_dir(self, start_cluster: Optional[int]) -> List[str]:
        data, _ = self._read_dir(start_cluster or self.root_clus)
        return [name for _o, name, attr, _c, _s in Fat16._iter_entries(data)
                if not (attr & _ATTR_DIR)]

    def find_dir(self, name: str) -> Optional[int]:
        data, _ = self._read_dir(self.root_clus)
        for _o, nm, attr, cl, _s in Fat16._iter_entries(data):
            if (attr & _ATTR_DIR) and nm.strip().lower() == name.strip().lower():
                return cl
        return None

    @staticmethod
    def _used_shortnames(data) -> set:
        out = set()
        for o in range(0, len(data), 32):
            if data[o] == _FREE:
                break
            if data[o] == _DELETED or data[o + 11] == _ATTR_LFN:
                continue
            out.add(bytes(data[o:o + 11]))
        return out

    @staticmethod
    def _short_entry_hi(short11, attr, cluster, size):
        e = bytearray(Fat16._short_entry(short11, attr, cluster, size))
        struct.pack_into('<H', e, 20, (cluster >> 16) & 0xFFFF)   # FAT32 high word
        return bytes(e)

    def _add_entries(self, dir_cluster: int, longname: str, attr: int,
                     cluster: int, size: int):
        data, wb = self._read_dir(dir_cluster)
        short = Fat16._short_name(longname, self._used_shortnames(data))
        entries = Fat16._lfn_entries(longname, short) + \
                  [self._short_entry_hi(short, attr, cluster, size)]
        off = Fat16._find_free_run(data, len(entries))
        if off is None:                       # grow the dir by appending a slot run
            off = len(data)
            data += bytearray(len(entries) * 32)
        for i, e in enumerate(entries):
            data[off + i * 32:off + i * 32 + 32] = e
        wb(data)

    # ── public mutators ──────────────────────────────────────────────────────
    def makedir(self, name: str) -> int:
        existing = self.find_dir(name)
        if existing is not None:
            return existing
        cl = self._alloc_chain(1)[0]
        block = bytearray(self.cluster_bytes)
        block[0:32]  = self._short_entry_hi(b'.          ', _ATTR_DIR, cl, 0)
        block[32:64] = self._short_entry_hi(b'..         ', _ATTR_DIR, 0, 0)
        self.f.seek(self._cluster_offset(cl)); self.f.write(block)
        self._add_entries(self.root_clus, name, _ATTR_DIR, cl, 0)
        self._flush_fat()
        return cl

    def add_file(self, src_path: str, longname: str,
                 folder_cluster: Optional[int] = None) -> None:
        size = os.path.getsize(src_path)
        need = max(1, (size + self.cluster_bytes - 1) // self.cluster_bytes)
        clusters = self._alloc_chain(need)
        with open(src_path, 'rb') as s:
            for c in clusters:
                chunk = s.read(self.cluster_bytes)
                self.f.seek(self._cluster_offset(c)); self.f.write(chunk)
                if len(chunk) < self.cluster_bytes:
                    self.f.write(b'\x00' * (self.cluster_bytes - len(chunk)))
        self._add_entries(folder_cluster or self.root_clus, longname, 0x20,
                          clusters[0], size)
        self._flush_fat()

    def delete_file(self, longname: str, folder_cluster: Optional[int] = None) -> bool:
        data, wb = self._read_dir(folder_cluster or self.root_clus)
        target = None
        for o, nm, attr, cl, _s in Fat16._iter_entries(data):
            if not (attr & _ATTR_DIR) and nm == longname:
                target = (o, cl); break
        if target is None:
            return False
        o, cl = target
        while 2 <= cl < _EOC and cl < len(self.fat):
            nxt = self.fat[cl] & 0x0FFFFFFF; self.fat[cl] = 0; cl = nxt
        data[o] = _DELETED
        j = o - 32
        while j >= 0 and data[j + 11] == _ATTR_LFN:
            data[j] = _DELETED; j -= 32
        wb(data)
        self._flush_fat()
        return True


# ── formatting a brand-new FAT32 image ────────────────────────────────────────

def format_new(path: str, size_mb: int, label: str = 'MPC2EMU',
               oem: bytes = b'E-MU SYS', serial: int = 0x12345678) -> 'Fat32':
    """Create a new EOS-native FAT32 .hda (MBR + FAT32) and return it open."""
    disk_sectors = (int(size_mb) * 1024 * 1024) // SECTOR
    part_lba = 63
    part_sectors = disk_sectors - part_lba
    bps, rsvd, nfats = 512, 32, 2
    # Pick the largest power-of-two cluster (≤32 KB) that still yields a valid
    # FAT32 (≥65525 clusters).  FAT32 size per MS fatgen103: FATSz =
    # ceil((DskSize-Rsvd) / ((256*SecPerClus + NumFATs) / 2)).
    spc = fatsz = data_sectors = n_clusters = 0
    for spc in (64, 32, 16, 8):                     # 32 / 16 / 8 / 4 KB
        tmp2 = (256 * spc + nfats) // 2
        fatsz = (part_sectors - rsvd + tmp2 - 1) // tmp2
        data_sectors = part_sectors - (rsvd + nfats * fatsz)
        n_clusters = data_sectors // spc
        if n_clusters >= 65525:
            break
    if n_clusters < 65525:
        raise ValueError(f"{size_mb} MB is too small for FAT32 (<65525 clusters); "
                         f"EOS uses FAT16 below ~1 GB — use --hda-fs fat.")

    lab = label.upper().encode('ascii', 'replace')[:11].ljust(11, b' ')
    root_clus = 2

    # MBR — partition type 0x0C (FAT32 LBA)
    mbr = bytearray(SECTOR)
    entry = (bytes([0x80]) + _chs(part_lba) + bytes([0x0C])
             + _chs(part_lba + part_sectors - 1)
             + struct.pack('<II', part_lba, part_sectors))
    mbr[0x1BE:0x1BE + 16] = entry
    mbr[510:512] = b'\x55\xAA'

    # boot sector / BPB (FAT32)
    bs = bytearray(SECTOR)
    bs[0:3] = b'\xE9\x00\x00'
    bs[3:11] = oem[:8].ljust(8, b' ')
    struct.pack_into('<H', bs, 11, bps)
    bs[13] = spc
    struct.pack_into('<H', bs, 14, rsvd)
    bs[16] = nfats
    struct.pack_into('<H', bs, 17, 0)              # RootEntCnt = 0 (FAT32)
    struct.pack_into('<H', bs, 19, 0)              # TotSec16 = 0
    bs[21] = 0xF8
    struct.pack_into('<H', bs, 22, 0)              # FATSz16 = 0 (FAT32 uses FATSz32)
    struct.pack_into('<H', bs, 24, 63)             # sectors/track
    struct.pack_into('<H', bs, 26, 255)            # heads
    struct.pack_into('<I', bs, 28, part_lba)       # hidden sectors
    struct.pack_into('<I', bs, 32, part_sectors)   # TotSec32
    struct.pack_into('<I', bs, 36, fatsz)          # FATSz32
    struct.pack_into('<H', bs, 40, 0)              # ExtFlags
    struct.pack_into('<H', bs, 42, 0)              # FSVer
    struct.pack_into('<I', bs, 44, root_clus)      # RootClus
    struct.pack_into('<H', bs, 48, 1)              # FSInfo sector
    struct.pack_into('<H', bs, 50, 6)              # backup boot sector
    bs[64] = 0x80                                  # drive number
    bs[66] = 0x29                                  # extended boot sig
    struct.pack_into('<I', bs, 67, serial)
    bs[71:82] = lab
    bs[82:90] = b'FAT32   '
    bs[510:512] = b'\x55\xAA'

    # FSInfo sector
    fsinfo = bytearray(SECTOR)
    struct.pack_into('<I', fsinfo, 0, 0x41615252)
    struct.pack_into('<I', fsinfo, 484, 0x61417272)
    free_count = n_clusters - 1                     # cluster 2 used by root
    struct.pack_into('<I', fsinfo, 488, free_count)
    struct.pack_into('<I', fsinfo, 492, 3)         # next free hint
    struct.pack_into('<I', fsinfo, 508, 0xAA550000)

    # FAT: reserved 0/1 + root chain EOC at cluster 2
    fat = bytearray(fatsz * SECTOR)
    struct.pack_into('<III', fat, 0, 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF)

    with open(path, 'wb') as f:
        f.write(mbr)
        f.seek(part_lba * SECTOR);            f.write(bs)
        f.seek((part_lba + 1) * SECTOR);      f.write(fsinfo)
        f.seek((part_lba + 6) * SECTOR);      f.write(bs)        # backup boot
        f.seek((part_lba + 7) * SECTOR);      f.write(fsinfo)    # backup FSInfo
        f.seek((part_lba + rsvd) * SECTOR);   f.write(fat)       # FAT1
        f.write(fat)                                             # FAT2
        # root cluster (cluster 2) with a volume-label entry
        root = bytearray(spc * SECTOR)
        root[0:11] = lab
        root[11] = _ATTR_VOLUME
        data_off = (part_lba + rsvd + nfats * fatsz) * SECTOR
        f.seek(data_off); f.write(root)
        f.truncate(disk_sectors * SECTOR)

    return Fat32(path)
