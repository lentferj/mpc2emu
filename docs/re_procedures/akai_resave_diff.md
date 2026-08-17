<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Hardware RE: the S3000XL resave diff

## Goal

Settle the regions both format references mark `??` — program common
`0x48`–`0xbf`, keygroup `0x96`–`0xbf`, sample header `0x8d`–`0xbd`. Our writer
zero-fills all of them and nothing tells us whether the machine ignores those
bytes, writes its own values there, or reads ours back.

This is the check `TODO.md` names as the gate on pushing `akai-s3000xl`.

**Cross-verification cannot answer it.** We already agree with `akaiutil`
byte-for-byte, but `akaiutil` is an independent *interpretation* of the same
undocumented format — on the parts neither of us knows, it agrees with us for
the same reason we agree with ourselves. Only the sampler is authoritative.

## What is already settled — do not re-derive it here

- **Unused velocity zones.** Real discs (2026-08-07) showed the sampler marks a
  disabled zone with an **inverted velocity range** (`lo` 1, `hi` 0) and leaves
  the old name in place. The writer already does this. `TODO.md:61` still says
  this diff will "settle the unused-zone encoding and the `??` regions
  together"; that is stale — only the `??` half is open.
- **Disk images mount and load**, programs load and their zone names read back
  (2026-08-16).
- **Velocity→filter** through keygroup byte 151, +25.3 dB at v120.
- **The two-name defect** and its fix.

## Why there are three programs

A resave of a zero-filled file cannot tell "the machine preserved our zeros"
from "the machine wrote its own zeros" from "the machine never touched these
bytes". All three produce an identical file. That is the experiment shape this
project keeps getting caught by: it looks like a clean confirmation and carries
no information.

| file | `??` regions | purpose |
|---|---|---|
| `RSCTRL.P3` | zero-filled, as we write today | baseline. If this does not survive a load-and-resave, the problem is not the unknown regions and the rest is moot |
| `RSPROBE.P3` | each byte = **its own offset** | makes the resave self-describing |
| `RSPROB2.P3` | each byte = **offset ^ 0x55** | makes a *moved* byte decidable |

Why the second probe: a returned value that lands inside the region's own
numeric range (`0x48`–`0xbf` is half the byte space) is ambiguous from one
probe — it could be one of our bytes that moved, or a value the machine simply
chose. Under two patterns they separate cleanly: **a byte that really moved
comes back different; a machine-chosen constant comes back the same.** Building
both now costs nothing and saves a second card crossing, which is the expensive
step.

All three carry four keygroups using **1, 2, 3 and 4** velocity zones, so a
difference that depends on zone count is visible rather than averaged away.

---

## Step 1 — build the disc (offline, no hardware)

```bash
cd /home/lentferj/git-repos/mpc2emu
python3 tests/re_banks/gen_akai_resave_probe.py --hda /home/lentferj/temp/HD4.img --size-mb 32
```

Writes volume `RESAVE` holding `RSTONE.S3`, `RSCTRL.P3`, `RSPROBE.P3`,
`RSPROB2.P3`.

**It must be a HARD DISK image, not a CD.** The machine has to write its
resaves somewhere, and a CD-ROM is read-only — every one of `CD0`–`CD3` on the
card is useless for this.

**Size it well above the data.** 32 MB against ~24 KB of files leaves the
partition (`part_blocks` 4096 × 8192 B) almost entirely free, which is the room
the sampler needs to create its own save volume. A data-sized image would load
fine and then have nowhere to save to — the failure would only appear at the
machine, with the card already in it.

**Keep the local copy.** `/home/lentferj/temp/HD4.img` is the pristine
reference the diff compares against; the card's copy is the one the machine
will modify.

## Step 2 — put it on the card

```bash
cp /home/lentferj/temp/HD4.img /media/lentferj/AKAI/HD4.img && sync
md5sum /home/lentferj/temp/HD4.img /media/lentferj/AKAI/HD4.img   # must match
```

**Pick a free SCSI ID.** ZuluSCSI maps by filename: `CD0`–`CD3` are already
CD-ROMs at IDs 0–3 and `HD5.img` is a disk at ID 5, so **ID 4 is free**. Check
`zululog.txt` after boot to confirm it came up:

```
-- Opening /HD4.img for id:4 lun:0
```

If the drive does not appear at all, check the **sampler's own** SCSI ID — an
S3000XL is commonly ID 6, but if it is set to 4 it will collide with this
image and neither will work.

## What can and cannot be driven remotely

Established by the s3ked project 2026-08-17, by enumerating the opcode surface
and by measurement, not from the manual alone.

| step | remote? |
|---|---|
| load a volume | **yes** — a register in the misc bank acts as a trigger when written (s3ked §71, §93), verified end to end |
| navigate to the SAVE page | yes — `byte[91]=9`, machine stays responsive with HARDDISK selected (§84) |
| **execute a save** | **no** |
| read a program back from RAM | yes — `RPDATA`, read-only, no risk |

**There is no save operation in the protocol.** The complete set of disk-related
opcodes this family defines is `RVOLLIST`/`VOLLIST` and `RHDDIR`/`HDDIR` — list
volumes, read a directory. Nothing writes. The load is not an exception to that
rule but a **side door**: the LOAD page happens to have a trigger register, and
nothing about that generalises. A remote save would need an equivalent trigger
on the SAVE page plus somewhere to carry a target volume *name*, and the
register model has no such thing. s3ked's §105 already swept `byte[6]` for a
CLR trigger — 48 unknown values, all inert — and CLR is a softkey beside GO on
a page we can already reach, so a save is the bigger ask with the worse prior.

**So step 4 requires a person at the panel. That is settled, not pending.**

### Do not trigger the stamped loads remotely

A load is exactly the operation that has wedged this machine: s3ked §71 wrote
the load-type register, the display showed "Loading Sample…" in bursts, then
sat at BUSY indefinitely until a power cycle — **on an ordinary volume, not a
malformed one.** Dozens of clean loads since, so it is not the common case, but
the precedent is a *load* rather than a register write, which is the opposite
of the intuition.

`RSPROBE` and `RSPROB2` are deliberately malformed in a region that might be
load-bearing. **Load them by hand, watching.** Load `RSCTRL` and confirm it
round-trips before either stamped file goes near the machine.

## Step 3b — the RAM readback (optional, read-only, no risk)

Once a program is resident, `RPDATA` returns it from memory. Measured by s3ked
2026-08-17: the program, keygroup and sample blocks are each **193 bytes,
`0x00`–`0xC0`** — so every `??` region we stamp (program `0x48`–`0xbf`,
keygroup `0x96`–`0xbf`, sample `0x8d`–`0xbd`) is **entirely inside** what the
machine hands back. The route carries the bytes.

Request shape, worth copying exactly — the item number is a **14-bit pair**,
not one byte:

```
f0 47 00 06 48 00 f7        -> no reply
f0 47 00 06 48 00 00 f7     -> PDATA, 386 payload bytes = 193 nibbled
```

A wrong request shape and an unsupported operation are indistinguishable over
the wire: both are silence. Two of s3ked's first three attempts looked exactly
like "the machine does not answer `RPDATA`".

### This answers a DIFFERENT question, and the write-up must keep them apart

`RPDATA` tells you what the machine's **in-memory** structure preserves. It
does not tell you what the **disk** format preserves. Those are already known
to disagree somewhere: s3ked §111 found the loader resolves sample references
by *directory* name while `RSLIST` reports *header* names — which is the same
two-name split that made every sharp in a volume silent here.

So "RAM kept my byte" does not entail "the disk format kept my byte", and a
clean `RPDATA` result must not be written up as a resave finding. Worth stating
plainly because **a clean result is exactly when the distinction stops feeling
important.**

## Step 3 — load, on the machine

> The front-panel key sequences are Jan's — they are deliberately not spelled
> out here rather than guessed at.

1. **Force a directory re-read.** `select_drive`, not `select_volume`: a card
   swapped while the sampler is powered leaves the *previous* card's directory
   cached, and the machine will then confidently describe a disc that is not
   in the drive. This has already cost one round of wrong conclusions.
2. Load **`RSCTRL` first.** If it does not load, stop — nothing below is
   meaningful.
3. Then `RSPROBE`, then `RSPROB2`.

**`RSPROBE` or `RSPROB2` may refuse to load or misbehave. That is a result,
not a failure** — it means at least one `??` byte is load-bearing enough to
reject a program, which is worth knowing before we ever write anything there.
Note *which* file and what the machine did. `RSCTRL` is a separate file so this
cannot take the baseline down with it.

## Step 4 — save each one back, to a **different volume**

Save all three programs, and `RSTONE.S3` as well (the sample header has its own
`??` region at `0x8d`–`0xbd`).

**Save to a new volume, not over the originals.** If the machine overwrites the
files it loaded, the diff has nothing to compare against and the whole crossing
is wasted.

## Step 5 — bring the card back and diff

```bash
cd /home/lentferj/git-repos/mpc2emu
# ours = the pristine local reference; theirs = the machine's save volume
python3 tests/re_banks/akai_resave_diff.py \
    /home/lentferj/temp/HD4.img#RSCTRL.P3 \
    /media/lentferj/AKAI/HD4.img#<SAVEVOL>/RSCTRL.P3
```

Repeat for `RSPROBE.P3` and `RSPROB2.P3`. **Qualify the machine's side with its
volume name** (`#VOLUME/FILE`): after the resave the card holds each filename
twice, once in `RESAVE` and once in the machine's new volume, and without the
qualifier the tool refuses rather than guessing which one you meant.

Either side accepts `IMAGE#FILENAME` and pulls the **raw** file out of the image — deliberately not through
`parse_akai_image`, because that returns our interpretation of the bytes, and
unknown bytes are exactly what an interpretation drops.

---

## Reading the result

The tool separates two things that mean opposite things:

- **A difference in a documented field** — we are writing something the machine
  disagrees with. The more serious of the two, and a bug in our writer.
- **A difference in a `??` region** — the point of the exercise.

Per stamped byte it reports `kept`, `cleared`, `rewrote -> 0xNN`, or
`AMBIGUOUS`. Resolve every `AMBIGUOUS` by comparing the same offset across
`RSPROBE` and `RSPROB2`:

| RSPROBE | RSPROB2 | meaning |
|---|---|---|
| `0xNN` | **same** `0xNN` | the machine writes a constant there |
| `0xNN` | **different** | one of our bytes moved — a field boundary is not where we think it is |

## What each outcome changes

| finding | consequence |
|---|---|
| every `??` byte comes back `kept` | the machine round-trips them untouched. Zero-filling stays correct, and we now know it is *safe*, not merely *not-yet-harmful* |
| some come back `cleared` or `rewrote` | the machine has its own convention there. Write what it writes — the values are in the diff output |
| any come back `MOVED` | a documented field boundary is wrong. Fix the map in `docs/AKAI_S3000_FORMAT.md` and the parser before anything else |
| a probe refuses to load | at least one `??` byte is load-bearing. Record which, and keep zero-filling |
| a **documented** field differs | a writer bug, independent of this exercise. Fix first |

Record the outcome in `docs/RESOLUTION_NOTES.md` §AKAI_S3000_FORMAT and close
the `TODO.md` gate row.

## Batch the rest of the crossing

Per the bench-economics rule, plan around the SD swap rather than one question
at a time. Also unlocked by this same crossing:

- **stereo** — whether the machine auto-pairs `-L`/`-R` names, and what happens
  to the 12-character name budget when two characters go to the suffix
- **resident P/K/S pool** — load two volumes with lopsided program/keygroup/
  sample counts and watch which way the `free P/K/S` number moves
- **`K_FREQ` 12 vs 22** — the field accepted 22 where the spec says 0–12;
  the strong test is whether the corner actually shifts differently, not
  whether the write is accepted

Filter envelope 2 is **not** on this list: it needs the additional filter board,
ordered 2026-08-17.
