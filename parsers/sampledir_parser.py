# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

"""
Sample-folder → Bank builder.

Point it at a directory of `.wav` files whose names carry the root note (e.g.
`Piano C3.wav`, `Cello-A#2.wav`, `Pad_60.wav`) and it builds a single playable
preset: each sample is auto-mapped to the keys nearest its root (split at the
midpoints between adjacent roots, key-tracked), with default values for
everything else.  The result feeds any writer (E4B / KRZ / ISO / HDA / floppy).

Root note is taken from the filename note-name (or a trailing MIDI number); if
the name has none, the WAV `smpl` chunk's unity note is used; else C3 (60).
Octave convention defaults to **C3 = 60** (set via `octave_offset`).
"""

import re
from collections import Counter
from pathlib import Path
from typing import Optional

from models.common import Bank, Preset, VoiceLayer, ZoneMapping
from parsers.xpm_parser import (load_wav, _read_smpl_root, _read_aiff_base_note,
                                 NOTE_NAMES, NOTE_ALIASES)

# A note token at a word boundary: letter, optional accidental, octave (maybe -1).
_NOTE_RE = re.compile(r'(?<![A-Za-z0-9])([A-Ga-g])([#sb]?)(-?\d{1,2})(?![0-9A-Za-z])')


def _name_note(stem: str):
    """The filename's last note token as (semitone 0-11, octave), or None."""
    matches = list(_NOTE_RE.finditer(stem))
    if not matches:
        return None
    m = matches[-1]
    acc = m.group(2).lower()
    name = m.group(1).upper() + ('#' if acc in ('#', 's') else 'b' if acc == 'b' else '')
    name = NOTE_ALIASES.get(name, name)
    if name not in NOTE_NAMES:
        return None
    return NOTE_NAMES.index(name), int(m.group(3))


def _name_midi_number(stem: str) -> Optional[int]:
    """A standalone MIDI number 0-127 in the filename, or None.  The lookbehind
    excludes letters so a note's octave digit (the '3' in 'C3') is not taken."""
    nums = re.findall(r'(?<![0-9A-Za-z])(\d{1,3})(?![0-9])', stem)
    for v in (int(n) for n in reversed(nums)):
        if 0 <= v <= 127:
            return v
    return None


def _note_to_midi(note, octave_offset: int) -> int:
    semitone, octave = note
    return max(0, min(127, (octave + octave_offset) * 12 + semitone))


def parse_sample_dir(dir_path: str, wav_dir: Optional[str] = None,
                     octave_offset: Optional[int] = None, **kw) -> Bank:
    """Build a one-preset Bank from a directory of root-note-named WAVs.

    Root per sample, in priority order: WAV `smpl`-chunk unity note (authoritative
    MIDI) → trailing MIDI number in the name → note-name in the name → C3.  The
    note-name octave convention is **auto-detected** (cross-checking name-notes
    against embedded/MIDI roots) unless `octave_offset` is given (2=C3, 1=C4, 0=C5).
    """
    p = Path(dir_path)
    _AUDIO_EXTS = ('.wav', '.aif', '.aiff')
    wavs = sorted(f for f in p.rglob('*') if f.suffix.lower() in _AUDIO_EXTS)
    if not wavs:
        raise ValueError(f"no audio files found under {dir_path}")

    # ── scan: filename note/number + embedded smpl root for every WAV ──────────
    scan = []                                 # (path, root_note, name_note, name_midi)
    for w in wavs:
        try:
            raw = w.read_bytes()
            if w.suffix.lower() in ('.aif', '.aiff'):
                smpl = _read_aiff_base_note(raw)
            else:
                smpl = _read_smpl_root(raw)
        except Exception:
            smpl = None
        scan.append((w, smpl, _name_note(w.stem), _name_midi_number(w.stem)))

    # ── auto-detect the note-name octave convention from anchored samples ──────
    if octave_offset is None:
        votes = Counter()
        for _w, smpl, note, midi in scan:
            ref = smpl if smpl is not None else midi
            if note and ref is not None:
                for off in (2, 1, 0):         # C3 / C4 / C5
                    if _note_to_midi(note, off) == ref:
                        votes[off] += 1
        octave_offset = votes.most_common(1)[0][0] if votes else 2
        conv = {2: 'C3', 1: 'C4', 0: 'C5'}[octave_offset]
        how = f"auto-detected {conv}=60" if votes else "no anchor → assuming C3=60"
        print(f"  Octave convention: {how}")

    bank = Bank(name=p.name[:16] or 'Samples')
    placed = []                               # (root, SampleData)
    used_names = set()
    print(f"  Building multisample from {len(wavs)} audio file(s) in {p.name}/")
    for w, smpl, note, midi in scan:
        sd = load_wav(str(w), w.stem)
        if sd is None:
            print(f"   [SKIP] unreadable WAV: {w.name}")
            continue
        if smpl is not None:
            root = smpl
        elif note is not None:
            root = _note_to_midi(note, octave_offset)
        elif midi is not None:
            root = midi
        else:
            print(f"   [WARN] no root note in '{w.name}' (no name token, no smpl) → C3")
            root = 60
        sd.root_note = root
        name = w.stem[:16]                     # unique sample name (E4B 16-char limit)
        if name in used_names:
            i = 2
            while f"{name[:14]}{i}" in used_names:
                i += 1
            name = f"{name[:14]}{i}"
        used_names.add(name)
        sd.name = name
        bank.samples.append(sd)
        placed.append((root, sd))

    if not placed:
        raise ValueError("no usable samples (all unreadable)")

    placed.sort(key=lambda rs: rs[0])
    roots = [r for r, _ in placed]
    n = len(placed)
    zones = []
    for i, (root, sd) in enumerate(placed):
        lo = 0 if i == 0 else (roots[i - 1] + root) // 2 + 1
        hi = 127 if i == n - 1 else (root + roots[i + 1]) // 2
        zones.append(ZoneMapping(sample_name=sd.name, lo_key=lo, hi_key=hi,
                                 lo_vel=0, hi_vel=127, root_key=root))
        print(f"   {sd.name:18s} root={root:3d}  keys {lo:3d}-{hi:3d}")

    bank.presets = [Preset(name=(p.name[:16] or 'Samples'), voices=[VoiceLayer(zones=zones)])]
    return bank
