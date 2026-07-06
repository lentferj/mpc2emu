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
                  limit_bytes: int) -> bool:
        """Check if adding this preset+samples would stay within the limit."""
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

        if len(self._sample_names) + new_samples > _MAX_SAMPLES_PER_BANK:
            return False

        if len(self.presets) + 1 > _MAX_PRESETS_PER_BANK:
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
    # Safety margin: the per-sample / per-preset / per-bank overhead constants
    # below slightly *under*-count the real serialized size (E4Sa headers,
    # word-alignment padding, the mandatory trailing EMSt chunk + FORM framing),
    # so packing right up to the byte limit can spill a few KB over — and an E4B
    # even 1 byte past the E4XT's 128 MB sample RAM will not load.  Reserve 1 MB.
    _SAFETY_MARGIN = 1024 * 1024
    limit_bytes = max(1, int(max_size_mb * 1024 * 1024) - _SAFETY_MARGIN)
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
            needed_samples = [
                sample_map[name]
                for name in needed_names
                if name in sample_map
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
                f"To fix: use --bank-size to raise the limit (E4XT max: 128 MB, K2000 max: 64 MB), "
                f"or reduce preset size with --reduce-key-zones / --reduce-velocity-layers."
            )
        if len(needed_samples) > _MAX_SAMPLES_PER_BANK:
            warnings.append(
                f"  [WARN] Preset '{preset.name}' from '{source_name}' "
                f"references {len(needed_samples)} unique samples, exceeding "
                f"the EOS {_MAX_SAMPLES_PER_BANK}-sample-per-bank limit "
                f"(S000-S999) — bank will be invalid."
            )

        # Find first target bank that fits
        placed = False
        for tb in target_banks:
            if tb.would_fit(preset, needed_samples, limit_bytes):
                tb.add_preset(preset, needed_samples)
                placed = True
                break

        if not placed:
            # Open a new target bank
            tb = TargetBank(index=len(target_banks) + 1)
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
