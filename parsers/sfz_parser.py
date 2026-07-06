# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
#
# This file is part of mpc2emu.
# Independent reimplementation from the public SFZ v1/v2 specification
# (https://sfzformat.com/). No third-party source code used.
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
SFZ v1/v2 Parser
-----------------
SFZ is a plain-text format using sections (<group>, <region>) and opcodes.
Each <region> maps one sample to a key/velocity range.

Structure:
  <group>            optional group defaults
    lokey=0  hikey=127  lovel=0  hivel=127
    ...
  <region>
    sample=path/to/file.wav
    lokey=60  hikey=72  pitch_keycenter=66
    lovel=0   hivel=127
    volume=0  pan=0  tune=0
    loop_mode=loop_continuous  loop_start=0  loop_end=44100
    ampeg_attack=0.001  ampeg_decay=0.3  ampeg_sustain=100  ampeg_release=0.5

References:
  - sfzformat.com (community reference)
  - Cakewalk SFZ specification v1
  - sfzformat.github.io v2 extensions
"""

import re
import os
from pathlib import Path
from typing import Optional, Dict, Any

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType,
    cents_to_filter_env_amount, lfo_pitch_depth_to_amount, hz_to_e4b_cutoff,
    velocity_filter_depth_to_amount, key_track_to_filter_amount,
    cap_voices_by_coverage,
)
from parsers.xpm_parser import load_wav, _safe_name


# ---------------------------------------------------------------------------
# Opcode tokeniser
# ---------------------------------------------------------------------------

def _parse_sfz_opcodes(text: str) -> list[dict]:
    """
    Parse SFZ text into a list of section dicts.
    Each dict has '_type' key ('group', 'region', 'global', 'control', etc.)
    plus all opcode key=value pairs found before the next section header.
    """
    # Strip comments (// and /* */ style)
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    sections = []
    current: Dict[str, Any] = {}

    for token in re.split(r'(<[^>]+>)', text):
        token = token.strip()
        if not token:
            continue

        if token.startswith('<') and token.endswith('>'):
            if current:
                sections.append(current)
            current = {'_type': token[1:-1].lower()}
        else:
            # Parse opcode=value pairs
            # Values can contain spaces (e.g. sample paths with spaces)
            # Use greedy match: opcode=value up to next opcode= or end
            for m in re.finditer(
                r'(\w+)\s*=\s*(.*?)(?=\s+\w+\s*=|$)',
                token, re.DOTALL
            ):
                key = m.group(1).strip()
                val = m.group(2).strip()
                current[key] = val

    if current:
        sections.append(current)

    return sections


# ---------------------------------------------------------------------------
# Helper conversions
# ---------------------------------------------------------------------------

def _note_name_to_midi(note: str) -> int:
    """Accept MIDI note number or note name (c4, f#3, bb2, etc.)."""
    note = str(note).strip()
    try:
        return max(0, min(127, int(note)))
    except ValueError:
        pass
    names = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}
    note_lower = note.lower()
    m = re.match(r'^([a-g])(#|b)?(-?\d+)$', note_lower)
    if m:
        base  = names.get(m.group(1), 0)
        sharp = 1 if m.group(2) == '#' else (-1 if m.group(2) == 'b' else 0)
        octave = int(m.group(3))
        return max(0, min(127, (octave + 1) * 12 + base + sharp))
    return 60


def _loop_mode_to_type(mode: str) -> LoopType:
    mode = mode.lower()
    if mode in ('loop_continuous', 'loop_sustain'):
        return LoopType.FORWARD
    if mode in ('loop_bidi', 'loop_alternate'):
        return LoopType.ALTERNATING
    return LoopType.NO_LOOP


def _sfz_sustain_to_linear(val_str: str) -> float:
    """SFZ ampeg_sustain / fileg_sustain are in percent (0–100)."""
    try:
        return max(0.0, min(1.0, float(val_str) / 100.0))
    except ValueError:
        return 0.8


# SFZ v2 lfoNN_wave code → canonical E4B shape.  ARIA wave table: 0=triangle,
# 1=sine, 2=pulse75, 3=square, 4=pulse25, 5=pulse12.5, 6=saw-up, 7=saw-down.
# v1 LFOs (pitchlfo/fillfo) have no wave opcode and are always sine.
_SFZ_LFO_WAVE = {0: 'triangle', 1: 'sine', 2: 'square', 3: 'square',
                 4: 'square', 5: 'square', 6: 'sawtooth', 7: 'sawtooth'}


def _sfz_lfo_wave(code) -> str:
    if code is None:
        return 'sine'   # v1 LFOs and unspecified v2 default to sine
    try:
        return _SFZ_LFO_WAVE.get(int(float(code)), 'sine')
    except (ValueError, TypeError):
        return 'sine'


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def _sfz_voice_params(merged: dict) -> dict:
    """Extract E4B voice-level parameters (envelope/filter/LFO) from a region's
    merged opcodes.  Returns only the attributes that are actually declared, so
    regions sharing the same group settings get an identical signature and
    collapse into one voice."""
    def _f(k, d=0.0):
        try:
            return float(merged.get(k, d))
        except (ValueError, TypeError):
            return d

    params: dict = {}
    if 'ampeg_attack' in merged:
        params['env_attack']  = _f('ampeg_attack', 0.001)
        params['env_decay']   = _f('ampeg_decay', 0.3)
        params['env_sustain'] = _sfz_sustain_to_linear(merged.get('ampeg_sustain', '80'))
        params['env_release'] = _f('ampeg_release', 0.5)
    if 'cutoff' in merged:
        try:
            params['filter_cutoff'] = hz_to_e4b_cutoff(float(merged['cutoff']))
        except ValueError:
            pass
    if 'fil_keytrack' in merged:
        try:
            params['filter_keytrack'] = key_track_to_filter_amount(
                float(merged['fil_keytrack']) / 100.0)
        except ValueError:
            pass
    if 'fil_veltrack' in merged:
        try:
            params['velocity_to_filter'] = velocity_filter_depth_to_amount(
                float(merged['fil_veltrack']))
        except ValueError:
            pass
    if 'fileg_depth' in merged:
        try:
            params['filter_env_amount']  = cents_to_filter_env_amount(float(merged['fileg_depth']))
            params['filter_env_attack']  = _f('fileg_attack', 0.0)
            params['filter_env_decay']   = _f('fileg_decay', 0.3)
            params['filter_env_sustain'] = _sfz_sustain_to_linear(merged.get('fileg_sustain', '100'))
            params['filter_env_release'] = _f('fileg_release', 0.0)
        except ValueError:
            pass
    # LFOs (v1 pitchlfo_*/fillfo_* or v2 lfo01/lfo02).
    p_depth = _f('pitchlfo_depth') or _f('lfo01_pitch')
    p_freq  = _f('pitchlfo_freq')  or _f('lfo01_freq')
    if p_depth:
        params['lfo1_rate']     = p_freq if p_freq else 5.0
        params['lfo1_shape']    = _sfz_lfo_wave(merged.get('lfo01_wave'))
        params['lfo1_to_pitch'] = lfo_pitch_depth_to_amount(p_depth)
    f_depth = _f('fillfo_depth') or _f('lfo02_cutoff') or _f('lfo01_cutoff')
    f_freq  = _f('fillfo_freq')  or _f('lfo02_freq')   or _f('lfo01_freq')
    if f_depth:
        params['lfo2_rate']      = f_freq if f_freq else 5.0
        params['lfo2_shape']     = _sfz_lfo_wave(merged.get('lfo02_wave'))
        params['lfo2_to_filter'] = cents_to_filter_env_amount(f_depth)
    return params


def _articulation_label(sw_label: Optional[str], sw_last: Optional[str]) -> str:
    """Derive a short articulation name from sw_label ('F2 Pizzicato' → 'Pizzicato')
    or fall back to the keyswitch note name."""
    if sw_label:
        # Drop a leading note token like "F2 " / "C#2 " if present.
        m = re.match(r'^[A-Ga-g][#b]?-?\d+\s+(.*)$', sw_label.strip())
        return (m.group(1) if m else sw_label).strip()
    return (sw_last or 'default').strip()


def parse_sfz(sfz_path: str, wav_dir: Optional[str] = None) -> Bank:
    """
    Parse an SFZ file into a Bank object.

    Args:
        sfz_path:  Path to the .sfz file
        wav_dir:   Override directory for sample search

    Returns:
        Bank with one Preset containing one VoiceLayer per group of regions.
    """
    p = Path(sfz_path).resolve()
    base_dir = Path(wav_dir) if wav_dir else p.parent
    print(f"Parsing SFZ: {p.name}")

    # Lazy fallback index: resolve samples kept in a sibling audio folder a few
    # levels away (common in commercial packs) by basename, built on first miss.
    _audio_index: dict = {}
    _index_built = [False]
    _AUDIO_DIR_NAMES = {'wav', 'wavs', 'audio', 'samples', 'sampler',
                        'aif', 'aiff', 'sounds', 'audiofiles'}

    def _find_indexed(name: str):
        if not _index_built[0]:
            _index_built[0] = True
            anc, ancestors = p.parent, []
            for _ in range(6):
                ancestors.append(anc)
                if anc.parent == anc:
                    break
                anc = anc.parent
            count = 0
            for root in ancestors:
                try:
                    subs = [d for d in root.iterdir()
                            if d.is_dir() and d.name.lower() in _AUDIO_DIR_NAMES]
                except OSError:
                    continue
                for sub in subs:
                    try:
                        for f in sub.rglob('*'):
                            if f.suffix.lower() in ('.wav', '.aif', '.aiff', '.flac', '.ogg'):
                                _audio_index.setdefault(f.name.lower(), str(f))
                                count += 1
                        if count > 80000:
                            break
                    except OSError:
                        pass
                if count > 80000:
                    break
        return _audio_index.get(name.lower())

    text = p.read_text(encoding='utf-8', errors='replace')

    # Handle #include directives (one level deep)
    def _resolve_include(m):
        inc_path = p.parent / m.group(1).strip('"\'')
        if inc_path.exists():
            return inc_path.read_text(encoding='utf-8', errors='replace')
        return ''
    text = re.sub(r'#include\s+(["\'][^"\']+["\'])', _resolve_include, text)

    sections  = _parse_sfz_opcodes(text)
    bank       = Bank(name=_safe_name(p.stem))
    preset_base = _safe_name(p.stem)

    global_defaults: Dict[str, str] = {}
    group_defaults:  Dict[str, str] = {}
    # Keyed by normalised lowercase sample path to avoid name-truncation collisions.
    # Value is SampleData on success, None when the file was not found.
    sample_cache:    Dict[str, Optional[SampleData]] = {}

    # Keyswitch articulations are mutually exclusive on the MPC; the E4XT has no
    # keyswitch, so each articulation (distinct sw_last) becomes its own preset.
    # Regions are collected as units per articulation, then lane-allocated into
    # voices (overlapping regions → parallel voices = stacking).
    from collections import OrderedDict
    units_by_art: "OrderedDict[str, dict]" = OrderedDict()  # art_key -> {label, units}
    cur_art_key   = 'default'
    cur_art_label = 'default'

    # One-time warnings — each key fires at most once per file
    _warned: set = set()

    def _warn(key: str, msg: str) -> None:
        if key not in _warned:
            print(f"  [WARN] {msg}")
            _warned.add(key)

    for section in sections:
        stype = section.get('_type', '')

        if stype == 'global':
            global_defaults.update(
                {k: v for k, v in section.items() if k != '_type'}
            )

        elif stype == 'group':
            group_defaults = {k: v for k, v in section.items() if k != '_type'}

            # Keyswitch articulation: each distinct sw_last is a separate preset.
            sw_last  = group_defaults.get('sw_last')
            sw_label = group_defaults.get('sw_label')
            if sw_last is not None:
                cur_art_key   = sw_last.strip().lower()
                cur_art_label = _articulation_label(sw_label, sw_last)
                _warn('ks', "Key-switch (sw_last) detected; each articulation is "
                      "emitted as a separate preset (keyswitch keys dropped).")
            else:
                cur_art_key, cur_art_label = 'default', 'default'

        elif stype == 'region':
            # Merge: global < group < region
            merged = {**global_defaults, **group_defaults,
                      **{k: v for k, v in section.items() if k != '_type'}}

            # Round-robin: keep only seq_position=1; discard higher positions.
            seq_pos = int(merged.get('seq_position', 1))
            if seq_pos > 1:
                _warn('rr', f"Round-robin (seq_position={seq_pos}) detected; "
                      f"keeping only seq_position=1. Higher positions discarded.")
                continue

            # One-time warnings for features that are parsed but not mapped to E4B.
            if 'gain_cc1' in merged or 'ampeg_attackcc1' in merged:
                _warn('cc1', "CC1 mod-wheel opcodes (gain_cc1, ampeg_attackcc1) "
                      "have no E4B equivalent; expression control is lost.")
            if any(k in merged for k in ('xfin_lovel', 'xfin_hivel',
                                         'xfout_lovel', 'xfout_hivel')):
                _warn('xfade', "Velocity crossfade (xfin_*/xfout_*) has no E4B "
                      "equivalent; replaced by the hard velocity split.")
            if 'eq1_freq' in merged:
                _warn('eq', "EQ opcodes (eq1_*) have no E4B equivalent; "
                      "spectral shaping is lost.")

            sample_rel = merged.get('sample', '')
            if not sample_rel:
                continue

            # Normalise path separators; use lowercase path as the cache key so
            # that samples differing only in case don't multiply-load, and —
            # critically — so that samples sharing the first 16 characters of
            # their filename (which would collapse to the same _safe_name) are
            # still stored as distinct entries with unique display names.
            sample_rel = sample_rel.replace('\\', '/')
            cache_key  = sample_rel.lower()

            if cache_key not in sample_cache:
                # Generate a display name that is unique within this bank.
                base_name     = _safe_name(Path(sample_rel).stem)
                existing_names = {sd.name for sd in bank.samples}
                unique_name    = base_name
                idx = 1
                while unique_name in existing_names:
                    suf = str(idx)
                    unique_name = base_name[:16 - len(suf)] + suf
                    idx += 1

                found = False
                winner = None
                for candidate in (p.parent / sample_rel,
                                  base_dir / sample_rel,
                                  base_dir / Path(sample_rel).name):
                    if candidate.exists():
                        winner = candidate
                        break
                if winner is None:               # fallback: ancestor audio index
                    hit = _find_indexed(Path(sample_rel).name)
                    if hit and Path(hit).exists():
                        winner = Path(hit)
                if winner is not None:
                    sd = load_wav(str(winner), unique_name)
                    if sd:
                        # CR-4: only override the loop that load_wav() read
                        # from the WAV smpl chunk when the SFZ actually
                        # declares it; an absent opcode means "use the
                        # sample's own loop" (SFZ default), not "no loop".
                        if 'loop_mode' in merged:
                            sd.loop_type = _loop_mode_to_type(merged['loop_mode'])
                        if 'loop_start' in merged:
                            sd.loop_start = int(merged['loop_start'])
                        if 'loop_end' in merged:
                            sd.loop_end = int(merged['loop_end'])
                        try:
                            sd.root_note = _note_name_to_midi(
                                merged.get('pitch_keycenter', '60'))
                        except Exception:
                            pass
                        sample_cache[cache_key] = sd
                        bank.samples.append(sd)
                        print(f"  Loaded: {sd.name} ({sd.sample_rate} Hz)")
                        found = True
                if not found:
                    print(f"  [WARN] Sample not found: {sample_rel}")
                    sample_cache[cache_key] = None  # sentinel; skip on next ref

            sd = sample_cache[cache_key]
            if sd is None:
                continue

            # key= is SFZ shorthand for lokey=hikey=pitch_keycenter=
            key_shorthand = merged.get('key')
            lo_key  = _note_name_to_midi(merged.get('lokey',
                                         key_shorthand or '0'))
            hi_key  = _note_name_to_midi(merged.get('hikey',
                                         key_shorthand or '127'))
            lo_vel  = int(merged.get('lovel', 0))
            hi_vel  = int(merged.get('hivel', 127))
            root    = _note_name_to_midi(merged.get('pitch_keycenter',
                                         key_shorthand or '60'))
            volume  = float(merged.get('volume', 0.0))
            pan     = float(merged.get('pan', 0.0)) / 100.0  # SFZ: -100..100
            tune    = float(merged.get('tune', 0.0))         # cents

            zone = ZoneMapping(
                sample_name = sd.name,
                lo_key      = lo_key,
                hi_key      = hi_key,
                lo_vel      = lo_vel,
                hi_vel      = hi_vel,
                root_key    = root,
                fine_tune   = int(tune),
                volume      = volume,
                pan         = pan,
            )
            # Per-region voice params (envelope/filter/LFO).  Regions sharing the
            # same group settings get an identical signature and merge into one
            # voice; overlapping regions split into parallel voices (stacking).
            params = _sfz_voice_params(merged)
            sig = tuple(sorted(
                (k, round(v, 6) if isinstance(v, float) else v) for k, v in params.items()
            ))
            art = units_by_art.setdefault(cur_art_key,
                                          {'label': cur_art_label, 'units': []})
            art['units'].append((sig, params, zone))

    # ---- Build one preset per articulation, lane-allocating overlapping
    #      regions into parallel voices (the E4XT plays one zone per note per
    #      voice, so simultaneously-sounding regions must be separate voices). --
    def _overlaps(a: ZoneMapping, b: ZoneMapping) -> bool:
        return not (a.hi_key < b.lo_key or a.lo_key > b.hi_key
                    or a.hi_vel < b.lo_vel or a.lo_vel > b.hi_vel)

    multi_art = len(units_by_art) > 1
    for art_key, info in units_by_art.items():
        lanes: list = []   # list of [sig, VoiceLayer]
        for sig, params, zone in info['units']:
            placed = False
            for lane_sig, v in lanes:
                if lane_sig == sig and not any(_overlaps(z, zone) for z in v.zones):
                    v.zones.append(zone)
                    placed = True
                    break
            if not placed:
                v = VoiceLayer()
                for k, val in params.items():
                    setattr(v, k, val)
                v.zones.append(zone)
                lanes.append((sig, v))

        if not lanes:
            continue
        if multi_art:
            # Keep the articulation visible (it's the selection key); fit a short
            # instrument prefix in front of it within the 16-char budget.
            label = info['label']
            keep  = max(1, 16 - 1 - len(label))
            pname = f"{preset_base[:keep]}-{label}"
        else:
            pname = preset_base
        preset = Preset(name=_safe_name(pname), program_number=0)
        built = [v for _sig, v in lanes if v.zones]
        capped = cap_voices_by_coverage(built)
        if len(capped) < len(built):
            print(f"  [WARN] {len(built)} simultaneous voices — capped to "
                  f"{len(capped)} (E4XT voice limit); narrowest layers dropped")
        preset.voices = capped
        bank.presets.append(preset)
        print(f"  Preset '{preset.name}': {len(preset.voices)} voice(s), "
              f"{sum(len(v.zones) for v in preset.voices)} region(s)")

    print(f"  Total: {len(bank.presets)} preset(s), {len(bank.samples)} sample(s)")
    return bank
