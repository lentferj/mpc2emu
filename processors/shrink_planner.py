# SPDX-License-Identifier: GPL-2.0-or-later
#
# mpc2emu — https://github.com/lentferj/mpc2emu
# Copyright (C) 2026 Jan Lentfer
#
# Automatic thinning plan: choose --reduce-key-zones and
# --reduce-velocity-layers for a memory target, by MEASURING what each axis
# costs on the material in hand.
"""Pick the thinning that costs the least audible damage for a size target.

**WHY THIS EXISTS.** `--auto-fit` already shrinks an oversized preset, but it is
greedy along a FIXED ordering — velocity layers first, then key zones, then
sample rate — asserted in `fit_options` as "least-lossy-first for a musical
multisample". That ordering is an assumption, and it is wrong about as often as
it is right:

  * a piano's velocity layers carry most of its character, and dropping them is
    the single most destructive thing available;
  * a string pad's layers may differ only in level, where dropping them costs
    nothing a gain change cannot restore;
  * a pad sampled every 12 semitones is already stretching hard, so thinning key
    zones doubles an audible artefact;
  * a piano sampled every semitone can lose half its zones and never stretch
    more than a tone.

**The material decides, so measure the material.** Nothing here assumes an
ordering; it computes what each axis costs FOR THIS PRESET and searches the
combinations.

**ONE UNIT FOR BOTH AXES: CENTS OF SPECTRAL-CENTROID ERROR.** This is what makes
the two comparable rather than merely both "loss":

  * **Key thinning** makes a surviving zone cover notes it was not sampled for.
    A note played from a root `N` semitones away has its WHOLE spectrum shifted
    by `N * 100` cents — formants included, which is exactly why a stretched
    multisample sounds wrong. The error is the transposition, in cents, and it
    is computable from the zone layout alone with no audio at all.

  * **Velocity thinning** makes a surviving layer stand in for a dropped one.
    The error is how different the two actually sound, measured as the shift in
    spectral centroid: `1200 * log2(c_kept / c_dropped)` cents. Centroid is used
    because it is LEVEL-INDEPENDENT — layers usually differ in level too, and a
    level difference is not damage, since the writer can compensate with gain.

Both land in cents of centroid error, so a single objective ranks every
combination without a hand-tuned weight between the axes.

**WHAT THIS DELIBERATELY DOES NOT MODEL.** Centroid is one number per spectrum:
two sounds with the same centroid and different shapes read as identical here.
It was chosen because this project has already used it as a cross-machine timbre
measure and knows its limits (§the AKAI/E4XT filter work) — not because it is
complete. It is a ranking, not a fidelity score, and the objective values are
only meaningful RELATIVE to each other within one preset.
"""
from __future__ import annotations

import cmath
import math
import weakref
from typing import Dict, List, Optional, Sequence, Tuple

from models.common import Bank, Preset, SampleData, VoiceLayer
from models.diagnostics import emit as _diag, WARNING as _W

#: Frame length for the centroid FFT. Power of two; 2048 at 44.1 kHz is 46 ms,
#: long enough to resolve a bass fundamental and short enough to stay inside a
#: steady part of a note.
_FRAME = 2048

#: Where in the sample to take the frame, as a fraction of its length. NOT the
#: start: an attack transient is the least representative part of a sample and
#: would make a centroid comparison between velocity layers measure the pick or
#: hammer noise rather than the sustained timbre.
_FRAME_AT = 0.25

#: Keyed by `id()` BUT WITH A WEAKREF THAT EVICTS THE ENTRY WHEN THE SAMPLE
#: DIES. `id()` alone is unique only among LIVE objects: CPython reuses an
#: address as soon as the previous tenant is collected, so a freed sample's
#: centroid was being served for a completely different one. Demonstrated
#: 2026-09-13 -- a 32-harmonic tone reported a sine's 447 Hz because it landed
#: on the same address. It surfaced as one test failing only when the whole
#: suite ran, and in a real conversion, where samples are created and dropped
#: constantly, it would have been an intermittent wrong measurement.
#:
#: A WeakKeyDictionary would be the obvious fix and does not work here:
#: SampleData is a dataclass with `eq`, so it is unhashable. The eviction
#: callback gives the same guarantee -- the id cannot be reused while the entry
#: lives, because the entry is removed the moment the object is collected.
_centroid_cache: Dict[int, Optional[float]] = {}
_energy_cache: Dict[int, float] = {}
_cache_refs: Dict[int, "weakref.ref"] = {}


def _cache_put(sd: SampleData, centroid: Optional[float], energy: float) -> None:
    key = id(sd)

    def _evict(_ref, _key=key):
        _centroid_cache.pop(_key, None)
        _energy_cache.pop(_key, None)
        _cache_refs.pop(_key, None)

    _centroid_cache[key] = centroid
    _energy_cache[key] = energy
    try:
        _cache_refs[key] = weakref.ref(sd, _evict)
    except TypeError:                       # not weakref-able: do not cache it
        _evict(None)


def _fft(a: List[complex]) -> List[complex]:
    """Iterative radix-2 FFT. Pure stdlib, because this project ships no
    third-party dependencies (see the no-dependencies rule)."""
    n = len(a)
    if n & (n - 1):
        raise ValueError('length must be a power of two')
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    ln = 2
    while ln <= n:
        ang = -2j * math.pi / ln
        wl = cmath.exp(ang)
        for i in range(0, n, ln):
            w = 1 + 0j
            for k in range(i, i + ln // 2):
                u = a[k]
                v = a[k + ln // 2] * w
                a[k] = u + v
                a[k + ln // 2] = u - v
                w *= wl
        ln <<= 1
    return a


def _frames(sd: SampleData) -> List[float]:
    """Mono float frames from a SampleData, or [] when it cannot be read."""
    data = getattr(sd, 'data', None)
    if not data:
        return []
    depth = getattr(sd, 'bit_depth', 16) or 16
    ch = max(1, getattr(sd, 'channels', 1) or 1)
    if depth == 16:
        n = len(data) // 2
        out = []
        for i in range(n):
            v = data[2 * i] | (data[2 * i + 1] << 8)
            out.append(float(v - 65536 if v > 32767 else v))
    elif depth == 8:
        out = [float(b) - 128.0 for b in data]
    else:
        return []
    if ch > 1:                       # mix to mono; centroid is a timbre measure
        out = [sum(out[i:i + ch]) / ch for i in range(0, len(out) - ch + 1, ch)]
    return out


def sample_centroid(sd: SampleData) -> Optional[float]:
    """Spectral centroid of one sample, in Hz. None when unmeasurable.

    Cached by object identity: a preset's layers routinely share SampleData, and
    the FFT is the only expensive thing here.
    """
    key = id(sd)
    if key in _centroid_cache:
        return _centroid_cache[key]
    frames = _frames(sd)
    sr = getattr(sd, 'sample_rate', 44100) or 44100
    if len(frames) < _FRAME:
        _cache_put(sd, None, 0.0)
        return None
    start = min(int(len(frames) * _FRAME_AT), len(frames) - _FRAME)
    seg = frames[start:start + _FRAME]
    _rms = math.sqrt(sum(s * s for s in seg) / len(seg))
    # Hann window: an unwindowed frame smears energy across the whole spectrum
    # and pulls every centroid toward the middle, which would flatten exactly
    # the differences this is here to detect.
    seg = [s * (0.5 - 0.5 * math.cos(2 * math.pi * i / (_FRAME - 1)))
           for i, s in enumerate(seg)]
    spec = _fft([complex(s, 0.0) for s in seg])
    num = den = 0.0
    for k in range(1, _FRAME // 2):           # skip DC: it carries no timbre
        mag = abs(spec[k])
        num += mag * (k * sr / _FRAME)
        den += mag
    val = (num / den) if den > 0 else None
    _cache_put(sd, val, _rms)
    return val


# ── what a (note, velocity) actually plays ───────────────────────────────────

def _sounding(preset: Preset, note: int, vel: int):
    """Every (sample_name, root_key) that sounds at this note+velocity.

    **ALL matching zones, not the first.** An earlier version took the first
    match, the way a single-voice writer walks zones -- and it made the cost
    model useless on stacked layers, which is most of the material here. With
    four voices layered, removing zones from one voice let a note "fall through"
    to a different voice's sample, so the measured error depended on WHICH zone
    happened to survive rather than on how much was lost. The cost curve came
    out chaotic: on a real preset, thinning 80% of zones scored 370 cents where
    thinning 40% scored 794, which is not a fidelity measure, it is noise.
    """
    out = []
    for voice in preset.voices:
        for z in getattr(voice, 'zones', ()):
            if (getattr(z, 'lo_key', 0) <= note <= getattr(z, 'hi_key', 127)
                    and getattr(z, 'lo_vel', 0) <= vel <= getattr(z, 'hi_vel', 127)):
                out.append((getattr(z, 'sample_name', None),
                            getattr(z, 'root_key', None)))
    return out


def sample_energy(sd: SampleData) -> float:
    """RMS of a sample, for weighting layers in a mix. Cached alongside the
    centroid, from the same frame, so the two always describe the same audio."""
    if id(sd) not in _energy_cache:
        sample_centroid(sd)                    # fills both caches
    return _energy_cache.get(id(sd), 0.0)


def _mix_centroid(zones, note: int, by_name: Dict[str, SampleData]):
    """Energy-weighted centroid of everything sounding at one note, in Hz.

    **Pitching a sample scales its whole spectrum**, so each layer contributes
    its own centroid times its transposition ratio. That is the step that puts
    both axes in one unit: thinning key zones changes a `root`, thinning
    velocity layers removes a member of this sum, and both come out as a shift
    of this single number.

    Weighted by RMS because when layers SUM, the loud one sets the timbre. (That
    is different from SUBSTITUTION, where a level difference is not damage
    because the writer can compensate with gain -- which is why the centroid,
    not the level, is what gets compared.)
    """
    num = den = 0.0
    for name, root in zones:
        if name is None or root is None:
            continue
        sd = by_name.get(name)
        if sd is None:
            continue
        c = sample_centroid(sd)
        if c is None:
            continue
        w = max(sample_energy(sd), 1e-9)
        num += w * c * (2.0 ** ((note - root) / 12.0))
        den += w
    return (num / den) if den > 0 else None


def coverage_error_cents(before: Preset, after: Preset,
                         by_name: Dict[str, SampleData],
                         note_step: int = 2,
                         velocities: Sequence[int] = (16, 48, 80, 112)) -> float:
    """RMS spectral-centroid error, in cents, between two versions of a preset.

    Walks the (note x velocity) grid the preset covers and compares what sounds
    before against what sounds after. **A cell that loses its sound entirely is
    not a large error, it is a different kind of failure** -- counted at a fixed
    heavy penalty rather than allowed to dominate an RMS meant to measure
    timbre drift.

    Falls back to pure transposition error when no centroid is available (no
    sample data, or too short to window): the centroid factor cancels and what
    is left is `100 * (root_before - root_after)` cents, which is right for the
    key axis and simply declines to rank the velocity axis.
    """
    lo, hi = 127, 0
    for voice in before.voices:
        for z in getattr(voice, 'zones', ()):
            lo = min(lo, getattr(z, 'lo_key', 0))
            hi = max(hi, getattr(z, 'hi_key', 127))
    if lo > hi:
        return 0.0

    _SILENCE_PENALTY = 2400.0          # two octaves; a dead cell is not "drift"
    acc = 0.0
    n = 0
    for note in range(lo, hi + 1, max(1, note_step)):
        for vel in velocities:
            zb = _sounding(before, note, vel)
            za = _sounding(after, note, vel)
            if not zb:
                continue               # not covered before either; not a loss
            if not za:
                acc += _SILENCE_PENALTY ** 2
                n += 1
                continue
            cb = _mix_centroid(zb, note, by_name)
            ca = _mix_centroid(za, note, by_name)
            if cb and ca:
                err = 1200.0 * math.log2(ca / cb)
            else:                      # no audio: transposition only
                rb = [r for _, r in zb if r is not None]
                ra = [r for _, r in za if r is not None]
                if not rb or not ra:
                    continue
                err = 100.0 * (sum(rb) / len(rb) - sum(ra) / len(ra))
            acc += err * err
            n += 1
    return math.sqrt(acc / n) if n else 0.0


# ── the search ───────────────────────────────────────────────────────────────

class ShrinkPlan:
    """What to pass to the reducers, and what it is expected to cost."""

    def __init__(self, key_pct: float, vel_pct: float, est_bytes: int,
                 cost_cents: float, orig_bytes: int, feasible: bool,
                 tried: int, blind: bool, rugged: bool = False):
        self.key_pct = key_pct
        self.vel_pct = vel_pct
        self.est_bytes = est_bytes
        self.cost_cents = cost_cents
        self.orig_bytes = orig_bytes
        self.feasible = feasible          # did anything reach the target?
        self.tried = tried
        self.blind = blind                # no centroids: key axis ranked only
        self.rugged = rugged              # a milder plan scored worse: the
                                          # objective is not smooth here

    def __repr__(self):
        return (f'<ShrinkPlan key -{self.key_pct:.0f}% vel -{self.vel_pct:.0f}% '
                f'{self.orig_bytes/1048576:.2f}->{self.est_bytes/1048576:.2f} MB '
                f'cost {self.cost_cents:.0f} cents>')


def _simulate(preset: Preset, samples: List[SampleData],
              key_pct: float, vel_pct: float):
    """Apply the REAL reducers to a copy and measure the result.

    Deliberately not a size model. Every divergence-between-model-and-code bug
    in this project has come from two places computing the same quantity, so
    the planner runs the same functions the conversion will run.
    """
    import copy
    from writers.bank_splitter import estimate_preset_size, preset_needed_samples
    from processors.zone_reducer import (thin_key_zones_for_preset,
                                         thin_velocity_layers)
    p = copy.deepcopy(preset)             # zones hold sample NAMES, so this is
                                          # cheap: no audio is copied
    if vel_pct > 0:
        thin_velocity_layers(p, 100.0 - vel_pct)
    if key_pct > 0:
        thin_key_zones_for_preset(p, 100.0 - key_pct)
    needed = preset_needed_samples(p, samples)
    return p, estimate_preset_size(p, needed)


def plan_shrink(preset: Preset, samples: List[SampleData], target_bytes: int,
                coarse: int = 10, refine: int = 2, max_pct: float = 90.0,
                tol_cents: float = 50.0, tol_frac: float = 0.10) -> ShrinkPlan:
    """Choose (key_pct, vel_pct) that reaches `target_bytes` most cheaply.

    Coarse grid, then a refinement pass around the winner -- an exhaustive 2%
    search over both axes is ~2000 simulations of a preset that may carry
    hundreds of zones, and two passes reach the same answer for a tenth of it.

    **THE OBJECTIVE IS RUGGED ON STACKED-LAYER MATERIAL, SO THE ARGMIN IS NOT
    TAKEN NAIVELY.** Measured on a real 4-voice preset, cost against key-zone
    thinning ran 0, 106, 300, 321, 796, 327, 842, 919, 464, 918 cents -- not
    noise from a coarse note grid (a per-semitone grid reproduces it), but real
    structure: with layers stacked, WHICH voice keeps coverage at WHICH note
    decides the mix, so a deeper cut can happen to land better than a shallower
    one. A single-voice preset is by contrast cleanly monotone (0, 136, 173,
    215, 217, 268, 344, 483, 979, 1759).

    Taking the raw argmin on rugged material means overfitting a lucky sample.
    So: find the cheapest feasible plan, then **accept the MILDEST plan whose
    cost is within tolerance of it** (`tol_cents` absolute or `tol_frac`
    relative, whichever is larger). Two plans that score within a few percent of
    each other on a one-number timbre proxy are not distinguishable, and between
    indistinguishable plans the one that removes less material wins.
    """
    from writers.bank_splitter import estimate_preset_size, preset_needed_samples
    by_name = {s.name: s for s in samples}
    orig_needed = preset_needed_samples(preset, samples)
    orig_bytes = estimate_preset_size(preset, orig_needed)

    # Without audio the velocity axis cannot be ranked at all; say so rather
    # than let a blind ranking look like a measured one.
    blind = not any(sample_centroid(s) for s in orig_needed[:8])

    feasible: List[Tuple[float, float, float, int]] = []   # cost, kp, vp, est
    seen = set()

    def consider(kp: float, vp: float):
        if (kp, vp) in seen:
            return
        seen.add((kp, vp))
        after, est = _simulate(preset, samples, kp, vp)
        if est <= target_bytes:
            feasible.append((coverage_error_cents(preset, after, by_name),
                             kp, vp, est))

    steps = [float(x * coarse) for x in range(int(max_pct // coarse) + 1)]
    for kp in steps:
        for vp in steps:
            consider(kp, vp)

    if feasible:                               # refine around the cheapest
        _, bk, bv, _ = min(feasible)
        near = lambda c: [c + d for d in range(-coarse, coarse + 1, refine)
                          if 0 <= c + d <= max_pct]
        for kp in near(int(bk)):
            for vp in near(int(bv)):
                consider(float(kp), float(vp))

    if not feasible:
        # NOTHING REACHES THE TARGET. Do not fall back to max thinning on both
        # axes -- that was the first behaviour here and it is maximally
        # destructive for a goal it still does not meet. Take the SMALLEST
        # reachable size instead, and among plans that reach it, the cheapest.
        floor_plans = []
        for kp in steps:
            for vp in steps:
                after, est = _simulate(preset, samples, kp, vp)
                floor_plans.append((est, kp, vp, after))
        smallest = min(e for e, _, _, _ in floor_plans)
        near = [f for f in floor_plans if f[0] <= smallest * 1.02]
        best_floor = min(near, key=lambda f: (
            coverage_error_cents(preset, f[3], by_name), f[1] + f[2]))
        est, kp, vp, after = best_floor
        return ShrinkPlan(kp, vp, est,
                          coverage_error_cents(preset, after, by_name),
                          orig_bytes, False, len(seen), blind, rugged=False)

    best_cost = min(c for c, _, _, _ in feasible)
    tol = max(tol_cents, best_cost * tol_frac)
    near_best = [f for f in feasible if f[0] <= best_cost + tol]
    # mildest total thinning first, then the larger result, then lower cost
    cost, kp, vp, est = min(near_best, key=lambda f: (f[1] + f[2], -f[3], f[0]))

    # Is the objective non-monotone over the feasible set? If a strictly milder
    # plan scored WORSE, the surface is rugged here and the number should not be
    # read as a smooth fidelity score.
    rugged = any(c2 > cost and k2 <= kp and v2 <= vp and (k2, v2) != (kp, vp)
                 for c2, k2, v2, _ in feasible)
    return ShrinkPlan(kp, vp, est, cost, orig_bytes, True, len(seen), blind,
                      rugged=rugged)


def shrink_bank(bank: Bank, target_bytes: Optional[int] = None,
                by_pct: Optional[float] = None, report: bool = False) -> None:
    """Plan and apply a per-preset shrink, in place.

    **Per preset, not per bank.** A bank's presets differ enormously in how
    they tolerate thinning -- a one-shot with two zones has nothing to give, a
    12-zone pad has plenty -- so one global percentage is the wrong instrument.
    That is exactly what `--reduce-key-zones` already is, and why this exists.
    """
    from processors.zone_reducer import (_prune_unused_samples,
                                         thin_key_zones_for_preset,
                                         thin_velocity_layers)
    from writers.bank_splitter import estimate_preset_size, preset_needed_samples

    rows = []
    for preset in bank.presets:
        cur = estimate_preset_size(preset, preset_needed_samples(preset, bank.samples))
        tgt = int(cur * (1.0 - by_pct / 100.0)) if by_pct is not None else target_bytes
        if tgt is None or cur <= tgt:
            rows.append((preset.name, cur, cur, 0.0, 0.0, 0.0, 'already fits'))
            continue
        plan = plan_shrink(preset, bank.samples, tgt)
        if plan.vel_pct > 0:
            thin_velocity_layers(preset, 100.0 - plan.vel_pct)
        if plan.key_pct > 0:
            thin_key_zones_for_preset(preset, 100.0 - plan.key_pct)
        note = ''
        if not plan.feasible:
            note = 'TARGET NOT REACHABLE'
            # NEVER SILENT, AND ALWAYS WITH THE MAGNITUDE. Without this the
            # whole user-visible output was "shrank 1 preset(s)" while the
            # result sat 14% over the target -- the same shape as the rate-snap
            # bug, where "+2 cents" and "+831 cents" both read as a bare
            # warning and every preset looked alike.
            over = plan.est_bytes - tgt
            _diag(_W, 'SHRINK_TARGET_UNREACHABLE',
                  f"preset '{preset.name}' cannot reach "
                  f"{tgt/1048576:.2f} MB by thinning: the smallest reachable "
                  f"size is {plan.est_bytes/1048576:.2f} MB, "
                  f"{over/1024:.0f} KB over ({plan.est_bytes/tgt*100-100:.0f}%). "
                  f"Key-zone and velocity-layer thinning cannot go below one "
                  f"sample per voice, and free whole samples at a time.",
                  content_lost=True, subject=str(preset.name),
                  remedy='also reduce the sample data itself, by mono '
                         'conversion or a sample-rate ceiling; those shrink '
                         'below the one-sample-per-voice floor that thinning '
                         'cannot cross. Or raise the target.',
                  detail={'target_bytes': tgt,
                          'reached_bytes': plan.est_bytes,
                          'over_bytes': over,
                          'floor_bytes': plan.est_bytes,
                          'key_pct': plan.key_pct, 'vel_pct': plan.vel_pct,
                          'cli_flag': ['--mono', '--max-sample-rate']},
                  echo=f"    [WARN] '{preset.name}' could not reach "
                       f"{tgt/1048576:.2f} MB — smallest reachable is "
                       f"{plan.est_bytes/1048576:.2f} MB "
                       f"({over/1024:.0f} KB over). Thinning cannot go below "
                       f"one sample per voice; use --mono or --max-sample-rate "
                       f"to shrink the sample data itself.")
        elif plan.blind:
            note = 'no audio: key axis only'
        elif plan.rugged:
            note = 'rugged objective'
        rows.append((preset.name, cur, plan.est_bytes, plan.key_pct,
                     plan.vel_pct, plan.cost_cents, note))

    freed = _prune_unused_samples(bank)
    if not report:
        touched = sum(1 for r in rows if r[3] or r[4])
        print(f"  '{bank.name}': shrank {touched} preset(s), "
              f"{freed} sample(s) no longer needed")
        return

    print(f"\n  '{bank.name}' shrink report — cost is RMS spectral-centroid "
          f"error in cents,\n  and is comparable BETWEEN PLANS FOR ONE PRESET, "
          f"not between presets.")
    print(f"    {'preset':<20}{'MB in':>7}{'MB out':>8}{'key%':>6}{'vel%':>6}"
          f"{'cost':>7}  note")
    for name, a, b, k, v, c, note in rows:
        print(f"    {str(name)[:20]:<20}{a/1048576:>7.2f}{b/1048576:>8.2f}"
              f"{k:>6.0f}{v:>6.0f}{c:>7.0f}  {note}")
    print(f"    {freed} sample(s) no longer needed")
