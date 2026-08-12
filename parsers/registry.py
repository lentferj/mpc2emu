# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# Original work.

"""
Single input-format → parser registry (CR-17).

`convert.py` and `info_cmd.py` previously each carried their own copy of this
table, with slightly different lambda signatures — and they had already drifted.
This is now the one source of truth.

Each entry is `ext -> callable(path, wav_dir, **kw) -> Bank`.  Callers that have
no extra options just call `parser(path, wav_dir)`; `convert.py` forwards CLI
tuning via `parser(path, wav_dir, **extra_kwargs)` (`max_presets`, `max_samples`).
"""

from parsers.e4b_parser      import parse_e4b
from parsers.xpm_parser      import parse_xpm
from parsers.pgm_parser      import parse_pgm
from parsers.mpc60_parser    import parse_mpc60_set, parse_mpc60_img
from parsers.talsmpl_parser  import parse_talsmpl
from parsers.sfz_parser      import parse_sfz
from parsers.sf2_parser      import parse_sf2
from parsers.exs24_parser    import parse_exs24
from parsers.gig_parser      import parse_gig
from parsers.krz_parser      import parse_krz
from parsers.eiii_parser     import parse_eiii
from parsers.akai_s3000_parser import parse_akai_program, parse_akai_sample
from parsers.akai_image_parser import is_akai_image, parse_akai_image


def _refuse_aux(p, what):
    """AKAI auxiliary file types: recognised, deliberately not converted."""
    raise ValueError(
        f"{getattr(p, 'name', p)} is {what} — an AKAI file type that carries "
        f"no sample data. Its contents are not documented by any available "
        f"reference and nothing reads them.")


def _parse_img(p, w, **kw):
    """`.img` is claimed by more than one format, so dispatch on content.

    An AKAI floppy or hard-disk image is identified by its partition-header
    magic (or the 0xFF marker in a floppy header), neither of which an MPC60
    disk image carries.
    """
    if is_akai_image(str(p)):
        return parse_akai_image(str(p), w)
    return parse_mpc60_img(str(p))


PARSERS = {
    '.e4b':     lambda p, w, **kw: parse_e4b(str(p)),
    '.xpm':     lambda p, w, **kw: parse_xpm(str(p), w),
    # MPC 3 writes the same gzip+JSON container under three extensions: a bare
    # program is .xpm, a track is .xty and a project is .xpj (confirmed on an
    # MPC One 3.9.0.31, checklist D5).  One reader handles all three — it
    # dispatches on the payload name in the header, not the extension.
    '.xty':     lambda p, w, **kw: parse_xpm(str(p), w),
    '.xpj':     lambda p, w, **kw: parse_xpm(str(p), w),
    '.pgm':     lambda p, w, **kw: parse_pgm(str(p), [w] if w else None),
    '.set':     lambda p, w, **kw: parse_mpc60_set(str(p)),
    '.img':     _parse_img,
    '.talsmpl': lambda p, w, **kw: parse_talsmpl(str(p), w),
    '.sfz':     lambda p, w, **kw: parse_sfz(str(p), w),
    '.sf2':     lambda p, w, **kw: parse_sf2(str(p),
                                    max_presets=kw.get('max_presets', 64)),
    '.exs':     lambda p, w, **kw: parse_exs24(str(p), [w] if w else None),
    '.gig':     lambda p, w, **kw: parse_gig(str(p),
                                    max_instruments=kw.get('max_presets', 32),
                                    max_samples=kw.get('max_samples', 512)),
    '.krz':     lambda p, w, **kw: parse_krz(str(p)),
    '.e3x':     lambda p, w, **kw: parse_eiii(str(p)),
    '.esi':     lambda p, w, **kw: parse_eiii(str(p)),
    '.e3b':     lambda p, w, **kw: parse_eiii(str(p)),
    # AKAI S3000-series. Two naming conventions exist and both are read.
    # `.S3`/`.P3` is the sampler's own: akaiutil derives the directory-entry
    # file-type byte from `.<letter><generation>` (s=sample, p=program;
    # 3=S3000, 1=S1000), and it REFUSES anything else -- verified by having it
    # import our output. `.a3s`/`.a3p` is what several extraction tools emit.
    '.a3p':     lambda p, w, **kw: parse_akai_program(str(p), w),
    '.a3s':     lambda p, w, **kw: parse_akai_sample(str(p)),
    '.s3p':     lambda p, w, **kw: parse_akai_program(str(p), w),
    '.s3s':     lambda p, w, **kw: parse_akai_sample(str(p)),
    '.p3':      lambda p, w, **kw: parse_akai_program(str(p), w),
    '.s3':      lambda p, w, **kw: parse_akai_sample(str(p)),
    '.p1':      lambda p, w, **kw: parse_akai_program(str(p), w),
    '.s1':      lambda p, w, **kw: parse_akai_sample(str(p)),
    # AKAI disk images: an S3000 hard disk (SCSI/ZuluSCSI), a CD3000 CD-ROM
    # or a floppy.  `.img` is shared with the MPC60 and sniffs on content
    # (above); `.hda` and `.iso` are only produced as AKAI media by anything
    # we can read back, and `parse_akai_image` says so plainly if they are not.
    '.hda':     lambda p, w, **kw: parse_akai_image(str(p), w),
    '.iso':     lambda p, w, **kw: parse_akai_image(str(p), w),
    # AKAI auxiliary types carry no sample data, and they must not fall
    # through to a caller that decides "program or sample" by trying parsers:
    # an effects file opens with the same block id a program does, so 90 `.X`
    # files on one library disc otherwise read as 90 phantom programs with key
    # ranges like 200-0. Named here so they refuse with a reason.
    '.x':       lambda p, w, **kw: _refuse_aux(p, 'an effects file'),
    '.q':       lambda p, w, **kw: _refuse_aux(p, 'a cue list'),
    '.d':       lambda p, w, **kw: _refuse_aux(p, 'a drum-input file'),
    '.t':       lambda p, w, **kw: _refuse_aux(p, 'a take list'),
    '.cd':      lambda p, w, **kw: _refuse_aux(p, 'a CD3000 setup file'),
    '.m3':      lambda p, w, **kw: _refuse_aux(p, 'a multi'),
}

INPUT_EXTS = set(PARSERS.keys())
