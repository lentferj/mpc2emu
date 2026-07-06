# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025  mpc2emu contributors
#
# This file is part of mpc2emu.
# Independent reimplementation from the public SoundFont 2.04 File
# Specification (E-mu Systems / Creative Technology Ltd.).
# SF2 knowledge additionally informed by libgig (GPL-2.0-or-later),
# Copyright (C) 2003-2021 Christian Schoenebeck <cuse@users.sourceforge.net>,
# https://www.linuxsampler.org/libgig/ — no source code copied.
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
SoundFont 2 (.sf2) Parser
--------------------------
SF2 is a RIFF-based binary format with the following top-level chunks:

  RIFF 'sfbk'
    LIST 'INFO'   — version, name, copyright, etc.
    LIST 'sdta'   — sample data
      smpl        — 16-bit PCM sample pool (all samples concatenated)
      sm24        — optional 24-bit extension bytes (ignored here)
    LIST 'pdta'   — preset/instrument/sample headers
      phdr[38]    — preset headers
      pbag[4]     — preset index list
      pmod[10]    — preset modulators
      pgen[4]     — preset generators
      inst[22]    — instrument headers
      ibag[4]     — instrument index list
      imod[10]    — instrument modulators
      igen[4]     — instrument generators
      shdr[46]    — sample headers

Key generator IDs (subset we use):
  0   startAddrsOffset
  1   endAddrsOffset
  4   startloopAddrsOffset
  5   endloopAddrsOffset
  17  pan          (-500..+500 permil, 0=center)
  41  instrument   (preset gen → instrument index)
  43  keyRange     (lo=byte0, hi=byte1)
  44  velRange
  53  sampleID     (instrument gen → sample index)
  54  sampleModes  (bit 0 = loop, bit 1 = ping-pong)
  58  overridingRootKey (MIDI note, 255=use sample header)

References:
  - "SoundFont 2.04 File Specification" (E-mu / Creative)
  - libsndfile sf2 reader
  - sftools source
"""

import struct
from pathlib import Path
from typing import Optional, List, Tuple, Dict

from models.common import (
    Bank, Preset, VoiceLayer, ZoneMapping, SampleData, LoopType,
    cents_to_filter_env_amount, lfo_pitch_depth_to_amount,
)
from parsers.xpm_parser import _safe_name


# ---------------------------------------------------------------------------
# RIFF reader helpers
# ---------------------------------------------------------------------------

class _RiffReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos  = 0

    def read(self, n: int) -> bytes:
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def seek(self, pos: int):
        self.pos = pos

    def tell(self) -> int:
        return self.pos

    def u16(self) -> int:
        v = struct.unpack_from('<H', self.data, self.pos)[0]
        self.pos += 2
        return v

    def i16(self) -> int:
        v = struct.unpack_from('<h', self.data, self.pos)[0]
        self.pos += 2
        return v

    def u32(self) -> int:
        v = struct.unpack_from('<I', self.data, self.pos)[0]
        self.pos += 4
        return v

    def str(self, n: int) -> str:
        return self.read(n).split(b'\x00')[0].decode('ascii', errors='replace')


def _find_chunks(data: bytes, parent_offset: int,
                 parent_size: int) -> Dict[str, Tuple[int, int]]:
    """Return dict of chunk_id -> (offset_of_data, size)."""
    chunks = {}
    pos    = parent_offset
    end    = parent_offset + parent_size
    while pos + 8 <= end:
        chunk_id = data[pos:pos+4].decode('ascii', errors='replace')
        size     = struct.unpack_from('<I', data, pos+4)[0]
        data_off = pos + 8
        if chunk_id in ('RIFF', 'LIST'):
            # For RIFF/LIST, the first 4 bytes of data are the type
            list_type = data[data_off:data_off+4].decode('ascii', errors='replace')
            chunks[list_type] = (data_off + 4, size - 4)
        else:
            chunks[chunk_id] = (data_off, size)
        pos = data_off + size
        if size % 2:
            pos += 1  # RIFF word alignment
    return chunks


# ---------------------------------------------------------------------------
# pdta struct parsers
# ---------------------------------------------------------------------------

PHDR_SIZE = 38
PBAG_SIZE = 4
PGEN_SIZE = 4
INST_SIZE = 22
IBAG_SIZE = 4
IGEN_SIZE = 4
SHDR_SIZE = 46


def _parse_shdr(data: bytes, offset: int, count: int) -> list:
    """Parse sample headers."""
    samples = []
    for i in range(count):
        o = offset + i * SHDR_SIZE
        name       = data[o:o+20].split(b'\x00')[0].decode('ascii', errors='replace')
        start      = struct.unpack_from('<I', data, o+20)[0]
        end        = struct.unpack_from('<I', data, o+24)[0]
        loop_start = struct.unpack_from('<I', data, o+28)[0]
        loop_end   = struct.unpack_from('<I', data, o+32)[0]
        sample_rate= struct.unpack_from('<I', data, o+36)[0]
        orig_pitch = data[o+40]
        pitch_corr = struct.unpack_from('<b', data, o+41)[0]
        sample_link= struct.unpack_from('<H', data, o+42)[0]
        sample_type= struct.unpack_from('<H', data, o+44)[0]
        samples.append({
            'name': name, 'start': start, 'end': end,
            'loop_start': loop_start, 'loop_end': loop_end,
            'sample_rate': sample_rate, 'orig_pitch': orig_pitch,
            'pitch_corr': pitch_corr, 'sample_type': sample_type,
        })
    return samples


def _parse_inst(data: bytes, offset: int, count: int) -> list:
    insts = []
    for i in range(count):
        o    = offset + i * INST_SIZE
        name = data[o:o+20].split(b'\x00')[0].decode('ascii', errors='replace')
        bag  = struct.unpack_from('<H', data, o+20)[0]
        insts.append({'name': name, 'bag_index': bag})
    return insts


def _parse_phdr(data: bytes, offset: int, count: int) -> list:
    phdrs = []
    for i in range(count):
        o    = offset + i * PHDR_SIZE
        name = data[o:o+20].split(b'\x00')[0].decode('ascii', errors='replace')
        preset_num = struct.unpack_from('<H', data, o+20)[0]
        bank_num   = struct.unpack_from('<H', data, o+22)[0]
        bag_index  = struct.unpack_from('<H', data, o+24)[0]
        phdrs.append({'name': name, 'preset': preset_num,
                      'bank': bank_num, 'bag_index': bag_index})
    return phdrs


def _parse_bags(data: bytes, offset: int, count: int, item_size: int) -> list:
    bags = []
    for i in range(count):
        o      = offset + i * item_size
        gen_idx = struct.unpack_from('<H', data, o)[0]
        mod_idx = struct.unpack_from('<H', data, o+2)[0]
        bags.append({'gen_index': gen_idx, 'mod_index': mod_idx})
    return bags


def _parse_gens(data: bytes, offset: int, count: int) -> list:
    """Parse generator list. Each is (oper:u16, amount:i16 or 2×u8)."""
    gens = []
    for i in range(count):
        o    = offset + i * IGEN_SIZE
        oper = struct.unpack_from('<H', data, o)[0]
        lo   = data[o+2]
        hi   = data[o+3]
        amt  = struct.unpack_from('<h', data, o+2)[0]
        gens.append({'oper': oper, 'lo': lo, 'hi': hi, 'amt': amt})
    return gens


def _gens_to_dict(gens: list) -> dict:
    return {g['oper']: g for g in gens}


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_sf2(sf2_path: str, max_presets: int = 64) -> Bank:
    """
    Parse a SoundFont 2 file into a Bank object.

    Args:
        sf2_path:     Path to the .sf2 file
        max_presets:  Maximum number of presets to import (large SF2s can
                      have hundreds; default 64 keeps memory reasonable)

    Returns:
        Bank with one Preset per SF2 instrument preset.
    """
    p = Path(sf2_path).resolve()
    print(f"Parsing SF2: {p.name}")

    data = p.read_bytes()

    # Verify RIFF sfbk header
    if data[:4] != b'RIFF' or data[8:12] != b'sfbk':
        raise ValueError(f"Not a valid SF2 file: {p.name}")

    # Parse top-level chunks inside sfbk
    top = _find_chunks(data, 12, len(data) - 12)
    # Required LIST chunks — give a clear error rather than a KeyError on a
    # malformed / non-standard SF2 (e.g. an SFX bank with no pdta).
    if 'pdta' not in top:
        raise ValueError("Not a valid SF2: missing 'pdta' LIST chunk")

    # sdta — sample data (optional: a bank may be ROM-only / no samples)
    smpl_data = b''
    if 'sdta' in top:
        sdta = _find_chunks(data, top['sdta'][0], top['sdta'][1])
        smpl_off, smpl_size = sdta.get('smpl', (0, 0))
        smpl_data = data[smpl_off:smpl_off + smpl_size]  # raw 16-bit PCM pool

    # pdta — preset/instrument/sample headers
    pdta = _find_chunks(data, top['pdta'][0], top['pdta'][1])

    def _pdta(key, item_size):
        off, size = pdta.get(key, (0, 0))
        return off, size // item_size

    shdr_off, shdr_cnt  = _pdta('shdr', SHDR_SIZE)
    inst_off, inst_cnt  = _pdta('inst', INST_SIZE)
    ibag_off, ibag_cnt  = _pdta('ibag', IBAG_SIZE)
    igen_off, igen_cnt  = _pdta('igen', IGEN_SIZE)
    phdr_off, phdr_cnt  = _pdta('phdr', PHDR_SIZE)
    pbag_off, pbag_cnt  = _pdta('pbag', PBAG_SIZE)
    pgen_off, pgen_cnt  = _pdta('pgen', PGEN_SIZE)

    shdrs  = _parse_shdr(data, shdr_off, shdr_cnt)
    insts  = _parse_inst(data, inst_off, inst_cnt)
    ibags  = _parse_bags(data, ibag_off, ibag_cnt, IBAG_SIZE)
    igens  = _parse_gens(data, igen_off, igen_cnt)
    phdrs  = _parse_phdr(data, phdr_off, phdr_cnt)
    pbags  = _parse_bags(data, pbag_off, pbag_cnt, PBAG_SIZE)
    pgens  = _parse_gens(data, pgen_off, pgen_cnt)

    print(f"  SF2: {phdr_cnt-1} presets, {inst_cnt-1} instruments, "
          f"{shdr_cnt-1} samples")

    bank = Bank(name=_safe_name(p.stem))

    # Pre-extract all samples from the smpl pool
    sample_objects: Dict[int, SampleData] = {}
    used_names: set = set()   # CR-7b: keep 16-char-truncated names unique

    def _get_sample(idx: int) -> Optional[SampleData]:
        if idx in sample_objects:
            return sample_objects[idx]
        if idx >= len(shdrs) - 1:
            return None
        sh   = shdrs[idx]
        name = _safe_name(sh['name'])
        # SF2 sample_type: 1=mono, 2=right, 4=left, 8=linked, 0x8000=ROM
        if sh['sample_type'] & 0x8000:
            return None  # ROM sample, skip
        # CR-7b: distinct SF2 samples whose names truncate to the same 16 chars
        # must not share a name, or zones resolve to the wrong sample/root.
        if name in used_names:
            base, i = name, 1
            while name in used_names:
                suf = str(i)
                name = base[:16 - len(suf)] + suf
                i += 1
        used_names.add(name)
        start = sh['start'] * 2
        end   = sh['end']   * 2
        if end <= start or end > len(smpl_data):
            return None
        raw = smpl_data[start:end]
        sd  = SampleData(
            name        = name,
            data        = raw,
            sample_rate = sh['sample_rate'],
            channels    = 1,
            bit_depth   = 16,
            root_note   = sh['orig_pitch'],
            fine_tune   = sh['pitch_corr'],
            loop_start  = max(0, sh['loop_start'] - sh['start']),
            loop_end    = max(0, sh['loop_end']   - sh['start']),
        )
        sample_objects[idx] = sd
        return sd

    # Iterate presets (last phdr is sentinel "EOP")
    n_presets = min(max_presets, phdr_cnt - 1)
    for pi in range(n_presets):
        ph   = phdrs[pi]
        name = _safe_name(ph['name']) or f"Preset{pi}"

        preset = Preset(name=name, program_number=ph['preset'])
        voice  = VoiceLayer()

        # Iterate preset bags → generators → instrument index
        p_bag_start = ph['bag_index']
        p_bag_end   = phdrs[pi+1]['bag_index']

        for pb_idx in range(p_bag_start, p_bag_end):
            pg_start = pbags[pb_idx]['gen_index']
            pg_end   = pbags[pb_idx+1]['gen_index'] if pb_idx+1 < pbag_cnt else pgen_cnt
            pg_dict  = _gens_to_dict(pgens[pg_start:pg_end])

            inst_idx = pg_dict.get(41, {}).get('amt', -1)  # gen 41 = instrument
            if inst_idx < 0 or inst_idx >= inst_cnt - 1:
                continue

            inst = insts[inst_idx]
            ib_start = inst['bag_index']
            ib_end   = insts[inst_idx+1]['bag_index']

            for ib_idx in range(ib_start, ib_end):
                ig_start = ibags[ib_idx]['gen_index']
                ig_end   = ibags[ib_idx+1]['gen_index'] if ib_idx+1 < ibag_cnt else igen_cnt
                ig_dict  = _gens_to_dict(igens[ig_start:ig_end])

                samp_idx = ig_dict.get(53, {}).get('amt', -1)  # gen 53 = sampleID
                if samp_idx < 0:
                    continue

                sd = _get_sample(samp_idx)
                if sd is None:
                    continue
                if sd.name not in {s.name for s in bank.samples}:
                    bank.samples.append(sd)

                # Key/vel range
                lo_k = ig_dict.get(43, {}).get('lo', 0)
                hi_k = ig_dict.get(43, {}).get('hi', 127)
                lo_v = ig_dict.get(44, {}).get('lo', 0)
                hi_v = ig_dict.get(44, {}).get('hi', 127)

                # overridingRootKey (gen 58)
                root = ig_dict.get(58, {}).get('amt', -1)
                if root < 0 or root > 127:
                    root = sd.root_note

                # Pan: gen 17, range -500..+500 permil
                pan_permil = ig_dict.get(17, {}).get('amt', 0)
                pan = max(-1.0, min(1.0, pan_permil / 500.0))

                # Loop mode: gen 54 (sampleModes).  CR-8: SF2 has NO ping-pong —
                # 1=loop continuous → FORWARD, 3=loop-then-remainder-on-release →
                # FORWARD_REL, 0/2=no loop.  (The old `& 2 → ALTERNATING` made
                # write_e4b bake reversed PCM into the sustain → garbled sound.)
                loop_flags = ig_dict.get(54, {}).get('amt', 0)
                if loop_flags == 1:
                    sd.loop_type = LoopType.FORWARD
                elif loop_flags == 3:
                    sd.loop_type = LoopType.FORWARD_REL

                zone = ZoneMapping(
                    sample_name = sd.name,
                    lo_key      = lo_k,
                    hi_key      = hi_k,
                    lo_vel      = lo_v,
                    hi_vel      = hi_v,
                    root_key    = root,
                    pan         = pan,
                )
                voice.zones.append(zone)

                # Envelope from instrument zone gens (timecents → seconds).
                # SF2 2.04 vol envelope: 34=attackVolEnv, 36=decayVolEnv,
                # 37=sustainVolEnv (centibels, 0=full, 1440=silence), 38=releaseVolEnv
                def _tc(gen_id, default_s):
                    tc = ig_dict.get(gen_id, {}).get('amt', None)
                    if tc is None:
                        return default_s
                    return max(0.001, 2 ** (tc / 1200.0))

                if len(voice.zones) == 1:
                    voice.env_attack  = _tc(34, 0.001)
                    voice.env_decay   = _tc(36, 0.3)
                    sus_cb = ig_dict.get(37, {}).get('amt', 0)
                    voice.env_sustain = max(0.0, min(1.0, 1.0 - sus_cb / 1440.0))
                    voice.env_release = _tc(38, 0.5)

                    # Filter envelope: the modulation envelope drives the cutoff
                    # via modEnvToFilterFc.  SF2 2.04 mod-env gens:
                    # 26=attackModEnv, 28=decayModEnv, 29=sustainModEnv (0.1%
                    # decrease), 30=releaseModEnv (timecents); 11=modEnvToFilterFc
                    # (cents = the envelope's filter depth/amount).
                    me_amt = ig_dict.get(11, {}).get('amt', 0)
                    if me_amt:
                        voice.filter_env_amount  = cents_to_filter_env_amount(me_amt)
                        voice.filter_env_attack  = _tc(26, 0.0)
                        voice.filter_env_decay   = _tc(28, 0.3)
                        sus_pm = ig_dict.get(29, {}).get('amt', 0)  # 0.1% units
                        voice.filter_env_sustain = max(0.0, min(1.0, 1.0 - sus_pm / 1000.0))
                        voice.filter_env_release = _tc(30, 0.0)

                    # LFOs.  SF2 has a triangle Mod-LFO (→ pitch/filter/volume)
                    # and a triangle Vib-LFO (→ pitch).  Map Mod-LFO → E4B LFO1,
                    # Vib-LFO → LFO2.  Generators: 5=modLfoToPitch, 10=modLfo→
                    # FilterFc, 22=freqModLFO, 6=vibLfoToPitch, 24=freqVibLFO
                    # (all cents; freq is absolute cents, Hz=8.176·2^(c/1200)).
                    def _abs_cents_hz(gen_id):
                        c = ig_dict.get(gen_id, {}).get('amt', None)
                        return 8.176 * 2 ** (c / 1200.0) if c is not None else None
                    mod_pitch  = ig_dict.get(5,  {}).get('amt', 0)
                    mod_cutoff = ig_dict.get(10, {}).get('amt', 0)
                    if mod_pitch or mod_cutoff:
                        voice.lfo1_shape     = 'triangle'
                        voice.lfo1_rate      = _abs_cents_hz(22) or 8.176
                        if mod_pitch:
                            voice.lfo1_to_pitch  = lfo_pitch_depth_to_amount(mod_pitch)
                        if mod_cutoff:
                            voice.lfo1_to_filter = cents_to_filter_env_amount(mod_cutoff)
                    vib_pitch = ig_dict.get(6, {}).get('amt', 0)
                    if vib_pitch:
                        voice.lfo2_shape    = 'triangle'
                        voice.lfo2_rate     = _abs_cents_hz(24) or 8.176
                        voice.lfo2_to_pitch = lfo_pitch_depth_to_amount(vib_pitch)

        if voice.zones:
            preset.voices.append(voice)
            bank.presets.append(preset)
            print(f"  Preset '{name}': {len(voice.zones)} zone(s)")

    print(f"  Loaded {len(bank.presets)} presets, {len(bank.samples)} samples")
    return bank
