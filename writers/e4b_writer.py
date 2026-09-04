# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# E4B format reverse-engineered from:
#   - E4XT hardware-saved banks (JL AnalogBank, FltEnvTest, FLTTYPES series)
#   - Commercial EOS CD-ROMs (library disc B,
#     library disc C, library disc S)
#   - struct emu3_sample from emu3bm by David García Goñi
#     https://github.com/dagargo/emu3bm  (GPL-3.0-or-later)
#   - Phil's E4 format notes
#     http://www.philizound.co.uk/freebies/software/emu-reorder/emu-reorder.html
# No third-party source code was copied; this is an independent implementation.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
EMU E4B Bank Writer
-------------------
Produces .E4B files readable by EMU Emulator 4 / E4XT (EOS 4.x).

Container: IFF-like FORM E4B0
  TOC1  — 32-byte entries (tag, size, offset, index, name, prog)
  E4Ma  — 256-byte multimap block
  E4P1  — preset chunks  (82-byte header + variable voice blocks)
  E3S1  — sample chunks  (94-byte header + little-endian 16-bit PCM)

Preset body layout (confirmed from hardware-saved files):
  [0-1]   preset index (BE u16)
  [2-17]  name (space-padded, 16 bytes)
  [18]    0x00
  [19]    0x52  (constant)
  [20-21] num_voices (BE u16)
  [22-27] zeros
  [28]    0x78  (master volume = 120)
  [29-51] zeros
  [52-55] 0x52 0x23 0x00 0x7E  (constant)
  [56-59] 0xFF x4  (MIDI routing — any note/channel)
  [60-81] zeros
  [82+]   voice blocks (one per voice)

Voice block = 284 fixed bytes + N_zones × 22 bytes:
  voice[0:110]    voice params — confirmed byte positions (hardware diff):
    vpar[4]   zone count  (E4XT reads exactly this many secondary zones)
    vpar[34]  Key Transpose     (signed byte semitones, −24..+24; keyboard pitch remap)
    vpar[35]  Coarse Tune       (signed byte semitones, −72..+24; repitches/stretches sample)
    vpar[36]  Fine Tune         (signed byte, 1/64-semitone units −64..+63 ≈ ±1 st)
    vpar[38]  Non-Transpose flag  (0=key-tracking on, 1=pitch fixed — confirmed B.010-Voices_RevEng.E4B)
    vpar[54]  Volume       (signed byte, dB; 0=unity — hardware-confirmed 2026-07-26)
    vpar[55]  Pan          (signed byte, −64=full-L..0=centre..+63=full-R — hardware-confirmed 2026-07-26)
    vpar[58]  VCF filter type  (0x00=4PLP, 0x01=2PLP, 0x02=6PLP,
                                 0x08=2HP, 0x09=4HP, 0x10=2BP, 0x11=4BP)
    vpar[60]  VCF cutoff frequency  (0≈57 Hz, 255=20 kHz, exponential)
    vpar[61]  VCF Q/resonance  (0–127 direct)
  voice[110:174]  primary zone table (4 × 16 bytes)
    PZT[14:26]  6-stage filter envelope  (rate/level pairs, hardware-confirmed):
      PZT[14/15] Attack1  rate/level
      PZT[16/17] Attack2  rate/level
      PZT[18/19] Decay1   rate/level
      PZT[20/21] Decay2   rate/level
      PZT[22/23] Release1 rate/level  (default rate=20)
      PZT[24/25] Release2 rate/level
  voice[174:190]  zeros
  voice[190:270]  modulation matrix (20 × 4 bytes)
  voice[270:284]  zeros
  voice[284:]     secondary zone table
    each 22-byte entry:
      [2]  lo_key
      [5]  hi_key
      [6]  lo_vel
      [9]  hi_vel
      [10:12] sample_idx (BE u16, 1-indexed — EOS supports up to 1000
              samples/bank (S000-S999), so this can't be a single byte)
      [12:14] fine_tune, signed BE i16, 1/64-semitone (used only for a
              MULTI-zone voice — single-zone voices use vpar[36] instead
              and leave this zero; hardware-confirmed 2026-07-26, see
              _zone_entry / _build_voice)
      [14] root_note
      [15] volume, signed byte, dB (multi-zone only, else vpar[54])
      [16] pan, signed byte, -64..+63 (multi-zone only, else vpar[55])
    terminated by an entry with lo_key(1) > hi_key(0)
  Voice-level velocity range mirrors the zone range: vpar[18]=lo_vel,
  vpar[21]=hi_vel — confirmed byte-for-byte against Jan's hand-fixed
  reference bank B.003-Vel-Split (Inst-Piano-F9 Grand Piano), which
  matches the source XPM's per-layer VelStart/VelEnd exactly.

Sample (E3S1) body = 94-byte header + little-endian 16-bit PCM
  (layout confirmed from emu3bm struct emu3_sample + hardware banks):
  [0-1]   sample index (BE u16)
  [2-17]  name (space-padded, 16 bytes)
  [18-21] header = 0
  [22-25] start_l = 92  (LE u32, byte offset to PCM start = sizeof struct)
  [30-33] end_l = 92 + pcm_bytes − 2  (LE u32)
  [38-41] loop_start_l  (LE u32, byte offset)
  [46-49] loop_end_l    (LE u32, byte offset)
  [54-57] sample_rate   (LE u32)
  [60-61] options       (LE u16)
            0x0020 = MONO_L (no loop)
            0x0031 = MONO_L | bit4 | LOOP (forward — hardware-confirmed)
  [62-65] sample_data_offset_l = 92  (LE u32)
  [94+]   PCM data (little-endian, native WAV byte order)
"""

import math
import copy
import struct
from typing import List
from models.common import (
    e4xt_cents_to_cord_amount, e4xt_cord_saturates, E4XT_VEL_SOURCE_UNITS,
    E4XT_VEL_AMPVOL_DB_PER_PERCENT,
    key_track_to_filter_amount,
    e4xt_cutoff_byte_to_position,Bank, Preset, VoiceLayer, ZoneMapping, SampleData,
                           LoopType, lfo_rate_hz_to_byte,
                           env_seconds_to_rate, env_rate_to_seconds,
                           env_level_to_byte, env_sustain_to_byte, cord_amount_to_byte,
                           e4xt_cutoff_position, e4xt_volume_byte, e4xt_pan_byte,
                           E4XT_VOL_MEASURED_FLOOR_DB, E4XT_VEL_PIVOT,
                           velocity_pivot_offset_db, velocity_pivot_preset_shift,
                           E4B_CUTOFF_MIN_HZ, E4B_CUTOFF_MAX_HZ,
                           env_level_byte_to_db,
                           E4B_MIN_AUDIBLE_DECAY_RATE,
                           e4xt_resonance_byte,
                           env_span_seconds_to_rate,
                           env_db_per_s_to_rate_byte)
from processors.loop_renderer import bake_alternating_loop
from writers.atomic import atomic_write


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FORM_MAGIC  = b'FORM'
FORM_TYPE   = b'E4B0'
TOC_TAG     = b'TOC1'
E4MA_TAG    = b'E4Ma'
PRES_TAG    = b'E4P1'
SAMP_TAG    = b'E3S1'
EMST_TAG    = b'EMSt'    # master setup; always the last chunk, not in the TOC

MAX_NAME    = 16
SAMP_HDR    = 94     # E3S1 header: 2 bytes sample_idx + 92 bytes struct emu3_sample
PRES_HDR    = 82     # E4P1 fixed preset header size
VOICE_FIXED = 284    # fixed bytes per voice (before variable zone table)
ZONE_ENTRY  = 22     # bytes per secondary zone entry

# XPM FilterType → E4B vpar[58] byte  (filter type lives in byte 58, NOT byte 54!)
#
# ALL confirmed from hardware (FLTTYPES.E4B, FLTTYPES2.E4B, JL AnalogBank K2 Bass):
#   Group LP (base 0):  4PLP=0x00, 2PLP=0x01, 6PLP=0x02
#   Group HP (base 8):  2HP=0x08,  4HP=0x09
#   Group BP (base 16): 2BP=0x10,  4BP=0x11
#   ContBP: 0x12 (inferred from pattern; base 16 + 2)
#
# 4PLP (0x00) at full frequency (vpar[60]=0xFF) = JL AnalogBank default = bypass-like.
# MPC 2.x FilterType → E4B vpar[58]  (MPC 3.7 manual appendix + hardware confirmed)
#
# MPC filter list (0-indexed, matches XPM FilterType integer):
#   0  Off
#   1  Low 1  (1-pole  LP,  6 dB/oct)
#   2  Low 2  (2-pole  LP, 12 dB/oct)
#   3  Low 4  (4-pole  LP, 24 dB/oct)
#   4  Low 6  (6-pole  LP, 36 dB/oct)  ← confirmed "Low 6" from hardware test
#   5  Low 8  (8-pole  LP, 48 dB/oct)
#   6  High 1 (1-pole  HP)
#   7  High 2 (2-pole  HP)
#   8  High 4 (4-pole  HP)
#   9  High 6 (6-pole  HP)
#  10  High 8 (8-pole  HP)
#  11  Band 2 (2-pole  BP)
#  12  Band 4 (4-pole  BP)
#  13  Band 6 (6-pole  BP)
#  14  Band 8 (8-pole  BP)
#  15  BS 2P  (2-pole  band-stop / notch)
#  16  BS 4P  (4-pole  band-stop)
#  17  BS 6P
#  18  BS 8P
#  19  BB 2P  (2-pole  band-boost, like parametric EQ band)
#  20  BB 4P
#  21  BB 6P
#  22  BB 8P
#  23  Model1 (4-pole LP analog emulation with distortion)
#  24  Model2 (LP, mellow resonance)
#  25  Model3 (LP, extreme resonance)
#  26  Vocal1 (formant: ah/ooh)
#  27  Vocal2 (formant: oh/ee, 3-band)
#  28  Vocal3 (formant: 5-band vocal tract model)
#  29  MPC3000 LPF (12 dB/oct resonant LP from original MPC3000, 1994)
#
# E4XT vpar[58] is fully reverse-engineered (hardware-confirmed 2026-06-08,
# B.005-FILTERTYPES.E4B): byte = group_base | variant (variant = slope/order in
# the low 3 bits).  See _E4XT_FILTER_BYTES below and docs/E4B_FORMAT.md §4.4.
# E4XT has no 1-pole, 8-pole, or band-boost variants — those map to the nearest
# available type (BB band-boost → BP as closest resonant emphasis).  The MPC
# Vocal-formant types DO have an E4XT equivalent (the Vocal filters) and now map
# there instead of falling back to LP.  Model/distortion LPs have no equivalent.
# Swept EQ 1-oct filter (vpar[58]=0x20): vpar[61] holds GAIN, not Q.
# Gain law hardware-RE'd 2026-06-14 (RE_SUITE2, 4 points): byte 0=−24 dB,
# 32=−12 dB, 64=0 dB, 114=+18.7 dB → gain_dB = (byte − 64) × 0.375.
_SWEPT_EQ_1OCT        = 0x20
_SWEPT_EQ_DB_PER_STEP = 0.375

_XPM_FILTER_TYPE = {
    0:  0x00,  # Off          → 4PLP wide open (bypass-like)
    1:  0x01,  # Low 1  1-p   → 2-Pole LP (closest)
    2:  0x01,  # Low 2  2-p   → 2-Pole LP
    3:  0x00,  # Low 4  4-p   → 4-Pole LP
    4:  0x02,  # Low 6  6-p   → 6-Pole LP  (confirmed from hardware)
    5:  0x02,  # Low 8  8-p   → 6-Pole LP  (E4XT max LP slope)
    6:  0x08,  # High 1 1-p   → 2nd Ord HP (closest)
    7:  0x08,  # High 2 2-p   → 2nd Ord HP
    8:  0x09,  # High 4 4-p   → 4th Ord HP
    9:  0x09,  # High 6 6-p   → 4th Ord HP (E4XT max HP slope)
    10: 0x09,  # High 8 8-p   → 4th Ord HP
    11: 0x10,  # Band 2 2-p   → 2nd Ord BP
    12: 0x11,  # Band 4 4-p   → 4th Ord BP
    13: 0x11,  # Band 6 6-p   → 4th Ord BP (E4XT max BP slope)
    14: 0x11,  # Band 8 8-p   → 4th Ord BP
    15: 0x20,  # BS 2P notch  → Swept EQ 1-oct (cut) — hardware-RE'd 2026-06-14
    16: 0x20,  # BS 4P notch  → Swept EQ 1-oct (cut)
    17: 0x20,  # BS 6P notch  → Swept EQ 1-oct (cut)
    18: 0x20,  # BS 8P notch  → Swept EQ 1-oct (cut)
    19: 0x20,  # BB 2P boost  → Swept EQ 1-oct (+gain) — band-boost = band-stop, gain flipped
    20: 0x20,  # BB 4P boost  → Swept EQ 1-oct (+gain)
    21: 0x20,  # BB 6P boost  → Swept EQ 1-oct (+gain)
    22: 0x20,  # BB 8P boost  → Swept EQ 1-oct (+gain)
    23: 0x00,  # Model1 LP+dist → 4-Pole LP
    24: 0x00,  # Model2 LP mellow → 4-Pole LP
    25: 0x00,  # Model3 LP extreme → 4-Pole LP
    26: 0x50,  # Vocal1 formant → E4XT Vocal Ah-Ay-Ee (real formant equivalent)
    27: 0x51,  # Vocal2 formant → E4XT Vocal Oo-Ah
    28: 0x50,  # Vocal3 formant → E4XT Vocal Ah-Ay-Ee (only 2 E4XT vocal types)
    29: 0x01,  # MPC3000 LPF 12dB/oct → 2-Pole LP (exact pole count match)
}

# Authoritative E4XT filter type → vpar[58] byte, reverse-engineered from
# hardware (B.005-FILTERTYPES.E4B, 2026-06-08).  Encoding: byte = base | variant
# (variant in the low 3 bits).  Not all are reachable from current source
# formats, but they document the full palette and back the e4b_parser reverse
# map.  See docs/E4B_FORMAT.md §4.4.
_E4XT_FILTER_BYTES = {
    'Lowpass 4-Pole':   0x00, 'Lowpass 2-Pole':   0x01, 'Lowpass 6-Pole':   0x02,
    'Highpass 2nd':     0x08, 'Highpass 4th':     0x09,
    'Bandpass 2nd':     0x10, 'Bandpass 4th':     0x11, 'Contrary Bandpass':0x12,
    'Swept EQ 1-oct':   0x20, 'Swept EQ 2->1-oct':0x21, 'Swept EQ 3->1-oct':0x22,
    'Phaser 1':         0x40, 'Phaser 2':         0x41, 'Bat Phaser':       0x42,
    'Flanger Lite':     0x48,
    'Vocal Ah-Ay-Ee':   0x50, 'Vocal Oo-Ah':      0x51,
    'Dual EQ Morph':    0x60, '2EQ+Lowpass Morph':0x61, '2EQ Morph+Expr':   0x62,
    'Peak/Shelf Morph': 0x68,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def _name16(s: str) -> bytes:
    """16-byte space-padded name, latin-1.

    latin-1 and not ASCII, so this is the exact inverse of
    e4b_parser._decode_name() -- see its docstring for why a real E4XT puts
    bytes above 0x7E in a name field.  Encoding as ASCII here would kill the
    byte at write time even with the parser fixed.

    errors= stays, unlike on the decode side: a name reaching us from a UTF-8
    source format (XPM, EXS24) can hold a codepoint above 0xFF, which latin-1
    genuinely cannot represent.

    Every name field in the file goes through this one helper -- sample header,
    preset, TOC entry -- so they cannot disagree with each other.
    """
    return s.encode('latin-1', errors='replace')[:MAX_NAME].ljust(MAX_NAME, b' ')


def _sample_display_name(sample: SampleData) -> str:
    """Sample name for E3S1 header: base truncated to fit '_<note><octave>' suffix.

    Root note is always preserved even if the base name must be shortened.
    Example: 'Inst-Bass-Underh' root=26(D0) → 'Inst-Bass-Un_D0'
    """
    octave = sample.root_note // 12 - 2
    note   = _NOTE_NAMES[sample.root_note % 12]
    suffix = f'_{note}{octave}'
    return sample.name[:MAX_NAME - len(suffix)] + suffix


def _iff_chunk(tag: bytes, data: bytes) -> bytes:
    """IFF chunk: tag(4) + BE-size(4) + data, word-aligned."""
    out = tag + struct.pack('>I', len(data)) + data
    if len(data) % 2:
        out += b'\x00'
    return out


# ---------------------------------------------------------------------------
# E4Ma multimap (256 bytes, required entry in TOC)
# ---------------------------------------------------------------------------

def _build_e4ma() -> bytes:
    """256-byte default multimap: all presets accessible on any MIDI channel."""
    entry = bytes([0x00, 0x00, 0x00, 0x01, 0x7F, 0x00, 0xFF, 0x00,
                   0x00, 0x00, 0xFF, 0xFF])
    return (entry * 22)[:256]


# ---------------------------------------------------------------------------
# EMSt master setup (1366 bytes, last chunk, NOT in the TOC)
# ---------------------------------------------------------------------------

# Default "Untitled MSetup" master-setup block, captured verbatim from
# hardware-saved E4XT banks (identical across all fresh/default banks; the
# trailing bytes are zero).  Real hardware always appends this chunk last, and
# the FORM size deliberately stops 4 bytes short of its end (see write_e4b),
# so when a bank is streamed from CD the truncated 4 bytes land in these
# trailing zeros instead of clipping the last sample's PCM.
_EMST_DEFAULT_B64 = (
    "AABVbnRpdGxlZCBNU2V0dXAgAAACAAAAfwAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAB/AAAA"
    "AAB/AAAAAP8AAAAAAAAAAAAAAAAAAAAAAAAAAH8AAAAAAH8AAAAA/wAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAfwAAAAAAfwAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAB/AAAAAAB/AAAAAP8AAAAA"
    "AAAAAAAAAAAAAAAAAAAAAH8AAAAAAH8AAAAA/wAAAAAAAAAAAAAAAAAAAAAAAAAAfwAAAAAA"
    "fwAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAB/AAAAAAB/AAAAAP8AAAAAAAAAAAAAAAAAAAAA"
    "AAAAAH8AAAAAAH8AAAAA/wAAAAAAAAAAAAAAAAAAAAAAAAAAfwAAAAAAfwAAAAD/AAAAAAAA"
    "AAAAAAAAAAAAAAAAAAB/AAAAAAB/AAAAAP8AAAAAAAAAAAAAAAAAAAAAAAAAAH8AAAAAAH8A"
    "AAAA/wAAAAAAAAAAAAAAAAAAAAAAAAAAfwAAAAAAfwAAAAD/AAAAAAAAAAAAAAAAAAAAAAAA"
    "AAB/AAAAAAB/AAAAAP8AAAAAAAAAAAAAAAAAAAAAAAAAAH8AAAAAAH8AAAAA/wAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAfwAAAAAAfwAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAB/AAAAAAB/AAAA"
    "AP8AAAAAAAAAAAAAAAAAAAAAAAAAAH8AAAAAAH8AAAAA/wAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "fwAAAAAAfwAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAB/AAAAAAB/AAAAAP8AAAAAAAAAAAAA"
    "AAAAAAAAAAAAAH8AAAAAAH8AAAAA/wAAAAAAAAAAAAAAAAAAAAAAAAAAfwAAAAAAfwAAAAD/"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAB/AAAAAAB/AAAAAP8AAAAAAAAAAAAAAAAAAAAAAAAAAH8A"
    "AAAAAH8AAAAA/wAAAAAAAAAAAAAAAAAAAAAAAAAAfwAAAAAAfwAAAAD/AAAAAAAAAAAAAAAA"
    "AAAAAAAAAAB/AAAAAAB/AAAAAP8AAAAAAAAAAAAAAAAAAAAAAAAAAH8AAAAAAH8AAAAA/wAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAfwAAAAAAfwAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAB/AAAA"
    "AAB/AAAAAP8AAAAAAAAAAAAAAAAAAAAAAAAAAH8AAAAAAH8AAAAA/wAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAfwAAAAAAfwAAAAD/AAAAAAAAAAAAAAAAAAAAAAAAAAB/AAAAAAB/AAAAAP8AAAAA"
    "AAAAAAAAAAAAAAAAAAAAAH8AAAD//////////wAAAAD/////AAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAA=="
)


def _build_emst() -> bytes:
    """1366-byte default master-setup ('Untitled MSetup') block."""
    import base64
    return base64.b64decode(_EMST_DEFAULT_B64)


# ---------------------------------------------------------------------------
# E3S1 sample chunk body
# ---------------------------------------------------------------------------

def _pcm_bytes_written(s) -> int:
    """How many PCM bytes this sample will actually contribute to the file.

    **Must** match what the write loop emits. For stereo that is not
    `len(s.data)`: `_interleaved_to_planar` keeps whole frames only, so a
    buffer holding a half-frame (`len % 4 == 2`) writes two bytes fewer than
    it holds. Declaring the larger number shifts every chunk after it, and the
    result is silent — the writer reports the full sample count, and the file
    reads back as ONE sample with the rest orphaned.

    Reached in practice through `--resample emulator2` / `emax1` on a stereo
    bank, which is what turned a 77-sample bank into a 1-sample file. The
    resampler no longer emits half-frames, but the invariant belongs here:
    the size a chunk declares comes from the bytes it writes, not from an
    upstream buffer that may not survive the transform.
    """
    n = len(s.data)
    return (n // 4) * 4 if getattr(s, 'channels', 1) == 2 else n


def _interleaved_to_planar(data: bytes) -> bytes:
    """Interleaved 16-bit stereo (mpc2emu's internal form) -> the E4B's
    PLANAR layout: the whole left channel, then the whole right.

    Corpus-RE'd 2026-07-29 (docs/RESOLUTION_NOTES.md §E4BSTEREO): a real
    stereo E3S1 object addresses two sequential blocks through the L/R
    halves of its start/end pairs, e.g. startL=92 endL=154458 /
    startR=154460 endR=308826. Strided slicing, so no per-frame loop.
    """
    n = len(data) // 4
    out = bytearray(n * 4)
    out[0:n * 2:2]        = data[0:n * 4:4]     # left  low byte
    out[1:n * 2:2]        = data[1:n * 4:4]     # left  high byte
    out[n * 2::2]         = data[2:n * 4:4]     # right low byte
    out[n * 2 + 1::2]     = data[3:n * 4:4]     # right high byte
    return bytes(out)


def _build_sample_header(sample: SampleData, sample_idx: int) -> bytes:
    """The 94-byte E3S1 sample header (the PCM is written separately).

    CR-16: returns the header only so write_e4b can stream `sample.data`
    straight to the file instead of concatenating it into ever-larger buffers
    (the body = this header + `sample.data`).

    Layout confirmed from emu3bm (dagargo/emu3fs) struct emu3_sample (92 bytes)
    plus 2-byte sample_idx prefix used by the E4B (EMU4) format:

      body[0-1]   sample_idx  (BE u16)               ← EMU4_E3S1_OFFSET = 2
      body[2-17]  name[16]                            ← struct[0-15]
      body[18-21] header = 0                          ← struct[16-19]
      body[22-25] start_l = 92  (= sizeof struct)     ← struct[20-23]  CRITICAL
      body[26-29] start_r = 0 (mono)                  ← struct[24-27]
      body[30-33] end_l = 92 + pcm_bytes - 2          ← struct[28-31]  CRITICAL
      body[34-37] end_r = 0                           ← struct[32-35]
      body[38-41] loop_start_l                        ← struct[36-39]
      body[42-45] loop_start_r = 0                    ← struct[40-43]
      body[46-49] loop_end_l                          ← struct[44-47]
      body[50-53] loop_end_r = 0                      ← struct[48-51]
      body[54-57] sample_rate  (u32 LE)               ← struct[52-55]
      body[58-59] playback_rate = 0  (u16 LE)         ← struct[56-57]
      body[60-61] options  (u16 LE)                   ← struct[58-59]  CRITICAL
                  0x0020 = MONO_L  0x0001 = LOOP
      body[62-65] sample_data_offset_l = 92  (u32 LE) ← struct[60-63]
      body[66-69] sample_data_offset_r = 0            ← struct[64-67]
      body[70-93] parameters[6] = {0…0}               ← struct[68-91]
      body[94+]   PCM data (little-endian, native WAV byte order)

    PCM is LE — confirmed from hardware-saved E4XT banks.
    """
    n_bytes   = len(sample.data)   # WAV = LE; E4XT reads LE — written as-is
    STRUCT_SZ = 92                 # sizeof(struct emu3_sample)

    # Stereo: one object carries BOTH channels as two sequential PCM blocks,
    # each addressed by its own half of the start/end pairs, with the channel
    # bits 0x0020|0x0040 both set. Corpus-RE'd over 473 local banks (23.6% of
    # sample objects are stereo this way) — see RESOLUTION_NOTES §E4BSTEREO.
    is_stereo   = getattr(sample, 'channels', 1) == 2
    chan_bytes  = n_bytes // 2 if is_stereo else n_bytes   # bytes per channel
    start_r     = STRUCT_SZ + chan_bytes if is_stereo else 0

    hdr = bytearray(SAMP_HDR)

    # --- EMU4_E3S1_OFFSET prefix (2 bytes) ---
    struct.pack_into('>H', hdr, 0, sample_idx)     # [0-1]  index BE

    # --- struct emu3_sample fields (start at body[2]) ---
    hdr[2:18] = _name16(_sample_display_name(sample))  # [2-17] name + root note
    # [18-21] header = 0 (already zero from bytearray init)
    struct.pack_into('<I', hdr, 22, STRUCT_SZ)      # [22-25] start_l = 92
    end_l = STRUCT_SZ + chan_bytes - 2
    struct.pack_into('<I', hdr, 30, end_l)          # [30-33] end_l
    if is_stereo:
        struct.pack_into('<I', hdr, 26, start_r)            # [26-29] start_r
        struct.pack_into('<I', hdr, 34, start_r + chan_bytes - 2)  # [34-37] end_r
    # else [26-29]/[34-37] stay 0 (mono)

    # Loop points (in bytes from struct start).
    # EOS 4.x has exactly ONE loop type: a forward loop, toggled On/Off at the
    # *sample* level (EOS 4.0 manual, Sample Edit → Loop Type: only "On"/"Off").
    # There is NO ping-pong / forward-backward loop mode in EOS.  ALTERNATING
    # (ping-pong) loops are therefore rendered into the PCM as forward loops
    # upstream in write_e4b (processors/loop_renderer.py) — mirroring what EOS
    # itself does when importing EIII forward/backward loops — so by the time we
    # get here the sample is already FORWARD.  ALTERNATING is kept in the tuple
    # below only as a defensive fallback.
    # Options confirmed from JL AnalogBank hardware (K2 PWM Pad samples):
    #   0x0031 = MONO_L | bit4 | LOOP (forward)  — hardware-verified
    #   0x0020 = MONO_L, no loop
    has_loop = (sample.loop_type in (LoopType.FORWARD, LoopType.ALTERNATING)
                and sample.loop_end > sample.loop_start)
    if has_loop:
        lsl = sample.loop_start * 2 + STRUCT_SZ
        # loop_end_l stores the frame BEFORE the true inclusive last loop
        # frame (`sample.loop_end`), not loop_end itself — see the matching
        # `+1` in e4b_parser._parse_sample_body, which is where the round-trip
        # is enforced. (This used to cite a RESOLUTION_NOTES section that was
        # never written. The fact is stated here instead, which is what the
        # citation was standing in for -- and naming the dead section again,
        # even to explain its removal, is still a reference a reader will try
        # to follow.)
        lel = (sample.loop_end - 1) * 2 + STRUCT_SZ
        # LOOP IN RELEASE, bit 3 (0x08), added 2026-08-24.
        #
        # **The mechanism is confirmed audibly; this bit's identity is not.**
        # Set "Loop in release" on the panel and a looped sample's release
        # appears and runs at the calibrated rate; leave it off and the voice
        # LEAVES THE LOOP at note-off, plays out whatever data lies past the
        # loop end -- typically a few tens of milliseconds -- and stops. So
        # every looped sample this writer has ever produced had NO RELEASE AT
        # ALL. Not too fast: absent. Nobody noticed because you have to listen
        # for a release on a looped sample to see it (§E4BLOOPREL).
        #
        # Measured by eosed with the flag toggled on one sample, A/B/A:
        #     off  -54 dB -> floor within 0.2 s of note-off
        #     on   -54 -57 -63 -71 -77 -83 over 2.5 s, 14.09 dB/s
        #     off  instant again
        # 14.09 dB/s against 15.1 predicted for this rate byte and 15.2 measured
        # on the AKAI for the source's own RELSE1 -- so the flag, the rate law
        # and the AKAI-to-E4XT rate matching are confirmed together, to 7%.
        #
        # **WHY BIT 3 AND NOT ANOTHER: correlation, not proof.** Across 125 E4B
        # files the options word takes five values, not the two this writer
        # emits -- 0x0031 (1219), 0x0020 (240), 0x0039 (38), 0x0079 (6),
        # 0x0078 (1). The difference is bit 3 alone, and every file carrying it
        # is dated 2002-09-21, i.e. E-MU-era. The other 121 files, spanning
        # 2002 to 2026 and including everything this toolchain has made, never
        # set it.
        #
        # One co-varying detail was checked and does NOT confound it: bit-3
        # samples all have 6 frames past the loop end, but so do 815 samples
        # across 382 local banks against 45 carrying bit 3, and that field
        # takes 807 distinct values. The two are not locked together.
        #
        # The confirmation this still wants is a converted bank that sustains
        # through its release on the hardware. Until then the bit is the
        # leading candidate for WHERE the flag lives, and the flag itself is
        # not in doubt.
        options = 0x0039   # MONO_L | bit4 | LOOP | LOOP-IN-RELEASE
    else:
        lsl = STRUCT_SZ
        lel = end_l
        options = 0x0020   # MONO_L, no loop
    if is_stereo:
        options |= 0x0040          # left | RIGHT = stereo in one object

    struct.pack_into('<I', hdr, 38, lsl)            # [38-41] loop_start_l
    struct.pack_into('<I', hdr, 46, lel)            # [46-49] loop_end_l
    if is_stereo:
        # Per-channel loop points: the same frame offsets, rebased onto the
        # right block (lsR - startR == lsL - startL in every corpus sample).
        struct.pack_into('<I', hdr, 42, lsl - STRUCT_SZ + start_r)  # [42-45]
        struct.pack_into('<I', hdr, 50, lel - STRUCT_SZ + start_r)  # [50-53]
    # else [42-45]/[50-53] stay 0 (mono)

    struct.pack_into('<I', hdr, 54, sample.sample_rate)  # [54-57] sample_rate u32
    # [58-59] pitch correction — HARDWARE-RE'd 2026-07-24 (RESOLUTION_NOTES §E4BRATE).
    # EOS 4 does NOT derive playback pitch from [54-57] (that field is informational);
    # it plays a sample at effective_rate = 44100 · 2^(f58/768), where f58 is a SIGNED
    # 1/64-semitone offset here.  So a sample stored below 44.1 kHz with f58=0 plays
    # SHARP by 44100/rate (e.g. 27500 → +8.18 st).  Setting f58 = round(768·log2(rate/
    # 44100)) makes EOS play at the stored rate → in tune.  Verified against the E4XT's
    # own Sample-Rate-Convert output (6 rates 11025-48000, ±1 unit / ≤3 cents); 44100
    # → 0 so 44.1 kHz samples are byte-unchanged.  [18-21] stays 0 (a non-deterministic
    # per-sample token EOS sets on modify, NOT pitch — verified it varies across saves).
    if sample.sample_rate > 0 and sample.sample_rate != 44100:
        f58 = int(round(768.0 * math.log2(sample.sample_rate / 44100.0)))
        struct.pack_into('<h', hdr, 58, max(-32768, min(32767, f58)))
    struct.pack_into('<H', hdr, 60, options)             # [60-61] options
    struct.pack_into('<I', hdr, 62, STRUCT_SZ)           # [62-65] sample_data_offset_l = 92
    if is_stereo:
        struct.pack_into('<I', hdr, 66, start_r)         # [66-69] ..._offset_r
    # else [66-69] stays 0 (mono)
    # [70-93] parameters[6] = 0

    return bytes(hdr)


# ---------------------------------------------------------------------------
# Zone entry (22 bytes, secondary zone table)
# ---------------------------------------------------------------------------

#: Presets whose pivot shift ran past E4XT_VOL_MEASURED_FLOOR_DB, collected
#: during a write so `write_e4b` can report them once instead of per voice.
_LEVEL_CLAMPED: list = []


def _offset_level_db(base_db: float, offset_db: float) -> float:
    """Add a pivot offset to a level, clamped at the measured floor.

    `e4xt_volume_byte` will happily EXTRAPOLATE its fitted quadratic past
    E4XT_VOL_MEASURED_FLOOR_DB and stay monotonic, which is fine for a level
    the user asked for and wrong for one we are adding ourselves: below the
    floor the byte no longer stands for a measured number of dB, so the
    relative balance this offset exists to preserve stops being preserved.
    Clamp instead, and record it -- on 10,933 real presets this fires on 4.5%.
    """
    if not offset_db:
        return base_db
    want = base_db + offset_db
    if want < E4XT_VOL_MEASURED_FLOOR_DB:
        _LEVEL_CLAMPED.append(E4XT_VOL_MEASURED_FLOOR_DB - want)
        return E4XT_VOL_MEASURED_FLOOR_DB
    return want


def _zone_entry(zone: ZoneMapping, sample_idx: int, write_absolute: bool = False,
                level_offset_db: float = 0.0) -> bytes:
    """22-byte secondary zone entry.

    Decoded by ConvertWithMoss (git-moss/ConvertWithMoss #220, commit
    7ce000f) from the commercial library CD-ROMs:
      [12:14] fine-tune, signed BE i16, 1/64-semitone
      [15]    volume, signed byte, dB
      [16]    panning, signed byte, -64..+63

    NOT a delta on top of the voice's own vpar[36]/[54]/[55] — that was
    tried and disproven 2026-07-26. These are the zone's ABSOLUTE value,
    used only for a MULTI-zone voice; a single-zone voice instead writes
    its one zone's value into vpar[36]/[54]/[55] and leaves this entry at
    zero (`write_absolute=False`, the default) — see `_build_voice` for the
    hardware evidence (B.012 single-zone, B.013 + a from-first-principles
    ASYMTEST bank multi-zone, all through this exact writer).
    """
    entry = bytearray(ZONE_ENTRY)
    entry[2]  = min(127, zone.lo_key)
    entry[5]  = min(127, zone.hi_key)
    entry[6]  = min(127, zone.lo_vel)
    entry[9]  = min(127, zone.hi_vel)
    # Sample reference is a big-endian u16 at [10:12] (1-indexed), matching
    # the BE-u16 index convention used everywhere else in the format (E3S1
    # sample header [0:2], TOC entry [12:14]). EOS supports up to 1000
    # samples per bank (S000-S999 per the manual) — far beyond a single byte;
    # our earlier single-byte write at [11] only "worked" because every test
    # bank happened to stay under 256 samples (high byte [10] read as 0).
    struct.pack_into('>H', entry, 10, min(0xFFFF, sample_idx))
    if write_absolute:
        ft_64 = max(-32768, min(32767, round(zone.fine_tune * 64.0 / 100.0)))
        struct.pack_into('>h', entry, 12, ft_64)
        # dB -> the byte that actually DELIVERS that dB; writing the value
        # straight in delivers only half to three-quarters of it (§E4BFILTCAL).
        entry[15] = e4xt_volume_byte(
            _offset_level_db(zone.volume, level_offset_db)) & 0xFF
        entry[16] = e4xt_pan_byte(zone.pan) & 0xFF
    # HARDWARE-CONFIRMED 2026-08-16 on Jan's E4XT. This field is where the
    # machine gets its pitch from -- the sample's own root is carried only in
    # the NAME suffix, which EOS displays and does not play from. A calibration
    # bank of three sines written by this writer, played on the E4XT:
    #
    #     CALA3 root 57 at key 57  ->  219.9 Hz     (220 exact)
    #     CALA3 root 57 at key 69  ->  439.8 Hz     (+12 st)
    #     CALA3 root 57 at key 45  ->  109.9 Hz     (-12 st)
    #     CALA4 root 69 at key 69  ->  439.8 Hz
    #
    # A consistent ~0.8 cent flat reading, which is one digit of the tuner's
    # 0.1 Hz display -- at 110 Hz a single digit IS 1.6 cents. Root placement
    # and pitch ratio are both correct.
    #
    # Worth the note because the AKAI writer had exactly this field's analogue
    # WRONG until the same day: it wrote the sample's root and ignored the
    # zone's, and every multisample came out with a different error per
    # keygroup. The two writers share the architecture; only one shared the bug.
    entry[14] = min(127, zone.root_key)
    return bytes(entry)


# ---------------------------------------------------------------------------
# Voice block
# ---------------------------------------------------------------------------

# Primary zone table template (64 bytes) — based on hardware reference preset.
# ---------------------------------------------------------------------------
# Filter envelope helpers  (confirmed from B.005-FltEnvTest.E4B hardware diff)
# ---------------------------------------------------------------------------

# CR-13: the envelope rate↔time + level↔byte math now lives in models.common
# (single home for the writer and parser).  Thin local aliases keep the existing
# call sites and public re-exports (e.g. tests import _fenv_seconds) working.
_fenv_level   = env_level_to_byte
_fenv_rate    = env_seconds_to_rate
_fenv_seconds = env_rate_to_seconds
_fenv_sustain = env_sustain_to_byte
_env_level_db = env_level_byte_to_db      #: level byte -> dB below peak
_env_span_rate = env_span_seconds_to_rate #: (span_dB, seconds) -> rate byte
_env_db_per_s_to_rate = env_db_per_s_to_rate_byte  #: dB/s -> rate byte

#: Peak-to-silence distance, used only for the RELEASE complement. Taken as the
#: level law's own value at byte 0, so the two stages are internally consistent
#: rather than using two different notions of "silence". Inferred, not measured.
_ENV_FULL_SPAN_DB = env_level_byte_to_db(0)


# Primary zone table template (64 bytes) — regular key-tracking voice.
# Filter envelope at PZT[14:26]:
#   PZT[14]=0  PZT[15]=0      Attack1  rate=0,  level=0
#   PZT[16]=0  PZT[17]=0x7F   Attack2  rate=0,  level=+100  (default)
#   PZT[18]=0  PZT[19]=0x7E   Decay1   rate=0,  level=+99   (default)
#   PZT[20]=0  PZT[21]=0x7F   Decay2   rate=0,  level=+100  (default)
#   PZT[22]=20 PZT[23]=0      Release1 rate=20, level=0     (default)
#   PZT[24]=0  PZT[25]=0      Release2 rate=0,  level=0
_PRIMARY_ZONE_TMPL = bytes([
    0x00, 0x00, 0x00, 0x7F, 0x00, 0x7E, 0x00, 0x7F,
    0x14, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00,
    0x00, 0x7F, 0x00, 0x7E, 0x00, 0x7F, 0x14, 0x00,
    0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x7F,
    0x00, 0x7E, 0x00, 0x7F, 0x14, 0x00, 0x00, 0x00,
    0x03, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])

# Modulation-routing table (80 bytes, 20×4-byte PatchCord slots `[src,dst,amt,
# flag]`) — the EOS default cord set, extracted byte-for-byte from hardware
# voices.  A plain KT voice with no modulation carries an all-zero table; two
# things require the populated one:
#   1. Non-transpose voices: the E4XT needs it to recognise the voice as valid
#      (an all-zero table → invisible/silent on hardware).
#   2. **Filter-envelope voices** (KT *or* NT): the cord at **slot 5**
#      (`50 38 00 00` = src 0x50 Filter-Envelope → dst 0x38 Filter-Frequency;
#      the E4XT UI calls it "Cord 05") is what routes the filter envelope at
#      PZT[14:26] to the cutoff.  It is **amount 0 by default**, so the envelope
#      is inert until we set its amount byte (`mod[22]`).  Slot/amount confirmed
#      from B.010-CordAmountTest.E4B (UI cord N = storage slot N; amount at byte
#      index 2 of the cord), 2026-06-09.
# The filter-envelope SHAPE is written full-scale in PZT; its DEPTH is this cord
# amount = round(filter_env_cents × 127), signed.
_MOD_TMPL = bytes([
    0x0C, 0x40, 0x1E, 0x00, 0x10, 0x30, 0x08, 0x00,
    0x60, 0x30, 0x00, 0x00, 0x11, 0xAA, 0x10, 0x00,
    0x0C, 0x38, 0x00, 0x00, 0x50, 0x38, 0x00, 0x00,
    0x08, 0x38, 0x00, 0x00, 0x16, 0x08, 0x7F, 0x00,
]) + bytes(48)

# LFO1/LFO2 live in the Primary Zone Table, hardware-RE'd 2026-06-10 from
# B.011-LFO1 settings.E4B (see docs/E4B_FORMAT.md §4.2).  LFO2 is an exact +8
# mirror of LFO1:
#   PZT[42]/[50] Rate      0-127 (default 64 = 4.12 Hz)
#   PZT[43]/[51] Shape     signed enum (below)
#   PZT[44]/[52] Delay     0-127 -> 0-20 s
#   PZT[45]/[53] Variation 0-127 = 0-100 %
#   PZT[46]/[54] Sync      0 = Key Sync, 1 = Free Run
# Shape codes hardware-confirmed: Triangle=0, Sine=1, Sawtooth=2, Square=3,
# Random=-1 (0xFF), Hemi-quaver=15.  (Sine=1 confirmed from the 'LFO1+2 SINE'
# preset: PZT[43] and PZT[51] both = 01.)
_LFO_SHAPE_CODE = {
    'triangle': 0x00, 'sine': 0x01, 'sawtooth': 0x02,
    'square':   0x03, 'hemiquaver': 0x0F, 'random': 0xFF,
}
_LFO_DELAY_MAX_S = 20.0   # PZT[44]/[52] 0-127 -> 0-20 s

# LFO rate byte<->Hz lives in models.common (lfo_rate_hz_to_byte), shared with
# the parser and every source-format parser.  3-point log-quadratic fit
# (byte 0=0.08 Hz, 64=4.12 Hz, 127=18.01 Hz), refineable.

# LFO modulation cord ids (hardware-RE'd 2026-06-10 from B.011 P012).  Sources:
# LFO1~ (bipolar) = 0x60, LFO2~ = 0x68.  Dests: Pitch = 0x30, Filter-Freq = 0x38,
# Filter-Q (resonance) = 0x39.  The default cord table already carries LFO1→Pitch
# at slot 2; the others are written into free slots (8+).
_LFO_ROUTE_FIRST_FREE_SLOT = 8
# Amount-byte offsets of the default cords that route into Filter-Freq (`0x38`)
# and Pitch (`0x30`).  UI cord N = storage slot N; amount = byte index 2 of the
# cord (slot*4 + 2).  Source/dest ids confirmed from default-preset cords on the
# E4XT (2026-06-09): src 0x0C=Velocity, 0x08=Key, 0x50=FilterEnv, 0x60=LFO1.
_MOD_LFO_TO_PITCH_AMT   = 10   # slot 2: LFO1 → Pitch ("Cord 02", src 0x60 dst 0x30)
_MOD_LFO_TO_PITCH_SLOT  = 2    #   …its cord slot (for the wheel-gate dest 0xA8+2)
_MOD_WHEEL_GATE_SLOT    = 3    # slot 3: default ModWheel → C02Amt gate (template)
_MOD_VEL_TO_CUTOFF_AMT  = 18   # slot 4: Velocity → Filter-Freq ("Cord 04")
#: slot 0 amount: Vel< → AmpVol. The value the template carries (30 = 23.62 %
#: = 22.37 dB) is now a FALLBACK for sources that ask for a velocity response
#: without stating a measurable one, not an unconditional write.
_MOD_VEL_TO_VOL_AMT = 2
_MOD_VEL_TO_CUTOFF_SRC  = 16   #   …its source byte (slot 4 byte 0)
_MOD_FENV_TO_CUTOFF_AMT = 22   # slot 5: FilterEnv → Filter-Freq ("Cord 05")
_MOD_KEY_TO_CUTOFF_AMT  = 26   # slot 6: Key → Filter-Freq ("Cord 06")

# EOS modulation-source POLARITY variants (manual: "+, ~, <").  Each source has
# three processed forms — "+" ADDS to the initial value (normal: ctrl 0..127 →
# 0..+full), "~" centres on zero (−63..+64, for LFOs / Filt-Freq), "<" SUBTRACTS
# (ctrl 0..127 → −full..0).  The default EOS table ships **Vel<** (0x0C) on the
# Velocity→Filter cord — correct for the Velocity→Amp default (full at vel 127)
# but WRONG for filter velocity-tracking: with "<", vel 127 only reaches the base
# cutoff and softer notes merely darken, so the filter never opens *above* base.
# Source-ID polarity block confirmed on the E4XT 2026-06-12: 0x0B reads as
# "Vel~", 0x0C as "Vel<" — so the consecutive triplet is `[+, ~, <]` =
# `[0x0A, 0x0B, 0x0C]` → **Vel+ = 0x0A**.  We want the ADD form so vel 0 = base
# cutoff and vel 127 = base + depth (matches SFZ `fil_veltrack` etc.).  (Vel~
# would centre on vel 64 and darken softer notes below base — wrong semantics;
# Vel< only ever subtracts, the original bug.)
_SRC_VEL_PLUS = 0x0A

# Mod-wheel→LFO-depth gating (KeygroupWheelToLfo), RE'd 2026-06-13 from
# B.013-RE_SUITE CrdAmt.E4B.  ModWheel source = 0x11; the "Cord N Amount"
# modulation destinations are linear: dst = _CORD_AMT_DEST_BASE + N for N=0..23
# (0xA8..0xBF).  We split each LFO→dest cord (depth D) into a static part
# D*(1-wheel) written to that cord's amount, plus a ModWheel→CordN-Amount cord
# of D*wheel in a free slot — so at wheel 0 the LFO sits at D*(1-wheel) and at
# full wheel it reaches the full programmed depth D.
_SRC_MOD_WHEEL      = 0x11
_CORD_AMT_DEST_BASE = 0xA8


def _set_cord(mod: bytearray, slot: int, src: int, dst: int,
              amount: float, flag: int = 0) -> None:
    """CR-18: write a PatchCord [src, dst, amount, flag] into mod-table `slot`
    (4 bytes each), replacing the magic `slot*4 + n` offset arithmetic."""
    o = slot * 4
    mod[o]     = src & 0xFF
    mod[o + 1] = dst & 0xFF
    mod[o + 2] = cord_amount_to_byte(amount)
    mod[o + 3] = flag & 0xFF


def _build_voice(voice: VoiceLayer, sample_name_to_idx: dict, is_last: bool,
                 level_offset_db: float = 0.0) -> bytes:
    # NT secondary voices use the same structure as KT voices with vpar[38]=0x01.
    # Confirmed from B.030-1V-2V-3V_2.E4B P012 V2 (hardware-created NT secondary):
    # P012 V2 == P011 V2 (KT) in every byte except vpar[38]=0x01.
    # Earlier "B.025 special format" (no zones, vpar[16]=sidx) was wrong.

    # ── per-voice tuning/volume/pan ─────────────────────────────────────────
    # transpose/coarse_tune have no per-zone storage at all (unlike fine_tune/
    # volume/pan below), so they're always taken from a representative zone
    # regardless of zone count.  fine_tune in ZoneMapping is cents; convert
    # to 64ths.
    _tp  = next((z.transpose    for z in voice.zones if getattr(z, 'transpose',    0)), 0)
    _ct  = next((z.coarse_tune  for z in voice.zones if getattr(z, 'coarse_tune',  0)), 0)
    # fine_tune/volume/pan: NOT a voice-value + per-zone-delta composition —
    # that model was tried and DISPROVEN 2026-07-26 (an asymmetric multi-zone
    # test, both B.013 hand-built on hardware and an ASYMTEST bank built by
    # this exact writer, showed the front panel displays/stores each zone's
    # RAW ABSOLUTE value, not a delta from any voice-level representative;
    # B.013's real zone volumes were already asymmetric — [+10,0,0,-96,0,0,0]
    # — yet the firmware still wrote vpar[54]=0, not their midpoint).
    # The real, much simpler rule (see `_zone_entry`):
    #   exactly 1 zone  -> its value goes to vpar[36]/[54]/[55]; its own zone
    #                       entry stays zero (matches B.012).
    #   2+ zones        -> vpar[36]/[54]/[55] stay zero; EACH zone writes its
    #                       own absolute value into its own zone entry.
    _multi = len(voice.zones) > 1
    if _multi:
        _ft = _vol = _pan = 0.0
    else:
        _z0 = voice.zones[0] if voice.zones else None
        _ft  = _z0.fine_tune if _z0 else 0.0
        _vol = _z0.volume    if _z0 else 0.0
        _pan = _z0.pan       if _z0 else 0.0
    _ft_64 = max(-64, min(63, round(_ft * 64.0 / 100.0)))

    # ── zone table ────────────────────────────────────────────────────────
    zones_raw = bytearray()
    voice_lo_vel, voice_hi_vel = 127, 0
    voice_lo_key, voice_hi_key = 127, 0
    for zone in voice.zones:
        idx = sample_name_to_idx.get(zone.sample_name, 0)
        if idx < 1:
            # Empty name = unassigned zone, which is the only case that occurs
            # (all 36 unresolved references over a 9 535-zone corpus are '').
            # A NON-empty name that does not resolve means the parser emitted a
            # zone pointing at a sample it did not write -- an internal
            # inconsistency worth surfacing rather than dropping in silence.
            if zone.sample_name:
                print(f"  [WARN] zone keys {zone.lo_key}-{zone.hi_key} names "
                      f"sample '{zone.sample_name}', which is not in the bank "
                      f"-- dropped. This means a parser emitted a zone "
                      f"pointing at a sample it did not write.")
            continue
        zones_raw += _zone_entry(zone, idx, write_absolute=_multi,
                                 level_offset_db=level_offset_db)
        voice_lo_vel = min(voice_lo_vel, zone.lo_vel)
        voice_hi_vel = max(voice_hi_vel, zone.hi_vel)
        voice_lo_key = min(voice_lo_key, zone.lo_key)
        voice_hi_key = max(voice_hi_key, zone.hi_key)
    if voice_lo_vel > voice_hi_vel:
        voice_lo_vel, voice_hi_vel = 0, 127
    if voice_lo_key > voice_hi_key:      # no valid zones → full-range fallback
        voice_lo_key, voice_hi_key = 0, 127

    n_zones = len(zones_raw) // ZONE_ENTRY

    # ── voice params (110 bytes) ───────────────────────────────────────────
    # vpar[2:4] = big-endian u16 byte offset (relative to this voice's own
    #   start) where the zone table's trailing entry begins, i.e.
    #   VOICE_FIXED + n_zones*ZONE_ENTRY.  E4XT uses this to locate/validate
    #   the next voice — confirmed against 14 data points (zone counts 1-62)
    #   from B.025, B.030-1V-2V-3V and the B.010-bisect-bank differential
    #   series: formula matches exactly in every case.
    # vpar[4] = n_zones: E4XT navigation formula (vpar[4]+1)*22 = zone table bytes.
    #   No MARKER needed — confirmed from a commercial SFX library and a commercial loop library commercial files.
    vpar = bytearray(110)
    _trailer_off = VOICE_FIXED + n_zones * ZONE_ENTRY
    vpar[2]  = (_trailer_off >> 8) & 0xFF
    vpar[3]  = _trailer_off & 0xFF
    vpar[4]  = min(255, n_zones)
    vpar[7]  = 0x64
    # Voice key window vpar[14]=low / vpar[17]=high (crossfades [15]/[16]=0) —
    # hardware-RE'd 2026-06-14 (RE_SUITE2 VOICE KEYWIN: C1/C5 → [14]=36,[17]=84).
    # Set from the voice's zone span so a voice no longer claims C-2..G8.
    vpar[14] = min(127, voice_lo_key)
    vpar[17] = min(127, voice_hi_key)
    vpar[18] = min(127, voice_lo_vel)
    vpar[21] = min(127, voice_hi_vel)
    vpar[25] = 0x7F
    # Per-voice tuning bytes (hardware-RE'd 2026-06-13 from RE_SUITE CT JL.E4B):
    #   vpar[34] = Key Transpose (semitones, −24..+24): keyboard pitch offset
    #   vpar[35] = Coarse Tune  (semitones, −72..+24): repitches/stretches sample
    #   vpar[36] = Fine Tune    (1/64-semitone units, −64..+63): ~1.56 cents/unit
    # _tp/_ct/_ft/_ft_64/_vol/_pan computed above, before the zone loop.
    vpar[34] = max(-128, min(127, int(_tp))) & 0xFF
    vpar[35] = max(-128, min(127, int(_ct))) & 0xFF
    vpar[36] = _ft_64 & 0xFF
    vpar[38] = 0x01 if voice.non_transpose else 0x00
    # vpar[42] = Chorus Amount (Voice/Tuning page). Hardware-confirmed 2026-06-08:
    # UI 0-100% maps linearly to 0-127 (round(pct/100*127)); verified against
    # commercial banks (Dutch Stab 50%->64/89%->113, Ya Tech 17/34/35%) and a
    # 25/50/75/100% -> 32/64/95/127 sweep on a hand-edited E4XT save. 0 = off.
    vpar[42] = min(127, round(max(0.0, min(1.0, voice.chorus_amount)) * 127))
    vpar[51] = 0x80
    # vpar[54] = Volume (Voice page), vpar[55] = Pan (Voice page) — both
    # HARDWARE-CONFIRMED 2026-07-26 via a 7-voice differential save (B.012
    # "Vce VolPan", one zone per voice): front-panel Volume +10/-96/+5/-50 ->
    # vpar[54] exactly; Pan +63/-64/+32/-32 -> vpar[55] exactly. Signed byte;
    # Volume in dB (0 = unity, matches ZoneMapping's -96..+12 dB convention
    # exactly — -96 was one of the test values); Pan -64=full-L..0=centre..
    # +63=full-R. (Earlier vpar[54] comment "0x00 = max, higher = quieter"
    # was an untested guess predating this confirmation.)
    #
    # READ THAT CONFIRMATION NARROWLY. It establishes that the FRONT PANEL
    # displays the byte we write -- nothing more. For vpar[54] that turned out
    # to be a different thing from the audio: writing the dB value straight in
    # delivered only half to three-quarters of the requested attenuation until
    # it was measured and corrected on 2026-07-31 (§E4BFILTCAL). vpar[55] pan
    # rests on the SAME differential save and the same reasoning, so its audio
    # law is likewise unmeasured -- we do not actually know that pan -64
    # produces full-left, nor that the law between the endpoints is linear.
    # vpar[42] Chorus Amount below carried the same weak evidence, but was
    # MEASURED on 2026-08-01 and came out right: amount maps linearly to
    # detune depth (spectral width 0.45 / 4.55 / 9.09 / 13.64 / 19.09 Hz at
    # 0/25/50/75/100%, with the beat rate tracking it — two independent
    # readings of the same quantity, which is the check that it is real). So
    # the linear UI-to-byte mapping does produce a linear audible effect.
    #
    # Two independent parameters have now failed this way, so panel agreement
    # is recorded here as insufficient evidence for any LEVEL or AMOUNT law.
    # Only a measurement counts.
    # ONLY meaningful for a single-zone voice (_vol/_pan are pre-set to 0.0
    # above when the voice has 2+ zones — see the per-zone entries instead;
    # a second hardware test showed this is NOT a voice-value + per-zone-
    # delta composition, the multi-zone case simply doesn't use these bytes).
    vpar[54] = e4xt_volume_byte(_offset_level_db(_vol, level_offset_db)) & 0xFF
    vpar[55] = e4xt_pan_byte(_pan) & 0xFF
    vpar[58] = _XPM_FILTER_TYPE.get(voice.filter_type, 0x00)
    # The 0-1 `filter_cutoff` is the SHARED internal position, defined by the
    # documented 57 Hz..20 kHz law. Convert it to the frequency it is meant to
    # mean, then ask for the position the E4XT actually renders there -- the
    # real curve tops out near 4.1 kHz with a bypass endpoint, so a nominal
    # 0.7 (3.4 kHz) would otherwise sound at 1.2 kHz. See §E4BFILTCAL.
    # The model carries Hz since 2026-08-25, so there is nothing to
    # reconstruct: this used to raise the nominal scale to a stored position,
    # which is the step that lost every corner below 57 Hz.
    _nominal_hz = max(E4B_CUTOFF_MIN_HZ,
                      min(E4B_CUTOFF_MAX_HZ, voice.filter_cutoff))
    vpar[60] = min(255, round(e4xt_cutoff_position(_nominal_hz) * 255))
    # SATURATION: A FULLY OPEN FILTER MUST STAY FULLY OPEN.
    #
    # The reader's measured table saturates -- bytes 252..255 all read back as
    # position 1.0 -- while this Hz path returns 251 for that position, so a
    # wide-open filter came back four bytes down. Measured over 131 real
    # third-party banks 2026-08-24: `filter_cutoff` changed on **95.5% of
    # round-tripped zones**, which is simply how common a wide-open filter is.
    #
    # It settles rather than ramps (255 -> 251 -> 251, a fixed point), so the
    # harm is one step at the very top of the range and not a drift. Fixed
    # anyway, because "the two ends of one law disagree" is the shape that has
    # produced most of this week's defects, and because a source that says
    # WIDE OPEN should not be written as slightly closed.
    #
    # Only the saturated end is touched. The Hz path below saturation is the
    # hardware-calibrated one (§E4BFILTCAL) and is left exactly as it was.
    if voice.filter_cutoff >= E4B_CUTOFF_MAX_HZ:
        vpar[60] = 255
    # RESONANCE through the MEASURED curve, since 2026-08-24 (§E4XTQCAL).
    # This was `round(resonance * 127)` -- an uncalibrated linear guess on a
    # field whose response is not linear in anything audible, exactly the shape
    # of the K2000 filter-envelope depth fixed on 2026-08-22 (23x too little at
    # low amounts, 1.75x too much at full).
    #
    # Two things the measurement changed. The byte now targets a PEAK HEIGHT IN
    # dB rather than a fraction of the field, because dB is what is audible and
    # a fraction is meaningless across machines with different ranges. And it
    # clamps at 112, not 127: bytes 112..127 are the same filter, 17.8 dB flat
    # within noise, while the panel goes on printing whatever was set.
    #
    # 4-pole is exactly twice the dB at the same byte, measured at every point,
    # so `poles` covers the whole lowpass family from one table.
    _poles = 4 if voice.filter_type in (3, 4, 5) else 2
    vpar[61] = e4xt_resonance_byte(voice.filter_resonance, _poles)
    # Band-stop (15-18) AND band-boost (19-22) both map to Swept EQ 1-oct
    # (vpar[58]=0x20), where vpar[61] is GAIN, not Q — they are the SAME parametric
    # band filter, differing only in gain SIGN: band-stop cuts, band-boost boosts.
    # Depth scales with the MPC resonance (±12 dB .. ±24 dB).  Gain law hardware-RE'd
    # 2026-06-14 (RE_SUITE2): gain_dB = (byte − 64) × 0.375 (byte 64 = 0 dB).
    if vpar[58] == _SWEPT_EQ_1OCT:
        res = max(0.0, min(1.0, voice.filter_resonance))
        if 19 <= voice.filter_type <= 22:        # BB band-boost → +gain
            gain_db = +(12.0 + 12.0 * res)
        else:                                    # BS band-stop → −gain (cut)
            gain_db = -(12.0 + 12.0 * res)
        vpar[61] = max(0, min(127, round(gain_db / _SWEPT_EQ_DB_PER_STEP) + 64))

    # vpar[0]/[1] are 0 in every hardware-saved bank — they are NOT the amp
    # envelope (the earlier corpus RE mis-attributed them).  The amp envelope is
    # the full 6-stage rate/level block at PZT[0:12] (written below).
    vpar[0] = 0
    vpar[1] = 0

    # Zone-table trailer: voices are packed back-to-back with NO gap and NO
    # terminator entry between them — the next voice's vpar header begins
    # immediately at this_voice_start + VOICE_FIXED + n_zones*ZONE_ENTRY
    # (= vpar[2:4]). What earlier analysis mistook for a 22-byte "lo>hi
    # terminator entry" was actually just the next voice's own vpar header
    # bytes (vpar[2] = high byte of ITS trailer offset, always ≥1 since every
    # voice is >255 bytes; vpar[5] = always 0) — which coincidentally satisfy
    # "lo>hi" when misread as a zone entry. Writing a real 22-byte terminator
    # shifts the next voice 22 bytes later than where E4XT looks for it,
    # landing on garbage — exactly the "voice count = 1" symptom.
    # Confirmed self-consistent with ZERO leftover bytes across 4 independent
    # confirmed-working multi-voice examples (B.030 P010/P011/P012, B.010
    # "P000+V2"): every non-last voice has NO trailer, and only the LAST voice
    # in the preset gets exactly 2 trailing bytes `00 00` (then end of body).
    if is_last:
        zones_raw += bytes(2)

    # ── primary zone table: amp envelope (PZT[0:12]) + optional filter env ──
    # Amp envelope is 6 rate/level stages (Atk1/2, Dcy1/2, Rls1/2), levels
    # unipolar 0..+100%.  Hardware-confirmed 2026-06-08 (B.006-AMPENV_SETME.E4B:
    # the E4XT Amp Envelope page writes exactly these 12 bytes).  Standard-ADSR
    # mapping (manual: "set the '2' levels = the '1' levels and the '2' rates to
    # 0"): Attack rises to full, Decay falls to the sustain level (held through
    # Decay 2), Release falls to silence.  PZT[4]=Decay1 rate confirmed by the
    # AMP_DECAY_CAL.E4B sweep (only PZT[4] varies); rate→time fit calibrated
    # below (_ENV_RATE_A/_ENV_RATE_K).
    pzt = bytearray(_PRIMARY_ZONE_TMPL)
    # Sustain uses _fenv_sustain (NOT _fenv_level): the amp-envelope Level%
    # target is exponential/dB-law on real hardware, not linear amplitude
    # (hardware-measured 2026-07-28, docs/RESOLUTION_NOTES.md §E4BLEVEL) --
    # a naive linear encoding plays far quieter than intended. Attack/Release
    # below stay on _fenv_level since 100%/0% are unaffected endpoints.
    sus = _fenv_sustain(voice.env_sustain)
    # THE RATE BYTE NEEDS THE SPAN. §ENVSPAN, hardware 2026-08-18: the byte is a
    # slew rate and the decay is linear in dB, so a stage's time is its dB
    # distance over that rate. `_fenv_rate` takes a time alone and is therefore
    # only right at the span its calibration used -- AMP_DECAY_CAL.E4B set
    # sustain=0 so the decay was audible, i.e. a full fall to silence. Every
    # decay to a non-zero sustain was too fast: 1.5x at sustain byte 80, 15x at
    # byte 122, worst exactly where real presets live.
    #
    # ATTACK IS DELIBERATELY UNCHANGED. It rises from silence, where the dB
    # distance is unbounded, so the model cannot apply as written. eosed's panel
    # evidence says attack is NOT a different mechanism -- the machine's own
    # page shows every segment as `seg | rate | level%` alike -- so it probably
    # obeys the same law from a floor, and that floor is simply unmeasured. The
    # fix is one measurement, not a new model.
    decay_span = _env_level_db(sus)
    pzt[0] = min(127, _fenv_rate(voice.env_attack)); pzt[1] = _fenv_level(100.0)  # Atk1 → full
    pzt[2] = 0;                                      pzt[3] = _fenv_level(100.0)  # Atk2 hold full
    # A DECAY TO SILENCE MUST NOT ENCODE TO A RATE THAT IS SILENT.
    # `_env_span_rate` clamps a too-fast request to 0, and rate 0 with a zero
    # sustain closes the envelope before any audio leaves the voice -- measured
    # by eosed, not inferred. So a source asking for a 10 ms cut got an
    # inaudible layer instead of a brief one. Floor it at the fastest rate that
    # actually sounds; the nearest expressible burst approximates the request
    # far better than nothing does. Only when a decay was ASKED FOR and it
    # falls to silence: rate 0 into a non-zero sustain is a legitimate instant
    # jump and is left alone.
    _dcy = _env_span_rate(decay_span, voice.env_decay)
    if _dcy < E4B_MIN_AUDIBLE_DECAY_RATE and voice.env_decay > 0.0 and sus == 0:
        _dcy = E4B_MIN_AUDIBLE_DECAY_RATE
    pzt[4] = _dcy;                                   pzt[5] = sus                 # Dcy1 → sustain
    pzt[6] = 0;                                      pzt[7] = sus                 # Dcy2 hold sustain
    # RELEASE: sustain -> silence, i.e. the COMPLEMENT of the decay span.
    # INFERRED, not measured. What eosed measured is that release rate is
    # INDEPENDENT of the sustain level -- t-40dB held at 0.193 s +/- 0.022
    # across the whole sustain sweep, flat with the scatter of a 10 ms metric
    # rather than a trend. That constrains the independence; the span
    # arithmetic `full - decay` is the part still unmeasured, and it is one
    # cheap bank to settle (fixed sustain, sweep the release byte, read t-40dB).
    #
    # AND A CARRIED RATE WINS OVER BOTH (§AKAIRELSPAN, 2026-08-24). The span
    # arithmetic below is only as good as `_ENV_FULL_SPAN_DB`, which is this
    # machine's level law evaluated at byte 0 -- not a floor anyone metered.
    # The AKAI's equivalent is 60.07 dB, equally unmeasured, and matching
    # SECONDS across the two made every AKAI-sourced release 1.6-4x too fast
    # while leaving the decay right to 1-7%. The decay stops at the sustain
    # level, which both machines agree on; the release stops at "silence",
    # which neither of them defines.
    #
    # So when the reader knew its own rate law it hands us the rate, and the
    # rate goes straight to a byte. Sources that genuinely specify a duration
    # (MPC, XPM) carry `None` and take the span path exactly as before.
    rel_span = max(0.0, _ENV_FULL_SPAN_DB - decay_span)
    _rel_rate = getattr(voice.amp_env, 'release_rate_db_per_s', None)
    pzt[8] = (_env_db_per_s_to_rate(_rel_rate) if _rel_rate
              else _env_span_rate(rel_span, voice.env_release))
    pzt[9] = _fenv_level(0.0)
    pzt[10] = 0;                                     pzt[11] = _fenv_level(0.0)   # Rls2 stay 0
    # Filter-envelope SHAPE — always written (§O, 2026-06-13).  Its depth/sign is
    # the Cord 05 (FilterEnv→FilterFreq) amount in the mod table (set below only
    # when filter_env_cents>0), so at amount 0 the env is inert/inaudible — but
    # writing the source curve preserves it for the E4XT display and for later use
    # if the depth is turned up on the hardware.  Mirrors how the E4XT stores it.
    sus = 100.0 * max(0.0, min(1.0, voice.filter_env_sustain))
    pzt[14] = _fenv_rate(voice.filter_env_attack);  pzt[15] = _fenv_level(100.0)
    pzt[16] = 0;                                     pzt[17] = _fenv_level(100.0)
    # ── THE FILTER ENVELOPE'S SPAN IS IN THE WRONG UNIT, AND IT CANCELS ────
    #
    # This block used to claim "the span is still the dB distance that byte
    # represents". That was an assumption stated as a fact, and it is wrong
    # (§E4BFENVUNIT, 2026-08-24). Read what actually happens below:
    #
    #   _fsus_byte   comes from _fenv_level -- a SIGNED -100..+100 percent
    #                encoding, x127/100
    #   _fdecay_span feeds that byte to env_level_byte_to_db, which is the
    #                AMPLITUDE SUSTAIN-BYTE law (dB below peak = 97.82 -
    #                0.7718 x byte). Different encoding, different quantity.
    #   _frel_span   subtracts it from the AMPLITUDE full span, in dB
    #   _env_span_rate applies the AMPLITUDE rate law to the result
    #
    # ...for an envelope the E4XT runs on a CUTOFF BYTE scale: §56 measured the
    # envelope-to-cutoff depth as linear in cutoff bytes, not in octaves and
    # not in dB.
    #
    # IT IS LEFT ALONE ON PURPOSE. Swept over 30 combinations of filter sustain
    # (10-100%) and release (0.1-8 s), what this emits lands within 2-3 bytes of
    # the machine's own measured filter law -- worst case 1.19x in time. The
    # unit error and a 0.52x difference in the rate prefactor very nearly
    # cancel, and the offset is NEAR-CONSTANT, which is the tell: shape right,
    # anchor off.
    #
    # Correcting it needs a reference we do not have. The filter law (§43) was
    # measured on a transition UPWARD to target 100; nobody has measured the
    # release segment. Correcting a 1.19x error against an assumed reference is
    # how a 1.19x error becomes a 1.4x one.
    #
    # AND NOTE THE THREE LAWS IN SIX LINES: the ATTACK below goes through
    # _fenv_rate (env_seconds_to_rate, the time-alone law) while the decay and
    # release go through _env_span_rate (the span law). One envelope, two
    # conventions, plus the unit mismatch above. Nothing in the output is
    # visibly wrong today -- which is exactly how the amplitude rate anchor
    # stayed 13-19% wrong for months behind a residual small enough to write
    # off. If you are here to change this function, change all three together
    # and measure first.
    _fsus_byte = _fenv_level(sus)
    _fdecay_span = _env_level_db(_fsus_byte)
    pzt[18] = _env_span_rate(_fdecay_span, voice.filter_env_decay)
    pzt[19] = _fsus_byte
    pzt[20] = 0;                                     pzt[21] = _fsus_byte
    pzt[22] = _env_span_rate(max(0.0, _ENV_FULL_SPAN_DB - _fdecay_span),
                             voice.filter_env_release)
    pzt[23] = _fenv_level(0.0)
    pzt[24] = 0;                                     pzt[25] = _fenv_level(0.0)

    # ── LFO1 (PZT[42:46]) + LFO2 (PZT[50:54], +8 mirror) ───────────────────
    # Hardware-RE'd 2026-06-10 (B.011-LFO1 settings.E4B).  The template already
    # carries the EOS defaults (rate 64=4.12 Hz, triangle, no delay/variation,
    # key-sync), so only overwrite a byte when the model specifies that field —
    # voices with no LFO data round-trip byte-identically.
    def _write_lfo(base, rate, shape, delay, variation, sync):
        if rate is not None:
            pzt[base]     = lfo_rate_hz_to_byte(rate)
        if shape is not None:
            pzt[base + 1] = _LFO_SHAPE_CODE.get(shape, 0x00)
        if delay is not None:
            pzt[base + 2] = min(127, round(max(0.0, delay) / _LFO_DELAY_MAX_S * 127))
        if variation is not None:
            pzt[base + 3] = min(127, round(max(0.0, min(1.0, variation)) * 127))
        if sync is not None:
            pzt[base + 4] = 0x01 if sync else 0x00
    _write_lfo(42, voice.lfo1_rate, voice.lfo1_shape, voice.lfo1_delay,
               voice.lfo1_variation, voice.lfo1_sync)
    _write_lfo(50, voice.lfo2_rate, voice.lfo2_shape, voice.lfo2_delay,
               voice.lfo2_variation, voice.lfo2_sync)

    # Write the EOS default cord table for NT voices (validity) and for any voice
    # that uses a mod routing we can fill in (filter envelope / keytrack /
    # velocity → Filter-Freq); plain unmodulated KT voices keep an all-zero table.
    # Each depth goes into its cord's amount byte, signed −1..+1 → −127..+127.
    _q = cord_amount_to_byte                       # CR-13: shared codec
    # Triangle phase: the E4XT key-synced triangle rises first (+amount → pitch
    # up), but the MPC triangle falls first — so negate a triangle LFO's cord
    # amounts (to every destination, keeping them in phase) to match the MPC's
    # starting direction.  Hardware-RE'd 2026-06-14 (RE_SUITE2 TRI PHASE).
    _lfo1_sign = -1.0 if voice.lfo1_shape == 'triangle' else 1.0
    _lfo2_sign = -1.0 if voice.lfo2_shape == 'triangle' else 1.0
    # LFO→Filter/Q (and LFO2→Pitch) have no default cord — they go into free
    # slots (8+) as [src, dst, amount, 0].  src/dst ids hardware-RE'd from B.011.
    _extra_cords = [
        (0x60, 0x38, voice.lfo1_to_filter   * _lfo1_sign),  # LFO1 → Filter-Freq
        (0x60, 0x39, voice.lfo1_to_filter_q * _lfo1_sign),  # LFO1 → Filter-Q
        (0x68, 0x30, voice.lfo2_to_pitch    * _lfo2_sign),  # LFO2 → Pitch
        (0x68, 0x38, voice.lfo2_to_filter   * _lfo2_sign),  # LFO2 → Filter-Freq
        (0x68, 0x39, voice.lfo2_to_filter_q * _lfo2_sign),  # LFO2 → Filter-Q
    ]
    has_extra = any(abs(a) > 0.01 for _, _, a in _extra_cords)
    # FILTER DEPTHS CONVERT THROUGH THE CORNER, FROM THIS VOICE'S OWN BASE.
    #
    # The model states them in cents (2026-08-25) and the cord moves the cutoff
    # BYTE linearly, so what a given depth costs in cord amount depends on
    # where this voice's cutoff already sits. There is no cents-per-cord
    # constant that would be right -- §FENVFULLSCALE spent three days with two
    # of them, 41% apart, and the answer was that the quantity is not constant.
    # `vpar[60]` is set above and is exactly the base these need.
    #
    # SATURATION IS RE-SATURATED, not re-derived. When the requested corner is
    # already at the end of the cutoff byte, MANY amounts reach it and the
    # conversion above picks the smallest that does -- so a third-party bank's
    # full-amount cord would be rewritten smaller on every round trip, sounding
    # identical and reading differently. 36.5% of the nonzero filter depths in
    # 60 real banks saturate, so this is the common case, not an edge one.
    def _cord(cents, units=1.0):
        amt = e4xt_cents_to_cord_amount(vpar[60], cents, source_units=units)
        if amt and e4xt_cord_saturates(vpar[60], amt) and abs(amt) < 100.0:
            return math.copysign(100.0, amt)
        return amt
    _fenv_amt = _cord(voice.filter_env_cents)
    _vel_amt = _cord(voice.velocity_to_filter_cents, E4XT_VEL_SOURCE_UNITS)
    # VELOCITY -> VOLUME, slot 0 of the template. THREE STATES (§KRZAMPVEL's
    # E4B half; Jan's decision 2026-09-01):
    #
    #   known swing    -> write it
    #   requested,     -> keep the template's own value; the source asked for a
    #     unscaled        response and silencing it would be worse than
    #                     carrying an unmeasured one
    #   nothing known  -> write NO velocity->volume cord
    #
    # Until 2026-09-01 every voice got the template's 23.62 % regardless, which
    # eosed's measured law makes **22.37 dB of velocity swing that no source
    # asked for** -- imposed even on an AKAI program whose V_LOUD is 0, a value
    # s3ked measured as genuinely neutral to 0.00001 dB/unit.
    #
    # PIVOT: written as `Vel<` (pivot 127), the template's own source and the
    # convention the E4XT and its factory library use. An AKAI swing pivots at
    # 64 and is therefore NOT reproduced exactly -- constructing that needs
    # `Vel+` plus a static trim of -swing/2, which runs out of range against
    # E4XT_VOL_MEASURED_FLOOR_DB on the loudest real sources. That trade is
    # still Jan's to make; this is the status-quo half of it.
    _vv_db = getattr(voice, 'velocity_to_volume_db', None)
    _vv_req = bool(getattr(voice, 'velocity_to_volume_requested', False))
    if _vv_db is not None:
        _vv_byte = max(-127, min(127, int(round(
            abs(_vv_db) / E4XT_VEL_AMPVOL_DB_PER_PERCENT * 127.0 / 100.0))))
    elif _vv_req:
        _vv_byte = _MOD_TMPL[_MOD_VEL_TO_VOL_AMT]
    else:
        _vv_byte = 0

    needs_mod = (voice.non_transpose
                 or _vv_byte != 0
                 or _q(_fenv_amt / 100.0) not in (0, 256)
                 or _q(key_track_to_filter_amount(voice.filter_keytrack)) not in (0, 256)
                 or _q(_vel_amt / 100.0) not in (0, 256)
                 or _q(voice.lfo1_to_pitch) not in (0, 256)
                 or has_extra)
    if needs_mod:
        mod = bytearray(_MOD_TMPL)
        mod[_MOD_VEL_TO_VOL_AMT] = _vv_byte & 0xFF
        # Mod-wheel→LFO-depth gating: split each LFO cord (depth D) into a static
        # part D*(1-Kw) + a ModWheel→CordN-Amount cord of D*Kw (Kw=0 → unchanged).
        Kw = max(0.0, min(1.0, voice.wheel_to_lfo))
        gate = Kw > 0.01
        _static = (lambda d: d * (1.0 - Kw)) if gate else (lambda d: d)
        # THRESHOLD IS THE ENCODED BYTE, NOT AN ARBITRARY FRACTION.
        # This was `> 0.01`, which was harmless while the AKAI vibrato depth
        # was 6x too large and became a silent dropout the moment that was
        # fixed: the measured depth for a real program is 0.00799, just under
        # the old line, so the cord was never written and the vibrato vanished
        # again after having just been repaired (§AKAILPTCH).
        #
        # The only threshold that means anything is whether the value survives
        # quantisation — if it encodes to a non-zero byte it is audible and
        # belongs in the file.
        if _q(voice.lfo1_to_pitch) not in (0, 256):
            _lfo1_pitch = voice.lfo1_to_pitch * _lfo1_sign   # triangle phase fix
            mod[_MOD_LFO_TO_PITCH_AMT] = _q(_static(_lfo1_pitch))
            if gate:
                # slot 3 is already ModWheel→C02Amt in the template; set its depth.
                _set_cord(mod, _MOD_WHEEL_GATE_SLOT, _SRC_MOD_WHEEL,
                          _CORD_AMT_DEST_BASE + _MOD_LFO_TO_PITCH_SLOT,
                          _lfo1_pitch * Kw)
        if _q(_fenv_amt / 100.0) not in (0, 256):
            mod[_MOD_FENV_TO_CUTOFF_AMT] = _q(_fenv_amt / 100.0)
        # The model carries oct/oct; the cord carries a fraction of this
        # machine's 0.713 oct/oct full scale. Converted here rather than
        # stored converted, so a source asking for more than the E4XT can do
        # saturates at the WRITER (which is the hardware's honest answer) and
        # not in the model (which would lose it for every other format too).
        _ktb = _q(key_track_to_filter_amount(voice.filter_keytrack))
        if _ktb not in (0, 256):
            mod[_MOD_KEY_TO_CUTOFF_AMT] = _ktb
        if _q(_vel_amt / 100.0) not in (0, 256):
            # Source = Vel+ (ADD, anchored at base for vel 0); the DIRECTION is the
            # sign of the (signed) amount: +amount → harder opens the filter above
            # base, −amount → harder closes it below base.  (The old default Vel<
            # subtracted, anchoring HARD notes at base — wrong for veltrack.)
            #
            # Vel+ spans 2.08 cord units over velocity 0..127, so the same
            # cents need 2.08x LESS amount here than on a unit source -- that
            # span is `E4XT_VEL_SOURCE_UNITS` and it is why the old
            # VEL_FILTER_FULL_CENTS was FILTER_ENV_FULL_CENTS times 2.08.
            mod[_MOD_VEL_TO_CUTOFF_SRC] = _SRC_VEL_PLUS
            mod[_MOD_VEL_TO_CUTOFF_AMT] = _q(_vel_amt / 100.0)
        slot = _LFO_ROUTE_FIRST_FREE_SLOT
        for src, dst, amt in _extra_cords:
            if abs(amt) > 0.01 and slot < 20:
                _set_cord(mod, slot, src, dst, _static(amt))   # CR-18 cord builder
                lfo_slot = slot
                slot += 1
                if gate and slot < 20:   # ModWheel → this cord's amount (0xA8+slot)
                    _set_cord(mod, slot, _SRC_MOD_WHEEL,
                              _CORD_AMT_DEST_BASE + lfo_slot, amt * Kw)
                    slot += 1
        mod = bytes(mod)
    else:
        mod = bytes(80)
    fixed = (bytes(vpar)
             + bytes(pzt)
             + bytes(16)
             + mod
             + bytes(14))

    return fixed + bytes(zones_raw)


# ---------------------------------------------------------------------------
# E4P1 preset chunk body
# ---------------------------------------------------------------------------

def _split_by_velocity(voice: VoiceLayer):
    """One voice per distinct velocity window.

    E4B switches velocity at the VOICE, not the zone: §5.2 of
    docs/E4B_FORMAT.md records that writing per-zone velocity without a
    matching vpar[18]/vpar[21] makes velocity-switched layers "layer instead
    of switch" -- every layer sounding at once. vpar[18]/[21] are the min/max
    over the voice's zones, so a single voice holding zones with DIFFERENT
    windows collapses to one window spanning them all, and the switch is gone.

    A source that puts velocity layers in one VoiceLayer therefore has to be
    split before writing. `parse_sample_dir` does exactly that for a folder
    that names velocities, and any per-zone-velocity source (SFZ, SF2, XPM)
    can too.

    Note the round-trip through this project's own parser does NOT show the
    fault: e4b_parser intersects the voice window with the zone entry's own
    velocity bytes, which this writer also emits, so it reconstructs the
    distinction the hardware would have lost. Reported by VinSamLib, whose
    container reader reads the voice window alone.

    Zone order is preserved within each window, and a voice whose zones all
    share one window is returned unchanged -- so output for every existing
    source is byte-identical.
    """
    windows = []
    for zone in voice.zones:
        key = (zone.lo_vel, zone.hi_vel)
        if key not in windows:
            windows.append(key)
    if len(windows) <= 1:
        return [voice]
    out = []
    for lo_vel, hi_vel in windows:
        clone = copy.copy(voice)
        clone.zones = [z for z in voice.zones
                       if (z.lo_vel, z.hi_vel) == (lo_vel, hi_vel)]
        out.append(clone)
    return out


def _build_preset_body(preset: Preset, preset_idx: int,
                       sample_name_to_idx: dict) -> bytes:
    # Velocity switches at the voice, so a voice holding several windows must
    # become several voices -- see _split_by_velocity.
    voices = []
    for v in preset.voices:
        split = _split_by_velocity(v)
        if len(split) > 1:
            print(f"  [INFO] preset '{preset.name}': a voice carries "
                  f"{len(split)} velocity windows — split into {len(split)} "
                  f"voices, since E4B switches velocity per voice")
        voices.extend(split)
    num_voices = len(voices)
    hdr = bytearray(PRES_HDR)

    struct.pack_into('>H', hdr, 0, preset_idx)   # [0-1]  index
    hdr[2:18] = _name16(preset.name)             # [2-17] name
    hdr[18]   = 0x00                             # [18]   null
    hdr[19]   = 0x52                             # [19]   constant
    struct.pack_into('>H', hdr, 20, num_voices)  # [20-21] num_voices
    hdr[28]   = 0x78                             # [28]   volume 120
    if num_voices > 1:
        hdr[41] = 0x04                           # [41]   multi-voice flag (confirmed B.025 + a commercial string library)
        hdr[43] = 0x01                           # [43]   multi-voice flag
    # [52-55] constant marker
    hdr[52], hdr[53], hdr[54], hdr[55] = 0x52, 0x23, 0x00, 0x7E
    # [56-59] MIDI any-note/any-channel
    hdr[56] = hdr[57] = hdr[58] = hdr[59] = 0xFF

    # VELOCITY-PIVOT OFFSET. We write the source's swing as `Vel<`, which
    # attenuates from velocity 127; a source that rotates about some other
    # velocity therefore sits a CONSTANT S*(127-P_src)/126 off, and a constant
    # in dB is a level, not a curve. Repairing it upward would need headroom
    # the volume field does not have, so the whole preset moves DOWN by its own
    # largest offset instead: inter-voice balance comes out exact and only the
    # preset's overall loudness changes. Jan's call, 2026-09-04.
    _shift = velocity_pivot_preset_shift(voices, E4XT_VEL_PIVOT['Vel<'])
    voice_parts = []
    last = num_voices - 1
    _before = len(_LEVEL_CLAMPED)
    for i, v in enumerate(voices):
        _off = velocity_pivot_offset_db(
            getattr(v, 'velocity_to_volume_db', None),
            getattr(v, 'velocity_to_volume_pivot', None),
            E4XT_VEL_PIVOT['Vel<']) - _shift
        voice_parts.append(_build_voice(v, sample_name_to_idx,
                                        is_last=(i == last),
                                        level_offset_db=_off))
    if len(_LEVEL_CLAMPED) > _before:
        _lost = _LEVEL_CLAMPED[_before:]
        print(f"  [INFO] preset '{preset.name}': velocity-pivot shift of "
              f"{_shift:.1f} dB ran past the measured volume floor on "
              f"{len(_lost)} level(s); clamped, up to {max(_lost):.1f} dB of "
              f"the correction not applied")
    voice_data = b''.join(voice_parts)
    return bytes(hdr) + voice_data


# ---------------------------------------------------------------------------
# TOC entry (32 bytes)
# ---------------------------------------------------------------------------

def _toc_entry(tag: bytes, data_size: int, file_offset: int,
               idx: int, name: str, midi_prog: int = 0) -> bytes:
    e = bytearray(32)
    e[0:4]  = tag
    struct.pack_into('>I', e, 4,  data_size)
    struct.pack_into('>I', e, 8,  file_offset)
    struct.pack_into('>H', e, 12, idx)
    e[14:30] = _name16(name)
    e[30]    = 0x00   # null
    e[31]    = min(127, max(0, midi_prog)) & 0xFF   # MIDI program (0 = any)
    return bytes(e)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def write_e4b(bank: Bank, output_path: str) -> None:
    """Serialize a Bank to an E4B file (FORM E4B0 / EOS 4.x format)."""
    print(f"Writing E4B: {output_path}")
    print(f"  {len(bank.presets)} preset(s), {len(bank.samples)} sample(s)")

    # EOS has no ping-pong loop mode, so render any ALTERNATING (ping-pong)
    # loops into the PCM as plain forward loops (processors/loop_renderer.py).
    # Names are preserved, so zone→sample references still resolve.  Work on a
    # local list — never mutate the caller's bank (it may be written to other
    # formats too).
    del _LEVEL_CLAMPED[:]        # per-write, not per-process
    samples = [bake_alternating_loop(s) for s in bank.samples]
    n_baked = sum(1 for s in bank.samples if s.loop_type == LoopType.ALTERNATING)
    if n_baked:
        print(f"  Rendered {n_baked} ping-pong loop(s) into PCM as forward loops")

    # sample name → 1-based index (E3S1 indices start at 1)
    sample_name_to_idx = {s.name: (i + 1) for i, s in enumerate(samples)}

    # ── build raw chunk bodies ────────────────────────────────────────────
    e4ma_body    = _build_e4ma()

    # CR-16: build only the small per-sample HEADERS in memory and stream each
    # sample's PCM straight to disk below — the previous code concatenated every
    # sample's PCM through sample_bodies → sample_chunks → form_content → output,
    # holding ~5 full copies of the bank's audio at peak (~640 MB on a 128 MB
    # bank).  Now peak ≈ 1× (just the source bank).
    sample_headers   = []
    sample_body_lens = []        # body = 94-byte header + PCM (no copy made)
    for i, s in enumerate(samples):
        hdr = _build_sample_header(s, i + 1)
        sample_headers.append(hdr)
        sample_body_lens.append(len(hdr) + _pcm_bytes_written(s))
        print(f"  Sample [{i+1:02d}] '{s.name}': {_pcm_bytes_written(s)} bytes PCM")

    preset_bodies = []
    for i, p in enumerate(bank.presets):
        body = _build_preset_body(p, i, sample_name_to_idx)
        preset_bodies.append(body)
        n_zones = sum(len(v.zones) for v in p.voices)
        print(f"  Preset '{p.name}': {len(p.voices)} voice(s), {n_zones} zone(s)")

    # ── compute offsets from sizes only (no PCM touched) ──────────────────
    n_toc     = 1 + len(bank.presets) + len(samples)
    toc_chunk = _iff_chunk(TOC_TAG, bytes(n_toc * 32))   # size placeholder
    e4ma_chunk    = _iff_chunk(E4MA_TAG, e4ma_body)
    preset_chunks = [_iff_chunk(PRES_TAG, b) for b in preset_bodies]

    def _chunk_len(body_len):    # IFF: 4 tag + 4 size + body + word-align pad
        return 8 + body_len + (body_len & 1)

    # File layout: FORM(4)+SIZE(4)+E4B0(4) = 12 bytes, then chunks
    pos = 12 + len(toc_chunk)
    e4ma_off = pos
    pos += len(e4ma_chunk)

    preset_offs = []
    for c in preset_chunks:
        preset_offs.append(pos)
        pos += len(c)

    sample_offs = []
    for blen in sample_body_lens:
        sample_offs.append(pos)
        pos += _chunk_len(blen)

    # ── build real TOC ────────────────────────────────────────────────────
    toc_entries = bytearray()
    toc_entries += _toc_entry(E4MA_TAG, len(e4ma_body),
                               e4ma_off, 0, 'Multimap')
    for i, p in enumerate(bank.presets):
        toc_entries += _toc_entry(PRES_TAG, len(preset_bodies[i]),
                                   preset_offs[i], i, p.name,
                                   midi_prog=p.program_number)
    for i, s in enumerate(samples):
        toc_entries += _toc_entry(SAMP_TAG, sample_body_lens[i],
                                   sample_offs[i], i + 1, s.name)

    toc_chunk = _iff_chunk(TOC_TAG, bytes(toc_entries))   # same length as placeholder

    # EMSt master-setup chunk is always the LAST chunk and is NOT listed in the
    # TOC (matches hardware-saved banks).
    emst_chunk = _iff_chunk(EMST_TAG, _build_emst())
    pos += len(emst_chunk)        # pos is now the total file size

    # FORM size uses the EMU convention, NOT standard IFF: it counts the chunk
    # bytes only and excludes the 4-byte 'E4B0' form type, so it is 4 less than
    # the standard value (== filesize - 12).  This is what hardware writes and
    # what reference loaders (e.g. emu.tools e-xplorer) validate against; the
    # standard IFF size is 4 too large and triggers an "IFF length mismatch".
    # The declared FORM boundary therefore stops 4 bytes short of EOF — inside
    # the trailing zeros of the EMSt chunk (deliberate: the E4XT enforces the
    # FORM boundary strictly when streaming from CD, so the clipped 4 bytes must
    # land in throwaway EMSt padding, not the last sample's PCM — hence EMSt last).
    form_size = pos - 12

    # ── stream to disk ────────────────────────────────────────────────────
    with atomic_write(output_path) as f:
        f.write(FORM_MAGIC)
        f.write(struct.pack('>I', form_size))
        f.write(FORM_TYPE)
        f.write(toc_chunk)
        f.write(e4ma_chunk)
        for c in preset_chunks:
            f.write(c)
        for i, s in enumerate(samples):
            blen = sample_body_lens[i]
            f.write(SAMP_TAG)
            f.write(struct.pack('>I', blen))   # IFF chunk size
            f.write(sample_headers[i])
            # PCM streamed — never copied. Stereo is de-interleaved to the
            # E4B's planar (all-left-then-all-right) layout first; that copy
            # is unavoidable and only affects stereo samples.
            f.write(_interleaved_to_planar(s.data)
                    if getattr(s, 'channels', 1) == 2 else s.data)
            if blen & 1:
                f.write(b'\x00')               # IFF word-align pad
        f.write(emst_chunk)

    print(f"  Written: {output_path} ({pos/1024/1024:.2f} MB)")
