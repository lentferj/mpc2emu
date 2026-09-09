<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: a `FIL2FR` ladder per `FLT2MODE` (§AKAIFIL2)

## Why this is the top ask

**Every point of the `FIL2FR` corner law was measured in mode 0**, which is
**7 %** of how the IB-304F is actually used in real library material. EQ is
50 % and HP 39 %. So 89 % of board use has its frequency placed by a law
measured on a different mode.

Hardware says that matters. Measured at `FIL2FR` 74, as ratios to the mode-0
law at the same byte:

| mode | feature | factor |
|---|---|---|
| HP | −3 dB corner | **0.688 ×** |
| BP | peak | **1.653 ×** |
| EQ cut (`FLT2Q` 20) | dip | **1.653 ×** |
| EQ boost (`FLT2Q` 27) | peak | **1.515 ×** |

**Those factors are recorded and deliberately not applied**, because each rests
on a single byte out of 0–99. This ladder is what would earn the right to apply
them — or replace them with something byte-dependent.

## What the ladder tests, stated as a falsifier

**Prediction: each factor is constant across the range**, so measured feature
frequency ÷ mode-0 law stays within ±10 % of the table above at every rung.

**Falsified if the ratio drifts monotonically with rung.** That is the specific
shape to look for and it is not hypothetical: the mode-0 law itself turned out
to have three regions, and a single exponential fitted through them was
falsified by its own extension (§AKAIFIL2FR).

**Report the ratio per rung, not a mean.** A mean over the range answers a
question about the range and is least able to show its endpoints — which is
exactly how filter 1's law survived being 23 % wrong at its own top for months.

## The rungs, and which source to use at each

Same rungs as the mode-0 ladder so the results are directly comparable. The
predicted feature frequency decides the source, because **the two volumes on
the card fail at opposite ends**:

```
  rung    BP / EQcut Hz  src        EQboost Hz  src
    20              44   noise              41  noise
    30              71   noise              65  noise
    37             115   noise             105  noise
    45             177   noise             162  noise
    64             685   either            628  either
    72            1190   either           1091  either
    80            2025   FLATCOMB         1856  either
    88            3427   FLATCOMB         3141  FLATCOMB
    94            9760   FLATCOMB         8945  FLATCOMB
```

**THE HP LADDER IS DONE (2026-09-09) AND ITS COLUMN HERE WAS WRONG.** This
table originally carried an HP column built from the single-byte factor 0.688,
which put rung 30 at 30 Hz. The measured HP curve puts it at **~21 Hz** — 18 %
lower, and as marginal as the rung 20 this procedure had already skipped.
s3ked got no crossing at rung 30 and correctly reported no number rather than
one.

**So the table above is the same mistake it warns about, one level up:** the
source was chosen per rung from a *predicted* feature frequency, and the
prediction came from a factor that the ladder then falsified. **A planning
table built on an unverified constant inherits its error** — and the visible
symptom was a rung that could not be measured, not a wrong answer, which is the
lucky direction.

The remaining BP and EQ columns rest on the same kind of single-byte factor
(1.653 and 1.515) and should be treated as provisional in exactly the same way.
**Expect the lowest one or two rungs of each to be unmeasurable rather than
merely awkward.**

- **`TC10 NOISE`** is continuous to 15 Hz. **Use it below ~300 Hz.**
- **`FLATCOMB`** is a comb whose teeth are further apart than the analysis
  bands below ~125 Hz — measured SNR **+3.8 dB at 22 Hz, +9.1 at 44** — and it
  beats the noise by 5–11 dB at 4–10 kHz. **Use it above ~2 kHz.**
- **HP rung 20 is skipped**: 19 Hz leaves no room beneath the rig's verified-flat
  11 Hz.

## The reference side is not the same in all three modes

**This flips which rungs are hard, and getting it backwards costs a whole
ladder.**

- **HP** — the passband is **above** the corner. Low corners are therefore
  *easy*, not hard, and the binding constraint is the source having energy AT
  the feature rather than a reference beneath it.
- **BP** — baseline either side of the peak; needs room on both.
- **EQ** — the baseline is everywhere else on the spectrum, which makes it the
  most forgiving of the three.

## Traps, all of them paid for already

- **Derive the analysis band from the data; never choose it.** Five wrong passes
  in one evening on the mode-0 disc, every one from a chosen band: a passband
  where the source has no energy, a corner search below that passband, harmonic
  sampling on an assumed root, a slope interpolated onto the noise floor, and a
  low-corner passband that moved the answer by **27 %**.
- **Raw bins, not octave bands.** Octave averaging under-read a notch by
  **49 dB**. `FLT2Q` is a width control and a fixed-width band cannot
  characterise a feature whose width is a free parameter.
- **A slope survives what a corner does not.** A slope is a difference between
  two points, so the normalisation constant cancels exactly; a corner is an
  absolute crossing against a reference and inherits every defect in it. When a
  reference is later retracted, the slopes stand and the corners do not.
- **Reference to an unfiltered control on the same disc**, not to a passband
  median. `FILTER2` program 40 exists for this. On the mode-0 disc it took
  three wrong passes to reach it, because the control shipped without a note
  saying it was the reference.
- **Confirm which volume and which id you loaded** rather than assuming.
  `FILTER2` exists byte-identically on two transports, so a load from the wrong
  one produces a perfect match and reads as a pass.
- **Exclude program header offset `0x6d`** from any header comparison: it is the
  last-played MIDI note, so two dumps of one program differ unless nothing has
  been played between them.

## No card needed

`FLT2MODE`, `FIL2FR`, `FLT2Q` and `LSI2_ON` are all writable over SysEx, which
is how the mode-0 ladder and the whole `FLT2Q` table were taken. Both sources
are already resident on the card. **`PRGNUM` 0 is never free** — the
boot-resident `TEST PROGRAM` survives every memory clear.
