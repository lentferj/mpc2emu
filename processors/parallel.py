# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# This file is part of mpc2emu.
# Original implementation. No third-party source code used.
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
One worker pool for a whole run, not one per bank
-------------------------------------------------
Every DSP stage used to open its own ``ProcessPoolExecutor`` per source bank.
A directory of 60 four-sample programs therefore ran 60 pools, each with four
items -- four busy cores out of eleven, and a full barrier at every bank
boundary, sixty times.

MEASURED on 60 banks x 4 samples with ``--auto-loop``: 9.48 s pool-per-bank
against 1.99 s for one flat pool, **4.77x**.

⚠ The external review that raised this (DS41F, 2026-09-26) diagnosed it as
process *startup* cost.  That part is wrong and the measurement says so:
across those same 60 pools, construction totalled 39 ms and teardown 312 ms --
3.5% of a 9.9 s wall clock.  The cost is not starting the workers, it is that
four items cannot fill eleven of them and every bank waits for its own
slowest sample before the next bank starts.  Sizing the fix to the startup
number would have bought 3.5% and stopped there.

This is a change in *scheduling only*.  The work items are the same, the
results are scattered back to the same slots, and each bank's report is
printed in bank order afterwards, so stage output is unchanged.

⚠ This does NOT relax the project rule against running several ``convert.py``
or resample invocations at once (CLAUDE.md, "Parallelism").  It is one pool
inside one invocation -- strictly fewer processes than before, never more.

Contribution: https://github.com/jlentfer/mpc2emu
"""
import concurrent.futures
import os
from typing import Callable, List, Optional, Sequence


def default_workers() -> int:
    """cpu_count - 1, the project-wide worker count."""
    return max(1, (os.cpu_count() or 2) - 1)


def map_over_banks(banks: Sequence, make_args: Callable, worker: Callable,
                   serial: Callable, workers: Optional[int] = None,
                   items: Optional[Callable] = None) -> List[list]:
    """Run `worker` over every item of every bank through ONE pool.

    make_args(item)   -> the picklable argument tuple for `worker`
    worker(args)      -> the result, in a worker process
    serial(item)      -> the same result computed in-process (workers == 1)
    items(bank)       -> the bank's work items (default: ``bank.samples``)

    Returns one result list per bank, in bank order and in each bank's own
    sample order -- so a caller can keep applying and printing exactly as it
    did when it owned the pool itself.
    """
    if workers is None:
        workers = default_workers()
    get = items or (lambda b: b.samples)
    per_bank = [list(get(b)) for b in banks]
    counts = [len(x) for x in per_bank]
    flat = [it for one in per_bank for it in one]
    total = len(flat)

    if workers == 1 or total <= 1:
        results = [serial(it) for it in flat]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
            # chunksize=1: items are whole samples and their cost varies by
            # orders of magnitude (a 60 ms one-shot next to a 10 s pad), so
            # handing out fixed blocks would re-create the tail-wait this
            # function exists to remove.
            results = list(ex.map(worker, [make_args(it) for it in flat],
                                  chunksize=1))

    out, at = [], 0
    for c in counts:
        out.append(results[at:at + c])
        at += c
    assert at == total, "scatter lost items"
    return out
