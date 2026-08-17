<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: the AKAI auxiliary files (`.D` drum inputs, `.M3` multi)

## Goal

Decode the two auxiliary file types worth reading. Every real library volume
carries `.T`, `.X`, `.D` and `.M3` files; we name them and round-trip them
byte-identically, but nothing reads their contents, so a multi's program
assignments are lost in conversion. No reference documents any of them.

## What is already known (§AKAIAUX)

Saving a volume on 2026-08-17 produced machine-authored examples of all four.
From those:

- **All four carry a 12-character AKAI-charset name at offset `0x03`** — the
  same convention as the program common, keygroup and sample header blocks.
  Decoded with our existing `akai_to_str`, no new charset work.
- Byte 0 varies and is **not** simply the file type (`.T` and `.M3` both hold
  `0x00`).
- **`DRUM INPUTS.D` is settled structurally: 16 inputs in two banks of eight.**
  The `01 00 00` at `0x00` is not a one-off header — it recurs at `0x58`, which
  is exactly `0x10 + 8x9`. So the file is *marker + 12-char name + 8 records of
  9*, then *marker + 8 records of 9*. Verified on our own capture: both markers
  identical, bank 1's eight records identical, bank 2 spanning 71 bytes.

  The arithmetic closes at `3 + 12 + 1 + 72 + 3 + 72 = 163` against 162 actual,
  and **the missing byte is the last field of the sixteenth record**, which
  ends after 8 bytes rather than 9. Not a header miscount. s3ked confirmed the
  same 162-byte shape over the wire (`RDDATA` -> `DDATA`), so the file and the
  RAM structure agree and this is the format, not a truncated save.

- **The page is readable over SysEx without a save at all** — `RDDATA` (`0Eh`)
  answers with the whole 162-byte structure. That does not remove the need for
  configured values, but it does mean the layout can be checked before or
  without a save cycle.
- `MULTI FILE.M3` is 4096 bytes, almost entirely zero past its header.

## Why those captures cannot be decoded further

**Every field holds the same value in every record, because nothing on the
machine was configured.** A file that varies nowhere cannot distinguish a
per-record field from a file-wide constant, or tell you where one record ends
and the next begins. It is the same no-information shape as a zero-filled
resave probe: it looks like data and answers nothing.

The obvious reading — 16 records of 9 bytes — also fails arithmetic: starting at
`0x5b`, eight records overrun the file by one byte. So even the record count is
not established.

**The fix is to make the file vary in a way we choose.**

---

## Step 1 — configure, on the machine

The parameter names on the DRUM INPUTS page are not known, and s3ked's parameter
table has no drum region at all — the page was never transcribed from the Akai
documents, so there is no table to consult and none will be invented. **Read the
labels off the LCD while setting them.** This procedure therefore speaks in
*positions*. Whatever the page's first
editable parameter is, call it **P1**, the second **P2**.

### Drum inputs

| input | what to set | why |
|---|---|---|
| 1 | **P1 = 36**, and **P2** to any clearly distinct value | two fields changed in one record locates both offsets |
| 2 | **P1 = 38** | |
| 3 | **P1 = 41** | non-uniform gaps, so a stride cannot be confused with a value |
| 4 | **P1 = 47** | |
| 5 | **P1 = 55** | |
| 6 | **P1 = 99** | a large value, in case the field is narrower than a byte |
| 7 … 16 | **leave untouched** | **controls** |

**Also set every one of the page's parameters on input 1**, even to an arbitrary
value. Two of the nine byte positions are `0` in every record today, so if the
configured inputs leave them at zero those two offsets stay exactly as
undecodable as the whole file is now — the same trap one level down. One input
with all nine positions carrying a non-default value gives every offset a single
observation, which is the minimum that makes a field map possible.

**Input 16 is real and safe to configure**, but its final field is the byte the
format truncates. If a distinctive value set there does not appear in the diff,
that is the truncation, not a failed save.

The controls are not optional. With every record changed, "the machine rewrote
the whole file" and "each record holds its own value" look identical — that
ambiguity is exactly what made the first `RSPROBE` unreadable on its own, and
what three untouched slots resolved.

Non-uniform gaps (36, 38, 41, 47, 55, 99) matter for the same reason: an evenly
spaced series can be matched by an offset arithmetic that is not the record
stride at all.

**None of these values may equal the current default**, or the change is
invisible and the record looks untouched. The unconfigured record reads
`60 50 25 2 4 10 10 0 0`, so **avoid 0, 2, 4, 10, 25, 50 and 60** for any
parameter. A draft of this table used 60 and the self-test duly showed that
record as unchanged — which would have read as "the machine ignored input 5".

### Multi

Create a multi with **three parts**, each differing from the others in every way
the page allows — different program, different MIDI channel, different level.
Leave the remaining parts empty as controls. Two parts would be enough to find
the stride; three tells us whether it is constant.

## Step 2 — save to a NEW volume

Not over the originals. The decode is a **diff** against the unconfigured files
already captured at `/home/lentferj/temp/akai_resave_results/VOLUME_005/`, so
both versions must survive.

## Step 3 — write down what was actually set

**This is the decoding key and the run is worthless without it.** Not "I set the
notes" — the exact values, against the exact input numbers, including anything
that would not take the value asked for, and the *names* of P1 and P2 as the
page shows them.

If a parameter refuses a value or snaps to another, that is a finding in itself
(see the accepted / preserved / effective distinction in §AKAIRESAVE) and worth
noting rather than working around.

## Step 4 — decode

```bash
python3 tests/re_banks/akai_aux_diff.py \
    "/home/lentferj/temp/akai_resave_results/VOLUME_005/DRUM INPUTS.D" \
    "/media/lentferj/AKAI/HD4.img#<NEWVOL>/DRUM INPUTS.D"
```

The tool reports every changed byte with its offset and its value before and
after, then **infers the record stride from the spacing of the changes** and
re-reports each change as `record N, +offset`. It does not take a stride as an
argument on purpose: an assumed stride misattributes every field to the wrong
record silently, which is precisely what the failed 16×9 reading would have
done. The stride is printed as a candidate with its support, not as a
conclusion.

Feed it the values from step 3 and the field map falls out: a changed byte whose
new value equals what you typed names that field; one that does not is scaled or
packed, and is worth more than the others.

## What this closes

`.M3` is the one with real conversion value: it is the AKAI equivalent of a
multi/performance, and a multi's program assignments are currently dropped.
`.D` is smaller but is the easier file to decode first, and decoding it
establishes whether these types share a record convention.

`.T` (take list) and `.X` (effects) are not covered here. `.X` is 7312 bytes and
would need its own session; `.T` is 160 bytes and may well be trivial once `.D`
is understood.
