<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# EMU E4B Bank Format — Reverse-Engineered Reference

This document describes the on-disk layout of `.E4B` bank files for the
**E-MU Emulator 4 / E4XT / E4K (EOS 4.x)**, as reverse-engineered by the
mpc2emu project. It covers the **Bank → Preset → Voice → Zone → Sample**
hierarchy, the byte-level layout of each structure, and a number of
non-obvious encoding conventions that took real hardware testing to pin
down.

The goal of this document is to let other implementers (sample-conversion
tools, librarians, archival projects, …) write or read E4B files without
repeating the trial-and-error this project went through. It is **not**
official E-MU documentation — it is the result of differential analysis of
hardware-saved banks, commercial CD-ROMs, and source code from prior
reverse-engineering efforts (see [Sources & Attribution](#sources--attribution)).

> **Implementation reference:** the canonical, always-up-to-date version of
> this layout lives in [`writers/e4b_writer.py`](../writers/e4b_writer.py)
> (serialization) — that file's doc-comments and this document should be kept
> in sync. Where they disagree, trust the code (and file an issue).

---

## 1. Overview: container & hierarchy

An E4B file is an **IFF-like container** (`FORM E4B0`, big-endian chunk
sizes — note this is *not* standard EA-IFF-85: the FORM size field's exact
semantics differ subtly from the spec; see [§6.1](#61-form-size-quirk)).

```
FORM <size> E4B0
  TOC1   — table of contents (32-byte entries: one per chunk below — NOT EMSt)
  E4Ma   — 256-byte "multimap" (MIDI channel → preset routing)
  E4P1   — preset chunk #1   (one per Preset)
  E4P1   — preset chunk #2
   …
  E3S1   — sample chunk #1   (one per Sample, 16-bit PCM)
  E3S1   — sample chunk #2
   …
  EMSt   — 1366-byte master setup, ALWAYS the last chunk, NOT in the TOC
```

The trailing `EMSt` chunk and the `<size>` field both follow the EMU
convention rather than standard IFF — both are essential for the file to load
in real hardware and in the reference loader (emu.tools e-xplorer); see
[§6.1](#61-form-size-quirk).

This maps directly onto the in-memory model in
[`models/common.py`](../models/common.py):

```
Bank
 ├── name
 ├── presets: [Preset, …]          ──► one E4P1 chunk each
 │     ├── name, program_number
 │     ├── volume, pan, transpose  (preset-global)
 │     └── voices: [VoiceLayer, …] ──► packed sequentially inside the E4P1 body
 │           ├── envelope / filter parameters
 │           └── zones: [ZoneMapping, …] ──► secondary zone table entries
 │                 ├── sample_name  ──► resolved to a 1-based sample index
 │                 ├── lo_key/hi_key, lo_vel/hi_vel, root_key
 │                 └── volume, pan, transpose, fine_tune
 └── samples: [SampleData, …]      ──► one E3S1 chunk each
       ├── name, sample_rate, channels, bit_depth (16-bit only)
       ├── loop_type, loop_start, loop_end
       └── data: raw 16-bit LE PCM
```

Key structural facts that fall out of this hierarchy:

- **A Preset is a flat list of Voices** — there is no separate "layer" or
  "keygroup" container; MPC "Layers" map 1:1 to E4B "Voices"
  (`VoiceLayer` in the model).
- **A Voice owns its own zone table** — key/velocity ranges are resolved at
  the zone level, not the voice level (though, confusingly, the voice header
  *also* carries a redundant velocity range — see [§5.2](#52-voice-level-velocity-range-mirrors-the-zone-range)).
- **Zones reference Samples by index, not by name** — the on-disk format has
  no concept of a sample name lookup; the writer must build a
  `name → 1-based index` map across the *whole bank* before serializing any
  preset (`sample_name_to_idx` in `write_e4b()`).
- **Samples are bank-global** — the same `E3S1` chunk can be (and usually is)
  referenced from many zones across many presets. `bank_splitter.py`
  deduplicates by `SampleData.name` when assembling output banks.

---

## 2. IFF container details

### 2.1 Chunk header

Every chunk (including the outer `FORM`) is:

```
tag        4 bytes  ASCII, e.g. 'TOC1', 'E4Ma', 'E4P1', 'E3S1'
size       4 bytes  big-endian u32 — length of the data that follows
data       <size> bytes
pad        0 or 1 byte — present iff size is odd, value 0x00 (word alignment)
```

### 2.2 TOC entry (32 bytes)

One entry per chunk that follows `E4Ma` onward (in mpc2emu's writer: one
`E4Ma` + one per preset + one per sample). Layout:

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0:4`   | 4  | `tag`         | chunk tag, e.g. `E4P1`, `E3S1`, `E4Ma` |
| `4:8`   | 4  | `data_size`   | BE u32 — chunk **data** size (matches the chunk's own size field) |
| `8:12`  | 4  | `file_offset` | BE u32 — absolute byte offset of the chunk's `tag` field from file start |
| `12:14` | 2  | `index`       | BE u16 — 0 for `E4Ma`, 0-based preset index, **1-based** sample index |
| `14:30` | 16 | `name`        | space-padded ASCII (16 bytes, see [§6.2](#62-name-encoding)) |
| `30`    | 1  | `0x00`        | null |
| `31`    | 1  | MIDI program  | `0x00` = "any" in mpc2emu's output |

### 2.3 E4Ma multimap (256 bytes)

A fixed-size routing table mapping MIDI channels to presets. mpc2emu always
writes a permissive default (every preset reachable on every channel) — see
`_build_e4ma()`. This block has not been fully reverse-engineered; the
default 22×12-byte repeating pattern is taken verbatim from a hardware
reference bank and is known to produce a working "all presets on all
channels" routing.

---

## 3. Preset (`E4P1` chunk body)

Fixed 82-byte header followed by N variable-length voice blocks, packed
**back-to-back with no padding or separator** (see [§5.1](#51-voice-packing-no-gapterminator-between-voices)).

### 3.1 Preset header (82 bytes)

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0:2`   | 2  | `index`      | BE u16, 0-based preset index within the bank |
| `2:18`  | 16 | `name`       | space-padded ASCII |
| `18`    | 1  | `0x00`       | null |
| `19`    | 1  | `0x52`       | constant (always observed as `0x52`) |
| `20:22` | 2  | `num_voices` | BE u16 — **must** equal the number of voice blocks that follow |
| `22:28` | 6  | —            | zero |
| `28`    | 1  | `volume`     | `0x78` (=120) is mpc2emu's default master volume |
| `29:41` | 12 | —            | zero |
| `41`    | 1  | multi-voice flag | `0x04` when `num_voices > 1` (confirmed from hardware + Kirk Hunter commercial banks) |
| `42`    | 1  | —            | zero |
| `43`    | 1  | multi-voice flag | `0x01` when `num_voices > 1` |
| `44:52` | 8  | —            | zero |
| `52:56` | 4  | constant     | `0x52 0x23 0x00 0x7E` |
| `56:60` | 4  | MIDI routing | `0xFF 0xFF 0xFF 0xFF` = any note / any channel |
| `60:82` | 22 | —            | zero |
| `82+`   | …  | voice blocks | one per `VoiceLayer`, see §4 |

The two "multi-voice flag" bytes (`[41]`/`[43]`) are set together whenever a
preset has more than one voice; their individual semantics are not fully
understood, but writing them only for `num_voices > 1` round-trips correctly
against every reference bank checked so far.

---

## 4. Voice block

A voice block is **284 fixed bytes** (`VOICE_FIXED`) followed by
`n_zones × 22 bytes` (`ZONE_ENTRY`) of secondary zone-table entries — and,
**only for the last voice in the preset**, two trailing `0x00` bytes
(see [§5.1](#51-voice-packing-no-gapterminator-between-voices)).

```
voice[  0:110]  voice parameters ("vpar")
voice[110:174]  primary zone table  (4 × 16 bytes incl. filter envelope)
voice[174:190]  zero padding (16 bytes)
voice[190:270]  modulation-routing matrix (20 × 4-byte slots)
voice[270:284]  zero padding (14 bytes)
voice[284: ]    secondary zone table — n_zones × 22-byte entries
                (+ 2 trailing 0x00 bytes, last voice only)
```

### 4.1 Voice parameters — `vpar` (110 bytes)

Confirmed byte positions, from differential analysis of hardware-saved
multi-voice banks:

| Offset | Field | Notes |
|---|---|---|
| `2:4`   | zone-table trailer offset | BE u16, **relative to this voice's own start**; equals `VOICE_FIXED + n_zones × ZONE_ENTRY`. This is how the E4XT locates the start of the *next* voice — see [§5.1](#51-voice-packing-no-gapterminator-between-voices) |
| `4`     | `n_zones`           | zone count; E4XT reads exactly this many secondary-zone entries |
| `7`     | `0x64`              | constant observed in working voices |
| `17`    | `0x7F`              | constant (max value, possibly a redundant/legacy velocity field) |
| `18`    | voice `lo_vel`      | mirrors the voice's aggregate zone velocity range — see [§5.2](#52-voice-level-velocity-range-mirrors-the-zone-range) |
| `21`    | voice `hi_vel`      | ditto |
| `25`    | `0x7F`              | constant |
| `34`    | coarse transpose    | **signed** semitones (`+12` → `0x0C`). Hardware-RE'd 2026-06-13 (`RE_SUITE` ZONE BASE tp+12) |
| `36`    | fine tune           | **signed** cents (`+50` → `0x32`). Hardware-RE'd 2026-06-13 (`RE_SUITE` ZONE BASE ft+50c) |
| `38`    | Non-Transpose flag  | `0x01` = pitch fixed (does not follow key), `0x00` = key-tracking. Confirmed from `B.010-Voices_RevEng.E4B` |
| `42`    | Chorus Amount       | Voice/Tuning page; UI `0–100%` → `0–127` linear (`round(pct/100×127)`), `0` = off. Hardware-confirmed 2026-06-08 |
| `51`    | `0x80`              | constant |
| `54`    | volume              | **signed** dB (`−12 dB` → `0xF4`, `0` = unity). Hardware-RE'd 2026-06-13 (`RE_SUITE` ZONE BASE vol-12); supersedes the earlier "amplitude gain" guess |
| `58`    | VCF filter type     | see [§4.4](#44-filter-type-mapping-xpm--e4b) |
| `60`    | VCF cutoff          | `0`≈57 Hz … `255`=20 kHz, exponential curve |
| `61`    | VCF Q / resonance   | `0`–`127`, linear |

The amplitude envelope is **not** in `vpar` — it lives in the primary zone
table at `PZT[0:12]` (see [§4.2](#42-primary-zone-table-64-bytes-voice110174)).
All other `vpar` bytes are zero in mpc2emu's output; some may carry meaning in
commercial banks that has not yet been decoded (e.g. LFO routing, chorus stereo
width — a separate byte from the Chorus Amount at `vpar[42]`).

### 4.2 Primary zone table (64 bytes, `voice[110:174]`)

A 4×16-byte block holding two **6-stage envelopes**, identical in structure:
the **amplitude envelope** at `PZT[0:12]` and the **filter envelope** at
`PZT[14:26]`. Each stage is a `rate`/`level` byte pair.

**Amplitude envelope — `PZT[0:12]`** (hardware-confirmed 2026-06-08 from
`AMPENV_SETME.E4B`; decay byte isolated via the `AMP_DECAY_CAL.E4B` sweep where
only `PZT[4]` varies):

| Stage | Offsets | Meaning |
|---|---|---|
| Attack 1  | `[0]`/`[1]`   | rate / level (rise from silence) |
| Attack 2  | `[2]`/`[3]`   | rate / level (default level `0x7F` = +100%) |
| Decay 1   | `[4]`/`[5]`   | rate / level — **`[4]` = decay rate**, `[5]` = sustain level |
| Decay 2   | `[6]`/`[7]`   | rate / level (holds at sustain) |
| Release 1 | `[8]`/`[9]`   | rate / level (default rate `0x14`=20; level `0` → silence) |
| Release 2 | `[10]`/`[11]` | rate / level |
| (mode)    | `[12]`/`[13]` | `0x03 0x00` constant — envelope mode/pointer |

**Filter envelope — `PZT[14:26]`** (confirmed via diff against
`B.005-FltEnvTest.E4B`):

| Stage | Offsets | Meaning |
|---|---|---|
| Attack 1  | `[14]`/`[15]` | rate / level |
| Attack 2  | `[16]`/`[17]` | rate / level (default level `0x7F` = +100%) |
| Decay 1   | `[18]`/`[19]` | rate / level (default level `0x7E` ≈ +99%) |
| Decay 2   | `[20]`/`[21]` | rate / level (default level `0x7F` = +100%) |
| Release 1 | `[22]`/`[23]` | rate / level (default rate `20`) |
| Release 2 | `[24]`/`[25]` | rate / level |

Both envelopes use the standard-ADSR mapping (per the EOS manual: "set the '2'
levels = the '1' levels and the '2' rates to 0") — Attack rises to full, Decay
falls to the sustain level (held through Decay 2), Release falls to silence.

**Encoding:**
- *Level* — a signed percentage `-100..+100` is stored as
  `round(pct × 127 / 100) & 0xFF` (see `_fenv_level()`).
- *Rate* — a time in seconds maps to an EOS rate byte (`0..127`) by a
  **hardware-calibrated log fit** (2026-06-08, 6 Decay-1 decay-to-silence
  measurements in `AMP_DECAY_CAL.E4B`): `time_s = 0.0310 · e^(0.0581 · rate)`,
  i.e. `rate = round((ln(seconds) − ln 0.0310) / 0.0581)` clamped to `0..127`.
  **Direction:** `0` = fastest (≈ instant), higher = slower (`127` ≈ 47 s).
  See `_fenv_rate()` / `_fenv_seconds()` in `e4b_writer.py` and the inverse
  `_fenv_rate_inv()` in `e4b_parser.py`. (Measured points: rate 8 → 0.034 s,
  16 → 0.098 s, 24 → 0.169 s, 32 → 0.198 s, 48 → 0.454 s, 64 → 1.225 s.)

When a voice has no meaningful filter envelope (`filter_env_amount ≈ 0`),
mpc2emu writes the filter section from a fixed template (`_PRIMARY_ZONE_TMPL`)
taken byte-for-byte from a hardware reference preset; the amp envelope at
`PZT[0:12]` is always written from the voice's `env_*` fields.

**LFO 1 and LFO 2** parameters also live in this table (decoded 2026-06-10 from
`B.011-LFO1 settings.E4B`). LFO 2 is an exact **+8 mirror** of LFO 1:

| LFO1 | LFO2 | Param | Encoding |
|---|---|---|---|
| `PZT[42]` | `PZT[50]` | Rate | `0–127`, default 64. **Hz curve** (E4XT menu readout): byte 0=0.08 Hz, 64=4.12 Hz, 127=18.01 Hz — *not* exponential; fit `ln(Hz)=−3.006e-4·b²+0.08082·b−2.5257` (3-point, refineable) |
| `PZT[43]` | `PZT[51]` | Shape | **signed**: `-1`=Random, `0`=Triangle, `1`=Sine, `2`=Sawtooth, `3`=Square, `4–7`=33/25/16/12 % Pulse, `8–11`=Pat Octaves/Fifth+Octave/Sus4/Neener, `12–13`=Sine 1,2 / 1,3,5, `14`=Sine+Noise, `15`=Hemi-quaver |
| `PZT[44]` | `PZT[52]` | Delay | `0–127` → 0–20 s |
| `PZT[45]` | `PZT[53]` | Variation | `0–127` = **0–100 %** per-note rate randomisation (`round(pct/100×127)`, 100 %=127) |
| `PZT[46]` | `PZT[54]` | Sync | `0`=Key Sync, `1`=Free Run |

Sine=1 **confirmed** from the `LFO1+2 SINE` preset (`PZT[43]` and `PZT[51]` both
`01`). Between the two LFO blocks, `PZT[48]`=`01` is constant (unknown). The
**Lag processors** follow: `PZT[57]`=Lag0, `PZT[59]`=Lag1 (confirmed from the
P011 preset's lag0:5 / lag1:10 markers).

### 4.3 Modulation-routing matrix (`voice[190:...]`, PatchCords)

A list of 4-byte **PatchCords**, each `[source, destination, amount, flag]`:

| Byte | Field | Notes |
|---|---|---|
| 0 | source id      | e.g. `0x50` = Filter Envelope |
| 1 | destination id | e.g. `0x38` = Filter Frequency (cutoff) |
| 2 | **amount**     | signed, `round(pct/100 × 127)` → `+100%`=`0x7F`, `−100%`=`0x81`, `0%`=`0`. Confirmed from `B.010-CordAmountTest.E4B` (2026-06-09) |
| 3 | flag           | `0x00` in observed cords |

UI cord number = storage slot number (so the E4XT "Cord 05" = slot 5, amount byte
`mod[22]`). An **all-zero** table is valid for a plain, unmodulated key-tracking
("KT") voice. Two cases need a populated table (`_MOD_TMPL`, the EOS factory
default cord set extracted from hardware):

1. **Non-Transpose ("NT") voices** — the E4XT requires a populated table to
   recognise the voice as valid (an all-zero table → silent/invisible on
   hardware).
2. **Filter-envelope voices** (KT *or* NT) — the filter-envelope shape at
   `PZT[14:26]` only reaches the cutoff through the **slot-5** cord
   `src=0x50 → dst=0x38` (E4XT UI "Cord 05"), which is **amount 0 by default**.
   `mpc2emu` writes the depth `round(filter_env_amount × 127)` into its amount
   byte `mod[22]`. Without it the filter envelope is inert. (Slot/scaling
   confirmed from `B.010-CordAmountTest.E4B`; the non-zero `16 08 7F` cord at
   slot 7 is a *different* default routing — the E4XT's "Cord 07".)

**Decoded cord ids** (default-preset routings 2026-06-09 + `B.011` P012 mod
matrix 2026-06-10):

| Source id | Meaning | | Dest id | Meaning |
|---|---|---|---|---|
| `0x50` | Filter Envelope | | `0x30` | Pitch |
| `0x60` / `0x61` | LFO1 ~ / + | | `0x38` | Filter Frequency (cutoff) |
| `0x68` / `0x69` | LFO2 ~ / + | | `0x39` | **Filter-Q (resonance)** |
| `0x50` | Filter Envelope | | `0x4A` | **Vol-Env Decay (VEnvDcy)** |
| `0x0C` | Velocity        | | `0x40` | (Velocity default dest) |
| `0x08` | Key (note)      | | `0x30` | Pitch |
| `0x11` | **ModWheel**    | | `0x60` | **LFO1 Rate** (`Lfo1Rt`) |
| (id `0x60`/`0x68` as a *destination* = that LFO's **Rate**) | | | `0x68` | **LFO2 Rate** (`Lfo2Rt`) |

ModWheel source `0x11` hardware-RE'd 2026-06-13 (`RE_SUITE` MW PITCH:
`[0x11 → 0x30]` ModWheel→Pitch). LFO-Rate destinations `0x60`/`0x68` from
`RE_SUITE` MW LFO1/LFO2 (`Cord 09: modwl → Lfo1Rt/Lfo2Rt +100%`). **Note:** these
gate LFO *rate* (speed), **not** depth — the MPC `KeygroupWheelToLfo` gates LFO
*depth*, which needs the still-unknown "PatchCord N Amount" destination.

All four LFO source ids **confirmed** (~ bipolar / + unipolar): LFO1 `0x60`/`0x61`,
LFO2 `0x68`/`0x69`. Decoded from P012's `Chrd10 LFO-FltQ` cords: `0x60→0x39`
LFO1~→Filter-Q (+50 %), `0x61→0x39` LFO1+→Filter-Q (+75 %), `0x68→0x30`
LFO2~→Pitch (+99 %), `0x69→0x4A` LFO2+→VEnvDcy (−99 %).

Default-preset cords (all amount 0 until dialled in): Cord 02 = slot 2
`60 30` LFO1→Pitch; Cord 04 = slot 4 `0C 38` Velocity→Filter-Freq; Cord 05 =
slot 5 `50 38` FilterEnv→Filter-Freq; Cord 06 = slot 6 `08 38` Key→Filter-Freq.
`mpc2emu` writes LFO→Filter/Q (and LFO2→Pitch) routings into the **free slots
8+** as `[src, dst, amount, 0]`. Still undecoded defaults: `src 0x10`→Pitch,
`0x11`→`0xAA`, slot-7 `16 08`.

### 4.4 Filter-type mapping (XPM → E4B)

`vpar[58]` selects the VCF type. The E4XT supports far fewer filter types
than the MPC's XPM `FilterType` enum (0–29), so mpc2emu maps each MPC type to
the closest available E4XT equivalent. The E4XT-side byte values below are
hardware-confirmed (from `FLTTYPES.E4B`, `FLTTYPES2.E4B`, JL AnalogBank K2
Bass); the MPC→E4XT mapping itself is a best-effort approximation:

| E4XT type | Byte | | E4XT type | Byte |
|---|---|---|---|---|
| 4-Pole LP (4PLP) | `0x00` | | 2nd-Order HP | `0x08` |
| 2-Pole LP (2PLP) | `0x01` | | 4th-Order HP | `0x09` |
| 6-Pole LP (6PLP) | `0x02` | | 2nd-Order BP | `0x10` |
| | | | 4th-Order BP | `0x11` |
| | | | Contrary BP (notch-like) | `0x12` |

The full MPC `FilterType` → E4XT byte table lives in `_XPM_FILTER_TYPE` in
`e4b_writer.py` — e.g. MPC "Low 6" (6-pole LP) → `0x02`, MPC "High 1" → `0x08`
(closest available HP), all band-stop/notch types → `0x12`, all formant/model
types → `0x00` (no E4XT equivalent, falls back to plain 4-pole LP).

#### `vpar[58]` encoding: complete map (hardware-confirmed 2026-06-08)

Reverse-engineered in full from `B.005-FILTERTYPES.E4B` (one preset per EOS
filter type, set on hardware and saved). The value is **`byte = group_base |
variant`** — the variant (slope / order) lives in the low 3 bits; it is *not*
the filter's position in the EOS menu.

| Group | Base | Members (byte) |
|-------|------|----------------|
| Lowpass    | `0x00` | 4-Pole `0x00`, 2-Pole `0x01`, 6-Pole `0x02` |
| Highpass   | `0x08` | 2nd-Order `0x08`, 4th-Order `0x09` |
| Bandpass   | `0x10` | 2nd-Order `0x10`, 4th-Order `0x11`, Contrary `0x12` |
| Swept EQ   | `0x20` | 1-oct `0x20`, 2→1-oct `0x21`, 3→1-oct `0x22` |
| Phaser     | `0x40` | Phaser 1 `0x40`, Phaser 2 `0x41`, Bat Phaser `0x42` |
| Flanger    | `0x48` | Flanger Lite `0x48` |
| Vocal      | `0x50` | Ah-Ay-Ee `0x50`, Oo-Ah `0x51` |
| Morph      | `0x60` | Dual EQ `0x60`, 2EQ+Lowpass `0x61`, 2EQ+Expression `0x62` |
| Peak/Shelf | `0x68` | Peak/Shelf Morph `0x68` |

Bits 3–6 of the base select the group (LP=`0x00`, HP=`0x08`, BP=`0x10`,
Swept=`0x20`; the effect/morph groups set bit 6 and sub-select via bits 3–5:
Phaser=`0x40`, Flanger=`0x48`, Vocal=`0x50`, Morph=`0x60`, Peak/Shelf=`0x68`).
An unrecognised byte displays as "2-Pole Lowpass" on the E4XT (its default).

The full table lives in `_E4XT_FILTER_BYTES` (`writers/e4b_writer.py`).  MPC XPM
has no Swept/Phaser/Flanger/Morph filters, so those are not reachable from XPM
sources; the MPC Vocal-formant types now map to the E4XT Vocal filters (`0x50`/
`0x51`) instead of falling back to LP.

### 4.5 Secondary zone table — zone entry (22 bytes)

Each entry maps a key/velocity range to a sample. Only a subset of the 22
bytes is currently understood:

| Offset | Size | Field | Notes |
|---|---|---|---|
| `2`     | 1 | `lo_key`     | MIDI note 0–127 |
| `5`     | 1 | `hi_key`     | MIDI note 0–127 |
| `6`     | 1 | `lo_vel`     | MIDI velocity 0–127 |
| `9`     | 1 | `hi_vel`     | MIDI velocity 0–127 |
| `10:12` | 2 | `sample_idx` | **BE u16**, 1-based — see [§5.3](#53-sample-index-is-a-2-byte-be-u16-not-a-single-byte) |
| `14`    | 1 | `root_key`   | MIDI note — playback root, overrides the sample's own root note |

All other bytes are zero in mpc2emu's output.

---

## 5. Encoding conventions & hard-won lessons

This section documents conventions — and bugs — that were *not* obvious from
a single reference file, and only surfaced through systematic differential
testing across many hardware-saved banks. They are recorded here in detail
because they are exactly the kind of trap a future implementer is likely to
fall into again.

### 5.1 Voice packing: no gap/terminator between voices

Voices are packed **back-to-back with zero bytes between them** — there is
**no terminator entry** separating one voice's zone table from the next
voice's header. The E4XT locates the start of voice *N+1* purely by
arithmetic: `this_voice_start + VOICE_FIXED + n_zones × ZONE_ENTRY`, which is
exactly the value stored at `vpar[2:4]` of voice *N*.

Only the **last** voice in a preset gets two trailing `0x00 0x00` bytes after
its zone table, and the preset body ends there.

> **Trap:** an earlier analysis pass misread the first bytes of the *next*
> voice's `vpar` header as a 22-byte "terminator entry" with `lo_key(1) >
> hi_key(0)` — because `vpar[2]` (the high byte of *that* voice's own trailer
> offset) is always ≥ 1 (every voice is > 255 bytes), and `vpar[5]` is always
> 0, which together coincidentally look like a "lo > hi" sentinel. Writing a
> real 22-byte terminator shifts every subsequent voice 22 bytes later than
> where the E4XT expects it, landing on garbage — which manifests on hardware
> as **"voice count = 1"** (the E4XT gives up after the first voice because
> the second one doesn't parse). This was confirmed self-consistent with zero
> leftover bytes across four independent hardware-confirmed multi-voice
> examples.

### 5.2 Voice-level velocity range mirrors the zone range

`vpar[18]`/`vpar[21]` (voice-level `lo_vel`/`hi_vel`) are **not** independent
of the zone table — they must be set to the **min/max of all of the voice's
zones'** `lo_vel`/`hi_vel` values (`voice_lo_vel`/`voice_hi_vel` in
`_build_voice()`). Confirmed byte-for-byte against a hand-fixed reference
bank (`B.003-Vel-Split — Inst-Piano-F9 Grand Piano`) whose values match the
source XPM's per-layer `VelStart`/`VelEnd` exactly.

> **Trap:** writing only the per-zone `lo_vel`/`entry[6]` (or worse, omitting
> it and leaving it zero) without also deriving and writing the matching
> voice-level `vpar[18]`/`vpar[21]` causes velocity-switched layers to
> **layer instead of switch** — every voice plays starting at velocity 0, so
> all velocity zones sound simultaneously rather than being selected by
> playing dynamics.
>
> A subtler version of the same trap: this bug can look "fixed" if your test
> banks happen to only use velocity ranges that start at 0, because then
> `lo_vel = 0` is correct by coincidence. The bug only becomes visible with
> banks that actually split velocity at a non-zero boundary.

### 5.3 Sample index is a 2-byte BE u16, not a single byte

The zone-entry `sample_idx` field at `entry[10:12]` is a **big-endian
unsigned 16-bit** value, 1-based — consistent with the BE-u16 indexing
convention used everywhere else in the format (`E3S1` sample header
`[0:2]`, TOC entry `[12:14]`).

> **Trap (the same trap as §5.2, in a different field):** an earlier
> implementation wrote `sample_idx` as a **single byte** at `entry[11]`
> (clamped via `min(255, sample_idx)`). This "worked" in every test bank
> because none of them had more than 255 samples — the unused high byte at
> `entry[10]` always happened to read back as zero. Once a bank crossed the
> 256-sample threshold, every sample with index ≥ 256 silently collided onto
> index 255 (`min(255, idx)`), so multiple presets ended up referencing the
> *wrong* sample (observed on hardware as "this preset has 4 voices and
> several velocity layers, but they all play the exact same sample — S255").
>
> The correct field width was confirmed independently from the EOS manual:
> a bank can hold samples `S000`–`S999` (up to **1000 samples per bank**,
> see [§6.3](#63-known-hardware-limits)), which is impossible to represent in
> a single byte and forced the field to be reinterpreted as the 2-byte BE u16
> that the rest of the format's indexing convention would predict anyway.
>
> **General lesson:** when a reference-data-derived field width "works" for
> every sample you have, check whether the format's *other* fields of the
> same conceptual kind (here: indices) share a wider, consistent encoding —
> and check the format's documented capacity limits — before trusting that a
> narrow field is correct. Both the velocity-range bug and this one were
> "confirmed" by limited reference data that happened not to exercise the
> full value range.

---

## 6. Other format quirks & limits

### 6.1 FORM size quirk (RESOLVED 2026-06-08)

The `FORM` size field uses the **EMU convention, not standard IFF**:

```
form_size = len(form_content) − 4     (== filesize − 12)
```

Standard IFF would write `len(form_content)` (`== filesize − 8`), counting the
4-byte `E4B0` form-type. EMU **excludes** the form-type from the count, so the
value is 4 smaller. Writing the standard value is 4 bytes too large and makes
the reference loader **emu.tools e-xplorer** report **"IFF length mismatch"**.
Confirmed against every hardware-saved `B.0NN-*.E4B`: `filesize − form_size == 12`.

This dovetails with the mandatory trailing **`EMSt`** chunk (§6.4). The `−4`
size makes the declared `FORM` boundary stop **4 bytes short of EOF — inside
`EMSt`'s trailing zeros**. When a bank is **streamed from CD** the E4XT
enforces the `FORM` boundary strictly, so the 4 clipped bytes must land in
throwaway `EMSt` padding rather than in the last sample's PCM. (An earlier
attempt at the `−4` size *without* an `EMSt` last chunk truncated the final
sample → "end of file" at ~99%; appending `EMSt` is what makes the convention
safe.)

`write_e4b()` writes `form_size = len(form_content) − 4` and always appends
`EMSt` last. Verified end-to-end: rebuilt banks load in e-xplorer and as EMU3
CD ISOs.

### 6.1a Master-setup chunk (`EMSt`)

Every hardware-saved bank ends with a **1366-byte `EMSt`** ("Untitled MSetup")
chunk that is **NOT listed in the TOC1**. It holds the global master-setup /
MIDI-channel table; the default block is byte-identical across all fresh banks
(captured verbatim as `_EMST_DEFAULT_B64` in `e4b_writer.py`, trailing bytes
zero). It must be the **final** chunk — see §6.1 for why.

### 6.2 Name encoding

All names (`preset.name`, `sample.name`, TOC entry names) are stored as
**16-byte, space-padded ASCII** (`_name16()`): truncated to 16 characters,
non-ASCII characters replaced, then right-padded with spaces (`0x20`) to
exactly 16 bytes. There is no null terminator within the 16-byte field.

Sample names additionally encode the **root note** as a suffix
(`_<note><octave>`, e.g. `_D0`, `_C4`) appended after truncating the base
name to make room — see `_sample_display_name()`. This appears to be a
convention used so that the sample's tuning is visible in hardware browsers
that only show the raw 16-character name.

### 6.3 Known hardware limits

These limits come from the EOS manual and hardware testing, and are enforced
(with warnings) by `bank_splitter.py` when packing presets into output banks:

| Limit | Value | Source |
|---|---|---|
| Samples per bank | 1000 (`S000`–`S999`) | EOS manual; also implied by the 2-byte `sample_idx` field, §5.3 |
| Presets per bank | 1000 (`P000`–`P999`) | EOS manual — same numbering scheme as samples |
| Sample RAM | 4–128 MB | EOS manual (separate physical pool from Preset RAM; not simply additive) |
| Preset RAM | 1–8 MB | EOS manual (holds presets + sequences, not samples) |
| E4XT max bank/image size | 128 MB | observed hardware constraint |

A single **preset** must fit entirely within one output bank together with
*all* of its referenced samples — presets are never split across banks, and
samples are deduplicated by name within a bank (`bank_splitter.py`).

---

## Sources & Attribution

This reverse-engineering effort drew on:

- **Hardware-saved E4XT banks** created and dumped by Jan Lentfer
  (`JL AnalogBank`, `FltEnvTest`, `FLTTYPES`/`FLTTYPES2` series, the
  `B.0xx-*` differential test series, and others referenced by name above) —
  the primary source for nearly every byte-level detail in this document.
- **Commercial EOS CD-ROMs**: E-MU Formula 4000 Series Vol. 5, Producer
  Series Vol. 01, Syntec WOS V4 (used to cross-check conventions against
  professionally authored content).
- **emu3bm** by David García Goñi — <https://github.com/dagargo/emu3bm>
  (GPL-3.0-or-later) — source of `struct emu3_sample`, the basis for the
  `E3S1` sample-header layout in §[3](#3-preset-e4p1-chunk-body)/[4](#4-voice-block)
  region (sample body, not reproduced verbatim here — see
  `_build_sample_body()` in the writer for the full byte-by-byte mapping).
- **Phil's E4 format notes** —
  <http://www.philizound.co.uk/freebies/software/emu-reorder/emu-reorder.html>
  — general E4B structural orientation.

No third-party source code was copied into mpc2emu; this document and the
corresponding writer (`writers/e4b_writer.py`) are independent
implementations informed by the above sources plus original hardware
differential analysis.
