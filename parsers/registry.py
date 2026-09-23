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
from parsers.eps_parser       import is_eps_image, parse_eps_image
from parsers.roland_s7xx_parser import is_roland_image, parse_roland_image


def _refuse_aux(p, what):
    """AKAI auxiliary file types: recognised, deliberately not converted."""
    raise ValueError(
        f"{getattr(p, 'name', p)} is {what} — an AKAI file type that carries "
        f"no sample data. Its contents are not documented by any available "
        f"reference and nothing reads them.")


def _accepted(fn, kw: dict) -> dict:
    """The subset of `kw` that `fn` actually declares.

    Blind `**kw` forwarding to a reader with a fixed signature is a
    `TypeError`; silently dropping everything is a no-op the caller cannot
    see. This does neither — it passes what the reader takes, and the caller's
    other options are refused explicitly above rather than vanishing.
    """
    import inspect
    sig = inspect.signature(fn).parameters
    if any(q.kind is inspect.Parameter.VAR_KEYWORD for q in sig.values()):
        return dict(kw)
    return {k: v for k, v in kw.items() if k in sig}


def _dispatch_disk_image(p, w, kw, fallback):
    """Identify a disk image and hand it to the right reader.

    Ordered by how strong each test is, because none of these formats has a
    magic string a reader can rely on:

      AKAI    partition-header magic -- the only real magic here
      EPS     decodes the root directory in block 2
      Roland  no header at all; checks that the FIXED record base holds
              plausible records, which is the weakest test of the three and
              so goes last

    A weaker test must never be offered a disc a stronger one can identify.

    **One dispatcher for every disk-image extension.** `.iso`, `.img` and
    `.hda` are the same question asked about the same bytes; when they each
    had their own answer, two of the three only knew about AKAI.

    ⚠ **`**kw` USED TO BE SWALLOWED HERE**, so every option the caller passed
    -- `max_presets`, `limit`, `firmware_sim` -- was a silent no-op for image
    inputs while working everywhere else. Found by VinSamLib 2026-09-22,
    measured rather than reasoned about. Accepting a keyword and dropping it
    is worse than rejecting it: the caller has no signal at all.
    """
    if is_akai_image(str(p)):
        return parse_akai_image(str(p), w, **kw)
    # ⚠ **THIS USED TO REFUSE `firmware_sim` FOR EVERYTHING BUT AKAI**, when
    # AKAI was the only implemented source. All three are implemented now, so
    # the refusal moved rather than vanished: each reader takes
    # `firmware_sim_target` and refuses a TARGET it has no simulation for,
    # because only the reader knows the source and only the caller knows the
    # target. Flagged as stale by VinSamLib 2026-09-23 -- a comment describing
    # a check that is gone sends a reader looking for it.
    if is_eps_image(str(p)):
        return parse_eps_image(str(p), w, **_accepted(parse_eps_image, kw))
    if is_roland_image(str(p)):
        return parse_roland_image(str(p), w, **_accepted(parse_roland_image, kw))
    return fallback()


def _parse_iso(p, w, **kw):
    """`.iso` — a CD-ROM image from any of the three samplers."""
    # The fallback keeps the old error path: parse_akai_image says plainly
    # what it could not read, which is more useful than "unrecognised".
    return _dispatch_disk_image(
        p, w, kw, fallback=lambda: parse_akai_image(str(p), w, **kw))


def _parse_img(p, w, **kw):
    """`.img` is claimed by more than one format, so dispatch on content.

    ⚠ **THIS USED TO TRY AKAI AND NOTHING ELSE**, so a Roland or Ensoniq
    HARD-DISK image fell through to the MPC60 reader and failed, while the
    same disc as `.iso` read fine. The three-way identification already
    existed — it was wired to one extension. *A dispatcher that is right
    about which formats exist and wrong about where to apply it fails in a
    way that looks like a missing reader.*

    An AKAI floppy or hard-disk image is identified by its partition-header
    magic (or the 0xFF marker in a floppy header), neither of which an MPC60
    disk image carries; MPC60 stays the fallback because it has no test of
    its own.
    """
    return _dispatch_disk_image(p, w, kw, fallback=lambda: parse_mpc60_img(str(p)))


def _parse_hda(p, w, **kw):
    """`.hda` — an EMU/AKAI hard-disk image, dispatched on content.

    Same three-way test as `.iso`. The fallback stays AKAI so an unreadable
    image still produces `parse_akai_image`'s own diagnosis rather than a
    generic one.
    """
    return _dispatch_disk_image(
        p, w, kw, fallback=lambda: parse_akai_image(str(p), w, **kw))


PARSERS = {
    '.e4b':     lambda p, w, **kw: parse_e4b(str(p)),
    '.xpm':     lambda p, w, **kw: parse_xpm(str(p), w,
                                    chromatic_pads=kw.get('chromatic_pads', False)),
    # MPC 3 writes the same gzip+JSON container under three extensions: a bare
    # program is .xpm, a track is .xty and a project is .xpj (confirmed on an
    # MPC One 3.9.0.31, checklist D5).  One reader handles all three — it
    # dispatches on the payload name in the header, not the extension.
    '.xty':     lambda p, w, **kw: parse_xpm(str(p), w,
                                    chromatic_pads=kw.get('chromatic_pads', False)),
    '.xpj':     lambda p, w, **kw: parse_xpm(str(p), w,
                                    chromatic_pads=kw.get('chromatic_pads', False)),
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
    '.a3p':     lambda p, w, **kw: parse_akai_program(
                    str(p), w, firmware_sim=kw.get('firmware_sim', False)),
    '.a3s':     lambda p, w, **kw: parse_akai_sample(str(p)),
    '.s3p':     lambda p, w, **kw: parse_akai_program(
                    str(p), w, firmware_sim=kw.get('firmware_sim', False)),
    '.s3s':     lambda p, w, **kw: parse_akai_sample(str(p)),
    '.p3':      lambda p, w, **kw: parse_akai_program(
                    str(p), w, firmware_sim=kw.get('firmware_sim', False)),
    '.s3':      lambda p, w, **kw: parse_akai_sample(str(p)),
    '.p1':      lambda p, w, **kw: parse_akai_program(
                    str(p), w, firmware_sim=kw.get('firmware_sim', False)),
    '.s1':      lambda p, w, **kw: parse_akai_sample(str(p)),
    # AKAI disk images: an S3000 hard disk (SCSI/ZuluSCSI), a CD3000 CD-ROM
    # or a floppy.  `.img` is shared with the MPC60 and sniffs on content
    # (above); `.hda` and `.iso` are only produced as AKAI media by anything
    # we can read back, and `parse_akai_image` says so plainly if they are not.
    '.hda':     _parse_hda,
    '.iso':     _parse_iso,
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

#: ⚠ **Source extensions for which `--firmware-sim` is actually implemented.**
#:
#: The flag reproduces a specific sampler's specific importer, so it is
#: meaningful only for source/target pairs whose firmware has been read. Any
#: other combination must be **refused**, never silently converted the normal
#: way: a user who asks for a device-faithful import and receives this
#: project's own conversion has no way to tell from the output, and would
#: then diff it against hardware and conclude the firmware read is wrong.
FIRMWARE_SIM_EXTS = frozenset({
    '.a3p', '.s3p', '.p3', '.p1',      # AKAI program files
    '.iso', '.img', '.hda',            # disk images -- the actual format is
                                       # identified at parse time, and a
                                       # non-AKAI disc is refused there
})

#: Target formats with a firmware simulation behind them.
FIRMWARE_SIM_FORMATS = frozenset({'e4b', 'krz'})
