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
#: NOMINAL, not a machine constant: 3.65 oct is what MOD_DEPTH_CAL measured
#: from ONE base cutoff (~byte 193), and the same cord is worth 5.14 oct from
#: byte 104 and 7.05 oct from byte 0. Kept as the input-path span for sources
#: that only give a fraction, and for the LFO->Filter depths, which are still
#: fractions. Not used for the filter envelope any more.
FILTER_ENV_FULL_CENTS = 4383.0       # = 3.65 octaves * 1200


def cents_to_filter_env_amount(cents: float) -> float:
    """Map a Filter-Freq mod depth in cents to an EOS cord amount (-1..+1).

    **The LFO->Filter cords only, since 2026-08-25.** The filter ENVELOPE used
    to share this and no longer does: `filter_env_cents` carries cents and each
    writer converts from the voice's own corner (`e4xt_cents_to_cord_amount`),
    because what a full cord is worth in octaves depends on the base and is not
    a constant -- see the note above `E4XT_VEL_SOURCE_UNITS`. The LFO depths
    are still fractions and still use this; they have the same latent fault.
    """
    return max(-1.0, min(1.0, cents / FILTER_ENV_FULL_CENTS))


def nominal_filter_env_cents(fraction: float) -> float:
    """A source's 0..1 filter-envelope depth -> cents, on the nominal span.

    For the sources that state a FRACTION and never a frequency (EXS24, EIII's
    0..127 byte, the MPC knob). Named so the assumption is visible: it puts the
    knob on `FILTER_ENV_FULL_CENTS`, which is one measurement from one base and
    not a property of any machine. A source that states cents must not come
    through here.
    """
    return max(-1.0, min(1.0, fraction)) * FILTER_ENV_FULL_CENTS


# Velocity→Filter: the velocity source spans 0→~2.08 units over MIDI velocity
# 0→127, so a 100% cord moves the cutoff ~7.6 octaves (= 9120 cents) across the
# full velocity range (measured r=0.9999; consistent with Key 0.713 oct/oct ×
# 10.6 oct keyboard).  Note: the writer routes this through the **Vel+** source.
#: NOMINAL, same caveat as FILTER_ENV_FULL_CENTS -- it is that number times
#: the Vel+ source's 2.08-unit span (`E4XT_VEL_SOURCE_UNITS`), so it inherits
#: the base it was measured from.
VEL_FILTER_FULL_CENTS = 9120.0       # = 7.6 octaves * 1200


def nominal_velocity_filter_cents(fraction: float) -> float:
    """A source's 0..1 velocity->filter depth -> cents, on the nominal span.

    Companion to `nominal_filter_env_cents`, same caveat: the span is one
    measurement from one base. Sources that state the depth in cents (SFZ,
    SF2, GIG, KRZ) assign it directly and never call this.
    """
    return max(-1.0, min(1.0, fraction)) * VEL_FILTER_FULL_CENTS


# Key→Filter: a 100% cord tracks the cutoff at 0.713 octave per octave of key
# (measured r=0.9994 — NOT the assumed 1:1), so a desired ratio needs
# amount = ratio / 0.713 (a true 1:1 request saturates at the 0.713 hardware max).
KEY_FILTER_OCT_PER_OCT = 0.713


def filter_amount_to_key_track(amount: float) -> float:
    """EOS cord amount -> octaves of cutoff per octave of key. The inverse."""
    return amount * KEY_FILTER_OCT_PER_OCT


def key_track_to_filter_amount(oct_per_oct: float) -> float:
    """Map a desired Key→Filter tracking ratio (octaves of cutoff per octave of
    key) to an EOS cord amount (-1..+1)."""
    return max(-1.0, min(1.0, oct_per_oct / KEY_FILTER_OCT_PER_OCT))


#: §AKAIKEYFOLLOWHW: `K_FREQ / 12` (the octaves-of-cutoff-per-octave-of-key a
#: raw K_FREQ step is nominally worth) was never right on the NEGATIVE side --
#: the only side ever shipped, and the one the first hardware test failed on.
#: Measured 2026-08-27 on a clean, non-resonant, non-masked subject (Q forced
#: to minimum, wide-open reference program to divide out): K_FREQ -4/-8/-12/-18
#: gave -0.186/-0.385/-0.585/-0.977 oct/oct against -0.333/-0.667/-1.000/-1.500
#: predicted -- a consistent ~0.59-0.65x undershoot across a 4.5x range of
#: magnitudes (least-squares through the origin: 0.622). The POSITIVE side
#: overshoots instead (~1.4-1.9x, non-constant, likely real nonlinearity or the
#: AKAI's own non-log-linear FILFRQ curve) and is NOT corrected here -- there is
#: not yet a clean single-factor law for it, and guessing one would repeat the
#: exact mistake this section fixes. Same measurement also found the AKAI's own
#: pivot clusters around note ~70, not the assumed 64 -- recorded in
#: TODO.md/RESOLUTION_NOTES.md, not yet acted on (unclear where in the model a
#: pivot-not-64 correction belongs without more thought).
#:
#: NOT A CONFIRMED LAW (2026-08-28, s3ked). This same field, measured on the
#: same physical S3000XL, gave K_FREQ/12 unscaled to 96-103% -- a real,
#: unresolved disagreement between two instruments (see TODO.md). Four
#: candidate mechanisms for the gap have been named and refuted (masking,
#: band-limited compression, a pivot error, a fixed-frequency anchor in the
#: corner estimator), so 0.622 is not simply a mistake either. Treat this as
#: an unexplained empirical correction from ONE bench sweep, not a physical
#: constant -- in particular, it has NOT been ruled out as note-dependent
#: (correct near the sweep's own test notes, 42-78, and increasingly wrong
#: toward the ends of the keyboard, which by construction sounds fine
#: everywhere it was checked and is the hardest kind of error to catch by ear).
AKAI_KEYFOLLOW_NEG_SCALE = 0.622


# E4B VCF cutoff byte (vpar[60]) is exponential: ~57 Hz at 0, 20 kHz at full.
# Shared by every parser that maps a source cutoff frequency onto the E4B scale
# (CR-12 — previously duplicated in exs24 and re-implemented wrong in sfz).
E4B_CUTOFF_MIN_HZ = 57.0
E4B_CUTOFF_MAX_HZ = 20000.0
#: Octaves spanned by the shared 0..1 cutoff position -- 8.455.  Wherever a
#: modulation depth is expressed as a FRACTION of that scale (the K2000
#: writer's velocity->filter fold), this is what the fraction is a fraction
#: OF, and multiplying by it converts the depth into octaves.  That lets the
#: sum happen in Hz, which matters for a source darker than 57 Hz: folding
#: via `hz_to_e4b_cutoff` would clamp it to the E4B floor first.
E4B_CUTOFF_RANGE_OCT = math.log2(E4B_CUTOFF_MAX_HZ / E4B_CUTOFF_MIN_HZ)


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
    # ONE QUADRATIC ACROSS THE WHOLE RANGE. This used to special-case db >= 0
    # as `round(db)`, a 1:1 positive branch that was ASSUMED rather than fitted
    # -- the 2026-07-31 measurement covered 0 to -22.9 dB and nothing above.
    # eosed measured the positive half on 2026-09-04 (§VELHW1): moving a voice
    # from byte -4 to +7 delivered 8.53 dB, where the 1:1 branch predicts 10.07
    # and this quadratic extended through zero predicts 8.45. The branch was
    # 1.54 dB optimistic there and grows worse -- 2.3 dB at +10, 3.0 at +13.
    disc = _E4XT_VOL_C1 ** 2 + 4.0 * _E4XT_VOL_C2 * db
    if disc < 0.0:
        return -128
    root = (-_E4XT_VOL_C1 + math.sqrt(disc)) / (2.0 * _E4XT_VOL_C2)
    return int(max(-128, min(127, round(root))))


def e4xt_byte_to_volume_db(byte: int) -> float:
    """Inverse of `e4xt_volume_byte`: the dB a written byte actually delivers.
    Same round-trip requirement as the cutoff above."""
    b = float(byte)
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


#: An AKAI envelope's full level. The ENV2 octave law is
#: `octaves = AKAI_ENV2_OCT_PER_UNIT * LEVEL * depth`, and LEVEL is wherever
#: the envelope currently is -- 99 at the attack peak, SUSTN2 while held.
#: Confirmed by s3ked's own cross-check, which measured SUSTN2 99 / depth 15
#: at 3.862 octaves against 3.874 predicted from a SUSTN2 25 fit.
AKAI_ENV2_FULL_LEVEL = 99


def akai_env2_target_hz(base_hz: float, sustn2: int, depth: int) -> float:
    """Where an AKAI ENV2 takes the corner AT LEVEL `sustn2`, ceiling included.

    Pass `AKAI_ENV2_FULL_LEVEL` for the attack peak. Passing the envelope's own
    sustain byte gives the corner it settles at, which is a different and much
    lower number on a percussive envelope -- 189 Hz against 7858 Hz on the
    program that exposed this (§AKAIENV2PEAK).
    """
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
                       / (AKAI_ENV2_OCT_PER_UNIT * 99.0))     #: ~19.88
#: The comment above said ~18.3 until 2026-08-25 and the docs quoted that
#: figure in four places. It is DERIVED, so it moved when one of its inputs
#: was recalibrated and nothing pointed at the stale copies. Caught by
#: tests/test_docs_constants_agree.py on that test's first run.


#: V_LOUD (program byte 0x1a, "velocity > loudness") -> the full-scale
#: amplitude swing in dB from velocity 1 to 127.
#:
#: CONFIRMED INDEPENDENTLY 2026-09-01 on a different program by a different
#: measurement: slope 0.1886 measured against 0.1892 predicted at V_LOUD +20.
#:
#: And `VLOUD1` was tested against this and is a STATIC offset, not a second
#: velocity term -- a hypothesis raised and then refuted by its own author.
#: Sweeping VLOUD1 -50..+10 at fixed V_LOUD moves the intercept at 0.59955
#: dB/unit (r2 0.999801, against this file's own 0.60576) while the slope
#: stays constant to +-0.0013 dB/velocity across a 41 dB range of level. The
#: "velocity" in VLOUD1's name denotes the ZONE, not a dependence.
#:
#: A TRAP FROM THAT RUN, worth carrying to any repeat: the VLOUD1 +20 row had
#: to be excluded because v127 sat flat against the gain ceiling, which fitted
#: as a slope of 0.137 and would have looked exactly like the velocity-term
#: evidence being looked for. **A ceiling-clipped point manufactures a fake
#: slope change.** Gate on HEADROOM, not only on the noise floor.
#:
#: CONFIRMED INDEPENDENTLY 2026-09-01 on a different program by a different
#: measurement: slope 0.1886 measured against 0.1892 predicted at V_LOUD +20.
#:
#: And `VLOUD1` was tested against this and is a STATIC offset, not a second
#: velocity term -- a hypothesis raised and then refuted by its own author.
#: Sweeping VLOUD1 -50..+10 at fixed V_LOUD moves the intercept at 0.59955
#: dB/unit (r2 0.999801, against this file's own 0.60576) while the SLOPE
#: stays constant to +-0.0013 dB/velocity across a 41 dB range of level. The
#: "velocity" in VLOUD1's name denotes the ZONE, not a dependence.
#:
#: A TRAP FROM THAT RUN, worth carrying to any repeat: the VLOUD1 +20 row had
#: to be excluded because v127 sat flat against the gain ceiling, which fitted
#: as a slope of 0.137 and would have looked exactly like the velocity-term
#: evidence being looked for. **A ceiling-clipped point manufactures a fake
#: slope change.** Gate on HEADROOM, not only on the noise floor.
#:
#: MEASURED (s3ked §171, 2026-09-01) on a white-noise program with VLOUD1,
#: VFREQ1 and V_ATT1 all zeroed -- the first sums with the field under test,
#: the second lets velocity change timbre so RMS moves for a reason that is
#: not loudness, and the third changes the contour under the analysis window.
#:
#:     dB(vel) = L64 + 0.009460 * V_LOUD * (vel - 64)
#:     swing_dB = 1.19557 * V_LOUD          r2 = 0.9999816
#:
#: THE RESPONSE ROTATES ABOUT VELOCITY 64, it does not scale from silence:
#: the level at v64 measured -37.9 dBFS at V_LOUD 0, 25 and 50 alike. Same
#: pivot `K_FREQ` uses for key-follow (§167). V_LOUD 0 is genuinely neutral
#: (slope 0.00001 dB/unit, r2 0.029 -- i.e. no velocity dependence at all),
#: so it is a real zero rather than a smallest-available value.
#:
#: Per end about the pivot that is 0.598 dB/unit, against VLOUD1's 0.60576
#: and PRLOUD's measured 0.603 -- all three AKAI loudness fields step about
#: 0.6 dB per unit, which is a useful consistency check on any of them.
#:
#: **A SWEEP ACROSS THE WHOLE RANGE LOOKS COMPRESSIVE AND IS NOT.** A straight
#: fit over everything gives r2 0.987 with +-5.5 dB residuals in a clear W --
#: the loud end running into a CEILING, not a curve in the law. Tested rather
#: than asserted: lowering PRLOUD buys headroom and should move the clamp while
#: leaving the slope alone -- at PRLOUD 80 (12.3 dB headroom) V_LOUD 20 is clean
#: and 30 clamps; at PRLOUD 60 (24.3 dB) V_LOUD 40 is within 0.4 dB and only 50
#: clamps. **So the law has no ends to it** -- a program with more headroom
#: simply uses more of the range, and a converter should carry the source's
#: number rather than any curve fitted from a clamped sweep.
#:
#: **THE CEILING IS A GAIN CEILING, NOT AN ABSOLUTE OUTPUT CEILING** (s3ked,
#: 2026-09-04, superseding their own earlier reading and this comment's). Both
#: were consistent with the PRLOUD test above; what separates them is whether
#: two different SAMPLES freeze at the same level. They do not -- they froze
#: **5.47 dB apart**, with the crest factor unmoved, so no peak is being
#: flattened: the gain coefficient simply stops rising and the output rests at
#: `sample amplitude x max gain`. The -25.62 dBFS figure this comment used to
#: quote as "the ceiling" was one sample's freeze point, not the machine's.
#:
#: The consequence is the one that matters here: **the realised swing is
#: SAMPLE-DEPENDENT**, so "how much headroom does the AKAI have" has no single
#: answer per machine. Nothing below changes -- every constant and every call
#: site uses the NOMINAL law and none of them ever read the ceiling -- but a
#: future target must match the nominal law and not a realised range, because
#: the realised range is a property of the material rather than the instrument.
#:
#: NOT CLAIMED: the ceiling was measured on one program through one signal
#: path and may be this rig's rather than the machine's; whether it belongs to
#: the voice or to something downstream was not separated. And the v64 pivot
#: is measured at note 60 on one keygroup of noise -- that it holds across
#: notes is assumed, not shown.
AKAI_VLOUD_SWING_DB_PER_UNIT = 1.19557


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
#: note or velocity is untested.
#:
#: **RE-MEASURED 2026-08-25 (s3ked, §155 amendment) AND IT IS NOT A GATE.**
#: The 10 ms above was the TRACE WINDOW, not the cut: a 10 ms grid can only
#: say the layer was present in one window and gone by the next, which bounds
#: the cut at <=10 ms and measures nothing. At 2 ms windows on a 0.5 ms hop,
#: the cut layer against its own uncut self:
#:
#:     t+ms      0     1     2     3     4     5     6     8    10    12
#:     dB      0.0  +0.7  +0.1  +1.0  -0.1  -1.6  -4.0 -13.1 -13.7 -20.7
#:
#: **Full level for the first 4-5 ms, then a ramp to -20 dB by 12 ms.** Below
#: about -20 dB the technique is floor-limited (the partner has to stay
#: audible enough to choke), so the tail beyond that is not quoted.
#:
#: **WHAT THIS CONSTANT CAN AND CANNOT DO.** `Envelope` is four parameters and
#: cannot express "hold, then fall": with attack 0 and sustain 0 the level
#: falls from t=0 at a constant rate, so the 5 ms at unity is unrepresentable.
#: The value below reproduces the measured RAMP -- 97 dB of span at the rate
#: that reaches -20 dB at 12 ms -- and accepts the hold as a known residual of
#: about 3.6 dB over the first 30 ms.
#:
#: The old 0.010 reached -20 dB at 2.1 ms and lost **11.2 dB** of energy over
#: that window against the measured cut. That is most of an attack transient,
#: and it is what Jan heard as "the click is pretty much gone" on a converted
#: electric piano whose loud layer is the choked one (the choke costs 13.7 dB
#: of early level, so the layer being cut carries most of the attack).
#:
#: The residual is a MODEL limit, not a calibration gap: see TODO "the mute
#: cut needs a hold stage". Do not fit this constant to close it -- matching
#: the energy instead would need 80 ms and would put the ramp 4.5 ms late.
AKAI_MUTE_CUT_SECONDS = 0.058

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

#: LFO2 (`PANRAT`) is a DIFFERENT law from LFO1 and using LFO1's here is a real
#: mistake that was made on 2026-09-06: `rate = 0.23708 * PANRAT Hz`, measured
#: over PANRAT 5..80 at r² 0.999843, **exactly twice LFO1's rate for the same
#: byte** (ratio 1.998) and forced through the origin — so no offset term.
#:
#: Consequence worth stating because the wrong law is plausible: LFO1 tops out at
#: 11.71 Hz where LFO2 reaches **23.47 Hz**, so a rate that looks marginal under
#: LFO1's law is mid-range under LFO2's. An 11.5 Hz source pan LFO is `PANRAT`
#: 49, not 97.
#: HARDWARE-MEASURED 2026-09-06 THROUGH THE PAN DESTINATION (s3ked, §AKAILFO2RATE).
#: Nine PANRAT points 10..99, ~1495 usable frames each at 0.07 Hz resolution,
#: three interleaved negative controls at 0.66-1.11 dB:
#:
#:     through origin   rate = 0.11913 * PANRAT
#:     with intercept   rate = 0.11921 * PANRAT - 0.0055 Hz    r2 0.999984
#:
#: The intercept is -0.0055 Hz, so the law passes through the origin and the old
#: value's factor of two was NOT a fitted artefact of a wrong intercept -- it was
#: simply wrong by two.
#:
#: REPLACES 0.23708, which came from §52's "LFO2 runs at exactly twice LFO1".
#: That was measured through the FILTER, where a bipolar sweep presents TWO
#: brightness excursions per cycle to a magnitude detector; measured through pan,
#: where balance is signed, the ratio is 1.990 against the old value and 1.004
#: against LFO1's own law. LFO2 does not run at twice LFO1 -- it runs at LFO1's
#: rate. Same magnitude-versus-sign confusion as the centroid reverse-indicator
#: trap in §AKAISUSTSAT, found the same evening.
#:
#: Consequence: every AKAI pan program built before this ran at HALF its intended
#: rate. Ceiling is 99 * 0.11913 = 11.79 Hz, so an 11.46 Hz source is still
#: representable (byte 96) but with much less headroom than assumed.
AKAI_LFO2_RATE_HZ_PER_UNIT = 0.11913
AKAI_LFO_DEPTH_CENTS_PP_PER_UNIT = 19.4932
AKAI_LFO_DELAY_NUM = 0.06905
AKAI_LFO_DELAY_POLE = 103.41


def akai_lfo_rate_hz(byte: int) -> float:
    """LFORAT -> Hz."""
    return max(0.0, AKAI_LFO_RATE_HZ_PER_UNIT * max(0, min(99, byte))
               + AKAI_LFO_RATE_HZ_OFFSET)


def akai_lfo2_rate_byte(hz: float) -> int:
    """Desired LFO2 rate in Hz -> the `PANRAT` byte. Inverts the measured law.

    Distinct from `akai_lfo_rate_byte`, which is LFO1's: LFO2 runs at twice the
    rate for the same byte and has no offset term. Reaches 23.47 Hz at byte 99.
    """
    if not hz or hz <= 0:
        return 0
    return max(0, min(99, int(round(hz / AKAI_LFO2_RATE_HZ_PER_UNIT))))


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
    # `poles` USED TO CANCEL ITSELF OUT. This scaled the target AND the table
    # by the same factor, so `(0.5, 2)` and `(0.5, 4)` returned the same byte
    # -- while `e4xt_byte_to_resonance` applied the scale ONE-SIDED and was
    # therefore not the inverse. An E4B repacked twice climbed: byte 40 ->
    # 0.38 -> 67 -> 0.998 -> 112, pinned at the maximum. Measured over the
    # corpus 2026-08-24: resonance changed on **60.5% of round-tripped zones**,
    # always upward.
    #
    # The inverse was the correct half. The machine at `poles` delivers
    # `table_db(b) * scale`, so to deliver `amount * RESONANCE_FULL_DB` the
    # table must be asked for `amount * RESONANCE_FULL_DB / scale` -- divided,
    # against the UNSCALED table.
    scale = max(1, poles) / 2.0
    target = max(0.0, min(1.0, amount)) * RESONANCE_FULL_DB / scale
    tbl = list(_E4XT_Q_TABLE)
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


#: `LFO1WAVE` (program byte 97) -> RMS-to-one-sided-peak factor.
#:
#: RMS is waveform-independent (a second moment about the carrier equals the
#: mean square FM deviation for any periodic shape), which is why
#: `AKAI_LFO_RMS_CENTS_PER_PRODUCT` could be measured without knowing the
#: wave. Converting RMS to the one-sided peak this project's model field
#: wants DOES need the shape, and until 2026-08-31 nobody read this byte —
#: every AKAI-sourced LFO1 was silently treated as a triangle.
#:
#: s3ked's §46 (2026-08-12) measured all four values on hardware by the
#: direct argument: LFO1 drives pitch, so the pitch track over one LFO cycle
#: IS the waveform. Values 0/1/2 came back exactly as the AKAI spec names
#: them (triangle/sawtooth/square) and give an exact factor. Value 3 read as
#: real but unidentified by shape alone at the time — symmetric like a
#: triangle (slope asymmetry 1.04) but spending half as long near centre
#: (0.16 against triangle's 0.34) — until Jan named it from the S3000XL
#: manual itself (2026-08-31): **random**.
#:
#: `random`'s factor is UNMEASURED and left at the triangle's `sqrt(3)` as a
#: provisional stand-in, not a derivation — a first attempt at one (assuming
#: the AKAI's random generator is uniformly distributed, which would give
#: the same RMS/peak ratio as a triangle) was proposed 2026-08-31 and
#: WITHDRAWN THE SAME NIGHT: s3ked pointed out §46's own "time near centre"
#: statistic is self-calibrating (it predicts, and measures, ~0.33 for the
#: two known uniform/ramp shapes and 0.0 for square) and reads 0.16 for
#: value 3 — half the uniform prediction. So the generator is NOT uniform;
#: it is weighted toward the extremes, somewhere between uniform (RMS/peak
#: 0.577) and a sine's arcsine distribution (0.707). Since a HIGHER RMS/peak
#: ratio means a LOWER peak for the same measured RMS, `sqrt(3)` most likely
#: OVER-estimates the peak for a genuinely random source — the direction is
#: known, the number is not. Left unchanged rather than replaced with a
#: second guess; s3ked has offered a direct ten-minute measurement (set
#: `LFO1WAVE` 3, capture, take RMS and peak straight off the pitch trace)
#: when the random path actually matters to something in flight.
AKAI_LFO_WAVE_RMS_TO_PEAK = {
    0: math.sqrt(3.0),     # triangle -- what every reading used before this
    1: math.sqrt(3.0),     # sawtooth -- happens to share the triangle factor
    2: 1.0,                 # square -- 73% LOWER peak than the triangle guess
    3: math.sqrt(3.0),     # random -- UNMEASURED, likely too high (see above)
}


def akai_lfo_depth_to_pitch(byte: int, l_ptch: int = None,
                             waveform: int = None) -> float:
    """LFODEP (+ the keygroup's `L_PTCH` gate) -> one-sided `lfo1_to_pitch`.

    The field is PEAK-TO-PEAK cents and our model field is one-sided against
    `LFO_PITCH_FULL_CENTS`, so this halves as well as scaling. Getting that
    wrong would double every vibrato — the same seam as the K2000 LFO depth,
    where the half-swing convention had to be checked on both sides before a
    factor of two could be ruled out.

    **`l_ptch` GATES AND SCALES.** MEASURED 2026-08-24 against a floor
    established in the same run: LFODEP 99 with L_PTCH 0 produces no vibrato,
    L_PTCH 50 with LFODEP 0 produces none either, and both non-zero produces
    a strong one — so 0 means silence, applied via the early return below.

    The scaling itself is `akai_lfo_rms_cents`'s product law
    (AKAI_LFO_RMS_CENTS_PER_PRODUCT), s3ked's §160 hardware measurement —
    confirmed 2026-08-31 to 5 decimal places against the reference preset's own
    LFODEP=8/L_PTCH=7 (predicted 7.351 rms ct, measured 7.35). This
    docstring used to say scaling was an unproven guess and NOT applied;
    that was accurate before §160 and is stale now (§AKAILPTCH).

    `waveform` is `LFO1WAVE` (0/1/2/3) — see `AKAI_LFO_WAVE_RMS_TO_PEAK`.
    `None` (the default) uses the triangle factor, matching every reading
    made before the byte was read at all.
    """
    if l_ptch is None:
        l_ptch = AKAI_LFO_DEPTH_CAL_LPTCH      # the calibration's own routing
    if l_ptch == 0:
        return 0.0
    # Through the MEASURED product, not through §35 scaled by a guess. RMS is
    # the form that was measured; the waveform factor takes it to one-sided
    # peak, which is what `lfo1_to_pitch` means.
    factor = AKAI_LFO_WAVE_RMS_TO_PEAK.get(waveform, math.sqrt(3.0))
    one_sided = akai_lfo_rms_cents(byte, l_ptch) * factor
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


def akai_01_to_filq(amount: float) -> int:
    """The model's 0..1 resonance -> FILQ. Inverse of `akai_filq_to_01`.

    **The reader's half was wired 2026-08-23 and the writer's was not**, so
    every conversion INTO an AKAI dropped resonance entirely -- measured across
    the library discs on 2026-08-24: **FILQ changed on 44.8% of round-tripped
    zones**, almost always to 0. Real programs use it heavily, so this was not
    a corner case; it was most of them.

    Inverts through dB, matching the forward direction, because the field is
    linear in nothing audible: FILQ 7 of 15 is a fifth of the range, not a
    half. Clamped to the field, and to `AKAI_FILQ_MAX` rather than to
    `AKAI_FILQ_DAMPING_ZERO` -- damping reaches zero at 15.84, past the top of
    the field, which is why the machine stops just short of self-oscillation.
    """
    db = max(0.0, min(1.0, amount)) * RESONANCE_FULL_DB
    z = 10.0 ** (-db / 20.0)
    return int(round(max(0, min(AKAI_FILQ_MAX,
                                AKAI_FILQ_DAMPING_ZERO * (1.0 - z)))))


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


# ── Filter-destination cord depths, in cents, via the corner (2026-08-25) ────
#
# WHAT A FULL CORD IS WORTH IN OCTAVES IS NOT A CONSTANT, and two entries in
# this file spent three days disagreeing about its value (§FENVFULLSCALE:
# `FILTER_ENV_FULL_CENTS` 3.65 oct on the input path against
# `E4B_FENV_OCT_PER_UNIT` 5.14 oct on the output path, 41% apart, composing
# rather than cancelling).  The answer is neither: the cord moves the cutoff
# BYTE linearly (`E4XT_FENV_BYTE_PER_UNIT`, 2.506 bytes per unit of amount) and
# the byte->Hz curve is not a pure exponential, so the same cord is worth a
# different number of octaves from every base.  A full cord saturates the byte
# from essentially any base, which makes "octaves per full cord" just
# `log2(20 kHz / base)` -- and that reproduces both disputed figures:
#
#     3.65 oct  <->  base byte ~193  (1559 Hz)     MOD_DEPTH_CAL, 2026-06-12
#     5.14 oct  <->  base byte ~104  ( 549 Hz)     eosed §46
#
# Consistent with two correct measurements taken from two different bases and
# reported as a property of the cord.  Neither is a constant of the machine.
#
# **CITE §56 FOR THE DEPTH LAW, NOT §46** (eosed, 2026-08-25).  §46 is the
# earlier OCTAVE-based product law -- the one that produces the numbers above
# -- and it is superseded by §56, the BYTE-based law measured on 57 points
# over five base cutoffs.  The distinction is the whole point rather than a
# footnote: an octave-based conversion needs a different amount from every
# base and a byte-based one does not, so anyone building against §46 rebuilds
# the defect this file just removed.  §46 is kept upstream for its method and
# for the part of it that was withdrawn.
#
# So depths on this destination convert through the CORNER, never through a
# cents-per-cord number: the model says how far the corner should move in
# cents, and these turn that into the amount that moves it that far FROM THIS
# VOICE'S OWN BASE.  Same reasoning as `e4xt_cord_amount`, whose docstring
# already said so; these add the sign and the source span it did not carry.

#: The Vel+ source spans 0 -> ~2.08 cord units over MIDI velocity 0..127
#: (MOD_DEPTH_CAL, r=0.9999), so a velocity cord at a given amount moves the
#: corner 2.08x as far at full velocity as a unit source would.  Was buried in
#: a comment on `VEL_FILTER_FULL_CENTS`, which is the constant it invalidates.
E4XT_VEL_SOURCE_UNITS = 2.08


def e4xt_cutoff_byte_to_hz(byte: float) -> float:
    """vpar[60] -> the corner the E4XT actually renders, in Hz.

    The MEASURED table, not the nominal scale: unlike
    `e4xt_cutoff_byte_to_position` this does not clamp into the shared
    57 Hz-20 kHz window, because cord arithmetic has to work in the machine's
    own range (byte 0 is ~133 Hz, above the shared floor).
    """
    return _interp(max(0.0, min(1.0, byte / 255.0)), _E4XT_CUTOFF_TABLE)


def e4xt_cutoff_hz_to_byte(hz: float) -> float:
    """Hz -> vpar[60], unrounded. EXACT inverse of `e4xt_cutoff_byte_to_hz`.

    **By search, not by a second formula.** `e4xt_cutoff_position` looks like
    the inverse and is not: it interpolates the same table LINEARLY IN
    POSITION while `e4xt_cutoff_byte_to_hz` interpolates it LOG IN HZ, so
    between knots the two curves diverge -- measured, up to **1.47 bytes** at
    byte 64. That is the identical fault the AKAI writer hit on 2026-08-20
    ("two hand-derived inverses of one curve drifted apart... a search cannot
    drift"), and here it broke the cord round trip: a cord byte read as cents
    and written back landed a byte away on 12% of values.

    `e4xt_cutoff_position` is left alone -- it is the writer's hardware-
    calibrated path for `vpar[60]` and moving it would move every E4B cutoff.
    """
    lo, hi = 0.0, 255.0
    if hz <= e4xt_cutoff_byte_to_hz(lo):
        return lo
    if hz >= e4xt_cutoff_byte_to_hz(hi):
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if e4xt_cutoff_byte_to_hz(mid) < hz:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def e4xt_cents_to_cord_amount(base_byte: float, cents: float,
                              level_percent: float = 100.0,
                              source_units: float = 1.0) -> float:
    """Cents of corner movement -> signed cord amount (-100..+100).

    `base_byte` is the voice's own cutoff byte: the same depth in cents needs a
    different amount from a different base, which is the whole point.  Clamped
    to the field's range; a request the cord cannot reach is reported by
    `e4xt_cord_saturates`, not silently approximated.

    **UNROUNDED on purpose.** The cord is stored on a 0..127 byte grid, not a
    0..100 one, so rounding to an integer amount here and quantising again at
    the byte put two grids in series -- measured on the 58-bank E4B corpus, an
    integer return moved the depth on 3.9-4.1% of zones purely through that.
    The caller quantises once.
    """
    if level_percent <= 0.0 or source_units <= 0.0 or not cents:
        return 0.0
    target_hz = e4xt_cutoff_byte_to_hz(base_byte) * (2.0 ** (cents / 1200.0))
    delta = e4xt_cutoff_hz_to_byte(target_hz) - base_byte
    per_unit = (E4XT_FENV_BYTE_PER_UNIT * (level_percent / 100.0)
                * source_units)
    return max(-100.0, min(100.0, delta / per_unit))


def e4xt_cord_amount_to_cents(base_byte: float, amount: float,
                              level_percent: float = 100.0,
                              source_units: float = 1.0) -> float:
    """Signed cord amount -> the cents of corner movement it produces.

    Exact inverse of `e4xt_cents_to_cord_amount` up to the cord byte's own
    quantisation.  The reader needs this so an E4B round trip does not have to
    agree with any cents-per-cord constant -- only with itself.

    **THE CORNER IS CLAMPED, so this reports what the machine RENDERS.**  A
    full cord covers the entire cutoff byte range (`E4XT_FENV_BYTE_PER_UNIT`),
    so from a mid cutoff more than half the cord's numeric range drives the
    corner off one end -- and **36.5% of the nonzero filter depths in 60 real
    banks do exactly that**.  Reporting what those cords ASK for instead of
    what they reach gave readings up to 71 octaves, which is not a sound, and
    every other machine would then be told to sweep 71 octaves rather than the
    7.2 the E4XT actually manages.  The model describes the sound.

    The cost is that a saturated cord does not always come back as the same
    BYTE: several amounts reach the same corner and the writer picks the one
    that just gets there.  `e4b_writer` keeps the full-amount case exact by
    re-saturating (see `e4xt_cord_saturates` there); the intermediate ones are
    audibly identical and numerically not.
    """
    if not amount:
        return 0.0
    reached = base_byte + (E4XT_FENV_BYTE_PER_UNIT * (level_percent / 100.0)
                           * source_units * amount)
    lo = e4xt_cutoff_byte_to_hz(base_byte)
    hi = e4xt_cutoff_byte_to_hz(max(0.0, min(255.0, reached)))
    return 1200.0 * math.log2(max(hi, 1e-6) / max(lo, 1e-6))


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
#: THE FILTER DOES NOT FLOOR. This is a modelling limit, not a machine one, and
#: the old comment ("below the lowest measured corner") invited the opposite
#: reading -- it looked like a property of the S3000XL and is not.
#:
#: MEASURED 2026-08-24 (s3ked), steady noise, FILQ 0, no modulation, each
#: setting differenced against wide open, absolute attenuation at 80 Hz:
#:
#:     FILFRQ    0     5    10    15    20    25    30    35    40
#:     dB @80 -41.2 -35.5 -30.5 -24.2 -17.7 -11.3  -5.4  -0.8  +1.0
#:
#: **Monotonic across 41 dB with no plateau anywhere**, and the exponential --
#: fitted 44..92 and never measured below it by anyone -- predicts a 12 dB/oct
#: rolloff to within ~2 dB all the way to FILFRQ 0. At 0 the corner is 6.5 Hz
#: and the filter attenuates 41 dB at 80 Hz: a real, usable, very dark setting.
#:
#: **AND 100.0 IS ALMOST CERTAINLY AN ARTEFACT OF THE MEASUREMENT THAT WAS NOT
#: TAKEN.** s3ked's first pass normalised each curve to its own 60-120 Hz level
#: before finding the -3 dB point, and got 111.3 Hz identically for FILFRQ 0,
#: 5, 10, 20 and 30 -- a clean flat-below-and-rising-above curve saying "the
#: filter floors at 111 Hz". Once the corner drops below the normalisation
#: band the 0 dB reference sits ON THE SLOPE, so the whole curve slides with it
#: and every setting reads the same -3 dB point. **A passband reference is only
#: a passband reference while the corner is above it.** 111 is close enough to
#: this constant's 100 that they are likely the same mistake.
#:
#: Kept only as the downward-sweep bound in `_env2_amount`, where SOMETHING has
#: to stop an unbounded octave count. Named for that and nothing else.
AKAI_ENV2_SWEEP_FLOOR_HZ = 100.0   #: modelling bound on a downward env2 sweep
AKAI_FILTER_FLOOR_HZ = AKAI_ENV2_SWEEP_FLOOR_HZ   #: deprecated alias


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
    # NO CLAMP AT THE FIT'S FLOOR. This read `max(lo, byte)` with lo = 40, so
    # every FILFRQ from 0 to 40 returned the same 137.9 Hz -- **29.4% of real
    # keygroups on the library discs, all given one cutoff.** Measured 2026-08-24
    # (see AKAI_ENV2_SWEEP_FLOOR_HZ above): the corner keeps descending to
    # FILFRQ 0 with no plateau, and this law predicts it to within ~2 dB the
    # whole way despite being fitted at 44..92.
    #
    # Fifth instance of one class in a week -- a bound taken from where somebody
    # stopped fitting, applied as though it were a property of the machine. This
    # one had the largest span of the five.
    return a * math.exp(b * max(0, byte))


# ── AKAI IB-304F second filter (§AKAIFIL2) ────────────────────────────────
#
# The IB-304F adds a SECOND filter in series after the always-present 2-pole
# lowpass. Everything below is measured except the frequency law, which is
# flagged as provisional and isolated in ONE function so a single edit lands
# the sweep result.
#
# **`LSI2_ON` cannot detect the board**: it reads back 1 on a machine with no
# IB-304F fitted. So nothing on the wire tells the converter whether the
# hardware is there, and the two directions are gated differently:
#
#   READ  (AKAI -> model): gated on EVIDENCE IN THE DATA. An inert filter 2 is
#         detectable -- ~60% of keygroups with LSI2_ON set leave it wide open
#         -- so a setting that actually shapes the sound is the gate, and a
#         diagnostic names the assumption.
#   WRITE (model -> AKAI): gated on the explicit `--akai-ib304f` flag, NEVER a
#         default. The output carries no evidence at all: writing filter-2
#         settings to a boardless machine gets *"2nd filter board IB304F not
#         fitted!"* and the program does not load.

AKAI_FLT2MODE_LP = 0        #: monotonic fall, -6 dB at 31 Hz to -30 at 8 kHz
AKAI_FLT2MODE_BP = 1        #: peak at the corner, falling either side
AKAI_FLT2MODE_HP = 2        #: rise then plateau
AKAI_FLT2MODE_EQ = 3        #: parametric band, sign from FLT2Q

#: Keygroup offsets, s3ked's IB-304F map (docs/AKAI_S3000_FORMAT.md).
AKAI_LSI2_ON_OFFSET  = 168
AKAI_FLT2GAIN_OFFSET = 169
AKAI_FLT2MODE_OFFSET = 170
AKAI_FLT2Q_OFFSET    = 171
AKAI_FIL2FR_OFFSET   = 177

#: `FLT2Q` -> depth in dB at the corner in EQ mode. MEASURED, raw 0.62 Hz bins
#: (s3ked, 2026-09-08). The octave-band figures taken first are wrong by up to
#: **49 dB** and are not recorded here at all -- a fixed-width analysis band
#: cannot characterise a feature whose width is a free parameter, and `FLT2Q`
#: is precisely a width control.
#:
#: **Not a signed gain.** The cut deepens from 0 to a true notch at 16 (108 Hz
#: wide, Q 20.5) and then shallows toward the crossing, so the curve is
#: genuinely non-monotonic; do not fit a line through it.
AKAI_FLT2Q_DEPTH_DB = {0: -4.3, 10: -10.0, 15: -23.9, 16: -53.9, 18: -16.6,
                       20: -9.5, 21: -7.0, 25: +2.3, 27: +6.5, 29: +12.0,
                       31: +22.4}

#: Sign bounds, both MEASURED points. The crossing interpolates to `FLT2Q`
#: 23.1, which places the unmeasured 22 and 23 on the cut side -- 14 keygroups,
#: 3% of EQ material. The manual's "16 is no cut or boost" is right about the
#: behaviour and wrong about the value: 16 is the DEEPEST cut of all.
AKAI_FLT2Q_BANDSTOP_MAX  = 21
AKAI_FLT2Q_BANDBOOST_MIN = 25

#: Headroom in dB at `FLT2Q` 31. **+22, not the +15.57 first reported** -- the
#: octave-band metric understated the peak by 7 dB, and this is the correction
#: that clips.
AKAI_FLT2_HEADROOM_DB = 22.4

#: **MEASURED, 2026-09-09** (s3ked, mode 0 / `FLT2Q` 0, -3 dB corner against
#: the same program bypassed). The sweep FALSIFIED the shared-law hypothesis
#: this function was written on: filter 2 sits about **half** filter 1\'s corner
#: at the same byte -- very close to one octave down.
AKAI_FIL2FR_LAW_MEASURED = True

#: The seven measured corners (s3ked, 2026-09-09, mode 0 / `FLT2Q` 0, -3 dB
#: corner taken as a ratio against the same program bypassed). **Shipped as
#: points, not as a fit**, for the same reason `AKAI_FILTER_MEASURED` is -- and
#: here that decision was load-bearing within the hour.
#:
#: The first run fitted a single exponential to five points and it was
#: falsified by the next three: `FIL2FR` 20 came in at **26.9 Hz against 18.4
#: predicted, 46% high**, past a falsifier stated in advance, and a re-take of
#: byte 30 agreed with the original to 1.6%. So byte 30 was never a bad
#: measurement, which was the standing explanation for it.
#:
#: **Filter 2 FLATTENS below FIL2FR 45; filter 1 does not.** Above 45 filter 2
#: is a clean exponential at filter 1's own slope and half its frequency; below
#: 45 it departs progressively:
#:
#:      local slope        octaves per 10 bytes
#:        20 -> 30                0.68
#:        30 -> 37                0.98
#:        37 -> 45                0.78
#:        45 -> 64                1.03
#:        64 -> 72                1.00
#:        72 -> 80                0.96
#:        filter 1, throughout    1.02 .. 1.05   (checked to FILFRQ 0)
#:
#: **So the difference between the two filters is structural, not just a
#: factor** -- and the "shallower exponent" reading of the first run was an
#: artefact of fitting a single curve through the flattened region. Above 45
#: the slope is filter 1's to within a few per cent.
#:
#: Two runs of the four overlapping points agree to within 1.8%.
#: **The top departs too, and between 88 and 94 rather than filter 1's 84.**
#: Byte 88 is still on the exponential (0.951 of it); byte 94 is **1.78x**
#: above it. So the curve has three regions, not two, and neither boundary is
#: borrowed from filter 1.
AKAI_FIL2FR_MEASURED = {20: 26.9, 30: 43.1, 37: 69.4, 45: 106.9,
                        64: 414.4, 72: 720.0, 80: 1225.0,
                        88: 2073.1, 94: 5904.4}

#: **MEASURED transparent: flat to 0.0 dB in every octave band from 31 Hz to
#: 16 kHz.** At `FIL2FR` 99 the filter is out of circuit -- not a corner that
#: has moved above the audio band, an actual bypass. It is where **1532 of 2457
#: enabled keygroups sit**, so this is the single most common setting.
#:
#: **This replaces a value borrowed from filter 1.** `AKAI_FILTER_SATURATED`
#: (96) was applied to filter 2 on the assumption that the two saturate alike;
#: byte 94 is a genuine 5.9 kHz corner, so that assumption was wrong and was
#: throwing away a real setting.
AKAI_FIL2FR_TRANSPARENT = 99

#: Extrapolation exponents, DIFFERENT AT THE TWO ENDS because the curve is not
#: one exponential. Each is the local slope of the nearest measured interval.
#:
#: Neither is a law. They cover 23.4% of active filter-2 keygroups in the
#: library corpus -- 1.4% below 20 and **22.0% above 80** -- so the top is
#: where the next sweep belongs, and the bottom is nearly closed.
AKAI_FIL2FR_EXTRAP_BELOW = 0.04714      # 20 -> 30, the flattened region
AKAI_FIL2FR_EXTRAP_ABOVE = 0.17445      # 88 -> 94, the steep top

#: **`FIL2FR` 95..98 are unmeasured and sit between a real 5.9 kHz corner at 94
#: and a measured bypass at 99.** Extrapolating 88->94's slope through them
#: gives corners from 7 to 12 kHz -- audible, so they are NOT folded into the
#: bypass. But the jump from a 12 kHz corner to nothing at 99 is a
#: discontinuity, which suggests 99 is a special "off" value the way
#: `AKAI_FILTER_OPEN` is for filter 1 rather than the end of a slide.
AKAI_FIL2FR_EXTRAP_TOP_UNMEASURED_FROM = 94

#: **THE FEATURE FREQUENCY MOVES WITH `FLT2MODE`, and by a lot.** HARDWARE
#: MEASURED 2026-09-09 from programs the writer itself emitted (`FILTER2`
#: volume, `FIL2FR` 74, filter 1 open, referenced to an unfiltered control,
#: +55..+74 dB SNR), as ratios to the mode-0 law at the same byte:
#:
#:      mode 2  HP      -3 dB corner    0.688 x
#:      mode 1  BP      peak            1.653 x
#:      mode 3  EQ cut  dip             1.653 x
#:      mode 3  EQ boost peak           1.515 x
#:
#: **BP and EQ-cut land on the SAME frequency**, which is one section placing
#: its feature identically in two modes rather than a coincidence -- and the
#: boost arm sitting lower than the cut arm is the same arm asymmetry §195
#: found in the `FLT2Q` sweep.
#:
#: **The EQ offset REPRODUCES across bytes, sessions and methods:** 1.515 here
#: at `FIL2FR` 74 against 1.528 from §195 at `FIL2FR` 80 -- **0.8% apart**, one
#: measured by rendering a file this writer emitted and the other by editing a
#: resident program over SysEx.
#:
#: **An earlier 0.594 for HP is WITHDRAWN** (s3ked, same day). It came from one
#: point at `FIL2FR` 64 whose normalisation band they had flagged at the time as
#: possibly sitting inside the highpass transition; this disc was built with a
#: control for exactly that and says 0.688. The decision to prefer the disc was
#: recorded BEFORE the capture, so it is not a preference formed after seeing
#: which number was nicer.
#:
#: **NONE OF THESE ARE APPLIED.** HP, BP and EQ-cut rest on ONE byte each; only
#: EQ-boost has two, and those span 74..80 out of 0..99. A ratio measured at one
#: byte and applied across the range is the exact mistake this table already had
#: to undo once, on a five-point fit levered by a single flagged point. **What
#: they are used for is to tell the caller how big the error is** --
#: `AKAI_FIL2FR_MODE_UNCALIBRATED` quotes the factor for the mode in hand -- and
#: to make a ladder per mode the next thing worth bench time.
#:
#: (0.688 is within 3% of 1/sqrt(2). Noted, not concluded.)
#: **THE CONSTANT-FACTOR MODEL IS FALSIFIED FOR HP, AND THE FALSIFIER WAS FILED
#: IN ADVANCE** (s3ked ladder, 2026-09-09). The prediction was "each factor
#: holds within 10% at every rung"; the HP factor drifts monotonically with no
#: reversal, against our shipped law and against a single-exponential one alike:
#:
#:      byte   HP corner   / our law
#:        37       34.2 Hz     0.493
#:        45       63.0        0.589
#:        64      250.6        0.605
#:        72      467.4        0.649
#:
#: **HP has its own exponent, not a scaled mode-0 one** -- 0.07425 against
#: 0.07024, so the "factor" is itself exponential and a single constant is
#: wrong by up to a third across the range.
#:
#: **The 0.688 measured at byte 74 was not a bad measurement.** It is the top of
#: the range, where the factor is largest. Two instruments agreeing about the
#: highest rung, not disagreeing about the law.
#:
#: **And the two modes differ STRUCTURALLY, not just in scale.** Mode 0 flattens
#: below byte 45 -- its byte-37 corner sits **+14.5%** above its own exponential
#: -- while HP's byte-37 corner sits **-0.5%** from its own. Whatever makes mode
#: 0 flatten at the bottom does not do so in highpass.
#: Where mode 0's own measured span ends; above this it is extrapolated.
AKAI_FIL2FR_MEASURED_TO = 80

#: Kept as a name for the highpass ladder. **Defined here and referenced from
#: `AKAI_FIL2FR_MODE_MEASURED` below**, so there is exactly one copy of these
#: four numbers -- two tables of one measurement drifting apart is a failure
#: this file records twice already.
#: **SUPERSEDED SET, 2026-09-09 late.** The first HP column (34.2 / 63.0 /
#: 250.6 / 467.4) normalised each rung against its OWN passband plateau. The
#: highpass has a **passband bump of ~+1.1 dB sitting at ~3.8x its corner and
#: scaling with the corner**, so at low rungs the plateau band sat above the
#: bump and read the settled -6.02 dB insertion loss, while at byte 80 it sat
#: ON the bump and read -5.34. **The reference slid with the curve** -- the
#: moving-reference failure, arrived at from the far side.
#:
#: Refitted against ONE fixed reference (-6.02 dB, §195's insertion loss,
#: independently confirmed at the settled low rungs). **Take this column
#: whole**: mixing a byte-80 point onto the old four is the exact error both
#: projects made once tonight.
AKAI_FIL2FR_HP_MEASURED = {37: 36.1, 45: 64.9, 64: 247.8, 72: 448.4,
                           80: 794.8}

#: Exponent for extrapolation outside the measured HP span, from the ladder's
#: own fit (residuals -0.5/+1.2/-1.8/+1.1 %). **Extrapolation here is a guess
#: about a curve that has already surprised us once**: mode 0 has three regions
#: and this ladder covers 37..72, so anything outside is reported as such.
AKAI_FIL2FR_HP_EXPONENT = 0.07161

#: **EVERY MODE NOW HAS A LADDER** (s3ked, 2026-09-09). The single-byte factors
#: are gone: three of the four drift by 17-42% across the range, so none is
#: applied as a constant and the measured points are used instead.
#:
#: **Fitted over 45..80 -- the range where mode 0 is exponential, so its bent
#: bottom cannot contaminate the comparison -- the exponents fall into TWO
#: GROUPS, not five:**
#:
#:      HP     0.07394  |
#:      BP     0.07421  |  group A, spread 0.7%
#:      EQcut  0.07371  |
#:      -------------------------------------------- 5.2% apart
#:      EQbst  0.07068  |  group B, spread 1.1%
#:      mode0  0.06988  |
#:
#: Within-group spread is about the size of the fit residuals; between-group is
#: five times it. **EQ BOOST belongs with the LOWPASS, not with the other two
#: band modes** -- which is why its factor against mode 0 looked constant (+4%
#: across the range) when the others did not. That was the same grouping seen
#: from a different angle, not a separate fact.
#:
#: **BP and EQ-cut are barely distinguishable from each other** (0.7% apart) and
#: share a residual S-shape the others do not have (+2.2/-4.2/-0.9/+3.0 against
#: HP's +0.6/-1.8/+1.3), which s3ked reads as one filter core reached two ways.
#: **Not claimed as fact** -- this ladder cannot prove it -- but it is why both
#: keep their own table rather than being merged.
#:
#: **MODE 0 IS THE ODD ONE OUT AT THE BOTTOM.** Its byte-37 corner sits +14.5%
#: above its own exponential; every other mode is within 2.5% of its own
#: (BP +2.5, EQcut -0.6, EQbst +0.9, HP -0.5). Four modes clean, mode 0 alone
#: bent -- so the flattening is a lowpass property and NOT a property of the
#: FIL2FR control. Expressing the other modes as ratios to measured mode 0 puts
#: a bend in the denominator, which is most of why those ratios looked like they
#: drifted so hard at the bottom.
AKAI_FIL2FR_MODE_MEASURED = {
    AKAI_FLT2MODE_HP: AKAI_FIL2FR_HP_MEASURED,
    AKAI_FLT2MODE_BP: {30: 55.7, 37: 95.2, 45: 165.5, 64: 635.7,
                       72: 1190.9, 80: 2241.2},
}

#: EQ is one `FLT2MODE` with two arms, and **the arms separate as the byte
#: rises**: under resolution below byte 45, then 4.1% apart at 64, 8.3% at 72
#: and **15.4% at 80**. One centre serves both arms below ~64 and is wrong above
#: it, so they get separate tables. The 8% measured at byte 74 sits on that rise.
AKAI_FIL2FR_EQCUT_MEASURED = {30: 55.7, 37: 90.8, 45: 164.1, 64: 632.8,
                              72: 1171.9, 80: 2179.7}
AKAI_FIL2FR_EQBOOST_MEASURED = {30: 54.2, 37: 90.8, 45: 159.7, 64: 607.9,
                                72: 1082.5, 80: 1889.6}

#: Extrapolation exponent per mode, from each ladder's own fit. Outside a
#: ladder's span this is a guess about a curve that has already surprised us
#: once -- mode 0 has three regions -- so the caller is told.
AKAI_FIL2FR_MODE_EXPONENT = {
    AKAI_FLT2MODE_HP: 0.07161,
    AKAI_FLT2MODE_BP: 0.07421,
    AKAI_FLT2MODE_EQ: 0.07371,          # cut arm; boost uses the value below
}
AKAI_FIL2FR_EQBOOST_EXPONENT = 0.07068


def _fil2fr_from_table(byte, table, exponent):
    """Shared shape: measured points exact, geometric between, fit outside."""
    if byte >= AKAI_FIL2FR_TRANSPARENT:
        return None
    pts = sorted(table)
    lo, hi = pts[0], pts[-1]
    if byte in table:
        return table[byte]
    if byte < lo:
        return table[lo] * math.exp(exponent * (byte - lo))
    if byte > hi:
        return table[hi] * math.exp(exponent * (byte - hi))
    for x0, x1 in zip(pts, pts[1:]):
        if x0 <= byte <= x1:
            y0, y1 = table[x0], table[x1]
            f = (byte - x0) / (x1 - x0)
            return math.exp(math.log(y0) + f * (math.log(y1) - math.log(y0)))
    return table[hi]


def akai_fil2fr_mode_to_hz(byte: int, mode: int, boost: bool = False):
    """`FIL2FR` -> the filter-2 feature frequency in Hz, FOR THIS MODE.

    Lowpass returns its -3 dB corner; highpass its -3 dB corner; bandpass its
    peak; EQ its dip or bump. **These are different quantities**, which is the
    whole reason one law could not serve them -- and comparing across them is
    how a 1.29x documented gap first got read as a property of filter 2.
    """
    if mode == AKAI_FLT2MODE_LP:
        return akai_fil2fr_to_hz(byte)
    if mode == AKAI_FLT2MODE_EQ:
        tbl = (AKAI_FIL2FR_EQBOOST_MEASURED if boost
               else AKAI_FIL2FR_EQCUT_MEASURED)
        exp = (AKAI_FIL2FR_EQBOOST_EXPONENT if boost
               else AKAI_FIL2FR_MODE_EXPONENT[AKAI_FLT2MODE_EQ])
        return _fil2fr_from_table(byte, tbl, exp)
    tbl = AKAI_FIL2FR_MODE_MEASURED.get(mode)
    if tbl is None:
        return akai_fil2fr_to_hz(byte)
    return _fil2fr_from_table(byte, tbl, AKAI_FIL2FR_MODE_EXPONENT[mode])


def akai_fil2fr_hp_to_hz(byte: int):
    """Kept as a name; the highpass case of `akai_fil2fr_mode_to_hz`."""
    return akai_fil2fr_mode_to_hz(byte, AKAI_FLT2MODE_HP)


def akai_fil2fr_to_hz(byte: int):
    """`FIL2FR` -> the filter-2 -3 dB corner in Hz, or None when wide open.

    **MEASURED 2026-09-09, and it is NOT filter 1\'s law.** Filter 2 sits at
    about **0.515x** filter 1\'s corner for the same byte -- 0.96 octaves down,
    stable at 0.50-0.53 across the four solid points.

    Measured points are returned exactly and interpolated geometrically between
    (the scale is logarithmic in frequency). Outside the span:

      * **below 20** -- extrapolated along the flattened region's own slope,
        `AKAI_FIL2FR_EXTRAP_BELOW`. Only 1.4% of active keygroups land here.
      * **above `AKAI_FIL2FR_MEASURED_TO`** -- extrapolated, and the caller
        should say so. Filter 1 leaves its own exponential from 84 up; whether
        filter 2 does is unmeasured and p90 of the corpus is 88.
      * at `AKAI_FIL2FR_TRANSPARENT` (99) -- None. **Measured flat to 0.0 dB
        in every band**: the filter is out of circuit, not merely wide open.
        95..98 are unmeasured and carry an extrapolated corner.

    **The corner also moves with `FLT2MODE`** -- 41% between LP and HP at one
    byte -- and everything here was measured in mode 0. See
    `AKAI_FIL2FR_HP_RATIO_AT_64`.

    **The hypothesis this function first shipped on was wrong, and the argument
    against that hypothesis was also wrong.** "Filter 2 measures ~2200 where our
    law says 2503" compared an EQ extremum against a corner law -- two correct
    numbers naming different quantities. The correct like-for-like comparison
    (an EQ boost peak against a resonance-peak fit) said the laws MATCHED to
    1.1%, which is what put the shared-law assumption in. Both readings were
    artefacts of the comparand; only the mode-0 corner ladder settled it, and
    the real difference is 2x in the direction neither comparison suggested.
    """
    if byte >= AKAI_FIL2FR_TRANSPARENT:
        return None
    pts = sorted(AKAI_FIL2FR_MEASURED)
    lo, hi = pts[0], pts[-1]
    if byte in AKAI_FIL2FR_MEASURED:
        return AKAI_FIL2FR_MEASURED[byte]
    if byte < lo:
        return AKAI_FIL2FR_MEASURED[lo] * math.exp(
            AKAI_FIL2FR_EXTRAP_BELOW * (byte - lo))
    if byte > hi:
        return AKAI_FIL2FR_MEASURED[hi] * math.exp(
            AKAI_FIL2FR_EXTRAP_ABOVE * (byte - hi))
    for x0, x1 in zip(pts, pts[1:]):
        if x0 <= byte <= x1:
            y0, y1 = AKAI_FIL2FR_MEASURED[x0], AKAI_FIL2FR_MEASURED[x1]
            f = (byte - x0) / (x1 - x0)
            return math.exp(math.log(y0) + f * (math.log(y1) - math.log(y0)))
    return AKAI_FIL2FR_MEASURED[hi]


#: **The two sections cascade, so the PAIR's corner is not either section's.**
#: MEASURED 2026-09-09 (s3ked): with `FILFRQ` 62 and `FIL2FR` 72 both landing
#: on ~679 Hz individually, the pair's -3 dB corner is **571 Hz**.
#:
#: The cascade is the sum of the singles in dB **to within 0.04 dB over six
#: octaves**, so the sections multiply cleanly and do not interact -- which is
#: what makes a single ratio the right model rather than a fudge.
#:
#: Two ideal Butterworth sections predict 0.802; the measured 0.841 sits above
#: it, consistent with filter 1's own **+0.74 dB passband bump** before its
#: corner (a Q slightly above Butterworth). The measurement is used, not the
#: theory.
#:
#: **A round trip cannot catch getting this wrong.** Writing both sections at
#: the asked-for corner and reading the pair back as that same corner is
#: self-consistent to the last decimal and 16% wrong against the instrument.
#: That is exactly how it shipped for one commit, with a passing round-trip
#: test at +-2.5%.
AKAI_CASCADE_CORNER_RATIO = 0.841

#: How close two corners must be for the ratio above to apply. It was measured
#: with the two sections MATCHED to within 1 Hz; how the pair's corner moves as
#: they separate is not measured, and interpolating it would be invention. Far
#: apart, the lower section dominates and its own corner is the answer.
AKAI_CASCADE_MATCHED_OCTAVES = 0.33


def hz_to_akai_fil2fr(hz: float) -> int:
    """Hz -> the `FIL2FR` byte whose corner is nearest, in LOG frequency.

    Inverse of `akai_fil2fr_to_hz`, and written as a search over that function
    rather than as an algebraic inverse **because the curve is not one law**:
    it flattens below byte 45, tracks filter 1's slope in the middle, and
    steepens above 88. A hand-derived inverse of a three-region curve is
    exactly the drift `AKAI_FILTER_LAW`\'s own comment warns about -- two
    inverses of one curve came apart in a day and nine of ten values failed a
    round trip while a docstring claimed they could not.

    Distance is measured in log Hz because the scale is logarithmic: nearest in
    Hz would put every low corner on the same byte.
    """
    if hz is None:
        return AKAI_FIL2FR_TRANSPARENT
    target = math.log(max(1e-6, hz))
    best, best_d = 0, None
    for b in range(0, AKAI_FIL2FR_TRANSPARENT):
        v = akai_fil2fr_to_hz(b)
        d = abs(math.log(v) - target)
        if best_d is None or d < best_d:
            best, best_d = b, d
    return best


def hz_to_akai_fil2fr_hp(hz: float) -> int:
    """Hz -> the `FIL2FR` byte whose HIGHPASS corner is nearest, in log Hz.

    Inverse of `akai_fil2fr_hp_to_hz`, and it must exist as its own function:
    placing a highpass corner with the mode-0 inverse while reading it back
    with the highpass curve makes the reader and writer stop being inverses,
    which is what the round-trip tests caught the moment the HP curve landed.
    """
    if hz is None:
        return AKAI_FIL2FR_TRANSPARENT
    target = math.log(max(1e-6, hz))
    best, best_d = 0, None
    for b in range(0, AKAI_FIL2FR_TRANSPARENT):
        d = abs(math.log(akai_fil2fr_hp_to_hz(b)) - target)
        if best_d is None or d < best_d:
            best, best_d = b, d
    return best


def akai_depth_db_to_flt2q(db: float) -> int:
    """A desired EQ depth in dB -> the nearest `FLT2Q`.

    **The notch at 16 is excluded from the search.** It is a singular 108 Hz
    feature at -53.9 dB, and a source asking for a deep cut would otherwise
    land on it and get something 20x narrower than it asked for. Depth alone
    does not describe that setting, so it is never chosen by depth alone.
    """
    best, best_d = 0, None
    for b, v in AKAI_FLT2Q_DEPTH_DB.items():
        if b == 16:
            continue
        d = abs(v - db)
        if best_d is None or d < best_d:
            best, best_d = b, d
    return best


def akai_flt2q_to_depth_db(byte: int) -> float:
    """`FLT2Q` -> depth in dB at the corner (EQ mode). Negative cuts.

    Interpolates linearly between measured points, which is **hazardous where
    the material actually sits**: 177 of 469 EQ keygroups fall in regions
    steeper than 2 dB per unit, and `FLT2Q` 16 is a singular 108 Hz notch that
    no interpolation through its neighbours reproduces. The measured points are
    exact; the gaps are the honest best available and are marked by
    `AKAI_FLT2Q_INTERPOLATED` at the point of use.
    """
    b = max(0, min(31, int(byte)))
    if b in AKAI_FLT2Q_DEPTH_DB:
        return AKAI_FLT2Q_DEPTH_DB[b]
    pts = sorted(AKAI_FLT2Q_DEPTH_DB)
    if b < pts[0]:
        return AKAI_FLT2Q_DEPTH_DB[pts[0]]
    if b > pts[-1]:
        return AKAI_FLT2Q_DEPTH_DB[pts[-1]]
    for x0, x1 in zip(pts, pts[1:]):
        if x0 <= b <= x1:
            y0, y1 = AKAI_FLT2Q_DEPTH_DB[x0], AKAI_FLT2Q_DEPTH_DB[x1]
            return y0 + (y1 - y0) * (b - x0) / (x1 - x0)
    return 0.0


def akai_flt2q_is_boost(byte: int) -> bool:
    """EQ mode: does this `FLT2Q` BOOST the band? 78% of real material does.

    Reading mode 3 as a notch -- which the one low-Q bench capture suggested --
    would be wrong for 367 of 469 enabled keygroups.
    """
    return int(byte) >= AKAI_FLT2Q_BANDBOOST_MIN


def nominal_knob_to_hz(knob: float) -> float:
    """A source's normalised 0..1 cutoff knob -> Hz on the NOMINAL scale.

    **For sources whose filter range nobody has measured.** `pgm` (MPC1000),
    the MPC 2.x XPM path, `talsmpl` and `gig` all carry a 0..1 knob with no
    Hz law behind it; see TODO's "Normalised-knob cutoff sources", where the
    MPC 3 half was closed by measuring the hardware and these were left.

    **This changes no output.** Until 2026-08-25 those parsers stored the raw
    knob into a field that the whole pipeline then read as a position on this
    exact scale -- so the assumption was already being made, silently, by
    everything downstream. Routing it through a named function makes it
    greppable and makes the day somebody measures one of those machines a
    one-line change instead of an archaeology exercise.

    It is NOT a calibration and must not be cited as one.
    """
    return e4b_cutoff_position_to_hz(max(0.0, min(1.0, knob)))


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


#: THE K2000's DISPLAYED RELEASE TIME IS THE TIME TO CROSS A FIXED SPAN.
#:
#: MEASURED 2026-08-25 (k2kremote), on a subject built for it: program 199's
#: edit buffer, algorithm 1 (PITCH->NONE->AMP, no filter stage at all), ROM
#: sawtooth, no cords, FX confirmed dry, AMPENV switched out of Natural mode --
#: which it ships in, and which would have made the whole run measure the
#: sample's own envelope instead.
#:
#:     displayed 3.00 s   ->  -33.02 dB/s   span 99.06 dB   r2 0.9996
#:     displayed 1.00 s   ->  -99.68 dB/s   span 99.68 dB   r2 0.9974
#:
#: **Two settings, one subject, spans agreeing to 0.62%.** The machine is a
#: RATE machine (slope invariant across sustain levels, measured separately),
#: and the display states the seconds to traverse ~99.4 dB.
#:
#: THE FAST SETTING HAD TO BE FITTED OVER ITS TOP THIRD. Across the whole
#: window it reads -89.4 dB/s, because the fall bends and a straight line
#: across a bend is a chord. The top 12 dB gives -99.68 with r2 0.9974. The
#: full-window number is an average and is not the rate.
#:
#: This supersedes `KRZ_RELEASE_FACTOR` for any source that carries a rate:
#: that factor was derived from the machine's DISPLAYED release against
#: another machine's, which is two conversions of an unmeasured span rather
#: than one measurement of a real one.
KRZ_RELEASE_SPAN_DB = 99.37


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
    """EOS rate byte → envelope time in seconds (inverse of env_seconds_to_rate).

    **RATE 0 IS INSTANT AND USED TO READ AS 31 ms.** `env_seconds_to_rate(0)`
    returns 0, so the pair were not inverses at the one value a source is most
    likely to state: an attack of exactly zero came back as `ENV_RATE_A`
    itself. Measured over the E4B corpus 2026-08-24, the filter envelope
    changed on **77.4% of round-tripped zones**, and the commonest single
    difference was `attack 0.0 -> 0.031`.

    It was known and unfixed: §LAWRANGE's own table lists this function at
    "0.031000, floor, against its own comment saying rate 0 = instant". The
    comment was right and the code did something else -- the fourth time this
    week (see §INERTCHANGE).

    Zero is a semantic value the source states, not a point on the curve, which
    is the same reason `akai_env2_stage_seconds` special-cases it.
    """
    if rate <= 0:
        return 0.0
    return ENV_RATE_A * math.exp(ENV_RATE_K * min(127, rate))


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
#: !! THE THREE-POINT FIT BELOW IS DEAD -- SUPERSEDED BY THE MEASURED TABLE.
#: Kept only so its failure is legible. It was exact at bytes 0/64/127 by
#: construction and wrong by a MEAN of 28.4% across the range, worst -61.3% at
#: byte 15. Neither this project nor eosed noticed for three months because each
#: validated the curve at the same three anchors it was fitted to -- a check the
#: instrument could not fail. A fitted law must be validated somewhere it was NOT
#: fitted: with N free parameters and N anchors, N agreements prove nothing.
_LFO_RATE_A = -0.000300578      # DEAD -- see _LFO_RATE_TABLE
_LFO_RATE_B =  0.0808242        # DEAD
_LFO_RATE_C = -2.52573          # DEAD

#: E4XT LFO rate byte -> Hz, MEASURED 2026-09-07 (eosed), one row per byte, read
#: off the machine's own LFO Rate field by exact-glyph LCD OCR -- no interpolation
#: and no curve. An unrecognised glyph was reported rather than guessed.
#: Validated three ways: the three June anchors land exactly (0.08 / 4.12 / 18.01),
#: five independent AUDIO measurements match to 0.00 Hz (bytes 40, 60, 95, 105,
#: 115), and the table is monotonic non-decreasing across the whole range, which a
#: mis-read digit would almost certainly break.
#: The steps are IRREGULAR by design -- 0.38, 0.42, 0.48, 0.50, then 0.65 with no
#: 0.6x before it. That is what a real lookup table looks like and it is why no
#: curve reproduces it.
#: Source: ~/temp/e4xt_ref/lfotable/lfo_rate_table.json (raw bitmaps beside it).
#: CONFIRMED IN THE SHIPPING PATH 2026-09-07, and the last caveat is discharged.
#: A/B on one disc, one byte apart, so no cross-card drift:
#:     byte  95  table  8.85  measured  8.85 Hz   (at CC1 = 0 and 127)
#:     byte 106  table 11.44  measured 11.44 Hz   (at CC1 = 0 and 127)
#: 750 frames each at 0.27 Hz resolution, and the balance SWINGS are unchanged
#: across the pair (27.05 -> 26.74 dB, 66.19 -> 65.21) -- so only the rate moved.
#:
#: NOT per-voice and NOT shape-dependent: a different bank, preset, voice and LFO
#: shape (triangle, where the A/B was sine) matched the table at bytes 30, 70,
#: 100 and 120 exactly, plus byte 64 read incidentally at the June anchor. The
#: mapping is a global property of the LFO.
_LFO_RATE_TABLE = (
     0.08,  0.11,  0.15,  0.17,  0.21,  0.25,  0.28,  0.32,   #   0-7
     0.36,  0.38,  0.42,  0.48,  0.50,  0.53,  0.56,  0.65,   #   8-15
     0.69,  0.72,  0.76,  0.80,  0.84,  0.92,  0.95,  0.99,   #  16-23
     1.03,  1.11,  1.13,  1.22,  1.26,  1.30,  1.37,  1.41,   #  24-31
     1.49,  1.56,  1.60,  1.68,  1.72,  1.79,  1.87,  1.95,   #  32-39
     1.98,  2.06,  2.14,  2.21,  2.29,  2.37,  2.44,  2.52,   #  40-47
     2.59,  2.67,  2.75,  2.82,  2.98,  3.05,  3.13,  3.20,   #  48-55
     3.28,  3.43,  3.51,  3.59,  3.74,  3.81,  3.89,  4.04,   #  56-63
     4.12,  4.26,  4.34,  4.50,  4.58,  4.73,  4.88,  4.96,   #  64-71
     5.11,  5.26,  5.34,  5.49,  5.65,  5.80,  5.95,  6.10,   #  72-79
     6.26,  6.41,  6.56,  6.71,  6.87,  7.02,  7.17,  7.32,   #  80-87
     7.63,  7.78,  7.93,  8.09,  8.39,  8.53,  8.69,  8.85,   #  88-95
     9.16,  9.31,  9.61,  9.77, 10.07, 10.22, 10.53, 10.68,   #  96-103
    10.99, 11.14, 11.44, 11.75, 12.05, 12.21, 12.51, 12.82,   # 104-111
    13.12, 13.43, 13.73, 14.04, 14.34, 14.65, 14.95, 15.26,   # 112-119
    15.56, 15.87, 16.17, 16.78, 17.09, 17.39, 17.70, 18.01,   # 120-127
)
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
#
# TWO PROBLEMS WITH THIS CONSTANT, recorded 2026-09-01, neither yet fixed:
#
# 1. It serves two roles at once and they will diverge. It is documented above
#    as an EOS-specific number -- the dB swing of an E4B mod cord at amount
#    100 % -- but `lfo_volume_depth_to_amount` uses it as the model's UNIVERSAL
#    dB <-> amount convention, so it is what an SFZ `amplfo_depth` in dB means
#    once it reaches the model, and what any future writer would multiply back
#    out by. The moment someone measures the real EOS full scale and edits this
#    line, every SFZ and SF2 tremolo silently changes depth, on every target,
#    including ones that have nothing to do with EOS. When the EOS measurement
#    lands, split this into a format constant and a model convention FIRST,
#    then change the format one.
#    RESOLVED the same day: the split was done, and with it this hazard went
#    away entirely -- see LFO_VOLUME_MODEL_FULL_DB, which was then safely
#    raised to 96.0 precisely because the two roles no longer share a name.
#
# 2. The swing DIRECTION underneath it is unmeasured -- see the docstring of
#    `lfo_volume_depth_to_amount`, which asserts a downward-only swing with
#    nothing behind it. The K2000 now has a real per-unit law for the same
#    modulation (`KRZ_F4_AMP_DEPTH_DB_PER_UNIT`, measured), so the missing
#    piece for writing tremolo at hardware is direction and headroom, not
#    scale. Questions are out to k2kremote and s3ked as of 2026-09-01.
#
# SPLIT 2026-09-01 into the two roles the single constant was carrying. They
# hold the same number today and are NOT the same fact: one is a claim about
# EOS hardware, the other is an arbitrary-but-fixed unit for the model.
#: The model's dB <-> 0..1 convention for `lfo1_to_volume` / `lfo2_to_volume`.
#: A unit, not a measurement: there is nothing here to calibrate.
#:
#: RAISED 24.0 -> 96.0 on 2026-09-01, and the reason is worth keeping because
#: it corrects an over-cautious note written here earlier the same day.
#:
#: WHY IT WAS RAISED. `lfo_volume_depth_to_amount` clamps at 1.0, so this
#: constant is a CEILING on any tremolo the model can carry. Surveying 10,933
#: real AKAI programs across 21 CD-ROMs, **25 keygroups** carry a non-zero
#: LFO->loudness amount, with one-sided depths from 0.31 to 49.84 dB (median
#: 3.38) -- so **6 of the 25 were being truncated at 24 dB**, the deepest
#: losing half its depth. A ceiling below the material is not a neutral unit
#: choice. 96 matches the K2000's own +/-96 dB rail, the widest measured
#: hardware range on this project; nothing in the corpus reaches it.
#:
#: (A first pass reported "8 programs, median 12.46". That scan checked only
#: the FIRST keygroup for the slot-3 amount, which is a PER-KEYGROUP field --
#: so it both under-counted and biased the median upward. The corrected sweep
#: walks every keygroup. Counting in the wrong unit is not a rounding error.)
#:
#: WHY CHANGING IT IS SAFE, having earlier been recorded as dangerous. The
#: warning was written while ONE constant served two roles, and it was correct
#: then. After the split it is not: this value is now used symmetrically --
#: readers divide by it, writers multiply by it, all in one process, and no
#: Bank is ever serialised -- so the dB a tremolo means is preserved across
#: any change of scale. Only the intermediate 0..1 number moves. The real
#: hazard was ever letting a hardware fact and an internal unit share a name.
LFO_VOLUME_MODEL_FULL_DB = 96.0

#: EOS mod-cord amount 100 % -> dB of amplitude swing. **UNMEASURED** -- this
#: is the one to edit when a MOD_DEPTH_CAL-style E4XT run finally pins it, and
#: editing it then affects the E4B writer ALONE, which is the entire point of
#: the split.
E4B_LFO_VOLUME_FULL_DB = 24.0


# ── K2000 LFO1 rate byte <-> Hz ────────────────────────────────────────────
#
# MEASURED 2026-09-07 (k2kremote): 185 rows, one per byte, read off the K2000's
# own LFO1 MnRate field. NOT a fit -- the five segments below reproduce all 185
# measured rows EXACTLY (verified here before adoption), so this is a lossless
# encoding of the table rather than an approximation of it.
#
#     byte   0..20    0.01 Hz/byte     0.00 ..  0.20 Hz
#     byte  20..36    0.05 Hz/byte     0.20 ..  1.00 Hz
#     byte  36..126   0.10 Hz/byte     1.00 .. 10.00 Hz
#     byte 126..176   0.20 Hz/byte    10.00 .. 20.00 Hz
#     byte 176..184   0.50 Hz/byte    20.00 .. 24.00 Hz
#
# BYTE 184 IS THE CEILING -- wheeling past it does not move the value, so the
# reachable range is 0..184 and NOT 0..255. The old writer clamped to 255; what
# the engine does with 185-255 is unknown and untested.
#
# WHY THE OLD LAW LOOKED RIGHT. `byte = 26 + 10*Hz` is segment 3 exactly:
# 36 + (Hz - 1.00)/0.10 == 26 + 10*Hz, character for character. It is the
# CORRECT law for 1.00-10.00 Hz and wrong everywhere else -- which is why it was
# exact at 8.70 Hz (byte 113) and put 11.50 Hz at byte 141, a byte that really
# is 13.00 Hz. The entire discrepancy was one segment boundary at 10 Hz.
#
# GRID COARSENESS IS REAL AND WORTH REPORTING TO CALLERS: above 10 Hz the step
# is 0.2 Hz and above 20 Hz it is 0.5 Hz, so e.g. 11.50 Hz is NOT reachable --
# byte 133 gives 11.40 and 134 gives 11.60.
#
# Source table: ~/temp/k2k_algs/lfo1_rate_table.json
_KRZ_LFO_RATE_SEGMENTS = ((0, 20, 0.01), (20, 36, 0.05), (36, 126, 0.10),
                          (126, 176, 0.20), (176, 184, 0.50))
KRZ_LFO_RATE_BYTE_MAX = 184
KRZ_LFO_RATE_HZ_MAX = 24.00


def krz_lfo_rate_byte_to_hz(byte: int) -> float:
    """K2000 LFO1 MnRate byte -> Hz, via the measured five-segment ladder."""
    b = max(0, min(KRZ_LFO_RATE_BYTE_MAX, int(byte)))
    hz = 0.0
    for lo, hi, step in _KRZ_LFO_RATE_SEGMENTS:
        if b > lo:
            hz += (min(b, hi) - lo) * step
    return round(hz, 2)


def krz_lfo_rate_hz_to_byte_actual(hz: float):
    """Hz -> (byte, achieved_hz) for the K2000 LFO1 rate.

    Returns the CLOSEST reachable byte and what it actually gives, because the
    grid is coarse above 10 Hz: 11.50 Hz is not reachable at all (133 -> 11.40,
    134 -> 11.60). A caller that needs to report or record the rounding can;
    silently assuming the request was honoured is how `26 + 10*Hz` shipped a
    13.00 Hz LFO for an 11.50 Hz source.
    """
    want = max(0.0, min(KRZ_LFO_RATE_HZ_MAX, float(hz)))
    best = min(range(KRZ_LFO_RATE_BYTE_MAX + 1),
               key=lambda b: abs(krz_lfo_rate_byte_to_hz(b) - want))
    return best, krz_lfo_rate_byte_to_hz(best)


def krz_lfo_rate_hz_to_byte(hz: float) -> int:
    """Hz -> the closest reachable K2000 LFO1 rate byte (0..184)."""
    return krz_lfo_rate_hz_to_byte_actual(hz)[0]


def lfo_rate_byte_to_hz(byte: int) -> float:
    """E4B LFO rate byte 0-127 -> Hz, by table lookup (see _LFO_RATE_TABLE)."""
    return _LFO_RATE_TABLE[max(0, min(127, int(byte)))]


def lfo_rate_hz_to_byte(hz: float) -> int:
    """LFO frequency in Hz -> the E4B rate byte whose rate is CLOSEST.

    The table is not dense enough to hit an arbitrary target: the low end steps
    by ~0.03 Hz and the top by ~0.31 Hz, so a request always lands on a
    neighbour. Use `lfo_rate_hz_to_byte_actual` when the caller needs to know
    what it actually got -- silently accepting the error is how a 28% mis-rate
    survived three months here.
    """
    return lfo_rate_hz_to_byte_actual(hz)[0]


def lfo_rate_hz_to_byte_actual(hz: float):
    """As `lfo_rate_hz_to_byte`, but returns ``(byte, achieved_hz)``.

    e.g. 11.46 Hz -> (106, 11.44). The caller can then report or record the
    rounding rather than assume it got what it asked for.
    """
    hz = max(LFO_RATE_HZ_MIN, min(LFO_RATE_HZ_MAX, float(hz)))
    best = min(range(128), key=lambda b: abs(_LFO_RATE_TABLE[b] - hz))
    return best, _LFO_RATE_TABLE[best]


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
    """Map an LFO→volume (tremolo) depth in dB to a 0..1 mod amount.

    Always positive: the depth is a magnitude, and swapping an LFO's sign
    only shifts its phase, so there is no meaningful "negative" direction to
    preserve. That much is safe.

    What is NOT established is where the swing sits relative to the
    un-modulated level -- whether its peak rises above that level (symmetric
    about it, costing depth/2 of headroom and able to clip a zone already near
    full scale) or merely ducks down to it. This docstring asserted the
    downward reading from 2026-07-28 until 2026-09-01, when the assertion was
    found to rest on nothing; it is now an open question with both hardware
    sessions. Do not rely on it to decide headroom.

    The scale is LFO_VOLUME_MODEL_FULL_DB, a fixed unit rather than a
    measurement; E4B_LFO_VOLUME_FULL_DB is the EOS-specific one."""
    return max(0.0, min(1.0, abs(db) / LFO_VOLUME_MODEL_FULL_DB))


# ── KRZ (K2000) scalar codecs ───────────────────────────────────────────────
# Shared by writers/krz_writer.py and parsers/krz_parser.py so the two stay
# exact inverses (CR-13/CR-18 pattern: single home, not "kept in sync by
# comment"). All HW-confirmed via krz_program_re.md; see docs/KRZ_FORMAT.md §4.

#: **THE K2000's DISPLAYED CUTOFF IS f0, NOT THE -3 dB CORNER -- RESOLVED
#: 2026-09-02 (k2kremote, swept sine). The label is HONEST; it just denotes a
#: different frequency than the other three formats do.** This supersedes both
#: the earlier "within ~10 %" bound and the intermediate reading of it as a
#: calibration error.
#:
#: Measured by reading the gain AT the displayed corner rather than inferring
#: Q from the -3 dB point, which would have been circular:
#:
#:     2POLE   gain at the label -0.10 dB -> Q = 0.989   (Butterworth: -3.01)
#:             -3 dB crossing at 1.264*f0 -> Q = 0.986
#:             two independent readings of one curve, agreeing to 0.2 %
#:     4POLE   gain at the label -6.11 dB -> |H| = 0.495 = 0.703^2
#:             i.e. two BUTTERWORTH sections (0.7071) at the same f0
#:             -3 dB at 0.774*f0 against 0.802 predicted (-3.5 %)
#:
#: So the two filters really do have different zero-resonance Q, which is what
#: the arithmetic demanded: no single Q can put a 2-pole at 1.242 and a
#: cascade at 0.760. The 2-pole is designed for **unity gain at the labelled
#: frequency** -- an obvious choice once seen. SEP was verified 0 off the panel
#: (`Coarse/Fine/KeyTrk/Depth` all 0), so the sections were genuinely
#: co-located and the cascade arithmetic applies.
#:
#: **CONSEQUENCE, AND IT IS A REAL CORRECTION rather than an error to fix.**
#: Every source format this project reads carries a MEASURED -3 dB CORNER
#: (AKAI and E4XT say so explicitly; the MPC's fitted 2-pole fc is one). The
#: K2000's byte denotes f0. Mapping one onto the other needs:
#:
#:     source is a -3 dB corner ->  2-pole: byte_Hz = f_3dB / 1.264  (-406 ct)
#:                                  4-pole: byte_Hz = f_3dB / 0.774  (+444 ct)
#:
#: **They go in OPPOSITE directions**, and the 2-pole is 77 % of real layers --
#: so writing the AKAI's -3 dB frequency straight into the byte, which is what
#: happens today, puts the K2000's f0 about **four semitones too high** on the
#: common case. §KRZCUTCAL could never have seen this: it only ever compared
#: our law to the machine's own label, and the label was right all along.
#:
#: **CONFIRMED AGAINST AN INDEPENDENT INSTRUMENT (2026-09-02).** The MPC
#: measures cutoff as a -3 dB corner, the same quantity we do, so the two
#: machines can be asked directly. MPC static filter (Cutoff 70, Depth 0) =
#: 808 Hz corner; K2000 program with its envelope zeroed at cutoff bytes 20
#: (displays 831) and 15 (displays 622):
#:
#:     level    MPC      A(831)     B(622)
#:     -40 dB   1256 Hz  1498 Hz    1287 Hz     A +305 ct   B  +43 ct
#:     -50 dB   1592 Hz  1756 Hz    1611 Hz     A +169 ct   B  +20 ct
#:     mean |error| vs MPC over 1-2 kHz:  A 7.9 dB    B 2.2 dB
#:
#: **B lands within 20-43 cents of the source; A is 170-305 cents bright.**
#: So three independent lines now agree the label is f0: gain at the corner
#: (-0.10 dB -> Q 0.989), the -3 dB crossing (1.264 -> Q 0.986), and an
#: external instrument measuring the same physical quantity.
#:
#: **METHOD WARNING, and it nearly inverted the answer: SPECTRAL CENTROID
#: CANNOT MEASURE A FILTER CORNER ON A PITCHED SOURCE.** mpc2emu asked for
#: centroid; on this material it moved only 115 cents where 406 was
#: predicted, and `rolloff85` moved 272 cents in the OPPOSITE direction --
#: two summary statistics disagreeing in SIGN over the same captures. Both
#: are dominated by the bass fundamental and its low harmonics, which sit far
#: below either corner. The 1/3-octave comparison above works because it
#: looks where the filter is actually acting. Reported as centroid, the
#: honest reading would have been "under-powered, inconclusive" -- and wrong.
#:
#: The cross-machine caveat shows up exactly where predicted: at 630-800 Hz
#: both K2000 versions sit 13-18 dB above the MPC, which is the converted
#: sample's own spectrum near the fundamental rather than the filter. Compare
#: on the SLOPE ABOVE the corner, where the source difference has died away.
#:
#: **STILL NOT WIRED -- Jan's call, pending his ears.** Held on k2kremote's own advice: one rig, one
#: day, and a 4-semitone change on the dominant KRZ path deserves a listen
#: before it ships. Repeatability is partial (1047 Hz measured twice at
#: 1.265/1.264; the 4-pole twice at 0.775/0.774). The 4-pole's residual -3.5 %
#: against the ideal cascade is unchased and may just be non-identical
#: sections.
#:
#: METHOD, and why it beat the noise runs: a chromatic scale on a sine keymap
#: IS a swept sine. All energy at one frequency, so a deep stopband point still
#: measures; the corner is read off the curve so no model and no topology
#: assumption is needed; and there is NO FIT BAND -- the knob whose sensitivity
#: had forced the earlier bound. Purity median 1.000, span 12.2 octaves,
#: plateau +0.0 dB.
#:
#: THE FAILED FIRST ATTEMPT, kept because the cause generalises: 49 notes gave
#: 0.8 octaves and purity 0.64. Neither a band-limited estimator (mpc2emu's
#: guess -- theirs is an unrestricted rfft argmax) nor pitch keytracking
#: (k2kremote's). **The CUT programs' layer spans exactly one key,
#: `LoKey C 4 / HiKey C 4`**, so 48 of 49 notes were silent and the
#: "measurement" was 48 noise-floor captures averaged with one real tone.
#: Jan's one-note test found it in a single capture -- which is why **play ONE
#: note and look at the raw waveform** belongs before any sweep logic exists.
#: The K2000's displayed cutoff is **f0**, the section's natural frequency;
#: every source format this project reads carries a **-3 dB corner**. For the
#: 2-pole (Q 0.989, 77 % of real layers) the two differ by a measured factor:
#:
#:     f_3dB = f0 * 1.264        f0 = f_3dB / 1.264      (-406 cents)
#:
#: Confirmed four ways -- gain at the corner, the -3 dB crossing, an external
#: instrument (the MPC, which measures the same quantity) and Jan's ears on an
#: A/B of the two. WIRED 2026-09-02 in both directions.
#:
#: **The 4-POLE IS DELIBERATELY NOT CORRECTED.** Its label is also f0 and its
#: factor goes the OTHER way (about 0.774-0.802, i.e. +444 cents), but it is
#: 2.4 % of real layers, measured to only ~3.5 %, and an uncorrected 4-pole is
#: wrong by less than a corrected-in-the-wrong-direction one would be. See the
#: note above krz_cutoff_byte_to_hz.
KRZ_2POLE_F0_TO_3DB = 1.264

#: 4POLE LOPASS W/SEP: its label is f0 of each SECTION, and the cascade's
#: -3 dB sits BELOW it -- so this correction runs the opposite way to the
#: 2-pole's (+444 cents rather than -406).
#:
#: **DERIVED, not fitted, and that is why 0.802 is used rather than the
#: measured 0.774.** k2kremote measured -6.11 dB at the displayed corner,
#: which is 0.703^2 against a Butterworth section's 0.7071^2 -- confirming to
#: 0.5 % that the filter IS two Butterworth sections at one f0. Two such
#: sections are -6 dB at the section corner, so their combined -3 dB falls at
#: exactly 0.802 x f0. The measured 0.774 carries the scatter of a fit over
#: ~3.5 %; 0.802 follows from a topology that was independently confirmed.
#: Jan's call 2026-09-02, after asking whether a listen could choose between
#: them: it cannot -- they are 60 cents apart, at or below what is
#: distinguishable on a corner across two machines.
#:
#: SEP was verified 0 off the panel for that measurement, so the sections
#: really were co-located and the cascade arithmetic applies. A non-zero SEP
#: separates them and this factor would not hold.
KRZ_4POLE_F0_TO_3DB = 0.802

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
    #: The resonance of the VOICE this zone came from, stamped before any
    #: layer fusion averages it away (§KRZRESKEYTRK). `filter_resonance` is a
    #: per-voice field, so once two voices merge the individual values are
    #: gone -- and that averaging is a defect a listener caught. Keeping it on
    #: the zone lets the KRZ writer fit the K2000's own per-key resonance ramp
    #: across a fused layer instead of writing a scalar.
    #:
    #: DECLARED HERE RATHER THAN STAMPED AD HOC, because a runtime attribute
    #: read through `getattr(z, '_src_reson', 0.0)` returns the default
    #: forever if the name is ever misspelled, and nothing fails --
    #: `test_no_getattr_default_hides_a_misspelled_model_field` exists for
    #: exactly that and caught this on its first run.
    src_resonance: Optional[float] = None
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
    #: `Optional[float]`, NOT `float | None`. PEP 604 in a class body is
    #: evaluated at import time, so on the Python 3.8/3.9 the README still
    #: promises, `float | None` raises TypeError and the whole converter fails
    #: to start. Every other optional field in this file uses Optional[...] and
    #: this one did not -- caught by review, not by any test, because the
    #: interpreter here is 3.11.
    release_rate_db_per_s: Optional[float] = None

    #: The DECAY's slew rate in dB/s, when the source machine measured one.
    #:
    #: Added for a narrower reason than the release's: a decay to FULL SUSTAIN
    #: has nowhere to travel, so its seconds are 0 whatever the rate byte says,
    #: and the byte cannot be recovered from them. Measured across the AKAI
    #: sound libraries 2026-08-24, `amp_decay` changed on ~100% of
    #: round-tripped zones -- every one a full-sustain keygroup falling through
    #: to the writer's default. Every other sustain level round-tripped
    #: exactly.
    #:
    #: Inaudible while the sustain stays full, and wrong the moment anyone
    #: edits the sustain on the machine.
    #:
    #: **The E4B path deliberately ignores this.** Its decay runs peak ->
    #: sustain, both ends defined, so the seconds are sound there and a rate
    #: would be a second way of saying the same thing (§AKAIRELSPAN).
    decay_rate_db_per_s: Optional[float] = None


def _amp_env() -> Envelope:    # amplitude-envelope default
    return Envelope(0.001, 0.3, 0.8, 0.5)


def _filter_env() -> Envelope:  # filter-envelope default (attack 0, sustain full)
    return Envelope(0.0, 0.3, 1.0, 0.0)


#: SHAPE of a velocity->volume response, beside the scalar span that has always
#: been carried in `velocity_to_volume_db`. Added 2026-09-04 (§MPCVELSHAPE) after
#: an end-to-end check found the scalar alone to be **14 dB RMS wrong** on MPC
#: material: a single dB span describes a response completely only if that
#: response is STRAIGHT IN dB, and three of our four machines are while the
#: fourth is not.
#:
#:     AKAI    swing_dB = 1.19557 * V_LOUD, linear in velocity   (s3ked §171)
#:     K2000   0.27618 dB per velocity unit, r2 0.999996         (k2kremote)
#:     E4XT    0.75097 dB per velocity unit at 100 % amount      (eosed §83)
#:     MPC     gain = (1-s) + s*(v/127) in AMPLITUDE             (bench 2026-09-01)
#:
#: Jan's call, 2026-09-04: carry the shape rather than pick a better scalar, so
#: each writer decides what to do with it instead of the parser guessing on
#: everyone's behalf.
VELOCITY_CURVE_DB_LINEAR = 'db-linear'
VELOCITY_CURVE_AMPLITUDE_LINEAR = 'amplitude-linear'

#: Velocity range the dB-linear fit below is taken over. **This has NO effect on
#: a dB-linear source** -- that fit is exact over any range -- so it only ever
#: chooses how a curved source is approximated, and every existing AKAI, KRZ and
#: E4B conversion is unaffected by it.
#:
#: 32 rather than 1 because the MPC's curve is logarithmic: v1 sits 30 dB below
#: v32 and anchoring on it lets one inaudible extreme point set the slope for
#: the whole range. Measured over the MPC's own law at full sensitivity:
#:
#:     v1..127    swing 24.89   RMS 3.67   worst 21.17 dB
#:     v32..127   swing 14.97   RMS 0.58   worst  1.66 dB
#:     v64..127   swing 11.73   RMS 0.15   worst  0.38 dB
#:
#: v32 keeps the worst case under 2 dB while still covering everything a player
#: reaches. Going further up buys accuracy in a narrower band at the cost of the
#: soft end, which is where a curved response is most audible.
VELOCITY_FIT_RANGE = (32, 127)


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
    #: Filter cutoff in **HERTZ**.
    #:
    #: **This was a 0..1 POSITION on the E-MU's 57 Hz..20 kHz scale until
    #: 2026-08-25**, which made it one machine's parameter scale standing in
    #: for a physical quantity -- the third instance of that fault in two days,
    #: after the release span and the key-follow units, and it cost about the
    #: same share of the corpus as each of those.
    #:
    #: **The floor was the damage.** The position scale bottoms out at 57 Hz,
    #: so every AKAI corner below that collapsed onto one byte: FILFRQ under 28
    #: is **29.4% of the library corpus**, and `filter_freq` changed on up to
    #: **26% of zones on a single disc**, reading back as 28 whatever it was.
    #:
    #: Hz is what every machine's own law is measured in, so each writer now
    #: converts at the point of use and each parser stores what it actually
    #: knows. `hz_to_e4b_cutoff` remains for the E-MU byte, and
    #: `nominal_knob_to_hz` exists for the sources that only have a knob.
    #: **THE -3 dB CORNER, IN HZ.** "Hz" alone was the whole definition until
    #: 2026-09-02, and it is not enough: two machines can both report "cutoff
    #: in Hz" and mean different frequencies.
    #:
    #: Every source that fills this field measures a -3 dB corner --
    #: `akai_filfrq_to_hz` says so in its own docstring, §E4BFILTCAL read the
    #: E4XT's "-3 dB corner off the noise spectrum in 1/6-octave bands", and
    #: §MPCCUTOFF fitted a 2-pole response whose fc IS the -3 dB point (the
    #: MPC's resonance-0 response measures +0.15 dB, i.e. near-Butterworth).
    #:
    #: **THE K2000 DOES NOT.** Its displayed cutoff is f0, the section's
    #: NATURAL frequency: its 2-pole runs Q ~ 0.99 (unity gain at the label,
    #: -3 dB at 1.264*f0) and its 4-pole is two Butterworth sections at one f0
    #: (-6.11 dB at the label, -3 dB at 0.774*f0). See krz_cutoff_byte_to_hz.
    #: So a KRZ byte and an AKAI corner are NOT the same quantity, and the
    #: conversion between them is pending Jan's decision rather than applied.
    filter_cutoff: float = E4B_CUTOFF_MAX_HZ
    filter_resonance: float = 0.0  # 0.0-1.0
    #: Cents the FILTER ENVELOPE moves the corner at full envelope level.
    #: Signed. Cents since 2026-08-25 (SS_CENTS_DEPTHS) -- see the note on
    #: `e4xt_cents_to_cord_amount` for why no cents-per-cord constant is
    #: right for the E4XT, and why this converts through the corner instead.
    filter_env_cents: float = 0.0
    # Tuning
    non_transpose: bool = False  # vpar[38]=1 in E4B: pitch does not follow key
    # Filter modulation (EOS mod cords into Filter-Freq; -1.0..+1.0 = ±100%)
    #: Key -> Filter tracking, in OCTAVES OF CUTOFF PER OCTAVE OF KEY.
    #:
    #: **This was an EOS CORD AMOUNT until 2026-08-24** -- a fraction of one
    #: machine's cord, whose full scale is 0.713 oct/oct. So any source asking
    #: for more than that saturated at -1..+1 and the value was gone. The AKAI
    #: uses 1:1 tracking on 27% of its keygroups and goes past 2.5 oct/oct in
    #: real material; measured over the sound libraries, key-follow was lost on
    #: **32.6% of round-tripped zones**, and widening the AKAI's own clamp only
    #: moved it to 31.3% because the loss was happening HERE, not there.
    #:
    #: Same defect as the release span and the same fix: carry the physical
    #: quantity, convert at the point of use. `key_track_to_filter_amount`
    #: turns it into an EOS cord amount where one is wanted.
    filter_keytrack: float = 0.0     # oct of cutoff per oct of key
    # VELOCITY -> FILTER IS A RANGE, NOT A DEPTH.
    #
    # `velocity_to_filter_cents` is the depth reached at FULL velocity. The floor the
    # modulation starts from is `velocity_to_filter_min_cents`, and the two together
    # are what a source actually specifies:
    #
    #   K2000 Src2:  (MinDpt, MaxDpt)      e.g. (0, +10800 ct)
    #   K2000 Src1:  (0, Depth)            a single depth is the same shape
    #
    # CARRYING ONLY THE DEPTH LOSES THE POLARITY. `(0, +10800)` only ever OPENS
    # the filter; `(-5400, +5400)` closes it as much as it opens. Both collapse
    # to the same scalar, and they are different patches. A converter that
    # re-centres a unipolar sweep on a bipolar destination drives the corner
    # BELOW a floor the source never crosses -- which on a cymbal is silence,
    # found on hardware 2026-08-17 (see RESOLUTION_NOTES.md AKAIVELFILT).
    #
    # UNITS: CENTS, since 2026-08-25 (SS_CENTS_DEPTHS). Both used to be
    # fractions -- of 10800 cents on the way in from a K2000 and of
    # VEL_FILTER_FULL_CENTS on the way in from an SFZ, which are two different
    # definitions of 1.0 for one quantity. Cents is what every source states
    # and what no machine has to agree about.
    #: Cents the corner moves at FULL velocity. Signed: negative darkens.
    velocity_to_filter_cents: float = 0.0
    #: Cents the corner moves at ZERO velocity. 0 = unipolar sweep from the
    #: voice's own cutoff, which is what a single-depth source means.
    velocity_to_filter_min_cents: float = 0.0
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
    #: PAN MODULATION. Bipolar, -1.0..+1.0, 0.0 = no modulation. SIGNED
    #: DELIBERATELY: pan is left-and-right, so an unsigned path would lose half
    #: the parameter space in the one place it obviously matters -- and
    #: §KRZLFOSIGN is the cautionary case, where a `> 0.0` gate silently dropped
    #: every negative LFO→pitch depth.
    #:
    #: All four formats in the matrix carry pan modulation and NONE of it was
    #: read or written before 2026-09-06 (§PANMOD):
    #:   MPC   <LfoPan>, <VelocityToPan>            per keygroup
    #:   AKAI  MODSPAN1/2/3 + MODVPAN1/2/3, ±50     LFO2 = source 8
    #:   E4XT  PatchCord destination 0x41 AmpPan    hardware-confirmed
    #:   K2000 PANNER Adjust/KeyTrk/VelTrk/Src1/Src2, algorithms 2/13/24/26
    lfo1_to_pan: float = 0.0         # LFO1 → Pan
    lfo2_to_pan: float = 0.0         # LFO2 → Pan
    velocity_to_pan: float = 0.0     # Velocity → Pan
    key_to_pan: float = 0.0          # Key position → Pan (K2000 KeyTrk, AKAI Key>pan)
    #: VELOCITY -> AMPLITUDE, as the full-scale swing in dB from velocity 1 to
    #: 127. Positive means harder is louder; 0.0 means no velocity dependence
    #: at all, which is a real neutral rather than a stand-in (measured).
    #:
    #: Added 2026-09-01 (§KRZAMPVEL / s3ked §171) because BOTH sides of the
    #: AKAI<->K2000 path were inventing this rather than carrying it: the AKAI
    #: writer hardcoded `p[0x1a] = 20` while the reader never read offset 0x1a
    #: at all, and the K2000 writer inherited 35 dB from the #199 template it
    #: clones, never setting the field deliberately. Real source material
    #: varies -- 20/20/25/25/30/36 across six programs on one disc.
    #:
    #: NOMINAL, NOT NECESSARILY REALISED -- and this is the property to check
    #: before wiring any NEW target (s3ked, 2026-09-01). The number states what
    #: the source ASKED FOR; what a machine actually produces is that swing
    #: clamped against its own ceiling. On the AKAI that ceiling is a GAIN
    #: ceiling and therefore SAMPLE-DEPENDENT (s3ked 2026-09-04: two samples
    #: froze 5.47 dB apart, crest factor unmoved), so there is no single dBFS
    #: number to subtract -- preset 6's 43.04 dB needs more headroom above its
    #: own v64 level than a quiet program has, and how much depends on what is
    #: loaded. **Some real source values are therefore partly unrealised on the
    #: source machine itself**, by an amount that is a property of the material.
    #:
    #: An earlier version of this comment named "-25.6 dBFS" as the ceiling and
    #: computed a fixed 21.5 dB from it. That arithmetic only works for an
    #: ABSOLUTE ceiling, which the 5.47 dB spread between samples rules out.
    #:
    #: For AKAI->AKAI that is harmless and carrying the number is exactly
    #: right: the destination clips it the same way the source did, so
    #: byte-for-byte fidelity is the correct target. **It bites on a target
    #: whose headroom differs** -- the same nominal number would then produce a
    #: LARGER actual swing than the original ever made. So a new writer must
    #: compare what each machine actually produces at v1 and v127, not nominal
    #: dB against nominal dB, which needs that machine's own ceiling and pivot
    #: measured rather than just its scaling law.
    #:
    #: A SWING rather than a slope, and about a PIVOT rather than from silence:
    #: on the AKAI the response rotates about velocity 64 (measured -- the
    #: level at v64 does not move as the field changes), the same pivot
    #: `K_FREQ` uses for key-follow. Machines that pivot elsewhere convert
    #: through their own law; the swing is the quantity both can state.
    #: **THE PIVOT IS PART OF THE QUANTITY, and the field carried a swing
    #: without one until 2026-09-01.** A swing in dB says how far the response
    #: moves between velocity 1 and 127; it does not say about WHICH velocity
    #: it rotates, and the machines genuinely disagree:
    #:
    #:     AKAI S3000XL   pivot 64    (V_LOUD, V_ENV2 and K_FREQ all measured
    #:                                 at 64 -- a machine-wide convention)
    #:     Kurzweil K2000 pivot 127   (AMP VelTrk attenuates downward from the
    #:                                 loudest note; nothing gets louder)
    #:     E-MU E4XT      pivot 0, 89.4 or 127, depending on the SOURCE chosen
    #:                                 (Vel+, Vel~, Vel< -- and Vel~ is NOT 64
    #:                                 despite its name)
    #:
    #: Filling this field from two of those readers without recording which
    #: convention produced it would make a pivot-127 swing and a pivot-64 swing
    #: interchangeable under one name -- the same class of defect as
    #: §KRZENVLOOP, where a plausible reading went unchallenged for two months.
    #: So the pivot travels WITH the swing, and neither is meaningful alone.
    #:
    #: `None` means NOT READ -- distinct from 0.0, which means measured and
    #: genuinely neutral. The AKAI reader can state the difference (V_LOUD 0 is
    #: neutral to 0.00001 dB/unit); a reader that never looked cannot, and a
    #: writer choosing a default needs to tell those apart.
    velocity_to_volume_db: Optional[float] = None
    #: Velocity at which `velocity_to_volume_db` has no effect. Set together
    #: with the swing or not at all.
    velocity_to_volume_pivot: Optional[int] = None
    #: SHAPE of that response: VELOCITY_CURVE_DB_LINEAR (the default, and what
    #: AKAI/K2000/E4XT all measure as) or VELOCITY_CURVE_AMPLITUDE_LINEAR (the
    #: MPC). The span above describes a response completely only for the first
    #: kind; see §MPCVELSHAPE for the 14 dB RMS this was worth on MPC material.
    velocity_to_volume_curve: str = VELOCITY_CURVE_DB_LINEAR
    #: THIRD STATE: the source asks for a velocity->volume response but states
    #: no amount this project can convert to dB yet. MPC's `VelocitySensitivity`
    #: is the case that forced it -- the field is present in every keygroup,
    #: 0.0 unambiguously means "none" whatever the law turns out to be, but a
    #: non-zero value has no measured dB law behind it until the MPC One is
    #: put on the bench.
    #:
    #: Three states, not two, because "no field at all" and "a field asking
    #: for something we cannot yet quantify" call for opposite defaults:
    #:
    #:     db=None, requested=False  -> nothing is known    -> write no cord
    #:     db=None, requested=True   -> wants some, unscaled -> keep the
    #:                                  target's own default rather than
    #:                                  silencing a response the source asked
    #:                                  for
    #:     db=<value>                -> known               -> write it
    #:
    #: Collapsing the middle case into either neighbour is wrong in an audible
    #: direction: into the first it flattens 65.8 % of MPC presets, into the
    #: third it invents a constant.
    velocity_to_volume_requested: bool = False
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


#: K2000 `F2 RES KeyTrk`: resonance as a function of key.
#:
#:     resonance(key) = Adjust + KRZ_RES_KEYTRK_DB_PER_KEY * KeyTrk * (key - 60)
#:
#: MEASURED (k2kremote, 2026-09-01, §KRZRESKEYTRK) on a purpose-built rig and
#: answering all four of the questions this project now asks of any displayed
#: unit:
#:
#:   PIVOT  = key 60 (middle C). Measured independently at two settings, 59.2
#:            and 59.8. NOT the endpoint pivot the amp's VelTrk uses (127), so
#:            the machine is not internally consistent about this and neither
#:            reading may be assumed from the other.
#:   LINEAR in key (r2 0.9989 and 1.0000) AND in the setting -- KeyTrk 0.04 and
#:            0.10 give the same gradient -- so one number characterises it.
#:   UNIT   = literal. The displayed dB/key is dB/key, gradient 1.010 and 1.009
#:            about the pivot, within 1 % of unity.
#:   ZERO   = genuinely neutral. Flat to 0.00 dB across six octaves, not a
#:            smallest-available value.
#:
#: Rig, because the first attempt was built on a real converted program and had
#: to be discarded: ROM #199 edit buffer, one layer, ALG 5, keymap 163 Sine
#: Wave with BOTH keymap and PITCH KeyTrk at 0 so pitch is frozen at 262 Hz and
#: the source cannot move with the key, corner parked on it, F1
#: KeyTrk/Depth/VelTrk 0, AMP VelTrk 0. Control: level spread 0.00 dB across
#: six octaves at crest 3.03 against a clean sine's 3.01.
#:
#: **CORRECTION 2026-09-02: the F3 block was NEVER switched off, here or in
#: §40/§42, and this note claimed it was.** Pressing the `F3` soft key
#: NAVIGATES to that block's page; it does not change the block's TYPE, which
#: lives on the ALG page. ROM #199 defaults F3 to **BAND2** under algorithm 5,
#: so a bandpass sat in series with the filter under test for every one of
#: those runs.
#:
#: **THE LAW ABOVE SURVIVES, and the reason is a MEASUREMENT, not an
#: argument.** The tempting justification -- "a fixed stage in series
#: contributes the same offset at every key, so it divides out of a gradient"
#: -- is valid but rests on a premise nobody checked: that BAND2 *was* fixed.
#: A bandpass has its own block parameters, and `F3 SEP` on the 4-pole turned
#: out to carry its own `KeyTrk`/`VelTrk`. Had BAND2's centre tracked the key,
#: its contribution would have varied with key, and **that failure would be
#: invisible in every fit because it would look exactly like resonance
#: keytracking.**
#:
#: What actually clears it is §40's control run -- KeyTrk 0, keys 24-96,
#: **level spread 0.00 dB across six octaves**. If BAND2's contribution had
#: moved with key by any amount, that spread could not have been 0.00. So the
#: stage was empirically key-independent on that rig whatever its parameters
#: were. A control run for an unrelated purpose turns out to be exactly the
#: test that excludes the confound.
#:
#: (Stronger still: the level->equivalent-resonance calibration curve was
#: measured through BAND2 as well, so the constant gain cancels in the mapping
#: before the difference is even taken.)
#:
#: A rogue stage IS fatal to an ABSOLUTE corner measurement, and was -- it is
#: what forced the 2026-09-02 K2000 corner run to be redone.
#:
#: **Do not describe the §40/§42 rigs as having F3 off.** They had BAND2 in
#: circuit and the results survive anyway, for the reason above. That is a
#: different and more honest claim than the original write-up made.
#:
#: **The fix is Jan's, and it generalises: verify by SysEx, not by reading the
#: screen.** A DUMP-diff of two saved copies isolates the F3 block type to
#: **program-object offset 241** (`BAND2 = 35`, `NONE = 60`), one byte apart --
#: and 60 matches `krz_writer`'s own `f3_byte` constant, derived independently.
#: Assert `byte@241 == 60` before capturing; do not parse the ALG row, and do
#: not trust a soft key to have changed what its label suggests.
#: CONFIRMED IDENTICAL ON THE 4-POLE (2026-09-01): gradient 1.052 / 1.020 and
#: pivot 59.0 / 59.5 at two settings, byte 228 encoding unchanged (1.00 ->
#: 50). **And the manual explains WHY, which is a better footing than two
#: matching numbers:** "Four-pole Lowpass Filter with Separation ... combines
#: 2POLE LOWPASS and LOPAS2 in one three-stage function ... **F2 RES affects
#: the resonance of 2POLE LOWPASS**." The 4-pole's resonance stage IS the
#: 2-pole's, with a second lowpass cascaded after it, so the law is shared
#: structurally rather than coincidentally.
#:
#: **SCOPE: `2POLE LOWPASS` and `4POLE LOPASS W/SEP` only.** Algorithm 1 alone
#: offers HIFREQ STIMULATOR, PARAMETRIC EQ, STEEP RESONANT BASS, 4POLE HIPASS
#: W/SEP, TWIN PEAKS BANDPASS and DOUBLE NOTCH W/SEP; none is measured, and
#: the 4-pole result transfers ONLY because the manual says the stage is
#: shared. Do not assume the highpass or bandpass follow without the check.
#:
#: A TRAP AVOIDED, worth carrying to any filter work: the plan for the 4-pole
#: run was to "switch F3 off" as a confound, as on the 2-pole. **On a 4-pole
#: F3 is not a spare slot -- it is the filter's own SEP stage**, and disabling
#: it would have dismantled the thing being measured. `F3 SEP` also carries
#: its OWN KeyTrk/VelTrk, so a non-zero SEP KeyTrk moves the second lowpass's
#: corner with key -- exactly the confound the rig exists to exclude -- and
#: nothing on the F2 RES page would reveal it. (Also: the manual prints that
#: page's first field as `Adjust:0ct`; the machine shows `Coarse:0ct`. The
#: manual is authoritative on structure, not always on labels.)
KRZ_RES_KEYTRK_DB_PER_KEY = 1.010

#: Byte encoding for F2 RES KeyTrk: 0.02 dB/key per unit, signed, measured by
#: DUMP-diff at three settings including a 10x check (+1.00 dB/key -> byte 50),
#: so the scale is confirmed linear rather than fitted through two points.
KRZ_RES_KEYTRK_DB_PER_UNIT = 0.02
KRZ_RES_KEYTRK_PIVOT_KEY = 60

#: K2000 resonance -> OUTPUT LEVEL saturates, and the reference preset already sits past the
#: knee. Level tracks `Adjust` at 1.00 dB/dB from 0 to 6 dB, then flattens:
#: 6->12 dB of resonance buys only 1.4 dB of level, and 12->24 almost nothing.
#: Measured alongside the KeyTrk law. **Do not predict audibility from a
#: resonance delta** -- the reference preset's layers sit at 19 and 14 dB, well inside the
#: saturated region, so a several-dB resonance change there moves the output
#: far less than its dB value suggests.
KRZ_RES_LEVEL_LINEAR_MAX_DB = 6.0


#: K2000 `F4 AMP` modulation section: LFO -> amplitude (tremolo).
#:
#: `Src1` at byte offset 262 selects the modulation source (OFF = 0,
#: LFO1 = 114); `Depth` at 263 is its amount, signed i8.
#:
#: MEASURED (k2kremote, 2026-09-01, §KRZF4AMPDEPTH) by DUMP-diff plus captured
#: swing. Two points are worth keeping attached to the number:
#:
#:   UNIT   = 1.0 dB per unit. This was NOT derivable and must not be inferred
#:            from its neighbours: `F2 RES KeyTrk`, on the same panel two pages
#:            over, is 0.02 dB per unit. Same container, same edit buffer, two
#:            orders of magnitude apart. Extrapolating the resonance scale here
#:            would have written every tremolo 50x too shallow -- silent rather
#:            than wrong, which is the failure mode that gets misread as "the
#:            feature does not work".
#:   RAILS  = +/-96 on the panel, NOT the +/-127 the signed byte would hold.
#:            Third measured rail this week narrower than its own container
#:            (keymap `VolumeAdjust` +/-63.5 not +/-64.0, `F2 RES KeyTrk`
#:            +/-100, this one +/-96). "Signed i8" is not a range on this
#:            machine; clamp to the measured rail, never to the byte.
#:
#: The adjacency of Src1/Depth was correctly guessed here before the run; the
#: absolute offsets and the scale were not. Recorded because the guess being
#: half-right is exactly what makes this class of inference dangerous.
#:
#: **DIRECTION, MEASURED (k2kremote, same day): the swing is BIPOLAR about the
#: un-modulated level, and `Depth` is the ONE-SIDED amplitude in dB.** At
#: Depth 12 the peak read +12.08 dB and the trough -11.51 dB; at Depth 24,
#: +23.85 and -22.52. So peak-to-peak is 2x Depth, and **writing depth D costs
#: the full D dB of headroom above nominal** -- not D/2, and not zero. A zone
#: sitting within D dB of full scale will clip on every tremolo peak. Budget
#: for it at write time.
#: **NOT exactly +/-D, and the first explanation for that was wrong.** The
#: shallow troughs were initially put down to the bench noise floor. Tested
#: 2026-09-01 at two gains 8 dB apart, and they are not:
#:
#:     Adjust   peak-nom   trough-nom   centre   half-swing   trough headroom
#:      -24.0    +24.46      -21.53      +1.46      23.00         9.68 dB
#:      -16.0    +24.48      -21.05      +1.72      22.77        18.17 dB
#:
#: The trough moved 0.48 dB while its headroom over the floor nearly DOUBLED;
#: if the floor were responsible the gap would have closed. Floor-correcting
#: the power still leaves it ~2.5 dB short of -24. And the peak is identical
#: at both gains to 0.01 dB, which rules out compression at the top -- the
#: louder run had 5.21 dB of peak headroom and read the same as the quiet one
#: with 13.12 dB.
#:
#: So the modulation CENTRE sits slightly ABOVE nominal, by an amount that
#: grows with depth (+0.29 at D=12, +1.47 at D=24), and the half-swing is
#: ~0.96-0.98 x D. No mechanism is offered from two depths and none should be
#: invented; nothing currently depends on it.
#:
#: **This does not change the write-side rule.** The headroom cost is the
#: PEAK, which is >= D (+12.08 at D=12, +24.47 at D=24), so "budget the full
#: Depth above nominal" stands and is if anything slightly conservative. What
#: it changes is that the swing must NOT be recorded as exactly symmetric --
#: +/-D is the setting's nominal meaning, not a measured device fact.
#:
#: (s3ked's AKAI, by contrast, tracked the MEDIAN across five depths and saw
#: 0.42 dB of drift over a 0->49 dB swing, which is strong evidence that
#: machine IS symmetric. So the two differ here after all -- and median
#: tracking is the better proof, being insensitive to exactly the endpoint
#: effects that caught the K2000 measurement out.)
#:
#: Worth keeping as method: "probably my noise floor" was a HYPOTHESIS
#: attached to sound data, hedged, recorded here WITH the hedge, and wrong.
#: The hedge is what made it cheap -- it was visibly unproven, and closing it
#: took one run. The same caveat asserted would now be a false constant.
#: Rig: ROM #199 at its DEFAULT algorithm, PITCH / NONE / AMP -- F1/F2/F3 all
#: off, so no filter anywhere to colour an amplitude reading -- sine keymap
#: 163, LFO1 at its default 2.00 Hz, ~4.5 cycles in the window. Linearity was
#: verified BEFORE the sweep (Adjust -18 -> -24 gave -5.95 dB against -6.0),
#: because a clipped peak would have read as "down only" whatever the truth
#: was.
#:
#: This corrected the docstring of `lfo_volume_depth_to_amount`, which had
#: claimed "always positive ... swings symmetrically down" since 2026-07-28 --
#: wrong in both halves, and the truth is the more expensive of the two
#: readings. It also corrected k2kremote's own classifier, which printed
#: "UP ONLY" because it tested the peak against D and never checked whether
#: the trough had stayed at nominal. The numbers were right and the label on
#: top of them was wrong -- the same failure as the byte-detector's empty
#: summary earlier that day, and worth remembering as a class: a derived
#: verdict can fail while every input to it is sound.
#:
#: POSITION. k2kremote reported absolute program-object offsets 262 and 263.
#: OUR layout is 24 bytes shorter before the layer block (`_TPL_GLOBAL` omits
#: four zero-bodied segments between PGM and FX), so those are indices 5 and 6
#: of HOB segment 0x53 -- and that is not merely arithmetic:
#:   * The four HOB segments share ONE parameter layout, and index 5 = Src1,
#:     index 6 = Depth is already what this project reads and writes for F1
#:     (`hob_f1[5] = _K2_CS_ENV2`, `hob_f1[6] = depth`).
#:   * Corpus check over 21,355 real F4 segments: byte 5 draws from the SAME
#:     control-source enumeration as F1 byte 5 -- 114 appears in both -- and
#:     `_K2_CS_LFO1 = 114` was already in this codebase from independent RE,
#:     matching the measured value with nothing shared between the two
#:     derivations.
#:   * LFO1 -> AMP is genuinely RARE in the wild: 10 of 21,355 layers (0.05%),
#:     depths 2..10. Reading it correctly changes almost nothing; the value is
#:     in not silently discarding the ones that have it.
KRZ_F4_AMP_SEG_TAG = 0x53
KRZ_F4_AMP_SRC1_INDEX = 5
KRZ_F4_AMP_DEPTH_INDEX = 6
KRZ_F4_AMP_SRC_OFF = 0
KRZ_F4_AMP_SRC_LFO1 = 114
KRZ_F4_AMP_DEPTH_DB_PER_UNIT = 1.0
KRZ_F4_AMP_DEPTH_CLAMP = 96

#: K2000 `F4 AMP Adjust`, HOB segment 0x53 index 1: the layer's static level
#: in dB, 1 dB per unit. MEASURED as a by-product of the tremolo work --
#: k2kremote's linearity control set Adjust -18 -> -24 and the capture moved
#: **-5.95 dB against -6.0 asked**, and the two-gain symmetry run set -24 and
#: -16 and saw the levels 8 dB apart as set. That control existed to prove the
#: signal path was linear before the depth sweep; it doubles as a calibration
#: of this field.
#:
#: This is the byte the tremolo's HEADROOM TRIM moves. ROM #199 leaves it at
#: +6 dB, so a converted layer starts 6 dB up before any trim.
#:
#: RAIL UNMEASURED. Depth's panel rail is +/-96 and this uses the same clamp
#: as a conservative proxy -- an inference, not a measurement, and flagged as
#: such because three K2000 rails this week turned out narrower than their
#: containers. Real trims land in -90..+6, well inside any plausible rail.
KRZ_F4_AMP_ADJUST_INDEX = 1
KRZ_F4_AMP_ADJUST_DB_PER_UNIT = 1.0
KRZ_F4_AMP_SRC_LFO2 = 116


#: AKAI S3000XL LFO1 -> LOUDNESS (tremolo). Loudness is a mod-matrix
#: destination with three slots: sources in program bytes MODSAMP1/2/3
#: (79/80/88), amounts in program MODVAMP1/2 (92/93) and keygroup MODVAMP3
#: (155). LFO1 is source value 7.
#:
#: MEASURED (s3ked, 2026-09-01, their §172) on white noise with a flat sustain
#: and every other route zeroed, five amounts, each verified clear of BOTH
#: rails:
#:
#:     peak-to-peak swing_dB = 1.94340 * amount + 0.967    r2 = 0.9993764
#:     => one-sided amplitude = 0.9717 dB per unit of amount
#:
#: DIRECTION: symmetric about the zone level, proved by the MEDIAN rather than
#: by peak and trough separately -- downward-only modulation would drag the
#: median down as depth rises, and it moved 0.42 dB while the swing went from
#: 0 to 49 dB. Sign inverts phase without changing size (|+25| 49.12 dB
#: against |-25| 48.14).
#:
#: **THE TWO MACHINES AGREE TO 3 %, AND THAT IS THE HEADLINE.** The AKAI's
#: amount is the ONE-SIDED amplitude in dB at 0.9717 dB/unit; the K2000's F4
#: AMP `Depth` is the one-sided amplitude at 1.0 dB/unit. Two different
#: machines, two agents, two rigs, two months of unrelated RE -- so an AKAI
#: tremolo maps onto a K2000 one at very nearly 1:1, and the AKAI's +/-50
#: panel range (+/-48.6 dB one-sided) sits inside the K2000's +/-96 rails with
#: room to spare. Contrast the velocity->amplitude story, where the same two
#: machines pivot at 64 and at 127 and nothing transfers.
#:
#: HEADROOM: writing amount A costs the FULL 0.9717*A dB above nominal, not
#: half of it. Both peers independently phrased this as "D/2", which is true
#: only when D means the peak-to-peak SWING and false when D means the amount
#: -- the quantity a writer actually clamps on. Budget on the one-sided value.
#:
#: RAILS -- and this one runs OPPOSITE to the three K2000 rails above. The
#: device does not clamp at all over SysEx: MODVAMP1 written -128..+127 reads
#: back verbatim, and MODSAMP1 accepts 15, 20 and 255, which are not valid
#: sources. So here the CONTAINER is the rail and the +/-50 is a panel or spec
#: limit the machine does not enforce. Whether it ACTS sensibly on an invalid
#: source is a separate question nobody has asked. Clamp in the writer; the
#: machine will not do it for us.
#:
#: **THE LAW IS A PRODUCT, NOT A PER-UNIT CONSTANT** (s3ked, 2026-09-01,
#: second run). `LFODEP` and the destination amount MULTIPLY, as §160 already
#: found for pitch. Established by equal-product equivalence, which is the
#: sharp test -- linearity in each variable separately would not have shown it:
#:
#:     depth 99 x amount 20 = 1980  ->  39.98 dB peak-to-peak
#:     depth 50 x amount 40 = 2000  ->  39.80 dB
#:     depth 40 x amount 50 = 2000  ->  39.90 dB
#:     spread 0.17 dB across a 2.5x range of EACH variable
#:
#: Joint fit through the origin, 12 points from three runs, max residual
#: 0.74 dB (3.6 % of value):
#:
#:     one_sided_dB = 0.010068 * LFODEP * amount
#:
#: THE EARLIER 0.9717 dB/unit FIGURE IS SUPERSEDED. It was a single-depth
#: slice at LFODEP 99; the joint fit gives 0.9968 dB/unit there, 2.6 % away,
#: with three times the leverage. **And the corrected value lands within a
#: third of a percent of the K2000's 1.0 dB/unit** -- see
#: KRZ_F4_AMP_DEPTH_DB_PER_UNIT. Two machines, two rigs, nothing shared.
#:
#: WHAT TREATING IT AS A FLAT CONSTANT WOULD HAVE COST, since this was very
#: nearly shipped as one:
#:
#:     LFODEP 99 -> over-reads by 1.00x      LFODEP 25 -> 3.96x  (+18.0 dB)
#:     LFODEP 50 ->               1.98x      LFODEP 10 -> 9.90x  (+21.8 dB)
#:
#: A program at LFODEP 10 would have had its tremolo read TEN TIMES too deep,
#: arriving with the authority of a measured constant.
#:
#: **THE COLLAPSE TO A K2000 `Depth` IS LOSSY AND NOT MERELY "DIFFERENT".**
#: The K2000 has no second multiplier, so AKAI->KRZ must fold the product into
#: one number. That is fine for playback and NOT invertible -- a round trip
#: cannot recover which factor held the magnitude. It is worse than it looks,
#: because the two factors are not interchangeable: **`LFODEP` is
#: PROGRAM-WIDE** and also feeds LFO1's other destinations (pitch via
#: `L_PTCH`, the same product form again), while **`amount` is specific to
#: loudness**. So normalising `LFODEP` and pushing the magnitude into the
#: amount silently rescales the VIBRATO, and doing the reverse rescales the
#: tremolo. On a patch using both there is no single correct collapse. Do not
#: write an AKAI tremolo writer that "normalises" either factor without
#: deciding, explicitly, which modulation is allowed to move.
AKAI_LFO_LOUDNESS_DB_PER_PRODUCT = 0.010068
AKAI_MODSAMP_OFFSETS = (79, 80, 88)
AKAI_MODVAMP_PROG_OFFSETS = (92, 93)
AKAI_MODVAMP3_KG_OFFSET = 155
AKAI_MOD_SOURCE_LFO1 = 7
AKAI_MODVAMP_PANEL_RAIL = 50


#: E4XT velocity -> AmpVol mod cord: dB of swing per PERCENT of cord amount.
#:
#: MEASURED (eosed, 2026-09-01, their §83) on a single-voice single-zone
#: preset, note 48, nine velocities, four cord amounts:
#:
#:     amount%   0.00   23.62   50.39   100.00
#:     dB/unit   ~0     0.1775  0.3790  0.7511
#:     per 1 %   --     0.9470  0.9477  0.9464     <- agree to +/-0.07 %
#:
#:     swing_dB(v1 -> v127) = 0.9470 * amount_percent          (94.7 dB at 100 %)
#:     attenuation_dB(v)    = 0.9470 * amount_percent * (127 - v) / 126
#:
#: Linear in velocity (r2 0.9997+) AND in the setting. Amount 0 is genuinely
#: neutral -- 0.01 dB across the whole velocity range -- which also proves
#: this cord is the ONLY velocity->volume path in the voice, so nothing else
#: has to be accounted for.
#: REFITTED 2026-09-01 (eosed, after this project queried a 0.8 % discrepancy
#: between two statements of the law). The primitive is per VELOCITY UNIT,
#: which has no denominator to argue about -- it is what a straight-line fit
#: of level against velocity returns:
#:
#:     0.75097 dB per velocity unit at 100 % cord amount
#:     sd 0.02288, 95 % CI +/-0.01088, n = 17
#:     (three sources, five amounts, three headroom settings, each divided by
#:      its own TRUE amount -- stored byte / 127 -- not the value asked for)
#:
#: from which both swings derive, and the two differ by 0.75 dB:
#:
#:     v1..v127  (126 steps) = 94.62 dB   what a player can actually reach
#:     v0..v127  (127 units) = 95.37 dB   the machine's applied range
#:
#: **This project's field is a v1..v127 swing, so 126 is the right divisor
#: here** -- MIDI has no note-on at velocity 0 (that is a note-off), so 127 is
#: right about the machine and 126 is right about anything playable. The rule
#: eosed drew from it is worth more than the number: **state a measured law in
#: the units it was measured in.** "Full swing" is a derived summary and cannot
#: be quoted without saying across what -- a summary that reads as a
#: measurement, which is the same family as the other four faults of that day.
#:
#: Superseded 0.9470 (n=3). The two differ by 0.08 %, i.e. nothing audible;
#: the point is provenance, not the value.
E4XT_VEL_AMPVOL_DB_PER_PERCENT = 0.9462
E4XT_VEL_AMPVOL_DB_PER_VELOCITY_UNIT_AT_FULL = 0.75097

#: PIVOTS, measured in the same run at +10 and -10 against an amount-0
#: control. **`Vel~` does not pivot mid-scale**, which is the finding that
#: broke the plan built on its name:
#:
#:     Vel+   pivot velocity   0     (as named)
#:     Vel~   pivot velocity  89.4   (NOT 64)
#:     Vel<   pivot velocity 127     (as named)
#:
#: `Vel~`'s span at a given amount is the same ~9.5 dB as the unipolar
#: sources rather than twice it, so it is not `2*Vel+ - 1` either.
#:
#: **THE MANUAL DISAGREES ABOUT `Vel~`, AND ONLY ABOUT `Vel~`** (Jan, EOS 4.0
#: Software Manual p.351, 2026-09-01). The polarity figure maps the control
#: value 0..127 onto each source's applied range:
#:
#:     +   0..127  ->    0 .. +127     zero effect at control 0     -> pivot 0
#:     ~   0..127  ->  -63 ..  +64     zero effect at control 63    -> pivot 63
#:     <   0..127  -> -127 ..    0     zero effect at control 127   -> pivot 127
#:
#: `+` and `<` match the measurement exactly. `~` is predicted at **63** and
#: was measured at **89.4** -- a 26-unit disagreement on one source of three.
#:
#: **The manual also EXPLAINS the span, which the measurement could not.**
#: eosed found `Vel~`'s span equal to the unipolar sources' rather than double,
#: and had no account of it; the figure shows why -- all three ranges are 127
#: units wide, `~` merely straddles zero. So the manual corroborates the
#: measurement on span and conflicts with it on pivot, which isolates the
#: pivot as the anomaly rather than leaving the whole `Vel~` reading in doubt.
#:
#: **RESOLVED IN FAVOUR OF THE MEASUREMENT (eosed §85, 2026-09-01). The
#: prediction of 63 was mine and it failed.** Re-measured 12 ways -- two
#: destinations (AmpVol, FilFreq), two presets, two observables (level,
#: spectral centroid), three headroom settings, three amount magnitudes --
#: giving crossings from 87.1 to 94.0. Pooled: **mean 89.66, sd 1.79, 95 % CI
#: +/-1.01**, the two destinations agreeing within the scatter (AmpVol 89.92
#: n=10, FilFreq 88.35 n=2). The manual's 63 is 26.7 units away -- about **51
#: standard errors**. That forecloses a category of follow-up rather than
#: merely settling a number: no further measurement ON THIS MACHINE can move
#: it, so the firmware test is not one option among several, it is the only
#: one left. The two artefacts that
#: can displace a midpoint were excluded by construction rather than by
#: argument:
#:
#:   * A FIXED INSERTION LOSS when the cord is active looks exactly like a
#:     shifted pivot at one amount and separates at another. It would have put
#:     the +/-5 crossing near velocity 117; it is at 88.86. The crossing is
#:     invariant across a 5x change of amount.
#:   * A CEILING would move the crossing as the voice is attenuated. ~15 dB
#:     more headroom moved nothing, and no capture clipped.
#:
#: And the displacement tracks the amount in BOTH sign and magnitude, which is
#: the definition of a pivot -- a sign-independent offset would have put the
#: -10 crossing at velocity 36, not 88.9. That was already derivable from the
#: original §83 data.
#:
#: **The manual is confirmed on the span and wrong only about the zero.** Spans
#: scale 1:2:5 exactly with amount, and `Vel~` carries the identical constant
#: to `Vel<` -- 0.9456 dB/% against 0.9470. So "all three ranges are 127 units
#: wide" is right; only where `~` sits inside its range is not.
#:
#: **Most likely a FIRMWARE difference, and not testable on one machine.** The
#: figure is from the EOS **4.0** manual; the bench machine runs EOS **4.70**.
#: A source's zero point moving between revisions fits every measurement here.
#: Anyone with E4-series hardware on another revision settles it in one
#: capture. Recorded this way deliberately rather than as "the machine
#: contradicts its own documentation", because the document may simply
#: describe an older machine.
#:
#: No mechanism is offered for 89.6. It is 0.70 of full scale; that is recorded
#: as numerology, not as a finding, in case a 0.70 turns up elsewhere.
#:
#: WHAT THIS COST: nothing, because nothing was built on it -- the writer's
#: template uses `Vel<` and no local E4B routes `Vel~` into AmpVol. The lesson
#: is the cheaper one: a source named for the middle that is NOT in the middle
#: is exactly what gets assumed once and never rechecked, and the wrong
#: assumption would have come from a document correct about everything else on
#: its page. Checked against
#: the obvious artefact: a ceiling compressing the gain half would push the
#: +10 crossing later and the -10 crossing earlier, so the two would diverge;
#: they agree to one velocity unit on all three sources, and nothing clipped
#: in any capture.
#:
#: **CONSEQUENCE FOR THE WRITER: no E4XT source pivots at 64**, so an AKAI
#: swing (which rotates about velocity 64, s3ked §171) cannot be carried by
#: choosing a source. It has to be CONSTRUCTED:
#:
#:     Vel+ at amount A           -> swing S = 0.9470 * A, pivoting at v0
#:     + static volume trim -S/2  -> moves the pivot to velocity 64
#:
#: Two hazards in that construction, both real:
#:   1. **The trim must NOT be written as dB.** `E4_GEN_VOLUME` is specified in
#:      dB and is not: asked -12, the capture moved -8.86 dB (0.03 dB spread
#:      over nine velocities, so the edit path is live and repeatable and the
#:      LABEL is what is wrong). This independently confirms
#:      `e4xt_byte_to_volume_db`, which predicts -9.172 dB for byte -12 --
#:      0.31 dB apart from two completely unrelated paths (editor SysEx on a
#:      resident preset vs our calibration against written banks). Put the trim
#:      through `e4xt_volume_byte`.
#:   2. **A large swing runs out of trim.** 43 dB of AKAI swing needs -21.5 dB
#:      of static trim against an `E4XT_VOL_MEASURED_FLOOR_DB` of -22.90 -- the
#:      loudest real sources sit at the very edge of the calibrated range.
#: `Vel~` is 89.6 MEASURED (mean of 12 runs, EOS 4.70); the EOS 4.0 manual
#: says 63.0, kept below as E4XT_VEL_PIVOT_MANUAL. See the note above --
#: probably a firmware difference, and the measurement is the one that
#: survived every control.
E4XT_VEL_PIVOT = {'Vel+': 0.0, 'Vel~': 89.6, 'Vel<': 127.0}
E4XT_VEL_PIVOT_MANUAL = {'Vel+': 0.0, 'Vel~': 63.0, 'Vel<': 127.0}

#: What the E4B writer's `_MOD_TMPL` currently IMPOSES on every voice, in dB.
#: Slot 0 is `Vel< -> AmpVol` at amount 30/127 = 23.62 %, so by the law above
#: it is a **22.37 dB velocity swing that no source asked for** -- and an AKAI
#: program with `V_LOUD` 0, measured genuinely neutral, arrives on the E4XT
#: carrying it. Not a rounding error; this is the size of the bug.
E4XT_IMPOSED_VEL_AMPVOL_SWING_DB = 22.37


# ── MPC filter section, measured on an MPC One 2026-09-01 ──────────────────
#
# Every constant below replaced an E4XT number that was being applied to MPC
# sources for want of anything better. Measured in LEGACY keygroup mode (the
# engine that plays classic XPMs -- 3.9 keygroups have two filters and are a
# different animal), white noise through a wide-open reference, corners from a
# fitted pole model rather than a -3 dB crossing.
#
# **WHY NOT A -3 dB CROSSING:** `hw_measure.corner_frequency` is accurate to
# 0.3 % on synthetic ideal data and reads ~25 % LOW on real spectra. That was
# caught only because an independent prior measurement (§MPCCUTOFF) disagreed,
# and it nearly became a recorded law. Fit the whole curve; and exclude bins
# that have reached the noise floor, which a 4-pole hits four times sooner
# than a 2-pole.

#: MPC filter-frequency MODULATION depth, full scale, in cents.
#:
#: **One law covers every filter-frequency destination on this machine**: they
#: all add in KNOB units at full efficiency, so full depth sweeps the entire
#: cutoff knob range. Measured twice through two different parameters:
#:
#:     velocity -> filter, full depth   11409 cents   (efficiency 1.008)
#:     filter envelope, full depth      11394 cents   (Depth 64)
#:                                      11485 cents   (Depth 96)
#:     the cutoff knob range itself     11409 cents
#:
#: Spread 0.8 %. The envelope was confirmed linear in the DEPTH setting, not
#: just in the modulation -- two points plus a saturated endpoint would have
#: been a line by definition, and the AKAI tremolo showed what assuming that
#: costs (9.9x at the far end of the other variable).
#:
#: REPLACES, for MPC sources only:
#:   VEL_FILTER_FULL_CENTS  9120  (E4XT) -- 1.25x too small
#:   FILTER_ENV_FULL_CENTS  4383  (E4XT) -- 2.60x too small, and the filter
#:                                envelope is non-zero in 41.6 % of real
#:                                keygroups, so nearly half the corpus has
#:                                been converting at 38 % of its true depth.
MPC_FILTER_MOD_FULL_CENTS = 11409.0

#: MPC `KB>FLT` (XPM `FilterKeytrack`) at maximum, in octaves of cutoff per
#: octave of key. MEASURED 0.945 over keys 36..72 (0.926 / 0.933 / 0.976 per
#: octave); the model previously assumed 1.000, i.e. 6 % high. Only ONE
#: setting was measured, so linearity in the setting is untested -- acceptable
#: because the field is 0.0 in 96.7 % of real keygroups.
#: (The panel calls it `KB>FLT` and the manual files it under a *Velocity
#: Sensitivity* heading, which shares no word with the XPM field name.)
MPC_KEYTRACK_OCT_PER_OCT = 0.945

#: MPC resonance -> peak height in dB above the passband, per filter type.
#: `(zero_offset_db, scale_db, exponent)`, evaluated as
#: `zero + scale * res**exponent` with `res` = setting/127.
#:
#: MEASURED at five settings each, residuals <= 0.6 dB. The two filters differ
#: in ALL THREE terms, so a shared law would have been wrong for whichever one
#: it was not fitted to -- and they are 35 % and 31 % of real keygroups:
#:
#:     Low 2   0.15 + 18.21 * res**0.502     ceiling 18.4 dB
#:     MPC LP  2.15 + 20.54 * res**0.390     ceiling 22.7 dB
#:
#: **MPC LP IS NOT NEUTRAL AT RESONANCE 0** -- it carries +2.15 dB of inherent
#: peak, which is character of the 3000 emulation rather than an offset error
#: (Low 2 measures +0.15 dB at the same setting). A resonance-0 MPC LP patch
#: converted at resonance 0 loses a bump it actually has.
#:
#: What this replaces was wrong in three ways at once: RESONANCE_FULL_DB
#: (25.51, an E4XT number) applied LINEARLY, so gentle resonance was
#: understated by ~2.7 dB, strong resonance overstated by ~7.6 dB, and the
#: error changed SIGN across the range.
MPC_RESONANCE_LAW = {
    2:  (0.15, 18.21, 0.502),     # Low 2  (2-pole, 12 dB/oct)
    29: (2.15, 20.54, 0.390),     # MPC LP (MPC3000 LPF emulation, 12 dB/oct)
}
#: Filter types with no measured law of their own fall back to Low 2's, which
#: is the closest measured lowpass. Recorded as a fallback, not a measurement.
MPC_RESONANCE_DEFAULT_TYPE = 2


def mpc_resonance_db(setting_01: float, filter_type: int = 2) -> float:
    """MPC `Resonance` (0..1 as stored in the XPM) -> peak dB above passband."""
    z, a, p = MPC_RESONANCE_LAW.get(filter_type,
                                    MPC_RESONANCE_LAW[MPC_RESONANCE_DEFAULT_TYPE])
    r = max(0.0, min(1.0, setting_01))
    return z + a * (r ** p) if r > 0.0 else z


def mpc_resonance_to_model(setting_01: float, filter_type: int = 2) -> float:
    """MPC `Resonance` -> this project's 0..1 peak-height convention.

    The model's 0..1 is a fraction of RESONANCE_FULL_DB (a measured PEAK
    HEIGHT, not a fraction of anybody's dial). RESONANCE_FULL_DB's own note
    says the blocker for putting every parser on that scale is "knowing each
    machine's peak-height range, which only the AKAI and the E4XT currently
    have measured" -- as of 2026-09-01 the MPC has it too, so this parser
    joins them instead of normalising by its own dial.
    """
    return max(0.0, min(1.0, mpc_resonance_db(setting_01, filter_type)
                        / RESONANCE_FULL_DB))


#: MPC `VelocitySensitivity` -> gain. MEASURED on an MPC One 2026-09-01
#: (`tests/re_banks/measure_xpm_velocity.py`, procedure in
#: docs/re_procedures/xpm_velocity.md), 81 points, 9 sensitivities x 9
#: velocities in ONE capture:
#:
#:     gain_linear(v, s) = (1 - s) + s * (v / 127)
#:
#: **RMS residual 0.033 dB, max 0.174 dB over all 81 points.** The machine
#: crossfades, IN AMPLITUDE, between a flat response and one where amplitude
#: is proportional to velocity. Gates all passed: gain drift across the run
#: 0.02 dB, negative control flat to 0.06 dB, peak -11.19 dBFS (no clipping),
#: manipulation live at 42.26 dB.
#:
#: PIVOT 127. At v=127 the gain is 1 for every sensitivity -- measured spread
#: 0.06 dB across all nine settings. Same convention as the K2000's amp
#: VelTrk, NOT the AKAI's 64.
#:
#: ZERO IS GENUINELY NEUTRAL: 0.01 dB across the full velocity range at
#: sensitivity 0. That was already the shipped reader's assumption, now
#: measured rather than assumed.
#:
#: **THE SHAPE IS A THIRD AXIS, and this is the part that does not fit the
#: model.** The AKAI, K2000 and E4XT velocity laws are linear in dB; this one
#: is linear in AMPLITUDE, which is strongly concave in dB (at sensitivity 1
#: the top half of the velocity range spans 6 dB and the bottom half spans 36).
#: `VoiceLayer` carries a swing and a pivot, so it can express "how far" and
#: "about what" but not "along what curve" -- an MPC source therefore converts
#: with the right endpoints and an approximated middle. Fitting a dB-linear
#: slope to this data gives r2 0.70 at full sensitivity, which is the model
#: being wrong rather than the measurement being noisy. Do not read a poor r2
#: here as scatter.
#:
#: The one visibly larger residual (-0.174 dB) is v1 at sensitivity 1.0, the
#: quietest point in the grid at -64 dB -- still 31 dB clear of the capture's
#: floor, so not a floor effect; most likely the machine's own quantisation of
#: a very small gain. Not chased; nothing depends on it.
MPC_VELSENS_PIVOT = 127


def mpc_velsens_gain_db(velocity: float, sensitivity: float) -> float:
    """dB the MPC applies at `velocity` for a given `VelocitySensitivity`,
    relative to the level at velocity 127. Always <= 0."""
    s = max(0.0, min(1.0, sensitivity))
    v = max(1.0, min(127.0, velocity))
    g = (1.0 - s) + s * (v / 127.0)
    return 20.0 * math.log10(g) if g > 0.0 else -120.0


def mpc_velsens_swing_db(sensitivity: float) -> float:
    """The v1..v127 swing in dB for a given `VelocitySensitivity`.

    Full sensitivity is 42.08 dB (amplitude proportional to velocity, so
    20*log10(1/127)); sensitivity 0 is 0.0.
    """
    return -mpc_velsens_gain_db(1.0, sensitivity)

#: Velocity pivots per machine, for `VoiceLayer.velocity_to_volume_pivot`.
#: All three MEASURED, none assumed: the AKAI's 64 from V_LOUD/V_ENV2/K_FREQ
#: independently (s3ked §167/§171 and the V_ENV2 run, the last exact to 1 cent
#: across the full velocity range), the K2000's 127 from AMP VelTrk delivering
#: its setting in full downward from the loudest note (k2kremote), the E4XT's
#: three from E4XT_VEL_PIVOT above.
VEL_VOL_PIVOT_AKAI = 64
VEL_VOL_PIVOT_KRZ = 127

#: K2000 `F4 AMP VelTrk`, HOB segment 0x53 index 4: dB of velocity swing per
#: unit. MEASURED at ~1:1 (k2kremote): with the velocity->filter route zeroed,
#: a setting of 35 delivered **34.59 dB** of v1..v127 swing, and v1's absolute
#: level moved +10.94 dB when the setting went 35 -> 24, against +11.0
#: predicted for full delivery and +0.0 for a fixed floor. The residual ~5 dB
#: shortfall in the un-zeroed case is the velocity->filter route, i.e. real
#: patch behaviour, not a scaling error -- do not compensate for it.
#:
#: The run that originally suggested a compressed delivery (28.77 dB of a 35
#: setting, with a plateau below v4) was a BROKEN EXPERIMENT, retracted: the
#: probe's `leave_editor()` answered the save prompt "No", so both conditions
#: were the same condition. §KRZAMPVEL keeps the full account.
#:
#: SIGNED. 38 of 16,649 real layers carry a negative value (0.23 %, clustered
#: at -1..-9), meaning louder-when-soft. Reading the byte unsigned would turn
#: -1 dB into +255 dB.
KRZ_AMP_VELTRK_DB_PER_UNIT = 1.0




def mpc_velsens_from_swing_db(swing_db: float) -> float:
    """Inverse of `mpc_velsens_swing_db`: the MPC sensitivity behind a span.

    The model stores the v1..v127 SPAN, because that is what every dB-linear
    machine's field means and what the readers and writers already exchange.
    Reconstructing the MPC's own parameter from it keeps that interface intact
    rather than adding a second, format-specific number to the model.
    """
    g1 = 10.0 ** (-max(0.0, swing_db) / 20.0)     # amplitude at v1 relative to v127
    denom = 1.0 - 1.0 / 127.0
    return max(0.0, min(1.0, (1.0 - g1) / denom))


def velocity_source_gain_db(swing_db, curve, pivot, velocity) -> float:
    """The SOURCE's own gain at `velocity`, in dB relative to its reference.

    For a dB-linear source this is the straight line `S*(v-pivot)/126` that the
    whole model has assumed since the field existed. For an amplitude-linear one
    it is the MPC's measured law, reconstructed from the stored span.
    """
    if swing_db is None or pivot is None:
        return 0.0
    v = max(1.0, min(127.0, float(velocity)))
    if curve == VELOCITY_CURVE_AMPLITUDE_LINEAR:
        # The MPC's reference is v127, so shift onto the caller's pivot to keep
        # both curves in the same coordinates.
        s = mpc_velsens_from_swing_db(swing_db)
        return mpc_velsens_gain_db(v, s) - mpc_velsens_gain_db(pivot, s)
    return swing_db * (v - pivot) / 126.0


def fit_velocity_line(swing_db, curve, src_pivot, dst_pivot,
                      v_lo=None, v_hi=None):
    """Best dB-linear approximation of a source's velocity response, for a
    target that pivots at `dst_pivot`.

    Returns `(swing_to_write, level_offset_db, rms_error_db)`.

    EVERY TARGET WE WRITE IS dB-LINEAR, so a writer has exactly two knobs -- the
    cord/field AMOUNT (the slope) and the static LEVEL (the offset) -- and this
    fits both at once by least squares. That is strictly more general than the
    older `velocity_pivot_offset_db`, which set the slope to the source's span
    and solved only for the offset.

    **It reduces to that function exactly when the source is dB-linear**: the
    fit is then exact, the slope comes back as the source's own swing and the
    offset as `S*(dst-src)/126`, RMS 0. Verified to 1e-9, which is what makes
    this safe to route AKAI, KRZ and E4B conversions through unchanged.
    """
    if swing_db is None or src_pivot is None or dst_pivot is None:
        return (swing_db, 0.0, 0.0)
    lo, hi = (v_lo or VELOCITY_FIT_RANGE[0]), (v_hi or VELOCITY_FIT_RANGE[1])
    vs = range(int(lo), int(hi) + 1)
    xs = [(v - dst_pivot) / 126.0 for v in vs]
    ys = [velocity_source_gain_db(swing_db, curve, src_pivot, v) for v in vs]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0.0:
        return (swing_db, my, 0.0)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    level = my - slope * mx
    rms = math.sqrt(sum((level + slope * x - y) ** 2
                        for x, y in zip(xs, ys)) / n)
    return (slope, level, rms)


def velocity_pivot_offset_db(swing_db, src_pivot, dst_pivot):
    """Static level offset that makes a target's velocity response match a
    source's when their PIVOTS differ.

    Writing the source's swing about a different pivot is wrong by

        S * (dst_pivot - src_pivot) / 126

    which is **CONSTANT in velocity** -- verified to 0.0000 dB of spread across
    v1..v127. So the whole pivot mismatch is repaired by one static level
    offset, and no new hardware measurement was needed to establish it: the
    pivots (AKAI 64, K2000 127, MPC 127, E4XT 0/89.6/127), the swing laws and
    the three targets' static-level laws were all already measured.

    Positive means the target must be made LOUDER to match. AKAI (64) -> K2000
    or E4XT (127) needs +S/2; MPC or KRZ (127) -> AKAI (64) needs -S/2.

    Returns 0.0 when either side's pivot is unknown -- a swing whose pivot
    nobody recorded cannot be corrected, and guessing one would be worse than
    leaving the flat error in place.
    """
    if swing_db is None or src_pivot is None or dst_pivot is None:
        return 0.0
    return swing_db * (dst_pivot - src_pivot) / 126.0


def velocity_pivot_preset_shift(voices, dst_pivot):
    """The per-PRESET downward shift that makes every voice's pivot offset fit.

    Jan's design, 2026-09-03, and it is better than clamping the offsets: the
    target's static level has far more range DOWNWARD than up (the K2000's
    Adjust knees at +12 and clamps from +24, but reaches about -96), so
    shifting the whole preset down by its largest required offset leaves every
    voice's offset at or below zero. **Relative balance inside the preset is
    then exact and only the preset's overall loudness moves** -- which is a
    knob, not a fidelity property. Clamping instead trades the property you
    hear for the one you do not.

    Measured over 10,933 real AKAI programs: median shift 12.0 dB, max 29.9.
    Every preset fits on the K2000; 96 % fit on the E4XT, whose measured floor
    is -22.9 dB, leaving 4.5 % that still need a clamp and a log line.

    Applies per PRESET because the level fields are per layer/voice -- presets
    play one at a time, so a level difference between them is far less harmful
    than an imbalance inside one.
    """
    offs = [velocity_pivot_offset_db(getattr(v, 'velocity_to_volume_db', None),
                                     getattr(v, 'velocity_to_volume_pivot', None),
                                     dst_pivot)
            for v in voices]
    return max([0.0] + offs)


def velocity_volume_gain_db(swing_db, pivot, velocity):
    """dB the velocity response applies at `velocity`, relative to the level
    at `pivot`.

    One formula covers all three machines because the pivot is a parameter
    rather than a per-format special case:

        gain(v) = swing * (v - pivot) / 126

        pivot   0  ->  gain(1) ~ 0,          gain(127) = +swing
        pivot  64  ->  gain(1) = -swing/2,   gain(127) = +swing/2
        pivot 127  ->  gain(1) = -swing,     gain(127) = 0

    The span between velocity 1 and 127 is `swing` in every case -- that is
    what makes the swing comparable across machines while the pivot is not.

    **/126 AND NOT /127, DELIBERATELY.** eosed has stated the E4XT law both
    ways -- `(127 - v) / 126` in §83 and `(v - pivot) / 127` in §85 -- and the
    two differ by 0.8 %. The constants were FITTED as a v1..v127 swing, so 126
    (the number of velocity steps between those endpoints) is the divisor that
    reproduces the fitted quantity exactly; 127 is the width of the control
    range including velocity 0, which no note ever sends. The difference is
    ~0.2 dB on a 24 dB swing and inaudible, but the two normalisations diverge
    silently and would otherwise surface later as an unexplained mismatch
    between a predicted and a measured swing.

    Returns 0.0 when the swing is unknown (None), NOT when it is 0.0: a
    measured-neutral response and an unread field are different facts, and
    only the caller knows what to do about the second.
    """
    if swing_db is None or pivot is None:
        return 0.0
    return swing_db * (max(1, min(127, velocity)) - pivot) / 126.0


#: K2000 envelope LEVEL field: displayed percent -> dB relative to 100 %.
#:
#: **MEASURED, not derived (§KRZLEVELCURVE, k2kremote, 2026-08-31).** The field
#: is NOT the linear amplitude percent it is displayed as. 50 % is -18.07 dB,
#: not -6.02 dB; 25 % is -28.03 dB, not -12.04 dB. Treating the display as
#: linear amplitude -- which `krz_writer._lvl_byte` did from the beginning --
#: writes every envelope level far quieter than intended, worst at the bottom.
#:
#: Rig, because a naive version of this measurement is wrong: ROM program 199
#: edit buffer (never saved), KeyMap 151 Sawtooth so no sample contour sits
#: underneath, Algorithm 1 with filter NONE, no LFO, AMPENV User, Att1/2/3 all
#: 0 s at 100 %, Dec1 time 0.50 s, note 48 vel 100, plateau = RMS over
#: 1.2-2.2 s, every value referenced to the 100 % capture's own plateau so no
#: absolute reference enters. Stitched from two gain settings tied on a
#: 7-point overlap (50/45/40/35/25/18/12) where both are demonstrably linear:
#: offset 29.925 dB, sd 0.211 dB.
#:
#: **The +30 dB pass saturates the K2000's own amp stage at the top** -- at
#: F4 AMP Adjust 36 dB, 100 % against 50 % differed by 3.7 dB instead of 18 --
#: so the high-gain arm supplies only 30 % and below. Worth knowing on its own:
#: F4 AMP Adjust saturates well before its 48 dB maximum on a full-level signal.
#:
#: Shape: TWO dB-linear segments and then a collapse -- 0.335 dB/unit above
#: 75 %, 0.398 dB/unit from 71 down to 25 %, then accelerating hard (0.70 at
#: 22 %, 1.34 at 12 %, 2.01 at 9 %, 5.96 at 6 %, 9.09 at 4 %). No single law
#: fits; a power law drifts from exponent ~2.6 to ~1.7. Hence a table, the
#: same answer §KRZENVDEPTH2 and §KRZLFOPITCH reached for the same reason.
#:
#: GOVERNS ALL SEVEN STAGE LEVELS, measured on each family rather than assumed:
#: the ATTACK stages match Dec1 within a few tenths (50 % -> -17.6..-17.9 dB
#: after correcting for the measurement window's own ramp bias, against Dec1's
#: -18.07), and the RELEASE stages match to 0.01 dB (50 % -> -18.06). Linear
#: amplitude (-6.02 dB) is excluded by ~12 dB in both cases.
#:
#: 3 % carries about +-1 dB (9.7 dB above the noise floor). 2 % and 1 % were
#: floor-limited lower bounds, visibly non-monotonic, and are DELIBERATELY
#: EXCLUDED rather than recorded as values -- below 3 % this table extrapolates
#: and says so.
KRZ_LEVEL_PCT_DB = [
    (100, 0.00), (95, -1.68), (90, -3.34), (85, -5.03), (80, -6.70),
    (75, -8.37), (71, -9.71), (65, -12.06), (60, -14.07), (55, -16.09),
    (50, -18.07), (45, -20.07), (40, -22.08), (35, -24.07), (30, -25.92),
    (25, -28.03), (22, -29.13), (18, -31.95), (12, -37.96), (9, -41.98),
    (6, -47.99), (4, -59.92), (3, -69.01),
]


def krz_level_pct_to_db(pct: float) -> float:
    """K2000 displayed envelope-level percent -> dB relative to 100 %.

    Linear interpolation in dB between measured points. Below the measured
    floor (3 %) this extrapolates on the last segment's slope, which is steep
    and poorly constrained -- callers wanting a specific dB should go through
    `krz_db_to_level_pct` instead of inverting this by search.
    """
    tbl = KRZ_LEVEL_PCT_DB
    if pct <= 0.0:
        return float('-inf')    # 0 % is silence, not the extrapolated tail
    if pct >= tbl[0][0]:
        return 0.0
    if pct <= tbl[-1][0]:
        (p1, d1), (p0, d0) = tbl[-1], tbl[-2]
        slope = (d0 - d1) / (p0 - p1)
        return d1 + (pct - p1) * slope
    for (p0, d0), (p1, d1) in zip(tbl, tbl[1:]):
        if p1 <= pct <= p0:
            return d1 + (pct - p1) * (d0 - d1) / (p0 - p1)
    return 0.0


def krz_db_to_level_pct(db: float) -> float:
    """dB relative to full -> the K2000 displayed envelope-level percent that
    produces it. Inverse of `krz_level_pct_to_db`, by interpolation.

    Clamped to the measured range: anything at or below the table's floor
    (-69.01 dB at 3 %) returns 0, because the hardware's own resolution there
    is worse than the step between adjacent percents and the two points below
    it could not be measured above the noise floor at all.
    """
    tbl = KRZ_LEVEL_PCT_DB
    if db >= 0.0:
        return 100.0
    if db <= tbl[-1][1]:
        return 0.0
    for (p0, d0), (p1, d1) in zip(tbl, tbl[1:]):
        if d1 <= db <= d0:
            return p1 + (db - d1) * (p0 - p1) / (d0 - d1)
    return 0.0
