<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
-->

# Tempo-synced LFO rates (MPC <Sync> -> E4XT LFO Rate)

The MPC stores a tempo-sync **division** per LFO but the **tempo lives in the
project, not the .xpm** — and the E4XT cannot tempo-follow. Per the EOS 4.0
manual (p.260) the clock has only six divisions and a clock→LFO-Trigger cord
merely *resets* the LFO (the rate stays a fixed Hz; mismatched rates "radically
alter" the wave). mpc2emu therefore reproduces a synced LFO as a **fixed rate**
at a reference tempo (default **120 BPM**; set with `--lfo-sync-bpm`).

If your MPC project ran at a different tempo, set the E4XT LFO **Rate** by hand
from this table (Hz). Values at **0.08 / 18.01** are clamped to the E4XT LFO
range, so very slow (multi-bar) or very fast (32nd/triplet) syncs cannot be
reproduced exactly at all tempos.

| Sync | Division | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 | 140 | 150 | 160 | 170 | 180 | 190 | 200 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | whole | 0.25 | 0.29 | 0.33 | 0.38 | 0.42 | 0.46 | 0.50 | 0.54 | 0.58 | 0.62 | 0.67 | 0.71 | 0.75 | 0.79 | 0.83 |
| 2 | dotted half | 0.33 | 0.39 | 0.44 | 0.50 | 0.56 | 0.61 | 0.67 | 0.72 | 0.78 | 0.83 | 0.89 | 0.94 | 1.00 | 1.06 | 1.11 |
| 3 | half | 0.50 | 0.58 | 0.67 | 0.75 | 0.83 | 0.92 | 1.00 | 1.08 | 1.17 | 1.25 | 1.33 | 1.42 | 1.50 | 1.58 | 1.67 |
| 4 | dotted quarter | 0.67 | 0.78 | 0.89 | 1.00 | 1.11 | 1.22 | 1.33 | 1.44 | 1.56 | 1.67 | 1.78 | 1.89 | 2.00 | 2.11 | 2.22 |
| 5 | half triplet | 0.75 | 0.88 | 1.00 | 1.12 | 1.25 | 1.38 | 1.50 | 1.62 | 1.75 | 1.88 | 2.00 | 2.13 | 2.25 | 2.38 | 2.50 |
| 6 | quarter | 1.00 | 1.17 | 1.33 | 1.50 | 1.67 | 1.83 | 2.00 | 2.17 | 2.33 | 2.50 | 2.67 | 2.83 | 3.00 | 3.17 | 3.33 |
| 7 | dotted eighth | 1.33 | 1.56 | 1.78 | 2.00 | 2.22 | 2.44 | 2.67 | 2.89 | 3.11 | 3.33 | 3.56 | 3.78 | 4.00 | 4.22 | 4.44 |
| 8 | quarter triplet | 1.50 | 1.75 | 2.00 | 2.25 | 2.50 | 2.75 | 3.00 | 3.25 | 3.50 | 3.75 | 4.00 | 4.25 | 4.50 | 4.75 | 5.00 |
| 9 | eighth | 2.00 | 2.33 | 2.67 | 3.00 | 3.33 | 3.67 | 4.00 | 4.33 | 4.67 | 5.00 | 5.33 | 5.67 | 6.00 | 6.33 | 6.67 |
| 10 | dotted 16th | 2.67 | 3.11 | 3.56 | 4.00 | 4.44 | 4.89 | 5.33 | 5.78 | 6.22 | 6.67 | 7.11 | 7.56 | 8.00 | 8.44 | 8.89 |
| 11 | eighth triplet | 3.00 | 3.50 | 4.00 | 4.50 | 5.00 | 5.50 | 6.00 | 6.50 | 7.00 | 7.50 | 8.00 | 8.50 | 9.00 | 9.50 | 10.00 |
| 12 | sixteenth | 4.00 | 4.67 | 5.33 | 6.00 | 6.67 | 7.33 | 8.00 | 8.67 | 9.33 | 10.00 | 10.67 | 11.33 | 12.00 | 12.67 | 13.33 |
| 13 | 16th triplet | 6.00 | 7.00 | 8.00 | 9.00 | 10.00 | 11.00 | 12.00 | 13.00 | 14.00 | 15.00 | 16.00 | 17.00 | 18.00 | 18.01* | 18.01* |
| 14 | thirty second | 8.00 | 9.33 | 10.67 | 12.00 | 13.33 | 14.67 | 16.00 | 17.33 | 18.01* | 18.01* | 18.01* | 18.01* | 18.01* | 18.01* | 18.01* |
| 15 | 8 whole | 0.08* | 0.08* | 0.08* | 0.08* | 0.08* | 0.08* | 0.08* | 0.08* | 0.08* | 0.08* | 0.08 | 0.09 | 0.09 | 0.10 | 0.10 |
| 16 | 6 whole | 0.08* | 0.08* | 0.08* | 0.08* | 0.08* | 0.08* | 0.08 | 0.09 | 0.10 | 0.10 | 0.11 | 0.12 | 0.12 | 0.13 | 0.14 |
| 17 | 4 whole | 0.08* | 0.08* | 0.08 | 0.09 | 0.10 | 0.11 | 0.12 | 0.14 | 0.15 | 0.16 | 0.17 | 0.18 | 0.19 | 0.20 | 0.21 |
| 18 | 3 whole | 0.08 | 0.10 | 0.11 | 0.12 | 0.14 | 0.15 | 0.17 | 0.18 | 0.19 | 0.21 | 0.22 | 0.24 | 0.25 | 0.26 | 0.28 |
| 19 | 2 whole | 0.12 | 0.15 | 0.17 | 0.19 | 0.21 | 0.23 | 0.25 | 0.27 | 0.29 | 0.31 | 0.33 | 0.35 | 0.38 | 0.40 | 0.42 |
| 20 | dotted whole | 0.17 | 0.19 | 0.22 | 0.25 | 0.28 | 0.31 | 0.33 | 0.36 | 0.39 | 0.42 | 0.44 | 0.47 | 0.50 | 0.53 | 0.56 |

*\* clamped to the E4XT LFO range (0.08–18.01 Hz).*
