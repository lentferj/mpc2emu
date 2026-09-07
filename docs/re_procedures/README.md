<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# RE procedures — what is here, and what is deliberately not

This directory holds the **procedures and the measured data** behind the format
references in `docs/`. Each `.md` records how something was established on real
hardware; each `.json` is the data that established it.

## The generators these procedures name are bench-local and not distributed

Several documents here name a script — `gen_amp_envelope_test.py`,
`analyze_envelope_recording.py`, `gen_filter_envelope_test.py` and others. Those
live in `tests/re_banks/`, which is **gitignored by project policy**, so they are
not part of a clone. That is deliberate: they carry hard-coded bench paths, MIDI
port names and SCSI ids for one specific rig, and they are not portable to
anyone else's machine.

**A reader is not missing anything they could have run.** The procedures describe
what was done and what was measured; the scripts only automate it against one
bench. Where a result matters, the *data* is here in JSON rather than only the
recipe.

Two exceptions have been promoted into this directory, on one test — **does a
tracked document depend on it?**

| file | why |
|---|---|
| `parse_k2000_algorithms.py` | regenerates `k2000_algorithms.json`, from which `docs/K2000_ALGORITHMS.md` is written — so the table can be rebuilt rather than trusted |
| `hw_measure.py` | the bench rig itself: the instrument behind every hardware number in `docs/` and `TODO.md`. Its 177 comment lines are a catalogue of measurement traps that each cost real time to find, and losing it would cost more than any single finding it produced |

## Measured data kept here

| file | what |
|---|---|
| `e4xt_lfo_rate_table.json` | E4XT LFO rate byte → Hz, 128 rows, panel-read, audio-verified at five bytes. Replaced a three-point fit that was wrong by a mean of 28.4% |
| `k2000_lfo1_rate_table.json` | K2000 LFO1 rate byte → Hz, 185 rows. A five-segment ladder; the previous law was one segment of it |
| `k2000_algorithms.json` | all 31 algorithms: block chains and the functions each block offers |
| `k2000_function_codes_by_block.json` | the stored byte for every DSP function, **per block** — the same function has different codes in different blocks |
| `e4b_cord_oracle_*.json` | mod-cord reads of two of our own converted banks, every cord including the zeros, with units and caveats stated in the file |

Cord amounts in the oracles are **interface units (±100)**; the file stores
**±127**. `interface = round(file × 100/127)`, exact.
