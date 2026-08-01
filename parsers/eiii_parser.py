# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# EIII format reverse-engineered from the same sources as writers/eiii_writer.py
# (emu3bm / ConvertWithMoss's independent re-verification — see that file's
# header and docs/EIII_FORMAT.md). This file is the reader/inverse of that
# writer; structural constants and conversion tables are imported from it
# rather than duplicated, so the two can never drift apart (this project's
# own CR-13/CR-17 lesson: duplicated codecs/tables have drifted before).
# No third-party source code copied.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
E-mu EIII Bank Parser
----------------------
Reads .E3X / .ESI / .E3B bank files into the common Bank model. This is the
inverse of writers/eiii_writer.py — see that file and docs/EIII_FORMAT.md
for the exhaustive format documentation.

Primary use case here: round-trip verification of eiii_writer.py's own
output (tests/test_eiii_roundtrip.py). Reading genuine third-party content
is also validated directly: this parser has been run — read-only, no
assertions beyond "doesn't crash and looks sane" — against 1118 real EIII/
EIIIX/ESI bank images (all three identifiers) pulled out of 22 commercial
E4XT library CD-ROM images (Jan's personal collection), covering all 3 bank
variants: 19,040 presets / 33,614 samples / 250,236 zones, zero parse
failures, spot-checked sample PCM (peak/RMS) and preset/zone structure all
plausible. That is a larger corpus than ConvertWithMoss's own independent
validation (22 CD-ROMs / 3,424 presets) — see TODO.md for how to re-run it.

Audited 2026-08-01 by reading the EMU3 filesystem properly (TODO.md "Corpus
scan counted 101 non-banks"): 1017 of those 1118 are banks the discs' own
directories list; the other 101 are deleted/free-space leftovers plus one
OS-file hit. They parse fine — they are real banks — but they are not
library content. So 1118 is the right number for "bank images this parser
handled" and 1017 for "banks on the discs".
None of this is hardware playback confirmation, only structural/PCM
plausibility — the writer side (eiii_writer.py) is the one that still needs
an E4XT to actually load and play a written bank.

Two lossy-import notes, both consequences of mpc2emu's own internal model
rather than anything EIII-specific:
  - EIII stores an envelope/filter/tuning/pan/level per ZONE; mpc2emu's
    VoiceLayer stores the envelope/filter once per VOICE. This parser takes
    the FIRST zone's envelope/filter as representative for the whole voice.
    This is exact for banks eiii_writer.py itself wrote (every zone in a
    voice always shares identical settings there) and a reduction for
    third-party banks with genuine per-zone variation.
  - Per-zone LFO, key-tracking and velocity-to-cutoff are not decoded —
    eiii_writer.py doesn't encode them either (no EIII hardware calibration
    exists yet for mpc2emu's EOS-calibrated equivalents).
"""

import math
import re
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models.common import Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType, Envelope, hz_to_e4b_cutoff, E4B_CUTOFF_MAX_HZ
from writers.eiii_writer import (
    BankFormat, ALL_BANK_FORMATS,
    NAME_LENGTH, PRESET_SIZE, NOTE_ZONE_SIZE, ZONE_SIZE, SAMPLE_HEADER_SIZE,
    NUM_KEYS, KEY_OFFSET, SAMPLE_ADDRESS_OFFSET, UNUSED, LOWEST_KEY, HIGHEST_KEY,
    BANK_NAME,
    PRESET_VELOCITY_PRIMARY_LOW, PRESET_VELOCITY_PRIMARY_HIGH,
    PRESET_VELOCITY_SECONDARY_LOW, PRESET_VELOCITY_SECONDARY_HIGH, PRESET_LINK,
    PRESET_NUM_NOTE_ZONES, PRESET_KEY_MAPPINGS,
    NOTE_ZONE_PRIMARY, NOTE_ZONE_SECONDARY,
    ZONE_ORIGINAL_KEY, ZONE_SAMPLE_INDEX, ZONE_SAMPLE_INDEX_MASK, ZONE_VCA_ENVELOPE,
    ZONE_VCF_CUTOFF, ZONE_VCF_Q, ZONE_VCF_ENVELOPE_AMOUNT, ZONE_VCF_ENVELOPE,
    ZONE_VCA_LEVEL, ZONE_NOTE_TUNING, ZONE_VCA_PAN, ZONE_FLAGS,
    ENVELOPE_ATTACK, ENVELOPE_DECAY, ENVELOPE_SUSTAIN, ENVELOPE_RELEASE,
    SAMPLE_START_LEFT, SAMPLE_END_LEFT, SAMPLE_LOOP_START_LEFT, SAMPLE_LOOP_END_LEFT,
    SAMPLE_RATE, SAMPLE_OPTIONS,
    OPTION_LOOP, OPTION_LOOP_IN_RELEASE, OPTION_CHANNEL_LEFT,
    ZONE_FLAG_NON_TRANSPOSE, ZONE_FLAG_DISABLE_LOOP,
    FULL_LEVEL,
    _ENVELOPE_TIME, _CUTOFF_FREQUENCY, _PANORAMA,
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _get_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from('<H', data, offset)[0]


def _get_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _get_s8(data: bytes, offset: int) -> int:
    return struct.unpack_from('<b', data, offset)[0]


def _decode_name(data: bytes, offset: int) -> str:
    length = min(NAME_LENGTH, len(data) - offset)
    if length <= 0:
        return ''
    chars = []
    for i in range(length):
        c = data[offset + i]
        chars.append(chr(c) if 32 <= c < 127 else ' ')
    return ''.join(chars).rstrip()


def _envelope_time_seconds(value: int) -> float:
    return _ENVELOPE_TIME[max(0, min(len(_ENVELOPE_TIME) - 1, value))]


def _cutoff_frequency(value: int) -> float:
    return _CUTOFF_FREQUENCY[max(0, min(len(_CUTOFF_FREQUENCY) - 1, value))]


def _panning(value: int) -> float:
    return _PANORAMA[max(0, min(len(_PANORAMA) - 1, value))] / 100.0


def detect_format(data: bytes) -> Optional[BankFormat]:
    if len(data) < 16 or data[15] != 0:
        return None
    text = data[0:15].decode('ascii', errors='replace')
    for fmt in ALL_BANK_FORMATS:
        if fmt.identifier == text:
            return fmt
    return None


# ---------------------------------------------------------------------------
# Sample parsing
# ---------------------------------------------------------------------------

class _RawSample:
    __slots__ = ('name', 'data', 'sample_rate', 'has_loop', 'loop_start',
                 'loop_end', 'loop_in_release')


def _parse_sample(data: bytes, address: int, sample_index: int) -> Optional[_RawSample]:
    if address < 0 or address + SAMPLE_HEADER_SIZE > len(data):
        return None
    offset = address

    options = _get_u16(data, offset + SAMPLE_OPTIONS)
    end = _get_u32(data, offset + SAMPLE_END_LEFT)
    num_frames = (end + 2 - SAMPLE_HEADER_SIZE) // 2
    sample_rate = _get_u32(data, offset + SAMPLE_RATE)
    data_size = num_frames * 2
    if num_frames <= 0 or sample_rate <= 0 or offset + SAMPLE_HEADER_SIZE + data_size > len(data):
        return None

    s = _RawSample()
    s.name = _decode_name(data, offset) or f"Sample {sample_index}"
    s.data = bytes(data[offset + SAMPLE_HEADER_SIZE: offset + SAMPLE_HEADER_SIZE + data_size])
    s.sample_rate = sample_rate
    s.has_loop = False
    s.loop_start = s.loop_end = 0
    s.loop_in_release = False

    if options & OPTION_LOOP:
        loop_start = (_get_u32(data, offset + SAMPLE_LOOP_START_LEFT) - SAMPLE_HEADER_SIZE) // 2
        loop_end = (_get_u32(data, offset + SAMPLE_LOOP_END_LEFT) - SAMPLE_HEADER_SIZE) // 2
        if loop_start >= 0 and loop_end > loop_start and loop_start < num_frames:
            s.has_loop = True
            s.loop_start = loop_start
            s.loop_end = min(loop_end, num_frames - 1)
            s.loop_in_release = bool(options & OPTION_LOOP_IN_RELEASE)

    return s


# ---------------------------------------------------------------------------
# Preset / zone parsing
# ---------------------------------------------------------------------------

def _preset_present(data: bytes, fmt: BankFormat, preset_index: int) -> bool:
    table = fmt.preset_table_offset
    return _get_u32(data, table + preset_index * 4) != _get_u32(data, table + (preset_index + 1) * 4)


def _preset_offset(data: bytes, fmt: BankFormat, preset_index: int) -> int:
    address = (fmt.preset_area_offset
               + _get_u32(data, fmt.preset_table_offset + preset_index * 4)
               - fmt.preset_address_bias)
    if address < 0 or address + PRESET_SIZE > len(data):
        return -1
    return address


def _parse_envelope(data: bytes, offset: int) -> Envelope:
    return Envelope(
        attack=_envelope_time_seconds(data[offset + ENVELOPE_ATTACK]),
        decay=_envelope_time_seconds(data[offset + ENVELOPE_DECAY]),
        sustain=max(0.0, min(1.0, data[offset + ENVELOPE_SUSTAIN] / float(FULL_LEVEL))),
        release=_envelope_time_seconds(data[offset + ENVELOPE_RELEASE]),
    )


class _ZoneExtra:
    __slots__ = ('amp_env', 'filter_type', 'filter_cutoff', 'filter_resonance',
                 'filter_env_amount', 'filter_env', 'non_transpose')


def _parse_zone(data: bytes, offset: int, key_lo: int, key_hi: int,
                 samples_by_index: Dict[int, SampleData],
                 extra_samples: Dict[str, SampleData],
                 index_repairs: Dict[int, int]) -> Optional[Tuple[ZoneMapping, _ZoneExtra]]:
    stored_index = _get_u16(data, offset + ZONE_SAMPLE_INDEX) & ZONE_SAMPLE_INDEX_MASK
    if stored_index == 0:
        return None
    # See "Truncated 8-bit zone sample index repair" above: index_repairs
    # remaps a stored index whose high byte was lost in mastering to the
    # sample slot it actually refers to; empty for the overwhelming majority
    # of presets, which keep their stored index unchanged.
    sample_index = index_repairs.get(stored_index, stored_index)
    sample = samples_by_index.get(sample_index)
    if sample is None:
        return None

    zone = ZoneMapping(
        sample_name=sample.name,
        lo_key=key_lo, hi_key=key_hi,
        lo_vel=0, hi_vel=127,
        root_key=data[offset + ZONE_ORIGINAL_KEY] + KEY_OFFSET,
    )
    # 1.5625 cents/LSB (100/64) — exact inverse of the writer's
    # round(fine_tune_cents * 64.0 / 100.0). Rounded to an int, matching
    # e4b_parser.py's identical conversion and ZoneMapping.fine_tune's
    # declared type: krz_writer._build_keymap_entries() packs this
    # straight into a '>h' field, so a float here raised struct.error
    # ("required argument is not an integer") and broke every EIII -> KRZ
    # conversion of a bank with any non-zero zone tuning.
    zone.fine_tune = round(_get_s8(data, offset + ZONE_NOTE_TUNING) * 100.0 / 64.0)
    level = data[offset + ZONE_VCA_LEVEL]
    zone.volume = -96.0 if level <= 0 else 20.0 * math.log10(level / float(FULL_LEVEL))
    zone.pan = _panning(data[offset + ZONE_VCA_PAN])

    flags = data[offset + ZONE_FLAGS]

    extra = _ZoneExtra()
    extra.amp_env = _parse_envelope(data, offset + ZONE_VCA_ENVELOPE)
    extra.non_transpose = bool(flags & ZONE_FLAG_NON_TRANSPOSE)

    cutoff = data[offset + ZONE_VCF_CUTOFF]
    cutoff_hz = _cutoff_frequency(cutoff)
    resonance = data[offset + ZONE_VCF_Q] & 0x7F
    env_amount = data[offset + ZONE_VCF_ENVELOPE_AMOUNT]
    # Bypass state: cutoff at/above the inaudible ceiling (20kHz, matching
    # E4B_CUTOFF_MAX_HZ -- the writer's own DEFAULT_CUTOFF=0xEF is 45213 Hz,
    # comfortably past it, but so is every byte from 0xD5 up per
    # eiii_writer._CUTOFF_FREQUENCY), combined with zero Q and zero envelope
    # amount so a static or animated near-Nyquist resonance sweep is still
    # modeled. Previously gated on cutoff==0xEF exactly, which only matched
    # our own writer's convention -- a real/library-mastered EIII bank using
    # any other high byte as its "filter off" value produced a spurious
    # filter object (a filter that "cannot be heard": ConvertWithMoss #248,
    # same finding). (Unlike ConvertWithMoss's own Detector, this still does
    # not additionally gate on key-tracking==0 — see eiii_writer.py's
    # _ZONE_TRACKING_NEUTRAL note on why that check is unreliable there.)
    has_filter = not (cutoff_hz >= E4B_CUTOFF_MAX_HZ and resonance == 0 and env_amount == 0)
    extra.filter_type = 1 if has_filter else 0
    if has_filter:
        extra.filter_cutoff = hz_to_e4b_cutoff(cutoff_hz)
        extra.filter_resonance = max(0.0, min(1.0, resonance / 127.0))
        extra.filter_env_amount = max(0.0, min(1.0, env_amount / 127.0))
        extra.filter_env = _parse_envelope(data, offset + ZONE_VCF_ENVELOPE)
    else:
        extra.filter_cutoff = 1.0
        extra.filter_resonance = 0.0
        extra.filter_env_amount = 0.0
        extra.filter_env = Envelope(0.0, 0.3, 1.0, 0.0)

    if sample.loop_type != LoopType.NO_LOOP and (flags & ZONE_FLAG_DISABLE_LOOP):
        # This zone opts out of a loop its sample otherwise has. mpc2emu has
        # no per-zone loop override (a zone's loop is entirely its sample's),
        # so this is approximated with a synthesized unlooped SampleData that
        # shares the same PCM — registered in `extra_samples` (keyed by name,
        # deduplicated across zones that make the same request) rather than
        # mutated in place, since other zones may still want the looped
        # original.
        unlooped_name = f"{sample.name} NL{sample_index}"
        if unlooped_name not in extra_samples:
            extra_samples[unlooped_name] = SampleData(
                name=unlooped_name, data=sample.data, sample_rate=sample.sample_rate,
                channels=1, bit_depth=16, loop_type=LoopType.NO_LOOP,
                root_note=sample.root_note)
        zone.sample_name = unlooped_name

    return zone, extra


def _apply_velocity_range(data: bytes, preset_offset: int, layer: int,
                           zones: List[ZoneMapping]) -> None:
    low_field = PRESET_VELOCITY_PRIMARY_LOW if layer == 0 else PRESET_VELOCITY_SECONDARY_LOW
    high_field = PRESET_VELOCITY_PRIMARY_HIGH if layer == 0 else PRESET_VELOCITY_SECONDARY_HIGH
    low = data[preset_offset + low_field]
    high = data[preset_offset + high_field]
    if high == 0 or high > 127 or low > high:
        return
    for z in zones:
        z.lo_vel = max(1, low)
        z.hi_vel = high


# ---------------------------------------------------------------------------
# Truncated 8-bit zone sample index repair
# ---------------------------------------------------------------------------
# Some E-mu library CD-ROM banks (library disc B, a General MIDI sample set, a
# few classic-volume banks) were mastered through an 8-bit tool chain: a
# zone's 16-bit sample index was written with the low byte as the true slot
# modulo 256 and the high byte zero or stale garbage. A preset whose samples
# sit above slot 256 then plays completely unrelated material. This is a
# mastering-tool artifact of specific commercial discs, not a hardware or
# format bug -- real EIII/EIIIX hardware reads the full 16-bit index
# correctly, which is why it never surfaced as a "known issue": the affected
# presets are a small fraction of any given bank and E-mu's library CD-ROMs
# have had no support channel for 30 years.
#
# Run against mpc2emu's own 1118-image real-world corpus (1017 of them
# directory-listed banks; see this module's
# docstring): 4,144 of 251,697 zone->sample references repaired across 771
# presets, 0 parse failures -- a similar scale to ConvertWithMoss's own
# 4,756/821 over their 8-CD-ROM set.
#
# Ported from ConvertWithMoss's Emulator3SampleIndexRepair.java (PR #252,
# GPL-3 -- de.mossgrabers.convertwithmoss.format.emu.emulator3, "Written by
# Jürgen Moßgraber"), which infers the repair per preset from: the note
# names E-mu sample names carry ("OBXStringD2"), the preset name occurring
# in the target sample names ("Oct 3 All" -> "Oct 3 All E4"), and the
# feasibility of each 256-slot "page" against the sample table. A preset
# whose evidence is ambiguous keeps its stored indices -- ported faithfully
# (same scoring thresholds) rather than simplified, since the thresholds are
# what keep this from mis-repairing an already-correct preset.

_NOTE_UPPER_RE = re.compile(r'([A-G])\s?([#bx])?\s?(-?\d)\s*$')
_NOTE_LOWER_RE = re.compile(r'([a-g])([#bx])?(-?\d)$')
_GENERIC_TOKENS = {'loop', 'wave', 'the', 'and', 'link', 'new', 'old', 'big', 'low', 'high'}
_PITCH_CLASSES = {'A': 9, 'B': 11, 'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7}


def _parse_note_name(name: str) -> Optional[Tuple[int, int, bool]]:
    """Parse a trailing note name off a sample name (e.g. 'OBXStringD2',
    'DRhodes F#4 Hard') -> (pitch_class 0-11, octave, has_accidental)."""
    stripped = name.rstrip()
    m = _NOTE_UPPER_RE.search(stripped)
    if not m:
        m = _NOTE_LOWER_RE.search(stripped)
        if not m:
            return None
    pitch_class = _PITCH_CLASSES[m.group(1).upper()]
    accidental = m.group(2)
    if accidental is not None:
        pitch_class = pitch_class - 1 if accidental == 'b' else pitch_class + 1
    return (pitch_class + 12) % 12, int(m.group(3)), accidental is not None


def _note_matches(key: int, note: Tuple[int, int, bool]) -> bool:
    """E-mu names are sloppy (accidental sometimes dropped, octave numbering
    follows both the C3=60 and C4=60 convention), so pitch class must match
    exactly (or one semitone flat when no accidental was written) and the
    octave within roughly one."""
    pitch_class, octave, has_accidental = note
    key_pitch_class = key % 12
    if pitch_class != key_pitch_class and (has_accidental or (pitch_class + 1) % 12 != key_pitch_class):
        return False
    for base in (1, 2):
        if abs(pitch_class + (octave + base) * 12 - key) <= 13:
            return True
    return False


def _normalize_token(text: str) -> str:
    return ''.join(c.lower() for c in text if c.isalnum())


def _preset_tokens(preset_name: str) -> set:
    """The distinctive words of a preset name, used to tie it to its samples
    ('KeyBass Sft' <-> 'SoftKeyBassA0'). Empty when the name is all generic
    or numeric, in which case affinity scoring is skipped entirely."""
    tokens = set()
    for word in preset_name.replace(':', ' ').replace('/', ' ').replace('-', ' ').split(' '):
        token = _normalize_token(word)
        if len(token) >= 3 and token not in _GENERIC_TOKENS and not token.isdigit():
            tokens.add(token)
    return tokens


def _repair_affinity(tokens: set, normalized_target_names: List[str]) -> float:
    """Fraction of target sample names carrying one of the preset name's
    distinctive words. Both the tokens and the normalized sample names are
    precomputed by the callers -- a bank has only a few hundred distinct
    sample names but scores thousands of (preset, candidate) pairs against
    them, so normalizing per call dominated the whole repair pass."""
    if not tokens or not normalized_target_names:
        return 0.0
    matched = 0
    for normalized in normalized_target_names:
        if any(tok in normalized for tok in tokens):
            matched += 1
    return matched / len(normalized_target_names)


def _collect_zone_pairs(data: bytes, preset_offset: int) -> set:
    """Distinct (original_key, stored_sample_index) pairs used anywhere in a
    preset's zone table -- a pair repeated across note zones is one piece
    of evidence, not many."""
    pairs = set()
    if preset_offset + PRESET_SIZE > len(data):
        return pairs
    num_note_zones = data[preset_offset + PRESET_NUM_NOTE_ZONES]
    note_zone_offset = preset_offset + PRESET_SIZE
    zones_offset = note_zone_offset + num_note_zones * NOTE_ZONE_SIZE

    max_zone = -1
    for note_zone_index in range(num_note_zones):
        nz = note_zone_offset + note_zone_index * NOTE_ZONE_SIZE
        if nz + NOTE_ZONE_SIZE > len(data):
            break
        for field in (NOTE_ZONE_PRIMARY, NOTE_ZONE_SECONDARY):
            zone_index = data[nz + field]
            if zone_index != UNUSED:
                max_zone = max(max_zone, zone_index)

    for zone_index in range(max_zone + 1):
        zone = zones_offset + zone_index * ZONE_SIZE
        if zone + ZONE_SIZE > len(data):
            break
        stored = _get_u16(data, zone + ZONE_SAMPLE_INDEX) & ZONE_SAMPLE_INDEX_MASK
        if stored == 0:
            continue
        root = data[zone + ZONE_ORIGINAL_KEY] + KEY_OFFSET
        pairs.add((root, stored))
    return pairs


def _score_repair_candidate(candidate: Tuple[bool, int], roots: List[int], stored: List[int],
                             lows: List[int], normalized_names: Dict[int, str],
                             parsed_notes: Dict[int, Tuple[int, int, bool]],
                             tokens: set) -> Tuple[int, int, int, float]:
    """-> (hits, parseable, distinct_roots_hit, affinity)."""
    as_is, page = candidate
    hits = 0
    parseable = 0
    hit_roots = set()
    target_names = []
    for i in range(len(roots)):
        slot = stored[i] if as_is else lows[i] + page * 256
        if tokens:
            normalized = normalized_names.get(slot)
            if normalized is not None:
                target_names.append(normalized)
        note = parsed_notes.get(slot)
        if note is None:
            continue
        parseable += 1
        if _note_matches(roots[i], note):
            hits += 1
            hit_roots.add(roots[i])
    return hits, parseable, len(hit_roots), _repair_affinity(tokens, target_names)


def _choose_repair_candidate(candidates: List[Tuple[bool, int]],
                              scores: List[Tuple[int, int, int, float]], num_pairs: int) -> int:
    """The stored (as-is) interpretation is the baseline (index 0, present
    only when feasible) and is only replaced by a decisively better page."""
    baseline = scores[0]
    best = 0
    for i in range(1, len(scores)):
        if scores[i][0] > scores[best][0]:
            best = i

    # When every pitch score is weak and the stored names are pitched but all
    # mismatch, a candidate carrying the preset's own name in most zones
    # outranks a lone chance hit.
    if scores[best][0] < 3 and baseline[0] == 0 and baseline[1] >= 2:
        affine = 0
        unique = True
        for i in range(1, len(scores)):
            if scores[i][3] > scores[affine][3]:
                affine, unique = i, True
            elif i != affine and scores[i][3] == scores[affine][3]:
                unique = False
        if scores[affine][3] >= 0.5 and (unique or len(candidates) == 1):
            best = affine

    if best == 0:
        return 0

    hits, parseable, distinct_roots, affinity_best = scores[best]
    baseline_hits, _, _, affinity_base = baseline

    # A baseline whose sample names carry the preset's own name is never overridden.
    if affinity_base > affinity_best:
        return 0

    # Hits must span 3+ distinct root keys -- a single repeated root matching
    # a chromatic ladder by chance is one hit, not many -- unless the preset
    # name itself vouches for the target family.
    decisive = (hits >= 3 and (distinct_roots >= 3 or affinity_best > affinity_base)
                and hits >= baseline_hits + 2
                and hits * 10 >= 6 * max(parseable, 1)
                and hits >= 2 * max(baseline_hits, 1))

    # Tiny presets: a perfect score is decisive only when the stored names
    # are pitched but mismatch -- an unpitched stored target (percussion) may
    # simply be correct and beyond the reach of the pitch test.
    perfect_small = (num_pairs <= 2 and hits == num_pairs and parseable == num_pairs
                     and baseline_hits == 0 and baseline[1] >= 1)

    # The preset name vouching for a candidate whose pitch is unreadable,
    # while the stored names are pitched and all mismatch, is decisive too.
    affinity_decisive = (baseline_hits == 0 and baseline[1] >= 2
                          and affinity_best >= 0.5 and affinity_base == 0)

    return best if (decisive or perfect_small or affinity_decisive) else 0


def _resolve_repair_per_zone(stored: List[int], lows: List[int],
                              sample_names: Dict[int, str], max_page: int) -> Dict[int, int]:
    """No single page interpretation fits every zone of the preset: repair
    zone-by-zone, moving only the indices that don't already resolve."""
    mapping = {}
    for i in range(len(stored)):
        if stored[i] in sample_names:
            continue
        for page in range(max_page + 1):
            slot = lows[i] + page * 256
            if slot in sample_names:
                mapping[stored[i]] = slot
                break
    return mapping


def _resolve_preset_repair(data: bytes, preset_offset: int, sample_names: Dict[int, str],
                            normalized_names: Dict[int, str],
                            parsed_notes: Dict[int, Tuple[int, int, bool]],
                            max_slot: int) -> Dict[int, int]:
    max_page = (max_slot - 1) // 256
    pair_set = _collect_zone_pairs(data, preset_offset)
    if not pair_set:
        return {}
    ordered = sorted(pair_set)
    num_pairs = len(ordered)
    roots  = [p[0] for p in ordered]
    stored = [p[1] for p in ordered]
    lows   = [(s - 1) % 256 + 1 for s in stored]
    as_is_feasible = all(s in sample_names for s in stored)

    # Provable no-op: a bank of <=256 samples (max_page 0) whose every stored
    # index resolves has lows == stored throughout, so the only candidate is
    # the stored interpretation itself. Skips the scoring pass outright for
    # the many small banks in which truncation cannot have happened.
    if as_is_feasible and max_page == 0:
        return {}

    candidates: List[Tuple[bool, int]] = []
    if as_is_feasible:
        candidates.append((True, 0))
    for page in range(max_page + 1):
        feasible = True
        identical = as_is_feasible
        for i in range(num_pairs):
            slot = lows[i] + page * 256
            if slot not in sample_names:
                feasible = False
                break          # infeasible pages are discarded regardless of `identical`
            if slot != stored[i]:
                identical = False
        if feasible and not identical:
            candidates.append((False, page))

    if not candidates:
        return _resolve_repair_per_zone(stored, lows, sample_names, max_page)

    # No page was feasible, so the stored interpretation is unopposed: every
    # branch of _choose_repair_candidate returns it. Skip the scoring pass.
    if len(candidates) == 1 and candidates[0][0]:
        return {}

    tokens = _preset_tokens(_decode_name(data, preset_offset))
    scores = [_score_repair_candidate(c, roots, stored, lows, normalized_names, parsed_notes, tokens)
              for c in candidates]
    chosen = _choose_repair_candidate(candidates, scores, num_pairs)
    winner = candidates[chosen]
    if winner[0]:  # as-is wins -> no repair needed
        return {}
    mapping = {}
    for i in range(num_pairs):
        slot = lows[i] + winner[1] * 256
        if slot != stored[i]:
            mapping[stored[i]] = slot
    return mapping


def _resolve_bank_repairs(data: bytes, preset_offsets: List[int],
                           sample_names: Dict[int, str]) -> Dict[int, Dict[int, int]]:
    """For every preset (by its byte offset) that needs it, a mapping from
    its stored (masked) zone sample index to the resolved slot. Presets
    whose stored indices are kept are absent from the result."""
    repairs: Dict[int, Dict[int, int]] = {}
    if not sample_names:
        return repairs
    max_slot = max(sample_names)
    # Both derived views of the sample names are built once per bank: the
    # scoring pass looks them up thousands of times across (preset, candidate)
    # pairs, and recomputing either per lookup dominated the whole pass.
    parsed_notes = {}
    normalized_names = {}
    for slot, name in sample_names.items():
        note = _parse_note_name(name)
        if note is not None:
            parsed_notes[slot] = note
        normalized_names[slot] = _normalize_token(name)
    for preset_offset in preset_offsets:
        mapping = _resolve_preset_repair(data, preset_offset, sample_names,
                                          normalized_names, parsed_notes, max_slot)
        if mapping:
            repairs[preset_offset] = mapping
    return repairs


def _parse_layers(data: bytes, preset_offset: int,
                   samples_by_index: Dict[int, SampleData],
                   extra_samples: Dict[str, SampleData],
                   index_repairs: Dict[int, int]) -> List[VoiceLayer]:
    num_note_zones = data[preset_offset + PRESET_NUM_NOTE_ZONES]
    if num_note_zones == 0:
        return []
    note_zone_offset = preset_offset + PRESET_SIZE
    zone_offset = note_zone_offset + num_note_zones * NOTE_ZONE_SIZE
    if zone_offset > len(data):
        return []

    layer_results: List[Optional[List[Tuple[ZoneMapping, _ZoneExtra]]]] = [None, None]
    for layer in (0, 1):
        layer_field = NOTE_ZONE_PRIMARY if layer == 0 else NOTE_ZONE_SECONDARY
        found: List[Tuple[ZoneMapping, _ZoneExtra]] = []
        for note_zone_index in range(num_note_zones):
            nz = note_zone_offset + note_zone_index * NOTE_ZONE_SIZE
            if nz + NOTE_ZONE_SIZE > len(data):
                break
            zone_index = data[nz + layer_field]
            if zone_index == UNUSED:
                continue

            key_lo, key_hi = None, None
            for key in range(NUM_KEYS):
                if data[preset_offset + PRESET_KEY_MAPPINGS + key] == note_zone_index:
                    if key_lo is None:
                        key_lo = key
                    key_hi = key
            if key_lo is None:
                continue

            zone_off = zone_offset + zone_index * ZONE_SIZE
            if zone_off + ZONE_SIZE > len(data):
                continue
            result = _parse_zone(data, zone_off, key_lo + KEY_OFFSET, key_hi + KEY_OFFSET,
                                  samples_by_index, extra_samples, index_repairs)
            if result is not None:
                found.append(result)

        if found:
            layer_results[layer] = found

    voices: List[VoiceLayer] = []
    for layer in (0, 1):
        found = layer_results[layer]
        if not found:
            continue
        zones = [z for z, _ in found]
        # Apply this layer's own velocity range whenever it's present and
        # restricted (_apply_velocity_range no-ops on an unrestricted
        # range). ConvertWithMoss's own Detector gates this on BOTH layers
        # being present in the same preset, to guard against stray
        # leftover range bytes on a preset whose secondary layer was never
        # filled in — but that gate also means it would never apply a
        # PRIMARY-only preset's velocity range across a `link` chain, which
        # is exactly the technique this project's own writer (and EIII's
        # documented multi-layer-stacking convention) uses. Applying it
        # unconditionally per layer is correct for that case; the tradeoff
        # is the rarer stray-bytes case ConvertWithMoss's comment describes.
        _apply_velocity_range(data, preset_offset, layer, zones)
        # First zone's amp/filter settings represent the whole voice — see
        # the module docstring's lossy-import note.
        rep = found[0][1]
        voice = VoiceLayer(
            zones=zones,
            amp_env=rep.amp_env,
            filter_env=rep.filter_env,
            filter_type=rep.filter_type,
            filter_cutoff=rep.filter_cutoff,
            filter_resonance=rep.filter_resonance,
            filter_env_amount=rep.filter_env_amount,
            non_transpose=rep.non_transpose,
        )
        voices.append(voice)
    return voices


def _parse_preset_chain(data: bytes, fmt: BankFormat, head_index: int,
                         samples_by_index: Dict[int, SampleData],
                         extra_samples: Dict[str, SampleData],
                         repairs_by_offset: Dict[int, Dict[int, int]]) -> Optional[Preset]:
    voices: List[VoiceLayer] = []
    visited = set()
    preset_name: Optional[str] = None
    idx: Optional[int] = head_index
    while idx is not None and idx not in visited and 0 <= idx < fmt.max_presets:
        visited.add(idx)
        offset = _preset_offset(data, fmt, idx)
        if offset < 0:
            break
        if preset_name is None:
            preset_name = _decode_name(data, offset)
        index_repairs = repairs_by_offset.get(offset, {})
        voices.extend(_parse_layers(data, offset, samples_by_index, extra_samples, index_repairs))
        link = _get_u16(data, offset + PRESET_LINK)
        idx = (link - 1) if (0 < link <= fmt.max_presets and link - 1 != idx) else None
        # A chain ends at the first slot that holds NO preset -- which is what
        # the device does.  Several library CD-ROMs leave the last link of a
        # chain dangling into an empty slot; ConvertWithMoss d94bde27 reports
        # one whose 25-preset percussion chain links both ends to the empty
        # slots 126/127.  An empty slot shares its table address with its
        # successor, so following the link reads whatever lies behind the last
        # preset as note zones -- on some discs garbage referencing impossible
        # sample numbers.
        #
        # Live, and confirmed on the very disc they describe (`library disc P`
        # in the local corpus map): its dangling targets decode to 68 note
        # zones of garbage referencing sample slots 385, 571, 16067, 16091,
        # 16381 and 16356 -- that last one the exact number their doc quotes --
        # in banks holding 3 to 27 samples.  178 out-of-range references in
        # all.  Pre-fix, that cost one drum preset seven phantom voices and
        # fourteen phantom zones (19 voices / 31 zones -> 12 / 17).
        #
        # Milder elsewhere: 10 dangling links across 4 of the other 17 discs,
        # of which two attach a phantom voice -- a percussion preset read
        # 3 voices / 36 zones against the device's 2 / 30, and an FM preset
        # 3 / 3 against 2 / 2.
        #
        # Two measurement traps worth recording, having fallen into both.
        # Walking the chains with an EMPTY sample table makes every dangling
        # link look harmless, because _parse_zone() drops a zone whose index
        # does not resolve before anything counts it.  And that same guard is
        # why that disc never blew up on us: the impossible indices were silently
        # discarded, so the damage that DID land was limited to the handful of
        # garbage indices that happened to fall inside the sample table and
        # therefore resolved -- to real samples that do not belong there.
        # A clean-looking parse was evidence of the guard working, not of the
        # bank being sound.
        if idx is not None and not _preset_present(data, fmt, idx):
            idx = None

    if not voices:
        return None
    return Preset(name=preset_name or '', voices=voices)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_eiii(path: str) -> Bank:
    """Parse an EIII bank file (.e3x/.esi/.e3b, or a bank of unknown
    extension whose first bytes carry an EIII identifier) into a Bank."""
    data = Path(path).read_bytes()
    fmt = detect_format(data)
    if fmt is None:
        raise ValueError(f"Not an EIII bank: {path}")

    if fmt.sample_table_offset + (fmt.max_samples + 1) * 4 > len(data):
        raise ValueError(f"Truncated EIII bank: {path}")

    preset_area_size = _get_u32(data, fmt.preset_table_offset + fmt.max_presets * 4) - fmt.preset_address_bias
    sample_area_start = fmt.preset_area_offset + 1 + preset_area_size

    samples_by_index: Dict[int, SampleData] = {}
    # Raw (pre-dedup-suffix) names by 1-based slot, for the sample-index
    # repair heuristic below -- it pattern-matches against E-mu's own
    # embedded note/preset names, which our `used_names` de-duplication
    # suffixing would corrupt.
    raw_sample_names: Dict[int, str] = {}
    used_names: set = set()
    for i in range(fmt.max_samples):
        entry = _get_u32(data, fmt.sample_table_offset + i * 4)
        if entry == 0:
            continue
        address = sample_area_start + entry - SAMPLE_ADDRESS_OFFSET
        raw = _parse_sample(data, address, i + 1)
        if raw is None:
            continue
        raw_sample_names[i + 1] = raw.name
        name = raw.name
        suffix = 1
        while name in used_names:
            suffix += 1
            name = f"{raw.name[:NAME_LENGTH - len(str(suffix))]}{suffix}"
        used_names.add(name)
        loop_type = LoopType.FORWARD if raw.has_loop else LoopType.NO_LOOP
        samples_by_index[i + 1] = SampleData(
            name=name, data=raw.data, sample_rate=raw.sample_rate, channels=1,
            bit_depth=16, loop_type=loop_type, loop_start=raw.loop_start,
            loop_end=raw.loop_end, root_note=60)

    linked = set()
    preset_offsets: List[int] = []
    for i in range(fmt.max_presets):
        if not _preset_present(data, fmt, i):
            continue
        offset = _preset_offset(data, fmt, i)
        if offset < 0:
            continue
        preset_offsets.append(offset)
        link = _get_u16(data, offset + PRESET_LINK)
        if 0 < link <= fmt.max_presets and link - 1 != i:
            linked.add(link - 1)

    repairs_by_offset = _resolve_bank_repairs(data, preset_offsets, raw_sample_names)
    if repairs_by_offset:
        n_refs = sum(len(m) for m in repairs_by_offset.values())
        print(f"  EIII: repaired {n_refs} truncated zone sample index reference(s) "
              f"across {len(repairs_by_offset)} preset(s)")

    # Zones whose ZONE_FLAG_DISABLE_LOOP overrides a looped sample get a
    # synthesized unlooped SampleData (see _parse_zone) collected here.
    extra_samples: Dict[str, SampleData] = {}

    presets: List[Preset] = []
    for i in range(fmt.max_presets):
        if not _preset_present(data, fmt, i) or i in linked:
            continue
        preset = _parse_preset_chain(data, fmt, i, samples_by_index, extra_samples, repairs_by_offset)
        if preset is not None:
            presets.append(preset)

    bank_name = _decode_name(data, BANK_NAME) or Path(path).stem
    samples: List[SampleData] = list(samples_by_index.values()) + list(extra_samples.values())
    return Bank(name=bank_name, presets=presets, samples=samples)
