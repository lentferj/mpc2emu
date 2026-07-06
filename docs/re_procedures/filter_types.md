<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# Hardware RE: Swept EQ Filter Type Bytes

## Goal

Find the `vpar[58]` byte values for E4XT filter types not yet identified
(swept/parametric EQ and any others not in the confirmed list).

---

## Background

Confirmed `vpar[58]` filter type bytes (from `FLTTYPES.E4B`, `FLTTYPES2.E4B`,
JL AnalogBank K2 Bass):

| E4XT filter type | vpar[58] | Status |
|---|---|---|
| 4-Pole LP (4PLP) | 0x00 | confirmed |
| 2-Pole LP (2PLP) | 0x01 | confirmed |
| 6-Pole LP (6PLP) | 0x02 | confirmed |
| 2nd-Order HP     | 0x08 | confirmed |
| 4th-Order HP     | 0x09 | confirmed |
| 2nd-Order BP     | 0x10 | confirmed |
| 4th-Order BP     | 0x11 | confirmed |
| Contrary BP (notch-like) | 0x12 | inferred (pattern: base 0x10 + 2) |

Unknown / not yet found:
- Any "Sweep" or "EQ" or parametric filter modes shown in EOS voice editor
- Whether values 0x03–0x07, 0x0A–0x0F, 0x13+ are valid

---

## Step 1: Check the EOS voice editor

On the E4XT, go to Voice Edit → Filter page.  Cycle through all available
filter types using the data wheel.  Write down every type name that appears
(e.g. "4PLP", "6PLP", "NOTCH", "2EQP", "S.EQ" etc.).

---

## Step 2: Create one-voice presets for each unknown type

For each filter type whose byte value is unknown:
1. Create a new preset on E4XT with one voice using that filter type.
2. Keep all other parameters identical (same sample, key range, cutoff, resonance).
3. Save all presets together in one bank as E4B.

---

## Step 3: Binary-inspect vpar[58]

Parse the saved E4B:
```bash
python3 -c "
from parsers.e4b_parser import parse_e4b
b = parse_e4b('/path/to/FILTER_TYPES_TEST.E4B')
for p in b.presets:
    print(p.name)
    for v in p.voices:
        print(f'  filter_type byte={v.filter_type}')
"
```

The `e4b_parser` already reads `vpar[58]` via `_E4B_TO_XPM_FILTER_TYPE`.
For unknown bytes, the parser returns `filter_type=0`.  To see the raw byte
value, add a debug print in `_parse_voice()` before the lookup:
```python
print(f'  raw filter byte: 0x{filter_byte:02X}')
```

---

## Step 4: Update the code

For each confirmed new byte value, add entries to both tables:

In `e4b_writer.py` (`_XPM_FILTER_TYPE`):
- Map the closest MPC `FilterType` integer → new E4XT byte

In `e4b_parser.py` (`_E4B_TO_XPM_FILTER_TYPE`):
- Map the new E4XT byte → closest XPM FilterType integer

Update `E4B_FORMAT.md` §4.4 and remove the swept EQ TODO from `TODO.md`.
