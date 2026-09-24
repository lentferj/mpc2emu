<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
<!-- SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors -->
<!-- Part of mpc2emu — https://github.com/lentferj/mpc2emu -->
<!-- Contributions: Jan Lentfer, with AI assistance (see README). -->

# Does EOS merge `-L`/`-R` zones on import? — E4XT procedure

**One import settles four firmware readings that have never been observed.**

## Why

EOS's AKAI importer carries a pairwise zone-merge loop (`0x4765c`), a sample
name classifier (`0x2faf0`: `-L` → 0, `-R` → 1, else 2, comparing **10**
characters for the first two and **12** for the third), an arena-existence
gate (`0x2fdf8`) and a partner-consistency check (`0x2fd54`). All four were
read from the ROM.

**None has ever run on material this project holds.** The only device import
available (`B030-AKAIIMPORT-full.E4B`) contains **no `-L`/`-R` names**, and
against it *no merging at all* reproduces the device's zone count on
**2 438 of 2 438 voices** (§AKAIZONEMERGE).

⚠ **Not a corner case: 41 020 of 111 221 enabled zones in the AKAI library
(36.9 %) carry a `-L`/`-R` name**, across 3 598 programs and 811 volumes. Our
simulation merges nothing — right on everything we could check, and possibly
wrong on over a third of real material.

## The medium

`~/temp/HD_stereozone.img` (16 MB), two volumes, both verified through this
project's own reader after building:

    EOSZONE   6 programs, 10 samples, 12 enabled zones, 8 with -L/-R
    LRREAL    6 programs, 80 samples, 326 enabled zones, all -L/-R,
              116 multi-zone keygroups   (real library material)

⚠ E4XT ZuluSCSI: **HD0 is off limits**; ids 1–4 are reusable and **1 and 2 are
the safest** (Jan, 2026-09-04). Back up whichever id is overwritten first.

## What each program decides

| PRG | name | zones | prediction if the merge fires |
|---|---|---|---|
| 120 | `SZ PAIR MATCH` | `SZ PAIR A -L` / `-R`, same tune | **1 zone** |
| 121 | `SZ PAIR TUNED` | `SZ TUNE B -L` / `-R`, tune differs by 1 semitone | is `0x2f8a0` a veto? **2 zones** if so |
| 122 | `SZ PAIR HALF` | `-L` present, `-R` names an absent sample | arena gate → **1 zone** |
| 123 | `SZ STEM DIFF` | `SZ STMD D -L` / `SZ STME D -R` | stems differ inside 10 → **2 zones** |
| 124 | `SZ PLAIN SAME` | `PLAIN E` twice, identical | control → **2 zones** |
| 125 | `SZ PLAIN DIFF` | `PLAIN F` / `PLAIN G` | control → **2 zones** |

Every program is one keygroup with two enabled velocity zones (0–63, 64–127).
Each zone plays a **distinct pitch**, so which survives is itself a finding
even without reading the bank back.

## Steps

1. Back up the target SCSI id's current image.
2. Write `~/temp/HD_stereozone.img` to a reusable id (1 or 2).
3. On the E4XT, import **both** volumes as AKAI.
4. Save the resulting bank and dump it back as `.E4B`.
5. Hand the `.E4B` back; the comparison is offline from there.

## What the result means

* **120 merges, 124 does not** → the classifier's `-L`/`-R` branch is the
  merge criterion, confirmed, and our simulation needs it for 36.9 % of the
  library.
* **Nothing merges** → the loop does not run on the CD-ROM/disc import path at
  all, and `zone_dedup` can be closed outright rather than left conditional.
* **121 tells us whether `0x2f8a0` is a veto** — `eosed` reads it as a safety
  check on the pair rather than the criterion, and this is the only test of
  that reading.
* `LRREAL` is the reality check: if the built volume behaves and real material
  does not, the authored material is unrepresentative and the finding is about
  the disc, not the firmware.

⚠ **Record the zone counts per program, not just an impression.** The
comparison is a count against a prediction, and this whole line of
investigation has twice been derailed by a number read through the wrong rule.
