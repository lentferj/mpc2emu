<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors -->
<!-- Part of mpc2emu — https://github.com/lentferj/mpc2emu -->
<!-- Contributions: Jan Lentfer, with AI assistance (see README). -->

# AKAI LFO2 (`PANDEP`) — loudness and filter calibration

**Status: built and verified, waiting on a card crossing.**
Image `~/temp/HD5-LFO2CAL.img` (8 MB, volume `LFO2CAL`, 18 programs).
Generator `tests/re_banks/gen_akai_lfo2cal.py` — **gitignored, so the numbers
and the method below are the durable record, not the script.**

## What it unblocks

Two matrix cells and nothing else:

| cell | today |
|---|---|
| `lfo2_to_volume` → AKAI | writer drops it and logs why |
| `lfo2_to_filter_cents` → AKAI | writer drops it and logs why |

LFO1's laws are products — loudness `0.010068 × LFODEP × amount`
(§AKAILFOAMP), filter 1 `~4.0 × LFODEP × MODVFILT1` (s3ked §270). **LFO2 is a
different rail**: its depth is `PANDEP` (0x1e), and no product has ever been
measured for it. Writing an amount against source 8 today would be a guess.

## The method is equal-product, not a sweep

§173 is explicit that linearity in each variable separately does **not**
establish a product, and it earned that: a coefficient taken at one depth and
applied flat over-reads by the depth ratio — 9.9× at the bottom. So the product
is held constant while the split varies.

**If the swing does not move across 100–103, the law is a product and one
coefficient covers it. If it moves, a single coefficient is wrong.**

## ⚠ The confound this disc exists to avoid

**`PANDEP` also gates LFO2's PAN route** (§AKAILFO2REST). A loudness sweep that
leaves the pan matrix alone measures loudness *and* pan moving together, and
they cannot be separated afterwards. **Every program here zeroes the pan matrix
explicitly.** Program 111 is the only one with pan live — it is not a data
point, it shows what the zeroing is worth.

## Programs

| prg | name | PANDEP | amt | dest | pan | decides |
|---|---|---|---|---|---|---|
| 100 | `L2AMP9920` | 99 | 20 | amp | 0 | product ~2000, split 1 |
| 101 | `L2AMP5040` | 50 | 40 | amp | 0 | product ~2000, split 2 |
| 102 | `L2AMP4050` | 40 | 50 | amp | 0 | product ~2000, split 3 |
| 103 | `L2AMP2099` | 20 | 99 | amp | 0 | product ~2000, split 4 |
| 104 | `L2AMPA10` | 50 | 10 | amp | 0 | coefficient, product 500 |
| 105 | `L2AMPA20` | 50 | 20 | amp | 0 | coefficient, product 1000 |
| 106 | `L2AMPA60` | 50 | 60 | amp | 0 | coefficient, product 3000 |
| 107 | `L2AMPD0` | **0** | 40 | amp | 0 | silent ⇒ `PANDEP` gates |
| 108 | `L2AMPV0` | 50 | **0** | amp | 0 | silent either way |
| 109 | `L2NONE` | 50 | 0 | — | 0 | **the rig's own floor** |
| 110 | `L2PANOFF` | 50 | 40 | amp | 0 | pan zeroed (as all above) |
| 111 | `L2PANON` | 50 | 40 | amp | **40** | pan LIVE — the confound, shown |
| 112 | `L2FLT9920` | 99 | 20 | flt | 0 | product ~2000, split 1 |
| 113 | `L2FLT5040` | 50 | 40 | flt | 0 | product ~2000, split 2 |
| 114 | `L2FLT4050` | 40 | 50 | flt | 0 | product ~2000, split 3 |
| 115 | `L2FLTA20` | 50 | 20 | flt | 0 | coefficient, product 1000 |
| 116 | `L2FLTD0` | **0** | 40 | flt | 0 | control |
| 117 | `L2FLTV0` | 50 | **0** | flt | 0 | control |

Source is a steady 220 Hz sine (`L2TONE`), 8 s, root/played key 36.
`PANRAT` = 8 → **~0.91 Hz**, about 7 cycles in the note.

Loudness programs leave `FILFRQ` wide open (99); filter programs sit at
**`FILFRQ` 70**, mid-range so the corner can move *both* ways — a corner near
either rail turns a symmetric modulation into a one-sided one and the fit reads
low, which is the band-edge trap that cost §270 two of its points.

## Measuring

**Measure the COHERENT swing at 0.91 Hz. Never a broadband percentile.** On the
K2000 the same week, a program with *nothing routed* read 2.20 dB broadband and
only 1.71 dB at the LFO rate — its strongest component was the rig's own
0.40 Hz image wander. **Program 109 is what says whether this rig has the same
floor**, and it must be captured before anything is believed.

For the filter programs the observable is the corner, not the level: track the
spectral centroid or the −3 dB corner against 116/117 as the unmodulated
reference.

## ⚠ Before it goes on the card

1. **The slot digit is a placeholder.** The name must be `HD<digit>-…` or
   ZuluSCSI never serves it — and **id 6 is the sampler itself**; an image
   there mounts cleanly, logs cleanly and breaks the bus one layer down.
   **Read the card's own listing first.** The card was not mounted when this
   was built, so `HD5` is a guess.
2. **Prefer appending to HD4 over claiming a new id**, per the standing
   append-never-rebuild rule — every id on this card is taken, so a new image
   *replaces* something.
3. **PRGNUM 100–117 has not been checked against the live card.** A collision
   does not fail; it sounds two programs at once (§135, an evening of spectral
   work on a sine sitting on top of the boot test program).

## What was already caught building it

**All eighteen programs initially landed on PRGNUM 127.** The generator was
modelled on the PANDEP disc, which writes `min(prgnum, 127)` — harmless there
because its numbers are 120–124, catastrophic here because the first draft used
130–147 and **every one clamped to the same number**. PRGNUM is a single byte
and the machine's range is 1–127. The clamp is now a fatal error, and every
patched byte is verified against the plan before the image is written.
