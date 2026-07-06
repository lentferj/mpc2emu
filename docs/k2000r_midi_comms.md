<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# K2000R MIDI / SysEx Communication — field notes

> Practical, verified notes for talking to a Kurzweil **K2000R** over MIDI,
> captured 2026-06-14 while reverse-engineering KRZ programs. Written to seed a
> future **graphical MIDI-remote** project. Items marked **✓verified** were
> exercised live against Jan's K2000R; others are from the K2000 *System
> Exclusive Protocol* manual (chapter 30) and the
> [`psobot/k2000`](https://github.com/psobot/k2000) library.

---

## 0. TL;DR for the remote app

- Use **`python-rtmidi`** + the **`psobot/k2000`** library — it implements the
  *entire* SysEx protocol (object read/write, screen read as text+graphics,
  front-panel button injection). Don't re-implement; wrap it.
- The K2000 echoes its **whole LCD** back over SysEx (`ALLTEXT` → 8×40 ASCII,
  `GETGRAPHICS` → 2560-byte pixel layer) and accepts **front-panel button
  presses** (`PANEL`). That is everything a remote UI needs: mirror the screen,
  send buttons + alpha-wheel. ✓verified (screen read works live).
- Product ID = **0x78**, manufacturer = **0x07** (Kurzweil). Device-ID 0 by
  default; **127 = broadcast** (any K2000 answers). ✓verified.

---

## 1. Transport / cabling (the part that wasted an hour — read this first)

A K2000 is "MIDI silent" until the **return path** is right. On Jan's rig the
working configuration is **asymmetric** ✓verified:

| Direction | Port |
|---|---|
| PC → K2000 (commands) | `mididings_k2000r:in_1` (mididings routes it to the K2000's MIDI IN) |
| K2000 → PC (replies)  | **`ESI M4U eX`** interface (a *different* box from the send side) |

Two traps:

1. **Send and receive are on different interfaces.** Most libraries (incl.
   psobot's auto-detect) assume one *bidirectional* port whose name appears in
   both the input and output lists. Here it doesn't — you must open the out and
   in ports **separately**. See `tests/re_banks/krz_sysex_live.py::connect`.
2. **The ESI M4U eX reassigns its IN/OUT sub-ports dynamically with traffic**
   (Jan), so the reply can arrive on *any* ESI sub-port (`56:0`…`56:7`). Solution:
   open **all** ESI input sub-ports and poll them merged (`MultiIn` in the same
   file). With only the K2000 powered on the ESI, this is unambiguous.

Diagnostic that finds the real reply port regardless of routing: send `ALLTEXT`,
then listen on **every** input port for a reply whose 5th byte is `0x19`
(SCREENREPLY) — distinguish it from your own `0x15` request echoed by any MIDI
thru/merge. (That is exactly how the ESI return path was found.)

> `is_connected` in psobot uses a 0.1 s timeout — too short for the mididings
> round-trip; it returns False even when the link is fine. Use **1.5–2 s**
> timeouts on real calls.

---

## 2. SysEx envelope

```
F0  07  <dev>  78  <msg-type>  <fields…>  F7
```
- `07` = Kurzweil manufacturer id, `78` = K2000 product id.
- `<dev>` = SysX Device ID (MIDI-mode RECV page). Matches the K2000's setting, or
  **127** to broadcast. (Device ID ≠ MIDI channel; channel only affects notes/CC.)
- Screen/param requests and replies use the same envelope.

### Numeric field encoding
Multi-byte values are **big-endian 7-bit chunks** (MIDI bytes are 7-bit). e.g.
`type(2)` for 132 → `01 04`; `idno(2)` for 200 → `01 48`.

### Binary `data` field encoding (the `form` byte)
- `form=0` **nibblized**: each 8-bit byte → two MIDI bytes (hi nibble, lo nibble).
  Easy to read/debug. (`4F D8 01 29` → `04 0F 0D 08 00 01 02 09`.)
- `form=1` **bit-stream**: 7 data bits per MIDI byte, trailing bits zero. Compact.
- `xsum` (1 byte) after `data` = `sum(data_midi_bytes) & 0x7F`.

(Codecs, unit-tested against the manual's worked examples, are in
`tests/re_banks/krz_sysex_probe.py`.)

---

## 3. Message catalogue (msg-type → fields)

| Code | Name | Fields | Purpose |
|---|---|---|---|
| 00 | DUMP | type idno offs size form | request a byte range of an object → LOAD |
| 01 | LOAD | type idno offs size form data xsum | **poke** bytes into an existing object |
| 02 | DACK | type idno offs size | load accepted |
| 03 | DNAK | type idno offs size code | load rejected (1 editing, 2 cksum, 3 bad id, 4 not found, 5 RAM full) |
| 04 | DIR | type idno | → INFO |
| 05 | INFO | type idno size ramf name | object size/name/in-RAM flag |
| 06 | NEW | type idno size mode name | create object (idno 0 = first free) |
| 07 | DEL | type idno | delete RAM object (ROM can't be deleted) |
| 08 | CHANGE | type idno newid name | rename / renumber |
| 09 | WRITE | type idno size mode name form data xsum | **write a whole object** (DEL+NEW+LOAD); also what the K2000 emits on a front-panel "Dump" |
| 0A | READ | type idno form | request a full object → WRITE |
| 0B | READBANK | type bank form ramonly | dump a whole bank (stream of WRITE, then ENDOFBANK) |
| 0C | DIRBANK | type bank ramonly | INFO for each object in a bank |
| 0D | ENDOFBANK | type bank | terminator for bank ops |
| 0E | DELBANK | type bank | **delete a bank** (DESTRUCTIVE — `type=0,bank=127` wipes all RAM) |
| 0F | MOVEBANK | type bank newbank | relocate a RAM bank |
| 14 | PANEL | buttons(3n) | inject front-panel presses (see §5) |
| 15 | ALLTEXT | — | request the LCD text |
| 16 | PARAMVALUE | — | request current parameter's value (ASCII) |
| 17 | PARAMNAME | — | request current parameter's name (ASCII) |
| 18 | GETGRAPHICS | — | request the LCD pixel layer |
| 19 | SCREENREPLY | (text/pixels) | reply to 15/16/17/18 |

**Safe for a remote:** 00,01,04,05,09,0A,0B,0C,0D,14,15,16,17,18 (reads + scoped
writes + UI). **Dangerous:** 07 DEL, 0E DELBANK, 0F MOVEBANK — gate behind
explicit user confirmation.

---

## 4. Object model

SysEx object **type = the disk-file object type + 96**:

| Object | File type | SysEx type | SysEx 2-byte field |
|---|---|---|---|
| Program | 36 | 132 | 01 04 |
| Keymap | 37 | 133 | 01 05 |
| Sample/Soundblock | 38 | 134 | 01 06 |
| Effect | — | 113 | 00 71 |
| Song | — | 112 | 00 70 |
| Setup | — | 135 | 01 07 |
| Master params | — | 100, id 16 | 00 64 |

IDs: user objects 1–999, grouped in banks of 100 (bank `n` = ids `n00–n99`); some
types allow only 10 per bank (effects 100–109). `idno=0` in NEW/LOAD-mode-1 = next
free id.

### ⚠ RAM format ≠ disk (.KRZ) format — **key finding** ✓verified
The object data returned by `DUMP`/`READ`/`WRITE` is the K2000's **fixed-layout
RAM structure**, *not* the variable tagged-segment serialization in a `.KRZ`
file. Examples (live dumps):
- Program 1: 498 bytes, no `0x08/0x09/0x21` segment tags.
- Keymap 1: 796 bytes; a level array reads `64,56,48,40,32,24,…` (×8 step) vs the
  file's `16,14,12,…` (×2 step), and the file's `cents=100/epv=127` signatures
  are absent.

The firmware converts segment-file ↔ RAM on load/save. So: **SysEx poking decodes
the RAM layout; a `.KRZ` writer must emit the file layout.** For a remote app this
doesn't matter (you operate on live RAM objects); for the mpc2emu converter it
means SysEx RE and file-format RE are two separate maps. See
`docs/re_procedures/krz_program_re.md`.

---

## 5. Front-panel remote control (PANEL = 0x14)

Each press = 3 bytes: `event, button, arg`.

- **event:** `08` up · `09` down · `0A` repeat · `0D` alpha-wheel.
- **arg:** for the wheel, `64 + clicks` (so `0x46`=+6 right, `0x3A`=−6 left); else 0.
- Efficiency: multiple `down`s then one `up` = auto-increment (e.g. holding `+`).

**Button codes** (hex): digits `00`–`09`, `+/−`=0A, CANCEL=0B, CLEAR=0C, ENTER=0D,
cursor Up/Dn/L/R = 10/11/12/13, CHAN/BANK +/− = 14/15, `+`=16 `−`=17,
EDIT=20 EXIT=21, soft A–F = 22–27 (YES=26 NO=27), mode buttons: PROGRAM=40
SETUP=41 QUICK-ACCESS=42 MASTER=43 MIDI=44 DISK=45 SONG=46 EFFECTS=47.

The K2000 also **emits** PANEL messages for its own presses if MIDI-mode XMIT
"Buttons" = On — i.e. a remote can mirror physical knob/button activity.

---

## 6. Reading the display

- **ALLTEXT (15) → 320 bytes** = 8 rows × 40 chars ASCII (mask each byte `&0x7F`).
  If you get <320, the screen was mid-redraw — re-request. ✓verified.
- **GETGRAPHICS (18) → 2560 bytes**: low 6 bits per byte = pixel on/off; chars are
  6×8 px monospaced; pixels over text invert it. psobot's `image.py` decodes this
  into a PIL image (great for a pixel-accurate remote view).
- **PARAMNAME (17)/PARAMVALUE (16)** → ASCII of the currently-cursored parameter.
  Some values embed the object id (e.g. `"983 OB Wave 1"`). Empty name (e.g. the
  program page) → just a `00`.

A remote-screen loop: poll ALLTEXT (or GETGRAPHICS) ~10 Hz, render; send PANEL on
user input; the soft-button labels are the bottom LCD row.

---

## 7. Implementation notes / gotchas

- **psobot/k2000 API:** `K2000Client(midi_identifier=…)`, then
  `.get_screen_text()`, `.get_screen_image()`, `.dump(type,id)`,
  `.load(type,id,data,offset)`, `.read/.write`, `.programs[id]`, `.press(Button.…)`.
  For Jan's split routing, bypass its auto-detect: construct via `__new__` and set
  `.midi_out`/`.midi_in` manually (see `krz_sysex_live.py`).
- **Threading:** rtmidi input is polled; a 5 ms poll loop with a 1.5–2 s deadline
  is reliable here. Flush stale input before each request.
- **Bank dumps** insert ~50 ms between WRITE messages; when sending a bank *to* the
  K2000, either pre-clear the target bank (DELBANK) or wait for each DACK, else
  messages are dropped while the CPU deletes.
- **ALSA on Linux:** opening many `rtmidi.MidiIn/Out` objects in a loop can throw
  `snd_seq_hw_open … Cannot allocate memory` — reuse port objects; don't re-open
  per request.
- **Device/channel:** SysEx uses the **SysX Device ID** (MIDI RECV page), *not* the
  MIDI channel. Jan's K2000R is on MIDI channel 9 (notes/CC) but SysEx works
  independent of that. Use device 127 if unsure of the SysX ID.

---

## 8. Repo tooling (reusable for the remote)

- `tests/re_banks/krz_sysex_live.py` — split-port live connection (the routing above)
- `tests/re_banks/krz_sysex_probe.py` — pure-python SysEx codecs (no MIDI dep), unit-tested
- `tests/re_banks/krz_reader.py` — `.KRZ` *file* object reader (disk format)
- Library: `/home/lentferj/git-repos/k2000` (psobot) — full protocol
- Manual: `…/K2000/30 SysEx.pdf` (authoritative protocol reference)

---

## 9. Program-editor navigation map (verified live, 2026-06-14)

Driving `EditProg` over SysEx `PANEL`. From Program mode: type a program number +
`Enter`, then `Edit` opens the editor on the **ALG** page. The bottom LCD row is
the soft-button tab strip; **SoftF = `more>`** cycles tab *groups* (SoftA =
`<more`). The displayed page only changes when you press a specific page's soft
button. Group order (SoftF from ALG):

| Group | Soft B / C / D / E tabs |
|---|---|
| 0 | ALG · LAYER · KEYMAP · PITCH |
| 1 | F1 · F2 · F3 · F4/AMP (DSP function pages) |
| 2 | OUTPUT · EFFECT · COMMON · SetRng |
| 3 | **AMPENV** · ENV2 · ENV3 · ENVCTL |
| 4 | LFO · ASR · FUN · VTRIG |
| 5 | Name · Save · Delete · Dump |
| 6 | NewLyr · DupLyr · ImpLyr · DelLyr |

So **AMPENV = `Edit`, SoftF×3, SoftB**. The AMPENV page shows a 7-segment env as
two rows (times / levels): `Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3` + `Loop`.

**Save flow:** group 5 → SoftC (`Save`) → "Save NAME as: ID#nnn" → type a new id
(digits) → `Enter` → **SoftE (`Save`)**. The "Save as" dialog soft row is
`Object · _ · _ · Rename · Save · Cancel` (Save=SoftE, Cancel=SoftF).

**Exit-without-saving:** after any value edit, `Exit` pops "Save NAME before
exiting?" with soft row `Rename · Cancel · Yes · No` → **No = SoftF**. Pure
*navigation* (no wheel turns) sets no modified-flag, so it exits cleanly.

**Recover-to-known-state routine:** loop reading the screen; if it contains
"before exiting" or a "Save … as:" → SoftF; else press `Exit`; until the top line
starts with `ProgramMode`. (Implemented in the RE scripts.)

### ⚠ Hang caveat
Long unattended PANEL sequences can leave the K2000 in a modal state where it
stops answering SysEx **entirely** (no `0x19` on any port, any route). Blind
`Exit` presses do not always clear it — recovery then needs a **front-panel /
power-cycle**. For automation: keep each transaction short, verify the screen
after every page change, and never fire a blind multi-step macro.

### Object scratch hygiene
RE that needs a writable program must use a **RAM copy** (programs 1–199 are ROM;
200–299 may hold user data — use **300+**). Raw `WRITE`/`new(create_ram_copy)` of
a dumped RAM object does **not** reliably reproduce a valid program (internal
size/pointer fields get mangled → 2-byte / 57 kB stubs), and **poking arbitrary
offsets can corrupt structural bytes**. The reliable path is the editor's own
**Save to a 300+ id**, then `DUMP` + diff. Delete scratch ids with a raw `DEL`
(msg 0x07) when done, and drain the `INFO` reply afterward.

---

## 10. Closed-loop audio measurement rig (2026-06-15)

The K2000R output is on JACK `system:capture_17/18`; MIDI notes go out the
`mididings_k2000r` port on **channel 9**.  `tests/re_banks/krz_audio_measure.py`
ties it together: **set a byte (SysEx) → play a note (MIDI) → record (JACK) →
analyse (numpy)** — fully autonomous parameter measurement, no ears, no disk.

Verified working: pitch to FFT-bin resolution (C4→261.1 Hz vs 261.6); spectral
centroid tracks filter cutoff (25088 Hz→6817, 8870→4628, 4435→3117, 2217→2648).

Use it for: end-to-end converter validation (load a `.KRZ`, measure env/filter/
vibrato vs the source); calibrating the approximate depths; measuring properties
the LCD doesn't show.  Needs `JACK-Client`, `python-rtmidi`, `numpy`.

**Probe signal:** use a steady, spectrally-known source, NOT a sample — Jan set
up **#311** = ROM keymap "151 Sawtooth" → Algorithm 1 4-pole lowpass.  Saw/`SAW+`
is a good all-rounder; `NOISE+` is better for full-range filter response; sine
for pure pitch/vibrato.  **Editor-cursor gotcha:** most edit pages have the entry
cursor already on the main field — wheel directly; moving the cursor lands you on
the wrong parameter (cost an hour on both the AMPENV and F1 pages).

> ⚠ Watch for **FX in the audio path** (an external pedal / the program's own FX
> chunk) coloring the spectrum — bypass it before measuring.
