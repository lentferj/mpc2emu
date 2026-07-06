<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# Hardware RE: K2000 Program Parameters (Envelopes / Filter / LFOs)

> **STATUS: OPEN — strategy + tooling ready, hardware iteration not yet done
> (2026-06-14).** This document is the plan and the toolkit for decoding the
> K2000 program object so the converter can carry envelopes, filter settings and
> LFOs the way the E4XT path already does. Nothing here is hardware-confirmed yet.

---

## 1. Honest assessment — what we can and cannot do today

| Source feature | E4XT (done) | K2000 today | After this RE |
|---|---|---|---|
| Sample mapping / multisample | ✅ | ✅ (sounds, HW-confirmed) | ✅ |
| Root / fine / coarse tune | ✅ | ✅ (keymap tuning) | ✅ |
| Amplitude envelope (ADSR) | ✅ | ❌ flat (sustain only) | 🎯 target |
| Filter type + cutoff + resonance | ✅ | ❌ none | 🎯 target |
| Filter envelope | ✅ | ❌ | 🎯 target |
| LFO (vibrato / filter / tremolo) | ✅ | ❌ | 🎯 target |
| Pitch envelope | ✅ | ❌ | stretch |

**We have the *structure* but not the *byte semantics*.** The KurzFiler source
gives us the program's segment framing (tags + lengths) and a proven-sounding
minimal program, but it treats every segment's contents as an opaque `byte[]`.
The manuals describe the *parameter model* (below) but not its binary encoding.
So we must reverse-engineer the byte layout — exactly as we did for the EMU
`vpar`/`PZT` blocks, but with a far better tool: **the K2000 SysEx interface**
(§4).

---

## 2. The VAST program model (from the K2000 manuals)

A program has 1–32 **layers**. Each layer is a **keymap** (sample playback)
feeding a **DSP algorithm**: a fixed chain `PITCH → [1–3 DSP function slots] →
AMP`. The configurable slots are chosen per algorithm (chapter 26, "DSP
Algorithms").

**Algorithm 1** is the one we care about first — it is the classic subtractive
path with a single triple-wide DSP block:

```
PITCH → { 4POLE LOPASS W/SEP | 4POLE HIPASS W/SEP | STEEP RESONANT BASS |
          TWIN PEAKS BANDPASS | PARAMETRIC EQ | HIFREQ STIMULATOR |
          DOUBLE NOTCH W/SEP | NONE } → AMP
```

`4POLE LOPASS W/SEP` = a 24 dB/oct lowpass whose **SEP** (separation) parameter
is the resonance. That maps 1:1 onto every source we convert (SF2/SFZ/MPC):
cutoff + resonance + filter-env + amp-ADSR + LFO vibrato.

Per layer the modulation sources are: **3 envelopes** (AMPENV + ENV2 + ENV3),
**2 LFOs**, **2 ASRs**, **4 FUNs**, plus the control-source matrix that routes
them to DSP-function parameters (chapter 23 LFOs, 25 Control Sources).

**Conversion target:** Algorithm 1, DSP block = `4POLE LOPASS W/SEP`, AMPENV ←
source amp ADSR, ENV2 → filter freq ← source filter env, LFO1 → pitch (vibrato)
or filter, cutoff/reson ← source filter. We do **not** need all 31 algorithms.

---

## 3. The program object structure (from corpus analysis of 201 soundsets)

`tests/re_banks/krz_reader.py` walks the program; the segment inventory over
4280 real programs / 16649 layers (`corpus.py`, `bytestats.py`):

```
program = PGM FX  (once)  then per layer:
  LYR [ASR* FUN* LFO ASR* FUN*]  ENC ENV ENC [ENC]  CAL  HOB HOB HOB HOB
```

Counts are exact where the structure is fixed: **4 HOB and 1 CAL per layer**;
~1 ENV, ~1 LFO, 2–3 ENC, ~2 ASR, ~2 FUN. Modulation segments (ASR/LFO/FUN)
appear only when that source is configured.

| Tag | Name | Len | Role (hypothesis) |
|---|---|---|---|
| 0x08 | PGM | 15 | program globals: mode=2, numLayers, bend, portamento |
| 0x0F | FX  | 7  | effect (studio/FX) selection |
| 0x09 | LYR | 15 | layer key/vel range, enable, xfade |
| 0x10 | ASR | 7  | ASR envelope (rate + control routing) |
| 0x14 | LFO | 7  | LFO: rate, shape, rate-control |
| 0x18 | FUN | 3  | `[function_enum, input_a, input_b]` |
| 0x20 | ENC | 15 | DSP-function control routing (algorithm + per-fn source/depth) |
| 0x21 | ENV | 15 | **AMP envelope** — rates + levels |
| 0x40 | CAL | 31 | keymap ref (bytes 7/8) + PITCH/sample-playback params |
| 0x50–0x53 | HOB×4 | 15 each | **the 4 DSP-function parameter pages** (PITCH, F1, F2, AMP) |

**Key structural finding:** the 4 HOB blocks share a *uniform 15-byte layout*
(byte[11] always a 0–3 enum, byte[12] always 0, a param value + control-source +
depth pattern). They are the per-DSP-function "pages"; the filter cutoff and
resonance live in the HOB block of the slot that holds the filter.

> Our current writer emits a reduced layer (`PGM LYR ENC ENV CAL HOB×4`, one ENC,
> no FX/LFO) and it plays — the K2000 tolerates a minimal program, so we can
> enrich it incrementally as each parameter group is decoded.

---

## 4. RE strategy A (PRIMARY): scripted SysEx

The K2000 exposes its object database **and** its front panel over MIDI SysEx
(chapter 30; encoders in `tests/re_banks/krz_sysex_probe.py`, codecs unit-tested
against the manual). This makes RE a tight scripted loop instead of blind
save-and-diff:

1. `READ`/`DUMP` a program's object bytes → our segment map (cross-check the
   reader).
2. `LOAD` (poke) one byte of the live object at a known offset = value V.
3. `PANEL` button presses to navigate to the parameter's edit page.
4. `PARAMVALUE` / `ALLTEXT` → read the LCD back as ASCII.
5. Sweep offset/value and read the **byte → parameter → displayed value** map
   straight off the screen. No ears required, fully automatable.

This also calibrates curves directly (e.g. poke ENV rate byte, read "Atk 0.5s"
off the display).

**Prerequisite:** a MIDI link PC↔K2000R (USB-MIDI or a DIN interface), `pip
install mido python-rtmidi`. `python3 tests/re_banks/krz_sysex_probe.py ports`
lists ports; the `K2000` class wraps the loop. **This is the open question for
Jan — see §8.**

---

## 5. RE strategy B (works today, no MIDI): forward-RE test banks

`tests/re_banks/gen_krz_program_re.py` builds banks where every preset shares one
sawtooth tone + keymap and differs by exactly one program byte. Load on the
K2000R, play C4 sustained, listen.

| Bank | Probes | What to listen for |
|---|---|---|
| `KRZ_ENVLOC` | each of the 15 **ENV** bytes (=60) | which presets change **attack / sustain / release** |
| `KRZ_ENVSW00`, `KRZ_ENVSW08` | sweep ENV[0], ENV[8] 0→127 | time vs byte-value curve |
| `KRZ_HOB0LOC`…`KRZ_HOB3LOC` | each byte of the 4 DSP pages (=64) | brightness / pitch / pan / level changes |
| `KRZ_ENCLOC` | ENC bytes | algorithm / routing changes |
| `KRZ_LYRLOC` | LYR bytes | key range / enable / xfade |

The ENV bank works immediately (the amp env is live in the baseline). The HOB
banks may show *no* change if the default algorithm has no filter in the path —
that null result is itself the signal that we must first set an algorithm with a
filter (→ strategy C / the SysEx algorithm byte).

Regenerate: `python3 tests/re_banks/gen_krz_program_re.py --floppy`
(writes `.KRZ` + Gotek `.img` + `.manifest.txt` to `/home/lentferj/temp/krz_re/`).

---

## 6. RE strategy C (filter/LFO ground truth): create-on-HW + diff

The filter and LFO only become *active* once an algorithm routes them, which we
can't yet author. So for those, capture ground truth on the instrument:

1. On the K2000R, start from a single-sample program (or ROM program 199
   "Default Program"). Set **Algorithm 1**, DSP slot = `4POLE LOPASS W/SEP`.
2. Save 6–8 variants to the Gotek floppy, each isolating **one** parameter:
   - cutoff: cutoff = 0, 30, 60, 90, 127 (everything else fixed)
   - resonance (SEP): 0, 8, 16, 24, 32
   - amp attack: 0, 20, 40, 80; amp release: 0, 20, 40, 80
   - LFO rate: slowest…fastest; LFO→pitch depth: 0…max
3. Hand the `.KRZ` files back; `krz_reader.py` + a diff script isolate the byte
   that moved (exactly the `AMP_DECAY_CAL` method from the E4XT amp-env RE).

A naming checklist for the saves lives in §7.

---

## 7. Per-parameter RE checklists

### 7a. Amp envelope (ENV, 0x21) — **start here, no MIDI needed**
Default ENV = `[0,100,0,0,0,0,0,100,0,0,0,0,0,0,0]` (KurzFiler); bytes [1] and
[7] are the non-zero defaults (level-like). K2000 amp env = Att1/Att2/Att3 +
Decay/Sustain + Rel1/Rel2/Rel3 (rates + levels).

- [ ] Load `KRZ_ENVLOC`; for each preset note attack/sustain/release effect →
      identify which byte is which rate/level. Fill the table below.
- [ ] Load `KRZ_ENVSW00`/`08`; measure time at byte=0,16,…,127 → fit a rate
      curve `_krz_env_rate(seconds)` (mirror `_fenv_rate` in the E4XT path).
- [ ] Cross-check with SysEx `PARAMVALUE` on the EditProg ENV page if MIDI is up.

```
ENV byte → meaning (fill in):
  [0]  ____________   [1]  ____________   [2] ____________
  [3]  ____________   ...                  [7]  sustain level? ____
Rate curve: byte 0 → ____ s ... byte 127 → ____ s
```

### 7b. Filter (HOB DSP page + ENC algorithm)
- [ ] Determine the **algorithm byte** (likely in ENC or LYR) by SysEx-poking,
      or by diffing two HW programs that differ only in algorithm.
- [ ] With Algorithm 1 + `4POLE LOPASS W/SEP`, diff the cutoff sweep (§6) →
      cutoff byte + its Hz mapping; diff the SEP sweep → resonance byte.
- [ ] Identify which of HOB0–3 is the filter slot vs PITCH vs AMP.

### 7c. Filter envelope (ENV2/ENV3 + control routing)
- [ ] Locate the 2nd/3rd ENV segment (corpus shows ~1 ENV per layer in factory
      patches, but filter-env patches should add one) and the ENC/FUN routing
      that sends it to filter freq.

### 7d. LFO (0x14, 7 bytes)
- [ ] Byte[5] is a small enum (0–39) — candidate **shape** or rate-control
      source. Diff LFO-rate and LFO-shape HW saves.
- [ ] Map rate byte → Hz; map the routing to pitch (vibrato) and filter.

### 7e. Pitch / keytrack (CAL, 0x40)
- [ ] CAL holds keymap ref (bytes 7/8, known) + pitch params. Diff coarse/fine
      tune HW saves to find the tune bytes (our keymap-entry tuning already
      covers per-note transposition, so this is for global layer pitch/LFO).

---

## 8. Open questions for Jan

1. **Is the K2000R connected to the computer over MIDI** (USB-MIDI interface or
   DIN)? If yes, strategy A (scripted SysEx) makes the whole RE an order of
   magnitude faster and removes the by-ear guesswork. If no, we proceed with
   strategy B (forward banks) + C (create-on-HW + diff) — slower but sufficient.
2. Preferred capture path for strategy C — same Gotek floppy save flow as the
   sample work, or SCSI/SmartMedia?
3. Priority order — amp envelope first (most universal, ready now), then filter,
   then LFO? (Recommended.)

---

## 9. RAM budget note (64 MB)

Orthogonal to program parameters: the K2000's max sample RAM is **64 MB**. The
converter already clamps KRZ banks to 64 MB (`convert.py` `_hw_limits['krz']`)
and splits larger inputs (`bank_splitter`); the default `--bank-size` is a
conservative 32 MB. Big multisamples (full pianos, orchestral sustains) should
be thinned with `--reduce-key-zones` / `--reduce-velocity-layers` and/or
down-sampled to fit — the same tools the E4XT path uses.

---

## 10. Toolkit index

- `tests/re_banks/krz_reader.py` — KRZ object reader / dumper (RE + writer verify)
- `tests/re_banks/gen_krz_program_re.py` — forward-RE test-bank generator
- `tests/re_banks/krz_sysex_probe.py` — SysEx message codecs + live `K2000` driver
- Writer being extended: `writers/krz_writer.py` (`_make_layer_segments`)
- Manuals: `…/K2000/{21 Progs, 23 LFOs, 25 Control Sources, 26 DSP Algs, 30 SysEx}.pdf`

---

## 11. RAM format ≠ disk (.KRZ) format — discovered live (2026-06-14)

Live SysEx `DUMP`/`READ`/`WRITE` return the K2000's **fixed-layout RAM object**,
NOT the tagged-segment serialization in a `.KRZ` disk file. Program 1 dumps as
498 bytes with no segment tags; keymap 1 as 796 bytes with a differently-scaled
level array. The firmware converts segment↔RAM on disk load/save.

Consequence — **two separate maps**:
- The **converter** writes the **.KRZ file/segment** format (proven sounding).
  Decoding *its* ENV/filter bytes needs the file-format RE (forward banks §5, or
  create-on-HW-and-save-to-floppy + read the `.KRZ`).
- **Live SysEx RE** decodes the **RAM** format — useful for a future "MIDI
  transfer" output mode and for the standalone K2000 MIDI-remote project
  (`docs/k2000r_midi_comms.md`), but a RAM→file bridge is still needed before it
  helps the `.KRZ` writer.

## 12. Live SysEx RE — Session 1 results (2026-06-14)

**Methodology (proven):** make a writable RAM copy via the editor's **Save to a
300+ id**, `DUMP` it as a constant baseline; then edit one env field via the
alpha-wheel (reading the AMPENV LCD to label exactly what changed), Save to a 2nd
300+ id, `DUMP`, and **byte-diff**. Clean 2-byte diffs result. (Raw SysEx
WRITE/poke of program objects is unreliable — structural bytes — so the editor is
the safe mutator; see comms doc §9.)

**First decoded field — Dec1 (decay) time, RAM format:**
- Location: **16-bit big-endian at RAM byte offset 136–137** of the program object.
- Encoding: **logarithmic time**, **~960 units per octave** (factor-of-2 in time).
  Measured: `20.0 s → 15558`, `10.0 s → 14598` (Δ = 960 for a halving).
- Higher stored value = longer time.

**AMPENV model (from the LCD):** 7 segments `Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3`,
each a (time, level) pair, plus `Loop` type + count. (Program 1 "Acoustic Piano":
times `0 / .46 / .58 / 20 / .22 / .50 / 0` s; levels `100 / 70 / 45 / 0 / 24 / 0`
% / `User`.)

**Next steps to finish the RAM amp-env map** (mechanical, ~12 more diffs):
- Confirm the 7 times are consecutive 16-bit at offsets 130,132,134,**136**,138,
  140,142 (change Att1 → expect 130; Rel1 → expect 138).
- Decode the 7 **levels** (one wheel-change on a level row → its offset + the
  %→byte scale).
- Then ENV2/ENV3 (filter env), LFO, and the DSP-function (filter) HOB pages by
  the same method.

> **Session end state:** a long unattended PANEL macro left the K2000R unresponsive
> to SysEx (hung mid-dialog) — it needs a **power-cycle**. Scratch RAM programs
> may exist at ids ~300–303 (delete with a raw `DEL`, or front-panel); ROM
> program 1 was restored intact. See the hang caveat in the comms doc.

## 13. Live SysEx RE — Session 2 results (2026-06-15, RAM amp-env mechanics)

Method refined (no hangs when each script run **completes** — keep runs short,
generous timeouts, end with a recover-to-ProgramMode; never let a script get
killed mid-save). Editor-Save scratch program to id **300+**, `DUMP`-diff against
a constant unchanged baseline (also 300+). Cursor mapping for the AMPENV page:

- **Time row:** home `cur_up×2, cur_left×8`, then `cur_right` steps along the
  times. `cur_down` is a no-op on this page (doesn't switch to the level row).
- **Level row:** home `cur_up×3, cur_left×9` lands on **Att2 level**; `cur_right`
  → Att3, Dec1, Rel1, Rel2 levels. (Att1 level @100% is at max; Rel3 = "User";
  these don't wheel-probe cleanly.)

**Encoding findings (RAM format) — all clean:**
- **Quantum = 64.** Every wheel click changes the stored value by **exactly 64
  units** (Dec1: wheel −50/−30/−10 → value −3200/−1920/−640).
- **Levels: 16-bit, 64 units per %.** Att2 level @131-132, Att3 level @133-134
  (Δ = 1600 = 64×25 for a +25 % change, on both).
- **Times: 16-bit; value is linear in clicks (64/click) but displayed seconds are
  a non-linear K2000 time table.** Dec1 time @136-137. Sampled value→time:

  | value | 12358 | 13638 | 14598 | 14918 | 15558 | 16326 |
  |---|---|---|---|---|---|---|
  | seconds | 6.5 | 8.5 | 10 | 12.5 | 20 | 60 (max) |

  For the converter this is a **seconds→value lookup** (sample more points to
  refine). Higher value = longer time; max Dec1 ≈ 60 s at 16326.

**Offsets mapped so far (program-object RAM, prog 1):** Att2 level @131, Att3
level @133, Dec1 time @136.

**Open challenge — bit-packing.** The level/time 16-bit fields are NOT a clean
contiguous block: Att2L@131, Att3L@133, Dec1T@136 overlap a naive 7×16-bit layout,
and Att3L's high byte carried a stray `0x80` (an absolute offset of ~32768) while
Att2L's did not — i.e. **neighbouring fields share bytes via high bits**. Finishing
the map needs per-field diffs that mask out the shared bits, best done with a
human watching (to re-home the cursor and avoid unattended hangs).

> This RAM map serves the future MIDI-transfer mode + the K2000 remote project.
> The converter's `.KRZ` writer still needs the **file-format** env bytes (a
> separate map — see §11, and the forward-RE banks in §5).

**Session-2 addendum (more offsets + lesson):** additional 16-bit env fields at
**@138-139 and @140-141**, both changing 64/click (so they are *times*, not
levels — they did not move the level row). Confirmed times appear consecutive
(16-bit) at **@136, @138, @140**; levels consecutive at **@131, @133**. The
naive "7 contiguous times + 7 contiguous levels" model still doesn't fit (a level
block at 129-142 would collide with the time at 136), so the two blocks are
interleaved/packed in a way still to be resolved.

**Lesson for finishing the map:** always read **both** the time row (LCD line 2)
*and* the level row (line 3) after each wheel — the AMPENV cursor frequently lands
on a *time* when you expect a level, and vice-versa. Disambiguate every diff by
which row actually moved. Best done with a human re-homing the cursor between
fields (the page cursor wraps unpredictably and `cur_down` is a no-op here).

## 14. RAM amp-env MAP — collaborative session (2026-06-15) — NEAR-COMPLETE

Decisive method (gentle, reliable): Jan set a reference program on the K2000R
front-panel with **distinctive times AND levels** (prog 300, single layer, 274 B:
times `0.02 0.04 0.06 0.08 0.10 0.12 0.14` s, levels `10 20 30 40 50 60 %`,
AmpEnv mode = User). I then did **one gentle edit per field** (change it, read the
LCD to label it, save to 301, `DUMP`-diff vs 300) — no hangs.

**AmpEnv MODE** lives in the Rel3-level display slot (`User`↔`Natural`); must be
`User` to edit (Natural = K2000 auto-shapes it, no manual values). So there are
**6 editable levels (Att1–Rel2)** + **7 times (Att1–Rel3)**.

**Encodings (both confirmed on multiple segments):**
- **LEVEL = % × 64** (16-bit). Att1: 10 %→641 (=0x0281), Att2: 20 %→1281
  (=0x0501); live Δ on Att2 20→50 % = +1920 = 64/%. (Matches the earlier
  498-byte object — encoding is object-independent even though offsets aren't.)
- **TIME = non-linear K2000 table** (15-bit). Value↔seconds samples:
  `261=.02 327=.04 394=.06 460=.08 527=.10 576=.12 648=.14` and (from §13)
  `14598=10 15558=20 16326=60 (max)`. → converter uses a **seconds→value LUT**.
- **Editor click = +64** to the stored value (both times and levels).

**Field byte map (prog 300, env block ≈ @129; offsets are object-size-dependent):**

| field | byte(s) that move | note |
|---|---|---|
| Att1 level | @129(-130) | 16-bit ×64, byte-aligned: 0x0281=641 |
| Att1 time  | @130 | shares @130 with Att1 level |
| Att2 level | @131-132 | 0x0501=1281 ✓ |
| Att3 level | @133 | |
| Dec1 level | @135 | |
| Rel1 level | @137-138 | |
| Rel2 level | @139-140 | |
| times (7)  | even bytes @130,132,134,136,138,140,142 | 15-bit, bit15 holds the neighbour level's high bit |

**Structure = a tight bit-packed stream**, not byte-aligned fields: early segments
(Att1, Att2) read as clean 16-bit, but later ones drift because each time/level
field is packed at a sub-byte bit offset, so consecutive fields share bytes (a
level edit flips bit-15 of the adjacent time word, etc.). The field *locations*
and *encodings* above are solid; the exact bit boundaries of the packed stream are
the one remaining nuance (needs a bit-offset model, not more hardware).

> This completes the RAM amp-env map to the practical level: all 13 fields located,
> both encodings pinned, the time LUT sampled. Enough to read/write amp envelopes
> over SysEx for a live-transfer mode and the MIDI-remote project. The `.KRZ`
> writer still needs the separate *file*-format env map (§11).

## 15. RAM ENV2/ENV3 + LFO (2026-06-15) — same gentle method, +CPU throttle

**CRITICAL operational fix (Jan):** the K2000's old CPU **crashes/garbles under a
MIDI flood** — every wedge was an over-fast SysEx stream, not the saves. Fix:
**throttle every outgoing SysEx to ≥120 ms apart** (`tests/re_banks/krz_sysex_live.py`
ThrottledOut) AND allow **~0.5 s settle after each page change** (the LCD redraw is
slow; reading sooner returns a blank/garbled screen). With both, zero crashes.

**ENV2 / ENV3 (filter / aux envelopes) — DONE by analogy.** Same 7-segment
structure as AMPENV (Att1-3, Dec1, Rel1-3; same ×64 levels + non-linear time LUT),
but always 7 real levels (no User/Natural mode — that slot is AMPENV-only). The
three envelopes are **consecutive 16-byte blocks**: AMPENV @128, **ENV2 @144,
ENV3 @160** (e.g. ENV2 Att2 time @148-149, ENV3 @164-165). New time-LUT point:
1.20 s = 4032.

**LFO (page params, prog 300 274-byte object):** block ~@90, ahead of the envs.
Entry cursor = LFO1 MnRate (no moves needed); cur_right → MxRate, RateCt, Shape,
Phase; cur_down → LFO2.

| LFO1 param | offset | encoding |
|---|---|---|
| MnRate | @90-91 (16-bit) | 2.00 Hz=2944, 3.00 Hz=3584; 64/click; display 0.1 Hz/click |
| MxRate | @91-92 (16-bit, shares @91) | 64/click; display 0.01 Hz/click |
| Shape  | @94 (byte) | Sine=64, +Sine=128 → ≈ shape_index × 64 |
| RateCt / Phase | not yet | RateCt = a control-source enum; Phase didn't register |

Same **bit-packed** sharing as the envelopes (MnRate/MxRate share byte @91). LFO2
mirrors LFO1 at a further offset (cur_down; not measured). The LFO→destination
**depth/routing** lives in the layer control matrix (a separate structure, not the
LFO page) — that's the next thing to RE for full vibrato conversion.

## 16. FILE-FORMAT decode (the converter's actual target) — Gotek disk-save, 2026-06-15

Decoded by editing #199 (RAM copy #301) on the K2000, **disk-saving variants to a
Gotek floppy, and diffing the `.KRZ` files** (NOT the RAM format). This is what the
`.KRZ` writer must emit. Template = `DFLT.KRZ` (the #199 default), full structure
`PGM FX LYR ASR ASR FUN FUN LFO ASR FUN FUN ENC ENV ENC ENC CAL HOB HOB HOB HOB`;
the **4 HOB = the 4 DSP function pages F1/F2/F3/F4-AMP**.

**Filter** (set F1 block = 4POLE LOPASS W/SEP) — all confirmed against hardware Hz/dB:
- type: **`HOB0[0]`** = 50 (4POLE LOPASS), 62 = NONE
- cutoff (F1 Freq): **`HOB0[1]` signed semitones**, `Hz = 440·2^((b−9)/12)` (b = note−60);
  range −48 (16 Hz) … +79 (25088 Hz)
- resonance (F2 RES): **`HOB1[1]` = round(dB×2)**, 0…48 = 0…24 dB
- SEP (F3) = `HOB2`, leave default. Filter is F1+F2 (+F3 SEP), AMP = F4.
- filter-env routing (ENV2→F1 Freq): **`HOB0[5]` = control source, `HOB0[6]` = depth**

**Envelopes** — 7 segments as **interleaved (time, level) bytes at seg[2..14]**
(t,l,t,l,t,l,t,l,t,l,t,l,t = 7 times + 6 levels; Rel3 has no level):
- **AMPENV = the `ENV` segment (0x21)**; **ENV2 (filter env) = an `ENC` segment (0x20)**
- **time byte = steps(seconds) + 3** — confirmed: AMPENV 30..60 s → 249..255, ENV2 1..7 s → 53..198
- **level byte = raw signed %** — confirmed: 90/80/70/60/50, 50/25/0/25/50/75
- AMPENV User/Natural mode = a flag in an `ENC` segment (`ENC[1]` 1=Natural → 0=User)

K2000 envelope time grid (for `steps()`): 0–2 s @0.02 · 2–5 @0.04 · 5–10 @0.10 ·
10–15 @0.50 · 15–25 @1.0 · 25–60 @5.0. (Same grid gives the RAM value =197+64·steps.)

**LFO** — params in the `LFO` segment; **LFO→PITCH routing = `CAL[21]` source / `CAL[22]` depth**.
Rate/shape/phase byte encodings pending (have HW values: LFO1 1/24 Hz +Sine 90°,
LFO2 2.5/0.01 Hz Square 270°).

**Converter implication:** clone `DFLT.KRZ`, set `HOB0[0]=50`, write cutoff/reson
(`HOB0[1]`,`HOB1[1]`), AMPENV into the `ENV` segment and ENV2 into its `ENC` segment
with the time/level encodings above, and the routing depths. Filter + both
envelopes are now fully writable in file format.

### §16 addendum — LFO + routing depths (file format, 2026-06-15)

**LFO1** (the `LFO` segment 0x14; clean isolate, LFO2 left default):
- rate (MnRate) = **`LFO[2]` = round(26 + 10·Hz)** — linear (1Hz=36, 2Hz=46, 10Hz=126)
- shape = **`LFO[4]`** enum: Sine=0, +Sine=1, Triangle=2, …
- phase = **`LFO[5]`** = 1 + deg/45 (0°=1, 180°=5)
- MxRate ≈ `LFO[3]`; LFO2 in a second (0x10-tagged) segment — mirror.

**Control-source codes:** ENV2 = 121, LFO1 = 114 (the routing `source` byte).

**Routing depths** (byte located; cents↔byte slightly non-linear, 2-point linear fits):
- filter-env (ENV2→F1 Freq) depth = **`HOB0[6]`** ≈ round(29 + cents·0.0091); +1200ct→40, +10800ct→127
- LFO→pitch depth = **`CAL[22]`** ≈ round(70 + cents·0.0073); +1200ct→79, +7200ct→123 (sign in the signed byte; −5000ct→−117)

**MODULATION MAP COMPLETE** for the converter: filter (type/cutoff/reson), AMPENV,
ENV2 (filter env), filter-env routing+depth, LFO1 (rate/shape/phase), LFO→pitch
routing+depth. Depth encodings are the only approximate part (refine with a low-end
point if needed). Converter = clone `DFLT.KRZ` + patch these bytes.

---

## 17. Session 7 (2026-06-15) — sonic validation + ALG filter-type lever + a wedge

Autonomous audio campaign on **#311 (BuzzWave 158 → 4-pole lopass)**, closed-loop
rig (`tests/re_banks/krz_audio_measure.py`). Two encodings sonically confirmed:

- **Cutoff = faithful.** Sweeping F1 Coarse from open (25088 Hz) down to ~250 Hz,
  the recorded **spectral centroid tracks the displayed cutoff** monotonically
  (≈0.76× the display Hz in the linear mid-band). Confirms display-cutoff =
  actual-cutoff, so the `cutoff_byte = signed semitones` encoding is correct.
  (My `cal_cutoff.py` `corner()` -3 dB detector is broken — clusters ~250 Hz
  regardless; use the centroid, which works. `cal_cutoff.txt` has the data.)
- **Resonance = faithful.** Cutoff fixed at 1568 Hz, sweeping F2 RES: the acoustic
  resonant-peak boost grows ≈linearly to ~21 dB at full, **≈0.44 dB per wheel
  click** while the display moves 0.5 dB/click. Confirms `reson_byte = round(dB×2)`
  is sonically right (display-dB ≈ acoustic-dB). `cal_reson.txt`.
  NOTE: on the F2 page the resonance value is the **`Adjust:` field**, not labelled
  "RES" (a regex looking for "RES" grabs the wrong column).

**Filter-type RE lever (Jan's suggestion — "change step 2 of the algorithm"):**
On the **ALG page** (`EDIT → ALG`) the algorithm chain is `PITCH → 4POLE LOPASS
W/SEP → AMP` on row 5. The **entry cursor lands directly on step 2** (the filter
DSP block): `paramvalue()` reads `"4POLE LOPASS W/SEP"` immediately, no cursor
move needed. Cursor map (non-destructive moves): cur_left/right walk
PITCH↔filter↔AMP↔`Algorithm:` ; the filter block is the default selection.
**Wheeling that block changes the filter type** — this is the route to RE the
missing types (4POLE HIPASS, 2POLE LOPASS, BANDPASS, NOTCH, …; byte `HOB0[0]`,
known: LP=50, NONE=62).

**⚠ Wedge lesson (cost a HW recovery — happened while Jan was away):** wheeling
step 2 off `4POLE LOPASS W/SEP` (a **double-wide** function spanning two DSP slots)
forces the K2000 to **recompute/relink the whole algorithm**, blanking the LCD for
**> 2.5 s**. My scripts fired `w:+1` then immediately retried `get_screen_text`
several times in a tight loop → an effective SysEx flood on the recompute-busy old
CPU → it stopped answering screen queries (link stayed up; CPU wedged). **Rule for
filter-type RE:** change **one** function, then **sleep ≥ 4–5 s of total silence**
before a single screen read; never loop screen-queries while the algorithm is
re-rendering. And the **byte encoding still needs a Gotek disk-save + diff** (audio
only proves the *type*, not `HOB0[0]`), so this is a Jan-present task: set each
type → disk-save → read `HOB0[0]`, optionally A/B the spectrum (LP cuts highs, HP
cuts lows, BP both, notch dips a band).

### 17a. Filter-type catalog (2026-06-16, after power-cycle recovery)

With the **safe cadence** (one `w:+1`, then ≥5 s of total silence, then a single
screen read — NO tight retry loops) the full step-2 DSP function list was captured
without a wedge. Step 2 of Algorithm 1 (double-wide block, fed by PITCH → AMP)
cycles through **8 functions**, wrapping at index 8:

| ALG idx | function name          | source-format mapping |
|--------:|------------------------|-----------------------|
| 0 | `4POLE LOPASS W/SEP`  | **lowpass**  (HOB0[0]=50, known) |
| 1 | `4POLE HIPASS W/SEP`  | **highpass** (byte TBD) |
| 2 | `TWIN PEAKS BANDPASS` | **bandpass** (byte TBD) |
| 3 | `DOUBLE NOTCH W/SEP`  | **notch**    (byte TBD) |
| 4 | `NONE`                | bypass (HOB0[0]=62, known) |
| 5 | `HIFREQ STIMULATOR`   | (enhancer — no source analogue) |
| 6 | `PARAMETRIC EQ`       | (EQ — no source analogue) |
| 7 | `STEEP RESONANT BASS` | (special — no source analogue) |

The four standard types every source format uses (LP/HP/BP/notch) are all present
at indices 0–3. **ALG-page navigation:** `EDIT → ALG`; the **entry cursor lands
directly on step 2**, so `paramvalue()` reads the filter name immediately and
`w:±1` cycles the type. `cur_left/right` walk PITCH↔filter↔AMP↔`Algorithm:`.

**Why the live sonic A/B was inconclusive (and the reliable path):** wheeling the
filter type in the *edit buffer* did **not** cleanly change the sounding voice in
my tests (LP/HP/notch all measured ~4000–4300 Hz centroid at a nominal 1.5 kHz
cutoff; HIPASS did not remove lows). Two compounding causes: (a) on the ALG page
the algorithm change may not re-link into the live voice until the program is
**saved/committed**; (b) F1-page cutoff context shifts after the page hop. The
clean way to characterise a type sonically is to **save the program** (RAM slot or
disk) with that type + a baked-in cutoff, then play the *saved* program. The audio
rig itself is healthy — verified by an open-filter sanity take (centroid 9885 Hz,
= BuzzWave).

**To capture the `HOB0[0]` bytes for HP/BP/notch (Jan-present, ~5 min):**
1. On the K2000: `EDIT #311 → ALG`, set step 2 to each type in turn, and
   **disk-save** each to the Gotek `.img` with distinct names (e.g. `FHP`, `FBP`,
   `FNOTCH`; `FLP` as the known-50 control).
2. Move the Gotek stick to the PC.
3. Read `HOB0[0]` of each saved program (mtools → `krz_reader.py`); LP=50, NONE=62
   are the known anchors. Then add the 3 new type bytes to `writers/krz_writer.py`
   (`_patch_layer` filter-type switch) — currently it only emits lowpass (50).

**JACK note (rig hygiene):** creating a fresh `jack.Client` per recording leaks
metadata DBs / semaphores into `/dev/shm` and eventually throws
`BDB2034 unable to allocate memory for mutex`, corrupting takes. Use **one
persistent client** reused across takes (`/home/lentferj/temp/persist_rec.py`,
class `Rec`). Do NOT `rm` `/dev/shm/jack_db-*` — it's the live jackd's DB.

### 17b. Filter-type bytes captured + implemented (2026-06-16) — RESOLVED

Jan disk-saved the four type-variants (driven over SysEx onto RAM slots 312-315,
each verified on-screen before save) into `REF_FILT.img::FILTERS.KRZ`. Read back
`HOB0(0x50)[0]` with `krz_reader.py`:

| program | K2000 function       | HOB0[0] |
|--------:|----------------------|--------:|
| 312     | 4POLE LOPASS W/SEP   | **50** (control — confirms method) |
| 313     | 4POLE HIPASS W/SEP   | **54** |
| 314     | TWIN PEAKS BANDPASS  | **55** |
| 315     | DOUBLE NOTCH W/SEP   | **56** |

(+ `NONE` = 62, known.) A tidy contiguous block 54/55/56 for the three resonant
non-LP types. All four share #311's other settings, so HOB0[1]=cutoff (79=open)
and HOB1[1]=reson are unchanged across types — the "W/SEP" structure is identical,
only `HOB0[0]` selects the family.

**Implemented** in `writers/krz_writer.py`: `_k2_filter_byte(xpm_type)` maps the
XPM `FilterType` enum (see `e4b_writer._XPM_FILTER_TYPE`) → K2000 byte
(Low/Model/MPC→50, High→54, Band/Band-boost→55, BS-notch→56), called from
`_patch_layer` (replaces the hard-coded `hob_f1[0]=50`). End-to-end verified:
`write_krz` of a 4-voice bank (Low4/High4/Band4/BSnotch) → `krz_reader` reads
50/54/55/56. Test artefact: `/home/lentferj/temp/FTYPE_RT.KRZ`.

### 17c. First HW load-test of converted MPC banks (2026-06-16) — two bugs fixed

Jan loaded converted MPC (XPM) banks on the K2000R; two bugs surfaced + fixed in
`writers/krz_writer.py`:

1. **One-shots were force-looped → unnatural held notes (no sustain/release).**
   The Soundfilehead loop bit is **0x80: CLEAR = loop ON, SET = one-shot** (per
   krz_reader, HW-confirmed). The writer hard-coded `flags=0x70` (0x80 clear) for
   *every* sample — only ever tested on looped Patchman corpora, so one-shots got
   looped on their zero-length end region → held notes stuck on the final sample.
   Fix: `sfh_flags = 0x70 if looped else 0xF0`. Per-sample, so a bank with mixed
   loops (e.g. Organ) keeps its real sustain loops AND plays one-shots out.

2. **MPC Velocity→Filter ignored → silent bass.** MPC bass presets ship with
   `Cutoff=0.0` **and `VelocityToFilter=1.0`**; the writer mapped cutoff 0.0 → 16 Hz
   (4-pole LP slammed shut) and dropped the velocity term → silence. Jan's MPC
   ground truth (Bass-MS20 Harmonic): VelToFilter 127 "pushes the cutoff up very
   far" (≈open, not a hard bypass); zeroing it makes the static Cutoff engage. So
   the audible cutoff = `Cutoff + VelocityToFilter`. We render a *static* K2000
   program, so we **fold** the velocity term into the effective cutoff
   (`eff = min(1.0, filter_cutoff + max(0, velocity_to_filter))`) rather than a
   K2000 VelTrk sweep — a VelTrk sweep from the 16 Hz floor would re-mute
   softly-played notes that the MPC keeps audible. Result: BASSMDACE cutoff byte
   208 (16 Hz) → 79 (25 kHz, open); all banks audible.
   (VelTrk *was* located on the F1 page for a true per-note sweep — left/down to
   `VelTrk:Nct`, calib pts staged on RAM 316=350ct/317=4200ct — but the fold
   matches the hardware behaviour and avoids the low-velocity-silence trap, so the
   true VelTrk routing is deferred unless a bright + partial-VelToFilter preset
   needs it.)

### 17d. K2000 full filter catalog from the Musician's Guide (Ch 14 + Ch 26)

Jan pointed to the manual (pp. 253ff = Ch 14 DSP Functions; pp. 421ff = Ch 26
algorithm charts). The K2000 has **3 filter slopes** (1-pole 6 dB/oct, 2-pole
12 dB/oct, 4-pole 24 dB/oct) — we currently use ONLY Algorithm 1's 4-pole filters,
which is too steep for the MPC's predominant 2-pole (`Low2`) sources.

**Full filter list (Ch 14):** ONE-POLE LOWPASS, TWO-POLE LOWPASS, 2-POLE LP -6 dB
RES (LOPAS2), 2-POLE LP +12 dB RES (LP2RES), 4POLE LOPASS W/SEP, GATED LOWPASS
(LPGATE), ONE-POLE HIGHPASS, TWO-POLE HIGHPASS, 4POLE HIPASS W/SEP, ONE-POLE
ALLPASS, TWO-POLE ALLPASS, TWO-POLE NOTCH, 2-POLE NOTCH FIXED, DOUBLE NOTCH W/SEP,
TWO-POLE BANDPASS, 2-POLE BANDPASS FIXED, TWIN PEAKS BANDPASS.

**Where they live (Ch 26 algorithm charts) — the filters are NOT all in Alg 1:**
- **Alg 1** block-2 (double-wide): HIFREQ STIM / PARAMETRIC EQ / STEEP RESONANT
  BASS / 4POLE LOPASS W/SEP / 4POLE HIPASS W/SEP / TWIN PEAKS BANDPASS /
  DOUBLE NOTCH W/SEP / NONE.  (the 24 dB filters — what we use today)
- **Alg 2–7** block-2: 2PARAM SHAPER / **2POLE LOWPASS** / BANDPASS FILT /
  NOTCH FILTER / 2POLE ALLPASS / PARA BASS/TREBLE/MID / NONE.  (the 12 dB filters)
- **Alg 4–24** single blocks: LOPASS / HIPASS / ALPASS (1-pole 6 dB) + GAIN /
  SHAPER / DIST and the oscillators (SINE/SAW/…) for synthesis.
- **Alg 5/9/11/21** 3rd block: LP2RES / LOPAS2 / HIPAS2 / SHAPE2 / BAND2 / NOTCH2 /
  LPGATE.
- **Alg 3** = `PITCH → [2-pole filter / EQ] → AMP` — cleanest single-2-pole-filter
  layout (block-3 = AMP U/AMP L/BAL/AMP).  Good candidate template for 2-pole.

**Parameter ranges (Ch 14), file-format relevant:**
- F1 FRQ page (all filters): Coarse **C0 16 Hz … G10 25088 Hz** (= our cutoff
  byte −48..+79, confirmed); Fine ±100 ct; KeyTrk ±250 ct/key; **VelTrk ±10800 ct**
  (= velocity→cutoff, ±9 oct — the proper home for MPC VelocityToFilter, a true
  per-note sweep up to 9 octaves); Pad 0/6/12/18 dB; Src1/Src2 (control-source list
  ±10800 ct).
- F2 RES page (2POLE LOWPASS): Adjust **−12 to +24 dB** (NOTE: 2-pole resonance
  can CUT, range differs from the 4-pole path where we map reson 0..24 dB →
  byte 0..48); VelTrk ±30 dB.
- 1-pole LOPASS/HIPASS: resonance FIXED at −3 dB (no F2 RES page). LOPAS2 fixed
  −6 dB, LP2RES fixed +12 dB.

**Implication / TODO:** to faithfully carry source filter *slope*, add a 2-pole
algorithm template (Alg 3) and map XPM `filter_type`: Low1→1-pole, Low2→2-pole,
Low4+→4-pole (current); High1/2→1/2-pole HP; Band2→2-pole BP; notch→2-pole NOTCH.
Needs HW RE of: the algorithm-selector byte (Alg 1 vs 3), the 2-pole filter-type
bytes, and the 2-pole F2 RES (−12..+24 dB) encoding — all via the Gotek
disk-save+diff route.

### 17e. Control-Source code list (manual Ch 25) — VALIDATES the RE'd Src bytes

The K2000 Musician's Guide Ch 25 "Main Control Source List" gives the control-source
*numbers*, and they are **identical to the file-format Src bytes I reverse-engineered**
(LFO1=114, ENV2=121 both match) — so the `.KRZ` Src1/Src2 byte = the manual's
control-source number. No HW RE needed for routing *sources* (only the byte offsets
of each Src/Depth slot per page, and the depth calibration, still need disk-save).

| code | source | code | source |
|----:|--------|----:|--------|
| 128 | OFF | 100 | **Attack Velocity (AttVel)** |
| 1 | MWheel (MIDI 01) | 101 | InvAttVel |
| 2 | Breath | 104 | RelVel |
| 4 | Foot | 105 | Bi-AVel (bipolar vel) |
| 7 | Volume | 102/103 | PPress / BPPress |
| 10 | Pan | 98/99 | KeyNum / BKeyNum |
| 33 | MPress (mono pressure) | 110/111 | ASR1 / ASR2 |
| 34 | BMPress | 112/113 | FUN1 / FUN2 |
| 35 | PWheel | 114 | **LFO1** (RE-confirmed) |
| 36 | Bi-Mwl | 115 | LFO1 phase |
| 64 | Sustain | 116 | LFO2 |
| 106/107 | VTRIG1/2 | 117 | LFO2 phase |
| 120 | AMPENV | 121 | **ENV2** (RE-confirmed) |
| 127 | ON | 122 | ENV3 |

**So MPC Velocity→Filter can be a real routing**: F1 Src = `100` (AttVel) + depth
(±10800 ct), in addition to (or instead of) today's cutoff-fold. Mod-wheel→vibrato
= LFO target + the depth controlled by MWheel(1); mod-wheel→filter = F1 Src=1; etc.
Still pending HW (disk-save) per page: the **byte offset of Src1/Depth/Src2/DptCtl/
Min/Max** within each HOB, and the **depth byte↔(cents/dB) calibration** (have rough
2-pt fits for ENV2→F1 and LFO1→pitch).

### 17f. 2-pole filter measured + RE programs staged (2026-06-16, autonomous)

Confirmed via the audio rig (no disk needed) that the **2POLE LOWPASS is much
gentler than the 4-pole** — at the same 1568 Hz cutoff on BuzzWave: 2-pole centroid
**9679 Hz** vs 4-pole **3725 Hz** (the 2-pole passes far more high end = 12 dB/oct
vs 24). This is the better match for MPC `Low1/Low2` sources. Setting Algorithm 3 on
the ALG page auto-selects `PITCH → 2POLE LOWPASS → BAL → AMP`.

**RE programs STAGED in RAM for the next disk-save batch** (drive-by-SysEx, Jan
disk-saves):
- **#320** = Algorithm 3, 2POLE LOWPASS, cutoff 1568 Hz, resonance 0
- **#321** = Algorithm 1, 4POLE LOPASS, cutoff 1568 Hz (4-pole control for diffing)
- **#322** = Algorithm 3, 2POLE LOWPASS, cutoff 1568 Hz, resonance +12.0 dB
  (decode the 2-pole F2-RES −12..+24 dB encoding vs the 4-pole's 0..24)
- (#316/#317 = VelTrk 350ct/4200ct — superseded by the cutoff-fold, low priority)

Disk-saving #320–#322 yields: the **algorithm-selector byte** (Alg 1 vs 3), the
full **Algorithm-3 program template** (different layout — has a BAL block), the
**2POLE LOWPASS filter-type byte**, and the **2-pole resonance encoding**. With
those + the control-source list (§17e) the writer can carry source filter *slope*.

**Implementation plan (after the disk-save):**
1. Build `_TPL_LAYER_ALG3` from #320 (as `_TPL_LAYER` was built from #199).
2. `_k2_filter_byte` → return (template_id, filter_byte): Low1/Low2→Alg3 2-pole;
   Low4+→Alg1 4-pole; High1/2→Alg3 2-pole HP (needs its byte); Band2→Alg3 2-pole
   BP; notch→Alg3 2-pole notch; etc.  `_write_program_object` picks the template.
3. 2-pole resonance uses its own −12..+24 dB encoding (decode from #322).
4. Optional: real velocity→filter via F1 Src=100 (AttVel) once the Src2 byte
   offset is decoded (needs a disk-save with Src2 set).

### 17g. 2-pole lowpass IMPLEMENTED (2026-06-16) — RESOLVED

POLE2LP.KRZ (disk-saved #320-322) decoded: Algorithm 3 and Algorithm 1 share an
**identical program layout** — only three bytes differ between the 2-pole and
4-pole paths:
- **HOB0[0]** = filter type: 2POLE LOWPASS = **2** (vs 4POLE LOPASS = 50)
- **HOB2[0]** = F3 block: BAL = **39** (Alg 3) vs SEP = **18** (Alg 1)
- **CAL[29]** = algorithm number: **3** vs 1
- 2-pole resonance: HOB1[1] = `round(dB×2)` (same as 4-pole; #322 = 24 @ +12 dB),
  range extends to −12 dB but MPC resonance 0..1 → 0..+24 dB only.

Implemented as `_k2_filter_plan(xpm_type) -> (algorithm, HOB0[0], HOB2[0])` in
`writers/krz_writer.py`, applied in `_patch_layer` (patches HOB0[0], HOB2[0]=seg
0x52, CAL[29]). **Low1/Low2 → 2-pole (Alg 3); Low4+/HP/BP/notch → 4-pole (Alg 1).**
Byte-exact to the HW-verified #320/#321/#322 (unit-checked). Bass/Keys/Organ banks
now use the gentler 12 dB filter. No separate template needed.

**Still 4-pole (no 2-pole byte RE'd yet):** High1/2 (→4POLE HIPASS), Band2
(→TWIN PEAKS), notch (→DOUBLE NOTCH).  The K2000 has 2-pole HP/BP/NOTCH in Alg 2-7;
their HOB0[0] bytes need another disk-save batch if higher fidelity is wanted.

### 17h. 1-pole lowpass + type-29 fix (2026-06-16) — RESOLVED

POLE1LP.KRZ (#323, Algorithm 16, `PITCH→LOPASS→NONE→AMP`) decoded — the 1-pole adds
one more distinguishing byte vs the 2/4-pole:

| slope | CAL[29] algo | HOB0[0] filter | HOB1[0] F2 | HOB2[0] F3 | resonance |
|---|---|---|---|---|---|
| 4-pole (24 dB) | 1  | 50 | 16 (RES) | 18 (SEP) | yes |
| 2-pole (12 dB) | 3  | 2  | 16 (RES) | 39 (BAL) | yes |
| 1-pole (6 dB)  | 16 | 15 | 61 (NONE)| 18       | **no** (fixed −3 dB) |

`_k2_filter_plan` now returns `(algo, HOB0[0], HOB1[0], HOB2[0], has_resonance)`.
**Slope is now matched exactly: Low1→1-pole, Low2→2-pole, Low4+→4-pole.** Also
fixed **FilterType 29 (MPC3000 LPF, 12 dB) → 2-pole** — it was hitting the 4-pole
default branch, and it's the 2nd most common filter on the hardware (1334 presets
vs Low2's 1340; Low1 = 137). 1-pole writes no resonance byte (F2=NONE). Byte-exact
to HW #320/#321/#323; suite passes. The 6 demo banks use only Low2/Low4/Band so
they're unaffected by this change.

**Cutoff on slope change:** because the K2000 now matches each source slope to its
exact filter, the cutoff frequency transfers 1:1 (it's the −3 dB corner regardless
of slope) — no adjustment needed.  The only place a slope is *forced* to differ is
the E4XT path (no 1-pole → Low1 maps to 2-pole); there we still keep the literal
source cutoff rather than shifting it (a slope difference can't be corrected by
moving the corner without also misstating it).  N.B. the manual notes the K2000's
own 1-pole vs 2-pole of a family have a ~1-octave perceptual brightness offset
(HIPASS C3 ≈ HIPAS2 C4) — relevant only if perceptual-match were ever wanted.

### 17i. 2-pole moved off Algorithm 3 (bypass) → Algorithm 5; + 2-pole BANDPASS (2026-06-16)

**Jan caught that Algorithm 3 has a bypass path around the filter** — which explained
a measurement that had looked off: the Alg-3 2-pole centroid was 9679 Hz vs ~9900
open (barely filtering) because the BAL/double-output split routed dry signal past
the filter.  Switched the 2-pole filters to **Algorithm 5 with F3=NONE** — a clean
single-output series path `PITCH -> filter -> NONE -> AMP`.  Re-RE'd (POLE2A5.KRZ,
#320/#324):

| Alg-5 (bypass-free) | CAL[29] | HOB0[0] | HOB1[0] F2 | HOB2[0] F3 |
|---|---|---|---|---|
| 2POLE LOWPASS | 5 | 2 | 16 (RES) | 60 (NONE) |
| BANDPASS FILT | 5 | 3 | 16 (WID) | 60 (NONE) |

vs the rejected Alg-3 2-pole the only changes are CAL[29] 3→5 and HOB2[0] 39→60;
filter byte (2) and cutoff location (HOB0[1]) unchanged.  **Added 2-pole BANDPASS
(byte 3)** for Band2(11)/BB-2P(19) — 21 source presets; Band4+/BB-4P+ stay on the
4-pole TWIN PEAKS.  Bandpass F2 is *width* not resonance, so no resonance byte is
written (has_res=False) — it uses the K2000 default width; mapping MPC resonance→
width is a future refinement (needs the width-byte encoding RE'd).  Bass/Keys/Organ
banks regenerated + redeployed on Alg 5.  1-pole (Alg 16) and 4-pole (Alg 1) are
single-output series (4-pole measured properly filtered at centroid 3725) so they
were unaffected.

**Still deferred:** 2-pole HP (`HIPAS2`) — it lives only in block 3 of Alg 5/9/etc
(no block-2 2-pole HP exists), so its cutoff would sit in HOB2 not HOB0, needing a
writer special-case.  High2 (18 presets) stays on the 4-pole HIPASS for now.
2-pole notch skipped (0 sources).

### 17j. Autonomous validation + corpus cross-check (2026-06-16)

Software-only work (no disk-saves) while Jan was AFK:

- **Regression tests added** — `tests/test_krz_writer.py` pins every HW-RE'd encoding
  (filter-byte map for all FilterTypes, loop flag 0x70/0xF0, velocity-fold cutoff,
  resonance, 1-pole no-resonance, byte encoders, write→read round-trip).  Run with
  `python3 tests/test_krz_writer.py`.

- **Corpus cross-check** (`/home/lentferj/temp/corpus_filter_analysis.py` over the
  160 Patchman soundsets = 3188 programs / 14212 layers) **validated the filter
  byte map against real K2000 production files**: HOB0[0] = 2 (2POLE LOWPASS, 12019
  layers), 3 (BANDPASS), 15 (1-pole LOPASS), 50 (4POLE), 56 (DOUBLE NOTCH), 62
  (NONE) all confirmed.  Real soundsets use **Algorithm 2** for 2-pole LP (never the
  bypassed Alg 3 — corroborating Jan's catch); our Alg-5 choice is byte-exact to a
  K2000-made program so it is valid, just less common.  KEY: real BANDPASS programs
  cluster their width byte (HOB1[1]) at **~57-70 (median ~64)**, not the 0 default a
  fresh-selected bandpass gives — so the writer now emits width **64** (`_K2_BP_
  DEFAULT_WIDTH`) for the 2-pole bandpass (was thin at 0).

- **Batch robustness** — 27 XPMs sampled across the whole hardware expansion tree:
  20/20 valid keygroup instruments produced valid KRZ; the 7 "failures" were all
  correct rejections (macOS `._` resource forks + drum programs the converter
  intentionally skips).  Zero writer bugs at scale.

- **Cross-format → KRZ** — SF2, SFZ, EXS, GIG, E4B all convert to structurally valid
  KRZ (parse + program/HOB segments).  Filter mapping is format-agnostic (lives in
  the writer, keyed on the shared `filter_type`), so it is covered by the writer
  tests regardless of source format.

### 17k. Modulation-routing byte offsets located via corpus (2026-06-16)

`/home/lentferj/temp/corpus_routing.py` scans every layer of the 160 Patchman
soundsets (14212 layers) and, per (segment, byte-index), measures what fraction of
values fall in the control-source code set (manual Ch25).  Positions dominated by
control-source codes ARE the Src/route fields — and the codes that show up confirm
the manual + earlier RE (ENV2=121, LFO1=114, AttVel=100, MWheel=1, LFO2=116,
MPress=33).  This locates the modulation matrix without a single disk-save:

**HOB0 (F1 FREQ / filter):**
- `[5]` = **Src1 source** (ENV2=121 dominant — confirms the filter-env route) ; `[6]` = Src1 depth
- `[7]` = **Src2 source** (top non-zero: AttVel=100, MWheel=1) — i.e. **velocity→filter
  and mod-wheel→filter live in HOB0[7]** ; `[8]` = DptCtl, `[9]`/`[10]`/`[11]` = depth/min/max

**HOB3 (F4 AMP / amplitude):**
- `[0]` = AMP function (1) ; `[7]` = **Src2 source** (MWheel=1, AttVel=100) → velocity→amp
  / mod-wheel→amp ; `[10]` = source with **LFO1=114** → LFO→amp (tremolo)

**CAL (pitch + keymap):**
- `[8]` = keymap id (low byte) ; `[21]` = **pitch Src1** (LFO1=114 = vibrato; FUN1=112
  default) ; `[26]` = **pitch Src2** (LFO1/LFO2=116/MPress=33)

**Enables (future work):** velocity→filter (real routing, vs today's static fold),
mod-wheel→filter, velocity→amp, mod-wheel→amp, LFO→amp tremolo, vibrato (LFO→pitch).
**Still needs HW**: the depth byte ↔ (cents/dB) calibration.  The manual gives the
RANGES (F1 Src depth ±10800 ct, AMP ±96 dB) but the byte curve (linear? offset?)
must be pinned with disk-saves at known displayed values — my earlier 2-pt ENV2
depth fit (byte≈29+ct·0.0091) disagrees with a naive linear ±10800 map, so it needs
re-measuring before these routings are implemented.
