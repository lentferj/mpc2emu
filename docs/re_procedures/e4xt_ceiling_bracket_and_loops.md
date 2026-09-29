<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors -->
<!-- Part of mpc2emu — https://github.com/lentferj/mpc2emu -->
<!-- Contributions: Jan Lentfer, with AI assistance (see README). -->

# `XPOSE3` — narrow the playback-rate ceiling, and ask whether a LOOP escapes it

**Disc: `CD5-XPOSE3.iso`, on the E4XT card since 2026-09-29 20:14, md5
`6bd9770d`.** One bank, 26 presets, so everything after the load is a program
change. Built by `tests/re_banks/gen_e4xt_xpose3.py`, which is gitignored —
this document is the record.

> **What is NOT open.** That an over-ceiling zone makes an audible artefact is
> already settled and is how §E4BXPOSE started: Jan at the instrument, *"there
> are clear artefacts on the output ... as if other samples are appended to the
> original"*, and a capture showing the voice jump back to −16.5 dBFS after the
> sample has decayed out and keep going for nine seconds. **Do not re-ask it.**

## The two gaps

**The ceiling is a bracket, not a number.** §E4BXPOSE measured
(593 337, 628 618] Hz — **5.95 % wide**. Four points, but both declared rates
tested (44100 and 22050) differ by exactly an octave, so they give the *same*
bracket twice. `models/common.py` says a 30000 Hz sample would split it, and
that is the wrong instrument: EOS's handling of the sample-rate field is itself
under investigation (§E4BRATE, where sub-44.1 kHz material played sharp), so a
surprise at an unusual declared rate would not be attributable.

**Fine tune is the same lever without the confound.** It moves the voice's rate
in sub-semitone steps at a fixed 44100 Hz — the rate the bracket was measured
at.

**And every measurement so far used UNLOOPED samples.** Both original presets
("no loop"), all four XPOSETEST presets ("unlooped"). The population that made
the ceiling worth warning about is the opposite: the commercial synth bank
measured on 2026-09-28 (§E4BCEILSRC) has **15 of 15 presets over the ceiling
and all four of its samples FORWARD-looped.** A looped voice does not reach the
end of its sample at all while the key is held. ⚠ **The whole prevalence result
rests on that untested transfer.**

## Pre-registered predictions

⚠ **These are PREDICTIONS. Nothing below has been measured.** Do not copy this
table into a file, sheet or directory whose name says measured, observed or
results — that has already happened once here, and a prediction set was used to
score its own law.

Clean while `(key − root) + fine_semitones ≤ T`, where `T = 12·log2(C/44100)`
and the bracket says `T ∈ (45, 46]`. The fitted 625 000 gives `T = 45.900`.

### Leg A — eight cells, root 60, zone 0-127, **unlooped**, 44100 Hz

Fine tune in **1/64 semitone**, the format's own step (`vpar[36]`), read back
out of the written file and asserted rather than computed twice.

| preset | units | semitones | breaks at 105 if | i.e. C ≤ (Hz) | **predicted under 625 000** |
|---|---|---|---|---|---|
| `XP3 FT00` | 0 | 0.0000 | — (control) | — | **106** |
| `XP3 FT08` | 8 | 0.1250 | T ≤ 45.1250 | 597 636 | 106 |
| `XP3 FT16` | 16 | 0.2500 | T ≤ 45.2500 | 601 967 | 106 |
| `XP3 FT24` | 24 | 0.3750 | T ≤ 45.3750 | 606 329 | 106 |
| `XP3 FT32` | 32 | 0.5000 | T ≤ 45.5000 | 610 723 | 106 |
| `XP3 FT40` | 40 | 0.6250 | T ≤ 45.6250 | 615 148 | 106 |
| `XP3 FT48` | 48 | 0.7500 | T ≤ 45.7500 | 619 606 | 106 |
| `XP3 FT56` | 56 | 0.8750 | T ≤ 45.8750 | 624 096 | 106 |

**`FT00` is the control and must break at 106, as XPOSETEST2 did.** If it does
not, nothing else in the bank means anything — stop and find out why.

**What each outcome buys:**

* **All eight break at 106** → `T > 45.875` → **C ∈ (624 096, 628 618]**, a
  **0.72 %** bracket. Consistent with the fitted 625 000, and it is then fitted
  inside a bracket eight times tighter.
* **Any cell breaks at 105** → that cell's row gives the upper bound directly,
  and **625 000 is refuted.** The largest `j` still breaking at 106 and the
  smallest breaking at 105 bracket `T` to 1/64 semitone.
* **A non-monotonic pattern** (105 at some `j`, 106 at a larger one) means the
  lever is not doing what this document assumes. Report it as that, not as a
  bracket.

### Leg B — does a loop escape the ceiling? Root 60, zone 0-127, fine 0

| preset | loop | predicted if a loop does NOT protect | predicted if it DOES |
|---|---|---|---|
| `XP3 LOOP LONG` | forward 245963..614908 (the commercial shape) | breaks at 106 | sustains cleanly at 106+ |
| `XP3 LOOP SHORT` | forward 1000..5000 (never nears the end) | breaks at 106 | sustains cleanly at 106+ |

⚠ **If the two DISAGREE**, the answer is about the *end comparison* rather than
about looping, and the short loop is the one that says so — it never approaches
the end address at all.

**This is the leg that can change shipped behaviour.** If a loop protects, the
diagnostic over-warns on most real material (the 10.8 % across 113 banks, and
the 15 of 15 in one bank, are looped material) and the remedy text is wrong.

### Leg C — the commercial zone's own geometry

`XP3 VENDORGEO`: root 72, zone 66-127, forward-looped, fine −12 c — the exact
geometry of the zone Jan imported. The shipped diagnostic reports
`highest_safe_key` **118** for it, so **predict the first bad note is 119.**

### The real material

Fifteen presets of the commercial bank itself, geometry unmodified (93 zones
round-trip identical), so the as-shipped preset plays beside the authored
cells. `SYNCO X   (cl)RP` is the one Jan imported; its third voice is the
untuned one and therefore the worst, `highest_safe_key` **117**.

## Running it

1. **Jan loads `CD5-XPOSE3.iso` from the front panel.** There is no remote
   load-bank command — eosed searched the message set, and the only bank-scope
   command is `ERASE_RAM_BANK`, which this project does not send.
2. Everything after that is a program change plus notes on MIDI ch 5, capture
   15/16 (`tests/re_banks/hw_measure.py`; `whichcard.py` prints the rig line).
3. Sweep each cell **ascending from the root**, notes 100→110 for legs A and B,
   112→122 for leg C.

⚠ **LEAVE SILENCE BETWEEN NOTES.** This defect's signature is that it does not
stop. §E4BXPOSE lost a whole sweep to a previous note still free-running into
the next capture, and every note then read as broken — including one the sweep
started on, against the argument that a sweep's first note cannot be
contaminated. It can.

⚠ **Keys 119-127 are above a 61-key controller** — which is why this shipped
unnoticed in the first place. Send them over MIDI; do not try to play them.

## Where the answers go

* Leg A → the bracket and the fitted value in `models/common.py`
  (`E4XT_MAX_PLAYBACK_RATE_BRACKET_HZ`, `E4XT_MAX_PLAYBACK_RATE_HZ`), and
  §E4BXPOSE.
* Leg B → §E4BCEILSRC and, if a loop protects, the
  `E4B_ZONE_ABOVE_PLAYBACK_CEILING` remedy text and probably its trigger.
* Leg C → confirms or refutes the shipped `highest_safe_key` on real geometry.
