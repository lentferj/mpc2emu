<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors

GENERATED FILE -- do not edit by hand.
python3 tests/release_matrix.py --markdown docs/release-matrix-results.md
-->

# Release matrix — recorded results

Generated on **2026-08-09** from commit `84c3213` on branch `main`. See `docs/RELEASE_MATRIX.md` for what the axes mean and what this does
*not* establish.

Axis A: **60 of 60** attempted cells green. `--` marks a format with no local fixture — **a gap, never a pass**; the list is at
the bottom.

| input | e4b | eiii | krz | talsmpl |
|---|---|---|---|---|
| `.e3b` | OK | OK | OK | OK |
| `.e3x` | OK | OK | OK | OK |
| `.e4b` | OK | OK | OK | OK |
| `.esi` | OK | OK | OK | OK |
| `.exs (synthetic)` | OK | OK | OK | OK |
| `.krz` | OK | OK | OK | OK |
| `.pgm` | OK | OK | OK | OK |
| `.sf2 (synthetic)` | OK | OK | OK | OK |
| `.sfz` | OK | OK | OK | OK |
| `.talsmpl` | OK | OK | OK | OK |
| `.xpj` | OK | OK | OK | OK |
| `.xpm` | OK | OK | OK | OK |
| `.xty` | OK | OK | OK | OK |
| `<wavdir stereo>` | OK | OK | OK | OK |
| `<wavdir>` | OK | OK | OK | OK |

| output | bank | --iso | --hda | --floppy | --add-to |
|---|---|---|---|---|---|
| `e4b` | OK | OK | OK | -- | OK |
| `eiii` | OK | OK | OK | -- | OK |
| `krz` | OK | OK | OK | OK | OK |
| `talsmpl` | OK | -- | -- | -- | -- |

| processor | result |
|---|---|
| `--resample emulator2` | OK |
| `--max-sample-rate 22050` | OK |
| `--trim` | OK |
| `--trim-start` | OK |
| `--trim-tail` | OK |
| `--auto-loop` | OK |
| `--single-cycle` | OK |
| `--mono` | OK |
| `--reduce-key-zones 50` | OK |
| `--reduce-velocity-layers 50` | OK |
| `--split-velocity-layers` | OK |
| `--auto-fit` | OK |
| `--bank-size 1 (splitting)` | OK |
| `--middle-c C4` | OK |
| `auto-loop + resample` | OK |
| `auto-loop + trim` | OK |
| `mono + resample` | OK |
| `trim + single-cycle` | OK |
| `--pan-law constant-power` | OK |
| `--no-bandpass` | OK |
| `--resample-keep-gain` | OK |
| `--max-presets 1` | OK |
| `--max-bank-size 1` | OK |
| `--max-preset-size + auto-fit` | OK |
| `stereo + emulator2` | OK |
| `stereo + emax1` | OK |
| `stereo + --mono` | OK |
| `stereo + --max-sample-rate` | OK |
| `stereo + auto-loop` | OK |
| `--max-preset-size (refuses)` | OK |

**No fixture (gap, not coverage):**
- `.gig` — no local GigaSampler file
- `.img (MPC60)` — the local MPC60 floppies contain those same truncated SETs
- `.set` — all 10 local MPC60 SETs are 720K-truncated copies; the parser correctly refuses them, so the intact path is untested
