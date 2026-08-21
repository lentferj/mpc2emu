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
    akai_filfrq_to_hz, hz_to_e4b_cutoff, AKAI_FILTER_LAW, AKAI_FILTER_OPEN)

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
    if filfrq >= AKAI_FILTER_OPEN:
        return 1.0
    _a, _b, _lo, _hi = AKAI_FILTER_LAW
    if filfrq > _hi:
        top = hz_to_e4b_cutoff(akai_filfrq_to_hz(_hi))
        span = AKAI_FILTER_OPEN - _hi
        return top + (1.0 - top) * (filfrq - _hi) / span
    return hz_to_e4b_cutoff(akai_filfrq_to_hz(filfrq))



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
            amp_attack=kg[0x0c], amp_decay=kg[0x0d],
            amp_sustain=kg[0x0e], amp_release=kg[0x0f],
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

    for kg in prog['keygroups']:
        voice = VoiceLayer()
        voice.filter_cutoff = _cutoff_of(kg['filter_freq'], prog['is_s3000'])
        for z in kg['zones']:
            src = z['sample_name']
            if src not in cache:
                raw = sample_bytes(src)
                if raw is None:
                    if src not in missing:
                        if not quiet:
                            print(f"    [WARN] sample not found: {src!r}")
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
            voice.zones.append(ZoneMapping(
                sample_name=sd.name,
                lo_key=kg['lo_key'], hi_key=kg['hi_key'],
                lo_vel=z['lo_vel'], hi_vel=z['hi_vel'],
                root_key=sd.root_note,
                fine_tune=(kg['tune'] + z['tune']) // 16,
                volume=1.0,
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
    return preset if preset.voices else None


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
