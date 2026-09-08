# Measuring the MPC `VelocitySensitivity` → dB law

**Status:** procedure written 2026-09-01, not yet run.
**Generator:** `tests/re_banks/gen_xpm_velocity_test.py`
**Needs:** an MPC One, one new project, one XPM. No panel parameter editing.

## Why

`VelocitySensitivity` sits in every keygroup of every real XPM and mpc2emu read
it for the first time on 2026-09-01. Only the **zero** is carried as a value —
`0.0` means "no velocity response" whatever the law turns out to be, so it
needs no measurement. A non-zero value has no measured dB law, so those
keygroups currently fall back to the target's own default.

Worth the bench time because the field is genuinely used. Over 263 real
presets: **65.8 %** all keygroups at 1.0, **13.7 %** all at 0.0, **11.8 %** a
uniform other value, and **8.7 % mixed within one preset** — that last group
cannot be expressed by a single default at all.

## Why this needs no panel editing

CC cannot reach keygroup parameters on the MPC One (`hw_measure.py` records
this for the S3000XL too, for a different reason). So the sweep is built into
the **file** instead: nine keygroups, one per value, each on its own key.

```
  MIDI 36   VelocitySensitivity 0.000   <- negative control
  MIDI 37                       0.125
  MIDI 38                       0.250
  MIDI 39                       0.375
  MIDI 40                       0.500
  MIDI 41                       0.625
  MIDI 42                       0.750
  MIDI 43                       0.875
  MIDI 44                       1.000
```

Nine keys × nine velocities = one MIDI pass, no hands on the machine.

*(Note numbers, not pitch names: MPC firmware shows note 36 as C1 or C2
depending on its note-naming setting, and a name that means two different keys
is a way to measure the wrong keygroup.)*

## Setup

```bash
python3 tests/re_banks/gen_xpm_velocity_test.py
# -> ~/temp/re_xpm_velocity/XPM_VELSENS.xpm
# -> ~/temp/re_xpm_velocity/XPM_Noise.wav
```

Copy **both** files into a new, otherwise empty MPC project folder and load
`XPM_VELSENS`. The sample must sit beside the `.xpm`; the program references it
by name (`<SampleName>XPM_Noise</SampleName>`) with an empty `<SampleFile/>`,
which is how the MPC's own exports do it.

Rig, from `hw_measure.py`: MIDI on `Scarlett 18i8 USB MIDI 1`, **channel 1**,
audio on `system:capture_5/6`.

## What the program already controls for

- **Every other velocity route pinned to 0** — `VelocityToFilter`,
  `VelocityToFilterEnvelope`, `VelocityToFilterAttack`,
  `VelocityToVolumeAttack`, `VelocityToStart`, `VelocityToPitch`,
  `VelocityToPan`. An **absent** tag takes the MPC's own default, which for
  these is not known to be zero. The K2000 amp measurement lost a day to
  exactly this: ~5 dB of apparent shortfall that was the velocity→filter route,
  not the amp.
- **Filter out of circuit** — `FilterType 0`, `Cutoff 1.0`, `FilterEnvAmt 0`.
  Opening a filter raises loudness as well as brightness; this is a loudness
  measurement.
- **Flat amp envelope** — attack 0, sustain 1.0, so the sustain level is the
  velocity response and nothing else.
- **White noise, seeded** — flat spectrum, steady RMS, byte-identical between
  runs of the generator. Same signal s3ked used for the AKAI tremolo law, so
  the two results are comparable.
- **`KeyTrack False`** — pitch is constant across the nine keys, so nothing
  varies between keygroups except the field under test.

## Run it

Nine velocities per key is enough for a linear fit with slack: **1, 16, 32, 48,
64, 80, 96, 112, 127**. Hold each note long enough to take a clean sustain
window well clear of the attack.

## Check these BEFORE fitting anything

Three gates, each of which has caught a real error on this project:

1. **The negative control must be flat.** Key 36 is `VelocitySensitivity 0.0`.
   Its level across all nine velocities must not move. If it does, something
   else is routed and the run is void — do not "correct" for it.
2. **Both rails, not just the floor.** Confirm nothing clips at the loudest
   note *and* that the quietest is clear of the noise floor. s3ked fitted a
   ceiling-limited AKAI sweep to r² 0.896 and got a plausible law that was pure
   artefact; k2kremote read shallow troughs that were 8.77 dB off the floor and
   attributed a real asymmetry to it.
3. **Show the manipulation is live.** Levels must differ between key 36 and key
   44. A "nothing changed" result is a broken experiment until proven
   otherwise — a K2000 run once reported a null because the probe's editor exit
   answered "No" to the save prompt and discarded every edit.

## What to extract

**PIVOT — read it off, do not assume it.**

- If the level at **v127 is identical across all nine keys**, the pivot is 127
  (attenuate downward; the K2000's convention).
- If the level at **v64 is identical instead**, the pivot is 64 (the AKAI's).
- If neither, fit the crossing. The E4XT's `Vel~` sits at **89.6** despite
  being named for the middle, and its own manual says 63 — so "obviously the
  middle" is not an argument.

**LINEARITY, in both variables.** Linear in velocity, and linear in the
setting. Check both: the AKAI's tremolo turned out to be a **product** of two
fields, and a law fitted against one alone was 9.9× wrong at the other's low
end. The sharp test for a product is equal-product equivalence, not linearity
in each variable separately.

**UNIT.** dB of swing at `VelocitySensitivity` 1.0 — the number mpc2emu needs.
Report it **in the units it was measured in**: dB per velocity unit is what a
straight-line fit returns; a "full swing" is a derived summary and cannot be
quoted without saying across what. v1..v127 is 126 steps; v0..v127 is 127
units; they differ by ~0.8 %. MIDI has no note-on at velocity 0, so 126 is the
one a converter wants.

**ZERO.** Is 0.0 genuinely neutral, or the smallest available value? The
negative control answers it — and this is not a formality, it is the assumption
the shipped reader already relies on.

## Then

Add the law to `models/common.py` beside the other measured constants, with its
provenance and the four answers above. `parsers/xpm_parser.py` currently sets
`velocity_to_volume_requested = True` for any non-zero value; that becomes a
real `velocity_to_volume_db` plus the measured pivot, and the third model state
stops being needed for MPC sources.
