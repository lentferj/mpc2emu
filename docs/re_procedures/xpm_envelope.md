<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# Hardware RE: Akai MPC (XPM) envelope value → time curve

## Goal

MPC keygroup envelope fields (`VolumeAttack/Decay/Sustain/Release`,
`FilterAttack/Decay/Sustain/Release`) are stored as **normalised 0.0–1.0**
floats. Akai publishes **no** value→time chart, and `parsers/xpm_parser.py`
currently passes those 0–1 values straight through *as seconds*, which is wrong
(a `VolumeDecay` of 0.5 is not 0.5 s). This measures the real curve on an
**MPC One** so the parser can convert correctly.

---

## Step 1: Generate the programs

```bash
cd /home/lentferj/git-repos/mpc2emu
python3 tests/re_banks/gen_xpm_envelope_test.py
```

Produces, in `/home/lentferj/temp/re_xpm_envelope/`:

- `XPM_Tone.wav` — a looping sawtooth (sustains for any envelope length).
- `XPM_VOL_DECAY.xpm` — 9 keygroups, one per key **C1…G#1**, sweeping
  `VolumeDecay` = 0.000, 0.125, … 1.000 (attack 0, **sustain 0** so the note
  decays to silence). Mode-robust.
- `XPM_FLT_DECAY.xpm` — 9 keygroups, same keys/values, sweeping `FilterDecay`
  through a resonant low-pass with a full filter envelope (`FilterEnvAmt` 1,
  `FilterSustain` 0); the amp holds the note so the cutoff sweep is audible.

| Key | MIDI | swept value |
|-----|------|-------------|
| C1  | 36   | 0.000 |
| C#1 | 37   | 0.125 |
| D1  | 38   | 0.250 |
| …   | …    | … |
| G#1 | 44   | 1.000 |

---

## Step 2: Load on the MPC One

1. Copy the whole `re_xpm_envelope/` folder to the MPC (USB/SD); keep the
   `.wav` next to the `.xpm` files.
2. Load `XPM_VOL_DECAY` (browse → the `.xpm`).
3. Play and hold **C1**, then **C#1**, … **G#1**. Each key is one keygroup with
   a known `VolumeDecay`; pitch is constant (key-tracking off).
4. If the MPC won't load the program, report back — the XML can be adjusted to
   match your firmware's exact expectations.

---

## Step 3: Record value → time

For `XPM_VOL_DECAY`, time the amplitude decay (attack peak → silence). For
`XPM_FLT_DECAY`, time the resonant filter sweep-down.

**Easiest: record one take and let the analyzer measure it.** Play the 9 keys
in order (lowest first), each fully decaying, with a short (≥0.3 s) silence gap
between them, into one WAV. Then:

```bash
python3 tests/re_banks/analyze_envelope_recording.py rec.wav            # XPM_VOL_DECAY
python3 tests/re_banks/analyze_envelope_recording.py rec.wav --mode filter  # XPM_FLT_DECAY
```

It auto-segments the 9 notes and prints each one's decay time (the `tau(1/e)`
column is the robust metric) next to its value — recovered within ~1 % on
synthetic tests. Or just send me the WAV and I'll run it.

| value | VolumeDecay time (s) | FilterDecay time (s) |
|-------|----------------------|----------------------|
| 0.000 | ______ | ______ |
| 0.125 | ______ | ______ |
| 0.250 | ______ | ______ |
| 0.375 | ______ | ______ |
| 0.500 | ______ | ______ |
| 0.625 | ______ | ______ |
| 0.750 | ______ | ______ |
| 0.875 | ______ | ______ |
| 1.000 | ______ | ______ |

---

## Step 4: Fit and apply

MPC envelope times are typically **exponential** in the 0–1 control value. Fit
the `(value, time)` points (likely `time = a · (e^(b·value) − 1)` or a
power/exponential form) and add a `_xpm_env_to_seconds(value)` converter to
`parsers/xpm_parser.py`, replacing the current pass-through that treats the
0–1 value as seconds (`VolumeAttack/Decay/Release` and the matching
`Filter*` fields).

Notes:
- If `VolumeDecay` and `FilterDecay` give the **same** times, one converter
  covers both envelopes (expected).
- Attack and release almost certainly share the decay curve; spot-check one
  release value on the MPC if you want to confirm before applying it to all
  segments.
- `VolumeSustain` / `FilterSustain` are levels (0–1), not times — no curve.
