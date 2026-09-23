<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# EMU E4B Bank Format — Reverse-Engineered Reference

> **Section citations.** **This project never numbers its own sections** — all
> 299 headings in `docs/RESOLUTION_NOTES.md` are named (`§KRZCOARSE`,
> `§MODWHEEL`). So **a section reference that is a NUMBER is always a sibling
> project's**, and must say whose. A named one is always ours.
>
> That is stronger than a per-file default, and it is why the rule is stated
> rather than assumed: `test_citations_resolve` only resolves NAMED sections,
> so every numbered citation in this repo is unchecked by construction. The
> sibling ranges also overlap — s3ked's section 139 is a filter-corner
> measurement while eosed's is a withdrawn cord-scale claim, and on 2026-09-15
> that collision produced a correction to a citation that was already right.
> Worse, s3ked's section 18 is a retraction about measuring the wrong program
> while ours would be a confirmed write path: a reader resolving that one
> locally lands somewhere actively misleading rather than merely absent.>
> **k2kremote numbers PER FILE**, so a citation of theirs at 7 or below must name
> the file: `RESOLUTION_NOTES.md` runs 1..73 and `MAC_FORMAT.md` runs 1..7, and
> the two share every number in that range. Their §6 is "Name-edit cursor" in one
> file and "Object lists — not covered" in the other. eosed and s3ked each number
> across a single file, so theirs need only the project.


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

> **`TOC1` is optional, not just "not trusted."** mpc2emu always writes one,
> and `e4b_parser._walk_chunks` never depends on it being present (it never
> looks at offset 12 specifically) — but at least one real commercial disc
> (`a drum-kit preset on library disc C`, library disc C) goes
> straight from `FORM <size> E4B0` to `E4Ma` with no `TOC1` chunk at all. Any
> reader that assumes `TOC1` always exists will break on real-world media.
>
> **`EMSt` is not always the single last chunk of the file — "mega-banks"
> exist.** At least one commercial disc (`a percussion/kit preset on library disc C`,
> same CD) is several originally-separate sub-banks concatenated into one
> file: it contains a `TOC1` and an `EMSt` *mid-stream*, followed by more real
> `E4P1`/`E3S1` content afterward. `e4b_parser._walk_chunks`'s caller tolerates
> this by construction (it filters for the sample/preset tags and ignores
> everything else, `EMSt` included, all the way to `form_size`) — but a reader
> that stops at the first `EMSt` will silently drop the rest of the file. This
> holds per logical sub-bank, not necessarily per physical file.

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

> **`data_size` can disagree with a chunk's own physical header — uniformly,
> across an entire file, regardless of parity.** At least one real bank
> (`B.030-1V-2V-3V.E4B`) has all 22 TOC entries with a physical chunk size
> exactly 2 bytes larger than the TOC's `data_size` (e.g. `E4Ma`: TOC says
> 256, physical header says 258) — this is *not* the odd-size word-alignment
> padding above (that's 0-or-1 byte, only when `size` is odd; here every
> affected size is *even*). Trusting the TOC's `data_size` for a chunk's byte
> extent grafts 2 stale/wrong bytes onto whatever's read. `e4b_parser.py`
> never trusts TOC1 offsets for this reason — always derive a chunk's extent
> from its own physical header, never from the TOC entry.

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
| `22:27` | 5  | —            | zero |
| `27`    | 1  | **unknown**  | zero in every hardware-saved and factory bank; **non-zero in every preset EOS's AKAI importer writes** — see note below |
| `28`    | 1  | `volume`     | `0x78` (=120) is mpc2emu's default master volume |
| `29:41` | 12 | —            | zero |
| `41`    | 1  | multi-voice flag | `0x04` when `num_voices > 1` (confirmed from hardware + commercial string-library banks) |
| `42`    | 1  | —            | zero |
| `43`    | 1  | multi-voice flag | `0x01` when `num_voices > 1` |
| `44:52` | 8  | —            | zero |
| `52:56` | 4  | constant     | `0x52 0x23 0x00 0x7E` |
| `56:60` | 4  | MIDI routing | `0xFF 0xFF 0xFF 0xFF` = any note / any channel |
| `60:76` | 16 | **FX block** | per-preset effects, in SysEx id 6-21 order — see [§3.2](#32-preset-fx-block-6076) |
| `76:82` | 6  | —            | zero |
| `82+`   | …  | voice blocks | one per `VoiceLayer`, see §4 |

### 3.2 Preset FX block (`60:76`)

**This region was documented as "zero" until 2026-09-20**, because mpc2emu
writes nothing here and the banks first used to derive the layout happened to
leave it zero. It is the per-preset effects block, mapped by eosed from the EOS
4.70 firmware and validated on hardware:

| Offset | Field | Range |
|---|---|---|
| `60` | `FX_A_ALGORITHM` | 0..44 |
| `61` | FX A `Decay Time` | |
| `62` | FX A `HF Damping` | |
| `63` | FX A `FxB==>FxA` | routing amount, B's output into A |
| `64:68` | `FX_A_AMT_0..3` | sends: Main, Sub 1, Sub 2, Sub 3 |
| `68` | `FX_B_ALGORITHM` | **0..32 on EOS 4.70**; the 4.00 spec's 0..27 stops at "Vibrato" and rejects the five distortion algorithms |
| `69` | FX B `Feedback` | |
| `70` | FX B `LFO Rate` | |
| `71` | FX B `Delay Time` | |
| `72:76` | `FX_B_AMT_0..3` | sends |

**Algorithm 0 is not "no effect" — it is `Master Effect A`/`Master Effect B`,
meaning inherit the master setting.** So an all-zero FX block is a valid,
meaningful state and not missing data. A printed effect list starts at the
first real effect, so **printed position is not wire value**: eosed's tables
were off by one from exactly that cause and named the neighbouring effect for
every preset, which never looked wrong because every answer was a real effect
name. Read the firmware POINTER table rather than the string pool — they
disagree from index 18 up.

**How much of this is actually evidenced — read this before relying on any
single field.** The layout was first reported as "validated by falsification
over 1184 preset headers, 704 non-zero blocks, zero range violations". eosed
withdrew that count the same evening: the 704 rows contain **6 DISTINCT
blocks**, from **2 independent sources** (three contributing banks, two of them
the same bank round-tripped), and 690 of the 704 are one bank's default effect
copied over and over. **The count was of rows when the evidence is in distinct
rows.**

Headroom actually exercised — a limit the data never approached was never
tested:

| field | limit | max seen | headroom | distinct n |
|---|---|---|---|---|
| `FX_A_ALGORITHM` | 44 | 20 | 45% | 704 rows / 6 blocks |
| `FX_A` Decay Time | 90 | 60 | 67% | as above |
| `FX_A` HF Damping | 127 | **120** | **94%** | as above |
| `FX_A` FxB==>FxA | 127 | 33 | 26% | **n=1** |
| `FX_A_AMT_0` Main | 100 | 11 | 11% | 702 rows |
| `FX_A_AMT_1..3` Sub | 100 | 0 | 0% | **n=0** |
| `FX_B_ALGORITHM` | 32 | 24 | 75% | 704 rows / 6 blocks |
| `FX_B` Feedback | 127 | 48 | 38% | n=10 |
| `FX_B` LFO Rate | 127 | 24 | 19% | 704 rows |
| `FX_B` Delay Time | 127 | 66 | 52% | n=9 |
| `FX_B_AMT_0` Main | 100 | 10 | 10% | n=9 |
| `FX_B_AMT_1..3` Sub | 100 | 0 | 0% | **n=0** |

**Six of the sixteen positions — every Sub 1-3 send — are non-zero NOWHERE in
the corpus. Their placement is layout symmetry, INFERRED, not observed.**
`FX_A` FxB==>FxA rests on a single preset.

Two results do carry independently:

- **`FX_A` HF Damping reaching 120 against a limit of 127** is the one tight
  range result, and it is exactly the byte that could NOT sit in the Decay Time
  slot, whose limit is 90. That pins the A-side parameter ORDER without relying
  on any label.
- **A machine-to-file link.** Preset 14 of a bank resident in an E4XT read over
  SysEx as FX B algorithm 24, parameters 24, 3, 50. One of the six distinct
  file blocks carries `24 24 3 50` at bytes `68:71` — four bytes, same order,
  different bank. A common factory FX B setting appearing identically in a file
  read and a SysEx read corroborates the B-half layout better than the range
  test did.

**Independent confirmation of the index-0 reading, from a different
mechanism.** The six-value panel comparison above is all from one bank, so a
second line was wanted. Querying the MASTER FX parameter ranges from the device
(SysEx ids 228-243) gives:

    228  MASTER_FX_A_ALGORITHM   device 1..44
    236  MASTER_FX_B_ALGORITHM   device 1..32
    the other 14 master FX ids agree with the spec exactly, defaults included

The stale maximum on 236 is the same off-by-one written in a second place.
**The MINIMUM is the finding: both master algorithm fields start at 1, not 0.**
That is exactly what "index 0 = inherit the master effect" predicts — the
master block cannot select "inherit from myself". Had index 0 been `Room 1` as
the printed-list tables claimed, there is no reason for the master to exclude a
plain reverb. Different mechanism (a range request, not a panel read),
different parameter block, same answer.

**If we ever model master FX: the minimum is 1 for both algorithm fields, and
0 is preset-only.**

**Do NOT convert an FX `Decay Time` byte to seconds.** The firmware's RFX-32
plug-in area carries parameter descriptions, and the reverb one reads "Reverb
decay time, in **arbitrary units**". That area also contains a `%#3.1f sec`
format string, which is the kind of thing that makes a seconds conversion look
supported. RFX is a different effects engine whose algorithm list only partly
overlaps this block, so neither the descriptor nor the format string documents
the preset FX field — but the warning is the useful part either way.

**What does NOT depend on any of this:** the finding that all 363 presets
written by EOS's AKAI importer have an all-zero FX block, and the byte-27
refutation built on it. Those are statements about zeros, and zero is zero
wherever the block sits — they need the block's OFFSETS right, not each field
inside it validated.

mpc2emu writes this region as zero, which is legal and means "inherit master".

### Byte `[27]`, and what it is not

Non-zero in every preset written by EOS's AKAI importer and zero everywhere
else:

    EOS AKAI import          363 presets   byte 27 in 239..250, mode 241
    hardware-saved commercial 10 presets   byte 27 = 0
    large factory bank       347 presets   byte 27 = 0

**It is not the FX field.** The FX block is `60:76` and it is identically zero
in precisely the banks where byte 27 is non-zero — so the importer neither maps
FX nor invents it, while writing something else here.

It is also **not generated by the save path**: a bank of ours with byte 27 = 0
was loaded into an E4XT and saved straight back, and every preset-header byte
round-tripped unchanged. So whatever writes 239-250 is the importer.

It tracks nothing structural — cross-tabbed against `num_voices` it scatters
(241 appears on voice counts 1..30, 242 on 1..40). **Open hypothesis:** read
SIGNED it lands in -17..0 across all 1184 headers, which would fit a per-preset
gain trim the importer derives from the AKAI source, and `E4_PRESET_VOLUME`
(SysEx id 1) is signed dB over -96..10. Weak on its own — the corpus only
exercises -17..0. One read settles it: select a preset whose byte 27 is 249
(-7) and read id 1. Reads -7, it is the volume; reads 0, the hypothesis is
dead.

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
| `4`     | `n_zones`           | zone count; E4XT reads exactly this many secondary-zone entries. **Redundant/display-only — see caveat below** |
| `7`     | `0x64`              | constant observed in working voices |
| `17`    | voice `hi_key`      | writer sets this to the voice's high key. Often reads as `0x7F` in single-full-range voices, which is why earlier notes called it "constant" |
| `18`    | voice `lo_vel`      | mirrors the voice's aggregate zone velocity range — see [§5.2](#52-voice-level-velocity-range-mirrors-the-zone-range) |
| `21`    | voice `hi_vel`      | ditto |
| `22`    | Realtime Xfade Low       | live SysEx `E4_GEN_RT_LOW` (id 53); found 2026-07-28 via live-parameter diff against a hardware-saved bank, see `docs/RESOLUTION_NOTES.md` §E4BPARAMHUNT. Meaning/purpose not yet cross-checked against the manual (name suggests a real-time/round-robin key-crossfade zone, currently unmodeled by mpc2emu) |
| `23`    | Realtime Xfade LowFade   | `E4_GEN_RT_LOWFADE` (id 54) |
| `24`    | Realtime Xfade HighFade  | `E4_GEN_RT_HIGHFADE` (id 56) |
| `25`    | Realtime Xfade High      | `E4_GEN_RT_HIGH` (id 55) — **aliases the byte previously called "`0x7F` constant"**: that value is just this field's common default (no realtime crossfade), not a true structural constant |
| `27`    | Assign Group (choke group) | `E4_VOICE_ASSIGN_GROUP` (id 66), `0–23`. Likely the "choke group" field noted as a gap in `TODO.md`'s instrument-params item |
| `28:30` | Voice Delay              | `E4_VOICE_DELAY` (id 61), `0–10000` ms. **Big-endian 16-bit word** (confirmed: 500 ms → bytes `0x01 0xF4`) — unlike the live protocol's 7-bit MIDI-safe pairs, the file just uses a plain 16-bit BE int |
| `33`    | Sample Start Offset      | `E4_VOICE_START_OFFSET` (id 62), `0–127` |
| `34`    | coarse transpose    | **signed** semitones (`+12` → `0x0C`). Hardware-RE'd 2026-06-13 (`RE_SUITE` ZONE BASE tp+12) |
| `36`    | fine tune           | **signed** cents (`+50` → `0x32`). Hardware-RE'd 2026-06-13 (`RE_SUITE` ZONE BASE ft+50c) |
| `37`    | Glide Rate               | `E4_VOICE_GLIDE_RATE` (id 63), `0–127` sec/oct — portamento, currently unmodeled by mpc2emu |
| `38`    | Non-Transpose flag  | `0x01` = pitch fixed (does not follow key), `0x00` = key-tracking. Confirmed from `B.010-Voices_RevEng.E4B` |
| `39`    | Solo mode                | `E4_VOICE_SOLO` (id 65), `0–8` — see `VOICE_SOLO_MODES` in eosed |
| `41`    | Chorus Width             | `E4_VOICE_CHORUS_WIDTH` (id 59), **signed byte**, `-128..0`. Confirmed by clean file diff: test value `-100` → byte `156` (two's-complement of a single signed byte) |
| `42`    | Chorus Amount       | Voice/Tuning page; UI `0–100%` → `0–127` linear (`round(pct/100×127)`), `0` = off. Hardware-confirmed 2026-06-08 |
| `44`    | Chorus X (initial ITD)   | `E4_VOICE_CHORUS_X` (id 60), `-32..32` ms |
| `50`    | Latch Mode               | `E4_VOICE_LATCHMODE` (id 67), `0`=off/`1`=on |
| `51`    | `0x80`              | constant |
| `53`    | Glide Curve              | `E4_VOICE_GLIDE_CURVE` (id 64), `0–8` (`0`=linear .. `8`=most exponential) |
| `54`    | volume              | **signed** dB (`−12 dB` → `0xF4`, `0` = unity). Hardware-RE'd 2026-06-13 (`RE_SUITE` ZONE BASE vol-12); supersedes the earlier "amplitude gain" guess. Written since 2026-07-26 — previously documented here but left hardcoded at `0x00` in the writer. **Only meaningful for a single-zone voice** — see [§4.5](#45-secondary-zone-table--zone-entry-22-bytes) |
| `55`    | pan                 | **signed** byte, `−64`=full-L … `0`=centre … `+63`=full-R. Hardware-confirmed 2026-07-26 via a 7-voice differential save (`B.012 "Vce VolPan"`): front-panel Pan `+63/−64/+32/−32` → this byte exactly, every other voice/zone byte unchanged. **Only meaningful for a single-zone voice** — see [§4.5](#45-secondary-zone-table--zone-entry-22-bytes) |
| `57`    | Amp Envelope Depth       | `E4_VOICE_VOLENV_DEPTH` (id 68), `0–16` raw = **−96 dB to −48 dB in 3 dB steps** (per the EOS manual, p.340: "maximum amount of attenuation from the amplifier envelope generator"). Directly relevant to `docs/RESOLUTION_NOTES.md` §E4BLEVEL (the amp-envelope sustain dB-law finding) — this is the field that sets the depth of that dB range; mpc2emu's writer never touches it, so it stays at whatever the source/template carries (commonly `0` = −96 dB, matching the calibration measurement) |
| `58`    | VCF filter type     | see [§4.4](#44-filter-type-mapping-xpm--e4b) |
| `60`    | VCF cutoff          | measured TABLE, not a curve: 133 Hz at `0` … 24163 Hz at `255` (`_E4XT_CUTOFF_TABLE`, E4XT 2026-07-31). **The old "57 Hz … 20 kHz exponential" here was never what the writer used**, and a second hardware sweep (eosed 2026-09-20) disagrees with the table's SHAPE — see RESOLUTION_NOTES §E4XTKEYPOL |
| `61`    | VCF Q / resonance   | `0`–`127`, linear. **Also aliases `E4_VOICE_FKEY_XFORM`** (live id 84, "meaning varies by filter type" per eosed's own notes) — confirmed by diff: baseline `0` (matching `filter_resonance=0.0`) became the test value after editing `FKEY_XFORM` remotely |
| `62`    | Filter Gen Param 1  | `E4_VOICE_FILT_GEN_PARM1` (id 85) |
| `63`    | Filter Gen Param 2  | id 86 |
| `64`    | Filter Gen Param 3  | id 87 |
| `65`    | Filter Gen Param 4  | id 88 |
| `66`    | Filter Gen Param 5  | id 89 |
| `67`    | Filter Gen Param 6  | id 90 |
| `68`    | Filter Gen Param 7  | id 91 |
| `69`    | Filter Gen Param 8  | id 92 — all 8 are "filter-type dependent" per eosed's own param table (their exact meaning shifts with `vpar[58]`, same caveat as `vpar[61]` above); confirmed only as *existing at these offsets*, not decoded per filter type |

> **A voice's real zone count can only be trusted from `vpar[2:4]`
> (`trailer_off`), not `vpar[4]`.** At least three real banks have at least
> one voice where the single-byte `vpar[4]` undercounts the real zone table
> relative to `(vpar[2:4] − VOICE_FIXED) / ZONE_ENTRY`. `e4b_parser._parse_voice`
> derives `n_zones` from `vpar[2:4]` exclusively and never reads `vpar[4]` at
> all — a reader that trusts `vpar[4]` instead will silently drop the
> tail-end zones (and their referenced samples) on affected files. Treat
> `vpar[2:4]` as authoritative and `vpar[4]` as redundant/display-only.

The amplitude envelope is **not** in `vpar` — it lives in the primary zone
table at `PZT[0:12]` (see [§4.2](#42-primary-zone-table-64-bytes-voice110174)).
All other `vpar` bytes are zero in mpc2emu's output; some may carry meaning in
commercial banks that has not yet been decoded (e.g. LFO routing, chorus stereo
width — a separate byte from the Chorus Amount at `vpar[42]`).

### 4.2 Primary zone table (64 bytes, `voice[110:174]`)

A 4×16-byte block holding **three 6-stage envelopes** (per the EOS manual,
p.256: "There are three envelope generators per voice, all of them are the
rate/level type") — the **amplitude envelope** at `PZT[0:12]`, the **filter
envelope** at `PZT[14:26]`, and the **auxiliary envelope** at `PZT[28:40]`
(the third generator, general-purpose/LFO2-driven — mpc2emu does not read or
write it; found 2026-07-28 via live SysEx parameter probing + diff against a
hardware-saved bank, see `docs/RESOLUTION_NOTES.md` §E4BPARAMHUNT). Each is a
uniform **14-byte record**: 12 data bytes (6 rate/level stage pairs) followed
by a 2-byte `0x03 0x00` constant marker — i.e. amp env is `PZT[0:14]`
(`[12:14]`=marker), filter env `PZT[14:28]` (`[26:28]`=marker), aux env
`PZT[28:42]` (`[40:42]`=marker). `PZT[42:64]` holds LFO1/LFO2 (below). Each
envelope's 12 data bytes are 6 `rate`/`level` stage pairs.

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

**Auxiliary envelope — `PZT[28:40]`** (general-purpose, LFO2-driven per the
manual; found 2026-07-28 via live SysEx probing, not yet used/written by
mpc2emu). **Byte order differs from amp/filter env above**: those are grouped
by phase name (Atk1, Atk2, Dcy1, Dcy2, Rls1, Rls2); the aux envelope instead
follows the live editor protocol's raw segment-id order (`SEG0..SEG5` =
Atk1, Dcy1, Rls1, Atk2, Dcy2, Rls2) — confirmed by setting each of the 12
live parameter ids (`E4_VOICE_AENV_SEG0_RATE`..`SEG5_TGTLVL`, ids 117-128) to
a distinct value and diffing a hardware-saved bank:

| Stage (playback order per the manual) | Offsets | Meaning |
|---|---|---|
| Attack 1  | `[28]`/`[29]` | rate / level |
| Decay 1   | `[30]`/`[31]` | rate / level (default level `0x7F` = +100%, i.e. this "decay" is a plateau by default — matches the standard-ADSR convention of the "2" levels equalling the "1" levels) |
| Release 1 | `[32]`/`[33]` | rate / level (default level `0x7E` ≈ +99%) |
| Attack 2  | `[34]`/`[35]` | rate / level (default level `0x7F` = +100%) |
| Decay 2   | `[36]`/`[37]` | rate / level (default rate `20`) |
| Release 2 | `[38]`/`[39]` | rate / level |

Level bytes use the same `round(pct × 127/100)` encoding as amp/filter env
(confirmed: live value 71% → byte 90, 72%→91, 73%→93, 74%→94, 75%→95,
76%→97 — all exact matches for `round(pct×1.27)`) — likely carries the same
hardware dB-law miscalibration as the amp envelope (see `docs/
RESOLUTION_NOTES.md` §E4BLEVEL), unconfirmed for this specific envelope.

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
| `0x0A` / `0x0B` / `0x0C` | **Vel+ / Vel~ / Vel<** — see note below | | `0x40` | **AmpVol** (amplitude) |
| `0x08` | Key (note)      | | `0x41` | **AmpPan** — hardware-confirmed, see below |
| `0x60` (`Lfo1~` = 96 dec) | LFO1 bipolar | | `0x42` | AmpXfd (from the SysEx spec, not measured) |

> **`0x41` = Amp Pan, MEASURED not transcribed** (eosed, 2026-09-06). The id was
> already in the SysEx spec transcription between `AmpVol` (64) and `AmpXfd`
> (66); transcription is not measurement, so it was driven on hardware with
> `AmpVol` as a positive control:
>
> ```
>   baseline                 L -32.46  R -32.04   R-L  +0.42
>   CONTROL DC -> AmpVol +100  L -19.11  R -18.70   R-L  +0.42   level +13.35, balance flat
>   CONTROL DC -> AmpVol -100  L -85.65  R -86.40   R-L  -0.75   level -53.2,  balance flat
>   TEST    DC -> 0x41  +100  L -85.30  R -24.81   R-L +60.49   HARD RIGHT
>   TEST    DC -> 0x41  -100  L -24.85  R -86.48   R-L -61.63   HARD LEFT
> ```
>
> 122 dB of balance swing with level roughly preserved, against a control that
> moves level 66 dB and leaves balance at +0.42 throughout. **The E4XT therefore
> supports DYNAMIC panning**: `Lfo1~` (96) into `0x41` at amount 100 sweeps the
> balance −56.7 → +57.5 dB, 22 sign changes over a 4-second note ≈ 3.06 Hz.
>
> **Two wrong-subject traps were hit and caught by that control**, both invisible
> in readback — every parameter read back exactly as written: `PRESET_SELECT`
> (223) chooses the preset for EDITING and does not change what the MIDI channel
> plays, so the edits landed on a preset that was not sounding; and voice 0 is
> not the voice that sounds at key 60 (voice 2 was, found by moving the control
> cord voice by voice). Without a positive control on a destination already known
> to work, the run would have reported "`0x41` does nothing" — the inverse of the
> truth.

> **The velocity SOURCE is a triad, not one id, and the difference is the
> PIVOT** (eosed, 2026-09-01). `0x0A` `Vel+` is unipolar and anchored at
> velocity 0 — measured, `E4XT_VEL_SOURCE_UNITS`, spanning 0 → 2.08 cord units
> over velocity 0..127 at r = 0.9999. `0x0B` `Vel~` is bipolar, i.e. anchored
> mid-scale — the convention the AKAI's `V_LOUD` uses (pivot at velocity 64).
> `0x0C` `Vel<` is inverted, and with a NEGATIVE amount is neutral at 127 and
> attenuates downward — the convention the K2000's amp `VelTrk` uses.
>
> This table previously labelled `0x0C` as plain "Velocity", which is a trap:
> it invites building an AmpVol cord by analogy with the factory
> Velocity→FilFreq default, whose amount is 0 and which therefore has never
> been heard. `e4b_writer` already uses `_SRC_VEL_PLUS = 0x0A` deliberately —
> its own comment records that "the old default `Vel<` subtracted, anchoring
> HARD notes at base — wrong for veltrack."
>
> **Consequence for any writer: choosing a source IS choosing a pivot**, so it
> must be a deliberate decision rather than whatever a template cord happened
> to hold. The E4XT is the only one of the three machines that can express
> either convention. `Vel~`'s and `Vel<`'s pivots are INFERRED from the naming
> triad (which recurs for Key, VEnv, FEnv and AEnv) and are not yet measured.
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

Each entry maps a key/velocity range to a sample.

| Offset | Size | Field | Notes |
|---|---|---|---|
| `2`     | 1 | `lo_key`     | MIDI note 0–127 |
| `5`     | 1 | `hi_key`     | MIDI note 0–127 |
| `6`     | 1 | `lo_vel`     | MIDI velocity 0–127 |
| `9`     | 1 | `hi_vel`     | MIDI velocity 0–127 |
| `10:12` | 2 | `sample_idx` | **BE u16**, 1-based — see [§5.3](#53-sample-index-is-a-2-byte-be-u16-not-a-single-byte) |
| `12:14` | 2 | `fine_tune`  | Signed **BE i16**, 1/64-semitone units. **Multi-zone voices only** — see below |
| `14`    | 1 | `root_key`   | MIDI note — playback root, overrides the sample's own root note |
| `15`    | 1 | `volume`     | Signed byte, dB. **Multi-zone voices only** — see below |
| `16`    | 1 | `pan`        | Signed byte, −64..+63. **Multi-zone voices only** — see below |
| `3`,`4` | 1+1 | `key fade`   | Low/high key CROSSFADE. Zero in all 10 142 corpus zones; identified from firmware, not seen in the wild — see below |
| `7`,`8` | 1+1 | `vel fade`   | Low/high velocity CROSSFADE. **Non-zero on 36 corpus zones**, in mirrored pairs — see below |

All other bytes (`0`, `1`, `17`, `19`, `20`, `21`) are zero in mpc2emu's
output **and in all 10 142 zone entries of the third-party corpus** — which
makes them unidentified, not unused. A byte nobody writes looks exactly like
a byte that does not exist.

**The four fade bytes, and how they were pinned (2026-09-21).** eosed
decompiled EOS's **Ensoniq** importer — a different importer from the AKAI one,
sharing none of its primitives — and its zone builder writes, relative to a
zone pointer that is `zone_base + 2`: key low at `+0`, "key low fade" at
`+1,+2`, key high at `+3`, velocity low at `+4`, "velocity fade" at `+5,+6`,
velocity high at `+7`, sample index at `+8:10`, fine tune at `+10:12`
(discarded), root key at `+12`, volume at `+13`, pan at `+14`.

**Add the +2 and every one of those lands on a field this table already had,
in the right place** — including the two pairs it did not. Two implementations
that never saw each other: a firmware trace and a 10 142-entry corpus.

The corpus then supplies what the trace could not. `[7]`/`[8]` are non-zero on
**36 zones of one bank**, and they come in mirrored pairs over the same key
range and the same full velocity span:

    (lo_key  0, hi_key  40)   lo_vel 0, [7]= 0, [8]=80, hi_vel 127
    (lo_key  0, hi_key  40)   lo_vel 0, [7]=80, [8]= 0, hi_vel 127
    (lo_key 41, hi_key  46)   lo_vel 0, [7]=80, [8]= 0, hi_vel 127
    (lo_key 41, hi_key  46)   lo_vel 0, [7]= 0, [8]=80, hi_vel 127

Two samples over one range, one fading in as the other fades out: **a velocity
crossfade**, which is the only reading that explains the mirroring. 18 such
pairs.

> ## ✅ `[C]` RESOLVED 2026-09-21 — `[7]` is the LOW fade, `[8]` the HIGH
>
> **Two independent routes, and they agree.** The EOS Roland zone builder was
> read in full at `0x171434`:
>
>     17148c:  a3@(7)  -> a5@(4)      a3 = the PARTIAL
>     171492:  a3@(8)  -> a5@(5)
>     171498:  a3@(9)  -> a5@(7)      <- crossed
>     17149e:  a3@(10) -> a5@(6)      <- crossed
>
> With `partial+7 = vlow` and `partial+9 = vhigh` measured on hardware, and
> this table's `[6] = lo_vel` / `[9] = hi_vel`, the destinations resolve:
>
>     entry[6] = partial+7   lo_vel
>     entry[7] = partial+8   LOW  fade
>     entry[8] = partial+10  HIGH fade
>     entry[9] = partial+9   hi_vel
>
> **This table was right.** It agrees with the asymmetric velocity stack
> measured off the E4XT, by a route that shares no evidence with it.
>
> > **And the `zone_base + 2` convention is now READ rather than inferred.**
> > `a5@(4)` must be `entry[6]` and `a5@(7)` must be `entry[9]`; **both
> > require `a5 = entry + 2`**, independently. That was the single inferred
> > step in the bridge this document flagged, **for the Roland builder
> > specifically** rather than carried over from the Ensoniq one.
>
> **The key quartet resolves the same way** — `entry[2..5]` from
> `patch+12..15` — and is nested identically: **low, fade, fade, high**,
> while Roland stores both quartets *ascending*. **So the "crossing" is the
> nesting transform**, now instruction-stream confirmed rather than argued,
> and an importer writing them in source order would be the broken one.

> ~~**[?] WHICH of `[7]`/`[8]` is the LOW fade is NOT established here, and
> this evidence structurally cannot establish it.**~~ *(Superseded above —
> kept because the reasoning was right: mirrored pairs genuinely cannot
> decide it, and it took a destination-side read to settle.)*
>
> **[?] WHICH of `[7]`/`[8]` is the LOW fade is NOT established here, and this
> evidence structurally cannot establish it.** Every pair contains both
> orderings — that is what mirroring means — so the corpus proves the two
> bytes are a crossfade pair and says nothing about their roles. The
> low/high labelling in the table above is **inference from position**, on
> the nesting pattern below. *Anyone needing the distinction should treat it
> as open.*
>
> **The asymmetric case now EXISTS, and it decides the semantics — but not
> yet the byte order.** eosed's Roland import produced a four-zone velocity
> stack, dumped over SysEx and **decoded independently here** from
> `preset009.bin` (14-bit word stream, zone blocks at word 188 stride 13).
> Read in the dump's own ascending order — `vlow, vlowfade, vhigh,
> vhighfade`, parameter ids 49–52:
>
>     zone 0      1,  0,  78,  7
>     zone 1     73,  7,  93,  7
>     zone 2     88,  7, 108,  7
>     zone 3    103,  7, 127,  0
>
> **Every outer edge carries 0 and every internal edge carries 7**, at both
> ends of the stack and on both middle zones. `[C]` — **the pair is per-edge**,
> and the two middle zones carrying 7 on *both* sides are the part 18 mirrored
> corpus pairs could never have shown.
>
> **[S] What that makes of `[7]`/`[8]`.** The SysEx dump is **ascending** and
> this table is **nested**, so the measurement does not land on a byte index
> by itself. The bridge is EOS's Roland zone builder: it writes `partial+10`
> (now measured as `vhighfade`) to zone `6`, which under the `zone_base + 2`
> pointer convention is entry `[8]`. **So `[8]` is the HIGH fade and `[7]` the
> LOW fade — this table is right** — but the convention is inferred from the
> *Ensoniq* builder rather than read in the Roland one, so it stays `[S]`.
>
> **What would make it `[C]`: an E4B FILE from that import.** A SysEx preset
> dump cannot settle a byte order in the file format. The bank is already
> loaded on the E4XT; saving it to disc and parsing entry `[6..9]` of the
> bottom zone ends the question — non-zero `[7]` there would mean this table
> is backwards.

**The nesting pattern, which is why the fades sit between the endpoints.**
E-MU stores every range as `[low, fade, fade, high]`, at three independent
places in this format:

| | low | fades | high |
|---|---|---|---|
| zone entry, key | `[2]` | `[3]`,`[4]` | `[5]` |
| zone entry, velocity | `[6]` | `[7]`,`[8]` | `[9]` |
| voice window, key | `vpar[14]` | `vpar[15]`,`vpar[16]` | `vpar[17]` |

**A source format that stores the four ASCENDING must therefore cross its
last two on the way in.** Roland does (`partial+7` vlow, `+8` vlowfade, `+9`
vhigh, `+10` vhighfade), and EOS's Roland importer writing its third source
field to the fourth destination slot is **the transform, not a defect** — a
reading that cost one cross-project round trip to establish, because the
firmware note recorded the destination offsets relative to a zone pointer at
`zone_base + 2` while this table indexes from the entry. `[3]`/`[4]` are zero everywhere in the corpus, so their identification
rests on the firmware alone — but a **second** importer writes them.
EOS's **Roland** importer fills the key-fade pair from `patch+13`/`patch+14`
while the Ensoniq one zeroes it, so **a Roland-sourced bank is where non-zero
values in `[3]`/`[4]` would be found**, and no such bank exists on this side
yet. Two independent traces placing the same pair at the same offsets is
worth more than one; it is still not a corpus check.

**A free confirmation of `[12:14]` from the same trace.** Roland's importer
computes fine tune as `(partial[6] * 64 + 32) / 100` — round-half-up on a
divide by 100, i.e. `round(cents * 0.64)`. Roland stores ±50 cents, so a
half-semitone is 32 units and **the E4 fine-tune unit is 1/64 semitone**,
which is what this table has said since it was decoded from the commercial
library CD-ROMs. Different importer, different source format, same unit.

**mpc2emu writes zero to all four** — no source format in the pipeline states
a zone crossfade — so a bank we write and read back is unaffected. What is
affected is reading someone else's: a crossfaded pair currently arrives as two
zones at full level over the same range.

**`[12:14]`/`[15]`/`[16]` are the zone's ABSOLUTE fine-tune/volume/pan, used
only when a voice has MULTIPLE sample zones — not a delta on top of the
voice's `vpar[36]`/`[54]`/`[55]` (§4.1).** A single-zone voice instead
writes its one zone's value directly into `vpar[36]`/`[54]`/`[55]` and
leaves these three bytes zero. Three-stage hardware investigation
(2026-07-26), all writing to the SD card as `HD0.img` and byte-diffed:

1. Decoded by [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss)
   (PR #220, commit `7ce000f`) from 76057 zones across commercial library CD-ROMs, as an offset on top of the voice's own settings.
2. `B.012 "Vce VolPan"` (7 *single-zone* voices, distinct front-panel
   Volume/Pan each) appeared to disprove it entirely — every zone entry
   stayed zero, `vpar[54]`/`[55]` matched the front-panel values exactly.
3. `B.013 "MultiSZpVce"` (**one voice, 7 sample zones**, each given a
   distinct Volume/Pan/Fine-tune) showed the zone entries ARE used for a
   multi-zone voice, matching CWM's offsets exactly — but its own zone
   volumes were already asymmetric (`+10, 0, 0, −96, 0, 0, 0`; a midpoint
   would be −43) and the firmware still wrote `vpar[54]=0`, not a
   composed baseline. That ruled out a delta model on its own, but every
   *test* built here up to that point had, by design, symmetric zone
   values (min = −max) — so the representative always landed on exactly
   0, and "delta from a nonzero voice value" vs. "absolute value, voice
   field simply unused" were still numerically indistinguishable in every
   case tried.
4. A dedicated `ASYMTEST` bank (one voice, two zones with deliberately
   ASYMMETRIC absolute values — `0`/`0`/`0` and `80c`/`20dB`/`+1.0`, giving
   a clearly nonzero midpoint of `+26`/`+10dB`/`+32`) — built by mpc2emu's
   own writer with the delta model still implemented — settled it: the
   E4XT displayed each zone's RAW entry bytes directly (the delta values,
   `−26`/`−10`/`−32` and `+25`/`+10`/`+32`), not the intended absolute
   values reconstructed via voice+delta. Confirms the absolute model; the
   delta model (as briefly implemented 2026-07-26) was wrong.

### 4.6 Sample chunk header (`E3S1` chunk body, 94 bytes)

Layout confirmed from emu3bm's `struct emu3_sample` (92 bytes) plus the 2-byte
`sample_idx` prefix EMU4/E4B adds in front of it:

| Offset | Size | Field | Notes |
|---|---|---|---|
| `0:2`   | 2  | `sample_idx`   | **BE u16** |
| `2:18`  | 16 | `name`         | sample name (+ trailing root-note text, see [§6.2](#62-name-encoding)) |
| `22:26` | 4  | `start_l`      | LE u32, always `92` (= header size) |
| `30:34` | 4  | `end_l`        | LE u32, `92 + pcm_bytes − 2` |
| `38:42` | 4  | `loop_start_l` | LE u32, byte offset from struct start (`loop_start × 2 + 92`) |
| `46:50` | 4  | `loop_end_l`   | LE u32, byte offset. Stores the frame **before** the true inclusive last loop frame: `(loop_end − 1) × 2 + 92`. See caveat below |
| `54:58` | 4  | `sample_rate`  | LE u32, Hz. **Informational only — EOS4 does NOT pitch from this field**, see below |
| `58:60` | 2  | pitch offset   | **signed LE i16**, 1/64-semitone units — see below. Zero for an untouched 44.1 kHz sample |
| `60:62` | 2  | `options`      | LE u16. `0x0020` = MONO_L; `0x0031` = MONO_L \| LOOP (forward; ping-pong is baked to forward upstream — EOS has no ping-pong mode) |
| `62:66` | 4  | `sample_data_offset_l` | LE u32, always `92` |

PCM data (16-bit LE) follows immediately at byte 94.

> **`loop_end_l` off-by-one, cross-referenced 2026-07-26.** Applied following
> [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) (PR #220,
> commit `2ccefea`), whose independent E4B reader measured the PCM amplitude
> step at the loop seam across a real commercial corpus: reading the raw
> `(loop_end_l − 92) / 2` value directly as the last loop frame left a
> nonzero-amplitude discontinuity at the seam in many cases; adding `+1`
> (capped at `numFrames − 1`) eliminated seams stepping by more than a third
> of the peak amplitude and raised the clean-seam share from 78% to 95%.
> `writers/e4b_writer.py` and `parsers/e4b_parser.py` both encode/decode this
> `-1`/`+1` consistently, so mpc2emu's own write→parse round-trip is still an
> exact identity — this only changes the *absolute* frame a loop_end value
> resolves to, which matters when reading a **third-party** `.e4b` (registered
> as an input format in `parsers/registry.py`). Not yet independently
> re-confirmed on mpc2emu's own hardware rig; the 1-frame (≈23 µs at 44.1 kHz)
> shift is below the threshold Jan's by-ear auto-loop HW confirmation could
> have caught either way.

**Pitch offset at `[58:60]` — hardware-RE'd 2026-07-24.** A sample stored below
44.1 kHz plays **sharp by `44100 / stored_rate`** unless this field is set; the
`sample_rate` field above is not used for playback pitch (EOS4 diverges here
from EOS3's `emu3bm`, which this whole struct layout is otherwise sourced
from). RE'd from hardware Sample-Rate-Convert captures (E4XT Sample Edit →
Tools1 → SrCnv to 6 known rates, diffing the resaved bank's `E3S1` headers
against an untouched 44.1 kHz sample in the same, EOS4-authored bank):

```
pitch_offset = round(768 · log2(rate / 44100))
```

Exact within ±2 units (≤3 cents) across the tested range (11025–48000 Hz);
`768 = 64 × 12`, i.e. 1/64-semitone resolution. `mpc2emu` writes this whenever
`sample_rate ≠ 44100` (`writers/e4b_writer.py`, `_sample_header`); a value of 0
leaves an already-44.1 kHz sample byte-identical to before the fix.

The companion field `[18:22]` (documented as `header = 0` above) was also
found non-zero on a hardware-resaved, rate-converted sample, but is **not**
pitch: the *same* rate conversion produced two different values across two
separate hardware saves — a non-deterministic per-sample token (likely a
checksum or edit-id), not signal. `mpc2emu` leaves it at 0.

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

**Minimum forward-loop length (HW-confirmed 2026-07-10).** A forward loop shorter
than ~84 frames plays an **octave low** — the E4XT silently doubles it. An
84-frame loop is fine; a 42-frame loop plays at half pitch. This bites
single-cycle waveforms of high notes (a 740 Hz cycle is only ~60 frames); the
`single_cycle` processor works around it by tiling the cycle to ≥256 frames (a
single-period loop of that pitch is physically impossible at a playable rate, so
identical repeats are the fix — see `docs/RESOLUTION_NOTES.md`).

---

## Sources & Attribution

This reverse-engineering effort drew on:

- **Hardware-saved E4XT banks** created and dumped by Jan Lentfer
  (`JL AnalogBank`, `FltEnvTest`, `FLTTYPES`/`FLTTYPES2` series, the
  `B.0xx-*` differential test series, and others referenced by name above) —
  the primary source for nearly every byte-level detail in this document.
- **Commercial EOS CD-ROMs**: library discs B, C and S (used to cross-check conventions against
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

---

## Cross-reference: the EOS editor-protocol parameter spec (2026-08-01)

The sibling project **eosed** (`~/git-repos/eosed`) talks to the E4XT live over
E-mu's *editor protocol* SysEx, and in doing so transcribed E-mu's own
parameter specification — ~270 parameters with names, ranges, units and, for
several, the literal display-conversion functions from the spec's C source
(`eos/params.py`, their RESOLUTION_NOTES §2).

That document is authoritative in a way this file's contents are not: almost
everything here was reverse-engineered by differential saves and byte hunting.
Three things are worth taking from it, and one raises a question about our own
calibration.

### 1. Official names for things we RE'd anonymously

The parameter ids are **not** our `vpar[]` offsets — they are a separate SysEx
id space (e.g. non-transpose is parameter 57 there, `vpar[38]` here) — but the
*semantics, ranges and units* describe the same machine, and they corroborate
the RE:

| spec parameter | range / unit | our field |
|----------------|--------------|-----------|
| `E4_VOICE_NON_TRANSPOSE` | 0/1 | `vpar[38]` |
| `E4_VOICE_CHORUS_AMOUNT` | 0–100 % | `vpar[42]` |
| `E4_VOICE_VENV_SEG0..4_RATE` / `_TGTLVL` | 0–127 / 0–100 % | the 6-stage amp PZT pairs |
| `E4_VOICE_VOLENV_DEPTH` | 0–16, "−96 dB to −48 dB by 3's" | not written |

### 2. The 6-stage envelope segments have official names

`Atk1 / Dcy1 / Rls1 / Atk2 / Dcy2 / Rls2` — exactly the rate/level pair
structure RE'd here, confirming the pairing and the ordering independently.

### 3. E-mu documents a closed-form cutoff byte → Hz conversion

```
fil_freq(value, maxfreq, mul):   # value 0..255
    f = maxfreq
    repeat (255 - value) times:  f = f * mul // 1024
    return f
```

with three tables — `(20000, 1002)`, `(18000, 1003)`, `(10000, 1006)` —
selected by filter type.

**It does not agree with the cutoff law measured here on 2026-07-31**, by up
to 3× in the middle of the range. That is not necessarily a contradiction,
because the two describe different quantities:

- the spec's value is the **displayed / design** frequency, which is what the
  front panel shows;
- ours is the **acoustic −3 dB corner** of a 4-pole lowpass, measured on noise.

A 4-pole cascade's −3 dB point sits well below its design frequency, and the
disagreement runs in exactly that direction. So both may be right about their
own quantity.

**But that leaves a real question about which one mpc2emu should target.**
Source formats (SF2, EXS24, SFZ, GIG) specify a filter *design* frequency, the
same convention as the panel — not a measured −3 dB point. If so, the
2026-07-31 calibration, which makes the acoustic corner match the requested Hz,
may be systematically **low**, and the spec's closed form would be the better
mapping — with the added advantages of covering all 256 byte values exactly and
being per-filter-type rather than measured on one type only.

**Settled 2026-08-01 — the premise was wrong, and no change was needed.** The
worry assumed a cascade of 1-pole sections. Measuring the asymptote instead of
the corner shows the E4XT's 4-pole lowpass running at ~24 dB/oct with its
extrapolated design frequency within 5-19% of its −3 dB point, so the two
conventions name nearly the same frequency. The spec's tables turn out not to
describe this filter well either: T3 is closest (exact at byte 96) but drifts
24% off by byte 160. Per-type differences are explained by filter ORDER — the
same byte on Low 2/4/6-pole gives 1037 / 872 / 734 Hz, monotonic with pole
count — not by table assignment. See `TODO.md` for the full result.

### What flows the other way

eosed deliberately did **not** transcribe the LFO-rate display table (their §2:
the source table's page-wrap is ambiguous). This project calibrated it
empirically instead, from the E4XT's own rate menu — byte 0 = 0.08 Hz,
64 = 4.12 Hz, 127 = 18.01 Hz, fitted log-quadratically in `models/common.py`.
That is usable by them directly.


### Mod-cord amounts: the file is ±127, the parameter interface is ±100

**Measured 2026-09-07 across three cords on two presets, exact in all three.**
A cord amount stored in the `.E4B` file as a signed byte in ±127 is reported by
the E4XT's parameter interface (SysEx dump / editor) in **±100**, i.e. as a
percentage. Full scale maps to full scale and the conversion is exact:

    preset                 file byte    interface    file x 100/127
    P001 static             92          72             72
    P005 static            -12          -9             -9
    P008 gate               67          53             53

`100/127 = 0.7874`; small magnitudes round to apparent ratios of 0.75-0.79,
which is why it first looked like a variable discrepancy rather than a constant.

**Practical consequence:** an oracle or test fixture captured from the machine is
in interface units. Comparing it against file bytes without the `x127/100`
conversion makes every cord look 27% wrong. State the unit wherever such a
fixture is stored — this cost an evening's confusion on the day it was found,
and it was misdiagnosed twice before being measured (once as a writer defect,
once as an unexplained "0.77 of prediction").

## Cord SOURCE ids — the full table, and why counting the manual's list fails

Transcribed from the EOS SysEx spec (eosed §142) with three ids
hardware-confirmed. **`0x0F`, `0x1C`-`0x1F` are unused.**

| | | | |
|---|---|---|---|
| `0x00` Off | `0x04` XfdRnd | | |
| `0x08` Key+ | `0x09` Key~ | `0x0A` Vel+ | `0x0B` Vel~ |
| `0x0C` Vel< | `0x0D` RlsVel | `0x0E` Gate | |
| `0x10` PitWl | **`0x11` ModWl** | `0x12` Press | `0x13` Pedal |
| **`0x14` MidiA** | `0x15` MidiB | `0x16` FtSw1 | `0x17` FtSw2 |
| `0x18` Ft1FF | `0x19` Ft2FF | `0x1A` MidiVl | `0x1B` MidPn |
| `0x20` MidiC | `0x21` MidiD | `0x22` MidiE | `0x23` MidiF |
| `0x24` MidiG | `0x25` MidiH | `0x26` Thumb | `0x27` ThmFF |
| `0x30` KeyGld | | | |

**THE IDS ARE BANKED IN GROUPS OF EIGHT, aligned to multiples of 8, with
padding at the end of each bank.** Gate ends the `0x08` bank at `0x0E`, `0x0F`
is unused, and PitWl starts the next at `0x10`. MidPn ends the `0x18` bank at
`0x1B`, and MidiC starts a fresh bank at `0x20`. The same banking runs through
the rest of the table — envelopes at `0x48`/`0x50`/`0x58`, LFOs at
`0x60`/`0x68`, clocks at `0x90`, maths at `0xA0`.

**So a sequential count through the EOS manual's display order DRIFTS at every
bank boundary**, which is why the manual's list cannot be numbered by position.
Counting from Key = 8 puts Mod Wheel at `0x10`; the hardware says `0x11`.

**The eight MIDI A–H sources are per-preset** — they are ordinary cord sources
written into the file. Only **which CC drives each letter** is global, at master
parameters 208–215 (`MIDIGLO_MIDI_A_CONTROL`..`_H_`), and a preset file cannot
carry it. The stored value IS the CC number: **0–31 = CC 0–31, 32 = pitch wheel,
33 = channel pressure, −1 = off**. EOS therefore reaches **CC 0–31 only**;
anything at CC 32 or above has no home on these sources.

> On the E4K and E-Synth Keyboard the four realtime controller sliders are
> permanently assigned to MIDI controllers A–D. (EOS 4.0 manual)

So `MidiA` is the first physical slider on a keyboard E-MU, which makes it the
natural target for a source-machine slider rather than a similarity judgement.

**A NEAR-MISS WORTH KEEPING.** This table was predicted from the manual's list
order before it was available, and the prediction was right through `0x15` and
wrong from `0x16`: it put MIDI C and D at `0x16`/`0x17`, **which are `FtSw1` and
`FtSw2` — foot SWITCHES.** Writing a slider mapping to `0x16` would have put a
switch into Filter Freq, producing an on/off jump instead of a sweep — the kind
of wrong that survives a spot check because something does move. The prediction
was checkable against known anchors exactly where it was right.

**Hardware-confirmed, three independent routes** (eosed): `MidiF` = `0x23` = 35
— eosed §133 drove CC 26 and got modulation through source 35; a cord Jan set from the
front panel as "MIDI F (CC 26) → FilFreq" reads back as source 35; and master
parameter 213 reads 26.

**Cord-amount destinations go further than the spec transcribes.**
`CORD_DESTINATIONS` documents `C00Amt`..`C03Amt` at 168–171, but eosed §95/§98 measured
`ModWheel → 176` driving **cord 8**'s amount on hardware, and 168 + 8 = 176. So
**destination `168 + n` sets cord n's amount** for any n, not just 0–3.

### Factory CC assignments — FROM THE FIRMWARE, not from a machine

Byte-identical in EOS 4.62 (body `0x12dfa2`) and 4.70 (`0x1dcff8`), fifteen
values matching the fifteen assignment parameters 201–215:

    32  1  33  4  5  6  20  21  22  23  24  25  26  27  28

| param | | factory | Jan's E4XT |
|---|---|---|---|
| 201 | Pitch | pitch wheel | pitch wheel |
| 202 | Mod | CC 1 | CC 1 |
| 203 | Pressure | chan pressure | chan pressure |
| 204 | Pedal | CC 4 | CC 3 *(changed)* |
| 205 | Switch 1 | CC 5 | CC 0 *(changed)* |
| 206 | Switch 2 | CC 6 | CC 1 *(changed)* |
| 207 | Thumb | CC 20 | CC 2 *(changed)* |
| 208–215 | **MIDI A–H** | **CC 21–28** | 21, **7**, 23–28 *(B changed)* |

**This also validates the value encoding from a source with no machine state in
it**: `32` and `33` sit in the default block exactly where Pitch and Pressure
are, which is what "32 = pitch wheel, 33 = channel pressure" predicts.

**A READ-BACK FROM ONE MACHINE LOOKS EXACTLY LIKE A FACTORY TABLE.** These were
first taken off Jan's E4XT and nearly recorded here as defaults. The only thread
was that one of the eight sat on CC 7 (MIDI Volume) while the other seven ran
contiguously — a hand edit, and 22 was the hole it left. Had *seven* of eight
agreed with the factory run, the eighth would have read as a firmware variation
rather than a user edit. Jan had also moved Pedal, both switches and Thumb onto
CC 0–3, which the seven-point run could not have revealed.

**For a diagnostic that asks a user to assign a letter: name both values** —
"assign MIDI A = CC 06 in the Master menu; the factory value is CC 21" — because
it is a change to a factory value, not a restore.

### CC 6 and RPN/NRPN — no handling found

CC 6 is Data Entry MSB in the MIDI spec, and a device that implements RPN/NRPN
may consume it. **EOS 4.70 shows no sign of doing so.** RPN and NRPN both require
recognising a selector pair — 98/99 for NRPN, 100/101 for RPN — and immediate
compare sites in the disassembly are:

    CC 1   271      CC 98    1  (a 32-bit cmpl, not a controller test)
    CC 7    53      CC 99    0
    CC 27   26      CC 100  17  (all 32-bit `cmpl #100`, percentage tests)
                    CC 101   0

EOS dispatches controllers by comparison — CC 1 alone has 271 sites — so the
absence of 99 and 101 is meaningful rather than an artefact of table-driven
dispatch. **Weaker evidence than a hardware sweep**, and a jump-table dispatch
would leave no compares at all; but a *positive* here would have killed the
mapping outright and it is not there.
