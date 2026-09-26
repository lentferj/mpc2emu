<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors -->
<!-- Part of mpc2emu — https://github.com/lentferj/mpc2emu -->
<!-- Contributions: Jan Lentfer, with AI assistance (see README). -->

# §KRZLFO2RATE — measuring the K2000's LFO2

**Status:** bank built and byte-verified, not yet loaded.
**Bank:** `~/temp/KRZLFO2.KRZ`, from `tests/re_banks/gen_krz_lfo2_re.py`.
**Needs:** the K2000R, one bank load, ~15 minutes of capture.

We began writing LFO2 on 2026-09-25 (segment `0x15`, located offline from the
201-file corpus — §KRZLFO2SEG). Three things about it are provisional. All
three are answerable on one loaded bank, so they ride together: the expensive
step is the crossing, not the item.

---

## The three questions

### Q1 — does LFO2's `MnRate` use LFO1's ladder?

The 185-row ladder was measured on **LFO1 `MnRate`**, and k2kremote stated
that boundary themselves. We reuse it for LFO2 on two pieces of structural
evidence: byte 2 tops out at exactly **184 on both segments** across 32 583
corpus LFO segments, and the Musician's Guide gives **both LFOs the same
published 0–24 Hz range** (LFO1 defaults to 2.00 Hz, LFO2 to OFF).

That is a carry-across. It is not a measurement.

**Programs 130–141.** Six rate bytes — 20, 60, 100, 140, 184, 36 — written
once on LFO1 (the control) and once on LFO2 (under test), at **identical
pitch depth**. Spread across the ladder including both ends, because a law
that is right in the middle and wrong at the ends is exactly what
`26 + 10 × Hz` was.

| prog | preset | rate byte | ladder says |
|---|---|---|---|
| 130 / 136 | `L1/L2 RATE 20` | 20 | 0.200 Hz |
| 131 / 137 | `L1/L2 RATE 60` | 60 | 3.400 Hz |
| 132 / 138 | `L1/L2 RATE 100` | 100 | 7.400 Hz |
| 133 / 139 | `L1/L2 RATE 140` | 140 | 12.800 Hz |
| 134 / 140 | `L1/L2 RATE 184` | 184 | 24.000 Hz |
| 135 / 141 | `L1/L2 RATE 36` | 36 | 1.000 Hz |

**Method.** Hold one note for 6 s on each program and measure the **vibrato
period**, not the pitch. A steady 220 Hz sine is the source, root-matched so
nothing is resampled — the §NOISESRC lesson applied to a tone: a source that
moves on its own reads as the LFO moving.

### Q2 — is the shape at byte 4 or byte 5?

`docs/KRZ_FORMAT.md` §4.5 puts the shape enum at byte 4 and the phase at
byte 5, and the writer follows it. The corpus disagrees: **byte 4 takes only
`{0,1,2,3}`** (96.5 % zero) and **byte 5 takes 27 values up to 39** (89.8 %
on `1`). Four values with a dominant default looks like the four phase
positions; 27 values reaching 39 looks like a 1-based shape enum.

§4.5 records a **live probe** of byte 4 across all 26 shapes, and a probe
outranks a histogram — which is why this is open rather than decided. But
§4.5 was demonstrably stale elsewhere (it still carried the superseded rate
law), so neither reading is safe.

**Programs 142 and 143.** Both request a **square** LFO2 at rate byte 100.
142 has it at byte 4 (what the writer does); 143 has it patched into byte 5
after writing. Everything else is identical.

### Q3 — does the panner's second wire sum with the first?

Panner `Src1` is HW-confirmed (§PANMOD — balance measured, wires spread).
`Src2`'s **offset** comes from the same confirmed diff but has **never been
driven**, so whether a second panner wire adds to the first is untested.

**Programs 144, 145, 146.** LFO1 pan alone; LFO2 pan alone; both together at
the same depth and rate.

---

## Predictions, filed before the run

Written here so the result cannot be read as whatever the data suggests
afterwards — the failure this project has already made under the name *a
theory that fits every point*.

| | prediction | what the alternative would mean |
|---|---|---|
| **Q1** | 136–141 match 130–135 pairwise in vibrato period | a **constant** ratio = shared shape, different scale; a ratio that **varies with byte** = LFO2 needs its own 185 rows |
| **Q2** | if §4.5 is right, 142 is a square-wave vibrato and 143 a sine | the reverse means the writer has been putting shape values into a phase field since it was written |
| **Q3** | 146 pans **deeper** than 144 or 145 alone | 146 == 144 means Src2 is inert or mis-addressed; 146 == 145 means Src1 was overwritten |

⚠ **A negative is a result.** If 136–141 produce no vibrato at all, that says
LFO2→Pitch does not reach `cal[26]` the way LFO1 does — worth more than a
ladder. **Program 147 (`NO MOD CTRL`) is what separates "LFO2 is silent" from
"the rig is silent"**, and it is the first thing to capture, not the last.

## Before the machine: what was already verified offline

Reading the written file back, not trusting the generator's exit code:

- LFO1 programs: `0x14[2]` = the requested byte, `cal[21] = 114`, depth ≠ 0.
- LFO2 programs: `0x15[2]` = the requested byte, `cal[26] = 116`,
  `MinDpt == MaxDpt`, `DptCtl = OFF`.
- 142: `0x15 = [100, 2, 1]`; 143: `0x15 = [100, 0, 2]`.
- 144: `F3 = [40, 114, 18, …]`; 145: `[40, 116, 18, …]`;
  146: `[40, 114, 18, 0, 18, 18, 116]`; 147: type 18, no panner.

**The first build of this bank had an all-zero panner on all three pan
programs** — `filter_type` was 1, and `_want_pan` requires algorithm 5 with a
2-pole lowpass, which only `filter_type` 2 produces. The generator printed 18
presets and a clean run. It was caught by reading the bytes back, and had it
reached the machine it would have measured *"the panner does nothing"* — the
identical failure `gen_krz_cutoffcal` shipped to hardware, where eleven
programs came back identical to four significant figures because the filter
was never in the signal path.

## Also worth grabbing while the bank is resident

Free, no extra setup, and neither side can do the other's half:

- **The F1 block's `DptCtl` (`seg[7]`).** Src1, Src2, MinDpt and MaxDpt are
  all read by `krz_parser` off real material; `seg[7]` is the one field of
  that block we infer from the panner's layout and never write. One panel
  read settles it.
- **`MxRate` (`0x15[3]`, and `0x14[3]`).** Same 0..184 rail, never written by
  us, law unmeasured. One panel read says whether the rail is shared.
- **`Globals` on the COMMON page.** The Musician's Guide says LFO2, ASR2,
  FUN2 and FUN4 become global together, and a **global LFO2 runs once for the
  whole layer instead of per note** — so a converted per-voice modulation
  would arrive phase-locked across the keyboard. We do not write that
  parameter and must not start without knowing where it is.
