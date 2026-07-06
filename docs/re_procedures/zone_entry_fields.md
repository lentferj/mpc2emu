<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# Hardware RE: Zone Entry `fine_tune` and `volume` Fields

## Goal

Identify the byte offsets within the 22-byte secondary zone entry that encode
per-zone fine-tune (cents) and per-zone volume (dB / gain trim).

---

## Background

The 22-byte secondary zone entry (`_zone_entry()` in `e4b_writer.py`) currently
writes only 6 of 22 bytes:

```
[0-1]   unknown (written as 0x00 0x00)
[2]     lo_key   ← confirmed
[3-4]   unknown
[5]     hi_key   ← confirmed
[6]     lo_vel   ← confirmed
[7-8]   unknown
[9]     hi_vel   ← confirmed
[10:12] sample_idx BE u16  ← confirmed
[12-13] unknown
[14]    root_key ← confirmed
[15-21] unknown (7 bytes written as zero)
```

The GIG and EXS24 parsers extract per-zone fine_tune and volume but cannot
write them because offsets [12], [13], [0], [1], and [15–21] are unidentified.

---

## Step 1: Generate test banks

```bash
cd /home/lentferj/git-repos/mpc2emu
python3 tests/re_banks/gen_zone_entry_test.py
```

Produces in `/home/lentferj/temp/re_zone_entry/`:

**Fine-tune test banks** (all other params identical):
- `ZONE_FINE_00.E4B` — fine_tune = 0 cents
- `ZONE_FINE_50.E4B` — fine_tune = +50 cents
- `ZONE_FINE_N50.E4B` — fine_tune = −50 cents

**Volume test banks**:
- `ZONE_VOL_0DB.E4B` — per-zone volume = 0 dB (reference)
- `ZONE_VOL_N12.E4B` — per-zone volume = −12 dB
- `ZONE_VOL_N24.E4B` — per-zone volume = −24 dB

---

## Step 2: Binary diff to find the fields

After generating the test banks, run:

```bash
python3 -c "
import sys
a = open('$TEMP/re_zone_entry/ZONE_FINE_00.E4B', 'rb').read()
b = open('$TEMP/re_zone_entry/ZONE_FINE_50.E4B', 'rb').read()
diffs = [(i, a[i], b[i]) for i in range(min(len(a),len(b))) if a[i] != b[i]]
for i,x,y in diffs[:20]:
    print(f'  byte {i:5d}: 0x{x:02X} -> 0x{y:02X}  (delta {y-x})')
"
```

The changing bytes are the candidates for fine_tune.  Map them back to the
zone entry by computing `(offset - zone_entry_start) % 22`.

To find `zone_entry_start`: it is `PRES_HDR + VOICE_FIXED = 82 + 284 = 366`
bytes into the first E4P1 chunk body (for a one-voice, one-zone preset).
In the file, the E4P1 chunk starts after `FORM(12) + TOC1_chunk + E4Ma_chunk`.
The test bank generator prints the exact byte offset; look for it in the output.

---

## Step 3: Verify on hardware

1. Load `ZONE_FINE_00.E4B` and `ZONE_FINE_50.E4B` on E4XT.
2. Play the same note (C4=60) on both.  `ZONE_FINE_50.E4B` should sound
   approximately 50 cents sharper (a quarter-tone up).
3. If you can, use a tuner to confirm the pitch difference is ~50 cents.

For volume: load `ZONE_VOL_0DB.E4B` and `ZONE_VOL_N12.E4B`; the second
should sound about 12 dB quieter.

---

## Step 4: Determine encoding

**fine_tune:** expect a signed byte (`-100` to `+100` cents), stored as
two's complement (`struct.pack('b', value)`) or offset binary (add 128).

**volume:** expect either:
- A signed byte in dB (`-128..+127`)
- A 7-bit unsigned level (like the filter resonance: `0..127`)
- A 0–127 linear scale where 127 = 0 dB and lower = quieter

---

## Step 5: Update the code

Once offsets are confirmed, update `_zone_entry()` in `e4b_writer.py`:

```python
def _zone_entry(zone: ZoneMapping, sample_idx: int) -> bytes:
    entry = bytearray(ZONE_ENTRY)
    entry[2]  = min(127, zone.lo_key)
    entry[5]  = min(127, zone.hi_key)
    entry[6]  = min(127, zone.lo_vel)
    entry[9]  = min(127, zone.hi_vel)
    struct.pack_into('>H', entry, 10, min(0xFFFF, sample_idx))
    entry[14] = min(127, zone.root_key)
    # NEW — once offsets confirmed:
    # entry[??] = struct.pack('b', max(-100, min(100, zone.fine_tune)))[0]
    # entry[??] = _encode_zone_volume(zone.volume)
    return bytes(entry)
```

Update `E4B_FORMAT.md` §4.5 with the confirmed zone entry layout.
Remove the relevant GIG TODO items from `TODO.md`.
