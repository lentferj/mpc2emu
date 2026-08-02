# KRZ stereo — K2000R hardware confirmation procedure

Branch `krz_stereo` implements stereo in both directions. Everything about it
is verified **structurally** — 533 corpus samples fix the layout, 51 real
samples round-trip byte-exact, mono output is byte-identical — and **nothing
is verified behaviourally**. No K2000 has ever loaded a stereo bank we wrote.

That gap matters here more than it sounds, because this project's failures have
consistently been files that were shaped exactly right and still misbehaved:

- the **silent-KRZ bug** — `Soundfilehead.flags` `0x40` alone loads the sample
  and produces no sound;
- the **4+ layer silence** — `CAL[7,8]` claimed a second keymap, muting the
  whole program;
- **CR-10** — `sampleEnd` means the *loop* end, which no amount of looking at a
  well-formed file reveals.

This session answers behaviour. Budget: one bench sitting.

---

## 0. Setup

```
python3 tests/re_banks/gen_krz_stereo_hwtest.py      # already run — see below
python3 tests/re_banks/krz_stereo_measure.py --selftest
```

| item | value |
|---|---|
| bank | `/home/lentferj/temp/krz_stereo_hw/KRZSTHW_01.KRZ` (136 KB) |
| floppy | `/home/lentferj/temp/krz_stereo_hw/KRZSTHW.img` (10% of a 1.44 MB disk) |
| manifest | `/home/lentferj/temp/krz_stereo_hw/KRZSTHW.md` |
| programs | 200 `STIMAGE`, 201 `STLOOP`, 202 `STVOICE`, 203 `MNVOICE`, 204 `STFLAG`, 205 `PANREF` |
| MIDI | `k2000r` port, channel 9 |
| audio | JACK `system:capture_17/18` |

**Two things that invalidate the whole session if skipped:**

1. **k2kremote OFF.** Its ~2–3 s `GETGRAPHICS` heartbeat has crashed the K2000
   mid-operation before (that was the "delete lockup" root cause). Every SysEx
   step below assumes a quiet bus.
2. **Keep L and R separate all the way to the measurement.** A mono-summed
   capture cannot distinguish a correct stereo image from a swapped one from a
   summed one — it answers every question in this document with the same wrong
   answer. This is exactly how the first E4B pan reading went wrong. The
   `--selftest` above includes a case asserting that a mono sum does *not* read
   as a correct channel order.

Run the self-test first regardless. The corpus scan that started this branch
reported "0 stereo samples found" because its own reader was broken — a broken
instrument looks identical to a clean result.

---

## 1. Does it load and make sound? (`STIMAGE`, key D#3)

**Check the mono key first.** `SI_MONO` at D#3 is an ordinary mono sample. If
that is silent, the problem is not stereo and nothing else here means anything.

## 2. Channel order (`STIMAGE`, keys C3–D3)

The only claim the corpus **cannot** settle: telling left from right inside a
file needs the source it was made from. Three keys answer it two independent
ways — by pitch (C3: L=440, R=660) and by absence (C#3 left-only, D3
right-only). Absence is the stronger evidence; a mono sum would still show
*some* pitch on both sides but cannot fake silence.

- **Correct** → header 0 is the left channel. Nothing to change.
- **Swapped** → header 0 is the right channel. One-argument fix: exchange the
  two planar blocks in `_write_sample_object`, and the matching pair in
  `krz_parser._planar_to_interleaved`.

## 3. Loop sync (`STLOOP`, key C3, hold ~8 s)

L 220 Hz / R 330 Hz, exactly 22 and 33 whole cycles in the 4410-frame loop, so
any drift between the two blocks beats rather than hiding. Measured in two
windows (0.5–1.5 s and 6–7 s). The E4XT passed this; the K2000 addresses its
two blocks through separate headers, so it is a genuinely open question.

## 4. Voice cost (`STVOICE` vs `MNVOICE`)

The K2000 has 24-voice polyphony. If a stereo sample costs two voices, stealing
starts at ~12 notes instead of ~24.

**The ratio is the result, not the absolute count.** On the E4XT the first two
attempts at this measurement both produced confident wrong answers, because a
level ceiling saturating on summed voices looks exactly like a voice ceiling.
The mono control run is what distinguishes them, which is why `MNVOICE` exists
and why the script refuses to conclude when the ratio lands between 1.3 and 1.6.

**Consequence if stereo costs two:** `bank_splitter._VOICES_PER_NOTE` currently
contains only `{'e4b': 32}` — krz was deliberately left out because nothing was
measured. Add it, and note that halving an already-tight 24-voice budget is far
more painful than halving the E4XT's 128.

## 5. What the `LYR[8]` `0x20` bit does (`STFLAG` vs `STIMAGE`)

`STFLAG` is byte-identical to `STIMAGE`'s C3 case except that one bit is
cleared, patched after writing so the comparison is controlled.

The corpus says the bit is set on 86.4% of all-stereo layers and 0.7% of
all-mono ones — a clear signal, but *not* 100%, and the 13.6% is the
interesting part. Either the bit is cosmetic, or those layers are deliberately
playing one channel of a stereo sample. This preset decides which.

## 6. Pan

**mpc2emu writes no pan to KRZ at all** — `krz_writer` drops `ZoneMapping.pan`
on the floor. So there is nothing in the bank to measure a pan law *against*,
and the E4B-style "convert two banks differing only in `--pan-law`" comparison
has no analogue yet. The work splits in two:

### 6a. The law — needs no byte knowledge

```
python3 tests/re_banks/krz_pan_hunt.py --law
```

Set PAN on the front panel for program 205 `PANREF` (single layer, mono 440 Hz
tone), press Enter at each prompt; the script records L and R and reports
balance and **total power L²+R² relative to centre**. That last quantity is the
E4XT's +4.5 dB pan excess, and it is the number that decides whether KRZ needs
its own `--pan-law {hardware,constant-power}`.

The script also checks +n against −n for asymmetry; if the two sides disagree
by more than 1.5 dB, the rig's channel gains are suspect and the law would
inherit the imbalance. `PANREF`'s own centred reading (test P005 in
`krz_stereo_measure.py`) is the guard for that — run it first.

### 6b. The byte — needed before anything can be written

Two constraints from earlier K2000 RE, both non-obvious:

- **Never poke program objects over SysEx.** They carry structural bytes and
  pokes wedge the machine. The proven mutator is the editor: change the value
  on the panel, **Save to a 300+ id**, dump, diff.
- **SysEx `DUMP` returns the RAM layout, not the `.KRZ` segment layout.** The
  firmware converts on load/save. So the RAM byte is the fast half of the
  answer and the *file* byte is the half the writer actually needs.

```
python3 tests/re_banks/krz_pan_hunt.py --baseline 300 /tmp/pan_base.bin
#   ... set PAN on the panel, Save to id 301 ...
python3 tests/re_banks/krz_pan_hunt.py --diff /tmp/pan_base.bin 301
```

A clean 1–2 byte diff is what previous single-parameter RE produced here. Then
for the file byte: save both variants to the Gotek as `.KRZ` and

```
python3 tests/re_banks/krz_pan_hunt.py --krzdiff PAN_A.KRZ PAN_B.KRZ
```

which reports the differing byte per program **per segment**. A byte moving
inside segment `0x53` would match the format doc's "pitch/filter/amp/pan
defaults" note for that HOB segment — wire it into `_patch_layer`.

---

## 7. Running the lot

```
python3 tests/re_banks/krz_stereo_measure.py --selftest        # first, always
python3 tests/re_banks/krz_stereo_measure.py --all --keep ~/temp/krz_stereo_hw/rec
python3 tests/re_banks/krz_pan_hunt.py --law
```

`--keep` writes every recording as a stereo `.wav`, so any surprising verdict
can be re-checked by ear or with a different analysis without re-running the
hardware.

---

## 8. Results (fill in)

| # | Question | Expected | Measured | Verdict |
|---|----------|----------|----------|---------|
| 1 | mono key sounds | yes | `ST_MONO` 440 Hz both outputs | **PASS** |
| 2 | stereo keys sound | yes, both channels | both headers audible, separated | **PASS** |
| 3 | **channel order** | header 0 = left | `ST_LR` L=440 / R=660; `ST_LON` R **silent**; `ST_RON` L **silent** | **PASS — header 0 IS left** |
| 4 | loop sync | L 220 / R 330 steady | `STLOOP` L 220 only (0.1055), R 330 only (0.0891) | **PASS** |
| 5 | stereo voice cost | 2 voices | not measured | open |
| 6 | mono voice cost (control) | 1 voice | not measured | open |
| 7 | `LYR[8]` 0x20 | unknown | **the stereo marker** — `0x24` vs `0x04` in a real bank's stereo/mono twins | **ANSWERED** |
| 8 | pan law: hard-pan excess | unknown | not measured | open |
| 9 | pan RAM byte | unknown | not measured | open |
| 10 | pan file byte | unknown | HOB `0x52`/`0x53` byte 2 + byte 14 carry channel routing (see §KRZSTEREO2) | partially answered |

**Measured 2026-08-02 on a bank produced by `krz_writer` with no post-hoc
patching**, so this exercises the shipping code path. Absence is what makes it
conclusive: `ST_LON`'s right and `ST_RON`'s left are at true zero, which
neither a summed nor a swapped image can produce.

| program | Left | Right |
|---|---|---|
| `ST_LR` | 440 = 0.1052, 660 = 0.0001 | 440 = 0.0001, 660 = 0.0886 |
| `ST_LON` | 440 = 0.1051 | silent |
| `ST_RON` | silent | 550 = 0.0889 |
| `STLOOP` | 220 = 0.1055, 330 = 0.0001 | 220 = 0.0001, 330 = 0.0891 |

## 9. What each outcome means for the branch

| outcome | action |
|---|---|
| all of 1–4 pass | the branch is behaviourally confirmed; merge it |
| channel order swapped | swap the planar blocks in writer + parser, re-run test 2 only |
| loop out of sync | the two headers need something we are not writing — do not merge |
| stereo costs 2 voices | add `'krz'` to `_VOICES_PER_NOTE` before merging, or the sizing warning is wrong for K2000 users |
| `0x20` bit required | keep setting it (we do); document that clearing it selects one channel |
| `0x20` bit cosmetic | note it, no change |
| pan law measured | decide whether KRZ needs `--pan-law`; blocked on 6b before anything can be written |

---

## Results (measured 2026-08-02 on the K2000R)

| # | Question | Result |
|---|----------|--------|
| 1 | mono key sounds | **PASS** |
| 2 | stereo keys sound, both channels | **PASS** |
| 3 | **channel order** | **header 0 is the LEFT channel** |
| 4 | loop sync | **PASS** — L 220 only, R 330 only, steady |
| 5 | stereo voice cost | **2 voices** — plateaus at 12 simultaneous notes |
| 6 | mono voice cost (control) | **1 voice** — reaches 24, the K2000's full polyphony |
| 7 | `LYR[8]` 0x20 | **required, not cosmetic** — clearing it removes the second channel entirely |
| 8 | pan law | **not applicable as framed** — see below |
| 9 | pan RAM byte | not applicable as framed |
| 10 | pan file byte | HOB `0x52`/`0x53` carry channel routing — see RESOLUTION_NOTES §KRZSTEREO2 |

Measured on a bank produced by `krz_writer` with no post-hoc patching, so this
exercises the shipping code path.

### Synthetic tones

| program | Left | Right |
|---|---|---|
| `ST_LR` (440 / 660) | 440 = 0.1052, 660 = 0.0001 | 440 = 0.0001, 660 = 0.0886 |
| `ST_LON` (440 / silent) | 440 = 0.1051 | silent |
| `ST_RON` (silent / 550) | silent | 550 = 0.0889 |
| `STLOOP` (220 / 330) | 220 = 0.1055, 330 = 0.0001 | 220 = 0.0001, 330 = 0.0891 |

Absence is what makes this conclusive: `ST_LON`'s right and `ST_RON`'s left sit
at true zero, which neither a summed nor a channel-swapped image can produce.

### Real audio, with a negative control

Four stereo drum samples converted through `convert.py`, one sample per program
(see the per-entry caveat below), all played on C3, three consecutive runs:

| program | content | corr(L,R) |
|---|---|---|
| `CrashSnare` | crash L / snare R | +0.0006 / -0.0000 / +0.0023 |
| `KickHat` | kick L / hat R | +0.0019 / +0.0018 / +0.0017 |
| **`MonoRef`** | **identical channels** | **-0.9930 / -0.9927 / -0.9996** |

`MonoRef` is the control and the reason this counts as confirmed: byte-identical
channels come back **correlated**, which rules out "two independently mangled
channels" as an explanation for the other two. The negative sign is the
measurement rig's own polarity inversion, matching the -0.93 that a commercial
mono program measures on the same rig. Confirmed by ear as well — crash in the
left speaker, snare in the right.

### Caveat when building any test bank for this instrument

**Per-entry sample assignment does not work on hardware.** A keymap with
distinct samples on adjacent keys plays only the FIRST, key-tracked — audible
as rising pitches. The file is written correctly; the K2000 does not honour it.
Give every sample its **own program** in any bank whose result must be trusted,
and verify by ear or by measurement which sample a key actually plays before
interpreting its audio. Tracked in TODO.md.

### Voice cost (measured 2026-08-02)

| notes played | stereo | mono |
|---|---|---|
| 8 | 8 | 8 |
| 12 | 12 | 12 |
| 16 | **12** | 16 |
| 20 | **12** | 20 |
| 24 | **12** | 24 |

**A stereo sample costs two voices**, as on the E4XT. Stereo plateaus at 12
simultaneous notes; the same material in mono reaches 24, the K2000's whole
polyphony. Ratio 2.00.

Measured at velocity 100, 45 and 25 with identical results (peaks -15 to
-28 dB at the lower velocities), so the plateau is voice allocation and not
output clipping — the failure mode that cost two attempts at this measurement
on the E4XT. `writers/bank_splitter._VOICES_PER_NOTE` now carries `'krz': 24`.

### Pan — MEASURED 2026-08-02

Pan is **not** on the layer page (it is on the **Output** page), which is what
made an earlier attempt conclude the question was mis-framed. It is a normal
parameter and both halves of it are now measured.

#### The law: constant power

| pan | L | R | total power | excess vs centre |
|---|---|---|---|---|
| hard left | -21.70 dB | -83.02 dB | -21.70 dB | +0.57 dB |
| centre | -24.72 dB | -25.88 dB | -22.27 dB | 0 |
| hard right | -86.07 dB | -22.84 dB | -22.84 dB | -0.57 dB |

Panning hard raises the live channel by **+3.02 dB** (left) and **+3.04 dB**
(right); the constant-power figure is 3.01 dB. The excess is symmetric at
**±0.57 dB**, exactly half the rig's own +1.14 dB centre imbalance, so the
instrument's true excess is **0.00 dB**.

**The K2000 pan law is constant power.** This differs from the E4XT's +4.5 dB
excess, so the two cannot share a `--pan-law` setting.

The opposite channel falls to -83/-86 dB at the extremes, i.e. the noise floor:
hard pan is full separation, not a partial tilt.

#### The RAM byte

A single byte changes across the whole 274-byte program object:

| pan | byte 270 | bits 2..5, 4-bit signed |
|---|---|---|
| hard left | `0xE5` | 9 → **-7** |
| centre | `0xC1` | 0 → **0** |
| hard right | `0xDD` | 7 → **+7** |

**Pan is a 4-bit signed field in bits 2..5 of RAM byte 270, range -7..+7** —
which is why the Output page shows no numeric value in the usual sense.

#### Still needed to WRITE pan

The above is the **RAM** layout returned by SysEx `DUMP`. The firmware converts
between RAM and the `.KRZ` segment layout on load/save, so the file byte is a
separate question: save a panned program to disk and byte-diff the `.KRZ`
against an unpanned one. Until that is done mpc2emu still writes no pan.

