<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
Jan Lentfer -- https://github.com/lentferj/mpc2emu
-->

# Ask the S3000XL what it makes of an S1000 program

**No S1000 required, and no audio required.** Jan's idea, 2026-08-20.

If the S3000 reads `.P1` natively, then its own import routine *is* a mapping
from S1000 parameters to S3000 ones. Load a `.P1` with known values, read the
resident program back over SysEx, and the machine has told us the mapping
directly.

## What it answers, and what it does not

**Answers:** what AKAI's own import makes of every S1000 parameter. For a
converter that is the defensible basis — reproduce the manufacturer's
semantics rather than invent a mapping.

**Does not answer:** what an S1000 *sounded* like. s3ked's §139 measured two
poles on this S3000XL against the S1000's specified three, so if the import is
identity, the same number means the same setting and a different sound. That
question still needs an S1000; this one does not, and it is the one that
unblocks `.P1` conversion today.

## The disc

`tests/re_banks/gen_akai_s1000import_disc.py` → `~/temp/HD_s1000import.img`,
one volume, 17 programs, all genuine S1000 `.P1` (type `0x70`) against a
40 Hz sawtooth `.S1` (`0x73`).

**Programs are patched copies of a real factory `.P1`**, not generated: 300
bytes, two 150-byte blocks, `FILFRQ` at keygroup+`0x07`. Our writer has no
S1000 output path, and inventing one in order to test S1000 handling would put
the untested thing inside the experiment. Structural fields are left alone — a
program that will not load measures nothing.

| PRGNUM | programs | what they carry |
|---|---|---|
| 40–53 | `S1F 30` … `S1F 99` | a FILFRQ ladder, 30 to 99 |
| 60–62 | `S1P 20`, `S1P 50`, `S1P 80` | every semantic field at 20, 50, 80 |

The ladder steps by 5 so an out-of-order load shows up as a **non-monotonic
readback** rather than having to be trusted, and it brackets both the fitted
range (40–84) and the band the factory discs actually use — our corpus found
685 of 1555 S3000 keygroups in 85–98 and only **two** inside 40–84.

The probes set 20 fields each: both envelopes, `FILFRQ`, LFO speed, program
loudness, octave shift, polyphony, the modwheel/bendwheel depths and the three
soft-pedal depths. **Three values, because one point cannot tell identity from
a scale or an offset, and two cannot tell a scale from an offset.** Three can,
for every field at once, from one load.

## Procedure

1. Load the volume (CLR first).
2. Read every field of PRGNUM 40–53 and 60–62 back over SysEx. **No notes need
   to be played.**
3. Compare against the table the generator prints.

Identity across all three probes means AKAI's import is a pass-through and our
S3000 semantics apply to `.P1` sources. Any field that is not identity has just
stated its own mapping.

## The free second result

The S3000 keygroup is 192 bytes against the S1000's 150, so the extension
fields cannot be carried by the source at all and the machine must default
them. **Read keygroup 151, 152 and 153** — the velocity, LFO2 and
envelope-to-filter depths of §AKAIVFR — and whatever is there is what AKAI's
import puts in fields the file could not supply.

## If the audio version is ever wanted

The sample is a 40 Hz sawtooth precisely so this disc also supports it: a
harmonic comb every 40 Hz samples the filter's transfer function densely enough
to fit both a corner and a slope. The `HD8_rateread.img` sines left that
discriminator unavailable, which s3ked pointed out after the fact.
