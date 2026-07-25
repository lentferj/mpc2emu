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
Auto sustain-loop
-----------------
Place a clean, seamless FORWARD sustain loop in the steady region of a sustained
sample (organ, strings, pads, brass, choir, analog synth) so that a held note
sustains indefinitely on the target sampler.  The natural companion to
``--trim-tail``: trim the dead tail off a fixed-length autosampler capture, then
loop its sustaining body.  Distinct from ``--single-cycle`` (which collapses a
sample to a tiny one-cycle oscillator); auto-loop keeps the full timbre and its
movement, looping a musically-sized chunk of it.

Pure Python (list + math), reusing the single-cycle DSP — no numpy, no external
dependency.

How it works
============
1. **Steady region.**  Skip the attack and any release/decay using a long-window
   (80 ms) smoothed amplitude envelope, which ignores tremolo/beating dips and
   locates only the real attack-end and release-onset.

2. **Fundamental period.**  Root-note-primed autocorrelation
   (``single_cycle._detect_period`` + ``_refine_period``).  A gross harmonic lock
   (detected pitch > 2 octaves off the root) is treated as a detection failure and
   falls back to the root-note period, so the loop stays integer-periodic.

3. **Adaptive loop length + beat alignment (the "optimal length").**  A tone with
   vibrato / tremolo / detuned-oscillator BEATING must loop a whole number of
   modulation cycles, or the modulation envelope jumps at the seam once per loop —
   an audible rhythmic "ding", even though the waveform splice is click-free.  So
   the candidate loop lengths are integer multiples of the detected modulation
   period (``_modulation``) for a modulated tone, or integer fundamental periods for
   a steady one.  Each candidate's loop-end is a rising zero-crossing near the
   target, chosen to balance splice quality against beat alignment; the LONGEST
   transparent loop is kept, because an evolving tone (strings, ensembles, pads)
   needs length to breathe — a short loop there sounds static even when seamless.  A
   few loop-start candidates are tried so one bad start can't spoil the search.

4. **Seamless splice.**  An equal-power crossfade morphs the last ``xfade`` loop
   samples from the loop-end content into the samples that PRECEDE the loop-start,
   ending exactly on the sample before loop-start.  The wrap loop_end→loop_start
   therefore reproduces a continuous run of the original waveform (no duplicated
   sample, no click — a synth's steep per-period edge included), and the crossfade
   hides the residual timbre difference over the join.  The crossfade can be turned
   OFF (``crossfade=False``) to leave the PCM pristine — loop points only, at the
   zero-crossing / beat-aligned positions — so the loop can be fine-tuned freely in
   the hardware's own loop editor without a baked crossfade locking its position.

Best-effort by design: unpitched / too-short / already-looped samples are left
alone (and reported); inherently hard material (a 20-player detuned string
section never repeats cleanly) still gets a click-free best-effort loop with a
longer crossfade, flagged as a weak match to audition, and can be skipped with a
quality threshold.
"""

import os
import math
import concurrent.futures
from dataclasses import replace
from typing import Optional, Tuple

from models.common import SampleData, LoopType
from processors.resampler import _pcm_to_float, _float_to_pcm
from processors.single_cycle import (
    _sustain_start, _detect_period, _refine_period, _find_rising_zero,
    _midi_to_hz, _note_name, _wav_bytes_with_loop, _safe_filename,
)


# ── Tunables (defaults; the CLI overrides) ───────────────────────────────────
_DEFAULT_MIN_MS   = 150.0    # loop floor (natural sustain; clears the EOS octave bug)
_DEFAULT_MAX_MS   = 2500.0   # loop cap (longer = more organic; more sample RAM)
_DEFAULT_XFADE_MS = 25.0     # crossfade length (grows for poor matches)
_DEFAULT_ACCEPT   = 0.06     # endpoint-cost "transparent" threshold
_RESCUABLE        = 0.45     # pre-crossfade cost the cost-scaled crossfade can hide
                             # (HW-auditioned: a 0.44-cost brass loop sounds seamless)
_LEN_COST_PENALTY_MS = 2000.0  # length/cost trade: a longer loop is preferred, but
                             # only worth ~+200 ms of length per +0.1 of match cost —
                             # so a fast-beating synth goes long (short = repetitive),
                             # yet a clean loop keeps its sweet spot instead of
                             # reaching for a marginally-longer, much-worse-matching one
_DEFAULT_MIN_QUAL = 0.45     # skip (unless forced) only when even the best match is
                             # worse than the crossfade can rescue
_LOWQUAL_FLAG     = 0.44     # advisory "weak match — audition" flag.  The raw cost
                             # badly OVER-predicts badness once the cost-scaled
                             # crossfade is applied — HW audition rated loops up to
                             # cost 0.437 "very good" — so flag ONLY the razor's-edge
                             # kept matches (0.44..0.45, one step from being skipped),
                             # and only as "give it a listen", not "bad".
_MOD_STRENGTH     = 0.30     # amp-modulation autocorr peak to count as "modulated"
_MOD_COV          = 0.05     # amp-envelope coeff-of-variation to count as "modulated"


def _windowed_rms(sig: list, win: int) -> list:
    n = len(sig)
    pre = [0.0] * (n + 1)
    acc = 0.0
    for i in range(n):
        acc += sig[i] * sig[i]
        pre[i + 1] = acc
    return [math.sqrt((pre[f + 1] - pre[max(0, f + 1 - win)])
                      / (f + 1 - max(0, f + 1 - win))) for f in range(n)]


def _steady_region(sig: list, sr: int, region: int) -> Tuple[int, int]:
    """Sustained body [start, end) from a long-window (80 ms) smoothed envelope.

    start = end of the attack.  end = the LAST frame still at sustain level (scanned
    from the tail), so only the final release/decay is excluded — mid-sustain tremolo
    / swell / beating dips (which can be deep on a choir or pad: down to ~40 % of
    peak) do NOT truncate the region.  An earlier "stop at the first dip below 45 %"
    threw away seconds of loopable material on strongly-modulated sustains."""
    n = len(sig)
    env = _windowed_rms(sig, max(1, int(0.08 * sr)))
    peak = max(env) or 1e-9
    start = 0
    for f in range(n):
        if env[f] >= 0.6 * peak:
            start = f
            break
    start = min(start, region)
    thr = 0.35 * peak
    end = start + 1
    for f in range(n - 1, start, -1):
        if env[f] >= thr:
            end = f + 1
            break
    return start, end


def _modulation(sig: list, sr: int, rs: int, re: int) -> Tuple[int, float, float]:
    """Detect a slow amplitude modulation (vibrato / tremolo / detuned-oscillator
    beating) in the sustain.  Returns (period_frames, strength 0..1, cov):
      period_frames — the FUNDAMENTAL modulation period (the beat/vibrato cycle),
                      so an integer multiple of it aligns the envelope at a loop seam;
      strength      — normalised autocorr peak of the low-rate amplitude envelope;
      cov           — the envelope's coefficient of variation.
    period_frames is 0 when no modulation is found."""
    hop = max(1, int(0.002 * sr))
    win = hop * 2
    env = []
    i = rs
    while i + win <= re:
        seg = sig[i:i + win]
        env.append(math.sqrt(sum(x * x for x in seg) / len(seg)))
        i += hop
    n = len(env)
    if n < 8:
        return 0, 0.0, 0.0
    mean = sum(env) / n
    if mean <= 1e-9:
        return 0, 0.0, 0.0
    cov = math.sqrt(sum((e - mean) ** 2 for e in env) / n) / mean
    e = [x - mean for x in env]
    e0 = sum(x * x for x in e) + 1e-12
    env_sr = sr / hop
    lo = max(1, int(env_sr / 25.0))          # 25 Hz
    hi = min(n // 2, int(env_sr / 1.5))       # 1.5 Hz
    if hi <= lo:
        return 0, 0.0, cov
    vals = [sum(e[j] * e[j + lag] for j in range(n - lag)) / e0
            for lag in range(lo, hi + 1)]
    gmax = max(vals)
    if gmax <= 0.0:
        return 0, 0.0, cov
    # FUNDAMENTAL modulation period = the smallest-lag strong local peak (a faster
    # component would appear as a harmonic at a shorter lag; the true beat/vibrato
    # cycle is the one whose integer multiples explain the envelope).
    lagsel = lo + vals.index(gmax)
    for k in range(1, len(vals) - 1):
        if vals[k] >= 0.8 * gmax and vals[k] >= vals[k - 1] and vals[k] >= vals[k + 1]:
            lagsel = lo + k
            break
    return lagsel * hop, gmax, cov


def _match_cost(sig: list, S: int, E: int, w: int) -> float:
    """Normalised SSD between the pre-END window [E-w+1..E] and the pre-START
    window [S-w..S-1] — the two regions the crossfade blends.  Low = transparent."""
    c = e0 = 0.0
    for j in range(w):
        a = sig[E - w + 1 + j]
        b = sig[S - w + j]
        d = a - b
        c += d * d
        e0 += a * a + b * b
    return c / (e0 + 1e-12)


def _find_loop(mono: list, sr: int, root: int, *, target_ms, min_ms, max_ms,
               accept) -> Optional[dict]:
    """Locate (loop_start S, loop_end E, crossfade xf, cost).  Returns None when
    no usable loop can be placed (too short / no period)."""
    n = len(mono)
    region = _sustain_start(mono)
    p_int, conf = _detect_period(mono, region, sr, root)
    if p_int <= 0:
        return None
    if 0 < root < 128:
        det_hz = sr / p_int
        root_hz = _midi_to_hz(root)
        if root_hz > 0 and abs(math.log2(det_hz / root_hz)) > 2.0:
            p_int = max(2, int(round(sr / root_hz)))
            conf *= 0.4
    p = _refine_period(mono, region, p_int)
    rs, re = _steady_region(mono, sr, region)
    pi = int(round(p))
    w = min(int(round(1.5 * p)), 1024)
    if pi < 2 or re - rs < min_ms / 1000.0 * sr + 2 * p + w:
        return None

    # loop-start candidates spread across the early sustain (~every 60 ms), so the
    # search finds a good start at WHATEVER depth: some material matches best right
    # after the attack, bright/evolving material (brass, ensembles) matches far
    # better a few hundred ms in — and a deeper start also leaves more steady audio
    # before loop-start for a long cost-scaled crossfade (which blends the loop end
    # into that pre-roll, so it must be sustain, not the attack transient).
    step = max(pi, int(0.06 * sr))
    Scands = []
    for j in range(8):
        Sc = _find_rising_zero(mono, rs + w + j * step, max(1, pi // 2))
        if (Sc - w >= 0 and re - Sc >= min_ms / 1000.0 * sr + 2 * p + w
                and Sc not in Scands):
            Scands.append(Sc)
    if not Scands:
        return None

    # Modulation drives the candidate lengths.  A tone with vibrato / tremolo /
    # detuned-oscillator BEATING must loop a whole number of modulation cycles, or
    # the beat envelope jumps at every loop point — an audible rhythmic pulse
    # ("ding-ding-ding") even when the waveform splice itself is click-free.
    M, strength, cov = _modulation(mono, sr, rs, re)
    modulated = M > 0 and strength > _MOD_STRENGTH and cov > _MOD_COV
    min_frames = min_ms / 1000.0 * sr
    max_frames = max_ms / 1000.0 * sr
    room = re - max(Scands) - w - 2 * p
    if target_ms:
        targets = [max(1.0, target_ms / 1000.0 * sr)]
    elif modulated:
        # integer multiples of the beat/vibrato period (envelope phase); the E-search
        # + crossfade below handle the waveform phase within each.
        jmin = max(1, int(math.ceil(min_frames / M)))
        jmax = max(jmin, min(int(max_frames / M), int(room / M)))
        js = (list(range(jmin, jmax + 1)) if jmax - jmin <= 24
              else sorted({int(round(jmin + (jmax - jmin) * i / 23)) for i in range(24)}))
        targets = [j * M for j in js]
    else:
        # steady tone: integer-period sweep (fundamental phase + crossfade suffice).
        k_min = max(2, int(round(min_frames / p)))
        k_max = max(k_min, min(int(max_frames / p), int(room / p)))
        ks = (list(range(k_min, k_max + 1)) if k_max - k_min <= 30
              else sorted({int(round(k_min + (k_max - k_min) * i / 29)) for i in range(30)}))
        targets = [k * p for k in ks]

    results = []          # (S, cost, E)
    for S in Scands:
        for T in targets:
            Et = S + int(round(T))
            best_e = None
            # search rising zero-crossings near the target (steady: waveform-phase
            # splice; modulated: also weight toward the EXACT beat multiple so the
            # modulation envelope matches at the seam — otherwise the beat "jumps"
            # once per loop, the audible "ding"). A wider window on modulated gives
            # a choice of zero-crossings to balance splice quality vs beat alignment.
            span = int(p) if modulated else int(p / 2)
            for E in range(Et - span, Et + span + 1):
                if E >= re - 1 or E + 1 >= n or E <= S + pi:
                    continue
                if not (mono[E - 1] < 0.0 <= mono[E]):
                    continue
                cst = _match_cost(mono, S, E, w)
                score = cst + (0.5 * abs(E - Et) / M if modulated else 0.0)
                if best_e is None or score < best_e[0]:
                    best_e = (score, cst, E)
            if best_e:
                results.append((S, best_e[1], best_e[2]))
    if not results:
        return None

    if target_ms:
        results.sort(key=lambda r: r[1])
        S, cost, E = results[0]
    else:
        # Prefer the LONGEST loop the crossfade can rescue.  A longer loop sounds
        # more organic and less repetitive — a SHORT loop sounds "loopy"/static even
        # at a low raw match cost (a fast-beating analog synth or an evolving pad
        # gives itself away every few tenths of a second), which is worse to the ear
        # than a long loop with a slightly-mismatched-but-crossfaded seam.  HW
        # audition confirmed the raw cost over-predicts badness: a 0.44-cost brass
        # loop with a long blend sounds seamless.  So keep the longest whose
        # pre-crossfade cost is within `_RESCUABLE`; fall back to the best match only
        # if nothing qualifies.  RAM-constrained users can force a length with
        # `--auto-loop MS`, or `--auto-loop-min-quality 0` to never skip.
        ok = [r for r in results if r[1] <= _RESCUABLE] or [min(results, key=lambda r: r[1])]
        pen = _LEN_COST_PENALTY_MS / 1000.0 * sr
        S, cost, E = max(ok, key=lambda r: (r[2] - r[0]) - pen * r[1])
    return {'S': S, 'E': E, 'p': p, 'cost': cost, 'conf': conf,
            'modulated': modulated}


def _auto_loop_sample(sample: SampleData, *, target_ms, xfade_ms, min_ms, max_ms,
                      accept, min_quality, force, trim,
                      crossfade=True) -> Tuple[SampleData, dict]:
    """Place a seamless forward sustain loop in one sample.  On any no-op the
    ORIGINAL sample is returned with info['ok'] = False and a reason."""
    ch = max(1, sample.channels)
    frames = (len(sample.data) // 2) // ch
    info = {'ok': False, 'reason': '', 'name': sample.name, 'frames': frames,
            'cost': 0.0, 'conf': 0.0, 'loop': 0, 'lowqual': False, 'trimmed': False}

    already = (sample.loop_type != LoopType.NO_LOOP
               and sample.loop_end > sample.loop_start)
    if already and not force:
        info['reason'] = 'already looped'
        return sample, info

    flat = _pcm_to_float(sample.data)
    mono = ([(flat[i] + flat[i + 1]) * 0.5 for i in range(0, len(flat) - 1, 2)]
            if ch == 2 else flat)

    root = sample.root_note if 0 < sample.root_note < 128 else 60
    res = _find_loop(mono, sample.sample_rate, root, target_ms=target_ms,
                     min_ms=min_ms, max_ms=max_ms, accept=accept)
    if res is None:
        info['reason'] = 'no loop found'
        return sample, info
    S, E, p, cost = res['S'], res['E'], res['p'], res['cost']
    info['cost'] = round(cost, 4)
    info['conf'] = round(res['conf'], 3)
    if cost > min_quality and not force:
        info['reason'] = f'quality {cost:.2f} > {min_quality:.2f}'
        return sample, info

    L = E - S + 1
    out = list(flat)
    xf = 0
    if crossfade:
        # Crossfade length grows with the endpoint mismatch.  A clean loop needs
        # almost none; a poorly-matching one (bright/evolving material — brass,
        # ensembles) needs a long, gradual blend so the timbral seam is MORPHED
        # across time instead of switched at one instant (which reads as an audible
        # "loop end" even though the waveform is click-free).  >= 2 fundamental
        # periods; capped at ~200 ms, the loop length / 3, and the pre-roll.
        xf_ms = min(200.0, xfade_ms + cost * 500.0)
        xf = max(int(round(xf_ms / 1000.0 * sample.sample_rate)), int(2 * p))
        xf = max(1, min(xf, L // 3, S))
        # Apply the equal-power crossfade on EVERY channel (period found on the mono
        # mix; the splice is identical per channel).  Ends exactly on frame S-1 so
        # the wrap E->S is a continuous run of the original waveform.
        for i in range(xf):
            t = i / (xf - 1) if xf > 1 else 1.0
            fo = math.cos(0.5 * math.pi * t)
            fi = math.sin(0.5 * math.pi * t)
            for c in range(ch):
                ie = (E - xf + 1 + i) * ch + c
                isr = (S - xf + i) * ch + c
                out[ie] = fo * flat[ie] + fi * flat[isr]
    # else: leave the PCM PRISTINE — set loop points only, so the loop can be freely
    # fine-tuned on the hardware (E4XT / K2000 loop editors) without a baked crossfade
    # locking it to this position.  The endpoints are already at rising zero-crossings
    # and (for modulated tones) beat-aligned, so the raw seam is decent on its own.

    end_frame = E
    if trim and (E + 1) * ch < len(out):        # drop everything past the loop end
        out = out[:(E + 1) * ch]
        info['trimmed'] = True

    new = replace(sample, data=_float_to_pcm(out), loop_type=LoopType.FORWARD,
                  loop_start=S, loop_end=end_frame)
    info.update(ok=True, loop=L, xf=xf, S=S, E=E,
                lowqual=(cost > _LOWQUAL_FLAG), modulated=res['modulated'])
    return new, info


def _worker(args):
    sample, kw = args
    return _auto_loop_sample(sample, **kw)


def auto_loop_bank(bank, *, target_ms: Optional[float] = None,
                   xfade_ms: float = _DEFAULT_XFADE_MS,
                   min_ms: float = _DEFAULT_MIN_MS, max_ms: float = _DEFAULT_MAX_MS,
                   accept: float = _DEFAULT_ACCEPT,
                   min_quality: float = _DEFAULT_MIN_QUAL,
                   force: bool = False, trim: bool = False, crossfade: bool = True,
                   dump_dir: Optional[str] = None,
                   workers: Optional[int] = None) -> None:
    """Place a seamless forward sustain loop in every sample of `bank` (in place).

    target_ms:   fixed loop length; None = adaptive (longest transparent, beat-aligned).
    xfade_ms:    crossfade length (grows automatically for poor matches).
    min_ms/max_ms: adaptive-length bounds.
    min_quality: skip a sample whose best endpoint cost exceeds this (unless force).
    force:       loop even already-looped / low-quality samples.
    trim:        drop audio after loop_end (saves RAM; the release tail is lost).
    crossfade:   bake a click-free crossfade into the PCM (default); False leaves the
                 PCM pristine (loop points only) for free fine-tuning on hardware.
    dump_dir:    also export each looped sample as a WAV (smpl loop embedded).
    """
    if workers is None:
        workers = max(1, (os.cpu_count() or 2) - 1)
    n = len(bank.samples)
    lbl = 'auto' if target_ms is None else f'{target_ms:g} ms'
    xflbl = f'xfade {xfade_ms:g} ms' if crossfade else 'no crossfade (pristine PCM)'
    print(f"\n  Auto sustain-loop (length: {lbl}, {xflbl}); "
          f"samples: {n}  (workers: {workers})")

    kw = dict(target_ms=target_ms, xfade_ms=xfade_ms, min_ms=min_ms, max_ms=max_ms,
              accept=accept, min_quality=min_quality, force=force, trim=trim,
              crossfade=crossfade)
    results = [None] * n
    if workers == 1 or n <= 1:
        for i, s in enumerate(bank.samples):
            results[i] = _auto_loop_sample(s, **kw)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
            for i, r in enumerate(ex.map(_worker, [(s, kw) for s in bank.samples])):
                results[i] = r

    n_ok = n_low = 0
    dumped = set()
    for i, (new_s, info) in enumerate(results):
        bank.samples[i] = new_s
        if info['ok']:
            n_ok += 1
            sr = new_s.sample_rate or 1
            flag = ''
            if info['lowqual']:
                n_low += 1
                flag = '  [weak match — audition]'
            kind = 'mod' if info.get('modulated') else 'steady'
            trimmed = ', trimmed' if info['trimmed'] else ''
            print(f"    '{info['name']}': loop {info['loop']}f "
                  f"({info['loop'] / sr * 1000:.0f} ms, {kind}{trimmed}), "
                  f"match {info['cost']:.3f}, xfade {info['xf']}f{flag}")
        else:
            print(f"    '{info['name']}': skipped ({info['reason']})")
        if dump_dir and info['ok']:
            _dump_loop(new_s, dump_dir, dumped)

    print(f"  Done: {n_ok}/{n} sample(s) looped"
          + (f", {n_low} weak-match (audition)" if n_low else "")
          + f"; {n - n_ok} left unlooped.")


def _dump_loop(sample: SampleData, dump_dir: str, seen: set) -> None:
    """Export one looped sample as an import-ready WAV (embedded `smpl` loop +
    root note), so the loop can be auditioned in Audacity / a player / another
    sampler without going through a bank writer."""
    os.makedirs(dump_dir, exist_ok=True)
    stem = _safe_filename(sample.name)
    if 0 <= sample.root_note <= 127:
        stem += '_' + _safe_filename(_note_name(sample.root_note))
    base, k = stem, 1
    while stem.lower() in seen:
        k += 1
        stem = f'{base}_{k}'
    seen.add(stem.lower())
    with open(os.path.join(dump_dir, stem + '.wav'), 'wb') as f:
        f.write(_wav_bytes_with_loop(sample))
