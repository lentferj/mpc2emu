# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# Part of mpc2emu — https://github.com/lentferj/mpc2emu
# Contributions: Jan Lentfer, with AI assistance (see README).
"""EOS 4.7's own import laws, reproduced exactly — the E4B half of the
firmware-import simulation.

**This module is not a converter. It is a measuring instrument.** Everything
here answers one question: *what would the E4XT itself have written?* A bank
built through it can be diffed against a bank the machine imported from the
same source, and **every difference is a defect in this project's reading of
the firmware** rather than a matter of taste. That is the whole value, and it
is destroyed the moment a field here falls back to one of this project's own
laws because EOS's behaviour for it is unknown. Where EOS's behaviour is not
established, this module writes **nothing** and says so, so the diff stays
honest — see `krz_writer.FIRMWARE_WRITES_K2000_AKAI` for the same rule stated
on the Kurzweil side.

`docs/FIRMWARE_IMPORT_ROUTINES.md` carries the evidence for every constant.

**Provenance of the machine code read here.** EOS 4.7, built from
`EMU_EOS470_OMNIFLOP.img` with `eosflash export` + `eosflash flash --4mb`:
1 965 696 bytes, **md5 `92a7ecced0f855f0b711f0bfe5cc89c7`**, load base
`0x20000` so file offset = address − `0x20000`. The md5 is quoted because
`eosed` and this project each built the image independently and compared it
before either read a byte out of it; if a third reader's md5 differs, every
address below is about a different firmware.
"""

from decimal import Decimal, ROUND_HALF_UP

from models.common import akai_program_loudness_to_e4b_db

__all__ = [
    'FIRMWARE_WRITES_EOS_AKAI',
    'EOS_T_ATK', 'EOS_T_DEC',
    'eos_rescale', 'eos_env_rate_index',
    'eos_akai_cords', 'eos_akai_amp_envelope', 'eos_akai_preset_volume',
    'EOS_AKAI_CORD_SLOT_LIMIT',
]


#: ✅ **What EOS's own AKAI importer writes, and nothing else.**
#:
#: Unlike the K2000's AKAI import — which clones a template program and writes
#: five fields — **EOS genuinely converts**, so "simulate it" here means
#: reproducing arithmetic rather than declining to write. The list is what has
#: been established; `[?]` fields are absent from it deliberately.
FIRMWARE_WRITES_EOS_AKAI = (
    'preset_volume',        # header[27], 363/363 against EOS's own output
    'amp_envelope',         # PZT[0..11] through T_atk / T_dec, 564/564
    'cords',                # the ten-cord keygroup pass, below
    'transpose_clamp',      # header[26], +-24
)


# ---------------------------------------------------------------------------
# The generic rescaler at 0x2f6b4
# ---------------------------------------------------------------------------

def eos_rescale(value: int, lo: int, hi: int, scale: int) -> int:
    """EOS's one rescaler, `0x2f6b4`, as the instruction stream has it.

    The routine doubles, adds 1 **when positive**, then arithmetic-shifts
    right — which is *round half away from zero*, not truncation and not
    Python's banker's rounding. The three differ at every exact half, and the
    AKAI cord scales (`96/50`, `48/50`) land on an exact half often enough
    that the choice is measurable: `kf 4` is `7.68` and rounds to 8, but
    `va 17` is `16.32` and rounds to 16, and a truncating implementation gets
    the second right and the first wrong.

    **Verified end to end, not just read.** All eight measured keyfollow
    points and all twelve measured `vel_to_attack` points on the E4XT
    reproduce exactly through this function plus the SysEx read-back scaling
    — see `tests/test_eos_firmware_sim.py`.
    """
    v = max(lo, min(hi, value))
    return int((Decimal(v * scale) / Decimal(hi)).quantize(0, ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# The envelope rate tables, 0x303d0 and 0x30434
# ---------------------------------------------------------------------------

#: ✅ **EOS computes no envelope time at all.** Attack, decay and release are
#: three lookups into two 100-byte tables — and decay and release share one.
#: Read out of the firmware here and byte-identical to `eosed`'s independent
#: read of the same addresses.
#:
#: ⚠ **`T_atk` IS FLAT AT ZERO FOR ITS FIRST 21 ENTRIES**, so AKAI attack 0
#: through 20 all import as rate 0. A sim/device diff over material with short
#: attacks therefore agrees *trivially* on those voices and tests nothing —
#: the table only starts discriminating at `kg[0x0c] >= 21`. `eosed` flagged
#: this when handing the tables over, and it is the right kind of warning: **a
#: faithful sim that agrees with the device for the wrong reason is worse than
#: one that disagrees, because it retires a test nobody actually ran.**
EOS_T_ATK = bytes((
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   #  0..9
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 10..19
    0x00, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,   # 20..29
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x02, 0x02,   # 30..39
    0x02, 0x02, 0x02, 0x03, 0x03, 0x03, 0x04, 0x04, 0x04, 0x05,   # 40..49
    0x06, 0x06, 0x07, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,   # 50..59
    0x11, 0x12, 0x13, 0x15, 0x17, 0x19, 0x1a, 0x1c, 0x1d, 0x1f,   # 60..69
    0x21, 0x23, 0x25, 0x27, 0x28, 0x2a, 0x2c, 0x2e, 0x30, 0x32,   # 70..79
    0x34, 0x36, 0x38, 0x3a, 0x3c, 0x3e, 0x3f, 0x41, 0x43, 0x45,   # 80..89
    0x47, 0x4a, 0x4b, 0x4d, 0x4f, 0x51, 0x53, 0x55, 0x57, 0x59,   # 90..99
))

EOS_T_DEC = bytes((
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,   #  0..9
    0x01, 0x01, 0x01, 0x01, 0x01, 0x02, 0x02, 0x02, 0x02, 0x02,   # 10..19
    0x02, 0x03, 0x03, 0x03, 0x03, 0x03, 0x03, 0x04, 0x04, 0x04,   # 20..29
    0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0e,   # 30..39
    0x0f, 0x10, 0x11, 0x12, 0x13, 0x14, 0x16, 0x17, 0x19, 0x1a,   # 40..49
    0x1c, 0x1d, 0x1f, 0x20, 0x22, 0x24, 0x25, 0x27, 0x28, 0x2a,   # 50..59
    0x2c, 0x2e, 0x30, 0x32, 0x34, 0x36, 0x37, 0x39, 0x3b, 0x3d,   # 60..69
    0x3f, 0x40, 0x42, 0x44, 0x46, 0x48, 0x49, 0x4b, 0x4c, 0x4e,   # 70..79
    0x50, 0x52, 0x54, 0x55, 0x57, 0x59, 0x5a, 0x5c, 0x5d, 0x5e,   # 80..89
    0x60, 0x61, 0x63, 0x64, 0x66, 0x67, 0x68, 0x6a, 0x6c, 0x6e,   # 90..99
))

#: The E4B rate byte each table can reach — `T_atk` stops at 89, `T_dec` at
#: 110, and both are monotonic non-decreasing. So **EOS cannot produce the
#: fastest attacks the E4XT is capable of** from any AKAI program.
EOS_T_ATK_MAX = 89
EOS_T_DEC_MAX = 110


def eos_env_rate_index(byte: int) -> int:
    """The index EOS actually uses, from the two identical clamp sites
    `0x2f7c8` (attack) and `0x2f7ec` (decay/release).

    **It is not `clamp(b, 0, 99)`.** The code does `extbl` — sign-extend the
    byte — and sends anything *negative* to 0 before clamping the rest to 99.
    So a stored `200` is read as `−56` and imports as rate **0**, the slowest
    the table has, where a plain unsigned clamp would give 99, the fastest.
    The two answers sit at opposite ends of the table.

    **How often that matters: 3 keygroups in 69 062, on 1 disc of 21** (the
    whole AKAI ISO corpus here, 10 933 programs). So it is real, reachable,
    and negligible — implemented because it is free, and recorded with its
    prevalence so nobody spends bench time confirming it.
    """
    b = byte - 256 if byte > 127 else byte
    return 0 if b < 0 else min(99, b)


def eos_akai_amp_envelope(kg: bytes) -> dict:
    """`{PZT offset: byte}` for the amp envelope, from one AKAI keygroup.

    [C: 564/564 exact, input to output, against 141 single-keygroup programs]

        PZT[0]/[1]   Attack1   T_atk[kg 0x0c]            127
        PZT[2]/[3]   Attack2   0                         127
        PZT[4]/[5]   Decay1    0                         127   <- a plateau
        PZT[6]/[7]   Decay2    T_dec[kg 0x0d]            round(kg 0x0e *127/99)
        PZT[8]/[9]   Release1  T_dec[kg 0x0f]            0
        PZT[10]/[11] Release2  0                         0

    **Decay1 is a plateau and that is not a rounding of our own model** — EOS
    spends the whole decay in stage 2 and leaves stage 1 flat at full level.
    A converter that split the decay across both stages would sound close and
    diff wrong on every voice.
    """
    return {
        0:  EOS_T_ATK[eos_env_rate_index(kg[0x0c])],  1:  127,
        2:  0,                                        3:  127,
        4:  0,                                        5:  127,
        6:  EOS_T_DEC[eos_env_rate_index(kg[0x0d])],
        7:  eos_rescale(eos_env_rate_index(kg[0x0e]), 0, 99, 127),
        8:  EOS_T_DEC[eos_env_rate_index(kg[0x0f])],  9:  0,
        10: 0,                                        11: 0,
    }


# ---------------------------------------------------------------------------
# The mod-source enum map, 0x48ab0
# ---------------------------------------------------------------------------

#: ✅ **AKAI mod-source selector → E4B cord source id.** Fifteen bytes at
#: `0x48ab0`, indexed at `0x47d4a` by `clamp(selector, 0, 14)` — with the same
#: `extbl`/negative→0 shape as the envelope tables — and stashed into the
#: staging struct at `%a5@(59..61)`.
#:
#: **This closed the last gap in the AKAI cord pass, and it did not need the
#: rig.** The plan of record an hour earlier was a card swap: load a volume
#: spanning many distinct `MODSFILT` values and read back which source ids
#: came out. `eosed` found the table instead.
#:
#: ⚠ **AND IT HAD BEEN FOUND ALREADY, AND FILED AS NOT-A-TABLE.** `eosed`'s
#: own notes carried `0x48ab0` under *"do not build on: its values are not
#: monotonic and do not look like a mapping"*. **Both observations were
#: correct.** An enum map is not monotonic and does not look like a mapping —
#: it looks like noise, because it is a permutation of unrelated ids rather
#: than a curve. *The property used to rule it out was the property that
#: identifies it*, and the test was reached for because the neighbouring
#: tables are rate and level curves — a classification inherited from context
#: rather than tested against what the thing could be. It sat in the discard
#: bucket for two days while both projects called its contents the blocker.
#:
#: ✅ **Two corroborations neither side designed:**
#:
#: * selector `10` → `80` (`FEnv+`) is *exactly* the gate condition at
#:   `0x46910`, so the table and the emitter agree about one specific id;
#: * **no entry falls outside the known cord-source set.**
EOS_AKAI_MOD_SOURCE_TABLE = bytes((
    0,    # 0  Off
    17,   # 1  ModWl
    16,   # 2  PitWl
    18,   # 3  Press
    20,   # 4  MidiA
    10,   # 5  Vel+
    9,    # 6  Key~
    97,   # 7  Lfo1+
    105,  # 8  Lfo2+
    72,   # 9  VEnv+
    80,   # 10 FEnv+     <- the id that creates the kg[0x1c] gate
    17,   # 11 ModWl     (duplicates 1, 2 and 4 -- the AKAI enum is not
    16,   # 12 PitWl      injective into EOS's sources, so a round trip
    20,   # 13 MidiA      cannot recover which selector was written)
    88,   # 14 AEnv+
))


def eos_akai_mod_source(selector: int) -> int:
    """AKAI `MODSFILT`/`MODS*` selector → E4B cord source id, via `0x48ab0`."""
    v = selector - 256 if selector > 127 else selector
    return EOS_AKAI_MOD_SOURCE_TABLE[0 if v < 0 else min(14, v)]


#: ⚠ **Our own parser's enum reading was right, and its caveat was ALSO
#: right — they are about different things.**
#:
#: `akai_s3000_parser` records `MODSFILT1=5` (velocity), `2=8` (LFO2),
#: `3=10` (env2) from two programs, flagged as *"may be this library's common
#: template rather than a fixed convention, so this is read per-program rather
#: than assumed."* The firmware table agrees at all three, so the **meaning**
#: of each selector value is EOS's fixed convention.
#:
#: The caveat was about which **values appear**, not what they mean — and a
#: sweep of 21 AKAI discs here settles that one the other way: **106 distinct
#: `(MODSFILT1,2,3)` combinations**, with `MODSFILT2` alone taking 14
#: different values. Reading them per-program was correct. *Neither statement
#: replaces the other, and collapsing them into "the enum is confirmed" would
#: lose the half that governs how the parser behaves.*


# ---------------------------------------------------------------------------
# The keygroup cord pass — function 0x4647c
# ---------------------------------------------------------------------------
#
# ✅ **This is the arm the AKAI disc import runs**, established by the call
# graph and then **confirmed on hardware**: `0x4647c` <- `0x473a6` in
# `0x46da8` <- `0x47650` in `0x475b4` <- `0x47fea` in `0x47f08` <- `0x489c0`
# in **`0x48934`**, the AKAI orchestrator.
#
# ❌ **AND THE SENTENCE THAT USED TO FOLLOW WAS WRONG, TWICE OVER.** It read:
# *"a second, near-identical cord emitter exists at `0x4430c` … reached only
# through a pointer at `0x1f901e`, so it belongs to one of the other
# importers"*, and *"the AKAI arm does not have this bug"*.
#
# **`0x4430c` IS AKAI.** The pointer at `0x1f901e` is index 2 of the `A3S1`
# record in an AKAI format-descriptor table at `0x1f9012`. The call-graph
# query found no `jsr`/`bsr` and one data pointer — that half was right — and
# *"therefore a different importer"* was an inference with no evidence,
# published under a heading claiming the method as its authority.
#
# ⚠ The guard/value mismatch at `0x44958` is real and **is in an AKAI arm**:
#
#     44958:  tstb %a3@(19)         <- guards on byte 0x13
#     44972:  moveb %a3@(27),%d0    <- converts byte 0x1b
#
# ✅ **What is true is narrower and was settled on the device 2026-09-23.**
# `eosed` imported a 128-program S3000 volume with predictions pre-registered
# from the buggy arm, and **two of five failed** — a `0x13 = 0, 0x1b = -50`
# keygroup produced a cord where the mismatch predicts none, and a
# `0x13 = -24, 0x1b = 0` keygroup produced none where it predicts one. Both
# match `0x46b7e`, which guards and reads `0x1b` both times.
#
# **So this import path does not reach `0x4430c`. That is not the same claim
# as `0x4430c` belonging elsewhere**, and the difference is what took two
# sessions and a hardware import to establish. What *does* reach it is open.
#
# ✅ **Narrowed again the same evening, with a readback rather than a
# prediction.** `eosed`'s `f40aa23`: an S3000 program with `0x13 = 0` and
# `0x1b = -50`, imported from CD-ROM, reads back `Key+ -> FEnvRls AMT = -38`.
# That is `clamp(-50, -50, 50) * 48/50 = -48` stored and `-48 * 100/127` on
# the wire -- **both constants derived here independently and neither fitted
# to that measurement**, so it is a prediction the device confirmed rather
# than a curve through it.
#
# The open question is therefore not *which disc*: CD-ROM S3000 import is
# now measured and it reaches the orchestrator arm. **Whatever reaches the
# descriptor-driven arm is a different kind of TRANSFER, not a different
# kind of disc** -- a smaller search space than "some import somewhere".
#
# ⚠ **AND THIS COMMENT SURVIVED ITS OWN CORRECTION.** The error was retracted
# to `eosed` in a message, recorded in `docs/FIRMWARE_IMPORT_ROUTINES.md`, and
# left standing here — and this project then told them *"our module never
# carried it in code"*, which was a claim about this file made without opening
# it. **The auditable channel was the one that kept the wrong text**, which is
# the opposite of the conclusion drawn at the time.

#: Every keygroup byte EOS turns into a cord, **in emission order**, with the
#: source and destination ids as literal `moveq` operands and the scale as the
#: literal pushed to `0x2f6b4`. All ten clamp to `(-50, +50)`.
#:
#:     (akai_keygroup_offset, src, dst, scale)
EOS_AKAI_CORDS = (
    (0x08,  8, 56, 96),   # Key+   -> FilFreq
    (0x10, 10, 73, 48),   # Vel+   -> VEnvAtk
    (0x11, 10, 75, 48),   # Vel+   -> VEnvRls
    (0x12, 13, 75, 48),   # RlsVel -> VEnvRls
    (0x13,  8, 75, 48),   # Key+   -> VEnvRls   (O7: 0x4B, *not* 0x4A VEnvDcy)
    (0x18, 10, 81, 48),   # Vel+   -> FEnvAtk
    (0x19, 10, 83, 48),   # Vel+   -> FEnvRls
    (0x1a, 13, 83, 48),   # RlsVel -> FEnvRls
    (0x1b,  8, 83, 48),   # Key+   -> FEnvRls
)

#: The source id whose cords EOS **negates**, and the rule is per-SOURCE.
#:
#: ⚠ **Two hardware results looked contradictory and this is why they are
#: not.** `O7b` measured twelve `vel_to_attack` points that all came back with
#: the sign flipped; `O7` measured `kg[0x13] = -5` arriving as amount `-5`,
#: not flipped. Neither is wrong: **`negl %d0` sits in exactly the four
#: `Vel+` blocks** (`0x46998`, `0x469dc`, `0x46aa4`, `0x46ae8`) and in none of
#: the `Key+` or `RlsVel` ones.
#:
#: **The plausible theory was wrong.** "E4B envelope destinations are *rates*
#: and AKAI's are *times*, so envelope cords invert" predicts the `Key+ ->
#: VEnvRls` cord inverts too, and it does not. The rule is about the source,
#: and no amount of reasoning about rate-versus-time would have produced it —
#: it came off the instruction stream.
EOS_AKAI_NEGATED_SRC = 10   # Vel+

#: EOS abandons the keygroup's cord run once the cursor reaches this, checked
#: **after** each write (`moveq #24,%d0; cmpl %d7,%d0; ble abandon`).
EOS_AKAI_CORD_SLOT_LIMIT = 24


def eos_akai_cords(kg: bytes, modsfilt=(0, 0, 0), first_slot: int = 0):
    """`[(slot, src, dst, amount_byte), ...]` for one AKAI keygroup, in EOS's
    own emission order.

    `modsfilt` is the program's `MODSFILT1/2/3` selectors (program bytes
    84/85/86) — program-level, which is why they arrive as an argument rather
    than out of `kg`.

    `amount_byte` is the **stored** signed byte, which is what lands in the
    E4B file. A SysEx read-back of the same cord reports `round(stored *
    100/127)` instead, because the wire field is a ±100 scale over a ±127
    stored one — so a measurement taken off `eosed` must be compared against
    that, not against this.

    ⚠ **The divisor was 128 until 2026-09-22**, and all 19 hardware points
    held at the time agree under both — which is why it lasted. Stored 96 is
    the first discriminating value either project measured, and it arrived
    because the validation material was chosen for **selector spread** rather
    than for the question being asked. *A constant that every measurement you
    have agrees with is not thereby measured.*

    **The guard is part of the law, not an optimisation.** A zero AKAI byte
    writes no cord *and does not advance the cursor*, so cords are packed
    densely with no gaps. On the reference disc 92.5% of keygroups take that
    branch for every byte. The three assignable slots are guarded **twice** —
    on the mapped source id *and* on the amount.
    """
    slot = first_slot
    out = []
    gate_slot = None

    # -- the three assignable filter-mod slots, 0x46832 / 0x46890 / 0x468f4 --
    for sel, off in zip(modsfilt, EOS_AKAI_MODVFILT_AMOUNT_BYTES):
        if off >= len(kg):
            continue
        src = eos_akai_mod_source(sel)
        if src == 0 or kg[off] == 0:      # both guards, 0x468f8 and 0x46900
            continue
        if src == EOS_AKAI_GATE_SRC and gate_slot is None:
            gate_slot = slot              # 0x46910: first FEnv+ slot only
        v = kg[off] - 256 if kg[off] > 127 else kg[off]
        out.append((slot, src, 56, eos_rescale(v, -50, 50, 96)))
        slot += 1
        if slot >= EOS_AKAI_CORD_SLOT_LIMIT:
            return out

    # -- the nine fixed cords, 0x46956 onwards ------------------------------
    for off, src, dst, scale in EOS_AKAI_CORDS:
        if off >= len(kg) or kg[off] == 0:
            continue                      # guard: no cord, cursor unmoved
        v = kg[off] - 256 if kg[off] > 127 else kg[off]
        amt = eos_rescale(v, -50, 50, scale)
        if src == EOS_AKAI_NEGATED_SRC:
            amt = -amt
        out.append((slot, src, dst, amt))
        slot += 1
        if slot >= EOS_AKAI_CORD_SLOT_LIMIT:
            return out                    # the run is abandoned, not wrapped

    # -- the cord-amount gate, 0x46bb0 --------------------------------------
    # Emitted only when one of the three slots above carried FEnv+, which is
    # what `%d4 == -1` tests. Its destination is another cord's AMOUNT.
    if gate_slot is not None and EOS_AKAI_GATE_AMOUNT_BYTE < len(kg) \
            and kg[EOS_AKAI_GATE_AMOUNT_BYTE] != 0:
        v = kg[EOS_AKAI_GATE_AMOUNT_BYTE]
        v = v - 256 if v > 127 else v
        dst = EOS_AKAI_CORD_AMOUNT_DEST_BASE + gate_slot
        # TWO cords share this destination, from one keygroup byte at two
        # different scales -- 0x46bc6 and 0x46c06. The second was missed here
        # until 2026-09-22 because the first looked like the whole mechanism.
        for src, scale in EOS_AKAI_GATE_CORDS:
            out.append((slot, src, dst, eos_rescale(v, -50, 50, scale)))
            slot += 1
            if slot >= EOS_AKAI_CORD_SLOT_LIMIT:
                break
    return out


#: The keygroup byte whose cords gate another cord's amount — `0x46bb0`.
EOS_AKAI_GATE_AMOUNT_BYTE = 0x1c

#: ✅ **`kg[0x1c]` writes TWO cords, not one** — `(src, scale)` each, both onto
#: the same computed destination, from the same byte at different scales:
#:
#:     0x46bc6   src  11   scale 50
#:     0x46c06   src 160   scale 11
#:
#: The second was missed here for as long as the gate has existed, because the
#: first looked like the whole mechanism. `eosed` found it while resolving an
#: unrelated address.
EOS_AKAI_GATE_CORDS = ((11, 50), (160, 11))

#: ✅ **The `%d4` latch cannot leak a destination of 167**, and this is a
#: *checked* non-finding rather than an unexamined one. `%d4` is initialised
#: to `-1` at `0x46496` and set to the cord index by whichever of emitter
#: blocks 10/11/12 fires first, each behind its own `cmpl %d4,#-1`. The gate
#: block then tests **twice** — `tstb %a3@(28)` at `0x46bb0` for a non-zero
#: `kg[0x1c]`, and `cmpl %d4,#-1` at `0x46bba` for the latch being set — so
#: `addl #168,%d4` at `0x46bca` can never run on `-1`.
#:
#: `eosed` predicted this hazard from the shape of the code, **checked it
#: before forwarding it**, and sent it as a non-finding. Had it arrived as a
#: warning this project would have hunted a bug that does not exist. *A
#: predicted hazard is a hypothesis, and it gets checked before it gets
#: forwarded* — the day's rule aimed at one's own output rather than someone
#: else's.
EOS_AKAI_GATE_LATCH_IS_GUARDED = True


#: The three AKAI keygroup bytes the assignable filter-mod cords take their
#: amount from — `MODVFILT1/2/3`, i.e. `AKAI_MODVFILT1_OFFSET` and its two
#: siblings, which `parsers/akai_s3000_parser.py` had named long before any of
#: this was traced.
EOS_AKAI_MODVFILT_AMOUNT_BYTES = (0x97, 0x98, 0x99)

#: The E4B source id whose presence in a `MODVFILT` slot creates the gate that
#: `kg[0x1c]` writes into: `FEnv+`, selector 10.
EOS_AKAI_GATE_SRC = 80

#: ✅ **The seven program-level mod slots — solved 2026-09-22, both halves.**
#:
#: Ahead of everything above, the same function runs seven more blocks through
#: the shared emitter at `0x46370`. Their SOURCE is the `0x48ab0` enum map
#: this module already carries; their AMOUNT is a rescale of one program byte.
#: All seven identical in shape, three distinct scales:
#:
#:     slot   operand    operand    AKAI program byte   scale
#:       1    %a5@(33)   %a5@(36)   raw[92]                75
#:       2    %a5@(34)   %a5@(37)   raw[93]                75
#:       3    %a5@(38)   %a5@(41)   raw[89]                48
#:       4    %a5@(39)   %a5@(42)   raw[90]                48
#:       5    %a5@(40)   %a5@(43)   raw[91]                48
#:       6    %a5@(50)   %a5@(53)   raw[94]                25
#:       7    %a5@(51)   %a5@(54)   raw[95]                48
#:
#: ⚠ **THE TWO RIGHT-HAND COLUMNS DO NOT DESCRIBE THE SAME POINTER, and
#: reading the table as if they did is what produced the retracted
#: `d[N]`-are-file-offsets claim (ef7e864 / 585b9df).** Checked 2026-09-24:
#:
#:     disp    33  34  38  39  40  50  51
#:     file    92  93  89  90  91  94  95
#:     base   +59 +59 +51 +51 +51 +44 +44   <- THREE different bases
#:
#: One register at one point has one base. **The file column is the sound
#: one**: it comes from the frame-relative chain against `%fp@(-196)`, and
#: `fp + 196` reproduces every one of the seven exactly --
#:
#:     -104 -103 -107 -106 -105 -102 -101   ->   92 93 89 90 91 94 95
#:
#: -- which holds because `0x4771c` copies the 192-byte program block
#: verbatim, so buffer index == file offset. Seven of seven, self-consistent,
#: and independent of whatever `%a5` is.
#:
#: **So `EOS_AKAI_PROGRAM_MOD_SLOTS` below is fine** -- it ships the file
#: column. What is wrong is the `%a5@(...)` column standing beside it with no
#: label: those are displacements into a DIFFERENT object, in the function at
#: `0x4647c`, and the two were tabulated together as though one implied the
#: other. That is also why the eleven unmodelled cords' `d[N]` displacements
#: could not be read as file offsets: same table, same conflation.
#:
#:     amount = eos_rescale(raw_byte, -50, +50, scale)
#:
#: ⚠ **THERE IS NO SHIFT, AND THE STORY THAT THERE WAS ONE LASTED FIVE
#: MINUTES.** `eosed`'s first table gave `86..92`, subtracted from the wrong
#: base. Checked against 10 933 programs on 21 discs, the raw record divides
#: sharply:
#:
#:     raw 84..88   10-14 distinct values, >=99.8% within 0..14   SELECTORS
#:     raw 89..95   13-51 distinct, every one spanning -50..+50   AMOUNTS
#:
#: `86..92` straddles that boundary, putting three slots on selector bytes —
#: rescaling a `0..14` enum through a `+-50` clamp. `+3` moved them onto the
#: contiguous amount run, so **this module proposed a +3 and explained it**:
#: the program name sits at `raw[3:15]`, so bytes 0..2 are a block prefix that
#: a parsed form would drop. Independent mechanism, not fitted to the data,
#: predicting exactly the observed offset.
#:
#: **It was explaining an arithmetic slip.** Re-derived from the base
#: `%fp@(-196)`, the seven reads are `%fp@(-104)`, `(-103)`, `(-107)`,
#: `(-106)`, `(-105)`, `(-102)`, `(-101)` = **92, 93, 89, 90, 91, 94, 95** —
#: the same bytes, no shift. And `0x4771c` is a verbatim 192-byte read from
#: offset 0 with exactly one in-place fixup, so **buffer index == file
#: offset**, directly.
#:
#: > **A MECHANISM THAT EXPLAINS A WRONG NUMBER IS MORE DANGEROUS THAN NO
#: > EXPLANATION**, because it turns *"these do not line up"* — a question —
#: > into *"these line up once you account for the prefix"* — an answer, and
#: > answers stop being checked. The corpus agreed because the shifted version
#: > was right about the **region** and wrong about **why**. *The load-bearing
#: > part of a claim is often not the claim*: the check ran against the region
#: > and passed, and the region was never in doubt.
#:
#: ✅ **The one fixup corroborates our parser — for EXACTLY ONE FIELD.**
#: `0x4771c` byte-swaps the 16-bit field at `raw[65]` in place, and the
#: converter then reassembles it big-endian from two byte loads at `0x47854`.
#: The two **compose** rather than cancel: `(buf[65]<<8)|buf[66]` after the
#: swap is `(file[66]<<8)|file[65]`, a little-endian read. *Each step alone
#: looks like the whole story and each is wrong alone.* That field is `tune`,
#: and `akai_s3000_parser` reads it `<h`. Correct.
#:
#: ⚠ **It says NOTHING about any other 16-bit field.** This module briefly
#: claimed the result "applies to every `_u16`/`_s16` in the parser". It does
#: not: across `0x47778..0x47e44` EOS makes **42 byte reads from the record
#: and zero word or long reads**, so `raw[65..66]` is the only multi-byte
#: field it takes at all, and **a byte-at-a-time read carries no endianness
#: information.** Confirmed-for-one, read downstream as confirmed-for-all.
#:
#: ✅ **The corpus settles the rest, and agrees** — 10 933 programs, 36 645
#: samples, each field read both ways:
#:
#:     SSRATE           0x8a  sample    LE 95.2% real sample rates   BE 0.0%
#:     loop_times       0x30  sample    LE 9999 (the hold sentinel) on 23 637
#:                                      of 23 641 non-zero; BE nothing
#:     tune_units       0x14  sample    LE 48.5% within +-200        BE 0.5%
#:     keygroup tune    0x05  keygroup  LE clusters on +-3072/+-512,
#:                                      i.e. exact multiples of 256 = semitones
#:     program tune     0x41  program   same, and firmware-confirmed above
#:
#: So every multi-byte read in the parser is little-endian — **established
#: from the corpus, which is the evidence that actually covers them, not from
#: the firmware, which is silent.** The conclusion was right and the reason
#: given for it was not, which is a worse position than being wrong loudly.
#:
#: **They still shift the slot base.** They run *first* and advance the same
#: cursor, so the relative order of everything this module emits is the
#: firmware's and the absolute slot numbers are not. A sim/device diff must
#: align cords on `(src, dst)`, not on slot — otherwise every cord of an
#: affected voice reports as misplaced, which on first run reads as total
#: failure rather than as a program-level slot.
EOS_AKAI_PROGRAM_MOD_SLOTS = (
    # (selector raw byte, amount raw byte, scale, dst)  -- dst None = computed
    (79, 92, 75, 64), (80, 93, 75, 64),
    (76, 89, 48, 65), (77, 90, 48, 65), (78, 91, 48, 65),
    (81, 94, 25, 96),
    (82, 95, 48, None),        # 168 + the cord index slot 1 was about to take
)

#: ✅ **`0xA8` (168) IS THE CORD-AMOUNT DESTINATION BASE, and it is pinned at
#: FIVE independent sites** — `0x466b4`, `0x466e0`, `0x4670c`, `0x46774` and
#: `0x46bca`. `eosed` read slot 7's `addl #168,%d0` and marked the base
#: `[S]`, not pinned; this project had independently modelled `kg[0x1c]`'s
#: gate as `0xA8 + slot` from `0x46bca`. *Same constant, two code sites, two
#: projects, neither fitted to the other* — so the base is confirmed and the
#: `[S]` can be lifted.
#:
#: ⚠ **And there are more gates than either of us modelled.** Five `addl #168`
#: sites means five cords whose destination is another cord's amount; `eosed`
#: had one (slot 7) and this module had one (`kg[0x1c]`). The three at
#: `0x466b4`/`0x466e0`/`0x4670c` are unmodelled. Likewise the emitter is
#: called **twelve** times in this function, where the block pattern scanned
#: here found ten — so the cord inventory is still not closed.
EOS_AKAI_CORD_AMOUNT_DEST_BASE = 168

#: ⚠ **Slot 7's destination is a SNAPSHOT, and it is taken before slot 1's
#: gate runs.** `%d5 := %d7` at `0x4657e`, immediately before slot 1's block
#: and with no reassignment before slot 7 (checked: `%d5`'s next write is
#: `0x46792`, past it). `%d7` is the cord cursor — it indexes the table as
#: `lea %a4@(0,%d7:l:4)`, is bounded by `cmpl #24`, and is passed to the
#: emitter **by reference** (`lea %fp@(-4),%a1`).
#:
#: So slot 7 points at *the index slot 1 was about to occupy*. **If slot 1 is
#: skipped — either half zero — that index is never consumed by slot 1 and
#: the next emitted cord takes it, so slot 7 modulates a different cord.**
#: `eosed`'s edge case, falling out of the by-reference counter, not tested
#: against hardware. It will not show up in an ordinary diff, which is exactly
#: why it is written down here rather than left to be rediscovered.
EOS_AKAI_SLOT7_DEST_IS_SNAPSHOT_OF_SLOT1_INDEX = True

#: ✅ **Both halves land on contiguous seven-byte runs, in the same slot
#: order** — selectors `raw[76..82]`, amounts `raw[89..95]`, with slots 3,4,5
#: first, then 1,2, then 6,7 in each. That the odd ordering reproduces across
#: two independently located runs is a corroboration nobody designed.
#:
#: All seven sources go through the **same `0x48ab0` lookup** as the keygroup
#: cords (`clamp(sel, 0, 14)`, `%a4` base) — verified at all seven writers
#: `0x47a1a`, `0x47a66`, `0x47adc`, `0x47b28`, `0x47b74`, `0x47cc8`,
#: `0x47d14`. So the enum map confirmed on hardware covers these too.
#:
#: Corpus check over 10 933 programs: `raw[76..88]` are all selector-shaped
#: (7–14 distinct values, most ≥99% within `0..14`) and `raw[89..95]` all
#: amount-shaped. `83`, `87` and `88` are three further selectors whose
#: destinations are not traced.


def eos_akai_program_cords(program: bytes, first_slot: int = 0):
    """`[(src, dst, amount_byte), ...]` for the seven program-level mod slots.

    These run **before** every keygroup cord and advance the same cursor, so
    a caller must emit them first and pass the resulting slot number on as
    `eos_akai_cords(..., first_slot=)`.

    Destinations are `64` (slots 1–2), `65` (3–5), `96` (slot 6) and, for
    slot 7, `168 + first_slot` — see the snapshot note above, including the
    case where slot 1 is skipped and the snapshot points elsewhere.
    """
    out = []
    for sel_off, amt_off, scale, dst in EOS_AKAI_PROGRAM_MOD_SLOTS:
        if sel_off >= len(program) or amt_off >= len(program):
            continue
        src = eos_akai_mod_source(program[sel_off])
        amt_raw = program[amt_off]
        amt_raw = amt_raw - 256 if amt_raw > 127 else amt_raw
        if src == 0 or amt_raw == 0:      # either half zero -> slot skipped
            continue
        if dst is None:
            # slot 7: 168 + the snapshot of slot 1's index, taken at 0x4657e
            # BEFORE slot 1's own gate runs.
            dst = EOS_AKAI_CORD_AMOUNT_DEST_BASE + first_slot
        out.append((src, dst, eos_rescale(amt_raw, -50, 50, scale)))
    return out


#: ✅ **One guard rule, uniform across every cord EOS emits from an AKAI
#: source:** a slot is skipped when *either* half is zero — the source id or
#: the amount. A zero amount **disables** the cord rather than writing a
#: zero-strength one. Same shape at the nine fixed cords, the three assignable
#: filter-mod slots (`0x468f8`/`0x46900`) and these seven (`0x46728`/
#: `0x46730`), so it is one rule rather than three observations.
EOS_AKAI_SKIPS_WHEN_EITHER_HALF_IS_ZERO = True

#: ⚠⚠ **THE CORD INVENTORY IS NOT CLOSED, AND THE GAP IS MUCH LARGER THAN
#: "TWO MORE".** Counted here over `0x4647c..0x46c7e`, a cord entry is
#: `%a4 + 4n` with `+188` src, `+189` dst, `+190` amt — and the source field
#: is written at **23 sites through five address registers**:
#:
#:     %a5@(188)  11      %a1@(188)   7      %a0@(188)   2
#:     %a3@(188)   1      %a4@(188)   1      %a4@(192)   1   <- slot 1, at 188+4
#:     emitter calls (bsrw 0x46370)          12
#:
#: **An emitter-anchored pattern cannot see an inline cord at all**, which is
#: why this module's scan matched **ten** and reported the path complete. Twice.
#:
#: ⚠ **And 23 is not a cord count.** Branches write one entry twice — cord 4's
#: source is `96` at `0x4655c` *or* `97` at `0x46568` on a `cmpl #255,%d5`
#: branch, one cord and two sites, with its dest reached through `%a1` while
#: src and amt go through `%a0`. **A grep gives sites; a cord count needs path
#: analysis.** `eosed` nearly reported 21 cords on this basis and stopped.
#:
#: > ## THE RULE THIS KEEPS TEACHING
#: > **A pattern fits everything it is shown, and that fit is what makes it
#: > feel complete.** This module's fit ten cords; `eosed`'s fit seven.
#: > Neither number was wrong as a count of what the pattern matched; both
#: > were wrong as inventories. The question that has broken it every time is
#: > **"what would this pattern be unable to see?"** — which is a different
#: > question from "did it match correctly", and the second one always passes.
EOS_AKAI_CORD_SITES = 23          #: source-field writes, five address registers
EOS_AKAI_EMITTER_CALLS = 12       #: bsrw 0x46370

#: ✅ **All 23 sites extracted here and reconciled against `eosed`'s read.**
#: The nine fixed cords and the `kg[0x1c]` gate turn out to be **written
#: inline too** (`0x46962`…`0x46b7a`, `0x46bc6`) — the emitter's twelve calls
#: are the *other* cords. So "inline vs emitter" is not the modelled/
#: unmodelled boundary, which is what the earlier framing implied.
#:
#: **Modelled: 21.** 9 fixed + 2 gate (inline) + 3 assignable + 7 program-level
#: (emitter). **Unmodelled: 13 inline sites** —
#:
#:     0x464ae src 11  dst 64   amt %a5@(32)     0x464d0 src 160 dst 64
#:     0x464f4 src 16  dst 48   amt %a5@(46)     0x4650c src 22  dst 8
#:     0x4652a src 96  dst 48   amt 127 const    0x4655c src 96  dst 48
#:     0x46568 src 97  dst 48   (branch twin of 0x4655c -- ONE cord)
#:     0x46688 src 18  dst 48   amt %a5@(47)
#:     0x466ae src 17  dst 168+%d5  amt %a5@(56)
#:     0x466da src 18  dst 168+%d5  amt %a5@(57)
#:     0x46706 src 12  dst 168+%d5  amt %a5@(58)
#:     0x46c48 src 10  dst 52
#:
#: ⚠⚠ **THE PARAGRAPH BELOW IS WRONG AND IS LEFT STANDING. Committed
#: ef7e864, refuted 2026-09-24 the same night, by this file's own seven-slot
#: table.** Struck rather than deleted because it was pushed, quoted to
#: `s3ked` and acted on there.
#:
#: It claimed the eleven amounts are program-FILE bytes 32/46/47/48/56/57/58,
#: on the strength of the caller reading `%a3@(24/25/26)` = pan / loudness /
#: vel_loudness. **That anchor is in the CALLER, on the caller's `%a3`.** The
#: step from there to "so the callee's `%a5` displacements are file offsets"
#: was never checked, and the table twenty lines above already refutes it:
#:
#:     %a5@(33) -> raw[92]   %a5@(38) -> raw[89]   %a5@(50) -> raw[94]
#:     %a5@(34) -> raw[93]   %a5@(39) -> raw[90]   %a5@(51) -> raw[95]
#:                           %a5@(40) -> raw[91]
#:
#:     shifts: +59, +59, +51, +51, +51, +44, +44   -- THREE different shifts
#:
#: A copied buffer gives **one** shift. Three means `%a5` points at a parsed,
#: REORDERED form, so an operand displacement is not a file offset and there
#: IS staging after all — exactly what the paragraph said there was not.
#:
#: The corpus says the same thing independently (3 456 programs, 6 discs):
#: raw[84..88] are 8-13 distinct values, 100 % <= 14, dominated by 5/8/10 —
#: enum selectors. raw[89..95] span and carry negatives. Displacements
#: 50/51/53/54, which the wrong reading would map to real program bytes, are
#: **0 on 100 % of 3 456 programs**. Nothing at 33..54 has the shape.
#:
#: **So the eleven cords' SOURCES, DESTINATIONS, gates and arithmetic stand —
#: those are read off the instruction stream — and every claim about WHICH
#: AKAI BYTE feeds them is withdrawn.** `s3ked` was asked to name eight
#: program-block offsets that were not program-block offsets; told, and the
#: question retracted. Modelling still needs the staging map, which is what
#: the note said before this attempted to remove it.
#:
#: ~~✅ **THE "STAGING" WAS NOT STAGING — traced 2026-09-24.** The amounts come
#: straight from the **AKAI program common block**.~~ In `0x4647c`:
#:
#:     0x46488  moveal %a1,%a4      -> the E4 VOICE; cords at voice+188,
#:                                    24 slots x 4, cleared by the memset at
#:                                    0x4649a (pea %a4@(188), 0x60 bytes)
#:     0x4648a  moveal %a0,%a5      -> caller's %a3 = the PROGRAM COMMON BLOCK
#:     0x4648e  moveal %fp@(8),%a3  -> caller's %a4 = the raw AKAI KEYGROUP
#:
#: ~~Identified, not guessed: the caller reads `%a5@(24/25/26)`, which this
#: project decodes as `pan` / `loudness` / `vel_loudness` at `0x18/0x19/0x1a`
#: — three consecutive hits~~ — **and that anchor is in the CALLER, on a
#: different register, and does not transfer.** Three consecutive hits made it
#: feel settled; what it settled was the caller's `%a3`, not the callee's
#: `%a5`. The keygroup half DOES hold: the known cords read `%a3@(27)`,
#: keygroup `0x1b`, the byte measured on the E4XT the same evening, and the
#: keygroup reads are direct.
#:
#: ⚠ **`%a5` names two different objects in this one function.** It is
#: reassigned to the cord slot at `0x46b74` (`lea %a4@(0,%d7:l:4),%a5`), which
#: is why the nine fixed cords appear to write `%a5@(188/189/190)` while these
#: appear to read `%a5@(32)`. The note above quoted the offsets without saying
#: which assignment was live — exactly the failure that
#: `reference_register_is_not_a_variable` exists for, committed in the file
#: that records the rule.
#:
#: What each one emits (`src`, `dst`, amount), all verbatim unless stated.
#:
#: ⚠ **`d[N]` is a DISPLACEMENT off `%a5`, NOT an AKAI file offset.** Written
#: `pgm[N]` here until 2026-09-24, which is the retracted claim above and read
#: as a file offset by two projects. The notation is the fix: a banner a
#: hundred lines up does not survive someone reading the table.
#: The displacement-to-file map is the seven-slot table's, and it is not a
#: constant shift.
#:
#:     d[32]  src 11  dst 64
#:            + src 160 dst 64 at d[32]/5, ONLY when that signed
#:              quotient is non-zero (0x464c8 tstl / beqs)
#:     d[46]  src 16  dst 48
#:     d[47]  src 18  dst 48
#:     d[48]  dst 48, and d[7] selects the source three ways:
#:              d[7] == 0    src 96, amount clamp(d[48]*2, -127, 127)
#:              d[7] == 255  src 96, amount verbatim
#:              otherwise    src 97, amount verbatim
#:     d[56]  src 17 | gated on itself, dst 168 + d5
#:     d[57]  src 18 | gated on itself, dst 168 + d5
#:     d[58]  src 12 | gated on itself, dst 168 + d5
#:     kg[?]  src 10 dst 52, amount rescale(word, -9999, 9999, 127)
#:
#: ℹ `s3ked` read `d[7]` as the program name's fifth character and called the
#: three-way branch a branch on junk. **That reading is void in both
#: directions** (their `9741efd`): displacement 7 is not byte 7, so it was
#: never a claim about the program file and was never refuted. `d[7]` is
#: simply unidentified, like the rest.
#:
#: ⚠ **`dst = 168 + d5` is a CORD-AMOUNT destination, and `d5` is chosen at
#: run time** — `movel %d7,%d5` at `0x4657e` leaves it holding the slot index
#: the `pgm[48]` cord landed in. So those three modulate *another cord's
#: amount*, and a writer has to know which slot that cord took. That is a
#: different kind of dependency from everything else modelled here.
#:
#: ⚠ **`0x46c48`'s guard is not traced.** `lea %a3@(0,%d3:l:2),%a5` then
#: `tstw %a5@(140)` — keygroup base, `%d3`-indexed, word-sized. Where `%d3`
#: was last assigned is NOT established, so the source field is unidentified
#: and this one stays out even when the other ten are named.
#:
#: ℹ **Where the staging object comes from — traced one more hop,
#: 2026-09-24, and stopping there deliberately.** The chain is
#:
#:     0x4647c   %a5 := %a0        <- caller's %a3
#:     0x46da8   %a3 := %a1        <- ITS caller's value
#:     0x475b4   %a1 := %d2        at 0x4763e, immediately before the
#:                                 bsrw 0x46da8 at 0x47650
#:
#: So the object these displacements index is **whatever `%d2` holds at
#: `0x4763e`**, and that is the next thing to establish. It is NOT the
#: verbatim 192-byte program buffer: that one is frame-relative at
#: `%fp@(-196)` and satisfies `fp + 196 == file offset` on all seven known
#: slots, while these displacements satisfy no constant offset at all.
#:
#: ⚠ Stopping at a named register rather than guessing the object is the
#: point. The previous attempt on this chain asserted an identification from
#: a three-hit anchor in the CALLER and had to be retracted from a pushed
#: commit; one more inferential hop is exactly where that happened.
#:
#: **Still unmodelled, and deliberately so**: `s3k/params.py` is the authority
#: for AKAI program-block field names and this project reads none of these
#: offsets (`0x0f 0x11 0x13 0x14 0x15 0x17 0x18 0x19 0x1a 0x21-0x24 0x59` and
#: stop). `docs/AKAI_S3000_FORMAT.md` has no table covering them. Asked
#: `s3ked` 2026-09-24. **A wrong field name is worse than a gap**, and the
#: contract reports these honestly today — inferring a name from what EOS
#: happens to do with the byte is fitting a label to one consumer's use of it.
#:
#: ⚠ **And a reconciliation failure worth keeping.** This module's own
#: extractor reported `dst` for `0x466ae`/`0x466da`/`0x46706` as `17`, `18`,
#: `12` — the same literals as their `src`. It resolved `dst` by scanning
#: backwards for a `moveq` and found the **source's** `moveq` instead of the
#: `addl #168` that actually computes the destination. `eosed`'s read had
#: them right. *A script is a pattern too, and this one fit every row it
#: produced.* The three it got wrong are exactly the three whose destination
#: is computed rather than literal — the case the pattern could not see.
#: ✅ Two of the thirteen resolved 2026-09-22 and are now modelled or
#: understood: `0x46c06` is `kg[0x1c]`'s partner gate cord (implemented), and
#: `0x4652a`'s destination is `48`, written once at `0x4657a` past the branch
#: merge — it and `0x4655c`/`0x46568` are **one** cord with two source paths,
#: which is why a per-block scan saw three.
EOS_AKAI_CORDS_NOT_MODELLED = ('eleven_located_inline_cords',)


def eos_akai_preset_volume(loudness: int) -> int:
    """`header[27]`, signed dB. [C: 363/363 against EOS's own output]

    **Only the AKAI importer sets it** — EOS writes zero here on Ensoniq and
    Roland imports, so a non-zero preset volume on a bank of either of those
    origins did not come from EOS.

    Deliberately a one-line delegation rather than a copy. The first draft of
    this module re-implemented the arithmetic and got it wrong by 1 dB on
    every value not divisible by 10, because Python's `//` floors and the
    firmware's signed divide truncates toward zero. `akai_program_loudness_
    to_e4b_db` already had that right and says so in its own comment; a
    simulation that re-derives a law this project has already measured is
    how the two drift apart.
    """
    return akai_program_loudness_to_e4b_db(loudness)


# ---------------------------------------------------------------------------
# Building a bank the way EOS would have imported it
# ---------------------------------------------------------------------------

def simulate_akai_preset(program_raw: bytes, s3000: bool, name: str,
                         preset_index: int = 0):
    """An E4B `Preset` as **EOS's own AKAI importer** would have produced it.

    The voices are **neutral** — zones, sample references, key and velocity
    windows, and nothing else. Every parameter EOS converts is attached as a
    raw byte override (`voice.firmware_raw`, `preset.firmware_raw`) which
    `writers/e4b_writer.py` applies last.

    **That split is the whole design.** A field EOS does not write must reach
    the file as the writer's neutral value, not as this project's own law for
    it — otherwise the output is a hybrid, and diffing it against a real
    device import measures nothing. The source PARSE is ours (the firmware
    traces give the conversion law, never the source parser); every
    conversion is the firmware's.

    ⚠ **The result is deliberately worse than `parse_akai_program`.** It is a
    measuring instrument, not a converter.
    """
    from models.common import Preset, VoiceLayer, ZoneMapping
    from parsers.akai_s3000_parser import _block_len, _zone_of, _ZONE_OFFSETS

    blen = _block_len(s3000)
    n_kg = max(0, (len(program_raw) // blen) - 1)
    modsfilt = tuple(program_raw[o] if o < len(program_raw) else 0
                     for o in (84, 85, 86))

    # Program-level cords run FIRST and take the leading slots; the keygroup
    # cursor continues from where they stop (0x4647c's %d7, by reference).
    prog_cords = eos_akai_program_cords(program_raw)

    preset = Preset(name=name)
    for k in range(n_kg):
        kg = program_raw[blen * (k + 1): blen * (k + 2)]
        if len(kg) < 0x10:
            continue
        zones = [z for z in (_zone_of(kg, b) for b in _ZONE_OFFSETS) if z]
        if not zones:
            continue
        v = VoiceLayer()
        for z in zones:
            v.zones.append(ZoneMapping(
                sample_name=z['sample_name'],
                lo_key=kg[0x03], hi_key=kg[0x04],
                lo_vel=z['lo_vel'], hi_vel=z['hi_vel'],
            ))
        cords = [(s, d, a) for s, d, a in prog_cords]
        for _slot, s_, d_, a_ in eos_akai_cords(kg, modsfilt=modsfilt,
                                                first_slot=len(cords)):
            cords.append((s_, d_, a_))
        v.firmware_raw = {
            'pzt': eos_akai_amp_envelope(kg),
            'cords': cords,
            'vpar': {},
        }
        preset.voices.append(v)

    loudness = program_raw[0x19] if len(program_raw) > 0x19 else 99
    preset.firmware_raw = {'hdr': {27: eos_akai_preset_volume(loudness) & 0xFF}}
    return preset


#: ⚠ **What `simulate_akai_preset` does NOT reproduce**, so a diff expects it:
#:
#: * the **11 located-but-unmodelled cords** (`EOS_AKAI_CORDS_NOT_MODELLED`);
#: * **zone de-duplication** [S, not [C] — see below] — EOS is believed to
#:   merge identical velocity zones pairwise,
#:   so voice *i* is not keygroup *i* on a source that has duplicates;
#: * `header[26]` transpose, read from the code as a clamped copy but written
#:   zero on all 363 presets of the reference disc, so nothing exercises it.
#: ⚠ `zone_dedup` is **[?] — a loop is located, and it does NOT predict the
#: device's output.** See §AKAIZONEMERGE. Labelled [C] for about an hour on
#: 2026-09-24 and retracted the same day: tested against EOS's own import
#: (`B030-AKAIIMPORT-full.E4B`, 333 paired presets, 193 voices with 2+
#: enabled zones) the predicate scores **42%** against **56%** for assuming
#: no merge at all, inventing 69 merges that did not happen while catching 48
#: of the 85 that did. Locating a mechanism is not confirming it governs the
#: behaviour, and the refuting data had been on this disk for four days.
#:
#: ℹ **Narrowed the same evening with `eosed`'s ROM reading.** The name
#: lookup at `0x2faf0` SELECTS the partner zone — it classifies
#: `name[10:12]` as `-L`/`-R`/neither and compares 10 characters for the
#: first two, 12 otherwise — and `0x2f8a0` is the safety check on the pair,
#: not the criterion. Scored against the device import, 193 voices:
#:
#:     no-merge                     56.0 %      stereo -L/-R   56.0 %
#:     tune+filter alone            42.0 %      NAME equal     67.9 %
#:     NAME + tune+filter           72.0 %   <- best, and matches the
#:                                              firmware's structure
#:
#: The `-L`/`-R` branch never fires on this corpus, so it reduces to the
#: class-2 branch: compare 12 characters = full name equality. All 37 voices
#: where the device merged and tune+filter said no carry two zones with the
#: SAME sample name.
#:
#: ⚠ Still not a law: 54 of 193 wrong. The two gates at `0x475f4`/`0x47606`
#: and `0x4762a`, which branch on the name class before the comparison is
#: reached, are the next thing to read. The loop is at `0x4765c`
#: (inner scan) with the skip at `0x47614` and the consume-mark at `0x4768e`;
#: the predicate is `0x2f8a0`, which compares **exactly two fields**:
#:
#:     zone[0x0e:0x10]  signed tune word -> (hi<<6 + lo/4) / 64, i.e. the
#:                      SEMITONE part; the fine byte cannot reach the result
#:     zone[0x11]       filter frequency offset, exact
#:
#: ✅ **Proven, not assumed.** The record sits at `kg + 0x22 + index*24` --
#: the documented raw velocity-zone offsets -- and the two fields are the
#: documented tune and filter-frequency offsets. An earlier version of this
#: note called the base `+22` and hedged the field identification: objdump
#: prints a BRIEF-extension displacement in **hex** and a `(d16,An)` one in
#: **decimal**, so `%a3@(22,%d0:l)` is `0x22 = 34`, not 22. Verified by
#: assembling known displacements and disassembling them.
#:
#: **It never reads the velocity range at [12]/[13].** So "merges identical
#: VELOCITY zones" names the one field the comparison ignores. Two zones over
#: different velocity spans playing different samples are merged when their
#: coarse tune and filter offset agree — which is how an ordinary
#: velocity-split keygroup is built.
#:
#: Prevalence, enabled zones only: **62% of the 9 851 multi-zone keygroups**
#: in 8 discs contain a merging pair; of 17 404 such pairs, 63% play a
#: different sample and 53% span a different velocity range.
#:
#: Still not implemented, and the prevalence is the reason to be deliberate
#: rather than quick: it fires on most multi-zone keygroups, so switching it
#: on changes a great deal of output at once.
EOS_AKAI_SIM_KNOWN_GAPS = ('located_not_modelled_cords', 'zone_dedup',
                           'header26_transpose')


# ---------------------------------------------------------------------------
# EOS's foreign-import voice template — Roland and Ensoniq
# ---------------------------------------------------------------------------
#
# ✅ **MEASURED FROM THE DEVICE'S OWN OUTPUT, not from the disassembly.**
# Two banks the E4XT itself produced — one from an Ensoniq EPS source, one
# from a Roland S-7xx source — give **61 voices**, and across all of them only
# **eight bytes vary**:
#
#     [ 3] [ 4]   structure: trailer offset low byte, zone count
#     [14] [17]   voice key window, low / high
#     [18]        voice velocity LOW   (velocity high is constant 127)
#     [35]        Coarse Tune
#     [54]        Volume
#     [55]        Pan
#
# **Everything else is one fixed template, identical for both source
# formats.** So EOS's foreign import converts key range, velocity floor,
# tuning, volume and pan — and writes a constant into every other field,
# including the whole filter, envelope, LFO and cord blocks.
#
# ⚠ **This is the complement of a write list, and it is the stronger half.** A
# write list says what the firmware sets; this says what it sets *everything
# else* to — which is the part a simulation cannot guess, and the part that
# makes a byte-diff against a device import mean anything.
#
# It also corroborates this document's confirmed laws for both paths from a
# third direction: volume through `TABLE_0x796a4`, pan, and tuning are the
# *only* per-voice quantities either import produces, which is what the
# hardware measurements said one field at a time.
#
# **Provenance:** `~/temp/EPSTEST.e4b` (41 voices) and `~/temp/ROLTEST.e4b`
# (20 voices), both written by the E4XT. Voices located by walking each
# preset's voice chain on the stride in `vpar[2:4]` — *not* by recomputing it
# from the zone count, which drifts after the first voice and produced an
# all-zero template twice before this one.

EOS_FOREIGN_VOICE_TEMPLATE = bytes((
    0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00, 0x00,   #   0
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7f, 0x00, 0x00,   #  12
    0x00, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   #  24
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   #  36
    0x00, 0x00, 0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   #  48
    0xff, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   #  60
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   #  72
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   #  84
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   #  96
    0x00, 0x00, 0x00, 0x7f, 0x00, 0x7f, 0x60, 0x7d, 0x26, 0x7a, 0x37, 0x55,   # 108
    0x2a, 0x00, 0x03, 0x00, 0x00, 0x7f, 0x00, 0x7f, 0x00, 0x7f, 0x00, 0x7f,   # 120
    0x00, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x7f, 0x00, 0x7e,   # 132
    0x00, 0x7f, 0x14, 0x00, 0x00, 0x00, 0x03, 0x00, 0x40, 0x00, 0x00, 0x00,   # 144
    0x00, 0x00, 0x01, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 156
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 168
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 180
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 192
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 204
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 216
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 228
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 240
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 252
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 264
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   # 276
))

EOS_FOREIGN_VOICE_VARIES = (3, 4, 14, 17, 18, 35, 54, 55)
# derived from 41 EPS + 20 Roland device voices


def simulate_eos_foreign_preset(preset):
    """Rebuild a Roland- or Ensoniq-sourced `Preset` as **EOS would import it**.

    The device writes one fixed 284-byte voice and varies only eight bytes:
    the structure (`2,3,4`), the key window (`14,17`), the velocity floor
    (`18`), coarse tune (`35`), volume (`54`) and pan (`55`). This lays down
    the measured template and lets `_build_voice` keep its own values at
    those eight, because it computes every one of them from the zones already
    — *including the voice-level-versus-zone-level rule, which this project
    implements independently and which the device turns out to share.*

    ⚠ **An earlier version set volume and pan here and was wrong on 53 of 66
    voices**: it wrote them at voice level unconditionally, where both EOS and
    this writer leave them zero on a multi-zone voice and carry the value in
    each zone entry instead. *The simulation needed less code, not more — the
    convention was already correct on both sides and only the override was
    new.*

    The source values come from this project's own readers, which is
    legitimate and is why these paths have one mode: `roland_s7xx_parser` and
    `eps_parser` were built from these very import routines and already apply
    EOS's volume table, pan law and tuning.
    """
    from models.common import Preset, VoiceLayer

    out = Preset(name=preset.name, program_number=preset.program_number)
    for v in preset.voices:
        if not v.zones:
            continue
        nv = VoiceLayer()
        nv.zones = list(v.zones)
        nv.firmware_raw = {'voice_fixed': EOS_FOREIGN_VOICE_TEMPLATE,
                           'voice_keep': EOS_FOREIGN_VOICE_VARIES}
        out.voices.append(nv)
    return out


#: ⚠ **VELOCITY HIGH IS NOT WRITTEN, AND THAT IS MEASURED, NOT AN OVERSIGHT.**
#: `[21]` is constant 127 across all 61 device voices while `[18]` varies, so
#: EOS carries a velocity FLOOR and leaves the ceiling open. A simulation that
#: wrote both would look more careful and be wrong on every voice whose source
#: has a velocity ceiling.
EOS_FOREIGN_WRITES = ('key_window', 'velocity_low', 'coarse_tune',
                      'volume', 'pan')
