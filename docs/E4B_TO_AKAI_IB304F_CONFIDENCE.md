<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Confidence table: E4B → AKAI S3000XL with the IB-304F filter board

**Scope:** one conversion path, `--format akai --akai-ib304f`, from an E4B
source. Everything below is about the **filter**; the rest of the path (samples,
keygroups, envelopes, tuning) has its own provenance elsewhere.

**As of 2026-09-11.** Corpus percentages are over **3168 active filter-2
keygroups** in the whole local AKAI corpus (64 images) — not a sample.

## Confidence classes

| class | means |
|---|---|
| **HW** | measured on the instrument, with conditions recorded |
| **HW-E2E** | measured end to end: our emitted file rendered on the machine |
| **DERIVED** | arithmetic over measured quantities, no new assumption |
| **DESIGN** | our modelling choice; defensible, not a measurement |
| **INTERPOLATED** | measured points either side, curve between them assumed |
| **UNMEASURED** | no evidence; the code says so at runtime |
| **KNOWN WRONG** | we ship it knowing it is the wrong quantity, and say so |

## Read side — E4B into the model

| element | basis | class |
|---|---|---|
| E4B filter byte → model `filter_type` | `_E4B_TO_XPM_FILTER_TYPE`, the source format's own enum | **DERIVED** |
| E4B cutoff byte → Hz | E4XT-measured −3 dB corner off a noise spectrum, 1/6-octave bands (§E4BFILTCAL) | **HW** |
| E4B resonance byte → model 0..1 | eosed's peak-dB sweep (§E4XTQCAL), replacing an uncalibrated linear guess | **HW** |

## The model's own definitions

| element | basis | class |
|---|---|---|
| `filter_cutoff` = the **−3 dB corner in Hz** | every source filling it measures a corner; **the K2000 does not**, and that conversion is deliberately pending | **DESIGN** |
| `filter_resonance` = peak dB above passband ÷ **25.51** | 25.51 is the AKAI's own maximum, `FILQ` 15, hardware-measured | **HW** |

## Write side — model into an AKAI program, board on

| element | span / value | class | corpus exposure |
|---|---|---|---|
| `filter_type` → `FLT2MODE` | mode enum measured from response shape; the *mapping* is ours | **HW** enum, **DESIGN** mapping | — |
| Filter 1 `FILFRQ` placement | §139 corner law to byte 80, measured table 84–94 | **HW** | — |
| Filter 2 tuning, LP mode | 9 measured points, `FIL2FR` **20–94** | **HW** | LP is 4.7 % of use |
| Filter 2 feature, HP | 5 points, `FIL2FR` **37–80** | **HW** | HP is **57.6 %** |
| Filter 2 feature, BP | 6 points, `FIL2FR` **30–80** | **HW** | BP is 3.5 % |
| Filter 2 feature, EQ cut / boost | 6 points each, `FIL2FR` **30–80**, separate tables per arm | **HW** | EQ is **34.2 %** |
| **non-LP feature outside 30–80** | extrapolated along the ladder's own exponent | **INTERPOLATED** | **16.4 %** |
| 4-pole cascade lift, ÷0.841 | measured pair corner; **verified end to end at 200/800/3000 Hz within 1.6 %** | **HW-E2E** | — |
| EQ depth, `FLT2Q` → dB | **all 32 values**, raw 1.465 Hz bins | **HW** | — |
| Resonance, `FLT2Q` → dB, LP and HP | 9 of 32 points; all three curves monotonic, so interpolation is safe here where the depth curve's was not | **INTERPOLATED** | **15.9 %** |
| Resonance, BP | borrows the HP curve — **a different filter order**, 1-pole against a 1-pole pair | **KNOWN WRONG** | 3.5 % |
| Pole counts: LP 2, HP **1**, BP 1+1 | far-band asymptotes measured at `FLT2Q` 0 **and** 31, unchanged | **HW** | — |
| `LSI2_ON` gating behind `--akai-ib304f` | `LSI2_ON` reads back 1 with no board, so nothing on the wire can decide it | **DESIGN**, necessity **HW** | — |
| Board released when both filters end open | ours; regression-tested | **DESIGN** | 1 preset in 6 of real material |
| Feature offset at arbitrary `FLT2Q` | **nothing models it**; `AKAI_FIL2FR_FEATURE_OFFSET_UNMODELLED` is emitted | **UNMEASURED** | all non-LP use |
| `FIL2FR` 95–98 | between a real 5.9 kHz corner at 94 and a measured bypass at 99 | **UNMEASURED** | 0.3 % |

## End to end

| claim | basis | class |
|---|---|---|
| Our emitted programs load and render on a board-fitted S3000XL | `FILTER2` volume, 12 programs, all four modes, gate confirmed by a withheld-board twin | **HW-E2E** |
| `--iso` delivers the same bytes as a disk image | 12 program headers diffed, **3720 bytes, zero differences** | **HW-E2E** |
| **A real E4B conversion sounds like its source** | `FXPATHS`, six A/B pairs on HD4 against the same six presets in E4XT RAM at P000–P005 | **PENDING — this is the open question** |

## The three things most worth knowing

**1. The biggest gap is not the smallest number.** `FIL2FR` 95–98 is 0.3 % and
gets a warning; **the non-LP feature outside 30–80 is 16.4 %** and gets the same
warning. Both are honest, neither is equally important.

**2. Highpass carries the most weight and the least margin.** It is **57.6 %** of
board use, its feature table is the narrowest of the four (37–80, five points),
and its pole count was wrong in this converter until 2026-09-10.

**3. One row is knowingly wrong.** Bandpass resonance borrows the highpass
curve, and the two taps are different filter orders. It affects 3.5 % of
material, and the fix is a modelling decision about what "bandpass resonance"
should mean rather than a measurement.
