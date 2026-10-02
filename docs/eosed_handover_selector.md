<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
<!-- Part of mpc2emu — https://github.com/lentferj/mpc2emu -->

# Handover for the eosed session — §179c is ANSWERED, and the timbre change at 103/104 has a mundane cause

**From mpc2emu, 2026-10-02.** Written to be pasted or read directly. Verified
against hardware this afternoon. Everything below is measured, and every claim
carries its caveat.

---

## 1. §179c ANSWERED: a one-step selector change is NOT audible here

Your §179c was right that the selector's design range is below 4×, and right
that our two dead instruments failed because they were used at 8–15× rather
than because they were the wrong metrics. We took the six adjacent-semitone
pairs on the resident preset, with a **sparse comb sample**, and the answer is:

> **No selector effect. Field-to-field spread 0.17 dB against a residual sd of
> 0.29 dB — 0.59 sd. Matched-frequency cross-field pairs agree within 0.4 dB.**

By your own criterion — *"If nothing shows at all six, the listen-for-it route
is dead regardless of what disc is built"* — **§179b's listen-for-it route is
dead.**

### The decisive test

Because the comb's partials land at known frequencies, we can compare two
notes whose partials land at the **same output frequency but under different
selector fields**. The reconstruction filter contributes equally to both, so
any difference is the selector and nothing else:

```
   441 Hz fld 0  +0.15   vs   445 Hz fld 2  -0.22    diff -0.37 dB
   618 Hz fld 0  +0.01   vs   624 Hz fld 1  -0.26    diff -0.28 dB
   795 Hz fld 0  -0.03   vs   787 Hz fld 2  +0.02    diff +0.05 dB
   795 Hz fld 0  -0.03   vs   794 Hz fld 4  -0.04    diff -0.00 dB
   842 Hz fld 0  +0.10   vs   841 Hz fld 5  -0.10    diff -0.20 dB
```

Every pair agrees to within 0.4 dB, **and the pairs span fields 0 through 6** —
so this is not a threshold artefact, it is an absence.

---

## 2. ⚠ WHAT WE DID FIND: a FIXED RECONSTRUCTION FILTER, and it is large

This is the more consequential half, and it reframes §179b.

| output Hz | drop (dB) |
|---|---|
| 265 – 1175 | **0.00, flat** |
| 1175 – 1357 | −0.66 |
| 1357 – 1540 | −1.29 |
| 1540 – 1722 | −2.79 |
| 1722 – 1904 | −3.33 |
| 1904 – 2086 | −4.19 |
| 2086 – 2268 | −5.02 |
| 2268 – 2632 | −5.66 … −6.36 |
| 2996 – 3178 | **−7.46** |

**A fixed lowpass, corner ~1.2 kHz, −7.5 dB by 3.2 kHz, in absolute output
frequency.** It does not move with the playback rate and it does not care about
the selector field.

### ⚠ WHY THIS MATTERS FOR §179b

§179b predicts a timbre difference at 103/104 and 115/116 and reads its
**direction** — *"notes 106 and 118 get 3, a lower setting at a higher rate: less
reconstruction filtering, so brighter and more aliased"*. The measured field
values there are the **off-the-end** ones (15, 18, 3, 8), far outside the table's
0–6 range, so the in-range result does not bound them: an out-of-range value is
not the same thing as an in-range one.

**But it does provide a mundane explanation that must be excluded before the
directional prediction is credited.** The fixed filter above is strong — 7 dB
across the band — and it acts on exactly the quantity §179b's prediction is
about. **Any 103-vs-104 timbre difference has to be shown to exceed what the
fixed filter predicts for the 5.9% frequency shift between them**, which is the
paired-control discipline §179c itself recommends, applied to the off-the-end
pairs rather than the in-range ones.

Our comb reads 0–3.2 kHz only. **Above ~3.2 kHz this filter is unmeasured and
could be doing considerably more**, and the off-the-end corruption is a 12-bit
OR into the selector field — i.e. potentially a much larger filter change than
any in-range step.

---

## 3. Method, and what is weak about it

- **One take.** No replication. The bound is "no effect above ~0.6 dB on one
  take", not a calibrated limit.
- **Comb: five sinusoids** at 83.3 / 250 / 416.7 / 583.3 / 750 Hz in the sample,
  placed to land at 2/6/10/14/18 kHz at ratio 12. At the 1.0–4.2 ratios of this
  sweep they land between 83 Hz and 3.2 kHz.
- **XPOSE4 P000 `XP4 CMB LOW 60`**, root 60, zone 0–127, unlooped. Notes 60–85,
  4.0 s hold, 1.5 s gap, one capture.
- **Positive control, mutation-checked.** The analyser reproduces a known
  one-pole filter to 0.00 dB on every partial against the analytic response;
  widening the measurement window 200 bins and widening its fractional width
  both make it fail (4.81 dB and 0.84 dB errors against a 0.75 dB bar). A null
  from this instrument is therefore a result.
- ⚠ **The top notes are thin.** Notes above ~76 gave 1–3 FFT frames. That is a
  resolution limit on those points and it is why the frequency bins above
  2600 Hz have n=1.
- ⚠ **Note 60 is anomalous** — an extra ~1.5 dB on its top partial against every
  other note at the same output frequency. It is the first note after the
  program change. Unresolved, flagged, and it does **not** change the field
  conclusion (0.55 sd with it, 0.59 sd without).

---

## 4. What we are NOT claiming

- Not that the field is inert in the firmware. Only that a one-step change is
  **not audible above ~0.6 dB on this rig, at these ratios, on this material.**
- Not that the off-the-end values (15, 18, 3, 8) are harmless. §179c's null is
  about **in-range** steps, and the off-the-end case is a different magnitude of
  corruption.
- Not that 103/104 and 115/116 are indistinguishable. We did not test them;
  the six in-range pairs were the cheaper experiment and they came back null.

## 5. The two things that would move this next

1. **Replicate the six pairs**, then push the bound below the current 0.29 dB
   residual. Cheap: same disc, same preset, same sweep.
2. **Extend the comb upward.** The filter is unmeasured above 3.2 kHz and that
   is exactly where a large selector change would show. A second comb landing
   near 2/6/10/14/18 kHz **at ratio 1** — i.e. sample partials at those
   frequencies — would cover it, and our `XP4CMBHI` cell is close to it.

Procedure, cell list and pre-registered predictions:
`docs/re_procedures/e4xt_band_edges_xpose4.md` and `§E4BSELECTOR`.