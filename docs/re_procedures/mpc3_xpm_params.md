<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: MPC 3.x `.xpm` parameter identification & verification

> **STATUS: OPEN — hardware-free groundwork done (E1, 2026-07-31).** The
> reader exists and is structurally correct (`docs/RESOLUTION_NOTES.md`
> §MPC3XPM), but most parameter *scales* remain unverified, because the only
> local files are MPC Auto Sampler output with every value at its default.
>
> The ConvertWithMoss crosscheck (**E1**) has now been done and moved four
> items: **A2 is settled** (root note really is 1-based — proven from inside
> the file, no hardware needed), **A1 is corroborated** by two independent
> implementations plus the manual's glossary ordering, **A4 is narrowed** to
> the top of the time range, and **B5's loop scheme** is confirmed as
> two-implementation rather than adopted-on-authority. Everything else still
> needs the MPC.

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

## Bench session protocol

The checklist below is ordered by *topic*. This section is ordered by **value
per export**, so a short session at the MPC still moves the most. Everything
here is hardware-only — the reader, the diff lever and the cross-checks are
already done.

Export everything to `~/temp/mpc3_re/`. The filenames matter: sweep mode sorts
them, so the UI value must be zero-padded (`cutoff_000.xpm`, `cutoff_025.xpm`,
… ) or the series prints out of order and the encoding is unreadable.

### Session 1 — 20 exports, settles the three parameters that change audio

**1. Null sweep first — 2 exports.** Save the baseline program twice, touching
nothing in between: `null_a.xpm`, `null_b.xpm`. Then

```bash
python3 tests/re_banks/mpc3_xpm_diff.py ~/temp/mpc3_re/null_a.xpm ~/temp/mpc3_re/null_b.xpm
```

Every path that shows up here is save-noise and must be ignored for the rest of
the session. **At least one is already known:** `layersv[*]/sliceIncrementRngSeed`
differs across all three local 3.9.0.31 files (124239 / 109445 / 112124) and is
plainly a random seed. Do this step first — without the noise list, a
one-parameter sweep is unreadable.

**2. A3 `filterCutoff` — 5 exports.** The highest-value item, because it now
has a *specific hypothesis to kill*: `docs/RESOLUTION_NOTES.md` §CUTOFFKNOB
records ConvertWithMoss's claimed curve (140-semitone log, 32.7 Hz – 106.3 kHz).
Set the filter to a plain low-pass and sweep **Cutoff** across its UI range —
`cutoff_000`, `cutoff_025`, `cutoff_050`, `cutoff_075`, `cutoff_100` —
recording the **UI readout** for each, which is the whole point (if the UI
shows Hz, the curve falls straight out; if it shows 0–100, we get the JSON
scale but still need the Hz another way).

```bash
python3 tests/re_banks/mpc3_xpm_diff.py --grep cutoff ~/temp/mpc3_re/cutoff_*.xpm
```

Confirm exactly one path varies. Then check the JSON series against
§CUTOFFKNOB: if `n = 0.75` reads ~14 kHz in the UI, CWM's curve is right and
three parsers can be fixed; if it reads ~4.5 kHz, our current writer is right
and CWM's constant is wrong. Either answer closes the item.

**3. A4 envelope top-of-range — 3 exports.** Only the **top** is in doubt
(ours 13.9 s vs CWM's 100 s at v = 1.0; they agree at the bottom). Set
**Release** to maximum, minimum, and midpoint: `release_max`, `release_min`,
`release_mid`. Then hold and release a note on the max one and **time the tail
with a stopwatch or a recording**. 14 s and 100 s are not close — a single
timing settles it, and no JSON reading can.

**4. A5 filter slot — 1 export.** Set **Filter 2 only**, leave Filter 1 at
default, export as `filter2_only.xpm`, and confirm `value1` moves while
`value0` does not. One export, removes an assumption underneath every filter
value we read.

**5. A1 filter enum, types 19–28 — 10 exports.** Types 1–18 and 29 are already
corroborated three ways; **19–28 (Band-Boost / Model / Vocal) are the ones with
no second opinion** — mpc2emu maps them, ConvertWithMoss drops them. One export
per type, named for the UI's own name for it (`ftype_bandboost1.xpm`, …), then
sweep and read off the integers. If time runs out, this is the item to cut —
it costs the most exports and mis-mapping a filter type is audible but not
silent-breaking.

### Session 2 — the B and D items

B1–B4 (volume law, pan, tune, velocity) are each a 3-export sweep on the same
pattern. **D1** (a real multi-layer keygroup with velocity splits) and **D2**
(a drum program) are worth more than any single B item, because they exercise
whole code paths that no local file reaches — build one of each by hand and
just convert it, rather than sweeping.

### What not to spend bench time on

**A2 is settled** — `rootNote` is 1-based, proven from inside the file. **E1,
E3 and D3 are done** — E3 (deterministic `sampleFile` resolution) and D3
(track/project containers) were software work and landed 2026-08-03.

The one thing D3 leaves for the bench is **D5**: it was verified against
synthesized containers, so two real exports — a keygroup program inside a
track, and a project with two keygroup tracks plus a drum track — would
confirm the field names and the `type == 1` filter on genuine MPC output.
Two exports, no sweeps; worth folding into session 1 if the MPC is already on.

---

## Checklist

### A. Confirm the things currently assumed

- [ ] **A1 `filterType` enumeration.** *Downgraded from "the single most
      important unknown" to "corroborated, wants one confirming sweep"* by E1
      (2026-07-31). Three independent lines now agree that MPC 3 kept MPC 2's
      ordering:
      1. ConvertWithMoss applies **one** table (`MPCFilter`) to the MPC 2.x
         XML `<FilterType>`, the MPC 3 JSON `filterType`, *and* its XPM
         writer — and it matches `_XPM_FILTER_TYPE` on every index it defines
         (1–5 Low 1/2/4/6/8-pole, 6–10 High, 11–14 Band, 15–18 BandStop, 29
         MPC3000 LPF).
      2. The manual's glossary lists the filter **families in that same
         order** (low-pass, high-pass, band-pass, band-stop, band-boost,
         Model, Vocal, MPC3000 LPF), and confirms 1/2/6/8-pole variants exist
         — which is what makes the indices come out where they do.
      3. Index 29 = MPC3000 LPF independently in both implementations.
      Still worth **one** sweep to confirm, but a converted program with a
      filter is no longer untrustworthy by default. Sweep every filter type by
      name and record the integer; pay particular attention to **19–28**
      (Band-Boost / Model / Vocal), which mpc2emu maps and CWM does not, so
      there is no second opinion on those.
- [x] **A2 `rootNote` is 1-based.** **Settled without hardware** by E1. The
      same JSON carries `samples[].metadata.rootNote`, which is **0-based**
      (it equals the note number in the sample's own filename), alongside
      `layersv[].rootNote`, which is that number **+ 1**. Two encodings of the
      same fact in one file, agreeing on 71/71 layers across all three files.
      A deliberate-root sweep would still be nice, but nothing hinges on it.
      *(This is also a live bug in CWM, which reads both raw — see TODO.md.)*
- [ ] **A3 `filterCutoff` / `filterResonance` scale.** Assumed normalised 0–1,
      as in MPC 2.x. Sweep against the UI readout; note the manual quotes
      resonance advice in "values lower than 80", implying a 0–100 UI scale.
- [ ] **A4 Envelope times.** `_xpm_env_to_seconds()` is hardware-measured on an
      **MPC One running 2.x**. Confirm MPC 3 did not change the curve —
      sweep Attack/Decay/Release against a stopwatch or a recorded tail.
      **E1 narrowed this to the range constant, not the law.** CWM uses
      `t = min · exp(v · ln(max/min))` with `min = 0.001 s`, `max = 100 s`;
      ours is `t = 0.00079 · exp(9.78 · v)`. Same exponential law, and they
      agree at the bottom (0.79 ms vs 1 ms at v=0) — but ours tops out at
      **13.9 s** and theirs at **100 s**. Ours is hardware-measured; theirs is
      two round numbers with no cited source, so ours is the better bet. The
      sweep only needs to nail the **top** of the range: one long Release at
      v=1.0, timed. *(The manual does not settle it — the "0 ms – 32 s" ranges
      in the parameter appendix belong to the AIR plugin instruments, not to
      keygroup programs. Checked and rejected.)*
- [ ] **A5 `value0` = Filter 1 / LFO 1.** Manual-confirmed, but verify by
      setting Filter 2 only and checking `value1` moves, not `value0`.

### B. Parameters we read but cannot verify

- [ ] **B1 Layer `volume`** — `{gainCoefficient, controlValue, law}`. Which
      field does the UI drive, and is `gainCoefficient` linear or dB?
- [ ] **B2 Layer `pan`** — assumed 0–1 with 0.5 centre.
- [ ] **B3 `coarseTune` / `fineTune`** — semitones and cents? Sweep ±.
- [ ] **B4 `velocityStart` / `velocityEnd`** — assumed 0–127 direct.
- [ ] **B5 Loop fields** — the two-tier scheme
      (`layerLoopModeOverridesSliceLoopMode`). Re-read against CWM in E1: our
      tier selection, the `mode > 0 && end > 0` guard and the field names all
      match theirs exactly, so this is a faithful adoption rather than a
      misreading — but it is still *their* reading, not evidence. Make a
      program with a real sustain loop and confirm which tier the MPC writes,
      and what `loopMode` integers mean. **Also unread on our side:**
      `loopCrossfadeLength` (CWM turns it into a crossfade fraction of the loop
      length) and `loopFineTune`.

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
- [x] **D3 `SerialisableTrackData` / `SerialisableProjectData`** — **DONE
      2026-08-03, no hardware.** `_mpc3_program_nodes()` extracts
      `data.program` (track) and `data.tracks[].program` (project), filtered to
      `type == 1`, and folds the root-level `samples[]` into each program so
      `_mpc3_to_xml` still reads one self-contained dict. A payload with no
      keygroup program now refuses with a sentence saying so instead of
      "unsupported payload". **Known limitation:** a project holding *several*
      keygroup programs converts only the first and warns, naming the ones it
      skipped — `parse_xpm` builds one Preset per file. Logged in TODO.md.
      Verified on synthetic track/project containers (a real one still has to
      come off the MPC — see D5).
- [ ] **D5 A real track / project export.** *(New, from D3.)* D3 was built and
      tested against synthesized containers, because no local file is one. Save
      a keygroup program inside a track, and a project with two keygroup tracks
      plus a drum track, and confirm the field names and the `type == 1`
      filter hold on real MPC output. Cheap: two exports, no sweeps.
- [ ] **D4 An oscillator layer** — confirm it arrives as a layer with no
      sample, and decide the behaviour (skip with a warning, most likely).

### E. Cross-checks needing no hardware

- [x] **E1 Diff our conversion against ConvertWithMoss's** — **DONE
      2026-07-31**, against CWM `e8027b9d`. Done by reading their
      `MPCModernDetector` / `MPCEnvelopesAndFilter` / `MPCFilter` against our
      `_mpc3_to_xml()` field by field, then testing each divergence against the
      three real 3.9.0.31 files. Outcome:
      - **Agreed** on filter enumeration, the `{value0,value1}` slot reading,
        AD ⇒ sustain 0, and the two-tier loop scheme — so those are now
        two-implementation results, not single-source assumptions.
      - **Three bugs found in CWM** (rootNote off-by-one, dead global-envelope
        branch, filter types 19–28 dropped) — logged in TODO.md for Jan's
        existing CWM conversation.
      - **Two real losses found on our side and fixed:** program/keygroup
        `transpose` was dropped entirely, and `samples[].metadata`
        (`rootNote` fallback + `tune`) was unread. Both verified by synthetic
        mutation of a real file, since every local value is 0/default.
      - **A1, A2 and A4 all narrowed** — see above. A2 is settled.
- [ ] **E2 Re-scan the library** for MPC 3 files as more are exported, and
      re-run the structural checks in §MPC3XPM.
- [x] **E3 Resolve samples via `sampleFile` in `<stem>_[ProgramData]/`.**
      **DONE 2026-08-03, no hardware.** `_resolve_mpc3_sample()` builds the
      exact path from the layer's own `sampleFile` and the sibling
      `<stem>_[<Kind>Data]/` folder, falling back to the old `_find_wav()`
      search when either is missing — so re-organised or hand-assembled
      exports keep working, where CWM errors out.
      **The bug it fixes is real, not theoretical**, confirmed with a negative
      control: two programs each holding their own `SHARED.wav`, the decoy
      earlier in traversal order. Old path resolved the decoy (1000 frames),
      new path resolves the right file (8000). All three local 3.9.0.31 files
      convert unchanged (21/25/25 samples).

---

## Results

*(One table per parameter as sweeps are done: UI value on the left, JSON value
on the right, then the derived encoding. Nothing here yet needed the MPC — all
of it came from E1.)*

### A2 `rootNote` basis — SETTLED (2026-07-31, no hardware)

Both roots for the same sample, from the same file. 71/71 layers, all three
local 3.9.0.31 files, zero exceptions:

| sample filename | `samples[].metadata.rootNote` | `layersv[].rootNote` |
|-----------------|------------------------------|----------------------|
| `…-024 C01`     | 24                           | 25                   |
| `…-072 C4`      | 72                           | 72 + 1 = 73          |

**Encoding:** `metadata.rootNote` = 0-based MIDI; `layersv[].rootNote` =
**1-based** (0 = "unset" sentinel). `_mpc3_to_xml()` emits the 1-based
convention and the XML path subtracts 1, which is correct.

### A1 `filterType` — corroborated, not yet swept

| index | family (both implementations agree) |
|-------|-------------------------------------|
| 0     | off                                 |
| 1–5   | Low-pass 1 / 2 / 4 / 6 / 8 pole     |
| 6–10  | High-pass 1 / 2 / 4 / 6 / 8 pole    |
| 11–14 | Band-pass 2 / 4 / 6 / 8 pole        |
| 15–18 | Band-stop 2 / 4 / 6 / 8 pole        |
| 19–22 | Band-boost 2 / 4 / 6 / 8 pole *(mpc2emu only — CWM drops these)* |
| 23–25 | Model 1–3 *(mpc2emu only)*          |
| 26–28 | Vocal 1–3 *(mpc2emu only)*          |
| 29    | MPC3000 LPF (12 dB/oct)             |

All three local files carry instrument-level `filterType: 2` with
`filterCutoff: 1.0` — a 2-pole low-pass held wide open, i.e. inaudible, which
is why the auto-sampler output sounds unfiltered despite a non-zero type.

### A4 envelope time curve — two candidate constants

| | law | v=0 | v=0.5 | v=1 |
|-|-----|-----|-------|-----|
| mpc2emu (HW-measured, MPC One 2.x) | `0.00079·e^(9.78v)` | 0.79 ms | 105 ms | **13.9 s** |
| ConvertWithMoss (round numbers)    | `0.001·e^(11.513v)` | 1.00 ms | 316 ms | **100 s** |

Same family, agreeing near zero and diverging badly at the top. Sweep the
long end to pick one.
