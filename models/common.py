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
import math
from dataclasses import dataclass, field
from typing import List, Optional
from enum import IntEnum


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
    filter_type: int = 0        # XPM FilterType: 0=off, 1=LP12, 2=LP24, 3=LP48,
                                #   4=HP12, 5=HP24, 6=BP12, 7=BP24, 8=ContBP
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
    lfo2_to_pitch: float = 0.0       # LFO2 → Pitch       (0x68→0x30)
    lfo2_to_filter: float = 0.0      # LFO2 → Filter-Freq (0x68→0x38)
    lfo2_to_filter_q: float = 0.0    # LFO2 → Filter-Q    (0x68→0x39)
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
