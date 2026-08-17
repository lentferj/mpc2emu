# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# KRZ object layout derived from:
#   KurzFiler (GPL-2.0), Marc Halbrügge, https://kurzfiler.sourceforge.io/
# Container walk promoted from tests/re_banks/krz_reader.py (the project's
# original diagnostic reader), corpus-verified against 577 real .KRZ files
# before this parser was built. Cross-checked against ConvertWithMoss's
# independent Kurzweil reader (git-moss/ConvertWithMoss, format/kurzweil/) —
# see docs/KRZ_FORMAT.md and TODO.md for the two points where this parser
# disagrees with it (CAL keymap slot, entry-index base). No source code
# copied from either project.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
Kurzweil K2000/K2500/K2600 KRZ Bank Parser
--------------------------------------------
Reads .KRZ files into the common Bank model. This is the inverse of
writers/krz_writer.py — see that file and docs/KRZ_FORMAT.md for the
exhaustive format documentation and hardware-verification notes.

Supported use case: import third-party KRZ content (commercial soundsets,
hardware-saved banks) so it can be passed through --resample,
--reduce-key-zones, etc. and re-exported.

Scope and known lossiness (mirrors docs/KRZ_FORMAT.md §7):
  - Objects referencing K2000 ROM samples (numeric id < 200) or objects
    missing from the file are skipped with a summarized [WARN], never fatal.
  - Filter-type reverse-mapping is many-to-one (e.g. K2000 byte 54 can mean
    High1..High8 — we return a canonical representative), mirroring
    parsers/e4b_parser.py's documented approach for the same problem.
  - AMPENV "Natural" mode (ENC[1]==1) means the hardware ignores the ENV
    bytes entirely; such layers keep the model's default envelope rather
    than decoding garbage.
  - Stereo samples (KSample flags bit 0 + a second Soundfilehead) are read
    back as one interleaved 2-channel SampleData. Note that numHeaders > 1
    alone does NOT mean stereo — real files also use multi-header objects
    for groups of MONO samples at different rootkeys.
  - The keymap entry tuning field's partial-key-tracking form and the
    per-entry volAdj unit are not confirmed against hardware — decoded but
    flagged inline (see docs/KRZ_FORMAT.md §3.2).
"""

import array
import struct
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from models.common import (Bank, Preset, VoiceLayer, ZoneMapping, SampleData,
                           LoopType, Envelope, krz_cutoff_byte_to_hz,
                           krz_reson_byte_to_01, krz_env_byte_to_seconds,
                           KRZ_RELEASE_FACTOR, hz_to_e4b_cutoff,
                           key_track_to_filter_amount)


# ---------------------------------------------------------------------------
# Constants (mirror writers/krz_writer.py)
# ---------------------------------------------------------------------------

T_PROGRAM, T_KEYMAP, T_SAMPLE = 36, 37, 38

MAX_NAME = 16
KRZ_ROM_ID_MAX = 199   # object ids < 200 are K2000 ROM content, not in the file

NUM_VELO_LEVELS = 8    # K2000 velocity buckets (ppp..fff), 16 MIDI values each

# Sample rate is stored as an integer nanosecond period (round(1e9/rate)), so
# 1e9/period doesn't invert exactly back to a round number. Snap to the
# nearest standard rate within +/-2 Hz (matches ConvertWithMoss's approach).
_STANDARD_SAMPLE_RATES = (8000, 11025, 16000, 22050, 24000, 32000, 44100,
                          48000, 96000)


def _snap_sample_rate(hz: float) -> int:
    for std in _STANDARD_SAMPLE_RATES:
        if abs(hz - std) <= 2:
            return std
    return round(hz)


# ---------------------------------------------------------------------------
# Container walk (promoted from tests/re_banks/krz_reader.py — verified
# against 577 real .KRZ files with zero container failures and zero unknown
# program segment tags before this parser was written)
# ---------------------------------------------------------------------------

_SEG_FIXED = {0x08: 15, 0x09: 15, 0x0F: 7}          # PGM, LYR, FX
_SEG_MASKED = {0x18: 3, 0x10: 7, 0x14: 7, 0x68: 7,  # FUN; ASR/LFO/KDFX
               0x20: 15, 0x50: 15,                  # ENC/HOB
               0x40: 31, 0x78: 31}                  # CAL/KB3


def _seg_len(tag: int) -> Optional[int]:
    if tag in _SEG_FIXED:
        return _SEG_FIXED[tag]
    return _SEG_MASKED.get(tag & 0xF8)


def _gtype(h: int) -> int:
    return (h >> 10) if (h & 0x8000) else (h >> 8)


def _gid(h: int) -> int:
    return (h & 1023) if (h & 0x8000) else (h & 255)


def _read_objects(data: bytes) -> Tuple[int, List[dict]]:
    """Return (osize, objs).  Each obj is a dict with hash/type/id/name plus
    ``body`` (offset of object-specific data) and ``after``/``objsize`` (for
    program-segment end-of-block math)."""
    if data[:4] != b'PRAM':
        raise ValueError(f"Not a KRZ file (magic={data[:4]!r})")
    osize = struct.unpack_from('>i', data, 4)[0]
    pos = 32
    objs = []
    n = len(data)
    while pos + 4 <= n:
        bs = struct.unpack_from('>i', data, pos)[0]
        after = pos + 4
        if bs >= 0:                       # end marker (0) or padding
            break
        objsize = -bs
        hash_ = struct.unpack_from('>H', data, after)[0]
        ofs = struct.unpack_from('>H', data, after + 4)[0]
        # [:MAX_NAME] is load-bearing, not tidiness. A name is at most 16
        # characters and is NUL-terminated -- but a name that fills the field
        # exactly has no terminator, so `split(b'\0')[0]` returns everything
        # up to `ofs`, which is padded and rounded. Real banks then read back
        # names like 'General MIDI kit\x9d\xdb': the 16 real characters plus
        # two bytes of whatever followed. Those trailing bytes are not name
        # content, and they are exactly the kind of thing that later gets
        # counted as evidence of a non-ASCII character set (they were).
        name = (data[after + 6:after + 4 + ofs]
                .split(b'\0')[0][:MAX_NAME].decode('latin1'))
        objs.append(dict(hash=hash_, type=_gtype(hash_), id=_gid(hash_),
                         name=name, body=after + 2 + 2 + ofs,
                         after=after, objsize=objsize))
        pos = after + objsize - 4
    return osize, objs


def walk_program(data: bytes, obj: dict) -> Iterator[Tuple[int, Optional[bytes]]]:
    """Yield (tag, segment_bytes) for every segment of a Program object.
    segment_bytes is None for an unrecognized tag (walk stops after that)."""
    o, end = obj['body'], obj['after'] + obj['objsize'] - 4
    while o < end - 1:
        tag = data[o]
        if tag == 0:
            break
        length = _seg_len(tag)
        if length is None:
            yield (tag, None)
            break
        yield (tag, bytes(data[o + 1:o + 1 + length]))
        o += 1 + length


# ---------------------------------------------------------------------------
# Sample object  (KSample + Soundfilehead)
# ---------------------------------------------------------------------------

class _KrzHeader:
    __slots__ = ('root_note', 'flags', 'vol_adj_db', 'max_pitch', 'start_w',
                'alt_start_w', 'loop_start_w', 'end_w', 'period',
                'sample_rate', 'has_data', 'looped')

    def __init__(self, data: bytes, ho: int):
        self.root_note = data[ho]
        self.flags = data[ho + 1]
        va = data[ho + 2]
        self.vol_adj_db = (va - 256 if va >= 128 else va) / 2.0
        self.max_pitch = struct.unpack_from('>h', data, ho + 4)[0]
        (self.start_w, self.alt_start_w,
         self.loop_start_w, self.end_w) = struct.unpack_from('>4i', data, ho + 8)
        self.period = struct.unpack_from('>I', data, ho + 28)[0]
        self.sample_rate = _snap_sample_rate(1e9 / self.period) if self.period else 44100
        self.has_data = bool(self.flags & 0x40)
        self.looped = not (self.flags & 0x80)   # inverted: 0x80 clear = looped


def _parse_sample_object(data: bytes, obj: dict) -> dict:
    """Return {'id', 'name', 'stereo', 'headers': [_KrzHeader, ...]}."""
    o = obj['body']
    base_id, num_headers, _headers_ofs = struct.unpack_from('>3h', data, o)
    flags = data[o + 6]
    stereo = bool(flags & 1)
    hdr_base = o + 12
    headers = [_KrzHeader(data, hdr_base + h * 32) for h in range(num_headers + 1)]
    return dict(id=obj['id'], name=obj['name'], stereo=stereo, headers=headers)


def _pcm_extents(sample_objs: List[dict], pcm_words: int) -> Dict[Tuple[int, int], int]:
    """(sample_id, header_idx) -> exclusive PCM end word.

    A sample's end word in the file format is the LOOP end for a looped
    sample, not the PCM end (docs/KRZ_FORMAT.md CR-10), so the true PCM
    extent is recovered from the next sample's start offset in the shared
    PCM region — this also correctly preserves a post-loop decay tail.

    The next-sample start is a HARD ceiling, never pushed past: whether a
    given sampleEnd is inclusive-last-frame or already exclusive varies in
    the wild (corpus-checked 2026-07-27 — real files mix both conventions
    for tightly-packed, zero-gap samples), and guessing wrong must never
    read into a neighboring sample's PCM. Loop points are clamped instead
    when SampleData is built (see parse_krz._get_sample).
    """
    starts = []
    for s in sample_objs:
        for hi, h in enumerate(s['headers']):
            if h.has_data:
                starts.append(h.start_w)
    starts = sorted(set(starts)) + [pcm_words]

    def _next_start(after: int) -> int:
        for st in starts:
            if st > after:
                return st
        return pcm_words

    extents: Dict[Tuple[int, int], int] = {}
    for s in sample_objs:
        for hi, h in enumerate(s['headers']):
            if not h.has_data:
                continue
            end_w = min(_next_start(h.start_w), pcm_words)
            end_w = max(end_w, h.start_w + 1)   # guard: never an empty/negative slice
            extents[(s['id'], hi)] = end_w
    return extents


def _planar_to_interleaved(left: bytes, right: bytes) -> bytes:
    """Two equal-length 16-bit LE channel blocks -> interleaved stereo, the
    exact inverse of `writers.e4b_writer._interleaved_to_planar` (which the KRZ
    writer also uses).  Strided slicing, so no per-frame loop."""
    n = min(len(left), len(right)) // 2      # frames
    out = bytearray(n * 4)
    out[0:n * 4:4] = left[0:n * 2:2]         # left  low byte
    out[1:n * 4:4] = left[1:n * 2:2]         # left  high byte
    out[2:n * 4:4] = right[0:n * 2:2]        # right low byte
    out[3:n * 4:4] = right[1:n * 2:2]        # right high byte
    return bytes(out)


def _extract_pcm(data: bytes, osize: int, h: _KrzHeader, end_w: int) -> bytes:
    """Slice one header's PCM and byteswap BE -> LE (mpc2emu's internal format)."""
    start_byte = osize + 2 * h.start_w
    end_byte = osize + 2 * max(end_w, h.start_w)
    raw = data[start_byte:end_byte]
    # `array.byteswap` flips the bytes inside each 2-byte element in C.
    # frombytes/tobytes are exact inverses on the same host, so the net
    # effect is "swap adjacent byte pairs" on any endianness -- identical
    # to the per-pair Python loop this replaces, but ~50x faster (KRZ banks
    # carry their whole sample pool in one file, so this ran over millions
    # of pairs per bank).
    n2 = len(raw) // 2 * 2
    a = array.array('h')
    a.frombytes(raw[:n2])
    a.byteswap()
    out = a.tobytes()
    # An odd trailing byte can't form a pair; the old loop left it as the
    # zero it was initialised to, so keep that exact length/content.
    return out if n2 == len(raw) else out + b'\x00'


# ---------------------------------------------------------------------------
# Keymap object  (KKeymap)
# ---------------------------------------------------------------------------

class _KrzEntry:
    __slots__ = ('tuning', 'vol_adj', 'sample_id', 'sub_sample')

    def __init__(self, tuning=0, vol_adj=0, sample_id=0, sub_sample=1):
        self.tuning = tuning
        self.vol_adj = vol_adj
        self.sample_id = sample_id
        self.sub_sample = sub_sample

    def key(self):
        return (self.tuning, self.vol_adj, self.sample_id, self.sub_sample)


#: The K2000 sounds keymap entry `i` at MIDI key `i + 12`.  HW-confirmed
#: 2026-08-02: a commercial bank whose entries 0..47 reference an absent ROM
#: sample and whose real samples start at entry 48 is silent below key 60 and
#: sounds from key 60 up, and its run boundary at entry 52 lands on key 64.
#: This is ConvertWithMoss's `12 + ...` form; the earlier corpus-only reading
#: (root-inside-zone, 39.6% vs 26.4%) picked the other one and was wrong.
KEYMAP_ENTRY_NOTE_OFFSET = 12


def _note_of_entry(base_pitch: int, cents_per_entry: int, i: int) -> int:
    """MIDI note sounded by entry `i` — see KEYMAP_ENTRY_NOTE_OFFSET."""
    return (KEYMAP_ENTRY_NOTE_OFFSET
            + round((base_pitch + i * cents_per_entry) / 100.0))


def _parse_keymap_object(data: bytes, obj: dict) -> dict:
    """Return {'id', 'name', 'header_sample_id', 'base_pitch', 'cents_per_entry',
    'num_keys', 'tables': [(vel_lo, vel_hi, [_KrzEntry,...]), ...]}.

    Handles the full method bitfield (compacted keymaps, i8 tuning, per-entry
    volAdj — all real-world, not just mpc2emu's own 0x13 write form) and the
    native Level[8] multi-velocity-table mechanism (docs/KRZ_FORMAT.md §3.2).
    """
    o = obj['body']
    header_sid, method, base_pitch, cents_per_entry, entries_per_vel, _entry_size = \
        struct.unpack_from('>6h', data, o)
    num_keys = entries_per_vel + 1

    # entrySize is recomputed from the method bits (matches ConvertWithMoss's
    # approach) rather than trusted from disk, since it must agree with how we
    # walk entries below.
    entry_size = 0
    if method & 0x10:
        entry_size += 2
    elif method & 0x08:
        entry_size += 1
    if method & 0x04:
        entry_size += 1
    if method & 0x02:
        entry_size += 2
    if method & 0x01:
        entry_size += 1
    entry_size = max(1, entry_size)

    level_base = o + 12
    raw_levels = [struct.unpack_from('>h', data, level_base + 2 * j)[0]
                 for j in range(NUM_VELO_LEVELS)]
    table_addr = [level_base + 2 * j + raw_levels[j] for j in range(NUM_VELO_LEVELS)]

    # Group velocity levels by distinct table address, preserving level order.
    addr_to_levels: "dict[int, list]" = {}
    for j, addr in enumerate(table_addr):
        addr_to_levels.setdefault(addr, []).append(j)

    def _decode_table(addr: int, table_size: int) -> List[_KrzEntry]:
        entries = []
        for k in range(num_keys):
            p = addr + k * entry_size
            tuning = vol_adj = sample_id = 0
            sub_sample = 1
            if method & 0x10:
                tuning = struct.unpack_from('>h', data, p)[0]; p += 2
            elif method & 0x08:
                b = data[p]; tuning = b - 256 if b >= 128 else b; p += 1
            if method & 0x04:
                vol_adj = data[p]; p += 1
            if method & 0x02:
                sample_id = struct.unpack_from('>H', data, p)[0]; p += 2
            else:
                sample_id = header_sid & 0xFFFF   # compacted keymap
            if method & 0x01:
                sub_sample = data[p]
            entries.append(_KrzEntry(tuning, vol_adj, sample_id, sub_sample))
        return entries

    table_size = num_keys * entry_size
    tables = []
    for addr in sorted(addr_to_levels):
        levels = addr_to_levels[addr]
        vel_lo = max(0, min(levels) * 16)
        vel_hi = max(levels) * 16 + 15
        tables.append((vel_lo, vel_hi, _decode_table(addr, table_size)))

    return dict(id=obj['id'], name=obj['name'], header_sample_id=header_sid,
               base_pitch=base_pitch, cents_per_entry=cents_per_entry,
               num_keys=num_keys, tables=tables)


def _entry_runs(entries: List[_KrzEntry]) -> Iterator[Tuple[int, int, _KrzEntry]]:
    """Collapse runs of identical adjacent entries -> (first_key, last_key, entry)."""
    if not entries:
        return
    start = 0
    cur = entries[0].key()
    for k in range(1, len(entries)):
        rec = entries[k].key()
        if rec != cur:
            yield (start, k - 1, entries[start])
            start = k
            cur = rec
    yield (start, len(entries) - 1, entries[start])


# ---------------------------------------------------------------------------
# Program object  (KProgram segments) — geometry (Phase 1) + DSP (Phase 2/3)
# ---------------------------------------------------------------------------

LYR_TAG, CAL_TAG = 0x09, 0x40
ENC_AMPMODE_TAG, ENV_AMP_TAG, ENC_FILTERENV_TAG = 0x20, 0x21, 0x22
HOB_F1_TAG, HOB_F2_TAG, HOB_F3_TAG = 0x50, 0x51, 0x52
LFO1_TAG = 0x14
def _k2_depth_cents(b: int) -> float:
    """K2000 DSP depth byte -> cents, for a frequency-unit function.

    Measured by the k2kremote project one alpha-wheel click at a time, and
    anchored against byte values from this side: the click and the stored byte
    step together (their 25 clicks matched our 127->102 difference exactly).

    Linear at 100 ct per unit over the middle, a COARSER 400-per-step tail at
    the top, and compression toward zero at the bottom. The taper is why a
    two-point fit gave 136 ct/unit and was wrong -- one of the anchors sat in
    the tail. Cross-checked at 98->7000, 58->3000, 54->2600, 52->2400 and, on
    the negative side, -58->-3000 and -77->-4900.

    Negatives mirror on MAGNITUDE, which was an untested assumption in the
    original fit until two signed values from this side confirmed it.

    The unit is per FUNCTION TYPE -- cents here, semitones on a pitch function,
    percent on a width one -- so this must only be called for a frequency slot.
    """
    if b < 0:
        return -_k2_depth_cents(-b)
    if b >= 125:                       # 125/126/127 -> 10000/10400/10800
        return 10000.0 + 400.0 * (b - 125)
    if b >= 33:                        # the linear middle
        # Floor is 33, not 35: k2kremote read byte 33 -> 500ct off a program's
        # own page, exactly 100*(33-28). Their wheel-sweep reading of 32 -> 450
        # disagrees with the law by 50ct, so the taper begins below 33 and the
        # sweep value is the less precise of the two -- a page read beats a
        # value counted while turning a wheel.
        return 100.0 * (b - 28)
    # Below ~35 the field compresses toward zero. Measured points from their
    # sweep: 32->450, 22->80, 12->24, 2->4. Interpolated between those rather
    # than extrapolating the linear law, which would give negative cents here.
    # Nodes from the machine's own display. 14->30, 29->300 and 31->400 came
    # from diffing our decode against k2kremote's correlation dump, where our
    # old curve read 35/339/413 against those values. The remainder are from
    # their alpha-wheel sweep. 32->450 sits exactly halfway between 31->400 and
    # 33->500, which is a check on the two sources agreeing rather than a
    # coincidence.
    pts = [(0, 0.0), (2, 4.0), (12, 24.0), (14, 30.0), (15, 35.0), (19, 55.0),
           (22, 80.0), (24, 100.0), (25, 120.0), (26, 150.0),
           (29, 300.0), (31, 400.0), (32, 450.0)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if b <= x1:
            return y0 + (y1 - y0) * (b - x0) / (x1 - x0)
    return 450.0


#: Codes seen in an F1 slot that this reader cannot name. Collected rather
#: than warned per-occurrence -- a bank can hold hundreds and the useful
#: report is the SET, summarised once, like the skipped-object [WARN] above.
_unknown_f1_blocks = set()


#: K2000 control-source codes, read off the machine's own editor pages by the
#: k2kremote project and correlated against these file bytes across 574
#: program-x-layer rows in four banks -- every one agreeing.
#:
#: The table is SHARED across slots: the same code means the same source whether
#: it appears as Src1 (seg[5]), DptCtl (seg[7]) or Src2 (seg[10]). 121=ENV2 was
#: verified in all three positions, 1=MWheel and 127=ON in two each.
#:
#: Codes 99/108/115/116/117/119/124 were each found by our decode disagreeing
#: with the machine and then being told the right answer -- table gaps, not map
#: errors, which is what a validated map looks like when it meets new material.
_K2_CONTROL_SOURCES = {
    0: 'OFF',       1: 'MWheel',    2: 'Breath',    6: 'Data',
    33: 'MPress',   35: 'PWheel',   98: 'KeyNum',   99: 'BKeyNum',
    100: 'AttVel',  108: 'RandV1',  110: 'ASR1',    111: 'ASR2',
    112: 'FUN1',    113: 'FUN2',    114: 'LFO1',    115: 'LFO1ph',
    116: 'LFO2',    117: 'LFO2ph',  118: 'FUN3',    119: 'FUN4',
    120: 'AMPENV',  121: 'ENV2',    122: 'ENV3',    124: 'PB Rate',
    127: 'ON',
}

_K2_CS_LFO1, _K2_CS_LFO2 = 114, 116
_K2_CS_FUN4, _K2_CS_BKEYNUM = 119, 99

_K2_CS_ENV2 = 121
_K2_CS_LFO1 = 114
_K2_CS_ATTACK_VEL = 100
_K2_FILTER_NONE = 62

# HOB0[0] -> canonical XPM FilterType.  Many-to-one on the write side
# (_k2_filter_plan in krz_writer.py collapses whole XPM ranges onto one K2000
# byte), so this reverse map picks one representative per byte — the same
# "closest structural match" approach parsers/e4b_parser.py documents for its
# own many-to-one filter-byte table.
_K2_FILTER_TO_XPM = {
    62: 0,    # NONE -> off
    15: 1,    # 1-pole LOPASS -> Low1
    2:  2,    # 2-pole LOWPASS -> Low2
    3:  11,   # 2-pole BANDPASS -> Band2
    51: 19,   # PARA MID (parametric boost) -> BB 2P (canonical of 19-22)
    54: 8,    # 4-pole HIPASS W/SEP -> High4 (canonical of 6-10)
    55: 12,   # 4-pole TWIN PEAKS BANDPASS -> Band4 (canonical of 12-14)
    56: 15,   # 4-pole DOUBLE NOTCH W/SEP -> BS 2P (canonical of 15-18)
    50: 3,    # 4-pole LOPASS W/SEP -> Low4 (canonical "default" family)
    # Read off the machine's own display by the k2kremote project, 2026-08-16.
    4:  16,   # NOTCH             -> notch
    5:  23,   # 2-pole ALLPASS    -> allpass
    12: 19,   # HIFREQ STIMULATOR -> treated as a shelving boost
    14: 19,   # STEEP RESONANT BASS
    17: 23,   # ALLPASS
    69: 2,    # LOPAS2            -> Low2
    8:  19,   # PARA BASS      \
    9:  19,   # PARA TREBLE     >  parametric EQ family, NOT lowpass variants --
    13: 19,   # PARAMETRIC EQ  /   see the note on _K2_NON_FILTER below
}

#: seg[0] codes that are NOT filters at all. A K2000 F-slot holds any DSP block,
#: and the same byte position names a pitch, width, amplitude or shaper function
#: depending on the block. Their UNITS differ too -- cents on a frequency slot,
#: semitones on pitch, percent on width, dB on amplitude, a multiplier on the
#: shaper -- so seg[1] is not a cutoff on any of these and must not be read as
#: one.
#:
#: Verified against the machine's display: 18 AMP(GAIN) reads 56dB where the
#: byte is 56, and 64 EVN(2P SHAPER) reads -18dB where the byte is -18. Both
#: 1:1 and neither in cents.
_K2_NON_FILTER = {
    18: 'AMP (GAIN)',        19: 'AMT (SHAPER)',      22: 'WID (PWM)',
    24: 'PCH (LF SIN)',      25: 'PCH (SW+SHP)',      26: 'PCH (SAW+)',
    27: 'PCH (SAW)',         29: 'PCH (SQUARE)',      33: 'PCH (SYNC M)',
    64: 'EVN (2P SHAPER)',
}

_LFO_SHAPE_FROM_BYTE = {
    0: 'sine', 1: '+sine', 2: 'square', 3: '+square', 4: 'triangle',
    5: '+triangle', 6: 'sawtooth', 7: '+sawtooth', 8: 'sawtooth_down',
    20: 'random',
}


def _vel_marks_to_range(byte: int) -> Tuple[int, int]:
    """Inverse of krz_writer._vel_byte: packed (loMark<<3)|(7-hiMark) -> (lo,hi)."""
    lo_mark = (byte >> 3) & 0x07
    hi_mark = 7 - (byte & 0x07)
    lo = max(0, lo_mark * 16)
    hi = min(127, hi_mark * 16 + 15)
    if lo > hi:
        lo, hi = 0, 127
    return lo, hi


def _decode_env(seg: bytes) -> Envelope:
    """15-byte ENV/ENC segment -> Envelope. This is a REDUCER, not a strict
    inverse of krz_writer._fill_env (which always writes a fixed Att/Dec/Rel
    shape): real K2000 programs use all 7 (time,level) stages arbitrarily, so
    peak/sustain/release are recovered generically. See docs/KRZ_FORMAT.md §4.4."""
    def _spct(b):
        return b - 256 if b >= 128 else b

    pairs = [(krz_env_byte_to_seconds(seg[2 * i]), float(_spct(seg[2 * i + 1])))
             for i in range(7)]
    att = pairs[0:3]
    dec = pairs[3]
    rel = pairs[4:7]

    att_levels = [l for _, l in att]
    peak = max(att_levels) if max(att_levels) > 0 else 100.0
    attack = 0.0
    for t, l in att:
        attack += t
        if l >= peak:
            break
    else:
        attack = sum(t for t, _ in att)

    decay = dec[0]
    # A stage whose raw time AND level bytes are both 0 is unused on the
    # device and holds the level of the PREVIOUS stage (the attack peak) --
    # read literally, this looks like an instant decay to silence. Found via
    # ConvertWithMoss PR #232 (2026-07-27): K2000 programs that leave decay
    # unused (e.g. FM basses sustaining at the attack level, fading only via
    # the release stages) were converted to silent presets before this check.
    if seg[6] == 0 and seg[7] == 0:
        sustain = 1.0  # holds at the attack peak, i.e. 100% of `peak`
    else:
        sustain = max(0.0, min(1.0, dec[1] / peak)) if peak else 0.0

    release = 0.0
    for t, l in rel:
        release += t
        if l <= 0:
            break
    release /= KRZ_RELEASE_FACTOR

    return Envelope(attack=attack, decay=decay, sustain=sustain, release=release)


class _KrzLayer:
    def __init__(self):
        self.keymap_id = 0
        self.lo_key, self.hi_key = 0, 127
        self.lo_vel, self.hi_vel = 0, 127
        self.transpose = 0
        self.filter_type = 0
        self.filter_cutoff = 1.0
        self.filter_resonance = 0.0
        self.filter_env_amount = 0.0
        self.velocity_to_filter = 0.0
        self.velocity_to_filter_min = 0.0
        self.filter_keytrack = 0.0
        # DECLARED HERE OR SILENTLY DISCARDED. This intermediate layer is not
        # the model voice: the fields below are copied across one by one when
        # the VoiceLayer is built, so a field assigned during the walk but
        # missing from BOTH this __init__ and that call simply becomes a stray
        # attribute nobody ever reads. No error, no warning, correct-looking
        # output -- I wired the LFO pair, watched 412 tests pass, and measured
        # zero of 126 routings arriving before finding it.
        self.lfo1_to_filter = 0.0
        self.lfo2_to_filter = 0.0
        self.lfo1_to_pitch = 0.0
        self.lfo1_rate: Optional[float] = None
        self.lfo1_shape: Optional[str] = None
        self.amp_env: Optional[Envelope] = None     # None = leave model default (Natural)
        self.filter_env: Optional[Envelope] = None


def _parse_program_object(data: bytes, obj: dict) -> Tuple[str, List[_KrzLayer]]:
    """Return (preset_name, [_KrzLayer, ...]).  Segments before the first LYR
    tag (PGM/FX) are skipped — they carry no per-layer geometry/DSP."""
    layers: List[_KrzLayer] = []
    cur: Optional[_KrzLayer] = None
    hob = {}   # tag -> bytes, reset per layer

    for tag, seg in walk_program(data, obj):
        if seg is None:
            break   # unrecognized tag; stop (matches krz_reader.py behavior)
        if tag == LYR_TAG:
            cur = _KrzLayer()
            layers.append(cur)
            hob = {}
            cur.lo_key, cur.hi_key = seg[3], seg[4]
            cur.lo_vel, cur.hi_vel = _vel_marks_to_range(seg[5])
            continue
        if cur is None:
            continue   # PGM/FX global segments
        if tag == CAL_TAG:
            t = seg[1]
            cur.transpose = t - 256 if t >= 128 else t
            cur.keymap_id = (seg[11] << 8) | seg[12]   # CAL[11:13] only, see TODO.md
            if seg[21] == _K2_CS_LFO1:
                cur.lfo1_to_pitch = max(0.0, min(1.0, seg[22] / 79.0))
        elif tag == ENC_AMPMODE_TAG:
            if seg[1] != 1:   # 1 = Natural (hardware ignores ENV) -> leave default
                pass          # actual ENV bytes read from ENV_AMP_TAG below
            else:
                cur.amp_env = False   # sentinel: Natural, decoded ENV must be ignored
        elif tag == ENV_AMP_TAG:
            if cur.amp_env is not False:
                cur.amp_env = _decode_env(seg)
            else:
                cur.amp_env = None
        elif tag == ENC_FILTERENV_TAG:
            cur.filter_env = _decode_env(seg)
        elif tag == HOB_F1_TAG:
            hob[HOB_F1_TAG] = seg
            b0 = seg[0]
            # AN UNRECOGNISED BLOCK MUST REFUSE, NOT DEFAULT.
            #
            # This used to be `_K2_FILTER_TO_XPM.get(b0, 3)` -- an unknown code
            # became a 2-pole BANDPASS, with seg[1] read as its cutoff. That is
            # not a dropped parameter, it is an INVENTED one: 10.2% of F1 slots
            # across 80 banks carried a code the table did not know, and every
            # one of them got a filter the program never had, tuned from a byte
            # that on those blocks is a pitch, a width or a gain.
            #
            # It never failed loudly because the common case really is a filter
            # (code 2, plain lowpass, is 85% of the corpus) and because a
            # fabricated bandpass produces plausible-sounding output. The three
            # codes I would have guessed as lowpass variants -- 8, 9, 13, which
            # cluster on the algorithms that offer filters -- turned out to be
            # PARA BASS, PARA TREBLE and PARAMETRIC EQ. Guessing would have been
            # wrong in exactly the way that does not announce itself.
            if b0 in _K2_NON_FILTER:
                cur.filter_type = 0          # not a filter block; leave it alone
            elif b0 != _K2_FILTER_NONE and b0 not in _K2_FILTER_TO_XPM:
                _unknown_f1_blocks.add(b0)
                cur.filter_type = 0
            elif b0 != _K2_FILTER_NONE:
                cur.filter_type = _K2_FILTER_TO_XPM[b0]
                hz = krz_cutoff_byte_to_hz(seg[1])
                cur.filter_cutoff = hz_to_e4b_cutoff(hz)
                # BOTH SOURCE SLOTS, ONE SCALE.
                #
                # A K2000 DSP function has two modulation sources. Slot 1 is
                # seg[5] with its depth in seg[6]; slot 2 is seg[10] with MaxDpt
                # in seg[9]. Until 2026-08-17 this read slot 1 as `byte / 127`
                # and slot 2 as `cents / 10800` -- two different scales for the
                # same model field depending on which slot the routing happened
                # to use. The /127 form treats a cents-scaled byte as a
                # fraction, so it was simply wrong; measured against the
                # machine's own pages, seg[6] carries the SAME taper as seg[9]
                # (62->3400ct, 46->1800, 42->1400, 17->45, all exact).
                #
                # Normalised on 10800 ct, the largest value the field reaches.
                #
                # ONLY FOUR SOURCES ARE MAPPED, and that is a model limit rather
                # than a reading one: LFO1/LFO2/ENV2/velocity have fields, while
                # MWheel, MPress, Data and ON do not. Across 3612 filter layers
                # that leaves ~640 routings read and discarded -- see TODO,
                # which carries the count so the decision is sized rather than
                # guessed at.
                # seg[3] IS KeyTrk, IN HALF-CENTS PER KEY.
                #
                # Named by the same join that identified VelTrk: seg[3] against
                # the machine's displayed KeyTrk agreed on 91 of 91 programs,
                # and the scale is a plain doubling -- displayed cents per key
                # is exactly seg[3] * 2, on all 45 non-zero observations, ratio
                # 2.00 every time. Not the depth taper that VelTrk uses; a
                # straight linear byte.
                #
                # Never read until 2026-08-17, and it is on 2455 of 15451
                # filter slots (15.9%). `filter_keytrack` has existed in the
                # model throughout and is consumed by the E4B writer, so those
                # conversions have been losing key tracking as well.
                #
                # 100 cents per key is one octave of cutoff per octave of key,
                # so the conversion goes through the existing
                # `key_track_to_filter_amount` helper rather than inventing a
                # scale: byte * 2 / 100 is the oct/oct ratio it expects.
                _kt = seg[3] - 256 if seg[3] >= 128 else seg[3]
                if _kt:
                    cur.filter_keytrack = key_track_to_filter_amount(
                        _kt * 2.0 / 100.0)

                # seg[4] IS VelTrk: A DIRECT VELOCITY->CUTOFF AMOUNT.
                #
                # Read as zero until 2026-08-17, and it is the DOMINANT
                # mechanism rather than a rare one. In one bank of 91 filter
                # slots: Src2 = AttVel appears once, VelTrk is non-zero
                # NINETEEN times. The routing this parser counted was the rare
                # one and the routing it ignored was the common one.
                #
                # JOINED against the machine's own pages (k2kremote read all 91
                # programs of that bank off the panel): seg[4] decoded with
                # `_k2_depth_cents` matches the displayed VelTrk on 89 of 91.
                # Of the two misses, one is 3 cents apart in the compressed low
                # region, and the other is a program whose filter sits in slot
                # F3 -- where the F1 tag is a different DSP block entirely, so
                # seg[4] is not its VelTrk. That miss independently confirms
                # the F3 blindness recorded in TODO.
                #
                # It is UNIPOLAR from the cutoff, like MinDpt 0 / MaxDpt N, so
                # it goes in as (0, VelTrk). AND IT GOES NEGATIVE -- observed
                # at -4600 ct and -60 ct, where velocity DARKENS. Anything
                # assuming velocity only ever opens the filter gets those
                # backwards rather than merely shallow.
                #
                # Added to whatever Src1/Src2 contribute rather than replacing
                # it: a program may carry both, and they sum on the machine.
                _vt = seg[4] - 256 if seg[4] >= 128 else seg[4]
                if _vt:
                    _vt_amt = max(-1.0, min(1.0,
                                            _k2_depth_cents(_vt) / 10800.0))
                    cur.velocity_to_filter = max(
                        -1.0, min(1.0, cur.velocity_to_filter + _vt_amt))

                # THE THIRD ELEMENT IS THE FLOOR, AND IT IS THE POINT.
                # Slot 2 specifies a RANGE -- MinDpt at zero velocity, MaxDpt
                # at full -- while slot 1 gives one Depth, which is the same
                # shape starting from zero. Carrying only the ceiling loses
                # whether a sweep merely opens the filter or also closes it,
                # and a unipolar sweep re-centred on a bipolar destination
                # drives the corner below a floor the source never crosses.
                # That silenced a zone on an S3000XL (see AKAIVELFILT).
                for _src, _depth, _floor in ((seg[5], seg[6], 0),
                                             (seg[10], seg[9], seg[8])):
                    if not _src:
                        continue
                    _d = _depth - 256 if _depth >= 128 else _depth
                    _f = _floor - 256 if _floor >= 128 else _floor
                    _amt = max(-1.0, min(1.0, _k2_depth_cents(_d) / 10800.0))
                    _amt_min = max(-1.0, min(1.0, _k2_depth_cents(_f) / 10800.0))
                    if _src == _K2_CS_ENV2:
                        cur.filter_env_amount = abs(_amt)   # model is 0..1
                    elif _src == _K2_CS_ATTACK_VEL:
                        cur.velocity_to_filter = _amt
                        cur.velocity_to_filter_min = _amt_min
                    elif _src == _K2_CS_LFO1:
                        cur.lfo1_to_filter = _amt
                    elif _src == _K2_CS_LFO2:
                        cur.lfo2_to_filter = _amt
            else:
                cur.filter_type = 0
        elif tag == HOB_F2_TAG:
            hob[HOB_F2_TAG] = seg
            f1 = hob.get(HOB_F1_TAG)
            if f1 is not None and f1[0] != _K2_FILTER_NONE:
                b0 = f1[0]
                if b0 == 51:                       # PARA MID gain, not resonance
                    cur.filter_resonance = max(0.0, min(1.0, (seg[1] - 12) / 12.0))
                elif b0 == 3:                       # 2-pole BP: F2 is width, not resonance
                    pass
                else:
                    # RESONANCE IS IN seg[1] WHETHER OR NOT seg[0] SAYS 16.
                    #
                    # This used to require seg[0] == 16, which is true in 37 of
                    # 3612 filter layer-pairs -- 1.0%. Non-zero resonance is
                    # present in 801 of them, 22.2%. So we were reading one
                    # resonance value in twenty-two.
                    #
                    # seg[0] is 0 on the overwhelming majority because F2 is the
                    # SECOND CONTROL INPUT of the F1 block, not a block of its
                    # own: on a 2-pole lowpass the machine shows F1 FRQ and
                    # F2 RES, two inputs of one filter. Only when the F1 block
                    # takes a single input does F2 begin a new block and carry a
                    # type of its own.
                    #
                    # Scale confirmed on 30 distinct displayed values from -15.0
                    # to +24.0 dB, every one exactly byte/2 -- the docstring on
                    # krz_reson_byte_to_01 already said dB*2 and was right.
                    #
                    # KNOWN LOSS: 204 of the 801 are CUTS, and the model's
                    # filter_resonance is 0..1 with no room for a negative, so
                    # those still clamp to 0. That is a model limit, not a
                    # reader one, and it is recorded in TODO rather than papered
                    # over here -- the fix is a signed range on the model, which
                    # every writer would then have to honour.
                    cur.filter_resonance = krz_reson_byte_to_01(seg[1])
        elif tag == LFO1_TAG:
            rate_byte = seg[2]
            cur.lfo1_rate = max(0.0, (rate_byte - 26) / 10.0)
            cur.lfo1_shape = _LFO_SHAPE_FROM_BYTE.get(seg[4])

    # amp_env sentinel cleanup: False (Natural, no ENV seen yet) or unresolved -> None
    for layer in layers:
        if layer.amp_env is False:
            layer.amp_env = None

    return obj['name'], layers


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_krz(path: str) -> Bank:
    """Parse a .KRZ file and return a Bank.

    Never raises for malformed/partial objects — each is skipped with a
    [WARN], mirroring parsers/e4b_parser.py. Layers referencing K2000 ROM
    samples (id < 200) or missing objects are dropped with a single summarized
    warning rather than one line per zone.
    """
    print(f"Parsing KRZ: {path}")
    data = Path(path).read_bytes()
    osize, objs = _read_objects(data)
    pcm_words = (len(data) - osize) // 2

    # A BIG FILE THAT YIELDS NO OBJECTS IS NOT AN EMPTY BANK.
    #
    # the continuation volume of a two-disk soundset is 1.4 MB and decodes to zero objects: its object table
    # declares 36 bytes. Until now we reported that as "0 preset(s),
    # 0 sample(s)" and exited successfully -- indistinguishable from a bank
    # that genuinely holds nothing.
    #
    # Its sibling explains it, and the explanation is a format gap rather than
    # a corrupt file: its first disk (Disk1) reads normally at osize=75484,
    # the continuation volume of a two-disk soundset (Disk2) is the SECOND FLOPPY of one bank. A K2000 bank too
    # large for one disk continues onto the next, so the continuation volume
    # carries sample DATA whose object headers stayed on disk 1. Strongly
    # supported -- same soundset, sequential disk directories, a full-size file
    # with a stub table -- but inferred, not confirmed against hardware.
    #
    # We have no multi-disk assembly, so this stays a warning rather than a
    # fix. Reading it would mean concatenating PCM across files against disk
    # 1's headers.
    #
    # The threshold is deliberately crude. A real empty bank is a few hundred
    # bytes of header; anything past 64 KiB with no objects in it is a read
    # failure wearing an empty bank's clothes, and the point is to say so
    # rather than to classify it correctly.
    if not objs and len(data) > 65536:
        print(f"  [WARN] {len(data)} bytes but NO decodable objects (object "
              f"table declares {osize} bytes). This file is not empty — we "
              f"cannot read it. Treat the empty result below as a failure, "
              f"not as the bank's contents. See TODO.md.")

    sample_objs = []
    keymap_objs = []
    program_objs = []
    for obj in objs:
        try:
            if obj['type'] == T_SAMPLE:
                sample_objs.append(_parse_sample_object(data, obj))
            elif obj['type'] == T_KEYMAP:
                keymap_objs.append(_parse_keymap_object(data, obj))
            elif obj['type'] == T_PROGRAM:
                program_objs.append(_parse_program_object(data, obj))
        except (struct.error, IndexError, ValueError) as exc:
            print(f"  [WARN] Skipping malformed object '{obj.get('name','?')}' "
                  f"(type {obj.get('type')}): {exc}")

    extents = _pcm_extents(sample_objs, pcm_words)
    # KEYING BY ID ALONE IS SAFE HERE **ONLY** BECAUSE EACH LIST IS ONE TYPE.
    #
    # The hash packs the type alongside the id (`type << 10 | id`), so the
    # format positively PERMITS two objects with the same id and different
    # types in one bank -- they hash differently and are both legal. An id is
    # therefore unique only within a type, and a dict keyed by id across types
    # would silently resolve a reference to whichever object was seen first.
    #
    # **AND THIS IS THE NORM, NOT AN EDGE CASE.** Measured over the 318 local
    # KRZ files: **285 of them (90%) hold at least one id in more than one
    # type**, and the worst carries 600 such ids -- 200, 201, 202 ... each
    # held by types 36, 37 and 38 at once, because the three types are simply
    # numbered from 200 in parallel. VinSamLib measured the same pattern in
    # 1631 banks of their own corpus.
    #
    # So a by-id dict spanning types would not fail rarely on an exotic bank.
    # It would pick the wrong object on nine banks in ten.
    #
    # VinSamLib hit exactly that on 2026-08-12: their FX lookups are keyed by
    # id alone across two effect types, and their corpus evidence for it was
    # "0 of 10 985 resolutions found a candidate in more than one type" -- a
    # fact about their corpus, not about the format, which is silent in the
    # permissive direction. They now report the collision rather than guessing
    # a precedence, because the reference carries no type and which object is
    # meant is genuinely undecidable from the file.
    #
    # We are not exposed, and the reason is the filter above: sample_objs,
    # keymap_objs and program_objs each hold exactly ONE type, so a sample 5
    # and a keymap 5 land in different dicts. **Do not merge these lists, and
    # do not add a by-id dict built from more than one type without carrying a
    # type with the key.**
    samples_by_id = {s['id']: s for s in sample_objs}
    keymaps_by_id = {k['id']: k for k in keymap_objs}

    # Lazy SampleData cache keyed (sample_id, header_idx) -- ROM/orphan samples
    # never get materialized, so all-ROM banks cost nothing.
    sample_cache: Dict[Tuple[int, int], SampleData] = {}
    sample_gain_db: Dict[str, float] = {}   # SampleData.name -> Soundfilehead.volumeAdjust
    all_names: set = set()
    used_sample_ids: set = set()
    n_rom = n_absent = n_stereo = n_half_stereo = 0

    def _get_sample(sample_id: int) -> Optional[Tuple[SampleData, int]]:
        """Return (SampleData, header_idx) for sample_id, or None if
        unavailable (ROM/absent).  A stereo sample (KSample flags bit 0, two
        Soundfileheads over two planar per-channel blocks) is returned as one
        interleaved 2-channel SampleData; header_idx is always the first
        header, which is the one whose loop points and rootkey are used."""
        nonlocal n_rom, n_absent, n_stereo, n_half_stereo
        s = samples_by_id.get(sample_id)
        if s is None:
            n_absent += 1
            return None
        used_sample_ids.add(sample_id)
        header_idx = 0
        key = (sample_id, header_idx)
        if key in sample_cache:
            return sample_cache[key], header_idx
        # Read both channels only when the sample really is stereo AND a second
        # header exists: numHeaders > 1 is ALSO used for multi-sample groups of
        # MONO samples at different rootkeys (71 such objects in the corpus,
        # up to 64 headers), so header count alone must not be taken as stereo.
        stereo = bool(s['stereo']) and len(s['headers']) >= 2
        if stereo:
            n_stereo += 1
        h = s['headers'][header_idx] if header_idx < len(s['headers']) else None
        if h is None or not h.has_data:
            n_rom += 1
            return None
        if h.start_w >= pcm_words:
            # start_w points entirely outside this file's own PCM region --
            # seen in multi-disk soundsets (e.g. "<soundset>/Disk1/...")
            # whose sample headers reference PCM that actually lives on a
            # different disk image. has_data is set, but the bytes simply
            # aren't here; treat like ROM rather than fabricating a phantom
            # 0-length SampleData (which corrupted writer math downstream --
            # found via a VinSamLib KRZ->KRZ crash, 2026-07-27).
            n_rom += 1
            return None
        end_w = extents.get(key, h.start_w)
        pcm = _extract_pcm(data, osize, h, end_w)
        channels = 1
        if stereo:
            h2 = s['headers'][1]
            pcm2 = (_extract_pcm(data, osize, h2,
                                 extents.get((sample_id, 1), h2.start_w))
                    if h2.has_data and h2.start_w < pcm_words else b'')
            if pcm2:
                # The two planar blocks should be the same length; a
                # tightly-packed file can leave the extent estimate a frame
                # out, so trim to the shorter rather than emit a ragged
                # interleave that would swap the channels part-way through.
                n = min(len(pcm), len(pcm2)) // 2 * 2
                pcm = _planar_to_interleaved(pcm[:n], pcm2[:n])
                channels = 2
            else:
                # Flagged stereo but the second block is ROM/absent — keep the
                # one channel we have rather than dropping the sample.
                n_stereo -= 1
                n_half_stereo += 1
        candidate = s['name'][:MAX_NAME]
        if candidate in all_names:
            candidate = f"{s['name'][:14]}#{header_idx}"[:MAX_NAME]
        if candidate in all_names:
            candidate = (s['name'][:11] + f"{sample_id:04d}")[:MAX_NAME]
        all_names.add(candidate)
        n_frames = len(pcm) // 2 // channels
        last_idx = max(0, n_frames - 1)
        # Defensive clamp: whether sampleEnd is inclusive-last-frame or already
        # exclusive varies for tightly-packed real-world samples (see
        # _pcm_extents); never emit a loop point past the PCM we actually
        # extracted, which is capped at the next sample's start.
        loop_start = min(max(0, h.loop_start_w - h.start_w), last_idx) if h.looped else 0
        loop_end = min(max(0, h.end_w - h.start_w), last_idx) if h.looped else 0
        sd = SampleData(
            name=candidate, data=pcm, sample_rate=h.sample_rate,
            channels=channels,
            bit_depth=16,
            loop_type=LoopType.FORWARD if h.looped else LoopType.NO_LOOP,
            loop_start=loop_start, loop_end=loop_end,
            root_note=h.root_note,
        )
        sample_cache[key] = sd
        sample_gain_db[candidate] = h.vol_adj_db
        return sd, header_idx

    n_zones = 0

    def _voices_from_keymap(layer: _KrzLayer, km: dict) -> List[VoiceLayer]:
        nonlocal n_zones
        voices: List[VoiceLayer] = []
        for vel_lo, vel_hi, entries in km['tables']:
            lo_vel = max(layer.lo_vel, vel_lo)
            hi_vel = min(layer.hi_vel, vel_hi)
            if lo_vel > hi_vel:
                continue
            zones: List[ZoneMapping] = []
            for first, last, entry in _entry_runs(entries):
                got = _get_sample(entry.sample_id)
                if got is None:
                    continue
                sd, _hidx = got
                lo_key = max(layer.lo_key, _note_of_entry(
                    km['base_pitch'], km['cents_per_entry'], first))
                hi_key = min(layer.hi_key, _note_of_entry(
                    km['base_pitch'], km['cents_per_entry'], last))
                if lo_key > hi_key:
                    continue
                # entry.tuning is a per-entry cents offset ON TOP OF the K2000's
                # automatic (key - sample.root_note)*100 transpose -- usually a
                # small "fine" nudge (root_key == sample.root_note), but real
                # drum-map keymaps use it to CANCEL that transpose and assign
                # each key an arbitrary independent pitch (one sample per key,
                # no keytracking). Using sample.root_note as ZoneMapping.root_key
                # unconditionally is only correct in the first case; the second
                # both mis-pitches the zone AND can trip the K2000 up-pitch
                # ceiling on re-encode (a key far from root_note looks like a
                # huge upward stretch even though the tuning brings it back
                # down). Fold BOTH terms into a single effective root_key +
                # fine_tune so (key - root_key)*100 + fine_tune reproduces the
                # true total shift for every key in this entry-run, matching
                # what every OTHER parser's ZoneMapping model assumes:
                #   true_shift(key) = 100*(key - sample.root_note) + t_total
                #                    = 100*(key - Z)   where Z = sample.root_note - t_total/100
                t_total = entry.tuning + 100 * layer.transpose
                z = sd.root_note - t_total / 100.0
                root_key = round(z)
                fine = round((root_key - z) * 100)
                zone_volume = sample_gain_db.get(sd.name, 0.0)
                if entry.vol_adj:
                    v = entry.vol_adj - 256 if entry.vol_adj >= 128 else entry.vol_adj
                    zone_volume += v / 2.0   # unit unverified, see docs/KRZ_FORMAT.md §3.2
                zones.append(ZoneMapping(
                    sample_name=sd.name, lo_key=lo_key, hi_key=hi_key,
                    lo_vel=lo_vel, hi_vel=hi_vel, root_key=root_key,
                    coarse_tune=0, fine_tune=fine,
                    volume=zone_volume,
                ))
                n_zones += 1
            if zones:
                voices.append(VoiceLayer(
                    zones=zones,
                    filter_type=layer.filter_type,
                    filter_cutoff=layer.filter_cutoff,
                    filter_resonance=layer.filter_resonance,
                    filter_env_amount=layer.filter_env_amount,
                    velocity_to_filter=layer.velocity_to_filter,
                    velocity_to_filter_min=layer.velocity_to_filter_min,
                    filter_keytrack=layer.filter_keytrack,
                    lfo1_to_filter=layer.lfo1_to_filter,
                    lfo2_to_filter=layer.lfo2_to_filter,
                    lfo1_to_pitch=layer.lfo1_to_pitch,
                    lfo1_rate=layer.lfo1_rate,
                    lfo1_shape=layer.lfo1_shape,
                    amp_env=layer.amp_env if layer.amp_env else Envelope(),
                    filter_env=layer.filter_env if layer.filter_env else Envelope(0.0, 0.3, 1.0, 0.0),
                ))
        return voices

    presets: List[Preset] = []
    used_keymap_ids: set = set()
    for name, layers in program_objs:
        voices: List[VoiceLayer] = []
        for layer in layers:
            km = keymaps_by_id.get(layer.keymap_id)
            if km is None:
                continue
            used_keymap_ids.add(layer.keymap_id)
            voices += _voices_from_keymap(layer, km)
        if voices:
            presets.append(Preset(name=name[:MAX_NAME], voices=voices))

    # Orphan recovery: a keymap no program references still has playable
    # sample data -- synth one full-range preset per orphan keymap so a
    # pure sample-pool bank (no program objects at all) still converts.
    n_orphan_keymaps = 0
    for kid, km in keymaps_by_id.items():
        if kid in used_keymap_ids:
            continue
        voices = _voices_from_keymap(_KrzLayer(), km)
        if voices:
            presets.append(Preset(name=km['name'][:MAX_NAME], voices=voices))
            n_orphan_keymaps += 1

    # Orphan samples: playable sample data no keymap (used or orphan) ever
    # referenced. Spread them across the keyboard by root note, classic
    # multisample style, in one extra preset.
    orphan_ids = [sid for sid, s in samples_by_id.items()
                 if sid not in used_sample_ids
                 and any(h.has_data for h in s['headers'])]
    n_orphan_samples = 0
    if orphan_ids:
        got_list = []
        for sid in orphan_ids:
            got = _get_sample(sid)
            if got is not None:
                got_list.append(got[0])
        got_list.sort(key=lambda sd: sd.root_note)
        zones = []
        n = len(got_list)
        for i, sd in enumerate(got_list):
            lo = 0 if i == 0 else min(sd.root_note, (got_list[i - 1].root_note + sd.root_note) // 2 + 1)
            hi = 127 if i == n - 1 else max(sd.root_note, (sd.root_note + got_list[i + 1].root_note) // 2)
            zones.append(ZoneMapping(sample_name=sd.name, lo_key=lo, hi_key=hi, root_key=sd.root_note))
            n_zones += 1
        if zones:
            presets.append(Preset(name=(Path(path).stem[:12] + "_ORP")[:MAX_NAME],
                                  voices=[VoiceLayer(zones=zones)]))
            n_orphan_samples = len(zones)

    samples = list(sample_cache.values())
    bank_name = Path(path).stem[:MAX_NAME]
    bank = Bank(name=bank_name, presets=presets, samples=samples)

    if n_rom:
        print(f"  [WARN] {n_rom} zone(s) reference K2000 ROM samples "
              f"(no PCM in this file) — skipped.")
    if n_absent:
        print(f"  [WARN] {n_absent} zone(s) reference sample object(s) "
              f"not present in this file — skipped.")
    if n_stereo:
        print(f"  [INFO] {n_stereo} stereo sample(s) read as two channels.")
    if n_half_stereo:
        print(f"  [WARN] {n_half_stereo} sample(s) flagged stereo carry only "
              f"one channel in this file — read as mono.")
    if n_orphan_keymaps:
        print(f"  [INFO] {n_orphan_keymaps} keymap(s) not referenced by any "
              f"program recovered as their own preset(s).")
    if n_orphan_samples:
        print(f"  [INFO] {n_orphan_samples} sample(s) not referenced by any "
              f"keymap recovered into one multisample preset.")
    # THE GUARD USED TO BE `sample_objs or keymap_objs`, WHICH IS THE EXACT
    # NEGATION OF THE CASE THIS MESSAGE EXISTS FOR. A programs-only bank is
    # defined by having neither, so the one diagnostic written for it could
    # never fire for it -- it printed only when samples existed but all of them
    # dropped out, which is a different (and much rarer) fault.
    #
    # 39 of 201 corpus banks are programs-only, 19.4%, referencing the K2000's
    # ROM soundset: one programs-only bank carries 100 programs and not one sample object.
    # Every one of them converted to an empty bank whose only explanation was a
    # row of zeros -- correct behaviour, reported identically to a failure.
    if not samples and program_objs:
        print(f"  [INFO] This bank holds {len(program_objs)} program(s) but no "
              f"sample or keymap objects: it references the K2000's ROM "
              f"soundset, which is not in the file. Nothing to convert — this "
              f"is the bank's nature, not a read error.")
    print(f"  {len(presets)} preset(s), {len(samples)} sample(s), "
          f"{n_zones} zone(s) total")
    return bank
