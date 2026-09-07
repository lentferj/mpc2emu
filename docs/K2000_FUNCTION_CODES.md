<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors

Measured and written by the k2kremote project (https://github.com/, local:
~/git-repos/k2kremote) on a Kurzweil K2000R, 2026-09-06/07, and contributed
here as the mpc2emu KRZ writer's reference. Raw artefacts, including the
per-code walk and the parser, are in ~/temp/k2k_algs/.
-->

# K2000 DSP function codes — measured on the device

Companion to `K2000_ALGORITHMS.md`, which lists what each algorithm offers.
This lists what each function's **stored byte** is.

Block type bytes live at Program-object offsets **F1 209, F2 225, F3 241,
F4 257** — all four measured by DUMP-diff, none inferred from the spacing.

**The codes are per block, not global.** The same function has different
bytes in different blocks (see NONE, PARA BASS, PARA TREBLE below), so a
byte only means something together with the block it sits in.

Method: typing a number into a block field on the ALG page selects the
function by its code, and a dump taken with the editor still open reflects
the edit buffer — so each row is a (typed code, panel name, stored byte)
triple. Where a block refuses a code it returns another legal function of
that block, so only rows whose byte was read at the block's own offset are
recorded here.

| Function | Byte | Blocks |
|---|---|---|
| `AMP` | 1 | *:F4 AMP (F4) |
| `2POLE LOWPASS` | 2 | 5:1 (F1), 2:1 (F1) |
| `BANDPASS FILT` | 3 | 5:1 (F1), 2:1 (F1) |
| `NOTCH FILTER` | 4 | 5:1 (F1), 2:1 (F1) |
| `2POLE ALLPASS` | 5 | 5:1 (F1), 2:1 (F1) |
| `PARA BASS` | 8 | 5:1 (F1), 2:1 (F1) |
| `PARA BASS` | 10 | 16:2 (F2) |
| `PARA TREBLE` | 9 | 5:1 (F1), 2:1 (F1) |
| `PARA TREBLE` | 11 | 16:2 (F2) |
| `HIFREQ STIMULATOR` | 12 | 1:1 (F1) |
| `PARAMETRIC EQ` | 13 | 1:1 (F1) |
| `STEEP RESONANT BASS` | 14 | 1:1 (F1) |
| `LOPASS` | 15 | 12:1 (F1), 12:2 (F2), 12:3 (F3) |
| `HIPASS` | 16 | 12:1 (F1), 12:2 (F2), 12:3 (F3) |
| `ALPASS` | 17 | 12:1 (F1), 12:2 (F2), 12:3 (F3) |
| `GAIN` | 18 | 12:1 (F1), 12:2 (F2), 12:3 (F3) |
| `SHAPER` | 19 | 12:1 (F1), 12:2 (F2), 12:3 (F3) |
| `DIST` | 20 | 12:1 (F1), 12:2 (F2), 12:3 (F3) |
| `PWM` | 22 | 12:1 (F1), 12:2 (F2) |
| `SINE` | 23 | 12:1 (F1), 12:2 (F2) |
| `LF SIN` | 24 | 12:1 (F1), 12:2 (F2) |
| `SW+SHP` | 25 | 12:1 (F1), 12:2 (F2), 12:3 (F3) |
| `SAW+` | 26 | 12:1 (F1), 12:2 (F2), 12:3 (F3) |
| `SAW` | 27 | 12:1 (F1), 12:2 (F2) |
| `LF SAW` | 28 | 12:1 (F1), 12:2 (F2) |
| `SQUARE` | 29 | 12:1 (F1), 12:2 (F2) |
| `LF SQR` | 30 | 12:1 (F1), 12:2 (F2) |
| `WRAP` | 31 | 12:1 (F1), 12:2 (F2) |
| `SYNC M` | 33 | 26:1 (F1) |
| `SYNC S` | 34 | 26:2 (F2) |
| `BAND2` | 35 | 5:2 (F3) |
| `NOTCH2` | 36 | 5:2 (F3) |
| `LOPAS2` | 37 | 5:2 (F3) |
| `AMP U   AMP L` | 38 | 3:2 (F3) |
| `BAL     AMP` | 39 | 3:2 (F3) |
| `PANNER` | 40 | 26:3 (F3) |
| `x GAIN` | 41 | 21:2 (F2) |
| `+ GAIN` | 42 | 21:2 (F2) |
| `XFADE` | 43 | 21:2 (F2) |
| `AMPMOD` | 44 | 21:2 (F2) |
| `x AMP` | 48 | 12:4 (F4), 6:3 (F4) |
| `+ AMP` | 49 | 12:4 (F4), 6:3 (F4) |
| `4POLE LOPASS W/SEP` | 50 | 1:1 (F1) |
| `PARA MID` | 51 | 5:1 (F1), 2:1 (F1) |
| `HIPAS2` | 52 | 5:2 (F3) |
| `SW+DST` | 53 | 12:3 (F3) |
| `4POLE HIPASS W/SEP` | 54 | 1:1 (F1) |
| `TWIN PEAKS BANDPASS` | 55 | 1:1 (F1) |
| `DOUBLE NOTCH W/SEP` | 56 | 1:1 (F1) |
| `LPGATE` | 57 | 5:2 (F3) |
| `NONE` | 60 | 12:1 (F1), 12:2 (F2), 12:3 (F3), 5:2 (F3) |
| `NONE` | 61 | 5:1 (F1), 2:1 (F1), 17:2 (F2), 18:2 (F2), 16:2 (F2) |
| `NONE` | 62 | 1:1 (F1) |
| `NONE` | 63 | 21:2 (F2) |
| `2PARAM SHAPER` | 64 | 5:1 (F1), 2:1 (F1) |
| `x SHAPEMOD OSC` | 66 | 18:2 (F2) |
| `+ SHAPEMOD OSC` | 67 | 18:2 (F2) |
| `SHAPE MOD OSC` | 68 | 17:2 (F2) |
| `LPCLIP` | 70 | 12:3 (F3) |
| `SINE+` | 71 | 12:3 (F3) |
| `AMP MOD OSC` | 72 | 17:2 (F2) |
| `LP2RES` | 73 | 5:2 (F3) |
| `SHAPE2` | 74 | 5:2 (F3) |
| `! AMP` | 75 | 12:4 (F4), 6:3 (F4) |
| `NOISE+` | 76 | 12:3 (F3) |

## Block-dependent functions

These are the ones that would break a global lookup:

- **NONE**: 60 in 12:1 (F1), 12:2 (F2), 12:3 (F3), 5:2 (F3); 61 in 5:1 (F1), 2:1 (F1), 17:2 (F2), 18:2 (F2), 16:2 (F2); 62 in 1:1 (F1); 63 in 21:2 (F2)
- **PARA BASS**: 8 in 5:1 (F1), 2:1 (F1); 10 in 16:2 (F2)
- **PARA TREBLE**: 9 in 5:1 (F1), 2:1 (F1); 11 in 16:2 (F2)
