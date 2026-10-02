<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors -->
<!-- Part of mpc2emu — https://github.com/lentferj/mpc2emu -->
<!-- Contributions: Jan Lentfer, with AI assistance (see README). -->

# `XPOSE4` — the sparse-spectrum cells, and what the previous disc could not hear

**Disc: `CD5-XPOSE4.iso`, ON THE CARD since 2026-10-02 14:41, md5
`8637b390b4b9228b4d1d5dcbe2a8d469`.** One bank, 18 presets, 36 samples, so
everything after the load is a program change. Generator
`tests/re_banks/gen_e4xt_xpose4.py` (gitignored — this document is the record).
**XPOSE3 is parked, not deleted**: `CD5-XPOSE3.iso` → `XX_CD5-XPOSE3.iso`,
rename back to restore.

## ⚠ CD6 MUST STAY EMPTY — do not look for a spare slot there

`id 6` is **the E4XT itself** on the real SCSI bus. ZuluSCSI will mount a
`CD6-*.iso` and log a clean *"Opening … for id:6"* — its numbering is unique on
the SD card and it sees no conflict. The collision is one layer down: the
sampler cannot see the device and the SCSI protocol is disrupted. `ENVSPAN` sat
there 09:14–12:42 on 2026-08-18 doing exactly that, invisible and in the way,
with a clean boot log throughout. Recorded in the card's own `whatiswhat.txt`.

## Verified off the card, not from the source

Checked **after copying, by reading the image back**:

- EMU3 superblock and directory walked — **payload present *and*
  directory-addressed**. `build_iso` has already produced banks physically on a
  disc with *no directory entry*: invisible to the E4XT, and silently. Searching
  the bytes for a bank would pass on exactly the image the machine cannot see.
- Bank md5 `aa3bfd2004c338fe140285f027c20a27` matches the built `.E4B` exactly.
- 18 presets / 36 samples, 18 markers adjacent to 18 test samples.
- All 10 fine-tune cells at the exact intended 1/64-semitone units.
- Both looped cells still `FORWARD`; declared 32000 Hz stored as 32000.

There was **no EMU3 image reader in this project**, so one was written for it
(`~/temp/emu3_read.py`). It is **not** ISO9660 — EMU3 images carry no ISO9660
descriptor and begin with the ASCII magic `EMU3`. Four separate layout errors in
its first drafts each produced output that *looked like data*, three of them
printing a plausible bank; the reason to trust it is that it reproduces the
known-good `CD5-XPOSE3.iso` exactly. Worth reading `docs/EMU3_ISO_FORMAT.md`
rather than inferring the layout.

## Why this disc exists

§E4BBANDS measured the E4XT's playback failure as **four-semitone bands at ×16
and ×32**, and then measured that **XPOSE3 cannot test the remaining questions**
— because its one sample is broadband metallic audio whose spectral envelope
does not depend on the playback rate over 8–15×. Two different spectral
statistics were tried, both blind, each caught by its own positive control.

The discriminator was never the instrument. It was the sample.

**This disc is built around a sparse known spectrum**, so that the two jobs
separate:

- the **playback rate** moves the partials → pitch becomes measurable
- the **interpolation selector** moves their **levels** → filtering becomes
  measurable

Neither is measurable on broadband material, which is exactly why the previous
disc could answer neither.

## ⚠ A design error this disc caught in its own build

The first draft carried **one** comb, built to be read at ratio 12. It reported
itself fully verified — every fine-tune unit read back out of the written file,
every root correct, every marker adjacent. And it was wrong: a fixed comb cannot
stay under 44.1 kHz Nyquist across a 12× ratio range, so the single comb
**aliased above key 106** and could not read the very keys it was built for.

Nothing in the first draft checked that, because every check confirmed what was
*intended* rather than what was *produced*. Printing the landing frequencies is
what found it.

**The fix is a computed reachability property**, `readable_keys(divisor)`: the
keys at which *every* partial is under Nyquist, derived from the partials and
the ratio curve. Two guards came with it, both mutation-checked:

| mutation | result |
|---|---|
| `LOW` divisor 6 instead of 24 (aliases early) | **FAILS** — `no comb reads [115, 116]`, plus two cells that cannot hear any predicted free-run key |
| `LOW` divisor 12, i.e. the original single-comb draft | **FAILS** — `no comb reads [115, 116]` |
| shipped configuration (`HIGH` 12, `LOW` 24) | passes |

The second row is the point: **the disc as first written would now refuse to
build.**

## The two combs

Readout targets are 2 / 6 / 10 / 14 / 18 kHz. All are under the 22.05 kHz
Nyquist of a 44.1 kHz sample.

| comb | divisor | sample partials | readable keys | job |
|---|---|---|---|---|
| `XP4CMBHI` | 12 | 166.7 / 500 / 833.3 / 1166.7 / 1500 Hz | 0–106 | sharpest spread at ratio 12 — partials land across the full 2–18 kHz, where an interpolator shows itself most |
| `XP4CMBLW` | 24 | 83.3 / 250 / 416.7 / 583.3 / 750 Hz | 0–118 | **the workhorse** — reads both A/B pairs, at 1–9 kHz for 103/104 and 2–18 kHz for 115/116 |

Where the partials land, from the generator's own output:

| key | ratio | `HIGH` lands | `LOW` lands |
|---|---|---|---|
| 103 | 11.986 | 1998 / 5993 / 9989 / 13984 / 17980 | 999 / 2997 / 4994 / 6992 / 8990 |
| 104 | 12.699 | 2117 / 6350 / 10583 / 14816 / 19049 | 1058 / 3175 / 5291 / 7408 / 9524 |
| 115 | 23.973 | **3995 / … / 35959 — ALIASES** | 1998 / 5993 / 9989 / 13984 / 17980 |
| 116 | 25.398 | **4233 / … / 38098 — ALIASES** | 2117 / 6350 / 10583 / 14816 / 19049 |

**eosed §179b named the A/B as 103 vs 104 and 115 vs 116** — adjacent semitones
straddling ratio 12.0. Only `LOW` reaches the second pair.

## ⚠ Every test sample gets a distinct neighbour

A free-run reads **past the end of the sample into neighbouring sample RAM**, so
what you hear when it happens is the *neighbour's* audio. **XPOSE3 put three
copies of the same PCM in a row** — a run-on played the same audio again:
audible, but **not identifiable as a run-on.**

Here every test sample is immediately followed by a marker carrying a **single
300 Hz tone** that is not a harmonic of anything in either comb. The marker is
named after the sample it follows (`XP4CMBLW` → `XP4MRKMBLW`), and `verify()`
reads the sample order back **out of the written file** and prints the actual
adjacency — because adjacency is a property of the file, not of the generator's
list. 18 test samples, 18 markers, checked.

## The cells, and what each predicts

Measured band, root-relative: **offsets 46–49 and 58–61**, i.e. `[12n − 2, 12n + 1]`
semitones around exact `12n` for `n ≥ 4`. ×8 (offset +36) was measured **NORMAL**,
so the series starts at `n = 4`.

### Root tracking — same PCM, byte-identical, md5-verified

XPOSE3's own `XPR60`, so these are directly comparable to the 40 notes §E4BBANDS
measured rather than merely similar.

| preset | root | predicted bands |
|---|---|---|
| `XP4 BRD ROOT48` | 48 | 94–97 and 106–109 |
| `XP4 BRD ROOT60` | 60 | 106–109 and 118–121 |
| `XP4 BRD ROOT72` | 72 | 118–121 and 130–133 |

**Discriminating prediction: the bands track the ROOT**, i.e. they sit at
root + 46–49 in every cell. Note 130–133 exceeds MIDI key 127 for root 72, so
only the first band is reachable there.

### ⚠ The rate cell — 32000 Hz, the one that separates two hypotheses

32000 Hz is **0.466 of a semitone off the 1/64-semitone grid** against a maximum
of 0.5 — the best cell available. **22050 is useless** (exactly twelve semitones,
so every band lands back on the same pitch classes) and **27777 — our own EII
profile — is 8.0027, equally useless**. 27500 is the fallback at 0.158 off.

eosed §179e: the declared rate enters as `round(768 · log2(rate / 44053))`,
added to the pitch **before** the octave split, the modulo and the clamp
(§179d). For 32000 that is **−354 units = −5.5312 semitones**, a shift of
**−5.5469** against a 44100 base.

| | bands move to | keys free-run | keys 106–109 |
|---|---|---|---|
| **A** — rate folds into the pitch | offsets 40.5–43.5 and 52.5–55.5 | **100–103** | **NORMAL** |
| **B** — the rule is key-only | offsets 46–49 and 58–61, unchanged | 106–109 | free-run |

The two are far apart and one sweep separates them. ⚠ **Hypothesis A is
architectural, not a located write** — the converter and its units are proven by
the firmware constants; that its result reaches the pitch adder follows from the
units rather than from a traced write.

Cells: `XP4 RATE32K BRD` (broadband PCM) and `XP4 RATE32K CMB` (`LOW` comb).

### Fine-tune ladders — aimed at BAND edges, not at a ceiling

Fine tune is stored in **1/64-semitone units** (`vpar[36]`); `coarse_tune`
carries the whole semitones, because reaching offset 49 needs
`shift = T − 49 = −3.10` semitones and `fine_tune` is documented as −100…+100
cents. With `T = 45.9001` semitones at 44100 Hz, first bad offset is
`ceil(T − shift)`.

**Lower edge (offset 46), coarse 0** — crossing at unit 57/58:

| units | cents | first bad offset | key |
|---|---|---|---|
| +56 | 88.0 | 46 | 106 |
| **+57** | 89.0 | **46** | 106 |
| **+58** | 91.0 | **45** | 105 |
| +59 | 92.0 | 45 | 105 |
| +60 | 94.0 | 45 | 105 |

**Upper edge (offset 49), coarse −3** — crossing at unit −7/−6:

| units | cents | first bad offset | key |
|---|---|---|---|
| **−8** | −12.0 | **50** | 110 |
| **−7** | −11.0 | **50** | 110 |
| **−6** | −9.0 | **49** | 109 |
| −5 | −8.0 | 49 | 109 |
| −4 | −6.0 | 49 | 109 |

Every unit is **read back out of the written file** and asserted against the
intended value, not recomputed. These brackets are what locate a band edge to
1/64 of a semitone — and they need the `LOW` comb, because `HIGH` stops being
readable at key 106 and the lower edge sits exactly there.

### Leg B, at last — does a loop escape a band?

**Every instrument tried so far has been blind to this**, for a structural
reason: a looped voice sustains for the whole gate *by design*, so duration
cannot distinguish "loops correctly" from "free-runs". XPOSE3's two looped cells
both read ~3.9 s at every note.

`XP4 CMB LOW LOOP` (forward loop, frames 1000…122479) is the same comb, looped.
Now the question has an answer available: **a free-run replaces the partials with
whatever the neighbour holds**, and the neighbour is a 300 Hz marker that is not
a harmonic of anything in the comb. Compare its spectrum against
`XP4 CMB LOW 60`, unlooped, at the same keys.

## ⚠ Before you capture

1. **Bring up mididings by hand if you restarted minimally.** `~/autostartaudio.sh
   minimal` does **not** start them — the whole block sits inside
   `if [ "$1" != "minimal" ]`. Confirm `ps -ef | grep mididings` before trusting
   a capture; the failure is silent and you get a clean recording of the noise
   floor.
2. **Anchor the spectral window on the note, not on the clock.** Every spectral
   window in the previous session was taken at `LEAD_IN + t_on + 0.05` while
   program-change-to-note latency on this rig is **0.71–0.93 s** — so they
   measured **silence**. That invalidated three conclusions before it was caught.
   `hw_measure.anchor_offset` exists for exactly this and was not used. Until
   the level-checked anchor lands (§E4BBANDPLAN step 0), anchor on each note's
   own envelope peak and **confirm the window contains a note** before trusting
   any spectral number.
3. **Gate of 6 s, not 3.** The comb is 2.80 s long.

## What this disc does NOT settle

- **B1** — why the band's lower half exists. eosed's `0x96028` accounts for the
  upper half (an off-the-end table read at ratio ≥ 12) but not offsets −2/−1,
  where `%d7` is 3 on both the failing and the passing side.
- **B2** — *what ends a voice* is unlocated on either side. The sawtooth predicts
  a wrong **pitch**, not a free-run, so these are **two defects and only one is
  explained**.
- **f0 on notes 110 and 122** — still the cheapest direct test of the sawtooth,
  and **pitch has been checked nowhere**. The comb now makes it measurable.
