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


# ── E4XT-measured cutoff and volume laws (2026-07-31) ──────────────────────
# Both were measured on real hardware with white noise / a steady tone, driven
# and captured by tests/re_banks/hw_measure.py.  See RESOLUTION_NOTES
# §E4BFILTCAL for the full tables.  These describe what the E4XT ACTUALLY
# does, as opposed to what the byte is labelled -- and they are applied in
# writers/e4b_writer.py only, because the 0-1 `filter_cutoff` position and the
# dB `volume` are SHARED internal representations that the KRZ and EIII paths
# also consume; correcting them here would silently move those formats too,
# and neither has hardware calibration to justify that.

# The cutoff sweep is NOT a single exponential. Fitting one over positions
# 0.0-0.9 looked convincing (r = 0.9958) but badly underestimates the top:
# sampling the raw bytes 217-255 that the fit had never covered showed the
# curve accelerating hard -- byte 252 measures 21.5 kHz where the exponential
# predicted 4.0 kHz. Extrapolating it would have capped every conversion at
# ~2.9 kHz while the hardware reaches beyond 20 kHz.
#
# So the law is a measured TABLE, interpolated in log-frequency, rather than
# any assumed form. Positions 0.0-0.8 come from the first white-noise sweep,
# 0.851-1.0 from the raw-byte sweep that filled the gap. Measured on the E4XT
# 2026-07-31; see RESOLUTION_NOTES §E4BFILTCAL.
_E4XT_CUTOFF_TABLE = [
    (0.000,   133.0), (0.100,   168.0), (0.200,   238.0), (0.300,   378.0),
    (0.400,   534.0), (0.500,   755.0), (0.600,  1068.0), (0.700,  1199.0),
    (0.800,  1903.0), (0.851,  2691.0), (0.878,  3390.0), (0.902,  3805.0),
    (0.925,  4271.0), (0.949,  6041.0), (0.973,  9589.0), (0.988, 21527.0),
    (1.000, 24163.0),
]
E4XT_CUTOFF_MIN_MEASURED_HZ = _E4XT_CUTOFF_TABLE[0][1]
E4XT_CUTOFF_MAX_MEASURED_HZ = _E4XT_CUTOFF_TABLE[-1][1]


def _interp(x, pts, xi=0, yi=1, logy=True):
    """Piecewise interpolation over a monotonic table of (x, y) pairs."""
    if x <= pts[0][xi]:
        return pts[0][yi]
    if x >= pts[-1][xi]:
        return pts[-1][yi]
    for a, b in zip(pts, pts[1:]):
        if a[xi] <= x <= b[xi]:
            span = b[xi] - a[xi]
            t = 0.0 if span == 0 else (x - a[xi]) / span
            if logy:
                return math.exp(math.log(a[yi]) + t * (math.log(b[yi]) - math.log(a[yi])))
            return a[yi] + t * (b[yi] - a[yi])
    return pts[-1][yi]


def e4xt_cutoff_position(hz: float) -> float:
    """Desired cutoff in Hz -> the position fraction the E4XT really renders
    there, by inverting the measured table. Requests outside the measured
    span clamp to its ends -- the hardware cannot go below ~133 Hz, and above
    ~24 kHz it is wide open anyway."""
    pts = [(f, p) for p, f in _E4XT_CUTOFF_TABLE]
    return max(0.0, min(1.0, _interp(max(hz, 1e-6), pts, logy=False)))


def e4b_cutoff_position_to_hz(pos: float) -> float:
    """The shared 0..1 cutoff position -> Hz. Inverse of `hz_to_e4b_cutoff`."""
    p = max(0.0, min(1.0, pos))
    return E4B_CUTOFF_MIN_HZ * (E4B_CUTOFF_MAX_HZ / E4B_CUTOFF_MIN_HZ) ** p


def e4xt_cutoff_byte_to_position(byte: int) -> float:
    """Inverse: a vpar[60] byte -> the SHARED 0-1 position it represents.
    Parser and writer must stay exact inverses -- when they were not, the
    correction was applied twice on every E4B->E4B conversion."""
    hw_hz = _interp(max(0.0, min(1.0, byte / 255.0)), _E4XT_CUTOFF_TABLE)
    pos = math.log(max(hw_hz, 1e-6) / E4B_CUTOFF_MIN_HZ) / math.log(
        E4B_CUTOFF_MAX_HZ / E4B_CUTOFF_MIN_HZ)
    return max(0.0, min(1.0, pos))


# Per-zone volume. vpar[54] / zone entry[15] is labelled dB, but the audio
# response is what matters: measured 2026-07-31 at a CONSTANT key (velocity-
# banded voices on one note, with a flat velocity control preset) it is almost
# exactly LINEAR, ~0.767 dB per byte unit, fitting to 0.33 dB.
#
# An earlier 13-point ladder put each gain on a different key and produced a
# strongly curved law. Both candidate confounds were then measured and came
# back flat -- level depends on neither key (+/-0.00 dB across C1-C6 with a
# non-transposing voice) nor velocity (+0.00 dB, 5 to 125) -- so why the two
# datasets disagree by ~2 dB in the middle is still unexplained. The linear law
# is used because it VERIFIES on hardware (7/7, max error 0.34 dB), which is a
# different and stronger claim than understanding the discrepancy.
_E4XT_VOL_C1 = 0.76732
_E4XT_VOL_C2 = 0.000246
E4XT_VOL_MEASURED_FLOOR_DB = -22.90   # what B = -30 actually delivers


# Pan reaches FULL DEFLECTION at byte +/-32, not +/-64 -- measured 2026-07-31
# by sweeping pan and reading the two channels separately. Bytes beyond +/-32
# are indistinguishable from +/-32, so mapping our -1.0..+1.0 through *64 threw
# away half the range: everything past +/-0.5 collapsed to hard-panned, and a
# preset panned -0.6 sounded identical to one panned -1.0.
#
# Exactly the gap the "hardware-confirmed" note on vpar[55] could not see: the
# front panel does display -64..+63, but the AUDIO saturates halfway.
#
# Also measured, and NOT compensated here: panning changes total level, with
# centre ~4.5 dB quieter than hard-panned, so this is not a constant-power
# law. Correcting that would couple pan into volume -- a bigger change than it
# looks, wanting its own verification. Recorded in TODO.
E4XT_PAN_FULL_BYTE = 32.0


# Measured 2026-08-01: panning the E4XT makes it LOUDER. Total output power
# rises ~4.5 dB from centre to hard, fitted as 4.54 * |pan|^0.75 (max residual
# 0.50 dB), and the curve is identical at every volume (spread 0.00/0.00/0.21 dB
# across 0/-6/-12 dB) and unchanged by the filter. So one curve does describe
# it -- which is what makes compensation possible at all.
_E4XT_PAN_EXCESS_K = 4.54
_E4XT_PAN_EXCESS_P = 0.75


def e4xt_pan_excess_db(pan: float) -> float:
    """How much LOUDER the E4XT plays a voice at this pan than at centre.

    Subtract this from a voice's volume to hold total power constant across
    pan -- a constant-power law, which is roughly what SFZ and SF2 assume, so
    it restores the balance a source author actually heard.

    This is a ONE-WAY transformation and deliberately not applied by the
    writer. Baking it into the volume byte makes it indistinguishable from a
    volume the user set deliberately, so the parser could not undo it and an
    E4B->E4B round-trip would drift further on every pass. It therefore belongs
    with `--mono`, `--resample` and `--trim-start` -- opt-in changes to the
    material -- rather than with the cutoff and gain corrections, which fix a
    mapping and round-trip exactly.
    """
    return _E4XT_PAN_EXCESS_K * (abs(max(-1.0, min(1.0, pan))) ** _E4XT_PAN_EXCESS_P)


def safe_filename(name: str, fallback: str = 'UNNAMED') -> str:
    """NOT FOR SAMPLER-SIDE NAME FIELDS -- host filesystems only.

    This sanitises for a POSIX/Windows filename. Applied to an AKAI directory
    entry it turned '#' into '_', and '_' is absent from the AKAI charset
    (0123456789 A-Z#+-.), so the encoder wrote a SPACE -- giving one sample two
    names, header '5BSHRDF#1' against directory '5BSHRDF 1'. Fifteen samples
    then failed to load and every sharp in the volume was silent, while every
    disc-side check passed because the zones referenced the header form.

    A sampler name field has its own charset and its own rules. Encode with that
    format's own helper, not this one.

    A model name made safe to use as one component of a filename.

    Preset and sample names are metadata and may legitimately contain anything
    the source device allowed — an E4XT preset really is called
    `Inv/Vel>Q Arco`. Writers that name a *file* after one must sanitise it, or
    the `/` is taken as a path separator and the write fails with
    FileNotFoundError on a directory that was never created.

    Unlike `_safe_name` this does not truncate and does not strip an
    extension: it is about the filesystem, not about a device's name field.
    """
    out = ''.join(c if (c.isalnum() or c in ' _-.') else '_' for c in name)
    out = out.strip(' .')
    return out or fallback


def e4xt_pan_byte(pan: float) -> int:
    """Our -1.0 (L) .. +1.0 (R) -> the vpar[55] / zone entry[16] byte."""
    return int(max(-64, min(63, round(max(-1.0, min(1.0, pan)) * E4XT_PAN_FULL_BYTE))))


def e4xt_byte_to_pan(byte: int) -> float:
    """Inverse of `e4xt_pan_byte`, so parser and writer stay inverses."""
    return max(-1.0, min(1.0, byte / E4XT_PAN_FULL_BYTE))


def e4xt_volume_byte(db: float) -> int:
    """Desired attenuation in dB -> the byte to write so the E4XT delivers it.

    Inverts the measured near-linear law (~0.767 dB per byte unit). Writing the
    dB value straight in -- what this project did until 2026-07-31 -- delivered
    only half to three-quarters of the requested attenuation. Note that
    vpar[54]'s earlier "hardware-confirmed" status only ever established that
    the FRONT PANEL displays what we write, never that the audio matched.

    Requests below `E4XT_VOL_MEASURED_FLOOR_DB` are EXTRAPOLATED past the
    fitted range and are not precise -- real hardware flattens out somewhere
    and a quadratic will not. They stay monotonic, which is what matters.
    """
    if db >= 0.0:
        return int(max(-128, min(127, round(db))))
    disc = _E4XT_VOL_C1 ** 2 + 4.0 * _E4XT_VOL_C2 * db
    if disc < 0.0:
        return -128
    root = (-_E4XT_VOL_C1 + math.sqrt(disc)) / (2.0 * _E4XT_VOL_C2)
    return int(max(-128, min(0, round(root))))


def e4xt_byte_to_volume_db(byte: int) -> float:
    """Inverse of `e4xt_volume_byte`: the dB a written byte actually delivers.
    Same round-trip requirement as the cutoff above."""
    b = float(byte)
    if b >= 0.0:
        return b
    return _E4XT_VOL_C1 * b + _E4XT_VOL_C2 * b * b


#: AKAI FILFRQ <-> Hz. **ONE definition, used by BOTH the reader and the
#: writer**, because they must be exact inverses and until 2026-08-20 only the
#: writer had a law at all -- the reader read FILFRQ into a dict and dropped
#: it, so every AKAI-sourced voice converted fully open (§AKAIFILTREAD).
#:
#: It lives here rather than in either module because `akai_s3000_writer`
#: imports `akai_s3000_parser`, so the parser cannot import back from the
#: writer without a cycle. A shared constant is also the structural guarantee
#: the two cannot drift apart, which matters more here than tidiness: a reader
#: and writer disagreeing about a hardware law is silent in both directions.
#:
#: **The CONSTANT is disputed and the QUANTITY is not.** Two of our own
#: measurements of the same S3000XL disagree by a constant 1.29x (sd 0.031
#: over FILFRQ 40..84):
#:
#:     s3ked §54  (2026-08-12)  6.4597  * exp(0.07100 v)   via the resonance
#:                                                          peak as an indicator
#:     s3ked §139 (2026-08-20)  7.60732 * exp(0.07245 v)   the -3 dB corner,
#:                                                          measured directly
#:
#: §54 argues the peak sits AT the corner and does not move with FILQ, so it
#: claims the SAME quantity by another route -- it is not a definitional
#: offset, it is an unexplained disagreement, and s3ked has it open with one
#: sweep yielding both numbers.
#:
#: **§139 is used** because it measures the -3 dB point directly, which is what
#: every source format means by "cutoff". If the sweep moves it, it moves here
#: once and both directions follow -- and an AKAI round trip stays
#: self-consistent meanwhile, because the same law cancels.
#:
#: S3000XL ONLY. §139 measured 12 dB/octave against the S1000's specified 18,
#: so neither law belongs on a `.P1`. See the generation branch in the parser.
AKAI_FILTER_LAW = (7.60732, 0.07245, 40, 84)      # Hz = a*exp(b*FILFRQ)

#: FILFRQ the machine treats as wide open. HW-confirmed: s3ked took a sweep's
#: 0 dB reference here and found no attenuation until the band edge, and it is
#: the value the machine itself rests at. Lives beside the law because both the
#: reader and the writer need it to agree about where the curve ends.
AKAI_FILTER_OPEN = 99

#: MEASURED corners above the fitted range (s3ked §146, 2026-08-21, from the
#: FILTERTOP disc: a Schroeder complex flat to 18 kHz, adjacent-setting ratios,
#: anchored on 68..84 where the corner was already known).
#:
#: **§139 was confirmed to 1.0042, sd 0.0136 inside 68..84** -- four parts in a
#: thousand, a different source and a different session -- and then **stops
#: being right immediately above it.** The measured corner rises faster than
#: the exponential and the gap grows monotonically:
#:
#:      FILFRQ   measured   §139 law   ratio
#:          84       3421       3344   1.023
#:          86       3984       3865   1.031
#:          88       4643       4468   1.039
#:          90       5512       5165   1.067
#:          92       6888       5970   1.154
#:          94       8481       6901   1.229
#:
#: So extrapolating the law understates the corner by up to 23% across exactly
#: the band where most S3000 factory material sits. These points replace the
#: extrapolation. 90..94 are marked marginal by s3ked -- they are still far
#: better than a law known to be 7..23% low there.
AKAI_FILTER_MEASURED = {84: 3421.0, 86: 3984.0, 88: 4643.0, 90: 5512.0,
                        92: 6888.0, 94: 8481.0}

#: The law is used only up to HERE, which is **one rung below its own fitted
#: top** (s3ked §146 refined, 2026-08-21). The departure begins AT 84, not
#: above it:
#:
#:      68..80   mean 0.9996  sd 0.0085     flat
#:      68..84   mean 1.0043  sd 0.0128     §139's own fitted range
#:      68..88   mean 1.0131  sd 0.0184
#:
#: Point by point the flat region scatters 0.987..1.007, and 84 sits at 1.023 --
#: outside it, and the first step of a monotone run (1.023, 1.031, 1.039,
#: 1.067, 1.154, 1.229). **A fit's upper bound is where it is least
#: constrained**, with the fewest neighbours holding it, so it is the first
#: point to go and the one an average over the range is least able to show.
#:
#: Both projects computed the same "1.004 across the fitted range" and neither
#: looked at its last point until an outlier forced it. A mean over a range
#: answers a question about the range, not about its endpoints.
#:
#: Nothing is lost by moving the boundary down: 84 has a measured corner.
AKAI_FILTER_LAW_TRUSTED_TO = 80

#: At and above this, the filter is INDISTINGUISHABLE FROM WIDE OPEN and is
#: treated as such rather than given a frequency. FILFRQ 98 differs from 99 by
#: **2.2 dB across the whole band** -- they are the same filter, and 96 was not
#: measurable against the reference either. Assigning them corners would be
#: inventing three numbers the machine does not distinguish.
AKAI_FILTER_SATURATED = 96

#: ENVELOPE 2 (filter) -- times for a FULL 0..99 traverse, from s3ked's
#: `s3k/scales.py`. Shared by the reader and the writer for the same reason
#: AKAI_FILTER_LAW is: two hand-derived inverses of one curve drifted apart on
#: 2026-08-20 and nine of ten values failed a round trip while a docstring
#: claimed they could not.
#:
#: A stage covering less than the full range takes proportionally less:
#: `full_time * distance / 99`. Attack climbs the whole range, decay falls
#: from the top to the sustain level, release falls from sustain to zero.
AKAI_ENV2_ATTACK  = (0.001363, 0.09703, 40, 85)     # s, r2 0.99981
AKAI_ENV2_DECAY   = (0.002464, 0.09844, 40, 80)     # s, r2 0.99997
AKAI_ENV2_RELEASE = (0.001344, 0.09692, 40, 80)     # s, r2 0.99998

#: Envelope2 -> Filter Frequency depth: keygroup 153, +-50 (§AKAIVFR).
#: §144 measured AKAI's own import defaulting 151/152/153 to ZERO, so an
#: envelope with no depth here modulates nothing -- which is why the reader
#: must treat depth 0 as "no filter envelope" rather than as a full-depth one.
AKAI_ENV2_DEPTH_OFFSET = 153
#: FILTER-ENVELOPE DEPTH: DERIVED FROM TWO HARDWARE LAWS, NOT CHOSEN.
#:
#: This was 50 -- a guess with no measurement behind it, which delivered 2.8x
#: the sweep the source asked for. Both halves were measured on 2026-08-22 and
#: both machines turn out to multiply envelope LEVEL by depth, so the sustain
#: cancels out of the mapping and one constant suffices:
#:
#:   E4XT   octaves = 5.14e-4 * level% * amount%     eosed §46
#:          12 levels, 132 captures, shifts <= 3 oct (n=106), median residual
#:          7.4%; log-log fit k ~ level^0.974 against 1.000 for a pure product.
#:          An earlier reading of this as level-DEPENDENT (k falling 37% across
#:          three levels) was withdrawn -- three points had landed on a
#:          descending stretch of scatter. Asking for more levels is what caught
#:          it; no instrument check would have, because the captures were clean
#:          and the fit was good.
#:   AKAI   octaves = 0.002837 * SUSTN2 * depth      s3ked §148
#:          7 points spanning products 250..1980, i.e. 0.72 to 5.80 octaves,
#:          sd 5.2% with no trend against product.
#:
#: Equating them for a source at sustain S and amount A:
#:     5.14e-4 * 100S * 100A  ==  0.002837 * 99S * (A * DEPTH_MAX)
#: S and A both cancel, leaving DEPTH_MAX = 5.14e-4 * 1e4 / (0.002837 * 99).
#:
#: NOT hardware-confirmed END TO END: the two laws are measured, the arithmetic
#: joining them is not yet checked by converting a bank and listening to it.
#: Octaves per (SUSTN2 x depth), REMEASURED by s3ked on white noise
#: 2026-08-24, superseding §148's 0.002837. Their section number is not cited
#: here because it was still being written when this landed; the run is dated
#: and the numbers below are the whole of it.
#:
#:     octaves = 0.002612 * SUSTN2 * depth      sd 0.000017, spread 0.7%
#:
#: Ten points that are neither bin-limited nor at the ceiling, across TWO
#: sustain settings and depth 5..50. No compression and no knee — depth is
#: linear across its whole range. The cross-check is the part to trust: SUSTN2
#: 99 / depth 15 has product 1485 and measured 3.862 octaves, where the SUSTN2
#: 25 fit predicts 3.874 — 0.3% apart from opposite ends of the range.
#:
#: **§148's 0.00283 was 8% higher and the gap is not just its ceiling-bound
#: point.** Its own mean excluding that point is 0.002822. s3ked's candidates:
#: §148 used a harmonic Schroeder complex and read the resonance PEAK, and
#: §145 showed the peak/corner ratio drifts with frequency; its base was 134 Hz,
#: below the tracker's stated 500 Hz floor for harmonic sources. White noise has
#: no comb, so that floor does not apply to the new run. Unsettled; the new one
#: is preferred only because it is internally consistent across two sustains.
AKAI_ENV2_OCT_PER_UNIT = 0.002612

#: **THE AKAI FILTER CORNER STOPS AT 7.86 kHz, whatever the depth asks for.**
#: s3ked, 2026-08-24: eight points across two base cutoffs, 1.6% spread —
#:
#:     from base  325 Hz: depth 25 -> 7787, 30 -> 7912, 40 -> 7862, 50 -> 7887
#:     from base 1325 Hz: depth 10 -> 7850, 20 -> 7850, 30 -> 7837
#:
#: The law predicts 28 kHz at depth 25 and 2.5 MHz at depth 50. The machine
#: sits at 7.86 kHz and stops. Controls rule out the material (44.1 kHz source
#: with content to 22 kHz) and the analysis window (ran to 20 kHz).
#:
#: **This is why there is no single AKAI_ENV2_DEPTH_MAX.** The ceiling is
#: absolute in Hz, so the largest shift available is `log2(7858 / base_Hz)` and
#: depends entirely on where the base sits: 5.87 octaves from FILFRQ 40, 4.27
#: from 55, 1.08 from 85. A converter mapping source depth onto a fixed octave
#: span cannot be right at more than one base.
#:
#: So CLAMP THE TARGET CORNER, never the depth.
AKAI_ENV2_CEILING_HZ = 7858.0


def akai_env2_target_hz(base_hz: float, sustn2: int, depth: int) -> float:
    """Where an AKAI ENV2 actually takes the corner, ceiling included."""
    if base_hz <= 0 or depth <= 0 or sustn2 <= 0:
        return max(0.0, base_hz)
    octaves = AKAI_ENV2_OCT_PER_UNIT * sustn2 * depth
    # The ceiling is a MAXIMUM, so it can never pull the corner BELOW its own
    # base -- a base already above 7.86 kHz (a saturated FILFRQ treated as the
    # machine's open corner) would otherwise produce a negative shift from a
    # positive depth, which reads as a downward sweep that was never asked for.
    return max(base_hz, min(base_hz * 2.0 ** octaves, AKAI_ENV2_CEILING_HZ))


def akai_env2_max_octaves(base_hz: float) -> float:
    """The largest shift reachable from this base — NOT a constant."""
    if base_hz <= 0:
        return 0.0
    return max(0.0, math.log2(AKAI_ENV2_CEILING_HZ / base_hz))

E4B_FENV_OCT_PER_UNIT  = 5.14e-4    #: octaves per (level% x amount%), eosed §46
AKAI_ENV2_DEPTH_MAX = (E4B_FENV_OCT_PER_UNIT * 100.0 * 100.0
                       / (AKAI_ENV2_OCT_PER_UNIT * 99.0))     #: ~18.3


#: VLOUD1 (per-zone level offset) -> dB. s3ked 2026-08-17: the full law is
#: `dB = 0.60576 * VLOUD1 - 20.1778`, r2 0.999896 over -50..+20; the intercept
#: is the absolute output level at VLOUD 0, so an OFFSET uses the slope alone.
#: Named here rather than left inline in the writer because the reader needs
#: the same number to invert it (CR-13).
AKAI_VLOUD_DB_PER_UNIT = 0.60576

#: AKAI KGTUNO/VTUNO are 1/256 semitone, so cents are `units * 100 / 256`.
#: Named because it has been got wrong twice: the writer multiplied by 256 and
#: by 16 before 2026-08-11, and the reader still divided by 16 until
#: 2026-08-23 (§AKAITUNEREAD).
AKAI_TUNE_UNITS_PER_SEMITONE = 256


#: How long a keygroup sounds before its mute-group partner cuts it.
#:
#: MEASURED by s3ked 2026-08-23 at 10 ms resolution on an S3000XL: the losing
#: layer is present for exactly one window and gone by the next. Both
#: keygroups are triggered by the SAME note-on, so the delay is the voice
#: allocator's own latency and does not depend on anything the player does --
#: which is what makes it emulable by an envelope at all.
#:
#: ONE MEASUREMENT, ONE NOTE, ONE PROGRAM. Whether it varies with polyphony,
#: note or velocity is untested, and 10 ms is the resolution of the trace
#: rather than a fitted value. Good enough to reproduce the audible effect,
#: not good enough to quote as a machine constant.
AKAI_MUTE_CUT_SECONDS = 0.010

#: The AKAI LFO1, all three fields, fitted across the WHOLE 0..99 field rather
#: than a window. s3ked's `s3k/scales.py`, 2026-08-12:
#:
#:     LFORAT  Hz     0.11867 * x - 0.04              r2 0.9995
#:     LFODEP  cents  19.4932 * x   (PEAK-TO-PEAK)    r2 0.99949
#:     LFODEL  s      0.06905 * x / (103.41 - x)      r2 0.999555
#:
#: **The reader read none of them until 2026-08-24** — a grep for "lfo" in this
#: parser returned nothing — so every AKAI-sourced conversion lost its vibrato
#: entirely. Ninth instance of the pattern that ran through this week: a writer
#: law measured and wired while the read path was never done. Jan heard it as
#: "a little vibrato during the sustain and release" that our conversion did
#: not have.
#:
#: LFODEP is peak-to-peak, so full scale is 1930 cents pp = +/-9.6 semitones —
#: a much wider range than the panel suggests. Our `lfo1_to_pitch` is a
#: one-sided depth against `LFO_PITCH_FULL_CENTS`, so the conversion halves it.
#:
#: NOTE THE FIELD NAME: s3ked calls the delay `LFODEL`, at program offset 35.
#: Calling it LFODLY sends a grep to the wrong place in their tree.
AKAI_LFO_RATE_HZ_PER_UNIT = 0.11867
AKAI_LFO_RATE_HZ_OFFSET = -0.04
AKAI_LFO_DEPTH_CENTS_PP_PER_UNIT = 19.4932
AKAI_LFO_DELAY_NUM = 0.06905
AKAI_LFO_DELAY_POLE = 103.41


def akai_lfo_rate_hz(byte: int) -> float:
    """LFORAT -> Hz."""
    return max(0.0, AKAI_LFO_RATE_HZ_PER_UNIT * max(0, min(99, byte))
               + AKAI_LFO_RATE_HZ_OFFSET)


#: The E4XT resonance parameter, MEASURED by eosed 2026-08-24 (§E4XTQCAL):
#: byte -> resonant peak height in dB above the passband, 2-pole, corner parked
#: where the peak resolves. **The 4-pole is exactly twice these dB at the same
#: byte** — 2.00 at every point, which is what cascading two identical sections
#: does — so one table covers the whole lowpass family via `poles / 2`.
#:
#: Replaces `round(resonance * 127)`, which was an uncalibrated linear guess of
#: exactly the shape as the K2000 filter-envelope depth fixed on 2026-08-22:
#: that one was 23x too little at low amounts and 1.75x too much at full,
#: because the field's response is not linear in anything audible.
_E4XT_Q_TABLE = [
    (0, 0.11), (8, 0.64), (16, 1.39), (24, 2.60), (32, 3.76), (40, 4.85),
    (48, 6.13), (56, 7.59), (64, 9.15), (72, 10.62), (80, 11.87), (88, 13.02),
    (96, 14.39), (108, 15.54), (112, 17.84),
]

#: **Bytes 112..127 are the same filter.** 17.8 dB flat within noise while the
#: panel goes on printing whatever was set — fifteen dead steps, so a writer
#: clamping to 127 silently writes 112. No self-oscillation anywhere: pre-roll
#: sat at -85 to -86 dBFS at every point on both filter types, checked rather
#: than assumed, since a ringing filter puts energy in the capture BEFORE the
#: note is sent.
E4XT_Q_MAX_BYTE = 112
E4XT_Q_MAX_DB = 17.84


#: What `VoiceLayer.filter_resonance == 1.0` MEANS, in dB of resonant peak
#: above the passband.
#:
#: The field had no absolute meaning at all until 2026-08-24 — every parser
#: normalised by its own machine's range, so a "0.5" from one format and a
#: "0.5" from another were different sounds, and no conversion could preserve
#: what a listener actually hears. Peak height in dB is the right currency for
#: the same reason it was for the AKAI/E4XT Q comparison: for a filter of a
#: given order it determines the response shape, and it is directly measurable
#: on both machines without composing anything.
#:
#: Set to the AKAI's own maximum (FILQ 15 = 25.51 dB), the widest measured
#: range we have, so that the format with the most resonance available defines
#: full scale and nothing has to exceed 1.0.
#:
#: **CONSEQUENCE, STATED RATHER THAN HIDDEN: the E4XT tops out at 17.84 dB.**
#: An AKAI source above about FILQ 13 asks for more than the E4XT can produce
#: and clamps, so two keygroups asking for different resonances can arrive
#: identical. That is a real limit of the target and belongs in the conversion
#: log, not in a rounding.
#:
#: **NOT YET APPLIED TO EVERY PARSER.** `e4b_parser` and this writer are a
#: matched pair through the measured table; `krz_parser` and others still
#: normalise by their own ranges and are therefore on a different scale. That
#: is a real inconsistency and it is recorded rather than fixed blind — fixing
#: it means knowing each machine's peak-height range, which only the AKAI and
#: the E4XT currently have measured.
RESONANCE_FULL_DB = 25.51


def e4xt_resonance_byte(amount: float, poles: int = 2) -> int:
    """Model resonance 0..1 -> the E4XT byte that delivers the same PEAK dB.

    Matches the resonant peak height rather than the fraction-of-range, because
    dB is what is audible and a fraction is meaningless across machines with
    different ranges. Interpolated linearly in dB between measured points — the
    curve is smooth and the points dense enough that a fit would add nothing
    but a place to be wrong.

    Clamped at `E4XT_Q_MAX_BYTE`, not 127. Writing 127 is not an error the
    machine reports; it is fifteen steps of nothing.
    """
    scale = max(1, poles) / 2.0
    target = max(0.0, min(1.0, amount)) * RESONANCE_FULL_DB * scale
    tbl = [(b, db * scale) for b, db in _E4XT_Q_TABLE]
    if target <= tbl[0][1]:
        return tbl[0][0]
    for (b0, d0), (b1, d1) in zip(tbl, tbl[1:]):
        if target <= d1:
            f = (target - d0) / (d1 - d0) if d1 > d0 else 0.0
            return int(round(b0 + f * (b1 - b0)))
    return E4XT_Q_MAX_BYTE


def e4xt_byte_to_resonance(byte: int, poles: int = 2) -> float:
    """Inverse of `e4xt_resonance_byte`, so reader and writer stay inverses."""
    b = max(0, min(E4XT_Q_MAX_BYTE, int(byte)))
    scale = max(1, poles) / 2.0
    tbl = _E4XT_Q_TABLE
    if b <= tbl[0][0]:
        db = tbl[0][1]
    else:
        db = tbl[-1][1]
        for (b0, d0), (b1, d1) in zip(tbl, tbl[1:]):
            if b <= b1:
                f = (b - b0) / (b1 - b0) if b1 > b0 else 0.0
                db = d0 + f * (d1 - d0)
                break
    return max(0.0, min(1.0, db * scale / RESONANCE_FULL_DB))


#: The AKAI vibrato depth, MEASURED AS A PRODUCT of both fields (s3ked,
#: 2026-08-24, by sideband analysis after the pitch tracker could not do it):
#:
#:     rms_cents = 0.13127 * LFODEP * L_PTCH        k sd 0.0055, spread 4.2%
#:
#: **The control is not the spread.** The same product reached from different
#: settings is what tests the product FORM: 30x10 against 6x50, both product
#: 300, agree to 8.6%, while same-setting repeatability is 0.5%. So this is "a
#: product to within about 9%", not "a product" — s3ked's phrasing and the
#: right one. Better than 9% needs a wider product range than the estimator's
#: window allows.
#:
#: **RMS is the primary form because the estimator is waveform-independent** —
#: a second moment about the carrier equals the mean square deviation for FM by
#: any periodic shape. Only converting to peak-to-peak needs a waveform.
AKAI_LFO_RMS_CENTS_PER_PRODUCT = 0.13127

#: `L_PTCH` at which §35's `19.4932 cents pp per LFODEP unit` was measured.
#: **IDENTIFIED 2026-08-24, having been unrecorded.** Converting the RMS law
#: back needs the LFO shape, and §35 recorded neither the routing nor the wave:
#:
#:     if sine     19.4932 / 2.828 = 6.892 rms/unit -> L_PTCH 52.5
#:     if triangle 19.4932 / 3.464 = 5.627 rms/unit -> L_PTCH 42.9
#:
#: The field's maximum is 50. So §35 was calibrated at or near MAXIMUM routing:
#: 52.5 is 5% over the top and inside the k spread, consistent with exactly 50.
#: The sine reading is therefore the likely one, and scaling §35 by L_PTCH/50 is
#: approximately right — which was the obvious guess, refused on 2026-08-24 for
#: want of evidence, and is now measured rather than plausible.
AKAI_LFO_DEPTH_CAL_LPTCH = 50


def akai_lfo_rms_cents(lfodep: int, l_ptch: int) -> float:
    """AKAI vibrato depth in RMS cents. Both fields, measured as a product."""
    return (AKAI_LFO_RMS_CENTS_PER_PRODUCT
            * max(0, min(99, lfodep)) * abs(max(-50, min(50, l_ptch))))


def akai_lfo_depth_to_pitch(byte: int, l_ptch: int = None) -> float:
    """LFODEP (+ the keygroup's `L_PTCH` gate) -> one-sided `lfo1_to_pitch`.

    The field is PEAK-TO-PEAK cents and our model field is one-sided against
    `LFO_PITCH_FULL_CENTS`, so this halves as well as scaling. Getting that
    wrong would double every vibrato — the same seam as the K2000 LFO depth,
    where the half-swing convention had to be checked on both sides before a
    factor of two could be ruled out.

    **`l_ptch` GATES, and does not yet SCALE.** MEASURED 2026-08-24 against a
    floor established in the same run: LFODEP 99 with L_PTCH 0 produces no
    vibrato, L_PTCH 50 with LFODEP 0 produces none either, and both non-zero
    produces a strong one. So 0 means silence here and that is applied.

    What is NOT applied is a proportional scaling, and the temptation is
    considerable — this program carries L_PTCH 7 of a possible 50, and 7/50
    would take a vibrato Jan calls "far too extreme" down to a plausible ±11
    cents. It is not applied because **nobody has shown the two compose
    multiplicatively**, and because 19.4932 was itself measured at an
    unrecorded non-zero L_PTCH, so there is no reference point to scale
    *from*. s3ked's pitch tracker could not resolve the composition — octave
    errors dominate at exactly the swings involved — and the honest instrument
    for it is sideband analysis, which does not exist yet (§AKAILPTCH).

    Applying 7/50 on the strength of it looking right would be fitting a
    constant to one listener's word for a symptom, which is the shape of most
    of the false findings this week.
    """
    if l_ptch is None:
        l_ptch = AKAI_LFO_DEPTH_CAL_LPTCH      # the calibration's own routing
    if l_ptch == 0:
        return 0.0
    # Through the MEASURED product, not through §35 scaled by a guess. RMS is
    # the form that was measured; the triangle factor takes it to one-sided
    # peak, which is what `lfo1_to_pitch` means.
    one_sided = akai_lfo_rms_cents(byte, l_ptch) * math.sqrt(3.0)
    return max(0.0, min(1.0, one_sided / LFO_PITCH_FULL_CENTS))


def akai_lfo_delay_seconds(byte: int) -> float:
    """LFODEL -> seconds. A pole, not a line: it runs away near byte 99."""
    b = max(0, min(99, byte))
    return AKAI_LFO_DELAY_NUM * b / max(1e-6, AKAI_LFO_DELAY_POLE - b)


#: FILQ (keygroup 149) -> resonance. s3ked §52, 2026-08-12, r2 0.999975,
#: replacing their own earlier linear 0.5764 dB/step reading:
#:
#:     damping z = 0.46864 - 0.029587 * FILQ
#:     dB        = -20 log10(1 - FILQ / 15.84)
#:     Q         = 1.067 / (1 - FILQ / 15.84)      1.07 at 0, ~20 at 15
#:
#: Damping reaches zero at 15.84, just past the top of the field, so the
#: machine stops short of self-oscillation and one number generates all
#: sixteen steps. The linear reading had the SHAPE backwards -- the last three
#: steps are worth more than the first ten together, which is why a
#: normalisation that assumes linearity gets the loud end badly wrong.
AKAI_FILQ_DAMPING_ZERO = 15.84
AKAI_FILQ_MAX = 15


def akai_filq_to_db(byte: int) -> float:
    """FILQ -> the resonant peak's height in dB above the passband."""
    z = 1.0 - max(0, min(AKAI_FILQ_MAX, byte)) / AKAI_FILQ_DAMPING_ZERO
    return -20.0 * math.log10(z) if z > 0 else 60.0


def akai_filq_to_01(byte: int) -> float:
    """FILQ -> the model's 0..1 resonance, as a fraction of the AKAI's own range.

    **Read by nobody and written by nobody until 2026-08-23** — every
    AKAI-sourced conversion we ever made had a filter with no resonance at all,
    while real programs use it heavily: one factory electric piano carries
    FILQ 7 on its unison layers and 13, 14 and 15 on its octave layers, which
    is Q 1.9 against Q 6 to 20 (§E4XTQCAL).

    Normalised in **dB of peak height**, not in field units, because the field
    is not linear in anything audible: FILQ 7 of 15 is 5.1 dB of a 25.5 dB
    range, i.e. a fifth, not a half.

    **This is the reader's half only.** What the destination machine does with
    a 0..1 resonance is its own problem, and the E4B writer's `round(res*127)`
    is an uncalibrated linear guess — the same shape as the K2000 depth bug
    fixed on 2026-08-22. eosed measured the E4XT's real curve on 2026-08-23
    (peak height per byte, clamping at byte 112 = 17.84 dB, and exactly twice
    that on the 4-pole), so it is now fixable; it is not fixed here.
    """
    full = akai_filq_to_db(AKAI_FILQ_MAX)
    return max(0.0, min(1.0, akai_filq_to_db(byte) / full))


#: The E4XT FilterEnv -> FilterFreq cord, measured properly at last.
#:
#: **THE CORD ADDS CUTOFF BYTES, NOT OCTAVES.** eosed, 2026-08-24, 57 points
#: over five base cutoffs (§AKAIENV2DEPTH, their §56):
#:
#:     delta_byte = E4XT_FENV_BYTE_PER_UNIT * level_percent * amount
#:
#: 2.506 byte per amount-unit at level 100, residual RMS 2.1 bytes over 41
#: unsaturated points; an independent refit here through their own byte<->Hz
#: calibration gives 2.480, agreeing to 1.0%.
#:
#: **It does NOT depend on the base cutoff.** Five bases agree to ~2.5% in
#: BYTES. In OCTAVES the same data looks strongly base-dependent — 0.0917
#: oct/unit from byte 0 against 0.0542 from byte 100 — and that is entirely an
#: artefact of the byte->Hz curve not being a pure exponential. It is also why
#: three octave voices of one program needed amounts 32, 15 and 39 for the same
#: source depth: three different bases, all landing within 2 bytes of each
#: other.
#:
#: **What this retires.** `E4B_FENV_OCT_PER_UNIT` (5.14e-4) is the same product
#: form in the wrong unit, and the "one cord is worth 5.14 octaves, the source
#: wants 7.02, so we clamp" story was never real — the old law simply
#: under-predicted what amount 100 does. One cord at full depth is worth 250.6
#: bytes of a 0..255 range, i.e. the entire cutoff range from any base.
#:
#: **Saturation is the CUTOFF BYTE hitting its ceiling, not a cord limit.**
#: Every saturated point predicts `base + 2.506*amount >= 250.3` and every
#: unsaturated one `<= 238.1` — clean separation, no overlap.
E4XT_FENV_BYTE_PER_UNIT = 2.506
E4XT_FENV_SATURATION_BYTE = 250.0   #: above this the cutoff byte is at its end


def e4xt_cord_amount(base_byte: float, target_byte: float,
                     level_percent: float = 100.0) -> int:
    """Cord amount that moves the corner from `base_byte` to `target_byte`.

    This is the function the conversion should use instead of composing two
    depth laws measured on two different machines. Converting CORNER POSITIONS
    rather than depths is what removes the base-dependence, because the cord's
    effect is linear in the byte and not in the frequency.

    Clamped to 0..100: the cord field's own range. A target the cord cannot
    reach from this base is reported by `e4xt_cord_saturates`, not silently
    approximated here.
    """
    if level_percent <= 0.0:
        return 0
    per_unit = E4XT_FENV_BYTE_PER_UNIT * (level_percent / 100.0)
    return max(0, min(100, round((target_byte - base_byte) / per_unit)))


def e4xt_cord_saturates(base_byte: float, amount: float,
                        level_percent: float = 100.0) -> bool:
    """Would this cord push the cutoff byte off the end of its range?

    Measured boundary rather than an assumed one: every saturated point in
    eosed's sweep predicts at or above 250.3 and every unsaturated one at or
    below 238.1.
    """
    reached = base_byte + (E4XT_FENV_BYTE_PER_UNIT
                           * (level_percent / 100.0) * amount)
    return reached >= E4XT_FENV_SATURATION_BYTE


def akai_env2_stage_seconds(byte: int, distance: float, law) -> float:
    """A stage byte -> the seconds it takes to cover `distance` of 99.

    **Byte 0 is INSTANT, and used not to be.** The fitted range starts at 40,
    and this clamped anything below it up to 40 -- so every byte from 0 to 40
    returned the same 66 ms, and a source asking for an instant filter attack
    got a 66 ms fade. On a percussive program that removes the entire
    transient, which is exactly what it did: see §AKAIENV2FLOOR, where it cost
    an evening of chasing the missing attack through filter parameters.

    Below the fitted range the law is now EXTRAPOLATED rather than clamped.
    That is not free -- extrapolation below a measured range is a fault this
    project has been bitten by repeatedly -- but the clamp is demonstrably
    wrong here and the extrapolation is at least monotonic and lands at 1.4 ms
    for byte 1, which is the right order of magnitude for "fast". Byte 0 is
    special-cased to exactly zero because "instant" is a semantic value the
    source states, not a point on a curve.

    The top is still clamped at the fitted maximum: extrapolating upward would
    invent slow stages nobody has measured.
    """
    a, b, lo, hi = law
    byte = max(0, min(hi, byte))
    if byte == 0:
        return 0.0
    full = a * math.exp(b * byte)
    return full * (max(0.0, distance) / 99.0)


#: The highest corner the AKAI filter actually distinguishes, and the lowest.
#: `akai_filfrq_to_hz` returns None at or above `AKAI_FILTER_SATURATED` because
#: the machine does not tell those settings apart — but "wide open" still has a
#: frequency, and a NEGATIVE ENV2 depth sweeps downward from it audibly. Using
#: these as the base for a saturated FILFRQ keeps that convertible instead of
#: silently dropping it.
AKAI_FILTER_OPEN_HZ = 8481.0     #: FILFRQ 95, the top of the measured table
AKAI_FILTER_FLOOR_HZ = 100.0     #: below the lowest measured corner


def akai_filfrq_to_hz(byte: int):
    """FILFRQ -> the -3 dB corner in Hz, or None when it is wide open.

    Measured everywhere, extrapolated nowhere:

      * at or above `AKAI_FILTER_SATURATED` -> **None**, i.e. open. The machine
        does not distinguish these settings from 99.
      * inside `AKAI_FILTER_MEASURED` -> the measured corners, interpolated
        geometrically between them (the scale is logarithmic in frequency, so
        a straight line in log Hz is the right interpolation and a straight
        line in Hz is not).
      * at or below `AKAI_FILTER_LAW_TRUSTED_TO` (80) -> the §139 law, which
        is flat against measurement to 0.9996, sd 0.0085, over 68..80.
    """
    a, b, lo, hi = AKAI_FILTER_LAW
    if byte >= AKAI_FILTER_SATURATED:
        return None
    pts = sorted(AKAI_FILTER_MEASURED)
    if byte >= pts[0]:
        if byte in AKAI_FILTER_MEASURED:
            return AKAI_FILTER_MEASURED[byte]
        for x0, x1 in zip(pts, pts[1:]):
            if x0 <= byte <= x1:
                y0, y1 = AKAI_FILTER_MEASURED[x0], AKAI_FILTER_MEASURED[x1]
                f = (byte - x0) / (x1 - x0)
                return math.exp(math.log(y0) + f * (math.log(y1) - math.log(y0)))
        return AKAI_FILTER_MEASURED[pts[-1]]
    top = AKAI_FILTER_LAW_TRUSTED_TO
    if byte > top:                      # between the trusted top and the first
        y0 = a * math.exp(b * top)      # measured point
        y1 = AKAI_FILTER_MEASURED[pts[0]]
        f = (byte - top) / (pts[0] - top)
        return math.exp(math.log(y0) + f * (math.log(y1) - math.log(y0)))
    return a * math.exp(b * max(lo, byte))


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


# ---------------------------------------------------------------------------
# EOS envelope: the byte is a RATE, not a duration  (§ENVSPAN, hardware 2026-08-18)
# ---------------------------------------------------------------------------
#
# Measured on an E4XT: the same rate byte with a 15.0 dB span took 0.540 s and
# with a 3.7 dB span took 0.135 s -- 4.00x the time for 4.09x the dB distance.
# So the decay is LINEAR IN dB and the time is the dB distance over a constant
# rate. A duration model predicts 1.00x and is dead.
#
# LEVEL LAW, fitted over sustain bytes 80-116 across three banks and two sources
# (SUSLEVEL relabelled, SUSANCHOR sine and harmonic), R^2 = 0.9983:
#
#     dB below peak = 97.82 - 0.7718 x level_byte
#
# It extrapolates to 0 dB at byte 126.7 -- and byte 127 is full sustain, where
# the plateau must EQUAL the peak. That point was not in the fit and was not
# told to agree; the byte-127 controls measured 0.27 dB below peak. Two
# independent routes to the same place.
#
# Below the fit window it still holds: bytes 64-80 agree to 0.6 dB uncorrected,
# with the residual in the direction noise contamination predicts (a noise floor
# ADDS to the plateau, shrinking the apparent span). Above it the plateau
# saturates against the peak it is divided by.
#
# RATE LAW -- REPLACED 2026-08-24 after a swept calibration (§E4BRATEANCHOR).
#
# WAS:  dB/s = 27.9 x 2 ** (-(byte - 72) / 12.3),  from ENVSPAN, "confirmed on
#       SUSLEVEL's decay times at 26.5 dB/s against 27.9 (5%, unexplained and
#       not worth chasing)".
#
# It was worth chasing. That law is 13-19% FAST across every byte anyone has
# since measured, and the 5% residual its own comment dismissed was the visible
# corner of it. It stayed invisible for months because EVERY path through this
# converter uses the law in BOTH directions, so a round trip through our own
# code cancels it exactly -- our tests could not see it and no test written in
# the same style ever would.
#
# NOW, measured on a stationary looped white-noise subject, one voice, filter
# open, no filter envelope, no LFO, envelope jumping straight to sustain and
# holding so the release is the only thing moving (eosed, 2026-08-24):
#
#     byte    measured   this law   ratio
#      60      46.48      46.59     1.00
#      72      23.70      23.65     1.00
#      88       9.67       9.58     1.01
#     100       4.84       4.86     1.00
#
# Residuals 0.41-0.43, thirds within +/-0.12, spans of 56 dB. **Byte 100 is
# twelve bytes outside the window the law was originally fitted over and still
# lands at 1.00x**, so 60..100 is now a MEASURED range rather than an
# extrapolation -- which is what §LAWRANGE asks for and what the old constants
# never had.
#
# A seven-point refit of our own was rejected in favour of these constants: two
# of its points came from fits whose lower edge stood in the noise floor, which
# levers a log-domain slope downward, and it predicts 23.88 at byte 72 against
# a measured 23.70 where this law gives 23.65. **A law measured across a range
# beats a fit pulled by two bad points**, even when the fit is ours.
#
# THE PREMISE, measured the same session and worth stating because everything
# downstream is quoted in dB/s: the byte is a SPEED and not a duration. Two
# sustain levels 17 dB apart, same rate byte, on two independent noise draws:
# 27.96 / 28.31 / 27.97 / 28.33 dB/s -- same to 1.3%.
#
# AND THE RATE DOES NOT SCALE WITH KEY OR WITH DISTANCE FROM ROOT. Six captures
# of ONE sample at root distances -24 to +24, achieved by moving the root rather
# than the note: 27.95 to 28.03, spread 0.3%. So an apparent rate that varies
# across a keyboard is the SAMPLE's own contour showing through a fit that
# assumes the envelope is the only thing moving -- not the machine.
#
#     dB per second = 1382 x exp(-0.0565 x byte)
#
#: NAMED FOR THE BYTE, not just 'level'. `ENV_LEVEL_DB_INTERCEPT` already
#: exists below for the sustain-PERCENT law and silently shadowed these when
#: they were first written -- the module defined mine, then redefined the
#: name 80 lines later, and every reading came out 0 dB. Python said nothing.
ENV_LEVELBYTE_DB_INTERCEPT = 97.82   #: dB below peak at level byte 0
ENV_LEVELBYTE_DB_PER_BYTE  = 0.7718  #: dB recovered per level byte
#: The swept law's own two constants. Everything below is DERIVED from these
#: rather than transcribed alongside them: the previous set was three numbers
#: kept consistent by hand, and a hand-maintained anchor is exactly what went
#: stale. Change these two and the rest follows.
ENV_RATE_SWEEP_A = 1382.0    #: dB/s at byte 0 (extrapolated; fitted 60..100)
ENV_RATE_SWEEP_K = 0.0565    #: per byte, natural log

ENV_RATE_BYTE_REF      = 72
ENV_RATE_HALVING_BYTES = math.log(2.0) / ENV_RATE_SWEEP_K   #: 12.268
ENV_RATE_DB_PER_S_REF  = ENV_RATE_SWEEP_A * math.exp(       #: 23.648
    -ENV_RATE_SWEEP_K * ENV_RATE_BYTE_REF)


def env_level_byte_to_db(level_byte: int) -> float:
    """How far below the attack peak a sustain LEVEL byte sits, in dB."""
    b = max(0, min(127, int(level_byte)))
    return max(0.0, ENV_LEVELBYTE_DB_INTERCEPT
                    - ENV_LEVELBYTE_DB_PER_BYTE * b)


def env_rate_byte_to_db_per_s(rate_byte: int) -> float:
    """The slew rate a rate byte produces, in dB per second."""
    b = max(0, min(127, int(rate_byte)))
    return ENV_RATE_DB_PER_S_REF * 2.0 ** (
        -(b - ENV_RATE_BYTE_REF) / ENV_RATE_HALVING_BYTES)


def env_db_per_s_to_rate_byte(db_per_s: float) -> int:
    """A slew rate in dB/s -> the EOS rate byte that produces it.

    The exact inverse of `env_rate_byte_to_db_per_s`, and the ONLY correct way
    to move a release between two rate machines (§AKAIRELSPAN).

    **Seconds are the wrong interchange currency for a release.** A decay stops
    at the sustain level, which both an AKAI and an E4XT agree on and either
    can be metered for, so converting a decay through seconds is sound. A
    release stops at *silence* -- and the AKAI's notion of that is 60.07 dB
    below peak (its sustain byte scale x 99) while the E4XT's is 97.82 (its
    level law at byte 0). **Neither number was ever measured.** Both are
    parameter-scale artifacts, and matching seconds across them made every
    AKAI-sourced release 1.6-4x too fast depending on the sustain.

    The rate laws on both sides ARE hardware. So carry the rate: it is the
    quantity that is measured on both machines rather than the one that is
    invented on both.
    """
    if db_per_s <= 0.0:
        return 0
    b = ENV_RATE_BYTE_REF - ENV_RATE_HALVING_BYTES * math.log2(
        db_per_s / ENV_RATE_DB_PER_S_REF)
    return max(0, min(127, round(b)))


def env_span_seconds_to_rate(span_db: float, seconds: float) -> int:
    """Rate byte for travelling `span_db` in `seconds`.

    THE SPAN IS NOT OPTIONAL and that is the whole point of this function.
    `env_seconds_to_rate()` below takes a time alone, which is only correct at
    the span its calibration happened to use -- `AMP_DECAY_CAL.E4B` set
    sustain=0 deliberately so the decay was audible, i.e. a full ~55 dB fall to
    silence. Every decay to a non-zero sustain was therefore too fast, by 1.5x
    at sustain byte 80 and 15x at byte 122, and the error is worst exactly where
    real presets live.
    """
    if seconds <= 0.0 or span_db <= 0.0:
        return 0
    needed = span_db / seconds
    b = ENV_RATE_BYTE_REF - ENV_RATE_HALVING_BYTES * math.log2(
        needed / ENV_RATE_DB_PER_S_REF)
    return max(0, min(127, round(b)))


#: The fastest envelope decay the E4XT actually SOUNDS at.
#:
#: MEASURED by eosed 2026-08-24, isolated voice, decay level 0, rate swept:
#:
#:     rate 0    SILENT           peak -73.7 dBFS   (noise floor -84.2)
#:     rate 1    SILENT           peak -74.2
#:     rate 2    burst  0.0 ms    peak -65.1
#:     rate 3    burst 13.4 ms    peak -50.8
#:     rate 5    burst 16.6 ms    peak -41.9
#:     rate 8    burst 17.0 ms    peak -37.0
#:
#: **Rate 0 is not a very short decay. It is the envelope reaching zero before
#: any audio leaves the voice.** Note the peak climbs with the rate as well as
#: the duration — a slower decay lets more of the attack transient out before
#: the envelope closes — so rate 0 loses the burst's amplitude, not just its
#: length.
#:
#: That matters because a source can legitimately ask for a decay faster than
#: this machine can render. Clamping to the fastest available rate is right in
#: principle and wrong here, because the fastest available rate is silence:
#: the AKAI mute-group re-model asks for a 10 ms cut and, clamped to 0,
#: rendered the layer INAUDIBLE rather than brief (§AKAIMUTEGRP). The nearest
#: expressible burst is a better approximation to 10 ms than nothing is.
E4B_MIN_AUDIBLE_DECAY_RATE = 3


def env_rate_to_span_seconds(span_db: float, rate_byte: int) -> float:
    """Seconds a rate byte takes to travel `span_db`. Inverse of
    `env_span_seconds_to_rate`.

    **The reader had no such inverse until 2026-08-24** (§E4BENVSPAN). The
    writer has been span-aware since the calibration that produced
    `env_span_seconds_to_rate`, and its docstring above says exactly why: a
    time alone is only correct at the span the calibration happened to use.
    The parser meanwhile decoded every stage with `env_rate_to_seconds`, which
    is that time-alone law — so writer and parser were not inverses, and a
    round trip through our own code turned 5.50 s and 3.86 s per voice into
    3.8518 s on every voice.

    The error has the same shape and size as the one the writer was fixed for:
    1.5x at sustain byte 80 and 15x at byte 122, worst exactly where real
    presets live. It reached every E4B-sourced conversion, not one path.

    A rate byte of 0 is the deliberate "instant" encoding rather than a point
    on the curve, and stays 0 seconds.
    """
    if rate_byte <= 0 or span_db <= 0.0:
        return 0.0
    return span_db / env_rate_byte_to_db_per_s(rate_byte)


#: Peak-to-silence distance: the level law's own value at byte 0, so both
#: sides use one notion of "silence" rather than two. Same definition the
#: writer uses for the release complement.
ENV_FULL_SPAN_DB = env_level_byte_to_db(0)


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


def env_sustain_from_byte(byte: int) -> float:
    """Amp-envelope sustain byte → the LINEAR amplitude fraction it plays at.

    The exact inverse of :func:`env_sustain_to_byte`, and it has to exist:
    that function pre-compensates for the E4XT's dB-law sustain (§E4BLEVEL,
    hardware-measured), so reading the byte back with the LINEAR
    `env_level_to_byte` inverse is not an inverse at all. It over-reads badly
    -- a bank written at 12.5% amplitude read back as 79.5%.

    That mattered beyond round-tripping: the byte means the same thing in a
    third-party bank, so every E4B read reported sustain far too high, and
    every E4B->KRZ/EIII/TAL conversion carried it.

    The filter envelope is NOT dB-law -- the writer uses the linear
    `env_level_to_byte` for it -- so only the amp envelope inverts through
    here.
    """
    byte = max(0, min(127, int(byte)))
    if byte <= 0:
        return 0.0
    if byte >= env_level_to_byte(100.0):
        return 1.0
    # env_byte_to_level returns a FRACTION (0..1) while env_sustain_to_byte's
    # `pct` is a percentage (0..100) -- the two helpers do not share units, and
    # forgetting that is what made the first version of this return 0.0.
    pct = env_byte_to_level(byte) * 100.0
    db = ENV_LEVEL_DB_INTERCEPT + ENV_LEVEL_DB_SLOPE * pct
    return max(0.0, min(1.0, 10 ** (db / 20.0)))


# ── Signed mod-cord amount codec (±1.0 <-> signed byte stored unsigned) ─────
# CR-13/CR-18: was inlined ~5× across the E4B writer/parser.
#: **CORD AMOUNT 1 DELIVERS ABOUT 40% OF A LINEAR UNIT** — measured on the
#: E4XT 2026-08-24, LFO->Pitch, rate pinned:
#:
#:     amount   rms cents (floor removed)   per unit   vs linear
#:         -1                 3.12            3.12       0.40
#:         -2                15.96            7.98       1.02
#:         -3                22.25            7.42       0.95
#:         -4                28.41            7.10       0.91
#:         -6                46.89            7.81       1.00
#:
#: Linear at ~7.6 cents per unit from amount 2 upward; the FIRST step is not.
#: The jump from 1 to 2 is five times where it should be two.
#:
#: **FOURTH INSTANCE OF ONE SHAPE IN A DAY.** The envelope decay (rates 0 and 1
#: both silent, 3 the first usable rung), the cutoff table's low bytes, the
#: LFO-depth law's unphysical +9 cent intercept, and this. **A law fitted over a
#: field's middle should not be trusted at its first step**, and on this machine
#: the first step has been wrong every time anyone has looked.
#:
#: Consequence: any conversion computing an amount of 1 delivers 40% of what it
#: intended, and there is no byte between 1 and 2 to correct it with. Not
#: compensated here — a fudge factor on one byte would be a fit to a single
#: point on one cord — but recorded so it is not rediscovered.
#: **AND THE FIRST STEP IS ASYMMETRIC IN SIGN.** The 0.40 above was measured on
#: the NEGATIVE side only. Sweeping the same slot on the same voices, one sign
#: at a time (eosed, 2026-08-24):
#:
#:     amount  +1   8.48 rms cents      amount  +2   20.84
#:     amount  -1   3.78                amount  -2   16.17
#:     amount  +1   8.48  (repeat, reproducible)
#:
#: **+1 delivers 2.24x what -1 does**, converging to 1.29x at |2| and closing
#: as the magnitude grows. So "amount 1 gives 40% of a linear unit" is true
#: going down and roughly true going up — a positive 1 is close to linear.
#:
#: Consequence for the writer's deliberate triangle-phase negation: at these
#: depths **the negation costs more than half the modulation**. If the phase
#: inversion is worth having, the magnitude must be re-derived on the negative
#: side rather than carried across — and at |1| no negative value reaches a
#: target of 7.35 rms, since -1 gives 3.78 and -2 gives 16.17.
#:
#: Cause not established. Two's-complement rounding in the encoding is the
#: obvious guess and is NOT supported by this codec: `cord_amount_to_byte` is
#: symmetric about zero here, +0.00787 -> +1 and -0.00787 -> -1. So the
#: asymmetry is in the machine rather than in our arithmetic.
CORD_AMOUNT_FIRST_STEP_FRACTION = 0.40
CORD_AMOUNT_POS_OVER_NEG_AT_ONE = 2.24


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
#
# **VALIDATED DOWN TO 1.57 % ON 2026-08-24 and left unchanged** (§LFODEPTHRANGE).
# The 25 % floor of that calibration mattered, because real vibratos live far
# below it: this program's is 4.72 %, a fifth of the way under the fitted
# window, and §LAWRANGE had just found two other laws wrong in exactly that
# region. eosed swept 1.57–25.2 % on both a triangle and a square LFO. The
# response is linear all the way down and the two waveforms agree to 1 %, so
# neither curvature nor waveform-dependence exists. An independent refit of
# their raw data gives a mean ratio of 1.005 against this constant across eight
# triangle points — scatter, not bias.
#
# The one real caveat is the INTERCEPT. The original fit is
# `cents = 15.752*pct + 9.00`, and 9 cents at zero amount cannot be physical —
# zero cord must give zero pitch. It is invisible above ~3 % and is the whole
# disagreement below it: at 1.57 % it predicts 33.8 c where 30.1 was measured,
# an 11 % overshoot. Forcing the new data through the origin gives 16.82*pct
# (full scale 1682), but with ~10 % point-to-point scatter that is not
# demonstrably better than what is here, so nothing is changed on it.
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


#: K2000 DSP depth byte -> cents, for a frequency-unit function slot.
#:
#: COMPLETE AND MEASURED, no interpolation. k2kremote read program 250 back at
#: every consecutive byte across the whole range, single-clicking one step at a
#: time (2026-08-21). That confirmed every point the earlier partial fit had
#: (32->450, 29->300, 22->80, 12->24, 2->4, and the 100 ct/unit middle) and
#: filled in the rest, so the interpolation this table replaces is gone.
#:
#: The byte is a plain 0..127 index; "cents" is the panel's own NONLINEAR
#: display of that index -- compressed near zero, exactly 100 ct/unit through
#: the middle, coarser again in the last three steps. An earlier reading that
#: called the compressed stretch an "anomaly" rested on two points and was
#: withdrawn once the range was walked; there is no anomaly, only a curve.
#:
#: The unit is per FUNCTION TYPE -- cents on a frequency slot, semitones on a
#: pitch one, percent on a width one -- so only call this for a frequency slot.
KRZ_DEPTH_CENTS = (
    [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 27, 30, 35, 40, 45, 50,
     55, 60, 70, 80, 90, 100, 120, 150, 200, 250, 300, 350, 400, 450, 500]
    + [(b - 28) * 100 for b in range(34, 125)]   # exact closed form, 34..124
    + [10000, 10400, 10800]                      # 125..127; the formula breaks
)

#: The ceiling, 10800 ct = exactly 9.000 octaves. Named because it is a
#: property of the BYTE, not of any destination -- see KRZ_FENV_FULL_CENTS for
#: why the two must not be confused.
KRZ_DEPTH_MAX_CENTS = 10800.0

#: Cents that a full (1.0) filter-envelope cord amount is worth on the K2000,
#: so a converted program sweeps as far as the E4XT would: 5.14 octaves, from
#: E4B_FENV_OCT_PER_UNIT at envelope level 100%. Both machines multiply level
#: by depth, so the level cancels -- the same reasoning behind
#: AKAI_ENV2_DEPTH_MAX, and deliberately the same source constant, so all three
#: writers move together if that measurement is ever revised.
#:
#: NOT the byte's ceiling. Reader and writer both used KRZ_DEPTH_MAX_CENTS for
#: this until 2026-08-22, which normalised the model's amount on how far the
#: FIELD reaches rather than on what the amount MEANS -- 9.000 octaves against
#: 5.14, and, because the display curve is compressed near zero, ~23x too
#: LITTLE at small amounts rather than uniformly too much.
#:
#: See TODO "FILTER_ENV_FULL_CENTS disagrees with E4B_FENV_OCT_PER_UNIT": the
#: model carries a second, older value for this same quantity (3.65 oct) on the
#: cents->amount input path, and the two need reconciling.
KRZ_FENV_FULL_CENTS = E4B_FENV_OCT_PER_UNIT * 100.0 * 100.0 * 1200.0


def krz_depth_byte_to_cents(b: int) -> float:
    """K2000 DSP depth byte -> cents. Negatives mirror on MAGNITUDE (confirmed
    against two signed values read off the machine)."""
    if b < 0:
        return -krz_depth_byte_to_cents(-b)
    return float(KRZ_DEPTH_CENTS[min(b, 127)])


def krz_cents_to_depth_byte(cents: float) -> int:
    """Cents -> the K2000 depth byte that lands nearest. Exact inverse of
    krz_depth_byte_to_cents on every value the table holds."""
    if cents < 0:
        return -krz_cents_to_depth_byte(-cents)
    return min(range(len(KRZ_DEPTH_CENTS)),
               key=lambda b: abs(KRZ_DEPTH_CENTS[b] - cents))


#: K2000 LFO1->Pitch depth byte -> cents. Measured the same way as
#: KRZ_DEPTH_CENTS: k2kremote walked every consecutive byte on program 250,
#: single-clicking one step at a time, ceiling confirmed by four identical
#: readings at byte 123 with further clicks doing nothing (2026-08-22).
#:
#: A DIFFERENT CURVE from the filter depth's, despite serving the same role.
#: This one tracks cents 1:1 up to byte 20, then steps 2/5/10/20/50/100 ct
#: before opening out at the top. Assuming one K2000 depth field's law carries
#: over to another would have been wrong.
KRZ_LFO_PITCH_CENTS = (
    list(range(0, 21))                                            # 0..20, 1:1
    + [22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48]    # 21..34, +2
    + [50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]               # 35..45, +5
    + [110, 120, 130, 140, 150, 160, 170, 180, 190, 200]          # 46..55, +10
    + [220, 240, 260, 280, 300, 320, 340, 360, 380, 400]          # 56..65, +20
    + [450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950]     # 66..76, +50
    + [1000, 1100]                                                # 77..78
    + [(b - 67) * 100 for b in range(79, 118)]                    # 79..117, +100
    + [5300, 5500, 6000, 6500, 6700, 7200]                        # 118..123
)

#: The K2000's own vibrato ceiling, 7200 ct = 6 octaves (byte 123). Far beyond
#: anything an EOS cord amount can ask for -- LFO_PITCH_FULL_CENTS is 1593 --
#: so this is headroom we can read but never write. Named for the same reason
#: as KRZ_DEPTH_MAX_CENTS: so it cannot be mistaken for a full scale.
KRZ_LFO_PITCH_MAX_CENTS = 7200.0


def krz_lfo_pitch_byte_to_cents(b: int) -> float:
    """K2000 CAL[22] LFO1->Pitch depth byte -> cents."""
    return float(KRZ_LFO_PITCH_CENTS[max(0, min(b, 123))])


def krz_cents_to_lfo_pitch_byte(cents: float) -> int:
    """Cents -> the K2000 LFO1->Pitch byte that lands nearest."""
    return min(range(len(KRZ_LFO_PITCH_CENTS)),
               key=lambda b: abs(KRZ_LFO_PITCH_CENTS[b] - abs(cents)))


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

    #: The release's slew rate in dB/s, when the SOURCE machine measured one.
    #:
    #: `None` means "seconds are all I have" -- an MPC or an XPM really does
    #: specify a duration, and nothing about those paths changes.
    #:
    #: Set by readers whose machine is a RATE machine, consumed by writers
    #: whose machine is one. It exists because `release` alone cannot survive
    #: the trip (§AKAIRELSPAN): a release ends at "silence", the two samplers
    #: disagree about where that is by 60.07 dB against 97.82, and NEITHER
    #: number was ever measured. Carrying the rate carries the quantity both
    #: machines were metered for instead of the one both of them invented.
    #:
    #: Deliberately NOT applied to the filter envelope, whose release ends at a
    #: cutoff LEVEL rather than at silence -- a defined endpoint on both sides,
    #: so the span arithmetic is correct there and this would be a wrong fix
    #: to a problem it does not have.
    release_rate_db_per_s: float | None = None


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
    # VELOCITY -> FILTER IS A RANGE, NOT A DEPTH.
    #
    # `velocity_to_filter` is the depth reached at FULL velocity. The floor the
    # modulation starts from is `velocity_to_filter_min`, and the two together
    # are what a source actually specifies:
    #
    #   K2000 Src2:  (MinDpt, MaxDpt)      e.g. (0, +10800 ct) -> (0.0, +1.0)
    #   K2000 Src1:  (0, Depth)            a single depth is the same shape
    #
    # CARRYING ONLY THE DEPTH LOSES THE POLARITY. `(0, +10800)` only ever OPENS
    # the filter; `(-5400, +5400)` closes it as much as it opens. Both collapse
    # to the same scalar, and they are different patches. A converter that
    # re-centres a unipolar sweep on a bipolar destination drives the corner
    # BELOW a floor the source never crosses -- which on a cymbal is silence,
    # found on hardware 2026-08-17 (see RESOLUTION_NOTES.md AKAIVELFILT).
    #
    # Both are normalised on 10800 cents (+-9 octaves), the K2000's own range.
    # Default (0.0, 0.0) is "no modulation" and is what every non-KRZ parser
    # leaves them at, so nothing changes for those paths.
    velocity_to_filter: float = 0.0      # depth at full velocity (cord 04)
    velocity_to_filter_min: float = 0.0  # depth at zero velocity; 0 = unipolar
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


def walk_files_deterministic(root):
    """Yield every file under `root` in a STABLE, filesystem-independent order.

    `Path.rglob()` and `Path.iterdir()` return entries in directory order,
    which on ext4 is a hash of the filename: stable while a directory is
    untouched, different after a file is added or removed, and different again
    on another machine or filesystem. That is fine for a scan that consumes
    everything, and a defect for one that stops early or keeps the first match.

    Both sample-index scans here do exactly that -- `setdefault()` keeps the
    FIRST file seen for a given basename, and an 80 000-entry cap breaks out of
    the walk -- so which file a sample reference resolved to, and above the cap
    which files were indexed at all, rode on directory iteration order. The
    same library could convert differently after an unrelated file was added
    beside it.

    Found 2026-08-12 from VinSamLib hitting the same defect class in corpus
    counting: an unsorted glob truncated at 150 entries made their denominator
    ride on iteration order, giving 448, 454 and 459 banks across three runs of
    one evening. Ours is worse in kind, because it moves conversion OUTPUT
    rather than a reported statistic.

    Sorting `rglob()` would fix the order and defeat the cap -- it materialises
    the whole tree before the bound applies, which is what the cap exists to
    prevent. This walks lazily and sorts only one directory level at a time, so
    the scan stays bounded AND repeatable.
    """
    import os
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames.sort()          # in place: os.walk reads this back for descent
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)
