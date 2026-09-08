<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: the IB-304F second filter board (§AKAIIB304F)

## Goal

Support the AKAI **IB-304F** ("ProFilter", *2nd LSI filter board*) in the AKAI
writer: the **FILTER 2** section, the **TONE** page, and **ENV3**.

## Why it is worth doing

The base S3000XL filter is **2-pole, 12 dB/octave**. Most sources we convert
from — E4B, KRZ, XPM — carry 4-pole filters, and today that slope is simply
lost on the AKAI path. With the board, FILTER 2 sits **in series** with
FILTER 1, so setting both identically to LOWPASS gives a genuine **4-pole,
24 dB/octave** filter. That is not a new effect; it is the missing half of a
mapping we already do.

## What is already established

**From the S3000XL Operator's Manual** (pp. 103–111, "The Second Filters"):

| | |
|---|---|
| Modes | **LP, BP, HP** and a special **EQ** mode |
| Slope | FILTER 2 is 2-pole; **in series with FILTER 1 → 4-pole / 24 dB/oct** |
| Resonance range | FILTER 1 is **0–15**; FILTER 2 is **0–31** — "twice the range". Manual's "very resonant" pair is **15 and 30** |
| EQ mode | Resonance **16 is flat**; above boosts, below cuts, around the set frequency |
| Key tracking | FILTER 2 has its own; **+12 tracks octave-for-octave** |
| ON/OFF | Bypasses **the second filter *and* the tone section together** |
| Polyphony | With it on, an S3200 drops to **30 voices** |
| TONE | "Spectral tilt" — a centre frequency and a ± slope |

**From the field work (peer handoffs, not yet in our own format reference):**

- **Fifteen keygroup fields** belong to the board: the second filter, the tone
  section, and **all eight stages of ENV3**.
- **The fields exist in the header on every machine and do nothing without the
  board.** The machine's own refusal is *"2nd filter board IB304F not fitted!"*
- **Nothing on the wire distinguishes a fitted machine from an unfitted one.**
- `ENV3` is modulation source **14**. A `MODV*` amount whose matching `MODS*`
  source is 0 is **silently inert** — carry both or neither.
- The ENV3 *generator* responds over SysEx even on a machine without the board;
  the ENV3 *page* is gated at the panel, **and that area has crashed the
  machine**. Prefer SysEx.

## Phase 0 — before the board arrives, and worth doing regardless

**0.1 Put the fifteen offsets in our own format reference.** They currently
live only in a peer handoff. `docs/AKAI_S3000_FORMAT.md` has no FILTER 2, TONE
or ENV3 rows, so our writer cannot address them and our reader cannot report
them.

**0.2 Scan the program corpus for non-zero values at those offsets.** This
needs no hardware and answers three things at once:

- whether the offsets are right (values should be plausible and bounded —
  resonance 0–31, mode 0–3, not arbitrary bytes);
- what real authored material actually sets;
- **prevalence** — how many library programs would change if we started
  honouring these fields on read.

9442 S3000 programs are already indexed for this kind of sweep (that is where
the mute-group 3.3 % figure came from).

**0.3 Decide the write policy before measuring anything.** Because nothing on
the wire says whether the board is fitted, a program that maps a 4-pole source
onto FILTER 1 + FILTER 2 sounds **correct on a fitted machine and half-filtered
on an unfitted one** — the second filter simply does nothing. This is a flag,
not a default: `--akai-ib304f`. Writing the fields unasked would quietly change
what every existing conversion sounds like on a fitted machine.

## Phase 1 — with the board installed

**1.1 Confirm the board is seen.** The FILTER 2 page opens instead of showing
the refusal. Record the firmware version alongside; this is the instrument for
everything below.

**1.2 The 4-pole check, first, because it validates the whole rig.** Set
FILTER 2 to LOWPASS with parameters identical to FILTER 1 and measure the
roll-off slope. It must read **24 dB/oct** against FILTER 1 alone at
**12 dB/oct**. If that does not come out, stop — nothing measured afterwards
can be trusted.

**1.3 FILTER 2 cutoff → Hz, per mode.** Do **not** assume it shares FILTER 1's
law because it is the same LSI; measure it and compare. Sweep the cutoff byte
across its range in LP, then confirm BP and HP land on the same law.

> **The trap that already cost this project 0.31 octaves.** FILTER 1's law was
> originally fitted to a **spectral centroid** — the average frequency of
> everything the *source* contains, which sits above the corner by a
> source-dependent amount. That is a **slope** error, not an offset, so no
> calibration constant could fix it, and every AKAI program came out dark.
> Fit from the **resonance peak**, and if a −3 dB point is used anywhere, take
> it against **one fixed wide-open reference**, never a per-curve
> normalisation.

**1.4 Resonance 0–31 → dB of peak.** Then compare against FILTER 1's 0–15.
"Twice the range" is a statement about the **control span**, not a promise that
one FILTER 2 unit equals half a FILTER 1 unit in dB. Measure both and state the
relationship as measured.

**1.5 EQ mode, separately.** Confirm **16 is exactly flat**, then measure cut
and boost in dB per unit either side. The manual is explicit that switching
LP → EQ at the same resonance value changes the tone, so a sweep that crosses
modes measures two laws at once. Keep them apart.

**1.6 TONE.** Centre-frequency law, and the slope law in dB of tilt per unit
over its ± range. Note that the ON/OFF switch bypasses TONE **and** FILTER 2
together, so an A/B on that switch moves two variables — isolate by leaving
FILTER 2 flat while measuring TONE.

**1.7 ENV3 → FILTER 2 depth.** Same shape as the ENV2 → FILTER 1 work, and
watch for the same structure: **ENV2's depth turned out to be a *product* with
its own sustain** (`octaves = 0.002612 × SUSTN2 × depth`). Test whether ENV3
behaves the same way before fitting a single depth constant — set two different
sustain levels and check whether depth scales with them.

**1.8 FILTER 2 key tracking.** Confirm +12 is octave-for-octave, and whether
the negative side carries the same asymmetry FILTER 1's does (that scale is
itself disputed — 0.622 from one sweep against 96–103 % unscaled from another).

## Traps

- **PRGNUM 0 is never free** — the boot-resident `TEST PROGRAM` sits there and
  survives every memory clear. Number test programs from 1.
- **Prefer SysEx to the panel for ENV3**; that page is gated and has crashed
  the machine.
- **A modulation amount without its source is inert.** When ENV3 is the source
  under test, set `MODS*` **and** `MODV*`.
- **Check what actually sounded** before interpreting — commanded notes present,
  and read the harness's blind fraction and spacing gate, not just the count.

## Deliverable

A section in `docs/AKAI_S3000_FORMAT.md` giving the fifteen offsets, and
measured laws in `models/common.py` alongside the FILTER 1 constants — each
carrying, as those do, the range it was fitted over and what it was measured
against.
