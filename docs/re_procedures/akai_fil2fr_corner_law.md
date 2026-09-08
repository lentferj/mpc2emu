<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: the filter-2 corner law, `FIL2FR` → Hz (§AKAIFIL2FR)

## Goal

Measure `FIL2FR` → Hz for the IB-304F second filter. **This one measurement
gates both directions of the converter.**

Everything else about filter 2 is settled — the mode enum, the sign rule and its
crossing at `FLT2Q` ≈ 23.1, depths across every populated value, the notch at
16, the level-neutral `FLT2GAIN` switch, +22 dB headroom. **None of it is
usable without knowing where the filter sits.**

## Why filter 1's law cannot be reused

```
  our FILFRQ -> Hz law at byte 80   2503 Hz
  filter 2 measured at FIL2FR 80    ~2200 Hz (cut arm)     0.88x
```

**They do not share a law**, and one measured point is not a law.

## Both arms are mandatory

The measured centre **steps ~17 % across the sign change** — 2201 Hz on the cut
arm against 1884 Hz on the boost arm, at identical `FIL2FR` 80. So a law fitted
on one arm is ~20 % wrong on the other, and this sweep must cover both.

## Where the material sits

925 enabled keygroups place `FIL2FR` below fully-open. The ladder follows that
distribution rather than an even split:

| | |
|---|---|
| range | 0–98 |
| median | 64 |
| percentiles | p10 = 30, p25 = 45, p50 = 64, p75 = 80, p90 = 88 |

No strong clustering — broad and fairly even.

## The sweep

```
  cut arm,   FLT2Q 15    FIL2FR  30  45  64  80  95
  boost arm, FLT2Q 31    FIL2FR  30  45  64  80  95
```

`FLT2Q` **15 and 31** are the **sharpest non-singular** points on their arms
(638 Hz and 423 Hz wide). Sharp features locate best — the centre estimate
correlates with feature width at r = +0.826, so a wide, shallow feature has a
poorly located extremum.

**`FLT2Q` 16 is deliberately not used**, despite being sharpest of all: it is
the singular notch and may not share the topology of the ordinary dips around
it.

**Order so that stopping early still yields something:** 64 on both arms first
(anchors against the existing `FIL2FR` 80 point), then 30 and 95 (the ends fix
the shape), then 45 and 80.

**Two spot checks, if cheap:** `FIL2FR` 64 at `FLT2Q` **20** (cut) and **27**
(boost). If the centre matches its arm's law there, one law per arm covers
everything. If it does not, **the corner moves with `FLT2Q`** — a bigger finding
than the law itself.

## Traps

- **The search window must follow the feature.** At `FIL2FR` 30 the corner may
  sit near 200–400 Hz. A fixed search range reproduces the `FIL2FR` 20 failure
  from the first sweep, where the corner had left the analysis band entirely.
- **Raw-bin analysis, not octave bands.** Octave averaging under-read a notch by
  **49 dB** in the `FLT2Q` sweep — a fixed-width band cannot characterise a
  feature whose width is a free parameter.
- **`FIL2FR` 99 is excluded**: fully open shows no identifiable feature, and
  1,532 of 2,457 enabled keygroups sit there and need no corner.
- **`PRGNUM` 0 is never free** — the boot-resident `TEST PROGRAM` survives every
  memory clear.

## Then

With the law, both directions open:

- **read** (AKAI → E4B/KRZ): filter 2 decodes into the model — mode to filter
  type, `FLT2Q` to band-stop/band-boost by sign, `FIL2FR` to a corner.
- **write** (→ AKAI, **behind `--akai-ib304f`, never a default**): a 4-pole
  source LP becomes both filters at one corner; HP and BP become filter 2, which
  filter 1 cannot express at all; band-stop/boost becomes EQ mode with `FLT2Q`
  from the measured depth table.

The gate is not caution: **`LSI2_ON` reads back 1 on a machine with no board**,
so nothing on the wire tells the converter whether the hardware is there.
