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
Single-cycle oscillator extraction
-----------------------------------
Replace each sample with a short, cleanly-looped slice of its own waveform
(one cycle, or a few), so the sampler plays it as a static *oscillator* and the
instrument becomes a synth voice driven by the hardware's own filter/envelope/
LFO.  A whole multisampled instrument collapses to a handful of tiny loops
(hundreds of bytes each) — the most extreme form of the project's "fit into
vintage RAM" goal, and a creative mode in its own right: MPC multisample →
E4XT / K2000 synth patch.

Two separable jobs:

  (A) Per-sample audio transform — locate the steady-state sustain, detect the
      fundamental period by autocorrelation to SUB-SAMPLE precision (using the
      sample's own root note as a pitch prior so we don't lock to the wrong
      octave), resample exactly one period (auto) — or N periods (=N) — to an
      integer frame count so the loop wrap is phase-perfect, TILE that seamless
      cycle to clear the hardware minimum loop length, front-pad so the loop
      never starts at frame 0 (an old EMU requirement), and bake the pitch into
      the stored sample RATE so it plays in tune (E4B carries only one fine-tune
      per voice, so a per-zone cents field can't tune shared samples).

  (B) Per-voice preset neutralisation — unless the caller keeps them, overwrite
      the voice's synth params with a neutral template: 4-pole lowpass wide open
      (XPM filter_type 3 → E4B 0x00 / K2000 Alg-1 4POLE LOPASS), organ-style amp
      envelope, default filter envelope, no LFO / mod.  The keep_* flags let the
      already-converted source filter / LFO / amp-env pass through instead.

This is best-effort by design: on unpitched or noisy material the extraction
still produces a (possibly weird) oscillator rather than failing — pitched
sources give clean results, and every sample's detection confidence is logged.

Pure Python (array + math), matching the rest of the DSP here — no numpy.
"""

import os
import math
import wave
import concurrent.futures
from dataclasses import replace
from typing import Optional, Tuple

from models.common import SampleData, LoopType, Envelope
from processors.resampler import _pcm_to_float, _float_to_pcm


# ── Tunables ───────────────────────────────────────────────────────────────
_FILTER_TYPE_4PLP  = 3        # XPM "Low 4" → E4B 0x00 (4-Pole LP) / K2000 Alg-1 4POLE LOPASS
_PAD_FRAMES        = 8        # silent-ish lead-in so loop_start >= 1 (EMU caveat)
_MAX_CYCLES        = 128      # upper bound on cycle count (only reachable via =N)
# EOS/E4XT (HW-confirmed) mishandles ultra-short loops: a ~42-frame loop plays an
# OCTAVE LOW (the loop is silently doubled), while an 84-frame loop is fine.  So
# high notes — whose single cycle is only tens of frames — TILE the seamless
# cycle until the loop clears this minimum.  Identical repeats keep the pitch and
# the single-cycle timbre; they just make the loop long enough for the hardware.
# 256 sits comfortably above the known-good 84.
_MIN_LOOP_FRAMES   = 256
_MIN_HZ            = 30.0     # pitch-search floor
_MAX_HZ            = 2000.0   # pitch-search ceiling

# Organ-style amp envelope: instant on, full sustain while held, quick release.
_ORGAN_AMP_ENV     = (0.0, 0.0, 1.0, 0.005)   # attack, decay, sustain, release


def _midi_to_hz(n: float) -> float:
    return 440.0 * (2.0 ** ((n - 69) / 12.0))


def _nearest_note(hz: float) -> int:
    """Nearest MIDI note (0..127) to a frequency."""
    if hz <= 0:
        return 60
    return max(0, min(127, int(round(69.0 + 12.0 * math.log2(hz / 440.0)))))


def _sustain_start(sig: list, frame: int = 512, hop: int = 256) -> int:
    """Sample index of the highest short-time-RMS window (past the attack)."""
    n = len(sig)
    if n < frame * 2:
        return 0
    best = -1.0
    best_i = 0
    st = 0
    while st + frame <= n:
        s = 0.0
        for x in sig[st:st + frame]:
            s += x * x
        if s > best:
            best = s
            best_i = st
        st += hop
    return best_i


def _autocorr_vals(seg: list, lo: int, hi: int, compare_len: int) -> list:
    """Normalised autocorrelation for each lag in [lo, hi] (index k → lag lo+k).

    `compare_len` caps the number of products per lag so a wide low-note search
    stays affordable in pure Python.
    """
    w = len(seg)
    vals = []
    for lag in range(lo, hi + 1):
        m = min(w - lag, compare_len)
        if m <= 0:
            vals.append(0.0)
            continue
        s = e0 = e1 = 0.0
        for i in range(m):
            a = seg[i]
            b = seg[i + lag]
            s += a * b
            e0 += a * a
            e1 += b * b
        denom = math.sqrt(e0 * e1)
        vals.append(s / denom if denom > 0.0 else 0.0)
    return vals


def _period_global_max(seg: list, lo: int, hi: int, compare_len: int) -> Tuple[int, float]:
    """Lag of the single strongest correlation in [lo, hi] (for the narrow,
    prior-guided search, where the range is already ±a few semitones)."""
    vals = _autocorr_vals(seg, lo, hi, compare_len)
    if not vals:
        return 0, 0.0
    k = max(range(len(vals)), key=lambda i: vals[i])
    return lo + k, vals[k]


def _period_first_peak(seg: list, lo: int, hi: int, compare_len: int,
                       thresh: float = 0.8) -> Tuple[int, float]:
    """Smallest-lag strong local peak in [lo, hi] — the FUNDAMENTAL, not one of
    its autocorrelation multiples (2p, 3p… all correlate strongly).  Used for the
    wide fallback when the root-note prior is missing or wrong."""
    vals = _autocorr_vals(seg, lo, hi, compare_len)
    if not vals:
        return 0, 0.0
    gmax = max(vals)
    if gmax <= 0.0:
        return 0, 0.0
    target = thresh * gmax
    for i in range(1, len(vals) - 1):
        if vals[i] >= target and vals[i] >= vals[i - 1] and vals[i] >= vals[i + 1]:
            return lo + i, vals[i]
    k = max(range(len(vals)), key=lambda i: vals[i])
    return lo + k, vals[k]


def _detect_period(sig: list, region: int, sr: int, root0: int) -> Tuple[int, float]:
    """Fundamental period (frames) + confidence.

    Primary: a narrow autocorrelation search around the period implied by the
    sample's root note (fast, and immune to octave errors).  Fallback: a wide
    first-strong-peak search when the prior yields nothing convincing (missing or
    wrong root metadata) — best-effort, so we still return a period.
    """
    n = len(sig)
    min_lag = max(2, int(sr / _MAX_HZ))
    max_lag = min(n // 2, int(sr / _MIN_HZ))
    if max_lag <= min_lag:
        return 0, 0.0

    # Narrow, prior-guided (±~4 semitones around the declared root).
    exp = sr / _midi_to_hz(root0)
    lo = max(min_lag, int(exp / 1.3))
    hi = min(max_lag, int(exp * 1.3))
    if hi > lo:
        seg = sig[region:region + min(n - region, hi * 3)]
        if len(seg) >= lo * 2:
            p, c = _period_global_max(seg, lo, min(hi, len(seg) // 2), 4096)
            if c >= 0.5:                           # prior + any real periodicity
                return p, c

    # Wide fallback.
    seg = sig[region:region + min(n - region, max_lag * 2 + 2048)]
    if len(seg) < min_lag * 2:
        seg = sig[:min(n, max_lag * 2 + 2048)]
    hi2 = min(max_lag, len(seg) // 2)
    if hi2 <= min_lag:
        return 0, 0.0
    return _period_first_peak(seg, min_lag, hi2, 2048)


def _refine_period(sig: list, region: int, p: int) -> float:
    """Sub-sample period via parabolic interpolation of the autocorrelation peak.

    An integer-sample cut leaves a fractional-sample phase error at the loop wrap;
    on a short (high-note) cycle that step is big enough to add harsh broadband
    high-frequency content.  Refining the period lets us resample to an EXACT
    whole number of periods so the wrap is phase-perfect.
    """
    if p < 2:
        return float(p)
    seg = sig[region:region + min(len(sig) - region, p * 3 + 2)]
    if len(seg) <= p + 2:
        return float(p)
    v = _autocorr_vals(seg, p - 1, p + 1, 4096)       # lags p-1, p, p+1
    if len(v) < 3:
        return float(p)
    denom = v[0] - 2.0 * v[1] + v[2]
    if denom == 0.0:
        return float(p)
    delta = max(-0.5, min(0.5, 0.5 * (v[0] - v[2]) / denom))
    return p + delta


def _find_rising_zero(sig: list, near: int, search: int) -> int:
    """Nearest rising zero-crossing (neg→non-neg) to `near`, within ±search."""
    n = len(sig)
    near = max(1, min(n - 1, int(near)))
    for off in range(0, search + 1):
        for idx in (near + off, near - off):
            if 1 <= idx < n and sig[idx - 1] < 0.0 <= sig[idx]:
                return idx
    return near


def _single_cycle_sample(sample: SampleData, cycles) -> Tuple[SampleData, dict]:
    """Transform one sample into a looped single/multi-cycle oscillator.

    Returns (new_or_original_sample, info).  On any failure the ORIGINAL sample
    is returned with info['ok'] = False and a reason (best-effort: the preset is
    still neutralised, the sample just isn't shortened).
    """
    info = {'ok': False, 'reason': '', 'name': sample.name,
            'period': 0, 'conf': 0.0, 'n': 0, 'loop': 0,
            'orig_frames': len(sample.data) // 2,
            'root': sample.root_note, 'cents': 0}

    sig = _pcm_to_float(sample.data)
    if sample.channels == 2:                       # defensive downmix to mono
        sig = [(sig[i] + sig[i + 1]) * 0.5 for i in range(0, len(sig) - 1, 2)]
    n = len(sig)
    sr = sample.sample_rate
    if n < 64:
        info['reason'] = 'too short'
        return sample, info

    # Detect the fundamental period, using the sample's own root note as a
    # prior (the converter already trusts it for tuning), with a wide fallback.
    region = _sustain_start(sig)
    root0 = sample.root_note if 0 < sample.root_note < 128 else 60
    p, conf = _detect_period(sig, region, sr, root0)
    if p <= 0:
        info['reason'] = 'no period found'
        return sample, info

    # Cycle count.
    # Musical loop = whole periods.  auto = ONE clean cycle (the truest, cleanest
    # oscillator); an explicit =N takes N contiguous periods for users who want
    # the source's cycle-to-cycle movement.
    n_cyc = 1 if cycles == 'auto' else max(1, int(cycles))

    # Sub-sample period, then resample EXACTLY n_cyc periods to an integer frame
    # count.  Because the span is phase-locked to a whole number of periods,
    # base[base_len] == base[0] by periodicity, so the loop wrap is phase-perfect
    # — no fractional-sample step, hence none of the broadband HF ("harshness")
    # that an integer-sample cut leaves on short high-note cycles.
    p_float = _refine_period(sig, region, p)
    s0 = _find_rising_zero(sig, region, p)
    span = n_cyc * p_float
    base_len = int(round(span))
    if base_len < 2 or s0 + span + 2.0 >= n:
        info['reason'] = 'no loop endpoint'
        return sample, info
    step = span / base_len
    base = []
    for k in range(base_len):
        pos = s0 + k * step
        i = int(pos)
        base.append(sig[i] + (sig[i + 1] - sig[i]) * (pos - i))

    # Pitch is the true (sub-sample) fundamental; tiling below doesn't change it.
    f_fund = sr / p_float

    # Reach the hardware minimum loop length by TILING the (seamless single-period)
    # base loop: identical repeats, so no cycle-to-cycle drift and no seam buzz,
    # and it clears the E4XT minimum-loop threshold (a loop < ~84 frames plays an
    # octave low).
    reps = max(1, -(-_MIN_LOOP_FRAMES // base_len))
    loopf = base * reps
    loop_len = len(loopf)

    pad = min(_PAD_FRAMES, loop_len)
    lead = [loopf[i] * (i / pad) for i in range(pad)] if pad > 0 else []
    out = lead + loopf

    loop_start = pad
    loop_end = pad + loop_len - 1                   # inclusive (codebase convention)
    root = _nearest_note(f_fund)
    # Bake the sub-semitone correction into the stored sample RATE rather than a
    # cents field: playback pitch scales with the stored rate, so rate =
    # sr·freq(root)/f_fund makes the loop play exactly freq(root) at the root key.
    # This is per-SAMPLE and near-exact (integer-Hz rounding ≈ 0.04 c near 44 kHz),
    # whereas E4B carries only ONE fine-tune per voice — a per-zone cents field
    # cannot tune each sample in a shared voice.
    new_rate = int(round(sr * _midi_to_hz(root) / f_fund))
    achieved = f_fund * new_rate / sr
    residual = int(round(1200 * math.log2(achieved / _midi_to_hz(root)))) if achieved > 0 else 0

    new = replace(
        sample,
        data=_float_to_pcm(out),
        sample_rate=new_rate,
        channels=1,
        loop_type=LoopType.FORWARD,
        loop_start=loop_start,
        loop_end=loop_end,
        root_note=root,
        fine_tune=0,
    )
    info.update(ok=True, reason='', period=p, conf=round(conf, 3),
                n=n_cyc, reps=reps, loop=loop_len, root=root, cents=residual,
                rate=new_rate)
    return new, info


def _sc_worker(args):
    """Top-level worker so ProcessPoolExecutor can pickle it."""
    sample, cycles = args
    return _single_cycle_sample(sample, cycles)


def _neutralize_voice(v, keep_flt: bool, keep_lfo: bool, keep_amp: bool) -> None:
    """Overwrite a voice's synth params with the neutral single-cycle template,
    honouring the keep_* opt-outs (see module docstring)."""
    if not keep_flt:
        v.filter_type = _FILTER_TYPE_4PLP
        v.filter_cutoff = 1.0
        v.filter_resonance = 0.0
        v.filter_env_amount = 0.0
        v.filter_keytrack = 0.0
        v.velocity_to_filter = 0.0
        v.filter_env = Envelope(0.0, 0.3, 1.0, 0.0)
    if not keep_amp:
        v.amp_env = Envelope(*_ORGAN_AMP_ENV)
    if not keep_lfo:
        for a in ('lfo1_rate', 'lfo1_shape', 'lfo1_delay', 'lfo1_variation',
                  'lfo1_sync', 'lfo1_sync_division',
                  'lfo2_rate', 'lfo2_shape', 'lfo2_delay', 'lfo2_variation',
                  'lfo2_sync'):
            setattr(v, a, None)
        for a in ('lfo1_to_pitch', 'lfo1_to_filter', 'lfo1_to_filter_q',
                  'lfo2_to_pitch', 'lfo2_to_filter', 'lfo2_to_filter_q',
                  'wheel_to_lfo', 'chorus_amount'):
            setattr(v, a, 0.0)


def _safe_filename(name: str) -> str:
    keep = [c if (c.isalnum() or c in '-_') else '_' for c in name]
    return ''.join(keep) or 'cycle'


def _dump_cycle(sample: SampleData, dump_dir: str) -> None:
    os.makedirs(dump_dir, exist_ok=True)
    path = os.path.join(dump_dir, _safe_filename(sample.name) + '.wav')
    w = wave.open(path, 'wb')
    try:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample.sample_rate)
        w.writeframes(sample.data)
    finally:
        w.close()


def single_cycle_bank(bank, *, cycles='auto',
                      keep_flt: bool = False, keep_lfo: bool = False,
                      keep_amp: bool = False, dump_dir: Optional[str] = None,
                      workers: Optional[int] = None) -> None:
    """Extract single/multi-cycle oscillators for every sample in `bank`
    (in place) and neutralise every voice's preset params.

    cycles:  'auto' (per-sample) or a positive int N.
    keep_*:  leave the source filter / LFO / amp-env instead of templating it.
    dump_dir: if set, write each extracted cycle as a .wav for audition.
    """
    if workers is None:
        workers = max(1, (os.cpu_count() or 2) - 1)

    n = len(bank.samples)
    label = 'auto' if cycles == 'auto' else f'{cycles} cycle(s)'
    print(f"\n  Single-cycle extraction ({label}); samples: {n}  (workers: {workers})")

    args = [(s, cycles) for s in bank.samples]
    results = [None] * n
    if workers == 1 or n <= 1:
        for i, s in enumerate(bank.samples):
            results[i] = _single_cycle_sample(s, cycles)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
            for i, r in enumerate(ex.map(_sc_worker, args)):
                results[i] = r

    # Apply transformed samples, collect per-name retuning, report.
    tune = {}
    n_ok = 0
    n_low = 0
    for i, (new_s, info) in enumerate(results):
        bank.samples[i] = new_s
        if info['ok']:
            n_ok += 1
            tune[new_s.name] = new_s.root_note
            shrink = (100.0 * (1 - info['loop'] / info['orig_frames'])
                      if info['orig_frames'] else 0.0)
            flag = ''
            if info['conf'] < 0.7:
                n_low += 1
                flag = '  [LOW CONFIDENCE — audition]'
            note = _NOTE_NAMES[info['root'] % 12] + str(info['root'] // 12 - 1)
            print(f"    '{info['name']}': {info['n']}cyc×{info['reps']} = "
                  f"{info['loop']}f loop (-{shrink:.1f}%), root {note} @ "
                  f"{info['rate']}Hz ({info['cents']:+d}c), "
                  f"conf {info['conf']:.2f}{flag}")
        else:
            print(f"    '{info['name']}': SKIPPED ({info['reason']}) — left full-length")
        if dump_dir and info['ok']:
            _dump_cycle(new_s, dump_dir)

    # Retune the zones that reference a transformed sample, and neutralise voices.
    for preset in bank.presets:
        for voice in preset.voices:
            for z in voice.zones:
                if z.sample_name in tune:
                    z.root_key = tune[z.sample_name]
                    z.fine_tune = 0        # tuning is baked into the sample rate
                    z.coarse_tune = 0
                    z.transpose = 0
            _neutralize_voice(voice, keep_flt, keep_lfo, keep_amp)

    kept = 'kept source' if (keep_flt and keep_lfo and keep_amp) else 'neutral synth preset'
    print(f"  Done: {n_ok}/{n} sample(s) cycled"
          + (f", {n_low} low-confidence" if n_low else "")
          + f"; {kept}.")


_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
