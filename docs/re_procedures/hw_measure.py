#!/usr/bin/env python3
#
# PROMOTED TO docs/ 2026-09-07. `tests/` is gitignored by project policy, so the
# working copy at tests/re_banks/hw_measure.py is NOT under version control. This
# copy exists so the bench rig -- the instrument behind every hardware number in
# docs/ and TODO.md -- survives a scratch clean-up and travels with the findings
# it produced. Run the copy in tests/re_banks/; treat this one as the record.
#
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2026  mpc2emu contributors
#
# This file is part of mpc2emu.
#
# Drive the E4XT over MIDI, record its audio, and measure the result --
# the automated version of every hand-timed calibration in this project
# (ENV_RATE, MOD_DEPTH_CAL, AMP_LEVEL were all fitted from 4-6 stopwatch
# points; this can sweep 128 unattended).
#
# Rig, as wired on Jan's bench 2026-07-31:
#   MIDI out : "ESI M4U eX MIDI 4"  (the eosed config.toml send_port)
#   channel  : 5, 1-indexed  (E4XT MIDIGLO_BASIC_CHANNEL = 4, 0-indexed)
#   audio in : JACK system:capture_15 / _16  (the E4XT feed), via an
#              in-process JACK client (_PersistentRecorder)
#              system:capture_5  / _6   (MPC One)
#              system:capture_13 / _14  (S3000XL)
#
# RECORD FROM THE HARDWARE CAPTURE PORTS, NEVER FROM A DOWNSTREAM CLIENT.
# On this rig the same two capture ports also feed AF210M (an EQ), whose
# output feeds Sonarworks room correction on the way to the speakers:
#
#   E4XT -> Scarlett in -> system:capture_15/16 -+-> our JACK client (RAW)
#                                                `-> AF210M -> Sonarworks -> monitors
#
# Our client taps the same node as AF210M, in parallel and upstream of it, so
# what we measure is the E4XT. Recording AF210M's or Sonarworks' OUTPUT
# instead would silently convolve every measurement with a room-correction
# curve -- it would tilt spectra, move every -3 dB filter corner and change
# resonance peak heights, and a verification pass would simply reproduce the
# same error twice and look like a confirmation.
#
# NOTE the predecessor's hard-won lessons (run_amp_level_cal_sweep.py, which
# depended on `eosremote` -- since gone, replaced by ~/git-repos/eosed):
#   - a preset must be selected with a real Program Change, or notes play
#     whatever was already active;
#   - the E4XT crashed once under unthrottled MIDI sent back-to-back with
#     heavy SysEx. This module only sends notes and program changes, spaced
#     by whole seconds, so it stays well clear of that.
#
# Usage as a library:
#     from hw_measure import play_sequence, envelope
#     wav = play_sequence([(48, 8.0, 1.5), (49, 8.0, 1.5)], program=3)
#     env, t = envelope(wav)
#
# Usage as a script (records a single note and prints its envelope shape):
#     python3 tests/re_banks/hw_measure.py --note 48 --program 3 --hold 8

import argparse
import json
import math
import signal
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

LEAD_IN = 1.5                    # recorder head start before the first note


# --- devices ---------------------------------------------------------------
#
# One rig, several instruments. Each entry is how THAT box is wired on Jan's
# bench; the pre-EQ warning at the top of this file applies to every one of
# them, since they all share the same Scarlett -> AF210M -> Sonarworks chain.
#
class Device:
    def __init__(self, name, midi_port, channel, capture):
        self.name = name
        self.midi_port = midi_port
        self.channel = channel        # 0-indexed
        self.capture = capture

    def __repr__(self):
        return f"<Device {self.name} ch{self.channel + 1} {self.capture}>"


DEVICES = {
    'e4xt': Device('E4XT', 'ESI M4U eX MIDI 4', 4,
                   ['system:capture_15', 'system:capture_16']),
    # MPC One, firmware 3.9.x. Wiring confirmed by Jan 2026-08-03: MIDI on the
    # Scarlett's own port, channel 1, audio on capture 5/6.
    'mpc':  Device('MPC One', 'Scarlett 18i8 USB MIDI 1', 0,
                   ['system:capture_5', 'system:capture_6']),
    # AKAI S3000XL. Audio on PCM Inputs (system) 13/14 (Jan, 2026-08-10);
    # MIDI port confirmed by the s3ked project, which drives this box over
    # SysEx on exclusive channel 0. rtmidi reports the port verbatim as
    # 'ESI M4U XT:ESI M4U XT MIDI 1 64:0'; the substring below is enough.
    #
    # !! send_cc() DOES NOTHING ON THIS MACHINE. !!
    # The S3000XL has no CC-to-parameter map at all -- cutoff, resonance,
    # attack, decay and release are not reachable over CC, and CC 74/71/73/
    # 75/72 are silently inert. The only external route into the modulation
    # matrix is source 4 "External", one generic controller rather than a
    # per-CC assignment, and choosing WHICH controller it means lives in the
    # miscellaneous data block, which is not indexed in any document either
    # project holds. So calibration here must go over SysEx.
    #
    # Use s3ked's probes/calibrate.py, whose rig model is ported from this
    # file; the primitive under it is
    #   s3k.bridge.S3kBridge.set_parameter(param, index, value,
    #                                      keygroup=..., confirm=True)
    # which waits for REPLY and raises on error.
    #
    # Two traps recorded by s3ked, both cheap to hit and expensive to notice:
    #   * a program left on an individual OUTPUT measures as SILENCE on the
    #     main stereo pair;
    #   * a SINE cannot measure a filter corner -- one frequency gives a step,
    #     not a curve. Sweep against SAWTOOTH (resident, all harmonics).
    # NB 'M4U XT' alone matches FOUR ports here (MIDI 1-4 of the same
    # interface); _midi_out takes hits[0], so it only works while the
    # enumeration order happens to put MIDI 1 first. Matched on the full
    # 'M4U XT MIDI 1' instead.
    'akai': Device('S3000XL', 'M4U XT MIDI 1', 0,
                   ['system:capture_13', 'system:capture_14']),
    # K2000R. Parameters as k2kremote reports them (2026-09-02): the ESI M4U
    # eX's eighth port, MIDI channel 9 (index 8), audio on capture 17/18.
    #
    # PROGRAM SELECT IS BANK-OF-100, NOT BANK-OF-128 (Jan, 2026-09-02):
    #     CC0 = id // 100     program change = id % 100     banks go to 99
    # so program 402 is bank 4, PC 2. The MIDI-standard id//128 / id%128 is
    # WRONG here and FAILS QUIETLY: CC0=3 + PC=18 selects **318**, a perfectly
    # real program on another bank, so the rig sounds fine and measures the
    # wrong thing. Only Jan reading the front panel caught it.
    'k2000': Device('K2000R', 'ESI M4U eX MIDI 8', 8,
                    ['system:capture_17', 'system:capture_18']),
}

DEFAULT_DEVICE = 'e4xt'
_ACTIVE = DEVICES[DEFAULT_DEVICE]

# Back-compat: the module used to expose these as plain globals and other
# scripts import them. They track the active device.
MIDI_PORT_MATCH = _ACTIVE.midi_port
MIDI_CHANNEL = _ACTIVE.channel
CAPTURE = _ACTIVE.capture


def use_device(key, channel=None):
    """Select which instrument the rig drives. Returns the Device.

    `channel` overrides the device's default MIDI channel, 0-indexed. Added
    2026-09-04: an MPC One can hold several programs at once on separate
    channels -- Jan loaded three on 14/15/16 (1-indexed) -- and without this
    the rig could only ever address the one channel in the DEVICES table, so a
    multi-program source had to be re-loaded between captures. The device's own
    value stays the default, so nothing that does not pass it changes.
    """
    global _ACTIVE, MIDI_PORT_MATCH, MIDI_CHANNEL, CAPTURE
    if key not in DEVICES:
        sys.exit(f"unknown device {key!r} -- known: {', '.join(sorted(DEVICES))}")
    _ACTIVE = DEVICES[key]
    MIDI_PORT_MATCH = _ACTIVE.midi_port
    MIDI_CHANNEL = _ACTIVE.channel if channel is None else int(channel)
    CAPTURE = _ACTIVE.capture
    return _ACTIVE


#: One open MidiOut per port match, for the life of the process.
#:
#: **ALSA sequencer clients are a finite, MACHINE-WIDE resource and rtmidi does
#: not free them on close.** This project has that on record from 2026-07-12:
#: `close_port()` leaves the backend client alive and `delete()` has to be
#: called explicitly. `_midi_out()` had no caching and no delete, so it leaked
#: a client per call -- and on 2026-09-04 a matrix capture run accumulated 22
#: of them and exhausted the sequencer, at which point a SIBLING session's
#: K2000 autodetect failed with
#:
#:     ALSA lib seq_hw.c: open /dev/snd/seq failed: Cannot allocate memory
#:     RuntimeError: auto-probe: no K2000 answered on any of 38 output ports
#:
#: **That is indistinguishable from the instrument being switched off**, and
#: taking it at face value would have cancelled a night's measurement on a
#: resource leak. "No device answered" is a claim about our ability to ask,
#: not about the device. Caching bounds the clients at one per port; the
#: atexit hook returns them even on an abnormal exit.
_MIDI_CACHE = {}


def _midi_out():
    import rtmidi
    if not MIDI_PORT_MATCH:
        sys.exit(f"no MIDI port configured for {_ACTIVE.name} -- fill in "
                 f"DEVICES[...] .midi_port or pass --midi-port")
    cached = _MIDI_CACHE.get(MIDI_PORT_MATCH)
    if cached is not None:
        return cached
    m = rtmidi.MidiOut()
    hits = [i for i, p in enumerate(m.get_ports()) if MIDI_PORT_MATCH in p]
    if not hits:
        m.delete()          # do not leak the probe itself on the error path
        sys.exit(f"MIDI port matching {MIDI_PORT_MATCH!r} not found -- is the "
                 f"interface on? (see eosed config.toml for the current wiring)")
    m.open_port(hits[0])
    _MIDI_CACHE[MIDI_PORT_MATCH] = m
    return m


def _release_midi():
    """Give every ALSA sequencer client back. `close_port()` alone does NOT."""
    for m in list(_MIDI_CACHE.values()):
        try:
            m.close_port()
            m.delete()
        except Exception:
            pass
    _MIDI_CACHE.clear()


import atexit as _atexit
_atexit.register(_release_midi)


# Standard MIDI sound controllers. Whether a given box honours them without
# an explicit mapping is a per-instrument question -- the MPC's answer is the
# open one (checklist A3/A4).
CC = dict(cutoff=74, resonance=71, attack=73, decay=75, release=72)


def send_cc(controls, settle=0.15):
    """Send `{cc_number_or_name: value}` on the active device's channel.

    Values are 0-127, which for the MPC is the SAME integer the program JSON
    stores as `n/127` (see the checklist "normalised controls are n/127").
    Spaced by `settle` -- the E4XT crashed once under unthrottled MIDI and
    there is no reason to discover whether anything else does.
    """
    m = _midi_out()
    try:
        for key, value in controls.items():
            num = CC.get(key, key) if isinstance(key, str) else key
            m.send_message([0xB0 | MIDI_CHANNEL, int(num) & 0x7F,
                            max(0, min(127, int(value)))])
            time.sleep(settle)
    finally:
        del m


def verify_isolation(change_source, play, tolerance_db=1.0):
    """Prove the recording responds to the thing under test BEFORE believing it.

    **Validate the instrument AND what it is pointed at.** This project spent
    an evening validating the former with real care -- 0.39% repeatability
    over five takes, a flatness guard on the reference band, restores verified
    by read-back, a blind-spot ceiling computed for the harmonic test -- and
    then reasoned for hours about numbers that were of the wrong program.

    s3ked, 2026-08-10: all eleven programs resident on an S3000XL sat on MIDI
    channel 1, so every note sounded the program under test buried beneath ten
    commercial library programs. SINE, SAWTOOTH and SQUARE produced IDENTICAL
    spectra -- a sine cannot look like a sawtooth, and that alone should have
    ended it hours earlier. Excluding the played note from the program's own
    keyrange changed nothing either. Every audio number from that session was
    of the sum.

    **Our own E4XT and MPC calibrations never ran this check.** Nothing says
    they were wrong; nothing said they were right either, and the same failure
    is available on any rig where more than one voice can answer a note.

    `change_source()` must make a change that MUST alter the sound (swap the
    zone's sample, mute the preset, move its key range off the played note).
    `play()` returns a recording. If the two are indistinguishable, the thing
    under test is not what is being recorded, and no measurement taken
    afterwards means anything.

    Returns (ok, delta_db). Deliberately returns rather than raising, so a
    caller can log the margin -- but treat False as fatal.
    """
    import wave, audioop

    def _rms_db(path):
        with wave.open(path) as w:
            data = w.readframes(w.getnframes())
            width = w.getsampwidth()
        rms = audioop.rms(data, width)
        return 20 * math.log10(rms / 32768.0) if rms else -120.0

    before = _rms_db(play())
    change_source()
    after = _rms_db(play())
    delta = abs(after - before)
    ok = delta >= tolerance_db
    if not ok:
        print(f"  [FATAL] isolation check FAILED: {delta:.2f} dB change when "
              f"the source was swapped (need >= {tolerance_db} dB).")
        print(f"          Something else is sounding on this channel. Any "
              f"measurement taken now is of the sum, not the target.")
        print(f"          Give the target its own MIDI channel and re-check.")
    return ok, delta


class SignalsAsExceptions:
    """Make SIGTERM/SIGHUP/SIGINT raise, so `finally` blocks actually run.

    **CPython does not unwind on SIGTERM.** The default disposition terminates
    the process outright: no `finally`, no `__exit__`, no atexit. So any
    cleanup written as

        try:
            sweep()
        finally:
            restore()          # <- never runs under SIGTERM

    is silently skipped the moment the run is wrapped in `timeout`, launched
    from cron, or stopped by a supervisor -- i.e. exactly the unattended cases
    a long sweep is written for.

    This is not hypothetical. s3ked lost a real restore this way on
    2026-08-10: their sweep ran under `timeout 900`, exceeded it, and left ten
    parameters wrong on the machine -- OUTPUT, three envelope segments and a
    mid-sweep cutoff -- because the `finally` that would have put them back
    never executed. They recovered only because the original values happened
    to exist in a header dump sent to this project as ground truth.

    Usage:

        with SignalsAsExceptions():
            try:
                sweep()
            finally:
                reset_controllers()

    Re-raises as KeyboardInterrupt so callers that already handle Ctrl-C get
    the same path, and restores the previous handlers on exit.
    """

    SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)

    def __init__(self):
        self._prev = {}
        self._fired = False

    def _raise(self, signum, _frame):
        # ONE-SHOT. The first signal converts to KeyboardInterrupt so `finally`
        # blocks unwind and the hardware is put back; every signal after that
        # is IGNORED until the unwind finishes.
        #
        # Without this, the handler stays armed during its own cleanup and a
        # second signal aborts the restore half-done -- which is not
        # hypothetical. s3ked, 2026-08-12: a doubled SIGTERM interrupted a
        # restore and FOURTEEN FIELDS could not be put back on the machine.
        # Process managers, impatient double Ctrl-C, and `pkill` matching twice
        # all produce that.
        #
        # Cost, stated plainly: once the unwind is running, TERM and INT no
        # longer stop it. A genuinely hung restore needs SIGKILL. That is the
        # right trade here -- the failure this prevents leaves real hardware in
        # a wrong state that nobody knows to fix, while the failure it enables
        # is one extra keystroke.
        if self._fired:
            return
        self._fired = True
        for sig in self._prev:
            try:
                signal.signal(sig, signal.SIG_IGN)
            except (ValueError, OSError):
                pass
        raise KeyboardInterrupt(f"signal {signum} (further signals ignored "
                                "until cleanup completes; SIGKILL to force)")

    def __enter__(self):
        for sig in self.SIGNALS:
            try:
                self._prev[sig] = signal.signal(sig, self._raise)
            except (ValueError, OSError):
                pass          # not main thread, or platform will not allow it
        return self

    def __exit__(self, *exc):
        for sig, prev in self._prev.items():
            try:
                signal.signal(sig, prev)
            except (ValueError, OSError):
                pass
        return False


#: MIDI "Reset All Controllers".
_CC_RESET_ALL = 121


def reset_controllers(settle=0.15):
    """Return the active device's controllers to their default values.

    **This is weaker than a snapshot/restore and the difference matters.**
    s3ked's SysEx layer can READ a parameter before writing it, so it can put
    back exactly what was there. MIDI CC is write-only -- there is no way to
    ask "what is cutoff now?" over a control change -- so the best available
    undo is the standard Reset All Controllers, which returns them to the
    *device's* defaults rather than to whatever the preset had.

    **And read-back is not merely better than an ack, it is the only thing
    that works** (s3ked, 2026-08-12). Their machine ACCEPTED a partition
    write, REPLIED OK, and ignored it -- a hold flag left set by an earlier
    panel action suppressed the re-read, so the directory went on describing
    the previous partition while every write was acknowledged. Their words: *a
    write that is acknowledged and ignored is worse than one that is refused,
    because the reply says it worked.*

    We are not exposed to that specific trap, and only because MIDI CC carries
    no acknowledgement to trust. Our equivalent state is weaker in a different
    way: every CC we send is simply ASSUMED to have landed, always. The
    defence is the same one either way and it is not the transport -- it is
    `verify_isolation()`, which proves the recording responds to the thing
    under test before any of it is believed. Observe the effect, never the
    request and never the reply.

    What this does NOT cover:

      * a device that latches CC into the stored preset (the E4XT does not
        until you save; do not save after a sweep);
      * a program change, which `play_sequence(program=...)` sends and which
        this does not put back -- the caller knows which program it wants;
      * anything set by another route entirely.

    **Wrap the sweep in `SignalsAsExceptions` if you call this from a
    `finally`**, or a SIGTERM will skip it -- see that class.

    Historically this rig has relied on being pointed at a **scratch preset
    built for the measurement**, so nothing it disturbed was worth keeping.
    That property lives in the material rather than in the code, and it does
    not survive somebody aiming this at a real preset -- which is exactly the
    hazard s3ked found in their own sweep harness (2026-08-10, fourth pass)
    and worth stating here rather than assuming.
    """
    m = _midi_out()
    try:
        m.send_message([0xB0 | MIDI_CHANNEL, _CC_RESET_ALL, 0])
        time.sleep(settle)
    finally:
        del m


def _stack_blocks(np, blocks, nports):
    """Turn JACK's per-period blocks into one (frames, channels) array.

    Takes a SNAPSHOT of the block list, because the naive version races its own
    process callback: it concatenates channel 0 across the blocks it can see,
    then channel 1 across the blocks it can see *by then*, and a callback
    landing between the two leaves the channels a period apart. s3ked lost four
    takes to exactly that (their §, 2026-08-16).

    Both rules here are about cutting every channel at the same place: work
    from one snapshot, and DROP a trailing block that does not carry every
    channel rather than padding it.
    """
    usable = [blk for blk in blocks if len(blk) == nports]
    if not usable:
        return np.zeros((0, nports), dtype='float32')
    chans = [np.concatenate([blk[i] for blk in usable]) for i in range(nports)]
    shortest = min(len(c) for c in chans)
    return np.stack([c[:shortest] for c in chans], axis=1)


class _PersistentRecorder:
    """One JACK client for the whole session, instead of one per capture.

    `jack_rec` is spawned and torn down per recording, and on this bench it
    stops exiting every 8-10 captures and takes the JACK SERVER with it -- after
    which no client can register and recovery needs the audio graph restarted.
    Registering once and keeping the client alive removes the create/destroy
    cycle, which is the thing that wedges.

    Ported from s3ked's `probes/calibrate.py::_InProcessRecorder`, which is
    itself built on the rig model in this file -- the improvement coming back
    the other way. They measured 19 consecutive captures with zero wedges.

    Written after wedging the server THREE times in one unattended session,
    with the warning to do this sitting in the comment directly below the
    `jack_rec` call I kept using.
    """

    def __init__(self, capture, name='mpc2emu-hw'):
        import jack, numpy as np
        self._np = np
        self.client = jack.Client(name, no_start_server=True)
        self.ports = [self.client.inports.register(f'in{i}')
                      for i in range(len(capture))]
        self._frames, self._armed = [], False

        @self.client.set_process_callback
        def _process(nframes):          # noqa: ARG001 -- jack calls with frames
            if self._armed:
                self._frames.append([p.get_array().copy() for p in self.ports])

        self.client.activate()
        self._sources = []
        self.reconnect(capture)
        self.samplerate = self.client.samplerate

    def reconnect(self, capture):
        """Point the recorder at `capture`, disconnecting whatever it had.

        **THE RECORDER IS PERSISTENT AND `use_device()` IS NOT.** Until
        2026-09-02 this client connected its ports once, at construction, and
        was then cached for the whole session -- so a script that switched
        instruments mid-run kept capturing the FIRST one's inputs while every
        other signal (MIDI port, channel, program change) followed the switch
        correctly. A cross-machine A/B would silently compare an instrument
        with itself, or with silence.

        Found the hard way: a K2000-then-MPC comparison returned five silent
        captures. The K2000 half was genuinely silent for its own reason; the
        MPC half was silent because it was still listening to the K2000's
        inputs. One bug hid behind another.
        """
        capture = list(capture)
        if capture == self._sources:
            return
        for dst in self.ports:
            for src in self.client.get_all_connections(dst):
                try:
                    self.client.disconnect(src, dst)
                except Exception:
                    pass
        for src, dst in zip(capture, self.ports):
            self.client.connect(src, dst)
        # ASSERT THE PATH EXISTS -- do not infer it from connect() not raising.
        #
        # k2kremote (2026-09-02) found the sibling of this in their own rig:
        # 29 capture scripts wrapping connect in `try/except: pass`, so a
        # failed connection is swallowed and the capture comes back SILENT --
        # then analyses cleanly, produces numbers and passes every gate,
        # because their gates check the SIGNAL and none check that a signal
        # path exists. It had not bitten them, but only because a fully silent
        # run also trips the SNR check, which they had been reading as "the
        # filter is closed" rather than "the audio path may be absent". Two
        # causes, one appearance.
        #
        # We never swallowed the exception, but we did trust its absence,
        # which is the same assumption one step weaker. Now the connection is
        # read back.
        for src, dst in zip(capture, self.ports):
            live = [str(c) for c in self.client.get_all_connections(dst)]
            if not any(src in c for c in live):
                raise RuntimeError(
                    f"capture port {dst.name} is NOT connected to {src!r} "
                    f"(connections: {live or 'none'}). Every downstream gate "
                    f"checks the signal; none of them can tell you the path "
                    f"was never there.")
        self._sources = capture

    def arm(self):
        self._frames, self._armed = [], True

    def stop_and_write(self, path):
        self._armed = False
        # A callback that already passed its `_armed` check will still append,
        # so give one in flight time to land rather than truncating it.
        time.sleep(0.05)
        data = _stack_blocks(self._np, self._frames[:], len(self.ports))
        np = self._np
        frames = (np.clip(data, -1, 1) * 32767).astype('<i2')
        with wave.open(str(path), 'wb') as w:
            w.setnchannels(data.shape[1] if data.ndim > 1 else 1)
            w.setsampwidth(2)
            w.setframerate(int(self.samplerate))
            w.writeframes(frames.tobytes())

    def close(self):
        for fn in (self.client.deactivate, self.client.close):
            try:
                fn()
            except Exception:
                pass


_REC = None


def _recorder():
    """The session's recorder, or None if the JACK binding is missing.

    A None return is fatal at the call site -- see the comment there. It is
    kept as a return rather than raising here so the caller can phrase the
    refusal in terms of what the run was about to do.
    """
    global _REC
    if _REC is None:
        try:
            _REC = _PersistentRecorder(list(CAPTURE))
        except Exception as e:
            print(f"  [FATAL] persistent JACK client unavailable ({e})")
            return None
    else:
        # Follow the active device. Cheap, idempotent, and the only thing
        # standing between a device switch and a silently wrong capture.
        _REC.reconnect(list(CAPTURE))
    return _REC


# ---------------------------------------------------------------------------
# BEFORE YOU BELIEVE A NULL, ASK TWO QUESTIONS (2026-08-16/17)
#
# Three nulls in one evening came from detectors that could not have shown the
# effect. None was a subtle statistical problem; each was structural and each was
# checkable before a note was played.
#
#   1. IS THE THING I AM CHANGING CONNECTED TO THE THING I AM MEASURING?
#      - probed note 84 on a program whose KEYGROUPS stop at 72: silence on every
#        setting, a beautifully flat null. The PLAY range said 24-127 and looked
#        fine; the keygroup span was what mattered.
#      - wrote K_FREQ into KEYGROUP 1 while playing a note covered by KEYGROUP 19.
#        The tell was that FILFRQ 40 and FILFRQ 17 gave IDENTICAL readings to a
#        tenth of a dB -- a filter parameter that does nothing when halved is not
#        in the signal path.
#
#   2. COULD THE EFFECT HAVE APPEARED AT THIS OPERATING POINT?
#      - a depth measured at ONE velocity cannot distinguish a live field from a
#        dead one; vary the source.
#      - opening a corner that already sits above the material changes nothing
#        however far it opens; closing one into the signal is loud.
#      - two settings that both clamp at a ceiling read as equal. Probing note 84
#        would have pushed both K_FREQ values past FILFRQ 99 for that reason too.
#
#   3. COULD TWO FAULTS BE SHARING ONE SYMPTOM?
#      eosed's silent note scan failed because RAM was empty AND the MIDI channel
#      was wrong. One symptom -- silence -- from two independent causes. Fixing
#      either alone reproduces the SAME null, which then reads as confirmation
#      that the other fix was unnecessary. In their words: independent faults
#      with a shared symptom do not merely hide each other, they actively reward
#      partial fixes with confirming evidence. When a null survives a fix, ask
#      whether it is the same null.
#
# DRIVING A PANEL REMOTELY: ONCE THE DISPLAY STOPS ANSWERING, STOP PRESSING.
# The read path and the write path are the SAME channel. Losing replies does not
# just cost the screen, it costs the ability to verify anything done next -- so
# a driver that keeps sending keypresses is pressing blind into menus that carry
# unconfirmed destructive operations. k2kremote has a precedent from a GOOD case:
# a known page, a human watching, and a soft key still began an irreversible
# floppy load that cost a power cycle.
#
# THE CENTROID IS NOT A SAFE CHANNEL. It is confounded at BOTH ends:
#   closing  -- signal falls toward the floor and the centroid reports NOISE as
#               brightness (K_FREQ 22 read 1732 Hz against K_FREQ 12's 270 Hz
#               while the level fell another 20 dB);
#   opening  -- admitted low-frequency signal swamps that noise and the centroid
#               FALLS while the level rises 14.6 dB.
# Read the level. Use a spectral measure only with a signal-presence gate, and
# never quote a centroid taken near the noise floor.
# ---------------------------------------------------------------------------


def play_sequence(notes, program=None, out_wav=None, velocity=127,
                  controls=None, off_velocity=0):
    """notes: list of (midi_note, hold_s, gap_s) or (midi_note, hold_s, gap_s,
    velocity).  Records the whole run and
    returns (wav_path, schedule) where schedule carries each note's on/off
    time in the MIDI clock -- segment on THAT, not on silence detection: a
    slow attack starts too quietly for a silence gate to find its true onset.

    `controls` is an optional {cc: value} dict sent after the program change
    and before the first note, so a parameter sweep needs no hardware fiddling
    between takes.

    PER-NOTE VELOCITY (4-tuple) EXISTS TO KEEP CAPTURE COUNT DOWN, which is a
    safety property here rather than a convenience. This function registers a
    JACK client per capture, and the comment below records that the CREATE/
    DESTROY cycle is what wedges the server -- s3ked hit a ceiling near eight.
    A velocity sweep driven by the `velocity` argument needs one capture per
    velocity; the same sweep as 4-tuples is ONE capture. Nine velocities across
    nine keygroups is 81 notes in a single recording instead of nine
    recordings, which also removes any between-capture gain drift from the
    comparison -- every point shares one gain staging.

    The schedule records each note's velocity, so an analysis written later
    does not have to re-derive which note was which.
    """
    # Indexed, not unpacked: a note may be (note, hold, gap) or
    # (note, hold, gap, velocity), and a 3-tuple unpack here silently
    # rejects the 4-tuple form the docstring promises.
    total = LEAD_IN + sum(n[1] + n[2] for n in notes) + 2.0
    out_wav = out_wav or tempfile.mktemp(suffix='.wav')
    # !! THIS SPAWNS A JACK CLIENT PER CAPTURE, AND THAT IS WHAT WEDGES THE
    # SERVER. !! s3ked established it on 2026-08-11: it is not the recording
    # that wedges jackd, it is the client CREATE/DESTROY cycle. Their sweep hit
    # a ceiling of about eight captures before the server stopped accepting new
    # clients -- twice in one evening, once taking down Jan's whole graph
    # (Carla, the mididings bridges, monitoring, the MPC send bus).
    #
    # They replaced it with an in-process JACK client registered ONCE for the
    # session (the JACK-Client binding, which is installed here -- 0.5.5) and
    # got 19 consecutive captures across two runs with zero wedges.
    #
    # This rig has the same exposure and the same fix is available. It has not
    # bitten here yet only because our sessions have been short: an E4XT
    # calibration is a handful of captures, not fifty. Anything unattended, or
    # any sweep past ~8 points, should move to a persistent client first.
    # NO SILENT FALLBACK TO `jack_rec`. Jan's call 2026-08-17, from the S3000XL
    # sessions: use the JACK client, full stop.
    #
    # This used to drop back to spawning `jack_rec` per capture when the binding
    # was missing, with a warning. That is the worst available behaviour. The
    # fallback path is not merely slower -- past roughly eight captures it stops
    # exiting and TAKES THE JACK SERVER WITH IT, after which no client can
    # register and recovery needs the whole audio graph restarted. In an
    # unattended sweep that means the run dies partway and leaves a truncated
    # set of captures that still look like a measurement.
    #
    # A warning does not help when nobody is at the desk, which is exactly the
    # case this rig exists for. Refusing to start is the only behaviour that
    # cannot produce a half-complete result someone later fits a curve to.
    rec = _recorder()
    if rec is None:
        raise SystemExit(
            "  No persistent JACK client available, and the jack_rec fallback\n"
            "  has been removed deliberately: it wedges the JACK SERVER past\n"
            "  ~8 captures and takes the audio graph with it.\n"
            "  Install the JACK-Client binding (0.5.5 is what this bench used)\n"
            "  and re-run. Do not work around this by restoring the fallback --\n"
            "  an unattended sweep that dies at capture 9 yields a truncated\n"
            "  set that still looks like a complete measurement.")
    rec.arm()
    time.sleep(LEAD_IN)

    m = _midi_out()
    if program is not None:
        m.send_message([0xC0 | MIDI_CHANNEL, program])
        time.sleep(0.6)
    for key, value in (controls or {}).items():
        num = CC.get(key, key) if isinstance(key, str) else key
        m.send_message([0xB0 | MIDI_CHANNEL, int(num) & 0x7F,
                        max(0, min(127, int(value)))])
        time.sleep(0.15)
    sched, t0 = [], time.monotonic()
    for _n in notes:
        note, hold, gap = _n[0], _n[1], _n[2]
        vel = _n[3] if len(_n) > 3 else velocity
        on = time.monotonic() - t0
        m.send_message([0x90 | MIDI_CHANNEL, note,
                        max(1, min(127, int(vel)))])
        time.sleep(hold)
        off = time.monotonic() - t0
        # NOTE-OFF VELOCITY IS A PARAMETER, not a constant.
        #
        # It was hardcoded to 0, which silently forecloses any measurement of a
        # release-velocity-dependent field: the modified quantity can never
        # happen, so the sweep returns a flat null that means nothing. That is
        # the wrong-stage shape documented on sweep_is_responsive -- true data,
        # correct statistics, no signal, and a verdict it does not support.
        #
        # s3ked found exactly this in their rig on 2026-08-12 while about to
        # measure a field whose description is "dependence of envelope 3
        # release rate on note-off velocity". They caught it BEFORE the run by
        # reading what the field claims to do and asking whether the rig could
        # vary it. We have no such field wired today; the point is that the rig
        # should not decide that in advance.
        #
        # This stays a real 0x80 message rather than a note-on with velocity 0,
        # because the running-status shorthand cannot carry a release velocity
        # at all.
        m.send_message([0x80 | MIDI_CHANNEL, note,
                        max(0, min(127, int(off_velocity)))])
        time.sleep(gap)
        sched.append(dict(note=note, t_on=on, t_off=off, velocity=int(vel)))
    del m
    # No `hasattr(rec, 'wait')` branch any more: `rec` is always the persistent
    # JACK client now, because the jack_rec fallback that made this polymorphic
    # was removed above. A duck-typed branch that can only take one path is a
    # place a future reader reinstates the wedging path without noticing.
    rec.stop_and_write(out_wav)

    # Persist the schedule NEXT TO the capture. A .wav on its own is not
    # re-analysable: without the note on/off times you have to re-derive the
    # segmentation from the audio, and that is guesswork.
    #
    # Demonstrated on our own archive, 2026-08-11. The July gain-calibration
    # captures survive in ~/temp/amp_level_cal but their schedules do not, and
    # two segmentations I wrote half an hour apart read the SAME file as
    # -55.1/-43.1/-30.1/-19.0 dB and as -24.8/-24.4/-24.6/-24.2/-19.2 dB. Both
    # looked reasonable. That is the whole reason the open ~2 dB discrepancy
    # (§ the gain fit, above) cannot be settled from the recordings we already
    # have, which would otherwise have cost no bench time at all.
    #
    # s3ked's line, earned the same evening: a disagreement between two of your
    # own tools bounds their difference, not the measurement's uncertainty. The
    # schedule is what stops two tools from being needed in the first place.
    wav_path = Path(out_wav)
    meta = dict(wav=wav_path.name, lead_in=LEAD_IN, program=program,
                velocity=velocity,
                controls={str(k): v for k, v in (controls or {}).items()},
                device=_ACTIVE.name if _ACTIVE else None,
                capture=list(CAPTURE), notes=sched,
                captured_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    try:
        wav_path.with_suffix('.sched.json').write_text(
            json.dumps(meta, indent=2))
    except OSError as e:
        # Deliberately narrow. An earlier draft caught bare Exception, and
        # since it also used a module this file does not import, the guard
        # would have swallowed the NameError, printed a reassuring warning and
        # never written a single schedule -- a safety net that quietly removes
        # the thing it protects. Only real I/O failure is tolerable here; a
        # programming error must reach the bench operator loudly, while the
        # session is still running and the capture can be repeated.
        print(f"  WARNING: schedule not saved ({e}) -- this capture will be as "
              f"hard to re-analyse as the July ones", file=sys.stderr)
    return out_wav, sched


def _read(path):
    import numpy as np
    w = wave.open(path, 'rb')
    sr, ch = w.getframerate(), w.getnchannels()
    a = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype('float32') / 32768.0
    return a.reshape(-1, ch).mean(axis=1), sr


def envelope(path, hop=0.005):
    """RMS envelope and its time axis."""
    import numpy as np
    a, sr = _read(path)
    win = int(hop * sr)
    n = len(a) // win
    env = np.sqrt((a[:n * win].reshape(n, win) ** 2).mean(axis=1))
    return env, np.arange(n) * hop


def anchor_offset(env, t, sched, hop=0.005, search_s=5.0):
    """Map MIDI clock -> audio clock by finding the first note's onset."""
    import numpy as np
    head = env[:int(search_s / hop)]
    a = t[np.argmax(head > head.max() * 0.05)]
    return a - sched[0]['t_on']


# --- measurement helpers ---------------------------------------------------

def attack_time(env, t, on, off, frac=0.90, hop=0.005):
    """Time to reach `frac` of peak after note-on.

    **RESOLUTION FLOOR: about two hops, i.e. ~10 ms at the default.** An attack
    faster than that cannot be measured here however clean the recording is --
    the envelope simply has no samples inside it, and the result collapses
    toward the hop rather than reporting the truth.

    That is not hypothetical for this project. Our own E4B attack law,
    `0.00079 * exp(9.78 * position)`, asks for 0.79 ms at position 0 and
    9.1 ms at 0.25 -- so the entire lower HALF of that curve sits at or below
    this floor. Any calibration point taken there is measuring the instrument.

    The general rule, from s3ked 2026-08-11 after a 100 ms window reported
    exactly TWICE the LFO rate at periods near its own length: **a window
    comparable to the quantity being measured cannot measure it**, and the
    failure announces itself as a suspiciously clean factor of two rather than
    as noise. Shorten `hop` for fast attacks, and treat any result within a
    few hops of the floor as a lower bound rather than a value.
    """

    """Time from onset to `frac` of the sustained plateau."""
    import numpy as np
    seg = env[int(on / hop):int(off / hop)]
    if len(seg) < 10:
        raise ValueError(
            f"attack_time: note window {off - on:.3f}s at hop {hop}s gives "
            f"{len(seg)} frames -- too few to time anything. This is an "
            "impossible REQUEST, not a measurement outcome, and it used to "
            "return NaN, which is indistinguishable downstream from 'measured "
            "and found nothing'. Shorten hop or lengthen the note.")
    # THE ATTACK MUST HAVE FINISHED INSIDE THE NOTE.
    #
    # If the level is still climbing at note-off, `pk` is not the attack's peak
    # -- it is however far the ramp got before the window ended -- and the
    # answer becomes a property of the NOTE LENGTH, not of the parameter.
    #
    # Measured on synthetic input: with a 3.0 s note, true attacks of 5, 8, 12,
    # 20 and 40 s all reported 2.585 s. Identical to three decimals across an
    # 8x range. Swept, that reads as a clean "the attack does not depend on the
    # parameter" finding.
    #
    # s3ked hit the same species on 2026-08-12 and named the tell: every row
    # reported exactly 200 frames after note-off, an identical count across
    # eight settings. Their cause was one edit where two were needed -- they
    # raised the capture tail to 10 s and left the ANALYSIS window at 2.0 s.
    # "There is no diagnostic for that except noticing the result is wrong."
    # This is that diagnostic.
    tail = max(3, len(seg) // 10)
    rise_at_end = float(seg[-1] - seg[-tail])
    total_rise = float(np.percentile(seg, 98) - seg[0])
    if total_rise > 0 and rise_at_end > 0.05 * total_rise:
        raise ValueError(
            f"attack_time: the level is still rising at note-off "
            f"({rise_at_end / total_rise:.0%} of the total rise happens in the "
            "last tenth of the note), so the attack did not finish inside the "
            "window. Any number here would be the note length, not the "
            "parameter. Lengthen the note -- and check the ANALYSIS window "
            "was lengthened too, not just the capture.")

    pk = np.percentile(seg, 98)
    base = np.argmax(seg > pk * 0.02)
    return (np.argmax(seg > pk * frac) - base) * hop


def release_time(env, t, on, off, frac=0.01, hop=0.005, window_s=9.0):
    """Time from note-off until the level falls to `frac` of its pre-off value."""
    import numpy as np
    i0 = int(off / hop)
    seg = env[i0:i0 + int(window_s / hop)]
    lvl = np.percentile(env[int(on / hop) + 40:i0], 50)
    # These two were one `or` returning one NaN, which merged an impossible
    # request with a real measurement outcome. s3ked, 2026-08-12: two hardware
    # runs were spent blaming vibrato depth for a NaN that was actually an
    # analysis window too short for the pitch floor to exist in -- "a NaN
    # indistinguishable from 'no pitch here'". Six lines of synthetic test
    # found what two bench sessions had not.
    if len(seg) < 10:
        raise ValueError(
            f"release_time: window_s={window_s} at hop {hop}s gives "
            f"{len(seg)} frames after note-off -- too few to time. Impossible "
            "request, not a result.")
    if seg.min() > lvl * frac:
        # GENUINE outcome: the level never fell to the threshold inside the
        # window. NaN is right here, and now means only this one thing.
        return float('nan')
    return np.argmax(seg < lvl * frac) * hop


def spectrum(path, on, off, hop=0.005, skip_s=0.25):
    """Average magnitude spectrum of the sustained part of one note.

    Skips `skip_s` after onset so the attack transient does not smear the
    result, and stops at note-off. Returns (freqs_hz, magnitude).

    **RAISES on a segment too short to analyse, and that is deliberate.** It
    used to return empty arrays below 4096 samples -- and, worse, a segment
    between 4096 and 16383 samples passed that guard, produced `frames = 0`,
    and returned an ALL-ZERO spectrum. At 48 kHz with the default skip that is
    any note shorter than ~591 ms, silently reporting a flat nothing.

    A caller looking for movement reads a zero spectrum as "nothing moved",
    which is a measurement that never happened wearing the clothes of a null
    result. s3ked hit exactly this on 2026-08-11: their LFO destination test
    reported brightness as unmodulated, and the brightness row had never been
    measured at all -- 40 ms windows against a 590 ms frame requirement.

    An empty return is a lie a caller cannot see. An exception is one it
    cannot ignore.
    """
    import numpy as np
    a, sr = _read(path)
    i0, i1 = int((on + skip_s) * sr), int(off * sr)
    seg = a[i0:i1]
    n = 1 << 14
    if len(seg) < n:
        raise ValueError(
            f"spectrum() needs at least one {n}-sample frame "
            f"({n / sr * 1000:.0f} ms at {sr} Hz) after skipping {skip_s * 1000:.0f} ms "
            f"of attack, but the note gives {len(seg)} samples "
            f"({len(seg) / sr * 1000:.0f} ms). Lengthen the note, reduce skip_s, "
            f"or use a shorter frame -- do NOT read the result as a null.")
    win = np.hanning(n)
    frames = len(seg) // n
    acc = np.zeros(n // 2 + 1)
    for k in range(frames):
        acc += np.abs(np.fft.rfft(seg[k * n:(k + 1) * n] * win))
    return np.fft.rfftfreq(n, 1 / sr), acc / max(frames, 1)


def corner_frequency(freqs, mag, drop_db=3.0, ref_lo=100.0, ref_hi=500.0,
                     reference=None):
    """The -`drop_db` point of a low-pass, in Hz.

    THIS is what settles the MPC cutoff curve (checklist A3): the program JSON
    stores only a knob position (n/127), so the only way to learn what the knob
    MEANS in Hz is to measure where the filter actually rolls off.

    Source material, best to worst: **noise** (flat, continuous -- the filter is
    the only shape present), **saw** (every harmonic, so no gaps), square (odd
    harmonics only, and the search can land in an even-harmonic gap and report
    a corner that is not there), sine (useless -- one frequency says nothing
    about where a filter turns over).

    `reference` is the magnitude spectrum of the SAME source with the filter
    wide open. Pass it and the source's own spectral shape divides out, which
    is what makes a saw -- or any sustained sample -- as usable as noise. Take
    the reference once at cutoff 127 and reuse it for the whole sweep.
    """
    import numpy as np
    if len(freqs) == 0:
        raise ValueError(
            "corner_frequency: empty spectrum -- nothing was measured. The "
            "two NaN returns further down are real outcomes (reference band "
            "has no energy; no corner inside the swept range); this is not.")
    curve = np.asarray(mag, dtype='float64')
    if reference is not None:
        ref_curve = np.asarray(reference, dtype='float64')
        if len(ref_curve) == len(curve):
            # Only trust bins the reference actually excited; a harmonic gap
            # divides noise by noise and produces garbage either way.
            floor = ref_curve.max() * 1e-4
            curve = np.where(ref_curve > floor, curve / np.maximum(ref_curve, 1e-12), np.nan)

    # Smooth in log-frequency before searching. A raw noise spectrum scatters
    # several dB bin to bin, and an unsmoothed -3 dB search latches onto the
    # first bin that happens to dip -- measured on real MPC white noise it
    # reported a 545 Hz corner for a spectrum that is only 1.7 dB down at
    # 10 kHz. Smoothing is not cosmetic here; it is what makes the number mean
    # anything.
    curve = _smooth_log(freqs, curve, frac=1 / 6)

    band = (freqs >= ref_lo) & (freqs <= ref_hi)
    ref = np.nanmean(curve[band])
    if not np.isfinite(ref) or ref <= 0:
        return float('nan')

    # THE REFERENCE BAND MUST BE FLAT, or this measures the SOURCE.
    #
    # Without `reference=`, the -3 dB point is taken against this band's mean,
    # which is only the filter's transfer function if the source is flat there.
    # Measured on synthetic input: with a sawtooth (-6 dB/octave) and the
    # filter WIDE OPEN, this function reported a 502 Hz corner that does not
    # exist -- and reported the same 502 Hz for a real 3 kHz filter. It was
    # reading the sawtooth's own rolloff. On white noise it gives 3025 Hz for a
    # true 3000 Hz corner.
    #
    # s3ked hit the same class on 2026-08-12: their FILFRQ law was derived from
    # a spectral centroid and read 20-30% high by a growing amount, because a
    # centroid is a property of the source as much as the filter. Their rule,
    # and the reason this guard exists: **a ruler that saturates against its
    # source is measuring the source.**
    #
    # The clean fix is `reference=` -- divide by a wide-open capture and the
    # source cancels exactly, which is what they moved to. This guard is for
    # when that was not done, so the failure is loud instead of plausible.
    lo_half = band & (freqs < (ref_lo + ref_hi) / 2)
    hi_half = band & (freqs >= (ref_lo + ref_hi) / 2)
    if lo_half.any() and hi_half.any():
        tilt = 20 * math.log10(max(float(np.nanmean(curve[hi_half])), 1e-12)
                               / max(float(np.nanmean(curve[lo_half])), 1e-12))
        if reference is None and abs(tilt) > 3.0:
            raise ValueError(
                f"corner_frequency: the {ref_lo:.0f}-{ref_hi:.0f} Hz reference "
                f"band tilts {tilt:+.1f} dB, so the source is not flat there "
                "and the -3 dB point will be the SOURCE's rolloff, not the "
                "filter's. Use white noise, or pass reference= (a wide-open "
                "capture) so the source divides out.")
    db = 20 * np.log10(np.maximum(curve, 1e-12) / ref)

    # Require the drop to PERSIST. A real corner stays down; a noise dip does
    # not. `hold` bins is about a sixth of an octave at the top of the range.
    below = (freqs > ref_hi) & (db <= -drop_db)
    hold = max(3, int(len(freqs) * 0.002))
    run = 0
    for i in np.where(freqs > ref_hi)[0]:
        run = run + 1 if below[i] else 0
        if run >= hold:
            return float(freqs[i - run + 1])
    return float('nan')


def _smooth_log(freqs, mag, frac=1 / 6):
    """Fractional-octave smoothing: each bin averaged over [f/2^(frac/2),
    f*2^(frac/2)]. Keeps a filter knee sharp while flattening noise scatter."""
    import numpy as np
    m = np.asarray(mag, dtype='float64')
    out = np.full(len(m), np.nan)
    lo_f = freqs / (2 ** (frac / 2))
    hi_f = freqs * (2 ** (frac / 2))
    lo = np.searchsorted(freqs, lo_f, 'left')
    hi = np.searchsorted(freqs, hi_f, 'right')
    finite = np.isfinite(m)
    filled = np.where(finite, m, 0.0)
    csum = np.concatenate([[0.0], np.cumsum(filled)])
    ccnt = np.concatenate([[0], np.cumsum(finite.astype('int64'))])
    n = ccnt[hi] - ccnt[lo]
    s = csum[hi] - csum[lo]
    ok = n > 0
    out[ok] = s[ok] / n[ok]
    return out


def onset_level(env, t, on, hop=0.005, window_s=0.05):
    """Level at note onset as a FRACTION of the note's own peak.  The
    acceptance criterion for slow-attack trim checks: a genuine slow swell
    starts near 0; a mis-trimmed one starts near half."""
    import numpy as np
    i0 = int(on / hop)
    seg = env[i0:i0 + int(6.5 / hop)]
    if len(seg) < 10:
        raise ValueError(
            f"onset_level: {len(seg)} frames from onset -- too few. Impossible "
            "request, not a result.")
    return float(seg[:int(window_s / hop)].mean() / max(seg.max(), 1e-9))


#: Minimum dB a note must rise above its OWN pre-roll before a capture counts
#: as a note at all.  Ported from eosed's `lift_db()` (2026-08-21) after the
#: same failure appeared FOUR times in one evening across three sessions:
#:
#:   * eosed's capture script passed thirty silent takes as "no clipping,
#:     peaks -70.3..-65.2 dBFS, RESULT: usable" -- it checked whether the audio
#:     was too loud and never whether there was any.  **Silence does not clip.**
#:   * s3ked captured thirty on a MIDI channel the sampler was not answering.
#:   * s3ked captured thirty more on a note above the mapped key range.
#:   * and their §138, a week earlier, read silence as +31 cents of pitch drift
#:     because the estimator's threshold scaled to the window's own peak.
#:
#: **Comparing a take with ITSELF is what makes this portable**: it needs no
#: absolute reference, no level calibration, and survives a change of rig or
#: gain, none of which a peak threshold does.  A real note lifts 50-70 dB here;
#: a dropped one lifts zero.  Measured across 150 takes on 2026-08-21 the two
#: populations did not overlap and needed no tuning.
#:
#: 20 dB, not higher: a sparse percussive source measured over a fixed window
#: lifted only 23.3 dB (s3ked, rainsticks), so the margin is thinner than the
#: bass material suggests.  **If this starts rejecting real takes the fix is a
#: LONGER WINDOW, not a lower bar** -- the failure direction that matters is
#: passing silence, not refusing a quiet note.
SOUNDED_MIN_LIFT_DB = 20.0


def lift_over_preroll(env, t, on, hop=0.005, window_s=0.30):
    """dB the note rises above the pre-roll of its own capture.

    `on` is the note-on time; everything before it is pre-roll and is the only
    reference used.  Returns +inf when there is no pre-roll to compare against,
    which is a caller error rather than a silent pass -- see `sounded()`.
    """
    import numpy as np
    i0 = int(on / hop)
    pre = env[:i0]
    note = env[i0:i0 + int(window_s / hop)]
    if len(pre) < 3 or len(note) < 3:
        raise ValueError(
            f"lift_over_preroll: {len(pre)} pre-roll and {len(note)} note "
            "frames -- a capture with no pre-roll cannot be gated this way. "
            "Record silence before the note-on.")
    floor = float(np.median(pre)) or 1e-9
    return float(20.0 * np.log10(max(float(note.max()), 1e-9) / floor))


def sounded(env, t, on, hop=0.005, min_lift_db=SOUNDED_MIN_LIFT_DB):
    """Did a note actually happen?  Gate every capture on this BEFORE analysing
    it: a measurement of silence is confident, well-behaved and worthless, and
    it looks exactly like a measurement of a very dark sound."""
    return lift_over_preroll(env, t, on, hop=hop) >= min_lift_db


#: Between/within ratio required before two conditions count as different.
#: **Fixed here, before any data is looked at.** s3ked, 2026-08-11: their
#: probe used F > 4 and their reusable helper used 3x, and the same data came
#: back "established" under one and "undecidable at 2.68" under the other --
#: two thresholds, one of them chosen while looking at the answer. A bar that
#: moves after the fact is not a bar. Change this constant only with a reason
#: that has nothing to do with the result it would flip.
SEPARABLE_RATIO = 3.0


def sweep_is_responsive(settings, readings, spans=None, min_distinct=3,
                        min_rho=0.7, max_reversal=0.15,
                        min_setting_spread=0.05):
    """Did the instrument actually follow the parameter? Raises if not.

    **WHAT THIS FUNCTION CANNOT CATCH — read before treating a pass as
    clearance.** The measurement faults found across this project and s3ked's
    on 2026-08-12 fall into six shapes. Five are mechanical and are checked
    here: frozen readings, frozen settings, a collapsed span, an unresponsive
    reading, a folded curve. The sixth is **testing a field on a stage it does
    not govern**, and it cannot be checked by any statistic, by construction.

    A wrong-stage run produces a TRUE measurement of a condition nobody wanted
    measured. The data is correct, every number computed from it is correct,
    and there is no signal to find. s3ked's `K_DAR3` read a flat null across
    every note and depth with a live route and a flat control — they had timed
    a phase the field does not govern, and against the two stages its own
    description names it moves by 2.6x. Their `V_ATT3` read 0.000 s everywhere
    because the attack it scales had been set to instant.

    Both would pass every check below.

    The only available signal is TEXTUAL: what does the field claim to do, and
    was that thing happening while you measured? Three shapes to recognise —
    an attack scaler tested on an instant attack, a release scaler on a note
    that never releases, a decay scaler on a sustain of 100 %. Each reads
    exactly like a dead field, and no amount of tightening the controls will
    show it.

    Call this on a completed sweep BEFORE fitting anything to it. Two failures,
    both of which read as findings rather than faults:

    **Frozen** -- a derived quantity bit-identical where the settings differ.
    s3ked found three (2026-08-12): PANDEL returning an impossible -0.150 s at
    all five settings (an identical impossible value is a floor); a resonance
    peak unchanged across smoothing widths from 6 to 40 Hz, which cannot happen
    for a peak narrower than the window; and a release sweep reporting exactly
    200 frames after note-off at all eight settings, because the capture tail
    had been lengthened and the analysis window had not.

    **Compressed** -- readings that differ but do not TRACK. This is the one a
    distinctness count misses, and it is our own historical failure:
    `~/temp/cal_cutoff.txt` swept the E4XT cutoff over 250:1 and the corner
    column moved 2.5:1, taking nine distinct values while following nothing.
    Bit-distinct, entirely unresponsive. That sweep was abandoned, but nothing
    in the code would have objected to fitting it.

    `min_distinct` is 3 rather than 2 deliberately (s3ked's reasoning, and it
    is right): two distinct values across a six-point sweep is nearly as
    suspicious as one, and any real law passes trivially. NaN is ignored --
    a detector that failed to read is a different problem with a different
    message, and conflating them is the fault this whole file is about.
    """
    import numpy as np
    xs = np.asarray(settings, dtype='float64')
    ys = np.asarray(readings, dtype='float64')
    ok = np.isfinite(xs) & np.isfinite(ys)
    xs, ys = xs[ok], ys[ok]
    if len(ys) < 3:
        raise ValueError(
            f"sweep_is_responsive: {len(ys)} finite readings -- too few to "
            "judge. An impossible request, not a verdict on the sweep.")

    # THE MANIPULATED QUANTITY MUST ALSO HAVE MOVED.
    #
    # Checking only the readings is half the check, and the missing half is
    # the more dangerous one: a frozen INDEPENDENT variable produces perfectly
    # well-behaved readings that mean nothing at all. Nothing in the output
    # looks wrong, because the output is a genuine measurement of a condition
    # that never changed.
    #
    # s3ked hit it twice on 2026-08-12 trying to vary an envelope's travel
    # distance. Sweeping ENV2L1 with SUSTN2 pinned left the envelope always
    # ending at full, so the span read 2.07 octaves at every setting; making
    # SUSTN2 follow ENV2L1 still left it at 1.88..2.07. Both runs produced
    # clean, varying readings and answered a question nobody had asked.
    # Distinctness alone is not enough here either, for the same reason it was
    # not enough for the readings: s3ked's frozen span read 1.88..2.07, three
    # distinct values that barely move. Relative spread is the honest measure.
    #
    # THE DEFAULT ONLY CATCHES THE EGREGIOUS CASE, and this is a real limit
    # rather than a tuning problem. Their 1.88..2.07 is a 9.6 % spread and
    # passes at 5 %; it was a failure only because they expected ENV2L1 20..99
    # to move the span several-fold. No universal threshold can know that.
    #
    # So `min_setting_spread` is for the caller to STATE what they expected
    # before running -- the predict-the-colour habit applied to the
    # independent variable. If you are varying a span to distinguish a rate
    # from a duration and you need it to double, pass 1.0 and find out in the
    # first second rather than after the fit.
    set_distinct = len(set(np.round(xs, 12)))
    denom = max(abs(float(np.mean(xs))), 1e-12)
    if (float(xs.max() - xs.min()) / denom < min_setting_spread
            and set_distinct >= min_distinct):
        raise ValueError(
            f"FROZEN SETTINGS: the manipulated quantity spans only "
            f"{float(xs.max() - xs.min()):.3g} about a mean of "
            f"{float(np.mean(xs)):.3g} ({float(xs.max() - xs.min()) / denom:.1%}) "
            f"across {len(xs)} points. It is technically distinct and did not "
            "meaningfully move. The readings may vary perfectly well and still "
            "mean nothing -- check that the thing you intended to vary is the "
            "thing that moved.")
    if set_distinct < min_distinct:
        raise ValueError(
            f"FROZEN SETTINGS: the manipulated quantity takes only "
            f"{set_distinct} distinct value(s) {sorted(set(np.round(xs, 6)))} "
            f"across {len(xs)} points. The readings may vary perfectly well "
            "and still mean nothing -- they are measuring a condition that "
            "did not change. Check that the thing you intended to vary is the "
            "thing that moved.")

    distinct = len(set(np.round(ys, 12)))
    if distinct < min_distinct:
        raise ValueError(
            f"FROZEN SWEEP: {len(ys)} readings take only {distinct} distinct "
            f"value(s) {sorted(set(np.round(ys, 6)))}. Either the instrument "
            "is sitting at a floor or the field does nothing -- different "
            "follow-ups, same interruption. If a capture length was changed, "
            "check the ANALYSIS window was changed too.")

    # RANK correlation, not a span ratio.
    #
    # The first version of this compared the log-span of the readings against
    # the log-span of the settings, and it was doubly wrong. It let our own
    # historical failure through at 0.17 against a 0.15 threshold -- scraping
    # past by 0.02 on the exact data it was written to catch. And the metric
    # is meaningless whenever the two axes are different quantities: a byte
    # setting against a reading in dB has no shared scale to take a ratio of.
    #
    # Spearman is unit-free and asks the question that actually matters: does
    # the reading MOVE WITH the parameter? A ruler reading its own source, or
    # one against a floor, scores near zero however many distinct values its
    # noise happens to produce.
    def _rank(v):
        order = np.argsort(v, kind='mergesort')
        r = np.empty(len(v), dtype='float64')
        r[order] = np.arange(len(v), dtype='float64')
        return r

    rx, ry = _rank(xs), _rank(ys)
    if rx.std() > 0 and ry.std() > 0:
        rho = float(np.corrcoef(rx, ry)[0, 1])
        if abs(rho) < min_rho:
            raise ValueError(
                f"UNRESPONSIVE SWEEP: rank correlation between settings and "
                f"readings is {rho:+.2f} over {len(ys)} points, with "
                f"{distinct} distinct readings. The values differ but do not "
                "move WITH the parameter -- which is what a ruler reading its "
                "own source, or an instrument against a floor, produces. "
                "Fitting this would give a law about the instrument.")

    # FOLDS. A calibration curve exists to be INVERTED, and a reading that
    # reverses direction cannot be: two settings give the same answer, and
    # only one branch is usable.
    #
    # This is the third distinct fault in one archived sweep of ours. The
    # centroid column of `cal_cutoff.txt` tracks the cutoff downward for ten
    # points and then RISES again for the last three -- so it passes both
    # checks above while being unusable below its minimum. s3ked recorded the
    # same fold as a property of the filter before finding it was a property
    # of the centroid: "a resonance peak does not fold".
    # Detected as a RUN against the trend, not as a magnitude. My first
    # version used "reversal exceeds 15% of the range" and let the real case
    # through at 10.2% -- the second metric in this function whose first form
    # missed the data it was written for. Noise reverses for one step; a fold
    # reverses for several consecutive ones, which is the actual signature.
    o = np.argsort(xs, kind='mergesort')
    ys_o = ys[o]
    steps = np.diff(ys_o)
    rng_y = float(ys_o.max() - ys_o.min())
    if rng_y > 0 and len(steps) >= 4:
        trend = 1.0 if steps.sum() >= 0 else -1.0
        run = worst = 0
        moved = worst_moved = 0.0
        for st in steps:
            if st * trend < 0:
                run += 1
                moved += abs(float(st))
                if run > worst or (run == worst and moved > worst_moved):
                    worst, worst_moved = run, moved
            else:
                run, moved = 0, 0.0
        if worst >= 3 and worst_moved / rng_y > 0.03:
            raise ValueError(
                f"FOLDED SWEEP: {worst} consecutive readings move AGAINST the "
                f"trend, covering {worst_moved / rng_y:.0%} of the range. The "
                "curve is not invertible there -- two settings give the same "
                "reading and only one branch can be used. Check whether the "
                "fold belongs to the machine or to the instrument; a centroid "
                "of the machine or of the instrument; a centroid folds and a "
                "resonance peak does not.")
    # COLLAPSING SPAN = TRUNCATION, and it is free if the caller logged the
    # excursion beside each reading (s3ked, 2026-08-12).
    #
    # Their case: with the estimator fixed, the fit still came back r2 0.65 and
    # the spans fell 2.10 -> 1.40 -> 0.56 across the slow settings. The stage
    # happens DURING the note, and the note was 1.5 s -- inherited from a
    # different probe where 1.5 s was correct. The reading was a property of
    # the note length again, and the span column said so without anyone
    # looking at the fit.
    #
    # This is the same family as attack_time reporting the note length, and as
    # our own ENVSPAN question. An answer that shrinks as the parameter slows
    # is an answer about the window.
    if spans is not None:
        sp = np.asarray(spans, dtype='float64')[ok]
        if len(sp) >= 4 and np.isfinite(sp).all() and sp.std() > 0:
            rho_s = float(np.corrcoef(_rank(ys), _rank(sp))[0, 1])
            if rho_s < -0.8:
                raise ValueError(
                    f"TRUNCATED SWEEP: the excursion shrinks as the reading "
                    f"grows (rank correlation {rho_s:+.2f}) -- spans "
                    f"{sp.min():.3g}..{sp.max():.3g}. The slow settings are "
                    "not completing inside the window, so those readings "
                    "describe the window rather than the machine. Lengthen "
                    "the note, and check the ANALYSIS window with it.")
    return True


def replicate(measure, n=3):
    """Run one condition `n` times and return (mean, spread, values).

    `measure` takes no arguments and returns a float -- close over the
    condition, e.g. ``lambda: attack_time(*capture(depth=17))``.

    **The gap this fills.** Until 2026-08-11 every hardware measurement in
    this project -- E4XT cutoff, gain, pan, stereo; the MPC 3 cutoff and
    envelope curves -- was taken exactly ONCE per condition. We did validate
    the instrument (0.39 % over five takes, see verify_isolation) but that is
    a single global figure standing in for an error bar we never had: it
    cannot catch a condition whose own scatter is larger, which is exactly
    what happens near a detector's threshold or on a slow attack where onset
    estimation jitters.

    s3ked found the cost. Three separate runs at "is ATTAK2 depth-dependent?"
    came back inconclusive; the cause was not too few conditions but no error
    bar at all, so a 17 % spread between conditions could not be told from
    17 % of noise within one. Three captures per condition gave a pooled
    within-condition scatter of 0.65 % and the question answered immediately.

    Spread is the sample standard deviation, or 0.0 for n == 1 -- which is
    the honest value, and is why `separable()` refuses to rule on it.
    """
    vals = [float(measure()) for _ in range(max(1, int(n)))]
    mean = sum(vals) / len(vals)
    if len(vals) < 2:
        return mean, 0.0, vals
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return mean, var ** 0.5, vals


def separable(groups, ratio=SEPARABLE_RATIO):
    """Do these conditions actually differ, or is the spread just noise?

    `groups` is {label: [values...]} from `replicate`. Returns
    (verdict, between, within) with verdict in {'differ', 'same',
    'undecidable'}.

    Compares the spread of the group MEANS against the pooled scatter WITHIN
    the groups. Above `ratio` the conditions differ; at or below 1.0 there is
    nothing to explain; between the two the measurement cannot rule and says
    so. **'undecidable' is not 'same'** -- it means take more replicates, and
    reporting it as a null result is the mistake that makes a blind test look
    like a clean one.

    **What this ratio is the answer to -- measured, because it is not what it
    looks like.** It is an EFFECT SIZE, not a significance test. A real F-test
    grows with the number of replicates; this one converges on the true
    between/within ratio and stays there (2 sd effect: 2.31 at n=3, 2.10 at
    n=8, 2.01 at n=80, 1500 trials each). Consequences, both load-bearing:

    * A verdict of 'undecidable' does NOT mean "take more captures". More
      captures make the estimate accurate, not sensitive. An effect that sits
      at 2.7x noise will still read ~2.7 at n=80 and will never cross a 3x
      bar. If you need to resolve it, you must lower the noise or raise the
      effect -- a longer capture, a cleaner tap, a wider condition spacing --
      not repeat the same measurement more times.
    * At n=3 the estimate is biased UPWARD (2.31 for a true 2.0), so small-n
      ratios flatter the effect. Treat a bare-crossing 3.1 at n=3 as thin.

    Detection floor at n=3, 2000 trials: 1 sd 2 %, 2 sd 18 %, 3 sd 57 %,
    4 sd 88 %, 6 sd 100 %. Pure noise reached 'differ' 0 times in 4000. The
    bar is conservative by design: when it says 'differ', believe it; when it
    does not, the effect may still be real and merely smaller than 3x noise.

    Raises rather than guessing if any group has fewer than 2 values: with no
    within-group scatter the ratio is infinite and every condition would
    "differ", which is the failure mode this exists to prevent.
    """
    thin = [k for k, v in groups.items() if len(v) < 2]
    if thin:
        raise ValueError(
            f"replicates missing for {thin} -- separable() cannot compare a "
            "between-group spread against a within-group scatter that was "
            "never measured. Use replicate(..., n=3).")
    means = [sum(v) / len(v) for v in groups.values()]
    gm = sum(means) / len(means)
    between = (sum((m - gm) ** 2 for m in means) / max(1, len(means) - 1)) ** 0.5
    within = (sum(sum((x - sum(v) / len(v)) ** 2 for x in v)
                  for v in groups.values())
              / sum(len(v) - 1 for v in groups.values())) ** 0.5
    # Any condition whose replicates are all IDENTICAL was not re-measured --
    # `measure` re-analysed one capture instead of taking a new one. That
    # manufactures a ratio out of nothing, and checking only the POOLED
    # scatter does not catch it: s3ked's eighteenth pass had sd 0.000 on
    # fifteen of sixteen conditions, and the one genuine condition kept the
    # pool above zero while the comparison reported a ratio of 3645 and called
    # it "varies". Fed the same shape, an earlier version of this function
    # returned 'differ' at 952. The check has to be per condition.
    frozen = [k for k, v in groups.items() if max(v) == min(v)]
    if frozen:
        raise ValueError(
            f"conditions {frozen} have identical replicates -- `measure` must "
            "RE-CAPTURE, not re-analyse a cached recording. A repeat that "
            "resamples nothing gives a fictitious error bar, and one live "
            "condition is enough to hide it in the pooled figure.")
    if within <= 0:
        raise ValueError("within-group scatter is zero -- captures identical?")
    f = between / within
    return ('differ' if f > ratio else 'same' if f <= 1.0 else 'undecidable',
            between, within)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--note', type=int, default=48)
    ap.add_argument('--program', type=int, default=None)
    ap.add_argument('--hold', type=float, default=6.0)
    ap.add_argument('--keep', help='write the recording here instead of a temp file')
    ap.add_argument('--device', default=DEFAULT_DEVICE,
                    choices=sorted(DEVICES), help='which instrument to drive')
    ap.add_argument('--midi-port', help='override the device MIDI port match')
    ap.add_argument('--channel', type=int,
                    help='override the MIDI channel (1-indexed)')
    ap.add_argument('--cc', action='append', default=[], metavar='NAME=VALUE',
                    help='set a controller before the note, e.g. --cc cutoff=64 '
                         '(names: ' + ', '.join(sorted(CC)) + ', or a number)')
    ap.add_argument('--corner', action='store_true',
                    help='also report the measured -3 dB corner (use a '
                         'broadband source, not a pitched sample)')
    ap.add_argument('--list-ports', action='store_true',
                    help='print the visible MIDI out ports and exit')
    args = ap.parse_args()

    if args.list_ports:
        import rtmidi
        for i, p in enumerate(rtmidi.MidiOut().get_ports()):
            print(f"  [{i}] {p}")
        return

    global MIDI_PORT_MATCH, MIDI_CHANNEL
    use_device(args.device)
    if args.midi_port:
        MIDI_PORT_MATCH = args.midi_port
    if args.channel:
        MIDI_CHANNEL = args.channel - 1

    controls = {}
    for item in args.cc:
        key, _, value = item.partition('=')
        controls[key if key in CC else int(key)] = int(value)

    wav, sched = play_sequence([(args.note, args.hold, 2.0)],
                               program=args.program, out_wav=args.keep,
                               controls=controls or None)
    env, t = envelope(wav)
    off = anchor_offset(env, t, sched)
    e = sched[0]
    print(f"  recording: {wav}")
    print(f"  note {e['note']}  attack t90={attack_time(env, t, e['t_on']+off, e['t_off']+off):.3f}s"
          f"  release t-40dB={release_time(env, t, e['t_on']+off, e['t_off']+off):.3f}s"
          f"  onset={onset_level(env, t, e['t_on']+off)*100:.1f}% of peak")
    if args.corner:
        f, mag = spectrum(wav, e['t_on'] + off, e['t_off'] + off)
        print(f"  -3 dB corner: {corner_frequency(f, mag):.0f} Hz")


if __name__ == '__main__':
    main()



# NOTE: pitch measurement lives in the SIBLING project, not here.
#
# A spectral-peak fundamental_hz() was written here on 2026-08-16 and deleted
# the same hour: s3ked's probes/measure.py already had one, and theirs is the
# better instrument by a distance. It interpolates the autocorrelation peak
# (an integer lag quantises to 9.4 cents at note 60 -- coarser than the
# parameter being measured, and their first tuning sweep duly returned
# 0,0,0,0,0,0,9.486,19.02 cents, which are lag steps wearing the clothes of
# results), carries explicit octave protection, and refuses an impossible
# window rather than returning NaN that reads as "no pitch here".
#
# Use:
#     sys.path.insert(0, '~/git-repos/s3ked')
#     from probes.measure import fundamental_hz, cents_between, rms_db
#
# Duplicating it here would have given this project a second, worse copy of a
# measurement both projects depend on -- the two-copies-of-one-thing failure
# VinSamLib hit twice this week with format lists.
