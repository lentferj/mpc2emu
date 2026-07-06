# K2000 PARAMETRIC-EQ / band-boost DSP function — RE procedure

**Goal:** find the K2000 DSP-function bytes for the parametric-EQ family
(PARA MID / PARA BASS / PARA TREBLE) so MPC **Band Boost** filters (FilterType
19–22, "BB 2P/4P/6P/8P") can map to a real band *boost* instead of the current
2-pole BANDPASS approximation (`_K2_FILTER_2P_BP`), which removes the out-of-band
signal and sounds wrong (e.g. #204 Bass-MS20-Patch 2c).

Background: TODO.md "Band-Boost (BB) filters map to BANDPASS"; the fix strategy and
the (already-applied) E4B Swept-EQ counterpart are in
`docs/RESOLUTION_NOTES.md §BB`. Generator + diff tool:
`tests/re_banks/gen_krz_paramid_re.py`.

## Procedure (reverse RE, disk-save + byte-diff)

1. Build the bank:
   ```
   python3 tests/re_banks/gen_krz_paramid_re.py --floppy
   ```
   → `/home/lentferj/temp/krz_re/PARAMIDRE.KRZ` (+ `.img` floppy, it's tiny).
   6 programs, all starting from the SAME baseline: **Algorithm 1 / F1 = 4POLE
   LOPASS W/SEP**, sharing one sawtooth sample + full-range keymap. **P000 is the
   untouched reference.**

2. On the K2000R set **PARA MID** on each program. **HW finding 2026-06-25:**
   PARA MID is a parametric EQ spanning **two blocks** — **F1-FRQ** (center
   frequency: Coarse default **E5 / 659 Hz** + Fine cents) and **F2-AMP** (gain:
   "Adjust" **+48 dB … −48 dB**, default 0 dB). MPC `Cutoff`→FRQ, MPC band-boost
   gain→AMP. We decode BOTH laws in one save — 3 frequency points (AMP=0) and
   3 gain points (FRQ=E5):
   | Program | F1-FRQ | F2-AMP |
   |---|---|---|
   | P001 (was "ctr")  | E5 (default) | 0 dB |
   | P002 (was "+max") | **C0/16Hz** (low) | 0 dB |
   | P003 (was "-max") | **G10/25088Hz** (high)| 0 dB |
   | P004 PARABASS set | E5 (default) | **+24 dB** |
   | P005 PARATREB set | E5 (default) | **+48 dB** |
   Play C4 sustained: P004/P005 should audibly **boost** the band. (PARA BASS/
   TREBLE shelves are not needed for BB and are dropped from this run.)

3. **Save the bank** (Master → Save) and copy the saved `.KRZ` back to the PC.

4. Read off the changed bytes with TWO reference passes:
   ```
   # vs P200 (Alg1 4POLE LOPASS) — shows the full Algorithm-2 + PARA MID setup:
   python3 tests/re_banks/gen_krz_paramid_re.py --diff /path/to/SAVED.KRZ --ref 0
   # vs P201 (PARA MID baseline, same Alg2) — isolates ONLY the FRQ/AMP bytes:
   python3 tests/re_banks/gen_krz_paramid_re.py --diff /path/to/SAVED.KRZ --ref 1
   ```

**HW finding 2026-06-25 (manual):** PARA MID/BASS/TREBLE live in **Algorithm 2**.
Algorithm-2 F-block function menu order: 2Param Shaper, 2Pole LP, BP Filt, Notch
Filter, 2Pole Allpass, Para Bass, Para Treble, Para Mid, None. Selecting Alg 2
defaults to **2Pole LP**. So the PARA MID programs are CAL[29]=2 (the `--ref 1`
pass cancels the algorithm difference and leaves only FRQ/AMP). FRQ range is
**16 Hz (C0) … 25088 Hz (G10)** = the standard K2000 filter range = our existing
`_cutoff_byte`, so MPC `Cutoff`→FRQ reuses that law directly. AMP "Adjust" is
**+48 … −48 dB** (default 0).

## Results to capture (fill in)

PARA MID = F1-FRQ + F2-AMP (two blocks). **RESULTS — captured 2026-06-25 from
PARAJLZ.KRZ (disk-save diff):**

| Param | Segment·byte | Value | Notes |
|---|---|---|---|
| Algorithm       | CAL(0x40)[29] | **2** | (4POLE LOPASS baseline was 1) |
| F1-FRQ function | HOB0(0x50)[0] | **51** | PARA MID FRQ |
| Center freq     | HOB0(0x50)[1] | signed −48…+79 | **= existing `_cutoff_byte`**: C0/16Hz=−48(208), E5≈16, G10/25088=+79 |
| F2-AMP function | HOB1(0x51)[0] | **16** | AMP block (constant; =`_K2_F2_RES` value) |
| Gain (AMP)      | HOB1(0x51)[1] | **dB, 1:1 signed** | 0 dB→0, +24→24, +48→48 (range ±48) |
| F3 block        | HOB2(0x52)[0] | **40** | None (Alg-2 separator; was 18 W/SEP) |

**Wired into `writers/krz_writer.py`** (2026-06-25): `_k2_filter_plan` routes BB
19–22 → `(2, _K2_FILTER_PARA_MID=51, _K2_F2_AMP=16, _K2_F3_NONE_ALG2=40)`;
`_patch_layer` sets HOB0[1]=`_cutoff_byte(cutoff)` and HOB1[1]=`+12..+24 dB` from
resonance. Verified end-to-end on #204 Bass-MS20-Patch. Note: P201 ("ctr") was not
edited on HW, so the E5/0 dB baseline came from P204/P205 (FRQ unchanged) instead.

## Wire-up once known

In `writers/krz_writer.py`:
- add `_K2_FILTER_PARA_MID = <byte>` (+ BASS/TREBLE) and any F2/F3/algorithm const;
- in `_k2_filter_plan`, route `xpm_type in (19,20,21,22)` (BB) → the PARA-MID plan
  instead of the current `_K2_FILTER_2P_BP`;
- map MPC `Cutoff` → center freq and `Resonance` → boost gain (sign +, mirroring
  the E4B Swept-EQ boost in §BB).
Then rebuild #204 and re-verify by ear vs the MPC original.
