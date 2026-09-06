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

import hashlib
import math
import struct
import sys
from pathlib import Path
from typing import Optional

from models.common import (
    AKAI_VLOUD_SWING_DB_PER_UNIT, fit_velocity_line,
    VELOCITY_CURVE_DB_LINEAR, VEL_VOL_PIVOT_AKAI,
    AKAI_LFO_DEPTH_CAL_LPTCH,
    akai_01_to_filq,
    KEY_FILTER_OCT_PER_OCT,
    AKAI_FILTER_LAW, AKAI_FILTER_OPEN, AKAI_FILTER_OPEN_HZ, akai_filfrq_to_hz,
    AKAI_ENV2_ATTACK, AKAI_ENV2_DECAY, AKAI_ENV2_RELEASE,
    AKAI_ENV2_DEPTH_OFFSET, AKAI_ENV2_DEPTH_MAX, akai_lfo2_rate_byte,
    Bank, LoopType, SampleData, safe_filename,
                           E4B_CUTOFF_MIN_HZ, E4B_CUTOFF_MAX_HZ, hz_to_e4b_cutoff)
from parsers.akai_s3000_parser import (
    AKAI_KGMUTE_OFFSET, AKAI_KGMUTE_OFF,
    str_to_akai, akai_to_str, AKAI_NAME_LEN, SAMPLE_HEADER_LEN, PROGRAM_COMMON_LEN,
    KEYGROUP_LEN, _ZONE_OFFSETS, _BLOCK_ID_PROGRAM, _BLOCK_ID_KEYGROUP,
    _BLOCK_ID_SAMPLE,
)

#: THE ONLY RATES THE S3000XL CAN PLAY. **Hardware-confirmed 2026-08-18** by
#: s3ked, who wrote sample-header byte 0x01 over SysEx on a RESIDENT sample and
#: measured the pitch, in both directions, with SSRATE untouched throughout:
#:
#:     SSRATE 44100, byte 0x01 = 1  ->  300.0 Hz   (baseline)
#:     SSRATE 44100, byte 0x01 = 0  ->  150.0 Hz   half speed
#:     SSRATE 22050, byte 0x01 = 0  ->  300.0 Hz   (baseline)
#:     SSRATE 22050, byte 0x01 = 1  ->  600.0 Hz   double speed
#:
#: **Byte 0x01 SELECTS the playback rate. SSRATE at 0x8a is descriptive only.**
#: It had been commented here as "bandwidth: 0 = 10 kHz, 1 = 20 kHz" and written
#: from `1 if sample_rate >= 30000 else 0` -- a threshold that exists nowhere but
#: in this file. That produced a header which reads back perfectly correct and a
#: sample which plays at the wrong pitch: a 48 kHz source, i.e. most modern
#: material, got flag 1, played at 44100 and came out **147 cents flat, silently**.
#:
#: A CLASSIFICATION CANNOT FIX THIS -- the audio has to BE one of these rates.
#: `akai_target_rate()` says which one to resample to; the flag then merely
#: reports it. Kept as a set rather than two literals because whether the field
#: is one bit or a small enum is still open (§AKAIRATEQUANT): if more rates
#: appear, this constant changes and nothing else does.
AKAI_PLAYBACK_RATES = (22050, 44100)

#: SPTYPE value meaning "no looping" -- what build_sample writes for a one-shot.
_SPTYPE_NO_LOOP = 2

#: PMCHAN for a converted program: MIDI channel 1. Measured from 1545 factory
#: volumes that put every program on channel 0, against ~35 using several and 3
#: programs in 11410 using OMNI.
_AKAI_DEFAULT_PMCHAN = 0

#: Derive sample-header 0x10 (active-loop count) from the loop state rather than
#: writing 1 unconditionally. Real output always wants True; the akaiutil
#: byte-identity tests flip it off, because akaiutil writes 1 for everything and
#: those hashes are only worth keeping while they compare us against an
#: INDEPENDENT implementation rather than against our own last output.
_ACTIVE_LOOP_COUNT_FROM_STATE = True

#: byte 0x01 value for each playable rate.
_AKAI_RATE_FLAG = {22050: 0, 44100: 1}

from models.diagnostics import (emit as _diag, WARNING as _W,
                                INFO as _I)

def akai_target_rate(rate: int) -> int:
    """The supported rate a sample at `rate` should be resampled to.

    Up to 44100 for anything above 22050, so no bandwidth the machine could
    have played is thrown away; 22050 for anything at or below, so a low-rate
    sample is not inflated fourfold on a machine with 32 MB.  Deliberately not
    "nearest": nearest sends 32000 down to 22050 and lowpasses it to 11 kHz.
    """
    return 22050 if rate <= 22050 else 44100


def akai_playback_rate(rate: int) -> int:
    """The rate the machine will ACTUALLY play a sample stored at `rate`.

    Equal to `rate` only when `rate` is supported; otherwise the flag we write
    picks a neighbour and the sample plays at the wrong speed.  This is what
    makes the warning in `build_sample` able to state the error in cents.
    """
    if rate in _AKAI_RATE_FLAG:
        return rate
    return akai_target_rate(rate)


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

_UNSET = object()          # 'this name is free', distinct from 'held by None'
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
#: SUPERSEDED 2026-08-12 -> 2026-08-20, kept only so the long provenance note
#: above still has its subject. **The writer no longer uses it.** s3ked §54
#: fitted this to the RESONANCE PEAK as an indicator of the corner; their §139
#: measured the corner directly and the two disagree by a constant 1.29x, which
#: is open on their side. §54 was never retracted, because it is still correct
#: as written -- which is exactly the trap §IDENTIFIERS records, so it is
#: marked here rather than left to be discovered by using it.
_AK_FILTER_SUPERSEDED = (6.4597, 0.07100, 44, 92)    # Hz -- see AKAI_FILTER_LAW
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
# RELSE1 REFITTED 2026-08-24 (s3ked), 11 points, log-space r2 0.99996. The
# constants barely move -- the VALUE of the run is the RANGE: **validated
# 45..99 where it was 55..70**, so the 8.7% of corpus keygroups above the old
# window are now measured rather than extrapolated, and this program's own
# RELSE1 75 with them.
#
# It also REFUTED a hypothesis of ours, which is the more useful half. We
# expected the curve to flatten above the fit, making the true release several
# seconds and explaining a difference Jan heard. It does not flatten: worst
# error 4.1% at RELSE1 99, twenty-nine units above the old top, and at 75 the
# measured release is 2.62 s against 2.59 s extrapolated. Whatever he is
# hearing, it is not the fit range (§LAWRANGE).
#
# BELOW 45 IS STILL UNVALIDATED and s3ked marked it rather than filling it: at
# RELSE1 35 and below their fit collapses to r2 0.51-0.73 AND stops depending
# on the setting -- 194, 192, 209, 155, 256, 305 dB/s for bytes 0..25.
# Non-monotonic and roughly constant is the signature of measuring the rig's
# own tail rather than the envelope, because the release is over in a
# millisecond or two.
_AK_RELSE1_RATE = (23042.3, -0.09754, 45, 99)   # dB/s,  log-space r2 0.99996

#: ATTAK1 -> seconds: `t = a * exp(b * ATTAK1)`, a RISE TIME and not a rate.
#: HW-MEASURED by s3ked (§141, 2026-08-20), time from note-on to 90% of the
#: plateau on a resident sine held at SUSTN1 99:
#:
#:      ATTAK1 70  0.320 s      ATTAK1 90  3.140 s
#:      ATTAK1 80  1.060 s      ATTAK1 99  8.600 s
#:
#: against `0.9 * a * exp(b * ATTAK1)` -- the 0.9 because t90 is 90% of a
#: LINEAR ramp -- the ratio is 0.982, sd 0.06, reproduced here independently.
#: ATTAK1 99 sits outside the 55..90 fit and still lands at 1.033.
#:
#: **The ramp is linear in amplitude, and that was established without any
#: fitted constant**: t50/t90 measured 0.500/0.547/0.548/0.558 over ATTAK1
#: 70..99, against 0.556 predicted for a linear ramp and 0.301 for an
#: exponential approach. A ratio of two numbers from one capture cancels the
#: level calibration, the plateau definition and the rig.
#:
#: Below ATTAK1 70 the times collapse into the 20 ms analysis window and are
#: floor-limited -- recorded as unmeasurable, NOT as disagreement, so the law
#: is extrapolated there and the clamp below is the only guard.
#: **WHY THIS WAS A FIXED 0 FOR TWELVE DAYS, corrected 2026-08-20.** The
#: writer's justification quoted s3ked §29 -- "attack fits neither a rate nor a
#: duration" -- which was true when written and **withdrawn the same day by
#: their §31**, once four models were fitted per curve: a linear-in-amplitude
#: ramp read on a dB axis is a curve, and a slope taken from the middle of a
#: curve depends on how far the curve extends, so the span-dependence was the
#: detector rather than the field. §31 names ATTAK1 a genuine DURATION and
#: gives a law. We cited the right field and a superseded version of the
#: finding.
#:
#: An earlier version of this note blamed an ATTAK1/ATTAK2 field mix-up. That
#: account came from s3ked, who corrected it within the hour after reading
#: their own section; the fields were never confused. Recorded because the
#: wrong story is tidier than the true one and would have survived.
#:
#: **The transferable rule is about TIME, not fields: a finding quoted across a
#: project boundary must carry WHEN it was true.** An append-only log is mostly
#: intermediate states written in the same voice as the conclusions -- §29 does
#: not announce that it is about to be superseded, because it was not. A
#: section number alone is not a citation; a superseding section can exist and
#: usually does.
#:
#: Constants are §141's refit (2026-08-20), superseding §31's (0.000150326,
#: 0.11175, fitted 55..90). The two agree to 2.5% at ATTAK1 80 and 3.5% at 99,
#: and §141 validated against ATTAK1 99 directly, which §31 never fitted.
_AK_ATTAK1_TIME = (0.000201173, 0.10844, 0, 99)   # seconds,  s3ked §141

# NOT WIRED, and each for its own reason rather than as a batch:
#
#   ATTAK2, DECAY2, RELSE2  the filter envelope's three time stages.
#       **NOT WIRED, AND BOTH REASONS THIS FILE GAVE FOR THAT ARE STALE.**
#       Audited 2026-08-20 against s3ked's `s3k/scales.py`, which is their
#       authority rather than their prose:
#
#           ATTAK2  0.001363 * exp(0.09703 v) s   40..85   r2 0.99981
#           DECAY2  0.002464 * exp(0.09844 v) s   40..80   r2 0.99997
#           RELSE2  0.001344 * exp(0.09692 v) s   40..80   r2 0.99998
#
#       all for a FULL 0..99 traverse, none provisional.
#
#       Stale reason 1, ATTAK2 "depth-scaling is open": those were §28's
#       numbers and §58 retracted them on 2026-08-12 -- the threefold spread
#       was the filter's own corner ceiling, not depth-dependence. §67 then
#       settled ATTAK2 as a RATE by varying the distance.
#
#       Stale reason 2, and this one is ours: "our model carries no
#       filter-envelope amount -- there is no span to divide by". It does.
#       `VoiceLayer.filter_env_cents` exists, EIGHT parsers populate it, and
#       it is non-zero on 20 of 39 voices in real E4B material.
#
#       So the honest current blocker is neither of those. It is that these
#       are RATES over a VARIABLE distance -- a stage takes
#       `full_time * (distance / 99)` -- so wiring them needs envelope 2's
#       level architecture (a four-stage rate/level envelope, s3ked §67) and
#       a decision about how our two-parameter model maps onto it. That is
#       real work, not a missing measurement, and it has never been costed.
#       See §AKAIENV2 in RESOLUTION_NOTES.
#
# Both were wired from the withdrawn model earlier today. Unwiring them is not
# a regression: writing a value derived from a retracted law is worse than
# writing a neutral default, because it looks like intent.

#: ── HOW TO TREAT AN IMPORTED "THIS FIELD DOES NOTHING" ───────────────────
#:
#: This file carries about twenty-five negative claims sourced from s3ked --
#: fields measured inert, values that store cleanly and do nothing. Treat every
#: one as PROVISIONAL, because the retraction rate on them is high and the
#: reason is structural rather than sloppy.
#:
#: Retracted so far: §45's four per-zone velocity fields (the detector returned
#: a velocity spread, which is zero at both extremes of a STATIC offset, so it
#: read inert whether the field worked or not); three of §47's six verdicts
#: (timing changes screened with a median centroid, which a timing change
#: cannot move); `PRSDEP` (channel pressure has to arrive DURING the note);
#: and on 2026-08-14 the load register, where "only value 1 acts" turned out
#: to be "writing value n performs load type n" -- the original null measured
#: against a machine whose memory was already fully resident, so every value
#: reloaded what was there and netted zero.
#:
#: The asymmetry to remember: a POSITIVE result carries its own evidence -- a
#: number moved, and you can ask how much. A NEGATIVE result is only ever as
#: good as the detector's ability to have seen the alternative, and that
#: ability is exactly what a null gives you no information about.
#:
#: The practical rule for this writer: never suppress a field, narrow a range,
#: or skip a write because something was reported inert. Declining to populate
#: a field we have no source for is fine; declining because it "does nothing"
#: is acting on the one class of claim this channel gets wrong most often.
#:
#: s3ked learned this the expensive way the same day: a probe was run on the
#: strength of a documented negative saying the write was inert, and it fired
#: a load on real hardware that nobody intended. A stale negative is not a
#: harmless one.
#:
#: **Never encode one of these in a test.** Their fourth retraction, hours
#: later, was "the volume cannot be selected remotely" -- repeated for six days
#: in a docstring, a CHANGELOG limitation, two screens, and a test literally
#: named `test_there_is_no_volume_register_to_offer` that asserted the feature
#: MUST NOT EXIST. The register had been found already and filed under the
#: wrong name. A test that locks in a negative does not merely record the
#: mistake, it defends it.
#:
#: The line to hold: a test may enforce a claim about OUR OWN code -- that we
#: do not upsample, that no flag goes unread -- because we decide those. It
#: must not enforce a discovery about someone else's system, because that is
#: not ours to fix in place when it turns out wrong.
#:
#: (Their find also confirms the machine's convention a second time: the
#: volume register is 0-based and the panel shows it 1-based, exactly as
#: PRGNUM does. Two independent fields agreeing makes it a machine-wide
#: convention rather than a quirk of one byte, which is worth knowing before
#: reading any future panel photograph as a stored value.)
#:
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

#: What we write at keygroup 160. 255 is OFF; akaiutil writes 0.
#: Module-level so `tests/test_akai_image.no_hw_defaults` can pin it
#: back to akaiutil's value, like every other deliberate divergence.
#: FILQ, resonance. Same offset the reader uses; named here rather than
#: imported because the constant lives in the parser module and importing
#: it the other way would be circular.
_AKAI_FILQ_OFFSET = 149
#: L_PTCH, the LFO->pitch gate. Same offset the reader uses.
_AKAI_LPTCH_OFFSET = 150
_KGMUTE_DEFAULT = AKAI_KGMUTE_OFF

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


#: VELOCITY -> FILTER, MEASURED 2026-08-17 (s3ked, sawtooth, two velocities).
#:
#:     cents_shift = 4.368 * MODVFILT1 * (velocity - 64.56)
#:
#: The PIVOT was SOLVED FOR rather than assumed -- two runs differing only in
#: velocity, then differenced -- and it lands on 64.56 against a 64 measured
#: independently on other fields.
#:
#: An earlier guess that a MODVFILT1 unit equals a FILFRQ unit was wrong by
#: 2.2x. It was flagged as a guess and it still produced confident numbers, so
#: nothing here is derived from it.
#: Keygroups whose requested velocity->filter span did not fit, reported
#: after a build rather than clipped in silence.
_velfilt_clipped = []
_AKAI_VELFILT_CENTS = 4.368        # cents per depth-unit per velocity-unit
_AKAI_VELFILT_PIVOT = 64.56        # the velocity the field pivots about
#: FILFRQ units of corner movement per depth-unit at full velocity swing,
#: = 4.368 cents * (127 - 64.56) / 1200 * 9.76 units-per-octave.
_AKAI_VELFILT_FILFRQ_PER_UNIT = 2.22


def akai_velocity_filter(cutoff_hz: float, vel_min_ct: float,
                         vel_max_ct: float, hi_key=None):
    """(resting corner in Hz, MinDpt and MaxDpt in CENTS)
       -> (FILFRQ, MODVFILT1, lost_ct).

    **THIS FUNCTION WAS BROKEN FOR ONE COMMIT (4733a90 -> here, 2026-08-25.)**
    That commit moved `filter_cutoff` to hertz and changed `akai_filter_byte`
    with it, but left this function's body raising the E-MU scale to the power
    of what is now a FREQUENCY -- so any voice that carried a velocity->filter
    sweep was written wide open. It survived the corpus sweep because the AKAI
    reader does not populate `velocity_to_filter_cents`, so an AKAI->AKAI trip
    takes the `not span_ct` early return and never reaches the broken line;
    only KRZ->AKAI and SFZ->AKAI could hit it. A round-trip corpus cannot see a
    field its own reader never sets, which is the general form of the lesson.
    

    THE SOURCE SPECIFIES A LINE, NOT A POINT. A K2000 velocity->filter routing
    runs from `vel_min` at velocity 0 to `vel_max` at velocity 127, and the
    machine's resting cutoff is the value at velocity ZERO. `MODVFILT1` is
    bipolar about velocity 64.56, so reproducing that line means matching its
    SLOPE with the depth and placing `FILFRQ` where the source is AT THE PIVOT
    -- not where the source starts.

    Writing the source's velocity-zero cutoff into `FILFRQ` and hanging a
    bipolar depth on it, which this writer did until 2026-08-17, drives the
    corner BELOW a floor the source never crosses. On a cymbal that is silence,
    and it was found by ear on hardware, not by any static check
    (RESOLUTION_NOTES AKAIVELFILT).

    Returns the two bytes plus how many cents of the requested span could not
    be represented, so the caller can say so rather than clip quietly.
    """
    # CENTS ON BOTH DEPTHS since 2026-08-25. They arrived normalised on the
    # K2000's 10800-cent field before that, which meant an SFZ and a KRZ
    # asking for the same sweep did not produce the same one.
    span_ct = vel_max_ct - vel_min_ct
    if not span_ct:
        return akai_filter_byte(cutoff_hz), 0, 0.0

    # Depth from the SLOPE: the source covers span_ct over 127 velocity units.
    depth = span_ct / (127.0 * _AKAI_VELFILT_CENTS)

    # FILFRQ from where the source sits AT THE PIVOT, not at velocity 0.
    pivot_ct = vel_min_ct + span_ct * _AKAI_VELFILT_PIVOT / 127.0
    f_byte = akai_filter_byte(cutoff_hz * 2.0 ** (pivot_ct / 1200.0))

    d_byte = _clamp(int(round(depth)), -50, 50)

    # THE CORNER MUST CLEAR THE HIGHEST PLAYED FUNDAMENTAL ACROSS THE WHOLE
    # SWEEP, NOT MERELY AT THE PIVOT (2026-09-05, hardware).
    #
    # `f_byte` above places the corner where the source sits at the velocity
    # pivot. The sweep then swings BELOW that at low velocity, and if it
    # crosses the fundamental of the notes the keygroup plays, those notes are
    # filtered into near-silence at the quiet end and not at the loud end --
    # a velocity response the source does not have, and a different one at
    # every key.
    #
    # Measured on an S3000XL, the ch2 lead program, keys 36 and 84 against the
    # MPC source (confidence = 1 - worst penalty, our matrix statistic):
    #
    #     FILFRQ 49 (as shipped)  0.000   key 84: 3 of 9 velocities audible
    #     FILFRQ 79               0.350   the corner at the pivot only
    #     FILFRQ 99               0.922   whole sweep above the fundamentals
    #
    # The floor is raised to the corner the sweep's LOW end needs, so a
    # program keeps its filter character wherever that is already satisfied.
    # RAISE ONLY: computing this as a target rather than a floor would have
    # LOWERED two programs that currently convert well (99 -> 90 and 99 -> 68,
    # scoring 0.830 and 0.940), trading a fixed fault for a new one.
    if hi_key is not None and d_byte > 0:
        top_hz = 440.0 * 2.0 ** ((min(hi_key, 108) - 69) / 12.0)
        down_ct = d_byte * _AKAI_VELFILT_CENTS * _AKAI_VELFILT_PIVOT
        f_byte = max(f_byte, akai_filter_byte(top_hz * 2.0 ** (down_ct / 1200.0)))

    # TWO SEPARATE LIMITS, AND ONLY ONE OF THEM IS THE FIELD'S RANGE.
    #
    # The rate is base-independent -- re-measured at FILFRQ 60 and 75 and
    # agreeing to 0.60%, so 4.368 applies wherever the corner sits. The
    # REACHABLE RANGE is not: the corner ceilings at the ends of FILFRQ, so the
    # headroom depends entirely on the base chosen. Measured: 39 units of swing
    # available at base 60 (3.99 octaves), 24 at base 75 (2.46).
    #
    # Those two facts look contradictory and never were -- a fixed rate with a
    # moving ceiling -- and the same holds for VLOUD1, whose rate is fixed
    # while its headroom moves with PRLOUD. Reporting only the +-50 clamp would
    # have counted the smaller limit and missed the one that usually binds: a
    # depth of 19 is nowhere near +-50 and still drives the corner off the top
    # of FILFRQ well before full velocity.
    # The two halves ceiling INDEPENDENTLY, and conflating them over-reports.
    # From the pivot the corner rises toward full velocity and falls toward
    # zero; a base near the top clips only the rising half and leaves the
    # falling half intact -- which is the half that matters, since it is where
    # the silent-zone fault lived.
    _U = _AKAI_VELFILT_FILFRQ_PER_UNIT
    want_up = abs(d_byte) * _U * (127.0 - _AKAI_VELFILT_PIVOT) / 62.44
    want_dn = abs(d_byte) * _U * _AKAI_VELFILT_PIVOT / 62.44
    lost_units = (max(0.0, want_up - (99 - f_byte))
                  + max(0.0, want_dn - f_byte))
    lost_range = lost_units / 9.76 * 1200.0          # FILFRQ units -> cents
    lost_clamp = abs(depth - d_byte) * 127.0 * _AKAI_VELFILT_CENTS
    return f_byte, d_byte, lost_clamp + lost_range


def _filfrq_hz_table():
    """FILFRQ -> the corner in Hz it reads as, for every settable value.

    Built from `akai_filfrq_to_hz`, the SAME function the reader uses, so the
    writer is the inverse of the reader BY SEARCH rather than by a second
    formula. That is the lesson of 2026-08-20: two hand-derived inverses of one
    curve drifted apart and nine of ten FILFRQ values failed a round trip while
    a docstring claimed they were inverses by construction. A search cannot
    drift.

    **THE DOMAIN IS THE WHOLE FIELD, and getting here took three attempts.**

    It began at the FITTED FLOOR (40), justified by "below it the reader
    clamps". That clamp was removed on 2026-08-24 once the corner was measured
    all the way down -- monotonic across 41 dB, no plateau -- and the read side
    was fixed while this was left, so FILFRQ 10 and 20 both wrote back as 40:
    a dark keygroup brightened by up to four octaves.

    Opening it to 0 was WORSE. `filter_cutoff` was then an E-MU POSITION whose
    scale bottoms at 57 Hz, so every AKAI corner below that arrived here
    identical and the search returned the darkest byte in the domain -- one
    plateau traded for another, at the wrong end. A floor at the darkest byte
    the model could distinguish was the honest patch, and it still flattened
    **29.4% of the corpus** onto FILFRQ 28.

    **The model carries Hz since 2026-08-25, so the search runs in Hz and the
    floor is gone.** Matching in LOG Hz, because a semitone is a ratio: 40 Hz
    against 45 is the same musical error as 4000 against 4500, and matching
    linearly would spend all its precision at the top.
    """
    out = {}
    for v in range(0, AKAI_FILTER_OPEN + 1):
        hz = akai_filfrq_to_hz(v)
        out[v] = None if hz is None else hz
    return out


_FILFRQ_HZ = None


def _nearest_filfrq(hz: float) -> int:
    """Cutoff in Hz -> the FILFRQ whose own corner is closest, in LOG Hz.

    Fully open is written as 99, the machine's own resting value, rather than
    the lowest saturated setting -- 96..99 are indistinguishable to the machine
    (98 differs from 99 by 2.2 dB across the whole band), so any is correct and
    99 is where a user's machine sits.

    Below that, **ties go to the LOWER setting**, which keeps a measured point
    in preference to an unmeasured one: FILFRQ 95 has no measurement and takes
    94's corner, so the two share a frequency and 94 is the one measured.
    """
    global _FILFRQ_HZ
    if _FILFRQ_HZ is None:
        _FILFRQ_HZ = _filfrq_hz_table()
    # STRICTLY GREATER. `AKAI_FILTER_OPEN_HZ` IS FILFRQ 95's own measured
    # corner, so `>=` swallowed 95 and returned 99 -- 2.1% of round-tripped
    # zones, all at this one boundary. The reader now returns wide open (the
    # scale's top) for the genuinely saturated 96..99, which is comfortably
    # above this, so both cases still land where they should.
    if hz > AKAI_FILTER_OPEN_HZ:
        return AKAI_FILTER_OPEN
    target = math.log(max(1e-6, hz))
    best, best_d = 0, 9e9
    for v in sorted(_FILFRQ_HZ):
        f = _FILFRQ_HZ[v]
        if f is None:               # saturated: indistinguishable from open
            continue
        d = abs(math.log(f) - target)
        if d < best_d - 1e-12:
            best, best_d = v, d
    return best


def akai_filter_byte(cutoff_hz: float) -> int:
    """Cutoff in Hz -> FILFRQ.

    `filter_cutoff` is this project's internal 0-1 position, defined by the
    documented 57 Hz..20 kHz law (see models.common). Convert it to the
    frequency it is meant to MEAN, then ask the measured S3000XL curve for the
    byte that lands there -- the same two-step the E4B writer does, and for the
    same reason: the position is shared across formats and the machines do not
    agree about what it sounds like.

    The measured curve covers FILFRQ 40..84, i.e. 138 Hz .. 3.3 kHz. Outside
    it the two ends are handled differently, because they are not symmetrical:

      above the fit -> the position is INTERPOLATED across 84..99 rather than
                       clamped, mirroring the reader exactly so the two are
                       inverses across the unmeasured decade as well. That band
                       carries 44% of S3000 factory voices, and clamping it
                       made 9 of 10 FILFRQ values fail an AKAI round trip,
                       drifting +3 to +11 and brightening on every pass.
                       Position 1.0 is **99**, the machine's own resting value
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
    return _nearest_filfrq(max(0.0, cutoff_hz))


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
    # PREFER A CARRIED RATE, for the same reason the release does and one more:
    # at full sustain the decay span is ZERO, so `_rate_law_value` divides
    # nothing by the time and falls through to its default. That default fired
    # on essentially every zone of the sound libraries, quietly replacing the
    # source's own decay byte with 50.
    _drate = getattr(env, 'decay_rate_db_per_s', None)
    if _drate:
        _a, _b, _lo, _hi = _AK_DECAY1_RATE
        d = int(round(max(0, min(99, math.log(_drate / _a) / _b))))
    else:
        span_decay_db = _AK_SUSTAIN_DB_PER_UNIT * (99 - sus)
        d = _rate_law_value(getattr(env, 'decay', 0.3) or 0.3,
                            span_decay_db, _AK_DECAY1_RATE, default=50)

    # Release travels from the sustain level down to the floor.
    #
    # PREFER A CARRIED RATE over the seconds when the source supplied one
    # (§AKAIRELSPAN). A release ends at "silence" and the two machines disagree
    # about where that is by 60.07 dB against 97.82 -- two numbers neither of
    # them was ever metered for. When the reader knew its own rate law, that
    # rate is the quantity both machines actually measure and it goes across
    # untouched; the seconds are the derived figure and only stand in when
    # there is nothing better.
    _rate = getattr(env, 'release_rate_db_per_s', None)
    if _rate:
        _a, _b, _lo, _hi = _AK_RELSE1_RATE
        r = int(round(max(0, min(127, math.log(_rate / _a) / _b))))
    else:
        span_rel_db = _AK_SUSTAIN_DB_PER_UNIT * sus
        r = _rate_law_value(getattr(env, 'release', 0.5) or 0.5,
                            span_rel_db, _AK_RELSE1_RATE, default=45)

    # Attack rises from silence to the peak, so unlike decay and release its
    # span is fixed and it needs no sustain-dependent distance.
    a = akai_attack_byte(getattr(env, 'attack', 0.0) or 0.0)

    return a, d, sus, r


def akai_env_from_bytes(atk: int, dec: int, sus: int, rel: int):
    """(ATTAK1, DECAY1, SUSTN1, RELSE1) -> Envelope. Inverse of `akai_env_bytes`.

    **The reader had no inverse at all until 2026-08-23** — it never assigned
    `amp_env`, so every AKAI-sourced voice carried the model default and the
    two distinct envelopes of a layered program came out identical. eosed read
    all six voices of one off the E4XT and found them byte-identical where the
    source says they must differ (§AKAIAMPENV).

    It lives here rather than in the parser so the law has ONE home: three of
    tonight's seven defects were a writer law that had been measured and wired
    while the corresponding read path was left as it was, and a second copy of
    the arithmetic is how that happens. The parser imports it inside the
    function, because this module imports the parser at module scope and the
    other direction would be circular.

    Sustain is recovered first, for the same reason `akai_env_bytes` computes
    it first: decay and release are RATES, so the seconds they represent
    depend on the distance travelled, and sustain sets that distance.
    """
    from models.common import Envelope
    sus_frac = _akai_sustain_fraction(sus)
    _a, _b, _lo, _hi = _AK_RELSE1_RATE
    return Envelope(
        attack=_ak_attack_seconds(atk),
        decay=_ak_rate_seconds(dec, _AK_SUSTAIN_DB_PER_UNIT * (99 - sus),
                               _AK_DECAY1_RATE),
        sustain=sus_frac,
        release=_ak_rate_seconds(rel, _AK_SUSTAIN_DB_PER_UNIT * sus,
                                 _AK_RELSE1_RATE),
        # The DECAY's rate too, for a narrower reason: at SUSTN1 99 the decay
        # has nowhere to travel, so its seconds are 0 and the byte is
        # unrecoverable from them. See `Envelope.decay_rate_db_per_s`.
        decay_rate_db_per_s=_AK_DECAY1_RATE[0] * math.exp(
            _AK_DECAY1_RATE[1] * max(0, dec)),
        # THE RATE ITSELF, alongside the seconds (§AKAIRELSPAN).
        #
        # `release` above is the same number it always was and every existing
        # consumer keeps working. This is the quantity that actually survives
        # the trip to another rate machine: the seconds are computed over a
        # 60.07 dB scale here and read back over a 97.82 dB one by the E4B
        # writer, and since both figures are parameter-scale artifacts rather
        # than measured floors, matching seconds across them made every
        # AKAI-sourced release 1.6-4x too fast.
        #
        # The DECAY deliberately gets no such field: it ends at the sustain
        # level, which both machines agree on, so its seconds are sound.
        release_rate_db_per_s=_a * math.exp(_b * max(0, rel)))


def _ak_attack_seconds(byte: int) -> float:
    """ATTAK1 -> seconds. Exact inverse of `akai_attack_byte`'s law."""
    a, b, lo, hi = _AK_ATTAK1_TIME
    return a * math.exp(b * max(lo, min(hi, byte)))


def _ak_rate_seconds(byte: int, span_db: float, law) -> float:
    """A rate byte and the distance it must cover -> seconds.

    `rate = a * exp(b * value)` and `time = span / rate`, which is the same
    relation `_rate_law_value` inverts in the other direction.

    **EXTRAPOLATES OUTSIDE THE FIT RATHER THAN CLAMPING, and the corpus is why
    (§LAWRANGE, 2026-08-24).** Both laws here are fitted over a narrow window —
    DECAY1 over 45..85, RELSE1 over 55..70 — and real material sits outside it
    most of the time. Across 168765 keygroups on the library discs:

        DECAY1   49.8% outside the fit   (25.9% below, 23.9% above)
        RELSE1   79.8% outside the fit   (71.0% below,  8.7% above)

    RELSE1's single commonest value is 45, below the fitted floor, on 39% of
    all keygroups by itself. Clamping turns every one of those into the same
    number: it produces a PLATEAU, so a program with a longer release converts
    to the same release as a shorter one, and ordering — which is the thing a
    converter must not lose — is destroyed for four fifths of the corpus.

    Extrapolation is not free and this is not a claim that the fit holds out
    there. It is monotonic, which a clamp is not, and monotonic-and-approximate
    beats a plateau when half the data is outside the window. The honest fix is
    a wider calibration; until then this is the lesser error and it is recorded
    as such rather than presented as measured.
    """
    a, b, _lo, _hi = law
    rate = a * math.exp(b * max(0, byte))
    return max(0.0, span_db) / rate if rate > 0 else 0.0


def _akai_sustain_fraction(byte: int) -> float:
    """SUSTN1 -> linear amplitude fraction. Inverse of `akai_sustain_byte`.

    Bisected rather than solved: `akai_sustain_byte` rounds, so several
    fractions map to one byte and the honest inverse is the midpoint of the
    band that produced it.

    **IT USED TO RETURN THE BAND'S LOWER EDGE, NOT ITS MIDPOINT**, which is
    what the docstring already said it should do -- one bisection for the first
    fraction reaching `byte`, and that value handed straight back. Sitting on a
    boundary, it re-rounded DOWN: SUSTN1 6 came back as 5, 10 as 9, 75 as 74,
    99 as 98. Off by one at 5 of 8 probed values, and silent, because a sustain
    one byte low is 0.6 dB and nothing downstream compares it.

    Found by an AKAI -> AKAI round trip on 2026-08-24 while fixing the keygroup
    merge -- the same test that has now caught three defects on this path
    (§AKAITUNEREAD's octave, the writer's fine-tune-only read, and this).
    **Converting to a format and back is the cheapest test we have for a pair
    of laws that were written apart.**

    Now bisects BOTH edges and returns the midpoint, so the value is as far
    from either boundary as it can be and the round trip is exact for every
    byte 0..99.
    """
    def _first_reaching(target):
        if target > 99:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2.0
            if akai_sustain_byte(mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0
    if byte <= 0:
        return 0.0
    return (_first_reaching(byte) + _first_reaching(byte + 1)) / 2.0


def akai_attack_byte(seconds: float) -> int:
    """Amplitude attack time in seconds -> ATTAK1.

    Inverts `t = a * exp(b * ATTAK1)`. **Higher ATTAK1 is a SLOWER attack**,
    which is the opposite sense to the decay and release fields beside it --
    those store a rate, this stores a time. Confirmed against the measured
    points before wiring (0.320 s at 70 rising to 8.600 s at 99), because a
    sign error here would be silent: the previous behaviour was a fixed 0, so
    an inverted law would still give fast attacks on most material and would
    only look wrong on the slowest sources.

    ATTAK1 0 is 0.2 ms, i.e. instant, so clamping a very fast source to the
    floor loses nothing audible.
    """
    a, b, lo, hi = _AK_ATTAK1_TIME
    if seconds <= a:
        return lo
    v = math.log(seconds / a) / b
    return int(round(max(lo, min(float(hi), v))))


def _rate_law_value(seconds: float, span: float, law, default: int) -> int:
    """Invert `rate = a*exp(b*v)` for a stage covering `span` in `seconds`.

    Returns `default` when the span is zero -- a stage with nowhere to travel
    has no meaningful rate, and dividing by it would produce a confident
    number from nothing.

    **EXTRAPOLATES OUTSIDE THE FIT RATHER THAN CLAMPING, and it did not until
    2026-08-24.** `_ak_rate_seconds` -- this function's own inverse, thirty
    lines up -- has extrapolated since §LAWRANGE, with a long note saying
    exactly why: clamping turns every value outside the window into the same
    number, so it produces a PLATEAU, and ordering is the one thing a converter
    must not lose. **The read path was fixed and the write path was left
    clamping**, which is the same one-sided repair that accounted for most of
    this week's defects.

    The corpus says it matters here in both directions: 25.9% of DECAY1 values
    sit below the fitted 45 and 23.9% above 85, so half of all real keygroups
    were being mapped onto one of two numbers.

    It also had a concrete victim. The mute-group re-model asks for a ~10 ms
    cut on the layer that loses; clamped at DECAY1 45 that became **210 ms, 21x
    too long**, and the field the model actually depends on was the one nobody
    printed. s3ked caught the class of it from the other side.

    Clamped only to the FIELD's legal range 0..99, which is a hardware limit
    rather than a fitting artifact. Extrapolation is not free and this is not a
    claim the fit holds out there -- it is monotonic, which a clamp is not, and
    monotonic-and-approximate beats a plateau.
    """
    a, b, lo, hi = law
    if span <= 0 or seconds <= 0:
        return default
    rate = span / seconds
    if rate <= 0:
        return default
    v = math.log(rate / a) / b
    return int(round(max(0.0, min(99.0, v))))


#: ENVELOPE 2, the FILTER envelope. Times for a FULL 0..99 traverse, from
#: s3ked's `s3k/scales.py` -- their authority, taken from the module rather
#: than from prose:
#:
#:     ATTAK2  0.001363 * exp(0.09703 v) s   fitted 40..85  r2 0.99981
#:     DECAY2  0.002464 * exp(0.09844 v) s   fitted 40..80  r2 0.99997
#:     RELSE2  0.001344 * exp(0.09692 v) s   fitted 40..80  r2 0.99998
#:     SUSTN2  a LEVEL, linear, v/99 of full excursion
#:
#: These are RATES over a VARIABLE distance -- a stage takes
#: `full_time * (distance / 99)` -- which is why this was harder than the amp
#: attack and why it sat unwired. ATTAK1 is a duration because it always
#: travels zero-to-peak; envelope 2 does not.
#:
#: **Wired 2026-08-21, on a measurement rather than a guess.** Jan A/B-ed ten
#: converted programs against their E4XT originals and the three whose source
#: carries a filter envelope came back **~20 dB darker in HF, flat across
#: three pitches** -- the signature of a missing modulation rather than a
#: mis-set corner. He picked those three out of ten by ear alone.
#: Aliases onto the SHARED laws in models.common -- see there for why.
_AK_ATTAK2_FULL = AKAI_ENV2_ATTACK
_AK_DECAY2_FULL = AKAI_ENV2_DECAY
_AK_RELSE2_FULL = AKAI_ENV2_RELEASE

#: Envelope2 -> Filter Frequency depth, keygroup 153, +-50 (§AKAIVFR).
#: §144 measured AKAI's own import defaulting 151/152/153 to 0, so an envelope
#: written without this routes nowhere and is silent in exactly the way the
#: unwired envelope was.
_AK_ENV2_DEPTH_OFF = AKAI_ENV2_DEPTH_OFFSET
_AK_ENV2_DEPTH_MAX = AKAI_ENV2_DEPTH_MAX


def _env2_stage_byte(seconds: float, distance: float, law) -> int:
    """Invert a full-traverse time law for a stage covering `distance`/99.

    The published law is the time for the whole 0..99 sweep, so a stage that
    travels less takes proportionally less: scale the wanted time UP by
    99/distance before inverting, and the byte that results is the one whose
    full traverse would take that long.

    **BOTTOM EXTRAPOLATES, TOP STILL CLAMPS, and the asymmetry is deliberate
    both ways** (2026-08-24, the same audit that caught `_rate_law_value`).

    This used to clamp BOTH ends to the fitted 40..80/85 while its own inverse
    `akai_env2_stage_seconds` already extrapolated downward -- so the two sides
    of one law disagreed about a quarter of the corpus. A source asking for a
    filter stage faster than byte 40 got byte 40, i.e. ~60 ms, however fast it
    asked; and the corpus puts **~25% of real ATTAK2 values in bytes 21..39**,
    all of which were landing on one number. A plateau is worse than an
    extrapolation because it is not merely inaccurate: it makes two different
    source programs identical, and ordering is the one thing a converter must
    not lose.

    A ZERO REQUEST STILL RETURNS 0, not an extrapolated small byte. "Instant"
    is a value the source states rather than a point on the curve, and the read
    side special-cases it the same way. Measured on an S3000XL: byte 0 is
    instant to within the rig's 10 ms floor, against the law's own prediction
    of 1.4 ms -- so this is a known endpoint, not a guess. s3ked's `endpoints`
    idea generalised: where a value outside the fit has an independently known
    meaning, use the fact rather than extrapolating or refusing.

    The TOP stays clamped at the fitted maximum, matching the read side.
    Extrapolating upward invents slow stages nobody has measured, and unlike
    the bottom there is no endpoint fact to anchor it. **Recorded as a known
    plateau rather than a fixed one:** the corpus puts 10.5% of DECAY2 and 4.6%
    of RELSE2 above the fit, so ordering IS being lost there and the honest fix
    is a wider calibration.
    """
    a, b, lo, hi = law
    if seconds <= 0 or distance <= 0:
        return 0
    full = seconds * (99.0 / distance)
    v = math.log(max(full, 1e-9) / a) / b
    return int(round(max(0.0, min(float(hi), v))))


def akai_filter_env_bytes(env, cents: float, filfrq: int = 99):
    """Filter envelope -> (ATTAK2, DECAY2, SUSTN2, RELSE2, depth byte).

    Distances mirror `akai_env_bytes`: attack climbs the full range, decay
    falls from the top to the sustain level, release falls from sustain to
    zero. Returns the depth separately because an envelope with no routing is
    inaudible, which is indistinguishable from the fixed defaults this
    replaced.

    **THE DEPTH CONVERTS A CORNER POSITION, and needs `filfrq` to do it**
    (§AKAIENV2DEPTH, 2026-08-24). It used to be `amount * AKAI_ENV2_DEPTH_MAX`,
    a constant derived by equating two laws measured on two different machines.
    Since 2026-08-25 the model states the depth in CENTS, so the composition is
    just this machine's own measured law:

        cents      -> where the corner ends up, from this FILFRQ
        ceiling    -> clamped at AKAI_ENV2_CEILING_HZ (absolute in Hz)
        depth      -> the ENV2 depth that lands there

    `filfrq` defaults to 99 (wide open) so existing callers keep working, and
    a wide-open base returns depth 0 -- correctly, since there is nowhere for
    the corner to sweep from there.
    """
    sus = int(round(max(0.0, min(1.0, getattr(env, 'sustain', 0.5))) * 99))
    a = _env2_stage_byte(getattr(env, 'attack', 0.0) or 0.0, 99, _AK_ATTAK2_FULL)
    d = _env2_stage_byte(getattr(env, 'decay', 0.0) or 0.0,
                         max(1, 99 - sus), _AK_DECAY2_FULL)
    r = _env2_stage_byte(getattr(env, 'release', 0.0) or 0.0,
                         max(1, sus), _AK_RELSE2_FULL)
    return a, d, sus, r, _akai_env2_depth(cents, sus, filfrq)


def _akai_env2_depth(cents: float, sustn2: int, filfrq: int) -> int:
    """Filter-env depth in CENTS -> AKAI ENV2 depth. Inverse of the reader's
    `_env2_amount`, and it must stay one: the two were briefly not inverses on
    2026-08-24 and the round-trip test caught it inside a minute, which is the
    entire argument for having that test.

    **No E-MU constant is involved any more (2026-08-25).** This used to turn
    the model's amount into an E4XT cord's byte movement, read that back as
    Hz, and only then ask what the AKAI needed -- so an AKAI conversion
    depended on the E4XT's byte curve for no reason. The model carries cents,
    the AKAI's own law is measured, and the two meet directly. That is this
    writer's half of §FENVFULLSCALE gone.

    The AKAI's CEILING still binds and is still absolute in Hz, so it is
    applied to the target corner rather than to the depth: the reachable span
    is 5.87 octaves from FILFRQ 40 and 1.08 from 85.
    """
    from models.common import (akai_filfrq_to_hz, AKAI_ENV2_OCT_PER_UNIT,
                               AKAI_ENV2_CEILING_HZ, AKAI_ENV2_FULL_LEVEL)
    # DO NOT REMOVE THE `sustn2 <= 0` TEST. It was removed on 2026-09-06 and
    # put back the same hour, because the MACHINE gates the same way and its
    # gate is the one that matters (§AKAIENV2SUSTAIN).
    #
    # §156: `octaves = 0.002612 * SUSTN2 * depth` -- a PRODUCT, so a zero
    # sustain gives zero sweep at any depth. §177: "SUSTN2 0 mutes its filter
    # route entirely." Measured by s3ked as an A/B/A writing this exact byte to
    # this exact value on the programs the change targeted:
    #
    #     PRG 0   k36->k72   A -22.87   B -22.90   A2 -22.91
    #     PRG 9   k36->k72   A -13.65   B -13.73   A2 -13.59
    #
    # 0.03 and 0.08 dB on a rig that reproduces to 0.02. Writing a depth here
    # when the sustain is 0 is pure churn: it changes bytes and no sound.
    #
    # The REAL loss is still real -- a K2000 program with a 10800-cent filter
    # envelope, sustain 0 and a 9-35 second decay cannot be represented on this
    # machine, because the AKAI's ENV2 filter route does not exist at sustain 0.
    # That is a fidelity LIMITATION to report, not a byte to write, and it wants
    # a diagnostic rather than a patch. See the section for the two-byte
    # alternative (depth + SUSTN2), which changes the envelope's SHAPE and is a
    # fidelity decision rather than a bug fix.
    if not cents or sustn2 <= 0:
        return 0
    base_hz = akai_filfrq_to_hz(filfrq)
    if base_hz is None:
        # Saturated FILFRQ. Same rule as the reader: use the highest corner the
        # machine distinguishes, so a downward sweep stays convertible.
        from models.common import AKAI_FILTER_OPEN_HZ
        base_hz = AKAI_FILTER_OPEN_HZ
    if cents > 0:
        tgt_hz = min(base_hz * 2.0 ** (cents / 1200.0), AKAI_ENV2_CEILING_HZ)
        octaves = math.log2(max(tgt_hz, 1e-6) / base_hz)
    else:
        octaves = cents / 1200.0        # the ceiling is an upper bound only
    # DIVIDE BY THE FULL LEVEL, NOT BY SUSTN2 -- the exact inverse of the
    # reader's fix of 2026-08-25 (§AKAIENV2PEAK). `cents` is the depth at full
    # envelope level; the SUSTN2 byte written alongside reproduces the settled
    # corner, and dividing by it here as well would apply the sustain twice.
    # That double application is what silenced the attack transient: on a
    # percussive envelope (SUSTN2 15) it made the written sweep fifteen times
    # too small, and reader and writer agreed with each other throughout.
    depth = octaves / (AKAI_ENV2_OCT_PER_UNIT * AKAI_ENV2_FULL_LEVEL)
    return int(round(math.copysign(min(abs(depth), 50.0), cents)))


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
#:
#: **MEASURED 2026-08-16 on Jan's S3000XL, automatically.** A ladder of six
#: keygroups on one sine, key == root so the tune was the only variable:
#:
#:     tune 5120 .. 7680  (+20 .. +30 semitones)
#:     every step sounded, every step within 1 cent of prediction,
#:     identical on 44.1 kHz and 22.05 kHz samples
#:
#: So +-50 semitones stands and the field is not the constraint. A rival
#: reading of "+-50" as UNITS (which would make this 256x too wide) is
#: refuted: s3ked wrote raw 256 through 5120 and read the pitch back, all on
#: target, and this ladder extends that to 7680.
#:
#: What silences a zone is therefore NOT the tune value -- and after four more
#: calibration volumes, it is not any keygroup setting at all:
#:
#:     downward offset alone, to -40 semitones          sounds, within 1 cent
#:     -28/-30/-36 offset WITH +30 tune                 sounds
#:     -47 offset with +45 tune, the exact silent shape sounds
#:     the same, with a full-length hold loop           sounds
#:
#: The silent keygroups were not a fault. Their samples are SUB-BASS: peak
#: energy at 18 and 24 Hz with 99 % and 98 % of it below 50 Hz, played at a net
#: -2 semitones. The two keygroups that DO sound in the same program carry
#: 3 % and 11 % of their energy in 50-200 Hz, and that harmonic content is what
#: is audible -- their fundamentals are equally inaudible at 16 and 20 Hz.
#:
#: Recorded because it cost five bench iterations to reach, and the evidence
#: that settled it was in the files the whole time. A spectrum of the four
#: samples, taken before the third calibration rather than after the fifth,
#: would have ended it: 'is there any energy above 50 Hz' is a cheaper question
#: than 'which keygroup parameter breaks this', and it was the right one.
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


def build_sample(sd: SampleData, name: Optional[str] = None,
                 root_override: Optional[int] = None,
                 channel: Optional[int] = None) -> bytes:
    """One SampleData -> a complete `.a3s` file.

    **One file carries one channel.** The format has no stereo sample: real
    library discs build a stereo voice from TWO samples named `<base>-L` and
    `<base>-R`, referenced by two hard-panned zones of the same keygroup
    (§AKAISTEREO2). The header's `0x88` "stereo partner" word is an internal
    RAM pointer, not on-disk state, and stays `_NO_POINTER` either way.

    `channel` selects which half of an interleaved source to write: 0 for the
    left file, 1 for the right. Left at None a multi-channel source is mixed
    down, which is what happens when stereo output is off.
    """
    h = bytearray(SAMPLE_HEADER_LEN)
    pcm = sd.data
    if getattr(sd, 'channels', 1) > 1:
        pcm = (_extract_channel(pcm, sd.channels, channel)
               if channel is not None else _mixdown(pcm, sd.channels))
    if len(pcm) % 2:
        pcm = pcm[:-1]
    n_frames = len(pcm) // 2

    h[0x00] = _BLOCK_ID_SAMPLE      # block id: 3 = sample header
    # PLAYBACK RATE SELECT -- see AKAI_PLAYBACK_RATES. Derived from the rate the
    # audio ACTUALLY is, never from a threshold: the machine plays at whatever
    # this byte says, so classifying a 48 kHz sample as "full bandwidth" simply
    # makes it play 147 cents flat with a header that looks right.
    played = akai_playback_rate(sd.sample_rate)
    h[0x01] = _AKAI_RATE_FLAG[played]
    if sd.sample_rate not in AKAI_PLAYBACK_RATES:
        # WARN RATHER THAN RESAMPLE. Resampling is a processor's job and doing
        # it here would hide the problem from every other output path; warn
        # rather than raise so a bench script or a caller that knows what it is
        # doing is not blocked. `convert.py` resamples before reaching here, so
        # in ordinary use this never fires.
        cents = 1200.0 * math.log2(played / float(sd.sample_rate))
        print(f"    [WARN] {sd.name!r}: stored at {sd.sample_rate} Hz, which the "
              f"S3000XL cannot play. It will sound at {played} Hz -- "
              f"{cents:+.0f} cents. Resample to one of "
              f"{AKAI_PLAYBACK_RATES} first (convert.py does this).")
    # ROOT: the ZONE's, when the zones agree, not the sample's own.
    #
    # **HARDWARE-CONFIRMED 2026-08-16 on Jan's S3000XL.** A calibration volume
    # of three pure sines, roots set to the matching MIDI notes, played at
    # their own roots and measured with a tuner:
    #
    #     CALA3  root 57  ->  220 Hz   exact
    #     CALA4  root 69  ->  440 Hz   exact
    #     CALA2  root 45  ->  110 Hz   exact
    #
    # And TRANSPOSITION, measured on the same 220 Hz sample an octave either
    # side of its root -- which the three readings above could not separate
    # from a correct root with a broken pitch ratio:
    #
    #     CALA3 (root 57) at key 69  = +12 st  ->  440 Hz   exact
    #     CALA3 (root 57) at key 45  = -12 st  ->  110 Hz   exact
    #
    # So the root byte, the key numbering, the pitch ratio and this zone-root
    # rule are all correct end to end. It took a purpose-built bank to establish: the real
    # bank we started from has sample names, zone roots and actual audio
    # pitches that disagree with each other by up to 45 semitones, and no
    # amount of listening to it could separate its faults from ours.
    #
    # Our E4B reader derives a sample's root from its NAME suffix ('_B3' -> 71),
    # because that inverts our own writer's naming -- it is not a field. The
    # machine that matters reads the ZONE's root instead, so a bank whose zone
    # roots differ from its name suffixes plays at a different pitch on an
    # S3000XL than on an E4XT. Jan heard exactly that.
    #
    # Correcting it through the per-zone tune was the first attempt and it is
    # not safe: a 20-semitone correction is 5120 units, and the ONLY
    # measurement of that field swept units 0..50 and produced 19.39 CENTS. Our
    # +-50 range is semitones inferred from a document, and if the machine
    # clamps near 50 units the correction silently vanishes -- the same
    # too-narrow-clamp failure this field has already produced twice, in the
    # other direction. Writing the root itself needs no such assumption.
    h[0x02] = _clamp(_or_default(root_override,
                                 _or_default(getattr(sd, 'root_note', None), 60)),
                     24, 127)
    h[0x03:0x03 + AKAI_NAME_LEN] = str_to_akai(name or sd.name)
    h[0x0f] = 0x80                      # sample rate field is valid
    # ACTIVE-LOOP COUNT: 0 for a one-shot, 1 for a looped sample. This wrote 1
    # unconditionally until 2026-08-18, which is wrong for every one-shot we
    # emit. Settled from two independent sources rather than from the manual:
    #
    #   the machine's own saves (XCROSS 1/2)   one-shot 0, loop 1
    #   factory material, 6 discs              one-shot 0 x1038 / 1 x56
    #                                          loop     1 x4094 / 0 x143
    #
    # Nothing is known to read it -- a one-shot carries SPTYPE 2 and no loop
    # record, so the count is redundant with what is already there. Corrected
    # for fidelity to the format, not to fix an observed fault.
    looped_now = (sd.loop_type != LoopType.NO_LOOP
                  and sd.loop_end > sd.loop_start >= 0
                  and sd.loop_end < n_frames)
    h[0x10] = (1 if looped_now else 0) if _ACTIVE_LOOP_COUNT_FROM_STATE else 1
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
        # LLNGTH1 IS EXCLUSIVE OF THE LAST FRAME, and the `+ 1` here made every
        # looped sample this writer produced overrun by one.
        #
        # MEASURED on an S3000XL 2026-08-17 (s3ked): with SMPEND 88199 and
        # LLNGTH1 88200, a held note plays ~2 s, goes silent for a stretch, and
        # repeats, with a ~500 ms silent lead-in before the first sound. At
        # 44100 and 22050 the same sample loops CONTINUOUSLY -- no lead-in, 2%
        # silence against 15%. Un-looped playback (SPTYPE 2 or 3) gives one
        # clean 2 s pass, which is what proves the sample data itself is sound
        # and looping is what introduced the silence.
        #
        # Diagnosed first as the wrong SPTYPE -- 0 "loop in release" against 1
        # "loop until release" -- which was a good hypothesis from the value
        # table and was REFUTED on the machine: 0 and 1 behave identically here
        # and neither removes the lead-in. The mode was never the fault.
        #
        # 88199 itself is NOT tested. The measured points are 88200 (fails),
        # 44100 and 22050 (work), so "one less than the length" is the minimal
        # fix consistent with the mechanism rather than a confirmed value.
        # 0x26 IS THE LOOP **END**, NOT THE START. This wrote `loop_start`
        # there until 2026-08-18, which is the field's opposite meaning.
        #
        # The AKAI loop record is a marker plus a length running BACKWARDS from
        # it -- "loop AT x, length y" means the loop is [x - y, x]. Four
        # independent sources, after a day of measuring the symptom:
        #
        #  * the S3000XL manual: "when playback reaches this point, it will go
        #    back to the point determined by the field described below"
        #  * the corpus: across 16493 factory S3000 loops, LOOPAT sits within
        #    1% of SLNGTH in 82.9% and within 10% in 92.5% -- i.e. at the END of
        #    the sample, which is where a sustain loop's end belongs. Under the
        #    start reading, 89% of factory loops would run off their own end.
        #  * ConvertWithMoss, an independent implementation, names the field
        #    `getEndMarker()` with the docstring "the end of the looped region
        #    (not the start!)" -- the exclamation mark is theirs
        #  * and its converter: `setStart(marker - coarseLength); setEnd(marker)`
        #
        # WHY THIS SURVIVED SO LONG. With `loop_start` written into the marker,
        # the resulting loop is [loop_start - length, loop_start] -- which for
        # our usual `loop_start == 0` is a region ending at frame 0. The machine
        # evidently coped with that in some configurations (SDZERO's loops
        # measured their intended periods to three decimals) and not in others,
        # which is exactly what feeding a field values outside its domain looks
        # like: it works until it does not, for reasons that look like something
        # else entirely.
        loop_len = sd.loop_end - sd.loop_start
        loop_end = min(sd.loop_end, max(0, n_frames - 1))
        loop_len = max(1, min(loop_len, loop_end))
        struct.pack_into('<I', h, 0x26, loop_end)      # LOOPAT1 -- the loop END
        struct.pack_into('<H', h, 0x2a, 0)             # length fraction
        struct.pack_into('<I', h, 0x2c, loop_len)      # LLNGTH1 -- back from it
        struct.pack_into('<H', h, 0x30, 9999)          # 9999 = hold
    # loops 2-8 stay zeroed: `loop times` 0 means "no loop", which is the
    # correct unused state for them.

    struct.pack_into('<H', h, 0x8a, _clamp(sd.sample_rate, 1, 65535))
    # Address of the stereo partner. 0xFFFF means "none", which is what every
    # mono sample on the disc corpus carries; zero is a value the format never
    # uses and could be read as a valid pointer.
    struct.pack_into('<H', h, 0x88, _NO_POINTER)
    return bytes(h) + pcm


def _extract_channel(pcm: bytes, channels: int, index: int) -> bytes:
    """Interleaved -> one channel, verbatim.

    Used for stereo output, where each half becomes its own AKAI sample file.
    Unlike `_mixdown` this applies NO gain change: halving is what stops a
    correlated pair clipping when summed, and there is no sum here. Scaling
    the halves would quietly alter the level of every stereo conversion.
    """
    n = len(pcm) // (2 * channels)
    out = bytearray(n * 2)
    for i in range(n):
        out[i * 2:i * 2 + 2] = pcm[(i * channels + index) * 2:
                                   (i * channels + index) * 2 + 2]
    return bytes(out)


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
#: **RETRACTED 2026-08-12 (s3ked §52 — NOT §51): LFO2 WORKS. Only its route to
#: pan is dead.**
#:
#: The §51 citation here was wrong and stood for weeks; §51 retracted §45 on the
#: per-zone `VLOUD1`/`VFREQ1`/`VTUNO1`/`VPANO1` fields and contains no mention of
#: LFO2, pan, or a dead route. The two sections are adjacent, same date, both
#: titled "RETRACTION", and §51 is the one that mentions `VPANO1` — so anything
#: grepping for a pan-ish retraction lands on it first. The same slip had
#: independently reached `docs/MODULATION_MATRIX.md`.
#:
#: **AND THE CLAIM ITSELF IS UNDER RE-MEASUREMENT (2026-09-06).** §39 swept
#: `PANDEP`, LFO2's own output depth — not `MODVPAN1`, the pan matrix's AMOUNT.
#: Those are different fields, and the matrix is a PRODUCT: §173 measured the
#: amplitude twin as `swing = 0.010068 * LFODEP * MODVAMP1`, so a zero amount
#: makes any LFO depth inert. Jan photographed a resident program's PAN page
#: showing `Lfo2 > pan: +00`, `Key > pan: +00`, `!Bend > pan: +00`. If the route
#: measures alive with the amount up, §52 is itself wrong and this whole block
#: needs rewriting rather than annotating. Everything from here to the end of this block was written while §39
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
#: **For this writer:** `PANRAT` and `PANDEP` are real, working controls.
#: **AUTO-PAN SOUNDS once `MODVPAN1` is non-zero** — the AMOUNT was the field
#: that was missing, not the route (s3ked §181, retracting §52's "route to pan
#: is dead"). Holding source, `PANDEP` and `PANRAT` identical and moving only the
#: matrix amount took the balance swing from 0.47 dB to 29.75 dB, against
#: `PANPOS` controls putting 60 dB through the same detector in the same run.
#:
#: **The 29.75 dB is a LOWER BOUND, not a calibration** (s3ked's own caveat):
#: it was sampled in 50 ms frames against a 7.11 Hz LFO — 2.8 frames per cycle,
#: above Nyquist but too coarse to catch the extremes. **Do not derive a
#: depth→swing mapping from it.** The `* 50` below is a RANGE mapping from the
#: model's ±1 onto the field's ±50, not a calibrated depth, and the true
#: amount→swing law is unmeasured.
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
#: ── IB304F / expansion boards: WHERE THIS STANDS ─────────────────────────
#:
#: Read this part and stop, unless you are checking the reasoning. Below it is
#: the record of how it was arrived at, kept because four corrections came out
#: of it and each one caught an inference reaching past its evidence. But the
#: record is chronological, and a reader who needs the answer should not have
#: to reconstruct it from seven dated layers -- that is the same defect as a
#: project describing its own maturity three different ways.
#:
#:   1. The S3000XL these findings come from has NO expansion boards: 8 MB of
#:      flash ROM, no EB16, no IB304F. Established by measurement, not assumed.
#:   2. The IB304F gates the SECOND FILTER -- seven fields. It does NOT gate
#:      envelope 3, whose every stage was measured working on that board-less
#:      machine. The owner's manual is wrong on this point.
#:   3. Panel behaviour is not machine behaviour, and does not even predict
#:      itself: EFFECTS is refused outright with the lamp dark, filter 2 is
#:      drawn with a warning line, and the mode register opens the EFFECTS page
#:      anyway with live data behind it.
#:   4. Fifteen fields (filter 2, TONE, ENV3) are nonetheless DANGEROUS -- an
#:      S3000XL crashed twice while that area was exercised. s3ked fences them
#:      behind a declaration. That is a safety interlock over a working
#:      capability, not a claim that the fields are dead.
#:   5. This writer populates none of them. If that changes, (4) is the reason
#:      for care and (2) is the reason not to suppress them outright.
#:   6. The SERVICE manual (2026-08-23, §IB304FDOC) documents the board in one
#:      line -- an optional-accessories entry, no parts list and no schematic,
#:      while the EB16 and IB-208P get both. It does corroborate (2) from the
#:      silicon: `L7A0986 L6029 DFL` appears only in the S3200XL parts list,
#:      the S3200XL is the model whose second filter is standard and the only
#:      one not offered the IB-304F, and both spec tables give the SAME
#:      -12 dB/oct filter -- so the option is a second filter, not a steeper
#:      one. It also supplies a mechanism for the panel behaviour in (3),
#:      better than this comment's "the manual is simply wrong": the spec
#:      tables say 2 envelope generators for an S3000XL and 3 for an S3200XL,
#:      which is what the PANEL exposes, and ENV3 measured working over SysEx
#:      on a board-less machine is what the WIRE does. Both documents are then
#:      self-consistent and the finding stands unchanged.
#:
#: ── how this was arrived at ──────────────────────────────────────────────
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
                    lfo1_rate=None, prog_num: int = 0,
                    midi_channel=None, vel_to_volume_db=None,
                    lfo_to_pan=None, pan_lfo_rate=None) -> bytearray:
    """The 192-byte program common block, filled with the format's own
    documented defaults rather than zeros."""
    p = bytearray(PROGRAM_COMMON_LEN)
    # Block id: 1 = program common. This is NOT the sampler generation --
    # every real program carries 1 whether it is S1000 or S3000, and the
    # generation lives in the directory entry's file type instead.
    p[0x00] = _BLOCK_ID_PROGRAM
    struct.pack_into('<H', p, 0x01, _RAM_BASE_PARA)
    p[0x03:0x03 + AKAI_NAME_LEN] = str_to_akai(name)
    # PRGNUM, the MIDI program number. **Sequential per volume, not 0 for
    # everything**, which is what this wrote until 2026-08-14.
    #
    # s3ked measured the consequence on an S3000XL: loading four volumes with
    # no CLR between them left fifteen programs resident, four of them sharing
    # a program number, and they STACK -- one program change fires all four at
    # once. PRGNUM is stored in the program and reloaded verbatim, so nothing
    # renumbers on load. A volume of ours held every program on the same
    # number, so a single program change addressed the whole volume.
    #
    # 0-BASED, MEASURED (s3ked, 2026-08-14). The panel's RNUM -> SEQU
    # renumbered fifteen resident programs and displayed them as 1..15; read
    # back over SysEx those same fifteen are 0..14. The byte is 0-based and
    # the panel adds one for display. `% 128` is right as well: the values are
    # 0..127, so there are 128 of them.
    #
    # This was written as an INFERENCE here first -- two authored programs
    # carrying 0 and 1, plus a panel reading of "1" for each volume's first
    # program -- and labelling it as one is what got it checked. s3ked had
    # written their own renumber to assign 1, 2, 3... on the strength of the
    # panel display, which would have left the machine's first program number
    # unused and shifted every program up by one. Reading this comment
    # surfaced the conflict; their read settled it, against themselves.
    #
    # Their summary of the shape, which has now caught this project twice: a
    # conclusion drawn from a single display reading, where the display is not
    # the storage. Bytes from files somebody authored were the better evidence
    # the whole time.
    #
    # CLAMPED at 127, not wrapped. This wrapped until 2026-08-14, on the
    # reasoning that wrapping "keeps the first 128 distinct instead of clamping
    # them all onto 127". VinSamLib pointed out what that actually does:
    # **wrapping puts program 128 onto program 0**, which is the collision this
    # whole field exists to avoid, and it lands on the LOW numbers -- the ones
    # most likely to be reached for.
    #
    # Past 128 programs in one volume some collision is unavoidable, since MIDI
    # has 128 program numbers and that is the whole address space. The choice is
    # only where to put the damage. Clamping concentrates it on the tail, so
    # programs 0..126 stay individually addressable and the extras stack on 127
    # together; wrapping spreads it over the beginning of the volume.
    #
    # NOT solved by splitting the volume at 128 programs: the machine is happy
    # to hold more than that, they are all selectable from the panel, and
    # splitting a volume that would have loaded is the over-tight clamp this
    # project has recorded twice as the worse failure -- only the loose kind
    # announces itself. The caller warns instead; see build_akai_volume.
    #
    # OPEN: what the machine does with a PRGNUM byte above 127 is untested. The
    # field is a byte and MIDI is 0..127, so writing 200 is out of spec rather
    # than out of range. Nobody has tried it.
    #
    # WHAT THIS CANNOT FIX, and it is worth knowing: numbering is per volume,
    # so two volumes authored independently both start at 0 and every program
    # in one collides with a program in the other. Loading several volumes
    # without clearing memory between them therefore stacks programs on shared
    # numbers -- s3ked measured fifteen resident programs with four sharing a
    # number, and one program change fires all four at once. There is nothing a
    # writer can do about it: a volume numbered 0..N-1 is correct in isolation.
    # It is documented rather than solved, because the failure is silent -- the
    # user hears four programs where they asked for one and nothing says why.
    p[0x0f] = min(prog_num, 127)
    # PMCHAN. "255 signifies OMNI, 0 to 15 indicate MIDI channel" -- the
    # S2800/S3000/S3200 document, offset 16. Verified 2026-08-10 against a real
    # S3000XL whose own program 0 holds 0 (channel 1): that is the channel that
    # program was created with, not a different convention. Omni is the right
    # default for a converted program, which has no channel of its own.
    # CHANNEL 0, NOT OMNI -- what every commercial disc does.
    #
    # This wrote 0xFF (omni) until 2026-08-18, on the reasoning that "a
    # converted program has no channel of its own, so omni is the sane
    # default". Plausible, and never checked against a real disc. The corpus is
    # emphatic:
    #
    #   factory volumes with 2+ programs, all programs on channel 0   1545
    #   the same with 2 or more DIFFERENT channels                     ~35
    #   factory programs using OMNI (255)          3 of 11410        0.03%
    #
    # and the large ones are unanimous -- 20- and 21-program volumes with every
    # program on channel 0 and PRGNUMs running 0,1,2,3..., which is exactly the
    # shape this writer produces except for the channel.
    #
    # OMNI IS NOT BROKEN, and that was tested rather than assumed before
    # changing it: a 21-program converted volume was bulk-loaded on an S3000XL
    # and program change still selected correctly, with unrelated programs
    # correlating at 0.002 and nothing stacking. So this is not a bug fix.
    #
    # It is changed because omni means every program answers every part, which
    # makes MULTITIMBRAL use impossible -- the whole point of a program's
    # channel is that part 1 plays the bass and part 2 the pads. A user with our
    # volume in a multi would find every program on every part, and nothing in a
    # program list would look wrong. That is also the mechanism behind this
    # project's worst measurement incident (s3ked's 18, "every audio measurement
    # before this was of the wrong program": eleven programs all answering).
    #
    # `midi_channel` still lets a bench disc give each program a channel nobody
    # else uses, which measurement discs need and libraries do not.
    p[0x10] = (_AKAI_DEFAULT_PMCHAN if midi_channel is None
               else _clamp(int(midi_channel), 0, 15))
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
    # V_LOUD, "velocity > loudness". HARDCODED AT 20 UNTIL 2026-09-01
    # (§KRZAMPVEL): the reader never read offset 0x1a at all, so the source's
    # own value was discarded on read and invented here on write. It is real,
    # varying content -- 20/20/25/25/30/36 across six programs on one disc --
    # so an AKAI->AKAI round trip flattened every program's dynamic response
    # to a single number.
    #
    # Through the measured law (s3ked §171): the response rotates about
    # velocity 64 and the full-scale swing is 1.19557 dB per unit, so the byte
    # is the swing divided by that. SIGNED and clamped to the field's own
    # -50..+50: a negative V_LOUD means harder is quieter, which is unusual
    # but legal, and an unsigned clamp would silently drop it.
    #
    # The old 20 stays as the fallback for a source that states nothing, so
    # conversions from formats with no such field are byte-identical to before.
    # `is not None`, NOT truthiness -- the SECOND of two places this mattered
    # (the selection in build_akai_volume was the first, and fixing only that
    # one changed nothing because this line swallowed the 0.0 again). A
    # measured-neutral 0.0 is a source stating it has NO velocity response;
    # only `None` means nobody looked, and only that deserves the fallback.
    if vel_to_volume_db is not None:
        p[0x1a] = _clamp(int(round(vel_to_volume_db
                                   / AKAI_VLOUD_SWING_DB_PER_UNIT)),
                         -50, 50) & 0xFF
    else:
        p[0x1a] = 20
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

    # AFTER THE DEFAULTS LOOP, DELIBERATELY. `_PROGRAM_HW_DEFAULTS` carries
    # `0x1d: PANRAT = 1` and runs last, so writing the rate before it is silently
    # undone -- which is what happened on the first attempt: the amount at 0x59
    # survived (not a default) and the rate did not, giving a program modulated
    # at 0.24 Hz instead of 11.5. A partial write is worse than none here,
    # because the pan would move just slowly enough to look like it works.
    # PAN MODULATION: the AMOUNT, and LFO2's own rate (§PANMOD).
    #
    # `MODSPAN1` at 0x4c is already 8 (= LFO2) from _PROGRAM_HW_DEFAULTS, so the
    # ROUTE has always been wired in everything we emit — with the amount at
    # zero. That is the "wired and the volume down" shape that produced three
    # separate false negatives on 2026-09-06, and here it was our own output.
    #
    # Range is +/-50, NOT +/-99: s3ked wrote 99 and the machine read back 50.
    # At amount 50 they measured ~30 dB of balance swing against a PANPOS
    # control spanning 60 dB, so full scale is about half the static range --
    # consistent with bipolar modulation about centre.
    #
    # THE RATE IS LFO2's LAW, NOT LFO1's. `PANRAT` is 0.23708 Hz/unit, twice
    # LFO1's, reaching 23.47 Hz at 99. Using LFO1's law here puts the sweep at
    # half speed and looks plausible while doing it -- which is exactly the
    # mistake made while writing this, caught against the note at :1536.
    if lfo_to_pan:
        p[0x59] = _clamp(int(round(lfo_to_pan * 50)), -50, 50) & 0xFF
        if pan_lfo_rate:
            p[0x1d] = akai_lfo2_rate_byte(pan_lfo_rate)

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
    # KGMUTE, keygroup 160: the mute group, where **255 is OFF and 0 is a real
    # group**. Never written until 2026-08-24, so every keygroup we authored
    # inherited the buffer's zero fill and landed in group 0 -- and two
    # keygroups sharing a group that overlap in key and velocity cut each
    # other. Measured by s3ked on an S3000XL: 19.1 dB (§AKAIMUTEGRP). 86% of
    # factory keygroups across 9442 programs carry 255, so OFF is the normal
    # authored value and the zeros look like S1000 zero-fill inherited by the
    # 192-byte layout.
    #
    # LATENT for our own output: this writer puts source layers into velocity
    # zones INSIDE one keygroup rather than into overlapping keygroups, and a
    # mute group only acts BETWEEN keygroups. 22 authored programs across two
    # source formats have zero overlaps. Fixed anyway, because "no current
    # victim" is not "correct" and the next feature that emits overlapping
    # keygroups would be bitten silently.
    #
    # It is one of the deliberate divergences from akaiutil, which leaves this
    # at zero as this writer used to -- suppressed in `no_hw_defaults` for the
    # same reason as the modulation-matrix defaults and the filter/envelope
    # laws: the golden hashes exist to pin the MEDIA layout against an
    # independent implementation, not to freeze hardware-measured content.
    k[AKAI_KGMUTE_OFFSET] = _KGMUTE_DEFAULT
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
    # FILQ (keygroup 149): RESONANCE, written since 2026-08-24.
    #
    # This comment used to end "and we still write nothing to it", with the law
    # recorded just below against the day resonance was ever carried across.
    # The reader's half went in on 2026-08-23 and the writer's did not, so
    # every conversion INTO an AKAI dropped resonance -- measured on the
    # library discs the next day, **FILQ changed on 44.8% of round-tripped
    # zones**, almost always to zero. Not a corner case: most of them.
    # L_PTCH (keygroup 150): THE LFO -> PITCH GATE, written since 2026-08-24.
    #
    # The reader has used this since the 23rd -- as a GATE, because 0 means no
    # vibrato and nobody has shown that the value composes multiplicatively
    # with LFODEP. The writer wrote nothing, so it stayed 0, so **every
    # keygroup we have ever written into an AKAI had its LFO->pitch routing
    # switched off.** Measured over the sound libraries: `lfo_to_pitch`
    # changed on **100% of round-tripped zones**, every one to zero.
    #
    # A source's vibrato was being carried faithfully all the way to the last
    # byte and then not routed. Same shape as FILQ, found the same day, by the
    # same harness.
    #
    # WHAT VALUE. The model does not carry L_PTCH -- the reader takes it as a
    # gate and discards the number -- so there is nothing to restore. Written
    # at `AKAI_LFO_DEPTH_CAL_LPTCH`, the routing the depth law was itself
    # measured at, which is the only choice that makes the depth we write mean
    # what the law says it means. A round trip therefore restores the VIBRATO
    # and not the original number, and the harness will keep reporting that
    # difference. That is honest: carrying the value needs the composition
    # measured first, and it is filed rather than guessed.
    _vib = abs(getattr(voice, 'lfo1_to_pitch', 0.0) or 0.0)
    k[_AKAI_LPTCH_OFFSET] = (AKAI_LFO_DEPTH_CAL_LPTCH if _vib > 0.0 else 0) & 0xFF

    k[_AKAI_FILQ_OFFSET] = akai_01_to_filq(
        getattr(voice, 'filter_resonance', 0.0) or 0.0)

    # The law it inverts (s3ked §52, 2026-08-12), replacing their own earlier
    # linear 0.5764 dB/step:
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
    # FILFRQ AND BYTE 151 ARE CHOSEN TOGETHER, because the source specifies a
    # LINE across velocity and this machine expresses it as a resting corner
    # plus a bipolar depth about velocity 64.56. Picking the corner without the
    # depth is what silenced a zone: see akai_velocity_filter().
    _cut = getattr(voice, 'filter_cutoff', None) if voice is not None else None
    if _cut is None:
        k[0x07] = 99                 # wide open (HW-confirmed) when unknown
    else:
        _vmin = getattr(voice, 'velocity_to_filter_min_cents', 0.0) or 0.0
        _vmax = getattr(voice, 'velocity_to_filter_cents', 0.0) or 0.0
        # `hi_key` so the corner can clear the fundamentals this keygroup
        # actually plays -- see the floor in akai_velocity_filter().
        k[0x07], _vf_byte, _vf_lost = akai_velocity_filter(_cut, _vmin, _vmax,
                                                           hi_key=hi_key)
        # K_FREQ (0x08): key follow of filter frequency, SIGNED semitones,
        # oct/oct = K_FREQ / 12, pivot note 64. Never written before
        # 2026-08-24, so an AKAI -> AKAI round trip silently zeroed whatever
        # the source had -- and the reader did not read it either, which is
        # why nothing ever disagreed.
        #
        # Clamped to -30..99: the whole positive half of the field plus the
        # negative range that has been visited.
        #
        # This was -5..+22, then -30..+40, and both were too narrow for the same
        # reason in two different ways. The first was a fit range mistaken for a
        # field range. The second was "declare only what has been visited" --
        # correct in principle, and wrong here because **the positive side had
        # already been swept to 99 a week earlier and the record of it was not
        # consulted**: the corner rises linearly to K_FREQ 99 at 0.508-0.602
        # FILFRQ units per step against 0.511 predicted, with no saturation
        # anywhere in range.
        #
        # This was -5..+22 for one evening and the corpus said that was far too
        # narrow: `filter_keyfollow` changed on **32.6% of round-tripped zones**
        # across the sound libraries, one program carrying -18 and being
        # flattened to -5. On a one-octave span that is the difference between
        # the filter dropping 1.5 octaves across the keyboard and dropping 0.4.
        #
        # THE DOCUMENTS DISAGREE AND BOTH ARE TOO NARROW. The S2800/S3000/S3200
        # sheet says "0 to 12 semitones" -- no sign at all. The S1000 sheet says
        # "+/-24 semitones/octave", which gives sign, unit and bound and is the
        # second independent source for the unit. **Measured, it is linear from
        # -30 to +40 with no knee at 24 or anywhere else**, every point within
        # 96-103% of K_FREQ/12, and every value reading back exactly as written.
        # So +/-24 is a display range too, and NO DOCUMENT STATES THIS FIELD'S
        # REAL LIMIT. s3ked did not find a wall and did not claim one.
        #
        # A predicted knee at 24 was written down before that run and refuted --
        # the second prediction refuted on this one field.
        _kf = getattr(voice, 'filter_keytrack', 0.0) or 0.0
        k[0x08] = _clamp(int(round(_kf * 12.0)), -30, 99) & 0xFF
        if _vf_lost > 50:
            _velfilt_clipped.append((index + 1, _vf_lost))
    # VELOCITY -> FILTER FREQUENCY, KEYGROUP BYTE 151. Written since 2026-08-16;
    # before that a source's velocity-to-cutoff modulation was silently dropped
    # and every converted program got a STATIC corner.
    #
    # The field is not where the documentation puts it. Inherited S1000 tables
    # name offset 9 "V_FREQ, not used, range 0..0" -- and offset 9 is genuinely
    # dead, measured. The live field is in the S3000 EXTENSION block past the
    # S1000's 150-byte keygroup, found by Jan setting Vel>Freq / LFO2>Freq /
    # Env2>Freq on the panel and the three values appearing at 151/152/153.
    #
    # MEASURED on an S3000XL, not inferred (P019, one keygroup, one zone):
    #
    #   FILFRQ 48   byte151  0 -> v30 -68.7 dBFS  v120 -45.2
    #               byte151 12 -> v30 -72.8       v120 -23.1   loud end +22 dB
    #               byte151 25 -> v30 -73.4       v120 -22.0
    #               byte151 50 -> v30 -72.8       v120 -22.1
    #
    # Two things that come only from measuring. It SATURATES: past ~12-25 the
    # sweep stops growing because the quiet end has bottomed out, so the +-50
    # the field accepts is mostly unusable and 25 is full scale in practice.
    # And the saturation point moves with the base -- at FILFRQ 72 it is ~25,
    # at 48 it is ~12 -- so this is scaled to the range that is reachable
    # rather than to the range the field declares.
    #
    # An earlier reading of the same field at FILFRQ 72 concluded that positive
    # depth only darkens quiet notes and never opens loud ones. That was an
    # artefact of a base already open enough to hit the ceiling; at a dark base
    # it plainly opens the top. Kept as the reason this is calibrated at the
    # base the material actually uses.
    #
    # Per KEYGROUP, verified: writing keygroup 1 left keygroup 2 untouched, and
    # the field clamps to +-50 on write (90 read back as 50).
    # Depth from the same joint solve as FILFRQ above. The old `_vf * 25` was
    # calibrated to the saturation seen at ONE dark base -- and that base was
    # itself the fault, so the constant was fitted to a symptom.
    if _cut is not None and _vf_byte:
        k[151] = _vf_byte & 0xFF
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
    # ENVELOPE 2 (filter), wired 2026-08-21. Written ONLY when the source
    # actually carries one and routes it: an envelope with zero depth is
    # inaudible, and writing one anyway would replace a fixed default with a
    # fixed default that merely looks converted.
    _fe = getattr(voice, 'filter_env', None) if voice is not None else None
    _famt = (getattr(voice, 'filter_env_cents', 0.0) or 0.0) if voice else 0.0
    if _fe is not None and abs(_famt) > 0.001:
        # k[0x07] is this keygroup's FILFRQ, set above. The depth is a
        # corner conversion now, so it needs the base it sweeps FROM.
        _a2, _d2, _s2, _r2, _dep = akai_filter_env_bytes(_fe, _famt,
                                                         k[0x07])
        k[0x14], k[0x15], k[0x16], k[0x17] = _a2, _d2, _s2, _r2
        k[_AK_ENV2_DEPTH_OFF] = _dep & 0xFF
    else:
        k[0x14] = 0                     # ATTAK2  -- no envelope in the source
        k[0x15] = 50                    # DECAY2
        k[0x17] = 45                    # RELSE2
        k[0x16] = 99                    # SUSTN2, open: no filter movement
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


def keygroup_count(preset) -> int:
    """How many keygroups `build_program` will emit for this preset.

    Exported so the bank splitter can budget for them without a second copy of
    the grouping rule -- the S3000XL's object pool counts every keygroup, and a
    count that disagreed with what is actually written would be worse than no
    count at all.

    It no longer RESTATES build_program's rule -- it calls it. The docstring
    used to say "the rule must stay identical to build_program's", which is the
    sort of instruction that holds until the day it does not; the rule changed
    on 2026-08-24 and a restated copy would have gone stale that day.

    One keygroup per distinct (key range, keygroup-settings fingerprint),
    clamped to MAX_KEYGROUPS, since keygroups past that are dropped on write
    and never become resident objects.

    **This count can now exceed the old one for the same preset**, because
    layers with different envelopes stop sharing a keygroup. That is the point
    of the change and the budget has to see it: a program that used to cost
    three objects and lose half its envelopes costs six and keeps them.
    """
    return min(len(_group_zones_into_keygroups(preset)), MAX_KEYGROUPS)


def _root_offset_units(z, sample_roots: Optional[dict]) -> int:
    """(sample root - zone root) in AKAI 1/256-semitone units.

    Zero when the zone states no root of its own, or when it agrees with the
    sample, which is the common case and why this went unnoticed: every source
    whose zones simply inherit the sample root converted correctly.
    """
    if not sample_roots:
        return 0
    zr = getattr(z, 'root_key', None)
    if zr is None:
        return 0
    sr = sample_roots.get((getattr(z, 'sample_name', '') or '').strip())
    if sr is None:
        return 0
    return int(round((sr - zr))) * _AKAI_TUNE_UNITS_PER_SEMITONE


def _voice_kg_signature(lo_key: int, hi_key: int, voice) -> bytes:
    """Byte-exact fingerprint of the keygroup this voice alone would produce.

    **Built by CALLING `_keygroup`, not by listing the fields it reads.** A
    hand-maintained list of "the settings that live at keygroup level" is a
    second copy of the rule, and every defect found on 2026-08-24 was a second
    copy that drifted from the first. Render an empty keygroup for each
    candidate voice and compare the bytes: if two voices would produce
    identical keygroup settings, they can share one; if a single byte differs,
    they cannot. The question is answered by the same code that answers it for
    real.

    Zones are excluded deliberately -- an empty zone list writes the same
    unused-slot pattern for every voice, so what remains is exactly the
    per-keygroup state. `index` is fixed at 0 so the RAM address, which is
    positional, does not enter the comparison.
    """
    return bytes(_keygroup(lo_key, hi_key, [], index=0, voice=voice,
                           dead_key_ranges=[]))


def _group_zones_into_keygroups(preset):
    """[( (lo,hi), voice, [zones...] )] -- the ONE grouping rule.

    Shared by `build_program` and `keygroup_count` so the object budget and the
    file can never disagree; `keygroup_count`'s docstring has warned about that
    since it was written.

    **A KEYGROUP HOLDS ONE AMPLITUDE ENVELOPE, ONE FILTER AND ONE FILTER
    ENVELOPE.** This used to group on key range alone and take the settings
    from whichever voice owned the lowest-velocity zone, which silently
    discarded every other voice's envelope over that range. Measured on an
    AKAI -> AKAI round trip 2026-08-24: a source with **six** keygroups in
    three pairs -- a percussive layer at SUSTN1 6 / RELSE1 45 and a sustaining
    layer at SUSTN1 50 / RELSE1 75 -- came back as **three**, all carrying the
    percussive envelope. The sustaining half of the program lost its sustain
    and its release outright.

    **The source used six keygroups precisely because two layers needing
    different envelopes cannot share one.** Merging them threw away the reason
    the structure existed, and nothing in the file said so: the zones were all
    present, the key ranges were right, and only the sound was wrong.

    So the grouping key is (key range, keygroup-settings fingerprint). Layers
    that genuinely agree still merge into velocity zones of one keygroup --
    that is the format's own idiom and costs an object where splitting does
    not. Layers that differ get their own keygroup, which is what the source
    did.

    Overlapping keygroups LAYER on this machine (hardware-measured, see
    `build_program`), so a split pair still sounds together.
    """
    by_key: dict = {}
    order = []
    for voice in getattr(preset, 'voices', []) or []:
        for z in getattr(voice, 'zones', []) or []:
            # A ZONE WITH NO SAMPLE IS NOT A KEYGROUP -- see build_program.
            if not (getattr(z, 'sample_name', '') or '').strip():
                continue
            rng = (z.lo_key, z.hi_key)
            key = (rng, _voice_kg_signature(rng[0], rng[1], voice))
            if key not in by_key:
                by_key[key] = []
                order.append(key)
            by_key[key].append((z, voice))
    out = []
    for key in order:
        pairs = sorted(by_key[key], key=lambda zv: zv[0].lo_vel)
        out.append((key[0], pairs[0][1], [z for z, _ in pairs]))
    return out


def build_program(preset, name: str, prog_num: int = 0,
                  sample_roots: Optional[dict] = None,
                  midi_channel=None,
                  stereo_right: Optional[dict] = None) -> bytes:
    """One Preset -> a complete `.a3p` file.

    `prog_num` is the MIDI program number written to PRGNUM; pass each
    program's position within its volume, or every program in the volume
    answers to the same program change (see `_program_common`).

    `sample_roots` maps sample name -> the root note written into that
    sample's own header. It is REQUIRED to place a zone at the right pitch:
    see the root-offset note on the tune field below.

    Zones are grouped into keygroups by key range: the AKAI keygroup owns a
    key span and holds up to four VELOCITY zones within it, which is the
    inverse of how the common model nests them.
    """
    # GROUPING LIVES IN ONE PLACE (`_group_zones_into_keygroups`) so the object
    # budget and the file cannot disagree.
    #
    # It used to be inline here and keyed on the KEY RANGE alone, taking the
    # filter and envelope from whichever voice owned the lowest-velocity zone
    # -- "a real lossiness", as the comment then said, "a keygroup built from
    # two voices with different envelopes keeps one of them". It was worse than
    # lossy: a layered program came back with every layer wearing the first
    # one's envelope. Voices whose keygroup settings differ now get their own
    # keygroup, which is what the source material does.
    _groups = _group_zones_into_keygroups(preset)

    keygroups = []
    dropped = 0
    spill_keygroups = 0        # extra keygroups the spill created (object budget)
    for key, owner, zs in _groups:
        # OVERLAPPING SPANS LAYER.
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
        # MORE THAN FOUR VELOCITY LAYERS: SPLIT ACROSS KEYGROUPS, DO NOT DROP.
        #
        # A keygroup has four zone slots, so six layers cannot live in one.
        # That is a real format limit and it is where this used to stop --
        # keeping the first four and discarding the rest. Since `zs` is sorted
        # by lo_vel, the ones discarded were the LOUDEST, taking every velocity
        # above the last survivor's hi_vel with them: a six-layer source came
        # out covering 0-95 with nothing from 96 up. Jan reported the program
        # as playing nothing at all, and the machine was right.
        #
        # The four-zone limit is per KEYGROUP, not per program. Several
        # keygroups may cover the SAME key range -- that is how this writer
        # already layers articulations -- so the layers go four at a time into
        # as many keygroups as they need. Their velocity ranges do not overlap,
        # so exactly one sounds at a time and the switching is preserved
        # exactly as the source meant it.
        #
        # An intermediate fix stretched the last survivor to cover the dropped
        # layers' velocities. It removed the silence but still threw two of six
        # layers away, and widened a third over a dynamic range it was not
        # recorded for. Kept here only as the note that the format was never
        # the thing preventing this.
        #
        # The cost is keygroups, which are bounded by MAX_KEYGROUPS and by the
        # sampler's resident object pool -- both checked below, and both far
        # from binding on the programs that need this.
        _zdicts = [dict(
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
            # THE ZONE'S OWN ROOT, WHICH THIS DISCARDED UNTIL 2026-08-16.
            #
            # An AKAI keygroup zone has no root field. Pitch comes from the
            # SAMPLE header's "original pitch" (0x02) against the key played.
            # Our model, and every source format that feeds it, lets a ZONE
            # override the sample's root -- so a sample recorded at B4 can be
            # placed in a zone whose root is 51, and the E4B means "sound this
            # at its natural pitch when key 51 is played".
            #
            # We wrote the sample's root and ignored the zone's. Jan heard it
            # on an S3000XL: 'P004 does not transpose - different sample on
            # different octaves'. The source zones carried roots 51/56/61/66/71
            # against sample roots 71/46/31/60/26, so every keygroup was off by
            # a DIFFERENT amount -- 20, 10, 30, 6 and 45 semitones -- which is
            # exactly what that sounds like.
            #
            # The correction goes in the tune field, because that is the only
            # per-zone pitch control the format has:
            #
            #     played  = key - sample_root + tune      (what the machine does)
            #     wanted  = key - zone_root               (what the source means)
            #     => tune = sample_root - zone_root
            #
            # A sample shared by zones with different roots therefore gets a
            # different tune per zone, which is correct and is why this cannot
            # be fixed by rewriting the sample header instead.
            # COARSE + FINE, since 2026-08-24. This read `fine_tune` alone,
            # so a zone tuned a whole semitone or more lost everything above
            # the cents -- an octave layer wrote as 0. Found by the AKAI ->
            # AKAI round-trip test the day it was written, which is the
            # mirror of the reader defect fixed the night before
            # (§AKAITUNEREAD): the reader put an octave entirely into
            # fine_tune, and the writer read only fine_tune. Neither side
            # could see it alone.
            tune=_akai_tune_units(
                     _or_default(getattr(z, 'coarse_tune', None), 0) * 100.0
                     + _or_default(getattr(z, 'fine_tune', None), 0))
                 + _root_offset_units(z, sample_roots),
            # `ZoneMapping.pan` is -1.0..+1.0 centred on 0.0; the AKAI field
            # is -50..+50 centred on 0. This used to subtract 0.5 first, on
            # the assumption of a 0..1 scale -- which put every *centred* zone
            # hard left. It went unnoticed because `or 0.5` rewrote the 0.0
            # that would have exposed it.
            pan=int(round(_or_default(getattr(z, 'pan', None), 0.0) * 50)),
            # VLOUD1, the per-zone level offset. Dropped entirely until
            # 2026-08-17 -- the encoder was in place and nothing ever set
            # 'loudness', so 14.8% of corpus zones lost their level offset in
            # silence.
            #
            # MEASURED (s3ked, 2026-08-17): dB = 0.60576 * VLOUD1 - 20.1778,
            # r2 0.999896 over -50..+20, so 0.60576 dB per unit. The model
            # carries `volume` already in dB, which makes this a division.
            #
            # CLAMPED AT +20, NOT +50. Above +20 the field saturates -- +30
            # through +50 sit within 1.09 dB of each other -- because it is
            # reaching the same output ceiling as the program level, from the
            # zone offset instead. So the usable top MOVES with PRLOUD, and
            # writing +50 would look like more gain while delivering none.
            # Same base-and-depth interaction as FILFRQ with byte 151, in a
            # second field family. Real sources sit far below it: the corpus
            # spans -12.5..+2.5 dB, about -21..+4 units.
            loudness=_clamp(int(round(
                _or_default(getattr(z, 'volume', None), 0.0) / 0.60576)),
                -50, 20),
        ) for z in zs]
        # STEREO: one zone becomes two, hard-panned, in the SAME keygroup.
        #
        # Layout read off real library discs (§AKAISTEREO2): zone 1 the `-L`
        # sample at pan -50, zone 2 the `-R` at +50, both over the full
        # velocity range of the zone they replace.
        #
        # The source zone's own pan is DISCARDED for these, deliberately. A
        # stereo sample's image lives in the difference between its channels;
        # panning both halves to some inherited centre would collapse exactly
        # the thing writing two files is for. A source pan on a stereo sample
        # has no faithful rendering here, and hard-panned is the one the
        # machine's own libraries use.
        if stereo_right:
            _exp = []
            for _z in _zdicts:
                _rn = stereo_right.get(_z['sample_name'])
                if _rn:
                    _l = dict(_z); _l['pan'] = -50
                    _r = dict(_z); _r['pan'] = 50; _r['sample_name'] = _rn
                    _exp.append((_l, _r))
                else:
                    _exp.append((_z,))
            _zdicts = _exp
        else:
            _zdicts = [(_z,) for _z in _zdicts]

        # PACK WITHOUT SPLITTING A PAIR.
        #
        # A stereo pair whose halves land in different keygroups is not a
        # stereo voice -- it is two mono keygroups over the same range, which
        # the machine will happily play and which no check downstream would
        # question. Chunking by a flat count of ZONES splits a pair whenever an
        # odd number of mono zones precedes it, so pack by group instead.
        chunk, first = [], True
        for _grp in _zdicts:
            if len(chunk) + len(_grp) > MAX_ZONES_PER_KEYGROUP and chunk:
                if not first:
                    dropped += len(chunk)
                    spill_keygroups += 1
                keygroups.append((key, owner, chunk))
                chunk, first = [], False
            chunk.extend(_grp)
        if chunk:
            if not first:
                dropped += len(chunk)      # counted as "carried into an extra
                                           # keygroup", reported as such below
                spill_keygroups += 1       # and the EXTRA KEYGROUPS are counted
                                           # separately: VinSamLib budgets an
                                           # S3000XL volume against a pool of
                                           # 1006 resident objects, in which a
                                           # keygroup costs the same as a
                                           # program. A faithful, nothing-lost
                                           # restructure can still be what stops
                                           # a volume loading, so they need the
                                           # NUMBER, not the category.
            keygroups.append((key, owner, chunk))

    if dropped:
        # NOT a loss -- the layers are kept, in extra keygroups.  Published as
        # INFO so a consumer can distinguish this from the real loss below,
        # which the printed text alone makes easy to confuse.
        _diag(_I, 'AKAI_LAYERS_SPILLED',
              f"{dropped} velocity layer(s) beyond {MAX_ZONES_PER_KEYGROUP} "
              f"per keygroup carried into additional keygroups over the same "
              f"key range; all layers kept",
              content_lost=False,
              detail={'spilled': dropped,
                      'keygroups_added': spill_keygroups,
                      'max_per_keygroup': MAX_ZONES_PER_KEYGROUP},
              echo=f"    [INFO] {dropped} velocity layer(s) beyond "
                   f"{MAX_ZONES_PER_KEYGROUP} per keygroup carried into "
                   f"additional keygroups over the same key range — all "
                   f"layers kept")
    if len(keygroups) > MAX_KEYGROUPS:
        _diag(_W, 'AKAI_KEYGROUPS_DROPPED',
              f"{len(keygroups)} key ranges exceed the AKAI limit of "
              f"{MAX_KEYGROUPS}; the highest "
              f"{len(keygroups) - MAX_KEYGROUPS} were dropped",
              content_lost=True,
              detail={'keygroups': len(keygroups),
                      'limit': MAX_KEYGROUPS,
                      'dropped': len(keygroups) - MAX_KEYGROUPS},
              remedy='reduce the number of key zones in the source preset, or '
                     'split it across more than one program',
              echo=f"    [WARN] {len(keygroups)} key ranges — AKAI allows "
                   f"{MAX_KEYGROUPS}; the highest "
                   f"{len(keygroups)-MAX_KEYGROUPS} dropped")
        keygroups = keygroups[:MAX_KEYGROUPS]
    if not keygroups:
        raise ValueError(f"preset '{name}' has no zones to write")

    lo = min(k[0][0] for k in keygroups)
    hi = max(k[0][1] for k in keygroups)
    # LFO rate from the first voice that carries one -- the AKAI LFO is per
    # PROGRAM while ours is per voice, so there is one to pick and this is it.
    _lfo = next((v.lfo1_rate for v in preset.voices
                 if getattr(v, 'lfo1_rate', None) is not None), None)
    # V_LOUD is per PROGRAM on the AKAI while ours is per voice, so take the
    # first voice that states one -- the same rule the LFO rate above uses.
    # `is not None`, NOT truthiness. A measured-neutral 0.0 is a source
    # STATING that it has no velocity response, and it is falsy -- so the old
    # test fell through to the writer's fallback of 20 and invented a 23.9 dB
    # swing for a program that explicitly asks for none. Found 2026-09-03
    # building the AKAI leg of a listening test from an MPC bass whose every
    # keygroup carries `VelocitySensitivity 0.000000`; it wrote V_LOUD 20.
    # Same None-vs-0.0 confusion Jan heard on the KRZ path a day earlier, and
    # the LFO line directly above already had it right.
    # THE FITTED SWING, not the source's own span (§MPCVELSHAPE). The AKAI is
    # dB-linear about velocity 64, so a dB-linear source fits exactly and this
    # is the number it always was; a CURVED source -- the MPC -- has no single
    # span that describes it, and its v1..v127 figure is the worst available
    # choice because one inaudible point at the bottom of a log curve sets the
    # slope for everything. `fit_velocity_line` returns the best line this
    # field can hold instead.
    #
    # ONLY THE SLOPE IS USED HERE. The fit's static level belongs to the voice,
    # and V_LOUD is per PROGRAM on this machine, so there is nowhere to put it
    # -- which is the same reason the pivot correction collapses on this target
    # (see the note above `_program_common`).
    _vsrc = next((v for v in preset.voices
                  if getattr(v, 'velocity_to_volume_db', None) is not None), None)
    _vvol = None if _vsrc is None else fit_velocity_line(
        _vsrc.velocity_to_volume_db,
        getattr(_vsrc, 'velocity_to_volume_curve', VELOCITY_CURVE_DB_LINEAR),
        getattr(_vsrc, 'velocity_to_volume_pivot', None),
        VEL_VOL_PIVOT_AKAI)[0]
    # NO VELOCITY-PIVOT OFFSET HERE, and that is a result rather than an
    # omission. The AKAI rotates its velocity->loudness response about
    # velocity 64 while a KRZ/MPC/E4XT source rotates about 127, so carrying a
    # swing across sits a constant S*(64-P_src)/126 off -- which the KRZ and
    # E4B writers repair with a static level shift. Here it collapses.
    #
    # V_LOUD is per PROGRAM on this machine (see `_vvol` above: exactly one
    # voice's swing survives, the rest are discarded on the way in). One swing
    # written means ONE offset, identical for every keygroup and every
    # velocity -- so applying it and then subtracting the preset's own maximum,
    # which is that same number, leaves zero. The correction is a pure change
    # of the program's overall loudness, and overall loudness is a knob.
    #
    # It would come back the day a per-keygroup velocity->loudness cord is
    # written (the mod matrix has the slots), because then the offsets differ
    # between keygroups and the difference is audible balance.
    # Pan modulation from the first voice that states one -- same rule as the
    # LFO rate above, because the AKAI's pan matrix is per PROGRAM.
    _pan = next((getattr(v, 'lfo1_to_pan', 0.0) or getattr(v, 'lfo2_to_pan', 0.0)
                 for v in preset.voices
                 if (getattr(v, 'lfo1_to_pan', 0.0) or getattr(v, 'lfo2_to_pan', 0.0))), None)
    out = _program_common(name, len(keygroups), lo, hi, lfo1_rate=_lfo,
                          lfo_to_pan=_pan, pan_lfo_rate=_lfo,
                          prog_num=prog_num, midi_channel=midi_channel,
                          vel_to_volume_db=_vvol)
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


def sample_identity(sd) -> bytes:
    """Everything build_sample() writes EXCEPT the name.

    Two samples with this key equal produce byte-identical files under the same
    name, so they are the same object to the sampler and must NOT be renamed
    apart -- a load replaces an identical item with an identical item, which
    costs one object and one copy of the audio instead of two.

    Hashing the PCM alone was not enough and the corpus said so within minutes:
    identical audio with different loop points or a different rate shares the
    audio hash, kept one name, and then wrote different bytes -- which is the
    data-loss case the uniquifier exists to prevent, reintroduced by a key that
    was too narrow. Every field the header carries is in here.

    **And the first count of that was badly understated.** Measuring it over
    six split banks found ONE instance, which read as a curiosity. Measured
    properly -- every sample occurrence on 21 library discs, 36 645 of them
    under 34 234 distinct names:

        repeats with DIFFERENT audio                   :  436
        repeats with IDENTICAL audio, DIFFERENT HEADER : 1499

    The class this key exists for is the LARGEST of the two, not a one-off.
    VinSamLib measured the same shape independently (151 and 875) and named the
    cause: drum-machine material files the same hit under the same name in kit
    after kit, with different tuning or loop settings and identical audio.

    Our absolute counts and theirs differ by roughly 2x with the same ratio,
    which means one of us is counting a different population -- they report
    13 877 distinct names where we see 34 234. Unresolved, and it does not
    change what this function has to hash.
    """
    h = hashlib.sha256()
    h.update(sd.data)
    lt = getattr(sd, 'loop_type', LoopType.NO_LOOP)
    for v in (getattr(sd, 'sample_rate', 0), getattr(sd, 'channels', 1),
              getattr(sd, 'root_note', 60), getattr(sd, 'fine_tune', 0),
              getattr(sd, 'loop_start', 0), getattr(sd, 'loop_end', 0),
              lt.value if isinstance(lt, LoopType) else lt):
        h.update(str(v).encode())
    return h.digest()


def _check_stereo_halves(prog: bytes, fn: str, stereo_right: dict,
                         quiet: bool = False) -> list:
    """Verify every stereo left half written into a program has its right half.

    §AKAISTEREO measured why this cannot be left to anything downstream: a
    program referencing only the left half **loads cleanly, raises no error and
    is not dangling** -- nothing it asked for is missing -- and simply plays
    mono. Neither the machine, nor `collect()`, nor `silence_audit.py` has any
    way to notice. The failure is a silent halving of the material, so stereo
    support has to carry its own check or it has none at all.

    Reads the bytes actually written rather than the intent that produced them,
    so a fault in the zone expansion or the keygroup packing is caught too.
    """
    n_kg = prog[0x2a] if len(prog) > 0x2a else 0
    seen = set()
    for k in range(n_kg):
        base = PROGRAM_COMMON_LEN + k * KEYGROUP_LEN
        names = []
        for zo in _ZONE_OFFSETS:
            o = base + zo
            if o + AKAI_NAME_LEN > len(prog):
                continue
            nm = akai_to_str(prog[o:o + AKAI_NAME_LEN]).strip()
            if nm:
                names.append(nm)
        for nm in names:
            r = stereo_right.get(nm)
            # BOTH HALVES IN THE SAME KEYGROUP, not merely both present:
            # halves split across keygroups are two mono voices, not a stereo
            # one, and that is precisely what the pair-aware packing prevents.
            if r and r not in names:
                seen.add(nm)
    if seen and not quiet:
        print(f"    [WARN] {fn}: {len(seen)} stereo sample(s) referenced by "
              f"their left half only — those keygroups will play MONO "
              f"({', '.join(sorted(seen)[:3])}"
              f"{', …' if len(seen) > 3 else ''})")
    return sorted(seen)


def build_akai_volume(bank: Bank, bank_name: Optional[str] = None,
                      quiet: bool = False,
                      taken: Optional[set] = None,
                      taken_prog: Optional[set] = None,
                      type0: bool = False,
                      stereo: bool = True) -> list:
    """Build a Bank's AKAI volume contents as ``[(filename, data), ...]``.

    One file per program and per sample, which is how the sampler's own
    volumes are laid out.  Names carry the canonical `.S3` / `.P3` extensions:
    those are not decoration, the directory-entry file-type byte is derived
    from them, so a file without one cannot be placed on a disk at all.

    ``type0`` additionally writes the four auxiliary files the instrument's own
    **type-0** save produces -- effects, multi, drum inputs, take list -- using
    the contents the machine itself writes (`akai_aux_defaults`).  Without it a
    volume we build is a **type-1** save, which is valid but lacks the four
    files every real library volume carries; a user reloading it finds the
    effects and the multi gone.

    OFF BY DEFAULT, deliberately.  It adds ~11.7 KB and four directory entries
    to every volume and changes the on-disk layout, and as of 2026-08-18 no
    volume written this way has been loaded by an S3000XL.  It is a capability
    to be tested, not yet a recommendation.
    """
    files: list = []

    # AKAI names are 12 characters, shorter than the 16 the rest of the
    # pipeline uses, so they can collide here even when they did not before.
    #: NAMES MUST BE UNIQUE ACROSS EVERY VOLUME OF ONE CONVERSION, not just
    #: within a volume, so the caller passes shared sets when it writes several.
    #:
    #: **A load REPLACES a resident item of the same name rather than adding a
    #: second one** (s3ked, measured 2026-08-14: five consecutive loads of
    #: already-resident volumes moved the object pool by exactly zero). Per
    #: volume, uniquifying was enough. Across a split it is not, and the
    #: consequences differ in severity:
    #:
    #:   * two programs sharing a name -- the second load silently REPLACES the
    #:     first, and the user is short a program with nothing to say so.
    #:   * two SAMPLES sharing a name and carrying different audio -- worse.
    #:     Zones reference samples BY NAME, so the first volume's programs now
    #:     play the second volume's audio. Silent, and wrong rather than absent.
    #:
    #: Measured before fixing: a 40-preset library whose names truncate alike
    #: splits into two volumes with 17 program names and 17 sample names in
    #: both, the samples carrying different payloads under the same name.
    taken = taken if taken is not None else {}
    #: Programs get their OWN namespace. Sharing one set with the samples would
    #: rename a program merely for matching a sample's name, which nothing
    #: requires -- they are different file types in the directory.
    taken_prog = taken_prog if taken_prog is not None else {}

    def uniq(stem: str, taken=taken, fallback: str = 'SAMPLE',
             content: Optional[bytes] = None) -> str:
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
        base = (stem or fallback).upper()[:AKAI_NAME_LEN]
        if not bytes(str_to_akai(base)).strip(bytes([_AKAI_SPACE])):
            base = fallback
        # RENAME ONLY WHEN DIFFERENT CONTENT HOLDS THE NAME.
        #
        # Renaming on any collision was wrong in the common case, and the
        # measurement is stark: splitting six real library banks produces 1210
        # cross-volume sample-name collisions carrying IDENTICAL audio against
        # 15 carrying different audio. 99 % of the renames bought nothing.
        # (VinSamLib found the same on their corpus -- 10 identical, 0
        # differing, on one split -- and raised it.)
        #
        # It is not merely wasted media. A load REPLACES a resident item of the
        # same name, so two volumes carrying the same sample under the same
        # name cost ONE object and one copy of the audio. Rename it and they
        # cost two of each -- on a machine with 32 MB and a 1006-object pool,
        # for samples the split shares precisely because both halves need them.
        #
        # Only a name held by DIFFERENT bytes loses data, and that is the case
        # this guard exists for.
        cand = base
        n = 1
        while True:
            key = bytes(str_to_akai(cand))
            held = taken.get(key, _UNSET) if hasattr(taken, 'get') else (
                _UNSET if key not in taken else None)
            if held is _UNSET:
                break                      # free
            if content is not None and held == content:
                return cand                # same name, same bytes: reuse it
            suf = str(n)
            cand = base[:AKAI_NAME_LEN - len(suf)] + suf
            n += 1
        if hasattr(taken, 'setdefault'):
            taken[bytes(str_to_akai(cand))] = content
        else:
            taken.add(bytes(str_to_akai(cand)))
        return cand

    #: source sample name -> the distinct root notes its PRESET ZONES give it.
    #: Computed before anything is written, because the sample header needs it.
    #: When a sample is referenced with exactly ONE root, that root goes into
    #: its header and no per-zone tune correction is needed -- the common case,
    #: and the one that must not depend on an unverified tune range.
    _zone_roots: dict = {}
    for _pr in bank.presets:
        for _v in getattr(_pr, 'voices', []) or []:
            for _z in getattr(_v, 'zones', []) or []:
                _sn = (getattr(_z, 'sample_name', '') or '').strip()
                _rk = getattr(_z, 'root_key', None)
                if _sn and _rk is not None:
                    _zone_roots.setdefault(_sn, []).append(int(_rk))

    def _chosen_root(sd):
        """The root to write into this sample's header.

        One AKAI sample file carries ONE root, so a sample used at several
        roots -- the same hit shared by two programs at different pitches --
        cannot be exact for all of them. The MAJORITY root goes in the header,
        so the fewest zones are left depending on a tune correction whose
        range this project has not verified.
        """
        rs = _zone_roots.get(sd.name) or []
        if rs:
            return _clamp(max(set(rs), key=rs.count), 24, 127)
        return _clamp(_or_default(getattr(sd, 'root_note', None), 60), 24, 127)

    def uniq_stereo_base(stem: str, ident: bytes) -> str:
        """A <=10-character base whose `-L` AND `-R` names are both free.

        The two halves must stay a matched pair, so they cannot be uniquified
        independently -- `uniq()` resolving a collision on the right half alone
        would produce `FOO-L` beside `FOO1-R`, two names that no longer look
        like a pair and, worse, a `-R` that some other sample may legitimately
        claim later. So the BASE is what gets uniquified, against both suffixed
        forms at once, and both are reserved together.

        Reserved under distinct identities: the halves carry different audio,
        so recording one identity for both would let the reuse path in
        `uniq()` hand the same name to a genuinely different sample.
        """
        # rstrip AFTER truncating: a 10-character cut lands mid-word as often
        # as not, and 'MLOGUE 01 -L' reads as a name with a stray space rather
        # than as a pair suffix. Real discs carry none ('B29C0-0999-L').
        base = (stem or 'SAMPLE').upper()[:AKAI_NAME_LEN - 2].rstrip()
        if not bytes(str_to_akai(base)).strip(bytes([_AKAI_SPACE])):
            base = 'SAMPLE'
        cand, n = base, 1
        while True:
            kl = bytes(str_to_akai(cand + '-L'))
            kr = bytes(str_to_akai(cand + '-R'))
            hl = taken.get(kl, _UNSET) if hasattr(taken, 'get') else (
                _UNSET if kl not in taken else None)
            hr = taken.get(kr, _UNSET) if hasattr(taken, 'get') else (
                _UNSET if kr not in taken else None)
            if hl is _UNSET and hr is _UNSET:
                break                                   # both halves free
            if hl == ident + b'L' and hr == ident + b'R':
                return cand                             # same pair, same audio
            suf = str(n)
            cand = base[:AKAI_NAME_LEN - 2 - len(suf)] + suf
            n += 1
        if hasattr(taken, 'setdefault'):
            taken[bytes(str_to_akai(cand + '-L'))] = ident + b'L'
            taken[bytes(str_to_akai(cand + '-R'))] = ident + b'R'
        else:
            taken.add(bytes(str_to_akai(cand + '-L')))
            taken.add(bytes(str_to_akai(cand + '-R')))
        return cand

    #: source sample name -> (left AKAI name, right AKAI name), for the zone
    #: expansion in build_program. Empty when stereo output is off.
    stereo_pairs: dict = {}

    renamed: dict = {}
    for sd in bank.samples:
        if stereo and getattr(sd, 'channels', 1) >= 2:
            # TWO FILES, ONE PER CHANNEL -- the format has no stereo sample.
            # Layout copied from real library discs: see §AKAISTEREO2.
            b = uniq_stereo_base(sd.name, sample_identity(sd))
            ln, rn = b + '-L', b + '-R'
            stereo_pairs[sd.name] = (ln, rn)
            root = _chosen_root(sd)
            for half, chan in ((ln, 0), (rn, 1)):
                files.append((f"{half.strip()}.S3",
                              build_sample(sd, name=half, root_override=root,
                                           channel=chan)))
            if not quiet:
                print(f"  Sample: {ln}.S3 + {rn}.S3 (stereo pair, "
                      f"{sd.sample_rate}Hz, "
                      f"{len(sd.data)//2//max(getattr(sd,'channels',1),1)} frames)")
            if b != sd.name.upper()[:AKAI_NAME_LEN - 2]:
                renamed[sd.name] = ln
            continue
        nm = uniq(sd.name, content=sample_identity(sd))
        if nm != sd.name.upper()[:AKAI_NAME_LEN]:
            renamed[sd.name] = nm
        # THIS IS AN AKAI DIRECTORY ENTRY, NOT A HOST FILENAME.
        #
        # It used to run through `safe_filename`, which sanitises for a PC
        # filesystem. That turned '#' into '_', and '_' is not in the AKAI
        # charset (0123456789 A-Z#+-.), so the encoder then wrote it as a
        # SPACE. The result: a sample whose header says '5BSHRDF#1' sitting in
        # a directory entry that says '5BSHRDF 1'. One sample, two names.
        #
        # The zones reference the header form, so the volume looked correct on
        # disc -- every zone resolved, and a diff of zone bytes against the
        # machine came back 70/70 identical. What that check could not see is
        # whether the named samples were RESIDENT. s3ked loaded the volume and
        # found 15 of them absent from RAM and 34 zone references dangling:
        # every sharp in the volume silent, which is what Jan reported by ear
        # this morning and what I then wrongly talked myself out of.
        #
        # '#' is legal here -- charset index 37 -- and so is '.'. The reader
        # takes the name from the entry's 12 bytes and derives the extension
        # from the file-TYPE byte, never by splitting the string, so nothing in
        # the AKAI charset needs escaping. Replacing '.' with '-' was my first
        # attempt and it simply moved the defect: 15 sharps became 9 dots.
        fn = f"{nm.strip()}.S3"
        files.append((fn, build_sample(sd, name=nm, root_override=_chosen_root(sd))))
        if not quiet:
            print(f"  Sample: {fn} ({sd.sample_rate}Hz, {len(sd.data)//2} frames)")
    if renamed:
        _diag(_I, 'AKAI_NAMES_SHORTENED',
              f"{len(renamed)} sample name(s) shortened to the AKAI "
              f"{AKAI_NAME_LEN}-character limit",
              content_lost=False,
              detail={'count': len(renamed),
                      'limit': AKAI_NAME_LEN,
                      'renamed': dict(list(renamed.items())[:64])},
              echo=('' if quiet else
                    f"    [INFO] {len(renamed)} sample name(s) shortened to "
                    f"the AKAI 12-character limit"))

    name_map = {sd.name: (stereo_pairs[sd.name][0] if sd.name in stereo_pairs
                          else (renamed.get(sd.name)
                                or sd.name.upper()[:AKAI_NAME_LEN]))
                for sd in bank.samples}
    #: AKAI name -> the root note actually written into that sample's header,
    #: so a zone can be pitch-corrected against it (see _root_offset_units).
    _roots = {name_map[sd.name]: _chosen_root(sd) for sd in bank.samples}
    #: Both halves of a stereo pair carry the same root, and the zone tune
    #: correction is looked up BY AKAI NAME -- so the right half needs its own
    #: entry or every stereo zone's right channel loses the correction and the
    #: two halves play at different pitches.
    for _sd in bank.samples:
        if _sd.name in stereo_pairs:
            _roots[stereo_pairs[_sd.name][1]] = _chosen_root(_sd)
    #: left AKAI name -> right AKAI name, which is what build_program needs:
    #: by the time it sees a zone the source name has already been remapped.
    _stereo_right = {l: r for (l, r) in stereo_pairs.values()}
    _chosen_root_by_name = {sd.name: _chosen_root(sd) for sd in bank.samples}
    # PRGNUM: HONOUR THE SOURCE'S OWN NUMBERS WHEN THEY ARE USABLE.
    #
    # `Preset.program_number` already carries what the source said -- sf2_parser
    # takes it from the SF2 preset header, gig_parser from the instrument, and
    # e4b_writer has always written it through. The first version of this fix
    # ignored all that and renumbered positionally, which solved the collision
    # by discarding the author's intent: an SF2 bank whose organ sits on program
    # 16 would have come out on whatever slot it happened to occupy.
    #
    # So: use the source numbers when they are distinct and in range, and fall
    # back to positional when they are not.
    #
    # **VinSamLib deliberately does the opposite -- always positional -- and
    # both are right, because the tools are different things (Jan, 2026-08-14).**
    # This is a BATCH CONVERTER: it is handed input it did not arrange and must
    # treat it in a standardized, repeatable way, so the source's own numbering
    # is information about the input and discarding it would be the converter
    # inventing an answer. VinSamLib builds banks by hand: there is no source
    # ordering to respect, the user arranged the programs themselves, and the
    # position they see IS the information, so numbering from it is the thing
    # they can predict without opening anything.
    #
    # Recorded because the two implementations now disagree on purpose, and the
    # obvious tidy-up -- make them match -- would break whichever one it was
    # applied to. Several parsers set 0 for every
    # preset (sfz, and our own AKAI reader), which collides immediately and
    # correctly takes the fallback -- that case is indistinguishable from "no
    # information", which is what it is.
    _wanted = [getattr(pr, 'program_number', 0) or 0
               for pr in bank.presets if pr.voices]
    _usable = (len(set(_wanted)) == len(_wanted)
               and all(0 <= v < 128 for v in _wanted))
    _over_127 = False            # set when a volume outruns the MIDI address space
    n_written = 0                # PRGNUM counts programs WRITTEN, and presets
                                 # with no voices are skipped below -- counting
                                 # the enumeration would leave gaps in the
                                 # numbering for no reason.
    for i, preset in enumerate(bank.presets):
        if not preset.voices:
            continue
        # UNIQUIFIED, like the samples above. Until 2026-08-14 this was a bare
        # truncation, and three presets named 'bas:303 Spectral',
        # 'bas:303 Spec 2V' and 'bas:303 Spec 3V' all became 'BAS_303 SPEC'
        # -- one filename, written three times, so the volume ended up with
        # FOUR programs where the bank had six and nothing said so. The two
        # lost programs are not recoverable from the output.
        #
        # Found while fixing PRGNUM: the new sequential numbers came out
        # 2, 3, 4, 5 on a four-program volume, and numbers starting at 2 are
        # only possible if two earlier programs went missing. A collision that
        # had been silent for as long as the writer existed was visible in
        # ninety seconds once something downstream counted.
        pname = uniq(((bank_name or preset.name) if len(bank.presets) == 1
                      else preset.name), taken_prog, 'PROGRAM')
        # Zones address samples by name, so they must use the AKAI-shortened
        # ones or the program will reference files that were never written.
        for v in preset.voices:
            for z in v.zones:
                z.sample_name = name_map.get(z.sample_name, z.sample_name)
        fn = f"{safe_filename((pname or f'PROGRAM{i}').strip().upper(), 'PROGRAM')}.P3"
        # PRGNUM 0 IN THE FALLBACK -- CONSIDERED AND REJECTED (§AKAIPRGNUM0).
        # s3ked flagged that a cold-booted S3000XL carries a boot-resident
        # `TEST PROGRAM`/`SINE` at PRGNUM 0, and a first version of this
        # comment shifted the positional fallback to start at 1 to avoid a
        # collision there. Jan corrected it the same night: loading with CLR
        # first -- the normal panel workflow, not a special precaution --
        # already clears that boot-resident program before anything of ours
        # loads, so the collision this was defending against does not occur
        # in ordinary use. Shifting our own numbering is not the fix for an
        # operating-procedure question on the machine side; reverted.
        _pnum = ((getattr(preset, 'program_number', 0) or 0) if _usable
                 else n_written)
        if _pnum > 127 and not _over_127:
            _over_127 = True
        _pdata = build_program(preset, pname, prog_num=_pnum,
                               sample_roots=_roots,
                               stereo_right=_stereo_right)
        _check_stereo_halves(_pdata, fn, _stereo_right, quiet)
        files.append((fn, _pdata))
        n_written += 1
        if not quiet:
            print(f"  Program: {fn} "
                  f"({sum(len(v.zones) for v in preset.voices)} zone(s))")
    _tuned = sum(1 for pr in bank.presets
                 for v in getattr(pr, 'voices', []) or []
                 for z in getattr(v, 'zones', []) or []
                 if (getattr(z, 'sample_name', '') or '').strip()
                 and getattr(z, 'root_key', None) is not None
                 and len(set(_zone_roots.get((z.sample_name or '').strip(), []))) > 1
                 and int(z.root_key) != _chosen_root_by_name.get((z.sample_name or '').strip()))
    if _tuned and not quiet:
        print(f"  [WARN] {_tuned} zone(s) reference a sample that other zones "
              f"use at a different root. One AKAI sample file holds one root, "
              f"so those zones are pitched by the per-zone TUNE field, whose "
              f"usable range is inferred rather than measured. If they sound "
              f"transposed, that field is the reason.")
    if _over_127 and not quiet:
        print(f"  [WARN] this volume holds more than 128 programs, and MIDI has "
              f"128 program numbers. Programs past the 128th all carry number "
              f"127 and will stack on one program change; they remain "
              f"selectable from the sampler's own panel.")

    if type0:
        # Appended AFTER programs and samples, which is the order the
        # instrument's own type-0 volumes carry them.
        from writers.akai_aux_defaults import AUX_FILES
        files.extend((name, bytes(data)) for name, data in AUX_FILES)

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
