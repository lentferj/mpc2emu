# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# Independent reimplementation.  Akai MPC60 SET layout and 12-bit sample
# unpacking informed by ConvertWithMoss (LGPLv3),
#   Jürgen Moßgraber, https://github.com/git-moss/ConvertWithMoss
#   (format/akai/mpc60: AkaiMPC60Set/Pad/Detector).
# Verified byte-for-byte against the reference "Akai MPC60 to WAV" decoder's
# output (decoded samples correlate >0.97 with the tool's WAVs for tonal hits).
# No source code was copied.
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
Akai MPC60 SET / floppy-image Parser
-------------------------------------
The Akai MPC60 (1988) stored sounds in `.SET` files on DOS-FAT 3.5" floppies.
A SET is a RAM image: a header + 32 pad records + a block of concatenated 12-bit
samples.  This parser handles both a bare `.SET` and a raw floppy `.img` (FAT12,
from which the embedded `.SET` is extracted).

SET layout (little-endian), intact "800K" version (magic byte 0x02):
  0x00   1   magic = 0x02
  0x05  ..   32 pad records, 0x3B (59) bytes each:
               +0   16  name (ASCII, space-padded)
               +18   3  sample start  (u24, in frames, into the sample block)
               +22   3  sample length (u24, in frames)
               (+more: play start, decay, volume, panning — not used here)
  0xBFF  ..   concatenated 12-bit sample block (2 frames packed per 3 bytes)

12-bit unpack (2 frames / 3 bytes), 40 kHz mono:
  s0 = byteswap(b0 | ((b2 & 0x0F) << 8))
  s1 = byteswap(b1 | ((b2 & 0xF0) << 4))
Each pad's audio is sample_block[start : start+length].

Note: floppies copied from the original 800K disks onto 720K PC disks are
truncated and have a different/disturbed header (magic byte 0x00).  Those are
only partially recoverable; this parser supports the intact 0x02 version and
warns on the truncated variant.
"""

import array
from pathlib import Path
from typing import List, Optional, Dict, Tuple

from models.common import Bank, Preset, VoiceLayer, ZoneMapping, SampleData

_MPC60_RATE  = 40000
_SET_MAGIC   = 0x02
_PAD_START   = 0x05
_PAD_STRIDE  = 0x3B
_N_PADS      = 32
_SAMPLE_BASE = 0xC00 - 1     # 0xBFF: start of the 12-bit sample block
_BASE_NOTE   = 36            # C1


def _u24(d: bytes, o: int) -> int:
    return d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)


def _unpack_12bit(block: bytes) -> array.array:
    """Unpack the MPC60 12-bit sample block (2 frames per 3 bytes) → int16."""
    out = array.array('h')
    n = (len(block) // 3) * 3
    for i in range(0, n, 3):
        b0, b1, b2 = block[i], block[i + 1], block[i + 2]
        for v in (b0 | ((b2 & 0x0F) << 8), b1 | ((b2 & 0xF0) << 4)):
            v = ((v & 0xFF) << 8) | ((v >> 8) & 0xFF)      # byteswap (left-justify)
            out.append(v - 0x10000 if v >= 0x8000 else v)
    return out


def parse_mpc60_set_bytes(data: bytes, name: str) -> Bank:
    """Parse raw MPC60 SET bytes into a Bank."""
    if not data or data[0] != _SET_MAGIC:
        b0 = data[0] if data else -1
        raise ValueError(
            f"Not an intact MPC60 SET (magic byte 0x{b0:02X}, expected 0x02). "
            f"720K-truncated copies (0x00) are not supported: {name}")

    bank   = Bank(name=name[:16])
    preset = Preset(name=name[:16])

    samples = _unpack_12bit(data[_SAMPLE_BASE:])
    total   = len(samples)

    # Parse pads; de-duplicate by (start,length) — the MPC60's 32 pad slots
    # often repeat the same sound (unassigned pads default to the first sample).
    seen: Dict[Tuple[int, int], str] = {}
    note = _BASE_NOTE
    n_trunc = 0
    for i in range(_N_PADS):
        o = _PAD_START + i * _PAD_STRIDE
        if o + 25 > len(data):
            break
        nm = data[o:o + 16].split(b'\x00')[0].decode('ascii', 'replace').strip()
        start = _u24(data, o + 18)
        length = _u24(data, o + 22)
        if not nm or length == 0:
            continue
        key = (start, length)
        if key in seen:
            continue
        seen[key] = nm

        end = start + length
        if start >= total:
            continue                      # sample lies entirely past the data
        if end > total:                   # truncated tail (720K copy etc.)
            end = total
            n_trunc += 1
        pcm = samples[start:end].tobytes()
        if len(pcm) < 4:
            continue

        sname = nm[:16]
        sd = SampleData(name=sname, data=pcm, sample_rate=_MPC60_RATE,
                        channels=1, bit_depth=16, root_note=note)
        bank.samples.append(sd)
        n = min(127, note)
        preset.voices.append(VoiceLayer(zones=[ZoneMapping(
            sample_name=sname, lo_key=n, hi_key=n, lo_vel=0, hi_vel=127,
            root_key=n)]))
        print(f"  Sample: {sname:16s} frames={end - start:6d} @ {_MPC60_RATE} Hz")
        note += 1

    if n_trunc:
        print(f"  [WARN] {n_trunc} sample(s) had truncated tails (incomplete SET)")
    if preset.voices:
        bank.presets.append(preset)
    print(f"  Preset '{preset.name}': {len(preset.voices)} sound(s)")
    return bank


def parse_mpc60_set(set_path: str, sample_dirs: Optional[List[str]] = None) -> Bank:
    """Parse a bare Akai MPC60 `.SET` file."""
    p = Path(set_path).resolve()
    print(f"Parsing MPC60 SET: {p.name}")
    return parse_mpc60_set_bytes(p.read_bytes(), p.stem)


# ---------------------------------------------------------------------------
# FAT12 floppy image (.img): extract the embedded .SET and parse it
# ---------------------------------------------------------------------------

def _fat12_read_set(img: bytes) -> Tuple[str, bytes]:
    """Find and read the (first) `.SET` file out of a FAT12 floppy image."""
    import struct
    if len(img) < 0x200 or img[0] not in (0xEB, 0xE9):
        raise ValueError("Not a FAT boot sector")
    bps    = struct.unpack_from('<H', img, 0x0B)[0]
    spc    = img[0x0D]
    rsvd   = struct.unpack_from('<H', img, 0x0E)[0]
    nfat   = img[0x10]
    rootn  = struct.unpack_from('<H', img, 0x11)[0]
    spf    = struct.unpack_from('<H', img, 0x16)[0]
    fat_off  = rsvd * bps
    root_off = (rsvd + nfat * spf) * bps
    data_off = root_off + ((rootn * 32 + bps - 1) // bps) * bps
    fat = img[fat_off:fat_off + spf * bps]

    def fat12(n: int) -> int:
        v = fat[n * 3 // 2] | (fat[n * 3 // 2 + 1] << 8)
        return (v & 0x0FFF) if n % 2 == 0 else (v >> 4)

    for e in range(rootn):
        ent = img[root_off + e * 32: root_off + e * 32 + 32]
        if ent[0] in (0x00, 0xE5) or (ent[11] & 0x08):
            continue
        name = ent[0:8].decode('ascii', 'replace').rstrip()
        ext  = ent[8:11].decode('ascii', 'replace').rstrip()
        if ext.upper() != 'SET':
            continue
        size  = struct.unpack_from('<I', ent, 28)[0]
        clus  = struct.unpack_from('<H', ent, 26)[0]
        buf = bytearray()
        while 2 <= clus < 0xFF0 and len(buf) < size + spc * bps:
            off = data_off + (clus - 2) * spc * bps
            buf += img[off:off + spc * bps]
            clus = fat12(clus)
        return f"{name}", bytes(buf[:size])

    # NAME WHAT IT ACTUALLY IS, rather than reporting a missing .SET.
    #
    # `.img` reaches this parser by elimination -- it is the only FAT12 floppy
    # format the dispatcher knows -- so a K2000 floppy, WHICH THIS PROJECT
    # ITSELF WRITES with --floppy, was announced as "Parsing MPC60 floppy
    # image" and then rejected for lacking a .SET. The parse never went wrong;
    # the diagnosis did, and it pointed the user at the wrong format entirely.
    #
    # Prompted by VinSamLib hitting the harsher version of this on 2026-08-14:
    # their loop scan picked its module by elimination, which was correct for
    # three formats and silently wrong the moment a fourth existed. Ours fails
    # loudly rather than silently, so this is a message, not a misread -- but
    # a wrong name in an error is a wrong answer to the question the user
    # actually asked.
    others = sorted({e for e in _fat12_extensions(img) if e and e != 'SET'})
    if 'KRZ' in others:
        raise ValueError(
            "This is a Kurzweil K2000 floppy image (it holds .KRZ files), not "
            "an MPC60 one. mpc2emu writes these with --floppy; reading them "
            "back is not implemented.")
    if others:
        raise ValueError(
            f"No .SET file in this FAT12 floppy image; it holds "
            f"{', '.join('.' + e for e in others[:4])} instead, so it is "
            f"probably not an MPC60 disk.")
    raise ValueError("No .SET file found in the floppy image")


def _fat12_extensions(img: bytes) -> set:
    """Every file extension in a FAT12 root directory, upper-case.

    Used only to say what an image IS when it turns out not to be an MPC60
    disk.  Deliberately tolerant: it runs on the failure path, so a malformed
    directory must not replace the real error with its own.
    """
    import struct
    out = set()
    try:
        bps   = struct.unpack_from('<H', img, 0x0B)[0]
        rsvd  = struct.unpack_from('<H', img, 0x0E)[0]
        nfat  = img[0x10]
        rootn = struct.unpack_from('<H', img, 0x11)[0]
        spf   = struct.unpack_from('<H', img, 0x16)[0]
        root_off = (rsvd + nfat * spf) * bps
        for e in range(rootn):
            ent = img[root_off + e * 32: root_off + e * 32 + 32]
            if len(ent) < 32 or ent[0] in (0x00, 0xE5) or (ent[11] & 0x08):
                continue
            out.add(ent[8:11].decode('ascii', 'replace').rstrip().upper())
    except Exception:
        pass
    return out


def parse_mpc60_img(img_path: str, sample_dirs: Optional[List[str]] = None) -> Bank:
    """Parse an MPC60 floppy image (.img, FAT12) by extracting its `.SET`."""
    p = Path(img_path).resolve()
    # Announce the FILE, not the format. Saying "MPC60" here asserted the
    # conclusion before the check that establishes it, so a K2000 floppy was
    # announced as an MPC60 disk and only contradicted afterwards.
    print(f"Reading floppy image: {p.name}")
    name, set_bytes = _fat12_read_set(p.read_bytes())
    print("  MPC60 floppy confirmed (.SET present)")
    print(f"  Extracted SET '{name}' ({len(set_bytes)} bytes)")
    return parse_mpc60_set_bytes(set_bytes, name or p.stem)
