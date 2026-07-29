# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
#
# This file is part of mpc2emu.
# Original work.
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
Common data models for MPC -> EMU E4B conversion.
Internal representation decoupled from both source and target formats.
"""
import array
import math
import sys
import warnings
from dataclasses import dataclass, field
from typing import List, Optional
from enum import IntEnum

# Stereo->mono downmix accelerator. See docs/RESOLUTION_NOTES.md §PARSERPERF
# for why `audioop` is used despite PEP 594 (it is ~100x a per-frame struct
# loop, and this ran at 99.5% of three parsers' time) and why the pure-`array`
# fallback below keeps Python 3.13+ working with byte-identical output.
try:
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        import audioop as _audioop
except ImportError:                                  # Python 3.13+
    _audioop = None


def stereo_to_mono(raw: bytes) -> tuple:
    """Downmix interleaved 16-bit LE stereo to mono, averaging with a floor
    (`(l + r) >> 1`). Returns `(pcm, 1)` so callers can assign both the data
    and the new channel count.

    Canonical home: parsers read it (via `xpm_parser`) and writers that cannot
    emit stereo call it at their entry point, so there is exactly one downmix
    in the project (CR-13/CR-17: duplicated codecs have drifted here before).
    """
    raw = raw[:len(raw) // 4 * 4]
    if _audioop is not None and sys.byteorder == 'little':
        return _audioop.tomono(raw, 2, 0.5, 0.5), 1
    a = array.array('h')
    a.frombytes(raw)
    if sys.byteorder == 'big':          # stored little-endian, read natively
        a.byteswap()
    mono = array.array('h', [(l + r) >> 1 for l, r in zip(a[0::2], a[1::2])])
    if sys.byteorder == 'big':          # emit little-endian
        mono.byteswap()
    return mono.tobytes(), 1


def pick_channel(raw: bytes, side: str) -> tuple:
    """Take ONE side of interleaved 16-bit LE stereo. Returns `(pcm, 1)`.

    An alternative to summing that matters more than it looks: measured over
    95 real stereo E4B samples the two sides are largely DEcorrelated (median
    Pearson r = 0.107, many negative), because they are genuine room
    recordings rather than a detuned duplicate of one source. Summing
    decorrelated -- let alone anti-phase -- channels cancels signal; on the
    worst samples measured the difference signal carried 1.9x the energy of
    the sum. Picking a side keeps that side's full level and room character.
    """
    a = array.array('h')
    a.frombytes(raw[:len(raw) // 4 * 4])
    if sys.byteorder == 'big':
        a.byteswap()
    one = a[0::2] if side == 'left' else a[1::2]
    if sys.byteorder == 'big':
        one.byteswap()
    return one.tobytes(), 1


def channel_correlation(raw: bytes, max_frames: int = 20000) -> float:
    """Pearson correlation between the two sides of interleaved 16-bit stereo,
    over at most `max_frames` frames. 1.0 = identical, 0 = unrelated,
    negative = anti-phase.

    Used to warn when an averaging downmix is likely to be destructive.
    Measured over 247 real stereo E-mu samples the median is 0.076 and NONE
    exceeded 0.9, i.e. summing is the lossy option for that material far more
    often than not -- which is why this is surfaced to the user instead of
    being guessed at automatically.
    """
    n = min(len(raw) // 4, max_frames)
    if n < 2:
        return 1.0
    a = array.array('h')
    a.frombytes(raw[:n * 4])
    if sys.byteorder == 'big':
        a.byteswap()
    L = a[0::2]
    R = a[1::2]
    mL = sum(L) / n
    mR = sum(R) / n
    vL = sum((x - mL) ** 2 for x in L)
    vR = sum((x - mR) ** 2 for x in R)
    if vL <= 0 or vR <= 0:
        return 1.0
    cov = sum((L[i] - mL) * (R[i] - mR) for i in range(n))
    return cov / math.sqrt(vL * vR)


def to_mono(sample, method: str = 'mix') -> bool:
    """Reduce `sample` to mono in place. `method` is 'mix' (average both
    sides), 'left' or 'right'. Returns True if anything changed.

    Used both as a deliberate size reduction (halves a sample; see the
    vintage-fit options in convert.py) and defensively by writers whose
    target format mpc2emu cannot yet emit stereo for.
    """
    if getattr(sample, 'channels', 1) != 2:
        return False
    if method in ('left', 'right'):
        sample.data, sample.channels = pick_channel(sample.data, method)
    else:
        sample.data, sample.channels = stereo_to_mono(sample.data)
    return True


def ensure_mono(sample) -> None:
    """Downmix `sample` in place if it is stereo, by averaging. For writers
    whose target format mpc2emu does not yet emit stereo for -- explicit and
    logged at the call site, rather than silently assuming every sample is
    mono."""
    to_mono(sample, 'mix')


class LoopType(IntEnum):
    NO_LOOP      = 0
    FORWARD      = 1
    ALTERNATING  = 2  # Ping-pong
    FORWARD_REL  = 3  # Loop until release


# Filter-envelope depth normalisation, shared by the parsers.  Several source
# formats express how much the envelope moves the cutoff in cents (SFZ
# fileg_depth, SF2 modEnvToFilterFc, GIG/DLS EG2-to-cutoff).  EOS stores
# Shared 0x38 (Filter-Freq) destination sensitivity, hardware-measured on the
# E4XT 2026-06-12 (MOD_DEPTH_CAL; four independent cords agree — see
# RESOLUTION_NOTES §19): a 100% cord amount moves the cutoff 3.65 octaves per full
# source unit.  FilterEnv (0→1 unit) and LFO~ (±1 unit, one-sided) therefore both
# reach full amount at ±3.65 oct = ±4383 cents, so this ONE constant scales both
# the filter-envelope depth AND the LFO→filter depth.  (Was 9600 = 8 oct, a guess
# ~2.2× too high, which under-delivered every cents-based filter-mod depth.)
FILTER_ENV_FULL_CENTS = 4383.0       # = 3.65 octaves * 1200


def cents_to_filter_env_amount(cents: float) -> float:
    """Map a Filter-Freq mod depth in cents to an EOS cord amount (-1..+1).
    Shared by the filter ENVELOPE and the LFO→Filter cords (same 0x38 dest)."""
    return max(-1.0, min(1.0, cents / FILTER_ENV_FULL_CENTS))


# Velocity→Filter: the velocity source spans 0→~2.08 units over MIDI velocity
# 0→127, so a 100% cord moves the cutoff ~7.6 octaves (= 9120 cents) across the
# full velocity range (measured r=0.9999; consistent with Key 0.713 oct/oct ×
# 10.6 oct keyboard).  Note: the writer routes this through the **Vel+** source.
VEL_FILTER_FULL_CENTS = 9120.0       # = 7.6 octaves * 1200


def velocity_filter_depth_to_amount(cents: float) -> float:
    """Map a velocity→filter depth in cents (cutoff change at full velocity) to
    an EOS cord amount (-1..+1)."""
    return max(-1.0, min(1.0, cents / VEL_FILTER_FULL_CENTS))


# Key→Filter: a 100% cord tracks the cutoff at 0.713 octave per octave of key
# (measured r=0.9994 — NOT the assumed 1:1), so a desired ratio needs
# amount = ratio / 0.713 (a true 1:1 request saturates at the 0.713 hardware max).
KEY_FILTER_OCT_PER_OCT = 0.713


def key_track_to_filter_amount(oct_per_oct: float) -> float:
    """Map a desired Key→Filter tracking ratio (octaves of cutoff per octave of
    key) to an EOS cord amount (-1..+1)."""
    return max(-1.0, min(1.0, oct_per_oct / KEY_FILTER_OCT_PER_OCT))


# E4B VCF cutoff byte (vpar[60]) is exponential: ~57 Hz at 0, 20 kHz at full.
# Shared by every parser that maps a source cutoff frequency onto the E4B scale
# (CR-12 — previously duplicated in exs24 and re-implemented wrong in sfz).
E4B_CUTOFF_MIN_HZ = 57.0
E4B_CUTOFF_MAX_HZ = 20000.0


def hz_to_e4b_cutoff(hz: float) -> float:
    """Map a cutoff frequency in Hz to the E4B exponential cutoff position
    (0.0-1.0, where the writer does round(pos*255) → vpar[60])."""
    hz = max(E4B_CUTOFF_MIN_HZ, min(E4B_CUTOFF_MAX_HZ, hz))
    return math.log(hz / E4B_CUTOFF_MIN_HZ) / math.log(E4B_CUTOFF_MAX_HZ / E4B_CUTOFF_MIN_HZ)


# ── EOS envelope rate <-> time and level <-> byte ──────────────────────────
# Rate↔time hardware-calibrated 2026-06-08 from 6 Decay-1 measurements on the
# E4XT (AMP_DECAY_CAL.E4B): rate 8→0.034 s, 16→0.098, 24→0.169, 32→0.198,
# 48→0.454, 64→1.225.  Log-linear fit (R²=0.96): time_s = 0.0310·e^(0.0581·rate);
# rate 0 = instant, higher = slower.  Single home for the E4B writer + parser
# (CR-13 — were duplicated "kept in sync by comment").
ENV_RATE_A = 0.0310
ENV_RATE_K = 0.0581


def env_seconds_to_rate(seconds: float) -> int:
    """Envelope time (seconds) → EOS rate byte (0 = instant, higher = slower)."""
    if seconds <= 0.0:
        return 0
    return min(127, max(0,
        round((math.log(seconds) - math.log(ENV_RATE_A)) / ENV_RATE_K)))


def env_rate_to_seconds(rate: int) -> float:
    """EOS rate byte → envelope time in seconds (inverse of env_seconds_to_rate)."""
    return ENV_RATE_A * math.exp(ENV_RATE_K * max(0, min(127, rate)))


def env_level_to_byte(pct: float) -> int:
    """Envelope level −100..+100 % → signed byte stored unsigned (×127/100)."""
    return round(max(-100.0, min(100.0, pct)) * 127 / 100) & 0xFF


def env_byte_to_level(b: int) -> float:
    """Inverse of env_level_to_byte: stored byte → −1.0..+1.0 fraction."""
    return (b if b < 128 else b - 256) / 127.0


# ── Amp-envelope SUSTAIN: linear fraction -> byte, hardware-compensated ────
# Hardware-measured 2026-07-28 (docs/RESOLUTION_NOTES.md §E4BLEVEL): the
# amp-envelope Decay1/Decay2 "Level%" target is NOT linear amplitude on the
# E4XT -- it's an exponential/dB-law response, ~1 dB of attenuation per
# percentage point below 100%. Writing `env_level_to_byte(frac*100)`
# directly (as if pct% == frac of full amplitude) plays far quieter than
# intended: a "linear 50%" target measured at -46.5 dB (0.47% actual
# amplitude) on real hardware, not -6 dB/50%.
#
# Measured via a 9-point sweep bank (tests/re_banks/gen_amp_level_cal.py),
# narrowband-analyzed against the test tone's own frequency to reject
# recording noise floor: measured_dB = ENV_LEVEL_DB_SLOPE*pct +
# ENV_LEVEL_DB_INTERCEPT, R²=0.996 across the full 0-100% range.
#
# Writer-only fix (CR-2026-07-28): only `env_sustain_to_byte` compensates
# for this curve, used for the amp-envelope sustain target specifically.
# `env_level_to_byte`/`env_byte_to_level` above are UNCHANGED and still
# used as-is for the Attack/Release endpoints (100%/0%, unaffected by the
# curve at either end) and by the parser (reading third-party files'
# existing sustain bytes is a separate, not-yet-decided scope -- see TODO).
ENV_LEVEL_DB_SLOPE = 1.010
ENV_LEVEL_DB_INTERCEPT = -98.74


def env_sustain_to_byte(frac: float) -> int:
    """Intended LINEAR amplitude fraction (0.0-1.0) → amp-envelope sustain
    byte, pre-compensated so the E4XT actually plays back at `frac` of full
    amplitude (see module-level comment above for the calibration).

    Both endpoints are special-cased to the exact byte `env_level_to_byte`
    already gives for 0%/100% (0 and 127) rather than running them through
    the fitted curve -- the least-squares fit doesn't pass exactly through
    (100%, 0 dB) (off by ~0.3 dB there), and frac=1.0 should mean "same as
    the true full-scale endpoint" the Attack/Release stages already use,
    not an artifact of curve-fit noise at the edge."""
    frac = max(0.0, min(1.0, frac))
    if frac <= 0.0:
        return 0
    if frac >= 1.0:
        return env_level_to_byte(100.0)
    db = 20 * math.log10(frac)
    pct = (db - ENV_LEVEL_DB_INTERCEPT) / ENV_LEVEL_DB_SLOPE
    pct = max(0.0, min(100.0, pct))
    return env_level_to_byte(pct)


# ── Signed mod-cord amount codec (±1.0 <-> signed byte stored unsigned) ─────
# CR-13/CR-18: was inlined ~5× across the E4B writer/parser.
def cord_amount_to_byte(amount: float) -> int:
    """Mod-cord amount −1.0..+1.0 → signed byte stored unsigned (±127)."""
    return round(max(-1.0, min(1.0, amount)) * 127) & 0xFF


def cord_byte_to_amount(b: int) -> float:
    """Inverse of cord_amount_to_byte: stored byte → −1.0..+1.0."""
    return (b - 256 if b >= 128 else b) / 127.0


# ── LFO rate byte (0-127) <-> Hz ───────────────────────────────────────────
# Calibrated 2026-06-10 from the E4XT rate menu readout (byte 0=0.08 Hz,
# 64=4.12 Hz, 127=18.01 Hz).  The curve is NOT exponential; a log-quadratic
# ln(Hz)=A·b²+B·b+C passes through all three anchors and inverts cleanly.
# 3-point fit (exact at min/default/max), refineable with intermediate readouts.
# Shared by the E4B writer/parser and every source-format parser.
_LFO_RATE_A = -0.000300578
_LFO_RATE_B =  0.0808242
_LFO_RATE_C = -2.52573
LFO_RATE_HZ_MIN = 0.08
LFO_RATE_HZ_MAX = 18.01

# MPC LFO Rate knob (0..1) -> Hz.  MEASURED on hardware 2026-06-13: six free-run
# patches read 0.02/0.13/0.50/2.00/7.96/21.93 Hz at knob 0.0/0.2/0.35/0.5/0.65/
# 0.76.  ln(Hz) is linear in knob -> Hz = A·e^(B·knob) (slope 9.195, intercept
# -3.901).  See docs/aural_notes.md.  Distinct from the E4XT byte curve above:
# the old code wrongly reused that (knob 0.5 -> 4.12 Hz instead of the MPC's
# 2.00).  The writer's lfo_rate_hz_to_byte clamps the result to the E4XT's
# 0.08-18.01 Hz range, so MPC rates above ~18 Hz (knob ~0.74+) land at the E4XT
# max — a hardware ceiling, not reproducible.
_MPC_LFO_RATE_A = 0.0202
_MPC_LFO_RATE_B = 9.195
# Full-scale ±cents for an LFO→pitch cord at amount=100% (±1.0).  MEASURED on the
# E4XT 2026-06-12 (MOD_DEPTH_CAL PitchDepth 25/50/75/100 % square-LFO recording):
# the response is linear through the origin, one-sided cents = 400/801/1190/1583
# at 25/50/75/100 %, giving a full-scale of 1593 c (σ=8) — i.e. ±16 semitones,
# NOT the ±1 octave previously assumed.  See RESOLUTION_NOTES §19.
LFO_PITCH_FULL_CENTS = 1593.0
# Full-scale dB swing for an LFO→volume cord at amount=100% (±1.0). UNCONFIRMED
# on hardware (no MOD_DEPTH_CAL-style measurement exists for this cord, unlike
# LFO_PITCH_FULL_CENTS above) — added 2026-07-28 cross-referencing
# ConvertWithMoss PR #240 (tremolo support for SFZ/SF2/DLS/DecentSampler,
# sources express depth directly in dB). Chosen as a plausible "full tremolo"
# swing pending real calibration; flag alongside any future MOD_DEPTH_CAL-style
# hardware test.
LFO_VOLUME_FULL_DB = 24.0


def lfo_rate_byte_to_hz(byte: int) -> float:
    """E4B LFO rate byte 0-127 -> frequency in Hz (forward log-quadratic fit)."""
    return math.exp(_LFO_RATE_A * byte * byte + _LFO_RATE_B * byte + _LFO_RATE_C)


def lfo_rate_hz_to_byte(hz: float) -> int:
    """LFO frequency in Hz -> E4B rate byte 0-127 (inverse of the fit)."""
    hz = max(LFO_RATE_HZ_MIN, min(LFO_RATE_HZ_MAX, hz))
    c = _LFO_RATE_C - math.log(hz)
    disc = _LFO_RATE_B * _LFO_RATE_B - 4.0 * _LFO_RATE_A * c
    if disc < 0:
        return 64
    # vertex is at byte≈134 (>127); the in-range root is the one nearer 0.
    b = (-_LFO_RATE_B + math.sqrt(disc)) / (2.0 * _LFO_RATE_A)
    return max(0, min(127, round(b)))


def lfo_knob_to_hz(knob01: float) -> float:
    """Map the MPC LFO-rate knob (XPM <Rate>, 0..1) to Hz via the hardware-
    measured MPC rate law  Hz = 0.0202·e^(9.195·knob)  (≈0.02 Hz at knob 0,
    2.00 Hz at 0.5, 21.9 Hz at 0.76 — fitted 2026-06-13, see docs/aural_notes.md).
    The caller converts this to an E4XT rate byte via lfo_rate_hz_to_byte, which
    clamps to the 0.08-18.01 Hz hardware range."""
    knob = max(0.0, min(1.0, knob01))
    return _MPC_LFO_RATE_A * math.exp(_MPC_LFO_RATE_B * knob)


def lfo_pitch_depth_to_amount(cents: float) -> float:
    """Map an LFO→pitch depth in cents to an EOS mod-cord amount (-1..+1)."""
    return max(-1.0, min(1.0, cents / LFO_PITCH_FULL_CENTS))


def lfo_volume_depth_to_amount(db: float) -> float:
    """Map an LFO→volume (tremolo) depth in dB to an EOS mod-cord amount
    (0..1 — always positive: a tremolo swings symmetrically down from the
    zone's own volume, there's no "negative" direction). See
    LFO_VOLUME_FULL_DB for calibration status."""
    return max(0.0, min(1.0, abs(db) / LFO_VOLUME_FULL_DB))


# ── KRZ (K2000) scalar codecs ───────────────────────────────────────────────
# Shared by writers/krz_writer.py and parsers/krz_parser.py so the two stay
# exact inverses (CR-13/CR-18 pattern: single home, not "kept in sync by
# comment"). All HW-confirmed via krz_program_re.md; see docs/KRZ_FORMAT.md §4.

def krz_cutoff_byte_to_hz(b: int) -> float:
    """K2000 HOB0[1] signed-semitone cutoff byte -> Hz.
    Inverse of krz_writer._cutoff_byte: Hz = 440 * 2**((s-9)/12), s in -48..79."""
    s = b - 256 if b >= 128 else b
    return 440.0 * (2.0 ** ((s - 9) / 12.0))


def krz_reson_byte_to_01(b: int) -> float:
    """K2000 HOB1[1] resonance byte (dB*2, 0..48 = 0..24 dB) -> 0.0-1.0.
    Inverse of krz_writer._reson_byte."""
    return max(0.0, min(1.0, b / 48.0))


# K2000 envelope-time display grid (seconds per editor step); env time byte =
# steps(seconds) + 3. Shared with krz_writer._ENV_TIME_GRID.
KRZ_ENV_TIME_GRID = [(0, 2, 0.02), (2, 5, 0.04), (5, 10, 0.10),
                     (10, 15, 0.50), (15, 25, 1.0), (25, 60, 5.0)]

# KRZ-only release-time correction (krz_writer._KRZ_RELEASE_FACTOR): the shared
# MPC value->seconds curve under-reads the K2000's displayed release by this
# roughly-constant factor (2.63 s displayed / 1.39 s curve, AlphaPad #200).
KRZ_RELEASE_FACTOR = 1.9


def krz_env_byte_to_seconds(b: int) -> float:
    """K2000 ENV/ENC time byte -> seconds (inverse of krz_writer._env_time_byte,
    which walks KRZ_ENV_TIME_GRID accumulating steps = seconds/step_size)."""
    steps = max(0, b - 3)
    remaining = float(steps)
    for lo, hi, st in KRZ_ENV_TIME_GRID:
        seg_steps = (hi - lo) / st
        if remaining <= seg_steps:
            return lo + remaining * st
        remaining -= seg_steps
    return KRZ_ENV_TIME_GRID[-1][1]   # beyond the grid -> clamp at 60s


@dataclass
class SampleData:
    """Raw PCM sample with metadata."""
    name: str                   # Max 16 chars for E4B
    data: bytes                 # Raw PCM, 16-bit signed, little-endian
    sample_rate: int            # Hz, e.g. 44100
    channels: int               # 1=mono, 2=stereo
    bit_depth: int              # 16 or 24 (E4B only supports 16)
    loop_type: LoopType = LoopType.NO_LOOP
    loop_start: int = 0         # Sample frames
    loop_end: int = 0           # Sample frames
    root_note: int = 60         # MIDI note, 60 = C4
    fine_tune: int = 0          # Cents, -100..+100


@dataclass
class ZoneMapping:
    """
    One key/velocity zone within a voice layer.
    Maps a sample to a range of keys and velocities.
    """
    sample_name: str            # References SampleData.name
    lo_key: int = 0             # MIDI 0..127
    hi_key: int = 127
    lo_vel: int = 0             # MIDI 0..127
    hi_vel: int = 127
    root_key: int = 60          # Playback root (overrides sample default)
    fine_tune: int = 0          # Cents (-100..+100); vpar[36] stores 1/64-semitone units
    coarse_tune: int = 0        # Semitones (-72..+24); vpar[35] — repitches sample (not key remap)
    volume: float = 0.0         # dB, -96..+12
    pan: float = 0.0            # -1.0 (L) .. +1.0 (R)
    transpose: int = 0          # Semitones; vpar[34] — key remap (keyboard offset)


@dataclass
class Envelope:
    """A 4-stage ADSR envelope: attack/decay/release in seconds, sustain 0.0-1.0.
    Used for both the amplitude and filter envelopes of a VoiceLayer (CR-18)."""
    attack:  float = 0.001
    decay:   float = 0.3
    sustain: float = 0.8
    release: float = 0.5


def _amp_env() -> Envelope:    # amplitude-envelope default
    return Envelope(0.001, 0.3, 0.8, 0.5)


def _filter_env() -> Envelope:  # filter-envelope default (attack 0, sustain full)
    return Envelope(0.0, 0.3, 1.0, 0.0)


@dataclass
class VoiceLayer:
    """
    A single voice/layer within a preset.
    E4B calls this a 'Voice'; MPC calls it a 'Layer'.
    """
    zones: List[ZoneMapping] = field(default_factory=list)
    # Amplitude + filter envelopes (CR-18: one Envelope type, used twice).  The
    # flat env_*/filter_env_* names below are kept as properties for back-compat.
    amp_env: Envelope = field(default_factory=_amp_env)
    filter_env: Envelope = field(default_factory=_filter_env)
    # Filter
    filter_type: int = 0        # MPC XPM FilterType, the full 0-29 enum:
                                #   0 off | 1-5 Low 1/2/4/6/8-pole
                                #   6-10 High 1/2/4/6/8-pole | 11-14 Band 2/4/6/8
                                #   15-18 BandStop 2/4/6/8   | 19-22 BandBoost 2/4/6/8
                                #   23-25 Model1-3 | 26-28 Vocal1-3 | 29 MPC3000 LPF
                                # Authoritative map: _XPM_FILTER_TYPE in
                                # writers/e4b_writer.py (see docs/E4B_FORMAT.md
                                # §4.4).  ConvertWithMoss's MPCFilter uses the
                                # identical numbering for both MPC 2.x XML and
                                # MPC 3.x JSON, so the MPC 3 reader passes the
                                # integer straight through.
    filter_cutoff: float = 1.0  # 0.0-1.0 (1.0 = fully open / 20kHz)
    filter_resonance: float = 0.0  # 0.0-1.0
    filter_env_amount: float = 0.0  # 0.0-1.0 (envelope→cutoff depth, separate)
    # Tuning
    non_transpose: bool = False  # vpar[38]=1 in E4B: pitch does not follow key
    # Filter modulation (EOS mod cords into Filter-Freq; -1.0..+1.0 = ±100%)
    filter_keytrack: float = 0.0     # Key → Filter-Freq  (cord 06)
    velocity_to_filter: float = 0.0  # Velocity → Filter-Freq (cord 04)
    # LFO1 (EOS Primary Zone Table PZT[42:46]; hardware-RE'd 2026-06-10 from
    # B.011-LFO1 settings.E4B).  None on a field = leave the EOS hardware default
    # (rate 4.12 Hz, triangle, no delay/variation, key-sync) so voices from
    # formats that carry no LFO data stay byte-identical.  Rate is in Hz; the
    # byte↔Hz curve was calibrated 2026-06-10 from the E4XT menu readout
    # (byte 0=0.08 Hz, 64=4.12 Hz, 127=18.01 Hz) — see writers/e4b_writer.py.
    lfo1_rate: Optional[float] = None       # Hz (0.08-18.01) -> PZT[42] (default 4.12)
    lfo1_shape: Optional[str] = None        # triangle|sine|sawtooth|square|random|hemiquaver
    lfo1_delay: Optional[float] = None      # seconds 0-20 -> PZT[44] 0-127
    lfo1_variation: Optional[float] = None  # 0.0-1.0 (=0-100%) -> PZT[45]
    lfo1_sync: Optional[bool] = None        # False=key sync (0), True=free run (1)
    lfo1_sync_division: Optional[int] = None  # MPC <Sync> tempo-lock division idx
                                              # (0/None = free; see xpm_parser _MPC_SYNC_DIV)
    # LFO2 — identical layout 8 bytes on (PZT[50:55]); hardware-RE'd 2026-06-10.
    lfo2_rate: Optional[float] = None       # Hz -> PZT[50] (default 4.12)
    lfo2_shape: Optional[str] = None        # same shape names as LFO1
    lfo2_delay: Optional[float] = None      # seconds 0-20 -> PZT[52]
    lfo2_variation: Optional[float] = None  # 0.0-1.0 -> PZT[53]
    lfo2_sync: Optional[bool] = None        # False=key sync (0), True=free run (1) PZT[54]
    # LFO modulation routings (EOS mod cords; -1.0..+1.0 = ±100%).  Source ids
    # (hardware-RE'd 2026-06-10 from B.011 P012): LFO1~=0x60, LFO2~=0x68; dests
    # Pitch=0x30, Filter-Freq=0x38, Filter-Q=0x39.  LFO1→Pitch uses the default
    # cord 02 (mod[10]); the rest are written into free cord slots (8+).
    lfo1_to_pitch: float = 0.0       # LFO1 → Pitch   (cord 02, mod[10])
    lfo1_to_filter: float = 0.0      # LFO1 → Filter-Freq (0x60→0x38)
    lfo1_to_filter_q: float = 0.0    # LFO1 → Filter-Q    (0x60→0x39)
    lfo1_to_volume: float = 0.0      # LFO1 → Volume (tremolo); 0.0-1.0 depth
    lfo2_to_pitch: float = 0.0       # LFO2 → Pitch       (0x68→0x30)
    lfo2_to_filter: float = 0.0      # LFO2 → Filter-Freq (0x68→0x38)
    lfo2_to_filter_q: float = 0.0    # LFO2 → Filter-Q    (0x68→0x39)
    lfo2_to_volume: float = 0.0      # LFO2 → Volume (tremolo); 0.0-1.0 depth
    # Mod-wheel→LFO-depth gating (MPC <KeygroupWheelToLfo>, 0.0-1.0).  On the E4XT
    # this is a cascaded cord ModWheel(0x11) → CordN-Amount(0xA8+N), splitting each
    # LFO→dest cord into a static part D*(1-wheel) and a wheel-added part D*wheel
    # (RE'd 2026-06-13 from B.013-RE_SUITE CrdAmt).  0 = LFO always at full depth.
    wheel_to_lfo: float = 0.0
    # FX
    chorus_amount: float = 0.0   # 0.0-1.0 (E4B vpar[42], 100% -> 127); 0 = off

    # ── back-compat flat accessors → the two Envelope objects (CR-18) ─────────
    @property
    def env_attack(self): return self.amp_env.attack
    @env_attack.setter
    def env_attack(self, v): self.amp_env.attack = v

    @property
    def env_decay(self): return self.amp_env.decay
    @env_decay.setter
    def env_decay(self, v): self.amp_env.decay = v

    @property
    def env_sustain(self): return self.amp_env.sustain
    @env_sustain.setter
    def env_sustain(self, v): self.amp_env.sustain = v

    @property
    def env_release(self): return self.amp_env.release
    @env_release.setter
    def env_release(self, v): self.amp_env.release = v

    @property
    def filter_env_attack(self): return self.filter_env.attack
    @filter_env_attack.setter
    def filter_env_attack(self, v): self.filter_env.attack = v

    @property
    def filter_env_decay(self): return self.filter_env.decay
    @filter_env_decay.setter
    def filter_env_decay(self, v): self.filter_env.decay = v

    @property
    def filter_env_sustain(self): return self.filter_env.sustain
    @filter_env_sustain.setter
    def filter_env_sustain(self, v): self.filter_env.sustain = v

    @property
    def filter_env_release(self): return self.filter_env.release
    @filter_env_release.setter
    def filter_env_release(self, v): self.filter_env.release = v


@dataclass
class Preset:
    """
    One Program/Preset = one MPC Program = one E4B Preset.
    """
    name: str                               # Max 16 chars
    program_number: int = 0                 # MIDI program 0..127
    voices: List[VoiceLayer] = field(default_factory=list)
    # Global preset settings
    volume: float = 0.0                     # dB
    pan: float = 0.0                        # -1.0..+1.0
    transpose: int = 0                      # Semitones


# E4XT per-preset voice cap.  RE (RE_SUITE "NN VOICES" presets) confirmed the
# E4XT lists 16 disjoint voices fine — there is no low voice-count cap, so this
# is disabled.  The real upper limit is unknown but >16; set a value here only if
# a future RE finds one.  None = no cap.
MAX_VOICES_PER_PRESET = None


def cap_voices_by_coverage(voices: "List[VoiceLayer]",
                           max_voices=MAX_VOICES_PER_PRESET) -> "List[VoiceLayer]":
    """When a preset stacks more voices than the E4XT will load, keep the
    `max_voices` with the WIDEST key coverage (the main instrument layers) and
    drop narrow fill/doubling voices.  Original order is preserved among kept
    voices.  Returns the (possibly trimmed) voice list."""
    if not max_voices or len(voices) <= max_voices:
        return voices

    def key_coverage(v: "VoiceLayer") -> int:
        keys = set()
        for z in v.zones:
            keys.update(range(z.lo_key, z.hi_key + 1))
        return len(keys)

    keep = set(id(v) for v in
               sorted(voices, key=key_coverage, reverse=True)[:max_voices])
    return [v for v in voices if id(v) in keep]


@dataclass
class Bank:
    """Top-level container: one E4B bank = one MPC project."""
    name: str = "UNTITLED"
    presets: List[Preset] = field(default_factory=list)
    samples: List[SampleData] = field(default_factory=list)

    def find_sample(self, name: str) -> Optional[SampleData]:
        for s in self.samples:
            if s.name == name:
                return s
        return None
