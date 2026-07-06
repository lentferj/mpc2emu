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

import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import wave
import struct

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType, lfo_knob_to_hz,
    cap_voices_by_coverage,
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


def _be24_to_le16(raw: bytes) -> bytes:
    """Convert big-endian 24-bit signed PCM → little-endian 16-bit signed."""
    n = len(raw) // 3
    out = bytearray(n * 2)
    for i in range(n):
        b0, b1, b2 = raw[i*3], raw[i*3+1], raw[i*3+2]
        val = (b0 << 16) | (b1 << 8) | b2
        if val >= 0x800000:
            val -= 0x1000000
        struct.pack_into('<h', out, i * 2, val >> 8)
    return bytes(out)


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
        n = len(raw) // 4
        out = bytearray(n * 2)
        for i in range(n):
            v = struct.unpack_from('>i', raw, i * 4)[0]
            struct.pack_into('<h', out, i * 2, v >> 16)
        raw, sample_size = bytes(out), 16
    elif sample_size != 16:
        print(f"  [WARN] Unsupported AIFF bit depth {sample_size}: {aiff_path}")
        return None

    if channels == 2:
        raw, channels = _stereo_to_mono(raw)

    # Loop from INST + MARK
    loop_type  = LoopType.NO_LOOP
    loop_start = 0
    loop_end   = 0
    n_pcm = len(raw) // 2
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

        # Stereo -> mono downmix
        if channels == 2:
            raw, channels = _stereo_to_mono(raw)

        # Read loop points from SMPL chunk (wave module ignores this).
        # Clamp loop_end to actual loaded frame count — the SMPL chunk uses the
        # nominal WAV header frame count which can differ from what wave.readframes
        # actually delivers.
        n_actual = len(raw) // (2 * (1 if channels == 1 else 2))  # frames before mono-mix
        # After possible stereo→mono conversion, n_frames is already correct
        n_frames_loaded = len(raw) // 2   # 16-bit mono frames after conversion
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
                 loop_on: bool = True) -> None:
    """Apply MPC Pad-Start/End + Pad-Loop slice playback to a loaded sample.

    `slice_start`/`slice_end` are sample frames (Pad Start / Pad End); when set
    they trim the audio to that window.  `slice_loop` is the Pad-Loop enum
    (0=Off, 1=Forward, 2=Reverse, 3=Alternating); when on, the loop runs from the
    Loop Position (`slice_loop_start`) to the Pad End — rebased to the trimmed
    slice.  `loop_on` is the layer's <Loop> master toggle.  The MPC reads the WAV
    `smpl` loop directly and plays it as a forward loop, EXCEPT a full-sample
    placeholder loop (`_is_full_sample_loop`), which it drops to a one-shot — so we
    only discard the embedded loop when it is full-sample (and <Loop> off), keeping
    genuine tail/sustain loops (Annenberg one-shot vs Bass-MS20's tail loop).
    Units are mono 16-bit here (2 bytes/frame).  Verified against the MPC
    3.7 manual + measured WAV frame counts — see docs/RESOLUTION_NOTES.md."""
    bytes_per_frame = 2  # load_wav delivers 16-bit mono
    n_frames = len(sd.data) // bytes_per_frame

    # Case 1: No Pad End set — play full sample.
    if slice_end == 0:
        if slice_loop:
            loop_pos = max(0, slice_loop_start)
            if loop_pos >= n_frames - 1:
                loop_pos = 0
            sd.loop_start = loop_pos
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
        sd.loop_end   = n_frames - 1
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


def _convert_24_to_16(raw: bytes, channels: int) -> tuple:
    n_samples = len(raw) // 3
    out = bytearray(n_samples * 2)
    for i in range(n_samples):
        b0, b1, b2 = raw[i*3], raw[i*3+1], raw[i*3+2]
        val = (b2 << 16 | b1 << 8 | b0)
        if val >= 0x800000:
            val -= 0x1000000
        val16 = val >> 8
        struct.pack_into('<h', out, i * 2, val16)
    return bytes(out), 16


def _convert_8_to_16(raw: bytes) -> tuple:
    out = bytearray(len(raw) * 2)
    for i, b in enumerate(raw):
        val = (b - 128) * 256
        struct.pack_into('<h', out, i * 2, val)
    return bytes(out), 16


def _stereo_to_mono(raw: bytes) -> tuple:
    n_frames = len(raw) // 4  # 2 channels * 2 bytes
    out = bytearray(n_frames * 2)
    for i in range(n_frames):
        l = struct.unpack_from('<h', raw, i * 4)[0]
        r = struct.unpack_from('<h', raw, i * 4 + 2)[0]
        m = (l + r) // 2
        struct.pack_into('<h', out, i * 2, m)
    return bytes(out), 1


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
            # <Loop> is the MPC layer's master loop toggle — its authority over any
            # embedded WAV `smpl` loop (the MPC ignores the WAV loop when False).
            # Absent → default True to preserve legacy WAV-smpl-loop behaviour.
            loop_on      = _get_text(layer, 'Loop', 'True').strip().lower() == 'true'
            cache_key = (sample_name, slice_start, slice_end, slice_loop,
                         slice_lstart, loop_on)

            if cache_key not in sample_cache:
                wav_path = _find_wav(sample_name, wav_dir)
                if wav_path:
                    sd = load_wav(str(wav_path), sample_name)
                    if sd:
                        _apply_slice(sd, slice_start, slice_end, slice_loop, slice_lstart, loop_on)
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

    # Recursive search by name
    for name in names:
        for p in search_dir.rglob(name):
            return p

    # Case-insensitive fallback across all candidates
    lower_names = {n.lower() for n in names}
    for p in search_dir.rglob('*'):
        if p.name.lower() in lower_names:
            return p

    return None
