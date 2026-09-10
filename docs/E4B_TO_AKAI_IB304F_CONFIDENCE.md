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
| The board does not engage when nothing asks it to | `40`/`50` measured null: **0.10 dB rms against a 0.10 dB repeatability floor** | **HW-E2E**, and see the narrowing below |

### What the `FX`/`NB` pairs can and cannot answer — corrected 2026-09-11

**They were described here and to s3ked as *"the same program with the board
off — same samples, same keygroups, one flag"*. That is false, and it cost four
captures.** Measured from the volume's own headers:

```
   pair         FX FILFRQ                  NB FILFRQ
   AIR HEED     99,99,99,99,99,99          89,67,67,77,80,89
   SYNTH BAS    99                         39
   OBX BP SW    99,99,99,99,99             39,39,39,39,39
   REZ PLAY     42,42,42,42,42,99,99,99    39,39,39,39,39,39,39,39
   MYSTERY M    42,42,42,42,42,99,99,99    39,39,39,39,39,69,69,69
```

**Three parameters differ, not one.** When the board is engaged for a non-lowpass
shape the writer opens filter 1 (`FILFRQ` 99) and lets filter 2 carry the band;
with the board withheld it must re-tune filter 1 instead — **and it also changes
key-follow and velocity depth**:

```
   FX AIR HEED   K_FREQ 0     velocity->filter 0
   NB AIR HEED   K_FREQ 0     velocity->filter 7      <- the corner moves with velocity
   FX OBX BP SW  K_FREQ 0     NB OBX BP SW  K_FREQ 1  <- and with key
```

**This is correct behaviour and a correct fallback.** For the question the volume
was built for — *does the conversion sound right with the board, and acceptable
without it* — re-tuning filter 1 is exactly what should happen. **What it is not
is a single-variable control**, so `FX − NB` is not filter 2's contribution and
no pole count can be read from it.

**And the `40`/`50` null means something narrower than it appeared.** It is null
because that source's filter was already wide open, so the writer had nothing to
approximate and both renderings coincided. *"The board does not engage unasked"*
holds. *"Only the flag differs"* was never true of any pair where the board does
something.

**Isolating filter 2 needs a RAM-only A/B on program `44`** — the only one of the
six without two filter modes layered on every note — clearing `LSI2_ON` alone and
leaving filter 1 untouched.

### And nothing has been measured across key or velocity

Every capture so far is **one note at one velocity**. These programs span
**5.6 to 7.0 octaves**, carry key-follow on some keygroups and not others, and
differ between `FX` and `NB` in velocity depth. **A single point cannot
characterise any of that**, and comparing two programs at one point compares two
surfaces at one point.

**The honest minimum is a grid on both sides** — the E4XT source and the AKAI
conversion, five octaves by five velocities — and neither side has had one.


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
