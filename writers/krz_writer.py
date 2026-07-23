# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# KRZ binary layout derived from:
#   KurzFiler (GPL-2.0), Marc Halbrügge,
#     https://kurzfiler.sourceforge.io/
# Structure verified against KPOWER.KRZ (K2000 production soundset).
# No source code was copied.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
Kurzweil K2000/K2500/K2600 KRZ File Writer
-------------------------------------------
Produces a .KRZ file readable by Kurzweil K-series samplers.

KRZ File Layout (big-endian throughout — Motorola 68000 platform)
-------------------------------------------------------------------
  File header          32 bytes
    magic[4]           "PRAM"
    osize (int32)      byte offset where sample PCM data begins (written last)
    rest[6] (int32)    rest[2] = 353 (firmware version); others = 0

  Object section       variable
    Each object:
      blocksize (int32)  negative total block size including itself
      hash (uint16)      (type<<10) + id  for types ≤ 42
      size (uint16)      filled by writefinish: end - &size + 2
      ofs  (uint16)      name_len+3 (odd) or name_len+4 (even)
      name (ASCII)       max 16 chars, null-terminated + pad to even
      object data        type-specific
    End marker: int32 = 0

  Sample PCM section   variable
    Raw 16-bit signed BE PCM, word-addressed from osize

Object types (type code → hash base)
  T_PROGRAM = 36  →  0x9000 + id   (VAST program)
  T_KEYMAP  = 37  →  0x9400 + id   (sample key/velocity mapping)
  T_SAMPLE  = 38  →  0x9800 + id   (sample header + metadata)
  (T_FX     = 28  →  0x7000 + id   FX/Studio effects — present in production
   soundsets but NOT written here; our programs reference ROM effects. Verified
   2026-06-14: 201/201 real Soundsets KRZs parse with exactly types 28/36/37/38.)

Program object (KProgram)
  Sequence of tagged segments (1 byte tag + N bytes data):
    0x08  PGMSEGTAG  15 bytes  global program settings
    0x09  LYRSEGTAG  15 bytes  per-layer range/enable settings
    0x20  ENCSEGTAG  15 bytes  encoder/control parameters
    0x21  ENVSEGTAG  15 bytes  amplitude envelope
    0x40  CALSEGTAG  31 bytes  keymap reference
    0x50-0x53        15 bytes  pitch/pan/amp/filter defaults
  Terminated by int16 = 0

Keymap object (KKeymap)
  method = 0x0013  (2-byte tuning | 2-byte sampleID | 1-byte subSample)
  128 key entries per velocity level, single level spanning all velocities
  Level[j] on disk = (8-j)*2  (single-level encoding, read back → all 0)
  Each entry: tuning (int16 BE) + sampleID (int16 BE) + SSNr (uint8)
  tuning = constant per-zone fine offset 100*(R_sample - R_zone) (usually 0);
           the K2000 transposes each key from the sample rootkey + centsPerEntry
  basePitch    = 0   (matches every real production soundset)

Sample object (KSample)
  Fixed 12-byte header: baseID(=1), numHeaders(=0 mono/1 stereo), HeadersOfs(=8),
                        flags(0=mono/1=stereo), ks1, copyID, ks2
  Per channel: 32-byte Soundfilehead
    rootkey(1), flags(1)=0x70, volumeAdjust(1), altVolumeAdjust(1),
    maxPitch(2), offsetToName(2), sampleStart(4), altSampleStart(4)=start,
    sampleLoopStart(4), sampleEnd(4), offsetToEnvelope(2),
    altOffsetToEnvelope(2), samplePeriod(4)
  2× Envelope (12 bytes each): [-1, 1, 0, 0, -1600, 0]
  sampleStart/End in words (uint16 samples), absolute from osize
  Soundfilehead.flags = 0x70 for any playable RAM sample (0x40 alone = silent)
  maxPitch = round(100*rootkey + 1200*log2(48000/sample_rate))
"""

import copy
import math
import struct
from typing import List, Tuple

from models.common import Bank, Preset, SampleData, VoiceLayer, LoopType
from processors.loop_renderer import bake_alternating_loop


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

T_PROGRAM = 36
T_KEYMAP  = 37
T_SAMPLE  = 38

PGMSEGTAG = 0x08
LYRSEGTAG = 0x09
FXSEGTAG  = 0x0F
ENCSEGTAG = 0x20
ENVSEGTAG = 0x21
CALSEGTAG = 0x40

KRZ_SOFTWARE_VERSION = 353   # K2000 firmware v3.53 (KHeader.rest[2])

# Keymap: method bits
# 0x10 = 2-byte tuning, 0x02 = 2-byte sampleID, 0x01 = 1-byte subSample
# method 0x13 (per-entry tuning+sampleID+subSample) is what the K2000 itself writes
# when it saves a keymap (confirmed against a hardware-edited save).
KEYMAP_METHOD = 0x0013
KEYMAP_ENTRY_SIZE = 5  # Method2Size(0x13) = 2+2+1

NUM_KEYS = 128          # K2000 keyboard range
_MAX_KRZ_LAYERS = 32    # K2000 hardware maximum layers per program
NUM_VELO_LEVELS = 8     # K2000 velocity buckets (ppp..fff)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _hash(type_code: int, obj_id: int) -> int:
    return (type_code << 10) + obj_id


def _seg_len(tag: int) -> int:
    if tag in (PGMSEGTAG, LYRSEGTAG):
        return 15
    if tag == FXSEGTAG:
        return 7
    masked = tag & 0xF8
    if masked == 0x18:   # FUNSEGTAG
        return 3
    if masked in (0x10, 0x14, 0x68):   # ASR, LFO, KDFX
        return 7
    if masked in (0x20, 0x50):   # ENC, HOB
        return 15
    if masked in (0x40, 0x78):   # CAL, KB3
        return 31
    return 0


def _pack_segment(tag: int, data: bytes) -> bytes:
    length = _seg_len(tag)
    padded = data[:length].ljust(length, b'\x00')
    return struct.pack('>B', tag) + padded


def _compute_sample_period(sample_rate: int) -> int:
    return round(1_000_000_000.0 / sample_rate)


def _compute_max_pitch(sample_rate: int, root_note: int) -> int:
    # The MIDI pitch (×100 cents) at which the sample, transposed upward, reaches
    # the K2000's 48 kHz internal playback ceiling.  Reverse-engineered from real
    # Patchman soundsets (PMVOL002): maxPitch = 100*root + 1200*log2(48000/sr)
    # (sr=30 kHz → +814, sr=15 kHz → +2014, both confirmed).
    return int(round(
        100 * root_note + 1200.0 * math.log(48000.0 / sample_rate, 2)
    ))


def _compute_base_pitch(sample_rate: int) -> int:
    return int(math.ceil(
        1200.0 * math.log(96000.0 / sample_rate) / math.log(2.0)
    ))


# ---------------------------------------------------------------------------
# Object block writer  (mirrors KObject.writestart / writefinish)
# ---------------------------------------------------------------------------

class _BlockWriter:
    """
    Writes one K2000 object block to an open binary file.

    On-disk layout after begin():
        [4]  blocksize placeholder (int32 BE, negative, filled by end())
        [2]  hash (uint16 BE)
        [2]  size placeholder (filled by end())
        [2]  ofs  = name_len + 3|4
        [n]  name bytes
        [1|2] null terminator + padding

    Call begin(name), write object-specific bytes, then call end().
    """

    def __init__(self, f, hash_val: int):
        self.f = f
        self.hash_val = hash_val

    def begin(self, name: str) -> None:
        f = self.f
        self._block_pos = f.tell()
        f.write(struct.pack('>i', 0))          # blocksize placeholder

        f.write(struct.pack('>H', self.hash_val))
        self._size_pos = f.tell()
        f.write(struct.pack('>H', 0))          # size placeholder

        nb = name.encode('ascii', errors='replace')[:16]
        n = len(nb)
        if n % 2 == 0:
            ofs = n + 4
            f.write(struct.pack('>H', ofs))
            f.write(nb)
            f.write(b'\x00\x00')
        else:
            ofs = n + 3
            f.write(struct.pack('>H', ofs))
            f.write(nb)
            f.write(b'\x00')

    def end(self) -> None:
        f = self.f
        # writefinish: pad to 2-byte boundary
        pos = f.tell()
        if pos % 2:
            f.write(b'\x00')
            pos = f.tell()
        size = pos - self._size_pos + 2
        f.seek(self._size_pos)
        f.write(struct.pack('>H', size))
        f.seek(pos)
        # writeobjects: pad to 4-byte boundary
        while f.tell() % 4:
            f.write(b'\x00')
        # fill blocksize
        end = f.tell()
        f.seek(self._block_pos)
        f.write(struct.pack('>i', self._block_pos - end))
        f.seek(end)


# ---------------------------------------------------------------------------
# Sample object  (KSample + Soundfilehead + Envelopes)
# ---------------------------------------------------------------------------

def _vol_adjust_byte(volume_db: float) -> int:
    """Soundfilehead.volumeAdjust encoding: a signed i8 in 0.5 dB steps
    (the "Volume Adjust" MISC-page parameter, K2600 manual range −64.0..+63.5 dB).
    0 dB → 0 (no change), so unity-gain samples are byte-identical to before."""
    return max(-128, min(127, round(volume_db * 2)))


def _write_sample_object(f, sample: SampleData, obj_id: int,
                          word_offset: int, volume_db: float = 0.0) -> None:
    num_words = len(sample.data) // 2
    loop_start_w = sample.loop_start
    loop_end_w   = sample.loop_end if sample.loop_end > 0 else num_words - 1
    period       = _compute_sample_period(sample.sample_rate)
    max_pitch    = _compute_max_pitch(sample.sample_rate, sample.root_note)

    looped = sample.loop_type != LoopType.NO_LOOP

    # Soundfilehead.flags — verified against real RAM-loaded soundsets (Patchman
    # PMVOL002) and KurzFiler's WAV importer (LoadWaveMethod): a playable RAM
    # sample needs 0x70 (needsLoad 0x40 + the 0x10/0x20 playback-enable bits);
    # 0x40 alone loads the sample but produces NO SOUND.
    #
    # Loop on/off IS the 0x80 bit (hardware-confirmed 2026-06-16): the K2000
    # LOOPS when 0x80 is CLEAR and plays one-shot when 0x80 is SET.  The Patchman
    # corpus is all looped multisamples, so this path only ever emitted 0x70 and
    # the bug hid until MPC one-shots (Bass/Synth/Perc) came through: every
    # one-shot was force-looped on its zero-length end region → held notes stuck
    # on the final sample (no sustain/release, unnatural).  Set 0x80 when the
    # source has no loop so one-shots play out and stop.
    sfh_flags = 0x70 if looped else 0xF0

    # Absolute word positions in the sample data region
    abs_start      = word_offset
    abs_loop_start = word_offset + loop_start_w
    abs_loop_end   = word_offset + loop_end_w
    abs_end        = word_offset + num_words - 1

    # CR-10: K2000 defines the loop as [sampleLoopStart, sampleEnd], so when a
    # loop is set the "sampleEnd" field must be the loop END, not the end of the
    # PCM — otherwise the K2000 loops over the post-loop decay tail.  For a
    # one-shot, KurzFiler collapses the loop onto the end (loopStart=end).
    sample_end_field = abs_loop_end   if looped else abs_end
    loop_start_field = abs_loop_start if looped else abs_end
    # altSampleStart always equals sampleStart in real files (KurzFiler sets it
    # to 0 then biases by the same per-sample offset as sampleStart).
    alt_start        = abs_start

    bw = _BlockWriter(f, _hash(T_SAMPLE, obj_id))
    bw.begin(sample.name)

    # KSample fixed header (12 bytes).  baseID=1 and flags=0 (mono) match every
    # real soundset; flags bit0 is the stereo flag (1=stereo), so the old 0x40
    # here was meaningless.
    f.write(struct.pack('>hhhBBhh',
        1,          # baseID (always 1)
        0,          # numHeaders (0 = 1 header, mono)
        8,          # HeadersOfs (always 8)
        0,          # flags (0 = mono, 1 = stereo)
        0,          # ks1
        0,          # copyID
        0,          # ks2
    ))

    # Soundfilehead (32 bytes) — single mono header
    # offsetToEnvelope: for 1 header, envofs=0, value=0+8=8
    # altOffsetToEnvelope: 0+6=6
    # volumeAdjust / altVolumeAdjust: per-sample gain, signed i8 in 0.5 dB steps.
    # Our gain is per-zone (ZoneMapping.volume); write_krz aggregates it per sample
    # and passes it here.  0 dB → 0, so unity samples are unchanged (pending HW).
    va = _vol_adjust_byte(volume_db) & 0xFF
    f.write(struct.pack('>BBBBhh',
        sample.root_note & 0xFF,
        sfh_flags & 0xFF,
        va,   # volumeAdjust      (signed i8, 0.5 dB steps)
        va,   # altVolumeAdjust   (same, applied when the Alt start is active)
        max_pitch & 0xFFFF,
        0,    # offsetToName
    ))
    f.write(struct.pack('>iiii',
        abs_start,
        alt_start,          # == sampleStart in real files
        loop_start_field,   # loop start (looped) / end (one-shot)
        sample_end_field,   # CR-10: loop end (looped) / PCM end (one-shot)
    ))
    f.write(struct.pack('>hhI',
        8,    # offsetToEnvelope
        6,    # altOffsetToEnvelope
        period,
    ))

    # 2× Envelope default: [-1, 1, 0, 0, -1600, 0]
    env = struct.pack('>hhhhhh', -1, 1, 0, 0, -1600, 0)
    f.write(env)
    f.write(env)

    bw.end()


# ---------------------------------------------------------------------------
# Keymap object  (KKeymap)
# ---------------------------------------------------------------------------

def _build_keymap_entries(voice: VoiceLayer,
                           sample_id_map: dict,
                           samples_by_name: dict,
                           base_pitch: int) -> bytes:
    """
    Build 128 5-byte keymap entries for one voice's zones.

    Entry layout (method=0x0013): tuning(int16) sampleID(int16) SSNr(uint8).

    The K2000 already transposes each key automatically from the sample's own
    rootkey and centsPerEntry=100 — entry[key] plays the sample shifted by
    (key − sample.rootkey) semitones.  The per-entry tuning is therefore a
    *constant* fine offset, NOT the full per-key transposition.  The old code
    baked 100*(root−12−key) into every entry, double-counting the automatic
    per-key shift (and adding a stray −1 octave), which pushed high keys to
    −72 semitones — out of range and silent.

    With the sample written at rootkey R_s, a zone that wants root R_zone needs
    a constant tuning of 100*(R_s − R_zone) cents so that key R_zone plays the
    sample at its natural pitch; R_s == R_zone ⇒ tuning 0 (the common case).

    CR-1: one keymap PER VOICE (not one merged keymap per preset).  Combined
    with one program layer per voice, this stops later voices overwriting
    earlier ones per key, and lets distinct voices (key splits, layers, and the
    velocity layers our parsers model as separate voices) coexist.
    """
    entries = bytearray(NUM_KEYS * KEYMAP_ENTRY_SIZE)
    for zone in voice.zones:
        sid = sample_id_map.get(zone.sample_name, 0)
        if sid == 0:
            continue
        sample = samples_by_name.get(zone.sample_name)
        r_sample = sample.root_note if sample is not None else 60   # written rootkey
        r_zone = zone.root_key if zone.root_key else r_sample
        tuning = 100 * (r_sample - r_zone) + zone.fine_tune
        tuning = max(-32768, min(32767, tuning))

        # Up-pitch ceiling (HW-confirmed 2026-06-21): a sample can only transpose
        # UP to the K2000's 48 kHz playback ceiling = maxPitch//100 (= root +
        # 12·log2(48000/sr) semitones).  Keys above that clamp to a single pitch —
        # and stretching a *single* sample far past it (e.g. a 33 kHz sample over
        # the whole keyboard) makes the K2000 drop keytracking for the ENTIRE
        # keymap (the bank played one fixed note).  So never assign a key above the
        # sample's ceiling: those keys go silent instead of playing the wrong
        # pitch, and the rest of the keymap keytracks correctly.  (To extend the
        # playable range upward, downsample the sample via --max-sample-rate, which
        # raises the ceiling — the same fix used for the KRZ floppy banks.)
        hi_key = zone.hi_key
        if sample is not None:
            ceiling = _compute_max_pitch(sample.sample_rate, r_sample) // 100
            hi_key = min(hi_key, ceiling)

        for key in range(zone.lo_key, hi_key + 1):
            offset = key * KEYMAP_ENTRY_SIZE
            struct.pack_into('>hHB', entries, offset,
                             tuning, sid & 0xFFFF, 1)

    # CRITICAL (HW-confirmed 2026-06-24): every K2000 keymap key MUST reference a
    # valid sample — real keymaps never leave a key empty.  The up-pitch ceiling
    # cap and inter-zone gaps above can leave sampleId=0 "holes"; a keymap with
    # such holes LOCKS UP the K2000 on Master→Delete (corrupts state — needs
    # multiple factory-reset cycles to recover; #202 PingPong had 79/128 holes).
    # Fill every hole by extending the nearest assigned key's entry (sample + its
    # constant tuning).  Above-ceiling fills may clamp / lose keytracking on
    # playback — a far lesser evil than the delete lockup; downsample via
    # --max-sample-rate to raise the ceiling and avoid both.
    ES = KEYMAP_ENTRY_SIZE
    def _sid(off):
        return (entries[off + 2] << 8) | entries[off + 3]
    carry = None                                   # forward-fill into later holes
    for key in range(NUM_KEYS):
        off = key * ES
        if _sid(off):
            carry = bytes(entries[off:off + ES])
        elif carry is not None:
            entries[off:off + ES] = carry
    carry = None                                   # back-fill any leading holes
    for key in range(NUM_KEYS - 1, -1, -1):
        off = key * ES
        if _sid(off):
            carry = bytes(entries[off:off + ES])
        elif carry is not None:
            entries[off:off + ES] = carry

    return bytes(entries), KEYMAP_METHOD, KEYMAP_ENTRY_SIZE, 0


def _write_keymap_object(f, name: str, voice: VoiceLayer, obj_id: int,
                          sample_id_map: dict, samples_by_name: dict,
                          base_pitch: int) -> None:
    entries, method, entry_size, header_sid = _build_keymap_entries(
        voice, sample_id_map, samples_by_name, base_pitch)

    bw = _BlockWriter(f, _hash(T_KEYMAP, obj_id))
    bw.begin(name)

    # KKeymap fixed header (28 bytes)
    # Level[j] = (8-j)*2 for a single velocity level spanning all 8 buckets
    levels = [(8 - j) * 2 for j in range(NUM_VELO_LEVELS)]
    f.write(struct.pack('>hhhhhh',
        header_sid,             # default sampleId (set for single-sample keymaps)
        method,
        base_pitch,
        100,                    # centsPerEntry (1 semitone per key)
        NUM_KEYS - 1,           # entriesPerVel (127 = 128 entries)
        entry_size,
    ))
    for lv in levels:
        f.write(struct.pack('>h', lv))

    f.write(entries)
    bw.end()


# ---------------------------------------------------------------------------
# Program object  (KProgram segments)
# ---------------------------------------------------------------------------

def _make_pgm_segment(num_layers: int) -> bytes:
    # PGMSEGTAG: mode=2 (K2000), numLayers, bendRange=0x37, portamento=64
    data = bytearray(15)
    data[0] = 2          # mode K2000
    data[1] = num_layers
    data[3] = 0x37       # bendRange
    data[4] = 64         # portamento
    return _pack_segment(PGMSEGTAG, bytes(data))


def _make_layer_segments(keymap_id: int, stereo: bool = False,
                          lo_key: int = 0, hi_key: int = 127,
                          lo_vel: int = 0, hi_vel: int = 127) -> bytes:
    segs = b''

    # LYRSEGTAG — per-layer ranges + Enable.  Byte map (HW-confirmed 2026-06-24
    # via KurzFiler + KPOWER/xprogs4 + the VELAYRE.KRZ velocity diff):
    #   [3]=loKey [4]=hiKey [5]=velocity window (packed loVel/hiVel, see _vel_byte)
    #   [6]=Enable control source (127=ON; NOT hiVel) [8]=flags(0x04 mono/0x24 stereo)
    lyr = bytearray(15)
    lyr[1] = 0x18
    lyr[3] = lo_key & 0x7F
    lyr[4] = hi_key & 0x7F
    lyr[5] = _vel_byte(lo_vel, hi_vel)  # packed LoVel/HiVel (0–7 marks)
    lyr[6] = 0x7F                       # Enable = ON
    lyr[8] = 0x24 if stereo else 0x04   # mono/stereo flags
    segs += _pack_segment(LYRSEGTAG, bytes(lyr))

    # ENCSEGTAG (all zeros)
    segs += _pack_segment(ENCSEGTAG, bytes(15))

    # ENVSEGTAG — amplitude envelope: flat sustain at 100
    env = bytearray(15)
    env[1] = 100
    env[7] = 100
    segs += _pack_segment(ENVSEGTAG, bytes(env))

    # CALSEGTAG — keymap reference
    cal = bytearray(31)
    cal[0] = 0x7F
    cal[3] = 0x2B
    cal[7]  = (keymap_id >> 8) & 0xFF
    cal[8]  =  keymap_id       & 0xFF
    cal[11] = (keymap_id >> 8) & 0xFF
    cal[12] =  keymap_id       & 0xFF
    cal[29] = 1   # numKeymaps
    segs += _pack_segment(CALSEGTAG, bytes(cal))

    # HOB segments 0x50–0x53 (pitch/filter/amp/pan defaults)
    s50 = bytearray(15); s50[0] = 62
    s51 = bytearray(15); s51[0] = 60
    s52 = bytearray(15); s52[0] = 60
    s53 = bytearray(15)
    s53[0] = 1;  s53[2] = 0x70;  s53[13] = 4
    s53[14] = 0x90 if stereo else 0x00
    segs += _pack_segment(0x50, bytes(s50))
    segs += _pack_segment(0x51, bytes(s51))
    segs += _pack_segment(0x52, bytes(s52))
    segs += _pack_segment(0x53, bytes(s53))

    return segs


# ---------------------------------------------------------------------------
# Template-and-patch program writer  (file-format RE, 2026-06-15)
# ---------------------------------------------------------------------------
# We clone the K2000 ROM #199 "Default Program" (disk-saved as DFLT.KRZ and
# diffed against single-parameter variants on the hardware — see
# docs/re_procedures/krz_program_re.md §16) and overwrite only the value bytes.
# This gives the full, correct K2000 program structure for free and lets us
# carry filter + envelopes + LFO that the old hand-built program could not.
#
# The 4 HOB segments (0x50-0x53) are the 4 DSP-function pages F1/F2/F3/F4-AMP.
# Algorithm 1 with F1 = 4POLE LOPASS W/SEP gives a 24 dB/oct resonant lowpass:
#   filter type  = HOB0(0x50)[0]  (50=4POLE LOPASS, 54=4POLE HIPASS,
#                  55=TWIN PEAKS BANDPASS, 56=DOUBLE NOTCH, 62=NONE)
#   cutoff       = HOB0[1]  (signed semitones; Hz = 440*2**((b-9)/12))
#   resonance    = HOB1(0x51)[1] (dB*2, 0..48 = 0..24 dB)
#   filter-env routing: HOB0[5]=121(=ENV2 source), HOB0[6]=depth
#   AMPENV mode  = ENC(0x20)[1]  (1=Natural -> 0=User)
#   AMPENV       = ENV(0x21)[0..13]  7 (time,level) pairs from byte 0
#                  (Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3); byte 14 = loop flag
#   ENV2 (filter env) = ENC(0x22)[0..13]   (same layout)
#   LFO1 rate/shape/phase = LFO(0x14)[2]/[4]/[5]
#   LFO1->Pitch routing   = CAL(0x40)[21]=114(LFO1 source), CAL[22]=depth
#   keymap reference      = CAL[7,8] / CAL[11,12]

# (tag, default bytes) — global PGM+FX, then one layer block, from DFLT.KRZ:
_TPL_GLOBAL = [
    (0x08, [2, 1, 0, 55, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),   # PGM
    (0x0F, [0, 1, 0, 0, 0, 0, 0]),                             # FX
]
_TPL_LAYER = [
    (0x09, [0, 0, 0, 12, 108, 0, 127, 0, 4, 0, 0, 0, 0, 0, 0]),     # LYR
    (0x10, [0, 127, 1, 53, 53, 0, 53]),                            # ASR1
    (0x11, [0, 127, 1, 53, 53, 0, 53]),                            # ASR2
    (0x18, [1, 0, 0]), (0x19, [2, 0, 0]),                          # FUN1,2
    (0x14, [0, 0, 46, 0, 0, 1, 0]),                                # LFO1
    (0x15, [0, 0, 46, 0, 0, 1, 0]),                                # LFO2
    (0x1A, [3, 0, 0]), (0x1B, [4, 0, 0]),                          # FUN3,4
    (0x20, [0, 1, 0, 0, 0, 73, 0, 0, 0, 72, 0, 0, 0, 72, 0]),       # ENC ampenv-mode
    (0x21, [0, 100, 0, 0, 0, 0, 0, 100, 0, 0, 0, 0, 0, 0, 0]),      # ENV  AMPENV
    (0x22, [0, 100, 0, 0, 0, 0, 0, 100, 0, 0, 0, 0, 0, 0, 0]),      # ENC  ENV2 (filter env)
    (0x23, [0, 100, 0, 0, 0, 0, 0, 100, 0, 0, 0, 0, 0, 0, 0]),      # ENC  ENV3 (pitch env)
    (0x40, [127, 0, 0, 43, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0]),            # CAL
    (0x50, [62, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]),         # HOB F1 (filter)
    (0x51, [16, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]),         # HOB F2 (resonance)
    (0x52, [18, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 3, 0]),         # HOB F3 (SEP)
    (0x53, [1, 6, 0, 0, 35, 0, 0, 1, 0, 0, 0, 0, 0, 3, 4]),         # HOB F4/AMP
]

# K2000 envelope-time display grid (s per editor step); env time byte = steps+3.
_ENV_TIME_GRID = [(0, 2, 0.02), (2, 5, 0.04), (5, 10, 0.10),
                  (10, 15, 0.50), (15, 25, 1.0), (25, 60, 5.0)]
# LFO shape name -> K2000 file byte.  All 26 shapes probed live on K2000R 2026-06-17:
# 0=Sine 1=+Sine 2=Square 3=+Square 4=Triangle 5=+Triangle
# 6=Rise S 7=+Rise 8=Fall S 9=+Fall 10-25=step patterns (3/4/5/6/7/8/10/12 Step ± unipolar)
_LFO_SHAPE = {
    'sine':       0,   # Sine
    '+sine':      1,   # +Sine (unipolar)
    'square':     2,   # Square
    '+square':    3,
    'triangle':   4,   # Triangle
    '+triangle':  5,
    'sawtooth':   6,   # Rising Sawtooth (most common upward-ramp LFO)
    '+sawtooth':  7,
    'sawtooth_down': 8,  # Falling Sawtooth (explicit downward ramp)
    'random':    20,   # 8 Step — nearest deterministic approximation to S&H
    'hemiquaver':20,   # 8 Step (stepped clock pattern, like E4B hemiquaver)
}
_K2_CS_ENV2 = 121      # control-source code for ENV2
_K2_CS_LFO1 = 114      # control-source code for LFO1


def _env_steps(seconds: float) -> float:
    t = max(0.0, min(60.0, seconds))
    s = 0.0
    for lo, hi, st in _ENV_TIME_GRID:
        if t <= lo:
            break
        s += (min(t, hi) - lo) / st
    return s


def _env_time_byte(seconds: float) -> int:
    return max(3, min(255, round(_env_steps(seconds) + 3)))


def _lvl_byte(pct: float) -> int:
    return round(max(-100.0, min(100.0, pct))) & 0xFF       # signed %


def _vel_byte(lo_vel: int, hi_vel: int) -> int:
    """Pack a MIDI velocity range into LYR data[5] (K2000).

    HW-confirmed 2026-06-24 by diffing VELAYRE.KRZ (3 layers saved on the K2000R
    with known LoVel/HiVel): the layer velocity window is a SINGLE byte holding
    two 0–7 dynamic marks (ppp=0 … fff=7) — LoVel in bits 3–5, HiVel in bits 0–2
    stored INVERTED (7−mark).  So a full-range layer (ppp…fff) is 0, which is why
    every factory layer reads 0 and the field was invisible in static files.
    """
    lo_mark = max(0, min(7, round(lo_vel / 127 * 7)))
    hi_mark = max(0, min(7, round(hi_vel / 127 * 7)))
    return ((lo_mark & 0x07) << 3) | ((7 - hi_mark) & 0x07)


# Two-leg release shape (see _fill_env) — HW-validated knee/split, AlphaPad #200.
_REL_KNEE_PCT   = 33.0    # Rel1 target level (% of full)
_REL1_TIME_FRAC = 0.8     # fraction of the release time spent reaching the knee

# KRZ-only release-time correction.  The shared MPC value→seconds curve
# (_xpm_env_to_seconds, fit in §18 to audio time-to-−40 dB) under-reads the MPC's
# DISPLAYED release time by a ~constant factor: AlphaPad VolumeRelease 0.764 →
# curve 1.39 s vs the MPC AMPENV display 2.63 s (Jan, 2026-06-24). Scaling here
# (KRZ-writer only) avoids lengthening every E4B/E4XT envelope; the proper global
# recalibration of the shared curve is a deferred TODO (needs a by-ear E4B check).
_KRZ_RELEASE_FACTOR = 1.9   # = 2.63 / 1.39


def _fill_env(b: bytearray, env) -> None:
    """Write an ADSR Envelope into a 15-byte ENV/ENC segment IN PLACE.

    K2000 layout (HW-confirmed 2026-06-24, Jan — read the AMPENV LCD against the
    on-disk bytes): seven `(time, level)` pairs packed from byte 0 —
    `Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3` — with times on the even bytes
    [0,2,…,12] and levels on the odd bytes [1,3,…,13]; byte 14 is a trailing
    flag (loop), left untouched.

    BUG FIXED 2026-06-24: the old code started writing at byte **2**, shifting
    every segment by one pair — the decay-to-sustain landed in the K2000's Rel1
    (so Rel1 read 100 % and never faded) and the release fade landed in Rel2.
    HW symptom (AlphaPad #200): levels Att1..Rel2 all read 100 % except Rel2=0,
    giving a held-then-cut release instead of a fade from sustain to silence.
    """
    tb, lv = _env_time_byte, _lvl_byte
    sus = env.sustain * 100.0
    # Two-leg release: the MPC release is ~exponential (linear in dB); a single
    # linear K2000 Rel1 sus→0 holds too loud then collapses ("sharp cutoff").
    # Approximate with a long first leg down to a knee, then a short tail to
    # silence.  Knee + split validated by ear on the K2000R (AlphaPad #200, Jan
    # 2026-06-24: Rel1 2.16 s → 33 %, Rel2 0.5 s → 0 %; total ≈ the release time).
    rel = env.release * _KRZ_RELEASE_FACTOR          # KRZ-only time correction
    pairs = [(env.attack, 100),                      # Att1 — ramp to full
             (0.0, 100),                             # Att2
             (0.0, 100),                             # Att3
             (env.decay, sus),                       # Dec1 — decay to sustain
             (rel * _REL1_TIME_FRAC, _REL_KNEE_PCT), # Rel1 — fade to the knee
             (rel * (1.0 - _REL1_TIME_FRAC), 0),     # Rel2 — short tail to silence
             (0.0, 0)]                               # Rel3
    o = 0
    for t, l in pairs:
        b[o] = tb(t); b[o + 1] = lv(l); o += 2
    # byte 14 (loop/flag) left as the template set it


def _cutoff_byte(cutoff01: float) -> int:
    # filter_cutoff 0..1 -> K2000 semitone byte -48 (16 Hz) .. +79 (25088 Hz)
    return max(-48, min(79, round(-48 + cutoff01 * 127))) & 0xFF


def _reson_byte(reson01: float) -> int:
    return max(0, min(48, round(reson01 * 48)))             # dB*2, max 24 dB


# K2000 DSP filter-type bytes — HOB0(0x50)[0] — and the algorithm they live in.
# Hardware-RE'd 2026-06-16 (FILTERS.KRZ 312-315; POLE1LP.KRZ 323; POLE2A5.KRZ 320/324):
#   Alg 1  (4-pole, 24 dB/oct): 4POLE LOPASS=50, HIPASS=54, TWIN PEAKS BP=55,
#          DOUBLE NOTCH=56, NONE=62; F2=RES(16), F3=SEP(18).
#   Alg 5  (2-pole, 12 dB/oct, SERIES/bypass-free): 2POLE LOWPASS=2, BANDPASS FILT=3;
#          F2=RES/WID(16), F3=NONE(60).  (Algorithm 3 was rejected — it has a bypass
#          path around the filter, so the 2-pole barely filtered; Alg 5 with F3=NONE
#          is `PITCH -> filter -> NONE -> AMP`, a clean series path.)
#   Alg 16 (1-pole, 6 dB/oct):  LOPASS=15;        F2=NONE(61), F3=18.  Fixed -3 dB
#          resonance (no F2 RES page), so no resonance byte is written.
#   All share an IDENTICAL program layout; the slope is selected by a handful of
#   bytes — HOB0[0] (filter), HOB1[0] (F2 block), HOB2[0] (F3 block), CAL[29]
#   (algorithm) — so no separate template is needed.
_K2_FILTER_NONE = 62
_K2_FILTER_LP = 50           # Alg1 4POLE LOPASS W/SEP  (24 dB/oct)
_K2_FILTER_HP = 54           # Alg1 4POLE HIPASS W/SEP
_K2_FILTER_BP = 55           # Alg1 TWIN PEAKS BANDPASS
_K2_FILTER_NOTCH = 56        # Alg1 DOUBLE NOTCH W/SEP
_K2_FILTER_2P_LP = 2         # Alg5 2POLE LOWPASS       (12 dB/oct)
_K2_FILTER_2P_BP = 3         # Alg5 BANDPASS FILT       (2-pole)
_K2_FILTER_1P_LP = 15        # Alg16 LOPASS            (6 dB/oct, fixed -3 dB res)
_K2_FILTER_PARA_MID = 51     # Alg2 PARA MID F1-FRQ  (parametric band BOOST; HW-RE'd 2026-06-25)
_K2_F2_RES = 16              # HOB1[0]: F2 = resonance/width page (4-pole / 2-pole)
_K2_F2_AMP = 16              # HOB1[0]: Alg2 PARA MID F2-AMP block (gain in HOB1[1], dB; =16)
_K2_F2_NONE = 61             # HOB1[0]: F2 = NONE        (1-pole; fixed resonance)
_K2_F3_SEP = 18              # HOB2[0]: F3 = separation  (Alg 1 / Alg 16)
_K2_F3_NONE = 60             # HOB2[0]: F3 = NONE        (Alg 5, clean series path)
_K2_F3_NONE_ALG2 = 40        # HOB2[0]: Alg2 F3 = None   (PARA MID; HW-RE'd 2026-06-25)
_K2_CAL_ALGORITHM = 29       # CAL byte holding the algorithm number
# PARA MID (Alg2) AMP gain = HOB1[1] as signed dB, 1:1 (HW: +24dB->24, +48dB->48,
# 0->0, range +-48).  Band-boost depth from MPC resonance: +12 .. +24 dB.
_K2_PARAMID_GAIN_MIN_DB = 12
_K2_PARAMID_GAIN_SPAN_DB = 12
# BANDPASS F2 is *width* (HOB1[1]), not resonance.  A fresh-selected bandpass
# defaults to byte 0 (very narrow / thin).  The real Patchman corpus clusters its
# bandpass width at ~57-70 (median ~64), so emit a medium 64 rather than the thin
# default.  Mapping MPC resonance->width is a future refinement (needs the width
# byte<->octaves encoding RE'd from a disk-save).
_K2_BP_DEFAULT_WIDTH = 64


def _k2_filter_plan(xpm_type: int):
    """Map an XPM FilterType int (see models.common.Voice.filter_type and the
    enumeration in writers.e4b_writer._XPM_FILTER_TYPE) onto a K2000 filter plan:
    ``(algorithm, HOB0[0] filter, HOB1[0] F2-block, HOB2[0] F3-block, has_resonance)``.

    Slope is matched to the source exactly where the K2000 can: Low1 (6 dB) -> the
    1-pole LOPASS (Alg 16); Low2 / MPC3000 LPF (12 dB) -> the 2-pole LOWPASS and
    Band2 -> the 2-pole BANDPASS (Alg 5, bypass-free); BB (band-boost, 19-22) -> the
    Alg-2 PARA MID parametric boost (FRQ=cutoff, AMP gain set from resonance), which
    keeps the body and lifts a band (a bandpass would wrongly remove the out-of-band
    signal); Low4+, HP, the multi-pole BP and the notch families -> the 24 dB Alg-1
    filters.  Because slopes
    are matched, the source cutoff frequency transfers 1:1 (it is the -3 dB corner
    regardless of slope).  Multi-pole variants collapse onto the nearest slope;
    Vocal (26-28) -> lowpass.  (2-pole HP and notch are not RE'd — High2 uses the
    4-pole HP; notch sources are all 4-pole+.)"""
    if xpm_type == 1:                                 # Low1 -> 1-pole 6 dB (Alg 16)
        return 16, _K2_FILTER_1P_LP, _K2_F2_NONE, _K2_F3_SEP, False
    if xpm_type in (2, 29):                           # Low2 / MPC3000 LPF -> 2-pole 12 dB
        return 5, _K2_FILTER_2P_LP, _K2_F2_RES, _K2_F3_NONE, True
    if 19 <= xpm_type <= 22:                          # BB band-boost -> Alg2 PARA MID
        return 2, _K2_FILTER_PARA_MID, _K2_F2_AMP, _K2_F3_NONE_ALG2, False  # gain set below
    if xpm_type == 11:                                # Band2 -> 2-pole bandpass
        return 5, _K2_FILTER_2P_BP, _K2_F2_RES, _K2_F3_NONE, False  # F2=width, not reson
    if 15 <= xpm_type <= 18:                          # BS notch (band-stop)
        return 1, _K2_FILTER_NOTCH, _K2_F2_RES, _K2_F3_SEP, True
    if 6 <= xpm_type <= 10:                           # High 1-8  (highpass)
        return 1, _K2_FILTER_HP, _K2_F2_RES, _K2_F3_SEP, True
    if 12 <= xpm_type <= 14:                          # Band4+ -> 4-pole TWIN PEAKS
        return 1, _K2_FILTER_BP, _K2_F2_RES, _K2_F3_SEP, True
    return 1, _K2_FILTER_LP, _K2_F2_RES, _K2_F3_SEP, True  # Low4+/Model/Vocal -> 4-pole


def _patch_layer(voice, keymap_id: int):
    """Return a patched copy of the template layer segments for one voice."""
    segs = [(tag, bytearray(data)) for tag, data in _TPL_LAYER]
    by = {}
    for i, (tag, data) in enumerate(segs):
        by.setdefault(tag, []).append((i, data))

    def seg(tag, n=0):
        return by[tag][n][1]

    lo_k, hi_k, lo_v, hi_v = _voice_key_vel_range(voice)
    lyr = seg(0x09)
    lyr[3], lyr[4] = lo_k & 0x7F, hi_k & 0x7F
    lyr[5] = _vel_byte(lo_v, hi_v)   # packed LoVel/HiVel (0–7 marks; see _vel_byte)
    lyr[6] = 0x7F                    # Enable = ON (NOT hiVel — that was the gating bug)

    cal = seg(0x40)
    # Keymap reference goes ONLY in CAL[11,12].  CAL[7,8] is a *second* keymap slot
    # (real K2000 programs keep it 0); writing the keymap id there too made every
    # layer claim two keymaps, overflowing the K2000 at 4+ layers -> whole program
    # silent (HW-confirmed 2026-06-23 against ROM #183/#193/#194, 3/8/19 layers, all
    # of which have CAL[8]=0).  Keep CAL[7,8] zero.
    cal[7] = cal[8] = 0
    cal[11] = (keymap_id >> 8) & 0xFF
    cal[12] = keymap_id & 0xFF

    # --- amp envelope (always User mode + the source ADSR) ---
    seg(0x20)[1] = 0                                         # AMPENV mode -> User
    _fill_env(seg(0x21), voice.amp_env)

    hob_f1 = seg(0x50)
    hob_f2 = seg(0x51)
    if getattr(voice, 'filter_type', 0):
        algo, ftype_byte, f2_byte, f3_byte, has_res = _k2_filter_plan(voice.filter_type)
        hob_f1[0] = ftype_byte                               # F1 DSP filter type
        hob_f2[0] = f2_byte                                  # F2 block: RES(16)/NONE(61)
        seg(0x52)[0] = f3_byte                               # F3 block: SEP(18)/NONE(60)
        cal[_K2_CAL_ALGORITHM] = algo                        # algorithm number (1/5/16)
        # Velocity->Filter: on the source (MPC) a high VelocityToFilter pushes the
        # cutoff "up very far" at playing velocity (hardware-checked by Jan on
        # Bass-MS20: VelToFilter 127 -> filter ~open; 0 -> static Cutoff engages,
        # i.e. effective cutoff = Cutoff + VelToFilter).  We render a static K2000
        # program, so fold the velocity term into the cutoff rather than a VelTrk
        # sweep from the K2000's 16 Hz floor (which would mute softly-played notes
        # that the MPC keeps audible).  velocity_to_filter is -1..+1; only the
        # opening (positive) part raises the floor.
        eff_cutoff = min(1.0, getattr(voice, 'filter_cutoff', 1.0)
                              + max(0.0, getattr(voice, 'velocity_to_filter', 0.0)))
        hob_f1[1] = _cutoff_byte(eff_cutoff)
        if has_res:                                          # 1-pole has fixed -3 dB res
            hob_f2[1] = _reson_byte(getattr(voice, 'filter_resonance', 0.0))
        elif ftype_byte == _K2_FILTER_2P_BP:                 # bandpass F2 = width
            hob_f2[1] = _K2_BP_DEFAULT_WIDTH
        elif ftype_byte == _K2_FILTER_PARA_MID:              # PARA MID F2-AMP = boost dB
            res = max(0.0, min(1.0, getattr(voice, 'filter_resonance', 0.0)))
            hob_f2[1] = max(0, min(48, round(_K2_PARAMID_GAIN_MIN_DB
                                             + _K2_PARAMID_GAIN_SPAN_DB * res)))
        # --- filter envelope (ENV2) + routing to filter freq ---
        amt = getattr(voice, 'filter_env_amount', 0.0)
        if amt > 0.0:
            _fill_env(seg(0x22), voice.filter_env)
            hob_f1[5] = _K2_CS_ENV2                          # source = ENV2
            hob_f1[6] = max(0, min(127, round(amt * 127)))  # depth (approx; see TODO)

    # --- LFO1 + vibrato (LFO1 -> Pitch) ---
    lfo = seg(0x14)
    if voice.lfo1_rate is not None:
        lfo[2] = max(0, min(255, round(26 + 10 * voice.lfo1_rate)))
    if voice.lfo1_shape:
        lfo[4] = _LFO_SHAPE.get(voice.lfo1_shape.lower(), 0)  # fallback: Sine
    if getattr(voice, 'lfo1_to_pitch', 0.0) > 0.0:
        cal[21] = _K2_CS_LFO1                                # source = LFO1
        cal[22] = max(0, min(123, round(voice.lfo1_to_pitch * 79)))  # depth (approx; TODO)

    return segs


def _write_program_object(f, preset: Preset, prog_id: int,
                           voice_keymaps: list) -> None:
    """Clone the #199 template and patch per-voice values (filter, envelopes,
    LFO).  One layer per voice (CR-1)."""
    layers = voice_keymaps or [(None, prog_id)]
    n = len(layers)

    bw = _BlockWriter(f, _hash(T_PROGRAM, prog_id))
    bw.begin(preset.name)

    # PGM + FX (global), with numLayers patched
    for tag, data in _TPL_GLOBAL:
        d = bytearray(data)
        if tag == 0x08:
            d[1] = n
        f.write(_pack_segment(tag, bytes(d)))

    for voice, kid in layers:
        if voice is None:
            segs = [(tag, bytearray(data)) for tag, data in _TPL_LAYER]
            cal = next(d for t, d in segs if t == 0x40)
            cal[7] = cal[8] = 0          # CAL[7,8] is a 2nd keymap slot — keep 0
            cal[11] = (kid >> 8) & 0xFF
            cal[12] = kid & 0xFF
        else:
            segs = _patch_layer(voice, kid)
        for tag, data in segs:
            f.write(_pack_segment(tag, bytes(data)))

    f.write(struct.pack('>H', 0))   # segment terminator
    bw.end()


def _split_voice_by_velocity(voice: VoiceLayer):
    """Split one voice into one VoiceLayer per distinct velocity band.

    A K2000 keymap maps a single sample per key (it has no per-key velocity
    zones — the velocity buckets all share one entry).  So a voice whose zones
    span several velocity bands — e.g. an MPC velocity-split keygroup whose
    mutually-exclusive layers the lane-allocator merged into one voice (their
    vel ranges don't overlap, so they never triggered the parser's voice split)
    — would otherwise collide on every key in a single keymap, last (= top, =
    brightest) zone winning, collapsing to one bright layer.

    Group the zones by their exact (lo_vel, hi_vel) band, preserving first-seen
    order, and return one shallow VoiceLayer copy per band carrying only that
    band's zones (so each becomes its own keymap + layer with the band's vel
    window via _voice_key_vel_range/_patch_layer).  A voice with a single band
    returns [voice] unchanged — the common case, byte-for-byte identical output.
    """
    bands: dict = {}
    for z in voice.zones:
        bands.setdefault((z.lo_vel, z.hi_vel), []).append(z)
    if len(bands) <= 1:
        return [voice]
    out = []
    for zones in bands.values():
        v = copy.copy(voice)        # shares envelopes/filter params; zones replaced
        v.zones = zones
        out.append(v)
    return out


def _voice_key_vel_range(voice: VoiceLayer):
    """(lo_key, hi_key, lo_vel, hi_vel) spanning all of a voice's zones."""
    if not voice.zones:
        return 0, 127, 0, 127
    lo_k = min(z.lo_key for z in voice.zones)
    hi_k = max(z.hi_key for z in voice.zones)
    lo_v = min(z.lo_vel for z in voice.zones)
    hi_v = max(z.hi_vel for z in voice.zones)
    return lo_k, hi_k, lo_v, hi_v


def _coverage_remap_voices(voices, samples_by_name):
    """K2000 up-pitch-ceiling fix for WIDE-RANGE OCTAVE-SLICE STACKS.

    Patches like the JR UniDrone/UniPan pads stack several heavily-overlapping
    voices, each stretching ONE octave-slice (roots an octave apart) across the
    whole keyboard.  But the K2000 can only pitch a sample up to the 48 kHz
    playback rate — for a 24 kHz slice that's ~1 octave above its root — so the
    top of every band goes silent (SloBand #204: L1 died at ~C2, L2/L3 at ~C3).

    Rebuild the stack as 1-3 COVERAGE multisample keymaps: lay the slices
    side-by-side, each covering only from the previous slice's ceiling up to its
    OWN up-pitch ceiling, the next-higher slice taking over — a proper
    multisample, so nothing is over-stretched (Jan's "splits → keymap, not
    layers").  Doubling (A/B copies at the same root) becomes parallel coverage
    layers (≤3, so it stays an any-channel program).  Returns (voices, applied).

    Scoped tight: only fires when every voice overlaps in key AND the samples span
    ≥2 octaves of root AND some zone actually overflows its ceiling — i.e. a real
    octave-slice drone, not a same-root unison stack or a normal multisample."""
    if len(voices) < 2:
        return voices, False
    # Velocity-layered presets are off-limits: this remap groups slices by ROOT
    # only, so merging across velocity bands would destroy the velocity split
    # (e.g. Bass-DX7).  Leave any preset that uses a velocity window to the
    # normal vel-split path.
    for v in voices:
        for z in v.zones:
            if z.lo_vel > 0 or z.hi_vel < 127:
                return voices, False
    rs = [_voice_key_vel_range(v) for v in voices]
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            lk1, hk1, _, _ = rs[i]
            lk2, hk2, _, _ = rs[j]
            if not (lk1 <= hk2 and lk2 <= hk1):
                return voices, False          # not a full stack — leave alone
    by_root: dict = {}
    overflow = False
    for v in voices:
        for z in v.zones:
            s = samples_by_name.get(z.sample_name)
            if s is None:
                return voices, False
            root = z.root_key if z.root_key else s.root_note
            ceil = _compute_max_pitch(s.sample_rate, root) // 100
            if z.hi_key > ceil + 3:
                overflow = True
            by_root.setdefault(root, []).append((ceil, z))
    roots = sorted(by_root)
    if not overflow or len(roots) < 3 or (roots[-1] - roots[0]) < 24:
        return voices, False
    depth = min(3, max(len(by_root[r]) for r in roots))
    new_voices = []
    for li in range(depth):
        nv = copy.copy(voices[0])
        nv.zones = []
        lo = 0
        for r in roots:
            entries = by_root[r]
            ceil, z = entries[li % len(entries)]
            zz = copy.copy(z)
            zz.lo_key = lo
            zz.hi_key = max(lo, ceil)
            nv.zones.append(zz)
            lo = ceil + 1
        new_voices.append(nv)
    return new_voices, True


def _spread_pick(items, k):
    """Pick k items evenly spread across the list (keeps the endpoints).  For a
    detuned unison stack 1-2-3-4-5 capped to 3 this keeps 1-3-5 — preserving the
    full detune/timbre spread instead of collapsing to 1-2-3."""
    if len(items) <= k:
        return list(items)
    if k == 1:
        return [items[len(items) // 2]]
    n = len(items)
    return [items[round(j * (n - 1) / (k - 1))] for j in range(k)]


def _voices_stacked(voices) -> bool:
    """True when every pair of voices overlaps in BOTH key and velocity — a
    unison/stacked program whose extra layers are redundant, so it can be capped
    to 3 and stay a regular K2000 program (plays on any channel).  False if any
    velocity- or key-split exists: those layers cover unique dynamics/range and
    must all be kept (a K2000 "drum program", >3 layers, played on a drum channel).

    NOTE (2026-06-24): a stricter "keep all distinct-sample voices" version was
    trialled to preserve SloBand's L/R octave stack, but it flips 7 melodic demo
    patches (F9 piano, JP8/DX7 basses, JR ShortPad/WarmSlow, both brass sections)
    to drum-channel-only — too broad to apply unsupervised.  Kept the original
    3-layer-any-channel cap; faithful all-layer (drum-program) rendering for
    SloBand & stacked siblings is a deferred opt-in.  See TODO."""
    rs = [_voice_key_vel_range(v) for v in voices]
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            (lk1, hk1, lv1, hv1), (lk2, hk2, lv2, hv2) = rs[i], rs[j]
            key_ov = lk1 <= hk2 and lk2 <= hk1
            vel_ov = lv1 <= hv2 and lv2 <= hv1
            if not (key_ov and vel_ov):
                return False
    return True


# ---------------------------------------------------------------------------
# Main writer
# ---------------------------------------------------------------------------

def write_krz(bank: Bank, output_path: str) -> None:
    """Serialize a Bank to a Kurzweil .KRZ file."""
    print(f"Writing KRZ: {output_path}")
    print(f"  {len(bank.presets)} preset(s), {len(bank.samples)} sample(s)")

    # CR-11c: bake ping-pong (ALTERNATING) loops into PCM as forward loops, the
    # same as write_e4b — the K2000 path previously emitted them as plain forward
    # (audible click every cycle).
    samples = [bake_alternating_loop(s) for s in bank.samples]
    n_baked = sum(1 for s in bank.samples if s.loop_type == LoopType.ALTERNATING)
    if n_baked:
        print(f"  Baked {n_baked} ping-pong loop(s) into PCM as forward loops")

    # --- Object ID assignment (user range 200-999) ---
    base_id = 200
    sample_id_map   = {s.name: base_id + i for i, s in enumerate(samples)}
    samples_by_name = {s.name: s for s in samples}

    # Per-sample gain.  The KRZ Soundfilehead.volumeAdjust is per-sample, but our
    # gain lives per-zone (ZoneMapping.volume, dB), so aggregate the volume of every
    # zone referencing a sample (mean).  The common MPC case is 1 zone : 1 sample →
    # exact; a sample shared by zones at different levels averages (lossy but rare).
    # Zones default to 0 dB (full) → 0 byte → no change, so HW-verified unity banks
    # stay byte-identical.
    _sample_vols: dict[str, list] = {}
    for _preset in bank.presets:
        for _voice in _preset.voices:
            for _z in _voice.zones:
                _sample_vols.setdefault(_z.sample_name, []).append(_z.volume)
    sample_gain_db = {name: sum(v) / len(v) for name, v in _sample_vols.items()}

    # Pre-compute per-sample word offsets into the PCM region
    word_offsets: list[int] = []
    cursor = 0
    for s in samples:
        word_offsets.append(cursor)
        cursor += len(s.data) // 2

    # CR-1: one keymap per voice — assign keymap ids with a running counter
    # (typed-hash means numeric overlap with sample/program ids is fine).
    #
    # The K2000 maxes out at 32 layers per program; clamp to that (rare).  The
    # earlier 4+ layer silence was a writer bug — each layer's CAL referenced the
    # keymap in TWO slots (CAL[7,8] and CAL[11,12]) so it claimed two keymaps,
    # overflowing the K2000 above 3 layers; fixed in _patch_layer (HW-RE'd against
    # ROM #183/#193/#194).
    preset_keymaps: list = []        # per preset: list of (voice, keymap_id)
    km_id = base_id
    for preset in bank.presets:
        # Split any multi-velocity-band voice into one layer per band BEFORE the
        # layer-cap logic, so the K2000 keymaps don't collide per key (clean
        # velocity splits like the DSI AlphaPad 0-64/65-96/97-127 trio).  Single-
        # band voices pass through unchanged.
        # Wide-range octave-slice stacks (JR UniDrone/UniPan pads) can't keytrack
        # past the K2000 up-pitch ceiling — rebuild them as coverage multisample
        # keymaps so the whole range sounds at the right octave (see func docstring).
        base_voices, _cov = _coverage_remap_voices(preset.voices, samples_by_name)
        if _cov:
            print(f"  [coverage] '{preset.name}': octave-slice stack → "
                  f"{len(base_voices)} coverage multisample layer(s) "
                  f"(K2000 up-pitch ceiling)")
        voices = [sv for v in base_voices for sv in _split_voice_by_velocity(v)]
        n_split = len(voices) - len(base_voices)
        if n_split:
            print(f"  [vel-split] '{preset.name}': {len(preset.voices)} voice(s) → "
                  f"{len(voices)} layer(s) (velocity bands split for the K2000 keymap)")
        # K2000: a regular program is max 3 layers; >3 layers is a "drum program"
        # that only sounds on a drum channel (HW-confirmed).  Cap STACKED/unison
        # programs (all layers overlap → redundant) to 3 so the common melodic case
        # plays on any channel; KEEP SPLIT programs (velocity layers / drum kits /
        # key splits — each layer covers unique territory) as drum programs.
        if len(voices) > 3 and _voices_stacked(voices):
            print(f"  [layers] '{preset.name}': {len(voices)} stacked layers → "
                  f"3 spread across the stack (regular program, any channel).")
            voices = _spread_pick(voices, 3)
        elif len(voices) > 3:
            n = min(len(voices), _MAX_KRZ_LAYERS)
            print(f"  [layers] '{preset.name}': {n} split layers → DRUM PROGRAM "
                  f"(play on a drum channel)."
                  + ("" if len(voices) <= _MAX_KRZ_LAYERS
                     else f"  (clamped from {len(voices)} to the K2000 max {_MAX_KRZ_LAYERS})"))
            voices = voices[:_MAX_KRZ_LAYERS]
        vk = []
        for voice in voices:
            vk.append((voice, km_id))
            km_id += 1
        preset_keymaps.append(vk)

    # basePitch=0: matches every real K2000 production file.  The K2000 derives
    # each key's pitch from the sample rootkey + centsPerEntry=100, so the keymap
    # entry tuning is only a constant per-zone fine offset (see _build_keymap_entries).
    base_pitch = 0

    with open(output_path, 'w+b') as f:
        # --- File header (32 bytes) ---
        f.write(b'PRAM')
        osize_pos = f.tell()
        f.write(struct.pack('>i', 0))   # osize placeholder
        for i, rv in enumerate([0, 0, KRZ_SOFTWARE_VERSION, 0, 0, 0]):
            f.write(struct.pack('>i', rv))

        # --- Sample objects ---
        for i, sample in enumerate(samples):
            sid = base_id + i
            gain = sample_gain_db.get(sample.name, 0.0)
            _write_sample_object(f, sample, sid, word_offsets[i], gain)
            print(f"  Sample  [{sid}] '{sample.name}': "
                  f"{len(sample.data)//2} words @ {sample.sample_rate} Hz"
                  + (f", {gain:+.1f} dB" if _vol_adjust_byte(gain) else ""))

        # --- Keymap objects (one per voice) ---
        for pi, preset in enumerate(bank.presets):
            for voice, kid in preset_keymaps[pi]:
                _write_keymap_object(f, preset.name, voice, kid,
                                     sample_id_map, samples_by_name, base_pitch)

        # --- Program objects (one layer per voice) ---
        for pi, preset in enumerate(bank.presets):
            pid = base_id + pi
            _write_program_object(f, preset, pid, preset_keymaps[pi])
            print(f"  Program [{pid}] '{preset.name}': "
                  f"{len(preset_keymaps[pi])} layer(s)")

        # --- End marker + finalize ---
        f.write(struct.pack('>i', 0))

        osize = f.tell()
        f.seek(osize_pos)
        f.write(struct.pack('>i', osize))
        f.seek(osize)

        # --- Sample PCM data (big-endian 16-bit) ---
        for sample in samples:
            # Our internal format is 16-bit signed little-endian;
            # K2000 expects big-endian.  Swap pairs of bytes.
            data = sample.data
            swapped = bytearray(len(data))
            for j in range(0, len(data) - 1, 2):
                swapped[j]   = data[j + 1]
                swapped[j+1] = data[j]
            f.write(swapped)

        total = f.tell()
        print(f"  Written: {output_path} ({total/1024/1024:.2f} MB)")
