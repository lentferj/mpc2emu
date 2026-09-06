<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Parameter & modulation support matrix — XPM · AKAI · E4B · KRZ

What actually survives a conversion, per parameter, per direction.

This is a claim about **the code as it stands**, not about what the formats are
capable of. Every non-obvious cell carries a `file.py:line` citation, and every
cell that rests on a *measured* hardware law says so — because a cell that
merely looks authoritative is worse than no cell at all.

Scope is the four paths that carry the project's real work: **MPC keygroup
(`.xpm`)**, **AKAI S1000/S3000**, **EMU E4B/E4XT**, and **Kurzweil KRZ**. The
EIII and TAL-Sampler writers exist but are deliberately out of scope here; see
the note at the end.

Companion documents: [`E4B_FORMAT.md`](E4B_FORMAT.md),
[`KRZ_FORMAT.md`](KRZ_FORMAT.md), [`AKAI_S3000_FORMAT.md`](AKAI_S3000_FORMAT.md).
Open defects referenced below live in [`../TODO.md`](../TODO.md) with fix
strategies in [`RESOLUTION_NOTES.md`](RESOLUTION_NOTES.md).

---

## How to read this

Every conversion runs **parser → model → writer**. The model is
`models/common.py` (`VoiceLayer`, `ZoneMapping`, `Envelope`, `SampleData`), and
a path supports a parameter only where **both ends** do. So there are three
tables, and the third is derived from the first two:

| | |
|---|---|
| **Table 1 — READ** | format → model. Columns XPM · AKAI · E4B · KRZ. |
| **Table 2 — WRITE** | model → format. Columns E4B · KRZ · AKAI. |
| **Table 3 — END-TO-END** | the weaker of the two, per path. |

### Legend

| | |
|---|---|
| `✓` | carried |
| `✓ᴴ` | carried, and the mapping law is **hardware-measured** on the real instrument |
| `~` | carried but approximate, lossy, or clamped — see the footnote |
| `!` | present but **defective** — links an open `TODO.md` entry |
| `✗` | the format has this parameter and we drop it |
| `·` | the format has no such parameter (nothing is lost) |

**`✓ᴴ` marks the mapping law, not the round trip.** A hardware-measured
byte↔Hz curve does not mean anyone has played the converted file on the
machine and listened.

### One caution about reading Table 1 against Table 2

A parameter read on one side and not written on the other is **not by itself a
bug**. On 2026-09-06 a reader/writer asymmetry around AKAI `SUSTN2` was
"fixed", shipped, and reverted an hour later because the *machine* gates the
way the writer did. Where this matrix exposes an asymmetry it says so and stops
there; a `!` is only used where the defect is established independently — by
absence in the code, not by disagreement between two of our own modules.

---

## Table 1 — READ: what each parser extracts into the model

### Zone / mapping

| Parameter | Model field | XPM | AKAI | E4B | KRZ |
|---|---|:--:|:--:|:--:|:--:|
| Key range | `ZoneMapping.lo_key/hi_key` | ✓ | ✓ | ✓ | ✓ |
| Velocity range | `lo_vel/hi_vel` | ✓ | ✓ | ✓ | ✓ |
| Root key | `root_key` | ✓ | ✓ | ✓ | ✓ |
| Loop points | `SampleData.loop_start/end` | ✓ | ✓ | ✓ | ✓ |
| Loop type | `SampleData.loop_type` | ✓ | ✓ | ✓ | ~ [^krzloop] |
| Non-transpose | `VoiceLayer.non_transpose` | ✓ [^xpmnt] | · | ✓ | · |

### Static per-zone

| Parameter | Model field | XPM | AKAI | E4B | KRZ |
|---|---|:--:|:--:|:--:|:--:|
| Volume (dB) | `ZoneMapping.volume` | ✓ | ✓ᴴ [^akvloud] | ✓ | ✓ |
| Pan | `ZoneMapping.pan` | ✓ [^xpmpan] | ✓ | ✓ | ~ [^krzpanread] |
| Fine tune | `fine_tune` | ✓ | ✓ [^aktune] | ✓ | ✓ |
| Coarse tune | `coarse_tune` | ✓ | ✓ [^aktune] | ✓ | ~ [^krztune] |
| Key transpose | `transpose` | ✓ | · | ✓ | · |
| Source resonance stamp | `src_resonance` | · | · | · | ✓ [^srcres] |

### Static per-voice

| Parameter | Model field | XPM | AKAI | E4B | KRZ |
|---|---|:--:|:--:|:--:|:--:|
| Filter type | `filter_type` | ✓ | · [^akftype] | ✓ | ✓ |
| Cutoff (Hz) | `filter_cutoff` | ✓ | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| Resonance | `filter_resonance` | ✓ | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| Chorus | `chorus_amount` | ✗ | · | ✓ | · |

### Envelopes

| Parameter | Model field | XPM | AKAI | E4B | KRZ |
|---|---|:--:|:--:|:--:|:--:|
| Amp ADSR | `amp_env` | ✓ | ✓ᴴ | ✓ | ✓ |
| Filter ADSR | `filter_env` | ✓ | ✓ᴴ | ✓ | ✓ |
| Filter-env depth | `filter_env_cents` | ✓ | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| Release slew rate | `release_rate_db_per_s` | · | ✓ᴴ | ✓ | · |
| Decay slew rate | `decay_rate_db_per_s` | · | ✓ᴴ | · | · |
| Pitch envelope | — | ✗ [^nopitchenv] | ✗ | ✗ | ✗ |

### LFO parameters

| Parameter | Model field | XPM | AKAI | E4B | KRZ |
|---|---|:--:|:--:|:--:|:--:|
| LFO1 rate | `lfo1_rate` | ✓ | ✓ᴴ | ✓ᴴ | ✓ |
| LFO1 shape | `lfo1_shape` | ✓ | ✓ | ✓ | ✓ |
| LFO1 delay | `lfo1_delay` | ✗ | ✓ᴴ | ✓ | ✗ |
| LFO1 variation | `lfo1_variation` | ✗ | · | ✓ | · |
| LFO1 key-sync | `lfo1_sync` | ✓ | ✗ | ✓ | ✗ |
| LFO1 tempo-sync division | `lfo1_sync_division` | ~ [^xpmsync] | · | · | · |
| LFO2 rate / shape | `lfo2_rate/shape` | ~ [^mpc3only] | ✗ [^akpanrat] | ✓ | ✗ |
| LFO2 delay / variation / sync | `lfo2_*` | ✗ | · | ✓ | ✗ |

### Modulation routings

| Routing | Model field | XPM | AKAI | E4B | KRZ |
|---|---|:--:|:--:|:--:|:--:|
| Velocity → volume | `velocity_to_volume_db` | ✓ᴴ | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| …its pivot | `velocity_to_volume_pivot` | ✓ (127) | ✓ᴴ (64) | ✓ | ✓ (127) |
| …its curve | `velocity_to_volume_curve` | ✓ᴴ [^mpccurve] | ✓ | ✓ | ✓ |
| Velocity → filter | `velocity_to_filter_cents` | ✓ | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| …its floor | `velocity_to_filter_min_cents` | ✗ [^xpmvfmin] | ✓ᴴ | ✗ | ✓ |
| Key → filter | `filter_keytrack` | ✓ | ✓ᴴ | ✓ᴴ | ✓ |
| Filter env → filter | `filter_env_cents` | ✓ | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| LFO1 → pitch | `lfo1_to_pitch` | ✓ | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| LFO1 → filter | `lfo1_to_filter` | ✓ | ✗ | ✓ | ✓ |
| LFO1 → filter Q | `lfo1_to_filter_q` | · | · | ✓ | ✗ |
| LFO1 → volume (tremolo) | `lfo1_to_volume` | ✗ [^xpmtrem] | ✓ | ✗ | ✓ |
| LFO2 → pitch | `lfo2_to_pitch` | ~ [^mpc3only] | ✗ | ✓ | ✗ |
| LFO2 → filter / Q | `lfo2_to_filter(_q)` | ✗ | ✗ | ✓ | ~ [^krzlfo2f] |
| LFO2 → volume | `lfo2_to_volume` | ✗ | · | ✗ | ✓ |
| Mod wheel → LFO depth | `wheel_to_lfo` | ✓ | ✗ | ✓ᴴ | ✗ |
| Key → resonance | — | · | · | · | ✗ [^kresonkt] |
| Aftertouch (any dest) | — | ✗ | ✗ | ✗ | ✗ [^noat] |

---

## Table 2 — WRITE: what each writer emits from the model

### Zone / mapping

| Parameter | E4B | KRZ | AKAI |
|---|:--:|:--:|:--:|
| Key range | ✓ | ✓ | ✓ |
| Velocity range | ✓ [^e4bvelsplit] | ✓ | ✓ |
| Root key | ✓ | ✓ | ✓ |
| Loop points | ✓ᴴ | ✓ᴴ | ✓ |
| Ping-pong loop | ~ [^bakepp] | ~ [^bakepp] | ~ [^bakepp] |
| Non-transpose | ✓ | · | · |

### Static per-zone

| Parameter | E4B | KRZ | AKAI |
|---|:--:|:--:|:--:|
| Volume (dB) | ✓ᴴ | ✓ | ✓ᴴ [^akvloud] |
| Pan | ✓ᴴ | ~ [^krzpan] | ✓ |
| Fine / coarse tune | ✓ | ✓ | ✓ |
| Key transpose | ✓ | ✗ | ✗ |

### Static per-voice

| Parameter | E4B | KRZ | AKAI |
|---|:--:|:--:|:--:|
| Filter type | ✓ᴴ | ✓ᴴ | · [^akftype] |
| Cutoff (Hz) | ✓ᴴ | ✓ᴴ | ✓ᴴ [^akjoint] |
| Resonance | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| Chorus | ✓ᴴ | ✗ | ✗ |

### Envelopes

| Parameter | E4B | KRZ | AKAI |
|---|:--:|:--:|:--:|
| Amp ADSR | ✓ᴴ | ✓ | ✓ᴴ |
| Filter ADSR | ✓ᴴ | ✓ [^krzfiltgate] | ✓ᴴ |
| Filter-env depth | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| Release slew rate | ✓ | ✓ | ✓ᴴ |
| Decay slew rate | · [^e4bdecay] | ✗ | ✓ᴴ |
| Pitch envelope | ✗ | ✗ [^krzenv3] | ✗ |

### LFO parameters

| Parameter | E4B | KRZ | AKAI |
|---|:--:|:--:|:--:|
| LFO1 rate | ✓ᴴ | ✓ | ~ [^aklfodep] |
| LFO1 shape | ✓ᴴ [^tri] | ✓ᴴ | ✗ [^aklfowave] |
| LFO1 delay | ✓ | ✗ | ✗ |
| LFO1 variation | ✓ | · | · |
| LFO1 key-sync | ✓ | ✗ | ✗ |
| LFO2 rate / shape | ✓ᴴ | ✗ [^krzlfo2] | ✗ [^akpanrat] |
| LFO2 delay / variation / sync | ✓ | ✗ | ✗ |

### Modulation routings

| Routing | E4B | KRZ | AKAI |
|---|:--:|:--:|:--:|
| Velocity → volume | ✓ᴴ [^e4bvelplus] | ✓ᴴ | ✓ᴴ |
| Velocity → filter | ✓ᴴ | ✓ᴴ | ~ [^akjoint] |
| Key → filter | ✓ᴴ | ✓ | ✓ᴴ |
| Key → resonance | ✗ | ✓ [^kresonkt] | ✗ |
| Filter env → filter | ✓ᴴ | ✓ᴴ | ✓ᴴ |
| LFO1 → pitch | ✓ᴴ | **!** [^krzlfosign] | **!** [^aklfodep] |
| LFO1 → filter | ✓ᴴ | ✗ | ✗ |
| LFO1 → filter Q | ✓ᴴ | ✗ | ✗ |
| LFO1 → volume (tremolo) | ✗ [^e4btrem] | ✓ | ✗ |
| LFO2 → pitch | ✓ᴴ | ✗ | ✗ |
| LFO2 → filter / Q | ✓ᴴ | ✗ | ✗ |
| LFO2 → volume | ✗ | ✓ | ✗ |
| Mod wheel → LFO depth | ✓ᴴ | ✗ | ✗ [^akmw] |
| Aftertouch (any dest) | ✗ | ✗ | ✗ [^noat] |

---

## Table 3 — END-TO-END, derived

Cell = the weaker of Table 1 and Table 2. `·` where neither end has the
parameter. The three MPC rows are the ones most people are converting.

| Routing / parameter | XPM→E4B | XPM→KRZ | XPM→AKAI | AKAI→E4B | AKAI→KRZ | E4B→KRZ | KRZ→E4B | E4B→AKAI | KRZ→AKAI |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Amp ADSR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Filter ADSR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Filter-env depth | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Cutoff / resonance | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Filter type | ✓ | ✓ | · | · | · | ✓ | ✓ | · | · |
| Velocity → volume | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Velocity → filter | ✓ | ✓ | ~ | ~ | ✓ | ✓ | ✓ | ~ | ~ |
| Key → filter | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| LFO1 rate | ✓ | ✓ | ~ | ✓ | ✓ | ✓ | ✓ | ~ | ~ |
| LFO1 shape | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |
| LFO1 delay | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| LFO1 → pitch | ✓ | **!** | **!** | ✓ | **!** | **!** | ✓ | **!** | **!** |
| LFO1 → filter | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| LFO1 → filter Q | · | · | · | · | · | ✓ | ✗ | ✗ | ✗ |
| LFO1/2 → volume | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| LFO2 (rate/shape/pitch) | ~ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Mod wheel → LFO depth | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Chorus | ✗ | ✗ | ✗ | · | · | ✗ | · | ✗ | · |
| Pitch envelope | · | · | · | · | · | · | · | · | · |
| Aftertouch | · | · | · | · | · | · | · | · | · |

**The one-line summary.** The E4B writer is the most complete modulation target
we have; the KRZ writer carries everything except the LFO's routings to the
filter; the AKAI writer carries the static and envelope world faithfully and
almost none of the LFO's. On the MPC path specifically, `LfoCutoff` reaches
only the E4B, and `KeygroupWheelToLfo` reaches only the E4B.

---

## How this matrix was verified

Two passes, because neither is sufficient alone.

**1. Grep-assertion.** Every `✗` cell asserts that the named model field appears
**zero** times in the named module. 22 such assertions, all passing as of
2026-09-06 — e.g. `lfo1_to_volume` / `lfo2_to_volume` appear nowhere in
`writers/e4b_writer.py`, and `lfo1_shape`, `lfo1_delay`, `lfo1_to_filter`,
`lfo2_*`, `wheel_to_lfo`, `chorus_amount` appear nowhere in
`writers/akai_s3000_writer.py`.

**2. Round trip.** A synthetic voice with **every** modulation field set
non-zero, written to each of the three targets and read back with the matching
parser. What came back:

| | E4B | KRZ | AKAI |
|---|---|---|---|
| Fields lost | `lfo1_to_volume`, `lfo2_to_volume` | LFO1 delay/variation, LFO1→filter, LFO1→filter-Q, all LFO2, chorus | the entire LFO1 and LFO2 block, chorus |
| Everything else | carried within quantisation | carried | carried |

That is the matrix, reproduced from the outside. Two results are worth stating
in full because they are the evidence behind the two `!` cells:

- **AKAI, LFO1 → pitch `0.30` came back `0.00`**, and so did `lfo1_rate`,
  `lfo1_shape` and `lfo1_delay` — the reader gates the *whole* LFO1 block on
  `LFODEP and L_PTCH` both being non-zero (`akai_s3000_parser.py:856`), and we
  write only the second. §AKAILFODEP costs more than the depth.
- **KRZ, LFO1 → pitch `+0.30` came back `0.314` and `−0.30` came back `0.00`.**
  The vibrato is not phase-flipped, it is gone. §KRZLFOSIGN.

**What neither pass proves.** A round trip shows our reader agreeing with our
writer, which is the one thing that was never in doubt; the `✓ᴴ` marks say a
*mapping law* was measured on hardware, not that the converted file was played
on the machine and listened to. Where those two could diverge, the machine
decides — see the caution at the top of this document.

---

## Known defects surfaced by this matrix

Both are established by **absence in the code**, not by a reader/writer
asymmetry. See `TODO.md` and `RESOLUTION_NOTES.md` for fix strategies.

- **§AKAILFODEP** — the AKAI writer writes the LFO→pitch *gate* and never the
  *depth*, so converted vibrato is still silent. `TODO.md`.
- **§KRZLFOSIGN** — the KRZ writer discards a negative `LfoPitch`. `TODO.md`.

---

## Out of scope here

`writers/eiii_writer.py` (Emulator IIIX/ESI) has **no modulation matrix at
all** — its header states the scope decision "no per-zone LFO"
(`eiii_writer.py:17`), it writes the VCF type/LFO-shape byte as a literal zero
(`:503`), and it leaves velocity→VCA and velocity→VCF neutral because no EIII
hardware calibration exists yet (`:496-511`). It carries the amp envelope, the
filter envelope + depth, cutoff, resonance, level and pan.

The TAL-Sampler writer (`parsers/talsmpl_parser.py:545-580`) carries the amp
envelope, filter mode, cutoff and resonance, and no modulation routings.

---

## Footnotes

[^krzloop]: `parsers/krz_parser.py` reads the K2000 loop flag, but the K2000 has
    no ping-pong mode, so `LoopType.ALTERNATING` can never come back off a KRZ.

[^xpmnt]: Derived rather than read: `xpm_parser.py:1921` sets it from
    `IgnoreBaseNote`, or from an unset root over a full key range, and
    `:2037-2043` withdraws it when the WAV `smpl` chunk supplies a root.

[^akvloud]: `dB = 0.60576 · VLOUD1 − 20.1778`, r² 0.999896 over −50..+20
    (s3ked, 2026-08-17). The writer clamps at **+20, not +50** — above +20 the
    field saturates against the same output ceiling as the program level
    (`akai_s3000_writer.py:2699-2702`).

[^xpmpan]: Instrument pan and layer pan are summed and clamped
    (`xpm_parser.py:1929-1931`).

[^aktune]: Read and written as one quantity: `coarse_tune·100 + fine_tune`
    (`akai_s3000_writer.py:2673-2675`). §AKAITUNEREAD — the reader once put a
    whole octave into `fine_tune` while the writer read only `fine_tune`;
    neither side could see it alone.

[^krzpanread]: Pan is per-**layer** on the K2000 and per-**zone** in the model,
    so every zone of a layer takes the layer's pan (`krz_parser.py:1329`,
    §KRZPANREAD). A stereo layer carries channel routing in the same nibble
    rather than a musical pan, so it is read as centred — testing the sample's
    own channel count, because an earlier guard on an attribute no dataclass has
    silently never fired.

[^krztune]: Not a loss. The K2000 states one total shift, and the parser
    normalises it into `root_key` + `fine_tune` with `coarse_tune = 0`
    (`krz_parser.py:1303-1314`) so that the model's
    `true_shift(key) = 100·(key − root_key) + fine_tune` holds. The pitch is
    exact; only the split between the two fields is not preserved.

[^srcres]: `ZoneMapping.src_resonance` stamps each zone with its originating
    voice's resonance *before* layer fusion averages it away, so the KRZ writer
    can fit the K2000's per-key resonance ramp across a fused layer
    (`krz_writer.py:1070`, §KRZRESKEYTRK).

[^akftype]: Not a gap. The S3000 has one fixed 2-pole low-pass, so the parser
    states it as a constant (`akai_s3000_parser.py:829`, XPM type 2) and the
    writer has nothing to select.

[^nopitchenv]: The model has no pitch-envelope field at all, so no parser reads
    one and no writer emits one. The MPC, E4XT (Aux envelope) and K2000 (ENV3)
    all have one.

[^xpmsync]: The tempo-lock division is folded into `lfo1_rate` at parse time at
    a reference BPM (`xpm_parser.py:1810-1822`, `--lfo-sync-bpm`), so what
    survives is a fixed Hz, not a tempo lock. The division index itself reaches
    no writer.

[^mpc3only]: LFO2 exists only in MPC 3.x programs (`xpm_parser.py:1859-1867`);
    an MPC 2.x XML program has no `<LFO2>` block.

[^akpanrat]: The AKAI's second LFO is `PANRAT`. The writer pins it to 1
    (`akai_s3000_writer.py:1799`) and the reader does not map it to `lfo2_*`.
    Its route to pan is dead on the machine, but the LFO itself works
    (s3ked §51, retracting §39).

[^mpccurve]: The MPC is the one machine of the four whose velocity→volume
    response is **linear in amplitude**, not in dB
    (`VELOCITY_CURVE_AMPLITUDE_LINEAR`, `xpm_parser.py:1797`). A single dB span
    describes it 14 dB RMS wrong, so the shape travels with the span and each
    writer fits its own line over `VELOCITY_FIT_RANGE` (32..127). §MPCVELSHAPE.

[^xpmvfmin]: The XPM parser never sets a floor, so an MPC velocity→filter sweep
    is always unipolar from the voice's own cutoff.

[^xpmtrem]: The XPM parser sets neither `lfo1_to_volume` nor `lfo2_to_volume`
    (verified by grep), so the KRZ writer's complete tremolo implementation
    (`krz_writer.py:2011-2023`) is unreachable from MPC input. It is live on the
    AKAI→KRZ and KRZ→KRZ paths.

[^krzlfo2f]: `krz_parser.py:971-973` reads LFO1→filter and LFO2→filter into the
    model, but no writer consumes `lfo2_to_filter` except the E4B one.

[^kresonkt]: The K2000's key→resonance ramp is **derived, not carried**: the KRZ
    writer least-squares-fits it across a fused layer's `src_resonance` stamps
    (`krz_writer.py:1610`, written `:2180-2182`) and only when fusion actually
    happened. No parser reads a key→resonance source field.

[^noat]: Aftertouch / channel pressure appears nowhere in the model, in any
    parser, or in any writer. The only occurrences in the tree are prose about
    the AKAI's `PRSDEP` (`akai_s3000_writer.py:338`, `:1565`).

[^e4bvelsplit]: E4B switches velocity at the **voice**, not the zone, so a voice
    holding several velocity windows is split into one voice per window before
    writing (`e4b_writer.py:_split_by_velocity`). Without that, velocity layers
    layer instead of switching (`E4B_FORMAT.md` §5.2).

[^bakepp]: No target has a ping-pong loop mode. A reversed copy of the loop
    interior is spliced into the PCM and the loop is written as forward
    (`bake_alternating_loop`; e.g. `e4b_writer.py:1543`).

[^krzpan]: A stereo sample is written as two hard-panned planar blocks, and
    `ZoneMapping.pan` is deliberately ignored for it (`krz_writer.py:1922`).
    Mono zones carry pan normally (`:1943-1952`).

[^krzfiltgate]: The **whole** filter block — cutoff, resonance, velocity→filter,
    key→filter and the filter envelope — is gated on `filter_type != 0`
    (`krz_writer.py:2047`). A voice with the filter off therefore also loses its
    filter envelope. The envelope *shape* is written unconditionally once inside
    that block, and only the routing depends on a non-zero depth
    (`:2209-2214`) — not doing so changed the filter envelope on 55.8% of
    round-tripped zones.

[^e4bdecay]: Deliberate. The E4B decay runs peak→sustain with both ends defined,
    so the seconds are sound and a rate would be a second way of saying the same
    thing (`Envelope.decay_rate_db_per_s`, §AKAIRELSPAN).

[^krzenv3]: ENV3 (segment `0x23`) is present in the ROM #199 template the writer
    clones and is never patched (`krz_writer.py:1237`). Same for ASR1/ASR2 and
    FUN1–4.

[^tri]: The E4XT's key-synced triangle rises first and the MPC's falls first, so
    a triangle LFO's cord amounts are negated to every destination to keep the
    starting direction (`e4b_writer.py:1210-1219`, RE'd 2026-06-14). The parser
    undoes it (`e4b_parser.py:571-580`).

[^aklfowave]: `LFO1WAVE` is read (`akai_s3000_parser.py:865`) and never written,
    so every converted AKAI LFO is whatever the machine defaults to. This
    matters more than it looks: the wave sets the RMS→peak factor the depth law
    is scaled by (`AKAI_LFO_WAVE_RMS_TO_PEAK`), so shape and depth have to land
    together — see §AKAILFODEP.

[^e4bvelplus]: Written as `Vel+` (pivot 0) since 2026-09-04, not the template's
    `Vel<`: a commercial EOS-native library CD is 96.9% `Vel+` (§E4XTVELSRC),
    and the bench refuted the objection that `Vel+` must clip — it tracks
    prediction to tenths of a dB up to +43 dB above nominal at 0–1% THD
    (§VELPLUSHDRM).

[^e4btrem]: The E4B writer has no LFO→AmpVol cord on any input path (grep for
    `to_volume` yields only `velocity_to_volume`), so the tremolo the AKAI, KRZ,
    SFZ and SF2 parsers all read is dropped on the way into an E4B.

[^krzlfosign]: **§KRZLFOSIGN** — `krz_writer.py:2222` gates on
    `lfo1_to_pitch > 0.0`, strictly positive, so an inverted-phase vibrato is
    silently discarded. Inconsistent with the filter-env and velocity depths,
    both made explicitly signed on 2026-08-25.

[^aklfodep]: **§AKAILFODEP** — the writer sets the gate `L_PTCH = 50`
    (`akai_s3000_writer.py:2118`) but never writes the depth byte `LFODEP`
    (program `0x22`), which is also absent from `_PROGRAM_HW_DEFAULTS`. The
    measured law is `rms_cents = 0.13127 · LFODEP · L_PTCH`
    (`models/common.py:1014`), and `LFODEP=0` produces no vibrato at any
    `L_PTCH`. The 2026-08-24 fix restored the routing and left the depth at
    zero — the same defect, one byte over.

[^akjoint]: The AKAI states a cutoff **and** a velocity depth in fields that
    share range, so `akai_velocity_filter` (`akai_s3000_writer.py:519`) solves
    the two jointly rather than writing either exactly — deliberate, not a
    defect. Measured on the round trip below: with no velocity depth, 2000 Hz
    returns as **2013.8 Hz** (0.7% off); with a 900-cent depth the same cutoff
    returns as **2706 Hz** and the depth as **555 cents**. So read the cutoff
    cell as exact only when nothing is competing for the byte.

[^akmw]: The AKAI's modwheel→LFO-depth byte is written as a fixed 30
    (`akai_s3000_writer.py:1984`); `wheel_to_lfo` is never consulted. The whole
    assignable `MODS*` matrix is likewise fixed factory defaults
    (`_PROGRAM_HW_DEFAULTS`, `:1798-1826`) — an amount without its matching
    source is silently inert on that machine, so nothing there is half-wired.

[^krzlfo2]: LFO2 (segment `0x15`) is written verbatim from the template
    (`krz_writer.py:1232`). The only LFO2 constant the writer touches is
    `KRZ_F4_AMP_SRC_LFO2` as a tremolo source (`:2021`).
