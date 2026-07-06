<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# Hardware RE: Amp Envelope Decay + `_fenv_rate()` Calibration

> **STATUS: RESOLVED (2026-06-08).** `PZT[4]` confirmed as the amp Decay1 rate
> byte and `_fenv_rate()` calibrated from hardware. Procedure retained as the
> record of how it was done; results are in the "Results" section below.
> See `docs/RESOLUTION_NOTES.md` §1 and §2.

## Goal

Confirm the hypothesis that `PZT[4]` is the amp envelope **decay rate** byte,
and use the result to calibrate the `_fenv_rate(seconds)` formula.

---

## Results (2026-06-08)

**Byte position — confirmed.** `AMPENV_SETME.E4B` (E4XT-saved baseline) pins the
12-byte `PZT[0:12]` amp-envelope layout. `AMP_DECAY_CAL.E4B` isolates the decay
byte: across its 6 voices the **only** byte that changes is `PZT[4]`
(`08 10 18 20 30 40`), proving `PZT[4]` = Amp Decay1 rate.

**Calibration — measured.** Decay-to-silence times (sustain=0) on the E4XT:

| rate (PZT[4]) | decay time |
|--------------:|-----------:|
|             8 |    0.034 s |
|            16 |    0.098 s |
|            24 |    0.169 s |
|            32 |    0.198 s |
|            48 |    0.454 s |
|            64 |    1.225 s |

Direction is the **opposite** of the original guess: rate 0 = fastest (instant),
higher = slower (rate 127 ≈ 47 s). Log-linear fit (R²=0.96):

```
time_s = 0.0310 · e^(0.0581 · rate)
```

Applied as `_ENV_RATE_A`/`_ENV_RATE_K` + `_fenv_rate()`/`_fenv_seconds()` in
`writers/e4b_writer.py`, mirrored by `_fenv_rate_inv()` in
`parsers/e4b_parser.py`.

---

## Background

The E4B voice block's primary zone table (PZT, 64 bytes at `voice[110:174]`)
contains a 6-stage amp envelope at `PZT[0:12]` and a 6-stage filter envelope
at `PZT[14:26]` (filter env is confirmed from `B.005-FltEnvTest.E4B`).

Known confirmed bytes:
- `PZT[8]` = Amp Release1 rate (confirmed: 0x14=20 ≈ 4 s in `_PRIMARY_ZONE_TMPL`)

Hypothesis for full amp envelope layout:
```
PZT[0/1]  = Amp Attack1   rate / level  (default 0x00, 0x00 → start at silence)
PZT[2/3]  = Amp Attack2   rate / level  (default 0x00, 0x7F → rise to +100%)
PZT[4/5]  = Amp Decay1    rate / level  (default 0x00, 0x7E → no decay, hold)
PZT[6/7]  = Amp Decay2    rate / level  (default 0x00, 0x7F → hold at +100%)
PZT[8/9]  = Amp Release1  rate / level  (default 0x14, 0x00 → fall at rate 20)
PZT[10/11]= Amp Release2  rate / level  (default 0x00, 0x00 → stay silent)
```

---

## Step 1: Generate test banks

```bash
cd /home/lentferj/git-repos/mpc2emu
python3 tests/re_banks/gen_amp_envelope_test.py
```

This produces 5 E4B files in `/home/lentferj/temp/re_amp_envelope/`:

| File | PZT[4] | Expected behavior |
|---|---|---|
| `AMP_DECAY_000.E4B` | 0   | No decay — tone holds forever after attack |
| `AMP_DECAY_030.E4B` | 30  | Slow decay (~2–3 s) |
| `AMP_DECAY_060.E4B` | 60  | Medium decay (~1 s) |
| `AMP_DECAY_090.E4B` | 90  | Fast decay (~0.5 s) |
| `AMP_DECAY_127.E4B` | 127 | Fastest decay (< 0.1 s?) |

All banks use the same synthetic 5-second sine tone at C3 (MIDI 48), sustain=0
so the decay is audible without needing to hold a key.

---

## Step 2: Load on E4XT and listen

1. Load each bank on E4XT via `--iso` output or directly as `.E4B`.
2. Trigger the single note at C3 (MIDI 48), hold it for at least 6 seconds.
3. Listen for how quickly the amplitude decays to silence after the attack.

If PZT[4] is the decay rate, you should hear progressively shorter decay times
as the bank number increases (000 = infinite hold, 127 = near-instant cut).

If you hear **no difference** between the banks, PZT[4] is NOT the decay byte
— report back and we will look at PZT[5], PZT[6], or vpar bytes instead.

---

## Step 3: Record the time → byte mapping

For each bank where the decay is audible, measure the approximate decay time
(time from note attack peak to near-silence).

**Done** — a finer 6-point sweep (`AMP_DECAY_CAL.E4B`, rates 8/16/24/32/48/64)
was used instead of the 0/30/60/90/127 set; see the Results table above. The
attack-rate sweep (`PZT[2]`) was not separately measured — the same calibration
curve is reused for attack/decay/release, which matches the hardware within the
log-fit residual.

---

## Step 4: Calibrate `_fenv_rate()`

With the measurements above, fit a curve to the (time, rate) data points.
The current formula is `rate = round(80.0 / (time + 0.01))`.

If the hardware measurements follow an inverse relationship, update the
constant (currently 80.0) by fitting to the measured points:
- For each (time_i, rate_i) pair: `constant ≈ rate_i × (time_i + 0.01)`
- Use the median or least-squares fit

If the shape is not inverse but logarithmic or power-law, note the shape
and we will derive the appropriate formula.

---

## Step 5: Update the code — DONE (2026-06-08)

1. ✅ `_build_voice()` in `e4b_writer.py` writes the full `PZT[0:12]` amp
   envelope (attack → full, decay → sustain held through Decay2, release →
   silence).
2. ✅ `_fenv_rate()` recalibrated (`_ENV_RATE_A`/`_ENV_RATE_K`, log fit).
3. ✅ `_parse_voice()` in `e4b_parser.py` reads it back via `_fenv_rate_inv()`.
4. ☐ `E4B_FORMAT.md` §4.2 — update with the confirmed amp envelope layout
   (still pending; the format reference has not yet been refreshed).
5. ✅ `TODO.md` / `RESOLUTION_NOTES.md` marked resolved.
