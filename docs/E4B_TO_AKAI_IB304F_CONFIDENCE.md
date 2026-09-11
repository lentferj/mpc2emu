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

### The key/velocity grid — CAPTURED on both sides 2026-09-11, not yet scored

Until 2026-09-11 every capture was **one note at one velocity**, against
programs spanning **5.6 to 7.0 octaves** with key-follow on some keygroups and
not others. A single point cannot characterise that, and comparing two programs
at one point compares two surfaces at one point.

**Both grids now exist** — six presets, five notes (24/38/52/65/79), five
velocities (16/48/80/104/127), on the E4XT (`eosed`) and on our AKAI conversion
of the same material (`s3ked-47`), plus a repeat pass at velocity 80 on both
sides so every cell has a measured floor. **They are not yet scored**, because
the campaign turned up four method problems that had to be settled first, and
each of them would have produced confident wrong numbers.

**AND CROSS-MACHINE, IT COVERS THREE PRESETS, NOT SIX.** The AKAI volume was
built by a bench script that bypassed the playback-rate snap `convert.py`
performs, so **three of the six presets played sharp** — by **+210, +786 and
+831 cents** — and those cells were comparing different pitches, not different
conversions. Confirmed from both machines independently to within 2 cents of the
shift predicted from the stored sample rates. **Not a converter fault:** the
writer warns, naming the fault and its size in cents, and the script had
suppressed its stdout for tidy output. See `TODO.md` and
`RESOLUTION_NOTES.md` §AKAIRATESNAP; a corrected volume exists and needs a card
crossing.

**What survives:** P000, P001 and P002 cross-machine (shifts of 0, +2 and +4
cents). **All** within-machine repeatability — both passes of a repeat pair play
the same shifted sample on the same machine, so every floor is a real floor —
and the three mechanism refutations that rest on it. **The preset that had been
serving as the stable reference pair is one of the three shifted ones**, and it
looked clean all night because nothing else about it was unusual.


## How the grid is scored, and why each rule is what it is

Settled 2026-09-11 with `eosed`. These are methodological decisions with dates
and reasons, not details.

**Floors are per cell — preset × note × band — never per preset.** One preset's
repeatability varied **13×** with window position, and within one preset at
matched level the spread ran 0.283 to 1.194 dB across five notes. A single noise
floor for the matrix would be wrong in at least three distinct ways:
analysis-path noise, level-dependent noise in bands below about −40 dB, and
per-preset instability nobody has explained.

**Exclusion is level-relative, not frequency-relative.** Bands more than ~12 dB
below *that note's own peak band* are indeterminate. The effect first read as
"confined to low frequency" and was confined to **low level** — for a note whose
fundamental is 349 Hz, the 20–80 Hz bands sit ~40 dB down, and *low frequency*
and *low level* were confounded in every earlier statement about it.

**`indeterminate` is a verdict, printed as such, never folded into
`agreeing`.** A cell whose floor exceeds its residual cannot fail, and **a cell
that cannot fail must not be allowed to pass.**

**The verdict uses the median floor; the max is printed beside it.** Where a
cell's max floor exceeds its residual but its median does not, the stricter
reading wins — the window was chosen by a rule that does not optimise the max.

**Windows are chosen by within-pass spectral drift, not by level tilt and not by
repeat-pair difference.** All three were tried:

| rule | quantity | independent of the floor? | tracks what the residual sees? |
|------|----------|---------------------------|-------------------------------|
| level tilt | smoothed level envelope, within pass | yes | **no** |
| repeat-pair | spectrum, across passes | **no** | yes |
| **drift (adopted)** | spectrum, within one pass | yes | yes |

Level tilt can be flat while the spectrum moves as fast as a filter sweeps, and
on one preset it selected that preset's **worst** available window. Repeat-pair
selection was rejected because **the repeat pair is the floor** — minimising it
over ~20 candidate windows biases the floor downward and systematically
overstates significance, which would make the matrix manufacture conversion
findings.

**Drift scores rank windows; they are not floors and must not be printed next to
residuals.** One preset scores 13.62 dB of within-window drift and repeats to
0.056 dB, because **a deterministic sweep produces large drift and repeats
perfectly.** Drift predicts poor repeatability only in combination with timing
jitter (±5 ms here).

**In honesty about how much the drift rule bought:** it fixes the one preset the
diagnosis was about (0.971 → 0.119 dB median) and changes every other preset by
≤0.023 dB, at or below the repeat noise. It is adopted for its independence from
the floor, not on a claim of general superiority. The two rules disagree on all
six presets, so **no window in this campaign was robust to the selection rule.**

**Floors from one repeat pair are labelled differently from floors from ten.** A
one-pair floor understates spread, so cells carrying one pass more easily than
they should. Two presets have ten pairs; four have one.


## The decay leg: a measured difference with no mechanism

Measured 2026-09-11 on five comparable presets, both sides anchored to each
machine's own measured peak, converted to **rate** because both machines are rate
machines on decay (E4XT slopes −5.75/−5.73/−4.50/−4.68 dB/s across successive
intervals; AKAI r² 0.99998):

| preset | E4XT dB/s | AKAI dB/s | E4XT/AKAI | `DECAY1` shortfall predicted |
|---|---|---|---|---|
| P001 | 5.28 | 0.87 | **6.07×** | 2.58 |
| P002 | 5.80 | 2.03 | 2.86× | 1.06 |
| P003 | 16.87 | 10.97 | 1.54× | 1.24 |
| P004 | 13.80 | 5.15 | 2.68× | **1.00** (no decay stage) |
| P005 | 7.58 | 4.08 | 1.86× | **1.00** (no decay stage) |

**The AKAI decays SLOWER on every preset, by 1.54× to 6.07× in rate.** Saturation
predicts it *faster*, by the shortfall factor. **The sign is wrong before any
magnitude is considered.**

**The single cleanest refutation needs no model at all: P004 diverges 2.68× on a
preset whose envelope does nothing.** With a flat envelope on both machines and
the pitch now correct, a 2.68× difference cannot be an envelope difference.

**A correlation exists and is not taken.** Shortfall against ratio gives Pearson
+0.916 on five points — and **−0.597** with P001 removed. One preset extreme on
both axes, and a magnitude agreement cannot rescue a prediction pointing the other
way.

**Mechanisms eliminated from the files, none replacing it:** per-voice attack
differences, envelope key-follow (the format has two such fields, neither on
envelope 1, and the one that exists measured inert), sample identity, pitch-scaled
sample decay (a 24× range across notes, r ≈ 0), loop preservation, ping-pong loop
mode (EOS has none), finite loop repeat count (we write 9999 = hold, verified on
the card) and playback type (reads "loop in release" on every sample).

**So the honest state of the decay leg is: a large, same-sign, reproducible
difference with no explanation.** That is recorded as a finding rather than a gap.

### Two cell-level cautions that come with those numbers

**Loop entry falls inside the hold at a note-dependent time**, spanning a factor of
~500 because it is `loop_start / (rate × playback)`:

```
  P004   n24 12.688 s (never)   n38 5.652   n52 2.518   n65 1.871   n79 1.545
  P005   n24  6.292 s (never)   n38 2.803   n52 1.998   n65 2.090   n79 1.165
  P001   n24  0.628 s           n38 0.280   n52 0.125   n65 0.059   n79 0.026
```

A window straddling entry measures a **blend** of pre-loop decay and post-loop
steady level, not a rate. Both machines enter at the same time, so this is not the
between-machine difference — but affected cells are marked rather than averaged
over.

**Corroborated from the E4XT audio, and its detectability is preset-dependent in
the way that matters.** Local slope change over ±0.35 s at the predicted entry
time, scored against the same statistic computed at every other time in the same
note as a null — because these envelopes swing anyway, and a first pass gave
changes of +14, −20 and −79 dB/s that looked decisive and were not:

| preset | note | change at entry | median elsewhere | percentile |
|---|---|---|---|---|
| P004 | 52 | 14.17 | 5.08 | 88% |
| P004 | 65 | 20.47 | 7.97 | 91% |
| P004 | 79 | 78.70 | 18.15 | **100%** |
| P005 | 38 | 1.19 | 7.44 | 10% |
| P005 | 52 | 24.22 | 14.56 | 76% |
| P005 | 65 | 10.27 | 9.34 | 54% |
| P005 | 79 | 19.41 | 11.46 | 75% |

**On the single-layer preset the predicted time is at the 88th, 91st and 100th
percentile of that note's own distribution. On the two-layer modulated preset it is
not** — one lands at the 10th, flatter than typical.

So the confound is real and **buried in the modulation on exactly the presets that
need checking most.** That is why the rule is *mark the cells from the file-side
prediction*, not *verify each one from the audio*: verification is unavailable
where it would matter. Held as **corroboration rather than independent
confirmation** — the file said where to look, and the null is computed from the
same capture the signal is in, so the percentiles are not independent draws.

**Two of five presets are non-monotonic on both machines** (P001 and P005, the two
two-layer presets), so those trajectories are partly measuring modulation phase.

**And divergence in dB ranks the presets differently from divergence as a fraction
of the E4XT fall** — 3.50–8.65 dB with P004 largest, against 35–84% with P001
largest and P003 smallest. **Both columns are reported per cell** rather than one
chosen: dB is the unit the conversion's laws are in, the fraction is what a
listener hears relative to the sound's own level, and the matrix is not the place
to settle that silently.


## The per-cell matrix is NOT published, and why

Filed 2026-09-11 rather than left as an absence. The per-cell table was built and
**held**, because the level offset between the two machines varies from **+0.29 to
+40.22 dB across cells, with one cell negative** — and a recording-chain gain
difference is a constant. Something upstream of the residual is wrong.

**It is not the conversion's level handling**, which was measured against the
source files at **0.2 dB across all six presets**. And it is not either
explanation proposed:

- **Window landing at different envelope phases.** The right size, the wrong
  places. `pickwin`'s gap is one number *per preset*, and **within P004 the offset
  runs +40.22 dB at note 24 against +4.16 dB at note 79** — 10× on one preset with
  one gap. Across presets `rate × gap` predicts 15.8 dB for P001 (measured 0.29)
  and 0 for P005 (measured −11.25).
- **Loop entry falling inside the window.** Matches within P004 exactly — the
  never-looping note gives 40.22 dB, the note looping at 1.545 s gives 4.16 — but
  the looped cells span 0.29 to 32.14 dB and `r = +0.577` on n=8. A hint, not a
  mechanism.

### What the offset IS good for: a verdict flag

**A large level offset means the two windows are not at comparable envelope
positions — so that cell's SHAPE number is not a timbre comparison either.** It is
not a nuisance to separate out and discard; it is evidence about whether the cell
compares the same moment of the sound at all.

```
  |level offset| > 2.0 dB  ->  INDETERMINATE, whatever the shape number says
```

**Threshold set from measurement, not from the table:** per-preset level accuracy
is 0.2 dB and the worst repeat floor is 1.6 dB, so an offset beyond ~2 dB cannot be
level conversion. On the eight cells available it marks six indeterminate.

### The band cut was wrong too, and the tell was visible

The **−12 dB** level-relative cut leaves **5 usable bands of 58**. It came from
repeatability work and was borrowed into a cross-machine spectral comparison —
the same shape as a ladder written as a standalone result becoming a reference.
**It should be −50 dB**, on s3ked's grounds: every repeat difference above 0.5 dB
sits more than 34 dB down and every band within 20 dB repeats to ≤0.22 dB, which
is two clean populations rather than one gradient. At −30 dB the usable count goes
5 → 16.

**5 of 58 should have stopped the table before the level offsets did.**

### What the level offset probably IS: the filter

Three facts from the files, the third decisive.

**1. The corners are fixed at 133–164 Hz and the grid's fundamentals span 33 →
784 Hz.** Identical on all three swinging presets:

| note | fund | E4B cutoff | oct past | AKAI filter 1 | oct past |
|---|---|---|---|---|---|
| 24 | 33 Hz | 133 Hz | **−2.02** | 159 Hz | −2.29 |
| 52 | 165 | 133 | +0.31 | 159 | +0.05 |
| 79 | 784 | 133 | **+2.56** | 159 | +2.30 |

**The note crosses the corner between 52 and 65.** Below it the filter is
irrelevant; above it the filter dominates. The filter's contribution to broadband
level therefore varies across the grid by **4.6 octaves of relative position** —
over 100 dB of range at 24 dB/oct.

**2. So a CONSTANT corner error produces a NOTE-DEPENDENT level difference.**
159 Hz against 133 Hz is 0.26 octaves. Worth nothing in the passband, worth the
slope times the offset in the stopband: **~0 dB at note 24 and ~6 dB at note 79,
from one constant.**

**3. And the filter sweeps 3–7 octaves during the note.** `filter_env_cents`
3707 / 4754 / 8316 over decays of 3.24 / 5.51 / 6.13 s. **The corner moves through
the fundamental while the window sits on it**, so a small difference in sweep rate
or depth becomes tens of dB — and a different number at every note, because the
fundamental being swept past differs.

**That accounts for all four things that defeated the measurement:** the 30 dB
magnitudes, the note-dependence within one preset, the sign reversals (the sweep
crosses the fundamental in different directions at different notes), and why
per-machine window anchoring did not help — **the level is a function of where the
filter is, and the filter is moving.**

### So the conclusion is "not on this material", which is more useful

A band residual needs the filter to **shape the spectrum without dominating the
broadband level**. These six presets have their corner 2+ octaves below most of the
grid with a 3–7 octave sweep in flight, so the quantity being measured swamps the
quantity used to normalise. **That is a material-selection failure**: the presets
were chosen for filter-shape coverage without checking where their corners sat
relative to the test notes.

**For the next campaign, specifically:** choose material whose corner sits **near
or above** the grid's fundamentals, and whose filter envelope is **shallow or
finished** before the analysis window.

**Honesty note.** Facts 1–3 are read straight from the files and the arithmetic
follows. **The preset-by-preset split is partly post-hoc** — the three swinging
presets have sweeps in flight during their windows (3.24–6.13 s) while P002's is
finished (0.04 s) and P001's has barely begun (7.29 s), but **P000's 1.92 s sweep
should be in flight and it shows a constant offset**; it fits only once you note its
window sits at 4.75 s, by which time its sweep is done. That explanation was found
after seeing which presets misbehaved.

### Next step, and it is free

Anchor each cell's window to **that machine's own envelope**, as was done for the
decay statistic. If the offsets collapse to a constant, the offset was window
phase and the shape column becomes meaningful. If they do not, the matrix is
published with most cells **indeterminate** and the reason stated — which is still
the answer to the question, just a sparser one than hoped.


## Provisional: the two sides were built from different sources

**This is one shared assumption under every cell, not a per-cell uncertainty,
and it does not average out.**

The AKAI volume was built from extracts of **`HD0-20260514.img.lzo`, a backup
from 14 May**. The E4XT side was loaded through the front panel from **live HD0
on 2026-09-11**. If any of the four source banks was edited in between, the two
machines played **different material**, and the residual method's premise — same
material, so the material's own structure cancels — fails. **The failure
direction is the bad one:** it appears as a per-preset conversion error that does
not exist, spectrally arbitrary, so it resembles a genuine hard-to-explain
residual rather than a level offset or a filter difference.

**Closed 2026-09-11 across the volume field**, on all six presets and in both
field families: per-zone values on the four multi-zone presets and the voice
field on the five single-zone voices, all fitting one units factor (127/96).
**Closed across the remaining sound-determining fields** by reading them off the
device against a table generated from the backup — filter type, cutoff,
resonance, keytrack, both envelopes, velocity→filter and →volume, zone key and
velocity ranges, root key, tuning, pan, sample names. **A field that cannot
affect a capture cannot manufacture a residual**, so that set closes the risk
that matters.

**Not closed as identity.** One matching field set is evidence, not proof: a
replaced sample or an edited key range outside the compared set reads clean. The
proper close is a byte-for-byte diff of the four banks against live HD0, which
needs a card crossing. See `TODO.md` §E4BSOURCEID.


### A separate finding the grid produced, larger than anything it was scoring

**Our decay times saturate, by up to 5.9x — and that does NOT explain the
envelope difference.** The attribution was withdrawn 2026-09-11 against its own
filed criterion: anchored to each note's own peak, the AKAI decays **less** than
the E4XT by ~4 dB over 1 s on both tested presets, where the prediction was
*more* by 0.9 dB — and the control preset, predicted to show 9% of the test
preset's divergence, showed 85%. A near-common offset on two presets whose
shortfalls differ 2.4-fold is not the shape saturation makes. Five candidate
mechanisms for the residual were then eliminated from the files (per-voice
attacks, envelope key-follow, sample identity, pitch-scaled sample decay, loop
state) and **no replacement is offered**. The saturation measurement itself is
read from files and stands.

The point in a 6 s hold where each
machine's output is flattest differs by **1 to 3.5 seconds on five of six
presets** — and the cause is largely ours: `DECAY1` is an 0..99 field, the four
presets with a genuine decay stage all wanted **more** than 99 (117.2, 108.7,
101.2, 99.6), and the resulting shortfall — 5.93x, 2.58x, 1.24x, 1.06x too fast
— **orders those five gaps exactly**. The two presets whose envelopes agree best
are the two with no decay stage at all.

**CUT DOWN TWICE on 2026-09-11, and the second cut is the serious one.** First,
three of the six presets were pitch-shifted by a bench-script fault, so only
three were comparable cross-machine at all. Then the "gap" turned out to be a
difference of **argmins** — each machine's own flattest window — and **an argmin
is only meaningful if it is separated from its alternatives**. Measured: only
**two of six presets have a well-identified flattest window on both sides**. For
the other four, at least one machine's argmin is drawn from a set of candidates
spanning 1.0–1.5 s, so a gap of that order is indistinguishable from noise.
**Five `ENVELOPE FINDING` flags were reported; two survive.**

So the ordering now rests on **two usable points** — 2.58× → 3.00 s and 1.06× →
1.00 s, which still order correctly — and the largest point (5.93× → 3.50 s) is
**both** argmin-unidentified over 1.25 s **and** confounded by a −8936 cent
filter envelope. It is the weakest, not the strongest.

The candidate-set threshold (within 10% of best) is a judgement, not a test:
there is no measured noise figure for the tilt statistic, so the verdicts are a
ranking. The honest form is best-versus-second directly.

**The replacement statistic has no argmin in it:** compare the two machines'
**onset-aligned level trajectories over the decay phase**, which is where
`DECAY1` acts and where they can actually differ. It also works on the
flat-landscape presets where the gap statistic cannot.

**One distinction worth keeping, because it bounds the damage:** an unidentified
argmin is **harmless for the residual** and **fatal for the envelope gap**. The
residual applies *one* window to *both* machines, so a flat landscape means the
choice barely matters; the gap is the distance between each side's *own* argmin,
which is exactly what a flat landscape destroys. The distributed windows stand;
the gaps do not.
**A target limit, not a defect** — the field has no range left — and the writer
now says so (`AKAI_DECAY1_SATURATED`). The filter path is now HW-verified in
both directions; the **envelope** rows in this document have never been better
than DERIVED. A disagreement of that size in where the output settles is more
audible than any corner-frequency error here. It was found as a by-product by a
tool written to choose analysis windows, so it has had none of the scrutiny the
intended measurement got and needs its own verification pass. `TODO.md`
§E4XTAKAIENV.


## Structural limits — things no setting can fix

Distinct from the measurement gaps above: these are places where the two machines
differ in a way our format cannot express, so they are not defects to be fixed and
not errors to be reduced.

**Attack SHAPE cannot be carried, only attack TIME.** Measured 2026-09-11 on both
machines:

| machine | t50/t90 | shape |
|---|---|---|
| AKAI S3000XL | 0.500–0.558 over `ATTAK1` 70–99 | **linear in amplitude** (0.556 predicted) |
| E-MU E4XT | **0.765**, five notes, spread 0.079 | **convex** — slow start, accelerating |

Our conversion carries a **time**. Matching it makes the endpoints agree and
leaves the middle of the rise different, which is audible. Stated from measured
points rather than a fitted exponent — E4XT medians `t10` 0.846 s, `t50` 1.712 s,
`t90` 2.214 s, against a linear ramp reaching the same `t90`:

- **3.4× slower to 10%** of level (0.846 s against 0.246 s);
- **1.39× slower to half** (1.712 s against 1.230 s);
- half level arrives **0.48 s late**.

**No `ATTAK1` value can fix this**, because the field sets a rate and the
difference is in the curve.

*(An earlier version of this row read 0.797 and "≈ t^2.6", taken from a
quarter-second table on one note — and that note is the lowest of the five at
0.701. Corrected to the five-note median. The conclusion is unchanged and better
supported: 0.765 against 0.556 and 0.301, convex on every note, spread 0.079.)*

It also explains a measurement artefact that looked like a defect: on the E4XT's
convex rise, threshold-crossing and argmax detectors differ by **1.69×** on one
capture (2.28 s against 3.85 s), both stable. On a straight ramp they agree. **The
detector disagreement is the curvature, reported in the units of two
conventions** — which is why "attack time" is a convention on the E4XT and close
to a property on the AKAI.

**The AKAI has no envelope-1 key-follow.** The format carries exactly two
key-follow fields, `K_FRQ2` and `K_DAR3`; neither touches envelope 1, and
`K_DAR3` measured inert (spread 1.02×). So a key-dependent amp envelope cannot be
expressed, and a measured 941 ms of note-dependence in AKAI `t_peak` against
0.16–0.24 s on the E4XT has no parameter in our control.

**`DECAY1` has no range left at the slow end.** 9.9% of 666 corpus voices saturate
at the byte ceiling; the worst wants 24.7 units beyond it, an 11.2× shortfall.
Every source slower than `DECAY1` 99 decays alike. Reported as
`AKAI_DECAY1_SATURATED` rather than corrected, because there is nothing to
correct it with.


## The four things most worth knowing

**1. The filter path is the measured part; the envelope path is not, and the
envelope disagreement is larger.** Everything below concerns filter behaviour,
which is now hardware-verified in both directions. The two machines' envelopes
are **1 to 3.5 seconds apart** in where their output settles, on five of six
presets, and those rows have never been better than DERIVED. **A reader who
takes this document's care about corner frequencies as the measure of the
conversion's fidelity will have the proportions backwards.**

**2. The biggest gap is not the smallest number.** `FIL2FR` 95–98 is 0.3 % and
gets a warning; **the non-LP feature outside 30–80 is 16.4 %** and gets the same
warning. Both are honest, neither is equally important.

**3. Highpass carries the most weight and the least margin.** It is **57.6 %** of
board use, its feature table is the narrowest of the four (37–80, five points),
and its pole count was wrong in this converter until 2026-09-10.

**4. One row is knowingly wrong.** Bandpass resonance borrows the highpass
curve, and the two taps are different filter orders. It affects 3.5 % of
material, and the fix is a modelling decision about what "bandpass resonance"
should mean rather than a measurement.
