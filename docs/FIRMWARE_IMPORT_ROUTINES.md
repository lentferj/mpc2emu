<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# The samplers' own import routines — consolidated state

**What the E-MU EOS 4.7 firmware and the Kurzweil K2000 v3.87J firmware do
when they import someone else's disc, as far as three sessions have read
them.** Compiled 2026-09-21 on branch `fw-only-imports` from the work of
`eosed` (EOS ROM + E4XT hardware), `k2kremote` (K2000 ROM + K2000R hardware)
and this project (corpus checks, format layouts, the conversion code).

Contribution: https://github.com/lentferj/mpc2emu (Jan Lentfer).
Written with Claude Code (Anthropic).

---

## Why this document exists

Two different jobs get confused, and the distinction decides everything below:

* **Converting better than the firmware.** Possible only where we can measure
  the *original* instrument, because "better" means closer to how the source
  material actually sounded. True for AKAI: an S3000XL is on the bench.
* **Converting the same as the firmware.** The only definition of correct
  available when the source instrument is absent — and it is checkable, by
  importing on the target machine and diffing its output against ours.

**There is no Ensoniq EPS/ASR and no Roland S-7xx here.** So for those two
formats the second job is the only one on the table, and matching the device
is not a compromise: it is the specification. For AKAI the first job applies
and this project deliberately keeps its own hardware-measured laws where they
compete with the firmware's tables.

---

## How to read this

Every claim below sits in exactly one bucket, and the bucket is stated:

| | |
|---|---|
| **[C]** | **Confirmed**, with the method named — hardware, corpus, or two independent traces agreeing |
| **[?]** | **Not known** — a stated gap |
| **[S]** | **Suggested, not confirmed** — believed, not demonstrated: code-only readings, single observations, plausible inferences |
| **[C-neg]** | **Confirmed absence** — an exhaustive negative search. Different evidence from reading one routine, and labelled apart so the two are not merged. **It needs a HIGHER bar than `[C]`, not a lower one** — see below |
| **[B]** | **Blocker** — what stops a path, and what would remove it |

> **`[C-neg]` carries the highest bar in this document, and it is the bucket
> that has cost the most.** A positive claim that is wrong gets tested by the
> next person who uses it. **A negative closes a door for everyone who trusts
> it** — and it redirects exactly the population you most want to reach: the
> people who read the status document before starting. One `[C-neg]` here was
> wrong (the Roland loop fields), and an external session duly told its
> readers not to look where the answer was. **Before writing `[C-neg]`,
> enumerate the assumptions the negative rests on and state which were
> tested.**

**Every open question is numbered `O1`…`O9`** in *Open topics*, near the end,
with a status table above it saying which topic blocks which import path.
**Cite open work by that number** — the numbers are stable, the prose is not,
and three separate retractions this week survived because a claim was
restated in different words elsewhere in the same file.

**`[C]` without a method is what produced most of the retraction table at the
end of this document.** *(The count is not restated here — see the note at
item 18 on why a headline that restates a derived quantity goes stale on the
next append.)*
Where a claim rests on one observation it says so, because "confirmed" and
"confirmed at one point" have been mistaken for each other twice in this
material.

Commercial disc titles are deliberately **not** named here, per this project's
convention; the material is pointed at by directory and by the properties that
matter (format version, object counts). The title↔path mapping stays local.

---

## Where the material is

### ✅ THE IMPORT DESCRIPTOR MAP — every arm, located 2026-09-22

EOS dispatches each foreign format through a table of `0x30`-byte records:
a 4-char ASCII tag, then a vector of function pointers, unused slots filled
with the stubs `0x19add4` / `0x19addc` / `0x19ade0`. Every family carries the
same **`B0` / `S1` / `P1` triple** — bank, sample, program.

| descriptor | tags | arm |
|---|---|---|
| `0x1f8f52` | `A0B0/S1/P1`, `A3B0/S1/P1` | `0x043xxx`–`0x044xxx` **AKAI**, two generations |
| `0x1f94a0` | `E4B0`, `E4Br`, `E3S1`, `E4P1`, `E4s1` | `0x04dxxx`–`0x050xxx` EMU native |
| `0x1fb6ae` | `E2B0/S1/P1` | `0x072xxx` **Ensoniq, family 2** |
| `0x1fbacc` | `EAB0/S1/P1` | `0x079xxx`–`0x07axxx` **Ensoniq, family A** |
| `0x1fc79c` | `WAVE`, `AIFF` | `0x0f0xxx`–`0x0f3xxx` |
| `0x1fcc78` | `E3B0`, `ExB0`, `EiB0`, `E3S1`, `E3P1` | `0x103xxx`–`0x105xxx` |
| `0x1fe878` | `R0B0/S1/P1` | `0x170788` / `0x1710cc` / `0x171b58` **ROLAND** |
| `0x1ff3b8` | `Midi` | `0x18axxx` |

Found by `eosed`, verified here record by record. **This locates the Roland
and Ensoniq arms**, which had been the standing gap on both paths.

> ### ⚠ THERE ARE **TWO** ENSONIQ FAMILIES, AND THIS DOCUMENT HAS ONLY EVER SEEN ONE
>
> `E2` at `0x072xxx` and `EA` at `0x079xxx`–`0x07axxx`. Every address in the
> Ensoniq section below — `0x78cc4`, `0x796a4`, `0x7b0e0`, `0x7bdf0` — is in
> the **`EA`** range. So the laws recorded there describe one of two arms, and
> nothing has ever been checked against the other. *A reader who took that
> section as "EOS's Ensoniq import" would be half right and have no way to
> know which half.*

> ### ⚠ AND BOTH SCANS THAT FOUND THIS WERE PATTERNS — neither number is a census
>
> This project scanned for a printable tag followed by one pointer shape,
> found the **`0x1f8f52` region only**, and published *"there is no Roland or
> Ensoniq descriptor"* — a fragment read as the remainder, and the third time
> in one evening a scan's fit was mistaken for its coverage.
>
> `eosed`'s first pass anchored on the stub in pointer slot 2 and found **15
> tags**, missing every family whose slot 2 holds a real function; a wider
> anchor found **43 candidates** including `NuHy`, `lLHy`, `N^Nu` — m68k
> opcode bytes that happen to be printable. **Narrow under-counts, wide
> over-counts**, and the table above is what survived reading both.
>
> **It is a floor, not a census**, and it is labelled as one because the
> difference is exactly what the earlier claim got wrong.

### Firmware images

| | |
|---|---|
| **EOS 4.7 (E4XT)** | `~/Dokumente/SYNTHS/E4XT/EOS/EMU_EOS470_OMNIFLOP.img` (also `EOS470.EXE`, `EOS470.zip`) |
| extraction | `eosflash export EMU_EOS470_OMNIFLOP.img --eos eos470.eos` then `eosflash flash eos470.eos --eos eos470_plain.eos --4mb` → **1 965 696 bytes** |
| disassembly | `m68k-linux-gnu-objdump -D -b binary -m m68k:68020 --adjust-vma=0x20000` |
| **load base** | **`0x20000`** — every EOS address in this document is a load address; file offset = `addr − 0x20000`. ISA is ColdFire MCF5206E; `m68k:68020` decodes the import region with no invalid words |
| **K2000 v3.87J** | `~/temp/k2k_fw/k2000_v387j.bin`, 1 MiB |
| disassembly | `m68k-linux-gnu-objdump -D -b binary -m m68k:68000 --adjust-vma=0x100000` |
| **load base** | **`0x100000`** — file offset = `addr − 0x100000` |

### Source corpora

| format | where | what is there |
|---|---|---|
| **Roland S-7xx** | `~/Dokumente/SYNTHS/Roland Samples/` | 2 extracted ISOs + 5 archives (`.zip`/`.rar`). The three discs all measurements rest on are one family: `S770 MR25A`, `SYS-772 HardDisk Sys` v1.04 ×2 and v2.19 ×1 |
| **Ensoniq EPS/ASR** | `~/Dokumente/SYNTHS/Ensoniq Samples/` | 5 disc images in `.7z`/`.rar`, 357 MB–681 MB each; one is the disc used for the E4XT import |
| **AKAI S1000/S3000** | `~/Dokumente/SYNTHS/Akai S3000XL/` and the card | the reference disc behind every AKAI prevalence figure here is **2690 keygroups**; a 13-program subset is `~/temp/CD3-MPC5_AKAI_SRC.iso` |
| **KRZ (K2000)** | across `~/temp`, plus `~/git-repos/kurzfiler*/tests` | **154 distinct files by content, 1156 keymaps.** Most are this project's own output — see the origin filter below |
| **E4B (E4XT)** | `~/temp/hd0_banks`, `~/temp/hd0_fx`, `~/temp/corpus_extract/eos` | **148 distinct files, ~2530 third-party voices** |
| **EOS's own AKAI import** | `~/temp/B030-AKAIIMPORT.E4B` (126 voices) and `~/temp/B030-AKAIIMPORT-full.E4B` (2800 voices) | EOS's conversion of the AKAI reference disc, dumped off the machine — the differential that found most of the AKAI results |

**Splitting a mixed corpus.** Most `.KRZ` and `.E4B` files on this machine are
mpc2emu's own output, so a raw count validates our writer against itself. The
filter that works is **a feature our writer cannot emit**:

* KRZ — any keymap `method` other than `0x13`/`0x17`. Six banks qualify and
  carry `0x01`, `0x03`, `0x05`, `0x0b`, `0x0f`, `0x11` between them.
* E4B — any voice whose cord table departs from `_MOD_TMPL` (e.g. `Key~ 0x09`
  where we always write `Key+ 0x08`): 92 of 148 files.

### Hardware

E4XT (EOS 4.7) and K2000R, both on the bench with SysEx tooling: `eosed` can
dump E4XT presets, `k2kremote` can dump K2000 objects. **An S3000XL is also
present** — which is why AKAI is the one format where the firmware is not the
only reference.

---

# EOS 4.7 (E4XT) — AKAI S1000/S3000 → E4B

**The best-understood of the six, and the only one where the firmware is not
the only reference** — an S3000XL is on the bench, so where EOS and a measured
hardware law disagree, this project keeps the measurement.

## Where the code is

| address | what |
|---|---|
| `0x48934`–`0x48a0c` | the orchestrator: header convert, then a keygroup loop |
| `0x47778`–`0x47e44` | the program-header converter (stack frame −200) |
| `0x47f08`, `0x48284`, `0x48500` | parallel converters (frames −208/−208/−200) |
| `0x48ab0`–`0x48c00`+ | conversion lookup tables, packed back to back |
| `0x303d0` | **`T_atk`** — attack rate table |
| `0x30434` | **`T_dec`** — decay rate table, **shared by decay and release** |
| `0x2f6f8` | the volume scaler |
| `0x2f6b4` | the generic rescaler |
| `0x3060c` / `0x31ba4` | AKAI name → ASCII converter / character set |
| `0x42a00`–`0x44400` | disk browser and file identification — **not** the importer |

## [C] Confirmed

**The generic rescaler, and it is arithmetic and not a fit.** [C: instruction
stream, plus 363/363 on EOS's own output for the volume row]

    amount = round(clamp(v, lo, hi) * scale / hi)

`0x2f6b4` doubles, adds 1 when positive, then shifts — **round-half-up**, not
truncation, which differs at every exact half.

**Preset volume, `header[27]`.** [C: 363/363 against EOS's output]
`clamp((loudness − 99) * 8 / 10, −96, +10)`, signed dB. Implemented here
(§AKAIIMPORTVOL). **Only the AKAI importer sets it** — Ensoniq and Roland both
write zero, so a non-zero preset volume on an Ensoniq- or Roland-sourced bank
did not come from EOS.

**Nine modulation cords from nine keygroup bytes.** [C: instruction stream for
the arithmetic; 7.0% of import voices carrying the `Key+` cord against 7.5% of
source keygroups with non-zero keyfollow is an independent prevalence check]

    kg    src  dst   destination   scale
    0x08    8   56   FilFreq         96
    0x10   10   73   VEnvAtk         48
    0x11   10   75   VEnvRls         48
    0x12   13   75   VEnvRls         48
    0x13    8   75   VEnvRls         48
    0x18   10   81   FEnvAtk         48
    0x19   10   83   FEnvRls         48
    0x1a   13   83   FEnvRls         48
    0x1b    8   83   FEnvRls         48

Sources `Key+ 0x08`, `Vel+ 0x0A`, `RlsVel 0x0D`. Destinations are literal
`moveq` operands and **are not contiguous** — `VEnvAtk 0x49`, `VEnvRls 0x4B`,
`FEnvAtk 0x51`, `FEnvRls 0x53` — so inferring the block from `0x49` puts every
release cord one byte low. `0x49` is independently confirmed: it is the
destination this project's writer has used for its velocity→attack cord since
that cord was hardware-RE'd.

**The guard is part of the law.** A zero AKAI byte writes **no cord at all**,
and EOS does not advance its slot cursor. On the reference disc 92.5% of
keygroups take that branch.

> ### ✅ THE SIGN RULE IS PER-**SOURCE**, AND IT RECONCILES `O7` WITH `O7b` — 2026-09-22
>
> Two hardware results looked contradictory. `O7b` measured twelve
> `vel_to_attack` points that **all** came back sign-flipped; `O7` measured
> `kg[0x13] = −5` arriving as amount `−5`, **not** flipped.
>
> **Both are right.** `negl %d0` sits in exactly the four `Vel+` blocks —
> `0x46998`, `0x469dc`, `0x46aa4`, `0x46ae8` — and in none of the `Key+` or
> `RlsVel` ones:
>
> | kg | src | dst | scale | clamp | `negl` |
> |---|---|---|---:|---|---|
> | `0x08` | `Key+ 8` | `FilFreq 56` | 96 | ±50 | no |
> | `0x10` | `Vel+ 10` | `VEnvAtk 73` | 48 | ±50 | **YES** |
> | `0x11` | `Vel+ 10` | `VEnvRls 75` | 48 | ±50 | **YES** |
> | `0x12` | `RlsVel 13` | `VEnvRls 75` | 48 | ±50 | no |
> | `0x13` | `Key+ 8` | `VEnvRls 75` | 48 | ±50 | no |
> | `0x18` | `Vel+ 10` | `FEnvAtk 81` | 48 | ±50 | **YES** |
> | `0x19` | `Vel+ 10` | `FEnvRls 83` | 48 | ±50 | **YES** |
> | `0x1a` | `RlsVel 13` | `FEnvRls 83` | 48 | ±50 | no |
> | `0x1b` | `Key+ 8` | `FEnvRls 83` | 48 | ±50 | no |
>
> **The plausible theory was wrong, and it is the sort that survives because
> it explains the data you have.** *"E4B envelope destinations are RATES and
> AKAI's are TIMES, so envelope cords invert"* fits all twelve `O7b` points,
> is physically reasonable, and predicts that `Key+ → VEnvRls` inverts too.
> It does not. The rule is about the **source**, and no amount of reasoning
> about rate-versus-time would have produced it — it came off the instruction
> stream. **The one measurement that could refute the theory had already been
> taken and was sitting in this document three sections up.**
>
> The clamp column is read from the stack arguments to `0x2f6b4`
> (`pea 0xffffffce`, `pea 0x32`), not assumed from the panel rail.

> ### ⚠ THE NINE CORDS ARE NOT ALL OF THEM — there is a whole assignable mod matrix
>
> Past the nine fixed cords the same routine runs **ten more blocks through a
> shared emitter at `0x46370`**. Three are fully read, and they are the AKAI
> **assignable filter-mod slots**:
>
> | at | src id | amount byte | scale | dst |
> |---|---|---|---:|---|
> | `0x46832` | `%a5@(59)` | `kg[0x97]` | 96 | `FilFreq 56` |
> | `0x46890` | `%a5@(60)` | `kg[0x98]` | 96 | `FilFreq 56` |
> | `0x468f4` | `%a5@(61)` | `kg[0x99]` | 96 | `FilFreq 56` |
>
> `0x97`/`0x98`/`0x99` are **151/152/153 — exactly `AKAI_MODVFILT1_OFFSET` and
> its two siblings**, which `parsers/akai_s3000_parser.py` has named all
> along. Each block is guarded **twice**: the staged source id must be
> non-zero *and* the keygroup amount must be non-zero.
>
> ### ✅ THE ENUM MAP IS AT `0x48ab0`, AND IT CANCELLED A CARD SWAP
>
> `src_id = TABLE_0x48ab0[clamp(MODSFILT, 0, 14)]`, indexed at `0x47d4a` with
> the same `extbl`/negative→0 shape as the envelope tables, staged into
> `%a5@(59..61)`. Fifteen bytes, read here and byte-identical to `eosed`'s:
>
> | sel | id | | sel | id | | sel | id |
> |---:|---:|---|---:|---:|---|---:|---:|
> | 0 | `0` Off | | 5 | `10` Vel+ | | 10 | `80` **FEnv+** |
> | 1 | `17` ModWl | | 6 | `9` Key~ | | 11 | `17` ModWl |
> | 2 | `16` PitWl | | 7 | `97` Lfo1+ | | 12 | `16` PitWl |
> | 3 | `18` Press | | 8 | `105` Lfo2+ | | 13 | `20` MidiA |
> | 4 | `20` MidiA | | 9 | `72` VEnv+ | | 14 | `88` AEnv+ |
>
> **The plan of record an hour earlier was a card swap** — load a volume
> spanning many distinct `MODSFILT` values and read back which source ids came
> out. It was a good plan and it is now unnecessary.
>
> ✅ **Two corroborations neither project designed:** selector `10` → `80`
> `FEnv+` is *exactly* the gate condition at `0x46910`, and **no entry falls
> outside the known cord-source set.**
>
> ⚠ **AND THE TABLE HAD ALREADY BEEN FOUND AND FILED AS NOT-A-TABLE.**
> `eosed`'s notes carried `0x48ab0` under *"do not build on: its values are
> not monotonic and do not look like a mapping."* **Both observations were
> correct.** An enum map is not monotonic and does not look like a mapping —
> it looks like noise, because it is a permutation of unrelated ids rather
> than a curve. *The property used to rule it out was the property that
> identifies it.* The test was reached for because the neighbouring tables are
> rate and level curves, so "not a curve" was read as "not a table" — a
> classification inherited from context rather than tested against what the
> thing could be. It sat in the discard bucket for two days while both
> projects called its contents the blocker.
>
> **A negative classification is only as good as the test's ability to
> separate the two cases**, and this test could not separate them at all.
>
> ### ✅✅ AND THE TABLE IS NOW **MEASURED** — 6 of 6 discriminating presets, 2026-09-22
>
> 250 AKAI programs imported into the E4XT (`AKAI-A/V1`/`AKAI-A/V2`/`AKAI-A/V3` +
> `AKAI-B/V1`, chosen by a search over 163 volumes for **selector spread**),
> predictions written to disk before the read-back, `eosed` dumping:
>
> | preset | sel | expected | measured |
> |---|---:|---|---|
> | `S1` | 2 | `PitWl 16` | ✅ |
> | `S2` | 7 | `Lfo1+ 97` | ✅ |
> | `S3` | 14 | `AEnv+ 88` | ✅ amounts exact |
> | `S4` | 11 | `ModWl 17` | ✅ amount −41 exact |
> | `S5` | 4 | `MidiA 20` | ✅ amounts exact |
> | `S6` | 4 | `MidiA 20` | ✅ amounts exact |
>
> **Selector 11 returning the same id as selector 1 confirms the duplicate
> rows are real** rather than a transcription artefact — a check worth having
> built in, since it was the one failure mode a correct-looking table could
> still have had.
>
> ⚠ **Not claimed:** this tests the *table*. Not the seven program-level
> slots, and not slot ordering. Only the six discriminating presets were read;
> the bulk selectors `5` and `10` are confirmed only where they co-occur here.
>
> ### ⚠⚠ AND THE WIRE DIVISOR IS **127**, NOT 128
>
>     wire = round(stored * 100 / 127)
>
> **Stored 96 is the first value either project ever measured where the two
> differ**, and it appeared three times in that six-preset read-back. Every
> earlier measured point agrees under *both* divisors, which is exactly why
> the wrong one survived a fortnight. 127 is also the more principled: the
> stored field is a symmetric signed byte, `−127..+127`.
>
> ### ⚠ AND "22/22" IS THREE POINTS OF SUPPORT PLUS NINETEEN OF CONSISTENCY
>
> Score on measured points is `127 → 22/22`, `128 → 19/22` — but a point only
> **supports** one divisor over the other where the two disagree, and
> **nothing except the stored-96 amounts does.** Not one of the nine keyfollow
> points, not one of the five `vel_to_attack` points, not `O7`.
>
> So the margin rests on **three cord amounts, all of stored value 96**, which
> is the `±50` clamp rail — three readings of *one* stored value, not three
> independent ones. 127 is right and unrefuted, and the evidence for it is
> narrow in a way the raw fraction hides.
>
> *Recorded because the next person deciding whether another read-back is
> worth rig time needs the width of the evidence, not its length.* `eosed`
> made the distinction; this project's own rescore had reported `19/19` as if
> it were nineteen points of support.
>
> **Ninth keyfollow point, paired here from the disc:** `eosed` held a
> `S3` `Key+` cord at wire `−13` with no source value. The program's
> `filter_keyfollow` is **−9** → stored `−17` → wire `−13` under *both*
> divisors. Corroboration, not discrimination — and it cost a disc read rather
> than a card swap.
>
> **It was found by material chosen for SPREAD rather than for the question.**
> A convenience sample would have passed. *A constant that every measurement
> you hold agrees with is not thereby measured — it is merely unrefuted.*
>
> Same load also delivered **`S4`'s `Key+ 36` = keyfollow 24**, twice
> the previous maximum and exactly `24 × 1.5` — the ±24 pair an afternoon had
> been spent arranging to load, arriving incidentally.
>
> ### ❌ THE "27th UNEXPLAINED POINT" WAS NEVER A MEASUREMENT — retracted within the hour
>
> This section briefly reported `va = −17 → 12` as a measured point that no
> divisor explains, with a hypothesis about a mis-read source byte and an
> offer to check the ISO. **There is no such measurement.** `eosed` grepped
> every log: five distinct `va` pairs have ever been read — `−3, −5, −8, −14,
> −50` — and `−17` is not among them.
>
> `va −17 → 12` is a **cell from the `×48/50` column of a pre-registration
> table**, sent hours earlier to separate two candidate laws. It was copied
> into a set named `MEASURED` and then used to score the law it had been
> derived from.
>
> **On measured points the score is `127 → 19/19`, `128 → 17/19`**, failing
> only the two stored-96 presets. The conclusion never moved; the evidence for
> it was overstated. `kf 14 → 21` came out of the same table and is gone too —
> that one nobody else spotted.
>
> > ## ⚠ A PREDICTION TABLE AND A MEASUREMENT SET WERE MERGED, AND THE MERGED
> > ## SET WAS USED TO SCORE THE THING THE PREDICTIONS CAME FROM
> >
> > Every row looked like data because every row had the same columns. **A
> > table's provenance is not visible in its shape** — which is an argument
> > for not letting predictions and observations share a container at all,
> > rather than for labelling them carefully inside one.
> >
> > **The tell was the COUNT.** Twelve `va` pairs were claimed; five had ever
> > been read. *A count that exceeds what anyone measured is the cheapest
> > possible check*, and neither project ran it — the inflated number sat in a
> > message to `eosed`, who did not notice it either.
> >
> > **And it was a near-miss in both directions.** Had the `×48/50` prediction
> > happened to be *wrong* at `−17`, `eosed` would have been handed an anomaly
> > in measurements they never took, and gone looking for it on the rig.
> >
> > This document's own `O7b` section named the real measured set correctly —
> > `−50`, `−14`, `−8` — **hours before the test suite contradicted it.**

> ### ✅ OUR PARSER'S ENUM READING WAS RIGHT — AND SO WAS ITS CAVEAT
>
> `akai_s3000_parser` records `MODSFILT1=5` velocity, `2=8` LFO2, `3=10` env2
> from two programs, flagged *"may be this library's common template rather
> than a fixed convention, so this is read per-program rather than assumed."*
> **The firmware agrees at all three**, so the *meaning* of a selector is
> EOS's fixed convention.
>
> The caveat was about which **values appear**, not what they mean — and a
> sweep of 21 AKAI discs here settles that the other way: **106 distinct
> `(MODSFILT1,2,3)` combinations, 10 933 programs**, `MODSFILT2` alone taking
> 14 different values. The disc that happened to be in the E4XT at the time
> carries **one** combination across all 369 of its programs. *Reading them
> per-program was correct, and collapsing the two statements into "the enum is
> confirmed" would lose the half that governs how the parser behaves.*
>
> **All three are now emitted** by `writers/eos_firmware_sim.py`, guarded
> twice as the firmware guards them — on the mapped source id *and* on the
> keygroup amount.
>
> **And `kg[0x1c]` is the other half of the same mechanism, not a second
> finding.** Its cord's destination is computed — `0xA8 + slot`, *the amount
> of another cord*, the mod-wheel gating trick — and each block above captures
> its slot at `0x46910` **only when its source id is `80` (`FEnv+`)**.
> `0x46bb0` then writes into whichever slot was captured and skips entirely
> when none was (`%d4 == −1`).
>
> ⚠ **This entry said something weaker for three hours, and `eosed` corrected
> it.** It read the cord's *source* as "a runtime value in `%d6`" and
> concluded it "cannot be expressed as a keygroup-byte row". **`%d6` holds the
> source id BEFORE the rescale and the AMOUNT after it** — two uses of one
> register, read as one, in a routine where every other cord's value arrives
> the same way. The value was in `%d5` from `%a3@(153)` the whole time. *A
> register reused across a call is not a hard read; it is a read that needs
> the call boundary marked, and this one did not mark it.*

> ### ❌ RETRACTED 2026-09-22 — `0x4430c` IS AN AKAI ARM, AND THE METHOD CLAIM WAS THE PROBLEM
>
> This section said `0x4430c` was reached only through a pointer and therefore
> "belongs to one of the other importers". **There is an AKAI format-descriptor
> table at `0x1f8f52`** — six records of `0x30` bytes, each a 4-char ASCII tag
> then a vector of function pointers, unused slots holding the stubs
> `0x19add4`/`0x19addc`/`0x19ade0`:
>
>     A0B0 @1f8f52   A0S1 @1f8f82   A0P1 @1f8fb2
>     A3B0 @1f8fe2   A3S1 @1f9012   A3P1 @1f9042
>
> **`0x4430c` is entry 3 of `A3S1`.** A different *file-type* arm of AKAI, not
> a different sampler.
>
> **Two things this project told `eosed` are withdrawn.** Their reading of
> `0x44632` as the AKAI keyfollow cord was **right**, and they struck it on
> this section's authority. And the guard/value mismatch at `0x44958` — tests
> source byte `0x13`, converts source byte `0x1b` — **is in an AKAI arm**,
> where this document said it was not.
>
> ⚠ **THE METHOD CLAIM IS WHAT MADE THE ERROR CREDIBLE.** The call-graph query
> found no `jsr`/`bsr` and one data pointer; that half was right. "Therefore a
> different importer" was an inference with no evidence, published under the
> heading *"settled by the CALL GRAPH, not by its contents"*. **A method being
> better than the alternative does not make its output a finding** — and a
> peer overturned a correct reading of their own because the claim arrived
> wearing a method's name. The dispatch table's address was in hand and
> nobody read what was in it.
>
> **And the extra source bytes cited as proof it was foreign** (`0x09`, `0x0a`,
> `0x0b` into `FilFreq`, `0x1d` into `Pitch` at scale 26) are therefore **AKAI
> bytes the modelled arm does not read** — two AKAI arms disagreeing about
> which source bytes become cords, which is a more interesting finding than
> the one it was mistaken for.

> ### ~~✅ WHICH ROUTINE IS THE AKAI ARM — settled by the CALL GRAPH, not by its contents~~ (superseded above)
>
>     0x4647c <- 0x473a6 in 0x46da8 <- 0x47650 in 0x475b4
>             <- 0x47fea in 0x47f08 <- 0x489c0 in 0x48934   (the AKAI orchestrator)
>
> **A second, near-identical cord emitter exists at `0x4430c`** — same shape,
> same rescaler, same slot cursor, same destination constants — reached only
> through a pointer at `0x1f901e`, so it belongs to one of the other
> importers. It additionally carries four source bytes the AKAI arm has no
> equivalent for (`0x09`, `0x0a`, `0x0b` into `FilFreq`; `0x1d` into `Pitch`
> at scale 26).
>
> ⚠ **And it contains a plain guard/value mismatch** — `0x44958` tests source
> byte `0x13` and then converts source byte `0x1b`:
>
>     44958:  tstb  %a3@(19)        <- guards on byte 0x13
>     44972:  moveb %a3@(27),%d0    <- converts byte 0x1b
>
> **The AKAI arm does not have this bug** (`0x46b6e` guards and reads `0x1b`
> both times). *Reading either block's contents would not have told them
> apart; one call-graph query did.* Had the bug been attributed to AKAI it
> would have been written into the simulation and then "confirmed" by a
> hardware diff that disagreed for an unrelated reason.

> ### ✅ THE ENVELOPE TABLES ARE EXTRACTED — `T_atk`, `T_dec`, 100 bytes each
>
> In `writers/eos_firmware_sim.py`, read out of the firmware here and
> **byte-identical to `eosed`'s independent read** of the same addresses. The
> indexing sites `0x2f7c8`/`0x2f7ec` give all three properties by reading
> rather than by arithmetic on two labels: **1-byte entries** (`addal %d1,%a0`
> with no scale), **100 each** (`0x303d0 + 100 == 0x30434`), **forward**
> (AKAI 0 → `table[0]`). Ranges 0..89 and 0..110, both monotonic — so **EOS
> cannot produce the fastest attacks the E4XT is capable of.**
>
> ⚠ **`T_atk` IS FLAT AT ZERO FOR ITS FIRST 21 ENTRIES.** AKAI attack 0..20
> all import as rate 0, so a sim/device diff over short-attack material agrees
> *trivially* on those voices. `eosed`'s warning, and the right kind: **a
> faithful sim that agrees with the device for the wrong reason is worse than
> one that disagrees, because it retires a test nobody actually ran.**
>
> ⚠ **The index is NOT `clamp(b, 0, 99)`.** The code does `extbl` and sends
> anything *negative* to 0 before clamping the rest to 99, so a stored `200`
> reads as `−56` and imports as rate **0** — the slowest the table has, where
> an unsigned clamp gives 99, the fastest. Opposite ends. **Prevalence,
> measured here: 3 keygroups in 69 062, on 1 disc of 21** (10 933 programs,
> the whole AKAI ISO corpus). Real, reachable, negligible — implemented
> because it is free, and recorded with its prevalence so nobody spends bench
> time on it.

> ### ⚠ `header[27]`'s `+10` UPPER CLAMP IS UNREACHABLE
>
> The **input** is clamped to 0..99 before the scale, so the output never
> rises above 0 and no AKAI byte can reach the documented `+10`. Worth
> stating: a reader who sees `clamp(−96, +10)` and tests the top rail will
> conclude the implementation is broken.
>
> The same field cost a bug in the first draft of the simulation, which
> **re-implemented** arithmetic this project had already measured and got it
> wrong by 1 dB on every value not divisible by 10 — Python's `//` floors
> where the firmware's signed divide truncates toward zero.
> `akai_program_loudness_to_e4b_db` already said so in its own comment. The
> simulation now delegates to it.

**Slot allocation is a cursor** (`%d7`, carried in `%fp@(-4)`), packing cords
densely in encounter order, with a bounds check that abandons the run at 24.

**The AKAI source offsets are file offsets** — unlike Ensoniq's. [C: two
independent readings] This project's own parser reads `kg[0x08]` as
`filter_keyfollow` and `kg[0x10]` as `vel_to_attack` at exactly those offsets,
and EOS's eight cord bytes fall into **two blocks of four, each immediately
after one of the two envelope blocks** (`0x0c–0x0f` amp, `0x14–0x17` env2), in
the same order both times. A wrong base does not land twice in one pattern
beside two independently located blocks.

**The envelope mapping is a table, and EOS computes no time at all.**
[C: 564/564 exact, input to output, against 141 single-keygroup programs]

    PZT[0]/[1]   Attack1   rate = T_atk[clamp(kg 0x0c,0,99)]   level = 127
    PZT[2]/[3]   Attack2   rate = 0                            level = 127
    PZT[4]/[5]   Decay1    rate = 0                            level = 127   <- plateau
    PZT[6]/[7]   Decay2    rate = T_dec[clamp(kg 0x0d,0,99)]   level = round(clamp(kg 0x0e,0,99)*127/99)
    PZT[8]/[9]   Release1  rate = T_dec[clamp(kg 0x0f,0,99)]   level = 0
    PZT[10]/[11] Release2  rate = 0                            level = 0

**What the importer silently drops** [**C-neg**: an *exhaustive negative*
search — the stack offsets do not appear anywhere in the disassembly. A
different kind of evidence from reading one routine, and labelled separately
so the two are not confused]: `MODVLFOD 0x60`, `PANDEL 0x1f`, `LFODEL 0x23` — so
**EOS carries both LFOs' rate and depth and neither of their delays**. And
`TRANSPOSE` is ±50 on the AKAI, clamped to ±24, so a program transposed beyond
two octaves is silently narrowed.

**Zone de-duplication.** EOS compares velocity zones pairwise and merges
identical ones, so voice *i* ≠ keygroup *i*. [C: explains the 23 differing
zone counts in the import differential]

## [S] Suggested, not confirmed

* **Pan** — `clamp(round(clamp(v,−50,50) * 64/50), −64, +63)`. **Instruction
  stream only**: not corpus-checked, not hardware-checked, and not present in
  eosed's own list of AKAI rows checked against data. **It was in [C] in the
  first version of this document and that was wrong** — the bracket withdrew
  what the label promised, and a reader who trusts the label need never reach
  the parenthesis. **Where the bucket error came from, traced to its
  source:** eosed's own
  `AKAI_IMPORT.md` carried this row under a heading reading **"Confirmed both
  ends"**, beside the preset-volume row which *is* checked 363/363. For pan,
  what was confirmed was that both **endpoints are identified** — the AKAI
  parameter by name, the E4 field by its destination range — and **an
  identified source and an identified destination do not verify the arithmetic
  between them.** The row could have the wrong rounding, the wrong clamp order
  or the wrong scale constant and nothing would show it. Corrected at source
  (`1d588ac`); the heading now separates VERIFIED from UNVERIFIED rows.
  **And even the endpoint identification is weaker than it looks here**, since
  the AKAI-side naming falls under the provenance caveat: possibly EOS's
  author and this project reading one Akai document rather than two
  independent reads of the machine. Same shape as the Ensoniq pan claim that
  was wrong this morning — a code-read treated as settled. **It was very
  nearly built on, too:** this project
  *proposed* crossing the planned PANPOS measurement off
  `docs/re_procedures/akai_program_scope_laws.md` on this row's authority.
  **Checked on review — the removal was never actually made; Measurement 3
  stands open**, and the first draft of this bullet asserted a consequence
  that had not happened.
* **`header[26]` transpose** — read from the code as a plain clamped copy.
  EOS writes **zero on all 363 presets** of the reference disc, so nothing on
  this material exercises it.
* **Three of the nine cords are underivable from this material.** `0x13`,
  `0x1a`, `0x1b` are zero on all 2690 reference-disc keygroups, and the guard
  means EOS's output is silent about them too — no experiment on that disc can
  separate "destination read correctly" from "read wrong". **`0x13` is −5 on
  17 of 205 keygroups of the 13-program subset**, so it *is* testable, by
  importing that program and reading the resulting cord. Pre-registered: a
  `Key+ → 0x4B` cord at −5 confirms, a decay destination refutes — and the
  refutation would be a finding about EOS rather than about the trace, since
  AKAI documentation names that byte a key→**decay** dependence.
* **The thirteen program-header rescales.** Real arithmetic, but they stage
  into `%a5`, a 68-byte **scratch struct in the caller's frame**, not an
  output structure — a corpus search for the rescaled values at file offsets
  found none of them. **Do not implement against file offsets.** Six of the
  thirteen are additionally unexercised: their source byte is constant across
  all 361 programs.
* **`%a5` is EOS's in-memory voice structure and not the E4B `vpar` layout.**
  Two candidate alignments give inconsistent shifts (11 vs 36), so it is a
  different layout rather than a shifted one.
* **The name converter maps character 41 to `'q'`** by reading one past a
  41-entry charset table. Match it to be byte-identical to EOS; do not match
  it to be correct.
* **"EOS ignores the fields AKAI's documentation calls unused"** may be two
  parties reading one document rather than evidence about the machine.

## [?] Not known

* The **filter** path and the **LFO** path beyond rate and depth.
* The **sample/audio** path — nothing in the traced regions touches PCM.
* What the thirteen staged header values become once the keygroup pass
  consumes them.

## [B] Blockers

**None for extending the current implementation.** This is the one path where
a source reader already exists here (`parsers/akai_s3000_parser.py`,
`parsers/akai_image_parser.py`), which is why seven cords went in within an
hour of the destinations being supplied. Remaining work is a code job:
zone de-duplication, and the cords' sonic verification where the disc
exercises them.

**Deliberately not taken:** EOS's envelope table, because it would replace
*measured hardware laws* with a lookup. The rule this project keeps —
**EOS is a starting point for a field we DROP, never an arbiter for one we
already convert.**

---

# EOS 4.7 (E4XT) — Ensoniq EPS/ASR → E4B

> ## ✅ THE IMPORTER EXISTS AND IS NAMED — strings, 2026-09-22
>
> Searched because the descriptor table at `0x1f8f52` has **no Ensoniq entry**
> (its nine records are AKAI ×6, `E3S1`, `E4P1`, `FILE`), and the EOS **4.0**
> manual mentions Ensoniq zero times while naming Akai and Roland S-700
> explicitly. Both facts are real and neither means what it looks like: the
> firmware is **4.7**, and it carries
>
>     0x772e0  "Scanning Ensoniq device"      referenced 0x76878/0x76ad0/0x76c62
>     0x7a80c  "Ensoniq Bank"                 0x79b6a
>     0x7a840  "Ensoniq sample"               0x79ef6
>     0x7a850  "Ensoniq Instrument"           0x7a196
>     0x7a81c  "UNNAMED WS"                   0x79bb0/0x79c06   <- EPS wavesample
>     0x25d58  "Foreign sampler SCSI ID"      0x25af6           <- a PREFERENCE
>     0x25d18  "Adjust Akai/Ensoniq fractional loops"  0x25ab2
>
> Those addresses sit in the same `0x76800`–`0x7c000` region this section
> already documents, so the existing reading was in the right place. **The new
> information is the vocabulary**: EOS speaks of *scanning a device* and of a
> *foreign sampler SCSI id*, not of reading a disc.
>
> ### ⚠ AND THAT MAY DISSOLVE THE BLOCKER RATHER THAN SOLVE IT
>
> The blocker below is *"every law is a law about a struct nobody can reliably
> find"*. If EOS reaches an EPS over SCSI rather than through a disc
> filesystem, the struct it converts is the sampler's **in-memory** layout, and
> no amount of searching a disc image will locate it. **Not established** —
> "device" is ambiguous and an EPS formats its own SCSI disks — but it is the
> first hypothesis that explains the shape of the failure rather than the
> failure itself.
>
> ### ✅ AND A SIMULATION MAY NOT NEED THE LOCATOR AT ALL
>
> *This project's own rule, arriving late:* **the firmware traces give the
> conversion LAW, never the source PARSER.** `parsers/eps_parser.py` already
> locates every struct this path needs — and already applies **EOS's own**
> volume table and pan law, because both were derived from this firmware and
> implemented directly.
>
> **So for the fields that are known, our ordinary conversion IS the
> firmware's**, and a simulation would differ only in what EOS *omits*.
> `0x7bb90` is annotated "where envelopes/filters would be, if they were
> anywhere", and the zone builder at `0x7b0e0` stores to offsets
> `3,4,7,8,12,13,14` only — consistent with a 22-byte zone entry and nothing
> else. ⚠ **That is suggestive, not exhaustive**, and until the omission is
> established as a negative this path stays `not implemented` rather than
> being shipped on a plausible silence.
>
> **`TABLE_0x796a4` extracted** — 128 entries, a clean dB curve from −72 at
> index 0 to 0 at 127, monotonic non-decreasing.



**Laws in good shape, structure locator unsolved.** Every law below is a law
about a struct nobody can reliably find, and that — not any missing
arithmetic — is what stands between this and a working path.

## Where the code is

| address | what |
|---|---|
| `0x7bdf0` | preset builder — calls the channel builder twice, `chan=1` then `chan=0` |
| `0x7be64` | the name-suffix write, `'*'`=42 / `'0'`=48 from the two bits of the variant |
| `0x7b0e0` | zone builder — the parameter mapping |
| `0x78d64` | the layer gate (table loaded by `0x78d24`) |
| `0x78f10` | pan: `moveb +221` / `extbl` / `mulsl #63` / `divsll #127` |
| `0x78edc` | volume, including the boost branch |
| `0x796a4` | the 128-entry volume table |
| `0x7b094` | the name converter (plain ASCII, source at `+10`) |
| `0x78cc4` | **packed 4-byte group decoder** at struct `+240/+248/+256/+264` — very likely the audio pointer and length |
| `0x7bb90` | where envelopes/filters would be, if they were anywhere |

## [C] Confirmed

**Pan.** [C: hardware, 25/25 out of sample — pan was *not* in the search key
used to locate the structs]

    pan = (int8)ws[221] * 63 / 127          signed, truncating

    source  -127  -85  -42   0  +42  +127
    E4 pan   -63  -42  -20   0  +20   +63

**Volume — the unboosted path.** [C: hardware, **24/25**, eleven distinct
table indices exercised]

    volume = TABLE_0x796a4[ ws[208] ]                    <- [C]

**The boost branch.** [S: **n = 1** — exactly one instrument of the 25 carries
`ws[225]`]

    volume = TABLE_0x796a4[ min((ws[208] + 12) & 0xff, 127) ]   when ws[225]   <- [S]

`+225` is **not a separate parameter**: it is a `+12` shift on the table index.
**The two halves are split because the 25/25 must not carry an n = 1 term
silently** — a reader copying the combined expression out of a Confirmed row
would be implementing one observation as if it were twenty-five.

**The four preset variants are LAYER masks, not channel selection.**
[C: hardware, 100/100 variants, 25/25 instruments partitioned]

    TABLE[v] = inst[44 + 2v]
    chanmask = chan ? inst[52] : inst[54]
    layer L enters variant v  iff  (TABLE[v] >> L) & 1  and  (chanmask >> L) & 1

Four presets per instrument, suffixed `00` / `0*` / `*0` / `**` from the two
bits of `v`. An empty variant is a variant whose layer mask selects a layer
the instrument does not populate.

**Zone fields:** root at struct `+170`, key low `+274`, key high `+276`.
[C: hardware, 14–25/25 depending on whether the struct was located by a fixed
base or by relation]

**The filesystem, and it is largely generic.** [C: five discs, cross-checked
against EOS's own import on two]

    directory entry, 26 bytes:
      +1   type      2 and 8 = directory · 3 = instrument · 9 = unidentified
      +2   name      12 chars
      +14  word      instrument: size IN BLOCKS   directory: child count
      +18  long      block pointer

    a directory spans TWO 512-byte blocks = 39 entries
    instrument files are CONTIGUOUS: ptr + size == next ptr across a directory
    every directory page opens with a type-8 ROOT entry whose pointer names the
    real root block, which lists the category folders

The ROOT anchor scan and the entry layout carry **no per-disc constants** and
found 12/8/5/5/3 directory pages across five discs.

**Generic in construction, PARTIALLY validated in fact** — the distinction
matters and its author asked for it explicitly. The reader has **never been
checked against a ground-truth file listing**; its output was cross-checked
against EOS's own import on two banks of two discs; the `+880` plausibility
rate ran **69–93% on three discs**, i.e. entries exist that the parser does
not account for, including an unidentified **type 9**. One disc also needed a
manual MODE1/2352 → 2048-byte sector conversion.

**The audio is in the instrument file, 16-bit BIG-endian PCM.** [C: corpus,
one instrument sampled at three offsets — successive-difference roughness
0.077/0.095/0.186 big-endian against 1.344/1.304/1.325 little-endian, a 17×
separation]. Large files are 96–98% audio; in one bank file sizes run from 8
blocks (4096 bytes, parameters only) to 976 blocks (499 712 bytes).

## [S] Suggested, not confirmed

* **The `+12` boost term is measured at exactly one instrument** — one of 25
  carries `ws[225]`. Whether the term is always 12, or 12 is itself a field,
  is untested. 59 of 853 corpus wavesamples are boosted, so it is testable.
* **The volume table is exercised at 11 of 128 indices.** The other 117 are
  code-only.
* **That EOS's Ensoniq importer drops envelopes, filters, LFO and all cords.**
  Code-only, single reading (`0x7bb90`: two 16-byte memsets and default-voice
  helpers, nothing read from source). Never hardware-checked — **and one dump
  would settle it.**
* **That the 224 spacing among the four small struct bases is the layer-array
  stride.** Four fit; 2544 does not.
* **That 880 is a header-size constant** where it holds.
* **`0x78cc4`'s packed groups are the audio pointer and length.** Not
  implemented, not validated.

## [?] Not known

* **The locator** — see blockers.
* Audio **start, length, sample rate, loop points, channel count** per
  wavesample. The struct's own longs read `0x23004600`, `0x08800000`,
  `0x20000000` — byte-interleaved — so a plain big-endian long probe for the
  known 70 192-byte gap between two located structs matches nothing, and was
  never going to.
* **Velocity low/high offsets.** `+278/+280` were *invented* and scored 0/25.
  Recorded so nobody retries them.
* Type 9 directory entries.

## [B] Blocker — ONE, not two

**The instrument file's LAYOUT: where every wavesample's struct begins, and
where its audio begins and ends.** An earlier draft of this document ranked
"the locator" above "the audio path". That mis-framed it: **they are the same
unknown.** A converter needs struct positions *and* audio extents, and one
structure governs both.

Observed struct bases in one bank: `656, 880, 1104, 1328, 2544, 93200, 97120,
105552, 115280, 129088`. **880 holds on 13 of 25 there and 97 of 97 on a
different disc.** No rule.

> ✅ **RESOLVED 2026-09-21 — there is no rule because the positions are
> LISTED, and the list is found.** It is the 136-entry table in the EPS
> instrument header, values `× 16`. **All ten of these bases appear as table
> values**, and they were derived from the E4XT's own output with no
> reference to the table. See the K2000 Ensoniq section — the K2000's
> importer reads the same table.
>
> **And `880` is explained, not merely superseded.** It held 97/97 on one
> disc and 13/25 on another **because it is the commonest LISTED value**, not
> because it is a constant. *There was never a rule to find.*

**The audio FORMAT is settled and independent of this** — 16-bit big-endian
PCM, in-file. What is missing is where each one starts and stops.

*Unblocked by* tracing the three builders under the file walker — `0x7ad44`,
`0x7ac24`, `0x7a9c4` — and by implementing `0x78cc4`'s packed-group decoder.
Offline work: **no hardware, no material, no authorisation.**

### [S] A chain rule that fit perfectly — and its refutation does not stand either

The natural hypothesis is that a struct is followed by its audio, so the next
struct falls out of the audio length. Decoding `0x78cc4` on the one instrument
where two struct positions are known exactly:

    +240 -> 0    +248 -> 34945    +256 -> 21973    +264 -> 34945
    880 + 288 + 2*34945 = 71058,  align16 -> 71072    <- the second struct, exactly

**A perfect fit, from one observation.** Tested before it was reported, using
the fact that each preset variant may draw a different layer and so a
different wavesample, which yields several hardware-derived struct positions
per instrument:

    consecutive pairs tested   18
    rule connects               1
    rule fails                 17

**Refuted — and then the refutation was withdrawn too.** This is the third
rule in two days that was generated from a single observation, fit that
observation perfectly, and failed everywhere else; it is also the only one
that never left the building, which is the part worth keeping.

> ⚠ **The 1-of-18 no longer stands.** Twelve of those eighteen pairs are
> consecutive *located* structs rather than consecutive structs, so their
> gaps span several extents and no adjacency rule could fit them — see the
> correction under the family search below. **The rule is still not believed**
> (it was derived from its own single datum, which is worth nothing), but it
> is **untested**, not refuted. The distinction matters to anyone deciding
> whether to re-test it once adjacency is knowable.

**What survives, because the failures are not random:**

     40608 vs  40832  (+224)      278240 vs 278464  (+224)
    105104 vs 105552  (+448)       97104 vs  97120  (+16)

Several misses are exactly **224 or 448** — the same 224 that appears among
the small struct bases and matches the layer-array stride. **The
per-wavesample overhead is not a constant 288**: there is further structure
between audio and next struct.

> ⚠ **"So `+248` is plausibly the sample count" is retired.** `0x790ca` puts
> `decode(src+248)` into `struct[+4]`, which the measurements above identify
> as the sample **END** — an absolute position, not a count. The arithmetic
> above happens to use `2 × decode(+248)` with `decode(+240) = 0` on this
> instrument, so a start of zero made an endpoint look like a length. *A
> quantity that equals a count in the one case where the other endpoint is
> zero is not a count.*

### And then the whole FAMILY of such rules was ruled out

[C: search over 18 hardware-derived pairs] Every rule of the form

    next = align( X + overhead + mult * decode(X + field) )
      field in {240, 248, 256, 264}      mult in {1, 2, 4}
      overhead 0..1200 even              align in {1,2,4,8,16,32,256,512}

**Best fit in the entire family: 3 of 18** — *and that denominator was
wrong; see the correction below.*

**No simple arithmetic chain OF THAT FAMILY describes this layout.** The
family conclusion survives for a reason independent of the score: the true
extent is a **difference** of two decoded fields rate-compensated by a third,
and the family only tested *multiples of one field*, so the answer was never
in it. **A closed family is worth more than a closed guess** — but this one
was closed on evidence that was two-thirds invalid.

> ⚠ **CORRECTED 2026-09-21 by its own author: twelve of the eighteen pairs
> were not fair tests.** The pairs are consecutive **LOCATED** structs, not
> consecutive structs — each found by matching what the E4XT reported for one
> variant, so an instrument with five wavesamples of which two were located
> yields a "pair" whose gap spans three extents. **No adjacency rule can fit
> such a pair.** The metric was computed over a population that does not meet
> the metric's precondition, and nothing in the text was false: 3/18 is what
> the script returned. **The defect was in what the 18 were.**

**The asymmetry that makes this reportable, stated by its author:** the
held-out set came back **empty** — on the reference disc every instrument
yields just one locatable struct, because its instruments are single-layer and
all four variants draw the same wavesample. So this is an *unvalidated fit
that happened to fit nothing*. **A negative from such a search is reportable;
a positive would not have been.** Had a rule scored 17 of 18 it could not have
been believed without a second disc, and no second disc exists in usable form.

### Two code increments, and where they point

[C: code read, **not corpus-checked**]

* `0x79024` is the packed-group decoder's **wrapper**, called from the walker
  at `0x7aed2` with the block record and a 32-byte local. So the decoded
  wavesample parameters are a **32-byte structure**, and every consumer
  downstream takes that local rather than the raw groups.
* The walker's running position, `0x7af1c`:

      d7 = fp@(-8) + fp@(12) + 48     ; extent + <accumulator> + 48
      if (d7 & 1) d7 += 1             ; round up to EVEN

  **`+48` and align-2** — which is why the chain rule above failed: it assumed
  288 and align-16, and the firmware uses neither. **Not established:** that
  `fp@(12)` is the previous struct's position. That was assumed, not read.

  > ⚠ **2026-09-21: it was read, and it is NOT that.** `fp@(12)` is the
  > **caller's own local**, passed both by value and by address (`0x7b046`
  > sets `fp@(12) = caller's %fp@(-4)` and also hands `0x7ae84` a pointer to
  > the same local) — **an accumulator the walker reads and writes back**,
  > definitively not the wavesample struct's file offset. **What it
  > accumulates is NOT established**, and nothing is computed downstream of
  > it. The flag above — "assumed, not read" — was
  > correct and was written *before* four separate scores were computed on
  > the assumption anyway. See **Withdrawn: the whole `req` line of enquiry**
  > below. `+48` and align-2 remain `[C]` **as a reading of those
  > instructions**; they are **not** `[C]` as a rule connecting one struct's
  > file offset to the next.

**Where this points, and it is the most useful thing in the section:** the
walker reads a **length at record `+10` and a pointer at record `+32` from a
BLOCK RECORD**, not from the wavesample struct. With the arithmetic family
dead, the likeliest structure is that **positions are LISTED rather than
computed** — a record table the walker indexes. That would explain the base
scatter (`656, 880, 1104, 1328, 2544, …`) with no rule connecting them, which
is exactly what is observed.

**Where the trace stopped:** `0x7ab78` computes the extent and calls `0x49ad4`
three times with shifted operands (`d0 << 28`) — fixed-point arithmetic, so a
rate or ratio rather than a byte count.

### The mechanism, traced end to end — and the arithmetic still open

[C: instruction stream, an external GLM session, `~/temp/GLM_FIRMWARE_RE.md`;
**the structure is verified, the numbers are not**]

    0x7ab78 reads four fields of the decoded 32-byte struct:
      +8  long   start        +12 long   end
      +16 long   rate, 4.28 fixed point  +20 byte flag (zero -> no audio)

    length = struct[+12] - struct[+8]                 ; a DIFFERENCE
    extent = rate-compensated length, via 0x49ad4     ; 64/32 restoring divide

    0x7ac24:  entry[+60] = extent          ; length STORED into the entry
              pos = entry[+28] + 2         ; position READ from the entry
              0x77a48(file, pos, extent | 0x40000000, cb)    ; the bulk read

**So "positions are LISTED rather than computed" is confirmed at instruction
level**, and the `+2` skips a two-byte marker at each audio block's start.

### Withdrawn: the whole `req` line of enquiry

> ⚠ **WITHDRAWN IN FULL 2026-09-21 by eosed, who built it.** Four sections of
> this document scored a candidate rule by computing
>
>     req = next_position − base − 48
>
> and comparing it to a decoded length. **`req` was never the extent.** It was
> built on `fp@(12)` being the struct's file offset, and `fp@(12)` is the
> caller's own local — **an accumulator of unestablished content**. Every
> score that line
> produced — the 0/18 for `decode(264) − decode(256)`, the 6/18 for
> `decode(248) − decode(240)`, the 1.0032 … 1.0360 ratio cluster, and the
> `req − 2×(g1−g0)` residual lead that clustered near 512 — **is a
> non-result**. Not a wrong answer: a comparison between a decoded length and
> a quantity that is not a length.
>
> **The unit of this withdrawal is SCORES**, stated because a retraction
> marker reads as covering everything beneath it. The **field mapping** at
> `0x790ca` is untouched and correct; so is the extent reading at `0x7ab8c`.
> What falls is every number that compared them to `req`. *(A gloss about a
> field survived two earlier withdrawals of this same arithmetic for exactly
> this reason — see the method section.)*
>
> **Do not read this as a contradiction between the code and the data** — an
> earlier version of this section framed it that way, with `0x790ca` saying
> one thing and the pairs saying another. Neither side was measuring what it
> claimed. There is nothing left to reconcile.
>
> **The cluster is withdrawn too, explicitly**, because it is the part a
> reader will want to keep: five ratios inside 1.0032 … 1.0121 is a tight
> cluster and it is *unexplained*, not meaningful. A tight distribution of a
> quantity with no defined meaning is not evidence of anything.

**What the two eliminated candidates left behind is worth more than the
scores were.** Both were chased and both came back clean, and each returned a
fact:

* **The decoder `0x78cc4` is sound.** `0x790be` enforces `g0 ≤ g2` **and**
  `g1 ≥ g3`, and real decoded data satisfies **both inequalities on 17 of 18
  structs before any clamp fires**. A mis-implemented signed shift does not
  satisfy two independent inequalities across values spanning 0 … 123 440.
  **And the reason it holds is the structure:** `g0 … g1` is the OUTER range
  and `g2 … g3` the INNER one. *Which of the two is the sample was settled
  separately and on different evidence — see below; the containment
  inequality cannot carry it, because containment does not say which pair is
  which.*
* **`0x79024`'s source object IS the disc wavesample block.** `0x78c84` is an
  array accessor: `base + index × 288`, the wavesample stride, sitting beside
  `0x78c60` (instrument global) and `0x78c68` (`layer array + i × 224`). So
  `+240 … +264` are offsets into the same 288-byte struct, read at the located
  base, as this document had them.

### [C] What survives, and it is a usable amount

| finding | evidence |
|---|---|
| Positions are **listed, not computed** | `0x7ac24`: `pos = entry[+28] + 2`, written back and passed to the bulk read |
| The block record **names its wavesample directly** | `0x7aebe` reads `record[+1]` and hands it to `0x78c84`, which multiplies by the 288-byte stride |
| The decoded struct is **32 bytes** with known semantics | `0x790ca` tail; `+0/+4` sample start/end, `+8/+12` loop start/end, `+16` a **4-bit** rate, `+20` a mapped flag from source `+238` |
| `+0/+4` is the **SAMPLE** extent and `+8/+12` the **SUBRANGE** | measured, not inferred — two single-voice instruments, coverage 0.97 outer vs 0.83 inner; and one instrument has `g3 < g2`, an inner difference of **−75 samples** |
| `length = struct[+12] − struct[+8]` is therefore the **INNER** length | `0x7ab8c`: `movel %a5@(12),%d7` / `subl %a5@(8),%d7` |
| `+48`, align-2 at `0x7af1c` | instruction reading only — see the warning above |

**Retire "record `+1` maps to an E4-side object kind" wherever it appears**,
including in the external loader trace: a type code is not multiplied by a
struct stride. It is a **wavesample index**, and that is the better fact —
the block record naming its wavesample directly is *independent* support for
the confirmed finding that positions are listed rather than computed. Two
readings of different code arriving at the same structure.

### How the sample/subrange labels were settled — and the anomaly it exposes

**[C: measured on 25 instruments]** The labels `+0/+4` = sample and `+8/+12`
= subrange are **not** read off the containment inequality, which cannot
distinguish them. Two independent measurements do:

* **Single-voice instruments.** Two instruments in the bank report one voice,
  so their audio should fill essentially the whole file:

      file-header   outer   cov    inner   cov   voices
           116592  113164  0.97    96802  0.83        1
           117104  113164  0.97    96802  0.83        1

  The **outer** pair covers 97 %. The inner leaves ~20 000 bytes unaccounted
  with no second wavesample to hold it. Bank-wide medians: **0.35 outer
  against 0.13 inner.**
* **A negative inner difference.** One instrument has `g3 < g2` — an inner
  length of **−75 samples**. A sample extent cannot be negative. And
  `0x790be` orders `g0` against `g2` and `g1` against `g3` but **never `g2`
  against `g3`**, so the firmware would compute the negative value too.

**A discriminator that FAILED, recorded so nobody re-invents it:** "whichever
pair's doubled difference fits inside the instrument file" separates nothing
— **0 of 25 for both pairs.** Neither exceeds its file.

> ### [?] OPEN, and it is a real anomaly rather than a naming artifact
>
> `0x7ab8c` computes `struct[+12] − struct[+8]` — the **inner** pair. So the
> quantity the extent is built from is the **subrange** length, not the
> sample length. **A sample loader that reads only the loop region is a
> strange loader**, and now that the labels are measured this is a property
> of the firmware rather than a mislabelling. It is open.
>
> **And it stops here, deliberately.** It is *not* established that
> `0x7ab78`'s output is the bulk read size: `0x7ac24` stores **a** length at
> `entry[+60]` and passes **an** extent to `0x77a48`, and that these are the
> same value is **assumed, not read**. So the anomaly may be "the loader
> reads only the subrange" or "the rate-compensated subrange length is used
> for something else and the bulk read is sized elsewhere". **Nothing
> downstream of that gets computed until someone reads it** — the
> flagged-assumption rule applied forward rather than backward, on its first
> opportunity, by the session that wrote it.

### The blocker, restated, and it moved the wrong way

The extent handed to the bulk read is still unknown, and the path to it is
now **longer** than this document claimed yesterday, not shorter: the rate is
a 4-bit field whose scale is unidentified, and the one quantity that looked
like a check on it was never a length.

**The next step is unchanged in name and different in kind:** locate **every**
struct in one instrument, not only the ones a variant happens to name. Before
that, adjacency is not knowable, and *nothing* computed from consecutive
located bases tests anything — which is the lesson of this whole section.

`0x7ad44` and `0x7a9c4` remain untraced.

---

# EOS 4.7 (E4XT) — Roland S-7xx → E4B

**No longer the thinnest of the six.** A hardware import ran on 2026-09-21;
the record base is solved and the velocity mapping is measured.

## [C] Confirmed

Module bounds, 18 function entries, and the Performance/Patch/Partial/Sample
hierarchy. The header builder is at `0x1713b0` and the zone builder at
`0x171434`. EOS's disc sniffer is a full `strcmp` where the K2000 does a
three-byte compare.

### [C: panel photograph] The three levels, and what each side calls them

**Read this before quoting any count on this path.** The two sides use the
same words for different levels, and an entire session's work was sized at
the wrong one because of it:

| EOS / E4XT says | Roland calls it | our models |
|---|---|---|
| **Folder** (`F065`) | **Volume** | the disc-level container |
| **Bank** (`B123`) | **Performance** | what a single `Load` acts on |
| **preset** | **Patch** | one playable program |

**The E4XT's browser lists FOLDERS at its top level**, so "the bank I
loaded" and "the bank in the object graph" are not the same object.
**None of these three words appears in the ISO or in the traced firmware
strings** — they exist only on the screen.

**Display indices are 1-based; internal ids are 0-based.** The performance
indexed internally as 122 displays as `B123`.

### [C: hardware, 2026-09-21] The source base — and it was the same shape as Ensoniq's

The Roland source offsets **are not file offsets**: every one below 16 lands
inside the record's own name. They are offsets into a **16-byte sub-record**:

    partial record   0x1D5800 + (id − 1) * 128
    sub-records      +16 + k * 16          one per E4 velocity zone
        +7  vlow     +8  vlowfade     +9  vhigh     +10  vhighfade

**The documented table was right all along and addressed from the wrong
origin** — which is the third time in two days that a correct table sat
behind a wrong base, after Ensoniq's 880 and the located-pair denominator.

**How it was found, because the method transfers.** One imported preset had
**overlapping** velocity zones where every other preset in the bank was
contiguous — 5–6 units of overlap, fade 7, against fade 0 everywhere else.
Searching the whole partial region for a record containing all three of its
split points matched **13 of 2880** records, at offsets 25, 41, 57: stride
16, and `25 = 16 + 9`, exactly where the table places velocity high.

> **A single preset with non-default values did what a whole bank of defaults
> could not.** The bank was picked for measured parameter variation, and the
> one preset that actually varied is the one that solved it. **A corpus of
> defaults is a corpus of one observation repeated** — the same shape as
> counting rows instead of distinct things, and here it paid rather than cost.

### [C: hardware, 384/384] The velocity mapping — with its strength column

    384 comparisons, 384 match, 0 mismatch

| field | distinct values | strength |
|---|---|---|
| `vlow` | 10 | **strong** |
| `vhigh` | 9 | **strong** |
| `vlowfade` | 2 (0 and 7) | *weak* |
| `vhighfade` | 2 (0 and 7) | *weak* |

**A bare 384/384 overstates this and the column is why it is reported with
one.** The two fade rows rest on two values each; what they have going for
them is that **7 appears at exactly the internal boundaries and 0 at the
outer edges**, which a wrong offset does not reproduce. The partial is
located **by name**, independently of the mapping under test, so only the
offsets are being tested.

### ~~Volume-level import loses material~~ WITHDRAWN — nothing is lost

> ⚠ **RETRACTED 2026-09-21, hours after it was written. It was never a
> firmware behaviour, and the word "silently" was wrong twice over.**
>
> The observation was real — a 3-performance volume gives **2 presets**
> loaded as a volume and **10** loaded performance-by-performance, with
> 117/128 MB sample RAM and 99 % of preset memory free. **The interpretation
> was wrong: nothing is discarded.**
>
> **THERE IS NO VOLUME-LEVEL IMPORT.** The retracted finding described an
> operation that does not exist. From a photograph of the panel:
>
>     Drive:  D7 <cd-rom>
>     Folder: F065 <name>        <- the Roland VOLUME
>     Bank:   B123 <name>        <- the Roland PERFORMANCE  (a selector)
>     [Cancel]      [Merge]      [Load]
>
> **`Bank` is a chooser, pre-filled with the first entry, and `Load` acts on
> the selected bank.** There are two routes to the same operation — set
> `Bank` in this dialogue, or navigate into the folder and pick the bank
> directly. **Every load is bank-level.** There was never a wider scope to be
> narrowed from, so "a narrower scope than intended" and "the machine
> announces the scope" are *both* too generous to the original claim.
>
> Confirmed by name: performance 122 lists exactly `E-Guitar 1`,
> `E-Guitar 2` — exactly the two presets that appeared — and the union of
> all three performances is the ten.
>
> **Do NOT carry "converting volume-by-volume loses material invisibly" into
> any scope statement.** It was written here as something we owed users. It is
> false, and the opposite is true: the behaviour is documented by the
> instrument's own UI at the moment it happens.
>
> ⚠ **And it survived the phrase sweeps of this file, twice, in wordings
> the sweeps did not contain** — as *"establish EOS's volume-vs-performance
> selection rule, which silently drops most of a volume's presets"* in the
> next-steps list, and as *"the one live unknown"* in this section's own
> blocker paragraph, **three paragraphs below the retraction**. Sweeps for
> *"volume-by-volume"* and *"silently yields"* both returned clean, and the
> second instance was found only by sweeping the SUBJECT.
>
> **A retracted claim restated in synonyms is invisible to a phrase sweep**,
> which is the limit of the unwrap rule recorded in the method section:
> unwrapping fixes line breaks, not vocabulary. Sweep for the
> CLAIM's subject — here, every mention of volumes and presets in the same
> sentence — not for the sentence that stated it.
>
> **Two failure modes, and the second is the one to keep.**
>
> 1. **An off-by-one that excluded the right answer instead of producing a
>    wrong one.** A performance's patch-id list resolved **1-based when it is
>    0-based** made the two loaded presets appear to come from two *different*
>    performances — which no "one bank from the folder" rule can explain. **So
>    the correct explanation looked refuted before it was raised.** An
>    off-by-one that produces a wrong value gets caught when something
>    downstream disagrees; this one agreed with everything it touched.
> 2. **THE DISPLAY CARRIES VOCABULARY THAT THE DATA DOES NOT**, and that is
>    what made a whole session's worth of work talk past itself. `Folder`,
>    `Bank` and `preset` appear **neither in the ISO nor in the traced
>    firmware strings** — they are the operator's names for the objects. The
>    browser's top list shows **folders**, so *"the bank I loaded"* and
>    *"the bank in the object graph"* were two different levels for the
>    entire session: work sized in patches, patch counts quoted as bank
>    sizes, and a defect read into the gap. **Without the screen's
>    vocabulary two sessions cannot agree on what LEVEL a question is
>    about** — and no amount of disassembly supplies it.
>
>    **And the panel had the off-by-one on it the whole time:** the
>    performance indexed internally as 122 displays as **B123**. Internal
>    0-based, display 1-based, legible without a debugger.
>
> **And the disagreement that should have been the signal.** This project read
> the same disc and found `E-Guitar 1` to be a single patch in a group holding
> far more than two, said so, and stopped rather than guess at the other
> session's structures. **Two sessions reading the same bytes to different
> conclusions is evidence about the readers, not noise to route around.**

## [S] Suggested, not confirmed

All code-and-corpus, **zero hardware**:

* `transpose = src[24] * 12` — an octave count becoming semitones,
  **unclamped**. ⚠ **`src` is not the partial record and not the sub-record.**
  At partial `+24` the values are `0` on 2866 of 2880 and `25` on the other
  14 (`25 × 12` = 300 semitones); at sub-record `+8` they run 0 … 127. **A
  third structure, unidentified** — the constraint is now recorded so the
  next attempt does not re-test these two.
* ~~`fine tune = (partial[6] * 64 + 32) / 100`~~ → **`[C]` and the offset is
  into the SUB-RECORD.** See the corpus check below.
* ~~`pan = clamp(partial[4] * 2, −64, +63)`~~ → **`[C]` and the offset is into
  the SUB-RECORD.** See below. The **forced to 0** arm when
  `(sample[58] >> 1) & 3 == 3` is untouched and stays `[S]` — `+58` is beyond
  the 48-byte sample record, so that source is a third structure and is not
  identified.
### [C: corpus, 26 925 zones on SEVEN discs] O8 — pan and fine tune, rebased

**The `[S]` rows above named `partial[4]` and `partial[6]`. Both offsets land
inside the record's NAME** — the partial record opens with a 4-byte tag and a
12-byte name, so bytes 4 and 6 are ASCII. Read that way across CD 2 they give
values 32 … 122, all positive, never in a pan or cents range.

**They are offsets into the 16-byte SUB-RECORD** — the same rebasing that was
found for the velocity quartet, and it had not been applied to these two.
Read at `+16 + k × 16`:

| | CD 1 (4004 partials) | CD 2 (2880 partials) |
|---|---|---|
| `sub[4]` signed, in ±32 | **4004 / 4004** | **2880 / 2880** |
| … at the `−32` / `+32` rails | both hit exactly | both hit exactly |
| `sub[6]` signed, in ±50 | **4004 / 4004** | **2880 / 2880** |
| … at the `−50` / `+50` rails | **both hit exactly** | `−50` hit |

**`pan = clamp(sub[4] × 2, −64, +63)`** — `sub[4]` touches both rails and
centre (0) is the modal value on both discs.

> ### ❌ "THE CLAMP NEVER FIRES ON REAL MATERIAL" IS REFUTED — 2026-09-22
>
> ~~`sub[4]` is confined to ±32, so doubling covers the E4's ±64 exactly and
> the clamp never fires on real material.~~
>
> **Measured over 26 925 zones on SEVEN discs** — the other five were sitting
> packed in the same directory and were unpacked on Jan's prompt:
>
> | | |
> |---|---:|
> | zones with `sub[4]` outside ±32 | **822 (3.05 %)** |
> | values | `+33` on 717, `+34` on 105 — **never `−33`** |
> | discs affected | 4 of 7 |
> | examples | `HRP:Harp C4`, `BEL:_Orch Bl B2`, `STR:Solo Tune Up` |
>
> **So the clamp fires, on 822 zones — and that is evidence FOR the formula
> rather than against it.** A clamp the firmware bothers to write that never
> fires would be the suspicious result. The asymmetry fits the E4's own
> asymmetric range: `−32 × 2 = −64` is exactly reachable while `+32 × 2`
> overshoots `+63` by one.
>
> **The claim was true on the two discs it was measured on and false on the
> other five** — the corpus-is-uniform trap, from a corpus that was two
> sevenths of the material sitting in one folder. *`sub[6]` survives the same
> test perfectly: 26 925 / 26 925 inside ±50, both rails reached.*

**`fine tune = (sub[6] × 64 + 32) / 100`** — `sub[6]` is confined to ±50 and
touches both rails on CD 1, which is **Roland's documented ±50 cents**, read
directly off the disc rather than inferred from the arithmetic.

**Both rows move `[S] → [C]`**, and the confirmation is stronger than "the
values fit": a field whose observed extremes land exactly on the rails of the
range its formula assumes is not fitting a range, it is *the* range.

* The zone map carries **both fade pairs and the fine tune** and **discards
  zone volume** — the mirror of the Ensoniq importer, which discards fine tune
  and both fades and converts volume through a table. Neither is the richer
  import across the board.
* **Roland's key-fade pair is written from `patch+13`/`patch+14`** — which
  makes a Roland-sourced bank the only place non-zero values would appear in
  E4B zone-entry bytes `[3]`/`[4]`, a pair this project's 10 142-entry corpus
  has zero everywhere.

  > **`[?]` TESTED HERE AND NOT LOCATED — recorded with its method so the
  > next attempt varies the right thing.** The patch records were found
  > (512-byte stride from `0x155800`: **916** on one disc, **889** on the
  > other) and `+13`/`+14` land inside the 16-byte tag-and-name, the same
  > defect as the partial rows. Rebased by `+16` as the partials were:
  >
  >     +29   TWO values only, 0 or 8   -> a flag bit, not a fade width
  >     +30   0 … 25, mostly zero       -> fade-shaped
  >
  > **One of the pair is binary, so the rebase does not yield a fade PAIR.**
  > A scan of every adjacent pair in the parameter block (`+16 … +80`) for
  > *both* members being fade-shaped on *both* discs returns **nothing**.
  >
  > **What this rests on, since a negative is only as good as its
  > assumptions:** that the patch record is 512 bytes from `0x155800`
  > (verified); that the rebase is `+16` (**assumed** — verified for partial
  > records, not for patch records); that the two bytes are adjacent after
  > rebasing (**assumed**); and that both members must look like fades
  > (**assumed** — a pair could have one member near-constant).
  >
  > **`+30` is the single best fade-shaped field in the record** and is the
  > obvious thing to test first if the rebase turns out to differ.
* ~~**One row flagged as surprising by its own author**: Roland's velocity
  high and its fade appear **crossed** — `partial+9` → zone `7`,
  `partial+10` → zone `6`.~~ **[S] PROBABLY NOT A CROSSING — and the note was
  comparing two different origins.** The instruction order is real; what was
  missing is that the Ensoniq zone builder, traced in the same session,
  writes **relative to a zone pointer that is `zone_base + 2`**. Under that
  convention `zone 7` and `zone 6` are entry bytes **9** and **8**, i.e.
  `hi_vel` and the high fade — the natural mapping, not a crossing.

  **Why it looks crossed either way, and why that is expected:** E-MU nests
  its ranges as `[low, fade, fade, high]` — zone entry `6,7,8,9` for
  velocity, `2,3,4,5` for key, and the voice window does the same
  (`vpar[14]` low, `[15]/[16]` fades, `[17]` high). **Roland stores the same
  four ascending** (`+7, +8, +9, +10`). So a correct importer *must* send the
  source's third field to the destination's fourth slot and its fourth to the
  third. **The descending pair is the transform, not a defect.**

  **And the measurement settles it independently of the convention
  question:** EOS-side `vhigh` matched the Roland source on **384 of 384**
  comparisons. Had `partial+9` gone into a fade byte, `hi_vel` on the E4 side
  would not match at all. *An absolute-entry crossing is refuted by the
  hardware result regardless of which origin the note meant.*

  **Left at `[S]` rather than `[C]` because one thing is genuinely open — and
  it is ours, not theirs:** *which* of entry `[7]`/`[8]` is the LOW fade. Our
  corpus evidence is 36 zones in **mirrored pairs**, which proves the two
  bytes are a crossfade pair and **structurally cannot** say which is which —
  every pair contains both orderings. See `docs/E4B_FORMAT.md` §4.5.
* The stereo path back-patches the *previous* zone at negative offsets and
  **mutates its own input** (`a3@(3) = 127`, `a3@(0,1,2) = 0`).

## [?] Not known

Essentially everything below those structures. **And the source columns are
offsets into what EOS HOLDS, not into the file** — proven for Ensoniq,
assumed here by the same rule.

## [B] Blocker

~~**No Roland import has ever been run on the E4XT.**~~ **CLOSED 2026-09-21 —
it ran.** That was the single biggest gap in this document and it is gone.

**What replaces it is much smaller.** The velocity quartet is measured and
the record base is solved; everything else in the `[S]` list above is still
code-and-corpus, and **2880 partial records on this one disc are now
corpus-checkable** against it. Nothing here needs hardware any more.

~~**The one live unknown that does:** the volume-vs-performance selection
rule above.~~ **WITHDRAWN — no such rule, nothing lost.** See
the retraction earlier in this section: every `Load` is bank-level and the
dialogue names the bank it will load. **Nothing on this path needs hardware
any more.**

---

# Kurzweil K2000 v3.87J — Roland S-7xx → KRZ

**The best-traced conversion law of all six — and on 2026-09-21 it stopped
being the one furthest from usable.** The audio is now located, decoded and
validated; what blocks it is narrower than the path itself: sample **rate**
and **loop points**.

## Frames and templates

    load base 0x100000, file offset = addr - 0x100000
    DUMP offset = file offset + 24           [C: 11 segment tags on a real program]
    layer k at DUMP 48 + 224k                [C: same]
    layer template = 18 tagged segments, sum(1 + size) = 224

**An imported Program is a clone of Program 199** — `movew #199` / `movew
#132` / `jsr 0x1032EA` at `0x1645E2` — plus a short write list. **Every field
the importer does not write keeps Program 199's value**, so the drop list is
decidable by construction. The manual says the same (15-31); this is the code
agreeing with it rather than the manual being taken on trust.

The keymap side clones a **ROM prototype**: `"New Keymap"` at `0x1888E4`,
referenced nine times. A second prototype `"New Sample"` exists at `0x18862A`.

> **[C: read out of the ROM image, twice] There is a THIRD prototype, and its
> name field is WIDER.** `0x188436` carries `"Abcdefghijkl"` — **twelve
> characters, not ten** — and the Roland sample loader clones from it
> (`0x169C20: moveal #0x188436`). Header words, **big-endian as the 68000
> reads them**, name at `addr + 6` in all three:
>
>     addr       raw bytes          words (BE)          name
>     0x188436   98 00 00 58 00 10  9800 0058 0010      "Abcdefghijkl"  (12)
>     0x18862A   94 01 00 AE 00 0E  9401 00AE 000E      "New Sample"    (10)
>     0x1888E4   94 01 00 AE 00 0E  9401 00AE 000E      "New Keymap"    (10)
>
> **Flagged loudly because a name-field width is copied, not re-derived.** An
> external analysis quoted this name as ten characters; anyone building a
> prototype table from that would truncate.
>
> > ⚠ **This project first published the first word byte-swapped** — `0x0098`
> > and `0x0194` — having transcribed `98 00` from a hex dump by reflex.
> > **The error was invisible on words two and three**, whose high byte is
> > zero, so both readings coincide there: two of the three words agreed and
> > the line looked self-consistent. Caught by k2kremote noticing the
> > disagreement on the *one* word that could show it, and **re-derived here
> > from the ROM rather than conceded.** *A byte-order error hides on every
> > field whose high byte is zero — which, in a format full of small values,
> > is most of them.*
**Both are `method = 1`, `entrySize = 1`.**

## [C] Confirmed

**The tuning formula, both terms.** [C: hardware, seven imports]

    tuning = record[+10 + 2z] + (root − 12 − I) × 100          I = key index

The decisive datum is one object: **`−134 cents constant across all 64
entries`** of a pitched patch. A non-zero value that does not vary with key is
key-track cancellation **applied**, which five zeros could never have shown.

**The cancellation is CONDITIONAL, gated by `record[+18 + 2z]`, which comes
from the disc.** [C: **instruction stream** for the offset — the stronger of
the two — plus hardware on both arms and corpus across three discs]

    gate 0  -> cancellation applied   (kits)     many distinct tunings, the ramp
    gate 8  -> cancellation skipped   (pitched)  exactly one distinct tuning

Corpus prevalence, **filtered to zone slots that carry a sample** (12 521 of
32 212 slots — the unfiltered count was the author's own first error):
**99.6% / 2% / 0%** across the three discs, tracking the material — an
all-pitched string library asks for cancellation on none of its zones.

**The two conventions are OPPOSITE and this is a porting trap.** Roland's
`8` means *do track*; this project's MPC `<KeyTrack>False</KeyTrack>` means
*do not track*, so the flag SET means cancel. Both measured.

**`lyr[8]` bit 5 is the stereo marker.** [C: hardware, seven imports — `0x24`
on four stereo, `0x04` on three mono; corpus split 86.4% all-stereo vs 0.7%
all-mono; and the `bset #5` at `0x16ADAA` sits after the second-keymap write,
i.e. inside the stereo branch]

**±7 pan is a within-layer pair.** [C: hardware] `0x53` body[2] high nibble
= 7 and body[13] bits 4–7 = 9 (= −7) on stereo imports; 0/0 on mono.

**Keymap entries are method `0x17`, six bytes** — so the header *implies*
796 = 28 + 128×6. [C: hardware, the imported objects themselves] **The objects
usually are not that size**: see the truncation item below, which is the same
measurement read the other way round.

**The velocity mark.** [C: **two independent derivations that never saw each
other** — this project's panel diff on a K2000R in June, and `0x164C66`…
`0x164CF0` read out of the ROM in September]

    (lo << 3) | (7 − hi)        two 0..7 dynamic marks, hi stored inverted

**There are TWO loops and they must not be fused.** [C: instruction stream]

    ZONE loop -- count differs by importer
      Roland  cmpiw #4,%a4@        at 0x16A452   four zones per 128-byte patch
      Akai    cmpiw #8,%sp@(528)   five occurrences, bltw back to 0x1641BC

    KEY loop -- 88 iterations on BOTH arms, one per key
      Roland  cmpiw #88,%sp@(250)  at 0x16AB28
      Akai    cmpiw #88,%sp@(526)  at 0x1640B0 and 0x1641F4

**4 and 8 count zones, not keys.** The keymap fill is the separate 88-key
loop, which is why the fill index is `I = 9 + key` and **not**
`9 + zone_counter` — the retraction that cost two sessions an evening only has
force while the two loops are kept apart. Reading 4 or 8 as a key count would
build four-entry keymaps.

The 88-key fill is also why imported kits carry dangling entries at keys
12–20.

**The Roland disc directory layout.** [C: corpus, five classes × three discs —
every record's class tag correct, counts equal to the header's own, terminator
empty]

    sector 0, LITTLE-endian counts:  0x114 volumes · 0x116 performances
                                     0x118 patches · 0x11A partials · 0x11C samples
    directory bases (ROM jump table 0x169960), records at base + 0x200, 32 bytes:
      0x000A0600 volume · 0x000A1600 performance · 0x000A5600 patch
      0x000AD600 partial (measured, no ROM entry) · 0x000CD600 sample
    record: +0x00 name(16) · +0x10 class tag 0x40..0x44 · +0x12 id/fwd link
            +0x14 back link · +0x16 index · +0x1E size

The loader opens the pseudo-file **`ROLAND.S`** and absolute-seeks — that name
is on no Roland disc anywhere; it is how the K2000's file layer is asked for
the raw volume.

**The patch record.** 128 bytes = 16 bytes of name + **four 16-byte zone
sub-records**; the gate is `sub[2]`; the sample reference is `record[+2 + 2z]`
feeding `find_object(134, ·)`; and the tuning base is

    record[+10 + 2z] = coarse * 100 + fine + record[+38]
    record[+38]        a per-record cents base

**The `+38` term is not optional, and the disc proves it.** `BA1:MC-202` is
on CD 2 at `0x1E1600` (partial index 368), and its one used zone reads

    zone 0:  3a 02 08 7f 00 00 00 01 00 7f 00 00 00 7f 7f ff
             sub[2] gate = 8  (pitched, matching the import exactly)
             sub[5] coarse = 0     sub[6] fine = 0

so `coarse × 100 + fine = 0` and **the entire −134 comes from `+38`.**
[C: disc read] A formula without that term is right only where `+38` is zero —
and it is precisely the kind of term that survives compression by looking
redundant: usually zero, occasionally decisive. (`sub[5]` is 0 in 99% of
zones, which is presumably how the whole cluster came to feel skippable.)

**Object type numbering.** [C: two readings] The K2000's RAM types are this
project's file types **plus 96**: 132 Program, 133 Keymap, **134 Sample**. And
`sample_body[12]` is `Soundfilehead.rootkey` — verified on real objects
(`body[12]` = 48/60/72 with `body[13]` = `0x70`, the playable-RAM flag).

**Imported keymaps are SHORTER than their own header declares.** [C: hardware,
seven imports] Every one declares `entriesPerVel = 127`, `entrySize = 6` —
796 bytes — and nine of thirteen objects are 156, 412 or 668 bytes. **This is
not a defect**: in a format whose object size is authoritative, the header
declares a layout and not an extent. It *is* a trap for a reader — and it was
one here, fixed on this branch.

**Dangling entries are harmless.** [C: hardware, scripted and by hand]
Entries 0–8 **of the two kit keymaps examined** carry an invalid sample id
(16582), i.e. keys 12–20 inside the layer's own declared range point at an
object that does not exist. **The importer caps object ids at 999**, so 16582
cannot be a stale or off-by-N reference — it is junk, which is what rules out
the boundary-copy reading. Played: **silent, no hang**, with a 2–3 s-class
SysEx poll running against that state throughout. Likely general for kits;
**unverified for the pitched imports.**

## [S] Suggested, not confirmed

* **One implementation serves both S-770 and S-750.** The evidence is
  *absence*: byte 6 of sector 0 — the model digit — is deliberately not
  tested, the only `cmpib #'7'` in the image is the sniffer, and there is no
  `cmpib #'5'` anywhere. **Absence of a compare is weaker than a compare.**
  Needs an S-750 disc.
* ~~**The Sample directory's size at `+0x1E` is scaled by 9 × 1024**
  (`0x169A3E`). Code-only, never checked against data, and 9 KB granularity is
  odd enough not to build on.~~ **PROMOTED 2026-09-21: the 9 × 1024 is real**,
  appearing at two independent sites — this scale and the data stride at
  `0x169BC4` — and now validated against 4128 directory entries. **The caveat
  is retired**; see the audio section below.
* **Bit 5 as an importer fingerprint** — set by the importer, not by
  hand-authored programs. Consistent with both datasets, demonstrated by
  neither.
* **The Akai low-velocity mark rounds UP** (`if src[89] & 0x0F: lo += 1`,
  then clamped to 7 and to `hi`). If that lands a boundary on a mark's
  defining velocity, **the K2000's own importer ships the silent-layer dropout
  this project measured and deliberately avoids** by rounding down. Inferred
  from the instruction, never tested — the cheapest remaining hardware test if
  an AKAI disc ever reaches the machine.
* **The ±7 copies**: `0x53` is the last segment of a layer, so copying 16
  bytes on from `body[2]`/`body[13]` lands in `lyr[2]`/`lyr[13]` of the
  **following** layer. Either "same index, next segment" or an off-by-one-
  segment bug in the importer. Not implemented anywhere on that reading.

## [C] The sample AUDIO — located, decoded and validated

**The single largest gap on this path closed on 2026-09-21.** Two disc areas,
both read out of the ROM's `addil` constants and both fitting the family that
ends in `0x5800` — **`0x5600` as first reported; corrected by measurement, see
the warning below:**

| area | contents |
|---|---|
| **`0x255800`** | sample parameters, **48 bytes** per entry |
| **`0x2B5800`** | sample **audio** |

    offset(n) = 0x2B5800 + (sum of size[0..n-1]) * 9216
    extent(n) = size[n] * 9216, zero-padded after the audio ends

**The index is a running total, not the ordinal** — and it was caught by
**refutation rather than measurement**: consecutive samples of 27 and 25
blocks cannot be one block apart. Validated twice over: the envelope tiles
with zero padding exactly where the model predicts, and **4128 entries sum to
56 125 blocks = 517 248 000 bytes, ending 1.79 MB inside a 521 MB image.**

**Encoding — measured, not assumed.** 16-bit signed **LITTLE-endian**:
smoothness ratio **0.0163** against **0.3058** for big-endian. A 20×
separation, not a marginal call. *(Note the contrast with the Ensoniq path,
which is big-endian — neither was assumed from the other.)*

**Stereo pairing** is adjacent entries carrying `L`/`R` name suffixes. The
counts are **deliberately recorded as unequal — 756 vs 716** — so that nobody
pairs by suffix alone and assumes a clean partition.

**Root key** is decoded at `+0x2D`, verified on three samples against their
own names.

> ### ⚠ CORRECTED 2026-09-21 by direct measurement: BOTH BASE CONSTANTS ARE 0x200 LOW
>
> Measured on the disc image, not traced: **`0x255600` and `0x2B5600` are both
> inside runs of `0xFF`.** Data begins exactly **512 bytes later** in both
> cases. The correct bases are
>
>     sample parameter records   0x255800     (48 bytes each)
>     sample audio               0x2B5800
>
> and the family is *…5800*, which is what the Ensoniq-side partial base
> `0x1D5800` already used.
>
> **Every total in the validation below is reproduced exactly** — 4128
> records, 56 125 blocks, 517 248 000 bytes, ending 1 827 840 bytes inside the
> image — **because a constant base offset cancels out of a total.** What does
> not cancel is every individual sample offset: each would start 512 bytes
> early, i.e. **256 samples inside the previous sample's ZERO PADDING.** At
> 44.1 kHz that is 5.8 ms of silence prepended to every sample — inaudible,
> and it hides inside the very padding the model was validated against.
>
> **A constant offset is invisible to a sum, and a zero-padded format hides it
> from a listening test.** Recorded as a method note; it is the same shape as
> a metric that cannot distinguish its hypotheses.

> ### ⚠ And the "constant deltas" ruling is half right — on 4128 records
>
> The three pointers were ruled out as loop points because their deltas were
> constant across *three* samples. Over the whole directory:
>
> | pair | constant? |
> |---|---|
> | `+32 − +28` | **1024 on 4122 of 4128** — effectively constant |
> | `+28 − +24` | **2560 on only 1316 of 4128** — it varies widely |
>
> **So the stated reason does not hold for the second pair.** The conclusion
> survives on a different test: `+28 − +24` **exceeds the sample's own byte
> length on 2514 of 4128 records**, which no loop length can do. *A
> conclusion reached for a reason that fails on the full population is worth
> re-deriving even when it turns out to be right.*

### [C: measured here, 4128 records] The sample record, and what is NOT in it

Reproduced independently against the corrected base: **48-byte records**,
`size` = LE16 at **`+42`** in 9216-byte blocks, **root key at `+45`** (`0x3c`
= 60 is the most common value, as a default root should be), stereo pairing by
an `L`/`R` suffix at name offset `+15`, audio little-endian 16-bit with
zero-padded tails.

**Sample RATE: `[C]` CLOSED at 44.1 kHz — two independent measurements.**
Autocorrelating a mid-sample window against the record's own root key gives
implied rates **44 292 … 44 965** here; the apparent 22 k readings are the
autocorrelation locking to the octave, and doubling the period returns 44.4 k.

**k2kremote measured it separately (`1b72d7b`) and their evidence is the
stronger of the two**, because it does not depend on any single period being
right: across seven choir entries with ascending semitone labels, the
**periods track the labels** at ratios 1.198 / 1.181 / 1.179 / 1.198 / 1.186 /
1.200 against a true semitone of 1.189. **A wrong root field or a wrong rate
cannot fake that across seven entries** — one bad period can look like a
plausible rate; a consistent *sequence* cannot. Neither measurement needed
firmware or hardware.

> # ⚠ THE `[C-neg]` BELOW IS REFUTED. THE LOOP POINTS **ARE** IN THIS RECORD.
>
> **Retracted 2026-09-21 by an external session (KIMIK3), verified here on
> both discs.** The fields are **24-bit little-endian at group base + 1, in
> SAMPLES** — not 32-bit at the group base, in bytes. Our test read the wrong
> width at the wrong alignment against the wrong unit, and the `[C-neg]` is
> an artefact of that, not a property of the format.
>
>     sampleStart LE24 at +17      (bytes +17..+19) — see the naming note
>     loopStart   LE24 at +21      SIGNED — negative is a no-loop sentinel
>     loopEnd     LE24 at +25
>     loop mode   byte at +36
>     rate code   byte at +44, low nibble
>     root key    byte at +45
>
> **Cross-checked against this project's own KRZ sample-object layout**
> (`docs/KRZ_FORMAT.md` §3.1: a 12-byte `KSample` header then the
> `Soundfilehead`), the destinations the trace names land exactly:
>
> | trace says | `body[n] − 12` | our field |
> |---|---|---|
> | `body[12]` root key | `Soundfilehead+0` | `rootkey` ✓ |
> | `body[20]` "altStart" | `Soundfilehead+8` | **`sampleStart`** — *not* the alt |
> | `body[24]` defaulted | `Soundfilehead+12` | `altSampleStart` ✓ |
> | `body[28]` loopStart | `Soundfilehead+16` | `sampleLoopStart` ✓ |
> | `body[32]` loopEnd | `Soundfilehead+20` | `sampleEnd` ✓ — our doc already records that for a looped sample this **is** the loop end |
>
> **Five destinations, five matches, one relabelled:** the field at Roland
> `+17` fills `sampleStart`, not an alt start. The trace's own reference to
> `body[24]` is the alt, and the two were conflated in the table this project
> first copied.
>
> **Verified on disc, both Roland disc images:**
>
> | | records | `alt ≤ loopStart < loopEnd ≤ length` |
> |---|---|---|
> | CD 1 | 5761 | **5473 (95.0 %)** |
> | CD 2 | 4128 | **4109 (99.5 %)** |
>
> The CD 2 outliers are two legitimate shapes, not violations: a **negative
> `loopStart`** (every one on a `mode = 2` one-shot — the no-loop sentinel),
> and **`altStart > loopStart` with `loopStart = 0`**, where the attack-skip
> and the body loop are independent parameters.
>
> **And the rate is now NAMED by a field rather than only measured.** The
> loader's jump table at `0x169D90` on `record[+44] & 15`, **read out of the
> ROM** (`cmpiw #5` / `bhis`, table words at `0x169DA8`):
>
>     0 -> 48000    1 -> 44100    2 -> 24000
>     3 -> 22050    4 -> 30000    5 -> 15000     6..15 -> 44100 (default)
>
> ⚠ **`5+ → 44100` was wrong.** Code 5 is a distinct arm at `0x169DD4`
> reached by table entry `002c`; the default starts at **6**. **A sixth rate
> nobody had** — and the one arm a pitch check could never have found, since
> 15 kHz material would have been swept into whatever bucket the estimator
> produced.
>
> **Tested here by autocorrelation against each record's own root key — and
> only TWO of the five arms are confirmed.**
>
> **BOTH sessions' figures are filtered, and the second one's filter is not
> uniform across the codes it compares.** This project hand-checked 14 per
> code at `corr ≥ 0.85` with pitched roots, and reported the count without
> the filter. k2kremote then measured **551 of 2064 sampled records** —
> dropping 1489 for `size < 20 blocks`, an arbitrary analysis-window
> threshold — and reported percentages without stating any of it.
>
> | code | table | sampled | measured | **retention** | on-grid |
> |---|---|---:|---:|---:|---:|
> | 0 | 48000 | 768 | 210 | **27.3 %** | 50.5 % |
> | **1** | 44100 | 797 | 222 | **27.9 %** | **79.3 %** |
> | 4 | 30000 | 130 | 75 | 57.7 % | 68.0 % |
> | 2 | 24000 | 206 | 27 | **13.1 %** | 48.1 % |
> | 3 | 22050 | 134 | 17 | **12.7 %** | 58.8 % |
>
> **A fourfold spread in retention across the codes being ranked against each
> other.** Each percentage is correct about its own survivors; the
> *comparison* between them is not.
>
> **What actually survives, and it is one arm rather than two:**
>
> * **Code 1 is MEASURED.** Codes 0 and 1 retain almost identically — 27.3 %
>   against 27.9 % — so that one comparison *is* like-for-like, and code 1's
>   79.3 % genuinely beats code 0's 50.5 %.
> * **Code 4 is PREDICTED, and that is a different and stronger kind of
>   evidence than a percentage.** Its 68 % sits on 57.7 % retention and is
>   not comparable to either. What supports it is that **30 000 Hz was named
>   in advance, from a jump table, before any audio was touched** — which no
>   retention artefact can manufacture.
> * **Codes 0, 2 and 3 are UNMEASURED.** 2 and 3 rest on ~13 % retention;
>   calling them "scattered" implied they had been tested.
>
> **So: one arm measured, one arm predicted, three unmeasured.**
>
> **Code 4 = 30 000 Hz is the load-bearing arm.** An odd rate, named by the
> jump table before any audio was touched, landing at 1.00 on every sampled
> record. Together with code 1 that is strong evidence the table is *real*.
>
> > ⚠ **RETRACTED, an hour after writing it: "the 2.00 ratios are the
> > autocorrelation's octave ambiguity".** That was an *interpretation*
> > presented as a measurement, and it is false for most of the records it
> > was applied to. **Autocorrelation locks onto MULTIPLES of the true
> > period, so if the estimator had picked the octave below, the half-lag
> > would also correlate strongly.** Tested: on the ratio-2.00 records the
> > half-lag correlation is mostly **negative or near zero** (−0.98, −0.92,
> > −0.86, −0.66, −0.61, +0.11 …). **`P` really is the period.** Only three
> > records (`SY Glas2/3/4`, at 0.80 / 0.94 / 0.99) are genuine octave locks.
> >
> > **And the earlier claim that "every measurement lands on exactly 1.00 or
> > 2.00" is also wrong** — code 0 is scattered on 9 of 14, and on 104 of 210
> > in the full population.
> >
> > **The discriminator generalises.** k2kremote re-ran it on **109**
> > ratio-2.00 records: half-lag correlation ≤ 0 on 53, between 0 and 0.5 on
> > 34 — **87 of 109 (80 %) are not octave locks** — and ≥ 0.5 on 22, median
> > **+0.044**. Four records in five, `P` really is the period.
>
> ### Re-measured under ONE uniform rule — three codes fail differently
>
> The earlier tables compared codes under filters that retained them at
> 12.7 % … 57.7 %. Re-run with a single acceptance rule applied identically
> to every code — ≥ 1 block of audio, pitched root 33…75, peak-to-peak
> ≥ 1500, a **2048-sample** window (fits inside one block, so short samples
> are not excluded), lags 20…700, correlation ≥ 0.80 — **and rejecting any
> record whose best lag lands on a search boundary**, which is the estimator
> failing rather than measuring:
>
> | code | Hz | eligible | est. floor | measured | retention | ~1.00 | ~2.00 | scatter | median implied |
> |---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
> | **1** | 44100 | 45 | **0** | 26 | 57.8 % | **26** | 0 | 0 | 44 647 |
> | **4** | 30000 | 45 | **0** | 30 | 66.7 % | **30** | 0 | 0 | 30 062 |
> | 3 | 22050 | 45 | 5 | 34 | 75.6 % | 0 | **34** | 0 | **44 005** |
> | 2 | 24000 | 45 | 5 | 35 | 77.8 % | 13 | 13 | 9 | 47 729 |
> | 0 | 48000 | 45 | **31** | 8 | 17.8 % | 0 | 2 | 6 | 193 603 |
>
> **`[S]` codes 1 and 4 — downgraded from `[C]`, see the octave-pair note
> below.** Perfect agreement on the ROOT reference, with **zero
> estimator-boundary failures**, so the *periods* are sound. What is not
> sound is the reference: on the NAME reference the same records give 22 246
> and 15 043 — which are codes 3 and 5, also table values.
>
> ### ⚠ AND THE WHOLE METHOD IS RETIRED — the codes come in OCTAVE PAIRS
>
> **The "code 3 contradicts the table" finding above is WITHDRAWN**, twenty
> minutes after it was written, and what replaces it condemns the instrument
> rather than any one result.
>
> **The ROM read is correct** — `0x169DC4` is `movel #22050` at jump-table
> index 3, unambiguous. So the contradiction had to be on the disc side, and
> it is: the **root-key field and the sample NAME disagree**, often by
> exactly twelve semitones. Measuring "implied rate = period ×
> frequency-of-reference" therefore gives an answer that **differs by exactly
> a factor of two depending on which reference you pick**, and nothing on the
> disc says which is right.
>
> **And the offset is NOT uniform, which removes the last repair.** Measured
> over every CD 2 record whose name carries a note — two independent counts,
> which agree on the shape and not on the numbers:
>
> | `root − name` | this project | k2kremote |
> |---|---:|---:|
> | `+0` | 599 (46.1 %) | 397 |
> | `+12` | 427 (32.9 %) | 413 |
> | `+1` | 94 (7.2 %) | 79 |
> | `+24`, `+48` | 55 | — |
>
> *(The counts differ because the two sessions extract the note from the name
> differently; neither is adopted over the other, and the split is the point.
> This project's parser is additionally unreliable on CD 1 — only 25 records
> parse, with implausible deltas — so **CD 1 is not evidence here either
> way**.)*
>
> **A uniform `+12` could have been corrected wholesale. A split cannot**, so
> there is no post-hoc repair.
>
> > ⚠ **Do not quote a ratio for the split. It is not a measurable
> > quantity.** An earlier version of this section said code 1 splits
> > 274 / 271 — *"a coin flip on the very code that carried both sessions'
> > `[C]`"*. k2kremote's parser gives 299 / 156 on the same code: **two to
> > one, not even.** Neither of us would adjudicate the other's extractor, so
> > this project ran four defensible ones over the same records:
> >
> >     note matched anywhere in the name      +12  50.3 %   +0  49.7 %
> >     note must follow a separator           +12  54.0 %   +0  46.0 %
> >     as above, without the ES alias         +12  49.5 %   +0  50.5 %
> >     note must be the trailing token        +12   3.7 %   +0  96.3 %
> >
> > **The same records, four reasonable readings, and the answer spans 3.7 %
> > to 54 %.** k2kremote then ran five extractors of their own lineage and
> > got **3.5 % to 65.7 %** — and the 65.7 % they had challenged this project
> > with is **the highest of their own five**, chosen before the others
> > existed because it was the first regex that worked. The ratio is
> > determined by the parser, not by the disc.
> >
> > **The two lineages agree at exactly one point** — the strictest reading,
> > *"the note must be the trailing token"*, at **3.7 %** and **3.5 %** — and
> > diverge as they loosen. Two readings were offered for that: the loose
> > variants admit names that do not really carry a note, **or** both strict
> > variants select the same small skewed subset. **Tested within the hour.
> > It is the second, and the mechanism is total:**
> >
> > | | whole disc | strict subset |
> > |---|---:|---:|
> > | name ends `L` | 18.3 % | **0.0 %** |
> > | name ends `R` | 17.3 % | **0.0 %** |
> > | loop mode 0 | 47.0 % | 65.1 % |
> > | loop mode 2 | 51.1 % | 33.5 % |
> > | rate code 5 | 1.4 % | **0.0 %** |
> >
> > **A stereo sample's name ends in `L` or `R`, so the note can never be its
> > trailing token.** The strict rule and the stereo marker compete for the
> > same character position, so the parser excludes every stereo sample **by
> > construction** — **0 of 1472** pass, 35.7 % of the disc, taking the whole
> > `0x53` pan-pair population with it. Code 5 disappears entirely and the
> > loop modes invert.
> >
> > **So the convergence was an artefact of a shared exclusion neither author
> > chose or knew about**, and 3.5 % is not the answer either.
> >
> > **The conclusion is completely insensitive to this**, and that is worth
> > stating so nobody thinks the withdrawal is back in play: the answer set
> > is three octave pairs, which kills the method *however* the references
> > split. **The "neither `[C]` was better than chance" sentence is
> > withdrawn** — it was a quantitative claim resting on one parser, and the
> > quantity does not exist.
>
> **And the rate table is three exact octave pairs:**
>
>     code 0  48000  =  2 × code 2  24000
>     code 1  44100  =  2 × code 3  22050
>     code 4  30000  =  2 × code 5  15000
>
> **So every code's octave partner is also in the table.** A pitch-based
> method with a one-octave reference ambiguity maps each code exactly onto
> its partner and **cannot distinguish them, ever.** Using the root reference
> code 3 "reads as" 44100 — which is code 1. Using the name reference code 3
> reads as **22 025**, matching its own arm. Both are internally consistent;
> the disc does not break the tie.
>
> **What this costs:** codes 1 and 4 were reported `[C]` on the root
> reference, and code 4's name reference gives **15 043 ≈ 15 000**, which is
> code 5 — also a table value. **Their confirmations have the same ambiguity
> and are downgraded with code 3's contradiction.** The two results were not
> independent of each other; they shared a reference choice that was never
> stated as one.
>
> **This cannot be resolved from the disc.** It needs the instrument, or a
> recording of known absolute pitch. *A measurement that can only ever return
> "X or 2X" is not a measurement of X.*
>
> **`[?]` code 2 — genuinely mixed**, 13 / 13 / 9, and its partner code 0 is
> exactly twice it, so the same ambiguity applies.
>
> **`[?]` code 0 is NOT MEASURABLE BY THIS METHOD** — different from
> unconfirmed. 31 of 45 eligible records drive the estimator onto its
> search floor: the material is percussive and unpitched, so autocorrelation
> against a root key has nothing to lock onto. **Both sessions previously
> reported code 0 as "scattered", attributing to the data what belongs to the
> instrument.**
>
> ### How we got it wrong, and the part that should have caught it
>
> `LE32 at +20` = `rec[20] | loopStart << 8`. The skip byte plus the loop
> start shifted left eight — which is why it "exceeded the sample's extent on
> 3721 of 4128 records". **The test fired on a misaligned read**, and firing
> is what it was built to do.
>
> **Our own byte-order census pointed straight at it and we did not follow
> it.** It recorded that `+22`, `+26`, `+30` and `+34` carry all the
> discriminating power — *those are the high bytes of the 24-bit values*, and
> the "positions `+16`/`+18` can never discriminate" line is the same fact at
> two-byte granularity: the real fields' low bytes sit at odd offsets and the
> skipped bytes are usually zero. **We wrote down the signature of the
> correct decoding and read it as a curiosity about byte order.**
>
> **A negative result is only as strong as its decoding assumption.** This
> document had already written that sentence about *byte order*. The failure
> was one level further down — in field **width and alignment**, and in
> **unit**: samples, not bytes.
>
> ### One correction to the source of the retraction
>
> KIMIK3 states *"every `CHO:` choir sample on CD 2 carries code 1 = 44100"*.
> Measured: of **440** `CHO:` records, **331** are code 1, **99** are code 4
> and **10** are code 3 — the `@`-suffixed choir sets are 30 kHz. The claim
> is not needed for their argument, and chasing it is what produced the code-4
> measurement above, which is the strongest evidence in this block.

### ~~[C-neg] Loop points not in this record~~ — superseded, kept for the mechanism

Read as **32-bit little-endian at the group base, against the padded byte
extent**, all four fields fail: `+20` exceeds on 3721 of 4128 (314 more are
zero), `+28 − +24` on 2507, and under big-endian 3778 and 3847. **All of that
is true and none of it is about loop points** — see the retraction above.

**[?] Not decoded, and stated as unknown rather than guessed:** the three
pointers at `+0x18` / `+0x1C` / `+0x20` have **constant deltas — 2560 and
1024 — across samples of 27, 25 and 30 blocks.** Per-sample loop points
cannot have constant spacing, and they are not disc offsets either (tested
against the envelope). Most likely S-770 RAM addresses left from mastering.

## [?] Not known — with addresses, so nobody repeats the searches

**Where the keymap `method`/`entrySize` header is written. Four negative
searches:**

1. constants `0x0017` at `body+2` and `6` at `body+10` — absent from the
   Roland module; the one `#23` is `jsr 0x149450(17,3,23,1)`, screen
   coordinates in a `sprintf` loop;
2. a second ROM prototype already carrying `method = 0x0017, entrySize =
   0x0006` — its 28-byte signature does not occur anywhere in the image, nor
   any shorter form;
3. the second prototype that *does* exist (`"New Sample"`, `0x18862A`) is also
   the 1-byte form — ⚠ **but this search was stated over a population of TWO
   and there are THREE** (`0x188436`, above). It may well still be negative;
   `0x188436` does not obviously carry `0x17`/`6`. **A negative result is only
   as good as the enumeration it is stated over, and this one was not
   exhaustive.** Recorded as incomplete rather than quietly extended;
4. the type-dispatched fixup `0x10A99C` → `0x10AD7C` for type 133 writes
   neither constant.

**`record[+38]`, the third tuning summand — where it is filled from.**
Confirmed non-zero on real material (`BA1:MC-202`, CD 2 `0x1E1600`,
contributing the whole of its −134) and **source untraced**: `−134` is
`0xFF7A` signed and appears nowhere in that 128-byte record, so it is computed
or fetched elsewhere. **Anyone proposing an answer can test it against a known
input/output pair** rather than against a plausible story.

Also open: the `0x16C5B8` / `0x15390C` volumeAdjust chain; the boundary-copy
claim for entries 0–8 and 96–127; the path where `record[+2 + 2z]` is set to
−1 and the zone skipped (`0x16BECE` tests it, the call is untraced); sniffer
format 5 at `0x171AC6`, which takes a drive number and never reads a sector;
`lyr[8]` bit 7, Akai-only and conditional on a per-zone flag mask.

**And not mapped at all: key ranges, velocity ranges, envelopes, filters,
LFOs, the Partial record's internals, and the Volume/Performance records
beyond their 32-byte directory entries.**

## [B] Blockers

**1 — sample RATE and LOOP POINTS, plus the compressed variant.** *The
audio itself is no longer a blocker* — it is located, decoded, little-endian
16-bit, stereo-paired and root-keyed (see the section above), which retires
the "never looked at, not once" state this entry described until
2026-09-21. **What remains blocks a conversion just as hard:** the **loop
points** are undecoded, and no compression flag has been found although
everything examined is linear. *(The sample **rate** was part of this blocker
until it was measured at ≈44.1 kHz — see the record section above.)* **An
extractor that ignores loops produces audio with no sustain, which is not a
conversion.** *Unblocked by* further offline work — **but not in the 48-byte
record at `0x255800`, which is `[C-neg]` for loop points**: all four of its
32-bit fields are S-770 RAM addresses, not offsets into the sample.

**2 — the disc tooling is not generic.** Hardcoded absolute offsets, no
partition offset, no sector interleave, validated on **three discs of one
family** (`S770 MR25A`, `SYS-772` v1.04 ×2 and v2.19 ×1). Against an S-750, a
floppy, a real SCSI drive or an image with a header there is no evidence at
all. *Unblocked by* more disc variety — Jan has five further Roland archives.

**3 — key/velocity ranges and every modulator are unmapped.** A first-cut
import would carry Program 199's values for all of them, which is exactly what
the K2000 does.

---

# Kurzweil K2000 v3.87J — AKAI → KRZ

**Shares the program builder with the Roland path; the staging record is
~96% structurally accounted for and its semantics are unknown.**

## [C] Confirmed

The **shared program builder** (Program-199 clone + write list), the
**8-zone loop** (`cmpiw #8,%sp@(528)`, five occurrences), the **88-key fill
bound** (`cmpiw #88,%sp@(526)` at `0x1640B0` and `0x1641F4`), and the
**velocity mark arithmetic** at `0x164C66`…`0x164CF0` — the strongest single
item in this document, being two independent derivations that never saw each
other.

The Akai arm differs from Roland in exactly three written fields plus the zone
count: `54 + 224k` (Akai only, source-derived), `57 + 224k` bit 7 (Akai only,
conditional), and the `0x17` header question that applies to both.

`54 + 224k` is `lyr[5]`, the velocity mark — an AKAI velocity range mapped
onto the K2000's eight dynamic marks. **Re-derived against operand widths
2026-09-21; the offsets in the first version were wrong:**

    lo = (WORD[+88] >> 4) & 0xFF
    if lo != 0:
        if byte[+89] & 0x0F: lo += 1        ; high nibble = mark, low = remainder
        if lo > 7: lo = 7
        if lo > hi: lo = hi
    hi = 7 if WORD[+90] == 127 else clamp((WORD[+90] >> 4) & 0xFF, <= 6)
    return (lo << 3) | (7 - hi)

**`(lo << 3) | (7 − hi)` is untouched**, as is the `negb`/`addqb #7`/`lslb #3`
at `0x164CE6`…`0x164CF0` and the two-independent-derivations claim: the panel
diff and the firmware still agree exactly. What was wrong was the **byte
numbering** — the values are at `+89` and `+91`. `lo = src[88] >> 4` read
literally yields 0 always, since `+88` is the sign half; read as *meant* it is
right, because `0x00VV >> 4` truncated to a byte **is** `VV >> 4` across the
legal range. **The arithmetic was never in danger. The coordinates were.**

The round-up also stops being odd once the widths are right: the source byte's
**high nibble is the mark and its low nibble the remainder**, which is why the
same byte is read twice.

**`0x1630C0` is closed and names nothing.** [C-neg] It is three instructions —
`movew %sp@(4),%d0` / `lsrw #8,%d0` / `rts`, the high byte of a word — a
generic accessor with no semantics, and `0x1630B8` is byte-for-byte identical,
which also kills the tempting reading that the two are a hi/lo pair. **So the
88-byte table's semantics remain `[S]` and this route to them is exhausted.**

## The 92-byte staging record — ✅ **SEMANTICS CLOSED 2026-09-22**

> ### ✅ IT IS A PER-LAYER KEY→WAVESAMPLE MAP, AND THE 88 BYTES ARE ONE WAVESAMPLE INDEX PER KEY
>
> **Settled here from the K2000 ROM and an EPS disc together**, which is the
> first time this arm has had both halves in one place.
>
> `0x1630C0`, read at the bytes (`k2000_v387j.bin`, md5
> `ab658571677603ee1bccb9cbe329aecd`) — three instructions:
>
>     1630c0:  302f 0004   movew %sp@(4),%d0
>     1630c4:  e048        lsrw  #8,%d0
>     1630c6:  4e75        rts
>
> **the high byte of a word**, exactly as recorded. And the word it converts
> comes from `%a3@(0x2E + 2·key)`, so `%a3` is the **EPS LAYER struct** —
> because the arithmetic closes on it and on nothing else:
>
>     46 header + 88 words (176) + 2 = 224 = the layer stride
>
> **The table's high bytes are wavesample slot indices, one per key**, and
> the table spans **MIDI 20 … 107**. On `FLUTE 1`'s first layer it reads
> `ws 1` for table entries 16…54, `ws 2` for 55…64, `ws 3` for 65…76 — which
> is MIDI 36…74, 75…84, 85…96, **exactly the three wavesamples' own declared
> key ranges.**
>
> **Corpus check, 11 532 layer-table runs across 613 instruments:**
>
> | | | |
> |---|---:|---:|
> | run maps onto the wavesample's own key range exactly | **9641** | **83.6 %** |
> | clipped by the table's own `20…107` extent | 1778 | 15.4 % |
> | narrower than the wavesample's range | 113 | 1.0 % |
>
> **The last 1 % is the table doing its job, not disagreeing with anything:**
> a layer may use a wavesample over a *narrower* span than the wavesample's
> own, which is what a per-layer key map is for. **So the table is
> authoritative for a layer's key mapping and the wavesample's own range is
> its native default.** The implied base is `20` on 9641 of 9644 runs where
> both ends are inside the table.
>
> **So the record reads, in full:**
>
>     staging[zone*92 + key]        zone = LAYER (0…7), key = 0…87 = MIDI 20…107
>     +0  … +87   one WAVESAMPLE SLOT INDEX per key, from layer[0x2E + 2*key] >> 8
>     +88 … +89   WORD, the layer's LOW velocity
>     +90 … +91   WORD, the layer's HIGH velocity
>
> *The structure was already accounted for; what was missing was what the 88
> bytes carried, and it is the keymap.*

## The 92-byte staging record — the structural account

[C: instruction stream] The record is **per ZONE** and its bytes are addressed
**by key**. `0x1641D4`:

    moveal %sp@(100),%a0        ; staging array base
    movew  %sp@(528),%d0        ; ZONE counter  (bounded by 8)
    mulsw  #92,%d0              ; 92 bytes per ZONE
    addal  %d0,%a0
    movew  %sp@(526),%d0        ; KEY counter   (bounded by 88)
    addal  %d0,%a0
    moveb  %a0@,%d0             ; staging[zone*92 + key]

so the layout closes exactly — **and the tail is two WORDS, not four bytes**
(corrected 2026-09-21 by its author, after re-reading the call sites against
actual operand widths):

    +0 .. +87   an 88-byte per-KEY table, one byte per key
    +88 .. +89  WORD, sign-extended AKAI LOW-velocity byte   -- value in +89
    +90 .. +91  WORD, sign-extended AKAI HIGH-velocity byte  -- value in +91

Unambiguous in the stream: `movew %d0,%a0@(88)` / `movew %d0,%a0@(90)` write
them (`0x1640D0`, `0x1640EC`), `movew %a0@(88),%d0` / `cmpiw #127,%a0@(90)`
read them (`0x164C7C`, `0x164C94`). Each source byte is `extw`-sign-extended,
so across the legal 0–127 range the high half is always `0x00` and the value
sits in the **odd** byte. **88 + 2 + 2 = 92, with nothing unaccounted** — the
earlier reading had three bytes plus a spare, which was the same total for the
wrong reason. The
`mulsw #92` appears **ten times** across the builder, so the stride is
pervasive. The importer additionally reads a per-key **word** table at
`%a3@(0x2E + 2·key)`, converts it through `0x1630C0` (the high byte of a
word), and stores one byte per key.

> ### `0x1645B6`'s 87 is NOT a key bound — and our corpus confirms what it is
>
> An external analysis flagged `cmpiw #87,%sp@(526)` as *"a second key bound,
> one iteration fewer"*, explicitly unread and with a warning to check.
> **Checked: it is the outer half of a nested pair**, and the inner loop runs
> `a3@ = 0…127` with a **6-byte stride** (`d0 = 6·d7`, then `moveb` into
> `%a4@(0,%d0:l)` and `%a4@(1,%d0:l)`).
>
> **That is a keymap entry array, not a key fill** — and this project's own
> corpus settles it:
>
> | measured over **2709 keymap objects** in 333 real `.KRZ` files | |
> |---|---|
> | keymaps with exactly **128 entries** (`num_keys = 127`) | **2709 of 2709** |
> | keymaps using **method `0x17`**, entry size **6** | **73** |
>
> **128 entries is universal in this format and the 6-byte entry is
> method `0x17`** — so the inner loop is building exactly that array, and the
> reused stack slot means something different here than at the `cmpiw #88`
> sites. **`0x1645B6` is not an off-by-one on the key fill.**
>
> > ⚠ **Two frames, not a disagreement — and one number to qualify before
> > anyone greps for it.** `796` is **measured**: it is the SysEx **DUMP**
> > payload of the Roland-imported keymaps, carrying `00 00 00 17 … 00 06` in
> > its header. `816/820/824` is also measured: the **`.KRZ` file objects**
> > in this project's corpus. **Nothing in a real file is 796 bytes**, and a
> > grep for one returns nothing — which is why it was worth raising.
> >
> > **The practical form: use `796` against a SysEx dump and `816/820/824`
> > against a file object, and expect `28 + 128 × 6` to describe only the
> > former.**
> >
> > > ⚠ **A reconciliation was offered, refused, and then WITHDRAWN by its
> > > author.** It was `796 + 24 = 820` — exact, landing on the middle of the
> > > observed split, and invoking a 24-byte constant between these frames
> > > that **is** genuinely documented (`IMPORT_CONVERSION.md` §2, eleven
> > > segment tags).
> > >
> > > **It was refused on direction and the refusal held.** That constant is
> > > `DUMP = file + 24` — a field at *file* `+12` appears at *dump* `+36`, so
> > > the dump carries a prefix the file lacks and should be the **larger**.
> > > For keymaps the **file** is larger. Opposite directions.
> > >
> > > **Its author's own §1 settles it, one section above the claim:** a
> > > 1-layer program is **DUMP 272 bytes, file 250** — *the dump is 22 bytes
> > > larger*, exactly as the direction argument required.
> > >
> > > **And it is worse than a sign error: `+24` is not the size difference
> > > even where §2 applies.** Offsets shift by **24**; sizes differ by
> > > **22**. *An offset constant was applied to sizes without anyone
> > > checking that it was one.*
> > >
> > > **`[?]` What stands: the measurements.** Dumps `796 / 668 / 412 / 156`;
> > > file objects `816 / 820 / 824`. **What is withdrawn: any account of
> > > why.** Open, not resolved, and neither session will offer another
> > > tonight.

> ### ⚠ "FROM THE SOURCE" IS WRONG — `a3` cannot be an AKAI program block
>
> An earlier version of this sentence said the table is read *"from the
> source"*. **The arithmetic rules that out.** It is a word per key with the
> key counter bounded by 88, so the structure must be at least
>
>     0x2E + 2 × 88 = 222 bytes
>
> and **no AKAI block is that big**. An S1000 common block or keygroup is
> **0x96 = 150** bytes; the S3000 form is **0xC0 = 192**. Measured here over
> **877 program blocks across two library discs: every file size divides by
> 150, none by 192.**
>
> A whole program *file* does exceed 222 bytes (smallest seen: 300), but
> `0x2E … 0xDE` would then straddle the common block and run into keygroup 1
> — not a table in the AKAI format, but two unrelated structures with a
> boundary in the middle of it.
>
> **So `a3` points at something the K2000 built, not at the disc.** Most
> likely the key→keygroup map the importer must construct for itself, since
> AKAI defines keygroups by key *ranges* while the K2000 wants a per-key
> lookup. `[S]` — the instruction stream is `k2kremote`'s arm.
>
> **And this is the class-sweep failure again.** `eosed` established on the
> EOS side that *"the source columns are offsets into what the machine HOLDS,
> not into the file"* — a statement about **every** such column in this
> document. It was applied to the Ensoniq and Roland arms and **never swept
> into the AKAI one**, where a sentence saying "from the source" sat
> unexamined. *That makes two rows the enumeration would have caught.*

This also **strengthens** the 88-key claim: both `cmpiw #88` sites are genuine
key loops with their own increments (`addqw #1,%sp@(526)` at `0x1640AC` and
`0x1641F0`, each `blts` back to `0x164082` / `0x1641D4`), not an analogy from
the Roland arm.

**[S]** — that the 88-byte table is a **per-key keygroup assignment** is the
obvious reading and **is not demonstrated**.

## [B] Blocker

**The record's SEMANTICS, and where any of it is filled from on disc.**
Structure without meaning and without the disc-fill path does not make a
converter.

> ### ⚠ The disc read is located. THE FIELD IDENTIFICATIONS ARE WITHDRAWN.
>
> `0x16399C` reads **644 bytes** from a file handle into `a5 + 0x2132` — a
> different region from the `a3` scratch area, 6 KiB away. **That much
> stands.** What does not:
>
> > **An earlier version of this block read: *"three offsets, three hits, one
> > of them load-bearing — so the 644-byte buffer is an AKAI PROGRAM FILE
> > read from offset 0"*. It is retracted in full.** The offsets were
> > `0x22`/`0x24`/`0x2A`, reached by treating `34`/`36`/`42` as decimal. They
> > were already **hexadecimal** — `objdump` prints the indexed form's
> > displacement in hex without a prefix while printing plain `%a5@(n)` in
> > decimal. **The real offsets are `0x2C`, `0x34`, `0x36`, `0x42`** — four,
> > not three; the fourth was missed by a `[0-9]+` regex that cannot match
> > `2c`.
>
> **Re-run against the correct offsets, over 5124 program files from eight
> library images — 2832 S1000-form and 2292 S3000-form:**
>
> | offset | distinct values | non-zero |
> |---|---:|---:|
> | `0x2C` | **1** | **0 of 5124** |
> | `0x34` | **1** | **0 of 5124** |
> | `0x36` | **1** | **0 of 5124** |
> | `0x42` | 9–10 | 169 of 5124 (3 %) |
>
> **Three of the four bytes are identically zero in every AKAI program ever
> written to these discs, in both generations.** The fourth is zero 97 % of
> the time.
>
> **So the conclusion inverts: the evidence now argues the 644-byte buffer is
> NOT an AKAI program file.** A routine that reads four header fields would
> not choose three that are always zero. *The "`0x175826` does not seek
> first" claim goes with it — it rested entirely on the withdrawn mapping.*
>
> > **What the first version got wrong is not the arithmetic but the
> > provenance.** A peer supplied displacements; this project converted them
> > without asking what base they were in, then scored the result against its
> > own format knowledge and called one hit "the clincher". **When you
> > transform someone else's numbers, state the unit you assumed back to
> > them** — the conversion is a claim, and it was the only wrong step in a
> > chain where nobody's reading was at fault.
>
> **And neither of us asked the baseline question.** Against a 150-byte block
> in which our reader names a couple of dozen fields — several of them in one
> dense cluster at `0x21`…`0x2A` — three hits is less improbable than it
> felt. *What could this evidence have come out as?* went unasked for the
> fourth time today.

> ### ⚠ But the 136-entry scan does NOT decompose as an AKAI structure
>
> The scan at `0x1630C8` runs `buffer + 100 + 4·i` for `i < 136`, splitting
> 8 / 128 by index. **Nothing in the AKAI format matches that.** An S1000
> common block ends at **150**, so a 544-byte run from `+100` leaves it after
> ten entries and crosses into keygroup 1 — and a keygroup is a 150- or
> 192-byte record, not a 4-byte one.
>
> **Two readings were offered. BOTH ARE REFUTED**, by enumerating every use
> of `d2` between the read and the scan: `0x1639FC`, `0x163A0A`, `0x163A1A`,
> `0x163A2A`, `0x16412E` — **all reads, not one store through `d2` anywhere
> in the builder.** The buffer is not overwritten, so the scan really is
> reading file bytes.
>
> ### ✅ SOLVED — it is an EPS INSTRUMENT header, and both bounds are real
>
> The file is not AKAI. Measured here against **120 EPS instrument headers**
> from a real Ensoniq CD-ROM, taking the first 644 bytes of each and
> decomposing them exactly as the firmware does:
>
> | | result |
> |---|---|
> | pool 1, indices `0…7` | **never exceeds 8**, and **43 of 120 instruments use all 8** |
> | pool 2, indices `8…135` | **never exceeds 128**, and the maximum observed **is 128** |
> | bytes 1 and 3 of every entry | zero on **16 175 of 16 320** (99.1 %) |
>
> **Both bounds are reached, not merely respected** — which is what makes
> them capacities rather than coincidences.
>
> **And the zero-byte pattern independently confirms the firmware's reader.**
> `0x162FF2` builds `(entry[0] << 8) + entry[2]`, using bytes 0 and 2 and
> ignoring 1 and 3. The EPS stores 16-bit quantities **zero-padded to
> 32 bits** — the same encoding its instrument names use, 16-bit characters
> with zero high bytes. *The firmware is not skipping bytes; it is reading
> the format as written.*
>
> **`[C]` 8 = LAYERS**, confirmed three ways and none of them shared: EOS's
> own Ensoniq channel builder loops `moveq #8,%d0` for layers 0…7; its
> per-variant and per-channel masks are single bytes tested bit by bit, eight
> bits for eight layers; and the first pool here is capped at 8 with 43
> instruments filling it.
>
> **`[S]` 128 = WAVESAMPLES.** The capacity is now `[C]` from the data — the
> pool holds 128 and real instruments reach it. **What it holds is still
> inference**, resting on EOS treating an EPS instrument as exactly two
> byte-indexed object kinds side by side: a **layer** array (stride 224) and
> a **wavesample** array (stride 288). A K2000 scan emitting *(index, type 1
> or 2)* maps onto that distinction, which is why the reading fits — but
> nothing has yet read a wavesample *count* out of either ROM.
>
> > ⚠ **`eosed` went looking for that count and declined to supply it.** They
> > found `#128` three times in EOS's Ensoniq region and checked what it
> > bounded before sending: a **128-word lookup table**, not a wavesample
> > limit. *Right number, wrong object* — and they flagged the risk of their
> > own half-answer hardening into a confirmed 128 in transit, in the message
> > that carried it. **It has not hardened here.**
>
> ### ✅✅ AND THE VALUES ARE THE POSITION LIST — `O1`'s missing table
>
> `0x162FF2` builds `(byte0 << 8) + byte2` **and then shifts left 4**. Apply
> the `× 16` and the table's values become **file positions**:
>
> | | measured on 120 instruments, 4078 values |
> |---|---|
> | values `× 16` falling inside the instrument file | **3772 (92.5 %)** |
> | smallest pool-1 value | **656**, on **101 of 120** instruments |
> | commonest gaps between sorted pool-1 values | 512, 800, and **224 × 45** — the layer stride |
>
> **The decisive check is against this document's own numbers.** The Ensoniq
> section records the observed struct bases as *"656, 880, 1104, 1328, 2544,
> 93200, 97120, 105552, 115280, 129088 — **No rule.**"* **ALL TEN appear as
> table values**, and those ten were derived from the E4XT's own output by
> matching root key and key range, with no reference to any table.
>
> *This project first reported nine of ten, with 93200 absent. **That was an
> artefact of a capped scan**, corrected by `eosed`'s wider walk — and it is
> worth leaving visible, because "nine of ten with one stubborn exception"
> is exactly the shape that invites a story about the exception.*
>
> **`eosed`'s own validation, on their reference disc:** 97 instruments, 232
> table values, **230 land on a plausible wavesample struct, 2 do not, 0 fall
> outside the file.**
>
> **So the document's own prediction is confirmed by its own numbers:**
> *"positions are LISTED rather than computed — a record table the walker
> indexes. That would explain the base scatter with no rule connecting them,
> which is exactly what is observed."* **This is that table. The scatter has
> no rule because it was never computed.**
>
> > **How it was missed, and it is the sharpest methodological moment of the
> > day.** `eosed` tested this exact table against `O1` and filed it as a
> > **failed** lead — *"the values are not positions; I tried raw, doubled,
> > ×512, and offset from the known base 880"*. **They did not try `× 16`**,
> > which is the one transform the firmware itself performs. And their own
> > message carried the proof: their `idx 9` decodes to **55**, and
> > `55 × 16 = 880` — the very base they were offsetting from.
> >
> > **They filed it as TESTED so nobody would re-run it.** It was re-run
> > anyway, on different material, with one transform varied — **which is the
> > argument for recording a failure together with its method.** A lead
> > marked "checked" stops the next person; a lead marked "checked *this
> > way*" tells them what to vary.
>
> ### ✅ `[C]` POOL 1 IS LAYERS, POOL 2 IS WAVESAMPLES — from the positions themselves
>
> Neither session would complete this from strides in a ROM. **The position
> list settles it**, because the strides appear *in the gaps between the
> positions*. Measured on 120 instruments, splitting gaps by size — a gap of
> tens of kilobytes spans **sample audio**, since the instrument file
> interleaves headers with PCM, so only struct-adjacent gaps are informative:
>
> | | gaps ≤ 1024 | fitting |
> |---|---:|---:|
> | **pool 1**, form `224 + n × 288` | 267 | **254 (95.1 %)** |
> | **pool 2**, form `n × 288` | 2149 | 1617 (75.2 %) |
>
> **`224 + n × 288` is the layout stated as arithmetic:** a **layer record of
> 224 bytes**, followed by **n wavesample records of 288 bytes** — its own
> wavesamples — then the next layer. Pool 1 holds layer positions, pool 2
> wavesample positions, and the two interleave in the file.
>
> **This confirms `eosed`'s `[S]` from the opposite direction.** They had
> EOS's two byte-indexed arrays — a layer array at stride **224** and a
> wavesample array at stride **288** — and declined to map them onto the
> pools. *The same two strides turn up in the disc's own position gaps, which
> is a fact about the file rather than about EOS's memory layout.*
>
> ### Confirmed on FIVE discs, and the 512 guess checked
>
> `eosed` re-ran the test on four further Ensoniq images:
>
> | disc | instruments | pool 1 `224 + n·288` | pool 2 `n·288` |
> |---|---:|---:|---:|
> | this project's | 120 | 254/267 **95.1 %** | 1617/2149 75.2 % |
> | A | 613 | 1792/1823 **98.3 %** | 5933/8301 71.5 % |
> | B | 49 | 38/40 **95.0 %** | 1206/1322 91.2 % |
> | C | 235 | 376/379 **99.2 %** | 2344/2982 78.6 % |
> | D | 741 | 97/97 **100.0 %** | 1636/1768 92.5 % |
> | reference | 97 | *no pool-1 gaps* | 1/1 |
>
> **Pool 1 holds at 95–100 % on every disc that has pool-1 gaps at all** —
> and the reference disc having none is **predicted, not missing**: its
> instruments populate layer 0 only, so each carries a single pool-1 entry
> and there is no gap to measure. *A rule that predicts its own absence of
> evidence is worth more than another data point.*
>
> **`[C]` The `512` reading is confirmed.** Of pool-2 gaps that are *not*
> multiples of 288, across two discs: **512 on 2875 (95.6 %)**, 736 on 61
> (2.0 %), everything else below 0.5 % each. So a pool-2 gap is `n × 288`
> **or a 512-byte block boundary**, and those two cover ~99 % of informative
> gaps.
>
> **`[?]` The 736 and the long tail are genuinely unexplained**, and recorded
> rather than folded into the 99 %. **And the residue is consistent across
> five discs**, which makes it a property of the format rather than of any
> disc — *so a sixth disc will not explain it. It needs a reader.*
>
> **`[?]` Two of 232 values land on no struct**, and 7.5 % of this project's
> fall outside the file — the latter probably its instrument detection, the
> former unexplained. Recorded.

> **`[?]` The 0.9 % exception.** 145 entries of 16 320 carry a non-zero byte
> 1 and 149 a non-zero byte 3. Either a second encoding exists in some
> instruments, or this project's header detection admits a few files that are
> not instruments. Recorded rather than rounded away.
>
> > ⚠ **A trap worth naming before anyone falls in it.** This project's AKAI
> > writer has `ROOTDIR_ENTRIES = 100`, and the scan's header is **100
> > bytes**. *These are unrelated:* one is a count of volumes per partition,
> > the other a byte offset. **The AKAI maxima are 18 partitions and 100
> > volumes — neither is 8 and neither is 128.**

> **Narrowed and then RE-OPENED on the same evening.** The instruction that
> looked like a disc-fill path — the per-key word table at
> `%a3@(0x2E + 2·key)` — **is not one**: `a3` is a global scratch area at
> `a5 + 0x3932`, confirmed from the instruction stream after this project
> showed the arithmetic could not fit an AKAI block.
>
> **The real read was then located**, and its three header fields all hit
> AKAI program common-block offsets, including the keygroup count. **So the
> disc-fill path exists, is found, and is partly decoded** — see above.
>
> **What this project can contribute offline is more than it looks:** a
> mature AKAI reader and a 27-image corpus. Once a genuine disc read is
> located, **every field the importer takes can be predicted from our side
> before any hardware runs** — the same asymmetry that closed the EOS Roland
> pan and fine-tune rows in a single pass.

**An earlier draft of this section said "three bytes known, the rest
untraced" and "one field wide".** That was an *understatement*, and it would
have sent an implementer away from a record that is ~96% structurally
accounted for. Recorded because an understated capability wastes time as
surely as an overstated one — and this document warns about the overstated
direction in a dozen places and had the other one in it.

**And there is no AKAI disc on the K2000's bus** — the corpus is at
`~/Dokumente/SYNTHS/Akai S3000XL` but nothing is mounted, so none of the Akai
arm has ever been hardware-checked.

---

# Kurzweil K2000 v3.87J — Ensoniq → KRZ

## ~~[C-neg] The K2000's Ensoniq support is AUDIO-ONLY~~ — **REFUTED 2026-09-21**

> # ⚠ THIS `[C-neg]` IS WRONG. THERE IS AN ENSONIQ PROGRAM CONVERTER.
>
> **It is at `0x16368A`, and both sessions had been documenting it all day —
> under the label "the AKAI arm".**
>
> The dispatch is in the **caller**, `0x1221AA`, on the disc format code
> `a5@(0x14AA)` (`movew #5290,%d2` at `0x12210E`):
>
>     0x122114   format 4  ROLAND   -> jsr 0x16BBEA
>     0x12215E   format 2  ?        -> jsr 0x1652FC
>     0x12218E   format 3  ENSONIQ  -> jsr 0x16368A
>     0x1221C8   format 5  ???      -> further on   <- NOT AKAI, see below
>
> **Everything this document called the AKAI arm is the Ensoniq arm:** the
> 92-byte staging record, the 88-key table at `a3@(0x2E)`, the 8-zone loop,
> the 88-key fill bound, the 644-byte read, the 136 × 4 scan split 8/128,
> and `0x164C66`.
>
> ### Confirmed independently here, and the ROM says it in three places
>
> **1. The filesystem layer names three separate drivers by prefix**, in its
> own diagnostic strings — which is as close to a labelled answer as a ROM
> gets:
>
>     0x1915xx   ak_dskinit, ak_pfinit, ak_read_obj, …      AKAI
>     0x1916xx   eps_dskinit, eps_dirinit, eps_read_obj, …  ENSONIQ EPS
>     0x1918a9   s770_dskinit                                ROLAND S-770
>     0x1911xx   pc_dskinit, …                               DOS/FAT
>
> **2. The string pool beside the builder is the EPS multi-floppy flow**, and
> nothing else on the disc needs it: *"This is one file of a multi-disk
> set."*, *"You must load disk #1 first."*, *"Insert disk #%d for loading."*,
> *"Sorry, this is disk #%d, try another."*, *"Load all programs or just the
> samples?"*, *"Progs  Samps  Cancel"*, *"Can't find any more samples for
> this program.  Insert a different disk."* — the EPS shipped libraries
> across numbered floppy sets; AKAI CD-ROMs do not.
>
> **3. It explains this project's own corpus result exactly.** Three of the
> four header bytes were identically zero across **5124 AKAI programs**, and
> the 136 × 4 scan matched nothing in the AKAI format. **Both measurements
> were correct and were pointing straight at this** — and both were read as
> *"my offsets are wrong"* when what they said was *"your format is wrong"*.
>
> ### The method failure, which is the part that generalises
>
> The `[C-neg]` rested on a reference set: 26 references to the format code,
> 25 in the file layer, the single converter-region one testing format 5.
> **Every count was correct.**
>
> > **A DISPATCH LIVES IN THE CALLER.** Asking whether the format code is
> > tested *inside* `0x163000`–`0x16C000` looks in the one place a dispatch
> > is never found. `0x12218E` was counted among the 25 and read as evidence
> > **against** the thing it proves. **Under that method a converter reached
> > by an external dispatch is indistinguishable from no converter — the
> > result was fixed before the search ran.**
>
> *This is the fifth time today the answer-set question went unasked, and
> the third time by the session that filed the rule.*
>
> ### What this costs, stated plainly
>
> * **`O6` does not shrink. It returns to EMPTY.** The AKAI builder is
>   somewhere past `0x1221C8` and nothing whatever is known about it.
> * **Every hour of "AKAI staging record" work belongs to the Ensoniq arm**,
>   where it is useful to `eosed` rather than here.
> * **`(lo << 3) | (7 − hi)` survives and changes meaning.** It is the
>   K2000's own `lyr[5]` encoding and the panel diff was of the *target*
>   field, which is source-agnostic — so the agreement was real. *"Two
>   independent derivations on the AKAI path"* becomes **"the Ensoniq
>   importer computing the K2000's own velocity encoding"**.
> * **Roland is untouched** — a different builder (`0x16BBEA`), and every
>   Roland finding was checked against disc bytes or device output.
>
> > ⚠ **One anchor worth re-checking, found while confirming the above.** The
> > Roland loader was identified by its progress string *"Loading sample %s,
> > %ldK bytes…"*. **That string occurs three times** — `0x1905BB`,
> > `0x190732`, `0x190B84` — once per importer. The Roland *findings* stand
> > on disc evidence independently, but **the anchor was not unique** and
> > nobody checked that it was.

**Settled 2026-09-21 by an exhaustive reference set, not a walk** — which is
why it is `[C-neg]` and not a gap:

* The format code `a5@(0x14AA)` has **26 references in the image**. Twenty-five
  are in the file/disk layer. The **single** converter-region reference,
  `0x168B98`, tests format **5**, not 3, and sits in directory-listing code
  (`cmpib #46` for `'.'`).
* **No converter-region code tests format 3 at all.** The only format-3 test
  in the ROM is `0x113514`, paired with format 2.
* Every object-lookup call site in the converter region belongs to the AKAI
  builder (`0x163C1A` … `0x163C8E`, `0x1645E2`) or the Roland one. **There is
  no third converter region.**

> ⚠ **CORRECTED 2026-09-21 by the session that supplied the original
> reading.** An earlier version of this section said `0x113514` selects
> *"a distinct transfer handler, replacing what the other formats get"*.
> **`0x1071FC` is not distinct.** It is installed unconditionally into the
> global slot `a5@(0x125C)` at `0x1129C2`, `0x1156EA` and `0x161FA8` — it is
> the machine's **generic** sample-transfer routine, one of two variants
> chosen by `a5@(0x14B2)` in a vtable installer. The format-2/3 branch
> selects the *standard* handler into a local slot.
>
> **This strengthens the conclusion rather than weakening it:** the Ensoniq
> path has **no Ensoniq-specific code beyond the sniffer.**

`0x1071FC` writes to `0x580000` … `0x5C0000` and to hardware ports
`0x780007` / `0x78000B` — bulk data transfer into sample RAM, and it is what
every format gets.

**What this means for us:** a K2000-faithful Ensoniq → KRZ program conversion
**cannot** be emulated, because the machine does not do one. Anything we
build on this path would be our own invention, not the firmware's behaviour —
which is precisely the thing Jan ruled out for formats he cannot check on
hardware. *Sample audio is a different question and is not closed by this.*

---

# Status at a glance — and what blocks each path

**Open topics are numbered `O1`…`O9` in the next section and nowhere else.**
Cite them by number; the numbers are stable and the prose is not.

| # | path | converts today? | law implemented | what is still open |
|---:|---|---|---|---|
| 1 | **EOS: Ensoniq → E4B** | ✅ **yes** — 2396 presets, 2681 samples, 14 040 zones from a 358 MB EPS CD | **complete.** Position table, root/key range, per-layer key map, pan, the `0x796A4` volume table, layer-mask variants, BE audio, `0x78CC4` audio pointers with loops | **nothing that blocks.** `[?]` the sample rate has no located field (29762 Hz, measured by pitch) |
| 2 | **EOS: Roland → E4B** | ✅ **yes** — 4004 / 2880 presets across the two Roland reference discs, 7 discs read in total | **complete.** `O8` closed: the zone builder writes all 22 bytes and maps onto §4.5 field for field. Pan, fine tune, velocity quartet, tuning, loops, rates | **nothing that blocks.** Filter/env/LFO are dropped *by the firmware*, so our defaults are deliberate |
| 3 | **EOS: AKAI → E4B** | ✅ **yes** — the oldest path here, a mature reader and hardware at both ends | **complete.** `O7` closed on the E4XT: keygroup `0x13` is key → amp-envelope **RELEASE** (`0x4B`), as written. `O7b` closed the scales: **96 for `FilFreq`, 48 for the seven envelope cords**, and the sign rule is **per-SOURCE** — `negl` on the four `Vel+` cords only | **nothing.** `[?]` two cords are unmodelled by the *simulation* (below); the converter is unaffected |
| 4 | **K2000: Ensoniq → KRZ** | ✅ **yes** — same EPS reader, KRZ writer | **complete.** The 92-byte staging record closed 2026-09-22: a per-LAYER key→wavesample map over MIDI 20…107 | **nothing.** |
| 5 | **K2000: AKAI → KRZ** | ✅ **yes**, and **deliberately better than the device** | **measured on 52 more programs 2026-09-22, and the headline was wrong.** The device converts the **keymap geometry** and the **velocity window** (`lyr[5]`, packed marks) and discards filter, envelope, LFO, pan and level. 84 programs now, both disc forms, mono / stereo / drum / velocity-split | `[?]` who owns the 100-object ceiling (`11 CLASSMIX1`, 49 samples, one load) · `[?]` what sets the keymap allocation — **four** import arms on one `28 + k×128` ladder, no candidate · `[?]` where the AKAI velocity computation lives (`54 + 224k` is annotated *Akai only* here, but `0x164C66` was re-attributed to Ensoniq — both cannot hold) |
| 6 | **K2000: Roland → KRZ** | ✅ **yes**, but **coarser than the device** | audio, loops, modes, rates, tuning — and the loop-mode table corrected 2026-09-22 (mode 2 sets bit 7) | `O5` — the device groups PARTIALS into one program and splits keys from the patch; we make one preset per partial. **`[S]` the patch's 128-byte key table at `+32`, MIDI base 21** |
| — | *(all paths, reading foreign banks)* | — | `O9` closed: E4B zone-entry `[7]` is the LOW fade, `[8]` the HIGH, read out of the zone builder | **nothing** |

**Ordered by how much of the firmware's law is implemented, not by effort
left.** All six convert today. Rows 1–4 have no open question that changes
output; row 5 is deliberately *better* than the firmware and row 6 is
deliberately coarser, and both say so.

## The firmware-import SIMULATION — a second table, because it is a different question

The table above asks *"does this path convert well?"* This one asks **"can we
reproduce, byte for byte, what the device itself would have written?"** —
Jan's directive of 2026-09-22. **They are not the same question and the
answers do not track each other:** row 5 converts *better* than the K2000 and
is the most complete simulation; row 1 converts completely and cannot be
simulated at all.

**A simulation is not a simpler conversion — it is a deliberately worse one**,
whose value is that a bank built with it can be diffed against a real device
import and **every difference is a defect in our reading of the firmware.**
That is destroyed the moment a field falls back to one of this project's own
laws because the firmware's behaviour for it is unknown. Where the firmware is
not established, a simulation writes **nothing** and names the gap.

| # | path | simulation | verified against | residual |
|---:|---|---|---|---|
| 5 | **K2000: AKAI → KRZ** | ✅ implemented | 84 programs diffed against ROM Program 199 | none known |
| 3 | **EOS: AKAI → E4B** | ✅ implemented | the cord manifests; enum table confirmed on hardware | 11 of 23 cord sites located-not-modelled |
| 2 | **EOS: Roland → E4B** | ✅ implemented | `ROLTEST.e4b` — **25/25 voices byte-exact, all 284 bytes** | none |
| 1 | **EOS: Ensoniq → E4B** | ✅ implemented | `EPSTEST.e4b` — 41/41 on the template; volume/pan 40/41 | zone COUNT on 10 of 41, **cause NOT diagnosed** — the "zone de-duplication" reading is refuted, see §EPSZONERESID |
| 6 | **K2000: Roland → KRZ** | ✅ implemented | 12 device banks, **164 layers**: `lyr[5]`, `lyr[8]`, `cal[7,8,11,12]`, `0x53[2]/[14]` | none known |
| 4 | **K2000: Ensoniq → KRZ** | ✅ implemented | 1 device bank, **56 layers**: `lyr[3]/[4]`, `cal[12]`, `0x53[14]` | `cal[11]` unexercised (all ids < 256) |

> ### ⚠ THE THREE K2000 ARMS DO NOT AGREE, AND THAT IS THE FINDING
>
> Its **Ensoniq** arm writes the layer **KEY RANGE** (`lyr[3]`/`lyr[4]`) and
> **no velocity window at all**; its **AKAI** and **Roland** arms write the
> velocity window (`lyr[5]`) and never the key range. The AKAI result — *"the
> firmware does not write the layer key range"* — is true of that arm and
> **false of the Ensoniq one**.
>
> *A simulation assuming one K2000 import behaviour would put the right value
> in the wrong field on every layer of two of the three.*

> ### ⚠ AND `cal[11]` IS A CONSTANT, NOT A LAW
>
> The keymap id's high byte is constant `0` across all 56 Ensoniq layers and
> varies (`0`/`1`) across the 164 Roland ones. **The difference is the
> material, not the firmware**: Roland's banks reference keymap ids 200–346
> and Ensoniq's only 200–255, so one needed the high byte and the other never
> did. Excluding it from the Ensoniq write list would have made a correct
> writer look wrong. *A corpus of defaults is a corpus of one observation
> repeated.*

**Ordered by how close each is to reproducing the device.** Note that this
ordering is nearly the *reverse* of the conversion table's on rows 1 and 5 —
which is the point of keeping them apart.

> ⚠ **A simulation that agrees with the device for the WRONG REASON is worse
> than one that disagrees**, because it retires a test nobody actually ran.
> `eosed` raised this handing over `T_atk`, which is **flat at zero for its
> first 21 entries**: every AKAI attack from 0 to 20 imports as rate 0, so a
> diff over short-attack material passes trivially on those voices. **Weight
> the validation material, or read a high pass rate as evidence of nothing.**

> **Row 5 changed on 2026-09-22 and the change is a warning about the other
> five.** *"The importer converts nothing"* stood on **32 programs across six
> volumes** — and every one of them was velocity-unrestricted at the source,
> so the one field that does cross was 0 on both sides and invisible. It took
> a 52-program load chosen for a different question to find it. **A negative
> is only as wide as the variation in the material it was measured on**, and
> nothing in the table tells a reader which rows rest on uniform corpora.

**The pattern behind the table: the firmware traces give the conversion LAW,
never the source PARSER.** AKAI→E4B was extendable in an hour because a mature
source reader already exists in this repository. For Roland and Ensoniq the
reader is the larger half of the work and almost none of it is in the
firmware.

**The offline/hardware split is stated per topic below rather than counted
here** — a count in this position goes stale on the next append, and this one
did: `O3` moved from offline to hardware-blocked on 2026-09-21 when its rate
*values* turned out to be unresolvable from the disc, while `O8` moved the
other way by being half-done. **Read the `· offline` / `· needs the rig`
marker on each topic; it is maintained, this sentence is not.**

---

# Open topics

Numbered for citation. Each says what it is, what would close it, and whether
it needs the rig.

### O1 — The Ensoniq instrument file's LAYOUT · ✅ **SOLVED**

Where every wavesample's struct begins, and where its audio begins and ends —
**one unknown, not two.** Observed struct bases in one bank (`656, 880, 1104,
1328, 2544, 93200, …`) follow no rule; positions are **listed, not computed**,
confirmed at instruction level.

~~**What closes it:** locate **every** struct in one instrument rather than
only those a preset variant happens to name.~~ ✅ **SOLVED** — the 136-entry
table in the EPS instrument header at `+100`, values `× 16`. Verified on 120
instruments here and **230 of 232 values on `eosed`'s reference disc**, with
**all ten** of this document's hardware-derived bases present.

> **The criterion behind "230 of 232", stated here because the number was
> not reproducible without it** — raised by GLM-5.3-Flash, 2026-09-22, as a
> provenance gap rather than a refutation: this document quoted the count
> while the definition of "a plausible wavesample struct" lived only in
> `eosed`'s `RESOLUTION_NOTES` §172. In their words:
>
> > *"Plausible wavesample struct" = at offset X, byte `X+170` in 1…127 (root
> > key), `X+274 ≤ X+276 ≤ 127` (key range ordered and in range), and fewer
> > than 200 of the 288 bytes non-zero (a parameter struct is ~35 % dense
> > where audio is ~98 %). 230 of 232 table values on 97 instruments meet
> > all three.*
>
> **The criterion makes the count reproducible; the ROM arithmetic makes the
> claim true.** `0x162FF2` computes `((byte0 << 8) + byte2) << 4` including
> the skipped padding byte — re-read and confirmed independently by
> GLM-5.3-Flash — so the `× 16` is the firmware's own transform rather than a
> fitted multiplier, which is the stronger support of the two.

**What remains is not a blocker:** which pool holds which object kind, and
two values in 232 that land on no struct. *Adjacency stops mattering —
nothing needs computing from consecutive bases, because nothing ever was.*

> **And it retrospectively explains the four withdrawn scores.** No
> arithmetic chain exists because **the positions are not arithmetic**. The
> family search, the `req` line, the ratio cluster — all of them were
> measuring a quantity that does not exist. *§164 predicted exactly this
> and nobody believed it strongly enough to stop looking for a rule.*

~~**Blocks:** EOS Ensoniq → E4B, completely.~~ **Nothing — `O1` is SOLVED**
(see above, and the status table). *This line stood for a day after the
section it closes was answered, in the exact position this document's own
method section says a retired claim survives longest: a section tail
immediately after the correction that retires it. Caught by an external
review (GLM-5.3-Flash, 2026-09-22), not from inside.*

### O2 — What the walker's accumulator holds · **CLOSED, lifecycle corrected**

**It holds an OBJECT ID.** All three parts are read at instruction level.

**`[C]` The stored length IS the read length — with a conditional `+8`.**
`0x7ac24` stores `d6` at `entry[+60]`, bounds-checks with it and passes it to
`0x77a48`. But between the store and the read, `0x7ac52` tests a flag and may
call `0x4a4ac`, which returns **8 or 0** (`d0 = 12 + obj[20]; return d0 >
obj[36] ? 8 : 0`) and adds it to `d6`.

> ⚠ **A converter using `entry[+60]` as the audio extent is short by 8 bytes
> on those records** — the kind of wrongness that surfaces as a click, not as
> an error. Take the read length, not the stored one.

**`[C]` The composite is real.** `d7 = extent + fp@(12) + 48`, 2-aligned, is
pushed as `fp@(20)` and becomes `d6` — so it **is** the read length. This
project objected that "a read length that grows with position is incoherent".
The objection was right and aimed one level too shallow: **what it refutes is
the word *position*, a label, not the disassembly.**

**`[C]` It is an OBJECT ID.** Raised by two external sessions and then read
in the ROM by `eosed` (§170):

    13e808:  movel 0x10004ff0,%d0          getter — current object id
    13e810:  movel %sp@(4),0x10004ff0      setter
    13e81c:  d0 = 92 * arg + [0x10004ff8]  arena accessor, 92-byte stride
    13e82c:  id table at 0x102d01d0, stride 92
    13de88:  zeroes 92 bytes, returns 92
    19d8e0:  free-slot allocator over ids 1 … 999

and decisively, in the walker's caller:

    7afea:  jsr   0x19d93c                 ALLOCATE a starting id
    7aff0:  movel %d0,%fp@(-4)
    7b062:  movel %fp@(-4),%sp@-
    7b066:  jsr   0x13e810                 publish it back AS THE OBJECT ID

**`fp@(12)` is a cursor in EOS's 92-byte imported-object arena — an id in the
1 … 999 space the bank format already uses.** Not a file position, not an
audio offset.

> ## ❌ RESOLVED 2026-09-22 — IT IS READ-MODIFY-WRITE. THIS NOTE WAS WRONG.
>
> ~~**The lifecycle is ALLOCATE-then-PUBLISH, not read-modify-write.** An
> earlier relay said the walker "initialises from `0x10004FF0`". It does not;
> it allocates through `0x19D93C`.~~
>
> **`0x19D93C` is a two-instruction alias for the GETTER.** Challenged by two
> external reviews and then **read out of the ROM by `eosed`**, who owns that
> image and had made the original claim:
>
>     19d93c:  jsr 0x13e808
>     19d942:  rts
>     13e808:  movel 0x10004ff0,%d0
>     13e80e:  rts
>
> So `0x7AFEA` **reads** the current id, `0x7AFF0` stores it, and
> `0x7B062/0x7B066` writes it back: **read-modify-write**, exactly what this
> note denied. **And the real allocator `0x19D8E0` is named three lines above
> in this document's own table** — the sentence denying it sat under the
> evidence against it.
>
> > **The relay was right and the correction overwrote it.** This project
> > recorded the corrected version because it arrived with confident
> > reasoning attached (*"a converter replicating the wrong lifecycle
> > collides with whatever else holds ids"*) — the fourth instance in this
> > record of **an item travelling inside a correction and inheriting its
> > credibility**, and the first where the corrector was the owner of the
> > evidence.
>
> **The safety sentence survives, re-pointed:** who allocates, and whether
> the imported id is reserved, is a sharper question under read-modify-write
> than under allocate-then-publish, not a moot one.
>
> **What was never challenged and still stands:** `fp@(12)` is an object id
> in the 92-byte arena, a small integer under 1000, not a file position.

**And this is why the composite read as nonsense.** `extent + fp@(12) + 48`
is incoherent only if `fp@(12)` is a large file offset. **It is a small
integer under 1000**, so the sum is dominated by the extent and the
arithmetic is unremarkable. *This project offered "or `fp@(12)` is small or
zero" as the weaker of two alternatives; it was the right one.*

> ## ✅ FOUND 2026-09-22 — the "not found" was a false negative
>
> ~~`eosed` looked and did not find it; that range works on `a4@(52)`/
> `a4@(56)` through the fixed-point helpers, with no `+92` and no
> `entry[+28]`/`entry[+60]`. It may sit elsewhere in the function than the
> window read.~~
>
> **KIMIK3's formula is exactly right, and it is `0x190` bytes further into
> the same function** — the search read `0x7A9C4`–`0x7AA20`, the head:
>
>     7ab50:  movel %a5@(28),%d6     entry[+28]
>     7ab54:  addl  %a5@(60),%d6     + entry[+60]
>     7ab58:  movel %d6,%a3@         store
>     7ab5c:  jsr   0x13de88         returns 92
>     7ab62:  addl  %d0,%a3@         + 92
>
> **`accumulator := entry[+28] + entry[+60] + 92`.**
>
> ### AND THE TWO REVIEWS DISAGREED HERE BY FOUR BYTES
>
> GLM-5.3-Flash read `7ab62: addl %d0,%a3@` (the 92 **is** added); QWEN38F
> read `7ab64: moveq #0,%d0` (the 92 **discarded**). **Both instructions
> exist.** `0x7AB64` is the function's own return value, two instructions
> before its `rts` — QWEN mistook a return for a discard. **GLM is right and
> the 92 is added.**
>
> *Holding this document rather than editing it on either review's say-so was
> the correct call, and the disagreement was resolvable by reading four more
> bytes than either of them quoted.*
>
> > **`eosed`'s own note on how the false negative happened, in their
> > words:** their message said *"it may sit elsewhere in the function than
> > the window I read"* — and then filed the result as not-found. **A STATED
> > LIMITATION ON A SEARCH IS A REASON TO REDO THE SEARCH, NOT A LICENCE TO
> > REPORT ITS RESULT.** The fix was one larger address range. *This project
> > asked for it to be recorded as "unlocated rather than wrong" and both
> > sides called that the careful option. The careful option was another
> > `objdump`.*
>
> **Do not re-derive the `+224`/`+448` residuals from `92 + 48`** — KIMIK3
> flagged this themselves, unprompted. That is the residual-fitting this
> document spent a day retracting, and locating every record is `O1`'s
> precondition rather than a thing to route around.

**Blocks:** nothing on its own; it sits underneath `O1`.

### O3 — Roland sample metadata · *closed for conversion, offline*

The audio is located, decoded and validated at **`0x2B5800`** — little-endian
16-bit, stereo-paired, zero-padded.

**Read the two halves separately: the structural findings are verified on
9889 records and none of them depends on pitch. The rate VALUES are not
resolvable from the disc at all.**

* **RATE:**
  * **`[C]` the dispatch** — `record[+44] & 15`, `cmpiw #5`/`bhis`, jump
    table at `0x169DA8`, **six arms**: `48000, 44100, 24000, 22050, 30000,
    15000`, default from **6** (not 5).
  * **`[C]` every arm's VALUE — and the pitch work was answering the wrong
    question.** Two questions were being conflated:
    1. *What rate does the K2000 ASSIGN to code N?* — **the ROM answers it.**
    2. *What rate was the material RECORDED at?* — pitch cannot answer it,
       and **a device-faithful conversion does not need it.**

    Only (1) is on the conversion path. (2) is a fact about Roland's
    mastering. **See the corroboration below; the rate row is closed for
    conversion purposes.**
  * **`[?]` (2) remains open and is deliberately kept apart** — whether the
    material is actually at the rate its code claims. Unanswerable by pitch
    (three octave pairs, two disagreeing pitch references), and not needed.
  * **`[?]` code 0 is additionally not measurable at all** — 31 of 45
    records defeat the pitch estimator; the material is percussive.
* **RATE CONSUMPTION: `[C]`, and corroborated by a convergence that COULD
  have disagreed.** `0x169DE2`, straight after the six-arm dispatch, turns
  the rate into two object fields via a log table at `0x1F9602` against
  **96000**:

      a0@(4)  = root*100 - 1200 - 1200*log2(rate/96000)     WORD
      a0@(28) = 1000000000 / rate                           LONG

  **Those are our `Soundfilehead.maxPitch` and `samplePeriod`** — fitted in
  `docs/KRZ_FORMAT.md` §3.1 from real `.KRZ` files, with no access to the
  firmware, as `round(100·rootkey + 1200·log2(48000 / rate))` and
  `round(1e9 / rate)`.

  **The algebra is an identity**, `−1200 − 1200·log2(rate/96000) ≡
  1200·log2(48000/rate)`, and the two agree **exactly on all 30
  combinations** of six rates × five root keys (max difference **0** cents).

  > **This is the convergence the parser agreement was not** — as far as it
  > goes. One side fitted a log form to observed files without seeing the
  > ROM; the other read a log table against 96000 out of the ROM without
  > seeing the corpus. **A misread jump table would not have produced the
  > 48000 constant**, and our 48 kHz ceiling falls out of their 96000 halved,
  > which neither side predicted. It also independently confirms **code 5 =
  > 15000**, which we had folded into the default.
  >
  > ⚠ **But the two columns do NOT have the same strength, and the agreement
  > hid that.** See below — `samplePeriod` is read off the instruction
  > stream; `maxPitch` is a closed form that **the firmware does not
  > evaluate**.

  **The two fields are `[C]` and `[S]`, not both `[C]`:**

  | field | strength | why |
  |---|---|---|
  | `samplePeriod` | **`[C]`** | `0x18352C` is a **32-iteration restoring division** — shift, rotate, conditional subtract, set quotient bit. The remainder is discarded and **there is no rounding step anywhere in it.** Exact, and truncating. |
  | `maxPitch` | **`[C]`** | the firmware does a **descending search of a log table** — it evaluates no logarithm — but the table has now been read, and its output **is** our formula on every rate the dispatch can produce. See below. |

  > **What the identity check actually established, stated narrowly because
  > this project overstated it.** Verifying that
  > `−1200 − 1200·log2(rate/96000) ≡ 1200·log2(48000/rate)` compares **two
  > closed forms**, and **the firmware runs neither.** Our form is fitted to
  > real `.KRZ` files, so it is corroborated against *outputs the table
  > produced* — on the rates and roots the corpus happens to contain. Their
  > form is the continuous function the table approximates.
  >
  > **The table's own resolution could place an entry a cent either side and
  > both sessions would be blind to it**: one fitted to the table's outputs,
  > the other checked algebra against that fit. *An identity between two
  > closed forms is not a verification of an implementation.*
  >
  > **The table was then read, and the check came back clean.** It runs
  > *backwards* from `0x1F9602`, addressing `0x1F9602 + 2i` for `i = 0 …
  > −9600`, so it occupies `0x1F4B02 … 0x1F9602`: **9601 `u16` entries, one
  > per cent**, each `round(65536 · 2^(i/1200))` with `i = 0` saturated at
  > `65535`. **Reproduced independently here** — eight probes match the model
  > with no mismatches, and simulating the descending search over all six
  > dispatch rates gives:
  >
  >     code   rate   ratio    fw i   fw cents   continuous     dev
  >        0  48000   32768   -1200          0        0.000   +0.000
  >        1  44100   30105   -1347        147      146.707   +0.293
  >        2  24000   16384   -2400       1200     1200.000   +0.000
  >        3  22050   15052   -2547       1347     1346.707   +0.293
  >        4  30000   20480   -2014        814      813.686   +0.314
  >        5  15000   10240   -3214       2014     2013.686   +0.314
  >
  > **Worst deviation 0.314 cents, and the firmware's integer is
  > `round(continuous)` on all six.** So
  > `round(100·rootkey + 1200·log2(48000/rate))` is **not an approximation of
  > what the K2000 emits — it is what the K2000 emits.** The corpus fit was
  > exact and now we know why.
  >
  > **The operational answer, which is what the question was for: the table
  > cannot contribute a `maxPitch` difference to a byte-diff. If one appears,
  > it is a bug in the writer.**
  >
  > ### ✅ And it is now confirmed against bytes the DEVICE emitted
  >
  > **14 type-134 sample bodies, dumped over SysEx from banks Jan imported
  > from a Roland disc**, are identical in every column: `root = 60`,
  > **`maxPitch − 100·root = 0`**, `samplePeriod = 20833`. Zero is the
  > code-0 arm exactly.
  >
  > **So the whole chain is closed on device output** — `record[+44] & 15` →
  > jump table → `movel #48000` → `(rate << 16)/96000` → the `0x1F9602`
  > search → `root·100 − 1200 − offset`. Until now it rested on the
  > instruction stream plus this project's corpus fit, **with no device
  > output anywhere in it.**
  >
  > ⚠ **But `samplePeriod = 20833` does NOT settle the truncation question**,
  > and the session that produced the dump said so rather than leaving it
  > implied. **48000 is one of the three rates where rounding and truncation
  > agree.** Only codes **1 (44100), 2 (24000) and 5 (15000)** discriminate —
  > 22676/22675, 41667/41666, 66667/66666. **The truncation finding still
  > rests on the instruction stream alone**, and settling it on hardware
  > needs an import of material at one of those three rates.
  >
  > *`maxPitch` was `[S]` for twenty minutes on entirely correct grounds, and
  > that is not undone by the outcome:* **nothing before the reading
  > distinguished this result from a one-cent table.** A caveat that resolves
  > favourably was still right to raise.

  **What a converter writes:**

  | code | rate | `samplePeriod` ns | `maxPitch − 100·root` |
  |---:|---:|---:|---:|
  | 0 | 48000 | 20833 | 0 |
  | 1 | 44100 | 22676 | 147 |
  | 2 | 24000 | 41667 | 1200 |
  | 3 | 22050 | 45351 | 1347 |
  | 4 | 30000 | 33333 | 814 |
  | 5 | 15000 | 66667 | 2014 |

  > ⚠ **The `samplePeriod` column above is the CONTINUOUS value. The device
  > truncates** — write `20833, 22675, 41666, 45351, 33333, 66666` to match
  > it. The column is kept as the true period because that is what this
  > project currently writes; see `§KRZSAMPPERIOD` for which to choose.
  >
  > **The cents column is `[C]`** — the table has been read and emits exactly
  > these values.

  > ⚠ **One real difference, found by running the check: we ROUND where the
  > firmware TRUNCATES.** `a0@(28)` is integer division; `_compute_sample_period`
  > is `round()`. On rates **44100, 24000 and 15000** that is a 1 ns
  > disagreement (22676/22675, 41667/41666, 66667/66666). Irrelevant to
  > playback, **visible in any byte-diff against a K2000's own import** —
  > see `TODO.md` / `§KRZSAMPPERIOD`.

* **LOOP POINTS: `[C]` CLOSED** — `altStart`/`loopStart`/`loopEnd` as **24-bit
  LE at `+17`/`+21`/`+25`, in samples**, `loopStart` signed with negative as
  the no-loop sentinel. 99.5 % consistent on CD 2, 95.0 % on CD 1.
  **This project's earlier `[C-neg]` on these fields is RETRACTED** — see the
  record section above for the misaligned read that produced it.
* **LOOP MODE: `[C]` the two that matter are named — from the corpus, not
  from the flag byte.** Characterising every record on both discs by its own
  loop geometry:

  | mode | n | median loop length | median loop ÷ sample | reading |
  |---|---:|---:|---:|---|
  | **0** | 3486 | **60 200 samples** | **0.762** | **LOOPED** — a real sustain region |
  | **2** | 6322 | **4 samples** | 0.000 | **ONE-SHOT** — 80 % have a loop of ≤ 8 samples, the terminal-hold convention |
  | 4 | 72 | 4 | 0.001 | bimodal: 54 % terminal-hold, the rest real loops |
  | 1, 3, 5 | 3, 4, 2 | — | — | too few to characterise |

  **Modes 0 and 2 are 9808 of 9889 records (99.2 %)**, so naming those two
  names the format in practice.

  > ✅ **The disagreement with the firmware trace DISSOLVES — neither horn.**
  > The trace groups modes 0 and 2 together (both "nothing, no loop flag"),
  > and this was recorded as *"either the arms are misread or the K2000 plays
  > mode-0 material as one-shot"*. **It is neither: the GEOMETRY already
  > carries the distinction, so no flag is needed to separate them.** Pooled
  > over both discs:
  >
  > | mode | n | median loop length | median `loopEnd ÷ length` |
  > |---|---:|---:|---:|
  > | 0 | 3486 | **60 200 samples** | 0.977 |
  > | 2 | 6322 | **4 samples** | 0.948 |
  > | 4 | 72 | 4 samples | **0.996** |
  >
  > **A 4-sample loop at the tail is a terminal hold** — audibly a one-shot
  > that stops dead, which is how a sampler with no loop-disable expresses
  > "no loop". A 60 000-sample loop is a sustain. The two need no flag to be
  > told apart, and the firmware accordingly does not set one.
  >
  > **And it explains mode 4's `loopEnd += 1`:** mode 4 is a terminal-hold
  > variant sitting even closer to the end (0.996, 75 % beyond 0.97·length),
  > so the firmware's increment is a **one-sample correction on a four-sample
  > hold** — which is only meaningful at that scale. *`[S]`, since the
  > K2000's treatment of a 4-sample loop has not been observed on hardware.*
  >
  > **The conversion rule this gives us:** a Roland mode-2 or mode-4 sample
  > should be written in **our own one-shot form** — `sampleLoopStart` and
  > `sampleEnd` collapsed onto the PCM end, `flags = 0xF0` — not as a literal
  > 4-sample loop. Copying the geometry verbatim would produce a 4-sample
  > loop on a machine that has a real loop-disable bit.
  >
  > **`[?]` modes 1, 3 and 5 stay unnamed** — n = 3, 4 and 2 across both
  > discs. The firmware gives them distinct arms (bit 3 for 1/3, bit 0 for
  > 5/6), so they are real loop *types*; the corpus simply does not contain
  > enough of them to characterise.

* **`[?]` `body[1]`, where the mode enum writes, is not a byte this project
  can name.** Under `docs/KRZ_FORMAT.md` §3.1 it falls inside `baseID`, which
  is `1` in every real soundset and cannot carry `0x30` plus mode bits — so
  either the RAM object's first bytes differ from the file form we document,
  or the trace's `body` origin slips for that one write. **Our loop-enable
  bit is `Soundfilehead+1` = `body[13]`** (`0x80` inverted: clear = loop),
  which the trace does not mention at all.
* **COMPRESSION: `[?]` nothing compressed found on either disc — and two
  tests that were meant to find it CANNOT.** Stated in full because this
  document raised the bar for negatives:
  * **No flag exists in the 48-byte record.** Every byte was censused on
    both discs. The one unexplained low-cardinality field is `+44`'s **high
    nibble**, which the rate dispatch masks off (`andiw #15`) — set on **43
    of 5761 records on CD 1, 0 of 4128 on CD 2**. Those 43 are all
    percussion (`BD`, `SD`, `HH`, `CYM`, `TOM`, ride), all `mode = 2`, all
    `rate = 0`, all `root = 60` — **and their audio decodes as ordinary
    16-bit LE PCM with entirely normal statistics.** Whatever that bit
    marks, it is not a decode difference.
  * **Test 1, waveform smoothness: cannot discriminate.** The least-smooth
    real samples (1.08 … 1.56) sit exactly where a deliberately *wrong*
    decode sits (big-endian median 1.19) — and they are `CHO:SSS`, cymbals,
    drums and a shakuhachi. **Sibilants and cymbals are near-white noise**,
    so the metric cannot separate compressed data from noisy audio.
  * **Test 2, byte entropy: cannot discriminate.** 16-bit PCM should show a
    low-entropy high byte; **651 of 4128 records exceed 7.0 bits on both
    bytes**, because loud material fills the 16-bit range. The signature
    fires on 16 % of ordinary audio.

  **So the honest statement is narrow: on these two discs no compressed
  sample has been identified, and the two instruments tried are incapable of
  identifying one.** That is *not* "the format has no compression" — the
  S-7xx supports it and this library may simply not use it. **A third disc
  family, or the decompressor in the ROM, is what would settle it.**

### What is left, and why neither gap stops a converter

**1 — three loop modes are unnamed, covering 0.08 % of the material.**
Measured over **all seven images, 20 018 samples, five disc families**:

    mode 0   9440  (47.16 %)   LOOPED           named
    mode 1      4  ( 0.02 %)                    not named
    mode 2  10265  (51.28 %)   ONE-SHOT         named
    mode 3      8  ( 0.04 %)                    not named
    mode 4    296  ( 1.48 %)   one-shot variant  named
    mode 5      5  ( 0.02 %)                    not named

**17 samples out of 20 018.** *Jan's further archives were opened specifically
to test whether the rarity was an artefact of one library. It is not* — the
rate holds at ~0.08 % across five independent releases, so it is a property
of Roland material rather than of our sample. **A converter handles 99.92 %
of it today** and needs a stated fallback for the rest.

> ## ❌ RETRACTED 2026-09-22 — THE DISPATCH HAS FOUR BLOCKS AND THIS READ ONE
>
> ~~`0x169E6C` dispatches `record[+36]` as `0 → normal · 1 → bset #3 ·
> 2 → normal · 3 → bset #3 · ≤6 → normal · >6 → skip loop setup`, so mode 5
> is not distinguished at all and only modes 1 and 3 are a separate type. And
> modes 0, 2 and 4 take identical arms, so the distinction cannot be
> flag-carried.~~
>
> **That is the FIRST of four flag blocks, and the conclusions drawn from it
> are wrong.** Raised by an external review (QWEN38F, 2026-09-22) and then
> **re-derived here from the ROM rather than taken** — `k2000_v387j.bin`,
> md5 `ab658571677603ee1bccb9cbe329aecd`, file offset = address − `0x100000`,
> every branch target decoded by hand:
>
>     169e68  206f 007c        moveal %sp@(124),%a0
>     169e6c  1028 0024        moveb  %a0@(36),%d0      ; the mode
>     169e70  4a00 / 6724      tstb; beqs -> 169e98     ; 0 -> no bit here
>     169e74  0c00 0001 / 6716 cmpib #1; beqs -> 169e90
>     169e7a  0c00 0002 / 6718 cmpib #2; beqs -> 169e98
>     169e80  0c00 0003 / 670a cmpib #3; beqs -> 169e90
>     169e86  0c00 0006 / 630c cmpib #6; BLS  -> 169e98 ; <=6 continues
>     169e8c  6000 00b4        bra 169f42                ; >6 skips the lot
>     169e90  2054 08e8 0003 0001   bset #3,%a0@(1)      ; modes 1,3
>     ...
>     169ee6  0c28 0002 0024 / 6708 cmpib #2,%a0@(36); beqs -> 169ef6
>     169eee  0c28 0005 0024 / 6608 cmpib #5,%a0@(36); bnes -> 169efe
>     169ef8  08e8 0007 0001   bset #7,%a0@(1)          ; MODES 2 AND 5
>     169f02  0c28 0004 0024   cmpib #4  -> andb #-4; bset #1   ; mode 4
>     169f20  0c28 0005 0024   cmpib #5  -> \
>     169f28  0c28 0006 0024   cmpib #6  -> andb #-4; bset #0   ; modes 5,6
>     169fd2  0c28 0004 0024 / 6606 / 52a8 0014  ; mode 4: body+20 += 1
>
> **The corrected table:**
>
> | mode | what the firmware sets on `body[1]` |
> |---|---|
> | 0 | nothing |
> | 1 | `bset #3` |
> | **2** | **`bset #7`** |
> | 3 | `bset #3` |
> | 4 | `andb #-4`, `bset #1` — and `body+20 += 1` |
> | **5** | **`bset #7` AND `andb #-4`, `bset #0`** — two arms, not one |
> | 6 | `andb #-4`, `bset #0` |
> | ≥7 | nothing at all (branches past every block) |
>
> ### ✅ AND BIT 7 IS OUR OWN INVERTED `0x80`, ARRIVING FROM THE OTHER SIDE
>
> `Soundfilehead.flags` bit `0x80` is **one-shot**, inverted — clear means
> looped (`docs/KRZ_FORMAT.md` §3.1, HW-confirmed 2026-06-16). And the
> firmware sets bit 7 for **mode 2, which this document's own corpus table
> names ONE-SHOT**, and leaves it clear for **mode 0, named LOOPED**.
>
> **So the distinction IS flag-carried, and the retracted paragraph had it
> exactly backwards.** Two independent routes — a K2000 disk-save byte-diff
> in 2026-06 and the Roland importer's own dispatch — agree on the same bit
> with the same inversion.
>
> **Blast radius of the error:** mode 2 is **10 265 of 20 018 samples
> (51.3 %)**. An importer built from the retracted table would have written
> every one of them as *looped*, silently, because the table said mode 2 sets
> nothing.
>
> *Method note: the retracted reading was not a misread instruction. It was a
> correct reading of one block, generalised to a dispatch that has four. The
> first block answers "does this mode set bit 3", and that answer was right.*
>
> **`[?]` What bit 3 does is untested, and the prediction's CONSTANT was
> wrong.** It was offered as *"a mode-1/3 import should carry `0x78` where
> everything else carries `0x70`"*. **The device's actual base is `0xB0`**
> (see below), so the prediction is **`0xB8`**.
>
> Scanned **11 798 `Soundfilehead` headers across 333 distinct `.KRZ` files:
> bit 3 is set on ZERO of them** — *not a refutation*, since our corpus holds
> no Roland-imported material and cannot exhibit the bit. Bit 3 is also clear
> on all 14 device-emitted bodies, which is **equally not a test**: kit
> material is modes 0/2/4, and modes 1/3 are 12 of 20 018 across five
> families, so a 14-sample import was never going to contain one.
>
> **`[S]`, constant corrected. Testing it needs a deliberate import of a
> known mode-1 or mode-3 sample — a hardware ask, not offline work.**
>
> The 17 rare-mode records are listed in the corpus notes; modes 1 and 3
> carry both tiny end-loops (~600 samples at 0.999 of length) and large
> mid-sample loops (~30 000 at 0.50), so **geometry does not separate them
> either.**

**2 — compression is UNTRACED, and three separate methods cannot settle it.**
Not "the format has none". The three, stated so nobody repeats them:

1. **No flag in the sample record** — every byte censused, now across
   **20 018 records in five families**. The one unexplained low-cardinality
   field is `+44`'s high nibble (152 records, two families, all percussion or
   strings) — and `[C-neg]` **the K2000 never reads it**: exactly one access
   to `record[+44]` exists in the whole Roland region and it is
   `andiw #15`, with no high-nibble test anywhere. *Provably not consumed, so
   a device-faithful converter ignores it by construction.*
2. **Audio statistics cannot discriminate** — both tests fail, see the
   compression entry in the record section.
3. **The object-building path has no decode branch** (`0x169Bxx`–`0x169Fxx`).
   **But the bulk transfer itself is untraced**, and a decompressor invoked
   from inside it would not appear where anyone has looked.

**There is nothing here to decode even if the decoder were known.** A
converter is unaffected until compressed material turns up, and should say
so rather than claim support. **The open route is the bulk transfer in the
ROM.**

**And one question deliberately NOT on that list:** whether Roland's material
is actually recorded at the rate its code claims. Pitch cannot answer it —
three octave pairs, two disagreeing references — and **a device-faithful
conversion does not need it**, because the K2000 assigns the rate from the
code regardless of what the audio is.
* ⚠ **`size × 9216` is the PADDED extent, by construction.** The audio ends
  somewhere inside the last block and the remainder is zero-filled. That is
  benign for *locating* a sample and **fatal for anyone who trims on it** —
  the stored value and the real value differ on every sample whose audio does
  not exactly fill its final block, which is nearly all of them. The real end
  has to come from the loop/length data that `O3` is still missing.

**An extractor that ignores loops produces audio with no sustain, which is
not a conversion.** The remaining search is the patch/partial records and the
loader's caller chain, **not** more of the 48-byte record.

**Blocks:** K2000 Roland → KRZ — the whole path.

### O4 — The Roland disc tooling · **largely answered 2026-09-21**

Was: *"hardcoded absolute offsets … validated on three discs of one family;
against anything else there is no evidence at all."* **Jan's further archives
were opened and the offsets hold across all of them.**

| images | families | sample records | loop invariant |
|---:|---:|---:|---:|
| **7** | **5 distinct releases** | **20 018** | 95.0 % … 100.0 % |

The fixed bases `0x255800` (sample records), `0x2B5800` (audio), `0x1D5800`
(partials) and `0xA5800` (patch directory) land on real data in **every
image**, across sizes from 130 MB to 682 MB, three different mastering years,
and both `.iso` and `MODE1/2048` `.bin`+`.cue` packaging. Every image is
2048-byte sectors with **no header offset** — the `.bin` files divide exactly
by 2048 and not by 2352.

**What is still untested**, and the entry is kept for it: an **S-750**, a
**floppy**, a real **SCSI drive**, and an image that genuinely *does* carry a
sector header. All five families here are CD-ROM masters of the same era.

**Degrades:** K2000 Roland → KRZ and EOS Roland → E4B — **much less than it
did.**

### O5 — K2000 Roland: key/velocity ranges · ⚠ **a DEVICE-CONVERTED reference now exists**

> ## 12 banks the K2000 itself produced from a Roland disc — 137 programs, 237 keymaps, 412 samples
>
> `HD0_K2X_HD2G-20260817.img.lzo`, folder `-RLNDCD2` (Jan, 2026-09-22).
> **This is the first ground truth this arm has ever had**: for Roland the
> rule is that matching the device IS the specification, and until now
> nothing on this machine could say what the device does.
>
> ### ✅ THE KEYMAP ALLOCATION IS FIRMWARE-WIDE, NOT AN AKAI QUIRK
>
> | body size | count |
> |---:|---:|
> | 156 | 41 |
> | 284 | 16 |
> | 412 | 104 |
> | 540 | 51 |
> | 668 | 24 |
> | 796 | 1 |
>
> **Every one is `28 + k × 128`** — the same quantised ladder measured on the
> AKAI arm, now confirmed on a *different importer* and a different disc
> family. So the content-independent allocation is a property of the
> machine's keymap builder, not of the AKAI path. *And `796` occurs: a full
> 128-entry allocation does happen, once in 237.*
>
> ### ✅ THE DEVICE SPLITS STEREO INTO L/R SAMPLES AND TWO KEYMAPS
>
> Samples arrive as `…L` / `…R` pairs and each program carries a `-1` / `-2`
> keymap pair. On the disc that is one partial with **two zones at `sub[4]`
> `−32` and `+32`** — hard left and hard right, the stereo pair this
> project's own pan formula already decodes.
>
> ### ⚠ AND OUR PARTIAL → PRESET MODEL IS ONE LEVEL OFF
>
> `SYN:K2000 DCF 1/2/3` in the device bank correspond to disc partials
> `SYN:K2000 DCF AA/AB/AC` — roots 48, 60, 72. **The device makes ONE program
> from a GROUP of partials**, keyed across the keyboard; this project's
> reader makes one preset per partial. *Not wrong, but coarser than the
> device, and the grouping is the patch level we have not decoded.*
>
> ### ❌ AND THE OBVIOUS RULE FOR THE KEY SPLITS IS REFUTED
>
> The `DCF` case splits at `53|54` and `65|66` for roots 48/60/72 — exactly
> the midpoints, which is a very good-looking hypothesis from one program.
> **Tested over 237 boundaries in all twelve banks: the midpoint rule is
> exact on 16 (6.8 %)**, with the residual spread over `+1` (86), `+2` (29),
> `+3` (22) and a tail at `+49`/`+61` that is name-collision noise in the
> join.
>
> **So the key splits come from somewhere else — almost certainly the patch
> level — and one program fitting a rule perfectly is worth 6.8 %.**
>
> ### ✅ `[C]` THE SOURCE IS THE PATCH'S 128-BYTE PER-KEY TABLE AT `+32` — 2026-09-22
>
> Joined the device's **programs** to the disc's **patches by exact name**
> (the earlier attempt joined truncated *keymap* names, which is what the
> 46.4 % was measuring), then compared each program's keymap boundaries
> against the patch's table read at MIDI base **21**:
>
> | over 137 device programs | | |
> |---|---:|---:|
> | boundary sets **identical** | **83** | 60.6 % |
> | device is a strict **superset** — 30 with one extra boundary, 2 with two | **32** | 23.4 % |
> | **explained** | **115** | **83.9 %** |
> | neither | 22 | 16.1 % |
>
> **The superset case is the model working, not failing:** the patch table
> splits keys between PARTIALS, and a partial holding several samples across
> its own range adds further boundaries inside that span. *So the table gives
> the partial splits and the keymap refines them.*
>
> **Against 6.8 % for the root-midpoint rule it replaces**, on the same 237
> boundaries.
>
> ### ❌ AND THE PARTIAL LINKAGE IS NOT SETTLED — a third mechanism refused
>
> `+256 … +511` of the patch record decodes, on `SYN:K2000 DCF 1`, as **128
> LE16 global partial indices**, `0xFFFF` for unused — `872 / 873 / 874` over
> exactly the key runs the `+32` slot table gives. It looks like the missing
> linkage and **it does not survive the corpus:**
>
> | disc | patches | `+32` and `+256` boundaries agree | out-of-range indices |
> |---|---:|---:|---:|
> | 60s/70s CD1 | 197 | **90.4 %** | 0 |
> | Solo Strings | 200 | 85.5 % | 0 |
> | LA Composer 4 | 103 | 65.0 % | 0 |
> | ROL-B | 916 | 53.9 % | 0 |
> | String Masters | 2302 | 40.4 % | **1277** |
> | **ROL-A** | 889 | **0.1 %** | 0 |
>
> **0.1 % on one disc and 90 % on another is not a field being read wrongly,
> it is a field that is not always there.** Left `[?]` rather than published:
> *this is the third mechanism today whose first case fit perfectly, and the
> first two were refuted by exactly this kind of sweep.*

A first-cut import would carry the prototype program's values for all of them
— **which is exactly what the K2000 itself does**, so this is a quality
ceiling rather than a blocker.

### O6 — The K2000's AKAI builder · ✅ **ANSWERED ON HARDWARE 2026-09-21**

> ## ✅ THERE IS NO BUILDER. THE IMPORT WRITES ONE BYTE.
>
> Jan imported the volume `SOPRANO SAX2` (6 programs, 19 samples, 0.40 MB)
> on the K2000R from an AKAI S3000-form CD; `k2kremote` read the result back
> over SysEx. **Programs 200–205 versus the ROM template Program 199:**
>
>     199 vs 200 .. 205   1 byte differs -> offset 189
>     200 vs 201 .. 205   1 byte differs -> offset 189, values 200..205
>
> Offset 189 is **`CAL[12]`** — layer 0 at 48, the `0x40` segment spanning
> 176–207, so `189 − 177 = 12` — the low byte of the keymap id.
>
> > **It is a TWO-byte field, and bank 200 hid that.** Programs 300 and 400
> > differ from 199 at offsets **188 AND 189**: `CAL[11] = 1` with
> > `CAL[12] = 44` and `144`. The bank-200 programs looked like a one-byte
> > diff only because their ids are under 256 and the high byte matched 199's
> > zero. *A field measured entirely inside one byte's worth of range.*
>
> **Every imported program is Program 199 verbatim with the 16-bit keymap id
> written at `CAL[11:13]`, and nothing else.** For a multi-layer source the law
> extends exactly, and lands on machinery this project already had:
>
>     1-layer programs  differ from 199 at  [188, 189]
>     2-layer programs  differ from 199 at  [2, 188, 189, 272]
>        2   = the layer count in the program header
>        272 = the start of the appended second layer
>     program 302 layer 1 vs layer 2        -> 1 byte differs
>     program 302 layer 2 vs 199's layer 1  -> 2 bytes, at layer offsets 140/141
>                                              = CAL[11:13] again
>
> > **THE COMPLETE LAW: clone Program 199, set the layer count, append a copy
> > of Program 199's layer 1 per extra layer, and write each layer's 16-bit
> > keymap id at `CAL[11:13]`. Nothing else.**
>
> **And that is exactly the template mechanism read out of the ROM months
> ago** — `create_object(132, id, size=0x112)`, `memcpy(new_body,
> program199_body, 0x110)`, then per extra layer grow by `0xE0` and
> `memcpy(new_body + 48 + 224k, program199_body + 48, 224)`. *The firmware
> reading and the machine agree byte for byte, on the arm where the firmware
> reading was never confirmed.* Not "the filter values
> disagree with the AKAI source": the program is byte-identical to the
> template. **Confirmed across three volumes, 7 and 19 keygroups, melodic and
> drum** — and a drum map was the place to expect the importer to write more,
> if it ever did. It does not.
>
> | field | AKAI source | 199 | imported 200–205 |
> |---|---|---|---|
> | filter cutoff (`HOB0[1]`) | 81 / 91 / 52 | 0 | **0** |
> | filter type (`HOB0[0]`) | 4-pole LP | 62 = NONE | **62** |
> | filter-env route (`HOB0[5]`) | on for 2 of 6 | 0 | **0** |
> | resonance (`HOB1[1]`) | — | 0 | **0** |
> | amp attack | 0 / 50 / 74 | template | **template** |
> | program loudness | 80 / 84 | template | **template** |
>
> ### ⚠ HOW CERTAIN IS THIS? — asked by Jan 2026-09-22, and the answer is not "100 %"
>
> **The claim is MEASURED, not traced, and that is the distinction that
> matters here.** Everything in this topic that flip-flopped — `format 5 =
> AKAI`, "the AKAI staging record", the device-type byte — was a
> *firmware-trace* claim, and every one of them was wrong at least once. **No
> ROM address is load-bearing in the one-byte result.** It is a SysEx
> read-back of what the machine produced, diffed against Program 199.
>
> | | |
> |---|---|
> | programs measured | **32**, across six volumes and two disc forms |
> | keygroup counts | 19 · 7–8 · 1 and 7 |
> | kinds | melodic, drum, **mono and stereo** |
> | retracted since? | **no** — the corrections after it were about the keymap *allocation* and about layers-vs-slots, which refined the field from one byte to `CAL[11:13]` |
>
> **And a coincidence cannot explain it.** The AKAI sources carried filter
> 81 / 91 / 52 where Program 199 has `NONE`. If the importer converted
> filters at all, the diff would show it — on none of the 20.
>
> ~~**The honest gap: all three volumes came from ID5, the S3000-form disc.**~~
> **Closed the same day — see the run below.**
> The AKAI path is selected by a device-type byte rather than a format code,
> so there is no strong reason to expect the S1000 form to differ — *but that
> is an argument, and this topic has punished arguments repeatedly.*
>
> > ### ✅ RUN 2026-09-22 — THE PREDICTION WAS REFUTED ON 5 OF 6, AND THE CLAIM CAME OUT STRONGER
> >
> > Jan loaded the first volume of each of the first three partitions of
> > **ID7, the S1000-form disc** (`Voice Spectral II`). `k2kremote` read back:
> >
> >     prog   diff vs 199                          keymap  CAL[7:9]
> >     200    [57, 185, 189, 259, 271]              200       201
> >     201    [57, 185, 189, 259, 271]              202       203
> >     202    [57, 185, 189, 259, 271]              204       205
> >     203    [57, 185, 189, 259, 271]              206       207
> >     300    [57, 184, 185, 188, 189, 259, 271]    300       301
> >     400    [188, 189]                            400         0   <- as predicted
> >
> > **Five are STEREO and one is MONO, and the mono one matches the
> > prediction byte for byte.** The keymap names say so: `H PHRS 01AMJ-L-1` /
> > `-R-1`, `SCAT 01-L-1` / `-R-1`, against `WHISPERS  -1` with no suffix.
> >
> > **THE EXTRA BYTES ARE THIS PROJECT'S OWN DOCUMENTED STEREO WIRING**, and
> > every offset type-checks against `docs/KRZ_FORMAT.md` without adjustment:
> >
> > | offset | = | field | 199 | stereo import |
> > |---:|---|---|---|---|
> > | 57 | `lyr[8]` | stereo marker | `0x04` | **`0x24`** |
> > | 184/185 | `CAL[7:9]` | second keymap id | 0 | **id + 1** |
> > | 188/189 | `CAL[11:13]` | first keymap id | — | the keymap |
> > | 259 | `0x53[2]` | pan **+7**, hard right | `0x00` | **`0x70`** |
> > | 271 | `0x53[14]` | pan **−7**, hard left | `0x04` | **`0x94`** |
> >
> > `0x70` / `0x94` are *verbatim* what §4.3 of our own format doc records for
> > stereo placement — **so the device's stereo wiring is byte for byte what
> > this project's KRZ writer already emits**, confirmed from the device's
> > output rather than from the ROM.
> >
> > **AND NOTHING ELSE MOVED.** `HOB0[0] = 62` (filter NONE), `HOB0[1] = 0`,
> > `HOB1[1] = 0` on all six, identical to 199. No filter, cutoff, resonance,
> > envelope or LFO is converted on the S1000 arm either.
> >
> > ### So the claim is now about the IMPORTER, not about one disc
> >
> > **26 programs. Two disc forms. Melodic, drum, mono and stereo.** The
> > importer clones Program 199, writes the keymap pointer(s), and for a
> > stereo source sets the stereo flag, the second keymap slot and the ±7 pan
> > pair — **mechanical wiring the K2000 needs to play two channels, not
> > conversion of AKAI parameters.**
> >
> > *The prediction failing is what made this worth running: a sixth mono
> > program confirming it would have added one observation, and five stereo
> > ones refuting it identified the entire remaining mechanism.*
> >
> > > **And it settles a disagreement between this project and `eosed` in
> > > which both were right.** This project said `CAL[7:9]` is used;
> > > `k2kremote` measured it as `0` on everything then available. **Both
> > > held, because ID5's material is entirely mono.** *The inference route
> > > was still wrong — the `DBL.REED -1/-2` objects are two layers — so a
> > > correct conclusion reached from a wrong reading, which is the outcome
> > > this record keeps having to separate out.*
> >
> > ### ✅ AND THE MONO CASE THICKENED FROM 1 TO 7 — Jan, 2026-09-22
> >
> > *"A single mono example seems to be a bit too little."* Three more
> > all-mono ID7 volumes — `09 PROC PHRS`, `02 LY SHORT`, `24 VB SHORTS`,
> > **169 keygroups across six programs, every one carrying AKAI filter 99**:
> >
> >     prog  diff vs 199   CAL[7:9]  lyr[8]  0x53[2]  0x53[14]  HOB0[0]
> >     500   [188, 189]        0      0x04    0x00     0x04       62
> >     501   [188, 189]        0      0x04    0x00     0x04       62
> >     600   [188, 189]        0      0x04    0x00     0x04       62
> >     601   [188, 189]        0      0x04    0x00     0x04       62
> >     800   [188, 189]        0      0x04    0x00     0x04       62
> >     801   [188, 189]        0      0x04    0x00     0x04       62
> >
> > **The widest filter net *then* thrown, and it caught nothing.** 169
> > keygroups at AKAI filter 99, all arriving as `HOB0[0] = 62` = NONE.
> > *Superseded: those 169 keygroups carried ONE filter value, so an importer
> > mapping 99 → NONE and converting everything else would have passed. The
> > S3000 stereo load put **eleven** distinct values from 40 to 90 across 559
> > keygroups through the same test, and `HOB0[0] = 62` on all 52 programs.*
> >
> > ### ✅ BOTH ARMS ARE MEASURED — and this document already said so, 140 lines up
> >
> > ~~One arm of the prediction was NOT exercised: all six keymap ids are
> > `≥ 256`, so `id < 256 → [189] only` remains untested.~~
> >
> > **It was exercised by the very FIRST AKAI load.** Program 199's keymap id
> > is `1`, high byte `0`; `SOPRANO SAX2` on ID5 gave keymap ids **200…205**,
> > all below 256, all with high byte `0` — so only the low byte moves and
> > the diff is **`[189]` alone**, on six programs.
> >
> >     [189]        6 programs, ID5,  keymap ids 200-205  (< 256)
> >     [188, 189]  12 programs, ID7,  keymap ids >= 256
> >
> > > **⚠ AND THE ANSWER WAS ALREADY IN THIS FILE WHEN THE CAVEAT WAS
> > > WRITTEN.** The `O6` entry above states it outright — *"the bank-200
> > > programs looked like a one-byte diff only because their ids are under
> > > 256 and the high byte matched 199's zero"* — and this caveat was added
> > > **later**, 140 lines below it, saying the same branch was untested.
> > >
> > > **Not a stale line that outlived its measurement: a NEW line
> > > contradicting an older one in the same document.** The usual failure
> > > here is a claim surviving its own refutation; this is the reverse, and
> > > it is worse, because nothing about the older text looked out of date.
> > > *Caught by `k2kremote` re-reading a read-back they had already
> > > published, after both of us had repeated the caveat back to each other
> > > as if confirming it.*
> >
> > **The ladder holds and gains a negative:** every keymap `668 = 28 + 5×128`
> > on volumes of 7, 24, 29, 29, 30 and 30 keygroups — **keygroup count does
> > not move the allocation** either.
> >
> > > ### ⚠⚠ AND THE BANKS WERE NOT THE BANKS THEY WERE SAID TO BE
> > >
> > > Jan reported `200ff/300ff/400ff`; the machine had them at **5, 6 and
> > > 8**, and banks 2/3/4 still held the *previous* stereo load.
> > > `k2kremote` scanned all ten banks instead of reading where they were
> > > told — **and reading where they were told would have re-diffed the
> > > stereo import and reported it as the mono result: five programs at
> > > `[57, 185, 189, 259, 271]`, which is VERBATIM the pattern this
> > > project's own prediction named as refuting.**
> > >
> > > **A refutation that arrives in exactly the shape you predicted is the
> > > one to distrust hardest.** It would have been confident, pre-registered
> > > and wrong, and the pre-registration would have made it *more*
> > > persuasive rather than less.
> >
> > ### ⚠ THE PCM IS LOADED TWICE ON THE S1000 ARM — the first behavioural difference between the disc forms
> >
> > Every disc sample becomes **two** 68-byte objects of the same name:
> > 36 → 72, and 60 → 100 / 53 → 100 where the bank's **100-object ceiling**
> > cuts the second block off.
> >
> > **Two hypotheses were offered and both died, which is why this is a
> > finding rather than a guess:**
> >
> > * *this project:* `T_SAMPLE = 38` and the RAM type is `38 + 96 = 134`, so
> >   one object seen through two type codes would duplicate exactly like
> >   this. **Dead** — `k2kremote` only ever enumerated type 134, and all
> >   72 / 100 / 100 ids are **distinct**.
> > * *also this project:* our AKAI reader skips 18 `type 0x00` directory
> >   records on that disc, so perhaps the volumes really hold 2N samples and
> >   our N is short. **Dead** — checked here: none of the 18 belongs to
> >   `09 PROC PHRS`, `02 LY SHORT` or `24 VB SHORTS`.
> >
> > **What it actually is.** The ids form **two complete consecutive blocks
> > of N** (`500…535` + `536…571`), the id gap within a name pair equals the
> > volume's sample count exactly, and objects `500` and `536` differ at
> > **bytes 20…35 and nowhere else**. Against `docs/KRZ_FORMAT.md` §3.1 that
> > span is exactly:
> >
> >     object = KSample (12) + Soundfilehead (32) + 2 x Envelope (12) = 68
> >       +20..23  sampleStart        +24..27  altSampleStart
> >       +28..31  sampleLoopStart    +32..35  sampleEnd
> >
> > **The four 32-bit PCM pointers, and only those.** Same root, same flags
> > (`0x30`, looped), same `maxPitch`, same `samplePeriod` **22675** — the
> > truncated value this project adopted, arriving again unprompted. *Two
> > objects, two distinct regions of sample RAM, the same audio.*
> >
> > **ID5 does NOT do this:** `SOPRANO SAX2` gave 19 objects for 19 disc
> > samples. So this is the **first behavioural difference between the S3000
> > and S1000 arms** found in the whole investigation — and it is a
> > RAM-consumption difference, not a conversion one, so it leaves *"the
> > importer converts nothing"* untouched.
> >
> > **What a user would notice**, and it belongs wherever this import's
> > practical limits are described: **double sample-RAM consumption**, and a
> > **bank filled to 100/100 by a 60-sample volume**, which blocks anything
> > else being imported into it. No distinct sample is lost — the first block
> > is always complete.
> >
> > ### ✅ AND THE STEREO CASE CLOSED WITHOUT A NEW LOAD — the structure is self-evidencing
> >
> > Banks 2/3/4 still held the earlier stereo import and their object lists
> > were already in hand:
> >
> >     bank 2   64 objects   32 distinct names   each name at n and n+32
> >     bank 3   16 objects    8 distinct names   each name at n and n+8
> >     bank 4   20 objects   10 distinct names   each name at n and n+10
> >
> > **The `-L`/`-R` channel split is already INSIDE the distinct-name count**
> > — `HPS01AMJ C-L` and `…C-R` are two different names — so the duplication
> > sits *on top of* it:
> >
> >     bank 2   16 stereo AKAI samples -> 32 channel objects -> 64
> >     bank 3    4 stereo              ->  8                -> 16
> >     bank 4   10 MONO (no -L/-R)     -> 10                -> 20
> >
> > **Bank 4 is the control that makes it airtight:** `WHISPERS` has no
> > channel suffix, is mono, and still doubles. *The duplication is not the
> > channel mechanism wearing a disguise.*
> >
> > **Triple-checked against the disc here:** `01 H PHRS 01` holds 32 samples
> > all carrying `-L`/`-R` = **16 stereo**; `01 SCAT 01` 8 = **4 stereo**;
> > `01 WHISPERS` 10 with no suffix = **10 mono**. All three as computed from
> > the machine side alone.
> >
> > **So the claim is `ID7 duplicates, ID5 does not`** — mono and stereo,
> > six banks across two loads, the same `gap = N` structure in every one.
> >
> > > **`[S]` and one prediction left, needing one load and no new disc:** if
> > > the 100-object ceiling is the **bank's**, then a 49-sample volume gives
> > > **98** objects and a 51-sample one gives 100 with two second-copies
> > > missing. **`11 CLASSMIX1` on ID7 holds exactly 49 samples** (3.56 MB,
> > > all-mono) and is the sharp case.
> >
> > ### ⚠ THE ALLOCATION IS THE ALLOCATOR'S, NOT THE CALLER'S — narrowed 2026-09-22
> >
> > **No caller rounds a size up to 128.** Searched the whole ROM for every
> > round-to-128 idiom — `andil #0xFFFFFF80`, `andiw #0xFF80`, `addil #127`,
> > `addiw #127` — and there are **zero** hits anywhere in the import modules.
> > The keymap creation sites push a size straight out of their stack frame
> > (`movew %a0@(76),%sp@-` and friends) into `create_object`.
> >
> > **So the `28 + k × 128` quantisation happens inside the allocator**,
> > which is consistent with it being content-independent across four import
> > arms — the callers are not choosing it.
> >
> > **And it cannot be traced further statically from here:** `0x103310` is a
> > thunk (`moveal %a5@(0x504),%a0 / jmp`), so `create_object`'s body is
> > reached through a pointer in the A5 globals and is not reachable by a
> > static search. *Closing this needs the allocator's own structures or a
> > live trace, not more grepping — which is worth knowing before anyone
> > spends another evening on it.*
> >
> > ### ✅ AND THREE IMPORT ARMS ARE NOW ON ONE KEYMAP LADDER
> >
> > Every keymap here is **668 = 28 + 5 × 128**, eight of them in one bank,
> > identical, for four programs of differing content. With the AKAI S3000
> > sizes (412/540/668) and the twelve K2000-converted **Roland** banks
> > (156/284/412/540/668/796, 237 keymaps), that is **three arms on the same
> > `28 + k × 128` ladder** — so the content-independent allocation is the
> > machine's keymap builder and was never an AKAI question.

> ## ❌ "THE IMPORTER CONVERTS NOTHING" IS REFUTED — 2026-09-22, and by its own test
>
> The S3000 **stereo** load (`AKAI-B/V2`, `AKAI-B/V4` from AKAI disc AKAI-B)
> fired the refutation clause this project had attached to every one of these
> predictions: *a byte outside the stereo set moved.*
>
>     pattern                                  n   lyr[5]
>     [57, 185, 189, 259, 271]                22     0
>     [57, 184, 185, 188, 189, 259, 271]      14     0
>     [54, 57, 184, 185, 188, 189, 259, 271]   8     3   <-- NEW
>     [2, 189, 272] / [2, 188, 189, 272]       8     0
>
> **Offset 54 is `0x09 body[5]`, the packed VELOCITY WINDOW** —
> `(loMark << 3) | (7 − hiMark)` per `docs/KRZ_FORMAT.md`, full range = 0.
> A value of **3** decodes as loMark 0, hiMark 4.
>
> ### ✅ AND THE DISC SAYS EXACTLY EIGHT
>
> Checked here, with none of the machine-side numbers in view:
>
> | `AKAI-B/V4`, 22 programs | |
> |---|---:|
> | zone velocity ranges `(0,64) (65,100) (101,127)` | **5** |
> | `(0,80) (81,127)` | **3** |
> | full range `(0,127)` | 14 |
>
> **8 restricted on the disc, 8 carrying a non-zero velocity mark on the
> machine.** The population matches exactly.
>
> *And `AKAI-B/V2`'s two "restricted" programs are `(0,123)` against
> `(0,127)` — a difference too fine for an 8-step mark, so they round to 0
> and correctly do NOT appear. The match survives the case that could have
> broken it.*
>
> > **So an AKAI parameter does reach the K2000 object.** Not plumbing, not a
> > keymap pointer, not stereo wiring — **the velocity range of the source
> > keygroup**. The correct statement is now: *the importer converts the
> > KEYMAP GEOMETRY and the VELOCITY WINDOW, and discards filter, envelope,
> > LFO, pan and level.*
>
> **Why every earlier test missed it, and this is the useful part:** 32
> programs across six volumes had already been measured, and **all of them
> were velocity-unrestricted at the source**, so `lyr[5]` was 0 on both sides
> and invisible. *The field was not hidden — the corpus was uniform in it*,
> which is this record's most-catalogued trap and it still took a card
> crossing chosen for a different question to break it.
>
> ### ⚠ AND IT PUTS TWO ENTRIES IN THIS DOCUMENT IN TENSION
>
> This file annotates `54 + 224k` as *"(Akai only, source-derived)"*, while
> the velocity arithmetic at `0x164C66` was later re-attributed to the
> **Ensoniq** builder at `0x16368A` on dispatch evidence.
>
> ### ✅ RESOLVED 2026-09-22 — they are different code, so both hold
>
> **The 92-byte staging record has exactly FOUR users in the whole ROM**, and
> they are one tight cluster: `mulsw #92` occurs at `0x1641DC`, `0x164376`,
> `0x164C76` and `0x164C8E` and nowhere else. `0x164C66` reads
> `staging[zone*92 + 88]`, shifts it `lsrw #4` into a 0…7 mark, and tests
> `staging[+90]` against 127 for the high mark:
>
>     164c76:  mulsw #92,%d0
>     164c7c:  movew %a0@(88),%d0      the LOW velocity word
>     164c80:  lsrw  #4,%d0            -> the 0..7 mark
>     164c94:  cmpiw #127,%a0@(90)     full range -> high mark 7
>
> **`lsrw #4` occurs once in the whole Ensoniq region and that is it.** So
> `0x164C66` is Ensoniq's, the re-attribution stands, **and the AKAI path's
> velocity computation is simply somewhere else and still unlocated.** The
> two entries were never in conflict — they describe different code, and the
> tension was between two correct claims.
>
> **`[?]` where the AKAI one lives.** It is now a *handle* on the unlocated
> AKAI builder rather than only a loose end: the builder must contain code
> that writes a layer's byte 5 from a source velocity range, and the measured
> import proves it runs.

> ~~**So `O6` spent weeks hunting an unlocated builder for a conversion that
> does not happen.**~~ **It converts less than anyone expected, but not
> nothing** — see the refutation above. The law for this arm, in full: *clone Program 199, point
> `CAL[12]` at the new keymap, discard everything else.* Samples and keymaps
> are genuinely built; the **program** is not converted at all.
>
> ### ⚠ AND THE KEYMAP TRUNCATES — real, and the SIZING mechanism below was REFUTED within the hour

> #### ❌ RETRACTED 2026-09-21 23:35 — "sized from the key span" is WRONG
>
> Two pre-registered tests were run on the same disc and **both predictions
> failed, in opposite directions**:
>
> | volume | predicted | observed |
> |---|---|---|
> | `ACCORDION 1` (span 92) | 668 B, nothing lost | **540 B**, top keygroup clipped `90..96` against a true `90..115` |
> | `CYMBAL MAP 4` (span 14) | 156 B, all seven zones lost | **668 B**, **all seven intact** |
>
> **The smallest span got the largest allocation.** The span is not the
> variable. *The fork table registered beforehand listed four outcomes and
> this was not one of them — both failing, oppositely, is the case that gets
> left out of a fork table by the person who believes the mechanism.*
>
> **What the three allocations actually are:** `384 / 512 / 640` = `3 / 4 / 5 ×
> 128` — and they were created in that order. Two readings fit all three
> points exactly and are **collinear on this data**: `k` rises with **load
> order** (+128 per import), or `k = (37 − n_samples)/6` falls with **sample
> count** (19 / 13 / 7). Neither is supported over the other by these points.
>
> **`[S]` load order, for two reasons stated before the test:** an allocator
> that gives *less* table to an instrument with *more* samples is backwards;
> and `SNARES ONE` on this disc has 40 samples, where `(37 − 40)/6` is
> **negative** and the content law cannot be evaluated at all.
>
> **The decisive test is one import: re-import `SOPRANO SAX2` into a fourth
> bank.** Same content, same 19 samples, same span, different position.
> Load order → 768 B area, object **796**; sample count → 384 B, object
> **412**, which is what it got the first time. *And `28 + 128×6 = 796` is
> exactly what these keymaps DECLARE — so if the fourth import gets six
> blocks the object is exactly full and the truncation vanishes, meaning the
> same volume imports correctly or incorrectly depending on nothing but
> when.*

> #### ❌❌ AND THE REPLACEMENT DIED TOO — 2026-09-21 23:40, on 16 points
>
> Each import builds **one keymap per program**, not one per volume, so the
> two test imports gave 16 allocations rather than 2. `k2kremote` read them
> all, and they kill both remaining readings at once:
>
>     bank 3 (ACCORDION 1, one import):  540 540 540 796 668 668 668 668
>     bank 4 (CYMBALS 4,  one import):   668 412 412 412 412 412 412 412
>
> **Load order is dead** — within a *single* import the sizes jump up to 796
> and come back down; no counter does that. **And the sample-count reading is
> dead** — all eight bank-3 keymaps were built from the same 13 samples.
>
> #### ✅ WHAT THE 16 POINTS DO ESTABLISH: the allocation is CONTENT-INDEPENDENT
>
> Two of those programs are structurally the same program, **in the same
> import**:
>
> | program | kgs | lo | hi | span | zones | distinct samples | allocation |
> |---|---:|---:|---:|---:|---:|---:|---:|
> | `ACCORDION 1A` | 8 | 21 | 115 | 95 | 8 | 8 | **540** |
> | `DBL.REED #3` | 8 | 24 | 115 | 92 | 8 | 8 | **668** |
> | `DBL.REED #4` | 8 | 24 | 115 | 92 | 8 | 8 | **668** |
>
> Same keygroups, same zones, same distinct samples, same top key — **128
> bytes apart**, and the direction is wrong for the only variable that
> differs: `ACCORDION 1A` has the *wider* span and the *lower* bottom key and
> got *less* table.
>
> **So no program-content variable can explain the sizes** — not span, not
> keygroups, not zones, not samples, not lowest or highest key, nor any
> combination, because two programs agreeing on all of them differ. *That
> closes the class rather than refuting one more member of it.* **`[?]` what
> does set it. No candidate, and "whatever the heap handed it" is not one —
> it fits everything and predicts nothing.**
>
> **The sharpest single case:** `CYMBALS 4`'s seven single-keygroup programs
> each span keys 24…127, needing entries up to index 115, **and each got 64.**
>
> > **One test would split what remains, and needs no new volume:**
> > `Master → Delete → Everything`, re-import `ACCORDION 1` alone, compare
> > against `540/540/540/796/668/668/668/668`. **Identical** → the allocator is
> > deterministic from a clean state, the sizes are a function of the import
> > sequence, and it is findable in the ROM. **Different** → it depends on heap
> > history, and it should be dropped rather than chased.
>
> #### ⚠ CONSEQUENCE: a bank saved from a K2000 AKAI import is NOT a trustworthy reference
>
> It may be missing zones — by an amount not predictable from the source, and
> **varying between structurally identical programs in the same run.** Anything
> that compares our AKAI → KRZ output against a device import must treat the
> **device** side as the lossy one and check the zone count before reading
> anything into a difference.
>
> #### ❌ my `CAL[7:9]` correction was itself wrong — withdrawn the same hour
>
> This document briefly said the `-2` objects were **second keymap slots**, so
> `CAL[7:9]` was used after all. **It is `0` on all six bank-3 programs.**
> `k2kremote` read every one rather than accept the correction — *because it
> overturned something they had asserted, which is the case where accepting is
> cheapest and checking is worth most.*
>
> **They are second LAYERS.** Programs 302 and 303 are **496 bytes =
> `48 + 224 × 2`**, and each layer carries its own `CAL[11:13]`: 302's layers
> point at keymaps 302 and 303, 303's at 304 and 305. The zone reading was
> right — those two programs do carry 14 zones over 7 keygroups — but the
> importer expresses it as a **layer**, not a slot.

**What survives, and it is the half that was never in doubt:** entries are
written from **key 12**, every zone in both new volumes lands exactly on our
ground truth, and **the truncation is real** — `ACCORDION 1`'s seventh
keygroup is clipped at 96 against a true 115, and `SOPRANO SAX2` lost keys
76…96. It follows from the allocation, whatever sets that.

> ### ⚠ A READ-LENGTH HAZARD OF THE FORMAT, not of one reader
>
> `k2kremote` requested 900 bytes and the device returned **796** for both
> objects, while `DIRBANK` reports 540 and 668. **Reading past an object
> returns padding to the DECLARED extent, and it looks exactly like a full
> 128-entry keymap.** Trusting the read length would have produced *"both
> keymaps are complete, there is no truncation"* — clean, confident and
> wrong. Their first read was right only because they happened to request
> exactly the `DIRBANK` size.
>
> **Size the read from `DIRBANK`, never from a generous request.** This is the
> same over-read defect this project's own `_decode_table` carried, arriving
> from the wire instead of from a header — which makes it a property of the
> **format**, not of either reader.

> ### And this does NOT put the project's "match the device" rule in tension
>
> The temptation here was to write an explicit exemption — *"the rule is
> suspended for AKAI, because matching this would make our output worse."*
> **That would have been the harmful move**, and `k2kremote` refused it by
> quoting this document's own opening section back: the rule is already
> scoped to *"the only definition of correct available when the source
> instrument is absent"*, and **for AKAI the source instrument is not absent —
> an S3000XL is on the bench**, which is why §"Why this document exists"
> carved AKAI out on the day it was written.
>
> **So the narrower and truer statement: the K2000's AKAI import sets one
> byte, so on this arm there is no device behaviour worth matching.** Match it
> on *encodings* — `samplePeriod`, `maxPitch` — and exceed it on *content*,
> which is what the existing carve-out already says. *Writing a suspension
> would have read as "the rule was inconvenient here" and weakened it on the
> two arms where it genuinely is the specification.*

> ⚠ **This entry described "the AKAI staging record" until 2026-09-21. That
> record is ENSONIQ's.** The heading survived the re-attribution by several
> commits — *the heading rule, committed again by the file that contains
> it.*

> ### ⚠⚠ AND `format 5` IS NOT AKAI EITHER — 2026-09-21 22:25
>
> An external session took this project's brief and did exactly what it
> asked: traced straight-line from `0x1221C8`, and landed in one pass. **The
> trace looks sound. The identification does not.**
>
> It reports the arm sniffing three magics — `SRAM`, `SROM`, `PRAM` — and
> calls them the AKAI file types. **They are KURZWEIL's:**
>
> | | |
> |---|---|
> | `.KRZ` files in this project's corpus beginning `PRAM` | **348 of 348** |
> | AKAI files beginning `SRAM`/`SROM`/`PRAM` | **0 of 3483** |
> | how an AKAI file actually starts | a **block-id byte**: `0x03` sample (2606), `0x01` program (877) |
>
> **The AKAI format has no four-character magic at all.** And the walker the
> trace describes creates **type 36** and passes **132 … 135** — Kurzweil's
> own (`T_PROGRAM/T_KEYMAP/T_SAMPLE = 36/37/38`, and RAM types are file types
> plus 96). *The trace even names `0x15FB82` "the native Kurzweil `.KRZ`
> loader" without drawing the conclusion.*
>
> **So `0x1221C8`… is the K2000's own file loader, and `format 5` is most
> likely its own disk format** — which fits the one converter-region
> reference to the format code, `0x168B98`, testing format 5 inside
> **directory-listing** code that checks for `'.'`.
>
> > **The `format 5 = AKAI` label was this project's, and it was inherited
> > rather than derived.** It came from a peer message into
> > `~/temp/break_O6.txt` §1 and was passed on unchecked — **the same failure
> > as the offset-base error earlier the same evening, with the roles
> > reversed.** An analysis that traces faithfully from a mislabelled entry
> > inherits the label, and this one did.
>
> ### ✅ AND THE REASON EVERY SEARCH FAILED: AKAI IS NOT FORMAT-GATED
>
> `0x12A6D6` — the function holding the partition-letter decode and the
> *"Akai partition not found."* string — has **one caller**, `0x129952`, and
> it is selected by a **medium/device type byte**, not by the format code:
>
>     0x129938   moveb %a0@(5),%d0     ; the DEVICE type, not %a5@(5290)
>     0x12993C   cmpib #1,%d0
>     0x129940   beqs 0x129950   ->  bsrw 0x12A6D6      ; AKAI partition
>     0x129942   cmpib #4,%d0    ->  0x12995C
>     0x129948   tstb  %d0       ->  0x129968
>
> **There is no format-code test anywhere in `0x129xxx` or
> `0x12A600`–`0x12A7xx`.** The AKAI path and the format code are unrelated
> variables — *which is exactly why no format-test search and no
> `jsr`-reference search ever found it.* **AKAI appears to be device type 1.**
>
> **`O6` gains its first real lead since the re-attribution**, and it is a
> different search axis rather than another address.
>
> > **And the `format 5 = AKAI` claim rested on PROXIMITY** — the AKAI
> > strings and the format-5 tests both living in `0x12Axxx`. **That is a
> > region argument**: the failure its own author had filed a standing check
> > against hours earlier — *"an anchor that is a region is not an anchor"* —
> > committed again the same evening by the session that wrote the rule.
>
> **On whose error it was, recorded in the other session's framing rather
> than this one's.** This project first wrote that the root error was its own
> for relaying the label unchecked. They rejected that: the label arrived
> **inside a correction to this project's own field mapping**, and the
> surrounding message was mostly right.
>
> > **AN ITEM THAT TRAVELS INSIDE A CORRECTION INHERITS THE CORRECTION'S
> > CREDIBILITY.** The parts that were load-bearing got checked; the framing
> > line was taken as given, *because being corrected is the context in which
> > a reader is least disposed to audit the corrector.*
>
> **The wrong lesson here would be "distrust the external analysis".** Its
> trace was better than the label it was given: **straight-line tracing from
> the dispatch worked and landed in one pass.** The method was sound and the
> entry was wrong.

**The builder is unlocated.** The format dispatch at `0x1221AA` routes format
5 past `0x1221C8`, and nothing beyond that is traced: not the entry, not what
it reads, not what it stages. **Every structure previously filed here belongs
to the Ensoniq arm.**

**Two anchors, and both are about what NOT to do as much as what to do:**
* the AKAI **filesystem driver** is named and located at `0x177572` …
  `0x1779E0` (23 `ak_*` functions, as error-reporter operands) — the
  filesystem layer, *not* the builder;
* the conversion entry is reached **indirectly**, so no `jsr`-reference
  search will find it, just as no region-scoped search found the dispatch.

**And no AKAI disc has ever been on the K2000's bus** — the corpus exists but
nothing is mounted, so none of this arm has been hardware-checked.

**Blocks:** K2000 AKAI → KRZ. **Full brief:** `~/temp/break_O6.txt`.

### O7 — What AKAI keygroup `0x13` actually modulates · ✅ **CLOSED 2026-09-22**

> ## ✅ `0x4B` = `VEnvRls` = AMP-ENVELOPE RELEASE. This project's writer was right.
>
> **Measured on the E4XT**, not inferred: `S7` imported from `CD3`
> by EOS's own AKAI importer, read back by `eosed`, identical on all 8 voices:
>
>     cord 7   SRC=8 (Key+)   DST=56 (0x38 FilFreq)   AMT= 8
>     cord 8   SRC=8 (Key+)   DST=75 (0x4B VEnvRls)   AMT=-4
>
> **`0x4B`, not `0x4A` `VEnvDcy`.** The AKAI documentation's *"key → decay"*
> reading is wrong about what this firmware does with the byte, and
> `AKAI_ENV_CORD_BYTES` needs no change.
>
> ### Why the test was unambiguous, and it was the material rather than the method
>
> **Six of the seven env-cord bytes are ZERO on all 17 keygroups** of that
> program — only `0x13` carries a value (`−5`). So exactly one cord from that
> family could appear. **Two Key+ cords came back and both are accounted for
> from the disc side:**
>
> | cord | AKAI source | value | E4B amount |
> |---|---|---:|---:|
> | Key+ → `FilFreq` | `filter_keyfollow` | **+5** | +8 |
> | Key+ → `VEnvRls` | keygroup `0x13` | **−5** | −4 |
>
> *Without the six-of-seven-zero check there would have been a cord and no
> way to attribute it.* Checked here against the disc after the read-back,
> with `filter_keyfollow = 5` explaining the first cord exactly.
>
> ### ~~⚠ AND THE SCALE IS NOT MEASURED — deliberately~~ ✅ **SETTLED, see `O7b`**
>
> *Kept for the reasoning, which was right at the time.* `−5 → −4` and
> `+5 → +8` were **two source values, two amounts, two different
> destinations, and therefore no law** — `eosed` declined to fit one and this
> project agreed: *"one source value and one amount does not determine a
> law."* The refusal to fit was correct; the gap it left closed the same day
> from two directions at once.
>
> **Both constants are now known**, and neither came from `SL3119`:
> **96 for `FilFreq`, 48 for the seven envelope destinations**, read as the
> literal pushed to the rescaler at `0x2f6b4` and independently confirmed by
> 17 keyfollow and 12 `vel_to_attack` points on the E4XT. The `−5 → −5`
> (wire `−4`) of this very measurement reproduces through `48/50` exactly.
>
> **`SL3119` is therefore no longer wanted**, and the card slot it needed
> stays where it is. The request had a good reason and the reason expired —
> worth saying out loud, because a standing hardware request that nobody
> retracts is how a bench queue fills with settled questions.

### O7b — EOS's AKAI cord SCALES · ✅ **MEASURED 2026-09-22**

> ## Two laws, both settled on the E4XT, both with a discriminating rail
>
>     keyfollow      stored = round(clamp(kg[0x08], -50, +50) * 96/50)
>     vel_to_attack  stored = round(clamp(kg[0x10], -50, +50) * 48/50), sign inverted
>     read-back      wire   = round(stored * 100/128)
>
> ### ✅ KEYFOLLOW: 17 OF 17 EXACT, AND PERFECTLY SYMMETRIC
>
> | `kf` | −12 | −7 | −2 | 3 | 4 | 5 | 12 |
> |---|---:|---:|---:|---:|---:|---:|---:|
> | predicted (wire) | −18 | −10 | −3 | 5 | 6 | 8 | 18 |
> | measured | **−18** | **−10** | **−3** | **5** | **6** | **8** | **18** |
>
> `+12 → +18` and `−12 → −18`, **in different volumes**, on material the
> `×100/128` correction was never fitted to. **EOS's keyfollow is symmetric:
> there is no asymmetry in the firmware to model.**
>
> > **⚠ AND THAT DOES NOT REFUTE `AKAI_KEYFOLLOW_NEG_SCALE = 0.622`.** That
> > constant measures **the S3000XL's own tracking** — what the sampler does.
> > This measures **EOS's conversion**. Two quantities that have never been
> > the same quantity. *Named as different BEFORE the result arrived, which
> > is the only reason it could not become another frame error.*
>
> ### ✅ vel_to_attack: `×48/50`, SETTLED AT FOUR DISCRIMINATING POINTS
>
> | `va` | 1:1 predicts | `×48/50` predicts | measured |
> |---:|---:|---:|---|
> | −50 | 39 | **38** | **38** — twice |
> | −14 | 11 | **10** | **10** — twice |
> | −8 | 6 | 6 | 6 — both laws agree |
>
> The `−50` rail is where the two laws part by the most, and it went to
> `×48/50`. **Scale 48 is a constant this project already carried**, and the
> `−8` points reproduce a measurement from a different disc the day before.
>
> ### ⚠ AND THE APPARATUS NEARLY WON AN ARGUMENT — `eosed`'s finding
>
> Five `kf −12` cords were missing from the first scan. Their scanner had
> `if not got and v > 0: break` and **the cords are on VOICE 13**.
>
> The part worth keeping is the reasoning that nearly excused it: the `−7`
> programs were interleaved among the `−12` ones, and the argument was that a
> truncation *"would have to hit exactly the −12 programs and spare both −7
> ones, five times running"*. **It did** — the `−7` programs carry their cord
> on an early voice and the `−12` programs on voice 13.
>
> > **A PATTERN THAT LOOKS TOO SELECTIVE FOR AN APPARATUS FAULT IS NOT
> > EVIDENCE AGAINST ONE.** *The re-scan settled it; the argument about
> > whether to re-scan pointed the wrong way.*

### O8 — The EOS Roland `[S]` rows · ✅ **CLOSED 2026-09-22**

* **`[C]` pan and fine tune** — corpus-confirmed on **6884 partial records
  across two discs**, after rebasing both offsets from the partial record to
  the 16-byte sub-record. Observed extremes land exactly on the rails their
  formulae assume (±32 → ±64 pan, ±50 cents). See the Roland section.
* **`[?]` transpose** — `src[24]` is neither the partial record nor the
  sub-record; a third structure, unidentified.
* **✅ `[C]` THE PAN FORCE-TO-ZERO ARM EXISTS, EXACTLY AS FIRST DOCUMENTED** —
  and this row spent four hours withdrawn on a refutation that was itself
  wrong. *(`eosed`; **not verified here**, the EOS image is not on this
  machine.)*

      1714be:  moveq #3,%d1
      1714cc:  moveb %a2@(58),%d0      the SAMPLE's byte 58
      1714d0:  lsrl  #1,%d0
      1714d2:  andl  #3,%d0
      1714d8:  andl  %d0,%d1
      1714da:  subql #3,%d1            (sample[58] >> 1) & 3 == 3 ?
      1714dc:  bnes  0x1714e4          no  -> compute the pan
      1714de:  clrb  %a5@(14)          YES -> PAN = 0
      1714e2:  bras  0x171504

  `%d1` is the constant 3, so the test is verbatim what was documented, `a2`
  **is** the sample structure and `sample[58]` **is** read.

  > **IT SAT `0x18` BYTES BEFORE WHERE THE REFUTING READ STARTED** — at
  > `0x1714E4`. And the message carrying that refutation *also* carried the
  > caveat that the last single-window read had missed a formula `0x190`
  > bytes past its window. **The caveat named the failure mode and did not
  > prevent it, in the same message.** In their words: *"a stated window
  > limit should send you back to widen the window, not into the report.
  > Writing 'I read one window' is not a mitigation, it is a TODO I keep
  > filing instead of doing."* Same rule as the flagged-assumption one, for
  > reads instead of quantities.
  >
  > **What found it was enumerating the class instead of re-reading the
  > region** — a sweep of every structure offset the two builders touch:
  >
  >     header builder 0x1713B0-0x171434   a4@(24) (25) (26)
  >     zone builder   0x171434-0x1715A0
  >         a2 (SAMPLE)    58, 68
  >         a3 (PARTIAL)   4, 6, 7, 8, 9, 10
  >         a4 (PATCH)     12,13,14,15, 16,17,18,19, 34, 52, 53
  >         a4 via 0x50D38  2, 24
  >
  > `a2@(58)` is in that list, and the sweep produced it on the first pass.
* **`[C]` fine tune, with its destination** *(same sweep)*:

      1714a4:  moveb %a3@(6),%d7 ; extw ; extl
      1714ae:  lsll  #6,%d7           * 64
      1714b0:  addl  #32,%d7          + 32
      1714b6:  divsll #100,%d7        / 100
      1714ba:  movew %d7,%a5@(10)     -> entry[12], as a WORD
> **⚠ AND THEIR OWN WEIGHTING OF THESE THREE READS, IN THEIR WORDS:** *"I
> read those instructions once, in one window, and the last time I reported a
> firmware read from a single window as settled it was the `0x7A9C4` formula
> that was sitting `0x190` bytes past where I stopped. Weight them
> accordingly until someone re-reads them."* **A caveat volunteered by the
> author of the claim, recorded at the claim rather than in the message that
> carried it.**

* **`[C]` pan's destination, named for the first time** *(same source, same
  caveat)*:

      1714e4:  moveb %a3@(4),%d7     the PARTIAL's byte 4
      1714ea:  extw  %d7             SIGN-extend
      1714ec:  addl  %d7,%d7         x2
               clamp -64 .. +63
      171500:  moveb %d7,%a5@(14)    -> entry[16]

* **`[C]` the stereo test is a FUNCTION CALL, and not on `sample[58]`**
  *(same source, same caveat — and **this one is corpus-checkable here**,
  which is why it is worth having):*

      17151a:  jsr 0x50d38           (a4 = the PATCH)
      171526:  subql #2,%d1          stereo iff result == 2
      50d48:   tstb %a0@(24) ; bnes -> return 0
      50d4e:   moveb %a0@(2),%d0     else return patch[2]

  **stereo iff `patch[24] == 0` AND `patch[2] == 2`.**

  > **⚠ TREAT THIS AND THE BACK-PATCH AS UNCONFIRMED.** Their author's own
  > instruction after being wrong twice in one day about what is and is not
  > in this routine: *"treat those as unconfirmed until someone re-reads the
  > whole function rather than a window of it."*

  > ### ❌ AND IT IS NOT CHECKABLE FROM THE DISC — tested 2026-09-22
  >
  > This project said it would corpus-check that, because it is a statement
  > about bytes. **It came back zero on both discs**, and the reason is the
  > frame, not the claim:
  >
  > | | CD 1 | CD 2 |
  > |---|---:|---:|
  > | patch records read (512-byte stride from `0x155800`) | 2972 | 3375 |
  > | `patch[2] == 2` | **4 (0.1 %)** | **7 (0.2 %)** |
  > | `patch[24] == 0` | 2253 | 1823 |
  > | **both** | **0** | **0** |
  >
  > **`patch[2]`'s commonest values are 68, 255, 97, 77, 48 — `D`, `a`, `M`,
  > `0`.** The disc patch record opens with **16 bytes of name**, so
  > `patch[2]` on the disc is a name character and the test cannot be about
  > that structure.
  >
  > **This is the key-fade pair's failure again, one field over.** `patch+n`
  > in this routine is an offset into **EOS's in-memory patch**, not into the
  > disc record — established for `patch+12..15` when `O9` closed, and now
  > shown to hold for `patch+2` and `patch+24` as well. *The rule is not
  > "that one field is in the memory frame"; it is that **every `patch+n` in
  > this routine is**, and a disc-side check of any of them tests nothing.*
  > Worth a full sweep of the record for other offsets quoted against the
  > wrong base before any of them is corpus-checked again.
* **⚠⚠ THE STEREO BACK-PATCH MUTATES ITS INPUTS, AND THAT IS A MEASUREMENT
  HAZARD BEFORE IT IS A CONVERTER ONE:**

      a4@(16..19) -> a5@(-18..-15)
      a3@(2)  = 0                       MUTATES the partial
      a4@(12..15) -> a5@(-22..-19)
      a4@(52) -> a5@(-9) ; a4@(52) = 0  MUTATES the patch
      a4@(53) -> a5@(-8) ; a4@(53) = 0  MUTATES the patch
      a4@(34) -= [0x102e0c86], stored back
      [0x102e0c86] -> a5@(-12) as a word

  **Anything reading `patch[52]`/`[53]` after a stereo zone has been built
  reads zeros**, and `patch[34]` has been decremented by a global. A corpus
  check that walks patches in order would measure a mutated structure and
  produce a clean, confident, wrong statistic — on exactly the fields this
  topic still has open. *Recorded here rather than in the Roland reader,
  because the reader does not exist yet and the corpus checks do.*
* ~~**`[S]` still open** — the zone-volume discard.~~ **✅ CLOSED below: it is an explicit `clr`, and the stereo back-patch fills the PREVIOUS zone's volume from `patch[52]`.**
* **✅ `[C]` EOS READS SIX BYTES FROM THE PARTIAL, AND NOTHING AT OR ABOVE
  `+11`** — `eosed`, 2026-09-22, sweeping the **whole Roland module**
  (`0x16D000`–`0x173800`) rather than the two builders:

      a3@(4)  a3@(6)  a3@(7)  a3@(8)  a3@(9)  a3@(10)
      pan  ·  fine tune  ·  the velocity quartet

  **So the filter, envelope and LFO parameters in the partial record above
  `+80` are DROPPED.** The only byte reads above `+64` anywhere in the module
  are one block at `0x16FF62` walking `+96/+128/+160/+192` at a 32-byte
  stride into a *different* structure — checked before the absence was
  reported, which is the step that was skipped earlier in the day.

  > **Both arms of this firmware convert geometry and sample references and
  > discard the synthesis parameters.** The Ensoniq importer gives the same
  > answer (`0x7BB90`: two 16-byte memsets and default-voice helpers). *A
  > consistent design is more likely to be deliberate than two independent
  > omissions are* — and it makes a missed second pass on either arm less
  > likely, since both would have to have been missed the same way.
  >
  > **Consequence for this project, and it is the doc's own rule rather than
  > a choice:** Roland has no source instrument on the bench, so matching the
  > firmware *is* the specification here. The converter writes defaults for
  > filter, envelope and LFO **deliberately**, not by omission — and this row
  > is what makes that a decision rather than a gap.
* **✅ `[C]` THE ZONE BUILDER WRITES EVERY BYTE OF THE 22-BYTE ZONE — and it
  maps onto `docs/E4B_FORMAT.md` §4.5 field for field.** *(`eosed`,
  2026-09-22, after withdrawing an unscoped list — see the retraction below.)*
  **Base: `%a5`, the zone pointer from `0x50E40(patch, index)` =
  `object + 284 + index*22`; `= entry + 2` under §167's endpoint match.**

  | `%a5` | source | = entry | our §4.5 field |
  |---:|---|---:|---|
  | `+0` | `patch[12]` | `[2]` | `lo_key` |
  | `+1` | `patch[13]` | `[3]` | key fade low |
  | `+2` | `patch[14]` | `[4]` | key fade high |
  | `+3` | `patch[15]` | `[5]` | `hi_key` |
  | `+4` | `partial[7]` | `[6]` | `lo_vel` |
  | `+5` | `partial[8]` | `[7]` | **vel fade LOW** |
  | `+6` | `partial[10]` | `[8]` | **vel fade HIGH** |
  | `+7` | `partial[9]` | `[9]` | `hi_vel` |
  | `+8` word | `%d7` | `[10:12]` | `sample_idx` BE u16 |
  | `+10` word | fine tune | `[12:14]` | `fine_tune` BE i16 |
  | `+12` | `a2@(68)` | `[14]` | `root_key` |
  | `+13` | **`clr`** | `[15]` | **`volume` — deliberately ZERO** |
  | `+14` | pan, or 0 when `(sample[58]>>1)&3 == 3` | `[16]` | `pan` |
  | `+15…+21` | **`clr`** | `[17…21]` | zero in all 10 142 corpus zones |

  **Twenty-two of twenty-two accounted for**, and every field lands where
  this project's hardware-derived map already had it — including the crossed
  velocity quartet `O9` closed. *Two maps built from opposite ends agreeing
  on all fourteen fields.*

  > **✅ AND THIS CLOSES THE ZONE-VOLUME DISCARD, the last `[S]` in this
  > topic.** `entry[15]` is not skipped, it is **explicitly cleared** — a
  > deliberate zero, not an omission. And the stereo back-patch then fills
  > the *previous* zone's volume and pan from `patch[52]`/`[53]`:
  >
  >     a5@(-9)  = entry-7  = prev_entry[15]   volume  <- patch[52]
  >     a5@(-8)  = entry-6  = prev_entry[16]   pan     <- patch[53]
  >     a5@(-22..-19) = prev_entry[2..5]   the key quartet   <- patch[12..15]
  >     a5@(-18..-15) = prev_entry[6..9]   the vel quartet   <- patch[16..19]
  >
  > *The arithmetic closes on a 22-byte stride and on nothing else*, so
  > **`-22` being exactly one zone back confirms the stride from the WRITE
  > side** — a third independent route to 22, after `0x50E40`'s
  > multiplication and this project's own writer.
  >
  > **`entry[0]` and `entry[1]` are never touched by this builder at all**,
  > because `%a5` starts two bytes in. They are zero in all 10 142 corpus
  > zones and in our output — and now there is a reason rather than a
  > coincidence.

* **The header builder writes a DIFFERENT `%a5`** — the preset/voice header:
  `+16` (word), `+20` (`clrw`), `+22` (`clrw`), `+24`, `+25` (`clr`).
  **Not to be merged with the zone list.**

> ### ❌ RETRACTED: the "complete destination list" published an hour earlier
>
> ~~`-22 -21 -20 -19 -18 -17 -16 -15 -12 -9 -8 / 1 2 3 4 5 6 7 8 10 12 13 14
> 15 16 17 18 19 / 24 28 33 34 36 52 53 56 58`~~ — **withdrawn by its author,
> and it was wrong in two directions at once.**
>
> The extraction **missed three instruction forms** — the bare `%a5@` with no
> displacement (offset 0, which is why `entry[2]` looked absent), `movel`,
> and `clr`. And it **swept the whole module, where `%a5` is a different
> structure in different functions**, so the result was a merge of a zone
> pointer, a file context and a preset header.
>
> > **A REGISTER IS NOT A STRUCTURE.** The union of one register's offsets
> > across a module describes nothing. **An offset list is only meaningful
> > inside the scope where its base register has one meaning, and the scope
> > belongs in the list as much as the numbers do.**
>
> **This project did not use it**, because type-checking it against §4.5 gave
> two readings that each dropped a field the importer demonstrably writes,
> and neither could be right. *Mapping it would have produced a converter
> written against a union of three structures — which would have run, and
> been wrong in a way no test here could see.* The check that caught it cost
> one message and no firmware.

**The lesson for whatever is checked next:** *every* offset below 16 in these
`[S]` rows lands inside a record's tag-and-name and must be rebased before it
means anything. That defect had been found once, for the velocity quartet,
and not swept for.

### O9 — E4B zone-entry `[7]`/`[8]`, which is the LOW fade · ✅ **CLOSED 2026-09-21**

**`[7]` is the LOW fade and `[8]` the HIGH — and this project's table was
right.** Settled from the **destination** side by `eosed`, who read the EOS
Roland zone builder in full at `0x171434`:

    17148c:  a3@(7)  -> a5@(4)
    171492:  a3@(8)  -> a5@(5)
    171498:  a3@(9)  -> a5@(7)      <- crossed
    17149e:  a3@(10) -> a5@(6)      <- crossed

With `partial+7 = vlow` and `partial+9 = vhigh` measured on hardware, and our
`[6] = lo_vel` / `[9] = hi_vel`, all four destinations resolve:

    entry[6] = partial+7    lo_vel
    entry[7] = partial+8    LOW  fade
    entry[8] = partial+10   HIGH fade
    entry[9] = partial+9    hi_vel

**Two routes that share no evidence agree** — this and the asymmetric velocity
stack measured off the E4XT.

> **The `[S]` bridge closes with it.** `a5@(4)` must be `entry[6]` and
> `a5@(7)` must be `entry[9]`; **both independently require `a5 = entry + 2`**.
> The `zone_base + 2` convention is now **read** for the Roland builder, not
> carried over from the Ensoniq one — which was the single inferred step this
> document had flagged.

**And the crossing is the nesting transform.** Roland stores both quartets
*ascending*; the E4B entry nests them **low, fade, fade, high**. An importer
writing them in source order would be the broken one. The key quartet
(`entry[2..5]` ← `patch+12..15`) is nested identically.

**The bank save would not have settled it**, which is worth recording against
the next "one hardware step closes this": `patch+12..15` are offsets into
EOS's in-memory patch, not into the file record, so the file-side search was
structurally incapable of the answer however it was rebased. *We write 0 to
both bytes, so our own output was never affected; this is about reading anyone
else's E4B.*

**Full record:** `docs/E4B_FORMAT.md` §4.5.

---

# What to do next, cheapest first

1. **`O8`** — corpus-check the Roland `[S]` rows against 2880 records.
   Offline, and the base that makes it possible was solved today.
   **Check the base first:** two of the three Roland constants turned out to
   be `0x200` low, and the error was invisible to every total computed from
   them.
2. **`O1`** — locate every Ensoniq struct in one instrument. Offline, and it
   is the only thing standing between a good law and a working path.
3. **`O3`** — read the rest of the 48-byte Roland sample record. Offline.
4. **`O7`** — one import and one SysEx read, outcomes pre-registered.

*(`O9` was item 4 here and is closed — offline, by a destination-side read,
not by the hardware step it was queued for.)*

---

# The target's ceiling, stated because it is a real limit

> ### ⚠ AND ON THE K2000's AKAI ARM THE CEILING IS THE FLOOR — measured 2026-09-21
>
> **That import writes one byte.** Filter, envelopes, LFO, pan, velocity and
> loudness are all discarded, and the keymap additionally truncates. So "match
> the firmware" here would mean emitting Program 199 with a pointer patched —
> *a converter that threw away everything this project has measured off the
> S3000XL in order to be more faithful to a machine that measured nothing.*
>
> **This is not an exception to the rule; it is the case the rule was already
> scoped around.** See §"Why this document exists": matching the device is the
> definition of correct **when the source instrument is absent**, and for AKAI
> it is not. Match the device on *encodings* (`samplePeriod`, `maxPitch`);
> exceed it on *content*.

For Ensoniq and Roland, "matches the firmware" is the only checkable
definition of correct — **and it makes the firmware's own drops the ceiling
too.** A converter that matched EOS exactly would discard everything EOS
discards: both LFO delays on the AKAI path, and (if the code-only reading
holds) envelopes, filters, LFO and all cords on the Ensoniq path.

That is a limit on the target, not an argument against it. Where a source
field survives into our model and the firmware drops it, **keeping it is the
better conversion and diverging from the firmware is correct** — the same
rule this project already applies on the AKAI path, where a measured hardware
law beats EOS's table.

---

# Method, as this material taught it

Every rule here was paid for with a retraction on 2026-09-20/21.

* **Identify a field by a RELATION several fields satisfy at once, never by a
  single plausible position.** An off-by-a-few base yields one field that fits
  and is wrong. Both projects hit this; the class tag caught it on the K2000
  side, the two-blocks-of-four adjacency caught it on the AKAI side.
* **Count distinct values before believing an agreement.** A field that barely
  varies cannot validate anything downstream of it. Three instances in one
  night: a 94.4%-constant velocity window, three all-zero cord rows, and a
  single-valued disc field.
* **The uniform thing can be the CORPUS, not just the field** — a property of
  one disc's content written down as a property of the format.
* **A prediction of "always X" tested on a corpus that is always X has been
  restated, not tested.**
* **Group a mixed corpus by a feature your own writer cannot emit.** 1140 of
  1156 keymaps here are our own output; the honest evidence was ~27 entries.
* **"My search found no reference" is not "the program does not read it."**
  An address held in a register appears once.
* **A count in a header need not describe the object you are holding.**
* **An estimator returns a number whether or not its input exists**, so the
  check that the input exists cannot live inside the estimator.
* **A value repeating exactly is a fact about your apparatus** — *and the
  heuristic has a false-positive direction*: an unsigned read of a signed byte
  produced 213 "out of range" values and one value repeating 155 times, and
  the finding was real. Ask whether the suspect records are structurally
  *worse* than the rest. Garbage is not better-formed than good data.
* **Record an anomaly with its exact arithmetic rather than smoothing it
  away.** One unexplained volume row, committed with its numbers, is what
  closed the boost law a day later.
* **Record a guess that FAILED.** Two invented offsets scored 0/25; written
  down, they stop the next person re-inventing them.
* **Reproduce a peer's measurement even when you believe it.** Scepticism
  finds what you suspect; reproduction finds what nobody was looking at.
* **A perfect fit from one observation is information-free, and treating it
  that way is the only clean save in this record.** The Ensoniq chain rule
  reproduced the single pair it was derived from *exactly* — and was tested
  anyway, **by the session that made it, before it reached anyone else.**
  Every error in the retraction table below was caught by somebody else. The
  difference was not care: it was refusing to count the derivation's own datum
  as confirmation. *(The score it returned, 1 of 18, has since been withdrawn
  with every other number from that validation set — twelve of the eighteen
  pairs were not adjacent. **The behaviour is the finding here, not the
  number**, and it is worth keeping precisely because the instinct was right
  while the apparatus was not.)*
* **"Confirmed" can name a weaker thing than the reader will hear.** A table
  headed *"Confirmed both ends"* held one formula checked 363/363 and one
  never checked against anything; what was confirmed for the second was that
  both **endpoints were identified**, which does not verify the arithmetic
  between them. **The other errors in this record were claims that LOST their
  scope in transit. This was a claim that never HAD it** — one word carrying
  two meanings, and the heading picking the stronger. When a bucket label is
  written, say what was checked, not what is known.
* **A phrase sweep over hard-wrapped text is NOT a sweep**, and a clean grep
  gets believed. Retiring "one field wide" from this document left it in the
  section *subtitle*, because the phrase was wrapped across a line break:
  `grep "one field wide"` returned only the paragraph that retires it, with a
  clean exit code. **Every standing check written today that says "grep for
  the words" — the caveat sweep, the reason check — is defeated by a line
  break at the wrong column**, silently. Unwrap first:

      tr '\n' ' ' < FILE | grep -o "phrase you are retiring"

  **And then read every hit's context, not the count.** *A count of 1 is
  exactly what a stale assertion looks like from a distance, and "the grep
  returned few hits" is the same mistake as "the grep returned none" in a
  smaller font.* The sweep that found the two stale claims in this repository
  returned four hits for one phrase; three were quotations retiring it and one
  was live.

* **The correction lands in the body and the headline keeps the retired
  claim.** Instances below, with how each was caught — counting the commentary
  about the list as part of the list, because the commentary errors are
  demonstrably the same shape at a smaller scale. **The lead carries no
  count**, for the reason recorded at item 18:

       1  bit 5 asserted in three tables         deliberate (eye)
       2  a "NEW DEFECT" framing                 deliberate (peer)
       3  a subtitle contradicting its section   INCIDENTAL, ordering
       4  a retracted gloss in a second file     TOOL
       5  a retired rationale in two files       TOOL
       6  "the base is a fixed offset", flat     TOOL
       7  a retracted channel reading, flat      TOOL
       8  this bullet's own "four of five"       INCIDENTAL, diffing for scope
       9  "one line remains over 88 columns"     INCIDENTAL, checking elsewhere
      10  this bullet's lead saying five         deliberate (peer)
          while its table said seven
      11  a section HEADING: "NONE confirmed,    TOOL, second pass
          and the address space is wrong"
      12  "no corpus validation at all"          TOOL, second pass
      13  a HEADING: "why the disc search        TOOL, second pass
          could never have worked"
      14  a HEADING counting "EIGHT" routings    TOOL, heading sweep
          above a body that says seven
      15  a HEADING asking whether two forms     TOOL, heading sweep
          share a span, after it was measured
      16  a HEADING and an opening sentence      TOOL, third pass
          left standing while the SAME
          paragraph's third sentence was fixed
      17  "dropped, not converted" stated as     TOOL, third pass
          settled, where it is code-only
      18  this bullet's lead saying TEN          INCIDENTAL
          while its table said seventeen

    TOOL        11    reproducible, handable to the next session
    deliberate   3    schedulable, but human and expensive
    INCIDENTAL   4    not reproducible at all

  **TALLY CLOSED AT SEVENTEEN, 2026-09-21 16:40**, at this document's own
  recommendation: further items were adding arithmetic rather than insight.
  The rules below are what the count was for. **Reopened once, at 16:52, for
  a new SHAPE rather than a new instance** — the invalid-denominator entry
  above — on the stated rule that a new mechanism is worth reopening for and a
  new instance of a known shape is not.

  **Items 14 and 15 are this repository's own**, found by running the heading
  rule the moment it was stated. Neither was findable by the phrase sweeps run
  earlier the same day: **one is a stale NUMBER and the other a stale
  QUESTION**, and a claim-sweep has no pattern for either.

  **Items 10 and 18 are the bullet describing the pattern, committing the
  pattern** — the lead left at "five" while the table grew to seven, then at
  "ten" while it grew to seventeen. **The list has now eaten its own
  commentary three times**, at items 8, 10 and 18.

  **And the recurrence has a structural cause rather than a careless one.**
  This is the one paragraph in the document whose **body grows on every
  edit** — each new instance appends a row — while its lead restated a
  quantity the body derives. **A headline that restates a derived quantity is
  stale by construction**: correct only in the instant between two edits, and
  broken again by every append.

  So the fix is not counting more carefully. **The number is deleted from the
  lead.** The table and the totals are now the only place a count appears —
  one source of truth, nothing to restate, nothing to go stale.

  > **Do not restate in a heading a quantity that the body derives.**
  > The heading/body rule above says *fix both in the same edit*; this bullet
  > proved three times that "remember to fix both" does not survive contact
  > with an append. **Removing the duplicate does.**

  **The ratio moves when the instrument is used, and it is now the majority.**
  Nine of the fifteen exist because sessions ran sweeps that had not existed
  four hours earlier — items 11–13 on a *second* pass after the first pass's
  own blind spot was identified, 14–15 within a minute of the heading rule
  being written down, and 16–17 on a *third* pass against patterns that were
  hours old. **Four hours earlier the count was zero of five.** That is the
  argument, and it survives everything else on this list being luck.

* **Right in substance, wrong in the detail a reimplementer would type.**
  Twice in one day, from the same session: `record[+38]` dropped from a tuning
  formula whose own cited number needed it, and a 92-byte layout whose tail
  was described as three bytes and a spare when it is two sign-extended words.
  **Both conclusions were correct and both sets of coordinates were not** —
  the arithmetic agreed, the offsets would not have compiled into anything
  that worked. **A claim can be true at the level it is argued and false at
  the level it is used**, and review at the level it is argued will not catch
  it. Both were caught by going back to the primary source **for an unrelated
  reason** — the disc one time, the operand widths the other.

* **A cheap suggestion can be wrong in its stated reason and still be worth
  taking.** `0x1630C0` was proposed as "one function, and it moves an `[S]` to
  a `[C]` or kills it". It is three instructions and names nothing, so the
  justification was false — and tracing it anyway cost three minutes and
  exposed the layout error above. **Judge a cheap check by its cost, not by
  the quality of the argument for it**; judge an expensive one by the
  argument.

* **A FLAGGED ASSUMPTION SHOULD BLOCK THE COMPUTATION THAT DEPENDS ON IT,
  NOT ANNOTATE IT.** The strongest item in this record, because the warning
  was already written and in the file. The `0x7af1c` bullet said, in bold,
  **"Not established: that `fp@(12)` is the previous struct's position. That
  was assumed, not read."** Four sections then computed
  `req = next − base − 48` as though it were — producing a 0/18, a 6/18, a
  ratio cluster and a residual lead, **none of which was a test of anything**,
  because `req` was never a length. Every one of the four cited the flag.

  **This defeats every rule above it.** The claim was correctly scoped,
  correctly labelled, not stale, not in a heading, and the sweeps would have
  found nothing wrong with it — *the annotation was accurate the whole time*.
  It simply did not stop anybody. An `[?]` marker is addressed to a reader;
  the thing that needs restraining is the next computation, and a computation
  does not read markers.

  So the rule is mechanical, not attentional: **when a quantity is flagged as
  unread, nothing downstream of it gets a SCORE.** Trace it first, or state
  the result as conditional in the same sentence as the number — never a
  clean `n/18` with the caveat two sections away. *Compare the rule recorded
  elsewhere in this project: put the check where it cannot be skipped, not in
  prose that can be not-reached-for.*

  **A CANDIDATE LIST IS A TODO, NOT A FINDING.** The same shape one level up,
  and it is the generalisation the other two are special cases of. Three
  candidate explanations were listed and sat for twenty minutes *looking
  handled*; two were eliminated the moment anyone ran them, at a cost of one
  disassembly each. **Listing them felt like rigour and discharged the feeling
  of having dealt with it.** If an item on such a list is cheap to test, not
  testing it is the error — and the list should say what each one costs, so
  that the cheap ones cannot be left sitting.

  **Caveat, candidate, denominator: all three are annotations standing in for
  work.** *Writing something down is not doing it.* That is one rule, not
  three, and it is the whole of what this material taught in a day.

  **It was applied FORWARD within the hour, by the session that wrote it**,
  and that is the part worth copying. On finding that the extent is built
  from the subrange pair, the obvious next sentence — "so the loader reads
  only the loop" — was **not written**, because `0x7ac24` storing a length at
  `entry[+60]` and passing an extent to `0x77a48` being *the same value* is
  assumed, not read. The anomaly is recorded as open and nothing is derived
  from it. **A rule demonstrated once on live work is worth more than the
  same rule sitting in a method section as advice.**

* **A RETRACTION IS A CLAIM, AND IT CAN BE RIGHT WITH THE WRONG EVIDENCE.**
  Candidate 1 above was withdrawn on `0x7ab84` (`moveal %a1,%a5`) — which
  only shows that `0x7ab78` reads the struct `0x79024` filled, and says
  **nothing** about whether `0x79024`'s *source* object is the disc
  wavesample block, which is the entire question the candidate raised. The
  conclusion was right and the argument did not reach it. Its author caught
  it within the hour and supplied the evidence that does reach it — the
  stride-288 array accessor at `0x78c84` — **and recorded the mis-step
  separately rather than quietly upgrading the citation.** A retraction that
  is believed for a reason that does not hold is a claim waiting to be
  re-opened by the first person who checks the citation.

* **Audit the INSTRUMENT, not only the population.** The same session that
  found its validation set invalid — twelve of eighteen pairs not meeting the
  precondition — then built two further results on a **decoder it had never
  calibrated**, one handed to it with an explicit warning that a signed shift
  was load-bearing. **The apparatus was the thing nobody checked**, and it
  sits upstream of every number derived through it. Validate a decoder against
  an independently known value *before* the results, not after they stop
  agreeing.

  **Epilogue, and it does not soften the rule: the decoder was fine.** Checked
  the next day, `0x78cc4`'s output satisfies both of `0x790be`'s inequalities
  on 17 of 18 structs before any clamp. **An uncalibrated instrument that
  turns out to be accurate was still uncalibrated when the results were
  published** — and the cost of finding out was paid anyway, by everyone who
  had to hold four numbers as provisional until somebody checked.

* **WHEN A MACHINE'S BEHAVIOUR DEPENDS ON OPERATOR STATE, NO AMOUNT OF
  DISASSEMBLY CONTAINS THE ANSWER.** Two sessions took a hardware
  observation — a volume-level import yielding 2 presets where a
  performance-by-performance one yielded 10 — filed it as a firmware
  selection rule, wrote a scope warning for users on the strength of it, and
  queued ROM traces. **The instrument displays a dialogue at that moment
  saying it will load a single bank from the folder, and asking which one.**
  The answer was on the screen.

  **Ask the operator before tracing.** The ROM has no opinion about where the
  cursor was, what a dialogue asked, or what was clicked — and those are
  first-class causes of observed behaviour, not noise around the real
  mechanism.

  **The sibling failure that kept it alive is worth its own line.** A
  performance's patch-id list was resolved **1-based when it is 0-based**,
  which made the two loaded presets appear to come from two *different*
  performances — and no "one bank from the folder" rule can explain that.
  **So the correct explanation was excluded from the candidate space before
  anyone proposed it.** An off-by-one that produces a wrong *value* is caught
  when something downstream disagrees; this one agreed with everything it
  touched, and its only effect was to make the right answer look refuted.
  **A wrong result is self-limiting. A wrong result that eliminates a
  hypothesis is not.**

  **And the disagreement nobody treated as one.** This project read the same
  disc, found `E-Guitar 1` to be a single patch in a group of far more than
  two, reported the disagreement, and stopped rather than guess at the other
  session's structures. Stopping was right on the information available —
  **but two sessions reading the same bytes to different conclusions is
  evidence about the readers, and neither side spent five minutes on it.**

* **AN OFFSET CONSTANT IS NOT A SIZE CONSTANT, AND AN EXACT HIT ON ONE
  MEMBER OF A SET IS ONE DATUM.** Two failures in a single reconciliation,
  and it is the second false reconciliation of the evening by the same
  session — *the first was fabricated; this one was arithmetically exact,
  which made it more attractive and no better founded.*

  * **The `+24` linking a dump frame to a file frame is an OFFSET
    relation** — fields sit 24 bytes later in the dump. It was applied to
    **sizes**. Where the documented case can be checked, the sizes differ by
    **22**, not 24: a 1-layer program is dump 272, file 250. *Offsets and
    sizes are different quantities and a constant established for one is not
    established for the other.*
  * **`796 + 24 = 820` hit the middle of a three-way split `816/820/824`** —
    and **the other two values fit nothing the explanation offered**, which
    neither session remarked on. An exact hit on one member of a set, with
    the rest unaccounted for, is **one datum dressed as a confirmation.**

  > **The mechanism produced two findings and the reconciliation produced
  > none.** Asking what a reader's grep would return exposed the frame
  > confusion; refusing the tidy answer to it exposed the real error. *Both
  > came from declining to accept something that fitted.*

* **ASK WHAT A FUTURE READER'S GREP WILL RETURN. IT IS THE ONLY MECHANISM
  HERE THAT CATCHES A SCOPE CHANGE BEFORE IT PROPAGATES.** Every other entry
  in this catalogue is retrospective: a claim is found wrong *after* it has
  travelled. This one is not.

  A peer quoted *"a method `0x17` keymap is 796 bytes"*. Both numbers in the
  ensuing discussion were correct — `796` measured on a SysEx dump,
  `816/820/824` measured on file objects — and **neither session had said
  which frame it was in.** The trigger for raising it was not an error, but a
  question: *what happens when somebody greps a real file for 796?* **It
  returns nothing, and the natural reading of nothing is that the analysis
  was wrong.**

  **That is the third scope-change of the day** — after a number computed to
  verify reused as an instruction, and a constant documented for one
  machine's output applied to another — **and the first caught before it did
  any damage.** It required no error to exist. *Simulate the reader, not the
  claim.*

* **RECORD A FAILURE WITH ITS METHOD, NOT ITS VERDICT. A VERDICT TELLS THE
  NEXT PERSON NOT TO BOTHER; A METHOD TELLS THEM WHAT TO CHANGE.** Both
  sessions nominate this as the most useful thing either of them found, and
  it is the only rule here that turns a dead end into someone else's lead.

  `eosed` tested the EPS header table against `O1`, concluded *"the values
  are not positions"*, and **filed it as tested-and-failed specifically so
  nobody would re-run it** — which was right. But they wrote down **how**:
  *raw, doubled, ×512, and offset from the known base 880*. That list is
  what made the failure re-usable. This project read it, saw that `× 16` —
  the transform the firmware itself performs — was **not in it**, ran that
  one, and `O1` fell.

  **Had the entry said only "tested, failed", the lead was dead.** The
  verdict was correct and the method was incomplete, and only the second is
  visible to a reader.

  > **And the proof was inside the failing report.** §171 printed
  > `idx 9 -> 55` three paragraphs below a section stating the base is
  > **880**. Its author wrote both in the same commit and did not multiply.
  > *A number and its own confirmation can sit on one page without meeting,
  > because nothing makes a reader apply an operation they have not thought
  > of.*

* **THE PEER BOUNDARY IS LOAD-BEARING, AND THE CHECKS ARE NOT SUFFICIENT
  WITHOUT IT.** Five structural checks came out of this material. Where each
  was caught:

  | check | caught by | in whose file |
  |---|---|---|
  | unwrap before a phrase sweep | k2kremote | this project's |
  | delete the duplicated count | k2kremote | this project's |
  | block the flagged assumption | eosed | **their own** |
  | validate a base on ONE object | this project | k2kremote's |
  | prove byte order on a discriminating field | k2kremote | this project's |

  **Four of five were caught across a session boundary. The one self-catch
  happened only because that session had just withdrawn four results and was
  re-reading its own scores for an unrelated reason** — incidental, which is
  the mechanism that has done most of the work in this document and the one
  that cannot be scheduled.

  > **And in one evening the boundary fired four more times, in a chain
  > where each link was the previous one's disclosure:**
  >
  > 1. k2kremote wrote down that instrument-blaming is untested by
  >    construction — **and did not apply it to their own live claim.**
  > 2. This project applied it to *its* claim. It overturned a published
  >    `[C]`.
  > 3. k2kremote then applied it to theirs. It overturned a "direct
  >    confirmation" — a median over a coin-flip distribution.
  > 4. This project disclosed that its own denominator was filtered. **That
  >    disclosure is the only reason k2kremote looked at theirs**, and found
  >    a filter retaining the compared groups at 12.7 % … 57.7 %.
  >
  > **Nobody in this chain was careless and nobody found their own error
  > first.** Each rule was written by the session that then failed to apply
  > it, and fired only when someone else's disclosure made the question
  > concrete. *The Roland findings will be superseded. This will not.*

  **So the honest summary is not that the day produced five instruments.** It
  is that it produced five instruments *and* a record showing that almost
  none of them would have been found by the session that needed them. That
  argues for the boundary, not for the checks. **A check written by the
  person who needs it is still read by the person who wrote it.**

  *Related, and it cuts the other way: crediting a check to whoever phrased
  it hides this. Two of the three phrased here came out of this project's own
  errors being caught from outside.*

* **REPORT THE DISAGREEMENT, NEVER THE EXPLANATION, UNTIL THE EXPLANATION HAS
  BEEN MEASURED.** Sharper than the dissolved-anomaly rule above, and worse:
  a *false* explanation at least leaves a contradiction for someone to trip
  over later. **A TRUE one closes the question permanently and leaves nothing
  behind.**

  The instance is exact. One header word disagreed between two sessions out
  of nine compared. *"Probably a transcription difference"* would have been
  **true** — it was a transcription difference — and this project would have
  accepted it, and the byte swap would have stayed in the document. It was
  caught only because the other session reported the disagreement bare and
  explicitly declined to account for it. **Its author notes they withheld the
  explanation because they had been caught inventing one an hour earlier,
  and that this is a scar rather than a method.** The method is the rule
  above.

* **PROVE BYTE ORDER ON A FIELD WITH TWO NON-ZERO BYTES, AND TREAT AGREEMENT
  ON SMALL-VALUED FIELDS AS NO EVIDENCE AT ALL.** A field holding a small
  value carries a zero byte, and a zero byte is nearly order-agnostic. **So a
  format full of small values can be read end-to-end in the wrong byte order
  without a single field complaining.**

  Measured on the Roland sample record — of its **sixteen** two-byte-aligned
  positions, counting records where *both* bytes are non-zero:

      +16  +18  +36  +38  +40  +42        0 of 4128   <- cannot ever discriminate
      +28  +32                            4 of 4128
      +24                                40 of 4128
      +20                                97 of 4128
      +22  +26  +30  +34  +44        876 … 2581

  **Six of the sixteen can never test byte order on any record in this
  corpus**, and four more are effectively useless. Five positions carry the
  whole of the evidence. *An endianness "confirmed" on any of the first ten
  is confirmed on nothing.*

  **Two consequences the rule alone does not give, both from the census:**

  * **The discriminating positions are `+22`, `+26`, `+30`, `+34` — the high
    halves of the four 32-bit fields nobody has decoded — plus `+44`.** So
    **the byte order of this record is attested only by fields whose meaning
    is unknown.** The evidence for *how to read* the record comes entirely
    from the part of it we cannot interpret.
  * **Both fields that ARE validated here are byte-order-blind.** `+42`
    (size) sits in the never-column and `+45` (root key) is a single byte.

* **A NEGATIVE RESULT IS ONLY AS STRONG AS ITS DECODING ASSUMPTION — AND THE
  ASSUMPTION IS RARELY THE ONE YOU CHECKED.** This document wrote that
  sentence about *byte order*, tested the Roland fields under both orders,
  found thousands of violations either way, and published a `[C-neg]`. **The
  fields are 24-bit at group-base + 1, in samples.** Width, alignment and
  unit — three assumptions below the one that got audited. `LE32 at +20` is
  `rec[20] | loopStart << 8`, so the test fired on a misaligned read, which
  is exactly what it was built to do.

  **The evidence for the correct decoding was already in this document, in a
  section written to argue something else.** The byte-order census recorded
  that `+22`, `+26`, `+30` and `+34` carry all the discriminating power —
  *those are the high bytes of the 24-bit values* — and that `+16`/`+18` can
  never discriminate, which is the same fact at two-byte granularity. **The
  signature of the right answer was measured, written down, and read as a
  curiosity about endianness.**

  So: when a negative rests on a decode, **enumerate the decode's assumptions
  and say which were tested** — width, alignment, unit, signedness, order —
  rather than naming the one that happened to come to mind. A `[C-neg]` that
  names only one of five has tested one of five.

* **AGREEMENT BETWEEN TWO READINGS OF THE SAME CONVENTION IS NOT EVIDENCE
  ABOUT THE CONVENTION.** The `size` field at `+42` was supported by its
  match against the directory's own `+0x1E`. **Read both big-endian and they
  still agree perfectly** — a cross-match proves the two fields are
  *consistent*, not that either is read the right way round. The real
  evidence is the global fit, where a swapped reading misses the image size
  by orders of magnitude; the cross-match is worth nothing and had been cited
  as though it were.

  **Second instance in one evening of a corroboration that corroborated
  nothing** — the first was `+36`'s distribution having exactly the shape a
  rate code would have. *Both felt like independent support and both were
  restatements of the thing being tested.*

* **FIXING AN INSTANCE WITHOUT SWEEPING THE CLASS.** The argument that solved
  the Roland velocity quartet — *every offset below 16 lands inside the
  4-byte tag and 12-byte name* — is a statement about **every row of that
  table**. It was written as a general finding, placed two sections above the
  table, and then applied to the four rows its author had in hand. **Two
  identical rows sat wrong for hours with their own refutation already
  published above them.**

  **This is nastier than anything else in this catalogue because nothing was
  false.** The general statement was true, the corrected rows were true, and
  the uncorrected rows were simply never revisited — so no sweep for stale
  claims, retracted headings or wrong numbers could have found it.

  **A discovery does not apply itself.** The moment a finding is general, the
  next action is to **enumerate what else it condemns**, and that enumeration
  is a different act from making the finding. *Sibling of the candidate-list
  rule: there a cheap test left unrun, here a general result left unapplied.
  Both are the gap between knowing and doing, and both feel like completion.*

* **AN IDENTITY BETWEEN TWO CLOSED FORMS IS NOT A VERIFICATION OF AN
  IMPLEMENTATION.** Two sessions agreed on `maxPitch` to 2 × 10⁻¹³ across
  thirty rate/root combinations — one form fitted from real `.KRZ` files, one
  read as a continuous function out of the ROM — and reported it as the
  strong convergence this catalogue had just demanded. **The firmware
  evaluates neither form.** It does a descending search of a log table, and
  the table's resolution could place an entry a cent either side without
  either session seeing it: one had fitted to the table's own outputs, the
  other had checked algebra against that fit.

  **The agreement was real, and it corroborated the design INTENT rather than
  the emitted VALUE.** *The table was then read and the two turned out to
  coincide — worst deviation 0.314 cents, the firmware's integer being
  `round(continuous)` on every rate.* **That does not retire the rule.**
  Nothing before the reading distinguished this outcome from a table a cent
  off, and the caveat is what caused the reading. **A check that comes back
  clean is what a correct caveat looks like most of the time.**

  **Filed beside the answer-set family, which is where it belongs:** it is
  the same question — *what could this evidence have come out as?* — asked of
  a **proof** instead of a measurement. Two closed forms can only ever agree
  or not; neither of them can tell you what a table does.

  **And a second shape underneath it, from the same exchange:** the cents
  column was computed with `round()` **in order to check the other session's
  formula**, then republished as *"what a converter writes"*. **A number
  computed to VERIFY a claim, reused as an INSTRUCTION.** The two purposes
  want different arithmetic — verification wants the continuous truth,
  instruction wants the device's own truncation — and nothing marks the
  moment a figure changes role.

  **A THIRD FORM, and the nastiest: a value DOCUMENTED for one context,
  applied to another.** The `0x78` prediction was built on `0x70` because
  `KRZ_FORMAT.md` documents that constant — **but that document describes
  what THIS PROJECT'S WRITER emits, and the prediction was about what THE
  K2000 emits.** The device's base is `0xB0`, so the prediction should have
  been `0xB8`.

  **Nothing was computed wrongly and nothing was stale.** The constant was
  correct where it was written; only its **scope** changed. *And a scope is
  even less re-derivable than a caption, because the source document was not
  wrong and therefore had no reason to qualify itself.* **When you borrow a
  constant from a format document, check whose output that document
  describes.**

  **Two more instances, both this project's, and both HARDER than the one
  that names the rule:** a retention-filtered sample published as a
  population, and a `14/14` published as a rate result. In that instance the
  arithmetic was wrong for the new purpose, so something *was* incorrect. In
  these two **the figure was fully correct in its first role** — the sample
  really did describe its survivors, the 14 really were 14 of 14 — so
  nothing about the number is ever wrong. **Only its caption changes**, and a
  caption is not something anybody re-derives.

* **TWO METHODS AGREEING IS EVIDENCE ONLY IF THEY COULD HAVE DISAGREED.
  CHECK WHAT EACH ONE SILENTLY DROPS BEFORE TREATING CONVERGENCE AS
  CORROBORATION.** Two sessions' strictest name parsers agreed to within
  0.2 % where every looser variant diverged wildly. **The agreement was
  worthless:** both rules require the note to be the name's trailing token,
  a stereo sample's name ends in `L`/`R`, and the two requirements compete
  for the same character. **0 of 1472 stereo records pass either parser** —
  35.7 % of the disc excluded by construction, code 5 gone, the loop modes
  inverted.

  **This is the one place in this record where independence in the STRONG
  sense was present and still insufficient.** Different sessions, different
  code, no shared lineage, no discussion of implementation — the convergence
  passed every corroboration test in this document. What was shared was not
  an *assumption* but a **side effect**: neither author decided to exclude
  stereo samples and neither knew they had.

  So this is the answer-set rule aimed at **agreement** rather than at
  outputs, and it adds a fourth question to the family below: **what does my
  agreement with someone else actually rest on?** Answerable the same way and
  by the same inspection.

  > **And the direction is what makes it hard.** Nobody caught anybody's
  > error here. One session caught a *convergence* of both and declined to
  > spend it, and that refusal is what made the test possible. **Declining to
  > bank an agreement is harder than reporting a disagreement**, and nothing
  > else in this catalogue would have prompted it.

* **A NEGATIVE RESULT ABOUT YOUR OWN INPUTS IS THE EASIEST EXPLANATION TO
  REACH FOR, AND IT LEAVES THE FRAME INTACT.** This project measured three
  header bytes identically zero across 5124 programs and a 136-entry scan
  matching nothing in the format, and read both as *"my offsets are wrong"*.
  The measurements were correct and were saying *"your format is wrong"*.

  **The two readings cost different things, and that is the whole
  mechanism:** re-checking a number costs minutes; abandoning the format
  costs a day's work and every claim built on it. **The cheaper reading wins
  by being cheaper, not by fitting better.**

  **The version that operates on someone ELSE's anomaly is worse**, because
  it costs you nothing at all: *when a peer's measurement contradicts your
  frame, the first available reading is that their inputs are bad.* Both
  sessions did exactly that here, to the same measurement, at the same time.
  *File it beside the frame-inheritance rules — it is how a frame survives
  contact with evidence against it.*

* **AND THE THIRD: THE SELECTING VARIABLE WAS NEVER THE ONE BEING SEARCHED
  ON.** Two search designs failed on the AKAI arm — a region-scoped one and a
  `jsr`-reference one — and both failures were explained at the time. **The
  real reason is simpler and subsumes them:** AKAI is not selected by the
  disc format code at all. It is selected by a **medium/device type byte**
  (`moveb %a0@(5)`, value 1, at `0x129938`), and there is no format-code test
  anywhere near the AKAI code.

  **Searching harder on the format code could never have worked**, however
  the search was scoped or whatever call form it followed. *Before deciding
  a search failed, check that the variable you searched on is the one the
  code branches on.*

* **AND THE FOURTH, THE SAME SHAPE POINTED AT HARDWARE: A QUEUED RIG STEP
  CAN BE STRUCTURALLY INCAPABLE OF SETTLING WHAT IT WAS QUEUED FOR.** `O9`
  sat behind "one bank save" for a day. The save would not have answered it:
  the bytes in question are written from `patch+12..15`, **offsets into EOS's
  in-memory patch, not into the file record**, and the in-memory patch is not
  the disc record shifted by a constant — so no file-side comparison, however
  rebased, could reach them. *(The `+29` probe coming back binary-valued was
  that fact arriving as a symptom.)* It closed offline, from the destination
  side, at `0x171434`.

  **Before booking rig time, say which frame the answer lives in and check
  that the measurement can see that frame.** Rig time is the expensive
  resource here; a step that cannot answer still costs a card crossing.

* **A STATED LIMITATION ON A SEARCH IS A REASON TO REDO THE SEARCH, NOT A
  LICENCE TO REPORT ITS RESULT.** `eosed`'s rule, in their words, after their
  "not found" on the `O2` accumulator turned out to be a window that stopped
  `0x190` bytes short of the answer. Their own message carried *"it may sit
  elsewhere in the function than the window I read"* — and the result was
  filed as not-found anyway. **Both sides then called recording it as
  "unlocated rather than refuted" the careful option. The careful option was
  another `objdump`.** *This is the flagged-assumption rule at its cheapest:
  the fix was one larger address range.*
* **WHEN TWO REVIEWS DISAGREE, THE DISAGREEMENT IS USUALLY SMALLER THAN
  EITHER — AND READING PAST BOTH QUOTATIONS SETTLES IT.** On the same
  function one review read `7ab62: addl %d0,%a3@` and the other
  `7ab64: moveq #0,%d0`, i.e. "the 92 is added" against "the 92 is
  discarded". **Both instructions exist**; the second is the function's
  return value, two before its `rts`. The conflict was four bytes wide and
  neither quotation was long enough to contain it. *Holding the document
  until someone read those four bytes was the right call, and cost one
  message.*
* **THE OWNER OF THE EVIDENCE IS NOT THEREBY RIGHT.** The `ALLOCATE`
  lifecycle was wrong, it overwrote a correct relay, and it came from the one
  session that had the ROM — with confident reasoning attached about
  converters colliding over ids. **The reasoning was what made it
  persuasive, and the reasoning was downstream of the error.** Ask for the
  bytes from the owner too.

* **A NEGATIVE CONTROL HAS TO BE TAKEN BEFORE THE THING IT CONTROLS FOR
  EXISTS.** Reading Program 199 *before* the AKAI import is what made a
  one-byte diff readable. An hour later it would have been six programs that
  merely *looked* like defaults, and the only honest conclusion available
  would have been "the filter values disagree with the source" — which is
  true, uninformative, and would have sent the next session looking for the
  conversion table that mangled them. **The control is worthless the moment
  the machine has been touched, so it is not a step that can be deferred to
  when there is time.**
* **THE OUTCOME A FORK TABLE LEAVES OUT IS THE ONE WHERE THE MECHANISM IS
  SIMPLY WRONG.** Two predictions were registered with a four-row table of
  what each result would mean. Both failed, *in opposite directions* — the
  largest span got the smallest table and the smallest span the largest — and
  that row was not in the table. **A fork table written by someone who
  believes the mechanism enumerates the ways it could be refined, not the way
  it could be absent.** Add the row that says "the variable is not the
  variable" before running the test.
* **COLLINEAR HYPOTHESES NEED A POINT OFF THE LINE, NOT MORE POINTS ON IT.**
  Three allocations, `384 / 512 / 640`, fit *both* "+128 per import in load
  order" *and* "`(37 − n_samples)/6` blocks" with no residual, because sample
  count fell while load order rose. A fourth volume would most likely lie on
  the same line again. **The test that separates them is re-importing an
  ALREADY-MEASURED volume**, which holds content fixed and moves position —
  one import, no new ground truth, and no third reading.
* **A CLIPPED BOUNDARY IS DIFFERENT EVIDENCE FROM A MISSING ONE.** The last
  surviving keymap zone read `75..75` where the source says `75..76`. "The
  top zones were dropped" and "the table ran out" look identical in a list of
  what is absent, and are told apart only by what is *half* present. The
  mechanism — sized from the span, indexed from the base — followed in one
  step once the half-zone was noticed, and it had been reported without being
  noticed.
* **AN EXACT NUMERIC COINCIDENCE CAN MAKE A DECISIVE-LOOKING TEST POINT THE
  WRONG WAY.** `412 = 28 + 64×6` **and** `412 = 28 + 128×3`. A peer proposed
  "if no corpus keymap is 412 bytes, the truncation reading wins"; 347 of 1610
  corpus keymaps are exactly 412 bytes, for the *other* reason. Answering the
  question as framed would have inverted the conclusion. **Before running a
  proposed decisive test, check whether the quantity it keys on can be reached
  by more than one route.**
* **THE QUESTION CAN BE WRONG, NOT JUST THE ANSWER.** `O6` spent weeks
  hunting an unlocated AKAI program builder. There is no builder: the import
  writes one byte. Every failed search was a correct negative about a thing
  that does not exist. *File it beside the selecting-variable rule — that one
  was searching the wrong variable, this one was searching for the wrong
  object.*
* **DO NOT WRITE AN EXEMPTION FOR A RULE THAT WAS ALREADY SCOPED.** Finding
  that the device discards nearly everything, this session proposed recording
  an explicit suspension of "match the device" for the AKAI arm. The rule
  already said *"the only definition of correct available when the source
  instrument is absent"* — and an S3000XL is on the bench. **A suspension in
  the record reads as "the rule was inconvenient here" and weakens it
  everywhere it genuinely binds.** Re-read the rule's own scope before
  carving an exception out of it.

* **AN ITEM THAT TRAVELS INSIDE A CORRECTION INHERITS THE CORRECTION'S
  CREDIBILITY.** The `format 5 = AKAI` label arrived in a message that was
  correcting this project's own field mapping — and was mostly right. **The
  parts that were load-bearing got checked; the framing line was taken as
  given.**

  **Being corrected is the context in which a reader is least disposed to
  audit the corrector**, and a wrong item riding inside a right correction is
  therefore about as unexaminable as an assertion gets. *It is the
  verify-versus-instruct family again, with credibility rather than a number
  doing the travelling.*

  > **And the label itself rested on PROXIMITY** — the AKAI strings and the
  > format-5 tests both living in `0x12Axxx`. A **region argument**, filed
  > against by its own author hours earlier as *"an anchor that is a region
  > is not an anchor"*, and committed again the same evening.

* **AND THE SECOND HALF: FOR AKAI THE DISPATCH IS A FUNCTION POINTER, SO NO
  `jsr`-REFERENCE SEARCH FINDS IT EITHER.** The Roland and Ensoniq arms were
  each located by a single direct `jsr` from the format test. The AKAI arm is
  not reached that way — `0x122200`/`0x122204` call indirectly through
  `a5@(4740)`, a media-variant-selected slot, and the code after it is
  indirect again (`jsr %a0@`).

  **A method that found two of three arms will report the third as absent**,
  and two successes are exactly what makes it look reliable. *Same shape as
  the region-scoped search one level up: the search space excluded the answer
  by construction, and the hit rate concealed it.*

  > **A correction that came with it, and it matters to anyone chasing this:**
  > `0x17562E` is the **open-by-name** routine, not a loader — it is what
  > opens `"ROLAND.S"` and what the Ensoniq builder calls. So `a5@(4740)` is
  > the **generic file-open slot**, not an entry to an AKAI converter.
  > *Finding a vtable is not finding the thing you were looking for.*

  **So `O6` is not "one address away", and it is not empty either.** The
  `ak_*` filesystem driver is located at `0x1775xx`–`0x1779xx`, and the entry
  to the conversion is known to be **indirect** — which tells the next person
  what *not* to search for, and that is worth more than another grep.

* **A DISPATCH LIVES IN THE CALLER — SO SEARCHING THE CALLEE FOR IT FIXES
  THE ANSWER BEFORE THE SEARCH RUNS.** The strongest `[C-neg]` in this
  document — *"the K2000 has no Ensoniq program converter"* — was built on an
  exhaustive reference set: 26 references to the disc format code, 25 in the
  file layer, the single converter-region one testing a different format.
  **Every count was correct.** There is a converter, at `0x16368A`, and both
  sessions had been documenting it all day under the label "the AKAI arm".

  The test asked whether the format code is compared **inside** the converter
  region. A dispatch is never there; it is in the caller, and the caller's
  comparison was counted among the 25 and read as evidence *against* the
  thing it proves. **Under that method, a converter reached by an external
  dispatch is indistinguishable from no converter.**

  **The corpus said so and was not heard.** Three of four header bytes were
  identically zero across 5124 real programs and a 136-entry scan matched
  nothing in the format — read as *"my offsets are wrong"* when the
  measurement was saying *"your format is wrong"*. **A negative result about
  your own inputs is the easiest explanation to reach for and the one that
  keeps the frame intact.**

  *Fifth instance today of the answer-set question going unasked, and the
  third by a session that had filed the rule.*

* **A CORRECT NUMBER IN THE WRONG BASE, AND A CORRECT NUMBER OF THE WRONG
  QUANTITY — BOTH LOOK LIKE HITS.** Two instances within one exchange, one
  from each session.

  * `objdump` prints an indexed displacement in **hex without a prefix** and
    a plain `%a5@(n)` in **decimal**. One session read both as decimal in the
    same document; the other converted the result to hex without asking what
    base the input was in. The mapping that came out scored **three of
    three** against real AKAI fields and one hit was called "the clincher".
    Re-run on the true offsets, **three of the four bytes are identically
    zero across 5124 programs** and the conclusion inverts.
  * The same document had just flagged `ROOTDIR_ENTRIES = 100` against a
    100-**byte** offset as a coincidence to avoid — a correct number of the
    wrong *quantity*. The base error is its sibling and neither is detectable
    by checking the arithmetic, because the arithmetic is right.

  **The transferable part: when you transform a peer's numbers, state the
  unit you assumed back to them.** The conversion is a claim, and here it was
  the only wrong step in a chain where nobody's *reading* was at fault.

  **And the enumeration that found the fourth field is its own lesson:** the
  first pass used `([0-9]+,%d2:l)`, which cannot match `2c`. **A pattern that
  cannot express the shape the data takes returns a clean short list that
  looks complete** — the wrap-sweep failure in a new costume, and the third
  time today a regex has silently under-reported.

* **A QUANTITY THAT MOVES WITH YOUR PARSER IS NOT A PROPERTY OF THE DATA.**
  Two sessions reported the root/name offset split for rate code 1 as
  **274 / 271** and **299 / 156** and treated the disagreement as a parser
  dispute to be left unadjudicated. Running four defensible extractors over
  the same records gives `+12` shares of **50.3 %, 54.0 %, 49.5 % and
  3.7 %** — and the fourth reading, "the note must be the trailing token",
  is if anything the most conservative of the four.

  **The right response was not to report a range with both attributions.**
  It was to notice that the figure is an artefact of a preprocessing choice
  nobody had validated, and to stop quoting a ratio at all. *Before
  reconciling two numbers, check whether the quantity is determined.*

  **A range is worse than either number alone**, in its author's words:
  it **dresses indeterminacy as precision with error bars.** Two numbers in
  conflict at least look like a problem; a range looks like a result.

  **Sibling of the retention confound**, one stage earlier: there the filter
  selected which records were compared, here the parser decides which records
  *exist*. Both are upstream of the statistic and neither shows up in it.

* **A MEASUREMENT THAT CAN ONLY EVER RETURN "X OR 2X" IS NOT A MEASUREMENT
  OF X — AND THE TELL IS IN THE ANSWER SET, NOT IN THE DATA.** The Roland
  rate codes were checked by implied pitch for hours across two sessions.
  The six table values are **three exact octave pairs** (48000/24000,
  44100/22050, 30000/15000), and the disc's two pitch references — the
  root-key field and the sample name — differ by **exactly twelve
  semitones** on most records. So the method maps every code onto its own
  partner and **can never separate them.**

  **Everything it produced was therefore an artefact of an unstated
  reference choice**: a `[C]` on code 1, a `[C]` on code 4, and a
  "systematic contradiction" on code 3 — which vanished the moment the other
  reference was tried, and whose replacement (code 4 reading as 15 000)
  is *also* a table value.

  **Nobody checked the answer set.** Two octave pairs inside a six-entry
  table is visible by inspection, before any audio is loaded, and it
  determines in advance that the experiment cannot succeed. *Look at what
  your method is able to distinguish before asking what it found.*

  **And the arm that settled it came from the ROM, not the corpus** — code 5
  = 15 000. **Corollary, and it is the durable half: a method blind to one of
  its own categories will never report that category missing.** 15 000 was
  not *absent* from the measurements, it was **absorbed** — the estimator had
  no way to produce "none of the above", so nothing in hours of results could
  ever have flagged a sixth arm.

* **AN INVARIANT CANNOT TEST THE QUANTITY IT IS INVARIANT UNDER.** The
  strongest-sounding evidence for the 44.1 kHz arm was that a choir set's
  periods *"track the labels exactly — 1.198, 1.181, 1.179, 1.198, 1.186,
  1.200 against a true semitone of 1.189 — which a wrong root field or a
  wrong rate cannot fake across seven entries."* **True, and irrelevant:
  ratios are invariant under a uniform factor of two.** The sequence proves
  the *relative* pitches are consistent and says exactly nothing about the
  absolute octave, which was the only quantity in dispute.

  *The most convincing argument in the exchange was built on the one
  property the ambiguity preserves.* Before offering a consistency result as
  evidence, ask what transformations it survives — and whether the disputed
  quantity is one of them.

  **And why it persuaded is the part to keep, in its author's words:** seven
  entries agreeing to fractions of a percent **does** rule out a mislabelled
  individual root, a scattered rate field and a broken estimator. *It rules
  out everything except the one hypothesis in play.* A result can be strong,
  correct, and decisive against every alternative but the live one.

  **Three questions, one family, all answerable before any data is
  collected — and none of them was asked:**
  1. **What can my METHOD distinguish?** (the answer set — three octave
     pairs, visible by inspection of the table)
  2. **What can my EVIDENCE vary?** (the invariant — ratios survive the
     factor of two in dispute)
  3. **What ALTERNATIVES am I holding?** (the live hypothesis was not in the
     set the argument was decisive against)
  4. **What does my AGREEMENT with someone else rest on?** (two parsers
     converged because both silently excluded the same third of the disc)

  **The third is the one this record keeps arriving at from new directions.**
  *A result can be strong, correct, and decisive against every alternative
  but the live one* — and nothing about the evidence can tell you the
  alternative set is incomplete, because the evidence is only ever evaluated
  against the set you hold.

* **"UNMEASURABLE BY THIS INSTRUMENT" IS NOT "UNCONFIRMED", AND REPORTING IT
  AS SCATTER ATTRIBUTES TO THE DATA WHAT BELONGS TO THE METHOD.** Rate code 0
  was reported by both sessions as scattered. Re-run with estimator-boundary
  failures rejected, **31 of 45 of its records drive the pitch estimator onto
  its search floor** — the material is percussive, so autocorrelation against
  a root key has nothing to lock onto. Code 0 was never measured at all.

  **The tell is cheap and was not checked: the best lag landing on the edge
  of the search range.** A confidence threshold does not catch it — a 20-lag
  correlation on bright noise passes `corr ≥ 0.80` comfortably. *Reject
  boundary hits before scoring anything.*

* **A FILTER THAT RETAINS THE COMPARED GROUPS AT DIFFERENT RATES IS NOT A
  FILTER, IT IS A CONFOUND — AND EVERY PERCENTAGE IT PRODUCES CAN STILL BE
  CORRECT.** Rate-code on-grid percentages were compared across five codes
  whose retention under the same exclusion ran **12.7 % to 57.7 %**. Each
  figure was true of its own survivors. The *ranking* between them was not a
  measurement of anything.

  **What survives such a table is only the pairs that retain alike.** Codes 0
  and 1 kept 27.3 % and 27.9 %, so that one comparison is like-for-like and
  it holds. Everything else in the table was a comparison of differently
  selected populations wearing the same units.

  **So report retention PER GROUP, beside the statistic**, not just the
  filter. A stated filter is not enough when the thing being claimed is a
  difference between groups: *the filter has to be shown to be neutral with
  respect to the comparison.*

* **EVIDENCE NAMED IN ADVANCE IS A DIFFERENT KIND FROM EVIDENCE FITTED
  AFTER**, and should be reported as its kind rather than converted into a
  percentage. Rate code 4 = **30 000 Hz** was read out of a jump table
  *before any audio was touched*, and then measured at 1.00. Its "68 %
  on-grid" sits on 57.7 % retention and is not comparable to any other row —
  **but no retention artefact can manufacture a correct odd number named in
  advance.** Converting a prediction into a percentage threw away the
  property that made it strong.

* **A SUMMARY STATISTIC IS A CLAIM ABOUT A DISTRIBUTION. REPORTING IT
  WITHOUT THE SPREAD IS NOT COMPRESSION, IT IS SUBSTITUTION.** k2kremote
  reported rate code 0 as *"median 0.999 — direct confirmation"* over a
  distribution that is **50.5 % on-grid: a coin flip.** The median sat on
  target because the scatter is **symmetric around it**, not because the
  prediction held.

  **Both sessions did this in the same hour, on the same codes.** This
  project wrote *"every measurement lands on exactly 1.00 or 2.00"* while
  holding data that scattered; k2kremote reported a median while holding the
  spread that contradicted it. **Neither reached for a summary out of
  laziness — both reached for it precisely because the raw distribution was
  inconvenient.** That is the tell: the statistic that gets chosen is the one
  that survives the data.

  Adjacent and equally mine: **this project's `14 × 1.00` was a FILTERED
  sample** — `corr ≥ 0.85`, pitched roots — reported without the filter. A
  legitimate exclusion, an illegitimate denominator. *The population figures
  are 79.3 % and 68 %, not 100 %.*

* **DISMISSING AN ANOMALY AS AN ARTEFACT OF YOUR OWN INSTRUMENT IS THE MOST
  INSIDIOUS FORM OF DISSOLVING IT — BECAUSE IT LOOKS LIKE HUMILITY.** The
  other dissolutions in this catalogue blame the data or invent a
  definitional story. This one blames your own tool, **which is exactly the
  caution this document keeps recommending**, so it reads as care rather than
  as a conclusion.

  Two instances, one evening, the second by the session that had just
  recorded the first:

  * k2kremote measured a 22.05 kHz cluster and wrote it off in their own
    commit as *"far more likely autocorrelation octave errors and mislabelled
    roots than real rates"*. It was a real code-3 population.
  * **Third costume, same evening, and the worst of the three:** in the very
    commit claiming 44.1 kHz, the same session wrote *"Roland's displayed
    names sit an octave below the C4 = 60 convention — the field says 42
    where the name says `F#1`."* **That is not a naming convention. It is the
    second pitch reference — observed, written down, and filed as a cosmetic
    quirk**, in the sentence next to the claim it invalidates. Nothing was
    missed; it was seen and dissolved.
  * **This project then did the same thing**, wrote *"the apparent 22 k
    readings are the autocorrelation locking to the octave"*, and built a
    five-arm rate confirmation on top of it. **Tested afterwards: false.**
    Autocorrelation locks onto *multiples* of the true period, so an octave
    lock implies the half-lag also correlates — and on those records the
    half-lag correlation is negative. The periods were real.

  **The tell is that the excuse was never measured.** "My estimator did X" is
  a claim about the estimator and is testable like any other. *If you are
  going to blame your instrument, test the instrument* — here it was one
  extra correlation at half the lag, and it overturned a published `[C]`.

* **AN EXPLANATION THAT DISSOLVES AN ANOMALY IS WORTH LESS THAN THE
  ANOMALY.** Two sessions reported `+20` exceeding the sample extent as
  **4035** and **3721**. A definitional explanation was offered — one side
  testing against audio length, the other against the padded extent — and it
  was **plausible, offered in good faith, and false**: both used the padded
  extent. The whole difference is **314 records whose `+20` is zero**, counted
  by one side as "not a valid offset" and excluded by the other from
  "exceeds".

  **This is the most credible-looking artefact in this catalogue, and it is
  not like the others.** Every other entry is a claim that was wrong. This is
  **two claims that are both right, plus a story about the difference** — and
  the story is the only part nobody re-measures, because it arrives already
  agreeing with two numbers that are each correct.

  **And it cost a real finding for an hour:** the 314 zeros are a genuine
  sub-population, and the explanation dissolved them into a definitional
  artefact. *When a reconciliation makes an anomaly disappear, re-derive the
  reconciliation — the anomaly was the more valuable of the two.*

* **AN ERROR THAT SURVIVES EVERY CHECK YOU OWN IS NOT A LAPSE OF ATTENTION.**
  The `0x200` base error was called "the worst error of the day" by its author
  on the grounds that the rule was written down correctly in their own file
  two sections away. That reading leads to *resolving to be more careful*,
  which is the thing that does not work. **Both available checks were blind to
  it** — a sum cancels a constant, and the format's padding swallows 5.8 ms of
  silence. The correct response is the cheaper check, not the resolution; and
  the rule being present is why it took one look at the right bytes to fix.

* **A LABEL TRAVELS FURTHER THAN THE CAVEAT ATTACHED TO IT.** `fp@(12)` was
  flagged as unread **and called "the previous struct's position" in the same
  sentence.** The caveat stopped at the paragraph; **the noun propagated into
  four scores, into a third party's analysis, and back into this document's
  own objection to that analysis** — which was phrased as *"a read length that
  grows with **position** is incoherent"*, inheriting the very word it was
  disputing. Read at last: it is the caller's own local, an accumulator, and
  what it accumulates is still unknown.

  **The objection was right and aimed one level too shallow.** The
  disassembly was correct; the *name* was the defect. So when a quantity is
  flagged as unread, **do not give it a descriptive name** — name it for what
  it is syntactically (`fp@(12)`, "the accumulator") until it is read. A name
  is a claim that nobody re-reads, and it is the part that gets quoted.

  > **And it was worse than "unverified": it was CATEGORICALLY wrong.**
  > `fp@(12)` is an **object id** — a small integer in a 1…999 namespace. The
  > label said *file position*. Not an unproven value of the right kind, but
  > **a quantity of a different kind entirely**, which is why the arithmetic
  > built on it looked incoherent to everyone who checked and why nobody
  > could say what was wrong with it. *Nobody's disassembly was ever wrong.
  > The noun was.* Four withdrawn scores, an external analysis and this
  > project's objection to that analysis all inherited it.
  >
  > **That is the strongest form this failure can take**, and it argues the
  > rule should be mechanical rather than stylistic: an unread quantity gets
  > a syntactic name, because a descriptive one asserts its *kind* before
  > anyone has established the kind.

  *Third instance today of a frame outliving the thing it framed: a
  retraction inheriting the premise of the claim it withdrew, a vocabulary
  mismatch that made two sessions talk past each other, and now a label
  outrunning its own caveat.*

* **VERIFY THE TEXT, NOT THE EXIT CODE — AND RE-CHECK A "MISSING" RESULT
  BEFORE ACTING ON IT.** A commit here described two edits it did not
  contain: an assertion aborted the first of three edit batches, python
  exited before writing, the other two applied, and the message was accurate
  about intent and wrong about content. Found by grepping for the text the
  message claimed to have added.

  **`eosed` then ran the same check across their own tree and it raised three
  FALSE alarms from three different causes** — a `grep -i "a\|b"` whose BRE
  alternation this host's grep does not take, a phrase broken by a line wrap,
  and a phrase containing markdown emphasis. Each looked exactly like a
  missing edit, and **acting on any of them would have re-applied text that
  was already there**, which produces a passage that says the same thing
  twice.

  So the rule has two halves. Search for **the shortest distinctive fragment
  containing no markup**, and flatten wraps first (`tr '\n' ' '`). Nothing
  handles emphasis inside a phrase, and **nothing at all helps if the pattern
  syntax is wrong for the host's grep — the one failure that is silent rather
  than noisy.**

  **The generalisation is the part worth keeping: a verifier that produces
  false alarms trains its user to discount it, which is worse than not having
  one.** Three misses in a ten-line check is the rate at which anybody stops
  reading the output.

* **A CONSTANT OFFSET IS INVISIBLE TO A SUM.** Two Roland base addresses were
  `0x200` low, and the model built on them validated *perfectly*: 4128
  records, 56 125 blocks, 517 248 000 bytes, ending inside the image — every
  figure reproduced exactly against the corrected base, **because a constant
  base cancels out of a total.** What it does not cancel out of is any single
  offset, and there each sample began 512 bytes early — **256 samples inside
  the previous sample's zero padding**, 5.8 ms of silence, inaudible.

  **The format's own padding hid the error from the only other check
  available.** So: validate a base by landing on ONE object and reading its
  first bytes, never by summing. A total tests the increments; it says
  nothing about where the ruler starts.

* **A FIELD WHOSE DISTRIBUTION HAS THE SHAPE YOUR HYPOTHESIS PREDICTS IS NOT
  EVIDENCE FOR IT.** `+36` in the Roland sample record splits the corpus
  1942 / 2108 with mean sizes of 17.91 and 9.69 blocks — **a 1.85 ratio,
  which is what a 2:1 sample-rate difference produces.** It is not the rate:
  measured, both classes are ≈44.1 kHz. The distribution was exactly as
  predicted and the prediction was wrong. *Recorded because the shape was
  genuinely persuasive and cost nothing to check — which is the whole
  argument for checking it.*

* **A TEST CAN BE CHEAP, WELL-MOTIVATED, AND STRUCTURALLY INCAPABLE OF
  RETURNING THE ANSWER IT WAS DESIGNED TO RETURN.** Offered here as a cheap
  discriminator between the outer and inner pairs: *"whichever doubled
  difference fits inside the instrument file is the sample extent."* It
  scored **0 of 25 for both pairs** — because both pairs are subranges of the
  same file, so "fits in the file" is true of both **by construction**. It
  could not have separated them even in principle.

  **Sibling of the invalid-denominator shape below, and it fails earlier.**
  There the population did not meet the metric's precondition; here the
  *metric* cannot distinguish the hypotheses, whatever the population. Before
  running a discriminator, ask what each outcome would rule out — and if one
  hypothesis has no outcome that would falsify it, the test is decoration.

  **Worth running anyway, on the record:** the query that carried it is what
  produced the single-voice coverage test that *did* settle the labels. **A
  wrong test asked at the right moment is not the same as no question.**

* **When a score is reported as `n/N`, `N` is a claim too — and it is the one
  that never gets audited.** The arithmetic family above was closed at "best
  fit 3 of 18"; **twelve of the eighteen were not fair tests**, being pairs of
  consecutive *located* structs rather than consecutive structs, so their gaps
  span several extents and no adjacency rule could fit them. The validation
  set had been built from whatever the hardware happened to identify, and
  **nobody asked whether its members satisfied the property being tested.**

  **This is invisible to every other check in this list**, because nothing in
  the text is false — `3/18` is exactly what the script returned. Not a stale
  claim, not a label error, not a lost scope: **a metric computed over a
  population that does not meet the metric's precondition.** The only defence
  is to state the inclusion criterion beside the score, where it can be read
  and disagreed with.

* **A TABLE CELL IS READ LIKE A HEADING, AND IT IS WHERE JARGON HIDES.** The
  status table's *blocked by* column read: *"nothing that blocks a
  conversion. Modes 1/3/5 are **material-limited** (n = 3, 4, 2) and
  compression **cannot be settled from these discs**"*. **Its primary reader
  could not parse it**, and he was right not to:

  * *"material-limited"* is a term this document invented and defined
    nowhere;
  * *"n = 3, 4, 2"* gives a count with **no denominator and no unit** — three
    what, out of how many? (Answer: 9 samples of 9889, 0.09 %.)
  * neither phrase says **what it costs a reader who wants to convert
    something**, which is the only question that column exists to answer.

  **Every fact in the cell was true.** It was compressed past the point of
  carrying meaning — and the status table is the part of this document with
  the most readers per word, the one an external session reads *first* and
  reasons from, as one demonstrably did. **The heading rule applies to table
  cells**, and more strongly: a heading at least uses ordinary words.

  **The tell was available and free:** the person the document is for said
  he did not understand it. *A reader reporting confusion is a measurement,
  not a request for elaboration.*

* **Sweep for TITLES, not only for claims.** The first sweep pass searched for
  retracted *statements* and found none of items 11–13, which are all section
  headings and bullet leads written under a belief since retracted — **each
  contradicted by a later section of the same file.** A retracted claim inside
  a paragraph gets marked when someone edits the paragraph. **A retracted
  claim in a heading survives, because nobody edits a heading while fixing the
  text beneath it** — and it is the part with the most readers per word, since
  a heading is what a reader scans before deciding whether to read at all. One
  of these survived three separate correction passes over the same file.

  **And "heading" is too narrow a word for the thing.** A STATUS line is read
  like a heading; so is a bolded first sentence, a summary row, a verdict
  column. **Whatever a reader's eye lands on before the body goes stale the
  same way and for the same reason** — it is written once, scanned often, and
  nobody edits it while fixing the text beneath it. A sibling session found a
  status line reading *"REFUTED. `+248` is probably the sample count"* that
  was **wrong in both halves at once**, having survived two separate
  withdrawals against the paragraph below it.

* **A WITHDRAWAL RETIRES CLAIMS OF THE UNIT IT NAMES, AND LEAVES THE OTHERS
  STANDING IN THE SAME PARAGRAPH.** The `+248` gloss survived two separate
  withdrawals over the very arithmetic that produced it — because both
  withdrawals were about **scores**, and the gloss is a claim about a
  **field**. Nobody re-reads a retracted paragraph looking for a claim of a
  different kind; the retraction marker at the top reads as covering
  everything beneath it. **When you withdraw a result, say which unit you are
  withdrawing** — a score, a field mapping, an offset, a prevalence — and
  re-read the passage for the others.

* **Half-correcting a passage LAUNDERS the rest of it.** Item 16: a section
  heading and its opening sentence were left asserting a retracted claim while
  the *third sentence of the same paragraph* was corrected — three minutes
  after its author committed the rule describing exactly that, against the
  same file, **knowing the rule.** And the partial correction was **more
  dangerous than none**: a section with no retraction marker looks unreviewed,
  while a section with a marker in the middle and a false heading on top looks
  **reviewed and cleared**, and a reader has every reason to trust the title of
  a paragraph that visibly carries a correction.

  **Knowing the pattern does not make you see the instance. Only running the
  sweep does.**

* **Put the ANSWER in a question-form heading.** The cheap prophylactic rather
  than the detection: headings like *"Does EOS's AKAI importer map FX? No"*
  cannot go stale the way *"measuring whether X"* does, because the heading
  carries the thing that would have to change. Two such headings survived
  three sweep passes untouched for exactly this reason.

* **A stale claim is not always stale in every direction.** Item 12 —
  *"no corpus validation at all; every offset comes from the instruction
  stream"* — had been superseded for Ensoniq by 853 wavesamples across five
  discs plus a hardware import, **and was still exactly true for Roland.**
  Striking it wholesale would have destroyed a true claim. **Check what a
  stale claim is ABOUT before retiring it**, and retire it by the half.

* **A measurement can be sound and the sentence reporting it wrong.** Item 9
  was not a bad check: the script correctly counted prose lines over 88
  columns, excluding table rows by design, and returned 1. What was wrong was
  writing *"one line remains over 88 columns"* — **a filtered count reported
  as a total**, when the file has 39. Distinct from everything else in this
  record, where the underlying work was flawed; here only the summary was.
  **Say what you filtered, in the sentence that quotes the number.**

* **A narrow question narrows where the answer-giver looks.** Asking a
  reviewer to check two specific sections found two real errors in opposite
  directions — and neither reviewer looked at the four lines *above* the
  section they had just corrected, where the stale headline sat on the same
  screen as the correction. Ask specifically; then sweep generally.
* **A rediscovery reported as a discovery.** A session read a firmware
  routine in full, found a `+12` term, and reported that "the documented law
  was incomplete" and that every earlier description of the flag "whose effect
  is unknown" could be replaced. **Both false: the term had been in that
  project's own document since its first commit.** What was incomplete was the
  *scoring script*, which is why exactly one instrument mismatched. The check
  that would have caught it is one grep of their own tree. **Check the
  firmware against your own DOCUMENT, not only against your code** — and the
  real finding survives and is smaller: the term was documented but never
  exercised, and is now measured at n = 1. A documented law and a measured one
  are different things.
* **For every number a document cites as evidence, check that the document's
  own stated law can produce it.** This one was paid for twice in an hour: a
  compression of the Roland tuning formula dropped a summand and left the
  section unable to reproduce its own headline `−134` — and running the same
  check against the *source* document found it asserting the opposite split of
  the same total, a hundred lines from where the number appeared. **Both
  documents were wrong, in opposite directions, and each looked authoritative
  alone.** The invariant was already broken upstream; compression only put the
  two halves close enough together to see. Neither review nor re-reading
  settled it — **one read of the actual disc did**, in a minute, and it should
  have come before the assertion rather than after.

---

# Retractions, 2026-09-20/21

Kept because a document that shows only findings misrepresents how they were
got — and because several of these were believed by two sessions at once.

| retracted | replaced by | caught by |
|---|---|---|
| "EOS invents filter key-tracking the source does not specify" (median 0.118 oct/oct) | our own parser reading a cord by SLOT — that 0.118 was EOS's *velocity*→cutoff amount | eosed enumerating the whole importer |
| "EOS never reads AKAI keygroup `0x08`" | it does — a guarded `Key+ → FilFreq` cord | eosed, against their own earlier claim |
| `src[5]×100 + src[6]` is a **Kurzweil object id** | it is **cents**, `coarse × 100 + fine` | k2kremote |
| `I = 9 + zone_counter` (the Roland fill index) | `I = 9 + key`, and now on **both** K2000 arms | a third party's disassembly of the loop bound |
| "the K2000's importers set `lyr[8]` bit 5 unconditionally" | stereo branch only | this project's corpus, then hardware |
| "the four Ensoniq preset variants select CHANNELS" | they are **layer masks** | eosed, 100/100 on hardware |
| "`+221`/`+225` are interleave dead bytes, so every Ensoniq import lands centre — an importer defect" | the **pan law**, 25/25; and `+225` is a `+12` volume-index shift | corpus (322/853 non-zero), then hardware |
| "base 880 is fixed" | a table of ten observed bases; 880 holds 13/25 on one disc, 97/97 on another | eosed's own re-scoring — *the supporting argument came from this project and was silent on universality* |
| "the K2000 writes keymaps shorter than their header declares — a defect" | a reader trusting the wrong field; the header declares a layout, not an extent | this project, correcting k2kremote |
| "mpc2emu never writes per-entry keymap volume" | it does (`0x17`), **and so does the K2000's own importer** | an external document quoting our stale sentence back to us |
| "the hole-fill is the delete-lockup guard" | a **quality** guard, not a safety one — the K2000 ignores a dead sample id | k2kremote, on hardware, with Jan listening |
| gate prevalence 49% / 1% / 0% | **99.6% / 2% / 0%** once filtered to zone slots carrying a sample | k2kremote, against their own measurement |
| "the 796-byte dump and the 820-byte file object are linked by the documented `+24` frame constant" | **withdrawn.** That constant is an OFFSET relation running the other way, and where it can be checked the sizes differ by **22**, not 24. The measurements stand; the account of why does not | k2kremote, withdrawing their own reconciliation after this project refused it on direction |
| "the EPS header table's values are not positions — `O1` needs a different list" | **they are positions**, `× 16`. Validated 230/232 against hardware-derived struct bases; all ten of this document's observed bases are in the table | this project, re-running a lead `eosed` had filed as tested-and-failed **with its method attached** |
| "the Ensoniq base is an open problem — 880 holds 97/97 on one disc, 13/25 on another" | **880 is simply the commonest listed value.** There was never a rule to find | `eosed`, once the list was located |
| **"the K2000 has no Ensoniq program converter" `[C-neg]`** | **it has one, at `0x16368A`** — and everything both sessions documented as "the AKAI arm" all day belongs to it. The reference set was correct; it searched the callee for a dispatch that lives in the caller | k2kremote, against their own `[C-neg]`, prompted by this project's corpus result |
| "three of three — the AKAI import's header fields are LFODEP, MWLDEP and the keygroup count, so the buffer is a program file read from offset 0" | **withdrawn entirely.** The offsets came from reading hex displacements as decimal; the true bytes are identically zero in 5124 real programs | k2kremote, correcting the numbers they had supplied |
| "the Roland loop points are NOT in the 48-byte record" `[C-neg]` | they **are** — 24-bit LE at `+17`/`+21`/`+25`, in samples. The negative was an artefact of reading LE32 at the group base against a byte extent | an external session (KIMIK3), verified here on 9889 records |
| "the rate table is confirmed on all five arms; the 2.00 ratios are the autocorrelation's octave ambiguity" | **two arms confirmed (1 and 4).** The octave explanation was an interpretation presented as a measurement, and the half-lag test refutes it — the periods are real | k2kremote flagging the assumption, then this project's own test |
| "codes 1 and 4 measured, code 3 systematically contradicts the table" | **none of the three.** The table is three octave PAIRS and the disc's two pitch references differ by an octave, so the method maps every code onto its partner. All three results were artefacts of an unstated reference choice | this project, on k2kremote's ROM read of the 22050 arm |
| "the rate table has five arms, `5+` defaults to 44100" | **six** — code 5 is `15000` at `0x169DD4`; the default starts at 6 | k2kremote, from the ROM |
| "`0x113514` selects a **distinct** transfer handler, replacing what the other formats get" | `0x1071FC` is the machine's **generic** sample-transfer routine, installed unconditionally at three sites — the Ensoniq branch picks the *standard* handler | k2kremote, correcting their own reading; it **strengthens** the `[C-neg]` |
| "`+248` is plausibly the sample count" | it is `struct[+4]`, the sample **END** — an absolute position. The one instrument it was read on has a start of 0, so an endpoint looked like a length | this project, against the measured field mapping |
| "outer = sample, inner = loop" (from the containment inequality) | the **labels** were inference; containment says which pair is inside, not which is the sample. Now measured — and the conclusion held | this project querying eosed, then eosed measuring it |
| "`decode(248) − decode(240)` fits 6 of 18, a tight cluster just above 1" | **not a result** — `req` was built on `fp@(12)` being the struct's file offset, which it is not; all four req-based scores withdrawn | eosed, against four of their own results at once |
| "record `+1` is a type code mapping to an E4-side object kind" | a **wavesample index** — `0x78c84` multiplies it by the 288-byte stride | eosed, correcting an external loader trace |
| "`0x79024` may read an object selected by type, not the disc wavesample block" | it reads the disc block; **the document this questioned was right** | eosed, withdrawing their own candidate — twice, the second time with evidence that reaches it |

**Who caught what matters**, because the point of the *suggested* bucket is
that believing things is cheap: the bit-5 correction and the header/body
framing were this project catching k2kremote; `9 + zone_counter` and the
base-880 assumption were k2kremote and eosed catching this project. **Until 2026-09-21,
not one row in this table was caught by the session that made the claim** —
the count is deliberately not restated here, for the reason at item 18. The
rows added that day are the exception, and they say what the rule costs: each
was caught by its own author, in one sitting, by chasing a candidate error
**to its end instead of listing it.** The one
counter-example is absent from this table because it never propagated — the
Ensoniq chain rule was tested to destruction by its own author before anyone
else saw it. See the method note above on a perfect fit from one observation —
including why the *score* it returned no longer stands even though the
instinct does.

---

# Sources

| | |
|---|---|
| `~/git-repos/eosed/docs/AKAI_IMPORT.md` | EOS's AKAI importer, full conversion map |
| `~/git-repos/eosed/docs/ENSONIQ_ROLAND_IMPORT.md` | EOS's Ensoniq and Roland importers |
| `~/git-repos/eosed/docs/GLM_ENSONIQ_LOADER_TRACE.md`, `GLM_ENSONIQ_DISC_FORMAT.md` | external-session traces, annotated |
| `~/git-repos/k2kremote/docs/IMPORT_CONVERSION.md` | the K2000's program/keymap builders |
| `~/git-repos/k2kremote/docs/ROLAND_IMPORT.md` | the K2000's disc sniffer and directory layout |
| `~/git-repos/k2kremote/docs/GLM_KEYMAP_ZONE_LAYOUT.md`, `GLM_ROLAND_KEYMAP_FILL.md` | external-session traces, annotated |
| `~/temp/GLM_FIRMWARE_RE.md` | external analysis, **annotated with a hand-back record**: what was relayed, what held, what was retracted |
| `~/temp/DSV4_FIRMWARE_RE.md` | external analysis, **annotated with a hand-back record**: four findings stand, two are wrong at implementer level, one is right in its disassembly and wrong in an inherited word |
| `~/temp/GPTLUNA_FIRMWARE_RE.md` | external analysis, **annotated**: the EOS accumulator's arena, and a naming caution this document adopted |
| `~/temp/KIMIK3_FIRMWARE_RE.md` | external analysis, **annotated**: refuted this project's Roland `[C-neg]` and closed the loop-point and rate-code questions |
| this repository | `docs/KRZ_FORMAT.md` §3.2, `docs/E4B_FORMAT.md` §4.5, `docs/RESOLUTION_NOTES.md` §AKAICORDGAP / §EOSDIFFGAP / §E4BCORDSLOT / §E4XTKEYPOL / §E4BVELFADEROLE |

**Both external files are annotated in place, never rewritten** — superseded
passages are struck or carry a ⚠ marker pointing at the correction, so a
reader landing in the middle is not handed a withdrawn number with nothing
beside it. Each opens with a hand-back block that should be read first.

**A caution about those sources, learned from them, and named at its author's
request:** `IMPORT_CONVERSION.md` stated "the importers set `lyr[8]` bit 5
unconditionally" as settled in its **write-list table, its constant/derived
table and a section heading** for several hours after its own later sections
had refuted it. The tables are what a reader consults.

k2kremote asked for this to be named rather than generalised, and the reason
is the point: **it happened to the session that ran the measurement which
killed the claim.** Anonymised it reads as a hazard; named it reads as
something that happens to whoever is closest to the work. Where this document
and a source disagree, the disagreement is probably a correction that has not
propagated — check the date, and check the tables against the prose.
