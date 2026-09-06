# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# KRZ binary layout derived from:
#   KurzFiler (GPL-2.0), Marc Halbrügge,
#     https://kurzfiler.sourceforge.io/
# Structure verified against one programs-only bank (K2000 production soundset).
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

import array
import copy
import math
import struct
from typing import List, Tuple

from models.common import (
    Bank, Preset, SampleData, VoiceLayer, LoopType,
    KRZ_ENV_TIME_GRID, KRZ_RELEASE_FACTOR, KRZ_RELEASE_SPAN_DB,
    E4B_CUTOFF_MAX_HZ,
    KEY_FILTER_OCT_PER_OCT,
    krz_cents_to_depth_byte,
    krz_cents_to_lfo_pitch_byte, LFO_PITCH_FULL_CENTS,
    AKAI_MUTE_CUT_SECONDS, RESONANCE_FULL_DB,
    KRZ_RES_KEYTRK_PIVOT_KEY, KRZ_RES_KEYTRK_DB_PER_UNIT,
    krz_db_to_level_pct, krz_level_pct_to_db,
    krz_cutoff_byte_to_hz, KRZ_2POLE_F0_TO_3DB, KRZ_4POLE_F0_TO_3DB,
    LFO_VOLUME_MODEL_FULL_DB, KRZ_F4_AMP_SRC1_INDEX,
    KRZ_F4_AMP_DEPTH_INDEX, KRZ_F4_AMP_SRC_LFO1, KRZ_F4_AMP_SRC_LFO2,
    KRZ_F4_AMP_DEPTH_DB_PER_UNIT, KRZ_F4_AMP_DEPTH_CLAMP,
    KRZ_F4_AMP_ADJUST_INDEX, KRZ_F4_AMP_ADJUST_DB_PER_UNIT,
    velocity_pivot_offset_db, velocity_pivot_preset_shift,
    fit_velocity_line, VELOCITY_CURVE_DB_LINEAR,
    VEL_VOL_PIVOT_KRZ,
)
from processors.loop_renderer import bake_alternating_loop
# The K2000 and the E4B both store stereo PCM planar (whole left channel, then
# whole right), so the de-interleaver is shared rather than reimplemented --
# duplicated codecs in this project have drifted before (CR-13/CR-17).
from writers.e4b_writer import _interleaved_to_planar


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
#: The K2000 sounds keymap entry `i` at key `i + 12` (HW-confirmed
#: 2026-08-02). With our fixed basePitch of 0 that puts the lowest
#: addressable key at 12; a non-zero basePitch would move it (see TODO.md).
FIRST_MAPPABLE_KEY = 12

#: OPT-IN, default OFF: emit ONE keymap object for voices whose keymaps come
#: out byte-identical, instead of one per voice.
#:
#: A keymap is 688 bytes of PRAM against a program's 272, so a bank of presets
#: that all share a layout wastes most of its PRAM on duplicates -- 300 such
#: presets carry 201 K of identical keymaps. Sharing them is what real K2000
#: banks do (a re-assembled 796-program bank was measured with 52 keymaps).
#:
#: Default OFF because it changes the bytes of every multi-preset bank we have
#: hardware-confirmed, and because the sharing itself is what is under test:
#: VinSamLib's 796-program/52-keymap bank hung a machine at 32% PRAM, which
#: would be explained if the K2000 materialises per-program state on load
#: rather than sharing the object the way the file does. Until a disc says
#: otherwise, this stays opt-in. See TODO "KRZ keymap sharing".
SHARE_IDENTICAL_KEYMAPS = False

KEYMAP_ENTRY_SIZE = 5  # Method2Size(0x13) = 2+2+1

#: Keymap variant that adds a PER-KEY-RANGE volume byte (§KRZSHAREDGAIN).
#:
#: `method` is a bitfield -- each bit adds one per-entry field, in this order:
#: 0x10 tuning i16 | 0x08 tuning i8 | 0x04 volumeAdjust i8 | 0x02 sampleID i16
#: | 0x01 subSample u8 -- so 0x17 is 0x13 plus the volume byte, which sits
#: between the i16 tuning and the i16 sampleID. See docs/KRZ_FORMAT.md 3.2;
#: `krz_parser._decode_table` has always decoded this, only the writer never
#: emitted it.
#:
#: HW-MEASURED on the panel (k2kremote, 2026-09-01): exactly **0.5 dB per
#: click, symmetric**, and the rails are **-63.5 .. +63.5 dB**, i.e. bytes
#: -127..+127 -- the field never uses 0x80. Do NOT clamp to -128 on the
#: assumption that a signed i8 reaches -64.0 the way the SAMPLE editor's
#: equivalent field does; 0x80 is the one value the panel cannot produce.
#: Per-key-range scoping confirmed by experiment rather than manual wording:
#: setting one range to 63.5 dB left the other two at 0.0 and it held.
KEYMAP_METHOD_VOL = 0x0017
KEYMAP_ENTRY_SIZE_VOL = 6   # Method2Size(0x17) = 2+1+2+1
_KEYMAP_VOL_MIN, _KEYMAP_VOL_MAX = -127, 127

NUM_KEYS = 128          # K2000 keyboard range
from models.diagnostics import emit as _diag, WARNING as _W, INFO as _I

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
    # THE STORED maxPitch FIELD.  Reverse-engineered from real third-party
    # soundsets (soundset 002): maxPitch = 100*root + 1200*log2(48000/sr)
    # (sr=30 kHz → +814, sr=15 kHz → +2014, both confirmed).
    #
    # THIS IS AN AUTHORING CONVENTION, NOT THE MACHINE'S PLAYBACK LIMIT, and
    # conflating the two cost us an octave of range (§KRZUPPITCH).  The K2000
    # plays a FULL OCTAVE past this value -- hardware-confirmed 2026-09-05 on
    # two samples an octave apart in stored rate, by raising a layer's HiKey
    # and reading the partial ladder.  A sample whose stored maxPitch says
    # key 83 tracks cleanly to key 95.
    #
    # So this function still writes the field the way every real soundset
    # writes it, and _compute_playback_ceiling() below -- NOT this -- decides
    # how far a zone may extend.
    return int(round(
        100 * root_note + 1200.0 * math.log(48000.0 / sample_rate, 2)
    ))


#: The K2000's real playback-rate ceiling, measured 2026-09-05 (§KRZUPPITCH).
#: Exported because convert.py and processors/resampler.py buy "up-pitch
#: headroom" against the same limit and had their own copies of the OLD 48000 --
#: which meant we downsampled 45 of 152 samples in a matrix build to buy
#: headroom the machine did not need, losing fidelity for nothing.
KRZ_PLAYBACK_CEILING_HZ = 96000.0


def _compute_playback_ceiling(sample_rate: int, root_note: int) -> int:
    # The MIDI pitch (×100 cents) above which the K2000 stops tracking and
    # freezes at one rate.  HARDWARE-MEASURED 2026-09-05 (§KRZUPPITCH):
    #
    #   smp root 71, stored 23999.808 Hz:  +24 plays (95 999 Hz), +25 caps
    #   smp root 66, stored 42762.455 Hz:  +14 plays (95 998 Hz), +15 caps
    #
    # Both last-playing rates are ~95 999 Hz and both first-capped rates are
    # ~101 707 Hz, so the ceiling lies strictly inside (95 999, 101 707) Hz.
    # 96000 is in that interval and 48000 is nowhere near it; 96000 is also
    # already the constant in _compute_base_pitch() below, which is what made
    # the 48000 here look wrong before anyone measured it.
    #
    # PINNED 2026-09-05 by a THIRD sample at an off-grid rate.  The two above
    # are 9.98 semitones apart -- the same semitone grid -- so their ladders
    # bracket the ceiling identically and gave a one-semitone interval rather
    # than four independent constraints.  A 44 099.488 Hz sample transposed
    # +14 asks for 99 000 Hz, which lands INSIDE that interval.  It caps.
    #
    # And the capped notes MEASURE the ceiling instead of bracketing it: above
    # the limit every key plays at the same frozen rate, so the plateau's pitch
    # IS the ceiling.  Key 64 plays a known 93 443.6 Hz; the plateau sits
    # +0.475 semitones above it -> 96 044 Hz, which is 0.8 cents from 96 000.
    # All six observations across three samples fit that value.
    #
    # Above the ceiling a note does NOT go silent: it plays at full level,
    # cleanly, at a frozen wrong pitch.  Any level-based check calls those keys
    # a success -- only the partials show it.
    return int(round(
        100 * root_note
        + 1200.0 * math.log(KRZ_PLAYBACK_CEILING_HZ / sample_rate, 2)
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

        # latin-1 so this is the exact inverse of krz_parser's latin-1 read:
        # no byte the parser produced can be altered on the way back out.
        #
        # NOT because 0x7F was being lost. 0x7F is authored in real K2000 names
        # -- the separator before a stereo pair's L/R marker,
        # 'VOI:Attack Voi\x7fL', 4 073 times across 4 627 local banks -- but it
        # is inside ASCII (0-127), so the previous encode preserved it exactly.
        # Both projects briefly believed otherwise; see RESOLUTION_NOTES
        # §NAMEBYTE. What this actually changes is bytes >= 0x80, of which the
        # corpus holds 12, all in names that are otherwise unprintable.
        nb = name.encode('latin-1', errors='replace')[:16]
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
    # Stereo is two Soundfilehead records over two PLANAR per-channel blocks
    # (docs/KRZ_FORMAT.md §3.1).  Corpus-verified over 533 real stereo samples
    # 2026-08-01: layout PLANAR 533/533, the two headers identical in rootkey,
    # sample rate and flags 533/533, and their loop points offset by exactly
    # the channel length 533/533 -- so the second header is the first with
    # every absolute word offset shifted by one channel.
    channels = 2 if getattr(sample, 'channels', 1) >= 2 else 1
    total_words = len(sample.data) // 2
    # Per-channel length.  Every word offset below is in CHANNEL words, which
    # for mono is just the sample length.
    num_words = total_words // channels
    loop_start_w = sample.loop_start
    loop_end_w   = sample.loop_end if sample.loop_end > 0 else num_words - 1
    period       = _compute_sample_period(sample.sample_rate)
    max_pitch    = _compute_max_pitch(sample.sample_rate, sample.root_note)

    looped = sample.loop_type != LoopType.NO_LOOP

    # Soundfilehead.flags — verified against real RAM-loaded soundsets (third-party soundset
    # soundset 002) and KurzFiler's WAV importer (LoadWaveMethod): a playable RAM
    # sample needs 0x70 (needsLoad 0x40 + the 0x10/0x20 playback-enable bits);
    # 0x40 alone loads the sample but produces NO SOUND.
    #
    # Loop on/off IS the 0x80 bit (hardware-confirmed 2026-06-16): the K2000
    # LOOPS when 0x80 is CLEAR and plays one-shot when 0x80 is SET.  The third-party soundset
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

    # KSample fixed header (12 bytes).  baseID=1 and HeadersOfs=8 match every
    # real soundset, mono and stereo alike (533/533 stereo samples in the
    # corpus carry baseID=1, HeadersOfs=8, numHeaders=1, flags=1).  flags bit0
    # is the stereo flag, so the old 0x40 here was meaningless.
    f.write(struct.pack('>hhhBBhh',
        1,             # baseID (always 1)
        channels - 1,  # numHeaders (0 = 1 header/mono, 1 = 2 headers/stereo)
        8,             # HeadersOfs (always 8)
        channels - 1,  # flags bit0: 0 = mono, 1 = stereo
        0,             # ks1
        0,             # copyID
        0,             # ks2
    ))

    # One Soundfilehead (32 bytes) per channel, planar: channel c's block
    # starts one channel-length after channel c-1's.
    # volumeAdjust / altVolumeAdjust: per-sample gain, signed i8 in 0.5 dB steps.
    # Our gain is per-zone (ZoneMapping.volume); write_krz aggregates it per sample
    # and passes it here.  0 dB → 0, so unity samples are unchanged (pending HW).
    # Real stereo samples carry the same value on both channels (533/533), so
    # the shared `va` is right rather than a simplification.
    va = _vol_adjust_byte(volume_db) & 0xFF
    for ch in range(channels):
        shift = ch * num_words
        # offsetToEnvelope points past the REMAINING headers at the shared
        # envelope records that follow the last one: (n-1-i)*32 + 8, and +6 for
        # the alt.  Mono reduces to the historic 8/6.  Corpus-verified on the
        # dominant stereo convention (439/533 are exactly 40/38 then 8/6; the
        # other 94 differ only in the alt slot, which we write identically to
        # the main envelope anyway).
        env_ofs = (channels - 1 - ch) * 32 + 8
        f.write(struct.pack('>BBBBhh',
            sample.root_note & 0xFF,
            sfh_flags & 0xFF,
            va,   # volumeAdjust      (signed i8, 0.5 dB steps)
            va,   # altVolumeAdjust   (same, applied when the Alt start is active)
            max_pitch & 0xFFFF,
            0,    # offsetToName
        ))
        f.write(struct.pack('>iiii',
            abs_start + shift,
            alt_start + shift,          # == sampleStart in real files
            loop_start_field + shift,   # loop start (looped) / end (one-shot)
            sample_end_field + shift,   # CR-10: loop end (looped) / PCM end (one-shot)
        ))
        f.write(struct.pack('>hhI',
            env_ofs,      # offsetToEnvelope
            env_ofs - 2,  # altOffsetToEnvelope
            period,
        ))

    # 2× Envelope default: [-1, 1, 0, 0, -1600, 0].  Shared by every header —
    # that is what the offsets above point at.
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
                           base_pitch: int,
                           zone_gain_db: dict = None) -> bytes:
    """
    Build 128 keymap entries for one voice's zones.

    Entry layout (method=0x0013): tuning(int16) sampleID(int16) SSNr(uint8).

    PER-RANGE VOLUME (§KRZSHAREDGAIN). `zone_gain_db` maps id(zone) -> the dB
    this zone needs ON TOP of the per-sample `volumeAdjust`. When any of them
    is non-zero the keymap is written in the 6-byte `0x17` form instead, with
    a volumeAdjust byte between the tuning and the sampleID. When they are all
    zero -- every bank that does not share a sample across presets at
    different levels -- the 5-byte `0x13` form is written exactly as before,
    so unaffected banks stay BYTE-IDENTICAL and the HW-verified unity banks
    cannot regress.

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

    **WHAT REAL BANKS DO INSTEAD, and why it matters (VinSamLib, 2026-08-12).**
    Over 400 real K2000 banks, restricted to drum-kit-shaped keymaps (>=8
    consecutive keys each holding a different sample -- 286 keymaps, 4823
    zones):

        root == key    684   14.2%
        root != key   4139   85.8%

    The common real shape is a FIXED root across many keys -- one keymap has
    root 60 on keys 36, 37 and 38. Under the automatic per-key transposition
    described above that would transpose, so those banks must be suppressing
    tracking by some per-program control rather than by root placement.

    OUR MECHANISM IS NOT THEIRS, and that is the point. We reach native pitch
    through the constant tuning offset, with tracking left at its default. A
    real bank reaches it by turning tracking off. **Both sound correct as
    written, and they diverge the moment a user edits the program** -- change
    the sample, the root or the key on ours and the offset that was cancelling
    the transposition is now cancelling the wrong amount.

    So this is not a bug and it is not confirmed correct either. The open
    question is which per-program control the K2000 uses for pitch tracking
    and what our output sets it to; if it defaults ON and real banks set it
    OFF, we are relying on a default that a user can change out from under the
    arithmetic. Recorded rather than acted on: nothing here is known wrong,
    and guessing at a control we have not identified is how the AKAI tuning
    field went 100x out.

    CR-1: one keymap PER VOICE (not one merged keymap per preset).  Combined
    with one program layer per voice, this stops later voices overwriting
    earlier ones per key, and lets distinct voices (key splits, layers, and the
    velocity layers our parsers model as separate voices) coexist.
    """
    # Only pay the 6-byte form when a zone actually needs a per-range volume;
    # otherwise emit exactly what we always did (§KRZSHAREDGAIN).
    zone_gain_db = zone_gain_db or {}
    _use_vol = any(round((zone_gain_db.get(id(z), 0.0)) * 2)
                   for z in (getattr(voice, 'zones', []) or []))
    _method = KEYMAP_METHOD_VOL if _use_vol else KEYMAP_METHOD
    _esize = KEYMAP_ENTRY_SIZE_VOL if _use_vol else KEYMAP_ENTRY_SIZE

    entries = bytearray(NUM_KEYS * _esize)
    lost_zones: list = []   # zones no part of which can be placed (see below)
    for zone in voice.zones:
        sid = sample_id_map.get(zone.sample_name, 0)
        if sid == 0:
            # An EMPTY sample name is an unassigned zone -- normal, and the
            # only case that occurs: measured over 9 535 corpus zones, all 36
            # unresolved references carry '' rather than a name, in banks that
            # do have samples. Skipping those is right and silence is right.
            #
            # A NON-empty name that does not resolve is different: the parser
            # produced a zone pointing at a sample it did not emit. That is an
            # internal inconsistency, it happens zero times today, and if it
            # ever starts happening the silence is what would hide it.
            if zone.sample_name:
                lost_zones.append((zone.sample_name, zone.lo_key, zone.hi_key,
                                   'no such sample in the bank'))
            continue
        sample = samples_by_name.get(zone.sample_name)
        r_sample = sample.root_note if sample is not None else 60   # written rootkey
        r_zone = zone.root_key if zone.root_key else r_sample
        # `zone.coarse_tune` (whole semitones -- a source that intentionally
        # repitches a zone by a full octave or more, e.g. AKAI TUNE combining
        # keygroup+zone fields to more than +/-100 cents) was never folded in
        # here (§KRZCOARSETUNE, found 2026-08-31): only `fine_tune` reached
        # the K2000 keymap entry, so any zone whose source tuning exceeded
        # +/-99 cents was silently detuned by whole semitones on write. The
        # E4B and AKAI writers both already read `coarse_tune` (`e4b_writer.py`
        # `_zone_entry`, `akai_s3000_writer.py`); the K2000 path is the one
        # that dropped it, not a deliberate KRZ-specific choice.
        tuning = 100 * (r_sample - r_zone + zone.coarse_tune) + zone.fine_tune
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
        #
        # The ceiling must be evaluated against r_zone (the zone's EFFECTIVE
        # root), not r_sample: the hardware's actual total pitch shift at key K
        # is (K - r_sample)*100 [auto-transpose] + tuning = (K - r_zone +
        # coarse_tune)*100 + fine_tune (substitute tuning above, now that it
        # carries coarse_tune too) — i.e. r_zone minus coarse_tune is what the
        # 48kHz internal engine limit is measured from: a positive coarse_tune
        # uses up exactly as much up-pitch headroom as lowering the effective
        # root by that many semitones would. Using r_sample here mis-flagged
        # deliberately retuned zones (r_zone != r_sample, e.g. a drum map that
        # cancels keytracking via a large per-entry tuning offset — found
        # 2026-07-27 building krz_parser.py, real third-party soundset
        # content) as over-ceiling even though their true shift is nowhere near
        # it, silently dropping the sample from the keymap.
        hi_key = min(zone.hi_key, NUM_KEYS - 1)   # defensive: never index past the 128-key buffer
        orig_hi = hi_key
        over_ceiling = False
        if sample is not None:
            ceiling = _compute_playback_ceiling(sample.sample_rate,
                                                r_zone - zone.coarse_tune) // 100
            over_ceiling = ceiling < zone.lo_key
            hi_key = min(hi_key, ceiling)

        # A zone is only worth reporting when NONE of it survives. Clipping
        # the bottom off a zone is the normal shape of a multisample: parsers
        # and _coverage_remap both extend the lowest zone down to key 0 as a
        # catch-all, and that zone still sounds from key 12 up -- nothing was
        # lost. Warning on those fired on nearly every bank, including two
        # test banks where no sample disappeared, which is how a warning
        # teaches people to ignore it.
        if over_ceiling:
            # The K2000 cannot pitch a sample arbitrarily far up, so a zone
            # sitting entirely above its sample's ceiling cannot be placed at
            # all. Measured over 7 082 corpus zones: 7.4 % are lost this way
            # and 43 % are merely clipped at the top -- reporting the clipped
            # ones would be the same noise the low-key warning started as.
            # These keys are NOT silent: the hole-filling below extends a
            # neighbour over them, so they play the WRONG sample instead.
            lost_zones.append((zone.sample_name, zone.lo_key, orig_hi,
                               'above the up-pitch ceiling'))
        elif hi_key < FIRST_MAPPABLE_KEY and hi_key >= zone.lo_key:
            lost_zones.append((zone.sample_name, zone.lo_key, hi_key,
                               f'below key {FIRST_MAPPABLE_KEY}'))

        for key in range(zone.lo_key, hi_key + 1):
            # The K2000 sounds entry `i` at key `i + 12`, so a zone that must
            # sound at `key` is written into entry `key - 12` (HW-confirmed
            # 2026-08-02; see parsers/krz_parser.KEYMAP_ENTRY_NOTE_OFFSET).
            # Writing entry[key] put every sample 12 keys above where it was
            # asked for, and left the keys actually played pointing at whatever
            # filled the entries below -- which is why a multisample keymap
            # sounded like ONE sample key-tracked.
            entry = key - 12
            if not 0 <= entry < NUM_KEYS:
                continue
            offset = entry * _esize
            if _use_vol:
                # tuning i16 | volumeAdjust i8 | sampleID i16 | subSample u8.
                # Clamped to +-127: the panel's rails are -63.5..+63.5 dB at
                # 0.5 dB/step, so 0x80 is a value the machine cannot produce.
                _vb = max(_KEYMAP_VOL_MIN, min(_KEYMAP_VOL_MAX,
                          int(round(zone_gain_db.get(id(zone), 0.0) * 2))))
                struct.pack_into('>hbHB', entries, offset,
                                 tuning, _vb, sid & 0xFFFF, 1)
            else:
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
    ES = _esize
    # The sampleID sits after the i16 tuning, and after the volume byte too
    # when the 0x17 form is in use -- so its offset within the entry is not a
    # constant. Getting this wrong would read the tuning's low byte as half a
    # sample id, making every entry look non-empty and silently disabling the
    # hole-fill below, which is the delete-lockup guard.
    _SID_OFF = 3 if _use_vol else 2
    def _sid(off):
        return (entries[off + _SID_OFF] << 8) | entries[off + _SID_OFF + 1]
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

    return bytes(entries), _method, _esize, 0, lost_zones


def _write_keymap_object(f, name: str, voice: VoiceLayer, obj_id: int,
                          sample_id_map: dict, samples_by_name: dict,
                          base_pitch: int, zone_gain_db: dict = None) -> list:
    entries, method, entry_size, header_sid, lost = _build_keymap_entries(
        voice, sample_id_map, samples_by_name, base_pitch, zone_gain_db)

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
    return lost


# ---------------------------------------------------------------------------
# Program object  (KProgram segments)
# ---------------------------------------------------------------------------

def _voice_span(v):
    """(lowest key, highest key) this voice sounds over."""
    zs = [z for z in getattr(v, 'zones', []) or []]
    return (min(z.lo_key for z in zs), max(z.hi_key for z in zs)) if zs else (0, -1)


def _spans_disjoint(a, b):
    la, ha = _voice_span(a)
    lb, hb = _voice_span(b)
    return ha < lb or hb < la


def _spans_adjacent(a, b):
    """True when two DISJOINT spans touch with no key between them -- fusing
    them leaves no hole for `_build_keymap_entries`'s gap-fill to patch."""
    la, ha = _voice_span(a)
    lb, hb = _voice_span(b)
    return ha + 1 == lb or hb + 1 == la


#: CONTINUOUS voice-level quantities: averaged when two layers fuse.
#:
#: The first version listed only the three filter fields, so a layer's velocity
#: tracking and key-follow were silently dropped while the banner announced
#: that "filter settings" had been averaged. The rule is now explicit --
#: anything physically interpolable is averaged and named; anything categorical
#: refuses the fusion outright (see `_voice_distance`). A field that is neither
#: listed here nor checked there would be dropped in silence, which is what
#: happened.
_VOICE_FIT_FIELDS = ('filter_cutoff', 'filter_resonance', 'filter_env_cents',
                     'filter_keytrack', 'velocity_to_filter_cents',
                     'velocity_to_filter_min_cents', 'lfo1_to_volume')


def _voice_distance(a, b):
    """How unlike two voices are, for choosing which pair to fuse.

    Only the CONTINUOUS voice-level fields count. Anything categorical -- the
    filter type, the envelopes, the LFO routing -- cannot be averaged, so a
    pair differing in one of those is refused outright rather than given a
    large distance: an averaged envelope is not a compromise between two
    envelopes, it is a third envelope neither layer asked for.
    """
    for name in ('filter_type',):
        if getattr(a, name, None) != getattr(b, name, None):
            return None
    for env in ('amp_env', 'filter_env'):
        ea, eb = getattr(a, env, None), getattr(b, env, None)
        if repr(ea) != repr(eb):
            return None
    if (getattr(a, 'lfo1_rate', None) != getattr(b, 'lfo1_rate', None)
            or getattr(a, 'lfo1_to_pitch', None) != getattr(b, 'lfo1_to_pitch', None)):
        return None
    # ANYTHING NOT AVERAGED MUST MATCH, or fusing silently drops the loser's
    # value. `_patch_layer` also consumes `velocity_to_filter_cents` and
    # `lfo1_shape`, and the first version of this compared neither -- so a
    # 4-layer split whose top layer tracked velocity into the filter lost that
    # entirely, while the deliberately loud banner said only that "filter
    # settings" were averaged. Refusing is right rather than averaging them
    # too: a velocity-tracking depth is not obviously interpolable, and a
    # program that stays a drum program is a visible failure where a silently
    # dropped modulation is not.
    #
    # VELOCITY->VOLUME JOINED THIS LIST 2026-09-04, and it is the same fault the
    # paragraph above describes, in a field added after that paragraph was
    # written. `velocity_to_volume_db` was neither averaged nor compared, so
    # fusing two voices kept the FIRST one's swing and dropped the other's in
    # silence. Caught building the listening set: an MPC preset whose four
    # voices ask for 0.0, 17.2 and 19.0 dB came out of the writer as two layers
    # both reading AMP VelTrk 0 -- the 0.0 voice won both fusions and the entire
    # velocity response of the preset was gone, with nothing printed.
    #
    # REFUSING rather than averaging, for the reason already given here: the
    # pivot and the curve have no meaningful interpolation at all (what is the
    # average of an amplitude-linear voice and a dB-linear one?), and a swing
    # averaged across voices that deliberately differ is not the source's
    # intent either. A program that declines to fuse is a visible outcome; a
    # program whose dynamics quietly vanished is not.
    for name in ('lfo1_shape', 'lfo1_delay',
                 'velocity_to_volume_db', 'velocity_to_volume_pivot',
                 'velocity_to_volume_curve'):
        if getattr(a, name, None) != getattr(b, name, None):
            return None
    d = 0.0
    for name in _VOICE_FIT_FIELDS:
        d += abs((getattr(a, name, 0.0) or 0.0) - (getattr(b, name, 0.0) or 0.0))
    return d


def _fuse_voices(a, b):
    """Fold b into a: zones concatenated, continuous fields key-span weighted.

    Weighted by how many keys each voice covers, so the setting that governs
    most of the keyboard dominates the compromise rather than both counting
    equally regardless of how much they are heard.
    """
    la, ha = _voice_span(a)
    lb, hb = _voice_span(b)
    wa, wb = max(1, ha - la + 1), max(1, hb - lb + 1)
    for name in _VOICE_FIT_FIELDS:
        va = getattr(a, name, 0.0) or 0.0
        vb = getattr(b, name, 0.0) or 0.0
        setattr(a, name, (va * wa + vb * wb) / (wa + wb))
    a.zones = list(a.zones) + list(b.zones)
    return a


def _group_overlapping(voices):
    """Partition voices into clusters of transitively overlapping key spans.

    `_fit_layers` only fuses DISJOINT pairs, so whatever is left when it gives
    up is, by construction, made of one or more clusters where every voice
    overlaps at least one other in the same cluster. Grouped by transitive
    overlap (union-find) rather than a single shared span, since three voices
    covering 0-40 / 30-70 / 60-100 pairwise-overlap their neighbours without
    all three sharing one common range.
    """
    n = len(voices)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if not _spans_disjoint(voices[i], voices[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(voices[i])
    return list(groups.values())


def _thin_velocity_voices(voices, limit):
    """Reduce a VELOCITY-SPLIT group (voices that share/overlap one key
    region, split only by velocity -- e.g. a 4-layer soft/hard piano stack)
    to `limit`, widening survivors' velocity ranges to absorb the gap.

    This is `_fit_layers`'s counterpart for the axis it deliberately leaves
    alone: `_fit_layers` fuses DISJOINT (key-split) voices only, because
    fusing overlapping ones "would delete a voice rather than approximate
    one" -- true for two voices covering the SAME velocity range, but a
    velocity-split voice does not need fusing, it needs its neighbour's
    range widened, which is a lossy-but-real approximation (fewer dynamic
    steps), not a deletion. Reuses `zone_reducer`'s redistribution so the
    two velocity-reduction code paths in this project (this one, and
    `--reduce-velocity-layers`) share one implementation.
    """
    if len(voices) <= limit:
        return voices, 0
    from processors.zone_reducer import _thin_and_redistribute

    def voice_lo(v):
        return min((z.lo_vel for z in getattr(v, 'zones', []) or []), default=0)

    def voice_hi(v):
        return max((z.hi_vel for z in getattr(v, 'zones', []) or []), default=127)

    def set_range(v, lo, hi):
        for z in getattr(v, 'zones', []) or []:
            z.lo_vel = lo
            z.hi_vel = hi

    before = len(voices)
    keep_pct = 100.0 * limit / before
    kept = _thin_and_redistribute(list(voices), keep_pct, voice_lo, voice_hi, set_range)

    # VERIFY NOTHING WAS SILENTLY DROPPED. `_thin_and_redistribute` widens
    # survivors to absorb a gap only when the whole set forms one contiguous
    # non-overlapping chain; when it does not (found 2026-08-30 on split patch 1
    # E: after `_fit_layers`'s disjoint pass, one surviving "voice" carries
    # BOTH a full-range zone and a hard-hit-only zone -- min/max over its
    # zones makes it look like one wide band to `voice_lo`/`voice_hi`, which
    # is not what any of its individual zones actually cover) it falls back
    # to dropping the surplus item outright, unchanged ranges on the rest.
    # For a real drum kit's parallel velocity layers that drop is the
    # existing, accepted, lossy-but-reasonable compromise `--reduce-
    # velocity-layers` already ships. Here it is not: a voice built by
    # cross-key fusion can hold a low-velocity zone found nowhere else, and
    # dropping it leaves a real gap wearing a "regular 3-layer program"
    # label -- worse than the drum program it was meant to replace, because
    # a drum program is at least honestly silent about the tradeoff.
    #
    # So: check every zone in a REMOVED voice against the survivors. If some
    # (key range, low-velocity edge) it covered is not covered by a
    # surviving zone at least as low, this reduction was a deletion, not an
    # approximation -- refuse it and let the caller fall back to a drum
    # program instead.
    kept_zones = [z for v in kept for z in (getattr(v, 'zones', []) or [])]
    dropped_voices = [v for v in voices if v not in kept]
    for dv in dropped_voices:
        for dz in getattr(dv, 'zones', []) or []:
            covered = any(
                z.lo_key <= dz.lo_key and z.hi_key >= dz.hi_key and z.lo_vel <= dz.lo_vel
                for z in kept_zones)
            if not covered:
                return voices, 0    # unsafe: refuse rather than delete content

    return kept, before - len(kept)



def _thin_velocity_bands(voices, limit=3):
    """Reduce velocity-split layers to `limit`, keeping the WIDEST band per group.

    `_split_voice_by_velocity` turns one voice into one layer per velocity band,
    because a K2000 keymap holds a single sample per key and has no per-key
    velocity zones — bands that share a keymap collide, brightest wins. That is
    necessary and it is also what pushes a preset past three layers.

    When the program must play on a normal channel, something has to go, and
    what goes is dynamic resolution rather than key coverage: layers are grouped
    by key territory, and within each group the band with the WIDEST velocity
    window survives — the one a player spends most time inside. Dropping a key
    region instead would silence part of the keyboard, which is the failure this
    whole path exists to avoid.

    Returns (kept_voices, dropped_bands) so the caller can name what was lost.
    """
    def _terr(v):
        return (min(z.lo_key for z in v.zones), max(z.hi_key for z in v.zones))

    groups: dict = {}
    for v in voices:
        groups.setdefault(_terr(v), []).append(v)

    kept, dropped = [], []
    for terr in sorted(groups):
        band = sorted(groups[terr],
                      key=lambda v: -(max(z.hi_vel for z in v.zones)
                                      - min(z.lo_vel for z in v.zones)))
        kept.append(band[0])
        for v in band[1:]:
            dropped.append((min(z.lo_vel for z in v.zones),
                            max(z.hi_vel for z in v.zones)))

    # WIDEN THE SURVIVOR TO THE FULL VELOCITY RANGE, or the cure is worse than
    # the disease. The band we keep carries the window the SOURCE gave it —
    # e.g. 48-111 on this preset — and a layer only sounds inside its window.
    # Keeping it unchanged therefore leaves velocities 0-47 and 112-127 silent:
    # a program that plays on any channel but not at any dynamic, which is a
    # partial version of exactly the silence this default exists to prevent.
    # Verified on the rebuilt bank before this was added — the surviving layers
    # read vel 48-111 and would have shipped that way.
    for v in kept:
        for z in v.zones:
            z.lo_vel, z.hi_vel = 0, 127
    # Still over budget (many key regions): keep the widest-spanning ones.
    if len(kept) > limit:
        kept.sort(key=lambda v: -(max(z.hi_key for z in v.zones)
                                  - min(z.lo_key for z in v.zones)))
        for v in kept[limit:]:
            dropped.append((min(z.lo_vel for z in v.zones),
                            max(z.hi_vel for z in v.zones)))
        kept = kept[:limit]
    return kept, dropped


def _fit_layers(voices, limit=3):
    """Fuse the most similar DISJOINT voices until `limit` layers remain.

    **Why this is the default and faithful is the option (Jan, 2026-08-24).**
    A K2000 program with more than three split layers is a drum program and
    sounds only on a drum channel -- so a faithful four-layer electric piano
    is SILENT on a normal channel, which is not a subtler rendering of the
    preset, it is no rendering at all. A slightly averaged filter is a
    compromise a listener can hear and judge; silence is not.

    ONLY DISJOINT VOICES FUSE. Two layers that overlap on a key sound
    together, and folding them into one would delete a voice rather than
    approximate it -- the difference between losing detail and losing a
    layer. Voices that overlap therefore survive, and if too many of them do,
    the program stays a drum program and says so.

    TWO PASSES, not one (§AKAILAYERGAP, 2026-08-31, the reference preset, Jan). A single
    greedy pass fuses only the MINIMUM number of pairs needed to reach
    `limit` -- for the reference preset's 4 voices (1 merged choke-loser + 3 disjoint,
    identically-shaped pad survivors, see §AKAIMUTEGRP) that fused exactly
    two of the three pads and left the third standing alone, covering its own
    60-71 range. The two fused pads' spans don't touch (24-59 and 72-127,
    with the third pad's OWN 60-71 sitting between them), so the fused
    voice's own keymap gained a 60-71 HOLE -- and `_build_keymap_entries`'s
    delete-lockup-avoidance gap-fill (mandatory, HW-confirmed 2026-06-24)
    patched it by extending the 24-59 zone's sample across 60-71, the exact
    range the third, un-fused pad ALSO covers with its own, correct sample.
    Two layers now sound together over that one octave where the source only
    ever sounds one -- not a subtler rendering, an unintended doubling.

    PASS 1 fuses only ADJACENT (touching, `_spans_adjacent`) fusable pairs,
    repeatedly, with NO regard for `limit` -- a chain of adjacent same-shaped
    voices (all three of the reference preset's pads) collapses all the way to one, since
    doing so can never create a hole (adjacent spans tile with nothing
    between them) and is free: it costs no MORE parameter-averaging than
    fusing just two of them would have, while a partial fusion pays the same
    averaging cost AND leaves a hole. PASS 2, only if still over `limit`
    afterward, falls back to today's behaviour -- the closest fusable pair
    regardless of adjacency, accepting a real hole when there is truly no
    gap-free option left.

    Returns (voices, notes) where notes describes what was given up, so the
    caller can print it rather than leave the user to notice.
    """
    # COPY BEFORE MUTATING. `_fuse_voices` writes averaged fields onto the
    # surviving voice, and `_split_voice_by_velocity` hands back the ORIGINAL
    # object for a single-band voice -- so fusing in place edited the caller's
    # Bank. A converter run that writes KRZ and then another format would have
    # written the second one from averaged values it never asked for. Caught by
    # review; no test covers writing one Bank to two formats.
    import copy as _copy
    voices = [_copy.copy(v) for v in voices]
    for v in voices:
        v.zones = list(getattr(v, 'zones', []) or [])
        # REMEMBER EACH ZONE'S OWN RESONANCE BEFORE ANY FUSION AVERAGES IT
        # (§KRZRESKEYTRK). `filter_resonance` is per VOICE, so once two voices
        # merge the individual values are gone -- and that averaging is the
        # defect Jan heard. Stamping the zones keeps the source values
        # available to `_patch_layer`, which can then fit the K2000's own
        # per-key resonance ramp across them instead of writing a scalar.
        # Copied zones, so the caller's Bank is untouched.
        v.zones = [_copy.copy(z) for z in v.zones]
        for z in v.zones:
            z.src_resonance = getattr(v, 'filter_resonance', 0.0) or 0.0
    notes = []

    def _fuse_one(require_adjacent):
        best = None
        for i in range(len(voices)):
            for j in range(i + 1, len(voices)):
                if not _spans_disjoint(voices[i], voices[j]):
                    continue
                if require_adjacent and not _spans_adjacent(voices[i], voices[j]):
                    continue
                d = _voice_distance(voices[i], voices[j])
                if d is None:
                    continue
                if best is None or d < best[0]:
                    best = (d, i, j)
        if best is None:
            return False
        d, i, j = best
        before = tuple(round(getattr(voices[i], n, 0.0) or 0.0, 4)
                       for n in _VOICE_FIT_FIELDS)
        other = tuple(round(getattr(voices[j], n, 0.0) or 0.0, 4)
                      for n in _VOICE_FIT_FIELDS)
        _fuse_voices(voices[i], voices[j])
        after = tuple(round(getattr(voices[i], n, 0.0) or 0.0, 4)
                      for n in _VOICE_FIT_FIELDS)
        notes.append((before, other, after, d))
        voices.pop(j)
        return True

    # PASS 1: prefer ADJACENT fusions, which cannot leave a hole -- but stop at
    # the limit like any other pass.
    #
    # THIS USED TO RUN UNCONDITIONALLY (2026-08-31 -> 2026-09-01), on the
    # stated grounds that collapsing a whole adjacent chain "costs no MORE
    # parameter-averaging than fusing just two of them would have". That is
    # simply false: fusing three voices averages three values, fusing two
    # averages two. The error cost real fidelity on the reference preset, whose three pad
    # keygroups carry DIFFERENT resonances (FILQ 14/15/13 = 18.7/25.5/14.9 dB)
    # that the AKAI applies per key range. Collapsing all three gave every key
    # one averaged 17.5 dB -- 8.1 dB too little over 60-71 and 2.5 dB too MUCH
    # above 72, which is audible as a resonant "snap" that worsens with pitch
    # (Jan, by ear, 2026-09-01). Fusing only as far as the limit leaves the
    # third keygroup its own layer and its own resonance.
    #
    # Unlike gain (§KRZSHAREDGAIN) this has no per-key-range escape hatch: the
    # K2000's resonance is a per-LAYER DSP parameter, so a fused layer can
    # only hold one value. Fusing less is the only lever.
    while len(voices) > limit and _fuse_one(require_adjacent=True):
        pass
    while len(voices) > limit:
        if not _fuse_one(require_adjacent=False):
            break                       # PASS 2: nothing left that may legally fuse
    return voices, notes


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
    # via KurzFiler + a programs-only bank/a third-party bank + the VELAYRE.KRZ velocity diff):
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
    # CAL[7,8] is the SECOND keymap slot — one slot per channel, so it carries
    # the id only for a stereo layer.  (This function is currently unused; kept
    # consistent with _patch_layer so reviving it cannot reintroduce the mono
    # playback bug.  See docs/RESOLUTION_NOTES.md §KRZSTEREO2.)
    if stereo:
        cal[7] = (keymap_id >> 8) & 0xFF
        cal[8] =  keymap_id       & 0xFF
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
#   AMPENV       = ENV(0x21)  byte 0 = loop flag, then 7 (LEVEL,time) pairs
#                  from byte 1 (Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3).
#                  NOT (time,level)-from-byte-0 with the flag last: that was
#                  this file's assumption until §KRZENVLOOP disproved it on
#                  hardware 2026-08-31. See _fill_env for the full trace.
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
# CR-KRZ: now lives in models.common (single home shared with krz_parser.py).
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

#: THE PANNER, for carrying pan modulation (§PANMOD). Hardware-mapped
#: 2026-09-06 by k2kremote from a RAM-only SysEx diff, then aligned against a
#: real bank here.
#:
#: The F3 HOB segment (tag 0x52) holds it. `seg(0x52)[0]` is the block TYPE and
#: **40 selects PANNER**; the fields follow at `seg` index = program offset − 241:
#:
#:     seg[1] Adjust  1 %/unit, ±100      seg[5] Src1    control-source code
#:     seg[3] KeyTrk  0.2 %/key           seg[6] Depth   2 %/unit, ±200
#:     seg[4] VelTrk  2 %/unit, ±200      seg[8] MinDpt  seg[9] MaxDpt
#:     seg[10] Src2                       seg[11] Pad    0/6/12/18 dB
#:
#: Verified against a source layer whose panel reads Adjust −32 %: its F3
#: segment is `[0x52, 40, -32, ...]`, i.e. type 40 then −32 at seg[1].
#:
#: **THE PANNER ONLY EXISTS IN ALGORITHMS 2, 13, 24 AND 26** (K2000 manual
#: Ch.14). Algorithm 2 is `PITCH → [filter] → PANNER → AMP` and its filter slot
#: offers 2POLE LOWPASS **with resonance** (Jan read that off the panel), which
#: is what makes carrying pan free rather than a trade: a 12 dB lowpass source
#: keeps its slope AND its resonance and gains the panner.
_K2_F3_PANNER = 40
_K2_ALG_PANNER = 2
_K2_PAN_ADJUST, _K2_PAN_SRC1, _K2_PAN_DEPTH = 1, 5, 6


def _env_steps(seconds: float) -> float:
    t = max(0.0, min(60.0, seconds))
    s = 0.0
    for lo, hi, st in KRZ_ENV_TIME_GRID:
        if t <= lo:
            break
        s += (min(t, hi) - lo) / st
    return s


def _env_time_byte(seconds: float) -> int:
    return max(3, min(255, round(_env_steps(seconds) + 3)))


def _lvl_byte(pct: float) -> int:
    """A K2000 envelope-level byte from a DISPLAYED PERCENT.

    Raw, deliberately: the percent is what the machine's own page shows, and
    several callers legitimately want to name a display value (Att stages at
    100 %, a null stage at 0). Callers that hold an AMPLITUDE -- a model
    `sustain`, a level in dB -- must convert through `_lvl_byte_amp` or
    `krz_db_to_level_pct` first, because the display is NOT linear amplitude
    (§KRZLEVELCURVE).
    """
    return round(max(-100.0, min(100.0, pct))) & 0xFF       # signed %


def _lvl_byte_amp(fraction: float) -> int:
    """A K2000 envelope-level byte from a LINEAR AMPLITUDE fraction (0..1).

    §KRZLEVELCURVE, 2026-08-31: the displayed percent is dB-linear in two
    segments and then collapses -- 50 % is -18.07 dB, not -6.02 dB. Writing
    `fraction * 100` into the field, which is what this writer did from the
    beginning, therefore lands every level far below where the source asked,
    and worst at the bottom: the reference preset's 3.26 % pad sustain measured -69 dB
    against the AKAI's own -29.73 dB, about 39 dB adrift. Going through the
    measured table puts it at 21.1 %, which reproduces -29.7 dB on hardware.
    """
    f = max(0.0, min(1.0, fraction))
    if f <= 0.0:
        return 0
    return _lvl_byte(krz_db_to_level_pct(20.0 * math.log10(f)))


def _vel_byte(lo_vel: int, hi_vel: int) -> int:
    """Pack a MIDI velocity range into LYR data[5] (K2000).

    HW-confirmed 2026-06-24 by diffing VELAYRE.KRZ (3 layers saved on the K2000R
    with known LoVel/HiVel): the layer velocity window is a SINGLE byte holding
    two 0–7 dynamic marks (ppp=0 … fff=7) — LoVel in bits 3–5, HiVel in bits 0–2
    stored INVERTED (7−mark).  So a full-range layer (ppp…fff) is 0, which is why
    every factory layer reads 0 and the field was invisible in static files.

    LO_MARK ROUNDS DOWN, NOT TO NEAREST (2026-08-30, §KRZVELBOUND). A note
    played AT EXACTLY a mark's own first-defining velocity is not reliable on
    real hardware: an AKAI velocity-split layer with lo_vel=100 -- which
    round(100/127*7) computes as exactly the first integer velocity of mark 6
    -- played SILENT at velocity 100 on the K2000R and clean at 99 and 110,
    both neighbours. k2kremote confirmed the mechanism surgically: nudging
    that live layer's mark down by one (6 -> 5) fixed the exact-100 dropout
    with nothing else changed. The K2000 firmware cannot cleanly resolve a
    note landing exactly on a mark's boundary-defining value, so this writer
    now never places a boundary there deliberately -- floor() puts `lo_mark`
    a step below the nearest edge instead of on it, same principle as this
    project's key-zone/velocity-layer widening elsewhere: prefer a layer
    that starts a few velocity units early over one that can silently drop
    the exact value it was built to include. `hi_mark` uses the mirror
    (ceil()) for the same reason on the top edge, untested on hardware but
    the same mechanism applies by symmetry.
    """
    import math
    lo_mark = max(0, min(7, math.floor(lo_vel / 127 * 7)))
    hi_mark = max(0, min(7, math.ceil(hi_vel / 127 * 7)))
    return ((lo_mark & 0x07) << 3) | ((7 - hi_mark) & 0x07)


# Two-leg release shape (see _fill_env) — HW-validated knee/split, AlphaPad #200.
#
# _REL_KNEE_PCT IS A DISPLAYED PERCENT AND STAYS ONE, DELIBERATELY
# (§KRZLEVELCURVE, 2026-08-31). It was chosen as "33 % of full", meaning
# -9.6 dB, on the assumption the field was linear amplitude. It is not: 33 %
# measures about -24.8 dB, so the knee has always sat ~15 dB below where it
# was described as sitting.
#
# It is NOT being "corrected" to 71 % (the percent that would really give
# -9.6 dB), and that is a decision rather than an oversight. The knee and the
# 80/20 split were validated BY EAR on real hardware (AlphaPad #200,
# 2026-06-24) -- so what was actually judged good was the shape this constant
# really produces, not the shape its label claimed.
#
# THAT NOW RESTS ON MEASUREMENT, NOT INFERENCE (2026-08-31). When this comment
# was first written the release stages were only ASSUMED to share the level
# curve measured on Dec1. They were then tested: Rel 50 % renders -18.06 dB
# against a predicted -18.07, so -24.8 dB really is what 33 % produces here
# and the listener's approval attaches to that shape. Moving it to the intended
# -9.6 dB would discard that validation and change a release that a listener
# already approved. The label was wrong; the sound was right.
#
# So: the number stays, the comment now says what it means, and re-deriving
# the knee in dB is a job for whoever next validates a release by ear.
# Contrast the SUSTAIN, which is genuinely wrong rather than mislabelled --
# it has to match a level the source specifies, and now goes through
# `_lvl_byte_amp`.
_REL_KNEE_PCT   = 33.0    # Rel1 target, DISPLAYED percent (~-24.8 dB, measured)
_REL1_TIME_FRAC = 0.8     # fraction of the release time spent reaching the knee

# KRZ-only release-time correction.  The shared MPC value→seconds curve
# (_xpm_env_to_seconds, fit in §18 to audio time-to-−40 dB) under-reads the MPC's
# DISPLAYED release time by a ~constant factor: AlphaPad VolumeRelease 0.764 →
# curve 1.39 s vs the MPC AMPENV display 2.63 s (Jan, 2026-06-24). Scaling here
# (KRZ-writer only) avoids lengthening every E4B/E4XT envelope; the proper global
# recalibration of the shared curve is a deferred TODO (needs a by-ear E4B check).
# CR-KRZ: now lives in models.common as KRZ_RELEASE_FACTOR (shared w/ krz_parser.py).
_KRZ_RELEASE_FACTOR = KRZ_RELEASE_FACTOR   # = 2.63 / 1.39


#: The AKAI mute-cut re-model's REAL curve (§155 amendment, s3ked, 2026-08-31)
#: is two-stage: a fast fall to -23.4 dB by 12 ms, then a much slower second
#: fall (fit at 366 dB/s, 12-80 ms window, +-5.2 dB worst case) reaching the
#: noise floor well past 200 ms. `parsers.akai_s3000_parser._apply_mute_groups`
#: cannot carry that shape for every target format: `sustain` only means "the
#: level a held note stays at" on hardware whose release is gated on note-off,
#: which every format EXCEPT the K2000 is presumed to be (unverified for E4B/
#: EIII, so left alone there) -- writing a nonzero sustain there would turn a
#: too-short click into a WORSE bug, an audible choke that holds indefinitely.
#:
#: The K2000 is provably not gated: the entire §KRZENVLOOP investigation
#: (2026-08-27 -> 2026-08-31) only makes sense because Dec1->Rel1->Rel2->Rel3
#: run to completion automatically over TIME while a note is held, regardless
#: of note-off -- so a real sustain-then-release shape is SAFE here, and this
#: function substitutes it for the plain single-stage click the shared AKAI
#: model still carries, right before that click would otherwise be written.
_AK_CHOKE_STAGE1_DB = 23.4       # fall to this by 12 ms
_AK_CHOKE_STAGE1_S = 0.012
_AK_CHOKE_STAGE2_RATE_DB_S = 366.0


def _krz_choke_env(env):
    """AKAI mute-cut re-model, K2000-specific: swap the plain single-stage
    click for the real two-stage curve (see `_AK_CHOKE_STAGE1_DB` above).

    Matches by VALUE, not by a carried flag -- `_apply_mute_groups` builds
    `cut_env` as a plain `Envelope(0.0, AKAI_MUTE_CUT_SECONDS, 0.0, 0.0)` with
    nothing else distinguishing it, and this is the one place that constant's
    exact shape is meaningful rather than coincidental: nothing else in this
    project ever asks for a fixed 0.058s decay to absolute silence.
    """
    if (env is not None and getattr(env, 'attack', None) == 0.0
            and getattr(env, 'decay', None) == AKAI_MUTE_CUT_SECONDS
            and getattr(env, 'sustain', None) == 0.0
            and getattr(env, 'release', None) == 0.0
            and not getattr(env, 'release_rate_db_per_s', None)):
        import copy as _copy
        env = _copy.copy(env)
        env.decay = _AK_CHOKE_STAGE1_S
        env.sustain = 10.0 ** (-_AK_CHOKE_STAGE1_DB / 20.0)
        env.release_rate_db_per_s = _AK_CHOKE_STAGE2_RATE_DB_S
    return env


def _fill_env(b: bytearray, env) -> None:
    """Write an ADSR Envelope into a 15-byte ENV/ENC segment IN PLACE.

    TRUE K2000 layout (§KRZENVLOOP, HW-confirmed 2026-08-31 — see TODO.md /
    RESOLUTION_NOTES.md for the full trace): byte **0 is a loop flag**
    (0=Off, 1=seg1F, 2=seg2F, 3=seg3F), then seven `(level, time)` pairs —
    NOT `(time, level)` — packed from byte **1**: `Att1 Att2 Att3 Dec1 Rel1
    Rel2 Rel3`, with levels on the odd bytes [1,3,…,13] and times on the even
    bytes [2,4,…,14].

    THIS SUPERSEDES THE 2026-06-24 "HW-confirmed" NOTE BELOW, WHICH WAS WRONG.
    Triple-confirmed independently on 2026-08-31: (1) k2kremote's controlled
    991/992 single-byte A/B DUMP diff, which is what first read the values
    0/1/2/3 = Off/seg1F/seg2F/seg3F at byte 0; (2) the reference preset Layer 2's real,
    correctly-sounding envelope, whose on-disk bytes are byte-identical to the
    device's and decode correctly ONLY under this convention; (3) a genuine,
    untouched ROM factory object (program 1, "Acoustic Piano") with seven
    independently distinguishable values that match this convention field for
    field and fail the old one at the first non-trivial field. No load-path
    transform exists between file and device — file bytes are device bytes.

    ROOT CAUSE OF §KRZENVLOOP (the "envelope re-cycle" finding first raised
    2026-08-27 and originally mistaken for a K2000 firmware defect): under the
    OLD (wrong) convention this function wrote byte 0 as `tb(env.attack)` —
    the "Att1 time" byte under the old scheme. `_env_time_byte` floors at 3,
    so nearly any zero/short-attack envelope wrote literal byte value 3 into
    what is ACTUALLY the loop-flag byte — engaging an active loop (seg3F) by
    accident, on nearly every envelope this writer has ever produced for the
    K2000. Not a firmware quirk: a self-inflicted byte-layout bug, now fixed.

    ORIGINAL (WRONG) NOTE, preserved for the trace, NOT to be trusted:
    "K2000 layout (HW-confirmed 2026-06-24, Jan — read the AMPENV LCD against
    the on-disk bytes): seven `(time, level)` pairs packed from byte 0 —
    `Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3` — with times on the even bytes
    [0,2,…,12] and levels on the odd bytes [1,3,…,13]; byte 14 is a trailing
    flag (loop), left untouched." k2kremote's own guess (unverified) is that
    this was checked by eye against a case where the shift happened to look
    plausible, rather than via a controlled byte-flip.

    BUG FIXED 2026-06-24 (this part is unaffected by the above — still true):
    the old code started writing at byte **2**, shifting every segment by one
    pair — the decay-to-sustain landed in the K2000's Rel1 (so Rel1 read
    100% and never faded) and the release fade landed in Rel2. HW symptom
    (AlphaPad #200): levels Att1..Rel2 all read 100% except Rel2=0, giving a
    held-then-cut release instead of a fade from sustain to silence.
    """
    tb, lv = _env_time_byte, _lvl_byte
    # THE SUSTAIN IS AN AMPLITUDE AND THE FIELD IS NOT (§KRZLEVELCURVE).
    # `env.sustain` is a linear amplitude fraction; the K2000's displayed
    # percent is dB-linear in two segments and then collapses. `sus` below is
    # therefore the DISPLAYED PERCENT that reproduces that amplitude, not the
    # fraction times 100 -- which is what this line used to be, and is why
    # the reference preset's 3.26 % pad sustain measured -69 dB on hardware against the
    # AKAI's own -29.73 dB. It now writes 21.1 %.
    #
    # Keeping `sus` in DISPLAY space also makes the `sus > _REL_KNEE_PCT`
    # test below a like-for-like comparison for the first time: the knee is a
    # displayed percent too, and the old code was comparing a linear-amplitude
    # figure against it.
    sus = (krz_db_to_level_pct(20.0 * math.log10(env.sustain))
           if env.sustain > 0.0 else 0.0)
    # Two-leg release: the MPC release is ~exponential (linear in dB); a single
    # linear K2000 Rel1 sus→0 holds too loud then collapses ("sharp cutoff").
    # Approximate with a long first leg down to a knee, then a short tail to
    # silence.  Knee + split validated by ear on the K2000R (AlphaPad #200, Jan
    # 2026-06-24: Rel1 2.16 s → 33 %, Rel2 0.5 s → 0 %; total ≈ the release time).
    # PREFER A CARRIED RATE (§CORPUSRT / KRZ_RELEASE_SPAN_DB, 2026-08-25).
    #
    # The K2000 is a RATE machine -- its slope is invariant across sustain
    # levels -- and its displayed release time is the seconds to cross a FIXED
    # span of ~99.4 dB, measured at two settings on a purpose-built subject and
    # agreeing to 0.62%. So a source that knows its own release RATE can be
    # converted exactly: seconds = span / rate.
    #
    # `_KRZ_RELEASE_FACTOR` stays for sources that only state a duration. It
    # was derived by comparing this machine's DISPLAYED release against
    # another's, which is two conversions of an unmeasured span rather than one
    # measurement of a real one -- fine as a fallback, wrong to prefer.
    #
    # THIS IS AN AUDIBLE CHANGE. An AKAI source at 15.22 dB/s went to 3.76 s
    # and now goes to 6.53 s. That is the same defect the E4B path carried
    # until 2026-08-24, one format over: matching SECONDS across two machines
    # that disagree about where silence is.
    _rrate = getattr(env, 'release_rate_db_per_s', None)
    if _rrate:
        rel = KRZ_RELEASE_SPAN_DB / _rrate
    else:
        rel = env.release * _KRZ_RELEASE_FACTOR      # KRZ-only time correction
    # THE KNEE IS ABOVE-SUSTAIN ONLY WHEN SUSTAIN IS ABOVE THE KNEE.
    #
    # `_REL_KNEE_PCT` is a fixed 33% of full scale, and the two-leg shape it
    # anchors was validated on AlphaPad #200 at a sustain comfortably above
    # that (2026-06-24). Nothing guarded the case where SUSTAIN ITSELF sits
    # below 33% -- found 2026-08-27 on an AKAI source converted at sustain
    # 3.3%. Written literally, Rel1 asks the K2000 to move from a 3.3% start
    # UP to a 33% target over 5.2s: not a release at all, since a release only
    # ever decreases, and undefined behaviour on real hardware -- measured on
    # this exact patch, the audible tail collapsed to the noise floor by
    # ~2.5-3s instead of the intended ~6.5s, matching neither leg's own
    # nominal duration.
    #
    # The two-leg shape exists to avoid "holds too loud then collapses" when
    # sustain is high; that problem does not exist when sustain is already
    # below the knee, so the fix is not a smaller knee -- it is aiming BOTH
    # legs at silence instead of one of them at the knee.
    #
    # NOT `[(rel, 0), (0.0, 0)]` — found on the bench the same day (§KRZDBLZERO):
    # a Rel2 with time AND level both zero, immediately followed by Rel3
    # (always (0.0, 0)), reads to the K2000 as TWO CONSECUTIVE null stages —
    # and it responds by looping the whole envelope back to Att1 while the
    # key is still held, repeating every ~rel seconds, rather than holding at
    # silence. The validated two-leg shape never hits this: its own Rel2 has
    # a real nonzero TIME (`rel * (1-frac)`) even though its level is 0, so
    # only Rel3 is ever a genuine (0, 0). Keeping the same 80/20 time split
    # here — both legs now aimed at 0 instead of one at the knee — reproduces
    # that same "one zero-zero stage, not two" shape and stays monotonic.
    if sus > _REL_KNEE_PCT:
        pairs_rel = [(rel * _REL1_TIME_FRAC, _REL_KNEE_PCT),  # Rel1 — fade to the knee
                    (rel * (1.0 - _REL1_TIME_FRAC), 0)]       # Rel2 — short tail to silence
    else:
        pairs_rel = [(rel * _REL1_TIME_FRAC, 0),              # Rel1 — fade toward silence
                    (rel * (1.0 - _REL1_TIME_FRAC), 0)]       # Rel2 — nonzero time, same target
    pairs = [(env.attack, 100),                      # Att1 — ramp to full
             (0.0, 100),                             # Att2
             (0.0, 100),                             # Att3
             (env.decay, sus)] + pairs_rel + [        # Dec1 — decay to sustain
             (0.0, 0)]                                # Rel3
    b[0] = 0   # loop flag -- Off (§KRZENVLOOP byte-layout fix, 2026-08-31)
    o = 1
    for t, l in pairs:
        b[o] = lv(l); b[o + 1] = tb(t); o += 2


#: The K2000 cutoff byte is signed semitones on the standard pitch scale,
#: Hz = 440 * 2**((b - 9) / 12) -- so byte 9 is A4. `krz_cutoff_byte_to_hz` in
#: models.common is that law, and the KRZ READER already decodes through it.
_KRZ_CUT_BYTE_MIN, _KRZ_CUT_BYTE_MAX = -48, 79

#: F2 RES KeyTrk rail: the panel stops at +-2.00 dB/key = +-100 units.
#: NOT the +-127 a signed i8 would allow (HW-measured 2026-09-01).
_KRZ_RES_KT_CLAMP = 100


def _cutoff_byte_hz(hz: float) -> int:
    """filter_cutoff in HERTZ -> K2000 signed-semitone byte.

    **This used to stretch the position linearly across the byte range**
    (`-48 + cutoff01 * 127`) and it put the filter in the wrong place on every
    KRZ we wrote. Both scales are logarithmic in frequency, so the shape was
    right, but the endpoints are not the same: the position it stretched spans
    57 Hz-20 kHz (8.45 octaves) and the byte range spans 16 Hz-25088 Hz
    (10.61 octaves). Stretching one onto the other misplaced every interior
    value -- measured against what the model asked for:

        position 0.0   57 Hz wanted,    16 Hz written   -1.80 octaves
        position 0.3  331 Hz wanted,   147 Hz written   -1.17 octaves
        position 0.5 1068 Hz wanted,   659 Hz written   -0.70 octaves
        position 0.8 6194 Hz wanted,  5920 Hz written   -0.07 octaves

    worst exactly where filtered material lives. For scale, the AKAI writer's
    equivalent mapping was checked against hardware on 2026-08-22 and came back
    within 0.05 octaves.

    Going through Hz makes this the exact inverse of `krz_cutoff_byte_to_hz`,
    which the reader already uses -- `docs/KRZ_FORMAT.md` recorded the two
    curves disagreeing and named this fix as "a follow-up (not yet done)".

    Since 2026-08-25 the model carries the frequency itself, so the position
    half is gone: the argument IS the Hz.  That also removes the 57 Hz floor
    this used to impose -- the K2000 tunes down to 16 Hz and a source darker
    than the E4B scale reaches no longer gets clamped up on the way through.

    **What is fixed and what is not.** The Hz->byte half rests on the documented semitone law, which
    is NOT yet hardware-confirmed: CUTCAL (§KRZCUTCAL) measures it. If that
    measurement disagrees, the correction belongs in `krz_cutoff_byte_to_hz`,
    where reader and writer will both pick it up, rather than here.
    """
    semitones = 9.0 + 12.0 * math.log2(max(1e-6, hz) / 440.0)
    return max(_KRZ_CUT_BYTE_MIN,
               min(_KRZ_CUT_BYTE_MAX, round(semitones))) & 0xFF


def _reson_keytrack_fit(voice):
    """Fit the K2000's per-key resonance ramp across a fused layer's zones.

    Returns `(adjust_db, keytrack_db_per_key)`, or None when a flat value is
    as good or better -- which is the common case and must stay the default.

    WHY THIS EXISTS. `filter_resonance` is per VOICE while a source's is often
    per key range, so fusing layers averages resonances the source applied
    separately. On the reference preset that was audible: three pad keygroups at 18.7 /
    25.5 / 14.9 dB collapsed to one value, 2.5 dB too resonant above key 72,
    which Jan heard as a resonant snap worsening with pitch (§AKAILAYERGAP).
    Fusing less fixed the top range but left keys 60-71 6.5 dB under, and with
    the program already at the K2000's three-layer maximum there is no further
    lever -- except this one.

    THE LAW (k2kremote, HW-measured 2026-09-01, §KRZRESKEYTRK):

        resonance(key) = Adjust + KeyTrk * (key - 60)

    linear in key and in the setting, pivot at middle C, displayed dB/key
    literal to within 1 %, and 0 genuinely neutral.

    ONLY WHEN IT ACTUALLY HELPS, and that is not a formality. KeyTrk is a
    LINEAR RAMP while a source's resonances are PIECEWISE CONSTANT, so a ramp
    can only help when they trend one way. the reference preset's rise then fall (18.7 ->
    25.5 -> 14.9); fitting all three in one layer measured WORSE than the
    three-layer split (RMS 2.81 dB against v15's, worst 7.8 dB). So the fit is
    computed, scored against the flat alternative over the actual key span,
    and discarded unless it wins.
    """
    zones = [z for z in (getattr(voice, 'zones', []) or [])
             if z.src_resonance is not None]
    if len(zones) < 2:
        return None
    # One point per KEY, so a wide zone counts for more than a narrow one --
    # the error that matters is per key played, not per zone authored.
    pts = [(k, z.src_resonance * RESONANCE_FULL_DB)
           for z in zones for k in range(z.lo_key, z.hi_key + 1)]
    if len({round(r, 3) for _k, r in pts}) < 2:
        return None                      # all the same: a scalar is exact
    n = len(pts)
    sx = sum(k - KRZ_RES_KEYTRK_PIVOT_KEY for k, _r in pts)
    sy = sum(r for _k, r in pts)
    sxx = sum((k - KRZ_RES_KEYTRK_PIVOT_KEY) ** 2 for k, _r in pts)
    sxy = sum((k - KRZ_RES_KEYTRK_PIVOT_KEY) * r for k, r in pts)
    den = n * sxx - sx * sx
    if not den:
        return None
    slope = (n * sxy - sx * sy) / den
    intercept = (sy - slope * sx) / n
    flat = sy / n
    err_ramp = sum((intercept + slope * (k - KRZ_RES_KEYTRK_PIVOT_KEY) - r) ** 2
                   for k, r in pts)
    err_flat = sum((flat - r) ** 2 for _k, r in pts)
    if err_ramp >= err_flat * 0.95:      # must be a real win, not a rounding
        return None
    return intercept, slope


def _reson_byte(reson01: float) -> int:
    return max(0, min(48, round(reson01 * 48)))             # dB*2, max 24 dB


def _lfo_pitch_depth_byte(amount: float) -> int:
    """LFO1->Pitch cord amount 0..1 -> K2000 CAL[22] depth byte.

    **This used to be `round(amount * 79)`.** Unlike the filter-envelope depth
    (`_filter_env_depth_byte`), the full-scale end of that mapping looked
    entirely reasonable: byte 79 is 1200 cents, a clean 1.000 octave, exactly
    what "full vibrato" ought to be. It is not what full vibrato is here --
    `LFO_PITCH_FULL_CENTS` was measured on the E4XT at 1593 cents, +-16
    semitones, and its own comment already records that "+-1 octave" was a
    wrong assumption once before. The plausible number was the disproved one.

    The real damage was below full scale. The K2000's curve tracks cents 1:1
    up to byte 20 and only then opens out, so scaling the amount onto the byte
    put small vibratos ~20x too shallow -- amount 0.05 wrote 4 cents where 80
    were wanted, which is inaudible rather than subtle. Every KRZ we wrote had
    effectively no vibrato unless the source asked for nearly all of it.

    Note the curve differs from the filter depth's despite the identical role,
    so neither table can be assumed from the other.
    """
    return krz_cents_to_lfo_pitch_byte(
        max(0.0, min(1.0, amount)) * LFO_PITCH_FULL_CENTS)



def _filter_env_depth_byte(cents: float) -> int:
    """FilterEnv->cutoff depth in CENTS -> K2000 ENV2->FilFreq depth byte.

    **This used to be `round(amount * 127)`**, which treated the byte's
    numerical maximum as "full envelope amount". It is not: byte 127 is
    10800 cents = exactly 9.000 octaves, against the 5.14 an EOS 100% cord
    delivers. And because the byte's display curve is compressed near zero the
    error was not a clean 1.75x -- at amount 0.10 the old code wrote 27 cents
    where 617 were wanted, ~23x too LITTLE. It was a shape error, not a scale
    one, so no single correction factor would have found it.

    With a 1047 Hz base cutoff, byte 127 asks the filter for ~536 kHz; the
    K2000 is far past its own usable range long before that, which is a second
    reason the old mapping could not have been what full amount meant.

    **The full-scale constant is gone entirely as of 2026-08-25.** The model
    carries the depth in cents, so this is now the hardware-measured
    byte<->cents table (k2kremote, 2026-08-21) and nothing else -- the exact
    inverse of what `krz_parser` reads, with no E4XT number in the middle.
    That retires this writer's half of §FENVFULLSCALE: the 41% disagreement
    between the input and output full scales cannot compose here any more,
    because neither one is consulted.

    Signed: the K2000 sweeps the corner down as readily as up, and the table's
    codec mirrors on magnitude.
    """
    return krz_cents_to_depth_byte(cents)


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
#: ---- K2000 FILTER FUNCTION TABLE ----------------------------------------
#: The K2000's own filter functions, and which algorithms carry them.
#: Transcribed from the manual Ch.14 "DSP Functions / Filters" -- the
#: seventeen-entry list plus the per-filter section headings -- and the
#: algorithm chart. Recorded because the writer's algorithm choice depends on
#: all three columns, and until now those lived only in `_k2_filter_plan`'s prose.
#:
#:   name                 poles  slope   resonance                   separation
#:   LOPASS                 1     6 dB   fixed                        no
#:   2POLE LOWPASS          2    12 dB   CONTROLLABLE (F2 RES page)   no
#:   LOPAS2                 2    12 dB   fixed  -6 dB (in the name)   no
#:   LP2RES                 2    12 dB   fixed +12 dB (in the name)   no
#:   4POLE LOPASS W/SEP     4    24 dB   CONTROLLABLE (F2 RES page)   YES (F3 SEP)
#:   LPGATE                 -     -      gated lowpass                no
#:   HIPASS                 1     6 dB   fixed                        no
#:   HIPAS2                 2    12 dB   -                            no
#:   4POLE HIPASS W/SEP     4    24 dB   -                            YES
#:   ALPASS                 1     -      phase only                   no
#:   2POLE ALLPASS          2     -      phase only                   no
#:   NOTCH FILTER           2     -      width controllable           no
#:   NOTCH2                 2     -      FIXED WIDTH (in the name)    no
#:   BANDPASS FILTER        2     -      width controllable           no
#:   BAND2                  2     -      FIXED WIDTH (in the name)    no
#:   DOUBLE NOTCH W/SEP     -     -      -                            YES
#:   TWIN PEAKS BANDPASS    -     -      -                            YES
#:
#: **How to read the resonance column** (the manual's own rule): "Resonance on
#: the K2vx is implemented in one of two ways. On some filters, the resonance is
#: fixed... On other filters, you can control the amount... In the case of these
#: filters, there will always be a SEPARATE CONTROL PAGE for the resonance." So
#: an F2 RES page means controllable and its absence means fixed -- which is
#: exactly why `_k2_filter_plan` returns `_K2_F2_RES` for some filters and not
#: others.
#:
#: **Separation**: the two four-pole filters, the double notch and twin peaks are
#: "actually two filters combined into one DSP function", with a Separation page
#: shifting the second filter's cutoff. At separation 0 a four-pole gives a clean
#: 24 dB/octave.
#:
#: ALGORITHM COVERAGE for the four algorithms this writer emits:
#:   alg  1   4POLE LOPASS W/SEP, 4POLE HIPASS W/SEP, TWIN PEAKS, DOUBLE NOTCH
#:   alg  2   2POLE LOWPASS, BANDPASS FILT, NOTCH FILTER, 2POLE ALLPASS,
#:            PARA BASS / TREBLE / MID        -- **and the PANNER**
#:   alg  5   2POLE LOWPASS, BANDPASS FILT, NOTCH FILTER, NOTCH2, HIPAS2,
#:            2POLE ALLPASS, LPGATE, PARA family
#:   alg 16   LOPASS, HIPASS, ALPASS, PARA BASS / TREBLE
#:
#: **The PANNER exists only in algorithms 2, 13, 24 and 26.** Of those, only
#: algorithm 2 also offers 2POLE LOWPASS with its resonance page -- which is what
#: makes moving a 12 dB source there free rather than a trade, and is the basis
#: of the pan write below.
#:
#: **THE FOUR-POLE IS NOT ONE FILTER — IT IS TWO IN SERIES** (Jan pointed at the
#: description, manual Ch.14). Read in full it says:
#:
#:   "This combines 2POLE LOWPASS and LOPAS2 in one three-stage function. The
#:    parameters on the F1 FRQ page affect the cutoff frequencies of BOTH
#:    filters. The parameters on the F2 RES page affect the resonance of
#:    2POLE LOWPASS. The parameters on the F3 SEP page shift the cutoff
#:    frequency of LOPAS2... If no separation is applied, there's a 24 dB per
#:    octave rolloff above the cutoff frequency."
#:
#: So `4POLE LOPASS W/SEP` = `2POLE LOWPASS` (controllable resonance) followed by
#: `LOPAS2` (fixed −6 dB), sharing one cutoff, with F3 sliding the second one
#: apart. Three pages, three stages, one DSP function.
#:
#:     F1 FRQ   cutoff of BOTH halves
#:     F2 RES   resonance of the 2POLE half only, −12 .. +24 dB
#:     F3 SEP   offset of the LOPAS2 half, ±2 octaves (coarse ±10800 cents)
#:              separation 0 -> a clean 24 dB/octave
#:
#: **THIS IS THE SECOND, INDEPENDENT REASON A 24 dB SOURCE CANNOT CARRY PAN.**
#: The panner lives "in the block before the final AMP" — F3 — and on a four-pole
#: F3 is already the separation page. So the slot is occupied by the filter
#: itself, quite apart from algorithm 1 having no panner in its list. Two
#: unrelated constraints agreeing is why the decision not to move 24 dB sources
#: is a structural fact rather than a preference.
#:
#: It also means a 24 dB lowpass is **structurally impossible** in algorithm 2,
#: which offers a single filter block: there is nowhere for the second half to go.
#:
#: **Transcribed by hand, deliberately.** Parsing the algorithm chart
#: programmatically passed every positive check and still put a PANNER in
#: algorithm 1, which the manual forbids; only a negative check exposed it. The
#: rows above claim the four algorithms this writer uses and not the other 27.
#: ---- end table ----------------------------------------------------------
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
# defaults to byte 0 (very narrow / thin).  The real third-party soundset corpus clusters its
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


def _voice_is_stereo(voice, samples_by_name: dict) -> bool:
    """True when any sample this voice's zones reference is stereo."""
    if not samples_by_name or voice is None:
        return False
    return any(getattr(samples_by_name.get(z.sample_name), 'channels', 1) >= 2
               for z in voice.zones)


def _preset_layers(layers, samples_by_name):
    """Yield `(voice, keymap_id, segments)` for one preset's layers.

    Pulled out of `write_krz` so the VELOCITY-PIVOT SHIFT below is reachable
    without writing a file. It is a per-PRESET quantity, so a test that called
    `_patch_layer` per layer would be re-deriving the shift itself and would
    pass with the shift removed from the writer -- which is exactly what
    happened on the first attempt at these tests.
    """
    # The K2000 attenuates its velocity->volume from velocity 127; an AKAI
    # source rotates about 64, so carrying that swing sits a constant S/2 low.
    # A constant in dB is a level, and repairable as one -- but +S/2 can exceed
    # what Adjust reaches upward (it knees at +12 and clamps at +24), so the
    # whole preset is shifted DOWN by its own largest offset instead. Relative
    # balance inside the preset stays exact; only its overall loudness moves,
    # which is a knob. Jan's design; over 10,933 real programs the shift is
    # 12 dB median, 29.9 max, and every one of them fits.
    fits = {id(v): fit_velocity_line(
                getattr(v, 'velocity_to_volume_db', None),
                getattr(v, 'velocity_to_volume_curve', VELOCITY_CURVE_DB_LINEAR),
                getattr(v, 'velocity_to_volume_pivot', None),
                VEL_VOL_PIVOT_KRZ)
            for v, _ in layers if v is not None}
    shift = max([0.0] + [lv for _s, lv, _r in fits.values()])
    for voice, kid in layers:
        if voice is None:
            segs = [(tag, bytearray(data)) for tag, data in _TPL_LAYER]
            cal = next(d for t, d in segs if t == 0x40)
            cal[7] = cal[8] = 0      # CAL[7,8] is a 2nd keymap slot — keep 0
            cal[11] = (kid >> 8) & 0xFF
            cal[12] = kid & 0xFF
        else:
            _sw, _lv, _r = fits[id(voice)]
            segs = _patch_layer(voice, kid,
                                _voice_is_stereo(voice, samples_by_name),
                                level_offset_db=_lv - shift,
                                vel_swing_db=_sw)
        yield voice, kid, segs


def _patch_layer(voice, keymap_id: int, stereo: bool = False,
                 level_offset_db: float = 0.0, vel_swing_db=None):
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
    # Bit 0x20 of LYR[8] is the layer's stereo flag; the low bits carry other
    # per-layer settings and are left as the template has them.  Corpus-checked
    # 2026-08-01 over 7,608 real layers: set on 86.4% of layers whose keymap is
    # all-stereo and 0.7% of all-mono ones.  (Not 100% — a layer may deliberately
    # play one channel of a stereo sample — so it is a playback choice, not a
    # property of the data.  We set it whenever the source is stereo.)
    if stereo:
        lyr[8] |= 0x20

    cal = seg(0x40)
    # Keymap reference: CAL[11,12] always; CAL[7,8] is a SECOND keymap slot, and
    # the K2000 appears to use one slot per channel.
    #
    #   mono   layer -> CAL[7,8] = 0        (id in CAL[11,12] only)
    #   stereo layer -> id in BOTH slots    (one per channel)
    #
    # Both halves are hardware-grounded and neither is optional:
    #
    # - Zeroing it unconditionally silenced our stereo samples. The K2000 read
    #   only the first Soundfilehead; ST_RON, whose first block is silent,
    #   produced silence rather than its 550 Hz second block (2026-08-02).
    # - Setting it unconditionally made every layer claim two keymaps and
    #   overflowed the K2000 at 4+ layers -> whole program silent (HW-confirmed
    #   2026-06-23 against ROM #183/#193/#194). That result stands; the rule
    #   drawn from it was over-general because it came from mono layers.
    #
    # The corpus agrees with both at once: across 201 real banks CAL[8] is
    # nonzero on 97.6% of layers whose keymap references a stereo sample and on
    # only 4.2% of mono ones.  See docs/RESOLUTION_NOTES.md §KRZSTEREO2.
    if stereo:
        cal[7] = (keymap_id >> 8) & 0xFF
        cal[8] = keymap_id & 0xFF
    else:
        cal[7] = cal[8] = 0
    cal[11] = (keymap_id >> 8) & 0xFF
    cal[12] = keymap_id & 0xFF

    # --- stereo channel routing (HW-confirmed 2026-08-02) ---
    #
    # The second keymap slot above makes the K2000 READ both Soundfileheads;
    # these two bytes decide WHERE each one goes.  Without them both headers
    # play but are summed to both outputs -- audible as a mono image from a
    # correctly-written stereo sample.
    #
    #   HOB 0x52/0x53 byte 2  = 0x70   routes header 1 to the RIGHT output
    #   HOB 0x52 byte 14      = 0x90   pulls header 0 to the LEFT
    #   HOB 0x53 byte 14      = 0x94
    #
    # Measured on C3 with a 440 Hz / 660 Hz stereo sample: left 440 = 0.1052 /
    # 660 = 0.0000, right 440 = 0.0000 / 660 = 0.0886.  Byte 2 alone routes
    # only header 1 (right carries 440 + 660); byte 14 is what completes it.
    # A variant with byte 2 + HOB 0x52 byte 0 = 0x28 and NO byte 14 did not
    # separate, so byte 0 is not part of this and is left alone.
    # See docs/RESOLUTION_NOTES.md §KRZSTEREO2.
    if stereo:
        # A stereo layer pans its two channels hard apart: 0x70 is pan +7
        # (hard right) in byte 2, 0x90/0x94 is pan -7 (hard left) in byte 14.
        # ZoneMapping.pan is deliberately ignored here -- panning a stereo
        # sample would collapse the image it was written to preserve.
        for tag, b14 in ((0x52, 0x90), (0x53, 0x94)):
            hob = seg(tag)
            hob[2] = 0x70
            hob[14] = b14
    else:
        # Mono: pan lives in the HIGH NIBBLE of HOB 0x53 byte 14, as a 4-bit
        # signed value -7 (hard left) .. +7 (hard right); the low nibble is
        # something else and is preserved.  HW-confirmed 2026-08-02 by saving
        # the same program at three pan settings and byte-diffing the .KRZ:
        # centre 0x04, hard left 0x94, hard right 0x74 -- one differing byte
        # out of 252.  Validated over 27k real fields, none outside -7..+7.
        #
        # The law is CONSTANT POWER (measured: hard pan raises the live channel
        # +3.0 dB with 0.00 dB total-power excess), unlike the E4XT's +4.5 dB,
        # so the two formats cannot share a --pan-law setting.
        # Pan is a per-ZONE value in the model but a per-LAYER field here, so
        # take the first zone that asks for one.  (mpc2emu builds one layer per
        # voice, so a layer's zones are a key/velocity split of one part and
        # share a pan in practice.)
        pan = 0.0
        for _z in getattr(voice, 'zones', ()) or ():
            _p = getattr(_z, 'pan', 0.0) or 0.0
            if _p:
                pan = float(_p)
                break
        pan = max(-1.0, min(1.0, pan))
        step = max(-7, min(7, round(pan * 7)))
        hob = seg(0x53)
        hob[14] = ((step & 0x0F) << 4) | (hob[14] & 0x0F)

    # --- velocity -> volume (AMP VelTrk) -----------------------------------
    #
    # ROM #199 leaves `hob_f4[4]` at **35 dB** and we inherited it on every
    # voice ever written. Jan heard it 2026-09-02: an MPC bass whose source
    # says `VelocitySensitivity 0.000000` on every keygroup -- no velocity
    # response at all -- arrived on the K2000 with 35 dB of it. That is not a
    # trim, it is the patch's whole dynamic response, invented.
    #
    # THE BYTE IS THE v1..v127 SWING IN dB, 1:1 (k2kremote, ten settings 0-48,
    # max deviation 0.21 dB), so no table is needed. Signed: 38 of 16,649 real
    # layers are negative, i.e. louder when played soft.
    #
    # PIVOT. The K2000 attenuates DOWNWARD from velocity 127. Sources that
    # share that convention (MPC, KRZ) transfer exactly. An AKAI source
    # rotates about velocity 64, so carrying its swing leaves the K2000 a
    # uniform half-swing below the source at every velocity -- **but that is
    # still strictly better than the inherited 35**, because the swing itself
    # becomes correct and the residual deficit is flat rather than velocity-dependent.
    # Jan's call 2026-09-02: write it. The pivot OFFSET remains open (§KRZVELOFFSET)
    # and is a separate, additive correction to the layer level.
    #
    # `None` means no reader looked, and then the template value stands --
    # unchanged behaviour for formats that state nothing.
    # THE FITTED SWING, not the source's own span. Identical for a dB-linear
    # source (the fit is exact there) and materially different for a curved one
    # -- an MPC keygroup's span is 42 dB where the best line the K2000 can hold
    # is 15, and writing 42 was 14 dB RMS wrong across the played range
    # (§MPCVELSHAPE). The caller fits, because the same line also sets Adjust.
    _vv = vel_swing_db if vel_swing_db is not None else getattr(
        voice, 'velocity_to_volume_db', None)
    if _vv is not None:
        seg(0x53)[4] = max(-128, min(127, int(round(_vv)))) & 0xFF

    # --- LFO -> amplitude (tremolo), with an automatic headroom trim -------
    #
    # WRITING THIS COSTS HEADROOM, WHICH IS WHY THE TRIM IS NOT OPTIONAL.
    # `Depth` is the ONE-SIDED amplitude in dB and the swing is bipolar about
    # the un-modulated level (k2kremote, §KRZF4AMPDEPTH: Depth 12 -> peak
    # +12.08 dB, Depth 24 -> +24.47), so a layer within D dB of full scale
    # clips on every tremolo peak. The layer's static `Adjust` is therefore
    # dropped by the same D, at the 1 dB/unit that field was measured at.
    #
    # Jan's call, 2026-09-01, choosing this over writing it untrimmed: the
    # trade is that a tremolo voice arrives D dB quieter than it otherwise
    # would. That is audible and deliberate -- the alternative is clipping on
    # material that happens to be hot, which is not recoverable by ear or by
    # gain staging afterwards.
    #
    # The trim uses the FULL depth rather than half. The measured half-swing is
    # ~0.96-0.98 x D and the modulation centre sits slightly ABOVE nominal, so
    # the peak is >= D; budgeting D is very slightly conservative and errs the
    # safe way.
    #
    # ONE LFO CAN DRIVE BOTH DESTINATIONS. Routing LFO1 here does not conflict
    # with LFO1 -> pitch above: it is one oscillator with two destinations,
    # exactly as on the AKAI, where a single LFO feeds pitch and loudness
    # through separate amounts.
    _trem1 = abs(getattr(voice, 'lfo1_to_volume', 0.0) or 0.0)
    _trem2 = abs(getattr(voice, 'lfo2_to_volume', 0.0) or 0.0)
    if _trem1 or _trem2:
        _use1 = _trem1 >= _trem2
        _depth_db = (_trem1 if _use1 else _trem2) * LFO_VOLUME_MODEL_FULL_DB
        _d = min(KRZ_F4_AMP_DEPTH_CLAMP,
                 int(round(_depth_db / KRZ_F4_AMP_DEPTH_DB_PER_UNIT)))
        if _d > 0:
            _hob4 = seg(0x53)
            _hob4[KRZ_F4_AMP_SRC1_INDEX] = (KRZ_F4_AMP_SRC_LFO1 if _use1
                                            else KRZ_F4_AMP_SRC_LFO2)
            _hob4[KRZ_F4_AMP_DEPTH_INDEX] = _d
            level_offset_db -= _d * KRZ_F4_AMP_ADJUST_DB_PER_UNIT

    # --- one clamped write of the layer's static level ------------------
    #
    # TWO THINGS MOVE THIS BYTE and they are both dB, so they add rather than
    # compete: the tremolo headroom trim above (subtracting the depth, because
    # the swing is bipolar about nominal) and the velocity-pivot offset passed
    # in by the caller. Writing them separately would have meant two clamps and
    # a read-modify-write between them.
    if level_offset_db:
        _a = seg(0x53)[KRZ_F4_AMP_ADJUST_INDEX]
        _a = _a - 256 if _a > 127 else _a
        seg(0x53)[KRZ_F4_AMP_ADJUST_INDEX] = max(
            -KRZ_F4_AMP_DEPTH_CLAMP,
            min(KRZ_F4_AMP_DEPTH_CLAMP,
                _a + int(round(level_offset_db
                               / KRZ_F4_AMP_ADJUST_DB_PER_UNIT)))) & 0xFF

    # --- amp envelope (always User mode + the source ADSR) ---
    seg(0x20)[1] = 0                                         # AMPENV mode -> User
    _fill_env(seg(0x21), _krz_choke_env(voice.amp_env))

    hob_f1 = seg(0x50)
    hob_f2 = seg(0x51)
    if getattr(voice, 'filter_type', 0):
        algo, ftype_byte, f2_byte, f3_byte, has_res = _k2_filter_plan(voice.filter_type)
        # PAN MODULATION NEEDS A PANNER ALGORITHM (§PANMOD). The panner exists
        # only in 2/13/24/26, and the algorithm is otherwise chosen from the
        # SOURCE's filter type so the slope matches and the cutoff transfers
        # 1:1. Those two requirements compete for one byte.
        #
        # They do not compete for a 2-pole lowpass: algorithm 2's filter slot
        # offers 2POLE LOWPASS with resonance, so such a source keeps everything
        # it had and gains the panner. Only that case is moved.
        #
        # A 6 dB or 24 dB source is NOT moved -- switching it would trade a
        # measured slope match for pan, which is a fidelity decision rather than
        # a free one, and it is not taken here silently.
        #
        # **JAN'S DECISION, 2026-09-06:** "for now, let's go with algo 2 for
        # programs that need a 2Pole LP with a panner". So the narrow rule is
        # the agreed one and not an inference — recorded here so it is not
        # re-litigated by whoever next reads the algorithm choice and wonders
        # why it is conditional.
        #
        # KNOWN GAP: a 6 dB or 24 dB source with pan modulation loses it
        # SILENTLY. That wants a `content_lost` diagnostic naming what was
        # dropped, in the same class as the unrepresentable filter envelope of
        # §AKAIENV2SUSTAIN. Not written yet.
        _pan_depth = (getattr(voice, 'lfo1_to_pan', 0.0) or 0.0)
        _want_pan = bool(_pan_depth) and algo == 5 and ftype_byte == _K2_FILTER_2P_LP
        if _want_pan:
            algo, f3_byte = _K2_ALG_PANNER, _K2_F3_PANNER
        hob_f1[0] = ftype_byte                               # F1 DSP filter type
        hob_f2[0] = f2_byte                                  # F2 block: RES(16)/NONE(61)
        seg(0x52)[0] = f3_byte                               # F3 block: SEP(18)/NONE(60)
        cal[_K2_CAL_ALGORITHM] = algo                        # algorithm number (1/2/5/16)
        if _want_pan:
            # Adjust stays 0 (centred) -- the LFO sweeps about centre, and a
            # static offset is a different parameter the source does not state.
            _f3 = seg(0x52)
            _f3[_K2_PAN_SRC1]  = _K2_CS_LFO1
            _f3[_K2_PAN_DEPTH] = max(-50, min(50, int(round(_pan_depth * 50)))) & 0xFF
            # SPREAD THE TWO WIRES, or none of the above is audible (§K2PANWIRES).
            # Musician's Guide p284: PANNER "converts a single wire at its input
            # into a double wire at its output" and "by itself the PANNER doesn't
            # change the pan position of the sound" -- the OUTPUT page pans each
            # wire, and the manual instructs setting one fully right and the other
            # fully left. Left at the inherited centre the two wires SUM and the
            # panner is silent however hard it is driven.
            #
            # HW-CONFIRMED 2026-09-06 on program 263 (MX9MPC8's Antimatter),
            # by panel edit + re-record, with every panner byte already correct:
            #     wires centred                 balance sd 0.018 dB
            #     wires spread                  balance sd 4.462 dB at 8.97 Hz
            # 8.70 Hz is LFO1's own rate, so the modulation was always present
            # and never reached the outputs. Adjust +50%% moved the image 0.01 dB
            # while centred -- even the STATIC offset is inaudible unspread.
            #
            # This reuses the stereo path's encoding deliberately: KRZ_FORMAT
            # §"Stereo placement is just pan at the extremes" records that byte 2
            # = 0x70 (pan +7, hard right) and byte 14 = 0x90/0x94 (pan -7, hard
            # left) is not a separate routing mechanism but the same wire pans.
            # It runs AFTER the stereo/mono pan block above and overrides the
            # mono per-zone pan, which is correct: a panner layer's placement is
            # the panner's job, and a static zone pan would fight it.
            #
            # Pan MODE is deliberately NOT touched. p64: Mode governs MIDI-pan
            # and key-tracked pan only, and a PANNER layer "will respond to MIDI
            # pan messages even if the Mode parameter is set to a value of Fixed."
            # Measured: flipping Fixed -> +MIDI changed the image by 0.00 dB.
            # OPPOSITE SIGNS -- one wire hard RIGHT, one hard LEFT.
            #
            # The first attempt wrote the stereo path's literals 0x90 and 0x94
            # verbatim. Both of those are pan **-7**: they put BOTH wires hard
            # left, which sums exactly as centre does. Measured on the shipped
            # bank (MX9MPC9 program 208, loaded from the card):
            #     both wires left   L-R +63.66 dB, nothing at the LFO rate
            #     one wire right    L-R  +3.57 dB, sd 4.07 dB, peak 8.70 Hz
            # 8.70 Hz is LFO1's own rate. So the mechanism was right and only
            # these two bytes were wrong -- and the failure LOOKED like the
            # original bug, because both-left and both-centre are both "no
            # spread". The stereo path gets away with 0x90/0x94 because it also
            # writes byte 2, routing the OTHER Soundfilehead; a mono panner
            # layer has only one header, so byte 2 has nothing to route and the
            # spread has to come from the pan nibbles alone.
            #
            # High nibble is the 4-bit signed pan (-7..+7): 0x7. = +7 hard
            # right, 0x9. = -7 hard left. The LOW nibble is unrelated and is
            # preserved (KRZ_FORMAT: "centre 0x04, hard left 0x94, hard right
            # 0x74" -- the 4 is not part of the pan).
            seg(0x52)[14] = (seg(0x52)[14] & 0x0F) | 0x70     # upper wire RIGHT
            seg(0x53)[14] = (seg(0x53)[14] & 0x0F) | 0x90     # lower wire LEFT
        # VELOCITY -> FILTER IS WRITTEN AS THE MACHINE'S OWN VelTrk, and used
        # to be folded into the static cutoff instead (§KRZVELFOLD).
        #
        # The fold was chosen because a VelTrk "sweep from the K2000's 16 Hz
        # floor" would mute softly-played notes that the MPC keeps audible.
        # That premise was wrong about the destination: `hob_f1[4]` is
        # UNIPOLAR FROM THE RESTING CORNER -- the parser records it as
        # (0, VelTrk) -- so soft notes sit at the voice's own cutoff and hard
        # notes at cutoff + depth. That is exactly the MPC semantics Jan
        # checked on hardware (Bass-MS20: VelToFilter 127 -> filter ~open,
        # 0 -> static Cutoff engages), so writing the cord serves the source
        # the fold was designed for AND stops destroying a K2000's own.
        #
        # Cost of the fold, measured over the 32-bank corpus: the cord was
        # lost on 46.7% of zones and its magnitude smeared into the cutoff,
        # which was 49.3% of zones changing where 3.5% was the floor.
        #
        # SIGNED: a K2000 VelTrk goes negative (observed at -4600 ct), where
        # velocity DARKENS. The fold could only ever open -- it took
        # max(0, ...) -- so every darkening routing was silently dropped.
        _vel_ct = getattr(voice, 'velocity_to_filter_cents', 0.0) or 0.0
        _vel_min_ct = getattr(voice, 'velocity_to_filter_min_cents', 0.0) or 0.0
        _hz = getattr(voice, 'filter_cutoff', E4B_CUTOFF_MAX_HZ)
        if _vel_ct and _vel_min_ct:
            # A FLOORED sweep -- the source moves the corner even at velocity
            # zero -- and VelTrk has no floor byte. Fall back to the fold,
            # anchored at the floor so the resting corner is right, and say so.
            # ZERO of 1383 velocity routings in the corpus take this branch;
            # it exists so a source that does specify a floor is not silently
            # flattened.
            print(f"  [krz] velocity->filter floor {_vel_min_ct:.0f} ct folded "
                  f"into the cutoff: VelTrk carries no floor byte")
            _true_floor_hz = _hz * (2.0 ** (_vel_min_ct / 1200.0))
            _hz = _true_floor_hz
            _vel_ct -= _vel_min_ct
            # THE FLOOR CAN ITSELF BE BELOW THE K2000'S OWN 16 Hz FLOOR
            # (§AKAICHOKEFILTER, 2026-08-31, found chasing the reference preset's remaining
            # brightness gap after §AKAICHOKECURVE). `_cutoff_byte_hz` below
            # clamps the WRITTEN byte up to 16 Hz when that happens -- correct,
            # the K2000 genuinely cannot go lower -- but until now nothing
            # compensated `_vel_ct`, which was computed against the
            # UNCLAMPED floor. The result: the resting corner reads brighter
            # than intended (unavoidable, a real hardware limit) AND the top
            # of the sweep ALSO reads brighter than intended by the same
            # amount (avoidable -- the depth is a choice, not a limit).
            # the reference preset's Layer 1 hits this at velocity 0 -- 96 Hz * 2^(-4390 ct)
            # = 7.6 Hz, clamped to 16.35 Hz -- and the un-compensated depth put
            # the top of its sweep at ~2.6 kHz where the source's own ceiling
            # is ~1.2 kHz, a real 1.1-octave error stacked on the unavoidable
            # floor error, for every zone this fold branch ever fires on (0 of
            # 1383 in the original corpus sweep -- untested until the reference preset).
            _min_hz = krz_cutoff_byte_to_hz(_KRZ_CUT_BYTE_MIN)
            if _true_floor_hz < _min_hz:
                _lost_ct = 1200.0 * math.log2(_min_hz / _true_floor_hz)
                _vel_ct = max(0.0, _vel_ct - _lost_ct)
                _hz = _min_hz
        # NOT clamped to E4B_CUTOFF_MAX_HZ. The K2000's cutoff byte reaches
        # 25088 Hz and the E-MU's scale stops at 20 kHz, so trimming here
        # imposed one machine's ceiling on a K2000->K2000 trip: 3.5% of the
        # corpus, `25087.7 -> 19912.1`. `_cutoff_byte_hz` clamps to this
        # machine's own byte range, which is the only ceiling that belongs
        # in a K2000 writer.
        # THE MODEL CARRIES A -3 dB CORNER; THE K2000 BYTE DENOTES f0.
        # Measured 2026-09-02: the 2-pole's -3 dB sits at 1.264 x its label
        # (Q 0.989 -- it is built for unity gain AT the labelled frequency).
        # Writing a source's -3 dB frequency straight into the byte therefore
        # placed the corner ~406 cents too high on 77 % of real layers.
        # The 4-pole's factor runs the other way and is NOT applied -- see
        # KRZ_2POLE_F0_TO_3DB.
        _f0_factor = {_K2_FILTER_2P_LP: KRZ_2POLE_F0_TO_3DB,
                      _K2_FILTER_LP:    KRZ_4POLE_F0_TO_3DB}.get(ftype_byte)
        _f0_hz = _hz / _f0_factor if _f0_factor else _hz
        hob_f1[1] = _cutoff_byte_hz(_f0_hz)
        if _vel_ct:
            hob_f1[4] = krz_cents_to_depth_byte(_vel_ct) & 0xFF
        # KEY TRACKING, seg[3]: a straight signed byte, 2 cents per key per
        # unit. The READER has read this since 2026-08-17 -- its comment there
        # notes the field is set on 15.9% of real filter slots and that E4B
        # conversions had been losing it -- and the writer never wrote it, so
        # anything converted INTO a K2000 lost it instead.
        #
        # Measured over 91 real third-party soundsets 2026-08-24: keytrack was
        # zeroed on **19.2% of round-tripped zones**, always to nothing.
        #
        # Same helper as the reader, in the same direction: the model's amount
        # is a fraction of the E4XT cord's own 0.713 oct/oct, so recover the
        # ratio first and then convert at 100 cents per octave, two cents per
        # unit. (That the model measures this in another machine's cord units
        # at all is filed as its own defect -- it costs a byte of precision
        # here and more elsewhere.)
        _kt_oct = getattr(voice, 'filter_keytrack', 0.0) or 0.0
        # SIGNED. The first version clamped to 0..255 before masking, which
        # threw away every NEGATIVE keytrack -- and the reader sign-extends
        # this byte, so negatives are legal and real material uses them. The
        # corpus barely moved (19.2% to 16.6%) until this was corrected, which
        # is the tell: a fix that only half works is measuring something it
        # only half understands.
        hob_f1[3] = max(-128, min(127,
                                  int(round(_kt_oct * 100.0 / 2.0)))) & 0xFF
        if has_res:                                          # 1-pole has fixed -3 dB res
            # PER-KEY RESONANCE when a fused layer needs it (§KRZRESKEYTRK).
            # `_reson_keytrack_fit` returns a ramp only when it genuinely
            # beats the flat value over the layer's own key span, so the
            # common case still writes a scalar and hob_f2[3] stays 0.
            #
            #   resonance(key) = Adjust + KeyTrk * (key - 60)     HW-measured
            #
            # BYTE: hob_f2[3], signed, **0.02 dB/key per unit**, clamped to
            # +-100 and NOT +-127 -- the panel's rails are +-2.00 dB/key, so a
            # full signed i8 would reach +-2.56 and let us write values the
            # machine cannot produce. Same shape as the keymap VolumeAdjust
            # rail stopping at -63.5 rather than -64.0.
            #
            # The offset was measured by DUMP-diff (k2kremote: only byte 228
            # of the program object moved across four scratch programs
            # differing in nothing else) and mapped onto our own layout two
            # ways that agree: their layer block starts 24 bytes later than
            # ours because `_TPL_GLOBAL` omits the four zero-bodied segments
            # between PGM and FX, so their 228 is our 204 = hob_f2[3]; and
            # independently, their F2 KeyTrk sits exactly one 16-byte segment
            # stride above the already-measured F1 FRQ KeyTrk at hob_f1[3],
            # i.e. the same index in the next segment.
            _ramp = _reson_keytrack_fit(voice)
            if _ramp is not None:
                _adj_db, _slope = _ramp
                hob_f2[1] = _reson_byte(
                    max(0.0, min(1.0, _adj_db / RESONANCE_FULL_DB)))
                hob_f2[3] = max(-_KRZ_RES_KT_CLAMP,
                                min(_KRZ_RES_KT_CLAMP,
                                    int(round(_slope / KRZ_RES_KEYTRK_DB_PER_UNIT)))) & 0xFF
            else:
                hob_f2[1] = _reson_byte(getattr(voice, 'filter_resonance', 0.0))
        elif ftype_byte == _K2_FILTER_2P_BP:                 # bandpass F2 = width
            hob_f2[1] = _K2_BP_DEFAULT_WIDTH
        elif ftype_byte == _K2_FILTER_PARA_MID:              # PARA MID F2-AMP = boost dB
            res = max(0.0, min(1.0, getattr(voice, 'filter_resonance', 0.0)))
            hob_f2[1] = max(0, min(48, round(_K2_PARAMID_GAIN_MIN_DB
                                             + _K2_PARAMID_GAIN_SPAN_DB * res)))
        # --- filter envelope (ENV2) + routing to filter freq ---
        #
        # THE SHAPE IS WRITTEN WHETHER OR NOT THE DEPTH IS, matching what the
        # E4B writer has done since 2026-06-13 and for the same reason: the
        # depth is a separate routing, so an envelope at zero depth is inert
        # rather than absent, and writing the source curve preserves it for the
        # machine's own display and for anyone who turns the depth up later.
        #
        # These two writers disagreed until 2026-08-24 and the KRZ one was the
        # loser: measured over 91 third-party soundsets, the filter envelope
        # changed on **55.8% of round-tripped zones**, and every example
        # inspected had `filter_env_cents == 0` with a real shape behind it --
        # attacks of 4.76 s and 8.0 s discarded because the routing that would
        # have swept them was switched off.
        #
        # The ROUTING still depends on the depth. Writing ENV2 as the source at
        # zero depth would be inventing a modulation the file does not ask for.
        _fenv_ct = getattr(voice, 'filter_env_cents', 0.0)
        _fill_env(seg(0x22), voice.filter_env)
        if _fenv_ct:
            hob_f1[5] = _K2_CS_ENV2                          # source = ENV2
            # Signed since 2026-08-25: `if amt > 0.0` dropped every downward
            # sweep the source asked for, and the K2000 has the sign.
            hob_f1[6] = _filter_env_depth_byte(_fenv_ct) & 0xFF

    # --- LFO1 + vibrato (LFO1 -> Pitch) ---
    lfo = seg(0x14)
    if voice.lfo1_rate is not None:
        lfo[2] = max(0, min(255, round(26 + 10 * voice.lfo1_rate)))
    if voice.lfo1_shape:
        lfo[4] = _LFO_SHAPE.get(voice.lfo1_shape.lower(), 0)  # fallback: Sine
    if getattr(voice, 'lfo1_to_pitch', 0.0) > 0.0:
        cal[21] = _K2_CS_LFO1                                # source = LFO1
        cal[22] = _lfo_pitch_depth_byte(voice.lfo1_to_pitch)  # depth (measured)

    return segs


def _write_program_object(f, preset: Preset, prog_id: int,
                           voice_keymaps: list,
                           samples_by_name: dict = None) -> None:
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

    for voice, kid, segs in _preset_layers(layers, samples_by_name):
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
    top of every band goes silent (the wide-drone preset #204: L1 died at ~C2, L2/L3 at ~C3).

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
    # DO NOT MERGE ACROSS VOICES WHEN EACH VOICE IS ALREADY ITS OWN LADDER.
    #
    # This function was written for octave-slice stacks, where each VOICE is one
    # slice (a single root stretched across the keyboard) and the slices must be
    # gathered across voices to rebuild a multisample. Gathering by root over
    # every voice is correct there.
    #
    # It is wrong once a preset's voices carry different ROLES. After the XPM
    # sparse-layer fix (§XPMLANEMIX) a bass preset arrives as v0 = ten noise
    # zones, v1 = ten pitched zones. Merging by root pulled the noise back into
    # the pitched ladder and assigned it a slot -- so the fix that separated
    # them in the parser was undone here, and hardware still played a noise
    # sample inside a bass multisample (§KRZWRONGSAMPLE, measured +72.75 dB at
    # k84 and a wrong sample at keys 70-74 on the SAME build that fixed the
    # parser).
    #
    # The discriminator is whether a voice is a ladder in its own right: an
    # octave-slice voice has ONE root, a multisample voice has many. So remap
    # per voice when every voice spans its own >= 2 octaves, and only gather
    # across voices when the voices are single-slice.
    def _roots_of(vs):
        out = {}
        for v in vs:
            for z in v.zones:
                s = samples_by_name.get(z.sample_name)
                if s is None:
                    return None
                r = z.root_key if z.root_key else s.root_note
                out.setdefault(r, []).append(
                    (_compute_playback_ceiling(s.sample_rate, r) // 100, z))
        return out

    _per_voice = [_roots_of([v]) for v in voices]
    # ANY voice that is a ladder in its own right, not ALL of them. The first
    # version required all, and a preset with v0/v1 as ten-zone ladders plus a
    # v2 holding ONE catch-all zone failed the test on v2 and fell through to
    # the cross-voice merge -- which is the exact preset this is for.
    # A single-zone voice is not evidence of an octave-slice stack; it is just a
    # voice with one zone, and it should be left alone rather than veto the
    # per-voice path.
    _is_ladder = [rv is not None and len(rv) >= 3 and (max(rv) - min(rv)) >= 24
                  for rv in _per_voice]
    if any(_is_ladder) and all(rv is not None for rv in _per_voice):
        out_voices, applied = [], False
        for v, rv, lad in zip(voices, _per_voice, _is_ladder):
            if lad and any(
                    z.hi_key > rv[(z.root_key if z.root_key
                                   else samples_by_name[z.sample_name].root_note)][0][0] + 3
                    for z in v.zones):
                nv = copy.copy(v)
                nv.zones = []
                lo = 0
                for r in sorted(rv):
                    if lo > NUM_KEYS - 1:
                        break
                    ceil, z = rv[r][0]
                    zz = copy.copy(z)
                    zz.lo_key = lo
                    zz.hi_key = min(NUM_KEYS - 1, max(lo, ceil))
                    nv.zones.append(zz)
                    lo = ceil + 1
                out_voices.append(nv)
                applied = True
            else:
                out_voices.append(v)
        return (out_voices, True) if applied else (voices, False)

    by_root: dict = {}
    overflow = False
    for v in voices:
        for z in v.zones:
            s = samples_by_name.get(z.sample_name)
            if s is None:
                return voices, False
            root = z.root_key if z.root_key else s.root_note
            ceil = _compute_playback_ceiling(s.sample_rate, root) // 100
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
            if lo > NUM_KEYS - 1:
                break   # keyboard already fully covered by earlier slices
            entries = by_root[r]
            ceil, z = entries[li % len(entries)]
            zz = copy.copy(z)
            zz.lo_key = lo
            # Defensive clamp to the hardware's actual 0..127 key range: ceil
            # (a per-root up-pitch ceiling, unrelated to zone.hi_key) is not
            # otherwise bounded, so a legitimate high root_note + low sample
            # rate combination can push it to 128+, overflowing the fixed
            # 128-key keymap-entries buffer in _build_keymap_entries (found
            # via a VinSamLib KRZ->KRZ crash, 2026-07-27: struct.error at
            # offset 640 = 128*KEYMAP_ENTRY_SIZE, i.e. exactly one key past
            # the valid range).
            zz.hi_key = min(NUM_KEYS - 1, max(lo, ceil))
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
    trialled to preserve the wide-drone preset's L/R octave stack, but it flips 7 melodic demo
    patches (F9 piano, JP8/DX7 basses, JR ShortPad/WarmSlow, both brass sections)
    to drum-channel-only — too broad to apply unsupervised.  Kept the original
    3-layer-any-channel cap; faithful all-layer (drum-program) rendering for
    the wide-drone preset & stacked siblings is a deferred opt-in.  See TODO."""
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

def write_krz(bank: Bank, output_path: str,
              faithful_layers: bool = False,
              drum_program: bool = False) -> None:
    """Serialize a Bank to a Kurzweil .KRZ file.

    `faithful_layers` keeps every layer even when that makes the program a
    K2000 DRUM PROGRAM, which sounds only on a drum channel. The default fits
    to three layers instead, because a program that does not sound on the
    channel it is played on is not a subtler rendering of the preset.
    """
    lost_zones: list = []
    fitted: list = []
    print(f"Writing KRZ: {output_path}")
    print(f"  {len(bank.presets)} preset(s), {len(bank.samples)} sample(s)")

    # CR-11c: bake ping-pong (ALTERNATING) loops into PCM as forward loops, the
    # same as write_e4b — the K2000 path previously emitted them as plain forward
    # (audible click every cycle).
    samples = [bake_alternating_loop(s) for s in bank.samples]
    n_baked = sum(1 for s in bank.samples if s.loop_type == LoopType.ALTERNATING)
    if n_baked:
        print(f"  Baked {n_baked} ping-pong loop(s) into PCM as forward loops")

    # Stereo is written as a second Soundfilehead over a second planar PCM
    # block (docs/KRZ_FORMAT.md §3.1).  Until 2026-08-01 this downmixed
    # instead, which was the right stopgap while nothing upstream carried
    # stereo and actively lossy once E4B stereo landed.
    n_stereo = sum(1 for s in samples if getattr(s, 'channels', 1) >= 2)
    if n_stereo:
        print(f"  {n_stereo} stereo sample(s) → two Soundfileheads each "
              f"(planar L then R)")

    # --- Object ID assignment (user range 200-999) ---
    base_id = 200
    # _hash() packs the object id into the low 10 bits (`type << 10 | id`) with
    # no mask, so an id of 1024 carries straight into the TYPE field: a sample
    # (type 38) numbered 1024 hashes to 39936, which reads back as type 39
    # id 0. It is not a sample with a wrong id -- it is not a sample. The
    # failure is silent and total.
    #
    # HW-CONFIRMED 2026-08-10 (K2000R, Jan): the usable id ceiling is 999, NOT
    # the 1023 the hash can encode. A test bank of 796 programs filled up to
    # program 999 and then put every remaining program ON 999, each
    # overwriting the last -- the machine clamps, it does not refuse. So there
    # are two ceilings and the LOWER one binds:
    #
    #   id > 999   the K2000 silently discards (clamps onto 999)
    #   id > 1023  the id carries into the type field and the object is read
    #              back as a different type entirely
    #
    # Ids run from base_id = 200, so 200..999 = 800 objects per type. Capping
    # at 999 keeps us below the 1023 wrap as well, so one guard covers both.
    #
    # The overflow was found by the VinSamLib project (2026-08-09) after
    # hitting the same ceiling on their side; the 999 clamp came out of the
    # hardware session that followed.
    _MAX_OBJ_ID = 999
    if base_id + len(samples) - 1 > _MAX_OBJ_ID:
        raise ValueError(
            f"{len(samples)} samples exceeds what a KRZ bank can address: "
            f"object ids run {base_id}..{_MAX_OBJ_ID} (HW-confirmed), so at "
            f"most {_MAX_OBJ_ID - base_id + 1} samples fit. Split the bank "
            f"(--max-bank-size, or fewer presets per bank).")
    if base_id + len(bank.presets) - 1 > _MAX_OBJ_ID:
        raise ValueError(
            f"{len(bank.presets)} presets exceeds what a KRZ bank can "
            f"address: at most {_MAX_OBJ_ID - base_id + 1} fit.")
    # HW 2026-08-10: a 796-PROGRAM bank HUNG the K2000 on "Please wait ..."
    # and needed a power cycle -- it is not only ids that limit a bank, sheer
    # size does too. The boundary is unmeasured, so this warns rather than
    # refuses.
    #
    # Both thresholds are MEASURED on a K2000R (2026-08-10, disc K2KLIMIT,
    # tests/re_banks/gen_k2000_loadlimit_disk.py), not inferred from the
    # largest bank in somebody's library:
    #
    #   samples  800 loaded, top object on id 999 -- the whole addressable
    #            range -- and quickly. No failure found on this axis at all.
    #   presets  600 loaded (600 programs + 600 keymaps = 1208 objects), but
    #            sat ~20 s on "Please wait ...", against a barely noticeable
    #            pause at 400. The per-program cost climbs.
    #
    # Earlier drafts used 229 / 283 (largest known to load in two libraries)
    # and before that 191, which fired on 4 of our own 6 hardware-verified
    # demo banks. Both would now nag about banks measured to be fine.
    #
    # What actually runs out is PRAM, and how much there is depends on the
    # machine -- see bank_splitter's PRAM section for the model and the
    # measurements. A preset costs 272 + voices*688 bytes; an unexpanded
    # K2000 has ~116K usable, so ~123 one-voice presets fit. The 600-preset
    # bank that loaded here did so on a 760K expansion. The default budget is
    # 110K rather than the full ~116K usable, to leave room for setups,
    # effects and whatever the user already has loaded.
    #
    # RETRACTED 2026-08-10: the 796-preset bank that hung is NOT explained by
    # this. It came from a re-assembler carrying the source's SHARED keymaps
    # -- 796 programs but only 52 keymaps, so 247K, 32% of that machine's
    # 760K. The 746K figure assumed our one-keymap-per-voice shape. PRAM is
    # the right model for what THIS writer emits, which is all this warning
    # claims; what hung that machine is still open.
    #
    # The splitter enforces the budget (--pram); this is a last-line warning
    # for banks that reach the writer another way, and it uses the stock
    # figure because that is what most machines have.
    from writers.bank_splitter import bank_pram_bytes, pram_budget_bytes
    _pram_used = bank_pram_bytes(len(samples), bank.presets)
    _pram_stock = pram_budget_bytes()
    if _pram_used > _pram_stock:
        print(f"  [WARN] this bank needs ~{_pram_used/1024:.0f} K of K2000 "
              f"PRAM ({len(bank.presets)} preset(s), {len(samples)} sample(s)); "
              f"an unexpanded K2000 has ~{_pram_stock/1024:.0f} K and will not "
              f"load it. Objects live in PRAM, not sample RAM -- a preset "
              f"costs ~1 K, a sample ~84 bytes. Split further "
              f"(--max-bank-size), or pass --pram if the target machine has a "
              f"PRAM expansion.")
    _HW_SAFE_PRESETS, _HW_SAFE_SAMPLES = 600, 800
    if len(bank.presets) > _HW_SAFE_PRESETS or len(samples) > _HW_SAFE_SAMPLES:
        print(f"  [WARN] {len(bank.presets)} preset(s) / {len(samples)} sample(s) "
              f"is larger than any bank known to LOAD on a K2000 "
              f"({_HW_SAFE_PRESETS} presets / {_HW_SAFE_SAMPLES} samples). A "
              f"796-preset bank hung the machine on \"Please wait ...\" and "
              f"needed a power cycle; where it actually breaks is unmeasured. "
              f"Consider --max-bank-size to split further.")

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

    # §KRZSHAREDGAIN: what each zone still needs after the per-sample mean.
    # `volumeAdjust` is per SAMPLE and `ZoneMapping.volume` is per ZONE, so a
    # sample used by several zones AT DIFFERENT LEVELS -- across presets, not
    # just within one -- has its gain averaged and every one of those zones
    # comes out wrong. Measured on an AKAI bank whose presets share samples:
    # up to 8.08 dB, always TOO LOUD, because averaging a quiet zone with
    # louder uses can only pull it up.
    #
    # The K2000 keymap carries a per-KEY-RANGE volumeAdjust that is a
    # one-to-one match for our per-zone volume, and -- decisively -- the
    # keymap object is private to its preset, so other presets sharing the
    # sample cannot contaminate it. Writing the RESIDUAL here means the two
    # fields sum to the right level for every zone, and the residual is
    # identically zero wherever a sample is not shared, so banks without this
    # bug are byte-identical to before.
    zone_gain_db = {}
    for _preset in bank.presets:
        for _voice in _preset.voices:
            for _z in _voice.zones:
                _mean = sample_gain_db.get(_z.sample_name, 0.0)
                zone_gain_db[id(_z)] = (_z.volume or 0.0) - _mean

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
    _shared_keymaps: dict = {}       # entry-bytes -> id, only when sharing
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
            _diag(_I, 'KRZ_COVERAGE_REMAP',
                  f"octave-slice stack remapped to {len(base_voices)} coverage "
                  f"multisample layer(s) for the K2000 up-pitch ceiling",
                  subject=preset.name,
                  content_lost=False,       # a restructure: every slice kept
                  detail={'coverage_layers': len(base_voices)},
                  echo=f"  [coverage] '{preset.name}': octave-slice stack → "
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
        elif len(voices) > 3 and not faithful_layers:
            # DEFAULT: fit to three so the program plays on ANY channel.
            #
            # Faithful used to be the only behaviour and it produced silence:
            # a four-layer electric piano is a drum program, and Jan's K2000R
            # refused it on channel 9 with every internal check reading clean
            # (2026-08-24). An averaged filter is a compromise a listener can
            # hear and argue with; a program that does not sound is not a
            # subtler rendering of the preset.
            _was = len(voices)
            voices, _notes = _fit_layers(voices, 3)
            _vel_thinned = 0
            if len(voices) > 3:
                # DISJOINT fusion alone couldn't reach 3 -- what's left
                # overlaps in key range. That is a genuine velocity split
                # (preset 4's 4 same-key-range dynamics layers is the case
                # that motivated this) ONLY when every remaining voice
                # belongs to a single overlapping cluster. Scoped narrowly
                # on purpose: a REAL drum kit that survives fusion as
                # several small overlapping clusters (distinct pads, each
                # already reduced by fusion) is left as a drum program
                # rather than having its per-pad velocity layers thinned
                # unasked -- that is the "too broad... flips melodic
                # patches" mistake `_voices_stacked` already recorded,
                # applied to the wrong axis, and is not attempted here.
                _groups = _group_overlapping(voices)
                if len(_groups) == 1:
                    voices, _vel_thinned = _thin_velocity_voices(voices, 3)
            if len(voices) <= 3:
                # LOUD ON PURPOSE (Jan, 2026-08-24). This is the one place the
                # converter knowingly changes what the source says, and the
                # thing it changes -- a filter setting -- is exactly the kind
                # that gets blamed on something else months later.
                print(f"  [!!] '{preset.name}': APPROXIMATED to fit the K2000's "
                      f"3-layer limit")
                print(f"       {_was} layers → {len(voices)}: "
                      f"{_was - len(voices) - _vel_thinned} disjoint layer(s) FUSED, "
                      f"their filter settings AVERAGED (key-span weighted)"
                      + (f", and {_vel_thinned} velocity layer(s) THINNED "
                         f"(neighbours' velocity ranges widened to cover the gap)"
                         if _vel_thinned else "") + ".")
                for _b, _o, _a, _d in _notes:
                    # Every averaged field, named. The banner used to say
                    # "filter settings" while quietly averaging (or dropping)
                    # more than that.
                    for _i, _fname in enumerate(_VOICE_FIT_FIELDS):
                        if _b[_i] == _o[_i]:
                            continue        # unchanged: not worth a line
                        print(f"       {_fname:22s} {_b[_i]:+.4f} + "
                              f"{_o[_i]:+.4f} → {_a[_i]:+.4f}")
                print(f"       The source authored these separately. "
                      f"Use --krz-faithful to keep all {_was} layers instead "
                      f"-- that makes it a DRUM PROGRAM, playable only on a "
                      f"drum channel.")
                fitted.append((preset.name, _was, len(voices), _notes))
            elif drum_program:
                n = min(len(voices), _MAX_KRZ_LAYERS)
                _diag(_W, 'KRZ_DRUM_PROGRAM',
                      f"{n} split layers written as a K2000 drum program; it "
                      f"sounds ONLY on a drum channel",
                      subject=preset.name,
                      # Nothing is dropped unless the layer clamp bites.  But
                      # the program is SILENT on every normal channel, which is
                      # not "content lost" and is still the worst outcome we
                      # ship -- so it is called out separately rather than
                      # smuggled into the bool. Filter on either.
                      content_lost=len(voices) > _MAX_KRZ_LAYERS,
                      detail={'layers': n, 'requested': True,
                              'layers_clamped': max(0, len(voices) - _MAX_KRZ_LAYERS),
                              'silent_on_normal_channel': True,
                              'cli_flag': '--krz-drum-program'},
                      # REMEDY TEXT CARRIES NO CLI FLAG. VinSamLib renders these
                      # in a GUI that has no command line, and was already
                      # rewriting our flag names into its own control names by
                      # hand. Flags belong in `detail`, where a CLI front end
                      # can pick them up and a GUI can ignore them.
                      remedy='play it on the drum channel, or convert it as a '
                             'normal program to get three layers that play '
                             'anywhere',
                      echo=f"  [layers] '{preset.name}': {n} split layers → DRUM "
                           f"PROGRAM (play on a drum channel; --krz-drum-program "
                           f"was given). Could not fit to 3: the remaining layers "
                           f"form more than one overlapping group.")
                voices = voices[:_MAX_KRZ_LAYERS]
            else:
                # A DRUM PROGRAM IS NEVER PRODUCED BY DEFAULT (Jan, 2026-09-05).
                #
                # This branch used to leave the program at >3 layers and say so,
                # on the grounds that thinning several overlapping groups
                # "unsupervised" was worse than reporting the limit. In practice
                # the automatism is wrong far more often than right: the user
                # gets an instrument that is SILENT on every normal channel, and
                # the only notice is one line in a build log. The ch10 lead
                # program reached three sessions and a hardware measurement
                # campaign that way before anyone read the line (2026-09-05).
                #
                # Converting a drum kit is a thing people know they are doing.
                # So it is now opt-in via --krz-drum-program, and the default
                # produces something that plays.
                _was2 = len(voices)
                voices, _dropped = _thin_velocity_bands(voices, 3)
                _diag(_W, 'KRZ_LAYERS_THINNED',
                      f"{_was2} split layers reduced to {len(voices)} so the "
                      f"program plays on a normal channel",
                      subject=preset.name,
                      # Velocity bands were DROPPED to fit three layers.  This
                      # is real loss and the default path, so it is the code a
                      # consumer will see most often.
                      content_lost=bool(_dropped),
                      detail={'layers_before': _was2, 'layers_after': len(voices),
                              'dropped_velocity_bands': [list(b) for b in _dropped],
                              'cli_flag': '--krz-drum-program'},
                      remedy='converting it as a drum program keeps every '
                             'layer, but that program sounds ONLY on a drum '
                             'channel',
                      echo=f"  [layers] '{preset.name}': {_was2} split layers → "
                           f"{len(voices)} (regular program, plays on any channel).")
                if _dropped:
                    print(f"       DROPPED {len(_dropped)} velocity band(s): "
                          + ", ".join(f"v{a}-{b}" for a, b in _dropped))
                    print(f"       The source switches samples at those "
                          f"velocities and the K2000 keymap has no per-key "
                          f"velocity zones, so each band costs a layer and only "
                          f"three are playable. Use --krz-drum-program to keep "
                          f"all {_was2} — that program sounds ONLY on a drum "
                          f"channel.")
                voices = voices[:_MAX_KRZ_LAYERS]
        elif len(voices) > 3:
            n = min(len(voices), _MAX_KRZ_LAYERS)
            _diag(_W, 'KRZ_DRUM_PROGRAM',
                  f"{n} split layers kept as a K2000 drum program; it sounds "
                  f"ONLY on a drum channel",
                  subject=preset.name,
                  content_lost=len(voices) > _MAX_KRZ_LAYERS,
                  detail={'layers': n, 'requested': True,
                          'layers_clamped': max(0, len(voices) - _MAX_KRZ_LAYERS),
                          'silent_on_normal_channel': True,
                          'via': '--krz-faithful', 'cli_flag': '--krz-faithful'},
                  remedy='play it on the drum channel, or convert without '
                         'faithful mode',
                  echo='')
            print(f"  [layers] '{preset.name}': {n} split layers → DRUM PROGRAM "
                  f"(play on a drum channel; --krz-faithful was given)."
                  + ("" if len(voices) <= _MAX_KRZ_LAYERS
                     else f"  (clamped from {len(voices)} to the K2000 max {_MAX_KRZ_LAYERS})"))
            voices = voices[:_MAX_KRZ_LAYERS]
        vk = []
        for voice in voices:
            kid = None
            if SHARE_IDENTICAL_KEYMAPS:
                # Key on the bytes the keymap would actually contain, not on
                # the voice: two different voices can yield the same keymap.
                entries = _build_keymap_entries(
                    voice, sample_id_map, samples_by_name, 0, zone_gain_db)[0]
                kid = _shared_keymaps.get(entries)
                if kid is None:
                    kid = km_id
                    _shared_keymaps[entries] = kid
                    km_id += 1
            else:
                kid = km_id
                km_id += 1
            vk.append((voice, kid))
            if km_id - 1 > _MAX_OBJ_ID:
                raise ValueError(
                    f"this bank needs more than {_MAX_OBJ_ID - base_id + 1} "
                    f"keymaps (one per voice); KRZ object ids stop at "
                    f"{_MAX_OBJ_ID}. Split the bank.")
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

        # --- Keymap objects (one per voice, or one per distinct keymap) ---
        _written_km = set()
        for pi, preset in enumerate(bank.presets):
            for voice, kid in preset_keymaps[pi]:
                if kid in _written_km:
                    continue            # shared: the object is already on disc
                _written_km.add(kid)
                lost_zones.extend(
                    (preset.name, *z) for z in _write_keymap_object(
                        f, preset.name, voice, kid,
                        sample_id_map, samples_by_name, base_pitch,
                        zone_gain_db))

        # --- Program objects (one layer per voice) ---
        for pi, preset in enumerate(bank.presets):
            pid = base_id + pi
            _write_program_object(f, preset, pid, preset_keymaps[pi],
                                  samples_by_name)
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
            # Our internal format is 16-bit signed little-endian INTERLEAVED;
            # the K2000 expects big-endian, and stereo PLANAR (all of the left
            # channel, then all of the right) — the two Soundfileheads point at
            # the two blocks.  De-interleave first, then byteswap the whole
            # thing in one pass.
            data = _interleaved_to_planar(sample.data) \
                if getattr(sample, 'channels', 1) >= 2 else sample.data
            # array.byteswap flips the bytes inside each 2-byte element in
            # C. This was a per-2-byte Python loop and it dominated the whole
            # conversion: on a 43 MB source the loop cost 3.55 s against
            # 0.09 s here (~39x), for identical output on every buffer of even
            # length -- which, measured over the corpus, is all 1504 of them.
            # krz_parser has always done it this way (`_extract_pcm`); only
            # the write path still had the loop, reintroduced when this block
            # was rewritten for stereo.
            #
            # A ragged final byte is DROPPED, not written. word_offsets above
            # advances by len(data)//2 words, so writing that byte pushed every
            # later sample's declared start one byte out and would have read
            # the rest of the bank byte-shifted. The old loop wrote a 0x00
            # there and desynced identically; dropping it is the fix, not a
            # regression. No corpus sample has an odd length -- 16-bit PCM
            # cannot -- so this path is a guard, not a behaviour change.
            n = len(data) // 2 * 2
            a = array.array('h')
            a.frombytes(memoryview(data)[:n])   # memoryview: no extra copy
            a.byteswap()
            a.tofile(f)                         # tofile: no .tobytes() copy

        total = f.tell()
        print(f"  Written: {output_path} ({total/1024/1024:.2f} MB)")
        # REPEATED AT THE END, deliberately. The per-preset warning above scrolls
        # past behind one line per sample; a bank of forty presets buries it
        # completely. The one thing the converter knowingly approximates should
        # still be on screen when the run finishes.
        if fitted:
            print()
            print(f"  [!!] {len(fitted)} preset(s) had LAYERS FUSED AND FILTER "
                  f"SETTINGS AVERAGED to fit the K2000's 3-layer limit:")
            for _nm, _was, _now, _notes in fitted:
                print(f"       '{_nm}': {_was} → {_now} layers, "
                      f"{len(_notes)} fusion(s)")
            print(f"       This is an APPROXIMATION of what the source "
                  f"authored, not a translation of it.")
            print(f"       --krz-faithful keeps every layer; those presets then "
                  f"become DRUM PROGRAMS and sound only on a drum channel.")
    if lost_zones:
        # PUBLISHED FOR CONSUMERS (VinSamLib priority 2: content silently
        # dropped).  echo='' because the human-readable form below is several
        # lines with a per-reason explanation; the structured record carries
        # the same facts in `detail` so a GUI can render them its own way.
        _diag(_W, 'KRZ_ZONES_DROPPED',
              f"{len(lost_zones)} zone(s) could not be placed and were dropped",
              content_lost=True,        # the name IS the loss
              detail={'count': len(lost_zones),
                      'reasons': sorted({w for _, _, _, _, w in lost_zones}),
                      'zones': [{'preset': pn, 'sample': sn,
                                 'lo_key': lo, 'hi_key': hi, 'why': w}
                                for pn, sn, lo, hi, w in lost_zones[:64]]},
              remedy='those keys are filled from a neighbouring zone, so they '
                     'sound the wrong sample rather than falling silent',
              echo='')
        print(f"  [WARN] {len(lost_zones)} zone(s) could not be placed and were "
              f"dropped:")
        for pname, sname, lo, hi, why in lost_zones[:8]:
            print(f"           '{pname}': '{sname}' keys {lo}-{hi} -- {why}")
        if len(lost_zones) > 8:
            print(f"           ... and {len(lost_zones) - 8} more")
        reasons = {w for _, _, _, _, w in lost_zones}
        if any('below key' in w for w in reasons):
            print(f"         A keymap entry sounds at key entry+"
                  f"{FIRST_MAPPABLE_KEY} with the basePitch of 0 this writer "
                  f"emits, so key {FIRST_MAPPABLE_KEY} is the lowest it can "
                  f"address.")
        if any('ceiling' in w for w in reasons):
            print(f"         The K2000 cannot pitch a sample far above its "
                  f"root; those keys are filled from a neighbouring zone, so "
                  f"they sound the WRONG sample rather than nothing. "
                  f"--max-sample-rate downsamples, which raises the ceiling.")
