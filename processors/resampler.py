# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
#
# This file is part of mpc2emu.
# Original DSP implementation. Filter/dither algorithms from
# standard DSP literature (no specific copyrighted source).
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
Vintage Resampler
-----------------
Simulates the signal path of:
  - EMU Emulator II  (1984): 8-bit, 27.5 kHz, CEM5505/SSM2045 filter, noisy DAC
  - EMU Emax I       (1986): 12-bit, 27.5 kHz, cleaner but still gritty

Signal chain (in order):
  1. Anti-aliasing lowpass filter  (before downsampling — authentisch: simple RC-style)
  2. Downsample to target rate     (naive integer decimation = aliasing like the real thing)
  3. Gain-stage toward full scale  (so the quantizer gets the resolution the profile spec
                                    assumes — what a sound designer would have done by
                                    recording hot; see resample_vintage())
  4. Requantize to target bit depth (truncation, not rounding — hardware did this)
  5. Noise shaping / dither        (TPDF dither for Emax; raw truncation noise for E2)
  6. Optional bandpass coloring    (models the output reconstruction filter + transformer)
  7. Restore original level        (default — undoes step 3 so the sample keeps the
                                    loudness the patch was authored at; can be disabled
                                    to keep the gain-staged "hot" level instead)

The output is stored at the profile's native rate (e.g. 27500 Hz).  EOS/E4XT handles
arbitrary sample rates in the E3S1 header correctly — real-world E4B libraries (e.g.
Angry Emax) ship samples at 27500 Hz with playback_rate=0 and play at correct pitch.
Storing at the vintage rate saves ~37 % sample RAM compared to upsampling back to 44100 Hz.

References:
  - "The E-mu Emulator" service manual (1981, revised 1984)
  - Emax technical reference manual
  - Kunkel & Tierney "Quantization Noise in Digital Audio" (1988)
  - Various MuffWiggler/GS threads on E2 sound character
"""

import array
import math
import os
import struct
import sys
import random
import concurrent.futures
from dataclasses import dataclass
from typing import Optional
from models.common import SampleData


# ---------------------------------------------------------------------------
# Device presets
# ---------------------------------------------------------------------------

@dataclass
class VintageProfile:
    """Complete signal-path specification for one vintage sampler."""
    name: str
    display_name: str

    # Core specs
    sample_rate: int        # Hz
    bit_depth: int          # Effective bits (8 or 12)

    # Anti-aliasing filter (1st-order RC lowpass applied before decimation)
    aa_cutoff_hz: float     # -3dB frequency of pre-filter
    aa_poles: int           # 1 = 6dB/oct (E2 RC filter), 2 = 12dB/oct

    # Quantization character
    truncate: bool          # True = truncate (hardware); False = round
    dither: bool            # True = TPDF dither before quantization
    noise_floor_bits: float # Extra noise added (models DAC noise); 0 = none

    # Bandpass coloring (output reconstruction)
    bp_enabled: bool
    bp_lo_hz: float         # High-pass knee (removes DC/sub rumble)
    bp_hi_hz: float         # Low-pass knee (output filter / transformer rolloff)
    bp_poles: int           # Filter order

    # DC offset (some E2 units had slight DC offset on output)
    dc_offset: float        # -1.0..+1.0, fraction of full scale; 0 = none


# EMU Emulator II (1984)
# - 8-bit linear PCM, 27.5 kHz
# - Simple RC anti-aliasing (one-pole, ~10 kHz)
# - CEM5505 VCF in the signal path (modeled as gentle HF rolloff)
# - Notoriously gritty quantization noise — NO dither
# - Output transformer adds slight low-end coloring
EMULATOR_II = VintageProfile(
    name             = "emulator2",
    display_name     = "EMU Emulator II (8-bit / 27.5 kHz)",
    sample_rate      = 27500,
    bit_depth        = 8,
    aa_cutoff_hz     = 9500.0,    # Measured from E2 schematics
    aa_poles         = 1,
    truncate         = True,      # E2 ADC truncates, no dither
    dither           = False,
    noise_floor_bits = 0.6,       # Extra DAC noise (roughly -43 dBFS)
    bp_enabled       = True,
    bp_lo_hz         = 30.0,      # Output transformer low-end rolloff
    bp_hi_hz         = 11000.0,   # CEM filter + output path HF loss
    bp_poles         = 1,
    dc_offset        = 0.002,     # Slight DC from unbalanced output stage
)

# EMU Emax I (1986)
# - 12-bit linear PCM, 27.5 kHz
# - Better anti-aliasing (two-pole), SSM2044-based VCF
# - Cleaner but still distinctly lo-fi compared to 16-bit
# - Slight dither in later firmware revisions
EMAX_I = VintageProfile(
    name             = "emax1",
    display_name     = "EMU Emax I (12-bit / 27.5 kHz)",
    sample_rate      = 27500,
    bit_depth        = 12,
    aa_cutoff_hz     = 11000.0,   # Better input filter than E2
    aa_poles         = 2,
    truncate         = False,     # Rounds to nearest (later firmware)
    dither           = True,      # TPDF dither
    noise_floor_bits = 0.2,       # Quieter DAC
    bp_enabled       = True,
    bp_lo_hz         = 20.0,
    bp_hi_hz         = 12500.0,   # Slightly brighter than E2
    bp_poles         = 1,
    dc_offset        = 0.0,
)

PROFILES = {
    "emulator2": EMULATOR_II,
    "emax1":     EMAX_I,
}


# ---------------------------------------------------------------------------
# DSP utilities
# ---------------------------------------------------------------------------

def _pcm_to_float(data: bytes) -> list[float]:
    """Convert 16-bit LE PCM bytes to list of floats in -1.0..+1.0.

    CR-16: bulk `array('h')` decode instead of a per-frame `struct.unpack_from`
    loop (~2× faster; byte-identical).  The remaining cost is the per-element
    float divide — without numpy (which the resampler intentionally avoids) that
    is the floor."""
    a = array.array('h')
    a.frombytes(data[:len(data) - (len(data) & 1)])   # drop a trailing odd byte
    if sys.byteorder == 'big':                        # PCM is little-endian
        a.byteswap()
    return [s / 32768.0 for s in a]


def _float_to_pcm(samples: list[float]) -> bytes:
    """Convert float list (-1..+1) to 16-bit LE PCM bytes, with hard clipping.

    CR-16: bulk `array('h')` encode instead of a per-frame `struct.pack_into`
    loop (~1.3×; the clip arithmetic dominates).  Same clip (`int()` truncation
    toward zero) → byte-identical output."""
    a = array.array('h',
                    (max(-32768, min(32767, int(s * 32768.0))) for s in samples))
    if sys.byteorder == 'big':
        a.byteswap()
    return a.tobytes()


def _onepole_lowpass(samples: list[float], cutoff_hz: float,
                     sample_rate: int) -> list[float]:
    """
    First-order IIR lowpass (RC filter).
    H(z) = (1-a) / (1 - a*z^-1)   where a = exp(-2π*fc/fs)
    """
    if cutoff_hz >= sample_rate * 0.5:
        return samples[:]
    omega = 2.0 * math.pi * cutoff_hz / sample_rate
    a = math.exp(-omega)
    b = 1.0 - a
    out = [0.0] * len(samples)
    prev = 0.0
    for i, x in enumerate(samples):
        prev = b * x + a * prev
        out[i] = prev
    return out


def _twopole_lowpass(samples: list[float], cutoff_hz: float,
                     sample_rate: int) -> list[float]:
    """
    Second-order Butterworth lowpass (cascaded two 1-pole stages).
    Gives 12 dB/oct rolloff like a proper 2-pole filter.
    """
    stage1 = _onepole_lowpass(samples, cutoff_hz, sample_rate)
    # Second pole slightly above to flatten passband
    stage2 = _onepole_lowpass(stage1, cutoff_hz * 1.2, sample_rate)
    return stage2


def _onepole_highpass(samples: list[float], cutoff_hz: float,
                      sample_rate: int) -> list[float]:
    """First-order IIR highpass (DC blocker / low-end rolloff)."""
    if cutoff_hz <= 0:
        return samples[:]
    omega = 2.0 * math.pi * cutoff_hz / sample_rate
    a = math.exp(-omega)
    out = [0.0] * len(samples)
    prev_x = 0.0
    prev_y = 0.0
    for i, x in enumerate(samples):
        y = a * (prev_y + x - prev_x)
        out[i] = y
        prev_x = x
        prev_y = y
    return out


def _decimate(samples: list[float], src_rate: int,
              dst_rate: int) -> list[float]:
    """
    Naive integer-ratio decimation (drop samples, no interpolation).
    This intentionally introduces aliasing — exactly like the real hardware.
    For non-integer ratios, uses nearest-sample selection.
    """
    if src_rate == dst_rate:
        return samples[:]
    ratio = src_rate / dst_rate
    n_out = int(len(samples) / ratio)
    return [samples[min(int(i * ratio), len(samples) - 1)] for i in range(n_out)]


def _quantize(samples: list[float], bit_depth: int,
              truncate: bool, dither: bool,
              noise_floor_bits: float) -> list[float]:
    """
    Requantize to target bit depth.

    truncate=True:  floor() — what early 8-bit samplers did (harsh)
    dither=True:    add TPDF dither before quantizing (smoother noise floor)
    noise_floor_bits: add extra white noise (models DAC noise floor)

    Both the dither and noise-floor amplitudes are tied to the converter's
    resolution (relative to full scale), not to the input signal's level —
    on real hardware the analog noise floor sits at a fixed level regardless
    of how hot you fed it. resample_vintage() gain-stages the signal toward
    full scale before calling this, exactly as a sound designer would have
    done on the original hardware to get the most out of its limited bit
    depth — that's what makes the resulting SNR match the profile spec.
    """
    levels = 2 ** (bit_depth - 1)   # e.g. 128 for 8-bit, 2048 for 12-bit

    dither_amp = (1.0 / levels) if dither else 0.0
    noise_amp = (2 ** noise_floor_bits - 1) / levels if noise_floor_bits > 0 else 0.0

    rng = random.Random(42)  # Deterministic for reproducibility

    out = []
    for x in samples:
        # Add noise floor
        if noise_amp > 0:
            x += rng.gauss(0.0, noise_amp)

        # TPDF dither: two uniform random values minus each other
        if dither_amp > 0:
            d = (rng.random() - rng.random()) * dither_amp
            x += d

        # Quantize
        scaled = x * levels
        if truncate:
            q = math.floor(scaled)
        else:
            q = round(scaled)

        # Clip and normalize back
        q = max(-levels, min(levels - 1, q))
        out.append(q / levels)

    return out


# ---------------------------------------------------------------------------
# Main resampler
# ---------------------------------------------------------------------------

def resample_vintage(
    sample: SampleData,
    profile: VintageProfile,
    bandpass: bool = True,
    restore_level: bool = True,
    verbose: bool = True,
) -> SampleData:
    """
    Apply vintage resampling to a SampleData object.

    Args:
        sample:        Input SampleData (16-bit, any rate)
        profile:       VintageProfile (EMULATOR_II or EMAX_I)
        bandpass:      Apply output bandpass coloring (default True)
        restore_level: After processing, scale the result back down to the
                       source's original peak level (default True). The
                       signal is always gain-staged up to near full scale
                       before quantizing — that's what gives it the
                       profile's documented SNR — so leaving this on keeps
                       that benefit while returning the sample to the
                       loudness the patch was authored at. Turning it off
                       keeps the boosted, "hot" level instead.

    Returns:
        New SampleData with the vintage character applied and upsampled back
        to the original sample_rate.  bit_depth stays at 16 for E4B
        compatibility (quantization noise is baked in as signal).
    """
    src_rate = sample.sample_rate
    dst_rate = profile.sample_rate

    if verbose:
        print(f"    Resampling '{sample.name}' → {profile.display_name}")

    # Convert to float
    signal = _pcm_to_float(sample.data)

    # --- Stage 1: Anti-aliasing filter (before decimation) ---
    if verbose:
        print(f"      [1/6] Anti-alias filter ({profile.aa_cutoff_hz:.0f} Hz, "
              f"{profile.aa_poles}-pole)")
    if profile.aa_poles == 1:
        signal = _onepole_lowpass(signal, profile.aa_cutoff_hz, src_rate)
    else:
        signal = _twopole_lowpass(signal, profile.aa_cutoff_hz, src_rate)

    # --- Stage 2: Decimate to target rate ---
    if verbose:
        print(f"      [2/6] Decimate {src_rate} Hz → {dst_rate} Hz")
    signal = _decimate(signal, src_rate, dst_rate)

    # --- Stage 3: Gain-stage (normalize toward full scale) ---
    # A quantizer's step size is fixed relative to full scale, so a signal
    # that only uses a fraction of the available range effectively gets
    # fewer usable bits — and proportionally worse SNR — than the profile
    # spec describes. A sound designer of the era would have recorded as hot
    # as possible before sampling to avoid exactly this. We reproduce that
    # best practice: boost the signal toward full scale before quantizing
    # (so it gets the full resolution the profile spec assumes), then —
    # by default — scale back down afterwards to restore the source's
    # original perceived level (see `restore_level`).
    target_peak = 0.99
    peak = max((abs(x) for x in signal), default=0.0)
    gain = (target_peak / peak) if peak > 1e-9 else 1.0
    if verbose:
        print(f"      [3/6] Gain-stage "
              f"(peak {20*math.log10(max(peak, 1e-9)):.1f} dBFS → "
              f"×{gain:.2f} → {20*math.log10(target_peak):.1f} dBFS)")
    if gain != 1.0:
        signal = [x * gain for x in signal]

    # --- Stage 4: Quantize + dither ---
    if verbose:
        noise_note = (f', +noise floor {profile.noise_floor_bits:.1f}b'
                      if profile.noise_floor_bits else '')
        print(f"      [4/6] Quantize to {profile.bit_depth}-bit "
              f"({'truncate' if profile.truncate else 'round'}"
              f"{', +TPDF dither' if profile.dither else ''}"
              f"{noise_note})")
    signal = _quantize(
        signal,
        profile.bit_depth,
        profile.truncate,
        profile.dither,
        profile.noise_floor_bits,
    )

    # --- Stage 5: Bandpass coloring ---
    if bandpass and profile.bp_enabled:
        if verbose:
            print(f"      [5/6] Bandpass color "
                  f"({profile.bp_lo_hz:.0f}–{profile.bp_hi_hz:.0f} Hz)")
        signal = _onepole_highpass(signal, profile.bp_lo_hz, dst_rate)
        if profile.bp_poles == 1:
            signal = _onepole_lowpass(signal, profile.bp_hi_hz, dst_rate)
        else:
            signal = _twopole_lowpass(signal, profile.bp_hi_hz, dst_rate)
        if profile.dc_offset != 0.0:
            signal = [x + profile.dc_offset for x in signal]
    elif verbose:
        print(f"      [5/6] Bandpass color: skipped")

    # --- Stage 6: Restore original level (default) and store at vintage rate ---
    if restore_level and gain != 1.0:
        signal = [x / gain for x in signal]
    if verbose:
        print(f"      [6/6] Restore level → store at {dst_rate} Hz (saves RAM; EOS pitches correctly)")
    pcm_out = _float_to_pcm(signal)

    # Loop points were relative to src_rate frames; rescale to dst_rate frames.
    scale = dst_rate / src_rate
    n_frames = len(pcm_out) // max(1, sample.channels * 2)
    loop_start = max(0, min(round(sample.loop_start * scale), n_frames))
    loop_end   = max(loop_start, min(round(sample.loop_end * scale), n_frames))

    return SampleData(
        name         = sample.name,
        data         = pcm_out,
        sample_rate  = dst_rate,          # Store at vintage rate — saves RAM, EOS pitches correctly
        channels     = sample.channels,
        bit_depth    = 16,                # Always 16 for E4B (noise baked in)
        loop_type    = sample.loop_type,
        loop_start   = loop_start,        # clamped to resampled length (CR-11)
        loop_end     = loop_end,
        root_note    = sample.root_note,
        fine_tune    = sample.fine_tune,
    )


def resample_to_rate(sample: SampleData, dst_rate: int,
                     verbose: bool = True) -> SampleData:
    """Clean linear-interpolation downsample to `dst_rate` (no vintage coloring).

    Unlike resample_vintage (which deliberately aliases + requantizes for
    period character), this is a faithful rate change: a 2-pole anti-alias
    lowpass at the new Nyquist, then linear interpolation, then loop-point
    rescaling.  16-bit is preserved.

    The motivating use is KRZ floppy banks: the K2000 can only pitch a sample
    UP by log2(48000/sr) octaves before clamping (see docs/RESOLUTION_NOTES.md
    "KRZ up-pitch clamp"), so storing multisamples at a LOWER rate buys the
    up-pitch headroom that wide key zones need — and shrinks the bank to fit a
    1.44 MB floppy at the same time.  Pitching down is unlimited, so the lower
    rate costs only high-frequency detail, not pitch tracking.
    """
    src_rate = sample.sample_rate
    if dst_rate >= src_rate:
        return sample  # never upsample here

    signal = _pcm_to_float(sample.data)
    if verbose:
        print(f"    Downsample '{sample.name}' {src_rate} → {dst_rate} Hz "
              f"(up-pitch headroom +{1200*math.log(48000.0/dst_rate, 2)/100:.1f} st)")

    # Anti-alias at the destination Nyquist (slightly below, for filter rolloff)
    signal = _twopole_lowpass(signal, dst_rate * 0.45, src_rate)

    # Linear-interpolation resample
    ratio = src_rate / dst_rate
    n_out = int(len(signal) / ratio)
    out = []
    last = len(signal) - 1
    for i in range(n_out):
        pos = i * ratio
        i0 = int(pos)
        frac = pos - i0
        s0 = signal[i0]
        s1 = signal[i0 + 1] if i0 < last else s0
        out.append(s0 + (s1 - s0) * frac)

    pcm_out = _float_to_pcm(out)
    scale = dst_rate / src_rate
    n_frames = len(pcm_out) // 2
    loop_start = max(0, min(round(sample.loop_start * scale), n_frames))
    loop_end   = max(loop_start, min(round(sample.loop_end * scale), n_frames))

    return SampleData(
        name        = sample.name,
        data        = pcm_out,
        sample_rate = dst_rate,
        channels    = sample.channels,
        bit_depth   = 16,
        loop_type   = sample.loop_type,
        loop_start  = loop_start,
        loop_end    = loop_end,
        root_note   = sample.root_note,
        fine_tune   = sample.fine_tune,
    )


def _worker_resample(args: tuple) -> SampleData:
    """Top-level worker so ProcessPoolExecutor can pickle it."""
    sample, profile, bandpass, restore_level = args
    return resample_vintage(sample, profile, bandpass, restore_level, verbose=False)


def resample_bank(
    bank,                           # models.common.Bank
    profile_name: str,
    bandpass: bool = True,
    restore_level: bool = True,
    workers: Optional[int] = None,
) -> None:
    """
    Resample all samples in a Bank in-place using a process pool.

    Args:
        bank:          Bank object (modified in-place)
        profile_name:  "emulator2" or "emax1"
        bandpass:      Apply bandpass coloring
        restore_level: Restore each sample's original level after the
                       gain-staged vintage processing (default True);
                       see resample_vintage().
        workers:       Number of worker processes (default: cpu_count - 1)
    """
    profile = PROFILES.get(profile_name)
    if profile is None:
        raise ValueError(
            f"Unknown profile '{profile_name}'. "
            f"Available: {list(PROFILES.keys())}"
        )

    if workers is None:
        workers = max(1, (os.cpu_count() or 2) - 1)

    n = len(bank.samples)
    print(f"\n  Vintage resampling: {profile.display_name}")
    print(f"  Samples to process: {n}  (workers: {workers})")

    args = [(s, profile, bandpass, restore_level) for s in bank.samples]

    if workers == 1 or n <= 1:
        # Single-process path: keep verbose per-stage output
        for i, sample in enumerate(bank.samples):
            bank.samples[i] = resample_vintage(sample, profile, bandpass, restore_level)
    else:
        done = 0
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
            for i, result in enumerate(ex.map(_worker_resample, args)):
                bank.samples[i] = result
                done += 1
                print(f"    [{done:3d}/{n}] '{result.name}' done")

    print(f"  Done. All {n} samples resampled.")
