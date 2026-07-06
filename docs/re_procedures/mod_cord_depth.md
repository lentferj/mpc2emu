<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# Hardware RE: Modulation-cord depth calibration

## Goal

Find the transfer function from an EOS **PatchCord amount** (the signed byte we
write, `round(depth × 127)`, ±127 = ±100 %) to the **actual modulation in
musical units**. The cord *routing* (which source → which dest) is fully RE'd
(see `E4B_FORMAT.md §4.3`); what is **not** measured is how much a given amount
*moves* the destination. The converter currently ships guesses:

| Cord | Code constant | Current assumption |
|---|---|---|
| LFO→Pitch | `LFO_PITCH_FULL_CENTS = 1200` | amount 100 % = ±1 octave |
| LFO→Filter-Freq | (proportional 0–1) | amount 100 % = ?? octaves |
| FilterEnv→Filter | `filter_env_amount` 0–1 | amount 100 % = ?? octaves |
| Key→Filter | `filter_keytrack` ±1 | amount 100 % = 1:1 tracking? |
| Velocity→Filter | `velocity_to_filter` ±1 | amount 100 % = ?? octaves |

These all feed the same unknown: **cents (or octaves) per cord-%**.

---

## Method — the square-LFO trick

Driving the destination with a **square** LFO at a known cord amount makes the
modulated parameter hop between two *steady* states. The difference between the
two states is the peak-to-peak modulation (= `amount/100` of full-scale); a
sweep of amounts shows whether the response is linear and pins the constant.

Key/Velocity tracking use no LFO — play different keys / velocities instead.

---

## Step 1: Generate the test bank

```bash
cd /home/lentferj/git-repos/mpc2emu
python3 tests/re_banks/gen_mod_depth_test.py
```

Writes to `/home/lentferj/temp/re_mod_depth/`:

- `MOD_DEPTH_CAL.E4B` / `.iso` — 10 presets:

| Preset | What it measures |
|---|---|
| `PitchDepth 25/50/75/100` | square LFO1 → **Pitch** at amount 25/50/75/100 %, pure 441 Hz sine |
| `FiltDepth 25/50/75/100` | square LFO1 → **Filter-Freq** at the same amounts, resonant saw |
| `KeyTrk 100` | **Key → Filter** at 100 % — play octaves and read the cutoff |
| `VelTrk 100` | **Velocity → Filter** at 100 % — play one key at vel 1 / 64 / 127 |

## Step 2: Record on the E4XT

- **PitchDepth / FiltDepth**: hold one note (any key) and let the square LFO run
  for **≥3 full cycles** (~6 s; the LFO is 0.5 Hz). One take per preset.
- **KeyTrk 100**: play and hold **C1, C2, C3, C4, C5, C6** in turn, with the
  resonance whistling so the cutoff is audible/visible.
- **VelTrk 100**: play the same key three times at velocity **1, 64, 127**.

Record dry (filter audible, no reverb), 44.1/48 kHz mono is fine. Put the WAVs in
`/home/lentferj/temp/re_mod_depth/`.

## Step 3: Analyse

```bash
# pitch presets (pure sine → unambiguous pitch tracking):
python3 tests/re_banks/analyze_mod_depth.py PitchDepth100.wav --mode pitch
# filter presets (tracks the resonant peak):
python3 tests/re_banks/analyze_mod_depth.py FiltDepth100.wav  --mode filter
```

The tool splits the take into its two square-LFO states and prints the **low /
high** frequency, the **peak-to-peak** (cents and octaves) and the **one-sided**
depth. Validated against a synthetic ±100 cent signal (recovers 200.8 c p2p).

For Key/Vel tracking just read the resonant-peak frequency at each key/velocity
off the analyzer (run `--mode filter` on each segment) or Audacity's *Plot
Spectrum*.

---

## Step 4: Fill in and back out the constants

**LFO→Pitch** — record the table, confirm linearity, set `LFO_PITCH_FULL_CENTS`
in `models/common.py` to the 100 %-amount one-sided cents:

```
amount %   one-sided cents (measured)
   25   ->  __________            full-scale (×4)  = ______
   50   ->  __________            full-scale (×2)  = ______
   75   ->  __________            full-scale (×4/3)= ______
  100   ->  __________            LFO_PITCH_FULL_CENTS = ______
```

**LFO→Filter-Freq** — same table in **octaves**; gives the octaves-per-100 %
constant for a new `lfo_filter_depth_to_amount()` helper (and informs
`filter_env_amount` / `FILTER_ENV_FULL_CENTS`, which share the Filter-Freq dest).

**Key→Filter** — cutoff-Hz at C1..C6 at amount 100 %; the octaves-per-octave
slope is the 1:1-tracking check (100 % should ≈ 1 octave cutoff per octave key).

**Velocity→Filter** — cutoff-Hz at vel 1/64/127 at 100 %; octaves between vel 1
and 127 = full-scale velocity→cutoff depth.

If the response is **non-linear** in cord amount (e.g. the 25/50/75/100 points
don't scale), fit a curve and replace the proportional pass-through, the same
way the LFO rate and envelope curves were calibrated.

---

## Notes

- The LFO rate→Hz curve itself is a separate (3-point) calibration — see
  `RESOLUTION_NOTES §15`. It does not affect these depth measurements (a square
  LFO's two states are rate-independent).
- The filter cutoff byte→Hz mapping (`vpar[60]`: 0≈57 Hz … 255=20 kHz,
  exponential) is documented in `E4B_FORMAT.md §4`; use it only as a sanity
  cross-check — the analyzer measures the *actual* resonant peak directly.
