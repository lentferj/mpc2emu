<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors

Part of mpc2emu — https://github.com/lentferj/mpc2emu
Contributions: Jan Lentfer, with AI assistance (see README).
-->

# Bringing the E4XT to K2000/S3000XL parity — plan, tools, and staged banks

**Written 2026-08-17 with the E4XT powered down.** Everything here is offline
preparation. The deliverable is that when the machine next powers up, the
measurement runs with as little human-in-the-loop as possible: banks already
built, procedures already written, analysis scripts already able to consume the
output.

---

## 0. Why this plan looks the way it does

Three days of work on the K2000R and S3000XL produced four lessons that cost
real time to learn. They shape every phase below, so they come first.

### 0.1 The display is a measuring instrument

The single highest-value artefact of the last 72 hours was **40 rows of "what
does the machine say is in this slot"**, read off the K2000's LCD by k2kremote.
No audio, no signal analysis. Joined against our stored bytes it overturned a
filter table we believed correct at 581 of 581, finding **one wrong row and two
missing ones** — we had been converting allpass filters as distorted lowpasses
and dropping a highpass entirely.

**eosed has just gained an LCD mirror.** That makes the same technique available
on EOS for the first time, and it is the highest-priority item in this plan. It
is also the cheapest: it needs the machine powered and nothing else — no audio
interface, no MIDI timing, no listening.

### 0.2 A value test is not evidence

Repeatedly fatal: a byte that *looks* like a filter code, a range that *looks*
plausible, a count that *looks* clean. The invented-bandpass bug shipped twice
because "the value is in the right range" was treated as identification. What
worked was joining stored bytes to what the machine *states*, and refusing to
model anything else.

### 0.3 Cheap offline checks before expensive ones

Twice in one evening an hour of instrument time was saved by finding the answer
already written down — the K2000's algorithm chapter, and a corpus of files.
The E4B sample-rate pitch bug (§E4BRATE) was root-caused **entirely from 681
corpus files**, no hardware, after being blocked for months on "needs an E4XT".
The blocker was a collapsed variable: it constrained *access to a machine* when
the question was *what value the field holds*.

**Before any phase below, ask: is this answerable from the 461-file local E4B
corpus, or from the EOS 4.0 manual?** Several items in Phase 1 may fall to that.

### 0.4 The errors that survive make the data look BETTER behaved

Both undetected errors of the last 72 hours produced *internally consistent*
output: a pattern holding 74 of 74 that was one writer's habit, and a table at
581/581 that was measuring only its own self-consistency. Neither looked wrong.

**Consequence for this plan: every measurement below names, in advance, what an
implausible result would look like and what its negative control is.** A check
that cannot fail is not a check.

---

## 1. State of the E4XT path

### 1.1 Settled and hardware-confirmed — do not re-measure

| item | evidence |
|---|---|
| `vpar[58]` filter type, full table | HW-RE'd 2026-06-08, `B.005-FILTERTYPES.E4B` |
| Cutoff, resonance, zone gain, pan, stereo | §E4BFILTCAL, 2026-07-31 |
| Amp-envelope sustain LEVEL is a dB law | §E4BLEVEL, HW-confirmed 2026-07-28 |
| Sample-rate pitch field `[58-59]` | §E4BRATE — `768·log2(rate/44100)`, verified against the E4XT's own SrCnv output at 6 rates, ±1 unit |
| `[18-21]` is NOT pitch | verified: varies across saves of the same sample |
| FORM size convention + trailing `EMSt` | `docs/E4B_FORMAT.md` (form_size = filesize − 12) |
| EMU3 `brem`=0 ISO bug | fixed, on main |
| Auto-loop, start-trim | merged, HW-confirmed |
| Name fields carry bytes >0x7E | §NAMEBYTE, latin-1 both ways |

### 1.2 Open — the actual work

| # | item | kind | blocked on |
|---|---|---|---|
| **A** | **§ENVSPAN** — is the envelope byte a RATE or a DURATION? | untested assumption **in shipped code** | audio timing, 2 presets |
| **B** | Byte↔display join for EOS parameters | never attempted | LCD mirror |
| ~~**C**~~ | ~~"voice count = 1" — zone-table trailer~~ | **CLOSED 2026-08-17 from the corpus — see §1.4** | — |
| **D** | E4B stereo | **already on `main`** — `stereoE2E` no longer exists (Jan, 2026-08-17). Corpus-RE'd over 473 files / 20,383 samples, implemented, **never hardware-confirmed** | listen |
| **E** | Single-cycle oscillators | implemented, unheard | listen |
| **F** | `filter_env_amount` −0.114 shift | on main, unheard | listen |
| **G** | `VF NEW` / `VF OLD` | built, unheard | listen |

**A is the only one that is a suspected defect in shipped output.** B is the
one with the largest unknown upside. C–G are confirmations of work already
done, and they are cheap to batch into a single session.

### 1.4 Item C closed offline, and the check that closed it

**eosed asked the right question and it came back clean.** Their warning: their
own `preset_num_voices` correction passed *two* independent dump-file
cross-checks and shipped wrong, because both were **preset 0 on two occasions**
— two data points that were one point wearing two hats. It survived until a
270-preset sweep found presets where the correct count was 0.

So the question to ask our trailer fix is **not "how many files" but "how many
DISTINCT voice counts"**. Our comment claimed four examples, and three of those
were presets of one bank.

Checked against every `.E4B` on this disk — walking each preset's voices via
`vpar[2:4]` and measuring the bytes left after the last one:

```
2,293 presets walked cleanly (101 refused mid-walk)
leftover after the last voice:  2 bytes -> 2,290
                               22 bytes ->     1
                               44 bytes ->     1
                              154 bytes ->     1
DISTINCT voice counts covered: 60   (1 .. 423 voices)
```

**The rule holds on 2,290 of 2,293, across 60 distinct voice counts**, not four
examples of one shape. The trap eosed described does not apply: we did not fit a
constant to one point. Three outliers at 0.13 % are worth a look someday and are
not evidence against the rule.

Also worth recording from their reply: the file side and the wire side disagree
in general. Their §11/§12 unreliability is about the **device's count commands
over SysEx**; file-side counts were honest on every preset they checked. Ours is
a file-side question, which is why it was answerable from files at all.

**Two sentinels to avoid modelling as data** if we ever do read counts over the
wire: `0x3FFF` is the spec's multisample marker and `0x3FFE` is an undocumented
but consistent "this voice index does not exist". A voice walk that reads either
as a sample id produces plausible garbage.

### 1.3 Closed by eosed before this plan was written — do not schedule

- **The rate/pitch attribution is settled both directions, within half a cent:**
  `[58-59]` is authoritative for playback pitch, `[54-57]` drives the *displayed*
  rate and duration. That closes the attribution half of §E4BRATE2. It does
  **not** close the SrCnv calibration-points question, which is about generating
  rather than reading.
- **`MASTER_AUDITION_KEY` (id 271) is confirmed absent** — never answered.
- **Item C was NOT a rediscovery** — checked and closed, see §1.4. eosed's
  §11/§12 unreliability is a *wire-side* finding about the device's count
  commands; ours was a *file-side* question, and file-side counts were honest
  on every preset they checked. Different layers, and the file layer answered.
- **Single-cycle output (E) can be heard whenever the machine is next up** —
  their audio chain is calibrated against `CD3-PITCHCAL` (−0.8/−0.8/−0.6 cents
  at 440/220/110 Hz) and the harness is written. Cheap add to any powered
  session.

---

## 2. Phase 1 — the display join (highest value, no audio)

**Port of the technique that overturned our K2000 filter table.**

### 2.1 The join runs BACKWARDS on EOS — this is not the K2000 method

**Answered by eosed 2026-08-17, and it invalidates the obvious design.** An
editor-protocol parameter write **does not reach the display**. Spec-stated and
demonstrated: setting `E4_PRESET_VOLUME` to −18 dB reads back −18 dB while
neither the audio nor the panel moves. The edit lands in a buffer the front
panel does not read until the preset is touched from the panel.

So **"write a byte over SysEx, read the label off the LCD" does not work here.**
Any plan built on it would have produced a clean, self-consistent, meaningless
table — §0.4's failure shape exactly.

**The direction that works is the better one.** eosed can drive the front panel
remotely *and* read it. So:

```
press panel keys to change the parameter   (remote)
screenshot the display -> name, value, units   (remote)
read the byte back over SysEx              (remote)
```

Both halves automatable, **no human at the rack**. This is the k2kremote
technique with the causality reversed, and it is stronger: the panel is the
machine's own authority on what a value means, and we read the byte *after* the
machine has committed to a rendering.

The display also carries things the bytes do not: derived values
(`2.00secs, left, 27500Hz` — the machine doing the division), whole-record info
popups, soft-key **greyed state** (semantic information available nowhere in
SysEx), and selection state with PREV/NEXT neighbours.

### 2.2 The target list already exists — `HW_CHECKLIST.md` section B

eosed's repo carries **45 unchecked items**, and **section B, "Value
descriptions — panel comparison", is 13 items and is precisely this join**. It
was written for an instrument that did not exist yet. Priority, their ranking
and mine agreeing:

1. **B11 `E4_VOICE_FTYPE` names** — "id == list position", 21 filter types,
   assumed. **This is our 581/581 filter table in EOS clothing**: same shape,
   same risk, never checked against the machine's own names. Highest priority.
2. **B1/B2 key fields** — pins the −2 octave offset (60 should display `C3`).
   Tonight's zone/root confusion on the K2000 is a live argument for doing this
   early and cheaply.
3. **B3 `E4_LINK_INTERNAL_EXTERNAL`** — flagged in their own file as
   "**INFERRED**, the risky one"; off-by-one direction assumed.
4. **B12** ids 87–92, whose overlay meaning changes with FTYPE.
5. **B5/B6** `MASTER_SCSI_TERM`, `MASTER_COMBINE_LR` — spec says INVERTED
   (0 = on), kept deliberately, never confirmed.
6. **B13** LFO rate display — transcribed from our calibration, never
   re-checked on this unit.

**Already closed by eosed, do not schedule:** A2 `MASTER_AUDITION_KEY` (id 271)
is **confirmed absent** — the E4XT never answers a read of it.

### 2.2b The B11 route is documented, and one trap sits in the joiner

**eosed read the chapter before the next hardware question — k2kremote's advice,
taken literally, and it paid three times offline.**

**The route is in the EOS 4.0 manual, ch.8 "Filter Parameters":** Preset Edit →
voice selection → **F3 (Amp/Filt)** → *Previous/Next Page* to the Filter screen.
Their probe said `PRESET_EDIT` and stopped, which would have read a crop of
whatever page that landed on, 98 times — a full-length table of the wrong field.
The abort-if-display-does-not-change guard would *probably* have caught it, but
only probably: the byte varies per preset, so a field that happens to change
would have sailed through. The manual does not give the Filter screen's page
index ("page until you find it"), so a `--survey` pass enumerates pages once and
the index is fixed for the run.

**THE ABBREVIATION TRAP — this one would have made a correct table look wrong.**
The LCD is 240 px of fixed-width font and abbreviates long names. The manual's
prose and its own illustrations disagree, and the illustrations disagree with
each other:

```
prose (p.344)         "2EQ Morph + Expression"
illustration (p.345)  "2EQ Morph + Exp"
illustration (p.346)  "2EQ Morph +Exp"
```

An exact-equality joiner flags every long name as a mismatch, and each is an
artefact of prose-versus-screen, not evidence about the id mapping. **The danger
is not the false alarm — it is someone "correcting" a correct table to match, or
discarding a good run.** `e4xt_display_join.py` therefore compares on a
normalised prefix, records both forms, and reports abbreviation in its own
bucket as EXPECTED.

It also makes the deliverable better than pass/fail: the run produces **the
machine's own displayed strings**, which neither the manual nor our table has
for any of the 21.

**What a mismatch would MEAN is now narrow.** eosed diffed `eos/params.py`'s
`FILTER_TYPE_NAMES` against the manual — all 21, same order, exact, no drift. So
the transcription half is closed and **the only open half is `id == list
position`**, which is exactly what the 98-preset bank tests. A wrong name at some
byte indicts the position assumption, not the names.

**One item for the walk's safety model, not for B:** there is a documented
PC-keyboard mapping (`EOS Keyboard shortcuts.pdf`) in which **Load Bank is CTRL-L
and Save Bank CTRL-S** — so Load and Save are reachable as *global accelerators*,
not only as soft keys on the disk pages. Our whitelist is over panel key codes,
so it is unaffected; but anything that ever drives the machine through the ASCII
keyboard surface has a different blast radius and needs its own whitelist.

### 2.3 The bank

`gen_e4xt_display_anchors.py` — **one bank, many presets**. For B11: **one
preset per filter type, named for the type index**, so a single INC walk with a
screenshot per step produces the whole id→name table in one pass, no audio.

Three properties eosed found made a bank cheap, all adopted:

- **Self-documenting preset names** (`A_R27500_OFF0` style) — the variant's
  metadata in its own name, so the LCD identifies what is loaded at a glance and
  a stale reading is obvious.
- **Distinct key zones per variant** — their pair zoned `C3-C3` and `C4-C4`,
  making it **self-verifying without the display at all**: the control answers
  only at one key, the test only at the other, so sound at both proves the
  preset changed. No software gate can match that, because it cannot be fooled
  by a stale screen read.
- **A known-good control in the same bank, measured in the same pass.**

**Correction to Jan's standing "send a program change" model:** on EOS,
**Program Change is PAGE-DEPENDENT** — honoured on the main preset page,
silently ignored on Preset Manage and Sample Manage. It cost eosed two
measurements today that came back identical because they were the same preset
twice. The robust substitute needs no human either: **step presets with the
panel's own INC key and verify on the LCD**, so selection and proof-of-selection
come from the same place.

### 2.4 Before any session: check for a second MIDI client

**eosed lost a sweep to this today and it is the §0.4 shape again.** ALSA
delivers a port's traffic to *every* subscriber, so Jan's own eosed TUI polling
the panel from a second process put foreign frames into their input. A frame
broke one preset's voice walk, a best-effort `except` swallowed it, and the
preset was recorded as **having no voices**. The sweep completed and reported
sensible numbers.

It surfaced only because a counter added that afternoon made the count visible
and it was one higher than it should have been. **Check for an existing MIDI
client before any measurement session** — this is CLAUDE.md's one-session rule,
and the cost of breaking it is a plausible wrong answer rather than an error.

(eosed also retracted, unprompted, an earlier report that the E4XT "pushes
unsolicited display frames" — same root cause, and §33b's "the device never
pushes" stands.)

### 2.3 Negative controls, stated in advance

- **At least three presets left at defaults**, untouched. If those read back
  changed, the join is misaligned and everything else in the run is void.
- **One preset with a deliberately out-of-range byte.** If the machine clamps,
  we learn the range; if it displays the raw value, we learn there is no guard.
  Either is a finding; a blank display means the read is wrong.
- **Implausible result to watch for:** every parameter reading back exactly what
  we wrote. That is what a round-trip through our own assumptions looks like,
  and it is what "581/581" felt like from the inside.

---

## 2b. Phase 1b — the exhaustive screen walk (Jan's, and the highest-yield item here)

**Different in kind from §2.** Section B verifies parameters we already model.
This **discovers parameters we do not model at all** — and Jan's premise is the
right one: *the EOS menus are far deeper than either the converter or the
documentation covers.* Neither our `E4B_FORMAT.md` nor the EOS manual's
parameter lists are a complete inventory of what the machine exposes.

It needs no bank, no audio, and no human. It is a graph traversal.

### 2b.1 What it produces

1. **A page map** — every reachable page, its title, its parameters, and for
   each the rendered value **with units** and the soft-key labels including
   **greyed state** (semantic information available nowhere in SysEx).
2. **A coverage diff** — the deliverable that matters. *Every EOS parameter the
   machine displays, against every parameter our writer emits.* Three buckets:
   we write it and the machine shows it (verify); the machine has it and we
   never write it (**a conversion feature gap**); we write something the walk
   never surfaces (**suspect — what is it doing?**).

Bucket two is what Jan is after. Bucket three is where an invented parameter
would be sitting, and nothing else we have planned would find it.

### 2b.2 SAFETY — a whitelist, because the unknown case is unrecoverable

**eosed's finding, 2026-08-17, and the plan does not ship without it.** An
exhaustive walk that presses every soft key **will eventually press Load, Save,
and the Utils menus — and the Utils menus contain Erase RAM Bank, Erase Presets
and Erase Samples.** Those are one-shot destroyers.

**Some paths have no confirmation dialog at all.** eosed pressed Load on a bank
with empty RAM and it fired immediately, because there was nothing to destroy. A
walk cannot know in advance which press is inert.

**"Navigation only, never change a value" is necessary but NOT sufficient.** It
addresses INC/DEC and the data wheel. It says nothing about soft keys, and on
this machine **the soft keys are where the destruction lives** — with
page-dependent meanings: F4 is Load on the disk pages and Place on Sample
Manage; F5 is Save on one page and Audition on another. A blacklist keyed on
key number is therefore meaningless.

**The rule is a whitelist — but NOT "read the label and match it".**

The first version of this rule, which both eosed and I wrote down and I called
adopted, said: *follow a soft key only when its label has been READ off the
screen and matched against an allowed set.* **eosed found while building it that
this is not implementable: there is no OCR anywhere in this rig, so the script
can read no label at all.** Taken literally the rule mandates refusing every soft
key — which is the correct behaviour, and not what the sentence appeared to
license. The danger was a loose implementation: *"well, it looks like a safe
label"*, three pages in.

**What replaces it is template matching, not reading:**

- Each soft-key cell is cropped and compared **bitmap-to-bitmap** against a
  library of human-labelled references.
- `ALLOW` may be followed. **`DENY` and `UNKNOWN` are both refused.**
- **The library ships EMPTY.** A first run therefore follows no soft keys at all
  and only harvests cells for labelling (`--learn`). Deny-by-default is the
  *initial state*, not a policy someone has to remember to enforce.
- Labelling is explicit, out-of-band and **human** — which is where a judgement
  like "is Utils safe" belongs.
- The word blacklist (Load/Save/Erase/Delete/New/Place/Format) survives, but it
  now filters **the labels a human typed**, not anything the machine said. It is
  a backstop against a mislabelled library entry, not the primary defence.

- Movement keys are unconditional — they change what is *displayed*, not what is
  *stored*. INC/DEC, data dial and numeric are never sent at all.

That inverts the default from *press unless known dangerous* to **press only if
known safe**, which is the only defensible default when the failure is
unrecoverable. The empty library is what makes it true on day one rather than
after someone configures it correctly.

- **Stay off the DISK pages entirely on the first pass.** That subtree holds
  every destructive operation, and eosed has already mapped most of it by hand —
  take their routes rather than have a robot rediscover them next to an Erase key.
- **Never change a value**: cursor movement and page entry/exit only. A walk that
  edits is a walk whose later readings are of its own damage.
- **Run on a scratch preset in a scratch bank**, so even a mistake above costs
  nothing. *Open question 3 for Jan.*

### 2b.3 Traversal rules

- **Key page identity on (left-edge label, soft-key row, cursor position) — NOT
  the title.** eosed's frames show the disk-family pages carrying a *vertical
  label down the left edge* (`DISK`, `BANK`, `SMPL`, `FLDR`) while sharing an
  identical soft-key row and icon grid. **Keying on the title alone collapses
  four distinct pages into one and terminates the walk early** — which is exactly
  the "too few pages" failure below, arriving by a route we would not have
  suspected. The soft-key row is the better fingerprint because it changes with
  context in ways the title does not.
- **Treat greyed and active soft keys as the same key.** The row changes with
  *media* state — Save greys out on read-only media — so a walk that
  distinguishes them revisits every page once per drive type.
- **Probe for an open modal dialog before EVERY step, not just at the start.**
  eosed lost a run to this: an Info popup left open made each subsequent
  open/dismiss do the opposite of what was intended, the modal ate the cursor
  keys, and the result was N identical frames of the page underneath. Their
  detector looks for the popup's top border as a long unbroken black run —
  **sampling one row inside the border finds white interior and reports "closed"
  for an open dialog.**
- **Screenshot every state**, named by its path, so any row can be audited later
  without re-walking.
- **Depth cap plus an explicit unvisited-frontier report.** A walk that claims
  completeness is claiming a negative; the honest output is "these pages were
  reached, these exits were seen and not followed".
- **Check for a second MIDI client before starting.** Repeated because an
  unattended walk is the worst possible place for it.

### 2b.4 The controls, since a walk is exactly the shape that fails silently

- **Re-visit a known page at the END** and compare bitmaps with its first visit.
  Same check as the anchor bank's two controls, same reason: if the walk
  desynchronised, everything after the divergence is mislabelled and looks fine.
- **An implausibility to watch for: too few pages.** If the walk reports a tidy
  number and terminates quickly, the likeliest cause is that navigation stopped
  working and the crop kept reading one static frame — 98 identical rows that
  each look like data. eosed's sweep-corruption of 2026-08-17 was this shape.
- **Cross-check a handful of found pages against the EOS 4.0 manual** (422 pp,
  `pdftotext`-readable, path in memory). Pages the manual documents and the walk
  missed are the measure of coverage; pages the walk found and the manual does
  not document are the find.

### 2b.4a THE WALK PRESSED LOAD — incident, 2026-08-18

**It reached the DISK subtree the design excludes, opened the "Destroys current
RAM bank" dialog, and confirmed a load.** RAM went from empty to one preset plus
~1.59 MB of samples. No Erase. CD slots are read-only images; **whether anything
reached HD0 is UNKNOWN and stays unknown**, because no backup of that card
existed to compare against.

**Root cause: the queue stored a key NAME but not the page it was validated on.**
A soft key checked against the library on one page was pressed later from
wherever the walk had since wandered — where the same key number means something
else. eosed had written the warning that a key-number blacklist is meaningless
because soft-key meaning is page-dependent, then built a whitelist that presses
key numbers. Compounding it: `PAGE_EXIT` does **not** dismiss that dialog
(`Cancel` on F1 does), so the walk was in the key-swallowing state and a later
queued press landed on Load.

**My share:** I took a full byte backup of the AKAI card before letting another
session near it, and wrote that this was "the reason I took it rather than
asking you to be careful" — then authorised this walk with no backup of HD0. The
rule was mine, stated hours earlier, and not applied to my own next piece of
work. **The general form, eosed's phrasing:** *both of us failed to apply a rule
we had just articulated, to our own next work.* Not fixable by more care; the
rule has to be in the shape of the thing.

**Consequences, now binding:**

1. **Recon and traversal are separate programs.** Recon (`recon.py`) contains no
   soft-key constant at all — audited independently: the only strings reaching
   `tap` are seven movement and five mode keys, `tap` sends exactly one key via
   `getattr(pp.Key, name)` and raises on an unknown name, and **no move or mode
   shares a code with any soft key**. The capability is absent, not guarded.
2. **Queue pages, not presses.** No stored intention outlives the screen it came
   from; the move is chosen from the page in front of you, now.
3. **Recon does not attempt modal dismissal.** It aborts and reports which move
   opened the dialog. Guessing a dismissal is what turned a wrong press into a
   confirmed one.
4. **No hardware session without a current image backup**, taken first.

**Wire-level adjacency, computed (not a defect, a property to know):** the panel
button message `40 <key> 00 <01|00>` carries **no checksum**, and three of
recon's seven movement keys sit one bit from a soft key —

```
CURSOR_UP  0x6E  ->  F3, F5, F6      (three, the worst)
PAGE_NEXT  0x6B  ->  F5
PAGE_PREV  0x69  ->  F4
F1 and F2 are NOT reachable by any single-bit flip from any recon key.
```

No guard is added, deliberately: a read-back **detects and cannot prevent** —
the press has happened by the time the fingerprint returns — and there is no
protocol-level check to reject a corrupted byte. What actually bounds the risk
is that recon never visits the disk subtree, so a bit flip reaches
Name/New/Copy/Export/Place/Info rather than Load/Save/Erase. That F1 (`Cancel`)
is unreachable is a small mercy in the wrong direction: a flip can open trouble
and never dismiss it.

**And the condition to respect after the backup:** with **RAM empty, Load fires
with NO confirmation dialog** — the dialog appears only when there is something
to destroy. The state we will be in after a backup and power cycle is precisely
the state in which a stray Load is least survivable.

### 2b.4b What the staged walk script actually does, and what it does not

`/home/lentferj/temp/re_e4xt_walk/walk.py` (eosed, 2026-08-17). Parses and runs
`--help`; everything past that is unverified until the machine is up.

In: the template-matching whitelist above with an empty library; DISK subtree
absent from the mode list outright; page fingerprint = (left-edge band,
soft-key row band); modal probe before walking **and after every press**, with a
refusal to start if a modal is already open; start-page control re-visited at
the end; `--min-pages` implausibility check; and `frontier.json` recording every
exit seen and not followed, with the reason.

**Two limitations, stated by its author rather than found later:**

1. **The fingerprint omits cursor position**, so it enumerates *pages*, not
   cursor states. The `(left-edge, soft-key row, cursor)` design above is the
   fuller version; this is the reduced one, and the difference is real for any
   page whose parameters live under cursor movement.
2. **The frontier queue is breadth-*ish*, not a graph search.** Good enough to
   enumerate reachable pages; **not a proof of coverage**, and should not be
   quoted as one.

Neither is a defect. They are the honest boundary of a first pass, and the
`frontier.json` output exists so the boundary is visible in the result rather
than in someone's memory of this document.

### 2b.5 Sequencing

Run it **before** the targeted B-section sweeps — but eosed corrected my reason,
and theirs is stronger. I argued the walk might *retire* section-B items. **It
cannot retire B11**: that is a mapping from a BYTE VALUE to a filter NAME, and
the walk sees only whatever the scratch preset happens to hold. Producing the
id-to-name table needs the byte varied across its range, which is exactly what
the 98-preset bank does and nothing else does. Same for B3. (B1/B2 it may well
answer incidentally, since any key field on screen renders the -2 octave
question visible.)

**The real argument is that the walk produces the input the B script is
currently guessing.** Every crop box and panel route in `b_sweep.py` is a
placeholder; eosed has never navigated Preset Edit's filter page. The walk is
the calibration pass for the whole B section and hands over routes and field
coordinates as a by-product. Running B11 first means running it with guessed
coordinates, discovering the route by trial with a 98-preset bank loaded, and
probably burning the load. It is also the phase most
likely to change what the converter should support, so its output has a longer
tail than any measurement here.

---

## 3. Phase 2 — §ENVSPAN, the one suspected live defect

`env_seconds_to_rate()` takes **no span argument**, so if the EOS envelope byte
is a slew *rate*, every stage whose travel distance differs from the
calibration's is wrong. A decay to sustain 80 % travels a fifth of the distance
and would finish in roughly a fifth of the requested time.

**This is not speculative by analogy** — s3ked established exactly this for the
AKAI on 2026-08-11, which is why AKAI envelope 2 is deliberately unwired. The
E4B path never had the lesson applied.

**A tell already in our own data:** the calibration is six Decay-1 measurements
fitted at **r² = 0.96**, far the worst fit in the file where every other
hardware law sits at 0.999+. If those six decays did not all use the same
sustain level and the byte is a rate, `time = span/rate` scatters exactly that
way. *The sustain level used was never recorded* — that gap is itself the
finding.

### The measurement

`gen_e4xt_envspan_bank.py` — one bank, four presets:

| preset | decay byte | sustain | predicts (RATE) | predicts (DURATION) |
|---|---|---|---|---|
| `ENVSPAN 20` | fixed *B* | 20 % | long | same as below |
| `ENVSPAN 80` | fixed *B* | 80 % | ~1/4 of the above | same as above |
| `ENVSPAN CTL` | fixed *B* | 20 % | **duplicate of preset 1** | ditto |
| `ENVSPAN REF` | different byte | 20 % | scales with byte | scales with byte |

**The discriminator is a ratio, not an absolute time** — no timing calibration
needed, only the same method applied twice. `ENVSPAN CTL` is the negative
control: it must reproduce preset 1. If it does not, the timing method is
unreliable and the ratio means nothing.

**Implausible result:** a ratio near 1.0 *and* near 4.0 in different repeats —
that is measurement noise, not a duration. Run each preset twice.

---

## 4. Phase 3 — batched confirmations (C–G)

All five are "we changed something, does it sound right". They share a bank.

`gen_e4xt_confirm_batch.py` — one bank whose presets are **A/B pairs**, because
"does it sound right" is unanswerable and "does it differ from the version
without the fix, in the predicted direction" is answerable:

- `VC OLD` / `VC NEW` — the zone-table trailer (item C). Predicts: OLD reports
  voice count 1, NEW reports the true count. **Readable on the display, so this
  may not need audio at all** — check in Phase 1 and skip here if so.
- `ST MONO` / `ST WIDE` — E4B stereo (D).
- `SC OFF` / `SC ON` — single-cycle (E).
- `FE OLD` / `FE NEW` — the −0.114 filter-env shift (F).
- `VF OLD` / `VF NEW` — already built (G); fold in rather than rebuild.

**Every pair must be audibly distinguishable in a stated direction before the
session**, written into the procedure. "They sound different" is not a result if
we did not say beforehand which way.

---

## 5. Sequencing, by what each phase costs

The expensive step is **powering the machine and having Jan at the desk** —
plan around that, not around tidy per-item order.

```
OFFLINE (tonight, no machine)
  build all three banks + analysis scripts
  ask the corpus first: any Phase-1 item answerable from 461 local E4B files?
  ask the EOS 4.0 manual (422 pp, pdftotext-readable) before measuring anything

POWER-ON, NO AUDIO NEEDED      <- do all of this before touching a cable
  Phase 1 display join, all presets
  item C if the voice count is displayed

POWER-ON, AUDIO
  Phase 2 ENVSPAN (needs timing only, not spectrum)
  Phase 3 listen batch
```

Phase 1 needs no audio path at all. If a session gets cut short, it is the part
that will have produced findings.

---

## 5b. Staged on the ZuluSCSI card, 2026-08-18

Both banks are written to the E4XT card and its `whatiswhat.txt` slot map is
updated to match (the old `CD2 - DIRCON` entry retired, since those files are
`XX_*.disabled` and slot CD2 was free).

    CD2-F58ANCHOR.iso            98 presets, vpar[58] 0x00-0x5F   Phase 1
    CD2-F58ANCHOR_expected.csv   the join's expectation table
    CD6-ENVSPAN.iso              4 presets, rate-vs-duration      Phase 2

**Phase 1b, the screen walk, needs neither** — it runs on a scratch preset and
wants no bank at all. It is still first.

## 6. Tools to build (offline deliverables)

| tool | status | purpose |
|---|---|---|
| `gen_e4xt_ftype_anchors.py` | **built**, staged as CD2 | Phase 1 bank |
| `gen_e4xt_envspan_bank.py` | **built**, staged as CD6 | Phase 2 bank |
| `gen_e4xt_confirm_batch.py` | **to build** | Phase 3 bank |
| `e4xt_display_join.py` | **built + self-tested** | joins eosed's display dump to our written bytes; reports disagreements, like the K2000 anchor join |
| `gen_hw_confirm_batch.py` | exists | precedent to follow |
| `fit_e4b_rate_fields.py` | exists | precedent for corpus-first analysis |

**`e4xt_display_join.py` is the one that matters.** The K2000 equivalent is what
found the filter-table faults, and writing it now — before any data exists —
forces the output format to be decided in advance rather than fitted to whatever
comes back.

---

## 7. The rig already exists — `tests/re_banks/hw_measure.py`

Jan's correction, 2026-08-17: **this was already built and I was about to plan
around not having it.** It drives the E4XT over MIDI, records its audio, and
measures the result — and it can **sweep 128 points unattended**, where
`ENV_RATE`, `MOD_DEPTH_CAL` and `AMP_LEVEL` were every one of them fitted from
four to six *stopwatch* points.

Rig as wired: MIDI out `ESI M4U eX MIDI 4`, channel 5; audio in JACK
`system:capture_15/16` for the E4XT. It records from the **hardware capture
ports, upstream of the AF210M EQ and Sonarworks** — recording downstream would
convolve every measurement with a room-correction curve, tilting spectra and
moving every filter corner, and a verification pass would reproduce the error
and look like a confirmation.

`analyze_envelope_recording.py` is its analysis half and already does
decay-time and plateau-level measurement.

**Consequence for Phase 2: §ENVSPAN needs no new tooling at all.** The bank, and
`hw_measure.py --program N` with `analyze_envelope_recording.py --mode amp`, is
the whole measurement — unattended, and at a point count that makes the r²=0.96
calibration re-fittable properly rather than merely re-checked.

**Changed 2026-08-17 on Jan's instruction** (from the S3000XL sessions): the
recorder is now the in-process JACK client **only**. It used to fall back to
spawning `jack_rec` per capture with a warning; that path stops exiting past
roughly eight captures and **takes the JACK server with it**, needing the audio
graph restarted. A warning helps nobody in an unattended sweep, which is the
case this rig exists for, so a missing binding is now fatal at startup rather
than a degraded run that dies at capture 9 and leaves a truncated set someone
later fits a curve to.

---

## 8. Open questions for Jan

1. ~~Is `stereoE2E` still the right branch for item D?~~ **Answered by Jan
   2026-08-17: the branch is gone and the work is on `main`.** Verified — 15
   stereo sites in `main`'s `e4b_writer`, §E4BSTEREO on `main`, no such branch
   in the repo or the reflog. It remains **unheard on hardware**, so item D
   stays open; only its branch note was stale.
2. **Priority if the session is short.** Recommendation: **Phase 1b, the screen
   walk, first** — it is the only phase that can find things we do not know
   exist, and it may retire section-B items by showing the machine's own labels.
   Then Phase 1, then Phase 2.
3. **Scratch bank for the walk** — it must run somewhere a stray keypress costs
   nothing. Is there a preset on the machine safe to treat as disposable, or
   should the walk load one of ours first?
