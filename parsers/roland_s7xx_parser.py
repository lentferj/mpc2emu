# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# Part of mpc2emu — https://github.com/lentferj/mpc2emu
# Contributions: Jan Lentfer, with AI assistance (see README).
"""Reader for Roland S-7xx CD-ROM and hard-disk images.

The disc side of the Roland path. Every constant here was established in
`docs/FIRMWARE_IMPORT_ROUTINES.md` (`O3`, `O4`) and validated across seven
images and 20 018 sample records; the field map came out of the K2000's own
loader and was then checked against the discs from the other side.

**The K2000 does not walk a directory for this.** It opens the pseudo-file
`ROLAND.S` — a name that appears on no Roland disc anywhere — and
absolute-seeks. So there is no filesystem to parse: the structures sit at
fixed offsets and the disc is addressed directly.

    0x0A5800   patch directory
    0x155800   patch records, 512-byte stride
    0x1D5800   partial records, 128-byte stride, id 1-based
    0x255800   sample parameter records, 48 bytes each
    0x2B5800   sample audio, in 9216-byte blocks

**Two of these were `0x200` low in the first published map**, and the error
was invisible to every total computed from them because a constant base
cancels out of a sum. `0x255600` and `0x2B5600` are inside 512-byte runs of
`0xFF`; the real bases land on the first record.
"""

import os
import struct
from typing import Dict, List, Optional

from models.common import Bank

#: **`S770 MR25A` at offset 4** — present on all seven images this project
#: holds, from five different releases spanning 2003-2009. A real magic
#: string, and a far stronger identification than the record-plausibility
#: heuristic this reader shipped with.
ROLAND_MAGIC_OFFSET = 4
ROLAND_MAGIC = b'S770 MR25A'

ROLAND_PATCH_DIR = 0x0A5800
ROLAND_PATCH_BASE = 0x155800
ROLAND_PATCH_STRIDE = 512
ROLAND_PARTIAL_BASE = 0x1D5800
ROLAND_PARTIAL_STRIDE = 128
ROLAND_SAMPLE_BASE = 0x255800
ROLAND_SAMPLE_LEN = 48
ROLAND_AUDIO_BASE = 0x2B5800
ROLAND_AUDIO_BLOCK = 9216

#: The parameter region ends where the audio begins: `(0x2B5800 - 0x255800)
#: / 48`. A hard cap, because the table's padding is `0xFF` rather than zero
#: and a scan that only stops at a zero size walks straight into the audio.
ROLAND_MAX_SAMPLES = (ROLAND_AUDIO_BASE - ROLAND_SAMPLE_BASE) // ROLAND_SAMPLE_LEN

#: The sample parameter record. Offsets verified on both Roland reference disc.
#:
#: The loop fields are **24-bit LITTLE-endian at group base + 1, in SAMPLES**.
#: This project published a `[C-neg]` saying they were not in this record at
#: all; that was an artefact of reading 32 bits at the group base against a
#: byte extent — wrong width, wrong alignment, wrong unit — and it was
#: refuted by an external session and then verified here on 9889 records.
ROL_START = 17           #: LE24, samples
ROL_LOOP_START = 21      #: LE24, SIGNED — negative is a no-loop sentinel
ROL_LOOP_END = 25        #: LE24
ROL_LOOP_MODE = 36
ROL_RATE_CODE = 44       #: low nibble
ROL_ROOT_KEY = 45
ROL_SIZE = 42            #: LE16, in 9216-byte blocks

#: `0x169D90`: `moveb %a1@(44),%d0 / andiw #15 / cmpiw #5 / bhis`, then a
#: word offset table at `0x169DA8` and `jmp %pc@(2,%d0:w)`.
#:
#: **Read out of the ROM here** (`k2000_v387j.bin`, md5
#: `ab658571677603ee1bccb9cbe329aecd`), offsets and arm immediates both:
#: table `000c 0034 0014 001c 0024 002c`, arms `movel #48000 / #44100 /
#: #24000 / #22050 / #30000 / #15000`.
#:
#: **Index 5 is LIVE.** `0x62` is `BHI`, so the branch to the default arm is
#: taken only when the index is *greater* than 5 — an external review called
#: index 5's arm dead code, and it is not. The offset table is also why
#: index 1 lands on 44100 rather than the second immediate in address order.
ROLAND_RATES = (48000, 44100, 24000, 22050, 30000, 15000)
ROLAND_RATE_DEFAULT = 44100

#: `record[+36]`. **The flag arms are in `docs/FIRMWARE_IMPORT_ROUTINES.md`
#: and mode 2 sets bit 7** — the K2000's one-shot flag, inverted. A table
#: that says mode 2 sets nothing is the retracted one; it covers 51 % of all
#: known Roland samples.
ROLAND_LOOP_LOOPED = 0
ROLAND_LOOP_ONESHOT = 2


def _le24(d: bytes, o: int) -> int:
    return d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)


def _le24s(d: bytes, o: int) -> int:
    v = _le24(d, o)
    return v - (1 << 24) if v & 0x800000 else v


def _le16(d: bytes, o: int) -> int:
    return d[o] | (d[o + 1] << 8)


class RolandImage:
    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, 'rb')
        self.size = os.path.getsize(path)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._fh.close()

    def close(self):
        self._fh.close()

    def at(self, off: int, n: int) -> bytes:
        self._fh.seek(off)
        return self._fh.read(n)


def is_roland_image(path: str) -> bool:
    """True if the fixed sample-record base holds plausible records.

    **There IS a magic after all** — `S770 MR25A` at offset 4, on all seven
    images here across five releases and six years. It is checked first.
    The heuristic below is kept as a fallback for an image that carries the
    structures without the header, and is the same check the record map
    makes: the
    first records must carry a root key in range and a non-zero size, and the
    `0xFF` run that hid the base error must NOT be there.
    """
    try:
        with RolandImage(path) as img:
            if img.size < ROLAND_AUDIO_BASE:
                return False
            magic = img.at(ROLAND_MAGIC_OFFSET, len(ROLAND_MAGIC))
            if magic == ROLAND_MAGIC:
                return True
            d = img.at(ROLAND_SAMPLE_BASE, ROLAND_SAMPLE_LEN * 8)
    except OSError:
        return False
    if len(d) < ROLAND_SAMPLE_LEN * 8 or all(b == 0xFF for b in d[:48]):
        return False
    good = 0
    for i in range(8):
        r = d[ROLAND_SAMPLE_LEN * i:ROLAND_SAMPLE_LEN * (i + 1)]
        if 0 < r[ROL_ROOT_KEY] < 128 and 0 < _le16(r, ROL_SIZE) < 4096:
            good += 1
    return good >= 6


def read_roland_samples(path: str) -> List[dict]:
    """Every sample parameter record, with its audio offset resolved.

    The audio index is a **running total of sizes**, not a per-sample index:
    `offset(n) = 0x2B5800 + sum(size[0..n-1]) * 9216`. Reading it as an index
    is the error that made the first extent map land 512 bytes out.
    """
    out: List[dict] = []
    with RolandImage(path) as img:
        running = 0
        for i in range(ROLAND_MAX_SAMPLES):
            off = ROLAND_SAMPLE_BASE + ROLAND_SAMPLE_LEN * i
            if off + ROLAND_SAMPLE_LEN > img.size:
                break
            r = img.at(off, ROLAND_SAMPLE_LEN)
            if len(r) < ROLAND_SAMPLE_LEN or not any(r):
                break
            size = _le16(r, ROL_SIZE)
            # THE TABLE IS PADDED WITH 0xFF, NOT WITH ZEROS, and stopping
            # only at a zero size runs the scan into the padding and then
            # into the audio region: 0x2B5800 is 8192 records past the base,
            # and a first version of this reader returned 8275 on both discs
            # where the real counts are 5761 and 4128. Padding reads as rate
            # code 15 and loop mode 255, which is how it was spotted.
            if size == 0 or all(b == 0xFF for b in r):
                break
            if not 0 < r[ROL_ROOT_KEY] < 128:
                break
            name = r[:12].decode('latin1').rstrip('\x00 ').rstrip()
            code = r[ROL_RATE_CODE] & 0x0F
            rate = (ROLAND_RATES[code] if code < len(ROLAND_RATES)
                    else ROLAND_RATE_DEFAULT)
            out.append(dict(
                index=i, name=name, root=r[ROL_ROOT_KEY], size=size,
                rate_code=code, rate=rate,
                loop_mode=r[ROL_LOOP_MODE],
                start=_le24(r, ROL_START),
                loop_start=_le24s(r, ROL_LOOP_START),
                loop_end=_le24(r, ROL_LOOP_END),
                audio_off=ROLAND_AUDIO_BASE + running * ROLAND_AUDIO_BLOCK,
                audio_len=size * ROLAND_AUDIO_BLOCK))
            running += size
            i += 1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Partials — the level that becomes a preset
# ─────────────────────────────────────────────────────────────────────────────
#
# Three levels sit on the disc and the naming in the record has drifted:
#
#   patch directory  0x0A5800   32-byte entries: 16-byte name + a linked list
#   patch records    0x155800   512 bytes, performance level
#   PARTIAL records  0x1D5800   128 bytes -- 16-byte name + FOUR 16-byte zone
#                               sub-records. **This is the instrument**, and
#                               it is what a preset is built from.
#
# `docs/FIRMWARE_IMPORT_ROUTINES.md` calls the 128-byte record "the patch
# record" in one place; the 128-byte stride is the PARTIAL base, and the
# cross-reference below is what settles it rather than the prose.
#
# **Verified end to end on CD 2:** the patch directory entry `BA1:MC-202`
# (id 0x67) has a partial at index 380 whose zone 0 names sample **570**, and
# sample record 570 reads `BA1:MC 202`. Name, level and index all agree.

ROLAND_ZONES_PER_PARTIAL = 4
ROLAND_PARTIAL_NAME = 16
#: **THE FOUR SUB-RECORDS ARE VELOCITY ZONES, NOT KEY ZONES.** A first
#: version of this reader read `sub[8]`/`sub[9]` as a key range because they
#: hold 0 and 127 on the partials it looked at; they are the velocity fade
#: and velocity high. **The key range is not in the partial at all** — the
#: zone builder takes it from `patch[12..15]`, one level up.
#:
#: Every offset here is into the **16-byte sub-record** at `+16 + k*16`, not
#: into the 128-byte record: each one below 16 lands inside the record's own
#: 4-byte tag and 12-byte name, which is how the first published table came
#: to be right and addressed from the wrong origin.
ROL_Z_SAMPLE = 0         #: LE16; 0xFFFF = unused
ROL_Z_GATE = 2           #: 8 = pitched — the doc's "sub[2] gate"
ROL_Z_LEVEL = 3
ROL_Z_PAN = 4            #: signed, confined to ±32 on 6884/6884 records
ROL_Z_COARSE = 5         #: signed semitones; ±12 observed, an octave
ROL_Z_FINE = 6           #: signed, confined to ±50 — Roland's ±50 cents
ROL_Z_LO_VEL = 7
ROL_Z_VEL_FADE_LO = 8
ROL_Z_HI_VEL = 9
ROL_Z_VEL_FADE_HI = 10


def roland_pan(sub4: int) -> int:
    """`pan = clamp(sub[4] * 2, -64, +63)`.

    [C: corpus, 6884 partial records on two discs.]

    ⚠ **"The clamp never fires on real material" is REFUTED — measured over
    26 925 zones on SEVEN discs.** `sub[4]` is not confined to ±32: **822
    zones (3.05 %) exceed it**, reaching **+34**, on four of the seven
    images and on plainly real instruments (`HRP:Harp C4`, `BEL:_Orch Bl B2`,
    `STR:Solo Tune Up`). Only ever positive — `+33` (717) and `+34` (105),
    never `−33`.

    So the clamp DOES fire, on 822 zones. *That is evidence for the formula
    rather than against it*: a clamp the firmware bothers to write, that
    never fires, would be the suspicious result. And the asymmetry fits the
    E4's own asymmetric range — `−32 × 2 = −64` is exactly reachable while
    `+32 × 2 = +64` overshoots `+63` by one.

    **The original claim was true on the two discs it was measured on and
    false on the other five** — the corpus-is-uniform trap, from a corpus
    that was two sevenths of the material.
    """
    v = sub4 - 256 if sub4 > 127 else sub4
    return max(-64, min(63, v * 2))


def roland_fine_tune(sub6: int) -> int:
    """`fine tune = (sub[6] * 64 + 32) / 100`, in 1/64-semitone units.

    [C: corpus, same 6884 — `sub[6]` is confined to ±50 and touches both
    rails on CD 1, which is Roland's documented ±50 cents read off the disc
    rather than inferred from the arithmetic.]
    """
    v = sub6 - 256 if sub6 > 127 else sub6
    return (v * 64 + 32) // 100

ROLAND_UNUSED_SAMPLE = 0xFFFF


def read_roland_partials(path: str, limit: Optional[int] = None) -> List[dict]:
    """Every partial: a name and up to four zones naming sample indices."""
    out: List[dict] = []
    with RolandImage(path) as img:
        i = 0
        while True:
            if limit and len(out) >= limit:
                break
            off = ROLAND_PARTIAL_BASE + ROLAND_PARTIAL_STRIDE * i
            if off + ROLAND_PARTIAL_STRIDE > ROLAND_SAMPLE_BASE:
                break
            r = img.at(off, ROLAND_PARTIAL_STRIDE)
            if len(r) < ROLAND_PARTIAL_STRIDE or not any(r) or r[0] == 0xFF:
                break
            zones = []
            for z in range(ROLAND_ZONES_PER_PARTIAL):
                sub = r[ROLAND_PARTIAL_NAME + 16 * z:
                        ROLAND_PARTIAL_NAME + 16 * (z + 1)]
                sid = _le16(sub, ROL_Z_SAMPLE)
                if sid == ROLAND_UNUSED_SAMPLE:
                    continue
                coarse = sub[ROL_Z_COARSE]
                zones.append(dict(
                    sample=sid, gate=sub[ROL_Z_GATE], level=sub[ROL_Z_LEVEL],
                    coarse=coarse - 256 if coarse > 127 else coarse,
                    pan=roland_pan(sub[ROL_Z_PAN]),
                    fine=roland_fine_tune(sub[ROL_Z_FINE]),
                    lo_vel=sub[ROL_Z_LO_VEL], hi_vel=sub[ROL_Z_HI_VEL],
                    vel_fade_lo=sub[ROL_Z_VEL_FADE_LO],
                    vel_fade_hi=sub[ROL_Z_VEL_FADE_HI]))
            out.append(dict(index=i,
                            name=r[:ROLAND_PARTIAL_NAME].decode('latin1')
                            .rstrip('\x00 ').rstrip(),
                            zones=zones))
            i += 1
    return out


def parse_roland_image(path: str, wav_dir: Optional[str] = None,
                       quiet: bool = False,
                       limit: Optional[int] = None,
                       firmware_sim: bool = False,
                     firmware_sim_target: Optional[str] = None) -> Bank:
    """A Roland disc as one `Bank`: one preset per partial that names a sample."""
    from models.common import (Bank, LoopType, Preset, SampleData, VoiceLayer,
                               ZoneMapping)

    samples = read_roland_samples(path)
    partials = read_roland_partials(path)
    bank = Bank(name=os.path.splitext(os.path.basename(path))[0][:16])
    used: Dict[int, str] = {}

    with RolandImage(path) as img:
        for part in partials:
            if limit and len(bank.presets) >= limit:
                break
            zones = []
            for z in part['zones']:
                sid = z['sample']
                if sid >= len(samples):
                    continue
                s = samples[sid]
                if sid not in used:
                    nm = f"{s['name'][:11] or 'SMP'}{sid:05d}"[:16]
                    pcm = img.at(s['audio_off'], s['audio_len'])
                    frames = len(pcm) // 2
                    ls, le = max(0, s['loop_start']), s['loop_end']
                    # `record[+36]`: mode 2 is the one-shot, and it is the
                    # single most common value on every known Roland disc.
                    looped = (s['loop_mode'] == ROLAND_LOOP_LOOPED
                              and 0 <= ls < le <= frames)
                    bank.samples.append(SampleData(
                        name=nm, data=pcm, sample_rate=s['rate'], channels=1,
                        bit_depth=16,
                        loop_type=LoopType.FORWARD if looped
                        else LoopType.NO_LOOP,
                        loop_start=ls if looped else 0,
                        loop_end=le if looped else 0,
                        root_note=s['root'] if 0 < s['root'] < 128 else 60))
                    used[sid] = nm
                # FULL KEY RANGE, deliberately. The key quartet is written
                # from `patch[12..15]` -- one level up, and the patch ->
                # partial linkage is not decoded here yet -- so a partial's
                # four sub-records are VELOCITY layers over whatever key
                # range the patch gives them. Writing 0..127 is the honest
                # default; inventing a key split from the velocity bytes is
                # what the first version of this reader did.
                lo_v, hi_v = z['lo_vel'], z['hi_vel']
                if lo_v > hi_v:
                    lo_v, hi_v = hi_v, lo_v
                zones.append(ZoneMapping(
                    sample_name=used[sid], lo_key=0, hi_key=127,
                    lo_vel=lo_v, hi_vel=hi_v,
                    root_key=s['root'] if 0 < s['root'] < 128 else 60,
                    coarse_tune=z['coarse'],
                    fine_tune=int(round(z['fine'] * 100 / 64.0)),
                    pan=max(-1.0, min(1.0, z['pan'] / 64.0)),
                    # EOS CLEARS THE ZONE VOLUME (`entry[15]`, an explicit
                    # `clr`), so this path leaves it at unity deliberately.
                    volume=0.0))
            if zones:
                bank.presets.append(Preset(name=part['name'][:16],
                                           voices=[VoiceLayer(zones=zones)]))
    # Set in BOTH modes: the source/target restriction
    # (`EXTERNALLY_VERIFIABLE_ONLY`) applies to ordinary
    # conversions too, so the tag cannot live inside the
    # simulation branch.
    bank.source_format = 'roland'
    if firmware_sim:
        # ⚠ **TWO DIFFERENT SIMULATIONS, AND ONLY ONE IS HERE.**
        # For an E4B target this rebuilds each preset the way EOS
        # would. For a KRZ target the simulation is WRITER-side --
        # the K2000 clones a template and writes a handful of
        # fields -- so the bank passes through untouched and
        # `write_krz` does the work, told which import to
        # reproduce by the tag set below.
        bank.firmware_sim_source = 'roland'
        if firmware_sim_target not in (None, 'e4b', 'krz'):
            raise ValueError(
                "--firmware-sim for a roland source is implemented "
                "for --format e4b and krz only.")
        # ⚠ NOT a conversion option -- reproduces what EOS's own
        # importer writes. Byte-exact against the E4XT's own output on
        # 25/25 voices of a Roland reference disc; see eos_firmware_sim.
        if firmware_sim_target in (None, 'e4b'):
            from writers.eos_firmware_sim import simulate_eos_foreign_preset
            bank.presets = [simulate_eos_foreign_preset(p)
                            for p in bank.presets]
    return bank
