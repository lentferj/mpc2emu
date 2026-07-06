<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Aural-comparison notes

Jan's by-ear A/B findings (converted E4XT vs original MPC), with my analysis.

## Implementation status (2026-06-13)

**✅ IMPLEMENTED (no RE needed):**
- **§C LFO rate** — `lfo_knob_to_hz` uses the measured MPC curve `0.0202·e^(9.195·knob)`.
- **§E/§F Root note** — `load_wav` reads the WAV `smpl` unity note; `xpm_parser`
  uses it as the RootNote=0 playback root (fixes +36) and as the sample root_note.
- **§N ODS mapping** — content-signature mapping in `rebuild_all.py`.
- **§O Filter env** — `e4b_writer` always writes the env shape; `e4b_parser` reads
  it even at amount 0 (survives repack).
- **§Q LFO S&H** — `SampHold → 'hemiquaver'` in `_xpm_lfo_shape`.

**⏳ STASHED — need hardware RE / more data** (RE bank: `tests/re_banks/gen_re_suite.py`,
procedures: `docs/re_procedures/re_suite.md`):
- **§G/§R-window** voice key-window bytes (so a voice claims only its zone span).
- **§K/§L** MPC band-stop → E4XT **Swept EQ (cut)** byte + cut/bandwidth params.
- **§D/§P** LFO clock-sync: Clock-Divisor source ids + LFO-Trigger dest ids + the
  MPC `<Sync>` index→division table (+ tempo assumption).
- **§S** Triangle/sine phase: negate-cord-amount — confirm the direction convention.
- **§B** SawDown waveform (full E4XT LFO-shape set, or the §S negate route).
- **§J / §O-cal** envelope-time calibration (MPC value→seconds curve; have 1 decay point).

---

## Bass-MS20-Patch  — `FEATUREDEMO_02.E4B [03]`  (src: `Bass-MS20-Patch 2c.xpm`)

### A. Multisample doesn't fill its claimed key range
**Jan:** V1 multisample claims to span the whole C-2 ↔ G8 range, but the lowest
(S167) and highest (S166) sample don't extend to the lowest/highest key.
**Jan (follow-up):** in the MPC program editor KG1 is indicated as spanning
**C1–D1**, yet **C0 still makes a sound** — so the MPC plays notes *below* the
lowest keygroup's stated range using that lowest sample (pitched down).

**Analysis:** the XPM has 15 real samples spanning **keys 36–84** (C1 … Gb4),
each a 3-key zone (36-38, 39-41, … 78-84), plus ~113 *empty* keygroup slots that
claim 0-127 with no sample. Our writer emits secondary zones at the real 36–84
spans but gives the **voice no key-window from the zones**, so the E4XT voice
shows the full-range default (C-2..G8) while keys 0–35 and 85–127 have no zone →
silent. Mechanism of the "C-2..G8" claim is the primary-zone / voice default
(`_PRIMARY_ZONE_TMPL` + no vpar key-window write) — confirm exact byte.

Jan's MPC observation is the key data point: the MPC **extends the edge keygroups
to the keyboard ends** (lowest KG plays below its indicated low note, pitched
down; by symmetry the highest plays above). The "C1–D1" label is just the zone's
*nominal* span, not its playable span. So the faithful behavior is to make the
edge zones cover 0 / 127, which our converter currently does NOT do.

**Fix direction → (1) confirmed by Jan's MPC test:**
- (1) Extend the lowest zone's `lo_key`→0 and the highest zone's `hi_key`→127 so
  the edge samples play across the whole keyboard (matches the MPC: C0 sounds
  from the C1 sample). *This is the correct one.*
- (2) ~~Clamp the voice window to 36–84~~ — rejected: would silence C0 etc., the
  opposite of the MPC.
- Cleanest in the **parser**: after building a voice's key-sorted zones, stretch
  the first zone's `lo_key` to 0 and the last zone's `hi_key` to 127 (per voice,
  only for genuine key-spread multisamples — not velocity stacks or single full-
  range zones). Verify it doesn't fight the existing `cap_voices_by_coverage` /
  non-transpose paths.

### B. LFO waveform `SawDown` not reproducible
**Jan:** MPC waveform is "SawD" (Saw Down), which the E4XT doesn't have.

**Analysis:** XPM `<Type>SawDown`. `parsers/xpm_parser._xpm_lfo_shape` collapses
both `Saw` and `SawDown` → `'sawtooth'` (loses the down direction). Our RE'd
E4XT shape set (`_LFO_SHAPE_NAME`) = triangle/sine/sawtooth/square/hemiquaver/
random — **no descending saw**.

**Fix direction:** RE the *full* E4XT LFO shape byte set from the EOS UI (we only
mapped a handful). If a descending-saw shape exists, map `SawDown` → it; else
best-effort (`sawtooth`) and document the gap. MPC shape list (manual): Sine,
Tri, S&H, Saw, SawD, Sqr, Noise.

### C. LFO rate ~2× too fast (knob→Hz calibration) — ✅ FIXED 2026-06-13
**Jan:** MPC rate is 2.00 Hz at this patch; E4XT comes out at 4.12 Hz.

**RESOLVED:** `lfo_knob_to_hz` now uses the measured MPC law `Hz = 0.0202·e^(9.195·knob)`
(`models/common.py`).  Verified: Bass-MS20 2c now converts to **2.005 Hz** (was
4.12); all 6 calibration points reproduce within rounding; pipeline smoke test
passes.  Residual hardware limits (not bugs): E4XT LFO floor 0.08 Hz (knob 0 wants
0.02) and ceiling 18.01 Hz (knob ≳0.74 wants >18) — both clamp.  **Feature-demo
banks still hold the old 4.12 rate until a rebuild.**

**Analysis:** `models/common.lfo_knob_to_hz(0.5)` returns **4.12 Hz** because it
equates the MPC `<Rate>` *knob position* with the E4XT *byte position* (0.5 →
byte 64 → 4.12 Hz). But the MPC knob 0.5 actually = **2.00 Hz** — the two devices
have different rate scales, so the position-correspondence assumption is wrong
(≈2× too fast at midpoint). Affects **all** non-synced MPC LFO patches.

**Fix direction:** recalibrate `lfo_knob_to_hz` against the MPC's real knob→Hz
curve.

**Calibration data points** (Jan reads the LFO Rate Hz on the MPC for each; all
free-run / Sync=None except where noted, so the on-screen value is the knob's Hz):

| `<Rate>` | our Hz (wrong) | **MPC Hz** (measured) | patch |
|---------:|---------------:|:---------------------:|-------|
| 0.000 | 0.08 | **0.02**  | Bass-Pulse-Bass 2c.xpm (Triangle) |
| 0.200 | ~0.6 | **0.13**  | Bass-Squelch-Windy City.xpm (Sine) |
| 0.350 | ~1.7 | **0.50**  | Bass-Twisted-Harmonical.xpm (Sine) |
| 0.500 | 4.12 | **2.00**  | 11 OB Thick Pad.xpm (Sine) — matches Bass-MS20-Patch 2c (sync'd) |
| 0.650 | ~8   | **7.96**  | Bass-DP Trimmer.xpm (SawDown) |
| 0.760 | ~13  | **21.93** | Lead-TS Hiss Sub.xpm (SawUp) |

**FITTED CURVE (2026-06-13):  Hz = 0.0202 · e^(9.195 · knob)**  (= `0.0202 ×
9856^knob`).  ln(Hz) linear in knob, slope 9.195 / intercept −3.901; matches all
6 points within rounding.  Corpus `<Rate>` maxes at 0.78, so the curve is
anchored over the used range; extrapolated knob 1.0 ≈ 200 Hz.

**Action plan (when greenlit):** in `lfo_knob_to_hz`, return this MPC Hz directly
instead of the byte-position shortcut.  Then the writer's Hz→E4XT-rate-byte step
maps it onto the hardware — **but the E4XT LFO max is only ~18.01 Hz** (rate byte
127), so MPC rates above that (knob ≳ 0.74, e.g. the 21.93 Hz patch) must **clamp
to the E4XT max** — a genuine hardware ceiling, not reproducible.  Most patches
sit ≤ 0.65 (≤ ~8 Hz) so they're fine.

### D. LFO tempo-sync ignored
**Jan:** MPC sync = "2 whole notes". Our converter ignores it. E4XT can clock-sync
(tricky); at 100 bpm, E4XT LFO rate ≈ 0.25 Hz comes close. Sync described EOS
manual **p.260ff**.

**Analysis:** XPM `<Sync>19` (= "2 whole notes"). `xpm_parser` reads `<Reset>`
(→ key-sync vs free-run) but **never reads `<Sync>`** (tempo division), so synced
LFOs get the (mis-calibrated) free-run knob rate instead of the tempo rate. When
sync is on, the `<Rate>` knob is irrelevant.

**E4XT mechanism (EOS p.260 "Clock Modulation"):** the Sequencer/Arpeggiator clock
(or external MIDI clock) is a mod source with **6 divisors**: *double-whole,
whole, half, quarter, 8th, 16th* note. To sync an LFO, patch a **Clock Divisor →
LFO Trigger (Trg)** cord (Cord Amount MUST be +); set the LFO rate near the clock
rate for a clean lock. `Clock Divisors` is a mod *source*; `LFO 1/2 Trigger` and
`LFO 1/2 Rates` are mod *destinations* (manual p.262). **"2 whole notes" = the
double-whole-note divisor.**

**Fix options:**
- (1) *Faithful clock-sync:* emit a `Clock Divisor(double-whole) → LFO1 Trigger`
  cord + set LFO rate near the clock rate. Needs RE of the **Clock-Divisor source
  IDs** + **LFO-Trigger destination IDs**, plus the preset/global clock tempo
  (BPM) on the E4XT. Complex; depends on the user's session tempo.
- (2) *Pragmatic free-run:* compute effective Hz from the `<Sync>` division at an
  assumed tempo and write it as a plain free-run rate (loses true sync, right
  speed). Needs the MPC `<Sync>` index→division table (19 = 2 whole notes) and a
  reference BPM (program tempo, else default e.g. 120). At 100 bpm, 2 whole notes
  ≈ 0.21 Hz (Jan: 0.25 close).

**Cross-ref:** the earlier "fixed un-gated LFO→Filter" item
(`RESOLUTION_NOTES.md`) is *confirmed faithful re: gating* — these LFO
waveform/rate/sync points are the remaining, separate fidelity gaps on this patch.

---

## Inst-Pad-JR Lazloz Split — `FEATUREDEMO_03.E4B [03]`
## …and `Inst-Bass-JR Jup` — `FEATUREDEMO_03.E4B [04]` (Jan: "same")

Source: `Jupiter Rising/Inst-Pad-JR Lazloz Split.xpm` — 4 keygroups, each 3
unison layers (A/B/C); KG1(C1)+KG2(C2) on keys 0-59, KG3(C3)+KG4(C4) on 60-127.
All layers RootNote=0, IgnoreBaseNote=False.

### E. Root note wrong → **+36 transposition**  (ROOT CAUSE FOUND)
**Jan:** sonically very close but transposed **+36**; all samples show "Orig: C3".

The samples are rooted at their **WAV `smpl` unity note**: C1=36, C2=48, C3=60,
C4=72. But `xpm_parser` sets `root = lo_key` whenever `RootNote==0` (the MPC
unset sentinel) — so:

| voice | sample unity (true root) | our root_key (=lo_key) | error |
|------|---:|---:|---:|
| V1-3  C1 | 36 | 0  | **+36** ← Jan |
| V4-6  C2 | 48 | 0  | +48 |
| V7-9  C3 | 60 | 60 | 0 (coincidence) |
| V10-12 C4 | 72 | 60 | +12 |

E4XT pitch = unity shifted by (playedKey − root_key); with root_key too low, every
note sounds too high. **Fix:** when `RootNote==0`, use the **sample's WAV smpl
unity note** as root, not `lo_key`. Needs `load_wav` to read the smpl
MIDIUnityNote (offset smpl+12) into `sd.root_note` (it currently reads only the
loop, leaving root_note=60), and `xpm_parser` to use `sd.root_note` for the
RootNote=0 fallback instead of `lo_key`. **Systematic** — same on `Inst-Bass-JR
Jup` and presumably all WAV-rooted RootNote=0 JR patches.

### F. "Orig: C3" on all samples
Our parsed `sample.root_note` is 0 (C1/C2) / 60 (C3/C4), yet the E4XT shows Orig
C3 (=60) for *all*. At fix time, recheck how the writer encodes the sample
original key (E3S1 header / `_sample_display_name` suffix) — it should carry the
true unity (36/48/60/72) once E is fixed.

### G. All voices span C-2 ↔ G8 (voice key-window)
**Jan:** all voices span C-2..G8. Same root cause as the MS20 §A above — the
writer sets **no voice key-window** from the zones, so the E4XT group shows full
range while the secondary zones (0-59 / 60-127) limit actual playback. Shared fix
with §A.

### H. 12 E4XT voices vs "3 Layers" on MPC — **NOT a bug**
**Jan:** stunned the E4XT has 12 voices but the MPC shows 3 layers. Correct
conversion: **4 keygroups × 3 unison layers (A/B/C) = 12**. The MPC GUI shows the
3 layers of *one* keygroup; there are 4 keygroups (KG1+KG2 stacked on the low
half, KG3+KG4 on the high half → 6 unison voices sounding per key). Nothing to fix.

### I. Per-voice detune — **CORRECT** (confirm)
**Jan:** V4-6 ctune+12/ftune+10, V10-12 ftune+16. These match the instrument-level
`TuneCoarse/TuneFine` (KG2: coarse 12 / fine 15¢→+10 in 1/64-st; KG4: fine
25¢→+16) — the intended Lazloz "split" detune, correctly converted. No action.

### J. Amp decay too short
**Jan:** MPC GUI decay = 1.9 s; E4XT sounds like ~0.703 s (matches if MPC decay
dropped to 703 ms). Source `VolumeDecay=0.732283`.
**Analysis:** two-stage undershoot —
1. `_xpm_env_to_seconds(0.732) = 1.018 s` but the MPC shows **1.9 s** → the MPC
   value→seconds curve is too short (~1.9×).
2. that 1.018 s then writes to an E4XT decay byte that plays ~**0.703 s** →
   the seconds→E4XT-rate encoding undershoots too (~1.45×).
End-to-end MPC 1.9 s → E4XT 0.70 s (~2.7× too fast). **Fix needs a calibration
pass like the LFO rate:** gather MPC decay value→seconds points (have one:
0.732→1.9 s) AND verify the E4XT decay-byte→seconds curve. Defer until data
collected.

---

## Synth-MS20-Patch — `FEATUREDEMO_03.E4B [08]`  (src: `Synth-MS20-Patch 10c.xpm`)

**Jan:** "very far off." MPC uses a **band-stop** filter ("dampens only the
frequencies around the cutoff"). Jan left it on our mapped type (Contrary BP) and
adjusted Freq/Q — ≈260 Hz, Q 0 got closer, but his question is: **is there an
E4XT type that better matches a band-stop?** (EOS filter list printed p.343 / PDF 355.)

Source: `FilterType=18 (BS 8P, band-stop/notch)`, `Cutoff=0.04`, `Resonance=0.89`.
Our current map (`_XPM_FILTER_TYPE`): 18 → `0x12` **Contrary Bandpass**. Packed
bank [08]: vpar[58]=0x12, cutoff byte 10 (~85 Hz), Q byte 113. (Filter byte
round-trips cleanly through the repack: parser 0x12→XPM15→writer 0x12.)

### K. E4XT has no true band-stop — but Contrary BP is the WRONG approximation
EOS 4.0 has **21 filter types** (manual p.343-346): LP 2/4/6-pole, HP 2nd/4th,
BP 2nd/4th, Contrary Bandpass, **Swept EQ ×3** (parametric ±24 dB boost/**cut**),
Phaser 1/2 + Bat, Flanger Lite, Vocal ×2, 4 Morph. None is labelled band-stop,
but several make notches.  **Contrary BP is a poor pick** — it's "a novel
*bandpass* where peaks and dips cross midway," not a clean notch.

### L. Better band-stop matches — **DECIDED: Swept EQ (cut)** (Jan, 2026-06-13)
Ranked closest → furthest for an MPC band-stop (single tunable notch):
1. **Swept EQ, 1-octave with gain = CUT** — a parametric EQ cut *is* a band-stop
   (attenuates a band around the centre). Same filter *kind*. Freq = cutoff,
   cut depth ≈ band-stop resonance. ✅ **CHOSEN** — implement MPC BS (15-18) →
   Swept-EQ-cut when we start.
2. **Peak/Shelf Morph, negative Peak** — a real single dip/notch at Freq (manual
   ex.: Freq 9824 / Shelf 0 / Peak −12). Fallback if Swept-EQ-cut disappoints.
3. Contrary Bandpass (current) — peak+dip hybrid, not a notch.
4. Phaser/Flanger — *multiple* comb notches, not a single band-stop.

**RE needed:** vpar[58] bytes for "Swept EQ 1-octave" and "Peak/Shelf Morph"
(not yet in `_E4XT_FILTER_BYTES`), plus how their gain/cut + bandwidth map to
vpar[61] (the FilRes/2nd-param). Then add MPC BS → Swept-EQ-cut to
`_XPM_FILTER_TYPE`. A/B Swept-EQ-cut vs Peak/Shelf-neg-peak on hardware to pick.

**Web research (2026-06-13) — ambiguous, no authoritative answer:**
- Sound on Sound's *E4XT Ultra* review lists the 21 Z-plane types and calls one
  "a contrary band-pass **(fancy name for notch?)**" — note the **question mark**:
  a reviewer's casual guess, not authority.  So there IS an online hint that
  Contrary BP ≈ notch, which would make our current map type-correct after all.
- BUT the official EOS 4.0 manual describes Contrary BP as a "novel *bandpass*
  where peaks and dips cross midway" — i.e. peak+dip, not a clean single notch.
- The wider E-MU Z-plane family (Proteus/Morpheus, same DSP) explicitly exposes
  separate **"EQ−" / Swept-EQ parametric cut** filters — a parametric cut is a
  textbook band-stop.  E-IV is also described generally as having "notch and
  parametric filters."
- **Conclusion:** the docs conflict (reviewer "notch?" vs manual "bandpass"), so
  the only reliable test is a hardware A/B: on the E4XT compare (a) Contrary BP,
  (b) Swept EQ 1-oct with **cut**, (c) Peak/Shelf Morph neg-Peak — against the MPC
  band-stop, at matched Freq.  Jan already found Contrary BP "far off" even after
  tuning Freq/Q, which leans toward Swept-EQ-cut being the better notch.

### M. Param issues that apply whatever band-stop type we choose
1. **Q meaning was inverted for Contrary BP.** MPC band-stop Resonance deepens the
   *notch*; E4XT Q "amplifies frequencies near the cutoff" (a *peak*). Copying
   Resonance 0.89 → Q 113 made a resonant peak where the source has a notch —
   hence Jan's Q 0 sounding better. With a real notch type (Swept EQ cut), the
   source resonance should map to **cut depth**, not a resonant-peak Q.
2. **Cutoff too low / mis-calibrated:** our byte 10 ≈ 85 Hz vs Jan's ~260 Hz.
   MPC Cutoff 0-1 → Hz curve vs our linear `round(0.04·255)`=10 — needs cutoff
   data points (same kind of calibration pass as the LFO rate / decay).

---

## Bass-Pulse-Bass — `FEATUREDEMO_03.E4B [13]/[14]`  (src: 2b + 3b)

**Jan:** [13] has wrong filter — MPC 2b is "High 4, Cutoff 60, Res 0", but [13]
shows 4P LP, 783 Hz, Q 44. Filter env also looks like the default. "Am I looking
at the wrong preset?"

### N. ODS preset→source map is SWAPPED for same-named presets — ✅ FIXED 2026-06-13
Two demo presets share the 16-char name "Bass-Pulse-Bass" (from `Bass-Pulse-Bass
2b.xpm` + `3b.xpm`). **The conversion is CORRECT** (verified via staging):
- 2b `FilterType=8 (High4)` → **0x09 (4th-order HP)**, Q 0, cut 120 ✓ (matches MPC)
- 3b `FilterType=3 (Low4)`  → **0x00 (4P LP)**, Q 44, cut 107
In the packed bank they landed as **[14]=2b**, **[13]=3b** — but the ODS pairs
[13]↔2b (wrong). Cause: `rebuild_all.py` phase-3 maps packed presets back to
sources by **preset name** via a deque pool; identical names → arbitrary order.
**Jan was comparing 2b to [13], which is actually 3b's data.** 2b is [14], and
there the High4→4HP filter is right.

**FIXED 2026-06-13:** `rebuild_all.py` phase-3 now maps packed presets → sources
by a **content signature** (`e4b_preset_sigs` = preset name + sorted CRC of each
referenced sample's PCM), not by ambiguous preset name. This disambiguates both
the different-sample case (Bass-Pulse 2b/3b) and the same-sample/different-PCM case
(the clean/emax1/emulator2 Synth-MS20 trio); uses PCM-CRC only so cross-source
sample renames don't break it. Verified: 46/46 presets map, 0 unmatched. The
**existing `feature_coverage.ods` was patched in place** (only the 2 swapped
Bass-Pulse rows' Source/Notes cells; Jan's yellow highlighting preserved exactly —
20 marked rows unchanged). Backup at `feature_coverage.ods.bak`.

### O. Filter envelope not written when FilterEnvAmt=0 — **DECISION: always write it**
Both 2b and 3b have `FilterEnvAmt=0.0`, so the writer currently skips writing the
filter-env shape (`_build_voice` writes PZT[14:26] only when `filter_env_amount >
0.01`) and leaves the default PZT env (Atk1 0 / Dcy1 +99). Jan sees the MPC's
FltEnv (e.g. 8.7 ms / 173 ms) but the E4XT shows the default.

**Mechanism note (re Jan's LFO question):** the filter envelope and the LFO are
*separate additive cords* into Filter-Freq (EOS voice diagram p.262) — they do NOT
interact. At `FilterEnvAmt=0` the env contributes 0 to cutoff regardless of LFO,
so it's inaudible for *this* patch (the audible miss is the LFO waveform/rate, §Q/§P).

**But — DECIDED (Jan, 2026-06-13): always map the filter-env shape**, even at
amount 0. Zero audible downside (FENV→cutoff cord amount stays 0 → env inert), real
upside: the E4XT *displays* the MPC's true env, and the curve is ready if the env
amount is later turned up on the hardware. **Fix:** in `e4b_writer._build_voice`,
write PZT[14:26] from the source `FilterAttack/Decay/Sustain/Release` unconditionally
(keep the FENV→FilterFreq cord amount = `filter_env_amount`, so 0 stays inert).
Needs the MPC FilterEnv-time→seconds calibration (same family as the amp-decay §J
gap) for the displayed times to match exactly. Note: this changes PZT bytes on
many demo voices (inaudible), so a rebuild would re-emit them.

### P. LFO sync — §D again; divisor availability varies per patch
Same tempo-sync gap as §D. The E4XT's 6 clock divisors are double-whole / whole /
half / quarter / 8th / 16th note.
- `[13]`/3b: `<Sync>9` = **Eighth Note** → IS an E4XT divisor → faithfully
  clock-syncable. Jan: free-run ~**5.8 Hz** at 100 BPM comes close (the §D option-2
  approximation).
- An earlier (pre-relabel) note mentioned "Quarter Note **Triplet**" — that has
  **no** E4XT divisor (no triplets), so only the free-run-Hz approximation works.

### Q. LFO waveform `SampHold` → mapped to Triangle, should be **Random** (bug)
**Jan:** [13]/3b uses S&H; we mapped it to Triangle. "Random would be a better
pick" (or Hemi-quaver?).

**Confirmed bug:** XPM `<Type>SampHold`. `_xpm_lfo_shape('SampHold')` returns
**'triangle'** — the random branch tests `'sample'`/`'s&h'`/`'random'`/`'noise'`,
none of which is a substring of "samphold" (it has `samp`, not `sample`). So S&H
falls through to the triangle default. The E4XT HAS a `random` shape (0xFF).

**The bug:** in `parsers/xpm_parser._xpm_lfo_shape`, `SampHold` matches none of the
random-branch tests (`'sample'`/`'s&h'`/...) and falls through to triangle. Add a
`'samp' in t` / `'hold'` test so it's caught.

**Random vs Hemi-quaver — DECIDED: Hemi-quaver (Jan's hardware A/B, 2026-06-13).**
My first call (Random, "truly random = faithful") was **wrong**: it ignored that
this S&H is **tempo-synced** (8th notes), so it steps *regularly/rhythmically* —
not the irregular truly-random character. E4XT **Random** (0xFF) is genuinely
random (irregular, different per voice) → does NOT match a clocked S&H. E4XT
**Hemi-quaver** (0x0F) is a regular stepped *Pattern* → matches the synced S&H's
rhythm. Jan confirms Hemi-quaver sounds closer, at **rate ≈ 0.42 Hz** (E4XT)
against the original at 100 BPM clock.

**Implication for the fix:** map MPC `SampHold` → `'hemiquaver'` (not random/
triangle), AND the rate must be set to make the pattern step at the synced rate
(0.42 Hz for 8th-note @ 100 BPM) — so the waveform fix is **coupled to the sync/
tempo handling (§D/§P)** for synced S&H. (Open question: for a *free-run* S&H —
irregular — Random may still be the better pick; only synced S&H tested so far.)
Scope: many EXPANSIONS patches use `SampHold` — all currently mis-map to triangle.

Useful manual p.258 reference for later LFO work: Random = per-voice-random;
Pattern/Hemi-quaver = same across voices; "Sine + Noise" simulates trumpet/flute
vibrato; Hemi-quaver→Pitch amounts: +38 major, −38 phrygian, +76 whole-tone,
(+38)+(+76) diminished, odd amount = S+H sound.

### O-bis. FilterEnv default (reinforces §O)
**Jan:** [13]/3b MPC FltEnv attack 8.7 ms / decay 173 ms, but E4XT shows the
default (Atk1 0, Dcy1 +99). Confirmed `FilterEnvAmt=0.0` on all 128 keygroups →
env inaudible on both machines → cosmetic (we only write the env shape when
amount > 0.01). Same as §O.

---

## …more on Bass-Pulse-Bass `[14]` / 2b  (2026-06-13)

2b = **21 keygroups** (C1–C6, one sample each, 3 keys wide). LFO = **Triangle**,
`<Sync>8` = **Quarter-note Triplet**, free-run rate-knob 0.

### R. 2 voices vs "1 layer" — **NOT a bug** (filter-type split)
Jan: MPC shows one layer per keygroup, E4XT shows 2 voices. Correct: **KG1 uses
FilterType=9 (High6), KG2–21 use FilterType=8 (High4)**. Our parser groups
same-param keygroups, so KG1 → V1 (High6, the lowest sample, keys 24-38 = C0-D1)
and KG2–21 → V2 (High4, a 20-sample keymap, keys 39-96). Faithful — the two voices
carry the two distinct filters.

### R-window. Voice key-window claims C-2↔G8 — confirmed wrong (the real §A/§G fix)
**Jan:** "V1 shouldn't expand over C-2↔G8 — KG1 only spans C0↔D1 on MPC." Correct.
V1's only zone is keys 24-38 (C0-D1), but the E4XT voice shows the full-range
default because **the writer sets no per-voice key window** — the secondary zone
limits what *sounds* (24-38) but the group mis-claims C-2↔G8. **Primary fix: set
each voice's key window = span of its zones** (V1 → 24-38, V2 → 39-96). Needs a
small RE: the vpar voice **key**-window bytes (analogous to the already-RE'd
velocity window vpar[18]/[21]), then set from min/max zone key.

**Correction to §A:** I earlier conflated this with an "extend the edge zones to
0/127" idea. They're **two separate things**:
1. **Voice key-window = zone span** (certain, this is Jan's point; fixes the
   false full-range claim on V1/V2 *and* the MS20/Lazloz "claims full range").
2. **Edge-extension** — whether keys *outside* the keymap's covered range (here
   0-23 below KG1, 97-127 above KG21) should play the nearest edge sample. This is
   **uncertain** and per-patch: needs a hardware check "does the MPC sound below
   the lowest / above the highest keygroup?" Don't assume it (my Lazloz "C0 sounds"
   read was likely just KG1 already spanning 0-59, not true extension). Fix (1) is
   the one to implement; (2) only if a patch demonstrably plays outside its keymap.

### S. Triangle LFO start phase differs — Jan's negate-cord fix is **valid**
Jan: MPC triangle and E4XT triangle start at centre but go opposite directions
(one up-first, one down-first). Two centre-start triangles of opposite direction
are exact **inversions** (`B(t) = −A(t)`), so **negating the LFO→dest cord amount
(−37% instead of +37%) flips the E4XT triangle to match the MPC** — Jan's idea is
right. Caveats: (a) only matters when the LFO is **key-synced** (per-note phase
reset makes the start direction audible; for free-run the phase is arbitrary and
it doesn't matter); (b) works for **symmetric** waves (triangle, sine — for
sawtooth, negating turns saw-up↔saw-down, which is actually a free SawDown route,
see §B); (c) must confirm the direction convention (which machine goes which way)
so we flip the right ones, and compose the sign with the existing depth sign so we
don't double-negate. **Fix sketch:** when shape == triangle/sine and the routing
is key-synced, emit the LFO→dest cord with negated amount (pending a hardware
confirm of the convention).

### T. FilterEnv Atk1 vs Atk2 — our mapping is **CORRECT** (manual p.257)
Jan: "Atk2 resembles the MPC attack, not Atk1?" — the question came from the
**E4XT's graphical envelope display**. **EOS envelopes are 6-stage rate/level**
(manual p.257): on key-down the env goes 0 → Attack-1 *level* at the Attack-1
*rate*, then to Attack-2. Sidebar: "for a standard ADSR, set the '2' levels = the
'1' levels and all '2' rates to 0" → **the attack lives in Atk1**; Atk2 is a no-op.
Our converter writes exactly that (Atk1 rate=attack/level=100, Atk2 rate=0/level=100).
So the mapping is right.

**Why the *graph* shows the rise in Atk2:** the displayed curve is the **default**
filter env we leave when `FilterEnvAmt=0` (`_PZT_FENV_DEFAULT` = Atk1→level 0,
Atk2→level +100), so its rising segment is drawn in the Atk2 portion. Artifact of
the default shape, not the conversion. **§O (always write the env) resolves it:** a
converted env sets Atk1 level=100, so the graph rises in Atk1 — matching the manual
and the MPC. No envelope-mapping change needed beyond §O.

### Sync detail for [14]/2b (updates §P)
`<Sync>8` = Quarter-note **Triplet** → **no** E4XT clock divisor (no triplets), so
only §D-option-2 free-run approximation: Jan ~**2.06 Hz** + key-sync at 100 BPM
comes close, "still not 100%". (3b/[13] was 8th-note = a real divisor.)
