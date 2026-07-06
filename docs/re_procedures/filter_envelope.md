<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# Hardware RE: Filter-envelope rate calibration (Gap A)

## Goal

Confirm whether the **filter** envelope uses the *same* rate↔time curve as the
**amp** envelope. The amp Decay-1 rate was hardware-calibrated to

```
time_s = 0.0310 · e^(0.0581 · rate)        (rate 0 = instant, 127 ≈ 47 s)
```

The filter-envelope writer currently reuses that formula but it was never
measured on the filter EG. See `docs/RESOLUTION_NOTES.md` §17 Gap A.

---

## Step 1: Generate the test bank

```bash
cd /home/lentferj/git-repos/mpc2emu
python3 tests/re_banks/gen_filter_envelope_test.py
```

This writes, in `/home/lentferj/temp/re_filter_envelope/`:

- `FLT_DECAY_CAL.E4B` — one bank, **6 presets**, differing only in the filter
  envelope Decay-1 rate byte `PZT[18]`.
- `FLT_DECAY_CAL.iso` — the same bank as a ZuluSCSI CD image.

| Preset | `PZT[18]` |
|---|---|
| `FltDcy r=8`  | 8  |
| `FltDcy r=16` | 16 |
| `FltDcy r=24` | 24 |
| `FltDcy r=32` | 32 |
| `FltDcy r=48` | 48 |
| `FltDcy r=64` | 64 |

Each preset plays a sustained 110 Hz sawtooth through a **resonant 4-pole
low-pass** (base cutoff low, resonance 0.75) with a **full positive filter
envelope**: the cutoff snaps fully open on the attack, then Decay-1 sweeps it
back down to the base cutoff. The rate bytes are written exactly (via
`filter_env_decay = _fenv_seconds(rate)`), so they do **not** depend on the
calibration being correct.

---

## Step 2: Load on the E4XT and listen

1. Copy `FLT_DECAY_CAL.iso` to the ZuluSCSI SD card (rename `CD1.iso`).
2. **Load → CD-ROM → FLT_DECAY_CAL**.
3. For each preset, **play and hold a low note** (e.g. C2 / MIDI 36).
4. You should hear the resonant cutoff snap open, then sweep **down** to the
   dark base over the Decay-1 time. Higher preset number → slower sweep
   (if the filter shares the amp curve).

If you hear **no sweep**, the filter envelope amount or resonance isn't being
applied — report back.

---

## Step 3: Record the time → byte mapping

Time the downward filter sweep (cutoff-open peak to settled base) for each
preset and fill in:

| `PZT[18]` | filter-sweep time (s) | amp curve (reference) |
|---|---|---|
| 8  | ______ | 0.034 |
| 16 | ______ | 0.098 |
| 24 | ______ | 0.169 |
| 32 | ______ | 0.198 |
| 48 | ______ | 0.454 |
| 64 | ______ | 1.225 |

Tip: record all 6 presets in order (short silence gaps between) into one WAV and
let the analyzer measure them:

```bash
python3 tests/re_banks/analyze_envelope_recording.py rec.wav --mode filter --notes 6
```

It segments the notes and reports each one's filter-sweep time (spectral-centroid
peak→settle) next to its rate. Or send me the WAV and I'll run it.

---

## Step 4: Resolve

- **If the measured times match the amp column** (within the log-fit residual,
  R²≈0.96): the amp and filter envelopes share one calibration. Document this in
  `RESOLUTION_NOTES.md` §17 and close Gap A — no code change needed.
- **If they differ**: fit a separate `(A, K)` pair to the filter (time, rate)
  points and split `_fenv_rate()` / `_fenv_seconds()` in
  `writers/e4b_writer.py` into amp and filter variants (and mirror the inverse
  in `parsers/e4b_parser.py`).

Three good points (8, 32, 64) are enough to decide; six gives a clean fit.
