<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# mpc2emu

Multi-format sampler converter with vintage resampling and ZuluSCSI output.
Converts sample libraries between common sampler formats and produces
ZuluSCSI-ready CD ISO images or native SCSI hard disk images for the
EMU Emulator 4 / E4XT and Kurzweil K2000 series.

> **See also:** [README_de.md](README_de.md) — German / Deutsche Version  
> **Legal:** [DISCLAIMER.md](DISCLAIMER.md) · [LICENSE](LICENSE)

---

## ⚠️ Use at your own risk — back up first

mpc2emu is provided **as is, with absolutely no warranty and no liability** for
lost data, damaged hardware, corrupted media, or any other harm arising from its
use. You assume all risk. (Full terms: [DISCLAIMER.md](DISCLAIMER.md).)

**Before you use this software, make good, current backups of all your files** —
and of any existing banks on your sampler and SCSI media. mpc2emu writes raw disk
images and can **modify existing images in place** (`--add-to`); a mistake, a bug,
or untested output could overwrite or corrupt data, or be rejected by hardware.
Always test images on a ZuluSCSI / SCSI2SD / emulator **before** connecting
irreplaceable equipment.

---

## AI assistance & human authorship

mpc2emu was built by its human author together with Anthropic's **Claude**. The
**ideas, the project vision, and every feature** came from the human author;
Claude assisted with **writing the code and analyzing the binary formats**.
Crucially, the **reverse engineering rests on hands-on human work** — all testing
and verification on real E-mu E4XT hardware, creating the RE reference images on
that hardware, and aural A/B comparison of presets — which is what makes the
results correct. Full account in [DISCLAIMER.md](DISCLAIMER.md).

---

## Supported Formats

### Input

| Format | Extension | Description |
|---|---|---|
| EMU E4B | `.e4b` / `.E4B` | EMU Emulator 4 / E4XT bank — import for resampling / re-export |
| Akai MPC Keygroup | `.xpm` | MPC 2.x / MPC X / Live / One (XML) |
| Akai MPC drum program | `.pgm` | MPC 500/1000/2500, **MPC 2000/2000XL** (`.WAV`) and MPC 60 (12-bit `.SND`) |
| Akai MPC60 SET / floppy | `.set` / `.img` | MPC 60 RAM set; `.img` = FAT12 floppy (SET auto-extracted) |
| TAL-Sampler | `.talsmpl` | TAL Software GmbH (XML + WAV) |
| SFZ v1/v2 | `.sfz` | Open standard, `#include` supported |
| SoundFont 2 | `.sf2` | RIFF-based, E-mu / Creative |
| Logic EXS24 | `.exs` | Logic Pro / MainStage — little-endian classic and v1.1 (Logic 10.4+) |
| GigaSampler / GigaStudio | `.gig` | DLS2-based, uncompressed only |
| Zampler | — | Uses SFZ natively → read via SFZ parser |
| **WAV sample folder** | _directory_ | Point at a directory of root-note-named `.wav`s (e.g. `Piano C3.wav`, `Pad_60.wav`) → auto-builds one multisample preset (`--from-samples`; auto-detected for a WAV-only dir; `--middle-c` sets the octave convention) |

> `.pgm` covers three **binary** drum-program formats, auto-detected by magic:
> MPC500/1000/2500 (`MPC1000 PGM 1.00` — 64 pads, each pad's 4 samples → velocity
> layers); MPC2000/2000XL (`0x07 0x04` — 64 pads referencing external `.WAV`);
> and MPC 60 (`0x07 0x00` — external 12-bit `.SND`, decoded to 40 kHz). Sample
> files sit next to the `.pgm`; for an MPC2000 **ISO9660 CD**, extract it first
> (e.g. `7z x disc.iso`) and convert the resulting folder. Other `.pgm` variants
> (e.g. Akai `BD12`) and the XML `.xpm` are handled separately.  
> `.talwav` files (TAL-encrypted) cannot be read.  
> Giga-compressed samples are not supported; uncompressed `.gig` files work.  
> EXS24 v1.1 (Logic 10.4+, magic `0x00000101`): zone–sample mapping is positional;
> multi-velocity-layer instruments load only the first layer.

### Output

| Format | Extension | Target device |
|---|---|---|
| EMU E4B | `.E4B` | EMU Emulator 4 / E4XT / E4K (EOS 4.x) |
| Kurzweil KRZ | `.KRZ` | Kurzweil K2000 / K2500 / K2600 |
| TAL-Sampler | `.talsmpl` | TAL-Sampler VST/AU |

---

## Requirements

- Python 3.8 or later
- No mandatory third-party dependencies (standard library only)

---

## Installation

```bash
git clone https://github.com/youruser/mpc2emu.git
cd mpc2emu
```

---

## Quick Start

```bash
# NOTE: output defaults to --format e4b (EMU E4B). The examples below pass it
# explicitly; use --format krz (Kurzweil K2000) or --format talsmpl (TAL-Sampler)
# to change it. Note --hda is e4b-only and --floppy is krz-only.

# Inspect a file without converting
python convert.py Piano.sf2 --info
python convert.py DrumKit.sfz --info --verbose

# Convert XPM to E4B + ZuluSCSI CD ISO
python convert.py MyDrums.xpm --format e4b --iso

# Convert XPM to E4B + ZuluSCSI SCSI hard disk image
python convert.py MyDrums.xpm --format e4b --hda

# Convert a whole folder, 32 MB banks, both ISO and HDA
python convert.py /mpc/programs/ --format e4b --bank-size 32 --iso --hda

# B.NNN prefix naming (for E4XT bank slot ordering)
python convert.py /mpc/programs/ --format e4b --bank-size 64 --bank-start 100 --iso

# TAL-Sampler preset to E4B
python convert.py MyPreset.talsmpl --format e4b

# SFZ library to Kurzweil KRZ
python convert.py /sfz/pianos/ --format krz

# GIG file to E4B (limit to 16 instruments)
python convert.py Orchestra.gig --format e4b --max-presets 16 --hda

# Vintage resampling: EMU Emulator II sound
python convert.py /mpc/programs/ --format e4b --resample emulator2 --iso

# Vintage resampling: EMU Emax I sound, no bandpass coloring
python convert.py /sfz/ --format e4b --resample emax1 --no-bandpass

# Vintage resampling: use all CPU cores (default is cpu_count-1)
python convert.py /sfz/ --format e4b --resample emulator2 --jobs 8 --iso

# Thin a densely multisampled library to fit vintage sample memory:
# keep all velocity layers, but drop 30% of the per-key samples
python convert.py /sfz/pianos/ --format e4b --reduce-key-zones 30 --iso
```

---

## All Options

```
python convert.py <input> [options]

Positional:
  input               File or directory
                      (.e4b .xpm .pgm .set .img .talsmpl .sfz .sf2 .exs .gig)

Info mode:
  --info              Inspect input file(s) without converting
  --verbose           Show per-zone detail with --info

Output:
  --format FORMAT     e4b | krz | talsmpl  (default: e4b)
  --output-dir DIR    Output directory  (default: current directory)
                      (alias: --out-dir)
  --overwrite         Overwrite existing output files without prompting
                      (default: prompt before clobbering any existing file;
                       non-interactive shells refuse unless --overwrite)
  --bank-size MB      Maximum bank size  (default: 32; alias: --max-bank-size)
                      Accepts K/KB/M/MB/G/GB suffixes; a bare number = MB
                      (e.g. --max-bank-size 64MB).
  --max-preset-size SIZE  Cap each single preset/program (e.g. 8192K) so no one
                      preset fills a whole bank; over-cap presets are thinned to
                      fit.  (default: no per-preset cap)
  --auto-fit          When a single preset is too big for one bank (or over
                      --max-preset-size), auto-apply the least-lossy fitting
                      reduction instead of failing (for batch runs).
  --bank-name NAME    Base name for output banks  (default: EMU_BANK)
  --bank-start N      Number the bank files B.NNN-NAME… starting at N so they can
                      be copied straight onto an existing E4XT volume — no --iso
                      needed (e.g. 100 → B.100-NAME_01.E4B, B.101-NAME_02.E4B …)

ZuluSCSI images:
  --iso               Build CD image(s) for ZuluSCSI  (e4b → EMU3, krz → K2000 FAT16)
  --hda               Build SCSI hard disk image (.hda) for ZuluSCSI  (e4b + krz)
                      e4b → E4XT EMU-fs/FAT disk; krz → K2000 FAT16 disk
                      (HW-confirmed — loads from a ZuluSCSI HDx device)
  --hda-size MB       Hard disk image size in MB
                      e4b default: auto — smallest 128 MB step that fits; max 14336
                      krz default: content + ~50% headroom to save onto (FAT16 max ~2047)
  --hda-fs FS         E4B HDA filesystem: fat | emu  (default: fat; ignored for krz)
                      fat — FAT16 image in EOS's native layout (MBR partition
                            at LBA 63, 32 KB clusters), read by EOS 4.7+ (needs
                            the `mtools` package); banks B.NNN-NAME.E4B in the
                            root.  Use >=512 MB.
                      emu — native EMU-fs (EMU3), read by all EOS versions
                            (incl. <=4.62 which lacks FAT).  Proper disk-sized
                            image (honours --hda-size) with free space; cluster
                            size scales with the disk (512 MB..~16 GB).
                      Both filesystems are E4XT hardware-confirmed.

Floppy image (KRZ only):
  --floppy [KB]       Write each bank to a DOS FAT12 floppy image (.img) for a
                      Gotek / FlashFloppy on the K2000R  (default: 1440 = 1.44 MB)

Add to an existing image (instead of building a new one):
  --add-to IMAGE      Append the converted bank(s) to an existing .hda (FAT or
                      EMU-fs, auto-detected).  Never overwrites existing banks.
  --folder NAME       Target folder on the image, created if absent
                      (default: root / Default Folder; EMU-fs: <=100 banks/folder).
  --on-duplicate WHAT prompt (default) | add-new (next free number/slot) |
                      skip | overwrite — how to handle a name already present.

Samples:
  --wav-dir DIR       Extra directory for WAV sample lookup
  --max-presets N     Maximum presets from SF2/GIG  (default: 64)
  --max-sample-rate HZ  Clean-downsample any sample above HZ to HZ
                      (defaults to 24000 Hz for --format krz — up-pitch headroom
                       + smaller banks; pass 0 to disable; no default for e4b)
  --from-samples      Treat the input directory as a folder of WAVs (root note in
                      filename) → one auto-built multisample preset
                      (also auto-detected for a WAV-only dir)
  --middle-c {auto,C3,C4,C5}  Octave naming for filename root notes: which C =
                      MIDI 60  (default: auto)

Vintage resampling:
  --resample PROFILE  emulator2  (8-bit / 27.5 kHz, EMU Emulator II)
                      emax1      (12-bit / 27.5 kHz, EMU Emax I)
  --no-bandpass       Disable output bandpass coloring
  --resample-keep-gain Keep the gain-staged "hot" level instead of restoring
                      each sample's original level afterwards (default: restore)
  --jobs N            Parallel resampling workers  (default: cpu_count-1)

Modulation:
  --lfo-sync-bpm BPM  Reference tempo for reproducing tempo-synced MPC LFOs as a
                      fixed rate  (default: 120; see docs/lfo_sync_rates.md)

Sample-count reduction (fit modern libraries into vintage memory limits):
  --reduce-key-zones PCT        Remove PCT% of per-voice key-zone samples
  --reduce-velocity-layers PCT  Remove PCT% of per-preset velocity-layer voices
                      Both default to 0 (off) and are independent — e.g. set
                      only --reduce-key-zones to keep every velocity layer
                      and thin only the keyboard split. Survivors' key/
                      velocity ranges are stretched to fill the resulting
                      gaps, split evenly between neighbors.
```

---

## --info Mode

Inspects any supported input file and prints a structured summary
without writing any output files.

```
$ python convert.py DrumKit.sfz --info

mpc2emu --info  (1 file(s))

────────────────────────────────────────────────────────────
  DrumKit.sfz
────────────────────────────────────────────────────────────
  Format:    SFZ v1/v2 (text)
  Bank name: DrumKit
  Presets:   1
  Samples:   12
  Zones:     24
  PCM data:  8.34 MB
  Est. E4B:  8.36 MB

  Presets:
    [00] DrumKit              1 layer(s)  24 zone(s)  prog 0

  Samples:
    [00] Kick_A               44100 Hz  16-bit  mono  320 ms  …
    …

  ⚠  1 warning(s):
     • Sample 'HiHat_Open': loop enabled but loop_end=0
```

Use `--verbose` to additionally show per-voice envelope parameters
(amp ADSR, filter cutoff/Q, and chorus amount when set) and individual
zone key/velocity ranges.

---

## ZuluSCSI Workflows

### CD image — E4XT (EMU3 filesystem)

When `--format e4b`, `--iso` produces an **EMU3 filesystem** image —
the same format as original E-mu sample CD-ROMs.  ZuluSCSI presents this
as a CD-ROM drive; the E4XT reads it directly and shows a "Default Folder"
containing all banks.  It is **not** standard ISO 9660.

> See [`docs/EMU3_ISO_FORMAT.md`](docs/EMU3_ISO_FORMAT.md) for the complete
> reverse-engineered reference of this filesystem (superblock, FAT,
> directory layout, cluster allocation, and the hardware quirks — like the
> `blks`-must-be-a-ceiling trap — that took real E4XT testing to pin down),
> as well as the K2000's standard ISO 9660 image format below.

```bash
python convert.py /mpc/programs/ --format e4b --bank-size 64 --bank-start 100 --iso
```

1. Copy the generated `.iso` to the ZuluSCSI SD card
2. Rename to `CD1.iso` (further discs: `CD2.iso`, `CD3.iso` …)
3. Power on E4XT → **Load → CD-ROM** → select bank

Multiple `.iso` files on the same SD card appear as separate CD drives
(CD1, CD2, …); the E4XT can switch between them.

### CD image — K2000 (FAT16 disk-image)

When `--format krz`, `--iso` produces a **FAT16 disk-image copy** (BPB at sector
0, no partition table, OEM `KCDM1.2`) — the universally-compatible K2000/K2500
disk form that **every K2000 OS reads**. It is *not* ISO 9660: real ISO 9660
needs K2000 OS **v3.87+** / K2500 2.96+ (`build_iso_9660` can produce that if you
need it). ZuluSCSI serves the `.iso` as a CD-ROM.

> **Full byte-level KRZ format reference:** see
> [`docs/KRZ_FORMAT.md`](docs/KRZ_FORMAT.md) — the bank/object model
> (Sample / Keymap / Program), the VAST program encoding (filter, envelopes,
> LFO), and the FAT16 CD/hard-disk media layout, reverse-engineered from
> hardware and the KurzFiler source.

```bash
python convert.py /sfz/pianos/ --format krz --iso
```

1. Copy the generated `.iso` to the ZuluSCSI SD card
2. Rename to `CD1.iso`
3. Power on K2000 → **Load → CD-ROM** → select bank

> The very same FAT16 image also works as a **hard disk** — see the K2000 HD
> section below.

### SCSI Hard Disk (.hda) — E4XT

```bash
python convert.py /mpc/programs/ --format e4b --bank-size 64 --hda --hda-size 200
```

1. Copy `output/EMU_BANK.hda` to the ZuluSCSI SD card
2. Rename to `HD10_512.hda` (SCSI ID 0, 512-byte sectors)
3. Power on E4XT → **Load → Hard Disk** → select bank

The hard disk image loads faster than CD and supports up to 14 GB
(EIV OS limit).

### SCSI Hard Disk (.hda) — K2000

When `--format krz`, `--hda` builds a **K2000 FAT16 hard-disk image** — the same
disk-image copy as the CD form, sized with free space so the K2000 can also save
onto it. **Hardware-confirmed on a K2000R**: banks load and play straight from a
ZuluSCSI `HDx` device.

```bash
python convert.py /sfz/pianos/ --format krz --hda --hda-size 1024
```

1. Copy the generated `.hda` to the ZuluSCSI SD card
2. Rename to `HD1-<name>.hda` — pick any **free SCSI ID** (`HD1`, `HD3`, …);
   ZuluSCSI reads it as a hard disk with the default 512-byte blocks
3. Power on K2000 → **Load → Disk** → select bank

`--hda-size` sets the volume size in MB (default: content + ~50% headroom;
FAT16 tops out near ~2047 MB).

### Adding files to an existing .hda with emu3fs (Linux)

```bash
# Mount the image
sudo losetup -b 512 /dev/loop0 output/EMU_BANK.hda
mkdir -p /mnt/emu4
sudo mount -t emu4 /dev/loop0 /mnt/emu4

# Copy files
sudo cp NewBank.E4B /mnt/emu4/

# Unmount
sudo umount /mnt/emu4
sudo losetup -d /dev/loop0
```

emu3fs: <https://github.com/dagargo/emu3fs>

---

## E4B Voice Parameters

Voice parameters are mapped from the source format to EOS 4.x through
hardware reverse-engineering (JL AnalogBank, B.005-FltEnvTest, FLTTYPES,
and the AMPENV_SETME / AMP_DECAY_CAL amp-envelope banks, compared against
confirmed E4XT hardware byte values).

> **Full byte-level format reference:** see
> [`docs/E4B_FORMAT.md`](docs/E4B_FORMAT.md) for the complete
> Bank/Preset/Voice/Zone/Sample structure, byte-offset tables, and the
> non-obvious encoding conventions (and bugs) discovered along the way —
> written so other implementers can benefit from this reverse-engineering
> work.

### Filter

All 8 MPC filter types (MPC 3.7 manual appendix) are mapped to the
nearest available E4XT equivalent:

| MPC type | Name | E4XT type |
|---|---|---|
| 0 | Off | bypass (4PLP wide open) |
| 1 | Low 1 — 1-pole LP | 2-Pole LP |
| 2 | Low 2 — 2-pole LP | 2-Pole LP |
| 3 | Low 4 — 4-pole LP | 4-Pole LP |
| 4 | Low 6 — 6-pole LP | 6-Pole LP |
| 5 | Low 8 — 8-pole LP | 6-Pole LP (closest) |
| 6–10 | High 1–8 | 2nd / 4th Order HP |
| 11–14 | Band 2–8 | 2nd / 4th Order BP |
| 15–18 | BS 2P–8P (band-stop / notch) | Contrary BP |
| 19–22 | BB 2P–8P (band-boost) | 4th Order BP (nearest resonant) |
| 23–25 | Model 1–3 (analog emulations) | 4-Pole LP |
| 26–28 | Vocal 1–3 (formant) | 4-Pole LP |
| 29 | MPC3000 LPF (12 dB/oct) | 2-Pole LP |

Filter cutoff (0.0–1.0 linear → exponential Hz scale, 0≈57 Hz / 255=20 kHz),
resonance (0.0–1.0 direct), and the 6-stage filter envelope
(Attack1/2 · Decay1/2 · Release1/2 with rate + level per stage) are all
mapped from the source preset.

### Amplitude envelope

The full 6-stage amplitude envelope (`PZT[0:12]`, same structure as the filter
envelope) is mapped from the source preset's attack / decay / sustain / release.
The amp **decay-rate** byte (`PZT[4]`) and the **rate↔time** conversion were
reverse-engineered on the E4XT: the decay byte was isolated with a single-byte
sweep, and the rate curve calibrated from six measured decay-to-silence times to
`time_s = 0.0310 · e^(0.0581 · rate)` (rate 0 = instant, 127 ≈ 47 s). See
[`docs/re_procedures/amp_envelope.md`](docs/re_procedures/amp_envelope.md).

### Chorus

Per-voice **Chorus Amount** (`vpar[42]`) is read and written: the E4XT's
0–100 % control maps linearly to a `0–127` byte (`round(pct/100 × 127)`),
hardware-confirmed against commercial banks and a 25/50/75/100 % save sweep.
(Chorus *stereo width* is a separate, not-yet-decoded byte.)

### Loops

WAV SMPL chunks are read for all input files. Forward loops use E4XT
confirmed encoding (`opts=0x0031`). EOS has no ping-pong (alternating) loop
mode, so ping-pong loops are **rendered into the PCM** as forward loops — a
reversed copy of the loop interior is spliced in so a forward loop reproduces
the bounce (the same technique EOS uses for imported EIII loops).

Samples marked **SMP** in the MPC Program Editor (RootNote=0, no pitch
tracking) are placed in a single zone spanning the full key range with a
neutral root note (60), preventing extreme pitch transposition.

---

## KRZ Program Parameters

KRZ program parameters are mapped onto the Kurzweil K2000 VAST program model
by cloning the ROM **#199 "Default Program"** template and patching the
per-voice values (filter, envelopes, LFO, loop points) into a single keymap +
single layer per voice. Much of this mapping is hardware-verified on a
**K2000R** — filter type, cutoff (in Hz) and resonance were confirmed by ear,
and the LFO shapes were decoded from a live SysEx probe.

> **Full byte-level format reference:** see
> [`docs/KRZ_FORMAT.md`](docs/KRZ_FORMAT.md) for the complete
> object/program/keymap/sample structure, byte-offset tables, and the
> non-obvious encoding conventions discovered along the way (filter algorithm
> bytes, envelope segments, loop-flag rule) — written so other implementers
> can benefit from this reverse-engineering work.

### Filter

Each MPC/XPM filter type is mapped to the nearest K2000 VAST filter algorithm.
Slope is matched to the source wherever the K2000 can (1-, 2- or 4-pole), so
the source cutoff frequency transfers ~1:1 (it is the −3 dB corner regardless
of slope):

| MPC/XPM type | Name | K2000 filter (algorithm) |
|---|---|---|
| 0 | Off | None / bypass (byte 62) |
| 1 | Low1 (1-pole, 6 dB) | 1-pole LOPASS (Alg 16) |
| 2, 29 | Low2 / MPC3000 LPF (2-pole, 12 dB) | 2-pole LOWPASS (Alg 5) |
| 3–5 | Low4/6/8 (4/6/8-pole LP) | 4POLE LOPASS W/SEP (Alg 1, 24 dB) |
| 6–10 | High 1–8 (HP) | 4POLE HIPASS W/SEP (Alg 1) |
| 11 | Band2 (2-pole BP) | 2-pole BANDPASS (Alg 5) |
| 12–14 | Band4–8 (BP) | TWIN PEAKS BANDPASS (Alg 1, 4-pole) |
| 15–18 | BS 2P–8P (band-stop / notch) | DOUBLE NOTCH W/SEP (Alg 1) |
| 19–22 | BB 2P–8P (band-boost) | PARA MID parametric boost (Alg 2) |
| 23–25 | Model 1–3 | 4POLE LOPASS (Alg 1) |
| 26–28 | Vocal 1–3 (formant) | 4POLE LOPASS (Alg 1) |

Band-boost (BB) maps to the Alg-2 **PARA MID** parametric boost — it keeps the
body of the signal and lifts a band around the cutoff, unlike a bandpass which
would wrongly remove the out-of-band signal (hardware reverse-engineered
2026-06-25). Filter **TYPE** *and* cutoff-Hz mapping were hardware-verified by
ear on a K2000R (4-pole HP ≈ 330 Hz, 2-pole BP ≈ 466 Hz, double-notch ≈ 22 Hz
demos). Cutoff is encoded as signed semitones and resonance as
`round(dB × 2)`, both sonically confirmed.

Lossiness (acceptable): the K2000 has one slope per filter family, so
multi-pole variants (6/8-pole) collapse onto the nearest reverse-engineered
slope; the 2-pole HP and 2-pole notch bytes are not yet RE'd (those sources use
the 4-pole path); Vocal formant filters fall back to lowpass.

### Envelopes

The amplitude and filter ADSR envelopes (attack / decay / sustain / release)
are read from the source preset and patched onto the #199 template's segment
structure (the amp envelope is forced to User mode; the filter envelope ENV2 is
routed to filter frequency only when its depth is positive). The filter-env
**depth** and the LFO→pitch **depth** are approximate 2-point linear
calibrations rather than fully reverse-engineered curves.

### LFO

LFO1 (vibrato) is mapped: rate plus all **26 LFO shapes**, which were decoded
from a live K2000R SysEx probe (0 = Sine … 4 = Triangle … 6 = Rising Sawtooth …
8 = Falling … 20 = 8 Step). Routed to pitch via the CAL control-source bytes.

Not yet mapped (honest gaps): **LFO2**, **LFO → filter** (filter wobble),
**LFO → amp** (tremolo), and LFO **delay / fade-in / tempo-sync**.

### Loops

WAV SMPL chunks are read for all input files. The loop flag follows the
hardware-confirmed K2000 rule: the sample header's `0x80` bit is **clear** to
loop (`0x70`) and **set** to play one-shot (`0xF0`); a looped sample's
`sampleEnd` field is set to the loop end (not the PCM end) so the K2000 does
not loop over the post-loop decay tail. The K2000 has no ping-pong loop mode,
so **ping-pong loops are baked into the PCM** (a reversed copy of the loop
interior is spliced in). Output is **mono only** — stereo sources are
downmixed.

---

## Vintage Resampler

Simulates the signal chain of two classic E-mu samplers:

| Profile | Device | Bit depth | Sample rate | Character |
|---|---|---|---|---|
| `emulator2` | EMU Emulator II (1984) | 8-bit | 27,500 Hz | Hard truncation noise, RC anti-alias, slight DC offset |
| `emax1` | EMU Emax I (1986) | 12-bit | 27,500 Hz | TPDF dither, cleaner noise floor |

Signal chain (6 stages):
1. Anti-alias filter (1-pole RC for E2, 2-pole Butterworth for Emax)
2. Decimation to target sample rate (naive — intentional aliasing)
3. **Gain-staging**: each sample is boosted toward full scale before
   quantizing — exactly what a sound designer of the era would have done
   when sampling, to get the most out of the device's limited bit depth.
   Without this, source material that was authored well below full scale
   (common with modern WAV/SF2/SFZ libraries) loses far more resolution
   to the quantizer than the profile is meant to model, and ends up
   sounding noisier than the real hardware ever would.
4. Requantisation + optional TPDF dither (now operating on a properly
   gain-staged signal, so the output SNR matches the profile spec)
5. Bandpass coloring (output filter model, disable with `--no-bandpass`)
6. Level restore: by default, each sample is scaled back down to its
   original peak level afterwards, so it keeps the loudness the patch was
   authored at. Pass `--resample-keep-gain` to keep the louder,
   gain-staged level instead.

Samples are processed in parallel using `ProcessPoolExecutor`.
The default worker count is `cpu_count − 1`; override with `--jobs N`.

---

## Bank Splitter

Automatically distributes presets across multiple output banks when
the size limit is reached:

- **First-Fit Decreasing** algorithm — maximises fill rate
- Presets always stay **complete** in one bank (never split)
- Samples are **deduplicated** within each bank; names longer than 16
  characters are truncated with a numeric suffix to ensure uniqueness
- Warning issued when a single preset exceeds the limit

---

## Fitting oversized presets

A preset is never split across banks, so a single preset too big for one bank
(or over `--max-preset-size`) must be **thinned** to fit. In an interactive
shell mpc2emu prints sized suggestions — drop velocity layers → thin key zones →
downsample, least-lossy first — and applies your choice. With `--auto-fit` it
does this automatically. A batch run without `--auto-fit` prints the suggestions
and exits non-zero, so an oversized / unloadable bank is never silently written.
This works for both E4B (128 MB E4XT) and KRZ (64 MB K2000) output.

Per-bank hardware limits: max **1000 samples** and **1000 presets** per bank;
max bank size **128 MB** (E4XT) / **64 MB** (K2000).

---

## Project Structure

```
mpc2emu/
├── LICENSE
├── DISCLAIMER.md
├── DISCLAIMER_de.md
├── README.md
├── README_de.md
├── convert.py                  # CLI entry point
├── info_cmd.py                 # --info mode implementation
├── test_pipeline.py            # Smoke tests
├── models/
│   └── common.py               # Internal data models (Bank / Preset / Sample)
├── parsers/
│   ├── registry.py             # Format auto-detection / parser dispatch
│   ├── xpm_parser.py           # Akai MPC XPM (filter, loops, SMP velocity split)
│   ├── pgm_parser.py           # Akai MPC500/1000/2500 + 2000/XL + MPC60 drum program
│   ├── mpc60_parser.py         # Akai MPC60 SET / FAT12 floppy image (12-bit RAM set)
│   ├── talsmpl_parser.py       # TAL-Sampler (parser + writer; 13-mode filter map)
│   ├── tal_template.py         # TAL-Sampler preset template for the writer
│   ├── sampledir_parser.py     # WAV sample folder → auto-built multisample preset
│   ├── sfz_parser.py           # SFZ v1/v2
│   ├── sf2_parser.py           # SoundFont 2
│   ├── exs24_parser.py         # Logic EXS24 (LE classic + v1.1; stereo de-dup)
│   ├── gig_parser.py           # GigaSampler / GigaStudio
│   └── e4b_parser.py           # EMU E4B import (inverse of e4b_writer)
├── writers/
│   ├── e4b_writer.py           # EMU E4B (FORM size + EMSt; filter, loops, zones)
│   ├── krz_writer.py           # Kurzweil KRZ
│   ├── iso_builder.py          # EMU3 filesystem image for ZuluSCSI CD emulation
│   ├── hda_builder.py          # SCSI hard disk image (.hda) for ZuluSCSI
│   ├── fat12.py                # FAT12 floppy image (K2000R Gotek / FlashFloppy)
│   ├── fat16.py                # FAT16 image in EOS's native layout (--hda-fs fat)
│   ├── fat32.py                # FAT32 image builder
│   └── bank_splitter.py        # First-Fit-Decreasing bank splitting
├── processors/
│   ├── resampler.py             # Vintage resampler (EMU E2 / Emax I)
│   ├── zone_reducer.py          # Key-zone / velocity-layer thinning for vintage memory limits
│   └── loop_renderer.py         # Ping-pong → forward loop (bakes the bounce into PCM)
└── tests/
    └── re_banks/                # Hardware-RE helpers: test-bank generators
        ├── gen_amp_envelope_test.py   #   amp envelope (decay byte / rate calibration)
        ├── gen_filter_envelope_test.py #  filter envelope Decay-1 rate calibration
        ├── gen_xpm_envelope_test.py   #   MPC (.xpm) envelope value→time curve (MPC One)
        ├── analyze_envelope_recording.py # measure per-note decay times from a recording (numpy)
        ├── gen_filter_types_test.py   #   vpar[58] filter-type sweep
        ├── gen_zone_entry_test.py     #   secondary-zone-entry field probes
        └── inspect_vpar.py            #   dump any vpar[N] across banks (found vpar[42]=chorus)
```

---

## Known Limitations

| Feature | Status |
|---|---|
| Native stereo samples in E4B | ❌ downmixed to mono |
| GIG Giga-codec (compressed) | ❌ not supported |
| TAL `.talwav` (encrypted) | ❌ not readable |
| EXS24 PPC big-endian | ❌ not supported — same on-disk magic as LE, can't be distinguished |
| EXS24 v1.1 multi-velocity layers | ⚠️ first layer only — positional zone mapping |
| EXS24 v1.1 L/R stereo | ✅ de-duplicated — `_R` group dropped when an `_L` partner exists |
| E4B filter type / cutoff / Q | ✅ mapped from MPC XPM (MPC 3.7 manual), plus EXS24 (FILTER1) and GIG (VCF) |
| E4B filter envelope from source | ✅ XPM, SFZ (`fileg_*`), SF2 (mod-env→cutoff), GIG (EG2/VCF) and EXS24 (ENV2) |
| E4B forward loops | ✅ SMPL chunk read; `opts=0x0031` hardware-confirmed |
| E4B ping-pong loops | ✅ EOS has no ping-pong mode — rendered into PCM as a forward loop (bounce baked in) |
| E4B multi-loop samples | ❌ only the first SMPL loop entry is used |
| E4B non-transpose (SMP) voice | ✅ one non-transpose voice per velocity range (root=60, full-range zones) |
| E4B FORM size / EMSt chunk | ✅ EMU convention (`filesize−12`) + trailing `EMSt` — loads in e-xplorer & from CD |
| E4B VCA (amp) envelope ADSR from source | ✅ full 6-stage amp envelope (`PZT[0:12]`); decay byte `PZT[4]` + rate↔time curve hardware-calibrated |
| E4B chorus amount | ✅ per-voice `vpar[42]` read/written (0–100 % → 0–127, hardware-confirmed) |
| E4B chorus stereo width | ❌ separate byte, not yet decoded |
| EMU3 ISO loading from ZuluSCSI CD | ✅ `blks` ceiling-division fix — end-of-file error resolved |
| KRZ filter type / cutoff / resonance | ✅ mapped from MPC XPM; filter-type + cutoff-Hz HW-verified on a K2000R (incl. band-boost → PARA MID) |
| KRZ amp + filter envelope from source | ✅ mapped from source ADSR (filter-env / LFO depth calibrations approximate) |
| KRZ LFO1 vibrato (rate + 26 shapes) | ✅ rate + all 26 shapes (live SysEx probe); LFO2 / filter-wobble / tremolo ❌ not yet |
| KRZ ping-pong loops | ✅ K2000 has no ping-pong mode — baked into PCM (bounce spliced in) |
| KRZ multi-pole filter slopes (6/8-pole, 2-pole HP/notch) | ⚠️ collapse to nearest RE'd slope |
| KRZ SCSI CD / hard disk (FAT16) / Gotek floppy | ✅ HW-confirmed (CD and HDx hard disk); Gotek FAT12 floppy ✅ |
| LFO rate / shape / routing | ✅ LFO rate/shape + pitch/filter routing mapped for E4B and KRZ, plus tempo-synced MPC LFOs via `--lfo-sync-bpm`; some depth calibrations approximate |
| Binary MPC `.pgm` | ✅ MPC500/1000/2500, MPC2000/2000XL, MPC60 supported (auto-detected) |
| MPC3000 `.pgm` | ❌ not supported — magic collides with MPC60, needs a body-level discriminator |
| HDA > 16 dir entries | ⚠️ single 512-byte dir block — warns and keeps first 16 (excess dropped, not silently) |

---

## License and Third-Party Sources

This project is released under the **GNU General Public License
v2.0 or later (GPL-2.0-or-later)** — see [`LICENSE`](LICENSE).

No third-party source code was copied. All parsers and writers are
independent Python reimplementations informed by format
specifications and open-source reference projects:

| File | Reference | License | Author |
|---|---|---|---|
| `gig_parser.py` | [libgig](https://www.linuxsampler.org/libgig/) — DLS/Giga structure; `3ewa` articulation layout + `GIG_EXP_DECODE` EG1/EG2/VCF decode (`gig.cpp` `DimensionRegion`), validated byte-exact against `gigdump` | GPL-2.0-or-later | Christian Schoenebeck |
| `hda_builder.py` | [emu3fs](https://github.com/dagargo/emu3fs) | GPL-2.0-or-later | David García Goñi |
| `e4b_writer.py`, `iso_builder.py` | [emu3bm](https://github.com/dagargo/emu3bm) — `struct emu3_sample` (E3S1 sample header fields) and `emu3_set_fattrs()` (ceiling-division `blks` formula for EMU3 filesystem) | GPL-3.0-or-later | David García Goñi |
| `krz_writer.py` | [KurzFiler](https://kurzfiler.sourceforge.io/) | GPL-2.0 | Marc Halbrügge |
| `exs24_parser.py` | [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) — EXS24 chunk layout; `TYPE_PARAMS` block, `EXS24Parameters` IDs and `EXS24Detector` filter/envelope conversions (FILTER1 + ENV2) | LGPL-3.0 | Jürgen Moßgraber |
| `talsmpl_parser.py` | [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) | LGPL-3.0 | Jürgen Moßgraber |
| `pgm_parser.py` | [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) — `format/akai/mpc1000`, `format/akai/mpc2000` and `format/akai/mpc60`; MPC2000/XL verified against an Akai factory CD, MPC60 `.PGM`/`.SND` container RE'd from a real kit | LGPL-3.0 | Jürgen Moßgraber |
| `mpc60_parser.py` | [ConvertWithMoss](https://github.com/git-moss/ConvertWithMoss) — `format/akai/mpc60` (MPC60 SET layout + 12-bit unpack); verified against the *Akai MPC60 to WAV* reference decoder | LGPL-3.0 | Jürgen Moßgraber |
| `e4b_writer.py` | Reverse-engineered from E4XT hardware-saved banks (JL AnalogBank, FltEnvTest, FLTTYPES series, AMPENV_SETME + AMP_DECAY_CAL amp-envelope/decay banks, and the Chorus-Amount `vpar[42]` reads/sweep), commercial EOS CD-ROMs (E-MU Formula 4000 Series Vol. 5, Producer Series 01, Syntec WOS V4) plus the ProRec / Rob Papen / Kirk Hunter bank corpus used for parameter mining, `struct emu3_sample` from [emu3bm](https://github.com/dagargo/emu3bm) (E3S1 field layout), and [Phil's E4 format notes](http://www.philizound.co.uk/freebies/software/emu-reorder/emu-reorder.html) | — | Original code |
| `iso_builder.py` | EMU3 filesystem structure informed by [emu3fs](https://github.com/dagargo/emu3fs) (GPL-2.0-or-later), verified against reference images; `blks` ceiling formula from `emu3_set_fattrs()` in [emu3bm](https://github.com/dagargo/emu3bm) | GPL-2.0-or-later | David García Goñi |

---

*E-mu, Emulator, EOS are trademarks of Creative Technology Ltd. ·
Kurzweil is a trademark of Young Chang Co. Ltd. ·
Akai MPC is a trademark of inMusic Brands Inc. ·
GigaStudio/GigaSampler are trademarks of TEAC Corporation. ·
Logic, EXS24, MainStage are trademarks of Apple Inc. ·
TAL-Sampler is a trademark of TAL Software GmbH. ·
SoundFont is a trademark of Creative Technology Ltd.*
