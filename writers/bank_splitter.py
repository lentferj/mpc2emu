# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
#
# This file is part of mpc2emu.
# Original work. No third-party source code used.
#
# mpc2emu is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# mpc2emu is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Bank Splitter
-------------
Nimmt eine Liste von Bank-Objekten (je eine pro XPM) und packt sie
in möglichst große Ausgabe-Banken, ohne das angegebene Größenlimit zu überschreiten.

Strategie: First-Fit Decreasing (FFD)
  1. Schätze die Größe jeder Quell-Bank (Samples + Overhead)
  2. Sortiere nach Größe (größte zuerst), damit große Blöcke früh platziert werden
  3. Weise jede Bank der ersten Ziel-Bank zu, in die sie noch passt
  4. Falls eine einzelne Bank größer als das Limit ist → Warnung + eigene Ziel-Bank

Wichtig: Samples werden NICHT aufgeteilt. Ein Preset bleibt immer komplett
in einer Ziel-Bank (zusammen mit seinen Samples). Das ist die einzig sinnvolle
Strategie für den E4XT, da ein Preset alle seine Samples in derselben Bank braucht.
"""

import math
from dataclasses import dataclass, field, replace
from typing import List, Tuple
from models.common import Bank, Preset, SampleData


# IFF/E4B structural overhead per bank (header + TOC) in bytes
# Conservative estimate: 512 bytes is more than enough
_BANK_OVERHEAD = 512

# IFF chunk overhead per sample (8-byte chunk header + 64-byte E4Sa header)
_SAMPLE_CHUNK_OVERHEAD = 72

# IFF chunk overhead per preset (8 + 24 preset header + ~50 per voice estimate)
_PRESET_CHUNK_OVERHEAD = 128

# Per the EOS manual, a bank can hold samples S000-S999 — max 1000 samples.
# (An earlier theory that the zone-table sample reference was a single byte,
# capping banks at 255 samples, was wrong — that field is actually a
# big-endian u16 at zone-entry[10:12]; see _zone_entry() in e4b_writer.py.)
_MAX_SAMPLES_PER_BANK = 1000

# Same limit applies to presets: EOS numbers them P000-P999 (max 1000/bank).
_MAX_PRESETS_PER_BANK = 1000

# ── KRZ: PRAM is the real limit, and it is per-machine ────────────────────────
# A K2000 keeps its OBJECTS (programs, keymaps, sample headers) in PRAM,
# separately from sample RAM. Object COUNT is not what binds -- PRAM BYTES are,
# and how many there are depends on the machine:
#
#   original K2000   128K fitted, ~116K usable
#   expanded         760K is common but NOT standard
#
# The default budget is 110K rather than the full 116K: PRAM also holds
# setups, effects and whatever the user already has loaded, and a bank that
# fills it exactly leaves no room for any of that. 110K is safe, and --pram
# overrides it in either direction.
#
# Most commercial banks were authored to fit the original, which is why real
# ones are small: our K2KFEATDEMO banks run 8-38K.
#
# Per-object cost, measured 2026-08-10 against a K2000R's own object list
# (the machine displays exactly these sizes):
_PRAM_SAMPLE  = 84     # sample header; the PCM itself lives in sample RAM
_PRAM_PROGRAM = 272
_PRAM_KEYMAP  = 688    # 128 entries x 5 bytes + header -- the dominant cost
#
# We emit one keymap PER VOICE, so a preset costs 272 + voices*688. A plain
# one-voice preset is 960 bytes, which is why the preset axis runs out long
# before the sample axis: 800 samples are only 66K, but 600 presets are 562K.
#
# This model explains the hang that started all of this: 796 presets x 960 B =
# 746K against that machine's 760K, i.e. 98% full. It was never an object-count
# limit. On a stock machine the same arithmetic allows ~117 presets at the 110K
# default, ~123 if the full 116K is claimed with --pram 116.
_DEFAULT_PRAM_K = 110


def pram_budget_bytes(pram_k=None) -> int:
    """Usable PRAM in bytes. `pram_k` is the machine's USABLE PRAM in KB."""
    return int(pram_k if pram_k else _DEFAULT_PRAM_K) * 1024


def preset_pram_bytes(preset: Preset) -> int:
    """PRAM an assembled preset occupies: its program plus one keymap per voice.

    **Correct only for banks THIS project writes**, and for two reasons worth
    keeping separate:

    1. The per-object sizes are OURS. `krz_writer` emits a fixed 128-entry
       keymap, so 688 bytes every time. Real banks vary: VinSamLib matched
       per-object PRAM to each object's OWN BLOCK SIZE against a photographed
       K2000R object list and saw keymaps from 178 to 1976 bytes.

       **That range is a disproof, not a table.** It is eight objects, one
       bank, one machine, and VinSamLib were explicit that it is enough to
       show a flat constant cannot be right for re-assembled banks and NOT
       enough to compute from. Do not build a size table out of it; read the
       object's own block size if you ever need real sizes.

       Point this function at a parsed third-party bank and it misestimates in
       both directions. Every caller here passes a bank we are about to write,
       which is why that is not a bug today.

    2. It assumes one keymap PER VOICE, which
       `krz_writer.SHARE_IDENTICAL_KEYMAPS` makes false when enabled. With
       sharing on, 300 presets over one keymap cost 80 K rather than the 281 K
       this returns -- so the splitter would emit roughly three times as many
       banks as needed. The flag is OFF by default, so this is latent rather
       than live, but the two must be changed together.
    """
    return _PRAM_PROGRAM + max(1, len(preset.voices)) * _PRAM_KEYMAP


def bank_pram_bytes(n_samples: int, presets) -> int:
    """PRAM an assembled KRZ bank occupies."""
    return (n_samples * _PRAM_SAMPLE
            + sum(preset_pram_bytes(p) for p in presets))


#: Per-format bank capacity: (max samples, max presets, max samples+presets).
#: The third is for formats where the two share one budget; None where they do
#: not.  An unlisted format gets the EOS numbers, which is what every caller
#: assumed before this table existed.
_FMT_CAPACITY = {
    'e4b':  (_MAX_SAMPLES_PER_BANK, _MAX_PRESETS_PER_BANK, None),
    'eiii': (_MAX_SAMPLES_PER_BANK, _MAX_PRESETS_PER_BANK, None),
    # KRZ is tighter than EOS, and for two separate reasons. Object ids start
    # at 200, and:
    #   * id > 999  -- HW-CONFIRMED 2026-08-10: the K2000 CLAMPS, putting
    #                  every further object on 999 so each overwrites the
    #                  last. Silent; it does not refuse.
    #   * id > 1023 -- the id carries into the type field of the hash
    #                  (`type << 10 | id`, krz_writer._hash) and the object
    #                  reads back as a different type entirely.
    # The lower one binds: 200..999 = 800 objects PER TYPE. write_krz refuses
    # a bank past it; splitting here means the user gets more banks instead of
    # an error. Samples and programs have separate id spaces, so no combined
    # cap.
    'krz':  (800, 800, None),
    # An AKAI bank is one volume, and a volume directory's 510 entries hold
    # the samples AND the programs — so unlike the others, the two compete for
    # one budget and the combined cap is the one that bites.
    'akai': (509, 509, 510),
    #
    # THE OTHER AKAI CEILING IS RAM, AND WE CLEAR IT BY ACCIDENT.
    # convert.py caps AKAI output at 32 MB, the largest S3000XL, and we count
    # FILE bytes -- which include a 150-byte header per sample and the program
    # files, and programs cost no sample RAM at all. So our volumes under-fill.
    #
    # The exact cost (s3ked, 2026-08-12, from the loaded volume's directory):
    #     audio_words = (size_bytes - 150) / 2,  summed over type 0x73 only
    # verified by predicting a machine's loaded memory from directory records
    # alone -- 16,424,982 words against 16,424,982 reported. Memory is counted
    # in 16-bit words: a 32 MB machine reports 16,777,216 of them.
    #
    # Worth knowing what we are protecting against, because the failure is
    # quiet. A volume needing 58.69 MB on a 32 MB machine loaded 10 programs
    # and 60 of 88 samples, said "insufficient waveform memory!" ONCE, and then
    # behaved normally -- every keygroup pointing at one of the 28 missing
    # samples plays SILENCE. A half-loaded bank is not obviously broken from
    # the front panel.
    #
    # Not taken: modelling RAM exactly would let a 32 MB volume carry 150 bytes
    # more audio per sample plus the whole program budget. That is an
    # optimisation of a limit we currently clear, and being conservative about
    # a ceiling whose overrun is silent is the right side to err on.
}


def bank_limit_bytes(max_size_mb: float) -> int:
    """Usable bytes in a bank of `max_size_mb`, after the safety margin.

    The per-sample/per-preset/per-bank overhead constants below slightly
    *under*-count the real serialized size (E4Sa headers, word alignment, the
    mandatory trailing EMSt chunk and FORM framing), so packing right up to
    the byte limit can spill a few KB over — and an E4B even one byte past the
    E4XT's sample RAM will not load.

    The margin used to be a flat 1 MB, which is sized for a 128 MB bank and
    fatal for a small one: `--bank-size 1` left **one byte** usable, so nothing
    could fit and the fit assistant looped applying reductions that could not
    help. It is now proportional with a floor. Every default is unaffected —
    12.5% of 8 MB is already 1 MB, and the smallest hardware limit in use is
    32 MB.

    **This is the only place the margin is computed.** `convert.py` used to
    carry its own copy of the flat 1 MB, so the splitter and the fit assistant
    disagreed about what fits.
    """
    margin = min(1024 * 1024, max(64 * 1024, int(max_size_mb * 1024 * 1024 * 0.125)))
    return max(1, int(max_size_mb * 1024 * 1024) - margin)


#: AKAI resident-object pool: programs + keygroups + samples, one budget.
#:
#: MEASURED by s3ked on a 32 MB S3000XL, 2026-08-14, after Jan noticed the row
#: on the LOAD page. It is `STAT.max_blocks`, and `free P/K/S` on the panel is
#: `STAT.free_blocks`:
#:
#:     max_blocks 1006, free 884  ->  used 122
#:     2 programs + 58 keygroups + 62 samples = 122     exact, not approximate
#:
#: Confirmed at a second setting: loading one sample moved free_blocks by one
#: and the object sum by one. So a keygroup costs exactly what a program and a
#: sample cost, and it is one shared pool rather than three figures on a row.
#:
#: PROVENANCE OF THE THREE TERMS, checked rather than assumed. Later the same
#: day s3ked found their directory walk had been returning one entry too many
#: on 98 of 100 volumes -- a phantom final record -- and reported that every
#: item count they had quoted was one high. That would have put a constant
#: error into this fit check on every volume, so they traced the identity's
#: call paths: programs from RPLIST, samples from RSLIST, keygroups from the
#: GROUPS field of each program header. None of the three comes from a
#: directory walk, and the phantom never entered the arithmetic.
#:
#: The exactness was doing the checking before anyone noticed. 122, 200 and 229
#: closed to the unit at three separate states; had any term inherited an
#: off-by-one, none of them could have. A sum that lands exactly is evidence
#: about its inputs, and it is worth reaching for that argument before
#: re-deriving a number from scratch.
#:
#: THIS IS NOT A PROPERTY OF THE VOLUME. It is a ceiling on what is RESIDENT in
#: the machine, so two things follow that the directory cap does not share:
#:
#:   * A volume can satisfy the 510-entry directory limit and still exceed the
#:     pool -- the budgets are independent. **MEASURED 2026-08-16 on Jan's
#:     S3000XL: exceeding the pool causes a PARTIAL LOAD, not a refusal.**
#:
#:     A volume needing 967 objects loaded whole and left `free P/K/S` at 39,
#:     matching this model to the unit. Loading a further volume needing 88
#:     took `free P/K/S` to 0 -- it consumed the remaining 39 and stopped. A
#:     refusal would have left 39 untouched.
#:
#:     So the honest wording is "will load INCOMPLETELY", never "will not
#:     load", and the failure is the quiet kind: programs stay resident and
#:     selectable with keygroups or samples missing underneath them, exactly
#:     as the RAM ceiling behaves. Two independent budgets, the same silent
#:     degradation. Ours overshoot badly: a
#:     six-program test volume uses 21 directory entries and 216 objects, about
#:     32 keygroups per program, so filling the directory would ask for ~5200.
#:   * The pool is shared across everything already loaded, exactly like the
#:     RAM budget. A volume that loads onto an empty machine may not load onto
#:     one already holding a bank, and we cannot see that from here.
#:
#: So this check is a FLOOR, not a guarantee: it catches a volume that cannot
#: load onto an empty machine. It cannot promise one will load onto a full one.
#:
#: THE POOL SIZE IS ALSO CONFIRMED DIRECTLY: a volume this model counts at 967
#: objects left the machine reporting `free P/K/S: 39`, and 967 + 39 = 1006.
#: The count here IS what the sampler counts.
#:
#: CORROBORATED BY AUTHORED DATA, which is a different kind of evidence from
#: the machine reading. Across 1843 volumes on 21 commercial library discs:
#:
#:     volumes over 1006 objects : 0
#:     largest volume            : 910  (23 programs, 811 keygroups, 76 samples)
#:     median / p90 / p99        : 45 / 134 / 404
#:
#: Real volumes crowd up to the ceiling and never cross it, which is what a
#: correct ceiling looks like. VinSamLib measured the same corpus with their
#: own reader and got 910 too.
#:
#: That largest volume is also the whole argument for this check in one line.
#: It uses **99 of 510 directory entries** -- 19 %, nowhere near the limit we
#: used to enforce -- and **910 of 1006 objects**, 90 %. Its keygroups are 89 %
#: of its object count and appear in no directory at all. A tool counting files
#: sees a volume at a fifth of capacity; the sampler sees one nearly full.
#:
#: 1006 is what one 32 MB machine reports and s3ked explicitly warned against
#: assuming it is universal -- whether it moves with fitted memory is untested,
#: and the right number is whatever the target's own STAT says. We cannot ask a
#: file for that, so it is a default and `--akai-max-objects` overrides it.
_AKAI_OBJECT_POOL = 1006

#: Two off-by-ones s3ked flagged as untested, both of which would LOOSEN this
#: cap slightly if they went the other way: whether a program with zero
#: keygroups costs 1 or 0, and whether a stereo sample costs one object or two.
#: Neither can bite us as we write: keygroups are clamped to a minimum of 1, and
#: AKAI stereo is written as two mono files, which are two directory entries and
#: are counted here as two.


def akai_object_count(presets, n_samples: int, ib304f: bool = False) -> int:
    """programs + keygroups + samples, the way the S3000XL counts them.

    `ib304f` because the keygroup count is BOARD-DEPENDENT: with the second
    filter available, two layers that differ only in filter 2 need separate
    keygroups where the board-off path correctly merges them. Defaulting to
    False keeps every existing caller's behaviour, and **under-counts when the
    board is on** -- see TODO "AKAI object budget does not know the IB-304F can
    force a split". The split that matters is rare (same corner, same
    resonance, different filter SHAPE in one key range), so this is a budget
    edge rather than a live defect; it is plumbed so a caller that knows the
    flag can pass it.
    """
    from writers.akai_s3000_writer import keygroup_count
    return (len(presets)
            + sum(keygroup_count(p, ib304f) for p in presets)
            + n_samples)


def _capacity(fmt: str):
    return _FMT_CAPACITY.get(fmt, (_MAX_SAMPLES_PER_BANK,
                                   _MAX_PRESETS_PER_BANK, None))

# ── Polyphony (measured on the E4XT 2026-07-31) ────────────────────────────────
# Two facts that nothing in the size/fit path used to know:
#
#   1. A STEREO sample costs TWO voices.  Detuned voice ladders plateau at 32
#      mono but only 16 stereo, and the two ladders settle at *different*
#      levels (~250-300 vs ~420-490), which rules out a shared level ceiling
#      masquerading as a voice ceiling.  See docs/RESOLUTION_NOTES.md
#      §E4BSTEREO item 4 — the first two attempts at this measurement both
#      produced confident wrong answers.
#   2. The ceiling is ~32 mono voices ON ONE NOTE, not the E4XT's 128-voice
#      global polyphony (32 voices on each of four separate keys all sound).
#
# Only the E4XT numbers are measured.  The K2000 (krz) and EIII paths have
# their own, smaller voice budgets, but no per-note limit has been measured on
# either — and both are still mono-only, so the stereo cost cannot bite there.
# Leave them out rather than warn on a guess.
#: Voices the hardware will sound on a single note.  `sample_voice_cost()`
#: charges a stereo sample two, which is measured on both machines.
#:   e4b — 32 per note (E4XT, global polyphony 128), HW-confirmed 2026-07-31
#:   krz — 24, the K2000's entire polyphony, HW-confirmed 2026-08-02: a stereo
#:         sample plateaus at 12 simultaneous notes where the same material in
#:         mono reaches 24, measured identically at velocity 100, 45 and 25 so
#:         the plateau is voice allocation rather than output clipping
#:   akai — 32, the S3000XL's entire polyphony. NOT a bench measurement like
#:         the two above: Jan states (2026-08-17) that polyphony is settable
#:         per program within a multi and that 32 is the maximum there, which
#:         matches the machine's 32-voice architecture. Same reasoning that
#:         gives krz its 24 (that machine's whole voice budget), so the number
#:         is an architectural ceiling rather than a measured steal point. It
#:         is an upper bound either way — a program allocated fewer voices in a
#:         multi steals SOONER, so this warns late, never early.
_VOICES_PER_NOTE = {'e4b': 32, 'krz': 24, 'akai': 32}


def estimate_bank_size(bank: Bank) -> int:
    """
    Estimate the serialized size of a Bank in bytes.
    Intentionally slightly overestimates to stay safely under the limit.
    """
    size = _BANK_OVERHEAD

    for sample in bank.samples:
        size += _SAMPLE_CHUNK_OVERHEAD + len(sample.data)

    for preset in bank.presets:
        voice_overhead = sum(
            8 + len(v.zones) * 32  # voice header + zone blocks
            for v in preset.voices
        )
        size += _PRESET_CHUNK_OVERHEAD + voice_overhead

    return size


def estimate_preset_size(preset: Preset, samples: List[SampleData]) -> int:
    """
    Estimate the size contribution of a single preset + its unique samples.
    Used to check if a preset fits into a target bank.
    """
    size = _PRESET_CHUNK_OVERHEAD
    for voice in preset.voices:
        size += 8 + len(voice.zones) * 32

    # Add samples that belong to this preset
    needed_sample_names = {
        zone.sample_name
        for voice in preset.voices
        for zone in voice.zones
    }
    for sample in samples:
        if sample.name in needed_sample_names:
            size += _SAMPLE_CHUNK_OVERHEAD + len(sample.data)

    return size


def preset_needed_samples(preset: Preset,
                          samples: List[SampleData]) -> List[SampleData]:
    """The subset of `samples` actually referenced by `preset`'s zones."""
    names = {z.sample_name for v in preset.voices for z in v.zones}
    return [s for s in samples if s.name in names]


def velocity_layer_count(preset: Preset) -> int:
    """
    Number of distinct velocity layers, whichever way the model represents them:
    separate VoiceLayer objects (SFZ/SF2/GIG), or velocity bands packed as zones
    inside a single voice (XPM keygroups).
    """
    if len(preset.voices) > 1:
        return len(preset.voices)
    if preset.voices:
        return len({(z.lo_vel, z.hi_vel) for z in preset.voices[0].zones})
    return 0


def sample_voice_cost(sample: SampleData) -> int:
    """Voices consumed by one sounding zone: 2 for a stereo sample, 1 for mono."""
    return 2 if getattr(sample, 'channels', 1) >= 2 else 1


def peak_note_voices(preset: Preset,
                     samples: List[SampleData]) -> Tuple[int, int, int]:
    """
    Highest voice count this preset can put on a SINGLE key at a single
    velocity, counting a stereo zone as two voices.

    Returns `(voices, key, velocity)` — the peak and one key/velocity that
    reaches it.  `(0, 0, 0)` for a preset with no playable zones.

    An E4B *voice* sounds only one matching zone per note (that is why SFZ
    overlapping regions had to be split into parallel voices, not stacked as
    zones), so a voice layer contributes the cost of its matching zone, not the
    sum over all of them.  Where several zones inside one layer overlap, the
    dearer one is assumed — a stereo zone is the conservative reading.
    """
    cost = {s.name: sample_voice_cost(s) for s in samples}
    # The peak of a step function built from closed intervals is always reached
    # at some interval's lower edge, so only the distinct lo_vel values need
    # testing (plus 0, for a preset whose zones all start above it).
    vel_edges = sorted({z.lo_vel for v in preset.voices for z in v.zones} | {0})

    best = (0, 0, 0)
    for vel in vel_edges:
        per_key = [0] * 128
        for voice in preset.voices:
            layer = [0] * 128
            for z in voice.zones:
                if not (z.lo_vel <= vel <= z.hi_vel):
                    continue
                c = cost.get(z.sample_name, 1)
                for k in range(max(0, z.lo_key), min(127, z.hi_key) + 1):
                    if c > layer[k]:
                        layer[k] = c
            for k in range(128):
                per_key[k] += layer[k]
        for k in range(128):
            if per_key[k] > best[0]:
                best = (per_key[k], k, vel)
    return best


def _note_name(midi: int) -> str:
    names = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
    return f"{names[midi % 12]}{midi // 12 - 1}"


def polyphony_warnings(source_banks: List[Bank], fmt: str) -> List[str]:
    """
    Warn about presets that stack more voices on one note than the hardware
    will sound.  Over the limit the extra voices are not merely quiet — they
    are stolen, so which layers survive is arbitrary.

    Returns a list of ready-to-print warning strings (empty when the format has
    no measured per-note limit, or nothing is over it).
    """
    limit = _VOICES_PER_NOTE.get(fmt)
    if not limit:
        return []

    out: List[str] = []
    for bank in source_banks:
        for preset in bank.presets:
            needed = preset_needed_samples(preset, bank.samples)
            voices, key, vel = peak_note_voices(preset, needed)
            if voices <= limit:
                continue
            stereo = sum(1 for s in needed if sample_voice_cost(s) > 1)
            why = (f" ({stereo} of {len(needed)} samples are stereo, and a "
                   f"stereo sample costs two voices)") if stereo else ""
            out.append(
                f"  [WARN] Preset '{preset.name}' from '{bank.name}' stacks "
                f"{voices} voices on {_note_name(key)} at velocity {vel}, over "
                f"the {limit}-voice-per-note limit{why} — the extra layers will "
                f"be stolen on playback. To fix: --reduce-velocity-layers, or "
                f"--mono to halve the cost of every stereo zone."
            )
    return out


def _resample_est_bytes(preset: Preset, needed: List[SampleData],
                        target_hz: int) -> int:
    """Estimate a preset's size if every sample above target_hz were downsampled
    to target_hz (PCM byte count scales linearly with the rate)."""
    size = _PRESET_CHUNK_OVERHEAD
    for v in preset.voices:
        size += 8 + len(v.zones) * 32
    for s in needed:
        scale = target_hz / s.sample_rate if s.sample_rate > target_hz else 1.0
        size += _SAMPLE_CHUNK_OVERHEAD + int(len(s.data) * scale)
    return size


def fit_options(preset: Preset, needed: List[SampleData], limit_bytes: int,
                rate_floor: int = 22050) -> Tuple[int, List[dict]]:
    """
    For a single preset that does not fit `limit_bytes`, compute concrete,
    already-sized ways to shrink it (a preset can never be split across banks,
    so it must be thinned or downsampled to fit).

    Returns `(current_bytes, options)`.  `options` is empty when the preset
    already fits.  Each option is a dict:
      kind      'velocity' | 'key' | 'resample'
      flag      the exact convert.py flag string a user would pass
      arg       (attr_name, value) for the caller to apply programmatically
      est_bytes estimated resulting preset size
      fits      whether est_bytes is within limit_bytes on its own
      label     one-line description of what is lost
    Options are ordered least-lossy-first for a musical multisample: velocity
    layers (keeps full key + rate), then key zones, then resample.
    """
    cur = estimate_preset_size(preset, needed)
    if cur <= limit_bytes:
        return cur, []
    ratio = limit_bytes / cur          # target fraction of current size
    opts: List[dict] = []

    v = velocity_layer_count(preset)
    if v > 1:
        keep = max(1, math.floor(v * ratio))
        if keep < v:
            pct = int(round((1 - keep / v) * 100))
            est = int(cur * keep / v)
            opts.append({
                'kind': 'velocity', 'flag': f'--reduce-velocity-layers {pct}',
                'arg': ('reduce_velocity_layers', float(pct)),
                'est_bytes': est, 'fits': est <= limit_bytes,
                'label': f'keep {keep} of {v} velocity layer(s); '
                         f'all key zones stay at full sample rate',
            })

    kpct = min(95, max(1, int(round((1 - ratio) * 100))))
    est = int(cur * (100 - kpct) / 100)
    opts.append({
        'kind': 'key', 'flag': f'--reduce-key-zones {kpct}',
        'arg': ('reduce_key_zones', float(kpct)),
        'est_bytes': est, 'fits': est <= limit_bytes,
        'label': f'keep ~{100 - kpct}% of key zones per layer '
                 f'(survivors stretch to fill the gaps)',
    })

    top = max((s.sample_rate for s in needed), default=0)
    if top > rate_floor:
        target = max(rate_floor, int(top * ratio))
        est = _resample_est_bytes(preset, needed, target)
        opts.append({
            'kind': 'resample', 'flag': f'--max-sample-rate {target}',
            'arg': ('max_sample_rate', target),
            'est_bytes': est, 'fits': est <= limit_bytes,
            'label': f'downsample every sample to {target} Hz '
                     f'(all zones kept; loses treble / up-pitch headroom)',
        })

    return cur, opts


@dataclass
class TargetBank:
    """One output E4B bank being assembled."""
    index: int                              # 1-based bank number
    presets: List[Preset]  = field(default_factory=list)
    samples: List[SampleData] = field(default_factory=list)
    _sample_names: set = field(default_factory=set, repr=False)
    # CR-7: name → content key, to tell a true duplicate from a same-name /
    # different-PCM collision (e.g. same-named samples from two source banks).
    _sample_keys: dict = field(default_factory=dict, repr=False)
    current_size: int = _BANK_OVERHEAD
    #: 0 = no PRAM limit (every format but KRZ).
    pram_budget: int = 0
    #: 0 = no resident-object pool (every format but AKAI).
    object_pool: int = 0

    def _unique_sample_name(self, base: str) -> str:
        if base not in self._sample_names:
            return base
        i = 1
        while True:
            suf = str(i)
            cand = base[:16 - len(suf)] + suf
            if cand not in self._sample_names:
                return cand
            i += 1

    def add_preset(self, preset: Preset, needed_samples: List[SampleData]) -> None:
        self.presets.append(preset)
        # CR-7: dedup by (name, content).  A genuine duplicate (same name AND
        # same PCM) is shared; a same-name/different-PCM sample is renamed and
        # this preset's zones are repointed — otherwise its zones would silently
        # resolve to the other bank's PCM.
        remap: dict = {}
        for sample in needed_samples:
            key = (len(sample.data), hash(sample.data))
            existing = self._sample_keys.get(sample.name)
            if existing is None:
                self._sample_names.add(sample.name)
                self._sample_keys[sample.name] = key
                self.samples.append(sample)
                self.current_size += _SAMPLE_CHUNK_OVERHEAD + len(sample.data)
            elif existing == key:
                continue                      # true duplicate — reuse
            else:
                new_name = self._unique_sample_name(sample.name)
                self._sample_names.add(new_name)
                self._sample_keys[new_name] = key
                self.samples.append(replace(sample, name=new_name))
                self.current_size += _SAMPLE_CHUNK_OVERHEAD + len(sample.data)
                remap[sample.name] = new_name
        if remap:
            for voice in preset.voices:
                for zone in voice.zones:
                    if zone.sample_name in remap:
                        zone.sample_name = remap[zone.sample_name]

        voice_overhead = sum(8 + len(v.zones) * 32 for v in preset.voices)
        self.current_size += _PRESET_CHUNK_OVERHEAD + voice_overhead

    def would_fit(self, preset: Preset, needed_samples: List[SampleData],
                  limit_bytes: int, capacity=None) -> bool:
        """Check if adding this preset+samples would stay within the limit."""
        max_samples, max_presets, max_files = capacity or _capacity('e4b')
        extra = _PRESET_CHUNK_OVERHEAD
        for voice in preset.voices:
            extra += 8 + len(voice.zones) * 32

        new_samples = 0
        for sample in needed_samples:
            key = (len(sample.data), hash(sample.data))
            existing = self._sample_keys.get(sample.name)
            if existing is None or existing != key:
                # New sample, or same name but different PCM (will be renamed in add_preset)
                extra += _SAMPLE_CHUNK_OVERHEAD + len(sample.data)
                new_samples += 1

        if len(self._sample_names) + new_samples > max_samples:
            return False

        if len(self.presets) + 1 > max_presets:
            return False

        if (max_files is not None
                and len(self._sample_names) + new_samples
                + len(self.presets) + 1 > max_files):
            return False

        # The resident-object pool, which the directory cap above says nothing
        # about: a volume can fit the directory four times over and still be
        # unloadable. Only applied where a pool is known.
        if self.object_pool:
            if akai_object_count(self.presets + [preset],
                                 len(self._sample_names) + new_samples) > self.object_pool:
                return False

        # PRAM, not object count, is what a K2000 actually runs out of.
        if self.pram_budget:
            used = bank_pram_bytes(len(self._sample_names) + new_samples,
                                   self.presets + [preset])
            if used > self.pram_budget:
                return False

        return (self.current_size + extra) <= limit_bytes

    def to_bank(self, base_name: str) -> Bank:
        """Convert to a Bank object for writing."""
        bank = Bank(
            name=f"{base_name[:12]}_{self.index:02d}",
            presets=self.presets,
            samples=self.samples,
        )
        return bank


def split_into_banks(
    source_banks: List[Bank],
    max_size_mb: float,
    base_name: str = "EMU_BANK",
    fmt: str = 'e4b',
    pram_k=None,
    max_objects=None,
) -> Tuple[List[Bank], List[str]]:
    """
    Pack presets from multiple source banks into size-limited output banks.

    Args:
        source_banks:  List of Bank objects (one per XPM)
        max_size_mb:   Maximum size per output bank in megabytes
        base_name:     Base name for output banks (truncated to 12 chars)

    Returns:
        Tuple of:
          - List of output Bank objects
          - List of warning strings (oversized presets, etc.)
    """
    limit_bytes = bank_limit_bytes(max_size_mb)
    cap = _capacity(fmt)
    _pram = pram_budget_bytes(pram_k) if fmt == 'krz' else 0
    _pool = (max_objects or _AKAI_OBJECT_POOL) if fmt == 'akai' else 0
    warnings: List[str] = []

    # Flatten: collect (preset, [its samples], source_bank_name) tuples
    # Each preset carries its own samples (may overlap across presets in same source bank)
    all_items: List[Tuple[Preset, List[SampleData], str]] = []

    for source_bank in source_banks:
        # Build sample lookup for this source bank
        sample_map = {s.name: s for s in source_bank.samples}

        for preset in source_bank.presets:
            needed_names = {
                zone.sample_name
                for voice in preset.voices
                for zone in voice.zones
            }
            # Iterate the sample LIST and filter, rather than iterating the
            # name set: Python randomises string hashing per process, so set
            # order differs between runs and this was the sole source of
            # mpc2emu's nondeterministic E4B output (6.3 M bytes differing
            # between two identical conversions -- same samples, same content,
            # different order). That made byte-comparison useless for
            # regression checking, which is exactly what you want when
            # changing a writer. `preset_needed_samples` above already used
            # this pattern; this was the one place that did not.
            needed_samples = [
                s for s in source_bank.samples
                if s.name in needed_names
            ]
            all_items.append((preset, needed_samples, source_bank.name))

    # Sort by estimated size descending (First-Fit Decreasing)
    def item_size(item):
        preset, samples, _ = item
        sz = _PRESET_CHUNK_OVERHEAD
        for v in preset.voices:
            sz += 8 + len(v.zones) * 32
        for s in samples:
            sz += _SAMPLE_CHUNK_OVERHEAD + len(s.data)
        return sz

    all_items.sort(key=item_size, reverse=True)

    # First-Fit Decreasing bin packing
    target_banks: List[TargetBank] = []

    for preset, needed_samples, source_name in all_items:
        preset_sz = item_size((preset, needed_samples, source_name))

        # Warn if a single preset exceeds the bank limit
        if preset_sz + _BANK_OVERHEAD > limit_bytes:
            warnings.append(
                f"  [WARN] Preset '{preset.name}' from '{source_name}' "
                f"({preset_sz/1024/1024:.1f} MB) exceeds bank limit "
                f"({max_size_mb:.0f} MB) — placed in its own bank. "
                f"To fix: use --bank-size to raise the limit "
                f"(E4XT max: 128 MB, K2000 max: 64 MB, S3000XL max: 32 MB), "
                f"or reduce preset size with --reduce-key-zones / --reduce-velocity-layers."
            )
        if _pram and preset_pram_bytes(preset) + _PRAM_SAMPLE * len(needed_samples) > _pram:
            need = (preset_pram_bytes(preset)
                    + _PRAM_SAMPLE * len(needed_samples)) / 1024
            warnings.append(
                f"  [WARN] Preset '{preset.name}' from '{source_name}' needs "
                f"{need:.0f} K of K2000 PRAM on its own, more than the "
                f"{_pram/1024:.0f} K budget — the bank will not load. A single "
                f"preset cannot be split; use --reduce-key-zones / "
                f"--reduce-velocity-layers, or --pram if the target machine "
                f"has a PRAM expansion."
            )

        if len(needed_samples) > cap[0]:
            where = {
                'akai': "an AKAI volume directory",
                'krz':  "the KRZ object-id ceiling (ids 200-999)",
            }.get(fmt, "the EOS sample-per-bank limit (S000-S999)")
            warnings.append(
                f"  [WARN] Preset '{preset.name}' from '{source_name}' "
                f"references {len(needed_samples)} unique samples, exceeding "
                f"{where} ({cap[0]}) — bank will be invalid. A single preset "
                f"cannot be split, so use --reduce-key-zones / "
                f"--reduce-velocity-layers."
            )

        # Find first target bank that fits
        placed = False
        for tb in target_banks:
            if tb.would_fit(preset, needed_samples, limit_bytes, cap):
                tb.add_preset(preset, needed_samples)
                placed = True
                break

        if not placed:
            # Open a new target bank
            tb = TargetBank(index=len(target_banks) + 1,
                            pram_budget=_pram, object_pool=_pool)
            tb.add_preset(preset, needed_samples)
            target_banks.append(tb)

    output_banks = [tb.to_bank(base_name) for tb in target_banks]
    return output_banks, warnings


def print_split_summary(
    source_banks: List[Bank],
    output_banks: List[Bank],
    max_size_mb: float,
) -> None:
    """Print a human-readable summary of the split result."""
    total_presets = sum(len(b.presets) for b in source_banks)
    total_samples = sum(len(b.samples) for b in source_banks)

    print(f"\n{'='*60}")
    print(f"Bank Split Summary")
    print(f"{'='*60}")
    print(f"  Source XPMs:      {len(source_banks)}")
    print(f"  Total presets:    {total_presets}")
    print(f"  Total samples:    {total_samples}")
    print(f"  Bank size limit:  {max_size_mb:.0f} MB")
    print(f"  Output banks:     {len(output_banks)}")
    print()

    for i, bank in enumerate(output_banks, 1):
        size_est = estimate_bank_size(bank)
        print(f"  Bank {i:02d}: '{bank.name}'")
        print(f"    Presets:  {len(bank.presets)}")
        print(f"    Samples:  {len(bank.samples)}")
        print(f"    Est. size: {size_est / 1024 / 1024:.2f} MB / {max_size_mb:.0f} MB "
              f"({100 * size_est / (max_size_mb * 1024 * 1024):.0f}% full)")
        preset_names = ', '.join(p.name for p in bank.presets[:6])
        if len(bank.presets) > 6:
            preset_names += f' … (+{len(bank.presets)-6} more)'
        print(f"    Presets:  [{preset_names}]")
    print()
