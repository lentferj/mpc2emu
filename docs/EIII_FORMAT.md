<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# E-mu EIII Bank Format (`.E3B` / `.E3X` / `.ESI`) — Reference

This document describes the on-disk layout of E-mu **Emulator III / Emulator
IIIX / ESI-32/2000/4000** bank files, as used by `writers/eiii_writer.py` and
`parsers/eiii_parser.py`. A bank holds the presets *and* the sample data of a
sound — the bank file is the whole instrument, not a reference to external
samples.

The **E4XT (EOS 4.x) loads EIII banks natively** for backward compatibility,
which is what makes hardware confirmation of this writer possible without
EIII/ESI hardware: a `.e3x` bank built by this project can be placed on the
same EMU3-filesystem CD/HD image this project already builds for E4B output
(`writers/iso_builder.py` is bank-format-agnostic — it just streams whatever
file it is given) and loaded on the E4XT directly.

> **Implementation reference:** the canonical, always-up-to-date layout lives
> in [`writers/eiii_writer.py`](../writers/eiii_writer.py) (serialization) and
> [`parsers/eiii_parser.py`](../parsers/eiii_parser.py) (reading). Where this
> document and the code disagree, trust the code.

## Sources & attribution

The structures below were originally reverse-engineered by the GPL tool
**emu3bm** by David García Goñi (https://github.com/dagargo/emu3bm; also
available locally at `../emu3bm`), the same project underlying **emu3fs**
(`../emu3fs`). [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss)
independently re-verified and corrected three details of emu3bm's model
(PR [#230](https://github.com/git-moss/ConvertWithMoss/pull/230)) against 22
commercial EIIIX/ESI library CD-ROMs (3,424 presets / 25,596 zones / 8,073
samples, byte-identical PCM) — see its
`documentation/design/EIII_FORMAT.md`. This document and mpc2emu's
implementation are derived from that corrected model (no source code was
copied; the Java was read for structure and re-implemented from scratch in
Python against mpc2emu's own `Bank`/`Preset`/`VoiceLayer`/`ZoneMapping`
model). Written banks have **not yet been hardware-confirmed** — see
`TODO.md`.

All multi-byte values are **little-endian** (unlike E4B/KRZ, which are
big-endian — EIII/ESI ran on different hardware). Sample positions are byte
offsets, not frame indices.

## Bank variants

The first 16 bytes of a bank are an identifier: 15 characters followed by a
terminating zero byte. All three variants use the same preset, zone and
sample structures and only differ in the position and size of the two
address tables which locate them.

| Identifier        | Devices                      | DOS ext | Preset table | Sample table | Preset area | Presets | Samples |
|--------------------|------------------------------|---------|--------------|--------------|-------------|---------|---------|
| `EMULATOR THREE `  | Emulator III                 | `.e3b`  | 0x006C       | 0x0204       | 0x074A      | 100     | 99      |
| `EMULATOR 3X   `   | Emulator IIIX, ESI-32        | `.e3x`  | 0x17CA       | 0x1BD2       | 0x2B72      | 256     | 999     |
| `EMU SI-32 v3  `   | ESI-32 / ESI-2000 / ESI-4000 | `.esi`  | 0x17CA       | 0x1BD2       | 0x2B72      | 256     | 999     |

mpc2emu writes **`EMULATOR 3X` (`.e3x`)** by default — it is the variant the
E4XT's compatibility loader is documented to read, and it has the largest
preset/sample capacity of the three. `EMULATOR THREE` additionally biases
every entry of its preset address table by `0x1A6FE`; the other two variants
use no bias (and still carry an empty/unused `EMULATOR THREE`-shaped table at
0x6C for compatibility).

On an E-mu-formatted disk (EMU3 filesystem — see
`docs/EMU3_ISO_FORMAT.md`) bank files carry **no extension at all**; the DOS
extensions above are only what the E-mu FAT/DOS tools use, and what
mpc2emu's `--iso`/`--hda` machinery strips back off (`Path.stem`) when
placing a bank onto an EMU3 image.

## Bank header

```
offset size
0      16   char   identifier (see above)
16     16   char   bank name, padded with spaces
32     4    uint32 number of objects - unreliable, empty banks hold 1 or 25
36     12   3 x uint32, always 1
48     4    uint32 position behind the last preset
52     4    uint32 position behind the last sample, relative to the sample area
56     4    uint32 unknown, always 0x00800000
60     4    uint32 number of 512 byte blocks which the presets occupy
64     4    uint32 number of 512 byte blocks which the samples occupy
68     4    uint32 unknown, always 0
72     4    uint32 number of 512 byte blocks of the whole bank
76     16   char   second copy of the bank name
92     4    uint32 index of the preset which is selected when the bank is loaded
96     12   3 x uint32 parameters
```

The block counts split the bank at the filler byte (see below):
`presetBlocks + sampleBlocks == totalBlocks`.

An **empty bank** (header + address tables + master-settings block the
sampler expects on load, but no presets/samples) is `0x2B73` bytes for the
non-compact variants; see `_empty_bank()` in the writer.

## Address tables

Both tables hold one entry per slot plus one terminating entry.

**Preset table** — entry *i* is the offset of preset *i* relative to the
preset area:

```
presetOffset(i) = presetArea + table[i] - bias
```

A slot whose entry equals the entry of its successor is **empty** (what
deleting a preset leaves behind) — this is a per-slot test, not a
terminator: the table must be walked to its end, since presets can follow an
empty slot. The terminating entry is the total size of the preset area.

**Sample table** — entry *i* is the address of sample *i+1* (sample numbers
are **1-based**) relative to the sample area, biased by `0x400000`:

```
sampleAddress(i) = sampleArea + table[i] - 0x400000
sampleArea       = presetArea + 1 + presetTable[maxPresets] - bias
```

The single filler byte between the presets and the samples is `0x74` in
EIIIX banks and `0xEE` in ESI banks; its value does not appear to matter.

An entry of `0` marks an **empty slot** (a deleted sample) — again not a
terminator, since valid samples can follow a hole. The terminating entry
points behind the last sample and equals the bank's file size.

## Preset (142 bytes header + note zones + zones)

```
offset size
0      16   char   preset name, padded with spaces
16     12   int8   real-time controller assignments (10 controllers + 2 footswitches)
28     16   int8   unknown
44     1    int8   pitch bend range in semitones
45     1    uint8  lowest velocity of the primary layer
46     1    uint8  highest velocity of the primary layer
47     1    uint8  lowest velocity of the secondary layer
48     1    uint8  highest velocity of the secondary layer
49     2    uint16 1-based number of the preset which is layered on top of this one, 0 = none
51     2    int8   unknown
53     1    uint8  number of note zones
54     88   uint8  one entry per key: index of its note zone, 0xFF = unmapped
```

Key `0` is MIDI note 21 (A-1 on E-mu's display), key `87` is MIDI note 108.
A velocity range with a high value of `0` means "not restricted". The
**link** field chains presets that play together — this is how the sampler
stacks more than the two layers a single preset provides, and is how
mpc2emu maps a `Preset` with more than one `VoiceLayer`: each `VoiceLayer`
becomes one linked EIII preset, one per layer, with that layer's zones'
velocity extent written into the primary velocity range.

### Note zone (4 bytes)

```
0  uint8  options (crossfade/switch settings) — mpc2emu writes 0
1  uint8  options, high byte — mpc2emu writes 0
2  uint8  index of the zone of the primary layer, 0xFF = none
3  uint8  index of the zone of the secondary layer, 0xFF = none
```

The key range of a note zone is **not stored** — it is given by the keys of
the preset's key map that point at it. mpc2emu (like ConvertWithMoss) only
ever populates the **primary** layer slot; the secondary slot is always
`0xFF`. Real EIII banks use the secondary slot for crossfade/velocity-switch
layering within a single preset — out of scope here since mpc2emu's own
`VoiceLayer`-per-preset-link model already covers multi-layer presets.

### Zone (48 bytes)

```
0   uint8  original key (0..87), the key at which the sample plays at its recorded pitch
1   uint16 1-based sample number; ESI samplers use bits 14/15 as unknown flags
3   int8   unknown — EIIIX writes 0x1F, ESI writes 0x00
4   5      amplifier envelope: attack, hold, decay, sustain, release
9   uint8  LFO rate            \
10  uint8  LFO delay            } not written by mpc2emu — see note below
11  uint8  LFO variation       /
12  uint8  filter cutoff
13  uint8  filter Q; bit 7 enables its real-time control (set for ESI)
14  int8   filter envelope amount
15  5      filter envelope
20  5      auxiliary envelope (only its pitch destination has an mpc2emu equivalent)
25  int8   auxiliary envelope amount
26  uint8  auxiliary envelope destination: 0 off, 1 pitch, 2 pan, 3 LFO rate,
           4 LFO->pitch, 5 LFO->VCA, 6 LFO->VCF, 7 LFO->pan
27-39      per-parameter velocity/LFO routing bytes — not written by mpc2emu
40  int8   amplifier level (0..127)
41  int8   tuning, -64..64 for -100..100 cents (1.5625 cents/LSB)
42  int8   filter key tracking, -127..127 for -2.0..2.0
43  uint8  note-on delay, 0x00..0xFF for 0.00..1.53 s — not written by mpc2emu
44  uint8  panorama, 0 fully left, 0x40 centered, 0x7F fully right
45  uint8  filter type (upper 5 bits, ESI only) and LFO shape (lower 2 bits)
46  uint8  flags which enable the real-time controls — mpc2emu writes 0xFF (all)
47  uint8  flags: 0x02 non-transpose, 0x04 envelope trigger mode, 0x08 chorus,
           0x10 solo, 0x20 disable loop, 0x40 disable left, 0x80 disable right
```

**LFO not modeled.** Neither ConvertWithMoss's EIII implementation nor
mpc2emu's reads or writes the per-zone LFO rate/delay/variation/shape or its
routing bytes — the byte positions are documented (bytes 9-11, 36-39, low 2
bits of byte 45) but their value scales have not been reverse-engineered
against hardware, so mpc2emu leaves them at `0`, which is the sampler's
"LFO present but silent/unrouted" state. This mirrors mpc2emu's own
intentional non-goal for E4B's LFO2 in early revisions — fill in once
hardware-confirmed.

**Sample number flags.** The ESI banks set bit 14 or bit 15 of the sample
number for reasons that are still unknown (comparing the same library bank
in EIIIX and ESI-4000 form shows the two differing only by exactly `0x4000`
or `0x8000` on ~5% of zones). `parsers/eiii_parser.py` masks with
`ZONE_SAMPLE_INDEX_MASK = 0x3FFF` when reading; `writers/eiii_writer.py`
never sets these bits.

**Truncated sample numbers on the library CD-ROMs.** Some E-mu library
CD-ROM banks (library disc B, a General MIDI sample set, a few classic-volume
banks) were mastered through a tool chain that wrote a zone's 16-bit sample
index through 8 bits: the low byte is the true sample slot modulo 256, the
high byte is zero or stale garbage. A preset whose samples sit above slot
256 then plays completely unrelated material (an "OBX Strings" preset
playing basketball-bounce samples, per ConvertWithMoss's own writeup). This
is a mastering-tool artifact of specific commercial discs, **not** a
hardware or format bug — real EIII/EIIIX hardware reads the full 16-bit
index correctly, which is presumably why it was never reported as a known
issue over 25+ years: the affected presets are a small fraction of any
given bank (running the repair below over mpc2emu's own 1118-image corpus
(1017 directory-listed banks; see TODO.md):
4,144 of 251,697 zone→sample references repaired, across 771 presets, 0
parse failures — a similar scale to ConvertWithMoss's own 4,756/821 over
their 8-CD-ROM set), and E-mu's library CD-ROMs have had no support channel
to surface it through. `parsers/eiii_parser.py`
repairs this per preset (`_resolve_bank_repairs` and friends), inferring
the correct page from the note names E-mu sample names carry
("OBXStringD2"), the preset name occurring in the target sample names, and
page feasibility against the sample table — a preset whose evidence is
ambiguous keeps its stored indices. Ported from ConvertWithMoss's
`Emulator3SampleIndexRepair.java` (PR #252, GPL-3), same scoring thresholds.

**Filter type.** Only the ESI samplers store a filter type (19 types encoded
in the upper 5 bits of byte 45). The EIII and EIIIX have a single fixed
4-pole low-pass filter — scanning the reference library CD-ROMs shows their
zones never set the filter-type-selecting bits. mpc2emu writes `0` (i.e. the
EIIIX/EIII default) regardless of target variant, since `VoiceLayer` models
one filter without an EIII-specific type enum.

**Conversion tables.** Envelope stage times, filter cutoff, and panorama are
**table indices**, not linear values — the tables live in
`writers/eiii_writer.py` / `parsers/eiii_parser.py` (`_ENVELOPE_TIME`,
`_CUTOFF_FREQUENCY`, `_PANORAMA`), ported byte-for-byte from
`Emulator3Constants`. Envelope times run 0 – 163.69 s; cutoff runs 26 Hz –
74040 Hz.

## Sample (92-byte header + 16-bit PCM)

```
offset size
0    16   char   sample name, padded with spaces
16   4    uint32 unknown
20   4    uint32 position of the first frame of the left channel (always 92)
24   4    uint32 position of the first frame of the right channel, 0 if mono
28   4    uint32 position of the last frame of the left channel
32   4    uint32 position of the last frame of the right channel, 0 if mono
36   4    uint32 loop start of the left channel
40   4    uint32 loop start of the right channel
44   4    uint32 loop end of the left channel
48   4    uint32 loop end of the right channel
52   4    uint32 sample rate in Hz
56   2    uint16 encoded playback rate, 0 for 44100 Hz
58   2    uint16 options
60   4    uint32 position of the left channel in the sample memory
64   4    uint32 position of the right channel in the sample memory
68   24   6 x uint32 parameters
92   ...  16-bit PCM data
```

All positions are byte offsets **relative to the start of this 92-byte
header**: number of frames = `(endLeft + 2 - 92) / 2`; a loop position in
frames = `(loopStart - 92) / 2`. The two channels of a stereo sample are
stored **one after the other, not interleaved** — left occupies
`92 .. 92 + frames*2`, right follows it.

Option flags:

```
0x0001  looped
0x0008  loop continues during the release phase; without this flag the
        loop stops as soon as the key is released
0x0020  sample has a left channel
0x0040  sample has a right channel
```

Sample rates are arbitrary (not a fixed set). The sampler always plays back
at 44.1 kHz and compensates a lower source rate via the encoded playback
rate: `0xF800 | (int)(-9799 + 1108 * ln(rate)) & 0x7FF`.

## Device requirements when writing

* The first and last two frames of every channel must be silent, or the
  sampler reports `Mono Start Zero!!!`.
* A loop position must keep a distance of 6 frames from the sample start and
  7 frames from the end, and must be at least 10 frames long.
* Sample memory is limited to **128 MB** per bank (same limit CLAUDE.md
  documents for E4B).
* `EMULATOR 3X`/`EMU SI-32 v3` cap out at **256 presets / 999 samples** per
  bank — tighter than E4B's 1000/1000 (`bank_splitter.py`'s
  `_MAX_PRESETS_PER_BANK`/`_MAX_SAMPLES_PER_BANK` are not yet EIII-aware; see
  `TODO.md`).

## What mpc2emu does not (yet) implement

Scoped out for the initial implementation, matching ConvertWithMoss's own
current scope:

* **Reading/writing directly from/to `.iso`/`.img`/`.hda` EMU3-filesystem
  images.** Not needed here — mpc2emu already builds EMU3/EOS images for
  E4B via `writers/iso_builder.py`/`writers/hda_builder.py`, and those
  builders are bank-content-agnostic, so an `.e3x` file produced by
  `eiii_writer.py` slots into the exact same pipeline used for E4B.
* **Per-zone LFO** (see above).
* **The secondary note-zone layer / preset-level crossfade options** (see
  above) — mpc2emu's own multi-`VoiceLayer` model is expressed as chained
  presets instead.
* **ESI-specific filter types** (swept EQ, phaser, flanger, vocal formant) —
  `VoiceLayer` has no equivalent parameter space; would need a model
  extension, not just a writer change.
