#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Batch-convert MPC ONE Autosampler programs into a variant matrix (plain /
# single-cycle / vintage-resampled / both), tail-trimmed, merged into ONE E4B
# bank and bundled onto an E4B CD image.
# Jan Lentfer <jan.lentfer@web.de>
# https://github.com/lentferj/mpc2emu

"""
The 3.9.0 MPC Standalone `.xpm` is a gzipped-JSON format the parser can't read
yet (TODO.md "MPC Standalone 3.9.0 .xpm"), so each program is rebuilt from its
sidecar `<name>_[ProgramData]/` folder of note-named WAVs (--from-samples path):
samples + auto-mapped key zones, no original synth params (there aren't any to
carry over — the WAVs are the whole program).

Every variant is TAIL-TRIMMED first (--trim-tail default: -72 dB "silence only",
drops the autosampler whole-take loop), then optionally processed:
  (plain)  trimmed one-shot
  SC       --single-cycle (looped oscillator, neutral synth preset)
  E2       --resample emulator2 (8-bit / 27.5 kHz)
  EX       --resample emax1     (12-bit / 27.5 kHz)
  E2SC     single-cycle, then EMU II resample (matches convert.py's own order)
  EXSC     single-cycle, then Emax resample

All 3 programs × 6 variants = 18 presets are merged into ONE E4B bank (each
preset keeps its variant-suffixed name, e.g. "K2-01 E2SC"); every sample is
renamed uniquely ("P<prog> <tag> <NN>", <=16 chars) so the flat bank sample list
has no collisions, and each preset's zones are repointed to its renamed samples.
The single bank is then written to one ISO.

Run from the repo root:
    python3 make_autosampler_variants.py
"""

from pathlib import Path

from models.common import Bank
from parsers.sampledir_parser import parse_sample_dir
from processors.tail_trim import trim_tail_bank
from processors.single_cycle import single_cycle_bank
from processors.resampler import resample_bank
from writers.e4b_writer import write_e4b
from writers.iso_builder import build_iso

SRC_ROOT = Path("/home/lentferj/temp/SamplerExports")
PROGRAMS = ["K2-01", "K2-02", "K2-03"]
OUT_DIR = Path("/home/lentferj/temp")
BANK_NAME = "K2 AUTOSAMP"          # internal E4B bank name (<=16)
ISO_NAME = "K2_AUTOSAMP"           # on-disk .iso / volume label

# name suffix, sample-name tag, single_cycle?, resample profile (None = off)
VARIANTS = [
    ("",     "PL",   False, None),
    ("SC",   "SC",   True,  None),
    ("E2",   "E2",   False, "emulator2"),
    ("EX",   "EX",   False, "emax1"),
    ("E2SC", "E2SC", True,  "emulator2"),
    ("EXSC", "EXSC", True,  "emax1"),
]


def build_variant_bank(program: str, suffix: str, do_single_cycle: bool,
                       resample_profile) -> Bank:
    """Parse one program's WAV folder, tail-trim, then optionally single-cycle
    and/or vintage-resample.  Returns the processed (single-preset) Bank."""
    bank = parse_sample_dir(str(SRC_ROOT / f"{program}_[ProgramData]"))

    name = f"{program} {suffix}".strip()[:16]
    bank.name = name
    for p in bank.presets:
        p.name = name

    # Tail-trim always runs first (as in convert.py's pipeline), so single-cycle
    # / resample see the shortened one-shot audio.
    trim_tail_bank(bank)
    if do_single_cycle:
        single_cycle_bank(bank, cycles="auto", workers=1)
    if resample_profile:
        resample_bank(bank, resample_profile, True, restore_level=True, workers=1)
    return bank


def merge_into(combined: Bank, variant_bank: Bank, prog_idx: int, tag: str,
               preset_number: int) -> None:
    """Append `variant_bank`'s samples + preset to `combined`, renaming every
    sample uniquely and repointing the preset's zones to the new names."""
    rename = {}
    for i, s in enumerate(variant_bank.samples):
        new = f"P{prog_idx} {tag} {i:02d}"[:16]
        rename[s.name] = new
        s.name = new
        combined.samples.append(s)
    for preset in variant_bank.presets:
        for voice in preset.voices:
            for z in voice.zones:
                if z.sample_name in rename:
                    z.sample_name = rename[z.sample_name]
        preset.program_number = preset_number
        combined.presets.append(preset)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    combined = Bank(name=BANK_NAME)

    preset_number = 0
    for prog_idx, program in enumerate(PROGRAMS, 1):
        if not (SRC_ROOT / f"{program}_[ProgramData]").exists():
            print(f"[SKIP] {program} not found")
            continue
        for suffix, tag, do_sc, profile in VARIANTS:
            print(f"\n{'='*60}\n{program} — {suffix or '(plain)'}\n{'='*60}")
            vbank = build_variant_bank(program, suffix, do_sc, profile)
            merge_into(combined, vbank, prog_idx, tag, preset_number)
            preset_number += 1

    print(f"\n{'='*60}\nMerged bank: {len(combined.presets)} preset(s), "
          f"{len(combined.samples)} sample(s)\n{'='*60}")

    e4b_path = OUT_DIR / f"{ISO_NAME}.E4B"
    write_e4b(combined, str(e4b_path))

    iso_path = OUT_DIR / f"{ISO_NAME}.iso"
    build_iso([str(e4b_path)], str(iso_path), volume_label=ISO_NAME)
    print(f"\nDone: 1 bank / {len(combined.presets)} presets -> {iso_path}")


if __name__ == "__main__":
    main()
