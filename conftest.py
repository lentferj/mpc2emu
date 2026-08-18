# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# Part of mpc2emu — https://github.com/lentferj/mpc2emu
# Contributions: Jan Lentfer, with AI assistance (see README).
"""Keep the test suite's scratch space off the system temp volume.

The suite needs **~420 MB** of free space for `tmp_path` — nearly all of it the
AKAI image tests, which build 16 MB disk images, several of them necessarily so
because their golden hashes are of 16 MB images `akaiutil` produced.

On a machine where `/tmp` is its own small volume that is enough to fill it,
and a full `/tmp` does not look like a disk problem: it looks like ~25 failures
clustered in `test_akai_image.py`. That happened, cost real time, and is
written up in `docs/RELEASE_MATRIX.md`.

So the suite writes under `~/temp/` instead, which is where
`CLAUDE.md` already says this project's test output belongs.

**Why a dedicated subdirectory and not `~/temp` itself:** passing
`--basetemp` tells pytest to *delete and recreate that directory at the start
of every run*. Pointed at `~/temp` that would destroy the corpus, the fixtures
and everything else the project keeps there. It therefore only ever points at
one path that nothing else uses, and only creates it if the parent exists.

Override at any time with an explicit `--basetemp=...`, which is honoured
unchanged.
"""

import os
import tempfile
from pathlib import Path

#: Nothing but pytest may use this directory — see the module docstring.
_BASETEMP = Path.home() / 'temp' / 'pytest-mpc2emu'


def pytest_configure(config):
    # An explicit --basetemp on the command line always wins.
    if config.option.basetemp:
        return
    if not _BASETEMP.parent.is_dir():
        return                      # no ~/temp here: leave pytest's default
    _BASETEMP.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(_BASETEMP)
    # Tests and subprocesses that reach for `tempfile` directly rather than
    # for `tmp_path` would otherwise still land on the system volume.
    os.environ.setdefault('TMPDIR', str(_BASETEMP))
    # AND THE MODULE'S OWN CACHE, WHICH THE ENVIRONMENT VARIABLE CANNOT REACH
    # ONCE IT IS SET.
    #
    # `tempfile` resolves its directory ONCE, on first use, and remembers it in
    # `tempfile.tempdir`. Anything that touches tempfile before this hook runs
    # -- a plugin, an import, a future pytest -- pins it to /tmp, and setting
    # TMPDIR afterwards is a silent no-op. Verified here rather than assumed:
    # populate the cache first and `gettempdir()` still answers /tmp with
    # TMPDIR pointing at ~/temp.
    #
    # It happens to work today because nothing touches tempfile first. That is
    # an ordering accident, not a property, and the failure it guards against
    # is not loud -- 400 MB of disk images fill the volume and surface as ~25
    # unrelated-looking failures in test_akai_image.py, which is what this
    # file's own docstring describes.
    #
    # From VinSamLib, who found the same latent hole in their suite on the same
    # day, after both projects had already paid for a filled /tmp once.
    tempfile.tempdir = os.environ['TMPDIR']
