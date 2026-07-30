<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: MPC 3.x `.xpm` parameter identification & verification

> **STATUS: OPEN — not started.** The reader exists and is structurally
> correct (`docs/RESOLUTION_NOTES.md` §MPC3XPM), but every parameter *scale*
> is unverified, because the only local files are MPC Auto Sampler output with
> every value at its default. This document is the plan to fix that.

## Why this is unusually cheap

MPC 3 programs are **gzip + JSON**, not a binary blob. So the classic
one-parameter-at-a-time differential works without any byte hunting: change a
single control on the hardware, export, and diff the JSON. This is the MPC
equivalent of the Gotek disk-diff method used for the K2000
(§KRZ program-param RE) — but easier, because the fields are self-describing.

The lever is already written:

```bash
# two files: what changed?
python3 tests/re_banks/mpc3_xpm_diff.py base.xpm changed.xpm

# a sweep: which path carries the series, and on what scale?
python3 tests/re_banks/mpc3_xpm_diff.py --grep cutoff sweep_*.xpm
```

Sweep mode prints the value series in order, which is what distinguishes a
normalised 0–1 control from seconds, cents, or an enum.

## Method

**Per parameter, five steps:**

1. On the MPC, start from the **baseline program** (below) and change *one*
   control to 3–5 values spanning its range, exporting after each. Name the
   exports `<param>_<uivalue>.xpm` so the series is self-documenting.
2. Run the sweep diff. Confirm **exactly one** JSON path varies — if more do,
   the control is compound (e.g. tempo-sync changes both a value and a mode).
3. Record the UI value → JSON value mapping in the results table.
4. Derive the encoding: linear 0–1, seconds, cents, dB, or an enum index.
5. Update `parsers/xpm_parser._mpc3_to_xml()` if the mapping differs from what
   is assumed today, and note it in §MPC3XPM.

**Baseline program.** One keygroup, one layer, one short sample, every control
at default, saved once and reused as the diff reference for every sweep. Keep
it in `~/temp/mpc3_re/baseline.xpm`.

**Guard against layout drift.** The MPC may rewrite unrelated fields on every
save (counters, seeds, timestamps). Do one **null sweep** first — save the
baseline twice without touching anything and diff — to learn which paths are
noise, and ignore them thereafter.

---

## Checklist

### A. Confirm the things currently assumed

- [ ] **A1 `filterType` enumeration.** The single most important unknown:
      `_XPM_FILTER_TYPE` maps MPC 2.x integers, and whether MPC 3 kept that
      ordering is **unverified** (the manual defers to a glossary that does not
      extract from the PDF). Sweep every filter type by name and record the
      integer. *Until this is done, a converted program that actually uses a
      filter cannot be trusted.*
- [ ] **A2 `rootNote` is 1-based.** Strongly evidenced (all 71 local roots match
      the note number in each sample's filename after `-1`) but never set
      deliberately. Set a known root and confirm.
- [ ] **A3 `filterCutoff` / `filterResonance` scale.** Assumed normalised 0–1,
      as in MPC 2.x. Sweep against the UI readout; note the manual quotes
      resonance advice in "values lower than 80", implying a 0–100 UI scale.
- [ ] **A4 Envelope times.** `_xpm_env_to_seconds()` is hardware-measured on an
      **MPC One running 2.x**. Confirm MPC 3 did not change the curve —
      sweep Attack/Decay/Release against a stopwatch or a recorded tail.
- [ ] **A5 `value0` = Filter 1 / LFO 1.** Manual-confirmed, but verify by
      setting Filter 2 only and checking `value1` moves, not `value0`.

### B. Parameters we read but cannot verify

- [ ] **B1 Layer `volume`** — `{gainCoefficient, controlValue, law}`. Which
      field does the UI drive, and is `gainCoefficient` linear or dB?
- [ ] **B2 Layer `pan`** — assumed 0–1 with 0.5 centre.
- [ ] **B3 `coarseTune` / `fineTune`** — semitones and cents? Sweep ±.
- [ ] **B4 `velocityStart` / `velocityEnd`** — assumed 0–127 direct.
- [ ] **B5 Loop fields** — the two-tier scheme
      (`layerLoopModeOverridesSliceLoopMode`) is adopted from ConvertWithMoss
      on their authority. Make a program with a real sustain loop and confirm
      which tier the MPC writes, and what `loopMode` integers mean.

### C. Parameters we currently drop (decide whether to implement)

- [ ] **C1 Envelope Hold + Delay.** E4B envelopes are 6-stage, so the target
      can carry them; our `Envelope` dataclass is the limit. Sweep to get the
      scale, then decide on the model change.
- [ ] **C2 `AD` vs ADSR.** Implemented as "AD ⇒ sustain 0" from the manual.
      Confirm on hardware that an AD envelope really decays to silence.
- [ ] **C3 Filter 2 + `filterBlend` + `filterSerialRouting`.**
- [ ] **C4 `pitchEnvelope`** (EOS has a routable aux envelope as a target).
- [ ] **C5 Envelope curves** (`AttackCurve`/`DecayCurve`/`ReleaseCurve`,
      default 0.375 — is 0.375 linear, or is 0.5?).
- [ ] **C6 `tempoSync` / `TimeScaling`** — both change what an envelope time
      *means*, so they must be read before trusting any time value.
- [ ] **C7 `direction`** → reversed playback (ConvertWithMoss implements it).
- [ ] **C8 Velocity modulation** — `velocityToStart`, `velocityToPan`,
      `velocityToPitch`, `VelocityToAttack`, `velocitySensitivity`.

### D. Coverage beyond the auto-sampler shape

- [ ] **D1 Multi-layer keygroup** (up to 8 samples per keygroup) with real
      velocity splits — exercises the lane allocation the XML path does.
- [ ] **D2 A drum program** (`type != 1`) — do we handle or reject it?
- [ ] **D3 `SerialisableTrackData` / `SerialisableProjectData`** — CWM extracts
      `data.program` and `data.tracks[].program` filtered to `type == 1`; we
      reject both, so a keygroup program inside a track/project is unreachable.
- [ ] **D4 An oscillator layer** — confirm it arrives as a layer with no
      sample, and decide the behaviour (skip with a warning, most likely).

### E. Cross-checks needing no hardware

- [ ] **E1 Diff our conversion against ConvertWithMoss's** for the same source
      file. Both read the same JSON, so any divergence flags a bug in one of
      them — the same lever that found the KRZ `LYR[6]` and CAL-keymap bugs
      (§KRZ-CWM).
- [ ] **E2 Re-scan the library** for MPC 3 files as more are exported, and
      re-run the structural checks in §MPC3XPM.

---

## Results

*(empty — fill in as sweeps are done, one table per parameter, UI value in the
left column and the JSON value in the right, followed by the derived
encoding.)*
