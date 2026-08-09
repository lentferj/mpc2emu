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
                                 NOTE_NAMES, NOTE_ALIASES,
                                 _safe_name, _prefers_tail, _unique_sample_name)

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



#: Dynamic markings, quietest first. Only these -- `p` and `f` alone are
#: deliberately included but `m` is not, and nothing shorter is matched,
#: because a bare letter in a drum name would fire constantly.
_DYNAMICS = ('pppp', 'ppp', 'pp', 'p', 'mp', 'mf', 'ff', 'fff', 'ffff', 'f')
_DYN_ORDER = {d: i for i, d in enumerate(
    ('pppp', 'ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff', 'ffff'))}
_VEL_NUM_RE = re.compile(r'(?:^|[-_ ])v(?:el)?[-_ ]?(\d{1,3})(?=$|[-_ .])', re.I)
_VEL_DYN_RE = re.compile(r'(?:^|[-_ ])(' + '|'.join(_DYNAMICS) + r')(?=$|[-_ .])')


def _velocity_rank(stem: str):
    """Order this sample within a velocity stack, or None if it names none.

    Two shapes appear in real folders: a number (`v40`, `vel90`, `V-127`) and
    a dynamic marking (`_pp`, `-ff`). Returns a sortable rank; the caller only
    compares ranks within one root, never across roots, so the two shapes
    never need a common scale.

    Deliberately conservative. A folder of drum one-shots must NOT match --
    the collided-root spread below is right for those, and a false positive
    here would map a whole kit onto one key. Hence the separator requirement
    and no bare single letters other than the real dynamics.
    """
    m = _VEL_NUM_RE.search(stem)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 127:
            return (0, n)
    m = _VEL_DYN_RE.search(stem.lower())
    if m:
        return (0, _DYN_ORDER[m.group(1)])
    return None


def _velocity_bands(n: int):
    """Split 1..127 into `n` contiguous bands, quietest first."""
    edges = [round(127 * i / n) for i in range(n + 1)]
    return [(max(1, edges[i] + 1) if i else 1, edges[i + 1]) for i in range(n)]


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
    # Head or tail, decided once from the whole folder's names -- the same
    # per-program choice the XPM path makes per program.
    name_tail = _prefers_tail(w.stem for w, _s, _n, _m in scan)
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
        # Name via the same three helpers the XPM path uses, rather than a
        # private `stem[:16]` + counter.  Each one fixes a real fault here:
        #
        #  * `_prefers_tail` decides head-vs-tail from THIS folder's own names.
        #    Head-only was backwards for the usual shape of a sample folder --
        #    a per-note export shares the instrument prefix and differs at the
        #    END (`…-036-c1`, `…-084-c6`), so the head keeps the part that
        #    identifies nothing.  Measured over a 5256-folder library: of the
        #    folders with 4+ WAVs the tail wins 1064 to 37, and forced renames
        #    drop from 54031 to 4710.
        #  * `_safe_name` sanitises and counts CHARACTERS.  `stem[:16]` cuts
        #    bytes, so `Bäss Ünïcode C3` lost the `C3` -- the one part naming
        #    the note -- and a literal tab passed straight into the name field.
        #  * `_unique_sample_name` cannot outgrow the field; the old counter
        #    produced a 17-character name once it reached 100.
        sd.name = _unique_sample_name(
            _safe_name(w.stem, tail=name_tail), used_names)
        used_names.add(sd.name)
        bank.samples.append(sd)
        placed.append((root, sd))

    if not placed:
        raise ValueError("no usable samples (all unreadable)")

    placed.sort(key=lambda rs: rs[0])

    # Samples sharing a root must not collide.  The split below puts the
    # boundary between two neighbours at their midpoint, so equal roots give
    # lo = root + 1 and hi = root -- an INVERTED, empty range, and that sample
    # never sounds.  A folder of drum one-shots hits this every time: nothing
    # names a pitch, so every sample lands on the default root and all but the
    # first and last are silently dropped.
    #
    # Spread a collided group onto consecutive keys instead, one sample per
    # key, and move each zone's root WITH it so the sample still plays at its
    # natural pitch rather than transposed.
    # Before spreading, ask whether a collided group is a VELOCITY STACK.
    # The spread below cannot tell "two drums that both defaulted to root 60"
    # from "two velocity layers of C3", because nothing here reads velocity --
    # so four files Piano-C3-v40/v90/E3-v40/v90 became four adjacent keys,
    # C#3 sounded a C3, and the layering was gone. Reported by VinSamLib.
    #
    # A group is a stack only if EVERY member names a velocity and no two name
    # the same one. That is deliberately strict: a drum kit must still spread,
    # and a false positive here would fold a whole kit onto one key.
    vel_zones = []
    if len({r for r, _ in placed}) < len(placed):
        by_root = {}
        for root, sd in placed:
            by_root.setdefault(root, []).append(sd)
        stacked = {}
        for root, group in by_root.items():
            if len(group) < 2:
                continue
            ranks = [_velocity_rank(sd.name) for sd in group]
            if all(r is not None for r in ranks) and len(set(ranks)) == len(ranks):
                stacked[root] = [sd for _r, sd in sorted(zip(ranks, group),
                                                         key=lambda rs: rs[0])]
        if stacked:
            keep = []
            for root, sd in placed:
                if root in stacked and sd is not stacked[root][0]:
                    continue                     # folded into the stack below
                keep.append((root, sd))
            n_layers = sum(len(g) for g in stacked.values())
            print(f"   [INFO] {n_layers} sample(s) across {len(stacked)} root(s) "
                  f"name a velocity — layered instead of spread onto new keys")
            placed = keep
            vel_zones = stacked

    if len({r for r, _ in placed}) < len(placed):
        spread, nxt = [], None
        for root, sd in placed:
            key = root if nxt is None or root > nxt else nxt
            spread.append((min(127, key), sd))
            nxt = min(127, key) + 1
        moved = sum(1 for (a, _), (b, _) in zip(placed, spread) if a != b)
        print(f"   [INFO] {moved} sample(s) shared a root note — spread onto "
              f"consecutive keys so none is lost")
        placed = spread

    roots = [r for r, _ in placed]
    n = len(placed)
    zones = []
    for i, (root, sd) in enumerate(placed):
        lo = 0 if i == 0 else (roots[i - 1] + root) // 2 + 1
        hi = 127 if i == n - 1 else (root + roots[i + 1]) // 2
        # fine_tune must be carried onto the ZONE: every writer reads
        # ZoneMapping.fine_tune, never SampleData.fine_tune, so a WAV `smpl`
        # chunk's MIDIPitchFraction (read by load_wav) was silently dropped
        # one function after being parsed.
        stack = vel_zones.get(root) if vel_zones else None
        if stack:
            for (v_lo, v_hi), layer in zip(_velocity_bands(len(stack)), stack):
                zones.append(ZoneMapping(sample_name=layer.name, lo_key=lo,
                                         hi_key=hi, lo_vel=v_lo, hi_vel=v_hi,
                                         root_key=root,
                                         fine_tune=layer.fine_tune))
                print(f"   {layer.name:18s} root={root:3d}  keys {lo:3d}-{hi:3d}"
                      f"  vel {v_lo:3d}-{v_hi:3d}")
            continue
        zones.append(ZoneMapping(sample_name=sd.name, lo_key=lo, hi_key=hi,
                                 lo_vel=0, hi_vel=127, root_key=root,
                                 fine_tune=sd.fine_tune))
        print(f"   {sd.name:18s} root={root:3d}  keys {lo:3d}-{hi:3d}")

    bank.presets = [Preset(name=(p.name[:16] or 'Samples'), voices=[VoiceLayer(zones=zones)])]
    return bank
