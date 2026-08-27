#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# This file is part of mpc2emu.
#
# AKAI S3000-series reader. The format is documented in
# docs/AKAI_S3000_FORMAT.md, which cites its sources: Hiroyuki Ohsaki's
# "AKAI S3000 Series Disk and File Formats" (the primary reference, derived
# by binary analysis and the basis of akaitools) cross-checked against
# akaiutil (GPL-2). Akai never published the format.
#
# No third-party source code copied -- this is written from the documented
# offsets, and where the two references disagree the code says so and
# detects rather than guesses.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
AKAI S3000 Parser
-----------------
Reads AKAI S3000-series **program** (`.a3p`) and **sample** (`.a3s`) files
into the common Bank model, plus the disk images that carry them.

The S3000 program is an extension of the S1000 one and the two are told
apart by a header-id byte (1 = S1000, 3 = S3000), so both are read here.

Scope note: this reads *extracted* program/sample files and raw disk images.
It does not drive SCSI hardware.
"""

import os
import struct
from pathlib import Path
from typing import Optional

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType,
    akai_filfrq_to_hz, hz_to_e4b_cutoff, AKAI_FILTER_LAW, AKAI_FILTER_OPEN,
    AKAI_ENV2_ATTACK, AKAI_ENV2_DECAY, AKAI_ENV2_RELEASE,
    AKAI_ENV2_DEPTH_OFFSET, AKAI_ENV2_DEPTH_MAX, akai_env2_stage_seconds,
    AKAI_VLOUD_DB_PER_UNIT, AKAI_TUNE_UNITS_PER_SEMITONE,
    akai_filq_to_01, AKAI_MUTE_CUT_SECONDS,
    akai_lfo_rate_hz, akai_lfo_depth_to_pitch, akai_lfo_delay_seconds,
    akai_env2_target_hz, E4B_CUTOFF_MAX_HZ, E4XT_FENV_BYTE_PER_UNIT,
    AKAI_ENV2_OCT_PER_UNIT, AKAI_ENV2_FULL_LEVEL, AKAI_FILTER_OPEN_HZ, AKAI_FILTER_FLOOR_HZ,
    key_track_to_filter_amount, AKAI_KEYFOLLOW_NEG_SCALE,
    Envelope)
import math

#: Keygroup byte offsets that had no name here until 2026-08-23.
AKAI_FILQ_OFFSET = 149        #: resonance, 0..15 (s3ked §52)
#: `L_PTCH`, "Amount of control of pitch by LFO1", -50..+50. The per-keygroup
#: GATE on the program's LFO1: measured 2026-08-24, LFODEP 99 with L_PTCH 0
#: produces no vibrato at all. So a program-level LFO depth means nothing
#: without this, and the same program can have vibrato on some keygroups and
#: none on others -- which is what Jan heard before anyone read the field.
AKAI_LPTCH_OFFSET = 150
AKAI_LPTCH_MAX = 50
AKAI_KGMUTE_OFFSET = 160      #: keygroup mute group; **255 is off, 0 is a
                              #: real group** (§AKAIMUTEGRP)
AKAI_KGMUTE_OFF = 255

# ── AKAI character encoding ────────────────────────────────────────────────
# Not ASCII: names are a 41-symbol alphabet packed one byte per character.
# docs/AKAI_S3000_FORMAT.md "Character encoding" -- confirmed identical in
# both references.
_AKAI_ALPHABET = ('0123456789'          # 0x00-0x09
                  ' '                   # 0x0A
                  'ABCDEFGHIJKLMNOPQRSTUVWXYZ'   # 0x0B-0x24
                  '#+-.')               # 0x25-0x28

AKAI_NAME_LEN = 12          # S1000/S3000 (the S900 uses 10)
BLOCK_SIZE = 0x2000         # 8192, fixed

#: Block lengths differ by sampler generation: **an S1000 block is 0x96 (150)
#: bytes and the S3000 form is the same layout plus 42 bytes of padding**, so
#: 0xC0.  This holds for the sample header, the program common block and every
#: keygroup alike, and the header-id byte says which one a file uses.
#:
#: Reading an S1000 file with the S3000 lengths shifts every field past the
#: first block: on a real S1000 library disc it made 243 of 335 programs parse
#: as zero keygroups and left 1 292 of 1 369 zones naming samples that do not
#: exist, and it cut 42 bytes off the front of every sample's PCM.
S1000_BLOCK_LEN = 0x96
S3000_BLOCK_LEN = 0xc0

#: Sample data starts at 0xC0, not 0xBE, *for an S3000 sample*.
#: The primary spec's layout line says `00be- sample data`, but two things
#: contradict it and both were checked: the same document annotates its own
#: last header field `8d-bd  ?? (from 0xc0??)` -- the author was unsure -- and
#: akaiutil's `sizeof(struct akai_sample3000_s)` is 192. 192 is also what the
#: rest of the format uses: the program common block and every keygroup are
#: 0xC0. Taking 0xBE offsets all PCM by one frame and turns a real sample into
#: noise, and akaiutil rejects such a file outright with "invalid sample size"
#: -- which is how this was caught.
SAMPLE_HEADER_LEN = S3000_BLOCK_LEN
PROGRAM_COMMON_LEN = S3000_BLOCK_LEN    # keygroup 1 starts here
KEYGROUP_LEN = S3000_BLOCK_LEN


def _block_len(s3000: bool) -> int:
    """Length of a header / common / keygroup block for a generation."""
    return S3000_BLOCK_LEN if s3000 else S1000_BLOCK_LEN

#: Velocity-zone offsets within a keygroup: a uniform 24-byte stride from
#: 0x22 (12-byte sample name, then 12 bytes of zone parameters).
#:
#: The primary spec gives zone 3 at **0x53**, one byte later, and that is
#: wrong. akaiutil's struct lays the four out uniformly, and real programs
#: settle it: across one library disc's S3000 programs, zone 3 read at 0x52
#: resolves to a sample in its own volume 317 times and fails 3, while at 0x53
#: it resolves 0 times and fails 8 462 -- reading a leading 0x00 that decodes
#: as the digit '0'. Getting this wrong reads a zone's name one byte into its
#: own field, which still decodes to *something* and would not look broken.
_ZONE_OFFSETS = (0x22, 0x3a, 0x52, 0x6a)

#: Byte 0x00 of every block is a **block id saying what kind of block it is**,
#: not which sampler generation wrote it.  Both references describe it as a
#: "header id -- 1 = S1000, 3 = S3000", and that reading is wrong: on real
#: media every program common block is 1 and every sample header is 3,
#: *regardless of generation* -- an S1000 disc's 335 programs and an S3000
#: disc's 2 117 programs all carry 1, and both discs' samples all carry 3.
#: akaiutil's own constants agree (`SAMPLE3000_BLOCKID == SAMPLE1000_BLOCKID`).
#:
#: **The generation is not recorded in the file at all.**  It comes from the
#: directory entry's file-type byte, i.e. from the `.P1` / `.P3` extension.
#: Where that is not available, `_infer_s3000_*` falls back to block arithmetic.
_BLOCK_ID_PROGRAM = 1
_BLOCK_ID_KEYGROUP = 2
_BLOCK_ID_SAMPLE = 3

# Kept as aliases: the old names said "header id" and were used as if they
# encoded the generation.  Nothing should read them that way again.
_HDR_ID_S1000 = _BLOCK_ID_PROGRAM
_HDR_ID_S3000 = _BLOCK_ID_SAMPLE


def _infer_s3000_sample(data: bytes) -> bool:
    """Guess a sample's generation from where its PCM has to start.

    `data length` at 0x1a is in samples and sits inside the first 0x96, so it
    is readable either way; whichever block length makes the file add up wins.
    """
    want = _u32(data, 0x1a) * 2
    if want and len(data) - want in (S1000_BLOCK_LEN, S3000_BLOCK_LEN):
        return len(data) - want == S3000_BLOCK_LEN
    return True                             # nothing to go on: assume S3000


def _infer_s3000_program(data: bytes) -> bool:
    """Guess a program's generation from its length.

    A program is a common block plus N keygroups of the same size, so the file
    length is a multiple of the block length. Only lengths that are a multiple
    of both (every 4 800 bytes) are ambiguous, and those prefer S3000.
    """
    fits3000 = len(data) % S3000_BLOCK_LEN == 0
    fits1000 = len(data) % S1000_BLOCK_LEN == 0
    if fits3000 and not fits1000:
        return True
    if fits1000 and not fits3000:
        return False
    return True


def akai_to_str(raw: bytes) -> str:
    """Decode an AKAI-encoded name. Unknown bytes become '.', as both
    references do, rather than raising -- a stray byte in a name must not
    stop a bank from converting."""
    out = []
    for b in raw:
        out.append(_AKAI_ALPHABET[b] if b < len(_AKAI_ALPHABET) else '.')
    return ''.join(out).rstrip()


def str_to_akai(name: str, length: int = AKAI_NAME_LEN) -> bytes:
    """Encode to the AKAI alphabet, space-padded to `length`."""
    rev = {c: i for i, c in enumerate(_AKAI_ALPHABET)}
    out = bytearray()
    for ch in name.upper()[:length]:
        out.append(rev.get(ch, rev[' ']))
    out.extend([rev[' ']] * (length - len(out)))
    return bytes(out)


def _s16(data: bytes, off: int) -> int:
    """Signed 16-bit little-endian. Tune offsets are signed; reading them
    unsigned turns a -1 semitone into +65535."""
    return struct.unpack_from('<h', data, off)[0]


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from('<H', data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from('<I', data, off)[0]


def _s8(v: int) -> int:
    return v - 256 if v > 127 else v


#: Playback rates the machine actually has. Byte 0x01 selects between them.
_AKAI_PLAYBACK_RATES = (22050, 44100)


def _playback_rate(data: bytes, s3000: bool) -> int:
    """The rate the sample will SOUND at, which is not always what it declares.

    **HARDWARE-CONFIRMED 2026-08-20 (s3ked §143), on the LOAD PATH
    specifically.** Four programs were loaded from a disc with byte `0x01` and
    `SSRATE` deliberately contradictory, and both conflicts resolved to the
    index byte, in opposite directions:

        0x01=1  SSRATE 22050  ->  300.0 Hz    the index, not SSRATE
        0x01=0  SSRATE 44100  ->  150.0 Hz    the index, not SSRATE

    with controls at 300.0 and 150.0 Hz passing first under a stop rule. **The
    loader reads byte 0x01 and ignores SSRATE**, which is descriptive only.

    It matters because the two disagree often: over 19 340 factory headers,
    4242 (22.0%) carry an SSRATE contradicting the index, including 1290
    declaring 48000 -- a rate the machine cannot produce at all. Reading SSRATE
    gave every one of those a rate the sampler never plays.

    **S1000 media is deliberately excluded, and the reason is measurable.**
    Byte 0x01 reads 1 in **35 990 of 35 990** `.S1` headers here, and varies
    only on `.S3` (961 of 18 293 at 0). A field constant across 35 990
    specimens bounds the CORPUS, not the machine: ConvertWithMoss saw the byte
    varying on machine-recorded S1000 material, where a 22050 recording leaves
    SSRATE at zero and is marked by the index alone. Ours are library CD-ROMs
    mastered at 44100, exactly where an invariant 1 is expected.

    So on `.S1` the index is a FALLBACK for an absent SSRATE -- CWM's case,
    where it is the only information present -- and not a preference.
    Preferring it outright would move 3242 of 35 990 `.S1` read rates, 1503 of
    them from a declared 22050 up to 44100, on an inference from a machine of
    the other generation. §143 was measured on an S3000XL, and s3ked's §139
    established that this family shares a protocol without sharing its
    hardware. **Blocked on:** the same disc test carrying `.S1` files.
    """
    declared = _u16(data, 0x8a)
    index = _AKAI_PLAYBACK_RATES[1 if (data[0x01] & 1) else 0]
    if s3000:
        return index
    return declared or index


# ── sample ─────────────────────────────────────────────────────────────────


def _filter_env_of(env2, depth, filfrq=99, s3000=True):
    """Keygroup envelope-2 bytes -> (Envelope, amount), or (None, 0).

    **Depth 0 means NO filter envelope**, not a full-depth one. §144 measured
    AKAI's own import defaulting keygroup 151/152/153 to zero, and our writer
    leaves 153 alone unless the source had an envelope -- so an unrouted
    envelope modulates nothing and reading one out would invent a modulation
    the program does not make. That also makes this correct for S1000
    programs, whose 150-byte keygroup cannot carry 153 at all.

    Exact inverse of `akai_filter_env_bytes`, through the SAME shared laws:
    the published times are full 0..99 traverses, so each stage is scaled by
    the distance it really covers.
    """
    if not env2 or not depth:
        return None, 0.0
    a, d, sus, r = env2
    sustain = max(0.0, min(1.0, sus / 99.0))
    return (Envelope(
        attack=akai_env2_stage_seconds(a, 99, AKAI_ENV2_ATTACK),
        decay=akai_env2_stage_seconds(d, max(1, 99 - sus), AKAI_ENV2_DECAY),
        sustain=sustain,
        release=akai_env2_stage_seconds(r, max(1, sus), AKAI_ENV2_RELEASE)),
        _env2_amount(depth, sus, filfrq, s3000))


def _env2_amount(depth, sustn2, filfrq, s3000):
    """AKAI ENV2 depth -> the model's filter-envelope depth in CENTS.

    `sustn2` is no longer used for the LEVEL -- see below -- and is kept in the
    signature because the caller has it and a future ceiling rule may need it.

    **CONVERTS A CORNER POSITION, NOT A DEPTH** (§AKAIENV2DEPTH). The old form
    was `depth / AKAI_ENV2_DEPTH_MAX`, where that constant was derived by
    EQUATING two laws measured on two different machines and never checked end
    to end. It over-delivered by 2.5x to 6.7x -- enough to sweep the corner
    past 19 kHz, out of the audio band -- which is why four filter tests in a
    row measured about 1 dB with nothing left to open.

    Both halves are now measured on the machines that produce them, so the
    conversion goes through the one thing both machines agree on: WHERE THE
    CORNER ENDS UP.

        base_hz    the keygroup's own resting corner
        target_hz  where the AKAI's envelope actually takes it, ceiling included
        amount     the fraction of a full sweep from base to target

    **The AKAI's ceiling is absolute in Hz (7.86 kHz), so the reachable octave
    span depends entirely on the base** -- 5.87 octaves from FILFRQ 40, 1.08
    from 85. That is why no single `DEPTH_MAX` could ever have been right, and
    why the target corner is clamped rather than the depth.
    """
    if not depth:
        return 0.0        # cents
    base_hz = akai_filfrq_to_hz(filfrq)
    if base_hz is None:
        # Saturated FILFRQ: the machine does not distinguish these from wide
        # open. Use the highest corner it DOES distinguish as the base rather
        # than returning zero -- a NEGATIVE depth sweeps downward from here and
        # is very audible, and returning zero would silently drop it.
        base_hz = AKAI_FILTER_OPEN_HZ
    # AT FULL ENVELOPE LEVEL, NOT AT SUSTAIN -- fixed 2026-08-25 (§AKAIENV2PEAK).
    #
    # `filter_env_cents` is defined as the depth at FULL level, and this used
    # to pass `sustn2` here, so it reported the corner the envelope SETTLES at
    # and called it the peak. On the program that exposed it the AKAI sweeps to
    # 7858 Hz instantly and decays to 189 Hz, and we were writing 189 Hz as the
    # peak with no sweep at all -- which removes the attack transient entirely.
    # Jan heard it as "the click is gone" on a converted electric piano; no
    # corpus round trip could see it, because the reader and the writer made
    # the same substitution and agreed with each other perfectly.
    #
    # The sustain is NOT lost by this and must not be applied twice: the
    # Envelope returned alongside carries sustain = sustn2/99, so a writer
    # reproduces the settled corner as sustain x full depth. For this program
    # that is 0.15 x 6.46 = 0.97 octaves against the machine's own 0.98.
    _lvl = AKAI_ENV2_FULL_LEVEL
    if depth < 0:
        # Downward sweep. The 7.86 kHz ceiling is an upper bound and does not
        # apply; the floor is the machine's own lowest corner.
        octaves = -min(AKAI_ENV2_OCT_PER_UNIT * _lvl * abs(depth),
                       math.log2(max(base_hz, 1.0) / AKAI_FILTER_FLOOR_HZ))
    else:
        target_hz = akai_env2_target_hz(base_hz, _lvl, depth)
        octaves = math.log2(max(target_hz, 1e-6) / base_hz)
    # THE MODEL CARRIES CENTS SINCE 2026-08-25, so the octaves this function
    # already computed ARE the answer -- one multiplication, and no E-MU
    # number anywhere in an AKAI read.
    #
    # It used to convert those octaves into "a fraction of one E4XT cord's
    # full sweep", measured in E4XT cutoff BYTES because that is the unit the
    # cord is linear in. Correct arithmetic for a wrong destination: it made
    # every AKAI filter-envelope depth depend on the E4XT's byte curve, and it
    # is half of what §FENVFULLSCALE was about -- the reader normalised on one
    # full scale and the KRZ and AKAI writers multiplied by another.
    return octaves * 1200.0


def _cutoff_of(filfrq: int, s3000: bool) -> float:
    """FILFRQ -> the model's 0..1 cutoff position.

    **Until 2026-08-20 this did not exist**: the keygroup's `filter_freq` was
    read into a dict and never consumed, so `filter_cutoff` stayed at its
    default and **all 16 020 AKAI-sourced voices across three factory discs
    converted fully open** (§AKAIFILTREAD). The mirror of the attack bug fixed
    the same day, where the writer emitted a constant instead of dropping a
    value -- and silent for the same reason: an open filter reads as a bright
    sample, not as missing information.

    Uses `AKAI_FILTER_LAW`, shared with the writer so the two are exact
    inverses by construction rather than by agreement.

    **S1000 sources use the same law, since 2026-08-21, and the reason is
    measured rather than assumed.** This returned the default for `.P1` until
    then, on the grounds that both laws are S3000XL measurements. s3ked §144
    settled it: the S3000XL loads `.P1` natively and **its import is a
    pass-through** -- a FILFRQ ladder of 14 values came back exact and
    monotonic, and three probe programs setting all twenty semantic fields to
    20, 50 and 80 returned every one unchanged. So AKAI's own importer treats
    an S1000 FILFRQ as an S3000 FILFRQ, and that is the manufacturer's answer
    to the question this branch was waiting on.

    It reached 14 661 keygroups: 19.3% of the 76 086 `.P1` keygroups in the
    corpus carry a real setting, and every one of them was converting fully
    open.

    **What this does NOT establish, and must be said whenever it is quoted:
    identity is not equivalence.** The importer not altering the number does
    not make the number sound the same -- §139 measured 12 dB/octave on this
    machine against the S1000's specified 18, so FILFRQ 60 can import untouched
    and still produce a different corner on the two machines. What we now
    reproduce for a `.P1` is **what an S3000XL makes of that file**, which is
    what anyone playing these discs on S3000-family hardware hears. What an
    S1000 made of it is still open and still needs an S1000.

    The `s3000` argument is kept although the filter no longer branches on it:
    the question was live for a day and a signature that never had the
    information would read as though it had never been asked.

    **Between the top of the fit (84) and wide open (99) the POSITION is
    interpolated, not clamped, and that band is where the corpus actually
    lives.** Measured over four S3000 factory discs, 1555 keygroups:

        FILFRQ  0..39      0
        FILFRQ 40..84      2      <- the entire fitted range
        FILFRQ 85..98    685      <- mostly 90 and 92
        FILFRQ 99        868

    Clamping to the fitted top put 685 voices on one value, all reading darker
    than they sound. Interpolating between **two measured endpoints** -- the
    fit at 84 and the hardware-confirmed wide open at 99 -- is not the
    unsampled extrapolation this project has been burned by, because both ends
    are known; only the shape between them is assumed, and it is assumed to be
    the straight line in POSITION that the rest of the scale already is.

    Worth telling s3ked: their sweep covered 40..84 and the factory data is
    almost entirely 85..99, so a sweep of the top decade would replace this
    interpolation with measurement and would move 44% of real voices.
    """
    hz = akai_filfrq_to_hz(filfrq)
    if hz is None:
        # Saturated: the machine does not distinguish these from wide open, so
        # the honest model value is WIDE OPEN and not the highest measured
        # corner.
        #
        # Returning `AKAI_FILTER_OPEN_HZ` here collided with FILFRQ 95, whose
        # measured corner IS that frequency -- so 95 and 96..99 arrived as the
        # same number and the writer had to pick one, sending 95 back as 99 on
        # 2.1% of zones. They are different settings and the model can hold
        # that.
        #
        # `_env2_amount` still uses the highest measured corner for its own
        # saturated case, and that is a different decision on purpose: a sweep
        # needs a real corner to start from, where a cutoff needs to say
        # "open".
        return E4B_CUTOFF_MAX_HZ
    # THE MODEL CARRIES Hz SINCE 2026-08-25, and this is the call site the
    # change was made for: converting to a position here put every corner
    # below 57 Hz -- 29.4% of the corpus -- onto one byte on the way back.
    return hz



def parse_sample_bytes(data: bytes, fallback_name: str = '',
                       s3000: Optional[bool] = None) -> Optional[SampleData]:
    """One AKAI sample file (header + PCM) -> SampleData.

    `s3000` picks the block length; pass it from the file's type byte or
    extension where that is known, since the file itself does not record the
    generation. None infers it from the length.
    """
    if not data or data[0x00] != _BLOCK_ID_SAMPLE:
        return None
    if s3000 is None:
        s3000 = _infer_s3000_sample(data)
    header_len = _block_len(s3000)
    if len(data) < header_len:
        return None

    name = akai_to_str(data[0x03:0x03 + AKAI_NAME_LEN]) or fallback_name
    root = data[0x02]
    play_type = data[0x13]
    n_samples = _u32(data, 0x1a)
    rate = _playback_rate(data, s3000)

    # pitch offset: byte 0x14 is the /256 part, 0x15 the whole -- i.e. a
    # 16-bit fixed-point cents value, low byte first like every other number
    # in the format.
    fine = _s16(data, 0x14) // 256

    pcm = data[header_len:]
    # `data length` is in SAMPLES; trust it over the file length, which may
    # be padded out to a block boundary.
    want = n_samples * 2
    if 0 < want <= len(pcm):
        pcm = pcm[:want]
    if len(pcm) % 2:
        pcm = pcm[:-1]

    # S1000/S3000 PCM is signed, full stop -- see the format doc. There used
    # to be a continuity check here that flipped the sign when it thought the
    # data looked unsigned. It was wrong on real files: over 21 503 samples
    # from the disc corpus it fired on 36, and they are SQUARE.S3 and PULSE.S3
    # -- oscillator waveforms whose edges are *meant* to be discontinuous,
    # which is exactly what a continuity test reads as "unsigned". The rewrite
    # turned a leading 0 into -32768, i.e. the full-scale noise the check was
    # supposed to prevent. akaiutil converts sign only for S900 *compressed*
    # data, which this reader does not handle at all.

    sd = SampleData(name=name, data=pcm, sample_rate=rate,
                    bit_depth=16, channels=1)
    sd.root_note = root if 0 < root < 128 else 60
    sd.fine_tune = fine

    # playback type 2 is the only one that means "no loop"; the others all
    # sustain in some form. Loop 1 is the one that matters -- the remaining
    # seven are alternates the hardware can switch between.
    loop_at = _u32(data, 0x26)
    loop_len = _u32(data, 0x2c)
    loop_times = _u16(data, 0x30)
    # LOOPAT1 IS THE LOOP **END**, and the length runs BACKWARDS from it, so
    # the loop is [loop_at - loop_len, loop_at]. This read it as the start
    # until 2026-08-18 -- the field's opposite meaning, mirroring the same
    # error in the writer.
    #
    # Confirmed four ways: the S3000XL manual ("when playback reaches this
    # point, it will go back to the point determined by the field described
    # below"); the corpus, where LOOPAT sits within 1% of SLNGTH in 82.9% of
    # 16493 factory loops and within 10% in 92.5%, i.e. at the sample's END;
    # and ConvertWithMoss, which names it `getEndMarker()` with the docstring
    # "the end of the looped region (not the start!)" and computes
    # `setStart(marker - coarseLength); setEnd(marker)`.
    #
    # Under the old reading, 89% of factory loops appeared to run off the end
    # of their own sample -- which was visible in the corpus the whole time and
    # was never checked, because nothing depended on it being sensible.
    if play_type != 2 and loop_len > 0 and loop_times != 0:
        n_frames = len(pcm) // 2
        end = min(loop_at, max(0, n_frames - 1))
        start = max(0, end - loop_len)
        if end > start:
            sd.loop_type = LoopType.FORWARD
            sd.loop_start = start
            sd.loop_end = end
    return sd


# ── program ────────────────────────────────────────────────────────────────

def _zone_of(kg: bytes, base: int) -> Optional[dict]:
    """One velocity zone of a keygroup, or None when unused."""
    if base + 0x14 > len(kg):
        return None
    raw = kg[base:base + AKAI_NAME_LEN]
    # An unused zone is blank -- but "blank" has two spellings, and one of
    # them is a trap: 0x00 decodes to the DIGIT '0', not to a space, so an
    # all-zero (never-populated) zone reads as the perfectly valid name
    # "000000000000" and would be taken for a real sample. Test the raw
    # bytes, not the decoded string.
    if not raw or all(b == 0x00 for b in raw) or all(b == 0x0A for b in raw):
        return None
    name = akai_to_str(raw)
    if not name:
        return None
    lo_vel, hi_vel = kg[base + 0x0c], kg[base + 0x0d]
    # A disabled zone is marked by an UNREACHABLE VELOCITY RANGE, not by a
    # blank name: real programs leave a leftover name in the slot -- a ROM
    # waveform (SAWTOOTH, PULSE, SQUARE) on some libraries, the library's own
    # branding on others -- and rely on the range alone.
    #
    # Two spellings occur, and both mean the same thing. One library inverts
    # the range (lo 1, hi 0); another sets it to (0, 0). MIDI velocity 0 is
    # note-off, so **any zone whose hi_vel is 0 can never be selected**,
    # inverted or not. Measured over 54 488 named zones in the disc corpus:
    #
    #     hi_vel == 0 :  10 825 zones,  4.43% name something on the disc
    #     hi_vel >  0 :  43 663 zones, 97.13% do
    #
    # NOT RE-DERIVABLE: the discs behind these percentages were read once
    # and are gone (searched 2026-08-13). They are a recorded measurement
    # rather than something a future disagreement can be checked against.
    # The RULE does not depend on them -- velocity 0 is note-off on any
    # conforming machine, and s3ked measured an inverted range dead on an
    # S3000XL. Only the spelling distribution and these figures need a
    # corpus.
    #
    # Trusting the name alone invents up to three phantom zones per keygroup:
    # 65% of one disc's zones, 67% of another's.
    if hi_vel == 0 or lo_vel > hi_vel:
        return None
    return dict(
        sample_name=name,
        lo_vel=lo_vel,
        hi_vel=hi_vel,
        tune=_s16(kg, base + 0x0e),
        loudness=_s8(kg[base + 0x10]),
        pan=_s8(kg[base + 0x12]),
    )


def parse_program_bytes(data: bytes, fallback_name: str = '',
                        s3000: Optional[bool] = None) -> Optional[dict]:
    """One AKAI program file -> a plain dict of what it declares.

    Kept separate from Bank building so the disk reader can inspect a
    program without resolving its samples.
    """
    if not data or data[0x00] not in (_BLOCK_ID_PROGRAM, _BLOCK_ID_SAMPLE):
        # _BLOCK_ID_SAMPLE is tolerated because mpc2emu itself wrote 3 here
        # before the block id was understood; real programs carry 1.
        return None
    if s3000 is None:
        s3000 = _infer_s3000_program(data)
    # An S1000 program's common block and keygroups are 0x96, not 0xC0.
    block = _block_len(s3000)
    if len(data) < block:
        return None

    n_kg = data[0x2a]
    # A corrupt or misidentified file can claim 99 keygroups it does not
    # have; believe the file length over the header.
    available = (len(data) - block) // block
    if n_kg < 1 or n_kg > available:
        n_kg = available

    keygroups = []
    for i in range(n_kg):
        off = block + i * block
        kg = data[off:off + block]
        if len(kg) < block:
            break
        zones = [z for z in (_zone_of(kg, b) for b in _ZONE_OFFSETS) if z]
        if not zones:
            continue
        keygroups.append(dict(
            lo_key=kg[0x03], hi_key=kg[0x04],
            tune=_s16(kg, 0x05),
            filter_freq=kg[0x07],
            # K_FREQ, "key follow of filter frequency", SIGNED semitones.
            # Never read until 2026-08-24 -- found by diffing raw keygroup
            # blocks when Jan challenged a claim about three keygroups' filter
            # settings, and confirmed on an S3000XL the same evening.
            #
            #   octaves of cutoff per octave of key = K_FREQ / 12
            #   pivot: note 64 (the machine's convention, shared with V_LOUD
            #   and V_ATT1 -- NOT middle C and NOT the sample root)
            #
            # SIGNED, and our documentation said 0..12 unsigned. That was a
            # DISPLAY range transcribed as a value range, the same error this
            # project already found on KGTUNO. Measured: raw 251 gives -0.435
            # oct/oct against -5/12 = -0.417 predicted, so the corner moves
            # DOWN as the note goes up and negative tracking is real content.
            #
            # It also does not clamp at 12: 18 and 22 give 1.491 and 1.845
            # against 1.500 and 1.833 predicted, straight through with no knee
            # (0.08444 per unit against 1/12 = 0.08333, 1.3%).
            filter_keyfollow=_s8(kg[0x08]),
            amp_attack=kg[0x0c], amp_decay=kg[0x0d],
            amp_sustain=kg[0x0e], amp_release=kg[0x0f],
            env2=(kg[0x14], kg[0x15], kg[0x16], kg[0x17]),
            env2_depth=(_s8(kg[AKAI_ENV2_DEPTH_OFFSET])
                        if len(kg) > AKAI_ENV2_DEPTH_OFFSET else 0),
            filter_q=(kg[AKAI_FILQ_OFFSET]
                      if len(kg) > AKAI_FILQ_OFFSET else 0),
            lfo_to_pitch=(_s8(kg[AKAI_LPTCH_OFFSET])
                          if len(kg) > AKAI_LPTCH_OFFSET else 0),
            # 255 is off. An S1000 keygroup is 150 bytes and has no offset
            # 160 at all, so a short block reports OFF rather than group 0 --
            # reporting 0 would invent an active mute group for every S1000
            # program on earth.
            mute_group=(kg[AKAI_KGMUTE_OFFSET]
                        if len(kg) > AKAI_KGMUTE_OFFSET else AKAI_KGMUTE_OFF),
            zones=zones,
        ))

    return dict(
        name=akai_to_str(data[0x03:0x03 + AKAI_NAME_LEN]) or fallback_name,
        is_s3000=s3000,
        midi_program=data[0x0f],
        polyphony=data[0x11],
        lo_key=data[0x13], hi_key=data[0x14],
        octave_shift=_s8(data[0x15]),
        loudness=data[0x19],
        pan=_s8(data[0x18]),
        tune=_s16(data, 0x41),
        # LFO1, read by nobody until 2026-08-24 (§AKAILFO). The AKAI LFO is
        # per PROGRAM, not per keygroup, so it lands on every voice.
        lfo_rate=data[0x21], lfo_depth=data[0x22], lfo_delay=data[0x23],
        keygroups=keygroups,
    )


#: Extensions a keygroup's sample may legitimately have on disk. `.wav` is
#: here because extraction tools emit it; the AKAI ones come from the type
#: byte (see `writers/akai_s3000_image.ftype_to_ext`).
_SAMPLE_EXTS = {'.s3', '.s1', '.a3s', '.s3s', '.wav'}


def _find_sample(name: str, search_dir: Path) -> Optional[Path]:
    """Locate the sample a keygroup names.

    AKAI names are space-padded and case-insensitive in practice, and the
    on-disk extension varies by extraction tool, so the fallback matches on
    the stem. **It must still check the type**: a program file opens with a
    block id the sample parser used to accept, so a program whose own name
    matches a wanted sample would be loaded as PCM and converted to a bank of
    noise, silently. That is real — one program in 5 246 on the disc corpus.
    """
    want = name.strip().upper()
    for ext in ('.S3', '.s3', '.S1', '.s1', '.a3s', '.A3S', '.s3s', '.S3S',
                '.wav', '.WAV'):
        cand = search_dir / f"{name.strip()}{ext}"
        if cand.is_file():
            return cand
    for f in search_dir.iterdir():
        if (f.is_file() and f.stem.strip().upper() == want
                and f.suffix.lower() in _SAMPLE_EXTS):
            return f
    return None


def build_preset_from_program(prog: dict, sample_bytes, bank: Bank,
                              fallback_name: str = '',
                              cache: Optional[dict] = None,
                              taken: Optional[set] = None,
                              quiet: bool = False,
                              missing_out: Optional[set] = None) -> Optional[Preset]:
    """Turn a parsed program dict into a Preset, appending its samples to `bank`.

    `sample_bytes(name)` returns the raw sample file for a keygroup's sample
    name, or None.  It is a callback rather than a directory so the same code
    reads loose files and files lifted out of a disk image.

    `cache` and `taken` may be shared across several programs on one volume, so
    that two programs naming the same sample load it once and reference the
    same Bank sample rather than duplicating it.
    """
    from parsers.xpm_parser import _safe_name, _unique_sample_name
    if cache is None:
        cache = {}
    if taken is None:
        taken = set()
    preset = Preset(name=_safe_name(prog['name'] or fallback_name),
                    program_number=0)
    missing: set = set()

    _kg_of_voice = []
    for kg in prog['keygroups']:
        voice = VoiceLayer()
        # The AKAI filter is 12 dB/octave -- the service manual's own
        # specification and s3ked's §139 measurement. Left unset until
        # 2026-08-23, and the model default of 0 is "Off", which the E4B
        # writer maps to vpar[58]=0x00 -- the FOUR-pole. Every AKAI-sourced
        # conversion we ever made had a filter twice as steep as its source.
        voice.filter_type = 2          # XPM "Low 2": 2-pole, 12 dB/oct
        # RESONANCE. FILQ was read by nobody and written by nobody, so every
        # AKAI-sourced filter came out flat. Real programs lean on it hard.
        voice.filter_resonance = akai_filq_to_01(kg.get('filter_q', 0))
        # VIBRATO. Dropped entirely until 2026-08-24: the reader never touched
        # the LFO, so every AKAI-sourced conversion lost it. Per-program on
        # this machine, so every voice gets the same.
        # VIBRATO, GATED PER KEYGROUP. The LFO is per PROGRAM but its route to
        # pitch is per KEYGROUP -- `L_PTCH`, offset 150. MEASURED 2026-08-24:
        # LFODEP 99 with L_PTCH 0 produces no vibrato at all, against a
        # detector floor established in the same run. So both must be
        # non-zero, and one program can have vibrato on some keygroups and
        # none on others.
        #
        # Jan heard exactly that before anyone read the field -- "on the AKAI
        # the LFO only affects the non-metallic sounding KG, on the EMU it
        # sounds like it is affecting all voices" -- while we were applying the
        # program depth to every voice.
        #
        # **THE DEPTH IS SCALED BY L_PTCH AND THE LAW IS NOT KNOWN.**
        # `akai_lfo_depth_to_pitch` rests on s3ked's 19.4932 cents/unit, and
        # their sweep never set L_PTCH -- it sat at whatever the calibration
        # program carried, unrecorded. Since L_PTCH 0 gates the vibrato off
        # entirely, that program cannot have had 0, so 19.4932 is the law at
        # some unknown non-zero routing rather than a full-scale reference.
        # A linear ratio is the obvious guess and is NOT applied: nobody has
        # shown the two compose multiplicatively (§AKAILPTCH).
        if prog.get('lfo_depth') and kg.get('lfo_to_pitch'):
            voice.lfo1_rate = akai_lfo_rate_hz(prog.get('lfo_rate', 0))
            voice.lfo1_to_pitch = akai_lfo_depth_to_pitch(
                prog['lfo_depth'], kg['lfo_to_pitch'])
            voice.lfo1_delay = akai_lfo_delay_seconds(prog.get('lfo_delay', 0))
        voice.filter_cutoff = _cutoff_of(kg['filter_freq'], prog['is_s3000'])
        # KEY FOLLOW OF FILTER FREQUENCY -- carried since 2026-08-24, dropped
        # silently before that on every AKAI-sourced conversion in every
        # format. See `filter_keyfollow` in parse_program_bytes for the law and
        # how the field was found.
        #
        # Converted through the SHARED helper rather than by dividing here: the
        # E4B cord's own full-scale lives in `KEY_FILTER_OCT_PER_OCT`, and a
        # second copy of that ratio is the exact shape of defect that accounted
        # for most of this week's work.
        #
        # ONE THING IS ASSUMED AND SHOULD BE MEASURED: the AKAI pivots this at
        # NOTE 64. The E4XT's Key source pivots somewhere too and nobody has
        # checked it is the same place. A pivot mismatch tilts the tracking
        # about the wrong centre -- audible as "the filter is wrong at one end
        # of the keyboard" while the ratio itself is right.
        # K_FREQ/12 IS the ratio: octaves of cutoff per octave of key. The
        # model carries that directly since 2026-08-24; it used to be converted
        # to an EOS cord fraction here and saturated at 0.713 oct/oct, which
        # threw away every value past K_FREQ 9 -- and real material reaches -30
        # and +40.
        #
        # NEGATIVE K_FREQ SCALED, POSITIVE NOT (§AKAIKEYFOLLOWHW, 2026-08-27):
        # K_FREQ/12 measured ~0.6x too strong on the negative side -- see
        # AKAI_KEYFOLLOW_NEG_SCALE's own comment for the measurement. The
        # positive side is a real, unresolved nonlinearity, not left alone out
        # of caution; applying an unmeasured correction there would be the
        # same mistake this fixes.
        _kfreq12 = kg.get('filter_keyfollow', 0) / 12.0
        voice.filter_keytrack = (_kfreq12 * AKAI_KEYFOLLOW_NEG_SCALE
                                 if _kfreq12 < 0 else _kfreq12)
        # AMPLITUDE ENVELOPE. Never assigned until 2026-08-23, so every
        # AKAI-sourced voice carried VoiceLayer's default and the two distinct
        # envelopes of a layered program came out identical -- eosed read all
        # six voices of one off the E4XT and found them byte-identical where
        # the source says they must differ (§AKAIAMPENV). The inverse lives
        # beside the forward law in the writer so there is one home for it;
        # the import is function-local because that module imports this one.
        from writers.akai_s3000_writer import akai_env_from_bytes
        voice.amp_env = akai_env_from_bytes(
            kg['amp_attack'], kg['amp_decay'], kg['amp_sustain'],
            kg['amp_release'])
        _fe, _amt = _filter_env_of(kg.get('env2'), kg.get('env2_depth', 0),
                                   kg.get('filter_freq', 99), prog['is_s3000'])
        if _fe is not None:
            voice.filter_env = _fe
            voice.filter_env_cents = _amt
        for z in kg['zones']:
            src = z['sample_name']
            if src not in cache:
                raw = sample_bytes(src)
                if raw is None:
                    if src not in missing:
                        if not quiet:
                            print(f"    [WARN] sample not found: {src!r}")
                            # THE HINT IS HERE BECAUSE THE WARNING CANNOT
                            # DISTINGUISH THE TWO CAUSES (§NAMEBITFLIP).
                            # A zone names its sample, so a name that is wrong
                            # in the SOURCE and a name that was corrupted in
                            # the copy we read produce byte-identical
                            # symptoms: no bad audio, no failed checksum,
                            # nothing to diff -- just a name that stops
                            # matching. s3ked saw a real one-bit flip in
                            # sampler RAM on 2026-08-24, H for I, that did not
                            # reproduce.
                            #
                            # Comparing against the medium is the only way to
                            # tell, and nobody takes that step unless they
                            # already suspect it. So the suspicion is printed
                            # once per program rather than left in a document.
                            if not missing:
                                print("           (if this program looks "
                                      "otherwise healthy, compare the name "
                                      "against the source medium -- a "
                                      "single-bit corruption reads exactly "
                                      "like a missing sample)")
                        missing.add(src)
                    # `quiet` exists so a 180-volume disc does not print a
                    # warning per program; it must not mean the loss goes
                    # unreported. Callers pass a set and summarise at the end.
                    if missing_out is not None:
                        missing_out.add(src)
                    cache[src] = None
                else:
                    sd = parse_sample_bytes(raw, fallback_name=src)
                    if sd is None:
                        if not quiet:
                            print(f"    [WARN] unreadable sample: {src!r}")
                        cache[src] = None
                    else:
                        sd.name = _unique_sample_name(_safe_name(sd.name or src), taken)
                        taken.add(sd.name)
                        cache[src] = sd
                        bank.samples.append(sd)
                        if not quiet:
                            print(f"    Loaded sample: {sd.name} "
                                  f"({sd.sample_rate}Hz, {len(sd.data)//2} frames)")
            sd = cache[src]
            if sd is None:
                continue
            _cents = int(round((kg['tune'] + z['tune']) * 100.0
                               / AKAI_TUNE_UNITS_PER_SEMITONE))
            # Truncate toward zero so `fine` keeps the sign of the whole
            # value: -1250 cents is -12 semitones and -50 cents, not -13 and
            # +50.
            _coarse = int(_cents / 100.0)
            _fine = _cents - _coarse * 100
            voice.zones.append(ZoneMapping(
                sample_name=sd.name,
                lo_key=kg['lo_key'], hi_key=kg['hi_key'],
                lo_vel=z['lo_vel'], hi_vel=z['hi_vel'],
                root_key=sd.root_note,
                # AKAI tune is 1/256 semitone. This divided by 16 until
                # 2026-08-23 -- 16% of the true value -- AND put the whole
                # result in fine_tune, which is a +/-100 cent field, so an
                # octave layer saturated at +98 cents (§AKAITUNEREAD).
                coarse_tune=_coarse, fine_tune=_fine,
                # VLOUD1 through the measured slope. Was a hardcoded 1.0,
                # which dropped the source's level offset AND meant +1 dB
                # rather than unity, since the field is dB (§AKAIZONELOUD).
                volume=z.get('loudness', 0) * AKAI_VLOUD_DB_PER_UNIT,
                # AKAI pan is -50..+50 with 0 centred; `ZoneMapping.pan` is
                # -1.0..+1.0 with 0.0 centred. Both ends are hard, so the
                # scale is /50. Measured over 54 654 zones on the disc corpus:
                # min -50, max +50 but for two junk zones, and +/-50 are the
                # two commonest non-centre values (33 337 zones -- the
                # hard-panned halves of stereo pairs).
                pan=min(1.0, max(-1.0, z['pan'] / 50.0)),
            ))
        if voice.zones:
            preset.voices.append(voice)
            _kg_of_voice.append(kg)
    if preset.voices:
        # AFTER the mute-group re-model, deliberately: that rewrites the losing
        # layer's envelope, so two keygroups identical in the source can end up
        # different here, and two that differed can end up the same. Merging
        # first would group on settings that are about to change.
        _apply_mute_groups(preset.voices, _kg_of_voice, prog['name'],
                           quiet=quiet)
        _before = len(preset.voices)
        preset.voices = _merge_identical_voices(preset.voices)
        if len(preset.voices) != _before and not quiet:
            print(f"    [layers] '{prog['name']}': {_before} keygroup(s) -> "
                  f"{len(preset.voices)} voice(s) (identical settings merged "
                  f"into multisampled layers)")
    return preset if preset.voices else None


def _merge_identical_voices(voices):
    """Voices that differ ONLY in which keys they cover become one voice.

    An AKAI keygroup owns a KEY RANGE and carries its own filter and envelopes.
    Our model's voice owns a SIGNAL PATH and carries zones that may span the
    keyboard. One keygroup per voice is therefore the wrong shape whenever
    several keygroups were authored as one multisampled layer -- which is the
    normal way to build an instrument, one sample per octave under a single
    envelope.

    It matters most on the K2000, whose keymap IS the multisample container:
    **measured over 201 real third-party soundsets, 20.7% of 1584 keymaps hold
    more than one sample, up to 64 in one.** Emitting one keymap and one layer
    per keygroup produced six layers for a three-octave electric piano, and a
    K2000 program with more than three SPLIT layers is a drum program that
    sounds only on a drum channel -- so the converted preset was silent on a
    normal channel, correctly, with nothing wrong anywhere in the file. Jan
    diagnosed the shape of it from the format's logic before any of the
    measurements existed.

    **LOSSLESS BY CONSTRUCTION.** Voices merge only when every voice-level
    field is identical -- filter type, cutoff, resonance, both envelopes, the
    envelope depth, the LFO and its routing. Everything that then differs
    between them lives on the ZONE (sample, key range, velocity, tune, volume,
    pan) and is carried unchanged. If two keygroups differ in so much as a
    cutoff byte they stay apart, which is why a preset whose octaves carry
    their own filter settings does not collapse to one layer and should not.

    The signature is built by iterating the model's own voice fields rather
    than by listing them here, so a field added later cannot be silently
    ignored by this function -- the failure mode that produced most of this
    week's defects.
    """
    if len(voices) < 2:
        return voices
    ignore = {'zones'}
    order, groups = [], {}
    for v in voices:
        sig = []
        for name in sorted(vars(v)):
            if name in ignore or name.startswith('_'):
                continue
            val = getattr(v, name)
            sig.append((name, repr(val)))
        key = tuple(sig)
        if key not in groups:
            groups[key] = v
            order.append(key)
        elif groups[key] is not v:
            groups[key].zones.extend(v.zones)
    return [groups[k] for k in order]


def _kg_vel_span(kg):
    """A keygroup's velocity span: the union of its zones'."""
    zs = [z for z in kg['zones'] if z]
    return (min(z['lo_vel'] for z in zs), max(z['hi_vel'] for z in zs))


def _merge_windows(wins):
    """Overlapping key windows -> the smallest set of disjoint ones."""
    if not wins:
        return []
    out = []
    for lo, hi in sorted(wins):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def _split_voice_on_windows(voice, wins, cut_env):
    """One voice -> the pieces inside `wins` (cut) and the pieces outside.

    A mute group bites only on the keys two keygroups SHARE, so a voice whose
    partner overlaps part of its range has to become two voices: the shared
    keys with the cut envelope, the rest with its own. Zones that straddle a
    boundary are split; a zone entirely outside every window is untouched.

    Returns voices in key order, and never returns an empty one.
    """
    import copy as _copy

    def clip(zones, lo, hi):
        out = []
        for z in zones:
            a, b = max(z.lo_key, lo), min(z.hi_key, hi)
            if a > b:
                continue
            nz = _copy.copy(z)
            nz.lo_key, nz.hi_key = a, b
            out.append(nz)
        return out

    lo0 = min(z.lo_key for z in voice.zones)
    hi0 = max(z.hi_key for z in voice.zones)
    pieces = []
    cursor = lo0
    for wlo, whi in wins:
        if cursor < wlo:
            pieces.append((cursor, wlo - 1, False))
        pieces.append((max(wlo, lo0), min(whi, hi0), True))
        cursor = min(whi, hi0) + 1
    if cursor <= hi0:
        pieces.append((cursor, hi0, False))

    out = []
    for a, b, is_cut in pieces:
        zs = clip(voice.zones, a, b)
        if not zs:
            continue
        nv = _copy.copy(voice)
        nv.zones = zs
        if is_cut:
            nv.amp_env = cut_env
        out.append(nv)
    return out or [voice]


def _apply_mute_groups(voices, kgs, prog_name, quiet=False):
    """Re-model the AKAI keygroup mute group, which E4B cannot express.

    **What the field does** (§AKAIMUTEGRP). `KGMUTE` is keygroup offset 160,
    255 is off, and 0 is a real group -- so a zero-filled keygroup header
    inherits an ACTIVE mute group for free. Two keygroups in one group that
    are triggered together cut each other: measured at 19.1 dB on an S3000XL.

    **Why it has to be re-modelled rather than converted.** eosed checked the
    E4XT: `E4_VOICE_ASSIGN_GROUP` exists and our own format doc calls it the
    choke group, but its semantics are note ALLOCATION. Two voices in one Mono
    group under a single note change the mix by 0.13 dB, while the same group
    across two overlapping notes suppresses the first entirely. The authority
    is across notes, not between sibling layers under one note. There is no
    other candidate field.

    **The re-model, and why it is exact rather than approximate.** When two
    keygroups overlap in key AND velocity, one note-on triggers both, so the
    cut happens after a fixed allocator latency and depends on nothing the
    player does. That is an envelope: instant attack, a short decay to zero,
    no sustain, no release. The TIMING is identical rather than approximated,
    because both layers start together. Only the shape of the ending differs
    -- a true cut is a discontinuity and this is a fast fade -- and that costs
    a click's worth of high frequency.

    **Where it cannot be re-modelled**, and is warned about instead: the
    classic cross-note use, a closed hi-hat keygroup cutting an open one on a
    DIFFERENT key. There the cut time depends on when the second note arrives,
    and no envelope can express it. The two cases are distinguishable in the
    file, which is the whole reason this can be a three-way decision rather
    than a blanket warning.

    **Sized before it was written.** Across 9442 S3000 programs on library
    discs, 5964 have two or more keygroups and 311 -- 3.3% of all, 5.2% of
    multi -- have a mute group that would actually bite. 255 is 86% of all
    keygroups, so a warning conditioned on "not 255" would fire on 14% of
    everything and be ignored inside a week.
    """
    groups = {}
    for i, kg in enumerate(kgs):
        g = kg.get('mute_group', 255)
        if g != 255:
            groups.setdefault(g, []).append(i)

    cut, cross, cut_windows = [], [], {}
    for g, members in groups.items():
        if len(members) < 2:
            continue
        for a_i in range(len(members)):
            for b_i in range(a_i + 1, len(members)):
                a, b = members[a_i], members[b_i]
                ka, kb = kgs[a], kgs[b]
                if not (ka['lo_key'] <= kb['hi_key']
                        and kb['lo_key'] <= ka['hi_key']):
                    cross.append((g, a, b))
                    continue
                va, vb = _kg_vel_span(ka), _kg_vel_span(kb)
                if not (va[0] <= vb[1] and vb[0] <= va[1]):
                    continue
                # The later keygroup wins: s3ked's 10 ms trace shows the mix
                # tracking the lower-numbered layer for one window and the
                # higher-numbered one thereafter.
                loser = min(a, b)
                cut.append(loser)
                # ...and it is only cut where the two actually overlap.
                cut_windows.setdefault(loser, []).append(
                    (max(ka['lo_key'], kb['lo_key']),
                     min(ka['hi_key'], kb['hi_key'])))

    # THE CUT APPLIES ONLY WHERE BOTH PARTNERS SOUND -- fixed 2026-08-25
    # (§AKAIMUTESCOPE). This replaced the losing voice's envelope across its
    # WHOLE key range, when a mute group can only bite on the keys the two
    # keygroups share. Measured on the bench: four of the six programs on one
    # volume converted to a click followed by silence, because the voices
    # covering the middle of the keyboard were cut by partners that overlap
    # them only at one end. On one test program, at note 48 --
    #
    #     v1 keys 39-52  cut     v2 keys 45-76  cut     nothing else plays there
    #
    # -- and the AKAI sustains that note for seconds. The rule was right and
    # its scope was not.
    cut_env = Envelope(attack=0.0, decay=AKAI_MUTE_CUT_SECONDS,
                       sustain=0.0, release=0.0)
    out, n_whole, n_split = [], 0, 0
    for i, v in enumerate(voices):
        wins = _merge_windows(cut_windows.get(i, []))
        if not wins:
            out.append(v)
            continue
        lo = min(z.lo_key for z in v.zones)
        hi = max(z.hi_key for z in v.zones)
        if wins[0][0] <= lo and wins[-1][1] >= hi and len(wins) == 1:
            v.amp_env = cut_env
            out.append(v)
            n_whole += 1
        else:
            out.extend(_split_voice_on_windows(v, wins, cut_env))
            n_split += 1
    voices[:] = out
    if not quiet:
        if n_whole or n_split:
            print(f"    [note] {prog_name!r}: {n_whole + n_split} layer(s) are "
                  f"cut by a keygroup mute group; re-modelled as a "
                  f"{AKAI_MUTE_CUT_SECONDS * 1000:.0f} ms decay"
                  + (f" ({n_split} only over the keys the partner shares)"
                     if n_split else ""))
        for g, a, b in cross:
            print(f"    [WARN] {prog_name!r}: keygroups {a} and {b} share mute "
                  f"group {g} but do not overlap in key range -- that is a "
                  f"cross-note choke and no target format here can express it")
    return sorted(set(cut))


#: Extensions that name a program file.
_PROGRAM_EXTS = {'.p3', '.p1', '.a3p', '.s3p'}


def _refuse_wrong_type(p: Path, allowed: set, what: str) -> None:
    """Refuse a file whose extension says it is something else.

    The type of an AKAI file comes from its directory entry, i.e. from the
    extension — never from its contents. An effects file opens with the same
    block id a program does, so a caller that decides by trying parsers in
    turn reads 90 `.X` files as 90 phantom programs with key ranges like
    `200-0`. Refusing here keeps that from reaching the caller at all.

    Corroborated 2026-08-13 (s3ked §88), which characterised the effects
    structure live on an S3000XL: it is a real, populated format -- a header
    record carrying a 12-character name at offset 3, plus lists of 128-byte
    preset entries. So the phantom programs were never corrupt data being
    misread; they were intact data of another type, read by a parser with no
    way to notice. That is the case extension-dispatch exists for, and it is
    also why a content sniff would not have saved us: the bytes are valid,
    they simply describe something else.
    """
    ext = p.suffix.lower()
    if ext and ext not in allowed:
        raise ValueError(
            f"{p.name} is not an AKAI {what}: the extension '{ext}' names a "
            f"different kind of file, and an AKAI file's type comes from its "
            f"extension rather than its contents.")


def parse_akai_program(path: str, sample_dir: Optional[str] = None) -> Bank:
    """Read an AKAI program file (and the samples it names) into a Bank."""
    p = Path(path).resolve()
    _refuse_wrong_type(p, _PROGRAM_EXTS, 'program')
    sdir = Path(sample_dir).resolve() if sample_dir else p.parent

    prog = parse_program_bytes(p.read_bytes(), fallback_name=p.stem)
    if prog is None:
        raise ValueError(
            f"{p.name} is not an AKAI S1000/S3000 program — its header id is "
            f"{p.read_bytes()[:1].hex() or '(empty file)'}, expected 01 or 03.")

    print(f"Parsing AKAI {'S3000' if prog['is_s3000'] else 'S1000'} program: {p}")
    print(f"  '{prog['name']}': {len(prog['keygroups'])} keygroup(s)")

    from parsers.xpm_parser import _safe_name
    bank = Bank(name=_safe_name(p.stem))

    def _lookup(name):
        f = _find_sample(name, sdir)
        return f.read_bytes() if f else None

    preset = build_preset_from_program(prog, _lookup, bank, fallback_name=p.stem)
    if preset is None:
        raise ValueError(
            f"{p.name} declares {len(prog['keygroups'])} keygroup(s) but none "
            f"resolved to a sample — the sample files are probably not beside "
            f"it. Pass the folder holding them.")
    bank.presets.append(preset)
    print(f"  Preset '{preset.name}': {len(preset.voices)} voice(s), "
          f"{len(bank.samples)} sample(s)")
    return bank


def parse_akai_sample(path: str) -> Bank:
    """Read a lone AKAI sample file into a one-zone Bank."""
    p = Path(path).resolve()
    _refuse_wrong_type(p, _SAMPLE_EXTS, 'sample')
    sd = parse_sample_bytes(p.read_bytes(), fallback_name=p.stem)
    if sd is None:
        raise ValueError(f"{p.name} is not an AKAI S1000/S3000 sample.")
    from parsers.xpm_parser import _safe_name
    sd.name = _safe_name(sd.name or p.stem)
    bank = Bank(name=_safe_name(p.stem))
    preset = Preset(name=sd.name, program_number=0)
    v = VoiceLayer()
    v.zones.append(ZoneMapping(sample_name=sd.name, lo_key=0, hi_key=127,
                               lo_vel=0, hi_vel=127, root_key=sd.root_note))
    preset.voices.append(v)
    bank.samples.append(sd)
    bank.presets.append(preset)
    print(f"Parsing AKAI sample: {p}\n  '{sd.name}' "
          f"({sd.sample_rate}Hz, {len(sd.data)//2} frames)")
    return bank
