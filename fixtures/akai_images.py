# SPDX-License-Identifier: GPL-2.0-or-later
#
# mpc2emu — https://github.com/lentferj/mpc2emu
"""AKAI hard-disk images that are broken in one specific way each."""
from __future__ import annotations

import contextlib
import io
import os
import struct
import tempfile
from typing import Optional

from models.common import (Bank, Envelope, Preset, SampleData, VoiceLayer,
                           ZoneMapping)


def _tone(name: str, frames: int = 600, rate: int = 44100) -> SampleData:
    return SampleData(name=name, data=struct.pack('<h', 800) * frames,
                      sample_rate=rate, channels=1, bit_depth=16, root_note=60)


def _one_zone_bank(name: str, samples) -> Bank:
    v = VoiceLayer()
    v.amp_env = Envelope(attack=0.0, decay=0.0, sustain=1.0, release=0.2)
    for i, s in enumerate(samples):
        v.zones.append(ZoneMapping(sample_name=s.name, lo_key=36 + i,
                                   hi_key=36 + i, lo_vel=0, hi_vel=127,
                                   root_key=60))
    p = Preset(name=name, program_number=0)
    p.voices.append(v)
    return Bank(name=name, presets=[p], samples=list(samples))


def unplayable_ssrate_image(path: str, rate: int = 27777) -> str:
    """An image whose samples declare a rate the S3000XL cannot play.

    **Reproduces:** Jan's Vol MPC, 2026-09-13. Every sample carried `SSRATE`
    27777 -- the Emulator II rate -- while the playback index byte said 44100.
    The machine reads the index and ignores SSRATE, so 27777 Hz audio played at
    44100: **+802 cents sharp**, measured on the sampler, against +800.3
    computed from the ratio.

    **Fails against:** a reader that takes the rate from the index byte alone.
    Ours did, and reported a serene 44100 for all 120 samples of the real
    volume -- which is why the first check anyone ran said "all playable" and
    the search went elsewhere for a day. Must raise `AKAI_SSRATE_UNPLAYABLE`.

    Three samples, ~4 kB of audio, against 94 MB for the specimen.
    """
    from writers.akai_s3000_image import build_akai_hd_image
    from writers.akai_s3000_writer import build_akai_volume
    bank = _one_zone_bank('BADRATE', [_tone(f'S{i}', rate=rate) for i in range(3)])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        files = build_akai_volume(bank, bank_name='BADRATE')
        items = list(files.items() if isinstance(files, dict) else files)
        build_akai_hd_image([('BADRATE', items)], path, size_mb=8)
    return path


def full_image_no_free_blocks(path: str, size_mb: int = 2,
                              leave_blocks: int = 8) -> str:
    """An image with a free volume SLOT but not enough free blocks.

    **Reproduces:** the refusal VinSamLib's rebuild path branches on. Distinct
    from having no free slot, and only this one is fixed by a larger image --
    rebuilding for the other would be work for nothing, which is why the two
    are separate fixtures.

    **Fails against:** an appender that grows the FILE instead of refusing.
    Writing past the partition's declared extent is a bytearray slice-assign,
    which APPENDS rather than failing: the image grows, the data lands at the
    wrong offset, the directory points elsewhere, and the call reports success.
    Must raise `AkaiImageError` and emit `AKAI_IMAGE_NO_ROOM` with a non-zero
    `short_blocks` and `had_free_slot` True.

    `leave_blocks` is how much room to leave -- small enough that any real
    volume will not fit, large enough that the disc is not pathologically full.
    """
    from writers.akai_s3000_image import (build_akai_hd_image, HD_BLOCK,
                                          PARTHEAD_BLKS, VOLDIR_HD_BLKS)
    from writers.akai_s3000_writer import build_akai_volume
    total = (size_mb * 1048576) // HD_BLOCK
    hog_blocks = max(1, total - PARTHEAD_BLKS - VOLDIR_HD_BLKS - leave_blocks)
    frames = hog_blocks * HD_BLOCK // 2
    bank = _one_zone_bank('HOG', [_tone('BIG', frames=frames)])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        files = build_akai_volume(bank, bank_name='HOG')
        items = list(files.items() if isinstance(files, dict) else files)
        build_akai_hd_image([('HOG', items)], path, size_mb=size_mb)
    return path


def full_image_no_free_slot(path: str, size_mb: int = 8) -> str:
    """An image with free blocks but every volume slot taken.

    **Reproduces:** the other half of the no-room refusal. A partition holds
    `ROOTDIR_ENTRIES` (100) volumes however much space is left, so a disc can be
    mostly empty and still refuse.

    **Fails against:** code that treats "no room" as one condition. A larger
    image does not help here -- the fix is deleting a volume or using another
    partition -- so a rebuild triggered by this refusal is wasted work, and
    `had_free_slot` False is what tells a caller which case it is in.
    """
    from writers.akai_s3000_image import build_akai_hd_image, ROOTDIR_ENTRIES
    from writers.akai_s3000_writer import build_akai_volume
    vols = []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for i in range(ROOTDIR_ENTRIES):
            bank = _one_zone_bank(f'V{i:03d}', [_tone(f'T{i:03d}', frames=64)])
            files = build_akai_volume(bank, bank_name=f'V{i:03d}')
            vols.append((f'V{i:03d}',
                         list(files.items() if isinstance(files, dict) else files)))
        build_akai_hd_image(vols, path, size_mb=size_mb)
    return path
