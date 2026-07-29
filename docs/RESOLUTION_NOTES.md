<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# mpc2emu — Resolution Notes

> **How to use this file:**
> Every open item in `TODO.md` has a corresponding entry here that answers
> *how* to fix it — code patches, hardware RE procedures, or open questions.
> When a TODO item is resolved, remove it from `TODO.md` and mark it done
> here with a date.
>
> This file is the companion to `TODO.md`.  `TODO.md` says *what* is broken;
> this file says *how* to fix it.  Keep them in sync.

---

## §E4BRATE — EOS4 sample-rate field (how to fix the resample pitch bug)

**Symptom.** E4B samples stored below 44.1 kHz play sharp by `src/dst` (27500 →
+8.18 st). See `TODO.md`. The E4XT honors low rates (SrCnv keeps pitch), so EOS4
reads the playback rate from a field other than our E3S1 `[54-57]` (which came from
emu3bm/EOS3). We currently write `[58-59]` playback_rate and `parameters[6]`
(`[70-93]`) as 0.

**RE procedure (hardware artifact — Jan).**
1. Load `K2_AUTOSAMP` on the E4XT (from the ISO / ZuluSCSI). Note a **non-resampled**
   sample's pitch — e.g. **S020** (a plain 44.1 kHz sample; plays A-something).
2. Sample Edit key → select S020 → **Tools 1 (F2)** → **SrCnv (F4)** → enter a
   **distinctive low rate (e.g. 22050)** → set filter (Smooth) → **OK**.
   Confirm S020 **still plays the same pitch** (proves EOS keeps pitch on rate change).
3. Save the bank back (new bank is fine). Hand the `.E4B` to Claude.

**Diff.** `python3 tests/re_banks/diff_sample_rate_field.py <hw_bank>.E4B`
— within the resaved (all-EOS4-authored) bank it diffs the SrCnv'd S020 (22050) vs
an untouched neighbour (44100); the differing offset(s) holding `22050`
(`0x5622`) is EOS4's real rate field. (SrCnv to 22050 also ~halves S020's PCM, so
it is easy to identify even if `[54-57]` no longer carries the rate.)

**Fix.** In `writers/e4b_writer` `_sample_header`, write `sample.sample_rate` into
the field the diff reveals (keep `[54-57]` too, for EOS3 tools / our own parser).
Then `resample_vintage` / `resample_to_rate` E4B output plays in tune at the reduced
rate — no upsampling, RAM saving retained. Re-verify on HW, then update
`docs/E4B_FORMAT.md` sample-header table with the corrected field.

**RE PROGRESS 2026-07-24 — fields identified, encoding half-decoded.** Diffed the
E4XT-resaved `B.010-K2_AUTOSAMP.E4B` (pulled from `HD0.img`, a **FAT32** ZuluSCSI
image — `mcopy -i HD0.img ::/B.010-K2_AUTOSAMP.E4B out`) where **S020 = idx 20
`P1 PL 19_A4` was SrCnv'd 44100 → 22050 and plays IN TUNE**. Against an untouched
44.1 kHz neighbour (idx 19), the pitch-carrying fields — both **written 0 by our
`_sample_header`** — are:
  * `[54-57]` sample_rate — EOS4 *does* store the real rate (22050) but does NOT
    pitch from it (our 27500 sets it too and plays sharp); informational/display.
  * **`[58-59]`** (our "playback_rate"=0): EOS4 = `0xFD02` = **−766 signed** for the
    2:1 drop. ≈ **−768 = −1 octave in 1/64-semitone units** (0.26 % off — see below).
  * **`[18-21]`** (our "header"=0): EOS4 = `0xEB8B839C` (s32 −343178340) — a 32-bit
    companion, encoding not yet solved from one point (not a clean cents/ratio/float).
Both are non-zero ONLY on the converted sample (the 44.1 kHz neighbour has both 0),
so together they are the sub-44.1-kHz pitch correction; leaving them 0 makes EOS4
play at native rate → sharp by `native/rate`. NOTE EOS4 also grew every sample's
PCM by +8/+12 bytes on resave (loop/format padding, not pitch).

**SOLVED 2026-07-24 — fix implemented, pending HW confirm.** Jan SrCnv'd S018-S023
to 11025/27500/22050/32000/33075/48000 (bank `B.011-K2_AUTOSAMP.E4B`). Fit
(`tests/re_banks/fit_e4b_rate_fields.py`):
  * **`[58-59]` (s16 LE) = round(768 · log2(rate / 44100))** — 768 = 64·12, i.e.
    **1/64-semitone**. Fits all 6 points within ±2 (an exact fit uses base 44037,
    but 44100 is the true f58=0 native — an untouched 45 kHz sample keeps f58=0 and
    plays in tune, and 44100→0 leaves plain samples byte-unchanged). 48000 → +95
    (positive above native). Deterministic (idx20=22050 gave −766 in BOTH B010/B011).
  * **`[18-21]` — NOT pitch.** Same 22050 conversion gave `0xEB8B839C` in B010 but
    `0x3B97FC3E` in B011 → non-deterministic per-sample token (checksum/id EOS sets
    on modify). Left 0 (all our 44.1 kHz samples work with 0).
Fix in `writers/e4b_writer._sample_header` (write f58 at offset 58 when rate≠44100).
**DONE — HW-CONFIRMED on the E4XT 2026-07-24**: E2/EX/E2SC/EXSC play in tune; plain
byte-unchanged. Commit-ready. (Also update `docs/E4B_FORMAT.md` sample-header table:
`[58-59]` = pitch offset in 1/64-semitone, not "playback_rate"; `[18-21]` = opaque
per-sample token, not "header".)

---

## §MPCFILT — MPC filter dropped at max cutoff (how to fix)

`parsers/pgm_parser.py` ~285:
```python
# CURRENT — drops the filter (type=0) when fully open, losing resonance:
if f1_type in _PGM_FILTER_XPM and f1_freq < 100:
    voice.filter_type      = _PGM_FILTER_XPM[f1_type]
    voice.filter_cutoff    = min(1.0, f1_freq / 99.0)
    voice.filter_resonance = min(1.0, f1_res / 100.0)
else:
    voice.filter_type   = 0
    voice.filter_cutoff = 1.0
```
Fix: create the filter whenever `f1_type` is a real type, regardless of `f1_freq`:
```python
if f1_type in _PGM_FILTER_XPM:
    voice.filter_type      = _PGM_FILTER_XPM[f1_type]
    voice.filter_cutoff    = min(1.0, f1_freq / 100.0)   # /100 (was /99)
    voice.filter_resonance = min(1.0, f1_res / 100.0)
else:
    voice.filter_type   = 0
    voice.filter_cutoff = 1.0
```
Then grep `parsers/xpm_parser.py` for a `Cutoff >= 1.0 → skip filter` pattern and
apply the same. Verify against a pad that has resonance (or a filter env) at max
cutoff — it should now keep its bite. Cross-ref ConvertWithMoss `c7b9641`.

## §MODELPARAMS — carry choke group / one-shot / key-track / round-robin (design)

Add to `models/common.py`:
- `ZoneMapping.exclusive_group: int = 0` (0 = none) — **choke/mute group**. Parse:
  MPC (`<MuteGroup>` / choke), SFZ (`group=`/`off_by=`), SF2 (exclusiveClass). Write:
  E4B/K2000 group field IF the hardware supports it — RE needed (E4XT "Group" and
  K2000 keymap have a mute-group concept; confirm the byte before wiring the writer).
- `SampleData.one_shot: bool = False` (first-class; today only `pgm_parser` infers it
  as a full-length release). Maps to E4B/KRZ "play to end / ignore note-off" where
  expressible.
- `VoiceLayer.amp_keytrack: float = 0.0` (mirror the existing `filter_keytrack`).
- Round-robin / random: a per-group play-logic enum; low priority (E4XT has no direct
  round-robin, would need a mod-cord/random-source hack).
Start with **exclusive_group** (drum kits benefit most). Cross-ref ConvertWithMoss
`6fcc346` (#212) for the source-side mappings per format.

## §MPC39 — MPC Standalone 3.9.0 gzipped-JSON `.xpm` parser (how to fix)

**What it is.** 3.9.0 hardware saves each `.xpm` as **gzip** (`1f 8b 08 …`).
`gzip.decompress(raw)` yields a UTF-8 text header then a JSON body:

```
ACVS
3.9.0.31
SerialisableProgramData
json
Linux
{ "data": { "version": 6, "name": "K2-01", "type": 1, "programPads": { … } } }
```

The header is line-delimited; the JSON starts at the first `{`.

**Parser plan (`parsers/mpc39_parser.py`, register `.xpm` → dispatch by magic):**
1. In `xpm_parser` (or the registry), sniff the first 3 bytes: if `1f 8b 08`,
   `raw = gzip.decompress(raw)`. If the result begins with `ACVS`, hand off to the
   new 3.9.0 JSON parser; else fall through to the existing XML path. (Keeps one
   `.xpm` entry in `PARSERS` handling both old XML and new gzipped-JSON.)
2. `body = raw[raw.index(b'{'):]`; `doc = json.loads(body)`.
3. Walk `doc["data"]` → build `Bank`/`Preset`/`VoiceLayer`/`ZoneMapping`. Map the
   keygroup/pad list (`programPads` and/or an instruments/keygroups array — RE
   needed) to zones: sample ref, lo/hi key, lo/hi vel, root, tune, volume, pan,
   plus filter/env/LFO where present (mirror the XML `xpm_parser` field mapping so
   the two share the model-fill helpers). Samples resolve to the sidecar
   `<name>_[ProgramData]/*.wav` via the existing `load_wav`.

**RE still needed:** catalogue the JSON keys under `data` and confirm the
key/velocity-zone and modulation layout. Dump: `python3 -c "import gzip,sys;
sys.stdout.buffer.write(gzip.decompress(open('K2-01.xpm','rb').read()))"`.
Reference programs: `/media/lentferj/3433-6435/SamplerExports/K2-0{1,2,3}.xpm`.

**Until then:** `convert.py <name>_[ProgramData]/ --from-samples` converts the
samples + auto-mapped zones (no program synth params).

---

## §AUTOLOOP — Auto sustain-loop (IMPLEMENTED, branch `autoloop`, 2026-07-25)

**Goal.** Set a clean forward sustain loop in the steady region so held notes
sustain. Autosampler follow-on to `--trim-tail` (trim the dead tail dropping the
whole-take loop, then place a *real* sustain loop). `processors/auto_loop.py`
(`auto_loop_bank` / `_auto_loop_sample` / `_find_loop`), pure Python, reuses the
single-cycle DSP; wired after `--trim-tail` in `convert.py`.

**As-built algorithm** (differs from the original sketch below in ways that matter):

1. **Steady region** — `_steady_region`: a LONG-window (80 ms) smoothed RMS envelope
   finds the attack-end and release-onset while IGNORING tremolo/beating dips. (The
   original short-window "stop at first dip" cut modulated material to nothing.)
2. **Period** — `single_cycle._detect_period` + `_refine_period`, root-primed, with a
   **harmonic-lock fallback**: detected pitch > 2 octaves off the root ⇒ use the
   root-note period, drop confidence (fixed a low-bass 0.49→0.15 case).
3. **Seamless splice — click-free by CONSTRUCTION (the key insight).** Endpoints snap
   to rising zero-crossings. The equal-power crossfade rewrites the last `xf` loop
   samples `[E-xf+1..E]`, morphing from the loop-end content into the samples that
   PRECEDE loop-start `[S-xf..S-1]`, with `t=i/(xf-1)` so `fo=0` at the last sample →
   `out[E] = orig[S-1]` EXACTLY. The wrap `E→S` therefore reproduces the natural
   waveform run `orig[S-1]→orig[S]`. Measured residual click ≈ **−240 dB** on all
   material, synth sawtooth edges included. ⚠ Ending the crossfade at `orig[S]`
   (off-by-one) DUPLICATES a sample = a real glitch — avoid. ⚠ Do NOT QC the seam
   with jump/avg-step (it false-flags a synth's legitimate per-period edge as 70×);
   QC with `|out[E]−orig[S−1]|` in dB below peak.
4. **Adaptive length + BEAT ALIGNMENT** (refined 2026-07-25 after audition feedback —
   loops were too short/static, and a detuned-synth loop pulsed "ding-ding-ding").
   Splice quality is scored by `_match_cost` = normalised SSD of the two crossfade
   windows (pre-end `[E-w+1..E]` vs pre-start `[S-w..S-1]`).  Length:
   - *modulated* tone (vibrato / tremolo / detuned-oscillator BEATING; `_modulation`
     returns the FUNDAMENTAL modulation period M) → candidate lengths are integer
     multiples of M, so the envelope matches at the seam.  A fraction-of-a-beat error
     is the audible ding — the loop-end zero-crossing search weights toward the exact
     beat multiple (`score = cost + 0.5·|E−Et|/M`).  ⚠ the click-free crossfade holds
     for ANY loop-end, but landing E on an exact non-zero-crossing beat multiple wrecks
     the crossfade-window match (waveform-phase mismatch → high cost → wrongly skipped);
     use a zero-crossing NEAR the beat, not exactly on it.
   - *steady* tone → integer-fundamental-period sweep.
   Keep the **LONGEST transparent** loop (was steady→shortest — wrong: a short loop on
   evolving material sounds static even when seamless).  Defaults `min_ms=150`,
   `max_ms=2500` (raised from 80/600 for natural, breathing loops).  A few loop-START
   candidates guard against a bad start.  A length/cost penalty (`_LEN_COST_PENALTY_MS
   =2000`) trades length against splice quality so a marginally-longer loop cannot win
   by degrading the seam.  Fast-beating/drifty analog synths are the one case where a
   long loop over-captures drift → manual override with `--auto-loop MS` or
   `--auto-loop-max-ms 800` (no metric auto-distinguishes drifty-wants-medium from
   clean-wants-long; see [[project_autoloop]]).  Skip default `min_quality=0.45`.
5. `loop_type=FORWARD`, `loop_start=S`, `loop_end=E` (inclusive). Round-trips through
   both E4B and KRZ writers (verified). Crossfade applied per channel (mono+stereo).
   **`crossfade=False` (`--auto-loop-no-crossfade`)** leaves the PCM pristine — loop
   points only, at the zero-crossing/beat-aligned positions — so the loop stays freely
   fine-tunable in the E4XT/K2000 loop editor (a baked crossfade locks it in place).

**Knobs:** `--auto-loop [auto|MS]`, `--auto-loop-xfade MS` (grows automatically for
poor matches), `--auto-loop-max-ms`, `--auto-loop-min-quality COST` (skip hard
material), `--auto-loop-force`, `--auto-loop-trim` (drop audio past loop_end),
`--auto-loop-dump-dir`. `[weak match — audition]` advisory above cost 0.44 (the raw cost badly over-predicts badness once the crossfade is applied — HW audition rated loops up to 0.437 "very good").

**Results (objective sweep, mellotron/VPO/prophet/K2).** Solo/pure timbres (flute,
cello, clean choir, analog synth) → excellent (match <0.07, natural 300-600 ms
loops). Dense ensemble / noisy analog → inherently hard (0.2-0.55): longer crossfade
+ flag/skip. Audition renders (loop×6 flat) in `/home/lentferj/temp/autoloop_work/aud/`.

**Still to do:** local audition (Audacity/VLC) then **HW audition** on E4XT + K2000
before merge to main; possibly pitch-based vibrato detection (amp-envelope misses
pure vibrato) and quality-threshold tuning. Prior art: LoopAuditioneer, PyMusicLooper.

<details><summary>Original design sketch (superseded)</summary>

1. `region = single_cycle._sustain_start(sig)`. 2. `_detect_period`/`_refine_period`.
3. loop length = integer periods (a few hundred ms). 4. cross-correlate end points,
snap to zero-crossings. 5. optional crossfade. 6. `loop_type=FORWARD`. The as-built
version replaced (3)+(4) with the measured length sweep and made the crossfade the
click-free primary mechanism rather than an optional touch-up.
</details>

---

## §CR — Code-review findings (2026-06-10), fix recipes

Items confirmed by the high-effort review (`TODO.md` "Code-review findings").
Each is a self-contained code fix. **Add/extend a `test_pipeline.py` case for the
P0 ones** (they're currently uncovered).

**DONE 2026-06-10:** CR-2, CR-4, CR-5, CR-8, CR-9, CR-11, CR-12 — fixed &
pipeline-verified (see each entry below). **CR-11b — FALSE POSITIVE**, see below.
**DONE 2026-06-11:** CR-3 (TAL writer); CR-1 + CR-10 + CR-11c (KRZ writer); CR-6
(zone-reducer); CR-7/7b/7c (name collisions) — see below. **All P0 items done;
CR-13/14/15/16/17 + CR-18 cord-builder done 2026-06-11; only CR-18
(`Envelope` dataclass — recommend skip / EXS24 walker-unify — needs `.exs`
files) remains.**

**CR-1 KRZ velocity layers / stacking — DONE 2026-06-11.** Restructured to **one
keymap + one program layer per voice** (was one merged keymap per preset with N
identical layers stacked over it → ~+9.5 dB / phasing, and later voices
overwriting earlier per key). `_build_keymap_entries` now takes a single voice;
`_write_program_object` emits one layer per voice pointing at that voice's keymap,
with the LYRSEGTAG **key AND velocity range** (`lyr[3..6]`) set from the voice's
zone span. Since the parsers model velocity layers as separate voices, those now
split correctly on the K2000. Keymap ids use a running counter (typed-hash makes
numeric overlap with sample/program ids fine). Verified: 3-voice preset (soft
vel 0–63 / loud 64–127 / key-split) → 3 layers, distinct keymaps, correct vel
windows. **Remaining limitation:** a *single* voice carrying internal vel-split
zones still collapses to one keymap velocity level (the 8-level on-disk keymap
layout isn't reverse-engineered) — fine in practice since parsers split velocity
into separate voices. Hardware load check is a Jan gate (as with all KRZ work).

**CR-10 KRZ loop end — DONE 2026-06-11.** The K2000 loop is [sampleLoopStart,
sampleEnd], so `_write_sample_object` now writes the loop **end** as the
Soundfilehead `sampleEnd` field when looped (`abs_loop_end`), the PCM end only
for one-shots. Verified: looped sample (loop 200–600 of 1000) writes sampleEnd
600, not 999.

**CR-11c KRZ ping-pong — DONE 2026-06-11.** `write_krz` now bakes ALTERNATING
(ping-pong) loops into PCM as forward loops via `bake_alternating_loop`, exactly
like `write_e4b` (was emitting plain forward → click every cycle). Verified: a
500-word ping-pong sample baked to 799 words.

**CR-2 + CR-12 SFZ cutoff — DONE 2026-06-10.** Added `hz_to_e4b_cutoff(hz)` +
`E4B_CUTOFF_MIN/MAX_HZ` to `models/common.py` (the 57 Hz / 20 kHz exponential
convention). `sfz_parser` now does `voice.filter_cutoff = hz_to_e4b_cutoff(hz)`
(was the broken `int(min(127, cutoff_hz/200))`); `exs24_parser._exs_cutoff_to_e4b`
calls the shared helper. Sanity: 1 kHz → pos 0.489 (was fully open).

**CR-3 TAL writer schema — DONE 2026-06-11.** `write_talsmpl` rewritten to emit
the real TAL **v11** schema (the old invented `<preset><layer><param><mapping>`
loaded nowhere). Jan supplied a fresh `Startup.talsmpl`; its 234 `<program>`
defaults + the `<multisample>` defaults are reproduced as *format data* in
`parsers/tal_template.py` (no TAL preset bundled), with generators for the
`voicetunings`/`modmatrix`/`tuningtable` child blocks. The writer clones a full
default program (`new_tal_root()`) and overrides only what mpc2emu models:
`programname`, program-global `filtercutoff/resonance/mode` + `adsramp{a,d,s,r}`
(from V1), one enabled sample layer (a–d) per voice, and per-zone
`url/root/low/high key`, `velocitystart/end`, `loop*`, `pingpongloop`,
`volume/pan/transpose/detune` on each `<multisample>`. Samples are **external WAV
refs** (`includewaveinpreset=0`, `url` + `urlRelativeToPresetDirectory` =
`samples/NAME.wav`). New inverse converters: `_secs_to_tal_adsr`,
`_xpm_filtermode_to_tal`. The **parser** now also reads the multisample-level
`volume/pan/velocity/transpose` (where TAL stores per-sample values), so
write→parse is **lossless** — verified: 2 voices, keys/root/vel 10-100/vol −3 dB/
pan −0.5/transpose +7/fine +10 c all round-trip exactly. Pipeline green.

**Layer bin-packing fix (2026-06-11):** the writer first mapped one voice → one
TAL layer (max 4), so any preset with >4 voices silently lost samples — e.g. a
14-pad drum kit (our parsers model each pad as a separate voice).  Now it
bin-packs ALL zones into ≤4 layers by key×velocity overlap (`_tal_zones_overlap`):
non-overlapping zones (drum kits, multisampled keyboards, velocity layers) share
ONE layer as many `<multisample>`s; only truly overlapping zones (simultaneous
stacking) take a new layer.  Verified: `AMBIENCE_SET__1.PGM` (14 pads) →
1 layer / 14 multisamples, each mapped to its key; synthetic per-zone round-trip
still lossless.

**TAL-Sampler load test — PASSED 2026-06-11** (Jan, real MPC2000XL drum kit
`AMBIENCE_SET__1.PGM` → external-WAV `.talsmpl`).  External refs resolve, samples
load and play.  The test (and a TAL-saved reference of the same kit) uncovered
**five** writer bugs the parse→write round-trip could not, all now fixed:
1. **Missing `<programs>` wrapper** — TAL (JUCE) walks `tal→programs→program` by
   name; `<tal><program>` loaded silently as empty.  `new_tal_root` now emits it.
2. **Layer bin-packing** — see the dedicated note above (>4 voices dropped).
3. **`track="0"` for one-shots** — single-key/drum zones must set `track="0"`
   EXPLICITLY; TAL's default for an *absent* `track` is `"1"` (keytrack on →
   heavy transpose at the pad's own key).  Ranged zones keep `track="1"`.
4. **`stereoinverse="0"`** — same absent→`"1"` default; written explicitly.
5. **Per-sample filter + CRLF** — the multisample template had inherited the
   Startup oscillator's `filtercutoff=0`/`filterhighpass=1` (would darken
   samples) → set neutral (`1.0`/`0.0`); file written with CRLF + blank line to
   match TAL.  Output verified field-for-field against the TAL-saved reference
   (only cosmetic float-format / inactive-grain diffs remain).
Key lesson: TAL keeps the **full 42-attr** multisample set and re-defaults any
*omitted* attribute, so the writer must set the meaningful ones explicitly.

**Remaining (minor, Jan, when convenient):** the absolute TAL **volume** and
**cutoff** mappings are reasonable approximations, not measured.  Embedded-PCM
(`includewaveinpreset=1`) is the fallback if external refs ever don't resolve —
not needed here.

**CR-4 SFZ loop override — DONE 2026-06-10.** `sfz_parser` now sets
`loop_type`/`loop_start`/`loop_end` only when the opcode is actually in `merged`
(`if 'loop_mode' in merged: …`); absent opcodes keep what `load_wav` read from the
WAV smpl chunk (SFZ default = "from the sample").

**CR-5 E4B amp-env decode — DONE 2026-06-10.** `_parse_voice` now mirrors
`_build_voice` PZT[0:12]: `env_attack=_fenv_rate_inv(pzt[0])`, decay pzt[4],
release pzt[8], `env_sustain=_fenv_level_inv(pzt[5])`. Verified round-trip
(A0.05/D1.2/S0.4/R0.8 → 0.049/1.205/0.40/0.802). (The `_fenv_*` math was later
de-duplicated into `models/common.py` — see CR-13 below.)

**CR-6 zone-reducer — DONE 2026-06-11.** `_thin_and_redistribute` now checks
whether the kept items form a non-overlapping chain on the reduction axis
(`orig_lo[i] > orig_hi[i-1]`). Only then does it widen survivors into the gaps;
overlapping/parallel items (drum-kit full-range voices, vel-split zones thinned
on the key axis) keep their original ranges, and a `new_lo <= new_hi` guard means
it never emits an inverted (silent) range. Verified: a 4-voice full-range drum
kit reduced 50 % → 2 voices, **zero inverted ranges** (was producing 64>63); a
real 8-zone key chain still redistributes to a clean ordered 0–127 cover.

**CR-19 `thin_velocity_layers()` entangled key/velocity presets — DONE
2026-07-27.** Found via VinSamLib (downstream project, see TODO history):
`velocity_layer_pct=30` on a preset with one voice per (key-zone × velocity-
layer) cell shrank total voice count by ~30% but left the distinct velocity-
BAND count unchanged, because the `len(preset.voices) > 1` branch thinned
individual voices by index-spacing without first grouping them by their own
velocity band — when several voices share a band (one per key zone), even-
spacing almost always leaves a survivor in every band. Fixed by grouping
`preset.voices` into `(voice_lo, voice_hi)` bands first (mirroring
`_thin_velocity_bands_in_voice`'s zone-grouping, one level up), thinning at
the band-group level via `_thin_and_redistribute`, then applying each
surviving band's (possibly widened) range to every voice in it. Verified
against the real repro file
(`.../Kirk.Hunter.Virtuoso.Series.Strings1.E4/KH Violins/B.003-2_8Violins128MB.e4b`,
preset `8VnEsHdMrcFat/SL`): 5 → 4 distinct bands at `keep_pct=70` (was 5 → 5).
Also spot-checked the CR-6 code paths still hold through the new grouping: a
synthetic overlapping-band case (all `hi_vel=127`, like the real file) kept
original ranges via the CR-6 guard; a synthetic contiguous 3-band/2-voices-
per-band case widened survivors correctly (3 → 2 bands, gap split at the
midpoint, both voices in each surviving band updated).

**CR-20 `thin_key_zones()` no-op for one-zone-per-voice presets — DONE
2026-07-27.** Found via VinSamLib (same downstream project as CR-19, same
session): CR-19's mirror image on the KEY axis. `reduce_key_zones_pct=30`/`60`
on the same real repro preset (`8VnEsHdMrcFat/SL`, 78 voices, each carrying
**exactly one zone** — the E4B parser's native shape for a densely
multisampled instrument) printed `removed 0 key zone(s)` at any percentage.
Root cause: `thin_key_zones(voice, keep_pct)` only thins zones *within one
voice* — correct for the XPM-keygroup representation it was written for (one
voice packs many zones across several velocity bands), but a no-op when
`len(voice.zones) == 1` for every voice, because the real key-zone variation
lives *across* voices instead — the exact same architectural gap CR-19 fixed
on the velocity axis, just transposed. Fixed by adding
`_thin_key_zones_across_voices()` (groups `preset.voices` by velocity band
first, then thins ACROSS the voices within each band by key position via
`_thin_and_redistribute`, keyed on each voice's own key range instead of
velocity range — mirrors CR-19's voice-grouping-by-band exactly, just on the
other axis) and a new dispatcher `thin_key_zones_for_preset()` that picks
between the existing within-voice `thin_key_zones()` (when any voice carries
`>1` zone — the XPM case) and the new across-voice path (when every voice
carries `<=1` zone — the E4B case). `reduce_bank()`'s `key_zone_pct` branch
now calls the dispatcher once per preset instead of `thin_key_zones()` per
voice. Verified: old code confirmed to reproduce `removed 0` on the real
file; new code removes 23/46 voices at `reduce_key_zones_pct=30`/`60`
respectively (matches the requested percentage exactly, mirroring CR-19's
verification). The pre-existing multi-zone-per-voice (XPM) case is
unaffected — same code path, same behavior, regression-tested directly.

**CR-21 `thin_velocity_layers()` picks a tiny outlier band as the sole
survivor at aggressive reduction — DONE 2026-07-28.** Found via real E4XT
hardware confirmation of VinSamLib's own test matrix (row 11,
`reduce_velocity_layers_pct=75.0` on the same `8VnEsHdMrcFat/SL` preset
CR-19/20 already used): 78 voices collapsed to **1 surviving voice, covering
only MIDI keys 63-66** — everywhere else on the keyboard silent on real
hardware, confirmed not sample corruption (the one surviving sample played
fine, intact PCM).

**Root cause:** the real preset's 5 velocity bands are wildly uneven in
size — `1 / 36 / 1 / 20 / 20` voices respectively (by `lo_vel` 0/1/9/50/86).
`_thin_and_redistribute`'s `keep_count == 1` special case picked
`ordered[n // 2]` — the **middle band by sorted-index position**, with zero
regard for how many voices (how much keyboard coverage) each band actually
represents. Sorted by `lo_vel`, the middle index (2 of 5) lands exactly on
the `vel[9-127]` band — a single stray voice covering 4 keys, almost
certainly a one-off fix-up sample in the original commercial patch, not a
real velocity layer. **Row 10 (`keep_pct=60`, keep 3 of 5 bands) wasn't
visibly broken but was equally miscalculated** — the evenly-spaced index
selection at `keep_count=3` picks indices `{0, 2, 4}`, which happens to
include *both* tiny 1-voice bands plus one legitimate 20-voice band
(1+1+20=22, matching the reported "78→22") — it only looked reasonable by
coincidence.

**Fix:** `_thin_and_redistribute` gained an optional `get_weight` parameter
(default `None` = the exact original uniform-index behavior, byte-for-byte,
so `thin_key_zones`/`_thin_velocity_bands_in_voice`/CR-19/CR-20's existing
call sites are untouched). When a weight function is given,
`keep_count == 1` picks the *heaviest* item (ties broken by proximity to the
middle index, preserving the old behavior when bands are evenly sized), and
`keep_count > 1` selects by evenly-spaced **cumulative weight** position
instead of raw index (falling back to greedily filling any collision from
one item's weight dominating the total). `thin_velocity_layers` now passes
`get_weight=len` for the multi-voice/band case, weighting each band by its
voice count.

**Verified** against the real repro file: 75% reduction now keeps the
36-voice band (80 distinct keys, range 48-127) instead of the 1-voice/4-key
outlier; 40% reduction now keeps 41 voices spanning the full 0-127 range
(up from 22, and with genuinely complete coverage this time, not by luck).
New regression tests `test_thin_velocity_layers_uneven_band_sizes_dont_pick_
outlier` (synthetic, exact 1/36/1/20/20 shape) and
`test_thin_velocity_layers_real_e4b_75pct_keyboard_coverage` (the real file,
the exact reported percentage) both confirmed to fail against the pre-fix
code and pass with it; the full existing suite (`tests/test_zone_reducer.py`)
still passes unchanged, confirming the default/uniform-weight path is
unaffected.

**Hardware-confirmed 2026-07-28.** Rebuilt the exact repro case (the real
file, `velocity_layer_pct=75.0`, the fixed code) as a standalone bank
(`11_reduce_velocity_75_FIXED.e4b` → `CD1-VL75FIX.iso`) and loaded it on
the real E4XT: plays across the full keyboard (C2-D8 in MPC-One octave
numbering), not just the previous 4-key silent-everywhere-else sliver.
Heavy aliasing at the pitch-shifted extremes is expected and correct for a
75% velocity-layer reduction (fewer samples stretched further), not a
regression. Closed.

Also worth noting: the VinSamLib hardware-test images already staged on
the SD card earlier this session (rows 08-12, as part of the consolidated
batch) were extracted from VinSamLib's own pre-built `.hda` files, built
with the pre-fix mpc2emu — they still reflect the old buggy thinning and
would need rebuilding downstream (in VinSamLib) to pick up this fix.

**CR-7 / 7b / 7c sample-name collisions — DONE 2026-06-11.**
- **CR-7** `bank_splitter.TargetBank.add_preset`: dedup now keys on
  `(name, len(data), hash(data))`. A genuine duplicate (same name+PCM) is shared;
  a same-name/different-PCM sample is renamed (16-char-safe suffix) and the
  preset's zones repointed. Verified: two `Kick`s with different PCM → `Kick` +
  `Kick1`, zone repointed, true dup still shared.
- **CR-7b** `sf2_parser._get_sample`: distinct SF2 samples whose names truncate
  to the same 16 chars now get a unique suffix (`used_names` set), so zones no
  longer resolve to the wrong sample/root.
- **CR-7c** `write_talsmpl`: preset filenames are de-duplicated per call
  (`Dup.talsmpl`, `Dup_1.talsmpl`) so same-named presets don't overwrite.

**CR-8 SF2 sampleModes — DONE 2026-06-10.** `sf2_parser` maps `sampleModes`
`1→FORWARD`, `3→FORWARD_REL`, `0/2→NO_LOOP`; never `ALTERNATING` (SF2 has no
ping-pong, so `write_e4b` no longer bakes reversed PCM into the sustain).

**CR-9 ISO cluster sizing — DONE 2026-06-10.** `_choose_cse(file_sizes)` now sums
the **per-file** ceilings `sum(ceil(size/cluster))` (was `ceil(total/cluster)`,
under-counting by up to one cluster/file) and raises a clear error if even the
largest cse overflows. Repro: 1000×600 KB → old est 1172 (would IndexError) vs
2000 real at cse=4 → now steps up to cse=5 (1000).

**CR-10 KRZ loop_end.** Include the loop-end word in the Soundfilehead position
struct (the `abs_loop_end` already computed), or truncate written PCM to loop_end
if the K2000 format implies loop=end. Verify against KurzFiler's layout.

**CR-11 resampler loop clamp — DONE 2026-06-10.** After resampling,
`n=len(pcm_out)//bpf`; `loop_start`/`loop_end` clamped to `[0, n]` (the
down-then-up `_decimate` pair can floor the length below source).

**CR-11b — FALSE POSITIVE (2026-06-10).** The recipe assumed MPC2000 sample
indices are 0-based with `names[0]` the first real sample. A real file
(`AMBIENCE_SET__1.PGM`) shows `names[0]=''` and **50 of 64 pads carry sn==0** as
the *unassigned* sentinel; real samples are indices 1–13. The existing
`0 < sn < len(names)` guard is correct — accepting `sn==0` would emit 50 phantom
zones onto an empty sample. **No change made.**

**CR-13 dedup — DONE 2026-06-11.** The EOS envelope rate↔time + level↔byte math
(`ENV_RATE_A/K`, `env_seconds_to_rate`/`env_rate_to_seconds`/`env_level_to_byte`/
`env_byte_to_level`) and the signed mod-cord codec (`cord_amount_to_byte`/
`cord_byte_to_amount`) now live once in `models/common.py`; `e4b_writer`/
`e4b_parser` keep thin `_fenv_*` aliases (so `tests` importing `_fenv_seconds`
still work) and call the shared cord codec (was inlined 5×).

**CR-14 EXS24 env — DONE 2026-06-11.** Deleted the quadratic `_env_byte_to_seconds`;
both amp and filter envelopes now use the linear CWM `_exs_env_to_seconds` (the
adopted EXS reference). *(Behaviour note: EXS24 amp-envelope times now follow the
linear curve — intentional.)*

**CR-15 dead code — DONE 2026-06-11.** Removed `_NT_MOD_TMPL` alias, the unused
local `import math` in `gig_parser` (no `math.` use) and `exs24_parser`, and the
unused `level_note` in the resampler verbose path; moved `find_multivoice.py` to
`tests/`.

**CR-17 parser registry — DONE 2026-06-11.** New `parsers/registry.py` holds the
single `ext → callable(path, wav_dir, **kw)` table + `INPUT_EXTS`; `convert.py`
and `info_cmd.py` both import it (was two drifted copies). Verified: convert
(XPM→E4B) and `--info` both run through it.

**CR-18 cord-builder — DONE 2026-06-11.** Added `_set_cord(mod, slot, src, dst,
amount, flag)` in `e4b_writer`, replacing the `slot*4 + n` offset arithmetic for
the free-slot LFO cords.

**CR-18 `Envelope` dataclass + EXS unify — DONE 2026-06-12.**
- **Envelope dataclass.** `VoiceLayer` stores `amp_env`/`filter_env` as
  `Envelope(attack, decay, sustain, release)`; `models.common` adds
  `_amp_env()`/`_filter_env()` `default_factory`s and eight property accessors
  (`env_attack`…/`filter_env_attack`…) that delegate to the dataclasses, so all
  existing `v.env_attack` reads/writes and `VoiceLayer(amp_env=Envelope(...))`
  constructor calls keep working.  Migrated the constructor call-sites that
  passed flat env kwargs (`e4b_parser`, `talsmpl_parser`, the three
  `tests/re_banks/gen_*` generators).  Validated: zero feature diffs XPM/SFZ/
  SF2/EXS → E4B (N=5 and N=14 seeds).
- **EXS24 "walker unify" → re-scoped.** The literal task (merge classic+v11,
  validate on real classic files) is **unsatisfiable for this corpus**: of 1717
  local `.exs` files, **0 are classic** — all are v1.1 — so the classic path is
  untestable dead code here.  Investigating the asymmetry instead exposed and
  fixed three concrete v1.1 bugs (all in `parsers/exs24_parser.py`):
  1. **`0x40000101` flag-variant rejection.** Some Logic Pro X exports OR
     `0x40000000` into the file magic and into every chunk type (magic reads
     `0x40000101`; zones `0x41000101`, samples `0x43000101`, …).  Layout is
     byte-for-byte normal v1.1.  Added `_V11_TYPE_FLAG = 0x40000000`, masked at
     the magic dispatch and at every `chunk_type` comparison in
     `_parse_exs_v11`.  14 corpus files were affected (Free-SP / SP-1200 /
     Analog-Tape From-Mars packs).
  2. **Long-common-prefix multisample collapse.** `_safe_name(stem)` truncates
     to 16 chars by default; using it as the sample-cache key meant every
     `DX100 Classic Bass-<note>-…` sample hashed to `DX100 Classic Ba`, so 36
     zones shared one SampleData.  Fixed by keying the cache on the full stem
     (`maxlen=255`).  Safe because the E4B zone entry references samples by
     **index** (`zone-entry[10:12]`), not by name, and bank_splitter/`_name16`
     apply the 16-char limit + uniqueness at write time.
  3. **`.aif`→`.wav`-twin resolution.** `load_wav` reads WAV only.  The From-
     Mars packs point the `.exs` at `.aif` but ship parallel `.wav` copies in a
     sibling `WAV/` folder.  Added a stem→path fallback index (preferring
     `.wav`) so an `.aif` reference whose exact name isn't a loadable WAV falls
     back to its same-stem WAV twin.
  Result: all 14 formerly-rejected files now parse full multisamples and
  round-trip **ERROR→PASS** through E4B.  Remaining gap (separate TODO): packs
  that ship **AIFF only** (no WAV twin) still won't load — needs real AIFF
  decode support in `load_wav` (Python's `aifc` is removed in 3.13, so a small
  manual AIFF reader would be required).

**CR-16 perf #2/#3 — DONE 2026-06-11.**
- **#2 `write_e4b` memory:** `_build_sample_body` split into `_build_sample_header`
  (header only); the writer computes all offsets/sizes from lengths, then streams
  `header + sample.data` per sample straight to the open file — no `join`/concat,
  so peak RAM drops from ~5× the bank's PCM to ~1×. **Byte-identical** verified
  (regenerated a ~1 MB multi-sample bank, `cmp` clean) + pipeline round-trip.
- **#3 resampler:** `_pcm_to_float`/`_float_to_pcm` use bulk `array('h')` (LE,
  byteswap on big-endian hosts) instead of per-frame `struct`. Byte-identical;
  **measured ~2× decode / ~1.3× encode** — the per-element float divide/clip is
  the floor without numpy (the resampler stays stdlib), so the earlier "~30-50×"
  estimate was wrong.
- **#1 gig decode — DONE 2026-06-11.** 24-bit→16-bit is `val>>8`, which equals
  the signed-16 of a frame's top two bytes, so it's a bulk `bytearray` slice
  (`out[0::2]=raw[1::3]; out[1::2]=raw[2::3]`; **~200× faster**, byte-identical).
  8-bit→16-bit `(b-128)*256` is a sign-flip into the high byte → bulk
  `raw.translate(_FLIP_SIGN8)`.  Both replace per-sample `struct.pack_into`
  loops; verified byte-identical against the old arithmetic on random data.
- **#4 ISO/HDA — DONE 2026-06-11.** `iso_builder` (both EMU3 + ISO-9660 paths)
  and `hda_builder` now copy each embedded E4B in 1 MB chunks and write the
  cluster/sector pad separately, instead of `src.read()` + `data + b'\x00'*pad`
  (which held the whole file twice).  Verified: regenerated ISO byte-identical
  (`cmp`); HDA round-trip embeds the E4B verbatim.
- *(Considered `audioop` for #1/#3 — byte-identical but deprecated and removed in
  Python 3.13, so avoided.)*

---

## Index

| TODO item | Resolution type | Status |
|---|---|---|
| Code-review findings CR-1..18 | Code (no RE) | **CR-1–17 DONE + CR-18 cord-builder** (11b false-positive); only CR-18 `Envelope` dataclass (recommend skip) + EXS-unify (needs `.exs` files) left — §CR |
| Amp envelope decay byte | **RESOLVED 2026-06-08** | PZT[4]=Decay1 rate confirmed (AMPENV_SETME + AMP_DECAY_CAL banks) |
| `_fenv_rate()` calibration | **RESOLVED 2026-06-08** | Log fit from 6 E4XT decay measurements; writer + parser updated |
| Ping-pong loop bit | **RESOLVED 2026-06-08** | EOS has no ping-pong mode; bounce baked into PCM (loop_renderer.py) |
| Swept/Phaser/Flanger/Vocal/Morph filter bytes | **RESOLVED 2026-06-08** | All vpar[58] bytes confirmed from B.005-FILTERTYPES.E4B (§4) |
| Zone entry `fine_tune` field | Hardware RE | Procedure written — test banks at `tests/re_banks/` |
| Zone entry `volume` field | Hardware RE | Same test bank as fine_tune |
| EXS24 v1.1 zone fields misassigned | **APPLIED 2026-06-08** | Fixed + verified on real files |
| EXS24 GROUP_V11 stereo doubling | **APPLIED 2026-06-08** | Fixed; ks+11 maps via sorted-distinct, verified corpus-wide |
| EXS24 multi-velocity layers | Deferred | Waiting for corpus with vel-layered EXS24 |
| SF2 MIDI program numbers | **APPLIED 2026-06-08** | byte[31]=program_number, verified |
| TAL filtermode encoding | **FULLY RESOLVED 2026-06-08** | 13 modes, N=UI position; 6 corners confirmed by Jan |
| E4B vpar[42] = Chorus Amount | **RESOLVED 2026-06-08** | 0-100% → 0-127; model+writer+parser wired (§13) |
| SMP velocity grouping | **APPLIED 2026-06-08** | One NT voice per vel range, verified |
| Filter envelope reproduction | **RESOLVED 2026-06-09** | Routing fixed (FilterEnv→Cutoff cord, amount=`filter_env_amount`) + hardware-confirmed; source mapping XPM/SFZ/SF2/GIG/EXS24 ✅; shares amp rate-curve (§17) |
| XPM envelope values = 0–1, not seconds | **RESOLVED 2026-06-09** | MPC One: `seconds≈0.00079·e^(9.78·v)`; `_xpm_env_to_seconds()` wired; filter env confirmed same curve (§18) |
| Mod routing: Key→Filter, Velocity→Filter | **DONE 2026-06-09** | cords 06/04, mapped from GIG/SFZ/XPM/EXS24 (§15) |
| LFO modulation routing | **DONE 2026-06-10** (§15); GIG deferred | LFO1+LFO2 bytes + LFO→Pitch/Filter/Q cords RE'd & round-trip; input mapping done for XPM/SFZ/SF2; only GIG LFO left (needs test file) |
| XPM PGM binary format | Deferred | Needs format docs |
| HDA directory >16 entries | **APPLIED 2026-06-08 (guard)** | Warns + truncates to 16, verified |
| EXS24 PPC big-endian | **WON'T FIX 2026-06-08** | Unreachable dead code removed; undetectable by magic |

---

## 1. Amp envelope: decay byte — RESOLVED (2026-06-08)

The amp envelope is the 6-stage rate/level block at `PZT[0:12]` (mirror of the
filter envelope at `PZT[14:26]`), confirmed on hardware:

```
PZT offset : interpretation
  [0/1]   Amp Attack1  rate / level
  [2/3]   Amp Attack2  rate / level   (rise to +100%)
  [4/5]   Amp Decay1   rate / level   ← decay rate = PZT[4] (CONFIRMED)
  [6/7]   Amp Decay2   rate / level   (hold at sustain)
  [8/9]   Amp Release1 rate / level   (fall to silence)
  [10/11] Amp Release2 rate / level
  [12]    0x03  envelope mode/pointer (constant)
  [13]    0x00
```

### Evidence

- **`AMPENV_SETME.E4B`** (baseline) — set known values on the E4XT Amp Envelope
  page and saved; the page writes exactly these 12 bytes
  (`00 00 00 7f 00 7e 00 7f 7f 00 00 00`).
- **`AMP_DECAY_CAL.E4B`** — 6 voices that differ in nothing but the decay
  setting; the **only** byte that moves is `PZT[4]` (`08 10 18 20 30 40`),
  proving PZT[4] is Amp Decay1 rate. The same sweep gave the rate→time
  calibration (see §2).

### Applied

`_build_voice()` in `e4b_writer.py` writes the full `PZT[0:12]` amp envelope
(attack → full, decay → sustain held through Decay2, release → silence), using
the calibrated `_fenv_rate()`. `_parse_voice()` in `e4b_parser.py` reads it back
via the matching `_fenv_rate_inv()`. The rate→time fit itself is §2.

The decay *level* sits at `PZT[5]` (= sustain), `PZT[6/7]` hold it through
Decay2, matching the manual's "set the '2' levels = the '1' levels, '2' rates
= 0" standard-ADSR mapping.

---

## 2. `_fenv_rate()` calibration — RESOLVED (2026-06-08)

### What was wrong

The old formula `round(80.0 / (t + 0.01))` was copied from the filter envelope
and never independently calibrated. It also had the **direction backwards**: it
treated rate 0 as the slowest (infinite) time, when hardware shows rate 0 is the
*fastest* (instant) and the byte increases monotonically with time.

### Measurements

6 Decay-1 decay-to-silence times measured on the E4XT (`AMP_DECAY_CAL.E4B`):

| rate | time    | rate | time    |
|-----:|--------:|-----:|--------:|
|    8 | 0.034 s |   32 | 0.198 s |
|   16 | 0.098 s |   48 | 0.454 s |
|   24 | 0.169 s |   64 | 1.225 s |

Log-linear fit (R²=0.96): **`time_s = 0.0310 · e^(0.0581 · rate)`**, i.e.
rate 0 ≈ 0.031 s (instant) and rate 127 ≈ 47 s (slowest).

**Re-validated 2026-06-09** by re-recording `AMP_DECAY_CAL` and analysing it with
`tests/re_banks/analyze_envelope_recording.py` (two passes, identical to the ms).
The automated τ(1/e) progression is smoother than the original hand-timed table
(which had a rate 24→32 kink); the fitted exponent (~0.058 at rates 32–64,
slightly steeper at the fast end) confirms the K=0.0581 curve. No change made —
the original calibration stands.

### Applied

- `writers/e4b_writer.py`: constants `_ENV_RATE_A = 0.0310`,
  `_ENV_RATE_K = 0.0581`; `_fenv_rate(seconds)` →
  `round((ln(s) − ln(A)) / K)` clamped to 0..127; inverse
  `_fenv_seconds(rate) = A · e^(K · rate)`.
- `parsers/e4b_parser.py`: `_fenv_rate_inv()` rewritten as the exact mirror of
  `_fenv_seconds()` (same constants), replacing the old `80.0/rate − 0.01`.
  Verified equal to the writer across rates 0..127 and round-trip stable.

### Byte position

`AMP_DECAY_CAL.E4B` doubles as the byte-position proof: across its 6 voices the
**only** byte that changes is `PZT[4]` (`08 10 18 20 30 40` = the swept rates),
so PZT[4] is unambiguously Amp Decay1 rate. The full 12-byte amp-envelope layout
was separately confirmed from the `AMPENV_SETME.E4B` baseline. See §1.

---

## 3. Ping-pong loops — RESOLVED + faithfully reproduced (2026-06-08)

**EOS has no ping-pong loop mode.** The EOS 4.0 Software Manual (Sample Edit →
Loop Type) confirms looping is a sample-level **On/Off** toggle with a single
forward loop. There is no forward/backward (ping-pong) loop *mode*: the manual
notes EIII forward/backward loops are **rendered into the PCM data** on import
("the loop data will be permanently modified to contain the forwards/backwards
sound data"), not preserved as a mode. So the old speculative `0x0033` byte was
meaningless and has been removed.

**We now reproduce ping-pong the same way EOS does** — by baking the bounce
into the PCM (`processors/loop_renderer.py`, the standard/recommended technique
for forward-only engines). For a ping-pong loop over forward frames S[0..n-1],
the renderer appends the reversed interior S[n-2..1] (endpoints not repeated)
to make a 2n-2-frame region that a plain forward loop plays as the bounce.
`write_e4b()` applies `bake_alternating_loop()` to every sample (on a local
copy — never mutating the caller's bank) before serialising, so an `ALTERNATING`
loop from EXS24 (`loop_mode=2`), SFZ (`loop_mode=alternate`), GIG/DLS
(bidirectional) or a WAV SMPL ping-pong loop is preserved audibly rather than
silently flattened to a forward loop.

Cost: the looped interior roughly doubles in size (n-2 extra frames per
ping-pong sample). Verified end-to-end (synthetic + round-trip via `parse_e4b`).

**Possible future enhancement (separate from ping-pong):** EOS's per-sample
"Loop in Release" flag may correspond to another bit in the `options` u16; not
currently modelled. Low priority.

---

## 4. Swept EQ / Phaser / Flanger / Vocal / Morph filter bytes — RESOLVED (2026-06-08)

All EOS `vpar[58]` filter-type bytes — including the swept/parametric ones — are
confirmed from the hardware-saved `B.005-FILTERTYPES.E4B` (one preset per type,
set on the E4XT and saved; in `/home/lentferj/temp/re_filter_types/`). Encoding
is `byte = group_base | variant`:

- LP `0x00/01/02`, HP `0x08/09`, BP `0x10/11/12`
- **Swept EQ `0x20/21/22`, Phaser `0x40/41/42`, Flanger `0x48`,
  Vocal `0x50/51`, Morph `0x60/61/62`, Peak/Shelf `0x68`**

Full table in `writers/e4b_writer.py:_E4XT_FILTER_BYTES` and
`docs/E4B_FORMAT.md` §4.4. The MPC Vocal-formant types map to the E4XT Vocal
filters; Swept/Phaser/Flanger/Morph have **no MPC-XPM source equivalent**, so
they're written-capable and reverse-mapped when parsing hardware banks, just not
reachable from current input formats (a source-format gap, not an open RE item).

---

## 5. Zone entry: `fine_tune` and `volume` fields

### Current state

`_zone_entry()` in `e4b_writer.py` writes only 6 of 22 zone-entry bytes.
`fine_tune` (cents) and `volume` (dB) are parsed from GIG and other formats
but not written because their byte offsets are unknown.

### Structural analysis of the 22 zero bytes

Known positions: `[2]` lo_key, `[5]` hi_key, `[6]` lo_vel, `[9]` hi_vel,
`[10:12]` sample_idx (BE u16), `[14]` root_key.

Unused bytes: 0,1, 3,4, 7,8, 12,13, 15,16,17,18,19,20,21.

Educated guesses based on similar formats and symmetry:
- `[12]` or `[13]`: fine_tune (signed byte, cents) — follows root_key at [14]
- `[0]` or `[1]`: per-zone volume or gain trim (0–127 linear, or signed dB)
- `[3]` or `[4]`: pan (-64..+63?)
- `[7]` or `[8]`: may mirror lo_vel/hi_vel redundantly (like voice-level vel range)
- `[15:22]`: possibly a per-zone modulation or routing slot

### Hardware RE procedure

See `docs/re_procedures/zone_entry_fields.md` and test bank generator
`tests/re_banks/gen_zone_entry_test.py`.

Two-step diff test:
1. Two presets, same sample, same key, **only fine_tune differs** (0 vs +50).
   → The changing byte(s) are fine_tune.
2. Two presets, same sample, same key, **only per-zone volume differs** (0 dB vs −12 dB).
   → The changing byte(s) are volume.

---

## 6. EXS24 v1.1 zone fields misassigned — CRITICAL

**Status: ready to apply. No hardware needed.**

### Bug

In `_parse_exs_v11()` (`parsers/exs24_parser.py:170–172`) three offsets are
wrong — the three most critical per-zone fields:

| Offset | Current label | **Actual meaning** |
|--------|-------------|-------------|
| `ks+9`  | `key_lo`    | `root_key` (sample centre pitch) |
| `ks+14` | `key_hi`    | `key_lo` (keyboard bottom — 0 is valid) |
| `ks+15` | `key_root`  | `key_hi` (keyboard top — 127 for last zone) |

Also: `ks+12` is `fine_cents` (not `coarse`), `ks+13` is `coarse_st` (not `fine`).

### Exact patch

In `parsers/exs24_parser.py`, replace lines 170–181:

```python
# BEFORE (broken):
key_lo   = data[ks + 9]
key_hi   = data[ks + 14] or key_lo
key_root = data[ks + 15] or key_lo
coarse   = struct.unpack_from('b', data, ks + 12)[0]
fine     = struct.unpack_from('b', data, ks + 13)[0]
vel_hi   = data[ks + 18]
zones_raw.append({
    'index': z_idx, 'name': name,
    'key_lo': key_lo, 'key_hi': key_hi, 'key_root': key_root,
    'vel_lo': 0, 'vel_hi': vel_hi,
    'coarse': coarse, 'fine': fine,
})

# AFTER (correct):
root_key = data[ks + 9]
key_lo   = data[ks + 14]                    # 0 = keyboard bottom (valid — no fallback)
key_hi   = data[ks + 15] or root_key        # 0 = unset → fall back to root
fine_cents = struct.unpack_from('b', data, ks + 12)[0]   # signed, cents
coarse_st  = struct.unpack_from('b', data, ks + 13)[0]   # signed, semitones
vel_hi   = data[ks + 18]
zones_raw.append({
    'index': z_idx, 'name': name,
    'key_lo': key_lo, 'key_hi': key_hi, 'key_root': root_key,
    'vel_lo': 0, 'vel_hi': vel_hi,
    'coarse': coarse_st, 'fine': fine_cents,
})
```

### Impact of the bug

- Full-range single-zone instruments (TB-303, organs): zone collapses to one
  key with root=127 → -98 semitone transpose → completely inaudible on hardware.
- Multi-zone chromatic instruments: bottom range lost on first zone; root=127
  on last zone.

---

## 7. EXS24 GROUP_V11: stereo doubling — APPLIED (2026-06-08)

### Problem

GROUP_V11 chunks were silently skipped. For stereo 101 From Mars instruments,
L+R zones both got included → doubled polyphony + doubled RAM.

### What the empirical test revealed (correction to the original RE)

The original assumption that `ks+11` is a **0-based index** into file-order
groups was **WRONG**.  Scanning the corpus (Oscar / StereoTracks / ExitSummer):

```
Oscar.exs        groups=['Oscar_L','Oscar_R']     zone group_byte ∈ {100, 156}
StereoTracks.exs groups=['StereoTracks_L','_R']   zone group_byte ∈ {100, 156}
ExitSummer.exs   groups=['ExitSummer_L','Layer 1'] zone group_byte ∈ {100, 156}
```

`ks+11` is some encoded reference (100, 156 — not 0, 1).  The robust decode:
the **distinct group_byte values map to file-order groups when sorted ascending**
(100 → group[0], 156 → group[1]).  Each group independently covers the full key
range, so dropping the `_R` group leaves a complete playable map.

### Applied fix (`_parse_exs_v11`)

1. Collect GROUP_V11 names in file order; store `group_byte = data[ks+11]` and a
   file-order `pos` on each zone.
2. After the zone sort: build `gb_to_group = {sorted_distinct_gb[i]: i}`; build a
   drop set of groups whose name ends `_R`/`_r` **and** has an `_L` partner of the
   same base name; gate on `len(distinct_gb) == len(group_names)` (else keep all).
3. Filter `zones_raw` **and** `samples_raw` in lockstep at the dropped file
   positions (zone[i] ↔ sample[i] holds for these instruments), leaving the
   existing positional pairing loop untouched.

### Verification (no hardware needed)

Corpus-wide scan of 2092 v1.1 files: only the 2 true `_L`/`_R` pairs drop zones
(Oscar 162→81, StereoTracks 156→78); ExitSummer keeps all 182 (partner "Layer 1"
isn't an `_R`); zero false positives elsewhere.

---

## 8. EXS24 multi-velocity layers

**Deferred.** No velocity-layered EXS24 instruments found in current test
corpus (101 From Mars / Acid From Mars / 2600 From Mars all use GROUP chunks
for L/R stereo separation only, with `vel_hi=127` everywhere).

If a velocity-layered EXS24 instrument appears: implement a grouping pass
similar to `vel_key` grouping in `xpm_parser.py`, with one `VoiceLayer` per
distinct `vel_lo/vel_hi` range.

---

## 9. SF2 MIDI program numbers

**Status: ready to apply.**

### Problem

`_toc_entry()` always writes `e[31] = 0x00` (MIDI program = any).
`Preset.program_number` is set correctly by the SF2 parser but never used.

### Fix

In `write_e4b()` / `_toc_entry()`, change the `e[31]` write:

```python
# In _toc_entry(), change the last line:
# BEFORE:
e[31] = 0x00   # MIDI prog (any)

# AFTER: accept midi_prog parameter
def _toc_entry(tag, data_size, file_offset, idx, name, midi_prog=0):
    ...
    e[31] = min(127, max(0, midi_prog)) & 0xFF
```

And in `write_e4b()`:
```python
# Preset TOC entries:
for i, p in enumerate(bank.presets):
    toc_entries += _toc_entry(PRES_TAG, len(preset_bodies[i]),
                               preset_offs[i], i, p.name,
                               midi_prog=p.program_number)
```

Collision handling: the current code assigns sequential preset indices (0,1,2…)
regardless of MIDI program number. The E4XT uses TOC entry `[31]` as a hint
for MIDI routing; writing the original program number there is correct even if
multiple presets share the same number (the E4XT picks by preset index, not
by program number alone). No collision handling needed — just write the value.

---

## 10. SMP (non-transpose) velocity grouping

**Status: ready to apply.**

### Problem

In `xpm_parser.py`, all non-transpose zones land in one `VoiceLayer(non_transpose=True)`
regardless of velocity range.  If an XPM has SMP layers at vel 0–63 and 64–127,
both end up in the same voice and the E4XT plays both simultaneously.

### Fix

Apply the same `vel_key` grouping used for pitched zones to SMP zones.
In `xpm_parser.py`, the SMP-mode grouping:

```python
# Current (broken): single NT voice for all SMP zones
smp_voice = VoiceLayer(non_transpose=True)
for layer in layers:
    if layer['root'] == 0:
        smp_voice.zones.append(...)

# Fix: one NT voice per distinct vel range (same pattern as KT voices)
smp_by_vel: dict = {}   # (lo_vel, hi_vel) → VoiceLayer
for layer in layers:
    if layer['root'] == 0:
        vel_key = (layer['vel_lo'], layer['vel_hi'])
        if vel_key not in smp_by_vel:
            smp_by_vel[vel_key] = VoiceLayer(non_transpose=True)
        smp_by_vel[vel_key].zones.append(...)
for v in smp_by_vel.values():
    preset.voices.append(v)
```

---

## 11. HDA directory >16 entries

**Status: ready to apply (add guard/warning).**

### Problem

`writers/hda_builder.py` fits at most 16 E4B files in a single 512-byte
directory block (32 bytes × 16 entries = 512 bytes).  No warning is emitted
when the limit is exceeded; excess files are written to disk but invisible
to the E4XT.

### Fix (guard + warning, not multi-block)

Multi-block directory support is complex and low-priority.  Instead, add:

```python
_MAX_HDA_FILES = 16   # 512-byte dir block / 32 bytes per entry

def write_hda(e4b_paths: list, output_path: str) -> None:
    if len(e4b_paths) > _MAX_HDA_FILES:
        print(f"[ERROR] HDA directory supports max {_MAX_HDA_FILES} files; "
              f"got {len(e4b_paths)}. "
              f"Split into multiple HDA images or increase banks-per-HDA.")
        # Still write what fits; warn about dropped files
        dropped = e4b_paths[_MAX_HDA_FILES:]
        print(f"  Dropped: {[Path(p).name for p in dropped]}")
        e4b_paths = e4b_paths[:_MAX_HDA_FILES]
    ...
```

Future: implement multi-block directory by chaining 512-byte blocks
(each block's last 4 bytes point to the next block's disk offset, or 0 if
last — needs hardware RE to confirm the chaining convention).

---

## 12. TAL-Sampler filtermode encoding — FULLY RESOLVED (2026-06-08)

**13 modes, N = UI dropdown position = internal storage index.**

Confirmed by corpus survey (1706 presets, step=1/12 exact) plus six explicit
`EV-VintageFifthLead_*.talsmpl` saves by Jan Lentfer:

| N  | filtermode | TAL name  | XPM type  | Status |
|----|------------|-----------|-----------|--------|
| 0  | 0.000      | LP 4P     | 3 Low 4   | confirmed — `_LP4P.talsmpl` |
| 1  | 0.083      | LP 2P     | 2 Low 2   | derived (N=UI pos, N=1) |
| 2  | 0.167      | LP 1P     | 1 Low 1   | derived (0 corpus presets) |
| 3  | 0.250      | LP 4PN    | 3 Low 4   | derived |
| 4  | 0.333      | LP 3PN    | 3 Low 4   | derived (no 3-pole XPM) |
| 5  | 0.417      | LP 2PN    | 2 Low 2   | derived |
| 6  | 0.500      | LP 1PN    | 1 Low 1   | confirmed — `_LP1PN.talsmpl` |
| 7  | 0.583      | HP 2PN    | 7 High 2  | confirmed — `_HP2PN.talsmpl` |
| 8  | 0.667      | HP 3PN    | 8 High 4  | derived (no 3-pole HP XPM) |
| 9  | 0.750      | BP 4PN    | 12 Band 4 | confirmed — `_BP4PN.talsmpl` |
| 10 | 0.833      | Notch 2P  | 15 BS 2P  | derived (0 corpus presets) |
| 11 | 0.917      | All Pass  | 3 Low 4   | confirmed — `_AllPass.talsmpl` (no E4B equiv) |
| 12 | 1.000      | BW 6P     | 4 Low 6   | confirmed — `_BW6P.talsmpl` |

Code: `_TAL_FM_XPM = [3, 2, 1, 3, 3, 2, 1, 7, 8, 12, 15, 3, 4]`
Formula: `mode = min(12, max(0, round(val * 12)))`

The only residual approximations are XPM-side (no 3-pole LP/HP in XPM; All Pass
has no E4B equivalent) — the TAL→XPM mode names are now fully confirmed.

---

## 13. E4B vpar[42] = Chorus Amount — RESOLVED (2026-06-08)

`vpar[42]` is the per-voice **Chorus Amount** (Voice/Tuning page). UI 0–100%
maps linearly to byte 0–127:

```
vpar[42] = round(chorus_pct / 100 * 127)        # write
chorus_pct = round(vpar[42] / 127 * 100)         # read
```

### Confirmation (hardware, E4XT)

Read straight off commercial banks, then nailed with a hand-edited save:

| Source | Chorus % | vpar[42] | round(%·1.27) |
|---|---:|---:|---:|
| Ya Mogue (Ya Tech) | 17 | 22 | 21.6 → 22 |
| Phase Rogue | 34 | 43 | 43.2 → 43 |
| Dance Rogue | 35 | 44 | 44.5 → 44 |
| Be an ULTRA (Dutch Stab) | 50 | 64 | 63.5 → 64 |
| WATCH OUT (Dutch Stab) | 89 | 113 | 113.0 → 113 |
| **edited sweep** | 25 / 50 / 75 / 100 | 32 / 64 / 95 / 127 | exact |

The 89→113 and 34→43 points rule out a `/128` scaling; the 25/50/75/100 →
32/64/95/127 sweep pins linearity and the 100 % → 127 maximum. Default 0 = off
(matches the 31 855 zero-valued voices in the corpus).

Chorus **stereo width** is a *separate* parameter (was 100 % in all samples) at
a different, still-unlocated byte — see the note in `TODO.md` if it ever
matters.

### Applied

- `models/common.py`: `VoiceLayer.chorus_amount` (float 0.0–1.0, default 0.0).
- `writers/e4b_writer.py` `_build_voice()`: `vpar[42] = round(chorus*127)`.
- `parsers/e4b_parser.py` `_parse_voice()`: `chorus_amount = vpar[42]/127`.

Byte↔float round-trips bijectively over all 128 values; verified by re-parsing
the edited bank (reads back 25/50/75/100 %).

No source format currently supplies a chorus-amount value, so writers leave it
at the 0.0 default unless an E4B is round-tripped; wiring a source mapping (if
any MPC/XPM/etc. field maps to it) is future work.

---

<details>
<summary>Original corpus investigation (how it was narrowed before the hardware read)</summary>

### Corpus evidence (full ProRec + Rob Papen + Kirk Hunter scan)

Scanned 131 commercial banks / 32 558 voices. `vpar[42]` is non-zero in
703 voices (2.2 %). Findings:

- **Standalone single byte.** The neighbours `vpar[41]` and `vpar[43]` are
  almost always zero (6 and 13 of 703), so byte 42 is *not* the low/high half
  of a 16-bit word — it is one 0–127-ish scalar (observed range ≈ 4–113, with
  most values ≤ 44; 113 is a rare outlier).
- **Per-voice tweakable.** In synth banks the value varies voice-to-voice
  (e.g. *Ambient Synth*: 23/17/33/11/36/29/14/9/4; *Ya Tech*: 22/43/44), so it
  is a real per-voice parameter, not a fixed flag.
- **Authors set it bank-wide on sliced loops.** The dominant value 15 (584 of
  703 voices) is **constant across entire sliced drum-loop banks** — every
  slice voice in *LPS 1/2/3* has exactly 15; *Hollywood* is all 16. A value an
  author sets once and copies to every slice of a loop.
- **No correlation** with the already-decoded properties (filter type/cutoff/Q,
  amp gain, tuning, velocity range) — the bytes that co-occur with a non-zero
  42 are just the always-set structural/template bytes.

### What this rules in / out

- **Rules OUT sample-start offset:** that would have to *differ* per slice of a
  drum loop, but byte 42 is *constant* across all slices. Drop it.
- **Rules OUT a 16-bit value** (41/43 are zero).
- **Rules IN** a single per-voice scalar that a loop author would apply
  uniformly to every slice. Best-fit candidates, in order:
  1. **Glide / portamento rate** (EOS "Glide Rate", 0–127) — uniform across a
     kit, per-voice on synths.
  2. **Chorus amount / width** (per-voice chorus send) — same usage pattern.
  3. **Voice "Group"** number (exclusive/mute group for voice-stealing) — loop
     authors often assign all slices to one group; 0 = none.

### How to confirm (two paths, fastest first)

**Path A — read it straight off a bank Jan already owns (no test banks):**
Load `B.000-LPS 1 136bpm RP` (or `Hollywood`) on the E4XT, open any voice, and
walk the voice-editor pages looking for the parameter that reads a non-default
**15** (Hollywood: **16**). Whatever page shows that value *is* `vpar[42]`.
This is the cheapest experiment and uses real non-zero data.

**Path B — isolate by single-parameter sweep:** start from one neutral preset,
make 3–4 copies that differ in exactly one candidate (Glide, then Chorus, then
Group), save each as E4B, and binary-diff byte 42. The candidate whose change
moves byte 42 is the answer; record the value↔setting mapping to calibrate.

To target a specific voice on hardware, use the inspector
`tests/re_banks/inspect_vpar.py` (gathered all the evidence above):

```bash
# list every preset/voice carrying a non-default vpar[42], with values
python3 tests/re_banks/inspect_vpar.py --nonzero \
    "~/Dokumente/SYNTHS/E4XT/E4Bs/.../B.000-Hollywood _.e4b"
```

It prints `bank / preset / voice# / value`, so Jan can open exactly that
preset+voice on the E4XT. `--byte N` reuses it for any other unknown voice byte.

</details>

---

## 14. EXS24 PPC big-endian — WON'T FIX / removed (2026-06-08)

The big-endian branch was **unreachable dead code** and has been removed. A
genuine PPC big-endian EXS file stores its magic as the on-disk bytes
`00 00 00 01`, but those same bytes read little-endian equal `0x01000000`
(`HEADER_MAGIC_LE`), which the parser checks first — so the BE branch could
never execute, and a real PPC file would be (mis)parsed as little-endian
regardless. The two endiannesses cannot be distinguished by magic alone.

Resolution: removed the unreachable branch, the unused `be` flag, and the
vestigial `*_BE` chunk/magic constants; documented EXS24 as little-endian
classic + v1.1 only (README / module docstring). PPC-era test data is also
effectively unobtainable, so there is nothing to validate. Closed as won't-fix.

---

## 15. LFO modulation routing

**Partially unblocked — cord format now known; specific routings wanted.**

**Target (Jan, 2026-06-09):** write at least **LFO→Pitch, LFO→Filter-Freq,
LFO→Filter-Q**, **Key→Filter-Freq** (filter keytrack) and **Velocity→Filter-Freq**
when the input format provides them. Input coverage: XPM (`LfoPitch/LfoCutoff/…`,
`FilterKeytrack`, `VelocityToFilter`), SF2 (`modLfoToPitch/FilterFc/Volume`,
`vibLfoToPitch`, default Velocity→Cutoff modulator), SFZ (`pitchlfo_*/fillfo_*/
amplfo_*`, `fil_keytrack`, `fil_veltrack`), GIG (LFO1/2/3, `VCFKeyboardTracking`,
`VCFVelocityScale`), EXS24 (`FILTER1_KEYTRACK`, velocity-to-filter).

The 4-byte PatchCord format is **confirmed** (no longer a hypothesis — see §4.3
of `E4B_FORMAT.md` and Gap 0 of §17): `[src, dst, amount, flag]`, amount
`= round(pct/100 × 127)` signed, UI cord N = storage slot N. Known ids:
`src 0x50` = Filter-Envelope, `dst 0x38` = Filter-Frequency.

**Decoded so far (2026-06-09, from default-preset cords on the E4XT):**
sources LFO1=`0x60`, Velocity=`0x0C`, Key=`0x08`, FilterEnv=`0x50`; dests
Pitch=`0x30`, Filter-Freq=`0x38`. The `_MOD_TMPL` already carries the cords (all
amount 0): slot 2 LFO1→Pitch (`mod[10]`), slot 4 Velocity→Filter (`mod[18]`),
slot 5 FilterEnv→Filter (`mod[22]`, done), slot 6 Key→Filter (`mod[26]`).

**DONE 2026-06-09 — Key→Filter and Velocity→Filter:** `VoiceLayer.filter_keytrack`
/ `velocity_to_filter` (signed ±1 → cord amounts `mod[26]` / `mod[18]`), written +
read back, mapped from GIG (`VCFKeyboardTracking`/`VCFVelocityScale`, verified on
the maestro grand), SFZ (`fil_keytrack`/`fil_veltrack`), XPM, EXS24
(`FILTER1_KEYTRACK`, scaling unverified). SF2 skipped.

**LFO 1 + LFO 2 settings DECODED & IMPLEMENTED (2026-06-10)** from
`B.011-LFO1 settings.E4B`. They live in the **Primary Zone Table**, not `vpar`;
LFO 2 is an exact **+8 mirror** of LFO 1:

| LFO1 | LFO2 | Param | Encoding |
|---|---|---|---|
| `PZT[42]` | `PZT[50]` | **Rate** | 0–127, default 64. **Hz**: byte 0=0.08, 64=4.12, 127=18.01 (E4XT menu); *not* exponential — log-quadratic fit `ln(Hz)=−3.006e-4·b²+0.08082·b−2.5257` (3-point, refineable) |
| `PZT[43]` | `PZT[51]` | **Shape** | **signed**: −1=Random, 0=Triangle, **1=Sine**, 2=Sawtooth, 3=Square, 4–7=33/25/16/12% Pulse, 8–11=Pat Octaves/Fifth+Octave/Sus4/Neener, 12–13=Sine1,2 / Sine1,3,5, 14=Sine+Noise, 15=Hemi-quaver |
| `PZT[44]` | `PZT[52]` | **Delay** | 0–127 → 0–20 s |
| `PZT[45]` | `PZT[53]` | **Variation** | 0–127 = **0–100 %** (`round(pct/100×127)`, 100 %=127) |
| `PZT[46]` | `PZT[54]` | **Sync** | 0=Key Sync (default), 1=Free Run |

All confirmed against the hardware bank. **Sine=1 confirmed** (`LFO1+2 SINE`
preset: `PZT[43]`+`PZT[51]`=01). `PZT[48]`=01 is a constant between the blocks
(unknown). **Lag processors** follow the LFO block: `PZT[57]`=Lag0, `PZT[59]`=Lag1
(P011 lag0:5/lag1:10 markers).

**Mod cords DECODED (2026-06-10)** from P012's `Chrd10 LFO-FltQ` preset:

| Source id | | Dest id | |
|---|---|---|---|
| `0x60` LFO1~ / `0x61` LFO1+ | | `0x30` Pitch | `0x38` Filter-Freq |
| `0x68` LFO2~ / `0x69` LFO2+ | | `0x39` **Filter-Q (resonance)** | `0x4A` **Vol-Env Decay** |

All four LFO source ids confirmed (LFO1~`0x60` from two cords + the default
LFO1→Pitch; LFO1+`0x61`, LFO2~`0x68`, LFO2+`0x69` from P012 cords 11/12/13).

**IMPLEMENTED:** `VoiceLayer.lfo{1,2}_{rate,shape,delay,variation,sync}` (rate in
Hz, `Optional`/`None`=EOS default) + routing fields `lfo1_to_pitch` (default cord
02 `mod[10]`), `lfo1_to_filter`/`lfo1_to_filter_q`/`lfo2_to_pitch`/
`lfo2_to_filter`/`lfo2_to_filter_q` (written into free cord slots 8+ as
`[src,dst,amt,0]`). The rate byte↔Hz curve lives in `models/common.py`
(`lfo_rate_byte_to_hz` / `lfo_rate_hz_to_byte` / `lfo_knob_to_hz` /
`lfo_pitch_depth_to_amount`), shared by writer, E4B parser and source parsers;
writer `_write_lfo`, parser `_find_cord` — full E4B round-trip, validated against
`B.011`.

**DONE 2026-06-10 — input-format source mapping (XPM / SFZ / SF2):**
- **XPM** — single keygroup `<LFO>` → LFO1: `<Rate>` knob→Hz (`lfo_knob_to_hz`),
  `<Type>`→shape (`_xpm_lfo_shape`), `<Reset>`→Sync, `LfoPitch`→`lfo1_to_pitch`,
  `LfoCutoff`→`lfo1_to_filter` (emitted only when a routing is non-zero).
- **SFZ** — v1 `pitchlfo_*`→LFO1 / `fillfo_*`→LFO2 (sine); v2 `lfo01/02_*` with
  `_pitch`/`_cutoff` targets + `_wave` (`_sfz_lfo_wave`).
- **SF2** — triangle Mod-LFO (gens 22/5/10)→LFO1, Vib-LFO (gens 24/6)→LFO2;
  abs-cents freq→Hz (`8.176·2^(c/1200)`).

Depth→cord-amount is proportional (absolute cord-amount↔semitone/dB scaling
unverified — same caveat as keytrack); bipolar `~` sources only.

**Remaining — GIG LFO mapping (deferred):** needs a test `.gig` to validate +
the libgig 3ewa LFO1/2/3 (amp/filter/pitch) byte offsets; current `_decode_3ewa`
reads only EG1/EG2/VCF. Unipolar `+` sources (0x61/0x69) unused (no format needs
0→+ modulation yet).

---

## 16. Binary MPC `.pgm` format

**Mostly DONE (2026-06-08).** `parsers/pgm_parser.py` reads MPC500/1000/2500,
MPC2000/2000XL and MPC60 binary `.pgm` (auto-detected by magic). The only
remaining variant is **MPC3000** (`0x07 0x00`, `byte2==0x00`) — its magic
collides with the MPC60 `.PGM`, so it needs a body-level discriminator and a
test file. See the "XPM parser" item in `TODO.md`.

---

## 17. Filter envelope — reproduction gaps (strategy, 2026-06-08)

**Question (Jan):** can we fully reproduce the filter envelope, the way the amp
envelope now is?

**Current state — partial.** The 6-stage filter envelope at `PZT[14:26]` is
hardware-confirmed (`B.005-FltEnvTest.E4B`); `_build_voice()` writes it when
`filter_env_amount > 0.01` and `_parse_voice()` reads it back, so it round-trips
losslessly. It is mapped from source for **XPM only** (`xpm_parser.py` sets the
`filter_env_*` fields) and for **E4B→E4B**. Two gaps keep it from being as
complete as the amp envelope:

### Gap 0 — the filter envelope wasn't *routed* to the cutoff — FIXED (2026-06-09)

The filter-envelope shape at `PZT[14:26]` does nothing on its own: EOS reaches
the cutoff through a **modulation cord** "Filter Env → Filter Freq" — the E4XT UI
"**Cord 05**" = mod-matrix **storage slot 5** (`50 38 …` = `src=0x50`
Filter-Envelope → `dst=0x38` Filter-Frequency). On a fresh preset that cord sits
at **amount 0 %**, so a written envelope is inert. Our generated KT voices wrote
an **all-zero** mod matrix → no cord → no sweep (symptom: all `FLT_DECAY_CAL`
presets sounded identical, and every source-mapped filter envelope was silent on
hardware).

*(False start: I first wrote the depth to slot 7's `16 08 7F` cord — `mod[30]` —
because that one is non-zero in the hardware template. But Jan confirmed that
shows up as the E4XT's "Cord 07", a different routing; the real filter-env cord
is slot 5 / `mod[22]`, amount 0 by default. B.005-FltEnvTest's slot 5 is also 0,
so that bank never actually swept either — its diff only proved the PZT shape.)*

**Fix (UI-faithful encoding):** `writers/e4b_writer.py` writes the EOS default
cord table for any filter-envelope voice (KT or NT), and puts the **depth in the
Cord-05 amount byte** — `mod[22]` = `round(filter_env_amount × 127)`, signed (±,
for downward sweeps) — while the PZT envelope levels are written full-scale. So
the E4XT shows Cord 05 at the real `FilterEnvAmount %`. `e4b_parser.py` mirrors it
(reads amount from `mod[22]`, shape from PZT). Driven by every source's filter-
env-amount field: XPM `FilterEnvAmt`, SFZ `fileg_depth`, SF2 `modEnvToFilterFc`,
GIG VCF, EXS24. Verified: amounts +1.0/+0.5/+0.25/−0.5 round-trip through `mod[22]`.

**CONFIRMED on hardware (2026-06-09).** Jan set Cord 05 → 100 %; the filter
envelope sweeps (`FILT_ENV.wav`). Byte↔% scaling pinned by `B.010-CordAmountTest`
(cords set to 0/±20/…/±100 %): **`amount_byte = round(pct/100 × 127)`, signed** —
+100 %=`0x7F`, −100 %=`0x81`, 0 %=0. Cord layout `[src, dst, amount, flag]`,
amount at byte index 2; UI cord N = storage slot N (so Cord 05 = `mod[22]`).

### Gap A — rate→time calibration — CONFIRMED shares the amp curve (2026-06-09)

The filter envelope reuses the amp `_fenv_rate()` (`time_s = 0.0310·e^(0.0581·
rate)`). Measured `FLT_DECAY_CAL` on the E4XT (Cord 05 = 100 %) and analysed with
`--mode filter` (centroid sweep, two passes). The reliable low rates land on the
amp curve almost exactly:

| rate (PZT[18]) | filter sweep (avg) | amp curve |
|---:|---:|---:|
| 8  | 0.050 s | 0.049 s |
| 16 | 0.080 s | 0.079 s |
| 24 | 0.110 s | 0.125 s |

(rates 32–64 read short and noisily because the spectral-centroid metric
saturates once the cutoff drops below the harmonics — a measurement artifact, not
a curve difference.) Combined with the XPM result (filter and volume envelopes
share one exponent), this confirms the filter envelope uses the **same** curve as
the amp envelope — which the writer already does. **No code change needed.**

<details><summary>original Gap A strategy</summary>

The filter envelope reuses the amp envelope's hardware-calibrated `_fenv_rate()`
(`time_s = 0.0310 · e^(0.0581 · rate)`). EOS envelopes are structurally
identical, so the curve *probably* applies to the filter envelope too — but this
was never measured. (This is the "secondary calibration" question that was
dropped when §2 was marked resolved.)

*Strategy:* extend `tests/re_banks/gen_amp_envelope_test.py` to sweep the filter
**Decay-1 rate** `PZT[18]` (e.g. 8/16/24/32/48/64) on a sustained tone with high
resonance and full filter-envelope amount, so the cutoff sweep is clearly
audible. Measure the sweep time per rate on the E4XT and compare to the amp
curve:
- **If they match** (within the log-fit residual): document that amp and filter
  envelopes share one calibration — no code change, just a confirmation note.
- **If they differ:** fit a separate `(_FENV_RATE_A, _FENV_RATE_K)` pair and
  split `_fenv_rate()` into amp/filter variants.

Cheapest cross-check first: a single bank with the filter Decay-1 rate at, say,
24, played and timed — if the filter sweep takes ≈ the amp curve's 0.169 s, the
shared-curve hypothesis holds and a fuller sweep can confirm.

**Test bank:** `tests/re_banks/gen_filter_envelope_test.py` builds
`FLT_DECAY_CAL.E4B` + `.iso` — one bank, 6 presets sweeping `PZT[18]` =
8/16/24/32/48/64 (the amp set), each a resonant 4-pole LP with a full filter
envelope so the Decay-1 sweep is audible. Step-by-step + result table in
`docs/re_procedures/filter_envelope.md`.

</details>

### Gap B — source filter-envelope mapping (partially DONE 2026-06-08)

The shared helper `cents_to_filter_env_amount()` (in `models/common.py`) maps a
filter-EG depth in cents to `filter_env_amount` (±9600 cents ≈ full sweep).

- **XPM** — ✅ (pre-existing).
- **SFZ** — ✅ **DONE.** `sfz_parser` reads `fileg_attack/decay/sustain/release`
  (+ `fileg_depth` → amount). Verified: `fileg_depth=4800` → amount 0.5, times
  passed through exactly.
- **SF2** — ✅ **DONE.** `sf2_parser` reads the modulation-envelope generators
  (26 attackModEnv, 28 decayModEnv, 29 sustainModEnv [0.1 % units], 30
  releaseModEnv) with generator 11 `modEnvToFilterFc` as the amount. Smoke-tested
  on real SoundFonts (graceful no-op when `modEnvToFilterFc = 0`, which is the
  common case).
- **GIG** — ✅ **DONE 2026-06-08.** The previous `_parse_3prg_envelope()` looked
  for a non-existent `3ewg` chunk (so amp env was *always* default). Rewrote it
  against **libgig 4.3.0** (`gig.cpp` `DimensionRegion`): navigate
  region → `3prg` → `3ewl` → `3ewa`, decode EG1 (amp) and EG2 (filter) with
  libgig's `GIG_EXP_DECODE(x)=1.000000008813822**x` (raw int32 → seconds), plus
  VCF cutoff/resonance/type. A `3prg` holds one `3ewl` per dimension region; amp
  env from the first, filter from the first VCF-enabled one (the default region
  is usually VCF-off). Validated **byte-exact against `gigdump`** on
  `maestro_concert_grand_v2.gig` (EG2 D=0.005 S=1.0 R=2.0, VCFCutoff 111→0.87,
  type 0→LP24) and the Hammond organ corpus (VCF-off → no filter env). This also
  **fixed the long-standing default-amp-env bug**.
- **EXS24** — ✅ **DONE 2026-06-08.** The filter + its envelope live in a
  `TYPE_PARAMS` block (`0x04000101`) at `chunk+84`, which the parser now decodes
  (legacy section: u32 count, `count` 1-byte IDs, `count` signed-16 values —
  ConvertWithMoss `EXS24Parameters`). Reads `FILTER1_TOGGLE=44`,
  `FILTER1_TYPE=243`, `FILTER1_CUTOFF=30` (0-1000), `FILTER1_RESO=29` (0-1000),
  and **ENV2** = `77/78/79/80` (0-127). Conversions per ConvertWithMoss
  `EXS24Detector`: type 0/1/2/3/4/5 → LP24/LP24/LP12/LP12/HP12/BP12; **cutoff is
  LINEAR in frequency** — `cutoff_Hz = value/1000 × 20 kHz` — then placed on the
  E4B exponential cutoff scale (`_exs_cutoff_to_e4b`, fixed 2026-06-09; we
  previously used `value/1000` directly as the exponential position, which made
  every EXS filter far too dark — caught by cross-checking HumanMusic); env time
  = v/127·10 s, sustain = v/127. Validated across **361 filtered instruments** in
  `~/Samples` and the cutoff matches CWM Hz exactly (e.g. 333→6660 Hz).
  Applies only when `FILTER1_TOGGLE==1` and ENV2 has a non-trivial shape.
  (v1.1 format = 1717/1753 local files; the rare classic/`0x04000101`-less
  variants are not wired and stay envelope-less.)

The writer already emits whatever the parsers set — no writer change needed.
Verify with `--info --verbose` (shows filter cutoff/Q; chorus) and an E4B
round-trip. No hardware required for any of the four.

---

## 18. XPM (MPC) envelope value → time curve — measured & APPLIED (2026-06-09)

MPC keygroup envelope *times* are normalised **0.0–1.0** controls, not seconds.
**Measured on an MPC One** by recording `XPM_VOL_DECAY` (8 audible notes; C1 /
value 0 produced no signal — instant decay) and analysing it with
`tests/re_banks/analyze_envelope_recording.py`:

| value | decay-to-−40 dB (s) |
|------:|--------------------:|
| 0.375 | 0.031 |
| 0.500 | 0.114 |
| 0.625 | 0.331 |
| 0.750 | 1.211 |
| 0.875 | 4.014 |
| 1.000 | 14.69 |

(values ≤ 0.25 hit the recording's ~60 ms floor but the fit + the silent C1
confirm they're near-instant.) Steep exponential fit:
**`seconds ≈ 0.00079 · e^(9.78 · value)`** (~×3.4 per 0.125 step).

**Applied:** `_xpm_env_to_seconds()` in `xpm_parser.py`, used for
`VolumeAttack/Decay/Release` and `FilterAttack/Decay/Release` (sustain fields are
levels, unchanged).

**Filter envelope — CONFIRMED shares the curve (2026-06-09).** Recorded
`XPM_FLT_DECAY` and analysed with `--mode filter` (centroid sweep): the fit is
`0.00092·e^(9.80·value)` vs the volume `0.00080·e^(9.77·value)` — **identical
exponent** (the 1.18× scale is just centroid-settle vs −40 dB defining "done"
differently). So one curve covers all MPC envelope segments; no separate
filter constants needed.

<details><summary>original bug note</summary>

`xpm_parser.py` previously passed the 0–1 values through as seconds. Akai
publishes no value→time chart, so the curve had to be measured on hardware.

`tests/re_banks/gen_xpm_envelope_test.py` builds two Keygroup programs
(`XPM_VOL_DECAY`, `XPM_FLT_DECAY`) — 9 keygroups each, one per key C1…G#1,
sweeping the value 0→1 in 0.125 steps — plus a looping `XPM_Tone.wav`. Built
against the real minimal MPC-V Keygroup layout (empty `ProgramPads-v2.10`, one
`Instrument` per key, `KeyTrack` off so pitch is constant). Load on the MPC One,
time the decay/sweep per key, fit, and add `_xpm_env_to_seconds()` to the
parser. Full procedure: `docs/re_procedures/xpm_envelope.md`.

The MPC time curve is expected to be exponential in the 0–1 value; if
`VolumeDecay` and `FilterDecay` measure the same, one converter covers both.

</details>

---

## 19. Mod-cord depth scaling — absolute-unit calibration (strategy, 2026-06-10)

**LFO→Pitch MEASURED 2026-06-12; LFO→Filter + the rest still need recordings.**
Companion to the TODO item "Mod-cord depth scaling uncalibrated"; full procedure
in `docs/re_procedures/mod_cord_depth.md`.

The cord *routing* and amount encoding are RE'd (`round(depth×127)`, ±127=±100 %;
see §4.3/§15); the amount→musical-units transfer function is now measured for
LFO→Pitch and still a proportional guess for the others (`FILTER_ENV_FULL_CENTS=
9600`, 0–1 pass-through for LFO→Filter / Key→Filter / Velocity→Filter).

### Measurements

- **LFO→Pitch — DONE 2026-06-12.** `PitchDepth 25/50/75/100 %` recorded on the
  E4XT (`PitchDepth.wav`, all four presets in one take, square LFO ≈0.5 Hz),
  analysed per segment.  One-sided depth was **400 / 801 / 1190 / 1583 cents** at
  25 / 50 / 75 / 100 % — **dead-linear through the origin**, implied full-scale
  1599 / 1603 / 1587 / 1583 c → **mean 1593 c (σ=8)**, i.e. **±16 semitones**, not
  the ±1 octave assumed.  Applied: `LFO_PITCH_FULL_CENTS = 1200 → 1593`
  (`models/common.py`).  The old value made every LFO→Pitch vibrato ≈33 % too
  deep (1593/1200).
- **LFO→Filter — first take UNUSABLE; bank redesigned for a clean re-record.**
  `FltDepth.wav` (25/50/75/100 % over a 0.50 base cutoff) couldn't be measured:
  (1) the up half-cycle **rails at the 20 kHz cutoff ceiling** for every amount
  ≥50 %, so the high state is clipped, and (2) a saw's spectral peak jumps
  between the *fundamental* (filter open) and the *resonant peak* (filter closed),
  so peak/centroid/whitened-peak trackers all scattered (σ ≈ 0.8–1.1 oct).  Only
  the **25 % point was clean** (resonant peak 524↔2096 Hz = exactly 2.0 oct p-p,
  geo-mean 1048 Hz = the 0.50 base) → extrapolating by the proven-linear law gives
  a *tentative* ±4 oct one-sided (8 oct p-p) full-scale, **not committed** off one
  point.  Re-record #1 (low 55 Hz saw, `FILT_AMOUNTS = 10/20/30/40 %`, base 0.30,
  Q 0.92) did NOT rail and gave a usable regression-through-origin of **±3.74 oct
  one-sided** (full100 per amount 3.68/4.45/3.35/3.78, σ 0.40 oct) — consistent
  with the old 25 % point (±4 oct).  But σ is still ~0.4 oct because a saw only
  has energy AT its harmonics (55 Hz spacing), so the resonant-peak reading snaps
  to the nearest harmonic (~0.26 oct quantisation; low states clustered on
  220/330 Hz = 4th/6th harmonic).  **Refinement (pending re-record):** the
  FiltDepth + KeyTrk + VelTrk presets now use a **white-noise** source (`Noise`,
  `non_transpose=True`) — a continuous spectrum gives one smooth resonant bump
  with no harmonic snapping, so the peak reads the cutoff to FFT-bin precision.
  **MEASURED on the noise take 2026-06-12** (`FltDepth.wav`, amounts 10/20/30/40 %,
  full100 = 3.96/3.54/3.62/3.68, σ 0.16 oct — vs σ 0.40 for the saw):
  **100 % LFO→Filter ≈ ±3.65 oct one-sided (≈4383 cents)**.  Cross-checks
  Key→Filter (±3.65 oct + 0.713 oct/oct ⇒ key source ±1 over ~128 keys, 2.08≈2.0).
  **Reconciliation:** destination `0x38` (Filter-Freq) has a single sensitivity
  shared by LFO→Filter, Key→Filter, Velocity→Filter AND FilterEnv→Filter, so
  `FILTER_ENV_FULL_CENTS = 9600` is ~2.2× too high → reset to **≈4383** at apply
  time (filter-env depth has likewise been under-delivered in conversions).
  Apply: add `lfo_filter_depth_to_amount(oct) = oct / 3.65` (clamped ±1).
- **Key→Filter — first take exposed a transpose-rail; KeyTrk/VelTrk redesigned.**
  `Keytrack.wav` (original bank: `Saw110`, root A2, transposing across C1..C6)
  showed C5 and C6 at the **same pitch** — the saw transposed +27/+39 st above
  root hits the **E4XT maximum sample-playback-rate ceiling**, so the top notes
  rail to one pitch and the moving pitch/harmonics make the cutoff untrackable
  (resonant-peak readings were pure noise).  Fix: `KeyTrk 100` / `VelTrk 100` are
  now **`non_transpose=True`** (vpar[38]) — every key plays the SAME fixed pitch,
  so only the keytracked/velocity-tracked cutoff moves (the Key→Filter `0x08→0x38`
  and Velocity→Filter `0x0C→0x38` cords track the key/velocity number regardless
  of pitch transposition).  Play a MODERATE key range (C2..C4) so the cutoff stays
  in range.
  **MEASURED 2026-06-12** (re-recorded `Keytrack.wav`, `SawLo55` non-transpose,
  C2..C4 C-major scale): the cutoff now tracks the key as a clean straight line —
  **0.713 octave of cutoff per octave of key at 100 % keytrack** (slope 71.3 c/
  semitone, linearity r=0.9994, σ=19 c), i.e. **~0.71 : 1, not 1 : 1**.  This
  CROSS-CHECKS the LFO→Filter number: with a ±3.8 oct/100 % `0x38` sensitivity,
  0.713 oct/oct implies the Key source spans ±1.0 over ~128 keys (full-keyboard
  normalisation) — so the ±3.8 oct LFO→Filter and 0.713 Key→Filter are mutually
  consistent.  (At these 3–8 kHz cutoffs the saw's 55 Hz harmonic spacing is
  negligible, so this take did not need the noise source.)  To apply: map an
  input's desired key-tracking (oct/oct) to cord amount = desired / 0.713,
  clamped to ±1 — note a true 1 : 1 request saturates the cord (0.71 max).
- **Velocity→Filter — BUG found & fixed 2026-06-12 (wrong polarity); depth still
  pending.** First noise take (`VelTrack.wav`, vel 1/64/127 = 1/50/100 %) showed
  the resonant peak pinned at 440 Hz for ALL velocities while only the amplitude
  changed — velocity reached the voice but never opened the filter.  Cause: the
  default EOS cord uses **`Vel<`** (source `0x0C`, the SUBTRACT polarity), so vel
  127 only reaches the *base* cutoff and softer notes merely darken — the filter
  never rises above base, and our measurement floor missed the low end.  The EOS
  manual documents three source polarities (`+` add / `~` centre / `<` subtract);
  for velocity-tracking we want **`Vel+` (ADD) = `0x0A`**.  Source IDs confirmed on
  the E4XT: `0x0B` reads as `Vel~`, `0x0C` as `Vel<`, so the consecutive block is
  `[+,~,<]` = `[0x0A,0x0B,0x0C]` → `Vel+` = `0x0A`.  `e4b_writer` now sets the
  Velocity→Filter cord source to `0x0A` whenever `velocity_to_filter` is non-zero
  (`_SRC_VEL_PLUS`; parser unaffected — it reads the amount at fixed offset 18).
  **This was a real conversion bug**: every prior velocity→filter mapping wrote
  the subtract polarity, so on hardware harder notes never brightened above base.
  **DEPTH MEASURED 2026-06-12** (`VelTrack.wav`, Vel+ confirmed, 5-velocity sweep
  2/31/64/95/127 ×reps).  Two extra fixes were needed for a clean take: (a) at
  100 % amount the cutoff railed past 20 kHz, so the test preset uses **25 % amount
  over a 0.45 base** and scales ×4; (b) the default **Vel→Amp** cord made soft
  hits inaudible while loud hits clipped — the generator now **zeroes Vel→Amp**
  (`_MOD_TMPL[2]=0`) for the whole measurement bank, so velocity changes ONLY the
  cutoff.  Result: dead-linear in velocity (r=0.9999); full velocity (0→127) spans
  1.87 oct at 25 % → **≈7.6 oct at 100 %**.  This MATCHES Key→Filter (0.713 oct/oct
  × 10.6 oct keyboard = 7.56 oct) — velocity and key share the same 0→~2-unit
  source scaling.  **Unified result:** the `0x38` (Filter-Freq) destination =
  **3.65 oct per source unit at 100 % cord**, confirmed by four independent cords
  (LFO ±3.65 one-sided, FilterEnv 0→3.65 = 4383 c, Key/Vel 0→127 = ~7.6 oct).
  Apply (velocity): `velocity_to_filter = desired_full_range_cents / 9120`
  (= 7.6 oct).  **Direction is configurable, not hardcoded:** the writer always
  uses the Vel+ source (anchors vel 0 at base) and the SIGN of the cord amount
  picks the direction — `+` = harder opens the filter, `−` = harder closes it.
  Parsers preserve the input veltrack sign (SFZ `fil_veltrack`, XPM
  `VelocityToFilter`).  Only the **open** (+) direction was hardware-measured; the
  close (−) direction is the expected signed-cord behaviour but still unverified —
  a negative-veltrack preset would confirm it.

### Strategy — square-LFO two-state measurement

A **square** LFO at a known cord amount makes the destination hop between two
*steady* states; their difference = `amount/100` of full-scale. Sweeping the
amount (25/50/75/100 %) checks linearity and pins the constant. Key/Velocity
tracking use no LFO — vary the played key / velocity instead.

The whole loop is automated and stays consistent with the converter, because the
test bank is generated *through* the same writer (the square LFO and the cord
amounts come from the `lfo1_shape` / `lfo1_to_pitch` / … model fields):

```bash
python3 tests/re_banks/gen_mod_depth_test.py            # → MOD_DEPTH_CAL.E4B/.iso
# …record each preset on the E4XT (≥3 LFO cycles; KeyTrk C1..C6; VelTrk vel 1/64/127)…
python3 tests/re_banks/analyze_mod_depth.py rec.wav --mode pitch   # or --mode filter
```

`analyze_mod_depth.py` tracks per-frame pitch (FFT peak, parabolic-interpolated)
or the filter resonant peak, 1-D k-means-splits the take into its two states, and
reports low/high Hz, peak-to-peak cents/octaves and the one-sided depth. Verified
against a synthetic ±100 cent square signal (recovered 200.8 c peak-to-peak).

### Fix recipe (apply after measuring)

1. **LFO→Pitch** — set `LFO_PITCH_FULL_CENTS` to the measured one-sided cents at
   amount 100 % (the analyzer prints `cents × 100/A`).
2. **LFO→Filter-Freq** — add `lfo_filter_depth_to_amount(octaves)` in
   `models/common.py` from the cutoff octaves-per-100 %; route the SFZ/SF2/XPM
   cutoff-LFO depths through it instead of the raw 0–1 pass-through.
3. **FilterEnv→Filter** — reconcile `FILTER_ENV_FULL_CENTS` with the same
   Filter-Freq octaves-per-100 % (they share the `0x38` destination).
4. **Key→Filter / Velocity→Filter** — confirm 100 % ≈ 1:1 key tracking and fix
   the velocity full-scale; both currently pass through unverified.
5. If any response is **non-linear** in amount, fit a curve (as done for the LFO
   rate and the envelope rate↔time) rather than a single constant.

---

## 20. Regression sweep (input → E4B round-trip), 2026-06-11

Harness `/home/lentferj/temp/regression/roundtrip.py`: for each real input file
parse → `write_e4b` → `parse_e4b`, then compare the two models feature-by-feature
(zones key/vel/root, sample mapping + PCM/rate/root, amp+filter envelopes, filter
cutoff/res/env, key/vel→filter, non-transpose, chorus, LFO routing) with
tolerances for the known quantisations.  Run over real libraries in
`~/Samples` and the MPC backup `EXPANSIONS`.

**Result (56 real files, 14/format): 47 PASS, ZERO feature diffs**
(XPM 13, SFZ 7, SF2 13, **EXS 14/14**; the rest skipped on absent samples /
unusual dialects, plus one intended SF2 reject).  **Cross-validated on a second
random sample (SEED=2026, ~56 different files): 49 PASS, again zero diffs** — so
across ~96 real files the input→E4B round-trip loses no modelled feature.  Every file that parsed with samples
round-trips through E4B with all implemented features intact — small patches and
big multisamples alike (322-zone SF2, 219-zone/125 MB XPM, 143 MB EXS).  Two
robustness fixes were made when real files exposed gaps:

- **SF2 missing `pdta`** — `parse_sf2` raised a bare `KeyError` on a non-standard
  SFX bank; now a clear `ValueError("missing 'pdta' LIST chunk")` (and `sdta` is
  optional).
- **EXS24 + SFZ sample resolution** — commercial packs often keep audio in a
  sibling folder several levels from the patch (e.g. Samples-From-Mars
  `.../Pack/WAV/<instr>/` while the `.exs` is `.../Pack/Logic EXS/<bank>/<cat>/`;
  or Loopmasters `.../Pack/XS_SINGLE_SOUNDS/XS_DRUM_HITS/`).  Added a **lazy
  ancestor audio-folder index** (built only on the first miss, file-capped):
  scans subdirs whose name contains an audio keyword (`wav/audio/sample/sound/
  loop/hit/drum/kit/…`) under up to 5 ancestors and resolves by basename.
- **EXS24 sample-name variant** — smaller v1.1 sample chunks (some drum kits)
  have no "clean path" at +420; the filename is the display name at +20.  Parser
  now prefers +420 only when the chunk is large enough, else falls back to +20.
  Together these took EXS from 3/14 → **14/14** on the sample.

**Remaining non-bugs:** some SFZ skip because the samples are genuinely absent or
the patch is an unusual dialect (e.g. `#KOTO.sfz` has no `sample=` opcodes and
uses `.flac` — `load_wav` is WAV only, via Python's `wave` module).  These are
coverage gaps, not E4B round-trip failures.

---

## Open questions for Jan

*(These all need your direct input — compile answers for the next session.)*

1. **TAL filtermode** — *RESOLVED 2026-06-08*.  See §12.  No further action needed.

2. **vpar[42]** — *RESOLVED 2026-06-08*. It is per-voice **Chorus Amount**
   (0–100 % → 0–127); confirmed on the E4XT and wired into the model/writer/
   parser. See §13. No further input needed.

3. **Ping-pong loop** — *RESOLVED 2026-06-08*.  EOS 4.0 manual confirms loop is
   a sample-level On/Off (forward only); no ping-pong mode exists.  See §3.

4. **EXS24 PPC** — *RESOLVED 2026-06-08 (won't fix)*.  The BE branch was
   unreachable dead code and has been removed; see §14.  No input needed.

5. **EXS24 GROUP_V11 group byte** — *RESOLVED 2026-06-08*.  Ran the diagnostic
   on Oscar / StereoTracks / ExitSummer directly: `ks+11` is NOT a file-order
   index (values are 100/156); distinct values map to groups when sorted
   ascending.  Fix applied and verified corpus-wide; see §7.  No input needed.

6. **Amp envelope test banks**: Once Jan has time at the E4XT, run the test
   banks from `tests/re_banks/gen_amp_envelope_test.py` and record the results
   table as described in `docs/re_procedures/amp_envelope.md`.

7. **Mod-cord depth calibration**: record `MOD_DEPTH_CAL` (from
   `tests/re_banks/gen_mod_depth_test.py`) on the E4XT and run
   `analyze_mod_depth.py` per the procedure in §19 /
   `docs/re_procedures/mod_cord_depth.md`. Yields the real cents/octaves per
   cord-% so LFO→Pitch/Filter, FilterEnv, Key/Velocity→Filter stop being guesses.

---

## XPM TuneCoarse / TuneFine dropped — fix strategy

### Root cause

`xpm_parser` reads neither `TuneCoarse` nor `TuneFine`; `e4b_writer` writes no
tuning. The model fields exist (`ZoneMapping.fine_tune` cents,
`VoiceLayer.fine_tune` cents, `VoiceLayer.transpose` semitones) but are inert.

MPC stores tuning at **two levels**, both of which must be summed:
- Instrument-level `<TuneCoarse>` (semitones) + `<TuneFine>` (cents) — applies to
  the whole keygroup (this is what `Lazloz Split` uses for its detuned stack).
- Layer-level `<TuneCoarse>`/`<TuneFine>` — per sample layer.

### Parser fix (straightforward)

In the zone/voice builder, read instrument-level tune once and layer-level tune
per layer, sum them:

```python
inst_ct = int(_get_text(instrument, 'TuneCoarse', '0'))
inst_ft = int(_get_text(instrument, 'TuneFine',  '0'))
lay_ct  = int(_get_text(layer, 'TuneCoarse', '0'))
lay_ft  = int(_get_text(layer, 'TuneFine',  '0'))
transpose = inst_ct + lay_ct          # semitones
fine      = inst_ft + lay_ft          # cents
```

Store `transpose` on the voice (or fold into `root_key` for tracking voices:
`root_key -= transpose`) and `fine` on the zone/voice `fine_tune`. Note the
detuned-stack use needs the layers in **separate voices** (see the SFZ-stacking
and RootNote items) — otherwise a single voice can't carry two different tunings
for the same key.

### Writer side (needs RE)

`_zone_entry()` (22-byte secondary zone) does not encode fine tune or transpose;
the byte offsets are unknown — **same gap as the GIG `fine_tune` / per-zone
volume items**. RE procedure (mirror those): on the E4XT make two identical
presets differing only by voice transpose (+12 st) and by fine tune (+50 c),
save, binary-diff the voice param block (`vpar`) and the 22-byte zone entries.
Likely a voice-level coarse (semitone) byte and a fine (cents) byte in `vpar`,
since MPC tuning here is per-instrument (= per-voice), not per-zone. Coarse
transpose for *tracking* voices can be applied immediately via `root_key`
without RE; only fine tune (and transpose on non-transpose voices) needs the
byte.

### Validation

`Lazloz Split`: Inst 2 voice +12 st / +15 c, Inst 4 +25 c — confirm the stacked
voices beat against the untuned ones (the chorused "split" sound). Re-check the
three demo presets and fix the `feature_coverage.ods` tuning labels.

**Regression case — two presets must stop sounding identical (Jan 2026-06-12):**
`Inst-Pad-JR Lazloz Split` (P003) and `Inst-Bass-JR Jupiter Rising Spt` (P004)
currently both collapse to the *same* structure (`1 voice, 12 zones, all
key0-127/vel0-127/root60`) — verified identical. Their source samples sound
alike (both JR "UniPanBass" unison pads), so once the RootNote-collapse + the
dropped split/tuning are gone they're indistinguishable. After the RootNote +
TuneCoarse/TuneFine fixes they should differ (P003 has an extra +12 st / +15 c
detuned octave layer that P004 lacks). Good end-to-end check that the
split/stack/tune chain is restored.

---

## XPM long-common-prefix name truncation — fix strategy

### Root cause

`_safe_name` truncates to 16 chars head-first. Sample sets sharing a long prefix
(`Inst-Pad-LazSp-UniPanBass_C1_A …`) collapse to the same 16 chars; the dedup
counter then yields `…-1/-2/-3`, losing the meaningful `C1_A`/`C2_B` tail.

### Fix

Reuse the EXS24 approach (RESOLUTION_NOTES §CR-18): keep the **full** name as the
cache key / model name, and apply the 16-char E4B limit only at write time with a
**tail-preserving** scheme — e.g. keep the last 15 chars (the
note/round-robin/layer suffix is the distinguishing part), or `prefix[:8] +
hash(full)[:8]`. Apply in `_safe_name` (or wherever names are truncated for the
E4B sample chunk) so distinct source samples never share a written name.
Validate on `Lazloz Split`: 12 samples should keep distinct, recognisable names
(`…C1_A`, `…C1_B`, … not `…-1`, `…-2`).

---

## XPM `KeygroupWheelToLfo` (mod-wheel → LFO depth) — fix strategy

### Root cause

`<KeygroupWheelToLfo>` (program-level, 0–1) is the MPC "WHEEL→LFO" depth: the mod
wheel scales the LFO's modulation amount. At 100% the LFO is fully wheel-gated
(no modulation at rest). `xpm_parser` never reads it; `e4b_writer` writes
LFO→Pitch/Filter/Vol cords at their full static amount → the E4XT applies the LFO
continuously at full depth (Jan: "too much LFO→Pitch" on `Bass-MS20 Acoustik`,
which has `KeygroupWheelToLfo=1.0`).

### EOS mechanism — cord-amount modulation

EOS PatchCords can modulate the **amount of another cord** (the EOS manual's
"a cord can control another cord's amount"). The standard mod-wheel-vibrato patch
is two cascaded cords:

```
Cord A:  LFO1~ → Pitch          amount = programmed depth (e.g. LfoPitch)
Cord B:  ModWheel → [Cord A Amount]   amount = KeygroupWheelToLfo (≈100%)
```

With Cord A's *initial* amount at 0 and Cord B scaling it by the wheel, the LFO
depth follows the wheel — matching the MPC. Same pattern for LFO→Filter and
LFO→Vol cords (one ModWheel→CordAmount cord per gated routing, or share if EOS
allows summing).

### What must be reverse-engineered

We already have LFO sources (`0x60`/`0x68`), dests Pitch `0x30` / Filter `0x38` /
Q `0x39`. **Unknown, needed for this fix:**

1. **ModWheel source id.** EOS controller sources (Pitch Wheel, Mod Wheel,
   Pressure, MIDI A–P…). RE: on the E4XT build a preset with ModWheel→Pitch at a
   known amount, save, read the cord `[src, 0x30, amt, 0]` → `src` is ModWheel.
2. **"PatchCord N Amount" destination ids.** EOS exposes each cord's amount as a
   destination (commonly `Cord 1 Amt …`). RE: build LFO1→Pitch (cord A) + a
   second cord whose dest is "Cord A Amount" at a known amount; save; the second
   cord's `dst` byte is the Cord-A-amount destination id. Sweep which cord slot
   maps to which amount-dest id (likely a contiguous block).

RE test-bank generator: add `tests/re_banks/gen_wheel_to_lfo_test.py` emitting a
few presets (ModWheel→Pitch; LFO→Pitch + ModWheel→CordAmt) for Jan to save+read,
mirroring `gen_mod_depth_test.py`.

### Fix once ids are known

- `xpm_parser`: read `KeygroupWheelToLfo` (program-level) into the model (e.g.
  `Preset.wheel_to_lfo` or per-voice `VoiceLayer.wheel_to_lfo`).
- `e4b_writer`: when `wheel_to_lfo > 0` and any `lfo*_to_*` routing is set, write
  the LFO→dest cord with its depth **and** a `ModWheel → [that cord's amount]`
  cord scaled by `wheel_to_lfo`. When `wheel_to_lfo == 0`, keep today's static
  behaviour.
- `e4b_parser`: mirror — recognise a ModWheel→CordAmount cord and recover
  `wheel_to_lfo`.

### No-RE interim approximation

Until the ids are RE'd, the cheapest improvement is to **scale the static LFO
depths by `(1 − KeygroupWheelToLfo)`** so a 100%-wheel-gated LFO is written at
~0 depth (silent at rest, like the MPC's default wheel-down state) instead of
full. This loses the wheel-up expressivity but stops the "too much LFO" at rest.
Gate behind a flag/comment so it's obviously a stopgap. **Decide with Jan** —
some may prefer keeping audible LFO over silence.

---

## XPM `RootNote=0` non-transpose mis-detection — fix strategy

### Root cause

`parsers/xpm_parser.py:331`:

```python
raw_root = int(_get_text(layer, 'RootNote', '60'))
smp_mode = (raw_root == 0)                    # ← WRONG signal
root = max(0, raw_root - 1) if not smp_mode else 60
```

`RootNote=0` is the MPC "root unset" sentinel, not "no key tracking". Treating it
as SMP routes pitched multisample zones through the SMP path (key 0-127, root 60),
detuning them badly.

### Authoritative semantics (ConvertWithMoss)

- **Read** `MPCModernDetector.java:481-487`:
  `keyRoot = RootNote - 1` (when present); `keyTracking` is overridden by the
  per-layer `KeyTrack` field **only when `IgnoreBaseNote` is True** — otherwise
  the zone key-tracks (default 1.0).
- **Write** `MPCKeygroupCreator.java:223`:
  `RootNote = limitToDefault(keyRoot, limitToDefault(keyLow, 0)) + 1` — i.e. the
  root falls back to the keygroup **LowNote** when unset. `IgnoreBaseNote` is
  written as `keyTracking == 0 ? "True" : "False"` (`:344`).

So: **non-transpose ⇔ `IgnoreBaseNote=True`** (with `KeyTrack=False`); root, when
`RootNote=0`, **= keygroup LowNote**.

### Corpus evidence (4 files)

| File | combo | correct handling |
|---|---|---|
| MS20 2c (broken) | `RootNote=0, IgnoreBase=False, KeyTrack=True, kg36-38` | **track, root=36 (LowNote)** |
| F9 Disco Rhds | `RootNote=0, IgnoreBase=True, KeyTrack=False, kg0-127` | non-transpose (as now) |
| F9 Disco Rhds | `RootNote=37, IgnoreBase=False, kg0-39` | track, root=36 |
| DX7 Advent | `RootNote=0, IgnoreBase=True, kg0-127` (Chain-Noise) | non-transpose |
| DX7 Advent | `RootNote=0, IgnoreBase=False, kg0-127` (Chain-Synth Osc) | **AMBIGUOUS — see below** |
| DX7 Advent | `RootNote=102, IgnoreBase=False, kg101-105` | track, root=101 |
| JR Short Pad | `RootNote=0, IgnoreBase=False, KeyTrack=False, kg0-47…` | track, root=LowNote |

### Design decision — the full-range ambiguous case  → **DECIDED: Option B (Jan, 2026-06-12)**

`RootNote=0 + IgnoreBaseNote=False + kg0-127` (DX7 "Chain-Synth Oscillators"):
strict CWM semantics say *track* (IgnoreBase=False), but root would fall back to
LowNote=0 → tracked from C-1 across the whole keyboard (wild pitch). Today these
are treated as non-transpose (root 60), which probably sounds closer for a
full-range oscillator/texture layer. Options:

- **(A) Strict CWM:** non-transpose ⇔ `IgnoreBaseNote=True`. Simplest, matches
  the reference, but risks regressing full-range root-0 texture layers.
- **(B) CWM + full-range guard (recommended):** non-transpose when
  `IgnoreBaseNote=True` **OR** (`RootNote=0` AND keygroup spans the whole
  range 0-127). Bounded keygroups with `RootNote=0` always track (root=LowNote);
  full-range root-0 layers stay fixed-pitch. Fixes all 168 mistuned multisample
  files without touching the working full-range texture layers.

### Fix (option B)

```python
ignore_base = _get_text(instrument, 'IgnoreBaseNote', 'False').lower() == 'true'
raw_root    = int(_get_text(layer, 'RootNote', '0'))
full_range  = (lo_key == 0 and hi_key == 127)

non_transpose = ignore_base or (raw_root == 0 and full_range)
if non_transpose:
    root = 60                      # fixed pitch; existing SMP/NT voice path
else:
    root = (raw_root - 1) if raw_root > 0 else lo_key   # ← LowNote fallback
    # normal key-tracking zone over [lo_key, hi_key]
```

Keep the SMP accumulation path only for `non_transpose` zones; tracking zones go
through the normal `vel_to_voice` zone builder with their real keygroup key range.
Re-run the MS20 patch: expect 1 voice with 15 zones at kg36-38…kg78-84, roots
36/39/42/… (not 15 zones at 0-127 root 60).

### Validation

- `Bass-MS20-Patch 2c.xpm` → tuned chromatically, no aliasing.
- F9 Disco Rhds / DX7 Advent → non-transpose layers unchanged (diff the voice
  `non_transpose` flags before/after).
- Spot-check a few of the 168 flagged files by ear on hardware.

---

## SFZ keyswitch articulations — fix strategy  → **DECIDED: one preset per articulation, drop KS keys (Jan 2026-06-12)**

### Root cause

`sfz_parser.py:256-272` discards every group whose `sw_last != sw_default`,
keeping only the default articulation. Keyswitch instruments lose all but one
style.

### Agreed mapping

The E4XT has no keyswitch. Emit **one E4B preset per articulation** and **drop
the keyswitch keys** (CWM-style):

- Group SFZ `<group>`s by their `sw_last` value (each distinct `sw_last` = one
  articulation; some articulations span several groups — e.g. 3× D#2 Accent).
- For each articulation, build a preset named `<basename>-<sw_label or note>`
  (sanitise the label: "F2 Pizzicato" → "Pizzicato"). Within a preset, apply the
  normal region→voice logic (incl. the overlapping-stacking fix below for its own
  groups).
- Do **not** emit zones for the keyswitch key range itself (regions are the
  playable range; the `sw_lokey..sw_hikey` band is control-only — already not a
  region, so nothing to drop there, but ensure no preset maps the KS keys).
- A bank built from one SFZ then holds N presets (Sustain, Tremolo, Pizzicato…),
  selectable on the E4XT.

### Implementation sketch

- In `parse_sfz`, accumulate regions into a dict keyed by `sw_last` (default key
  for groups without `sw_last`). Replace the single-preset build with a loop that
  emits one `Preset` per key.
- Preserve the existing round-robin / xfade / CC1 warnings (fire once per file).
- Preset naming: dedupe + 16-char limit at write; keep the articulation label.
- `convert.py` already handles multi-preset banks, so no caller change.

### Validation

`1st-violin-SOLO-KS-C2.sfz` → ~6 presets (Sustain, Tremolo, Normal, Accent,
Staccato, Pizzicato), each playable G3+, no keyswitch keys. Pizzicato preset must
sound like pizz, not sustain.

---

## SFZ overlapping-region stacking — fix strategy

### Root cause

`parsers/sfz_parser.py` creates one `VoiceLayer` (`:232`) and appends every
region to it (`:387`). An E4B **voice** plays only one matching zone per note,
so overlapping samples (multiple instruments / dynamic layers on the same
key+vel) don't stack. Verified on `all-brass-SEC-accent.sfz`: 14 `<group>`s,
155 regions, up to 14 overlapping at one key → converts to `1 voice, 155 zones`
→ thin. ConvertWithMoss instead emits MPC keygroups with up to **4 simultaneous
Layers** (54 keygroups, 85 samples, 26 of them 4-layer); the E4XT analogue is
parallel **voices**.

### Design decision (resolve before coding)

Two ways to split the single voice into stacking voices:

- **(A) One voice per `<group>`.** Each SFZ `<group>` is already a self-contained
  keymap (confirmed: brass groups 1–14 each span the keyboard at vel 0–127, one
  per instrument/dynamic layer). Map each group → one voice. Most faithful to
  per-group params (envelope/filter/pan differ per instrument), and mirrors how
  the SFZ author organised it. Risk: SFZs that use `<group>` for *velocity*
  layers or round-robin would over-split — but those are already handled
  upstream (vel grouping / `seq_position`), and a group whose regions don't
  overlap any other group's key+vel range collapses back to shared coverage
  anyway. Gives 14 voices here.
- **(B) Greedy overlap-lane allocation.** Ignore groups; for each zone place it
  in the first voice whose existing zones don't overlap its key+vel, else open a
  new voice. Format-agnostic, guarantees exactly `max_overlap_depth` voices, but
  can mix zones from different instruments into one voice (they'd share that
  voice's envelope/filter — fine for VPO, lossy in general).

**Recommendation: (A)**, falling back to per-region lanes only inside a group if
a single group self-overlaps. Keeps per-instrument voice params intact.

### Voice-count cap

The E4XT allows many voices per preset (far more than the MPC's 4-layer cap), so
we need not down-select like CWM. But a preset stacking 14 sustained looped
voices per note is heavy on polyphony; consider an optional cap (e.g. warn + keep
the loudest N by `volume`) if real banks blow the voice budget. Not needed for
correctness — decide with Jan.

### Implementation sketch

- Replace the single `voice = VoiceLayer()` with a `voices: list[VoiceLayer]`
  keyed by group identity (a counter incremented on each `<group>` whose key+vel
  span overlaps an already-open voice).
- Move the per-voice param assignment (envelope/filter/LFO, currently "first
  region that declares one") to per-group, reading the group defaults.
- Append each voice with zones to `preset.voices`.
- Re-validate `multi_vel_layers` / `multi_key_zones` feature counting and the
  existing xfade/round-robin/keyswitch warnings still fire once per file.

---

## XPM slice-based playback — fix strategy

### Root cause

`xpm_parser.py` lines 320–371: when processing a `<Layer>`, the parser reads
`SampleName`, `RootNote`, `VelStart`/`VelEnd`, and per-layer tuning, but
silently ignores `<SliceStart>`, `<SliceEnd>`, and `<SliceLoop>`. The full WAV
is loaded unchanged.

### Field semantics (verified against MPC 3.7 manual + measured WAV frame counts)

All slice offsets are in **sample frames** (confirmed: `SliceEnd` equals the
referenced WAV's frame count in 6 of 7 `SloBand Sweeper` slices; the 7th,
`C1_B`, is `2454` against a `2666`-frame WAV — a genuine pad-end trim).

| Field | MPC UI name | Meaning |
|---|---|---|
| `SliceStart` | Pad Start | first frame played |
| `SliceEnd` | Pad End / "end of sample" | last frame of the play + loop region |
| `SliceLoopStart` | **Loop** (Loop Position) | frame the loop repeats *from* |
| `SliceLoop` | **Pad Loop** mode | **enum**: 0=Off, 1=Forward, 2=Reverse, 3=Alternating (ping-pong) — numeric 0/1 confirmed in data; 2/3 inferred from the manual's mode list, not yet seen |
| `SliceLoopCrossFadeLength` | loop crossfade | frames; `-1` = none |
| `Direction` | reverse playback | 0 = forward (all 7 slices are 0) |

Manual (Pad Loop, Forward): *"hold the pad to cause that sample to repeat from
the **Loop Position** to the **end of the sample**."* So the loop region is
`[SliceLoopStart, SliceEnd]`, **not** the whole slice. Pad Loop only sustains
when the pad's **Sample Play = Note On** (One Shot ignores it) and **Slice =
Pad** — both true here, which is why the intent is a held, sustaining drone.

**Degenerate loop points (must handle):** 4 of 7 `SloBand` slices have
`SliceLoopStart == SliceEnd` (a zero-length loop: C1_A `[1325,1325]`, C2_A
`[664,664]`, C2_B `[669,669]`, C4_B `[336,336]`). C3_A has a real sub-loop
`[468,672]`; C1_B loops the whole pad region `[1120,2454]`. The MPC's behaviour
when Loop Position == Pad End is **not yet confirmed** — most likely it falls
back to looping the entire pad region `[SliceStart, SliceEnd]`. **Verify by ear
/ on hardware before trusting either interpretation.**

### Fix

**1. Slice extraction** — after `load_wav()`, trim `SampleData.data` to the pad
range `[SliceStart, SliceEnd]`:

```python
slice_start = int(_get_text(layer, 'SliceStart', '0'))
slice_end   = int(_get_text(layer, 'SliceEnd',   '0'))
bytes_per_frame = sd.channels * (sd.bit_depth // 8)
if slice_end > slice_start:
    sd.data = sd.data[slice_start * bytes_per_frame : slice_end * bytes_per_frame]
```

**2. Slice loop** — `SliceLoop` is the Pad Loop **enum** (Jan confirmed mode is
"Pad Loop / Forward" for `SloBand`). Map it; loop region is
`[SliceLoopStart, SliceEnd]`, both rebased to the trimmed slice. Clamp the
degenerate `loop_start >= loop_end` case to the whole trimmed slice (TENTATIVE —
see "Degenerate loop points" above):

```python
mode = int(_get_text(layer, 'SliceLoop', '0'))
if mode:  # 0 = Off
    loop_pos = int(_get_text(layer, 'SliceLoopStart', '0')) - slice_start
    n_frames = len(sd.data) // bytes_per_frame
    sd.loop_start = loop_pos if 0 <= loop_pos < n_frames - 1 else 0
    sd.loop_end   = n_frames - 1
    sd.loop_type  = {1: LoopType.FORWARD,
                     2: LoopType.REVERSE,       # if model/E4B supports it
                     3: LoopType.PINGPONG}.get(mode, LoopType.FORWARD)
```

**3. Sample cache key** — two instruments may reference the same `SampleName`
with different slice ranges. Change the cache key from `sample_name` to
`(sample_name, slice_start, slice_end)` so each unique slice becomes a separate
`SampleData` entry (with its own truncated name suffix to keep 16-char uniqueness).

**4. SMP-mode tuning** — in the SMP accumulation dict, store the
instrument-level `TuneCoarse`/`TuneFine` alongside `vel_lo`/`vel_hi`, and
propagate them into the `ZoneMapping` when building the final SMP voice (lines
422–433). Group by `(vel_lo, vel_hi, tune_coarse, tune_fine)` rather than vel
range alone.

**Caveat — the 122× unison stack:** `SloBand Sweeper` layers 122 identical
`C1_A` instruments (same slice, `TuneCoarse=12`, tiny per-voice `LfoPitch`/
`LfoPan`), which on the MPC produces a thick phasing drone. The E4XT caps voices
per preset far below 122, so even with correct slices the converted preset can
only approximate the massed-unison character. Worth a note to Jan when fixing.


## Fixed (un-gated) LFO→Filter on MS-20 patches — pending aural check

`Bass-MS20-Patch 2c` (FEATUREDEMO_02 P003) plays LFO1→Filter at a fixed +42
(33%).  **Verified faithful:** source `KeygroupWheelToLfo=0.0`, `LfoCutoff=0.33`,
`LfoPitch=0`.  No code change unless Jan's by-ears check picks one of:

**Path B — depth calibration.**  Today `lfo1_to_filter` (= XPM `LfoCutoff`,
0–1) is written linearly: `cord_amount_to_byte(depth)` = `round(depth*127)`
(`models/common.py:130`).  There is no measured `LFO_FILTER_FULL_*` constant
analogous to `LFO_PITCH_FULL_CENTS=1593` (`models/common.py:156`).  If the
filter wobble is too strong/weak, add one: measure the E4XT filter-LFO sweep in
cents/Hz at cord amount 127 vs the MPC at `LfoCutoff=1.0`, then scale
`lfo1_to_filter` by `measured_mpc_depth / measured_e4xt_full` before the write
(mirror §19's mod-cord absolute-unit calibration).  Apply in `xpm_parser.py:396`
(`lfo1_to_filter=lfo_cutoff`) so it's source-unit-correct.

**Path C — always wheel-gate (deviation from source).**  Force gating regardless
of `KeygroupWheelToLfo`: in `xpm_parser.py` clamp `wheel_to_lfo = max(wheel_to_lfo,
DEFAULT_WHEEL_GATE)` when any `lfo1_to_*` is active.  e4b_writer already splits
every LFO cord (static + ModWheel→CordN-Amt) for `Kw>0`, so no writer change.
This makes every LFO preset wheel-dimmable but no longer matches the MPC default.

**Path A (likely) — leave as-is.**  Fixed filter LFO is authentic (MS-20 MG→VCF
is always-on; the MPC author set `KeygroupWheelToLfo=0`).  Then just close the
TODO.  (Optional cosmetic: suppress the template-default `ModWheel→C02Amt @16`
cord when `lfo1_to_pitch==0` — but that edits the hardware-extracted `_MOD_TMPL`
byte output, so only with Jan's sign-off.)

---

## §KRZ-PROG — K2000 program parameters (envelopes / filter / LFOs) — fix strategy

**Goal:** extend `writers/krz_writer.py` to carry amp envelope, filter (type +
cutoff + resonance), filter envelope, and LFOs from the `VoiceLayer` model into
the KRZ program object — i.e. give the K2000 path the synth fidelity the E4XT
path already has.

**Where we are:** sample mapping + tuning convert and sound (HW-confirmed). The
program is written as a proven-but-flat minimal layer (`PGM LYR ENC ENV CAL
HOB×4`, amp env = sustain-only). The full plan, corpus analysis, byte-level
hypotheses, and per-parameter checklists are in
`docs/re_procedures/krz_program_re.md`. Do **not** duplicate them here; this
section is the decision log + open questions.

**Decided design target:** Algorithm 1, DSP slot = `4POLE LOPASS W/SEP` (24 dB/oct
resonant lowpass). It maps 1:1 onto every source format (cutoff, resonance=SEP,
filter-env→freq, amp ADSR, LFO→pitch/filter). We will NOT implement all 31
algorithms — one good subtractive algorithm covers the conversion need.

**RE method — recommended order:**
1. Amp envelope (ENV 0x21) — `KRZ_ENVLOC` + `KRZ_ENVSW*` banks, no MIDI needed.
   Calibrate `_krz_env_rate(seconds)` mirroring the E4XT `_fenv_rate`.
2. Algorithm byte + filter cutoff/resonance — needs a filter in the signal path,
   so either scripted-SysEx poke (strategy A) or create-on-HW + diff (strategy C).
3. LFO + filter envelope routing.

**Implementation plan once bytes are known:**
- Add `_make_layer_segments` params: `algorithm`, `amp_env`, `filter_cutoff`,
  `filter_reson`, `filter_env`, `lfo*`. Emit the ENC (algorithm + routing), the
  filled ENV, the filter HOB page, and an LFO segment when the voice has one.
- Reuse the existing `VoiceLayer` envelope/filter/LFO fields (already populated
  by every parser for the E4XT path) — no parser changes needed.
- Keep the writer's "reduced layer is OK" property: only emit modulation
  segments (LFO/ASR/FUN) when the source actually uses them.

**DONE 2026-06-17 — LFO shape complete map (live K2000R SysEx probe):**
All 26 LFO shapes probed by navigating EditProg→LFO page (EDIT→SoftF×3→SoftB,
CursorRight×3 to Shape), then wheeling through all values and reading LCD:

| Byte | Display | Shape |
|------|---------|-------|
| 0 | Sine | Sine |
| 1 | +Sine | Unipolar Sine |
| 2 | Square | Square |
| 3 | +Squar | Unipolar Square |
| 4 | Triang | Triangle |
| 5 | +Trian | Unipolar Triangle |
| 6 | Rise S | Rising Sawtooth |
| 7 | +Rise | Unipolar Rising Saw |
| 8 | Fall S | Falling Sawtooth |
| 9 | +Fall | Unipolar Falling Saw |
| 10–25 | N Step / +N Step | Step patterns: 3/4/5/6/7/8/10/12 Step (± unipolar) |

**Critical correction:** prior RE notes said "Triangle=2" — **WRONG**. Byte 2 is
Square. Triangle is byte 4. `_LFO_SHAPE` in `krz_writer.py` fixed (and fallback
changed from 2 to 0=Sine). Tests in `tests/test_krz_writer.py` pin all values.

K2000 has **no random/S&H LFO** — `'random'` and `'hemiquaver'` map to byte 20
(8 Step), the closest deterministic stepped approximation.

**OPEN QUESTIONS FOR JAN** (also in the .md §8):
1. Is the K2000R on a MIDI link to the PC? That unlocks the *scripted-SysEx* RE
   loop (`tests/re_banks/krz_sysex_probe.py`, codecs unit-tested) — poke an object
   byte, read the LCD back via `PARAMVALUE`. Massively faster than by-ear.
   **UPDATE 2026-06-17: K2000R MIDI link confirmed and operational.**
2. Capture path for create-on-HW saves — Gotek floppy (as for the sample work) or
   SCSI/SmartMedia?
3. Confirm priority: amp env → filter → LFO.


## §KRZ velocity-split layers — IMPLEMENTED 2026-06-24

**Status:** DONE. `writers/krz_writer._split_voice_by_velocity()` groups a
voice's zones by their distinct `(lo_vel, hi_vel)` band and returns one shallow
VoiceLayer copy per band; `write_krz` expands `preset.voices` through it before
the layer-cap/keymap-assignment loop, so each band gets its own keymap + layer
with its vel window (single-band voices pass through unchanged → no regression).
Verified: AlphaPad #200 → 3 layers, vel 0-64/65-96/97-127, full-keyboard each;
`tests/test_krz_writer.py` 8/8 pass. Pending K2000R HW A/B. Strategy below kept
for the record.

**TODO:** "KRZ: clean velocity-SPLIT layers collapse to ONE layer". AlphaPad
(#200) has 3 mutually-exclusive velocity bands (0-64/65-96/97-127); the KRZ
gets 1 layer because (1) `xpm_parser._overlaps()` merges non-overlapping vel
bands into one voice, and (2) `krz_writer._build_keymap_entries()` keys the
keymap by note only, so co-keyed vel-band zones overwrite each other (top
band wins → too bright). The E4B path is correct and must stay untouched.

**Decision: fix in the KRZ writer, not the parser.** The E4B model (one voice,
per-zone vel ranges) is the right faithful representation and the E4XT honours
it. Re-splitting in the XPM parser would regress the E4B side and the lane
budget. The K2000 simply can't express per-key velocity zones inside one
keymap — it needs one layer per velocity band — so the split belongs at KRZ
write time. The writer ALREADY accepts per-layer `lo_vel`/`hi_vel`
(`_build_layer(... lo_vel, hi_vel)`, `_voice_key_vel_range`); we just never
feed it more than one band per voice.

**Patch (writers/krz_writer.py), in the per-voice program-build loop:** before
building a layer+keymap for a voice, group that voice's zones by their distinct
`(lo_vel, hi_vel)` band and emit one (keymap, layer) pair per band, passing the
band's vel range to `_build_layer`. Sketch:

```python
from collections import OrderedDict
def _vel_bands(voice):
    bands = OrderedDict()
    for z in voice.zones:
        bands.setdefault((z.lo_vel, z.hi_vel), []).append(z)
    return bands   # {(lo,hi): [zones]}, file order preserved
```

Then where the code currently does "one keymap + one layer per voice", iterate
`_vel_bands(voice)`: build `_build_keymap_entries` from that band's zone subset
(make the keymap builder take an explicit `zones` list, or a shim VoiceLayer
carrying only the band's zones), and `_build_layer(..., lo_vel=lo, hi_vel=hi)`.
A single-band voice (the common case) yields exactly today's output — zero
regression. Respect `_MAX_KRZ_LAYERS = 32`: AlphaPad = 3 bands × 1 key-split
voice = 3 layers, fine; for drum kits already at many layers, cap and warn.

**Verify:** rebuild K2KFEATDEMO; `krz_reader.walk_program` should report
**3 LYR** for `Alpha Pad`, each LYR segment byte[5]/[6] = the band's lo/hi vel
(0/64, 65/96, 97/127). Then HW A/B on the K2000R — soft notes should now play
the darker low-velocity layer.

This is the KRZ twin of §10 (SMP "one voice per distinct vel range"); cross-
check that fix's shape when implementing.


## §XPM release-time recalibration — fix strategy (2026-06-24)

**TODO:** "XPM→KRZ: VolumeRelease time ~2.5× too short". AlphaPad
`<VolumeRelease>0.763780` → current `_xpm_env_to_seconds` (`0.00079·e^(9.78·v)`,
RE'd in §18 from a *decay*-to-silence sweep) → 1.39 s; Jan matched the MPC One
original by ear at K2000 ~3.48 s (×2.51 short; would need v≈0.858).

**Do NOT hand-tune the constants off one point.** One sample can't distinguish
a constant release×factor from a wrong curve shape, and §18's curve is HW-
verified for *decay* — blindly scaling it would risk regressing decay.

**RE procedure (mirror §18 / `docs/re_procedures/xpm_envelope.md`):** on the
MPC One, make a single full-level looped tone, set Decay/Sustain to hold, sweep
**`<VolumeRelease>`** across ≥4 values (0.25, 0.50, 0.764, 1.0), release the
key and measure time from key-off to silence (−60 dB) for each. Then:
- if the points sit on `0.00079·e^(9.78·v)` scaled by a constant → add a single
  `_XPM_REL_FACTOR` applied only to release (and re-check whether filter-release
  needs the same);
- if the shape differs → fit a separate `_xpm_release_to_seconds()` and route
  `VolumeRelease`/`FilterRelease` through it, leaving attack/decay on the §18
  curve.

Sanity anchor already in hand: (v=0.764 → ~3.48 s) implies, if it's a constant
factor, ~2.5× — but confirm with the sweep before shipping. Record the raw
measurements in `docs/re_procedures/xpm_envelope.md` alongside the decay data.

---

## §BB. Band-Boost (BB 2P/4P/6P/8P) filters → wrong target (2026-06-25)

MPC FilterType **19–22 = Band Boost** (parametric peak: full signal + a boosted
band).  Both writers send it to a **bandpass**, which removes the out-of-band signal
instead of boosting in-band → thin/hollow.  See TODO "Band-Boost (BB) filters map to
BANDPASS".  Symptom source: `K2KFEATDEMO` #204 **Bass-MS20-Patch 2c** (FilterType=19,
Cutoff=0.27, Reson=0.65).

### E4B — ready patch (no HW needed)
EOS **Swept EQ 1-oct** (`vpar[58]=0x20`) is a parametric band gain; the gain law is
already HW-RE'd (`gain_dB=(byte−64)×0.375`, `byte 64 = 0 dB`).  Band-*stop* (15–18)
already uses it with a **negative** gain; Band-*boost* is the **same filter with a
positive** gain.  In `writers/e4b_writer.py`:

1. Re-point the BB entries in `_XPM_FILTER_TYPE` from bandpass to Swept EQ:
   ```python
   19: 0x20,  # BB 2P boost → Swept EQ 1-oct (+gain)
   20: 0x20,  # BB 4P boost → Swept EQ 1-oct (+gain)
   21: 0x20,  # BB 6P boost → Swept EQ 1-oct (+gain)
   22: 0x20,  # BB 8P boost → Swept EQ 1-oct (+gain)
   ```
2. In the `if vpar[58] == _SWEPT_EQ_1OCT:` block, choose the gain *sign* from the
   source type (both BS and BB now land on 0x20):
   ```python
   res = max(0.0, min(1.0, voice.filter_resonance))
   if 19 <= voice.filter_type <= 22:      # BB band-boost → +gain
       gain_db = +(12.0 + 12.0 * res)
   else:                                   # BS band-stop → −gain (cut)
       gain_db = -(12.0 + 12.0 * res)
   vpar[61] = max(0, min(127, round(gain_db / _SWEPT_EQ_DB_PER_STEP) + 64))
   ```
   (Magnitude mirrors the existing notch depth; refine vs. the MPC BB gain law if a
   measurement is taken.)

### KRZ/K2000 — RESOLVED 2026-06-25 (PARA MID, hardware-RE'd)
BB 19–22 now map to **Algorithm 2 PARA MID** (parametric band boost), RE'd via
`tests/re_banks/gen_krz_paramid_re.py` + a PARAJLZ.KRZ disk-save diff:

| Byte | Value |
|---|---|
| `CAL[29]` (algorithm) | **2** |
| `HOB0(0x50)[0]` F1-FRQ function | **51** |
| `HOB0(0x50)[1]` center freq | signed −48…+79 = existing `_cutoff_byte` (16 Hz…25088 Hz) |
| `HOB1(0x51)[0]` F2-AMP block | **16** |
| `HOB1(0x51)[1]` gain | **dB, 1:1 signed** (0→0, +24→24, +48→48; ±48 range) |
| `HOB2(0x52)[0]` F3 | **40** (None) |

Wired in `_k2_filter_plan` (BB → `(2, 51, 16, 40)`) and `_patch_layer`
(HOB0[1]=`_cutoff_byte(cutoff)`, HOB1[1]=`+12..+24 dB` from resonance).  Verified
end-to-end on #204 Bass-MS20-Patch (FilterType=19 → ALG2/51/AMP+20 dB).  Full
procedure + capture table: `docs/re_procedures/krz_paramid.md`.  Later refinement:
measure the MPC's actual BB gain law to calibrate the dB depth (FRQ already exact).

### Single-cycle oscillator extraction — IMPLEMENTED + HW-CONFIRMED 2026-07-10 (E4XT)

New creative stage `processors/single_cycle.py` (CLI `--single-cycle[=auto|N]`):
replaces each sample with a short forward-looped slice of its own waveform so the
sampler plays it as an oscillator, and the hardware's filter/envelopes make the
patch. Turns an MPC multisample into an E4XT / K2000 synth voice; collapses a
bank to a few hundred bytes per zone. No writer changes were needed — the feature
only populates the shared `models.common` structures.

Key design decisions (all verified end-to-end, tuning within ≤1 cent):

- **Pitch detect**: pure-Python normalised autocorrelation (no numpy). Primary
  search is narrow, around the period implied by the sample's own `root_note`
  (the converter already trusts it for tuning), so it never locks to a spurious
  octave; a wide first-strong-peak fallback covers missing/wrong root metadata.
- **Cycle count**: `auto` = ONE cycle (see the 2026-07-11 refinement below); `=N`
  takes N contiguous cycles for the source's cycle-to-cycle movement.
- **Sub-sample extraction + loop**: refine the period to sub-sample precision
  (parabolic interp of the autocorr peak), resample exactly 1 (or N) period(s) to
  an integer frame count so the wrap is phase-perfect (no crossfade), TILE to
  `_MIN_LOOP_FRAMES=256`, and prepend an 8-frame faded lead-in so `loop_start ≥ 1`
  (old EMU "loop can't start at frame 0" caveat; harmless on K2000).
- **Tuning — the crux**: the perceived pitch is `rate / single-cycle-period`
  (an N-cycle loop of a periodic wave still sounds at the fundamental, NOT at
  `rate/loop_len`). The sub-semitone correction is **baked into each sample's
  stored sample rate** (`rate = orig_rate · freq(nearest_note) / f_fund`), not a
  cents field — because **E4B carries only ONE fine-tune per voice**, so a
  per-zone cents field cannot individually tune samples that share a voice.
  Rate-baking is per-sample and near-exact (integer-Hz rounding ≈ 0.04 c near
  44 kHz) and is engine-agnostic (both writers derive pitch from stored rate +
  root). `fine_tune`/`coarse_tune`/`transpose` are zeroed; `root_key` set to the
  nearest note. Survives the KRZ headroom downsample (a clean resample preserves
  `rate/loop_len`).
- **Neutral preset**: `filter_type=3` (XPM "Low 4" → E4B `0x00` 4-Pole LP /
  K2000 Alg-1 4POLE LOPASS — the one XPM value that lands on 4PLP on BOTH and is
  truthy so the KRZ writer actually patches it), `filter_cutoff=1.0` (open),
  organ amp env (instant on, full sustain), no LFO. `--single-cycle-keep-flt/
  -lfo/-amp/-all` let the already-converted source params pass through instead.
- **Best-effort**: unpitched/too-short samples are left full-length (logged), the
  preset is still neutralised — a creative option where "failing" is acceptable.
- **EOS minimum loop length (HW-confirmed 2026-07-10)**: the E4XT silently
  DOUBLES an ultra-short loop → the note plays an **octave low**. Measured on the
  E4XT with pure-sine single cycles: an 84-frame loop (C5, 523 Hz) played in
  tune, but a **42-frame loop (C6, should be 1046 Hz) played 524 Hz** — exactly
  one octave down, identical to the 84-frame note. Fix: `_MIN_LOOP_FRAMES = 256`
  in `single_cycle.py` — high notes repeat whole cycles (`n_cyc` bumped to
  `ceil(256/p)`) until the loop clears the minimum. Identical repeats keep the
  pitch and single-cycle timbre; low notes stay literally one cycle. After the
  fix, MIDI 24→84 track perfectly (each octave doubles, 0 cents). (Above MIDI ~84
  gxtuner can't lock at 2–4 kHz and reports garbage, but the notes are audibly
  correct — a tuner limit, not playback.)

Companion flag `--split-velocity-layers` (`processors/zone_reducer.explode_velocity_layers`)
explodes each preset's velocity layers into separate full-velocity presets
(handles both the XPM zone-band and SF2/SFZ/GIG multi-voice representations);
overflow past the 1000-preset cap fans into extra banks automatically.

Verification done: N=1 tunes to 0.0 c through a real E4B write→parse round-trip;
N=4 within ±1 c (sub-sample measured); loop_start ≥ 1; filter/keep-flags; both
representations of the layer split; E4B + KRZ both write. **HW-CONFIRMED on the
E4XT 2026-07-10** (via `SINETEST.iso`, pure-sine single cycles): tuning tracks
perfectly and in tune from MIDI 24 to 84 (each octave doubles, 0 cents), loops
sound and look good. The one issue found on hardware — ultra-short loops playing
an octave low — is fixed (see the EOS-minimum-loop bullet above) and re-confirmed
on the E4XT.  KRZ (K2000) tested via a Gotek FAT12 floppy (SCSYNTH.img) — sounds
good.  Cleared to commit.

#### Refinements from real-world HW testing (2026-07-11)

Everything below is in `processors/single_cycle.py` and was driven by playing the
output on the E4XT (and a K2000 floppy).

- **`auto` is now ONE cycle, tiled — not a multi-cycle fill.**  The original
  `auto` filled ~1024 frames with *contiguous* cycles.  A real analog oscillator
  drifts slightly cycle-to-cycle, so a multi-cycle loop isn't exactly periodic and
  buzzed at the loop rate.  `auto` now extracts a single cycle and TILES identical
  copies to reach the minimum length (perfectly periodic → no drift, no seam
  buzz).  `=N` still cuts N contiguous cycles for those who want the movement.
- **Sub-sample-accurate extraction (the harshness fix).**  The remaining
  "harshness" on short/high-note cycles (and the tiled pink noise) was traced —
  via the user's filter test (it lived above ~10 kHz) and an offline spectrum
  check — to a **fractional-sample phase step at the loop wrap**: a whole-sample
  cut of a fractional-period cycle leaves a "kink" that is proportionally huge on a
  60-frame cycle (tiny on a 475-frame one).  Fix: refine the period to sub-sample
  precision (parabolic interp of the autocorr peak) and resample exactly one period
  to integer frames.  Measured ~0.00 % energy > 10 kHz on the previously-harsh
  triangle/square loops afterward.
- **Aliasing is inherent to single cycles played up; multisampling cures it.**
  A bright single cycle transposed up the keyboard folds harmonics past Nyquist.
  The real fix is multisampled input (a cycle per source octave → each key barely
  transposes); real `.xpm`/`.sf2` multisamples get this for free.  (The SYS100
  construction-kit build originally mapped one cycle across all keys → aliased;
  rebuilding it as a per-octave multisample fixed it.)
- **Octave-fold-to-prior was TRIED and REVERTED.**  Forcing a harmonic/subharmonic
  lock back to the labeled octave regressed 45 → 356 low-confidence (it drags clean
  locks onto non-periodic points).  Some lo-fi textures (e.g. BoC "Annenberg" —
  dominated by a ~2 kHz partial with a weak fundamental) simply have no clean single
  cycle at their labeled pitch.  Accepted as a best-effort limitation.
- **`--split-velocity-layers` + single-cycle → near-duplicate presets.**  Single-
  cycle strips dynamics, so a pad's velocity layers collapse to the same oscillator.
  A build-time de-dupe (phase/pitch-invariant harmonic-magnitude fingerprint,
  cosine ≥ 0.99) removes them, but MUST be scoped **within each source patch**
  (group by preset name minus the `_L<n>` suffix) — a global compare falsely merges
  different instruments because many single cycles share low-harmonic spectra.
- **K2000 floppy path.**  Single-cycle multisamples need the KRZ headroom
  downsample (~24 kHz) or wide zones clamp on the K2000 up-pitch ceiling; then
  `write_krz` → FAT12 via `writers.fat12.format_new` → `.add_file`.  Scratchpad
  builders `build_sys100.py` / `build_synth_sc.py` show the full recipe (combine
  many XPMs → single-cycle → re-split zones by *detected* root → split-layers →
  de-dupe → E4B/ISO + KRZ/floppy).
- **`--single-cycle-dump-dir` WAV export (2026-07-12).**  The dump path
  (`single_cycle._dump_cycle` → `_wav_bytes_with_loop`) now emits a proper `smpl`
  chunk — one forward loop (`loop_start`/`loop_end`, inclusive) plus the MIDI
  unity note — under a descriptive `<sample>_<note>.wav` name, so the oscillators
  import into samplers we don't write presets for (loop + tuning intact). Field
  offsets mirror `xpm_parser._read_smpl_loop` / `_read_smpl_root`, so they
  round-trip back through our own importer.

---

## §KRZ-CWM — Fidelity gaps found via ConvertWithMoss cross-reference (2026-07-22)

TODO item: *"KRZ: fidelity gaps found via ConvertWithMoss cross-reference"*.
Source: a full byte-level diff of ConvertWithMoss's KurzFiler-derived
`format/kurzweil/*.java` against `writers/krz_writer.py`. Ordered easiest-first.

**Update 2026-07-27 — PR #232 changes the "nothing to learn on the program
side" conclusion below.** At the time of the original 2026-07-22 diff, CWM's
KRZ writer only emitted a flat default program. [PR #232](
https://github.com/git-moss/ConvertWithMoss/pull/232) (merged) adds real
program-side modulation handling:

- **Velocity(AttVel=100)→cutoff on the F1 filter page**, read+write, claimed
  round-trip-verified against a real K2000-saved FM-bass program. Their depth
  scale: `MAX_VELOCITY_MODULATION_CENTS = 9600` (8 octaves) — a candidate
  value for our own still-blocked "Modulation routings" depth calibration
  (see `TODO.md`, filter Src2=`HOB0[7]`; our own unconfirmed estimate there
  is a *different* number, ±10800 ct, sourced from the general F-page
  Src-Depth range in the manual rather than measured). Worth a disk-save
  cross-check of both numbers before trusting either — **not wired into
  `krz_writer.py`**, since this needs our own hardware confirmation, and it's
  unclear from the PR description alone whether their "one F1 modulation
  source" model maps directly onto the *two* independent slots our own RE
  documented (Src1=`HOB0[5]`/depth`[6]` for ENV2, Src2=`HOB0[7]` for
  velocity/mod-wheel) or whether real K2000 programs only ever populate one
  of the two at a time in practice.
- **Envelope "unused stage" semantics**: a K2000 envelope stage with *both*
  zero time and zero level is unused on the device and holds the previous
  stage's level, rather than decaying to silence — CWM's reader was treating
  it literally and producing silent FM-bass conversions. **Checked against
  our own writer, not applicable:** `writers/krz_writer.py._env_time_byte`
  floors every written time byte at `3` (`max(3, ...)`), so `_fill_env` never
  emits a literal on-disk time of `0` — the ambiguous (0-time, 0-level) case
  this PR fixes can't occur in mpc2emu's own output. It matters to a *reader*
  of third-party KRZ programs, which mpc2emu didn't have at the time this
  note was written — see §KRZ-READER below, which added exactly that.

  **UPDATE 2026-07-28: this bit us too, now that the reader exists.** A
  second CWM cross-check (post-#232 merge) found `krz_parser._decode_env`
  had the *exact same* bug the note above flagged as "not applicable" —
  applicable now that §KRZ-READER shipped a real reader after this note was
  written, and apparently missed in that work. Confirmed against the local
  201-file corpus: **30.6% of 7228 voices** read `sustain==0.0` before the
  fix (silent/held-forever presets), dropping to 1.6% after — a much larger
  real-world impact than CWM's own "FM bass" framing suggested. Fixed the
  same way: `seg[6]==0 and seg[7]==0` (raw decay bytes) → `sustain=1.0`
  (holds at the attack peak) instead of the literal `level/peak=0`. New
  regression test `test_decode_env_unused_decay_stage_holds_peak` in
  `tests/test_krz_roundtrip.py`. Full writeup in `docs/KRZ_FORMAT.md` §4.4.
  Not yet hardware-confirmed on a real K2000/K2000R.

### 1. Per-sample gain (`Soundfilehead.volumeAdjust`) — DONE + HW-CONFIRMED (2026-07-23)

`volumeAdjust` (Soundfilehead byte 2) and `altVolumeAdjust` (byte 3) are signed
i8 in **0.5 dB steps** (−64.0…+63.5 dB — the MISC-page "Volume Adjust"). We used
to write `0`. Now applied in `writers/krz_writer.py`:

```python
def _vol_adjust_byte(volume_db: float) -> int:
    return max(-128, min(127, round(volume_db * 2)))   # 0.5 dB steps, signed i8
```

Gain is per-zone in our model (`ZoneMapping.volume`, dB) but the header field is
per-sample, so `write_krz` aggregates the **mean** volume of every zone referencing
a sample into `sample_gain_db[name]` and passes it to `_write_sample_object`, which
packs `_vol_adjust_byte(gain) & 0xFF` into both volumeAdjust and altVolumeAdjust.
The common MPC case is 1 zone : 1 sample (exact); a sample shared by zones at
different levels averages (lossy, rare). **0 dB → 0**, so unity samples are
byte-identical and the HW-verified filter floppies are untouched.

**HW-confirmed on the K2000R (2026-07-23).** `tests/re_banks/gen_volume_adjust_test.py`
builds a constant-pitch `VOLADJ` floppy: three key-blocks playing the *same* 240 Hz
sine at unison, differing only in zone volume (0/−6/−12 dB → bytes 0/−12/−24). On
hardware each block stepped down in loudness exactly as intended → the K2000 honours
the field and the 0.5 dB/step scale is correct. (An initial 0/−12/−24 dB build had a
silent −24 dB block = below monitor level, plus an octave-label mismatch — the K2000
calls MIDI 60 "C3", our `_note_name` calls it "C4"; display-only, no byte impact.)

### 2. Partial key-tracking in the keymap entry `tuning` — needs a test source

`_build_keymap_entries` writes a **constant** per-zone `tuning` = `100·(R_sample −
R_zone) + fine_tune`, i.e. it assumes 100 % chromatic tracking (the K2000 does the
per-key transpose itself). To honour a source `key_tracking` (0..1, where 1 =
normal, 0 = drum/fixed pitch), make the tuning per-key:

```python
# per key `note` in the zone, instead of a constant offset:
tuning = round((key_tracking - 1.0) * (note - R_sample) * 100) + fine_tune
# key_tracking == 1.0 -> constant fine_tune (today's behaviour); == 0.0 -> fixed pitch
```

*Blocked on:* an input path that actually carries keytrack ≠ 1 (XPM/SFZ). Add the
plumbing only alongside a real source + HW drum-map check. Beware the existing
hole-fill and up-pitch-ceiling logic operate on the *constant* assumption — a
fixed-pitch (keytrack 0) map has no up-pitch problem, so gate the ceiling cap off
when `key_tracking == 0`.

### 3. Native 8-level multi-table keymap — larger, weigh vs current splitting

The keymap `Level[8]` field can point the 8 dynamic levels (velocity `j·16…+15`)
at up to 8 distinct entry tables inside **one** keymap:

```
Level[j] = (8 - j)*2 + tableIndex_for_level_j * (num_entries * entry_size)
tables laid out after the header: numTables x (entriesPerVel+1) x entrySize
```

CWM builds these from source velocity zones (`KurzweilCreator.calcBandOverlap` /
`setTableIndexOfLevel`, sharing a table across levels with identical content).
Adopting it would let `_split_voice_by_velocity` fold velocity bands back into one
keymap + **one** layer, relieving the 32-layer cap and the "3 regular layers"
spread. *Trade-off:* our current per-band split-layer approach is HW-verified; the
multi-table form is not. Decision + HW confirm required before touching a working
path — keep as a design item, not a drive-by change.

**Read side done (2026-07-27, §KRZ-READER below):** `parsers/krz_parser.py`
decodes native `Level[8]` multi-table keymaps (real third-party content uses
them — 15-30 keymaps in the local corpus, depending on how it's counted).
This item is about the *writer* still never emitting them; unaffected.

### 4. Stereo / multi-root sample objects — broader feature

We emit mono, single-`Soundfilehead` samples. The multi-header generalization
(also in `docs/KRZ_FORMAT.md` §3.1):

- `KSample.numHeaders = N − 1` (N headers); `flags` bit `0x01` = stereo, headers
  in L/R pairs, even index = left; keymap `subSample` references the **left** (odd:
  1,3,5…).
- each header's envelope offsets become `(numHeaders − 1 − i)·32 + 8` and `+6`
  (we hardcode `8`/`6`, valid only for the single/last header).

Gated behind general stereo support in the converter; HW confirm needed.

### 5. Doc-only reconciliations (no code change)

- **Object-type hash decode:** our unconditional `hash >> 10` mislabels objects
  with the `0x8000` bit clear (types > 42 use `hash >> 8`: 111 QA-bank / 112 song
  / 113 effect). We never emit them; only relevant if we add a reader. Documented
  in `docs/KRZ_FORMAT.md` §2.2.
- **Entry-index base:** CWM sounds entry `i` at MIDI note `i + 12` (`basePitch=0`,
  `BASE_NOTE=12`); we index entries by raw MIDI note. Ours is HW-confirmed to play
  correctly, so this only matters if an external reader (incl. CWM) reads our files
  — verify whether it sees our zones shifted +12 before assuming interop.

## §KRZ-READER — KRZ added as a source format (2026-07-27)

TODO item: *"KRZ was write-only; add it as an input format"* — prompted by
Jan asking how much effort it'd take, given ConvertWithMoss shipped a KRZ
reader in the preceding ~10 days partly credited to this project's own
hardware RE (see §KRZ-CWM above and `dea9dbb` in ConvertWithMoss).

**Done.** `parsers/krz_parser.py`, `parse_krz(path) -> Bank`, wired into
`parsers/registry.py` (`'.krz'`). Structural template: `parsers/e4b_parser.py`
(self-contained binary reader, in-memory PCM, numeric-id→name resolution,
per-object `try/except` + `[WARN]`, never fatal).

**Why cheaper than a normal new-format reader:** the container walk already
existed as a diagnostic tool (`tests/re_banks/krz_reader.py`, promoted into
the new module since `tests/` is gitignored and can't be imported from
shipping code) and was corpus-verified against 577 real files (zero
container/segment failures) *before* any model-building code was written.
The format is documented at byte level in `docs/KRZ_FORMAT.md`, and the DSP
decoders (filter/cutoff/resonance/envelopes) are inverses of encoders this
project already hardware-RE'd in `krz_writer.py` — this was mostly a
model-construction job, not a reverse-engineering one.

**Scope implemented, all in one pass** (the original 3-phase estimate
collapsed once the container proved solid):
- Samples: PCM extraction with BE→LE byteswap, loop points, per-sample gain
  (`Soundfilehead.volumeAdjust`), sample-rate reconstruction snapped to
  standard rates (see finding below).
- Keymaps: the full method bitfield (compacted keymaps, i8 tuning, per-entry
  volAdj — the writer only ever emits one variant, `0x13`; real content uses
  12 different ones, see corpus counts in the KRZ-as-source-format plan) and
  the native `Level[8]` multi-velocity-table mechanism the writer never uses.
- Programs: key/velocity geometry, filter type (many-to-one reverse map,
  same "canonical representative" approach as `e4b_parser.py`'s own filter
  table), cutoff/resonance, amp + filter envelopes (a *reducer*, not a strict
  inverse — see below), LFO1, and the AMPENV Natural-mode gate.
- Orphan recovery: keymaps no program references, and samples no keymap
  references, are recovered into synthetic presets rather than silently
  dropped (real pure sample-pool banks exist in the corpus).
- ROM/absent samples (K2000 built-in waveforms, ids < 200, no PCM in the
  file) are dropped with one summarized `[WARN]` per bank, never per-zone;
  an all-ROM program-only bank gets a plain `[INFO]` rather than looking
  like a parse failure.

**Corpus findings that shaped the design** (577 local `.KRZ` files,
`tools/krz_corpus_check.py`):

- **CAL keymap-slot resolves in mpc2emu's favor, not CWM's.** `CAL[7,8]` is
  the sole keymap-id carrier in **0 of 33,866** program layers; `CAL[11,12]`
  alone in 30,483; both set (disagreeing) in 948. CWM's `KurzweilProgram.java`
  reads `[7,8]` first, so it misreads those 948. `krz_parser.py` reads
  `CAL[11:13]` only, matching the writer and `docs/KRZ_FORMAT.md` §4.2. This
  **closes** doc-only reconciliation item 5 above (partially — the hash-decode
  half of that item is still open, we still don't emit type-28 FX objects so
  it doesn't bite our own output).
- **Entry-index base evidence favors mpc2emu's convention, not conclusively.**
  Root-inside-zone check over 8,010 multisample entry-runs: `note = i` 39.6%
  vs CWM's `note = i+12` 26.4%. Recorded in `docs/KRZ_FORMAT.md` §3.2 and
  `TODO.md`; **not** closed outright — wants an aural/HW check.
- **PCM-extent recovery needed a hard ceiling, found by testing against
  synthetic writer output, not the real corpus.** The first implementation
  floored the extent at `sampleEnd + 1`, reasoning `sampleEnd` is always
  inclusive-last-frame. That overshoots by one word whenever two samples are
  packed with zero gap (common for the writer's own tightly-packed output),
  silently stealing one PCM word from the next sample. Fixed by making the
  next sample's start (or PCM-region end) a hard ceiling the floor can never
  exceed, with loop points defensively clamped afterward. Caught by building
  `tests/test_krz_roundtrip.py`, not by the corpus sweep (which only flags
  invariant *violations*, and the original bug happened not to trip one for
  most files — 24 of 583 local files had visibly out-of-range loop points
  before the fix, all self-authored test/demo banks with tight packing).
- **Sample-rate snapping** — `samplePeriod` is an integer nanosecond value,
  so `1e9/period` doesn't invert exactly (a written 44100 Hz reads back as
  44099/44098 depending on rounding direction). Snapped to the nearest
  standard rate within ±2 Hz, matching ConvertWithMoss's approach.
- **Pre-existing writer bug found by actually round-tripping real content
  (KRZ→KRZ→KRZ, not just synthetic fixtures), 2026-07-27: the up-pitch
  ceiling was measured from the wrong root.** `_build_keymap_entries`
  computed `ceiling = _compute_max_pitch(sample.sample_rate, r_sample)`, using
  the sample's own physical `root_note` — but the hardware's actual total
  pitch shift at key `K` is `(K - r_sample)*100` [auto-transpose] `+ tuning`,
  and since `tuning = 100*(r_sample - r_zone) + fine_tune`, that total
  algebraically reduces to `(K - r_zone)*100 + fine_tune`. So the ceiling —
  which bounds how far *above the sample's actual playback rate* the K2000's
  48kHz internal engine can stretch it — must be measured from `r_zone`
  (`zone.root_key`), not `r_sample`. Whenever a zone deliberately retunes
  (`root_key != sample.root_note`), the old check mis-flagged perfectly safe
  assignments as over-ceiling and silently dropped the sample from the
  keymap. Found via Patchman `PMVOL098.KRZ` (`2000 Series v114`, "Lo Fi Kicks
  1"): a genuine drum map where each key gets its own sample at an
  independently chosen pitch (`entry.tuning` cancels the normal per-key
  auto-transpose entirely) — parsed correctly by `krz_parser.py`, but
  re-encoding that Bank back to KRZ dropped 4 of the kit's 45 samples, which
  the reader then correctly (if confusingly) recovered as an orphan preset on
  the next parse, one new orphan compounding with every generation. **This
  bug was not specific to KRZ-sourced content** — any source format producing
  a deliberately retuned zone (`root_key != root_note`) would have hit it when
  converting *to* KRZ. Fixed by measuring the ceiling from `r_zone`
  (`writers/krz_writer.py:392`). Verified: `PMVOL098.KRZ` is now stable
  gen1→gen2→gen3 (`Lo Fi Kicks 1`, 45 samples, no orphan preset); the existing
  HW-confirmed `tests/test_krz_writer.py` suite is unaffected (its fixtures
  never exercise `root_key != root_note`, so `r_zone == r_sample` there and
  the fix is a no-op for every case that was already HW-verified).

**Known remaining limitation (not fixed, documented 2026-07-27): `_coverage_
remap_voices` / `_voices_stacked` are not idempotent across repeated KRZ→KRZ→
KRZ generations.** `tools/krz_to_krz_check.py` (parse → write → parse → write
→ parse, 3 generations) found 10 of 593 local files where gen2→gen3 zone/
preset counts drift — all of them this project's own synthetic multi-voice
octave-slice pad-stack test/demo banks (`JRSLO*`, `K2KFEATDEMO*`,
`krz_staging/VPO_BRASSACC|BRASSNOR|VIOLINKS`, `SCSYNTH_01`), **zero real
commercial-library files** (all 12 Patchman files that were unstable before
the ceiling fix are now stable). Root cause: `_coverage_remap_voices` (§7.3's
already-documented lossy octave-slice rebuild) regroups samples by root
differently when applied a second time to its own previous output, so a
second re-encode can leave a different subset of samples referenced by no
keymap; `krz_parser.py`'s orphan recovery correctly rescues them each time,
but that means a new tiny recovery preset can appear every generation instead
of the set settling. Not chased further: a real user's KRZ→other-format
conversion only round-trips through the writer once, so this only bites
KRZ→KRZ→KRZ chains of this specific stacked-pad content, and doesn't affect
any real library found in the local corpus. Would need `_coverage_remap_
voices` made idempotent (or gated off on Bank input that is *already* a
coverage-remap's own output) to close for good.

**CR-21 two real crash bugs found via VinSamLib re-processing real
commercial content — DONE 2026-07-27.** VinSamLib's own black-box testing
of "reprocess an existing KRZ preset through mpc2emu" (parse → optionally
resample/reduce → write back) against a real Kurzweil SynthExpanse file
crashed with `struct.error: pack_into requires a buffer of at least 645
bytes for packing 5 bytes at offset 640 (actual buffer size is 640)` at
`writers/krz_writer.py._build_keymap_entries`, raised from
`_write_keymap_object`. This looked at first like it might invalidate the
idempotency entry's "zero real commercial files affected" conclusion (a
ONE-pass crash, not a multi-generation drift) — turned out to be two
separate, independent bugs:

1. **`parsers/krz_parser.py` fabricated a phantom 0-length `SampleData`.**
   The repro file is `.../Kurzweil K2000 SynthExpanse/SynthExpanse/Disk1/
   SYNTHEX_1.KRZ` — a multi-disk soundset. Two of its sample headers
   (`Prodigy ShortBas`, `Sprinkle`) have `has_data=True` (flags bit 0x40
   set) but a `sampleStart` word offset (783170) that lies entirely
   outside *this file's* own PCM region (690058 words) — the sample's
   real PCM is on a different disk in the set, not present here. The old
   `_extract_pcm` sliced `data[start_byte:end_byte]` with `start_byte`
   past `len(data)`, which Python silently returns as an empty `bytes`
   object rather than raising — so a 0-length `SampleData` got created
   and fed downstream instead of being treated as unavailable. Fixed:
   `_get_sample` now checks `h.start_w >= pcm_words` and treats it exactly
   like ROM/absent (same `n_rom` counter, same summarized `[WARN]`,
   `used_sample_ids` still marked so it isn't ALSO offered to orphan-sample
   recovery).
2. **`_coverage_remap_voices` had no upper clamp on `hi_key`.** Once (1)'s
   phantom sample was excluded, the specific reported preset ("Phase
   Dist") no longer had any zones at all and stopped reaching
   `_coverage_remap_voices` — but the buffer-overflow mechanism itself is
   a real, separate, general bug independent of phantom data. The function
   computes `zz.hi_key = max(lo, ceil)` where `ceil =
   _compute_max_pitch(sample_rate, root) // 100` — a per-root up-pitch
   ceiling that is **not otherwise bounded**, unlike
   `_build_keymap_entries`'s own zone-level ceiling check (`hi_key =
   min(zone.hi_key, ceiling)`, which can only ever *reduce* `hi_key` below
   a well-formed zone's own value). A legitimate high `root_note` combined
   with a low sample rate pushes `ceil` past 127 (e.g. root=127 @ 8000 Hz
   → ceil=158), and the resulting `hi_key >= 128` overflows the fixed
   `bytearray(NUM_KEYS * KEYMAP_ENTRY_SIZE)` = 640-byte keymap-entries
   buffer at exactly `key=128` → `offset=640` — matching VinSamLib's error
   message byte-for-byte. **Reproduced independently with plain synthetic
   data** (3 samples at roots 40/70/127, all at 8000 Hz, no phantom/corrupt
   data involved) — confirmed the OLD code crashes with the identical
   message, confirming this is the true general mechanism, not merely a
   symptom of (1). Fixed by clamping `zz.hi_key = min(NUM_KEYS - 1,
   max(lo, ceil))`, plus a matching defensive clamp on the zone-level path
   in `_build_keymap_entries` (`hi_key = min(zone.hi_key, NUM_KEYS - 1)`
   before the ceiling `min()`, cheap insurance now that this writer is
   exposed to arbitrary third-party content via `krz_parser.py` rather
   than only MPC-sourced conversions).

Verified: `tests/test_krz_writer.py::test_coverage_remap_ceiling_overflow`
(the synthetic repro, asserting no `struct.error`); the exact real-world
preset no longer crashes and the file's other 53 presets parse/write
cleanly; full 589-file local corpus sweep and 3-generation KRZ→KRZ→KRZ
sweep both show **zero exceptions** (the idempotency drift above is
unrelated and unchanged at the same 10-file count).
- **`filter_cutoff` is not a shared frequency scale**, confirmed while writing
  `tests/test_krz_roundtrip.py`: the KRZ writer maps 0..1 onto a *linear
  semitone* scale (`_cutoff_byte`), while the reader decodes through E4B's
  *log-Hz* scale (`hz_to_e4b_cutoff`, for consistency with every other
  parser). Both are internally correct; they're just different curves, so a
  round-tripped cutoff value legitimately doesn't come back unchanged. A
  follow-up (not done here) would route `_cutoff_byte` through Hz too,
  making writer and parser exact inverses.

**Shared codecs moved to `models/common.py`** (the CR-13/CR-18 pattern —
single home for writer+parser math instead of "kept in sync by comment"):
`krz_cutoff_byte_to_hz`, `krz_reson_byte_to_01`, `krz_env_byte_to_seconds`,
`KRZ_ENV_TIME_GRID`, `KRZ_RELEASE_FACTOR`. `writers/krz_writer.py` now
imports these instead of keeping its own copies.

**Verification:** `tests/test_krz_roundtrip.py` (write_krz → parse_krz,
geometry + DSP, deliberately dodging three writer-side structural rewrites —
hole-filling, layer-capping, the up-pitch ceiling — that would fail a naive
round-trip for the wrong reason); `tools/krz_corpus_check.py` (584 local
files, zero exceptions, model invariants); `tests/test_krz_writer.py`'s
`test_write_read_roundtrip`/`test_sample_gain` rewritten to call `parse_krz`
directly instead of shelling out to the old reader and regex-scraping stdout
— this rewrite is what surfaced a **pre-existing, previously-uncaught writer/
fixture issue**: both tests' fixtures assigned zones to key ranges beyond
their sample's up-pitch ceiling (root+1 semitone at 44.1kHz), which the
writer correctly refuses (delete-lockup avoidance), silently leaving that
voice's keymap empty — invisible to the old byte-regex assertions, which
never checked keymap sample-id fidelity. Fixed by giving each test fixture's
samples a `root_note` that covers their widest assigned zone.

`tests/re_banks/krz_reader.py` reduced to a thin CLI pretty-printer importing
the container walk from `parsers/krz_parser.py`, with the same `CAL[7,8]` bug
fixed in its display code.

## §CWM19 — Input-parser feature-parity gaps found via ConvertWithMoss 19.1.0 (2026-07-25)

TODO item: *"Input-parser feature-parity gaps found via ConvertWithMoss 19.1.0"*.
Source: [ConvertWithMoss 19.1.0 release notes](https://github.com/git-moss/ConvertWithMoss/releases/tag/19.1.0)
(`documentation/CHANGELOG.md` in `~/git-repos/ConvertWithMoss`, tag `19.1.0`,
commit `6765c11`), read against our own `parsers/exs24_parser.py`,
`parsers/sfz_parser.py`, `parsers/talsmpl_parser.py`, `parsers/sf2_parser.py`,
`parsers/gig_parser.py` (all independent reimplementations — no CWM code copied,
see file headers).

### Fixes in 19.1.0 checked and confirmed NOT applicable (already correct here)

- **EXS24 group panning read as unsigned/unscaled** (CWM: *Logic EXS24 — Fixed:
  The panning of a group was read as an unsigned value and was not scaled*). We
  don't parse group-level pan at all yet (see gap list below) — only zone-level
  pan, which is already signed and scaled correctly: `exs24_parser.py:705`
  (`pan = z['pan'] / 63.0`, `i8` read at `:576`).
- **TAL reverse flag parsed as text bool instead of numeric** (CWM: *TAL Sampler
  — Fixed: the sample "reverse" flag ... is stored numerically (0/1) ... but was
  parsed as a true/false text boolean*). Ours already reads it numerically:
  `talsmpl_parser.py:413` (`ms.get('reverse', '0') not in ('0', '0.0')`).
- **TAL "disabled groups" only skipped for `enabled="0"`, not `"false"`** (CWM:
  same fix text as the DecentSampler one, applied to TAL Sampler too). Doesn't
  map cleanly onto our model: TAL's `sampleenabled{a-d}` is the 4-*layer*-slot
  enable within one program (not a DecentSampler-style alternate-kit group), and
  our corpus-verified format notes (`talsmpl_parser.py:71`, 1706-preset survey)
  say TAL only ever writes `"0"`/`"1"` for these flags, never `"false"`. Already
  numeric-checked correctly at `:357`.
- **SFZ velocity range grown from the crossfade opcodes** (CWM: *SFZ — Fixed:
  The velocity range was taken from the cross-fade opcodes, so it grew by the
  width of the cross-fade with every conversion*). Ours reads `lovel`/`hivel`
  directly (`sfz_parser.py:437-438`) and only *checks for the presence of*
  `xfin_lovel`/`xfin_hivel`/`xfout_lovel`/`xfout_hivel` as a separate flag
  (`:358-359`) — never reads the range from them.
- **"Two filters differing only in their cutoff envelope treated as equal"**
  (CWM: generic backend fix — could merge non-identical zones). We have no
  zone-dedup / filter-equality-merge logic anywhere in the parsers, so this
  failure mode can't occur.

### Confirmed input-parser feature-parity gaps (not bugs — CWM extracts these, we don't yet)

Ordered by rough usefulness; none are blocking anything, pick up independently:

1. **EXS24 group-level volume/pan/tune offsets.** CWM 19.1.0 *New: Added support
   for group volume, panning and tuning offsets* (Kontakt, DecentSampler, Logic
   EXS24, Synclavier, TX16Wx, Waldorf Quantum/Iridium). We parse the EXS24 group
   struct only for names (`exs24_parser.py` GROUP_V11, used for L/R stereo dedup,
   see `:328-359`) and per-group envelopes (`:682-684`) — group pan/volume/tune
   fields are never read, so a group-level offset is silently dropped (zones keep
   only their own pan/volume/tune).
2. **EXS24 Velocity → Filter Cutoff modulation.** CWM 19.1.0 *New: Implemented
   Velocity -> Filter Cutoff Modulation (read/write)*. We read filter *keytrack*
   (`exs24_parser.py:155,219-223`, itself unverified-scaling / no corpus example)
   but nothing for a velocity→cutoff cord.
3. **EXS24 one-shot playback flag (ignore note-off).** CWM 19.1.0 *New: Added
   support for the one-shot playback mode* (EXS24 among ~15 formats). We have no
   EXS24 field read for this — the only "oneshot" string in the file is an
   unrelated audio-folder-name heuristic (`exs24_parser.py:387`, sample-file path
   resolution, not a preset flag).
4. **Choke / exclusive groups.** CWM 19.1.0 *New: Added support for exclusive
   ('choke') groups* (EXS24 and SF2 among the formats we read; also Kontakt/DLS/
   MPC1000/MPC60/Renoise/MV-8000/TAL — formats we don't read). Not present in
   `parsers/exs24_parser.py` or `parsers/sf2_parser.py`, and no `Preset`/`Zone`
   model field to hold it yet either.
5. **Amplitude keyboard-tracking.** CWM 19.1.0 *New: Added support for amplitude
   keyboard-tracking* (Akai S1000, DLS, Logic EXS24, Roland MV-8000/S-7xx, SFZ,
   Synthstrom Deluge, Yamaha YSFC — EXS24 and SFZ are ours). We support *filter*
   keytrack but not amp keytrack in either parser.
6. **Envelope time keyboard-/velocity-scaling.** CWM 19.1.0 *New: Added support
   for envelope time keyboard- and velocity-scaling* (Akai S1000, Ensoniq EPS/
   ASR/Mirage, Logic EXS24, Reason NN-XT, Roland S-7xx, SoundFont 2, Yamaha YSFC
   — EXS24 and SF2 are ours). Distinct from the envelope-slope ("curvature")
   support we already have; this scales the *time* by key/velocity.
7. **Per-instrument voice settings (polyphony, mono legato).** CWM 19.1.0 *New:
   Added support for per-instrument voice settings* (Akai S1000, DecentSampler,
   Disting EX, Ensoniq Mirage, Logic EXS24, Reason NN-XT, Roland S-7xx, SFZ,
   Synthstrom Deluge, TAL Sampler — EXS24, SFZ, TAL are ours). No polyphony/
   legato field read by any of our parsers.
8. **Random play logic (vs. round-robin).** CWM 19.1.0 *New: Added support for a
   random play logic next to round-robin* (Ableton, Akai MPC, DecentSampler,
   Logic EXS24, Renoise, Yamaha YSFC — EXS24 is ours; falls back to round-robin
   when a format can't express it). Not distinguished from round-robin in
   `exs24_parser.py` today.

### Not relevant

- Roland ZEN-Core SVZ embedded-WAV fix, Waldorf Quantum/Iridium fixes, Elektron
  Tonverk / Reason NN-XT / Omnisphere / Deluge / Disting EX / Polyend / Bliss /
  1010music / TX16Wx fixes, and the new Kurzweil K2000/K2500/K2600 **reader** —
  none are formats/directions we read or write (we *write* KRZ, CWM's new K2000
  support is a *reader*; no overlap to exploit).

---

## §E4BREAD — E4B reading gaps found via ConvertWithMoss's independent E4B reader (FIXED 2026-07-26)

**Context:** `parsers/e4b_parser.parse_e4b` is registered as an input format
(`parsers/registry.py`) — not just this project's own round-trip validation
oracle — because the sibling `VinSamLib` project (a librarian GUI built on
top of mpc2emu) reads real third-party/commercial `.e4b` files through it.
Cross-referencing ConvertWithMoss's independent E4B reader (PR #220,
`format/emu/emulator4/Emulator4Detector.java`) surfaced two real gaps in that
reading path — both now fixed.

### 1. Zone key/velocity range not intersected with the voice-level window

**Symptom:** many real hardware/commercial presets leave a voice's *zone*
entry wide open at 0-127 (key and velocity) and do the actual split at the
*voice* level instead (`vpar[14]`/`[17]` key, `vpar[18]`/`[21]` velocity —
see `docs/E4B_FORMAT.md` §4.1, hardware-RE'd 2026-06-14). `_parse_voice` read
`lo_key`/`hi_key`/`lo_vel`/`hi_vel` straight from the zone entry only and
never consulted the voice window, so such a voice's sample mapped across the
whole keyboard/velocity range instead of its real one.

**Fix** (`parsers/e4b_parser.py`, in the zone loop of `_parse_voice`):
intersect each zone's range with the voice window —
`lo_key=max(vpar[14], entry.lo_key)`, `hi_key=min(vpar[17], entry.hi_key)`,
same pattern for velocity. If the intersection is empty (`lo > hi`), the zone
is dropped rather than emitting an inverted range (mirrors CWM's own
early-exit — commit `ead0e07`, cross-referenced against 76057 real zones from
the E-mu Producer Series CD-ROMs).

**Why this is safe for mpc2emu's own output:** `writers/e4b_writer.py`
(`_build_voice`) always sets the voice window to the min/max of the voice's
*own* zones, so the intersection is a no-op there by construction — verified
with a synthetic multi-zone round-trip (two zones, disjoint key ranges,
unaffected after the fix). Only third-party-authored files where a zone is
genuinely wider than the voice window are affected.

### 2. `loop_end_l` off-by-one

**Symptom:** CWM's reader (commit `2ccefea`) found the on-disk `loop_end_l`
field stores the frame *before* the true last loop frame, not the true last
frame itself — measured empirically by checking the PCM amplitude step at the
loop seam across a real commercial corpus: reading the raw value directly
left many seams with a step over a third of peak amplitude; adding `+1`
(capped at `numFrames−1`) eliminated all of those and raised the clean-seam
share from 78% to 95%.

Our own `parsers/e4b_parser.py`/`writers/e4b_writer.py` pair previously
treated the on-disk value as `loop_end` directly — an exact inverse of each
other, so our own write→parse round-trip was unaffected by this convention
either way, but reading a **third-party** file's loop point through
`e4b_parser` alone would land one frame short of the model's documented
"inclusive last loop frame" convention (`processors/loop_renderer.py`).

**Fix:** both sides updated together, keeping them exact inverses —
- `writers/e4b_writer.py._build_sample_header`: `lel = (loop_end - 1) * 2 + STRUCT_SZ`
- `parsers/e4b_parser.py._parse_sample_body`: `loop_end = min((loop_end_l - STRUCT_SZ) // 2 + 1, n_frames - 1)`

Verified: (a) mpc2emu's own write→parse round-trip is still an exact identity
(loop_end in == loop_end out); (b) the on-disk byte now encodes `loop_end - 1`
as expected; (c) `test_pipeline.py`'s existing PINGPONG round-trip and
`tests/test_krz_writer.py` (9 tests) still pass.

**Hardware-confirmed 2026-07-28** via `tests/re_banks/gen_hw_confirm_batch.py`
— a 100 Hz sine looped over exactly 20 whole periods (44.1 kHz → 441
samples/cycle, an exact integer, so any 1-frame loop-point error would
introduce a phase discontinuity right at the seam), held for 9s (~45 loop
repeats) on the real E4XT and recorded. Checked the actual waveform at
every loop-boundary crossing directly (not just by ear): the
sample-to-sample delta there (0.0011–0.0018) was *smaller* than the
typical mid-cycle delta elsewhere in the same recording (0.0083) — no
discontinuity, a clean seamless loop with the fix applied.

## §E4BREAD2 — Two more E4B reading gaps found via ConvertWithMoss PR #242 (FIXED 2026-07-28)

**Context:** ConvertWithMoss PR #242 (independent E4B reader, commit
`054972c7`) made two more claims about `Emulator4Detector.java` that this
project's own `documentation/design/E4B_FORMAT.md` (their doc, built partly
from mpc2emu's own RE work) had gotten wrong. Per the standing project rule,
both were checked against real local third-party `.e4b` content **before**
touching any code — see the corpus numbers below. Both turned out to be real,
independent of CWM's own corpus.

### 1. Amp/filter envelope: only stage 1 of each pair was read

**Symptom:** the 6-stage PZT (Attack1/Attack2/Decay1/Decay2/Release1/
Release2, bytes 0-11 amp / 14-25 filter) had only stage 1 of each pair read
(`_fenv_rate_inv(pzt[0])` for attack, `pzt[4]` for decay, `pzt[8]` for
release, `pzt[5]`'s LEVEL for sustain) since CR-5 (2026-06-10). CWM's PR
claims this is the same envelope as the Emulator X, and that decay1 is
frequently a *plateau* (holds at attack2's peak) with the real decay-to-
sustain motion happening in decay2 alone — reading decay1's level as
"sustain" makes a voice that should decay over many seconds instead "sustain
forever" at (near-)full volume, matching the classic "Nylon Guitar" bug
class (a plucked instrument that rings and fades vs. one that holds the pick
attack's level indefinitely).

**Corpus-checked before fixing** (141 local third-party `.e4b` files,
32,558 voices): stage-2 has a nonzero *time* in only ~1-2% of voices
(attack2 1.1%, decay2 1.6%, release2 0.2% — usually negligible on its own),
but where decay1's and decay2's *levels* differ sharply (0.9% of voices,
`|Δ| >= 50` out of 127), it's concentrated in one-shot SFX material: every
sampled example came from one `ProRec "Hollywood"` sound-effects bank
(`WALKER C1`, `DARTH VADER`, `LASER`, `X-WING`, …) where decay1 = byte 126
(near-full, ~31ms — read alone as "sustain at 99%") and decay2 = byte 118
(the *real* ~29.4 SECOND decay to silence). Old read: `attack=0.031 decay=
0.031 sustain=0.992 release=4.6`. Real envelope per the raw bytes:
`attack=5.8 decay=29.5 sustain=0.0 release=4.6` — a completely different,
audible envelope shape.

**Fix** (`parsers/e4b_parser.py`, both amp and filter envelope decode): sum
both stages' TIMES per pair (`attack = attack1_s + attack2_s`, same for
decay/release) and read **sustain from decay2's level**, not decay1's. For
mpc2emu's 4-stage `Envelope` model (no separate hold field), this is
provably equivalent to CWM's hold+decay split regardless of whether decay1
is a true plateau: `hold + decay = (plateau ? d1_time : 0) + (plateau ?
d2_time : d1_time+d2_time) = d1_time + d2_time` either way — so no plateau
detection is actually needed for our model, just an unconditional sum.
A stage-2 rate byte of exactly `0` contributes **true zero** seconds, not
the continuous rate curve's ~31ms floor (`env_rate_to_seconds(0) == 0.031`,
but `writers/e4b_writer.py`'s `env_seconds_to_rate(0.0) == 0` — byte 0 is a
deliberate "unused" encoding) — this keeps the ~98%+ of voices with a real
single-stage envelope byte-for-byte unchanged from the original CR-5
behavior; only genuine two-stage envelopes are affected.

**Verified:** corpus sweep before/after shows **0 crashes**, the exact
"Hollywood" repro now decodes to the envelope above; new regression tests
`tests/test_e4b_parser.py::test_single_stage_envelope_unchanged` (the common
case, unaffected), `test_two_stage_envelope_combines` (synthetic two-stage
case matching CWM's model), `test_stage2_zero_byte_contributes_true_zero`,
`test_real_world_hollywood_sfx_repro` (exact byte repro) — all 4 confirmed to
fail against the pre-fix code and pass with it.

**HARDWARE-CONFIRMED 2026-07-28.** Built a listen-control bank
(`tests/re_banks/gen_e4bread2_listen_test.py`) that patches the *exact* raw
WALKER C1 PZT bytes (Attack1 0/127, Attack2 0/127, Decay1 0/126, Decay2
118/0, Release1 60/0, Release2 0/0) onto a plain 40s held sine tone —
bypassing mpc2emu's own parser entirely, so this tests the E4XT's actual
hardware behavior with zero dependency on whether our fix is right.
Loaded via a ZuluSCSI CD image (`writers/iso_builder.build_iso`) and played
on a real E4XT: **the tone genuinely fades to silence** over the held note
(matching the NEW decay≈29.5s/sustain=0.0 reading), not "holds near-full
forever" (the old, buggy reading). Fix confirmed correct on real hardware —
closing the open TODO item.

### 2. Sample loop fields: right-channel-only samples read the wrong (stale) field

**Symptom:** the E4B sample struct is the Emulator III's, which stores every
position (start/end/loop-start/loop-end) **twice** — once per channel, at
offsets 22/30/38/46 (left) and 26/34/42/50 (right). A sample object holding
only its **right** channel (options bit `0x0020` clear) keeps its real
positions in the second field of each pair and leaves the first with a stale
value that doesn't address this sample at all. `parsers/e4b_parser.py`
always read the left/first field unconditionally.

**Corpus-checked before fixing:** of 7,460 sample objects across the same
141 files, 88 (1.2%) have the option-clear ("right channel") flag, 73 of
those are looped. Reading the **left** field gives an in-range loop point
for 67/73 (91.8%) — but for the other 6 (all in a `"Preview Vol.2"` bank),
it's **negative** (e.g. `loop_start = -40`), an outright invalid value that
can't be right by construction. Reading the **right** field instead gives a
valid, in-range loop point for **all 73/73 (100%)**.

**Fix:** `_parse_sample_body` now picks the loop-field offset based on the
options bit: `38/46` when bit `0x0020` is set (left/mono — the overwhelming
majority, and everything mpc2emu's own writer ever emits), `42/50` when
clear (right-channel-only). The now-unused `end`/`end_l` field (read but
never actually consulted anywhere in the parser — `n_frames` comes from the
PCM length, not this field) was removed rather than also branched, since
nothing reads it.

**Verified:** full corpus re-check after the fix: **0 invalid loop points**
across all 7,460 samples (down from 6). New regression tests
`tests/test_e4b_parser.py::test_stereo_right_channel_loop_fields` (exact
repro: a deliberately-stale negative left field vs. a valid right field) and
`test_stereo_left_channel_loop_fields_unchanged` (confirms the overwhelmingly
common left/mono case is untouched) — both confirmed to fail against the
pre-fix code and pass with it.

**Not related to full stereo support** — mpc2emu's `SampleData`/parser
remain mono-only by design (each E3S1 chunk is still read as one independent
mono sample); this fix only corrects which loop-point *field* is trusted for
a mono-per-object sample, it doesn't add channel-pairing/joining.

## §E4BLEVEL — Amp-envelope sustain LEVEL byte is exponential/dB-law on real hardware — WRITER FIXED + HW-CONFIRMED (2026-07-28)

**Context:** while building the §E4BREAD2 listen-control bank above, a
second calibration reference preset ("SIMPLE REF") was included: an
ordinary envelope through the normal write path, `Envelope(attack=0.5,
decay=2.0, sustain=0.5, release=1.0)`. `models/common.py:env_level_to_byte`
encodes the 0.5 sustain fraction **linearly**: `pct=50 -> round(50*127/100)
= byte 64`, and the parser's inverse (`env_byte_to_level`) reads byte 64
back as `0.504` — self-consistent in software, confirmed by round-tripping
the written file through `parse_e4b` before the hardware test.

**Symptom (hardware-observed):** on a real E4XT, this preset's sustained
portion (after the 0.5s attack, in the middle of the 2s decay-then-hold) was
audible but far quieter than "half volume" — the listener had to raise the
E4XT's own output volume knob from ~45% to 100% (more than doubling the
gain) to hear the sustain clearly. A linear amplitude ratio of 0.5 is only
about −6 dB, which should not require anywhere near a 2x+ gain boost to
become clearly audible.

**Hypothesis:** the EOS envelope LEVEL byte (0-127, used for every
non-terminal stage target — Decay1's level *as read by the old, pre-E4BREAD2
parser*, and both Decay1/Decay2 sustain targets under the new one) likely
does not map linearly onto output amplitude the way `env_level_to_byte`
assumes. Plausible explanations, most likely first:
  - The byte feeds an exponential/dB-law VCA stage internally (common in
    envelope-generator hardware — a linear control value produces an
    exponential *voltage* response), so "50% of the level byte range" is a
    much larger attenuation in dB than 50% of linear amplitude would be.
  - The level scale is itself already a dB or other non-linear percentage
    in the EOS UI, and `env_level_to_byte`'s straight `pct * 127/100` is
    the wrong codec for anything except the two endpoints (0% and 100%,
    which are unaffected either way — this is why every other envelope
    stage in the writer that targets "full" or "silence" is unaffected;
    only genuine partial-sustain presets would sound wrong).

**Scope:** every E4B preset mpc2emu writes with a sustain level strictly
between 0% and 100% is potentially affected — this is a writer-side
calibration gap, independent of the §E4BREAD2 parser fix above (which reads
existing third-party bytes; this is about what byte value we *write* for a
given intended sustain fraction). Filter-envelope sustain uses the same
`_fenv_level` codec and would carry the same risk if `filter_env_amount` is
ever turned up (currently written inert/amount-0 by default, so not
audible today, but the byte would still be wrong if that changes).

**MEASURED 2026-07-28.** Live SysEx parameter-edit automation was tried
first (`tests/re_banks/run_amp_level_cal_sweep.py`, via the sibling
`../eosremote` project) and abandoned after three rounds of incoherent,
non-monotonic results plus one device crash — see the "live automation"
TODO entry and `../eosremote/docs/RESOLUTION_NOTES.md` §14/§15. Switched to
a **file-based bank** instead: `tests/re_banks/gen_amp_level_cal.py` builds
`AMPLVLCAL.E4B`, one preset with 9 voices, each covering exactly one key
(MIDI 48-56) with `Envelope(attack=0.01, decay=0.15, sustain=i/8, release=
0.3)` for `i=0..8` — i.e. the *normal* write path (same mechanism that
already HW-confirmed the §E4BREAD2 fix cleanly, no live parameter edits at
all). Loaded via a ZuluSCSI CD image exactly like the §E4BREAD2 listen
bank; played back with plain Note On/Off (`tests/re_banks/
play_amp_level_cal_notes.py`, MIDI only, no SysEx) while recording
`system:capture_15/16` (the E4XT's audio-in feed) via `ffmpeg -f jack`.

Measured plateau level per note, in dB relative to that note's own attack
peak (`analyze_envelope_recording.py --mode level --fixed-hold 2.3` — the
`--fixed-hold` option was added because the quiet notes fall below the
note-segmenter's gate before the actual note-off, so the plateau window
must be taken from a known fixed duration after the peak, not from the
gate-detected region end):

First pass used broadband RMS and pinned the bottom 3 points (0/12.5/25%)
at an identical -55.4 dB floor — re-checked by re-recording the same bank
at 75% hardware output volume (up from ~50%): the low points got **more**
negative (-67.7 dB), not less, which is the signature of a fixed recording
noise floor (interface self-noise) becoming relatively quieter as the
signal-carrying peak grows with output volume — i.e. those 3 points were
below the recording chain's broadband noise floor, not real measurements,
and the volume knob can't fix that (broadband noise floor is independent
of it, self-normalized dB-to-peak measurement cancels out any actual gain
change).

**Fixed by switching to a narrowband measurement** at the test tone's own
220 Hz (`analyze envelope via FFT bandpass ±15 Hz around 220 Hz`, using a
long ~1.9s window for good frequency resolution, referenced against the
100%-target note's own plateau rather than each note's short attack
transient) — this rejects broadband hiss outside the tone's own frequency
and recovered clean, monotonic data all the way down to 0%:

| target% | measured dB | measured% (linear) |
|--------:|------------:|--------------------:|
|     0.0 |     -99.73  |  0.001 |
|    12.5 |     -90.27  |  0.003 |
|    25.0 |     -70.61  |  0.029 |
|    37.5 |     -58.55  |  0.118 |
|    50.0 |     -46.49  |  0.474 |
|    62.5 |     -35.20  |  1.737 |
|    75.0 |     -23.11  |  6.992 |
|    87.5 |     -10.22  | 30.847 |
|   100.0 |       0.00  |100.000 (reference) |

All 9 points fit a straight line in dB (i.e. the byte really is
exponential/dB-law in amplitude, confirming the hypothesis above)
extremely well:

**`measured_dB ≈ 1.010 × target_pct − 98.74`** (least-squares fit over all
9 points, `R² = 0.996`; fitting only the 25-100% subset tightens further
to `dB ≈ 0.948×pct − 94.15`, `R² = 0.9996` — both describe essentially the
same curve, and either is usable for a fix). This **supersedes** the
first-pass partial fit above (`0.846×pct − 84.13`) — same shape, corrected
slope/intercept now that the low end is real data instead of noise floor.

**Implied fix**, not yet applied — inverting the fit to solve for the byte
value (0-100 sustain%) that a **linear** intended amplitude fraction
`frac` (0.0-1.0) should actually be written as:
`sustain_pct = (20*log10(frac) + 98.74) / 1.010`. Sanity check: `frac=1.0`
→ 100.0% (exact, by construction — it's the reference point);
**`frac=0.5` → 92.9%** (not 50% — confirms the "half volume" bug's
magnitude: to sound like true half-amplitude, the written byte needs to be
~93%, not 50%); `frac=0.1` (−20 dB) → 78.0%; `frac=0.01` (−40 dB) → 58.2%.
This would replace `env_level_to_byte`/`env_byte_to_level` in
`models/common.py` for the **amplitude-envelope sustain field only** — NOT
the rate fields (already separately calibrated and confirmed correct), and
NOT necessarily the filter-envelope sustain (same codec today, but filter
env is written inert/amount-0 by default — needs its own decision, see
Scope above).

**Not yet decided: whether/how to apply this to the parser too.** The
writer-fix question (what byte to WRITE for an intended fraction) is
separate from whether the PARSER's `env_byte_to_level` (used to interpret
third-party E4B files' *existing* sustain bytes) should also switch to this
curve — that would change how mpc2emu interprets every third-party preset's
sustain level, a much bigger blast radius than fixing our own writer.
Needs a decision before implementing, not just a formula.

**HARDWARE-CONFIRMED 2026-07-28.** `models/common.py:env_sustain_to_byte()`
implements the inverted-fit formula above (both endpoints special-cased to
exact byte 0/127); `writers/e4b_writer.py`'s amp-envelope sustain encoding
now calls it. Built `tests/re_banks/gen_hw_confirm_batch.py` ->
`HWCONFIRM.E4B`, 5 keys (48-52) at sustain 0/25/50/75/100% through the
*normal* (now-fixed) writer path, played and recorded on the real E4XT,
narrowband-measured against the 100% key's own plateau:

| target% | measured% |
|--------:|----------:|
|     0.0 |      0.0  |
|    25.0 |     22.7  |
|    50.0 |     45.6  |
|    75.0 |     67.3  |
|   100.0 |    100.0  |

Approximately linear, night-and-day from the pre-fix measurement (a
"linear 50%" target used to measure at 0.47% actual amplitude — see the
measurement above). Small residual deviations (25→22.7, 50→45.6, 75→67.3,
all slightly under target) are consistent with the calibration curve's own
~2 dB fit residual, not evidence the fix is broken. Writer-side fix closed;
the parser-scope and filter-envelope-scope questions above remain open by
deliberate choice, not oversight.

---

## §E4BPARAMHUNT — Live-SysEx parameter hunting: a new, fast method for finding unknown `vpar` bytes (2026-07-28)

**Context:** while chasing the `E4_VOICE_VOLENV_DEPTH` byte for §E4BLEVEL,
realized the sibling `../eosremote` project's editor-protocol SysEx could
be used far more generally — to hunt down *any* currently-unknown `vpar`
byte, not just this one field. This section documents the method (reusable
for future RE) and the full batch of findings from doing it once.

### The method

1. **Set live parameters to distinctive values, don't touch the front
   panel.** `EosBridge.set_parameters([(preset_select, N), (voice_select,
   0)])` then `set_parameters([(param_id, distinctive_value)])`, confirmed
   immediately via `get_parameter` readback. No notes, no bank rebuild.
2. **Save the whole bank to disk once** (a normal front-panel action — RAM
   edits are already "live"/permanent per EOS's own model; there's no
   scripted "save" in the documented protocol, confirmed by grepping
   `eos.messages.Command` for anything save-related — none exists). One
   save captures every preset/voice touched in step 1, however many there
   are — this is what makes batching worthwhile.
3. **Extract the saved bank from the SD card's `HD0.img`.** It turned out
   to be a **plain FAT32 image** (`file` reports `DOS/MBR boot sector...
   OEM-ID "mkfs.fat"`), not the EMU-fs used by CD images/other HDD setups —
   readable directly with **mtools** (`mdir -i HD0.img :: ` /
   `mcopy -i HD0.img "::B.0NN-name.E4B" out.e4b`), no custom reader needed.
4. **Diff the extracted file against a known-clean baseline**, not a raw
   value search. This distinction mattered a lot in practice — see below.

### Value-search vs. diff: value-search produces false positives on
### common/small-range parameters

First pass searched the saved file for each parameter's raw test value
(e.g. is byte `92` present near this voice's data). This worked cleanly for
**wide-range parameters with distinctive test values** (`VOLENV_DEPTH=16`,
`FILT_GEN_PARM1-8=201..208`, `FKEY_XFORM=66` — each a single, unambiguous
match) — but produced **multiple candidate offsets, or an implausible
non-monotonic ordering, for small-range parameters** (`GLIDE_CURVE` 0-8,
`SOLO` 0-8, `LATCHMODE` 0-1): a value like `1`, `3`, or `4` is common enough
elsewhere in the voice block that several unrelated bytes coincidentally
match. **Switching to a direct byte-diff against an untouched baseline
voice/preset resolved every one of these instantly** — exactly one byte
differs, unambiguously, regardless of how "common" its value is. Recommend
diff-first for any future hunt; value-search is only reliable as a quick
first pass for wide-range/distinctive values.

**A related trap: some "found" bytes were really something else entirely,
correlating with preset *index*, not the tested parameter** — e.g. two
bytes that read `0`/`48` in preset 0 and `N`/`48+N` in preset N, for every
N tested, regardless of which parameter was assigned to that preset. These
were something structural (likely a creation-order/slot counter), not
noise to fix, but a reminder to sanity-check that a "changed" byte's new
value actually matches the specific test value set for *that* parameter,
not just "changed at all."

### Findings

All confirmed via the diff method except where noted. `vpar` offsets below
use the established convention (`voice[0:110]`=vpar, PZT starts at
voice-relative 110) — verified to hold for E4XT-native-saved files too (not
just mpc2emu's own writer output) by checking `vpar[2:4]` (`trailer_off`)
lands on a value that divides out to a whole `n_zones`.

See `docs/E4B_FORMAT.md` §4.1's `vpar` table for the full writeup of each
field (`vpar[22]`=RT_LOW, `[23]`=RT_LOWFADE, `[24]`=RT_HIGHFADE, `[25]`=
RT_HIGH — this last one **aliases** the previously-documented "`0x7F`
constant"; `[27]`=Assign Group/choke group; `[28:30]`=Voice Delay, a
big-endian 16-bit word unlike the live protocol's own 7-bit MIDI pairs;
`[33]`=Sample Start Offset; `[37]`=Glide Rate; `[39]`=Solo mode;
`[41]`=Chorus Width, a signed byte (`-100` → `156`, two's complement);
`[44]`=Chorus X; `[50]`=Latch Mode; `[53]`=Glide Curve; `[57]`=Amp
Envelope Depth (the original target — see §E4BLEVEL); `[61]`=VCF
Q/resonance, **also aliases** `FKEY_XFORM`; `[62:70]`=Filter Gen Params
1-8). **Every field in this list is now confirmed by a clean diff against
an untouched baseline** — the last one (Chorus Width) was closed out by
re-diffing a file already on disk from an earlier round, no further
hardware needed.

**Also found, documented in `docs/E4B_FORMAT.md` §4.2 instead of the `vpar`
table:** a third envelope generator, the **Auxiliary Envelope**, at
`PZT[28:40]` — mpc2emu doesn't read or write this at all currently. Its
12 data bytes are ordered by the live protocol's raw `SEG0..SEG5` numbering
(Atk1, Dcy1, Rls1, Atk2, Dcy2, Rls2), **not** the amp/filter envelopes'
phase-grouped file order (Atk1, Atk2, Dcy1, Dcy2, Rls1, Rls2) — a genuine
structural difference between how this third envelope is packed vs. the
other two, confirmed by setting all 12 live ids to distinct values and
reading back the exact byte sequence. Its level bytes go through the same
`round(pct×127/100)` encoding as amp/filter envelope, so likely carries the
same dB-law miscalibration as §E4BLEVEL — unconfirmed for this specific
envelope, not yet acted on.

**Independently re-confirmed** (found via this method, already documented
elsewhere from earlier static-file RE): `LFO2` Lag0/Lag1 at `PZT[57]`/
`PZT[59]` — matches `docs/E4B_FORMAT.md` §4.2's existing entry exactly,
now confirmed via a second, independent method (live SysEx vs. the
original static commercial-bank analysis).

### A useful side-discovery for `../eosremote`, not mpc2emu

While hunting, found that the OLD-format SysEx dump (`dump_preset_old`)
lays out parameters **uniformly, 2 bytes per id, in strict ascending id
order** — `dump_offset = 98 + (param_id − 53) × 2` — verified across a wide
span (ids 53 through 116, crossing the `voice.general`/`.tuning`/`.mode`/
`.amp`/`.filter`/`.lfo` group boundaries without exception, including
right through the `vpar`/PZT structural boundary at id 70). This resolves
eosremote's own long-standing "voice data layout not yet fully
cross-checked" TODO for at least this section of the old dump format —
logged in `../eosremote/docs/RESOLUTION_NOTES.md` and `../eosremote/TODO.md`
instead of here, since it's their protocol layer, not mpc2emu's file
format. **Caveat proven by the Aux Envelope finding above: the dump's own
id-ascending order does NOT necessarily match the file's internal byte
order** (the file groups envelope stages by phase name or `SEG` number
depending on which envelope; the dump doesn't) — so the dump-offset formula
is a fast way to test whether a parameter *exists* and read back its
current value, but the real file offset still needs an independent diff
against a saved file, not an assumption ported over from the dump.

---

## §EIII — E-mu Emulator IIIX/ESI writer+parser (design notes, 2026-07-28)

**Not a bug fix** — this is the "how it works" companion for the new EIII
support (`writers/eiii_writer.py`, `parsers/eiii_parser.py`,
`docs/EIII_FORMAT.md`). See `TODO.md` → "EIII writer needs hardware
confirmation on the E4XT" for what's still open (just the hardware step —
everything below is settled/implemented).

### Model mapping: VoiceLayer -> linked EIII preset chain

EIII presets hold only one primary-layer set of note zones (a preset can
add a *secondary* layer for a 2-layer velocity/crossfade split, and can
`link` to another preset to stack further layers). mpc2emu's `Preset`
already models "more than 2 layers" as an arbitrary list of `VoiceLayer`s.
Rather than trying to pack the first two voices into primary/secondary and
`link` the rest (asymmetric, more code, and ConvertWithMoss's own Creator
doesn't do this either — it never uses the secondary slot), every
`VoiceLayer` becomes its own EIII preset, chained via `link` in order. A
voice's velocity extent (min `lo_vel`/max `hi_vel` across its zones) is
written into that linked preset's *primary* velocity-range field.

**Parser bug found and fixed while writing the round-trip test**
(`tests/test_eiii_roundtrip.py`): the read side initially mirrored
ConvertWithMoss's `Detector.parseLayers`, which only applies a preset's
velocity-range fields when **both** the primary and secondary layers are
populated (a guard against stray leftover range bytes on presets whose
secondary layer was never filled in — see its comment). But that gate means
a primary-only, link-chained preset's velocity range — exactly the
technique both this writer and ConvertWithMoss's own Creator use to stack
more than 2 layers — was silently ignored on read. Fixed in
`parsers/eiii_parser._parse_layers` by applying each layer's own range
unconditionally (`_apply_velocity_range` already no-ops on an unrestricted
range, so this is safe); documented as an intentional divergence from
ConvertWithMoss's Detector in a code comment. This is very likely a genuine
gap in ConvertWithMoss's own round-trip too (not verified against their
code directly — inferred from reading `Emulator3Detector.java`).

### Deliberately NOT translated (no hardware calibration exists)

- **Per-zone LFO** (rate/delay/variation/shape, bytes 9-11/36-39/45): byte
  positions are documented (from emu3bm/ConvertWithMoss) but their value
  scales have never been hardware-calibrated, and ConvertWithMoss's own
  Creator/Detector don't read or write them either. Left at 0 (silent/
  unrouted) on write; not decoded on read.
- **Filter key-tracking / velocity-to-cutoff** (`VoiceLayer.filter_keytrack`,
  `.velocity_to_filter`): these mpc2emu fields are EOS/E4XT mod-cord amounts,
  calibrated against E4XT hardware (`models.common.key_track_to_filter_amount`
  = 0.713 oct/oct at cord amount 1.0, `velocity_filter_depth_to_amount` = 9120
  cents at full scale) — that calibration is meaningless for EIII's
  differently-scaled, differently-shaped DSP, and no EIII hardware
  calibration exists. Writing a guessed conversion risked shipping filters
  that audibly mistrack on real hardware, which is strictly worse than
  leaving tracking neutral. `writers/eiii_writer.py` writes byte `0`
  (literal neutral under the format's own documented -127..127 scale) for
  `ZONE_VCF_TRACKING`, **not** ConvertWithMoss's `NO_VCF_TRACKING = 0x40`
  constant — that constant round-trips to ~full positive tracking through
  ConvertWithMoss's own Detector formula (`byte/127.0*2.0`), which looks like
  a latent inconsistency in their code between the Creator's bypass value and
  the Detector's inverse (see the `_ZONE_TRACKING_NEUTRAL` comment in the
  writer for the arithmetic). mpc2emu's writer+parser pair is self-consistent
  under the documented scale regardless of which reading of ConvertWithMoss's
  constant is "right".

### Real-world validation (read side)

`parsers/eiii_parser.py` was run read-only (no assertions beyond "doesn't
crash, structure looks sane") against every EIII/EIIIX/ESI bank identifiable
by its 16-byte header magic across 17 commercial E4XT library CD-ROM `.iso`
images in Jan's local collection
(`/home/lentferj/Dokumente/SYNTHS/E4XT/{*.ISO,ISO-Images/*.iso}`) — banks
were located by scanning each ISO's raw bytes for the three identifier
strings (`EMULATOR THREE `, `EMULATOR 3X    `, `EMU SI-32 v3   `) and slicing
from each match to the next (or a 130 MB cap), since these commercial disc
images don't need their EMU3/ISO9660 filesystem parsed to locate bank
boundaries this way. **Result: 1118 banks, 19,040 presets, 33,614 samples,
250,236 zones, zero parse failures.** Spot-checked decoded PCM (peak/RMS,
e.g. a "STRANGELOVE" bank from the Depeche Mode/Alan Wilder EIII CD-ROM
decoding to a plausible layered stereo pad with sane sample rates and loop
points; an "OrbitPercMasterX" bank — the same "Orbit Presets" library
ConvertWithMoss's own format doc cites for the ESI sample-index-flag finding
— decoding to real-looking drum one-shots) confirms plausible, not
necessarily byte-perfect, decoding; this is corpus-scale structural
validation, not a hardware playback test. The one-off scan script isn't
checked in (ad hoc, paths are Jan's local collection) — re-derive from this
note if needed again.

### Bank-format scope

Only `EMULATOR_3X` (`.e3x`) and `ESI_32_V3` (`.esi`) are write targets
(`writers.eiii_writer.BANK_FORMATS`), matching ConvertWithMoss's own
`Emulator3CreatorUI` (`EMULATOR_THREE`'s compact, address-biased layout is
explicitly excluded from its `TARGET_FORMATS` too). `EMULATOR_THREE`
(`.e3b`) is read-only (`writers.eiii_writer.ALL_BANK_FORMATS`, used by
`parsers/eiii_parser.py`) — validated structurally by 34 real `.e3b` banks
in the corpus above, all parsed cleanly.

### Hardware confirmation — DONE 2026-07-28 (E4XT, via its EIII compatibility loader)

First real hardware attempt found and fixed a bug before ever reaching the
per-preset checklist: the E4XT reported the loaded bank as `Type: E4BANK` /
"Unknown file type" instead of recognizing it as EIII content. **Not an
EIII bank-format bug at all** — the EIII byte layout was fine. Root cause
was one level down, in the shared EMU3 filesystem wrapper:
`writers/iso_builder.py`'s dir-content entry `props[5]` field was hardcoded
to `\x00E4B0` (the E4B marker) for every bank unconditionally, harmless
while this project only ever wrote E4B, but wrong now that `.e3x` banks
share the same builder (`docs/EIII_FORMAT.md`'s own "bank-format-agnostic"
claim turned out to need one more layer of nuance).

Checked against 5 real commercial EMU3-filesystem discs
(`docs/EMU3_ISO_FORMAT.md` §2.4, read directly with a throwaway inspection
script against `/home/lentferj/Dokumente/SYNTHS/E4XT/ISO-Images/`, known-good
media Jan pointed at): E4B entries always carry `props = \x00E4B0`
(`Post Industrial Cybr-Sound Depot.iso`, every bank); EIII entries always
carry all-zero, across all three on-disk variants (`E-MU Formula 4000 Series
Vol. 5 – Protozoa.iso`: `EMULATOR 3X`/`EMU SI-32 v3` entries; `Vol. 1 –
Emulator Standards.iso`: `EMULATOR THREE` entries) — a clean, consistent,
never-mixed pattern. Since the E4XT's own file browser evidently reads this
field to label a catalog entry (not just a third-party reader classifying
someone else's disc, which was the narrower claim the field was originally
documented under), writing the wrong marker actively misidentifies the bank.

Fixed: new `_bank_props(path)` in `writers/iso_builder.py` peeks at each
bank's own first 4 bytes (`FORM` -> E4B marker, anything else -> all-zero)
when building a dir-content entry, wired into both write paths (`_dircon_block`,
used by `build_iso`/`build_emu_hdd`, and the inline entry-write in
`emu_hdd_append`). Keeps the module's bank-format-agnostic design intact —
no caller needs to pass a type flag. Verified E4B output is byte-identical
to before (still `\x00E4B0`); new regression test
`tests/test_iso_builder_props.py` (direct `_bank_props()` cases + an
end-to-end `build_iso()` check for both formats).

`EIIITEST.iso` regenerated with the fix and copied onto the ZuluSCSI SD card
as `CD1-EIIITEST.iso`, replacing the mis-tagged one. **Reloaded on the E4XT
and hardware-confirmed 2026-07-28** by Jan: the props fix resolved the
misidentification and the bank now loads correctly as EIII content. This
closes the EIII hardware-confirmation TODO item.

## §CWM-LFOVOL — SFZ/SF2 volume LFO (tremolo) reading, read-side only (2026-07-28)

**Context:** cross-referencing ConvertWithMoss PRs
[#216](https://github.com/git-moss/ConvertWithMoss/pull/216)/[#233](https://github.com/git-moss/ConvertWithMoss/pull/233)/[#239](https://github.com/git-moss/ConvertWithMoss/pull/239)/[#240](https://github.com/git-moss/ConvertWithMoss/pull/240)
(see `TODO.md` for the summary). Both `parsers/sfz_parser.py` and
`parsers/sf2_parser.py` already read pitch-LFO (vibrato) and filter-LFO into
`VoiceLayer.lfo1_*`/`lfo2_*`, but neither read a volume-LFO (tremolo).

### Format shapes differ

- **SFZ v1** treats `pitchlfo_*`, `fillfo_*`, `amplfo_*` as three fully
  independent oscillators (v2 equivalents: `lfo0N_pitch`/`lfo0N_cutoff`/
  `lfo0N_gain` opcodes on arbitrary-numbered LFO blocks). Three oscillators
  don't fit mpc2emu's two hardware-matched LFO slots.
- **SF2** (`Generator.java` in CWM, confirmed via `git show 5e868c6`) has
  generator id `13 = MOD_LFO_TO_VOLUME` (unit: centibels, i.e. 0.1 dB) living
  on the *same* "Mod LFO" oscillator as generator `5 = modLfoToPitch` and
  `10 = modLfoToFilterFc` — SF2's own convention already collapses
  pitch+filter+volume onto one oscillator, which maps naturally onto
  `lfo1_*` with no fallback logic needed (unlike SFZ).

### Model additions (`models/common.py`)

```python
LFO_VOLUME_FULL_DB = 24.0   # NOT hardware-calibrated -- see below

def lfo_volume_depth_to_amount(db: float) -> float:
    return max(0.0, min(1.0, abs(db) / LFO_VOLUME_FULL_DB))
```

Plus `lfo1_to_volume`/`lfo2_to_volume: float = 0.0` fields on `VoiceLayer`.

`LFO_VOLUME_FULL_DB` follows the precedent of `LFO_PITCH_FULL_CENTS = 1593.0`
(hardware-measured via MOD_DEPTH_CAL on the E4XT, 2026-06-12) but **has no
equivalent measurement** — there's no tremolo-depth calibration bank on
record. 24 dB is a plausible placeholder (a full-swing tremolo audibly
silencing a sound), not a measured value. Flag this if it ever needs to be
precise.

### SFZ fallback logic (`parsers/sfz_parser.py`)

```python
a_depth = _f('amplfo_depth') or _f('lfo03_gain') or _f('lfo02_gain') or _f('lfo01_gain')
a_freq  = _f('amplfo_freq')  or _f('lfo03_freq') or _f('lfo02_freq') or _f('lfo01_freq')
if a_depth:
    if not lfo2_claimed:
        params['lfo2_rate']      = a_freq if a_freq else 5.0
        params['lfo2_shape']     = _sfz_lfo_wave(merged.get('lfo02_wave'))
        params['lfo2_to_volume'] = lfo_volume_depth_to_amount(a_depth)
    elif not p_depth:   # LFO1 only free if no pitch-LFO already claimed it
        params['lfo1_rate']      = a_freq if a_freq else 5.0
        params['lfo1_shape']     = _sfz_lfo_wave(merged.get('lfo01_wave'))
        params['lfo1_to_volume'] = lfo_volume_depth_to_amount(a_depth)
```

Claims LFO2 if the filter-LFO block hasn't already claimed it; else claims
LFO1 if the pitch-LFO block hasn't; else the tremolo data is dropped
(no third slot to put it in, and overwriting an existing pitch/filter LFO
would be worse than losing the tremolo).

### SF2 addition (`parsers/sf2_parser.py`)

```python
mod_volume_cb = ig_dict.get(13, {}).get('amt', 0)
if mod_pitch or mod_cutoff or mod_volume_cb:
    ...
    if mod_volume_cb:
        voice.lfo1_to_volume = lfo_volume_depth_to_amount(mod_volume_cb / 10.0)
```

Centibels -> dB is `/10.0`.

### Verification

New `tests/test_lfo_volume.py` (plain-python `check()`/`main()`, matching
project convention — no pytest): depth<->amount conversion (0 dB -> 0.0,
full-depth -> 1.0, sign-independence, clamping); SFZ claims-LFO2 (no filter
LFO present); SFZ falls-back-to-LFO1 (filter LFO already on LFO2, no pitch
LFO); SFZ drops-when-both-slots-taken (pitch on LFO1, filter on LFO2). All
pass. SF2 path verified only by `python3 -c "from parsers.sf2_parser import
parse_sf2"` (imports cleanly) plus structural review against the
already-working pitch/filter reading pattern — no binary SF2 fixture was
built, since no existing SF2 test file exists to extend.

### Writer side: deliberately NOT wired (open, blocked)

Neither `writers/e4b_writer.py` nor `writers/krz_writer.py` has a
hardware-confirmed "LFO->Volume" mod-destination byte documented anywhere
(`docs/E4B_FORMAT.md`, `docs/KRZ_FORMAT.md`) — `e4b_writer.py`'s
`_extra_cords` list only routes LFO1 to Filter-Freq (`0x38`)/Filter-Q
(`0x39`)/Pitch (`0x30`); `krz_writer.py` only wires `lfo1_to_pitch` via
`CAL[21]`/`CAL[22]`. Checked ConvertWithMoss's own
`Emulator4Constants.java` for a matching destination constant
(`grep -n "VOLUME|0x36|AMP_"` — no hits): their own Emulator4/Kurzweil
writers don't implement LFO->Volume output either, only for SFZ/SF2/DLS/
DecentSampler targets, which don't need a byte-level hardware destination.
Guessing a destination byte risks misrouting modulation onto some other,
unintended parameter in a real E4B/KRZ file — worse than the read-only gap
this closes. Blocked on: live-SysEx parameter-hunting (same method as
§E4BPARAMHUNT) to find the real E4B cord-destination byte for Volume, and
the equivalent K2000 `CAL[]` byte, before either writer can consume these
new `lfo1_to_volume`/`lfo2_to_volume` fields.

Also noted, bigger and out of scope here: `parsers/gig_parser.py` has no
LFO support at all (pitch, filter, or volume).

## §EIII-CWM — Five reader gaps found cross-referencing ConvertWithMoss (FIXED 2026-07-29)

**Context:** ConvertWithMoss landed ~38 commits in 48 h, nearly one per
format it supports. Reviewed the subset touching formats mpc2emu also
reads (the rest — Kontakt, Roland, Tonverk, 1010music, QPAT, YSFC, Korg,
Deluge, Renoise, TX16Wx, Ensoniq, Maschine, DLS, NN-XT, DecentSampler,
Disting — are formats we don't touch). Four of their PRs revealed real
gaps on our side; the rest we either already handled correctly or had
deliberately diverged from. Commits `ea74e45`/`d0ed2cc`/`ad4c80e`/
`6c463c4` plus our own follow-up `5900560`.

**Checkpoint for the next round:** the last CWM commit reviewed is
`9443b635` (2026-07-29). Diff from there rather than a `--since` window.

### What was already right (no action)

Worth recording, since re-checking these each round is wasted effort:

- **EIII parked-filter / tracking-neutral byte** (their #245): already
  fixed here independently, and `writers/eiii_writer.py` carries the
  `_ZONE_TRACKING_NEUTRAL` note explaining why we write `0` rather than
  their `NO_VCF_TRACKING = 0x40` — see §EIII.
- **E4B envelope decay1/decay2 + channel-paired loop** (their #242):
  already fixed, same "Nylon Guitar" case — see §E4BREAD2.
- **Volume LFO / tremolo** (their #240): already read — see §CWM-LFOVOL.
- **Sample-file root-note priority** (their #281): `sampledir_parser.py`
  already prefers the embedded `smpl` root over the filename.
- **TAL volume default** (their #276): already written unconditionally.
- Their EXS24 (#261) and SFZ (#278) fixes are **writer-side**; mpc2emu
  has no EXS24 or SFZ writer, so they don't apply.

### The four fixes

1. **SF2 static filter + preset-level generators** (their #255). Gen 8
   `initialFilterFc` / gen 9 `initialFilterQ` were never read — every
   other reader we have models a static filter, SF2 alone didn't. And a
   preset zone with no gen 41 is SF2's *global zone*, whose generators
   are additive offsets over every instrument zone beneath it (spec
   §8.1.3); only gen 41 itself was being read. Also picked up gen 48/51/52
   (attenuation, coarse, fine) into the `ZoneMapping` fields that already
   existed for them.

2. **EIII filter bypass** (their #248). The bypass test compared the
   cutoff byte to `0xEF` exactly — our own writer's `DEFAULT_CUTOFF`.
   Every byte from `0xD5` up is already past 20 kHz, so third-party banks
   parking the filter elsewhere got a spurious filter object. Now tested
   against `E4B_CUTOFF_MAX_HZ`. Corpus check: 130,473 zones qualify as
   inaudible-with-zero-Q, and **69,981 of them (>half) used a byte other
   than `0xEF`** and were mis-read.

3. **EIII truncated sample indices** (their #252). See
   `docs/EIII_FORMAT.md` for the format-level writeup. Mastering-tool
   artifact of specific library CD-ROMs, *not* a hardware/format bug —
   which is why it survived 25+ years unreported. Ported their
   `Emulator3SampleIndexRepair.java` faithfully (same scoring
   thresholds); the thresholds are what stop it mis-repairing a correct
   preset, so they are not to be "simplified" without re-running the
   corpus.

4. **WAV `smpl` MIDIPitchFraction** (their #254). Only `MIDIUnityNote`
   was read, so embedded fine-tune rounded to the nearest semitone.

### Corpus validation method (reusable)

The EIII work was validated by scanning **1118 real EIII/EIIIX/ESI banks**
out of 22 commercial CD-ROM `.iso` images in Jan's collection
(`~/Dokumente/SYNTHS/E4XT/{*.ISO,ISO-Images/*.iso}`), located by scanning
raw bytes for the three identifier strings and slicing to the next match
— the same technique §EIII used. Result: **4144 sample-index references
repaired across 771 presets, zero parse failures.**

A **decision-branch census** (instrumenting `_choose_repair_candidate`)
answered whether any of the heuristic is dead weight:

```
3073  kept stored (no repair)
 495  gate: decisive (pitch ladder)      395 of them decisive-only
 219  gate: affinity_decisive (name only)
 137  gate: perfect_small (<=2 zones)
  30  via affinity override (pitch too weak)
 200  repairs REQUIRED a non-pitch gate
```

So the preset-name affinity machinery carries ~30 % of repaired presets;
deleting it to shorten the port would have silently lost 200 repairs.
**Don't strip it.**

Spot-check that the repairs are real rather than merely plausible: an
`apo:PlusDXep` preset resolves to `C3Yamaha` F0/C1/Gx1/Dx2/Gx2/Dx3/A3/D4/
Gx4/Cx5/G5 and `TinePiano` G2/G3/G4 — an ascending ladder matching the
zones' own keys — where the stored indices pointed at unrelated `OB 1 G1`
and `B3LoDistSlow*` samples.

### Performance note

The faithful port was profiled afterwards (`5900560`): `_repair_affinity`
was **63 % of the whole repair pass**, because sample-name normalization
ran per (preset × candidate) instead of once per bank — 37,470 calls on a
bank holding 738 distinct names. Hoisting that, plus two provable no-op
short-circuits, cut the pass ~1.8× with byte-identical output (re-verified
at 4144/771 over the full corpus). General lesson, third time in this
project: **the hot spot in a ported heuristic is almost always repeated
string normalization in an inner loop, not the algorithm itself.**

### Not fixed — reference only

- EIII per-zone **vibrato** (their #284) and **chorus-as-detuned-voice**
  (their #285): not modelled by mpc2emu; would need the per-zone LFO
  bytes §EIII deliberately leaves alone (no hardware calibration).
- EIII **floppy disk sets** (their #237): `ALL_BANK_FORMATS` covers
  SCSI/hard-disk bank files only, not raw floppy memory dumps.
