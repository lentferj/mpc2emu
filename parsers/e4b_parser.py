# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# E4B format reverse-engineered from the same sources as writers/e4b_writer.py;
# this file is the reader/inverse of that writer. No third-party source code copied.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
EMU E4B Bank Parser
-------------------
Reads .E4B files (FORM E4B0 / EOS 4.x) into the common Bank model.
This is the inverse of writers/e4b_writer.py — see that file for the
exhaustive format documentation and hardware-verification notes.

Supported use case: import third-party E4XT content (factory libraries,
hardware-saved banks) so it can be passed through --resample,
--reduce-key-zones, etc. and re-exported.

Round-trip fidelity notes:
  - Sample PCM and zone key/velocity/root fields are preserved exactly.
  - Filter type reverse-mapping is many-to-one (e.g. E4B 0x11 can mean Band 4,
    Band 6, Band 8, or BB 4-8P — we return 12=Band 4 as the canonical choice).
  - Filter envelope parameters are inverses of _fenv_level/_fenv_rate
    (rate↔time uses the hardware-calibrated log fit shared with e4b_writer).
  - Root note is decoded from the '_NoteOctave' suffix appended by
    _sample_display_name(); if the suffix is absent (third-party content),
    root_note defaults to 60 and playback pitch comes from each zone's root_key.
"""

import math
import re
import struct
from pathlib import Path
from models.common import (Bank, Preset, VoiceLayer, ZoneMapping, SampleData,
                           LoopType, Envelope, lfo_rate_byte_to_hz,
                           env_rate_to_seconds, env_byte_to_level,
                           cord_byte_to_amount,
                           e4xt_cutoff_byte_to_position, e4xt_byte_to_volume_db)


# ---------------------------------------------------------------------------
# Constants (mirror writers/e4b_writer.py)
# ---------------------------------------------------------------------------

FORM_MAGIC  = b'FORM'
FORM_TYPE   = b'E4B0'
PRES_TAG    = b'E4P1'
SAMP_TAG    = b'E3S1'

MAX_NAME    = 16
SAMP_HDR    = 94
PRES_HDR    = 82
VOICE_FIXED = 284
ZONE_ENTRY  = 22
VOICE_MOD_OFF = 190           # modulation cord table at voice[190:270]
_MOD_LFO_TO_PITCH_AMT   = 10  # slot 2: LFO1 → Pitch ("Cord 02")
_MOD_LFO_TO_PITCH_SLOT  = 2   #   …its cord slot (gate dest = 0xA8 + 2)
# Mod-wheel→LFO-depth gate (inverse of e4b_writer): ModWheel source = 0x11,
# Cord-N-Amount dest = 0xA8 + N.  The EOS template ships a default
# ModWheel→C02Amt at byte 16 even with no LFO — treated as the default, not a
# gate, so non-LFO voices don't reconstruct a phantom LFO1→Pitch.
_SRC_MOD_WHEEL          = 0x11
_CORD_AMT_DEST_BASE     = 0xA8
_MOD_WHEEL_GATE_DEFAULT = 16
_MOD_VEL_TO_CUTOFF_AMT  = 18  # slot 4: Velocity → Filter-Freq ("Cord 04")
_MOD_FENV_TO_CUTOFF_AMT = 22  # slot 5: FilterEnv → Filter-Freq ("Cord 05")
_MOD_KEY_TO_CUTOFF_AMT  = 26  # slot 6: Key → Filter-Freq ("Cord 06")
# (src, dst) of LFO routings written into free cord slots (mirror of writer).
_MOD_LFO1_TO_FILTER   = (0x60, 0x38)
_MOD_LFO1_TO_FILTER_Q = (0x60, 0x39)
_MOD_LFO2_TO_PITCH    = (0x68, 0x30)
_MOD_LFO2_TO_FILTER   = (0x68, 0x38)
_MOD_LFO2_TO_FILTER_Q = (0x68, 0x39)

# LFO1/LFO2 Primary-Zone-Table bytes (mirror of writers/e4b_writer.py).  Shape
# code → canonical name (Sine=1 hardware-confirmed).  PZT offsets in the 64-byte
# primary zone table: LFO1 Rate=42/Shape=43/Delay=44/Variation=45/Sync=46;
# LFO2 is the +8 mirror Rate=50/Shape=51/Delay=52/Variation=53/Sync=54.
_LFO_SHAPE_NAME = {
    0x00: 'triangle', 0x01: 'sine', 0x02: 'sawtooth',
    0x03: 'square', 0x0F: 'hemiquaver', 0xFF: 'random',
}
_LFO_DELAY_MAX_S = 20.0
# LFO rate byte -> Hz lives in models.common (lfo_rate_byte_to_hz), shared.

# Primary zone table filter-envelope section template (bytes 14-25 of _PRIMARY_ZONE_TMPL).
# Default (filter_env_amount=0) — see writers/e4b_writer.py for full 64-byte template.
_PZT_FENV_DEFAULT = bytes([
    0x00, 0x00,   # Attack1:  rate=0,  level=0
    0x00, 0x7F,   # Attack2:  rate=0,  level=+100
    0x00, 0x7E,   # Decay1:   rate=0,  level=+99
    0x00, 0x7F,   # Decay2:   rate=0,  level=+100
    0x14, 0x00,   # Release1: rate=20, level=0
    0x00, 0x00,   # Release2: rate=0,  level=0
])

# E4B vpar[58] byte → canonical XPM FilterType.
# Forward mapping (writers/e4b_writer.py) is many-to-one; we pick the
# closest structural match for each E4B byte.  Lossiness documented inline.
# Full E4XT byte set is hardware-confirmed (B.005-FILTERTYPES.E4B, 2026-06-08;
# see writers/e4b_writer.py:_E4XT_FILTER_BYTES).  XPM has no Swept EQ / Phaser /
# Flanger / Morph filters, so those exotic E4XT types have no exact XPM type and
# are reverse-mapped to the closest available (lossy — flagged inline).  The
# E4XT Vocal filters do correspond to XPM Vocal-formant types.
_E4B_TO_XPM_FILTER_TYPE = {
    0x00: 3,   # 4-pole LP  → Low 4  (exact match)
    0x01: 2,   # 2-pole LP  → Low 2  (exact match; also MPC3000 LPF)
    0x02: 4,   # 6-pole LP  → Low 6  (exact match, hardware-confirmed)
    0x08: 7,   # 2nd-ord HP → High 2 (exact match)
    0x09: 8,   # 4th-ord HP → High 4 (exact match)
    0x10: 11,  # 2nd-ord BP → Band 2 (exact match)
    0x11: 12,  # 4th-ord BP → Band 4 (many-to-one: also Band 6/8, BB 4-8P)
    0x12: 15,  # Contrary BP → BS 2P notch (closest; also BS 4-8P)
    0x20: 3, 0x21: 3, 0x22: 3,   # Swept EQ → BB(19)/BS(15) by gain sign (see below); ~flat→Low4
    0x40: 3, 0x41: 3, 0x42: 3,   # Phaser 1/2/Bat → Low 4 (no XPM equiv, lossy)
    0x48: 3,                     # Flanger Lite   → Low 4 (no XPM equiv, lossy)
    0x50: 26, 0x51: 27,          # Vocal Ah-Ay-Ee/Oo-Ah → XPM Vocal-formant
    0x60: 3, 0x61: 3, 0x62: 3,   # EQ-Morph types → Low 4 (no XPM equiv, lossy)
    0x68: 3,                     # Peak/Shelf Morph → Low 4 (no XPM equiv, lossy)
}

_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
_NOTE_RE = re.compile(r'_([A-G]#?)(-?\d+)$')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_name(raw: bytes) -> str:
    return raw.decode('ascii', errors='replace').rstrip()


def _decode_root_and_name(display_name: str) -> tuple:
    """Invert _sample_display_name(): strip the '_NoteOctave' suffix.

    Returns (base_name, root_note).  If no suffix, returns (display_name, 60).
    """
    m = _NOTE_RE.search(display_name)
    if m:
        try:
            note_idx = _NOTE_NAMES.index(m.group(1))
            octave = int(m.group(2))
            root_note = (octave + 2) * 12 + note_idx
            if 0 <= root_note <= 127:
                return display_name[:m.start()], root_note
        except (ValueError, IndexError):
            pass
    return display_name, 60


# CR-13: envelope rate↔time + level↔byte math now lives in models.common
# (single home shared with writers/e4b_writer.py).  Local aliases keep the
# existing _fenv_* call sites readable.
_fenv_level_inv = env_byte_to_level
_fenv_rate_inv  = env_rate_to_seconds


# ---------------------------------------------------------------------------
# IFF chunk walker
# ---------------------------------------------------------------------------

def _walk_chunks(data: bytes):
    """Yield (tag, body) for each IFF chunk in a FORM E4B0 stream.

    Validates the FORM/E4B0 header and iterates the inner chunks.
    """
    if len(data) < 12:
        raise ValueError("File too short to be a FORM E4B0 container")
    if data[0:4] != FORM_MAGIC:
        raise ValueError(f"Not an IFF FORM file (got {data[0:4]!r})")
    if data[8:12] != FORM_TYPE:
        raise ValueError(f"Not a FORM E4B0 bank (got {data[8:12]!r})")

    form_size = struct.unpack_from('>I', data, 4)[0]
    end = min(12 + form_size, len(data))
    pos = 12
    while pos + 8 <= end:
        tag  = data[pos:pos+4]
        size = struct.unpack_from('>I', data, pos+4)[0]
        body = data[pos+8:pos+8+size]
        pos += 8 + size
        if size % 2:
            pos += 1
        yield tag, body


# ---------------------------------------------------------------------------
# Sample body parser
# ---------------------------------------------------------------------------

def _parse_sample_body(body: bytes) -> tuple:
    """Parse an E3S1 chunk body into (sample_idx, display_name, SampleData).

    Returns the raw display_name separately so the caller can apply
    collision-avoidance naming when multiple samples share the same base name
    (e.g. when the original name was truncated to make room for the note suffix).
    Exact inverse of _build_sample_body() in writers/e4b_writer.py.
    """
    if len(body) < SAMP_HDR:
        raise ValueError(f"E3S1 body too short: {len(body)} < {SAMP_HDR}")

    sample_idx   = struct.unpack_from('>H', body, 0)[0]
    display_name = _decode_name(body[2:18])
    base_name, root_note = _decode_root_and_name(display_name)

    sample_rate  = struct.unpack_from('<I', body, 54)[0]
    options      = struct.unpack_from('<H', body, 60)[0]

    # The E4B sample struct is the Emulator III's, which stores every position
    # TWICE (once per channel: start/end/loop-start/loop-end at offsets
    # 22/30/38/46 for the left channel, 26/34/42/50 for the right). A sample
    # object holding only its RIGHT channel (options bit 0x0020 clear) keeps
    # its real positions in the SECOND field of each pair and leaves the first
    # with a stale value that doesn't address this sample at all — reading the
    # left field unconditionally can produce an outright invalid loop point.
    # Cross-referenced against ConvertWithMoss PR #242; corpus-checked
    # 2026-07-28 against 141 local third-party .e4b files: 6 of 73 looped
    # "right-channel-only" samples have a negative (nonsensical) loop_start
    # under the unconditional left-field read, all valid once read via the
    # correct field per this bit.
    has_left_channel  = bool(options & 0x0020)
    has_right_channel = bool(options & 0x0040)
    is_stereo = has_left_channel and has_right_channel

    STRUCT_SZ = 92

    if is_stereo:
        # BOTH channel bits set = one object carrying both channels, with the
        # two PCM blocks stored SEQUENTIALLY (all of left, then all of right)
        # and addressed by the L/R halves of each position pair. Corpus-RE'd
        # 2026-07-29 over 473 local .E4B files: 4803 of 20383 sample objects
        # (23.6%) are stereo this way, e.g. "a stereo slide sample" with
        # startL=92 endL=154458 / startR=154460 endR=308826 over 308736 PCM
        # bytes -- two equal 154368-byte blocks, and per-channel loop points
        # (lsL=104 is 12 bytes into left, lsR=154472 is 12 bytes into right).
        #
        # Previously this whole region was read as ONE mono block, so a
        # stereo sample imported at double length and played left-then-right.
        start_l, start_r = struct.unpack_from('<II', body, 22)
        end_l,   end_r   = struct.unpack_from('<II', body, 30)
        loop_start_l = struct.unpack_from('<I', body, 38)[0]
        loop_end_l   = struct.unpack_from('<I', body, 46)[0]

        # A position `p` addresses body offset `p + 2` (the 2-byte sample_idx
        # prefix sits in front of the 92-byte header); `end` is inclusive of
        # its own 2-byte frame.
        left  = body[start_l + 2: end_l + 4]
        right = body[start_r + 2: end_r + 4]
        n_frames = min(len(left), len(right)) // 2
        # mpc2emu's internal PCM is INTERLEAVED (every processor computes
        # frames as len(data) // (2 * channels)), so de-planarise here.
        inter = bytearray(n_frames * 4)
        inter[0::4] = left[0:n_frames * 2:2]
        inter[1::4] = left[1:n_frames * 2:2]
        inter[2::4] = right[0:n_frames * 2:2]
        inter[3::4] = right[1:n_frames * 2:2]
        pcm = bytes(inter)
        channels = 2
        loop_base = start_l
    else:
        # A sample object holding only its RIGHT channel (bit 0x0020 clear)
        # keeps its real positions in the SECOND field of each pair and leaves
        # the first with a stale value that doesn't address this sample at all
        # — reading the left field unconditionally can produce an outright
        # invalid loop point. Cross-referenced against ConvertWithMoss PR #242;
        # corpus-checked 2026-07-28 against 141 local third-party .e4b files:
        # 6 of 73 looped "right-channel-only" samples have a negative
        # (nonsensical) loop_start under the unconditional left-field read, all
        # valid once read via the correct field per this bit.
        loop_start_off = 38 if has_left_channel else 42
        loop_end_off   = 46 if has_left_channel else 50
        loop_start_l = struct.unpack_from('<I', body, loop_start_off)[0]
        loop_end_l   = struct.unpack_from('<I', body, loop_end_off)[0]
        pcm = body[SAMP_HDR:]
        n_frames = len(pcm) // 2   # 16-bit mono
        channels = 1
        loop_base = STRUCT_SZ

    has_loop = bool(options & 0x0001)
    if has_loop:
        loop_type  = LoopType.FORWARD
        loop_start = (loop_start_l - loop_base) // 2
        # On-disk loop_end_l stores the frame BEFORE the true inclusive last
        # loop frame — e4b_writer._build_sample_header encodes the matching
        # `-1` so this stays an exact inverse of our own output. Cross-
        # referenced against ConvertWithMoss's independent E4B reader (PR
        # #220 commit 2ccefea), which measured the loop-seam amplitude step
        # across a real commercial corpus and found this +1 correction takes
        # clean seams from 78% to 95% and eliminates seams stepping by more
        # than a third of the peak amplitude.
        loop_end   = min((loop_end_l - loop_base) // 2 + 1, max(0, n_frames - 1))
    else:
        loop_type  = LoopType.NO_LOOP
        loop_start = 0
        loop_end   = 0

    sample = SampleData(
        name        = base_name,
        data        = bytes(pcm),
        sample_rate = sample_rate,
        channels    = channels,
        bit_depth   = 16,
        loop_type   = loop_type,
        loop_start  = loop_start,
        loop_end    = loop_end,
        root_note   = root_note,
    )
    return sample_idx, display_name, sample


# ---------------------------------------------------------------------------
# Voice block parser
# ---------------------------------------------------------------------------

def _parse_voice(data: bytes, idx_to_name: dict) -> tuple:
    """Parse one voice block from data[0:].

    Returns (VoiceLayer, consumed_bytes) where consumed_bytes does NOT
    include the 2-byte last-voice trailer — the caller adds +2 for the
    last voice in a preset (mirroring how _build_voice writes it).
    """
    if len(data) < VOICE_FIXED:
        raise ValueError(f"Voice data too short: {len(data)} < {VOICE_FIXED}")

    vpar = data[0:110]
    pzt  = data[110:174]   # primary zone table (64 bytes)

    trailer_off = struct.unpack_from('>H', vpar, 2)[0]
    n_zones     = (trailer_off - VOICE_FIXED) // ZONE_ENTRY

    non_transpose    = (vpar[38] == 0x01)
    # Per-voice tuning (hardware-RE'd 2026-06-13 from RE_SUITE CT JL.E4B):
    #   vpar[34] = Key Transpose  (signed byte, semitones)
    #   vpar[35] = Coarse Tune    (signed byte, semitones; repitches sample)
    #   vpar[36] = Fine Tune      (signed byte, 1/64-semitone units → cents = val*100/64)
    v_transpose      = vpar[34] - 256 if vpar[34] > 127 else vpar[34]
    v_coarse_tune    = vpar[35] - 256 if vpar[35] > 127 else vpar[35]
    v_fine_tune      = round((vpar[36] - 256 if vpar[36] > 127 else vpar[36]) * 100 / 64)
    # Per-voice Volume/Pan (hardware-RE'd 2026-07-26, see writers/e4b_writer.py
    # _build_voice): vpar[54] = Volume (signed byte, dB), vpar[55] = Pan
    # (signed byte, -64=full-L..+63=full-R). Only meaningful for a
    # single-zone voice — a multi-zone voice ignores these and uses each
    # zone's own absolute value instead (see the zone loop below).
    # Same inverse requirement as the cutoff above: vpar[54] is the corrected
    # byte, not the dB value, so decode it through the measured volume law.
    v_volume         = e4xt_byte_to_volume_db(
        vpar[54] - 256 if vpar[54] > 127 else vpar[54])
    v_pan            = max(-1.0, min(1.0, (vpar[55] - 256 if vpar[55] > 127 else vpar[55]) / 64.0))
    chorus_amount    = vpar[42] / 127.0   # Chorus Amount: 0-127 -> 0.0-1.0 (see _build_voice)
    filter_byte      = vpar[58]
    # vpar[60] holds a HARDWARE-CORRECTED byte (writers/e4b_writer.py applies
    # the measured E4XT cutoff law), so it must be inverted back to the shared
    # nominal position here -- otherwise parser and writer stop being inverses
    # and an E4B->E4B conversion applies the correction twice. See §E4BFILTCAL.
    filter_cutoff    = e4xt_cutoff_byte_to_position(vpar[60])
    filter_resonance = vpar[61] / 127.0
    if filter_byte in (0x20, 0x21, 0x22):
        # Swept EQ 1-oct = parametric band gain; vpar[61] is GAIN, not Q
        # (gain_dB=(byte-64)*0.375).  Recover band-BOOST (BB) vs band-STOP (BS)
        # from the sign so the round-trip restores a parametric boost (KRZ PARA
        # MID) / notch instead of collapsing to a plain lowpass.  resonance is
        # back-derived so the writers reproduce the same ±dB (see e4b/krz writers).
        gain_db = (vpar[61] - 64) * 0.375
        if gain_db > 1.0:                       # boost  → BB 2P (band-boost)
            filter_type      = 19
            filter_resonance = max(0.0, min(1.0, (gain_db - 12.0) / 12.0))
        elif gain_db < -1.0:                    # cut    → BS 2P (band-stop/notch)
            filter_type      = 15
            filter_resonance = max(0.0, min(1.0, (-gain_db - 12.0) / 12.0))
        else:                                   # ~flat  → no useful EQ, nearest LP
            filter_type      = _E4B_TO_XPM_FILTER_TYPE.get(filter_byte, 0)
    else:
        filter_type      = _E4B_TO_XPM_FILTER_TYPE.get(filter_byte, 0)

    # Mod cords into Filter-Freq (voice[190:270]).  Each cord amount is a signed
    # byte → ±1.0.  The filter-env SHAPE is at PZT[14:26] but its depth/sign is
    # the FilterEnv→FilterFreq cord ("Cord 05", mod offset 22).
    fenv_raw = pzt[14:26]
    mod_region = data[VOICE_MOD_OFF:VOICE_MOD_OFF + 80] if len(data) >= VOICE_MOD_OFF + 27 else b''
    _cord = lambda off: (cord_byte_to_amount(mod_region[off]) if mod_region else 0.0)
    cord_amt = mod_region[_MOD_FENV_TO_CUTOFF_AMT] if mod_region else 0
    filter_keytrack    = _cord(_MOD_KEY_TO_CUTOFF_AMT)
    velocity_to_filter = _cord(_MOD_VEL_TO_CUTOFF_AMT)
    # LFO→dest cords + mod-wheel→LFO-depth gate reconstruction (inverse of
    # e4b_writer: each LFO cord depth D is split into static D*(1-Kw) + a
    # ModWheel→CordN-Amount cord of D*Kw).  Recover the full depth (static+gate)
    # and the common wheel ratio Kw.  LFO1→Pitch is at the fixed slot 2; the
    # other routings live in free slots, found by (src, dst).
    def _cord_slot(src, dst):
        for s in range(20):
            o = s * 4
            if o + 1 < len(mod_region) and mod_region[o] == src and mod_region[o + 1] == dst:
                return s
        return -1

    def _gate_byte(slot):
        """Raw amount byte of the ModWheel→CordN-Amount gate for cord `slot`."""
        if slot < 0:
            return 0
        want = _CORD_AMT_DEST_BASE + slot
        for s in range(20):
            o = s * 4
            if o + 2 < len(mod_region) and mod_region[o] == _SRC_MOD_WHEEL and mod_region[o + 1] == want:
                return mod_region[o + 2]
        return 0

    # (attr, src, dst, fixed_slot-or-None) for every LFO routing
    _lfo_defs = [
        ('lfo1_to_pitch',    0x60, 0x30, _MOD_LFO_TO_PITCH_SLOT),
        ('lfo1_to_filter',   _MOD_LFO1_TO_FILTER[0],   _MOD_LFO1_TO_FILTER[1],   None),
        ('lfo1_to_filter_q', _MOD_LFO1_TO_FILTER_Q[0], _MOD_LFO1_TO_FILTER_Q[1], None),
        ('lfo2_to_pitch',    _MOD_LFO2_TO_PITCH[0],    _MOD_LFO2_TO_PITCH[1],    None),
        ('lfo2_to_filter',   _MOD_LFO2_TO_FILTER[0],   _MOD_LFO2_TO_FILTER[1],   None),
        ('lfo2_to_filter_q', _MOD_LFO2_TO_FILTER_Q[0], _MOD_LFO2_TO_FILTER_Q[1], None),
    ]
    _routes = {}   # attr -> (full_depth, static, gate)
    for _attr, _src, _dst, _fixed in _lfo_defs:
        _slot = _fixed if _fixed is not None else _cord_slot(_src, _dst)
        _static = (cord_byte_to_amount(mod_region[_slot * 4 + 2])
                   if (_slot >= 0 and _slot * 4 + 2 < len(mod_region)) else 0.0)
        _gb = _gate_byte(_slot)
        if _slot == _MOD_LFO_TO_PITCH_SLOT and _gb == _MOD_WHEEL_GATE_DEFAULT:
            _gb = 0   # EOS template default ModWheel→C02Amt, not a real gate
        _gate = cord_byte_to_amount(_gb)
        _routes[_attr] = (_static + _gate, _static, _gate)

    # Engage gating only when every active LFO routing is gated with one shared
    # ratio (our writer gates uniformly); otherwise read the static amounts (the
    # template's default cord then round-trips byte-for-byte via the writer).
    _active = {a: v for a, v in _routes.items() if abs(v[0]) > 0.01}
    _gated  = {a: v for a, v in _active.items() if abs(v[2]) > 0.004}
    wheel_to_lfo = 0.0
    _use_full = False
    if _gated and len(_gated) == len(_active):
        _ratios = [g / f for (f, s, g) in _gated.values() if abs(f) > 1e-6]
        if _ratios and (max(_ratios) - min(_ratios) <= 0.05):
            wheel_to_lfo = max(0.0, min(1.0, sum(_ratios) / len(_ratios)))
            _use_full = True
    _depth = (lambda a: _routes[a][0]) if _use_full else (lambda a: _routes[a][1])
    lfo1_to_pitch    = _depth('lfo1_to_pitch')
    lfo1_to_filter   = _depth('lfo1_to_filter')
    lfo1_to_filter_q = _depth('lfo1_to_filter_q')
    lfo2_to_pitch    = _depth('lfo2_to_pitch')
    lfo2_to_filter   = _depth('lfo2_to_filter')
    lfo2_to_filter_q = _depth('lfo2_to_filter_q')

    # LFO1 (PZT[42:46]) + LFO2 (PZT[50:54]) — hardware-RE'd 2026-06-10 (B.011).
    lfo1_rate      = lfo_rate_byte_to_hz(pzt[42])
    lfo1_shape     = _LFO_SHAPE_NAME.get(pzt[43], 'triangle')
    lfo1_delay     = pzt[44] / 127.0 * _LFO_DELAY_MAX_S
    lfo1_variation = pzt[45] / 127.0
    lfo1_sync      = (pzt[46] == 0x01)
    lfo2_rate      = lfo_rate_byte_to_hz(pzt[50])
    lfo2_shape     = _LFO_SHAPE_NAME.get(pzt[51], 'triangle')
    lfo2_delay     = pzt[52] / 127.0 * _LFO_DELAY_MAX_S
    lfo2_variation = pzt[53] / 127.0
    lfo2_sync      = (pzt[54] == 0x01)

    # CR-5 / CWM PR #242 cross-reference (2026-07-28): amp envelope (PZT[0:12])
    # — inverse of _build_voice's 6-stage write. The 6 (rate,level) stages are
    # Attack1/Attack2/Decay1/Decay2/Release1/Release2 (bytes 0-11), the SAME
    # envelope shape as the Emulator X per ConvertWithMoss's independent RE.
    # Attack1-only was CR-5's original fix (without it, parsed voices fell
    # back to dataclass defaults, silently discarding the source envelope on
    # E4B→E4B re-bank/resample/zone-reduce) — but reading only stage 1 of each
    # pair drops the second stage entirely. Corpus-checked against 141 local
    # third-party .e4b files (32,558 voices) before applying this: the second
    # stage has a nonzero TIME in only ~1-2% of voices (attack2 1.1%, decay2
    # 1.6%, release2 0.2%) — usually negligible — but where decay2's LEVEL
    # differs sharply from decay1's (0.9% of voices, concentrated in one-shot
    # SFX content — e.g. a "a commercial SFX library the SFX bank" bank's laser/explosion/dialogue
    # hits), decay1 alone reports "holds near-full forever" when the real
    # envelope decays to silence over decay1+decay2's combined time (one
    # measured case: decay1 rate byte 0 = 31ms read as the whole decay, vs.
    # the real decay2 tail of 29.4s) — exactly the "Nylon Guitar"-style bug
    # ConvertWithMoss also found (their corpus: 52% benefit from combining
    # decay1+decay2, 8% would otherwise "sustain forever"). Fixed: sum each
    # pair's two stage TIMES (attack1+attack2, decay1+decay2, release1+
    # release2) and read SUSTAIN from decay2's level (not decay1's) — for our
    # 4-stage Envelope model (no separate hold field), summing both decay
    # sub-stages is equivalent to CWM's hold+decay split, since a plateau
    # (decay1 holding at attack2's level) or a true decay both need the SAME
    # total decay1+decay2 duration to reach whatever decay2's level is.
    # A stage byte of 0 is a deliberate "unused/instant" encoding (matches
    # writers/e4b_writer.py's env_seconds_to_rate(0.0) == 0), not literally
    # 0.031s (the continuous rate curve's floor) — so the second stage of
    # each pair only contributes real time when its own byte is nonzero,
    # keeping single-stage envelopes (the vast majority) byte-for-byte
    # unchanged from the original CR-5 behavior.
    def _stage2_seconds(rate_byte: int) -> float:
        return 0.0 if rate_byte == 0 else _fenv_rate_inv(rate_byte)

    env_attack  = _fenv_rate_inv(pzt[0]) + _stage2_seconds(pzt[2])
    env_decay   = _fenv_rate_inv(pzt[4]) + _stage2_seconds(pzt[6])
    env_release = _fenv_rate_inv(pzt[8]) + _stage2_seconds(pzt[10])
    env_sustain = max(0.0, min(1.0, _fenv_level_inv(pzt[7])))

    # Depth/sign from the cord amount (0 when the FilterEnv→Filter cord is 0).
    filter_env_amount = cord_byte_to_amount(cord_amt)
    if fenv_raw == _PZT_FENV_DEFAULT:
        # EOS template-default env (third-party files / never-set) → dataclass
        # defaults so it round-trips cleanly.
        filter_env_attack  = 0.0
        filter_env_decay   = 0.3
        filter_env_sustain = 1.0
        filter_env_release = 0.0
    else:
        # Read the env SHAPE even when amount==0 (§O: e4b_writer always writes the
        # filter-env shape), so the source curve survives an E4B→E4B repack.
        # Same 2-stage-pair combination as the amp envelope above.
        filter_env_attack  = _fenv_rate_inv(fenv_raw[0]) + _stage2_seconds(fenv_raw[2])
        filter_env_decay   = _fenv_rate_inv(fenv_raw[4]) + _stage2_seconds(fenv_raw[6])
        filter_env_release = _fenv_rate_inv(fenv_raw[8]) + _stage2_seconds(fenv_raw[10])
        # Decay2 level byte = sustain (levels are full-scale).
        filter_env_sustain = max(0.0, min(1.0, _fenv_level_inv(fenv_raw[7])))

    # Voice-level key/velocity window — vpar[14]/[17] (key), vpar[18]/[21]
    # (velocity), hardware-RE'd 2026-06-14 (writers/e4b_writer.py, RE_SUITE2
    # VOICE KEYWIN). mpc2emu's own writer always sets this to the min/max of
    # the voice's own zones, so intersecting is a no-op on our own output —
    # but real-world commercial banks commonly leave the ZONE entry wide open
    # at 0-127 and do the actual key/velocity split at the VOICE level only
    # (cross-referenced against ConvertWithMoss's independent E4B reader,
    # PR #220 commit ead0e07, validated against 76057 real zones). Without
    # this intersection, such a voice's samples all map across the whole
    # keyboard/velocity range instead of their real window.
    voice_key_lo = vpar[14]
    voice_key_hi = vpar[17]
    voice_vel_lo = vpar[18]
    voice_vel_hi = vpar[21]

    # Secondary zone table starts at VOICE_FIXED
    zones = []
    for i in range(n_zones):
        off   = VOICE_FIXED + i * ZONE_ENTRY
        entry = data[off:off + ZONE_ENTRY]
        if len(entry) < ZONE_ENTRY:
            break
        lo_key = max(voice_key_lo, entry[2])
        hi_key = min(voice_key_hi, entry[5])
        lo_vel = max(voice_vel_lo, entry[6])
        hi_vel = min(voice_vel_hi, entry[9])
        if lo_key > hi_key or lo_vel > hi_vel:
            # Voice and zone windows don't overlap at all — a dead zone
            # (malformed/leftover entry); skip rather than emit an inverted
            # range downstream writers don't expect.
            continue
        sample_idx = struct.unpack_from('>H', entry, 10)[0]
        root_key   = entry[14]
        sname      = idx_to_name.get(sample_idx, '')
        if n_zones > 1:
            # Multi-zone voice: each zone's ABSOLUTE fine-tune/volume/pan,
            # read directly from its own entry — NOT a delta on top of the
            # voice's vpar[36]/[54]/[55] (that model was tried and disproven
            # 2026-07-26: a hardware differential save with genuinely
            # asymmetric zone volumes still wrote vpar[54]=0, and a from-
            # scratch bank built by this exact writer/parser pair confirmed
            # the front panel displays each zone's raw entry value, not a
            # voice+delta sum). vpar[36]/[54]/[55] are ignored here — the
            # writer leaves them at 0 for a multi-zone voice (see
            # writers/e4b_writer.py._build_voice).
            zone_fine_tune = round(struct.unpack_from('>h', entry, 12)[0] * 100.0 / 64.0)
            zone_volume    = e4xt_byte_to_volume_db(entry[15] - 256 if entry[15] > 127 else entry[15])
            zone_pan       = max(-1.0, min(1.0, (entry[16] - 256 if entry[16] > 127 else entry[16]) / 64.0))
        else:
            # Single-zone voice: the voice's own vpar[36]/[54]/[55]
            # (hardware-confirmed 2026-07-26, see writers/e4b_writer.py).
            zone_fine_tune = v_fine_tune
            zone_volume    = v_volume
            zone_pan       = v_pan
        zones.append(ZoneMapping(
            sample_name = sname,
            lo_key      = lo_key,
            hi_key      = hi_key,
            lo_vel      = lo_vel,
            hi_vel      = hi_vel,
            root_key    = root_key,
            transpose   = v_transpose,
            coarse_tune = v_coarse_tune,
            fine_tune   = zone_fine_tune,
            volume      = zone_volume,
            pan         = zone_pan,
        ))

    voice = VoiceLayer(
        zones              = zones,
        non_transpose      = non_transpose,
        chorus_amount      = chorus_amount,
        amp_env            = Envelope(env_attack, env_decay, env_sustain, env_release),
        filter_env         = Envelope(filter_env_attack, filter_env_decay,
                                      filter_env_sustain, filter_env_release),
        filter_type        = filter_type,
        filter_cutoff      = filter_cutoff,
        filter_resonance   = filter_resonance,
        filter_env_amount  = filter_env_amount,
        filter_keytrack    = filter_keytrack,
        velocity_to_filter = velocity_to_filter,
        lfo1_rate          = lfo1_rate,
        lfo1_shape         = lfo1_shape,
        lfo1_delay         = lfo1_delay,
        lfo1_variation     = lfo1_variation,
        lfo1_sync          = lfo1_sync,
        lfo2_rate          = lfo2_rate,
        lfo2_shape         = lfo2_shape,
        lfo2_delay         = lfo2_delay,
        lfo2_variation     = lfo2_variation,
        lfo2_sync          = lfo2_sync,
        lfo1_to_pitch      = lfo1_to_pitch,
        lfo1_to_filter     = lfo1_to_filter,
        lfo1_to_filter_q   = lfo1_to_filter_q,
        lfo2_to_pitch      = lfo2_to_pitch,
        lfo2_to_filter     = lfo2_to_filter,
        lfo2_to_filter_q   = lfo2_to_filter_q,
        wheel_to_lfo       = wheel_to_lfo,
    )
    consumed = VOICE_FIXED + n_zones * ZONE_ENTRY
    return voice, consumed


# ---------------------------------------------------------------------------
# Preset body parser
# ---------------------------------------------------------------------------

def _parse_preset_body(body: bytes, idx_to_name: dict) -> Preset:
    """Parse an E4P1 chunk body into a Preset.

    Inverse of _build_preset_body() in writers/e4b_writer.py.
    """
    if len(body) < PRES_HDR:
        raise ValueError(f"E4P1 body too short: {len(body)} < {PRES_HDR}")

    name       = _decode_name(body[2:18])
    num_voices = struct.unpack_from('>H', body, 20)[0]

    voices = []
    offset = PRES_HDR
    for i in range(num_voices):
        voice, consumed = _parse_voice(body[offset:], idx_to_name)
        voices.append(voice)
        offset += consumed
        if i == num_voices - 1:
            offset += 2   # last voice has a 2-byte trailing zero marker

    return Preset(name=name, voices=voices)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_e4b(path: str) -> Bank:
    """Parse an .E4B file and return a Bank.

    Walks the FORM E4B0 IFF container sequentially (does not trust TOC1
    offsets — more robust against third-party files).  E4Ma and TOC1 chunks
    are silently ignored; they will be rebuilt correctly by write_e4b().
    """
    print(f"Parsing E4B: {path}")
    data = Path(path).read_bytes()

    sample_chunks: list = []
    preset_chunks: list = []

    for tag, body in _walk_chunks(data):
        if tag == SAMP_TAG:
            sample_chunks.append(body)
        elif tag == PRES_TAG:
            preset_chunks.append(body)

    # Build sample list + index map (sample_idx → unique name).
    # When multiple samples share the same base name (because the original was
    # truncated to fit the _NoteOctave display suffix), fall back to the full
    # display name which includes the unique note suffix.  Our own output uses
    # short synthetic names (e.g. "R000") that never collide, so those round-
    # trip identically; this path only activates for third-party content.
    raw_samples: list = []
    for body in sample_chunks:
        try:
            sample_idx, display_name, sample = _parse_sample_body(body)
        except (ValueError, struct.error) as exc:
            print(f"  [WARN] Skipping malformed E3S1 chunk: {exc}")
            continue
        raw_samples.append((sample_idx, display_name, sample))

    all_names: set = set()
    samples: list = []
    idx_to_name: dict = {}
    for sample_idx, display_name, sample in raw_samples:
        # 1st priority: base name (suffix-stripped) — exact round-trip for our own files.
        # 2nd priority: full display name — unique when only the base truncated.
        # 3rd priority: display prefix + sample_idx — unique when display names also
        #   repeat (e.g. velocity layers at the same pitch in a multi-layer piano bank).
        candidate = sample.name
        if candidate in all_names:
            candidate = display_name
        if candidate in all_names:
            candidate = (display_name[:12] + f"{sample_idx:04d}")[:MAX_NAME]
        sample.name = candidate
        all_names.add(candidate)
        idx_to_name[sample_idx] = sample.name
        samples.append(sample)

    # Build preset list
    presets: list = []
    for body in preset_chunks:
        try:
            preset = _parse_preset_body(body, idx_to_name)
        except (ValueError, struct.error) as exc:
            print(f"  [WARN] Skipping malformed E4P1 chunk: {exc}")
            continue
        presets.append(preset)

    bank_name = Path(path).stem[:MAX_NAME]
    bank = Bank(name=bank_name, presets=presets, samples=samples)

    n_zones = sum(len(v.zones) for p in presets for v in p.voices)
    print(f"  {len(presets)} preset(s), {len(samples)} sample(s), "
          f"{n_zones} zone(s) total")
    return bank
