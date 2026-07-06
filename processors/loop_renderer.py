# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# Independent implementation; no third-party source code was copied.
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
Ping-pong (alternating) loop → forward loop renderer
-----------------------------------------------------
EMU EOS / E4B — and most forward-only sampler engines — have no ping-pong
(forward/backward, "alternating") loop mode.  The standard, widely recommended
workaround is to **bake the bounce into the PCM**: append a reversed copy of the
loop interior after the forward segment, then loop the combined region forward.
This is exactly what EOS itself does when importing EIII forward/backward loops
(EOS 4.0 manual: "the loop data will be permanently modified to contain the
forwards/backwards sound data").

A ping-pong loop over forward frames S[0..n-1] plays:

    S[0] S[1] ... S[n-1]      (forward)
    S[n-2] S[n-3] ... S[1]    (backward — the two endpoints are NOT repeated)
    [then forward again from S[0], and so on]

so one full period is  S[0..n-1] + S[n-2..1]  (length 2n-2 frames).  A plain
forward loop over that rendered region reproduces the bounce exactly, with no
duplicated endpoint samples (which would otherwise cause an audible stutter at
each turnaround).

Cost: the looped region grows by n-2 frames (≈ doubles the loop interior).  The
sample's non-loop head and tail are preserved unchanged.
"""

from dataclasses import replace

from models.common import SampleData, LoopType


def bake_alternating_loop(sample: SampleData) -> SampleData:
    """Render an ALTERNATING (ping-pong) loop into the PCM as a FORWARD loop.

    Returns a new ``SampleData`` with the reversed loop interior spliced in and
    ``loop_type`` set to ``FORWARD``.  Samples that do not have an alternating
    loop are returned unchanged (same object).

    ``loop_end`` is treated as the *inclusive* index of the last loop frame
    (the convention used throughout the codebase — see ``load_wav``).
    """
    if sample.loop_type != LoopType.ALTERNATING:
        return sample

    ls, le = sample.loop_start, sample.loop_end      # le inclusive
    n = le - ls + 1                                  # forward-segment length (frames)

    # Degenerate / too-short loop: a forward loop is already identical, so just
    # retag it (no PCM change, nothing meaningful to bounce).
    if le <= ls or n < 3:
        return replace(sample, loop_type=LoopType.FORWARD)

    bpf  = max(1, sample.channels * (sample.bit_depth // 8))   # bytes per frame
    data = sample.data

    # Reversed interior: frames le-1, le-2, ..., ls+1 (both endpoints excluded).
    mid = bytearray()
    for f in range(le - 1, ls, -1):
        mid += data[f * bpf:(f + 1) * bpf]

    cut      = (le + 1) * bpf                 # byte offset just past the forward segment
    new_data = data[:cut] + bytes(mid) + data[cut:]
    new_le   = le + (n - 2)                   # inclusive last frame of the 2n-2 region

    return replace(
        sample,
        data       = new_data,
        loop_start = ls,
        loop_end   = new_le,
        loop_type  = LoopType.FORWARD,
    )
