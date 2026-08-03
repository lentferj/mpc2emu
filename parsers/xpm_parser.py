# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
#
# This file is part of mpc2emu.
# Original work. No third-party source code used.
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
Akai MPC XPM Program Parser
----------------------------
XPM is XML-based (MPC 2.x / MPC X / MPC Live / MPC One).
Parses Instruments > Keygroup > Layer structure into internal Bank model.

Older MPC formats (PGM) are binary and handled separately (not yet implemented).
"""

import array
import collections
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import sys
import struct

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType, lfo_knob_to_hz,
    cap_voices_by_coverage, stereo_to_mono, hz_to_e4b_cutoff,
)


# MPC LFO <Type> string → canonical E4B shape name (substring match; MPC ships
# Sine / Triangle / Saw Up / Saw Down / Square / S&H).
def _xpm_lfo_shape(type_str: str) -> str:
    t = (type_str or '').lower()
    if 'sine' in t:                                   return 'sine'
    if 'tri' in t:                                    return 'triangle'
    if 'saw' in t:                                    return 'sawtooth'
    if 'squ' in t or 'puls' in t:                     return 'square'
    # MPC Sample & Hold ('SampHold') → E4XT Hemi-quaver (a regular stepped
    # pattern), which matches a *tempo-synced* S&H better than the truly-random
    # 'random' wave (Jan's hardware A/B, 2026-06-13; see docs/aural_notes.md §Q).
    if 'samp' in t or 's&h' in t or 'hold' in t:      return 'hemiquaver'
    if 'random' in t or 'noise' in t:                 return 'random'
    return 'triangle'


# MPC LFO <Sync> index → tempo division (hardware-read on an MPC One, 2026-06-14,
# from the "Canedrive Analogue Synths" expansion).  0 = free (use <Rate>).
# (18 = 3 whole and 14 = 32nd are inferred — the only two not seen in the wild.)
_MPC_SYNC_DIV = {
    0:  'free',
    1:  'whole',          2:  'dotted_half',     3:  'half',
    4:  'dotted_quarter', 5:  'half_triplet',    6:  'quarter',
    7:  'dotted_eighth',  8:  'quarter_triplet', 9:  'eighth',
    10: 'dotted_16th',    11: 'eighth_triplet',  12: 'sixteenth',
    13: '16th_triplet',   14: 'thirty_second',   15: '8_whole',
    16: '6_whole',        17: '4_whole',         18: '3_whole',
    19: '2_whole',        20: 'dotted_whole',
}

# Division length in quarter-note beats (for computing the synced LFO rate).
_MPC_SYNC_BEATS = {
    1: 4, 2: 3, 3: 2, 4: 1.5, 5: 4/3, 6: 1, 7: 0.75, 8: 2/3, 9: 0.5,
    10: 0.375, 11: 1/3, 12: 0.25, 13: 1/6, 14: 0.125,
    15: 32, 16: 24, 17: 16, 18: 12, 19: 8, 20: 6,
}
_E4XT_LFO_MIN_HZ, _E4XT_LFO_MAX_HZ = 0.08, 18.01

# Reference tempo for reproducing tempo-synced LFOs as a fixed rate.  The BPM
# lives in the MPC *project*, not the XPM, so 120 (the DAW/MPC new-project
# default) is assumed; convert.py overrides it via --lfo-sync-bpm.
SYNC_BPM = 120.0

def _mpc_sync_hz(div: int, bpm: float = None):
    """LFO rate (Hz) for an MPC tempo-sync division at `bpm` (default 120).

    EOS can't tempo-FOLLOW a sync (clock divisor is straight-only and the LFO
    rate is a fixed Hz), so a synced MPC LFO — which the MPC stores at the
    useless default <Rate>=0.5 — is reproduced as a fixed rate at the division's
    speed.  Correct at a normal tempo; a static snapshot, not a live lock."""
    beats = _MPC_SYNC_BEATS.get(div)
    if not beats:
        return None
    if bpm is None:
        bpm = SYNC_BPM
    hz = (bpm / 60.0) / beats        # cycles/sec = (quarter-beats/sec) / (beats/cycle)
    return max(_E4XT_LFO_MIN_HZ, min(_E4XT_LFO_MAX_HZ, hz))


# ---------------------------------------------------------------------------
# MPC envelope value → seconds
# ---------------------------------------------------------------------------
# MPC keygroup envelope *times* (VolumeAttack/Decay/Release, FilterAttack/
# Decay/Release) are normalised 0.0–1.0 controls, NOT seconds.  Both firmware
# generations use the same exponential form with different constants, so the
# two paths carry their own — see docs/RESOLUTION_NOTES.md §MPCENV.
#
# 2.x: hardware-measured on an MPC One (2026-06-09, XPM_VOL_DECAY), 1.0 ≈ 14 s.
_XPM_ENV_A = 0.00079
_XPM_ENV_K = 9.78

# 3.x: measured on an MPC One running 3.9.0.31 (2026-08-03) by reading the
# firmware's own millisecond display against the dial's 128 detents -- each
# detent is one n/127 step.  Five points from 3.7 ms to 30 s fit to within
# 0.56%, and n=96 was predicted before measuring to +0.08%:
#
#     n=16 -> 3.7 ms   n=32 -> 13.4 ms   n=64 -> 180.4 ms
#     n=96 -> 2.42 s   n=127 -> 30.0 s
#
# The displayed number is the time to SILENCE, confirmed acoustically at both
# ends of the scale.  Attack, Decay and Release were each measured and agree
# exactly, so one curve still covers every segment; Hold and Delay are assumed
# to match but were NOT measured.
_XPM3_ENV_A = 0.001005
_XPM3_ENV_K = 10.3022


def _xpm_env_to_seconds(value: float, mpc3: bool = False) -> float:
    """MPC normalised envelope value (0.0–1.0) → time in seconds."""
    v = max(0.0, min(1.0, value))
    if mpc3:
        return _XPM3_ENV_A * math.exp(_XPM3_ENV_K * v)
    return _XPM_ENV_A * math.exp(_XPM_ENV_K * v)


# ---------------------------------------------------------------------------
# MPC 3 filter cutoff → Hz
# ---------------------------------------------------------------------------
# `filterCutoff` is a normalised knob, not a frequency.  Measured on an MPC One
# 3.9.0.31 (2026-08-03) by sweeping the cutoff against band-limited noise and
# fitting the -3 dB corner of each recording -- eight points from 112 Hz to
# 10.6 kHz, max residual 2.6%, with knob 88 predicted before measurement to
# +0.9%.  See docs/RESOLUTION_NOTES.md §MPCCUTOFF.
#
# This replaces ConvertWithMoss's claimed curve (§CUTOFFKNOB), which measured
# 2-6x too high and was never an MPC scale at all.
_XPM3_CUTOFF_F0 = 21.377      # Hz at knob 0
_XPM3_CUTOFF_SPAN = 728.0     # multiplier across the full 0..1 range


def _xpm3_cutoff_to_hz(value: float) -> float:
    """MPC 3 normalised `filterCutoff` (0.0–1.0) → -3 dB corner in Hz."""
    return _XPM3_CUTOFF_F0 * (_XPM3_CUTOFF_SPAN ** max(0.0, min(1.0, value)))


# ---------------------------------------------------------------------------
# WAV loader
# ---------------------------------------------------------------------------

def _read_smpl_loop(wav_bytes: bytes):
    """Scan a WAV file's RIFF chunks for a 'smpl' loop definition.
    Returns (loop_type, loop_start_frame, loop_end_frame) or None.
    WAV loop types: 0=forward, 1=ping-pong, 2=backward."""
    pos = 12  # skip 'RIFF' + size + 'WAVE'
    while pos + 8 <= len(wav_bytes):
        tag = wav_bytes[pos:pos+4]
        sz  = struct.unpack_from('<I', wav_bytes, pos+4)[0]
        if tag == b'smpl':
            n_loops = struct.unpack_from('<I', wav_bytes, pos+36)[0]
            if n_loops >= 1:
                lp        = pos + 44          # first loop entry
                loop_type = struct.unpack_from('<I', wav_bytes, lp+4)[0]
                loop_start= struct.unpack_from('<I', wav_bytes, lp+8)[0]
                loop_end  = struct.unpack_from('<I', wav_bytes, lp+12)[0]
                return loop_type, loop_start, loop_end
            return None
        pos += 8 + sz + (sz & 1)   # word-align
    return None


def _read_smpl_root(wav_bytes: bytes):
    """Return the WAV `smpl` chunk's MIDI unity note (the sample's recorded root),
    or None if absent.  Layout: smpl body = manufacturer(4) product(4)
    samplePeriod(4) **MIDIUnityNote(4)** … → unity at chunk+8+12."""
    pos = 12
    while pos + 8 <= len(wav_bytes):
        tag = wav_bytes[pos:pos+4]
        sz  = struct.unpack_from('<I', wav_bytes, pos+4)[0]
        if tag == b'smpl':
            if pos + 8 + 16 <= len(wav_bytes):
                u = struct.unpack_from('<I', wav_bytes, pos + 8 + 12)[0]
                return u if 0 <= u <= 127 else None
            return None
        pos += 8 + sz + (sz & 1)
    return None


def _read_smpl_pitch_fraction_cents(wav_bytes: bytes):
    """Return the WAV `smpl` chunk's MIDIPitchFraction (fine-tune below the
    unity note) as cents, or None if absent. Layout: MIDIPitchFraction
    immediately follows MIDIUnityNote → chunk+8+16, a u32 fraction of a
    semitone (0 = none, 0xFFFFFFFF = just under +100 cents). Previously not
    read at all -- only the whole-semitone MIDIUnityNote was, so embedded
    fine-tune silently rounded to the nearest semitone (cross-referenced
    against ConvertWithMoss PR #254, which found the same gap)."""
    pos = 12
    while pos + 8 <= len(wav_bytes):
        tag = wav_bytes[pos:pos+4]
        sz  = struct.unpack_from('<I', wav_bytes, pos+4)[0]
        if tag == b'smpl':
            if pos + 8 + 20 <= len(wav_bytes):
                frac = struct.unpack_from('<I', wav_bytes, pos + 8 + 16)[0]
                return round(frac / 4294967296.0 * 100.0)
            return None
        pos += 8 + sz + (sz & 1)
    return None


# ---------------------------------------------------------------------------
# AIFF / AIFF-C loader
# ---------------------------------------------------------------------------

def _aiff_decode_rate(data: bytes) -> int:
    """Decode a 10-byte 80-bit IEEE 754 extended big-endian float → Hz (int)."""
    exp  = ((data[0] & 0x7F) << 8) | data[1]
    mant = int.from_bytes(data[2:10], 'big')
    if exp == 0 and mant == 0:
        return 0
    return round(mant * 2.0 ** (exp - 16383 - 63))


def _be_high2_to_le16(raw: bytes, stride: int) -> bytes:
    """Take the top two bytes of each big-endian `stride`-byte sample as a
    signed 16-bit value, emitted little-endian.

    This is what both downscaling paths reduce to. For 24-bit, dropping the
    low byte IS the 16-bit value: with `b0 < 0x80` the old
    `((b0<<16|b1<<8|b2)) >> 8` is plainly `b0<<8|b1`, and with `b0 >= 0x80`
    the `-0x1000000` sign correction and the floor `>> 8` cancel to exactly
    the same `(b0<<8|b1) - 0x10000`. Same argument for 32-bit with `>> 16`.

    So no arithmetic is needed at all — just a strided copy of the two
    high bytes and one byteswap, instead of an unpack/pack per sample.
    The byteswap is unconditional: on a little-endian host it turns the
    big-endian pairs into correct native values whose `tobytes()` is
    little-endian, and on a big-endian host it converts correct native
    values into their little-endian representation.
    """
    n = len(raw) // stride
    be = bytearray(n * 2)
    be[0::2] = raw[0:n * stride:stride]
    be[1::2] = raw[1:n * stride:stride]
    a = array.array('h')
    a.frombytes(bytes(be))
    a.byteswap()
    return a.tobytes()


def _be24_to_le16(raw: bytes) -> bytes:
    """Convert big-endian 24-bit signed PCM → little-endian 16-bit signed."""
    return _be_high2_to_le16(raw, 3)


def _read_aiff_base_note(data: bytes) -> Optional[int]:
    """Return the INST chunk base note from raw AIFF bytes, or None."""
    if len(data) < 12 or data[:4] != b'FORM' or data[8:12] not in (b'AIFF', b'AIFC'):
        return None
    pos = 12
    while pos + 8 <= len(data):
        ck_id = data[pos:pos+4]
        ck_sz = struct.unpack_from('>I', data, pos+4)[0]
        if ck_id == b'INST' and ck_sz >= 1:
            note = struct.unpack_from('>b', data, pos+8)[0]
            return max(0, min(127, note))
        pos += 8 + ck_sz + (ck_sz & 1)
    return None


def _load_aiff(aiff_path: str, name: str) -> Optional[SampleData]:
    """Load AIFF or AIFF-C (uncompressed / 'sowt') → SampleData (16-bit LE mono).

    Reads COMM (format), SSND (PCM), MARK (loop positions), INST (loop mode +
    base note).  Handles 8/16/24/32-bit and big-endian byte order.  AIFC 'sowt'
    (signed 16-bit little-endian) is also accepted; all other AIFC compression
    types are rejected with a warning."""
    try:
        data = open(aiff_path, 'rb').read()
    except OSError as e:
        print(f"  [ERROR] Could not read AIFF {aiff_path}: {e}")
        return None

    if len(data) < 12 or data[:4] != b'FORM' or data[8:12] not in (b'AIFF', b'AIFC'):
        print(f"  [WARN] Not an AIFF/AIFC file: {aiff_path}")
        return None

    is_aifc     = data[8:12] == b'AIFC'
    compression = b'NONE'
    channels = n_frames = sample_size = sample_rate = None
    ssnd_data   = None
    ssnd_offset = 0
    markers     = {}      # marker_id → frame position
    sustain_loop = None   # (play_mode, begin_id, end_id)
    base_note   = 60

    pos = 12
    while pos + 8 <= len(data):
        ck_id = data[pos:pos+4]
        ck_sz = struct.unpack_from('>I', data, pos+4)[0]
        body  = data[pos+8: pos+8+ck_sz]

        if ck_id == b'COMM' and len(body) >= 18:
            channels    = struct.unpack_from('>h', body, 0)[0]
            n_frames    = struct.unpack_from('>I', body, 2)[0]
            sample_size = struct.unpack_from('>h', body, 6)[0]
            sample_rate = _aiff_decode_rate(body[8:18])
            if is_aifc and len(body) >= 22:
                compression = body[18:22]

        elif ck_id == b'SSND' and len(body) >= 8:
            ssnd_offset = struct.unpack_from('>I', body, 0)[0]
            ssnd_data   = body[8 + ssnd_offset:]

        elif ck_id == b'MARK' and len(body) >= 2:
            n_marks = struct.unpack_from('>H', body, 0)[0]
            mp = 2
            for _ in range(n_marks):
                if mp + 6 > len(body):
                    break
                mk_id  = struct.unpack_from('>h', body, mp)[0]
                mk_pos = struct.unpack_from('>I', body, mp+2)[0]
                plen   = body[mp+6] if mp+6 < len(body) else 0
                markers[mk_id] = mk_pos
                step = 7 + plen         # 6 bytes fixed + 1 plen byte + plen chars
                mp  += step + (step & 1)

        elif ck_id == b'INST' and len(body) >= 14:
            base_note  = max(0, min(127, struct.unpack_from('>b', body, 0)[0]))
            s_mode     = struct.unpack_from('>H', body, 8)[0]
            s_begin    = struct.unpack_from('>h', body, 10)[0]
            s_end      = struct.unpack_from('>h', body, 12)[0]
            if s_mode > 0:
                sustain_loop = (s_mode, s_begin, s_end)

        pos += 8 + ck_sz + (ck_sz & 1)

    if channels is None or ssnd_data is None or sample_rate is None:
        print(f"  [WARN] AIFF missing COMM or SSND: {aiff_path}")
        return None

    # AIFC: check compression type
    already_le = False
    if is_aifc and compression not in (b'NONE', b'    '):
        if compression == b'sowt':
            already_le = True   # signed 16-bit LE — no byte swap needed
        else:
            print(f"  [WARN] Unsupported AIFC compression {compression!r}: {aiff_path}")
            return None

    # Clip to declared frame count, then convert to 16-bit LE
    bps = (sample_size + 7) // 8
    raw = bytes(ssnd_data[:n_frames * channels * bps])

    if sample_size == 8:
        # AIFF 8-bit is signed (unlike WAV's unsigned 8-bit center at 128)
        out = bytearray(len(raw) * 2)
        for i, b in enumerate(raw):
            v = b if b < 128 else b - 256
            struct.pack_into('<h', out, i * 2, v << 8)
        raw, sample_size = bytes(out), 16
    elif sample_size == 16:
        if not already_le:
            import array as _arr
            a = _arr.array('h', raw)
            a.byteswap()
            raw = a.tobytes()
    elif sample_size == 24:
        raw, sample_size = _be24_to_le16(raw), 16
    elif sample_size == 32:
        raw, sample_size = _be_high2_to_le16(raw, 4), 16
    elif sample_size != 16:
        print(f"  [WARN] Unsupported AIFF bit depth {sample_size}: {aiff_path}")
        return None

    # Stereo preserved -- see the note in load_wav.

    # Loop from INST + MARK
    loop_type  = LoopType.NO_LOOP
    loop_start = 0
    loop_end   = 0
    n_pcm = len(raw) // (2 * max(1, channels))   # frames, stereo-aware
    if sustain_loop is not None:
        play_mode, begin_id, end_id = sustain_loop
        if begin_id in markers and end_id in markers:
            ls = markers[begin_id]
            le = min(markers[end_id], n_pcm - 1)
            if ls < le:
                loop_start = ls
                loop_end   = le
                loop_type  = (LoopType.ALTERNATING if play_mode == 2
                               else LoopType.FORWARD)

    safe_name = _safe_name(name, tail=True)
    return SampleData(
        name        = safe_name,
        data        = raw,
        sample_rate = sample_rate,
        channels    = channels,
        bit_depth   = sample_size,
        loop_type   = loop_type,
        loop_start  = loop_start,
        loop_end    = loop_end,
        root_note   = base_note,
    )


# --- RIFF/WAVE container ---------------------------------------------------
#
# The stdlib `wave` module accepts ONLY format code 0x0001 and raises
# `unknown format: N` for everything else, so 32-bit float exports (0x0003)
# and WAVE_FORMAT_EXTENSIBLE (0xFFFE, the usual encoding for 24-bit and
# multichannel WAV) were rejected outright. Both are ordinary DAW and
# sample-library output. See docs/RESOLUTION_NOTES.md §WAVFMT.

_WAVE_FORMAT_PCM        = 0x0001
_WAVE_FORMAT_IEEE_FLOAT = 0x0003
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE

# Ogg-in-WAV: a complete Ogg stream in the data chunk. Rejected deliberately
# rather than mis-read -- decoding it would need a Vorbis decoder.
_WAVE_FORMAT_OGG = frozenset(range(0x674F, 0x6752)) | frozenset(range(0x676F, 0x6772))


def _parse_wav_chunks(raw: bytes) -> tuple:
    """Walk a RIFF/WAVE file and return
    ``(format_code, channels, sample_rate, bits, data)``.

    Replaces `wave.open`, which only understands PCM.  Raises ValueError with
    a readable message -- load_wav's caller turns that into the [ERROR] line.
    """
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise ValueError("not a RIFF/WAVE file")

    fmt = data = None
    pos, end = 12, len(raw)
    while pos + 8 <= end:
        ck_id = raw[pos:pos + 4]
        ck_sz = struct.unpack_from('<I', raw, pos + 4)[0]
        body  = raw[pos + 8:pos + 8 + ck_sz]
        if ck_id == b'fmt ':
            fmt = body
        elif ck_id == b'data':
            data = body
        pos += 8 + ck_sz + (ck_sz & 1)      # chunks are word-aligned
        if fmt is not None and data is not None:
            break

    if fmt is None or data is None:
        raise ValueError("missing fmt or data chunk")
    if len(fmt) < 16:
        raise ValueError("fmt chunk too short")

    code, channels, rate = struct.unpack_from('<HHI', fmt, 0)
    bits = struct.unpack_from('<H', fmt, 14)[0]

    if code == _WAVE_FORMAT_EXTENSIBLE:
        # The real code is the first two bytes of the SubFormat GUID; the rest
        # of the GUID is the fixed KSDATAFORMAT tail and carries nothing.
        if len(fmt) < 40:
            raise ValueError("extensible fmt chunk without a SubFormat GUID")
        code = struct.unpack_from('<H', fmt, 24)[0]

    if channels < 1:
        raise ValueError(f"bad channel count {channels}")
    return code, channels, rate, bits, data


def _float_to_int16(raw: bytes, bits: int) -> bytes:
    """IEEE float PCM -> signed 16-bit LE.

    Float WAVs legitimately exceed +/-1.0 (headroom is the point of the
    format), so the scale is clamped; a bare cast would wrap loud peaks into
    the opposite polarity.
    """
    src = array.array('f' if bits == 32 else 'd')
    src.frombytes(raw[:len(raw) - (len(raw) % src.itemsize)])
    if sys.byteorder == 'big':              # WAV is little-endian
        src.byteswap()
    # Round rather than truncate: truncation biases every sample toward zero
    # and doubles the mean quantisation error (0.50 vs 0.25 LSB, measured over
    # 500k samples of a real 32-bit float take).
    out = array.array('h', [-32768 if v <= -1.0 else
                            (32767 if v >= 1.0 else round(v * 32767.0))
                            for v in src])
    if sys.byteorder == 'big':
        out.byteswap()
    return out.tobytes()


def load_wav(wav_path: str, name: str) -> Optional[SampleData]:
    """Load WAV or AIFF/AIFC audio and return a SampleData (16-bit mono LE).
    AIFF: reads INST+MARK chunks for loop points and base note.
    WAV: reads SMPL chunk for loop points and unity note."""
    sfx = Path(wav_path).suffix.lower()
    if sfx in ('.aif', '.aiff'):
        return _load_aiff(wav_path, name)
    try:
        raw_file = open(wav_path, 'rb').read()

        code, channels, framerate, bit_depth, raw = _parse_wav_chunks(raw_file)

        # Trim a ragged tail so every frame is whole -- some writers pad the
        # data chunk, and the converters below assume complete frames.
        frame_bytes = channels * ((bit_depth + 7) // 8)
        if frame_bytes and len(raw) % frame_bytes:
            raw = raw[:len(raw) - (len(raw) % frame_bytes)]

        if code == _WAVE_FORMAT_IEEE_FLOAT:
            if bit_depth not in (32, 64):
                print(f"  [WARN] Unsupported float width {bit_depth} in "
                      f"{wav_path}, skipping")
                return None
            raw, bit_depth = _float_to_int16(raw, bit_depth), 16
        elif code == _WAVE_FORMAT_PCM:
            # Convert to 16-bit if necessary
            if bit_depth == 24:
                raw, bit_depth = _convert_24_to_16(raw, channels)
            elif bit_depth == 32:
                raw, bit_depth = _convert_32_to_16(raw)
            elif bit_depth == 8:
                raw, bit_depth = _convert_8_to_16(raw)
            elif bit_depth != 16:
                print(f"  [WARN] Unsupported bit depth {bit_depth} in {wav_path}, skipping")
                return None
        elif code in _WAVE_FORMAT_OGG:
            print(f"  [WARN] {wav_path} holds an Ogg stream, not PCM — skipping "
                  f"(no Vorbis decoder; see RESOLUTION_NOTES §WAVFMT)")
            return None
        else:
            print(f"  [WARN] Unsupported WAV format code 0x{code:04X} in "
                  f"{wav_path}, skipping")
            return None

        # Stereo is PRESERVED here: the parser's job is a faithful read.
        # Reducing to mono is an explicit choice made later (convert.py
        # --mono), alongside the other vintage-fit reductions, or forced by
        # a writer whose format mpc2emu cannot emit stereo for.

        # Read loop points from the SMPL chunk.
        # Clamp loop_end to the actual loaded frame count — the SMPL chunk uses
        # the nominal WAV header frame count, which can differ from what the
        # data chunk actually delivers.
        n_actual = len(raw) // (2 * (1 if channels == 1 else 2))
        # Frame count, channel-aware: a frame is 2 bytes PER CHANNEL, and the
        # data stays interleaved here because the parser preserves stereo.
        # Loop points are in FRAMES either way, so they must not shift with
        # the channel count.
        n_frames_loaded = len(raw) // (2 * max(1, channels))
        loop_type_raw = LoopType.NO_LOOP
        loop_start    = 0
        loop_end      = 0
        smpl = _read_smpl_loop(raw_file)
        if smpl:
            wav_loop_type, loop_start, loop_end = smpl
            loop_end = min(loop_end, n_frames_loaded - 1)  # clamp to actual frames
            if wav_loop_type == 0:
                loop_type_raw = LoopType.FORWARD
            elif wav_loop_type == 1:
                loop_type_raw = LoopType.ALTERNATING  # ping-pong

        safe_name = _safe_name(name, tail=True)
        # Sample's recorded pitch from the smpl chunk (MIDI unity note); the XPM
        # parser uses this as the playback root when RootNote=0 (the MPC unset
        # sentinel) instead of the keygroup low note — see _read_smpl_root.
        smpl_root = _read_smpl_root(raw_file)
        smpl_fine_cents = _read_smpl_pitch_fraction_cents(raw_file)
        return SampleData(
            name        = safe_name,
            data        = raw,
            sample_rate = framerate,
            channels    = channels,
            bit_depth   = bit_depth,
            loop_type   = loop_type_raw,
            loop_start  = loop_start,
            loop_end    = loop_end,
            root_note   = smpl_root if smpl_root is not None else 60,
            fine_tune   = smpl_fine_cents if smpl_fine_cents is not None else 0,
        )
    except Exception as e:
        print(f"  [ERROR] Could not load WAV {wav_path}: {e}")
        return None


def _is_full_sample_loop(loop_start: int, loop_end: int, n_frames: int) -> bool:
    """A WAV `smpl` loop that spans (almost) the whole sample — loop_start at the
    very beginning AND loop_end at the very end.  These are placeholder/default
    loops (common in auto-converted packs); the MPC IGNORES them and plays the
    sample one-shot (e.g. Annenberg: loop 29..end of a 269k-frame sample).  A
    genuine sustain loop (loop_start well into the sample, e.g. Bass-MS20: loop
    304175 of 308306) is NOT full-sample and the MPC plays it as a forward loop."""
    if n_frames <= 0:
        return False
    return (loop_start <= max(256, 0.02 * n_frames)
            and loop_end >= 0.90 * n_frames)


def _apply_slice(sd: SampleData, slice_start: int, slice_end: int,
                 slice_loop: int, slice_loop_start: int,
                 loop_on: bool = True, slice_loop_end: int = 0) -> None:
    """Apply MPC Pad-Start/End + Pad-Loop slice playback to a loaded sample.

    `slice_start`/`slice_end` are sample frames (Pad Start / Pad End); when set
    they trim the audio to that window.  `slice_loop` is the Pad-Loop enum
    (0=Off, 1=Forward, 2=Reverse, 3=Alternating); when on, the loop runs from the
    Loop Position (`slice_loop_start`) to the Pad End — rebased to the trimmed
    slice.  `slice_loop_end` is an explicit loop END in frames: MPC 2.x has no
    such field (its loop always runs to the Pad End) so it stays 0 there and the
    old behaviour is unchanged, but MPC 3.x does carry one -- see _mpc3_to_xml.
    `loop_on` is the layer's <Loop> master toggle.  The MPC reads the WAV
    `smpl` loop directly and plays it as a forward loop, EXCEPT a full-sample
    placeholder loop (`_is_full_sample_loop`), which it drops to a one-shot — so we
    only discard the embedded loop when it is full-sample (and <Loop> off), keeping
    genuine tail/sustain loops (Annenberg one-shot vs Bass-MS20's tail loop).
    Units are FRAMES here.  Verified against the MPC 3.7 manual + measured
    WAV frame counts — see docs/RESOLUTION_NOTES.md."""
    # 2 bytes per channel per frame: load_wav preserves the source's channel
    # count, so a stereo sample's frame is 4 bytes, not 2.
    bytes_per_frame = 2 * max(1, getattr(sd, 'channels', 1))
    n_frames = len(sd.data) // bytes_per_frame

    # Case 1: No Pad End set — play full sample.
    if slice_end == 0:
        if slice_loop:
            loop_pos = max(0, slice_loop_start)
            if loop_pos >= n_frames - 1:
                loop_pos = 0
            sd.loop_start = loop_pos
            sd.loop_end = (min(slice_loop_end, n_frames - 1)
                           if 0 < slice_loop_end else n_frames - 1)
            if sd.loop_end <= sd.loop_start:
                sd.loop_end = n_frames - 1
            sd.loop_type = LoopType.ALTERNATING if slice_loop == 3 else LoopType.FORWARD
        elif (not loop_on
              and _is_full_sample_loop(sd.loop_start, sd.loop_end, n_frames)):
            # Full-sample placeholder loop with <Loop> off — MPC plays one-shot.
            sd.loop_type  = LoopType.NO_LOOP
            sd.loop_start = 0
            sd.loop_end   = 0
        # else: keep the WAV smpl loop as-is — a genuine forward sustain loop
        # (Bass-MS20 tail loop) or an explicit <Loop>True.
        return

    trim_start = slice_start
    trim_end   = slice_end

    if slice_loop:
        # Case 2: XPM loop on — trim to [slice_start, slice_end] and loop from
        # slice_loop_start.  This is the explicit MPC Pad-Loop setting.
        if trim_end <= n_frames and (trim_start > 0 or trim_end < n_frames):
            sd.data  = sd.data[trim_start * bytes_per_frame: trim_end * bytes_per_frame]
            n_frames = trim_end - trim_start
        else:
            trim_start = 0
        loop_pos = slice_loop_start - trim_start
        if not (0 <= loop_pos < n_frames - 1):
            loop_pos = 0
        sd.loop_start = loop_pos
        _le = slice_loop_end - trim_start if 0 < slice_loop_end else 0
        sd.loop_end   = min(_le, n_frames - 1) if _le > loop_pos else n_frames - 1
        sd.loop_type  = LoopType.ALTERNATING if slice_loop == 3 else LoopType.FORWARD
    elif sd.loop_type != LoopType.NO_LOOP and sd.loop_start >= trim_end:
        # Case 3: No XPM loop, but WAV smpl loop starts BEYOND the attack slice.
        # The full sample has attack + sustain loop — expand to include the loop.
        # (e.g. SYNTHBONES: SliceEnd ≈ 23k frames but loop_start ≈ 58k frames)
        n_frames_ext = min(sd.loop_end + 1, n_frames)
        sd.data      = sd.data[trim_start * bytes_per_frame: n_frames_ext * bytes_per_frame]
        sd.loop_start -= trim_start
        sd.loop_end  -= trim_start
        # loop_type preserved from WAV smpl chunk
    else:
        # Case 4: No XPM loop, loop within trim window or no WAV loop.
        # Trim strictly to [slice_start, slice_end] and force one-shot.
        # (e.g. BASSMDACE: SliceLoop=0 and loop_start=0 inside trim → one-shot)
        if trim_end <= n_frames and (trim_start > 0 or trim_end < n_frames):
            sd.data = sd.data[trim_start * bytes_per_frame: trim_end * bytes_per_frame]
        sd.loop_type  = LoopType.NO_LOOP
        sd.loop_start = 0
        sd.loop_end   = 0


#: MPC zone-play mode -> (name, whether EOS can express it).
#: 0 = cycle (round-robin), 1 = velocity (the normal case), 2 = random.
_ZONE_PLAY = {
    0: ('cycle / round-robin', False),
    2: ('random', True),
}


def _warn_zone_play(mode: int, inst_idx: int, seen: set) -> None:
    """Report a zone-play mode we do not reproduce, once per mode per bank.

    Mode 1 (velocity) is the normal case and is exactly what the converter
    already does, so it is silent.

    **Mode 2 (random) is not hopeless**, and the earlier note in §XPMGAPS that
    "EOS has no round-robin" was only half right. The EOS 4.0 manual (p. 320,
    Realtime Window Controls) documents **Crossfade Random** as a modulation
    source "specifically designed" to "randomly switch between several voices",
    generating one random number for every voice assigned to the same key --
    which is precisely this feature. Mapping it means building realtime
    crossfade windows plus a cord per voice, so it is a writer-side project of
    its own and is filed in TODO.md rather than guessed at here.

    **Mode 0 (cycle) really has no equivalent** -- Crossfade Random is random,
    not sequential, and nothing in EOS advances through zones in order.

    Either way the conversion currently keeps every layer and lets key/velocity
    decide, so a round-robin keygroup plays one fixed choice instead of
    alternating. That is a visible, warned loss rather than an invented mapping
    that would change what the preset does.
    """
    entry = _ZONE_PLAY.get(mode)
    if entry is None or mode in seen:
        return
    seen.add(mode)
    name, has_eos_equivalent = entry
    hint = ("EOS can express this via Crossfade Random — not implemented yet, "
            "see TODO.md" if has_eos_equivalent else
            "EOS has no sequential zone cycling")
    print(f"    [WARN] instrument {inst_idx + 1}: zone play = {name}; "
          f"not reproduced ({hint})")


def _apply_loop_crossfade(sd: SampleData, xfade_frames: int) -> bool:
    """Bake the MPC layer's loop crossfade into the PCM.

    The MPC stores the length in FRAMES (`loopCrossfadeLength`, or `sliceInfo`'s
    `LoopCrossfadeLength`; both -1 and 0 mean none).  ConvertWithMoss stores a
    *fraction of the loop length* instead -- do not copy their number.

    Neither target format carries a loop-crossfade parameter, so as with
    reverse playback the only way to reproduce it is to render it.  The blend
    is the equal-power one `processors/auto_loop.py` already uses: the `xf`
    frames ending at loop_end are morphed into the `xf` frames ending just
    before loop_start, so the wrap loop_end -> loop_start is a continuous run.

    **The MPC's own convention is UNVERIFIED.** Whether it crossfades
    symmetrically about the loop point or backwards from it is unknown: every
    one of the 69 808 layers in the MPC One corpus has a crossfade of 0 or -1,
    so there is no real file to check against, and it has not been measured on
    hardware.  This renders a seamless loop of the right length, which is the
    audible intent; the exact frame alignment is a best-faithful guess.  See
    §XPMGAPS.

    Returns True if a crossfade was applied.
    """
    if xfade_frames <= 0 or sd.loop_type == LoopType.NO_LOOP:
        return False
    ch = max(1, getattr(sd, 'channels', 1))
    bpf = 2 * ch
    n = len(sd.data) // bpf
    S, E = sd.loop_start, sd.loop_end
    if not (0 <= S < E < n):
        return False
    loop_len = E - S + 1
    # Cap: cannot blend more than the pre-roll before the loop, nor so much of
    # the loop that the crossfade swallows it.
    xf = max(1, min(int(xfade_frames), S, loop_len // 3))
    if xf < 1:
        return False
    pcm = array.array('h')
    pcm.frombytes(sd.data[:n * bpf])
    if sys.byteorder == 'big':
        pcm.byteswap()
    for i in range(xf):
        t = i / (xf - 1) if xf > 1 else 1.0
        fo = math.cos(0.5 * math.pi * t)
        fi = math.sin(0.5 * math.pi * t)
        for c in range(ch):
            ie = (E - xf + 1 + i) * ch + c
            isr = (S - xf + i) * ch + c
            v = fo * pcm[ie] + fi * pcm[isr]
            pcm[ie] = max(-32768, min(32767, int(round(v))))
    if sys.byteorder == 'big':
        pcm.byteswap()
    sd.data = pcm.tobytes()
    return True


def _apply_reverse(sd: SampleData) -> None:
    """Play this sample backwards (MPC layer `Direction` = 1).

    Neither E4B/EOS nor the K2000 has a per-zone reverse-playback flag, so the
    only faithful conversion is to reverse the PCM itself -- the same approach
    the ping-pong renderer already takes for a loop mode the target cannot
    express.  Done AFTER slicing, so the reversal applies to exactly the region
    the MPC would have played.

    Frames are reversed, not bytes: channel interleaving inside a frame must
    survive, or a stereo sample comes back with its channels swapped and each
    sample's bytes flipped into noise.

    Loop points mirror about the new length -- a loop [a, b] in an n-frame
    sample becomes [n-1-b, n-1-a] -- because the frames they referred to have
    moved.  Leaving them alone would keep the loop at the wrong end of the
    sound, which is the kind of bug that still plays and still sounds like
    "a loop", just not the right one.
    """
    ch = max(1, getattr(sd, 'channels', 1))
    n = len(sd.data) // (2 * ch)
    if n < 2:
        return
    # Reverse per channel with strided slices rather than joining frames one at
    # a time: the naive version costs ~750 ms on a 5 MB stereo sample, which is
    # long enough to notice on a bank full of reversed layers.
    pcm = array.array('h')
    pcm.frombytes(sd.data[:n * 2 * ch])
    if sys.byteorder == 'big':
        pcm.byteswap()
    if ch == 1:
        pcm.reverse()
    else:
        out = array.array('h', bytes(len(pcm) * 2))
        for c in range(ch):
            lane = pcm[c::ch]
            lane.reverse()
            out[c::ch] = lane
        pcm = out
    if sys.byteorder == 'big':
        pcm.byteswap()
    sd.data = pcm.tobytes()
    if sd.loop_type != LoopType.NO_LOOP:
        a, b = sd.loop_start, sd.loop_end
        sd.loop_start = max(0, n - 1 - b)
        sd.loop_end   = max(sd.loop_start, n - 1 - a)


# unsigned-8 -> signed-8 sign flip, for the bulk 8->16 conversion below.
# (Same table `gig_parser` uses for its own 8-bit path, CR-16 #1.)
_FLIP_SIGN8 = bytes((i ^ 0x80) for i in range(256))


def _convert_24_to_16(raw: bytes, channels: int) -> tuple:
    """Little-endian signed 24-bit -> signed 16-bit.

    Dropping the LOW byte of an LE 24-bit sample IS the 16-bit value: with
    `b2 < 0x80` the old `(b2<<16|b1<<8|b0) >> 8` is plainly `b2<<8|b1`, and
    with `b2 >= 0x80` the `-0x1000000` sign correction and the flooring
    `>> 8` cancel to exactly `(b2<<8|b1) - 0x10000`. Bytes 1 and 2 are
    already in little-endian order, so unlike the big-endian AIFF variant
    (`_be_high2_to_le16`) this needs no byteswap -- just a strided copy.

    This was 87% of SFZ/EXS24 parse time; those formats' sample sets are
    predominantly 24-bit WAV, so they saw none of the stereo-downmix win.
    """
    n = len(raw) // 3
    out = bytearray(n * 2)
    out[0::2] = raw[1:n * 3:3]      # mid byte  -> LE low
    out[1::2] = raw[2:n * 3:3]      # high byte -> LE high
    return bytes(out), 16


def _convert_32_to_16(raw: bytes) -> tuple:
    """Little-endian signed 32-bit integer PCM -> signed 16-bit.

    Same argument as `_convert_24_to_16`: for LE data the top two bytes ARE
    the 16-bit value, so this is a strided copy rather than arithmetic.
    Distinct from IEEE float, which also carries 32 bits per sample but is
    format code 0x0003 and needs `_float_to_int16`.
    """
    n = len(raw) // 4
    out = bytearray(n * 2)
    out[0::2] = raw[2:n * 4:4]      # byte 2 -> LE low
    out[1::2] = raw[3:n * 4:4]      # byte 3 -> LE high
    return bytes(out), 16


def _convert_8_to_16(raw: bytes) -> tuple:
    """Unsigned 8-bit -> signed 16-bit, i.e. `(b - 128) * 256`.

    As little-endian int16 that is low byte 0 and high byte `b ^ 0x80`, so
    it is a zero fill interleaved with one bulk `bytes.translate`.
    """
    out = bytearray(len(raw) * 2)
    out[1::2] = raw.translate(_FLIP_SIGN8)
    return bytes(out), 16


# Canonical implementation lives in models.common so writers can reach it
# without importing a parser; kept under the old private name because
# gig_parser and this module's own call sites use it.
_stereo_to_mono = stereo_to_mono


def _safe_name(name: str, maxlen: int = 16, tail: bool = False) -> str:
    """Truncate and sanitize name for E4B (ASCII, max 16 chars).

    Preset/bank names keep the head (most meaningful).  Sample names pass
    `tail=True`: multisample sets often share a long common *prefix* and differ
    only in the *suffix* (note/layer/round-robin, e.g. `…UniPanBass_C1_A` vs
    `…_C2_B`); head truncation collapses those to identical names, so keep the
    tail where the distinguishing part lives."""
    name = os.path.splitext(name)[0]  # strip extension
    name = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in name)
    if len(name) <= maxlen:
        return name
    return name[len(name) - maxlen:] if tail else name[:maxlen]


# ---------------------------------------------------------------------------
# MPC 3.x JSON program (gzip + ACVS container)
# ---------------------------------------------------------------------------
# MPC 3.x stopped writing XML.  A modern .xpm is GZIP-compressed and holds five
# plain-text header lines followed by a JSON document:
#
#     ACVS
#     3.9.0.31                    <- MPC app/firmware version
#     SerialisableProgramData     <- also ...TrackData / ...ProjectData
#     json
#     Linux
#     { "data": { "version": 6, "name": ..., "drum": {"instruments": [...]}, ...
#
# Rather than re-implement the whole mapping (envelopes, filter, LFO, and the
# lane allocation that splits overlapping layers into parallel voices), the
# JSON program is converted into the SAME element tree the XML path already
# understands and handed to the existing parser.  One mapping, one set of
# hardware-calibrated curves, no drift.  See docs/RESOLUTION_NOTES.md §MPC3XPM.

MPC3_MAGIC = b'\x1f\x8b'          # gzip; a classic XPM is plain '<?xml'

#: MPC 3 `program.type` -> human name, for messages.  0/1 are the two we
#: convert; 7/8/9 were read off a real 32-track project (§MPC3D3).  3 and 4
#: appear only in MIDI-controller and multi-interface template projects in the
#: MPC One backup and have not been pinned down, so they print as "type N"
#: rather than being guessed at.
_MPC3_PROGRAM_TYPES = {
    0: 'drum', 1: 'keygroup', 7: 'return', 8: 'submix', 9: 'output',
}


def _mpc3_type_name(t) -> str:
    try:
        t = int(t)
    except (TypeError, ValueError):
        return 'unknown'
    return _MPC3_PROGRAM_TYPES.get(t, f'type {t}')


#: An MPC drum program always serialises 128 pads, sampled or not.
_MAX_PADS = 128
#: Pad 1 lands on MIDI 36 (C1) when a program carries no explicit map -- the
#: MPC's own default, and what 24 of 56 corpus drum programs use verbatim.
_PAD_BASE_NOTE = 36

# Header line 3 -> the word the MPC uses for that container in the sibling
# sample folder it writes next to the file (`<stem>_[ProgramData]/` etc).
_MPC3_PAYLOADS = {
    'SerialisableProgramData': 'Program',
    'SerialisableTrackData':   'Track',
    'SerialisableProjectData': 'Project',
}


def is_mpc3_xpm(path) -> bool:
    """True if `path` is an MPC 3.x (gzip+JSON) program rather than XML."""
    try:
        with open(path, 'rb') as fh:
            return fh.read(2) == MPC3_MAGIC
    except OSError:
        return False


def _mpc3_read(path):
    """Return (header_lines, data_dict) from an MPC 3.x .xpm."""
    import gzip as _gzip, json as _json
    with _gzip.open(path, 'rt', encoding='utf-8', errors='replace') as g:
        header = [g.readline().rstrip('\n') for _ in range(5)]
        if header[0] != 'ACVS':
            raise ValueError(f"not an MPC 3 program (magic {header[0]!r})")
        if header[3] != 'json':
            raise ValueError(f"unsupported MPC 3 encoding {header[3]!r}")
        payload = _json.load(g)
    kind = header[2]
    if kind not in _MPC3_PAYLOADS:
        raise ValueError(f"unsupported MPC 3 payload {kind!r} "
                          f"(expected one of {', '.join(sorted(_MPC3_PAYLOADS))})")
    return header, payload.get('data', {})


def _mpc3_program_nodes(kind: str, data: dict) -> list:
    """The keygroup program(s) inside an MPC 3 payload.

    A `.xpm` is not always a bare program: the MPC also writes a whole track
    (`SerialisableTrackData`, one program) and a whole project
    (`SerialisableProjectData`, one program per track).  Both were rejected
    outright before, so a keygroup program saved inside either was
    unreachable.

    `type == 1` is the keygroup program; the other types are drum, plugin and
    MIDI tracks, which are not ours to convert.  ConvertWithMoss filters on
    the same field.

    In the track and project containers `samples[]` sits on the payload root
    rather than on the program node, so it is folded into each program here —
    that keeps `_mpc3_to_xml` reading one self-contained dict regardless of
    which container the program arrived in.
    """
    if kind == 'SerialisableProgramData':
        return [data] if isinstance(data, dict) else []

    if kind == 'SerialisableTrackData':
        candidates = [data.get('program')]
    else:                                    # SerialisableProjectData
        candidates = [t.get('program') for t in (data.get('tracks') or [])
                      if isinstance(t, dict)]

    programs = []
    for prog in candidates:
        if not isinstance(prog, dict):
            continue
        # 1 = keygroup, 0 = drum.  Both carry sampled material and both are
        # convertible (a drum kit is one-key zones whose root equals their key
        # -- see §XPMDRUM).  The other types (MIDI, plugin, audio, CV, clip)
        # reference no sample data at all: 393 such files in the MPC One
        # corpus, every one of them with zero sample references.
        if int(_as_float(prog.get('type'), -1.0)) not in (0, 1):
            continue
        if not prog.get('samples'):
            prog = {**prog, 'samples': data.get('samples') or []}
        programs.append(prog)
    return programs


def _resolve_mpc3_sample(layer, sample_dir) -> Optional[Path]:
    """The WAV for an MPC 3 layer, resolved exactly rather than by search.

    MPC 3 writes its samples into a sibling `<stem>_[<Kind>Data]/` folder and
    names the file in the layer's own `sampleFile`, so the right WAV is known
    without looking for it.  `_find_wav` instead takes the first name match in
    a whole-tree walk, which picks the wrong file when a same-named sample
    sits in another program's folder beside it.

    Returns None — falling back to `_find_wav` — when the folder or the file
    is missing, so a re-organised or hand-assembled export still resolves the
    old way.  (ConvertWithMoss treats the miss as an error instead; being
    forgiving here costs nothing and keeps every export that works today
    working.)
    """
    if sample_dir is None:
        return None
    name = _get_text(layer, 'SampleFile', '')
    if not name:
        return None
    candidate = sample_dir / name
    return candidate if candidate.is_file() else None


def _v0(node, default=0.0):
    """MPC 3 wraps many scalars as {'value0': x} (one entry per articulation);
    take the first."""
    if isinstance(node, dict):
        return node.get('value0', default)
    return default if node is None else node


def _as_float(value, default=0.0) -> float:
    """MPC 3 JSON numbers arrive as int, float, null or (rarely) a string;
    coerce to float so arithmetic on them cannot raise."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _prefers_tail(sample_names) -> bool:
    """Should this program's sample names keep their tail or their head?

    `_safe_name(tail=True)` is right for a MULTISAMPLE: those share a long
    prefix and differ at the end (`…UniPanBass_C1_A` vs `…_C2_B`), so the tail
    is where the identity lives. A drum kit is the mirror image — `BD
    Drumulator Clean`, `Clap Drumulator Clean`, `Cymbal Drumulator Clean` all
    *end* alike and differ at the front — so the tail keeps the one part that
    identifies nothing. One real 14-sample kit collapses to **4** distinct
    tails against 13 distinct heads, and the bank then reads
    `Drumulator Clean`, `Drumulator Clea1`, … on a 16-character display.

    **Not a flag to flip globally.** Measured over the corpus, the tail is the
    only rule that works for the overwhelming majority of programs; switching
    everything to the head makes things far worse overall. Both rules are pure
    functions of one program's own name set, so the choice is made per program:
    whichever yields more distinct names, **ties going to the tail** so today's
    behaviour is preserved wherever it already works.

    No audio depends on this — `_unique_sample_name` guarantees uniqueness
    either way (§XPMNAMES). What is at stake is whether a user can tell which
    pad is which on the hardware.
    """
    uniq = {n for n in sample_names if n}
    if len(uniq) < 2:
        return True
    n_tail = len({_safe_name(n, tail=True) for n in uniq})
    n_head = len({_safe_name(n, tail=False) for n in uniq})
    return n_tail >= n_head


def _unique_sample_name(name: str, taken: set, limit: int = 16) -> str:
    """A name at most `limit` chars that is not already in `taken`.

    Sample names are the ONLY handle a zone has on its audio, so two samples
    sharing one name is not a cosmetic clash — it silently drops the second
    sample's audio and makes its zones sound the first one.

    The counter has to be advanced against the names actually taken, not
    against a per-base tally, because shortening can map two different bases
    onto the same string. Both failure modes were live:

      * a base already ending in the digit being appended came back unchanged
        (`'…_2600_C-1'` + `'1'` -> `'…_2600_C-1'`), and names ending `-1`,
        `A1`, `C1` are ordinary in auto-sampled sets;
      * a rewrite could land on a *different* real sample
        (`'MarioPCP2600__C0'` + `'1'` -> `'MarioPCP2600__C1'`).

    Falls back to a longer suffix rather than giving up, and finally to the
    candidate itself, so it always returns something.
    """
    if name not in taken:
        return name
    for n in range(1, 10_000):
        suffix = str(n)
        cand = name[:max(1, limit - len(suffix))] + suffix
        if cand not in taken:
            return cand
    return name


def _pad_note_map(root) -> dict:
    """`{pad_index (0-based): midi_note}` for a drum program.

    Read from `<PadNoteMap><PadNote number="N">note</PadNote>`, which the MPC 3
    path fills in from the program's own `padNoteMap.noteForPad`.

    **MPC 2.x XML does not store this.** All 11 520 `<PadNote>` elements across
    the 90 drum programs in the MPC One corpus carry a `number` attribute and an
    empty body, and the neighbouring `ProgramPads-v2.10` blob holds pad colours
    (`0,127,0` green, `0,127,127` teal), not notes. So an unmapped pad falls
    back to `_PAD_BASE_NOTE + index`, wrapped into range.

    That fallback is right for the 24 corpus programs that use the MPC default
    and wrong for the 31 that carry a custom (often General-MIDI) layout --
    but for a 2.x file there is nothing better to read, and consecutive keys
    still give a playable kit. Callers warn when they fall back.
    """
    out = {}
    for el in root.iter('PadNote'):
        try:
            idx = int(el.get('number', '0')) - 1
        except ValueError:
            continue
        text = (el.text or '').strip()
        if idx < 0 or not text:
            continue
        try:
            out[idx] = int(float(text)) & 0x7F
        except ValueError:
            continue
    return out


def _mpc3_to_xml(data) -> 'ET.Element':
    """Build the MPC 2.x element tree this module already parses from an
    MPC 3.x JSON program."""
    root = ET.Element('MPCVObject')
    prog = ET.SubElement(root, 'Program')
    is_drum = int(_as_float(data.get('type'), 1.0)) == 0
    prog.set('type', 'Drum' if is_drum else 'Keygroup')
    ET.SubElement(prog, 'ProgramName').text = str(data.get('name', ''))

    # A drum program's pad -> MIDI note mapping is real per-program DATA, not a
    # formula: across 56 drum programs in the MPC One corpus, 24 use
    # (36 + pad) mod 128, one is the identity, and **31 carry a custom map**
    # (General-MIDI drum layouts and hand-arranged kits).  Assuming the formula
    # would put more than half of them on the wrong keys.
    #
    # Emitted into the 2.x `<PadNoteMap><PadNote number="N">` shape so both
    # firmware paths read one place.  MPC 2.x XML does NOT store it -- every
    # one of the 11 520 <PadNote> elements in the corpus has an empty body --
    # so that path falls back to consecutive notes (see _pad_note_map).
    note_for_pad = ((data.get('padNoteMap') or {}).get('noteForPad')) or {}
    if is_drum and note_for_pad:
        pnm = ET.SubElement(prog, 'PadNoteMap')
        for i in range(_MAX_PADS):
            v = note_for_pad.get(f'value{i}')
            if v is None:
                continue
            el = ET.SubElement(pnm, 'PadNote')
            el.set('number', str(i + 1))
            el.text = str(int(_as_float(v)))

    # MPC 3 keeps the keygroup list under 'drum' even for a keygroup program
    # (type 1); 'keygroup' holds only program-global settings.
    instruments = (data.get('drum') or {}).get('instruments') or []
    insts_el = ET.SubElement(prog, 'Instruments')

    # Program- and keygroup-level transpose, in semitones (may be fractional).
    # Both apply on top of every instrument's own coarse/fine tune, so fold
    # them into the instrument's TuneCoarse/TuneFine, which is where the XML
    # path already sums instrument + layer tuning.  ConvertWithMoss does the
    # same (`keygroupTranspose = programTranspose + keygroup.transpose`).
    # Both are 0 in all three local 3.9 files, so this is read-side only until
    # a program with a real transpose turns up — see the RE checklist.
    kg_node = data.get('keygroup') or {}
    transpose = (_as_float(data.get('transpose'))
                 + _as_float(kg_node.get('transpose')))

    # `samples[]` carries per-sample metadata the layers do not repeat: the
    # recorded root note and a tuning offset.  NOTE the two root notes use
    # DIFFERENT bases -- verified across all 71 layers of the three local
    # files: `samples[].metadata.rootNote` equals the note number in the
    # sample's own filename (0-based MIDI), while `layersv[].rootNote` is that
    # number PLUS ONE (1-based, as in MPC 2.x XML).  <RootNote> below is the
    # 1-based convention, so the metadata fallback is written +1.
    sample_meta = {s.get('name'): (s.get('metadata') or {})
                   for s in (data.get('samples') or []) if isinstance(s, dict)}

    for idx, inst in enumerate(instruments):
        layers = [l for l in (inst.get('layersv') or [])
                  if l.get('sampleName') and l.get('active', True)]
        if not layers:
            continue
        ie = ET.SubElement(insts_el, 'Instrument')
        ie.set('number', str(idx + 1))
        ss = inst.get('synthSection') or {}
        filt = _v0(ss.get('filterData'), {}) or {}
        amp = ss.get('ampEnvelope') or {}
        fenv = ss.get('filterEnvelope') or {}
        lfo = _v0(ss.get('lfoData'), {}) or {}

        def put(tag, val):
            ET.SubElement(ie, tag).text = str(val)

        put('LowNote',  inst.get('lowNote', 0))
        put('HighNote', inst.get('highNote', 127))
        # Zone-play mode: 0 = cycle (round-robin), 1 = velocity (normal),
        # 2 = random.  MPC 2.x spells it <ZonePlay>; the JSON field is named
        # `zonePlayTime`, whose value distribution across the corpus matches
        # the XML tag exactly (1 dominant, 0 and 2 rare).  Read only to warn
        # -- see _warn_zone_play.
        put('ZonePlay', int(_as_float(inst.get('zonePlayTime'), 1.0)))
        # Fold the program/keygroup transpose in; keep whole semitones in
        # TuneCoarse and push any fraction into TuneFine as cents.
        inst_semis  = _as_float(inst.get('coarseTune')) + transpose
        inst_coarse = int(inst_semis)
        put('TuneCoarse', inst_coarse)
        put('TuneFine',   int(_as_float(inst.get('fineTune')))
                          + round((inst_semis - inst_coarse) * 100))
        put('IgnoreBaseNote', 'True' if inst.get('ignoreBaseNote') else 'False')
        # Filter — MPC 3 keeps the same normalised 0-1 domain as MPC 2.
        put('FilterType',      filt.get('filterType', 0))
        put('Cutoff',          filt.get('filterCutoff', 1.0))
        put('Resonance',       filt.get('filterResonance', 0.0))
        put('FilterEnvAmt',    filt.get('filterEnvelopeAmount', 0.0))
        put('FilterKeytrack',  filt.get('filterKeytrack', 0.0))
        put('VelocityToFilter', filt.get('filterVelocity', 0.0))
        # Envelopes — {'Attack': {'value0': x}, ...}.
        # MPC 3 envelopes are DAHDSR (Delay, Attack, Hold, Decay, Sustain,
        # Release) and can run in AD mode, where there is no sustain segment
        # at all: the level decays to zero after the attack (manual: "the
        # volume will gradually drop to zero over the set duration").  The
        # model here is ADSR, so AD mode is expressed as sustain 0 --
        # otherwise an AD envelope would import as a full-level hold, which
        # is the opposite of what it does.  Delay and Hold are dropped; see
        # the gap list in docs/RESOLUTION_NOTES.md §MPC3XPM.
        def env_sustain(env):
            return 0.0 if _v0(env.get('AD'), False) else _v0(env.get('Sustain'), 1.0)

        put('VolumeAttack',  _v0(amp.get('Attack')))
        put('VolumeDecay',   _v0(amp.get('Decay')))
        put('VolumeSustain', env_sustain(amp))
        put('VolumeRelease', _v0(amp.get('Release')))
        put('FilterAttack',  _v0(fenv.get('Attack')))
        put('FilterDecay',   _v0(fenv.get('Decay')))
        put('FilterSustain', env_sustain(fenv))
        put('FilterRelease', _v0(fenv.get('Release')))
        # LFO — lfoFilterCutOff is itself per-articulation.
        put('LfoPitch',  lfo.get('lfoPitch', 0.0))
        put('LfoCutoff', _v0(lfo.get('lfoFilterCutOff')))
        lfo_el = ET.SubElement(ie, 'LFO')
        ET.SubElement(lfo_el, 'Rate').text  = str(lfo.get('lfoRate', 0.5))
        ET.SubElement(lfo_el, 'Type').text  = _MPC3_LFO_SHAPES.get(
            lfo.get('lfoWaveformType', 0), 'Sine')
        ET.SubElement(lfo_el, 'Sync').text  = str(lfo.get('lfoSync', 0))
        ET.SubElement(lfo_el, 'Reset').text = str(lfo.get('lfoReset', True))

        # MPC 3 has a SECOND LFO (manual: "Tap LFO to cycle between the LFO 1
        # and LFO 2 controls"), which MPC 2.x had no equivalent of.  VoiceLayer
        # already carries lfo2_* fields, so emit it in a parallel <LFO2> block
        # the reader below picks up; XML programs never contain one, so their
        # behaviour is unchanged.
        lfo2 = (ss.get('lfoData') or {}).get('value1') or {}
        if lfo2:
            l2 = ET.SubElement(ie, 'LFO2')
            ET.SubElement(l2, 'Rate').text  = str(lfo2.get('lfoRate', 0.5))
            ET.SubElement(l2, 'Type').text  = _MPC3_LFO_SHAPES.get(
                lfo2.get('lfoWaveformType', 0), 'Sine')
            ET.SubElement(l2, 'Pitch').text = str(lfo2.get('lfoPitch', 0.0))

        layers_el = ET.SubElement(ie, 'Layers')
        for lidx, lay in enumerate(layers):
            le = ET.SubElement(layers_el, 'Layer')
            le.set('number', str(lidx + 1))

            def lput(tag, val):
                ET.SubElement(le, tag).text = str(val)

            meta = sample_meta.get(lay.get('sampleName', '')) or {}

            lput('SampleName', lay.get('sampleName', ''))
            # The exact filename inside the sibling `_[<Kind>Data]/` folder.
            # Carries no meaning for the XML path (MPC 2.x has no equivalent)
            # but lets the MPC 3 sample lookup be exact — see
            # _resolve_mpc3_sample.
            lput('SampleFile', lay.get('sampleFile', ''))
            lput('VelStart',   lay.get('velocityStart', 0))
            lput('VelEnd',     lay.get('velocityEnd', 127))
            # rootNote 0 is the MPC "root unset" sentinel.  Prefer the sample's
            # own recorded root over the WAV `smpl` unity note the XML path
            # falls back to -- it is what the MPC itself shows.  Converted
            # 0-based -> 1-based to match the <RootNote> convention.
            lay_root = int(_as_float(lay.get('rootNote')))
            if lay_root <= 0 and meta.get('rootNote') is not None:
                lay_root = int(_as_float(meta.get('rootNote'))) + 1
            lput('RootNote', lay_root)
            # volume is {'gainCoefficient': linear, 'controlValue': .., 'law': ..}
            vol = lay.get('volume')
            lput('Volume', vol.get('gainCoefficient', 1.0)
                 if isinstance(vol, dict) else (1.0 if vol is None else vol))
            lput('Pan',        lay.get('pan', 0.5))
            lput('TuneCoarse', lay.get('coarseTune', 0))
            # metadata.tune is a per-sample offset in semitones (0.0 in every
            # local file, so read-side only for now); TuneFine is in cents.
            lput('TuneFine',   int(_as_float(lay.get('fineTune')))
                               + round(_as_float(meta.get('tune')) * 100))
            # Loops.  MPC 3 carries TWO loop descriptions and a flag choosing
            # between them, which MPC 2.x had no equivalent of; this follows
            # ConvertWithMoss's MPCModernDetector, taken as correct in the
            # absence of a test file that exercises it (all three local 3.9
            # files are auto-sampler output with loop=false throughout).
            #   layerLoopModeOverridesSliceLoopMode -> use the LAYER's
            #     loopMode/loopStart/loopEnd/loopCrossfadeLength
            #   otherwise                           -> use sliceInfo's
            #     LoopMode/LoopStart/End/LoopCrossfadeLength
            # A loop counts only when mode > 0 AND its end > 0.
            slice_info = lay.get('sliceInfo') or {}
            if lay.get('layerLoopModeOverridesSliceLoopMode'):
                lmode  = int(lay.get('loopMode', 0) or 0)
                lstart = int(lay.get('loopStart', 0) or 0)
                lend   = int(lay.get('loopEnd', 0) or 0)
                lxfade = int(lay.get('loopCrossfadeLength', 0) or 0)
            else:
                lmode  = int(slice_info.get('LoopMode', 0) or 0)
                lstart = int(slice_info.get('LoopStart', 0) or 0)
                lend   = int(slice_info.get('End', 0) or 0)
                lxfade = int(slice_info.get('LoopCrossfadeLength', 0) or 0)
            has_loop = lmode > 0 and lend > 0
            # `offset` shifts the play start on top of sampleStart (CWM does
            # the same); MPC 2.x folded it into SliceStart.
            start = int(lay.get('offset', 0) or 0) + int(lay.get('sampleStart', 0) or 0)

            lput('Loop',       'True' if (has_loop or lay.get('loop')) else 'False')
            lput('SliceStart',     start)
            lput('SliceEnd',       lay.get('sampleEnd', 0))
            lput('SliceLoop',      lmode if has_loop else 0)
            lput('SliceLoopStart', lstart)
            lput('SliceLoopEnd',   lend if has_loop else 0)
            # `direction` 1 = the layer plays its sample BACKWARDS.  This is a
            # different mechanism from SliceLoop 2/3 (a reverse or alternating
            # loop MODE) and must not be conflated with it -- see §XPMGAPS.
            # MPC 2.x spells the same field <Direction>, so both paths meet at
            # this tag and only one implementation is needed downstream.
            lput('Direction',  int(_as_float(lay.get('direction'))))
            # Loop crossfade length in FRAMES (-1 and 0 both mean "none").
            # NOT ConvertWithMoss's fraction-of-loop-length -- do not copy
            # their number without converting.
            lput('SliceLoopCrossFadeLength', max(0, lxfade) if has_loop else 0)
            # `loopFineTune` has no known semantics and is 0 in every one of
            # the 69808 layers of the MPC One corpus, so there is nothing to
            # calibrate it against. Warn rather than guess if one ever appears.
            _lft = _as_float(lay.get('loopFineTune'))
            if _lft:
                print(f"    [WARN] layer {lidx + 1} has loopFineTune={_lft:g}, "
                      f"whose meaning is unknown — ignored (see §XPMGAPS)")
    return root


# MPC 3 lfoWaveformType -> the <Type> strings _xpm_lfo_shape() already maps.
_MPC3_LFO_SHAPES = {0: 'Sine', 1: 'Triangle', 2: 'Saw Up', 3: 'Saw Down',
                    4: 'Square', 5: 'SampHold', 6: 'Random'}


# ---------------------------------------------------------------------------
# XPM parser
# ---------------------------------------------------------------------------

def parse_xpm(xpm_path: str, wav_dir: Optional[str] = None) -> Bank:
    """
    Parse an Akai MPC XPM program file and resolve WAV samples.

    Args:
        xpm_path:  Path to the .xpm file
        wav_dir:   Directory to search for WAV files.
                   If None, uses the XPM file's directory.
    Returns:
        Bank object with one Preset and all referenced samples loaded.
    """
    xpm_path = Path(xpm_path).resolve()
    if wav_dir is None:
        wav_dir = xpm_path.parent
    else:
        wav_dir = Path(wav_dir).resolve()

    # An MPC 3.x program is gzip+JSON, not XML — convert it to the element
    # tree this parser already understands (see _mpc3_to_xml). A file ending
    # .xpm that is neither is almost always an X11 pixmap, which shares the
    # extension; say so plainly instead of failing with an XML error.
    mpc3_sample_dir = None
    is_mpc3 = False
    if is_mpc3_xpm(xpm_path):
        is_mpc3 = True
        header, data = _mpc3_read(str(xpm_path))
        kind = header[2]
        container = _MPC3_PAYLOADS[kind]
        programs = _mpc3_program_nodes(kind, data)
        if not programs:
            # Name what WAS found rather than what was not: this sentence is
            # the whole explanation a user gets (VinSamLib shows it verbatim in
            # the tooltip of a greyed-out row), so "nothing here" is far less
            # useful than "these are the things it holds".
            _present = []
            for _t in (data.get('tracks') or []):
                _p = _t.get('program') if isinstance(_t, dict) else None
                if isinstance(_p, dict) and _p.get('type') is not None:
                    _present.append(_mpc3_type_name(_p.get('type')))
            _bare = data.get('program')
            if isinstance(_bare, dict) and _bare.get('type') is not None:
                _present.append(_mpc3_type_name(_bare.get('type')))
            _seen = ', '.join(sorted(set(_present))) or 'no programs at all'
            raise ValueError(
                f"{xpm_path.name} is an MPC {header[1]} {container.lower()} "
                f"with no keygroup or drum program in it — it holds {_seen}, "
                f"none of which carries sample data.")
        print(f"Parsing XPM (MPC {header[1]} JSON, {container.lower()}): "
              f"{xpm_path}")
        if len(programs) > 1:
            _kinds = collections.Counter(
                _mpc3_type_name(p.get('type')) for p in programs)
            _desc = ' + '.join(f"{n} {k}" for k, n in sorted(_kinds.items()))
            print(f"  {_desc} program(s) → one bank, one preset each: "
                  f"{', '.join(str(p.get('name', '?')) for p in programs)}")
        # A project carries one keygroup program per track, so it is the MPC's
        # equivalent of an E4B bank: every program becomes a preset, and they
        # share one sample pool (see _build_preset).  A bare program or a track
        # simply yields a one-preset bank.
        program_trees = [(str(p.get('name') or xpm_path.stem), _mpc3_to_xml(p))
                         for p in programs]
        # MPC 3 keeps its samples in a sibling folder named after the file and
        # its container kind; used for exact lookup (see _resolve_mpc3_sample).
        mpc3_sample_dir = xpm_path.parent / f"{xpm_path.stem}_[{container}Data]"
        if not mpc3_sample_dir.is_dir():
            mpc3_sample_dir = None
    else:
        with open(xpm_path, 'rb') as _fh:
            _head = _fh.read(16)
        if _head[:1] != b'<':
            raise ValueError(
                f"{xpm_path.name} is not an MPC program — it starts with "
                f"{_head[:8]!r}. Files ending .xpm are also X11 pixmaps "
                f"(/* XPM */), an unrelated image format.")
        print(f"Parsing XPM: {xpm_path}")
        tree = ET.parse(str(xpm_path))
        _root = tree.getroot()
        if _root.tag == 'Project':
            # An MPC 2.x project (.xpj) is XML, but it is a <Project>, not a
            # program: it holds only settings and a file list.  Its programs
            # live as separate .xpm files in the sibling data folder, named
            # `<name>.<Kind>.xpm` -- so the 2.x equivalent of the 3.x
            # "project = bank" case is to gather the convertible ones.  Without
            # this a 2.x .xpj parsed "successfully" into an empty preset, which
            # is worse than failing.  See §MPC3BANK.
            #
            # Keygroup AND Drum, to match what the MPC 3 path gathers
            # (`_mpc3_program_nodes` takes type 0 and 1).  Taking only keygroups
            # here left the two container generations disagreeing about what a
            # project contains: measured on the MPC One backup, 62 of 94 2.x
            # projects converted incompletely and 32 more -- holding only drum
            # kits -- refused outright, while every one of those kits converted
            # fine when pointed at directly.  All 224 drum programs in that
            # backup live inside a project folder, so the .xpj route reached
            # none of them.  See §XPMDRUM2X.
            #
            # Keygroups first, then drums, each sorted: this leaves the preset
            # ORDER of an already-converting project untouched, so re-converting
            # one does not renumber the presets an existing E4B bank has.
            data_dir = xpm_path.parent / f"{xpm_path.stem}_[ProjectData]"
            if data_dir.is_dir():
                kg = sorted(data_dir.glob('*.Keygroup.xpm'))
                dr = sorted(data_dir.glob('*.Drum.xpm'))
            else:
                kg = dr = []
            progs = [(p, '.Keygroup') for p in kg] + [(p, '.Drum') for p in dr]
            if not progs:
                raise ValueError(
                    f"{xpm_path.name} is an MPC 2.x project, not a program. "
                    f"Its programs live in {data_dir.name}/ and none of them is "
                    f"a keygroup or drum program (only MIDI, plugin, audio, CV "
                    f"or clip tracks, which carry no sample data) — nothing to "
                    f"convert.")
            _kinds = (f"{len(kg)} keygroup" if kg else '') + \
                     (' + ' if kg and dr else '') + (f"{len(dr)} drum" if dr else '')
            print(f"  MPC 2.x project → {_kinds} program(s): "
                  f"{', '.join(p.name.rsplit(k, 1)[0] for p, k in progs)}")
            program_trees = [(p.name.rsplit(k, 1)[0], ET.parse(str(p)).getroot())
                             for p, k in progs]
            # The project's samples sit in that same folder, not beside the
            # .xpj, so search there rather than walking the whole Projects tree.
            if wav_dir == xpm_path.parent:
                wav_dir = data_dir
        else:
            program_trees = [(xpm_path.stem, _root)]

    bank = Bank(name=_safe_name(xpm_path.stem))

    sample_cache: dict[str, SampleData] = {}
    # The sample names ALREADY taken in this bank.  Tracking the names rather
    # than a per-base count is the whole point -- see _unique_sample_name.
    _names_taken: set = set()
    # Source names whose WAV could not be found on disk.  Their zones
    # legitimately resolve to nothing, and that was already reported as
    # `[WARN] Sample not found` -- so the invariant below must not report
    # them a second time as if the name handling were at fault.
    _missing_wavs: set = set()
    # WAV smpl-chunk recorded root per cached sample (None if the WAV has no
    # unity note) — used as the RootNote=0 playback root instead of lo_key.
    sample_wav_root: dict[str, Optional[int]] = {}

    def _build_preset(root, preset_name):
        """Build one Preset from one program element tree and append it to
        `bank`.  Split out of parse_xpm so an MPC 3 project, which carries one
        keygroup program per track, converts into a multi-preset bank the way
        an E4B bank does -- see docs/RESOLUTION_NOTES.md §MPC3D3.

        The sample caches are deliberately SHARED across presets: two programs
        in one project routinely reference the same WAV, and it must be loaded
        and stored once, not once per preset."""
        preset = Preset(name=_safe_name(preset_name), program_number=len(bank.presets))

        # MPC XPM v2.x structure (MPC One / Live / X, firmware 2.x):
        # <MPCVObject>
        #   <Program type="Keygroup">
        #     <Instruments>
        #       <Instrument number="1">          ← no type attr; key range here
        #         <LowNote>36</LowNote>          ← MIDI integer
        #         <HighNote>47</HighNote>         ← MIDI integer
        #         <VolumeAttack>…</VolumeAttack>  ← envelope on Instrument
        #         <Layers>
        #           <Layer number="1">
        #             <SampleName>kick</SampleName>  ← no extension
        #             <VelStart>0</VelStart>
        #             <VelEnd>127</VelEnd>
        #             <RootNote>36</RootNote>     ← MIDI integer
        #             <Volume>1.0</Volume>        ← 0-1 linear
        #             <Pan>0.5</Pan>              ← 0-1, 0.5=center
        #           </Layer>
        #         </Layers>
        #       </Instrument>
        #     </Instruments>
        #   </Program>
        # </MPCVObject>

        # A drum program is convertible: each pad becomes a ONE-KEY zone whose
        # root equals its key, so the sample plays at native pitch and does not
        # keytrack.  Both writers already handle that shape -- EOS plays one
        # zone per key, and krz_writer's `tuning = 100*(r_sample - r_zone)`
        # cancels the K2000's auto-transpose exactly when r_zone is the key
        # (the drum-map idiom it already documents meeting in real soundsets).
        # See §XPMDRUM.
        program_elem = root.find('Program')
        prog_type = (program_elem.get('type', '') if program_elem is not None
                     else '')
        is_drum = prog_type == 'Drum'
        if program_elem is not None and prog_type not in ('', 'Keygroup', 'Drum'):
            # MIDI / Plugin / Audio / CV / Clip reference no sample data at all
            # (393 such files in the corpus, every one with zero references).
            # Refuse rather than hand back an empty preset a caller cannot
            # distinguish from a successful conversion.
            raise ValueError(
                f"{xpm_path.name} is an MPC {prog_type} program — it carries no "
                f"sample data, so there is nothing to convert.")
        pad_notes = _pad_note_map(root) if is_drum else {}
        if is_drum and not pad_notes:
            print(f"  [WARN] drum program has no pad→note map (MPC 2.x does not "
                  f"store one) — laying pads out from MIDI {_PAD_BASE_NOTE}; a "
                  f"kit using a custom/GM layout will land on different keys")

        # Decide head-vs-tail truncation ONCE for this program, from its own
        # set of sample names -- a multisample wants the tail, a drum kit the
        # head.  See _prefers_tail.
        _name_tail = _prefers_tail(
            (e.text or '').strip() for e in root.iter('SampleName'))

        instruments = sorted(
            root.findall('.//Instrument'),
            key=lambda e: int(e.get('number', '9999'))
        )
        # The XPM always carries 128 Instrument slots; only the first
        # KeygroupNumKeygroups are real — the rest are padding (often duplicates of
        # one keygroup, e.g. the wide-drone preset's 120 copies of a 24-47 C1 slice that
        # otherwise survive dedup as a junk voice and eat a K2000 layer).  Trim to
        # the declared count.
        n_kg = int(float(_get_text(root, './/KeygroupNumKeygroups', '0')) or 0)
        if 0 < n_kg < len(instruments):
            print(f"  KeygroupNumKeygroups={n_kg} → using first {n_kg} of "
                  f"{len(instruments)} instrument slots (rest are padding)")
            instruments = instruments[:n_kg]
        print(f"  Found {len(instruments)} instrument(s)")

        # Zone/voice building.  Each parsed layer becomes a "unit" carrying its zone
        # plus a parameter signature; units are then lane-allocated into voices so
        # that overlapping (simultaneously-sounding) layers become *parallel* voices
        # — the E4XT plays one zone per note per voice, so stacked MPC layers must be
        # separate voices to actually stack (fixes thin/collapsed pads, e.g. the detuned-stack split preset).
        _zone_play_warned: set = set()   # warn once per mode, not once per keygroup
        all_units: list = []          # list of (params_key, inst_idx, ZoneMapping, non_transpose)
        inst_params: dict = {}        # inst_idx -> dict of voice-level params (env/filter/lfo)

        # KeygroupWheelToLfo (program-level, 0-1): on the MPC the mod wheel gates the
        # LFO depth — at rest (wheel down) the LFO contributes (1 - wheel) of its
        # programmed depth, reaching full depth only at full wheel.  We pass the FULL
        # LFO depth plus `wheel_to_lfo` to the writer, which reproduces this on the
        # E4XT via a cascaded ModWheel→CordN-Amount cord (RE'd 2026-06-13 — see
        # e4b_writer / docs/re_procedures/re_suite.md §3-4).
        wheel_to_lfo = max(0.0, min(1.0, float(_get_text(root, './/KeygroupWheelToLfo', '0.0'))))

        for inst_idx, instrument in enumerate(instruments):
            lo_key = int(_get_text(instrument, 'LowNote',  '0'))
            hi_key = int(_get_text(instrument, 'HighNote', '127'))

            # A drum pad carries no key range of its own -- every pad in the
            # corpus is LowNote 0 / HighNote 127, because the PAD is the key.
            # Collapse it onto its mapped note; `pad_key` also becomes the
            # zone's root below, which is what stops it keytracking.
            pad_key = None
            if is_drum:
                try:
                    pad_no = int(instrument.get('number', inst_idx + 1)) - 1
                except ValueError:
                    pad_no = inst_idx
                pad_key = pad_notes.get(
                    pad_no, (_PAD_BASE_NOTE + pad_no) % 128)
                lo_key = hi_key = pad_key

            # IgnoreBaseNote is the MPC's real "non-transpose" flag (CWM
            # MPCModernDetector: the per-layer KeyTrack field is only honoured when
            # IgnoreBaseNote=True).  RootNote=0 is the "root unset" sentinel, NOT a
            # non-transpose signal — see docs/RESOLUTION_NOTES.md.
            ignore_base = _get_text(instrument, 'IgnoreBaseNote', 'False').strip().lower() == 'true'
            try:
                _warn_zone_play(int(float(_get_text(instrument, 'ZonePlay', '1') or 1)),
                                inst_idx, _zone_play_warned)
            except ValueError:
                pass
            # Tuning: MPC stores it at instrument *and* layer level; both are summed.
            inst_coarse = int(_get_text(instrument, 'TuneCoarse', '0'))
            inst_fine   = int(_get_text(instrument, 'TuneFine',  '0'))

            # Envelope *times* are normalised 0–1 controls, not seconds — convert
            # via the hardware-measured MPC curve (sustain values are levels: kept).
            # 2.x and 3.x use different constants; see §MPCENV.
            _env = lambda tag, dflt='0.0': _xpm_env_to_seconds(
                float(_get_text(instrument, tag, dflt)), mpc3=is_mpc3)
            env_attack  = _env('VolumeAttack')
            env_decay   = _env('VolumeDecay')
            env_sustain = float(_get_text(instrument, 'VolumeSustain', '1.0'))
            env_release = _env('VolumeRelease')

            filt_type    = int(  _get_text(instrument, 'FilterType',    '0'))
            # MPC 3's `Cutoff` is a normalised knob, NOT a position on the E4B
            # 57 Hz–20 kHz exponential that `filter_cutoff` is contractually
            # defined as.  Convert knob → Hz → contract, the same route every
            # Hz-aware parser takes (§MPCCUTOFF).  The MPC 2.x path has no
            # measured curve yet, so it keeps its historical pass-through.
            _cut_raw = float(_get_text(instrument, 'Cutoff', '1.0'))
            filt_cutoff = (hz_to_e4b_cutoff(_xpm3_cutoff_to_hz(_cut_raw))
                           if is_mpc3 else _cut_raw)
            filt_res     = float(_get_text(instrument, 'Resonance',     '0.0'))
            filt_env_amt = float(_get_text(instrument, 'FilterEnvAmt',  '0.0'))
            filt_atk     = _env('FilterAttack')
            filt_dec     = _env('FilterDecay')
            filt_sus     = float(_get_text(instrument, 'FilterSustain', '1.0'))
            filt_rel     = _env('FilterRelease')
            filt_keytrk  = max(-1.0, min(1.0, float(_get_text(instrument, 'FilterKeytrack',   '0.0'))))
            filt_velamt  = max(-1.0, min(1.0, float(_get_text(instrument, 'VelocityToFilter', '0.0'))))

            # LFO (MPC has a single per-keygroup LFO → maps to E4B LFO1).  Only
            # emit it when something is actually routed (LfoPitch / LfoCutoff),
            # otherwise leave the EOS default so the voice stays byte-clean.
            lfo_pitch  = max(-1.0, min(1.0, float(_get_text(instrument, 'LfoPitch',  '0.0'))))
            lfo_cutoff = max(-1.0, min(1.0, float(_get_text(instrument, 'LfoCutoff', '0.0'))))
            lfo_block  = instrument.find('LFO')
            lfo_active = (abs(lfo_pitch) > 0.001 or abs(lfo_cutoff) > 0.001) and lfo_block is not None
            if lfo_active:
                lfo_rate_hz = lfo_knob_to_hz(float(_get_text(lfo_block, 'Rate', '0.5')))
                lfo_shape   = _xpm_lfo_shape(_get_text(lfo_block, 'Type', 'Sine'))
                # MPC <Reset> True = retrigger phase per note = E4B Key Sync;
                # False = free-run.  model lfo*_sync: False=Key Sync, True=Free Run.
                lfo_sync    = (_get_text(lfo_block, 'Reset', 'False').lower() != 'true')
                # MPC <Sync> = tempo-lock division index (0 = free; see _MPC_SYNC_DIV).
                try:
                    lfo_sync_div = int(_get_text(lfo_block, 'Sync', '0') or 0)
                except ValueError:
                    lfo_sync_div = 0
                # When synced the MPC ignores <Rate> (it sits at the default ~0.5 ≈
                # 2 Hz for every division — the §D/§P bug).  The tempo lives in the
                # project, not the XPM, so reproduce the division's speed as a fixed
                # rate at a 120 BPM reference (see _mpc_sync_hz).
                if lfo_sync_div:
                    _synced_hz = _mpc_sync_hz(lfo_sync_div)
                    if _synced_hz is not None:
                        lfo_rate_hz = _synced_hz

            # Per-instrument voice parameters (env / filter / LFO).  Layers from
            # instruments with identical params merge into one voice (a keymap);
            # overlapping layers split into parallel voices (see lane-allocation).
            pdict = dict(
                env_attack=env_attack, env_decay=env_decay,
                env_sustain=env_sustain, env_release=env_release,
                filter_type=filt_type, filter_cutoff=filt_cutoff,
                filter_resonance=filt_res, filter_env_amount=filt_env_amt,
                filter_env_attack=filt_atk, filter_env_decay=filt_dec,
                filter_env_sustain=filt_sus, filter_env_release=filt_rel,
                filter_keytrack=filt_keytrk, velocity_to_filter=filt_velamt,
            )
            # MPC 3 second LFO (<LFO2>, emitted only by the JSON converter — an
            # MPC 2.x XML program never has one, so this is inert there).  Routed
            # to pitch only, which is what VoiceLayer's lfo2_* models.
            lfo2_block = instrument.find('LFO2')
            if lfo2_block is not None:
                _l2_pitch = max(-1.0, min(1.0,
                                float(_get_text(lfo2_block, 'Pitch', '0.0'))))
                if abs(_l2_pitch) > 0.001:
                    pdict.update(
                        lfo2_rate=lfo_knob_to_hz(float(_get_text(lfo2_block, 'Rate', '0.5'))),
                        lfo2_shape=_xpm_lfo_shape(_get_text(lfo2_block, 'Type', 'Sine')),
                        lfo2_to_pitch=_l2_pitch,
                    )

            if lfo_active:
                # Full LFO depth + wheel_to_lfo → writer splits into static + wheel-
                # gated cords (faithful KeygroupWheelToLfo gating).
                pdict.update(
                    lfo1_rate=lfo_rate_hz, lfo1_shape=lfo_shape, lfo1_sync=lfo_sync,
                    lfo1_sync_division=lfo_sync_div,
                    lfo1_to_pitch=lfo_pitch,
                    lfo1_to_filter=lfo_cutoff,
                    wheel_to_lfo=wheel_to_lfo,
                )
            iparam_tuple = tuple(sorted(
                (k, round(v, 6) if isinstance(v, float) else v) for k, v in pdict.items()
            ))
            inst_params[iparam_tuple] = pdict

            for layer in instrument.findall('Layers/Layer'):
                sample_name = _get_text(layer, 'SampleName', '')
                if not sample_name:
                    continue

                vel_lo = int(_get_text(layer, 'VelStart', '0'))
                vel_hi = int(_get_text(layer, 'VelEnd',   '127'))
                # RootNote=0 is the MPC "root unset" sentinel (NOT non-transpose).
                raw_root = int(_get_text(layer, 'RootNote', '0'))
                lay_coarse   = int(_get_text(layer, 'TuneCoarse', '0'))
                lay_fine     = int(_get_text(layer, 'TuneFine',  '0'))
                coarse_tune  = inst_coarse + lay_coarse      # semitones → vpar[35]
                fine_cents   = inst_fine + lay_fine          # cents → vpar[36]

                # Non-transpose (fixed pitch) iff IgnoreBaseNote, OR a *full-range*
                # root-unset layer (0-127 oscillator/texture with no key info, e.g.
                # DX7 "Chain-Synth Oscillators").  Every other root-unset keygroup is
                # a normal multisample zone — even wide drone/"UniDrone" splits are
                # meant to play CHROMATICALLY (Jan: the wide-drone preset must track per key) — so
                # it key-tracks with root = keygroup LowNote (CWM writer fallback),
                # which matches the sample's recorded pitch (the pack roots each
                # sample at its keygroup low note).  Option B — RESOLUTION_NOTES.md.
                full_range = (lo_key <= 0 and hi_key >= 127)
                non_transpose = ignore_base or (raw_root == 0 and full_range)

                vol_linear = float(_get_text(layer, 'Volume', '1.0'))
                volume = 20.0 * math.log10(max(vol_linear, 1e-6))
                # Pan lives at BOTH the keygroup (Instrument) and layer level (0-1,
                # 0.5=center).  Many MPC pads pan per keygroup (e.g. the wide-drone preset's
                # A/B copies hard L/R for stereo width) with the layer left centered,
                # so sum both and clamp.
                inst_pan  = (float(_get_text(instrument, 'Pan', '0.5')) - 0.5) * 2.0
                layer_pan = (float(_get_text(layer,      'Pan', '0.5')) - 0.5) * 2.0
                pan = max(-1.0, min(1.0, inst_pan + layer_pan))

                # MPC slice playback (Pad Start/End + Pad Loop).  Same sample at a
                # different slice window is a distinct SampleData → key the cache by
                # the slice too.
                slice_start  = int(_get_text(layer, 'SliceStart', '0'))
                slice_end    = int(_get_text(layer, 'SliceEnd',   '0'))
                slice_loop   = int(_get_text(layer, 'SliceLoop',  '0'))
                slice_lstart = int(_get_text(layer, 'SliceLoopStart', '0'))
                slice_lend   = int(_get_text(layer, 'SliceLoopEnd', '0'))
                # <Loop> is the MPC layer's master loop toggle — its authority over any
                # embedded WAV `smpl` loop (the MPC ignores the WAV loop when False).
                # Absent → default True to preserve legacy WAV-smpl-loop behaviour.
                loop_on      = _get_text(layer, 'Loop', 'True').strip().lower() == 'true'
                # Reverse playback and loop crossfade are both baked into the
                # PCM (no target format carries either as a flag), so the same
                # WAV at different settings is a DIFFERENT SampleData and must
                # not share a cache entry -- see §XPMGAPS.
                reverse = _get_text(layer, 'Direction', '0').strip() not in ('', '0')
                slice_xf = int(float(_get_text(
                    layer, 'SliceLoopCrossFadeLength', '0') or 0))
                cache_key = (sample_name, slice_start, slice_end, slice_loop,
                             slice_lstart, loop_on, slice_lend, reverse, slice_xf)

                if cache_key not in sample_cache:
                    # MPC 3 names its file exactly; only search when it cannot.
                    wav_path = (_resolve_mpc3_sample(layer, mpc3_sample_dir)
                                or _find_wav(sample_name, wav_dir))
                    if wav_path:
                        sd = load_wav(str(wav_path), sample_name)
                        if sd:
                            _apply_slice(sd, slice_start, slice_end, slice_loop,
                                         slice_lstart, loop_on, slice_lend)
                            if slice_xf > 0 and _apply_loop_crossfade(sd, slice_xf):
                                print(f"    Loop crossfade: {slice_xf} frames "
                                      f"baked into '{sd.name}'")
                            if reverse:
                                _apply_reverse(sd)
                                print(f"    Reversed '{sd.name}' (Direction=1)")
                            # Deduplicate truncated names within this XPM.
                            #
                            # Counting per base and trusting the rewrite was
                            # silent DATA LOSS: it never checked the result was
                            # actually free.  A base already ending in the digit
                            # being appended came back UNCHANGED
                            # ('…_2600_C-1' + '1' -> '…_2600_C-1', and names
                            # ending -1/A1/C1 are everywhere), and a rewrite
                            # could equally land on a different real sample
                            # ('…__C0' + '1' -> '…__C1').  Zones address samples
                            # by NAME, so the loser was loaded, appended and
                            # logged, then never referenced -- measured on one
                            # auto-sampled program: 97 WAVs, 57 distinct names,
                            # 97 zones, 40 of them sounding a namesake.
                            #
                            # Advance until the candidate is genuinely unused,
                            # against the names actually taken.
                            # Re-derive under this program's chosen rule:
                            # load_wav defaults to the tail, which is wrong
                            # for a drum kit (see _prefers_tail).
                            sd.name = _safe_name(sample_name, tail=_name_tail)
                            sd.name = _unique_sample_name(sd.name, _names_taken)
                            _names_taken.add(sd.name)
                            sample_cache[cache_key] = sd
                            # Sample's recorded root (WAV smpl unity, None if absent)
                            # — the RootNote=0 playback root (fixes JR +36 transpose).
                            sample_wav_root[cache_key] = _read_smpl_root(
                                open(wav_path, 'rb').read())
                            bank.samples.append(sd)
                            print(f"    Loaded sample: {sd.name} ({sd.sample_rate}Hz, {len(sd.data)//2} frames)")
                    else:
                        print(f"    [WARN] Sample not found: {sample_name}")
                        _missing_wavs.add(sample_name)

                sd_cached = sample_cache.get(cache_key)
                safe_sname = (sd_cached.name if sd_cached
                              else _safe_name(sample_name, tail=_name_tail))

                # Playback root: non-transpose → 60; explicit RootNote → RootNote-1;
                # RootNote=0 (MPC unset) → the sample's WAV-recorded pitch (smpl unity),
                # falling back to the keygroup low note when the WAV has no unity note.
                #
                # Override full_range+root-unset → non_transpose when the WAV smpl chunk
                # contains a unity note: the sample IS pitched (e.g. AXELEAD smpl_unity=48).
                # IgnoreBaseNote is left alone — that's an explicit user setting.
                if non_transpose and not ignore_base:
                    _wr = sample_wav_root.get(cache_key)
                    if _wr is not None:
                        non_transpose = False
                if non_transpose:
                    root = 60
                elif raw_root > 0:
                    root = raw_root - 1
                else:
                    _wr = sample_wav_root.get(cache_key)
                    root = _wr if _wr is not None else lo_key
                # Fold MPC TuneCoarse into the root note so K2000 key-tracking matches.
                # TuneCoarse > 0 means MPC plays everything that many semitones higher;
                # lowering root by the same amount makes K2000 apply the same transpose.
                root = max(0, min(127, root - coarse_tune))
                # A drum pad plays its sample at NATIVE pitch on its own key.
                # Making the root the key is what expresses that in both target
                # formats: EOS transposes by (key - root) = 0, and the K2000's
                # `tuning = 100*(r_sample - r_zone)` cancels its auto-transpose
                # exactly.  It also keeps the zone clear of krz_writer's
                # up-pitch ceiling, which is measured from the zone root.
                # TuneCoarse is deliberately NOT folded in here -- on a pad it
                # is a deliberate pitch offset of the hit, so it must survive as
                # a real transpose rather than being cancelled.
                if pad_key is not None:
                    root = max(0, min(127, pad_key - coarse_tune))
                if sd_cached is not None:
                    sd_cached.root_note = root

                zone = ZoneMapping(
                    sample_name = safe_sname,
                    lo_key      = lo_key,
                    hi_key      = hi_key,
                    lo_vel      = vel_lo,
                    hi_vel      = vel_hi,
                    root_key    = root,
                    volume      = volume,
                    pan         = pan,
                    fine_tune   = fine_cents,
                    coarse_tune = coarse_tune,
                )
                all_units.append(((iparam_tuple, non_transpose), zone))

        # Lane-allocate units into voices: zones that overlap in key AND velocity
        # must go to *separate* voices (the E4XT plays one zone per note per voice,
        # so stacked MPC layers only stack as parallel voices); non-overlapping zones
        # sharing the same params collapse into one voice (a keymap).
        def _overlaps(a: ZoneMapping, b: ZoneMapping) -> bool:
            return not (a.hi_key < b.lo_key or a.lo_key > b.hi_key
                        or a.hi_vel < b.lo_vel or a.lo_vel > b.hi_vel)

        # Drop fully-identical units first.  Some MPC presets stack the *same*
        # sample/zone dozens of times (e.g. the wide-drone preset layers one slice 122×)
        # as a polyphony/unison trick; on the E4XT that's just N identical voices
        # adding level, not character, and would blow the voice budget.  Keep one.
        _seen_units: set = set()
        deduped_units: list = []
        for sig, zone in all_units:
            key = (sig, zone.sample_name, zone.lo_key, zone.hi_key,
                   zone.lo_vel, zone.hi_vel, zone.root_key, zone.fine_tune)
            if key in _seen_units:
                continue
            _seen_units.add(key)
            deduped_units.append((sig, zone))
        if len(deduped_units) < len(all_units):
            print(f"    Deduplicated {len(all_units) - len(deduped_units)} identical stacked unit(s)")

        voice_lanes: list = []   # list of [sig, VoiceLayer]
        for sig, zone in deduped_units:
            placed = False
            for lane_sig, v in voice_lanes:
                if lane_sig == sig and not any(_overlaps(z, zone) for z in v.zones):
                    v.zones.append(zone)
                    placed = True
                    break
            if not placed:
                iparam_tuple, non_transpose = sig
                v = VoiceLayer(non_transpose=non_transpose)
                for k, val in inst_params[iparam_tuple].items():
                    setattr(v, k, val)
                v.zones.append(zone)
                voice_lanes.append((sig, v))

        # Cap to the E4XT per-preset voice limit, keeping the widest-coverage voices
        # (shared with the SFZ parser; limit pinned by the VOICECOUNT RE bank).
        built = [v for _sig, v in voice_lanes if v.zones]
        capped = cap_voices_by_coverage(built)
        if len(capped) < len(built):
            print(f"    [WARN] {len(built)} simultaneous voices — capped to "
                  f"{len(capped)} (E4XT voice limit); narrowest layers dropped")
        for voice in capped:
            preset.voices.append(voice)

        if not preset.voices:
            # A program with no sampled content contributes nothing, and an
            # empty preset in a bank is worse than no preset: it occupies a
            # slot and tells the user a program converted when it did not.
            # Real: 55 of the 224 drum programs in the MPC One backup are kits
            # that were created but never filled.  Gathering a project skips
            # them and keeps the rest; a single such file yields a bank with no
            # presets, which convert.py already reports as nothing to do.
            print(f"  [SKIP] '{preset.name}': no sampled content")
            return

        bank.presets.append(preset)
        print(f"  Preset '{preset.name}': {len(preset.voices)} voice(s), "
              f"{len(bank.samples)} sample(s)")
        return

    for _name, _root in program_trees:
        _build_preset(_root, _name)
    if len(program_trees) > 1:
        print(f"  {len(bank.presets)} preset(s), {len(bank.samples)} sample(s) "
              f"total in '{bank.name}'")

    # Post-build invariant. A zone's only handle on its audio is the sample
    # NAME, so two samples sharing one name means the second is unreachable and
    # its zones sound the first — silent data loss that used to happen and
    # logged nothing (see _unique_sample_name).
    #
    # NOT "zones <= distinct samples", which the bug report suggested: many
    # zones legitimately share one sample (velocity layers, split key ranges),
    # so that test would fire constantly on healthy banks. The real invariants
    # are that names are unique and that every zone resolves.
    _names = [s.name for s in bank.samples]
    if len(set(_names)) != len(_names):
        dupes = sorted({n for n in _names if _names.count(n) > 1})
        print(f"  [ERROR] {len(_names) - len(set(_names))} sample(s) share a "
              f"name with another — their zones will sound the wrong audio: "
              f"{', '.join(dupes[:6])}")
    # Exclude zones whose WAV was simply absent: that is a missing FILE, not a
    # name-resolution fault, and it already produced its own warning. Reporting
    # it here too made the check fire on 11 corpus files that are merely
    # incomplete -- a check that cries wolf gets ignored when it matters.
    _unresolved = {_safe_name(n, tail=True) for n in _missing_wavs} | \
                  {_safe_name(n, tail=False) for n in _missing_wavs}
    _missing = sorted({z.sample_name for p in bank.presets for v in p.voices
                       for z in v.zones} - set(_names) - _unresolved)
    if _missing:
        print(f"  [ERROR] {len(_missing)} zone sample name(s) match no loaded "
              f"sample: {', '.join(_missing[:6])}")
    return bank


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_ALIASES = {
    'Db': 'C#', 'Eb': 'D#', 'Fb': 'E', 'Gb': 'F#',
    'Ab': 'G#', 'Bb': 'A#', 'Cb': 'B'
}

def _note_name_to_midi(note_str: str) -> int:
    """Convert note name like 'C3', 'F#4', 'Bb2' to MIDI number."""
    note_str = note_str.strip()
    if not note_str:
        return 60

    # Try to parse note + octave
    for i in range(len(note_str), 0, -1):
        note_part = note_str[:i]
        oct_part  = note_str[i:]
        # Normalize aliases
        note_part = NOTE_ALIASES.get(note_part, note_part)
        if note_part in NOTE_NAMES:
            try:
                octave = int(oct_part)
                # MPC uses C3=60 convention (same as MIDI standard C4=60 but -1 octave naming)
                midi = (octave + 2) * 12 + NOTE_NAMES.index(note_part)
                return max(0, min(127, midi))
            except ValueError:
                pass
    return 60  # fallback


def _get_text(elem, tag: str, default: str = '') -> str:
    """Safely get text from a child element."""
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default


# First-occurrence file index per search directory, for _find_wav's slow
# paths.  Bounded FIFO so converting many unrelated trees can't grow it
# without limit.
_DIR_INDEX_CACHE: dict = {}


def _dir_first_occurrence_index(search_dir: Path):
    """`({name: path}, {lowercased_name: (position, path)})` for everything
    under `search_dir`, recording the FIRST occurrence of each in `rglob`
    traversal order.

    Replaces repeated `rglob` calls: `rglob(name)` and `rglob('*')` walk the
    tree in the same order, so the first entry with a given name in the full
    walk is the same path `rglob(name)` would have returned.  The recorded
    position lets the case-insensitive fallback reproduce "first match in
    traversal order" rather than "first matching candidate".

    One deliberate behaviour change: a sample name containing glob
    metacharacters (`[`, `?`, `*`) was previously interpreted as a PATTERN by
    `rglob`, so e.g. `Bass[12].wav` could resolve to `Bass1.wav`.  Lookups
    here are literal, which is what the caller means.
    """
    key = str(search_dir)
    cached = _DIR_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    by_name: dict = {}
    by_lower: dict = {}
    try:
        for pos, entry in enumerate(search_dir.rglob('*')):
            name = entry.name
            if name not in by_name:
                by_name[name] = entry
            lowered = name.lower()
            if lowered not in by_lower:
                by_lower[lowered] = (pos, entry)
    except OSError:
        pass
    if len(_DIR_INDEX_CACHE) >= 8:
        _DIR_INDEX_CACHE.pop(next(iter(_DIR_INDEX_CACHE)))
    _DIR_INDEX_CACHE[key] = (by_name, by_lower)
    return by_name, by_lower


def _find_wav(sample_name: str, search_dir: Path) -> Optional[Path]:
    """Search for a WAV file by name in the given directory and subdirectories."""
    basename = Path(sample_name).name

    # Build candidate names: the exact name first, then with .wav/.WAV appended.
    # The extension is appended even when the name ALREADY ends in .wav -- a
    # sample imported from `Foo.wav` is named "Foo.wav" in the program and
    # stored as `Foo.wav.WAV` on disk, so the double extension is real and
    # common (393 such files in one 2.x project of the MPC One backup).
    names = [basename]
    if Path(basename).suffix.lower() != '.wav':
        names += [basename + '.wav', basename + '.WAV']
    else:
        names += [basename + '.WAV', basename + '.wav']

    # Direct lookup first (fast path)
    for name in names:
        candidate = search_dir / name
        if candidate.exists():
            return candidate

    # Slow paths: the sample is not sitting directly in `search_dir`.  Both
    # the by-name search and the case-insensitive sweep used to walk the whole
    # tree *per lookup* (`rglob(name)` once per candidate name, then a full
    # `rglob('*')`), so an XPM referencing N missing samples paid N tree
    # walks.  One walk now builds a first-occurrence index that answers both,
    # memoized per directory.
    by_name, by_lower = _dir_first_occurrence_index(search_dir)

    # By exact name, candidates in priority order (same order as before).
    for name in names:
        hit = by_name.get(name)
        if hit is not None:
            return hit

    # Case-insensitive fallback.  The old loop returned the FIRST entry in
    # traversal order matching any candidate, which is not necessarily the
    # first candidate — so pick by recorded traversal position, not by
    # candidate order, to keep the same answer.
    lower_names = {n.lower() for n in names}
    best = None
    for ln in lower_names:
        entry = by_lower.get(ln)
        if entry is not None and (best is None or entry[0] < best[0]):
            best = entry
    return best[1] if best is not None else None
