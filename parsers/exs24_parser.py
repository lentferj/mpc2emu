# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# Independent reimplementation. EXS24 binary layout informed by:
#   exs2sfz (GPL-2.0), https://github.com/mqnc/exs2sfz
#   ConvertWithMoss (LGPLv3), Jürgen Moßgraber,
#     https://github.com/git-moss/ConvertWithMoss
# No source code was copied from either project.  The TYPE_PARAMS block layout,
# parameter IDs (FILTER1, ENV2) and filter/envelope value conversions follow
# ConvertWithMoss (EXS24Parameters / EXS24Detector), validated across a large
# local .exs corpus.
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
Logic EXS24 / EXS24 mkII Parser
---------------------------------
EXS24 is a binary format used by Logic Pro and MainStage.
File extension: .exs

Binary structure (little-endian).  A legacy PowerPC big-endian variant exists
(Logic 7 and earlier) but is NOT supported: its on-disk magic bytes are
identical to the little-endian magic (00 00 00 01), so the two cannot be told
apart by magic alone and the LE interpretation always wins.  Only little-endian
classic + v1.1 files are handled.

  File Header (84 bytes):
    0    4    Magic: 0x01000000 (LE).  (PPC BE 0x00000001 has the same bytes.)
    4    4    File type: 0x01000000 (instrument)
    8    4    Number of zones (map entries)
    12   4    Number of groups
    16   4    Number of samples
    20   64   Instrument name (null-padded)

  Zone records (start at offset 84 + header_size, variable):
    Each zone = 104 bytes
    0    4    chunk type (0x01000100 LE or 0x00010001 BE = zone)
    4    4    chunk size
    8    4    zone index
    12   4    flags
    16   1    coarse tune (semitones, signed)
    17   1    fine tune (cents, signed)
    18   1    pan (-64..+63)
    19   1    volume (0..127)
    20   1    flags2
    21   1    sample_select_group
    22   2    key_lo
    24   2    key_hi
    26   2    vel_lo
    28   2    vel_hi
    30   2    key_root
    32   4    loop_start
    36   4    loop_end
    40   1    loop_on
    41   3    padding
    44   4    sample_index
    48   56   zone name (null-padded)

  Group records (136 bytes each):
    0    4    chunk type
    4    4    chunk size
    8    4    group index
    12   4    flags
    16   4    voices
    20   1    envelope_attack (0..127)
    21   1    envelope_decay (0..127)
    22   1    envelope_sustain (0..127)
    23   1    envelope_release (0..127)
    ...  ...  more params
    52   84   group name

  Sample records (196 bytes each):
    0    4    chunk type
    4    4    chunk size
    8    4    sample_index
    12   4    flags
    16   4    sample_length (frames)
    20   4    sample_rate
    24   2    bit_depth
    26   2    channels
    28   4    loop_start
    32   4    loop_end
    36   4    loop_mode (0=off, 1=fwd, 2=bidir)
    40   4    root_note (MIDI)
    44   4    root_fine (cents)
    48   148  file_path (null-padded)

References:
  - EXS24 reverse engineering by Redmatica / Chicken Systems
  - exs2sfz source (GPL) - https://github.com/mqnc/exs2sfz
  - ConvertWithMoss EXS source (LGPLv3)
"""

import struct
import os
import math
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType,
    hz_to_e4b_cutoff, E4B_CUTOFF_MAX_HZ
)
from parsers.xpm_parser import load_wav, _safe_name


# Chunk type identifiers (classic little-endian)
CHUNK_ZONE   = 0x01000100
CHUNK_GROUP  = 0x02000100
CHUNK_SAMPLE = 0x03000100

HEADER_MAGIC_LE = 0x01000000

# Logic 10.4+ "v1.1" format — chunks have a 76-byte tail after declared data
HEADER_MAGIC_LE_V11 = 0x00000101
CHUNK_ZONE_V11      = 0x01000101
CHUNK_GROUP_V11     = 0x02000101
CHUNK_SAMPLE_V11    = 0x03000101
CHUNK_PARAMS_V11    = 0x04000101
_V11_TAIL           = 76   # extra bytes appended to every chunk in v1.1
# v1.1 block: 84-byte header (8 type/size + index/flags + 'TBOS' magic + name),
# then the content — for a PARAMS block this is the parameter table.
_V11_CONTENT_OFF    = 84
# Some Logic Pro X exports OR a high flag bit (0x40000000) into the file magic
# AND into every chunk type (so the magic reads 0x40000101 and zones read
# 0x41000101, samples 0x43000101, …).  The on-disk layout is byte-for-byte the
# normal v1.1 structure — only the type fields carry the extra bit — so we mask
# it off before dispatching and before every chunk-type comparison.  (Observed
# across the Samples-From-Mars / Drums-From-Mars EXS packs, 2026-06-12.)
_V11_TYPE_FLAG      = 0x40000000

# EXS24 FILTER1 + ENV2 parameter IDs (ConvertWithMoss EXS24Parameters), and the
# FILTER1_TYPE → model filter_type map (ConvertWithMoss EXS24Detector):
#   0=LP 24dB, 1=LP 18dB, 2=LP 12dB, 3=LP 6dB, 4=HP 12dB, 5=BP 12dB.
_EXS_FILTER_TOGGLE = 44
_EXS_FILTER_TYPE   = 243
_EXS_FILTER_CUTOFF = 30
_EXS_FILTER_RESO   = 29
_EXS_ENV2_ATTACK   = 77
_EXS_ENV2_DECAY    = 78
_EXS_ENV2_SUSTAIN  = 79
_EXS_ENV2_RELEASE  = 80
_EXS_FILTER_KEYTRACK = 46   # 0x2e; scaling unverified (CWM defines but never uses it)
_EXS_FILTER_TYPE_MAP = {0: 2, 1: 2, 2: 1, 3: 1, 4: 4, 5: 6}  # → LP24/LP24/LP12/LP12/HP12/BP12


def _looks_like_filename(b: bytes) -> bool:
    """Heuristic: the bytes are a plausible filename/path (mostly printable
    ASCII), used to tell a real EXS sample path from control-byte garbage."""
    if not b or len(b) < 3:
        return False
    printable = sum(1 for c in b if 32 <= c < 127)
    return printable >= len(b) * 0.8


def _exs_env_to_seconds(val: int) -> float:
    """EXS24 envelope time param (0-127) → seconds, linear (max 10 s).
    Matches ConvertWithMoss EXS24Detector (value / 127 * 10).  CR-14: this is
    now the single converter for BOTH the amp and filter envelopes (the old
    quadratic `_env_byte_to_seconds` for the amp envelope is gone — the linear
    CWM curve is the adopted EXS reference, see _exs_cutoff_to_e4b)."""
    return max(0.0, min(127, val)) / 127.0 * 10.0


def _exs_cutoff_to_e4b(value: int) -> float:
    """EXS24 FILTER1_CUTOFF (0-1000) → E4B exponential cutoff position (0-1).

    The value→frequency mapping follows ConvertWithMoss's `EXS24Detector`
    (Jürgen Moßgraber, LGPL-3.0): a LINEAR fraction of MAX_FREQUENCY (20 kHz),
    `cutoff_Hz = value/1000 × 20 kHz`.  Adopted as the reference EXS cutoff
    interpretation 2026-06-09 (ConvertWithMoss is the only EXS reader that maps
    the cutoff at all — Bliss / EXS2DS / Tonverk-elmconv drop the filter).  We
    then place that frequency on the E4B's exponential cutoff scale (the shared
    `hz_to_e4b_cutoff`, CR-12).  (We previously used value/1000 directly as the
    exponential position, which made every EXS filter far too dark.)"""
    return hz_to_e4b_cutoff((max(0, value) / 1000.0) * E4B_CUTOFF_MAX_HZ)


def _parse_exs_params_v11(data: bytes, content_off: int) -> dict:
    """Parse the EXS24 v1.1 parameter block (legacy section, IDs ≤ 0xFF).

    Layout (ConvertWithMoss EXS24Parameters): u32 count, then `count` 1-byte
    IDs, then `count` signed-16 values (value[i] at ids_end + 2*i)."""
    if content_off + 4 > len(data):
        return {}
    count = struct.unpack_from('<I', data, content_off)[0]
    if not (1 <= count <= 300) or content_off + 4 + count * 3 > len(data):
        return {}
    ids_off = content_off + 4
    val_off = ids_off + count
    out = {}
    for i in range(count):
        pid = data[ids_off + i]
        if pid:
            out[pid] = struct.unpack_from('<h', data, val_off + 2 * i)[0]
    return out


def _apply_exs_filter(voice: VoiceLayer, params: dict) -> None:
    """Apply EXS24 FILTER1 (cutoff/resonance/type) and, when ENV2 has a shape,
    the filter envelope to a voice — only when the filter is switched on."""
    if not params or params.get(_EXS_FILTER_TOGGLE) != 1:
        return
    voice.filter_type      = _EXS_FILTER_TYPE_MAP.get(params.get(_EXS_FILTER_TYPE, 0), 2)
    voice.filter_cutoff    = _exs_cutoff_to_e4b(params.get(_EXS_FILTER_CUTOFF, 1000))
    voice.filter_resonance = max(0.0, min(1.0, params.get(_EXS_FILTER_RESO, 0) / 1000.0))
    # Filter keytrack (FILTER1_KEYTRACK) — scaling unverified (no corpus example
    # and CWM never applies it); assume 0-1000 like cutoff. No EXS velocity→filter.
    kt = params.get(_EXS_FILTER_KEYTRACK, 0)
    if kt:
        voice.filter_keytrack = max(-1.0, min(1.0, kt / 1000.0))
    atk = params.get(_EXS_ENV2_ATTACK, 0)
    dec = params.get(_EXS_ENV2_DECAY, 0)
    rel = params.get(_EXS_ENV2_RELEASE, 0)
    if atk or dec or rel:        # ENV2 actually moves the cutoff
        # EXS routes ENV2 to the cutoff; EOS has no separate env→cutoff depth, so
        # a full positive sweep is used (approximation, see RESOLUTION_NOTES §17).
        voice.filter_env_amount  = 1.0
        voice.filter_env_attack  = _exs_env_to_seconds(atk)
        voice.filter_env_decay   = _exs_env_to_seconds(dec)
        voice.filter_env_sustain = max(0.0, min(1.0, params.get(_EXS_ENV2_SUSTAIN, 127) / 127.0))
        voice.filter_env_release = _exs_env_to_seconds(rel)


def _parse_exs_v11(p: Path, data: bytes,
                   sample_dirs: Optional[List[str]] = None) -> Bank:
    """Parse Logic EXS24 v1.1 (magic 0x00000101, Logic 10.4+).

    Layout changes vs classic:
      - 80-byte file header (field at +4 = header_size)
      - Every chunk: stride = 8 + declared_size + 76 (tail bytes)
      - Zone name at chunk+16 (4-byte 'TBOS' tag + 56-byte name)
      - Zone key/vel fields shifted to chunk+76+N
      - Sample clean filename at chunk+420
      - Zone-to-sample: positional (zone[i] -> sample[i], ordered by index)
    """
    inst_name = _safe_name(p.stem)
    print(f"  EXS24 v1.1: '{inst_name}'")

    bank   = Bank(name=inst_name)
    preset = Preset(name=inst_name)

    header_size = struct.unpack_from('<I', data, 4)[0]

    zones_raw:   List[dict] = []
    samples_raw: List[dict] = []
    group_names: List[str]  = []   # GROUP_V11 names, in file order

    zone_pos = 0
    params: dict = {}
    offset = header_size
    while offset + 8 <= len(data):
        chunk_type = struct.unpack_from('<I', data, offset)[0] & ~_V11_TYPE_FLAG
        chunk_size = struct.unpack_from('<I', data, offset + 4)[0]
        stride     = 8 + chunk_size + _V11_TAIL

        if chunk_type == CHUNK_ZONE_V11:
            z_idx    = struct.unpack_from('<I', data, offset + 8)[0]
            name     = data[offset+20:offset+76].split(b'\x00')[0].decode('utf-8', errors='replace')
            ks       = offset + 76
            # Field offsets corrected 2026-06-08.  Previously key_lo/key_hi/
            # key_root were read from ks+9/14/15 — wrong: it collapsed full-range
            # zones to one key and set root=127 (→ inaudible on hardware).  The
            # correct layout (binary cross-checked against zone names) is:
            #   ks+9  = root_key,  ks+14 = key_lo,  ks+15 = key_hi.
            # See TODO.md / RESOLUTION_NOTES.md §6.
            root_key   = data[ks + 9]
            key_lo     = data[ks + 14]                # 0 = keyboard bottom (valid)
            key_hi     = data[ks + 15] or root_key    # 0 = unset → fall back to root
            fine_cents = struct.unpack_from('b', data, ks + 12)[0]   # signed cents
            coarse_st  = struct.unpack_from('b', data, ks + 13)[0]   # signed semitones
            vel_hi     = data[ks + 18]
            group_byte = data[ks + 11]                # reference into GROUP chunks
            zones_raw.append({
                'index': z_idx, 'name': name, 'pos': zone_pos,
                'key_lo': key_lo, 'key_hi': key_hi, 'key_root': root_key,
                'vel_lo': 0, 'vel_hi': vel_hi,
                'coarse': coarse_st, 'fine': fine_cents,
                'group_byte': group_byte,
            })
            zone_pos += 1

        elif chunk_type == CHUNK_GROUP_V11:
            gname = data[offset+20:offset+76].split(b'\x00')[0].decode('utf-8', errors='replace')
            group_names.append(gname)

        elif chunk_type == CHUNK_SAMPLE_V11:
            # The "clean" path normally lives at +420, but some smaller v1.1
            # chunks (e.g. drum kits) have no path there — it reads as control-
            # byte garbage — and keep just the filename at the +20 name field.
            # Use +420 when it looks like a real filename, else fall back to +20.
            fn_raw = b''
            if offset + 420 + 256 <= len(data):
                fn_raw = data[offset+420:offset+420+256].split(b'\x00')[0]
            if not _looks_like_filename(fn_raw):
                alt = data[offset+20:offset+20+64].split(b'\x00')[0]
                if _looks_like_filename(alt):
                    fn_raw = alt
            try:
                filename = fn_raw.decode('utf-8')
            except Exception:
                filename = fn_raw.decode('latin-1', errors='replace')
            samples_raw.append({'filename': filename})

        elif chunk_type == CHUNK_PARAMS_V11:
            params = _parse_exs_params_v11(data, offset + _V11_CONTENT_OFF)

        if stride < 8:
            break
        offset += stride

    print(f"  Found {len(zones_raw)} zone(s), {len(samples_raw)} sample(s)")
    zones_raw.sort(key=lambda z: z['index'])

    # ── Stereo de-duplication (GROUP_V11) ────────────────────────────────────
    # Logic stores L/R stereo as two groups ('Name_L' / 'Name_R'), each a
    # complete keyboard map.  Including both doubles E4XT polyphony and sample
    # RAM with no audible benefit, so drop the _R group's zones (and their
    # samples) when an _L partner of the same base name exists.
    #
    # The zone group-reference byte (ks+11) is NOT a 0-based index: distinct
    # values map to groups in file order when sorted ascending (empirically
    # {100→group0, 156→group1}, verified corpus-wide 2026-06-08 — only true
    # _L/_R pairs are touched, zero false positives).  In these instruments
    # zones and samples share the same file-order position (zone[i] ↔ sample[i]),
    # so we filter both lists in lockstep and leave the pairing loop unchanged.
    if group_names:
        def _stereo_base(n: str) -> str:
            return n[:-2] if n.endswith(('_L', '_R', '_l', '_r')) else n
        l_bases     = {_stereo_base(n) for n in group_names if n.endswith(('_L', '_l'))}
        drop_groups = {i for i, n in enumerate(group_names)
                       if n.endswith(('_R', '_r')) and _stereo_base(n) in l_bases}
        distinct_gb = sorted({z['group_byte'] for z in zones_raw})
        if drop_groups and len(distinct_gb) == len(group_names):
            gb_to_group    = {gb: i for i, gb in enumerate(distinct_gb)}
            drop_positions = {z['pos'] for z in zones_raw
                              if gb_to_group.get(z['group_byte']) in drop_groups}
            if drop_positions:
                before      = len(zones_raw)
                zones_raw   = [z for z in zones_raw if z['pos'] not in drop_positions]
                samples_raw = [s for i, s in enumerate(samples_raw)
                               if i not in drop_positions]
                print(f"  Stereo de-dup: dropped {len(drop_positions)} _R zone(s) "
                      f"({before}→{len(zones_raw)})")
        elif drop_groups:
            print(f"  [WARN] GROUP_V11 group mapping ambiguous "
                  f"({len(distinct_gb)} ref values vs {len(group_names)} groups); "
                  f"keeping all zones")

    search_dirs = [p.parent]
    if sample_dirs:
        search_dirs += [Path(d) for d in sample_dirs]
    search_dirs += [
        p.parent / 'Samples' / p.stem,
        p.parent / 'Samples',
        p.parent.parent / 'Samples' / p.stem,
        p.parent.parent / 'Samples',
        p.parent / 'samples',
    ]

    # Lazy fallback index: many sample packs keep WAV/AIFF in a sibling audio
    # folder several levels from the .exs (e.g. ".../Pack/WAV/<instr>/" while the
    # .exs is ".../Pack/Logic EXS/<bank>/<cat>/").  On the first miss, scan
    # audio-named folders under each ancestor (bounded) and index by basename.
    # A second index keyed by extension-less stem lets a reference to one audio
    # format resolve to a parallel copy in another (e.g. several Logic packs ship
    # the .exs pointing at .aif while a sibling WAV/ folder holds the same stems
    # as .wav — load_wav handles both WAV and AIFF).
    _audio_index: dict = {}
    _stem_index:  dict = {}
    _index_built = [False]
    # Match audio-ish folder names by substring (covers WAV/Audio/Samples but
    # also pack-specific names like "XS_SINGLE_SOUNDS", "XS_DRUM_HITS").
    _AUDIO_KEYWORDS = ('wav', 'aif', 'audio', 'sample', 'sampler', 'sound',
                       'loop', 'hit', 'drum', 'oneshot', 'one-shot', 'kit')

    def _find_indexed(name: str):
        if not _index_built[0]:
            _index_built[0] = True
            anc, ancestors = p.parent, []
            for _ in range(8):            # deep pack trees (Drums-From-Mars etc.)
                ancestors.append(anc)
                if anc.parent == anc:
                    break
                anc = anc.parent
            count = 0
            for root in ancestors:        # nearest ancestor first
                try:
                    subs = [d for d in root.iterdir() if d.is_dir()
                            and any(k in d.name.lower() for k in _AUDIO_KEYWORDS)]
                except OSError:
                    continue
                for sub in subs:
                    try:
                        for f in sub.rglob('*'):
                            if f.suffix.lower() in ('.wav', '.aif', '.aiff'):
                                _audio_index.setdefault(f.name.lower(), str(f))
                                # Prefer a loadable .wav for the stem fallback so a
                                # .aif reference lands on its WAV twin, not the AIFF.
                                key = f.stem.lower()
                                if key not in _stem_index or f.suffix.lower() == '.wav':
                                    _stem_index[key] = str(f)
                                count += 1
                                if count > 80000:    # hard cap → bounded scan
                                    break
                    except OSError:
                        pass
                    if count > 80000:
                        break
                if count > 80000:
                    break
        # Prefer .wav over .aif when both exist (same decoded result, but WAV
        # avoids parsing overhead): exact .wav match → same-stem .wav twin →
        # exact AIFF match → stem AIFF fallback (load_wav handles both).
        exact    = _audio_index.get(name.lower())
        if exact and exact.lower().endswith('.wav'):
            return exact
        stem_hit = _stem_index.get(Path(name).stem.lower())
        if stem_hit and stem_hit.lower().endswith('.wav'):
            return stem_hit
        return exact or stem_hit

    voice        = VoiceLayer()
    sample_cache: Dict[str, SampleData] = {}

    for i, z in enumerate(zones_raw):
        if i >= len(samples_raw):
            break
        filename = samples_raw[i]['filename']
        if not filename:
            continue

        file_path = Path(filename.replace('\\', '/'))
        # Key on the FULL stem.  _safe_name truncates to 16 by default, which
        # collapsed every sample of a long-common-prefix multisample (e.g.
        # "DX100 Classic Bass-C0-…", "…-C#0-…" all → "DX100 Classic Ba") into one
        # cache entry, so 36 keyboard zones played a single sample.  E4B maps
        # zones by sample index (not name), so distinct full names are safe here;
        # the 16-char limit + uniqueness is applied later (bank_splitter/writer).
        sname     = _safe_name(file_path.stem, maxlen=255)

        if sname in sample_cache:
            sd = sample_cache[sname]
        else:
            sd = None
            for d in search_dirs:
                for cand in (d / file_path.name, d / file_path):
                    if Path(cand).exists():
                        sd = load_wav(str(cand), sname)
                        if sd:
                            sd.root_note = z['key_root']
                            sd.fine_tune = z['fine']
                            sample_cache[sname] = sd
                            bank.samples.append(sd)
                            print(f"  Loaded: {sd.name} ({sd.sample_rate} Hz)")
                        break
                if sd:
                    break
            if not sd:                          # fallback: ancestor audio index
                hit = _find_indexed(file_path.name)
                if hit:
                    sd = load_wav(hit, sname)
                    if sd:
                        sd.root_note = z['key_root']
                        sd.fine_tune = z['fine']
                        sample_cache[sname] = sd
                        bank.samples.append(sd)
                        print(f"  Loaded (indexed): {sd.name} ({sd.sample_rate} Hz)")
            if not sd:
                print(f"  [WARN] Sample not found: {file_path.name}")
                continue

        zone = ZoneMapping(
            sample_name = sd.name,
            lo_key      = min(127, z['key_lo']),
            hi_key      = min(127, z['key_hi']),
            lo_vel      = z['vel_lo'],
            hi_vel      = min(127, z['vel_hi']),
            root_key    = min(127, z['key_root']),
            fine_tune   = z['fine'],
            transpose   = z['coarse'],
        )
        voice.zones.append(zone)

    if voice.zones:
        _apply_exs_filter(voice, params)
        preset.voices.append(voice)
        print(f"  Preset '{inst_name}': {len(voice.zones)} zone(s)")

    if preset.voices:
        bank.presets.append(preset)
    return bank


def parse_exs24(exs_path: str,
                sample_dirs: Optional[List[str]] = None) -> Bank:
    """
    Parse a Logic EXS24 instrument file.

    Args:
        exs_path:    Path to the .exs file
        sample_dirs: Additional directories to search for samples.
                     The .exs file's directory is always searched first.

    Returns:
        Bank with one Preset.
    """
    p = Path(exs_path).resolve()
    print(f"Parsing EXS24: {p.name}")
    data = p.read_bytes()

    if len(data) < 84:
        raise ValueError(f"File too small to be EXS24: {p.name}")

    # Detect format from the little-endian magic.  (A legacy PowerPC big-endian
    # variant shares the same on-disk magic bytes, so it cannot be detected here
    # and is not supported — see the module docstring.)
    magic_le = struct.unpack_from('<I', data, 0)[0]

    if (magic_le & ~_V11_TYPE_FLAG) == HEADER_MAGIC_LE_V11:
        return _parse_exs_v11(p, data, sample_dirs)
    elif magic_le == HEADER_MAGIC_LE:
        fmt = '<'
    else:
        raise ValueError(f"Not a valid EXS24 file (magic: 0x{magic_le:08X})")

    def u32(off): return struct.unpack_from(fmt+'I', data, off)[0]
    def i32(off): return struct.unpack_from(fmt+'i', data, off)[0]
    def u16(off): return struct.unpack_from(fmt+'H', data, off)[0]
    def i16(off): return struct.unpack_from(fmt+'h', data, off)[0]
    def u8(off):  return data[off]
    def i8(off):  return struct.unpack_from('b', data, off)[0]
    def cstr(off, n): return data[off:off+n].split(b'\x00')[0].decode(
        'utf-8', errors='replace')

    n_zones   = u32(8)
    n_groups  = u32(12)
    n_samples = u32(16)
    inst_name = _safe_name(cstr(20, 64))

    print(f"  EXS24: '{inst_name}', {n_zones} zones, "
          f"{n_groups} groups, {n_samples} samples")

    bank   = Bank(name=inst_name)
    preset = Preset(name=inst_name)

    # --- Parse all chunks after the 84-byte header ---
    zones_raw:   List[dict] = []
    groups_raw:  List[dict] = []
    samples_raw: List[dict] = []

    offset = 84
    while offset + 8 <= len(data):
        chunk_type = u32(offset)
        chunk_size = u32(offset + 4)

        if chunk_type == CHUNK_ZONE:
            if offset + 104 > len(data):
                break
            z = {
                'index':      u32(offset + 8),
                'coarse':     i8(offset + 16),
                'fine':       i8(offset + 17),
                'pan':        i8(offset + 18),
                'volume':     u8(offset + 19),
                'key_lo':     u16(offset + 22),
                'key_hi':     u16(offset + 24),
                'vel_lo':     u16(offset + 26),
                'vel_hi':     u16(offset + 28),
                'key_root':   u16(offset + 30),
                'loop_start': u32(offset + 32),
                'loop_end':   u32(offset + 36),
                'loop_on':    u8(offset + 40),
                'sample_idx': u32(offset + 44),
                'name':       cstr(offset + 48, 56),
            }
            zones_raw.append(z)

        elif chunk_type == CHUNK_GROUP:
            base = offset + 8  # chunk data starts after 8-byte header
            if base + 24 > len(data):
                break
            name_offset = base + 44
            name_len = min(84, len(data) - name_offset)
            g = {
                'index':   u32(base + 0),
                'flags':   u32(base + 4),
                'attack':  u8(base + 12),
                'decay':   u8(base + 13),
                'sustain': u8(base + 14),
                'release': u8(base + 15),
                'name':    cstr(name_offset, name_len) if name_len > 0 else '',
            }
            groups_raw.append(g)

        elif chunk_type == CHUNK_SAMPLE:
            base = offset + 8  # chunk data starts after 8-byte header
            if base + 48 > len(data):
                break
            path_offset = base + 40
            path_len    = min(148, len(data) - path_offset)
            raw_path    = data[path_offset:path_offset + path_len]
            try:
                file_path_str = raw_path.split(b'\x00')[0].decode('utf-8')
            except Exception:
                file_path_str = raw_path.split(b'\x00')[0].decode('latin-1', errors='replace')
            s = {
                'index':       u32(base + 0),
                'length':      u32(base + 8),
                'sample_rate': u32(base + 12),
                'bit_depth':   u16(base + 16),
                'channels':    u16(base + 18),
                'loop_start':  u32(base + 20),
                'loop_end':    u32(base + 24),
                'loop_mode':   u32(base + 28),
                'root_note':   u32(base + 32),
                'root_fine':   i32(base + 36),
                'file_path':   file_path_str,
            }
            samples_raw.append(s)

        offset += 8 + chunk_size

    # --- Build sample index map ---
    sample_index_map: Dict[int, SampleData] = {}
    search_dirs = [p.parent]
    if sample_dirs:
        search_dirs += [Path(d) for d in sample_dirs]
    # Also check common Logic sample locations relative to .exs
    search_dirs += [
        p.parent / 'Samples',
        p.parent.parent / 'Samples',
        p.parent / 'samples',
    ]

    sample_cache: Dict[str, SampleData] = {}

    for sr in samples_raw:
        file_path = Path(sr['file_path'].replace('\\', '/'))
        sname     = _safe_name(file_path.stem)

        if sname in sample_cache:
            sample_index_map[sr['index']] = sample_cache[sname]
            continue

        # Search for the file
        candidates = [d / file_path.name for d in search_dirs]
        candidates += [d / file_path for d in search_dirs]

        for candidate in candidates:
            if candidate.exists():
                sd = load_wav(str(candidate), sname)
                if sd:
                    sd.root_note  = min(127, sr['root_note'])
                    sd.fine_tune  = sr['root_fine']
                    loop_mode     = sr['loop_mode']
                    sd.loop_type  = (LoopType.FORWARD if loop_mode == 1
                                     else LoopType.ALTERNATING if loop_mode == 2
                                     else LoopType.NO_LOOP)
                    sd.loop_start = sr['loop_start']
                    sd.loop_end   = sr['loop_end']
                    sample_cache[sname] = sd
                    sample_index_map[sr['index']] = sd
                    bank.samples.append(sd)
                    print(f"  Loaded: {sd.name} ({sd.sample_rate} Hz)")
                break
        else:
            print(f"  [WARN] Sample not found: {file_path.name}")

    # --- Build group envelope map ---
    group_envs: Dict[int, dict] = {}
    for g in groups_raw:
        group_envs[g['index']] = g

    # --- Build voices from zones ---
    voice = VoiceLayer()
    # Use first group's envelope if available
    if group_envs:
        g0 = next(iter(group_envs.values()))
        voice.env_attack  = _exs_env_to_seconds(g0['attack'])
        voice.env_decay   = _exs_env_to_seconds(g0['decay'])
        voice.env_sustain = g0['sustain'] / 127.0
        voice.env_release = _exs_env_to_seconds(g0['release'])

    for z in zones_raw:
        sd = sample_index_map.get(z['sample_idx'])
        if sd is None:
            continue

        # Volume: EXS24 0..127 → dB
        vol_db = 20 * math.log10(max(1e-6, z['volume'] / 127.0))
        # Pan: -64..+63 → -1.0..+1.0
        pan = z['pan'] / 63.0

        zone = ZoneMapping(
            sample_name = sd.name,
            lo_key      = min(127, z['key_lo']),
            hi_key      = min(127, z['key_hi']),
            lo_vel      = min(127, z['vel_lo']),
            hi_vel      = min(127, z['vel_hi']),
            root_key    = min(127, z['key_root']),
            fine_tune   = z['fine'],
            transpose   = z['coarse'],
            volume      = vol_db,
            pan         = max(-1.0, min(1.0, pan)),
        )
        voice.zones.append(zone)

    if voice.zones:
        preset.voices.append(voice)
        print(f"  Preset '{inst_name}': {len(voice.zones)} zone(s)")

    bank.presets.append(preset)
    return bank
