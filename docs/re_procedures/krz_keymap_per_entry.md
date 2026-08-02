# KRZ per-entry sample assignment — confirm or disprove

**The claim under test:** a KRZ keymap with distinct samples on adjacent keys
plays only the FIRST sample on the K2000, key-tracked, instead of one sample
per key.

**Treat the claim itself as suspect.** It is not yet established. The evidence
is one listening observation ("crash left / snare right in rising pitches")
plus a reading from an earlier sitting that predates the stereo fixes — from a
session that misread several other things with equal confidence. Every offline
comparison since has failed to find any difference between our keymaps and real
multi-sample ones. **A plan that assumes the bug is real will find a cause for
something that may not exist.** Phase 0 exists to kill it or confirm it.

---

## Phase 0 — establish whether the phenomenon exists at all

Everything else is conditional on this. Budget: one sitting.

### 0.1 Build an unambiguous test bank

The existing evidence used drum one-shots, where "which sample is playing" is a
judgement call. Use **distinct pure tones** instead, so the measurement states
directly which sample sounded:

| key | sample | content |
|---|---|---|
| C3 (48) | `T440` | 440 Hz |
| C#3 (49) | `T550` | 550 Hz |
| D3 (50) | `T660` | 660 Hz |
| D#3 (51) | `T880` | 880 Hz |

All **mono**, all looped, each rooted on its own key so nothing transposes.
Mono matters: it removes the stereo machinery from the experiment entirely.
Frequencies are not harmonically related to each other's transpositions — 440
key-tracked to key 49 is 466 Hz, which is not 550, so "wrong sample" and
"right sample" can never be confused.

**Predictions, and they are mutually exclusive:**

- per-entry works → 440 / 550 / 660 / 880
- per-entry broken → 440 / 466 / 494 / 523 (one sample, key-tracked)

There is no third reading. Measure with a per-key Goertzel at all four
frequencies plus the key-tracked series.

### 0.2 The control that has never been run

**Does a real multi-sample bank do per-key assignment on this K2000R?**

Never verified. The commercial control bank has keymaps with several samples
across a key range, but only stereo separation was ever measured on it — never
that two keys play two different samples. Load one, find a keymap whose runs put
different sample ids on nearby keys (`PPG table` in the local corpus has 5
distinct samples in one 0..127 table), and play across a run boundary.

### Gate

| 0.1 | 0.2 | conclusion |
|---|---|---|
| per-key works | — | **the bug does not exist.** Retract it, delete the workaround note, stop |
| per-key broken | real bank also broken | **not our bug** — a K2000 or rig behaviour. Document and stop |
| per-key broken | real bank works | the bug is real and ours. Proceed to Phase 1 |

Only the third row justifies any further work.

---

## Phase 1 — offline structural diff (no hardware)

Do this only if Phase 0's third row holds. Everything below has **already been
checked and matches** real multi-sample keymaps; listed so it is not redone:

| field | ours | real |
|---|---|---|
| method (body `[2:4]`) | `0x0013` | `0x0013` on 62 real multi-sample keymaps |
| entry size | 5 bytes | 5 for method `0x13` |
| 28-byte keymap header | `00 00 00 13 00 00 00 64 00 7f 00 05 …` | byte-identical |
| entry layout | `tuning(2) sampleID(2) byte4(1)` | same |
| entry byte 4 | `1` | `1` in 1598 of 2020 real entries (79 %) |
| body size | 668 = 28 + 128×5 | both 668 and 670 occur; `PPG table` is 668 |
| tables | one, 0..127 | 1569 of 1584 corpus keymaps |
| `header_sample_id` | 0 | 0 |
| `cents_per_entry` | 100 | 100 (1584/1584) |

**So the keymap object is not where the difference is.** Phase 1 must look
outside it:

1. **The layer's key range.** `LYR[3]`, `LYR[4]` are the layer lo/hi key. A
   real stereo program reads `0x0c 0x6c` (12..108); ours has read `0x30 0x30`
   (48..48) in at least one bank. A layer spanning one key cannot play four.
   **Check this first — it is the only known concrete divergence.**
2. **`CAL[29]` `numKeymaps`.** We write 1. Confirm real multi-sample layers
   also write 1, and that it is not a count of something we are getting wrong.
3. **Sample object ordering and PCM contiguity.** Does the K2000 require the
   referenced samples' PCM to be laid out in a particular order relative to the
   keymap's entries?
4. **Object id ordering.** Our samples are 200, 201, 202 … in entry order. Check
   whether real banks ever reference ids out of ascending order across a keymap,
   i.e. whether ascending order is load-bearing.

---

## Phase 2 — hardware bisection

Only if Phase 1 finds candidates. Method that worked for the stereo hunt:

- **Three variants per bank load.** Put each hypothesis on its own program, each
  with content that identifies which variant sounded. One load tests three.
- **Patch our bank toward a real one**, field by field, rather than building
  from scratch — the target is a byte-level bisection between a keymap that
  works and one that does not.
- Keep one unmodified program in every bank as an internal control.

---

## Rules for this investigation

Carried from the stereo session, where ignoring them cost hours:

1. **Verify which sample a key actually plays before interpreting its audio.**
   The file was correct every time while the hardware played something else.
   Reading the keymap back out of the file proves nothing.
2. **Cross-key correlation does NOT show that two keys play different samples.**
   One sample transposed decorrelates just as thoroughly. This inference is what
   wrongly retracted this very bug once already.
3. **Check the level before believing a correlation.** A table of correlations
   near +0.5 once looked like a result; every level in it was at the noise floor.
4. **Check any single-pair difference against the corpus** before believing it.
   Three of four candidate "markers" in the stereo hunt died that way.
5. **Design the negative control in from the start.** Here it is Phase 0.2:
   without knowing that real banks work on this machine, a null result means
   nothing.
