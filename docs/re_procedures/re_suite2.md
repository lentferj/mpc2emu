<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# RE Suite #2 — open RE tasks from the 2026-06-13 aural pass

Generator: `tests/re_banks/gen_re_suite2.py` → `/home/lentferj/temp/re_suite2/RE_SUITE2.iso`
(one bank, 4 presets). Load on the E4XT (copy to ZuluSCSI SD, rename `CDx.iso`).
Keep the baseline `RE_SUITE2.E4B` — every diff is taken against it.

All four are **READ-direction**: edit on the E4XT, **SAVE as a new preset/bank**,
send the saved `.E4B` back so the changed bytes can be diffed. (TRI PHASE is
observe-only — no save needed.) Background in `docs/aural_notes.md`.

---

## RESULTS (2026-06-14) — Jan returned `HD1-RE_SUITE2_emu.hda` (bank "RE_SUITE2 DONE")

- **1. Voice key-window — SOLVED + IMPLEMENTED.** `vpar[14]`=key low, `vpar[17]`=
  key high (baseline 0/127). Writer now sets them from the voice's zone span.
- **2. Swept EQ — SOLVED + IMPLEMENTED.** type `vpar[58]=0x20`, freq `vpar[60]`
  (=127 ≈ 1008 Hz), gain `vpar[61]`: 4 points (−24/−12/0/+18.7 dB → 0/32/64/114)
  fit **gain_dB=(byte−64)×0.375**. Band-stop→0x20 with resonance→cut depth.
- **3. Clock-sync — EOS SIDE SOLVED, MPC side pending.** cord `[src,0x61,127,0]`;
  src ids: Dwhl=0x90 Whl=0x91 Half=0x92 Qtr=0x93 8th=0x94 16th=0x95. Need the MPC
  `<Sync>` index→division table + triplet/dotted ids before wiring it up.
- **4. Triangle phase — SOLVED + IMPLEMENTED.** `+amount`→up first, `−amount`→
  down first; MPC falls first → writer negates triangle LFO cord amounts.

---

## 1. Voice key-window  — preset `VOICE KEYWIN`   (aural_notes §G/§R-window)

The single sample covers only **C2 (48) – C3 (60)**, but the E4XT voice will show
the full-range default (C-2..G8) because the writer sets no per-voice key window.
**Goal:** find the vpar bytes that hold the voice key low/high (analogous to the
already-RE'd *velocity* window vpar[18]/[21]).

**Do:** in the voice editor, set the voice **Key Window** to a distinctive range —
**low = C1 (36), high = C5 (84)** — then SAVE as a new preset/bank.

**Report:** send the saved `.E4B`. The two vpar bytes that change to 36 and 84 are
the voice key-window lo/hi. Then the writer sets them from each voice's min/max
zone key (V1 → 24-38 etc.), so a voice no longer claims C-2..G8.

## 2. Swept EQ as band-stop  — preset `SWEPT EQ CUT`   (aural_notes §K/§L)

We decided to map the MPC band-stop → E4XT **Swept EQ (cut)**. Need its byte +
how cut depth / bandwidth are stored.

**Do:** set the filter **Type = "Swept EQ, 1-octave"**; **Frequency** to a value
you note (e.g. ~1 kHz); **Gain** to **maximum CUT** (most negative). SAVE. If easy,
also do a second save at a *moderate* cut so we can scale.

**Report:** the saved `.E4B` + the on-screen **Freq** and **Gain** numbers. Reveals
`vpar[58]` for Swept-EQ-1-oct, `vpar[60]` = frequency, `vpar[61]` = the gain/cut
byte (and whether cut sits below a midpoint). Then `_XPM_FILTER_TYPE` maps MPC
band-stop (15-18) → this byte, with resonance → cut depth.

## 3. LFO clock-sync  — preset `CLOCK SYNC`   (aural_notes §D/§P)

LFO1 → Filter is already routed (audible filter wobble). EOS syncs an LFO by
patching a **Clock Divisor → LFO Trigger** (manual p.260).

**Do:** add one PatchCord, source **Clock Divisor** (set its division to **8th
note**), destination **LFO 1 Trigger** ("LFO1 Trg"), amount **+100** (must be `+`).
SAVE. If quick, repeat for **whole / half / quarter / 16th** divisions (separate
saves) so we can map every divisor source id.

**Report:** the saved `.E4B`(s). The new cord's **source byte = the Clock-Divisor
(8th-note) id**, **dest byte = the LFO-1-Trigger id**. With those, the writer can
emit a clock-divisor→LFO-trigger cord to reproduce the MPC `<Sync>` tempo lock.
(We also still need the MPC `<Sync>` index→division table: known so far 8 = quarter
triplet, 9 = 8th note.)

## 4. Triangle phase  — preset `TRI PHASE`   (OBSERVE only, aural_notes §S)

A **key-synced Triangle LFO → Pitch** (slow vibrato; phase resets per note).

**Do / Report:** play a note and watch the pitch (or the LFO graph): at note-on
does it go **UP first or DOWN first**? Tell me the direction. The MPC's triangle
differs; this decides whether the converter negates the LFO→dest cord amount
(`−amount`) for triangle/sine, and which way. No save needed.

---

After reporting, the matching `docs/aural_notes.md` items move from STASHED to
implemented, and the corresponding fixes (voice key-window; band-stop→Swept-EQ;
LFO clock-sync; triangle phase) can be written.
