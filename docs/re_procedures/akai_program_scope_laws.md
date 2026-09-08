<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: three AKAI program-scope laws (§AKAIPROGSCOPE)

## Goal

Settle three laws so `octave_shift`, stereo `LEVEL` and program `PAN` can be
applied instead of reported. Each is **one measurement**; together they are one
short session and **no card swap** — `s3ked`'s probes set program parameters
over SysEx.

## Why these three

[ConvertWithMoss PR #400](https://github.com/git-moss/ConvertWithMoss/pull/400)
applies all three on their side, which is what put them in view here. Their
work is independent (the offsets were already in their parser), and their
*scaling assumptions* are not measurements we hold — which is exactly what this
procedure exists to replace.

Our parser reads all three; nothing applies them; the writer emits a fixed
0 / 99 / 0. As of 2026-09-08 each is **reported** as dropped rather than
silently ignored.

## What the corpus already says

10,933 programs across 21 library discs, **no out-of-range values in any of the
three**, so the reads are aligned (this project's own rule: a distribution is
not evidence of alignment, an out-of-range value is evidence against it).

| field | offset | non-default | commonest non-default |
|---|---|---|---|
| stereo `LEVEL` | `0x17` | **1,347 (12.3 %)** | 90 (735), 80 (239), 85 (80) |
| `PAN` | `0x18` | 91 (0.8 %) | 3, −10, −5, −20 |
| `OCTAVE` | `0x15` | 33 (0.3 %) | −1 (20), +1 (13) |

**Stereo level is the one that matters by volume**, and at 90 the measured
program-loudness law would put it **5.8 dB** below what we render today.
**Octave shift matters by severity** — a pitch error of up to two octaves.

## The manual settles the semantics; only the laws are open

- `LEVEL` — *"the level of the program as it appears at the left/right stereo
  outputs … the equivalent of a mixer's fader"*, 0–99.
- `PAN` — *"L50 through MID (00) to R50"*.
- Both are **MULTI parameters**: a part's values override in MULTI, so the
  program's own apply in **SINGLE** — which is how a converted program is
  auditioned. They are audible, not vestigial.

## Measurement 1 — the octave shift's SIGN

*"Key ranges move against the shift and the tuning moves with it"* is CWM's
description, not our measurement. **Backwards is worse than dropped.**

1. One program, one keygroup, a sample with a clear pitch, `OCTAVE = 0`.
   Play a known key; record the pitch.
2. Set `OCTAVE = +1`. Play **the same key**.
3. The pitch either rises an octave or falls one. That is the whole answer.

Also record whether the **key range** the sample answers on moves — that is the
second half of CWM's claim and is separable: play the octave above and below
the original range and see which now sounds.

## Measurement 2 — does stereo LEVEL reuse the program-loudness law?

The law we already hold is `dB = 0.642719 × PRLOUD − 87.63` (r² 0.9933).

1. Fix everything else; set `LEVEL = 99`, capture, note the level.
2. Set `LEVEL = 90`, capture. **The measured law predicts −5.78 dB.**
3. Repeat at 80 and 60 — the corpus's other common values — to see whether the
   law holds across the range or only near the top.

**If it matches, no new law is needed** and the field can be applied through
the existing one. If it does not, this is a second law and needs its own fit.

## Measurement 3 — does program PAN reuse the constant-power law?

Zone pan uses constant power, `theta = (PANPOS + 50)/100 × pi/2`.

1. `PAN = 0`, capture both channels; then `PAN = 25` and `PAN = 50`.
2. Compare the L/R balance against the constant-power prediction.
3. **Also settle how it COMBINES with zone pan** — CWM adds it to the zone
   values. Set a zone hard left and the program hard right and see what comes
   out: sum, override, or clamp. A law without its combination rule cannot be
   applied.

## Traps

- **PRGNUM 0 is never free** — the boot-resident `TEST PROGRAM` sits there and
  survives every memory clear. Number test programs from 1.
- **Measure in SINGLE mode.** In MULTI these three are part parameters and the
  program's own values do not apply; a null result there would mean nothing.
- **Change one field at a time.** `LEVEL = 0` removes the program from the
  stereo mix entirely, which looks like silence from a broken rig.
- **Check what actually sounded** before interpreting — commanded notes
  present, and read the harness's blind fraction and spacing gate.

## Then

Apply each law only once measured, and keep the diagnostics for anything still
unapplied. The three reporting codes are `AKAI_OCTAVE_SHIFT_DROPPED`,
`AKAI_STEREO_LEVEL_DROPPED` and `AKAI_PROGRAM_PAN_DROPPED`.
