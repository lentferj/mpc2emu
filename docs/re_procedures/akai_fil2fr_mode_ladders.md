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

**Plan the rungs so the plan does not depend on the factor being tested.**
That is the mistake this table made in its HP column and it is worth stating as
a rule, because the fix is cheap: give every rung its feature frequency under
**both** the constant-factor assumption and a pessimistic drift, and require it
to be measurable under the pessimistic one — since that is the case the ladder
exists to detect.

HP is the only mode with a ladder, so its own drift is the pessimistic model:
its factor fell to **0.55×** of its byte-74 value by byte 20, 0.72× by byte 30.

```
  rung   BP / EQcut, constant   with an HP-like drift   verdict
    20              44.5 Hz              24.3 Hz        SKIP -- under the rig's floor
    30              71.2                 51.0           ok
    37             114.7                 85.7           ok
    45             176.7                157.9           ok
    64             685.0                628.2           ok
    72            1190                  1100            ok
    80            2025                  1900            ok
    88            3427                  3250            ok
    94            9760                  9300            ok
```

**So BP and EQ start at rung 30, not 20.** Under the optimistic reading rung 20
looks fine at 44 Hz; under the pessimistic one it is 24 Hz, below where the rig
is verified flat. **A rung that is only measurable if the hypothesis is true
cannot test the hypothesis.**

**Sources** — by predicted feature frequency, taking the pessimistic column:

| rungs | feature | source |
|---|---|---|
| 30–64 | 50 Hz – 700 Hz | **`TC10 NOISE`** — continuous to 15 Hz |
| 72–80 | 1.1 – 2 kHz | either |
| 88–94 | 3 – 10 kHz | **`FLATCOMB`** — beats the noise by 5–11 dB above 4 kHz |

`FLATCOMB` must not be used below ~125 Hz: it is a comb whose teeth are wider
than the analysis bands there, measured at **+3.8 dB SNR at 22 Hz** and +9.1 at
44.

**Run EQ at two `FLT2Q` values, one per arm** — 20 (cut) and 27 (boost). Their
centres measured 8 % apart at one byte, and whether that gap is constant across
the range is exactly the same open question one level down.

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
