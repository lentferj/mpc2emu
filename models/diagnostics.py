# SPDX-License-Identifier: GPL-2.0-or-later
#
# mpc2emu — Multi-format Sampler Converter
# https://github.com/jlentfer/mpc2emu
#
# Structured diagnostics: a machine-readable channel for the things a
# conversion needs to tell its caller.
"""Structured warnings and errors from the conversion pipeline.

**Why this exists.** Every writer already reports what it had to compromise —
layers thinned, zones dropped above the up-pitch ceiling, samples renamed,
banks split. It reported them by `print()`, which works for a person watching a
terminal and fails for everything else:

* mpc2emu's own test harness wrapped conversions in `quiet()` and swallowed the
  up-pitch warning wholesale;
* VinSamLib calls our writers through a bridge and captures our stdout with
  `redirect_stdout` into a buffer that only surfaces on an exception — so a
  warning printed by a *successful* conversion is discarded;
* and on 2026-09-05 a `[layers] ... DRUM PROGRAM (play on a drum channel)`
  notice, printed correctly and completely, cost three sessions most of a day
  of hardware investigation because nobody read the log it went to.

A caller that wants to act on a compromise — display it in a GUI, refuse the
conversion, pick a different flag — cannot parse prose out of stdout. It needs
records.

**Design constraints.** Stdlib only (this project takes no dependencies).
Printing must keep working exactly as before, so the CLI is unaffected and no
existing behaviour changes. Collection must be opt-in, so a caller that does
not care pays nothing.

**Usage from a library caller:**

    from models.diagnostics import collect

    with collect() as diags:
        write_krz(bank, path)

    for d in diags:
        if d.code == 'KRZ_LAYERS_THINNED':
            gui.warn(d.message, detail=d.detail)

`diags` is a plain list of `Diagnostic`; `Diagnostic.as_dict()` is JSON-safe.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterator, List, Optional

__all__ = ['Diagnostic', 'emit', 'collect', 'INFO', 'WARNING', 'ERROR']

INFO = 'info'
WARNING = 'warning'
ERROR = 'error'


@dataclass
class Diagnostic:
    """One thing the conversion needs to tell its caller.

    `code` is the stable identifier a program branches on — it must not change
    once published, because that is the whole contract. `message` is for a
    human and may be reworded freely. `detail` carries the numbers, so a caller
    never has to parse them back out of the sentence.
    """
    severity: str
    code: str
    message: str
    content_lost: bool           # DELIBERATELY has no default -- see below
    subject: str = ''            # preset / sample / bank the record is about
    detail: Dict[str, Any] = field(default_factory=dict)
    remedy: str = ''             # what the user can DO; NEVER names a CLI flag
    #
    # WHY content_lost IS A REQUIRED FIELD AND NOT A detail KEY.
    #
    # It started as detail['content_lost'] with a test asserting every NEW code
    # carried it. VinSamLib read that as a consumer and found the hole: they
    # filter with `d.detail.get('content_lost')`, which returns None for the
    # five codes written before the convention, and None is falsy. So
    # KRZ_DRUM_PROGRAM -- the silent instrument, the worst thing either project
    # can ship, and the episode this whole interface exists because of --
    # filtered as "nothing lost". So did KRZ_ZONES_DROPPED, whose name IS the
    # loss.
    #
    # The test passed the whole time, because it was scoped to new codes. So did
    # review, because no single emit site looked wrong.
    #
    # Their fix, taken as offered and better than backfilling: a required
    # constructor argument. Omitting it is now a TypeError at the EMIT site
    # rather than a None at the consumer's, every existing code had to be
    # answered to keep the module importable, and the property holds for every
    # future code with no test to maintain. A detail key can always be
    # forgotten; a required argument cannot.

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        who = f" '{self.subject}'" if self.subject else ''
        return f"[{self.severity}:{self.code}]{who} {self.message}"


_local = threading.local()


def _sinks() -> List[List[Diagnostic]]:
    if not hasattr(_local, 'sinks'):
        _local.sinks = []
    return _local.sinks


def emit(severity: str, code: str, message: str, *, content_lost: bool,
         subject: str = '', detail: Optional[Dict[str, Any]] = None,
         remedy: str = '', echo: Optional[str] = None) -> Diagnostic:
    """Record a diagnostic and, unless `echo` is '', print it.

    `content_lost` is REQUIRED and keyword-only: say whether musical content
    was actually lost, every time. It is the consumer's primary filter and the
    distinction is frequently invisible in the message text -- "velocity layers
    carried into additional keygroups" loses nothing, while "key ranges beyond
    the limit dropped" loses audio, and the two read almost identically.

    `echo` is the exact line to print, so existing output is preserved
    byte-for-byte while the record is added alongside. Pass `echo=''` to record
    silently; pass None to print a rendering of the diagnostic itself.
    """
    d = Diagnostic(severity=severity, code=code, message=message,
                   content_lost=bool(content_lost), subject=subject,
                   detail=dict(detail or {}), remedy=remedy)
    for sink in _sinks():
        sink.append(d)
    if echo != '':
        print(echo if echo is not None else str(d))
    return d


@contextlib.contextmanager
def collect() -> Iterator[List[Diagnostic]]:
    """Collect diagnostics emitted inside the block.

    Nests: an inner `collect()` does not hide records from an outer one, so a
    caller that wraps a whole conversion still sees what a nested step emitted.
    Thread-local, so concurrent conversions do not cross-contaminate.
    """
    sink: List[Diagnostic] = []
    _sinks().append(sink)
    try:
        yield sink
    finally:
        # REMOVE BY IDENTITY. `list.remove` compares with `==`, and two sinks
        # holding equal contents -- most commonly two EMPTY lists -- compare
        # equal, so an inner `collect()` removed the OUTER sink instead of its
        # own. After that every emit in the outer block routed into an exited
        # list nobody reads, and the diagnostics vanished silently; if the two
        # had diverged by then it raised ValueError instead.
        #
        # Nesting is a documented property of this contextmanager, so this is
        # the ordinary case, not an exotic one.
        _s = _sinks()
        for _i in range(len(_s) - 1, -1, -1):
            if _s[_i] is sink:
                del _s[_i]
                break
