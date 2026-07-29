# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# EIII binary layout, constants and conversion tables derived from:
#   emu3bm (GPL-2.0), David García Goñi, https://github.com/dagargo/emu3bm
#     (also available locally at ../emu3bm; ../emu3fs is the companion
#     filesystem project both this project and ConvertWithMoss build on).
#   Cross-checked against ConvertWithMoss's independent re-verification of
#   emu3bm's model (documentation/design/EIII_FORMAT.md, PR #230/#231,
#   https://github.com/git-moss/ConvertWithMoss), which corrected three
#   details (empty keymap/sample-table slots are holes not terminators; ESI
#   sample-index flag bits; EIII/EIIIX filter is fixed low-pass) against 22
#   commercial library CD-ROMs. No source code was copied; this module is an
#   independent re-implementation against mpc2emu's own Bank/Preset/
#   VoiceLayer/ZoneMapping model. See docs/EIII_FORMAT.md for the full
#   reference and this project's own scope decisions (no per-zone LFO, no
#   EOS-calibrated key/velocity-to-filter translation — see the notes below).
#
# Written banks have not yet been hardware-confirmed; see TODO.md.
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
E-mu EIII Bank Writer (.E3X / .ESI)
------------------------------------
Produces a bank file readable by the Emulator IIIX / ESI-32/2000/4000, and
(the reason this format is worth having) natively loadable by the E4XT's
backward-compatibility loader — see docs/EIII_FORMAT.md.

Unlike E4B/KRZ (multi-voice-per-preset engines with a general mod matrix),
an EIII preset holds only ONE primary-layer set of note zones. mpc2emu's
`Preset.voices` (one VoiceLayer per instrument layer) is therefore written
as a *chain* of linked EIII presets — one per VoiceLayer, each carrying that
layer's zones and velocity extent, linked via the preset `link` field so
they play together. This mirrors how the EIII sampler itself stacks more
than two velocity layers.

All multi-byte values are little-endian (EIII/ESI, unlike E4B/KRZ, is not
68k-derived). Sample positions are byte offsets, not frame indices.
"""

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models.common import Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType, ensure_mono
from processors.loop_renderer import bake_alternating_loop


# ---------------------------------------------------------------------------
# Structural constants (ported from Emulator3Constants.java)
# ---------------------------------------------------------------------------

NAME_LENGTH            = 16
PRESET_SIZE             = 142
NOTE_ZONE_SIZE          = 4
ZONE_SIZE               = 48
SAMPLE_HEADER_SIZE      = 92
NUM_KEYS                = 88
KEY_OFFSET              = 21                # E-mu key 0 = MIDI note 21 (A-1)
SAMPLE_ADDRESS_OFFSET   = 0x400000
BLOCK_SIZE              = 512
UNUSED                  = 0xFF
MAX_SAMPLE_RATE         = 44100
EMPTY_BANK_SIZE         = 0x2B73

LOWEST_KEY              = KEY_OFFSET
HIGHEST_KEY             = KEY_OFFSET + NUM_KEYS - 1

# Bank header fields
BANK_NAME               = 0x10
BANK_OBJECTS            = 0x20
BANK_NEXT_PRESET        = 0x30
BANK_NEXT_SAMPLE        = 0x34
BANK_PRESET_BLOCKS      = 0x3C
BANK_SAMPLE_BLOCKS      = 0x40
BANK_TOTAL_BLOCKS       = 0x48
BANK_NAME_COPY          = 0x4C
BANK_SELECTED_PRESET    = 0x5C

# Preset fields
PRESET_PITCH_BEND_RANGE        = 0x2C
PRESET_VELOCITY_PRIMARY_LOW    = 0x2D
PRESET_VELOCITY_PRIMARY_HIGH   = 0x2E
PRESET_VELOCITY_SECONDARY_LOW  = 0x2F
PRESET_VELOCITY_SECONDARY_HIGH = 0x30
PRESET_LINK                    = 0x31
PRESET_NUM_NOTE_ZONES          = 0x35
PRESET_KEY_MAPPINGS            = 0x36

# Note zone fields
NOTE_ZONE_PRIMARY   = 2
NOTE_ZONE_SECONDARY = 3

# Zone fields
ZONE_ORIGINAL_KEY             = 0
ZONE_SAMPLE_INDEX             = 1
ZONE_SAMPLE_INDEX_MASK        = 0x3FFF
ZONE_PARAMETER_A              = 3
ZONE_VCA_ENVELOPE             = 4
ZONE_VCF_CUTOFF                = 12
ZONE_VCF_Q                     = 13
ZONE_VCF_ENVELOPE_AMOUNT       = 14
ZONE_VCF_ENVELOPE              = 15
ZONE_AUX_ENVELOPE              = 20
ZONE_AUX_ENVELOPE_AMOUNT       = 25
ZONE_AUX_ENVELOPE_DESTINATION  = 26
ZONE_VELOCITY_TO_VCA_LEVEL      = 28
ZONE_VELOCITY_TO_VCF_CUTOFF     = 32
ZONE_VCA_LEVEL                 = 40
ZONE_NOTE_TUNING                = 41
ZONE_VCF_TRACKING               = 42
ZONE_NOTE_ON_DELAY              = 43
ZONE_VCA_PAN                    = 44
ZONE_VCF_TYPE_LFO_SHAPE         = 45
ZONE_REALTIME_ENABLE            = 46
ZONE_FLAGS                      = 47

# Envelope stages (5 bytes)
ENVELOPE_ATTACK  = 0
ENVELOPE_HOLD    = 1
ENVELOPE_DECAY   = 2
ENVELOPE_SUSTAIN = 3
ENVELOPE_RELEASE = 4
ENVELOPE_SIZE    = 5

# Sample fields
SAMPLE_START_LEFT         = 0x14
SAMPLE_START_RIGHT        = 0x18
SAMPLE_END_LEFT           = 0x1C
SAMPLE_END_RIGHT          = 0x20
SAMPLE_LOOP_START_LEFT    = 0x24
SAMPLE_LOOP_START_RIGHT   = 0x28
SAMPLE_LOOP_END_LEFT      = 0x2C
SAMPLE_LOOP_END_RIGHT     = 0x30
SAMPLE_RATE               = 0x34
SAMPLE_PLAYBACK_RATE      = 0x38
SAMPLE_OPTIONS            = 0x3A
SAMPLE_DATA_OFFSET_LEFT   = 0x3C
SAMPLE_DATA_OFFSET_RIGHT  = 0x40

# Sample option flags
OPTION_LOOP            = 0x0001
OPTION_LOOP_IN_RELEASE = 0x0008
OPTION_CHANNEL_LEFT    = 0x0020
OPTION_CHANNEL_RIGHT   = 0x0040
OPTION_STEREO          = OPTION_CHANNEL_LEFT | OPTION_CHANNEL_RIGHT

# Zone flags
ZONE_FLAG_NON_TRANSPOSE = 0x02
ZONE_FLAG_DISABLE_LOOP  = 0x20
ZONE_FLAG_DISABLE_LEFT  = 0x40
ZONE_FLAG_DISABLE_RIGHT = 0x80
Q_REALTIME_ENABLE       = 0x80
REALTIME_ENABLE_ALL     = 0xFF
PARAMETER_A_EMULATOR_3X = 0x1F

DEFAULT_CUTOFF   = 0xEF
FULL_LEVEL       = 0x7F
CENTER_PAN       = 0x40

# Neutral (no key tracking) value for ZONE_VCF_TRACKING. ConvertWithMoss's
# Emulator3Constants defines a NO_VCF_TRACKING=0x40 for this, but that value
# is inconsistent with its own documented -127..127 signed-byte scale (0x40
# = +64, not 0) and with its own Detector's inverse formula — round-tripping
# a bank written with 0x40 back through that formula yields ~full positive
# tracking, not none. Since this writer doesn't attempt to translate
# mpc2emu's filter_keytrack into this byte anyway (see _write_zone), the
# literal, scale-independent neutral value 0 is used instead, which is
# self-consistent with parsers/eiii_parser.py's inverse read.
_ZONE_TRACKING_NEUTRAL = 0

DEFAULT_REALTIME_CONTROLS = bytes([1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 1, 8])

# Device limits (docs/EIII_FORMAT.md "Device requirements when writing")
MAX_BANK_SIZE       = 128 * 1024 * 1024
MINIMUM_LOOP_LENGTH = 10
NUM_SILENT_FRAMES   = 2

_INITIAL_NEXT_PRESET = 0x2B27

_MASTER_SETTINGS = bytes([
    0xFF, 0xFF, 0x00, 0x00, 0x00, 0xFE, 0xFF, 0xFF, 0x28, 0x00,
    0x02, 0x00, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])

_TUNING_TABLE = [
    0x17037, 0x17027, 0x17029, 0x1702B, 0x1702C,
    0x1702E, 0x17030, 0x17032, 0x17033, 0x17035,
]


# ---------------------------------------------------------------------------
# Conversion tables (ported verbatim from Emulator3Constants.java)
# ---------------------------------------------------------------------------

# Times in seconds of the 128 values of an envelope stage (attack, hold,
# decay, release — all three envelopes share this table).
_ENVELOPE_TIME = [
    0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08,
    0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17,
    0.18, 0.19, 0.20, 0.21, 0.22, 0.23, 0.25, 0.26, 0.28,
    0.29, 0.32, 0.34, 0.36, 0.38, 0.41, 0.43, 0.46, 0.49,
    0.52, 0.55, 0.58, 0.62, 0.65, 0.70, 0.74, 0.79, 0.83,
    0.88, 0.93, 0.98, 1.04, 1.10, 1.17, 1.24, 1.31, 1.39,
    1.47, 1.56, 1.65, 1.74, 1.84, 1.95, 2.06, 2.18, 2.31,
    2.44, 2.59, 2.73, 2.89, 3.06, 3.23, 3.42, 3.62, 3.82,
    4.04, 4.28, 4.52, 4.78, 5.05, 5.34, 5.64, 5.97, 6.32,
    6.67, 7.06, 7.46, 7.90, 8.35, 8.83, 9.34, 9.87, 10.45,
    11.06, 11.70, 12.38, 13.11, 13.88, 14.70, 15.56, 16.49, 17.48,
    18.53, 19.65, 20.85, 22.13, 23.50, 24.97, 26.54, 28.24, 30.06,
    32.02, 34.15, 36.44, 38.93, 41.64, 44.60, 47.84, 51.41, 55.34,
    59.70, 64.56, 70.03, 76.22, 83.28, 91.40, 100.87, 112.09, 125.65,
    142.36, 163.69,
]

# Cutoff frequencies in Hertz of the 256 values of the filter cutoff parameter.
_CUTOFF_FREQUENCY = [
    26, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35,
    36, 37, 39, 40, 41, 42, 44, 45, 47, 48, 50,
    51, 53, 55, 56, 58, 60, 62, 64, 66, 68, 70,
    72, 75, 77, 80, 82, 85, 87, 90, 93, 96, 99,
    102, 106, 109, 112, 116, 120, 124, 128, 132, 136, 140,
    145, 149, 154, 159, 164, 169, 175, 180, 186, 192, 198,
    204, 211, 217, 224, 231, 239, 246, 254, 262, 271, 279,
    288, 297, 307, 316, 327, 337, 348, 359, 370, 382, 394,
    407, 419, 433, 447, 461, 475, 491, 506, 522, 539, 556,
    574, 592, 611, 630, 650, 671, 692, 714, 737, 760, 784,
    809, 835, 861, 889, 917, 946, 976, 1007, 1039, 1072, 1106,
    1141, 1178, 1215, 1254, 1294, 1335, 1377, 1421, 1466, 1512, 1560,
    1610, 1661, 1714, 1768, 1825, 1882, 1942, 2004, 2068, 2133, 2201,
    2271, 2343, 2417, 2494, 2573, 2655, 2739, 2826, 2916, 3009, 3104,
    3203, 3304, 3409, 3518, 3629, 3744, 3863, 3986, 4112, 4243, 4378,
    4517, 4660, 4808, 4960, 5118, 5280, 5448, 5621, 5799, 5983, 6173,
    6368, 6570, 6779, 6994, 7216, 7444, 7680, 7924, 8175, 8434, 8702,
    8978, 9262, 9556, 9859, 10171, 10493, 10826, 11169, 11522, 11887, 12264,
    12652, 13053, 13466, 13892, 14332, 14785, 15253, 15736, 16233, 16747, 17276,
    17823, 18386, 18967, 19566, 20185, 20822, 21480, 22158, 22858, 23580, 24324,
    25091, 25883, 26699, 27541, 28409, 29305, 30228, 31181, 32163, 33176, 34220,
    35297, 36407, 37553, 38734, 39951, 41207, 42502, 43836, 45213, 46632, 48095,
    49604, 51160, 52763, 54417, 56121, 57879, 59691, 61559, 63484, 65469, 67515,
    69625, 71799, 74040,
]

# Panorama in percent of the 128 values of the panorama parameter (0 = fully
# left, 64 = centered, 127 = fully right).
_PANORAMA = [
    -100, -99, -97, -96, -94, -93, -91, -90, -88, -86, -85, -83, -82, -80, -79,
    -77, -75, -74, -72, -71, -69, -68, -66, -65, -63, -61, -60, -58, -57, -55,
    -54, -52, -50, -49, -47, -46, -44, -43, -41, -40, -38, -36, -35, -33, -32,
    -30, -29, -27, -25, -24, -22, -21, -19, -18, -16, -15, -13, -11, -10, -8,
    -7, -5, -4, -2, 0, 1, 3, 4, 6, 7, 9, 11, 12, 14, 15,
    17, 19, 20, 22, 23, 25, 26, 28, 30, 31, 33, 34, 36, 38, 39,
    41, 42, 44, 46, 47, 49, 50, 52, 53, 55, 57, 58, 60, 61, 63,
    65, 66, 68, 69, 71, 73, 74, 76, 77, 79, 80, 82, 84, 85, 87,
    88, 90, 92, 93, 95, 96, 98, 100,
]

# E4B cutoff position (0.0-1.0, ZoneMapping-adjacent VoiceLayer.filter_cutoff
# domain) <-> Hz, exponential 57 Hz - 20 kHz.  Inverse of models.common's
# hz_to_e4b_cutoff — reused here only to decode the *shared* internal-model
# convention (VoiceLayer.filter_cutoff is always stored in this position
# form, regardless of target format), not because EIII's own cutoff curve
# has anything to do with E4B/EOS.
_E4B_CUTOFF_MIN_HZ = 57.0
_E4B_CUTOFF_MAX_HZ = 20000.0


def _e4b_cutoff_position_to_hz(position: float) -> float:
    position = max(0.0, min(1.0, position))
    return _E4B_CUTOFF_MIN_HZ * (_E4B_CUTOFF_MAX_HZ / _E4B_CUTOFF_MIN_HZ) ** position


# ---------------------------------------------------------------------------
# Bank format variants
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BankFormat:
    identifier:          str    # 15 chars, NUL-terminated on disk
    device_name:         str
    file_ending:          str
    sample_area_marker:   int
    preset_table_offset:  int
    sample_table_offset:  int
    preset_area_offset:   int
    max_presets:          int
    max_samples:          int
    is_esi:                bool = False
    preset_address_bias:   int = 0   # only EMULATOR_THREE biases its table


# The two writable, non-compact variants (matches ConvertWithMoss's own
# scope — EMULATOR_THREE's biased/compact address tables are write-unsupported
# here, but still readable — see EMULATOR_THREE/ALL_BANK_FORMATS below, used
# by parsers/eiii_parser.py).
EMULATOR_3X = BankFormat(
    identifier='EMULATOR 3X    ', device_name='Emulator IIIX', file_ending='.e3x',
    sample_area_marker=0x74, preset_table_offset=0x17CA, sample_table_offset=0x1BD2,
    preset_area_offset=0x2B72, max_presets=256, max_samples=999, is_esi=False)

ESI_32_V3 = BankFormat(
    identifier='EMU SI-32 v3   ', device_name='ESI-32/2000/4000', file_ending='.esi',
    sample_area_marker=0xEE, preset_table_offset=0x17CA, sample_table_offset=0x1BD2,
    preset_area_offset=0x2B72, max_presets=256, max_samples=999, is_esi=True)

EMULATOR_THREE = BankFormat(
    identifier='EMULATOR THREE ', device_name='Emulator III', file_ending='.e3b',
    sample_area_marker=0x00, preset_table_offset=0x6C, sample_table_offset=0x204,
    preset_area_offset=0x74A, max_presets=100, max_samples=99, is_esi=False,
    preset_address_bias=0x1A6FE)

BANK_FORMATS = {'e3x': EMULATOR_3X, 'esi': ESI_32_V3}          # writable targets
ALL_BANK_FORMATS = (EMULATOR_3X, ESI_32_V3, EMULATOR_THREE)    # readable variants


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _get_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into('<H', data, offset, value & 0xFFFF)


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into('<I', data, offset, value & 0xFFFFFFFF)


def _put_s8(data: bytearray, offset: int, value: int) -> None:
    data[offset] = int(round(value)) & 0xFF


def _encode_name(data: bytearray, offset: int, name: str) -> None:
    """Write a 16-char space-padded name; non-printable/non-ASCII -> '?'."""
    text = (name or '').encode('ascii', errors='replace')
    for i in range(NAME_LENGTH):
        c = text[i] if i < len(text) else ord(' ')
        data[offset + i] = c if 32 <= c < 127 else ord('?')


def _find_closest(table: List[float], value: float) -> int:
    best, best_dist = 0, float('inf')
    for i, t in enumerate(table):
        d = abs(t - value)
        if d < best_dist:
            best, best_dist = i, d
    return best


def _envelope_time_value(seconds: float) -> int:
    return _find_closest(_ENVELOPE_TIME, max(0.0, seconds))


def _cutoff_value(hz: float) -> int:
    return _find_closest(_CUTOFF_FREQUENCY, hz)


def _panning_value(panning: float) -> int:
    percent = round(max(-1.0, min(1.0, panning)) * 100)
    best, best_dist = 0, None
    for i, p in enumerate(_PANORAMA):
        d = abs(p - percent)
        if best_dist is None or d < best_dist:
            best, best_dist = i, d
    return best


def _encode_playback_rate(sample_rate: int) -> int:
    if sample_rate >= MAX_SAMPLE_RATE:
        return 0
    return 0xF800 | (int(-9799 + 1108 * math.log(sample_rate)) & 0x7FF)


# ---------------------------------------------------------------------------
# Empty bank skeleton (header + address tables + device-state block)
# ---------------------------------------------------------------------------

def _create_empty_bank(bank_format: BankFormat, name: str) -> bytearray:
    data = bytearray(EMPTY_BANK_SIZE)

    identifier = bank_format.identifier.encode('ascii')
    data[0:len(identifier)] = identifier
    _encode_name(data, BANK_NAME, name)
    _encode_name(data, BANK_NAME_COPY, name)

    _put_u32(data, 0x24, 1)
    _put_u32(data, 0x28, 1)
    _put_u32(data, 0x2C, 1)
    _put_u32(data, BANK_NEXT_PRESET, _INITIAL_NEXT_PRESET)
    _put_u32(data, 0x38, 0x00800000)
    _put_u32(data, BANK_SELECTED_PRESET, 0xFFFFFFFF)
    _put_u32(data, 0x60, 1)

    # The address table of the original (compact) Emulator III format, which
    # the later bank variants still carry unused at a fixed offset.
    compact_bias = 0x1A6FE
    for i in range(101):   # EMULATOR_THREE.max_presets(100) + 1
        _put_u32(data, 0x6C + i * 4, compact_bias)

    data[0x6E2:0x6E2 + len(_MASTER_SETTINGS)] = _MASTER_SETTINGS
    data[0x6F6:0x6F6 + len(_MASTER_SETTINGS)] = _MASTER_SETTINGS
    for i in range(17):
        data[0x76C + i] = FULL_LEVEL
    for i in range(16):
        data[0x78E + i] = 0xFF
    data[0xE96] = ord('T')
    data[0xE97] = ord('M')
    for i, v in enumerate(_TUNING_TABLE):
        _put_u32(data, 0xE98 + i * 4, v)

    # Settings only the EIIIX writes; ESI leaves them at zero. mpc2emu always
    # writes the EIIIX variant of this block since both non-compact targets
    # (EMULATOR_3X, ESI_32_V3) share the byte layout in every EIIIX-family
    # bank observed by emu3bm/ConvertWithMoss; only ESI's own firmware clears
    # it, which we cannot distinguish from "identical to EIIIX" without a
    # real ESI-written sample to diff against.
    if not bank_format.is_esi:
        data[0x394:0x394 + 4] = bytes([0xFF, 0xFF, 0xFF, 0x01])
        data[0x6D1] = 0x01
        data[0x74C] = 0xFF
        data[0x74D] = 0xFF
        data[0x79F] = 0x01

    # Last entry of the sample address table points behind the last sample.
    _put_u32(data, bank_format.sample_table_offset + bank_format.max_samples * 4,
             SAMPLE_ADDRESS_OFFSET)
    # Filler byte separating the (empty) preset area from the sample area.
    data[bank_format.preset_area_offset] = bank_format.sample_area_marker
    return data


# ---------------------------------------------------------------------------
# Envelope / zone / preset serialization
# ---------------------------------------------------------------------------

def _write_envelope(data: bytearray, offset: int, env, full_sustain: bool = False) -> None:
    """Write a 5-byte envelope. `env=None` (or `full_sustain`) writes the
    neutral/bypass envelope (instant, full sustain, no release)."""
    if env is None:
        data[offset + ENVELOPE_SUSTAIN] = FULL_LEVEL
        return
    data[offset + ENVELOPE_ATTACK]  = _envelope_time_value(env.attack)
    data[offset + ENVELOPE_HOLD]    = 0   # not modeled by mpc2emu's Envelope
    data[offset + ENVELOPE_DECAY]   = _envelope_time_value(env.decay)
    sustain = max(0.0, min(1.0, env.sustain))
    data[offset + ENVELOPE_SUSTAIN] = int(round(sustain * FULL_LEVEL))
    data[offset + ENVELOPE_RELEASE] = _envelope_time_value(env.release)


def _write_zone(data: bytearray, offset: int, zone: ZoneMapping, voice: VoiceLayer,
                 sample_index: int, sample_has_loop: bool, bank_format: BankFormat) -> None:
    key_root = max(LOWEST_KEY, min(HIGHEST_KEY,
                   zone.root_key if zone.root_key is not None else zone.lo_key))
    data[offset + ZONE_ORIGINAL_KEY] = key_root - KEY_OFFSET
    _put_u16(data, offset + ZONE_SAMPLE_INDEX, sample_index)
    data[offset + ZONE_PARAMETER_A] = 0 if bank_format.is_esi else PARAMETER_A_EMULATOR_3X

    _write_envelope(data, offset + ZONE_VCA_ENVELOPE, voice.amp_env)

    tuning_units = max(-64, min(64, round(zone.fine_tune * 64.0 / 100.0)))
    _put_s8(data, offset + ZONE_NOTE_TUNING, tuning_units)

    gain_db = zone.volume
    level = 0 if gain_db <= -96.0 else int(round(
        max(0.0, min(FULL_LEVEL, FULL_LEVEL * (10.0 ** (gain_db / 20.0))))))
    data[offset + ZONE_VCA_LEVEL] = max(0, min(FULL_LEVEL, level))
    data[offset + ZONE_VCA_PAN] = _panning_value(zone.pan)
    # No velocity->amplitude field exists in mpc2emu's model (no source
    # parser populates one) — left at 0, matching what ConvertWithMoss's own
    # writer would also emit for a source with no such data.

    # Filter. EIII/EIIIX have a single fixed low-pass filter; only the ESI
    # samplers select a type, and VoiceLayer has no EIII-specific type enum
    # to select one from, so the type nibble is always left at 0 (= the
    # EIIIX/EIII low-pass, and ESI's own most-used type).
    if voice.filter_type:
        hz = _e4b_cutoff_position_to_hz(voice.filter_cutoff)
        data[offset + ZONE_VCF_CUTOFF] = _cutoff_value(hz)
        resonance = max(0, min(127, int(round(voice.filter_resonance * 127))))
        data[offset + ZONE_VCF_Q] = resonance | (Q_REALTIME_ENABLE if bank_format.is_esi else 0)
        data[offset + ZONE_VCF_TYPE_LFO_SHAPE] = 0
        # Key-tracking and velocity-to-cutoff are left neutral: mpc2emu's
        # filter_keytrack/velocity_to_filter are EOS mod-cord amounts
        # calibrated against E4XT hardware (models.common
        # key_track_to_filter_amount / velocity_filter_depth_to_amount) —
        # that calibration does not apply to EIII's differently-scaled,
        # differently-shaped DSP, and no EIII hardware calibration exists
        # yet (see docs/EIII_FORMAT.md). Writing a made-up conversion would
        # risk producing filters that audibly mistrack on real hardware.
        data[offset + ZONE_VCF_TRACKING] = _ZONE_TRACKING_NEUTRAL

        env_amount = max(0, min(127, int(round(voice.filter_env_amount * 127))))
        data[offset + ZONE_VCF_ENVELOPE_AMOUNT] = env_amount
        if env_amount:
            _write_envelope(data, offset + ZONE_VCF_ENVELOPE, voice.filter_env)
        else:
            _write_envelope(data, offset + ZONE_VCF_ENVELOPE, None)
    else:
        # Bypass state: fully open, no resonance, no key tracking.
        data[offset + ZONE_VCF_CUTOFF] = DEFAULT_CUTOFF
        data[offset + ZONE_VCF_Q] = Q_REALTIME_ENABLE if bank_format.is_esi else 0
        data[offset + ZONE_VCF_TRACKING] = _ZONE_TRACKING_NEUTRAL
        _write_envelope(data, offset + ZONE_VCF_ENVELOPE, None)

    # Auxiliary envelope: mpc2emu has no pitch-envelope modulator, so this
    # always stays off (destination 0) with the neutral envelope shape.
    _write_envelope(data, offset + ZONE_AUX_ENVELOPE, None)

    data[offset + ZONE_REALTIME_ENABLE] = REALTIME_ENABLE_ALL
    flags = 0x01   # always set by the samplers, meaning unknown
    if voice.non_transpose:
        flags |= ZONE_FLAG_NON_TRANSPOSE
    if not sample_has_loop:
        # mpc2emu has no per-zone loop override (a zone's loop is entirely
        # the referenced sample's) — this flag simply mirrors whether the
        # sample itself loops, matching what a zone whose sample has no
        # loop would carry regardless of any override.
        flags |= ZONE_FLAG_DISABLE_LOOP
    data[offset + ZONE_FLAGS] = flags


# mpc2emu's model carries no per-preset pitch-bend-range override; every
# written preset gets the sampler's own factory default of 2 semitones
# (matches ConvertWithMoss's fallback for sources with no such data).
_DEFAULT_PITCH_BEND_RANGE = 2


def _create_preset(name: str, voice: VoiceLayer,
                    sample_info_by_name: Dict[str, Tuple[int, bool]],
                    bank_format: BankFormat, notifier=print) -> Optional[bytes]:
    """`sample_info_by_name` maps a sample name to (1-based index, has_loop)."""
    zones = sorted(voice.zones, key=lambda z: z.lo_key)

    key_mappings = [UNUSED] * NUM_KEYS
    mapped_zones: List[ZoneMapping] = []
    sample_indices: List[int] = []
    sample_has_loops: List[bool] = []

    for zone in zones:
        key_lo = max(LOWEST_KEY, zone.lo_key)
        key_hi = min(HIGHEST_KEY, zone.hi_key)
        if key_lo > key_hi:
            notifier(f"  [WARN] zone '{zone.sample_name}' outside the 88-key "
                     f"EIII keyboard range, skipped")
            continue
        sample_info = sample_info_by_name.get(zone.sample_name)
        if not sample_info:
            notifier(f"  [WARN] zone references unknown sample "
                     f"'{zone.sample_name}', skipped")
            continue

        note_zone_index = len(mapped_zones)
        for key in range(key_lo, key_hi + 1):
            key_mappings[key - KEY_OFFSET] = note_zone_index
        mapped_zones.append(zone)
        sample_indices.append(sample_info[0])
        sample_has_loops.append(sample_info[1])

    # Drop zones which lost every key to a later zone (later wins ties, like
    # the sampler's own front panel) and renumber the survivors densely.
    survivors: List[int] = []
    renumbered = [UNUSED] * len(mapped_zones)
    for key in range(NUM_KEYS):
        note_zone_index = key_mappings[key]
        if note_zone_index == UNUSED:
            continue
        if renumbered[note_zone_index] == UNUSED:
            renumbered[note_zone_index] = len(survivors)
            survivors.append(note_zone_index)
        key_mappings[key] = renumbered[note_zone_index]

    if not survivors:
        return None

    num_note_zones = len(survivors)
    data = bytearray(PRESET_SIZE + num_note_zones * NOTE_ZONE_SIZE
                      + num_note_zones * ZONE_SIZE)

    _encode_name(data, 0, name)
    data[NAME_LENGTH:NAME_LENGTH + len(DEFAULT_REALTIME_CONTROLS)] = DEFAULT_REALTIME_CONTROLS
    _put_s8(data, PRESET_PITCH_BEND_RANGE, _DEFAULT_PITCH_BEND_RANGE)
    data[PRESET_NUM_NOTE_ZONES] = num_note_zones
    for key in range(NUM_KEYS):
        data[PRESET_KEY_MAPPINGS + key] = key_mappings[key]

    velocity_low, velocity_high = 127, 1
    for idx in survivors:
        z = mapped_zones[idx]
        velocity_low = min(velocity_low, max(1, min(127, z.lo_vel)))
        velocity_high = max(velocity_high, max(1, min(127, z.hi_vel)))
    if velocity_low > 1 or velocity_high < 127:
        data[PRESET_VELOCITY_PRIMARY_LOW] = velocity_low
        data[PRESET_VELOCITY_PRIMARY_HIGH] = velocity_high

    note_zone_offset = PRESET_SIZE
    zone_offset = note_zone_offset + num_note_zones * NOTE_ZONE_SIZE
    for i, idx in enumerate(survivors):
        nz = note_zone_offset + i * NOTE_ZONE_SIZE
        data[nz + NOTE_ZONE_PRIMARY] = i
        data[nz + NOTE_ZONE_SECONDARY] = UNUSED
        _write_zone(data, zone_offset + i * ZONE_SIZE, mapped_zones[idx], voice,
                    sample_indices[idx], sample_has_loops[idx], bank_format)

    return bytes(data)


# ---------------------------------------------------------------------------
# Sample serialization
# ---------------------------------------------------------------------------

def _prepare_sample_pcm(sample: SampleData) -> Tuple[bytearray, bool, int, int, bool]:
    """Bake ping-pong loops, silence the required edge frames, and clamp the
    loop to the sampler's minimum-distance/length rules.

    Returns (pcm, has_loop, loop_start, loop_end, loop_in_release).
    """
    baked = bake_alternating_loop(sample)
    pcm = bytearray(baked.data)
    num_frames = len(pcm) // 2

    n = min(NUM_SILENT_FRAMES * 2, len(pcm))
    for i in range(n):
        pcm[i] = 0
        pcm[len(pcm) - 1 - i] = 0

    has_loop = (baked.loop_type in (LoopType.FORWARD, LoopType.FORWARD_REL)
                and baked.loop_end > baked.loop_start and num_frames > 0)
    loop_start = loop_end = 0
    loop_in_release = False
    if has_loop:
        hi = max(6, num_frames - 7)
        loop_start = max(6, min(hi, baked.loop_start))
        loop_end = max(6, min(hi, baked.loop_end))
        if loop_end - loop_start < MINIMUM_LOOP_LENGTH:
            loop_start = max(0, loop_end - MINIMUM_LOOP_LENGTH)
        has_loop = loop_end > loop_start
        # FORWARD_REL ("loop until release") is the one loop mode where the
        # sampler is explicitly told to stop looping at key-up; plain
        # FORWARD carries no such request, so it gets the sampler's default
        # of continuing through the release phase (matching what E4B/EOS
        # already does for the same LoopType — see writers/e4b_writer.py).
        loop_in_release = baked.loop_type != LoopType.FORWARD_REL

    return pcm, has_loop, loop_start, loop_end, loop_in_release


def _write_sample(data: bytearray, offset: int, name: str, pcm: bytes, sample_rate: int,
                   has_loop: bool, loop_start: int, loop_end: int, loop_in_release: bool,
                   memory_offset: int) -> int:
    num_frames = len(pcm) // 2
    channel_size = num_frames * 2
    mono_size = SAMPLE_HEADER_SIZE + channel_size

    _encode_name(data, offset, name)
    _put_u32(data, offset + SAMPLE_START_LEFT, SAMPLE_HEADER_SIZE)
    _put_u32(data, offset + SAMPLE_START_RIGHT, 0)
    _put_u32(data, offset + SAMPLE_END_LEFT, mono_size - 2)
    _put_u32(data, offset + SAMPLE_END_RIGHT, 0)

    loop_start_bytes = SAMPLE_HEADER_SIZE + (loop_start * 2 if has_loop else 0)
    loop_end_bytes = (SAMPLE_HEADER_SIZE + loop_end * 2) if has_loop else (mono_size - 2)
    _put_u32(data, offset + SAMPLE_LOOP_START_LEFT, loop_start_bytes)
    _put_u32(data, offset + SAMPLE_LOOP_START_RIGHT, 0)
    _put_u32(data, offset + SAMPLE_LOOP_END_LEFT, loop_end_bytes)
    _put_u32(data, offset + SAMPLE_LOOP_END_RIGHT, 0)

    _put_u32(data, offset + SAMPLE_RATE, sample_rate)
    _put_u16(data, offset + SAMPLE_PLAYBACK_RATE, _encode_playback_rate(sample_rate))

    options = OPTION_CHANNEL_LEFT
    if has_loop:
        options |= OPTION_LOOP
        if loop_in_release:
            options |= OPTION_LOOP_IN_RELEASE
    _put_u16(data, offset + SAMPLE_OPTIONS, options)
    _put_u32(data, offset + SAMPLE_DATA_OFFSET_LEFT, memory_offset + SAMPLE_HEADER_SIZE)
    _put_u32(data, offset + SAMPLE_DATA_OFFSET_RIGHT, 0)

    data[offset + SAMPLE_HEADER_SIZE:offset + SAMPLE_HEADER_SIZE + channel_size] = pcm
    return SAMPLE_HEADER_SIZE + channel_size


def _unique_disk_name(name: str, used: set) -> str:
    base = (name or '').strip()[:NAME_LENGTH]
    candidate = base
    counter = 1
    while candidate in used:
        counter += 1
        suffix = str(counter)
        candidate = base[:max(0, NAME_LENGTH - len(suffix))] + suffix
    used.add(candidate)
    return candidate


def _preset_name(preset_name: str, layer_number: int) -> str:
    if layer_number == 0:
        return preset_name
    suffix = f" L{layer_number:02d}"
    max_len = NAME_LENGTH - len(suffix)
    base = preset_name[:max_len] if len(preset_name) > max_len else preset_name
    return base + suffix


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def write_eiii(bank: Bank, output_path: str, variant: str = 'e3x') -> None:
    """Serialize a Bank to an EIII bank file.

    `variant`: 'e3x' (Emulator IIIX, default — also loaded by the E4XT's
    backward-compatibility loader and by the ESI samplers) or 'esi'
    (ESI-32/2000/4000's own identifier).
    """
    bank_format = BANK_FORMATS.get(variant)
    if bank_format is None:
        raise ValueError(f"Unknown EIII variant '{variant}', expected one of "
                          f"{sorted(BANK_FORMATS)}")

    print(f"Writing EIII ({bank_format.device_name}): {output_path}")
    print(f"  {len(bank.presets)} preset(s), {len(bank.samples)} sample(s)")

    # The EIII carries stereo via OPTION_CHANNEL_RIGHT plus the RIGHT half of
    # every position pair (constants already defined above); mpc2emu writes
    # OPTION_CHANNEL_LEFT and zeroes the RIGHT fields, so downmix EXPLICITLY
    # here rather than letting interleaved PCM be measured as mono. Tracked
    # in TODO.md.
    n_stereo = sum(1 for s in bank.samples if getattr(s, 'channels', 1) == 2)
    if n_stereo:
        for s in bank.samples:
            ensure_mono(s)
        print(f"  Downmixed {n_stereo} stereo sample(s) to mono "
              f"(EIII stereo output not implemented)")

    # ── samples: prepare PCM once per bank-level SampleData ────────────────
    used_names: set = set()
    prepared = []   # (disk_name, pcm, sample_rate, has_loop, loop_start, loop_end, loop_in_release)
    sample_info_by_name: Dict[str, Tuple[int, bool]] = {}
    for i, s in enumerate(bank.samples):
        if len(prepared) >= bank_format.max_samples:
            print(f"  [WARN] bank exceeds {bank_format.max_samples}-sample "
                  f"{bank_format.device_name} limit, '{s.name}' and later dropped")
            break
        pcm, has_loop, loop_start, loop_end, loop_in_release = _prepare_sample_pcm(s)
        disk_name = _unique_disk_name(s.name, used_names)
        prepared.append((disk_name, bytes(pcm), s.sample_rate, has_loop, loop_start,
                          loop_end, loop_in_release))
        sample_info_by_name[s.name] = (len(prepared), has_loop)   # 1-based index

    # ── presets: one EIII preset per VoiceLayer, chained per mpc2emu Preset ─
    # `groups` records the [first, last) preset_bodies index range each
    # original mpc2emu Preset actually produced — NOT assumed from
    # len(preset.voices), since a voice can be dropped by _create_preset
    # (e.g. every zone outside the 88-key range or referencing a missing
    # sample) and that must not desync the link-chaining pass below.
    preset_bodies: List[bytes] = []
    groups: List[Tuple[int, int]] = []
    hit_limit = False
    for preset in bank.presets:
        first = len(preset_bodies)
        multi = len(preset.voices) > 1
        for i, voice in enumerate(preset.voices):
            if len(preset_bodies) >= bank_format.max_presets:
                print(f"  [WARN] bank exceeds {bank_format.max_presets}-preset "
                      f"{bank_format.device_name} limit, '{preset.name}' voice "
                      f"{i + 1} and later dropped")
                hit_limit = True
                break
            name = _preset_name(preset.name, (i + 1) if multi else 0)
            body = _create_preset(name, voice, sample_info_by_name, bank_format)
            if body is not None:
                preset_bodies.append(body)
        n_zones = sum(len(v.zones) for v in preset.voices)
        print(f"  Preset '{preset.name}': {len(preset.voices)} voice(s) "
              f"-> {len(preset_bodies) - first} EIII preset(s), {n_zones} zone(s)")
        groups.append((first, len(preset_bodies)))
        if hit_limit:
            break

    if not preset_bodies:
        raise ValueError("EIII bank has no usable presets/zones — nothing to write")

    # Chain each group's linked presets so its voices play together
    # (1-based `link` = index of the next preset).
    links = [0] * len(preset_bodies)
    for first, last in groups:
        for i in range(first, last - 1):
            links[i] = i + 2

    # ── assemble bank ───────────────────────────────────────────────────────
    preset_area_size = sum(len(b) for b in preset_bodies)
    sample_area_size = sum(SAMPLE_HEADER_SIZE + len(p[1]) for p in prepared)
    size = EMPTY_BANK_SIZE + preset_area_size + 1 + sample_area_size
    if size > MAX_BANK_SIZE:
        raise ValueError(f"EIII bank too large: {size / (1024 * 1024):.1f} MB "
                          f"exceeds the {MAX_BANK_SIZE // (1024 * 1024)} MB sample-memory limit")

    data = bytearray(size)
    data[0:EMPTY_BANK_SIZE] = _create_empty_bank(bank_format, bank.name)

    preset_table = bank_format.preset_table_offset
    preset_area_offset = bank_format.preset_area_offset
    offset = preset_area_offset
    for i, body in enumerate(preset_bodies):
        _put_u32(data, preset_table + i * 4, offset - preset_area_offset)
        data[offset:offset + len(body)] = body
        if links[i]:
            _put_u16(data, offset + PRESET_LINK, links[i])
        offset += len(body)
    for i in range(len(preset_bodies), bank_format.max_presets + 1):
        _put_u32(data, preset_table + i * 4, preset_area_size)

    data[offset] = bank_format.sample_area_marker
    offset += 1

    sample_table = bank_format.sample_table_offset
    sample_area_offset = offset
    for i, (disk_name, pcm, sample_rate, has_loop, loop_start, loop_end,
            loop_in_release) in enumerate(prepared):
        _put_u32(data, sample_table + i * 4,
                  offset - sample_area_offset + SAMPLE_ADDRESS_OFFSET)
        written = _write_sample(data, offset, disk_name, pcm, sample_rate, has_loop,
                                 loop_start, loop_end, loop_in_release,
                                 offset - sample_area_offset)
        print(f"  Sample [{i + 1:03d}] '{disk_name}': {len(pcm)} bytes PCM"
              + (f", loop {loop_start}-{loop_end}" if has_loop else ""))
        offset += written
    _put_u32(data, sample_table + bank_format.max_samples * 4,
              offset - sample_area_offset + SAMPLE_ADDRESS_OFFSET)

    _put_u32(data, BANK_OBJECTS, len(preset_bodies) + len(prepared))
    _put_u32(data, BANK_NEXT_PRESET, _get_u32(data, BANK_NEXT_PRESET) + preset_area_size)
    _put_u32(data, BANK_NEXT_SAMPLE, offset - sample_area_offset)
    _put_u32(data, BANK_SELECTED_PRESET, 0)

    preset_blocks = (sample_area_offset - 1 + BLOCK_SIZE - 1) // BLOCK_SIZE
    total_blocks = (size + BLOCK_SIZE - 1) // BLOCK_SIZE
    _put_u32(data, BANK_PRESET_BLOCKS, preset_blocks)
    _put_u32(data, BANK_SAMPLE_BLOCKS, total_blocks - preset_blocks)
    _put_u32(data, BANK_TOTAL_BLOCKS, total_blocks)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(data)
    print(f"  Done: {output_path} ({len(data) / 1024 / 1024:.2f} MB)")
