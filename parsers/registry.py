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


PARSERS = {
    '.e4b':     lambda p, w, **kw: parse_e4b(str(p)),
    '.xpm':     lambda p, w, **kw: parse_xpm(str(p), w),
    '.pgm':     lambda p, w, **kw: parse_pgm(str(p), [w] if w else None),
    '.set':     lambda p, w, **kw: parse_mpc60_set(str(p)),
    '.img':     lambda p, w, **kw: parse_mpc60_img(str(p)),
    '.talsmpl': lambda p, w, **kw: parse_talsmpl(str(p), w),
    '.sfz':     lambda p, w, **kw: parse_sfz(str(p), w),
    '.sf2':     lambda p, w, **kw: parse_sf2(str(p),
                                    max_presets=kw.get('max_presets', 64)),
    '.exs':     lambda p, w, **kw: parse_exs24(str(p), [w] if w else None),
    '.gig':     lambda p, w, **kw: parse_gig(str(p),
                                    max_instruments=kw.get('max_presets', 32),
                                    max_samples=kw.get('max_samples', 512)),
}

INPUT_EXTS = set(PARSERS.keys())
