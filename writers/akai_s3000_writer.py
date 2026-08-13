#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# This file is part of mpc2emu.
#
# AKAI S3000-series writer. The inverse of parsers/akai_s3000_parser.py;
# both are driven by docs/AKAI_S3000_FORMAT.md, which cites its sources.
# Structural constants and the name codec are imported from the parser
# rather than duplicated -- this project has had duplicated tables drift
# apart before (CR-13/CR-17), and a writer that disagrees with its own
# reader is the worst possible version of that.
#
# No third-party source code copied.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
AKAI S3000 Writer
-----------------
Emits AKAI S3000-series program (`.a3p`) and sample (`.a3s`) files.

**Defaults are not zeros.** The format's unset state for most parameters is a
specific non-zero value -- polyphony 31, stereo level 99, loudness 80, filter
frequency 99, amp sustain 99 and so on. A zeroed program loads on the
hardware and sounds wrong: silent, or fully closed filter, rather than
obviously broken. Every default below is the one the format documentation
lists, so an untouched field means "as the sampler would have made it".
"""

import math
import struct
import sys
from pathlib import Path
from typing import Optional

from models.common import (Bank, LoopType, SampleData, safe_filename,
                           E4B_CUTOFF_MIN_HZ, E4B_CUTOFF_MAX_HZ)
from parsers.akai_s3000_parser import (
    str_to_akai, AKAI_NAME_LEN, SAMPLE_HEADER_LEN, PROGRAM_COMMON_LEN,
    KEYGROUP_LEN, _ZONE_OFFSETS, _BLOCK_ID_PROGRAM, _BLOCK_ID_KEYGROUP,
    _BLOCK_ID_SAMPLE,
)

#: Blocks carry their own RAM address at 0x01-0x02, in **16-byte paragraphs**
#: (12 paragraphs = 192 bytes = one S3000 block).  Confirmed on the disc
#: corpus: across 2 058 programs the value steps by exactly 12 from the
#: program common block to keygroup 1 and on through every keygroup, 19 553
#: consecutive deltas with one outlier.  It is a save-time artifact the
#: sampler recomputes on load, but **no real file leaves it zero**, and 0x900c
#: is the most common base (411 programs) -- the address of the first program
#: in a freshly cleared memory.  Writing the observed shape is strictly safer
#: than writing a value the format never uses.
_RAM_BASE_PARA = 0x900c
_BLOCK_PARA = 12            # one 192-byte block, in 16-byte paragraphs

#: 0xFFFF is the format's "no pointer" marker: it is what 72% of real samples
#: carry as their stereo partner (every mono one), and what 100% of real
#: keygroups carry in the two bytes after each velocity zone's parameters.
_NO_POINTER = 0xFFFF

MAX_KEYGROUPS = 99          # program common 0x2a is 1-99
MAX_ZONES_PER_KEYGROUP = len(_ZONE_OFFSETS)     # four velocity zones


def _clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


def _or_default(v, default):
    """`v` unless it is None. NOT `v or default`: 0 and 0.0 are legitimate
    values here -- a pan of 0.0 is hard left, and `or` would centre it."""
    return default if v is None else v


def _put_s16(buf: bytearray, off: int, v: int) -> None:
    struct.pack_into('<h', buf, off, _clamp(v, -32768, 32767))


# ── sample ─────────────────────────────────────────────────────────────────

# ── S3000XL parameter laws, HW-measured (s3ked, 2026-08-10/11) ───────────────
# Every one of these was fitted from a real machine after the program under
# test was isolated on its own MIDI channel -- an earlier set was measured with
# ten library programs sounding underneath and was void. Each carries the
# parameter range it was FITTED OVER, and we clamp to that rather than
# extrapolate.
#
# Not extrapolating is a lesson from the E4B side of this project: an
# exponential fitted over cutoff positions 0.0-0.9 looked convincing at
# r = 0.9958 and predicted 4.0 kHz where the hardware actually measured
# 21.5 kHz. A curve is evidence only where it was sampled.
#: FILFRQ -> Hz. **Re-derived from the RESONANCE PEAK, 2026-08-12 (s3ked §54),
#: replacing the centroid-derived 6.998 * exp(0.07384 v) this writer shipped.**
#:
#: The old law read 20-30% high and got worse as the corner rose -- 0.28
#: octaves at FILFRQ 40, 0.40 at 70, 0.52 at 99. A spectral centroid is the
#: average frequency of everything the SOURCE contains, so it sits above the
#: corner by a source-dependent amount: a SLOPE error, not an offset, which is
#: why the discrepancy their §33 had already noticed could never have been
#: fixed with a calibration constant.
#:
#: Cost of the old value here, measured by inverting one law and evaluating
#: with the other: every AKAI program we have written is DARK by 0.31 octaves
#: at a 300 Hz target, 0.41 at 1 kHz, 0.47 at 4 kHz. Audible, and worse the
#: brighter the source asked for.
#:
#: Taken despite being minutes old, which is a departure from the rule applied
#: to K_FREQ and FILQ this week -- and the difference is that those would ADD a
#: capability we do not have, while this REPLACES a law we ship that is now
#: measured wrong. Keeping the old value is not the neutral choice. It also
#: meets the standard in docs/RESOLUTION_NOTES.md AGREEMENT: fitted on 62..92,
#: it predicted FILFRQ 44, 50 and 56 to -0.2%, +0.5% and +2.2%, and an
#: independently fitted damping law predicts its damping to 0.7%. Nothing
#: reaches a user regardless -- this branch is gated on hardware.
_AK_FILTER = (6.4597,     0.07100, 44, 92)    # Hz
# ── Envelope timing: RATES, not durations (s3ked retraction, 2026-08-11) ─────
# An AKAI envelope value sets a SLEW RATE. How long a stage takes therefore
# depends on how far it has to travel, and a "decay time" alone does not
# determine the value. Their varying-span test is decisive: hold the value and
# change the distance, and the RATE stays constant (CV 0.27% for DECAY1) while
# the TIME moves 18.8%.
#
# So DECAY1 70 is not "339 ms". It is ~24.7 dB/s, which happened to take 339 ms
# across the span their calibration used. A patch sustaining at -12 dB and one
# at -48 dB need DIFFERENT DECAY1 values for the same wall-clock decay -- a
# factor of four in distance.
#
# This withdrew every envelope TIMING constant previously published, including
# the ones this file had wired. The exponents are negative here because a
# larger value means a SLOWER stage, the opposite direction from the withdrawn
# set -- so a stale constant cannot silently survive; it inverts.
#
#   rate = a * exp(b * value),  time = span / rate
_AK_DECAY1_RATE = (23525.6, -0.09776, 45, 85)   # dB/s,            r2 0.99998
_AK_RELSE1_RATE = (22055.3, -0.09683, 55, 70)   # dB/s,            r2 0.99956

# NOT WIRED, and each for its own reason rather than as a batch:
#
#   ATTAK1, ATTAK2  s3ked's varying-span test says attack fits NEITHER a rate
#       nor a duration -- across a 99% change in span the rate moved 29% and
#       the time 11%, both sub-linearly. They recorded it unresolved rather
#       than forcing it, which is right, and it leaves us nothing to convert
#       with. Fixed defaults until it is resolved.
#
#   DECAY2, RELSE2  the replacement rates are in FILFRQ units (octaves, 9.4
#       units to the octave). Converting a time needs the SPAN the filter
#       envelope sweeps, and our model carries no filter-envelope amount --
#       there is no span to divide by. Fixed defaults until there is.
#
# Both were wired from the withdrawn model earlier today. Unwiring them is not
# a regression: writing a value derived from a retracted law is worse than
# writing a neutral default, because it looks like intent.

#: References to s3ked are by SECTION (§NN in their docs/RESOLUTION_NOTES),
#: never by commit hash. They squashed their history on 2026-08-12 and every
#: hash this file used to cite was orphaned in one operation -- fourteen
#: dead links, all written the night before. A section number survives a
#: rebase; a hash in another project's repository is a reference you do not
#: control.
#:
#: **s3ked is a sibling project on the author's machine, NOT shipped with this
#: repository and not public.** So no reader outside that machine can follow
#: any §NN here, which makes every one of them provenance rather than an
#: argument. Each is therefore written to be redundant: the measurement, its
#: numbers and its caveats are stated INLINE, and the section number records
#: only who measured it and where the long form lives. If you are ever tempted
#: to shorten one of these notes to "see s3ked §NN", don't — that converts a
#: standalone fact into a dangling pointer for everyone but us.
#:
#: (Audited 2026-08-13, after s3ked hit both failure modes in one evening: a
#: note citing a section that said nothing about its claim, and a correction
#: citing a section its own branch did not carry. All sixteen section
#: citations in this file were checked against their sources; all sixteen say
#: what is claimed here, including §45, whose finding was later retracted and
#: which is recorded as retracted with the reasoning that broke it. One real
#: defect found and fixed: a doubled "(§49, §49)".)
#:
#: SUSTN1 slope, dB per unit. Re-measured 2026-08-11 (s3ked §37):
#: 0.60676, r2 0.99993, thirteen points each verified to have at least 6 dB of
#: headroom to the output ceiling AND 22 dB above the noise floor, both limits
#: measured in the same session. Supersedes 0.60832.
#:
#: The re-measurement was an audit, not a refinement: every earlier sweep had
#: PRLOUD pinned to 99 while V_LOUD sat at its factory 20, driving 6.8 dB into
#: a ceiling. The level laws survived it (this one to 0.26 %) because only
#: their topmost point ever approached the limit -- the velocity work did not.
#:
#: Worth keeping for the trap in the audit itself: the first CONTROL run was
#: worse than the thing it checked. At PRLOUD 70 it returned 0.57888, out by
#: 4.6 %, because its low end sat in the noise floor instead. **A ceiling and a
#: noise floor both flatten a curve, from opposite ends, so two such runs do
#: not bracket the truth -- both understate the slope and the answer lies
#: outside them.** The tell was that the "clean" run had the worse r2 and six
#: times the residual tilt. A flattened line is still a line, so goodness of
#: fit does not notice; only measuring the limits does.
#:
#: Cost here: 36 sustain fractions in 1000 shift by one byte, max delta 1, and
#: the release span moves with it (release starts at the sustain level).
_AK_SUSTAIN_DB_PER_UNIT = 0.60676

#: LFORAT is LINEAR, not exponential: Hz = 0.11867 * LFORAT - 0.04, r2 0.9995.
#: Measured twice by independent routes -- once through loudness modulation,
#: once by tracking PITCH directly (LFO1 drives pitch, so there is no
#: destination to choose). Two unrelated signal paths and detectors agreeing
#: within a few percent is stronger than either alone.
_AK_LFO_RATE = (0.11867, -0.04, 0, 99)

#: ENVELOPE 2 -- the FILTER envelope, and its laws are NOT envelope 1's.
#: Measured through BRIGHTNESS rather than level (s3ked): ENV2 routed via
#: MODSFILT1=10 / MODVFILT1=50 with the filter part-closed, tracking the
#: spectral centroid against a MODVFILT1=0 control that holds flat.
#:
#: The attack curves CROSS envelope 1's -- ENV2 is ~1.7x slower at the low end
#: and ~0.8x at the high end -- so inheriting ENV1's law would have been wrong
#: at both ends and right in the middle, which is the sustain failure mode and
#: the one that survives every endpoint check.
#:
#: Values taken from s3ked's s3k/scales.py, NOT from their prose. The first
#: ATTAK2 figures they sent by message (a=0.00073832, b=0.08963, fitted 40..90)
#: were superseded by a re-measurement before I had finished wiring them, and
#: the module had the newer ones. That is precisely the hand-copy drift they
#: warned about; tests/test_akai_scales.py now detects it instead of hoping.


def _invert_exp_law(value: float, law) -> int:
    """value = a*exp(b*param)  ->  param, clamped to the FITTED range."""
    a, b, lo, hi = law
    if value <= 0:
        return lo
    param = math.log(value / a) / b
    return int(round(max(lo, min(hi, param))))


def akai_filter_byte(cutoff_pos: float) -> int:
    """0..1 shared cutoff position -> FILFRQ.

    `filter_cutoff` is this project's internal 0-1 position, defined by the
    documented 57 Hz..20 kHz law (see models.common). Convert it to the
    frequency it is meant to MEAN, then ask the measured S3000XL curve for the
    byte that lands there -- the same two-step the E4B writer does, and for the
    same reason: the position is shared across formats and the machines do not
    agree about what it sounds like.

    The measured curve covers FILFRQ 44..92, i.e. 147 Hz .. 4.4 kHz. Outside
    it we do NOT extrapolate, and the two ends are handled differently because
    they are not symmetrical:

      above 4.4 kHz -> **99**, not 92. 99 is the machine's own resting value
                       and is known to be wide open (s3ked took the sweep's
                       0 dB reference there and found no attenuation until the
                       band edge). Clamping to 90 instead would make every
                       "filter fully open" source audibly DARKER than the
                       writer's previous fixed 99 -- being careful about
                       extrapolation must not cost fidelity we already had.
      below 147 Hz  -> 44, the measured floor. Brighter than asked for, but
                       FILFRQ 0..43 is unmeasured and the E4B precedent says
                       an unsampled extrapolation can be wrong by 5x.
    """
    pos = max(0.0, min(1.0, cutoff_pos))
    hz = E4B_CUTOFF_MIN_HZ * (E4B_CUTOFF_MAX_HZ / E4B_CUTOFF_MIN_HZ) ** pos
    a, b, lo, hi = _AK_FILTER
    if hz >= a * math.exp(b * hi):
        return 99                       # wide open, HW-confirmed
    return _invert_exp_law(hz, _AK_FILTER)


def akai_lfo_rate_byte(hz: float) -> int:
    """LFO rate in Hz -> LFORAT. Linear, HW-measured.

    Clamped to 0..99. The law reaches ~11.7 Hz at 99, so anything faster is
    written as 99 rather than extrapolated -- our model allows up to 18 Hz.
    """
    m, c, lo, hi = _AK_LFO_RATE
    return int(round(max(lo, min(hi, (hz - c) / m))))


def akai_env_bytes(env) -> tuple:
    """Envelope -> (ATTAK1, DECAY1, SUSTN1, RELSE1).

    Sustain is computed FIRST because the decay and release values depend on
    it: an envelope value is a slew rate, so the value needed for a given time
    depends on the distance the stage travels, and sustain sets that distance.

    Attack is a fixed default -- s3ked's varying-span test found it fits
    neither a rate nor a duration, so there is nothing to convert with.
    """
    sus = akai_sustain_byte(getattr(env, 'sustain', 0.8))

    # Decay travels from peak DOWN to the sustain level.
    span_decay_db = _AK_SUSTAIN_DB_PER_UNIT * (99 - sus)
    d = _rate_law_value(getattr(env, 'decay', 0.3) or 0.3,
                        span_decay_db, _AK_DECAY1_RATE, default=50)

    # Release travels from the sustain level down to the floor.
    span_rel_db = _AK_SUSTAIN_DB_PER_UNIT * sus
    r = _rate_law_value(getattr(env, 'release', 0.5) or 0.5,
                        span_rel_db, _AK_RELSE1_RATE, default=45)

    return _AK_FIXED_ATTACK, d, sus, r


#: Attack has no usable law -- see the envelope-timing note above.
_AK_FIXED_ATTACK = 0


def _rate_law_value(seconds: float, span: float, law, default: int) -> int:
    """Invert `rate = a*exp(b*v)` for a stage covering `span` in `seconds`.

    Returns `default` when the span is zero -- a stage with nowhere to travel
    has no meaningful rate, and dividing by it would produce a confident
    number from nothing.
    """
    a, b, lo, hi = law
    if span <= 0 or seconds <= 0:
        return default
    rate = span / seconds
    if rate <= 0:
        return default
    v = math.log(rate / a) / b
    return int(round(max(lo, min(hi, v))))


def akai_sustain_byte(fraction: float) -> int:
    """Sustain 0..1 (a level fraction) -> SUSTN1, which is dB-LINEAR.

    `99 + 20*log10(fraction) / 0.60832`, clamped 0..99. Note that 0.10 maps to
    66, not 10 -- the bottom of our range lands in the MIDDLE of the machine's,
    which is why `fraction * 99` sounded plausible and was 34 dB out there.
    """
    f = max(0.0, min(1.0, fraction))
    if f <= 0.0:
        return 0
    return int(round(max(0.0, min(99.0,
               99 + 20 * math.log10(f) / _AK_SUSTAIN_DB_PER_UNIT))))


#: One semitone in AKAI tuning fields. They store semitones with a binary
#: fraction in the low byte -- a step of 1 is 1/256 of a semitone, 0.39 cents.
#: HW-MEASURED by the s3ked project 2026-08-11 for KGTUNO (keygroup 0x05) and
#: PTUNO (program 0x41), both 0.3928/0.3866 cents per unit against a predicted
#: 0.390625. STUNO (sample 0x14) uses the same constant by INFERENCE -- see
#: build_sample, where it is qualified.
#: Charset index of SPACE, and therefore what an empty or unrepresentable
#: name field is filled with. Measured by s3ked as the content of an
#: unassigned zone: twelve of these.
_AKAI_SPACE = 0x0a

_AKAI_TUNE_UNITS_PER_SEMITONE = 256

#: Range of every two-byte tuning field (PTUNO, KGTUNO, VTUNO1..4): +-50
#: semitones, i.e. +-12800 in 1/256-semitone units.
#:
#: **Measured, not inferred (s3ked §57, 2026-08-12).** Raw values written and
#: the PITCH read back: 256 -> +99.8 cents, 512 -> +199.8, 1280 -> +499.9,
#: 2560 -> +999.9, 5120 -> +1999.9, negatives matching to 0.3 cents. Storage
#: was never in question -- every value round-tripped, negatives as two's
#: complement -- the question was whether the stored number means what the
#: document says, and it does.
#:
#: We clamped to the s16 WIDTH until this was settled, which was permissive
#: rather than wrong. Their parameter table had declared 0..50 while quoting
#: "-50.00 to +50.00" in the same entry, a 256x disagreement with itself; when
#: they added a range guard it duly refused every detune past 19.53 cents, so a
#: keygroup could not be moved by a semitone. Their own commit had called an
#: over-tight check the worse bug, and it was, within the hour.
#:
#: The moral for this writer, which has been burned twice on this exact field:
#: a clamp is a claim about the hardware. Too wide lets a bad value through;
#: too narrow silently truncates a good one, and only the first kind announces
#: itself.
_AK_TUNE_MAX = 50 * _AKAI_TUNE_UNITS_PER_SEMITONE     # 12800


#: 2.56 raw units to the cent. Derived, not typed: 256 units per semitone over
#: 100 cents per semitone. Writing the 2.56 literally would let it drift out of
#: agreement with the semitone constant it comes from.
_AK_TUNE_UNITS_PER_CENT = _AKAI_TUNE_UNITS_PER_SEMITONE / 100.0


def _akai_tune_units(cents: float) -> int:
    """Cents -> AKAI 1/256-semitone units, ON THE ONE-CENT GRID.

    The factor is 2.56, NOT 256 and NOT 16. Both of those were in this file
    until 2026-08-11: the sample path multiplied by 256 (treating cents as
    semitones, 100x out) and the zone path by 16 (6.25x out). A 25-cent
    detune came out as 25 semitones and 1.56 semitones respectively.

    The document calls STUNO "cent:semi", which reads like a cents field and
    is not one.

    **The field does not accept every value it can hold (s3ked, 2026-08-13).**
    Writing raw 5121 stores 5120. The machine keeps tuning on a one-cent grid
    and snaps anything between grid points to its neighbour -- silently, with
    no error, visible only on a read-back. Their rule, fitted to 22 measured
    points with no exceptions:

        stored = trunc( round_half_away( written / 2.56 ) * 2.56 )

    Only 101 of the 256 values in a semitone are reachable. So this rounds to
    a whole cent FIRST and then scales, rather than scaling a float and
    rounding the result: `round(12.3 * 2.56)` is 31, which is not on the grid
    and would be stored as 30. Both are within a cent of the request, so the
    audible difference is nil -- what matters is that the written value and
    the stored value are then the same number, which is what makes a
    round-trip check meaningful and a read-back comparison honest.

    Rounds half AWAY FROM ZERO, not Python's banker's rounding: raw 32 is
    exactly 12.5 cents, where round() goes to even and the sampler goes up.
    That one point is what broke their first fit.

    Returns an int, so no caller needs a second round() -- one at the call
    site would quantise the already-quantised value and could walk it back off
    the grid.

    Worth keeping for how it was missed: their original sweep tried 256, 512,
    1280, 2560 and 5120. A sensible ladder, every rung a whole semitone, and
    every rung on the grid -- so the quantisation is invisible from all of
    them. It surfaced only on a different question: not "what does this field
    mean" but "can the display represent everything the byte can hold". A
    parameter sweep confirms the law; it does not test the law's domain.
    """
    whole_cents = math.floor(abs(cents) + 0.5) * (1 if cents >= 0 else -1)
    return math.trunc(whole_cents * _AK_TUNE_UNITS_PER_CENT)


def build_sample(sd: SampleData, name: Optional[str] = None) -> bytes:
    """One SampleData -> a complete `.a3s` file.

    Mono only: the format carries one channel per file and pairs them via
    `address of stereo partner`, which is an internal pointer we cannot
    meaningfully synthesise. A stereo sample is mixed down rather than
    written as a broken pair -- see write_akai_bank.
    """
    h = bytearray(SAMPLE_HEADER_LEN)
    pcm = sd.data
    if getattr(sd, 'channels', 1) > 1:
        pcm = _mixdown(pcm, sd.channels)
    if len(pcm) % 2:
        pcm = pcm[:-1]
    n_frames = len(pcm) // 2

    h[0x00] = _BLOCK_ID_SAMPLE      # block id: 3 = sample header
    # bandwidth: 0 = 10 kHz, 1 = 20 kHz. Anything at or above 30 kHz is
    # full-bandwidth material.
    h[0x01] = 1 if sd.sample_rate >= 30000 else 0
    h[0x02] = _clamp(_or_default(getattr(sd, 'root_note', None), 60), 24, 127)
    h[0x03:0x03 + AKAI_NAME_LEN] = str_to_akai(name or sd.name)
    h[0x0f] = 0x80                      # sample rate field is valid
    h[0x10] = 1                         # one active loop (internal)
    h[0x11] = 0                         # first active loop (internal)

    looped = (sd.loop_type != LoopType.NO_LOOP
              and sd.loop_end > sd.loop_start >= 0
              and sd.loop_end < n_frames)
    # 0 = loop in release, 2 = no looping. The parser treats only 2 as
    # unlooped, so the writer must not emit 0 for a one-shot.
    h[0x13] = 0 if looped else 2

    # STUNO, sample tuning offset.
    #
    # !! THE SCALE HERE IS INFERRED, NOT MEASURED. !!  s3ked swept STUNO on a
    # real S3000XL and it does NOTHING: values 32, 64, 256 and 1000 all wrote
    # and read back exactly, while the pitch did not move by a thousandth of a
    # cent. That is the round-trip trap on a live field -- the byte stores and
    # returns faithfully and means nothing over SysEx.
    #
    # KGTUNO (keygroup 0x05) and PTUNO (program 0x41) ARE measured, both at
    # 0.39 cents per unit = 1/256 semitone. STUNO carries identical wording in
    # the document, so we use the same scale. That is an inference from its
    # neighbours, not a measurement of it.
    #
    # Whether it matters is OUR layer, not theirs: over SysEx there is a
    # machine that may recalculate it, on disc there is not. Only a disc test
    # can say whether a load trusts this field. Until then the factor is right
    # if the field is ever honoured, and harmless if it is not.
    #
    # Regardless of that, the previous code was indefensible: it multiplied by
    # 256, treating cents AS semitones, so a 25-cent detune became 25
    # SEMITONES -- 100x out. Latent because fine_tune is 0 for most sources,
    # so only material carrying real fine tuning was affected, and then
    # catastrophically. Found 2026-08-11 when s3ked measured the scale and
    # warned that "cent:semi" in the document reads like a cents field and is
    # not one.
    _put_s16(h, 0x14, _clamp(_akai_tune_units(getattr(sd, 'fine_tune', 0) or 0),
                             -_AK_TUNE_MAX, _AK_TUNE_MAX))
    struct.pack_into('<I', h, 0x1a, n_frames)          # data length in SAMPLES
    struct.pack_into('<I', h, 0x1e, 0)                 # play relative start
    struct.pack_into('<I', h, 0x22, max(0, n_frames - 1))

    if looped:
        loop_len = sd.loop_end - sd.loop_start + 1
        struct.pack_into('<I', h, 0x26, sd.loop_start)
        struct.pack_into('<H', h, 0x2a, 0)             # length fraction
        struct.pack_into('<I', h, 0x2c, loop_len)
        struct.pack_into('<H', h, 0x30, 9999)          # 9999 = hold
    # loops 2-8 stay zeroed: `loop times` 0 means "no loop", which is the
    # correct unused state for them.

    struct.pack_into('<H', h, 0x8a, _clamp(sd.sample_rate, 1, 65535))
    # Address of the stereo partner. 0xFFFF means "none", which is what every
    # mono sample on the disc corpus carries; zero is a value the format never
    # uses and could be read as a valid pointer.
    struct.pack_into('<H', h, 0x88, _NO_POINTER)
    return bytes(h) + pcm


def _mixdown(pcm: bytes, channels: int) -> bytes:
    """Interleaved -> mono, averaging. Halved before summing so a
    full-scale correlated pair cannot clip."""
    n = len(pcm) // (2 * channels)
    out = bytearray(n * 2)
    for i in range(n):
        acc = 0
        for c in range(channels):
            acc += struct.unpack_from('<h', pcm, (i * channels + c) * 2)[0]
        struct.pack_into('<h', out, i * 2, _clamp(acc // channels, -32768, 32767))
    return bytes(out)


# ── program ────────────────────────────────────────────────────────────────

#: Program-header bytes a real S3000XL holds at rest, which this writer used
#: to leave at ZERO. Offset -> (value, what it is).
#:
#: Thirteen of these are the assignable modulation SOURCES: each byte is an id
#: naming what drives a destination (0 = No Source, 1 = Modwheel, ... 7 = LFO1,
#: 8 = LFO2, 9 = Env1 -- see "Values used to represent Modulation Sources" in
#: lakai_s2800_sysex.html). Read off an S3000XL (OS 2.00) via the s3ked project
#: and diffed against our own header.
#:
#: Our old all-zero output was NOT a stray routing -- 0 means the slot is
#: unassigned, and with every MODV* amount at zero it made no sound either way.
#: The machine's own program 0 has all thirteen sources assigned and every
#: amount at zero, so the two are audibly identical. What the factory values
#: buy is what happens when a user turns an amount UP on the sampler: they get
#: the factory routing (LFO2 on pan, velocity on filter, Env2 on pitch) instead
#: of silence until they also pick a source.
#:
#: THE TRAP, for whoever carries modulation across from a source format: an
#: amount without its matching source is silently inert. A real library program
#: has MODSPAN2 = LFO2 with MODVPAN2 = 25; write the 25 without the 8 and it
#: does nothing. We write no MODV* amounts at all today, so nothing here is
#: inert -- but the moment one is carried over, its source must come with it.
#:
#: **RETRACTED 2026-08-12 (s3ked §51): LFO2 WORKS. Only its route to pan is
#: dead.** Everything from here to the end of this block was written while §39
#: stood, and the caution recorded in it turned out to be justified — so the
#: history is kept rather than deleted, but read the correction first.
#:
#: `LFO2 rate = 0.23708 * PANRAT Hz` over 5..80, r² 0.999843 — exactly twice
#: LFO1's rate for the same value (ratio 1.998), forced through the origin.
#: `PANDEP` gates the depth, `PANDEL` delays the growth, `LFO2WAVE` changes the
#: shape, and `LFO2TRIG` mode 1 locks phase to note-on. LFO2 is
#: assignable-matrix source 8 and modulates the filter at 25–99x prominence.
#:
#: §39 called five fields inert after testing all five against **the pan
#: destination — the one broken component**. What is actually dead is a single
#: DESTINATION, not the oscillator and not its four controls.
#:
#: **For this writer:** `PANRAT` and `PANDEP` are real, working controls worth
#: writing for matrix use; auto-pan itself still will not sound. So the byte we
#: emit was right all along, and the sentence beside it was wrong in a way that
#: would have stopped someone carrying LFO2 across for any destination.
#:
#: Their note on how it happened, which is the durable part: three detectors in
#: one topic could only ever return one answer — a rate that read exactly half
#: above PANRAT 80, a PANDEL onset returning an impossible −0.150 s at every
#: setting because that was the rolling window's floor, and an LFO2TRIG test
#: measuring rate and swing when a trigger mode sets phase. Their §47 rule
#: existed four sections earlier and was violated three times inside this one
#: topic. **Stating a rule is not applying it; the positive control is the only
#: mechanism that has actually caught these.**
#:
#: ---- superseded, kept for the reasoning ----
#:
#: **The pan slot buys nothing, though (s3ked §39, 2026-08-11).** PANDEP,
#: PANRAT, PANDEL, LFO2WAVE and LFO2TRIG produce no measurable change in
#: stereo balance across ~30 settings, all inside the 0.76 dB that the depth-0
#: control shows -- while PANPOS drives the same measured balance across
#: 118 dB in the same session, so the path is alive and the oscillator is not
#: reaching it. Source AND amount together still does nothing.
#:
#: We keep writing the factory PANRAT anyway: it is what a real S3000XL has,
#: and dropping it would diverge from the machine and from `akaiutil` byte
#: identity to no benefit. What changes is the CLAIM above -- the pan routing
#: does not buy a user anything on the one machine measured, so do not carry
#: an auto-pan across from a source format expecting it to sound. s3ked were
#: careful that this is "nothing reachable from these five fields moves the
#: output", NOT "unimplemented": some enabling condition the survey missed
#: remains possible, so this is a reason not to promise auto-pan, not proof
#: the hardware lacks it. (This sentence used to name the IB304F board as that
#: condition. See below -- that attribution has no source.)
#:
#: **AND THAT CAUTION GOT SHARPER THE SAME NIGHT (s3ked §44).**
#: They recorded `PRSDEP` as inert and then found it is not: channel pressure
#: has to arrive DURING the note. Sent before note-on it does nothing; sent
#: 0.4 s after, it is linear across the whole controller range. That is the
#: SECOND field in one day that looked dead because of how it was driven
#: rather than what it does, after `MODSFILT1`. Their own conclusion: vary how
#: a field is driven before recording it as inert.
#:
#: The pan survey drove those five fields one way. It has not been retracted
#: and I am not second-guessing their measurement — but "no auto-pan reaches
#: the output" now rests on a class of conclusion that has been overturned
#: repeatedly on this machine, and the honest weight is lower than it was when
#: this comment was written six hours earlier. Nothing to change in the bytes
#: either way: we write the factory value and carry no auto-pan.
#:
#: **The rate is now quantified (s3ked §47).** Of five fields
#: screened inert in one group, **three verdicts were wrong on the first
#: pass** — `V_ATT2` and `V_REL2` change a TIME and were screened with a median
#: centroid, which a timing change cannot move; `O_REL1` was driven by velocity
#: while the field beside it turned out key-scaled. All three survived
#: re-screening under detectors that could have seen the alternative, so the
#: verdicts stand — but they were artefacts until re-run.
#:
#: Their resulting rule, and it is the one to apply to any inert claim
#: including this one: **before recording a field inert, state what the
#: detector would show if the field worked, and confirm the detector can
#: produce that — before the run.** A negative result is only as good as the
#: demonstrated ability to have produced a positive one.
#:
#: **THE COUNT IS NOW FIVE, NOT FOURTEEN, AND A NEGATIVE NEEDS THE RIGHT
#: STAGE (s3ked, 2026-08-12).** Two of the three groups below were retracted
#: on re-measurement -- the per-zone block works, and the pan LFO works with
#: only its destination dead. Every number in this block that says "fourteen"
#: predates that.
#:
#: Their rule, which is the one to apply to whatever remains: it is not enough
#: to ask whether a field was ROUTED. You must ask whether **the thing it
#: modifies was actually happening at the time.**
#:
#: `K_DAR3` read 0.660..0.670 s at every note and depth -- spread 1.02x,
#: identical to its own control. Live route, flat control, distinct readings,
#: every mechanical check green, and one sentence from being recorded inert.
#: They had timed PHASE 2; the field's own description names the release and
#: the DECAY. Retested against the stages it names, it moves both by 2.6x.
#: The phase-2 reading was a TRUE negative -- the field really does not touch
#: phase 2, at a coefficient 30x smaller. What would have been wrong is the
#: sentence it invited.
#:
#: `V_ATT3` read 0.000 s at every velocity, because the attack rate was set to
#: 0 -- an attack scaler tested on an instant attack. Only a NaN control
#: stopped the verdict. Given a real 1.25 s rise it swings 37-fold.
#:
#: **This failure is invisible from inside the run.** There is no signal in the
#: data: the null is clean, well-behaved and convincing. The only available
#: signal is TEXTUAL -- a field whose description names two stages had been
#: tested on a third. So for any inert claim we inherit or make: an attack
#: scaler on an instant attack, a release scaler on a note that never
#: released, or a decay scaler on a sustain of 100 % all read exactly like a
#: dead field, and no amount of control-tightening will show it.
#:
#: Superseded, and kept because the reasoning still applies to the remainder:
#: **fourteen fields now measure inert across three
#: groups** on that machine, with no visible common factor. If some hardware
#: option is responsible, every one of those fields works on a machine that
#: has it — so "inert" here may mean "inert on one particular machine", which
#: is a different thing from a fact about the format.
#:
#: **SCOPED, 2026-08-12 — and note what is and is not in doubt.** s3ked (§49)
#: cross-checked their night run against the S2800/S3000/S3200 SysEx
#: specification and flagged the IB304F as unsourced: it "appears in neither
#: document consulted". Two earlier versions of this comment had named the
#: board as the obvious explanation for the inert fields, copied from their
#: notes without my once asking where it came from.
#:
#: **But the board is NOT unsourced, and the source is better than a document.**
#: The machine itself refuses with *"2nd filter board IB304F not fitted!"* —
#: first-hand, from their own S3000XL, recorded in our handoff to VinSamLib
#: earlier the same day. What it gates there is `FILTER2`, the TONE page and
#: `ENV3`: fifteen fields that exist in the header on every machine and do
#: nothing without the board, with nothing on the wire distinguishing a fitted
#: machine from an unfitted one.
#:
#: So two claims were travelling as one, and only the second is unsupported:
#:
#:   1. IB304F exists and gates FILTER2 / TONE / ENV3 — evidenced by the
#:      machine's own error message. Stands *as to the panel*; see the
#:      correction below, which takes ENV3 out of it and narrows the rest.
#:   2. IB304F explains the auto-pan, per-zone-velocity and envelope-scaling
#:      fields measuring inert — an extrapolation from (1) to three unrelated
#:      field groups, with nothing behind it. Withdrawn.
#:
#: **Settled the same morning (s3ked §50).** They measured it:
#: `LSI2_ON` reads 0 at factory and `FIL2FR` produces no response swept 20..99
#: with `LSI2_ON` at either value, so the board is genuinely not fitted on that
#: machine. And its function does not cover these fields — the IB304F adds
#: direct-to-disk recording, reverb, a digital EQ and a second filter, not
#: auto-pan. So (2) now has a documentary *refutation* rather than merely no
#: support, and why the remaining fields are inert is open again. `LSI2_ON` is
#: settable over SysEx and means nothing without the hardware, so it cannot be
#: used to detect the board.
#:
#: One consequence worth knowing if envelope 3 is ever wired: it WORKS on that
#: board-less machine through modulation-matrix source 14, which the owner's
#: manual appears to deny. Panel access needs the board; the generator is in
#: firmware. Unreachable from the front panel and fully usable over SysEx.
#:
#: **Settled 2026-08-13 (s3ked §86): that machine has NO expansion boards at
#: all** -- 8 MB of flash ROM and nothing else, no EB16 and no IB304F -- so
#: envelope 3's four stages were measured working on hardware that has never
#: had the board the manual requires for them. The manual is simply wrong
#: about that, and the finding rests on base-machine functionality rather than
#: on an unverified assumption about what was fitted.
#:
#: Worth keeping for what it says about documentation generally: this is the
#: second time this week a manufacturer's own statement has been the thing
#: that was wrong, after the 60 MB partition "maximum" that turned out to be
#: the FORMAT screen's editable default. A document is evidence about intent,
#: not about behaviour.
#:
#: **Correction to claim (1), 2026-08-13 (s3ked §87).** That claim cited the
#: machine's own *"2nd filter board IB304F not fitted!"* refusal as evidence
#: that the board gates those fields — and a panel refusal does not carry that
#: weight. s3ked demonstrated the gap on the sibling board: pressing EFFECTS
#: on their machine with no EB16 does nothing and reports the board missing,
#: but writing 6 to the mode register opens the page anyway, with real preset
#: names, four channels, and data that reads back over a *separate* command
#: path (RFXDATA / FX_ENTRY agree with the display). The effects firmware, UI
#: and preset tables are all in the base machine; the board supplies only the
#: DSP that makes it audible, and the panel simply declines to show an
#: interface it cannot back with audio.
#:
#: So the honest form of claim (1) is: **the panel treats the missing board as
#: a display problem.** Whether the header fields are inert *on the wire* is a
#: separate question that the error message never answered, and ENV3 is now a
#: worked counter-example — it is one of the three the message names, and it
#: works (its whole calibration ran on hardware the gating claim said it could
#: not run on).
#:
#: Note the panel gates the two boards *differently*, which is why a single
#: rule like "the panel refuses" is already too strong: EFFECTS is refused
#: outright with the lamp dark, while the filter-2 page renders with its
#: fields visible and a warning line across it. Same class of absent board,
#: two different behaviours — so panel behaviour does not even predict panel
#: behaviour, let alone wire behaviour. What the IB304F actually gates is the
#: SECOND FILTER (seven genuinely board-dependent fields), which envelope 3
#: can target among other destinations; that is a routing destination for
#: ENV3, not a precondition for it. The general rule, which is the part worth carrying:
#:
#:   A front-panel refusal is a policy of the panel, not a property of the
#:   machine.
#:
#: Consequence for this writer: we do not populate FILTER2 / TONE / ENV3 today
#: (they keep their template defaults, and no source format we read asks for
#: them). If that ever changes, do NOT suppress them on the theory that they
#: are dead weight — but see the hazard below before wiring them.
#:
#: **Hazard, same evening (s3ked, fencing commit).** They now refuse reads and
#: writes to these fifteen fields unless a board is declared fitted, because an
#: S3000XL was crashed twice in one session with the same flooding-display
#: signature while that area was exercised. That is a safety decision about a
#: real machine and we should respect it: if this writer ever populates them,
#: the value of doing so has to be weighed against a documented crash.
#:
#: Note what the hazard is NOT evidence for. Their justification sentence says
#: the fields "belong to the optional IB304F", which is the claim their own
#: correction one hour earlier withdrew for ENV3 specifically — measured
#: working across three sections on a machine that has never had the board.
#: A crash while exercising an area is a reason to fence it; it is not a
#: finding that the fields are board-dependent. Both can be true at once, and
#: only one of them is measured. We keep ENV3 out of the gated list here and
#: carry the crash risk separately, because merging them would relose the
#: distinction that took three corrections to establish. Authoring them on a board-less machine
#: for a program destined for a fitted one is a legitimate thing to do, and it
#: is precisely what a converter is for. Write what the source asks for.
#:
#: This also un-promotes the value-11 reading recorded above: value 6 opens a
#: page for absent hardware without crashing, so "a page for hardware not
#: fitted" is not by itself fatal, and it stops being the leading explanation
#: for value 11. Three readings remain live over there and none is favoured.
#:
#: For those fourteen fields the honest position is that they measure inert on
#: one machine and nobody knows why. Do not name a cause until one has its own
#: provenance — and do not let (1) lend its credibility to (2) because they
#: share a name.
#:
#: What §49 DID confirm verbatim from the specification: `PANRAT`, `PANDEP`
#: and `PANDEL` are genuine LFO2 controls. So the fields we write are real and
#: correctly identified; only their audibility on that one machine is in
#: question.
#:
#: Kept as data rather than inline assignments so tests can suppress it and
#: show that the images still agree with `akaiutil` byte for byte everywhere
#: else -- that agreement is the only independent check this writer has, and
#: it should not be quietly dropped just because we now diverge on purpose.
_PROGRAM_HW_DEFAULTS = {
    0x1d: (  1, 'PANRAT     LFO2 speed'),
    0x49: (  2, 'B_PTCHD    bendwheel pitch-down, 0..12'),
    0x4c: (  8, 'MODSPAN1   -> pan position'),
    0x4d: (  6, 'MODSPAN2   -> pan position'),
    0x4e: ( 12, 'MODSPAN3   -> pan position'),
    0x4f: (  6, 'MODSAMP1   -> loudness'),
    0x50: (  3, 'MODSAMP2   -> loudness'),
    0x51: (  6, 'MODSLFOT   -> LFO1 speed'),
    0x52: (  6, 'MODSLFOL   -> LFO1 depth'),
    0x53: (  6, 'MODSLFOD   -> LFO1 delay'),
    0x54: (  5, 'MODSFILT1  -> filter frequency'),
    0x55: (  8, 'MODSFILT2  -> filter frequency'),
    0x56: ( 10, 'MODSFILT3  -> filter frequency'),
    0x57: ( 10, 'MODSPITCH  -> pitch'),
    0x58: (  5, 'MODSAMP3   -> loudness'),
    0x63: (  5, 'MODSLFLT2_1 -> filter 2 frequency'),
    0x64: (  8, 'MODSLFLT2_2 -> filter 2 frequency'),
    0x65: ( 14, 'MODSLFLT2_3 -> filter 2 frequency'),
    0x72: ( 25, 'PFXSLEV    FX send level (doc: "not used")'),
    0x2b: (  1, 'TPNUM      temporary program number; 1 on all 11 resident programs'),
    # A 7-byte reserved span starts at 0x67; the machine holds these three
    # non-zero. Reserved fields are exactly the ones to copy rather than
    # reason about.
    0x67: (  8, 'RESERVED[0]'),
    0x68: (  8, 'RESERVED[1]'),
    0x6d: ( 69, 'RESERVED[6]'),
}


def _program_common(name: str, n_keygroups: int, lo_key: int, hi_key: int,
                    lfo1_rate=None) -> bytearray:
    """The 192-byte program common block, filled with the format's own
    documented defaults rather than zeros."""
    p = bytearray(PROGRAM_COMMON_LEN)
    # Block id: 1 = program common. This is NOT the sampler generation --
    # every real program carries 1 whether it is S1000 or S3000, and the
    # generation lives in the directory entry's file type instead.
    p[0x00] = _BLOCK_ID_PROGRAM
    struct.pack_into('<H', p, 0x01, _RAM_BASE_PARA)
    p[0x03:0x03 + AKAI_NAME_LEN] = str_to_akai(name)
    p[0x0f] = 0                         # MIDI program number
    # PMCHAN. "255 signifies OMNI, 0 to 15 indicate MIDI channel" -- the
    # S2800/S3000/S3200 document, offset 16. Verified 2026-08-10 against a real
    # S3000XL whose own program 0 holds 0 (channel 1): that is the channel that
    # program was created with, not a different convention. Omni is the right
    # default for a converted program, which has no channel of its own.
    p[0x10] = 0xff                      # MIDI channel: omni
    p[0x11] = 31                        # polyphony
    p[0x12] = 1                         # priority: normal
    # Play range is a filter over the whole program, not a description of the
    # keys in use: 96% of real programs set it to the full 24-127 span
    # regardless of where their keygroups sit. Narrowing it to the keygroups
    # sounds the same today but silently mutes any keygroup added later on the
    # sampler itself.
    p[0x13] = 24
    p[0x14] = 127
    p[0x15] = 0                         # octave shift
    p[0x16] = 0xff                      # individual output: off
    p[0x17] = 99                        # stereo level
    p[0x18] = 0                         # pan
    p[0x19] = 80                        # loudness
    p[0x1a] = 20                        # velocity > loudness
    p[0x1e] = 99                        # pan depth
    # LFO1 speed. Fixed at 50 until 2026-08-11; now from the source when it
    # carries an LFO rate, through the measured linear law. A preset with no
    # LFO data keeps the old default so those conversions stay byte-identical.
    p[0x21] = (akai_lfo_rate_byte(lfo1_rate) if lfo1_rate is not None else 50)
    p[0x24] = 30                        # modwheel > depth
    p[0x27] = 2                         # bendwheel > pitch
    p[0x2a] = _clamp(n_keygroups, 1, MAX_KEYGROUPS)
    p[0x3e] = 10                        # soft pedal loudness reduction
    p[0x3f] = 10                        # soft pedal attack stretch
    p[0x40] = 10                        # soft pedal filter close
    p[0x46] = 50                        # voice output scale

    # Modulation matrix and the rest, from a real S3000XL -- see
    # _PROGRAM_HW_DEFAULTS above for why these are not zero.
    for _off, (_val, _what) in _PROGRAM_HW_DEFAULTS.items():
        p[_off] = _val

    # TPNUM ("temporary program number, internal use"). Left at zero until
    # 2026-08-10 because one sample could not distinguish a constant from a
    # per-program index. s3ked then read ELEVEN resident programs, ten of them
    # loaded from a library disc, and every one holds 1. Constant, so copy it.
    #
    # Caveat kept because it is theirs: those ten arrived by loading a disc, so
    # either the disc carried 1 or the machine normalises it on load. Both
    # readings make 1 the right thing for us to write.
    return p


def _keygroup(lo_key: int, hi_key: int, zones, index: int = 0,
              voice=None, dead_key_ranges=None) -> bytearray:
    """One 192-byte keygroup with up to four velocity zones."""
    k = bytearray(KEYGROUP_LEN)
    k[0x00] = _BLOCK_ID_KEYGROUP
    # Own RAM address: one block past the previous one.
    struct.pack_into('<H', k, 0x01,
                     _RAM_BASE_PARA + _BLOCK_PARA * (index + 1))
    # THE PAIR HAS A CONSTRAINT THE MEMBERS DO NOT.
    #
    # These were two independent clamps, so a malformed source with lo=72
    # hi=60 was written verbatim -- each key individually legal, the pair not.
    # Same shape as the width-versus-range fault: clamping members separately
    # cannot catch a constraint that exists between them.
    #
    # An inverted key range is DEAD, measured on an S3000XL (s3ked, 2026-08-13,
    # note 60 at velocity 100, 52.5 dB isolation): 72..48 reads 0.00003 RMS
    # against 0.00711 for a range spanning the note -- 242x down, the same
    # floor as a range that simply excludes it. The machine stores 72..48
    # verbatim rather than swapping or clamping, so it does not defend itself.
    #
    # `lo == hi` is REACHABLE and must survive: 60..60 measured 0.00712 on its
    # own note, the full-range level to three digits, and 0.00003 one semitone
    # away. A `lo < hi` guard would kill a legitimate one-key keygroup.
    #
    # Reported rather than repaired. Swapping the pair guesses that the source
    # meant the reverse, and nothing supports that; skipping would drop the
    # sample silently. The keygroup is written as asked and the caller is told
    # it cannot sound, which is the one outcome the user can act on.
    lo_b, hi_b = _clamp(lo_key, 24, 127), _clamp(hi_key, 24, 127)
    if lo_b > hi_b and dead_key_ranges is not None:
        dead_key_ranges.append((lo_b, hi_b))
    k[0x03] = lo_b
    k[0x04] = hi_b
    _put_s16(k, 0x05, 0)                # tune offset
    # Filter frequency, fully open. CONFIRMED ON HARDWARE 2026-08-11 by the
    # s3ked project: keygroup offset 7 IS the basic filter frequency, and 99
    # is genuinely wide open.
    #
    # The measurement, once the program under test was isolated on its own
    # MIDI channel: RMS falls monotonically by 47.5 dB from FILFRQ 50 down to
    # 0 (-42.6 dB to -90.1 dB, the latter being the noise floor of a shut
    # filter). Above ~55 the LEVEL plateaus within 1 dB while the spectral
    # centroid keeps climbing, 945 Hz to 1813 Hz -- a low-pass whose corner
    # has passed the fundamental, gaining no more level but admitting
    # progressively more harmonics.
    #
    # Getting here took two retractions and both are worth remembering:
    #
    #   * an earlier sweep found offset 7 did nothing audible. Every note had
    #     sounded the program under test buried beneath ten library programs,
    #     all resident on MIDI channel 1. The instrument was validated
    #     carefully; nobody validated what it was pointed at.
    #   * FILFRQ round-trips perfectly over SysEx, and both projects had been
    #     reading that as evidence the offset was right. It never was -- a
    #     wrong offset writes somewhere real and reads back clean. That trap
    #     survives the good news and is the durable lesson here.
    #
    # FILQ (keygroup 149) is NOT required for the filter to act; it rested at
    # 0 throughout, and we still write nothing to it.
    #
    # A law now exists if resonance is ever carried across (s3ked §52,
    # 2026-08-12), replacing their own earlier linear 0.5764 dB/step:
    #
    #     damping z = 0.46864 - 0.029587 * FILQ      r2 0.999975
    #     dB        = -20 log10(1 - FILQ / 15.84)
    #     Q         = 1.067 / (1 - FILQ / 15.84)     1.07 at 0, ~20 at 15
    #
    # Damping reaches zero at 15.84, past the top of the field, so the machine
    # stops just short of self-oscillation and one number generates all sixteen
    # steps. The linear reading had the shape backwards -- the last three steps
    # are worth more than the first ten together.
    #
    # NOT WIRED. It is twenty minutes old and retracts a law of their own; our
    # model carries `filter_resonance` and drops it for AKAI today. Recorded as
    # available.
    k[0x07] = (akai_filter_byte(voice.filter_cutoff)
               if voice is not None and getattr(voice, 'filter_cutoff', None) is not None
               else 99)     # wide open (HW-confirmed) when unknown
    # Amp envelope, from the source, through the HW-measured laws. These were
    # FIXED defaults until 2026-08-11 -- every converted program got the same
    # envelope and the same wide-open filter whatever the source asked for,
    # because no curve existed to convert with. See the laws above for what
    # range each was actually fitted over; values outside it clamp rather than
    # extrapolate.
    _env = getattr(voice, 'amp_env', None) if voice is not None else None
    if _env is not None:
        _a, _d, _s, _r = akai_env_bytes(_env)
    else:
        _a, _d, _s, _r = 0, 50, 99, 45     # the historical defaults
    k[0x0c] = _a                        # amp attack
    k[0x0d] = _d                        # amp decay
    k[0x0e] = _s                        # amp sustain
    k[0x0f] = _r                        # amp release
    # ENVELOPE 2 (filter): DECAY2 / SUSTN2 / RELSE2 at doc offsets 21/22/23.
    # DELIBERATELY STILL FIXED, while the amp envelope above now follows the
    # source. These are a SEPARATE parameter set from ATTAK1/DECAY1/RELSE1,
    # and s3ked measured envelope 1 only. Applying envelope 1's laws here
    # would be assuming two parameter sets share a scale -- which is exactly
    # what produced VinSamLib's 16x tuning error (they had labelled the
    # keygroup tune 1/16 semitone by inheriting a neighbour's unit) and what
    # s3ked's STUNO result disproves in general: identical wording and
    # identical ranges are not evidence of identical behaviour.
    #
    # Our model does carry a filter envelope, so wiring this is a small change
    # the moment envelope 2 is measured. Until then fixed values are the
    # honest option, exactly as they were for the amp envelope until
    # 2026-08-11. Asked of s3ked.
    #
    # Note we also never write ATTAK2 (offset 20), which therefore stays 0.
    # (The sentence that used to follow this one said the filter envelope's
    # attack "follows the source". It has not since the slew-rate retraction,
    # and it contradicted the line above it. Stale by two lines, which is how
    # long a comment survives a reverted feature.)
    #
    # NOTHING in envelope 2 is wired, and as of 2026-08-12 that is the lucky
    # position rather than the cautious one: s3ked measured DECAY2, RELSE2,
    # ATTAK2 and SUSTN2 through the spectral-centroid ruler that also produced
    # their wrong FILFRQ law, and have flagged all four as suspect pending
    # re-measurement with the resonance-peak tracker. Had we wired them when
    # they were first offered, we would now be shipping a correction.
    # ENVELOPE 2 TIMINGS ARE FIXED AGAIN. They were wired this morning from
    # a model s3ked has since retracted: an envelope value is a slew RATE, so
    # converting a time needs the span the stage travels. For envelope 2 that
    # span is how far the FILTER sweeps, in FILFRQ units, and our model
    # carries no filter-envelope amount -- there is nothing to divide by.
    # Reverting is not a regression: a value derived from a retracted law is
    # worse than a neutral default because it looks like intent.
    k[0x14] = 0                         # ATTAK2  -- no usable law
    k[0x15] = 50                        # DECAY2  -- no span in our model
    k[0x17] = 45                        # RELSE2  -- no span in our model
    k[0x16] = 99                        # SUSTN2  -- unmeasured, fixed
    k[0x1c] = 25                        # velocity > filter envelope
    k[0x1e] = 0                         # velocity zone crossfade off
    struct.pack_into('<H', k, 0x20, _NO_POINTER)    # 0xFFFF on every real keygroup
    # 0x1f was taken for "number of zones used". Real media disagrees: every
    # keygroup on every disc of the corpus carries 4 here regardless of how
    # many zones it actually uses, so it is not a count and writing one would
    # be inventing a meaning. Whatever it is, 4 is what the sampler writes.
    k[0x1f] = MAX_ZONES_PER_KEYGROUP

    for i, z in enumerate(zones[:MAX_ZONES_PER_KEYGROUP]):
        o = _ZONE_OFFSETS[i]
        k[o:o + AKAI_NAME_LEN] = str_to_akai(z['sample_name'])
        k[o + 0x0c] = _clamp(z.get('lo_vel', 0), 0, 127)
        k[o + 0x0d] = _clamp(z.get('hi_vel', 127), 0, 127)
        # OPEN QUESTION, 2026-08-12 (s3ked §45). They screened
        # VLOUD1, VFREQ1, VTUNO1 and VPANO1 -- which are exactly these four
        # bytes for zone 1 -- and recorded all of them INERT: no measurable
        # response on level, centroid, pitch or balance.
        #
        # If that holds as stated, every per-zone offset written here does
        # nothing, including the sample fine-tune we take real care over.
        #
        # But it may be testing a different hypothesis than ours. They swept
        # VELOCITY 1..127 looking for a response, and their rig has a sample in
        # ZONE 1 ONLY -- so a velocity sweep never leaves zone 1, and a STATIC
        # zone-1 offset is constant across that sweep by construction. Our
        # reading of the document is that these are static per-zone offsets,
        # not velocity->X modulation depths: they sit immediately after this
        # zone's lo_vel/hi_vel, and the document gives VTUNO1-4 the identical
        # structural wording as KGTUNO and PTUNO, which are plainly static.
        # On that reading the discriminating test needs no velocity sweep at
        # all -- set the field to each extreme at FIXED velocity and look for a
        # difference.
        #
        # RESOLVED 2026-08-12, 06:49 (s3ked, retracting §45): **§45 IS RETRACTED and
        # these fields all work.** Measured at a FIXED velocity with each field
        # at both extremes -- VTUNO1 19.39 cents across 0..50, VLOUD1 39.81 dB,
        # VFREQ1 3346 Hz, VPANO1 118.57 dB (the same span as PANPOS).
        #
        # The fault was the one predicted here: their detector returned the
        # velocity SPREAD and compared it at the field's two extremes. For a
        # static offset that spread is zero at both, so the difference is zero
        # and the field reads inert whether it works or not. The V in these
        # names is the velocity ZONE the field belongs to -- LOVEL1/HIVEL1
        # define the zone, these four are its offsets -- not velocity as a
        # modulation source.
        #
        # **And our 1/256-semitone scale is now confirmed by measurement.**
        # VTUNO1 comes out at 0.3878 cents/unit against the 0.390625 we take
        # structurally from the document, 0.7% apart. We chose that scale from
        # the spec's wording rather than from any fit, so this is a measurement
        # the constant was never fitted to -- the standard recorded in
        # docs/RESOLUTION_NOTES.md §AGREEMENT for what actually earns trust.
        #
        # Their rule from the episode, worth more than the fields: **a
        # screening batch in which NOTHING responds has not validated its own
        # detector.** §47 survived because K_DAR1 responded in the same run
        # through the same detector shape; §45 had four fields and four
        # negatives with nothing establishing the detector could register
        # anything at all.
        # Range settled by MEASUREMENT 2026-08-12 (s3ked §57), see
        # _AK_TUNE_MAX. This clamped to the s16 width until then, because the
        # document and their parameter table disagreed by 256x and guessing a
        # tuning scale is how this writer was 100x and then 6.25x out before.
        _put_s16(k, o + 0x0e, _clamp(z.get('tune', 0), -_AK_TUNE_MAX, _AK_TUNE_MAX))
        # FITTING IN THE WIDTH IS NOT THE SAME AS BEING IN THE RANGE.
        # VLOUD1 is a ONE-BYTE field whose declared range is -50..+50, and this
        # clamped to 0..255 -- the byte's capacity, not the field's range. Any
        # value in between encodes cleanly and goes to the machine.
        #
        # Unreachable today: nothing sets 'loudness' in the zone dict, so this
        # is always 0. It is fixed because the failure mode is silent the
        # moment somebody wires per-zone loudness. s3ked, 2026-08-12: their
        # encoder guarded only fields with a display offset, a probe asked for
        # MODVFILT1 = 60 against a -50..+50 range, the byte was duly sent, and
        # the filter modulated the wrong way for a full run.
        k[o + 0x10] = _clamp(z.get('loudness', 0), -50, 50) & 0xff
        k[o + 0x11] = 0                 # filter frequency offset
        k[o + 0x12] = _clamp(z.get('pan', 0), -50, 50) & 0xff
        k[o + 0x13] = 0                 # loop in release
        # Four bytes of pointer per zone -- two 16-bit fields, both 0xFFFF
        # for "no address yet". The first is 0xFFFF on 100% of real keygroups;
        # the second holds the sample's RAM address once the sampler has
        # loaded it, and is 0xFFFF on every zone that has not been.
        struct.pack_into('<H', k, o + 0x14, _NO_POINTER)
        struct.pack_into('<H', k, o + 0x16, _NO_POINTER)

    # Mark the remaining zones as the sampler does: an **inverted velocity
    # range** (lo 1, hi 0) so nothing can select them. Real programs leave a
    # leftover sample name in place and rely on this alone -- across the disc
    # corpus every one of 5 990 disabled zones is exactly (1, 0). Leaving them
    # all-zero instead was a guess, and a bad one: 0x00 decodes to the digit
    # '0', so a zeroed zone reads back as a sample named "000000000000".
    for i in range(len(zones), MAX_ZONES_PER_KEYGROUP):
        o = _ZONE_OFFSETS[i]
        # Blank the name with SPACES, not zeros: 0x00 decodes to the digit '0',
        # so a zeroed name reads back as the sample "000000000000". Real
        # keygroups leave spaces or a stale name here.
        k[o:o + AKAI_NAME_LEN] = str_to_akai('')
        k[o + 0x0c] = 1                 # lo_vel
        k[o + 0x0d] = 0                 # hi_vel  -> no velocity matches
        struct.pack_into('<H', k, o + 0x14, _NO_POINTER)
        struct.pack_into('<H', k, o + 0x16, _NO_POINTER)
    return k


def build_program(preset, name: str) -> bytes:
    """One Preset -> a complete `.a3p` file.

    Zones are grouped into keygroups by key range: the AKAI keygroup owns a
    key span and holds up to four VELOCITY zones within it, which is the
    inverse of how the common model nests them.
    """
    by_range: dict = {}
    order = []
    # Keep the owning VOICE beside each zone. An AKAI keygroup is keyed on a
    # KEY RANGE, while our model nests zones under voices (layers), so one
    # keygroup can collect zones from several voices and there is no single
    # owner. The filter and envelope have to come from somewhere, so the rule
    # is: the voice owning the LOWEST-VELOCITY zone in the keygroup. Stated
    # here rather than left implicit, because it is a real lossiness -- a
    # keygroup built from two voices with different envelopes keeps one of
    # them.
    for voice in preset.voices:
        for z in voice.zones:
            key = (z.lo_key, z.hi_key)
            if key not in by_range:
                by_range[key] = []
                order.append(key)
            by_range[key].append((z, voice))

    keygroups = []
    dropped = 0
    for key in order:
        # ONE KEYGROUP PER KEY SPAN, AND OVERLAPPING SPANS LAYER.
        #
        # Any layered multisample produces keygroups whose key ranges overlap.
        # This construction assumes both answer a note in the overlap -- and
        # if only one did, every layered program we write would lose voices
        # SILENTLY, with no file inspection able to show it.
        #
        # Measured on an S3000XL 2026-08-13 (s3ked), on a program built for
        # the purpose rather than found, since a real program carries its
        # author's intent. Two keygroups overlapping on note 60:
        #
        #     A only  (SINE)     0.01999 RMS   3f0/f0 0.000
        #     B only  (SQUARE)   0.01981       3f0/f0 0.335
        #     BOTH               0.03377       3f0/f0 0.184
        #
        # The discriminator is the SAMPLE, not the level: two keygroups playing
        # one sample sum coherently and +6 dB is not reliably distinguishable
        # from a single louder voice. SINE against SQUARE lets the third
        # harmonic say WHICH voice is present.
        #
        # Three readings agree. The RMS exceeds the loudest single AND the
        # incoherent power sum (0.02814) while staying under the coherent
        # amplitude sum (0.03980) -- the middle ground two partly-in-phase
        # voices predict, and neither endpoint. The third harmonic lands at
        # 0.184 against 0.167 predicted. And SINE alone reads exactly 0.000,
        # which validates the marker rather than assuming it.
        #
        # NOT established: what happens when overlapping voices exceed
        # polyphony. That is a resource limit, not a routing rule, so this is
        # not a promise about voice count.
        pairs = sorted(by_range[key], key=lambda zv: zv[0].lo_vel)
        zs = [z for z, _ in pairs]
        owner = pairs[0][1] if pairs else None
        if len(zs) > MAX_ZONES_PER_KEYGROUP:
            dropped += len(zs) - MAX_ZONES_PER_KEYGROUP
            zs = zs[:MAX_ZONES_PER_KEYGROUP]
        keygroups.append((key, owner, [dict(
            sample_name=z.sample_name,
            lo_vel=z.lo_vel, hi_vel=z.hi_vel,
            # VTUNO1..4 (offsets 48/72/96/120). VinSamLib's parser, written
            # separately, derives the same four zone bases (0x22/0x3A/0x52/
            # 0x6A) and the same +0x0E tune offset. Worth stating what that
            # does and does not establish, because it is the same shape as
            # s3ked's "two detectors rule out detector error, not model
            # error": both readings come from ONE document, so agreement rules
            # out TRANSCRIPTION error and says nothing about whether the
            # document is right. It is still worth having -- transcription is
            # what actually goes wrong when four near-identical offsets are
            # copied by hand -- but it is not hardware corroboration.
            #
            # We apply the 1/256-semitone
            # scale here, and the justification is NOT "the neighbouring field
            # was measured" -- that is the move that produced VinSamLib's 16x
            # and that STUNO disproves. It is that the DOCUMENT gives these
            # the identical structural wording as KGTUNO and PTUNO:
            #
            #   KGTUNO / PTUNO / VTUNO1-4  "-50.00 to +50.00 (fraction is
            #                               binary)"   <- structural claim
            #   STUNO                      "cent:semi" <- different wording,
            #                               and measured to do NOTHING
            #
            # and that KGTUNO and PTUNO were then independently measured at
            # 0.3928 and 0.3866 cents/unit against the 100/256 = 0.390625 that
            # wording predicts. So the claim is the format's, made about four
            # fields at once, and confirmed on two of them by separate sweeps.
            #
            # That is stronger than inheritance and weaker than measurement.
            # VTUNO has not been swept, and if it ever is and disagrees, this
            # is the line to change.
            tune=_akai_tune_units(_or_default(getattr(z, 'fine_tune', None), 0)),
            # `ZoneMapping.pan` is -1.0..+1.0 centred on 0.0; the AKAI field
            # is -50..+50 centred on 0. This used to subtract 0.5 first, on
            # the assumption of a 0..1 scale -- which put every *centred* zone
            # hard left. It went unnoticed because `or 0.5` rewrote the 0.0
            # that would have exposed it.
            pan=int(round(_or_default(getattr(z, 'pan', None), 0.0) * 50)),
        ) for z in zs]))

    if dropped:
        print(f"    [WARN] {dropped} velocity zone(s) dropped — an AKAI keygroup "
              f"holds at most {MAX_ZONES_PER_KEYGROUP}")
    if len(keygroups) > MAX_KEYGROUPS:
        print(f"    [WARN] {len(keygroups)} key ranges — AKAI allows "
              f"{MAX_KEYGROUPS}; the highest {len(keygroups)-MAX_KEYGROUPS} dropped")
        keygroups = keygroups[:MAX_KEYGROUPS]
    if not keygroups:
        raise ValueError(f"preset '{name}' has no zones to write")

    lo = min(k[0][0] for k in keygroups)
    hi = max(k[0][1] for k in keygroups)
    # LFO rate from the first voice that carries one -- the AKAI LFO is per
    # PROGRAM while ours is per voice, so there is one to pick and this is it.
    _lfo = next((v.lfo1_rate for v in preset.voices
                 if getattr(v, 'lfo1_rate', None) is not None), None)
    out = _program_common(name, len(keygroups), lo, hi, lfo1_rate=_lfo)
    dead: list = []
    for i, ((klo, khi), owner, zs) in enumerate(keygroups):
        out += _keygroup(klo, khi, zs, i, voice=owner, dead_key_ranges=dead)
    if dead:
        # Loud, because the failure it describes is silent on the machine: the
        # keygroup loads, occupies a directory entry, and never sounds.
        print(f"  [WARN] program '{name}': {len(dead)} keygroup(s) have an "
              f"INVERTED key range {dead[:3]}"
              + (" ..." if len(dead) > 3 else "")
              + " -- written as asked, but a range whose low key is above its "
                "high key cannot sound (measured on an S3000XL). The source "
                "gave the pair in that order; nothing here guesses what it "
                "meant.", file=sys.stderr)
    return bytes(out)


def build_akai_volume(bank: Bank, bank_name: Optional[str] = None,
                      quiet: bool = False) -> list:
    """Build a Bank's AKAI volume contents as ``[(filename, data), ...]``.

    One file per program and per sample, which is how the sampler's own
    volumes are laid out.  Names carry the canonical `.S3` / `.P3` extensions:
    those are not decoration, the directory-entry file-type byte is derived
    from them, so a file without one cannot be placed on a disk at all.
    """
    files: list = []

    # AKAI names are 12 characters, shorter than the 16 the rest of the
    # pipeline uses, so they can collide here even when they did not before.
    taken: set = set()

    def uniq(stem: str) -> str:
        # KEYED ON THE WRITTEN FIELD, not on the Python string.
        #
        # str_to_akai() space-pads to 12, so 'BASS' and 'BASS ' produce
        # BYTE-IDENTICAL name fields. Keying `taken` on the raw string called
        # those distinct and wrote both -- two samples with the same name in
        # one volume, which is exactly the ambiguity this function exists to
        # prevent. An AKAI zone references its sample BY NAME, the machine
        # enforces no uniqueness (s3ked measured it 2026-08-13: two resident
        # samples both named SINE, ten before and ten after), and a zone
        # naming the duplicate cannot be resolved to either one.
        #
        # Found because s3ked asked whether our uniquifier could emit names
        # differing only in whitespace -- they were checking for a false
        # positive in their auditor and found a real defect in our writer. I
        # had told them our output could not contain this.
        #
        # Leading whitespace does not collide (the charset keeps it), so a
        # rstrip would also work; keying on the bytes is exact by construction
        # rather than by an argument about which cases pad away.
        # A NAME CAN VANISH IN THE CHARSET, NOT ONLY BE EMPTY.
        #
        # str_to_akai substitutes anything the AKAI alphabet lacks with a
        # space rather than refusing it, so a name of entirely unsupported
        # characters -- CJK, punctuation, whitespace -- encodes to TWELVE
        # SPACES. s3ked measured that twelve spaces is exactly what an
        # UNASSIGNED zone holds, so such a sample would be written with a name
        # field indistinguishable from an empty slot, and their audit reads it
        # as unassigned.
        #
        # `stem or 'SAMPLE'` caught the empty string and nothing else, because
        # a non-empty name that ENCODES to nothing is still truthy.
        base = (stem or 'SAMPLE').upper()[:AKAI_NAME_LEN]
        if not bytes(str_to_akai(base)).strip(bytes([_AKAI_SPACE])):
            base = 'SAMPLE'
        cand = base
        n = 1
        while bytes(str_to_akai(cand)) in taken:
            suf = str(n)
            cand = base[:AKAI_NAME_LEN - len(suf)] + suf
            n += 1
        taken.add(bytes(str_to_akai(cand)))
        return cand

    renamed: dict = {}
    for sd in bank.samples:
        nm = uniq(sd.name)
        if nm != sd.name.upper()[:AKAI_NAME_LEN]:
            renamed[sd.name] = nm
        # The AKAI name field tolerates characters a filename does not.
        fn = f"{safe_filename(nm.strip(), 'SAMPLE')}.S3"
        files.append((fn, build_sample(sd, name=nm)))
        if not quiet:
            print(f"  Sample: {fn} ({sd.sample_rate}Hz, {len(sd.data)//2} frames)")
    if renamed and not quiet:
        print(f"    [INFO] {len(renamed)} sample name(s) shortened to the AKAI "
              f"12-character limit")

    name_map = {sd.name: (renamed.get(sd.name) or sd.name.upper()[:AKAI_NAME_LEN])
                for sd in bank.samples}
    for i, preset in enumerate(bank.presets):
        if not preset.voices:
            continue
        pname = ((bank_name or preset.name) if len(bank.presets) == 1
                 else preset.name)[:AKAI_NAME_LEN]
        # Zones address samples by name, so they must use the AKAI-shortened
        # ones or the program will reference files that were never written.
        for v in preset.voices:
            for z in v.zones:
                z.sample_name = name_map.get(z.sample_name, z.sample_name)
        fn = f"{safe_filename((pname or f'PROGRAM{i}').strip().upper(), 'PROGRAM')}.P3"
        files.append((fn, build_program(preset, pname)))
        if not quiet:
            print(f"  Program: {fn} "
                  f"({sum(len(v.zones) for v in preset.voices)} zone(s))")
    return files


def write_akai_bank(bank: Bank, output_dir: str,
                    bank_name: Optional[str] = None) -> list:
    """Write a Bank as loose AKAI `.S3` + `.P3` files. Returns the paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for fn, data in build_akai_volume(bank, bank_name):
        p = out / fn
        p.write_bytes(data)
        written.append(p)
    return written
