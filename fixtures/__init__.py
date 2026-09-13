# SPDX-License-Identifier: GPL-2.0-or-later
#
# mpc2emu — https://github.com/lentferj/mpc2emu
"""Minimal synthetic inputs that fail in specific, known ways.

**These exist because a fixture that needs a 57 000-WAV NFS share is not a
fixture.** 32 of VinSamLib's 86 tests depended on Jan's real library, which
travels with nothing and cannot be committed. Each generator here produces the
smallest thing that fails the same way as the real material it stands for.

**EVERY FIXTURE MUST FAIL AGAINST THE CODE THAT HAD THE BUG** (k2kremote's
rule, 2026-09-13: a fixture that cannot fail is not a test). Each generator's
docstring names the fault it reproduces and what the real specimen was, so the
two can be compared when one of them changes.

They are GENERATORS, not files: the fixture is a few lines of Python that
builds the bytes deterministically, so it is diffable, reviewable and adds no
binaries to the repo. Call one, write the bytes where your test wants them.
"""
