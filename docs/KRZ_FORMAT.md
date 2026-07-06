<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# Kurzweil K2000 `.KRZ` Bank Format — Reverse-Engineered Reference

This document describes the on-disk layout of `.KRZ` bank files for the
**Kurzweil K2000 / K2500 / K2600 (VAST)** samplers, and the SCSI / CD / floppy
media formats mpc2emu wraps them in, as reverse-engineered by the mpc2emu
project. It covers the **Bank → Object (Sample / Keymap / Program)** model, the
byte-level layout of each object, the tagged-segment encoding of a VAST program
(filter, envelopes, LFO), and a number of non-obvious conventions that took
real hardware testing to pin down.

The goal is to let other implementers (sample-conversion tools, librarians,
archival projects, …) write or read `.KRZ` files without repeating the
trial-and-error this project went through. It is **not** official Kurzweil
documentation — it is the result of differential analysis of hardware-saved
banks, a large corpus of commercial soundsets, and the KurzFiler source (see
[Sources & Attribution](#sources--attribution)).

> **Implementation reference:** the canonical, always-up-to-date version of this
> layout lives in [`writers/krz_writer.py`](../writers/krz_writer.py)
> (serialization) and [`writers/iso_builder.py`](../writers/iso_builder.py) /
> [`writers/fat16.py`](../writers/fat16.py) (media). Where they disagree with
> this document, trust the code (and file an issue). The reverse-engineering
> methodology and hardware-session logs are in
> [`docs/re_procedures/krz_program_re.md`](re_procedures/krz_program_re.md) and
> [`docs/re_procedures/krz_paramid.md`](re_procedures/krz_paramid.md).

> **Endianness:** everything in a `.KRZ` file is **big-endian** (the K-series is
> a Motorola 68000 platform). This is the opposite of the E4B format and of
> mpc2emu's internal little-endian PCM, which is byte-swapped on write.

---

## 1. Overview: container & object model

A `.KRZ` file is **not** an IFF-like container. It is a flat **object database
dump**: a 32-byte file header, a run of length-prefixed **object blocks**, an
end marker, and then a single contiguous region of raw 16-bit PCM sample data
that the sample objects point into by absolute word offset.

```
PRAM <osize> <rest[6]>            — 32-byte file header
  object block  (Sample)          — negative blocksize + hash + name + data
  object block  (Sample)
   …
  object block  (Keymap)
   …
  object block  (Program)
   …
  int32 = 0                        — object-section end marker
  <PCM sample data>                — raw big-endian 16-bit signed, from osize
```

Unlike E4B/E4XT there is **no preset/voice/zone hierarchy inside a single
object**. Instead a bank is three *kinds* of independent, cross-referencing
objects, distinguished by a type code packed into each object's hash:

```
Bank
 ├── samples : one Sample object each   ──► KSample header + Soundfilehead + PCM ref
 │     └── points into the PCM region by absolute word offset
 ├── keymaps : one Keymap object per voice ──► 128 key entries (tuning + sampleID)
 │     └── each entry references a Sample by numeric id
 └── programs: one Program object per preset ──► VAST layers (DSP algorithm)
       └── each layer's CAL segment references a Keymap by numeric id
```

Key structural facts that fall out of this model (all as emitted by
`write_krz()` in `krz_writer.py`):

- **Objects reference each other by numeric id, not by name.** A Program layer
  names a Keymap id; a Keymap entry names a Sample id. mpc2emu assigns ids from
  a single **user id space starting at 200** (`base_id = 200` in `write_krz()`):
  samples get `200 + i`, keymaps a running counter from 200, programs `200 + i`.
  Numeric collisions between the three id spaces are harmless because the id is
  always qualified by its **type** in the object hash (§2.2).
- **One Keymap per voice, one Program layer per voice** (`CR-1`). The K2000
  keymap maps a *single* sample per key with no per-key velocity zones, so
  mpc2emu never merges voices into one keymap — see [§7.2](#72-velocity-splits--multisample-collapse).
- **Samples are bank-global** and word-addressed into one shared PCM blob at the
  end of the file.
- **The mpc2emu writer emits object types 36 / 37 / 38 only** (Program / Keymap
  / Sample). Real production soundsets also contain type **28** (FX/Studio
  effects); mpc2emu's programs reference the K2000's ROM effects instead of
  writing effect objects. A structural walk of **201 real soundset `.KRZ`
  files** parsed cleanly with exactly types 28/36/37/38 (verified 2026-06-14),
  confirming the header + object-block framing against production files.

---

## 2. Container details

### 2.1 File header (32 bytes)

Written by `write_krz()`; big-endian throughout.

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0:4`   | 4  | `magic`   | ASCII `PRAM` |
| `4:8`   | 4  | `osize`   | BE **i32** — absolute byte offset where the PCM sample region begins. Written **last** (a placeholder `0` is written first, then patched after all objects are laid out). |
| `8:12`  | 4  | `rest[0]` | `0` |
| `12:16` | 4  | `rest[1]` | `0` |
| `16:20` | 4  | `rest[2]` | firmware/software version — mpc2emu writes **353** (`KRZ_SOFTWARE_VERSION`, K2000 OS v3.53) |
| `20:32` | 12 | `rest[3..5]` | `0` |

### 2.2 Object block (variable)

Every object is one length-prefixed block. The framing is emitted by the
`_BlockWriter` class (`begin()` / `end()`), which mirrors KurzFiler's
`KObject.writestart` / `writefinish`:

| Offset (from block start) | Size | Field | Notes |
|---|---|---|---|
| `0:4` | 4 | `blocksize` | BE **i32**, **negative** = `block_start − block_end`, i.e. −(total bytes of this block including this field). Patched by `end()`. A reader walks objects by adding `−blocksize` to the current position; the walk stops at the `int32 = 0` end marker. |
| `4:6` | 2 | `hash` | BE u16 = `(type_code << 10) + id` (`_hash()`). See the type table below. |
| `6:8` | 2 | `size` | BE u16 — object size, patched by `end()` to `end_of_object − offset_of_size_field + 2`. |
| `8:10` | 2 | `ofs` | BE u16 = `name_len + 3` (odd name length) or `name_len + 4` (even). This is the offset from the `ofs` field to the start of the object-specific data. |
| `10:10+n` | n | `name` | ASCII, max 16 chars (`ascii`, `errors='replace'`). |
| — | 1 or 2 | pad | null terminator + word-alignment: `\x00` (odd `n`) or `\x00\x00` (even `n`). |
| — | … | data | type-specific object body (§3–§4) |

`end()` pads the object to a 2-byte boundary before computing `size`, then pads
the whole block to a 4-byte boundary before computing `blocksize`.

**Object type codes** (`_hash(type, id)` → hash base):

| Type code | Name | Hash base | Emitted by mpc2emu |
|---|---|---|---|
| 36 | `T_PROGRAM` | `0x9000 + id` | ✅ one per preset |
| 37 | `T_KEYMAP`  | `0x9400 + id` | ✅ one per voice |
| 38 | `T_SAMPLE`  | `0x9800 + id` | ✅ one per sample |
| 28 | `T_FX` (Studio/effects) | `0x7000 + id` | ❌ — programs use ROM effects |

### 2.3 End marker & PCM region

After the last object, `write_krz()` writes `int32 = 0` (the object-section
terminator), records the current file position as `osize`, patches it into the
header at offset 4, and then streams the sample PCM. mpc2emu's internal PCM is
16-bit signed **little**-endian; each 16-bit word is byte-swapped to big-endian
on the way out. Sample objects address this region by absolute **word** offset
(`osize + word_index × 2`).

---

## 3. Sample & Keymap objects

### 3.1 Sample object (`KSample` + `Soundfilehead` + envelopes)

Written by `_write_sample_object()`. Body layout after the object name:

**KSample fixed header (12 bytes)** — `struct '>hhhBBhh'`:

| Offset | Size | Field | Value written |
|---|---|---|---|
| `0:2`   | 2 | `baseID`     | `1` (always — matches every real soundset) |
| `2:4`   | 2 | `numHeaders` | `0` = one header (mono) |
| `4:6`   | 2 | `HeadersOfs` | `8` (always) |
| `6`     | 1 | `flags`      | `0` = mono, `1` = stereo (bit 0 is the **stereo** flag, *not* needsLoad) |
| `7`     | 1 | `ks1`        | `0` |
| `8:10`  | 2 | `copyID`     | `0` |
| `10:12` | 2 | `ks2`        | `0` |

> mpc2emu writes **mono only** — one `Soundfilehead` per sample. A stereo sample
> would need `numHeaders = 1`, `flags` bit 0 set, and a second `Soundfilehead`;
> that path is not implemented (see [§7.5](#75-other-known-caveats)).

**Soundfilehead (32 bytes)** — one per channel; `struct '>BBBBhh'` + `'>iiii'` +
`'>hhI'`:

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0`   | 1 | `rootkey`          | MIDI note; the K2000 auto-transposes each key relative to this |
| `1`   | 1 | `flags`            | **`0x70` when looped, `0xF0` when one-shot** — see below |
| `2`   | 1 | `volumeAdjust`     | `0` |
| `3`   | 1 | `altVolumeAdjust`  | `0` |
| `4:6` | 2 | `maxPitch`         | BE u16, the ×100-cents pitch at which the sample, transposed up, hits the K2000's 48 kHz playback ceiling. `round(100·rootkey + 1200·log2(48000 / sample_rate))` (`_compute_max_pitch`). |
| `6:8` | 2 | `offsetToName`     | `0` |
| `8:12`  | 4 | `sampleStart`      | BE i32, absolute **word** offset of the sample's first PCM word |
| `12:16` | 4 | `altSampleStart`   | `== sampleStart` in real files |
| `16:20` | 4 | `sampleLoopStart`  | looped → loop start word; one-shot → PCM-end word |
| `20:24` | 4 | `sampleEnd`        | looped → **loop end** word (not PCM end); one-shot → PCM-end word. See below (`CR-10`). |
| `24:26` | 2 | `offsetToEnvelope` | `8` (mono, 1 header) |
| `26:28` | 2 | `altOffsetToEnvelope` | `6` |
| `28:32` | 4 | `samplePeriod`     | BE u32 = `round(1e9 / sample_rate)` (`_compute_sample_period`) |

Followed by **2× Envelope** (12 bytes each), each `struct '>hhhhhh'` =
`[-1, 1, 0, 0, -1600, 0]`.

Two hardware-confirmed encoding subtleties:

- **`Soundfilehead.flags`** — bit `0x40` (needsLoad) plus playback-enable bits
  `0x10|0x20` are all required for a playable RAM sample: **`0x40` alone loads
  the sample but produces *no sound*** (this was the original "silent KRZ" bug,
  fixed + HW-confirmed 2026-06-14). The **loop on/off** bit is **`0x80`,
  inverted**: `0x80` **clear** = loop, `0x80` **set** = one-shot (HW-confirmed
  2026-06-16). So `flags = 0x70` (loop) or `0xF0` (one-shot). Force-looping
  one-shots (the old `0x70`-always behaviour) left held notes stuck on the final
  sample with no release.
- **Loop region (`CR-10`)** — the K2000 defines a loop as
  `[sampleLoopStart, sampleEnd]`, so for a looped sample `sampleEnd` must be the
  **loop end**, not the PCM end, or the K2000 loops over the post-loop decay
  tail. For a one-shot both `sampleLoopStart` and `sampleEnd` collapse onto the
  PCM end.

### 3.2 Keymap object (`KKeymap`)

Written by `_write_keymap_object()` / `_build_keymap_entries()`. One keymap per
voice. Body layout after the object name:

**KKeymap fixed header (28 bytes)** — `struct '>hhhhhh'` + 8× `'>h'`:

| Offset | Size | Field | Value |
|---|---|---|---|
| `0:2`   | 2 | `sampleId`     | default sample id (0 for multi-sample keymaps; the per-entry ids carry the mapping) |
| `2:4`   | 2 | `method`       | **`0x0013`** (`KEYMAP_METHOD`) = per-entry `2-byte tuning \| 2-byte sampleID \| 1-byte subSample`. This is what the K2000 itself writes on save. |
| `4:6`   | 2 | `basePitch`    | **`0`** — matches every real production soundset (an earlier `ceil(1200·log2(96000/sr))` guess was wrong). |
| `6:8`   | 2 | `centsPerEntry`| `100` (one semitone per key) |
| `8:10`  | 2 | `entriesPerVel`| `NUM_KEYS − 1 = 127` |
| `10:12` | 2 | `entrySize`    | `5` (`KEYMAP_ENTRY_SIZE` = 2 + 2 + 1) |
| `12:28` | 16 | `Level[8]`     | `(8 − j)·2` for `j` in 0..7 — the single-velocity-level encoding; a reader decodes it back to a single level spanning all 8 velocity buckets |

**Key entries** — `NUM_KEYS = 128` × 5 bytes, `struct '>hHB'` per key:

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0:2` | 2 | `tuning`   | BE **i16** cents — a **constant per-zone fine offset** `100·(R_sample − R_zone) + fine_tune`, usually 0. The K2000 already transposes each key from the sample rootkey + `centsPerEntry`; the tuning field must **not** re-encode the per-key shift (the old `100·(root−12−key)` double-counted it and drove high keys to −72 semitones → silent). |
| `2:4` | 2 | `sampleID` | BE u16, the referenced Sample object id |
| `4`   | 1 | `SSNr`     | subsample index = `1` |

Two hardware-driven rules baked into `_build_keymap_entries()`:

- **Up-pitch ceiling.** A sample can only transpose *up* to the K2000's 48 kHz
  ceiling (`maxPitch // 100 = root + 12·log2(48000/sr)` semitones). Keys above
  that are not assigned the over-stretched sample (HW-confirmed 2026-06-21:
  stretching one sample far past its ceiling makes the K2000 **drop keytracking
  for the entire keymap**). To extend the range, downsample via
  `--max-sample-rate` (raises the ceiling).
- **No empty keys (delete-lockup avoidance).** Every one of the 128 keys **must**
  reference a valid sample. A keymap with `sampleId = 0` holes **locks up the
  K2000 on `Master → Delete`** (corrupts state; HW-confirmed 2026-06-24). The
  writer forward-fills then back-fills every hole from the nearest assigned
  key's entry.

---

## 4. Program object (VAST layers)

Written by `_write_program_object()`. A program is a stream of **tagged
segments** — `tag (1 byte) + data (N bytes)` — terminated by `int16 = 0`. The
segment lengths are fixed per tag (`_seg_len()`):

| `tag & 0xF8` (or exact tag) | Segment family | Length |
|---|---|---|
| `0x08` PGM, `0x09` LYR | program / layer globals | 15 |
| `0x0F` FX | effect selection | 7 |
| `0x18` FUN | function `[func, inA, inB]` | 3 |
| `0x10` ASR, `0x14` LFO, `0x68` KDFX | modulation sources | 7 |
| `0x20` ENC, `0x50` HOB | DSP routing / DSP-function page | 15 |
| `0x40` CAL, `0x78` KB3 | keymap ref + pitch | 31 |

The overall program shape is `PGM FX` once, then **per layer**:

```
LYR [ASR* FUN* LFO ASR* FUN*] ENC ENV ENC [ENC] CAL HOB HOB HOB HOB
```

with exactly **4 HOB (0x50–0x53) + 1 CAL per layer** (from a corpus of 201
soundsets / 4280 programs / 16649 layers). The 4 HOB blocks are the **4
DSP-function "pages"** of the layer's algorithm.

### 4.1 Template-and-patch strategy

Rather than hand-build a program, `write_krz()` **clones the K2000 ROM #199
"Default Program"** (disk-saved as `DFLT.KRZ` and diffed against
single-parameter variants on hardware — see
[`krz_program_re.md` §16](re_procedures/krz_program_re.md)) and overwrites only
the value bytes. `_TPL_GLOBAL` holds the PGM (0x08) + FX (0x0F) segments;
`_TPL_LAYER` holds one full layer (`LYR ASR ASR FUN FUN LFO LFO FUN FUN ENC ENV
ENC ENC CAL HOB×4`). `_patch_layer()` patches per-voice values into a copy.
This carries the full, correct K2000 program structure "for free" and lets the
writer express filter + envelopes + LFO that the earlier hand-built program
could not.

### 4.2 PGM / LYR / CAL segments

**PGM (0x08, 15 bytes)** — `_make_pgm_segment()` / `_TPL_GLOBAL`:

| Byte | Field | Value |
|---|---|---|
| `0` | mode | `2` = K2000 |
| `1` | `numLayers` | patched to the layer count |
| `3` | bend range | `0x37` (`55`) |
| `4` | portamento | `64` |

**LYR (0x09, 15 bytes)** — key/velocity window + enable (HW-confirmed 2026-06-24
via KurzFiler + KPOWER + the `VELAYRE.KRZ` velocity diff):

| Byte | Field | Notes |
|---|---|---|
| `1` | flags marker | `0x18` |
| `3` | `loKey` | `0–127` |
| `4` | `hiKey` | `0–127` |
| `5` | velocity window | **packed** LoVel/HiVel — see below |
| `6` | Enable control source | **`0x7F` = ON** (this is *not* hiVel — writing hiVel here gated the layer) |
| `8` | mono/stereo flags | `0x04` mono / `0x24` stereo |

The velocity window byte (`_vel_byte()`) packs two 0–7 dynamic marks
(`ppp = 0 … fff = 7`): **`(loMark << 3) | (7 − hiMark)`** — LoVel in bits 3–5
direct, HiVel in bits 0–2 **inverted**. A full-range layer is therefore `0`,
which is why every factory layer reads 0 and the field was invisible in static
files until the `VELAYRE.KRZ` diff.

**CAL (0x40, 31 bytes)** — keymap reference + pitch routing:

| Byte | Field | Notes |
|---|---|---|
| `0` | (constant) | `0x7F` |
| `3` | (constant) | `0x2B` |
| `11:13` | `keymapID` (BE) | the Keymap object id for this layer. **Only** CAL[11,12] — CAL[7,8] is a *second* keymap slot and must stay 0 (writing the id there too made every layer claim two keymaps, overflowing the K2000 at 4+ layers → whole program silent; HW-confirmed 2026-06-23). |
| `21` | pitch Src1 source | `114` = LFO1 when LFO→pitch (vibrato) is routed (`_K2_CS_LFO1`) |
| `22` | pitch Src1 depth | signed, `round(lfo1_to_pitch × 79)` (approx — see [§7.4](#74-approximate-depth-calibrations)) |
| `29` | algorithm number | `1` / `5` / `16` / `2` — selected by the filter plan (§4.3) |

### 4.3 DSP algorithm & filter (the 4 HOB pages)

The K2000 DSP path is `PITCH → [1–3 DSP function slots] → AMP`. mpc2emu targets
one subtractive algorithm per filter *slope*, selected by `CAL[29]` plus the
three HOB "block-type" bytes. The four HOB pages map to functions **F1 / F2 / F3
/ F4-AMP** (`_patch_layer` segs `0x50 / 0x51 / 0x52 / 0x53`):

| Byte | Field | Meaning |
|---|---|---|
| `HOB0(0x50)[0]` | F1 filter type | see the filter-type table |
| `HOB0(0x50)[1]` | F1 cutoff | signed semitones (`_cutoff_byte`) |
| `HOB0(0x50)[5]` | F1 Src1 source | `121` (`_K2_CS_ENV2`) when a filter envelope is routed |
| `HOB0(0x50)[6]` | F1 Src1 depth | filter-env depth `round(amt × 127)` (approx) |
| `HOB1(0x51)[0]` | F2 block type | `16` = RES / AMP-gain, `61` = NONE |
| `HOB1(0x51)[1]` | F2 value | resonance (`dB×2`), bandpass width, or PARA-MID gain |
| `HOB2(0x52)[0]` | F3 block type | `18` = SEP (Alg 1/16), `60` = NONE (Alg 5), `40` = None (Alg 2) |

**Filter type / algorithm plan** (`_k2_filter_plan()`, mapping the shared XPM
`FilterType` enum → K2000; all HW-RE'd via Gotek disk-save + byte-diff, see
`krz_program_re.md` §17b/§17g/§17h/§17i and `krz_paramid.md`):

| Source `filter_type` | K2000 filter | `CAL[29]` algo | `HOB0[0]` | `HOB1[0]` F2 | `HOB2[0]` F3 | resonance |
|---|---|---|---|---|---|---|
| Low1 (6 dB) | 1-pole LOPASS | 16 | `15` | `61` NONE | `18` | fixed −3 dB (none written) |
| Low2 / MPC3000 LPF (12 dB) | 2-pole LOWPASS | 5 | `2` | `16` RES | `60` NONE | yes |
| Band2 (12 dB) | 2-pole BANDPASS FILT | 5 | `3` | `16` WID | `60` NONE | no (F2 = width, default 64) |
| BB band-boost (19–22) | Alg-2 PARA MID (parametric boost) | 2 | `51` | `16` AMP | `40` None | no (F2 = gain, +12…+24 dB) |
| High 1–8 | 4-pole HIPASS W/SEP | 1 | `54` | `16` RES | `18` SEP | yes |
| Band4+ | 4-pole TWIN PEAKS BANDPASS | 1 | `55` | `16` RES | `18` SEP | yes |
| BS notch (15–18) | 4-pole DOUBLE NOTCH W/SEP | 1 | `56` | `16` RES | `18` SEP | yes |
| Low4+ / Model / Vocal (default) | 4-pole LOPASS W/SEP | 1 | `50` | `16` RES | `18` SEP | yes |
| (bypass) | NONE | — | `62` | — | — | — |

Named filter-byte constants in `krz_writer.py`: `_K2_FILTER_1P_LP = 15`,
`_K2_FILTER_2P_LP = 2`, `_K2_FILTER_2P_BP = 3`, `_K2_FILTER_LP = 50`,
`_K2_FILTER_HP = 54`, `_K2_FILTER_BP = 55`, `_K2_FILTER_NOTCH = 56`,
`_K2_FILTER_PARA_MID = 51`, `_K2_FILTER_NONE = 62`.

**Cutoff (`_cutoff_byte`)** — `filter_cutoff` (0..1) → **signed semitones**,
`clamp(-48..79, round(-48 + cutoff01 × 127)) & 0xFF`. The byte maps to
`Hz = 440 · 2^((b − 9) / 12)`, range **−48 = 16 Hz … +79 = 25088 Hz**
(HW-confirmed; the recorded spectral centroid tracks the displayed cutoff).
MPC `VelocityToFilter` is folded into the effective cutoff rather than rendered
as a per-note sweep (`eff = min(1.0, filter_cutoff + max(0, velocity_to_filter))`)
— a static-program approximation that matches the MPC's "cutoff pushed up very
far" behaviour and avoids re-muting soft notes (HW-reasoned 2026-06-16).

**Resonance (`_reson_byte`)** — `filter_resonance` (0..1) → `clamp(0..48,
round(reson01 × 48))` = **dB × 2**, max 24 dB (HW-confirmed: acoustic peak boost
≈ 0.44 dB per click). The 1-pole LOPASS writes no resonance byte (its F2 page is
NONE; resonance is fixed at −3 dB). Bandpass F2 is **width** (default
`_K2_BP_DEFAULT_WIDTH = 64`, the median of the real-soundset corpus), not
resonance. PARA-MID F2 is a **band-boost gain** of `+12…+24 dB` derived from
resonance (`_K2_PARAMID_GAIN_MIN_DB = 12`, `_K2_PARAMID_GAIN_SPAN_DB = 12`).

### 4.4 Envelopes (ENV / ENC segments)

Amp and filter envelopes share one 7-segment ADSR model written by
`_fill_env()`. The **amplitude envelope** is the `ENV` segment (0x21); the
**filter envelope (ENV2)** is an `ENC` segment (0x20). Within a 15-byte segment
the layout is **seven `(time, level)` pairs packed from byte 0**:

| Bytes | Stage | Bytes | Stage |
|---|---|---|---|
| `[0]`/`[1]`   | Att1 time/level | `[8]`/`[9]`   | Rel1 time/level |
| `[2]`/`[3]`   | Att2 time/level | `[10]`/`[11]` | Rel2 time/level |
| `[4]`/`[5]`   | Att3 time/level | `[12]`/`[13]` | Rel3 time/level |
| `[6]`/`[7]`   | Dec1 time/level | `[14]`        | loop flag (template default) |

(HW-confirmed 2026-06-24 by reading the AMPENV LCD against the on-disk bytes.
An earlier off-by-one started writing at byte 2, shifting every pair.) mpc2emu
fills `Att1 → full`, `Dec1 → sustain`, then a **two-leg release**: `Rel1` fades
to a 33 % knee over 80 % of the release time, `Rel2` a short tail to silence
(`_REL_KNEE_PCT`, `_REL1_TIME_FRAC`), approximating the MPC's exponential
release with the K2000's linear segments.

**Encodings** (HW-confirmed):
- *Time byte* = `steps(seconds) + 3` (`_env_time_byte`), where `steps()` walks a
  K2000 time grid `_ENV_TIME_GRID` (0–2 s @ 0.02, 2–5 @ 0.04, 5–10 @ 0.10,
  10–15 @ 0.50, 15–25 @ 1.0, 25–60 @ 5.0). Clamped to `3..255`.
- *Level byte* = raw **signed %** (`_lvl_byte`, clamped ±100).
- The AMPENV User/Natural mode lives in an `ENC` segment (`ENC[1]`: `1` =
  Natural → `0` = User); mpc2emu sets User so its values apply.

A KRZ-only release-time correction factor (`_KRZ_RELEASE_FACTOR = 1.9`) scales
the release before encoding, compensating a known under-read of the MPC's
displayed release by the shared value→seconds curve (a proper global
recalibration is a deferred TODO).

### 4.5 LFO segment (0x14)

`_patch_layer` sets, on the LFO1 segment (`seg 0x14`):

| Byte | Field | Encoding |
|---|---|---|
| `2` | rate | `round(26 + 10 × lfo1_rate)` — linear (HW: 1 Hz = 36, 2 Hz = 46, 10 Hz = 126) |
| `4` | shape | enum (`_LFO_SHAPE`), all 26 shapes probed live 2026-06-17: `0` Sine, `1` +Sine, `2` Square, `3` +Square, `4` Triangle, `5` +Triangle, `6` Rising Saw, `8` Falling Saw, `20` 8-Step (nearest to S&H/random), … |
| `5` | phase | `1 + deg/45` (template default) |

LFO→pitch routing is expressed through `CAL[21] = 114` (LFO1 source) /
`CAL[22]` (depth). Control-source codes match the K2000 Musician's Guide Ch 25
exactly (LFO1 = 114, ENV2 = 121, Attack Velocity = 100, MWheel = 1), validating
the reverse-engineered `Src` bytes.

---

## 5. Media formats

A raw `.KRZ` file must be presented to the K2000 on a medium its OS can mount.
mpc2emu emits three, all reverse-engineered against working references.

### 5.1 FAT16 "disk-image copy" — CD *and* SCSI hard disk (primary)

`build_k2000_disk()` in `iso_builder.py` (backed by `fat16.py`) produces the
**universally compatible** form: a plain FAT16 volume that **every** K2000 OS
reads, whether ZuluSCSI presents it as a CD (`CDx.iso`) **or as a SCSI hard
disk** (`HDx.hda`).

> **HW-CONFIRMED 2026-07-06 on a K2000R:** the same byte-identical FAT16 image
> loads banks both as a CD and as an `HDx` SCSI hard disk (ZuluSCSI picks the
> device type from the filename prefix: `HDx` = hard disk, `CDx` = CD, `FDx` =
> floppy; the trailing number is the SCSI id). Jan loaded banks from a 1 GB
> `HD5-…​.hda` and they browse + play.

Layout (verified against a working factory K2000 CD), via
`fat16.format_new(..., partition=False, oem=b'KCDM1.2', rsvd=1)`:

- **BPB at sector 0, no MBR / no partition table** (the K2000 does not support
  partitions). The FAT16 boot sector / BPB fields written by `format_new`:

  | Offset | Field | Value (no-partition K2000 form) |
  |---|---|---|
  | `0:3`   | jump | `E9 00 00` |
  | `3:11`  | OEM name | **`KCDM1.2`** (space-padded to 8) |
  | `11:13` | bytes/sector | `512` |
  | `13`    | sectors/cluster | `8`/`16`/`32`/`64` (chosen to keep cluster count 4085..65524) |
  | `14:16` | reserved sectors | `1` |
  | `16`    | FAT count | `2` |
  | `17:19` | root entries | `512` |
  | `21`    | media | `0xF8` |
  | `22:24` | sectors/FAT | computed |
  | `28:32` | hidden sectors | `0` (no partition) |
  | `32:36` | total sectors (32-bit) | disk sectors |
  | `43:54` | volume label | uppercased, 11 chars |
  | `54:62` | FS type | `FAT16   ` |
  | `510:512` | boot signature | `55 AA` |

- **Banks live in a sub-directory** (`BANKS/` by default) with clean 8.3 names
  (`PFX_NN.KRZ`). `fat16.py` writes a plain 8.3 short entry with **no VFAT
  long-name entries** when the name already fits 8.3 (`_try_83`) — the K2000
  reads 8.3, so long names would show mangled `NAME~1` aliases.
- `size_mb = None` auto-sizes the image to just fit the banks (the CD form); an
  explicit size gives a hard disk with free space to save onto.

### 5.2 ISO 9660 CD (K2000 OS v3.87+ only)

`build_iso_9660()` writes a standard ISO 9660 Level-1 CD (PVD at sector 16,
VDST 17, path table 18, root dir 19, then file extents). Names are unique 8.3
`PREFIXnnn.KRZ;1`, with the extension taken from each source file so the K2000
recognises the bank type. **Only K2000 OS v3.87+ (K2500 2.96+/4.32+, any K2600)
can read ISO 9660**; older OS need the §5.1 FAT16 disk-image copy ("require an
image of a Kurzweil/DOS-formatted disk").

### 5.3 Gotek FAT12 floppy

`writers/fat12.py` + `convert.py --floppy [720|1440]` writes one `<bank>.img`
per bank: a standard DOS **720 KB / 1.44 MB FAT12** floppy (no MBR, floppy BPB,
12-bit FAT, VFAT + 8.3) that a Gotek/FlashFloppy presents to the K2000R as a raw
sector image. A bank is a single `.KRZ` in the floppy root (a ~1.39 MB KRZ fills
a 1.44 MB disk); the converter warns/skips if the KRZ exceeds the floppy. HW-used
on the K2000R.

---

## 6. Hardware limits

| Limit | Value | Where enforced / source |
|---|---|---|
| Sample RAM | **64 MB** | `convert.py` `_hw_limits['krz'] = 64`; larger inputs split by `bank_splitter.py`; default `--bank-size` a conservative 32 MB |
| Layers per program | **32** (`_MAX_KRZ_LAYERS`) | hardware max; the writer clamps split layers to it |
| "Regular" program layers | **3** | >3 *stacked/unison* layers are spread-picked to 3 so the program plays on **any** channel; >3 *split* layers (velocity/key/drum) become a **drum program** that only sounds on a drum channel (HW-confirmed) |
| Object user id space | **200–999** | `base_id = 200`; samples/keymaps/programs share it (typed hash disambiguates) |
| Up-pitch ceiling (per sample) | `root + 12·log2(48000/sr)` semitones | keys above it are not assigned the sample (avoids losing keytracking); raise via `--max-sample-rate` |
| FAT16 volume | **~2047 MB** | `fat16.format_new` requires cluster count 4085..65524; `build_k2000_disk` splits or errors above it |

---

## 7. Known lossiness & caveats

Recorded here because they are the traps a future implementer is most likely to
hit. Most are drawn from `krz_writer.py` comments and the RE session logs.

### 7.1 One filter slope per family

Slope is matched exactly where the K2000 has a native equivalent — Low1 →
1-pole (6 dB), Low2 / MPC3000 LPF → 2-pole (12 dB), Low4+ → 4-pole (24 dB). But
**2-pole HP / BP / notch are not RE'd**: High1/2 collapse onto the 4-pole
HIPASS, notch onto the 4-pole DOUBLE NOTCH, and Vocal/formant/model types fall
back to the 4-pole LOPASS. Multi-pole variants within a family collapse to the
nearest available slope. Because slopes are matched where possible, the source
cutoff frequency transfers 1:1 (it is the −3 dB corner regardless of slope).

### 7.2 Velocity splits & multisample collapse

A K2000 keymap maps **one sample per key** — it has no per-key velocity zones.
So `_split_voice_by_velocity()` splits any voice spanning multiple velocity
bands into **one layer + keymap per band** (else the last/brightest zone would
win on every key). This is also why there is one keymap per voice, not one
merged keymap per preset.

### 7.3 Layer capping & octave-slice coverage remap

`_voices_stacked()` caps redundant unison/stacked programs to 3 layers
(`_spread_pick` keeps the endpoints of a detune spread). Wide-range
octave-slice pad stacks that would over-stretch past the up-pitch ceiling are
rebuilt into 1–3 **coverage multisample** keymaps by `_coverage_remap_voices()`
so the whole range sounds at the right octave. A faithful all-layer
(drum-program) rendering of large stacks is a deferred opt-in.

### 7.4 Approximate depth calibrations

The **filter-env depth** (`HOB0[6]`) and **LFO→pitch depth** (`CAL[22]`) are
written with rough 2-point linear fits (`krz_program_re.md` §16 addendum:
filter-env ≈ `29 + cents·0.0091`, LFO→pitch ≈ `70 + cents·0.0073`). The
converter currently uses the simpler `round(amt × 127)` / `round(depth × 79)`
approximations in `_patch_layer`; both are flagged "approx; see TODO". Filter
cutoff and resonance are sonically confirmed faithful; the modulation-routing
*sources* match the manual's control-source codes, but per-page byte offsets and
exact depth curves for the fuller routing set (velocity→filter/amp,
mod-wheel→filter, LFO→amp tremolo) still need disk-save calibration.

### 7.5 Other known caveats

- **Mono only.** Stereo samples would need a second `Soundfilehead`; not
  implemented.
- **Ping-pong loops** (`ALTERNATING`) are baked into PCM as forward loops by
  `bake_alternating_loop()` (the K2000 path has no native ping-pong; emitting a
  plain forward loop clicked every cycle).
- **FX/Studio effects (type 28) are not written** — programs reference the
  K2000's ROM effects.
- **RAM ≠ file format.** The K2000's live SysEx object dump returns a *fixed-
  layout RAM* object, not this tagged-segment disk format (the firmware converts
  on load/save). The RAM map (decoded separately for a future MIDI-transfer mode
  and the K2000 remote project) does **not** describe `.KRZ` bytes — see
  `krz_program_re.md` §11.

---

## Sources & Attribution

This reverse-engineering effort drew on:

- **KurzFiler** by Marc Halbrügge — <https://kurzfiler.sourceforge.io/>
  (GPL-2.0) — the source of the object-block framing (`KObject`), segment tag
  model, and the `Soundfilehead` / `KKeymap` / `KProgram` field names. **No
  source code was copied**; `writers/krz_writer.py` is an independent Python
  implementation informed by it.
- **Hardware-saved K2000R banks** created and disk-saved by Jan Lentfer via a
  Gotek floppy (`DFLT.KRZ`, `FILTERS.KRZ`, `POLE2LP/POLE2A5/POLE1LP.KRZ`,
  `PARAJLZ.KRZ`, `VELAYRE.KRZ`, and the `KRZ_*` forward-RE series) plus live
  SysEx sessions — the primary source for the program-parameter byte semantics.
- **Commercial soundset corpora**: 201 K2000 soundset `.KRZ` files (structural
  validation of the container) and 160 Patchman soundsets / ~14 000 layers
  (filter-byte and routing cross-checks), plus `KPOWER.KRZ` / Patchman
  `PMVOL002.KRZ` (RAM-sample header verification).
- **The E-MU / Kurzweil K2000 Musician's Guide** (Ch 14 DSP Functions, Ch 23
  LFOs, Ch 25 Control Sources, Ch 26 DSP Algorithms, Ch 30 SysEx) for the
  parameter model and the control-source code list.

Detailed session logs and the still-open RE items live in
[`docs/re_procedures/krz_program_re.md`](re_procedures/krz_program_re.md),
[`docs/re_procedures/krz_paramid.md`](re_procedures/krz_paramid.md), and
`TODO.md` / `docs/RESOLUTION_NOTES.md`.
