# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# Independent reimplementation.  Akai MPC1000 / MPC2000(XL) .pgm binary layouts
# and the MPC60 12-bit sample unpacking informed by ConvertWithMoss (LGPLv3),
#   Jürgen Moßgraber, https://github.com/git-moss/ConvertWithMoss
#   (format/akai/mpc1000, format/akai/mpc2000, format/akai/mpc60).
# MPC1000 offsets verified against MPC1000/2500 "From Mars" kits; MPC2000/XL
# verified against an Akai MPC2000XL factory CD; the MPC60 .PGM/.SND container
# layout was reverse-engineered from a real MPC60 kit.  No source was copied.
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
Akai MPC .pgm Parser (MPC500/1000/2500 + MPC2000/XL + MPC60)
------------------------------------------------------------
`parse_pgm()` dispatches by magic to three different binary drum-program
formats (the MPC2000/XL and MPC60 sections are documented near their parsers
at the bottom):
  - MPC500/1000/2500 — "MPC1000 PGM 1.00" at offset 4 (detailed below).
  - MPC2000 / MPC2000XL — byte 0/1 == 0x07/0x04; 64 pads referencing external
    standard `.WAV` files.
  - MPC60 (1988)      — byte 0/1 == 0x07/0x00; references external 12-bit
    `.SND` files.

The MPC1000-family `.pgm` is a fixed-size (10756-byte) binary drum program.
Unlike the modern XML `.xpm` (MPC X/Live/One), it is a flat binary with five
sections: header, 64 pads, MIDI-note table, slider, footer.  Each of the 64
pads holds up to four samples (velocity layers / stacks) that reference external
`.wav` files in the same folder.

File layout (little-endian; offsets in bytes):

  Header (24):
    0    2   file size (u16 LE) = 10756
    2    2   padding
    4   16   magic  "MPC1000 PGM 1.00"
    20   4   padding

  64 pads, each 164 bytes starting at offset 24 + pad*164:
    4 × sample record (24 bytes each):
      0   16   sample name (ASCII, NUL/space padded, no extension)
      16   1   padding
      17   1   level            (0..100)
      18   1   velocity lo       (0..127)
      19   1   velocity hi       (0..127)
      20   2   tuning (s16 LE)   (cents, -3600..3600)
      22   1   play mode         (0=One Shot, 1=Note On)
      23   1   padding
    pad parameters (68 bytes, after the 4 samples):
      6    1   attack            (0..100)
      7    1   decay             (0..100)
      8    1   decay mode        (0=End, 1=Start)
      11   1   velocity→level    (0..100)
      17   1   filter1 type      (0=Off,1=LP,2=BP,3=HP,4=LP2)
      18   1   filter1 freq      (0..100)
      19   1   filter1 res       (0..100)
      24   1   filter1 vel→freq  (0..100)
      47   1   mixer level       (0..100)
      48   1   mixer pan         (0..100, 50=centre)

  Footer (starts at 24 + 64*164 = 10520):
    10520  64   MIDI note per pad (pad index → MIDI note)
    10584 128   assigned-pads table (MIDI note → pad index; 64 = unassigned)
    10712   1   MIDI program change
    10713  26   slider 1 + 2 parameters
    10739  17   padding

Mapping to the mpc2emu model:
  - One `.pgm` → one Bank / one Preset (the kit).
  - Each non-empty sample → one key-tracking VoiceLayer at the pad's MIDI note
    (lo_key = hi_key = note, root_key = note → recorded pitch on that key).
    Multiple samples on a pad become separate voices with their own velocity
    ranges (mirrors the velocity-layer handling in xpm_parser).
  - Amp envelope, filter and mixer come from the pad/sample parameters.

Sample audio lives in sibling `.wav`/`.WAV` files named after the (≤16-char)
sample name.  Names longer than 16 chars are truncated by the MPC and may not
match the on-disk file — such samples are reported and skipped.

`.pgm` files with a different magic (e.g. older Akai `BD12` programs) are
rejected with a clear error.
"""

import array
import math
import struct
from pathlib import Path
from typing import Optional, List, Dict

from models.common import Bank, Preset, VoiceLayer, ZoneMapping, SampleData
from parsers.xpm_parser import load_wav, _safe_name


_MAGIC       = b'MPC1000 PGM 1.00'
_HEADER_SZ   = 24
_SAMPLE_SZ   = 24
_PAD_SZ      = 4 * _SAMPLE_SZ + 68     # 164 bytes per pad
_N_PADS      = 64
_MIDI_OFF    = _HEADER_SZ + _N_PADS * _PAD_SZ   # 10520
_FILE_SZ     = _MIDI_OFF + 64 + 128 + 1 + 26 + 17  # 10756

# MPC1000 filter type → MPC-XPM FilterType int (consumed by
# e4b_writer._XPM_FILTER_TYPE).  LP→Low 4, BP→Band 4, HP→High 4, LP2→Low 2.
_PGM_FILTER_XPM = {1: 3, 2: 12, 3: 8, 4: 2}


def _amp_time(value: int, long: bool) -> float:
    """MPC 0..100 envelope value → seconds (calibration per ConvertWithMoss:
    assume ~2 s max for short stages, ~6 s for the long decay stage)."""
    return value / 100.0 * (6.0 if long else 2.0)


def _gain_db(mixer_level: int, sample_level: int) -> float:
    """Combined mixer + sample level (each 0..100) → dB (0 dB at both = 100)."""
    x = (mixer_level + sample_level) / 200.0
    if x <= 0.0:
        return -96.0
    return max(-96.0, min(12.0, 20.0 * math.log10(x)))


def _find_sample(name: str, search_dirs: List[Path]) -> Optional[Path]:
    for d in search_dirs:
        for ext in ('.wav', '.WAV', '.Wav'):
            cand = d / f"{name}{ext}"
            if cand.exists():
                return cand
    return None


def parse_pgm(pgm_path: str,
              sample_dirs: Optional[List[str]] = None) -> Bank:
    """Parse an Akai MPC `.pgm` drum program into a Bank.

    Dispatches by magic:
      - MPC500/1000/2500 — "MPC1000 PGM 1.00" at offset 4 (fixed 10756-byte
        layout, references external `.wav` samples).
      - MPC60 — byte 0 == 0x07 (sample-name list + per-pad params, references
        external 12-bit `.SND` samples).

    Args:
        pgm_path:    Path to the `.pgm` file.
        sample_dirs: Extra directories to search for the referenced samples
                     (the `.pgm`'s own directory is always searched first).
    """
    p = Path(pgm_path).resolve()
    print(f"Parsing MPC PGM: {p.name}")
    data = p.read_bytes()

    if len(data) >= 20 and data[4:20] == _MAGIC:
        return _parse_mpc1000(p, data, sample_dirs)
    if len(data) >= 2 and data[0] == 0x07 and data[1] == 0x04:
        return _parse_mpc2000(p, data, sample_dirs)   # MPC2000 / MPC2000XL
    if _looks_like_mpc60(data):
        return _parse_mpc60(p, data, sample_dirs)

    magic = data[4:20].decode('ascii', errors='replace') if len(data) >= 20 else '?'
    raise ValueError(
        f"Unrecognised .pgm: not MPC1000/2500 ('MPC1000 PGM 1.00'), MPC2000/XL "
        f"(0x07 0x04) nor MPC60 (0x07 0x00 + name); magic={magic!r}: {p.name}")


def _looks_like_mpc60(data: bytes) -> bool:
    """MPC60 .PGM signature: 0x07 0x00, then a printable 16-char sample name.
    (Guards against unrelated `.pgm` whose u16 size field happens to start 0x07,
    e.g. the Akai `BD12` programs where byte 1 is non-zero.)"""
    if len(data) < 18 or data[0] != 0x07 or data[1] != 0x00:
        return False
    name = data[2:18]
    # First name char must be a normal printable ASCII glyph.
    return 0x20 <= name[0] < 0x7F and all(b == 0 or 0x20 <= b < 0x7F for b in name)


def _parse_mpc1000(p: Path, data: bytes,
                   sample_dirs: Optional[List[str]] = None) -> Bank:
    """MPC500/1000/2500 binary drum program (fixed 10756-byte layout)."""
    if len(data) < _FILE_SZ:
        raise ValueError(
            f"MPC PGM too small: {len(data)} bytes (expected {_FILE_SZ}): {p.name}")

    program_name = _safe_name(p.stem)
    bank   = Bank(name=program_name)
    preset = Preset(name=program_name[:16])

    search_dirs = [p.parent]
    if sample_dirs:
        search_dirs += [Path(d) for d in sample_dirs]

    sample_cache: Dict[str, SampleData] = {}

    def _load(name: str) -> Optional[SampleData]:
        safe = _safe_name(name)
        if safe in sample_cache:
            return sample_cache[safe]
        path = _find_sample(name, search_dirs)
        if path is None:
            print(f"  [WARN] Sample not found: {name!r} (.wav)")
            return None
        sd = load_wav(str(path), name)
        if sd is None:
            return None
        sample_cache[safe] = sd
        bank.samples.append(sd)
        print(f"  Loaded: {sd.name} ({sd.sample_rate} Hz)")
        return sd

    n_pads_used = 0
    for pad in range(_N_PADS):
        pad_base   = _HEADER_SZ + pad * _PAD_SZ
        param_base = pad_base + 4 * _SAMPLE_SZ
        midi_note  = max(0, min(127, data[_MIDI_OFF + pad]))

        attack     = data[param_base + 6]
        decay      = data[param_base + 7]
        decay_mode = data[param_base + 8]
        f1_type    = data[param_base + 17]
        f1_freq    = data[param_base + 18]
        f1_res     = data[param_base + 19]
        mixer_lvl  = data[param_base + 47]
        mixer_pan  = data[param_base + 48]

        pad_has_sample = False
        for s in range(4):
            soff = pad_base + s * _SAMPLE_SZ
            sname = data[soff:soff + 16].split(b'\x00')[0].decode(
                'ascii', errors='replace').strip()
            if not sname:
                continue

            level     = data[soff + 17]
            vel_lo    = min(127, data[soff + 18])
            vel_hi    = min(127, data[soff + 19])
            tuning    = struct.unpack_from('<h', data, soff + 20)[0]   # cents
            play_mode = data[soff + 22]

            sd = _load(sname)
            if sd is None:
                continue
            pad_has_sample = True

            # Tuning (cents) → integer semitones + remaining cents.
            semis = int(tuning / 100)
            cents = tuning - semis * 100

            zone = ZoneMapping(
                sample_name = sd.name,
                lo_key      = midi_note,
                hi_key      = midi_note,
                lo_vel      = min(vel_lo, vel_hi),
                hi_vel      = max(vel_lo, vel_hi),
                root_key    = midi_note,
                transpose   = semis,
                fine_tune   = cents,
                volume      = _gain_db(mixer_lvl, level),
                pan         = max(-1.0, min(1.0, (mixer_pan - 50) / 50.0)),
            )

            voice = VoiceLayer(zones=[zone])
            one_shot = (play_mode == 0)

            # Amp envelope (pad attack/decay + one-shot/note-on play mode).
            voice.env_attack  = _amp_time(attack, long=False)
            voice.env_decay   = _amp_time(decay, long=True) if decay_mode == 0 else 0.0
            voice.env_sustain = 1.0 if one_shot else 0.0
            if decay_mode == 1:
                voice.env_release = _amp_time(decay, long=False)
            elif one_shot:
                frames = len(sd.data) // 2          # 16-bit mono
                voice.env_release = frames / float(sd.sample_rate or 44100)
            else:
                voice.env_release = 0.05

            # Filter 1 (only when engaged and not fully open).
            if f1_type in _PGM_FILTER_XPM and f1_freq < 100:
                voice.filter_type      = _PGM_FILTER_XPM[f1_type]
                voice.filter_cutoff    = min(1.0, f1_freq / 99.0)
                voice.filter_resonance = min(1.0, f1_res / 100.0)
            else:
                voice.filter_type   = 0
                voice.filter_cutoff = 1.0

            preset.voices.append(voice)

        if pad_has_sample:
            n_pads_used += 1

    if preset.voices:
        bank.presets.append(preset)
    print(f"  Preset '{preset.name}': {n_pads_used} active pad(s), "
          f"{len(preset.voices)} voice(s), {len(bank.samples)} sample(s)")
    return bank


# ===========================================================================
# Akai MPC60 (1988) — sample-name list + external 12-bit .SND samples
# ===========================================================================
# The MPC60 `.PGM` (magic byte 0x07) is a program that lists sample names and
# per-pad parameters; the audio lives in separate `.SND` files (magic 0x0101).
# MPC60 samples are signed 12-bit mono at 40 kHz, two samples packed per 3
# bytes.  The 12-bit→16-bit unpacking is the same as ConvertWithMoss's MPC60
# SET reader (format/akai/mpc60, LGPL — independent impl, no code copied);
# the .PGM/.SND container layout here was reverse-engineered directly from a
# real MPC60 kit (verified: decoded samples are clean decaying drum hits).
#
# .SND header (little-endian):
#   0x00  2   magic 0x01 0x01
#   0x02 16   sample name (ASCII, space-padded)
#   0x12  1   0x00
#   0x13  3   length in frames (u24)
#   ...       further params (loop/level — not decoded)
#   0x26      12-bit packed sample data (2 frames per 3 bytes)
#
# .PGM (magic 0x07): 16-byte sample names at +1 stride (17 bytes each) from
# offset 2 until a 0x00 name; per-pad note/volume/pan params follow but are not
# yet decoded (single test file), so samples map to sequential keys from C1.

_MPC60_RATE       = 40000          # MPC60 sample rate (Hz)
_MPC60_SND_MAGIC  = b'\x01\x01'
_MPC60_SND_DATA   = 0x26           # offset of packed 12-bit data
_MPC60_NAME_STRIDE = 17            # 16-byte name + 1 separator
_MPC60_BASE_NOTE  = 36             # C1 (GM kick) — first pad


def _decode_mpc60_snd(snd: bytes) -> Optional[bytes]:
    """Decode an MPC60 `.SND` (12-bit packed, 40 kHz mono) → 16-bit LE PCM."""
    if len(snd) < _MPC60_SND_DATA + 3 or snd[0:2] != _MPC60_SND_MAGIC:
        return None
    body = snd[_MPC60_SND_DATA:]
    out = array.array('h')
    for i in range(0, len(body) - 2, 3):
        b0, b1, b2 = body[i], body[i + 1], body[i + 2]
        for v in (b0 | ((b2 & 0x0F) << 8), b1 | ((b2 & 0xF0) << 4)):
            v = ((v & 0xFF) << 8) | ((v >> 8) & 0xFF)   # byte-swap (left-justify)
            out.append(v - 0x10000 if v >= 0x8000 else v)
    return out.tobytes()


def _parse_mpc60(p: Path, data: bytes,
                 sample_dirs: Optional[List[str]] = None) -> Bank:
    """Akai MPC60 `.PGM` (+ external `.SND` samples) → Bank."""
    program_name = _safe_name(p.stem)
    bank   = Bank(name=program_name)
    preset = Preset(name=program_name[:16])

    # Sample-name list: 16-byte names at 17-byte stride from offset 2.
    names: List[str] = []
    off = 2
    while off + 16 <= len(data) and data[off] != 0x00:
        nm = data[off:off + 16].split(b'\x00')[0].decode('ascii', 'replace').strip()
        if not nm:
            break
        names.append(nm)
        off += _MPC60_NAME_STRIDE
    print(f"  MPC60 program: {len(names)} sample(s)")

    search_dirs = [p.parent]
    if sample_dirs:
        search_dirs += [Path(d) for d in sample_dirs]

    note = _MPC60_BASE_NOTE
    for nm in names:
        snd_path = None
        for d in search_dirs:
            for ext in ('.SND', '.snd', '.Snd'):
                cand = d / f"{nm}{ext}"
                if cand.exists():
                    snd_path = cand
                    break
            if snd_path:
                break
        if snd_path is None:
            print(f"  [WARN] .SND not found: {nm!r}")
            continue

        pcm = _decode_mpc60_snd(snd_path.read_bytes())
        if not pcm:
            print(f"  [WARN] Could not decode: {snd_path.name}")
            continue

        sname = _safe_name(nm)
        sd = SampleData(name=sname, data=pcm, sample_rate=_MPC60_RATE,
                        channels=1, bit_depth=16, root_note=note)
        bank.samples.append(sd)
        print(f"  Loaded: {sname} ({len(pcm)//2} frames @ {_MPC60_RATE} Hz)")

        n = min(127, note)
        zone = ZoneMapping(sample_name=sname, lo_key=n, hi_key=n,
                           lo_vel=0, hi_vel=127, root_key=n)
        preset.voices.append(VoiceLayer(zones=[zone]))
        note += 1

    if preset.voices:
        bank.presets.append(preset)
    print(f"  Preset '{preset.name}': {len(preset.voices)} voice(s), "
          f"{len(bank.samples)} sample(s)")
    return bank


# ===========================================================================
# Akai MPC2000 / MPC2000XL — sample-name list + 64 pads, external .WAV samples
# ===========================================================================
# The MPC2000/XL `.PGM` (byte0=0x07, byte1=0x04) is a 64-pad program that lists
# sample names and references external standard `.WAV` files (unlike the MPC60's
# 12-bit `.SND`).  Layout informed by ConvertWithMoss (format/akai/mpc2000,
# LGPL — independent impl, no code copied) and verified against an MPC2000XL
# factory CD (APLIX/Akai, 1999).
#
# Header: 0x07 0x04, u16 numSamples, numSamples x (16-byte name + 1 pad),
#   0x1E, 0x00, 16-byte program name, 0x00, 9-byte slider params, MIDI channel,
#   {0x23 0x40 0x00 0x19 0x00}, 64 x 25-byte pad, 64 x 6-byte mixer,
#   {0x00 0x00 0x40 0x00}, 64-byte MIDI-note table (pad -> note).
# Pad[0]=sampleNumber (index into the name list; 0 = none).

def _parse_mpc2000(p: Path, data: bytes,
                   sample_dirs: Optional[List[str]] = None) -> Bank:
    """Akai MPC2000 / MPC2000XL `.PGM` (+ external `.WAV` samples) → Bank."""
    o = 2
    n_samp = struct.unpack_from('<H', data, o)[0]; o += 2
    names: List[str] = []
    for _ in range(n_samp):
        names.append(data[o:o + 16].split(b'\x00')[0].decode('ascii', 'replace').strip())
        o += 17
    o += 2                                   # 0x1E, 0x00
    prog = data[o:o + 16].split(b'\x00')[0].decode('ascii', 'replace').strip(); o += 16
    o += 1                                   # padding
    o += 9                                   # slider params
    o += 1                                   # MIDI channel
    o += 5                                   # 0x23 0x40 0x00 0x19 0x00

    pads = []
    for _ in range(64):
        pads.append({
            'sample': data[o + 0],
            'tune':   struct.unpack_from('<h', data, o + 9)[0],   # signed cents-ish
            'attack': data[o + 11], 'decay': data[o + 12],
        })
        o += 25
    mixers = []
    for _ in range(64):
        mixers.append({'level': data[o + 2], 'pan': data[o + 3]}); o += 6   # XL order
    o += 4                                   # 0x00 0x00 0x40 0x00
    midi_notes = data[o:o + 64]

    program_name = _safe_name(prog or p.stem)
    bank   = Bank(name=program_name)
    preset = Preset(name=program_name[:16])
    print(f"  MPC2000/XL program {prog!r}: {n_samp} sample(s)")

    search_dirs = [p.parent]
    if sample_dirs:
        search_dirs += [Path(d) for d in sample_dirs]
    sample_cache: Dict[str, SampleData] = {}

    def _load(name: str) -> Optional[SampleData]:
        safe = _safe_name(name)
        if safe in sample_cache:
            return sample_cache[safe]
        path = _find_sample(name, search_dirs)
        if path is None:
            print(f"  [WARN] Sample not found: {name!r} (.wav)")
            return None
        sd = load_wav(str(path), name)
        if sd:
            sample_cache[safe] = sd
            bank.samples.append(sd)
            print(f"  Loaded: {sd.name} ({sd.sample_rate} Hz)")
        return sd

    n_used = 0
    for i in range(64):
        sn = pads[i]['sample']
        if not (0 < sn < len(names)) or not names[sn]:
            continue
        sd = _load(names[sn])
        if sd is None:
            continue
        note  = min(127, midi_notes[i])
        tune  = pads[i]['tune']
        semis = int(tune / 100); cents = tune - semis * 100
        lvl   = mixers[i]['level']
        vol   = _gain_db(100, lvl)
        pan   = max(-1.0, min(1.0, (mixers[i]['pan'] - 50) / 50.0))
        zone  = ZoneMapping(sample_name=sd.name, lo_key=note, hi_key=note,
                            lo_vel=0, hi_vel=127, root_key=note,
                            transpose=semis, fine_tune=cents, volume=vol, pan=pan)
        voice = VoiceLayer(zones=[zone])
        voice.env_attack = _amp_time(pads[i]['attack'], long=False)
        voice.env_decay  = _amp_time(pads[i]['decay'],  long=True)
        voice.env_sustain = 1.0
        preset.voices.append(voice)
        n_used += 1

    if preset.voices:
        bank.presets.append(preset)
    print(f"  Preset '{preset.name}': {n_used} pad(s), {len(bank.samples)} sample(s)")
    return bank
