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

import struct
from pathlib import Path
from typing import Optional

from models.common import Bank, LoopType, SampleData, safe_filename
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

    _put_s16(h, 0x14, _clamp(getattr(sd, 'fine_tune', 0) or 0, -128, 127) * 256)
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


def _program_common(name: str, n_keygroups: int, lo_key: int, hi_key: int) -> bytearray:
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
    p[0x21] = 50                        # LFO speed
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


def _keygroup(lo_key: int, hi_key: int, zones, index: int = 0) -> bytearray:
    """One 192-byte keygroup with up to four velocity zones."""
    k = bytearray(KEYGROUP_LEN)
    k[0x00] = _BLOCK_ID_KEYGROUP
    # Own RAM address: one block past the previous one.
    struct.pack_into('<H', k, 0x01,
                     _RAM_BASE_PARA + _BLOCK_PARA * (index + 1))
    k[0x03] = _clamp(lo_key, 24, 127)
    k[0x04] = _clamp(hi_key, 24, 127)
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
    # 0 throughout.
    k[0x07] = 99                        # wide open (HW-confirmed)
    k[0x0c] = 0                         # amp attack
    k[0x0d] = 50                        # amp decay
    k[0x0e] = 99                        # amp sustain
    k[0x0f] = 45                        # amp release
    k[0x15] = 50                        # filter decay
    k[0x16] = 99                        # filter sustain
    k[0x17] = 45                        # filter release
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
        _put_s16(k, o + 0x0e, _clamp(z.get('tune', 0), -32768, 32767))
        k[o + 0x10] = _clamp(z.get('loudness', 0), 0, 255) & 0xff
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
    for voice in preset.voices:
        for z in voice.zones:
            key = (z.lo_key, z.hi_key)
            if key not in by_range:
                by_range[key] = []
                order.append(key)
            by_range[key].append(z)

    keygroups = []
    dropped = 0
    for key in order:
        zs = sorted(by_range[key], key=lambda z: z.lo_vel)
        if len(zs) > MAX_ZONES_PER_KEYGROUP:
            dropped += len(zs) - MAX_ZONES_PER_KEYGROUP
            zs = zs[:MAX_ZONES_PER_KEYGROUP]
        keygroups.append((key, [dict(
            sample_name=z.sample_name,
            lo_vel=z.lo_vel, hi_vel=z.hi_vel,
            tune=int(round(_or_default(getattr(z, 'fine_tune', None), 0))) * 16,
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
    out = _program_common(name, len(keygroups), lo, hi)
    for i, ((klo, khi), zs) in enumerate(keygroups):
        out += _keygroup(klo, khi, zs, i)
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
        base = (stem or 'SAMPLE').upper()[:AKAI_NAME_LEN]
        cand = base
        n = 1
        while cand in taken:
            suf = str(n)
            cand = base[:AKAI_NAME_LEN - len(suf)] + suf
            n += 1
        taken.add(cand)
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
