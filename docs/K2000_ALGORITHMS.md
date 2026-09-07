<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors

Measured and written by the k2kremote project (https://github.com/, local:
~/git-repos/k2kremote) on a Kurzweil K2000R, 2026-09-06/07, and contributed
here as the mpc2emu KRZ writer's reference. Raw artefacts, including the
per-code walk and the parser, are in ~/temp/k2k_algs/.
-->

# K2000 algorithm / DSP-function lookup table

> **Regenerating this table:** `docs/re_procedures/parse_k2000_algorithms.py`
> parses chapter 26 of the Reference Guide and emits
> `docs/re_procedures/k2000_algorithms.json`, from which this document is
> written. The parser is kept beside the data so the table can be rebuilt rather
> than trusted.

Source: Kurzweil K2000 Series **Reference Guide, chapter 26 'DSP Algs'**
(`26 DSP Algs.pdf`), extracted with `pdftotext -layout` and parsed by
`parse_algs.py`. This is the table the Musician's Guide points at when it
says "the Reference Guide contains a list of all 31 algorithms and the DSP
functions available for each one" (Musician's Guide p2781 of the text
extract). It is authoritative for **block chains and available functions**.

It does NOT give the **function code bytes** — those still need the device.

Algorithms 1-25 have five stages (PITCH plus F1-F4); **26-31 are the Sync
algorithms and have no PITCH stage**, four stages only.

`w` = stage width, i.e. how many of the five stage slots the block occupies,
derived from the diagram's input-arrow row. Marked `?` where the derivation
is not self-consistent — every one of those is an `AMP U`/`AMP L` pair, whose
separator glyph differs because the two blocks sit on different wires.

## Algorithm 1

`PITCH -> HIFREQ STIMULATOR -> AMP`  (w=[1, 3, 1], separators `trrtt`)

- **PITCH**: fixed (no alternatives)
- **HIFREQ STIMULATOR**: PARAMETRIC EQ, STEEP RESONANT BASS, 4POLE LOPASS W/SEP, 4POLE HIPASS W/SEP, TWIN PEAKS BANDPASS, DOUBLE NOTCH W/SEP, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 2

`PITCH -> 2PARAM SHAPER -> PANNER -> AMP`  (w=[1, 2, 1, 1], separators `trttt`)

- **PITCH**: fixed (no alternatives)
- **2PARAM SHAPER**: 2POLE LOWPASS, BANDPASS FILT, NOTCH FILTER, 2POLE ALLPASS, PARA BASS, PARA TREBLE, PARA MID, NONE
- **PANNER**: fixed (no alternatives)
- **AMP**: fixed (no alternatives)

## Algorithm 3

`PITCH -> 2PARAM SHAPER -> AMP U -> AMP L`  (w=?, separators `trtrt`)

- **PITCH**: fixed (no alternatives)
- **2PARAM SHAPER**: 2POLE LOWPASS, BANDPASS FILT, NOTCH FILTER, 2POLE ALLPASS, NONE
- **AMP U**: BAL
- **AMP L**: AMP

## Algorithm 4

`PITCH -> 2PARAM SHAPER -> LPCLIP -> AMP`  (w=[1, 2, 1, 1], separators `trttt`)

- **PITCH**: fixed (no alternatives)
- **2PARAM SHAPER**: 2POLE LOWPASS, BANDPASS FILT, NOTCH FILTER, 2POLE ALLPASS, PARA BASS, PARA TREBLE, PARA MID, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP, SAW+, SW+DST, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 5

`PITCH -> 2PARAM SHAPER -> LP2RES -> AMP`  (w=[1, 2, 1, 1], separators `trttt`)

- **PITCH**: fixed (no alternatives)
- **2PARAM SHAPER**: 2POLE LOWPASS, BANDPASS FILT, NOTCH FILTER, 2POLE ALLPASS, PARA BASS, PARA TREBLE, PARA MID, NONE
- **LP2RES**: SHAPE2, BAND2, NOTCH2, LOPAS2, HIPAS2, LPGATE, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 6

`PITCH -> 2PARAM SHAPER -> LPCLIP -> x AMP`  (w=[1, 2, 1, 1], separators `trttt`)

- **PITCH**: fixed (no alternatives)
- **2PARAM SHAPER**: 2POLE LOWPASS, BANDPASS FILT, NOTCH FILTER, 2POLE ALLPASS, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP
- **x AMP**: + AMP, ! AMP

## Algorithm 7

`PITCH -> 2PARAM SHAPER -> LPCLIP -> x AMP`  (w=[1, 2, 1, 1], separators `trTtt`)

- **PITCH**: fixed (no alternatives)
- **2PARAM SHAPER**: 2POLE LOWPASS, BANDPASS FILT, NOTCH FILTER, 2POLE ALLPASS, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SW+DST, NONE
- **x AMP**: + AMP, ! AMP

## Algorithm 8

`PITCH -> LOPASS -> LOPASS -> LPCLIP -> AMP`  (w=[1, 1, 1, 1, 1], separators `ttttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP, SAW+, WRAP, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP, SAW+, SW+DST, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 9

`PITCH -> LOPASS -> LOPASS -> LP2RES -> AMP`  (w=[1, 1, 1, 1, 1], separators `ttttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP, SAW+, WRAP, NONE
- **LP2RES**: SHAPE2, BAND2, NOTCH2, LOPAS2, HIPAS2, LPGATE, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 10

`PITCH -> LOPASS -> LOPASS -> LPCLIP -> x AMP`  (w=[1, 1, 1, 1, 1], separators `tTttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP, SAW+, SW+DST, NONE
- **x AMP**: + AMP, ! AMP

## Algorithm 11

`PITCH -> LOPASS -> LOPASS -> LPCLIP -> x AMP`  (w=[1, 1, 1, 1, 1], separators `tTttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SW+DST, NONE
- **x AMP**: + AMP, ! AMP

## Algorithm 12

`PITCH -> LOPASS -> LOPASS -> LPCLIP -> x AMP`  (w=[1, 1, 1, 1, 1], separators `ttttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP, SAW+, SW+DST, NONE
- **x AMP**: + AMP, ! AMP

## Algorithm 13

`PITCH -> LOPASS -> LOPASS -> PANNER -> AMP`  (w=[1, 1, 1, 1, 1], separators `ttttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP, SAW+, WRAP, NONE
- **PANNER**: fixed (no alternatives)
- **AMP**: fixed (no alternatives)

## Algorithm 14

`PITCH -> LOPASS -> LOPASS -> AMP U -> AMP L`  (w=?, separators `tTtrt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **AMP U**: BAL
- **AMP L**: AMP

## Algorithm 15

`PITCH -> LOPASS -> LOPASS -> AMP U -> AMP L`  (w=?, separators `tttrt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **AMP U**: BAL
- **AMP L**: AMP

## Algorithm 16

`PITCH -> LOPASS -> PARA BASS -> AMP`  (w=[1, 1, 2, 1], separators `ttrtt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **PARA BASS**: PARA TREBLE, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 17

`PITCH -> LOPASS -> SHAPE MOD OSC -> AMP`  (w=[1, 1, 2, 1], separators `ttrtt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, PWM, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **SHAPE MOD OSC**: AMP MOD OSC, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 18

`PITCH -> LOPASS -> x SHAPEMOD OSC -> AMP`  (w=[1, 1, 2, 1], separators `ttrtt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **x SHAPEMOD OSC**: + SHAPEMOD OSC, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 19

`PITCH -> LOPAS2 -> SHAPE MOD OSC -> AMP`  (w=[1, 1, 2, 1], separators `ttrtt`)

- **PITCH**: fixed (no alternatives)
- **LOPAS2**: NONE
- **SHAPE MOD OSC**: NONE
- **AMP**: fixed (no alternatives)

## Algorithm 20

`PITCH -> LOPASS -> x GAIN -> LPCLIP -> AMP`  (w=[1, 1, 1, 1, 1], separators `ttttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **x GAIN**: + GAIN, XFADE, AMPMOD, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SW+SHP, SAW+, SW+DST, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 21

`PITCH -> LOPASS -> x GAIN -> LP2RES -> AMP`  (w=[1, 1, 1, 1, 1], separators `ttttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **x GAIN**: + GAIN, XFADE, AMPMOD, NONE
- **LP2RES**: SHAPE2, BAND2, NOTCH2, LOPAS2, HIPAS2, LPGATE, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 22

`PITCH -> LOPASS -> x GAIN -> LPCLIP -> x AMP`  (w=[1, 1, 1, 1, 1], separators `tTttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **x GAIN**: + GAIN, XFADE, AMPMOD, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SW+DST, NONE
- **x AMP**: + AMP, ! AMP

## Algorithm 23

`PITCH -> LOPASS -> x GAIN -> LPCLIP -> x AMP`  (w=[1, 1, 1, 1, 1], separators `ttttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **x GAIN**: + GAIN, XFADE, AMPMOD, NONE
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SW+DST, NONE
- **x AMP**: + AMP, ! AMP

## Algorithm 24

`PITCH -> LOPASS -> x GAIN -> PANNER -> AMP`  (w=[1, 1, 1, 1, 1], separators `ttttt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **x GAIN**: + GAIN, XFADE, AMPMOD, NONE
- **PANNER**: fixed (no alternatives)
- **AMP**: fixed (no alternatives)

## Algorithm 25

`PITCH -> LOPASS -> x GAIN -> AMP U -> AMP L`  (w=?, separators `tTtrt`)

- **PITCH**: fixed (no alternatives)
- **LOPASS**: HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SAW, LF SAW, SQUARE, LF SQR, WRAP, NONE
- **x GAIN**: + GAIN, XFADE, AMPMOD, NONE
- **AMP U**: BAL
- **AMP L**: AMP

## Algorithm 26

`SYNC M -> SYNC S -> PANNER -> AMP`  (w=[1, 1, 1, 1], separators `tttt`)

- **SYNC M**: fixed (no alternatives)
- **SYNC S**: fixed (no alternatives)
- **PANNER**: fixed (no alternatives)
- **AMP**: fixed (no alternatives)

## Algorithm 27

`SYNC M -> SYNC S -> LPCLIP -> AMP`  (w=[1, 1, 1, 1], separators `tttt`)

- **SYNC M**: fixed (no alternatives)
- **SYNC S**: fixed (no alternatives)
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SW+DST, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 28

`SYNC M -> SYNC S -> LP2RES -> AMP`  (w=[1, 1, 1, 1], separators `tttt`)

- **SYNC M**: fixed (no alternatives)
- **SYNC S**: fixed (no alternatives)
- **LP2RES**: SHAPE2, BAND2, NOTCH2, LOPAS2, HIPAS2, LPGATE, NONE
- **AMP**: fixed (no alternatives)

## Algorithm 29

`SYNC M -> SYNC S -> LPCLIP -> x AMP`  (w=[1, 1, 1, 1], separators `tTtt`)

- **SYNC M**: fixed (no alternatives)
- **SYNC S**: fixed (no alternatives)
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SW+DST, NONE
- **x AMP**: + AMP, ! AMP

## Algorithm 30

`SYNC M -> SYNC S -> LPCLIP -> x AMP`  (w=[1, 1, 1, 1], separators `tttt`)

- **SYNC M**: fixed (no alternatives)
- **SYNC S**: fixed (no alternatives)
- **LPCLIP**: SINE+, NOISE+, LOPASS, HIPASS, ALPASS, GAIN, SHAPER, DIST, SINE, LF SIN, SW+SHP, SAW+, SW+DST, NONE
- **x AMP**: + AMP, ! AMP

## Algorithm 31

`SYNC M -> SYNC S -> AMP U -> AMP L`  (w=?, separators `ttrt`)

- **SYNC M**: fixed (no alternatives)
- **SYNC S**: fixed (no alternatives)
- **AMP U**: BAL
- **AMP L**: AMP

