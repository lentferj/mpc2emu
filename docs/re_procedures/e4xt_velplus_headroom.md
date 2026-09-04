# Does a `Vel+` voice have headroom above nominal, or does it clip?

**Status:** disc built and staged 2026-09-04, not yet run.
**Generator:** `tests/re_banks/gen_e4xt_velplus_headroom.py`
**Runner:** `tests/re_banks/measure_e4xt_velplus.py`
**On the card:** `CD1-VELPLUS.iso`, SCSI id 1
**Needs:** the E4XT, the measurement rig, ~3 minutes of recording. No panel
editing, no bank authoring, nobody at the rack after the first note.

## Why

Our E4B writer emits velocity→volume as `Vel<` (pivot 127, so the cord only
ever attenuates). The reason on record was that `Vel<` is what the machine and
its factory library use — which the corpus census of 2026-09-04 refuted
(§E4XTVELSRC). A commercial EOS-native library CD-ROM is **96.9 % `Vel+`**:
11,449 of 11,806 voices across 2,035 presets.

`Vel+` pivots at velocity 0, so it puts v127 at nominal **plus** the whole
swing. That should clip. The same census says the library disagrees — those
11,449 voices budget no headroom at all:

    mean swing            28.6 dB
    mean static level     -2.9 dB   (median 0.0, p10 -14.5, p90 +10.0)
    corr(swing, level)    +0.068

Both cannot be true. Either the E4XT has ~30 dB above what the volume field
calls nominal, or a large commercial library clips as a matter of course. This
is the only thing standing between here and a defensible choice of cord source,
and it is one capture.

## The disc

**One preset, thirteen voices, one key each** — not thirteen presets. The cord
is a per-voice object, so the whole comparison fits in one program and the run
needs no program changes: one capture, 65 notes, one gain staging shared by
every reading. Thirteen presets would have meant thirteen captures, and
`play_sequence` registers a JACK client per capture — s3ked hit a ceiling near
eight before the server stopped accepting clients. It also deletes the entire
class of program-walk desynchronisation the other anchor banks need controls
for.

| key | voice | source | amount | sample |
|---|---|---|---|---|
| 48 | CTL-A | none | — | sine, full scale |
| 49 | VLESS 30 | `Vel<` | 30 % | sine, full scale |
| 50–54 | A VPLUS 10/20/30/40/60 | `Vel+` | 10–60 % | sine, full scale |
| 55–59 | B VPLUS 10/20/30/40/60 | `Vel+` | 10–60 % | same sine, −20 dB |
| 60 | CTL-B | none | — | sine, full scale |

Every voice is rooted on its own key, so the sine plays at unity rate
everywhere and no resampler sits between the cord and the reading. Five
velocities each: 1, 32, 64, 96, 127.

**The two sample levels are what make this an experiment rather than a yes/no.**
If the ceiling belongs to the ENGINE, both series cap at the same absolute
level and the quiet one reaches it 20 dB later in cord amount. If it belongs to
the SAMPLE's own headroom, the loud series clips where the quiet one does not,
at the same amount. One capture separates two hypotheses a single-level test
would leave tangled.

## Controls, and they are not optional

* **CTL-A and CTL-B are the same voice**, on the lowest and highest key, played
  first and last. They straddle both the keyboard span and the three minutes of
  recording: if they disagree, either the level depends on the key or the
  capture drifted, and the run is void either way. The runner checks this and
  says so.
* **The control voice is also the velocity negative control.** It carries no
  cord at all — not an amount-0 cord, which the writer's three-state logic
  omits entirely — and is played at all five velocities. Any velocity response
  the E4XT applies on its own shows up there and is subtracted from every other
  reading instead of being attributed to the cord.
* **Key 49 is a `Vel<` fingerprint** at the same amount as key 52: equal to the
  control at v127 and 28 dB below it at v1. Nothing else in the bank has that
  shape, so a key/label mix-up in the analysis is visible rather than merely
  possible.
* **A pure sine, deliberately** — not the harmonic tone the other E4XT anchor
  banks use. The observable is not only level but DISTORTION, and a clipped sine
  grows harmonics a THD reading finds unambiguously. A tone that already has
  eleven of them hides it completely.

## Running it

```
python3 tests/re_banks/measure_e4xt_velplus.py gain      # set the input trim
python3 tests/re_banks/measure_e4xt_velplus.py capture   # ONE recording, ~2.5 min
python3 tests/re_banks/measure_e4xt_velplus.py analyse
```

**Set the trim against the LOUDEST note, not the first.** `A VPLUS 60` at v127
predicts +57 dB over the control. If the interface clips there, the capture
reports a ceiling belonging to the Scarlett and we would publish it as the
E4XT's — §GATESUBJECT in its purest form: a real ceiling, measured accurately,
belonging to the wrong subject. `gain` loops that one note so everything else in
the run is below it by construction.

On the machine: Load → CD-ROM (id 1) → bank `VELPLUS` → preset `VELPLUS HDRM`.

## What the answer looks like

The measured-vs-predicted grid, plus THD per cell. The answer is the first cell
that falls short of prediction and **how** it falls short:

* **THD up** → it clips. The library's `Vel+` voices distort and we should not
  copy them; `Vel<` stays, now for a measured reason.
* **THD flat, level bends** → a soft ceiling. Report the largest prediction that
  still arrives; that is the usable headroom above nominal.
* **Nothing falls short** → the E4XT has the headroom the library assumes, and
  `Vel+` becomes a real option. It still would not change the velocity
  *response* — all three sources draw the same line at one measured slope
  (0.9462 dB/%) and differ only in where it crosses zero — so it remains a
  choice about where the preset's level sits, made on evidence instead of on my
  assumption.

## Card note

CD1 previously held `E4XT_COMPARE`. It was **renamed, not deleted** — the bytes
are still on the card as `XX_CD1-E4XT_COMPARE.iso` and one rename restores it.
Its older `~/temp/CD1-E4XT_COMPARE-backup.iso` is **stale** and differs from
what was live, so the live bytes were backed up byte-verified first at
`~/temp/CD1-E4XT_COMPARE-live-20260904.iso`. HD0 was read (FAT32, via mtools)
and never written.
