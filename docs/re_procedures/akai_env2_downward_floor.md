<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: where does a downward ENV2 sweep actually stop? (§AKAIENV2FLOOR)

## Goal

Measure the real floor of a **negative** ENV2 filter sweep on the S3000XL, and
retire or confirm `AKAI_ENV2_SWEEP_FLOOR_HZ = 100.0`.

## Why this is open

The constant's own comment says it is **almost certainly an artefact**, and
`akai_filfrq_to_hz` is deliberately unclamped down to **~7.6 Hz** — so the two
disagree by nearly four octaves.

That disagreement caused a real defect. The downward headroom
`log2(base/floor)` went **negative** for any corner under the floor, `min()`
selected it, and the leading minus turned a downward sweep into an **upward**
one: FILFRQ 20 at depth −20 returned **+1951 cents**, FILFRQ 0 returned
**+4460**, with the sign flipping at FILFRQ 36. Fixed 2026-09-08 by clamping
the headroom at zero — which means **every corner below 100 Hz now gets no
downward sweep at all.** Under-sweeping instead of inverting: wrong by degree
rather than by direction, and still wrong if the real floor is lower.

29.4 % of real keygroups on the library discs sit in the affected FILFRQ range.

## The experiment is inverted on purpose

**Do not start from a low corner and ask how much further down it goes.** At
FILFRQ 20 the filter is already shut and there is nothing left to measure — the
signal is gone before the question is asked.

**Start high and sweep down with increasing depth; find where descending
stops.** Measurable at every point, and it answers the question directly.

## THE TRAP THAT PRODUCED THE SUSPECT CONSTANT

The 100 Hz figure came from normalising **each curve to its own 60–120 Hz
level** before taking the −3 dB point. Once the corner drops below that band
the 0 dB reference sits **on the slope**, the whole curve slides with it, and
every setting reads the same corner — a floor that is an artefact of the
reference, not of the machine. It read 111.3 Hz identically for FILFRQ 0, 5,
10, 20 and 30, which is what a broken reference looks like.

> **Normalise against ONE FIXED reference captured with the filter wide open.
> Never per-curve.**

This single instruction decides whether the run is worth anything. A repeat of
the original mistake will reproduce the original number and look like
confirmation.

## Route: SysEx, no card crossing

`s3ked`'s probes (`probes/calibrate.py`, `probes/measure.py`) set FILFRQ and the
ENV2 depth directly. **This is the primary route.** The volume below is the
fallback and the whole-pipeline check.

## Material

`~/temp/HWCHK_ENV2/`, built by `tests/re_banks/build_hwcheck_akai_env2.py`
through `build_akai_volume`. Broadband noise source — a corner can only be
found where there is energy on both sides of it. ENV2 sustains at full so the
swept corner **sits** rather than passing through.

| requested | FILFRQ | base corner | ENV2 depth byte |
|---|---|---|---|
| 0 | 77 | 2013.8 Hz | 0 |
| −1200 ct | 77 | 2013.8 Hz | −4 |
| −2400 ct | 77 | 2013.8 Hz | −8 |
| −3600 ct | 77 | 2013.8 Hz | −12 |
| −4800 ct | 77 | 2013.8 Hz | −15 |
| −6000 ct | 77 | 2013.8 Hz | −19 |
| −7200 ct | 77 | 2013.8 Hz | −23 |

Base corner is ~4.3 octaves above 100 Hz and ~8 above 7.6 Hz, so the sweep has
room to descend through both candidates.

## Procedure

1. Capture the **fixed reference**: depth 0, filter wide open. This is the 0 dB
   denominator for every later curve. Capture it once and reuse it.
2. For each depth, hold a note long enough for ENV2 to reach and hold its
   sustain, and take the spectrum **during the held portion**.
3. Find the −3 dB corner **against the fixed reference from step 1**.
4. Plot corner against depth.

## What each outcome means

- **The corner keeps descending past 100 Hz** → the constant is an artefact,
  the fix's zero-clamp is under-sweeping, and the corner law's own bottom
  (~7.6 Hz) is the better bound. Re-base the headroom and expect every
  currently-bounded sweep to deepen.
- **The corner stops near 100 Hz** → the constant is real, the clamp is
  correct, and the two-instrument disagreement is resolved in its favour.
- **The corner stops somewhere else** → that value is the floor; record it with
  the measurement rather than reasoning from either existing number.
- **Every depth reads the same corner** → suspect the reference before
  believing it. That is exactly the artefact signature above.

## Traps

- **Fixed reference, never per-curve.** Stated twice on purpose.
- **A sine tells you nothing about a filter.** Broadband source only.
- **Measure during ENV2's held sustain**, not its attack — a corner in motion
  is not a corner.
- **Check the noise floor.** At deep settings the signal approaches it, and a
  corner "measured" in the floor is not a measurement. The rig floor is
  0.05 dB with a 0.3 dB threshold (§RIGNOISEFLOOR).

## Not established by this run

The **positive** side is a separate, unresolved nonlinearity and is
deliberately left alone. `AKAI_KEYFOLLOW_NEG_SCALE`'s 0.622-vs-96–103 %
disagreement is a different field and is not touched by this.
