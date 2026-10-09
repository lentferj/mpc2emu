<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors

This file is part of mpc2emu.

Full-tree code-review record. See README.md -> "Code review" for the entry point
and TODO.md -> CODE_REVIEW_2026_10_10 for the tracking row.
-->

# mpc2emu Code Review — 2026-10-10

Full findings from a whole-tree review of `mpc2emu` (~58k LOC source + ~32k LOC
tests), focused on **bugs, improvements and execution speed**.

- **Reproduced / verified:** every finding below states how it was checked. Claims
  marked *verified* were executed and their effect observed; claims marked
  *inferred* were read but not run.
- **Anti-duplication:** each finding was checked against `TODO.md` (949k, ~350
  heading rows). Where `TODO.md` already tracks the defect, the row says
  `TODO.md` and gives the row. New rows are those with **no** `TODO.md` entry.
- Nothing here has been changed. This document is the record; the fixes are a
  separate decision.

---

## Summary

| # | Severity | Area | One line |
|---|----------|------|----------|
| 1 | critical | `parsers/` | GIG region loop override mutates shared wave pool — last region wins |
| 2 | critical | `parsers/` | XPM `_apply_slice` uses file ints as slice bounds; negative start wipes sample |
| 3 | critical | `processors/` | `resample_*` clamps `loop_end` to a count, not an index — AKAI drops the loop |
| 4 | critical | `writers/` | `LoopType.FORWARD_REL` reaches E4B writer as *no loop at all* |
| 5 | critical | `convert.py` | §SILENTFAIL incomplete: AKAI path ignores `n_parse_failed`, exits 0 |
| 6 | critical | `processors/` | `--auto-loop-dump-dir` writes a stereo sample as a mono WAV |
| 7 | critical | `processors/` | `--shrink-by 100` / `--shrink-to 0` → unhandled `ZeroDivisionError` |
| 8 | major | `writers/` | EIII: chunk/area size from buffer, not bytes written — odd-length PCM overlaps |
| 9 | major | `writers/` | KRZ `_write_sample_object` does not clamp loop points against PCM |
| 10 | major | `writers/` | E4B one-sided `min(127, …)` clamps crash the write on negative keys |
| 11 | major | `parsers/` | SFZ `key=` is a fallback only — never overrides group `lokey`/`hikey` |
| 12 | minor | many | bounds guards that are off by one, unreachable, or missing |
| 13 | minor | `tests/` | two tests that cannot fail, and the seams that no test covers |
| 14 | perf | `resampler` | quantizers 1.6×, `auto_loop`/trim 1.5–2.7×, `e4b_parser` 1.46× |
| 15 | perf | retracted | `zip`-of-planes downmix rewrite is **slower** — measured |

**Headline speed:** end-to-end `trim → auto_loop → resample → write_e4b`,
mono + emulator2 **1.35×**, stereo **1.38×**, every written file
SHA-256-identical.

---

# CRITICAL

## 1. `gig_parser` region loop override mutates the shared wave pool

**File:** `parsers/gig_parser.py:668-675`

```python
sd = waves[wave_idx]

# Apply region-level loop override
if wsmp_info['loops']:
    l0 = wsmp_info['loops'][0]
    sd.loop_type  = (LoopType.ALTERNATING if l0['type'] == 1
                     else LoopType.FORWARD)
    sd.loop_start = l0['start']
    sd.loop_end   = l0['end']
```

`waves` is built once by `_extract_waves`; every region, instrument and
dimension-region referencing the same wave index receives **the same object**.
The module's own comment at lines 711-714 says shared waves are the normal case
in real GIG files — *"on the reference disc seven layers routinely share three
audio regions"*. So a later region's `wsmp` loop silently overwrites every
earlier one's.

**Verified** (two instruments, one wave). INSTR-A's region declares
`ulStart=100/ulLength=90`; INSTR-B's declares `0/190`. Both zones come back
with `loop=(0,189)`; `bank.samples` holds **one** object; after
`write_e4b → parse_e4b` the written sample carries `loop=(0,189)` —
**INSTR-A's zone plays INSTR-B's loop.**

Not tracked in `TODO.md`.

---

## 2. `xpm_parser._apply_slice` uses unclamped file integers as slice bounds

**File:** `parsers/xpm_parser.py:711-718` (and `729-734`, `771-774`)

```python
trim_start = slice_start          # straight from the file, no clamps
trim_end   = slice_end
...
sd.data = sd.data[trim_start * bytes_per_frame: trim_end * bytes_per_frame]
```

Python slicing makes a negative index mean *from the end*, and a buffer longer
than the upper bound yields an **empty** slice — the sample becomes 0 frames.
`SliceEnd` is not validated against `n_frames` in a way that saves it.

**Reachable from the current format, not only hand-edited files.**
`_mpc3_to_xml` (line 1603) feeds both arbitrary **signed** JSON integers
straight into `<SliceStart>`:

```python
start = int(lay.get('offset', 0) or 0) + int(lay.get('sampleStart', 0) or 0)
lput('SliceStart', start)
```

**Verified end-to-end** with a real gzip/`ACVS`/JSON MPC 3 program plus a
44,100-frame WAV: `offset: -100, sampleEnd: 200` →
`Loaded sample: kick (44100Hz, 0 frames)`. The zone keeps its `sample_name`,
the sample still reaches `bank.samples`, the preset is emitted, no diagnostic
is raised. `SliceStart=0, SliceEnd=-100` instead silently trims 100 frames off
the tail.

### Knock-on — a distinct defect on the same trigger

A 0-frame sample makes `krz_writer` print
`Sample [200] 'kick': 0 words` and `Written: …` with success, but re-parsing
that KRZ yields **0 presets / 0 samples / 0 zones**, and the reader reports the
false diagnostic at `parsers/krz_parser.py:2228-2250`:

```
[INFO] This bank holds 1 program(s) but no sample or keymap objects: it references
the K2000's ROM soundset, which is not in the file. Nothing to convert — this is the
bank's nature, not a read error.
```

It *does* have a sample object; `_get_sample` classified it as ROM because
`h.start_w >= pcm_words` (`krz_parser.py:1973`). The E4B path round-trips the
0-length sample cleanly, so the loss is KRZ-specific.

Not tracked in `TODO.md` (the row at `TODO.md:4545` is RESOLVED and about
slice playback generally, with no mention of bound validation).

---

## 3. `resample_*` clamps `loop_end` to a *count*, not an index — AKAI drops the loop

**File:** `processors/resampler.py:675-676` and `:746-747` (identical in both
functions)

```python
loop_start = max(0, min(round(sample.loop_start * scale), n_frames))
loop_end   = max(loop_start, min(round(sample.loop_end * scale), n_frames))
```

Every consumer of the model treats `loop_end` as **inclusive** —
`writers/e4b_writer.py:524` (`lel = (sample.loop_end - 1) * 2`),
`parsers/eiii_parser.py:173`, `parsers/xpm_parser.py:623`,
`processors/loop_renderer.py:59`, `processors/single_cycle.py:317`.
`n_frames` is a *count*, so the last valid index is `n_frames - 1`. The clamp
emits exactly `n_frames`, and `writers/akai_s3000_writer.py:2046-2048` gates
on `sd.loop_end < n_frames`:

```python
looped_now = (sd.loop_type != LoopType.NO_LOOP
              and sd.loop_end > sd.loop_start >= 0
              and sd.loop_end < n_frames)
```

**Verified end-to-end.** A 48 kHz WAV carrying a `smpl` forward loop ending at
the last frame, through `convert.py in --format akai`:

```
no --resample:   n=11024  loop_type=NO_LOOP  loop=0..0          <- loop GONE
--resample emax1: n=11025  loop_type=FORWARD loop=0..11023      <- loop kept
```

Direct proof at the site: with `loop_end == n_frames` the AKAI header carries
active-count 0 / "no looping" / both loop fields zeroed; with
`loop_end == n_frames - 1` it writes `LOOPAT1=44098, LLNGTH1=43179`
correctly. Also reachable via `--max-sample-rate` (44100→22050 gives
`loop_end=22050 == n_frames`).

No diagnostic is emitted anywhere — the run reports
`Done: 1 of 1 volume(s) written`.

**Blast radius:** every resampled or rate-snapped sample whose loop ends on
the last frame loses its loop when written to AKAI. E4B output is unaffected
(it stores `loop_end-1`); KRZ is masked by `krz_parser.py:2016-2017`'s
read-back clamp, though `krz_writer.py:583` still writes
`abs_loop_end = word_offset + num_words`, one word past the PCM.

Not tracked in `TODO.md` (the row at `TODO.md:2836` is about the E4B on-disk
field encoding, a different thing).

---

## 4. `LoopType.FORWARD_REL` is written by the E4B writer as *no loop at all*

**File:** `writers/e4b_writer.py:500`

```python
has_loop = (sample.loop_type in (LoopType.FORWARD, LoopType.ALTERNATING)
            and sample.loop_end > sample.loop_start)
```

`models/common.py:146` declares the value as first-class
(`FORWARD_REL = 3  # Loop until release`), `parsers/sf2_parser.py:458`
produces it, and `writers/eiii_writer.py:677` honours it — but the E4B writer
does not.

**Verified:** writing a bank whose sample has
`FORWARD_REL, loop_start=1000, loop_end=44099` and re-parsing gives
`loop_type=NO_LOOP loop=0-0`. An SF2 "loop until release" therefore converts
to an E4XT **one-shot** — the note stops sustaining. Nothing in the model or
README says the E4B target cannot represent this; E4B has a loop/no-loop bit
only, so the closest mapping is `FORWARD`, not "drop it".

Not tracked in `TODO.md` (grep `FORWARD_REL` → no rows).

---

## 5. §SILENTFAIL is incomplete — the AKAI path ignores `n_parse_failed`

**File:** `convert.py:1199-1204` promises the exit code:

```python
print(f"\n  [WARN] {n_parse_failed} input file(s) FAILED to parse and are "
      f"not in this run's output. This run will exit {RC_PARTIAL}.")
```

but the AKAI branch (`convert.py:1576-1579`) returns from `main()` using only
the writer's return code:

```python
_rc = write_akai_output(output_banks, out_dir, bank_name, args, step_n)
if _rc:
    sys.exit(_rc)
return
```

`write_akai_output` also returns `None` on its `--add-to` path
(`convert.py:495`) and its "nothing to write" path (`convert.py:428`). The
single-file path computes
`partial = (n_parse_failed + n_write_failed + n_append_failed) > 0` at
`convert.py:1811` and exits 4; the AKAI path never sees `n_parse_failed`.

**Verified end-to-end.** A directory with one good `.sfz` and one corrupt
`.e4b`, `--format akai`:

```
[WARN] 1 input file(s) FAILED to parse and are not in this run's output.
       This run will exit 4.
Done: 1 of 1 volume(s) written to out/
rc = 0
```

The identical run with `--format e4b` exits 4. This is the same shape
`TODO.md:37` (§SILENTFAIL) claims closed — the fix propagated the parse count
to the summary but not to the AKAI early return.

---

## 6. `--auto-loop-dump-dir` writes a stereo sample as a mono WAV

**File:** `processors/single_cycle.py:405`, reached from
`processors/auto_loop.py:484-477` → `_dump_loop`

```python
fmt = struct.pack('<HHIIHH', 1, 1, sr, sr * 2, 2, 16)   # PCM, mono, 16-bit
```

`_auto_loop_sample` preserves `sample.channels` (`auto_loop.py:394` sets only
loop fields), so a stereo sample arrives here with interleaved bytes.

**Verified.** A 1.0 s stereo pad, auto-looped with `dump_dir` set: the dumped
`Pad_C4.wav` reports `channels=1 frames=88200 rate=44100`. It **plays 2.0 s —
an octave down** — and the embedded `smpl` loop (10825–35280, which are
*stereo-frame* indices) points at half the intended position.
`_dump_cycle` (single-cycle) is safe because it always sets `channels=1`.

Not tracked in `TODO.md`.

---

## 7. `--shrink-by 100` / `--shrink-to 0` → unhandled `ZeroDivisionError`

**File:** `processors/shrink_planner.py:498` and `:520`

`--shrink-by` has no range validation, unlike `--reduce-key-zones` /
`--reduce-velocity-layers` (validated at `convert.py:1077-1081`). With
`by_pct=100`, `shrink_planner.py:498` gives
`tgt = int(cur * (1.0 - 100/100)) = 0`, the plan is infeasible, and
`shrink_planner.py:520` divides by it **inside the f-string that is supposed
to report the unreachable target**:

```python
f"{over/1024:.0f} KB over ({plan.est_bytes/tgt*100-100:.0f}%). "
```

**Verified.** `convert.py in/t.sfz --format e4b --shrink-by 100` →
`ZeroDivisionError` traceback, exit 1. Nothing is written (it crashes in
step 2), so it is not audio loss — but it is a raw traceback on a plausible
user value, and `--shrink-to 0` does the same. `by_pct > 100` produces a
*negative* target and the record says "could not reach -0.04 MB … (130 KB
over)".

`shrink_bank(bank, by_pct=)` is a documented VinSamLib-facing API
(`TODO.md:7726`), so the same crash is reachable in-process.

Not tracked in `TODO.md`.

---

# MAJOR

## 8. EIII: chunk/area size computed from the *buffer*, not the *bytes written*

**File:** `writers/eiii_writer.py:701-702, 730-731, 945-946`

```python
num_frames  = len(pcm) // 2
channel_size = num_frames * 2          # even-truncated
...
data[offset + SAMPLE_HEADER_SIZE:offset + SAMPLE_HEADER_SIZE + channel_size] = pcm
return SAMPLE_HEADER_SIZE + channel_size
```

```python
sample_area_size = sum(SAMPLE_HEADER_SIZE + len(p[1]) for p in prepared)   # len(pcm), NOT channel_size
size = EMPTY_BANK_SIZE + preset_area_size + 1 + sample_area_size
```

`data[a:b] = pcm` with `len(pcm) > b-a` **inserts** into the bytearray instead
of raising. Consequences, all verified with three mono samples of 101, 99 and
100 bytes:

- the file is **N bytes longer** than the layout the bank header describes
  (one per odd-length sample) — writer reports `Sample [001] 'ODD1': 101 bytes
  PCM`, file is **12000** bytes, layout says **11998**;
- the *following* sample's header is written at the logical `offset`, which is
  one byte **before** where the previous sample's PCM actually ends — so the
  previous sample's trailing PCM byte is overwritten by the next sample's
  name. Confirmed `d[11613] == 0x4F` (`'O'` of `"ODD2"`) sitting where `ODD1`'s
  101st PCM byte belongs;
- `BANK_NEXT_SAMPLE` (line 986) and `BANK_*_BLOCKS` (lines 989-993)
  under-report the area actually present.

Reading back gives 100/98/100 bytes. Mitigating: `_prepare_sample_pcm` zeroes
the last 4 bytes (lines 672-675), so the clobbered byte is usually 0 — audible
loss is nil. The size/offset disagreement and the cross-sample overlap are
unconditional.

**This is the third writer with this defect class.** `TODO.md` §HALFFRAME
(line 39) fixed it for `e4b_writer` (`_pcm_bytes_written`) and `krz_writer`
(`_pcm_words_written`), but only for the stereo `len % 4 == 2` half-frame.
EIII has no such helper and a *different* trigger: an odd **byte** length.
§HALFFRAME names only the two writers and only the stereo half-frame, so this
is unmentioned.

---

## 9. KRZ `_write_sample_object` does not clamp loop points against the PCM it writes

**File:** `writers/krz_writer.py:558-559, 582-584, 590-591`

```python
loop_start_w = sample.loop_start
loop_end_w   = sample.loop_end if sample.loop_end > 0 else num_words - 1
...
abs_loop_end   = word_offset + loop_end_w
abs_end        = word_offset + num_words - 1
sample_end_field = abs_loop_end   if looped else abs_end
```

Contrast `writers/e4b_writer.py:509-513`, which clamps **and re-tests**
`has_loop` after the clamp:

```python
if sample.loop_end > n_frames:
    sample = replace(sample, loop_end=n_frames)
has_loop = sample.loop_end > sample.loop_start
```

**Verified:** a 64-frame mono `FORWARD` sample with `loop_end = 64` — the
model's "loop to the very end" value, since `loop_end` is exclusive in this
model per `e4b_writer.py:524` and `parsers/e4b_parser.py:376` — makes
`krz_writer` emit `end_w = 64` when the last valid word index is 63.
`loop_end = 100` emits `end_w = 100`.

Because the K2000 defines the loop as `[sampleLoopStart, sampleEnd]` and
`sampleEnd` *is* the sample end for a looped sample (CR-10), the machine loops
one word into the **next sample's PCM** on every cycle.

**Reachability caveat, stated honestly:** all three of this project's parsers
clamp `loop_end ≤ n_frames−1` (`e4b_parser.py:376`, `krz_parser.py:2017`,
eiii's `hi = max(6, num_frames-7)`), so an *ours-only* pipeline cannot produce
it today. A source that sets `loop_end ≥ n_frames` directly (SFZ / WAV `smpl` /
XPM) can. Severity is input-gated.

---

## 10. E4B one-sided clamps on zone/key bytes crash the whole write

**File:** `writers/e4b_writer.py:656-659` and `:693`, `:1136-1139` (voice
window, same shape)

```python
entry[2]  = min(127, zone.lo_key)      # no max(0, ...)
entry[5]  = min(127, zone.hi_key)
entry[6]  = min(127, zone.lo_vel)
entry[9]  = min(127, zone.hi_vel)
# entry[14] = min(127, zone.root_key)
```

**Verified:** a preset with one zone `lo_key=-5, hi_key=200` → `write_e4b`
raises `ValueError: byte must be in range(0, 256)` on the very first zone
entry. `krz_writer` and `e3x` handle the same input fine (KRZ guards with
`if not 0 <= entry < NUM_KEYS: continue`; EIII clamps to
`LOWEST_KEY`/`HIGHEST_KEY`).

**Reachable:** `parsers/xpm_parser.py:1911` —
`lo_key = int(_get_text(instrument, 'LowNote', '0'))` passes any integer a
source file carries straight into the model.

---

## 11. SFZ `key=` is a fallback only — never overrides the group's `lokey`/`hikey`

**File:** `parsers/sfz_parser.py:495-504`

```python
# key= is SFZ shorthand for lokey=hikey=pitch_keycenter=
key_shorthand = merged.get('key')
lo_key  = _note_name_to_midi(merged.get('lokey', key_shorthand or '0'))
hi_key  = _note_name_to_midi(merged.get('hikey', key_shorthand or '127'))
```

`key=` is read only as a **fallback**, so a region-level `key=48` never
overrides the group's `lokey=0 hikey=127` — violating the merge the code
itself asserts at line 407 (`# Merge: global < group < region`). Per SFZ,
`key=` *is* `lokey=hikey=pitch_keycenter` and region beats group.

**Verified end-to-end.** `<group> lokey=0 hikey=127` +
`<region> sample=C.wav key=48`:

```
g.sfz:  [('A', 0, 127, 36), ('C', 0, 127, 48)]   <-- hi_key 127, WRONG
r.sfz (no group): [('A', 36, 36, 36), ('C', 48, 48, 48)]   <-- correct
```

and through the real CLI + E4B writer + parser:

```
$ python3 convert.py g.sfz --format e4b --overwrite --output-dir kz
  [WARN] preset 'g': zone 0-127 plays past the E4XT's rate ceiling above key 81
$ (read back)  zone C lo 0 hi 127 root 48
```

So a one-key region ships as full-range, invites a false up-pitch warning, and
loses its key span in every output format. `TODO.md` has no SFZ-precedence row
(`grep -n "lokey\|hikey" TODO.md` → 0 hits).

---

# MINOR

## Parsers

### m1 — `parsers/exs24_parser.py:279-285` — v1.1 chunk-walk guard is too tight
The guard ensures only 8 bytes but the handler unpacks at `offset+8`:
```python
while offset + 8 <= len(data):                       # only 8 bytes guaranteed
    chunk_type = struct.unpack_from('<I', data, offset)[0] & ~_V11_TYPE_FLAG
    ...
    if chunk_type == CHUNK_ZONE_V11:
        z_idx = struct.unpack_from('<I', data, offset + 8)[0]      # needs offset+12
```
Compare lines 609-610 and 649-650, where the classic walk does
`if offset + 104 > len(data): break` and `if base + 48 > len(data): break`.
**Verified:** an 88-byte v1.1 file whose last 8 bytes are a zone-chunk header
raises `unpack_from requires … 92 bytes`.

### m2 — `parsers/gig_parser.py:146` — off-by-one in its own bounds guard
```python
'layer': struct.unpack_from('<H', data, off+10)[0] if len(data)-off > 10 else 0,
```
`len(data) == off+11` passes the guard but `unpack_from('<H', …, off+10)` needs
`off+12`. **Verified:** `_parse_rgnh(b'\x00'*11, 0)` → `struct.error`. The
guard should be `>= 12` / `> 11`.

### m3 — `parsers/gig_parser.py:213-221` — `_parse_smpl` loops over `cSampleLoops` unbounded
No bound against the chunk or the file → `struct.error` on a short `smpl`
chunk. **Verified:** a 36-byte `smpl` body with `cSampleLoops = 0xFFFF` (a
plausible malformed/absent-loop record) reads at `off+44` and raises.

### m4 — `parsers/gig_parser.py:178` — `ulLength == 0` becomes an inverted loop
```python
'end': loop_start + loop_length - 1,   # ulStart+ulLength-1 = inclusive end
```
A WLOOP with `ulStart=5000, ulLength=0` yields `loop_start=5000,
loop_end=4999`. That pair lands in `SampleData` and is carried by both writers
(`krz_writer._write_sample_object:559` keeps `loop_end_w = 4999` and writes
`loopStart > loopEnd`). **Verified.**

### m5 — `parsers/mpc60_parser.py:180` — `_fat12_read_set` indexes `ent[11]` unguarded
```python
ent = img[root_off + e*32: root_off + e*32 + 32]
if ent[0] in (0x00, 0xE5) or (ent[11] & 0x08):
    continue
```
`_fat12_extensions` (line 241) does `if len(ent) < 32 or …` on the identical
walk. A truncated image therefore raises `IndexError` **before** the "this is a
Kurzweil K2000 floppy image" diagnosis (lines 211-214) is reached, so the
helpful error is lost. **Verified** with a 1.44 MB boot sector truncated to
9,728 bytes.

### m6 — `parsers/pgm_parser.py:439-467` — `_parse_mpc2000` has no length validation
Unlike `_parse_mpc1000` (line 190: `if len(data) < _FILE_SZ`), every
`data[o:…]` slice silently truncates and every `data[o]` /
`struct.unpack_from` past the end raises. **Verified:** a 2-byte `07 04` file
(which `parse_pgm`'s dispatcher at line 165 accepts) → `struct.error` at
offset 2; a file declaring 5,000 samples in 40 bytes → `IndexError`; a
well-formed header truncated mid-pad-block → `IndexError`.

### m7 — `parsers/eps_parser.py:733-734` — uniquifier `while` loop cannot make progress
```python
nm = f"{inst['name'][:11]}{len(seen_names) % 100000:05d}"
while nm in seen_names:
    nm = f"{nm[:11]}{len(seen_names) % 100000 + 1:05d}"
```
`len(seen_names)` is constant inside the loop body, so if both
`prefix+len%100000` and `prefix+len%100000+1` are taken the loop re-derives
the *same* string and hangs. Reached once the modulo wraps, i.e. ≥ 100,001
sample names in one `parse_eps_image` call — **latent**, not live on the
reference disc's 2,681 names. **Verified** by isolating the expression and
seeding the collision.

### m8 — `parsers/e4b_parser.py:165-166` — duplicate key in a table literal
`0x68: 3` appears twice in `_E4B_TO_XPM_FILTER_TYPE` (once inside the Morph
family group at 165, once on its own annotated line at 166). Harmless (same
value, last binding wins), but dead/contradictory code and the annotation
reads as if it were the only entry. **Verified** by parsing the literal:
1 duplicate key, 21 literal entries, 20 dict entries.

### m9 — `parsers/e4b_parser.py:517` — the `mod_region` guard is unreachable
```python
mod_region = data[VOICE_MOD_OFF:VOICE_MOD_OFF + 80] if len(data) >= VOICE_MOD_OFF + 27 else b''
```
`VOICE_MOD_OFF + 27 = 217`, but the function's own length check at line 407
already requires `len(data) >= VOICE_FIXED = 284`. The `b''` branch can never
execute, so what reads like a bounds guard is not one. **Verified** by
arithmetic and by importing the constants.

### m10 — `parsers/xpm_parser.py:611` — `n_actual` computed and never used
Line 616 recomputes the same quantity correctly as `n_frames_loaded`. The
`channels == 1` special case at 611 is also wrong for any channel count > 1.
Dead variable, no behavioural effect.

### m11 — `parsers/akel_image_parser.py:372` — `_read_harddisk` reads past the acceptance test's coverage
```python
partnum = min(data[_OFF_PARTTAB + 0x100], MAX_PARTITIONS)   # offset 0x4500 = 17664
```
`read_aksi_image`'s only gate is `_has_parthead_magic(data[:0x200])`, which
needs **202** bytes. A 202…17,663-byte file carrying the magic therefore
raises `IndexError` instead of the clean `"is not an AKAI disk image — the
partition header magic is missing"` `ValueError` at line 303. **Verified:** a
512-byte file with the 98-magic-field pattern passes the gate then
`IndexError`s.

### m12 — `parsers/sfz_parser.py:244` — tremolo LFO *shape* read from the wrong block
The rate is resolved from whichever field supplied it (`amplfo_freq` /
`lfo03_freq` / `lfo02_freq` / `lfo01_freq`, line 240), but the shape is
hard-wired to `lfo02_wave` even when the gain came from `amplfo_depth` or
`lfo01_gain` and the slot allocated is the free LFO2. Result: a v2 SFZ tremolo
carried by `lfo01_gain` reports `'sine'` regardless of `lfo01_wave`. The LFO1
branch two lines below *does* read `lfo01_wave`, which makes the asymmetry look
deliberate when it is not.

### m13 — `parsers/roland_s7xx_parser.py:293` — `roland_fine_tune` floors where it should truncate
```python
return (v * 64 + 32) // 100
```
For `v = -1`, `(-64+32)//100 == -1` instead of `0`; for `v = -2`, `-1`
instead of `0`. Floor division breaks the sign symmetry the docstring claims.
Off by 1.5625 cents on small negative values only.

## Writers

### m16 — `writers/krz_writer.py:1900` — comment repeats a withdrawn derivation
```python
_KRZ_RELEASE_FACTOR = KRZ_RELEASE_FACTOR   # = 2.63 / 1.39
```
**Verified:** `writers.krz_writer._KRZ_RELEASE_FACTOR == 3.65` and
`models.common.KRZ_RELEASE_FACTOR == 3.65`, while `2.63/1.39 == 1.892`. The
value was recalibrated 2026-09-18 and `models/common.py:4207` says so in its
own words: *"**RECALIBRATED 2026-09-18 ON HARDWARE, 1.9 -> 3.65, AND CONFIRMED
BY EAR.**"* The trailing comment repeats the withdrawn derivation, so a reader
of the writer sees the old factor as current. `docs/KRZ_FORMAT.md:818`
(`_KRZ_RELEASE_FACTOR = 1.9`) is the same stale number. The recalibration
itself is tracked (`TODO.md:60`); the stale comment and doc line are not, and
`tests/test_docs_constants_agree.py` cannot see either (its `WATCHED` list
covers `models.common` only, and `_KRZ_RELEASE_FACTOR` is private +
two-module).

### m17 — `writers/krz_writer.py:1237` — `_thin_velocity_bands`'s `_terr` on a possibly-empty zone list
```python
def _terr(v):
    return (min(z.lo_key for z in v.zones), max(z.hi_key for z in v.zones))
```
**Verified by direct call:**
`_thin_velocity_bands([VoiceLayer(zones=[]), VoiceLayer(zones=[])], 3)` →
`ValueError: min() arg is an empty sequence`. The sibling helpers in the same
file are written defensively — `_thin_velocity_voices` (1170-1173) uses
`default=0` / `default=127`, and `_voice_span` (1008) uses
`... if zs else (0, -1)`. **Not reachable through `write_krz`** (an
empty-zones voice reports the full key range, so `_voices_stacked` at 3890 is
always True and `_spread_pick` fires first — verified with a 5-voice preset
containing one empty voice). Latent inconsistency only.

## Processors / CLI

### m18 — `processors/single_cycle.py:256` — shrink percentage against a channel-blind frame count
`'orig_frames': len(sample.data) // 2` — no `// ch`, while the same file
computes frames correctly at line 333 (`(len(sample.data) // 2) // ch`) and
`auto_loop.py:333` does too. **Verified:** a stereo sample of 11,025 frames
reports `orig_frames=22050` → prints `-98.2%` instead of `-96.4%`; for very
short samples the percentage goes negative (`-136.4%`) because the
hardware-minimum loop exceeds the source. Report-only.

### m19 — `convert.py:852` — `--jobs 0` / negative → raw `ValueError`
`--jobs` is declared a bare `int` with no validation;
`processors/parallel.py:84` passes it straight to `ProcessPoolExecutor`.
**Verified:** three samples + `--single-cycle --jobs 0` →
`ValueError: max_workers must be greater than 0`, traceback, exit 1. With a
single sample the `total <= 1` serial branch masks it. Zero test coverage
(`grep -rn -- "--jobs" tests/` → 0 hits).

### m20 — `convert.py:1131` — `--output-dir /dev/null/x` → unhandled `NotADirectoryError`
**Verified:** raw `NotADirectoryError: [Errno 20] Not a directory:
'/dev/null/x'`, exit 1, from `out_dir.mkdir(...)`.

### m21 — `convert.py` / `README.md` document the pre-2026-09-13 `--trim-start` default
`convert.py:906-909` still says a sample whose loop starts in the trimmed
lead-in *"has that loop DROPPED so the result is a clean one-shot — see
`--trim-start-keep-loops`"*, but `--trim-start-keep-loops` is now
`argparse.SUPPRESS` and the code passes `drop_full_loop=args.trim_start_drop_loops`
(default `False`, `convert.py:1246-1247`), i.e. loops are **kept**. Same
contradiction in `README.md:1557-1559` and `README.md:1589-1591`; the README's
own option table (`README.md:780-784`) states the correct current default, so
the file contradicts itself. `tests/test_readme_options.py` only checks flag
presence, so nothing catches it. Direction of harm is "believes the destructive
thing is default", not the reverse, so MINOR.

### m22 — `info_cmd.py:166` — `data = open(path, 'rb').read()`
Closes on CPython refcount, but not a `with`. Cosmetic.

### m23 — undocumented CLI acceptances
`--max-sample-rate -5` is silently treated as *unset* (`max_sr > 0` false,
`max_sr < 0 and format=='krz'` → headroom-aware path) — benign but
undocumented. `--max-sample-rate 1` is accepted and downsamples every sample to
1 Hz, output 0.00 MB — no lower sanity bound. `--lfo-sync-bpm 0` / negative is
accepted (`xpm_parser.py:111` clamps to `[0.08, 18.01]`). `--hda-size 0` /
`-5` is accepted (only the 20,000-over-limit case exits 2).

---

# TEST SUITE

Suite state verified before reporting:
```
$ python3 -m pytest tests/ -q
1417 passed, 1469 subtests passed in 135.30s
```
No skips, no xfails. A second shuffled-file-order run also passed
1417/1469 (order-independent).

## T1 — a tautological test that never touches the code it names 🔴

**File:** `tests/test_review_2026_10_02.py:65-81`

```python
    import parsers.gig_parser as G          #  <-- imported, then NEVER used
    warned = set()
    out = io.StringIO()
    for lo, hi in ((36, 48), (36, 48), (60, 72)):
        with contextlib.redirect_stdout(out):
            if hi != lo and (lo, hi) not in warned:      # the TEST re-implements
                out.write(f"[WARN] {lo}-{hi}\n")         # the post-fix logic
                warned.add((lo, hi))
    text = out.getvalue()
    assert text.count('[WARN]') == 2, text
```

The docstring says *"The flag became a set keyed on `(key_lo, key_hi)`"*, but
nothing in `parsers/gig_parser.py` is called. **Verified:** stubbing
`sys.modules['parsers.gig_parser']` with a module that raises on any attribute
access leaves the test **green** — it cannot fail on any implementation,
including the single-boolean bug it names. (`G` is dead.)

Not tracked in `TODO.md`.

## T2 — an assertion that collapses to a near-tautology 🔴

**File:** `tests/test_akai_authored_zero_and_collisions.py:71-75`

```python
    a, d, s, r = akai_env_bytes(e, quiet=True)
    assert r == 45 or r > 10, 'a missing release lost its default'
    assert d == 50 or d > 10, 'a missing decay lost its default'
```

`r == 45 or r > 10` is logically just `r > 10` (45 already satisfies it);
likewise for `d`. **Verified by execution:** the real bytes are
`release=56, decay=67`, so the test passes — but so would 11, i.e. a
fast-but-wrong release. The docstring says the point is *"None means the source
said nothing and the factory value is correct"*, which this cannot catch. A
regression to `release=None → RELSE1 12` passes silently. The test above it
(`test_an_instant_release_stops_dead`, line 34, `assert ... [3] == 0`) is
exact, which makes the contrast obvious.

## T3 — an assertion-free test 🟡

**File:** `tests/test_diagnostics.py:102-109` — the only `def test_` in the
tree with no `assert` and no `pytest.raises`; it relies entirely on
`json.dumps` raising, and on `diags[0]` raising `IndexError` if nothing was
emitted. Non-vacuous by accident rather than by construction.

## T4 — untested seams 🟡

| Seam | Status |
|---|---|
| `info_cmd.run_info` / `_sniff_format` (`info_cmd.py`, ~450 LOC) | **0 references in `tests/`.** Ran `convert.py t.sfz --info` by hand; it works, but nothing guards it. |
| `parsers/talsmpl_parser.write_talsmpl` ↔ `parse_talsmpl` | Only `tests/release_matrix.py:198-212` touches it, and `pytest --co` reports **0** tests from that file (it is a `main()` harness, not a `test_*.py`). Ran the round-trip manually; it works, so the seam is real and live but unchecked. |
| `--add-to` for e4b/krz/eiii → `iso_builder.k2000_disk_append`, `emu_hdd_append`, `hda_builder.fat_hda_append` | The only pytest coverage is `test_silent_failures.py:254-283`, which shims **all four** append entry points to `raise`. The real FAT32/FAT16 append path is exercised only by `release_matrix.py` (uncollected). AKAI is the exception: `test_akai_image.py:409-540` exercises `append_akai_volumes` for real. |
| `parsers/*.py ↔ writers/*.py` round-trips | **Covered.** E4B, KRZ, EIII, AKAI all have round-trip tests. Clean. |
| `diagnostics_catalog` contract | **Covered and in sync** — `python3 diagnostics_catalog.py` is byte-identical to `docs/diagnostics.json`, 3 tests. |
| `convert.py` error paths / exit codes | **Covered** (`test_silent_failures.py`, incl. mutation checks); README §Exit codes verified against the 25 `sys.exit()` sites. |
| opcode precedence inside `parse_sfz` | **Untested** — `tests/test_lfo_volume.py` is the only `parse_sfz` caller and only ever emits `<region>` blocks; no test puts a `key=` in a region under a `<group>` that also declares `lokey/hikey`. (This is the gap that let finding 11 through.) |

---

# CROSS-CUTTING ROBUSTNESS

## Clean, and verified rather than assumed

**Exception handling.** An AST scan of the whole tree for single-statement
`Pass`/`Continue` handlers found **23, none inside a per-item loop**. All are
narrow (`ValueError`, `OSError`, `SyntaxError`, `struct.error`) with a defined
local fallback. The broad ones are deliberate and documented:
- `parsers/gig_parser.py:409` → `return defaults` (`{'attack':0.001,'decay':0.3,...}`)
- `writers/iso_builder.py:681,700` → `return {}` / `return dict(out)`, docstring *"Deliberately tolerant … must not stop an image being built"*
- `writers/krz_writer.py:2014-2016` → `return None` (unparseable sample → "does not decay")
- `parsers/mpc60_parser.py:244` → `pass` in `_fat12_extensions`, whose docstring says it *"runs on the failure path, so a malformed directory must not replace the real error with its own"*
- `convert.py:389-391` catches per-file and **counts** (`n_failed`), exit 4 — and is mutation-tested.

**Nothing hides one bad sample as zero samples.**

**Resource leaks.** The only `ProcessPoolExecutor` is inside a `with`
(`processors/parallel.py:84`); no `multiprocessing.Pool` anywhere.
`Fat12/Fat16/Fat32/EpsImage/RolandImage` all expose
`__enter__/__exit__`/`close()`; all 12 call sites use `with`.
`writers/atomic.py:78-84` catches `BaseException` and unlinks — correct for
Ctrl-C.

**Path traversal — properly handled.** `--bank-name ../evil`, `..`,
`/tmp/pwned`, `A/B`, `....` → all sanitised (`_EVIL_01.E4B`, `_01.E4B`,
`_TMP_PWNED_01.E4B`, `A_B_01.E4B`); **no file escaped `--output-dir`**.
`--folder '../../evil'`, `A/B`, `/abs` on `--add-to` → confined to the image.

**Read-only output dir — exemplary.** `[ERROR] … Permission denied: '…/*.part'`
→ `[WARN] 1 bank(s) FAILED to write …` → `PARTIAL: …` → **exit 4**.

**Refused with a message (exit 1/2):** `--bank-size -5`,
`--reduce-key-zones 150`, `--auto-loop 0`, `--single-cycle 0`,
`--mono bogus`, missing `--add-to` image.

**Determinism — verified, not assumed.** Byte-identical output across
`PYTHONHASHSEED=0/1/3/5/7/777/12345/999/4242` for `e4b`, `krz`, `eiii`,
`--iso`, `--hda`, `--floppy`, `--from-samples`, and
`--auto-loop --trim --single-cycle`. Multiprocessing result ordering:
`--jobs 1` vs `--jobs 4` under `--resample emax1` → identical md5
(`9e392416…`), so `map_over_banks`' scatter (`parallel.py:92-96`) is
order-correct.

**Test-suite hygiene.** `conftest.py:35-67` pins
`--basetemp ~/temp/pytest-mpc2emu` **and** `tempfile.tempdir`;
`tests/test_law_consistency.py:611-665` guards both. **Measured:** full suite
run → `comm -13 before after` on `~/temp` = **0 new entries**.
`tests/test_no_scratch_leaks.py` enforces the rule by AST and mutation-checks
itself against a planted corpus. No order dependence.

⚠ **False positive avoided:** `/tmp/fat16-{__sabwxc,u14lktkh,wpocomf1}/disk.hda`
(3 × 1 GB) is **not** mpc2emu — `/tmp/repro/t_fat16.py:5` does
`sys.path.insert(0, "/home/lentferj/git-repos/VinSamLib")` +
`mkdtemp(prefix="fat16-")`. mpc2emu contains no such prefix.

## Documentation/code agreement — 10 sites hand-verified

| Site | Comment claim | Code | ✓/✗ |
|---|---|---|---|
| `CLAUDE.md` → `bank_splitter.py:108,111` | 1000 samples / 1000 presets | both `1000` | ✓ |
| `CLAUDE.md` → `convert.py:1061` | e4b max bank 128 MB | `_hw_limits e4b 128` | ✓ |
| `models/common.py:1040` | `625000/44100 = 14.17`, `2^(46/12) = 14.25` | 14.1723, 14.2544 | ✓ |
| `models/common.py:1206-7` | `19.4932/2.828 = 6.892`, `19.4932/3.464 = 5.627` | 6.8929, 5.6274 | ✓ |
| `writers/akai_s3000_writer.py:749` | `4.368 * (127-64.56)/1200 * 9.76` | 2.2183 vs `_AKAI_VELFILT_FILFRQ_PER_UNIT = 2.22` | ✓ |
| `models/common.py:943` | `99 * 0.11913 = 11.79` | 11.7939 vs `AKAI_LFO2_RATE_HZ_PER_UNIT = 0.11913` | ✓ |
| `models/common.py:6421` | `0.07206 / 0.05841 = 1.2337` | 1.23369 | ✓ |
| `writers/e4b_writer.py:951,739` | `97.82/60 = 1.630` | `_ENV_FULL_SPAN_DB = 97.82`, 1.6303 | ✓ |
| `parsers/eps_parser.py:374-375` | code 21 → 29 800 vs `625000/21 = 29 762` | `EPS_RATE_TABLE[21] = 29800`, 29761.9 | ✓ |
| `eiii_writer.py:192` / `e4b_writer.py:1158` | device −24..+24 / transpose −72..+24 | `max(-24,min(24,…))`, `max(-72,min(24,…))` | ✓ |

An automated pass also extracted **699** module-level numeric constants from
37 modules and checked every `` `NAME = value` `` claim in the README and 20
`docs/` files; 17 claims checked, 2 flagged (1 false positive — the m16 stale
`_KRZ_RELEASE_FACTOR` comment above).

---

# EXECUTION SPEED

**Environment:** Python 3.11.2, Linux, 12 cores. Benchmarks under
`/tmp/opencode/` (nothing in the repo was modified). Every "before" is the
**shipped code timed directly** — each function was re-implemented verbatim
first and the timings confirmed to agree with the repo's own before anything
was claimed about it. Where a change could not be made byte-identical, that is
said.

**Realistic inputs:** 4 s of 44.1 kHz 16-bit PCM (352,800 B mono / 705,600 B
stereo — two partials plus noise, not a constant); banks of 8–200 samples;
60–100 presets × 4 voices with real mod cords.

## 1. The two quantizers are the hottest loops in the project — 1.6–1.7× each, byte-identical

`cProfile` over `resample_vintage` on 4 s of 44.1 kHz mono puts
`_mu_law_quantize` at **0.438 s tottime / 0.811 s cumtime out of 1.275 s
total (64 %)** for the EII profile, and `_quantize` at 0.324/0.674 s out of
1.195 s for EMAX. The cause is the same in both: per element the loops pay
global-name lookups for `math.log1p`/`math.expm1`/`math.floor`/`round`,
attribute lookups for `rng.gauss`, builtin `min()`/`max()` calls for a clamp
that is two conditional expressions, and a `list.append` looked up each time.

For `_mu_law_quantize` there is one more structural fix: the *expand* step
takes only 256 distinct values (it is a function of the quantised code `q`, an
integer in −128..127), so it can be tabulated once — the table entries are
produced by the **identical expression**, so they are bit-for-bit the same
floats.

**File:** `processors/resampler.py:446-491` and `:396-443`

```
_mu_law_quantize  (EII: 8-bit, µ-255, truncate, +noise)  176400 values
  repo (shipped)                 366.11 ms
  verbatim copy of the source    360.91 ms     <- confirms the baseline
  hoisted + 256-entry expand     222.22 ms     1.65x   BYTE-IDENTICAL
_quantize        (EMAX: 12-bit, round+dither+noise)      176400 values
  repo (shipped)                 349.76 ms
  verbatim copy of the source    343.10 ms
  hoisted + conditional clamp    214.99 ms     1.60x   BYTE-IDENTICAL
_quantize, truncate/no-dither/no-noise branch (the arithmetic alone)
                                      96.61 ->  32.52 ms     2.97x   BYTE-IDENTICAL
```

Byte-identity was verified on the full 176,400-value lists for the truncate
path, the round path, with and without noise, at 8-bit and 12-bit. The
remaining floor is `rng.gauss` — measured separately at **122 ms for 176,400
calls (34 % of the old loop)**, and it cannot be replaced without changing the
RNG sequence and therefore the output bytes.

The µ-law expand table costs 0.071 ms to build for 256 entries — amortised
over 111,108 values.

**Verified at the function level, at the shipped API, and through the real
worker pool:**

```
resample_vintage, 4 s/sample, workers=1, best of 3
  EMULATOR_II mono     417.98 -> 294.81 ms   1.42x   PCM identical
  EMAX_I      mono     409.28 -> 305.46 ms   1.34x   PCM identical
  EMULATOR_II stereo   875.68 -> 641.40 ms   1.37x   PCM identical
  EMAX_I      stereo   864.50 -> 658.90 ms   1.31x   PCM identical

resample_banks, workers=6  (8 x 3 s stereo)   <- the path a conversion takes
  emulator2     1413.21 -> 1093.93 ms   1.29x   PCM sha256 79a3bd76b5859cee ==
  emax1         1413.21 -> 1097.57 ms   1.29x   PCM sha256 edea9c481d5f76b0 ==
resample_banks, workers=1
  emulator2     5185.09 -> 3984.45 ms   1.29x   identical
  emax1         5185.09 -> 4066.24 ms   1.28x   identical
```

⚠ An earlier run of this benchmark reported 1.08×; that run built the bank
*inside* the timed call. Corrected: with the bank built once outside, the gain
is 1.29× and is the same serial and parallel.

## 2. `auto_loop` rebuilds sliding-window statistics per frame — 2.7×, byte-identical

`processors/auto_loop.py:115-121` `_windowed_rms` calls
`max(0, f + 1 - win)` **twice per frame** — 352,833 `max()` calls for one 4 s
sample — and does two `pre[...]` indexings. The `max()` is invariant: for
`f < win-1` it is 0, and from there on it is `f + 1 - win`. Splitting the
comprehension at that point and using `zip(pre[win:], pre)` for the steady
part removes both.

`processors/auto_loop.py:180` `_modulation`'s autocorrelation is
`sum(e[j]*e[j+lag] for j in range(n-lag))` — 575,505 generator iterations for
one sample, where `sum(map(mul, e[:n-lag], e[lag:]))` does the same
left-to-right sum in C. This is the exact substitution the module already
documents for `_match_cost` ("measured 1.8x"); it generalises.

```
_windowed_rms (win=3528, n=176400)
  repo                       132.56 ms
  split head/steady + zip     48.60 ms    2.73x   BYTE-IDENTICAL
_modulation envelope build (win=176, hop=88)
                              25.61 -> 18.21 ms    1.41x   BYTE-IDENTICAL
_modulation autocorrelation (315 lags x ~2003 env frames)
                              66.61 -> 26.13 ms    2.55x   BYTE-IDENTICAL
_auto_loop_sample, 4 s
  mono                       358.76 -> 227.15 ms   1.58x   PCM + info dict identical
  stereo (456.10) -> 318.64 ms                    1.43x   PCM identical
```

The `info` dict and the chosen loop points (18834..168415, cost 0.004300) are
identical, so the loop *decision* is unchanged, not just the audio.

## 3. The trim stages carry the same two defects — 1.5–1.6×, byte-identical

`processors/tail_trim.py:90-120` `_windowed_ms` is 76 % of `_trim_tail_sample`.
It builds the prefix sum in a Python loop, then does
`pre[f+1] - pre[max(0, f+1-win)]` with a `max()` and two indices per frame.
`itertools.accumulate(energy, initial=0.0)` is bit-identical to that loop (same
left-to-right order, which the function's own comment already relies on for
`auto_loop._windowed_rms`), and splitting at `win-1` removes the `max()`.

`processors/tail_trim.py:70-87` `_frame_energy` for stereo is a **nested double
loop with index arithmetic** over every interleaved sample (78 ms for a 4 s
buffer) — `zip(sig[0::2], sig[1::2])` over the two planes replaces it.
`(l*l + r*r) * 0.5` is exactly `s / channels` for `channels == 2` (division and
multiplication by a power of two are both exact), so this is bit-identical,
unlike a general channel count.

```
_windowed_ms  (mono or stereo, n=176400, win=882)
  repo                       103.54 ms
  accumulate + split/zip      65.79 ms    1.57x   BYTE-IDENTICAL
_frame_energy stereo (n_frames=176400)
  repo (nested loop)          78.09 ms
  zip of the two planes       29.31 ms    2.66x   BYTE-IDENTICAL

_trim_tail_sample 4 s     mono  148.00 -> 115.69 ms  1.28x  PCM identical
                          stereo 234.39 -> 151.66 ms  1.55x  PCM identical
_trim_start_sample 4 s    mono  151.97 -> 114.46 ms  1.33x  PCM identical
                          stereo 237.11 -> 153.69 ms  1.54x  PCM identical
```

## 4. E4B reader: 25–38 linear scans of a 20-slot table per voice — 1.46×

`parsers/e4b_parser.py` `_cord_slot` walks the 20 cord slots for every
`(src, dst)` query, and `_cord_amount_byte(dst, *sources)` calls it once per
source; `_gate_byte` walks it again; `_parse_voice` makes ~25 such queries per
voice. Each walk calls `len(mod_region)` **on every slot iteration** — 218,110
`len()` calls in one 400-voice profile.

```
_parse_voice x 240 (cord-rich: filter/env, velocity->filter, 2 LFO filters, 2 mod routings)
  current (per-query scan)     33.66 ms    (0.140 ms/voice)
  one (src,dst)->slot index    20.69 ms    1.63x   VoiceLayer objects == on every field
parse_e4b, 100 presets / 400 voices / 20 samples
  current                      59.30 ms
  slot index                   40.52 ms    1.46x   whole-Bank sha256 identical
parse_e4b, 20 presets / 80 voices
  current                      12.15 ms    -> 8.66 ms   1.42x   identical
```

Re-implemented by `inspect.getsource` + `exec` into the parser's own
namespace, then patched into `parsers.e4b_parser`, so `parse_e4b` /
`_parse_preset_body` ran the real path.

## 5. `krz_parser._pcm_extents` is quadratic in header count

`parsers/krz_parser.py:235-239`: `_next_start(after)` linearly scans the sorted
`starts` list for every header, so the whole function is **O(H²)** where
H = header count. `bisect.bisect_right` on an already-sorted list is the exact
same answer. Measured on the **real** start-word distributions taken out of
written `.KRZ` files:

```
headers   linear -> bisect   speedup   identical
  100     0.278 -> 0.130 ms   2.14x     yes
  400     2.930 -> 0.562 ms   5.21x     yes
  800    10.083 -> 1.072 ms   9.41x     yes   (KRZ caps at 800 samples)
parse_krz whole file, 400 samples
         23.30 -> 20.60 ms               1.13x   Bank hash identical
```

**Honest calibration:** a first micro-benchmark of this used adversarial starts
and claimed 12–22×; on real files the function is ~4 % of `parse_krz`, so the
**file-level** gain is 1.13×. The quadratic is real (4× cost per 2× headers,
measured 2.14 → 5.21 → 9.41) and the fix is a two-line `bisect` swap, but it
is not a headline number. KRZ cannot exceed 800 samples (object ids 200..999),
so the worst case is bounded at ~10 ms.

## 6. `models/common.py:357` inverts the cutoff table on every call — 1.64×

`e4xt_cutoff_position` does `pts = [(f, p) for p, f in _E4XT_CUTOFF_TABLE]` — a
fresh 17-tuple list — **per call**, and it is called once per voice from
`e4b_writer.py:1260`. This is precisely the "table rebuilt instead of cached"
shape, and the function's own docstring says the result depends on nothing but
the module constant.

```
e4xt_cutoff_position, 4000 calls
  current (rebuilds the table)   16.55 ms   (4.14 us/call)
  module-level inverted table    10.08 ms   1.64x   BYTE-IDENTICAL
```

Low absolute value (11.6 ms → 7.1 ms on a 2,800-voice corpus bank), but a
one-line, zero-risk hoist. Neighbouring candidates were checked too: `_interp`
5,120 calls = 0.65 ms, `e4xt_cutoff_hz_to_byte`'s 40-iteration binary search
1,600 calls = 0.008 s in a cord-rich 400-voice write — both below any bar worth
setting.

## 7. Minor wins inside the resampler — all byte-identical

```
processors/resampler.py:572  peak scan  (genexpr)   13.67 -> 4.89 ms   2.79x
processors/resampler.py:667  stereo re-interleave   15.06 -> 4.80 ms   3.14x
processors/resampler.py:208  _onepole_lowpass        22.73 -> 19.32 ms  1.18x
processors/resampler.py:382  _decimate               41.87 -> 35.65 ms  1.17x
processors/resampler.py:364  _onepole_highpass       23.43 -> 20.62 ms  1.14x
processors/resampler.py:179  _float_to_pcm           40.79 -> 37.46 ms  1.09x
processors/resampler.py:176  _pcm_to_float [s/32768] 16.26 -> 15.04 ms  1.08x
```

The peak scan one matters more than its own size: `max(max(x), -min(x))` is
exact for every float including ±0.0 and infinities, and it is 2.8×.

**The two codec functions are essentially at the floor.** With `repeat=9` the
`_pcm_to_float` gain settles at 15.42 → 15.04 ms = **1.03×**. The repo's own
retraction ("memoryview measured 19.11 → 19.57 ms — no change") reproduces
exactly: the same idea measured here at 16.26 → 15.21 ms = **1.07×**. The
per-element convert is the floor, as the comment says. The `_float_to_pcm`
`array('h', [...])` form at 1.09× and the `* 2^-15` form at 1.03–1.08× are real
but below the bar — take them if you want them, they are free and exact
(1/32768 is a power of two, so multiply and divide agree bit-for-bit), but do
not expect a measurable conversion.

## 8. Whole conversion, end to end

Pipeline = `trim_start_bank` → `auto_loop_banks(workers=1)` →
`resample_banks(profile, workers=1)` → `write_e4b`, 4 samples × 2.0 s, best of
1 after warm-up, stdout suppressed, SHA-256 of the written file compared:

```
mono    emulator2  1102.66 ->  814.40 ms   1.35x   sha256 23869203588b11f6  identical
mono    emax1      1130.96 ->  873.21 ms   1.30x   sha256 e251994840cc2846  identical
stereo  emulator2  2269.39 -> 1641.70 ms   1.38x   sha256 7a70da6e3f3b07ea  identical
stereo  emax1      2299.66 -> 1672.31 ms   1.38x   sha256 0425e06a55a49266  identical
```

The four written `.E4B` files are byte-for-byte identical. The gain is diluted
relative to §1 because the `write_e4b` step (unchanged) and
`_pcm_to_float`/`_float_to_pcm` (decoded once per stage, unavoidable without a
cross-stage cache) are in there.

---

# RETRACTED — measured, no gain, or not safe

These are the findings this project asked for explicitly. Each was implemented
and timed. The repo has a hard rule about not shipping a measurement that is
not actually measured — several comments already record retracted
optimisations — so these are recorded with the same status.

**`_sinc_resample`'s inner convolution is at the pure-Python floor.**
`out[i] = sum(map(mul, w, seg))` over 68 taps × 88,200 outputs: 540.49 ms.
Hoisting `map`/`mul`/`sum` to locals and making `w` a tuple: 562.77 ms =
**0.96×** — no change, byte-identical. This is the one place where I went
looking hard for a win and found none; 45 ns per multiply-add is what pure
Python costs.

**`resampler.py:352`, the non-exact polyphase branch, rebuilds a weight vector
for every output sample — and cannot be fixed safely.** For 27777 → 22050
(which the KRZ headroom stage and `--resample eii` + `--max-sample-rate` both
produce, because `up = 7350 > _SINC_MAX_PHASES`),
`w = [a + (b-a)*f for a, b in zip(wa, wb)]` is **2.157 s of a 3.622 s profile
— 60 %**. Three alternatives were built:

```
  current (listcomp per output sample)   1458.7 ms
  cached DIFF rows (d = b-a, computed once) 1427.6 ms   1.02x   byte-identical
  cached blended vectors                   1051.2 ms   1.39x   byte-identical
```

The 1.39× is **rejected on memory**: the phase sequence is *pseudo-random*, not
periodic, because `ratio` is a float rather than the exact rational —
**24,944 distinct `(p0, f)` pairs for 88,200 output samples** of a 4 s sample,
so a cache grows linearly with sample length (≈18 MB for this one sample,
~330 MB at 20 s) and must live in every pool worker. A bounded cache does not
work either, measured: `lru_cache(maxsize=1024/4096)` → **0.0 % hit rate**,
1785/1789 ms (i.e. *slower* than no cache); only at 16384 entries does it reach
71.7 % hits and 956.7 ms. **State the non-exact branch as an
unfixable-in-pure-Python hot spot, not as an opportunity.**

**`heapq.nsmallest` instead of `sorted` in `_windowed_ms`:** 65.79 → 111.09 ms
= **0.59×** — much worse. The full sort stays.

**The stereo downmix `zip` rewrite in `auto_loop.py:344` / `single_cycle.py:260`:**
0.89× / 0.91× — slower. The two strided slices cost more than the range-index
loop saves. Odd-length buffers (7, 5, 3, 1, 0 values) were checked too — the
results agree, the point is purely speed. **Do not "fix" those two lines this
way.**

---

# ALREADY OPTIMAL — measured, with numbers

**The write loops.** 7.06 MB of PCM written in **35.0 ms** (E4B, mono) /
**53.2 ms** (KRZ) — 200 MB/s, which is the I/O and `array.byteswap` bandwidth.
Stereo: 51.9 ms / 69.8 ms. In the profile of a 200-sample, 400-zone bank the
single largest item in `write_e4b` is **`posix.fsync` at 0.030 s of 0.152 s** —
the write path is I/O-bound, not compute-bound. The KRZ PCM loop already uses
`a.tofile(f)` with a `memoryview` (`krz_writer.py:4631-4635`). No
byte-concatenation of large buffers anywhere in the tree.

**`e4b_parser` PCM extraction.** 7.06 MB in 10.6 ms = **670 MB/s** mono,
232 MB/s stereo. Consistent with §PARSERPERF's 445.7 MB/s and already
`bytes(pcm)` over a slice basis — nothing to win.

**`krz_parser` PCM extraction.** `_extract_pcm` is `array.frombytes` +
`byteswap` + `tobytes`: 355 MB/s mono, 179 MB/s stereo. Already the
§PARSERPERF fix.

**`processors/single_cycle.py`** — 20 × 4 s mono in **0.17 s** total
(8.5 ms/sample); 47 ms for a single 4 s sample, of which `_pcm_to_float` is
half and `_sustain_start`'s window scan the rest. Not a hot path.

**The multiprocessing boundary is correctly placed, and this was checked rather
than assumed.** Pickle round-trip of the `(SampleData, dst_rate)` argument
tuple: 0.11 ms at 352,800 B, 0.88 ms at 1.76 MB, 0.03 ms at 4,410 B — against
745 / 3,480 / 10 ms of `resample_to_rate` compute. **0.0–0.3 %.**
`processors/parallel.py:59` `map_over_banks` and `resampler.py:806` each build
**one** pool per stage, never per item; a grep for `ProcessPoolExecutor` across
the repo (excluding tests) finds exactly two sites plus the worker
trampolines. No per-item pool creation exists to fix.

**Import time.** `python3 -X importtime -c "import convert"` → cumulative
**73 ms** one-time. `parsers.registry`'s 17 eager parser imports are 52.6 ms of
that. Not worth a lazy-import refactor.

**`merge_akai_stereo_pairs` (`krz_writer.py:4013`) is O(Z²) in zones per voice —
but bounded.** 32 zones → 0.03 ms, 64 → 0.05 ms, 128 → 0.10 ms; 1024 zones
across 8 voices → 0.69 ms. The 128-key keymap caps a voice at 128 zones, so the
quadratic never bites.

**`_reson_keytrack_fit` (`krz_writer.py:2337`) builds one `(key, resonance)`
point per key** — 0.183 ms at 16 zones/128 keys, 0.358 ms at 32, 0.720 ms at 64
zones/512 keys. Material only if a large bank fuses every layer on a resonanced
source; making it per-zone would change the floating-point summation order of
five reduction terms, so **no speedup is claimed** for it. Left as an
unverified opportunity.

**`e4xt_cutoff_hz_to_byte`'s 40-iteration binary search** (each iteration
doing a `zip(pts, pts[1:])` inside `_interp`): 1600 calls in 0.008 s on a
cord-rich 400-voice write. Below the bar.

---

# CLEAN FILES

**`fat12.py`, `fat16.py`, `fat32.py`** — verified with `mtools` and byte
inspection. FAT12 images (both 1440 and 720 geometries) round-trip file content
byte-identically through `mtype`, including VFAT long names. FAT16/FAT32 boot
sectors, FAT chains, MBR CHS (`_chs`), `fatsz` iteration, FSInfo and
backup-boot placement all check out. *(mtools refuses `img@@63` on a
partitioned FAT16 image of ours, but the identical boot sector with no MBR
reads fine and the chain/FAT bytes are correct — mtools' MBR handling, not our
layout.)*

**`atomic.py`**, **`akai_aux_defaults.py`** (asserted lengths match),
**`iso_builder.py`**, **`hda_builder.py`**, **`eos_firmware_sim.py`**,
**`akai_s3000_image.py`** — chunk/block arithmetic verified;
`_put_block`'s out-of-range guard is the right shape.

**`writers/e4b_writer.py`** — FORM/chunk/TOC arithmetic verified byte-exact,
including mono odd-length PCM, stereo with a half-frame, loop-to-the-end, and
stereo loop-point rebasing (`lsl - STRUCT_SZ + start_r`). *(The one-sided
zone-entry clamps at 656-693 are finding 10 above.)*

**`writers/krz_writer.py`** — `_BlockWriter` size/blocksize/`ofs` arithmetic
and `word_offsets` vs `_pcm_words_written` verified; object/PCM geometry exact
in all tests. *(Loop clamping is finding 9; `_terr` is m17; the comment is
m16.)*

**`writers/akai_s3000_writer.py`** — round-tripped through
`parse_program_bytes`/`parse_sample_bytes`: per-zone tune (25 ct → 64 units →
25 ct), coarse tune (3 st → 768 units), loudness (−6 dB → −10), pan (0.5 →
25), root, rate and loop all exact. No caller-bank mutation (deep-copies the
preset at line 4950).

**`parsers/sf2_parser.py`** — chunk/size handling and the preset-global-zone
additive merge are correct; the `len(voice.zones) == 1` guard is *"first
zone"* as documented (already settled in `TODO.md:46`).

**`parsers/talsmpl_parser.py`**, **`parsers/tal_template.py`** — no defects
found.

**`parsers/sampledir_parser.py`** — `_velocity_bands` cannot divide by zero
(`stacked` groups are ≥ 2); the only edge case is `lo > hi` when many samples
collapse onto key 127 after the spread.

**`parsers/registry.py`**, **`parsers/krz_parser.py`** (aside from the false
KRZ_ROM_ONLY diagnostic in finding 2), **`parsers/eiii_parser.py`**,
**`parsers/eps_parser.py`** (aside from m7), **`parsers/roland_s7xx_parser.py`**
(aside from m13), **`parsers/akai_s3000_parser.py`** — bounds checks at the
block/keygroup/zone level are thorough, and the writer/reader inverse pairs
spot-checked (E4B sample header & voice, KRZ KSample/Soundfilehead/KKeymap
entry sizes and field order) agree byte-for-byte.

**`processors/parallel.py`** — clean. No broad `except` anywhere; verified that
a raising worker propagates (`RuntimeError: worker exploded` surfaced to the
caller, not swallowed); the `with` block guarantees `shutdown(wait=True)`;
`assert at == total` is a real invariant check. Only nit: `assert` disappears
under `python -O`.

**`processors/zone_reducer.py`** — clean. The CR-21 collapse
(`TODO.md:2586`) does *not* recur on the key axis: `_thin_and_redistribute`'s
`keep_count == 1` path widens the survivor to `[full_lo, full_hi]`, so
`--reduce-key-zones 95` on a 1/36/1/20/20-key E4B-native preset keeps full 0-127
coverage. The `contiguous` and `new_lo <= new_hi` guards hold under the shapes
tried.

**`processors/loop_renderer.py`** — clean. Verified that the baked 2n−2 forward
loop reproduces the ping-pong sequence sample-for-sample, that the head and the
post-loop tail are byte-preserved, and that `loop_end == frames - 1` for mono
and stereo.

**`processors/start_trim.py`** — clean. The documented slow-attack fix
(`TODO.md:2948`) holds; on decaying material with no leading silence it cuts 0
frames, unlike its tail counterpart.

**`processors/tail_trim.py`** / **`auto_loop.py`** / **`single_cycle.py`** DSP —
no new defect beyond findings 6 and m18. An 84-case sweep (sr 8k–48k, lengths
5–1500 ms, pitches 55–9000 Hz, mono + stereo) produced no exception, no
`loop_end > frames`, no inverted loop, and no `min()`/`max()` over an empty
sequence. `TODO.md:55` (percentile-floor) and `TODO.md:2948` remain the only
real defects there.

**`models/common.py`** — no new defect. No mutable defaults
(`field(default_factory=...)` throughout); every `math.log`/division probed is
guarded. Latent only: `shrink_planner._centroid_frames` has a live `depth == 8`
branch while every processor decodes via `_pcm_to_float` (16-bit only) — dead
code today because all parsers normalise to 16-bit, but the two disagree about
what `SampleData.bit_depth` means.

---

# FILING CONVENTION

Per `CLAUDE.md`, anything not fixed immediately belongs in `TODO.md` (what is
open) with the resolution strategy in `docs/RESOLUTION_NOTES.md` (how to fix
it). The rows above that say *"Not tracked in `TODO.md`"* are the ones that
still need writing there; the ones that name a row already are recorded and
need only a cross-reference added.

**Priority if only a few are taken:** 3 (loops dropped on AKAI, one-line fix,
no diagnostic today) → 2, 5, 6, 11 (silent content loss or wrong output) →
the quantizer optimisations (§1 — highest-leverage speed change, byte-identical,
1.29× through the real worker pool).
