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
Start trimming
---------------
Cleanly remove leading silence at the START of a sample.

The MPC ONE Autosampler's "Auto Trim Start" only moves the pad's playback
start MARKER in the MPC's own project — it does not cut the captured WAV
data itself. Once the sample is exported as a bare WAV (which is all an XPM
program actually references), that marker is gone and the audible lead-in
silence is back. The companion to `processors.tail_trim` — same detector,
opposite end.

The transform walks FORWARD from the start to find the first frame whose
level (max across channels) exceeds a threshold set relative to the
sample's own peak, cuts everything before it, and applies a short linear
fade-in over the first kept frames so the cut is click-free. It is
loop-safe: a loop that starts inside the region being cut is either dropped
(the common autosampler whole-take default) or protected, mirroring
`tail_trim`'s handling of a loop that ends inside the trimmed tail — see
`drop_full_loop`. Best-effort — a silent or immediately-loud sample is left
untouched and reported.

Pure Python (array + math), matching the rest of the DSP here — no numpy.
"""

from dataclasses import replace
from typing import Tuple

from models.common import SampleData, LoopType
from processors.resampler import _pcm_to_float, _float_to_pcm
from processors.tail_trim import (_frame_energy, _windowed_ms, _signal_threshold,
                                  _FLOOR_PERCENTILE)


# ── Defaults ────────────────────────────────────────────────────────────────
# Same "silence only" philosophy as tail_trim: the cut is driven by where the
# signal first rises out of the sample's own noise floor, not a fixed line.
_DEFAULT_THRESH_DB       = -72.0   # dB below peak RMS; deep = floor term governs
_DEFAULT_FLOOR_MARGIN_DB = 6.0     # cut where RMS rises above floor + this
_DEFAULT_FADE_MS         = 5.0     # click-avoiding fade-in length
_DEFAULT_RMS_MS          = 20.0    # coarse short-time RMS window: robust onset region
_REFINE_RMS_MS           = 3.0     # fine window: precise onset localization within it
_LEAD_FRACTION           = 0.10    # floor is estimated over the LEADING this-much
                                   # of the sample -- see _start_cut_frame
_MIN_KEEP_FRAMES         = 32      # never trim a sample shorter than this


def _start_cut_frame(energy: list, n: int, win: int, thresh_db: float,
                     floor_margin_db: float, refine_win: int = 1) -> int:
    """Frame index of the true onset — the first sample where the signal
    counts as louder than the noise floor.

    Two stages, both sharing `_windowed_ms`/`_signal_threshold` with
    `tail_trim._tail_cut_frame` (same detector, opposite intent):

    1. COARSE — a `win`-length window robustly finds the region where the
       signal first rises out of the noise floor. A window this long rejects
       a single noisy dither sample deciding the outcome on its own; critically,
       `_windowed_ms` shrinks the window for frames near the very start (there's
       no history yet), so a lone noise spike right at frame 0 gets read as its
       OWN 1-sample "window" — plenty to spuriously exceed the threshold and
       return cut=0, defeating the whole trim. Starting the coarse scan only
       once a FULL window is available (`f >= win-1`) closes that hole.
    2. REFINE — the coarse window `[coarse-win+1, coarse]` only bounds the
       onset; it doesn't locate it; backing off by the *entire* coarse window
       overshoots by the same margin every time (real-world MPC ONE Autosampler
       captures: a consistent ~20 ms of extra kept silence, i.e. exactly the
       default coarse window — these are fast synth/percussive attacks, not
       gradual swells, so the windowed average only crosses the threshold once
       the transient is already most of the way through the window). A short
       `refine_win`-length re-scan of just that bounded region localizes the
       true onset precisely, at the same absolute threshold.

    Returns 0 when nothing exceeds the threshold anywhere (nothing to cut).
    """
    ms, peak_ms, floor_ms = _windowed_ms(energy, n, win)
    if peak_ms <= 0.0:
        return 0

    # `_windowed_ms` estimates the floor as a PERCENTILE over the WHOLE sample,
    # chosen to be robust to the loud body. That is right for tail-trim, where
    # the quiet part really is the noise floor -- and wrong here for a gradual
    # attack, where the quiet part IS the signal. On a 3 s linear swell the
    # whole-sample percentile read -20.6 dB instead of digital silence, so
    # `_signal_threshold` took the floor branch (-14.6 dB) over the intended
    # peak-72 dB (-78.4 dB) and cut 1.16 s into the attack.
    #
    # For START trim the floor that matters is the LEAD-IN, so estimate it over
    # the leading `_LEAD_FRACTION` of the sample only. Both cases then behave:
    # a real capture's lead-in silence still dominates that region's low
    # percentile, so the adaptive floor is unchanged; a swell's leading tenth is
    # its own quietest part, so the floor stays near silence and the intended
    # peak-relative threshold decides instead.
    #
    # Taking the MINIMUM windowed energy instead was tried and measured
    # FAILING: it fixes the swell but drops the real autosampler corpus from
    # trimming 21/21 samples to 8/21, because real captures usually contain one
    # genuinely silent window which zeroes the floor and disables the adaptive
    # branch altogether.
    lead_n = max(win, int(n * _LEAD_FRACTION))
    lead = sorted(ms[:lead_n])
    lead_floor = lead[min(len(lead) - 1, int(_FLOOR_PERCENTILE * len(lead)))] if lead else floor_ms
    thresh_ms = _signal_threshold(peak_ms, min(floor_ms, lead_floor),
                                  thresh_db, floor_margin_db)

    coarse = None
    for f in range(min(win - 1, n - 1), n):
        if ms[f] > thresh_ms:
            coarse = f
            break
    if coarse is None:
        return 0

    lo = max(0, coarse - win + 1)
    rwin = max(1, min(refine_win, coarse + 1 - lo))
    sub_n = coarse + 1 - lo
    r_ms, _, _ = _windowed_ms(energy[lo:coarse + 1], sub_n, rwin)
    for i in range(min(rwin - 1, sub_n - 1), sub_n):
        if r_ms[i] > thresh_ms:
            return lo + max(0, i - rwin + 1)
    return lo


def _trim_start_sample(sample: SampleData, thresh_db: float, fade_ms: float,
                       rms_ms: float = _DEFAULT_RMS_MS,
                       drop_full_loop: bool = True,
                       floor_margin_db: float = _DEFAULT_FLOOR_MARGIN_DB,
                       refine_ms: float = _REFINE_RMS_MS
                       ) -> Tuple[SampleData, dict]:
    """Trim the leading silence of one sample.

    Returns (new_or_original_sample, info). On any no-op the ORIGINAL sample
    is returned with info['trimmed'] = False and a reason.

    Loop handling — a real sustain loop wholly inside the kept audio is never
    touched (the cut only ever lands before it). A loop whose start sits
    inside the region we're removing is a *full-length / default* loop (an
    autosampler's whole-take loop typically starts at or near frame 0); with
    `drop_full_loop` it is discarded so the trimmed sample is a clean
    one-shot, otherwise the trim is clamped to protect it.
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
    rwin = max(1, int(round(refine_ms / 1000.0 * sample.sample_rate)))
    cut = _start_cut_frame(energy, n, win, thresh_db, floor_margin_db, rwin)
    if cut <= 0:
        info['reason'] = 'nothing to trim'
        return sample, info

    # Loop handling (see docstring).
    has_loop = (sample.loop_type != LoopType.NO_LOOP
                and sample.loop_end > sample.loop_start)
    drop_loop = False
    if has_loop and sample.loop_start < cut:
        # The loop starts inside the region we would trim.
        if drop_full_loop:
            drop_loop = True                       # discard the full-length loop
        else:
            cut = sample.loop_start                # protect it: never cut past loop_start
            info['loop_guarded'] = True

    cut = min(cut, n - _MIN_KEEP_FRAMES)
    if cut <= 0:
        info['reason'] = 'nothing to trim'
        return sample, info

    # Fade the first `fade` frames of the KEPT region up from zero so the new
    # start is click-free regardless of where the cut lands.
    fade = int(round(fade_ms / 1000.0 * sample.sample_rate))
    fade = max(1, min(fade, n - cut - 1))
    out = sig[cut * channels:]
    for i in range(fade):
        g = i / fade                                # ~0.0 → 1.0 across the fade
        base = i * channels
        for c in range(channels):
            out[base + c] *= g

    if drop_loop:
        new = replace(sample, data=_float_to_pcm(out),
                      loop_type=LoopType.NO_LOOP, loop_start=0, loop_end=0)
        info['loop_dropped'] = True
    elif has_loop:
        new = replace(sample, data=_float_to_pcm(out),
                      loop_start=sample.loop_start - cut,
                      loop_end=sample.loop_end - cut)
    else:
        new = replace(sample, data=_float_to_pcm(out))
    info.update(trimmed=True, new_frames=n - cut, cut_frames=cut)
    return new, info


def trim_start_bank(bank, *, thresh_db: float = _DEFAULT_THRESH_DB,
                    fade_ms: float = _DEFAULT_FADE_MS,
                    rms_ms: float = _DEFAULT_RMS_MS,
                    drop_full_loop: bool = True) -> None:
    """Trim the leading silence of every sample in `bank` (in place).

    thresh_db:  cut point is just before the first short-time-RMS window
                louder than this many dB below the sample's own peak RMS
                (default -72, "silence only"). Higher (e.g. -40) trims
                deeper into the natural attack; lower keeps more lead-in.
    fade_ms:    click-avoiding fade-in ending at the new sample start.
    rms_ms:     short-time RMS window used to detect the onset (default 20 ms).
    drop_full_loop:  when a sample's loop starts inside the trimmed lead-in
                (an autosampler whole-take loop), discard it (True) so the
                result is a clean one-shot, or preserve it by clamping the
                trim to the loop start (False).
    """
    n = len(bank.samples)
    print(f"\n  Start trim (threshold {thresh_db:g} dB below peak RMS, "
          f"fade {fade_ms:g} ms); samples: {n}")

    n_trim = n_drop = 0
    saved_frames = 0
    for i, s in enumerate(bank.samples):
        new_s, info = _trim_start_sample(s, thresh_db, fade_ms, rms_ms,
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

    rate = bank.samples[0].sample_rate if bank.samples else 44100
    print(f"  Done: trimmed {n_trim}/{n} sample(s); "
          f"removed ~{saved_frames / (rate or 1):.1f}s of lead-in total"
          + (f"; dropped {n_drop} full-length loop(s)." if n_drop else "."))
