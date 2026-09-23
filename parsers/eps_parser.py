# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# Part of mpc2emu — https://github.com/lentferj/mpc2emu
# Contributions: Jan Lentfer, with AI assistance (see README).
"""Reader for Ensoniq EPS / EPS-16+ / ASR disk images.

The filesystem half of the Ensoniq path.  The *instrument* half — where the
wavesample and layer structs live inside one instrument file — was reverse
engineered from EOS's own importer and is recorded as `O1` in
`docs/FIRMWARE_IMPORT_ROUTINES.md`; this module is what puts a real
instrument in front of it.

**Everything here was read off a 358 MB EPS CD-ROM**, not taken from a
reference, and the walk is checked against the directory's own counts rather
than trusted: see `read_eps_image`.

Layout, in full — it is a small format:

    block size            512 bytes, files are CONTIGUOUS (no chain, no FAT)
    root directory        block 2, first entry at offset 0x38
    directory entry       26 bytes:

        +0   BE u16   type   — see `EPS_TYPE_*` below
        +2   char[12] name   — space padded, not NUL terminated
        +14  BE u16   directories: number of child entries
                      files:       length in 512-byte blocks
        +16  BE u16   a second copy of +14 on every file of the reference
                      disc bar one (a type-23 bank, where the two differ);
                      its meaning for non-instruments is NOT established
        +18  BE u32   start block
        +22  4 bytes  zero on every entry seen

A directory holds a **type-8 back-link to its parent as its first entry**,
then exactly `+14` children.  Reading one entry more than that walks off the
end into the next structure's text — which produced four "files" whose start
block was the ASCII `ONGS` before the count was respected.
"""

import os
from typing import Dict, List, Optional

from models.common import Bank

EPS_BLOCK = 512

#: The root directory does not live at a block of its own: it sits in block 2
#: behind a 56-byte volume header.  Sub-directories start their entries at
#: offset 0.
EPS_ROOT_BLOCK = 2
EPS_ROOT_OFFSET = 0x38

EPS_DIR_ENTRY_LEN = 26
EPS_NAME_LEN = 12

#: Entry types seen on the reference disc, with their counts there.
EPS_TYPE_DIRECTORY = 2        # 104
EPS_TYPE_INSTRUMENT = 3       # 613 — the only type this project converts
EPS_TYPE_PARENT = 8           # one per directory, the back-link
EPS_TYPE_MACRO = 9            # 1
#: 23 (186), 25 (92) and 26 (186) also occur — banks, songs and sequences in
#: some order.  **Which is which is not established**, and nothing here reads
#: them; they are listed so a caller can see them rather than have them
#: silently dropped.
EPS_TYPE_OTHER = (23, 25, 26)

_MAX_DEPTH = 16


def _u16(d: bytes, o: int) -> int:
    return int.from_bytes(d[o:o + 2], 'big')


def _u32(d: bytes, o: int) -> int:
    return int.from_bytes(d[o:o + 4], 'big')


class EpsEntry:
    """One directory entry.  `data` is read lazily through the image."""

    __slots__ = ('type', 'name', 'path', 'count', 'field16', 'start', 'parent')

    def __init__(self, type_, name, path, count, field16, start, parent=None):
        self.type = type_
        self.name = name
        self.path = path
        self.count = count          # blocks for a file, children for a dir
        self.field16 = field16
        self.start = start
        self.parent = parent

    @property
    def is_dir(self) -> bool:
        return self.type == EPS_TYPE_DIRECTORY

    @property
    def is_instrument(self) -> bool:
        return self.type == EPS_TYPE_INSTRUMENT

    @property
    def size(self) -> int:
        """Length in bytes, for a file."""
        return self.count * EPS_BLOCK

    def __repr__(self):
        return (f"EpsEntry(type={self.type}, path={self.path!r}, "
                f"blocks={self.count}, start=0x{self.start:x})")


class EpsImage:
    """An open EPS disk image.  Use as a context manager or call `close()`."""

    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, 'rb')
        self.size = os.path.getsize(path)
        self.nblocks = self.size // EPS_BLOCK

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._fh.close()

    def block(self, n: int, count: int = 1) -> bytes:
        self._fh.seek(n * EPS_BLOCK)
        return self._fh.read(EPS_BLOCK * count)

    def read(self, entry: EpsEntry) -> bytes:
        """The whole file behind `entry`.  Files are contiguous."""
        return self.block(entry.start, entry.count)


def _parse_entries(d: bytes, limit: Optional[int]) -> List[dict]:
    """Decode up to `limit` entries, stopping at the first all-zero one.

    `limit` is load-bearing: a directory's block holds whatever followed it,
    and reading past the declared child count returns plausible-looking
    garbage rather than nothing.
    """
    n = len(d) // EPS_DIR_ENTRY_LEN if limit is None else limit
    out = []
    for i in range(min(n, len(d) // EPS_DIR_ENTRY_LEN)):
        e = d[EPS_DIR_ENTRY_LEN * i:EPS_DIR_ENTRY_LEN * (i + 1)]
        if not any(e):
            continue
        out.append(dict(type=_u16(e, 0),
                        name=e[2:2 + EPS_NAME_LEN].decode('latin1').rstrip(),
                        count=_u16(e, 14), field16=_u16(e, 16),
                        start=_u32(e, 18)))
    return out


def _walk(img: EpsImage, start: int, children: int, path: str,
          seen: set, out: List[EpsEntry], warn: List[str], depth: int = 0):
    if depth > _MAX_DEPTH or start in seen:
        return
    seen.add(start)
    # children + the type-8 back-link, rounded up to whole blocks
    need = max(1, ((children + 1) * EPS_DIR_ENTRY_LEN + EPS_BLOCK - 1)
               // EPS_BLOCK)
    d = img.block(start, need)
    found = 0
    for e in _parse_entries(d, children + 1):
        if e['type'] == EPS_TYPE_PARENT:
            continue
        found += 1
        p = f"{path}/{e['name']}"
        ent = EpsEntry(e['type'], e['name'], p, e['count'], e['field16'],
                       e['start'], parent=path)
        out.append(ent)
        if ent.is_dir:
            _walk(img, ent.start, ent.count, p, seen, out, warn, depth + 1)
        elif ent.start + ent.count > img.nblocks:
            warn.append(f"{p}: extends past the end of the image "
                        f"(start {ent.start}, {ent.count} blocks, image has "
                        f"{img.nblocks})")
    if found != children:
        warn.append(f"{path or '/'}: directory declares {children} entries, "
                    f"{found} decoded")


def is_eps_image(path: str) -> bool:
    """True if `path` looks like an EPS filesystem.

    Identified by the root directory decoding rather than by a magic string:
    block 2 at offset 0x38 must hold at least one plausible entry whose type
    is known and whose start block is inside the image.
    """
    try:
        with EpsImage(path) as img:
            if img.nblocks < 8:
                return False
            d = img.block(EPS_ROOT_BLOCK)[EPS_ROOT_OFFSET:]
            ents = _parse_entries(d, None)
    except OSError:
        return False
    if not ents:
        return False
    known = (EPS_TYPE_DIRECTORY, EPS_TYPE_INSTRUMENT, EPS_TYPE_MACRO,
             EPS_TYPE_PARENT) + EPS_TYPE_OTHER
    good = [e for e in ents
            if e['type'] in known and 0 < e['start'] < (os.path.getsize(path)
                                                        // EPS_BLOCK)]
    return len(good) >= 2 and len(good) >= len(ents) // 2


def read_eps_image(path: str, quiet: bool = False) -> List[EpsEntry]:
    """Every entry on the disc, depth first, directories included.

    **The walk is checked, not trusted.** Each directory's declared child
    count is compared against what decoded, and every file's extent against
    the image length; anything that disagrees is reported. On the reference
    disc all 1182 entries pass both.
    """
    warn: List[str] = []
    out: List[EpsEntry] = []
    with EpsImage(path) as img:
        d = img.block(EPS_ROOT_BLOCK)[EPS_ROOT_OFFSET:]
        seen = {EPS_ROOT_BLOCK}
        for e in _parse_entries(d, None):
            if e['type'] == EPS_TYPE_PARENT:
                continue
            p = '/' + e['name']
            ent = EpsEntry(e['type'], e['name'], p, e['count'], e['field16'],
                           e['start'], parent='')
            out.append(ent)
            if ent.is_dir:
                _walk(img, ent.start, ent.count, p, seen, out, warn)
            elif ent.start + ent.count > img.nblocks:
                warn.append(f"{p}: extends past the end of the image")
    if warn and not quiet:
        for w in warn[:20]:
            print(f"    [WARN] EPS: {w}")
        if len(warn) > 20:
            print(f"    [WARN] EPS: {len(warn) - 20} more")
    return out


def eps_instruments(path: str, quiet: bool = False) -> List[EpsEntry]:
    """Just the instrument files, in disc order."""
    return [e for e in read_eps_image(path, quiet) if e.is_instrument]


# ─────────────────────────────────────────────────────────────────────────────
# The instrument file
# ─────────────────────────────────────────────────────────────────────────────
#
# The layout is `O1` in docs/FIRMWARE_IMPORT_ROUTINES.md, read out of EOS's own
# importer, and the conversion law below it is EOS's too.  **For Ensoniq this
# project matches the firmware rather than improving on it** — there is no EPS
# on the bench, so "what EOS does" is the only checkable definition of correct
# (see that document's opening section).
#
# What is FIRMWARE-DERIVED here, and what is not, stated per field rather than
# in a block, because the two are mixed:
#
#   [C] the position table, the struct strides, root/key-range, pan, the
#       volume index, the layer-mask variants, big-endian audio
#   [S] the audio EXTENT — see `_ws_audio_extent`
#   [?] the sample rate — no field for it has been located; see EPS_DEFAULT_RATE

EPS_INST_NAME = 10            #: 12 chars, 16-bit, high byte carries the char
EPS_INST_TABLE = 100          #: 136 packed 4-byte position slots
EPS_INST_LAYER_SLOTS = 8
EPS_INST_WS_SLOTS = 128
#: `TABLE[v] = inst[44 + 2v]` — the four preset variants are LAYER MASKS, not
#: channel selection.  [C: hardware, 100/100 variants, 25/25 instruments]
EPS_INST_VARIANT_TABLE = 44
EPS_INST_CHANMASK = (54, 52)  #: (chan 0, chan 1)
EPS_VARIANT_SUFFIX = ('00', '0*', '*0', '**')

EPS_LAYER_LEN = 224

#: **The layer's per-key map: one WAVESAMPLE SLOT INDEX per key**, as the
#: high byte of a word, over **MIDI 20 … 107**.
#:
#: Read out of the K2000's own Ensoniq importer (`%a3@(0x2E + 2·key)` fed
#: through `0x1630C0`, which is `movew %sp@(4),%d0 / lsrw #8,%d0 / rts` —
#: the high byte of a word) and it is what closed that importer's 92-byte
#: staging record. The arithmetic closes on the layer struct and nothing
#: else: `46 header + 88 words (176) + 2 = 224`, the layer stride.
#:
#: **Corpus-checked over 11 532 runs on 613 instruments:** 83.6 % map onto
#: the wavesample's own declared key range exactly, 15.4 % are clipped by
#: the table's own `20…107` extent, and 1.0 % are NARROWER than the
#: wavesample's range — which is the table doing its job, since a layer may
#: use a wavesample over a narrower span than the wavesample's native one.
#: **So the table is authoritative for a layer's key mapping**, and
#: `ws[274]`/`ws[276]` are the wavesample's default.
EPS_LAYER_KEYMAP = 0x2E
EPS_LAYER_KEYS = 88
EPS_LAYER_KEY_BASE = 20
EPS_WS_LEN = 288

EPS_WS_NAME = 14              #: 12 chars, 16-bit
EPS_WS_ROOT = 170             #: MIDI root key, 1..127            [C]
EPS_WS_VOL = 208              #: index into EOS's 128-entry table [C]
EPS_WS_PAN = 221              #: signed; pan = ws[221] * 63 / 127 [C]
EPS_WS_BOOST = 225            #: non-zero shifts the volume index by 12 [S, n=1]
EPS_WS_KEY_LO = 274           #: [C]
EPS_WS_KEY_HI = 276           #: [C]

#: The four packed groups `0x78CC4` decodes. **These ARE the audio pointers**
#: -- this reader first derived the extents by measurement and then had the
#: decoder corrected by `eosed` (2026-09-22), at which point the two agreed:
#:
#:     EOS    0x78CC4   hi  = (b0 << 15) + (b2 << 7) + (b4 >> 1)
#:     K2000  0x162FF2  pos = ((b0 << 8) + b2) << 4
#:     hi = 8 * pos + (b4 >> 1)
#:
#: The shift is UNSIGNED. The formula this project carried said `(int8)b4 >> 1`
#: with a note that the signedness was load-bearing; `0x78CDA` zeroes `%d4` and
#: `0x78CEA` writes only its low byte, so the `asrl` at `0x78CEC` runs on a
#: register whose top 24 bits are clear and is a logical shift. It differs for
#: every `b4 >= 128`, and the warning was adopted by both projects unchecked.
#:
#: Units are 16-bit WORDS. **What they are relative to is only PARTLY
#: settled, and the measurement is here rather than an assumption:** over the
#: 3359 wavesamples of the reference disc that carry audio,
#:
#:     end fits after its OWN struct (to the next struct)   2697  80.3 %
#:       ...of those, within 64 bytes of the gap            2467  91.5 %
#:     end exceeds that gap                                  662  19.7 %
#:     end fits from the instrument's FIRST audio base      3359   100 %
#:
#: ✅ **RESOLVED: the 662 are ALIASES, not a coordinate problem.** `struct +
#: 288` is right, and a struct whose pointer overshoots its room is
#: describing another wavesample's audio — 558 of the 662 (84.3 %) share
#: their `end` with a wavesample in the same instrument that DOES fit, and
#: 384 (58 %) match on `end`, both loop points and root as well.
#:
#: The overshoot is not marginal, which is what rules out an arithmetic fix:
#: the median want/room ratio is **26×** and the largest **1020×**. On the
#: whole disc 8899 of 11597 wavesamples (76.7 %) are aliases — `FLUTE 1`'s
#: seven layers over three audio regions is the normal shape, not an
#: exception. `_resolve` sends each to its original by pointer signature.
#:
#: *A single shared base scored 100 % and was still wrong: on `FLUTE 1` the
#: second and third structs sit INSIDE the span it would give the first. And
#: `(end − start)` does not explain them either — only 11 of the 662, and
#: only 102 carry a non-zero `start` at all.*
EPS_WS_GROUPS = dict(start=240, end=248, loop_start=256, loop_end=264)

#: ✅ **THE RATE IS A CODE AT `ws+272`, AND THE TABLE IS THE K2000's OWN.**
#:
#: Found 2026-09-22 by reading the K2000's Ensoniq converter rather than by
#: estimating pitch — two rounds of autocorrelation had already failed on the
#: octave trap, which is what sent the search to the ROM.
#:
#:     163d78:  movew %a3@(272),%sp@-
#:     163d7c:  bsr   0x1630C0          ; movew %sp@(4),%d0 / lsrw #8 / rts
#:     163d84:  moveq #0,%d1
#:     163d86:  moveb %d0,%d1           ; d1 = the HIGH BYTE = the rate code
#:     163d88:  addl  %d1,%d1
#:     163d8a:  addil #0x0018881A,%d1   ; the TABLE
#:     163d94:  movew %a0@,%d0          ; d0 = the rate in Hz
#:     163d9a:  movel #1000000000,%d1
#:     163da6:  jsr   0x18352C          ; samplePeriod = 1e9 / rate
#:     163dae:  movel %d0,%a0@(28)
#:
#: **So: rate code = high byte of the word at wavesample `+272`**, and the
#: rate is `EPS_RATE_TABLE[code]`.
#:
#: **Confirmed on the disc without using the ROM's value range as a prior:**
#: every one of 11 597 wavesamples carries a code of **100 or less**, and the
#: table ends at exactly 100. A field whose observed range stops where an
#: independently-located table stops is not a coincidence.
#:
#: Codes 10…100 are a divide-down ladder, `≈ 625000 / code` rounded to three
#: significant figures — `code 21 → 29 800` against `625000/21 = 29 762`,
#: which is the figure this reader had been using for everything. *It was
#: right for one code out of the thirty-three the disc uses.*
#:
#: Disc distribution: code 20 (31 300 Hz) 27.7 %, code 16 (39 100) 16.7 %,
#: code 1 (44 100) 14.0 %, code 0 (48 000) 6.5 %, code 19 (32 900) 6.3 %.
EPS_WS_RATE_CODE = 272

#: The K2000's table at ROM `0x18881A`, read out of `k2000_v387j.bin`
#: (md5 `ab658571677603ee1bccb9cbe329aecd`). Entries 0…9 are the fixed rates;
#: 10…100 are the divide-down ladder. Entry 101 onward is not part of it.
EPS_RATE_TABLE = (
    48000, 44100, 31200, 20800, 15600, 12500, 10400, 8930, 7810, 6940,
    62500, 56800, 52100, 48100, 44600, 41700, 39100, 36800, 34700, 32900,
    31300, 29800, 28400, 27200, 26000, 25000, 24000, 23100, 22300, 21600,
    20800, 20200, 19500, 18900, 18400, 17900, 17400, 16900, 16400, 16000,
    15600, 15200, 14900, 14500, 14200, 13900, 13600, 13300, 13000, 12800,
    12500, 12300, 12000, 11800, 11600, 11400, 11200, 11000, 10800, 10600,
    10400, 10200, 10100, 9900, 9800, 9600, 9500, 9300, 9200, 9100,
    8900, 8800, 8700, 8600, 8400, 8300, 8200, 8100, 8000, 7900,
    7800, 7700, 7600, 7500, 7400, 7350, 7270, 7180, 7100, 7020,
    6940, 6870, 6790, 6720, 6650, 6580, 6510, 6440, 6380, 6310,
    6250,
)

#: Used only when a wavesample's code falls outside the table, which does not
#: happen on the reference disc.
EPS_DEFAULT_RATE = 29800


def _eps_wide_name(d: bytes, off: int, n: int = 12) -> str:
    """A name stored as `n` 16-bit chars — the char in the HIGH byte.

    The same widening the position table uses, which is why a reader that
    assumes 8-bit reads every second character.
    """
    out = bytes(d[off + 2 * i] for i in range(n) if off + 2 * i < len(d))
    # Trailing non-printables are not name content. Wavesample names run
    # "NAMED WS" followed by a one-byte index on every struct but the first,
    # which read as part of the name until it was stripped here.
    txt = out.decode('latin1')
    txt = ''.join(c for c in txt if 32 <= ord(c) < 127)
    return txt.rstrip()


def eps_positions(d: bytes) -> List[int]:
    """The 136 struct positions: `((b0 << 8) + b2) << 4`, the firmware's own.

    `0x162FF2` computes exactly this, padding byte skipped and all.  Slots
    0…7 are layers, 8…135 wavesamples.
    """
    out = []
    for i in range(EPS_INST_LAYER_SLOTS + EPS_INST_WS_SLOTS):
        o = EPS_INST_TABLE + 4 * i
        if o + 4 > len(d):
            out.append(0)
            continue
        out.append(((d[o] << 8) + d[o + 2]) << 4)
    return out


def eps_group(d: bytes, base: int, off: int) -> int:
    """`0x78CC4`'s packed group, in 16-bit words. See `EPS_WS_GROUPS`."""
    g = d[base + off:base + off + 8]
    if len(g) < 8:
        return 0
    return (g[0] << 15) + (g[2] << 7) + (g[4] >> 1)


def _ws_audio_extent(pos: int, marks: List[int], size: int) -> int:
    """Where this wavesample's audio ends.

    **`[S]`, and measured here rather than taken from the firmware.** The
    record has `0x78CC4` decoding a packed 4-byte group at struct
    `+240/+248/+256/+264` as "very likely the audio pointer and length"; on
    this disc that decode yields small repeated values (0, 2256, 1040384 on a
    125 kB file), so whatever it reads, it is not an offset into the
    instrument.

    What holds instead: each wavesample's audio runs from the end of its
    288-byte struct to the next struct named in the position table. Over all
    613 instruments of the reference disc that gives a **96.3 % audio share
    of total bytes (median 95.9 %)**, against EOS's own "large files are
    96–98 % audio" — and the instruments below 50 % are exactly the
    single-cycle synth waveforms where the parameter structs dominate.
    """
    later = [m for m in marks if m > pos]
    return min(later) if later else size


def parse_eps_instrument(d: bytes, fallback_name: str = '') -> dict:
    """Decode one instrument file into layers, wavesamples and audio extents."""
    size = len(d)
    name = _eps_wide_name(d, EPS_INST_NAME) or fallback_name
    pos = eps_positions(d)
    layers = [(i, v) for i, v in enumerate(pos[:EPS_INST_LAYER_SLOTS]) if v]
    wss = [(i, v) for i, v in enumerate(pos[EPS_INST_LAYER_SLOTS:],
                                        EPS_INST_LAYER_SLOTS) if v]
    marks = sorted({v for _, v in layers} | {v for _, v in wss})
    lay_pos = sorted(v for _, v in layers)

    out_ws = []
    for slot, b in wss:
        if b + EPS_WS_LEN > size:
            continue
        audio_at = b + EPS_WS_LEN
        w_start = eps_group(d, b, EPS_WS_GROUPS['start'])
        w_end = eps_group(d, b, EPS_WS_GROUPS['end'])
        w_ls = eps_group(d, b, EPS_WS_GROUPS['loop_start'])
        w_le = eps_group(d, b, EPS_WS_GROUPS['loop_end'])
        # The pointers are the firmware's; the gap is kept as a CEILING, so a
        # damaged or misread group can never read into the next struct.
        ceiling = _ws_audio_extent(b, marks, size)
        # THE SPAN FIRST. A non-zero `start` means the pair is a span in a
        # per-instrument coordinate space and the extent is the difference --
        # `eosed`, 2026-09-22, where it is a SET IDENTITY: on their disc the
        # 98 structs needing the subtraction are exactly the 98 with a
        # non-zero `start`, and it fixes 98 of their 99 over-runs.
        #
        # ON THIS DISC IT FIXES 11 OF 662 and aliasing explains 558. The two
        # discs behave oppositely and BOTH mechanisms are real; the mix is
        # disc-dependent, so all three rules apply in order -- subtract,
        # then alias, then clamp. Implementing only the one that is nearly
        # perfect here would silently truncate 98 of 232 wavesamples there.
        want = (w_end + 1 - w_start) * 2 if w_start else (w_end + 1) * 2
        room = ceiling - (audio_at + w_start * 2)
        # A STRUCT WHOSE POINTER OVERSHOOTS ITS ROOM IS AN ALIAS, not a
        # truncation. Measured on the reference disc: of 662 such structs,
        # 558 (84.3 %) share their `end` with another wavesample in the same
        # instrument that DOES fit, and 384 (58 %) match on end, both loop
        # points and root as well. The overshoot is not marginal either --
        # the median want/room ratio is 26x and the largest 1020x -- so these
        # are not off-by-a-subtraction, they are structs describing somebody
        # else's audio. `_resolve_alias` sends them to it.
        alias = want > room
        alen = 0 if alias else max(0, min(want, room))
        audio_from = audio_at + w_start * 2
        out_ws.append(dict(
            slot=slot, pos=b,
            name=_eps_wide_name(d, b + EPS_WS_NAME),
            rate_code=d[b + EPS_WS_RATE_CODE],
            root=d[b + EPS_WS_ROOT],
            key_lo=d[b + EPS_WS_KEY_LO], key_hi=d[b + EPS_WS_KEY_HI],
            vol_index=d[b + EPS_WS_VOL],
            boost=bool(d[b + EPS_WS_BOOST]),
            pan_raw=d[b + EPS_WS_PAN] - 256 if d[b + EPS_WS_PAN] > 127
            else d[b + EPS_WS_PAN],
            audio_off=audio_from, audio_len=alen - (alen % 2),
            loop_start=max(0, w_ls - w_start), loop_end=max(0, w_le - w_start),
            w_start=w_start, w_end=w_end, alias=alias))

    # Wavesamples belong to the last LAYER position at or before them: the
    # file interleaves them (layer, its wavesamples, their audio, next layer),
    # which is why the position gaps run 224 and 288. Checked over the
    # reference disc: 3697 layer groups have correctly ordered key ranges
    # against 3 that do not, and 272 carry an overlap -- plausible velocity
    # layering, not necessarily a mis-assignment.
    groups: Dict[int, list] = {v: [] for v in lay_pos}
    for w in out_ws:
        earlier = [L for L in lay_pos if L <= w['pos']]
        key = earlier[-1] if earlier else (lay_pos[0] if lay_pos else None)
        if key is not None:
            groups[key].append(w)

    by_slot = {w['slot']: w for w in out_ws}
    out_layers = []
    for slot, b in sorted(layers, key=lambda t: t[1]):
        # The layer's own key map, which overrides each wavesample's native
        # range for THIS layer. Runs of one slot index become one zone.
        keymap = {}
        if b + EPS_LAYER_LEN <= size:
            run_slot = None
            run_lo = 0
            for k in range(EPS_LAYER_KEYS + 1):
                v = 0
                if k < EPS_LAYER_KEYS:
                    o = b + EPS_LAYER_KEYMAP + 2 * k
                    v = d[o] if o < size else 0
                if v != run_slot:
                    if run_slot:
                        keymap[run_slot] = (run_lo + EPS_LAYER_KEY_BASE,
                                            k - 1 + EPS_LAYER_KEY_BASE)
                    run_slot, run_lo = v, k
        members = groups.get(b, [])
        for w in members:
            rng = keymap.get(w['slot'])
            w['layer_lo_key'], w['layer_hi_key'] = rng if rng else (None, None)
        out_layers.append(dict(slot=slot, pos=b, wavesamples=members,
                               keymap=keymap))
    return dict(name=name, size=size, layers=out_layers, wavesamples=out_ws)


def eps_variant_layers(d: bytes, variant: int) -> int:
    """The layer mask for preset variant `variant` (0…3).

    `layer L enters variant v iff (inst[44+2v] >> L) & 1 and (chanmask >> L) & 1`
    [C: hardware, 100/100 variants]. The two channel masks are OR-ed here —
    EOS runs the channel builder twice, `chan=1` then `chan=0`, and this
    reader is mono, so a layer present in EITHER channel is kept. **That is a
    simplification of the firmware, and the one place this path knowingly
    diverges from it.**
    """
    o = EPS_INST_VARIANT_TABLE + 2 * variant
    if o >= len(d):
        return 0
    chan = 0
    for c in EPS_INST_CHANMASK:
        if c < len(d):
            chan |= d[c]
    return d[o] & chan


# ─────────────────────────────────────────────────────────────────────────────
# Conversion to the shared model
# ─────────────────────────────────────────────────────────────────────────────

#: EOS's 128-entry volume table at `0x796A4`, if it is ever dumped here.
#:
#: **It is not, and that is a real gap rather than a rounding detail.** The
#: law is `volume = TABLE_0x796a4[ws[208]]` [C: hardware, 24/25, eleven
#: distinct indices exercised], and the table lives only inside the EOS image.
#: Until it arrives, `_eps_volume_db` uses a stated stand-in and says so once
#: per run — a silent approximation of a confirmed law is exactly the shape
#: this project keeps retracting.
EPS_VOLUME_TABLE: Optional[List[float]] = [
    # 128 SIGNED bytes, byte-indexed and sign-extended (`moveb` + `extbl` at
    # 0x78F08) -- dumped from the EOS image by `eosed`, 2026-09-22 (c8d40c6).
    # Monotonic non-decreasing, -72 dB at index 0 to 0 dB at 123..127, and
    # index 127 = 0 is the one point that was hardware-confirmed.
    -72, -66, -60, -54, -48, -48, -42, -42, -42, -36, -36, -36, -36, -36,
    -30, -30, -30, -30, -30, -30, -24, -24, -24, -24, -18, -18, -18, -12,
    -12, -11, -11, -11, -11, -11, -11, -10, -10, -10, -10, -10, -10, -10,
    -9, -9, -9, -9, -9, -9, -9, -9, -9, -9, -8, -8, -8, -8, -8, -8, -8,
    -7, -7, -7, -7, -7, -7, -7, -6, -6, -6, -6, -6, -6, -6, -6, -5, -5,
    -5, -5, -5, -5, -5, -4, -4, -4, -4, -4, -4, -4, -4, -4, -3, -3, -3,
    -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -3, -2, -2, -2, -2,
    -2, -2, -2, -2, -2, -2, -2, -2, -1, -1, -1, -1, -1, 0, 0, 0, 0, 0,
]

#: `min((ws[208] + 12) & 0xff, 127)` when `ws[225]`.  **[S], n = 1** — one
#: instrument of the twenty-five that measured the unboosted path carries it,
#: so the term is applied but never presented as confirmed.
EPS_VOLUME_BOOST = 12

_warned: set = set()


def _warn_once(key: str, msg: str, quiet: bool = False):
    if quiet or key in _warned:
        return
    _warned.add(key)
    print(f"    [WARN] {msg}")


def _eps_volume_db(index: int, boost: bool, quiet: bool = False) -> float:
    """dB for a wavesample's volume index."""
    idx = index
    if boost:
        idx = min((index + EPS_VOLUME_BOOST) & 0xFF, 127)
    if EPS_VOLUME_TABLE:
        return float(EPS_VOLUME_TABLE[min(idx, len(EPS_VOLUME_TABLE) - 1)])
    _warn_once('eps-volume',
               "EPS volume: EOS's table at 0x796A4 has not been dumped into "
               "this reader, so levels use a stand-in (index 127 = 0 dB, "
               "20*log10(idx/127) below it). The MAPPING is confirmed; the "
               "TABLE is not present. See EPS_VOLUME_TABLE.", quiet)
    import math
    return -96.0 if idx <= 0 else max(-96.0, 20.0 * math.log10(idx / 127.0))


def _eps_pan(raw: int) -> float:
    """`pan = (int8)ws[221] * 63 / 127`, then into the model's -1 … +1.

    [C: hardware, 25/25, and pan was not in the search key used to find the
    structs, so it is an out-of-sample confirmation rather than a fit.]
    """
    e4 = int(raw * 63 / 127)            # truncating, as the firmware does
    return max(-1.0, min(1.0, e4 / 63.0))


def _eps_audio(d: bytes, w: dict) -> bytes:
    """The wavesample's PCM, byte-swapped into the model's little-endian.

    **The source is 16-bit BIG-endian** [C: corpus]. Re-measured here on 36
    audio regions from 36 random instruments of the reference disc: mean
    successive-difference roughness 0.0699 big-endian against 0.5316
    little-endian, a 7.6x separation, and big-endian lower on 36 of 36.
    """
    raw = d[w['audio_off']:w['audio_off'] + w['audio_len']]
    return bytes(raw[i + 1] if i % 2 == 0 else raw[i - 1]
                 for i in range(len(raw)))


def parse_eps_image(path: str, wav_dir: Optional[str] = None,
                    quiet: bool = False, limit: Optional[int] = None,
                     firmware_sim: bool = False,
                     firmware_sim_target: Optional[str] = None) -> Bank:
    """Every instrument on an EPS disc, as one `Bank`.

    Each instrument yields up to four presets — EOS's layer-mask variants,
    suffixed `00` / `0*` / `*0` / `**` — and an empty variant is skipped
    rather than written as a silent preset.
    """
    from models.common import (Bank, Preset, SampleData, VoiceLayer,
                               ZoneMapping, LoopType)

    entries = eps_instruments(path, quiet)
    if limit:
        entries = entries[:limit]
    bank = Bank(name=os.path.splitext(os.path.basename(path))[0][:16])
    seen_names: set = set()

    with EpsImage(path) as img:
        for ent in entries:
            d = img.read(ent)
            inst = parse_eps_instrument(d, ent.name)

            # One SampleData per wavesample that CARRIES audio. The others
            # reuse a sibling's: on the reference disc seven layers routinely
            # share three audio regions, the extra layers being the stereo
            # pair and level variants.
            by_range: Dict[tuple, str] = {}
            by_pointer: Dict[tuple, str] = {}
            for w in inst['wavesamples']:
                if w['audio_len'] < 64:
                    continue
                # ⚠ **EPS INSTRUMENT NAMES ARE NOT UNIQUE**, and 32 of them
                # on the reference disc are a prefix of another (VinSamLib,
                # measured 2026-09-22 -- `HARP` names two instruments). So a
                # sample name is the instrument name plus a GLOBAL counter,
                # with the `while` below closing the remaining gap.
                #
                # Measured on this side over the same disc: **2681 sample
                # names, 0 duplicates**, against **4 duplicate PRESET names in
                # 2396** -- all four `HARP` variants. Zone->sample resolution
                # is therefore safe; a consumer keying PRESETS by name is not,
                # and should use the index. `tests/test_eps_filesystem.py`
                # asserts the sample half.
                nm = f"{inst['name'][:11]}{len(seen_names) % 100000:05d}"
                while nm in seen_names:
                    nm = f"{nm[:11]}{len(seen_names) % 100000 + 1:05d}"
                seen_names.add(nm)
                pcm = _eps_audio(d, w)
                frames = len(pcm) // 2
                ls, le = w['loop_start'], w['loop_end']
                looped = 0 <= ls < le <= frames and (le - ls) >= 16
                code = w.get('rate_code', 0)
                rate = (EPS_RATE_TABLE[code] if code < len(EPS_RATE_TABLE)
                        else EPS_DEFAULT_RATE)
                bank.samples.append(SampleData(
                    name=nm, data=pcm, sample_rate=rate,
                    channels=1, bit_depth=16,
                    loop_type=LoopType.FORWARD if looped else LoopType.NO_LOOP,
                    loop_start=ls if looped else 0,
                    loop_end=le if looped else 0,
                    root_note=w['root'] if 0 < w['root'] < 128 else 60))
                by_range.setdefault((w['key_lo'], w['key_hi'], w['root']), nm)
                by_pointer.setdefault((w['w_end'], w['loop_start'],
                                       w['loop_end']), nm)
                by_pointer.setdefault((w['w_end'],), nm)
                w['sample_name'] = nm

            def _resolve(w):
                """Which SampleData this wavesample plays.

                Pointer signature first -- an alias carries the pointers of
                the audio it shares, and that is an exact match on 84.3 % of
                them -- then the key range, then the root. Each fallback is
                weaker than the one above it and is only reached when the
                stronger one finds nothing.
                """
                if w.get('sample_name'):
                    return w['sample_name']
                for k in ((w['w_end'], w['loop_start'], w['loop_end']),
                          (w['w_end'],)):
                    if k in by_pointer:
                        return by_pointer[k]
                k = (w['key_lo'], w['key_hi'], w['root'])
                if k in by_range:
                    return by_range[k]
                same_root = [n for (lo, hi, r), n in by_range.items()
                             if r == w['root']]
                return same_root[0] if same_root else None

            for v in range(4):
                mask = eps_variant_layers(d, v)
                voices = []
                for li, layer in enumerate(inst['layers']):
                    if not (mask >> layer['slot']) & 1:
                        continue
                    zones = []
                    for w in layer['wavesamples']:
                        nm = _resolve(w)
                        if not nm:
                            continue
                        # THE LAYER'S KEY MAP WINS where it names this
                        # wavesample; `ws[274]/[276]` is the native default.
                        lo, hi = w['key_lo'], w['key_hi']
                        if w.get('layer_lo_key') is not None:
                            lo, hi = w['layer_lo_key'], w['layer_hi_key']
                        if lo > hi:
                            lo, hi = hi, lo
                        zones.append(ZoneMapping(
                            sample_name=nm, lo_key=lo, hi_key=hi,
                            root_key=w['root'] if 0 < w['root'] < 128 else 60,
                            volume=_eps_volume_db(w['vol_index'], w['boost'],
                                                  quiet),
                            pan=_eps_pan(w['pan_raw'])))
                    if zones:
                        voices.append(VoiceLayer(zones=zones))
                if not voices:
                    continue            # an empty variant is not a preset
                bank.presets.append(Preset(
                    name=f"{inst['name'][:13]}{EPS_VARIANT_SUFFIX[v]}"[:16],
                    voices=voices))
    if firmware_sim:
        # ⚠ **TWO DIFFERENT SIMULATIONS, AND ONLY ONE IS HERE.**
        # For an E4B target this rebuilds each preset the way EOS
        # would. For a KRZ target the simulation is WRITER-side --
        # the K2000 clones a template and writes a handful of
        # fields -- so the bank passes through untouched and
        # `write_krz` does the work, told which import to
        # reproduce by the tag set below.
        bank.firmware_sim_source = 'ensoniq'
        if firmware_sim_target not in (None, 'e4b', 'krz'):
            raise ValueError(
                "--firmware-sim for a ensoniq source is implemented "
                "for --format e4b and krz only.")
        # ⚠ NOT a conversion option -- reproduces what EOS's own importer
        # writes. See writers/eos_firmware_sim.simulate_eos_foreign_preset.
        if firmware_sim_target in (None, 'e4b'):
            from writers.eos_firmware_sim import simulate_eos_foreign_preset
            bank.presets = [simulate_eos_foreign_preset(p)
                            for p in bank.presets]
    return bank
