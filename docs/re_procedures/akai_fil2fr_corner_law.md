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

## The premise this was first written on was wrong

A first version of this procedure said filter 2 does not share filter 1's law,
because *"our `FILFRQ` law gives 2503 Hz at byte 80 where filter 2 measures
~2200"*. **Both numbers were right and they name different quantities**
(s3ked, 2026-09-09):

```
  §54  law, fitted to the RESONANCE PEAK, at byte 80    1892.4 Hz
  our shipping law (§139, corner measured directly)     2502.7 Hz
                                                 ratio  1.323x
```

Our own writer already records this: *"§54 fitted this to the RESONANCE PEAK as
an indicator of the corner; their §139 measured the corner directly and the two
disagree by a constant 1.29x, which is open on their side."* **I compared
filter 2's EQ extremum against the corner law and called the mismatch a
property of filter 2.**

**Filter 2's EQ boost extremum matches the RESONANCE-PEAK law to 1.1 %:**

```
  boost-arm centre (FLT2Q 25..31, mean)  1872 Hz  vs §54's 1892   0.989x
```

which is like for like — an EQ boost peak *is* a resonance peak. **So filter 2
may share filter 1's frequency control exactly**, and there may be nothing to
measure beyond confirming it.

## And the "arm step" may be a quantity mismatch too

The ~17 % step was checked robustly against the width artefact, but the check
compared **the sharpest point on each arm** — and those are a **notch minimum**
(`FLT2Q` 16) against a **peak maximum** (`FLT2Q` 31). Those are not the same
quantity either, on an asymmetric response. **The step may be the same class of
error one level down**, which is why the primary ladder below is mode 0.

## Where the material sits

925 enabled keygroups place `FIL2FR` below fully-open. The ladder follows that
distribution rather than an even split:

| | |
|---|---|
| range | 0–98 |
| median | 64 |
| percentiles | p10 = 30, p25 = 45, p50 = 64, p75 = 80, p90 = 88 |

No strong clustering — broad and fairly even.

## The sweep — mode 0, one ladder

**Measure the LOWPASS −3 dB corner, not an EQ extremum.** It is unambiguous,
directly comparable to filter 1's shipping corner law, and free of **both**
artefacts the EQ arms carry — the width dependence and the peak/notch quantity
mismatch. Mode 0 has no sign and therefore no arms.

```
  FLT2MODE 0 (LP), FLT2Q 0     FIL2FR  30  45  64  72  80
```

**`FIL2FR` 95 was in the first version of this ladder and is now out.** It fails
for two independent reasons, and the first is the same trap one step further
downstream (found here, 2026-09-09):

```
  FIL2FR   §54 peak   §139 corner    ours   ours/§139   where ours comes from
      30       54.4         70.0     66.9       0.955   LAW
      45      157.7        203.2    198.2       0.976   LAW
      64      607.6        783.0    785.2       1.003   LAW
      80     1892.4       2438.5   2502.7       1.026   LAW
      95     5489.4       7073.7   8481.0       1.199   MEASURED TABLE
```

1. **95 is not on the law at all.** `AKAI_FILTER_LAW_TRUSTED_TO` is **80**;
   above it `akai_filfrq_to_hz` reads `AKAI_FILTER_MEASURED`, because §146 found
   filter 1's real corner runs **7–23 % above** its own exponential from 84 up.
   A `FIL2FR` 95 capture compared against "the law" would recover that
   filter-1 gap and **read as filter 2 differing from filter 1**. Same shape as
   comparing an EQ peak against a corner law: a documented discrepancy
   re-surfacing as a finding.
2. **95 is very likely unmeasurable.** `AKAI_FILTER_SATURATED` is **96** —
   at and above it filter 1 is indistinguishable from wide open — and §146
   already marks its own 90–94 points **marginal**. 95 sits past the last
   marginal point, one rung below the value where the machine stops
   distinguishing. It is the `FIL2FR` 20 failure at the other end of the range.

**All five points now sit inside 0–80, so all five compare against one
reference: the law.** The `ours/§139` column above says a constant-ratio §139
and our shipping law agree to 4.5 % across exactly that band, so either is a
valid comparand there — but not above it.

**The top of the range is a separate sweep, not part of this one.** If filter 2
needs corners at 84–94, they have to be *measured* into a filter-2 table the way
§146 measured filter 1's; no law check can supply them. Worth doing — p90 of the
corpus is 88 — but it answers a different question and is analysed against
`AKAI_FILTER_MEASURED`, never against the exponential.

Express the EQ centres as offsets from this afterwards, if they are still
wanted. The two-arm requirement was a consequence of the step, and the step is
now suspect.

**Predict the level before capturing, at the bottom of the ladder.** If filter 2
follows §54, byte 30 puts the corner near **54 Hz** and byte 45 near **158 Hz** —
and `FIL2FR` 30 would then sit close to the condition that made `FIL2FR` 20
unmeasurable in the first sweep. §RIGNOISEFLOOR says the rig is flat to 11 Hz
with 60–80 dB of headroom below 44 Hz, so it should be reachable, but that is a
prediction to check rather than assume.

**Order so that stopping early still yields something:** 64 first (it anchors
against the existing `FIL2FR` 80 point), then 30 and 80 (the ends fix the
shape), then 45 and 72. "Both arms" is gone with the arms — mode 0 has none.

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
