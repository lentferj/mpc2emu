# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# Independent reimplementation. TAL-Sampler XML format knowledge
# partially informed by ConvertWithMoss (LGPLv3),
#   Jürgen Moßgraber, https://github.com/git-moss/ConvertWithMoss
# Structure verified against live .talsmpl preset files.
# No source code was copied.
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
TAL-Sampler .talsmpl Parser & Writer
--------------------------------------
.talsmpl is an XML preset file used by TAL-Sampler (TAL Software GmbH).

File structure (all versions):
  <tal version="1.3">       ← root tag is always 'tal'; version varies 1.3..6.0
    <programs>
      <program programname="MyPreset"
               filtercutoff="1" filterresonance="0" filtermode="0"
               adsrampattack="0" adsrampdecay="0" adsrampsustain="1" adsramprelease="0.65"
               sampleenableda="1" samplevolumea="0.5" samplepana="0.5"
               sampletunea="0.5" samplefinetunea="0.5" layertransposea="0.5"
               sampleenabledb="0" ...
               sampleenabledc="0" ...
               sampleenabledd="0" ...>
        <samplelayer0>
          <multisamples>
            <multisample url="kick.wav"
                         rootkey="36" lowkey="36" highkey="36"
                         loopstartsample="0" loopendsample="0"
                         startsample="0" endsample="9797"
                         loopenabled="0" volume="1" detune="0.5"
                         isromsample="0" reverse="0"/>
          </multisamples>
        </samplelayer0>
        <samplelayer1> ... </samplelayer1>
        <samplelayer2> ... </samplelayer2>
        <samplelayer3> ... </samplelayer3>
      </program>
    </programs>
  </tal>

  v6.0 only: adds a <sampledata> block with base64 float32-LE stereo PCM.
  The url filenames in <sampledata> match the samplelayer multisample urls
  exactly (after stripping the Windows path prefix).

Parameter notes:
  - All 0..1 normalised knobs: 0.5 = neutral
  - sampletune{a-d}:       ±24 semitones  (0.25 = -12, 0.5 = 0, 0.75 = +12)
  - samplefinetune{a-d}:   ±100 cents     (0.0 = -100, 0.5 = 0, 1.0 = +100)
  - layertranspose{a-d}:   ±24 semitones, integer-rounded
  - samplevolume{a-d}:     0..1 linear
  - samplepan{a-d}:        0.0=L, 0.5=C, 1.0=R
  - filtercutoff:          0..1 (maps directly to VoiceLayer.filter_cutoff)
  - filterresonance:       0..1 (maps directly to VoiceLayer.filter_resonance)
  - adsramp*:              0..1 normalised, approximate log mapping to seconds
  - loopenabled:           "0"/"1"  (NOT "false"/"true")

  .talwav files are TAL-proprietary encrypted audio and cannot be decoded.

filtermode encoding (confirmed 2026-06-08):
  13 discrete modes, filtermode = mode_index / 12.0  (step ≈ 0.0833).
  Confirmed by corpus survey (1706 presets) + TAL-Sampler UI cross-checks.

  Internal order = UI dropdown order (confirmed 2026-06-08, N = UI position):
    N= 0 (0.000) LP 4P   N= 1 (0.083) LP 2P   N= 2 (0.167) LP 1P
    N= 3 (0.250) LP 4PN  N= 4 (0.333) LP 3PN  N= 5 (0.417) LP 2PN
    N= 6 (0.500) LP 1PN  N= 7 (0.583) HP 2PN  N= 8 (0.667) HP 3PN
    N= 9 (0.750) BP 4PN  N=10 (0.833) Notch 2P N=11 (0.917) All Pass
    N=12 (1.000) BW 6P

  Confirmed by explicit preset saves (Jan Lentfer, 2026-06-08):
    N=0→LP 4P, N=6→LP 1PN, N=7→HP 2PN, N=9→BP 4PN, N=11→All Pass, N=12→BW 6P.
  N=2 (LP 1P) and N=10 (Notch 2P) have zero corpus presets.
  N=11 (All Pass): no E4B equivalent; falls back to LP24 (XPM type 3).
  N=4 (LP 3PN): no 3-pole XPM type; approximated as Low 4 (XPM type 3).
  N=8 (HP 3PN): no 3-pole HP XPM; approximated as High 4 (XPM type 8).
  See _tal_filtermode_to_xpm() for the full XPM mapping table.
"""

import array
import base64
import os
import shutil
import struct
import wave
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET
from xml.dom import minidom

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType, Envelope
)
from parsers.xpm_parser import load_wav, _safe_name
from parsers.tal_template import new_tal_root, new_multisample


# ---------------------------------------------------------------------------
# Helpers — value conversions
# ---------------------------------------------------------------------------

def _midi_to_name(note: int) -> str:
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    return f"{names[note % 12]}{note // 12 - 1}"


def _vol_linear_to_db(linear: float) -> float:
    import math
    if linear <= 0:
        return -96.0
    return 20.0 * math.log10(max(linear, 1e-6))


def _db_to_vol_linear(db: float) -> float:
    import math
    if db <= -96:
        return 0.0
    return min(1.0, 10 ** (db / 20.0))


def _pan_tal_to_internal(tal_pan: float) -> float:
    return (tal_pan - 0.5) * 2.0


def _pan_internal_to_tal(internal: float) -> float:
    return (internal / 2.0) + 0.5


def _loop_type_to_tal(loop_type: LoopType) -> str:
    return "false" if loop_type == LoopType.NO_LOOP else "true"


def _tal_adsr_to_secs(val: float) -> float:
    """Approximate TAL 0..1 ADSR knob → seconds (logarithmic, 0=0s, 1≈10s)."""
    return (val ** 3) * 10.0


def _secs_to_tal_adsr(secs: float) -> float:
    """Inverse of _tal_adsr_to_secs: seconds → TAL 0..1 ADSR knob."""
    return max(0.0, min(1.0, (max(0.0, secs) / 10.0) ** (1.0 / 3.0)))


def _tal_zones_overlap(a, b) -> bool:
    """True if two zones overlap in BOTH key and velocity (→ they would sound
    simultaneously, so they need separate TAL layers)."""
    return (a.lo_key <= b.hi_key and b.lo_key <= a.hi_key and
            a.lo_vel <= b.hi_vel and b.lo_vel <= a.hi_vel)


# ---------------------------------------------------------------------------
# Filter mode mapping
# ---------------------------------------------------------------------------

# TAL-Sampler filtermode → XPM FilterType.
# 13 discrete modes: filtermode = N/12.0, N in 0..12.
# mode_index = min(12, max(0, round(val * 12)))
#
# N = UI dropdown position = internal storage index (confirmed 2026-06-08).
# Six confirmed by explicit EV-VintageFifthLead_*.talsmpl saves (Jan Lentfer):
#   N=0  (0.000) LP 4P    → XPM 3  Low 4    confirmed
#   N=6  (0.500) LP 1PN   → XPM 1  Low 1    confirmed
#   N=7  (0.583) HP 2PN   → XPM 7  High 2   confirmed
#   N=9  (0.750) BP 4PN   → XPM 12 Band 4   confirmed
#   N=11 (0.917) All Pass → XPM 3  Low 4    confirmed (no E4B equivalent; LP24 fallback)
#   N=12 (1.000) BW 6P    → XPM 4  Low 6    confirmed
# Derived from confirmed order (N = UI pos) — no hardware ambiguity remains:
#   N=1  (0.083) LP 2P    → XPM 2  Low 2
#   N=2  (0.167) LP 1P    → XPM 1  Low 1    (0 corpus presets)
#   N=3  (0.250) LP 4PN   → XPM 3  Low 4
#   N=4  (0.333) LP 3PN   → XPM 3  Low 4    (no 3-pole XPM; Low 4 closest)
#   N=5  (0.417) LP 2PN   → XPM 2  Low 2
#   N=8  (0.667) HP 3PN   → XPM 8  High 4   (no 3-pole HP XPM; High 4 closest)
#   N=10 (0.833) Notch 2P → XPM 15 BS 2P    (0 corpus presets)
_TAL_FM_XPM = [3, 2, 1, 3, 3, 2, 1, 7, 8, 12, 15, 3, 4]

def _tal_filtermode_to_xpm(val: float) -> int:
    mode = min(12, max(0, round(val * 12)))
    return _TAL_FM_XPM[mode]


# Inverse: XPM FilterType → TAL filtermode (0..1).  _TAL_FM_XPM is many-to-one,
# so pick the first (lowest, most-standard) N that maps to each XPM type.
_XPM_FM_TAL = {}
for _n, _x in enumerate(_TAL_FM_XPM):
    _XPM_FM_TAL.setdefault(_x, _n)


def _xpm_filtermode_to_tal(xpm_type: int) -> float:
    """XPM/model filter_type → TAL filtermode knob (0..1). Unknown → LP 4P (0)."""
    return _XPM_FM_TAL.get(xpm_type, 0) / 12.0


# ---------------------------------------------------------------------------
# Audio format helpers
# ---------------------------------------------------------------------------

def _float32_stereo_to_int16_mono(raw: bytes) -> bytes:
    """Convert float32-LE stereo interleaved PCM to int16-LE mono.

    Used for v6.0 embedded base64 audio (float32 LE, 2 channels).
    """
    fa = array.array('f')
    fa.frombytes(raw)
    out = array.array('h')
    SCALE = 32767.0
    for i in range(0, len(fa) - 1, 2):
        v = (fa[i] + fa[i + 1]) * 0.5
        if v > 1.0:
            v = 1.0
        elif v < -1.0:
            v = -1.0
        out.append(int(v * SCALE))
    return out.tobytes()


def _load_aiff(path: str, name: str) -> Optional[SampleData]:
    """Load AIFF or AIFF-C via stdlib aifc module."""
    import aifc
    try:
        with aifc.open(path, 'r') as af:
            n_ch = af.getnchannels()
            sw   = af.getsampwidth()    # bytes per sample per channel
            rate = af.getframerate()
            nf   = af.getnframes()
            raw  = af.readframes(nf)

        total = nf * n_ch
        if sw == 2:
            samps = list(struct.unpack(f'>{total}h', raw))
        elif sw == 3:
            samps = []
            for i in range(0, len(raw), 3):
                b = raw[i:i + 3] + b'\x00'
                samps.append(struct.unpack('>i', b)[0] >> 16)
        elif sw == 4:
            samps = [s >> 16 for s in struct.unpack(f'>{total}i', raw)]
        else:
            print(f"  [WARN] AIFF: unsupported sample width {sw}: {path}")
            return None

        if n_ch == 2:
            samps = [(samps[i] + samps[i + 1]) // 2 for i in range(0, len(samps), 2)]
        elif n_ch > 2:
            samps = samps[0::n_ch]

        return SampleData(
            name=name,
            data=struct.pack(f'<{len(samps)}h', *samps),
            sample_rate=rate,
            channels=1,
            bit_depth=16,
        )
    except Exception as exc:
        print(f"  [WARN] AIFF load failed {path}: {exc}")
        return None


def _load_sample_file(path: str, name: str) -> Optional[SampleData]:
    """Dispatch to WAV or AIFF loader based on file extension."""
    if path.lower().endswith(('.aif', '.aiff')):
        return _load_aiff(path, name)
    return load_wav(path, name)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_talsmpl(talsmpl_path: str, wav_dir: Optional[str] = None) -> Bank:
    """
    Parse a TAL-Sampler .talsmpl preset file.

    Handles all real-world versions (1.3 – 6.0):
      - v1.3..5.0: external WAV/AIFF sample files
      - v6.0: embedded base64 float32-LE stereo PCM in <sampledata>

    .talwav files are proprietary-encrypted and are skipped with a warning.

    Args:
        talsmpl_path:  Path to the .talsmpl file
        wav_dir:       Extra directory for sample file search (default: preset dir)

    Returns:
        Bank with one Preset and loaded SampleData objects.
    """
    p = Path(talsmpl_path).resolve()
    search_dir = Path(wav_dir) if wav_dir else p.parent

    print(f"Parsing TALSMPL: {p.name}")

    tree = ET.parse(str(p))
    root = tree.getroot()

    prog = root.find('.//program')
    if prog is None:
        print(f"  [WARN] No <program> element found — unsupported format, skipping")
        bank = Bank(name=_safe_name(p.stem))
        bank.presets.append(Preset(name=_safe_name(p.stem)))
        return bank

    preset_name = _safe_name(prog.get('programname', p.stem))
    bank   = Bank(name=preset_name)
    preset = Preset(name=preset_name)

    sample_cache: dict = {}

    # v6.0: build filename → (PCM bytes, metadata) map from embedded <sampledata>
    embedded: dict      = {}   # filename → int16-LE mono bytes
    embedded_meta: dict = {}   # filename → {samplerate, loopstart, loopend, loopenabled}
    for sd_elem in root.findall('.//sampledata/sample'):
        url = sd_elem.get('url', '')
        b64 = (sd_elem.text or '').strip()
        if not (url and b64):
            continue
        fn = url.replace('\\', '/').split('/')[-1]
        try:
            pcm = _float32_stereo_to_int16_mono(base64.b64decode(b64))
            embedded[fn] = pcm
            embedded_meta[fn] = {
                'samplerate':  int(float(sd_elem.get('samplerate', '44100'))),
                'loopstart':   int(sd_elem.get('loopstart', '0')),
                'loopend':     int(sd_elem.get('loopend', '0')),
                'loopenabled': sd_elem.get('loopenabled', '0'),
            }
        except Exception as exc:
            print(f"  [WARN] Embedded sample decode failed ({fn}): {exc}")

    # Global filter / ADSR (single set for the whole preset in TAL-Sampler)
    filter_cutoff    = float(prog.get('filtercutoff',    '1.0'))
    filter_resonance = float(prog.get('filterresonance', '0.0'))
    filter_type      = _tal_filtermode_to_xpm(float(prog.get('filtermode', '0.0')))
    adsr_attack  = _tal_adsr_to_secs(float(prog.get('adsrampattack',  '0.0')))
    adsr_decay   = _tal_adsr_to_secs(float(prog.get('adsrampdecay',   '0.0')))
    adsr_sustain = float(prog.get('adsrampsustain', '0.8'))
    adsr_release = _tal_adsr_to_secs(float(prog.get('adsramprelease', '0.5')))

    _SUFFIXES = ['a', 'b', 'c', 'd']

    for layer_idx in range(4):
        sfx = _SUFFIXES[layer_idx]

        if prog.get(f'sampleenabled{sfx}', '0') in ('0', '0.0'):
            continue

        layer_el = prog.find(f'samplelayer{layer_idx}')
        ms_cont  = layer_el.find('multisamples') if layer_el is not None else None
        if ms_cont is None:
            continue

        # Per-layer parameters (0..1 normalised, 0.5 = neutral)
        vol_lin   = float(prog.get(f'samplevolume{sfx}',   '0.5'))
        pan_tal   = float(prog.get(f'samplepan{sfx}',      '0.5'))
        tune_norm = float(prog.get(f'sampletune{sfx}',     '0.5'))
        fine_norm = float(prog.get(f'samplefinetune{sfx}', '0.5'))
        xpos_norm = float(prog.get(f'layertranspose{sfx}', '0.5'))
        # Calibrated: 0.25=−12 semi, 0.5=0, 0.75=+12 semi → range ±24 semitones
        tune_semi = (tune_norm - 0.5) * 48.0
        fine_cent = (fine_norm - 0.5) * 200.0      # ±100 cents
        transpose = int(round((xpos_norm - 0.5) * 48.0))

        voice = VoiceLayer(
            amp_env          = Envelope(adsr_attack, adsr_decay,
                                        adsr_sustain, adsr_release),
            filter_cutoff    = filter_cutoff,
            filter_resonance = filter_resonance,
            filter_type      = filter_type,
        )

        for ms in ms_cont.findall('multisample'):
            if ms.get('isromsample', '0') not in ('0', '0.0'):
                continue   # built-in oscillator waveform, no sample file

            url = ms.get('url', '')
            if not url:
                continue

            fn = url.replace('\\', '/').split('/')[-1]

            root_key = int(ms.get('rootkey', '60'))
            lo_key   = int(ms.get('lowkey',  '0'))
            hi_key   = int(ms.get('highkey', '127'))
            lp_en    = ms.get('loopenabled', '0')
            lp_st    = int(ms.get('loopstartsample', '0'))
            lp_end   = int(ms.get('loopendsample',   '0'))
            start_s  = int(ms.get('startsample', '0'))
            end_s    = int(ms.get('endsample',   '0'))
            det_norm = float(ms.get('detune', '0.5'))
            zone_fine = int((det_norm - 0.5) * 200.0)   # per-zone ±100 cents
            # v11 multisamples carry per-sample gain/pan/velocity/transpose — TAL
            # (and our writer) store the per-zone values here, not on the
            # layer-level sample* attrs.  Prefer them so write→read is lossless.
            ms_vol   = float(ms.get('volume', '1.0'))
            ms_pan   = float(ms.get('pan',    '0.5'))
            ms_vlo   = int(float(ms.get('velocitystart', '0')))
            ms_vhi   = int(float(ms.get('velocityend',   '127')))
            ms_xpose = int(round((float(ms.get('transpose', '0.5')) - 0.5) * 48.0))

            if ms.get('reverse', '0') not in ('0', '0.0'):
                print(f"  [WARN] reverse playback not supported: {fn} — zone skipped")
                continue

            if fn.lower().endswith('.talwav'):
                print(f"  [SKIP] Encrypted .talwav sample (TAL proprietary): {fn}")
                continue

            sname = _safe_name(Path(fn).stem)

            if sname not in sample_cache:
                sd = None

                # v6.0: try embedded PCM (keyed by filename, not full path)
                if fn in embedded:
                    m = embedded_meta[fn]
                    loop_flag = m['loopenabled'] in ('1', '1.0', 'true')
                    sd = SampleData(
                        name        = sname,
                        data        = embedded[fn],
                        sample_rate = m['samplerate'],
                        channels    = 1,
                        bit_depth   = 16,
                        loop_type   = LoopType.FORWARD if loop_flag else LoopType.NO_LOOP,
                        loop_start  = m['loopstart'],
                        loop_end    = m['loopend'],
                        root_note   = root_key,
                    )
                    print(f"  Loaded (embedded): {sd.name} ({sd.sample_rate} Hz)")
                else:
                    candidates = [
                        p.parent / url,
                        p.parent / fn,
                        search_dir / fn,
                        search_dir / url,
                    ]
                    for c in candidates:
                        if c.exists():
                            sd = _load_sample_file(str(c), sname)
                            if sd:
                                loop_flag     = lp_en in ('1', '1.0', 'true')
                                sd.root_note  = root_key
                                sd.loop_type  = LoopType.FORWARD if loop_flag else LoopType.NO_LOOP
                                sd.loop_start = lp_st
                                sd.loop_end   = lp_end
                                print(f"  Loaded: {sd.name} ({sd.sample_rate} Hz)")
                            break
                    else:
                        print(f"  [WARN] Sample not found: {url}")
                        continue

                if sd is None:
                    continue

                # Apply startsample/endsample playback window trim
                n_frames = len(sd.data) // 2
                trim_end = end_s if end_s > 0 else n_frames
                if start_s > 0 or trim_end < n_frames:
                    sd.data       = sd.data[start_s * 2 : trim_end * 2]
                    sd.loop_start = max(0, sd.loop_start - start_s)
                    sd.loop_end   = max(0, sd.loop_end   - start_s)

                sample_cache[sname] = sd
                bank.samples.append(sd)

            zone = ZoneMapping(
                sample_name = sname,
                lo_key      = lo_key,
                hi_key      = hi_key,
                lo_vel      = ms_vlo,
                hi_vel      = ms_vhi,
                root_key    = root_key,
                fine_tune   = max(-100, min(100, int(fine_cent + zone_fine))),
                volume      = _vol_linear_to_db(ms_vol),
                pan         = _pan_tal_to_internal(ms_pan),
                transpose   = int(tune_semi) + transpose + ms_xpose,
            )
            voice.zones.append(zone)

        if voice.zones:
            preset.voices.append(voice)
            print(f"  Layer {layer_idx} ({sfx}): {len(voice.zones)} zone(s)")

    bank.presets.append(preset)
    print(f"  Preset '{preset.name}': {len(preset.voices)} voice(s), "
          f"{len(bank.samples)} sample(s)")
    return bank


def parse_talsmpl_dir(directory: str, wav_dir: Optional[str] = None
                      ) -> list:
    """Parse all .talsmpl files in a directory."""
    banks = []
    for p in sorted(Path(directory).rglob('*.talsmpl')):
        try:
            banks.append(parse_talsmpl(str(p), wav_dir))
        except Exception as e:
            print(f"  [ERROR] {p.name}: {e}")
    return banks


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_talsmpl(bank: Bank, output_dir: str,
                  copy_samples: bool = True) -> list:
    """
    Write a Bank as TAL-Sampler preset(s).

    Each Preset in the bank becomes one .talsmpl file.
    WAV files are written to a 'samples/' subfolder next to the preset.

    Args:
        bank:          Bank to write
        output_dir:    Directory to create preset files in
        copy_samples:  If True, write WAV files alongside the preset

    Returns:
        List of paths to created .talsmpl files
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_dir = out_dir / 'samples'
    if copy_samples:
        sample_dir.mkdir(exist_ok=True)

    sample_map = {s.name: s for s in bank.samples}
    written: list = []
    used_stems: set = set()   # CR-7c: keep preset filenames unique per call

    for preset in bank.presets:
        # CR-7c: two presets with the same name would otherwise overwrite each
        # other's .talsmpl on disk — suffix duplicates.
        stem = preset.name or 'Preset'
        if stem in used_stems:
            i = 1
            while f"{stem}_{i}" in used_stems:
                i += 1
            stem = f"{stem}_{i}"
        used_stems.add(stem)
        talsmpl_path = out_dir / f"{stem}.talsmpl"
        print(f"  Writing TALSMPL: {talsmpl_path.name}")

        # Start from a full v11 default program (all 234 synth attrs + child
        # blocks); override only what mpc2emu models.  CR-3: the previous writer
        # invented a <preset><layer><mapping> schema that loaded nowhere.
        root, prog = new_tal_root()
        prog.set('programname', preset.name)

        # Filter + amp envelope are program-global in TAL; take them from V1.
        v0 = preset.voices[0] if preset.voices else None
        if v0 is not None:
            prog.set('filtercutoff',    f"{max(0.0, min(1.0, v0.filter_cutoff)):.6f}")
            prog.set('filterresonance', f"{max(0.0, min(1.0, v0.filter_resonance)):.6f}")
            prog.set('filtermode',      f"{_xpm_filtermode_to_tal(v0.filter_type):.6f}")
            prog.set('adsrampattack',   f"{_secs_to_tal_adsr(v0.env_attack):.6f}")
            prog.set('adsrampdecay',    f"{_secs_to_tal_adsr(v0.env_decay):.6f}")
            prog.set('adsrampsustain',  f"{max(0.0, min(1.0, v0.env_sustain)):.6f}")
            prog.set('adsramprelease',  f"{_secs_to_tal_adsr(v0.env_release):.6f}")

        # Bin-pack ALL zones into TAL sample layers (max 4) by key×velocity
        # overlap.  TAL has only 4 layers but each holds many <multisample>s with
        # their own key+velocity range, so non-overlapping zones (drum kits,
        # multisampled keyboards, velocity layers our parsers model as separate
        # voices) share ONE layer; only genuinely overlapping zones (simultaneous
        # stacking) need separate layers.  (Was "one voice = one layer", which
        # dropped everything past 4 voices — e.g. a 14-pad drum kit.)
        packed: list = []   # each entry: a list of zones for one layer
        for voice in preset.voices:
            for zone in voice.zones:
                if sample_map.get(zone.sample_name) is None:
                    print(f"    [WARN] Sample '{zone.sample_name}' not in bank, skipping")
                    continue
                target = next((lyr for lyr in packed
                               if not any(_tal_zones_overlap(zone, z) for z in lyr)),
                              None)
                if target is not None:
                    target.append(zone)
                elif len(packed) < 4:
                    packed.append([zone])
                else:
                    print("    [WARN] >4 overlapping layers — extra samples merged "
                          "into layer D")
                    packed[3].append(zone)

        def _emit_multisample(zone):
            sample = sample_map[zone.sample_name]
            if copy_samples:
                wav_filename = f"{sample.name}.wav"
                _write_wav(sample, str(sample_dir / wav_filename))
                rel_path = f"samples/{wav_filename}"
            else:
                rel_path = f"{sample.name}.wav"
            n_frames = len(sample.data) // (2 * max(1, sample.channels))
            last     = max(0, n_frames - 1)   # last valid sample index (TAL uses
                                              # the index, not the count — an
                                              # off-by-one reads past the buffer
                                              # and crashes the looped resampler)
            looped   = sample.loop_type != LoopType.NO_LOOP
            loop_end = min(sample.loop_end if sample.loop_end > 0 else last, last)

            # TAL keeps the FULL multisample attribute set (confirmed by a
            # TAL-Sampler-saved reference); omitting fields makes TAL fall back to
            # its defaults — and its default for `track`/`stereoinverse` is "1"
            # (ON), which keytracks (heavy transpose) and inverts stereo.
            ms = new_multisample()                          # full template
            ms.set('url', rel_path)
            ms.set('urlRelativeToPresetDirectory', rel_path)
            ms.set('isromsample', '0')
            ms.set('rootkey', str(zone.root_key))
            ms.set('lowkey',  str(zone.lo_key))
            ms.set('highkey', str(zone.hi_key))
            # A single-key zone is a one-shot / drum pad: keytracking OFF so it
            # plays at native pitch (track="0").  Ranged zones are melodic
            # multisamples: keep tracking on.  Must be written EXPLICITLY —
            # absent → TAL defaults to "1".
            ms.set('track', '0' if zone.lo_key == zone.hi_key else '1')
            ms.set('stereoinverse', '0')                    # never invert
            # Per-sample filter neutral/open (the template inherited the Startup
            # oscillator's cutoff=0 / highpass=1, which would darken samples).
            ms.set('filtercutoff',   '1.0')
            ms.set('filterhighpass', '0.0')
            ms.set('filterkeyfollow', '0.5')
            ms.set('velocitystart', str(zone.lo_vel))
            ms.set('velocityend',   str(zone.hi_vel))
            ms.set('startsample', '0')
            ms.set('endsample',   str(last))
            ms.set('loopenabled',     '1' if looped else '0')
            ms.set('loopstartsample', str(max(0, sample.loop_start)))
            ms.set('loopendsample',   str(loop_end))
            ms.set('pingpongloop', '1' if sample.loop_type == LoopType.ALTERNATING else '0')
            # Per-zone gain/pan/tune live on the multisample (TAL applies them
            # per sample); layer-level samplevolume/pan/tune stay neutral.
            ms.set('volume',    f"{_db_to_vol_linear(zone.volume):.6f}")
            ms.set('pan',       f"{_pan_internal_to_tal(zone.pan):.6f}")
            ms.set('transpose', f"{max(0.0, min(1.0, 0.5 + (zone.transpose + zone.coarse_tune) / 48.0)):.6f}")
            ms.set('detune',    f"{max(0.0, min(1.0, 0.5 + zone.fine_tune / 200.0)):.6f}")
            return ms

        for layer_idx, zlist in enumerate(packed[:4]):
            sfx = 'abcd'[layer_idx]
            prog.set(f'sampleenabled{sfx}', '1.0')
            ms_cont = prog.find(f'samplelayer{layer_idx}/multisamples')
            for c in list(ms_cont):          # drop the default ROM 'Saw' multisample
                ms_cont.remove(c)
            for zone in zlist:
                ms_cont.append(_emit_multisample(zone))

        # Empty the unused (disabled) layers' default 'Saw' multisamples, so no
        # stray template flags (track="1", etc.) remain anywhere in the file.
        for unused_idx in range(len(packed), 4):
            ms_cont = prog.find(f'samplelayer{unused_idx}/multisamples')
            for c in list(ms_cont):
                ms_cont.remove(c)

        xml_str = minidom.parseString(
            ET.tostring(root, encoding='unicode')
        ).toprettyxml(indent='  ', encoding=None)
        lines = [ln for ln in xml_str.split('\n') if ln.strip()]
        if lines and lines[0].startswith('<?xml'):
            lines = lines[1:]

        # TAL writes CRLF + a blank line after the declaration; match it
        # (newline='' so Python doesn't re-translate).
        with open(str(talsmpl_path), 'w', encoding='utf-8', newline='') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\r\n\r\n')
            f.write('\r\n'.join(lines) + '\r\n')

        written.append(str(talsmpl_path))
        n_zones = sum(len(l) for l in packed)
        print(f"    {len(packed)} layer(s), {n_zones} zone(s)")

    return written


def _write_wav(sample: SampleData, path: str) -> None:
    """Write a 16-bit WAV with a `smpl` chunk carrying the root note (and loop).

    TAL-Sampler reads the sample's root note from the WAV `smpl` chunk's
    MIDIUnityNote for keyboard tracking; without it a key-tracked (track=1)
    multisample plays heavily transposed.  Python's `wave` module can't write
    custom chunks, so assemble the RIFF manually."""
    ch   = max(1, sample.channels)
    sr   = sample.sample_rate or 44100
    data = sample.data
    if len(data) & 1:                 # 16-bit frames must be byte-aligned
        data = data[:-1]

    fmt = struct.pack('<HHIIHH', 1, ch, sr, sr * ch * 2, ch * 2, 16)

    # Root note only — NO loop in the `smpl` chunk.  The loop lives on the TAL
    # multisample (loopstart/endsample); a `smpl` loop ending at the last sample
    # makes TAL's keytrack resampler read one past the buffer → the keytracked
    # zone goes silent (non-resampled track=0 zones tolerate it, which is why
    # only the track=1 zone was affected).
    sample_period = int(1_000_000_000 / sr)
    smpl = struct.pack('<IIIIIIIII',
                       0, 0, sample_period, max(0, min(127, sample.root_note)),
                       0, 0, 0, 0, 0)

    body = (b'fmt ' + struct.pack('<I', len(fmt)) + fmt
            + b'data' + struct.pack('<I', len(data)) + data
            + (b'\x00' if len(data) & 1 else b'')
            + b'smpl' + struct.pack('<I', len(smpl)) + smpl)
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 4 + len(body)) + b'WAVE' + body)
