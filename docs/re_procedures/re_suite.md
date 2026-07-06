<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# RE Suite — one bank for all open E4XT reverse-engineering tasks

Generator: `tests/re_banks/gen_re_suite.py` → `/home/lentferj/temp/re_suite/RE_SUITE.iso`
(one bank, 10 presets). Load it on the E4XT (copy to ZuluSCSI SD, rename `CDx.iso`).

Two kinds of preset:
- **WRITE-direction** (just load + observe): the voice-count presets.
- **READ-direction** (edit on the E4XT, **save as a new preset/bank**, send the
  saved `.E4B` back so the changed bytes can be diffed against the baseline):
  ZONE BASE, MW PITCH, MW LFO1, MW LFO2.

Keep the original `RE_SUITE.E4B` — it is the baseline every diff is taken against.

---

## 1. Voice-count limit  — presets `08/10/11/12/14/16 VOICES`

Each preset's file declares exactly N voices; each voice covers a distinct key
band and plays a distinct pitch. A 15-voice brass preset only showed V1–V10 in
the editor, so the E4XT caps somewhere.

**Do:** open each preset's voice editor; note the **highest voice number listed**
(V1…Vn) and **how many distinct pitches sound** when you sweep the keyboard.

RESULTS so far: 16 disjoint voices load fully (no voice-count cap); 16 fully
OVERLAPPING voices also load + play (no per-key overlap cap). A 15-voice brass
preset (≈10 zones/voice) showed only 10 — its first 10 voices total 5282 bytes /
111 zones; voice 11 → 5720 B / 118 zones. So the cap is either total voice-data
**bytes** (~5.3 KB) or total **zones** (~111).

**`20 VOICES` / `24 VOICES`** — single-zone (few zones) but large byte-size (24 ≈
7.3 KB). Discriminator:
- load fully → NOT bytes → the cap is total **zones** (~111).
- cap at ~17 → **byte** limit (~5.3 KB).

**`MZ 14V 11Z`** — 14 voices, each an 11-zone keymap (154 zones), brass-like.
Report how many voices show.

**Report:** for `08…24 VOICES` + `MZ 14V 11Z` — voices listed + audible.

## 1b. Per-key voice OVERLAP — RESOLVED (no limit)

`OVL 12/16 SAMEKEY` (12/16 voices all on keys 48–72) both load and play across
that range → no per-key overlap cap. (Presets kept for reference.)

**Report:** voices listed + voices sounding per note for each.
- If both show 12 / 16 → no per-key limit; the brass issue is elsewhere (tell me).
- If both cap at the same number (~10) → that's the **per-key voice-overlap
  limit**; we then thin *overlap* (not total voices) to that number.

## 2. Voice tuning + volume bytes  — preset `ZONE BASE`

RESULTS (all in **vpar**, signed bytes):
- **Key Transpose** +12 → `vpar[34]` = `0x0C`  ✓  (from `B.012-RE_SUITE JL.E4B`)
- **Fine Tune** +50 units (1/64-st each) → `vpar[36]` = `0x32`  ✓  (from `B.012-RE_SUITE JL.E4B`)
- **Volume** −12 dB → `vpar[54]` = `0xF4`  ✓  (from `B.012-RE_SUITE JL.E4B`)
- **Coarse Tune** +12 st → `vpar[35]` = `0x0C`  ✓  (from `B.012-RE_SUITE CT JL.E4B`, 2026-06-13)

All three tuning bytes are now fully RE'd and implemented:
- `vpar[34]` = Key Transpose (keyboard pitch remap, −24..+24 st)
- `vpar[35]` = Coarse Tune (sample repitch, −72..+24 st; maps from MPC `TuneCoarse`)
- `vpar[36]` = Fine Tune (1/64-semitone units, −64..+63; maps from MPC `TuneFine` in cents × 64/100)

**RESOLVED.** ✓

## 3. ModWheel source id  — preset `MW PITCH`  ✅ RESOLVED 2026-06-13

**Result (from `B.013- RE_SUITE CrdAmt.E4B`):** the saved cord is
`src=0x11 dst=0x30(Pitch) +50%` → **ModWheel source id = `0x11`** (`0x10` is the
adjacent Pitch Wheel). Corroborated by the EOS default cord 03
`src=0x11 dst=0xaa +13%` (ModWheel→C02Amt) Jan flagged.

## 4. PatchCord-amount destination id  — `MW LFO1 PITCH`, `MW LFO2 FILT`  ✅ RESOLVED 2026-06-13

LFO cords (4-byte `src,dst,amt,00` in voice[190:270]):
- `MW LFO1 PITCH` — LFO1→Pitch in **Cord 02** (`src=0x60 dst=0x30`).
- `MW LFO2 FILT` — LFO2→Filter in **Cord 08** (`src=0x68 dst=0x38`).

**Result:** Jan added `ModWheel→C02Amt` (saved as cord 09: `src=0x11 dst=0xaa`)
and `ModWheel→C08Amt` (cord 09: `src=0x11 dst=0xb0`). So the **Cord-N-Amount
destination is linear: `dst = 0xA8 + N`** (`0xA8..0xBF` for cords 0..23) — the
manual's 24 consecutive "Cord 0-23 Amount" destinations.

**Implemented** in `e4b_writer._build_voice`: each LFO→dest cord at slot N with
depth D and voice `wheel_to_lfo = Kw` is split into a static part `D*(1-Kw)` (the
LFO cord's amount) plus a `ModWheel(0x11) → CordN-Amount(0xA8+N)` cord of `D*Kw`
in a free slot. `xpm_parser` maps `<KeygroupWheelToLfo>` → `VoiceLayer.wheel_to_lfo`.
(Depth-split math is the principled model; the exact cord-amount-modulation scale
could use one more hardware check, but byte ids are confirmed.)

---

**All RE tasks in this bank are now resolved:**
- §1 E4XT voice cap — **no cap found** (20/24 single-zone + MZ 14V all load fully;
  the 15-voice brass→10 was preset-specific). `MAX_VOICES_PER_PRESET = None`.
- §2 Voice tuning + volume — **done** (vpar[34]=Key Transpose, vpar[35]=Coarse
  Tune, vpar[36]=Fine Tune in 1/64-st, vpar[54]=Volume).
- §3 ModWheel source id = `0x11`; §4 Cord-N-Amount dest = `0xA8 + N` — **done**.

**Still needs hardware (§3 + §4 above):** the ModWheel source id + the
PatchCord-amount destination id — the last piece for **KeygroupWheelToLfo** depth
gating. Everything else in this bank is resolved.
