<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Ready-to-release matrix

What must pass end to end before a release, how to run it, and — just as
important — **what it does not cover**.

Run it:

```bash
python3 tests/release_matrix.py                 # full, ~4 min
python3 tests/release_matrix.py --quick         # axis A only
python3 tests/release_matrix.py --markdown m.md # record the result
```

It exits non-zero if any cell fails, synthesises its own fixtures where it
can, and writes only under `~/temp/release_matrix/`.

## Why these axes and not "every combination"

The full cross-product is 32 input extensions × 4 output formats × 5 media ×
a dozen independent processor flags. That is not a test plan — most of it
exercises `argparse`, and the combinatorial cells share no code that the
per-axis cells do not already reach. What is worth *complete* coverage is
each axis:

| axis | what it answers | cells |
|------|-----------------|-------|
| **A** input × output | does every source format reach every target format at all | 92 |
| **B** output × medium | bank file, `--iso`, `--hda`, `--floppy`, `--add-to` | 14 |
| **C** processors | each flag on one representative path, plus the pairs known to interact | 30 |

**Two fixtures are synthesised, and that is weaker.** No SoundFont or EXS24
instrument is local, so `tests/re_banks/gen_sf2_fixture.py` and
`gen_exs24_fixture.py` build one each — a structurally complete SF2 (INFO /
sdta / pdta with the terminal records the spec requires) and a classic
little-endian EXS24 with one zone, group and sample. They are marked
`(synthetic)` in the results because a fixture we wrote tests the parser
against **our own model** of the format: it catches a regression, it cannot
catch a misunderstanding. A real file of either would be strictly better and
would replace them.

**What axis C does *not* reach**, stated so it is not mistaken for coverage:
the sub-options of a flag it does drive — `--auto-loop-{xfade,trim,force,
max-ms,min-quality,no-crossfade}`, `--single-cycle-keep-*`,
`--trim-{start,tail}-{fade,keep-loops}`. That is a deliberate omission: they
modify a flag whose path the axis already walks. `--pan-law`, `--no-bandpass`,
`--resample-keep-gain` and the three size gates *were* a genuine gap and are
now cells.

**One cell is inverted.** `--max-preset-size (refuses)` passes when the run
**fails**. For a size gate, converting anyway is the defect — an over-size
bank that reaches hardware is worse than a run that stops — so writing it as
an ordinary cell would have recorded the bug as green. `run_refusal()` exists
for that reason, and the accept path is covered separately by
`--max-preset-size + auto-fit`.

Axis C's pairs are chosen because they touch the same state: resampling
changes frame counts that loop points index into, `--mono` halves a stereo
buffer the loop finder just measured, and trimming moves the loop points
`--auto-loop` chose.

## Why this exists

The unit suite tests parsers and writers in isolation, and exactly one of its
files invoked `convert.py`. **Nothing had ever crossed the two axes.** A
parser can be right, a writer can be right, and the path between them still be
broken by option handling, bank splitting, or a format gate that never listed
the new format.

That is not hypothetical. The first three runs of this matrix found four
defects that the 250-test unit suite passed straight through:

1. **A preset name containing `/` crashed two writers.** An E4XT preset really
   is called `Inv/Vel>Q Arco`; the talsmpl and AKAI writers named a *file*
   after it, so the `/` became a path separator and the run died with
   `FileNotFoundError` on a directory nobody created. `models.safe_filename`
   now separates "name as metadata" from "name as a filename component".
2. **`--bank-size 1` made every conversion impossible.** The safety margin was
   a flat 1 MB — sized for a 128 MB bank — so a 1 MB bank had *one byte*
   usable and the fit assistant looped applying reductions that could not
   help. The margin is now proportional with a floor; every default is
   unchanged.
3. **The margin was computed in two places.** `convert.py` carried its own
   copy of the flat 1 MB, so the splitter and the fit assistant disagreed
   about what fits. There is now one function.
4. **`--add-to` was in no test at all** — it needs a medium to append to, so
   it never appeared in a matrix that only ran single commands.

## A matrix is only as good as the shape of its fixtures

Axis C originally ran every processor on a **mono** WAV directory. That is why
it passed `--resample emulator2` while the vintage profiles were smearing
stereo channels together and leaving a half-frame that reduced a 77-sample E4B
to one sample — a fault VinSamLib found from the other side, not this matrix.

Two changes came out of it:

- A **stereo** fixture with odd frame counts, and a `STEREO_PROCESSORS` group
  that runs the processors for which stereo is the interesting case.
- Those cells **read the bank back** rather than asking whether files
  appeared. "Files appeared" could never have caught it: the writer reported
  8 samples while the file held 1.

Even so, be honest about the strength of it: with the bug reintroduced, the
stereo cells catch `emax1` but not `emulator2`, because a two-sample fixture
does not always land on an odd frame count. **The unit tests are the reliable
detector** — `tests/test_resampler.py` sweeps frame parity — and the matrix
cell is a backstop.

## Current state

All cells green: **axis A 85/85, axis B 19/19, axis C 18/18.**

## What has no fixture — a gap, not coverage

These are reported as `--`, never as a pass:

| format | why |
|--------|-----|
| `.sf2` | no local SoundFont |
| `.exs` | no local EXS24 instrument |
| `.gig` | no local GigaSampler file |
| `.set` | **all 10 local MPC60 SETs are 720K-truncated copies.** The parser correctly refuses them, so the intact path is untested end to end |
| `.img` (MPC60) | the local MPC60 floppy images contain those same truncated SETs |

The MPC60 pair is the one worth acting on: that code has *no* end-to-end
coverage on this machine, and the reason is fixture quality rather than
anything about the code.

## What the matrix deliberately does not establish

- **That the output sounds right.** Every cell asks "did this run produce
  files without erroring". Audio correctness lives in the unit suite (PCM
  round-trips, byte-identical comparisons against independent implementations)
  and, for anything that matters, on hardware.
- **That the hardware loads it.** For AKAI in particular, see
  `docs/AKAI_S3000_FORMAT.md`: everything is cross-verified against `akaiutil`
  and 33 real library discs, and none of it is confirmed by an S3000XL.
- **Interactive paths.** The fit assistant's prompts, `--on-duplicate prompt`
  and the overwrite confirmation are all non-interactive here.

## Temp-space requirement — and the flake it caused

**The suite needs ~420 MB of scratch space** (measured peak 416 MB). Nearly
all of it is the AKAI image tests, which build 16 MB disk images — several of
them must, because their golden hashes are of 16 MB images `akaiutil` produced.

**Since 2026-08-07 that no longer lands on `/tmp`.** The root `conftest.py`
points pytest's `basetemp` at `~/temp/pytest-mpc2emu`, which is where
`CLAUDE.md` already says this project's test output belongs, and sets `TMPDIR`
to match for anything reaching for `tempfile` directly. Measured after the
change: a full run moves `/tmp` by **1 MB** instead of 416.

Two things about that redirect are deliberate. Passing `--basetemp` makes
pytest **delete and recreate that directory at the start of every run**, so it
points at one path nothing else uses — never `~/temp` itself, which holds the
corpus and the fixtures. And an explicit `--basetemp=…` on the command line is
honoured unchanged, as is a machine with no `~/temp`, which keeps pytest's
default.

This was diagnosed after two runs reported 8–9 failures that then would not
reproduce. The cause was **`/tmp` filling up** — on this machine `/tmp` is its
own 4.7 GB volume, and another project was consuming it. Confirmed by
capping file size with `ulimit -f` and re-running: the failures land on
*exactly* the AKAI image tests and nothing else. A hard cap fails 22–25 of
them; a partially-full disk fails however many happen to cross the boundary,
which is why the count was 8–9 and why it vanished when the space came back.

Two things worth carrying:

- **A green suite is not evidence the disk was fine** — and a red one is not
  evidence the code is broken. If failures cluster in `test_akai_image.py`,
  check `df` before reading a diff.
- The failure mode is loud (`OSError`), not silent, so nothing incorrect can
  pass because of it.
