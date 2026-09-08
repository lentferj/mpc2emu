<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: does a zero-sustain release actually sound? (§E4BZEROSUSRELEASE)

## Goal

Settle whether the 2026-09-08 fix to `writers/e4b_writer.py` is right. It is
currently **inferred from the segment model and has never been put in front of
the machine.**

## The claim under test

At `env_sustain = 0` the release span is the complement of the decay span — so
it is **zero** — and `_env_span_rate(0, t)` returns `0` for any `t`. Rate 0 is
the **instant** rate (the decay block directly above it says so and floors
against it). Every release, 5 ms or 5 s, encoded as a dead cut.

The fix uses the **full span** as the reference distance instead, so the
requested seconds survive, plus the same minimum-audible floor the decay
carries.

**Why it hides:** held to the end of its own decay a zero-sustain voice is
already silent, so nothing is lost. It is audible **only when the key is lifted
during the decay.** A probe that holds the note to silence measures nothing and
will report a clean pass.

## Route: SysEx, no card crossing

`eosed` has sent whole presets over SysEx since 2026-08-25 (`eos/bridge.py`).
The bank below is an ordinary `.E4B`; nothing here needs a card.

## Material

`~/temp/HWCHK_REL.E4B`, built by
`tests/re_banks/build_hwcheck_e4xt_release.py` **through `write_e4b`** — a bank
built by anything other than the shipping pipeline is not evidence about the
shipping pipeline.

One bank, six presets. Decay is 4.0 s throughout so that a note-off at ~1.0 s
lands **inside** the decay.

| # | preset | sustain | release | Rls1 byte | role |
|---|---|---|---|---|---|
| 0 | `REL 0.5 SUS0` | 0 | 0.5 s | **35** | zero sustain, short |
| 1 | `REL 1.0 SUS0` | 0 | 1.0 s | **47** | zero sustain, medium |
| 2 | `REL 5.0 SUS0` | 0 | 5.0 s | **75** | zero sustain, long |
| 3 | `REL 1.0 SUS50` | 0.5 | 1.0 s | 48 | control, untouched path |
| 4 | `REL 5.0 SUS50` | 0.5 | 5.0 s | 77 | control, untouched path |
| 5 | `REL 1.0 PREFIX` | 0 | 1.0 s | **0** | **BEFORE:** pre-fix encoding |

**Preset 5 is the on-machine "before".** Its `Rls1` is forced to 0 after
writing, because the fixed writer can no longer produce that byte. Without it
the bench is comparing against memory, and "it sounds like it releases" is not
a measurement.

## Procedure

For each preset, one note, and **note-off must fall inside the decay**:

```
  note-on   C3 (60), velocity 100
  hold      1.00 s          <- mid-decay; the decay is 4.0 s
  note-off
  record    8.0 s total from note-on
```

Measure **time from note-off to −40 dB** relative to the level at the instant
of note-off.

## What each outcome means

- **Presets 0/1/2 give increasing release times** → the fix works and the
  requested seconds survive. Record the three measured times; they are also the
  first data on what the full-span reference is actually worth.
- **Preset 5 cuts abruptly (release ≪ 50 ms)** → the defect was real and
  audible. **If preset 5 does NOT cut**, stop: the premise is wrong, rate 0 is
  not the instant rate for release, and the fix needs re-deriving rather than
  confirming.
- **Presets 3/4 unchanged from previous behaviour** → the non-zero-sustain path
  was untouched, as intended.
- **Presets 0/1/2 all identical to each other** → the seconds are still being
  discarded; the full-span reference is the wrong model even though it is
  better than a dead cut.

## Traps

- **Release mid-decay or measure nothing.** A note held to silence passes
  whatever the encoding says.
- **Measure from note-off, not note-on.** The decay is 4 s and dominates any
  window anchored at note-on.
- **Verify what actually sounded before interpreting.** Four notes commanded,
  four onsets present, per `~/temp/matrix/measure.py` — and check the reported
  **blind fraction** and **spacing gate**, not just the count.
- **Use the pre-EQ tap.** Post-EQ material has cost real bench time before.

## Not established by this run

The full-span reference is a **model choice**, not a measured law. Confirming
that the release now sounds does not confirm that its duration is right — that
needs a rate ladder against measured times, which is the same missing
measurement as the two-stage attack question in `TODO.md`.
