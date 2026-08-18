# SPDX-License-Identifier: GPL-2.0-or-later
#
# Part of mpc2emu -- https://github.com/lentferj/mpc2emu
# Written with assistance from Claude (Anthropic).
"""Write a file completely or not at all.

Every image this project produces is destined for real media: a ZuluSCSI card,
a Gotek stick, a CF card in a sampler.  Written straight to the target path,
an interrupted build leaves a TRUNCATED file under the name the user asked
for, and nothing about it says so -- the disclaimer's advice to verify output
with `--info` does not help against a file the user believes finished, and a
128 MB `.hda` takes long enough that pressing Ctrl-C during one is ordinary.

Prompted by s3ked on 2026-08-14, from the other side of the same shape: their
client was killed mid-request, no `finally` ran, and the sampler was left
composing a reply to a request nobody was listening for -- wedged until a
power cycle.  Theirs was hardware left inconsistent by a process dying; ours
is a file left inconsistent by the same thing.  Neither is about what the code
does when it works.

`os.replace()` is atomic within a filesystem, so the temporary lives beside
the destination rather than in the system temp directory -- a rename across
filesystems is not atomic and would reintroduce exactly the partial file this
exists to prevent.
"""
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


@contextmanager
def atomic_write(path, mode: str = 'wb', encoding: Optional[str] = None):
    """Open a temporary file beside `path`, then move it into place on success.

    On any exception the temporary is removed and `path` is left exactly as it
    was -- absent if it did not exist, and UNTOUCHED if it did.  That second
    property matters as much as the first: rebuilding an image over a good one
    should not destroy the good one when the rebuild fails halfway.

    KeyboardInterrupt and SystemExit inherit from BaseException rather than
    Exception, and both are ordinary ways for a long build to end, so the
    cleanup catches BaseException deliberately.
    """
    # A TEXT mode with no encoding takes the locale codec -- cp1252 on a
    # Windows box -- so the same source produces different bytes on different
    # machines and a UTF-8 host can never see it. s3ked lost two days of CI to
    # exactly that, and their em dashes are ours too.
    #
    # Every caller here passes binary today, so this is about the signature
    # rather than a live bug: `atomic_write(p, 'w')` reads as obviously fine
    # and would not be. Text without an explicit encoding is UTF-8 by
    # construction now, and cannot become locale-dependent by accident.
    if 'b' not in mode and encoding is None:
        encoding = 'utf-8'
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                               prefix=f'.{path.name}.', suffix='.part')
    os.close(fd)
    # mkstemp creates 0600 -- correct for a temporary, wrong for the file it
    # becomes. Without this every image this project writes would land
    # user-readable-only, where `open(path, 'wb')` had always respected the
    # umask. Caught by looking at `ls -l` on the first real build after the
    # change: the conversion succeeded, the bytes were right, and the mode had
    # quietly changed. A correctness fix is still a behaviour change.
    _umask = os.umask(0)
    os.umask(_umask)
    os.chmod(tmp, 0o666 & ~_umask)
    try:
        with open(tmp, mode, encoding=encoding) as f:
            yield f
            f.flush()
            os.fsync(f.fileno())        # the rename is atomic; the DATA still
                                        # has to be on disk before it happens
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass                        # already gone, or never created
        raise
