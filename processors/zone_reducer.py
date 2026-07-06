# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# Original implementation. No third-party source code used.
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
Zone Reducer
------------
Thins out densely multisampled instruments so they fit the limited sample
memory of vintage hardware (e.g. E4XT: 4-128 MB sample RAM, max 1000
samples/bank — see docs/E4B_FORMAT.md §6.3) instead of forcing the user to
split a library across many banks.

Two independent axes can be reduced, by percentage of the original count:
  - velocity layers  (separate VoiceLayer objects within a Preset)
  - key zones        (ZoneMapping entries within a VoiceLayer)

Removed zones/layers are not just dropped: their surviving neighbors' key or
velocity ranges are widened to absorb the gap, split at the midpoint between
the two surviving neighbors' original boundaries — so the extra pitch-shift
distance this introduces is spread evenly across both sides of each gap
rather than dumped entirely onto one neighbor.
"""

from typing import Callable, List, TypeVar
from models.common import Bank, Preset, VoiceLayer

T = TypeVar('T')


def _thin_and_redistribute(
    items: List[T],
    keep_pct: float,
    get_lo: Callable[[T], int],
    get_hi: Callable[[T], int],
    set_range: Callable[[T, int, int], None],
    full_lo: int = 0,
    full_hi: int = 127,
) -> List[T]:
    """
    Keep ~keep_pct% of `items`, evenly spaced across the lo..hi range
    (always keeping the lowest- and highest-ranged item, so the full 0..127
    span stays covered), then stretch each survivor's [lo, hi] to cover the
    gap left by its removed neighbors.

    Each gap is split at the midpoint between the two surviving neighbors'
    *original* boundary values — not the already-stretched ones — so a chain
    of removals doesn't compound onto a single survivor.
    """
    n = len(items)
    keep_count = max(1, min(n, round(n * keep_pct / 100.0)))
    if keep_count >= n:
        return list(items)

    ordered = sorted(items, key=get_lo)

    if keep_count == 1:
        keep_idx = [n // 2]
    else:
        # Evenly spaced index selection (nearest-neighbor downsampling) —
        # guarantees index 0 and n-1 are always kept.
        keep_idx = sorted({round(i * (n - 1) / (keep_count - 1))
                           for i in range(keep_count)})
    kept = [ordered[i] for i in keep_idx]

    orig_lo = [get_lo(it) for it in kept]
    orig_hi = [get_hi(it) for it in kept]

    # CR-6: gap-redistribution only makes sense when the kept items form a
    # non-overlapping chain along this axis (a true multisample spread).  When
    # they OVERLAP — drum-kit voices that are all full-range velocity, or
    # velocity-split zones being thinned on the key axis — the midpoint math
    # produces inverted ranges (e.g. lo=64 > hi=63 → silent) and effectively
    # deletes layers/pads.  Then just drop the surplus and leave each survivor's
    # original range untouched.
    if len(kept) == 1:
        set_range(kept[0], full_lo, full_hi)
        return kept

    contiguous = all(orig_lo[i] > orig_hi[i - 1] for i in range(1, len(kept)))
    if not contiguous:
        return kept   # overlapping / parallel items — keep original ranges

    last = len(kept) - 1
    for i, item in enumerate(kept):
        new_lo = full_lo if i == 0    else (orig_hi[i - 1] + orig_lo[i]) // 2 + 1
        new_hi = full_hi if i == last else (orig_hi[i] + orig_lo[i + 1]) // 2
        if new_lo <= new_hi:                 # guard: never emit lo > hi
            set_range(item, new_lo, new_hi)

    return kept


def thin_key_zones(voice: VoiceLayer, keep_pct: float) -> int:
    """
    Reduce `voice`'s key-zone samples to ~keep_pct% of the original count,
    widening survivors' key ranges to cover the gaps. Returns the number of
    zones removed.

    A single voice may carry several velocity bands as zones (the XPM parser
    packs non-overlapping velocity layers into one voice).  Thinning across the
    combined, key-sorted list would interleave bands and tear holes in the
    velocity coverage (e.g. removing every high-velocity zone over a key range),
    so each velocity band is thinned and re-spread to full keyboard coverage
    INDEPENDENTLY.
    """
    before = len(voice.zones)
    from collections import OrderedDict
    bands: "OrderedDict[tuple, list]" = OrderedDict()
    for z in voice.zones:
        bands.setdefault((z.lo_vel, z.hi_vel), []).append(z)

    new_zones: list = []
    for band_zones in bands.values():
        new_zones += _thin_and_redistribute(
            band_zones, keep_pct,
            get_lo=lambda z: z.lo_key,
            get_hi=lambda z: z.hi_key,
            set_range=lambda z, lo, hi: (setattr(z, 'lo_key', lo),
                                         setattr(z, 'hi_key', hi)),
        )
    voice.zones = new_zones
    return before - len(voice.zones)


def _thin_velocity_bands_in_voice(voice: VoiceLayer, keep_pct: float) -> int:
    """
    Reduce a *single voice*'s distinct velocity BANDS to ~keep_pct%.

    The XPM parser packs a keygroup's velocity layers into one voice as zones
    with differing (lo_vel, hi_vel) — so the whole preset is one voice and the
    voice-level thinning below sees nothing to remove.  Here we group that
    voice's zones by velocity band (the mirror of `thin_key_zones`, which groups
    by band on the key axis), keep ~keep_pct% of the bands widened to cover the
    full 0..127 velocity span, and drop the removed bands' zones entirely.
    Returns the number of bands removed.
    """
    from collections import OrderedDict
    bands: "OrderedDict[tuple, list]" = OrderedDict()
    for z in voice.zones:
        bands.setdefault((z.lo_vel, z.hi_vel), []).append(z)
    if len(bands) <= 1:
        return 0                      # no velocity layering to thin

    band_list = list(bands.values())
    before = len(band_list)

    def set_band_range(b: list, lo: int, hi: int) -> None:
        for z in b:
            z.lo_vel = lo
            z.hi_vel = hi

    kept = _thin_and_redistribute(
        band_list, keep_pct,
        get_lo=lambda b: min(z.lo_vel for z in b),
        get_hi=lambda b: max(z.hi_vel for z in b),
        set_range=set_band_range,
    )
    voice.zones = [z for band in kept for z in band]
    return before - len(kept)


def thin_velocity_layers(preset: Preset, keep_pct: float) -> int:
    """
    Reduce `preset`'s velocity layers to ~keep_pct%, widening survivors'
    velocity ranges to cover the gaps. Returns the number of layers removed.

    Velocity layering has two representations in the model, so we thin whichever
    one this preset uses:
      - **Separate VoiceLayer objects** per layer (SFZ / SF2 / GIG) → thin the
        voices, propagating each survivor's new velocity range to its zones.
      - **One voice carrying several velocity bands as zones** (XPM keygroups)
        → thin the bands within that voice (see `_thin_velocity_bands_in_voice`).
    """
    if len(preset.voices) > 1:
        before = len(preset.voices)

        def voice_lo(v: VoiceLayer) -> int:
            return min((z.lo_vel for z in v.zones), default=0)

        def voice_hi(v: VoiceLayer) -> int:
            return max((z.hi_vel for z in v.zones), default=127)

        def set_voice_range(v: VoiceLayer, lo: int, hi: int) -> None:
            for z in v.zones:
                z.lo_vel = lo
                z.hi_vel = hi

        preset.voices = _thin_and_redistribute(
            preset.voices, keep_pct,
            get_lo=voice_lo, get_hi=voice_hi, set_range=set_voice_range,
        )
        return before - len(preset.voices)

    if preset.voices:
        return _thin_velocity_bands_in_voice(preset.voices[0], keep_pct)
    return 0


def _prune_unused_samples(bank: Bank) -> int:
    """
    Drop bank-global samples no longer referenced by any zone after thinning.
    This is what actually shrinks the bank's memory footprint — without it,
    thinned-out zones would still drag their now-orphaned samples along.
    Returns the number of samples removed.
    """
    used = {
        zone.sample_name
        for preset in bank.presets
        for voice in preset.voices
        for zone in voice.zones
    }
    before = len(bank.samples)
    bank.samples = [s for s in bank.samples if s.name in used]
    return before - len(bank.samples)


def reduce_bank(bank: Bank, key_zone_pct: float = 0.0,
                velocity_layer_pct: float = 0.0) -> None:
    """
    Thin out `bank` in place to shrink its sample-memory footprint.

    Args:
      key_zone_pct:       percentage of each voice's key-zone samples to
                          REMOVE (e.g. 30 removes ~30%, keeping ~70% spread
                          evenly across the keyboard)
      velocity_layer_pct: percentage of each preset's velocity-layer voices
                          to REMOVE (e.g. 30 removes ~30%, keeping ~70%
                          spread evenly across the velocity range)

    The two axes are independent: set one to 0 to leave it untouched
    (e.g. keep all velocity layers, only thin key zones).
    """
    if key_zone_pct <= 0 and velocity_layer_pct <= 0:
        return

    removed_voices = removed_zones = 0
    for preset in bank.presets:
        if velocity_layer_pct > 0:
            removed_voices += thin_velocity_layers(preset, 100.0 - velocity_layer_pct)
        if key_zone_pct > 0:
            for voice in preset.voices:
                removed_zones += thin_key_zones(voice, 100.0 - key_zone_pct)

    removed_samples = _prune_unused_samples(bank)
    print(f"  '{bank.name}': removed {removed_voices} velocity layer(s), "
          f"{removed_zones} key zone(s) -> {removed_samples} sample(s) "
          f"no longer needed")
