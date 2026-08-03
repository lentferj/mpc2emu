<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: MPC 3.x `.xpm` parameter identification & verification

> **STATUS: the two scales that change audio are now MEASURED (2026-08-03,
> MPC One 3.9.0.31).**
>
> - **A3 cutoff — DONE.** `f(c) = 21.377 * 728^c` Hz (§MPCCUTOFF).
> - **A4 envelope times — DONE.** `t(v) = 0.001005 * e^(10.3022 v)` s (§MPCENV).
> - **D5 containers — DONE.** `.xty` / `.xpj`, `type == 1` (§MPC3D3).
> - **A2, E1, E3, D3** were already settled without hardware.
>
> Both third-party candidate curves were refuted in the process: CWM's cutoff
> mapping ran 2–6× high, and neither envelope law survived (ours 0.47× at the
> top, theirs 3.33×).
>
> **Still open and still needing the MPC:** A1 (filter-type integers,
> especially 19–28), A3's *resonance* half, A5, all of B, all of C, and D1/D2/D4.
> Those are structural — they need exports, not audio, and batch onto one card
> trip.
>
> **Method note that changed everything:** the data dial is detented and its
> clicks are exactly the `n/127` steps, and the firmware displays envelope
> times in milliseconds. Between them, most remaining *scale* questions can be
> answered by dialling and reading the screen, with audio needed only to
> confirm the UI is truthful (it was, at both ends of the envelope range).

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

## Bench session protocol — ONE card trip

**The expensive operation is not dialling in a parameter, it is moving the SD
card between the MPC and the PC** (Jan, 2026-08-03). So this section is not
ordered by value-per-export and does not propose sessions: it is a single
batch designed so that **nothing here needs a second trip**. Do as much of it
as patience allows in one sitting; anything skipped is a known gap rather than
a forced return.

Everything goes to `~/temp/mpc3_re/`. **The MPC does not allow underscores in
filenames** — use hyphens. Zero-pad the numeric part (`cutoff-000`,
`cutoff-032`, …) so sweep mode sorts the series correctly; unpadded names print
out of order and the encoding becomes unreadable.

### The finding that shapes this list

The MPC's normalised controls are **`n / 127` in float32** — the default amp
`Decay` of `0.04724409431219101` is exactly `float32(6/127)`. The parameter
domain is 127 integer steps, and **the JSON therefore contains no Hz and no
seconds anywhere**.

That has a hard consequence: **no number of exports can settle A3 (cutoff in
Hz) or A4 (envelope times in seconds).** A diff can only ever recover the knob
position. ConvertWithMoss's `normalizeCutoff` (§CUTOFFKNOB) is not reading an
MPC scale — it is *inventing* a Hz interpretation of a knob position.

So the trip has three parts, and **part 2 is the one that is easy to forget and
expensive to forget**.

### Part 1 — exports (one control off baseline, everything else default)

Save the baseline program once as `baseline.xpm`, then change exactly one
control per export. The null sweep is already done and came back clean (only
`/name` differs between two saves), so **the save is byte-stable and every
sweep below will show exactly one moving path.**

| item | exports | names |
|------|---------|-------|
| A1 filter enum | one per type, **19–28 first** | `ftype-<uiname>` |
| A3 cutoff | 5 | `cutoff-000/032/064/096/127` |
| A3 resonance | 3 | `res-000/064/127` |
| A4 amp envelope | 3 each for A/D/R | `amp-attack-000/064/127`, `amp-decay-…`, `amp-release-…` |
| A5 filter slot | 1 | `filter2-only` (Filter **2** set, Filter 1 default) |
| B1 volume law | 3 | `vol-000/064/127` |
| B2 pan | 3 | `pan-000/064/127` |
| B3 tune | 4 | `tune-coarse-minus12`, `tune-coarse-plus12`, `tune-fine-minus50`, `tune-fine-plus50` |
| B4 velocity | 1 | `vel-split` (two layers, 0–63 and 64–127) |
| B5 loop | 2 | `loop-sustain` (a real sustain loop), `loop-xfade` (crossfade set) |
| C1 hold / delay | 2 | `hold-064`, `delay-064` |
| C2 AD mode | 1 | `ad-mode` |
| C3 filter 2 | 2 | `filter-blend-064`, `filter-serial` |
| C4 pitch envelope | 1 | `pitchenv-127` |
| C5 curves | 2 | `curve-attack-000`, `curve-attack-127` |
| C6 tempo sync | 1 | `tempo-sync-on` |
| C7 direction | 1 | `reverse` |
| C8 velocity mod | 4 | `vel-to-start`, `vel-to-pan`, `vel-to-pitch`, `vel-sens` |
| D1 multi-layer | 1 | `multilayer-4` (4 layers, real velocity splits) |
| D2 drum program | 1 | `drum-standalone` (a drum program saved on its own) |
| D4 oscillator | 1 | `osc-layer` (a layer with an oscillator, no sample) |

`~40` exports. Each is one control change and a save.

### Part 2 — audio (**mostly superseded: the MPC is on the bench rig now**)

The card-trip framing above assumed audio had to be *recorded on the MPC*. It
does not: the MPC One is wired into the same rig as the E4XT and K2000R —
MIDI on the Scarlett port channel 1, audio on `system:capture_5/6` — so
`tests/re_banks/hw_measure.py --device mpc` drives and records it directly from
the PC. **A3 and A4 were both settled this way and need no further audio.**

What that leaves for audio, all cheap now that the rig is wired:

- **C2 AD mode.** Record a held note in AD mode — does it decay to silence
  while the key is still down?
- **C5 curves.** Record attack at curve `0.375` (default), `0`, and max. The
  question is whether 0.375 is linear.
- **A1 filter slopes.** A quick confirmation that `Low1` is 6 dB/oct against
  `Low2`'s measured 12 — cheaper than reasoning about the enum from names.

**Note on CC automation: it does not work for keygroup parameters.** MPC
forums and Akai's own docs agree there is no MIDI-learn path to a keygroup
filter, and the commonly suggested workaround — insert a filter FX and control
*that* — is actively wrong for calibration, since it measures a different
filter from the one whose knob value the JSON stores. Everything above was
measured by dialling by hand and recording, which worked fine.

### Part 3 — a text file on the card

The cheapest item here and the one that can make half of part 2 unnecessary.
Create `ui-readouts.txt` next to the exports and write down **what the MPC's
screen actually displays** for each control:

- Cutoff — Hz? `0–127`? `0–100`? (If it shows Hz, A3 is settled on the spot.)
- Resonance — the manual's "values lower than 80" hints at a 0–100 display.
- Envelope A/D/R — ms/seconds, or a bare number?
- Volume — dB or normalised? Pan — L/R or 0–127?

Also note the UI name of each filter type next to its index as you sweep A1;
that mapping is the whole deliverable for that item.

### Insurance — cheap now, expensive to come back for

- A **second null sweep** at the end of the session (`null-end.xpm`), to prove
  nothing drifted across ~40 saves.
- One export with **two filters and an LFO active at once**, to confirm the
  `value0` / `value1` slot reading holds when both slots are genuinely in use.
- A project (`.xpj`) containing **three or more** auto-sampled keygroup tracks —
  the real target of the project-as-bank work, and the only way to test more
  than two presets in one file.

### What not to spend bench time on

**A2 is settled** — `rootNote` is 1-based, proven from inside the file. **E1,
E3 and D3 are done** — E3 (deterministic `sampleFile` resolution) and D3
(track/project containers) were software work and landed 2026-08-03.

**D5 is done too** (2026-08-03) — see the results section. `type == 1` is
confirmed against real MPC output, and the real container extensions turned out
to be `.xty` and `.xpj`, not `.xpm`.

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
- [x] **A3 `filterCutoff` scale.** **DONE 2026-08-03, hardware.** Measured on
      an MPC One 3.9.0.31: `f(c) = 21.377 * 728^c` Hz, 21.4 Hz to 15.6 kHz,
      eight points, max residual 2.6%, knob 88 predicted before measurement to
      +0.9%. Implemented in `xpm_parser._xpm3_cutoff_to_hz`. See
      `docs/RESOLUTION_NOTES.md` §MPCCUTOFF. **`filterResonance` is still
      unmeasured** — only the cutoff half of this item is closed.
- [x] **A4 Envelope times.** **DONE 2026-08-03, hardware.**
      `t(v) = 0.001005 * e^(10.3022 v)` s, 1 ms to 30 s, five points, max
      residual 0.56%, knob 96 predicted before measurement to +0.08%. The
      displayed number is time-to-silence, confirmed acoustically. Attack,
      Decay and Release all measured identical, so one curve still covers every
      segment; Hold and Delay assumed, not measured. See §MPCENV. Original
      note follows: `_xpm_env_to_seconds()` is hardware-measured on an
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

### D5 container shapes — SETTLED (2026-08-03, real MPC One 3.9.0.31)

Jan exported a baseline program, a track and a project from an MPC One on
firmware **3.9.0.31**. Four results:

**1. The containers do not share the `.xpm` extension.**

| payload | extension | sample folder |
|---------|-----------|---------------|
| `SerialisableProgramData` | `.xpm` | `<stem>_[ProgramData]/` |
| `SerialisableTrackData` | **`.xty`** | `<stem>_[TrackData]/` |
| `SerialisableProjectData` | **`.xpj`** | `<stem>_[ProjectData]/` |

The folder naming E3 assumes is confirmed exactly. The extensions were *not*
what D3 assumed, and `parsers/registry.py` keys the CLI on extension — so
track and project files were being ignored by `convert.py` even though
`parse_xpm()` handles them correctly when called directly. ConvertWithMoss
registers all three (`MPCModernDetector`: `".xpm", ".xpj", ".xty"`).

**2. `type == 1` is confirmed, and the filter is essential rather than
cosmetic.** Observed values in a real project:

| type | track kind |
|------|-----------|
| 0 | drum |
| **1** | **keygroup** |
| 7 | return |
| 8 | submix |
| 9 | output |

A three-track project serialises **32 tracks** — the two keygroup programs plus
30 submix / return / output buses. Without the type filter a project is
unconvertible noise.

**3. One D3 assumption was wrong (harmlessly).** The implementation folds the
payload-root `samples[]` into each program node, on the assumption that track
and project programs do not carry their own. Real output shows **every program
node has its own `samples`**; the root copy in a `.xpj` is a project-wide pool
of all sixteen. The fold-in is guarded by `if not prog.get('samples')`, so it
is a no-op rather than a bug — but it is not doing what its comment claimed.

**4. The save is byte-stable.** The null sweep (same program saved twice)
differs in exactly one path, `/name`, and only because the second save was
given a different filename. **There is no save-noise at all**, so every
parameter sweep shows exactly one moving path. This corrects an earlier note in
this document which called `sliceIncrementRngSeed` save-noise: it is stable
across saves of one program and differs only *between* programs.

### Normalised controls are `n / 127` — SETTLED (2026-08-03, no hardware)

Derived from the baseline export, not measured. The default amp-envelope
`Decay` is `0.04724409431219101`, which is **exactly `float32(6 / 127)`**. The
MPC's normalised parameter domain is 127 integer steps stored as float32.

**Consequence, and it is the important one:** the JSON contains **no Hz and no
seconds anywhere**. A parameter diff can only ever recover a knob position, so
**A3 and A4 cannot be settled by exporting** — they need recorded audio. This
is also why §CUTOFFKNOB should be read as ConvertWithMoss *inventing* a Hz
interpretation of a knob position rather than reporting an MPC scale.

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
