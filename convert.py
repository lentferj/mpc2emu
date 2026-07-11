#!/usr/bin/env python3
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
mpc2emu — Multi-format Sampler Converter
=========================================
INPUT:   .e4b  .xpm  .pgm  .set  .img  .talsmpl  .sfz  .sf2  .exs  .gig
OUTPUT:  e4b   krz   talsmpl

Usage:
  python convert.py <input> [options]
  python convert.py <input> --info [--verbose]
  python convert.py --long-help                 # full README as a manual

Options:
  --info               Inspect input file(s) without converting
  --verbose            Show per-zone detail with --info
  --format FORMAT      Output: e4b | krz | talsmpl  (default: e4b)
  --output-dir DIR     Output directory  (default: current directory)
  --bank-size SIZE     Max bank size, e.g. 64MB / 65536K / 32 (bare = MB).
    --max-bank-size      (alias)  Default 32 MB; E4XT max 128 MB, K2000 max 64 MB.
  --max-preset-size SIZE  Cap each single preset/program (e.g. 8192K) so no one
                       preset fills a whole bank; over-cap presets are thinned
                       like an over-bank preset.  Default: no per-preset cap.
  --bank-name NAME     Base name for output banks  (default: EMU_BANK)
  --bank-start N       Number the output bank files B.NNN-NAME… starting at N,
                       so they can be copied straight onto an existing E4XT
                       volume (no --iso needed).  e.g. --bank-start 100
  --overwrite          Overwrite existing output files without prompting
                       (default: prompt before clobbering any existing file)
  --wav-dir DIR        Extra directory for WAV sample search
  --from-samples       Treat the input dir as a folder of WAVs (root note in the
                       filename) → one auto-built multisample preset (also auto-
                       detected for a WAV-only directory).
  --middle-c {auto,C3,C4,C5}  Octave naming for filename root notes: which C =
                       MIDI 60 (default auto — detect from embedded WAV roots).
  --iso                Build a ZuluSCSI CD image (e4b → EMU3, krz → K2000 FAT16)
  --hda                Build a ZuluSCSI SCSI hard disk image (.hda). e4b → E4XT
                       EMU-fs/FAT disk; krz → K2000 FAT16 disk (HW-confirmed:
                       loads from a ZuluSCSI HDx device).
  --hda-size MB        HDA image size in MB. e4b default: auto (smallest 128 MB
                       step that fits; max 14336). krz default: content + ~50%
                       headroom to save onto (FAT16 max ~2047).
  --hda-fs FS          E4B HDA filesystem: fat (EOS 4.7+, default, needs mtools)
                       | emu (native EMU-fs, all EOS versions). Ignored for krz.
  --add-to IMAGE       Append the bank(s) to an existing image in place, no
                       rebuild / no emu3fs.  e4b → a .hda (FAT or EMU-fs); krz →
                       a K2000 FAT16 CD (.iso) or hard disk (.hda), into BANKS/.
  --folder NAME        With --add-to: target folder on the image (created if
                       absent; default: root / Default Folder).
  --on-duplicate {prompt,add-new,skip,overwrite}
                       With --add-to, when a bank name already exists.
  --floppy [KB]        Write each KRZ bank to a DOS FAT12 floppy image (.img)
                       for a Gotek/FlashFloppy on the K2000R  [krz only;
                       default 1440 = 1.44 MB].
  --resample PROFILE   Vintage resampling: emulator2 | emax1
  --no-bandpass        Skip bandpass coloring with --resample
  --resample-keep-gain Keep the gain-staged "hot" level from --resample instead
                       of restoring each sample's original level.
  --max-sample-rate HZ Clean-downsample any sample above HZ down to HZ.  Buys
                       K2000 up-pitch headroom + shrinks banks.  Defaults to
                       24000 Hz for --format krz; pass 0 to disable.  No e4b
                       default.
  --reduce-key-zones PCT       Remove PCT% of per-voice key-zone samples,
                               spreading survivors to fill the gaps (0-100)
  --reduce-velocity-layers PCT Remove PCT% of per-preset velocity layers,
                               spreading survivors to fill the gaps (0-100;
                               independent of --reduce-key-zones)
  --auto-fit           When a single preset is too big for one bank (or over
                       --max-preset-size), auto-apply the least-lossy fitting
                       reduction instead of failing (for batch/non-interactive
                       runs; interactively you are prompted with sized options).
  --lfo-sync-bpm BPM   Reference tempo for reproducing tempo-synced MPC LFOs as
                       a fixed rate (default 120).  See docs/lfo_sync_rates.md.
  --max-presets N      Max presets from SF2/GIG  (default: 64)
  --jobs N             Parallel workers for resampling  (default: cpu_count-1)

When a single preset won't fit its bank, mpc2emu (in an interactive shell)
prints sized suggestions — drop velocity layers / thin key zones / downsample —
and applies your choice; a batch run needs --auto-fit or it exits non-zero.

E4B (E4XT) output: filter type/cutoff/Q, the 6-stage amp + filter envelopes,
chorus, LFO routing and forward/ping-pong loops are mapped from the source (RE'd
against EOS 4.x hardware).  Full byte reference: docs/E4B_FORMAT.md.

KRZ (K2000) output: filter type, cutoff (semitones) + resonance, amp + filter
envelopes and LFO1 vibrato are mapped onto the K2000 #199 template.  A program
with more than 3 UNIQUE (split) layers becomes a K2000 "drum program" — PLAY IT
ON A DRUM CHANNEL; stacked/unison layers are thinned to 3 (any channel).  Each
preset prints a [layers] note.  Full byte reference: docs/KRZ_FORMAT.md.

Examples:
  python convert.py Piano.sf2 --info
  python convert.py DrumKit.sfz --format e4b --hda
  python convert.py /mpc/programs/ --max-bank-size 32MB --iso
  python convert.py Orchestra.gig --format e4b --hda --hda-size 200
  python convert.py Pad.xpm --format krz --floppy --auto-fit
  python convert.py Big.xpm --format krz --max-preset-size 8192K --auto-fit --iso
  python convert.py /sfz/ --reduce-key-zones 30 --reduce-velocity-layers 50 --iso
"""

import sys
import re
import math
import argparse
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from parsers.registry        import PARSERS, INPUT_EXTS   # CR-17: shared table
from parsers.talsmpl_parser  import write_talsmpl
from writers.e4b_writer      import write_e4b
from writers.krz_writer      import write_krz
from writers.iso_builder     import build_iso, build_iso_9660
from writers.hda_builder     import build_hda_fat, build_hda_emu, auto_hda_size_mb
from writers.bank_splitter   import split_into_banks, print_split_summary
from processors.resampler    import resample_bank, resample_to_rate, PROFILES
from processors.zone_reducer import reduce_bank
from info_cmd                import run_info
from models.common           import Bank


def collect_input_files(input_path: Path) -> List[Path]:
    if input_path.is_dir():
        files = []
        for ext in INPUT_EXTS:
            files += sorted(input_path.glob(f'**/*{ext}'))
            files += sorted(input_path.glob(f'**/*{ext.upper()}'))
        return sorted(set(files))
    elif input_path.suffix.lower() in INPUT_EXTS:
        return [input_path]
    return []


def _confirm_overwrite(paths: List[str], overwrite: bool) -> bool:
    """Return True if it's OK to (over)write `paths`.

    Skips silently when nothing exists or --overwrite was given; otherwise lists
    the clashing files and prompts.  Refuses in a non-interactive shell (so batch
    runs never hang) — pass --overwrite there instead."""
    existing = [p for p in paths if Path(p).exists()]
    if not existing or overwrite:
        return True
    print(f"\n  {len(existing)} output file(s) already exist:")
    for p in existing:
        print(f"    {p}")
    if not sys.stdin.isatty():
        print("  Refusing to overwrite in non-interactive mode — pass --overwrite.")
        return False
    try:
        return input("  Overwrite? [y/N] ").strip().lower() in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        print()
        return False


_HW_LABEL = {'e4b': 'E4XT', 'krz': 'K2000'}

_SIZE_UNITS = {'': 1024 ** 2, 'K': 1024, 'KB': 1024, 'M': 1024 ** 2,
               'MB': 1024 ** 2, 'G': 1024 ** 3, 'GB': 1024 ** 3}


def _parse_size_bytes(s: str) -> int:
    """Parse a human size like '8192K', '64MB', '1.5G' or a bare '32' (=MB, to
    match --bank-size's unit) into bytes."""
    m = re.fullmatch(r'\s*([0-9]*\.?[0-9]+)\s*([KMG]B?)?\s*', str(s).upper())
    if not m:
        raise argparse.ArgumentTypeError(
            f"invalid size {s!r} — use e.g. 8192K, 64MB, 1.5G, or a bare number (MB)")
    return int(float(m.group(1)) * _SIZE_UNITS[m.group(2) or ''])


def _size_mb_type(s: str) -> float:
    """argparse type: a size string → megabytes (float). Bare number = MB."""
    return _parse_size_bytes(s) / (1024 ** 2)


def _size_bytes_type(s: str) -> int:
    """argparse type: a size string → bytes (int). Bare number = MB."""
    return _parse_size_bytes(s)


class _LongHelpAction(argparse.Action):
    """--long-help: print the full README (the long-form manual) and exit.
    Fires during parsing like -h, so it works with no input argument. Prints
    README.md next to this script (single source of truth); falls back to the
    GitHub URL if the file isn't alongside (e.g. an odd install layout)."""
    def __init__(self, option_strings, dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings=option_strings, dest=dest,
                         default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        readme = Path(__file__).resolve().parent / 'README.md'
        if readme.exists():
            sys.stdout.write(readme.read_text(encoding='utf-8'))
        else:
            print("Full documentation (README):\n"
                  "  https://github.com/lentferj/mpc2emu/blob/main/README.md")
        parser.exit()


def _print_fit_options(preset_name: str, source_name: str, cur_bytes: int,
                       limit_bytes: int, bound_desc: str, opts: list) -> list:
    """Print the over-limit banner + numbered fitting options. Returns the list
    of fitting options in the order they were numbered (1-based on screen)."""
    print(f"\n  [FIT] Preset '{preset_name}' from '{source_name}' needs "
          f"{cur_bytes/1024/1024:.0f} MB but {bound_desc} is "
          f"{limit_bytes/1024/1024:.1f} MB.")
    print("        A single preset can't be split across banks, so it must be "
          "thinned to fit:")
    fitting = [o for o in opts if o['fits']]
    n = 0
    for o in opts:
        est = o['est_bytes'] / 1024 / 1024
        if o['fits']:
            n += 1
            print(f"    {n}) {o['flag']:<32} {o['label']}  (~{est:.0f} MB)")
        else:
            print(f"       {o['flag']:<32} {o['label']}  (~{est:.0f} MB, still too big)")
    return fitting


def _apply_fit_option(opt: dict, preset, bank) -> None:
    """Apply one chosen fit option to `preset`/`bank` in place."""
    from processors.zone_reducer import (thin_velocity_layers, thin_key_zones,
                                         _prune_unused_samples)
    attr, val = opt['arg']
    if attr == 'reduce_velocity_layers':
        thin_velocity_layers(preset, 100.0 - val)
    elif attr == 'reduce_key_zones':
        for v in preset.voices:
            thin_key_zones(v, 100.0 - val)
    elif attr == 'max_sample_rate':
        for i, s in enumerate(bank.samples):
            if s.sample_rate > val:
                bank.samples[i] = resample_to_rate(s, val)
    _prune_unused_samples(bank)


def fit_oversized_presets(source_banks: List[Bank], fmt: str,
                          bank_size_mb: float, auto_fit: bool = False,
                          max_preset_bytes: Optional[int] = None) -> None:
    """
    Before splitting, catch any single preset that is too big — either for one
    bank (a preset is never split across banks) or for an explicit
    --max-preset-size cap.  Behaviour when a preset is over the effective limit:
      - interactive shell: offer smart, pre-sized suggestions (drop velocity
        layers / thin key zones / downsample) and apply the user's choice;
      - non-interactive + --auto-fit: auto-apply the least-lossy fitting option;
      - non-interactive without --auto-fit: print the suggestions and exit
        non-zero, so a batch run never silently ships an unloadable/oversized bank.
    """
    from writers.bank_splitter import fit_options, preset_needed_samples
    bank_limit = max(1, int(bank_size_mb * 1024 * 1024) - 1024 * 1024)  # 1 MB safety
    if max_preset_bytes and max_preset_bytes < bank_limit:
        limit_bytes = max_preset_bytes
        bound_desc = "the per-preset limit (--max-preset-size)"
    else:
        limit_bytes = bank_limit
        bound_desc = f"the {_HW_LABEL.get(fmt, fmt)} bank limit"
    rate_floor = 24000 if fmt == 'krz' else 22050
    interactive = sys.stdin.isatty()
    unresolved = []

    for bank in source_banks:
        for preset in list(bank.presets):
            needed = preset_needed_samples(preset, bank.samples)
            cur, opts = fit_options(preset, needed, limit_bytes, rate_floor)
            if cur <= limit_bytes:
                continue                              # already fits
            _print_fit_options(preset.name, bank.name, cur, limit_bytes,
                               bound_desc, opts)

            # Resolve by applying reductions until it fits.  A single reduction
            # may not be enough (an aggressive cap on a huge preset), so we stack
            # them, re-computing the options after each step.
            last = None
            while cur > limit_bytes:
                if not opts or (last is not None and cur >= last):
                    unresolved.append((preset.name, bank.name, cur))
                    break                             # no options / stalled
                fitting = [o for o in opts if o['fits']]

                if interactive:
                    prompt = (f"  Choose [1-{len(fitting)}] to apply"
                              if fitting else
                              "  No single reduction fits — press Enter to apply "
                              f"the strongest ({opts[0]['flag']})")
                    try:
                        raw = input(f"{prompt}, or 's' to skip: ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        print(); raw = 's'
                    if raw in ('s', 'skip'):
                        unresolved.append((preset.name, bank.name, cur))
                        break
                    if fitting and raw.isdigit() and 1 <= int(raw) <= len(fitting):
                        chosen = fitting[int(raw) - 1]
                    else:
                        chosen = opts[0]              # strongest least-lossy axis
                elif auto_fit:
                    # least-lossy option that fits, else strongest available axis
                    chosen = next((o for o in opts if o['fits']), opts[0])
                else:
                    unresolved.append((preset.name, bank.name, cur))
                    break                             # batch, no --auto-fit

                last = cur
                _apply_fit_option(chosen, preset, bank)
                tag = '--auto-fit applied' if (auto_fit and not interactive) \
                    else 'applied'
                print(f"    → {tag} {chosen['flag']}; re-checking…")
                needed = preset_needed_samples(preset, bank.samples)
                cur, opts = fit_options(preset, needed, limit_bytes, rate_floor)
                if cur <= limit_bytes:
                    print(f"    → fits now (~{cur/1024/1024:.1f} MB).")
                elif interactive or (auto_fit and not interactive):
                    _print_fit_options(preset.name, bank.name, cur, limit_bytes,
                                       bound_desc, opts)

    if not unresolved:
        return
    print()
    for name, bnk, sz in unresolved:
        print(f"  [FIT] Preset '{name}' ({sz/1024/1024:.0f} MB) still exceeds "
              f"{bound_desc} ({limit_bytes/1024/1024:.1f} MB).")
    if not interactive:
        print("  Re-run with --auto-fit, or --reduce-velocity-layers / "
              "--reduce-key-zones / --max-sample-rate (see the sized suggestions "
              "above), or raise --bank-size (if the hardware allows).")
        sys.exit(2)
    print("  Proceeding anyway at your request — the oversized bank(s) may not "
          "load on hardware.")


def parse_all_sources(files: List[Path], wav_dir: Optional[str],
                      extra_kwargs: dict) -> List[Bank]:
    banks = []
    for p in files:
        ext = p.suffix.lower()
        parser = PARSERS.get(ext)
        if not parser:
            continue
        print(f"\n  Parsing [{ext.upper()[1:]}]: {p.name}")
        try:
            bank = parser(p, wav_dir or str(p.parent), **extra_kwargs)
            if not bank.presets:
                print(f"  [SKIP] No presets in {p.name}"); continue
            if not bank.samples:
                print(f"  [SKIP] No samples loaded for {p.name}"); continue
            banks.append(bank)
        except Exception as e:
            print(f"  [ERROR] {p.name}: {e}")
    return banks


def main():
    ap = argparse.ArgumentParser(
        description='mpc2emu — Multi-format Sampler Converter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('input',
        help='Input file or directory '
             '(.e4b .xpm .pgm .set .img .talsmpl .sfz .sf2 .exs .gig)')
    ap.add_argument('--long-help', action=_LongHelpAction,
        help='Print the full README (long-form manual) and exit')
    ap.add_argument('--info',    action='store_true',
        help='Inspect without converting')
    ap.add_argument('--verbose', action='store_true',
        help='Show per-zone detail with --info')
    ap.add_argument('--wav-dir',
        help='Extra directory to search for referenced WAV samples')
    ap.add_argument('--output-dir', '--out-dir', dest='out_dir', default='.',
        metavar='DIR', help='Output directory (default: current directory)')
    ap.add_argument('--overwrite', action='store_true',
        help='Overwrite existing output files without prompting')
    ap.add_argument('--bank-size', '--max-bank-size', dest='bank_size',
        type=_size_mb_type, default=32.0, metavar='SIZE',
        help='Max bank size, e.g. 64MB / 65536K / 32 (bare = MB). Default 32 MB; '
             'E4XT hardware max 128 MB, K2000 max 64 MB.')
    ap.add_argument('--max-preset-size', dest='max_preset_size',
        type=_size_bytes_type, default=None, metavar='SIZE',
        help='Cap each single preset/program, e.g. 8192K / 8MB, so no one '
             'preset fills a whole bank (thinned to fit like an over-bank preset; '
             'use with --auto-fit for batch runs). Default: no per-preset cap.')
    ap.add_argument('--bank-name', default='EMU_BANK', metavar='NAME',
        help='Base (internal) name for output banks (default: EMU_BANK). The '
             'on-disk B.NNN- prefix comes from --bank-start.')
    ap.add_argument('--bank-start', type=int, default=None, metavar='N',
        help='Number output bank files B.NNN-NAME… starting at N so they can be '
             'copied straight onto an existing E4XT volume (e.g. 100 → '
             'B.100-NAME_01.E4B); no --iso needed')
    ap.add_argument('--format', choices=['e4b','krz','talsmpl'], default='e4b',
        help='Output format (default: e4b). e4b = EMU Emulator 4 / E4XT, '
             'krz = Kurzweil K2000/K2500/K2600, talsmpl = TAL-Sampler.')
    ap.add_argument('--iso',  action='store_true',
        help='Build a ZuluSCSI CD image (e4b → EMU3 filesystem, krz → K2000 FAT16)')
    ap.add_argument('--floppy', nargs='?', const='1440', choices=['720', '1440'],
        metavar='KB',
        help='Write each KRZ bank to a DOS FAT12 floppy image (.img) for a Gotek/'
             'FlashFloppy on the K2000R  [krz only; default 1440 = 1.44 MB]')
    ap.add_argument('--hda',  action='store_true',
        help='Build a ZuluSCSI SCSI hard disk image (.hda). e4b → EMU-fs/FAT '
             'E4XT disk; krz → K2000 FAT16 disk (HW-confirmed: loads from a '
             'ZuluSCSI HDx device).')
    ap.add_argument('--hda-size', type=int, default=None, metavar='MB',
        help='HDA image size in MB. e4b default: auto (smallest 128 MB step that '
             'fits; max 14336). krz default: content + ~50%% headroom to save '
             'onto (FAT16 max ~2047).')
    ap.add_argument('--hda-fs', choices=['fat', 'emu'], default='fat',
        help="E4B HDA filesystem: 'fat' (EOS 4.7+, default; needs mtools) or "
             "'emu' (native EMU-fs, all EOS versions). Ignored for krz (K2000 "
             "is always FAT16).")
    ap.add_argument('--add-to', metavar='IMAGE',
        help='Append the converted bank(s) to an existing image in place (no '
             'rebuild, no emu3fs). e4b → a .hda (FAT or EMU-fs, auto-detected); '
             'krz → a K2000 FAT16 CD (.iso) or hard-disk (.hda), into BANKS/. '
             'Never overwrites existing banks unless --on-duplicate overwrite.')
    ap.add_argument('--folder', metavar='NAME',
        help='With --add-to: target folder on the image, created if absent '
             '(default: root / Default Folder).')
    ap.add_argument('--on-duplicate', choices=['prompt', 'add-new', 'skip', 'overwrite'],
        default='prompt',
        help='With --add-to, when a bank name already exists: prompt (default), '
             'add-new (next free number/slot), skip, or overwrite.')
    ap.add_argument('--resample', choices=list(PROFILES.keys()), metavar='PROFILE',
        help='Vintage resampling profile: emulator2 (EMU Emulator II, 8-bit) or '
             'emax1 (EMU Emax I, 12-bit) — both 27.5 kHz.')
    ap.add_argument('--no-bandpass', action='store_true',
        help='Skip the bandpass output coloring stage when using --resample')
    ap.add_argument('--resample-keep-gain', action='store_true',
        help='With --resample, keep the gain-staged "hot" level instead of '
             "restoring each sample's original level afterwards")
    ap.add_argument('--max-sample-rate', type=int, default=-1, metavar='HZ',
        help='Clean-downsample any sample above HZ down to HZ (linear, no '
             'vintage coloring). Buys K2000 up-pitch headroom for wide key '
             'zones (log2(48000/HZ) octaves) and shrinks the bank to fit a '
             'floppy. e.g. 12000 keeps full multisample tracking on a 1.44 MB '
             'floppy. **Defaults to 24000 Hz for --format krz** (the K2000 only '
             'gives +1.46 st headroom at 44.1 kHz, so wide zones clamp); pass 0 '
             'to disable, or any HZ to override. No default for e4b. '
             'See docs/RESOLUTION_NOTES.md "KRZ up-pitch clamp".')
    ap.add_argument('--reduce-key-zones', type=float, default=0.0, metavar='PCT',
        help='Remove PCT%% of per-voice key-zone samples, spreading '
             'survivors to fill the gaps (0-100)')
    ap.add_argument('--reduce-velocity-layers', type=float, default=0.0, metavar='PCT',
        help='Remove PCT%% of per-preset velocity layers, spreading '
             'survivors to fill the gaps (0-100)')
    ap.add_argument('--auto-fit', action='store_true',
        help='When a single preset is too big for one bank, auto-apply the '
             'least-lossy fitting reduction (drop velocity layers, else thin key '
             'zones, else downsample) instead of failing. For batch/non-interactive '
             'builds; in an interactive shell you are prompted with sized options '
             'either way.')
    ap.add_argument('--max-presets', type=int, default=64,
        help='Max presets to import from a multi-preset SF2 / GIG (default: 64)')
    ap.add_argument('--from-samples', action='store_true',
        help='Treat the input directory as a folder of WAVs (root note in the '
             'filename) and auto-build one multisample preset (also auto-detected '
             'for a WAV-only directory).')
    ap.add_argument('--middle-c', choices=['auto', 'C3', 'C4', 'C5'], default='auto',
        help='Octave naming for filename root notes: which C = MIDI 60. Default '
             '"auto" detects it from embedded WAV roots (falls back to C3).')
    ap.add_argument('--lfo-sync-bpm', type=float, default=120.0, metavar='BPM',
        help='Reference tempo for reproducing tempo-synced MPC LFOs as a fixed '
             'rate (default: 120 — the MPC/DAW new-project default; the BPM is '
             'not stored in the XPM). See docs/lfo_sync_rates.md for the table.')
    ap.add_argument('--jobs', type=int, default=None, metavar='N',
        help='Parallel workers for resampling (default: cpu_count-1)')
    ap.add_argument('--single-cycle', nargs='?', const='auto', default=None,
        metavar='auto|N',
        help='Turn each sample into a looped oscillator so the sampler plays it '
             'as a synth voice (its own filter/envelopes shape the tone). '
             'Bare/"auto" extracts ONE clean cycle (sub-sample accurate) and tiles '
             'it to a hardware-safe loop length; "=N" takes N contiguous cycles '
             'instead (keeps the source\'s cycle-to-cycle movement). Pitch is baked '
             'into the sample rate so it plays in tune. Emits a neutral 4-pole-'
             'lowpass + organ-envelope preset; see the --single-cycle-keep-* '
             'flags to retain the source filter/LFO/amp-env instead. Best on '
             'multisampled input (each key plays a near-pitched cycle → no aliasing).')
    ap.add_argument('--single-cycle-keep-flt', action='store_true',
        help='With --single-cycle: keep the converted source filter '
             '(type/cutoff/resonance/env) instead of the neutral 4-pole lowpass.')
    ap.add_argument('--single-cycle-keep-lfo', action='store_true',
        help='With --single-cycle: keep the converted source LFO(s) and their '
             'modulation routings instead of stripping them.')
    ap.add_argument('--single-cycle-keep-amp', action='store_true',
        help='With --single-cycle: keep the converted source amp envelope '
             'instead of the organ-style (instant-on, full-sustain) default.')
    ap.add_argument('--single-cycle-keep-all', action='store_true',
        help='With --single-cycle: keep the whole converted voice (implies '
             '--single-cycle-keep-flt/-lfo/-amp); only shorten the samples.')
    ap.add_argument('--single-cycle-dump-dir', metavar='DIR', default=None,
        help='With --single-cycle: also write each extracted cycle as a .wav '
             'into DIR for audition/QA.')
    ap.add_argument('--split-velocity-layers', action='store_true',
        help='Explode each preset\'s velocity layers into separate full-velocity '
             'presets (a playable palette). Pairs naturally with --single-cycle, '
             'where each layer is a distinct oscillator waveform.')

    args       = ap.parse_args()
    input_path = Path(args.input)
    out_dir    = Path(args.out_dir)

    _hw_limits = {'e4b': 128, 'krz': 64}
    _hw_names  = {'e4b': 'E4XT', 'krz': 'K2000'}
    _hw_max = _hw_limits.get(args.format)
    if _hw_max and args.bank_size > _hw_max:
        print(f"  [WARN] --bank-size {args.bank_size:.0f} MB exceeds the "
              f"{_hw_names[args.format]} hardware max of {_hw_max} MB "
              f"— clamping to {_hw_max} MB")
        args.bank_size = float(_hw_max)

    for opt_name, opt_val in (('--reduce-key-zones', args.reduce_key_zones),
                              ('--reduce-velocity-layers', args.reduce_velocity_layers)):
        if not 0.0 <= opt_val <= 100.0:
            print(f"Error: {opt_name} must be between 0 and 100 (got {opt_val:.0f}).")
            sys.exit(1)

    # --single-cycle: normalise 'auto' | positive int; fold keep-all into the trio.
    if args.single_cycle is not None and args.single_cycle != 'auto':
        try:
            sc_n = int(args.single_cycle)
            if sc_n < 1:
                raise ValueError
        except ValueError:
            print("Error: --single-cycle takes 'auto' or a positive integer "
                  f"(got {args.single_cycle!r}).")
            sys.exit(1)
        args.single_cycle = sc_n
    if args.single_cycle_keep_all:
        args.single_cycle_keep_flt = True
        args.single_cycle_keep_lfo = True
        args.single_cycle_keep_amp = True

    if not input_path.exists():
        print(f"Error: '{input_path}' not found."); sys.exit(1)

    extra = {'max_presets': args.max_presets, 'max_samples': 512}

    # ── --info mode ───────────────────────────────────────────────────────────
    if args.info:
        run_info(input_path, args.wav_dir, extra, verbose=args.verbose)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    bank_name = args.bank_name.upper()[:12]

    fmt_names = {
        'e4b':     'EMU Emulator 4 / E4XT',
        'krz':     'Kurzweil K2000 / K2500 / K2600',
        'talsmpl': 'TAL-Sampler',
    }

    input_files = collect_input_files(input_path)
    # Sample-folder mode: a directory of root-note-named WAVs → one multisample.
    sample_dir = None
    if args.from_samples or (not input_files and input_path.is_dir()
            and next(input_path.rglob('*.[wW][aA][vV]'), None) is not None):
        sample_dir = input_path
        input_files = [input_path]                 # for the summary count
    if not input_files:
        print(f"No supported input files found in '{input_path}'.")
        print(f"Supported extensions: {', '.join(sorted(INPUT_EXTS))}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"mpc2emu  |  Multi-format Sampler Converter")
    print(f"{'='*60}")
    print(f"  Input:      {input_path}")
    print(f"  Files:      {len(input_files)}")
    print(f"  Format:     {args.format.upper()}  ({fmt_names[args.format]})")
    if args.format != 'talsmpl':
        print(f"  Bank size:  {args.bank_size:.0f} MB max")
    print(f"  Output:     {out_dir}/")
    if args.iso:
        print(f"  ISO:        yes (ZuluSCSI CD image)")
    if args.hda:
        _sz = f"{args.hda_size} MB" if args.hda_size else "auto-size"
        print(f"  HDA:        yes (ZuluSCSI SCSI disk, {_sz})")
    if args.resample:
        prof     = PROFILES[args.resample]
        bp_str   = 'off' if args.no_bandpass else 'on'
        lvl_str  = 'keep gain-staged level' if args.resample_keep_gain else 'restore source level'
        print(f"  Resample:   {prof.display_name}  (bandpass: {bp_str}, level: {lvl_str})")
    if args.reduce_key_zones > 0 or args.reduce_velocity_layers > 0:
        print(f"  Reduce:     key zones -{args.reduce_key_zones:.0f}%, "
              f"velocity layers -{args.reduce_velocity_layers:.0f}%")
    print(f"{'='*60}")

    step_n = 1

    # ── Parse ─────────────────────────────────────────────────────────────────
    print(f"\n[{step_n}] Parsing source files...")
    step_n += 1
    import parsers.xpm_parser as _xpm
    _xpm.SYNC_BPM = args.lfo_sync_bpm          # tempo for synced-LFO rate
    if sample_dir:
        from parsers.sampledir_parser import parse_sample_dir
        _off = None if args.middle_c == 'auto' else {'C3': 2, 'C4': 1, 'C5': 0}[args.middle_c]
        try:
            source_banks = [parse_sample_dir(str(sample_dir), octave_offset=_off)]
        except Exception as e:
            print(f"  [ERROR] {e}"); source_banks = []
    else:
        source_banks = parse_all_sources(input_files, args.wav_dir, extra)
    if not source_banks:
        print("No banks could be parsed. Aborting."); sys.exit(1)
    print(f"\n  Parsed {len(source_banks)} bank(s).")
    _n_synced = sum(1 for b in source_banks for p in b.presets for v in p.voices
                    if getattr(v, 'lfo1_sync_division', None))
    if _n_synced:
        print(f"  [LFO] {_n_synced} tempo-synced LFO(s) reproduced at "
              f"{args.lfo_sync_bpm:g} BPM (the XPM has no tempo; override with "
              f"--lfo-sync-bpm). E4XT can't tempo-follow; see docs/lfo_sync_rates.md.")

    # ── Single-cycle oscillator extraction ─────────────────────────────────────
    # Runs first so the shrunk samples flow through reduce/resample/fit/split with
    # their real (tiny) sizes.
    if args.single_cycle is not None:
        _sc_lbl = 'auto' if args.single_cycle == 'auto' else f'{args.single_cycle} cycle(s)'
        print(f"\n[{step_n}] Single-cycle extraction ({_sc_lbl})...")
        step_n += 1
        from processors.single_cycle import single_cycle_bank
        for bank in source_banks:
            single_cycle_bank(bank, cycles=args.single_cycle,
                              keep_flt=args.single_cycle_keep_flt,
                              keep_lfo=args.single_cycle_keep_lfo,
                              keep_amp=args.single_cycle_keep_amp,
                              dump_dir=args.single_cycle_dump_dir,
                              workers=args.jobs)

    # ── Reduce ────────────────────────────────────────────────────────────────
    if args.reduce_key_zones > 0 or args.reduce_velocity_layers > 0:
        print(f"\n[{step_n}] Reducing sample count "
              f"(key zones -{args.reduce_key_zones:.0f}%, "
              f"velocity layers -{args.reduce_velocity_layers:.0f}%)...")
        step_n += 1
        for bank in source_banks:
            reduce_bank(bank, args.reduce_key_zones, args.reduce_velocity_layers)

    # ── Resample ──────────────────────────────────────────────────────────────
    if args.resample:
        print(f"\n[{step_n}] Vintage resampling ({args.resample})...")
        step_n += 1
        for bank in source_banks:
            resample_bank(bank, args.resample, not args.no_bandpass,
                          restore_level=not args.resample_keep_gain,
                          workers=args.jobs)

    # ── Clean downsample for K2000 up-pitch headroom (+ floppy fit) ────────────
    # The K2000 can only pitch a sample UP to its 48 kHz playback ceiling, so a
    # 44.1 kHz sample tracks just +1.46 st before clamping.  Two modes:
    #   --max-sample-rate HZ  (explicit, >0): blanket — downsample EVERY sample
    #       above HZ to HZ.  Uniform/predictable size; used for floppy fit.
    #   default (krz, unset = -1): HEADROOM-AWARE — only downsample a sample whose
    #       key zones ask it to play HIGHER than its current rate allows, and only
    #       as far as needed (floor 24 kHz).  Dense/narrow-zone multisamples that
    #       already track are left at full quality.  (0 disables entirely.)
    _KRZ_RATE_FLOOR = 24000
    max_sr = args.max_sample_rate
    if max_sr > 0:
        print(f"\n[{step_n}] Downsampling to max {max_sr} Hz "
              f"(+{1200*math.log(48000.0/max_sr, 2)/100:.1f} st "
              f"up-pitch headroom)...")
        step_n += 1
        for bank in source_banks:
            for i, s in enumerate(bank.samples):
                if s.sample_rate > max_sr:
                    bank.samples[i] = resample_to_rate(s, max_sr)
    elif max_sr < 0 and args.format == 'krz':
        print(f"\n[{step_n}] KRZ headroom-aware downsample (floor "
              f"{_KRZ_RATE_FLOOR} Hz; override --max-sample-rate, 0 disables)...")
        step_n += 1
        for bank in source_banks:
            need_hi = {}    # sample name → highest key any zone asks it to play
            for p in bank.presets:
                for v in p.voices:
                    for z in v.zones:
                        need_hi[z.sample_name] = max(need_hi.get(z.sample_name, 0),
                                                     z.hi_key)
            for i, s in enumerate(bank.samples):
                hi = need_hi.get(s.name)
                if hi is None or s.sample_rate <= _KRZ_RATE_FLOOR:
                    continue
                needed_up = max(0, hi - s.root_note)        # semitones up required
                cur_head = (1200 * math.log(48000.0 / s.sample_rate, 2) / 100
                            if s.sample_rate < 48000 else 0)
                if needed_up <= cur_head + 0.5:             # already tracks (+tol)
                    continue
                target = int(48000.0 / (2 ** (needed_up / 12.0)))   # just-enough rate
                target = max(_KRZ_RATE_FLOOR, min(s.sample_rate, target))
                if target < s.sample_rate:
                    bank.samples[i] = resample_to_rate(s, target)

    # ── TAL-Sampler output ────────────────────────────────────────────────────
    if args.format == 'talsmpl':
        print(f"\n[{step_n}] Writing TAL-Sampler presets...")
        all_written = []
        for bank in source_banks:
            written = write_talsmpl(bank, str(out_dir), copy_samples=True)
            all_written.extend(written)
        print(f"\n{'='*60}")
        print(f"Done: {len(all_written)} preset(s) written to {out_dir}/")
        print(f"{'='*60}\n")
        return

    # ── Explode velocity layers into separate presets ──────────────────────────
    # Before the fit assistant + split so both see the final preset set.
    if args.split_velocity_layers:
        print(f"\n[{step_n}] Splitting velocity layers into separate presets...")
        step_n += 1
        from processors.zone_reducer import explode_velocity_layers
        for bank in source_banks:
            explode_velocity_layers(bank)

    # ── Fit oversized single presets (interactive assistant) ───────────────────
    # A preset is never split across banks, so one too big for a bank must be
    # thinned/downsampled to fit.  Offer sized suggestions (or hard-fail a batch
    # run) BEFORE the split so no unloadable bank is ever written silently.
    if args.format in ('e4b', 'krz'):
        fit_oversized_presets(source_banks, args.format, args.bank_size,
                              auto_fit=args.auto_fit,
                              max_preset_bytes=args.max_preset_size)

    # ── Split ─────────────────────────────────────────────────────────────────
    print(f"\n[{step_n}] Splitting into {args.bank_size:.0f} MB banks...")
    step_n += 1
    output_banks, warnings = split_into_banks(
        source_banks, args.bank_size, bank_name)
    for w in warnings:
        print(w)
    print_split_summary(source_banks, output_banks, args.bank_size)

    # ── Write bank files ──────────────────────────────────────────────────────
    ext = '.E4B' if args.format == 'e4b' else '.KRZ'

    def _bank_path(i: int, bank) -> str:
        # --bank-start adds the EOS B.NNN- volume prefix (B.100-NAME_01.E4B, …);
        # without it, just NAME.E4B.
        if args.bank_start is not None:
            return str(out_dir / f"B.{args.bank_start + i:03d}-{bank.name}{ext}")
        return str(out_dir / f"{bank.name}{ext}")

    # Pre-flight: don't clobber existing bank/ISO/HDA files unless --overwrite.
    planned = [_bank_path(i, b) for i, b in enumerate(output_banks)]
    if args.iso:
        planned.append(str(out_dir / f"{bank_name}.iso"))
    if args.hda and (args.format == 'krz' or
                     (args.format == 'e4b' and (args.hda_size is None or args.hda_size <= 14 * 1024))):
        planned.append(str(out_dir / f"{bank_name}.hda"))
    if not _confirm_overwrite(planned, args.overwrite):
        print("\nAborted — no files written. Re-run with --overwrite to skip this check.")
        sys.exit(1)

    print(f"\n[{step_n}] Writing {args.format.upper()} files...")
    step_n += 1
    out_paths: List[str] = []
    for i, bank in enumerate(output_banks):
        out_path = _bank_path(i, bank)
        try:
            (write_e4b if args.format == 'e4b' else write_krz)(bank, out_path)
            out_paths.append(out_path)
        except Exception as e:
            print(f"  [ERROR] {bank.name}{ext}: {e}")

    # ── Append to an existing image ─────────────────────────────────────────────
    if args.add_to and out_paths:
        if not Path(args.add_to).exists():
            print(f"\n[ADD] ERROR: image not found: {args.add_to}")
        elif args.format == 'krz':
            # K2000 CD (.iso) and hard-disk (.hda) are the same FAT16 disk-image;
            # append into BANKS/ in place — no rebuild, no emu3fs.
            from writers.iso_builder import k2000_disk_append
            print(f"\n[ADD] Appending {len(out_paths)} bank(s) to "
                  f"{Path(args.add_to).name} (K2000 FAT16)"
                  + (f", folder '{args.folder}'" if args.folder else "") + "...")
            try:
                k2000_disk_append(args.add_to, out_paths, args.folder, args.on_duplicate)
            except Exception as e:
                print(f"  [ADD] ERROR: {e}")
        elif args.format == 'e4b':
            from writers.hda_builder import detect_hda_fs, fat_hda_append
            from writers.iso_builder import emu_hdd_append
            try:
                fs = detect_hda_fs(args.add_to)
                print(f"\n[ADD] Appending {len(out_paths)} bank(s) to "
                      f"{Path(args.add_to).name} ({fs.upper()})"
                      + (f", folder '{args.folder}'" if args.folder else "") + "...")
                append = emu_hdd_append if fs == 'emu' else fat_hda_append
                append(args.add_to, out_paths, args.folder, args.on_duplicate)
            except Exception as e:
                print(f"  [ADD] ERROR: {e}")

    # ── Floppy (Gotek / K2000R) ─────────────────────────────────────────────────
    if args.floppy and out_paths:
        if args.format != 'krz':
            print("\n[FLOPPY] Skipped — floppy images are only for KRZ (K2000) banks.")
        else:
            from writers.fat12 import format_new as _fmt_floppy
            cap = (1440 if args.floppy == '1440' else 720) * 1024 - 16 * 1024  # ~free
            print(f"\n[FLOPPY] Writing FAT12 {args.floppy} KB floppy image(s) for Gotek...")
            for op in out_paths:
                src = Path(op)
                img = out_dir / (src.stem + ".img")
                size = src.stat().st_size
                if size > cap:
                    print(f"  [SKIP] {src.name} ({size/1024:.0f} KB) exceeds a "
                          f"{args.floppy} KB floppy — use a HD/ISO image or split the bank.")
                    continue
                fs = _fmt_floppy(str(img), args.floppy, src.stem[:11])
                fs.add_file(str(src), src.name)
                fs.close()
                print(f"  → {img.name}  ({size/1024:.0f} KB bank on a {args.floppy} KB floppy)")
            print(f"  Copy the .img onto the Gotek USB stick (FlashFloppy reads raw .img).")

    # ── ISO / disk image ───────────────────────────────────────────────────────
    if args.iso and out_paths:
        # E4XT → EMU3 filesystem.  K2000 → FAT16 "disk-image copy" (no partition):
        # the only CD form every K2000 OS reads (ISO 9660 needs OS v3.87+, and even
        # then the K2000's reader is picky).  See writers/iso_builder.build_k2000_disk.
        from writers.iso_builder import build_k2000_disk
        iso_fn = build_iso if args.format == 'e4b' else build_k2000_disk
        iso_label = "EMU3" if args.format == 'e4b' else "K2000 FAT16"
        print(f"\n[ISO] Building ZuluSCSI CD image(s) ({iso_label})...")
        total = sum(Path(p).stat().st_size for p in out_paths)
        if total <= 650 * 1024 * 1024:
            iso_path = str(out_dir / f"{bank_name}.iso")
            iso_fn(out_paths, iso_path, bank_name)
            print(f"  → Rename to CD1.iso on ZuluSCSI SD card")
        else:
            for i, op in enumerate(out_paths, 1):
                iso_path = str(out_dir / (Path(op).stem + ".iso"))
                iso_fn([op], iso_path, f"{bank_name}_{i:02d}")
                print(f"  Bank {i} → CD{i}.iso")

    # ── HDA ───────────────────────────────────────────────────────────────────
    if args.hda and out_paths:
        if args.format == 'krz':
            # K2000 SCSI hard disk = the same FAT16 disk-image copy as the CD form
            # (HW-confirmed: banks load from a ZuluSCSI HDx device).  Give it
            # headroom by default so the K2000 can also save onto it.
            from writers.iso_builder import build_k2000_disk
            content_mb = sum(Path(p).stat().st_size for p in out_paths) / 1024 / 1024
            hda_size = args.hda_size or min(2047, max(64, ((int(content_mb * 1.5) // 64) + 1) * 64))
            if hda_size > 2047:
                print(f"\n[HDA] --hda-size {hda_size} MB exceeds the FAT16 limit; "
                      f"clamping to 2047 MB.")
                hda_size = 2047
            hda_path = str(out_dir / f"{bank_name}.hda")
            print(f"\n[HDA] Building K2000 FAT16 hard-disk image "
                  f"({hda_size} MB, ~{hda_size - content_mb:.0f} MB free)...")
            build_k2000_disk(out_paths, hda_path, bank_name, size_mb=hda_size)
            print(f"  → Copy to the ZuluSCSI SD card as HDx-{bank_name}.hda "
                  f"(x = a free SCSI ID)")
        elif args.format == 'e4b':
            # default: auto-size to the smallest 128 MB step that fits the banks.
            hda_size = args.hda_size or auto_hda_size_mb(out_paths, args.hda_fs)
            if hda_size > 14 * 1024:
                print(f"\n[HDA] ERROR: --hda-size {hda_size} MB exceeds "
                      f"EIV OS limit of 14336 MB.")
            elif args.hda_fs == 'fat':
                # FAT image (EOS 4.7+) — read by ZuluSCSI + EOS directly.
                build_hda_fat(
                    output_path = str(out_dir / f"{bank_name}.hda"),
                    size_mb     = hda_size,
                    volume_name = bank_name,
                    e4b_files   = out_paths,
                )
            else:
                # EMU-fs (all EOS versions) — proper disk-sized EMU3 image.
                build_hda_emu(
                    output_path = str(out_dir / f"{bank_name}.hda"),
                    volume_name = bank_name,
                    e4b_files   = out_paths,
                    size_mb     = hda_size,
                )

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Done: {len(out_paths)} file(s) written to {out_dir}/")
    for p in out_paths:
        mb = Path(p).stat().st_size / 1024 / 1024
        print(f"  {Path(p).name}  ({mb:.2f} MB)")
    if args.iso:
        for iso in sorted(out_dir.glob("*.iso")):
            print(f"  {iso.name}  ({iso.stat().st_size/1024/1024:.1f} MB)")
    if args.hda:
        for hda in sorted(out_dir.glob("*.hda")):
            print(f"  {hda.name}  ({hda.stat().st_size/1024/1024:.1f} MB)")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
