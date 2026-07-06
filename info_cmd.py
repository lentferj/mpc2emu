# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
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
Info command — inspect any supported input file without converting.

Prints a structured summary of:
  - File type and format version (where detectable)
  - Number of presets / instruments / programs
  - Per-preset: name, voice/layer count, zone count, key/vel ranges
  - Per-sample: name, sample rate, bit depth, channels, length, loop info
  - Estimated converted bank size
  - Any structural warnings (missing samples, oversized banks, etc.)
"""

import os
import struct
from pathlib import Path
from typing import List, Optional

from models.common import Bank, Preset, SampleData, LoopType


# ── ANSI colour helpers (auto-disable if not a tty) ──────────────────────────

def _use_colour() -> bool:
    import sys
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

_C = _use_colour()
def _bold(s):  return f"\033[1m{s}\033[0m"  if _C else s
def _cyan(s):  return f"\033[36m{s}\033[0m" if _C else s
def _green(s): return f"\033[32m{s}\033[0m" if _C else s
def _yellow(s):return f"\033[33m{s}\033[0m" if _C else s
def _red(s):   return f"\033[31m{s}\033[0m" if _C else s
def _dim(s):   return f"\033[2m{s}\033[0m"  if _C else s


# ── Format sniffers (detect format without full parse) ───────────────────────

def _sniff_format(path: Path) -> str:
    """Return a human-readable format description by peeking at the file."""
    ext = path.suffix.lower()
    try:
        data = path.read_bytes()
    except OSError:
        return ext.upper().lstrip('.')

    if ext == '.sf2':
        if data[:4] == b'RIFF' and data[8:12] == b'sfbk':
            # Read version from INFO chunk if present
            return "SoundFont 2 (RIFF sfbk)"
        return "SoundFont 2 (unrecognised header)"

    if ext == '.gig':
        if data[:4] == b'RIFF' and data[8:12] == b'DLS ':
            return "GigaSampler / GigaStudio (RIFF DLS)"
        return "GIG (unrecognised header)"

    if ext == '.exs':
        magic = struct.unpack_from('<I', data, 0)[0] if len(data) >= 4 else 0
        if magic == 0x01000000:
            return "Logic EXS24 mkII (little-endian / Intel)"
        if magic == 0x00000001:
            return "Logic EXS24 mkII (big-endian / PPC)"
        if magic == 0x00000101:
            return "Logic EXS24 v1.1 (Logic 10.4+, little-endian)"
        return "EXS24 (unrecognised header)"

    if ext == '.sfz':
        return "SFZ v1/v2 (text)"

    if ext == '.talsmpl':
        return "TAL-Sampler preset (XML)"

    if ext == '.xpm':
        return "Akai MPC Keygroup program (XML)"

    if ext == '.krz':
        if data[:6] == b'PRAM\x00\x00':
            return "Kurzweil KRZ (PRAM)"
        return "KRZ (unrecognised header)"

    if ext == '.e4b':
        if data[:4] == b'FORM' and data[8:12] == b'E4B0':
            return "EMU E4B (FORM E4B0)"
        return "E4B (unrecognised header)"

    if ext == '.pgm':
        if data[:16] == b'MPC1000 PGM 1.00':
            return "Akai MPC500/1000/2500 drum program (binary)"
        if data[:2] == b'\x07\x04':
            return "Akai MPC2000/2000XL drum program (binary)"
        if data[:1] == b'\x07':
            return "Akai MPC60 drum program (binary, 12-bit .SND)"
        return "Akai MPC drum program (.pgm, unrecognised magic)"

    if ext == '.set':
        return "Akai MPC60 RAM set"

    if ext == '.img':
        return "Akai MPC60 FAT12 floppy image"

    return ext.upper().lstrip('.')


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_size(n_bytes: int) -> str:
    if n_bytes >= 1024 * 1024:
        return f"{n_bytes / 1024 / 1024:.2f} MB"
    if n_bytes >= 1024:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes} B"


def _fmt_duration(n_frames: int, sample_rate: int) -> str:
    if sample_rate == 0:
        return "?"
    secs = n_frames / sample_rate
    if secs >= 1.0:
        return f"{secs:.2f} s"
    return f"{secs * 1000:.0f} ms"


def _fmt_note(midi: int) -> str:
    names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    return f"{names[midi % 12]}{midi // 12 - 1}"


def _fmt_loop(sd: SampleData) -> str:
    if sd.loop_type == LoopType.NO_LOOP:
        return "no loop"
    n_frames = len(sd.data) // (sd.channels * 2)
    label = {
        LoopType.FORWARD:     "fwd",
        LoopType.ALTERNATING: "bidi",
        LoopType.FORWARD_REL: "fwd-rel",
    }.get(sd.loop_type, str(sd.loop_type))
    return f"{label} [{sd.loop_start}–{sd.loop_end or n_frames}]"


# ── Warning collector ─────────────────────────────────────────────────────────

class _Warnings:
    def __init__(self):
        self._items: List[str] = []

    def add(self, msg: str):
        self._items.append(msg)

    def print_all(self):
        if not self._items:
            return
        print()
        print(_bold(_yellow(f"  ⚠  {len(self._items)} warning(s):")))
        for w in self._items:
            print(_yellow(f"     • {w}"))


# ── Core info printer ─────────────────────────────────────────────────────────

def print_bank_info(bank: Bank, source_path: Path,
                    fmt_desc: str, verbose: bool = False) -> None:
    """Print a structured info summary for a parsed Bank."""
    warn = _Warnings()

    # Compute aggregate stats
    total_sample_bytes = sum(len(s.data) for s in bank.samples)
    total_zones = sum(
        len(v.zones)
        for p in bank.presets
        for v in p.voices
    )
    # Estimated E4B size (rough: sample data + 2 KB overhead per preset)
    est_e4b = total_sample_bytes + len(bank.presets) * 2048 + 512

    sep = "─" * 60

    # ── Header ──
    print()
    print(_bold(_cyan(sep)))
    print(_bold(_cyan(f"  {source_path.name}")))
    print(_bold(_cyan(sep)))
    print(f"  Format:    {fmt_desc}")
    print(f"  Bank name: {bank.name}")
    print(f"  Presets:   {len(bank.presets)}")
    print(f"  Samples:   {len(bank.samples)}")
    print(f"  Zones:     {total_zones}")
    print(f"  PCM data:  {_fmt_size(total_sample_bytes)}")
    print(f"  Est. E4B:  {_fmt_size(est_e4b)}")

    # ── Presets ──
    if bank.presets:
        print()
        print(_bold("  Presets:"))
        for pi, preset in enumerate(bank.presets):
            n_voices = len(preset.voices)
            n_zones  = sum(len(v.zones) for v in preset.voices)
            print(f"    [{pi:02d}] {_bold(preset.name):<20s}  "
                  f"{n_voices} layer(s)  {n_zones} zone(s)  "
                  f"prog {preset.program_number}")
            if verbose:
                for vi, voice in enumerate(preset.voices):
                    # Key range summary across zones
                    if voice.zones:
                        lo = min(z.lo_key  for z in voice.zones)
                        hi = max(z.hi_key  for z in voice.zones)
                        vlo= min(z.lo_vel  for z in voice.zones)
                        vhi= max(z.hi_vel  for z in voice.zones)
                        key_range = f"{_fmt_note(lo)}–{_fmt_note(hi)}"
                        vel_range = f"{vlo}–{vhi}"
                    else:
                        key_range = "—"
                        vel_range = "—"
                    chorus = (f"  chorus {round(voice.chorus_amount * 100)}%"
                              if voice.chorus_amount > 0 else "")
                    print(f"         voice {vi}: keys {key_range}  "
                          f"vel {vel_range}  "
                          f"A{voice.env_attack:.3f} "
                          f"D{voice.env_decay:.2f} "
                          f"S{voice.env_sustain:.2f} "
                          f"R{voice.env_release:.2f}  "
                          f"flt {voice.filter_cutoff}/{voice.filter_resonance}"
                          f"{chorus}")
                    if verbose and len(voice.zones) <= 8:
                        for zone in voice.zones:
                            print(f"           zone  "
                                  f"key {_fmt_note(zone.lo_key)}–{_fmt_note(zone.hi_key)}"
                                  f"  vel {zone.lo_vel}–{zone.hi_vel}"
                                  f"  root {_fmt_note(zone.root_key)}"
                                  f"  → {zone.sample_name}")
                    elif verbose:
                        print(f"           ({len(voice.zones)} zones, use -vv for full list)")

    # ── Samples ──
    if bank.samples:
        print()
        print(_bold("  Samples:"))
        for si, sd in enumerate(bank.samples):
            n_frames  = len(sd.data) // (sd.channels * 2)
            ch_label  = "stereo" if sd.channels == 2 else "mono"
            loop_info = _fmt_loop(sd)
            size_info = _fmt_size(len(sd.data))
            dur_info  = _fmt_duration(n_frames, sd.sample_rate)
            root_str  = _fmt_note(sd.root_note)

            # Warnings
            if sd.sample_rate not in (22050, 44100, 48000, 27500, 32000):
                warn.add(f"Sample '{sd.name}': unusual rate {sd.sample_rate} Hz")
            if sd.loop_type != LoopType.NO_LOOP and sd.loop_end == 0:
                warn.add(f"Sample '{sd.name}': loop enabled but loop_end=0")
            if n_frames < 16:
                warn.add(f"Sample '{sd.name}': very short ({n_frames} frames)")

            print(f"    [{si:02d}] {_bold(sd.name):<20s}  "
                  f"{sd.sample_rate} Hz  {sd.bit_depth}-bit  {ch_label}  "
                  f"{dur_info}  {size_info}  root {root_str}  {loop_info}")

    # ── Warnings ──
    warn.print_all()
    print()


# ── Entry point (called from convert.py --info) ───────────────────────────────

def run_info(input_path: Path, wav_dir: Optional[str],
             extra_kwargs: dict, verbose: bool = False) -> None:
    """
    Parse and display info for all supported files under input_path.
    Does not write any output files.
    """
    # CR-17: shared registry (imported lazily to keep info_cmd import-light).
    # Reads every format convert.py can read, by construction.
    from parsers.registry import PARSERS, INPUT_EXTS

    # Collect files
    if input_path.is_dir():
        files = []
        for ext in INPUT_EXTS:
            files += sorted(input_path.glob(f'**/*{ext}'))
            files += sorted(input_path.glob(f'**/*{ext.upper()}'))
        files = sorted(set(files))
    elif input_path.suffix.lower() in INPUT_EXTS:
        files = [input_path]
    else:
        print(f"No supported input files found at '{input_path}'.")
        return

    if not files:
        print(f"No supported files found in '{input_path}'.")
        return

    print(f"\n{_bold('mpc2emu --info')}  "
          f"{_dim(f'({len(files)} file(s))')}")

    total_presets = 0
    total_samples = 0
    total_bytes   = 0

    for p in files:
        ext    = p.suffix.lower()
        parser = PARSERS.get(ext)
        if not parser:
            continue

        fmt_desc = _sniff_format(p)
        search   = wav_dir or str(p.parent)

        # Suppress parser stdout during info mode by redirecting
        import io, contextlib
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                bank = parser(p, search, **extra_kwargs)
        except Exception as e:
            print(f"\n  {_red('ERROR')} {p.name}: {e}")
            continue

        print_bank_info(bank, p, fmt_desc, verbose=verbose)

        total_presets += len(bank.presets)
        total_samples += len(bank.samples)
        total_bytes   += sum(len(s.data) for s in bank.samples)

    # Grand total if multiple files
    if len(files) > 1:
        print(_bold("─" * 60))
        print(_bold(f"  Total: {len(files)} file(s)  "
                    f"{total_presets} preset(s)  "
                    f"{total_samples} sample(s)  "
                    f"{_fmt_size(total_bytes)} PCM"))
        print()
