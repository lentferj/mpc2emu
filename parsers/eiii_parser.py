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
EIIIX/ESI banks (all three identifiers) pulled out of 17 commercial E4XT
library CD-ROM images (Jan's personal collection), covering all 3 bank
variants: 19,040 presets / 33,614 samples / 250,236 zones, zero parse
failures, spot-checked sample PCM (peak/RMS) and preset/zone structure all
plausible. That is a larger corpus than ConvertWithMoss's own independent
validation (22 CD-ROMs / 3,424 presets) — see TODO.md for how to re-run it.
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
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models.common import Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType, Envelope, hz_to_e4b_cutoff
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
                 extra_samples: Dict[str, SampleData]) -> Optional[Tuple[ZoneMapping, _ZoneExtra]]:
    sample_index = _get_u16(data, offset + ZONE_SAMPLE_INDEX) & ZONE_SAMPLE_INDEX_MASK
    if sample_index == 0:
        return None
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
    resonance = data[offset + ZONE_VCF_Q] & 0x7F
    env_amount = data[offset + ZONE_VCF_ENVELOPE_AMOUNT]
    # Bypass state as written by eiii_writer.py: DEFAULT_CUTOFF, zero Q,
    # zero envelope amount. (Unlike ConvertWithMoss's own Detector, this
    # does not additionally gate on cutoff==0xFF/key-tracking==0 — see
    # eiii_writer.py's _ZONE_TRACKING_NEUTRAL note on why that check is
    # unreliable there.)
    has_filter = not (cutoff == 0xEF and resonance == 0 and env_amount == 0)
    extra.filter_type = 1 if has_filter else 0
    if has_filter:
        extra.filter_cutoff = hz_to_e4b_cutoff(_cutoff_frequency(cutoff))
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


def _parse_layers(data: bytes, preset_offset: int,
                   samples_by_index: Dict[int, SampleData],
                   extra_samples: Dict[str, SampleData]) -> List[VoiceLayer]:
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
                                  samples_by_index, extra_samples)
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
                         extra_samples: Dict[str, SampleData]) -> Optional[Preset]:
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
        voices.extend(_parse_layers(data, offset, samples_by_index, extra_samples))
        link = _get_u16(data, offset + PRESET_LINK)
        idx = (link - 1) if (0 < link <= fmt.max_presets and link - 1 != idx) else None

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
    used_names: set = set()
    for i in range(fmt.max_samples):
        entry = _get_u32(data, fmt.sample_table_offset + i * 4)
        if entry == 0:
            continue
        address = sample_area_start + entry - SAMPLE_ADDRESS_OFFSET
        raw = _parse_sample(data, address, i + 1)
        if raw is None:
            continue
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
    for i in range(fmt.max_presets):
        if not _preset_present(data, fmt, i):
            continue
        offset = _preset_offset(data, fmt, i)
        if offset < 0:
            continue
        link = _get_u16(data, offset + PRESET_LINK)
        if 0 < link <= fmt.max_presets and link - 1 != i:
            linked.add(link - 1)

    # Zones whose ZONE_FLAG_DISABLE_LOOP overrides a looped sample get a
    # synthesized unlooped SampleData (see _parse_zone) collected here.
    extra_samples: Dict[str, SampleData] = {}

    presets: List[Preset] = []
    for i in range(fmt.max_presets):
        if not _preset_present(data, fmt, i) or i in linked:
            continue
        preset = _parse_preset_chain(data, fmt, i, samples_by_index, extra_samples)
        if preset is not None:
            presets.append(preset)

    bank_name = _decode_name(data, BANK_NAME) or Path(path).stem
    samples: List[SampleData] = list(samples_by_index.values()) + list(extra_samples.values())
    return Bank(name=bank_name, presets=presets, samples=samples)
