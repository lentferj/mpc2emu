<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# AKAI S3000 series — disk and file formats

> **DO NOT PUSH THE `akai-s3000xl` BRANCH UNTIL HARDWARE CONFIRMS IT.**
> (Jan, 2026-08-05.) Everything here is cross-verified against `akaiutil` and
> nothing here is verified against an S3000XL. That distinction has already
> bitten once: the sample header length taken from the primary spec was wrong
> by two bytes, which offsets every PCM frame, and only an independent
> implementation caught it. Two references agreeing is not hardware agreeing.
> See "What this does NOT establish" at the end, and the AKAI entries in
> `TODO.md`, for the specific checks to run first.


Reference for `parsers/akai_s3000_parser.py`, `parsers/akai_image_parser.py`
and `writers/akai_s3000_{writer,image}.py`. Covers the S3000XL and its
siblings (S1000/S1100/S2800/S3000/S3200/CD3000/S2000/S3200XL), whose disk and
program formats are the same family — the S3000 blocks are the S1000 ones plus
42 bytes of padding. **Nothing in a file says which generation wrote it**; that
comes from the directory entry's file type. See "Block lengths and the block
id".

## Sources

None of this is guesswork on our part, but none of it is vendor documentation
either — Akai never published the disk format.

1. **"AKAI S3000 Series Disk and File Formats"**, Hiroyuki Ohsaki, v1.0,
   2019-07-18 — `lsnl.jp/~ohsaki/software/akaitools/S3000-format.html`.
   Derived by binary analysis in 1993 and the basis of `akaitools`. This is the
   primary reference for every offset below.
2. **`akaiutil`** (GPL-2, Klaus Michael Indlekofer) — an independent
   implementation, used here only to *cross-check* constants. Local copy in
   `~/temp/akai_s3000xl_docs/src/`.
3. **AKAI S2800/S3000/S3200 and S2000/S3000XL/S3200XL MIDI System Exclusive
   Format** — `lakai.sourceforge.net/docs/`. The SysEx parameter lists mirror
   the file layout and were used to sanity-check field meanings.
4. **S3000XL Owner's Manual** (archive.org `S3000XLOM`) for parameter ranges
   and what the front panel calls each value.

**No third-party source code was copied.** Where (1) and (2) were compared they
agree; disagreements are flagged inline below.

## Repeated sample names across a corpus, and how to count them

Measured over 21 library disc images, cross-checked against VinSamLib's
independent reader. Both enumerate **36 645 sample occurrences** with the same
generation split — **25 407 S1000, 11 238 S3000** — to the unit, which is the
strongest agreement the two readers have produced.

**Counting DISTINCT names needs a definition, and the two obvious ones differ
by exactly 57:**

| definition | distinct names |
|---|---|
| extension stripped (`808 COWBELL`) | 34 234 |
| full filename (`808 COWBELL.S1`, `.S3` separately) | 34 291 |

The 57 are names present in **both sampler generations** — the same sound
shipped once for each machine, `808 COWBELL`, `808 RIM`, `AGOGO 1`,
`BASSFLUTE C3`. Neither count is wrong; they answer different questions.

**Names that repeat carrying different bytes** (the population that matters to
any writer assembling from several sources):

| | |
|---|---|
| repeats with DIFFERENT audio | 436 |
| repeats with IDENTICAL audio, DIFFERENT HEADER | 1499 |

The second class is the larger, and its cause is visible in the material:
drum-machine libraries file the same hit under the same name in kit after kit,
with different tuning or loop settings over identical audio. **A writer keying
sample identity on the PCM alone therefore mis-merges the LARGER of the two
classes** — see `akai_s3000_writer.sample_identity()`, which hashes every field
the header carries for exactly this reason.

**A volume MAY hold `NAME.S1` and `NAME.S3`** — two directory entries, two type
bytes, the same 12-character name field — but **no volume in the corpus does**.
VinSamLib checked all 1843 volumes across the 21 images, uncapped: zero. The 57
cross-generation names are always one `.S1` volume and one `.S3` volume, the
same library shipped twice and never mixed on the media.

So the pair cannot arise from reading a disc. It can only arise from
ASSEMBLING one, which puts it outside this project entirely — we emit S3000
samples only and cannot produce it. A librarian staging an S1000 program beside
an S3000 program in one volume can.

**Still unmeasured for whoever can produce it:** whether the sampler's
replace-on-load keys on the name alone or on name-and-type. The asymmetry
decides the safe default without needing the answer — renaming when it keys on
name+type costs one object and one copy of the audio, while not renaming when
it keys on name alone silently loses a sound the disc offered. Pay the object.

## Sample header bytes 141-191, measured over 36 645 real headers

Our own table stops at offset 141. What lies past it was measured 2026-08-14
across 21 commercial library disc images (1843 volumes, 49 984 files), after
s3ked asked three questions from a six-sample reading on one disc.

**The two sampler generations behave completely differently, and that is the
answer to all three.**

| bytes 182-187 | S3000 samples (type `0xF3`), n = 11 238 | S1000 samples (type `0x73`), n = 25 407 |
|---|---|---|
| all-zero | 91.3 % | 13.2 % |
| mixed | 8.4 % | 85.9 % |
| all-ones | 0.3 % | 0.9 % |

**1. The "all-zero or all-ones" run is real for S3000 and false for S1000.**
It holds in 91.6 % of S3000 headers, so a six-sample reading of one S3000 disc
was representative of that generation. It is not a property of the format.

Note what the remaining 8.4 % does to the inference that drew attention to it:
"a six-byte run that is only ever all-zero or all-ones is sign extension, not
data" — 940 S3000 headers are neither. With six samples the odds of seeing
none of them were about three in five. The pattern is real and dominant; *only
ever* is not, and sign extension does not follow from it.

**2. `17 412` at bytes 188-191 is not a default.** Zero occurrences in 36 645
headers across 21 discs. The dominant value there is 0 (10 262 of 11 238 S3000
headers) and the remaining non-zero values scatter with none repeating more
than ~350 times. Whatever that constant was on the disc it came from, it is a
property of that library rather than of the format.

**3. Position in a multisample does not predict the value.** Measured by taking
each program's keygroup zones, resolving them to distinct samples, ordering by
key, and comparing how often a non-zero value lands on an end against the
`2/n` chance baseline:

| | |
|---|---|
| multisamples (≥3 distinct members, ≥1 non-zero) | 304 |
| non-zero members | 1730 |
| at an extreme, observed | 427 (24.7 %) |
| at an extreme, expected by chance | 424 (24.5 %) |
| ratio | **1.01×** |

Nothing. The observation that prompted it — two differing members of a
six-sample multisample, both outermost — is what chance produces at that size:
two non-zero out of six both landing on the ends happens about one time in
fifteen.

**A counting trap worth recording, because the first run here fell into it.**
Counting each sample once per KEYGROUP REFERENCE rather than once per
multisample gave outermost 9.13 % non-zero against inner 6.32 % — a 1.4×
enrichment that reads as weak support for the hypothesis. A sample spanning
eight keygroups voted eight times, so the observations were not independent.
Deduplicating per multisample and using the right baseline collapses it to
1.01×. The wrong version pointed the same way as the hypothesis being tested,
which is the direction that does not get double-checked.

**All 51 offsets in 141-191 are non-zero somewhere in the corpus**, so this
region is populated rather than reserved — but nothing here decodes it, and
nothing in this project writes it.

## Directory record types, and one we cannot identify

A volume directory entry carries a type byte at offset 16:

| type | meaning |
|------|---------|
| `0x70` | program (`.P3`) |
| `0x73` | sample (`.S3`) |
| `0x00` | an empty slot — **and at least one real record type** |

**A keygroup is never a directory entry.** Keygroups exist only inside program
files, so a directory walk can never encounter one. Measured by s3ked
2026-08-14 and worth stating, because the S3000XL's resident-object pool counts
keygroups while the directory does not — the two budgets are in different units
and a reader never has to reconcile them.

### The third type

s3ked found a record on a real disc that is none of the above:

```
type 0x00, 162 bytes, at most one per volume, not present on every volume
tail bytes  1e 04     where every program and sample carries  1e 09
```

**SETTLED 2026-08-14: there is no such record type.** VinSamLib walked 21
discs — 1843 volumes, 441 498 directory slots. 32 entries carry the `1e 04`
tail; **31 sit past the last real entry**, and the single mid-directory one is
a same-name, same-size shadow of the program in the very next slot. The
original claim rested on a reader's own stop condition, which is circular, and
was withdrawn the same day it was made.

### What the junk actually is, which is worth more than the record was

**The type byte is the one field the authoring tools reliably clear. Nothing
else is.** Past the first truly empty slot (`type == 0 and size == 0`) the type
byte is zero in **375 623 of 375 623** slots — the set of type values seen
there is empty — while the rest of those records is left stale: sizes running
to `0xFFFFFF`, tail bytes taking hundreds of values that look like x86 code.

So `1e 04` is not a signature. It is a stale tail in a slot whose type byte was
cleared, which is exactly why it never appears beside a live type.

**And this is why no reader has emitted a phantom file from unallocated
capacity — but it is a property of the tools that wrote these discs, not of the
format.** A disc written by something that clears the type byte less
thoroughly would put any length-bounded reader straight into that case.
Unobserved across 21 discs is not the same as impossible; see `TODO.md`.

## Character encoding

Names are not ASCII. Each byte maps:

| byte | character |
|------|-----------|
| `0x00`–`0x09` | `0`–`9` |
| `0x0A` | space |
| `0x0B`–`0x24` | `A`–`Z` |
| `0x25` | `#` |
| `0x26` | `+` |
| `0x27` | `-` |
| `0x28` | `.` |

Anything else is undefined; both references substitute `.`. Confirmed
identical in source (1)'s `tr/\x00-\x28/0-9 A-Z#+-./` and source (2)'s
`akai2ascii()`.

Names are **12 bytes**, space-padded. All multi-byte numbers are
**little-endian**.

## Disk structure

Reference for `writers/akai_s3000_image.py` and `parsers/akai_image_parser.py`.
Hard-disk block size is fixed at **0x2000 (8192) bytes**; a floppy block is
**0x400 (1024)**. All multi-byte numbers are little-endian.

A disk is a chain of **partitions** laid end to end. Each partition holds up to
**100 volumes**; each volume holds up to **510 files**. A partition is at most
**0x1E00 blocks (60 MB)** and there are at most **18** of them; block numbers
are 16-bit, so the whole disk cannot exceed **0xFFFF blocks (~511 MB)**. Real
discs run to **16 partitions**, so the upper end of that range is used in
practice, not theoretical.

### Partition header — 3 blocks, at partition-relative block 0

| offset | field |
|--------|-------|
| `0x0000` | partition size in blocks |
| `0x0002` | 98 magic fields of 2 bytes, value `(i * 3333) & 0xffff` |
| `0x00c6` | checksum (4 bytes): partition size **in blocks** plus the sum of those 98 values |
| `0x00ca` | root directory — 100 volume entries of 16 bytes |
| `0x070a` | FAT — 0x1E00 entries of 2 bytes |
| `0x4400` | partition table (512 bytes) — **first partition on the disk only** |
| `0x4600` | `"TAGS"` then 26 tag names of 12 bytes (`TAG A` … `TAG Z`) |
| `0x6000` | end of header; volume 1's directory starts here |

Source (1)'s layout lines (`0000-00c9` disk information, `00ca-0709` volume
entries, `070a-` FAT, `6000-` file entries of volume 1) agree with this
exactly; the table above just names the fields inside the first 0xCA bytes.

The magic fields are what identifies the medium as an AKAI hard disk. Note
that magic field 0 is legitimately `0x0000`, so testing only that field
matches any zero-filled file — the detector checks several spread-out fields.

**Volume entry** (16 bytes): name (12), type (1), load number (1), start block
(2). Type `0x00` = inactive, `0x01` = S1000, `0x03` = S3000, `0x07` = CD3000.
Unused slots are named `VOLUME 002`, `VOLUME 003`, … and marked inactive.

**Partition table** at `0x4400`: 128 magic fields of value `(i * 9999) &
0xffff`, then the sampler-partition count, the DD-partition count, 19 partition
sizes and 19 DD-partition sizes. The size list is terminated by the **total**,
appended after the last real entry.

### Volume directory

Its **shape depends on the volume type in the root directory**, and getting
this wrong does not fail loudly — it invents files:

| volume type | blocks | entries |
|-------------|--------|---------|
| `0x01` S1000 | 1 | 126 |
| `0x03` S3000, `0x07` CD3000 | 2 | 510 |
| S3000 floppy | 12 | 510 |

Then 48 bytes of volume parameters. (On a floppy the parameters live in the
header label instead and this area stays zero.)

The FAT chain cannot substitute for the type here: an S1000 harddisk marks the
end of its directory chain with `0x4000`, the **same value** the S3000 uses for
"reserved for system". Reading an S1000 volume with the S3000 shape therefore
walks off the end of the directory into whatever follows and decodes it as
entries — on a real third-party S1000 library disc that turned 1 799 files
into 2 606, the surplus carrying unrecognisable type bytes.

**File entry** (24 bytes):

| offset | field |
|--------|-------|
| `00-0b` | file name (12 bytes, AKAI encoding) |
| `0c-0f` | four tag slots, `0x00` = untagged |
| `10` | file type — `0x00` means a free entry |
| `11-13` | file size in bytes (24-bit) |
| `14-15` | start block within the partition |
| `16-17` | OS version (`0x1100` = "17.00", the S3000 maximum) |

The file type is a letter identifying the kind, in one of three ranges by
sampler generation: `A`–`Z` for the S900, `a`–`z` for the S1000, and the S1000
letters with bit 7 set for the S3000. So an S3000 sample (`s`) is `0xF3` and a
program (`p`) is `0xF0`. This is why the **extension is not decoration** — it
is the only place the type comes from.

The extension is a *rule*, not a table, and the rule has exceptions:

| type | extension | |
|------|-----------|---|
| S900 range | `.<LETTER>9` | |
| S1000 range, `p` or `s` | `.P1` / `.S1` | |
| S1000 range, anything else | `.<LETTER>` | **no digit** — an FX file is `.X`, not `.X1` |
| S3000 range | `.<LETTER>3` | |
| `T` (CD3000 setup) | `.CD` | special-cased, not `.T9` |
| `h`+0x80 (CD3000 sample params) | `.s+` | special-cased, not `.H3` |
| anything else | `.x<hex>` | |

The 21 discs still on disk carry **nine** of these — 36 645 `.S1`/`.S3`,
10 933 `.P1`/`.P3`, and 2 406 auxiliary files (`.D` 954, `.X` 501, `.T` 449,
`.Q` 408, `.M3` 94). Handling only samples and programs would leave those
2 406 unnamed. (Re-measured 2026-08-09 over the discs actually present; an
earlier count covered a different subset.)

### FAT

One 2-byte entry per block, indexed by partition-relative block number. A file
occupies `ceil(size / blocksize)` blocks chained through it.

| code | meaning |
|------|---------|
| `0x0000` | free block |
| `0x4000` | reserved for system (the partition header, and the floppy header + directory) |
| `0x8000` | end of volume-directory chain (S3000) |
| `0xc000` | end of file chain |

### CD-ROM (CD3000)

A CD3000 disc is **not ISO 9660** — it is the same partition format written
raw, so an image of one is burned as a plain data image. Two differences from
a hard disk:

1. Volumes are typed **`0x07`** (CD3000) instead of `0x03`. The sampler treats
   the two as compatible.
2. The **three blocks right after the partition header** (blocks 3–5) are
   reserved for the CD-ROM info, marked `0x4000` in the FAT like the header
   itself. They hold an *index* of every file in the partition, so the sampler
   can browse the disc without reading each volume directory in turn:

| offset | field |
|--------|-------|
| `0x0000` | total number of files in the partition |
| `0x0002` | per volume (100 entries of 2 bytes): the **byte length** of that volume's file entries, i.e. `file count × 24` |
| `0x00ca` | disc label (12 bytes, AKAI encoding) |
| `0x00d6` | a flat copy of every 24-byte file entry, in volume order |

`0x00d6` is 214, which leaves room for **1015** entries in the three blocks —
past that the index is truncated and the extra files are simply not listed.
The default label is `CDROM`.

The index is a cache, not storage: the files themselves live where the FAT
says. It has to be rebuilt whenever the partition's contents change —
`akaiutil` makes that an explicit `setcdinfo` command, and our append path
does it automatically, because a stale index shows the sampler the disc's old
contents.

### Floppy

A floppy is **not** DOS-formatted: 80 tracks x 2 sides x **10** sectors x 1024
bytes = 1.6 MB. Reading one on a PC needs the drive parameters overridden
(`setfdprm`), which is why ordinary tools see an unformatted disk. Low density
is 800 blocks (800 KB), high density 1600 (1.6 MB).

There is no partition table and no root directory — the whole disk is one
volume. The header is **4 blocks** (low density) or **5** (high density):

| offset | field |
|--------|-------|
| `0x0000` | 64 file-entry slots of 24 bytes — unused on an S3000 floppy |
| `0x0600` | FAT, one 2-byte entry per floppy block |
| after FAT | volume label: name (12), 2 unused, OS version (2), volume parameters (48) |

The S3000 volume directory sits **behind** the header (block 4 or 5) and takes
12 blocks. An S3000 floppy is flagged by file type **`0xFF`** — never a valid
type — in the header's first entry slot; all 64 slots carry 12 raw `0x20`
bytes as filler and the OS version, which is *not* AKAI-encoded text (`0x20`
decodes as `V`).

### What real discs actually look like

Read from **40 commercial library CD-ROMs — twenty-one libraries under
sixteen publisher badges, one of them Akai itself**. Of those, the **21 still
on disk hold 1 843 volumes and 49 984 files** and can be re-verified at any
time; the other 19 were measured and then deleted to reclaim space —
the only *hardware-authored* evidence available so far, in both S1000 and
S3000 format. It does not confirm
what the sampler accepts, but it does show what the sampler was shipped:

- **The 16-bit total is real.** Every disc totals exactly `0xffff` or `0xfdbe`
  blocks and no more, with the last partition deliberately short to land on
  it (one is 8 × `0x1e00` + `0xfff`). The image file is a few MB larger than
  the AKAI data; the tail is not addressed.
- **Volume type and CD-ROM info are independent.** Seven of the eight are
  CD3000-typed (`0x07`) but only three carry the info block, and one is typed
  plain S3000 (`0x03`) with no info block at all. **Neither alone identifies a
  CD**, which is why `akai_is_cd3000()` and `akai_cd_label()` are separate.
- Real files carry OS version **16.50** and non-zero **tags** (`05 11`), where
  we write 17.00 and no tags. Nothing reads them back differently.
- Sample names use the **`-L` / `-R` suffix** for stereo halves
  (`PF BDF C 0-L`), confirming that a stereo sample is a pair of mono files
  and not a flag in the header. See "Stereo" below.
- Sample rates are mostly 44 100 but not always: 48 000, 22 050, 11 025 and
  even 8 000 all occur, so the rate field is worth reading rather than
  assuming.
- Programs carry polyphony **15** on S1000 discs and **31** on S3000 ones.
- Every disc also carries a handful of auxiliary files we do not parse —
  `.T` (take list), `.X` (effects), `.D` (drum inputs), `.M3` (multi) — one
  set per volume on some discs. They are named correctly and carried through
  a disk-image round trip untouched, but nothing reads their contents.
- One "disc" in the set is **ISO 9660** (`CD001`) rather than AKAI at all —
  a PC data disc bundled with the library. Content sniffing rejects it, which
  is the behaviour to want.
- Leading spaces in names are common (`  E-3 L 01-L`) — used for display
  alignment on the front panel. They are real data, so the reader keeps them
  and only strips trailing padding.
- **A program may name a sample that is not on its volume.** One disc of the
  40 does this 139 times, across 44 distinct names. 15 of those samples sit on
  **another volume of the same disc** — the sampler would resolve them only if
  that volume were loaded too — and 29 are nowhere on the disc, so they belong
  to another disc of the set. Every other disc in the corpus resolves
  completely, which is why the reader dropped such zones silently until
  2026-08-09. Resolution stays per-volume, which is what the sampler does; the
  loss is now reported.
- **Incomplete rips look perfect from the inside.** One disc in the set is
  61% present: 6 of its 9 partitions are readable, the 42 volumes that parse
  give 224 programs with 0 parse errors, 0 empty keygroup lists and 0 zones
  naming a missing sample — and three whole partitions are simply absent.
  Nothing in the volume data says so, because a partition starting past the
  end of the file is dropped before any directory is read: none of its files
  can reach the "runs past the end" list. That is why the warning counts
  **partitions** as well as bytes. A percentage alone reads like trimmed
  free space.

### Stereo

There is no stereo flag on disk. The sample header's `0x88`–`0x89` is
annotated *"address of stereo partner (internal)"* — a RAM pointer, not a file
field — and real discs pair stereo halves by the **`-L` / `-R` name suffix**.
`writers/akai_s3000_writer.py` therefore mixes stereo down to mono rather than
guessing at a pairing convention it cannot verify. Writing `-L`/`-R` pairs is
a plausible next step but wants hardware: whether the sampler pairs them
automatically, and what it does with the 12-character name budget once two
characters are spent on the suffix, are both unknown.

### What the corpus says about the *writer*

The discs were also used the other way round: for every byte
`writers/akai_s3000_writer.py` emits, the distribution of that byte across
**11 238 real S3000 samples and 4 433 real programs** was checked. An offset
where our value never appears in any real file is a guess that the format does
not agree with. There were **26**; there is now **1**.

| offset | was | now | evidence |
|--------|-----|-----|----------|
| sample `0x88-0x89` | `0000` | `FFFF` | the "no stereo partner" marker; 72% of real samples (every mono one) |
| program / keygroup `0x01-0x02` | `0000` | own RAM address in 16-byte paragraphs, chained `+12` | 19 553 consecutive deltas of exactly 12 across 2 058 programs; **no real file leaves it zero** |
| program `0x13` / `0x14` play range | the keygroup span | `24` / `127` | 96% and 99% of real programs |
| keygroup `0x20-0x21` | `0000` | `FFFF` | 100% |
| each zone `+0x14-0x17` | `0000` | `FFFF FFFF` | two 16-bit pointers, `FFFF` until the sampler fills them on load |
| unused zone name | all-zero | **spaces** | `0x00` decodes to the digit `0`, so a zeroed name reads back as `"000000000000"` |

Play range is worth singling out: narrowing it to the keygroups in use sounds
identical today, but it silently mutes any keygroup added later on the sampler
itself. Real programs leave it wide.

The one remaining offset is sample `0x18`, part of `locat` — an absolute RAM
address that akaiutil annotates *"updated by sampler"*. Unlike the stereo
partner it has no "none" sentinel to write, so it stays zero.

Two differences from real discs are **deliberate**:

- **File-entry tags.** Every real file carries one — S1000 volumes use `0x20`
  filler, S3000 volumes a tag number — and all-zero appears in 0 of 4 590 real
  entries. But `0x00` is the *documented* "free tag entry", and inventing a tag
  number would file the user's samples under a category they did not ask for.
- **OS version `0x1100`.** Real discs span 4.30 to 17.00; ours is the S3000
  maximum, which occurs 335 times in the corpus.

### Cross-check

Images built by `writers/akai_s3000_image.py` are **byte-identical** to images
`akaiutil` builds for the same content — the 16 MB hard disk, the CD3000
CD-ROM and the 1.6 MB floppy, verified over the whole file, not just the
headers. All three hashes are pinned in `tests/test_akai_image.py`. Getting there corrected two
things a header-only check would have missed: the floppy header initialises
**all 64** entry slots, not just the marker one, and the floppy volume
directory must leave its volume-parameter area zero.

## Block lengths and the block id

Two things that both references get wrong, and that real media settles.

### An S1000 block is 0x96; an S3000 block is that plus 42 bytes

`0x96` (150) is the length of an S1000 sample header, program common block and
keygroup alike. The S3000 forms are **the same layout followed by 42 bytes of
padding**, so `0xC0` (192). akaiutil's structs say so explicitly
(`struct akai_sample3000_s` is `struct akai_sample1000_s` plus `dummy1[42]`),
and real media confirms it: every program on an S1000 library disc has a
length divisible by 150, every program on an S3000 disc by 192.

Reading an S1000 file with the S3000 lengths shifts every field past the first
block. On a real S1000 disc that made **243 of 335 programs parse as zero
keygroups** and left **1 292 of 1 369 zones naming samples that do not
exist**; for samples it cut 42 bytes off the front of the PCM. With the right
lengths, all 1 465 zones resolve and the PCM matches `akaiutil`'s export
byte-for-byte.

### Byte 0x00 is a block id, not a generation marker

Both references describe it as *"header id — 1 = S1000, 3 = S3000"*. **That is
wrong.** It identifies the *kind of block*:

| value | block |
|-------|-------|
| `1` | program common |
| `2` | keygroup |
| `3` | sample header |

…and it is identical on both generations. On an S1000 library disc all 1 464
samples carry `3` and all 335 programs carry `1` — exactly as on an S3000
disc. akaiutil's own constants agree
(`SAMPLE3000_BLOCKID == SAMPLE1000_BLOCKID`).

**The generation is not recorded in the file at all.** It lives only in the
directory entry's file-type byte — i.e. in the `.S1`/`.S3`, `.P1`/`.P3`
extension. Where that is unavailable, `parsers/akai_s3000_parser.py` infers it
from the arithmetic: for a sample, `len(file) - samples×2` is either `0x96` or
`0xC0` (exact on all 6 012 samples of two real discs); for a program, the
length is a multiple of one block size or the other.

This one bit us as a *writer* bug too: mpc2emu wrote `3` into program common —
the **sample** block id — because it had taken the "3 = S3000" reading at face
value. `akaiutil` could not catch it, since it takes a file's type from the
directory entry rather than from its contents.

## Sample file

```
0000-0095   sample header (S1000, 150 bytes)
0000-00bf   sample header (S3000, 192 bytes)
     -      sample data
```

**For an S3000 sample the header is 0xC0, not the 0xBE source (1) states in
its layout line.**
That source contradicts itself — its last header entry is annotated
`8d-bd  ?? (from 0xc0??)`, i.e. the author was unsure — and source (2)'s
`sizeof(struct akai_sample3000_s)` is 192. 192 also matches the rest of the
format, where the program common block and every keygroup are 0xC0. Taking
0xBE offsets all PCM by one frame; `akaiutil` rejects such a file outright
with *"invalid sample size"*, which is how we caught it.

| offset | field |
|--------|-------|
| `00` | block id — **always 3** for a sample (see above; it is *not* the generation) |
| `01` | bandwidth (0 = 10 kHz, 1 = 20 kHz) |
| `02` | original pitch (24–127 = C0–G8) |
| `03-0e` | name (12 bytes, AKAI encoding) |
| `0f` | sample-rate-valid flag (`0x80` = yes) |
| `13` | playback type — 0 = loop in release, 1 = loop until release, **2 = no looping**, 3 = play to sample end |
| `14-15` | pitch offset (cents; `14` is the /256 part) |
| `1a-1d` | data length **in samples** |
| `1e-21` | play relative start |
| `22-25` | play relative end |
| `26-31` | loop 1: at (4), len fraction (2), len (4), times (2) |
| … | loops 2–8, same 12-byte shape, through `0x85` |
| `8a-8b` | sample rate in Hz |
| `8c` | hold-loop tune offset |

Loop `times`: 0 = no loop, 1–9998 = milliseconds, **9999 = hold** (sustain).

**Sample data is 16-bit linear PCM, SIGNED.** Source (1) says *unsigned*; that
appears to be wrong. Source (2) copies S3000 PCM straight into a WAV buffer
with no sign conversion (it converts sign only for S900 *compressed* data),
and WAV 16-bit is signed — and a sample we wrote as signed exported back
through `akaiutil` **byte-identical**. The parser still measures rather than
assuming (`_pcm_is_signed()`), which now serves as a guard against odd files
rather than as a coin-flip on the format.

## Program file

```
S3000:  0000-00bf  program common (192)   00c0-017f  keygroup 1   0180-023f  keygroup 2 ...
S1000:  0000-0095  program common (150)   0096-012b  keygroup 1   012c-01c1  keygroup 2 ...
```

### Program common

| offset | field |
|--------|-------|
| `00` | block id — **always 1** for a program (not the generation) |
| `03-0e` | program name |
| `0f` | MIDI program number |
| `10` | MIDI channel (0–15, `0xff` = omni) |
| `11` | polyphony (1–32; 1–16 on S1000) |
| `13` | play range low (24–127) — `PLAYLO` |
| `14` | play range high — `PLAYHI` |
| `15` | octave shift (±2) — `OSHIFT` |
| `16` | individual output assignment — `OUTPUT`, **`0xff` = off** |
| `17` | stereo level (0–99, 99 = full) — `STEREO` |
| `18` | pan (−50…+50, signed) — `PANPOS` |
| `19` | loudness — `PRLOUD` |

**`13`–`19` are one contiguous run and all seven are confirmed**, by three
independent routes that agree 1:1:

1. The **S1000 structure document** — `PRIDENT`, `KGRP1@`, `PRNAME`, then
   `PRGNUM PMCHAN POLYPH PRIORT PLAYLO PLAYHI OSHIFT OUTPUT STEREO PANPOS
   PRLOUD`; summing the field sizes puts `STEREO` at 23 (`0x17`) and `PANPOS`
   at 24 (`0x18`).
2. **s3ked's own field table**, at the same seven positions.
3. **A prediction tested against 5,124 library programs.** If the run is
   contiguous then `0x16` must be `OUTPUT` with `0xff` = off — and 3,188 of
   5,124 read exactly `0xff`, with `0x17` never exceeding 99 and `0x18` reading
   as a signed ±50. The run is anchored at both ends by fields confirmed
   separately: the key range, and `PRLOUD`, whose dB law was fitted on hardware.

**These same three fields also exist in the MULTI part**, at multipart 22/23/24
— the identical positions. The multi part mirrors this region. The manual gives
the precedence: *"stereo level, pan, output and effects assignment are MULTI
parameters, these are not accessible in EDIT MULTI"* — the part's copies win in
MULTI, the program's own apply in SINGLE. **Anything measuring these must do so
in SINGLE**, or it measures the wrong copy.

**`OSHIFT`, `STEREO` and `PANPOS` are read but not yet applied** — see
`docs/re_procedures/akai_program_scope_laws.md`. Each needs one law measured
first; all three are reported as dropped in the meantime.
| `2a` | **number of keygroups (1–99)** |
| `41-42` | tune offset (signed) |

### Keygroup

Each keygroup is 192 bytes on the S3000 and 150 on the S1000: 0x22 of common
data, then **four velocity zones**.

| offset | field |
|--------|-------|
| `00` | block id (2) |
| `03` | key range low |
| `04` | key range high |
| `05-06` | tune offset (signed) |
| `07` | filter frequency |
| `0c-0f` | amp attack / decay / sustain / release |
| `14-17` | filter attack / decay / sustain / release |
| `1e` | velocity-zone crossfade (0/1) |

### The IB-304F second filter board — keygroup offsets 168–190

**S3000 keygroups only.** An S1000 keygroup is 150 bytes, so these offsets do
not exist there at all.

Twenty-three fields, from `s3ked`'s parameter table. The **board** column is
whether the field genuinely requires the IB-304F.

**Only seven fields are board-gated**: `FLT2GAIN`, `FLT2MODE`, `FLT2Q`,
`FIL2FR`, `K_FRQ2`, `TONEFREQ`, `TONESLOP`. **Envelope 3 is not among them** —
its eight stages were measured on an S3000XL with no filter board at all, which
is what established that the generator lives in firmware and only the *panel
page* is gated.

> **`s3ked`'s table still declares `requires="IB304F"` on the eight ENV3
> stages**, and its own §87 — titled *"Envelope 3 does not need the IB304F"* and
> marked **corrected** — is the section that disproves it. The prose was fixed
> and **the enforcing flag was left in place**, so their reader refuses those
> exact fields on a boardless machine while the note three lines below says they
> work there. Surfaced to Jan on 2026-09-08; not changed by us, it is their
> table.
>
> **The pattern is the one this project keeps meeting**: a claim corrected in
> prose while the artefact that enforced it survives, and afterwards the
> section number makes the *artefact* look checked. §87's own words for the
> original defect apply to its remedy — *"an assumption wearing a citation, the
> most persuasive form a wrong claim can take, because the reference makes it
> look checked."*

| offset | field | board | what it is |
|---|---|---|---|
| 168 | `LSI2_ON` | — | filter 2 + tone enable |
| 169 | `FLT2GAIN` | IB304F | the panel's `attenuator` |
| 170 | `FLT2MODE` | IB304F | **LP / BP / HP / EQ** |
| 171 | `FLT2Q` | IB304F | resonance, 0–31 |
| 172 | `TONEFREQ` | IB304F | tone centre frequency |
| 173 | `TONESLOP` | IB304F | tone slope (spectral tilt) |
| 174–176 | `MODVFLT2_1..3` | — | filter-2 modulation amounts |
| 177 | `FIL2FR` | IB304F | filter 2 frequency |
| 178 | `K_FRQ2` | IB304F | filter 2 key follow |
| 179–186 | `ENV3R1/L1 … R4/L4` | **—** | envelope 3, eight stages — **not board-gated**, see below |
| 187–190 | `V_ATT3` `V_REL3` `O_REL3` `K_DAR3` | — | envelope-3 modulation |

**`FLT2MODE` enum, measured from response shape 2026-09-08** (s3ked, `FIL2FR`
80, all four values read back) — no longer resting on a panel photo:

| value | mode | measured shape |
|---|---|---|
| 0 | **LP** | monotonic fall, −6 dB at 31 Hz to −30 at 8 kHz |
| 1 | **BP** | **peak at 2 kHz**, falling either side |
| 2 | **HP** | rise then plateau |
| 3 | **EQ** | dip or bump at the corner — see below |

**Mode 3 is a parametric band whose SIGN comes from `FLT2Q`, and reading it as
a notch would be wrong for 78 % of real material.** The manual: *"a value of 16
is no cut or boost. Raising the resonance above 16 will boost the selected
cutoff frequency and lowering it below 16 will cut it."* The bench measurement
was taken at low `Q` and therefore saw a **cut**; the corpus says that is the
minority case.

| mode 3, enabled keygroups | count |
|---|---|
| `FLT2Q` **> 16 → BOOST** | **367 (78 %)** |
| `FLT2Q` < 16 → cut | 100 |
| `FLT2Q` = 16 → flat | 2 |

**The sign rule is confirmed on hardware; the PIVOT VALUE is not 16.** Measured
2026-09-08, normalised to each row's own low-frequency plateau so the insertion
loss drops out:

| `FLT2Q` | action at the corner |
|---|---|
| 0 | **cut** −5.6 dB |
| **16** | **cut −7.3 dB — the deepest of the four** |
| 25 | boost +1.9 dB |
| 31 | boost **+15.5 dB** |

**So 16 is not the neutral point on this machine** — the manual's *"a value of
16 is no cut or boost"* is right about the behaviour and wrong about the value.
The inversion happens **somewhere between 16 and 25**, and that interval is
unresolved.

**It is not a corner case: 146 of 469 EQ keygroups (31.1 %) sit in `FLT2Q`
17–23**, and `FLT2Q` **20 alone accounts for 104** — the single most common
value in EQ mode, ahead of 25 (101). Decoding by `Q > 16` would assign the
wrong sign to whatever part of that interval actually cuts, which is the
inverted-effect failure rather than a lost one.

**Until it is measured, decode `FLT2Q ≥ 24` as band-boost and `≤ 16` as
band-stop** (together 323 of 469, 69 %), and treat 17–23 as uncertain rather
than picking an unmeasured boundary.

**And the boost is not gentle**: +15.5 dB at `FLT2Q` 31 against +1.9 at 25.
Anything rendering it needs headroom.

**So `FLT2MODE = 3` decodes to band-stop or band-boost by SIGN, never to one of
them unconditionally.**

**Our model already carries exactly this distinction**, and for the same
reason: `e4b_writer` notes that band-stop (types 15–18) and band-boost (19–22)
*"are the SAME parametric band filter, differing only in gain SIGN"*. So the
AKAI EQ mode maps onto the existing pair — **type 15 `BS 2P` below 16, type 19
`BB 2P` above** — with the filter being 2-pole, so the 2P variants
specifically.

**`FLT2GAIN` is a switch, and it exactly cancels the insertion loss.** Measured
2026-09-08: the difference between `FLT2GAIN` 1 and 0 is **+6.03 dB, flat to
0.02 dB across nine octave bands**, bringing the enabled path to +0 dB against
bypass in every band. Declared range is 0..1, so it is +0 dB / +6 dB with
nothing between.

**The corpus agrees that 1 is the normal state**: of 2,457 enabled keygroups,
**2,267 (92 %) carry `FLT2GAIN` = 1** — authors set the gain that cancels the
loss. The 188 at 0 are deliberately 6 dB down and that is real authored intent,
not a default.

**For any write path: enabling filter 2 with `FLT2GAIN` = 1 is level-neutral.**
That closes the 6 dB problem — it is a switch to set, not a gain to compute.

**`LSI2_ON` cannot detect the board.** It accepts a write and reads back 1 with
no board fitted, so a tool must be *told* the board is present — **nothing on
the wire will say whether that claim is true.** The audio response is the only
detector.

**Corpus, 4,436 S3000 programs / 27,028 keygroups across 21 library discs:**

- **831 programs (18.7 %) contain at least one keygroup with `LSI2_ON = 1`** —
  2,457 keygroups in total.
- **THE ENABLE IS NOT THE EFFECT. Only 333 programs (7.5 %) have a second
  filter that is audibly doing anything**, and that is the figure to quote.
  **60 % of enabled keygroups are inert** — mode LP at frequency 99, resonance
  0, no modulation, key-follow or tone: the enable is on and the filter is a
  pass-through. An earlier version of this section gave 18.7 % as the material
  we lose, which overstates it by 2.5×.
- The 983 active keygroups are **deliberately configured, not stray bytes**:
  most carry three to six non-default parameters at once (counts by number of
  parameters set — 1: 62, 2: 126, 3: 212, 4: 285, 5: 185, 6: 113).
- What makes them active: frequency below 99 (37.6 %), mode ≠ LP (36.0 %),
  resonance (27.6 %), modulation (21.3 %), tone (20.4 %), key-follow (7.4 %).
- Among the **active** ones the modes invert: **EQ 469, HP 374**, against LP 99
  and BP 39 — the two modes that change the sound *regardless* of corner
  frequency, which is exactly what should dominate once a pass-through LP is
  excluded.
- Where **enabled** (active or not), `FLT2MODE` distributes across all four
  modes: **LP 64.0 %, EQ 19.1 %, HP 15.2 %, BP 1.6 %** — the LP majority being
  mostly the inert pass-throughs.
- Where **disabled**, `FLT2MODE` is 0 in 99.5 % of keygroups.

**That correlation is the alignment proof, and a histogram alone could not give
it:** the mode field carries meaning *only* where the enable is set. A
misaligned read would not reproduce that.

> **How the first attempt was caught.** Scanning with a fixed `0xC0` stride
> over *all* programs put **16,106 values out of range** — `LSI2_ON` is 0–1 and
> read 0–255. The cause was S1000 programs, whose 150-byte keygroup does not
> reach these offsets, so the read ran past the block. Restricting to S3000
> programs dropped out-of-range to **20 of 27,028 (0.07 %)**. This is the mirror
> of the error `corpus_scan_env2.py` already documents, and the same rule
> caught it: *a distribution is not evidence that a read is aligned; an
> out-of-range value is evidence that it is not.*

Velocity zones sit at `0x22`, `0x3a`, `0x52`, `0x6a` — a **uniform 24-byte
stride**: a 12-byte sample name then 12 bytes of zone parameters.

**Source (1) puts zone 3 at `0x53`, one byte later, and that is wrong.**
akaiutil's struct lays the four out uniformly, and real programs settle it:
across one library disc's S3000 programs, zone 3 read at `0x52` resolves to a
sample in its own volume **317 times and fails 3**, while at `0x53` it
resolves **0 times and fails 8 462** — reading a leading `0x00` that decodes
as the digit `0`. This applies to the writer as well, which was emitting
zone 3's name one byte into its own field.

| offset (rel.) | field |
|---------------|-------|
| `+00` | sample name (12 bytes) |
| `+0c` | velocity range low |
| `+0d` | velocity range high |
| `+0e-0f` | tune offset (signed) |
| `+10` | loudness offset |
| `+11` | filter frequency offset |
| `+12` | pan offset (signed) |
| `+13` | loop in release |

**A zone is disabled by an unreachable velocity range, not by a blank name.**
Real programs leave a leftover name in the slot and rely on the range alone.
Two spellings occur, and they mean the same thing:

| spelling | who writes it | the leftover name |
|----------|---------------|-------------------|
| `lo=1, hi=0` (inverted) | several libraries | a ROM waveform — `SAWTOOTH`, `PULSE`, `SQUARE` |
| `lo=0, hi=0` | another library | its own branding |

MIDI velocity 0 is note-off, so **any zone whose `hi_vel` is 0 can never be
selected**, inverted or not. That is the test to use. Measured over 54 488
named zones in the disc corpus:

**These figures are not re-derivable.** The 40 library discs behind them were read once and are not on this disk; searched 2026-08-13 and every AKAI file present is test material. Treat them as a recorded measurement, not as something a disagreement can be adjudicated against. What does NOT depend on them: `hi_vel == 0` is unreachable because MIDI velocity 0 is note-off, which holds on any conforming machine, and an inverted range is dead by hardware measurement (s3ked, 2026-08-13). Only the SPELLING distribution and these percentages need the corpus.
| | zones | name present on the disc |
|---|---|---|
| `hi_vel == 0` | 10 825 | **4.43%** |
| `hi_vel > 0` | 43 663 | **97.13%** |

Judging by the name instead invents up to three phantom zones per keygroup —
65% of one disc's zones, 67% of another's.

A zone naming a sample that is not on the disc is *not* by itself a sign of a
misread: one library's programs reference material that ships on other discs
of its set, and those zones have perfectly valid ranges.

Keygroup byte `0x1f` is *not* a count of zones in use, though it is easy to
read as one: every keygroup on every disc carries **4** there regardless of
how many zones it uses.

## Known gaps

Both references mark regions `??`, and we do not invent meanings for them:

- program common `0x48`–`0xbf`
- keygroup `0x96`–`0xbf` (source 1 lists three fields at `0x97`–`0x99` that
  *overlap* this range and contradict its own `96-bf ??` line — treated as
  unknown)
- `0x8d`–`0xbd` of the sample header
- the 48 bytes of volume parameters, and the partition header's `0x430a`–
  `0x43ff` and `0x473c`–`0x5fff`. Source 1 annotates the area near `0x4400`
  only with observed byte patterns per geometry, and source 2 names none of
  the volume-parameter fields either. The **structure** around them is settled
  (the partition table's own layout is in the table above); it is the meaning
  of the individual bytes that is not. Our writer reproduces the observed
  defaults verbatim: `00 01 01 00 00 00 32 09 0c ff` then zeros.

Nothing in this project reads those bytes, and a writer must preserve them
rather than zero them.

## Cross-verification against an independent implementation

No S3000 hardware was available, so the strongest available check was used
instead: files written by `writers/akai_s3000_writer.py` were imported into a
formatted S3000 disk image with **`akaiutil`** and read back by *its* parser,
not ours.

| check | result |
|-------|--------|
| `akaiutil` accepts the files into a volume | yes (`.S3` / `.P3` naming) |
| it identifies the types | "S3000 sample", "S3000 program" |
| sample metadata | `scount` 12000, `srate` 44100, `rkey` 0x3c, `pmode` LOOP, `loopat` 0x7d0, `length` 0x1b59 — all as written |
| program structure | `kgnum` 2, keygroup 1 → `XKICK`, keygroup 2 → `XPAD` |
| **PCM through its WAV exporter** | **byte-identical to the source** |

Two corrections came out of it, both of which would have produced broken files:

1. **The 192-byte sample header** (above). With 190 the export failed outright.
2. **Extensions matter.** `akaiutil` derives the directory-entry file-type byte
   from the extension and rejects anything it cannot map, so files must be
   named `.S3` / `.P3`. The `.a3s` / `.a3p` used by some extraction tools is a
   different convention; the reader accepts both, the writer emits both.

### Disk media

| check | result |
|-------|--------|
| hard-disk image vs `akaiutil`'s, same content | **byte-identical (16 MB, whole file)** |
| CD3000 CD-ROM image vs `akaiutil`'s | **byte-identical (whole file)** |
| 1.6 MB floppy image vs `akaiutil`'s | **byte-identical (whole file)** |
| `akaiutil`'s `vcdinfo` on a CD index we rebuilt after an append | right file count, per-volume counts, label and file list |
| `akaiutil` mounts a 3-volume, 2-partition disk we built | yes — right partitions, volumes, sizes |
| files read back out of our images | byte-identical to what went in |
| our reader on `akaiutil`'s images | same volumes, same files, byte-identical |
| **our reader vs `akaiutil`, every disc, file by file** | **all 84 345 files agree** on volume, name and size |
| **our sample parser vs `akaiutil`'s WAV export, both generations** | **PCM byte-identical**, same rate, root note and loop type |
| all 33 real library discs | 2 922 volumes read without error; 0 unparseable programs or samples |
| zones resolving to a sample on their own disc | **99.8%**; the rest reference material the library ships elsewhere |
| **every byte we write vs what real files hold there** | 26 offsets held a value no real disc uses → **1** |
| real disc content written back through our image writer and re-read | every file byte-identical |
| PCM through `akaiutil`'s WAV exporter, from inside our image | byte-identical |

### What this does NOT establish

That the *hardware* accepts these files. `akaiutil` is an independent reading
of the same undocumented format, so agreement means we are consistent with the
best available interpretation — not that Akai's ROM agrees. In particular:

- ~~Unused velocity zones are written all-zero.~~ **Answered by real discs
  2026-08-07**: the sampler marks a disabled zone with an inverted velocity
  range (`lo` 1, `hi` 0) and leaves whatever name was there. The writer now
  does the same. The old guess was actively bad — `0x00` decodes to the digit
  `0`, so a zeroed zone reads back as a sample named `"000000000000"`.
- The `??` regions are zero-filled by our writer.
