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

## Route: SysEx, and NO card crossing — the source is already on the disk

**Corrected twice, and this is the settled version (Jan, 2026-09-08).**

The first version said "no card crossing" and was wrong: `s3ked`'s probes set
*parameters on a resident program* and cannot supply a sample, while this
measurement needs a **broadband source** — a sine tells you nothing about a
filter.

The second version concluded a card crossing was therefore required. **Also
wrong, and the error was mine: I confused a card LOAD with a card SWAP.** The
HD4 card is already in the sampler's ZuluSCSI. Loading a volume from it is a
machine operation, not a physical exchange.

**And a suitable broadband source is already on that disk:**

```
  TC10 NOISE   NOISE WHT A.S3   176,400 samples = 4.0000 s @ 44.1 kHz
                                flat within 0.78 dB, 11 Hz to 11.3 kHz
               N50/N51          single-keygroup S3000 programs
```

Verified from the image, not assumed — the same check s3ked applied to the
purpose-built source, which this one beats (0.78 dB to 11 kHz against 0.9 dB to
5.6 kHz).

**So the whole measurement is: load `TC10 NOISE`, then SysEx parameter writes
and audio capture.** Single keygroup, so no layer interactions; S3000, so the
board offsets exist. `~/temp/HWCHK_ENV2/` remains as a whole-pipeline check but
is no longer the route.

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

**Steps are dense where the answer is.** A first version stepped
−4 −8 −12 −15 −19 −23 and jumped straight over the crossing: −15 is 136.9 Hz
and −19 is 66.8 Hz, so **one step spanned the 100 Hz candidate** and the run
could only ever have reported "somewhere between 67 and 137 Hz" — which does
not distinguish 100 from 80 or 120, a weak answer about a constant stated to
0.1 Hz. The crossing is now bracketed by **−16 (113.6 Hz)** and
**−17 (95.0 Hz)**, under 20 Hz apart, for the price of two captures.

**SUSTN2 must be read back on the machine and recorded beside every result.**
§156 makes the shift a **product** — `octaves = 0.002612 x SUSTN2 x depth` — so
this whole table is valid only at the sustain that actually landed. If the
machine's SUSTN2 differs, every corner in the plot is wrong by a constant factor
and **nothing in the output would show it.** The generator prints it (uniformly
99 here) for exactly that comparison.

*A near-miss worth keeping:* the first version of that readback printed byte
`0x17` under a "SUSTN2" heading. The writer assigns
`k[0x14..0x17] = attack, decay, sustain, release`, so `0x17` is RELSE2 — a real
value under a wrong label, and the corner column computed from it would have
been wrong with it.

## Procedure

1. Capture the **fixed reference**: depth 0, filter wide open. This is the 0 dB
   denominator for every later curve. Capture it once and reuse it.
2. For each depth, hold a note long enough for ENV2 to reach and hold its
   sustain, and take the spectrum **during the held portion**.
3. Find the −3 dB corner **against the fixed reference from step 1**.
4. Plot corner against depth.
5. **Record the searched cents beside each depth byte**, not only the byte. The
   writer's map is not linear — about 300 ct/unit at the top against 313 at the
   bottom — so anyone re-deriving it linearly lands where the first version of
   this plan landed, straight over the crossing. The generator prints both
   columns; carry both into the results.
6. **Record the SUSTN2 read back from the machine** beside every corner, for
   the reason in the material section.

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
- **Follow the corner with the analysis band; do not measure at a fixed high
  frequency.** At a 95 Hz corner a 4-pole is ~81 dB down at 1 kHz, which is the
  rig floor — a corner "found" up there is found in the noise. Measured around
  the expected corner a broadband source still has full energy density and the
  −3 dB point is a real feature. The generator prints a ±1.5-octave band per
  step for this.
- **The floor is a PRECONDITION, and it has been CHECKED — no depths need
  dropping.** s3ked measured the rig's own floor per band rather than inferring
  it, and it is flat to 11 Hz:

  | band (Hz) | 11–22 | 22–44 | 44–88 | 88–176 |
  |---|---|---|---|---|
  | floor (dB) | −32 | −35 | −25 | −26 |
  | typical SNR | +78 | +72 | +45 | +28 |

  **60–80 dB of headroom in the two bands below 44 Hz.** The chain — sampler
  output, interface, JACK — is not the limit here.

  And the source is genuinely flat, which was the remaining risk:
  `ENV2NZ.S3` measures **within 0.9 dB from 11 Hz to 5.6 kHz** (+36.5 to +37.9
  across every band). So at the deepest step, a 38.8 Hz corner, the
  ±1.5-octave band still carries full source energy over 45–78 dB of headroom.

  **The failure mode was the fixed high-frequency probe, not the deep
  settings.** −96 dB at 1 kHz is a real number; it is simply not the number the
  experiment depends on.

## Not established by this run

The **positive** side is a separate, unresolved nonlinearity and is
deliberately left alone. `AKAI_KEYFOLLOW_NEG_SCALE`'s 0.622-vs-96–103 %
disagreement is a different field and is not touched by this.
