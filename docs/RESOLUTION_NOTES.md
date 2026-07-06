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
