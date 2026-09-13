# SPDX-License-Identifier: GPL-2.0-or-later
#
# mpc2emu — https://github.com/lentferj/mpc2emu
"""MPC keygroup programs (XPM + WAVs) that are broken in one specific way each.

Each generator writes a small directory and returns the path to the `.xpm`.
Nothing here exceeds a few hundred kB; the real specimens they stand for run to
tens of megabytes inside libraries of tens of thousands of files.

**`<RootNote>` IN XPM XML IS 1-BASED.** `<RootNote>36</RootNote>` is MIDI 35.
Verified in `xpm_parser` across 71 layers of three files, and the first draft of
these fixtures got it wrong and produced a plausible off-by-one -- exactly the
kind of fault a fixture must not invent, since it would be indistinguishable
from one in the code under test.
"""
from __future__ import annotations

import math
import os
import struct
import wave
from typing import Optional, Sequence, Tuple


def _wav(path: str, root: int, secs: float = 1.0, sr: int = 44100,
         pitch_fraction: Optional[int] = None, decay: bool = True,
         loop: bool = True) -> None:
    """A tone with an optional `smpl` chunk carrying a loop and/or a fraction."""
    n = int(sr * secs)
    f0 = 440.0 * 2 ** ((root - 69) / 12.0)
    fr = bytearray()
    for k in range(n):
        env = max(0.0, 1.0 - k / (n * 0.45)) if decay else 1.0
        v = math.sin(2 * math.pi * f0 * k / sr) * env
        fr += struct.pack('<h', int(max(-1.0, min(1.0, v)) * 20000))
    w = wave.open(path, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(bytes(fr)); w.close()
    if pitch_fraction is None and not loop:
        return
    d = bytearray(open(path, 'rb').read())
    smpl = bytearray(36 + (24 if loop else 0))
    struct.pack_into('<I', smpl, 12, root)                     # MIDIUnityNote
    struct.pack_into('<I', smpl, 16, pitch_fraction or 0)      # MIDIPitchFraction
    if loop:
        struct.pack_into('<I', smpl, 28, 1)                    # numSampleLoops
        struct.pack_into('<I', smpl, 36 + 8, 0)                # loop start
        struct.pack_into('<I', smpl, 36 + 12, n - 1)           # loop end
    chunk = b'smpl' + struct.pack('<I', len(smpl)) + bytes(smpl)
    d[4:8] = struct.pack('<I', struct.unpack('<I', d[4:8])[0] + len(chunk))
    open(path, 'wb').write(bytes(d) + chunk)


def _xpm(path: str, name: str,
         zones: Sequence[Tuple[int, int, int, str]]) -> None:
    """zones: (lo_key, hi_key, root_midi, sample_stem). RootNote is written +1."""
    kgs = ''.join(
        f'''    <Instrument number="{i + 1}">
      <LowNote>{lo}</LowNote><HighNote>{hi}</HighNote>
      <IgnoreBaseNote>False</IgnoreBaseNote>
      <Layers>
        <Layer number="1">
          <SampleName>{stem}</SampleName><SampleFile></SampleFile>
          <RootNote>{root + 1}</RootNote><SampleStart>0</SampleStart>
          <Loop><LoopMode>Off</LoopMode></Loop>
          <Volume>1.0</Volume><Pan>0.5</Pan>
          <TuneCoarse>0</TuneCoarse><TuneFine>0</TuneFine>
        </Layer>
      </Layers>
    </Instrument>\n''' for i, (lo, hi, root, stem) in enumerate(zones))
    with open(path, 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<MPCVObject><Version><File_Version>2.1</File_Version></Version>\n'
                ' <Program type="Keygroup">\n'
                f'  <ProgramName>{name}</ProgramName>\n'
                f'  <KeygroupNumKeygroups>{len(zones)}</KeygroupNumKeygroups>\n'
                '  <Instruments>\n' + kgs + '  </Instruments>\n'
                ' </Program></MPCVObject>\n')


def looped_pad_a_tail_trim_cuts(directory: str, n_zones: int = 5) -> str:
    """Sustained, looped samples whose loops reach into the trimmed tail.

    **Reproduces:** `MPC Prophet/Pad-PRO5 Lunar Daze.xpm` on Jan's volume --
    16 looped samples, **15 loops dropped** by a tail trim, and one sample on a
    sibling preset cut by 63%. Nothing reached the user: the drop was announced
    with a bare `print`, and VinSamLib surface diagnostic records.

    **Fails against:** `--trim-tail` defaulting to drop, and against a loop drop
    that is not a record. Must emit `TRIM_TAIL_LOOP_DROPPED` per sample, with
    `content_lost=True`, and must emit nothing when loops are kept.

    Each sample decays to silence well before its end, so a 72 dB trim has a
    real tail to cut, and the loop spans the whole file so the cut lands inside
    it -- which is the condition, not the trim length.
    """
    os.makedirs(directory, exist_ok=True)
    zones = []
    for i in range(n_zones):
        root = 36 + 12 * i
        _wav(os.path.join(directory, f'PAD{i}.wav'), root, secs=1.0,
             decay=True, loop=True)
        zones.append((30 + 12 * i, 41 + 12 * i, root, f'PAD{i}'))
    p = os.path.join(directory, 'LoopedPad.xpm')
    _xpm(p, 'LoopedPad', zones)
    return p


def pitch_fraction_sentinel(directory: str) -> str:
    """One sample whose `smpl` MIDIPitchFraction is `0xFFFFFFFF`.

    **Reproduces:** `The Vault 2.0`, where **2062 of 7790 WAVs** carry it --
    exactly one library of the 45 scanned. Read as `round(0xFFFFFFFF / 2**32 *
    100)` it becomes **100 cents**, and 100 cents is a whole semitone, which the
    AKAI writer then stored as 256 tune units. Seven of sixteen samples in one
    drum kit played a semitone sharp; the kit's own XPM says `TuneFine 0`, so
    the authoring tool meant "unset".

    **Fails against:** a reader that treats the all-ones value as a tuning, and
    against any rounding that lets a FRACTION of a semitone reach a whole one.
    The parser must return `None` here and a neighbouring 0x00000000 must read
    as 0.
    """
    os.makedirs(directory, exist_ok=True)
    _wav(os.path.join(directory, 'SENT.wav'), 60, pitch_fraction=0xFFFFFFFF,
         loop=False)
    _wav(os.path.join(directory, 'CLEAN.wav'), 62, pitch_fraction=0x00000000,
         loop=False)
    p = os.path.join(directory, 'Sentinel.xpm')
    _xpm(p, 'Sentinel', [(59, 61, 60, 'SENT'), (62, 64, 62, 'CLEAN')])
    return p


def inconsistent_declared_roots(directory: str) -> str:
    """A program where one sample's audio is an octave from its declared root.

    **Reproduces:** the shape I wrongly attributed to Jan's library. The point
    of having it as a FIXTURE is that here the inconsistency is real and known,
    so anything downstream can be tested without a pitch detector in the loop.

    **Fails against:** code that assumes a declared root describes the audio.
    Deliberately NOT a test of pitch analysis: two of my own detector readings
    on real material were octave errors in opposite directions, so nothing here
    should depend on measuring pitch to know what this file contains.
    """
    os.makedirs(directory, exist_ok=True)
    # LOW sounds an octave below what it claims; TRUE is honest.
    _wav(os.path.join(directory, 'LOW.wav'), 36, loop=False)      # audio at 36
    _wav(os.path.join(directory, 'TRUE.wav'), 60, loop=False)
    p = os.path.join(directory, 'Inconsistent.xpm')
    _xpm(p, 'Inconsistent', [(42, 53, 48, 'LOW'),                 # claims 48
                             (54, 65, 60, 'TRUE')])
    return p


def thinnable_preset(directory: str, n_zones: int = 8) -> str:
    """Enough distinct zones that a memory target must thin them.

    **Reproduces:** the case `--shrink-to` exists for. Zones carry audibly
    different timbres so the planner's centroid cost has something real to rank;
    an eight-zone program of identical tones would make every plan score the
    same and the fixture would prove nothing.

    **Fails against:** a planner that cannot reach a target, and -- with a
    target below one sample per voice -- must emit
    `SHRINK_TARGET_UNREACHABLE`, because thinning frees whole samples at a time
    and cannot go below that floor.
    """
    os.makedirs(directory, exist_ok=True)
    zones = []
    for i in range(n_zones):
        root = 36 + 6 * i
        path = os.path.join(directory, f'Z{i}.wav')
        # brighter with each zone: a real centroid spread to rank
        n, sr = 44100 // 2, 44100
        f0 = 440.0 * 2 ** ((root - 69) / 12.0)
        fr = bytearray()
        for k in range(n):
            v = sum(math.sin(2 * math.pi * f0 * h * k / sr) / h
                    for h in range(1, 2 + 4 * i))
            fr += struct.pack('<h', int(max(-1.0, min(1.0, v / 2)) * 20000))
        w = wave.open(path, 'wb')
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(bytes(fr)); w.close()
        zones.append((33 + 6 * i, 38 + 6 * i, root, f'Z{i}'))
    p = os.path.join(directory, 'Thinnable.xpm')
    _xpm(p, 'Thinnable', zones)
    return p
