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
Tail trimming
-------------
Cleanly remove the decaying tail + trailing silence at the END of a sample.

Autosamplers (MPC ONE Autosampler, Kontakt auto-sample, …) record every note
for a FIXED duration — e.g. the MPC pads each capture to a flat 4 s — so a note
that speaks for ~2 s is followed by its natural release, then a long stretch of
pure digital silence.  That dead tail wastes vintage sampler RAM and, when the
hardware's own amp-envelope release is doing the work, is not wanted in the
sample at all.

The transform walks BACKWARD from the end to find the last frame whose level
(max across channels) exceeds a threshold set relative to the sample's own peak,
cuts just after it, and applies a short linear fade-out ending exactly at the new
end so the cut is click-free.  It is loop-safe: a forward loop is never truncated
(the cut is clamped to loop_end).  Best-effort — a silent or all-loud sample is
left untouched and reported.

Pure Python (array + math), matching the rest of the DSP here — no numpy.
"""

import math
from dataclasses import replace
from typing import Optional, Tuple

from models.common import SampleData, LoopType
from processors.resampler import _pcm_to_float, _float_to_pcm


# ── Defaults ────────────────────────────────────────────────────────────────
# "Silence only": the cut is driven by where the signal decays into its OWN
# noise floor, not a fixed line — real recordings sit on an analog/dither floor
# (these MPC captures ~-66 dB below peak), so a fixed "-72 dB below peak" would
# fall UNDER the floor and trim nothing.  Two thresholds are combined and the
# cut is the last window above EITHER:
#   • floor-relative (default, "silence only"): floor + _DEFAULT_FLOOR_MARGIN_DB,
#     so we cut exactly where audible decay meets the noise floor, whatever its
#     level.
#   • peak-relative (thresh_db): a ceiling "this far below peak" that only binds
#     when set high (e.g. -45) to deliberately cut INTO the natural release.
_DEFAULT_THRESH_DB       = -72.0   # dB below peak RMS; deep = floor term governs
_DEFAULT_FLOOR_MARGIN_DB = 6.0     # cut where RMS falls to floor + this
_DEFAULT_FADE_MS         = 5.0     # click-avoiding fade-out length
_DEFAULT_RMS_MS          = 20.0    # short-time RMS window for tail detection
_FLOOR_PERCENTILE        = 0.10    # noise-floor estimate = 10th-pct window RMS
_MIN_KEEP_FRAMES         = 32      # never trim a sample shorter than this


def _frame_energy(sig: list, channels: int) -> Tuple[list, int]:
    """Per-frame energy = mean square across the interleaved channels.

    Returns (energy, n_frames).  `sig` is the flat float stream from
    `_pcm_to_float` (mono: one value per frame; stereo: L,R,L,R…).
    """
    if channels <= 1:
        return [x * x for x in sig], len(sig)
    n = len(sig) // channels
    e = [0.0] * n
    for f in range(n):
        base = f * channels
        s = 0.0
        for c in range(channels):
            a = sig[base + c]
            s += a * a
        e[f] = s / channels
    return e, n


def _tail_cut_frame(energy: list, n: int, win: int, thresh_db: float,
                    floor_margin_db: float) -> int:
    """Frame index one past the last short-time-RMS window that counts as signal.

    A sliding-window RMS (prefix sums, O(n)) is used instead of per-sample level
    so the dithered noise floor — whose individual samples spike well above a raw
    dB line — does not read as "signal" and defeat the trim.

    A window counts as signal if its RMS exceeds EITHER threshold:
      • floor + `floor_margin_db`  — where audible decay meets the sample's own
        noise floor (estimated as the 10th-percentile window RMS), so "silence
        only" adapts to each recording's floor level;
      • peak − |`thresh_db`|      — a fixed ceiling below peak that only bites
        when set high, to cut deliberately into the natural release.
    Returns n when nothing is below both (nothing to cut).
    """
    win = max(1, min(win, n))
    # prefix[k] = sum(energy[0:k]); windowed mean-square over [f-win+1, f].
    prefix = [0.0] * (n + 1)
    acc = 0.0
    for f in range(n):
        acc += energy[f]
        prefix[f + 1] = acc
    ms = [0.0] * n
    peak_ms = 0.0
    for f in range(n):
        lo = f + 1 - win
        if lo < 0:
            lo = 0
        m = (prefix[f + 1] - prefix[lo]) / (f + 1 - lo)
        ms[f] = m
        if m > peak_ms:
            peak_ms = m
    if peak_ms <= 0.0:
        return n

    # Noise floor = low percentile of window energy (robust to the loud body).
    floor_ms = sorted(ms)[min(n - 1, int(_FLOOR_PERCENTILE * n))]
    thr_peak  = peak_ms * (10.0 ** (thresh_db / 10.0))         # power ratio → /10
    thr_floor = floor_ms * (10.0 ** (floor_margin_db / 10.0)) if floor_ms > 0 else 0.0
    thresh_ms = max(thr_peak, thr_floor)
    for f in range(n - 1, -1, -1):
        if ms[f] > thresh_ms:
            return f + 1
    return n


def _trim_tail_sample(sample: SampleData, thresh_db: float, fade_ms: float,
                      rms_ms: float = _DEFAULT_RMS_MS,
                      drop_full_loop: bool = True,
                      floor_margin_db: float = _DEFAULT_FLOOR_MARGIN_DB
                      ) -> Tuple[SampleData, dict]:
    """Trim the trailing tail/silence of one sample.

    Returns (new_or_original_sample, info).  On any no-op the ORIGINAL sample is
    returned with info['trimmed'] = False and a reason.

    Loop handling — a real sustain loop wholly inside the kept audio is never
    touched (the cut only ever lands after it).  A loop whose end sits inside the
    tail we are removing is a *full-length / default* loop (autosamplers write one
    spanning the whole take); with `drop_full_loop` it is discarded so the trimmed
    sample is a clean one-shot, otherwise the trim is skipped to preserve it.
    """
    channels = max(1, sample.channels)
    info = {'trimmed': False, 'reason': '', 'name': sample.name,
            'orig_frames': (len(sample.data) // 2) // channels,
            'new_frames': 0, 'cut_frames': 0, 'loop_dropped': False}

    sig = _pcm_to_float(sample.data)
    energy, n = _frame_energy(sig, channels)
    info['orig_frames'] = n
    if n <= _MIN_KEEP_FRAMES:
        info['reason'] = 'too short'
        return sample, info

    win = max(1, int(round(rms_ms / 1000.0 * sample.sample_rate)))
    cut = _tail_cut_frame(energy, n, win, thresh_db, floor_margin_db)
    if cut <= 0:
        info['reason'] = 'silent'
        return sample, info

    # Loop handling (see docstring).
    has_loop = (sample.loop_type != LoopType.NO_LOOP
                and sample.loop_end > sample.loop_start)
    drop_loop = False
    if has_loop and sample.loop_end + 1 > cut:
        # The loop extends into the region we would trim.
        if drop_full_loop:
            drop_loop = True                       # discard the full-length loop
        else:
            cut = sample.loop_end + 1              # protect it: keep past loop_end
            info['loop_guarded'] = True

    cut = max(cut, _MIN_KEEP_FRAMES)
    if cut >= n:
        info['reason'] = 'nothing to trim'
        return sample, info

    # Fade the last `fade` frames of the KEPT region down to zero so the new end
    # is click-free regardless of where the cut lands.
    fade = int(round(fade_ms / 1000.0 * sample.sample_rate))
    fade = max(1, min(fade, cut - 1))
    out = sig[:cut * channels]
    for i in range(fade):
        g = (fade - i) / fade                      # 1.0 → ~0.0 across the fade
        base = (cut - fade + i) * channels
        for c in range(channels):
            out[base + c] *= g

    if drop_loop:
        new = replace(sample, data=_float_to_pcm(out),
                      loop_type=LoopType.NO_LOOP, loop_start=0, loop_end=0)
        info['loop_dropped'] = True
    else:
        new = replace(sample, data=_float_to_pcm(out))
    info.update(trimmed=True, new_frames=cut, cut_frames=n - cut)
    return new, info


def trim_tail_bank(bank, *, thresh_db: float = _DEFAULT_THRESH_DB,
                   fade_ms: float = _DEFAULT_FADE_MS,
                   rms_ms: float = _DEFAULT_RMS_MS,
                   drop_full_loop: bool = True) -> None:
    """Trim the trailing tail/silence of every sample in `bank` (in place).

    thresh_db:  cut point is just after the last short-time-RMS window louder
                than this many dB below the sample's own peak RMS (default -60).
                Higher (e.g. -40) trims deeper into the natural release; lower
                (e.g. -72) keeps more of it and removes mostly dead silence.
    fade_ms:    click-avoiding fade-out ending at the new sample end.
    rms_ms:     short-time RMS window used to detect the tail (default 20 ms).
    drop_full_loop:  when a sample's loop spans into the trimmed tail (a
                autosampler whole-take loop), discard it (True) so the result is
                a clean one-shot, or preserve it by not trimming (False).
    """
    n = len(bank.samples)
    print(f"\n  Tail trim (threshold {thresh_db:g} dB below peak RMS, "
          f"fade {fade_ms:g} ms); samples: {n}")

    n_trim = n_drop = 0
    saved_frames = 0
    for i, s in enumerate(bank.samples):
        new_s, info = _trim_tail_sample(s, thresh_db, fade_ms, rms_ms,
                                        drop_full_loop)
        bank.samples[i] = new_s
        if info['trimmed']:
            n_trim += 1
            saved_frames += info['cut_frames']
            sr = new_s.sample_rate or 1
            shrink = (100.0 * info['cut_frames'] / info['orig_frames']
                      if info['orig_frames'] else 0.0)
            drop = '  [loop dropped]' if info['loop_dropped'] else (
                   '  [loop kept]' if info.get('loop_guarded') else '')
            if info['loop_dropped']:
                n_drop += 1
            print(f"    '{info['name']}': {info['orig_frames']} → "
                  f"{info['new_frames']} f  (-{shrink:.1f}%, "
                  f"cut {info['cut_frames'] / sr:.2f}s){drop}")
        elif info['reason'] not in ('nothing to trim',):
            print(f"    '{info['name']}': kept ({info['reason']})")

    # A representative rate for the aggregate seconds figure (samples may differ).
    rate = bank.samples[0].sample_rate if bank.samples else 44100
    print(f"  Done: trimmed {n_trim}/{n} sample(s); "
          f"removed ~{saved_frames / (rate or 1):.1f}s of tail total"
          + (f"; dropped {n_drop} full-length loop(s)." if n_drop else "."))
