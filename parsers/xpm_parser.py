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
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import wave
import struct

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType, lfo_knob_to_hz,
    cap_voices_by_coverage, stereo_to_mono,
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
# Decay/Release) are normalised 0.0–1.0 controls, NOT seconds.  Hardware-
# measured on an MPC One (2026-06-09, XPM_VOL_DECAY): the control is a steep
# exponential — decay-to-(effectively-)silence ≈ 0.00079·e^(9.78·value) s
# (~×3.4 per 0.125 step; value 0 ≈ instant/silent, 1.0 ≈ 15 s).  Same curve is
# applied to attack/release and the filter envelope (MPC uses one time-curve
# for all segments).  See docs/re_procedures/xpm_envelope.md.
_XPM_ENV_A = 0.00079
_XPM_ENV_K = 9.78


def _xpm_env_to_seconds(value: float) -> float:
    """MPC normalised envelope value (0.0–1.0) → time in seconds."""
    return _XPM_ENV_A * math.exp(_XPM_ENV_K * max(0.0, min(1.0, value)))


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

    if channels == 2 and not PRESERVE_STEREO:
        raw, channels = _stereo_to_mono(raw)

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


def load_wav(wav_path: str, name: str) -> Optional[SampleData]:
    """Load WAV or AIFF/AIFC audio and return a SampleData (16-bit mono LE).
    AIFF: reads INST+MARK chunks for loop points and base note.
    WAV: reads SMPL chunk for loop points and unity note."""
    sfx = Path(wav_path).suffix.lower()
    if sfx in ('.aif', '.aiff'):
        return _load_aiff(wav_path, name)
    try:
        raw_file = open(wav_path, 'rb').read()

        with wave.open(wav_path, 'rb') as wf:
            channels   = wf.getnchannels()
            sampwidth  = wf.getsampwidth()
            framerate  = wf.getframerate()
            n_frames   = wf.getnframes()
            raw        = wf.readframes(n_frames)

        bit_depth = sampwidth * 8

        # Convert to 16-bit if necessary
        if bit_depth == 24:
            raw, bit_depth = _convert_24_to_16(raw, channels)
        elif bit_depth == 8:
            raw, bit_depth = _convert_8_to_16(raw)
        elif bit_depth != 16:
            print(f"  [WARN] Unsupported bit depth {bit_depth} in {wav_path}, skipping")
            return None

        # Stereo -> mono downmix (kept as-is when PRESERVE_STEREO)
        if channels == 2 and not PRESERVE_STEREO:
            raw, channels = _stereo_to_mono(raw)

        # Read loop points from SMPL chunk (wave module ignores this).
        # Clamp loop_end to actual loaded frame count — the SMPL chunk uses the
        # nominal WAV header frame count which can differ from what wave.readframes
        # actually delivers.
        n_actual = len(raw) // (2 * (1 if channels == 1 else 2))  # frames before mono-mix
        # Frames after any downmix.  With PRESERVE_STEREO the data is still
        # interleaved, so a frame is 2 bytes PER CHANNEL -- loop points are in
        # frames either way and must not shift when stereo is kept.
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
    Units are mono 16-bit here (2 bytes/frame).  Verified against the MPC
    3.7 manual + measured WAV frame counts — see docs/RESOLUTION_NOTES.md."""
    # 2 bytes per channel per frame: load_wav delivers mono normally, but
    # interleaved stereo under PRESERVE_STEREO.
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


def _convert_8_to_16(raw: bytes) -> tuple:
    """Unsigned 8-bit -> signed 16-bit, i.e. `(b - 128) * 256`.

    As little-endian int16 that is low byte 0 and high byte `b ^ 0x80`, so
    it is a zero fill interleaved with one bulk `bytes.translate`.
    """
    out = bytearray(len(raw) * 2)
    out[1::2] = raw.translate(_FLIP_SIGN8)
    return bytes(out), 16


# Opt-in stereo passthrough (convert.py --stereo).  Default False keeps every
# existing conversion byte-identical: sources are downmixed to mono as they
# always were.  When True, load_wav keeps interleaved stereo and the E4B
# writer emits a real stereo sample; the KRZ/EIII writers still downmix at
# their own entry points, so only the E4B path actually carries it through.
#
# Off by default deliberately: stereo DOUBLES every sample, and an E4B bank
# is capped at 128 MB, so flipping this silently would push existing banks
# over the limit and change the output of every conversion.
PRESERVE_STEREO = False


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
    if kind != 'SerialisableProgramData':
        raise ValueError(f"unsupported MPC 3 payload {kind!r} "
                          f"(only SerialisableProgramData is a program)")
    return header, payload.get('data', {})


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


def _mpc3_to_xml(data) -> 'ET.Element':
    """Build the MPC 2.x element tree this module already parses from an
    MPC 3.x JSON program."""
    root = ET.Element('MPCVObject')
    prog = ET.SubElement(root, 'Program')
    prog.set('type', 'Keygroup')
    ET.SubElement(prog, 'ProgramName').text = str(data.get('name', ''))

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
            else:
                lmode  = int(slice_info.get('LoopMode', 0) or 0)
                lstart = int(slice_info.get('LoopStart', 0) or 0)
                lend   = int(slice_info.get('End', 0) or 0)
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
    if is_mpc3_xpm(xpm_path):
        header, data = _mpc3_read(str(xpm_path))
        print(f"Parsing XPM (MPC {header[1]} JSON): {xpm_path}")
        root = _mpc3_to_xml(data)
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
        root = tree.getroot()

    bank = Bank(name=_safe_name(xpm_path.stem))
    preset = Preset(
        name           = _safe_name(xpm_path.stem),
        program_number = 0,
    )

    sample_cache: dict[str, SampleData] = {}
    # Tracks how many samples share the same truncated base name so we can
    # append a counter suffix to keep each sd.name unique within 16 chars.
    _name_count: dict[str, int] = {}
    # WAV smpl-chunk recorded root per cached sample (None if the WAV has no
    # unity note) — used as the RootNote=0 playback root instead of lo_key.
    sample_wav_root: dict[str, Optional[int]] = {}

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

    # Skip drum programs — each instrument is a pad hit, not a pitched zone.
    program_elem = root.find('Program')
    if program_elem is not None and program_elem.get('type', '') == 'Drum':
        print(f"  [SKIP] Drum program — not a Keygroup instrument")
        bank.presets.append(preset)
        return bank

    instruments = sorted(
        root.findall('.//Instrument'),
        key=lambda e: int(e.get('number', '9999'))
    )
    # The XPM always carries 128 Instrument slots; only the first
    # KeygroupNumKeygroups are real — the rest are padding (often duplicates of
    # one keygroup, e.g. SloBand Sweeper's 120 copies of a 24-47 C1 slice that
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
    # separate voices to actually stack (fixes thin/collapsed pads, e.g. Lazloz).
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

        # IgnoreBaseNote is the MPC's real "non-transpose" flag (CWM
        # MPCModernDetector: the per-layer KeyTrack field is only honoured when
        # IgnoreBaseNote=True).  RootNote=0 is the "root unset" sentinel, NOT a
        # non-transpose signal — see docs/RESOLUTION_NOTES.md.
        ignore_base = _get_text(instrument, 'IgnoreBaseNote', 'False').strip().lower() == 'true'
        # Tuning: MPC stores it at instrument *and* layer level; both are summed.
        inst_coarse = int(_get_text(instrument, 'TuneCoarse', '0'))
        inst_fine   = int(_get_text(instrument, 'TuneFine',  '0'))

        # Envelope *times* are normalised 0–1 controls, not seconds — convert
        # via the hardware-measured MPC curve (sustain values are levels: kept).
        env_attack  = _xpm_env_to_seconds(float(_get_text(instrument, 'VolumeAttack',  '0.0')))
        env_decay   = _xpm_env_to_seconds(float(_get_text(instrument, 'VolumeDecay',   '0.0')))
        env_sustain = float(_get_text(instrument, 'VolumeSustain', '1.0'))
        env_release = _xpm_env_to_seconds(float(_get_text(instrument, 'VolumeRelease', '0.0')))

        filt_type    = int(  _get_text(instrument, 'FilterType',    '0'))
        filt_cutoff  = float(_get_text(instrument, 'Cutoff',        '1.0'))
        filt_res     = float(_get_text(instrument, 'Resonance',     '0.0'))
        filt_env_amt = float(_get_text(instrument, 'FilterEnvAmt',  '0.0'))
        filt_atk     = _xpm_env_to_seconds(float(_get_text(instrument, 'FilterAttack',  '0.0')))
        filt_dec     = _xpm_env_to_seconds(float(_get_text(instrument, 'FilterDecay',   '0.0')))
        filt_sus     = float(_get_text(instrument, 'FilterSustain', '1.0'))
        filt_rel     = _xpm_env_to_seconds(float(_get_text(instrument, 'FilterRelease', '0.0')))
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
            # meant to play CHROMATICALLY (Jan: SloBand must track per key) — so
            # it key-tracks with root = keygroup LowNote (CWM writer fallback),
            # which matches the sample's recorded pitch (the pack roots each
            # sample at its keygroup low note).  Option B — RESOLUTION_NOTES.md.
            full_range = (lo_key <= 0 and hi_key >= 127)
            non_transpose = ignore_base or (raw_root == 0 and full_range)

            vol_linear = float(_get_text(layer, 'Volume', '1.0'))
            volume = 20.0 * math.log10(max(vol_linear, 1e-6))
            # Pan lives at BOTH the keygroup (Instrument) and layer level (0-1,
            # 0.5=center).  Many MPC pads pan per keygroup (e.g. SloBand Sweeper's
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
            cache_key = (sample_name, slice_start, slice_end, slice_loop,
                         slice_lstart, loop_on, slice_lend)

            if cache_key not in sample_cache:
                wav_path = _find_wav(sample_name, wav_dir)
                if wav_path:
                    sd = load_wav(str(wav_path), sample_name)
                    if sd:
                        _apply_slice(sd, slice_start, slice_end, slice_loop,
                                     slice_lstart, loop_on, slice_lend)
                        # Deduplicate truncated names within this XPM.
                        base = sd.name
                        n = _name_count.get(base, 0)
                        if n > 0:
                            suffix = str(n)
                            sd.name = base[:16 - len(suffix)] + suffix
                        _name_count[base] = n + 1
                        sample_cache[cache_key] = sd
                        # Sample's recorded root (WAV smpl unity, None if absent)
                        # — the RootNote=0 playback root (fixes JR +36 transpose).
                        sample_wav_root[cache_key] = _read_smpl_root(
                            open(wav_path, 'rb').read())
                        bank.samples.append(sd)
                        print(f"    Loaded sample: {sd.name} ({sd.sample_rate}Hz, {len(sd.data)//2} frames)")
                else:
                    print(f"    [WARN] Sample not found: {sample_name}")

            sd_cached = sample_cache.get(cache_key)
            safe_sname = sd_cached.name if sd_cached else _safe_name(sample_name, tail=True)

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
    # sample/zone dozens of times (e.g. SloBand Sweeper layers one slice 122×)
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

    bank.presets.append(preset)
    print(f"  Preset '{preset.name}': {len(preset.voices)} voice(s), "
          f"{len(bank.samples)} sample(s)")
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

    # Build candidate names: exact, plus .wav/.WAV when no extension is present
    names = [basename]
    if not Path(basename).suffix:
        names += [basename + '.wav', basename + '.WAV']

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
