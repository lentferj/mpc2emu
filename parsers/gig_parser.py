# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
#
# This file is part of mpc2emu.
# GIG/DLS2 binary structure derived from libgig:
#   Copyright (C) 2003-2021 Christian Schoenebeck <cuse@users.sourceforge.net>
#   https://www.linuxsampler.org/libgig/  —  GPL-2.0-or-later
# Initial GIG reverse engineering: Paul Kellett, Ruben van Royen.
# GigaStudio v3/v4 support: Andreas Persson.
# No source code was copied; this is an independent Python reimplementation
# of the documented binary structures.  The '3ewa' articulation layout (EG1 amp
# + EG2 filter envelopes, VCF) follows libgig's gig.cpp DimensionRegion and was
# validated byte-for-byte against the libgig `gigdump` tool.
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
GigaSampler / GigaStudio (.gig) Parser
----------------------------------------
GIG is based on DLS Level 2 with Giga-specific extensions.
It is a RIFF file with the top-level type 'DLS '.

Top-level structure:
  RIFF 'DLS '
    colh      — collection header (number of instruments)
    LIST 'lins' — instrument list
      LIST 'ins ' (×N) — one per instrument
        insh          — instrument header (bank, program, regions count)
        LIST 'lrgn'   — region list
          LIST 'rgn '  — one region per key range
            rgnh        — region header (key/vel range, layer info)
            wsmp        — wave sample (root note, fine tune, loop)
            wlnk        — wave link (sample index)
            LIST '3prg' — Giga-specific articulation (envelopes, etc.)
        LIST 'lart'   — instrument articulation
    LIST 'wvpl' — wave pool
      LIST 'wave' (×M) — one per sample
        fmt           — WAVE fmt chunk
        data          — PCM sample data
        smpl          — optional loop points

References:
  - Microsoft DLS Level 1 & 2 specifications
  - libgig source (GPL, Christian Schoenebeck / linuxsampler.org)
  - Giga format notes from jimcraiglive.com and linuxsampler wiki
"""

import array
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType
)
from parsers.xpm_parser import _safe_name

# CR-16: unsigned-8 → signed-8 sign-flip table (bulk `bytes.translate`).
_FLIP_SIGN8 = bytes((i ^ 0x80) for i in range(256))


# ---------------------------------------------------------------------------
# RIFF/LIST walker
# ---------------------------------------------------------------------------

class _RiffWalker:
    """Lightweight RIFF chunk navigator."""

    def __init__(self, data: bytes, offset: int = 0, size: int = -1):
        self.data   = data
        self.start  = offset
        self.size   = size if size >= 0 else len(data) - offset
        self.end    = offset + self.size

    def chunks(self) -> List[Tuple[str, int, int]]:
        """Yield (fourcc, data_offset, data_size) for each direct child."""
        result = []
        pos = self.start
        while pos + 8 <= self.end:
            fourcc = self.data[pos:pos+4].decode('ascii', errors='replace')
            size   = struct.unpack_from('<I', self.data, pos+4)[0]
            d_off  = pos + 8
            result.append((fourcc, d_off, size))
            pos = d_off + size
            if pos % 2:
                pos += 1
        return result

    def find(self, fourcc: str) -> Optional[Tuple[int, int]]:
        """Return (offset, size) of first chunk with given fourcc."""
        for fc, off, sz in self.chunks():
            if fc == fourcc:
                return off, sz
        return None

    def find_list(self, list_type: str) -> Optional['_RiffWalker']:
        """Return sub-walker for first LIST/RIFF with given list-type."""
        for fc, off, sz in self.chunks():
            if fc in ('LIST', 'RIFF') and sz >= 4:
                lt = self.data[off:off+4].decode('ascii', errors='replace')
                if lt == list_type:
                    return _RiffWalker(self.data, off+4, sz-4)
        return None

    def read(self, offset: int, size: int) -> bytes:
        return self.data[offset:offset+size]

    def u32(self, offset: int) -> int:
        return struct.unpack_from('<I', self.data, offset)[0]

    def u16(self, offset: int) -> int:
        return struct.unpack_from('<H', self.data, offset)[0]

    def i16(self, offset: int) -> int:
        return struct.unpack_from('<h', self.data, offset)[0]

    def cstr(self, offset: int, maxlen: int) -> str:
        return self.data[offset:offset+maxlen].split(b'\x00')[0].decode(
            'ascii', errors='replace')


# ---------------------------------------------------------------------------
# DLS / GIG data structures
# ---------------------------------------------------------------------------

def _parse_rgnh(data: bytes, off: int) -> dict:
    """Region header: key range, vel range, layer."""
    return {
        'key_lo':  struct.unpack_from('<H', data, off)[0],
        'key_hi':  struct.unpack_from('<H', data, off+2)[0],
        'vel_lo':  struct.unpack_from('<H', data, off+4)[0],
        'vel_hi':  struct.unpack_from('<H', data, off+6)[0],
        'key_group': struct.unpack_from('<H', data, off+8)[0],
        'layer':   struct.unpack_from('<H', data, off+10)[0] if len(data)-off > 10 else 0,
    }


def _parse_wsmp(data: bytes, off: int, chunk_size: int = 0) -> dict:
    """Wave sample: root note, fine tune, loops.

    chunk_size must be the RIFF chunk data size (wsmp_r[1]) so the bounds check
    uses the real on-disk size.  WSMPL.cbSize (at off+0) equals 20 per the DLS 2.0
    spec — it counts only the fixed header, not the WLOOP structs that follow —
    so using it for bounds would always reject loops.
    """
    cbsize      = struct.unpack_from('<I', data, off)[0]
    unity_note  = struct.unpack_from('<H', data, off+4)[0]
    fine_tune   = struct.unpack_from('<h', data, off+6)[0]   # cents
    gain        = struct.unpack_from('<i', data, off+8)[0]   # millibels
    options     = struct.unpack_from('<I', data, off+12)[0]
    num_loops   = struct.unpack_from('<I', data, off+16)[0]

    loops = []
    bounds = off + (chunk_size if chunk_size > cbsize else cbsize)
    for li in range(num_loops):
        lo = off + 20 + li * 16          # WLOOP stride = 16 (cbSize+type+start+length)
        if lo + 16 > bounds:
            break
        # DLS WLOOP layout: [0] cbSize  [4] ulType  [8] ulStart  [12] ulLength
        loop_type   = struct.unpack_from('<I', data, lo+4)[0]
        loop_start  = struct.unpack_from('<I', data, lo+8)[0]
        loop_length = struct.unpack_from('<I', data, lo+12)[0]
        loops.append({
            'type':  loop_type,
            'start': loop_start,
            'end':   loop_start + loop_length - 1,  # ulStart+ulLength-1 = inclusive end
        })

    gain_db = gain / 655360.0  # millibels → dB

    return {
        'root_note': unity_note,
        'fine_tune': fine_tune,   # cents, pass through directly
        'gain_db':   gain_db,
        'loops':     loops,
    }


def _parse_wlnk(data: bytes, off: int) -> dict:
    """Wave link: index into wave pool."""
    return {
        'flags':      struct.unpack_from('<H', data, off)[0],
        'phase_group':struct.unpack_from('<H', data, off+2)[0],
        'channel':    struct.unpack_from('<I', data, off+4)[0],
        'table_index':struct.unpack_from('<I', data, off+8)[0],
    }


def _parse_fmt(data: bytes, off: int) -> dict:
    """WAV fmt chunk."""
    return {
        'format':      struct.unpack_from('<H', data, off)[0],
        'channels':    struct.unpack_from('<H', data, off+2)[0],
        'sample_rate': struct.unpack_from('<I', data, off+4)[0],
        'bit_depth':   struct.unpack_from('<H', data, off+14)[0],
    }


def _parse_smpl(data: bytes, off: int) -> dict:
    """WAV smpl chunk (loop points)."""
    num_loops = struct.unpack_from('<I', data, off+28)[0]
    loops = []
    for li in range(num_loops):
        lo  = off + 36 + li * 24
        loops.append({
            'type':  struct.unpack_from('<I', data, lo+4)[0],
            'start': struct.unpack_from('<I', data, lo+8)[0],
            'end':   struct.unpack_from('<I', data, lo+12)[0],
        })
    return {'loops': loops}


# ---------------------------------------------------------------------------
# GIG-specific articulation: amp envelope (EG1), filter envelope (EG2), VCF
# ---------------------------------------------------------------------------
#
# Layout reverse-engineered from libgig 4.3.0 (gig.cpp, DimensionRegion ctor)
# and validated byte-for-byte against `gigdump` on a real corpus
# (maestro_concert_grand_v2.gig, Hammond organ .gig files).  The articulation
# lives in the '3ewa' chunk inside  region → LIST(3prg) → LIST(3ewl) → 3ewa.
# (The previous code looked for a non-existent '3ewg' chunk and so always fell
# back to default envelopes.)
#
# EG times use libgig's GIG_EXP_DECODE(x) = 1.000000008813822**x  (raw signed
# int32 → seconds).  EG sustain is a 0..1000 permille level.
#
# 3ewa byte offsets (from chunk-data start) used here:
#   [28] i32 EG1Attack   [32] i32 EG1Decay1  [38] u16 EG1Sustain  [40] i32 EG1Release
#   [52] i32 EG2Attack   [56] i32 EG2Decay1  [62] u16 EG2Sustain  [64] i32 EG2Release
#   [132] u8 vcf: bit7=VCFEnabled, low7=VCFCutoff
#   [134] u8 low7=VCFVelocityScale (velocity→cutoff, 0-127)
#   [136] u8 low7=VCFResonance        [139] u8 VCFType (0=LP,1=BP,2=HP,3=BR,4=LPturbo)
#   [137] u8 bit7=VCFKeyboardTracking (cutoff follows key)

def _gig_exp_decode(raw_i32: int) -> float:
    """libgig GIG_EXP_DECODE: raw signed int32 → seconds."""
    return 1.000000008813822 ** raw_i32


# gig vcf_type_t → XPM/model filter_type (see models.common VoiceLayer).
_GIG_VCF_TYPE = {0: 2, 4: 3, 2: 5, 1: 7, 3: 8}  # LP→LP24, LPturbo→LP48, HP→HP24, BP→BP24, BR→ContBP


def _decode_3ewa(d: bytes, o: int) -> dict:
    """Decode one '3ewa' chunk (data offset `o`) into amp keys + optional
    'filter' dict (present only when the VCF is enabled)."""
    i32 = lambda off: struct.unpack_from('<i', d, off)[0]
    u16 = lambda off: struct.unpack_from('<H', d, off)[0]
    out = {
        'attack':  max(0.0, _gig_exp_decode(i32(o + 28))),
        'decay':   max(0.0, _gig_exp_decode(i32(o + 32))),
        'sustain': min(1.0, u16(o + 38) / 1000.0),
        'release': max(0.0, _gig_exp_decode(i32(o + 40))),
    }
    vcf = d[o + 132]
    if vcf & 0x80:  # VCFEnabled
        out['filter'] = {
            'cutoff':    (vcf & 0x7f) / 127.0,
            'resonance': (d[o + 136] & 0x7f) / 127.0,
            'type':      _GIG_VCF_TYPE.get(d[o + 139], 2),
            # EOS has no separate EG2-to-cutoff depth; GigaStudio routes the
            # whole EG2 to the cutoff, so we map a full positive sweep.
            'env_amount':  1.0,
            'env_attack':  max(0.0, _gig_exp_decode(i32(o + 52))),
            'env_decay':   max(0.0, _gig_exp_decode(i32(o + 56))),
            'env_sustain': min(1.0, u16(o + 62) / 1000.0),
            'env_release': max(0.0, _gig_exp_decode(i32(o + 64))),
            # Velocity→cutoff (VCFVelocityScale, 0-127) and keyboard tracking.
            'vel_to_filter': (d[o + 134] & 0x7f) / 127.0,
            'keytrack':      1.0 if (d[o + 137] & 0x80) else 0.0,
        }
    return out


def _parse_3prg_envelope(walker: _RiffWalker) -> dict:
    """Extract amp envelope (EG1) and, when the VCF is enabled, the filter
    envelope (EG2) + cutoff/resonance/type from the Giga 3prg LIST.

    A 3prg holds one '3ewl' LIST per dimension region (velocity/key split),
    each with a '3ewa' articulation chunk.  Amp env is taken from the first
    dimension region; the filter is taken from the first region that actually
    enables the VCF (the default/first region is frequently VCF-off).
    Returns the amp keys plus an optional 'filter' dict, or safe defaults."""
    defaults = {'attack': 0.001, 'decay': 0.3, 'sustain': 0.8, 'release': 0.5}
    try:
        d = walker.data
        result = None
        for fc, off, sz in walker.chunks():
            if fc != 'LIST' or d[off:off + 4] != b'3ewl':
                continue
            ewl = _RiffWalker(d, off + 4, sz - 4)
            ea = ewl.find('3ewa')
            if not ea or ea[1] < 140:
                continue
            dec = _decode_3ewa(d, ea[0])
            if result is None:
                result = dec                       # amp env: first region
            if 'filter' not in result and 'filter' in dec:
                result['filter'] = dec['filter']   # filter: first VCF-on region
                break
        return result if result is not None else defaults
    except Exception:
        return defaults


# ---------------------------------------------------------------------------
# Wave pool extractor
# ---------------------------------------------------------------------------

def _extract_waves(riff: _RiffWalker, max_samples: int = 512
                   ) -> List[Optional[SampleData]]:
    """
    Extract all samples from the wvpl (wave pool) LIST.
    Returns list indexed by wave table position.
    """
    wvpl = riff.find_list('wvpl')
    if wvpl is None:
        return []

    waves = []
    for fc, off, sz in wvpl.chunks():
        if fc != 'LIST':
            continue
        if len(riff.data) <= off or riff.data[off:off+4] != b'wave':
            continue
        if len(waves) >= max_samples:
            break

        wave_walker = _RiffWalker(riff.data, off+4, sz-4)

        # fmt chunk
        fmt_r = wave_walker.find('fmt ')
        if not fmt_r:
            waves.append(None)
            continue
        fmt_off, _ = fmt_r
        fmt = _parse_fmt(riff.data, fmt_off)

        # data chunk
        dat_r = wave_walker.find('data')
        if not dat_r:
            waves.append(None)
            continue
        dat_off, dat_sz = dat_r
        raw_data = riff.data[dat_off:dat_off + dat_sz]

        # Optional: wsmp for root note / loop (at wave level)
        wsmp_info = {'root_note': 60, 'fine_tune': 0, 'gain_db': 0.0, 'loops': []}
        wsmp_r = wave_walker.find('wsmp')
        if wsmp_r:
            wsmp_info = _parse_wsmp(riff.data, wsmp_r[0], wsmp_r[1])

        # Optional: smpl chunk for loops
        smpl_r = wave_walker.find('smpl')
        loops = wsmp_info['loops']
        if smpl_r and not loops:
            smpl_info = _parse_smpl(riff.data, smpl_r[0])
            loops = smpl_info['loops']

        # Name from INFO
        name = f"wave{len(waves):04d}"
        info = wave_walker.find_list('INFO')
        if info:
            inam = info.find('INAM')
            if inam:
                name = _safe_name(
                    riff.data[inam[0]:inam[0]+inam[1]].split(b'\x00')[0]
                    .decode('ascii', errors='replace'))

        # Convert to 16-bit mono
        channels  = max(1, min(2, fmt['channels']))
        bit_depth = fmt['bit_depth']
        if bit_depth not in (8, 16, 24):
            waves.append(None)
            continue

        if bit_depth == 8:
            # CR-16: unsigned-8 → signed-16 is `(b-128)*256`, i.e. low byte 0 and
            # high byte = the sign-flipped sample.  Bulk translate instead of a
            # per-sample `struct.pack_into` loop (byte-identical).
            out = bytearray(len(raw_data) * 2)
            out[1::2] = raw_data.translate(_FLIP_SIGN8)
            raw_data = bytes(out)
            bit_depth = 16

        elif bit_depth == 24:
            # CR-16: 24-bit-LE-signed >> 8 equals the signed-16 value formed by a
            # frame's top two bytes, so the conversion is just "keep bytes [1,2],
            # drop the low byte" — a bulk slice (~200× faster, byte-identical).
            n = len(raw_data) // 3
            out = bytearray(n * 2)
            out[0::2] = raw_data[1::3][:n]
            out[1::2] = raw_data[2::3][:n]
            raw_data = bytes(out)
            bit_depth = 16

        if channels == 2:
            # E4B supports only mono samples; downmix L+R to mono.
            arr = array.array('h', raw_data)
            n   = len(arr) // 2
            mono = array.array('h', ((arr[i*2] + arr[i*2+1]) >> 1 for i in range(n)))
            raw_data = mono.tobytes()
            channels = 1

        loop_type  = LoopType.NO_LOOP
        loop_start = 0
        loop_end   = 0
        if loops:
            l0 = loops[0]
            loop_type  = LoopType.ALTERNATING if l0['type'] == 1 else LoopType.FORWARD
            loop_start = l0['start']
            loop_end   = l0['end']

        sd = SampleData(
            name        = name,
            data        = raw_data,
            sample_rate = fmt['sample_rate'],
            channels    = channels,
            bit_depth   = 16,
            root_note   = min(127, wsmp_info['root_note']),
            fine_tune   = wsmp_info['fine_tune'],
            loop_type   = loop_type,
            loop_start  = loop_start,
            loop_end    = loop_end,
        )
        waves.append(sd)

    return waves


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_gig(gig_path: str, max_instruments: int = 32,
              max_samples: int = 512) -> Bank:
    """
    Parse a GigaSampler/GigaStudio .gig file.

    Args:
        gig_path:        Path to the .gig file
        max_instruments: Max instruments to import (default 32)
        max_samples:     Max samples to extract (default 512)

    Returns:
        Bank with one Preset per GIG instrument.
    """
    p = Path(gig_path).resolve()
    print(f"Parsing GIG: {p.name}")
    data = p.read_bytes()

    if data[:4] != b'RIFF' or data[8:12] != b'DLS ':
        raise ValueError(f"Not a valid GIG/DLS file: {p.name}")

    riff = _RiffWalker(data, 12, len(data) - 12)

    # Extract wave pool first
    print(f"  Extracting wave pool...")
    waves = _extract_waves(riff, max_samples)
    print(f"  Found {len(waves)} waves")

    bank = Bank(name=_safe_name(p.stem))

    # Instrument list
    lins = riff.find_list('lins')
    if lins is None:
        print("  [WARN] No instrument list found")
        return bank

    inst_count = 0
    for fc, off, sz in lins.chunks():
        if fc != 'LIST':
            continue
        if data[off:off+4] != b'ins ':
            continue
        if inst_count >= max_instruments:
            break

        ins_walker = _RiffWalker(data, off+4, sz-4)

        # insh — instrument header
        insh_r = ins_walker.find('insh')
        if not insh_r:
            continue
        insh_off, _ = insh_r
        n_regions = struct.unpack_from('<I', data, insh_off)[0]
        bank_num  = struct.unpack_from('<I', data, insh_off+4)[0]
        prog_num  = struct.unpack_from('<I', data, insh_off+8)[0] & 0x7F

        # Instrument name from INFO
        inst_name = f"Inst{inst_count:03d}"
        info = ins_walker.find_list('INFO')
        if info:
            inam = info.find('INAM')
            if inam:
                inst_name = _safe_name(
                    data[inam[0]:inam[0]+inam[1]].split(b'\x00')[0]
                    .decode('ascii', errors='replace'))

        print(f"  Instrument: '{inst_name}' ({n_regions} regions)")

        preset = Preset(name=inst_name, program_number=prog_num)
        voice  = VoiceLayer()

        # lrgn — region list
        lrgn = ins_walker.find_list('lrgn')
        if lrgn:
            for rfc, roff, rsz in lrgn.chunks():
                if rfc != 'LIST':
                    continue
                if data[roff:roff+4] not in (b'rgn ', b'rgn2'):
                    continue

                rgn_walker = _RiffWalker(data, roff+4, rsz-4)

                # rgnh
                rgnh_r = rgn_walker.find('rgnh')
                if not rgnh_r:
                    continue
                rgn = _parse_rgnh(data, rgnh_r[0])

                # wsmp
                wsmp_info = {'root_note': 60, 'fine_tune': 0,
                             'gain_db': 0.0, 'loops': []}
                wsmp_r = rgn_walker.find('wsmp')
                if wsmp_r:
                    wsmp_info = _parse_wsmp(data, wsmp_r[0], wsmp_r[1])

                # wlnk
                wlnk_r = rgn_walker.find('wlnk')
                if not wlnk_r:
                    continue
                wlnk = _parse_wlnk(data, wlnk_r[0])
                wave_idx = wlnk['table_index']

                if wave_idx >= len(waves) or waves[wave_idx] is None:
                    continue

                sd = waves[wave_idx]

                # Apply region-level loop override
                if wsmp_info['loops']:
                    l0 = wsmp_info['loops'][0]
                    sd.loop_type  = (LoopType.ALTERNATING if l0['type'] == 1
                                     else LoopType.FORWARD)
                    sd.loop_start = l0['start']
                    sd.loop_end   = l0['end']

                if sd.name not in {s.name for s in bank.samples}:
                    bank.samples.append(sd)

                # 3prg — Giga articulation (envelope)
                env = {'attack': 0.001, 'decay': 0.3,
                       'sustain': 0.8, 'release': 0.5}
                prg_r = rgn_walker.find_list('3prg')
                if prg_r:
                    env = _parse_3prg_envelope(prg_r)

                root = wsmp_info['root_note']
                if root == 0 or root > 127:
                    root = sd.root_note

                vol_db = wsmp_info['gain_db']

                zone = ZoneMapping(
                    sample_name = sd.name,
                    lo_key      = min(127, rgn['key_lo']),
                    hi_key      = min(127, rgn['key_hi']),
                    lo_vel      = min(127, rgn['vel_lo']),
                    hi_vel      = min(127, rgn['vel_hi']),
                    root_key    = min(127, root),
                    fine_tune   = wsmp_info['fine_tune'],
                    volume      = vol_db,
                )
                voice.zones.append(zone)

                # Amp envelope (EG1): take from the first region.
                if len(voice.zones) == 1:
                    voice.env_attack  = env['attack']
                    voice.env_decay   = env['decay']
                    voice.env_sustain = env['sustain']
                    voice.env_release = env['release']
                # Filter envelope (EG2) + VCF: take from the first region that
                # actually enables the filter (the first region is often VCF-off).
                flt = env.get('filter')
                if flt and voice.filter_env_amount == 0.0:
                    voice.filter_type        = flt['type']
                    voice.filter_cutoff      = flt['cutoff']
                    voice.filter_resonance   = flt['resonance']
                    voice.filter_env_amount  = flt['env_amount']
                    voice.filter_env_attack  = flt['env_attack']
                    voice.filter_env_decay   = flt['env_decay']
                    voice.filter_env_sustain = flt['env_sustain']
                    voice.filter_env_release = flt['env_release']
                    voice.velocity_to_filter = flt['vel_to_filter']
                    voice.filter_keytrack    = flt['keytrack']

        if voice.zones:
            preset.voices.append(voice)
            bank.presets.append(preset)
            inst_count += 1

    print(f"  Loaded {len(bank.presets)} instrument(s), "
          f"{len(bank.samples)} sample(s)")
    return bank
