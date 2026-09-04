# What does the E4XT voice-volume byte actually deliver below −22.9 dB?

**Status:** disc built and staged 2026-09-04, not yet run.
**Generator:** `tests/re_banks/gen_e4xt_volcal.py`
**Runner:** `tests/re_banks/measure_e4xt_volcal.py`
**On the card:** `CD1-VELPLUS-VOLCAL.iso`, SCSI id 1, bank `VOLCAL`
**Needs:** the E4XT and the rig. ~1 minute of recording.

## Why

`e4xt_volume_byte` inverts a quadratic fitted over **0 to −22.90 dB**.
`E4XT_VOL_MEASURED_FLOOR_DB` marks where the *measurement* stopped, not where
the field does — the byte reaches about −94 dB by the model and the law stays
monotonic all the way. Below the floor the writer is therefore
**extrapolating**: monotonic, but not a measured number of dB.

Until 2026-09-04 that hardly mattered, because nothing asked for it. Then
`Vel+` landed (§E4XTVELSRC) and the velocity-pivot trim began writing static
levels ~20 dB past the fit on MPC material. The curve fit of §MPCVELSHAPE has
since pulled those back to about −14 dB, **inside** the calibrated range, so
this is no longer urgent.

It is still worth one capture, for two reasons that outlive the pivot work:
the field carries **every zone and voice level we write**, not only the trim;
and the run re-measures the already-fitted region, so it either confirms the
2026-07-31 law on today's rig or tells us the two disagree.

## The disc

One preset, sixteen voices, one key each, identical except the byte in
`vpar[54]`:

| keys | bytes | region |
|---|---|---|
| 48 | 0 | control |
| 49–57 | −2 −4 −6 −8 −12 −16 −20 −24 −30 | already fitted (0 to −22.8 dB) |
| 58–62 | −36 −44 −52 −64 −80 | **extrapolated** (−27.3 to −59.8 dB) |
| 63 | 0 | control |

**The bytes are patched in directly, not written through `e4xt_volume_byte`.**
That mapping is the thing under test; a calibration that used it would be
measuring its own assumption.

**Half the sweep re-measures ground the existing fit already covers**, and that
is the part that makes the other half trustworthy. A calibration that only
walks new ground cannot separate "the law changes here" from "my rig differs
from the rig that measured the old points". The runner reports that comparison
as its own line.

## Controls

* **Byte 0 on the lowest and highest key**, played first and last — they
  straddle both the keyboard span and the recording. If they disagree by more
  than a dB the run is void, and the runner says so.
* **Two velocities per voice.** No velocity cord is written, so the two must
  agree. A free check that nothing velocity-dependent is contaminating a
  measurement about a static field.
* **A pure sine.** The level is read from one FFT bin, so the floor that
  matters is the noise *in that bin* — which is what makes a 60 dB sweep
  survivable at all. The runner measures that floor from the capture's own
  lead-in and excludes any cell within 10 dB of it.

## Running it

```
python3 tests/re_banks/measure_e4xt_volcal.py gain      # identity + trim
python3 tests/re_banks/measure_e4xt_volcal.py capture   # ONE recording, ~1 min
python3 tests/re_banks/measure_e4xt_volcal.py analyse
```

On the machine: Load → CD-ROM (id 1) → bank **`VOLCAL`** → preset `VOLCAL`.
Loading a bank on its own makes its preset **program 0**; the runner sends that.
Only if you *merge* VELPLUS and VOLCAL into one RAM bank does VOLCAL become
program 1, and `--program 1` covers that.

**The identity check is a level ladder:** key 48 (byte 0) against key 62
(byte −80), about 60 dB apart. VELPLUS shares the disc and cannot imitate that
on those keys, so hearing full-then-barely-there identifies the bank by effect
rather than by a screen that says the right thing.

**Set the trim on key 48.** The sweep runs 60 dB below it, so extra headroom at
the top is paid for at the bottom.

## What comes back

Measured dB per byte, the error against the shipped law, and a refit of the
**same** `C1·b + C2·b²` shape so the result is a drop-in replacement rather than
a different model. Three RMS figures are printed:

- the refit over all usable points,
- the shipped law over the same points,
- **the shipped law over the already-fitted points only** — which validates the
  rig against the 2026-07-31 measurement. If that one is large, the
  disagreement is the rig and not the law, and nothing below it should be
  believed.
