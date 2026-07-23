# mpc2emu — Open Items

## K2000R "Object → Delete" LOCKUP (OPEN, 2026-06-25) — needs factory resets

Deleting a program loaded from a converted KRZ locks up the K2000R (~2 factory-reset
cycles to recover). **Status: unresolved, paused mid-investigation.** Full detail in
the `project_k2000_delete_lockup` memory.

Key points: isolated to deleting a PROGRAM object (keymap-only delete is clean);
**reproduces on REAL soundsets** (Monotanz `acguit`, authored `SYNTHEX_1`) — so likely
**K2000-side, not our converter**. Our program/keymap/sample objects are byte-for-byte
valid vs real banks (DFLT/CUTLO/xprogs4/SYNTHEX/PMVOL). Leading theory: deleting a
program loaded **individually** (partial dependency chain) corrupts the K2000 object
table. Open: confirm whole-bank-load deletes are reliable; test `PPNOLOOP.img`; check
OS version / another unit. Uncommitted `_build_keymap_entries` gap-fill (sampleId=0)
did NOT fix it — reconsider reverting. See memory for tests, artifacts, next steps.

## Code-review findings (2026-06-10) — high-effort multi-agent review

**Status: ALL RESOLVED (2026-06-10 → 2026-06-12).** CR-1 through CR-18 are all
fixed & pipeline-verified, or marked false-positive / N-A (CR-11b, CR-18 #2).
No open code-review items remain — this section is kept as a record only.
Fix strategies + patches in `docs/RESOLUTION_NOTES.md` §CR (Code Review).

**Resolved 2026-06-10:** CR-2, CR-4, CR-5, CR-8, CR-9, CR-11, CR-12 — fixed &
pipeline-verified. **CR-11b — FALSE POSITIVE** (MPC2000 sample-index 0 *is* the
"unassigned" sentinel: `names[0]=''`, 50/64 pads use it; the `0 < sn` guard is
correct). **Resolved 2026-06-11:** CR-3 — `write_talsmpl` rewritten to the real
TAL v11 schema (clones a full default `<program>` from `parsers/tal_template.py`,
overrides only modelled attrs; external-WAV refs); write→parse round-trip
lossless. **TAL-Sampler load test PASSED 2026-06-11** (real MPC drum kit) —
uncovered & fixed 5 more writer bugs (`<programs>` wrapper, layer bin-packing,
`track`/`stereoinverse`="0" for one-shots, neutral filter, CRLF); only the
absolute volume/cutoff law approximations remain — see
`docs/RESOLUTION_NOTES.md §CR`. **Also 2026-06-11:**
CR-1, CR-10, CR-11c — KRZ writer: one keymap + one layer per voice (no more N×
stacking; per-layer key/vel range so velocity layers modelled as separate voices
now split correctly); loop end written as `sampleEnd`; ping-pong baked like
`write_e4b`. See `docs/RESOLUTION_NOTES.md §CR`. **Also 2026-06-11:** CR-6
(zone-reducer overlap guard) and CR-7/7b/7c (sample-name collisions) — fixed &
verified. See `docs/RESOLUTION_NOTES.md §CR`.

**All P0 code-review items are now resolved.**

---

## KRZ: program parameters — FILTER + ENVELOPES + LFO IMPLEMENTED (2026-06-15)

`writers/krz_writer.py` now clones the K2000 #199 "Default Program" template
(`_TPL_GLOBAL`/`_TPL_LAYER`, RE'd via Gotek disk-save — see
`docs/re_procedures/krz_program_re.md` §16) and patches per-voice values:
**4-pole lowpass (cutoff+resonance), amp envelope, filter envelope, LFO1 vibrato.**
All round-trip-verified against the file format. **HW load-test DONE 2026-06-16**
(converted MPC banks on the K2000R) → found+fixed two writer bugs (doc §17c):
one-shot samples were force-looped (loop bit is 0x80: clear=on; fix `0x70 if
looped else 0xF0`), and MPC Velocity→Filter was ignored, muting Cutoff=0 basses
(fix: fold `velocity_to_filter` into the effective cutoff).

### Feature gaps — input features we cannot yet map to KRZ (TODO)

**Filter — highpass / bandpass / notch now IMPLEMENTED (2026-06-16).**
- **HW-VERIFIED via floppy demo banks 2026-06-21** (by-ear, Jan): all four
  filter-type demos read correctly on the K2000R — filter-TYPE *and* cutoff-Hz
  mapping confirmed on hardware (not just round-trip):
  - `4PoleHP` (Synth-Pulse-Synt, src FilterType=7, Cutoff=0.41) → **4-pole
    high-pass @ ~330 Hz**
  - `2PoleBP` (Synth-MS20-Patch, FilterType=11, Cutoff=0.46) → **band-pass @ ~466 Hz**
  - `Notch` (Synth-MS20-Patch, FilterType=18, Cutoff=0.04, Resonance=0.89) →
    **Double Notch w/SEP, FRQ Coarse 22 Hz**
  - (1PoleLP / Bass-Pulse-Bass verified separately — see the floppy clamp item.)
  The three cutoff points (0.04→22, 0.41→330, 0.46→466 Hz) lie on one exponential
  curve → the **Cutoff-Hz mapping is faithful**, confirming the §"sonically
  CONFIRMED" note below with explicit Hz readouts.
- Filter-type bytes hardware-RE'd from `FILTERS.KRZ` (K2000R disk-save of progs
  312-315) and wired into `writers/krz_writer.py` (`_k2_filter_byte` +
  `_patch_layer`): `HOB0[0]` = **LP 50, HP 54, BP 55, NOTCH 56, NONE 62**.
  XPM `filter_type` families map: Low/Model/MPC→LP, High→HP, Band/Band-boost→BP,
  BS notch→NOTCH. End-to-end round-trip verified (write_krz → krz_reader).
- Remaining lossiness (acceptable): K2000 has one slope per family, so multi-pole
  source variants (2/4/6/8-pole) collapse onto the single 4-pole type; Vocal
  formant sources (XPM 26-28) have no Algorithm-1 analogue → fall back to LP.
- Cutoff (signed semitones) + resonance (`round(dB×2)`) encodings are
  sonically CONFIRMED on hardware (centroid tracks cutoff; resonant-peak boost
  ≈ display dB). Cutoff Hz curve is faithful, not just an approximation.

**Modulation routings (mod wheel / pressure / velocity / keytrack)**
- **Routing byte OFFSETS now located** (2026-06-16, doc §17k) by corpus analysis of
  14212 real layers: filter Src1=HOB0[5]/depth[6] (ENV2 filter-env — implemented),
  filter Src2=HOB0[7] (velocity=100/mod-wheel=1 go here), amp Src2=HOB3[7]
  (vel/mwheel→amp), amp LFO=HOB3[10] (tremolo), pitch Src CAL[21]/[26] (vibrato).
  Control-source CODES all known from the manual (doc §17e). **Remaining blocker for
  implementing any of these: the depth byte↔(cents/dB) calibration** — needs HW
  (disk-save or audio-rig at known displayed values; the F1 Src-depth range is
  ±10800 ct but the byte curve isn't pinned).
- **Mod-wheel → vibrato depth** and **mod-wheel → filter** (very common in sources). NOT mapped.
- **Velocity → filter cutoff** (`velocity_to_filter`): partially mapped 2026-06-16 —
  folded into the static effective cutoff (`min(1, cutoff + velocity_to_filter)`),
  HW-validated against the MPC ("VelToFilter pushes cutoff up very far"). A true
  per-note VelTrk sweep is deferred (VelTrk located on the F1 page; a sweep from the
  16 Hz floor would re-mute soft notes). **Velocity → amp**: still NOT mapped.
- **Keytrack → filter** (`filter_keytrack`). NOT mapped.
- Aftertouch/pressure routings. NOT mapped.
- (These all live as source+depth on the function pages / CAL, like the two we
  decoded.  **Control-source CODES are now all known** from the manual (doc §17e),
  validated against RE: AttVel=100, MWheel=1, MPress=33, PWheel=35, KeyNum=98,
  LFO1=114, LFO2=116, ENV2=121, ENV3=122, AMPENV=120.  Only the per-page Src/Depth
  byte OFFSETS + depth calibration still need a disk-save.)

**Filter slope — 2-pole lowpass IMPLEMENTED (2026-06-16, doc §17g).** Low1/Low2 now
map to the K2000's gentler 12 dB 2POLE LOWPASS (Algorithm 3) instead of the 24 dB
4-pole. Decoded from POLE2LP.KRZ: only 3 bytes differ from the 4-pole path
(HOB0[0]=2, HOB2[0]=39 BAL, CAL[29]=3); same layout, no separate template.
`_k2_filter_plan` in krz_writer; byte-exact to HW #320/#322. Still 4-pole (2-pole
bytes not yet RE'd): High1/2, Band2, notch — another disk-save batch if wanted.

**Envelopes**
- **Pitch envelope (ENV3)** — segment + encoding known, not yet wired.
- Only ADSR; source **delay/hold** (DAHDSR) stages dropped.
- Filter-env depth + LFO→pitch depth are **approximate** (2-point linear fits;
  need a low-end data point for exact cents).

**LFO**
- **LFO2** (second LFO) not written (only LFO1).
- **LFO → filter** (filter wobble) and **LFO → amp** (tremolo) not mapped (vibrato only).
- LFO **delay/fade-in**, **tempo-sync**, **MxRate** not mapped.
- **LFO shapes — DONE 2026-06-17** (live K2000R SysEx probe): all 26 shapes
  mapped (0=Sine…4=Triangle…6=Rise…8=Fall…20=8 Step). `_LFO_SHAPE` updated.

**Other**
- **Pan** (per-zone) not mapped to the K2000 pan (F4/output).
- Velocity → pitch.

---

## KRZ: fidelity gaps found via ConvertWithMoss cross-reference (OPEN, 2026-07-22)

ConvertWithMoss (git-moss) added a KurzFiler-derived K2000/K2500/K2600 reader+
writer in 2026 (`format/kurzweil/`, not HW-tested). A full byte-level compare
against `krz_writer.py` found **nothing to learn on the VAST program side** (we
decode filter/env/LFO; CWM writes a flat default program — and in two spots CWM's
writer is *wrong* where ours is HW-corrected: it writes `LYR[6]=hiVel` when that
byte is the Enable source, and writes the keymap id into `CAL[7,8]` which silences
4+-layer programs). The gaps run the **other** way — container/keymap/sample-header
fidelity we don't yet emit. Fix recipes in `docs/RESOLUTION_NOTES.md` §KRZ-CWM.

- **Per-sample gain — DONE + HW-CONFIRMED (2026-07-23).** `Soundfilehead.volumeAdjust`
  (byte 2) is a signed i8 in **0.5 dB steps**; `write_krz` now aggregates the
  referencing zones' `ZoneMapping.volume` (mean) per sample and `_write_sample_object`
  writes `round(gain_dB × 2)` (`_vol_adjust_byte`, clamped ±i8) into volumeAdjust +
  altVolumeAdjust. 0 dB → 0, so unity banks stay byte-identical (HW-verified filter
  floppies unaffected). **HW check on the K2000R** (`tests/re_banks/gen_volume_adjust_test.py`
  → `VOLADJ` floppy): three constant-pitch key-blocks at 0/−6/−12 dB stepped down in
  loudness exactly as intended → the K2000 honours the field and the 0.5 dB/step scale
  is right. (Note: K2000 labels middle C = MIDI 60 as **C3**; our `_note_name` uses the
  C4=60 scientific convention — a one-octave display-only difference, no byte impact.)
- **Partial key-tracking not expressible.** `_build_keymap_entries` writes a
  *constant* per-zone tuning → implicitly 100 % chromatic tracking. A source with
  reduced/zero key-tracking (drum maps) needs the per-key form
  `round((keyTracking − 1)·(note − rootkey)·100) + fine_tune`. *Blocked on:* a
  source that actually carries a keytrack ≠ 1 to test against.
- **Native 8-level multi-table keymap not used.** The K2000 keymap `Level[8]`
  can address up to 8 velocity tables in *one* keymap (level `j` = velocity
  `j·16…+15`). We instead split every velocity band into a separate keymap +
  program layer (`_split_voice_by_velocity`), which burns layers against the
  32-layer cap and the "3 regular layers" rule. Adopting the native form would
  fold velocity layers back into one keymap. *Blocked on:* design decision +
  HW confirm (larger change; weigh against current layer-splitting, which is
  HW-verified). Bit-layout HW-documented but the multi-table write path is untested.
- **Stereo / multi-root sample objects.** We emit mono, single-header only. The
  generalization is `numHeaders = N−1`, `flags` bit 0 = stereo (L/R header pairs,
  even index = left), and envelope offsets `(numHeaders−1−i)·32 + 8/+6` instead
  of the hardcoded `8/6`. *Blocked on:* stereo handling is a broader converter
  feature; HW confirm needed.
- **Doc-only:** our `hash >> 10` object-type decode mislabels the FX/song/QA
  objects (types > 42 use the 8-bit `hash >> 8` decode when the 0x8000 bit is
  clear). We never emit them, so this only matters for a future reader — noted in
  `docs/KRZ_FORMAT.md` §2.2. Also verify the entry-index base: CWM places entry
  `i` at note `i+12`; we index entries by raw MIDI note (ours is HW-confirmed to
  play, so this only bites an external reader of our files).

---

## KRZ: program parameters (envelopes / filter / LFOs) — OPEN (2026-06-14)

**Status:** strategy + tooling complete; hardware RE not yet started.
**Blocked on:** hardware iteration on the K2000R (and, ideally, a PC↔K2000R MIDI
link to enable the scripted-SysEx approach — open question for Jan).

We can convert sample mapping + tuning to KRZ (HW-confirmed sounding) but **not**
envelopes / filter / cutoff / resonance / LFOs the way the E4XT path does. We
have the program object's *structure* (segment skeleton, the Algorithm-1
`PITCH → 4POLE LOPASS W/SEP → AMP` target, the uniform 4×HOB DSP-function-page
layout) but not the *byte semantics* — those need RE.

The plan, three RE strategies (scripted SysEx / forward-RE test banks /
create-on-HW + diff), per-parameter checklists, the corpus analysis, and the
full toolkit are in **`docs/re_procedures/krz_program_re.md`**. New tools:
`tests/re_banks/krz_reader.py`, `gen_krz_program_re.py`, `krz_sysex_probe.py`.
Start with the **amp envelope** (`KRZ_ENVLOC` bank, no MIDI needed). The 64 MB
K2000 sample-RAM ceiling is already enforced (`convert.py` clamp + splitter).

Resolution strategy + open questions: `docs/RESOLUTION_NOTES.md` §KRZ-PROG.

---

## KRZ: converted banks load but emit NO SOUND — RESOLVED (2026-06-14)

Converted KRZs (ABASBASS / BLKSAW / SF2SET) loaded on the K2000R and created
their presets, but **played silent**, while pre-existing soundsets played fine.
Root-caused against KurzFiler source (`/home/lentferj/git-repos/kurzfiler`) +
ground-truth dumps of real RAM-sample soundsets (Patchman `PMVOL002.KRZ`). The
sample/keymap/program *framing* was already byte-correct; the bugs were all in
**sample header field values** the program-only test banks never exercised:

1. **Soundfilehead.flags = `0x40` → must be `0x70`.** This is THE silence cause.
   `0x40` is needsLoad alone; a playable RAM sample needs the `0x10`+`0x20`
   playback-enable bits too (`LoadWaveMethod` always writes `0x70`). `0x40` loads
   the sample but produces no output.
2. **KSample object `flags` = `0x40` → must be `0`** (bit0 = stereo; `0x40` is
   meaningless) and **`baseID` = obj_id → must be `1`** (every real soundset).
3. **Keymap entry `tuning` double-counted the per-key transposition.** Old:
   `100*(root−12−key)` for every key — but the K2000 already transposes each key
   from the sample rootkey + `centsPerEntry=100`, so high keys hit −72 semitones
   (out of range → also silent). Fixed to a *constant* per-zone offset
   `100*(R_sample − R_zone) + fine_tune` (0 in the common case).
4. **`altSampleStart`** was loopStart → must equal `sampleStart` (real files).
5. **`maxPitch`** formula corrected to `100*root + 1200*log2(48000/sr)` (the
   48 kHz transpose ceiling; RE'd from PMVOL002).

Fix in `writers/krz_writer.py` (`_write_sample_object`, `_build_keymap_entries`,
`_compute_max_pitch`). Verified structurally identical to real soundsets with
the new `krzdump.py` reader. **HW-CONFIRMED 2026-06-14:** ABASBASS_01.img loaded
on the K2000R via Gotek — all 5 presets play sound. See `docs/RESOLUTION_NOTES.md`.

---

## Aural-comparison fidelity (2026-06-13) — see `docs/aural_notes.md`

By-ear A/B of converted E4XT presets vs MPC originals.

**Implemented (no RE):** LFO rate curve (§C), root-from-WAV-unity / +36 fix
(§E/§F), filter-env always written (§O), S&H→Hemi-quaver (§Q), ODS mapping (§N).

**Implemented from RE_SUITE2 hardware data (2026-06-14); verified on the E4XT
via `VERIFY_emu.hda`:**
- **Voice key-window (§G) — DONE + HW-CONFIRMED.** `vpar[14]`=key low,
  `vpar[17]`=key high (were 0/127 = C-2..G8); writer sets them from each voice's
  min/max zone key. HW: C2–C3 sample → B1↓ silent, C2–C3 sound, C#3↑ silent.
- **Band-stop → Swept EQ 1-oct (§K/§L) — DONE + HW-CONFIRMED.** `vpar[58]=0x20`,
  `vpar[60]`=freq (cutoff law), `vpar[61]`=gain where **gain_dB=(byte−64)×0.375**
  (byte 0=−24 dB cut). MPC band-stop (15-18) → 0x20, cut depth −12..−24 dB from
  resonance. HW: band-stop preset reads as Swept EQ cut.
- **Triangle phase (§S) — DONE + HW-CONFIRMED.** E4XT triangle rises first;
  MPC falls first → writer negates a triangle LFO's cord amounts (all dests).
  HW: triangle LFO→pitch (rate 0.08 Hz) sweeps down first.

- **Tempo-synced LFO rate (§D/§P) — DONE (rate-based).** The MPC `<Sync>` index→
  division table is now known (Jan, 2026-06-14, full table in `xpm_parser
  _MPC_SYNC_DIV`). The MPC ignores `<Rate>` when synced (stuck at ~0.5 ≈ 2 Hz =
  the bug). Fix: `xpm_parser` reads `<Sync>` and sets the LFO rate to the
  division's frequency at a reference tempo (`_mpc_sync_hz`).
  **Why not the clock cord (confirmed by the EOS 4.0 manual p.260):** the clock
  source has exactly **six divisions** (dbl-whole/whole/half/quarter/8th/16th =
  the ids 0x90–0x95) — no dotted/triplet/multi-bar — and the clock→LFO-Trigger
  cord only **resets** the LFO ("the LFO wave resets to zero every time the clock
  wave goes low … if the two rates are far apart, the waveform … will be mildly
  or radically altered").  So EOS does **not** tempo-follow even straight
  divisions (unlike the Proteus 2000's 25-division synced-LFO mode, which EOS
  lacks).  The BPM also lives in the MPC *project*, not the XPM.  So a fixed rate
  at a reference tempo is the faithful best — right speed for all 20 divisions,
  robust at any E4XT tempo; a clock cord would add no follow and would *worsen*
  the wave at off-reference tempos.  (RE'd clock ids kept in
  `docs/re_procedures/re_suite2.md`.)  Configurable via **`--lfo-sync-bpm`**
  (default 120, the MPC/DAW new-
  project default); convert.py prints a note when synced LFOs are converted;
  per-tempo lookup table in **`docs/lfo_sync_rates.md`** (60–200 BPM).

**Open — need data:** **SawDown** waveform (§B); **envelope-time calibration** (§J).

### Enhancements (no behaviour change)

**DONE 2026-06-11:** CR-13, CR-14, CR-15, CR-17, and the CR-18 cord-builder —
fixed & pipeline-verified (details in `docs/RESOLUTION_NOTES.md §CR`).

- **CR-16 Perf — DONE 2026-06-11 (all four; each byte-identical).**
  - **#1 gig decode:** 24-bit→16-bit is a bulk `bytearray` slice (drop the low
    byte of each frame; ~200× faster), 8-bit→16-bit a bulk `bytes.translate`
    (sign-flip) — were per-sample `struct.pack_into` loops. (Stereo downmix was
    already `array`-based.)
  - **#2 `write_e4b` memory:** streams each sample's header+PCM straight to disk
    (was ~5 PCM copies via join/concat → ~1×).
  - **#3 resampler:** bulk `array('h')` de/encode (~2×/1.3×; per-element float
    math is the floor without numpy — the earlier ~30-50× estimate was wrong).
  - **#4 ISO/HDA:** copy embedded files in 1 MB chunks + pad separately (was
    read-whole-file then build a 2nd padded copy).
  - *(Avoided `audioop` — byte-identical to the manual loops but deprecated/
    removed in Python 3.13.)*
- **CR-18 — DONE 2026-06-12.**
  - **#1 `Envelope` dataclass — DONE.** `VoiceLayer` now stores `amp_env` and
    `filter_env` as `Envelope(attack, decay, sustain, release)` with
    backward-compatible `env_*`/`filter_env_*` property accessors, so every
    existing parser/writer field access keeps working.  Round-trip across XPM /
    SFZ / SF2 / EXS → E4B shows **zero feature diffs**.
  - **#2 EXS24 walker unify — N/A as written; replaced by concrete EXS fixes.**
    The premise ("validate a merged classic+v11 walker on real classic files")
    is unsatisfiable: the local corpus is **1717 v1.1 + 0 classic** `.exs`
    files, so the classic path can't be exercised at all.  Investigating it
    instead surfaced three real v1.1 bugs, now fixed in `exs24_parser.py`:
    1. **`0x40000101` flag variant rejected.** 14 files (Samples-/Drums-From-
       Mars packs) set bit `0x40000000` on the magic AND every chunk type, so
       the magic read `0x40000101` and the parser raised "Not a valid EXS24".
       Now masked off (`_V11_TYPE_FLAG`) at dispatch + every chunk compare.
    2. **Long-common-prefix multisamples collapsed to 1 sample.** `_safe_name`
       truncated the sample-cache key to 16 chars, so 36 `DX100 Classic Bass-*`
       zones all mapped to one sample.  Parser now keeps the full stem
       (E4B maps zones by index, not name; 16-char limit applied at write).
    3. **`.aif` references with `.wav` twins didn't resolve.** `load_wav` is
       WAV-only; the ancestor index now keeps a stem→`.wav` fallback so an
       `.aif` reference lands on its sibling WAV copy.
    All 14 formerly-rejected files now round-trip ERROR→PASS through E4B.

---

## TAL writer: keytracked external-sample RANGE zones play silent (OPEN)

**Status:** open — stashed 2026-06-11.  Per-note single-key zones (`track="0"`)
work perfectly in TAL-Sampler (drum kits + melodic per-note multisamples,
confirmed in tune).  A **range** zone (`low≠high`, `track="1"`, one external WAV
keytracked across keys) is **silent**, even at its root key.

**Investigated, not solved:**
- The sample has audio; `track="0"` plays it; `track="1"` silences it.
- Progression across attempts: keytracked → `-48` semitones off (wrong root) →
  added WAV `smpl` MIDIUnityNote (TAL keytracks off the WAV root) → crash → after
  `endsample = n_frames-1` fix → silent → after removing the `smpl` LOOP (kept
  root) → still silent (Jan, last test before stashing).
- **No real TAL preset in Jan's library keytracks an external sample over a
  range** — they all use per-note single-key samples or ROM oscillators
  (`isromsample=1`).  Possible TAL limitation or a deeper resampler interaction.

**Fixes that DID land from this (keep):** `<programs>` wrapper, layer bin-packing,
`track`/`stereoinverse` explicit for one-shots, neutral per-sample filter, CRLF,
`endsample=n_frames-1`, WAV `smpl` root note.

**Pragmatic fallback if not solved:** emit range zones as `track="0"` (plays at
native pitch across the range — audible, not pitch-shifted) instead of silent;
or split a ranged source zone into per-key single-key zones.  Decide with Jan.

---

## E4B writer: amplitude envelope — RESOLVED (2026-06-08)

The full 6-stage amp envelope (`PZT[0:12]`) is now written and parsed. The
decay rate byte was the last unknown; it is **`PZT[4]`**, confirmed on hardware:

- `AMPENV_SETME.E4B` (E4XT-saved baseline) pins the 12-byte layout.
- `AMP_DECAY_CAL.E4B` isolates it — across 6 voices only `PZT[4]` changes
  (`08 10 18 20 30 40`), and the same sweep calibrated rate→time (see below).

The earlier corpus-RE guess (vpar[0]=attack / vpar[1]=sustain) was wrong: those
bytes are 0 in every hardware-saved bank. The amp envelope lives entirely in the
`PZT[0:12]` rate/level block. See `docs/RESOLUTION_NOTES.md` §1.

**`vpar[42]`** is now resolved — it is per-voice Chorus Amount (see below).

---

## E4B: filter-envelope reproduction — RESOLVED (2026-06-09)

The 6-stage filter envelope (`PZT[14:26]`) is written, round-trips, and is now
hardware-confirmed to sweep on the E4XT. Three things were resolved:

- **Routing (Gap 0):** the envelope shape alone is inert — it reaches the cutoff
  through the **FilterEnv→FilterFreq mod cord** (E4XT "Cord 05", default 0 %).
  Our KT voices wrote an all-zero mod matrix → no sweep (all `FLT_DECAY_CAL`
  presets sounded identical). Fixed: `e4b_writer` writes the EOS default cord
  table for filter-env voices and puts `filter_env_amount` (signed) in the cord
  amount byte `mod[30]`; `e4b_parser` mirrors it. Hardware-confirmed.
- **Calibration (Gap A):** measured `FLT_DECAY_CAL` on the E4XT — the filter
  Decay-1 rate→time follows the **amp curve** (low rates match exactly; highs
  noisy from the centroid metric). Writer already reuses `_fenv_rate()` → correct.
- **Source mapping (Gap B):** XPM, SFZ, SF2, GIG, EXS24 all set
  `filter_env_amount` → Cord 05. Details in `docs/RESOLUTION_NOTES.md` §17.

Cord amount encoding confirmed from `B.010-CordAmountTest.E4B`:
`amount = round(pct/100 × 127)` signed (+100 %=127, −100 %=−127), cord layout
`[src, dst, amount, flag]`. Matches the writer/parser exactly.

---

## XPM parser: envelope values 0–1 → seconds — RESOLVED (2026-06-09)

`xpm_parser` previously passed `VolumeAttack/Decay/Release` and the `Filter*` env
times through as seconds, but MPC stores them as normalised **0.0–1.0** controls.
Measured on the **MPC One** (recorded `XPM_VOL_DECAY` + `XPM_FLT_DECAY`, analysed
with `analyze_envelope_recording.py`): steep exponential
`seconds ≈ 0.00079·e^(9.78·value)`, and the filter envelope confirmed to share the
**same exponent** (one curve for all segments). Applied as `_xpm_env_to_seconds()`
in `xpm_parser.py`. Details in `docs/RESOLUTION_NOTES.md` §18.

---

## E4B writer: `vpar[42]` = Chorus Amount — RESOLVED (2026-06-08)

`vpar[42]` is the per-voice **Chorus Amount** (Voice/Tuning page), UI 0–100 %
mapped linearly to byte 0–127 (`round(pct/100*127)`). Confirmed on the E4XT
(commercial-bank reads + a 25/50/75/100 % → 32/64/95/127 sweep) and wired into
`VoiceLayer.chorus_amount`, `_build_voice()`, and `_parse_voice()`. Details in
`docs/RESOLUTION_NOTES.md` §13.

**Note:** Chorus *stereo width* is a separate, still-unlocated byte (was 100 %
in every sample, so it never varied). Only worth chasing if a source format
ever needs per-voice width.

---

## E4B writer: `_fenv_rate()` calibration — RESOLVED (2026-06-08)

Calibrated from 6 Decay-1 decay-to-silence measurements on the E4XT
(`AMP_DECAY_CAL.E4B`). The earlier `round(80.0 / (t + 0.01))` formula had the
direction backwards; hardware shows **rate 0 = fastest (instant), higher =
slower** (rate 127 ≈ 47 s):

| rate | time   | rate | time    |
|-----:|-------:|-----:|--------:|
|    8 | 0.034 s|   32 | 0.198 s |
|   16 | 0.098 s|   48 | 0.454 s |
|   24 | 0.169 s|   64 | 1.225 s |

Log-linear fit (R²=0.96): `time_s = 0.0310 · e^(0.0581 · rate)`. Applied as
`_ENV_RATE_A`/`_ENV_RATE_K` + `_fenv_rate()`/`_fenv_seconds()` in
`writers/e4b_writer.py`, with the matching inverse `_fenv_rate_inv()` in
`parsers/e4b_parser.py`. Details in `docs/RESOLUTION_NOTES.md` §2.

---

## E4B writer: E4XT filter type bytes — RESOLVED (2026-06-08)

All 21 EOS filter `vpar[58]` bytes reverse-engineered from
`B.005-FILTERTYPES.E4B` (one preset per filter type, set on hardware and saved).
Encoding: `byte = group_base | variant`. Full table in
`writers/e4b_writer.py:_E4XT_FILTER_BYTES` and `docs/E4B_FORMAT.md` §4.4
(LP `0x00`, HP `0x08`, BP `0x10`, Swept `0x20`, Phaser `0x40`, Flanger `0x48`,
Vocal `0x50`, Morph `0x60`, Peak/Shelf `0x68`).

Applied: MPC Vocal-formant types now map to the E4XT Vocal filters (`0x50`/
`0x51`) instead of LP; `e4b_parser` reverse-map updated. Swept/Phaser/Flanger/
Morph have no MPC-XPM source equivalent, so they're documented but not reachable
from current inputs (reverse-mapped lossily when parsing hardware banks).

---

## GIG→E4B: `fine_tune` not written to zone entry

**Status:** parser side complete; writer side blocked on hardware RE.

The GIG parser now extracts per-zone `fine_tune` in cents (DLS `sFineTune`,
signed 16-bit) and stores it correctly in `ZoneMapping.fine_tune`. However
`_zone_entry()` in `writers/e4b_writer.py` does not write this value — the
byte offset for fine_tune in the 22-byte secondary zone entry has not been
reverse-engineered yet.

**To resolve:** on the E4XT create two otherwise identical presets with
fine_tune = 0 and fine_tune = +50 cents, save as E4B, binary-diff the zone
entry bytes. The changing byte(s) are the field.

---

## GIG→E4B: per-zone volume (gain_db) not written to zone entry

**Status:** parser side complete; writer side blocked on hardware RE.

DLS `lAttenuation` (millibels) is parsed and stored in `ZoneMapping.volume`
(dB). `_zone_entry()` in `writers/e4b_writer.py` does not write it — the
byte offset in the 22-byte secondary zone entry is unknown.

**To resolve:** same approach as fine_tune above — diff presets with
differing per-zone volume (e.g. 0 dB vs −12 dB).

---

## Sample loader: AIFF (`.aif`/`.aiff`) not decoded — WAV only

**Status:** open (2026-06-12). **Blocked on:** none (implementation only).

`load_wav` (in `parsers/xpm_parser.py`) reads WAV via Python's `wave` module
only — there is no AIFF decoder.  Several Logic packs reference `.aif` samples.
The EXS24 parser works around this when a parallel `.wav` copy exists (stem→wav
fallback, see RESOLUTION_NOTES §CR-18), but a pack shipping **AIFF only** still
loads zero samples.

**To fix:** add a minimal AIFF reader (parse `FORM/AIFF` → `COMM` for
rate/channels/bits + `SSND` for big-endian PCM, byte-swap to LE16).  Python's
`aifc` is deprecated and **removed in 3.13**, so a small manual chunk reader is
the durable path.  Wire it into `load_wav` by suffix (`.aif`/`.aiff`).  Also
read the AIFF `INST`/`MARK` chunks for loop points to match the WAV `smpl`-chunk
handling.

---

## EXS24 parser: multi-velocity layers — first layer only

**Status:** known limitation; positional zone mapping.

EXS24 v1.1 instruments can have multiple velocity layers per key zone. The
current parser uses a positional zone-mapping approach and only reliably
captures the first velocity layer. Additional layers may be silently dropped.

Note: the tested corpus (101 From Mars, Acid From Mars, 2600 From Mars) uses
GROUP chunks exclusively for L/R stereo separation — not for velocity layers.
All observed zones have `vel_hi=127` and no velocity-split. True velocity-layered
instruments may exist in other packs but were not found in this test set.

**To fix:** implement a proper velocity-aware zone grouping pass in the EXS24
parser, similar to the `vel_to_voice` grouping logic in `xpm_parser.py`.

---

## E4B writer: LFO modulation routing (partial)

**Status:** E4B-side LFO1+LFO2 encoding + all LFO→{Pitch,Filter,Q} cords +
round-trip DONE (2026-06-10); Key/Vel→Filter DONE (2026-06-09); **input-format
LFO source mapping DONE for XPM / SFZ / SF2 (2026-06-10)**. **Only remaining gap:
GIG LFO mapping** (deferred — needs a test `.gig` + libgig 3ewa LFO byte offsets).
See the DONE blocks below.
**Wanted (Jan, 2026-06-09):** at least **LFO→Pitch, LFO→Filter-Freq,
LFO→Filter-Q (resonance)**, **Key→Filter-Freq (filter keyboard tracking)**, and
**Velocity→Filter-Freq** — written when the input format actually provides them.

Most input formats carry these routings: XPM (`LfoPitch`, `LfoCutoff`,
`LfoVolume`, `LfoPan`, **`FilterKeytrack`**, **`VelocityToFilter`** + `<LFO>`
Rate/Type), SF2 (`modLfoToPitch`, `modLfoToFilterFc`, `modLfoToVolume`,
`vibLfoToPitch`, default **Velocity→FilterCutoff** modulator), SFZ (`pitchlfo_*`,
`fillfo_*`, `amplfo_*`, **`fil_keytrack`**, **`fil_veltrack`**), GIG (LFO1/2/3 →
pitch/filter/amp, **`VCFKeyboardTracking`**, **`VCFVelocityScale`**), EXS24 (LFO
block, **`FILTER1_KEYTRACK` id 0x2e**, velocity-to-filter). We currently write
none of it — KT voices get an all-zero mod table, NT voices the fixed `_MOD_TMPL`.

**Cord format decoded** (`[src, dst, amount, flag]`, amount `= round(pct/100 ×
127)` signed, UI cord N = storage slot N — see `RESOLUTION_NOTES.md` §4.3/§15).
**Ids decoded 2026-06-09:** sources LFO1=`0x60`, Velocity=`0x0C`, Key=`0x08`,
FilterEnv=`0x50`; dests Pitch=`0x30`, Filter-Freq=`0x38`. `_MOD_TMPL` already
carries the cords at amount 0: slot 2 LFO1→Pitch (`mod[10]`), slot 4
Velocity→Filter (`mod[18]`), slot 5 FilterEnv→Filter (`mod[22]`, done), slot 6
Key→Filter (`mod[26]`).

**DONE 2026-06-09:** **Key→Filter (cord 06)** and **Velocity→Filter (cord 04)** —
`VoiceLayer.filter_keytrack` / `velocity_to_filter` (signed ±1 → `mod[26]`/
`mod[18]`), read back by the parser, mapped from GIG (`VCFKeyboardTracking`,
`VCFVelocityScale`, real data verified), SFZ (`fil_keytrack`/`fil_veltrack`), XPM
(`FilterKeytrack`/`VelocityToFilter`), EXS24 (`FILTER1_KEYTRACK`, scaling
unverified). SF2 skipped (velocity→filter is a fixed default modulator).

**DONE 2026-06-10 — LFO1 + LFO2 encoding & all LFO routing cords (E4B side).**
RE'd from `B.011-LFO1 settings.E4B` (`E4B_FORMAT.md` §4.2/§4.3,
`RESOLUTION_NOTES.md` §15); full E4B→E4B round-trip, validated against the
hardware bank:
- `VoiceLayer.lfo{1,2}_{rate,shape,delay,variation,sync}` (all `Optional`,
  `None` = leave EOS default so non-LFO voices stay byte-identical). LFO2 is the
  `PZT[50:54]` +8 mirror of LFO1 `PZT[42:46]`.
- **Rate in Hz** — byte↔Hz calibrated from the E4XT menu readout (0=0.08, 64=4.12,
  127=18.01 Hz); log-quadratic fit `models.common.lfo_rate_hz_to_byte` /
  `lfo_rate_byte_to_hz` (3-point, refineable with intermediate readouts).
- **Sine=1 confirmed** (`LFO1+2 SINE` preset: `PZT[43]`+`PZT[51]`=01).
- Routing cords: `lfo1_to_pitch` (default cord 02 `mod[10]`); `lfo1_to_filter`
  (`0x60→0x38`), `lfo1_to_filter_q` (`0x60→0x39`), `lfo2_to_pitch` (`0x68→0x30`),
  `lfo2_to_filter` (`0x68→0x38`), `lfo2_to_filter_q` (`0x68→0x39`) written into
  free cord slots 8+. New ids: **Filter-Q dest `0x39`**, VEnvDcy `0x4A`, LFO2~
  `0x68`/LFO2+ `0x69`. LFO1~`0x60` doubly confirmed; **Lag0=`PZT[57]`,
  Lag1=`PZT[59]`**.

**DONE 2026-06-10 — input-format LFO source mapping (XPM / SFZ / SF2).** The
shared rate curve lives in `models/common.py` (`lfo_rate_byte_to_hz` /
`lfo_rate_hz_to_byte` / `lfo_knob_to_hz` / `lfo_pitch_depth_to_amount`), used by
the writer, the E4B parser and all source parsers:
- **XPM** (`xpm_parser._xpm_lfo_shape`): single keygroup `<LFO>` → LFO1.
  `<Rate>` knob 0–1 → Hz via `lfo_knob_to_hz`; `<Type>` → shape; `<Reset>` →
  Sync (True=key-sync); `LfoPitch`→`lfo1_to_pitch`, `LfoCutoff`→`lfo1_to_filter`.
  Emitted only when a routing is non-zero.
- **SFZ** (`sfz_parser._sfz_lfo_wave`): v1 `pitchlfo_*`→LFO1 / `fillfo_*`→LFO2
  (sine); v2 `lfo01_*`/`lfo02_*` with `_pitch`/`_cutoff` targets + `_wave`.
- **SF2**: triangle Mod-LFO (gens 22/5/10) → LFO1, Vib-LFO (gens 24/6) → LFO2;
  absolute-cents freq → Hz (`8.176·2^(c/1200)`).

**Remaining — GIG LFO mapping (deferred):** needs a test `.gig` to validate
against, plus the libgig 3ewa LFO1/2/3 (amp/filter/pitch) byte offsets — the
current `_decode_3ewa` only reads EG1/EG2/VCF. Other open sub-items: LFO→Amp/Pan/
VEnv dests if a format needs them; cord-amount↔musical-unit absolute scaling is
proportional pass-through (unverified — see the dedicated issue below); only the
bipolar `~` sources are wired (the musical default).

---

## E4B: Mod-cord depth scaling — RESOLVED (2026-06-12, measured + applied)

**Status:** **RESOLVED 2026-06-12** — all five cords measured AND applied.
`models/common.py` now carries the hardware constants (`LFO_PITCH_FULL_CENTS=1593`,
`FILTER_ENV_FULL_CENTS=4383`, `VEL_FILTER_FULL_CENTS=9120`, `KEY_FILTER_OCT_PER_OCT
=0.713`) + helpers `velocity_filter_depth_to_amount` / `key_track_to_filter_amount`.
Cents-based filter mods (SF2 + SFZ filter-env & LFO→filter) are auto-corrected by
the 9600→4383 flip; SFZ velocity/keytrack go through the new scalings; XPM/GIG/EXS
stay proportional passthroughs (their inputs are fractional knobs/flags, not
absolute units).  RE methodology preserved in RESOLUTION_NOTES §19 for re-runs.
**Bonus bug fixed:** Velocity→Filter shipped the wrong polarity (`Vel<` subtract
→ now `Vel+` add, 0x0A).

We RE'd *which* cord routes *where* and the amount encoding (`round(depth×127)`,
±127=±100 %), and have now **measured** what each amount does in real units —
all four filter cords agree on one `0x38` sensitivity (3.65 oct/source-unit):

| Cord | Code constant | Status |
|---|---|---|
| LFO→Pitch | `LFO_PITCH_FULL_CENTS=1593` (`models/common.py`) | **MEASURED**: 100 % = ±1593 c (±16 st), linear |
| LFO→Filter-Freq | proportional 0–1 | **MEASURED**: 100 % = ±3.65 oct (noise take, σ0.16); apply `oct/3.65` |
| FilterEnv→Filter | `FILTER_ENV_FULL_CENTS=9600` | **→ reset to ≈4383** (shared 0x38 sensitivity = ±3.65 oct, ~2.2× too high) |
| Key→Filter | `filter_keytrack` ±1 | **MEASURED**: 100 % = 0.713 oct/oct (~0.71:1, NOT 1:1); r=0.9994 |
| Velocity→Filter | `velocity_to_filter` ±1 | **MEASURED + polarity fixed** (`Vel+` 0x0A): 100 % = ~7.6 oct over vel 0→127, linear r=0.9999 |

**RE strategy (full procedure: `docs/re_procedures/mod_cord_depth.md`; fix
recipe: `RESOLUTION_NOTES.md §19`):** drive the destination with a **square**
LFO at a known cord amount so the parameter hops between two steady states — the
gap between them is `amount/100` of full-scale. Sweep 25/50/75/100 % to check
linearity and pin each constant.

- Generate: `python3 tests/re_banks/gen_mod_depth_test.py` → `MOD_DEPTH_CAL.E4B`
  /`.iso` (10 presets: PitchDepth×4, FiltDepth×4, KeyTrk 100, VelTrk 100).
- Record each sustained note (≥3 LFO cycles; KeyTrk play C1..C6; VelTrk vel
  1/64/127).
- Analyse: `python3 tests/re_banks/analyze_mod_depth.py <rec.wav> --mode
  pitch|filter` → low/high state, peak-to-peak cents/octaves, one-sided depth
  (validated against a synthetic ±100 c signal).
- Apply: set `LFO_PITCH_FULL_CENTS` to the measured 100 % one-sided cents; add an
  `lfo_filter_depth_to_amount()` for the cutoff octaves-per-100 %; reconcile
  `FILTER_ENV_FULL_CENTS`; verify Key→Filter 100 % ≈ 1:1.

---

## XPM parser: MPC binary `.pgm` — MPC1000/2500 + MPC60 DONE; MPC2000 open

**MPC500/1000/2500 and MPC60 `.pgm` are implemented** in `parsers/pgm_parser.py`
(`parse_pgm` dispatches by magic; wired into `convert.py`):
- **MPC1000/2500** (`MPC1000 PGM 1.00`): 64 pads → voices at their MIDI notes; 4
  per-pad samples → velocity layers; amp env / filter1 / mixer mapped. Validated
  against all 8 From Mars kits + a synthetic kit (vel-split/filter/tuning/pan/
  play-mode); non-MPC1000 `.pgm` (e.g. `BD12`) rejected cleanly.
- **MPC60** (byte 0 = `0x07`, 2026-06-08): sample-name list → external 12-bit
  `.SND` samples decoded to 40 kHz mono (verified clean decaying drum envelopes,
  PCM round-trips through E4B identically). Samples map to sequential keys from
  C1; per-pad note/vol/pan/tuning params not yet decoded (single test file).

Both informed by ConvertWithMoss (`format/akai/mpc1000`, `format/akai/mpc60`),
independent impl + attribution. The MPC60 `.PGM`/`.SND` container was RE'd from a
real kit (ConvertWithMoss only reads the MPC60 *SET* variant).

**DONE — MPC2000 / MPC2000XL (2026-06-08):** implemented in `pgm_parser.py`
(`_parse_mpc2000`, magic `0x07 0x04`). Header → sample-name list, 64 × 25-byte
pads (+6-byte mixer) + 64-byte note table; each pad's `sampleNumber` → a
key-tracking voice at its MIDI note, with tune/level/pan/envelope mapped.
Samples are standard external `.WAV` (not 12-bit). Validated against an Akai
MPC2000XL factory CD (AMBIENCE_SET — 13 sounds, correct GM notes, E4B written).
MPC2000 and MPC2000XL use the **same** `.pgm` layout (one parser).

**Still open — MPC3000 `.pgm`:** ConvertWithMoss's `mpc2000` package also reads
MPC3000 (`0x07 0x00`, `byte2==0x00`) — but that magic collides with our MPC60
`.PGM` (also `0x07 0x00`); they'd need a body-level discriminator. Low priority
(no MPC3000 test file). Also possible: read MPC2000 `.iso`/disk images directly
(currently extract with `7z` first), and decode the MPC60 PGM per-pad params.

**DONE — MPC60 SET + floppy (`.set` / `.img`), 2026-06-08:** implemented in
`parsers/mpc60_parser.py` (wired into `convert.py`). The intact "800K" SET
(magic byte 0x02) is the standard ConvertWithMoss layout: pads at 0x05 (0x3B
each, name@+0, start@+18, length@+22 in frames), 12-bit sample block from 0xBFF
(2 frames per 3 bytes). Each pad → a sample at sample_block[start:start+len];
32 pad slots are de-duplicated to the unique sounds and mapped to sequential
keys from C1. `.img` floppies are read directly (built-in FAT12 reader extracts
the `.SET`). **Validated** against the *Akai MPC60 to WAV* reference decoder —
decoded PCM correlates 0.99 (tonal) with its WAVs (the residual is the tool's
per-sample gain, which the E4XT applies itself).

The earlier confusion was that the user's first disks were **720K copies of
800K originals** (truncated → magic byte 0x00, garbled header) — those are
flagged and skipped; the intact 800K images decode perfectly. Truncated tails
on individual samples are handled gracefully (clamped).

---

## XPM→E4B: TuneCoarse / TuneFine dropped entirely (no transpose, no detune)

**Status:** **RESOLVED 2026-06-13.**

All three E4XT per-voice tuning bytes are now RE'd and implemented:
- `vpar[34]` = Key Transpose (keyboard pitch remap, signed byte semitones)
- `vpar[35]` = Coarse Tune (sample repitch, signed byte semitones) ← RE'd 2026-06-13
- `vpar[36]` = Fine Tune (signed byte in 1/64-semitone units; cents × 64/100)

XPM `TuneCoarse` (inst + layer summed) → `ZoneMapping.coarse_tune` → vpar[35].
XPM `TuneFine` (inst + layer summed, cents) → `ZoneMapping.fine_tune` → vpar[36]
with proper unit conversion.

The Lazloz/JR-Spt "split" character from detuned stacked instruments is now
correctly written. Feature-demo banks can be rebuilt to reflect this.

**⚠ Demo-bank rebuild pending:** `JR_LAZLOZSPL`, `JR_SLOBANDSW`, `JR_JRISINGSP`
need a rebuild to pick up the new tuning output.

---

## XPM parser: long-common-prefix sample names collide on 16-char truncation

**Status:** **RESOLVED 2026-06-12.** `_safe_name(..., tail=True)` keeps the
distinguishing *tail* for sample names (preset/bank names still head-truncate).
Verified: Lazloz samples keep distinct `…_C1_A`-style names.

When many samples share a >16-char common prefix, `_safe_name`'s 16-char
truncation destroys the distinguishing suffix and the dedup counter replaces it
with a meaningless index. `Inst-Pad-JR Lazloz Split.xpm` references
`Inst-Pad-LazSp-UniPanBass_C1_A … _C4_C` (26-char shared prefix) → all become
`Inst-Pad-LazSp-U`, `…-1`, `…-2`, … (Jan: "S222-S233 often have the same
names"). They stay unique but lose the C1_A/C2_B identity and look like
duplicates on the E4XT.

The EXS24 parser already solved the analogous problem (RESOLUTION_NOTES §CR-18:
keep the full stem, map zones by index, apply the 16-char limit only at write
with a *suffix*-preserving scheme). Apply the same to `xpm_parser` /
`_safe_name`: truncate keeping the tail (or hash the prefix) so `…C1_A` vs
`…C2_B` stay distinguishable.

---

## XPM→E4B: `KeygroupWheelToLfo` ignored → LFO modulation always at full depth

**Status:** **RE COMPLETE 2026-06-13 — implementing faithful gating.**
RE bytes from `B.013- RE_SUITE CrdAmt.E4B` (hardware save):
- **ModWheel source id = `0x11`** (Cord 00 of saved MW PITCH: `src=0x11 dst=0x30`;
  also the default `src=0x11 dst=0xaa +13%` cord 03 Jan flagged). `0x10` = Pitch
  Wheel (adjacent in the EOS source list).
- **Cord-N-Amount destination id = `0xA8 + N`** (linear): `C02Amt`=`0xAA` (cord 09
  of saved MW LFO1), `C08Amt`=`0xB0` (cord 09 of saved MW LFO2). Range `0xA8..0xBF`
  for cords 0..23 — the manual's 24 consecutive "Cord 0-23 Amount" destinations.

Cord layout reminder: 4-byte cords `src, dst, amt(signed byte), 0x00` at
voice[190:270]; amount is the single signed byte (`+127` = +100%).

**Faithful fix (in progress):** for each LFO→dest cord at slot N with intended
depth D and a voice `KeygroupWheelToLfo = Kw`:
  - set that LFO cord's static amount to `round(D * (1 - Kw))` (always-on part);
  - add a cord `src=0x11 (ModWheel), dst=0xA8+N, amt=round(D * Kw)` (wheel-added
    part) in a free slot.
At wheel 0 → cord N amount = `D*(1-Kw)`; at full wheel → `D` (programmed depth).
This generalises the interim `(1-wheel)` static scaling (which dropped the
wheel-controlled part entirely).

**Interim (superseded):** `xpm_parser` scaled static LFO depth by `(1 - wheel)`
so a 100%-gated LFO wrote near-silent instead of full-on.

The MPC program-level field **`<KeygroupWheelToLfo>`** (0–1, the UI "WHEEL→LFO"
amount) scales how much the mod wheel gates the LFO's modulation depth. At
`1.0` (100%) the LFO→Pitch / LFO→Filter / LFO→Vol routings contribute **nothing
at rest** and only reach their programmed depth as the wheel is raised.

Reported by Jan on `Bass-MS20 Acoustik.xpm` ("too much LFO→Pitch"): it has
`KeygroupWheelToLfo=1.0`, `LfoPitch=0.055`, `LfoCutoff=0.291`, LFO rate ~5 Hz —
so on the MPC the vibrato is wheel-gated (silent until you push the wheel).

Known LFO cord src/dst (for picking the cords to gate): LFO1=`0x60`, LFO2=`0x68`;
dests Pitch=`0x30`, Filter=`0x38`, Q=`0x39`. ModWheel=`0x11`, CordNAmt=`0xA8+N`.

Related to the LFO routing work ([[E4B-LFO-routing]]) — this is the missing
"depth controller" layer on top of the already-working LFO→dest cords.

---

## Fixed (un-gated) LFO→Filter on MS-20 patches — aural check needed

**Status:** open (2026-06-13). **Blocked on:** Jan's by-ears check on the E4XT.

`FEATUREDEMO_02 P003 Bass-MS20-Patch` (= `Bass-MS20-Patch 2c.xpm`) plays its
LFO1→Filter at a **fixed** amount (cord 08 `0x60→0x38` = +42 ≈ 33%), not
wheel-gated. **This is faithful to the source:** the XPM has
`KeygroupWheelToLfo=0.0`, `LfoCutoff=0.33`, `LfoPitch=0` — so the MPC does not
wheel-gate it, and a real MS-20's MG→VCF LFO is always-on too. Confirmed in
phase-1 staging (cord 8 = +42, cord 9 empty) — not a repack loss.

Jan flagged it as "not 100%" and will **judge by ear** whether:
1. it's correct as-is (faithful fixed LFO — most likely), or
2. the fixed filter LFO is too strong → the `LfoCutoff → cord-amount` mapping
   needs a calibration constant (currently linear `amt=round(depth*127)`, no
   `LFO_FILTER_FULL_*` analogue to `LFO_PITCH_FULL_CENTS=1593`), or
3. he wants LFO→Filter wheel-gated regardless of `KeygroupWheelToLfo` (a
   deliberate deviation from the MPC source).

(Aside: cord 03 `ModWheel→C02Amt @16` on this voice is the EOS template default
sitting on an absent pitch LFO — gates a zero cord, audibly nothing. Could be
suppressed when LFO1→Pitch is 0, but that changes the hardware-extracted
`_MOD_TMPL` byte output — left as-is pending the same aural pass.)

---

## XPM parser: `RootNote=0` wrongly treated as non-transpose → mistuned

**Status:** **RESOLVED 2026-06-12; root source REFINED 2026-06-13.**  Option B
(wide-keygroup non-transpose) implemented.  **2026-06-13 (aural §E):** for a
tracking `RootNote=0` zone the root now comes from the sample's **WAV `smpl`
unity note** (`load_wav` reads it; `xpm_parser` uses it), falling back to the
keygroup low note only when the WAV carries no unity note.  This fixed the **+36
transpose** on Jupiter-Rising patches (lowest sample rooted at C1=36, but
lo_key=0).  Verified: Lazloz Split now root_keys 36/48/60/72 (was 0).  See
`docs/aural_notes.md` §E/§F.

`xpm_parser.py:331` decides key-tracking from `smp_mode = (raw_root == 0)`. This
is wrong: `RootNote=0` is the MPC "root unset" sentinel, **not** a non-transpose
flag. The real non-transpose signal is the instrument-level **`IgnoreBaseNote`**
(authoritative: ConvertWithMoss `MPCModernDetector.java:486` only honours the
per-layer `KeyTrack` field *when `IgnoreBaseNote` is True*; otherwise the zone
key-tracks). When a zone tracks with `RootNote=0`, the root should fall back to
the keygroup **LowNote** (CWM writer `MPCKeygroupCreator.java:223` does exactly
this: `RootNote = (keyRoot || keyLow) + 1`).

Symptom (reported by Jan on `Bass-MS20-Patch 2c.xpm`): "metallic, out of tune."
Cause: the 15 narrow multisample keygroups (kg36-38 → sample "036 C1", …, root =
LowNote) all have `RootNote=0`, so the parser routes them through the SMP path →
**one voice, 15 zones all spanning key 0-127 with root=60** → the E4XT stretches
a single sample across the whole keyboard from the wrong root → severe
pitch-shift/aliasing.

**Verified non-regressions to preserve:** genuine non-transpose layers use
`IgnoreBaseNote=True` (F9 Disco Rhodes, DX7 "Chain-Noise"). The one ambiguous
case is `RootNote=0 + IgnoreBaseNote=False + full-range kg0-127` (DX7
"Chain-Synth Oscillators") — see the design note in `docs/RESOLUTION_NOTES.md`.

Related: [[MS20-tuning]] is the same root-derivation gap that the slice-playback
SMP-tuning sub-item touches. Fix strategy + CWM citations in RESOLUTION_NOTES.

---

## SFZ parser: keyswitch articulations discarded (only default kept)

**Status:** **RESOLVED 2026-06-12.** Each `sw_last` articulation → its own preset
(named `<inst>-<label>`, keyswitch keys dropped).  Verified:
`1st-violin-SOLO-KS-C2.sfz` → 6 presets (Sustain, Tremolo, Normal, Accent,
Staccato, Pizzicato).

`sfz_parser.py:256-272` keeps only the group whose `sw_last == sw_default` and
**discards every other articulation**. SFZs with keyswitches (e.g.
`1st-violin-SOLO-KS-C2.sfz`: 9 groups — C2 Sustain, C#2 Tremolo, D2 Normal,
D#2 Accent, E2 Staccato, **F2 Pizzicato**, all on the same playable range) come
out as a single articulation transposed across the keyboard. Jan: "CWM plays
different styles … ours just plays the same sound transposed." CWM keeps all
articulations (ignores keyswitches, stacks ~4 overlapping per key).

**Agreed E4XT mapping:** emit **one E4B preset per keyswitch articulation**
(`<base>-Sustain`, `<base>-Pizzicato`, …) — most faithful and usable on the
preset-based E4XT — and **drop the keyswitch keys** (C2-F2) like CWM, so each
preset's playable range is the real instrument range. Fix strategy in
`docs/RESOLUTION_NOTES.md`.

Distinct from (but related to) [[sfz-stacking]]: that item is about
*simultaneous* overlapping instruments (brass — correct to stack into parallel
voices); this one is *mutually-exclusive* articulations (must NOT stack — split
into separate presets). The discriminator is the presence of `sw_last`.

---

## E4XT per-preset voice limit — pin the cap (RE)

**Status:** **RESOLVED 2026-06-13 — no cap found; HARDWARE-CONFIRMED.**

E4XT RE via `RE_SUITE.iso`: `20 VOICES` loads all 20, `24 VOICES` loads all 24,
and `MZ 14V 11Z` (154 zones) loads all 14 — so there is **no general per-preset
voice-count, voice-data-byte, or zone-count limit**.  Jan confirmed 2026-06-13
on the rebuilt FEATUREDEMO ISO: `P001 all-brass-SEC-ac` shows all **15 voices**
(SFZ overlapping-region stacking + no cap → full 15-voice load). The original 15-voice
SFZ-brass preset showing only V1–V10 was **specific to that preset's
construction**, not a hardware ceiling. `MAX_VOICES_PER_PRESET` is therefore
`None` (cap disabled); `cap_voices_by_coverage` is a no-op pass-through unless a
cap is ever explicitly set. No writer change needed.

**Consolidated RE bank:** `RE_SUITE.iso` still carries the test presets for the
one remaining open RE task — **KeygroupWheelToLfo gating** (ModWheel source id +
PatchCord-amount dest id); see that item below and §3/§4 of
`docs/re_procedures/re_suite.md`.

---

## Zone reducer: `--reduce-key-zones` not velocity-aware → velocity holes

**Status:** **RESOLVED 2026-06-13.** `thin_key_zones` ran over a voice's whole
key-sorted zone list; after the XPM parser change packs non-overlapping velocity
layers into one voice, that interleaved the bands and tore holes in the velocity
coverage (Jan: Alpha Pad G#4-C#5 silent at high velocity, "holes" in the
hardware Vces-VelWin). Fixed: `thin_key_zones` now groups zones by velocity band
and thins + re-spreads each band to full keyboard coverage independently.
Verified: DSI Alpha Pad at `--reduce-key-zones 35` → every velocity band spans
0-127 with zero holes.

---

## SFZ parser: overlapping regions collapsed to one voice (no stacking)

**Status:** **RESOLVED 2026-06-12.** Regions lane-allocate into parallel voices
(overlapping key+vel → separate voices); same-param non-overlapping regions
share a voice.  Verified: `all-brass-SEC-accent.sfz` → 15 stacked voices (was 1).

`sfz_parser.parse_sfz` builds a **single** `VoiceLayer` and appends every
`<region>` to it as a zone (`parsers/sfz_parser.py:232` + `:387`). When an SFZ
overlays several instruments/dynamic layers on the same key+velocity range
(e.g. `all-brass-SEC-accent.sfz`: tuba + horns + trombone + trumpet, 14 groups,
up to 14 regions sounding at one key), the E4XT only plays **one** zone per note
(a voice selects a single matching zone), so the stack is lost and the preset
sounds thin. ConvertWithMoss reproduces it by building MPC keygroups with up to
4 simultaneous **Layers** (its hardware cap); the E4XT equivalent is multiple
overlapping **voices**, which we currently never emit (`1 layer(s), 155 zones`).

Each SFZ `<group>` here is a self-contained keymap (one instrument/dynamic
layer), so the natural fix is **one voice per overlapping stream** instead of one
voice for the whole file. Fix strategy + the group-vs-overlap-lane design
decision in `docs/RESOLUTION_NOTES.md`.

Note: this is the same "thin vs thick" class of issue as the XPM 122× unison
stack ([[SloBand]] slice item) — both come down to the E4B needing parallel
voices to stack.

---

## XPM parser: slice-based sample playback not honoured

**Status:** **RESOLVED 2026-06-12.** `_apply_slice()` trims to Pad-Start/End and
sets a forward (or ping-pong) loop from the Loop Position; slice-keyed sample
cache.  122× identical unison stacks are deduped.  Degenerate
`SliceLoopStart==SliceEnd` still falls back to whole-slice loop (unconfirmed on
HW — see RESOLUTION_NOTES).

MPC XPM `<Layer>` elements carry `<SliceStart>`, `<SliceEnd>`, `<SliceLoopStart>`
and `<SliceLoop>` (Pad Loop mode: 0=Off, 1=Forward, 2=Reverse, 3=Alternating)
fields that select a sub-range of the referenced WAV in **sample frames** and
loop from the Loop Position (`SliceLoopStart`) to the Pad End (`SliceEnd`). The
current parser ignores all of these — it loads the full WAV and creates no loop
points. Presets built on slice-based layers (e.g. `Inst-Synth-JR SloBand
Sweeper.xpm`, which loops 7 short drone segments and stacks one 122×) sound
"metallic and distorted" because the full, non-looped WAV bears no resemblance to
the intended looping slice.

Secondary: instrument-level `<TuneCoarse>` / `<TuneFine>` are not applied to
zones created from SMP-mode layers (RootNote=0). Affects all slice-based presets.

Field semantics verified against the MPC 3.7 manual + measured WAV frame counts;
the degenerate `SliceLoopStart == SliceEnd` case still needs ear/hardware
confirmation. Full fix strategy + field table in `docs/RESOLUTION_NOTES.md`.

---

## HDA: EMU-fs works; FAT layout corrected to EOS-native — both RE'd 2026-06-14

**Status:** **BOTH HDA filesystems HARDWARE-CONFIRMED (2026-06-14).** Jan loaded
banks from both `FEATUREDEMO_emu1gb.hda` (properly disk-sized EMU-fs, free space,
`build_emu_hdd`) and `FEATUREDEMO_fat.hda` (EOS-native FAT16/MBR, `build_hda_fat`)
on the E4XT.  EMU-fs HDD geometry confirmed against 1/2/4 GB EOS references;
bank-count-per-folder (≤100, multi-block dircon) RE'd from emu3fs + implemented.
Full RE in `docs/re_procedures/emu_hdd_fs.md`.

### EMU-fs (`--hda-fs emu`) — WORKS + now properly disk-sized (free space)
`build_hda_emu` → `iso_builder.build_emu_hdd`: a real **disk-sized** EMU3 image
(honours `--hda-size`) with the banks in a `Default Folder` and the rest of the
clusters **free** (so EOS can save onto it).  Geometry RE'd & **confirmed across
EOS-formatted 1/2/4 GB references** (`HD1-FEATUREDEMO_emufs.hda`,
`HD1-2GBemufs.hda`, `HD2-4GBemufs.hda`): it is a **second fixed profile** of the
EMU3 fs — directory geometry constant (`fat=4 root=7 dircon=169 start_data=182
total_clusters=1023`), only the **cluster size scales** (cse 4/5/6/7 =
512 MB/1/2/4 GB, keeping clusters ≤ 1023).  `build_emu_hdd` output's **superblock
and Default-Folder entry are byte-identical to the references**.  Full table +
the 2-digit (EMU-fs slot) vs 3-digit (FAT filename) numbering rule in the RE doc.
**HW-CONFIRMED:** disk-sized image loads on the E4XT (Jan, 2026-06-14).
**Multi-block dircon DONE + HW-confirmed:** up to **100 banks/folder** across
`ceil(N/16)` dircon blocks via `block_list[7]` (RE'd from emu3fs `emu3_fs.h`:
`EMU3_BLOCKS_PER_DIR=7`, 16 entries/block).  `MULTIBLOCK20_emu.hda` SLOT16 &
SLOT19 (2nd dircon block) loaded on hardware.

**Multi-folder DONE + HW-CONFIRMED (2026-06-14):** >100 banks now spill from the
system "Default Folder" (id 0x80, banks 0–99) into additional root folders
"Folder 2", "Folder 3", … (id 0x40), each ≤100 banks with per-folder slots reset
to 0.  dircon blocks allocated sequentially across folders; next-free pointer
set.  Limited by disk capacity (≤1023 clusters) / root (112 folders) / dircon
pool (169 blocks).  Verified: 150 banks → Default Folder(100) + Folder 2(50);
4-bank output byte-identical to the HW reference.  **HW**: on
`MULTIFOLDER105_emu.hda` Jan loaded RICH00 from "Folder 2" — presets work.

### FAT (`--hda-fs fat`, default) — corrected to EOS native, was wrong
The first attempt (partitionless **FAT32** superfloppy) was **rejected by EOS**
("No Banks Exist in Folder!").  An EOS-formatted reference (`HD1-FEATUREDEMO.hda`)
shows EOS actually writes:
- an **MBR partition table** (zeroed boot code, 0x55AA), partition 1 at **LBA 63,
  type 0x06 (FAT16)** — *not* partitionless, *not* FAT32;
- **FAT16**, **32 KB clusters** (64 sec/clus), **32 reserved sectors**, 2 FATs,
  512 root entries; OEM **`E-MU SYS`**;
- banks `B.NNN-NAME.E4B` in the partition **root** (and optionally sub-folders).
`build_hda_fat` rewritten to this exact layout (hand-written MBR + `mformat
-c 64 -R 32` + OEM patch + `mcopy`); `FEATUREDEMO_fat.hda` **HW-CONFIRMED** (Jan
loaded a bank, 2026-06-14).  (The HD0.img reference used earlier was a PC-made
FAT32, which misled the first attempt — the E4XT's own format is FAT16/MBR.)

### Append to an existing image (`--add-to`) — IMPLEMENTED 2026-06-14
`convert.py --add-to <image> [--folder NAME] [--on-duplicate ...]` appends the
converted bank(s) to an existing .hda (FAT or EMU-fs, auto-detected via
`detect_hda_fs`) without overwriting existing banks/folders; creates the folder
if absent.  EMU-fs: `iso_builder.emu_hdd_append` (read-modify-write — finds free
clusters/slots, spills dircon blocks, bumps next-free, superblock untouched).
FAT: `hda_builder.fat_hda_append` (pure-Python `writers/fat16.py`, next free
B.NNN).  Duplicate policy: prompt (default) / add-new / skip / overwrite.
**Append HW-CONFIRMED for BOTH filesystems** (2026-06-14): EMU-fs — APPENDED_BANK
from a new ADDED folder; FAT — a bank from the appended `Added` folder on
`FEATUREDEMO_fat_py.hda`.  Presets work from appended banks in both.

## FAT path is pure-Python — mtools dependency removed (Windows-ready) 2026-06-14
`writers/fat16.py` is a from-scratch FAT16 reader/writer (MBR + FAT16 + VFAT long
names, EOS-native layout) used by `build_hda_fat` + `fat_hda_append`.  **No
external tools** — the whole converter is now pure Python stdlib (no third-party
libs, no binaries), so it runs natively on **Windows** (the resampler's
ProcessPoolExecutor was already spawn-safe).  **HW-CONFIRMED 2026-06-14**: on
`FEATUREDEMO_fat_py.hda` (built+appended purely in Python) Jan loaded banks from
the root AND the appended `Added` folder on the E4XT — presets work.  Also
mtools-validated, BPB matches EOS, bank bytes round-trip byte-identical.
(mtools retained in dev only as an independent cross-check.)

**FAT32 added 2026-06-14** (`writers/fat32.py`): EOS uses FAT32 above ~1 GB (4.7
addendum p.3), so `build_hda_fat` now auto-selects **FAT16 ≤1 GB / FAT32 >1 GB**
and `fat_hda_append` detects the type.  FAT32: MBR type 0x0C, adaptive 16/32 KB
clusters (largest yielding ≥65525 clusters), FSInfo + backup boot, cluster-chain
root/folders.  mtools-validated at 1152 MB & 4 GB; build/append/folders work;
bytes round-trip identical.  **HW-CONFIRMED 2026-06-14** (Jan loaded a bank + played presets off the 4 GB FAT32 FEATUREDEMO.hda). (Was validated only
against mtools — no EOS-formatted FAT32 reference yet).  The whole FEATUREDEMO was
rebuilt with this session's aural fixes onto a **4 GB FAT32 HDA** (sparse 441 MB
on disk), ISO + colour-preserved ODS regenerated.

---

## KRZ #204 SloBand Sweeper — structure fixes 2026-06-24 (junk KGs, +12); gaps remain

Deep-dived with Jan A/B-ing on the K2000R. The XPM is **8 keygroups** (4 key-bands
× A/B pan pair, samples UniDrone C1/C2/C3/C4, unity 36/48/60/72) but pads to **128
Instrument slots** — KG9–128 are 120 identical junk copies (24–47 C1). All 8 KGs:
**KeyTrack ON, Semi +12, Pan ∓50 (A=L/B=R)**, identical env + LFO (0.54 Hz → Pan22
/ Pitch3 / FiltEnvDepth10).

**FIXED (xpm_parser):**
- **Junk KGs dropped** — honor `<KeygroupNumKeygroups>` (8); was keeping a junk
  voice that the K2000 3-layer cap then *kept while dropping a real one*.
- **Per-keygroup Pan** now read (instrument-level `<Pan>` + layer, summed).
- **Semi +12** confirmed already applied (roots = unity−12); staging E4B was just
  stale → regenerated `feature_staging/JR_SLOBANDSW_01.E4B` and rebuilt the ISO.

**ALSO FIXED — coverage multisample remap (2026-06-24, Jan's idea).** Wide-range
octave-slice stacks can't keytrack past the K2000 up-pitch ceiling (~1 octave
above root at 24 kHz), so high keys went silent (L1 died ~C2). New
`krz_writer._coverage_remap_voices`: lays the C1/C2/C3/C4 slices side-by-side as
a COVERAGE multisample (each slice keys 0/handoff→its ceiling, next slice takes
over), in ≤3 parallel layers (any-channel). #204 now plays **gap-free 0–72**,
correct octave. Auto-applies to the sibling stacks too (F9 Rhodes, JR AFX/JP8/
Warm/1V — they reach keys 109–120). Scoped tight: only fires for all-overlapping,
**full-velocity**, ≥2-octave-root, ceiling-overflowing stacks (a velocity guard
keeps it off Bass-DX7 etc.).

**STILL OPEN / deferred (all need Jan or HW):**
1. **Pan not delivered to K2000** — `write_e4b`/`parse_e4b` drop per-zone pan, and
   `krz_writer` doesn't render pan at all. So the L/R width (and LFO→Pan,
   LFO→FilterEnvDepth) is lost. Needs: E4B pan round-trip + KRZ pan byte (RE) +
   LFO→pan/→filt-env-depth cords. (The coverage remap is currently mono; once pan
   is delivered it can split the doubling layers L/R.)
2. **#204 top keys 73–127 silent** — its highest slice is C4 (root 60 after +12,
   ceiling 72 at 24 kHz) and there's no higher slice; the source plays these on
   the MPC (no ceiling). Only fix is heavier downsampling (`--max-sample-rate`)
   to raise the ceiling, at a quality cost. (Sibling stacks reach 109–120 — they
   have higher-rooted slices.)
3. **Sibling JR drones' staging is stale** — the coverage remap (writer) helps
   them, but the junk-KG-drop / +12 / pan PARSER fixes only apply when their
   staging E4B is regenerated; only SloBand's was this round. Regenerate
   `JR_*` staging from XPM to apply those uniformly.

## Band-Boost (BB) filters map to BANDPASS — RESOLVED 2026-06-25 (E4B + KRZ)

**Both writers fixed.** E4B: BB 19-22 → Swept EQ 1-oct (`0x20`) with +gain (the
band-stop mapping, gain sign flipped). KRZ: BB 19-22 → **Alg 2 PARA MID** parametric
boost, hardware-RE'd 2026-06-25 (PARAJLZ.KRZ disk-save diff): `CAL[29]=2`,
F1(0x50)[0]=**51** (PARA MID FRQ), F1[1]=center freq = existing `_cutoff_byte`
(16 Hz/C0=−48 … 25088 Hz/G10=+79), F2(0x51)[0]=**16** (AMP block), F2[1]=**gain in
dB, 1:1 signed** (boost = `+12..+24 dB` from MPC resonance), F3(0x52)[0]=**40** (None).
Verified end-to-end: #204 Bass-MS20-Patch (FilterType=19) → ALG2/51/AMP+20 dB.
Procedure + byte table: `docs/re_procedures/krz_paramid.md`; details in
`docs/RESOLUTION_NOTES.md §BB`.  (Possible later refinement: measure the MPC's true
BB gain law to calibrate the dB depth; FRQ already exact.)

---

## (was) Band-Boost (BB) filters map to BANDPASS — wrong sound (2026-06-25)

MPC FilterType **19–22 = "BB 2P/4P/6P/8P" (Band Boost** — a parametric/peaking EQ
that passes the full-range signal and *boosts* a band). Both writers approximate it
as a **bandpass** ("closest resonant emphasis; no exact match"), which instead
*removes* everything outside the band → thin/hollow. Confirmed audibly wrong on
`K2KFEATDEMO` **#204 Bass-MS20-Patch 2c** (src FilterType=19, Cutoff=0.27, Reson=0.65):
the K2000 conversion sounds very different from the MPC original (Jan, 2026-06-25).
(NB the on-HW bank Jan tested is a *stale* build showing 4-pole LP; current code already
emits 2-pole BANDPASS — still wrong.)

- **E4B — FIXABLE NOW (no RE):** EOS **Swept EQ 1-oct** (`vpar[58]=0x20`) is a
  parametric band gain whose law is already HW-RE'd (`gain_dB=(byte−64)×0.375`). Band-
  *stop* (15–18) already maps there with a *negative* gain; Band-*boost* is the **same
  filter with positive gain**. Patch in `docs/RESOLUTION_NOTES.md §BB`.
- **KRZ/K2000 — needs HW RE:** the right target is a K2000 **parametric-EQ DSP block
  (PARA MID / PARA BASS)**, not yet reverse-engineered (bandpass is just the nearest
  RE'd block). RE the function byte + algorithm + freq/gain/width mapping (FILTERS.KRZ
  disk-save method, same as the 2026-06-16 filter-type RE). **Status: blocked on RE.**

---

## KRZ: bandpass + filter-env-sweep preset plays silent (OPEN, 2026-06-21)

`K2KFEATDEMO` #204 "Inst-Synth-JR SloBand Sweeper" emits no sound on the K2000R.
Diagnosed: samples (UniDrone, root C1) have audio + loops, keymap keys assigned, amp
env fine. The **2-pole bandpass** (HOB0[0]=3) is centered at cutoff byte **−12 (≈130 Hz**,
from source `Cutoff=0.285`) and swept by the filter env (HOB0[5]=121 ENV2, depth 60); on
the low drone it parks where ~nothing passes → silent. **Not caused by the keytrack/cap/
downsample work** (filter bytes come straight from the source; unchanged). Belongs to the
known "KRZ filter-env depth + LFO→filter depth are approximate / need HW calibration"
gap — a bandpass-sweep is the first source that makes it fully inaudible rather than just
off. **To fix:** RE the 2-pole bandpass center/width + ENV2→filter depth+direction on HW
(disk-save trick, like the keytrack fix) so the sweep opens audibly. Likely also affects
other bandpass + slow-filter-env sources. Possible interim: widen the bandpass (HOB1[1])
or floor the static cutoff so it's audible before the sweep.

---

## KRZ single-sample keymaps don't keytrack — FIXED 2026-06-21 (up-pitch ceiling cap)

Surfaced on the K2000R: **single-sample presets (#202 PingPong_Vox, #203 Ab-e1) played
at FIXED pitch** while multisample presets (#200/#201) tracked.

**Root cause (RE'd from a hardware-edited save, `TRACK203.KRZ`):** the writer stretched a
single sample across the WHOLE keyboard (zone 0–127). The sample (33 kHz, root 60) can
only transpose UP to the K2000's 48 kHz ceiling = `maxPitch//100` = root + 12·log2(48000/sr)
≈ key 66. Assigning it to keys far beyond that (up to 127) makes the K2000 **drop
keytracking for the ENTIRE keymap** (plays one fixed pitch). Jan's fix-by-hand narrowed
the keymap range; the diff showed that was the *only* change (same method 0x13, same
sample, same program, same per-key tuning). Two effects confirmed on HW: (A) extreme
overshoot → whole keymap goes fixed; (B) even when tracking, keys above the ceiling clamp
to one pitch (C5==C4). (My earlier method-0x11 / WAVEFAZE-`defaultSampleID` theory was
WRONG — the K2000 re-saved as 0x13; reverted.)

**Fix (`writers/krz_writer._build_keymap_entries`):** cap each zone's assigned keys at the
sample's up-pitch ceiling (`_compute_max_pitch(sr, root)//100`). Keys above the ceiling go
SILENT instead of playing the wrong pitch, and the rest of the keymap keytracks. Multisample
unaffected except already-clamping top keys of the highest sample (verified vs RegalLead:
only keys 120–127 of its top run, which already clamped, are trimmed). To extend the
playable range UPWARD, downsample via `--max-sample-rate` (raises the ceiling — same lever
as the KRZ floppy banks). **HW retest:** `FLOPPIES/SF2FIX_01.img` (5 single-sample bass
presets, keys 0–66) on the Gotek.

**Ping-pong loop "audible seam" (#202) — NOT a bug.** Re-analysis of the baked PCM:
`PCM[sampleEnd]=L+1`, `PCM[loopStart]=L` → the seam is a correct, value-continuous
ping-pong turnaround (…L+1, L, L+1…). The audible artifact is the inherent *slope*
discontinuity at a ping-pong turnaround (same on E4XT). Optional future enhancement: a
short crossfade at the turnarounds to soften it. The bake (`loop_renderer`, 2n−2 frames,
inclusive `loop_end`) and the KRZ loop-point math are correct.

---

## KRZ `--iso` produced unreadable ISO 9660 — RESOLVED (2026-06-21): K2000 wants FAT16

**Symptom:** the K2000 demo CD built with `convert.py --format krz --iso` was rejected
on the K2000R ("Disk must be in K2000 format"), even on **OS v3.87** (which *does* read
ISO 9660 — but its reader is picky about our xorriso-built image).

**Root cause + fix:** the K2000/K2500 SCSI CD/disk format is a **FAT16 "disk-image
copy", not ISO 9660** — RE'd from a working factory CD (`CD1-E_Bomb.iso`) + the Kurzweil
`SCSI.txt` + the v3.87 release notes (all in `/home/lentferj/Dokumente/SYNTHS/K2000R`):
FAT16, **BPB at sector 0, NO MBR/partition**, OEM `KCDM1.2`, fsType `FAT16   `, 8.3
filenames, KRZ files in a subdirectory. ISO 9660 needs OS v3.87+; the FAT16 image works
on **every** OS version (older OS "require an image of a Kurzweil/DOS-formatted disk").

Implemented: `fat16.format_new(partition=False, oem=, spc=)` (no-MBR layout) + a clean
8.3-no-LFN path in `fat16.add_file`/`makedir`; new `iso_builder.build_k2000_disk`;
`convert.py --iso` for krz now builds the FAT16 disk image (E4XT `--hda`/EMU3 paths
unchanged, regression-checked). Also fixed `_iso9660_unique_names` hardcoding ext=`E4B`
(KRZ ISOs got `.E4B` filenames). Verified byte-identical extraction via mtools; the demo
CD `K2KFEATDEMO.iso` matches the factory CD's BPB. **HW-CONFIRMED 2026-06-21:** the
K2000R reads the FAT16 CD and loaded bank _01 (64486K ≈ 62.97 MB sample data) to
completion. FAT16 disk-image is the correct K2000 CD format.

---

## KRZ floppy multisamples: up-pitch clamp at 44.1 kHz (FIX SHIPPED + ALL BANKS HW-VERIFIED)

**Status:** root cause fixed in converter (2026-06-18); all 6 `FLOPPY_JOBS`
banks HW-verified (last one, RegalLead, confirmed 2026-06-21). Only the
low-priority headroom-aware rate-picker enhancement remains open (see bottom).

**Symptom (HW, audio-measured):** wide key zones at 44.1 kHz played groups of
adjacent keys at the *same* pitch — the K2000 can only pitch a 44.1 kHz sample
UP ~1.46 st before hitting its 48 kHz playback ceiling (`maxPitch`), so every
key >~1.5 st above its sample root clamped flat. Confirmed via
`tests/re_banks/pitch_sweep.py` (5-zone build: 11-key dead zones 20 st apart =
sample-root spacing). Pitching DOWN is unlimited.

**Fix:** new `convert.py --max-sample-rate HZ` (clean linear downsample in
`resampler.resample_to_rate`). Lower rate buys up-pitch headroom
(log2(48000/HZ) octaves) AND shrinks the bank to fit a floppy. SYNTHBONES at
12 kHz / 16 zones (+24 st headroom) = HW-CONFIRMED 2026-06-18: F#2–E7 track
within +10 c, no clamping. Reducing zone COUNT at high rate (the old
`--reduce-key-zones 70`) was exactly wrong.

**DONE 2026-06-18:** `rebuild_krz_floppies.py` rewritten to drop --reduce and
instead pick the highest RATE_CANDIDATE that fits the floppy at reduce=0. All 10
banks rebuilt + redeployed to the Gotek (FLOPPIES/ + FILTERTYPES/). Rates landed:
Bass/Organ 22 kHz, Synth/Timeless 16 kHz, filter-synths 7–9 kHz — all with ample
headroom for their narrow 16/21-zone maps.

**HW-VERIFIED 2026-06-18** (autonomous audio sweep, `tests/re_banks/verify_programs.py`,
programs #200–205 on ch9): Bass-MD Ace 60/60, Organ-PRO5 Coming 56/61 (92%),
Synth-PRO5 Bones 61/61, Keys Timeless 61/61 keys in tune (±60c) — all PASS, no
clamp. AxeLead clamps (2-sample source, unfixable by rate). PercDynobel pitch test
inconclusive (short one-shot percussion defeats pitch detection) but structurally
clamp-free (30 kHz → +8 st headroom > 4 st zones).

**HW-VERIFIED 2026-06-21 — RegalLead:** the MS20 lead that replaced the degenerate
AxeLead (16 samples, roots 31-106, 22 kHz) **tracks chromatically across the FULL
MIDI range C-2…G8 (notes 0–127) with no clamping** (by-ear, Jan, program #200,
"Lead-MS20 Regal"). Confirms the rate-over-reduce strategy end-to-end. All
`FLOPPY_JOBS` banks are now HW-verified.

**Also HW-verified 2026-06-21 — 1PoleLP (Bass-Pulse-Bass):** the 1PoleLP
filter-demo bank also tracks chromatically C1–C6 with no clamping (first program
tested this session, before the RegalLead re-test).

**Remaining script gap (low priority):** the fit-driven selection ignores
HEADROOM for banks that already fit at a high rate. Two needed manual rates this
round: AxeLead (2 samples on one full-keyboard zone — degenerate source, forced
to 12 kHz for ~2 oct tracking; can't be fully fixed without more samples) and
PercDynobel (16 one-shot perc zones, 5 keys wide — kept high quality at 30 kHz,
+8 st headroom). Proper fix: make the rate picker headroom-aware — parse each
voice's max (hi_key − sample_root) and cap rate so log2(48000/rate)·12 ≥ that.

## HDA builder: directory block limited to 16 entries

**Status:** low priority; silent-data-loss already guarded (2026-06-08 —
`build_hda()` warns + truncates to 16, no invisible sectors written).

The remaining work is to actually *support* more than 16 E4B files per HDA
image via multi-block directory support — chain additional 512-byte directory
blocks beyond the single root block.

**To implement:** needs hardware RE to confirm the block-chaining convention
(how the E4XT locates the next directory block).

## KRZ: clean velocity-SPLIT layers collapse to ONE layer — FIXED 2026-06-24

**Status:** FIXED in `writers/krz_writer.py` (`_split_voice_by_velocity`,
wired into `write_krz`); KRZ-writer tests pass; verified on the AlphaPad
staging E4B (program #200 now 3 layers, vel windows 0-64/65-96/97-127).
**Pending: K2000R HW A/B re-test by Jan** (soft notes should now play the
darker low-velocity layer). Rebuild K2KFEATDEMO to ship it.
Found by Jan loading K2KFEATDEMO to K2000R bank 200, `#200 Alpha Pad`.

**Symptom:** the MPC One original has **3 velocity layers** (split 0-64 /
65-96 / 97-127); the converted KRZ program has only **1 layer**. Audibly the
K2000 plays too bright at all velocities (the top/loudest layer always wins) —
Jan's "lots less high frequencies on the original, although the filter is fully
open … probably the velocity-triggered layers."

**Root cause:** *not* the KRZ writer's layer support (which already writes
per-layer `loVel`/`hiVel`, CR-1) and *not* the E4B path (the staging E4B is
correct: 1 voice / 141 zones, each zone carrying its own vel range — the E4XT
plays one zone per note by key+vel). The break is the interaction between two
correct-in-isolation pieces:

1. `xpm_parser._overlaps()` (lane-allocator, ~line 811) splits zones into
   separate voices only when they overlap in key **AND** velocity. AlphaPad's
   three velocity bands are mutually exclusive (0-64 vs 65-96 don't overlap),
   so all 219→141 zones collapse into **one voice**. (CR-1 only ever split
   velocity layers that *also* overlap; clean splits were never exercised.)
2. `krz_writer._build_keymap_entries()` builds one keymap per voice using
   **only `lo_key`/`hi_key`** — it ignores `lo_vel`/`hi_vel`. Three zones on
   the same key (one per vel band) all write the same keymap slot; the last
   one (top velocity = brightest) wins. Result: 1 layer, vel 0-127, brightest
   sample on every key.

This is the KRZ analogue of the SMP-parser bug already documented in
`docs/RESOLUTION_NOTES.md §10` ("one voice per distinct vel range").

**Fix:** see `docs/RESOLUTION_NOTES.md` §"KRZ velocity-split layers" — split
each KRZ voice's zones by distinct (lo_vel,hi_vel) band into separate K2000
layers + keymaps at write time (the writer already accepts per-layer vel
range, so this stays a writer-only change and leaves E4B untouched).

## KRZ: LYR velocity range + Enable — FIXED 2026-06-24 (HW-confirmed)

**Symptom (Jan, K2000R, AlphaPad #200):** intermittent / no sound; Layer page
showed `Enable: Sustain / Note St / ON` and wrong LoVel/HiVel.

**Two bugs, both fixed:**
1. **Enable clobber.** The writer wrote hiVel into LYR `data[6]`, but `data[6]`
   is the layer **Enable control source** (every real K2000 layer = 127 = ON;
   KurzFiler/xprogs4/KPOWER all confirm). hiVel 64/96 there set Enable to
   Sustain(64)/Note St(96) → gated layers. Fix: keep `data[6]=127`.
2. **Velocity encoding.** Both LoVel and HiVel are packed into the SINGLE byte
   `data[5]`, as 0–7 dynamic marks (ppp=0…fff=7): **bits 3–5 = LoVel mark,
   bits 0–2 = HiVel mark stored INVERTED (7−mark)** → `data[5] =
   (loMark<<3) | (7−hiMark)`. So full-range = 0 (why it was invisible in static
   files). HW-confirmed by diffing `VELAYRE.KRZ` (3 layers saved on the K2000R:
   ppp/fff→0, mf/fff→32, ppp/mf→3). Implemented as `_vel_byte()`.

**Confirmed LYR map:** `[1]=0x18 [3]=loKey [4]=hiKey [5]=packed vel (see
_vel_byte) [6]=Enable(127=ON) [8]=flags(0x04 mono/0x24 stereo)`.

**Result:** AlphaPad #200 → 3 layers, all Enable ON, LoVel/HiVel ppp–mf / mf–f /
f–fff (MPC 0-64/65-96/97-127 quantised to the K2000's 8 marks). Bands touch at
mf/f due to the 8-step granularity (minor overlap; acceptable). Reference: the
packed-byte map is also in the `reference_krz_format` memory.
**HW playback CONFIRMED on K2000R (Jan, 2026-06-24): velocity split is in place.**
Shipped in K2KFEATDEMO.iso. Optional future tweak: nudge each layer's HiVel down
one mark for strictly non-overlapping bands.

## KRZ: AMPENV segment offset + flat release — FIXED 2026-06-24

**Status:** FIXED in `writers/krz_writer._fill_env`; tests pass; verified on
AlphaPad #200. **Pending K2000R HW A/B.**

**Bug 1 — segment offset (the big one).** `_fill_env` wrote its `(time,level)`
pairs starting at byte **2** of the 0x21/0x22 ENV segment, but the K2000 packs
the 7 pairs `Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3` from byte **0** (times on even
bytes, levels on odd; byte 14 = loop flag). HW-confirmed by Jan reading the
AMPENV LCD: levels Att1..Rel2 all 100 % except Rel2=0. Effect: our decay→sustain
landed in Rel1 (so Rel1 read 100 %, never faded) and the release fade landed in
Rel2 → "held then cut" instead of a fade. Masked earlier for sustain=100 %
patches. Fix: write pairs from byte 0; leave byte 14.

**Bug 2 — release shape.** A single linear Rel1 sus→0 doesn't match the MPC's
~exponential (dB-linear) release. Now a two-leg approximation: Rel1 fades to a
**33 % knee** over **80 %** of the release time, Rel2 tails 33 %→0 over the
remaining 20 % (`_REL_KNEE_PCT`, `_REL1_TIME_FRAC`). Knee + split validated by
ear (Jan, AlphaPad: Rel1 2.16 s→33 %, Rel2 0.5 s→0 %).

NB: the *absolute* release duration is still ~1.9× short — that's the shared
time-curve item below, not this fix.

## XPM envelope-time curve under-reads vs MPC display — KRZ patched; global recalibration DEFERRED (by-ear)

**Status:** KRZ side handled (2026-06-24) with a writer-only ×1.9 release
multiplier (`_KRZ_RELEASE_FACTOR` in `krz_writer.py`). **Global recalibration of
the shared `_xpm_env_to_seconds` curve is deferred pending a by-ear E4B/E4XT
check (Jan).**

**Authoritative data (MPC One AMPENV display, Jan 2026-06-24):** `#200 Alpha
Pad`, XPM `<VolumeRelease>0.763780</VolumeRelease>` → MPC display **2.63 s**;
our curve gives **1.39 s** (`0.00079·e^(9.78·v)`) → **×1.90 short**. Jan's
by-ear K2000 match (Rel1 2.16 s→33 %, Rel2 0.5 s→0 %; total ≈2.66 s) agrees with
the MPC display, confirming the gap is a uniform ~1.9× under-read, NOT a K2000
perceptual difference. (The earlier "by-ear 3.48 s / ×1.3 perceptual factor"
guess is RETRACTED — it was measured on the pre-fix mis-mapped envelope.)

**Why the curve is low:** §18 (2026-06-09) fit it to **audio time-to-−40 dB**,
not the MPC's displayed segment time. An exponential release passes −40 dB
before the segment ends, so the display reads longer by a ~constant factor
(both scale with the same time-constant). §18 itself noted the threshold only
shifts the **constant**, not the 9.78 exponent.

**DEFERRED TODO — global curve recalibration (needs by-ear check):**
- `_xpm_env_to_seconds`: rescale **A 0.00079 → ~0.0015** (= `2.63/e^(9.78·0.764)`,
  exponent unchanged) so ALL segments (attack/decay/release + filter, all
  formats) match the MPC's *displayed* times.
- **Blocked on:** Jan A/B-ing a few E4B presets on the E4XT after the rescale —
  it lengthens every E4B envelope 1.9×, which was never scrutinised for release
  length. Ideally also read MPC-displayed seconds at ≥3 `XPM_VOL_DECAY` sweep
  values to confirm the exponent before refitting.
- When done, **drop the KRZ-only `_KRZ_RELEASE_FACTOR`** (the global fix
  subsumes it). See `docs/RESOLUTION_NOTES.md` §"XPM release-time recalibration".
