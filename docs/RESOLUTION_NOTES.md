<!--
SPDX-License-Identifier: GPL-2.0-or-later
SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
-->

# mpc2emu — Resolution Notes

> **How to use this file:**
> Every open item in `TODO.md` has a corresponding entry here that answers
> *how* to fix it — code patches, hardware RE procedures, or open questions.
> When a TODO item is resolved, remove it from `TODO.md` and mark it done
> here with a date.
>
> This file is the companion to `TODO.md`.  `TODO.md` says *what* is broken;
> this file says *how* to fix it.  Keep them in sync.

---

<!-- INDEX:BEGIN -->
- [§SIBCHECK — three sibling findings checked against our own corpora (2026-08-15)](#sibcheck-three-sibling-findings-checked-against-our-own-corpora-2026-08-15)
- [§NAMEBYTE — name fields decoded as ASCII (E4B/EMU3 DONE; EIII/SF2/MPC60 open)](#namebyte-name-fields-decoded-as-ascii-e4bemu3-done-eiiisf2mpc60-open)
- [§KRZNAME16 — a full-length KRZ name picked up the bytes after it (2026-08-09)](#krzname16-a-full-length-krz-name-picked-up-the-bytes-after-it-2026-08-09)
- [§ISODIR — EMU3 CD image drops banks past the 16th (how to fix)](#isodir-emu3-cd-image-drops-banks-past-the-16th-how-to-fix)
- [§E4BRATE — EOS4 sample-rate field (how to fix the resample pitch bug)](#e4brate-eos4-sample-rate-field-how-to-fix-the-resample-pitch-bug)
- [§MPCFILT — MPC filter dropped at max cutoff (how to fix)](#mpcfilt-mpc-filter-dropped-at-max-cutoff-how-to-fix)
- [§MODELPARAMS — carry choke group / one-shot / key-track / round-robin (design)](#modelparams-carry-choke-group-one-shot-key-track-round-robin-design)
- [§MPC39 — MPC Standalone 3.9.0 gzipped-JSON `.xpm` parser (how to fix)](#mpc39-mpc-standalone-390-gzipped-json-xpm-parser-how-to-fix)
- [§AUTOLOOP — Auto sustain-loop (IMPLEMENTED, branch `autoloop`, 2026-07-25)](#autoloop-auto-sustain-loop-implemented-branch-autoloop-2026-07-25)
- [§CR — Code-review findings (2026-06-10), fix recipes](#cr-code-review-findings-2026-06-10-fix-recipes)
- [Index](#index)
- [1. Amp envelope: decay byte — RESOLVED (2026-06-08)](#1-amp-envelope-decay-byte-resolved-2026-06-08)
- [2. `_fenv_rate()` calibration — RESOLVED (2026-06-08)](#2-_fenv_rate-calibration-resolved-2026-06-08)
- [3. Ping-pong loops — RESOLVED + faithfully reproduced (2026-06-08)](#3-ping-pong-loops-resolved-faithfully-reproduced-2026-06-08)
- [4. Swept EQ / Phaser / Flanger / Vocal / Morph filter bytes — RESOLVED (2026-06-08)](#4-swept-eq-phaser-flanger-vocal-morph-filter-bytes-resolved-2026-06-08)
- [5. Zone entry: `fine_tune` and `volume` fields](#5-zone-entry-fine_tune-and-volume-fields)
- [6. EXS24 v1.1 zone fields misassigned — CRITICAL](#6-exs24-v11-zone-fields-misassigned-critical)
- [7. EXS24 GROUP_V11: stereo doubling — APPLIED (2026-06-08)](#7-exs24-group_v11-stereo-doubling-applied-2026-06-08)
- [8. EXS24 multi-velocity layers](#8-exs24-multi-velocity-layers)
- [9. SF2 MIDI program numbers](#9-sf2-midi-program-numbers)
- [10. SMP (non-transpose) velocity grouping](#10-smp-non-transpose-velocity-grouping)
- [11. HDA directory >16 entries](#11-hda-directory-16-entries)
- [12. TAL-Sampler filtermode encoding — FULLY RESOLVED (2026-06-08)](#12-tal-sampler-filtermode-encoding-fully-resolved-2026-06-08)
- [13. E4B vpar[42] = Chorus Amount — RESOLVED (2026-06-08)](#13-e4b-vpar42-chorus-amount-resolved-2026-06-08)
- [14. EXS24 PPC big-endian — WON'T FIX / removed (2026-06-08)](#14-exs24-ppc-big-endian-wont-fix-removed-2026-06-08)
- [15. LFO modulation routing](#15-lfo-modulation-routing)
- [16. Binary MPC `.pgm` format](#16-binary-mpc-pgm-format)
- [17. Filter envelope — reproduction gaps (strategy, 2026-06-08)](#17-filter-envelope-reproduction-gaps-strategy-2026-06-08)
- [18. XPM (MPC) envelope value → time curve — measured & APPLIED (2026-06-09)](#18-xpm-mpc-envelope-value-time-curve-measured-applied-2026-06-09)
- [19. Mod-cord depth scaling — absolute-unit calibration (strategy, 2026-06-10)](#19-mod-cord-depth-scaling-absolute-unit-calibration-strategy-2026-06-10)
- [20. Regression sweep (input → E4B round-trip), 2026-06-11](#20-regression-sweep-input-e4b-round-trip-2026-06-11)
- [Open questions for Jan](#open-questions-for-jan)
- [XPM TuneCoarse / TuneFine dropped — fix strategy](#xpm-tunecoarse-tunefine-dropped-fix-strategy)
- [XPM long-common-prefix name truncation — fix strategy](#xpm-long-common-prefix-name-truncation-fix-strategy)
- [XPM `KeygroupWheelToLfo` (mod-wheel → LFO depth) — fix strategy](#xpm-keygroupwheeltolfo-mod-wheel-lfo-depth-fix-strategy)
- [XPM `RootNote=0` non-transpose mis-detection — fix strategy](#xpm-rootnote0-non-transpose-mis-detection-fix-strategy)
- [SFZ keyswitch articulations — fix strategy  → **DECIDED: one preset per articulation, drop KS keys (Jan 2026-06-12)**](#sfz-keyswitch-articulations-fix-strategy-decided-one-preset-per-articulation-drop-ks-keys-jan-2026-06-12)
- [SFZ overlapping-region stacking — fix strategy](#sfz-overlapping-region-stacking-fix-strategy)
- [XPM slice-based playback — fix strategy](#xpm-slice-based-playback-fix-strategy)
- [Fixed (un-gated) LFO→Filter on MS-20 patches — pending aural check](#fixed-un-gated-lfofilter-on-ms-20-patches-pending-aural-check)
- [§KRZ-PROG — K2000 program parameters (envelopes / filter / LFOs) — fix strategy](#krz-prog-k2000-program-parameters-envelopes-filter-lfos-fix-strategy)
- [§KRZ velocity-split layers — IMPLEMENTED 2026-06-24](#krz-velocity-split-layers-implemented-2026-06-24)
- [§XPM release-time recalibration — fix strategy (2026-06-24)](#xpm-release-time-recalibration-fix-strategy-2026-06-24)
- [§BB. Band-Boost (BB 2P/4P/6P/8P) filters → wrong target (2026-06-25)](#bb-band-boost-bb-2p4p6p8p-filters-wrong-target-2026-06-25)
- [§KRZ-CWM — Fidelity gaps found via ConvertWithMoss cross-reference (2026-07-22)](#krz-cwm-fidelity-gaps-found-via-convertwithmoss-cross-reference-2026-07-22)
- [§KRZ-READER — KRZ added as a source format (2026-07-27)](#krz-reader-krz-added-as-a-source-format-2026-07-27)
- [§CWM19 — Input-parser feature-parity gaps found via ConvertWithMoss 19.1.0 (2026-07-25)](#cwm19-input-parser-feature-parity-gaps-found-via-convertwithmoss-1910-2026-07-25)
- [§E4BREAD — E4B reading gaps found via ConvertWithMoss's independent E4B reader (FIXED 2026-07-26)](#e4bread-e4b-reading-gaps-found-via-convertwithmosss-independent-e4b-reader-fixed-2026-07-26)
- [§E4BREAD2 — Two more E4B reading gaps found via ConvertWithMoss PR #242 (FIXED 2026-07-28)](#e4bread2-two-more-e4b-reading-gaps-found-via-convertwithmoss-pr-242-fixed-2026-07-28)
- [§E4BLEVEL — Amp-envelope sustain LEVEL byte is exponential/dB-law on real hardware — WRITER FIXED + HW-CONFIRMED (2026-07-28)](#e4blevel-amp-envelope-sustain-level-byte-is-exponentialdb-law-on-real-hardware-writer-fixed-hw-confirmed-2026-07-28)
- [§E4BPARAMHUNT — Live-SysEx parameter hunting: a new, fast method for finding unknown `vpar` bytes (2026-07-28)](#e4bparamhunt-live-sysex-parameter-hunting-a-new-fast-method-for-finding-unknown-vpar-bytes-2026-07-28)
- [§EIII — E-mu Emulator IIIX/ESI writer+parser (design notes, 2026-07-28)](#eiii-e-mu-emulator-iiixesi-writerparser-design-notes-2026-07-28)
- [§CWM-LFOVOL — SFZ/SF2 volume LFO (tremolo) reading, read-side only (2026-07-28)](#cwm-lfovol-sfzsf2-volume-lfo-tremolo-reading-read-side-only-2026-07-28)
- [§EIII-CWM — Five reader gaps found cross-referencing ConvertWithMoss (FIXED 2026-07-29)](#eiii-cwm-five-reader-gaps-found-cross-referencing-convertwithmoss-fixed-2026-07-29)
- [§PARSERPERF — Parser performance pass: the cost was a handful of per-sample loops and two directory walks, not the algorithms (2026-07-29)](#parserperf-parser-performance-pass-the-cost-was-a-handful-of-per-sample-loops-and-two-directory-walks-not-the-algorithms-2026-07-29)
- [§MPC3XPM — MPC 3.x `.xpm` is gzip+JSON, not XML (found 2026-07-30)](#mpc3xpm-mpc-3x-xpm-is-gzipjson-not-xml-found-2026-07-30)
- [§E4BSTEREO — E4B stereo samples: layout RE'd from the corpus, decode bug fixed, write side implemented (2026-07-29)](#e4bstereo-e4b-stereo-samples-layout-red-from-the-corpus-decode-bug-fixed-write-side-implemented-2026-07-29)
- [§MONO — Stereo is the default; mono is a vintage-fit reduction (2026-07-29)](#mono-stereo-is-the-default-mono-is-a-vintage-fit-reduction-2026-07-29)
- [§E4BFILTCAL — Cutoff, resonance and zone-gain measured on the E4XT (2026-07-31)](#e4bfiltcal-cutoff-resonance-and-zone-gain-measured-on-the-e4xt-2026-07-31)
- [§POLY — Per-note voice budget: teaching the size/fit path that stereo costs double (2026-08-01)](#poly-per-note-voice-budget-teaching-the-sizefit-path-that-stereo-costs-double-2026-08-01)
- [§OSFILE — Auditing the corpus count: the raw-byte bank scan over-counted by 9% (2026-08-01)](#osfile-auditing-the-corpus-count-the-raw-byte-bank-scan-over-counted-by-9-2026-08-01)
- [§RESAMPALIAS — `resample_to_rate` aliased worse than the code it was better than (FIXED 2026-08-02)](#resampalias-resample_to_rate-aliased-worse-than-the-code-it-was-better-than-fixed-2026-08-02)
- [§WAVFMT — `load_wav` rejected every WAV that is not format code 0x0001 (FIXED 2026-08-02)](#wavfmt-load_wav-rejected-every-wav-that-is-not-format-code-0x0001-fixed-2026-08-02)
- [§KRZSTEREO — the stereo sample layout, read from the corpus (2026-08-01)](#krzstereo-the-stereo-sample-layout-read-from-the-corpus-2026-08-01)
- [§KRZSTEREO2 — what makes a stereo sample play as stereo (2026-08-02)](#krzstereo2-what-makes-a-stereo-sample-play-as-stereo-2026-08-02)
- [§KRZKEYMAP — per-entry sample assignment: the entry index is off by 12 (FIXED 2026-08-02)](#krzkeymap-per-entry-sample-assignment-the-entry-index-is-off-by-12-fixed-2026-08-02)
- [§MPC3D3 — track and project containers, and exact sample resolution (FIXED 2026-08-03)](#mpc3d3-track-and-project-containers-and-exact-sample-resolution-fixed-2026-08-03)
- [§CUTOFFKNOB — a candidate MPC knob → Hz curve, from ConvertWithMoss (**REFUTED 2026-08-03**, see §MPCCUTOFF)](#cutoffknob-a-candidate-mpc-knob-hz-curve-from-convertwithmoss-refuted-2026-08-03-see-mpccutoff)
- [§MPCCUTOFF — the MPC 3 cutoff knob, measured (SETTLED 2026-08-03, hardware)](#mpccutoff-the-mpc-3-cutoff-knob-measured-settled-2026-08-03-hardware)
- [§MPCENV — MPC 3 envelope times, measured (SETTLED 2026-08-03, hardware)](#mpcenv-mpc-3-envelope-times-measured-settled-2026-08-03-hardware)
- [§MPC3BANK — an MPC 3 project is a bank; every keygroup track is a preset (2026-08-03)](#mpc3bank-an-mpc-3-project-is-a-bank-every-keygroup-track-is-a-preset-2026-08-03)
- [§XPMGAPS — three MPC layer fields we drop and ConvertWithMoss reads (**1 and 2 IMPLEMENTED 2026-08-03**, branch `cwm_ketchup`)](#xpmgaps-three-mpc-layer-fields-we-drop-and-convertwithmoss-reads-1-and-2-implemented-2026-08-03-branch-cwm_ketchup)
- [§XPMDRUM — MPC drum programs convert; sample-free program types now refuse (2026-08-03)](#xpmdrum-mpc-drum-programs-convert-sample-free-program-types-now-refuse-2026-08-03)
- [§XPMDRUM2X — an MPC 2.x project gathered only its keygroup programs (FIXED 2026-08-04)](#xpmdrum2x-an-mpc-2x-project-gathered-only-its-keygroup-programs-fixed-2026-08-04)
- [§XPMNAMES — truncated-name dedup silently dropped every second sample (FIXED 2026-08-04)](#xpmnames-truncated-name-dedup-silently-dropped-every-second-sample-fixed-2026-08-04)
- [§XPMTRUNC — head-vs-tail sample-name truncation, decided per program (2026-08-04)](#xpmtrunc-head-vs-tail-sample-name-truncation-decided-per-program-2026-08-04)
- [§XPMXFADE — HW-2 answered: the MPC does not apply the loop crossfade (2026-08-04, measured)](#xpmxfade-hw-2-answered-the-mpc-does-not-apply-the-loop-crossfade-2026-08-04-measured)
- [§XPMREV — HW-1 answered: the MPC does reverse on `Direction` (2026-08-04, measured)](#xpmrev-hw-1-answered-the-mpc-does-reverse-on-direction-2026-08-04-measured)
- [§AKAIIMG — AKAI disk images: written, read, and byte-identical to an independent implementation (2026-08-05)](#akaiimg-akai-disk-images-written-read-and-byte-identical-to-an-independent-implementation-2026-08-05)
- [§CWM202 — ConvertWithMoss cross-check (2026-08-13)](#cwm202-convertwithmoss-cross-check-2026-08-13)
- [§CWM201 — ConvertWithMoss 20.1.0 cross-check (2026-08-08)](#cwm201-convertwithmoss-2010-cross-check-2026-08-08)
- [§GIGE2E — GigaSampler end to end, over 146 real files (2026-08-09)](#gige2e-gigasampler-end-to-end-over-146-real-files-2026-08-09)
- [KRZ keymap: reporting the up-pitch ceiling clamp](#krz-keymap-reporting-the-up-pitch-ceiling-clamp)
- [§ENVSPAN — ANSWERED: the EOS envelope byte is a RATE (2026-08-18, hardware)](#envspan-answered-the-eos-envelope-byte-is-a-rate-2026-08-18-hardware)
- [§RULER — a ruler that saturates against its source is measuring the source](#ruler-a-ruler-that-saturates-against-its-source-is-measuring-the-source)
- [§AGREEMENT — what a second source actually rules out](#agreement-what-a-second-source-actually-rules-out)
- [§AKAIAUX — first read of the four auxiliary file types (2026-08-17)](#akaiaux-first-read-of-the-four-auxiliary-file-types-2026-08-17)
- [§KRZFILL — `id − base` is not position, and the failure is silent (2026-08-17)](#krzfill-id-base-is-not-position-and-the-failure-is-silent-2026-08-17)
- [§NOISESRC — a taper is a de-click on a one-shot and a tremolo on a loop (2026-08-17)](#noisesrc-a-taper-is-a-de-click-on-a-one-shot-and-a-tremolo-on-a-loop-2026-08-17)
- [§AKAIVELFILT — a zone that fires and makes no sound (2026-08-17)](#akaivelfilt-a-zone-that-fires-and-makes-no-sound-2026-08-17)
- [§AKAIVELZONE — overlapping velocity zones LAYER on the S3000XL (2026-08-17)](#akaivelzone-overlapping-velocity-zones-layer-on-the-s3000xl-2026-08-17)
- [§AKAISTEREO — the sampler does NOT pair `-L`/`-R` (2026-08-17, measured)](#akaistereo-the-sampler-does-not-pair--l-r-2026-08-17-measured)
- [§AKAIRESAVE — the `??` regions, answered on an S3000XL (2026-08-17)](#akairesave-the-regions-answered-on-an-s3000xl-2026-08-17)
- [§K2DSP — the K2000 F1 slot is a DSP block, not a filter (2026-08-16, measured)](#k2dsp-the-k2000-f1-slot-is-a-dsp-block-not-a-filter-2026-08-16-measured)
- [§AKAIVFR — S3000XL velocity→filter is keygroup byte 151 (2026-08-16, measured)](#akaivfr-s3000xl-velocityfilter-is-keygroup-byte-151-2026-08-16-measured)
- [§E4BRATE2 — the rate-pitch formula confirmed on machine-authored material (2026-08-16)](#e4brate2-the-rate-pitch-formula-confirmed-on-machine-authored-material-2026-08-16)
- [§AKAINAME — one sample, one name, and the cached directory that hid it (2026-08-16)](#akainame-one-sample-one-name-and-the-cached-directory-that-hid-it-2026-08-16)
- [§KRZF3 — a filter in slot F3, and the two ways of being wrong about it (2026-08-17)](#krzf3-a-filter-in-slot-f3-and-the-two-ways-of-being-wrong-about-it-2026-08-17)
- [§RIGHTNUMBER — when the measurement survives and the explanation does not (2026-08-18)](#rightnumber-when-the-measurement-survives-and-the-explanation-does-not-2026-08-18)
- [§WRONGLAYER — a positive control on the transport is not one on the measurement (2026-08-18)](#wronglayer-a-positive-control-on-the-transport-is-not-one-on-the-measurement-2026-08-18)
- [§AKAIAUX-DECODED — the drum-input and multi files, read off the disk (2026-08-18)](#akaiaux-decoded-the-drum-input-and-multi-files-read-off-the-disk-2026-08-18)
- [§PROSEGUARD — a caveat in a docstring does not defend against a printed number (2026-08-18)](#proseguard-a-caveat-in-a-docstring-does-not-defend-against-a-printed-number-2026-08-18)
- [§AKAIDELETE — the delete-type enum, and why it must never be swept (2026-08-18)](#akaidelete-the-delete-type-enum-and-why-it-must-never-be-swept-2026-08-18)
- [§E4BFTYPE — `vpar[58]` is a GROUPED code, not a sequential index (2026-08-18)](#e4bftype-vpar58-is-a-grouped-code-not-a-sequential-index-2026-08-18)
- [§POWEROFF — every symptom fitted, and nobody enumerated the cheapest cause (2026-08-18)](#poweroff-every-symptom-fitted-and-nobody-enumerated-the-cheapest-cause-2026-08-18)
- [§FECLAMP — a real difference, measured with a ruler that had hit its ceiling (2026-08-18)](#feclamp-a-real-difference-measured-with-a-ruler-that-had-hit-its-ceiling-2026-08-18)
- [§GRANULARITY — one false member says nothing about its neighbours (2026-08-18)](#granularity-one-false-member-says-nothing-about-its-neighbours-2026-08-18)
- [§AKAILOOPRATE — RETRACTED: the loop does not play 11% fast; I measured a stacked sine (2026-08-18)](#akailooprate-retracted-the-loop-does-not-play-11-fast-i-measured-a-stacked-sine-2026-08-18)
- [§AKAIPRGCLAMP — WITHDRAWN: the clamp is not silent and the fix I proposed was already rejected (2026-08-18)](#akaiprgclamp-withdrawn-the-clamp-is-not-silent-and-the-fix-i-proposed-was-already-rejected-2026-08-18)
- [§AKAIIDTHIEF — a sidecar file stole the SCSI id and the image was never served (2026-08-18, FIXED — HARDWARE-CONFIRMED)](#akaiidthief-a-sidecar-file-stole-the-scsi-id-and-the-image-was-never-served-2026-08-18-fixed-hardware-confirmed)
- [§AKAINAME12 — two bench samples truncated to the same 12-character name (2026-08-18, FIXED)](#akainame12-two-bench-samples-truncated-to-the-same-12-character-name-2026-08-18-fixed)
- [§AKAILOADTYPE — LOAD type 1 loads no samples, contradicting our SAVE-type note (2026-08-18, OPEN)](#akailoadtype-load-type-1-loads-no-samples-contradicting-our-save-type-note-2026-08-18-open)
- [§AKAIFILTQTY — two AKAI filter laws that disagree, for a principled reason (2026-08-18, OPEN — DEFINITIONAL)](#akaifiltqty-two-akai-filter-laws-that-disagree-for-a-principled-reason-2026-08-18-open-definitional)
- [§AKAILOOPCROSS — the pool-base conclusion is REFUTED BY THE CORPUS; loop_start is the suspect (2026-08-18, REOPENED)](#akailoopcross-the-pool-base-conclusion-is-refuted-by-the-corpus-loop_start-is-the-suspect-2026-08-18-reopened)
- [§AKAIRATEQUANT — sample-header byte 0x01 selects the playback rate; SSRATE is descriptive only (2026-08-18, CONFIRMED — FIXED)](#akairatequant-sample-header-byte-0x01-selects-the-playback-rate-ssrate-is-descriptive-only-2026-08-18-confirmed-fixed)
- [§AKAISDATA — we write 0 into the sample-data address; it is a real deviation with no effect (2026-08-18, CLOSED — COSMETIC)](#akaisdata-we-write-0-into-the-sample-data-address-it-is-a-real-deviation-with-no-effect-2026-08-18-closed-cosmetic)
- [§AKAIAUXDEFAULT — `.X` and `.T` do not need decoding to be written correctly (2026-08-18)](#akaiauxdefault-x-and-t-do-not-need-decoding-to-be-written-correctly-2026-08-18)
- [§AKAIUNKNOWNDUP — the undecodable-record diagnostic multiplied across reads (2026-08-18, FIXED)](#akaiunknowndup-the-undecodable-record-diagnostic-multiplied-across-reads-2026-08-18-fixed)
- [§ASKFORDEFINITIONS — the two corrections that came from questions, not measurements (2026-08-18)](#askfordefinitions-the-two-corrections-that-came-from-questions-not-measurements-2026-08-18)
- [§AKAILOOPSEM — our loop convention is the reverse of the factory one (2026-08-18, ESTABLISHED; NOT the cause of the silence)](#akailoopsem-our-loop-convention-is-the-reverse-of-the-factory-one-2026-08-18-established-not-the-cause-of-the-silence)
- [§AKAILOOPAT — LOOPAT1 is the loop END; we wrote the loop START into it (2026-08-18, FIXED)](#akailoopat-loopat1-is-the-loop-end-we-wrote-the-loop-start-into-it-2026-08-18-fixed)
- [§LOOKITUP — why two sessions ground for six hours on something that was written down (2026-08-18)](#lookitup-why-two-sessions-ground-for-six-hours-on-something-that-was-written-down-2026-08-18)
- [§AKAIRELTEST — the release test, and the artefact that was my own disc (2026-08-18, PASSED)](#akaireltest-the-release-test-and-the-artefact-that-was-my-own-disc-2026-08-18-passed)
- [§PRESETORDER — preset order and program numbers survive the trip](#presetorder-preset-order-and-program-numbers-survive-the-trip)
- [§AKAIATTACK — the attack we throw away, and the first law anyone has offered for it](#akaiattack-the-attack-we-throw-away-and-the-first-law-anyone-has-offered-for-it)
- [§AKAIRATEREAD — the reader takes SSRATE, the writer trusts byte 0x01](#akairateread-the-reader-takes-ssrate-the-writer-trusts-byte-0x01)
- [§AKAIENV2 — the filter envelope: measured for eight days, unwired for two stale reasons](#akaienv2-the-filter-envelope-measured-for-eight-days-unwired-for-two-stale-reasons)
- [§IDENTIFIERS — six wrong objects, zero wrong sums (2026-08-19/20)](#identifiers-six-wrong-objects-zero-wrong-sums-2026-08-1920)
- [§AKAIFILTREAD — the reader reads the filter and drops it, and the law it would need may be stale](#akaifiltread-the-reader-reads-the-filter-and-drops-it-and-the-law-it-would-need-may-be-stale)
- [§AKAIPOOLBASE — the silent first program, and a fix that was only ever described](#akaipoolbase-the-silent-first-program-and-a-fix-that-was-only-ever-described)
- [§SILENCEGATE — silence does not clip](#silencegate-silence-does-not-clip)
<!-- INDEX:END -->

## §SIBCHECK — three sibling findings checked against our own corpora (2026-08-15)

VinSamLib offered three KRZ corpus measurements and s3ked shipped a Windows
encoding guard. All four were checked here rather than filed. **One was a real
hole; three were not, and knowing which is which is the point of writing this
down.**

### 1. Text I/O riding the locale codec — REAL, and my first check was wrong

s3ked's CI had never been green on Windows: text files written as cp1252 and
read back as UTF-8, on em dashes, which both projects write everywhere. I
checked this repo two nights earlier with a single-line `grep` and reported it
clean.

Their fix records that **their own grep missed two call sites because the call
spanned lines**. Re-run over the AST, ours found one: `writers/atomic.py`,
whose `mode` is a parameter no static check can resolve. Every caller passed
binary, but `atomic_write(p, 'w')` reads as obviously fine and would have
written locale-encoded bytes. Fixed by construction — text without an explicit
encoding is UTF-8 there now — and a standing AST guard treats an unresolvable
mode as the dangerous case rather than the safe one.

The lesson is about the first check, not the bug: **a single-line regex over
source cannot see a multi-line call, so its clean result was worth less than it
looked.** This project already had a rule against inferring code properties
from source text, and the grep predated applying it here.

### 2. Nested / gapped stereo planes — real phenomenon, we are clean on it

They found 45 of 802 multi-header samples with a gap between channels, and one
bank where two stereo samples are NESTED inside one another. A reader taking a
sample's length as the distance to the next sample's start gets 10 950 words
where the sample spans 176 794. `krz_parser._pcm_extents` does exactly that,
using the next start as a hard ceiling.

Measured over **201 real soundsets**: 594 multi-header samples, 65 with a gap
between planes — and where it matters, 529 stereo samples with two usable
planes show **16 unequal (3.0 %), the worst a one-word difference**. No
truncation. Our ceiling handles the gapped case correctly on this material and
the pathological nested bank is not in this corpus.

Not "fixed", because there is nothing here to fix and their safe rule
(`max(sampleEnd) - min(sampleStart) + 1` as a floor that may extend but never
shorten) is a change we cannot validate against a case we do not have. Recorded
so the next person who meets a 16x-short stereo sample knows where to look.

### 3. Duplicate object ids in the wild — not in our corpus

They have 3 banks holding two objects of the same type and id, where a
dict-keyed parse silently keeps the last. **Zero across our 201 soundsets.**
Their fix (keep the FIRST, the one every reference was written against, and
record the shadowed one) is the right behaviour if we ever meet it.

### The pattern worth keeping

Four findings from projects reading the same formats: one landed, three did
not, and none could have been sorted by argument. The corpus decided each in
minutes. **An offered finding is a hypothesis about your code, not a report
about it** — and the one that landed was the one where I had already convinced
myself we were clean.

### A quantity can be right where it is computed and wrong where it is read

`build_akai_hd_image` returned `len(plan)` as the number of partitions used.
That was correct at the top of the function and false by the bottom: the plan
is padded with empty partitions to fill the disk's slots on the way through, so
by the return statement the same expression meant the SLOT count. The fix is a
variable captured before the padding, not a cleverer expression at the end.

VinSamLib named the shape after hitting several of their own this week: *a
quantity that was correct where it was computed and wrong where it was read,
with nothing in between to say the meaning had changed.* It is the mutable
cousin of the wrong-population errors above — same symptom, a plausible number
nobody can see is wrong, arrived at without a crash.

Worth noticing that the same function had ALREADY exported this confusion to a
caller: `'partitions'` meant slots, VinSamLib's layout preview read it as used,
and they spent a debugging session on a fill-rule disagreement that did not
exist. The ambiguity was visible from outside before it was visible from
inside.

### A corpus figure must carry its population, in the output

Six wrong numbers crossed these three projects in two days and every one was a
truncated or mis-chosen population rather than bad arithmetic:

| | |
|---|---|
| a 40-file loader cap | made an E4B click rate 0.5 % instead of 2.8 % |
| an unsorted glob cut at 150 banks | a corpus figure over a sixth of it |
| `[:30]` volumes per disc | a 2x disagreement between two readers |
| a filter identical to its own population | returned 0/0/0 tautologically |
| `hasattr(P, 'SAMPLE_TYPES')` — the constant is `_SAMPLE_TYPES` | silently answered from one sampler generation |
| six split banks, described as the corpus | "exactly one" where the corpus says 1499 |

The last two are ours. **None produced a crash; every one produced a plausible
number.** And VinSamLib's diagnosis is the part to keep: these are convenience
caps that keep an exploratory loop fast, so *the line that makes the loop usable
is the line that makes the result wrong*, and nothing in the output says which
mode it ran in.

So: **print the denominator beside the figure** — "1843 volumes, 21 images,
uncapped" — and write the population into any figure recorded here. A number
that cannot be read without knowing what it is over should not be quoted, and
a scan that prints its own population makes a truncated run visible in its own
output rather than in a later disagreement with somebody else.


## §NAMEBYTE — name fields decoded as ASCII (E4B/EMU3 DONE; EIII/SF2/MPC60 open)

**Status: fixed 2026-08-08 for E4B (`57a909b`) and the EMU3/ISO 9660 sites
(`149e2b9`). Three formats still to decide, each on its own evidence.**

### What was wrong

`parsers/e4b_parser.py::_decode_name` used `raw.decode('ascii',
errors='replace')`. A real E4XT writes bytes above 0x7E into the 16-byte name
field — glyphs off its own front panel, from a character ROM that is neither
ASCII nor ISO-8859-1 — and `errors='replace'` turned each into U+FFFD before
the name reached the `Bank` model. Unrecoverable, and carried into every bank
written from that parse.

### The measurement

Walk every local `.E4B` chunk by chunk with the parser's own `_walk_chunks`
and inspect `body[2:18]` of each `E3S1`/`E4P1`:

```python
for tag, body in _walk_chunks(open(path, 'rb').read()):
    if tag in (b'E3S1', b'E4P1') and len(body) >= 18:
        hi = [b for b in body[2:18] if b > 0x7e]
```

461 files: exactly one byte value, **0xA5, 19 times**, all in one third-party
bank, separating an articulation label from the note name (`8LDesp\xa5G1`) —
authoring, not corruption. VinSamLib measured the same byte independently:
413 times plus 0x7F across 131 hardware-authored banks. Low local prevalence
is expected; nearly all 461 files are our own output.

### The fix, and three details worth keeping

`latin-1` on both sides, exact inverses. It preserves the **byte**, and makes
no claim about the **glyph** — latin-1 renders 0xA5 as a yen sign and EOS's
table is not ISO-8859-1. Displaying the right character needs that table,
which we do not have; storing the right byte does not, and only the byte
decides whether a written bank is correct. **Do not guess at a mapping.**

1. **`errors=` is dead code on a latin-1 decode** — latin-1 maps all 256 byte
   values and cannot fail. Keep it on the *encode*, where a codepoint above
   0xFF from a UTF-8 source format genuinely cannot fit.
2. **`rstrip(' ')`, not `rstrip()`.** Bare `rstrip()` strips every
   whitespace-class codepoint, which under latin-1 includes 0xA0 (NBSP) and
   0x85 (NEL) — real name bytes the old ASCII decode turned into U+FFFD and
   therefore kept. It would have fixed 0xA5 while opening a hole one byte
   away. The pad character is the space `_name16()` writes, and nothing else.
3. **Fix both sides in one commit.** Parser-only leaves the byte alive in the
   model and kills it at write time; VinSamLib hit the mirror image of this on
   their side, where a latin-1 reader against an ASCII writer put the same
   sample under two different names in one file.

### The same fault one level up (both fixed in `149e2b9`)

- EMU3 directory entries were **written** `encode('ascii','replace')` at four
  sites while being **read** `decode('latin-1')` at two, a few lines away. A
  bank name carrying the byte died on the media even with the parser fixed.
- `_iso9660_unique_names` filtered with `str.isalnum()`, which is **True** for
  latin-1 letters (`é`, `ü`, `µ`). Those reached the caller's bare
  `iso_name.encode('ascii')` and raised `UnicodeEncodeError` mid-build — a
  crash, not a corruption. Confirmed: stem `Café` → `CAF\xc9001.E4B;1` →
  raises. ISO 9660 Level 1 identifiers are spec'd to `A-Z 0-9 _`, so
  restricting to ASCII is the format's rule, not a workaround.

### Still open — decide per format, do not blanket-replace

| format | state | what would settle it |
|--------|-------|----------------------|
| ~~EIII~~ | **CLOSED 2026-08-08: leave it ASCII** | measured after all — see below |
| SF2 (`sf2_parser`, 6 sites) | ASCII on read | SF2 is spec'd ASCII — this one may well be correct as it stands |
| MPC60 (`mpc60_parser`, 3 sites) | ASCII on read | the MPC60's own character set; no corpus measured |

**EIII: measured and closed, against the prior.** VinSamLib had the corpus we
did not and walked **1 019** EIII/ESI banks out of its EMU3 images — 30 935
sample names and 19 423 preset names. Six banks hold any byte above 0x7E, and
none of them is plausible text: the high bytes are interleaved with control
characters throughout (`'\x83\x02l\xfe\x05\x04\xe8\x13…'`), which is what
deleted-bank content sitting in free space looks like, not what a person types
on a front panel.

So the E-MU-lineage prior was wrong, and it was a strong one — the E4B sample
struct *is* the Emulator III's, and 0xA5 appears 413 times in a comparable E4B
library. Six banks in a thousand, none of them text, is not evidence of a
charset. `eiii_writer` stays ASCII rather than pushing an unverified byte at
hardware. **This is the argument for the per-format rule:** a blanket replace
would have shipped a change here that a thousand real banks say nothing asks
for.

**KRZ: RETRACTED 2026-08-09 — the byte is real and `krz_writer` now encodes
latin-1.** This section twice recorded the opposite, and the reasoning failed
the same way both times.

The first answer scanned **238 loose `.KRZ` files** and found zero. VinSamLib
reported zero over 472 loose files, and this section called that "two disjoint
corpora agreeing". VinSamLib then withdrew its number — it had never opened a
disc image — and reported **0x7F 4 036 times**. Re-running here over loose
files plus one subdirectory of floppy images still gave zero, so the reply
said the finding did not reproduce.

It reproduces. The third scan covered what the first two had missed — the
**K2000 CD-ROM images under `~/Dokumente/SYNTHS/K2000R`**, which is where
almost all commercial K2000 content on this machine lives:

| corpus | banks | objects | high bytes |
|--------|-------|---------|------------|
| loose `.KRZ` | 833 | 27 149 | **0** |
| floppy images | 1 747 | 43 548 | 14 |
| **K2000 CD-ROM images** | **2 047** | **60 574** | **4 083** |
| total | 4 627 | 131 271 | 4 097 |

**4 073 of those are 0x7F, and every one is authored**: a sample-object name
with 0x7F as the separator before a stereo pair's channel marker —
`'VOI:Attack Voi\x7fL'` / `\x7fR` — filling exactly 16 characters, so it is
inside the field and not the §KRZNAME16 overrun. The remaining 12 bytes are
scattered singles in names that are mostly unprintable: misparse, as before.

**But the inference everyone drew from it was wrong, including mine.** 0x7F
is *inside* ASCII (0–127), so `krz_writer`'s `encode('ascii')` preserved it
exactly and always had. Nothing was ever lost. VinSamLib reported "it loses
0x7F on the way out"; the first regression test written here for it passed
with the fix reverted, which is what exposed the error. The frequency
measurement was right; the conclusion drawn from it was not.

`krz_writer` now encodes latin-1 anyway, for the narrower reason that it makes
the pair exact inverses — no byte `krz_parser` produces can be altered on the
way back out. What that actually changes is bytes **≥ 0x80**, of which the
corpus holds 12, all in otherwise-unprintable names.

**Two method lessons, and the entry is worth keeping for them.**

*One.* Three scans returned zero and all three were looking where the byte is
not. A zero is
evidence of absence only if the corpus is known to cover the places the thing
would live, and none of the three checked that. VinSamLib caught it first for
its own corpus and said so; the same sentence applied here and was not
applied. **Before reporting a zero, enumerate where the material actually
lives and show the scan reached it.**

*Two.* A correct measurement does not make the conclusion drawn from it
correct. 0x7F really does appear 4 073 times, and "therefore ASCII drops it"
still did not follow. The check that caught it was mechanical: **write the
regression test, then revert the fix and require the test to fail.** It
passed, so the fix was not doing the thing the commit message was about to
claim.

**EIII: measured and closed, against the prior.** VinSamLib had the corpus we
did not and walked **1 019** EIII/ESI banks out of its EMU3 images — 30 935
sample names and 19 423 preset names. Six banks hold any byte above 0x7E, and
none of them is plausible text: the high bytes are interleaved with control
characters throughout (`'\x83\x02l\xfe\x05\x04\xe8\x13…'`), which is what
deleted-bank content sitting in free space looks like, not what a person types
on a front panel.

So the E-MU-lineage prior was wrong, and it was a strong one — the E4B sample
struct *is* the Emulator III's, and 0xA5 appears 413 times in a comparable E4B
library. Six banks in a thousand, none of them text, is not evidence of a
charset. `eiii_writer` stays ASCII rather than pushing an unverified byte at
hardware. **This is the argument for the per-format rule:** a blanket replace
would have shipped a change here that a thousand real banks say nothing asks
for.

**Deliberately not changed — and the evidence for it was rebuilt twice
(2026-08-09).** `krz_writer.py:209` encodes ASCII while `krz_parser.py`
decodes latin-1, the same shape of asymmetry as the E4B name byte. The
question is whether any real KRZ name uses one.

The first answer here scanned **238 loose `.KRZ` files** and found zero.
VinSamLib reported zero over 472 loose files of its own, and this section
recorded that as "two disjoint corpora agreeing". **Both scans were the same
blind spot**: nearly all real K2000 content lives inside floppy and disk
images, and neither had opened one. VinSamLib withdrew its number and
re-scanned including images, reporting 0x7F 4 036 times.

Re-run properly here — loose files **plus** every bank inside
`~/disk-image/*/*.img`, walking each `PRAM` header: **216 banks, 6 451
objects, zero authored high bytes.** The 0x7F it reports does not appear at
all locally.

What the image scan *did* find was four bytes (0x9D, 0xDB) that turned out not
to be name content: see §KRZNAME16 below. Both projects had counted the same
artefact.

So the conclusion stands but the reasoning does not transfer: **no local
evidence a KRZ name carries a byte above 0x7E**, and `krz_writer` stays ASCII
until someone produces a raw block dump showing one *inside* a 16-character
name rather than past it.

### Regression tests (local, `tests/` is untracked)

`tests/test_e4b_parser.py`: byte survives the decode; 0xA0/0x85 are not
stripped; full write→re-parse round trip, asserting the file holds 0xA5 and no
`?`. `tests/test_iso_builder_props.py`: the EMU3 entry holds the byte; every
ISO 9660 identifier is pure ASCII and a full build with a non-ASCII bank name
and volume label completes. Each was confirmed to fail with its own half of
the fix reverted.

---

## §KRZNAME16 — a full-length KRZ name picked up the bytes after it (2026-08-09)

**Status: fixed.** `parsers/krz_parser.py` capped at `MAX_NAME`.

A KRZ object name is at most 16 characters and NUL-terminated. A name that
fills the field **exactly** has no room for its terminator, so
`split(b'\x00')[0]` returned everything up to `ofs` — which is padded and
rounded up — and the reader appended whatever followed.

Found in two real banks: `ofs = 20`, name field `b'General MIDI kit\x9d\xdb'`.
Sixteen real characters, then two bytes that belong to the block, not the name.

Why it matters beyond tidiness: those two bytes were **counted as evidence of
a character set**, here and independently in VinSamLib's corpus (it reported
0x9D and 0xDB six times each — the same artefact at a different corpus size).
A reader bug produced data that looked like a format finding, and the finding
would have justified changing the writer.

The general lesson, which is the one worth keeping: **a byte that appears only
at the very end of a maximum-length field is a parsing artefact until proven
otherwise.** Check the field's own length limit before concluding anything
about its contents.

Regression test in `tests/test_krz_roundtrip.py`, confirmed to fail with the
cap reverted (it returns `'General MIDI kit\x9dÛ'`).

---

## §ISODIR — EMU3 CD image drops banks past the 16th (how to fix)

**Status: guard ready to apply; multi-block wants one E4XT confirmation.**

### Problem

`writers/iso_builder.py::build_iso` writes one dir-content block for a list
of any length. `_dircon_block` slices `files[:EMU3_ENTRIES_PER_BLOCK]` and
`_root_block("Default Folder  ", _DIRCON_START)` puts a single block number
in the folder's 7-slot block list. Cluster allocation, FAT and file data are
built from the full list, so the excess banks are on the disc but
unreferenced. See `TODO.md` for the reproduction.

### Stage 1 — stop the silent loss (software only, no hardware)

Mirror what `build_hda` already does. In `build_iso`, right after
`file_infos` is built:

```python
if len(e4b_files) > EMU3_ENTRIES_PER_BLOCK:
    dropped = file_infos[EMU3_ENTRIES_PER_BLOCK:]
    print(f"  [ERROR] EMU3 CD directory holds at most "
          f"{EMU3_ENTRIES_PER_BLOCK} banks; {len(file_infos)} provided. "
          f"Dropping {len(dropped)}:")
    for fi in dropped:
        print(f"            {Path(fi['path']).name}")
    print("          Split across multiple images, or use --hda "
          "(multi-block, no 16-bank limit).")
    file_infos = file_infos[:EMU3_ENTRIES_PER_BLOCK]
```

Truncate `file_infos` **before** `allocs`/`n_clusters`/`total_blocks` are
computed, otherwise the image keeps the dead clusters it has now.

### Stage 2 — 17…112 banks on one disc

The machinery exists in this same module; `build_emu_hdd` (line ~745) already
does it:

```python
dircon_bytes = b''
for i in range(0, len(banks), EMU3_ENTRIES_PER_BLOCK):
    dircon_bytes += _dircon_block(banks[i:i + EMU3_ENTRIES_PER_BLOCK])
```

with the folder entry carrying the block list. For the CD path:

```python
n_dircon = max(1, (len(file_infos) + EMU3_ENTRIES_PER_BLOCK - 1)
                  // EMU3_ENTRIES_PER_BLOCK)          # cap at EMU3_BLOCKS_PER_DIR (7)
blocks   = [_DIRCON_START + i for i in range(n_dircon)]
root     = _root_block("Default Folder  ", blocks)     # already takes a list
dircon   = b''.join(_dircon_block(file_infos[i:i + EMU3_ENTRIES_PER_BLOCK])
                    for i in range(0, len(file_infos), EMU3_ENTRIES_PER_BLOCK))
dircon  += b'\x00' * BSIZE * (_DIRCON_BLOCKS - n_dircon)
pad1[0]  = _DIRCON_START + n_dircon                    # next-free pointer, not +1
```

`_folder_entry` already accepts a list and pads with `0xFFFF`, so no change
there. Two details that are easy to get wrong:

- **`pad1[0]` must become `_DIRCON_START + n_dircon`**, not the hardcoded
  `+ 1` — it is the next-free dir-content block pointer.
- **The `slot` byte** (entry offset 17) is the 2-digit bank id. `_dircon_block`
  falls back to the *within-block* index when `slot` is absent, which is
  correct only for a single block. Past 16 banks the caller must set
  `fi['slot']` to the running index across all blocks, as `build_emu_hdd`
  does, or the discs get four banks each numbered 00–15.

Beyond 112 banks the folder is full; `build_emu_hdd`'s multi-folder path
(`EMU3_BANKS_PER_FOLDER = 100`) is the model, but the EOS UI's 2-digit bank
slots make >100 per folder questionable anyway.

### Confirmation needed before Stage 2 ships

Our multi-block dir content is hardware-confirmed on the **HDD** profile
only. Build one CD image with ~20 banks, load it on the E4XT via ZuluSCSI and
check that banks 17–20 appear in the browser and load. If the CD reader only
honours the first block-list slot, Stage 1 is the permanent answer and the
16-bank cap is a real format limit for CD volumes.

### Cross-reference

ConvertWithMoss `3dbd378f` (2026-08-03) makes exactly this change to the
writer it took from our RE — 16 → 112 files, same 7-slot folder block list,
entry numbers running across blocks. Independent agreement on the mechanism,
but they state the images are round-tripped through their own detector and
**not** hardware-verified, so it is not a substitute for the E4XT check.

That commit also adds an **EIII/EIIIX/ESI-native CD layout**, which we do not
have and currently do not need — our `--format eiii --iso` targets the E4XT's
EIII compatibility loader, so EOS geometry is right for it. Recorded in case
we ever want discs a real EIII can mount: `fat_blocks=7, root_blocks=6,
dircon_blocks=192` (vs EOS 5/4/125); file entries carry **no** form type at
offset 28 where EOS has `E4B0`; the superblock stores the medium size as u32
at `0x2A` instead of the EOS flag byte `0x2D = 0x08`; the padding block after
the superblock is filled with `0x80` from offset 4. Their source is two
volumes of one EIIIX library, unverified on hardware.

**Not a finding, do not re-derive:** the per-entry form-type difference
(`\x00E4B0` for E4B bodies, all-zero for EIII bodies) is the same thing
`_bank_props` has done since 2026-07-28, where we established it from five
commercial discs *and* hardware-tested it on the E4XT's browser. We were
there first and with better evidence.

---

## §E4BRATE — EOS4 sample-rate field (how to fix the resample pitch bug)

**Symptom.** E4B samples stored below 44.1 kHz play sharp by `src/dst` (27500 →
+8.18 st). See `TODO.md`. The E4XT honors low rates (SrCnv keeps pitch), so EOS4
reads the playback rate from a field other than our E3S1 `[54-57]` (which came from
emu3bm/EOS3). We currently write `[58-59]` playback_rate and `parameters[6]`
(`[70-93]`) as 0.

**SOLVED FROM THE CORPUS, 2026-08-12 — no hardware needed.** The blocker below
was a collapsed variable: it constrained *access to an E4XT*, while the question
is *what value the field holds at a given rate* — and 681 real E4B files written
by real E4XTs answer that directly.

Reading `[58-59]` against `[54-57]` across every sample in the local corpus, on
the 103 rates below 44.1 kHz where the value has not wrapped:

```
    [58-59] = round(768 * log2(rate / 44066)) mod 65536      max residual 1.32
```

768 units per octave is **64 per semitone** — a 1/64-semitone pitch offset, and
the reference is 44066 Hz, i.e. 44.1 kHz to within 0.08 %. So the field is not a
rate at all: it is the playback pitch relative to 44.1 kHz.

**Which is exactly the bug.** We write `[58-59] = 0`, and zero means "44.1 kHz",
so the E4XT plays every sample as though it were 44.1 kHz. A sample stored at
27500 Hz therefore plays sharp by `12·log2(44100/27500)` = **8.18 semitones** —
and TODO.md recorded the observed symptom, months ago, as *"27500 → +8.18 st"*.

That match is the evidence, not the fit. The law was fitted to corpus field
values and predicts an independently observed hardware symptom it was never
fitted to — the §AGREEMENT standard for what earns trust.

**The fix** is to write the field instead of zeroing it. Still worth one
hardware confirmation, but it is now a one-line change to verify rather than the
multi-step RE procedure below.

**Superseded RE procedure (hardware artifact — Jan).**
1. Load `K2_AUTOSAMP` on the E4XT (from the ISO / ZuluSCSI). Note a **non-resampled**
   sample's pitch — e.g. **S020** (a plain 44.1 kHz sample; plays A-something).
2. Sample Edit key → select S020 → **Tools 1 (F2)** → **SrCnv (F4)** → enter a
   **distinctive low rate (e.g. 22050)** → set filter (Smooth) → **OK**.
   Confirm S020 **still plays the same pitch** (proves EOS keeps pitch on rate change).
3. Save the bank back (new bank is fine). Hand the `.E4B` to Claude.

**Diff.** `python3 tests/re_banks/diff_sample_rate_field.py <hw_bank>.E4B`
— within the resaved (all-EOS4-authored) bank it diffs the SrCnv'd S020 (22050) vs
an untouched neighbour (44100); the differing offset(s) holding `22050`
(`0x5622`) is EOS4's real rate field. (SrCnv to 22050 also ~halves S020's PCM, so
it is easy to identify even if `[54-57]` no longer carries the rate.)

**Fix.** In `writers/e4b_writer` `_sample_header`, write `sample.sample_rate` into
the field the diff reveals (keep `[54-57]` too, for EOS3 tools / our own parser).
Then `resample_vintage` / `resample_to_rate` E4B output plays in tune at the reduced
rate — no upsampling, RAM saving retained. Re-verify on HW, then update
`docs/E4B_FORMAT.md` sample-header table with the corrected field.

**RE PROGRESS 2026-07-24 — fields identified, encoding half-decoded.** Diffed the
E4XT-resaved `B.010-K2_AUTOSAMP.E4B` (pulled from `HD0.img`, a **FAT32** ZuluSCSI
image — `mcopy -i HD0.img ::/B.010-K2_AUTOSAMP.E4B out`) where **S020 = idx 20
`P1 PL 19_A4` was SrCnv'd 44100 → 22050 and plays IN TUNE**. Against an untouched
44.1 kHz neighbour (idx 19), the pitch-carrying fields — both **written 0 by our
`_sample_header`** — are:
  * `[54-57]` sample_rate — EOS4 *does* store the real rate (22050) but does NOT
    pitch from it (our 27500 sets it too and plays sharp); informational/display.
  * **`[58-59]`** (our "playback_rate"=0): EOS4 = `0xFD02` = **−766 signed** for the
    2:1 drop. ≈ **−768 = −1 octave in 1/64-semitone units** (0.26 % off — see below).
  * **`[18-21]`** (our "header"=0): EOS4 = `0xEB8B839C` (s32 −343178340) — a 32-bit
    companion, encoding not yet solved from one point (not a clean cents/ratio/float).
Both are non-zero ONLY on the converted sample (the 44.1 kHz neighbour has both 0),
so together they are the sub-44.1-kHz pitch correction; leaving them 0 makes EOS4
play at native rate → sharp by `native/rate`. NOTE EOS4 also grew every sample's
PCM by +8/+12 bytes on resave (loop/format padding, not pitch).

**SOLVED 2026-07-24 — fix implemented, pending HW confirm.** Jan SrCnv'd S018-S023
to 11025/27500/22050/32000/33075/48000 (bank `B.011-K2_AUTOSAMP.E4B`). Fit
(`tests/re_banks/fit_e4b_rate_fields.py`):
  * **`[58-59]` (s16 LE) = round(768 · log2(rate / 44100))** — 768 = 64·12, i.e.
    **1/64-semitone**. Fits all 6 points within ±2 (an exact fit uses base 44037,
    but 44100 is the true f58=0 native — an untouched 45 kHz sample keeps f58=0 and
    plays in tune, and 44100→0 leaves plain samples byte-unchanged). 48000 → +95
    (positive above native). Deterministic (idx20=22050 gave −766 in BOTH B010/B011).
  * **`[18-21]` — NOT pitch.** Same 22050 conversion gave `0xEB8B839C` in B010 but
    `0x3B97FC3E` in B011 → non-deterministic per-sample token (checksum/id EOS sets
    on modify). Left 0 (all our 44.1 kHz samples work with 0).
Fix in `writers/e4b_writer._sample_header` (write f58 at offset 58 when rate≠44100).
**DONE — HW-CONFIRMED on the E4XT 2026-07-24**: E2/EX/E2SC/EXSC play in tune; plain
byte-unchanged. Commit-ready. (Also update `docs/E4B_FORMAT.md` sample-header table:
`[58-59]` = pitch offset in 1/64-semitone, not "playback_rate"; `[18-21]` = opaque
per-sample token, not "header".)

---

## §MPCFILT — MPC filter dropped at max cutoff (how to fix)

`parsers/pgm_parser.py` ~285:
```python
# CURRENT — drops the filter (type=0) when fully open, losing resonance:
if f1_type in _PGM_FILTER_XPM and f1_freq < 100:
    voice.filter_type      = _PGM_FILTER_XPM[f1_type]
    voice.filter_cutoff    = min(1.0, f1_freq / 99.0)
    voice.filter_resonance = min(1.0, f1_res / 100.0)
else:
    voice.filter_type   = 0
    voice.filter_cutoff = 1.0
```
Fix: create the filter whenever `f1_type` is a real type, regardless of `f1_freq`:
```python
if f1_type in _PGM_FILTER_XPM:
    voice.filter_type      = _PGM_FILTER_XPM[f1_type]
    voice.filter_cutoff    = min(1.0, f1_freq / 100.0)   # /100 (was /99)
    voice.filter_resonance = min(1.0, f1_res / 100.0)
else:
    voice.filter_type   = 0
    voice.filter_cutoff = 1.0
```
Then grep `parsers/xpm_parser.py` for a `Cutoff >= 1.0 → skip filter` pattern and
apply the same. Verify against a pad that has resonance (or a filter env) at max
cutoff — it should now keep its bite. Cross-ref ConvertWithMoss `c7b9641`.

## §MODELPARAMS — carry choke group / one-shot / key-track / round-robin (design)

Add to `models/common.py`:
- `ZoneMapping.exclusive_group: int = 0` (0 = none) — **choke/mute group**. Parse:
  MPC (`<MuteGroup>` / choke), SFZ (`group=`/`off_by=`), SF2 (exclusiveClass). Write:
  E4B/K2000 group field IF the hardware supports it — RE needed (E4XT "Group" and
  K2000 keymap have a mute-group concept; confirm the byte before wiring the writer).
- `SampleData.one_shot: bool = False` (first-class; today only `pgm_parser` infers it
  as a full-length release). Maps to E4B/KRZ "play to end / ignore note-off" where
  expressible.
- `VoiceLayer.amp_keytrack: float = 0.0` (mirror the existing `filter_keytrack`).
- Round-robin / random: a per-group play-logic enum; low priority (E4XT has no direct
  round-robin, would need a mod-cord/random-source hack).
Start with **exclusive_group** (drum kits benefit most). Cross-ref ConvertWithMoss
`6fcc346` (#212) for the source-side mappings per format.

## §MPC39 — MPC Standalone 3.9.0 gzipped-JSON `.xpm` parser (how to fix)

**What it is.** 3.9.0 hardware saves each `.xpm` as **gzip** (`1f 8b 08 …`).
`gzip.decompress(raw)` yields a UTF-8 text header then a JSON body:

```
ACVS
3.9.0.31
SerialisableProgramData
json
Linux
{ "data": { "version": 6, "name": "K2-01", "type": 1, "programPads": { … } } }
```

The header is line-delimited; the JSON starts at the first `{`.

**Parser plan (`parsers/mpc39_parser.py`, register `.xpm` → dispatch by magic):**
1. In `xpm_parser` (or the registry), sniff the first 3 bytes: if `1f 8b 08`,
   `raw = gzip.decompress(raw)`. If the result begins with `ACVS`, hand off to the
   new 3.9.0 JSON parser; else fall through to the existing XML path. (Keeps one
   `.xpm` entry in `PARSERS` handling both old XML and new gzipped-JSON.)
2. `body = raw[raw.index(b'{'):]`; `doc = json.loads(body)`.
3. Walk `doc["data"]` → build `Bank`/`Preset`/`VoiceLayer`/`ZoneMapping`. Map the
   keygroup/pad list (`programPads` and/or an instruments/keygroups array — RE
   needed) to zones: sample ref, lo/hi key, lo/hi vel, root, tune, volume, pan,
   plus filter/env/LFO where present (mirror the XML `xpm_parser` field mapping so
   the two share the model-fill helpers). Samples resolve to the sidecar
   `<name>_[ProgramData]/*.wav` via the existing `load_wav`.

**RE still needed:** catalogue the JSON keys under `data` and confirm the
key/velocity-zone and modulation layout. Dump: `python3 -c "import gzip,sys;
sys.stdout.buffer.write(gzip.decompress(open('K2-01.xpm','rb').read()))"`.
Reference programs: `/media/lentferj/3433-6435/SamplerExports/K2-0{1,2,3}.xpm`.

**Until then:** `convert.py <name>_[ProgramData]/ --from-samples` converts the
samples + auto-mapped zones (no program synth params).

---

## §AUTOLOOP — Auto sustain-loop (IMPLEMENTED, branch `autoloop`, 2026-07-25)

**Goal.** Set a clean forward sustain loop in the steady region so held notes
sustain. Autosampler follow-on to `--trim-tail` (trim the dead tail dropping the
whole-take loop, then place a *real* sustain loop). `processors/auto_loop.py`
(`auto_loop_bank` / `_auto_loop_sample` / `_find_loop`), pure Python, reuses the
single-cycle DSP; wired after `--trim-tail` in `convert.py`.

**As-built algorithm** (differs from the original sketch below in ways that matter):

1. **Steady region** — `_steady_region`: a LONG-window (80 ms) smoothed RMS envelope
   finds the attack-end and release-onset while IGNORING tremolo/beating dips. (The
   original short-window "stop at first dip" cut modulated material to nothing.)
2. **Period** — `single_cycle._detect_period` + `_refine_period`, root-primed, with a
   **harmonic-lock fallback**: detected pitch > 2 octaves off the root ⇒ use the
   root-note period, drop confidence (fixed a low-bass 0.49→0.15 case).
3. **Seamless splice — click-free by CONSTRUCTION (the key insight).** Endpoints snap
   to rising zero-crossings. The equal-power crossfade rewrites the last `xf` loop
   samples `[E-xf+1..E]`, morphing from the loop-end content into the samples that
   PRECEDE loop-start `[S-xf..S-1]`, with `t=i/(xf-1)` so `fo=0` at the last sample →
   `out[E] = orig[S-1]` EXACTLY. The wrap `E→S` therefore reproduces the natural
   waveform run `orig[S-1]→orig[S]`. Measured residual click ≈ **−240 dB** on all
   material, synth sawtooth edges included. ⚠ Ending the crossfade at `orig[S]`
   (off-by-one) DUPLICATES a sample = a real glitch — avoid. ⚠ Do NOT QC the seam
   with jump/avg-step (it false-flags a synth's legitimate per-period edge as 70×);
   QC with `|out[E]−orig[S−1]|` in dB below peak.
4. **Adaptive length + BEAT ALIGNMENT** (refined 2026-07-25 after audition feedback —
   loops were too short/static, and a detuned-synth loop pulsed "ding-ding-ding").
   Splice quality is scored by `_match_cost` = normalised SSD of the two crossfade
   windows (pre-end `[E-w+1..E]` vs pre-start `[S-w..S-1]`).  Length:
   - *modulated* tone (vibrato / tremolo / detuned-oscillator BEATING; `_modulation`
     returns the FUNDAMENTAL modulation period M) → candidate lengths are integer
     multiples of M, so the envelope matches at the seam.  A fraction-of-a-beat error
     is the audible ding — the loop-end zero-crossing search weights toward the exact
     beat multiple (`score = cost + 0.5·|E−Et|/M`).  ⚠ the click-free crossfade holds
     for ANY loop-end, but landing E on an exact non-zero-crossing beat multiple wrecks
     the crossfade-window match (waveform-phase mismatch → high cost → wrongly skipped);
     use a zero-crossing NEAR the beat, not exactly on it.
   - *steady* tone → integer-fundamental-period sweep.
   Keep the **LONGEST transparent** loop (was steady→shortest — wrong: a short loop on
   evolving material sounds static even when seamless).  Defaults `min_ms=150`,
   `max_ms=2500` (raised from 80/600 for natural, breathing loops).  A few loop-START
   candidates guard against a bad start.  A length/cost penalty (`_LEN_COST_PENALTY_MS
   =2000`) trades length against splice quality so a marginally-longer loop cannot win
   by degrading the seam.  Fast-beating/drifty analog synths are the one case where a
   long loop over-captures drift → manual override with `--auto-loop MS` or
   `--auto-loop-max-ms 800` (no metric auto-distinguishes drifty-wants-medium from
   clean-wants-long; see [[project_autoloop]]).  Skip default `min_quality=0.45`.
5. `loop_type=FORWARD`, `loop_start=S`, `loop_end=E` (inclusive). Round-trips through
   both E4B and KRZ writers (verified). Crossfade applied per channel (mono+stereo).
   **`crossfade=False` (`--auto-loop-no-crossfade`)** leaves the PCM pristine — loop
   points only, at the zero-crossing/beat-aligned positions — so the loop stays freely
   fine-tunable in the E4XT/K2000 loop editor (a baked crossfade locks it in place).

**Knobs:** `--auto-loop [auto|MS]`, `--auto-loop-xfade MS` (grows automatically for
poor matches), `--auto-loop-max-ms`, `--auto-loop-min-quality COST` (skip hard
material), `--auto-loop-force`, `--auto-loop-trim` (drop audio past loop_end),
`--auto-loop-dump-dir`. `[weak match — audition]` advisory above cost 0.44 (the raw cost badly over-predicts badness once the crossfade is applied — HW audition rated loops up to 0.437 "very good").

**Results (objective sweep, mellotron/VPO/prophet/K2).** Solo/pure timbres (flute,
cello, clean choir, analog synth) → excellent (match <0.07, natural 300-600 ms
loops). Dense ensemble / noisy analog → inherently hard (0.2-0.55): longer crossfade
+ flag/skip. Audition renders (loop×6 flat) in `/home/lentferj/temp/autoloop_work/aud/`.

**Still to do:** local audition (Audacity/VLC) then **HW audition** on E4XT + K2000
before merge to main; possibly pitch-based vibrato detection (amp-envelope misses
pure vibrato) and quality-threshold tuning. Prior art: LoopAuditioneer, PyMusicLooper.

<details><summary>Original design sketch (superseded)</summary>

1. `region = single_cycle._sustain_start(sig)`. 2. `_detect_period`/`_refine_period`.
3. loop length = integer periods (a few hundred ms). 4. cross-correlate end points,
snap to zero-crossings. 5. optional crossfade. 6. `loop_type=FORWARD`. The as-built
version replaced (3)+(4) with the measured length sweep and made the crossfade the
click-free primary mechanism rather than an optional touch-up.
</details>

---

## §CR — Code-review findings (2026-06-10), fix recipes

Items confirmed by the high-effort review (`TODO.md` "Code-review findings").
Each is a self-contained code fix. **Add/extend a `test_pipeline.py` case for the
P0 ones** (they're currently uncovered).

**DONE 2026-06-10:** CR-2, CR-4, CR-5, CR-8, CR-9, CR-11, CR-12 — fixed &
pipeline-verified (see each entry below). **CR-11b — FALSE POSITIVE**, see below.
**DONE 2026-06-11:** CR-3 (TAL writer); CR-1 + CR-10 + CR-11c (KRZ writer); CR-6
(zone-reducer); CR-7/7b/7c (name collisions) — see below. **All P0 items done;
CR-13/14/15/16/17 + CR-18 cord-builder done 2026-06-11; only CR-18
(`Envelope` dataclass — recommend skip / EXS24 walker-unify — needs `.exs`
files) remains.**

**CR-1 KRZ velocity layers / stacking — DONE 2026-06-11.** Restructured to **one
keymap + one program layer per voice** (was one merged keymap per preset with N
identical layers stacked over it → ~+9.5 dB / phasing, and later voices
overwriting earlier per key). `_build_keymap_entries` now takes a single voice;
`_write_program_object` emits one layer per voice pointing at that voice's keymap,
with the LYRSEGTAG **key AND velocity range** (`lyr[3..6]`) set from the voice's
zone span. Since the parsers model velocity layers as separate voices, those now
split correctly on the K2000. Keymap ids use a running counter (typed-hash makes
numeric overlap with sample/program ids fine). Verified: 3-voice preset (soft
vel 0–63 / loud 64–127 / key-split) → 3 layers, distinct keymaps, correct vel
windows. **Remaining limitation:** a *single* voice carrying internal vel-split
zones still collapses to one keymap velocity level (the 8-level on-disk keymap
layout isn't reverse-engineered) — fine in practice since parsers split velocity
into separate voices. Hardware load check is a Jan gate (as with all KRZ work).

**CR-10 KRZ loop end — DONE 2026-06-11.** The K2000 loop is [sampleLoopStart,
sampleEnd], so `_write_sample_object` now writes the loop **end** as the
Soundfilehead `sampleEnd` field when looped (`abs_loop_end`), the PCM end only
for one-shots. Verified: looped sample (loop 200–600 of 1000) writes sampleEnd
600, not 999.

**CR-11c KRZ ping-pong — DONE 2026-06-11.** `write_krz` now bakes ALTERNATING
(ping-pong) loops into PCM as forward loops via `bake_alternating_loop`, exactly
like `write_e4b` (was emitting plain forward → click every cycle). Verified: a
500-word ping-pong sample baked to 799 words.

**CR-2 + CR-12 SFZ cutoff — DONE 2026-06-10.** Added `hz_to_e4b_cutoff(hz)` +
`E4B_CUTOFF_MIN/MAX_HZ` to `models/common.py` (the 57 Hz / 20 kHz exponential
convention). `sfz_parser` now does `voice.filter_cutoff = hz_to_e4b_cutoff(hz)`
(was the broken `int(min(127, cutoff_hz/200))`); `exs24_parser._exs_cutoff_to_e4b`
calls the shared helper. Sanity: 1 kHz → pos 0.489 (was fully open).

**CR-3 TAL writer schema — DONE 2026-06-11.** `write_talsmpl` rewritten to emit
the real TAL **v11** schema (the old invented `<preset><layer><param><mapping>`
loaded nowhere). Jan supplied a fresh `Startup.talsmpl`; its 234 `<program>`
defaults + the `<multisample>` defaults are reproduced as *format data* in
`parsers/tal_template.py` (no TAL preset bundled), with generators for the
`voicetunings`/`modmatrix`/`tuningtable` child blocks. The writer clones a full
default program (`new_tal_root()`) and overrides only what mpc2emu models:
`programname`, program-global `filtercutoff/resonance/mode` + `adsramp{a,d,s,r}`
(from V1), one enabled sample layer (a–d) per voice, and per-zone
`url/root/low/high key`, `velocitystart/end`, `loop*`, `pingpongloop`,
`volume/pan/transpose/detune` on each `<multisample>`. Samples are **external WAV
refs** (`includewaveinpreset=0`, `url` + `urlRelativeToPresetDirectory` =
`samples/NAME.wav`). New inverse converters: `_secs_to_tal_adsr`,
`_xpm_filtermode_to_tal`. The **parser** now also reads the multisample-level
`volume/pan/velocity/transpose` (where TAL stores per-sample values), so
write→parse is **lossless** — verified: 2 voices, keys/root/vel 10-100/vol −3 dB/
pan −0.5/transpose +7/fine +10 c all round-trip exactly. Pipeline green.

**Layer bin-packing fix (2026-06-11):** the writer first mapped one voice → one
TAL layer (max 4), so any preset with >4 voices silently lost samples — e.g. a
14-pad drum kit (our parsers model each pad as a separate voice).  Now it
bin-packs ALL zones into ≤4 layers by key×velocity overlap (`_tal_zones_overlap`):
non-overlapping zones (drum kits, multisampled keyboards, velocity layers) share
ONE layer as many `<multisample>`s; only truly overlapping zones (simultaneous
stacking) take a new layer.  Verified: `AMBIENCE_SET__1.PGM` (14 pads) →
1 layer / 14 multisamples, each mapped to its key; synthetic per-zone round-trip
still lossless.

**TAL-Sampler load test — PASSED 2026-06-11** (Jan, real MPC2000XL drum kit
`AMBIENCE_SET__1.PGM` → external-WAV `.talsmpl`).  External refs resolve, samples
load and play.  The test (and a TAL-saved reference of the same kit) uncovered
**five** writer bugs the parse→write round-trip could not, all now fixed:
1. **Missing `<programs>` wrapper** — TAL (JUCE) walks `tal→programs→program` by
   name; `<tal><program>` loaded silently as empty.  `new_tal_root` now emits it.
2. **Layer bin-packing** — see the dedicated note above (>4 voices dropped).
3. **`track="0"` for one-shots** — single-key/drum zones must set `track="0"`
   EXPLICITLY; TAL's default for an *absent* `track` is `"1"` (keytrack on →
   heavy transpose at the pad's own key).  Ranged zones keep `track="1"`.
4. **`stereoinverse="0"`** — same absent→`"1"` default; written explicitly.
5. **Per-sample filter + CRLF** — the multisample template had inherited the
   Startup oscillator's `filtercutoff=0`/`filterhighpass=1` (would darken
   samples) → set neutral (`1.0`/`0.0`); file written with CRLF + blank line to
   match TAL.  Output verified field-for-field against the TAL-saved reference
   (only cosmetic float-format / inactive-grain diffs remain).
Key lesson: TAL keeps the **full 42-attr** multisample set and re-defaults any
*omitted* attribute, so the writer must set the meaningful ones explicitly.

**Remaining (minor, Jan, when convenient):** the absolute TAL **volume** and
**cutoff** mappings are reasonable approximations, not measured.  Embedded-PCM
(`includewaveinpreset=1`) is the fallback if external refs ever don't resolve —
not needed here.

**CR-4 SFZ loop override — DONE 2026-06-10.** `sfz_parser` now sets
`loop_type`/`loop_start`/`loop_end` only when the opcode is actually in `merged`
(`if 'loop_mode' in merged: …`); absent opcodes keep what `load_wav` read from the
WAV smpl chunk (SFZ default = "from the sample").

**CR-5 E4B amp-env decode — DONE 2026-06-10.** `_parse_voice` now mirrors
`_build_voice` PZT[0:12]: `env_attack=_fenv_rate_inv(pzt[0])`, decay pzt[4],
release pzt[8], `env_sustain=_fenv_level_inv(pzt[5])`. Verified round-trip
(A0.05/D1.2/S0.4/R0.8 → 0.049/1.205/0.40/0.802). (The `_fenv_*` math was later
de-duplicated into `models/common.py` — see CR-13 below.)

**CR-6 zone-reducer — DONE 2026-06-11.** `_thin_and_redistribute` now checks
whether the kept items form a non-overlapping chain on the reduction axis
(`orig_lo[i] > orig_hi[i-1]`). Only then does it widen survivors into the gaps;
overlapping/parallel items (drum-kit full-range voices, vel-split zones thinned
on the key axis) keep their original ranges, and a `new_lo <= new_hi` guard means
it never emits an inverted (silent) range. Verified: a 4-voice full-range drum
kit reduced 50 % → 2 voices, **zero inverted ranges** (was producing 64>63); a
real 8-zone key chain still redistributes to a clean ordered 0–127 cover.

**CR-19 `thin_velocity_layers()` entangled key/velocity presets — DONE
2026-07-27.** Found via VinSamLib (downstream project, see TODO history):
`velocity_layer_pct=30` on a preset with one voice per (key-zone × velocity-
layer) cell shrank total voice count by ~30% but left the distinct velocity-
BAND count unchanged, because the `len(preset.voices) > 1` branch thinned
individual voices by index-spacing without first grouping them by their own
velocity band — when several voices share a band (one per key zone), even-
spacing almost always leaves a survivor in every band. Fixed by grouping
`preset.voices` into `(voice_lo, voice_hi)` bands first (mirroring
`_thin_velocity_bands_in_voice`'s zone-grouping, one level up), thinning at
the band-group level via `_thin_and_redistribute`, then applying each
surviving band's (possibly widened) range to every voice in it. Verified
against the real repro file
(`.../Kirk.Hunter.Virtuoso.Series.Strings1.E4/KH Violins/B.003-2_8Violins128MB.e4b`,
preset the 78-voice string preset): 5 → 4 distinct bands at `keep_pct=70` (was 5 → 5).
Also spot-checked the CR-6 code paths still hold through the new grouping: a
synthetic overlapping-band case (all `hi_vel=127`, like the real file) kept
original ranges via the CR-6 guard; a synthetic contiguous 3-band/2-voices-
per-band case widened survivors correctly (3 → 2 bands, gap split at the
midpoint, both voices in each surviving band updated).

**CR-20 `thin_key_zones()` no-op for one-zone-per-voice presets — DONE
2026-07-27.** Found via VinSamLib (same downstream project as CR-19, same
session): CR-19's mirror image on the KEY axis. `reduce_key_zones_pct=30`/`60`
on the same real repro preset (the 78-voice string preset, 78 voices, each carrying
**exactly one zone** — the E4B parser's native shape for a densely
multisampled instrument) printed `removed 0 key zone(s)` at any percentage.
Root cause: `thin_key_zones(voice, keep_pct)` only thins zones *within one
voice* — correct for the XPM-keygroup representation it was written for (one
voice packs many zones across several velocity bands), but a no-op when
`len(voice.zones) == 1` for every voice, because the real key-zone variation
lives *across* voices instead — the exact same architectural gap CR-19 fixed
on the velocity axis, just transposed. Fixed by adding
`_thin_key_zones_across_voices()` (groups `preset.voices` by velocity band
first, then thins ACROSS the voices within each band by key position via
`_thin_and_redistribute`, keyed on each voice's own key range instead of
velocity range — mirrors CR-19's voice-grouping-by-band exactly, just on the
other axis) and a new dispatcher `thin_key_zones_for_preset()` that picks
between the existing within-voice `thin_key_zones()` (when any voice carries
`>1` zone — the XPM case) and the new across-voice path (when every voice
carries `<=1` zone — the E4B case). `reduce_bank()`'s `key_zone_pct` branch
now calls the dispatcher once per preset instead of `thin_key_zones()` per
voice. Verified: old code confirmed to reproduce `removed 0` on the real
file; new code removes 23/46 voices at `reduce_key_zones_pct=30`/`60`
respectively (matches the requested percentage exactly, mirroring CR-19's
verification). The pre-existing multi-zone-per-voice (XPM) case is
unaffected — same code path, same behavior, regression-tested directly.

**CR-21 `thin_velocity_layers()` picks a tiny outlier band as the sole
survivor at aggressive reduction — DONE 2026-07-28.** Found via real E4XT
hardware confirmation of VinSamLib's own test matrix (row 11,
`reduce_velocity_layers_pct=75.0` on the same the 78-voice string preset preset
CR-19/20 already used): 78 voices collapsed to **1 surviving voice, covering
only MIDI keys 63-66** — everywhere else on the keyboard silent on real
hardware, confirmed not sample corruption (the one surviving sample played
fine, intact PCM).

**Root cause:** the real preset's 5 velocity bands are wildly uneven in
size — `1 / 36 / 1 / 20 / 20` voices respectively (by `lo_vel` 0/1/9/50/86).
`_thin_and_redistribute`'s `keep_count == 1` special case picked
`ordered[n // 2]` — the **middle band by sorted-index position**, with zero
regard for how many voices (how much keyboard coverage) each band actually
represents. Sorted by `lo_vel`, the middle index (2 of 5) lands exactly on
the `vel[9-127]` band — a single stray voice covering 4 keys, almost
certainly a one-off fix-up sample in the original commercial patch, not a
real velocity layer. **Row 10 (`keep_pct=60`, keep 3 of 5 bands) wasn't
visibly broken but was equally miscalculated** — the evenly-spaced index
selection at `keep_count=3` picks indices `{0, 2, 4}`, which happens to
include *both* tiny 1-voice bands plus one legitimate 20-voice band
(1+1+20=22, matching the reported "78→22") — it only looked reasonable by
coincidence.

**Fix:** `_thin_and_redistribute` gained an optional `get_weight` parameter
(default `None` = the exact original uniform-index behavior, byte-for-byte,
so `thin_key_zones`/`_thin_velocity_bands_in_voice`/CR-19/CR-20's existing
call sites are untouched). When a weight function is given,
`keep_count == 1` picks the *heaviest* item (ties broken by proximity to the
middle index, preserving the old behavior when bands are evenly sized), and
`keep_count > 1` selects by evenly-spaced **cumulative weight** position
instead of raw index (falling back to greedily filling any collision from
one item's weight dominating the total). `thin_velocity_layers` now passes
`get_weight=len` for the multi-voice/band case, weighting each band by its
voice count.

**Verified** against the real repro file: 75% reduction now keeps the
36-voice band (80 distinct keys, range 48-127) instead of the 1-voice/4-key
outlier; 40% reduction now keeps 41 voices spanning the full 0-127 range
(up from 22, and with genuinely complete coverage this time, not by luck).
New regression tests `test_thin_velocity_layers_uneven_band_sizes_dont_pick_
outlier` (synthetic, exact 1/36/1/20/20 shape) and
`test_thin_velocity_layers_real_e4b_75pct_keyboard_coverage` (the real file,
the exact reported percentage) both confirmed to fail against the pre-fix
code and pass with it; the full existing suite (`tests/test_zone_reducer.py`)
still passes unchanged, confirming the default/uniform-weight path is
unaffected.

**Hardware-confirmed 2026-07-28.** Rebuilt the exact repro case (the real
file, `velocity_layer_pct=75.0`, the fixed code) as a standalone bank
(`11_reduce_velocity_75_FIXED.e4b` → `CD1-VL75FIX.iso`) and loaded it on
the real E4XT: plays across the full keyboard (C2-D8 in MPC-One octave
numbering), not just the previous 4-key silent-everywhere-else sliver.
Heavy aliasing at the pitch-shifted extremes is expected and correct for a
75% velocity-layer reduction (fewer samples stretched further), not a
regression. Closed.

Also worth noting: the VinSamLib hardware-test images already staged on
the SD card earlier this session (rows 08-12, as part of the consolidated
batch) were extracted from VinSamLib's own pre-built `.hda` files, built
with the pre-fix mpc2emu — they still reflect the old buggy thinning and
would need rebuilding downstream (in VinSamLib) to pick up this fix.

**CR-7 / 7b / 7c sample-name collisions — DONE 2026-06-11.**
- **CR-7** `bank_splitter.TargetBank.add_preset`: dedup now keys on
  `(name, len(data), hash(data))`. A genuine duplicate (same name+PCM) is shared;
  a same-name/different-PCM sample is renamed (16-char-safe suffix) and the
  preset's zones repointed. Verified: two `Kick`s with different PCM → `Kick` +
  `Kick1`, zone repointed, true dup still shared.
- **CR-7b** `sf2_parser._get_sample`: distinct SF2 samples whose names truncate
  to the same 16 chars now get a unique suffix (`used_names` set), so zones no
  longer resolve to the wrong sample/root.
- **CR-7c** `write_talsmpl`: preset filenames are de-duplicated per call
  (`Dup.talsmpl`, `Dup_1.talsmpl`) so same-named presets don't overwrite.

**CR-8 SF2 sampleModes — DONE 2026-06-10.** `sf2_parser` maps `sampleModes`
`1→FORWARD`, `3→FORWARD_REL`, `0/2→NO_LOOP`; never `ALTERNATING` (SF2 has no
ping-pong, so `write_e4b` no longer bakes reversed PCM into the sustain).

**CR-9 ISO cluster sizing — DONE 2026-06-10.** `_choose_cse(file_sizes)` now sums
the **per-file** ceilings `sum(ceil(size/cluster))` (was `ceil(total/cluster)`,
under-counting by up to one cluster/file) and raises a clear error if even the
largest cse overflows. Repro: 1000×600 KB → old est 1172 (would IndexError) vs
2000 real at cse=4 → now steps up to cse=5 (1000).

**CR-10 KRZ loop_end.** Include the loop-end word in the Soundfilehead position
struct (the `abs_loop_end` already computed), or truncate written PCM to loop_end
if the K2000 format implies loop=end. Verify against KurzFiler's layout.

**CR-11 resampler loop clamp — DONE 2026-06-10.** After resampling,
`n=len(pcm_out)//bpf`; `loop_start`/`loop_end` clamped to `[0, n]` (the
down-then-up `_decimate` pair can floor the length below source).

**CR-11b — FALSE POSITIVE (2026-06-10).** The recipe assumed MPC2000 sample
indices are 0-based with `names[0]` the first real sample. A real file
(`AMBIENCE_SET__1.PGM`) shows `names[0]=''` and **50 of 64 pads carry sn==0** as
the *unassigned* sentinel; real samples are indices 1–13. The existing
`0 < sn < len(names)` guard is correct — accepting `sn==0` would emit 50 phantom
zones onto an empty sample. **No change made.**

**CR-13 dedup — DONE 2026-06-11.** The EOS envelope rate↔time + level↔byte math
(`ENV_RATE_A/K`, `env_seconds_to_rate`/`env_rate_to_seconds`/`env_level_to_byte`/
`env_byte_to_level`) and the signed mod-cord codec (`cord_amount_to_byte`/
`cord_byte_to_amount`) now live once in `models/common.py`; `e4b_writer`/
`e4b_parser` keep thin `_fenv_*` aliases (so `tests` importing `_fenv_seconds`
still work) and call the shared cord codec (was inlined 5×).

**CR-14 EXS24 env — DONE 2026-06-11.** Deleted the quadratic `_env_byte_to_seconds`;
both amp and filter envelopes now use the linear CWM `_exs_env_to_seconds` (the
adopted EXS reference). *(Behaviour note: EXS24 amp-envelope times now follow the
linear curve — intentional.)*

**CR-15 dead code — DONE 2026-06-11.** Removed `_NT_MOD_TMPL` alias, the unused
local `import math` in `gig_parser` (no `math.` use) and `exs24_parser`, and the
unused `level_note` in the resampler verbose path; moved `find_multivoice.py` to
`tests/`.

**CR-17 parser registry — DONE 2026-06-11.** New `parsers/registry.py` holds the
single `ext → callable(path, wav_dir, **kw)` table + `INPUT_EXTS`; `convert.py`
and `info_cmd.py` both import it (was two drifted copies). Verified: convert
(XPM→E4B) and `--info` both run through it.

**CR-18 cord-builder — DONE 2026-06-11.** Added `_set_cord(mod, slot, src, dst,
amount, flag)` in `e4b_writer`, replacing the `slot*4 + n` offset arithmetic for
the free-slot LFO cords.

**CR-18 `Envelope` dataclass + EXS unify — DONE 2026-06-12.**
- **Envelope dataclass.** `VoiceLayer` stores `amp_env`/`filter_env` as
  `Envelope(attack, decay, sustain, release)`; `models.common` adds
  `_amp_env()`/`_filter_env()` `default_factory`s and eight property accessors
  (`env_attack`…/`filter_env_attack`…) that delegate to the dataclasses, so all
  existing `v.env_attack` reads/writes and `VoiceLayer(amp_env=Envelope(...))`
  constructor calls keep working.  Migrated the constructor call-sites that
  passed flat env kwargs (`e4b_parser`, `talsmpl_parser`, the three
  `tests/re_banks/gen_*` generators).  Validated: zero feature diffs XPM/SFZ/
  SF2/EXS → E4B (N=5 and N=14 seeds).
- **EXS24 "walker unify" → re-scoped.** The literal task (merge classic+v11,
  validate on real classic files) is **unsatisfiable for this corpus**: of 1717
  local `.exs` files, **0 are classic** — all are v1.1 — so the classic path is
  untestable dead code here.  Investigating the asymmetry instead exposed and
  fixed three concrete v1.1 bugs (all in `parsers/exs24_parser.py`):
  1. **`0x40000101` flag-variant rejection.** Some Logic Pro X exports OR
     `0x40000000` into the file magic and into every chunk type (magic reads
     `0x40000101`; zones `0x41000101`, samples `0x43000101`, …).  Layout is
     byte-for-byte normal v1.1.  Added `_V11_TYPE_FLAG = 0x40000000`, masked at
     the magic dispatch and at every `chunk_type` comparison in
     `_parse_exs_v11`.  14 corpus files were affected (Free-SP / SP-1200 /
     Analog-Tape From-Mars packs).
  2. **Long-common-prefix multisample collapse.** `_safe_name(stem)` truncates
     to 16 chars by default; using it as the sample-cache key meant every
     `DX100 Classic Bass-<note>-…` sample hashed to `DX100 Classic Ba`, so 36
     zones shared one SampleData.  Fixed by keying the cache on the full stem
     (`maxlen=255`).  Safe because the E4B zone entry references samples by
     **index** (`zone-entry[10:12]`), not by name, and bank_splitter/`_name16`
     apply the 16-char limit + uniqueness at write time.
  3. **`.aif`→`.wav`-twin resolution.** `load_wav` reads WAV only.  The From-
     Mars packs point the `.exs` at `.aif` but ship parallel `.wav` copies in a
     sibling `WAV/` folder.  Added a stem→path fallback index (preferring
     `.wav`) so an `.aif` reference whose exact name isn't a loadable WAV falls
     back to its same-stem WAV twin.
  Result: all 14 formerly-rejected files now parse full multisamples and
  round-trip **ERROR→PASS** through E4B.  Remaining gap (separate TODO): packs
  that ship **AIFF only** (no WAV twin) still won't load — needs real AIFF
  decode support in `load_wav` (Python's `aifc` is removed in 3.13, so a small
  manual AIFF reader would be required).

**CR-16 perf #2/#3 — DONE 2026-06-11.**
- **#2 `write_e4b` memory:** `_build_sample_body` split into `_build_sample_header`
  (header only); the writer computes all offsets/sizes from lengths, then streams
  `header + sample.data` per sample straight to the open file — no `join`/concat,
  so peak RAM drops from ~5× the bank's PCM to ~1×. **Byte-identical** verified
  (regenerated a ~1 MB multi-sample bank, `cmp` clean) + pipeline round-trip.
- **#3 resampler:** `_pcm_to_float`/`_float_to_pcm` use bulk `array('h')` (LE,
  byteswap on big-endian hosts) instead of per-frame `struct`. Byte-identical;
  **measured ~2× decode / ~1.3× encode** — the per-element float divide/clip is
  the floor without numpy (the resampler stays stdlib), so the earlier "~30-50×"
  estimate was wrong.
- **#1 gig decode — DONE 2026-06-11.** 24-bit→16-bit is `val>>8`, which equals
  the signed-16 of a frame's top two bytes, so it's a bulk `bytearray` slice
  (`out[0::2]=raw[1::3]; out[1::2]=raw[2::3]`; **~200× faster**, byte-identical).
  8-bit→16-bit `(b-128)*256` is a sign-flip into the high byte → bulk
  `raw.translate(_FLIP_SIGN8)`.  Both replace per-sample `struct.pack_into`
  loops; verified byte-identical against the old arithmetic on random data.
- **#4 ISO/HDA — DONE 2026-06-11.** `iso_builder` (both EMU3 + ISO-9660 paths)
  and `hda_builder` now copy each embedded E4B in 1 MB chunks and write the
  cluster/sector pad separately, instead of `src.read()` + `data + b'\x00'*pad`
  (which held the whole file twice).  Verified: regenerated ISO byte-identical
  (`cmp`); HDA round-trip embeds the E4B verbatim.
- *(Considered `audioop` for #1/#3 — byte-identical but deprecated and removed in
  Python 3.13, so avoided.)*

---

## Index

| TODO item | Resolution type | Status |
|---|---|---|
| Code-review findings CR-1..18 | Code (no RE) | **CR-1–17 DONE + CR-18 cord-builder** (11b false-positive); only CR-18 `Envelope` dataclass (recommend skip) + EXS-unify (needs `.exs` files) left — §CR |
| Amp envelope decay byte | **RESOLVED 2026-06-08** | PZT[4]=Decay1 rate confirmed (AMPENV_SETME + AMP_DECAY_CAL banks) |
| `_fenv_rate()` calibration | **RESOLVED 2026-06-08** | Log fit from 6 E4XT decay measurements; writer + parser updated |
| Ping-pong loop bit | **RESOLVED 2026-06-08** | EOS has no ping-pong mode; bounce baked into PCM (loop_renderer.py) |
| Swept/Phaser/Flanger/Vocal/Morph filter bytes | **RESOLVED 2026-06-08** | All vpar[58] bytes confirmed from B.005-FILTERTYPES.E4B (§4) |
| Zone entry `fine_tune` field | Hardware RE | Procedure written — test banks at `tests/re_banks/` |
| Zone entry `volume` field | Hardware RE | Same test bank as fine_tune |
| EXS24 v1.1 zone fields misassigned | **APPLIED 2026-06-08** | Fixed + verified on real files |
| EXS24 GROUP_V11 stereo doubling | **APPLIED 2026-06-08** | Fixed; ks+11 maps via sorted-distinct, verified corpus-wide |
| EXS24 multi-velocity layers | Deferred | Waiting for corpus with vel-layered EXS24 |
| SF2 MIDI program numbers | **APPLIED 2026-06-08** | byte[31]=program_number, verified |
| TAL filtermode encoding | **FULLY RESOLVED 2026-06-08** | 13 modes, N=UI position; 6 corners confirmed by Jan |
| E4B vpar[42] = Chorus Amount | **RESOLVED 2026-06-08** | 0-100% → 0-127; model+writer+parser wired (§13) |
| SMP velocity grouping | **APPLIED 2026-06-08** | One NT voice per vel range, verified |
| Filter envelope reproduction | **RESOLVED 2026-06-09** | Routing fixed (FilterEnv→Cutoff cord, amount=`filter_env_amount`) + hardware-confirmed; source mapping XPM/SFZ/SF2/GIG/EXS24 ✅; shares amp rate-curve (§17) |
| XPM envelope values = 0–1, not seconds | **RESOLVED 2026-06-09** | MPC One: `seconds≈0.00079·e^(9.78·v)`; `_xpm_env_to_seconds()` wired; filter env confirmed same curve (§18) |
| Mod routing: Key→Filter, Velocity→Filter | **DONE 2026-06-09** | cords 06/04, mapped from GIG/SFZ/XPM/EXS24 (§15) |
| LFO modulation routing | **DONE 2026-06-10** (§15); GIG deferred | LFO1+LFO2 bytes + LFO→Pitch/Filter/Q cords RE'd & round-trip; input mapping done for XPM/SFZ/SF2; only GIG LFO left (needs test file) |
| XPM PGM binary format | Deferred | Needs format docs |
| HDA directory >16 entries | **APPLIED 2026-06-08 (guard)** | Warns + truncates to 16, verified |
| EXS24 PPC big-endian | **WON'T FIX 2026-06-08** | Unreachable dead code removed; undetectable by magic |

---

## 1. Amp envelope: decay byte — RESOLVED (2026-06-08)

The amp envelope is the 6-stage rate/level block at `PZT[0:12]` (mirror of the
filter envelope at `PZT[14:26]`), confirmed on hardware:

```
PZT offset : interpretation
  [0/1]   Amp Attack1  rate / level
  [2/3]   Amp Attack2  rate / level   (rise to +100%)
  [4/5]   Amp Decay1   rate / level   ← decay rate = PZT[4] (CONFIRMED)
  [6/7]   Amp Decay2   rate / level   (hold at sustain)
  [8/9]   Amp Release1 rate / level   (fall to silence)
  [10/11] Amp Release2 rate / level
  [12]    0x03  envelope mode/pointer (constant)
  [13]    0x00
```

### Evidence

- **`AMPENV_SETME.E4B`** (baseline) — set known values on the E4XT Amp Envelope
  page and saved; the page writes exactly these 12 bytes
  (`00 00 00 7f 00 7e 00 7f 7f 00 00 00`).
- **`AMP_DECAY_CAL.E4B`** — 6 voices that differ in nothing but the decay
  setting; the **only** byte that moves is `PZT[4]` (`08 10 18 20 30 40`),
  proving PZT[4] is Amp Decay1 rate. The same sweep gave the rate→time
  calibration (see §2).

### Applied

`_build_voice()` in `e4b_writer.py` writes the full `PZT[0:12]` amp envelope
(attack → full, decay → sustain held through Decay2, release → silence), using
the calibrated `_fenv_rate()`. `_parse_voice()` in `e4b_parser.py` reads it back
via the matching `_fenv_rate_inv()`. The rate→time fit itself is §2.

The decay *level* sits at `PZT[5]` (= sustain), `PZT[6/7]` hold it through
Decay2, matching the manual's "set the '2' levels = the '1' levels, '2' rates
= 0" standard-ADSR mapping.

---

## 2. `_fenv_rate()` calibration — RESOLVED (2026-06-08)

### What was wrong

The old formula `round(80.0 / (t + 0.01))` was copied from the filter envelope
and never independently calibrated. It also had the **direction backwards**: it
treated rate 0 as the slowest (infinite) time, when hardware shows rate 0 is the
*fastest* (instant) and the byte increases monotonically with time.

### Measurements

6 Decay-1 decay-to-silence times measured on the E4XT (`AMP_DECAY_CAL.E4B`):

| rate | time    | rate | time    |
|-----:|--------:|-----:|--------:|
|    8 | 0.034 s |   32 | 0.198 s |
|   16 | 0.098 s |   48 | 0.454 s |
|   24 | 0.169 s |   64 | 1.225 s |

Log-linear fit (R²=0.96): **`time_s = 0.0310 · e^(0.0581 · rate)`**, i.e.
rate 0 ≈ 0.031 s (instant) and rate 127 ≈ 47 s (slowest).

**Re-validated 2026-06-09** by re-recording `AMP_DECAY_CAL` and analysing it with
`tests/re_banks/analyze_envelope_recording.py` (two passes, identical to the ms).
The automated τ(1/e) progression is smoother than the original hand-timed table
(which had a rate 24→32 kink); the fitted exponent (~0.058 at rates 32–64,
slightly steeper at the fast end) confirms the K=0.0581 curve. No change made —
the original calibration stands.

### Applied

- `writers/e4b_writer.py`: constants `_ENV_RATE_A = 0.0310`,
  `_ENV_RATE_K = 0.0581`; `_fenv_rate(seconds)` →
  `round((ln(s) − ln(A)) / K)` clamped to 0..127; inverse
  `_fenv_seconds(rate) = A · e^(K · rate)`.
- `parsers/e4b_parser.py`: `_fenv_rate_inv()` rewritten as the exact mirror of
  `_fenv_seconds()` (same constants), replacing the old `80.0/rate − 0.01`.
  Verified equal to the writer across rates 0..127 and round-trip stable.

### Byte position

`AMP_DECAY_CAL.E4B` doubles as the byte-position proof: across its 6 voices the
**only** byte that changes is `PZT[4]` (`08 10 18 20 30 40` = the swept rates),
so PZT[4] is unambiguously Amp Decay1 rate. The full 12-byte amp-envelope layout
was separately confirmed from the `AMPENV_SETME.E4B` baseline. See §1.

---

## 3. Ping-pong loops — RESOLVED + faithfully reproduced (2026-06-08)

**EOS has no ping-pong loop mode.** The EOS 4.0 Software Manual (Sample Edit →
Loop Type) confirms looping is a sample-level **On/Off** toggle with a single
forward loop. There is no forward/backward (ping-pong) loop *mode*: the manual
notes EIII forward/backward loops are **rendered into the PCM data** on import
("the loop data will be permanently modified to contain the forwards/backwards
sound data"), not preserved as a mode. So the old speculative `0x0033` byte was
meaningless and has been removed.

**We now reproduce ping-pong the same way EOS does** — by baking the bounce
into the PCM (`processors/loop_renderer.py`, the standard/recommended technique
for forward-only engines). For a ping-pong loop over forward frames S[0..n-1],
the renderer appends the reversed interior S[n-2..1] (endpoints not repeated)
to make a 2n-2-frame region that a plain forward loop plays as the bounce.
`write_e4b()` applies `bake_alternating_loop()` to every sample (on a local
copy — never mutating the caller's bank) before serialising, so an `ALTERNATING`
loop from EXS24 (`loop_mode=2`), SFZ (`loop_mode=alternate`), GIG/DLS
(bidirectional) or a WAV SMPL ping-pong loop is preserved audibly rather than
silently flattened to a forward loop.

Cost: the looped interior roughly doubles in size (n-2 extra frames per
ping-pong sample). Verified end-to-end (synthetic + round-trip via `parse_e4b`).

**Possible future enhancement (separate from ping-pong):** EOS's per-sample
"Loop in Release" flag may correspond to another bit in the `options` u16; not
currently modelled. Low priority.

---

## 4. Swept EQ / Phaser / Flanger / Vocal / Morph filter bytes — RESOLVED (2026-06-08)

All EOS `vpar[58]` filter-type bytes — including the swept/parametric ones — are
confirmed from the hardware-saved `B.005-FILTERTYPES.E4B` (one preset per type,
set on the E4XT and saved; in `/home/lentferj/temp/re_filter_types/`). Encoding
is `byte = group_base | variant`:

- LP `0x00/01/02`, HP `0x08/09`, BP `0x10/11/12`
- **Swept EQ `0x20/21/22`, Phaser `0x40/41/42`, Flanger `0x48`,
  Vocal `0x50/51`, Morph `0x60/61/62`, Peak/Shelf `0x68`**

Full table in `writers/e4b_writer.py:_E4XT_FILTER_BYTES` and
`docs/E4B_FORMAT.md` §4.4. The MPC Vocal-formant types map to the E4XT Vocal
filters; Swept/Phaser/Flanger/Morph have **no MPC-XPM source equivalent**, so
they're written-capable and reverse-mapped when parsing hardware banks, just not
reachable from current input formats (a source-format gap, not an open RE item).

---

## 5. Zone entry: `fine_tune` and `volume` fields

### Current state

`_zone_entry()` in `e4b_writer.py` writes only 6 of 22 zone-entry bytes.
`fine_tune` (cents) and `volume` (dB) are parsed from GIG and other formats
but not written because their byte offsets are unknown.

### Structural analysis of the 22 zero bytes

Known positions: `[2]` lo_key, `[5]` hi_key, `[6]` lo_vel, `[9]` hi_vel,
`[10:12]` sample_idx (BE u16), `[14]` root_key.

Unused bytes: 0,1, 3,4, 7,8, 12,13, 15,16,17,18,19,20,21.

Educated guesses based on similar formats and symmetry:
- `[12]` or `[13]`: fine_tune (signed byte, cents) — follows root_key at [14]
- `[0]` or `[1]`: per-zone volume or gain trim (0–127 linear, or signed dB)
- `[3]` or `[4]`: pan (-64..+63?)
- `[7]` or `[8]`: may mirror lo_vel/hi_vel redundantly (like voice-level vel range)
- `[15:22]`: possibly a per-zone modulation or routing slot

### Hardware RE procedure

See `docs/re_procedures/zone_entry_fields.md` and test bank generator
`tests/re_banks/gen_zone_entry_test.py`.

Two-step diff test:
1. Two presets, same sample, same key, **only fine_tune differs** (0 vs +50).
   → The changing byte(s) are fine_tune.
2. Two presets, same sample, same key, **only per-zone volume differs** (0 dB vs −12 dB).
   → The changing byte(s) are volume.

---

## 6. EXS24 v1.1 zone fields misassigned — CRITICAL

**Status: ready to apply. No hardware needed.**

### Bug

In `_parse_exs_v11()` (`parsers/exs24_parser.py:170–172`) three offsets are
wrong — the three most critical per-zone fields:

| Offset | Current label | **Actual meaning** |
|--------|-------------|-------------|
| `ks+9`  | `key_lo`    | `root_key` (sample centre pitch) |
| `ks+14` | `key_hi`    | `key_lo` (keyboard bottom — 0 is valid) |
| `ks+15` | `key_root`  | `key_hi` (keyboard top — 127 for last zone) |

Also: `ks+12` is `fine_cents` (not `coarse`), `ks+13` is `coarse_st` (not `fine`).

### Exact patch

In `parsers/exs24_parser.py`, replace lines 170–181:

```python
# BEFORE (broken):
key_lo   = data[ks + 9]
key_hi   = data[ks + 14] or key_lo
key_root = data[ks + 15] or key_lo
coarse   = struct.unpack_from('b', data, ks + 12)[0]
fine     = struct.unpack_from('b', data, ks + 13)[0]
vel_hi   = data[ks + 18]
zones_raw.append({
    'index': z_idx, 'name': name,
    'key_lo': key_lo, 'key_hi': key_hi, 'key_root': key_root,
    'vel_lo': 0, 'vel_hi': vel_hi,
    'coarse': coarse, 'fine': fine,
})

# AFTER (correct):
root_key = data[ks + 9]
key_lo   = data[ks + 14]                    # 0 = keyboard bottom (valid — no fallback)
key_hi   = data[ks + 15] or root_key        # 0 = unset → fall back to root
fine_cents = struct.unpack_from('b', data, ks + 12)[0]   # signed, cents
coarse_st  = struct.unpack_from('b', data, ks + 13)[0]   # signed, semitones
vel_hi   = data[ks + 18]
zones_raw.append({
    'index': z_idx, 'name': name,
    'key_lo': key_lo, 'key_hi': key_hi, 'key_root': root_key,
    'vel_lo': 0, 'vel_hi': vel_hi,
    'coarse': coarse_st, 'fine': fine_cents,
})
```

### Impact of the bug

- Full-range single-zone instruments (TB-303, organs): zone collapses to one
  key with root=127 → -98 semitone transpose → completely inaudible on hardware.
- Multi-zone chromatic instruments: bottom range lost on first zone; root=127
  on last zone.

---

## 7. EXS24 GROUP_V11: stereo doubling — APPLIED (2026-06-08)

### Problem

GROUP_V11 chunks were silently skipped. For stereo 101 From Mars instruments,
L+R zones both got included → doubled polyphony + doubled RAM.

### What the empirical test revealed (correction to the original RE)

The original assumption that `ks+11` is a **0-based index** into file-order
groups was **WRONG**.  Scanning the corpus (Oscar / StereoTracks / ExitSummer):

```
Oscar.exs        groups=['Oscar_L','Oscar_R']     zone group_byte ∈ {100, 156}
StereoTracks.exs groups=['StereoTracks_L','_R']   zone group_byte ∈ {100, 156}
ExitSummer.exs   groups=['ExitSummer_L','Layer 1'] zone group_byte ∈ {100, 156}
```

`ks+11` is some encoded reference (100, 156 — not 0, 1).  The robust decode:
the **distinct group_byte values map to file-order groups when sorted ascending**
(100 → group[0], 156 → group[1]).  Each group independently covers the full key
range, so dropping the `_R` group leaves a complete playable map.

### Applied fix (`_parse_exs_v11`)

1. Collect GROUP_V11 names in file order; store `group_byte = data[ks+11]` and a
   file-order `pos` on each zone.
2. After the zone sort: build `gb_to_group = {sorted_distinct_gb[i]: i}`; build a
   drop set of groups whose name ends `_R`/`_r` **and** has an `_L` partner of the
   same base name; gate on `len(distinct_gb) == len(group_names)` (else keep all).
3. Filter `zones_raw` **and** `samples_raw` in lockstep at the dropped file
   positions (zone[i] ↔ sample[i] holds for these instruments), leaving the
   existing positional pairing loop untouched.

### Verification (no hardware needed)

Corpus-wide scan of 2092 v1.1 files: only the 2 true `_L`/`_R` pairs drop zones
(Oscar 162→81, StereoTracks 156→78); ExitSummer keeps all 182 (partner "Layer 1"
isn't an `_R`); zero false positives elsewhere.

---

## 8. EXS24 multi-velocity layers

**Deferred.** No velocity-layered EXS24 instruments found in current test
corpus (101 From Mars / Acid From Mars / 2600 From Mars all use GROUP chunks
for L/R stereo separation only, with `vel_hi=127` everywhere).

If a velocity-layered EXS24 instrument appears: implement a grouping pass
similar to `vel_key` grouping in `xpm_parser.py`, with one `VoiceLayer` per
distinct `vel_lo/vel_hi` range.

---

## 9. SF2 MIDI program numbers

**Status: ready to apply.**

### Problem

`_toc_entry()` always writes `e[31] = 0x00` (MIDI program = any).
`Preset.program_number` is set correctly by the SF2 parser but never used.

### Fix

In `write_e4b()` / `_toc_entry()`, change the `e[31]` write:

```python
# In _toc_entry(), change the last line:
# BEFORE:
e[31] = 0x00   # MIDI prog (any)

# AFTER: accept midi_prog parameter
def _toc_entry(tag, data_size, file_offset, idx, name, midi_prog=0):
    ...
    e[31] = min(127, max(0, midi_prog)) & 0xFF
```

And in `write_e4b()`:
```python
# Preset TOC entries:
for i, p in enumerate(bank.presets):
    toc_entries += _toc_entry(PRES_TAG, len(preset_bodies[i]),
                               preset_offs[i], i, p.name,
                               midi_prog=p.program_number)
```

Collision handling: the current code assigns sequential preset indices (0,1,2…)
regardless of MIDI program number. The E4XT uses TOC entry `[31]` as a hint
for MIDI routing; writing the original program number there is correct even if
multiple presets share the same number (the E4XT picks by preset index, not
by program number alone). No collision handling needed — just write the value.

---

## 10. SMP (non-transpose) velocity grouping

**Status: ready to apply.**

### Problem

In `xpm_parser.py`, all non-transpose zones land in one `VoiceLayer(non_transpose=True)`
regardless of velocity range.  If an XPM has SMP layers at vel 0–63 and 64–127,
both end up in the same voice and the E4XT plays both simultaneously.

### Fix

Apply the same `vel_key` grouping used for pitched zones to SMP zones.
In `xpm_parser.py`, the SMP-mode grouping:

```python
# Current (broken): single NT voice for all SMP zones
smp_voice = VoiceLayer(non_transpose=True)
for layer in layers:
    if layer['root'] == 0:
        smp_voice.zones.append(...)

# Fix: one NT voice per distinct vel range (same pattern as KT voices)
smp_by_vel: dict = {}   # (lo_vel, hi_vel) → VoiceLayer
for layer in layers:
    if layer['root'] == 0:
        vel_key = (layer['vel_lo'], layer['vel_hi'])
        if vel_key not in smp_by_vel:
            smp_by_vel[vel_key] = VoiceLayer(non_transpose=True)
        smp_by_vel[vel_key].zones.append(...)
for v in smp_by_vel.values():
    preset.voices.append(v)
```

---

## 11. HDA directory >16 entries

**Status: APPLIED (2026-08-03 audit) — `build_hda` emits the `[ERROR]`, lists
the dropped files and truncates. The guard below is the code that is in the
tree, not a proposal.**

**Correction (2026-08-03):** the "Future" paragraph below speculates that
multi-block directories chain via a next-block pointer in each block's last
4 bytes, and that confirming this needs hardware RE. That is wrong on both
counts for the **EMU3** filesystem: there is no chaining. The folder's root
directory entry carries a **list of up to 7 dir-content block numbers** at
offset 18 (`0xFFFF` = unused), which `_folder_entry`/`build_emu_hdd` in
`writers/iso_builder.py` already write and which is hardware-confirmed on the
HDD profile. The EMU3 CD path has the same 16-entry bug and is *not* guarded —
see §ISODIR. Note this §11 is about `writers/hda_builder.py`, the **EMU4/EIV**
filesystem, whose directory is a different structure; whether it has an
equivalent block list is genuinely unknown.

### Problem

`writers/hda_builder.py` fits at most 16 E4B files in a single 512-byte
directory block (32 bytes × 16 entries = 512 bytes).  No warning is emitted
when the limit is exceeded; excess files are written to disk but invisible
to the E4XT.

### Fix (guard + warning, not multi-block)

Multi-block directory support is complex and low-priority.  Instead, add:

```python
_MAX_HDA_FILES = 16   # 512-byte dir block / 32 bytes per entry

def write_hda(e4b_paths: list, output_path: str) -> None:
    if len(e4b_paths) > _MAX_HDA_FILES:
        print(f"[ERROR] HDA directory supports max {_MAX_HDA_FILES} files; "
              f"got {len(e4b_paths)}. "
              f"Split into multiple HDA images or increase banks-per-HDA.")
        # Still write what fits; warn about dropped files
        dropped = e4b_paths[_MAX_HDA_FILES:]
        print(f"  Dropped: {[Path(p).name for p in dropped]}")
        e4b_paths = e4b_paths[:_MAX_HDA_FILES]
    ...
```

Future: implement multi-block directory by chaining 512-byte blocks
(each block's last 4 bytes point to the next block's disk offset, or 0 if
last — needs hardware RE to confirm the chaining convention).

---

## 12. TAL-Sampler filtermode encoding — FULLY RESOLVED (2026-06-08)

**13 modes, N = UI dropdown position = internal storage index.**

Confirmed by corpus survey (1706 presets, step=1/12 exact) plus six explicit
`EV-VintageFifthLead_*.talsmpl` saves by Jan Lentfer:

| N  | filtermode | TAL name  | XPM type  | Status |
|----|------------|-----------|-----------|--------|
| 0  | 0.000      | LP 4P     | 3 Low 4   | confirmed — `_LP4P.talsmpl` |
| 1  | 0.083      | LP 2P     | 2 Low 2   | derived (N=UI pos, N=1) |
| 2  | 0.167      | LP 1P     | 1 Low 1   | derived (0 corpus presets) |
| 3  | 0.250      | LP 4PN    | 3 Low 4   | derived |
| 4  | 0.333      | LP 3PN    | 3 Low 4   | derived (no 3-pole XPM) |
| 5  | 0.417      | LP 2PN    | 2 Low 2   | derived |
| 6  | 0.500      | LP 1PN    | 1 Low 1   | confirmed — `_LP1PN.talsmpl` |
| 7  | 0.583      | HP 2PN    | 7 High 2  | confirmed — `_HP2PN.talsmpl` |
| 8  | 0.667      | HP 3PN    | 8 High 4  | derived (no 3-pole HP XPM) |
| 9  | 0.750      | BP 4PN    | 12 Band 4 | confirmed — `_BP4PN.talsmpl` |
| 10 | 0.833      | Notch 2P  | 15 BS 2P  | derived (0 corpus presets) |
| 11 | 0.917      | All Pass  | 3 Low 4   | confirmed — `_AllPass.talsmpl` (no E4B equiv) |
| 12 | 1.000      | BW 6P     | 4 Low 6   | confirmed — `_BW6P.talsmpl` |

Code: `_TAL_FM_XPM = [3, 2, 1, 3, 3, 2, 1, 7, 8, 12, 15, 3, 4]`
Formula: `mode = min(12, max(0, round(val * 12)))`

The only residual approximations are XPM-side (no 3-pole LP/HP in XPM; All Pass
has no E4B equivalent) — the TAL→XPM mode names are now fully confirmed.

---

## 13. E4B vpar[42] = Chorus Amount — RESOLVED (2026-06-08)

`vpar[42]` is the per-voice **Chorus Amount** (Voice/Tuning page). UI 0–100%
maps linearly to byte 0–127:

```
vpar[42] = round(chorus_pct / 100 * 127)        # write
chorus_pct = round(vpar[42] / 127 * 100)         # read
```

### Confirmation (hardware, E4XT)

Read straight off commercial banks, then nailed with a hand-edited save:

| Source | Chorus % | vpar[42] | round(%·1.27) |
|---|---:|---:|---:|
| Ya Mogue (Ya Tech) | 17 | 22 | 21.6 → 22 |
| Phase Rogue | 34 | 43 | 43.2 → 43 |
| Dance Rogue | 35 | 44 | 44.5 → 44 |
| Be an ULTRA (Dutch Stab) | 50 | 64 | 63.5 → 64 |
| WATCH OUT (Dutch Stab) | 89 | 113 | 113.0 → 113 |
| **edited sweep** | 25 / 50 / 75 / 100 | 32 / 64 / 95 / 127 | exact |

The 89→113 and 34→43 points rule out a `/128` scaling; the 25/50/75/100 →
32/64/95/127 sweep pins linearity and the 100 % → 127 maximum. Default 0 = off
(matches the 31 855 zero-valued voices in the corpus).

Chorus **stereo width** is a *separate* parameter (was 100 % in all samples) at
a different, still-unlocated byte — see the note in `TODO.md` if it ever
matters.

### Applied

- `models/common.py`: `VoiceLayer.chorus_amount` (float 0.0–1.0, default 0.0).
- `writers/e4b_writer.py` `_build_voice()`: `vpar[42] = round(chorus*127)`.
- `parsers/e4b_parser.py` `_parse_voice()`: `chorus_amount = vpar[42]/127`.

Byte↔float round-trips bijectively over all 128 values; verified by re-parsing
the edited bank (reads back 25/50/75/100 %).

No source format currently supplies a chorus-amount value, so writers leave it
at the 0.0 default unless an E4B is round-tripped; wiring a source mapping (if
any MPC/XPM/etc. field maps to it) is future work.

---

<details>
<summary>Original corpus investigation (how it was narrowed before the hardware read)</summary>

### Corpus evidence (full commercial-library scan)

Scanned 131 commercial banks / 32 558 voices. `vpar[42]` is non-zero in
703 voices (2.2 %). Findings:

- **Standalone single byte.** The neighbours `vpar[41]` and `vpar[43]` are
  almost always zero (6 and 13 of 703), so byte 42 is *not* the low/high half
  of a 16-bit word — it is one 0–127-ish scalar (observed range ≈ 4–113, with
  most values ≤ 44; 113 is a rare outlier).
- **Per-voice tweakable.** In synth banks the value varies voice-to-voice
  (e.g. *Ambient Synth*: 23/17/33/11/36/29/14/9/4; *Ya Tech*: 22/43/44), so it
  is a real per-voice parameter, not a fixed flag.
- **Authors set it bank-wide on sliced loops.** The dominant value 15 (584 of
  703 voices) is **constant across entire sliced drum-loop banks** — every
  slice voice in *the loop-slice banks* has exactly 15; *the SFX bank* is all 16. A value an
  author sets once and copies to every slice of a loop.
- **No correlation** with the already-decoded properties (filter type/cutoff/Q,
  amp gain, tuning, velocity range) — the bytes that co-occur with a non-zero
  42 are just the always-set structural/template bytes.

### What this rules in / out

- **Rules OUT sample-start offset:** that would have to *differ* per slice of a
  drum loop, but byte 42 is *constant* across all slices. Drop it.
- **Rules OUT a 16-bit value** (41/43 are zero).
- **Rules IN** a single per-voice scalar that a loop author would apply
  uniformly to every slice. Best-fit candidates, in order:
  1. **Glide / portamento rate** (EOS "Glide Rate", 0–127) — uniform across a
     kit, per-voice on synths.
  2. **Chorus amount / width** (per-voice chorus send) — same usage pattern.
  3. **Voice "Group"** number (exclusive/mute group for voice-stealing) — loop
     authors often assign all slices to one group; 0 = none.

### How to confirm (two paths, fastest first)

**Path A — read it straight off a bank Jan already owns (no test banks):**
Load `B.000-a loop-slice bank` (or `the SFX bank`) on the E4XT, open any voice, and
walk the voice-editor pages looking for the parameter that reads a non-default
**15** (the SFX bank: **16**). Whatever page shows that value *is* `vpar[42]`.
This is the cheapest experiment and uses real non-zero data.

**Path B — isolate by single-parameter sweep:** start from one neutral preset,
make 3–4 copies that differ in exactly one candidate (Glide, then Chorus, then
Group), save each as E4B, and binary-diff byte 42. The candidate whose change
moves byte 42 is the answer; record the value↔setting mapping to calibrate.

To target a specific voice on hardware, use the inspector
`tests/re_banks/inspect_vpar.py` (gathered all the evidence above):

```bash
# list every preset/voice carrying a non-default vpar[42], with values
python3 tests/re_banks/inspect_vpar.py --nonzero \
    "~/Dokumente/SYNTHS/E4XT/E4Bs/.../B.000-the SFX bank _.e4b"
```

It prints `bank / preset / voice# / value`, so Jan can open exactly that
preset+voice on the E4XT. `--byte N` reuses it for any other unknown voice byte.

</details>

---

## 14. EXS24 PPC big-endian — WON'T FIX / removed (2026-06-08)

The big-endian branch was **unreachable dead code** and has been removed. A
genuine PPC big-endian EXS file stores its magic as the on-disk bytes
`00 00 00 01`, but those same bytes read little-endian equal `0x01000000`
(`HEADER_MAGIC_LE`), which the parser checks first — so the BE branch could
never execute, and a real PPC file would be (mis)parsed as little-endian
regardless. The two endiannesses cannot be distinguished by magic alone.

Resolution: removed the unreachable branch, the unused `be` flag, and the
vestigial `*_BE` chunk/magic constants; documented EXS24 as little-endian
classic + v1.1 only (README / module docstring). PPC-era test data is also
effectively unobtainable, so there is nothing to validate. Closed as won't-fix.

---

## 15. LFO modulation routing

**Partially unblocked — cord format now known; specific routings wanted.**

**Target (Jan, 2026-06-09):** write at least **LFO→Pitch, LFO→Filter-Freq,
LFO→Filter-Q**, **Key→Filter-Freq** (filter keytrack) and **Velocity→Filter-Freq**
when the input format provides them. Input coverage: XPM (`LfoPitch/LfoCutoff/…`,
`FilterKeytrack`, `VelocityToFilter`), SF2 (`modLfoToPitch/FilterFc/Volume`,
`vibLfoToPitch`, default Velocity→Cutoff modulator), SFZ (`pitchlfo_*/fillfo_*/
amplfo_*`, `fil_keytrack`, `fil_veltrack`), GIG (LFO1/2/3, `VCFKeyboardTracking`,
`VCFVelocityScale`), EXS24 (`FILTER1_KEYTRACK`, velocity-to-filter).

The 4-byte PatchCord format is **confirmed** (no longer a hypothesis — see §4.3
of `E4B_FORMAT.md` and Gap 0 of §17): `[src, dst, amount, flag]`, amount
`= round(pct/100 × 127)` signed, UI cord N = storage slot N. Known ids:
`src 0x50` = Filter-Envelope, `dst 0x38` = Filter-Frequency.

**Decoded so far (2026-06-09, from default-preset cords on the E4XT):**
sources LFO1=`0x60`, Velocity=`0x0C`, Key=`0x08`, FilterEnv=`0x50`; dests
Pitch=`0x30`, Filter-Freq=`0x38`. The `_MOD_TMPL` already carries the cords (all
amount 0): slot 2 LFO1→Pitch (`mod[10]`), slot 4 Velocity→Filter (`mod[18]`),
slot 5 FilterEnv→Filter (`mod[22]`, done), slot 6 Key→Filter (`mod[26]`).

**DONE 2026-06-09 — Key→Filter and Velocity→Filter:** `VoiceLayer.filter_keytrack`
/ `velocity_to_filter` (signed ±1 → cord amounts `mod[26]` / `mod[18]`), written +
read back, mapped from GIG (`VCFKeyboardTracking`/`VCFVelocityScale`, verified on
the maestro grand), SFZ (`fil_keytrack`/`fil_veltrack`), XPM, EXS24
(`FILTER1_KEYTRACK`, scaling unverified). SF2 skipped.

**LFO 1 + LFO 2 settings DECODED & IMPLEMENTED (2026-06-10)** from
`B.011-LFO1 settings.E4B`. They live in the **Primary Zone Table**, not `vpar`;
LFO 2 is an exact **+8 mirror** of LFO 1:

| LFO1 | LFO2 | Param | Encoding |
|---|---|---|---|
| `PZT[42]` | `PZT[50]` | **Rate** | 0–127, default 64. **Hz**: byte 0=0.08, 64=4.12, 127=18.01 (E4XT menu); *not* exponential — log-quadratic fit `ln(Hz)=−3.006e-4·b²+0.08082·b−2.5257` (3-point, refineable) |
| `PZT[43]` | `PZT[51]` | **Shape** | **signed**: −1=Random, 0=Triangle, **1=Sine**, 2=Sawtooth, 3=Square, 4–7=33/25/16/12% Pulse, 8–11=Pat Octaves/Fifth+Octave/Sus4/Neener, 12–13=Sine1,2 / Sine1,3,5, 14=Sine+Noise, 15=Hemi-quaver |
| `PZT[44]` | `PZT[52]` | **Delay** | 0–127 → 0–20 s |
| `PZT[45]` | `PZT[53]` | **Variation** | 0–127 = **0–100 %** (`round(pct/100×127)`, 100 %=127) |
| `PZT[46]` | `PZT[54]` | **Sync** | 0=Key Sync (default), 1=Free Run |

All confirmed against the hardware bank. **Sine=1 confirmed** (`LFO1+2 SINE`
preset: `PZT[43]`+`PZT[51]`=01). `PZT[48]`=01 is a constant between the blocks
(unknown). **Lag processors** follow the LFO block: `PZT[57]`=Lag0, `PZT[59]`=Lag1
(P011 lag0:5/lag1:10 markers).

**Mod cords DECODED (2026-06-10)** from P012's `Chrd10 LFO-FltQ` preset:

| Source id | | Dest id | |
|---|---|---|---|
| `0x60` LFO1~ / `0x61` LFO1+ | | `0x30` Pitch | `0x38` Filter-Freq |
| `0x68` LFO2~ / `0x69` LFO2+ | | `0x39` **Filter-Q (resonance)** | `0x4A` **Vol-Env Decay** |

All four LFO source ids confirmed (LFO1~`0x60` from two cords + the default
LFO1→Pitch; LFO1+`0x61`, LFO2~`0x68`, LFO2+`0x69` from P012 cords 11/12/13).

**IMPLEMENTED:** `VoiceLayer.lfo{1,2}_{rate,shape,delay,variation,sync}` (rate in
Hz, `Optional`/`None`=EOS default) + routing fields `lfo1_to_pitch` (default cord
02 `mod[10]`), `lfo1_to_filter`/`lfo1_to_filter_q`/`lfo2_to_pitch`/
`lfo2_to_filter`/`lfo2_to_filter_q` (written into free cord slots 8+ as
`[src,dst,amt,0]`). The rate byte↔Hz curve lives in `models/common.py`
(`lfo_rate_byte_to_hz` / `lfo_rate_hz_to_byte` / `lfo_knob_to_hz` /
`lfo_pitch_depth_to_amount`), shared by writer, E4B parser and source parsers;
writer `_write_lfo`, parser `_find_cord` — full E4B round-trip, validated against
`B.011`.

**DONE 2026-06-10 — input-format source mapping (XPM / SFZ / SF2):**
- **XPM** — single keygroup `<LFO>` → LFO1: `<Rate>` knob→Hz (`lfo_knob_to_hz`),
  `<Type>`→shape (`_xpm_lfo_shape`), `<Reset>`→Sync, `LfoPitch`→`lfo1_to_pitch`,
  `LfoCutoff`→`lfo1_to_filter` (emitted only when a routing is non-zero).
- **SFZ** — v1 `pitchlfo_*`→LFO1 / `fillfo_*`→LFO2 (sine); v2 `lfo01/02_*` with
  `_pitch`/`_cutoff` targets + `_wave` (`_sfz_lfo_wave`).
- **SF2** — triangle Mod-LFO (gens 22/5/10)→LFO1, Vib-LFO (gens 24/6)→LFO2;
  abs-cents freq→Hz (`8.176·2^(c/1200)`).

Depth→cord-amount is proportional (absolute cord-amount↔semitone/dB scaling
unverified — same caveat as keytrack); bipolar `~` sources only.

**Remaining — GIG LFO mapping (deferred):** needs a test `.gig` to validate +
the libgig 3ewa LFO1/2/3 (amp/filter/pitch) byte offsets; current `_decode_3ewa`
reads only EG1/EG2/VCF. Unipolar `+` sources (0x61/0x69) unused (no format needs
0→+ modulation yet).

---

## 16. Binary MPC `.pgm` format

**Mostly DONE (2026-06-08).** `parsers/pgm_parser.py` reads MPC500/1000/2500,
MPC2000/2000XL and MPC60 binary `.pgm` (auto-detected by magic). The only
remaining variant is **MPC3000** (`0x07 0x00`, `byte2==0x00`) — its magic
collides with the MPC60 `.PGM`, so it needs a body-level discriminator and a
test file. See the "XPM parser" item in `TODO.md`.

---

## 17. Filter envelope — reproduction gaps (strategy, 2026-06-08)

**Question (Jan):** can we fully reproduce the filter envelope, the way the amp
envelope now is?

**Current state — partial.** The 6-stage filter envelope at `PZT[14:26]` is
hardware-confirmed (`B.005-FltEnvTest.E4B`); `_build_voice()` writes it when
`filter_env_amount > 0.01` and `_parse_voice()` reads it back, so it round-trips
losslessly. It is mapped from source for **XPM only** (`xpm_parser.py` sets the
`filter_env_*` fields) and for **E4B→E4B**. Two gaps keep it from being as
complete as the amp envelope:

### Gap 0 — the filter envelope wasn't *routed* to the cutoff — FIXED (2026-06-09)

The filter-envelope shape at `PZT[14:26]` does nothing on its own: EOS reaches
the cutoff through a **modulation cord** "Filter Env → Filter Freq" — the E4XT UI
"**Cord 05**" = mod-matrix **storage slot 5** (`50 38 …` = `src=0x50`
Filter-Envelope → `dst=0x38` Filter-Frequency). On a fresh preset that cord sits
at **amount 0 %**, so a written envelope is inert. Our generated KT voices wrote
an **all-zero** mod matrix → no cord → no sweep (symptom: all `FLT_DECAY_CAL`
presets sounded identical, and every source-mapped filter envelope was silent on
hardware).

*(False start: I first wrote the depth to slot 7's `16 08 7F` cord — `mod[30]` —
because that one is non-zero in the hardware template. But Jan confirmed that
shows up as the E4XT's "Cord 07", a different routing; the real filter-env cord
is slot 5 / `mod[22]`, amount 0 by default. B.005-FltEnvTest's slot 5 is also 0,
so that bank never actually swept either — its diff only proved the PZT shape.)*

**Fix (UI-faithful encoding):** `writers/e4b_writer.py` writes the EOS default
cord table for any filter-envelope voice (KT or NT), and puts the **depth in the
Cord-05 amount byte** — `mod[22]` = `round(filter_env_amount × 127)`, signed (±,
for downward sweeps) — while the PZT envelope levels are written full-scale. So
the E4XT shows Cord 05 at the real `FilterEnvAmount %`. `e4b_parser.py` mirrors it
(reads amount from `mod[22]`, shape from PZT). Driven by every source's filter-
env-amount field: XPM `FilterEnvAmt`, SFZ `fileg_depth`, SF2 `modEnvToFilterFc`,
GIG VCF, EXS24. Verified: amounts +1.0/+0.5/+0.25/−0.5 round-trip through `mod[22]`.

**CONFIRMED on hardware (2026-06-09).** Jan set Cord 05 → 100 %; the filter
envelope sweeps (`FILT_ENV.wav`). Byte↔% scaling pinned by `B.010-CordAmountTest`
(cords set to 0/±20/…/±100 %): **`amount_byte = round(pct/100 × 127)`, signed** —
+100 %=`0x7F`, −100 %=`0x81`, 0 %=0. Cord layout `[src, dst, amount, flag]`,
amount at byte index 2; UI cord N = storage slot N (so Cord 05 = `mod[22]`).

### Gap A — rate→time calibration — CONFIRMED shares the amp curve (2026-06-09)

The filter envelope reuses the amp `_fenv_rate()` (`time_s = 0.0310·e^(0.0581·
rate)`). Measured `FLT_DECAY_CAL` on the E4XT (Cord 05 = 100 %) and analysed with
`--mode filter` (centroid sweep, two passes). The reliable low rates land on the
amp curve almost exactly:

| rate (PZT[18]) | filter sweep (avg) | amp curve |
|---:|---:|---:|
| 8  | 0.050 s | 0.049 s |
| 16 | 0.080 s | 0.079 s |
| 24 | 0.110 s | 0.125 s |

(rates 32–64 read short and noisily because the spectral-centroid metric
saturates once the cutoff drops below the harmonics — a measurement artifact, not
a curve difference.) Combined with the XPM result (filter and volume envelopes
share one exponent), this confirms the filter envelope uses the **same** curve as
the amp envelope — which the writer already does. **No code change needed.**

<details><summary>original Gap A strategy</summary>

The filter envelope reuses the amp envelope's hardware-calibrated `_fenv_rate()`
(`time_s = 0.0310 · e^(0.0581 · rate)`). EOS envelopes are structurally
identical, so the curve *probably* applies to the filter envelope too — but this
was never measured. (This is the "secondary calibration" question that was
dropped when §2 was marked resolved.)

*Strategy:* extend `tests/re_banks/gen_amp_envelope_test.py` to sweep the filter
**Decay-1 rate** `PZT[18]` (e.g. 8/16/24/32/48/64) on a sustained tone with high
resonance and full filter-envelope amount, so the cutoff sweep is clearly
audible. Measure the sweep time per rate on the E4XT and compare to the amp
curve:
- **If they match** (within the log-fit residual): document that amp and filter
  envelopes share one calibration — no code change, just a confirmation note.
- **If they differ:** fit a separate `(_FENV_RATE_A, _FENV_RATE_K)` pair and
  split `_fenv_rate()` into amp/filter variants.

Cheapest cross-check first: a single bank with the filter Decay-1 rate at, say,
24, played and timed — if the filter sweep takes ≈ the amp curve's 0.169 s, the
shared-curve hypothesis holds and a fuller sweep can confirm.

**Test bank:** `tests/re_banks/gen_filter_envelope_test.py` builds
`FLT_DECAY_CAL.E4B` + `.iso` — one bank, 6 presets sweeping `PZT[18]` =
8/16/24/32/48/64 (the amp set), each a resonant 4-pole LP with a full filter
envelope so the Decay-1 sweep is audible. Step-by-step + result table in
`docs/re_procedures/filter_envelope.md`.

</details>

### Gap B — source filter-envelope mapping (partially DONE 2026-06-08)

The shared helper `cents_to_filter_env_amount()` (in `models/common.py`) maps a
filter-EG depth in cents to `filter_env_amount` (±9600 cents ≈ full sweep).

- **XPM** — ✅ (pre-existing).
- **SFZ** — ✅ **DONE.** `sfz_parser` reads `fileg_attack/decay/sustain/release`
  (+ `fileg_depth` → amount). Verified: `fileg_depth=4800` → amount 0.5, times
  passed through exactly.
- **SF2** — ✅ **DONE.** `sf2_parser` reads the modulation-envelope generators
  (26 attackModEnv, 28 decayModEnv, 29 sustainModEnv [0.1 % units], 30
  releaseModEnv) with generator 11 `modEnvToFilterFc` as the amount. Smoke-tested
  on real SoundFonts (graceful no-op when `modEnvToFilterFc = 0`, which is the
  common case).
- **GIG** — ✅ **DONE 2026-06-08.** The previous `_parse_3prg_envelope()` looked
  for a non-existent `3ewg` chunk (so amp env was *always* default). Rewrote it
  against **libgig 4.3.0** (`gig.cpp` `DimensionRegion`): navigate
  region → `3prg` → `3ewl` → `3ewa`, decode EG1 (amp) and EG2 (filter) with
  libgig's `GIG_EXP_DECODE(x)=1.000000008813822**x` (raw int32 → seconds), plus
  VCF cutoff/resonance/type. A `3prg` holds one `3ewl` per dimension region; amp
  env from the first, filter from the first VCF-enabled one (the default region
  is usually VCF-off). Validated **byte-exact against `gigdump`** on
  `maestro_concert_grand_v2.gig` (EG2 D=0.005 S=1.0 R=2.0, VCFCutoff 111→0.87,
  type 0→LP24) and the Hammond organ corpus (VCF-off → no filter env). This also
  **fixed the long-standing default-amp-env bug**.
- **EXS24** — ✅ **DONE 2026-06-08.** The filter + its envelope live in a
  `TYPE_PARAMS` block (`0x04000101`) at `chunk+84`, which the parser now decodes
  (legacy section: u32 count, `count` 1-byte IDs, `count` signed-16 values —
  ConvertWithMoss `EXS24Parameters`). Reads `FILTER1_TOGGLE=44`,
  `FILTER1_TYPE=243`, `FILTER1_CUTOFF=30` (0-1000), `FILTER1_RESO=29` (0-1000),
  and **ENV2** = `77/78/79/80` (0-127). Conversions per ConvertWithMoss
  `EXS24Detector`: type 0/1/2/3/4/5 → LP24/LP24/LP12/LP12/HP12/BP12; **cutoff is
  LINEAR in frequency** — `cutoff_Hz = value/1000 × 20 kHz` — then placed on the
  E4B exponential cutoff scale (`_exs_cutoff_to_e4b`, fixed 2026-06-09; we
  previously used `value/1000` directly as the exponential position, which made
  every EXS filter far too dark — caught by cross-checking HumanMusic); env time
  = v/127·10 s, sustain = v/127. Validated across **361 filtered instruments** in
  `~/Samples` and the cutoff matches CWM Hz exactly (e.g. 333→6660 Hz).
  Applies only when `FILTER1_TOGGLE==1` and ENV2 has a non-trivial shape.
  (v1.1 format = 1717/1753 local files; the rare classic/`0x04000101`-less
  variants are not wired and stay envelope-less.)

The writer already emits whatever the parsers set — no writer change needed.
Verify with `--info --verbose` (shows filter cutoff/Q; chorus) and an E4B
round-trip. No hardware required for any of the four.

---

## 18. XPM (MPC) envelope value → time curve — measured & APPLIED (2026-06-09)

MPC keygroup envelope *times* are normalised **0.0–1.0** controls, not seconds.
**Measured on an MPC One** by recording `XPM_VOL_DECAY` (8 audible notes; C1 /
value 0 produced no signal — instant decay) and analysing it with
`tests/re_banks/analyze_envelope_recording.py`:

| value | decay-to-−40 dB (s) |
|------:|--------------------:|
| 0.375 | 0.031 |
| 0.500 | 0.114 |
| 0.625 | 0.331 |
| 0.750 | 1.211 |
| 0.875 | 4.014 |
| 1.000 | 14.69 |

(values ≤ 0.25 hit the recording's ~60 ms floor but the fit + the silent C1
confirm they're near-instant.) Steep exponential fit:
**`seconds ≈ 0.00079 · e^(9.78 · value)`** (~×3.4 per 0.125 step).

**Applied:** `_xpm_env_to_seconds()` in `xpm_parser.py`, used for
`VolumeAttack/Decay/Release` and `FilterAttack/Decay/Release` (sustain fields are
levels, unchanged).

**Filter envelope — CONFIRMED shares the curve (2026-06-09).** Recorded
`XPM_FLT_DECAY` and analysed with `--mode filter` (centroid sweep): the fit is
`0.00092·e^(9.80·value)` vs the volume `0.00080·e^(9.77·value)` — **identical
exponent** (the 1.18× scale is just centroid-settle vs −40 dB defining "done"
differently). So one curve covers all MPC envelope segments; no separate
filter constants needed.

<details><summary>original bug note</summary>

`xpm_parser.py` previously passed the 0–1 values through as seconds. Akai
publishes no value→time chart, so the curve had to be measured on hardware.

`tests/re_banks/gen_xpm_envelope_test.py` builds two Keygroup programs
(`XPM_VOL_DECAY`, `XPM_FLT_DECAY`) — 9 keygroups each, one per key C1…G#1,
sweeping the value 0→1 in 0.125 steps — plus a looping `XPM_Tone.wav`. Built
against the real minimal MPC-V Keygroup layout (empty `ProgramPads-v2.10`, one
`Instrument` per key, `KeyTrack` off so pitch is constant). Load on the MPC One,
time the decay/sweep per key, fit, and add `_xpm_env_to_seconds()` to the
parser. Full procedure: `docs/re_procedures/xpm_envelope.md`.

The MPC time curve is expected to be exponential in the 0–1 value; if
`VolumeDecay` and `FilterDecay` measure the same, one converter covers both.

</details>

---

## 19. Mod-cord depth scaling — absolute-unit calibration (strategy, 2026-06-10)

**LFO→Pitch MEASURED 2026-06-12; LFO→Filter + the rest still need recordings.**
Companion to the TODO item "Mod-cord depth scaling uncalibrated"; full procedure
in `docs/re_procedures/mod_cord_depth.md`.

The cord *routing* and amount encoding are RE'd (`round(depth×127)`, ±127=±100 %;
see §4.3/§15); the amount→musical-units transfer function is now measured for
LFO→Pitch and still a proportional guess for the others (`FILTER_ENV_FULL_CENTS=
9600`, 0–1 pass-through for LFO→Filter / Key→Filter / Velocity→Filter).

### Measurements

- **LFO→Pitch — DONE 2026-06-12.** `PitchDepth 25/50/75/100 %` recorded on the
  E4XT (`PitchDepth.wav`, all four presets in one take, square LFO ≈0.5 Hz),
  analysed per segment.  One-sided depth was **400 / 801 / 1190 / 1583 cents** at
  25 / 50 / 75 / 100 % — **dead-linear through the origin**, implied full-scale
  1599 / 1603 / 1587 / 1583 c → **mean 1593 c (σ=8)**, i.e. **±16 semitones**, not
  the ±1 octave assumed.  Applied: `LFO_PITCH_FULL_CENTS = 1200 → 1593`
  (`models/common.py`).  The old value made every LFO→Pitch vibrato ≈33 % too
  deep (1593/1200).
- **LFO→Filter — first take UNUSABLE; bank redesigned for a clean re-record.**
  `FltDepth.wav` (25/50/75/100 % over a 0.50 base cutoff) couldn't be measured:
  (1) the up half-cycle **rails at the 20 kHz cutoff ceiling** for every amount
  ≥50 %, so the high state is clipped, and (2) a saw's spectral peak jumps
  between the *fundamental* (filter open) and the *resonant peak* (filter closed),
  so peak/centroid/whitened-peak trackers all scattered (σ ≈ 0.8–1.1 oct).  Only
  the **25 % point was clean** (resonant peak 524↔2096 Hz = exactly 2.0 oct p-p,
  geo-mean 1048 Hz = the 0.50 base) → extrapolating by the proven-linear law gives
  a *tentative* ±4 oct one-sided (8 oct p-p) full-scale, **not committed** off one
  point.  Re-record #1 (low 55 Hz saw, `FILT_AMOUNTS = 10/20/30/40 %`, base 0.30,
  Q 0.92) did NOT rail and gave a usable regression-through-origin of **±3.74 oct
  one-sided** (full100 per amount 3.68/4.45/3.35/3.78, σ 0.40 oct) — consistent
  with the old 25 % point (±4 oct).  But σ is still ~0.4 oct because a saw only
  has energy AT its harmonics (55 Hz spacing), so the resonant-peak reading snaps
  to the nearest harmonic (~0.26 oct quantisation; low states clustered on
  220/330 Hz = 4th/6th harmonic).  **Refinement (pending re-record):** the
  FiltDepth + KeyTrk + VelTrk presets now use a **white-noise** source (`Noise`,
  `non_transpose=True`) — a continuous spectrum gives one smooth resonant bump
  with no harmonic snapping, so the peak reads the cutoff to FFT-bin precision.
  **MEASURED on the noise take 2026-06-12** (`FltDepth.wav`, amounts 10/20/30/40 %,
  full100 = 3.96/3.54/3.62/3.68, σ 0.16 oct — vs σ 0.40 for the saw):
  **100 % LFO→Filter ≈ ±3.65 oct one-sided (≈4383 cents)**.  Cross-checks
  Key→Filter (±3.65 oct + 0.713 oct/oct ⇒ key source ±1 over ~128 keys, 2.08≈2.0).
  **Reconciliation:** destination `0x38` (Filter-Freq) has a single sensitivity
  shared by LFO→Filter, Key→Filter, Velocity→Filter AND FilterEnv→Filter, so
  `FILTER_ENV_FULL_CENTS = 9600` is ~2.2× too high → reset to **≈4383** at apply
  time (filter-env depth has likewise been under-delivered in conversions).
  Apply: add `lfo_filter_depth_to_amount(oct) = oct / 3.65` (clamped ±1).
- **Key→Filter — first take exposed a transpose-rail; KeyTrk/VelTrk redesigned.**
  `Keytrack.wav` (original bank: `Saw110`, root A2, transposing across C1..C6)
  showed C5 and C6 at the **same pitch** — the saw transposed +27/+39 st above
  root hits the **E4XT maximum sample-playback-rate ceiling**, so the top notes
  rail to one pitch and the moving pitch/harmonics make the cutoff untrackable
  (resonant-peak readings were pure noise).  Fix: `KeyTrk 100` / `VelTrk 100` are
  now **`non_transpose=True`** (vpar[38]) — every key plays the SAME fixed pitch,
  so only the keytracked/velocity-tracked cutoff moves (the Key→Filter `0x08→0x38`
  and Velocity→Filter `0x0C→0x38` cords track the key/velocity number regardless
  of pitch transposition).  Play a MODERATE key range (C2..C4) so the cutoff stays
  in range.
  **MEASURED 2026-06-12** (re-recorded `Keytrack.wav`, `SawLo55` non-transpose,
  C2..C4 C-major scale): the cutoff now tracks the key as a clean straight line —
  **0.713 octave of cutoff per octave of key at 100 % keytrack** (slope 71.3 c/
  semitone, linearity r=0.9994, σ=19 c), i.e. **~0.71 : 1, not 1 : 1**.  This
  CROSS-CHECKS the LFO→Filter number: with a ±3.8 oct/100 % `0x38` sensitivity,
  0.713 oct/oct implies the Key source spans ±1.0 over ~128 keys (full-keyboard
  normalisation) — so the ±3.8 oct LFO→Filter and 0.713 Key→Filter are mutually
  consistent.  (At these 3–8 kHz cutoffs the saw's 55 Hz harmonic spacing is
  negligible, so this take did not need the noise source.)  To apply: map an
  input's desired key-tracking (oct/oct) to cord amount = desired / 0.713,
  clamped to ±1 — note a true 1 : 1 request saturates the cord (0.71 max).
- **Velocity→Filter — BUG found & fixed 2026-06-12 (wrong polarity); depth still
  pending.** First noise take (`VelTrack.wav`, vel 1/64/127 = 1/50/100 %) showed
  the resonant peak pinned at 440 Hz for ALL velocities while only the amplitude
  changed — velocity reached the voice but never opened the filter.  Cause: the
  default EOS cord uses **`Vel<`** (source `0x0C`, the SUBTRACT polarity), so vel
  127 only reaches the *base* cutoff and softer notes merely darken — the filter
  never rises above base, and our measurement floor missed the low end.  The EOS
  manual documents three source polarities (`+` add / `~` centre / `<` subtract);
  for velocity-tracking we want **`Vel+` (ADD) = `0x0A`**.  Source IDs confirmed on
  the E4XT: `0x0B` reads as `Vel~`, `0x0C` as `Vel<`, so the consecutive block is
  `[+,~,<]` = `[0x0A,0x0B,0x0C]` → `Vel+` = `0x0A`.  `e4b_writer` now sets the
  Velocity→Filter cord source to `0x0A` whenever `velocity_to_filter` is non-zero
  (`_SRC_VEL_PLUS`; parser unaffected — it reads the amount at fixed offset 18).
  **This was a real conversion bug**: every prior velocity→filter mapping wrote
  the subtract polarity, so on hardware harder notes never brightened above base.
  **DEPTH MEASURED 2026-06-12** (`VelTrack.wav`, Vel+ confirmed, 5-velocity sweep
  2/31/64/95/127 ×reps).  Two extra fixes were needed for a clean take: (a) at
  100 % amount the cutoff railed past 20 kHz, so the test preset uses **25 % amount
  over a 0.45 base** and scales ×4; (b) the default **Vel→Amp** cord made soft
  hits inaudible while loud hits clipped — the generator now **zeroes Vel→Amp**
  (`_MOD_TMPL[2]=0`) for the whole measurement bank, so velocity changes ONLY the
  cutoff.  Result: dead-linear in velocity (r=0.9999); full velocity (0→127) spans
  1.87 oct at 25 % → **≈7.6 oct at 100 %**.  This MATCHES Key→Filter (0.713 oct/oct
  × 10.6 oct keyboard = 7.56 oct) — velocity and key share the same 0→~2-unit
  source scaling.  **Unified result:** the `0x38` (Filter-Freq) destination =
  **3.65 oct per source unit at 100 % cord**, confirmed by four independent cords
  (LFO ±3.65 one-sided, FilterEnv 0→3.65 = 4383 c, Key/Vel 0→127 = ~7.6 oct).
  Apply (velocity): `velocity_to_filter = desired_full_range_cents / 9120`
  (= 7.6 oct).  **Direction is configurable, not hardcoded:** the writer always
  uses the Vel+ source (anchors vel 0 at base) and the SIGN of the cord amount
  picks the direction — `+` = harder opens the filter, `−` = harder closes it.
  Parsers preserve the input veltrack sign (SFZ `fil_veltrack`, XPM
  `VelocityToFilter`).  Only the **open** (+) direction was hardware-measured; the
  close (−) direction is the expected signed-cord behaviour but still unverified —
  a negative-veltrack preset would confirm it.

### Strategy — square-LFO two-state measurement

A **square** LFO at a known cord amount makes the destination hop between two
*steady* states; their difference = `amount/100` of full-scale. Sweeping the
amount (25/50/75/100 %) checks linearity and pins the constant. Key/Velocity
tracking use no LFO — vary the played key / velocity instead.

The whole loop is automated and stays consistent with the converter, because the
test bank is generated *through* the same writer (the square LFO and the cord
amounts come from the `lfo1_shape` / `lfo1_to_pitch` / … model fields):

```bash
python3 tests/re_banks/gen_mod_depth_test.py            # → MOD_DEPTH_CAL.E4B/.iso
# …record each preset on the E4XT (≥3 LFO cycles; KeyTrk C1..C6; VelTrk vel 1/64/127)…
python3 tests/re_banks/analyze_mod_depth.py rec.wav --mode pitch   # or --mode filter
```

`analyze_mod_depth.py` tracks per-frame pitch (FFT peak, parabolic-interpolated)
or the filter resonant peak, 1-D k-means-splits the take into its two states, and
reports low/high Hz, peak-to-peak cents/octaves and the one-sided depth. Verified
against a synthetic ±100 cent square signal (recovered 200.8 c peak-to-peak).

### Fix recipe (apply after measuring)

1. **LFO→Pitch** — set `LFO_PITCH_FULL_CENTS` to the measured one-sided cents at
   amount 100 % (the analyzer prints `cents × 100/A`).
2. **LFO→Filter-Freq** — add `lfo_filter_depth_to_amount(octaves)` in
   `models/common.py` from the cutoff octaves-per-100 %; route the SFZ/SF2/XPM
   cutoff-LFO depths through it instead of the raw 0–1 pass-through.
3. **FilterEnv→Filter** — reconcile `FILTER_ENV_FULL_CENTS` with the same
   Filter-Freq octaves-per-100 % (they share the `0x38` destination).
4. **Key→Filter / Velocity→Filter** — confirm 100 % ≈ 1:1 key tracking and fix
   the velocity full-scale; both currently pass through unverified.
5. If any response is **non-linear** in amount, fit a curve (as done for the LFO
   rate and the envelope rate↔time) rather than a single constant.

---

## 20. Regression sweep (input → E4B round-trip), 2026-06-11

Harness `/home/lentferj/temp/regression/roundtrip.py`: for each real input file
parse → `write_e4b` → `parse_e4b`, then compare the two models feature-by-feature
(zones key/vel/root, sample mapping + PCM/rate/root, amp+filter envelopes, filter
cutoff/res/env, key/vel→filter, non-transpose, chorus, LFO routing) with
tolerances for the known quantisations.  Run over real libraries in
`~/Samples` and the MPC backup `EXPANSIONS`.

**Result (56 real files, 14/format): 47 PASS, ZERO feature diffs**
(XPM 13, SFZ 7, SF2 13, **EXS 14/14**; the rest skipped on absent samples /
unusual dialects, plus one intended SF2 reject).  **Cross-validated on a second
random sample (SEED=2026, ~56 different files): 49 PASS, again zero diffs** — so
across ~96 real files the input→E4B round-trip loses no modelled feature.  Every file that parsed with samples
round-trips through E4B with all implemented features intact — small patches and
big multisamples alike (322-zone SF2, 219-zone/125 MB XPM, 143 MB EXS).  Two
robustness fixes were made when real files exposed gaps:

- **SF2 missing `pdta`** — `parse_sf2` raised a bare `KeyError` on a non-standard
  SFX bank; now a clear `ValueError("missing 'pdta' LIST chunk")` (and `sdta` is
  optional).
- **EXS24 + SFZ sample resolution** — commercial packs often keep audio in a
  sibling folder several levels from the patch (e.g. Samples-From-Mars
  `.../Pack/WAV/<instr>/` while the `.exs` is `.../Pack/Logic EXS/<bank>/<cat>/`;
  or Loopmasters `.../Pack/XS_SINGLE_SOUNDS/XS_DRUM_HITS/`).  Added a **lazy
  ancestor audio-folder index** (built only on the first miss, file-capped):
  scans subdirs whose name contains an audio keyword (`wav/audio/sample/sound/
  loop/hit/drum/kit/…`) under up to 5 ancestors and resolves by basename.
- **EXS24 sample-name variant** — smaller v1.1 sample chunks (some drum kits)
  have no "clean path" at +420; the filename is the display name at +20.  Parser
  now prefers +420 only when the chunk is large enough, else falls back to +20.
  Together these took EXS from 3/14 → **14/14** on the sample.

**Remaining non-bugs:** some SFZ skip because the samples are genuinely absent or
the patch is an unusual dialect (e.g. `#KOTO.sfz` has no `sample=` opcodes and
uses `.flac` — `load_wav` is WAV only, via Python's `wave` module).  These are
coverage gaps, not E4B round-trip failures.

---

## Open questions for Jan

*(These all need your direct input — compile answers for the next session.)*

1. **TAL filtermode** — *RESOLVED 2026-06-08*.  See §12.  No further action needed.

2. **vpar[42]** — *RESOLVED 2026-06-08*. It is per-voice **Chorus Amount**
   (0–100 % → 0–127); confirmed on the E4XT and wired into the model/writer/
   parser. See §13. No further input needed.

3. **Ping-pong loop** — *RESOLVED 2026-06-08*.  EOS 4.0 manual confirms loop is
   a sample-level On/Off (forward only); no ping-pong mode exists.  See §3.

4. **EXS24 PPC** — *RESOLVED 2026-06-08 (won't fix)*.  The BE branch was
   unreachable dead code and has been removed; see §14.  No input needed.

5. **EXS24 GROUP_V11 group byte** — *RESOLVED 2026-06-08*.  Ran the diagnostic
   on Oscar / StereoTracks / ExitSummer directly: `ks+11` is NOT a file-order
   index (values are 100/156); distinct values map to groups when sorted
   ascending.  Fix applied and verified corpus-wide; see §7.  No input needed.

6. **Amp envelope test banks**: Once Jan has time at the E4XT, run the test
   banks from `tests/re_banks/gen_amp_envelope_test.py` and record the results
   table as described in `docs/re_procedures/amp_envelope.md`.

7. **Mod-cord depth calibration**: record `MOD_DEPTH_CAL` (from
   `tests/re_banks/gen_mod_depth_test.py`) on the E4XT and run
   `analyze_mod_depth.py` per the procedure in §19 /
   `docs/re_procedures/mod_cord_depth.md`. Yields the real cents/octaves per
   cord-% so LFO→Pitch/Filter, FilterEnv, Key/Velocity→Filter stop being guesses.

---

## XPM TuneCoarse / TuneFine dropped — fix strategy

### Root cause

`xpm_parser` reads neither `TuneCoarse` nor `TuneFine`; `e4b_writer` writes no
tuning. The model fields exist (`ZoneMapping.fine_tune` cents,
`VoiceLayer.fine_tune` cents, `VoiceLayer.transpose` semitones) but are inert.

MPC stores tuning at **two levels**, both of which must be summed:
- Instrument-level `<TuneCoarse>` (semitones) + `<TuneFine>` (cents) — applies to
  the whole keygroup (this is what `the detuned-stack split preset` uses for its detuned stack).
- Layer-level `<TuneCoarse>`/`<TuneFine>` — per sample layer.

### Parser fix (straightforward)

In the zone/voice builder, read instrument-level tune once and layer-level tune
per layer, sum them:

```python
inst_ct = int(_get_text(instrument, 'TuneCoarse', '0'))
inst_ft = int(_get_text(instrument, 'TuneFine',  '0'))
lay_ct  = int(_get_text(layer, 'TuneCoarse', '0'))
lay_ft  = int(_get_text(layer, 'TuneFine',  '0'))
transpose = inst_ct + lay_ct          # semitones
fine      = inst_ft + lay_ft          # cents
```

Store `transpose` on the voice (or fold into `root_key` for tracking voices:
`root_key -= transpose`) and `fine` on the zone/voice `fine_tune`. Note the
detuned-stack use needs the layers in **separate voices** (see the SFZ-stacking
and RootNote items) — otherwise a single voice can't carry two different tunings
for the same key.

### Writer side (needs RE)

`_zone_entry()` (22-byte secondary zone) does not encode fine tune or transpose;
the byte offsets are unknown — **same gap as the GIG `fine_tune` / per-zone
volume items**. RE procedure (mirror those): on the E4XT make two identical
presets differing only by voice transpose (+12 st) and by fine tune (+50 c),
save, binary-diff the voice param block (`vpar`) and the 22-byte zone entries.
Likely a voice-level coarse (semitone) byte and a fine (cents) byte in `vpar`,
since MPC tuning here is per-instrument (= per-voice), not per-zone. Coarse
transpose for *tracking* voices can be applied immediately via `root_key`
without RE; only fine tune (and transpose on non-transpose voices) needs the
byte.

### Validation

`the detuned-stack split preset`: Inst 2 voice +12 st / +15 c, Inst 4 +25 c — confirm the stacked
voices beat against the untuned ones (the chorused "split" sound). Re-check the
three demo presets and fix the `feature_coverage.ods` tuning labels.

**Regression case — two presets must stop sounding identical (Jan 2026-06-12):**
`the detuned-stack split preset` (P003) and `Inst-Bass-JR Jupiter Rising Spt` (P004)
currently both collapse to the *same* structure (`1 voice, 12 zones, all
key0-127/vel0-127/root60`) — verified identical. Their source samples sound
alike (both JR "UniPanBass" unison pads), so once the RootNote-collapse + the
dropped split/tuning are gone they're indistinguishable. After the RootNote +
TuneCoarse/TuneFine fixes they should differ (P003 has an extra +12 st / +15 c
detuned octave layer that P004 lacks). Good end-to-end check that the
split/stack/tune chain is restored.

---

## XPM long-common-prefix name truncation — fix strategy

### Root cause

`_safe_name` truncates to 16 chars head-first. Sample sets sharing a long prefix
(`Inst-Pad-LazSp-UniPanBass_C1_A …`) collapse to the same 16 chars; the dedup
counter then yields `…-1/-2/-3`, losing the meaningful `C1_A`/`C2_B` tail.

### Fix

Reuse the EXS24 approach (RESOLUTION_NOTES §CR-18): keep the **full** name as the
cache key / model name, and apply the 16-char E4B limit only at write time with a
**tail-preserving** scheme — e.g. keep the last 15 chars (the
note/round-robin/layer suffix is the distinguishing part), or `prefix[:8] +
hash(full)[:8]`. Apply in `_safe_name` (or wherever names are truncated for the
E4B sample chunk) so distinct source samples never share a written name.
Validate on `the detuned-stack split preset`: 12 samples should keep distinct, recognisable names
(`…C1_A`, `…C1_B`, … not `…-1`, `…-2`).

---

## XPM `KeygroupWheelToLfo` (mod-wheel → LFO depth) — fix strategy

### Root cause

`<KeygroupWheelToLfo>` (program-level, 0–1) is the MPC "WHEEL→LFO" depth: the mod
wheel scales the LFO's modulation amount. At 100% the LFO is fully wheel-gated
(no modulation at rest). `xpm_parser` never reads it; `e4b_writer` writes
LFO→Pitch/Filter/Vol cords at their full static amount → the E4XT applies the LFO
continuously at full depth (Jan: "too much LFO→Pitch" on `Bass-MS20 Acoustik`,
which has `KeygroupWheelToLfo=1.0`).

### EOS mechanism — cord-amount modulation

EOS PatchCords can modulate the **amount of another cord** (the EOS manual's
"a cord can control another cord's amount"). The standard mod-wheel-vibrato patch
is two cascaded cords:

```
Cord A:  LFO1~ → Pitch          amount = programmed depth (e.g. LfoPitch)
Cord B:  ModWheel → [Cord A Amount]   amount = KeygroupWheelToLfo (≈100%)
```

With Cord A's *initial* amount at 0 and Cord B scaling it by the wheel, the LFO
depth follows the wheel — matching the MPC. Same pattern for LFO→Filter and
LFO→Vol cords (one ModWheel→CordAmount cord per gated routing, or share if EOS
allows summing).

### What must be reverse-engineered

We already have LFO sources (`0x60`/`0x68`), dests Pitch `0x30` / Filter `0x38` /
Q `0x39`. **Unknown, needed for this fix:**

1. **ModWheel source id.** EOS controller sources (Pitch Wheel, Mod Wheel,
   Pressure, MIDI A–P…). RE: on the E4XT build a preset with ModWheel→Pitch at a
   known amount, save, read the cord `[src, 0x30, amt, 0]` → `src` is ModWheel.
2. **"PatchCord N Amount" destination ids.** EOS exposes each cord's amount as a
   destination (commonly `Cord 1 Amt …`). RE: build LFO1→Pitch (cord A) + a
   second cord whose dest is "Cord A Amount" at a known amount; save; the second
   cord's `dst` byte is the Cord-A-amount destination id. Sweep which cord slot
   maps to which amount-dest id (likely a contiguous block).

RE test-bank generator: add `tests/re_banks/gen_wheel_to_lfo_test.py` emitting a
few presets (ModWheel→Pitch; LFO→Pitch + ModWheel→CordAmt) for Jan to save+read,
mirroring `gen_mod_depth_test.py`.

### Fix once ids are known

- `xpm_parser`: read `KeygroupWheelToLfo` (program-level) into the model (e.g.
  `Preset.wheel_to_lfo` or per-voice `VoiceLayer.wheel_to_lfo`).
- `e4b_writer`: when `wheel_to_lfo > 0` and any `lfo*_to_*` routing is set, write
  the LFO→dest cord with its depth **and** a `ModWheel → [that cord's amount]`
  cord scaled by `wheel_to_lfo`. When `wheel_to_lfo == 0`, keep today's static
  behaviour.
- `e4b_parser`: mirror — recognise a ModWheel→CordAmount cord and recover
  `wheel_to_lfo`.

### No-RE interim approximation

Until the ids are RE'd, the cheapest improvement is to **scale the static LFO
depths by `(1 − KeygroupWheelToLfo)`** so a 100%-wheel-gated LFO is written at
~0 depth (silent at rest, like the MPC's default wheel-down state) instead of
full. This loses the wheel-up expressivity but stops the "too much LFO" at rest.
Gate behind a flag/comment so it's obviously a stopgap. **Decide with Jan** —
some may prefer keeping audible LFO over silence.

---

## XPM `RootNote=0` non-transpose mis-detection — fix strategy

### Root cause

`parsers/xpm_parser.py:331`:

```python
raw_root = int(_get_text(layer, 'RootNote', '60'))
smp_mode = (raw_root == 0)                    # ← WRONG signal
root = max(0, raw_root - 1) if not smp_mode else 60
```

`RootNote=0` is the MPC "root unset" sentinel, not "no key tracking". Treating it
as SMP routes pitched multisample zones through the SMP path (key 0-127, root 60),
detuning them badly.

### Authoritative semantics (ConvertWithMoss)

- **Read** `MPCModernDetector.java:481-487`:
  `keyRoot = RootNote - 1` (when present); `keyTracking` is overridden by the
  per-layer `KeyTrack` field **only when `IgnoreBaseNote` is True** — otherwise
  the zone key-tracks (default 1.0).
- **Write** `MPCKeygroupCreator.java:223`:
  `RootNote = limitToDefault(keyRoot, limitToDefault(keyLow, 0)) + 1` — i.e. the
  root falls back to the keygroup **LowNote** when unset. `IgnoreBaseNote` is
  written as `keyTracking == 0 ? "True" : "False"` (`:344`).

So: **non-transpose ⇔ `IgnoreBaseNote=True`** (with `KeyTrack=False`); root, when
`RootNote=0`, **= keygroup LowNote**.

### Corpus evidence (4 files)

| File | combo | correct handling |
|---|---|---|
| MS20 2c (broken) | `RootNote=0, IgnoreBase=False, KeyTrack=True, kg36-38` | **track, root=36 (LowNote)** |
| F9 Disco Rhds | `RootNote=0, IgnoreBase=True, KeyTrack=False, kg0-127` | non-transpose (as now) |
| F9 Disco Rhds | `RootNote=37, IgnoreBase=False, kg0-39` | track, root=36 |
| DX7 Advent | `RootNote=0, IgnoreBase=True, kg0-127` (Chain-Noise) | non-transpose |
| DX7 Advent | `RootNote=0, IgnoreBase=False, kg0-127` (Chain-Synth Osc) | **AMBIGUOUS — see below** |
| DX7 Advent | `RootNote=102, IgnoreBase=False, kg101-105` | track, root=101 |
| JR Short Pad | `RootNote=0, IgnoreBase=False, KeyTrack=False, kg0-47…` | track, root=LowNote |

### Design decision — the full-range ambiguous case  → **DECIDED: Option B (Jan, 2026-06-12)**

`RootNote=0 + IgnoreBaseNote=False + kg0-127` (DX7 "Chain-Synth Oscillators"):
strict CWM semantics say *track* (IgnoreBase=False), but root would fall back to
LowNote=0 → tracked from C-1 across the whole keyboard (wild pitch). Today these
are treated as non-transpose (root 60), which probably sounds closer for a
full-range oscillator/texture layer. Options:

- **(A) Strict CWM:** non-transpose ⇔ `IgnoreBaseNote=True`. Simplest, matches
  the reference, but risks regressing full-range root-0 texture layers.
- **(B) CWM + full-range guard (recommended):** non-transpose when
  `IgnoreBaseNote=True` **OR** (`RootNote=0` AND keygroup spans the whole
  range 0-127). Bounded keygroups with `RootNote=0` always track (root=LowNote);
  full-range root-0 layers stay fixed-pitch. Fixes all 168 mistuned multisample
  files without touching the working full-range texture layers.

### Fix (option B)

```python
ignore_base = _get_text(instrument, 'IgnoreBaseNote', 'False').lower() == 'true'
raw_root    = int(_get_text(layer, 'RootNote', '0'))
full_range  = (lo_key == 0 and hi_key == 127)

non_transpose = ignore_base or (raw_root == 0 and full_range)
if non_transpose:
    root = 60                      # fixed pitch; existing SMP/NT voice path
else:
    root = (raw_root - 1) if raw_root > 0 else lo_key   # ← LowNote fallback
    # normal key-tracking zone over [lo_key, hi_key]
```

Keep the SMP accumulation path only for `non_transpose` zones; tracking zones go
through the normal `vel_to_voice` zone builder with their real keygroup key range.
Re-run the MS20 patch: expect 1 voice with 15 zones at kg36-38…kg78-84, roots
36/39/42/… (not 15 zones at 0-127 root 60).

### Validation

- `Bass-MS20-Patch 2c.xpm` → tuned chromatically, no aliasing.
- F9 Disco Rhds / DX7 Advent → non-transpose layers unchanged (diff the voice
  `non_transpose` flags before/after).
- Spot-check a few of the 168 flagged files by ear on hardware.

---

## SFZ keyswitch articulations — fix strategy  → **DECIDED: one preset per articulation, drop KS keys (Jan 2026-06-12)**

### Root cause

`sfz_parser.py:256-272` discards every group whose `sw_last != sw_default`,
keeping only the default articulation. Keyswitch instruments lose all but one
style.

### Agreed mapping

The E4XT has no keyswitch. Emit **one E4B preset per articulation** and **drop
the keyswitch keys** (CWM-style):

- Group SFZ `<group>`s by their `sw_last` value (each distinct `sw_last` = one
  articulation; some articulations span several groups — e.g. 3× D#2 Accent).
- For each articulation, build a preset named `<basename>-<sw_label or note>`
  (sanitise the label: "F2 Pizzicato" → "Pizzicato"). Within a preset, apply the
  normal region→voice logic (incl. the overlapping-stacking fix below for its own
  groups).
- Do **not** emit zones for the keyswitch key range itself (regions are the
  playable range; the `sw_lokey..sw_hikey` band is control-only — already not a
  region, so nothing to drop there, but ensure no preset maps the KS keys).
- A bank built from one SFZ then holds N presets (Sustain, Tremolo, Pizzicato…),
  selectable on the E4XT.

### Implementation sketch

- In `parse_sfz`, accumulate regions into a dict keyed by `sw_last` (default key
  for groups without `sw_last`). Replace the single-preset build with a loop that
  emits one `Preset` per key.
- Preserve the existing round-robin / xfade / CC1 warnings (fire once per file).
- Preset naming: dedupe + 16-char limit at write; keep the articulation label.
- `convert.py` already handles multi-preset banks, so no caller change.

### Validation

`1st-violin-SOLO-KS-C2.sfz` → ~6 presets (Sustain, Tremolo, Normal, Accent,
Staccato, Pizzicato), each playable G3+, no keyswitch keys. Pizzicato preset must
sound like pizz, not sustain.

---

## SFZ overlapping-region stacking — fix strategy

### Root cause

`parsers/sfz_parser.py` creates one `VoiceLayer` (`:232`) and appends every
region to it (`:387`). An E4B **voice** plays only one matching zone per note,
so overlapping samples (multiple instruments / dynamic layers on the same
key+vel) don't stack. Verified on `all-brass-SEC-accent.sfz`: 14 `<group>`s,
155 regions, up to 14 overlapping at one key → converts to `1 voice, 155 zones`
→ thin. ConvertWithMoss instead emits MPC keygroups with up to **4 simultaneous
Layers** (54 keygroups, 85 samples, 26 of them 4-layer); the E4XT analogue is
parallel **voices**.

### Design decision (resolve before coding)

Two ways to split the single voice into stacking voices:

- **(A) One voice per `<group>`.** Each SFZ `<group>` is already a self-contained
  keymap (confirmed: brass groups 1–14 each span the keyboard at vel 0–127, one
  per instrument/dynamic layer). Map each group → one voice. Most faithful to
  per-group params (envelope/filter/pan differ per instrument), and mirrors how
  the SFZ author organised it. Risk: SFZs that use `<group>` for *velocity*
  layers or round-robin would over-split — but those are already handled
  upstream (vel grouping / `seq_position`), and a group whose regions don't
  overlap any other group's key+vel range collapses back to shared coverage
  anyway. Gives 14 voices here.
- **(B) Greedy overlap-lane allocation.** Ignore groups; for each zone place it
  in the first voice whose existing zones don't overlap its key+vel, else open a
  new voice. Format-agnostic, guarantees exactly `max_overlap_depth` voices, but
  can mix zones from different instruments into one voice (they'd share that
  voice's envelope/filter — fine for VPO, lossy in general).

**Recommendation: (A)**, falling back to per-region lanes only inside a group if
a single group self-overlaps. Keeps per-instrument voice params intact.

### Voice-count cap

The E4XT allows many voices per preset (far more than the MPC's 4-layer cap), so
we need not down-select like CWM. But a preset stacking 14 sustained looped
voices per note is heavy on polyphony; consider an optional cap (e.g. warn + keep
the loudest N by `volume`) if real banks blow the voice budget. Not needed for
correctness — decide with Jan.

### Implementation sketch

- Replace the single `voice = VoiceLayer()` with a `voices: list[VoiceLayer]`
  keyed by group identity (a counter incremented on each `<group>` whose key+vel
  span overlaps an already-open voice).
- Move the per-voice param assignment (envelope/filter/LFO, currently "first
  region that declares one") to per-group, reading the group defaults.
- Append each voice with zones to `preset.voices`.
- Re-validate `multi_vel_layers` / `multi_key_zones` feature counting and the
  existing xfade/round-robin/keyswitch warnings still fire once per file.

---

## XPM slice-based playback — fix strategy

### Root cause

`xpm_parser.py` lines 320–371: when processing a `<Layer>`, the parser reads
`SampleName`, `RootNote`, `VelStart`/`VelEnd`, and per-layer tuning, but
silently ignores `<SliceStart>`, `<SliceEnd>`, and `<SliceLoop>`. The full WAV
is loaded unchanged.

### Field semantics (verified against MPC 3.7 manual + measured WAV frame counts)

All slice offsets are in **sample frames** (confirmed: `SliceEnd` equals the
referenced WAV's frame count in 6 of 7 `the wide-drone preset` slices; the 7th,
`C1_B`, is `2454` against a `2666`-frame WAV — a genuine pad-end trim).

| Field | MPC UI name | Meaning |
|---|---|---|
| `SliceStart` | Pad Start | first frame played |
| `SliceEnd` | Pad End / "end of sample" | last frame of the play + loop region |
| `SliceLoopStart` | **Loop** (Loop Position) | frame the loop repeats *from* |
| `SliceLoop` | **Pad Loop** mode | **enum**: 0=Off, 1=Forward, 2=Reverse, 3=Alternating (ping-pong) — numeric 0/1 confirmed in data; 2/3 inferred from the manual's mode list, not yet seen |
| `SliceLoopCrossFadeLength` | loop crossfade | frames; `-1` = none |
| `Direction` | reverse playback | 0 = forward (all 7 slices are 0) |

Manual (Pad Loop, Forward): *"hold the pad to cause that sample to repeat from
the **Loop Position** to the **end of the sample**."* So the loop region is
`[SliceLoopStart, SliceEnd]`, **not** the whole slice. Pad Loop only sustains
when the pad's **Sample Play = Note On** (One Shot ignores it) and **Slice =
Pad** — both true here, which is why the intent is a held, sustaining drone.

**Degenerate loop points (must handle):** 4 of 7 `the wide-drone preset` slices have
`SliceLoopStart == SliceEnd` (a zero-length loop: C1_A `[1325,1325]`, C2_A
`[664,664]`, C2_B `[669,669]`, C4_B `[336,336]`). C3_A has a real sub-loop
`[468,672]`; C1_B loops the whole pad region `[1120,2454]`. The MPC's behaviour
when Loop Position == Pad End is **not yet confirmed** — most likely it falls
back to looping the entire pad region `[SliceStart, SliceEnd]`. **Verify by ear
/ on hardware before trusting either interpretation.**

### Fix

**1. Slice extraction** — after `load_wav()`, trim `SampleData.data` to the pad
range `[SliceStart, SliceEnd]`:

```python
slice_start = int(_get_text(layer, 'SliceStart', '0'))
slice_end   = int(_get_text(layer, 'SliceEnd',   '0'))
bytes_per_frame = sd.channels * (sd.bit_depth // 8)
if slice_end > slice_start:
    sd.data = sd.data[slice_start * bytes_per_frame : slice_end * bytes_per_frame]
```

**2. Slice loop** — `SliceLoop` is the Pad Loop **enum** (Jan confirmed mode is
"Pad Loop / Forward" for `the wide-drone preset`). Map it; loop region is
`[SliceLoopStart, SliceEnd]`, both rebased to the trimmed slice. Clamp the
degenerate `loop_start >= loop_end` case to the whole trimmed slice (TENTATIVE —
see "Degenerate loop points" above):

```python
mode = int(_get_text(layer, 'SliceLoop', '0'))
if mode:  # 0 = Off
    loop_pos = int(_get_text(layer, 'SliceLoopStart', '0')) - slice_start
    n_frames = len(sd.data) // bytes_per_frame
    sd.loop_start = loop_pos if 0 <= loop_pos < n_frames - 1 else 0
    sd.loop_end   = n_frames - 1
    sd.loop_type  = {1: LoopType.FORWARD,
                     2: LoopType.REVERSE,       # if model/E4B supports it
                     3: LoopType.PINGPONG}.get(mode, LoopType.FORWARD)
```

**3. Sample cache key** — two instruments may reference the same `SampleName`
with different slice ranges. Change the cache key from `sample_name` to
`(sample_name, slice_start, slice_end)` so each unique slice becomes a separate
`SampleData` entry (with its own truncated name suffix to keep 16-char uniqueness).

**4. SMP-mode tuning** — in the SMP accumulation dict, store the
instrument-level `TuneCoarse`/`TuneFine` alongside `vel_lo`/`vel_hi`, and
propagate them into the `ZoneMapping` when building the final SMP voice (lines
422–433). Group by `(vel_lo, vel_hi, tune_coarse, tune_fine)` rather than vel
range alone.

**Caveat — the 122× unison stack:** `the wide-drone preset` layers 122 identical
`C1_A` instruments (same slice, `TuneCoarse=12`, tiny per-voice `LfoPitch`/
`LfoPan`), which on the MPC produces a thick phasing drone. The E4XT caps voices
per preset far below 122, so even with correct slices the converted preset can
only approximate the massed-unison character. Worth a note to Jan when fixing.


## Fixed (un-gated) LFO→Filter on MS-20 patches — pending aural check

`Bass-MS20-Patch 2c` (FEATUREDEMO_02 P003) plays LFO1→Filter at a fixed +42
(33%).  **Verified faithful:** source `KeygroupWheelToLfo=0.0`, `LfoCutoff=0.33`,
`LfoPitch=0`.  No code change unless Jan's by-ears check picks one of:

**Path B — depth calibration.**  Today `lfo1_to_filter` (= XPM `LfoCutoff`,
0–1) is written linearly: `cord_amount_to_byte(depth)` = `round(depth*127)`
(`models/common.py:130`).  There is no measured `LFO_FILTER_FULL_*` constant
analogous to `LFO_PITCH_FULL_CENTS=1593` (`models/common.py:156`).  If the
filter wobble is too strong/weak, add one: measure the E4XT filter-LFO sweep in
cents/Hz at cord amount 127 vs the MPC at `LfoCutoff=1.0`, then scale
`lfo1_to_filter` by `measured_mpc_depth / measured_e4xt_full` before the write
(mirror §19's mod-cord absolute-unit calibration).  Apply in `xpm_parser.py:396`
(`lfo1_to_filter=lfo_cutoff`) so it's source-unit-correct.

**Path C — always wheel-gate (deviation from source).**  Force gating regardless
of `KeygroupWheelToLfo`: in `xpm_parser.py` clamp `wheel_to_lfo = max(wheel_to_lfo,
DEFAULT_WHEEL_GATE)` when any `lfo1_to_*` is active.  e4b_writer already splits
every LFO cord (static + ModWheel→CordN-Amt) for `Kw>0`, so no writer change.
This makes every LFO preset wheel-dimmable but no longer matches the MPC default.

**Path A (likely) — leave as-is.**  Fixed filter LFO is authentic (MS-20 MG→VCF
is always-on; the MPC author set `KeygroupWheelToLfo=0`).  Then just close the
TODO.  (Optional cosmetic: suppress the template-default `ModWheel→C02Amt @16`
cord when `lfo1_to_pitch==0` — but that edits the hardware-extracted `_MOD_TMPL`
byte output, so only with Jan's sign-off.)

---

## §KRZ-PROG — K2000 program parameters (envelopes / filter / LFOs) — fix strategy

**Goal:** extend `writers/krz_writer.py` to carry amp envelope, filter (type +
cutoff + resonance), filter envelope, and LFOs from the `VoiceLayer` model into
the KRZ program object — i.e. give the K2000 path the synth fidelity the E4XT
path already has.

**Where we are:** sample mapping + tuning convert and sound (HW-confirmed). The
program is written as a proven-but-flat minimal layer (`PGM LYR ENC ENV CAL
HOB×4`, amp env = sustain-only). The full plan, corpus analysis, byte-level
hypotheses, and per-parameter checklists are in
`docs/re_procedures/krz_program_re.md`. Do **not** duplicate them here; this
section is the decision log + open questions.

**Decided design target:** Algorithm 1, DSP slot = `4POLE LOPASS W/SEP` (24 dB/oct
resonant lowpass). It maps 1:1 onto every source format (cutoff, resonance=SEP,
filter-env→freq, amp ADSR, LFO→pitch/filter). We will NOT implement all 31
algorithms — one good subtractive algorithm covers the conversion need.

**RE method — recommended order:**
1. Amp envelope (ENV 0x21) — `KRZ_ENVLOC` + `KRZ_ENVSW*` banks, no MIDI needed.
   Calibrate `_krz_env_rate(seconds)` mirroring the E4XT `_fenv_rate`.
2. Algorithm byte + filter cutoff/resonance — needs a filter in the signal path,
   so either scripted-SysEx poke (strategy A) or create-on-HW + diff (strategy C).
3. LFO + filter envelope routing.

**Implementation plan once bytes are known:**
- Add `_make_layer_segments` params: `algorithm`, `amp_env`, `filter_cutoff`,
  `filter_reson`, `filter_env`, `lfo*`. Emit the ENC (algorithm + routing), the
  filled ENV, the filter HOB page, and an LFO segment when the voice has one.
- Reuse the existing `VoiceLayer` envelope/filter/LFO fields (already populated
  by every parser for the E4XT path) — no parser changes needed.
- Keep the writer's "reduced layer is OK" property: only emit modulation
  segments (LFO/ASR/FUN) when the source actually uses them.

**DONE 2026-06-17 — LFO shape complete map (live K2000R SysEx probe):**
All 26 LFO shapes probed by navigating EditProg→LFO page (EDIT→SoftF×3→SoftB,
CursorRight×3 to Shape), then wheeling through all values and reading LCD:

| Byte | Display | Shape |
|------|---------|-------|
| 0 | Sine | Sine |
| 1 | +Sine | Unipolar Sine |
| 2 | Square | Square |
| 3 | +Squar | Unipolar Square |
| 4 | Triang | Triangle |
| 5 | +Trian | Unipolar Triangle |
| 6 | Rise S | Rising Sawtooth |
| 7 | +Rise | Unipolar Rising Saw |
| 8 | Fall S | Falling Sawtooth |
| 9 | +Fall | Unipolar Falling Saw |
| 10–25 | N Step / +N Step | Step patterns: 3/4/5/6/7/8/10/12 Step (± unipolar) |

**Critical correction:** prior RE notes said "Triangle=2" — **WRONG**. Byte 2 is
Square. Triangle is byte 4. `_LFO_SHAPE` in `krz_writer.py` fixed (and fallback
changed from 2 to 0=Sine). Tests in `tests/test_krz_writer.py` pin all values.

K2000 has **no random/S&H LFO** — `'random'` and `'hemiquaver'` map to byte 20
(8 Step), the closest deterministic stepped approximation.

**OPEN QUESTIONS FOR JAN** (also in the .md §8):
1. Is the K2000R on a MIDI link to the PC? That unlocks the *scripted-SysEx* RE
   loop (`tests/re_banks/krz_sysex_probe.py`, codecs unit-tested) — poke an object
   byte, read the LCD back via `PARAMVALUE`. Massively faster than by-ear.
   **UPDATE 2026-06-17: K2000R MIDI link confirmed and operational.**
2. Capture path for create-on-HW saves — Gotek floppy (as for the sample work) or
   SCSI/SmartMedia?
3. Confirm priority: amp env → filter → LFO.


## §KRZ velocity-split layers — IMPLEMENTED 2026-06-24

**Status:** DONE. `writers/krz_writer._split_voice_by_velocity()` groups a
voice's zones by their distinct `(lo_vel, hi_vel)` band and returns one shallow
VoiceLayer copy per band; `write_krz` expands `preset.voices` through it before
the layer-cap/keymap-assignment loop, so each band gets its own keymap + layer
with its vel window (single-band voices pass through unchanged → no regression).
Verified: AlphaPad #200 → 3 layers, vel 0-64/65-96/97-127, full-keyboard each;
`tests/test_krz_writer.py` 8/8 pass. Pending K2000R HW A/B. Strategy below kept
for the record.

**TODO:** "KRZ: clean velocity-SPLIT layers collapse to ONE layer". AlphaPad
(#200) has 3 mutually-exclusive velocity bands (0-64/65-96/97-127); the KRZ
gets 1 layer because (1) `xpm_parser._overlaps()` merges non-overlapping vel
bands into one voice, and (2) `krz_writer._build_keymap_entries()` keys the
keymap by note only, so co-keyed vel-band zones overwrite each other (top
band wins → too bright). The E4B path is correct and must stay untouched.

**Decision: fix in the KRZ writer, not the parser.** The E4B model (one voice,
per-zone vel ranges) is the right faithful representation and the E4XT honours
it. Re-splitting in the XPM parser would regress the E4B side and the lane
budget. The K2000 simply can't express per-key velocity zones inside one
keymap — it needs one layer per velocity band — so the split belongs at KRZ
write time. The writer ALREADY accepts per-layer `lo_vel`/`hi_vel`
(`_build_layer(... lo_vel, hi_vel)`, `_voice_key_vel_range`); we just never
feed it more than one band per voice.

**Patch (writers/krz_writer.py), in the per-voice program-build loop:** before
building a layer+keymap for a voice, group that voice's zones by their distinct
`(lo_vel, hi_vel)` band and emit one (keymap, layer) pair per band, passing the
band's vel range to `_build_layer`. Sketch:

```python
from collections import OrderedDict
def _vel_bands(voice):
    bands = OrderedDict()
    for z in voice.zones:
        bands.setdefault((z.lo_vel, z.hi_vel), []).append(z)
    return bands   # {(lo,hi): [zones]}, file order preserved
```

Then where the code currently does "one keymap + one layer per voice", iterate
`_vel_bands(voice)`: build `_build_keymap_entries` from that band's zone subset
(make the keymap builder take an explicit `zones` list, or a shim VoiceLayer
carrying only the band's zones), and `_build_layer(..., lo_vel=lo, hi_vel=hi)`.
A single-band voice (the common case) yields exactly today's output — zero
regression. Respect `_MAX_KRZ_LAYERS = 32`: AlphaPad = 3 bands × 1 key-split
voice = 3 layers, fine; for drum kits already at many layers, cap and warn.

**Verify:** rebuild K2KFEATDEMO; `krz_reader.walk_program` should report
**3 LYR** for `Alpha Pad`, each LYR segment byte[5]/[6] = the band's lo/hi vel
(0/64, 65/96, 97/127). Then HW A/B on the K2000R — soft notes should now play
the darker low-velocity layer.

This is the KRZ twin of §10 (SMP "one voice per distinct vel range"); cross-
check that fix's shape when implementing.


## §XPM release-time recalibration — fix strategy (2026-06-24)

**TODO:** "XPM→KRZ: VolumeRelease time ~2.5× too short". AlphaPad
`<VolumeRelease>0.763780` → current `_xpm_env_to_seconds` (`0.00079·e^(9.78·v)`,
RE'd in §18 from a *decay*-to-silence sweep) → 1.39 s; Jan matched the MPC One
original by ear at K2000 ~3.48 s (×2.51 short; would need v≈0.858).

**Do NOT hand-tune the constants off one point.** One sample can't distinguish
a constant release×factor from a wrong curve shape, and §18's curve is HW-
verified for *decay* — blindly scaling it would risk regressing decay.

**RE procedure (mirror §18 / `docs/re_procedures/xpm_envelope.md`):** on the
MPC One, make a single full-level looped tone, set Decay/Sustain to hold, sweep
**`<VolumeRelease>`** across ≥4 values (0.25, 0.50, 0.764, 1.0), release the
key and measure time from key-off to silence (−60 dB) for each. Then:
- if the points sit on `0.00079·e^(9.78·v)` scaled by a constant → add a single
  `_XPM_REL_FACTOR` applied only to release (and re-check whether filter-release
  needs the same);
- if the shape differs → fit a separate `_xpm_release_to_seconds()` and route
  `VolumeRelease`/`FilterRelease` through it, leaving attack/decay on the §18
  curve.

Sanity anchor already in hand: (v=0.764 → ~3.48 s) implies, if it's a constant
factor, ~2.5× — but confirm with the sweep before shipping. Record the raw
measurements in `docs/re_procedures/xpm_envelope.md` alongside the decay data.

---

## §BB. Band-Boost (BB 2P/4P/6P/8P) filters → wrong target (2026-06-25)

MPC FilterType **19–22 = Band Boost** (parametric peak: full signal + a boosted
band).  Both writers send it to a **bandpass**, which removes the out-of-band signal
instead of boosting in-band → thin/hollow.  See TODO "Band-Boost (BB) filters map to
BANDPASS".  Symptom source: `K2KFEATDEMO` #204 **Bass-MS20-Patch 2c** (FilterType=19,
Cutoff=0.27, Reson=0.65).

### E4B — ready patch (no HW needed)
EOS **Swept EQ 1-oct** (`vpar[58]=0x20`) is a parametric band gain; the gain law is
already HW-RE'd (`gain_dB=(byte−64)×0.375`, `byte 64 = 0 dB`).  Band-*stop* (15–18)
already uses it with a **negative** gain; Band-*boost* is the **same filter with a
positive** gain.  In `writers/e4b_writer.py`:

1. Re-point the BB entries in `_XPM_FILTER_TYPE` from bandpass to Swept EQ:
   ```python
   19: 0x20,  # BB 2P boost → Swept EQ 1-oct (+gain)
   20: 0x20,  # BB 4P boost → Swept EQ 1-oct (+gain)
   21: 0x20,  # BB 6P boost → Swept EQ 1-oct (+gain)
   22: 0x20,  # BB 8P boost → Swept EQ 1-oct (+gain)
   ```
2. In the `if vpar[58] == _SWEPT_EQ_1OCT:` block, choose the gain *sign* from the
   source type (both BS and BB now land on 0x20):
   ```python
   res = max(0.0, min(1.0, voice.filter_resonance))
   if 19 <= voice.filter_type <= 22:      # BB band-boost → +gain
       gain_db = +(12.0 + 12.0 * res)
   else:                                   # BS band-stop → −gain (cut)
       gain_db = -(12.0 + 12.0 * res)
   vpar[61] = max(0, min(127, round(gain_db / _SWEPT_EQ_DB_PER_STEP) + 64))
   ```
   (Magnitude mirrors the existing notch depth; refine vs. the MPC BB gain law if a
   measurement is taken.)

### KRZ/K2000 — RESOLVED 2026-06-25 (PARA MID, hardware-RE'd)
BB 19–22 now map to **Algorithm 2 PARA MID** (parametric band boost), RE'd via
`tests/re_banks/gen_krz_paramid_re.py` + a PARAJLZ.KRZ disk-save diff:

| Byte | Value |
|---|---|
| `CAL[29]` (algorithm) | **2** |
| `HOB0(0x50)[0]` F1-FRQ function | **51** |
| `HOB0(0x50)[1]` center freq | signed −48…+79 = existing `_cutoff_byte` (16 Hz…25088 Hz) |
| `HOB1(0x51)[0]` F2-AMP block | **16** |
| `HOB1(0x51)[1]` gain | **dB, 1:1 signed** (0→0, +24→24, +48→48; ±48 range) |
| `HOB2(0x52)[0]` F3 | **40** (None) |

Wired in `_k2_filter_plan` (BB → `(2, 51, 16, 40)`) and `_patch_layer`
(HOB0[1]=`_cutoff_byte(cutoff)`, HOB1[1]=`+12..+24 dB` from resonance).  Verified
end-to-end on #204 Bass-MS20-Patch (FilterType=19 → ALG2/51/AMP+20 dB).  Full
procedure + capture table: `docs/re_procedures/krz_paramid.md`.  Later refinement:
measure the MPC's actual BB gain law to calibrate the dB depth (FRQ already exact).

### Single-cycle oscillator extraction — IMPLEMENTED + HW-CONFIRMED 2026-07-10 (E4XT)

New creative stage `processors/single_cycle.py` (CLI `--single-cycle[=auto|N]`):
replaces each sample with a short forward-looped slice of its own waveform so the
sampler plays it as an oscillator, and the hardware's filter/envelopes make the
patch. Turns an MPC multisample into an E4XT / K2000 synth voice; collapses a
bank to a few hundred bytes per zone. No writer changes were needed — the feature
only populates the shared `models.common` structures.

Key design decisions (all verified end-to-end, tuning within ≤1 cent):

- **Pitch detect**: pure-Python normalised autocorrelation (no numpy). Primary
  search is narrow, around the period implied by the sample's own `root_note`
  (the converter already trusts it for tuning), so it never locks to a spurious
  octave; a wide first-strong-peak fallback covers missing/wrong root metadata.
- **Cycle count**: `auto` = ONE cycle (see the 2026-07-11 refinement below); `=N`
  takes N contiguous cycles for the source's cycle-to-cycle movement.
- **Sub-sample extraction + loop**: refine the period to sub-sample precision
  (parabolic interp of the autocorr peak), resample exactly 1 (or N) period(s) to
  an integer frame count so the wrap is phase-perfect (no crossfade), TILE to
  `_MIN_LOOP_FRAMES=256`, and prepend an 8-frame faded lead-in so `loop_start ≥ 1`
  (old EMU "loop can't start at frame 0" caveat; harmless on K2000).
- **Tuning — the crux**: the perceived pitch is `rate / single-cycle-period`
  (an N-cycle loop of a periodic wave still sounds at the fundamental, NOT at
  `rate/loop_len`). The sub-semitone correction is **baked into each sample's
  stored sample rate** (`rate = orig_rate · freq(nearest_note) / f_fund`), not a
  cents field — because **E4B carries only ONE fine-tune per voice**, so a
  per-zone cents field cannot individually tune samples that share a voice.
  Rate-baking is per-sample and near-exact (integer-Hz rounding ≈ 0.04 c near
  44 kHz) and is engine-agnostic (both writers derive pitch from stored rate +
  root). `fine_tune`/`coarse_tune`/`transpose` are zeroed; `root_key` set to the
  nearest note. Survives the KRZ headroom downsample (a clean resample preserves
  `rate/loop_len`).
- **Neutral preset**: `filter_type=3` (XPM "Low 4" → E4B `0x00` 4-Pole LP /
  K2000 Alg-1 4POLE LOPASS — the one XPM value that lands on 4PLP on BOTH and is
  truthy so the KRZ writer actually patches it), `filter_cutoff=1.0` (open),
  organ amp env (instant on, full sustain), no LFO. `--single-cycle-keep-flt/
  -lfo/-amp/-all` let the already-converted source params pass through instead.
- **Best-effort**: unpitched/too-short samples are left full-length (logged), the
  preset is still neutralised — a creative option where "failing" is acceptable.
- **EOS minimum loop length (HW-confirmed 2026-07-10)**: the E4XT silently
  DOUBLES an ultra-short loop → the note plays an **octave low**. Measured on the
  E4XT with pure-sine single cycles: an 84-frame loop (C5, 523 Hz) played in
  tune, but a **42-frame loop (C6, should be 1046 Hz) played 524 Hz** — exactly
  one octave down, identical to the 84-frame note. Fix: `_MIN_LOOP_FRAMES = 256`
  in `single_cycle.py` — high notes repeat whole cycles (`n_cyc` bumped to
  `ceil(256/p)`) until the loop clears the minimum. Identical repeats keep the
  pitch and single-cycle timbre; low notes stay literally one cycle. After the
  fix, MIDI 24→84 track perfectly (each octave doubles, 0 cents). (Above MIDI ~84
  gxtuner can't lock at 2–4 kHz and reports garbage, but the notes are audibly
  correct — a tuner limit, not playback.)

Companion flag `--split-velocity-layers` (`processors/zone_reducer.explode_velocity_layers`)
explodes each preset's velocity layers into separate full-velocity presets
(handles both the XPM zone-band and SF2/SFZ/GIG multi-voice representations);
overflow past the 1000-preset cap fans into extra banks automatically.

Verification done: N=1 tunes to 0.0 c through a real E4B write→parse round-trip;
N=4 within ±1 c (sub-sample measured); loop_start ≥ 1; filter/keep-flags; both
representations of the layer split; E4B + KRZ both write. **HW-CONFIRMED on the
E4XT 2026-07-10** (via `SINETEST.iso`, pure-sine single cycles): tuning tracks
perfectly and in tune from MIDI 24 to 84 (each octave doubles, 0 cents), loops
sound and look good. The one issue found on hardware — ultra-short loops playing
an octave low — is fixed (see the EOS-minimum-loop bullet above) and re-confirmed
on the E4XT.  KRZ (K2000) tested via a Gotek FAT12 floppy (SCSYNTH.img) — sounds
good.  Cleared to commit.

#### Refinements from real-world HW testing (2026-07-11)

Everything below is in `processors/single_cycle.py` and was driven by playing the
output on the E4XT (and a K2000 floppy).

- **`auto` is now ONE cycle, tiled — not a multi-cycle fill.**  The original
  `auto` filled ~1024 frames with *contiguous* cycles.  A real analog oscillator
  drifts slightly cycle-to-cycle, so a multi-cycle loop isn't exactly periodic and
  buzzed at the loop rate.  `auto` now extracts a single cycle and TILES identical
  copies to reach the minimum length (perfectly periodic → no drift, no seam
  buzz).  `=N` still cuts N contiguous cycles for those who want the movement.
- **Sub-sample-accurate extraction (the harshness fix).**  The remaining
  "harshness" on short/high-note cycles (and the tiled pink noise) was traced —
  via the user's filter test (it lived above ~10 kHz) and an offline spectrum
  check — to a **fractional-sample phase step at the loop wrap**: a whole-sample
  cut of a fractional-period cycle leaves a "kink" that is proportionally huge on a
  60-frame cycle (tiny on a 475-frame one).  Fix: refine the period to sub-sample
  precision (parabolic interp of the autocorr peak) and resample exactly one period
  to integer frames.  Measured ~0.00 % energy > 10 kHz on the previously-harsh
  triangle/square loops afterward.
- **Aliasing is inherent to single cycles played up; multisampling cures it.**
  A bright single cycle transposed up the keyboard folds harmonics past Nyquist.
  The real fix is multisampled input (a cycle per source octave → each key barely
  transposes); real `.xpm`/`.sf2` multisamples get this for free.  (The SYS100
  construction-kit build originally mapped one cycle across all keys → aliased;
  rebuilding it as a per-octave multisample fixed it.)
- **Octave-fold-to-prior was TRIED and REVERTED.**  Forcing a harmonic/subharmonic
  lock back to the labeled octave regressed 45 → 356 low-confidence (it drags clean
  locks onto non-periodic points).  Some lo-fi textures (e.g. BoC "Annenberg" —
  dominated by a ~2 kHz partial with a weak fundamental) simply have no clean single
  cycle at their labeled pitch.  Accepted as a best-effort limitation.
- **`--split-velocity-layers` + single-cycle → near-duplicate presets.**  Single-
  cycle strips dynamics, so a pad's velocity layers collapse to the same oscillator.
  A build-time de-dupe (phase/pitch-invariant harmonic-magnitude fingerprint,
  cosine ≥ 0.99) removes them, but MUST be scoped **within each source patch**
  (group by preset name minus the `_L<n>` suffix) — a global compare falsely merges
  different instruments because many single cycles share low-harmonic spectra.
- **K2000 floppy path.**  Single-cycle multisamples need the KRZ headroom
  downsample (~24 kHz) or wide zones clamp on the K2000 up-pitch ceiling; then
  `write_krz` → FAT12 via `writers.fat12.format_new` → `.add_file`.  Scratchpad
  builders `build_sys100.py` / `build_synth_sc.py` show the full recipe (combine
  many XPMs → single-cycle → re-split zones by *detected* root → split-layers →
  de-dupe → E4B/ISO + KRZ/floppy).
- **`--single-cycle-dump-dir` WAV export (2026-07-12).**  The dump path
  (`single_cycle._dump_cycle` → `_wav_bytes_with_loop`) now emits a proper `smpl`
  chunk — one forward loop (`loop_start`/`loop_end`, inclusive) plus the MIDI
  unity note — under a descriptive `<sample>_<note>.wav` name, so the oscillators
  import into samplers we don't write presets for (loop + tuning intact). Field
  offsets mirror `xpm_parser._read_smpl_loop` / `_read_smpl_root`, so they
  round-trip back through our own importer.

---

## §KRZ-CWM — Fidelity gaps found via ConvertWithMoss cross-reference (2026-07-22)

TODO item: *"KRZ: fidelity gaps found via ConvertWithMoss cross-reference"*.
Source: a full byte-level diff of ConvertWithMoss's KurzFiler-derived
`format/kurzweil/*.java` against `writers/krz_writer.py`. Ordered easiest-first.

**Update 2026-07-27 — PR #232 changes the "nothing to learn on the program
side" conclusion below.** At the time of the original 2026-07-22 diff, CWM's
KRZ writer only emitted a flat default program. [PR #232](
https://github.com/git-moss/ConvertWithMoss/pull/232) (merged) adds real
program-side modulation handling:

- **Velocity(AttVel=100)→cutoff on the F1 filter page**, read+write, claimed
  round-trip-verified against a real K2000-saved FM-bass program. Their depth
  scale: `MAX_VELOCITY_MODULATION_CENTS = 9600` (8 octaves) — a candidate
  value for our own still-blocked "Modulation routings" depth calibration
  (see `TODO.md`, filter Src2=`HOB0[7]`; our own unconfirmed estimate there
  is a *different* number, ±10800 ct, sourced from the general F-page
  Src-Depth range in the manual rather than measured). Worth a disk-save
  cross-check of both numbers before trusting either — **not wired into
  `krz_writer.py`**, since this needs our own hardware confirmation, and it's
  unclear from the PR description alone whether their "one F1 modulation
  source" model maps directly onto the *two* independent slots our own RE
  documented (Src1=`HOB0[5]`/depth`[6]` for ENV2, Src2=`HOB0[7]` for
  velocity/mod-wheel) or whether real K2000 programs only ever populate one
  of the two at a time in practice.
- **Envelope "unused stage" semantics**: a K2000 envelope stage with *both*
  zero time and zero level is unused on the device and holds the previous
  stage's level, rather than decaying to silence — CWM's reader was treating
  it literally and producing silent FM-bass conversions. **Checked against
  our own writer, not applicable:** `writers/krz_writer.py._env_time_byte`
  floors every written time byte at `3` (`max(3, ...)`), so `_fill_env` never
  emits a literal on-disk time of `0` — the ambiguous (0-time, 0-level) case
  this PR fixes can't occur in mpc2emu's own output. It matters to a *reader*
  of third-party KRZ programs, which mpc2emu didn't have at the time this
  note was written — see §KRZ-READER below, which added exactly that.

  **UPDATE 2026-07-28: this bit us too, now that the reader exists.** A
  second CWM cross-check (post-#232 merge) found `krz_parser._decode_env`
  had the *exact same* bug the note above flagged as "not applicable" —
  applicable now that §KRZ-READER shipped a real reader after this note was
  written, and apparently missed in that work. Confirmed against the local
  201-file corpus: **30.6% of 7228 voices** read `sustain==0.0` before the
  fix (silent/held-forever presets), dropping to 1.6% after — a much larger
  real-world impact than CWM's own "FM bass" framing suggested. Fixed the
  same way: `seg[6]==0 and seg[7]==0` (raw decay bytes) → `sustain=1.0`
  (holds at the attack peak) instead of the literal `level/peak=0`. New
  regression test `test_decode_env_unused_decay_stage_holds_peak` in
  `tests/test_krz_roundtrip.py`. Full writeup in `docs/KRZ_FORMAT.md` §4.4.
  Not yet hardware-confirmed on a real K2000/K2000R.

### 1. Per-sample gain (`Soundfilehead.volumeAdjust`) — DONE + HW-CONFIRMED (2026-07-23)

`volumeAdjust` (Soundfilehead byte 2) and `altVolumeAdjust` (byte 3) are signed
i8 in **0.5 dB steps** (−64.0…+63.5 dB — the MISC-page "Volume Adjust"). We used
to write `0`. Now applied in `writers/krz_writer.py`:

```python
def _vol_adjust_byte(volume_db: float) -> int:
    return max(-128, min(127, round(volume_db * 2)))   # 0.5 dB steps, signed i8
```

Gain is per-zone in our model (`ZoneMapping.volume`, dB) but the header field is
per-sample, so `write_krz` aggregates the **mean** volume of every zone referencing
a sample into `sample_gain_db[name]` and passes it to `_write_sample_object`, which
packs `_vol_adjust_byte(gain) & 0xFF` into both volumeAdjust and altVolumeAdjust.
The common MPC case is 1 zone : 1 sample (exact); a sample shared by zones at
different levels averages (lossy, rare). **0 dB → 0**, so unity samples are
byte-identical and the HW-verified filter floppies are untouched.

**HW-confirmed on the K2000R (2026-07-23).** `tests/re_banks/gen_volume_adjust_test.py`
builds a constant-pitch `VOLADJ` floppy: three key-blocks playing the *same* 240 Hz
sine at unison, differing only in zone volume (0/−6/−12 dB → bytes 0/−12/−24). On
hardware each block stepped down in loudness exactly as intended → the K2000 honours
the field and the 0.5 dB/step scale is correct. (An initial 0/−12/−24 dB build had a
silent −24 dB block = below monitor level, plus an octave-label mismatch — the K2000
calls MIDI 60 "C3", our `_note_name` calls it "C4"; display-only, no byte impact.)

### 2. Partial key-tracking in the keymap entry `tuning` — needs a test source

`_build_keymap_entries` writes a **constant** per-zone `tuning` = `100·(R_sample −
R_zone) + fine_tune`, i.e. it assumes 100 % chromatic tracking (the K2000 does the
per-key transpose itself). To honour a source `key_tracking` (0..1, where 1 =
normal, 0 = drum/fixed pitch), make the tuning per-key:

```python
# per key `note` in the zone, instead of a constant offset:
tuning = round((key_tracking - 1.0) * (note - R_sample) * 100) + fine_tune
# key_tracking == 1.0 -> constant fine_tune (today's behaviour); == 0.0 -> fixed pitch
```

*Blocked on:* an input path that actually carries keytrack ≠ 1 (XPM/SFZ). Add the
plumbing only alongside a real source + HW drum-map check. Beware the existing
hole-fill and up-pitch-ceiling logic operate on the *constant* assumption — a
fixed-pitch (keytrack 0) map has no up-pitch problem, so gate the ceiling cap off
when `key_tracking == 0`.

### 3. Native 8-level multi-table keymap — larger, weigh vs current splitting

The keymap `Level[8]` field can point the 8 dynamic levels (velocity `j·16…+15`)
at up to 8 distinct entry tables inside **one** keymap:

```
Level[j] = (8 - j)*2 + tableIndex_for_level_j * (num_entries * entry_size)
tables laid out after the header: numTables x (entriesPerVel+1) x entrySize
```

CWM builds these from source velocity zones (`KurzweilCreator.calcBandOverlap` /
`setTableIndexOfLevel`, sharing a table across levels with identical content).
Adopting it would let `_split_voice_by_velocity` fold velocity bands back into one
keymap + **one** layer, relieving the 32-layer cap and the "3 regular layers"
spread. *Trade-off:* our current per-band split-layer approach is HW-verified; the
multi-table form is not. Decision + HW confirm required before touching a working
path — keep as a design item, not a drive-by change.

**Read side done (2026-07-27, §KRZ-READER below):** `parsers/krz_parser.py`
decodes native `Level[8]` multi-table keymaps (real third-party content uses
them — 15-30 keymaps in the local corpus, depending on how it's counted).
This item is about the *writer* still never emitting them; unaffected.

### 4. Stereo / multi-root sample objects — broader feature

We emit mono, single-`Soundfilehead` samples. The multi-header generalization
(also in `docs/KRZ_FORMAT.md` §3.1):

- `KSample.numHeaders = N − 1` (N headers); `flags` bit `0x01` = stereo, headers
  in L/R pairs, even index = left; keymap `subSample` references the **left** (odd:
  1,3,5…).
- each header's envelope offsets become `(numHeaders − 1 − i)·32 + 8` and `+6`
  (we hardcode `8`/`6`, valid only for the single/last header).

Gated behind general stereo support in the converter; HW confirm needed.

### 5. Doc-only reconciliations (no code change)

- **Object-type hash decode:** our unconditional `hash >> 10` mislabels objects
  with the `0x8000` bit clear (types > 42 use `hash >> 8`: 111 QA-bank / 112 song
  / 113 effect). We never emit them; only relevant if we add a reader. Documented
  in `docs/KRZ_FORMAT.md` §2.2.
- **Entry-index base:** CWM sounds entry `i` at MIDI note `i + 12` (`basePitch=0`,
  `BASE_NOTE=12`); we index entries by raw MIDI note. Ours is HW-confirmed to play
  correctly, so this only matters if an external reader (incl. CWM) reads our files
  — verify whether it sees our zones shifted +12 before assuming interop.

## §KRZ-READER — KRZ added as a source format (2026-07-27)

TODO item: *"KRZ was write-only; add it as an input format"* — prompted by
Jan asking how much effort it'd take, given ConvertWithMoss shipped a KRZ
reader in the preceding ~10 days partly credited to this project's own
hardware RE (see §KRZ-CWM above and `dea9dbb` in ConvertWithMoss).

**Done.** `parsers/krz_parser.py`, `parse_krz(path) -> Bank`, wired into
`parsers/registry.py` (`'.krz'`). Structural template: `parsers/e4b_parser.py`
(self-contained binary reader, in-memory PCM, numeric-id→name resolution,
per-object `try/except` + `[WARN]`, never fatal).

**Why cheaper than a normal new-format reader:** the container walk already
existed as a diagnostic tool (`tests/re_banks/krz_reader.py`, promoted into
the new module since `tests/` is gitignored and can't be imported from
shipping code) and was corpus-verified against 577 real files (zero
container/segment failures) *before* any model-building code was written.
The format is documented at byte level in `docs/KRZ_FORMAT.md`, and the DSP
decoders (filter/cutoff/resonance/envelopes) are inverses of encoders this
project already hardware-RE'd in `krz_writer.py` — this was mostly a
model-construction job, not a reverse-engineering one.

**Scope implemented, all in one pass** (the original 3-phase estimate
collapsed once the container proved solid):
- Samples: PCM extraction with BE→LE byteswap, loop points, per-sample gain
  (`Soundfilehead.volumeAdjust`), sample-rate reconstruction snapped to
  standard rates (see finding below).
- Keymaps: the full method bitfield (compacted keymaps, i8 tuning, per-entry
  volAdj — the writer only ever emits one variant, `0x13`; real content uses
  12 different ones, see corpus counts in the KRZ-as-source-format plan) and
  the native `Level[8]` multi-velocity-table mechanism the writer never uses.
- Programs: key/velocity geometry, filter type (many-to-one reverse map,
  same "canonical representative" approach as `e4b_parser.py`'s own filter
  table), cutoff/resonance, amp + filter envelopes (a *reducer*, not a strict
  inverse — see below), LFO1, and the AMPENV Natural-mode gate.
- Orphan recovery: keymaps no program references, and samples no keymap
  references, are recovered into synthetic presets rather than silently
  dropped (real pure sample-pool banks exist in the corpus).
- ROM/absent samples (K2000 built-in waveforms, ids < 200, no PCM in the
  file) are dropped with one summarized `[WARN]` per bank, never per-zone;
  an all-ROM program-only bank gets a plain `[INFO]` rather than looking
  like a parse failure.

**Corpus findings that shaped the design** (577 local `.KRZ` files,
`tools/krz_corpus_check.py`):

- **CAL keymap-slot resolves in mpc2emu's favor, not CWM's.** `CAL[7,8]` is
  the sole keymap-id carrier in **0 of 33,866** program layers; `CAL[11,12]`
  alone in 30,483; both set (disagreeing) in 948. CWM's `KurzweilProgram.java`
  reads `[7,8]` first, so it misreads those 948. `krz_parser.py` reads
  `CAL[11:13]` only, matching the writer and `docs/KRZ_FORMAT.md` §4.2. This
  **closes** doc-only reconciliation item 5 above (partially — the hash-decode
  half of that item is still open, we still don't emit type-28 FX objects so
  it doesn't bite our own output).
- **Entry-index base evidence favors mpc2emu's convention, not conclusively.**
  Root-inside-zone check over 8,010 multisample entry-runs: `note = i` 39.6%
  vs CWM's `note = i+12` 26.4%. Recorded in `docs/KRZ_FORMAT.md` §3.2 and
  `TODO.md`; **not** closed outright — wants an aural/HW check.
- **PCM-extent recovery needed a hard ceiling, found by testing against
  synthetic writer output, not the real corpus.** The first implementation
  floored the extent at `sampleEnd + 1`, reasoning `sampleEnd` is always
  inclusive-last-frame. That overshoots by one word whenever two samples are
  packed with zero gap (common for the writer's own tightly-packed output),
  silently stealing one PCM word from the next sample. Fixed by making the
  next sample's start (or PCM-region end) a hard ceiling the floor can never
  exceed, with loop points defensively clamped afterward. Caught by building
  `tests/test_krz_roundtrip.py`, not by the corpus sweep (which only flags
  invariant *violations*, and the original bug happened not to trip one for
  most files — 24 of 583 local files had visibly out-of-range loop points
  before the fix, all self-authored test/demo banks with tight packing).
- **Sample-rate snapping** — `samplePeriod` is an integer nanosecond value,
  so `1e9/period` doesn't invert exactly (a written 44100 Hz reads back as
  44099/44098 depending on rounding direction). Snapped to the nearest
  standard rate within ±2 Hz, matching ConvertWithMoss's approach.
- **Pre-existing writer bug found by actually round-tripping real content
  (KRZ→KRZ→KRZ, not just synthetic fixtures), 2026-07-27: the up-pitch
  ceiling was measured from the wrong root.** `_build_keymap_entries`
  computed `ceiling = _compute_max_pitch(sample.sample_rate, r_sample)`, using
  the sample's own physical `root_note` — but the hardware's actual total
  pitch shift at key `K` is `(K - r_sample)*100` [auto-transpose] `+ tuning`,
  and since `tuning = 100*(r_sample - r_zone) + fine_tune`, that total
  algebraically reduces to `(K - r_zone)*100 + fine_tune`. So the ceiling —
  which bounds how far *above the sample's actual playback rate* the K2000's
  48kHz internal engine can stretch it — must be measured from `r_zone`
  (`zone.root_key`), not `r_sample`. Whenever a zone deliberately retunes
  (`root_key != sample.root_note`), the old check mis-flagged perfectly safe
  assignments as over-ceiling and silently dropped the sample from the
  keymap. Found via a third-party `soundset 098` (`2000 Series v114`, "Lo Fi Kicks
  1"): a genuine drum map where each key gets its own sample at an
  independently chosen pitch (`entry.tuning` cancels the normal per-key
  auto-transpose entirely) — parsed correctly by `krz_parser.py`, but
  re-encoding that Bank back to KRZ dropped 4 of the kit's 45 samples, which
  the reader then correctly (if confusingly) recovered as an orphan preset on
  the next parse, one new orphan compounding with every generation. **This
  bug was not specific to KRZ-sourced content** — any source format producing
  a deliberately retuned zone (`root_key != root_note`) would have hit it when
  converting *to* KRZ. Fixed by measuring the ceiling from `r_zone`
  (`writers/krz_writer.py:392`). Verified: `soundset 098` is now stable
  gen1→gen2→gen3 (`Lo Fi Kicks 1`, 45 samples, no orphan preset); the existing
  HW-confirmed `tests/test_krz_writer.py` suite is unaffected (its fixtures
  never exercise `root_key != root_note`, so `r_zone == r_sample` there and
  the fix is a no-op for every case that was already HW-verified).

**Known remaining limitation (not fixed, documented 2026-07-27): `_coverage_
remap_voices` / `_voices_stacked` are not idempotent across repeated KRZ→KRZ→
KRZ generations.** `tools/krz_to_krz_check.py` (parse → write → parse → write
→ parse, 3 generations) found 10 of 593 local files where gen2→gen3 zone/
preset counts drift — all of them this project's own synthetic multi-voice
octave-slice pad-stack test/demo banks (`JRSLO*`, `K2KFEATDEMO*`,
`krz_staging/VPO_BRASSACC|BRASSNOR|VIOLINKS`, `SCSYNTH_01`), **zero real
commercial-library files** (all 12 third-party soundset files that were unstable before
the ceiling fix are now stable). Root cause: `_coverage_remap_voices` (§7.3's
already-documented lossy octave-slice rebuild) regroups samples by root
differently when applied a second time to its own previous output, so a
second re-encode can leave a different subset of samples referenced by no
keymap; `krz_parser.py`'s orphan recovery correctly rescues them each time,
but that means a new tiny recovery preset can appear every generation instead
of the set settling. Not chased further: a real user's KRZ→other-format
conversion only round-trips through the writer once, so this only bites
KRZ→KRZ→KRZ chains of this specific stacked-pad content, and doesn't affect
any real library found in the local corpus. Would need `_coverage_remap_
voices` made idempotent (or gated off on Bank input that is *already* a
coverage-remap's own output) to close for good.

**CR-21 two real crash bugs found via VinSamLib re-processing real
commercial content — DONE 2026-07-27.** VinSamLib's own black-box testing
of "reprocess an existing KRZ preset through mpc2emu" (parse → optionally
resample/reduce → write back) against a real a commercial soundset file
crashed with `struct.error: pack_into requires a buffer of at least 645
bytes for packing 5 bytes at offset 640 (actual buffer size is 640)` at
`writers/krz_writer.py._build_keymap_entries`, raised from
`_write_keymap_object`. This looked at first like it might invalidate the
idempotency entry's "zero real commercial files affected" conclusion (a
ONE-pass crash, not a multi-generation drift) — turned out to be two
separate, independent bugs:

1. **`parsers/krz_parser.py` fabricated a phantom 0-length `SampleData`.**
   The repro file is `.../a commercial two-disk soundset/<soundset>/Disk1/
   its first disk` — a multi-disk soundset. Two of its sample headers
   (`Prodigy ShortBas`, `Sprinkle`) have `has_data=True` (flags bit 0x40
   set) but a `sampleStart` word offset (783170) that lies entirely
   outside *this file's* own PCM region (690058 words) — the sample's
   real PCM is on a different disk in the set, not present here. The old
   `_extract_pcm` sliced `data[start_byte:end_byte]` with `start_byte`
   past `len(data)`, which Python silently returns as an empty `bytes`
   object rather than raising — so a 0-length `SampleData` got created
   and fed downstream instead of being treated as unavailable. Fixed:
   `_get_sample` now checks `h.start_w >= pcm_words` and treats it exactly
   like ROM/absent (same `n_rom` counter, same summarized `[WARN]`,
   `used_sample_ids` still marked so it isn't ALSO offered to orphan-sample
   recovery).
2. **`_coverage_remap_voices` had no upper clamp on `hi_key`.** Once (1)'s
   phantom sample was excluded, the specific reported preset ("Phase
   Dist") no longer had any zones at all and stopped reaching
   `_coverage_remap_voices` — but the buffer-overflow mechanism itself is
   a real, separate, general bug independent of phantom data. The function
   computes `zz.hi_key = max(lo, ceil)` where `ceil =
   _compute_max_pitch(sample_rate, root) // 100` — a per-root up-pitch
   ceiling that is **not otherwise bounded**, unlike
   `_build_keymap_entries`'s own zone-level ceiling check (`hi_key =
   min(zone.hi_key, ceiling)`, which can only ever *reduce* `hi_key` below
   a well-formed zone's own value). A legitimate high `root_note` combined
   with a low sample rate pushes `ceil` past 127 (e.g. root=127 @ 8000 Hz
   → ceil=158), and the resulting `hi_key >= 128` overflows the fixed
   `bytearray(NUM_KEYS * KEYMAP_ENTRY_SIZE)` = 640-byte keymap-entries
   buffer at exactly `key=128` → `offset=640` — matching VinSamLib's error
   message byte-for-byte. **Reproduced independently with plain synthetic
   data** (3 samples at roots 40/70/127, all at 8000 Hz, no phantom/corrupt
   data involved) — confirmed the OLD code crashes with the identical
   message, confirming this is the true general mechanism, not merely a
   symptom of (1). Fixed by clamping `zz.hi_key = min(NUM_KEYS - 1,
   max(lo, ceil))`, plus a matching defensive clamp on the zone-level path
   in `_build_keymap_entries` (`hi_key = min(zone.hi_key, NUM_KEYS - 1)`
   before the ceiling `min()`, cheap insurance now that this writer is
   exposed to arbitrary third-party content via `krz_parser.py` rather
   than only MPC-sourced conversions).

Verified: `tests/test_krz_writer.py::test_coverage_remap_ceiling_overflow`
(the synthetic repro, asserting no `struct.error`); the exact real-world
preset no longer crashes and the file's other 53 presets parse/write
cleanly; full 589-file local corpus sweep and 3-generation KRZ→KRZ→KRZ
sweep both show **zero exceptions** (the idempotency drift above is
unrelated and unchanged at the same 10-file count).
- **`filter_cutoff` is not a shared frequency scale**, confirmed while writing
  `tests/test_krz_roundtrip.py`: the KRZ writer maps 0..1 onto a *linear
  semitone* scale (`_cutoff_byte`), while the reader decodes through E4B's
  *log-Hz* scale (`hz_to_e4b_cutoff`, for consistency with every other
  parser). Both are internally correct; they're just different curves, so a
  round-tripped cutoff value legitimately doesn't come back unchanged. A
  follow-up (not done here) would route `_cutoff_byte` through Hz too,
  making writer and parser exact inverses.

**Shared codecs moved to `models/common.py`** (the CR-13/CR-18 pattern —
single home for writer+parser math instead of "kept in sync by comment"):
`krz_cutoff_byte_to_hz`, `krz_reson_byte_to_01`, `krz_env_byte_to_seconds`,
`KRZ_ENV_TIME_GRID`, `KRZ_RELEASE_FACTOR`. `writers/krz_writer.py` now
imports these instead of keeping its own copies.

**Verification:** `tests/test_krz_roundtrip.py` (write_krz → parse_krz,
geometry + DSP, deliberately dodging three writer-side structural rewrites —
hole-filling, layer-capping, the up-pitch ceiling — that would fail a naive
round-trip for the wrong reason); `tools/krz_corpus_check.py` (584 local
files, zero exceptions, model invariants); `tests/test_krz_writer.py`'s
`test_write_read_roundtrip`/`test_sample_gain` rewritten to call `parse_krz`
directly instead of shelling out to the old reader and regex-scraping stdout
— this rewrite is what surfaced a **pre-existing, previously-uncaught writer/
fixture issue**: both tests' fixtures assigned zones to key ranges beyond
their sample's up-pitch ceiling (root+1 semitone at 44.1kHz), which the
writer correctly refuses (delete-lockup avoidance), silently leaving that
voice's keymap empty — invisible to the old byte-regex assertions, which
never checked keymap sample-id fidelity. Fixed by giving each test fixture's
samples a `root_note` that covers their widest assigned zone.

`tests/re_banks/krz_reader.py` reduced to a thin CLI pretty-printer importing
the container walk from `parsers/krz_parser.py`, with the same `CAL[7,8]` bug
fixed in its display code.

## §CWM19 — Input-parser feature-parity gaps found via ConvertWithMoss 19.1.0 (2026-07-25)

TODO item: *"Input-parser feature-parity gaps found via ConvertWithMoss 19.1.0"*.
Source: [ConvertWithMoss 19.1.0 release notes](https://github.com/git-moss/ConvertWithMoss/releases/tag/19.1.0)
(`documentation/CHANGELOG.md` in `~/git-repos/ConvertWithMoss`, tag `19.1.0`,
commit `6765c11`), read against our own `parsers/exs24_parser.py`,
`parsers/sfz_parser.py`, `parsers/talsmpl_parser.py`, `parsers/sf2_parser.py`,
`parsers/gig_parser.py` (all independent reimplementations — no CWM code copied,
see file headers).

### Fixes in 19.1.0 checked and confirmed NOT applicable (already correct here)

- **EXS24 group panning read as unsigned/unscaled** (CWM: *Logic EXS24 — Fixed:
  The panning of a group was read as an unsigned value and was not scaled*). We
  don't parse group-level pan at all yet (see gap list below) — only zone-level
  pan, which is already signed and scaled correctly: `exs24_parser.py:705`
  (`pan = z['pan'] / 63.0`, `i8` read at `:576`).
- **TAL reverse flag parsed as text bool instead of numeric** (CWM: *TAL Sampler
  — Fixed: the sample "reverse" flag ... is stored numerically (0/1) ... but was
  parsed as a true/false text boolean*). Ours already reads it numerically:
  `talsmpl_parser.py:413` (`ms.get('reverse', '0') not in ('0', '0.0')`).
- **TAL "disabled groups" only skipped for `enabled="0"`, not `"false"`** (CWM:
  same fix text as the DecentSampler one, applied to TAL Sampler too). Doesn't
  map cleanly onto our model: TAL's `sampleenabled{a-d}` is the 4-*layer*-slot
  enable within one program (not a DecentSampler-style alternate-kit group), and
  our corpus-verified format notes (`talsmpl_parser.py:71`, 1706-preset survey)
  say TAL only ever writes `"0"`/`"1"` for these flags, never `"false"`. Already
  numeric-checked correctly at `:357`.
- **SFZ velocity range grown from the crossfade opcodes** (CWM: *SFZ — Fixed:
  The velocity range was taken from the cross-fade opcodes, so it grew by the
  width of the cross-fade with every conversion*). Ours reads `lovel`/`hivel`
  directly (`sfz_parser.py:437-438`) and only *checks for the presence of*
  `xfin_lovel`/`xfin_hivel`/`xfout_lovel`/`xfout_hivel` as a separate flag
  (`:358-359`) — never reads the range from them.
- **"Two filters differing only in their cutoff envelope treated as equal"**
  (CWM: generic backend fix — could merge non-identical zones). We have no
  zone-dedup / filter-equality-merge logic anywhere in the parsers, so this
  failure mode can't occur.

### Confirmed input-parser feature-parity gaps (not bugs — CWM extracts these, we don't yet)

Ordered by rough usefulness; none are blocking anything, pick up independently:

1. **EXS24 group-level volume/pan/tune offsets.** CWM 19.1.0 *New: Added support
   for group volume, panning and tuning offsets* (Kontakt, DecentSampler, Logic
   EXS24, Synclavier, TX16Wx, Waldorf Quantum/Iridium). We parse the EXS24 group
   struct only for names (`exs24_parser.py` GROUP_V11, used for L/R stereo dedup,
   see `:328-359`) and per-group envelopes (`:682-684`) — group pan/volume/tune
   fields are never read, so a group-level offset is silently dropped (zones keep
   only their own pan/volume/tune).
2. **EXS24 Velocity → Filter Cutoff modulation.** CWM 19.1.0 *New: Implemented
   Velocity -> Filter Cutoff Modulation (read/write)*. We read filter *keytrack*
   (`exs24_parser.py:155,219-223`, itself unverified-scaling / no corpus example)
   but nothing for a velocity→cutoff cord.
3. **EXS24 one-shot playback flag (ignore note-off).** CWM 19.1.0 *New: Added
   support for the one-shot playback mode* (EXS24 among ~15 formats). We have no
   EXS24 field read for this — the only "oneshot" string in the file is an
   unrelated audio-folder-name heuristic (`exs24_parser.py:387`, sample-file path
   resolution, not a preset flag).
4. **Choke / exclusive groups.** CWM 19.1.0 *New: Added support for exclusive
   ('choke') groups* (EXS24 and SF2 among the formats we read; also Kontakt/DLS/
   MPC1000/MPC60/Renoise/MV-8000/TAL — formats we don't read). Not present in
   `parsers/exs24_parser.py` or `parsers/sf2_parser.py`, and no `Preset`/`Zone`
   model field to hold it yet either.
5. **Amplitude keyboard-tracking.** CWM 19.1.0 *New: Added support for amplitude
   keyboard-tracking* (Akai S1000, DLS, Logic EXS24, Roland MV-8000/S-7xx, SFZ,
   Synthstrom Deluge, Yamaha YSFC — EXS24 and SFZ are ours). We support *filter*
   keytrack but not amp keytrack in either parser.
6. **Envelope time keyboard-/velocity-scaling.** CWM 19.1.0 *New: Added support
   for envelope time keyboard- and velocity-scaling* (Akai S1000, Ensoniq EPS/
   ASR/Mirage, Logic EXS24, Reason NN-XT, Roland S-7xx, SoundFont 2, Yamaha YSFC
   — EXS24 and SF2 are ours). Distinct from the envelope-slope ("curvature")
   support we already have; this scales the *time* by key/velocity.
7. **Per-instrument voice settings (polyphony, mono legato).** CWM 19.1.0 *New:
   Added support for per-instrument voice settings* (Akai S1000, DecentSampler,
   Disting EX, Ensoniq Mirage, Logic EXS24, Reason NN-XT, Roland S-7xx, SFZ,
   Synthstrom Deluge, TAL Sampler — EXS24, SFZ, TAL are ours). No polyphony/
   legato field read by any of our parsers.
8. **Random play logic (vs. round-robin).** CWM 19.1.0 *New: Added support for a
   random play logic next to round-robin* (Ableton, Akai MPC, DecentSampler,
   Logic EXS24, Renoise, Yamaha YSFC — EXS24 is ours; falls back to round-robin
   when a format can't express it). Not distinguished from round-robin in
   `exs24_parser.py` today.

### Not relevant

- Roland ZEN-Core SVZ embedded-WAV fix, Waldorf Quantum/Iridium fixes, Elektron
  Tonverk / Reason NN-XT / Omnisphere / Deluge / Disting EX / Polyend / Bliss /
  1010music / TX16Wx fixes, and the new Kurzweil K2000/K2500/K2600 **reader** —
  none are formats/directions we read or write (we *write* KRZ, CWM's new K2000
  support is a *reader*; no overlap to exploit).

---

## §E4BREAD — E4B reading gaps found via ConvertWithMoss's independent E4B reader (FIXED 2026-07-26)

**Context:** `parsers/e4b_parser.parse_e4b` is registered as an input format
(`parsers/registry.py`) — not just this project's own round-trip validation
oracle — because the sibling `VinSamLib` project (a librarian GUI built on
top of mpc2emu) reads real third-party/commercial `.e4b` files through it.
Cross-referencing ConvertWithMoss's independent E4B reader (PR #220,
`format/emu/emulator4/Emulator4Detector.java`) surfaced two real gaps in that
reading path — both now fixed.

### 1. Zone key/velocity range not intersected with the voice-level window

**Symptom:** many real hardware/commercial presets leave a voice's *zone*
entry wide open at 0-127 (key and velocity) and do the actual split at the
*voice* level instead (`vpar[14]`/`[17]` key, `vpar[18]`/`[21]` velocity —
see `docs/E4B_FORMAT.md` §4.1, hardware-RE'd 2026-06-14). `_parse_voice` read
`lo_key`/`hi_key`/`lo_vel`/`hi_vel` straight from the zone entry only and
never consulted the voice window, so such a voice's sample mapped across the
whole keyboard/velocity range instead of its real one.

**Fix** (`parsers/e4b_parser.py`, in the zone loop of `_parse_voice`):
intersect each zone's range with the voice window —
`lo_key=max(vpar[14], entry.lo_key)`, `hi_key=min(vpar[17], entry.hi_key)`,
same pattern for velocity. If the intersection is empty (`lo > hi`), the zone
is dropped rather than emitting an inverted range (mirrors CWM's own
early-exit — commit `ead0e07`, cross-referenced against 76057 real zones from
the commercial library CD-ROMs).

**Why this is safe for mpc2emu's own output:** `writers/e4b_writer.py`
(`_build_voice`) always sets the voice window to the min/max of the voice's
*own* zones, so the intersection is a no-op there by construction — verified
with a synthetic multi-zone round-trip (two zones, disjoint key ranges,
unaffected after the fix). Only third-party-authored files where a zone is
genuinely wider than the voice window are affected.

### 2. `loop_end_l` off-by-one

**Symptom:** CWM's reader (commit `2ccefea`) found the on-disk `loop_end_l`
field stores the frame *before* the true last loop frame, not the true last
frame itself — measured empirically by checking the PCM amplitude step at the
loop seam across a real commercial corpus: reading the raw value directly
left many seams with a step over a third of peak amplitude; adding `+1`
(capped at `numFrames−1`) eliminated all of those and raised the clean-seam
share from 78% to 95%.

Our own `parsers/e4b_parser.py`/`writers/e4b_writer.py` pair previously
treated the on-disk value as `loop_end` directly — an exact inverse of each
other, so our own write→parse round-trip was unaffected by this convention
either way, but reading a **third-party** file's loop point through
`e4b_parser` alone would land one frame short of the model's documented
"inclusive last loop frame" convention (`processors/loop_renderer.py`).

**Fix:** both sides updated together, keeping them exact inverses —
- `writers/e4b_writer.py._build_sample_header`: `lel = (loop_end - 1) * 2 + STRUCT_SZ`
- `parsers/e4b_parser.py._parse_sample_body`: `loop_end = min((loop_end_l - STRUCT_SZ) // 2 + 1, n_frames - 1)`

Verified: (a) mpc2emu's own write→parse round-trip is still an exact identity
(loop_end in == loop_end out); (b) the on-disk byte now encodes `loop_end - 1`
as expected; (c) `test_pipeline.py`'s existing PINGPONG round-trip and
`tests/test_krz_writer.py` (9 tests) still pass.

**Hardware-confirmed 2026-07-28** via `tests/re_banks/gen_hw_confirm_batch.py`
— a 100 Hz sine looped over exactly 20 whole periods (44.1 kHz → 441
samples/cycle, an exact integer, so any 1-frame loop-point error would
introduce a phase discontinuity right at the seam), held for 9s (~45 loop
repeats) on the real E4XT and recorded. Checked the actual waveform at
every loop-boundary crossing directly (not just by ear): the
sample-to-sample delta there (0.0011–0.0018) was *smaller* than the
typical mid-cycle delta elsewhere in the same recording (0.0083) — no
discontinuity, a clean seamless loop with the fix applied.

## §E4BREAD2 — Two more E4B reading gaps found via ConvertWithMoss PR #242 (FIXED 2026-07-28)

**Context:** ConvertWithMoss PR #242 (independent E4B reader, commit
`054972c7`) made two more claims about `Emulator4Detector.java` that this
project's own `documentation/design/E4B_FORMAT.md` (their doc, built partly
from mpc2emu's own RE work) had gotten wrong. Per the standing project rule,
both were checked against real local third-party `.e4b` content **before**
touching any code — see the corpus numbers below. Both turned out to be real,
independent of CWM's own corpus.

### 1. Amp/filter envelope: only stage 1 of each pair was read

**Symptom:** the 6-stage PZT (Attack1/Attack2/Decay1/Decay2/Release1/
Release2, bytes 0-11 amp / 14-25 filter) had only stage 1 of each pair read
(`_fenv_rate_inv(pzt[0])` for attack, `pzt[4]` for decay, `pzt[8]` for
release, `pzt[5]`'s LEVEL for sustain) since CR-5 (2026-06-10). CWM's PR
claims this is the same envelope as the Emulator X, and that decay1 is
frequently a *plateau* (holds at attack2's peak) with the real decay-to-
sustain motion happening in decay2 alone — reading decay1's level as
"sustain" makes a voice that should decay over many seconds instead "sustain
forever" at (near-)full volume, matching the classic "Nylon Guitar" bug
class (a plucked instrument that rings and fades vs. one that holds the pick
attack's level indefinitely).

**Corpus-checked before fixing** (141 local third-party `.e4b` files,
32,558 voices): stage-2 has a nonzero *time* in only ~1-2% of voices
(attack2 1.1%, decay2 1.6%, release2 0.2% — usually negligible on its own),
but where decay1's and decay2's *levels* differ sharply (0.9% of voices,
`|Δ| >= 50` out of 127), it's concentrated in one-shot SFX material: every
sampled example came from one `a commercial SFX` sound-effects bank
(`WALKER C1`, `DARTH VADER`, `LASER`, `X-WING`, …) where decay1 = byte 126
(near-full, ~31ms — read alone as "sustain at 99%") and decay2 = byte 118
(the *real* ~29.4 SECOND decay to silence). Old read: `attack=0.031 decay=
0.031 sustain=0.992 release=4.6`. Real envelope per the raw bytes:
`attack=5.8 decay=29.5 sustain=0.0 release=4.6` — a completely different,
audible envelope shape.

**Fix** (`parsers/e4b_parser.py`, both amp and filter envelope decode): sum
both stages' TIMES per pair (`attack = attack1_s + attack2_s`, same for
decay/release) and read **sustain from decay2's level**, not decay1's. For
mpc2emu's 4-stage `Envelope` model (no separate hold field), this is
provably equivalent to CWM's hold+decay split regardless of whether decay1
is a true plateau: `hold + decay = (plateau ? d1_time : 0) + (plateau ?
d2_time : d1_time+d2_time) = d1_time + d2_time` either way — so no plateau
detection is actually needed for our model, just an unconditional sum.
A stage-2 rate byte of exactly `0` contributes **true zero** seconds, not
the continuous rate curve's ~31ms floor (`env_rate_to_seconds(0) == 0.031`,
but `writers/e4b_writer.py`'s `env_seconds_to_rate(0.0) == 0` — byte 0 is a
deliberate "unused" encoding) — this keeps the ~98%+ of voices with a real
single-stage envelope byte-for-byte unchanged from the original CR-5
behavior; only genuine two-stage envelopes are affected.

**Verified:** corpus sweep before/after shows **0 crashes**, the exact
"the SFX bank" repro now decodes to the envelope above; new regression tests
`tests/test_e4b_parser.py::test_single_stage_envelope_unchanged` (the common
case, unaffected), `test_two_stage_envelope_combines` (synthetic two-stage
case matching CWM's model), `test_stage2_zero_byte_contributes_true_zero`,
`test_real_world_sfx-bank_sfx_repro` (exact byte repro) — all 4 confirmed to
fail against the pre-fix code and pass with it.

**HARDWARE-CONFIRMED 2026-07-28.** Built a listen-control bank
(`tests/re_banks/gen_e4bread2_listen_test.py`) that patches the *exact* raw
WALKER C1 PZT bytes (Attack1 0/127, Attack2 0/127, Decay1 0/126, Decay2
118/0, Release1 60/0, Release2 0/0) onto a plain 40s held sine tone —
bypassing mpc2emu's own parser entirely, so this tests the E4XT's actual
hardware behavior with zero dependency on whether our fix is right.
Loaded via a ZuluSCSI CD image (`writers/iso_builder.build_iso`) and played
on a real E4XT: **the tone genuinely fades to silence** over the held note
(matching the NEW decay≈29.5s/sustain=0.0 reading), not "holds near-full
forever" (the old, buggy reading). Fix confirmed correct on real hardware —
closing the open TODO item.

### 2. Sample loop fields: right-channel-only samples read the wrong (stale) field

**Symptom:** the E4B sample struct is the Emulator III's, which stores every
position (start/end/loop-start/loop-end) **twice** — once per channel, at
offsets 22/30/38/46 (left) and 26/34/42/50 (right). A sample object holding
only its **right** channel (options bit `0x0020` clear) keeps its real
positions in the second field of each pair and leaves the first with a stale
value that doesn't address this sample at all. `parsers/e4b_parser.py`
always read the left/first field unconditionally.

**Corpus-checked before fixing:** of 7,460 sample objects across the same
141 files, 88 (1.2%) have the option-clear ("right channel") flag, 73 of
those are looped. Reading the **left** field gives an in-range loop point
for 67/73 (91.8%) — but for the other 6 (all in a a preview bank),
it's **negative** (e.g. `loop_start = -40`), an outright invalid value that
can't be right by construction. Reading the **right** field instead gives a
valid, in-range loop point for **all 73/73 (100%)**.

**Fix:** `_parse_sample_body` now picks the loop-field offset based on the
options bit: `38/46` when bit `0x0020` is set (left/mono — the overwhelming
majority, and everything mpc2emu's own writer ever emits), `42/50` when
clear (right-channel-only). The now-unused `end`/`end_l` field (read but
never actually consulted anywhere in the parser — `n_frames` comes from the
PCM length, not this field) was removed rather than also branched, since
nothing reads it.

**Verified:** full corpus re-check after the fix: **0 invalid loop points**
across all 7,460 samples (down from 6). New regression tests
`tests/test_e4b_parser.py::test_stereo_right_channel_loop_fields` (exact
repro: a deliberately-stale negative left field vs. a valid right field) and
`test_stereo_left_channel_loop_fields_unchanged` (confirms the overwhelmingly
common left/mono case is untouched) — both confirmed to fail against the
pre-fix code and pass with it.

**Not related to full stereo support** — mpc2emu's `SampleData`/parser
remain mono-only by design (each E3S1 chunk is still read as one independent
mono sample); this fix only corrects which loop-point *field* is trusted for
a mono-per-object sample, it doesn't add channel-pairing/joining.

## §E4BLEVEL — Amp-envelope sustain LEVEL byte is exponential/dB-law on real hardware — WRITER FIXED + HW-CONFIRMED (2026-07-28)

**Context:** while building the §E4BREAD2 listen-control bank above, a
second calibration reference preset ("SIMPLE REF") was included: an
ordinary envelope through the normal write path, `Envelope(attack=0.5,
decay=2.0, sustain=0.5, release=1.0)`. `models/common.py:env_level_to_byte`
encodes the 0.5 sustain fraction **linearly**: `pct=50 -> round(50*127/100)
= byte 64`, and the parser's inverse (`env_byte_to_level`) reads byte 64
back as `0.504` — self-consistent in software, confirmed by round-tripping
the written file through `parse_e4b` before the hardware test.

**Symptom (hardware-observed):** on a real E4XT, this preset's sustained
portion (after the 0.5s attack, in the middle of the 2s decay-then-hold) was
audible but far quieter than "half volume" — the listener had to raise the
E4XT's own output volume knob from ~45% to 100% (more than doubling the
gain) to hear the sustain clearly. A linear amplitude ratio of 0.5 is only
about −6 dB, which should not require anywhere near a 2x+ gain boost to
become clearly audible.

**Hypothesis:** the EOS envelope LEVEL byte (0-127, used for every
non-terminal stage target — Decay1's level *as read by the old, pre-E4BREAD2
parser*, and both Decay1/Decay2 sustain targets under the new one) likely
does not map linearly onto output amplitude the way `env_level_to_byte`
assumes. Plausible explanations, most likely first:
  - The byte feeds an exponential/dB-law VCA stage internally (common in
    envelope-generator hardware — a linear control value produces an
    exponential *voltage* response), so "50% of the level byte range" is a
    much larger attenuation in dB than 50% of linear amplitude would be.
  - The level scale is itself already a dB or other non-linear percentage
    in the EOS UI, and `env_level_to_byte`'s straight `pct * 127/100` is
    the wrong codec for anything except the two endpoints (0% and 100%,
    which are unaffected either way — this is why every other envelope
    stage in the writer that targets "full" or "silence" is unaffected;
    only genuine partial-sustain presets would sound wrong).

**Scope:** every E4B preset mpc2emu writes with a sustain level strictly
between 0% and 100% is potentially affected — this is a writer-side
calibration gap, independent of the §E4BREAD2 parser fix above (which reads
existing third-party bytes; this is about what byte value we *write* for a
given intended sustain fraction). Filter-envelope sustain uses the same
`_fenv_level` codec and would carry the same risk if `filter_env_amount` is
ever turned up (currently written inert/amount-0 by default, so not
audible today, but the byte would still be wrong if that changes).

**MEASURED 2026-07-28.** Live SysEx parameter-edit automation was tried
first (`tests/re_banks/run_amp_level_cal_sweep.py`, via the sibling
`../eosed` project) and abandoned after three rounds of incoherent,
non-monotonic results plus one device crash — see the "live automation"
TODO entry and `../eosed/docs/RESOLUTION_NOTES.md` §14/§15. Switched to
a **file-based bank** instead: `tests/re_banks/gen_amp_level_cal.py` builds
`AMPLVLCAL.E4B`, one preset with 9 voices, each covering exactly one key
(MIDI 48-56) with `Envelope(attack=0.01, decay=0.15, sustain=i/8, release=
0.3)` for `i=0..8` — i.e. the *normal* write path (same mechanism that
already HW-confirmed the §E4BREAD2 fix cleanly, no live parameter edits at
all). Loaded via a ZuluSCSI CD image exactly like the §E4BREAD2 listen
bank; played back with plain Note On/Off (`tests/re_banks/
play_amp_level_cal_notes.py`, MIDI only, no SysEx) while recording
`system:capture_15/16` (the E4XT's audio-in feed) via `ffmpeg -f jack`.

Measured plateau level per note, in dB relative to that note's own attack
peak (`analyze_envelope_recording.py --mode level --fixed-hold 2.3` — the
`--fixed-hold` option was added because the quiet notes fall below the
note-segmenter's gate before the actual note-off, so the plateau window
must be taken from a known fixed duration after the peak, not from the
gate-detected region end):

First pass used broadband RMS and pinned the bottom 3 points (0/12.5/25%)
at an identical -55.4 dB floor — re-checked by re-recording the same bank
at 75% hardware output volume (up from ~50%): the low points got **more**
negative (-67.7 dB), not less, which is the signature of a fixed recording
noise floor (interface self-noise) becoming relatively quieter as the
signal-carrying peak grows with output volume — i.e. those 3 points were
below the recording chain's broadband noise floor, not real measurements,
and the volume knob can't fix that (broadband noise floor is independent
of it, self-normalized dB-to-peak measurement cancels out any actual gain
change).

**Fixed by switching to a narrowband measurement** at the test tone's own
220 Hz (`analyze envelope via FFT bandpass ±15 Hz around 220 Hz`, using a
long ~1.9s window for good frequency resolution, referenced against the
100%-target note's own plateau rather than each note's short attack
transient) — this rejects broadband hiss outside the tone's own frequency
and recovered clean, monotonic data all the way down to 0%:

| target% | measured dB | measured% (linear) |
|--------:|------------:|--------------------:|
|     0.0 |     -99.73  |  0.001 |
|    12.5 |     -90.27  |  0.003 |
|    25.0 |     -70.61  |  0.029 |
|    37.5 |     -58.55  |  0.118 |
|    50.0 |     -46.49  |  0.474 |
|    62.5 |     -35.20  |  1.737 |
|    75.0 |     -23.11  |  6.992 |
|    87.5 |     -10.22  | 30.847 |
|   100.0 |       0.00  |100.000 (reference) |

All 9 points fit a straight line in dB (i.e. the byte really is
exponential/dB-law in amplitude, confirming the hypothesis above)
extremely well:

**`measured_dB ≈ 1.010 × target_pct − 98.74`** (least-squares fit over all
9 points, `R² = 0.996`; fitting only the 25-100% subset tightens further
to `dB ≈ 0.948×pct − 94.15`, `R² = 0.9996` — both describe essentially the
same curve, and either is usable for a fix). This **supersedes** the
first-pass partial fit above (`0.846×pct − 84.13`) — same shape, corrected
slope/intercept now that the low end is real data instead of noise floor.

**Implied fix**, not yet applied — inverting the fit to solve for the byte
value (0-100 sustain%) that a **linear** intended amplitude fraction
`frac` (0.0-1.0) should actually be written as:
`sustain_pct = (20*log10(frac) + 98.74) / 1.010`. Sanity check: `frac=1.0`
→ 100.0% (exact, by construction — it's the reference point);
**`frac=0.5` → 92.9%** (not 50% — confirms the "half volume" bug's
magnitude: to sound like true half-amplitude, the written byte needs to be
~93%, not 50%); `frac=0.1` (−20 dB) → 78.0%; `frac=0.01` (−40 dB) → 58.2%.
This would replace `env_level_to_byte`/`env_byte_to_level` in
`models/common.py` for the **amplitude-envelope sustain field only** — NOT
the rate fields (already separately calibrated and confirmed correct), and
NOT necessarily the filter-envelope sustain (same codec today, but filter
env is written inert/amount-0 by default — needs its own decision, see
Scope above).

**Not yet decided: whether/how to apply this to the parser too.** The
writer-fix question (what byte to WRITE for an intended fraction) is
separate from whether the PARSER's `env_byte_to_level` (used to interpret
third-party E4B files' *existing* sustain bytes) should also switch to this
curve — that would change how mpc2emu interprets every third-party preset's
sustain level, a much bigger blast radius than fixing our own writer.
Needs a decision before implementing, not just a formula.

**HARDWARE-CONFIRMED 2026-07-28.** `models/common.py:env_sustain_to_byte()`
implements the inverted-fit formula above (both endpoints special-cased to
exact byte 0/127); `writers/e4b_writer.py`'s amp-envelope sustain encoding
now calls it. Built `tests/re_banks/gen_hw_confirm_batch.py` ->
`HWCONFIRM.E4B`, 5 keys (48-52) at sustain 0/25/50/75/100% through the
*normal* (now-fixed) writer path, played and recorded on the real E4XT,
narrowband-measured against the 100% key's own plateau:

| target% | measured% |
|--------:|----------:|
|     0.0 |      0.0  |
|    25.0 |     22.7  |
|    50.0 |     45.6  |
|    75.0 |     67.3  |
|   100.0 |    100.0  |

Approximately linear, night-and-day from the pre-fix measurement (a
"linear 50%" target used to measure at 0.47% actual amplitude — see the
measurement above). Small residual deviations (25→22.7, 50→45.6, 75→67.3,
all slightly under target) are consistent with the calibration curve's own
~2 dB fit residual, not evidence the fix is broken. Writer-side fix closed;
the parser-scope and filter-envelope-scope questions above remain open by
deliberate choice, not oversight.

---

## §E4BPARAMHUNT — Live-SysEx parameter hunting: a new, fast method for finding unknown `vpar` bytes (2026-07-28)

**Context:** while chasing the `E4_VOICE_VOLENV_DEPTH` byte for §E4BLEVEL,
realized the sibling `../eosed` project's editor-protocol SysEx could
be used far more generally — to hunt down *any* currently-unknown `vpar`
byte, not just this one field. This section documents the method (reusable
for future RE) and the full batch of findings from doing it once.

### The method

1. **Set live parameters to distinctive values, don't touch the front
   panel.** `EosBridge.set_parameters([(preset_select, N), (voice_select,
   0)])` then `set_parameters([(param_id, distinctive_value)])`, confirmed
   immediately via `get_parameter` readback. No notes, no bank rebuild.
2. **Save the whole bank to disk once** (a normal front-panel action — RAM
   edits are already "live"/permanent per EOS's own model; there's no
   scripted "save" in the documented protocol, confirmed by grepping
   `eos.messages.Command` for anything save-related — none exists). One
   save captures every preset/voice touched in step 1, however many there
   are — this is what makes batching worthwhile.
3. **Extract the saved bank from the SD card's `HD0.img`.** It turned out
   to be a **plain FAT32 image** (`file` reports `DOS/MBR boot sector...
   OEM-ID "mkfs.fat"`), not the EMU-fs used by CD images/other HDD setups —
   readable directly with **mtools** (`mdir -i HD0.img :: ` /
   `mcopy -i HD0.img "::B.0NN-name.E4B" out.e4b`), no custom reader needed.
4. **Diff the extracted file against a known-clean baseline**, not a raw
   value search. This distinction mattered a lot in practice — see below.

### Value-search vs. diff: value-search produces false positives on
### common/small-range parameters

First pass searched the saved file for each parameter's raw test value
(e.g. is byte `92` present near this voice's data). This worked cleanly for
**wide-range parameters with distinctive test values** (`VOLENV_DEPTH=16`,
`FILT_GEN_PARM1-8=201..208`, `FKEY_XFORM=66` — each a single, unambiguous
match) — but produced **multiple candidate offsets, or an implausible
non-monotonic ordering, for small-range parameters** (`GLIDE_CURVE` 0-8,
`SOLO` 0-8, `LATCHMODE` 0-1): a value like `1`, `3`, or `4` is common enough
elsewhere in the voice block that several unrelated bytes coincidentally
match. **Switching to a direct byte-diff against an untouched baseline
voice/preset resolved every one of these instantly** — exactly one byte
differs, unambiguously, regardless of how "common" its value is. Recommend
diff-first for any future hunt; value-search is only reliable as a quick
first pass for wide-range/distinctive values.

**A related trap: some "found" bytes were really something else entirely,
correlating with preset *index*, not the tested parameter** — e.g. two
bytes that read `0`/`48` in preset 0 and `N`/`48+N` in preset N, for every
N tested, regardless of which parameter was assigned to that preset. These
were something structural (likely a creation-order/slot counter), not
noise to fix, but a reminder to sanity-check that a "changed" byte's new
value actually matches the specific test value set for *that* parameter,
not just "changed at all."

### Findings

All confirmed via the diff method except where noted. `vpar` offsets below
use the established convention (`voice[0:110]`=vpar, PZT starts at
voice-relative 110) — verified to hold for E4XT-native-saved files too (not
just mpc2emu's own writer output) by checking `vpar[2:4]` (`trailer_off`)
lands on a value that divides out to a whole `n_zones`.

See `docs/E4B_FORMAT.md` §4.1's `vpar` table for the full writeup of each
field (`vpar[22]`=RT_LOW, `[23]`=RT_LOWFADE, `[24]`=RT_HIGHFADE, `[25]`=
RT_HIGH — this last one **aliases** the previously-documented "`0x7F`
constant"; `[27]`=Assign Group/choke group; `[28:30]`=Voice Delay, a
big-endian 16-bit word unlike the live protocol's own 7-bit MIDI pairs;
`[33]`=Sample Start Offset; `[37]`=Glide Rate; `[39]`=Solo mode;
`[41]`=Chorus Width, a signed byte (`-100` → `156`, two's complement);
`[44]`=Chorus X; `[50]`=Latch Mode; `[53]`=Glide Curve; `[57]`=Amp
Envelope Depth (the original target — see §E4BLEVEL); `[61]`=VCF
Q/resonance, **also aliases** `FKEY_XFORM`; `[62:70]`=Filter Gen Params
1-8). **Every field in this list is now confirmed by a clean diff against
an untouched baseline** — the last one (Chorus Width) was closed out by
re-diffing a file already on disk from an earlier round, no further
hardware needed.

**Also found, documented in `docs/E4B_FORMAT.md` §4.2 instead of the `vpar`
table:** a third envelope generator, the **Auxiliary Envelope**, at
`PZT[28:40]` — mpc2emu doesn't read or write this at all currently. Its
12 data bytes are ordered by the live protocol's raw `SEG0..SEG5` numbering
(Atk1, Dcy1, Rls1, Atk2, Dcy2, Rls2), **not** the amp/filter envelopes'
phase-grouped file order (Atk1, Atk2, Dcy1, Dcy2, Rls1, Rls2) — a genuine
structural difference between how this third envelope is packed vs. the
other two, confirmed by setting all 12 live ids to distinct values and
reading back the exact byte sequence. Its level bytes go through the same
`round(pct×127/100)` encoding as amp/filter envelope, so likely carries the
same dB-law miscalibration as §E4BLEVEL — unconfirmed for this specific
envelope, not yet acted on.

**Independently re-confirmed** (found via this method, already documented
elsewhere from earlier static-file RE): `LFO2` Lag0/Lag1 at `PZT[57]`/
`PZT[59]` — matches `docs/E4B_FORMAT.md` §4.2's existing entry exactly,
now confirmed via a second, independent method (live SysEx vs. the
original static commercial-bank analysis).

### A useful side-discovery for `../eosed`, not mpc2emu

While hunting, found that the OLD-format SysEx dump (`dump_preset_old`)
lays out parameters **uniformly, 2 bytes per id, in strict ascending id
order** — `dump_offset = 98 + (param_id − 53) × 2` — verified across a wide
span (ids 53 through 116, crossing the `voice.general`/`.tuning`/`.mode`/
`.amp`/`.filter`/`.lfo` group boundaries without exception, including
right through the `vpar`/PZT structural boundary at id 70). This resolves
eosed's own long-standing "voice data layout not yet fully
cross-checked" TODO for at least this section of the old dump format —
logged in `../eosed/docs/RESOLUTION_NOTES.md` and `../eosed/TODO.md`
instead of here, since it's their protocol layer, not mpc2emu's file
format. **Caveat proven by the Aux Envelope finding above: the dump's own
id-ascending order does NOT necessarily match the file's internal byte
order** (the file groups envelope stages by phase name or `SEG` number
depending on which envelope; the dump doesn't) — so the dump-offset formula
is a fast way to test whether a parameter *exists* and read back its
current value, but the real file offset still needs an independent diff
against a saved file, not an assumption ported over from the dump.

---

## §EIII — E-mu Emulator IIIX/ESI writer+parser (design notes, 2026-07-28)

**Not a bug fix** — this is the "how it works" companion for the new EIII
support (`writers/eiii_writer.py`, `parsers/eiii_parser.py`,
`docs/EIII_FORMAT.md`). See `TODO.md` → "EIII writer needs hardware
confirmation on the E4XT" for what's still open (just the hardware step —
everything below is settled/implemented).

### Model mapping: VoiceLayer -> linked EIII preset chain

EIII presets hold only one primary-layer set of note zones (a preset can
add a *secondary* layer for a 2-layer velocity/crossfade split, and can
`link` to another preset to stack further layers). mpc2emu's `Preset`
already models "more than 2 layers" as an arbitrary list of `VoiceLayer`s.
Rather than trying to pack the first two voices into primary/secondary and
`link` the rest (asymmetric, more code, and ConvertWithMoss's own Creator
doesn't do this either — it never uses the secondary slot), every
`VoiceLayer` becomes its own EIII preset, chained via `link` in order. A
voice's velocity extent (min `lo_vel`/max `hi_vel` across its zones) is
written into that linked preset's *primary* velocity-range field.

**Parser bug found and fixed while writing the round-trip test**
(`tests/test_eiii_roundtrip.py`): the read side initially mirrored
ConvertWithMoss's `Detector.parseLayers`, which only applies a preset's
velocity-range fields when **both** the primary and secondary layers are
populated (a guard against stray leftover range bytes on presets whose
secondary layer was never filled in — see its comment). But that gate means
a primary-only, link-chained preset's velocity range — exactly the
technique both this writer and ConvertWithMoss's own Creator use to stack
more than 2 layers — was silently ignored on read. Fixed in
`parsers/eiii_parser._parse_layers` by applying each layer's own range
unconditionally (`_apply_velocity_range` already no-ops on an unrestricted
range, so this is safe); documented as an intentional divergence from
ConvertWithMoss's Detector in a code comment. This is very likely a genuine
gap in ConvertWithMoss's own round-trip too (not verified against their
code directly — inferred from reading `Emulator3Detector.java`).

### Deliberately NOT translated (no hardware calibration exists)

- **Per-zone LFO** (rate/delay/variation/shape, bytes 9-11/36-39/45): byte
  positions are documented (from emu3bm/ConvertWithMoss) but their value
  scales have never been hardware-calibrated, and ConvertWithMoss's own
  Creator/Detector don't read or write them either. Left at 0 (silent/
  unrouted) on write; not decoded on read.
- **Filter key-tracking / velocity-to-cutoff** (`VoiceLayer.filter_keytrack`,
  `.velocity_to_filter`): these mpc2emu fields are EOS/E4XT mod-cord amounts,
  calibrated against E4XT hardware (`models.common.key_track_to_filter_amount`
  = 0.713 oct/oct at cord amount 1.0, `velocity_filter_depth_to_amount` = 9120
  cents at full scale) — that calibration is meaningless for EIII's
  differently-scaled, differently-shaped DSP, and no EIII hardware
  calibration exists. Writing a guessed conversion risked shipping filters
  that audibly mistrack on real hardware, which is strictly worse than
  leaving tracking neutral. `writers/eiii_writer.py` writes byte `0`
  (literal neutral under the format's own documented -127..127 scale) for
  `ZONE_VCF_TRACKING`, **not** ConvertWithMoss's `NO_VCF_TRACKING = 0x40`
  constant — that constant round-trips to ~full positive tracking through
  ConvertWithMoss's own Detector formula (`byte/127.0*2.0`), which looks like
  a latent inconsistency in their code between the Creator's bypass value and
  the Detector's inverse (see the `_ZONE_TRACKING_NEUTRAL` comment in the
  writer for the arithmetic). mpc2emu's writer+parser pair is self-consistent
  under the documented scale regardless of which reading of ConvertWithMoss's
  constant is "right".

### Real-world validation (read side)

`parsers/eiii_parser.py` was run read-only (no assertions beyond "doesn't
crash, structure looks sane") against every EIII/EIIIX/ESI bank identifiable
by its 16-byte header magic across 17 commercial E4XT library CD-ROM `.iso`
images in Jan's local collection
(`/home/lentferj/Dokumente/SYNTHS/E4XT/{*.ISO,ISO-Images/*.iso}`) — banks
were located by scanning each ISO's raw bytes for the three identifier
strings (`EMULATOR THREE `, `EMULATOR 3X    `, `EMU SI-32 v3   `) and slicing
from each match to the next (or a 130 MB cap), since these commercial disc
images don't need their EMU3/ISO9660 filesystem parsed to locate bank
boundaries this way. **Result: 1118 bank images, 19,040 presets, 33,614
samples, 250,236 zones, zero parse failures.** (Audited 2026-08-01 — see
§OSFILE: 1017 of those 1118 are banks the discs' directories actually list,
the rest deleted/free-space leftovers that parse fine but are not library
content. The parse-success claim stands; the *bank count* is 1017.) Spot-checked decoded PCM (peak/RMS,
e.g. a "a pad" bank from the an artist-signature EIII CD-ROM
decoding to a plausible layered stereo pad with sane sample rates and loop
points; an "a drum-map bank" bank — the same "a commercial ESI library" library
ConvertWithMoss's own format doc cites for the ESI sample-index-flag finding
— decoding to real-looking drum one-shots) confirms plausible, not
necessarily byte-perfect, decoding; this is corpus-scale structural
validation, not a hardware playback test. The one-off scan script isn't
checked in (ad hoc, paths are Jan's local collection) — re-derive from this
note if needed again, or start from `tests/re_banks/emu3_os_file_audit.py`,
which reads the EMU3 directory properly and reproduces the raw scan's counts
alongside the corrected ones.

### Bank-format scope

Only `EMULATOR_3X` (`.e3x`) and `ESI_32_V3` (`.esi`) are write targets
(`writers.eiii_writer.BANK_FORMATS`), matching ConvertWithMoss's own
`Emulator3CreatorUI` (`EMULATOR_THREE`'s compact, address-biased layout is
explicitly excluded from its `TARGET_FORMATS` too). `EMULATOR_THREE`
(`.e3b`) is read-only (`writers.eiii_writer.ALL_BANK_FORMATS`, used by
`parsers/eiii_parser.py`) — validated structurally by 34 real `.e3b` banks
in the corpus above, all parsed cleanly.

### Hardware confirmation — DONE 2026-07-28 (E4XT, via its EIII compatibility loader)

First real hardware attempt found and fixed a bug before ever reaching the
per-preset checklist: the E4XT reported the loaded bank as `Type: E4BANK` /
"Unknown file type" instead of recognizing it as EIII content. **Not an
EIII bank-format bug at all** — the EIII byte layout was fine. Root cause
was one level down, in the shared EMU3 filesystem wrapper:
`writers/iso_builder.py`'s dir-content entry `props[5]` field was hardcoded
to `\x00E4B0` (the E4B marker) for every bank unconditionally, harmless
while this project only ever wrote E4B, but wrong now that `.e3x` banks
share the same builder (`docs/EIII_FORMAT.md`'s own "bank-format-agnostic"
claim turned out to need one more layer of nuance).

Checked against 5 real commercial EMU3-filesystem discs
(`docs/EMU3_ISO_FORMAT.md` §2.4, read directly with a throwaway inspection
script against `/home/lentferj/Dokumente/SYNTHS/E4XT/ISO-Images/`, known-good
media Jan pointed at): E4B entries always carry `props = \x00E4B0`
(`library disc A.iso`, every bank); EIII entries always
carry all-zero, across all three on-disk variants (`E-MU library disc B Series
`library disc B`: `EMULATOR 3X`/`EMU SI-32 v3` entries; `library disc D`: `EMULATOR THREE` entries) — a clean, consistent,
never-mixed pattern. Since the E4XT's own file browser evidently reads this
field to label a catalog entry (not just a third-party reader classifying
someone else's disc, which was the narrower claim the field was originally
documented under), writing the wrong marker actively misidentifies the bank.

Fixed: new `_bank_props(path)` in `writers/iso_builder.py` peeks at each
bank's own first 4 bytes (`FORM` -> E4B marker, anything else -> all-zero)
when building a dir-content entry, wired into both write paths (`_dircon_block`,
used by `build_iso`/`build_emu_hdd`, and the inline entry-write in
`emu_hdd_append`). Keeps the module's bank-format-agnostic design intact —
no caller needs to pass a type flag. Verified E4B output is byte-identical
to before (still `\x00E4B0`); new regression test
`tests/test_iso_builder_props.py` (direct `_bank_props()` cases + an
end-to-end `build_iso()` check for both formats).

`EIIITEST.iso` regenerated with the fix and copied onto the ZuluSCSI SD card
as `CD1-EIIITEST.iso`, replacing the mis-tagged one. **Reloaded on the E4XT
and hardware-confirmed 2026-07-28** by Jan: the props fix resolved the
misidentification and the bank now loads correctly as EIII content. This
closes the EIII hardware-confirmation TODO item.

## §CWM-LFOVOL — SFZ/SF2 volume LFO (tremolo) reading, read-side only (2026-07-28)

**Context:** cross-referencing ConvertWithMoss PRs
[#216](https://github.com/git-moss/ConvertWithMoss/pull/216)/[#233](https://github.com/git-moss/ConvertWithMoss/pull/233)/[#239](https://github.com/git-moss/ConvertWithMoss/pull/239)/[#240](https://github.com/git-moss/ConvertWithMoss/pull/240)
(see `TODO.md` for the summary). Both `parsers/sfz_parser.py` and
`parsers/sf2_parser.py` already read pitch-LFO (vibrato) and filter-LFO into
`VoiceLayer.lfo1_*`/`lfo2_*`, but neither read a volume-LFO (tremolo).

### Format shapes differ

- **SFZ v1** treats `pitchlfo_*`, `fillfo_*`, `amplfo_*` as three fully
  independent oscillators (v2 equivalents: `lfo0N_pitch`/`lfo0N_cutoff`/
  `lfo0N_gain` opcodes on arbitrary-numbered LFO blocks). Three oscillators
  don't fit mpc2emu's two hardware-matched LFO slots.
- **SF2** (`Generator.java` in CWM, confirmed via `git show 5e868c6`) has
  generator id `13 = MOD_LFO_TO_VOLUME` (unit: centibels, i.e. 0.1 dB) living
  on the *same* "Mod LFO" oscillator as generator `5 = modLfoToPitch` and
  `10 = modLfoToFilterFc` — SF2's own convention already collapses
  pitch+filter+volume onto one oscillator, which maps naturally onto
  `lfo1_*` with no fallback logic needed (unlike SFZ).

### Model additions (`models/common.py`)

```python
LFO_VOLUME_FULL_DB = 24.0   # NOT hardware-calibrated -- see below

def lfo_volume_depth_to_amount(db: float) -> float:
    return max(0.0, min(1.0, abs(db) / LFO_VOLUME_FULL_DB))
```

Plus `lfo1_to_volume`/`lfo2_to_volume: float = 0.0` fields on `VoiceLayer`.

`LFO_VOLUME_FULL_DB` follows the precedent of `LFO_PITCH_FULL_CENTS = 1593.0`
(hardware-measured via MOD_DEPTH_CAL on the E4XT, 2026-06-12) but **has no
equivalent measurement** — there's no tremolo-depth calibration bank on
record. 24 dB is a plausible placeholder (a full-swing tremolo audibly
silencing a sound), not a measured value. Flag this if it ever needs to be
precise.

### SFZ fallback logic (`parsers/sfz_parser.py`)

```python
a_depth = _f('amplfo_depth') or _f('lfo03_gain') or _f('lfo02_gain') or _f('lfo01_gain')
a_freq  = _f('amplfo_freq')  or _f('lfo03_freq') or _f('lfo02_freq') or _f('lfo01_freq')
if a_depth:
    if not lfo2_claimed:
        params['lfo2_rate']      = a_freq if a_freq else 5.0
        params['lfo2_shape']     = _sfz_lfo_wave(merged.get('lfo02_wave'))
        params['lfo2_to_volume'] = lfo_volume_depth_to_amount(a_depth)
    elif not p_depth:   # LFO1 only free if no pitch-LFO already claimed it
        params['lfo1_rate']      = a_freq if a_freq else 5.0
        params['lfo1_shape']     = _sfz_lfo_wave(merged.get('lfo01_wave'))
        params['lfo1_to_volume'] = lfo_volume_depth_to_amount(a_depth)
```

Claims LFO2 if the filter-LFO block hasn't already claimed it; else claims
LFO1 if the pitch-LFO block hasn't; else the tremolo data is dropped
(no third slot to put it in, and overwriting an existing pitch/filter LFO
would be worse than losing the tremolo).

### SF2 addition (`parsers/sf2_parser.py`)

```python
mod_volume_cb = ig_dict.get(13, {}).get('amt', 0)
if mod_pitch or mod_cutoff or mod_volume_cb:
    ...
    if mod_volume_cb:
        voice.lfo1_to_volume = lfo_volume_depth_to_amount(mod_volume_cb / 10.0)
```

Centibels -> dB is `/10.0`.

### Verification

New `tests/test_lfo_volume.py` (plain-python `check()`/`main()`, matching
project convention — no pytest): depth<->amount conversion (0 dB -> 0.0,
full-depth -> 1.0, sign-independence, clamping); SFZ claims-LFO2 (no filter
LFO present); SFZ falls-back-to-LFO1 (filter LFO already on LFO2, no pitch
LFO); SFZ drops-when-both-slots-taken (pitch on LFO1, filter on LFO2). All
pass. SF2 path verified only by `python3 -c "from parsers.sf2_parser import
parse_sf2"` (imports cleanly) plus structural review against the
already-working pitch/filter reading pattern — no binary SF2 fixture was
built, since no existing SF2 test file exists to extend.

### Writer side: deliberately NOT wired (open, blocked)

Neither `writers/e4b_writer.py` nor `writers/krz_writer.py` has a
hardware-confirmed "LFO->Volume" mod-destination byte documented anywhere
(`docs/E4B_FORMAT.md`, `docs/KRZ_FORMAT.md`) — `e4b_writer.py`'s
`_extra_cords` list only routes LFO1 to Filter-Freq (`0x38`)/Filter-Q
(`0x39`)/Pitch (`0x30`); `krz_writer.py` only wires `lfo1_to_pitch` via
`CAL[21]`/`CAL[22]`. Checked ConvertWithMoss's own
`Emulator4Constants.java` for a matching destination constant
(`grep -n "VOLUME|0x36|AMP_"` — no hits): their own Emulator4/Kurzweil
writers don't implement LFO->Volume output either, only for SFZ/SF2/DLS/
DecentSampler targets, which don't need a byte-level hardware destination.
Guessing a destination byte risks misrouting modulation onto some other,
unintended parameter in a real E4B/KRZ file — worse than the read-only gap
this closes. Blocked on: live-SysEx parameter-hunting (same method as
§E4BPARAMHUNT) to find the real E4B cord-destination byte for Volume, and
the equivalent K2000 `CAL[]` byte, before either writer can consume these
new `lfo1_to_volume`/`lfo2_to_volume` fields.

Also noted, bigger and out of scope here: `parsers/gig_parser.py` has no
LFO support at all (pitch, filter, or volume).

## §EIII-CWM — Five reader gaps found cross-referencing ConvertWithMoss (FIXED 2026-07-29)

**Context:** ConvertWithMoss landed ~38 commits in 48 h, nearly one per
format it supports. Reviewed the subset touching formats mpc2emu also
reads (the rest — Kontakt, Roland, Tonverk, 1010music, QPAT, YSFC, Korg,
Deluge, Renoise, TX16Wx, Ensoniq, Maschine, DLS, NN-XT, DecentSampler,
Disting — are formats we don't touch). Four of their PRs revealed real
gaps on our side; the rest we either already handled correctly or had
deliberately diverged from. Commits `ea74e45`/`d0ed2cc`/`ad4c80e`/
`6c463c4` plus our own follow-up `5900560`.

**Checkpoint for the next round:** the last CWM commit reviewed is
`9443b635` (2026-07-29). Diff from there rather than a `--since` window.

### What was already right (no action)

Worth recording, since re-checking these each round is wasted effort:

- **EIII parked-filter / tracking-neutral byte** (their #245): already
  fixed here independently, and `writers/eiii_writer.py` carries the
  `_ZONE_TRACKING_NEUTRAL` note explaining why we write `0` rather than
  their `NO_VCF_TRACKING = 0x40` — see §EIII.
- **E4B envelope decay1/decay2 + channel-paired loop** (their #242):
  already fixed, same "Nylon Guitar" case — see §E4BREAD2.
- **Volume LFO / tremolo** (their #240): already read — see §CWM-LFOVOL.
- **Sample-file root-note priority** (their #281): `sampledir_parser.py`
  already prefers the embedded `smpl` root over the filename.
- **TAL volume default** (their #276): already written unconditionally.
- Their EXS24 (#261) and SFZ (#278) fixes are **writer-side**; mpc2emu
  has no EXS24 or SFZ writer, so they don't apply.

### The four fixes

1. **SF2 static filter + preset-level generators** (their #255). Gen 8
   `initialFilterFc` / gen 9 `initialFilterQ` were never read — every
   other reader we have models a static filter, SF2 alone didn't. And a
   preset zone with no gen 41 is SF2's *global zone*, whose generators
   are additive offsets over every instrument zone beneath it (spec
   §8.1.3); only gen 41 itself was being read. Also picked up gen 48/51/52
   (attenuation, coarse, fine) into the `ZoneMapping` fields that already
   existed for them.

2. **EIII filter bypass** (their #248). The bypass test compared the
   cutoff byte to `0xEF` exactly — our own writer's `DEFAULT_CUTOFF`.
   Every byte from `0xD5` up is already past 20 kHz, so third-party banks
   parking the filter elsewhere got a spurious filter object. Now tested
   against `E4B_CUTOFF_MAX_HZ`. Corpus check: 130,473 zones qualify as
   inaudible-with-zero-Q, and **69,981 of them (>half) used a byte other
   than `0xEF`** and were mis-read.

3. **EIII truncated sample indices** (their #252). See
   `docs/EIII_FORMAT.md` for the format-level writeup. Mastering-tool
   artifact of specific library CD-ROMs, *not* a hardware/format bug —
   which is why it survived 25+ years unreported. Ported their
   `Emulator3SampleIndexRepair.java` faithfully (same scoring
   thresholds); the thresholds are what stop it mis-repairing a correct
   preset, so they are not to be "simplified" without re-running the
   corpus.

4. **WAV `smpl` MIDIPitchFraction** (their #254). Only `MIDIUnityNote`
   was read, so embedded fine-tune rounded to the nearest semitone.

### Corpus validation method (reusable)

The EIII work was validated by scanning **1118 real EIII/EIIIX/ESI bank
images** (1017 of them directory-listed banks — §OSFILE)
out of 22 commercial CD-ROM `.iso` images in Jan's collection
(`~/Dokumente/SYNTHS/E4XT/{*.ISO,ISO-Images/*.iso}`), located by scanning
raw bytes for the three identifier strings and slicing to the next match
— the same technique §EIII used. Result: **4144 sample-index references
repaired across 771 presets, zero parse failures.**

A **decision-branch census** (instrumenting `_choose_repair_candidate`)
answered whether any of the heuristic is dead weight:

```
3073  kept stored (no repair)
 495  gate: decisive (pitch ladder)      395 of them decisive-only
 219  gate: affinity_decisive (name only)
 137  gate: perfect_small (<=2 zones)
  30  via affinity override (pitch too weak)
 200  repairs REQUIRED a non-pitch gate
```

So the preset-name affinity machinery carries ~30 % of repaired presets;
deleting it to shorten the port would have silently lost 200 repairs.
**Don't strip it.**

Spot-check that the repairs are real rather than merely plausible: an
`apo:PlusDXep` preset resolves to `C3Yamaha` F0/C1/Gx1/Dx2/Gx2/Dx3/A3/D4/
Gx4/Cx5/G5 and `TinePiano` G2/G3/G4 — an ascending ladder matching the
zones' own keys — where the stored indices pointed at unrelated `OB 1 G1`
and `B3LoDistSlow*` samples.

### Performance note

The faithful port was profiled afterwards (`5900560`): `_repair_affinity`
was **63 % of the whole repair pass**, because sample-name normalization
ran per (preset × candidate) instead of once per bank — 37,470 calls on a
bank holding 738 distinct names. Hoisting that, plus two provable no-op
short-circuits, cut the pass ~1.8× with byte-identical output (re-verified
at 4144/771 over the full corpus). General lesson, third time in this
project: **the hot spot in a ported heuristic is almost always repeated
string normalization in an inner loop, not the algorithm itself.**

### Not fixed — reference only

- EIII per-zone **vibrato** (their #284) and **chorus-as-detuned-voice**
  (their #285): not modelled by mpc2emu; would need the per-zone LFO
  bytes §EIII deliberately leaves alone (no hardware calibration).
- EIII **floppy disk sets** (their #237): `ALL_BANK_FORMATS` covers
  SCSI/hard-disk bank files only, not raw floppy memory dumps.

## §PARSERPERF — Parser performance pass: the cost was a handful of per-sample loops and two directory walks, not the algorithms (2026-07-29)

**Context:** general "optimize the input parsers" sweep. Benchmarked every
parser over real files first rather than guessing, which turned out to
matter — the cost was not spread across the parsers at all.

### The measurement that decided everything

Throughput over real corpus files, before any change:

| fmt   | files | MB    | secs  | MB/s  |
|-------|------:|------:|------:|------:|
| xpm   | 20    | 20.5  | 87.59 | 0.2   |
| sfz   | 25    | 0.3   | 38.68 | 0.0   |
| exs24 | 10    | 0.4   | 27.67 | 0.0   |
| krz   | 20    | 23.6  | 1.41  | 16.8  |
| e4b   | 19    | 129.1 | 0.29  | 445.7 |
| sf2   | 25    | 13.4  | 0.05  | 259.2 |
| gig   | 8     | 2.1   | 0.01  | 262.2 |

`e4b` parsed 129 MB in 0.29 s while `xpm` needed 87 s for 20 files. The
split is exactly "does this parser load external WAVs": xpm/sfz/exs24 do,
the others read a self-contained bank. A `cProfile` of one XPM
(`45 Cosmos.Keygroup.xpm`, 24.6 s) put **`_stereo_to_mono` at 24.46 s —
99.5%**, with 27M `unpack_from` + 13.5M `pack_into` calls for 31 samples.

**Lesson worth keeping:** the throughput column is what exposed this. A
per-format "seconds" number alone looks like "xpm files are just bigger";
MB/s made a 2000x spread obvious.

### Fixes (each verified byte-identical, see below)

1. **`_stereo_to_mono`** (`parsers/xpm_parser.py`) — per-frame struct loop
   → `audioop.tomono(raw, 2, 0.5, 0.5)`, with a pure-`array` fallback.
   Reached by **six** parsers through `load_wav` (xpm, sfz, exs24, pgm,
   talsmpl, sampledir), so one fix carries every sample-loading format.
   Measured on 400k frames: struct 127 ms, array 43 ms, audioop 1.3 ms.

2. **AIFF 24-bit and 32-bit downscale** — both collapse to *"take the top
   two bytes of each big-endian sample as a signed 16-bit value"*. Proof
   for 24-bit: with `b0 < 0x80` the old `(b0<<16|b1<<8|b2) >> 8` is plainly
   `b0<<8|b1`; with `b0 >= 0x80` the `-0x1000000` sign correction and the
   flooring `>> 8` cancel to exactly `(b0<<8|b1) - 0x10000`, which *is* the
   big-endian int16. Same argument for 32-bit with `>> 16`. So no
   arithmetic is needed — a strided byte copy plus one `byteswap`. Unified
   as `_be_high2_to_le16(raw, stride)`. (`gig_parser` had already found
   this for its own 24-bit path in CR-16 #1; this generalizes it.)

3. **KRZ `_extract_pcm`** — the BE→LE swap was a per-byte-pair Python
   loop over the bank's entire sample pool; now `array.byteswap()`.
   `frombytes`/`tobytes` are exact inverses on the same host, so the net
   effect is "swap adjacent byte pairs" on any endianness.

4. **O(n²) sample dedup** — `sf2_parser` and `gig_parser` both did
   `if sd.name not in {s.name for s in bank.samples}`, rebuilding a set of
   *every* sample name once per zone. Now an incrementally maintained set.

5. **De-duplication** — `gig_parser` carried its own stereo downmix; it now
   calls the shared one (CR-13/CR-17: duplicated codecs have drifted here
   before). Its `import array` became unused and was dropped.

6. **`_convert_24_to_16`** — a *second*, separate 24-bit path for **WAV**
   (little-endian) alongside the big-endian AIFF one in #2. Missed on the
   first pass, and re-measuring caught it: after #1 landed, `sfz`/`exs24`
   had not improved at all, because their sample sets are predominantly
   24-bit WAV and never reached the downmix. It was **87%** of their parse
   time. Same reduction, but for LE the two high bytes are already in
   order, so it needs no byteswap — a pure strided copy. `_convert_8_to_16`
   went the same way (`bytes.translate` sign flip, zero-interleaved).

7. **`exs24_parser._find_indexed`** — a different *class* of hotspot: not
   PCM at all but filesystem tree-walking, at **97%** of exs24 parse time.
   The fallback audio index (for packs keeping WAV/AIFF in a sibling folder)
   walks up to 8 ancestor levels and 80k files, and the closure is per
   `parse_exs24` call — so converting a folder of N presets re-walked the
   same tree N times. Memoized per parent directory (bounded FIFO); the
   index derives purely from those ancestors, so it is identical by
   construction for any two `.exs` in one folder.

8. **`xpm_parser._find_wav`** — the same cliff, latent rather than measured:
   both slow paths walked the whole tree *per lookup* (`rglob(name)` per
   candidate, then a full `rglob('*')`), so an XPM referencing N missing
   samples paid N walks. One walk now builds a first-occurrence index
   answering both, memoized per directory.

   Two traps worth recording. The case-insensitive fallback returned the
   first entry in **traversal** order matching any candidate, *not* the
   first candidate — so the index records traversal position and selects by
   it; a naive candidate-order rewrite silently picks a different file when
   a `.wav` and a `.WAV` twin live in different folders. And `rglob(name)`
   treated the sample name as a **glob pattern**, so `Bass[12].wav` could
   resolve to `Bass1.wav`; lookups are now literal, which is what the caller
   means. That is a deliberate, Jan-confirmed behaviour change — the one
   place in this pass that is not strictly input-for-input identical.

### The audioop decision (reverses CR-16)

CR-16 (2026-06-11) explicitly *avoided* `audioop` — "byte-identical to the
manual loops but deprecated/removed in Python 3.13". That call is reversed
here, deliberately:

- CR-16 optimized only the gig decode path and left `_stereo_to_mono` as a
  struct loop. It could not have known that function would turn out to be
  99.5% of three formats' runtime.
- The 3.13 objection is *answered*, not ignored: the import is
  `try/except`, and the `array` fallback is byte-identical, so on 3.13+ the
  code keeps working and merely loses the speedup (43 ms vs 1.3 ms — still
  ~3x better than the 127 ms it replaced).

**Why audioop was deprecated** (PEP 594, "Removing dead batteries"): the
module exists mainly for a-LAW/u-LAW/ADPCM telephony codecs and was
dropped as a cluster with `sunau`/`aifc`/`sndhdr`/`chunk`/`ossaudiodev`;
it was unmaintained, and being hand-written C doing pointer arithmetic on
caller-supplied buffers it had a history of overflow fixes. **None of that
rationale touches `tomono`**, which is trivial fixed-point arithmetic with
no format parsing — it is not deprecated for being wrong. Verified equal to
`(l + r) >> 1` across an exhaustive sign/parity/clipping matrix.

If the 3.13 cliff is ever hit, the options are `pip install audioop-lts`
(a maintained drop-in that reinstalls the `audioop` module name, so the
`try/except` picks it up with no code change) or taking on numpy — which
this project has so far deliberately avoided as a dependency.

### Equivalence method (reusable)

`scratchpad/verify2.py`: `git worktree add --detach` a pristine checkout of
`HEAD`, run **both** the old and new parser in separate subprocesses over
the same real files, and compare a SHA-256 over the whole parsed `Bank` —
every sample's full PCM plus every zone/voice field. That catches drift the
unit tests would not, since it hashes decoded audio rather than structure.
Plus targeted equivalence tests for each rewritten function against the
original implementation, including adversarial byte patterns
(`0x00/0x7F/0x80/0xFF`), the 24-bit sign boundary, and odd-length buffers
(the old loops left a trailing partial frame as zero — the replacements
reproduce that exactly).

## §MPC3XPM — MPC 3.x `.xpm` is gzip+JSON, not XML (found 2026-07-30)

**Context:** routine check of ConvertWithMoss for MPC work in the last three
months. Two relevant landings: `58933a2c` (2026-05-18) added JSON `.xpm`
reading and merged their two MPC detectors into "Akai MPC Modern"; `bfbc82c4`
and `30177c27` (both 2026-07-30) added MPC 3 `.xty` track-file *writing* and
fixed its filter scaling.

### The container

An MPC 3.x `.xpm` is **gzip-compressed**. Decompressed, it starts with five
plain-text lines and then a JSON document:

| line | value (observed) | meaning |
|---|---|---|
| 0 | `ACVS` | magic; CWM rejects anything else |
| 1 | `3.9.0.31` | MPC firmware/app version |
| 2 | `SerialisableProgramData` | payload kind — also `SerialisableTrackData`, `SerialisableProjectData` |
| 3 | `json` | encoding; CWM rejects anything else |
| 4 | `Linux` | host OS |

Payload shape (from `K2-01.xpm`): `data.version = 6`, `data.name`,
`data.type`, `data.programPads.pads` (128 entries), plus `customQLinks`,
`transpose`, `midiKillGroup`, `chainID` and ~40 more keys.

### Detection

CWM sniffs the first five bytes for `<?xml` and falls through to the JSON
reader otherwise. mpc2emu should do the same, but the cheaper and more
robust test is the **gzip magic** `1f 8b`, since a classic XPM is plain text
and an MPC3 one is always compressed.

Worth adding at the same time: 101 files in Jan's tree ending `.xpm` are **X11
pixmaps** (`/* XPM */`), an unrelated image format sharing the extension. They
currently reach the XML parser and fail with a confusing error;
`collect_input_files()` globs `*.xpm` so a user pointing mpc2emu at the wrong
folder hits this. A magic-byte check should skip them with a clear message.

### Why this matters now

Three MPC 3.9 files already sit in `~/temp/SamplerExports/`, exported from
Jan's own MPC, and they are **completely unreadable** — `parse_xpm()` raises
`ParseError` at line 1 column 0 rather than degrading. Any MPC running 3.x
firmware produces these, so the classic XML path is on its way to being the
legacy case.

### Not applicable: their cutoff fix

`30177c27` also states *"Cutoff 24000ct is Max… resulting values were too
high. Also fixed in XPM reading/writing"*. That is their **writer's**
normalized↔cents conversion (`MathUtils.normalizeCutoff`). mpc2emu reads the
XPM `Cutoff` element as an already-normalized `0.0–1.0` float straight into
`VoiceLayer.filter_cutoff` (its own 0–1 domain) and never converts through
cents, so there is no equivalent scaling bug to inherit. Recorded so it is not
re-checked.

### Implementation (2026-07-30)

Rather than write a second mapping, `parse_xpm()` detects the gzip magic and
runs `_mpc3_to_xml()`, which builds the **MPC 2.x element tree** from the JSON
and hands it to the existing parser. Everything downstream — the
hardware-measured envelope curve, the filter-type table, the LFO sync
divisions, and the lane allocation that splits overlapping layers into
parallel voices — is reused unchanged. One mapping to maintain, and MPC 3
files cannot drift away from MPC 2 behaviour.

Field mapping (JSON → the XML tag the parser reads):

| JSON | XML tag |
|---|---|
| `drum.instruments[i].lowNote` / `.highNote` | `LowNote` / `HighNote` |
| `.coarseTune` / `.fineTune` / `.ignoreBaseNote` | `TuneCoarse` / `TuneFine` / `IgnoreBaseNote` |
| `.synthSection.filterData.value0.*` | `FilterType`, `Cutoff`, `Resonance`, `FilterEnvAmt`, `FilterKeytrack`, `VelocityToFilter` |
| `.synthSection.ampEnvelope.{Attack,Decay,Sustain,Release}.value0` | `Volume*` |
| `.synthSection.filterEnvelope.*` | `Filter{Attack,Decay,Sustain,Release}` |
| `.synthSection.lfoData.value0.*` | `LfoPitch`, `LfoCutoff`, `LFO/{Rate,Type,Sync,Reset}` |
| `.layersv[j].sampleName` / `rootNote` / `velocityStart` / `velocityEnd` | `SampleName` / `RootNote` / `VelStart` / `VelEnd` |
| `.layersv[j].volume.gainCoefficient` / `pan` | `Volume` / `Pan` |
| `.layersv[j].loop` / `loopStart` / `sampleStart` / `sampleEnd` | `Loop` / `SliceLoopStart` / `SliceStart` / `SliceEnd` |
| `transpose` + `keygroup.transpose` | folded into the instrument's `TuneCoarse`/`TuneFine` *(added 2026-07-31)* |
| `samples[].metadata.rootNote` / `.tune` | `RootNote` fallback (+1) / added to `TuneFine` as cents *(added 2026-07-31)* |

Three things worth knowing for the next person:

- **The keygroup list lives under `drum`, not `keygroup`**, even for a keygroup
  program (`type = 1`). `data.keygroup` holds only program-global settings
  (`numKeygroups`, pitch-bend range, mod links). Looking under `keygroup` for
  the instruments finds nothing.
- **Many scalars are wrapped per-articulation** as `{"value0": x}` — envelope
  stages, filter blocks, LFO blocks, `lfoFilterCutOff`. `_v0()` takes the
  first; multi-articulation programs would need more.
- **`rootNote` is 1-based**, exactly as in MPC 2.x XML, so the existing
  `raw_root - 1` conversion applies unchanged. Confirmed independently: all 71
  roots across the three test files match the note number in each sample's own
  filename after the -1.

**Not yet handled:** `SerialisableTrackData` / `SerialisableProjectData`
payloads (rejected with a clear message — they are tracks/projects, not
programs), multi-articulation programs beyond `value0`, and MPC 3's `.xty`
track files, which are a separate format ConvertWithMoss only recently began
writing.

### Validation scope — narrow, and worth stating plainly

The three local 3.9.0.31 files are **hardware-created by the MPC Auto Sampler**
(Jan, 2026-07-30), which produces a deliberately minimal program: *"just
samples, keyzones and amp env, no filter or anything."* Measured across all
71 keygroups in them:

| exercised | not exercised |
|---|---|
| key ranges, root notes (1-based), velocity ranges | velocity-split layers (all 71 are `0-127`) |
| one layer per keygroup | multi-layer keygroups, layer crossfade |
| amp envelope | filter envelope, LFO routing (all at defaults) |
| sample name → file resolution | loops (`loop: false` throughout) |
| `type = 1` keygroup programs | drum programs, `SerialisableTrackData`/`ProjectData` |
| | per-layer tune / volume / pan (all at defaults) |

So the container handling, the keygroup/layer walk and the tag mapping are
well covered, but **the parameter-heavy paths are only covered structurally**:
the values were all defaults, so a wrong scale factor on, say, the filter
envelope would not have shown up. Anything beyond auto-sampler output should
be re-checked against a real file before being trusted.

**The two filter slots, concretely.** Every keygroup carries
`filterData.value0` AND `value1`, and in all 71 they DIFFER
(`value0.filterType = 2`, `value1.filterType = 0`). These are **Filter 1 and
Filter 2** (see the manual correction above), and `_v0()` takes Filter 1.
Harmless in these files — cutoff is at maximum with zero resonance and zero
envelope amount, so both map to an audibly wide-open filter
(`_XPM_FILTER_TYPE` sends type 2 to a 2-pole LP, and type 0 is itself
documented as "4PLP wide open (bypass-like)") — but a program that actually
uses Filter 2, or blends the pair, converts with only the first.

### Is MPC 3 a new container, or a new model? Both, partly.

Asked directly, and worth answering with the schemas rather than an impression.
Comparing a classic XML `.xpm` against a 3.9.0.31 JSON one:

|  | XML (MPC 2.x) | JSON (MPC 3.x) |
|---|---|---|
| instrument-level fields | 66 **flat** tags | 39 keys, synth params **nested** in `synthSection` |
| layer-level fields | 28 | 42 |

17 layer concepts appear in **both** schemas: `sampleName`, `rootNote`, `pan`,
`volume`, `loopStart`, `loopEnd`, `sampleStart`, `sampleEnd`, `direction`,
`offset`, `mute`, `active`, `pitch`, `sliceIndex`, `sampleFile`, `loop`,
`loopCrossfadeLength`.

**Core model preserved.** Program → keygroups (`lowNote`/`highNote`) → layers
(sample, root, velocity, tune, pan, volume) is unchanged, and `rootNote` is
1-based in *both*. That is why translating the JSON into the XML element tree
works and is not a hack.

**Renames only:** `TuneCoarse`→`coarseTune`, `VelStart`→`velocityStart`,
`LoopTune`→`loopFineTune`.

**Genuinely restructured:**
- Synth parameters moved from 66 flat instrument tags into nested
  `synthSection` (`filterData` / `ampEnvelope` / `filterEnvelope` / `lfoData`).
- **`{value0, value1}` wrappers are SLOTS, not articulations** — corrected
  2026-07-30 against the official *MPC Standalone OS User Guide v3.9*, which
  is unambiguous (p. ~8838): *"The Filters tab features **two filters** which
  can be run in either parallel or series configuration, with a **blend**
  control"*, plus `Filter 1/2 Type` fields, a `Blend` knob and a
  `Parallel/Serial` toggle — exactly the JSON's `filterData.value0/value1`,
  `filterBlend` and `filterSerialRouting`. Likewise `lfoData.value0/value1`
  are **LFO 1 and LFO 2** (the manual's "Tap LFO to cycle between the LFO 1
  and LFO 2 controls"), and a layer's `lfoFilterCutOff: {value0, value1}` is
  that LFO's depth *into each of the two filters* ("To Filter 1/2").
  Envelope stages carry only `value0`, consistent with there being one amp
  and one filter envelope. So MPC 3 gained a **dual filter and a second
  LFO**, which is a real model change — but nothing to do with articulations.
  (Articulations do exist in MPC 3, as drum rudiments/flams with up to four
  per pad selected by pad quadrant, which is what `quadrantEnabled` relates
  to — a separate feature.)
- Slice parameters went flat → nested `sliceInfo`, with
  `layerLoopModeOverridesSliceLoopMode` arbitrating between the layer's loop
  and the slice's.

**Genuinely extended** — no XML ancestor:
- **`oscillatorType` / `Mode` / `Params` / `SubTypeName` / `StartPhase` /
  `Decay`**: an MPC 3 layer can be a *synth oscillator* rather than a sample.
  Dormant in the local files (all 568 layer slots are `oscillatorType = 0`,
  sample mode) but structurally new.
- Per-layer randomisation (`offsetRandom`, `panRandom`, `pitchRandom`,
  `volumeRandom`), `keyTrackEnable`, `quadrantEnabled`, `playbackOffset`,
  slice increment/cycle/seed.

**Consequence for this implementation.** Translating to the XML tree is sound
for the *sample-playback subset*, which is all mpc2emu converts. Its ceiling is
now known rather than assumed. `_v0()` taking `value0` means we take **Filter 1
and LFO 1** — a defensible choice, since mpc2emu models one filter, rather than
the arbitrary pick it looked like before this correction. What is dropped:

- **Filter 2**, and with it `filterBlend` and `filterSerialRouting`. A program
  using both filters converts with only the first.
- **LFO 2** — and this one is cheap to fix, because `VoiceLayer` already has
  `lfo2_rate` / `lfo2_shape` / `lfo2_to_pitch` fields that the XML path fills
  from a second LFO block. Mapping `lfoData.value1` onto them is a small,
  well-founded improvement.
- **Oscillator layers** (they arrive as a layer with no sample) and the
  extended per-layer fields listed above.

Two more facts from the manual worth recording: a keygroup holds **up to eight
samples** (p. ~1915) — matching the 8 layer slots measured per keygroup, of
which the auto-sampler fills one — and a keygroup track holds **up to 128
keygroups**.

### Loops (implemented 2026-07-30, following ConvertWithMoss)

MPC 3 carries **two** loop descriptions plus a flag choosing between them,
where MPC 2.x had one implicit loop running to the Pad End:

- `layerLoopModeOverridesSliceLoopMode` true → the layer's `loopMode`,
  `loopStart`, `loopEnd`, `loopCrossfadeLength`
- otherwise → `sliceInfo`'s `LoopMode`, `LoopStart`, `End`,
  `LoopCrossfadeLength`
- a loop counts only when `mode > 0` **and** its end `> 0`
- `offset` shifts the play start on top of `sampleStart`

Taken from `MPCModernDetector.readJsonSampleZone()` and **assumed correct** —
none of the local files exercise it (all auto-sampler output, `loop: false`
throughout), so this is adopted on ConvertWithMoss's authority rather than
verified against hardware output.

MPC 2.x has no explicit loop END, so `_apply_slice` always looped to the slice
end. It now takes an optional `slice_loop_end` (0 = old behaviour, so the XML
path is untouched) fed by a new `SliceLoopEnd` tag that only the JSON converter
emits.

Verified on synthesised programs covering both tiers: layer-tier forward
(1000-6000), slice-tier forward (2000-5000), alternating (500-7000), no loop,
and the discriminating case — override flag OFF while layer loop data IS set,
where the slice tier must win and correctly yields no loop. The three real
files are byte-identical before and after the change; their 6/13/13 looped
samples come from the WAVs' own `smpl` chunks, which the auto-sampler writes
and the existing MPC rule already honoured.

**Still not implemented** (CWM does these): `direction` → reversed playback,
`SerialisableTrackData` / `SerialisableProjectData` payloads (they extract
`data.program` and `data.tracks[].program` filtered to `type == 1`; we reject
both), `samples[].metadata.tune`, and pitch-bend range.

### Full sweep of the official MPC v3.9 User Guide (2026-07-30)

Read the whole *MPC Standalone OS User Guide v3.9* (37 MB PDF → 21,651 lines
of `pdftotext -layout`) looking for anything implementable. It is the same
class of authority for MPC work that the EOS manual is for E4XT work, and it
corrected one thing I had already documented wrongly (see the `{value0,
value1}` = filter/LFO **slots** correction above).

**Confirmed structural facts** (previously inferred):

- A keygroup holds **up to eight samples** — matching the 8 layer slots
  measured per keygroup, of which the auto-sampler fills exactly one.
- A keygroup track holds **up to 128 keygroups**.
- **Oscillators are a per-layer Sample/OSC switch**: *"Drum and Keygroup
  tracks can now use oscillators as a sound generator per layer instead of
  samples"* — confirming the `oscillatorType` reading exactly.

**Envelopes are DAHDSR, not ADSR.** The controls are *Delay, Attack, Hold,
Decay, Sustain, Release*, and the JSON carries all of them plus `AttackCurve`,
`DecayCurve`, `ReleaseCurve`, `TimeScaling`, `tempoSync`, `Looped`, `OneShot`,
`VelocityToAttack`, `DecayStart` and a `Type`. There are also **four**
envelopes per keygroup — `ampEnvelope`, `filterEnvelope`, `pitchEnvelope`,
`auxEnvelope` — where mpc2emu models two.

*Implemented from this:* **AD-mode envelopes now import with sustain 0.** The
manual is explicit that in AD mode the level *"will gradually drop to zero"*
with no sustain segment, so reading `Sustain` regardless would import an AD
envelope as a full-level hold — the opposite of what it does. `AD` is a
per-envelope flag, so amp and filter are handled independently.

*Implemented from this:* **LFO 2 is mapped.** The manual confirms two LFOs
(*"Tap LFO to cycle between the LFO 1 and LFO 2 controls"*), and `VoiceLayer`
already had `lfo2_*` fields the XML path never filled. `lfoData.value1` now
becomes an `<LFO2>` block (routed to pitch, which is what `lfo2_*` models).
XML programs never contain one, so their behaviour is untouched.

**Worth implementing next, in rough value order:**

1. **Envelope Hold and Delay.** E4B envelopes are 6-stage, so the target can
   represent more than our 4-stage `Envelope` dataclass carries. Needs a model
   change, which is why it is not done here — but it is a real fidelity gain
   for any program that uses them, and the data is already parsed.
2. **Filter 2**, with `filterBlend` and `filterSerialRouting`. A program using
   both filters currently converts with only Filter 1.
3. **`pitchEnvelope`** — EOS has a routable aux envelope, so there is a
   plausible target.
4. **`direction`** → reversed playback (ConvertWithMoss does this).
5. **Track/Project payloads** — CWM extracts `data.program` and
   `data.tracks[].program` filtered to `type == 1`; we reject both, so a
   keygroup program living inside an MPC 3 track or project file is
   unreachable.
6. Envelope **curves** (`AttackCurve`/`DecayCurve`/`ReleaseCurve`, default
   0.375) and `tempoSync`/`TimeScaling`, which would change the seconds
   conversion when not `None`/0.5.

**Deliberately not pursued:** the filter-type enumeration. The manual defers
to *Appendix > Glossary > Filter*, whose layout does not extract cleanly from
the PDF, so whether MPC 3's `filterType` integers still match MPC 2's ordering
(which `_XPM_FILTER_TYPE` encodes) is **unverified**. It did not matter for
the local files — every filter is at maximum cutoff with zero resonance, i.e.
audibly bypassed either way — but it is the obvious thing to check before
trusting a converted program that actually uses a filter.
*(Substantially resolved the next day — see the crosscheck below.)*

The extracted text is kept out of the repo (it is a 37 MB copyrighted manual);
re-derive with `pdftotext -layout` from the vendor PDF if needed again.

### ConvertWithMoss crosscheck (2026-07-31) — RE checklist item E1

Read CWM `e8027b9d`'s `MPCModernDetector` / `MPCEnvelopesAndFilter` /
`MPCFilter` against `_mpc3_to_xml()` field by field, then tested every
divergence against the three real 3.9.0.31 files. Both sides read the same
JSON, so a divergence is a bug in one of them — the lever that worked on the
KRZ reader (§KRZ-CWM). Full detail in
`docs/re_procedures/mpc3_xpm_params.md`.

**Agreements** (these stop being single-source assumptions): the filter
enumeration for 1–18 and 29; `{value0, value1}` as filter/LFO **slots**;
AD mode ⇒ sustain 0; and the two-tier loop scheme including the
`mode > 0 && end > 0` guard.

**The filter-enumeration question above is largely answered.** CWM applies
*one* table to MPC 2.x XML, MPC 3 JSON **and** its XPM writer, and it matches
`_XPM_FILTER_TYPE` on every index it defines. The glossary — unreadable as a
table, but readable as prose — lists the families in exactly that order
(low-pass, high-pass, band-pass, band-stop, band-boost, Model, Vocal, MPC3000
LPF) and confirms 1/2/6/8-pole variants exist, which is what puts the indices
where they are. Not a hardware sweep, but no longer a leap of faith.

**Two real losses on our side, both fixed here:**

1. **`transpose` was dropped.** Program-level `transpose` and
   `keygroup.transpose` are semitone offsets applying on top of every
   instrument's own tuning; we read neither, so a transposed program converted
   at concert pitch. Now folded into the instrument's `TuneCoarse`, with any
   fraction pushed into `TuneFine` as cents — the same place the XML path
   already sums instrument + layer tuning, and the same composition CWM uses.
2. **`samples[].metadata` was unread.** It carries the sample's recorded
   `rootNote` and a `tune` offset. The root is now the fallback when a layer's
   `rootNote` is the 0 "unset" sentinel (preferred over the WAV `smpl` unity
   note, since it is what the MPC itself displays), and `tune` is added to
   `TuneFine` as cents.

   **Mind the bases.** `samples[].metadata.rootNote` is **0-based** MIDI;
   `layersv[].rootNote` is **1-based**. Verified on 71/71 layers across all
   three files: the metadata root equals the note number in the sample's own
   filename, the layer root equals that number **+ 1**. `_mpc3_to_xml()`
   normalises everything to the 1-based `<RootNote>` convention, so the
   metadata fallback is written **+1**. This also settles checklist item A2
   without hardware — the file states the same fact twice, in two encodings.

Both are 0/default in every local file, so they are read-side only until a
non-default program turns up. Tested by mutating a real file: `transpose` +7 /
−5 / net +2 / +2.5 (fractional → 2 semitones + 50 cents), `rootNote` forced to
0 (falls back to the identical root), and `tune` 0.5 (→ +50 cents). Output on
the three unmodified files is **byte-identical** to before, the classic XML
path is unchanged across 60 real XML `.xpm` files, all 51 tests pass, and
`K2-01.xpm` still converts to the same 7.06 MB / 21-zone E4B.

**Three bugs found in CWM's MPC 3 JSON reader** while doing this crosscheck,
all in `format/akai/mpc/` at CWM `e8027b9d`. Kept here as format knowledge —
each one is a statement about the *format*, which is why it is worth having
even though passing them upstream is not a tracked action:

- **`layersv[].rootNote` is 1-based and CWM reads it raw.**
  `MPCModernDetector.readJsonSampleZone()` calls `setKeyRoot(rootNote)` with no
  adjustment, so every MPC 3 keygroup import lands **one semitone sharp**. The
  proof is inside the same method: `samples[].metadata.rootNote`, its fallback
  when `rootNote == 0`, is 0-based — so the two branches use two different
  bases. This is the same 71/71 evidence recorded above.
- **The global-envelope branch is dead code.**
  `MPCEnvelopesAndFilter(node, isGlobal=true)` looks for `ampEnvelopeGlobal` /
  `filterEnvelopeGlobal` / `pitchEnvelopeGlobal` **inside `synthSection`**, but
  in real files those flags are siblings of `synthSection` on the `keygroup`
  node. They therefore always read false, `globalEnvelopesAndFilter` is always
  empty, and a program using global envelopes silently imports the
  per-keygroup ones. No user-visible difference *today*, because that fallback
  happens to be the right answer while the flags are off — which is exactly
  what makes it worth writing down.
- **`MPCFilter` drops filter types 19–28.** `FILTER_TYPES` is populated for
  1–18 and 29 only, so Band-Boost (19–22), Model1–3 (23–25) and Vocal1–3
  (26–28) yield `type == null` and the filter is discarded outright. mpc2emu
  maps all of them (`_XPM_FILTER_TYPE`, `writers/e4b_writer.py`), including the
  hardware-RE'd band-boost = band-stop-with-inverted-gain result (§BB).

The crosscheck also **agreed** on the substantive things, which is the more
important outcome: identical filter enumeration 1–18/29, identical
`{value0,value1}` slot reading, identical AD-mode ⇒ sustain-0 handling, and
the same two-tier loop scheme.

**Also fixed:** the `filter_type` comment in `models/common.py` described a
9-value enum (`0=off, 1=LP12, 2=LP24, 3=LP48, 4=HP12…`) that **nothing in the
codebase uses** — the operative table is the full MPC 0–29 enum in
`_XPM_FILTER_TYPE`. Behaviour was always correct; the docstring on the
canonical field that six parsers write into was not, and it briefly sent this
crosscheck down a false trail.
## §E4BSTEREO — E4B stereo samples: layout RE'd from the corpus, decode bug fixed, write side implemented (2026-07-29)

**Context:** Jan pushed back on a code comment claiming "E4B supports only
mono samples" — *"I can sample in stereo on the hardware"*. He was right;
the comment was wrong about the format and right only about mpc2emu.
Investigating it turned up a live decode bug, not merely a missing feature.

### The layout, read off real banks rather than guessed

Scanned every `E3S1` object in **473 local `.E4B` files (20,383 samples)**:

| `options & 0x0060` | meaning | count | share |
|---|---|---:|---:|
| `0x20` | LEFT only (mono) | 15,492 | 76.0% |
| `0x40` | RIGHT only | 88 | 0.4% |
| `0x60` | **BOTH — stereo in one object** | **4,803** | **23.6%** |

So a stereo sample is **one object with both channel bits set**, not two
linked L/R objects. The E3S1 struct is the Emulator III's and stores every
position twice — start/end/loop-start/loop-end at 22/30/38/46 (left) and
26/34/42/50 (right) — and the two channels sit in **sequential PCM blocks**,
not interleaved. From `a stereo slide sample`:

```
startL=92     endL=154458      startR=154460   endR=308826    pcm=308736
loopSL=104    loopEL=154448    loopSR=154472   loopER=308816
```

`startR == endL + 2`, the two blocks are equal (154,368 B each) and together
span exactly the PCM, and the loop offsets are identical *relative to each
channel's own base*. A position `p` addresses body offset `p + 2` (the
2-byte `sample_idx` sits in front of the 92-byte header) and `end` is
inclusive of its own frame.

### The bug this exposed

`e4b_parser` read that whole region as ONE mono block, so a stereo sample
imported at **double length and played left-then-right**. Roughly a quarter
of the corpus. Fixed by de-planarising to mpc2emu's interleaved internal
form with `channels = 2`.

The model needed no change: `resampler`, `start_trim`, `tail_trim`,
`auto_loop` and `loop_renderer` all already compute frames as
`len(data) // (2 * channels)`. **Only the parsers never set it** — the
plumbing was there the whole time, which is why this was much smaller than
the TODO estimated.

### Write side

`e4b_writer` now emits stereo: both channel bits, the L/R start/end and
loop pairs, `sample_data_offset_r`, and PCM de-interleaved to planar on the
way out. Written samples reproduce the corpus shape exactly (`startL=92`,
`startR = endL + 2`, equal blocks, equal per-channel loop offsets).

`krz_writer`/`eiii_writer` cannot emit stereo yet, so they now call
`ensure_mono` **explicitly** at entry and log it. This mattered: no writer
looked at `channels` at all, so once the parser produced stereo, interleaved
PCM would have been measured as mono and written at double length and wrong
pitch.

### Why `--stereo` is opt-in

Reading stereo correctly is a bug fix and always on. *Keeping* it is a flag,
because stereo doubles every sample against a 128 MB bank cap — silently
enabling it would change every existing conversion and could push libraries
that fit today over the limit.

### Verification

- Mono cannot regress: the mono decode paths (including the right-only
  special case) are untouched, and over 25 real banks **all 10 mono-only
  banks parse byte-identically** while exactly the 15 stereo-containing
  banks change. Mono writer output is byte-identical to `main`.
- Round-trip: a synthetic stereo sample with deliberately different L and R
  survives write→parse bit-exact, no channel swap, loop preserved.
- End-to-end: a stereo WAV (L 220 Hz / R 330 Hz) through
  `load_wav → E4B → parse` returns both channels bit-exact.

**Found while verifying — FIXED 2026-07-31.** E4B output was
**nondeterministic**: two runs of the *same* code over the same input differed
by millions of bytes because sample ordering varied, while the semantic
content was identical.

Root cause: `bank_splitter.split_into_banks` gathered each preset's samples by
iterating a **set** of sample names. Python randomises string hashing per
process, so the order differed between runs. `preset_needed_samples` in the
same file already had it right — build the name set, then iterate the sample
*list* and filter — and that pattern is now used in both places.

Verified by conversion, not by inspection: the same XPM converted twice
differed by 6.27 MB before and is byte-identical after, including across three
explicitly different `PYTHONHASHSEED` values, with the sample set and PCM
content unchanged. `tests/test_determinism.py` pins the property; reverting
the fix fails two of its three tests.

Why it was worth fixing rather than working around: byte-comparison is the
cheapest and strictest regression check available when touching a writer, and
this made it useless — which is precisely when you least want to be without
it.

**Audit of the other writers (same day): clean.** An AST pass over `writers/`,
`parsers/`, `processors/`, `models/` and `convert.py` found only **two**
set-iteration sites, and neither can affect output order — one is a boolean
`any()` inside a counter (`eiii_parser`), the other picks its result by
minimum recorded traversal position rather than by iteration order
(`xpm_parser._find_wav`, made that way deliberately; its comment says so).
Dict iteration elsewhere is insertion-ordered in Python 3.7+ and therefore
safe. The worker pools in `resampler`, `auto_loop` and `single_cycle` all use
`ProcessPoolExecutor.map`, which preserves input order.

Confirmed empirically rather than by reading: `--format e4b`, `krz`, `eiii`
and `talsmpl` all produce byte-identical output across different
`PYTHONHASHSEED` values, including `talsmpl`'s 21 exported WAVs.

*Method note, because it bit me:* comparing `find | xargs md5sum` output
between two runs reports a difference even when every file matches, since
`md5sum` prints the path and the two runs live in differently-named
directories. All four formats looked nondeterministic until the comparison
was done per file. `md5sum` on a directory also fails silently and compares
"equal", which turned an unchecked `samples/` directory into a false pass.

### Offline confirmation round (2026-07-29) — what raised confidence short of hardware

Asked how certain the stereo work is without a hardware re-check. Four
independent offline checks, in rough order of how much they moved the needle:

**1. Round-trip against E-mu's own bytes (strongest).** Parse a real stereo
sample, re-encode its header with `e4b_writer`, diff field by field against
the original. Over **509 real stereo samples**:

| field group | agreement |
|---|---|
| block layout (`start_l/r`, `end_l/r`) | **509/509 (100%)** |
| loop fields, **looped** samples | **180/180 (100%)** |
| loop fields, unlooped samples | 0/329 — leftover values EOS ignores with the loop bit clear |

This is close to a closed loop: the decode must be right for the encode to
regenerate E-mu's bytes. Four other fields differ (`pitch`, `options` bit
`0x08`, `dataOff_l/r`) — but they differ **identically for mono**, and mono
E4B output is hardware-confirmed, so EOS demonstrably tolerates them.
(`0x08` is set on 97.4% of mono and 97.9% of stereo samples; we have never
written it, mono included.)

**2. A false alarm worth recording.** A mono-vs-stereo differential over all
94 header bytes flagged bytes 73-93 (`parameters[6]`, documented `{0…0}`) as
varying in stereo but constant in mono — i.e. a field we might be failing to
write. It is **uninitialised buffer padding**: only 5.75% of stereo samples
have anything there, 100% of mono have zeros, the values decode as smooth
audio ramps, and 88 of them are literally byte-copies of the sample's own PCM
found elsewhere in the same sample. Writing zeros is correct. Recorded so the
next person does not re-investigate it.

**3. EOS 4.0 manual, p.93 "Combine L/R into Stereo".** Independently confirms
the corpus RE: left/right samples are *"combined into a **single stereo
sample**"* (one object, not two linked ones), *"Program parameters for the new
stereo sample are taken from the left sample. **The right side parameters are
ignored**"* (so mirroring the left loop points onto the right, as the writer
does, is safe), and *"when this function is disabled, each sample is placed in
a **separate voice**"* — implying a combined stereo sample occupies **one**
voice, so no change is needed to voice-count or preset-size accounting.

Also p.~10095: EOS's own Stereo→Mono *"sums both sides of the stereo sample,
then divides by two"* — exactly the `(l + r) >> 1` in `models.common.
stereo_to_mono`, now validated against the manufacturer's own definition.

**4. ConvertWithMoss cross-check — no corroboration available, because they
have the same bug.** `Emulator4Detector` hardcodes
`DefaultAudioMetadata(1, …)` and takes the whole PCM region as one mono block,
exactly as mpc2emu did. They handle the right-channel-only loop-field case
(their PR #242, which we adopted) but never noticed the both-channels case.
Their Creator downmixes on write (`isStereo ? mixToMono(wavData) : wavData`).
So this finding is novel and there is no second implementation to check
channel ORDER against.

### Residual risk, honestly

- **Channel order (L/R vs R/L) is the one thing offline work cannot settle.**
  It rests on two prior independent RE efforts naming the first block left:
  emu3bm's `struct emu3_sample` (`start_l` before `start_r`) and the EIII's
  `SAMPLE_START_LEFT = 0x14` before `_RIGHT = 0x18`. Low risk, and the failure
  mode is a mirrored image rather than corruption. Four real stereo samples
  are exported as stereo WAVs to `~/temp/stereo_audition/` so it can be
  settled by ear on a familiar library, no hardware needed.
- **The write side is not hardware-proven.** Every meaningful field matches
  E-mu across 509 samples, but this project's own history (the voice-count
  trailer, the silent-KRZ bug, the ISO `props[5]` marker) is a standing
  reminder that byte-correct files can still fail on the device.

### Hardware checklist — DONE 2026-07-31, except item 4

Confirmed on the E4XT with the combined open-HW-RE bank, measured rather than
judged by ear: notes driven over MIDI, audio captured from JACK, analysed per
channel (`tests/re_banks/hw_measure.py`).

1. **Loads.** ✅ No "Unknown file type" / IFF complaint.
2. **Plays in stereo.** ✅ The two sides carry different content.
3. **Channel order is correct.** ✅ Left is left. Measured per channel on the
   deliberately asymmetric material: a left-only key gives L 440 Hz / R silent
   (rms 0.092 vs 0.00006), the right-only key the exact mirror, and the
   split-pitch key gives **440 Hz left / 659 Hz right** — the low tone on the
   side its sample stores it. This is the item no offline work could settle;
   it rested on emu3bm and the EIII naming the first PCM block left, and that
   inference is now confirmed. Independently corroborated a second time
   through the pan path (below).
4. **A stereo sample costs TWO voices.** ✅ Measured 2026-07-31, third attempt.
   Level of a DETUNED stack (which sums incoherently, so level tracks √N)
   follows √N exactly up to **32** stacked mono voices and up to **16** stacked
   stereo voices — a clean 2:1.

   The first two attempts both failed to a level ceiling masquerading as a
   voice ceiling, and the second nearly produced a confident wrong answer:
   identical stacked voices sum COHERENTLY, so 128 sat 42 dB above one and
   saturated something long before the polyphony limit — and because a stereo
   voice starts 1.65× louder, it saturated at ~0.6 of the mono depth, which is
   very close to the 0.5 that the true answer produces.

   Detuning settles it two ways. A shared level ceiling would break stereo at
   32/5.6 ≈ 6 voices, not the observed 16; and more conclusively the two
   ladders plateau at **different levels** (mono ~250–300, stereo ~420–490),
   which no common level ceiling can produce. Feeds `--max-preset-size` and
   the voice-limit logic.

   *Incidental:* the ceiling is ~32 mono voices **on one note**, not the
   E4XT's 128-voice global polyphony — so it looks like a per-note layer
   limit. Separate question, not chased.
5. **Pan MONO-SUMS a stereo voice** onto the pan position — it does not
   balance, and it does not discard a channel. ✅ Measured: at hard left the
   LEFT output carries **both** source pitches (440 + 659) and the right is
   silent; hard right is the mirror; centre preserves the image (distinct
   pitches per side). The summed level is 0.131 ≈ 0.092·√2, exactly two
   channels folded into one.

   **Consequence for the writer:** a non-centre pan on a stereo voice costs
   the stereo image, not content. Keep stereo voices centred, or warn — the
   earlier guess that extreme pan *drops a side* was wrong, so suppressing pan
   to protect a channel would be solving the wrong problem.
6. **Looped stereo loops in sync.** ✅ Measured 2026-07-31 on a sample
   carrying 220 Hz left and 330 Hz right with a 4410-frame loop (an exact
   whole number of cycles on both sides, so any drift would beat). Held well
   past the loop point, each channel holds its own pitch exactly — L 220.0 Hz,
   R 330.0 Hz at both 0.5-1.5 s and 4.0-5.0 s — with level steady to within
   3%. Both blocks loop, and they stay in sync.

**All six stereo questions are now settled.** The write side is confirmed on
hardware end to end: loads, plays in stereo, correct channel order, pan
mono-sums, and loops hold sync. The only stereo work left is the KRZ path,
which is still mono in both directions (see TODO).

**Method note worth keeping.** The first pan reading was inferred from a
by-ear report of "different pitches on each side" and concluded *balance*.
That was wrong: the keys involved were transposed copies of one sample from a
single root, so the differing pitches were transposition, not channel
selection. Only a per-channel FFT settled it — and note that analysing a
mono-summed capture would have destroyed exactly the evidence needed. For any
stereo question, keep L and R separate all the way to the measurement.

## §MONO — Stereo is the default; mono is a vintage-fit reduction (2026-07-29)

**Context:** the first cut of the stereo work shipped `--stereo` as an opt-in
passthrough, defaulting to the old mono downmix. Jan rejected that framing on
two counts, both right: stereo input should default to stereo output, and
"reduce to mono" belongs with the other memory-fit options rather than being
the default behaviour you opt out of.

### Resulting split of responsibility

- **Parsers are faithful.** `load_wav` preserves the source's channel count
  unconditionally. Reading is the parser's job.
- **Reduction is explicit.** `--mono [mix|left|right]` sits in the vintage-fit
  family (`--reduce-key-zones`, `--reduce-velocity-layers`,
  `--max-sample-rate`) and runs before resample/fit/split so everything
  downstream sees the halved sizes. Halving a stereo sample is the single
  largest saving available and is usually what keeps a stereo library inside
  the 128 MB bank cap.
- **Writers that cannot emit stereo downmix at entry** (`ensure_mono` in
  `krz_writer`/`eiii_writer`) and say so, so nothing silently mis-measures
  interleaved PCM as mono.

### Why `left`/`right` exist, and why they are not exotic

EOS's own Stereo→Mono is *"sums both sides, then divides by two"* (manual
p.~10095), which `stereo_to_mono` matches exactly. But summing is only safe
when the sides are coherent. Measured across **95 real stereo E-mu samples**:

| L/R correlation | count |
|---|---:|
| r > 0.95 (detuned duplicate, "fake stereo") | 0 |
| 0.5 < r ≤ 0.95 (wide) | 38 |
| r ≤ 0.5 (decorrelated) | 57 |

Median r = **0.107**, some negative. These are genuine room recordings of
string sections, not fake stereo. Summing decorrelated — let alone anti-phase —
content cancels signal. The degenerate case is exact: averaging `(100, -100)`
gives `0`.

(The original argument for channel-pick was the opposite one: EOS's manual
mono→stereo *"duplicates the sample on both sides and slightly detunes them"*,
so summing THAT back comb-filters. That is a real hazard but does not occur in
this corpus — nobody used that Sample Edit utility on these banks. The
justification survives inverted: wide real stereo cancels for a different
reason than fake stereo does.)

### `--mono auto` / "pick the best channel" — investigated and REJECTED

Worth recording so it is not re-proposed. Measured per-channel RMS, peak,
clipping and correlation over **247 real stereo samples**:

| signal an auto-picker would use | corpus reality |
|---|---|
| dead / near-silent channel (>20 dB asymmetry) | **0** (max 7.1 dB) |
| highly correlated, so averaging is safe (r > 0.9) | **0** (median 0.076) |
| RMS asymmetry as a tiebreak | median **1.05 dB** |
| one-sided clipping | 78 flagged, but at counts of 1/0 — a single peak
  touching full scale, not clipping; the metric was too naive to trust |

Every branch either never fires or decides on ~1 dB, so `auto` would collapse
to "pick the marginally louder side" while presenting itself as a judgement.
Not built. **Caveat on scope:** this corpus is dominated by one vendor's string
libraries. Drum machines, synth patches and genuinely fake-stereo material
could well contain dead channels and r > 0.95 pairs, so the negative result is
about *this* corpus, not about the idea in general. If it is revisited, base it
on the two objective rules (dead channel, real clipping via run-length
detection) and follow `_choose_repair_candidate`'s pattern: only override the
baseline when decisively better.

### What was built instead: an advisory

Since r > 0.9 never occurs, averaging is usually the lossy choice here. So
`--mono mix` measures `channel_correlation` per sample *before* reducing it and
warns below 0.3 (well clear of the 0.076 median), naming the worst case and
pointing at `--mono left/right`. The user keeps the decision and the risk stops
being invisible — better than a heuristic guessing on their behalf.
`channel_correlation` is windowed to 20k frames to keep it off the critical
path.

## §E4BFILTCAL — Cutoff, resonance and zone-gain measured on the E4XT (2026-07-31)

Measured with the second open-HW-RE bank, driven and captured by
`tests/re_banks/hw_measure.py`.

**Where the tap is, and why it matters.** Recording is from the JACK
*hardware capture* ports (`system:capture_15/16`), which is the E4XT's feed
into the interface. On this rig those same ports also feed an EQ whose output
goes through Sonarworks room correction to the monitors — so the recorder and
the monitoring chain are parallel taps on one source, and the measurement sits
upstream of both. Recording the EQ's or Sonarworks' *output* instead would
convolve every reading with a room-correction curve: spectra would tilt, every
−3 dB corner would move, resonance peaks would change height, and a
verification pass would reproduce the same error and read as a confirmation.
Verified before trusting any of the numbers below. The material is **white noise**, chosen after
the first attempt used a 110 Hz harmonic saw that ran out of content at
2.6 kHz and left most of the cutoff range unmeasurable.

### Cutoff position → Hz: our model is wrong above about 0.3

The −3 dB corner, read off the noise spectrum in 1/6-octave bands:

| position | measured | `hz_to_e4b_cutoff` model | measured / model |
|---------:|---------:|-------------------------:|-----------------:|
| 0.0 | 133 Hz | 57 Hz | 2.34× |
| 0.1 | 168 Hz | 102 Hz | 1.64× |
| 0.2 | 238 Hz | 184 Hz | 1.29× |
| 0.3 | 378 Hz | 331 Hz | 1.14× |
| 0.4 | 534 Hz | 594 Hz | 0.90× |
| 0.5 | 755 Hz | 1068 Hz | 0.71× |
| 0.6 | 1068 Hz | 1919 Hz | 0.56× |
| 0.7 | 1199 Hz | 3447 Hz | 0.35× |
| 0.8 | 1903 Hz | 6194 Hz | 0.31× |
| 0.9 | 3390 Hz | 11130 Hz | 0.30× |
| 1.0 | >20 kHz | 20000 Hz | — |

Log-linear fit over 0.0–0.9: **`Hz = 125.9 · e^(3.494 · position)`**, r = 0.9958.
That implies ~126 Hz at position 0 and only ~4.1 kHz at position 1, against the
57 Hz / 20 kHz the current constants assume.

**Position 1.0 is a bypass, not the top of the curve.** It measures wide open
(>20 kHz), which is nowhere near the fitted trend's 4.1 kHz — so the control
is an exponential sweep up to roughly 4 kHz with a fully-open endpoint, not a
single exponential to 20 kHz.

**Consequence.** Parsers that specify a cutoff in Hz (SF2, EXS24, GIG, SFZ)
run it through `hz_to_e4b_cutoff` to get a position. Because the real curve is
much shallower, a request for 3.4 kHz picks position 0.70 and the hardware
delivers **1.2 kHz** — roughly an octave and a half too dark. The error is
small below ~400 Hz and grows to 3× by the top of the sweep.

*Caveats:* one filter type (4-pole lowpass), and the −3 dB corner is our
definition, which need not match E-mu's design frequency. Neither explains a
3× divergence.

### Resonance: clean and monotonic

Peak boost over the passband, at cutoff position 0.4:

| resonance | peak boost | peak at |
|----------:|-----------:|--------:|
| 0.00 | +2.2 dB | 305 Hz |
| 0.20 | +7.7 dB | 604 Hz |
| 0.40 | +15.9 dB | 639 Hz |
| 0.60 | +23.3 dB | 668 Hz |
| 0.80 | +30.1 dB | 721 Hz |
| 0.95 | +37.1 dB | 750 Hz |

Monotonic, roughly 39 dB per unit, and the peak converges on the corner as Q
rises. Nothing self-oscillates at 0.95 — broadband level actually falls
slightly as resonance concentrates energy. No change needed.

### Per-zone gain: the label is dB, the behaviour is not

13 points, identical source, filter open, only `ZoneMapping.volume` varying:

| requested | measured | error | measured/requested |
|----------:|---------:|------:|-------------------:|
| −2 dB | −0.91 | +1.09 | 0.46 |
| −6 dB | −2.97 | +3.03 | 0.50 |
| −12 dB | −7.28 | +4.72 | 0.61 |
| −18 dB | −11.54 | +6.46 | 0.64 |
| −24 dB | −18.05 | +5.95 | 0.75 |

The delivered fraction climbs from 0.46 to 0.75, so this is a curve, not an
offset — a 3-point correction could not have captured it, which is why the
ladder was rebuilt with 13.

**Why this slipped through.** `vpar[54]` is documented as "signed byte, dB;
0 = unity — hardware-confirmed 2026-07-26", and `_zone_entry` writes the dB
value straight in. That confirmation established that the **front panel
displays** the value we write; it never established that the **audio** matches
it. This is the same trap as §E4BLEVEL, where the amp-envelope sustain byte
read 50% on the panel and measured −46 dB. Two independent parameters have now
shown the same pattern, so *"the panel agrees"* should not be recorded as
hardware confirmation of a level law again — only a measurement counts.

### Both corrections are now HARDWARE-VERIFIED (2026-07-31)

Fixed in `writers/e4b_writer.py`, inverted in `parsers/e4b_parser.py` so the
two stay exact inverses, and replayed on the E4XT through a bank built the way
a real conversion builds one — so a pass means *measured == requested*, with
no correction arithmetic at analysis time.

| ladder | result |
|--------|--------|
| **Cutoff**, 12 points 150 Hz–18 kHz | **12/12 pass** — including the four above 2920 Hz that the earlier fitted exponential would have clamped |
| **Gain**, 7 points 0 to −18 dB | **7/7 pass**, max error **0.34 dB** (was 6.5 dB uncorrected) |
| **Pan**, 7 points −1.0 to +1.0 | **monotonic across the whole range**, symmetric; −0.6 and −1.0 now 34.3 dB apart where they were previously identical |

All three re-verified 2026-07-31 after the cutoff law was replaced by the
measured table and pan was corrected from ×64 to ×32.

**Two false starts on the way, both worth remembering.**

*The correction was applied twice.* `convert.py` re-parses an E4B to build an
ISO, and the parser still read `vpar[60]/255` as a nominal position after the
writer began emitting a corrected byte. That broke the writer/parser inverse
property for every E4B→E4B conversion, not just the test bank — and it only
surfaced because the verification bank checked the *output*, independently of
the arithmetic that produced it.

*The first gain fit was contaminated.* It measured a strongly curved law; the
truth is almost exactly linear (~0.767 dB per byte unit, residual 0.33 dB).
Two candidate confounds were then measured directly and **both came back
flat** — output level does not depend on key (±0.00 dB across C1–C6 with a
non-transposing voice) and does not depend on velocity (+0.00 dB from 5 to
125). **So the reason the two datasets disagree by ~2 dB in the middle, while
agreeing at both endpoints, is still unexplained.** The linear law is the one
that verifies on hardware, so it is the one in the code; that is a stronger
claim than understanding the discrepancy, and the discrepancy stays open.

*How to actually close it (2026-08-11).* The honest description of that 2 dB
is **two numbers, each measured exactly once, differing by an amount neither
one carried an error bar for** — which was true of every hardware measurement
this project had taken until today. It is not noise — but see the correction below on
*how far* from noise.

*Correction, 2026-08-11, measured not assumed.* This note first said 2 dB is
**59×** the floor, from the 0.39 % instrument repeatability (0.034 dB). Wrong
denominator: that figure is the recording chain alone, and the quantity that
matters is how much the whole measurement — capture, segmentation, plateau
estimation — moves between takes. Two takes of the same sweep are in the
archive (`level_cal_take2/3.wav`), and running one analysis over both gives a
per-note difference of **0.30 dB mean, 0.39 dB max**, nine notes. That is **9×
larger** than the instrument figure, so the honest comparison is

    2 dB / 0.30 dB ≈ **6.7×** take-to-take scatter, not 59×.

*And 6.7× is still not the right comparison — a third denominator, 2026-08-12.*
s3ked, measuring `FILQ`: **"the null pass's 0.016 dB measured whether one path
repeats, not whether two paths agree — the real rms is 0.274 dB, 17× that."**

That is the exact shape of the 0.30 dB above. It was take2 against take3 through
**one** analysis, so it measures whether a single path repeats. The 2 dB gap is
between two *datasets* that may have been reduced by two different analyses —
and the denominator for that comparison is the **between-path** scatter on the
same data, which nobody has ever measured here. Their two paths differed by 17×
their within-path figure.

So the honest statement of the open item is now: 2 dB against a within-path
scatter of 0.30 dB, with the between-path scatter **unmeasured and plausibly
several times larger**. 6.7× is an upper bound on how anomalous the gap is, not
an estimate of it. That is the third denominator this note has used, and each
correction has moved the same direction — toward the gap being less remarkable
than it first looked.

It also cannot be computed from the archive, for the reason recorded below:
which analysis produced each dataset is written down nowhere.

Still comfortably real, and still with a cause. But 59× was a claim about a
quantity that was never the right comparison, and it would have made the gap
look far more anomalous than the evidence supports. **This is the project's
first error bar on a level measurement** — it was recoverable from the archive
because these two takes are of the same conditions.

Two things fell out of the same pass, both worth keeping:

* **The self-normalisation is sound.** `analyze_envelope_recording.py --mode
  level` divides each note's plateau by *that note's own attack peak*, valid
  only if the peak is constant across the sweep. Measured: constant to
  **0.01 dB** across all nine notes in both takes. A ratio pinned to its own
  peak would have produced errors that vanish at the endpoints and concentrate
  in the middle — exactly this discrepancy's signature — so this was a strong
  candidate, and it is now excluded.
* **The analyser silently drops notes.** Two of nine came back
  `(plateau too short)` in one take and were simply absent from the output. A
  sweep that quietly measures 7 of 9 points still prints a clean-looking
  table. The procedure, from s3ked's V_LOUD re-measurement of 2026-08-11 (cited by date and subject, not by hash — they rebase, and every hash this file cited on 2026-08-12 was orphaned within a day), where a 17 dB version of this
turned out to be a fault in the model rather than in the data:

1. Re-measure **both** configurations back to back in one session, with every
   parameter write read back to confirm it took.
2. `replicate(measure, n=3)` on each condition
   (`tests/re_banks/hw_measure.py`) so the comparison has a within-condition
   scatter to be judged against, then `separable()` rather than eyeballing the
   gap. Note its verdict is an effect size, not a significance test — see its
   docstring before reading 'undecidable' as 'no difference'.
3. Do not reach first for the ceiling explanation. A ceiling compresses the TOP
   of a curve; ours agrees at both endpoints and diverges in the middle, which
   is the wrong shape. A bad fit is consistent with many faults, so looking for
   support rather than refutation will find some.

Velocity and key are already excluded as confounds by direct measurement
(above) — worth keeping, because s3ked's fault was pinning a variable at its
extreme *without* that check.

*A diagnosis added and then withdrawn the same evening, 2026-08-11 — kept
because the withdrawal is the useful part.*

For about half an hour this note said the 2 dB was most likely an
**underdetermined quantity**, on the strength of s3ked hitting the same
signature on `ATTAK1` (two fits, each at r² 0.99991, disagreeing 13–20 %) and
on their 33 % disagreement between two implementations of "10–90 % rise"
inside one project, which had been attributed to unwritten choices about
baseline, truncation and peak estimation.

**Both legs were withdrawn by s3ked within the hour.** The 33 % was a plain
selection bug — one implementation took the last sample inside the 10–90 band
rather than the last of the first contiguous run, which reads long, as
predicted. `ATTAK1` and `ATTAK2` were both re-measured after the fix and
settled; two definitions sharing no arithmetic now agree to 0.19 % on the
exponent. Their published coefficients had never been more than 1.3 % wrong.
What had been wrong was the *confidence interval*, built by comparing two
implementations one of which was broken.

The line that survives, and it is the one to apply here:

> **A disagreement between two of your own tools bounds their difference, not
> the measurement's uncertainty.**

That is sharper than what it replaced, and it points the other way. Our two
gain datasets disagreeing by 2 dB is, first and most cheaply, evidence that
**one of our two analyses has a bug** — not evidence about the E4XT. s3ked
found the same selection fault three times in three hand-rolled selections,
each an aggregate taken over a whole record when the region of interest was a
small and varying fraction of it. Our two runs are exactly that shape.

So the revised order at the bench:

1. **Instrument before theorising.** s3ked burned two hardware runs on two
   plausible hypotheses about a NaN before a diagnostic that simply printed
   every intermediate answered it immediately. Print the intermediates of both
   analyses on the *same* capture first — that costs no bench time at all and
   would settle a tool-difference without the machine.

   **Attempted 2026-08-11, and it is blocked — for an avoidable reason.** The
   July captures survive (`~/temp/amp_level_cal/*.wav`) but **their schedules
   do not**: `play_sequence` returned the note on/off times and never wrote
   them anywhere. Segmenting an archived capture without its schedule is
   guesswork, and it does not degrade gently — two segmentations written half
   an hour apart read the *same* file as −55.1/−43.1/−30.1/−19.0 dB and as
   −24.8/−24.4/−24.6/−24.2/−19.2 dB. Both looked reasonable in isolation.

   One other thing the archive shows, and it is a candidate the ceiling and
   underdetermined-quantity hypotheses both missed: `models/common.py:434`
   records the sweep as *narrowband-analysed against the test tone's own
   frequency to reject recording noise floor*, while a broadband RMS of the
   same capture is a different measurement entirely — they diverge wherever
   the noise floor is a meaningful fraction of the signal. Whether the two
   datasets used the same one is **not written down anywhere**, which is
   precisely the gap. Do not treat this as the answer; treat it as the first
   thing to check, because it is checkable from the archive.

   `play_sequence` now writes a `.sched.json` sidecar beside every capture
   (note times, program, velocity, controls, device, capture ports, UTC
   timestamp), so this specific dead end cannot recur. It does not recover the
   July sessions.
2. Only if both tools agree on one capture does the disagreement become a
   fact about the sampler worth spending a session on.
3. Then the operational-definition question, and `replicate(n=3)`.

Note that r² cannot see any of this: both runs fit beautifully, and so did
both of s3ked's while one was broken. Goodness of fit measures agreement with
a model, never agreement with reality.

**Blocked on:** bench time only.

---

## §POLY — Per-note voice budget: teaching the size/fit path that stereo costs double (2026-08-01)

**Implemented.** The two facts came out of the 2026-07-31 bench session
(§E4BSTEREO item 4): a stereo sample costs **two voices**, and the ceiling is
**~32 voices on one NOTE**, not the E4XT's 128-voice global polyphony. Neither
had reached any code.

### What the estimate has to get right

Three things, and only the first is obvious:

1. **Stereo doubles.** `sample_voice_cost()` — 2 if `channels >= 2`.
2. **Zones inside one voice layer do not stack.** An E4B voice sounds only one
   matching zone per note. That is precisely why SFZ overlapping regions had to
   be split into parallel *voices* rather than piled into one voice's zone
   table (see the SFZ overlapping-region strategy above). A 155-zone
   single-layer import costs **one** voice. An estimator that counted zones
   would fire on nearly every multisample in the corpus, and a warning that
   cries wolf gets ignored — which is worse than no warning.
   Where zones within one layer overlap, which one EOS picks is not modelled,
   so the estimate takes the dearer (stereo) one.
3. **The peak is not at the extremes.** Layers with velocity ranges 0–99,
   50–127 and 64–90 all overlap only in 64–90; sampling velocity 0 or 127 sees
   two layers, not three. The peak of a step function over closed intervals is
   always reached at some interval's lower edge, so `peak_note_voices()` sweeps
   the distinct `lo_vel` values (plus 0) against all 128 keys. Cost is
   `vel_edges x layers x 128`, which is nothing.

### Scope: e4b only

`_VOICES_PER_NOTE = {'e4b': 32}`. The K2000 and EIII have smaller voice budgets
and no per-note limit has been measured on either — and both paths are still
mono-only, so the stereo cost cannot bite there anyway. Warning on a guessed
number would be inventing a hardware fact, which is the one thing this
project's notes have consistently refused to do. Add a row when a bench session
produces one.

### What was NOT wrong

The byte estimate. Stereo PCM is naturally twice the bytes and
`len(sample.data)` already counted it, so `--max-preset-size` never
under-counted *size*. The TODO entry's "under-count by 2x" phrasing conflated
the two ceilings. Voices are a **separate** budget: a preset can be trivially
small in bytes and still steal voices, which is exactly why the check runs on
every preset rather than only on the oversized ones the fit assistant sees.

### Open question for Jan — should `--auto-fit` act on this?

Today the fit assistant triggers on **bytes only**. An over-budget preset that
fits by size gets a warning naming the two flags that fix it (`--mono`,
`--reduce-velocity-layers`) but is written unchanged.

- **For acting:** voice stealing is a real playback failure, and which layers
  survive is arbitrary — arguably worse than a bank that is merely too big,
  because it looks like it worked.
- **Against:** `--auto-fit` is documented as fitting *oversized* presets.
  Silently thinning a preset that fits every stated limit is a surprise, and
  the honest fix is often `--mono`, which is a fidelity decision the user
  should make rather than have made for them.

Recommendation: leave it as a warning. Revisit if a real bank turns up where
the warning fires and the suggested flags are not the right answer.

### Verification

`tests/test_polyphony.py` — 21 assertions covering the cost rule, the
non-stacking cases (key splits, velocity splits, zones within a layer), the
partial-velocity-overlap peak, out-of-range and dangling zones, and the
warning's on/off boundary at exactly 32 mono / 16 stereo. End-to-end on an
18-layer stereo SFZ: warns at 36 voices, and both suggested flags clear it.
Write→read→estimate agrees: re-parsing that bank returns 36 as well, so the
writer, the E4B parser and the estimator all count the same voices.

**A/B against the pre-change tree** (worktree at `4ab9584`): 56 conversions —
a 33-file corpus across sfz/sf2/xpm/exs/pgm, run for e4b, krz and eiii, with
and without `--auto-fit` — produced **byte-identical output in every case**.
The change is purely additive; nothing written moved.

**The corpus scan is the real validation**, and it is the check worth
repeating if this code ever changes. Running the estimator over every local
E4B bank — **385 banks, 1706 presets** — puts **4 presets** over the budget,
0.23%. All four are `P_VMONO` (128) and `P_VSTER` (256) in `OHWRE2B`/`OHWRE3B`:
the deliberately-built voice ladders from the 2026-07-31 bench session that
*established* the limit. Nothing else in the corpus trips it, and the
next-highest preset is `P_VSPREAD` at exactly 32 — the "32 voices on each of
four keys" bank, which sits on the boundary and correctly stays silent.

That the estimator independently rediscovers exactly the presets built to
exceed the ceiling, and flags no ordinary multisample, is much stronger
evidence than any synthetic fixture. Note also that `P_VSTER` reports 256
voices from **one** stereo sample reused across 128 layers — the doubling
follows the zone, not the sample count.

Cost: **0.092 ms per preset** (158 ms for all 1706), so running it on every
preset of every conversion is free.

---

## §OSFILE — Auditing the corpus count: the raw-byte bank scan over-counted by 9% (2026-08-01)

**Resolved.** ConvertWithMoss `d94bde27` flags that an E-mu volume's
operating-system file (`E3 Main Code`, dircon type `0x80`) is a memory dump
that can itself contain a bank identifier, and skips type `0x80` when reading.
mpc2emu's corpus scan searched **raw image bytes** for the three EIII
identifier strings, so it could not skip anything — and every figure derived
from that scan (§EIII, the sample-index-repair rates, the README claims)
inherits whatever it over-counted.

### Method — build the filesystem reader the project never had

The honest way to answer this is not a heuristic. `docs/EMU3_ISO_FORMAT.md` §2
already documents the volume layout well enough to *read* it, which nothing in
the project had done — `iso_builder.py` only ever wrote one.
`tests/re_banks/emu3_os_file_audit.py`:

1. parses the superblock for the real geometry (all of it — several commercial
   volumes use `cse=1` and `cse=3`, cluster sizes the writer never emits, and
   a `dircon_start` of 9 rather than the writer's 11, so nothing may be
   assumed from the writer's constants);
2. walks every dir-content block for 32-byte entries, keeping the type byte
   (`0x81` file, `0x80` OS image) and rejecting the `0x42`-filler that pads
   the unused directory area on real discs;
3. follows each file's **FAT chain** for its true extent, rather than assuming
   the contiguous allocation the writer happens to produce;
4. locates every identifier hit in the raw bytes, exactly as the original scan
   did, and asks which file — if any — owns that offset.

### Result: the raw count reproduces exactly, so the numbers are comparable

**1118 raw hits**, matching the documented figure to the digit, which is the
check that makes the rest of the table trustworthy:

| where the hit lands | count |
|---|---:|
| head of a real, directory-listed bank | **1017** |
| in FAT-**free** space (deleted / leftover) | 100 |
| inside an OS file (type `0x80`) | 1 |
| embedded in a bank's own data | 0 |
| in a file's slack space | 0 |
| FAT-allocated but unlisted | 0 |

**The corpus is 1017 banks, not 1118 — 9.0% over-counted.** Free-space hits
cluster on a handful of volumes (one contributes 62 on its own, another 18);
most volumes are clean.

### The mechanism CWM warned about is real but negligible here

Exactly **one** hit of 1118 falls inside a type-`0x80` OS file. Every disc
carrying an OS image has one or two (`E3 Main Code`, `E3X Main Code`, 25
across the 22 volumes), but their content almost never begins with, or
contains, a bank identifier. Skipping type `0x80` — the fix CWM applied —
would have removed 1 of the 101 bad hits. **The real cause is different:
deleted banks still physically present in free space.** Worth stating plainly,
because adopting CWM's fix and declaring the problem solved would have left
99% of the over-count in place.

### What this does *not* invalidate

All 100 free-space hits were re-parsed: **every one is a structurally valid
bank** with a sensible name, presets and samples (1496 presets, 2193 samples
between them). They are banks the disc's directory no longer references —
deleted, or left over from mastering — not garbage that merely started with
the right 15 bytes.

So the parser claim and the library claim are different claims and both are
now stated correctly:

- **"read 1118 real bank images, zero failures"** — true, and the right
  statement about the *parser*, since all 1118 really are banks;
- **"the discs hold 1118 banks"** — wrong; that is 1017.

Corrected in `README.md`, `README_de.md`, `parsers/eiii_parser.py`,
`docs/EIII_FORMAT.md` and §EIII above.

### Two traps found on the way

- **The original glob was case-sensitive** (`*.ISO` at the top level, `*.iso`
  in the subdirectory) and silently skipped five volumes. The audit only lands
  on 1118 once that is fixed; before that it saw 17 of 22 volumes and 649
  hits. A scan that quietly reads a subset of its corpus is worse than one
  that fails.
- **A coincidence not to be fooled by:** the 22 volumes hold exactly **1118
  directory entries** as well (1017 EIII banks + 76 E4B banks + 25 OS files).
  The two 1118s have nothing to do with each other, and either could be
  mistaken for confirmation of the other.

### Re-running it

`python3 tests/re_banks/emu3_os_file_audit.py [IMAGE ...]` — no arguments
audits the default 22-volume set; `VERBOSE=1` prints every hit that is not a
clean bank header, with the file (or free cluster) that owns it.

---

## §RESAMPALIAS — `resample_to_rate` aliased worse than the code it was better than (FIXED 2026-08-02)

Prompted by ConvertWithMoss `e3a9600a` (2026-08-02), which replaced its own
linear-interpolation rate conversion with a band-limited one. Checking whether
that finding applied to us showed it did — and that we were in worse shape than
the code they had just replaced.

### What was wrong

`processors/resampler.py::resample_to_rate` ran a `_twopole_lowpass` at
`0.45 × dst_rate` and then linear-interpolated. Two one-poles in cascade is
~12 dB/oct, which is nowhere near enough at a transition this tight: content
just above the destination Nyquist arrived barely attenuated and folded
straight back into the audible band.

Measured on a full-scale sweep lying **entirely** above the new Nyquist
(11.6–21 kHz, converted 44.1 → 22.05 kHz), which should come back as silence:

| implementation | aliased residual |
|---|---|
| CWM, linear (the code they replaced) | −9 dB (their figure) |
| CWM, windowed sinc (`e3a9600a`) | −101 dB (their figure) |
| **mpc2emu, 2-pole + linear** | **−5.3 dB peak / −9.6 dB RMS** |
| **mpc2emu, windowed sinc (this fix)** | **−89.4 dB peak / −115 dB RMS** |

The same softness cost the passband: −1.4 dB at 5 kHz and −3.0 dB at 8 kHz,
i.e. it dulled clearly audible content while still aliasing. The new path is
flat (< 0.05 dB) to 9.5 kHz and −0.5 dB at 10 kHz.

This was **not** an opt-in corner. The KRZ headroom-aware downsample
(`convert.py`, the `max_sr < 0` branch) is the default for KRZ output, so every
KRZ bank with wide key zones went through it. `--max-sample-rate` is the other
caller. `resample_vintage` is untouched: its aliasing is the product, not a
defect — see `_decimate`.

### The fix

Convolution with a Blackman-windowed sinc whose cutoff sits below the
destination Nyquist; the kernel is both the anti-alias filter and the
interpolator. `_sinc_bank` / `_sinc_resample`, pure stdlib — numpy is
deliberately not a pipeline dependency.

Three things worth not re-deriving:

- **A lower-sidelobe window is worse here.** Blackman-Harris (−92 dB sidelobes
  vs Blackman's −74 dB) measured **−55 dB where Blackman gave −75 dB** at equal
  kernel length. What limits this filter is the width of the transition band
  just above the new Nyquist, not the far stopband, and B-H's wider main lobe
  attenuates less exactly there. Reach for a longer kernel, not a quieter
  window.
- **`_SINC_ZEROS = 32`, `_SINC_ROLLOFF = 0.95`** from a measured sweep. Going
  to 48 zeros pushes the alias below the 16-bit floor entirely (the "−239 dB"
  reading is output quantising to exact zero, not a real number) for +37 %
  time; 32 already sits at the floor. Rolloff 0.95 costs nothing in aliasing
  over 0.92 and buys ~1 kHz of passband; 0.97 costs 6 dB for another 0.4 dB.
- **Weights are precomputed per phase.** The fractional position of an output
  sample cycles with period `dst_rate / gcd`, so an exact polyphase bank is
  built when that is ≤ `_SINC_MAX_PHASES` (2048) and phase-interpolated
  otherwise. The KRZ path picks arbitrary targets (e.g. 44100 → 42763), so the
  interpolated branch is a normal case, not a fallback. 2 s of mono audio
  converts in ~0.3 s.

### Two pre-existing bugs in the same function, also fixed

Both were latent because they need a **stereo** sample to bite, and only
reachable via `--max-sample-rate` until KRZ stereo lands:

1. **Channel bleed.** The old code interpolated over the interleaved stream,
   so each output sample mixed L and R together and the frame count was
   computed on total samples rather than frames. Now split → convert →
   re-interleave.
2. **Loop points scaled against twice the real frame count.**
   `n_frames = len(pcm_out) // 2` treats bytes-per-frame as 2 regardless of
   channel count, so a stereo sample's `loop_end` could be clamped to a value
   past the end of the sample. Now divides by `channels`.

### Verification

`tests/test_resampler.py` (10 assertions): the sweep-above-Nyquist property,
passband flatness at 1/5/8/9.5 kHz, unity DC gain, stereo non-bleed, loop-point
frame math, the never-upsample guard, and the interpolated-phase path. Plus an
end-to-end `--format krz` conversion of a 21-sample multisample: both rate
paths exercised, and every sample's dominant partial still lands on its root
pitch after conversion.

---

## §WAVFMT — `load_wav` rejected every WAV that is not format code 0x0001 (FIXED 2026-08-02)

Found while checking ConvertWithMoss `8dcb97cb` (WAV files carrying an Ogg
stream) for relevance. That specific case is niche for us, but the check
exposed a much broader one underneath it.

`parsers/xpm_parser.py::load_wav` decodes through the stdlib `wave` module,
which accepts **only** `WAVE_FORMAT_PCM` (`0x0001`) and raises
`unknown format: N` for anything else. The exception is caught and turned into

```
  [ERROR] Could not load WAV <path>: unknown format: 3
```

and the sample is dropped. The failure is at least loud and names the file —
no silent corruption — but these are not exotic files:

| code | meaning | how common |
|---|---|---|
| `0x0003` | IEEE float (32/64-bit) | **ordinary DAW export**; confirmed on a real 2ch/48 kHz/32-bit file in `~/Dokumente/New Project/Audio/` |
| `0xFFFE` | `WAVE_FORMAT_EXTENSIBLE` | the standard way to write 24-bit and >2-channel WAV; the real format code sits in the `SubFormat` GUID |
| `0x674F`–`0x6751`, `0x676F`–`0x6771` | Ogg Vorbis in WAV | niche (FL Studio DirectWave packs) — CWM's actual commit |

A local scan of 496 `.wav` files found 493 plain PCM and one real float file,
so this is not currently biting a corpus we convert often. It would bite the
moment someone builds a bank straight from DAW-exported material, which is a
normal workflow.

### Fix strategy

Do **not** reach for a dependency. `load_wav` already reads the whole file
into `raw_file` for the `smpl` chunk, so the `fmt ` chunk is right there:
parse it directly instead of delegating the container walk to `wave`.

1. Read `fmt `: `wFormatTag`, `nChannels`, `nSamplesPerSec`, `wBitsPerSample`.
2. If `wFormatTag == 0xFFFE`, the effective code is the first two bytes of the
   `SubFormat` GUID in the chunk extension — resolve it and continue as that
   code. This alone fixes most 24-bit files.
3. `0x0001` → the existing 8/16/24-bit paths, unchanged.
4. `0x0003` → float32 (or float64) to int16: scale by 32767 with a clamp,
   since float WAVs legitimately exceed ±1.0 and a bare cast would wrap.
5. Anything else, Ogg codes included → keep today's named `[ERROR]`. Failing
   clearly beats mis-reading; CWM took the same line, accepting only a data
   chunk that really begins with an `OggS` page.

Worth keeping the 16-bit-only contract at the `SampleData` boundary — the
conversion belongs in the loader, next to `_convert_24_to_16`, not in the
writers.

### What was implemented (2026-08-02)

`_parse_wav_chunks()` walks the RIFF chunks directly and `load_wav` dispatches
on the resulting code; `import wave` is gone from the parser. Float PCM is
converted by `_float_to_int16()`. Covered by `tests/test_wav_formats.py`
(15 assertions).

Three things the implementation turned up that the plan did not anticipate:

- **The stdlib module was also truncating ordinary PCM files.** `wave` clamps
  its reads to the **RIFF size field**, and real MPC exports understate it —
  in `~/temp/SamplerExports` the field is 556 bytes short of the actual file.
  Every one of those 71 samples was losing its last **186 frames** (~4 ms) and
  having `loop_end` clamped that much early. Reading the `data` chunk as
  declared recovers a length of exactly 4.000000 s, and the new output is a
  strict superset of the old: byte-identical prefix, 186 frames longer. So the
  container walk fixed a silent data-loss bug that had nothing to do with
  format codes.
- **Round, do not truncate.** `int(v * 32767.0)` biases every sample toward
  zero; measured over 500k samples of a real 32-bit float take, truncation
  gives a mean error of 0.497 LSB against rounding's 0.250. The converted
  output now matches a float64 round-half-even reference exactly.
- **Clamp before scaling.** Float WAVs legitimately exceed +/-1.0 — headroom
  is the point of the format — so an unclamped cast wraps a loud peak into the
  opposite polarity.

- **32-bit *integer* PCM was a separate gap**, found only by running the
  corpus: code `0x0001` with `wBitsPerSample == 32` is not float, and the PCM
  branch handled 8/16/24 only. 12 of a 300-file random sample failed on it
  until `_convert_32_to_16()` was added — the same strided high-two-bytes copy
  as the 24-bit path, verified against an arithmetic `>> 16` reference on a
  real 48 kHz stereo file.

Validated on ~3,700 real WAVs in `~/Mixbus` and `/mnt/music/rehearse`, of
which **3,363 are 32-bit float** — i.e. material the old code rejected
outright. A random 300-file sample now loads 300/300, where the first run of
that same sample loaded 288. A 44 MB / 3.7-minute float take converts in ~3 s;
sampler sources are far shorter, so the pure-Python conversion loop is not
worth optimising further.

### FLAC — raised and DECLINED 2026-08-02

Reading FLAC as a sample input was raised alongside this fix (the corpora at
`/mnt/music/sorted`, `/mnt/music/rehearse` and `~/Mixbus` hold a lot of it).
**Declined — do not re-raise without a new reason.**

It is not a variation of the WAV work. That needed no decoder; FLAC needs a
real one and Python ships none, so every route costs something permanent: a
third-party dependency (`soundfile`/`pyflac`, i.e. libsndfile or libFLAC),
shelling out to `flac`/`ffmpeg` and inheriting whatever is installed, or
carrying a pure-Python decoder. mpc2emu stays small and self-contained — the
same reason the resampler implements its own windowed sinc rather than
importing numpy (§RESAMPALIAS).

The two arguments that settle it:

- **Nothing we read embeds FLAC.** The sampler containers mpc2emu parses
  (E4B, EIII/ESI, KRZ, XPM/PGM, SFZ, SF2, EXS24, GIG, TAL) all carry PCM.
  Adding a decoder would buy exactly one thing: loose `.flac` files in a
  folder import. (For the record, FL Studio's DirectWave *does* store its
  samples FLAC-compressed — but mpc2emu does not read DirectWave, so it
  costs us nothing today. If that format is ever added, this decision is
  worth revisiting **for that reader only**.)
- **Folder input has a trivial user-side workaround.** Converting a folder of
  `.flac` to `.wav` beforehand is one `flac`/`ffmpeg` command, and the user
  keeps control of the decode.

---

## §KRZSTEREO — the stereo sample layout, read from the corpus (2026-08-01)

KRZ stereo samples are **planar**: the whole left channel, then the whole
right. Established from 533 real stereo samples across 233 local `.KRZ` files,
533/533 on every claim below.

A stereo sample carries **two `Soundfilehead` records** with independent
absolute offsets. The second is the first with every offset shifted by exactly
one channel length:

| claim | evidence |
|---|---|
| `block1.start = block0.end + 1` | 533/533 |
| delta start = delta end = delta loopstart = channel length | 533/533 |
| both headers share `root`, `period`, `flags` | 533/533 |
| never reversed (block 1 always follows block 0) | 730/730 objects with two real blocks |

### `numHeaders > 1` does NOT mean stereo

Real files use multi-header sample objects for groups of **mono** samples at
different rootkeys — 71 such objects locally, up to 64 headers. Only
`KSample.flags` bit 0 (`FLAG_STEREO`) means stereo. Keying on the header count
corrupts every multi-root mono sample.

### Keymap entry `SSNr`

The keymap entry's `SSNr` selects the header; for a stereo sample it must
reference the LEFT member of a pair, so the K2000 takes `SSNr` and `SSNr+1` as
the two channels (`headerIndex = (SSNr - 1) & ~1`). A two-header stereo sample
therefore has exactly one valid value, `SSNr = 1`, which mpc2emu writes.
Hardware-checked: setting it to 3 addresses a header that does not exist and
the sample goes silent.

### Implementation

`writers/krz_writer.py` writes the two planar blocks; `parsers/krz_parser.py`
reassembles them into interleaved stereo. Mono output is byte-identical to
before, and 51 real samples round-trip byte-exact.

**Writing this layout is necessary but not sufficient to get stereo
playback** — see §KRZSTEREO2 for the three additional fields the K2000
requires.

## §KRZSTEREO2 — what makes a stereo sample play as stereo (2026-08-02)

Writing the planar block layout is necessary but **not sufficient**. A file can
match real stereo samples field for field and still play as mono. Three more
things are required, all hardware-confirmed on a K2000R:

### 1. `LYR[8]` bit `0x20` — the stereo marker

Set on the layer. Confirmed by a real bank carrying stereo and mono programs
over the same material: `0x24` vs `0x04`. Clearing it removes the second
channel entirely.

### 2. `CAL[7,8]` — the second keymap slot

A stereo layer carries the keymap id in **both** `CAL[11:13]` and `CAL[7,8]`.
The K2000 uses one keymap slot per channel; with only the first set it never
reads the second `Soundfilehead` at all — a sample whose first block is silent
produces silence, even with a full-scale second block.

**This is conditional on the layer being stereo.** Setting it unconditionally
makes every layer claim two keymaps and silences programs at 4+ layers
(HW-confirmed 2026-06-23, ROM #183/#193/#194). Mono layers must keep it zero.

Corpus evidence across 201 banks: `CAL[8]` is nonzero on **97.6%** of layers
whose keymap references a stereo sample and **4.2%** of mono ones.

### 3. HOB `0x52`/`0x53` — channel routing

| byte | value | effect |
|---|---|---|
| `0x52`/`0x53` byte 2 | `0x70` | routes header 1 to the RIGHT output |
| `0x52` byte 14 | `0x90` | pulls header 0 to the LEFT |
| `0x53` byte 14 | `0x94` | " |

Byte 2 alone leaves header 0 on both outputs, so the image is still centred.
Both are needed. HOB byte 0 is *not* part of this — a variant carrying byte 2
plus byte 0 and no byte 14 does not separate.

Corpus: byte 2 = `0x70` on 72.4% of stereo layers vs 4.2% of mono; byte 14 =
`(0x90, 0x94)` on 47.7% of stereo vs **0.7%** of mono. Neither is universal
among stereo programs, which is consistent with these encoding pan **positions**
rather than a boolean — a deliberately centred or narrowed stereo program would
carry different values, while a mono program has no reason to carry them at all.
If KRZ ever gains a `--pan-law`, this is the field it writes.

### Channel order

**Header 0 is the LEFT channel**, header 1 the right. Measured directly: a
440/660 stereo sample plays 440 on the left output and 660 on the right, with
the opposite channel at true zero.

### Verification

See `docs/re_procedures/krz_stereo.md` for the measured results, including the
negative control (byte-identical channels must come back correlated) that
distinguishes working stereo from two independently mangled channels.

---

## §KRZKEYMAP — per-entry sample assignment: the entry index is off by 12 (FIXED 2026-08-02)

A keymap with distinct samples on adjacent keys played only the **first**,
key-tracked. The cause: **the K2000 sounds keymap entry `i` at key `i + 12`**,
and mpc2emu wrote each zone into `entry[key]`. The keys actually played
therefore read entries 12 below the ones we filled — whatever the surrounding
fill had put there, almost always the first sample.

### Evidence

A commercial bank whose entries 0..47 reference an absent ROM sample and whose
real samples begin at entry 48 is silent below key 60, sounds from key 60 up,
and its run boundary at entry 52 lands on key 64.

A four-tone test bank (mono, 440/550/660/880, one per key on 48..51) written
the old way measured **440/466/494/524** — indistinguishable from the
single-sample control, because that is what it was. Written as
`entry[key - 12]` the same bank measures **440/550/660/880** while the control
is unchanged.

### Consequences

- **Every multisample KRZ bank produced before this fix is wrong on hardware**
  and must be regenerated; the file looks correct and re-reads correctly,
  because the reader carried the matching offset. See the README.
- With `basePitch = 0` the 128 entries cover keys **12..139**, so keys 0..11
  cannot be addressed and a zone asked for from key 0 starts at 12.
- This settles the entry-index base question open since the ConvertWithMoss
  crosscheck: their `12 + ...` form is right. The earlier corpus-only reading
  (root-inside-zone, 39.6% vs 26.4%) picked the other one — that margin was
  never strong enough to decide it either way.

## §MPC3D3 — track and project containers, and exact sample resolution (FIXED 2026-08-03)

Two MPC 3 gaps closed from the RE checklist
(`docs/re_procedures/mpc3_xpm_params.md`, items **D3** and **E3**), both
software-only — no hardware was needed for either.

### D3 — a `.xpm` is not always a bare program

Header line 3 names the payload, and the MPC writes three of them:
`SerialisableProgramData`, `SerialisableTrackData` and
`SerialisableProjectData`. We accepted only the first and raised on the other
two, so **a keygroup program saved inside a track or a project was
unreachable** even though the program itself is identical.

`_mpc3_program_nodes()` now extracts them:

| payload | program(s) |
|---------|------------|
| `…ProgramData` | the payload root itself |
| `…TrackData` | `data.program`, if `type == 1` |
| `…ProjectData` | every `data.tracks[].program` with `type == 1` |

`type == 1` is the keygroup program; drum, plugin and MIDI tracks are filtered
out. ConvertWithMoss reads the same field the same way.

**One structural wrinkle:** in the track and project containers `samples[]`
sits on the *payload root*, not on the program node — so the per-sample
`metadata` (`rootNote`, `tune`) that §MPC3XPM depends on is one level up from
where a bare program keeps it. It is folded into each program node on
extraction, which keeps `_mpc3_to_xml()` reading one self-contained dict and
means nothing downstream had to learn about containers at all.

A payload with no keygroup program now refuses with a sentence that says so,
rather than the old "unsupported payload".

**Superseded 2026-08-03 by §MPC3BANK:** a project holding several keygroup
programs originally converted only the first. It now converts all of them into
one multi-preset bank.

### E3 — resolve the sample exactly instead of searching for it

MPC 3 writes its samples into a sibling `<stem>_[<Kind>Data]/` folder and names
the file in each layer's own `sampleFile`, so the correct WAV is known without
looking for it. We were resolving by `sampleName` through `_find_wav()`, which
walks the whole tree and takes the **first name match in traversal order**.

**That is a real bug, not a theoretical one.** Negative control: two programs,
each with its own `_[ProgramData]` folder, each holding a different
`SHARED.wav`, the decoy earlier in traversal order.

| path | resolves to | frames |
|------|-------------|--------|
| old `_find_wav` | `AAA_decoy_[ProgramData]/SHARED.wav` | 1000 |
| new `_resolve_mpc3_sample` | `ZZZ_real_[ProgramData]/SHARED.wav` | 8000 |

It stays a *preference*, not a requirement: a miss falls back to the old
search, so re-organised or hand-assembled exports keep working. CWM errors out
instead; being forgiving costs nothing here and keeps every export that works
today working.

### Verification

All three local 3.9.0.31 files convert unchanged (21 / 25 / 25 samples), the
133-test suite passes, and track/project extraction was checked on synthesized
containers covering: a track, a project with two keygroup tracks plus a drum
track, and a project with no keygroup program at all.

**What is still owed:** the synthesized containers are our own guess at the
shape. Two real exports would confirm the field names and the `type == 1`
filter on genuine MPC output — filed as checklist item **D5**.

## §CUTOFFKNOB — a candidate MPC knob → Hz curve, from ConvertWithMoss (**REFUTED 2026-08-03**, see §MPCCUTOFF)

> **Refuted the same day it was written.** Measured on an MPC One 3.9.0.31:
> at three-quarter knob this curve predicts 13 858 Hz; the hardware measures
> **2934 Hz**. It is 2–6× high across the whole usable range and the error
> grows upward. The real curve is in §MPCCUTOFF.
>
> Kept because *how* it was wrong is the useful part. The `n/127` finding
> below is what should have raised suspicion: the MPC's JSON stores a knob
> position and no frequency anywhere, so a converter quoting Hz for it is
> necessarily supplying its own interpretation. A third-party constant that
> cannot be traced to a measurement is a hypothesis, whatever its provenance —
> and this project has now seen ConvertWithMoss be right (the §KRZKEYMAP entry
> base) and wrong (this) on exactly that kind of value.



Fix material for the open TODO *"Normalised-knob sources violate the
`filter_cutoff` contract"*. That item is blocked on the **source-side**
knob → Hz curves, which have never been measured. ConvertWithMoss now carries
one for the MPC, so there is finally a concrete curve to test against — but it
is **their reading, not our measurement**, which is why this is a candidate and
not a fix.

### The curve

`ConvertWithMoss 30177c27` (2026-07-30) added
`core/algorithm/MathUtils.normalizeCutoff` / `denormalizeCutoff`:

```
n  = clamp((log2(hz / 880) * 12 + 57) / 140, 0, 1)
hz = clamp(880 * 2^((n * 140 - 57) / 12), 32.7, 106300)
```

A plain **log/semitone scale: 140 semitones wide, anchored so `n = 0` is
32.7 Hz (C1) and `n = 1` is 106.3 kHz.** The two directions round-trip exactly
(verified here to 4 decimals). Before this commit CWM used the same flat
`normalizeFrequency(cutoff, MAX_FREQUENCY)` that we still use.

The same commit also moved MPC cutoff **key-tracking** from a 1200-cent to a
**24000-cent** full-scale range, on both the read and write sides.

### What it would mean for us

`parsers/xpm_parser.py:1112` reads MPC `<Cutoff>` as a bare float and passes it
through as `filter_cutoff`, i.e. straight into a field contractually defined as
a position on the 57 Hz – 20 kHz E4XT exponential. The fix shape is the one the
TODO already states — knob → Hz → `hz_to_e4b_cutoff` — with this as the first
leg.

Applying it changes the answer a lot, and not toward the current one:

| knob | current (post-2026-07-31 writer) | this curve |
|------|----------------------------------|------------|
| 0.25 | 247 Hz | 247 Hz |
| 0.50 | 1068 Hz | 1865 Hz |
| 0.75 | 4552 Hz | **14080 Hz** |

Two consequences worth knowing before anyone implements it:

- **The top fifth of the knob is off the end of the E4XT.** `n = 0.7934` is
  already 20 kHz, so everything above that clamps to wide open — a real
  MPC preset sweeping 0.8 → 1.0 would flatten to no movement at all.
- **The bottom is below the floor too**: `n = 0` is 32.7 Hz against the
  E4XT's 57 Hz. Only the middle ~72% of the range survives the mapping.

That is not an argument against the curve — if it is what the MPC does, the
clamping is honest and the current silent mis-scaling is not. It does mean the
conversion must clamp deliberately and probably warn.

### Status

**Candidate, not adopted.** Nothing here is measured by us, and a third-party
converter's constant is exactly the kind of thing the §KRZKEYMAP episode says
can be either right (their `12 + ...` entry base was) or wrong. It stays item
**A3** on the MPC 3.x parameter checklist; the bench task is unchanged, but it
now has a specific hypothesis to confirm or refute rather than an open
question. TAL and MPC1000 (`talsmpl_parser`, `pgm_parser`) are untouched by
this — CWM offers nothing for either.

## §MPCCUTOFF — the MPC 3 cutoff knob, measured (SETTLED 2026-08-03, hardware)

`filterCutoff` is a normalised knob, not a frequency, and the JSON carries no
Hz anywhere. Measured directly on an **MPC One running 3.9.0.31**, driven over
MIDI with audio captured through the bench rig:

```
f(c) = 21.377 * 728.0^c        c = the stored 0-1 value
f(n) = 21.377 * 1.05326^n      n = the UI knob 0..127
```

**21.4 Hz .. 15.6 kHz, 9.51 octaves, 0.898 semitones per step.**

### Measurement

White noise through a single keygroup, Filter 1 set to **Low2**, resonance 0,
filter-envelope amount 0. One recording per knob position; each spectrum is
divided by a reference take at knob 127 (which cancels the noise sample's own
shape *and* the interface response), then a 2-pole response is fitted to the
result.

| knob | measured | fitted | err |
|------|----------|--------|-----|
| 32 | 112.1 Hz | 112.5 | +0.3% |
| 48 | 260.9 Hz | 258.0 | −1.1% |
| 64 | 592.5 Hz | 591.9 | −0.1% |
| 79 | 1285.8 Hz | 1289.2 | +0.3% |
| 88 | 2053.2 Hz | 2056.6 | +0.2% |
| 95 | 2933.6 Hz | 2957.4 | +0.8% |
| 111 | 6630.3 Hz | 6784.1 | +2.3% |
| 119 | 10553.9 Hz | 10275.0 | −2.6% |

Knob **88 was predicted at 2035 Hz before it was measured** and came back at
2053 (+0.9%), so the law predicts rather than merely interpolating.

Two by-products: the fitted slope came out at −11.6 / −12.5 / −11.8 dB per
octave, independently confirming **Low2 is a true 2-pole**; and `filterBlend:
0.5` was shown *not* to pass a dry path — closing the filter drops the output
21.7 dB, so the blend does not leak unfiltered signal into the measurement.

### What it replaces

`parsers/xpm_parser.py` passed the raw knob straight into `filter_cutoff`,
which is contractually a position on the E4B 57 Hz–20 kHz exponential. That
made MPC-sourced filters roughly **2× too bright**. The parser now converts
knob → Hz → `hz_to_e4b_cutoff`, the same route every Hz-aware parser uses.

Both prior candidates were wrong: ConvertWithMoss's §CUTOFFKNOB by 2–6× (worst
at the top), our own pass-through by 1.4–2.9× (worst at the bottom).

### Not settled

**Knob 127 itself.** The law extrapolates to 15.6 kHz; measuring it against a
filter-off reference gives ~23 kHz with a 20–31 kHz confidence band. The whole
measurement rests on 0.96 dB of droop, so it constrains little. Left as
extrapolated — it is above the E4XT's 20 kHz ceiling and clamps anyway.

**MPC 2.x.** This curve was measured on 3.9.0.31 only. The XML path keeps its
historical pass-through until someone measures a 2.x unit the same way.

## §MPCENV — MPC 3 envelope times, measured (SETTLED 2026-08-03, hardware)

```
t(v) = 0.001005 * e^(10.3022 v)   seconds     v = the stored 0-1 value
range: 1.00 ms .. 30.0 s
```

### Measurement

Two discoveries made this cheap. **The MPC's data dial is detented, and its
clicks are exactly the `n/127` steps** — so knob positions are addressable by
counting clicks, for any parameter. And **the firmware displays envelope times
in milliseconds**, so the mapping can largely be *read* rather than measured.

| clicks | UI | fitted | err |
|--------|----|--------|-----|
| 16 | 3.7 ms | 3.7 | −0.56% |
| 32 | 13.4 ms | 13.5 | +0.54% |
| 64 | 180.4 ms | 180.6 | +0.13% |
| 96 | 2.420 s | 2.422 | +0.08% |
| 127 | 30.0 s | 29.94 | −0.19% |

Knob 96 was predicted before measurement (+0.08%). Max residual **0.56% across
four orders of magnitude**.

**Attack, Decay and Release were each read at 32 clicks and all give 13.4 ms**,
and Decay and Release both max at 30 s — so one curve covers every segment, as
before. Hold and Delay are *assumed* to match; they were not measured.

### The displayed number is the time to SILENCE

Confirmed acoustically at both ends. At 2.42 s the output is −56 dB and in the
noise floor immediately after; −40 dB arrives at 2.362 s.

**A trap worth recording:** the same check at 13.4 ms first suggested the UI
meant the −20 dB point. That was an artefact of smoothing the analysis with a
3 ms window over a 13 ms decay — 23% of the event, which drags every crossing
later. At 2.42 s the same smoothing is 2% and the answer changes. *Match the
analysis window to the timescale, or the measurement invents a convention that
is not there.*

### The decay shape is not exponential

| t | measured | linear-amplitude model |
|---|----------|------------------------|
| 0.5 s | −2.3 dB | −2.0 dB |
| 1.0 s | −7.1 dB | −4.6 dB |
| 1.5 s | −13.0 dB | −8.4 dB |
| 2.0 s | −22.1 dB | −15.2 dB |

It falls faster than linear — roughly **amplitude ∝ (1 − t/T)^1.5**. EOS
envelopes are built from exponential segments, so matching the total time gets
the length right while the middle of the curve sits a few dB high. Not
corrected; recorded so the residual is known rather than mysterious.

### What it replaces

Ours (`0.00079·e^(9.78v)`, max 14 s) ran **0.47×** at the top; CWM's
(`0.001·e^(11.513v)`, max 100 s) ran **3.33×**. The truth sits between them:
CWM had essentially the right prefactor (0.001 vs 0.001005) with far too steep
an exponent, we had the better exponent with less than half the range. Neither
was salvageable by adjusting one constant.

`_xpm_env_to_seconds()` now takes an `mpc3=` flag and keeps both sets of
constants — the 2.x curve was itself hardware-measured (on an MPC One running
2.x) and there is no evidence it is wrong for 2.x programs, only that 3.x
differs.

## §MPC3BANK — an MPC 3 project is a bank; every keygroup track is a preset (2026-08-03)

An MPC 3 **project** (`.xpj`) carries one program per track, so a project with
several keygroup tracks is the MPC's equivalent of an E4B bank. `parse_xpm`
built exactly one `Preset` per file, so everything past the first keygroup
program was dropped with a warning.

That mattered more than it first looked. The natural MPC workflow — run the
Auto Sampler several times, each onto its own track, then save the project —
produces exactly the file this could not convert.

### What changed

The preset-building body of `parse_xpm` is now an inner `_build_preset(root,
preset_name)`, and the function drives it once per program:

| container | presets |
|-----------|---------|
| `.xpm` (program) | 1 |
| `.xty` (track) | 1 |
| `.xpj` (project) | one per `type == 1` track |

The MPC 2.x XML path is unchanged — it feeds a one-element list, so it takes
the identical route and cannot behave differently.

**The sample caches are shared across presets on purpose.** Two programs in one
project routinely reference the same WAV, and it must be loaded and stored
once. Verified on a synthetic three-track project where two keygroup programs
share a sample and a drum track is filtered out: 2 presets, 2 samples, the
shared one loaded once.

Preset names come from the **program**, not the filename, so a converted
project reads `Keygroup 001` / `Keygroup 002` rather than two copies of the
project name. `program_number` is assigned in order and reaches the E4B TOC as
the per-preset MIDI program (byte 31 — verified in a written file: 0 and 1).

### MPC 2.x projects are the same case, and were silently broken

A 2.x `.xpj` is **XML**, and it is a `<Project>` — settings and a file list, not
a program. Registering `.xpj` therefore fed it to the program parser, which
found no `<Instrument>` elements and returned a **preset with zero voices and
zero samples**: a "successful" parse of nothing, which is worse than an error.

A 2.x project keeps its programs as separate files in its data folder, named
`<name>.<Kind>.xpm` — the kind is in the filename (`Keygroup`, `Drum`, `MIDI`,
`Plugin`, `Audio`, `CV`, `Clip`). So the 2.x equivalent of "project = bank" is
to gather the `*.Keygroup.xpm` files, which is now what happens; samples are
searched in that folder rather than the whole Projects tree. A project with no
keygroup program refuses with a sentence saying so.

### `_find_wav` missed every sample whose name ends in `.wav`

Found by the corpus, not by reasoning. A sample imported from `Foo.wav` is
named **"Foo.wav"** in the program and stored as **`Foo.wav.WAV`** on disk.
`_find_wav` only appended `.wav`/`.WAV` when the name had *no* suffix, so it
looked for `Foo.wav`, missed `Foo.wav.WAV`, and dropped the zone. One 2.x
project alone has 393 such files. The extension is now appended regardless,
with the exact name still tried first.

### Verified against the MPC One backup corpus

`/mnt/music_production/mpc_one_backup/.../Projects` — 22 JSON projects spanning
firmware **3.4.1 → 3.9.0**, 36 XML 2.x projects, 571 standalone 2.x programs.

| | converted | refused | presets | samples |
|---|---|---|---|---|
| `.xpj` JSON (3.x) | 7 | 10 | — | — |
| `.xpj` XML (2.x) | 22 | 8 | — | — |
| both | 29 | 18 | **93** | **1271** |
| standalone `.xpm` | 571 / 571 | 0 | 571 | 970 zones |

**Zero crashes and zero missing-sample warnings** across the projects. The 18
refusals are projects containing no keygroup program at all. Five missing-sample
warnings remain among the standalone programs, all in one `_[AutoSave]` folder
that carries 5 programs and 0 WAVs — genuinely absent, not a lookup failure.

Also confirmed end to end: `Project-three.xpj` → one E4B bank, 2 presets,
2 samples, which re-parses correctly and carries distinct MIDI program numbers
in the TOC (byte 31: 0 and 1).

### Not addressed

Reading a preset's MIDI program number back out of an E4B is still missing —
`parse_e4b` constructs `Preset(...)` without `program_number`, so an E4B→E4B
round trip loses the assignment. Logged in TODO.md; it is a parser gap that
predates this work.

## §XPMGAPS — three MPC layer fields we drop and ConvertWithMoss reads (**1 and 2 IMPLEMENTED 2026-08-03**, branch `cwm_ketchup`)

Found by comparing our MPC support against `MPCModernDetector` after the
project-as-bank work (§MPC3BANK). None of the three blocks a conversion; each
silently loses fidelity. Listed most audible first.

> **Status after implementation:**
> 1. **`direction` — DONE.** Baked into the PCM, byte-exact against a reversed
>    real 330 612-frame sample and mirror-exact in the audio domain.
> 2. **Loop crossfade — DONE**, with the caveat below that the MPC's own frame
>    alignment is unverified. `loopFineTune` is *not* implemented: it warns.
> 3. **`ZonePlay` — warns, deliberately not reproduced.** But the claim below
>    that "EOS has no round-robin" was **half wrong** — see the correction in
>    section 3.
>
> **What is still assumption rather than measurement**, and the plan to settle
> it, is written up as **HW-1 … HW-5** in
> `docs/re_procedures/mpc3_xpm_params.md` ("Hardware confirmation plan").
> Byte-exactness proves we do what we *intended*; it does not prove the
> intention matches the MPC. HW-1 (is `direction` whole-region reversal, and
> does the amp envelope stay on the forward time axis?) is the one that
> actually matters — the other four are cheap or dormant.

### 1. `direction` — reverse playback (checklist C7)

**What:** the layer field `direction` (`0` = forward). §MPC3XPM already records
it in the slice-field table; nothing reads it. A reversed layer converts as
forward, which is not a subtle loss.

**Fix:** neither E4B nor KRZ has a per-zone reverse-playback flag, so the
conversion has to **reverse the PCM itself** at load time — the same shape as
the existing ping-pong handling, which bakes the reversed interior into the
sample rather than relying on a target-format flag (see the ping-pong note
earlier in this file). Reverse the frames after slicing and before looping, and
mirror the loop points about the new length: a loop `[a, b]` in a sample of
`n` frames becomes `[n-1-b, n-1-a]`.

**Watch for:** `SliceLoop = 2` (Reverse) and `3` (Alternating) are a *separate*
mechanism from `direction` and are still only inferred from the manual, never
seen in data (§MPC3XPM). Do not conflate them — a reversed *sample* and a
reverse *loop mode* are different things, and implementing one as the other
would be worse than dropping both.

**Implemented 2026-08-03** as `_apply_reverse()`, applied after slicing so the
reversal covers exactly the region the MPC would have played, with loop points
mirrored about the new length. Frames are reversed, not bytes — reversing bytes
would swap a stereo sample's channels and flip each sample's bytes into noise.

**Verified eight ways:**

1. Byte-exact unit tests: mono order, stereo channel pairing, loop mirroring
   `(2,5) → (4,7)`, and double-reverse identity on random stereo PCM.
2. **Byte-exact end to end on a real file** — a real 2.x keygroup program with
   `Direction` flipped on, giving a 330 612-frame stereo sample identical to
   its source read backwards.
3. **Byte-exact through the full `convert.py` → E4B → re-parse round trip**, so
   the writer preserves it too.
4. **Audio domain:** the RMS envelope mirrors to within 0.0000% of peak.
5. **Negative control:** the same sample's forward and reversed envelopes
   differ by 77% of peak, so the mirror test is meaningful rather than a
   symmetric-sample artefact.
6. **MPC 3 JSON path** separately: byte-exact reversal and correct loop
   mirroring from a synthesized `.xpm` (the real-file test above is the 2.x XML
   path, and the two reach `_apply_reverse` by different routes).
7. **Cache separation:** one program using the same WAV forward on one key and
   reversed on another yields two distinct samples, the second the reverse of
   the first — reverse and crossfade both bake into the PCM, so the cache key
   had to include them or the two would collide. Also confirmed deterministic
   across runs.
8. **KRZ path:** byte-exactness is impossible there because that path resamples
   (44.1 kHz → 24 kHz), so it was checked in the audio domain instead — the
   envelope mirrors to 0.008% of peak with 78% asymmetry.

**Composition with the crossfade** is also checked: crossfade-then-reverse
equals reverse-of-crossfaded, the loop mirrors, and the blended frames land at
the mirrored boundary (frames 31–35 become 4–8), i.e. still at the loop seam.

**Performance:** the obvious implementation — joining frames one at a time —
costs ~750 ms on a 5 MB stereo sample, long enough to notice on a bank full of
reversed layers. Reversing per channel with strided `array` slices instead
brings that to ~57 ms (13×; 52× for mono), with byte-exactness re-verified on
the real file afterwards.

**Corpus note:** `Direction = 1` occurs in 32 files, but *only in Drum and Clip
programs* — which are skipped by design. No keygroup program in the corpus uses
it, which is why test 2 above had to flip the flag on a real file rather than
find one.

### 2. Loop crossfade and `loopFineTune` (checklist B5)

**What:** `loopCrossfadeLength` (layer) and `SliceLoopCrossFadeLength`
(`sliceInfo`, `-1` = none), plus `loopFineTune`. All unread. A crossfaded MPC
loop converts as a hard splice and can click at the seam.

**Fix:** we already own a crossfade implementation — `--auto-loop` renders
seamless loops with a crossfade — so this is wiring an incoming length into
that machinery rather than writing new DSP. The MPC value is in **frames**;
CWM instead stores a *fraction of the loop length*, so do not copy their
number without converting.

**Open question:** whether the MPC crossfades symmetrically about the loop
point or backwards from it. That changes which frames get mixed, and it is
measurable on the bench rig now — a loop with a long crossfade, recorded and
compared against both renderings.

**Implemented 2026-08-03**, using the equal-power blend `processors/auto_loop.py`
already uses: the `xf` frames ending at `loop_end` are morphed into the `xf`
frames ending just before `loop_start`, so the wrap is continuous. Length is
clamped to the pre-roll and to a third of the loop. Verified byte-exact against
a hand-computed blend, with the region outside the blend proven untouched.

**CORRECTION 2026-08-04: it does run on real data.** This paragraph used to say
the opposite — that all 69 808 corpus layers carry `0` or `-1`, so the code
could never fire. That count was **MPC 3 JSON only**. MPC 2.x XML carries
`SliceLoopCrossFadeLength` as well, and across the MPC One backup **1 375
layers hold a positive value** (4, 7, 8, 9, 14, 65, 69, 70, 74, 77, 128 …); two
files in `Projects` bake a crossfade into 14 samples today.

So the frame alignment is not a dormant guess — it alters real conversions.
That promotes **HW-2** from "low priority, nothing affected either way" to the
live question on this branch, and real test material already exists rather than
needing to be built (`CAT10-Auto sampled.Keygroup.xpm`, crossfade 128).

`loopFineTune` is a separate matter and the `0`-everywhere claim still holds for
it: it is **not** implemented, it warns, because there is nothing to calibrate a
guess against.

### 3. `ZonePlay` / play logic

**What:** the per-instrument zone-selection mode — round-robin, random,
velocity-based. CWM maps it onto its `PlayLogic`. We ignore it, so a
round-robin keygroup collapses to one fixed choice and loses its variation.

**Values:** `0` = cycle (round-robin), `1` = velocity (the normal case),
`2` = random. Corpus distribution across MPC 2.x XML: 61 823 × `1`, 271 × `2`,
145 × `0` — so non-default zone play is rare but real, and it does occur in
keygroup programs (`Inst-Bass-F9 *.xpm` among others).

**CORRECTION (2026-08-03): "EOS has no round-robin" was half wrong.** The EOS
4.0 manual, *Realtime Window Controls* p. 320, documents **Crossfade Random**
as a modulation source *"specifically designed"* for when *"you may want to
randomly switch between several voices"*, and — unlike the other random sources
— it *"generates one random number for all voices that are assigned to the same
key"*. That is exactly `ZonePlay = 2`.

So the two modes are not alike:

| mode | EOS equivalent |
|------|----------------|
| `2` random | **yes** — Crossfade Random + realtime crossfade windows |
| `0` cycle | **no** — Crossfade Random is random, not sequential, and nothing in EOS advances through zones in order |

**Implemented:** a warning per mode per bank, naming which of the two it is and
whether EOS could express it. Nothing is silently lost, and the message points
at the right next step instead of implying the feature is impossible.

**Still to do (TODO.md):** mapping `ZonePlay = 2` onto Crossfade Random. That
is writer-side work — realtime crossfade windows plus a cord per voice — and
doing it unverified would risk changing what a preset does, so it wants a
hardware audition rather than a guess.

### Where we are ahead, for balance

Not everything went their way in that comparison: CWM cannot convert MPC **2.x
XML projects** at all (their `getProgramElement()` rejects any root that is not
`MPCVObject`, and a 2.x `.xpj` is a `<Project>`), their XML sample lookup is a
single `sampleName + ".WAV"` candidate with no subdirectory search or
case-insensitive fallback, they drop filter types 19–28 which we map, and their
cutoff and envelope curves are unmeasured — §MPCCUTOFF refuted theirs by 2–6×.

## §XPMDRUM — MPC drum programs convert; sample-free program types now refuse (2026-08-03)

`parse_xpm` skipped `type="Drum"` and returned a preset with no voices and no
samples, without raising — so a caller could not tell "nothing to convert" from
"converted". Raised from VinSamLib, which greys such rows out rather than
offering an import that silently yields nothing.

**It was not a marginal file type.** In the MPC One backup's `Projects` tree,
drum programs are **90 files carrying 956 zones and 907 samples** — comparable
to the 82 keygroup programs (970 zones, 957 samples), with a much higher median
per file (12 samples vs 5). All of it converted to nothing.

*(One correction to the original TODO text: it said drum programs hold "more
sampled material than the keygroup programs". Counting distinct sample names,
it is 940 vs 964 — slightly fewer, ~98%. The density-per-file point stands.)*

### A drum kit is one-key zones whose root equals their key

That single idea is the whole conversion, and **neither writer needed a new
feature**:

- **EOS** transposes by `key - root`, which is 0 when they are equal.
- **The K2000** computes `tuning = 100*(r_sample - r_zone) + fine_tune`
  (`krz_writer.py:405`), which cancels its auto-transpose exactly when `r_zone`
  is the key. `krz_writer` already documents meeting this idiom in real
  third-party soundsets, and its up-pitch ceiling is measured from `r_zone`
  precisely so deliberately-retuned drum zones are not dropped.

`TuneCoarse` is deliberately **not** folded into the root for a pad: on a drum
hit it is an intentional pitch offset and must survive as a real transpose,
unlike the keygroup path where it is cancelled to match key-tracking.

### The pad → note map is DATA, not a formula

Across 56 MPC 3 drum programs: **24** use `(36 + pad) mod 128`, **1** is the
identity, and **31 carry a custom map** — General-MIDI layouts and hand-built
kits, e.g. `37, 36, 42, 82, 40, 38, 46, 44, …`. Computing the note instead of
reading `padNoteMap.noteForPad` would put more than half the corpus's kits on
the wrong keys.

**MPC 2.x XML does not store it.** All **11 520** `<PadNote>` elements across
the 90 corpus drum programs carry a `number` attribute and an empty body, and
the neighbouring `ProgramPads-v2.10` blob holds pad *colours*
(`0,127,0` green, `0,127,127` teal), not notes. So the 2.x path lays pads out
from MIDI 36 and **warns** that a custom/GM kit will land elsewhere. There is
nothing better to read in a 2.x file; consecutive keys still give a playable
kit.

### Consequence on the K2000 worth knowing

`krz_writer` fills keymap holes by extending the nearest assigned entry, because
a keymap with `sampleId=0` holes **locks up the K2000 on Master→Delete** and
needs multiple factory resets. The fill copies the neighbour's entry verbatim,
including its constant tuning — so on a drum kit the keys *between* pads sound
the neighbouring hit **transposed**, rather than silent. That is the documented
lesser evil, not a new fault: the alternative is the lockup.

### Sample-free program types now refuse

MIDI, Plugin, Audio, CV and Clip programs reference no sample data at all —
**399 such files in the corpus, every one with zero sample references**. They
now raise with a sentence saying so, instead of returning an empty preset.

### Verified

| type | files | converted | zones | samples |
|------|-------|-----------|-------|---------|
| Keygroup | 82 | 82 | **970** | 957 |
| Drum | 90 | **90** | **956** | **907** |
| MIDI / Audio / Plugin / CV / Clip | 399 | 0 (refused) | — | — |

Keygroup zone count is **identical to the pre-change baseline**, so the keygroup
path is untouched. 629-file sweep: 0 unexpected errors. A project that
previously refused for holding no keygroup program (`Complex.xpj`) now yields
three drum presets, and both writers round-trip them with every zone one-key
and `root == key`. The custom pad map is honoured end to end — keys land on
`36,37,38,40,42,43,44,45,46,47,48,82`, including the outlier.

### Not done

Velocity layers within a pad, pad mute groups, and the MPC's one-shot/note-off
pad modes are not mapped. Nor is the 2.x pad layout recoverable — if a real
`<PadNote>` body ever turns up in the wild, `_pad_note_map` already reads it.

## §XPMDRUM2X — an MPC 2.x project gathered only its keygroup programs (FIXED 2026-08-04)

§XPMDRUM (`27ff6a4`) taught the MPC **3** project path to take drum programs —
`_mpc3_program_nodes` accepts `type` 0 and 1 — but left the **2.x** branch
beside it globbing `*.Keygroup.xpm` alone. The two container generations were
left disagreeing about what a project contains, and the same commit's drum
support was unreachable through a 2.x project.

Found from VinSamLib 2026-08-04, where a project row listed 5 programs while
its own data folder held 7.

### Measured on the MPC One backup

| | |
|---|---|
| 2.x projects with a data folder | **94** |
| converted incompletely (keygroups only) | 62 |
| refused outright, holding *only* drum kits | **32** |
| keygroup-only projects (i.e. unaffected) | **0** |
| drum programs inside 2.x project folders | 219 |
| …of those with sampled pads | 166 |
| sampled pads the `.xpj` route could not reach | **2 197** |

Because no keygroup-only project exists in that backup, **every** 2.x project
that converted at all converted partially.

*(The originating note said 178 projects and 63 incomplete. 178 is both
firmware generations combined — 94 are 2.x XML, 84 are MPC 3 JSON — and the
2.x-specific figures are the ones above. Every actionable number in it was
correct.)*

### Fix

Gather `*.Keygroup.xpm` **and** `*.Drum.xpm`, and reword the refusal, which
must now mean "no keygroup *or drum* program".

**Order: keygroups first, then drums, each sorted.** Not cosmetic — preset
order is what an E4B bank exposes, so appending drums after the existing
keygroup order leaves the preset *numbering* of an already-converting project
untouched. Re-converting a project therefore does not renumber the presets of a
bank someone has already loaded.

### A second empty-preset case, found while testing

**55 of the 224 drum programs in the backup have zero sampled pads** — kits
created but never filled. Those produced an empty preset, which is the very
complaint §XPMDRUM was raised to fix, just one level further in: a slot in the
bank claiming a program converted when it did not.

`_build_preset` now skips a preset with no voices and says so. Gathering a
project drops those and keeps the rest; a single such file yields a bank with
no presets, which `convert.py` already reports as nothing to do.

### Verified

97 MPC 2.x projects across the whole backup: **94 convert, 3 refuse, 0
unexpected errors**, giving 286 presets / 3 302 zones / 2 752 samples. Before
the fix, 62 converted and 35 refused. A mixed project now reports
`2 keygroup + 2 drum program(s)` and skips the unfilled kit by name.

## §XPMNAMES — truncated-name dedup silently dropped every second sample (FIXED 2026-08-04)

A zone's only handle on its audio is the sample **name**. The dedup that kept
names inside 16 characters counted per base and then trusted its own rewrite:

```python
n = _name_count.get(base, 0)
if n > 0:
    sd.name = base[:16 - len(n_str)] + n_str    # never checked this was free
```

**Two ways the result was not new**, both live in real data:

1. **The base already ends in the digit being appended**, so the rewrite is a
   no-op: `'…_2600_C-1'` + `'1'` → `'…_2600_C-1'`. Names ending `-1`, `A1`,
   `C1` are ordinary in auto-sampled sets, so this is the common case.
2. **The rewrite lands on a different real sample**:
   `'MarioPCP2600__C0'` + `'1'` → `'MarioPCP2600__C1'`, which is another
   note's name.

Either way the loser was loaded, appended to `bank.samples`, printed as
`Loaded sample:` — and never referenced again. Its zones addressed the winner.
**Nothing warned; the log looked clean.**

### Measured

One auto-sampled keygroup program, one WAV per semitone:

| | before | after |
|---|--------|-------|
| WAVs loaded | 97 | 97 |
| distinct sample names | **57** | **97** |
| zones | 97 | 97 |
| zones sounding a namesake | **40** | **0** |

So every second semitone played its neighbour, at the wrong pitch. Across the
`Projects` tree the fix leaves **0 programs with duplicate names and 0 orphaned
samples**, from 140 programs / 5 766 samples affected before.

### Fix

`_unique_sample_name()` advances the counter against the names **actually
taken**, not a per-base tally, because shortening can map two different bases
onto one string. Names stay within 16 characters.

### The guard, and why not the one that was proposed

The report suggested writers refuse a bank whose *zone count exceeds its
distinct sample names*. That would fire constantly on healthy banks — many
zones legitimately share one sample (velocity layers, split key ranges). The
real invariants are that sample names are **unique** and that every zone name
**resolves**, and `parse_xpm` now checks both after building, reporting
`[ERROR]` with the offending names rather than failing silently.

Found from VinSamLib 2026-08-04.

## §XPMTRUNC — head-vs-tail sample-name truncation, decided per program (2026-08-04)

`_safe_name(..., tail=True)` was fixed at every sample call site. The reasoning
holds for a **multisample** — those share a long prefix and differ at the end
(`…UniPanBass_C1_A` vs `…_C2_B`), so the tail is where identity lives.

**A drum kit is the mirror image.** `BD Drumulator Clean`, `Clap Drumulator
Clean`, `Cymbal Drumulator Clean` all *end* alike and differ at the front, so
the tail keeps the one part that identifies nothing. A real 14-sample kit:

| | distinct names |
|---|---|
| tail | **4** |
| head | **13** |

`_unique_sample_name` then numbers the collisions, and the kit reads
`Drumulator Clean`, `Drumulator Clea1`, … `Drumulator Cle10` on a
16-character display. No audio is lost — that was §XPMNAMES — but a user
cannot tell which pad is which.

### Why not simply flip the flag

Measured over **5 311** corpus programs holding 2+ distinct sample names:

| | programs |
|---|---|
| only the tail works | 4 264 |
| only the head works | 79 |
| both | 820 |
| neither | 148 |

| rule | renames forced |
|------|----------------|
| all tail (today) | 8 694 |
| **all head** | **71 030** |
| per program, best of the two | **5 665** |

A global switch is **8× worse**. Both rules are pure functions of one program's
own name set, so `_prefers_tail()` picks per program — whichever yields more
distinct names, **ties to the tail**, so behaviour is preserved everywhere it
already worked. **101 programs improve**, and the best cases go from dozens of
renames to none.

### It composes with §XPMNAMES

The auto-sampled program from that entry collapses 97 → 57 under the tail;
under the head all 97 survive. §XPMNAMES stopped that collapse from *losing
audio*; this removes the collapse itself, so the same bank now converts with
**zero renames instead of 40**.

### A false positive fixed in the same pass

The invariant added with §XPMNAMES — "every zone name resolves" — was firing on
**11 corpus files** whose zones name a WAV that is simply absent from disk.
That is a missing *file*, already reported as `[WARN] Sample not found`, not a
name-resolution fault. Those names are now excluded: a check that cries wolf
gets ignored when it matters.

### Verified

629-file sweep: **0 duplicate names, 0 `[ERROR]` lines, 0 unexpected errors.**
The Drumulator kit now reads `BD`, `SD`, `Clap`, `Cymbal`, `CH`, `OH`,
`Cowbell`, `Clave`, `Rim`, `Tom Lo/Mid/Hi` with one rename instead of ten.

**Note:** this changes sample names in *newly* converted banks for those 101
programs, so any byte-identical baseline covering them needs re-taking. Banks
already built are not wrong — just named less helpfully.

Found via VinSamLib 2026-08-04.

## §XPMXFADE — HW-2 answered: the MPC does not apply the loop crossfade (2026-08-04, measured)

**Result: our implementation was falsified, and the crossfade is no longer
baked in.** This is the negative result HW-2 existed to get, and it arrived
before the branch was merged.

### What was measured

`CAT10-Auto sampled.Keygroup.xpm` carries `SliceLoopCrossFadeLength = 128` on
seven samples. Its `-060 C1` sample was played on the MPC at **key 60, root
60** — native rate, no transposition, so a sample-accurate comparison is
possible — held for 12 s across several loop cycles and recorded through the
bench rig.

Three candidate renderings of the loop were built from the source WAV,
resampled to the 48 kHz capture rate and aligned by cross-correlation:

| candidate | residual RMS in the seam window |
|-----------|--------------------------------|
| **raw — no crossfade at all** | **0.02421** |
| symmetric about the loop point | 0.02812 |
| ours (blend ending at `loop_end`) | 0.03052 |

The two blended candidates differ from raw by RMS **0.269** in that window and
the measurement residual is **0.1×** that, so the test resolves the question
with an order of magnitude to spare. Decisively, the residual against raw
*inside* the seam (0.02421) equals the residual everywhere else (0.02394) —
the seam is not special. **The MPC produces no blend there.**

### Why: the crossfade was applied ONCE ALREADY, when the sample was made

*Revised 2026-08-04 after Jan found the control.* The **Auto Sampler** has its
own looping settings: `Loop Start (ms)`, `Loop End (ms)`, **`X-Fade (# of
samples)`** and **`X-Fade-Type (EqPower / Linear)`**.

That matches `SliceLoopCrossFadeLength` exactly — same units (*samples*, not
ms), and `EqPower` is the same blend shape this project implemented. So the
field is a **record of what the Auto Sampler already did to the WAV when it
created it**, not an instruction to do it at load time. The audio on disk is
*already* crossfaded; applying it again double-crossfades, which is precisely
what the measurement caught.

Supporting evidence: the loop wrap in that WAV is continuous — the step from
`loop_end` back to `loop_start` is only **1.63×** a normal sample-to-sample
step — i.e. a seam that has already been dealt with.

*(An earlier revision of this section blamed the `Tail Length` control below
for gating the crossfade. That was a guess made before the Auto Sampler
setting was known. Tail Length is a real and separate feature; it is not what
`SliceLoopCrossFadeLength` records. A correlation probe looking for a blend
signature in the WAV was inconclusive and is not counted as evidence — the
conclusion rests on the playback measurement and the Auto Sampler control.)*

### The four related fields

The layer carries four, and the UI explains them:

| field | value here | UI |
|-------|-----------|-----|
| `SliceTailLength` | `0.0` | **"Tail Length: Off"** |
| `SliceTailPosition` | `0.5` | "tail start 253 ms" |
| `SliceLoopCrossFadeLength` | `128` | *(what we read)* |
| `LoopCrossfadeLength` | `0` | layer-level twin |

**Tail Length** is a separate playback feature offering `Off, 100, 200, …
5000 ms`, and it is Off here. `SliceLoopCrossFadeLength` is in *samples*
(128 = 2.9 ms) and cannot be that control — the corpus values (4, 7, 8, 9, 14,
65, 69, 70, 74, 77, 128) do not sit on a 100 ms grid, but they do look exactly
like Auto Sampler X-Fade lengths.

### What changed

`_apply_loop_crossfade` is **no longer called**. A layer with a non-zero length
logs an `[INFO]` saying it was not applied and why. The renderer and its tests
are kept: the DSP is correct, and it is what will be needed once a
tail-enabled measurement says how the feature should actually sound.

### Two side results from the same take

- **The MPC plays at correct pitch.** The loop period measured 2.000 s against
  a metadata period of 1.9996 s — within ~7 cents. An earlier reading of
  "47930 Hz, 8.8% sharp" was an artefact of an autocorrelation window centred
  on the wrong expected value, which could not have found the right answer.
  Search wide before believing a period.
- **The audible loop seam in that program is the source material, not us.** It
  is an auto-sampled note looping from ~2.0 s back to ~0.5 s while still
  decaying, so there is a level step at every wrap. A 2.9 ms crossfade could
  not hide it even switched on.

### Still open

**Tail Length**, which is a genuinely separate feature and still unmapped. One
export with it set non-zero identifies the field that carries it, and a
recording says how to render it.

**`128` looks like the Auto Sampler's default.** Of the positive values in the
`Projects` subtree, **7 of 9 are 128** (78%), with a single `100` and a single
`123` beside them — a power of two that dominates, with occasional
user-dialled values. That is what a default looks like, and it further
supports the field being a record of what the sampler did rather than an
instruction to the loader.

## §XPMREV — HW-1 answered: the MPC does reverse on `Direction` (2026-08-04, measured)

**Result: confirmed.** Unlike the crossfade (§XPMXFADE), `Direction` is a live
parameter that MPC 3.9 honours, and our implementation matches what it does.

### What was measured

A drum kit on the MPC, 16 keys scanned (36–51, 11 sounding), recorded through
the rig; then `Direction → Reverse` applied and the identical scan repeated.
The setting was applied to **all pads**, which made every sounding key a test
case rather than one.

The robust measure is **where the peak falls within each hit**:

| | forward | reversed |
|---|---------|----------|
| peak position (0 = start, 1 = end) | 0.01 – 0.20 | 0.16 – 0.62 |

**All 10 comparable hits move their peak later**, and the energy centroid moves
later in 8 of 10. A forward drum hit peaks immediately; these build toward the
end. That is reversal.

### The amp envelope stays on the forward time axis

The second question in the same take. Had the envelope been mirrored with the
audio, the reversed peak would sit at ≈1.0 — an abrupt onset with everything
at the very end. It does not; it lands mid-to-late, which is what reversed
audio shaped by a **still-forward** envelope looks like. That is what
`_apply_reverse` assumes, so the assumption holds.

Stated honestly: this half is *consistent with* the measurement rather than
proven by it. A mirrored envelope is excluded; the exact envelope contribution
is not separately fitted.

### Where `Direction` lives, and what it is not

- It is exposed in **Program Edit**, not Sample Edit — which is why it first
  looked absent. It is not a legacy field.
- It is **not a loop setting**. Across the files that use it, `Direction = 1`
  appears on **non-looped** layers 6 times against looped 3, and the
  `Fake Scratches` tutorial kit pairs the same sample forward and reversed on
  adjacent pads with no loop at all. `SliceLoop` (0=Off, 1=Forward, 2=Reverse,
  3=Alternating) is the loop-direction field; `Direction` is whole-slice
  playback direction.
- The MPC also offers a destructive **"Process slice → Reverse"** DSP, which
  rewrites the sample data and leaves `Direction = 0`. That is a different
  operation and must not be confused with the flag.

### Method note — two metrics that were wrong before one that was right

Worth recording, because both failures looked like results:

1. **A single global time offset** across two separate recordings reported that
   *all eleven* keys had changed. With short drum hits, run-to-run timing
   jitter destroys per-note alignment. (That one turned out to be accidentally
   right — all pads *had* been reversed — which is exactly how a broken metric
   escapes notice.)
2. **Envelope correlation over a fixed window** scored the mirrored hypothesis
   at 0.04–0.39 and concluded "same orientation" for every hit, while the raw
   envelopes plainly showed a swell-then-cut. The window was 0.45 s but the
   slices occupy ~0.2 s, so it was correlating the forward decay tail against
   silence.

Peak position within the sounding span needs no alignment, no window choice and
no normalisation, and it separated the two cases immediately. **Prefer a
measure with nothing to tune.**

---

## §AKAIIMG — AKAI disk images: written, read, and byte-identical to an independent implementation (2026-08-05)

**Status:** implemented on branch `akai-s3000xl`, cross-verified, **not
hardware-verified**. Nothing on that branch is to be pushed until the S3000XL
confirms it.

`writers/akai_s3000_image.py` builds AKAI media; `parsers/akai_image_parser.py`
reads it. `convert.py --format akai` gains `--hda` (partitioned SCSI /
ZuluSCSI disk), `--iso` (CD3000 CD-ROM) and `--floppy` (800 KB / 1.6 MB AKAI
floppy); without any of them it writes the volumes as directories of `.S3` /
`.P3` files. `.img`, `.hda` and `.iso` are claimed by more than one format, so
all three dispatch on content — an AKAI medium is identified by its
partition-header magic, or by the `0xFF` marker in a floppy header. A
*directory* scan skips shared-extension files that are not AKAI, so an output
folder full of E4B/K2000 images does not produce a parse error per file;
naming one explicitly still gives a real message.

The layout itself is in `docs/AKAI_S3000_FORMAT.md`. What is worth recording
here is **how far the verification actually got, and what it still does not
cover.**

### The verification that was available

No S3000 hardware, so the strongest available check was to build the same
content two ways and compare every byte:

| built by us | built by `akaiutil` | result |
|---|---|---|
| 16 MB hard disk, 1 volume, 3 files | `formatharddisk3 16M 16M` + `mkvol3` + `put` ×3 | **identical, all 16 777 216 bytes** |
| 16 MB CD3000 CD-ROM, same content | `formatharddisk3cd` + `mkvol3cd` + `put` ×3 + `setcdinfo MYCD` | **identical, all 16 777 216 bytes** |
| 1.6 MB floppy, 3 files | `formatfloppyh3` + `put` ×3 | **identical, all 1 638 400 bytes** |

Both hashes are pinned in `tests/test_akai_image.py`. `akaiutil` is an
independent implementation of the same undocumented format, so this is not a
self-check — but see the limits below.

Structures `akaiutil` was never asked to produce were verified the other way
round, by having *it* read what *we* built: a 3-volume, 2-partition disk lists
with the right partitions, volume start blocks and file sizes, and its WAV
exporter returns PCM from inside our image byte-identical to the source.

### What byte-identity caught that a header check would not

Both of these produced a structurally plausible image that differed from the
real thing:

1. **The floppy header initialises all 64 file-entry slots**, not just the
   first. Only slot 0 carries the `0xFF` S3000 marker, but every slot gets 12
   raw `0x20` filler bytes and the OS version. Writing only slot 0 left 63
   slots zeroed — which decode as the *valid-looking* name `"000000000000"`,
   the same trap as the unused-velocity-zone question.
2. **A floppy's volume directory must leave its volume-parameter area zero.**
   The parameters live in the header label instead. Writing them in both
   places (as the hard disk does) was a 6-byte difference that no structural
   assertion would have flagged.

### Design decisions worth not re-deriving

- **A CD3000 disc is not ISO 9660.** It is the same partition format written
  raw, so `--iso` for AKAI shares the hard-disk writer rather than going
  anywhere near `iso_builder`. The only deltas are the volume type (`0x07`)
  and three reserved blocks holding a flat index of every file in the
  partition. That index is a cache — `akaiutil` leaves it stale until you run
  `setcdinfo`, which is a foot-gun, so **our append path rebuilds it
  automatically**; a stale index shows the sampler the disc's old contents.
- **A volume is never split across a partition.** A volume's blocks are
  numbered relative to its own partition, so a split volume is not
  describable. `_plan_partitions` fills a partition and then opens the next;
  a single volume larger than a partition is an error with an explicit
  "split it into several volumes".
- **Auto-sizing stays close to the content** (+25%, 8 MB floor) rather than
  rounding up generously. These images are copied to a ZuluSCSI SD card over
  USB, where spare megabytes are copy time — the same reasoning as the E4B
  `.hda` sizing.
- **The extension is load-bearing.** The directory entry stores only a type
  byte and it is derived from the extension, so the writer emits `.S3` / `.P3`
  (changed from `.a3s` / `.a3p`) and refuses a filename it cannot map rather
  than guessing. The reader still accepts both conventions.
- **`--add-to` is genuinely in place.** A free root-directory slot plus free
  FAT blocks, no rebuild and no growth, so an existing volume keeps its
  blocks — verified by reading the disk back and comparing the old volume's
  files byte for byte, and by having `akaiutil` list a volume we appended to
  a disk *it* had formatted. `overwrite` frees the old volume's directory and
  file chains first; without that, repeated overwrites leak the disk away a
  volume at a time.
- **FAT walks are bounded and track visited blocks.** A thirty-year-old
  library disk is exactly where a chain that points back into itself turns up;
  the reader raises rather than looping.

### Real library discs (2026-08-05, eight commercial CD-ROMs)

Jan supplied eight real AKAI library CD-ROMs — **895 volumes, 24 334 files,
2.2 GB**. This is the first *hardware-authored* AKAI data in the project, and
it is a different kind of evidence from `akaiutil` agreeing with us: it is what
the sampler was actually shipped.

All eight read without error, and on one 512 MB disc our reader and `akaiutil`
agree on **all 3 922 files** — volume, name and size. Three real samples
exported through `akaiutil`'s WAV converter come back **PCM byte-identical**
to ours, with the same rate, root note and loop type. Feeding real volumes
back through our image writer and re-reading them returns every file
byte-identical. One disc converts end to end to four E4B banks.

Four things the real data settled that neither reference did:

1. **The extension is a rule with exceptions, not a table.** Only `.S1`/`.P1`
   take the generation digit in the S1000 range — an FX file is `.X`, not
   `.X1` — and `.CD` / `.s+` are special-cased away from `.T9` / `.H3`. The
   hardcoded five-entry table left **375 real files unnamed**: 344 `.X`, 17
   `.M3`, 9 `.D`, 5 `.Q`. Now derived from the type byte's range.
2. **Volume type and CD-ROM info are independent.** Seven discs are
   CD3000-typed (`0x07`), only three carry the info block, one is plain S3000
   with neither. Detection needs both checks, so `akai_is_cd3000()` and
   `akai_cd_label()` are separate functions.
3. **The 16-bit total-block cap is real** — every disc lands exactly on
   `0xffff` or `0xfdbe`, with a deliberately short last partition. Our
   writer's check was right, and now has evidence rather than an inference
   from a constant in someone else's header.
4. **Stereo is a `-L` / `-R` name-suffix convention**, not a header flag; the
   spec's `0x88` "stereo partner" is annotated *internal*, i.e. a RAM pointer.
   That is why the writer mixes to mono rather than guessing.

Real files also carry OS version **16.50** and non-zero tags (`05 11`) where
we write 17.00 and none, and names often have **leading** spaces for front-panel
alignment — real data, so only trailing padding is stripped.

### A third-party S1000 disc (2026-08-05)

A ninth disc, mastered by a third party rather than by Akai, is **S1000
format** — `.S1` samples and `.P1` programs, OS version 9.30 — and it exposed
a reader bug that eight Akai-mastered S3000 discs could not.

**An S1000 volume directory is one block of 126 entries; an S3000's is two
blocks of 510.** We used the S3000 shape unconditionally, so we read past the
end of every directory and decoded the following bytes as file entries:
**2 606 files where there are 1 799**, the surplus carrying type bytes like
`0xd4` and `0x89` that map to nothing.

The FAT cannot be used to detect this instead of the volume type: an S1000
harddisk terminates its directory chain with `0x4000`, the **same value** the
S3000 uses for "reserved for system". The shape has to come from the root
directory's type byte.

After the fix all 1 799 files agree with `akaiutil` on volume, name and size,
and the eight S3000 discs are unchanged (82 volumes / 3 922 files on the one
re-checked). The regression test plants plausible entries in two places — past
the 126-entry cap but inside block 1, and in block 2 — and was confirmed to
fail with the bug reintroduced.

Two lessons worth keeping:

- **The corpus was homogeneous and looked diverse.** Eight discs, 895 volumes
  and 24 334 files all shared one volume type; the ninth disc was worth more
  than the eight for finding this.
- The bad output was *plausible*: right file count order of magnitude, names
  that decoded, sizes that looked sane. What gave it away was the tail of
  unmappable type bytes — which only existed because the extension logic had
  just been generalised to name every type instead of silently dropping the
  ones it did not know.

### The S1000 disc kept giving (2026-08-05)

The same third-party disc, once its directory was read correctly, exposed
three more faults — two of them in code that had been "verified" against
`akaiutil` and a real S3000 disc. All three are cases where **two references
agreed with each other and were both wrong**.

**1. An S1000 block is 0x96, an S3000 block is that plus 42 bytes.**
The sample header, program common block and keygroup are all 150 bytes on the
S1000 and 192 on the S3000. With the S3000 lengths, 243 of 335 S1000 programs
parsed as zero keygroups and 1 292 of 1 369 zones named samples that do not
exist; samples lost 42 bytes off the front of their PCM. Fixed: 1 465/1 465
zones resolve and the PCM matches `akaiutil`'s export byte-for-byte.

**2. Byte 0x00 is a block id, not a generation marker.** Both references call
it *"header id — 1 = S1000, 3 = S3000"*. It is neither: `1` = program common,
`2` = keygroup, `3` = sample header, **identical on both generations**. An
S1000 disc's 1 464 samples all carry 3 and its 335 programs all carry 1,
exactly as on an S3000 disc.

That misreading was also a **writer** bug: we wrote `3` into program common —
the *sample* block id — into every program mpc2emu has ever produced.
`akaiutil` cannot catch it, because it takes a file's type from the directory
entry rather than from its contents. Only real files could show it.

The generation is therefore **not in the file at all**; it comes from the
directory entry's type byte. Where that is unavailable the parser infers it
from arithmetic, which is exact on all 6 012 samples of the two discs.

**3. Velocity zone 3 is at 0x52, not 0x53.** The primary spec's `0x53` made
the stride non-uniform, and `docs/AKAI_S3000_FORMAT.md` even flagged the
oddity while following it. Real programs settle it: at `0x52`, zone 3 resolves
to a sample in its own volume **317 times and fails 3**; at `0x53`, **0 and
8 462**. This was wrong in the writer too, which put zone 3's name one byte
into its own field. Only programs actually *using* three or more velocity
zones can show this — 318 keygroups on one disc, none at all on the other.

The golden image hashes were regenerated from `akaiutil` after the writer
changed, so they still encode agreement with an independent implementation
rather than with our previous selves.

**What to take from this:** the AKAI verification story had been "akaiutil
agrees with us". Two implementations agreeing is one *reading* of an
undocumented format, and every fault above survived that check. Real
hardware-authored files are a different class of evidence, and the two that
mattered most (the block id, zone 3) needed files that *exercise* the field —
a corpus can be large and still not touch it.

### Twelve more discs, two more libraries (2026-08-06)

An orchestral library (5 discs, S1000) and a vocal library (7 discs, S3000 —
one of which is a plain ISO 9660 PC disc) were added to the corpus. Both come
from publishers already represented or new, but neither is Akai-mastered, so
they are independent of the eight factory discs in what matters: whoever wrote
the mastering tool. Together
with the earlier nine that is **20 discs across four distinct libraries from
three publishers, 1 835
volumes, 56 214 files, 7.6 GB, evenly split between S1000 and S3000**.

**Nothing broke.** After the fixes the earlier discs forced, this round was
pure validation:

| check | result |
|-------|--------|
| our reader vs `akaiutil`, all 11 new AKAI discs, file by file | **30 081 / 30 081 agree** on volume, name and size |
| programs parsed | 2 745, **0 unparseable, 0 with zero keygroups** |
| zones resolved to a sample on the same disc | **35 087 / 35 088 (99.997%)** |
| samples parsed | 26 846, **0 unparseable** |
| PCM vs `akaiutil`'s WAV export, both generations | **byte-identical** |
| S1000 disc converted end to end to E4B | 4 banks, reads back, every zone resolves |
| real S1000 volumes through our image writer and back | every file byte-identical |
| the ISO 9660 disc | correctly **not** detected as AKAI |

Two things this corpus adds that the earlier one could not:

- **518 keygroups use velocity zone 3 or 4**, independently confirming the
  `0x52` offset on material from two libraries that had not been seen before.
- **Sample rates vary more than expected**: 48 000, 22 050, 11 025 and 8 000
  all appear alongside 44 100. Nothing assumed a rate, but it is worth knowing
  the field earns its keep.

The block-id finding also held everywhere: across 31 880 files, every `.P1`
and `.P3` carries 1, every `.S1` and `.S3` carries 3, `.X` carries 2, and
`.T`/`.M3` carry 0 — with no relationship to generation.

### Five more discs, and a zone rule the corpus had been hiding (2026-08-07)

Five more S3000 discs, five publisher badges not seen before — 25 discs
total, 2 276 volumes, 71 158 files, 9.2 GB. Four of the five validated silently. The fifth did not:
**64.9% of its zones named samples that are not on the disc.**

The names were `SAWTOOTH`, `PULSE`, `SQUARE` — the sampler's **ROM waveforms**,
not files — and their velocity range was `lo=1, hi=0`. An inverted range: no
velocity can fall inside it.

**A velocity zone is disabled by an inverted range, not by a blank name.** Real
programs leave whatever name was in the slot and rely on the range alone. We
were treating any non-blank name as a live zone, so on discs that do this we
invented three phantom zones per keygroup.

Measured across the whole corpus before changing anything — 77 453 named zones:

| | zones | name absent from the disc |
|---|---|---|
| valid range (`lo <= hi`) | 71 646 | **0.23%** |
| inverted range (`lo > hi`) | 5 807 | **98.66%** |

Every one of the 5 990 disabled zones found is exactly `(1, 0)`. After the fix
the offending disc went 64.89% → 0.82% unresolved, the corpus total is 0.23%
(167 of 71 646, genuinely missing samples), and **every disc that was already
at 0.00% stayed there** — the negative control that matters, since a
too-aggressive rule would have silently dropped real zones.

Two further things fell out:

- **Keygroup `0x1f` is not a count of zones in use.** It reads like one, and
  the writer was writing one. Every keygroup on every disc carries **4**
  regardless. The writer now writes 4 rather than inventing a meaning.
- **This answers a question that had been open since the writer was built.**
  `TODO.md` recorded that we write unused zones all-zero and did not know
  whether the sampler wanted that. It does not: it wants an inverted range.
  The old guess was actively harmful, since `0x00` decodes to the digit `0` —
  a zeroed zone reads back as a sample named `"000000000000"`.

**Why the corpus had not caught this**: 20 discs from four libraries, 56 214
files, and none of them used the convention. It took a fifth publisher. The
same shape as the block-id and zone-3 findings — the fault needs material that
*exercises* the field, and more of the same material never will.

### A second spelling of "disabled", and truncated images (2026-08-07)

Five more discs. Two findings, one of them a correction to the fix made
earlier the same day.

**1. `hi_vel == 0` is the disabled-zone test, not `lo > hi`.** The inverted
range `(1, 0)` was only one library's spelling. Another writes `(0, 0)` and
leaves its own branding in the name field — a *valid* range by the earlier
rule, so 5 686 phantom zones came back on one disc (67% of it). MIDI velocity
0 is note-off, so any zone whose `hi_vel` is 0 is unreachable either way, and
that is the general test. Over 54 488 named zones: `hi_vel == 0` resolves
4.43% of the time, `hi_vel > 0` resolves 97.13%.

Worth noting how this was caught: the corpus measurement was re-run after the
first fix, and the disc still showed 66% unresolved. Had the earlier fix been
accepted on the strength of "the offending disc now reads 0.82%", this would
have shipped.

**2. A truncated image now warns.** Two of the five discs were partial
downloads holding **4-5% of what their own partition table declares**. The
reader already dropped files whose data ran past the end — correct — but did
so silently, so a half-downloaded disc converted to a plausible-looking
subset: 55 files where the directory lists 103. It now reports both the size
mismatch and the number of skipped files. `akaiutil`, for comparison, marks
such a partition *invalid* and recovers nothing; we recover the intact files
and say what was lost.

The remaining unresolved zones on one disc (29%) are **not** a misread: the
library's programs reference samples that ship on other discs of its set, with
valid velocity ranges, and our file list matches `akaiutil` exactly. A zone
naming an absent sample is not by itself evidence of a parsing fault.

### A 16-partition disc, and a feature the corpus argued against (2026-08-07)

One more orchestral disc, the 29th: 16 partitions — the most seen, against a
format maximum of 18 — 104 volumes, 2 450 files. All 2 450 agree with
`akaiutil`; 0 unparseable programs or samples; 4 731 zones with 52 unresolved
(1.10%).

Those 52 were checked rather than assumed. Each was matched against its
nearest name on the disc, and the nearest is always a **different note or
channel** (`TK FN A 4 -L` vs `TK FN G 4 -L`; `CEL.MARCG#3L` vs `…G#3R`) — the
signature of samples the library simply omitted, not of a decode fault, which
would corrupt characters rather than produce valid names for adjacent notes.

**A feature the measurement talked me out of.** One unresolved name was
`SINE` — a ROM waveform, which the sampler can layer with a sample and which
is not a file. A dedicated message for those ("references the internal SINE
waveform") looked worthwhile until it was counted: across **47 918 live zones
in the corpus, exactly 2** name a ROM waveform. The generic "sample not found"
warning stays.

### Four more discs, three more publishers, nothing broken (2026-08-07)

Discs 30-33, all S1000: 219 volumes, 5 259 files. Every one of the 3 504
agrees with `akaiutil` on volume, name and size; 0 unparseable programs or
samples; and **all four come in at 0.00% unresolved zones** — 6 736 zones,
every one resolving to a sample on its own disc. PCM spot-checked against
`akaiutil`'s WAV export: byte-identical.

That is the first round where the reader was exercised on unfamiliar material
and found nothing at all, which is what the fixes of the preceding two days
were for. It is not evidence the format is fully understood — the two-day
pattern was that each new *publisher* broke something — but three new
publishers in a row passing is the first sign of the curve flattening.

### Turning the corpus on the writer (2026-08-07)

Everything up to here used the discs to check the **reader**. They answer a
sharper question about the **writer**: for each byte we emit, does any real
file ever hold that value? An offset where ours never appears is a guess the
format disagrees with — and unlike a reader bug it produces a file that looks
fine to us and to `akaiutil`, because both are our own interpretation.

Method: byte-value distributions per offset over 11 238 real S3000 samples and
4 433 real programs, compared against what `build_sample`/`build_program`
emit. **26 offsets held a value no real disc writes. There is now 1.**

The corrections are tabulated in `docs/AKAI_S3000_FORMAT.md` §"What the corpus
says about the writer". The ones that matter:

- **`0xFFFF` is the format's null pointer**, and we were writing `0x0000` — in
  the sample's stereo-partner field and in two pointer fields per velocity
  zone. Zero is not "none" here; it is a valid address.
- **Blocks carry their own RAM address** at `0x01-0x02` in 16-byte paragraphs,
  chained `+12` per 192-byte block. 19 553 consecutive deltas of exactly 12
  across 2 058 programs, and **not one real file leaves it zero**. It is a
  save-time artifact the sampler recomputes, so zero is *probably* harmless —
  but "probably harmless" is the reasoning that produced four of the five
  faults on this branch, and matching the observed shape costs nothing.
- **Play range belongs wide open.** We were writing the span of the keygroups
  actually present; 96% of real programs write `24`/`127` regardless. Ours
  sounds identical today and silently mutes any keygroup added later on the
  sampler itself.
- **Unused zone names are spaces, not zeros** — the same `0x00`-is-the-digit-
  `0` trap that has now bitten in three separate places.

Two differences are deliberate and recorded so they are not "fixed" later:
all-zero **file tags** (never observed, but the documented "free" value, and
inventing a tag number would file the user's samples under a category they did
not choose) and **OS version 0x1100** (the S3000 maximum; real discs span 4.30
to 17.00 and 0x1100 occurs 335 times).

The image-level structures — partition sizing, volume load numbers, the TAGS
magic, the 48 volume-parameter bytes — were checked the same way and are all
already within the observed range.

**What this does not do** is validate the *semantics*. It shows our files now
look like real ones byte-for-byte in every field where real ones agree with
each other. Whether the sampler accepts them is still the open question.

### Two more discs, and a re-fetched one (2026-08-08)

**Ueberschall Drum'N'Bass Resonance** — a seventeenth library, a thirteenth
publisher badge, and at 701 MB the largest file in the corpus (its AKAI area is
still the usual `0xffff` blocks; the rest is padding). 63 volumes, 4 243 files,
4 032 zones, **0 unresolved**, nothing unparseable, PCM byte-identical to
`akaiutil`'s export.

**E-Lab X Static Goldmine 2**, re-fetched complete.** The copy deleted on
2026-08-07 held 4% of what its partition table declared, and the truncation
warning added then reported it correctly: 24 volumes and 318 files, with 10
more skipped for running past the end of the file. The complete disc holds
**137 volumes and 3 727 files** — so that warning was the difference between
converting a disc and converting 8% of one, silently.

All 16 discs currently on disk were re-swept at the same time: every file on
every disc still agrees with `akaiutil`, no program or sample fails to parse,
and every disc is at 0.00–1.10% unresolved zones except the one known case —
the drumloops disc at 29.55%, whose programs reference samples that ship on
other discs of its set (see above; not a fault).

The corpus is now **37 distinct discs**, after a two-disc bass library was
added (below). The 18 on disk (1 432 volumes, 41 227 files) can be re-verified
at any time; the other 19 were measured and deleted to reclaim space, and the
two sets do not overlap.

### A two-disc bass library, and the widest OS-version range yet (2026-08-08)

Both discs of an eighteenth library. CD1: 58 volumes, 1 931 files, **8 740
zones, 0 unresolved**. CD2: 34 volumes, 1 396 files, **5 790 zones, 0
unresolved**. Every file on both agrees with `akaiutil`; nothing fails to
parse; PCM byte-identical to `akaiutil`'s export.

Three things they add that the rest of the corpus did not:

- **OS versions down to 2.21.** The field had spanned 4.30 to 17.00; these
  programs go lower. Another reason the version is read rather than assumed —
  and a reminder that our own writer's fixed `0x1100` sits at the very top of
  a range that is far wider than it first appeared.
- **They exercise velocity zones 3 and 4 heavily** — 211 keygroups with three
  zones and 6 with four, from a publisher whose other discs never used them.
  A third independent confirmation of the `0x52` offset.
- **Sample names beginning with `-`** (`-MM RAGG E 2`). Harmless here —
  `safe_filename` keeps `-` and nothing shells out — but it is the kind of
  name that reaches a real filesystem, and it did break an `ls` during the
  check.

Both carry `.D` drum files (56 and 33) which are named and carried correctly
but never read: the known auxiliary-type gap.

### What this does NOT establish

That the sampler mounts any of it. Two independent implementations agreeing is
still two readings of the same undocumented format.

Specifically unverified:

- Whether the sampler accepts a disk whose partitions we sized, as opposed to
  one it formatted itself.
- The 48 bytes of volume parameters. We reproduce the observed defaults
  (`00 01 01 00 00 00 32 09 0c ff` then zeros) verbatim; no source names a
  single field in them.
- Whether a partition smaller than 60 MB, or a disk with several partly-filled
  partitions, is handled the way the front panel expects.

### First hardware checks, in order

**Read the cross-project order below first.** These five are this project's
half; the sibling s3ked has its own, and running either half straight through
in isolation wastes the trip.

1. **Does it mount?** Write an 8 MB `--hda`, put it on the ZuluSCSI as
   `HD0_512.hda`, and see whether the sampler lists a disk at all. If it does
   not, nothing below matters — and the first thing to try then is an image
   `akaiutil` formatted, to separate "our writer is wrong" from "this whole
   approach is wrong".
2. **Does the volume list look right?** Volume names, and the empty
   `VOLUME 002`… slots.
3. **Does a program load and play?** This is also the file-level check the
   AKAI TODO row asks for — the zone names on the display settle the
   unused-velocity-zone encoding at the same time.
4. **Format a disk on the S3000XL itself and diff it against ours.** One
   comparison settles the volume parameters, the partition sizing and the `??`
   regions together — the same move that settled the file format.
5. **Floppy**, via the Gotek: same three questions, and it is the cheaper
   medium to iterate on if step 1 fails.

### The cross-project order (mpc2emu + s3ked), agreed 2026-08-08

The obvious plan — confirm s3ked completely, then confirm mpc2emu — has the
dependency backwards in one place. **s3ked's calibration sweeps need a disc
this project wrote**: s3ked can set any parameter over SysEx but cannot put a
sample in memory, and the family has no oscillator, so with an empty machine
every sweep records silence. The two halves interleave.

Also worth knowing when planning the evening: `s3kcli status` answers on an
empty machine, but `programs`, `samples` and `header` all need something
loaded. A disc goes in early regardless.

| # | what | project | why here |
|---|------|---------|----------|
| 1 | `s3kcli ports`, `s3kcli status` | s3ked | Ten minutes, no media, read-only. Either the protocol answers or that project's whole foundation is wrong, and that is worth knowing before anything else is carried in. |
| 2 | Load a **commercial** disc; then s3ked steps 3–6 (program list, sample list, header diff vs the panel) | both | Someone else's disc separates "the drive/ZuluSCSI path works" from "our image is wrong" — the distinction that otherwise costs an hour. |
| 3 | **Format a disk on the S3000XL itself**, diff against ours | mpc2emu | Independent of everything else, costs one format, settles volume parameters + partition sizing + the `??` regions together. Do it while the machine is on. |
| 4 | Our own `--hda`: mount, list volumes, load and play a program | mpc2emu | Confirms this project's disk writer. Prerequisite for 6. |
| 5 | **The cross-check.** mpc2emu writes a program with *known* parameter values; s3ked reads that header back | both | The step worth planning around — see below. |
| 6 | s3ked's first write + throttle floor | s3ked | |
| 7 | Calibration sweeps | s3ked | Needs 4 (our disc loads) and 5 (offsets are right). Unattended once started. |

**Why step 5 is worth more than either project's own checks.** mpc2emu's
offsets came from `akaiutil` plus the disk-format documentation; s3ked's came
from Akai's SysEx documents. Those are two independent sources describing the
**same** 192-byte program and keygroup headers — one as they sit on disk, one
as they are addressed over the wire. Agreement confirms both at once, which
neither can achieve alone; disagreement names the field to take to the front
panel. The caveat: where both inherited the same Akai numbering, agreement is
not proof, so the panel stays the tiebreaker for anything surprising.

**Batch by the expensive step.** The costly move here is the SD-card / media
swap, and only this project needs it — every s3ked operation is SysEx. Run
steps 2–4 back to back with the card out once, rather than alternating between
projects. (Only one session may drive the sampler at a time.)

---

## §CWM202 — ConvertWithMoss cross-check (2026-08-13)

Checkpoint moved from `8e2345fa` to `b465b8f0` (10 commits, all dated
2026-08-13). Four touch formats we share; the rest are Waldorf and Fairlight.

**Nothing here needs a change from us, and two of the four we already do.**

* **#345, case-insensitive sample lookup.** Their presets could not find
  samples on Linux because sampler CD-ROMs store names upper-case while a
  preset may reference them lower-case. **We already do this** — the fallback
  index keys on `f.name.lower()` and looks up `name.lower()`.

* **#338, search outward from the nearest folder.** Their search jumped all
  configured folder levels at once and took whatever a recursive walk found
  first, so with two libraries under one download folder a preset got the
  OTHER library's identically-named sample — and kept its own loop points, so
  the loop wrapped in a differently-long sample and clicked. Found with two
  Ensoniq libraries both holding `RHODES C3 FF.wav` at 42384 Hz/5280 frames
  and 44100 Hz/5469 frames.

  **We already do this too, by construction rather than by design**: the
  ancestor list is built nearest-first and the index uses `setdefault`, so
  first-wins IS nearest-wins. Verified by reproducing their exact layout —
  preset at `LibA/presets/`, the name present under both `LibA/samples/` and
  `LibB/samples/` — and we return LibA's.

  Worth noting this is the same FAMILY as our own 2026-08-12 resolver bug
  (`bd51347`), where the walk order was unsorted so resolution rode on
  filesystem directory order. Two projects, same function, two different ways
  for the wrong file to win.

* **#340, warn when a loop will click.** NOT covered here, and the one worth
  considering. They now check every forward loop without a crossfade for a
  discontinuity at the wrap, having found **17 of 152 presets across three
  commercial libraries** ship loops whose boundaries land on non-matching
  values. Our `--auto-loop` creates click-free loops; nothing checks the loops
  we pass THROUGH from a source, so a clicking source loop converts silently
  and the first hint is the destination device ticking.

  Cheap if wanted: `processors/auto_loop._match_cost()` already computes a
  normalised SSD across exactly the two windows a wrap blends, and
  `_RESCUABLE = 0.45` is already calibrated as "what a crossfade can hide".
  A pass-through warning is that function plus a call site.

  **Before building it, read this (VinSamLib, 2026-08-14).** They built the
  detector and three repairs, and their own success measurement came out
  wrong: a cross-fade repair that works *by construction* scored as fixing
  only 42 % of cases. The repair was correct. Their detector compares the step
  at the wrap against a window median, and a loop start sitting on a steep
  slope has a large natural step there — so a perfectly continuous join got
  flagged. The number would have steered users away from the only repair that
  always works.

  Two things follow for us. A wrap-discontinuity detector must compare the
  step against **the waveform's own local slope**, not against a window
  statistic, or it reports the steepest material as the most broken —
  precisely inverted. And a repair whose correctness is structural should have
  its measured effectiveness treated as a test OF THE DETECTOR when the two
  disagree, not as a result about the repair. `_match_cost()` is a windowed
  SSD rather than a single-point step, so it is less exposed to this than a
  naive step test — but "less exposed" is not "immune", and it has never been
  measured against loops known to be fine.

  Their measured repair effectiveness, for reference, on 101 clicking loops
  from real banks: snapping both points to the nearest same-slope zero
  crossing fixes 64 %, nudging the loop end to the best-matching position 99 %,
  cross-fading 100 %. None applied automatically; the user chooses.

  **Prevalence per format, measured 2026-08-14 across their corpus:**
  E4B **96 of 3416** looped headers (2.8 %), EIII **1 of 237**, KRZ
  **1545 of 11551** (13 %). So it is predominantly a KRZ-source problem, but
  E4B is not the rarity it first appeared.

  **The E4B figure was corrected within two hours of being published, and the
  correction is the more useful half.** It was first reported as 11 of 2294 —
  0.5 % — from a sweep whose file loader capped at 40 files, then quoted as a
  corpus rate. Over all 131 E4B files it is 2.8 %, nearly six times the share,
  and the difference between "vanishingly rare" and "one preset in twenty".
  Their diagnosis: *wrong population, not wrong rule.* The KRZ row came from a
  disk-image walk that covers everything and stands; EIII had only three files
  to begin with and stands as the thin result it always was.

  We had already copied the 0.5 % figure here. A number arriving with a
  denominator is not the same as a number arriving with a POPULATION — 2294
  looked like a corpus and was the output of a capped loader, and nothing in
  the figure itself said so. Ask what was actually walked before quoting a
  rate, including one of our own.

  And a warning about building the detector, from the bug that nearly buried
  their whole result. A `big_endian` flag landed as a third argument to
  `max()` instead of reaching the frame decoder, so the movement window was
  decoded big-endian while the seam frames were decoded correctly. Little-
  endian E4B and EIII windows scrambled, the median frame-to-frame movement
  exploded, and the ratio test could never fire: **4703 loops reported
  perfectly clean, which is indistinguishable from a clean corpus** and was
  believed until a known click was injected and went unnoticed. The docstring
  warning about exactly that failure sat one line above the call that got it
  wrong.

  So if we build this: the acceptance test is an INJECTED click in a loop the
  reader calls clean, per format, required to be found — not a corpus scan
  that comes back quiet. A detector that cannot fire looks exactly like a
  corpus with nothing wrong in it. Scale the injected step to the material,
  since a fixed offset is a click in a slow waveform and nothing in a fast one.

  Audited our own code for that argument-absorption shape while recording
  this: three `min()` calls take three positional arguments
  (`parsers/akai_image_parser.py`, `parsers/xpm_parser.py`,
  `processors/auto_loop.py`) and all three are genuine three-way numeric
  minimums with no flag among them.

* **#344, E-mu Emulator II floppy disks.** An FM decoder for HFE track
  encoding 0x03, which is not IBM System 34: address mark `FA 96` rather than
  a missing-clock pattern, a single track number rather than
  cylinder/head/sector/size, one 3584-byte sector per track (no IBM size code
  expresses it), CRC polynomial 8005 with initial value 0000 over the payload
  alone, LSB-first at both bit and byte level.

  Not ours — we read EIII/E4B disk images, not Emulator II floppies, and have
  no HFE path at all. Recorded because it is the only E-MU work they have done
  since our last two checkpoints, and because those parameters would be the
  starting point if Emulator II support were ever wanted.

---

## §CWM201 — ConvertWithMoss 20.1.0 cross-check (2026-08-08)

Checkpoint moved from `80e6076e` to `8e2345fa` (28 commits).

**The release contains no MPC and no E-MU work.** It adds Teenage Engineering
OP-XY, Casio FZ and Audiomodern Soundbox, and fixes 1010music, DecentSampler,
Fairlight, Korg, Roland MC-707, Roland S-7xx, Synclavier and Yamaha. Nothing
in it is about the formats this project shares with it.

What it was still worth reading for is **fault families**. Four were checked
against this codebase and found already correct — recorded so they are not
re-checked next time:

| CWM fixed | ours |
|-----------|------|
| a preset name with `&`, `<`, `>` or a quote produced malformed XML | not applicable: `talsmpl` writes through `ElementTree`, which escapes |
| upsampling 8-bit gave silent samples; 8→24 set UNSIGNED instead of SIGNED | `_convert_8_to_16` already treats 8-bit WAV as unsigned; a 128-centred input comes out centred on zero |
| 32-bit float samples as input | already supported (`_WAVE_FORMAT_IEEE_FLOAT`) |
| WAV metadata unreadable behind a large padding chunk before `data` | our RIFF walker reads a 5 KB `PAD ` chunk correctly |

One found a **real bug here**. Three separate CWM writers had kept characters
illegal in filenames (DecentSampler's DSBUNDLE folder, 1010music's preset
folders, Audiomodern's preset and group names). Checking the same family
locally showed `_bank_path` building the output path straight from
`bank.name` — so `--bank-name "Rock/Pop"` wrote **zero files and still printed
"Done"**, on both `e4b` and `krz`. Fixed in `f76e09d`.

The uncomfortable part: `73da40d` had already fixed exactly this for *preset*
names a day earlier, after the release matrix hit it in the `talsmpl` writer.
That fix stopped at the level where the fault appeared instead of asking where
else a name becomes a path. **When a bug turns out to be "a name used as a
filename", the fix is to find every place that does it, not the one that
crashed.**

Two further items are relevant but not actionable:

- **Roland S-7xx**: locating sample data through the FAT and the directory
  entries rather than assuming a contiguous block, and skipping deleted
  entries so following references do not shift. Our AKAI image reader already
  walks the FAT, and AKAI programs reference samples **by name**, so a skipped
  entry cannot shift anything.
- **Continuation disks** whose names carry trailing spaces. We have the same
  situation unsupported: one library disc's programs reference samples that
  ship on other discs of its set (see the AKAI notes). Not a fault, but the
  same problem exists here and CWM has now solved its half of it.

---

## §GIGE2E — GigaSampler end to end, over 146 real files (2026-08-09)

**Status: verified. `.gig` is no longer a declared gap in the release matrix.**

`.gig` had a matrix row and no fixture — "no local GigaSampler file" — so the
parser had unit coverage and the path from a real GIG to a written bank had
never been walked. `~/linuxsampler` holds **146** of them (1.4 GB), which
closes that.

### What was checked

| | |
|---|---|
| files parsed | **146 / 146**, no failures |
| totals | 151 presets, 910 samples, 2 698 zones |
| converted end to end | 12 files × 4 output formats = **48 conversions, 0 failures** |
| content preserved | key coverage identical in 11 of 12; the 12th is explained below |

Both extension cases occur — 117 `.gig` and 29 `.GIG` — and both work: the
registry holds `.gig` only, but `convert.py` lower-cases the suffix before the
lookup. Worth stating because it looked like a 20% gap until it was tested.

### The one difference, and why it is not a loss

KRZ reports FEWER zones than the source for several files (61 → 16, 61 → 7,
61 → 13). That is re-grouping, not loss: a KRZ keymap is 128 entries and
`krz_parser` merges contiguous runs of the same sample back into one zone, so
61 single-key zones over one sample come back as a handful of ranges. **Key
coverage is identical**, which is the measure that matters — comparing zone
counts alone would have raised a false alarm here, and did until coverage was
checked.

One file gains keys (60 → 128). That is the documented keymap gap-fill:
`krz_writer` fills holes because a hole locks the K2000 up on Master→Delete,
and the trade-off is recorded in `TODO.md`.

### Fixture selection

The matrix picks its GIG **by rule** — the smallest file carrying at least 5
samples and 5 zones — rather than by name, so the cell does not depend on one
library staying where it is, and no commercial filename enters a tracked file.

### MPC60 closed too, the same day (2026-08-09)

`.set` and `.img (MPC60)` were the last two declared gaps, and for the same
reason as GIG: every local SET was a **720K-truncated** copy that the parser
correctly refuses, so the intact path had never run. Two archives of intact
**800K** disks (819 200 bytes exactly) closed it:

| | |
|---|---|
| disks parsed | **34 / 34** |
| totals | 34 presets, 664 samples, 459+205 zones, 40 kHz throughout |
| end to end | 4 disks × 4 targets, key coverage preserved |

The fixture filters on the 819 200-byte size on purpose. Emptying `NO_FIXTURE`
re-activated a legacy line that pointed `.img (MPC60)` at the old truncated
copies and silently overwrote the intact fixture — four green cells became
four red ones, and the cause was a fixture-selection line rather than any
parser. That line is gone; the size filter is what stops it recurring.

**Nothing is now marked "no fixture".** The remaining honesty about coverage
is elsewhere: `.sf2` and `.exs` are synthesised, and axis C does not cross the
sub-options of the flags it drives.


## KRZ keymap: reporting the up-pitch ceiling clamp

Companion to the TODO of the same name.

**How to fix:** the mechanism is already in place — `_build_keymap_entries`
now returns a `lost_zones` list that `write_krz` renders into one summary.
Add a second category to it for ceiling-clamped zones rather than a second
warning: one message, two reasons, so the output does not grow a warning per
defect class.

**Measure first.** The low-key warning shipped on 2026-08-09 in a form that
fired on nearly every bank, because clipping the bottom off a catch-all zone
is the normal shape of a multisample, not a defect. A code review caught it on
two of our own test banks. Before reporting ceiling clamps, count over the
corpus how many zones are *entirely* lost (`ceiling < lo_key`) versus merely
clipped, and report only the first — the same distinction that made the
low-key warning correct.

**Open question for Jan:** when a zone IS entirely lost to the ceiling, is
dropping it right at all? `_compute_max_pitch` exists because the K2000
cannot up-pitch a sample indefinitely; the alternative is to keep the zone and
let it play flat above the ceiling. That is a hardware-audible judgement call,
not a code decision.

---

## §ENVSPAN — ANSWERED: the EOS envelope byte is a RATE (2026-08-18, hardware)

**Measured on the E4XT by eosed. Both controls pass, each preset twice.**

```
LO   sustain 20%  byte 72   0.540 0.540  -> 0.540s
HI   sustain 80%  byte 72   0.140 0.130  -> 0.135s
CTL  duplicate of LO        0.550 0.560  -> 0.555s     CONTROL 1: 15 ms from LO   PASS
REF  sustain 20%  byte 84   1.070 1.050  -> 1.060s     CONTROL 2: 1.96x from LO   PASS

RESULT  LO/HI = 4.00x        DURATION predicts 1.00x
```

**Same rate byte, four times the time. DURATION is dead.**

### The law, which fell out because no ratio was predicted

```
LO  sustain/peak 0.177 -> dB span 15.0      dB-span ratio  4.09
HI  sustain/peak 0.655 -> dB span  3.7      measured time  4.00     agree to 2%
                                             LINEAR span ratio 2.38  <- would be wrong
```

**The decay is linear in dB, and the time is the dB distance over a constant
rate.** The plan deliberately refused to predict a numeric ratio because the
level is a dB law and a linear guess would have been a number invented from an
assumption — that refusal is what makes this readable. A "roughly 4x" prediction
from linear percentages would have been **right for the wrong reason**, and
nobody would have noticed.

### Free calibration from the REF control

Byte 84 against byte 72, same span, 1.96x the time. **+12 on the rate byte
halves the rate** — one data point, but the first anyone has on that axis.

```
rate(72) = 27.9 dB/s     rate(84) = 14.2 dB/s     halving every ~12.3 bytes
```

Our existing `ENV_RATE_K` implies a doubling every **11.9** bytes, so **the SHAPE
of our byte↔time model is very nearly right**. What is wrong is what it is
anchored to.

### What is actually broken in shipped code

`env_seconds_to_rate()` takes no span argument. Solving for the span at which our
model and the machine agree gives **≈55 dB — i.e. decay all the way to silence.**
That is exactly how the original calibration was built: `AMP_DECAY_CAL.E4B` set
`sustain=0` deliberately "so decay is audible". **The calibration is correct for
its own span and wrong for every other**, and every decay to a non-zero sustain
is therefore too fast.

### THE FIX IS BLOCKED, and by a second discrepancy this exposed

The obvious repair is `env_seconds_to_rate(seconds, span_db)`. **It cannot be
written yet**, because computing the span needs the achieved sustain level, and
our model disagrees with the measurement:

```
model 0.20 -> byte 107 -> we predict 0.208   eosed MEASURED 0.177
model 0.80 -> byte 122 -> we predict 0.821   eosed MEASURED 0.655
```

Our own numbers give a span ratio of **8.0x** where the machine gives **4.00x**.
A span-aware conversion built on `env_sustain_to_byte` would be **wrong by a
factor of two** — a correction that looks principled and is not.

**So the rate question is closed and the fix waits on a sustain-LEVEL sweep.**
§E4BLEVEL records that law as hardware-measured; these two points disagree with
it, and two points cannot re-fit it. That is the next bank: sustain across its
range, achieved level measured, at a single fixed rate byte.

**Do not "fix" the decay conversion before that exists.** The temptation is
strong because the rate finding is solid, and the result would be a
confidently-wrong number in place of a confidently-wrong number.


## §RULER — a ruler that saturates against its source is measuring the source

s3ked, 2026-08-12, after their `FILFRQ` law turned out to read 20–30 % high by
a *growing* amount: it had been derived from a spectral centroid, and a
centroid is the average frequency of everything the **source** contains. It
sits above the corner by however much energy lies above it, and that mix moves
as the corner moves — so the error is in the **slope**, not the offset, and no
single correction factor could have removed it.

Their warning to us was explicit: *if you have a filter-frequency law derived
from any spectral-summary statistic — centroid, rolloff, brightness — it is
probably biased the same way.*

**Checked, and we are structurally clear but had a live trap.**
`corner_frequency()` measures a −3 dB point against a reference band, which is
a transfer-function measurement rather than a spectral summary — the right
kind. But the source-cancelling `reference=` argument was **never passed at any
call site**, so every corner we have measured was taken against the signal's
own 100–500 Hz band, and that is only the filter's response if the source is
flat there.

Measured on synthetic input, wide-open filter, no reference:

| source | reported corner | truth |
|---|---|---|
| white noise | none found (correct) | no corner |
| sawtooth (−6 dB/oct) | **502 Hz** | no corner |
| sawtooth, real 3 kHz filter | **502 Hz** | 3000 Hz |
| white noise, real 3 kHz filter | 3025 Hz | 3000 Hz |

With a falling source the function reports the source's own rolloff and is
completely insensitive to the filter. The MPC cutoff work used white noise and
is fine; anything measured on a saw through this path is not.

`corner_frequency()` now refuses when the reference band tilts more than 3 dB
without a `reference=` capture. With one, the source divides out exactly and a
saw gives 3025 Hz for a true 3000 Hz corner — the same answer as noise.

**A ceiling can fake r² 0.99999 — and one extra run exposes it (s3ked,
2026-08-12).** Measuring envelope 3, their corner saturated at 6650 Hz at full
modulation depth — the top of the *filter's* range, not the instrument's. The
timings fitted an exponential at **r² 0.99999** and were wrong. What exposed it
was repeating the sweep at a second drive level: the two disagreed by a factor
approaching 2.0, exactly their depth ratio, which is what a linear ramp read
through a ceiling produces, since the time to cross a fixed fraction of a
*truncated* span scales inversely with drive.

> **A law that changes when the drive changes is not a law.**

An excellent r² cannot see this, because it is faithfully measuring how
consistently the ceiling clipped. **Open for us:** our E4XT cutoff, gain and
pan laws were each fitted at one fixed drive level, and none has been repeated
at a second. That is one extra run per law and it is the cheapest check
available against this whole class. Not blocked on anything but bench time.

*And for the 2 dB gap it is a THREE-WAY discriminator, not a confirmation
test* (s3ked, 2026-08-12). The ceiling hypothesis makes a **numeric**
prediction rather than a qualitative one: with a linear ramp read through a
ceiling, the time to cross a fixed fraction of a truncated span scales as
1/drive exactly — which is why their two drive levels disagreed by 2.02
against a drive ratio of 2.0. So: **halve the drive and re-measure.**

| the gap becomes | conclusion |
|---|---|
| ~4 dB | a pure ceiling; it scales with drive |
| ~2 dB, unmoved | a real offset between the datasets, and the shape argument keeps its force |
| anything else | a third thing neither hypothesis covers |

The null result is informative here, which is not usually true of a ceiling
hunt: "it did not move" is positive evidence *against* a ceiling rather than an
absence of evidence. One run separates three hypotheses instead of confirming
one.

**The one-sided case, tested 2026-08-12.** s3ked's stated range stops at
FILFRQ 44..92 not because the machine stops there but because their sawtooth
runs out of harmonics above the corner and drops below the lowest fundamental
below it — *both ends fail by going one-sided, limits of the source rather than
the method.* Asked whether ours fabricates a number in that case: with a
`reference=` capture and **independent** noise in each capture, a corner inside
the reference band reads 3025 Hz against a true 3000 Hz, repeatably; a corner
at 12 kHz, beyond where the reference has any signal, returns **NaN every
time**. It degrades to "no corner found" rather than to a wrong number, which
is the genuine-outcome NaN this file distinguishes from the impossible-request
one.

Worth noting how that test nearly passed for the wrong reason: the first
version built the filtered capture from the *same* noise array as the
reference, so the noise divided out exactly and the estimator looked robust at
12 kHz. Two captures never share a noise realisation. Same shape as the null
pass that measured whether one path repeats.

**And one thing our own headline result does not establish.** The E4XT cutoff
ladder passed 12/12 on hardware, measured==requested. That check runs through
the *same* estimator that produced the calibration, so per §AGREEMENT it rules
out inversion and arithmetic error and says nothing about estimator bias. An
independent check would need a different instrument — a tuned oscillator swept
against the filter, or the resonance-peak differencing s3ked moved to.

---

## §AGREEMENT — what a second source actually rules out

A rule this project earned expensively over 2026-08-10/11, in exchange with
the VinSamLib and s3ked projects. Recorded here because it decided three
separate arguments in two days and will decide more.

> **Agreement between two sources rules out only what they do NOT share.**

The question to ask of any corroboration is therefore not *"do these agree"*
but *"what do these two have in common, because that is the part still
untested."*

### A corpus of authored artefacts cannot bound a tool that authors differently

VinSamLib, 2026-08-12, having measured 499 real AKAI volumes from 23 images
before deciding whether a capacity warning was worth writing:

```
    exceeding a 32 MB machine:   0 of 499
    median 1.8 MB, largest 15.4 MB = 48 % of a 32 MB machine
```

Read carelessly that says the hazard does not exist. It says nothing of the
kind. **Every one of those volumes was authored by somebody for a sampler, so
of course they fit.** The corpus measures an authoring convention, and the
thing being built — a volume assembler fed an arbitrary folder — is the first
link in the chain not subject to that convention.

> **Corpus silence about X is evidence only if the corpus population is
> subject to the same constraints as the thing you are building.**

This is the same error as the 229/191 case in the table above, in its most
dangerous form: there it produced a wrong belief, here it would have prevented
a correct feature. A null that argues *against* writing a guard deserves more
scrutiny than one that argues for it, because it is self-executing — nobody
reviews the check that was never written.

**Where this bites us.** Every corpus we own is authored artefacts: 681 E4B
files, 318 KRZ, 1017 EIII banks, 499 AKAI volumes. Each is evidence about what
the machines and their authors did, and *none* of it bounds what our writers
can emit — our writers are not bound by the conventions that produced it. So
"no bank in the corpus does X" is never on its own a reason to skip a guard
against our doing X.

### The constructive half — what DOES earn trust (s3ked, 2026-08-11)

Everything below this line says what fails to establish a thing. The positive
form, which took the same two days to find:

> **A law earns trust by predicting a measurement it was not fitted to.
> Agreement among things fitted together is arithmetic.**

The case that produced it: an AKAI `SUSTN1` level law and a `RELSE1` rate law
were fitted from separate sweeps, and neither was fitted to a third dataset —
release behaviour across five sustain levels. Both predicted it, to 0.33 dB
and 1.8 %. The run could have refuted either and did not. That is worth more
than any number of internally consistent checks, and it is the standard our
own KRZ reader still does not meet (§KRZREAD — zero external evidence).

Note the asymmetry in cost: a prediction test needs no new apparatus, only the
discipline of stating the prediction **before** looking. Three of s3ked's
passes mistook fitted-together agreement for this, and each cost a retraction.

**We already have one, and it is ours: `KEY_FILTER_OCT_PER_OCT = 0.713`.**
Measured 2026-06-12 as a slope over C2–C4 (71.3 cents/semitone, r = 0.9994).
Independently, the `0x38` LFO→Filter sensitivity was measured at ±3.8 octaves
per 100 %. If the Key modulation source is normalised across the full
keyboard — ±1.0 over ~128 keys — then one octave of key moves the source
12/128 × 2 = 0.1875, and 0.1875 × 3.8 = **0.7125 oct/oct predicted against
0.713 measured**, from a sensitivity the keytrack fit never saw. Two different
cords, two sessions, 0.07 % apart.

So 0.713 is not "the hardware maximum, annoyingly not 1:1" as the constant's
comment frames it. It is *what full-keyboard normalisation implies*, and the
agreement is evidence rather than arithmetic.

### A third thing a comparison cannot tell you: "none of these" (s3ked, 2026-08-12)

Ranking candidate model families returns the **least wrong** one, never
evidence that a right one was offered. s3ked's §36: four shapes fitted to a
clipped velocity curve, all fitting badly, and the most curved won by bending
toward the flat top. The true law — piecewise linear — was not among the four,
and nothing in the comparison could say so.

This is the same rule as the rest of this section, one level up: a comparison
rules out only the alternatives it contains. It bites us wherever a law was
chosen by ranking r² across families rather than by testing the winner in its
own right.

**The guard is absolute, not relative.** A best-of-N winner with all-bad
candidates shows up as *structured residuals* — runs of the same sign, a
visible bend, error growing with x. r² cannot see it (see the 2 dB note: both
of s3ked's competing `ATTAK1` fits sat at r² 0.99991 while one was broken), so
the check has to look at residual *shape*, not fit quality. Any law here whose
provenance is "best of the shapes we tried" should carry that check before it
is called measured.

*Refuted on the way, 2026-08-11, and worth keeping.* s3ked found their AKAI
`K_FREQ` referenced to note 64, having previously assumed 60 — an assumption
that made full 1:1 tracking read as 8.4 semitones per octave. The obvious
worry was that our 0.713 was the same artefact, and a reference of 64 with a
test note of 74 does reproduce 0.714 almost exactly. **It cannot be**: ours is
a gradient, not a point ratio, and a wrong pivot moves the intercept while
leaving `d(shift)/d(note)` untouched. The 0.714 was found by filtering a grid
of (reference, note) pairs for anything near 0.713, which is how numerology
looks from the inside — the check that settled it was asking what the number
was the answer to, not searching for a way to make it fit.

Worked cases, all from this project's own history:

| two sources | shared | so it rules out | and does NOT rule out |
|---|---|---|---|
| two parsers (ours + VinSamLib's) reaching the same AKAI zone offsets | one document | **transcription** error | the document being wrong |
| two detectors (amplitude + filter) agreeing on an envelope law to 0.16 % | one **model**, applied to both | **detector** error | the model — and the model was wrong (durations, not rates) |
| two corpora of commercial K2000 banks, max 229 presets / 191 samples | one **authoring convention** — both libraries written for unexpanded hardware | transcription, sampling | that 229/191 is a machine limit. **It is not.** Measurement gave 600+ |
| our KRZ writer byte-identical to `akaiutil` | one reading of an undocumented format | our arithmetic | either implementation being right |
| `tests/test_krz_roundtrip.py` — write a bank, read it back, compare | **our own `krz_parser`, on both sides** | **writer** error | **reader** error, at all |

The third row is the one that cost real work: two independent libraries
agreeing looked like strong evidence for a hardware ceiling, and it was
evidence about how people authored banks in 1994. Only a disc built to exceed
it settled the question.

The KRZ round-trip row is ours and was found by VinSamLib pointing this rule
at their equivalent tooling. It matters more than it looks: there is **no
foreign KRZ reader anywhere** for either project to compare against, the way
`akaiutil` serves for AKAI. A wrong offset or a wrong band decode makes both
sides of a round trip agree — wrongly — and every check reports clean.

So a round-trip pass count is a statement about the WRITER. The only thing that
could test our KRZ **reader** structurally is a K2000 playing a bank we built
from a PARSED KRZ source: a misread source produces a wrong-sounding bank, and
that is the one step in the chain that does not pass through `krz_parser`.

**Counted honestly, that evidence is currently ZERO.** Every hardware-confirmed
KRZ bank in this project was built from a NON-KRZ source — XPM, E4B, GIG — so
each one tests the writer. Our KRZ→KRZ path was checked by
`tools/krz_to_krz_check.py`, which is parse → write → parse → write → parse:
our reader on every side, the blind spot in its purest form, and never heard on
hardware. (VinSamLib counted their equivalent at six programs from six source
banks. Ours is none.)

**The cheap test, and its shape is the finding** (VinSamLib, 2026-08-11):

> Reader confidence scales with SOURCE DIVERSITY PER LISTENING MINUTE, not with
> bank size. Every program from one source bank re-tests one parse of one file.

So the useful experiment is one program from each of ~20 DIFFERENT source KRZ
banks, chosen for distinguishable sounds, played briefly — roughly twenty
minutes at the machine. A 796-program bank from 70 sources is the opposite
shape: it tests the machine's capacity, costs eleven minutes to load, and adds
almost nothing here.

**And stated for readers in series**, which is where it gets worst. VinSamLib
instrumented their KRZ paths on 2026-08-11 rather than re-reading the dispatch
code, and found:

| path | who reads the user's file | who reads what |
|---|---|---|
| whole bank | **their** reader | ours never sees it |
| single preset | **their** reader | their assembler writes a temp KRZ, and **our `krz_parser` reads that temp** |

So on the single-preset path our parser never touches the original. It reads
their re-encoding of it. A misread by their reader is laundered through their
own assembler into something ours parses as well-formed — **the two readers
cannot disagree, because the second never sees what the first read.** Two
readers in series with a re-encoding between them corroborate nothing; they
only confirm the intermediate is self-consistent.

Their first description of this — reached by reading the dispatch function and
stopping — was "your parser reads every KRZ we convert". A correct reading of
one function and a wrong description of the system. Executing it took one
command.

**The same shape, stated for measurement:** two runs of one instrument rule out
noise, not bias. Bias is what the runs share. s3ked's individual fits sat at
r² 0.943–0.957 at *every* value for three runs and they read that consistency
as reassurance — flat mediocrity is bias, because noise varies and bias does
not.

### The four evidence boxes

The companion taxonomy, which exists because two boxes are not enough:

1. **Measured** — swept on hardware, with the range it was fitted over.
2. **Structurally claimed, and confirmed on a sibling the claim also covers** —
   e.g. the AKAI tuning fields, where one document sentence covers four fields
   and two of the four were measured against it.
3. **Unknown** — no law, no claim. Write a neutral default and say so.
4. **Measured to be inert** — actively established to do nothing, e.g. AKAI
   `STUNO`.

Box 4 is load-bearing rather than a curiosity: it is what stops box 2
collapsing back into "the neighbour looked similar". `STUNO` earns it because
its wording *differs* from the four fields that work — had it carried identical
wording and still done nothing, box 2 would be dead.

With only boxes 1 and 3, anything unmeasured gets treated as unknowable and
anything adjacent to a measurement gets quietly promoted. VinSamLib traced four
separate defects in one parser to exactly that missing category.

## §AKAIAUX — first read of the four auxiliary file types (2026-08-17)

Saving a volume on the S3000XL produced `TL1.T`, `EFFECTS FILE.X`,
`DRUM INPUTS.D` and `MULTI FILE.M3` unasked — **machine-authored examples of
all four types we carry but have never read.** No reference documents any of
them. Preserved at `/home/lentferj/temp/akai_resave_results/VOLUME_005/`.

### Solid: all four share the program/sample header convention

Decoded with our existing `akai_to_str`, no new charset work:

| file | size | byte 0 | name at `0x03` (12 chars) |
|---|---:|---:|---|
| `TL1.T` | 160 | `0x00` | `TL1` |
| `EFFECTS FILE.X` | 7312 | `0x02` | `EFFECTS FILE` |
| `DRUM INPUTS.D` | 162 | `0x01` | `DRUM INPUTS` |
| `MULTI FILE.M3` | 4096 | `0x00` | `MULTI FILE` |

**A 12-character AKAI-charset name at offset `0x03` is universal across every
block type this format has** — program common, keygroup, sample header, and now
all four auxiliary types. That is enough to name these files from their own
contents rather than from the directory entry, which is exactly the split that
made every sharp in a volume silent (§AKAINAME).

Byte 0 varies and is *not* simply the file type: `.T` and `.M3` both hold
`0x00`. Not enough evidence to say what it is; recorded, not interpreted.

### `DRUM INPUTS.D` — decoded, and NOT worth acting on

**What the file is for matters more than its layout: drum inputs are a
trigger-to-MIDI interface, not sample data.** `sens`, `trig`, `capture`,
`recover`, `on-time` and `V-curve` are analog envelope-detection parameters
converting a voltage spike from a drum pad into a MIDI note. Nothing this
converter reads or writes is affected by them, and no target format has an
equivalent. **Round-tripping `.D` byte-identically is the whole correct
behaviour** — it preserves the user's settings and asks nothing of us.

A configure-and-diff session was proposed for this and was the wrong use of
bench time. Recorded so it is not proposed again.

The layout came from a photograph of the `DRUM INPUT SETTINGS` page next to the
bytes, plus two confirmation reads over `RDDATA` (no save, no card movement).

**Header, `0x00`–`0x0f`:**

| offset | field | evidence |
|---|---|---|
| `0x00` | unit marker, `01` | recurs at `0x58` — a *unit* header, not a file header |
| `0x01`–`0x02` | `00 00` | unknown |
| `0x03`–`0x0e` | 12-char AKAI name | decoded |
| `0x0f` | **`chan`, GLOBAL, 0-based** | **observed**: `chan 1→9` moved this byte `0→8` |

**Records, 16 of 9 bytes at `0x10 + 9(n-1)`**, in two banks of eight
(units 1 and 2). Baseline `60 50 25 2 4 10 10 0 0`:

| byte | field | evidence |
|---:|---|---|
| 0 | `note`, raw MIDI number | **observed**: `C_3→C_1` moved it `60→36` |
| 1 | `sens` | *inferred* — 50 appears once in the record and once on screen |
| 2 | `trig` | *inferred* — same, 25 |
| 3 | `V-curve`, **0-based** | **observed**: `3→1` moved it `2→0` |
| 4 | `capture` (mS) | *inferred* — same, 4 |
| 5 | `recover` **or** `on-time` | **order undetermined** — both read 10 |
| 6 | the other of the two | " |
| 7 | unknown | `0` in all 16 records |
| 8 | unknown | `0` in all 16; also the byte truncated on record 16 |

So: **two fields observed directly, three inferred from a unique value match,
two identified as a pair but not separated, and two unknown.** Stated that way
because "seven of nine named" reads as stronger than the evidence is — bytes 5
and 6 both hold 10, so nothing yet distinguishes `recover` from `on-time`.

### Three things this got wrong before getting them right

**`chan` is not per-input.** The plan was to separate bytes 7 and 8 by moving
`chan`, since both were `0` and `chan: 1` stored 0-based is also `0`. The
elimination was sound and its premise was false: `chan` is global, in the
header, so *neither* byte is it and both are still open. The map came out with
one more unknown than the experiment was designed to leave.

That is worth more than the byte: **the page mixes scopes.** Editing `chan`
rewrites a header byte, not sixteen records. Irrelevant to a converter that
round-trips the file unchanged; the whole difference for anything that edits it.

**Per-file, and per-unit was positively ruled out** rather than merely not
supported: both `01 00 00` markers were byte-identical across the change, so the
channel is not stored per bank of eight either. One transmit channel for the
whole trigger interface, which fits the hardware — sixteen pads, one MIDI
output. Bracketed across four reads (`00` before, `00` after the note and
V-curve edits, `08` after `chan→9`, `08` again a minute later), so it is a
stable stored value and not a transient.

**0-based is now confirmed twice, independently.** `V-curve` moved two steps,
`chan` moved eight. Two fields, different ranges, same convention.

**`input: ALL` is a page scope selector, not a stored parameter.** With `input`
set to 1, exactly one record changed — and *nothing in the 162 bytes encodes
"input 1"*. An absence, which is not what either predicted branch looked for.
Whether `ALL` writes all sixteen at once is untested.

### Byte 7 or 8 of a record is a DIVISOR — the bytes that looked spare were the live ones

**Writing 42 and 77 into a record's last two bytes crashed the firmware.** Those
are exactly the two bytes the evidence had been pointing at as padding, and the
crash is a better answer than the map it interrupted.

Sequence, with the causality corrected after a first write-up got it wrong:

```
17:19:53  DDATA writes record 1 bytes 7,8 = 42, 77   (acked REPLY 0x16 [0])
          Jan checks DRUM INPUT SETTINGS  -> neither value visible
          Jan navigates to DRUM UNIT CONTROL, and onward
~17:22    Internal Error - divide overflow
17:23:03  a further probe script cannot even connect: the machine has
          already stopped answering RSTAT
```

```
Internal Error - divide overflow
Please tell Richard the operations that you performed to reach this state
Press F8 to continue
```

**`Press F8 to continue` does not work.** Every keypress re-raised the same
error — the structure is re-read on each UI action, so the division recurs. It
took a power cycle.

**Only bytes 7 and 8 were ever written.** A follow-up probe of `0x01`/`0x02`/
`0x59`/`0x5a` was *attempted and never sent* — the script died before
connecting, because the machine was already wedged. A first version of this
section blamed those four bytes and was reasoning from a write that does not
exist. Corrected here rather than quietly amended, because the wrong version
had a plausible mechanism and would have survived review.

**Isolated 2026-08-17: it is BYTE 7.** The first crash wrote 42 and 77 together
and so named neither. Jan spotted that and asked for byte 7 alone; the isolating
run wrote `0x17 = 42` with `0x18` left at `00` — exactly one byte differing from
a verified snapshot — and it crashed again.

Same value in each position was the point: 42-then-77 could not have separated
*position* from *value*, since a divide overflow depends on the divisor's
magnitude as much as on which field it is. With 42 in byte 7 alone producing the
assertion, byte 8 never needed testing.

An identity write immediately beforehand round-tripped byte-for-byte, **after**
the earlier assertion and power cycle, so the transport was demonstrably healthy
going in and the byte is responsible rather than a machine still upset from the
first crash. That staging was s3ked's and it is what makes this a single-variable
result.

So: **byte 7 of a drum record is a divisor in firmware, or feeds one.** Byte 8
remains unknown and untested — not shown to be padding, merely never probed.
`DRUM INPUT SETTINGS` never renders them — it exposes exactly seven per-input
parameters — but another drum page does, and divides by one of them. The crash
appeared as Jan moved *between* pages, which is what places it there.

**The reading this destroys is the one that was best supported.** Seven visible
parameters against a nine-byte record, and a write of 42/77 that changed nothing
on the page: two independent lines both saying *spare*. They were the live
bytes. A count of visible fields is not a count of stored fields, and a value
not shown on the page you are looking at is not a value the machine ignores.

**Both lines shared a blind spot — they were both looking at one page** — and
that is the case cross-checking cannot catch, because agreement between two
readings with the same blind spot is indistinguishable from confirmation. Two
sources agreeing raises confidence only when they could have failed
independently.

**And what falsified the wrong write-up was a timestamp in a log, not anyone's
judgement.** The account blaming `0x01`/`0x02`/`0x59`/`0x5a` had real offsets, a
plausible mechanism and a real crash to explain; it was checked, committed, and
wrong. It fell to the fact that the probe script's connection error was logged
at 17:23:03 and the values were therefore never sent. Worth more attention than
the divisor: the reasoning was sound and the premise was false, and only the
machine's own record of what happened could tell them apart.

**The structure is self-clearing, observed twice.** After each power cycle the
page read back at factory defaults — note 60, V-curve 2, byte 7 back to `00`.
Two different crashes, two different reboots, same result, which is the
difference between *what happened* and *what happens*: the first was a single
observation and would have been recorded as one.

A bad write here does not persist. That is the safer of the two possibilities
and is the whole reason this was a cheap experiment rather than an expensive
one — the worst case was always a power cycle.

### `accepted` vs `effective`, with a fourth corner

The write was **accepted** — `REPLY 0x16`, payload `[0]`, no error — on a route
that had already swallowed 15, 23 and 40 elsewhere. The firmware then divided by
it and halted.

`REPLY [0]` acknowledges that the **transfer** was well-formed. It is not a
statement that the machine can live with the contents. Every write route tested
here — `PHEADER` taking 15/23/40, `DDATA` taking 42/77 — acknowledges structure,
never meaning. So acceptance says nothing about **survivability**, not merely
nothing about effect.

**Operational rule for anything writing a whole AKAI structure:** there is no
byte-addressable route for drum data — `DDATA` sends all 162 bytes — so every
write is a whole-structure write, and one invented byte anywhere in it can wedge
the machine. Read, modify one field, write back. Never fill an unknown byte with
a probe value on a live machine unless a power cycle is acceptable.

### Where this stops

`.D` does not matter to this converter (above). The remaining questions — what
bytes 7 and 8 are, and which of 5/6 is `recover` — need panel time on a file we
only ever copy verbatim. **Deliberately not pursued.** If it is ever wanted, the
cheap form is one edit on a *different* input, say input 5: it would name the
leftover bytes if they are fields and simultaneously check that record *n* sits
at `0x10 + 9(n-1)` for a record other than the first — which every reading so
far has assumed and only record 1 has demonstrated.

Superseded detail, kept because the arithmetic was the clue:

**`unit: 1` explains the structure.** The two banks of eight are trigger
units 1 and 2, eight inputs each, so the recurring `01 00 00` is a *unit*
header rather than a file header — which is why it appears at `0x00` and again
at `0x58`.

Eight of nine fields from a screenshot. The two 0-based fields are the kind of
detail a configure-and-diff run would have produced expensively, and a picture
of the page produced for nothing. **Ask what the machine already displays
before designing an experiment to find it out.**

### Superseded: the earlier partial reading

From `0x10`, the unit `3c 32 19 02 04 0a 0a 00 00` repeats — eight times, then a
3-byte `01 00 00` marker at `0x58`, then the same unit again to the end. The
tail does not divide evenly, so **the record layout is not resolved** and the
obvious reading (16 inputs of 9 bytes) does not survive arithmetic: `0x5b` plus
eight records overruns the file by one byte.

Deliberately left there. Every field in it is the same value in every record,
because nothing on this machine was configured — a file that varies nowhere
cannot distinguish a per-record field from a constant, which is the same
"experiment with no information in it" shape as a zero-filled resave probe. **To
make this readable, set a few drum inputs to different values on the panel and
save again.** One volume, no card swap beyond the one already planned.

Written up as a procedure with the value choices and their reasoning:
`docs/re_procedures/akai_aux_files.md`, decoded by
`tests/re_banks/akai_aux_diff.py`.

`MULTI FILE.M3` is 4096 bytes and almost entirely zero past its header — an
empty multi, which is what an unconfigured machine would write, and equally
uninformative for the same reason.

## §KRZFILL — `id − base` is not position, and the failure is silent (2026-08-17)

**Measured.** A 19-entry K2000 boot macro was loaded and all 441 resident
programs matched their files' names **positionally, 441/441, verbatim** — no
normalisation, leading and trailing spaces and embedded quotes intact. That
proves the join. What it also proves is that the arithmetic everyone reaches
for first would have been wrong.

```
bank 200  KPOWFAV  200-237   SOARCFAV 238-266   KURVSFAV 267-269  SYNEXFAV 270-283
bank 300  LFOALFAV 300-374
bank 500  XPRGFV01 500-607        <- runs straight through the 599/600 boundary
bank 600  ANA1FAV  608-619        <- starts after the spill, NOT at its bank base
```

**`Fill` means "continue from the highest occupied id".** The bank number in a
macro entry is a *starting hint*, not a destination. So `position = id − base`
holds under Overwrite into an empty range and fails under Fill — here it would
have mis-joined **403 of 441 programs**, and mis-joined them *plausibly*: every
id lands on a real program with a real name, simply the wrong one.

**Join by name, per bank, in order.** It needs no arithmetic, needs nothing
known about Fill's semantics, and self-checks: names agreeing across a whole
bank proves the alignment, and names diverging is a finding rather than a silent
mis-join. Entries that *are* clean Overwrites then serve as a test of the
arithmetic instead of a dependency on it.

### A disagreement that resolves into the right answer for a different question

k2kremote's first census reported 278/441 and was nearly sent as a Fill anomaly.
It was a malformed expectation: eighteen files flattened into one global
sequence, ignoring that they load into different banks, so from index 38 the
comparison was bank 200's device ids against bank 300's file.

Two things caught it. The mismatch began at exactly **38**, the length of the
first file — too clean for a loader quirk. And the device name at the first
"mismatch" was the *next file's first program*, i.e. the chain continuing
correctly. **A disagreement that resolves into the correct answer for a
different question is a bug in the question**, and the tell is that the wrong
answer is too tidy.

The same run also produced a `list_bank` returning `(infos, done)` bound to one
name, so every bank reported "2 programs" — the arity of a tuple wearing the
costume of a count. Caught only because two banks reported 2 and the rest
raised.

## §NOISESRC — a taper is a de-click on a one-shot and a tremolo on a loop (2026-08-17)

**Defect, found by ear.** A generated white-noise measurement source had "a
rhythm to it" (Jan). It did: the generator faded 5 ms in and out to avoid a
loop-point click, and on a LOOPED sample a fade at both ends is not a de-click —
it is an amplitude dip at every seam.

```
tapered,   looped:  minimum 2 ms window  -23.1 dBFS
untapered, looped:  minimum               -9.8 dBFS      -> 13.3 dB, once per loop
```

**The taper was never needed.** Joining two random points is a step drawn from
the same distribution as the noise itself, indistinguishable from any other
adjacent pair. There is nothing to click. Removed.

### The verification that could not see it

The generator was verified against theory — white measured +3.0 dB/octave in
equal-width bands, pink flat within 0.5 dB — and that check **passes either
way**. Flat per Hz, averaged over the whole sample, is entirely compatible with
the amplitude pumping once a second. **The spectrum was checked and the fault
was in the envelope.** A source needs both verified, and they are different
measurements.

### Two numbers that agreed from opposite ends

s3ked first reported 71.2 dB of envelope spread from their recording. Our file
measured 0.3 dB at the generator, 0.3 dB in the encoded `.S3`, and 0.3 dB
tapered-and-looped — the dip is 0.5% of windows and cannot move a 5th
percentile. **The two did not reconcile, and saying so rather than going hunting
in the generator is what found it:** their analysis window began 200 ms before
the note sounded, and the silence was the spread. Measured strictly inside the
sound, their figure is **13.3 dB** — our file-side taper dip to the decimal.

Their own conclusion, worth more than the number: *look at the recording before
analysing it.* A coarse RMS-per-50 ms picture of the whole capture, four lines
of text, showed the pre-note silence instantly — and would have caught all three
of their failed analyses, each of which was an artefact of its own window.

### A control has to match the thing it controls

Their "≈2 dB envelope spread" control is correct for **white** and wrong for
**pink**, which inherently swings more. A professionally-generated pink
reference Jan supplied measures **5.7 dB** (48 kHz float, 15 s, rms −22.9 dBFS,
octave bands flat within 0.3 dB). Our pink measures 7.2 dB — fine. Judged
against the white control it would have looked broken, and "fixing" it would
have turned a correct source into a wrong one.

### Noise is the right source for a spectrum and the WRONG one for a timing

Recommended here for filter work on the reasoning that a broadband source makes
the transfer function directly readable — correct, and it is what let §116 agree
to 0.1% across two sources.

**It is the wrong instrument for envelope timing, and the same property is why.**
A noise source's amplitude fluctuates by design; an envelope sweep times a
threshold crossing on that amplitude. Every point is a race between the envelope
and the source's own variance.

Measured: with the loop fixed and the source sustaining cleanly, `ATTAK1`,
`DECAY1` and `RELSE1` all came back **non-monotonic**, none reaching r² 0.99,
against existing entries fitted at 0.99988, 0.99998 and 0.99956. **`DECAY1` ran
the wrong way** — time rising with the parameter where the recorded law has it
falling, since the field is a rate. All three were **withheld rather than
recorded**: a re-measurement contradicting a well-fitted law in *direction* is
not a correction, it is a measurement of something else.

**Fixing the source's silence did not make the sweeps valid.** Two independent
faults sat on the same measurement — a loop overrun that made the note stop, and
a source whose variance defeats threshold timing — and clearing the first felt
like clearing the road. **Unblocking is not validating.**

A sustained tone is what envelope timing wants. The ROM sawtooth measured a clean
onset and a power cycle restores it.

### A recurring shape: the document you reason from is not the document that decides

Three instances in one day, ours and k2kremote's, with the same structure — a
claim that is TRUE about a specific thing, widened into a false claim about a
general thing, with the widened version never checked against the source that
actually settles it.

| the true, narrow claim | the false, widened one | what settled it |
|---|---|---|
| our parser treats only playback type 2 as unlooped, so the writer must not emit 0 for a one-shot | therefore 0 is the right value for a looped sample | the hardware, which loops mode 0 only in the release |
| "the ?? regions are zero-filled by our writer" | true of the keygroup span, false of the common one, where 21 bytes carry measured values | reading the writer's actual output |
| (k2kremote §6) the name-edit cursor is not in any device reply | therefore the parameter cursor is not readable over MIDI | the message table — `0x17` name, `0x16` value, readable all along |

In every case the reasoning was sound and the premise was drawn from a document
that did not cover the case. **A round-trip argument settles a round trip and
says nothing about the machine.** The cost of the third was a render-to-PNG loop
built to read a cursor the device reports, and 48 wheel clicks that silently
changed the routing under measurement.

The cheap defence is naming which authority a claim rests on when it is written
down, so that widening it later is visibly a different claim.

### OPEN: a silent lead-in that scales with pitch, cause unknown

s3ked recorded the pre-correction sample and found silence before the sound
that **halves with each octave**:

```
note 36  2070 ms      note 60   610 ms
note 48  1190 ms      note 72   310 ms
```

Halving per octave means a fixed number of FRAMES — roughly 27000 — not a time
constant, so it is sample-domain and not an envelope. The whole capture shows
sound, decay, silent gap, repeat, about a quarter of each cycle silent.

**This does not reconcile with the file.** Measured on the image as written:
PCM 88200 frames, audible from frame 0 to 88199, and three independent length
fields agreeing — `u32 @0x1a` = 88200, `@0x22` = 88199, `@0x2c` = 88200. No
silence anywhere, and a 5 ms taper cannot produce 610 ms.

Two facts bound it. The recordings predate Jan loading the corrected volume, so
they may describe a file already replaced. And the mismatch itself is the useful
part: **saying two measurements do not reconcile is what found the last one**,
where a 71.2 dB figure turned out to be silence inside an analysis window.

**Candidate, unverified:** `locat` — sample header `0x18`, documented here as an
absolute RAM address with no known "none" value, which our writer sets to 0.
§AKAI_S3000_FORMAT lists it as the one remaining offset whose real-disc value we
have never matched. If the machine treats 0 as an address rather than as unset,
a playback offset is the shape of fault that would follow. Recorded as a
candidate and nothing more — the resave test showed the machine resolves pointer
fields on load, which argues against it.

**To settle it:** re-record the CORRECTED sample at two octaves. If the lead-in
is gone, the taper explained it after all. If it persists and still halves, it is
in the header, and `locat` is where to look first.

### Rig caveat, not chased

There is roughly **500 ms between note-on and audible sound** on that rig, where
its harness assumes 0.15 s. Harmless for a spectrum measured over the held
portion. **Anything measuring an ATTACK inherits it** — which is exactly what
the amp- and filter-envelope calibration work does.

## §AKAIVELFILT — a zone that fires and makes no sound (2026-08-17)

**Two faithful translations composed into something the source never did, and
nothing in our tooling could see it.**

Jan auditioned a converted K2000 cymbal program on the S3000XL: three velocity
zones, and zone 1 (velocities 0–63) produced nothing. The panel's zone-activity
bars showed it firing.

### What it was not

Everything checkable from the file was correct, and the obvious explanations
were wrong in a way worth recording:

| ruled out | evidence |
|---|---|
| a soft sample | zone 1 carries the **loudest** of the three: peak −4.2 dBFS vs −9.8 and −6.2 |
| leading silence | first sample over −40 dB at frame 1, peak at frame 40 |
| play range | `start 0`, `end 491985`, against 491986 frames |
| the two-name defect | directory, header and zone reference all read `CYMB.STICK 1` |
| per-zone level | `VLOUD` is 0 on all four zones |
| RAM exhaustion | 7.74 MB of samples against 31.75 MB free |
| level generally | **Jan's test**: zones 2/3 disabled, zone 1 loudness to +50 — against a measured 39.81 dB span — still silent |

### What it was

The **filter**. `FILFRQ 48`, translated faithfully from the source's own cutoff
of 0.2107 through a measured law, plus full-depth velocity tracking. At zone 1's
velocities the filter is nearly shut, and a cymbal is nothing *but* high
frequencies. The source is dark by design; the conversion takes it to inaudible.

**Neither half is a bug on its own.** The cutoff translation is right, and the
velocity tracking is what the source asked for.

### Root cause: the model collapses a RANGE into a scalar

The source does not carry "velocity→filter depth". It carries a **pair**:

```
Src2 = AttVel     MinDpt = 0 ct     MaxDpt = +10800 ct     base cutoff = 196 Hz
```

`MinDpt = 0` makes the modulation **unipolar** — velocity only ever *opens* the
filter, and 196 Hz is a floor the K2000 never goes below:

| velocity | K2000 cutoff | as an AKAI byte |
|---:|---:|---:|
| 0 | 196 Hz | 48 |
| 30 | 856 Hz | 69 |
| 64 | 4545 Hz | 99 |
| 127 | ~100 kHz (wide open) | 99 |

**`MODVFILT1` is bipolar about a velocity pivot.** We wrote `FILFRQ 48` — the
source's value at velocity *zero* — and then hung a bipolar depth on it. So
below the pivot our cutoff falls **below 196 Hz**, somewhere the source never
goes, and zone 1 lives entirely down there.

`velocity_to_filter` is a single scalar, so `(0, 10800)` and `(-5400, +5400)`
both normalise to the same number. The first only opens; the second closes as
much as it opens. **They are different patches and the model cannot tell them
apart.**

**This is the direct consequence of a decision recorded here this morning.**
§K2DSP left `MinDpt`/`DptCtl` deliberately unwired, reasoning that "MinDpt and
MaxDpt as a *pair* have nowhere to go in a model that carries one scalar depth."
That was true, and the missing pair is exactly what makes a converted program
silent. The gap was identified, the consequence was not.

### CORRECTION: the `25` is measured, and it is not the fault

An earlier version of this section said the `25` had "no rationale in the code",
and that was **wrong** — written after reading the assignment and not the
comment above it. `writers/akai_s3000_writer.py` records a hardware measurement
on an S3000XL (P019, one keygroup, one zone) at `FILFRQ 48`:

```
byte151  0 -> v30 -68.7 dBFS   v120 -45.2
byte151 12 -> v30 -72.8        v120 -23.1
byte151 25 -> v30 -73.4        v120 -22.0
byte151 50 -> v30 -72.8        v120 -22.1
```

The field **saturates**: past roughly 12–25 the sweep stops growing because the
quiet end has bottomed out, so ±50 is mostly unusable and 25 is full scale in
practice. `25` is calibrated to the reachable range rather than the declared
one, and doubling it does nothing — rows 25 and 50 are the same to 0.1 dB.

**And the same table contains the actual fault, unremarked at the time.** At
`byte151 = 0` — no velocity modulation whatever — `v30` already reads
**−68.7 dBFS**. The quiet end was inaudible *before* any modulation was applied.
So `MODVFILT1` never silenced anything: **`FILFRQ 48` did**, and the modulation
merely deepened it by 4 dB.

The measurement showed the symptom on 2026-08-16 and it was read as a property
of the field (saturation) rather than as a consequence of the base. It is both,
and only the base is ours to choose.

### What is actually wrong: the base is the floor of the sweep

We set `FILFRQ` from the source's cutoff at velocity **zero** — the bottom of a
unipolar sweep — and then modulate about it. For this program that is 196 Hz on
a cymbal, which has nothing to pass. The source spends almost none of its
velocity range there; at the pivot it is at 4.5 kHz.

**The writer's own comment already anticipates the fix:** *"the saturation point
moves with the base — at `FILFRQ` 72 it is ~25, at 48 it is ~12 — so this is
scaled to the range that is reachable rather than the range the field
declares."* Choose a better base and the reachable range grows, and the depth
calibration must move with it. The two are not independent.

**`MODVFILT1`'s depth in cents has still never been measured** — s3ked confirms
it is absent from `scales.py`; §109 gives only the ±50 clamp, and a clamp is a
range limit, not a scale. What is measured is its *audible* saturation at one
base, which is what `25` encodes.

What *is* measured is `FILFRQ` itself: `Hz = 6.4597 · exp(0.071 · FILFRQ)`,
r² 0.99984, so one octave is **9.76 FILFRQ units**. If a `MODVFILT1` unit is a
`FILFRQ` unit — a reasonable guess and still a guess:

```
our 25    ->  2.56 octaves
50        ->  5.12 octaves
source    ->  9 octaves (10800 ct) = 87.9 units
FILFRQ 0..99 end to end = 10.14 octaves
```

**A ±9-octave sweep cannot be expressed on this machine at all** — the whole
`FILFRQ` range is 10.14 octaves, so no centre leaves 88 units of headroom both
ways. So the honest model is a **documented lossy clamp** that reports what it
could not represent, not a scale factor.

**Do not simply double it.** More depth closes the filter *further* below the
pivot, which is exactly Jan's symptom — a "more faithful" constant would have
deepened the fault it was meant to fix, and the only test that catches that is a
listening test nobody would re-run after a constant change.

### The measurement, when it happens

Fix `FILFRQ` mid-range with headroom both ways, set `MODVFILT1` to a few values,
sweep velocity, track the corner by **resonance peak** rather than spectral
centroid (§108: the centroid misleads at both ends). That gives octaves per unit
directly, and `FILFRQ`'s fitted law converts to cents for free.

**Measure away from both ends of `FILFRQ`.** `scales.py` records an `ATTAK2`
case where `MODVFILT1` 18 vs 25 disagreed threefold and looked like
depth-dependence — it was the corner saturating at the top of the filter's own
range. Measured at an end, the ceiling gets measured instead of the field.

### Superseded framing: "are we writing half the authored depth"

```
K2000 VelTrk    -10800 .. +10800 cents
krz_parser      cents / 10800    ->  -1.0 .. +1.0
akai writer     _vf * 25         ->  -25 .. +25
MODVFILT1       accepts          ->  -50 .. +50
```

Full K2000 depth lands on half the AKAI field, and **the `25` has no rationale
in the code**. Raised by Jan. Blocked on measuring what `+50` spans in cents.

**Do not simply double it.** The field is bipolar about a velocity pivot: more
depth closes the filter *further* below the pivot, so a wrong guess makes soft
notes **more** inaudible — the exact symptom this started from. The first
instinct here was to double it, and it would have made the thing worse while
looking like a fix.

### Why no detector caught it

`silence_audit.py` exists for this class and finds nothing: no dangling
reference, no empty PCM, no velocity gap, no unreachable zone. Every check
passes because every *component* is correct. **A converted program can be
structurally perfect and still silent**, and the only thing that found it was a
person playing it.

## §AKAIVELZONE — overlapping velocity zones LAYER on the S3000XL (2026-08-17)

**Confirmed by ear on the machine: velocity zones inside one keygroup are not
exclusive.** Where two zones' ranges overlap, both sound.

The case that raised it was a converted K2000 program whose three voices are
authored to overlap:

```
zone1  vel  0-63    CYMB.STICK 1
zone2  vel 64-127   CYMB.STICK 2
zone3  vel 96-127   CYMB.STICK M     <- entirely inside zone 2's range
```

That overlap is **in the source** — the K2000 bank layers voices 2 and 3 above
velocity 96 deliberately — and our writer reproduces it as three zones in one
keygroup. The open question was whether the AKAI honours it or picks the first
matching zone, because if it picked one we would be silently dropping a layer:
every sample present, nothing dangling, no error anywhere, just a thinner sound
than the source. Same shape as the `-L`/`-R` defect in §AKAISTEREO.

It honours it. **So mapping overlapping source voices onto velocity zones within
a keygroup is correct**, and no separate-keygroup workaround is needed for the
overlapping case. The `>4 layers` spill into additional keygroups stays right
for its own reason — a keygroup holds only four zones.

Worth recording as a positive result rather than left as an assumption: the
behaviour was never verified before, and "the zones are all present in the file"
would not have detected the alternative.

### Incidental, from the same program: a keygroup count is not a layer count

The program is named `3-VEL...` and the panel shows **1 keygroup**, which reads
as wrong until you look at the zone page. Three velocity layers live *inside*
one keygroup, four to a keygroup. `KEYGROUPS: 1` is the correct display for a
three-way velocity split.

## §AKAISTEREO — the sampler does NOT pair `-L`/`-R` (2026-08-17, measured)

**Answered on the S3000XL. There is no `-L`/`-R` convention in the firmware.**

Real library discs name stereo halves with a `-L`/`-R` suffix (`PF BDF C 0-L`)
and there is no stereo flag on disk — the sample header's `0x88` "stereo
partner" is annotated *internal*, a RAM pointer. So the open question was
whether writing name-suffixed pairs would be enough and the machine would pair
them itself. It will not.

Measured by loading a program that references **only the left half**, with the
right half present on the disc but named by nothing:

```
after CLR        programs ['TEST PROGRAM'], samples []
load STPRSHORT   samples ['STPAIR-L']          -R did NOT arrive
after CLR        programs ['TEST PROGRAM'], samples []
load STPRLONG    samples ['STEREOLONG-L']      -R did NOT arrive
```

The `CLR` is load-bearing: memory came back with **zero** samples both times, so
"arrived" means arrived rather than "was already there". `Cursor Prog+Samps`
loads exactly what the program references and nothing more.

The two name forms **agree** here — directory and `RSLIST` both give
`STPAIR-L` — so the absence is real and not the header-versus-directory
artefact that made every sharp in a volume silent (§AKAINAME). That check is
the reason to ask for both forms rather than a yes/no.

`STEREOLONG-L` is **twelve characters exactly** and resolved correctly, so the
name-budget edge is fine in itself: a 10-character base plus the suffix fits.

### The consequence, and it is the silent kind

A program referencing only the left half **loads cleanly, reports no error, is
not dangling** — nothing it asked for is missing — and plays mono. There is no
signal anywhere in the chain: not on the machine, not in our `collect()`, not in
`silence_audit.py`, which looks for zones whose sample is absent.

So writing stereo means **emitting both references explicitly**, and nothing
downstream will catch a writer that emits one. Any future stereo support needs
its own check that both halves of a pair are referenced, because the failure
mode is a quiet halving of the material rather than an error.

Our writer currently mixes stereo down to mono, which is at least honest and is
unaffected by this. What this closes is the design question above it: the
name-pairing route works only if we reference both halves ourselves.

## §AKAIRESAVE — the `??` regions, answered on an S3000XL (2026-08-17)

**Result: our zero-fill is safe. The machine round-trips those bytes verbatim
and validates only one 13-byte field inside them.**

Method: `docs/re_procedures/akai_resave_diff.md`. Jan loaded volume `RESAVE`
with **LOAD ENTIRE VOLUME + CLR** and saved it back to `VOLUME 005` on the same
disc; the two were then byte-diffed. Three programs — a control written exactly
as we write today, and two whose `??` bytes were stamped with different known
patterns (`offset` and `offset ^ 0x55`).

### What the machine preserved

| span | stamped | kept | cleared |
|---|---:|---:|---:|
| program common `0x48`–`0xbf` | 120 | **107** | 13 |
| keygroup `0x96`–`0xbf` (×4) | 168 | **168** | 0 |

Nothing was rewritten to a third value, and **nothing moved** — the `MOVED`
case the two-pattern design existed to detect did not occur. Every unknown byte
came back exactly as written, including deliberately absurd values.

### The one field it does validate — and its boundary

The 13 contiguous bytes `0x4c`–`0x58`, the modulation-source matrix
(`MODSPAN1-3`, `MODSAMP1-2`, `MODSLFOT/L/D`, `MODSFILT1-3`, `MODSPITCH`,
`MODSAMP3`). Illegal source codes are **zeroed on load**. The two probes
disagreed here, and that disagreement is the finding rather than a problem —
`offset` stamping produces large values, `offset ^ 0x55` small ones:

```
values KEPT    : 0 1 2 3 4 5 6 7 13
values CLEARED : 24 25 26 27      (and 76-88 from the other probe)
```

So a legal source code includes **0–13**, and **≥24 is rejected**.

**Boundary closed the same day** (s3ked §114, `BOUND` volume): writing 14–23
into the matrix and reading back showed **14 KEPT, 15–23 CLEARED**. The break is
between 14 and 15. All three known-good controls (`5`) survived, which is what
makes it a *per-value* rule rather than a wholesale field clear — with thirteen
zeros and no controls the two readings are indistinguishable.

**Most of the remaining gap was already answered by the control file, in a
capture taken an hour earlier for a different purpose.** `RSCTRL` went through
the same validating load path carrying our `_PROGRAM_HW_DEFAULTS` in that exact
matrix:

```
off   4c 4d 4e 4f 50 51 52 53 54 55 56 57 58
ours   8  6 12  6  3  6  6  6  5  8 10 10  5
back   8  6 12  6  3  6  6  6  5  8 10 10  5
```

Every value survived, so **8, 10 and 12 are accepted**. Accepted set: **0–8, 10,
12, 13, 14**. Cleared: 15–23, 24–27, 76–88. **Only 9 and 11 are untested.**

A clean-0–14 reading still rests on two gaps and stays a prediction. But the
method point outlives the number: this project ran the `RSCTRL` diff, read
"0 differing bytes in the common block", and filed it as *nothing to see*. A
diff that finds nothing is a positive result — it says every value in it
survived — and we were an hour and a card write away from measuring something
we had already captured. **Check the captures you have before proposing a
measurement.**

### Two rejection regimes: the load path validates, the write path does not

s3ked then tested the *write* side (§114). `PHEADER`, the byte-offset SysEx
write, applies **no validation at all** — 15, 23 and even 40 are all accepted
and stick in RAM, including values the load path zeroes.

So one field has two regimes depending on how the value arrived. **A value
written over SysEx sits in RAM and appears to work; the same value written into
a volume is discarded when that volume loads.** Nothing on the machine says so.

For this converter that has a direct consequence: **the load path is the only
authority.** We cannot validate our output by poking a value into a live machine
and watching it stick — that tests the regime our files never travel through.
Our own `MODSFILT1 = 5` is confirmed *through the load path*, which is the one
that matters.

### Accepted, preserved, and effective are three different things

Third independent instance of the same distinction, and it is now a rule rather
than an observation:

| | what it shows | example |
|---|---|---|
| **accepted** | a write was not rejected | `K_FREQ` 22 against a documented 0–12 (s3ked §108) — and here it *was* also effective |
| **preserved** | the save path kept the byte | `0x49` holding 73 through a resave — which says nothing about the machine acting on it |
| **effective** | the machine's behaviour changed | requires measuring the sound or the display, not the bytes |

`MODVFILT1` clamped to ±50 (s3ked §109) is the fourth corner: accepted, and
silently altered. **A finding has to say which of the three it measured.**

**A single probe would have got this wrong in both directions.** The offset
probe alone shows all 13 cleared and reads as "the machine rebuilds this whole
field". The XOR probe alone shows 9 of 13 kept and reads as "it mostly does
not care". Only together do they show a *value*-dependent rule.

### What it does NOT validate, and one hypothesis

`0x49 B_PTCHD` kept **73** where the documented range is 0–12. **Kept is not
the same as effective**, and the distinction cuts both ways: surviving a resave
shows the *save path* preserved the byte, not that the machine acts on it.
s3ked's §108 is the mirror image — `K_FREQ` accepted 22 against a documented
0–12 and turned out to be genuinely effective — so neither "accepted" nor
"preserved" settles what a field does. `0x63`–`0x65`,
the **filter-2** modulation sources, kept values as bogus as the ones cleared
next door. `0x67`/`0x68`/`0x6d` (reserved) and `0x72` (`PFXSLEV`) also survived.

The filter-2 asymmetry has an obvious candidate explanation — **this machine has
no additional filter board fitted** (Jan ordered one 2026-08-17), so there may be
nothing to validate against. That is a hypothesis, not a finding; re-run when the
board arrives, and if `0x63`–`0x65` start being validated it is confirmed.

### Two internal pointers the machine rewrites, both of them ours to leave alone

**Block base, `0x01`–`0x02`.** We write `_RAM_BASE_PARA` 0x900c; the machine
relocated to 0x9054 in RAM and 0x9048 on this save. **The `0x0c` paragraph
stride is identical to ours** — our block-layout model is confirmed against
hardware, only the base is machine-assigned.

**Per-zone pointer, `zone_base + 0x16`** (`0x38`/`0x50`/`0x68`/`0x80`). We write
the `0xFFFF` null sentinel; the machine writes a live RAM address (`0x90b4`).
It rewrites **exactly one per USED zone** — the keygroups with 1/2/3/4 zones
came back with 2/4/6/8 differing bytes, and unused zones kept `0xFFFF`. That
scaling is what identifies it as a per-zone resolved pointer rather than a
format constant, and it is why the probe carried a spread of zone counts.

Both are re-resolved on load, so writing `0xFFFF` is correct and our files are
not made wrong by differing here.

### Consequences for the writer

- **Zero-filling `??` is safe.** Nothing there is required, and the machine
  imposes nothing.
- **But those bytes are carried.** They survive a load-and-save round trip
  untouched, so anything meaningful a real disc holds there we would drop by
  writing zeros. That is a reason to keep the `_PROGRAM_HW_DEFAULTS` copies, not
  to add more guesses.
- **Do not rely on the machine to correct anything we write** — outside
  `0x4c`–`0x58` it corrects nothing, not even a documented range violation.

### Incidental: machine-authored auxiliary files

Saving the volume produced `TL1.T`, `EFFECTS FILE.X`, `DRUM INPUTS.D` and
`MULTI FILE.M3` alongside the programs — **machine-written examples of all four
auxiliary types we carry but do not read.** They arrived free with this session
and are the reference material that TODO item was blocked on.

## §K2DSP — the K2000 F1 slot is a DSP block, not a filter (2026-08-16, measured)

### Addendum 2026-08-17 — the LFO pair, one depth scale, and a lesson about wiring

**A decoded field that reaches no model field is invisible.** Wiring `LFO1`
(source 114) and `LFO2` (116) took ten minutes; finding out it had not worked
took an hour. `krz_parser` decodes into a private mutable layer object and then
builds a `VoiceLayer` from it with an explicit keyword per field. Assigning
`cur.lfo1_to_filter` during the walk therefore creates an attribute on an object
nobody reads. Python says nothing, the suite passed at 412, and **0 of the 126
routings present in a 40-bank sample arrived**. It surfaced only because the
change was measured on the corpus afterwards instead of being trusted to a green
suite.

The fix needs BOTH halves — declare the field in the layer's `__init__` and pass
it to `VoiceLayer(...)`. `tests/test_krz_layer_fields_reach_the_model.py` pins
the wire rather than these two fields: every attribute the layer declares that
the model can hold must be forwarded, and every `cur.<name> =` in the walk must
be declared. Each half has its own negative control, both confirmed to fire.

Note the first version of that test passed vacuously — it located the layer
class as "the first class with an `__init__`", which matched something else
entirely, so it intersected an empty set. It is identified by content now
(the class declaring `filter_cutoff`). A structural test that cannot see its
subject is worse than no test, because it reports success.

**One depth scale, not two.** Slot 1 read `seg[6] / 127`, slot 2 read
`_k2_depth_cents(seg[9]) / 10800` — two scales for the same model field
depending on which slot a program happened to use. `seg[6]` carries the SAME
taper as `seg[9]`, exact on every measured page (62→3400ct, 46→1800, 42→1400,
17→45), so the `/127` form was reading a cents-scaled byte as a fraction. Both
slots now go through `_k2_depth_cents` normalised on 10800. **This also changes
`filter_env_amount`**, which had the same fault and is populated on ~15% of
voices.

That last one is the change to watch, and it is NOT confirmed. Across 827
ENV2→filter routings in a 40-bank sample the depth moves by **−0.114 on
average (mean 0.776 → 0.663), never upward: 750 shallower, 77 unchanged, 0
deeper**, worst case −0.287. So every KRZ program with a filter envelope
converts with a less pronounced sweep than it did yesterday. The reasoning says
this is a correction — the old `/127` reading has no basis and the cents taper
is measured against the machine's own pages — but the argument for it is
arithmetic, whereas the velocity fix that preceded it was settled by +25.3 dB on
hardware. A one-directional shift across nearly the whole corpus deserves the
same standard. **Play a KRZ-sourced filter-envelope program before this ships.**

**What is still discarded, and why it is not a parser question.** Full corpus,
201 banks, 15451 filter F1 slots, 14134 non-OFF routings: **4461 (31.6%) are
decoded correctly and dropped** for want of a model field.

| source | count | note |
|---|---:|---|
| `ON` | 1235 | constant-true — a STATIC corner offset |
| `MWheel` | 710 | performance controller |
| `Breath` | 549 | performance controller |
| `MPress` | 546 | performance controller |
| `Data` | 463 | performance controller |
| `PWheel` | 331 | performance controller |
| `ASR1` / `ENV3` | 258 | second envelope family |
| tail | 369 | FUN1-4, RandV1, KeyNum, unidentified 8/9/37/97/105/106/126 |

**`ON` should be split off from the rest.** It is always true, so its depth is
not modulation at all — it is a fixed offset applied to the filter corner, and
it folds into `filter_cutoff` with no new model field and no target-side
support. 1235 routings, 8.7% of the total, currently converting as an un-shifted
filter. That is a bounded, checkable change of exactly the shape already
validated twice here.

The performance controllers are a different problem: they need a real-time
modulation concept `VoiceLayer` does not have, and most output targets cannot
express one either. Deliberately left open rather than answered by inventing
four fields — the count is recorded so the decision can be sized.

**Still deliberately unwired:** the algorithm byte (a legality check for RE
work, not a parameter), and `DptCtl`/`MinDpt` — MinDpt and MaxDpt are a *pair*
describing a depth RANGE, and a model carrying one scalar depth has nowhere
honest to put them.


Three silent defects in `parsers/krz_parser.py`, all found in one evening by
chasing a single symptom: converted cymbals were inaudible on an S3000XL.

**1. An unknown block type defaulted to a bandpass.** `_K2_FILTER_TO_XPM.get(b0,
3)` turned any unrecognised `seg[0]` into a 2-pole bandpass with `seg[1]` as its
cutoff — **10.2% of F1 slots across 80 banks**. Not a dropped parameter, an
invented one. It never failed loudly because plain lowpass (code 2) is 85% of the
corpus and a fabricated bandpass sounds plausible. Now refuses and collects the
code.

**2. Non-filter blocks had their first byte read as a cutoff.** An F1 slot holds
any DSP block, and the unit follows the block: cents on frequency, semitones on
pitch, percent on width, dB on amplitude, a multiplier on the shaper. Verified on
the machine — `AMP(GAIN)` byte 56 reads `56dB`, `EVN(2P SHAPER)` byte −18 reads
`−18dB`, both 1:1 and neither in cents.

**3. The second modulation source was never read.** `seg[5]`/`seg[6]` are
Src1/Depth; `seg[10]`/`seg[9]` are Src2/MaxDpt and were ignored. One bank routes
everything through Src2 — Src1 OFF on all 21 programs — so a 196 Hz corner swept
open **nine octaves** by attack velocity converted as a static corner. That was
the audible bug.

### Field map, confirmed against the machine's display

```
seg[0] block type   seg[1] Coarse    seg[5] Src1     seg[6] Depth
seg[7] DptCtl       seg[8] MinDpt    seg[9] MaxDpt   seg[10] Src2
```

Algorithm number: **tag `0x40`, offset 29** — found by intersecting 15 programs
whose algorithm was read off the display, then validated on **1355 programs,
100%**. It gives a legality check: a decode producing a function the program's
algorithm cannot hold is wrong.

Depth scale for frequency blocks: `100 × (byte − 28)` over the linear middle
(floor 33), a 400-per-step tail at 125–127, compression toward zero below.
Negatives mirror on magnitude — that branch was an untested assumption until two
signed file values confirmed it.

`seg[0]` is a **global** namespace, not a per-algorithm index: algorithm 1 carries
codes 12 and 14, both outside its eight-option range, both on its legal list.

### What was NOT concluded, deliberately

Codes 8, 9 and 13 cluster on the algorithms that offer filters, and algorithm 2's
F1 is a lowpass — so "lowpass variants" was the obvious reading. They are
**PARA BASS, PARA TREBLE and PARAMETRIC EQ**. The clustering was evidence about
which algorithms admit these functions and said nothing about what they are.
F1 has no fixed chain position either: it is the first control input after pitch,
so it is a filter on algorithm 2 and a pitch function on 9 and 28.

### Validated against the machine, 574 program-x-layer rows

k2kremote dumped what the K2000's editor actually renders for every layer of 255
resident programs; `tests/re_banks/krz_machine_diff.py` joins that to our file
bytes and checks all three source slots, MaxDpt, MinDpt and the algorithm.
**581 joined rows, 581 agreeing, zero disagreements — every field, every layer:**

```
layer coverage   1:255  2:184  3:76  4:33  5:12  6:9  7:4  8:2  9-14:1 each
                 all complete, matching the device's own per-layer counts exactly

field coverage   algorithm 581/581   Src1 581/581   Src2 581/581   DptCtl 581/581
                 MaxDpt    417/581   MinDpt 417/581   <- FRQ slots only, by design
```

**The depth fields remain validated on a subset**, because they are only compared
on frequency slots — the unit differs per function type (cents on FRQ, semitones
on PCH, percent on WID, dB on AMP/EVN, a multiplier on AMT). Correct behaviour,
stated rather than left implicit, because the tool now reports coverage alongside
agreement.

**Getting there took two dumps and three bugs, none found by its own author.**
The first pass read the F1 page believing it was the ALG page, so the algorithm
was null on 322 of 577 rows — every layer but the first — and our diff *skipped*
nulls, so that column passed **by not running**. The second pass sized a soft-key
retry to four presses against a six-page cycle: fine for layers 1–2, 100% failure
at layer 3, silently taking layers 4–7 with it. And our own coverage counter,
built to catch a check that never ran, was blind to a row that never *arrived*
until layer coverage was added.

Same lesson each time: **a fix can carry a narrower version of the problem it
fixes**, and the narrowness is invisible from inside the fix.

That matters because every field had been verified on **layer 1 only**, and layer
1 is demonstrably unrepresentative: code 2 (plain lowpass) is 67% of layer-1 slots
against 89% of later ones, and the modulation fields are populated 50–60% of the
time in layer 1 against 12–16% after it. One program carries three different
functions across four layers.

Getting there took four rounds, and **every disagreement was a table gap rather
than a map error** — nine control-source codes and six depth nodes the machine
supplied by disagreeing with us. That is what a correct map looks like when it
meets new material.

One program is **excluded, not resolved**: bank C carries two different programs
both named `*Soft Trumpet` (ids 405 and 475, 2 layers/2P LOPASS and 1 layer/DBL
NOTCH). The K2000 enforces no name uniqueness, so a `(name, layer)` dict silently
keeps the last — exactly the collapse s3ked warned about and this tool did anyway
until three "disagreements" turned out to be one program overwriting another.

`(name, layer)` is therefore **not a valid join key**; the tool now joins on
`(id, layer)`, which resolves both programs instead of dropping either.

`position = id − bank_base`, **zero-based**, verified three ways: bank D's
programs are self-numbering (`ATMOSFEAR 00`…`50`) and 51 of 51 agree; our own
first-object identification of another bank matches at 300/301; and diffing the
machine's id sequence against the file's type-36 order gives **255 programs, 0
mismatches** across all four banks.

**It holds only because every load went into an EMPTY id range.** Append places
objects at the next free id, so loading into a partly-occupied range makes ids
skip around the existing objects and `id − base` silently stops meaning position.
Nothing announces that.

**Still open:** 4 codes (20, 23, 30, 31 now identified; 61 remains — 0.7% of
segments) refuse rather than decode. `0x51`'s byte 0 is `0` in 606 of 627 lowpass programs while the F2
handler only reads resonance when it sees 16, so **resonance is dropped on ~6% of
lowpass programs**. Not fixed: reading `0x51[1]` as resonance because it sits in
the right place is the same move that produced defect 1.

## §AKAIVFR — S3000XL velocity→filter is keygroup byte 151 (2026-08-16, measured)

The field is not where inherited S1000 documentation puts it. Offsets 9/10/11
(`V_FREQ`/`P_FREQ`/`E_FREQ`) are the **S1000** positions and are genuinely dead —
writing 0, 40 and 88 to offset 9 produced no change at two velocities. The live
fields are in the **S3000 extension** past the S1000's 150-byte keygroup:

```
151  Velocity  -> Filter Frequency
152  LFO2      -> Filter Frequency
153  Envelope2 -> Filter Frequency
```

Located because Jan set those three on the panel and the values appeared at
exactly those offsets. Per keygroup and independent (wrote KG1=40, KG2 unchanged);
clamps to ±50 (wrote 90, read back 50).

```
FILFRQ 48   byte151  0  ->  v30 −68.7 dBFS   v120 −45.2
            byte151 12  ->  v30 −72.8        v120 −23.1   loud end +22 dB
            byte151 25  ->  v30 −74.1        v120  −1.0
```

**It saturates.** Past ~12–25 the sweep stops growing because the quiet end has
bottomed out, so most of the ±50 the field accepts is unusable, and the
saturation point moves with the base — ~25 at `FILFRQ 72`, ~12 at 48.

An earlier reading at `FILFRQ 72` concluded that positive depth only darkens
quiet notes and never opens loud ones. That was an artefact of a base already
open enough to hit the ceiling. **Calibrate at the base the material uses.**

Applied end to end: 21 programs reconverted, 24 bytes pushed to RAM over SysEx
with no media, **+25.3 dB at v120, reproducible to 0.1 dB** over four interleaved
A/B pairs.

### Measurement traps paid for tonight

* Spectral centroid is meaningless at the noise floor — a closed filter reported
  "12429 Hz", which is the centroid of noise. Always read the peak beside it.
* A depth must be measured at **two velocities**. At one, a live field and a dead
  one look identical.
* A sweep measured as the last of an ascending series read 22 dB below the same
  configuration measured in isolation. The interleaved repeat settled it: the
  configuration is stable to 0.1 dB and the sweep's analysis window was at fault.
  Three explanations were proposed and wrong before the repeat was run.

## §E4BRATE2 — the rate-pitch formula confirmed on machine-authored material (2026-08-16)

### Addendum 2026-08-17 (later) — ANSWERED on the E4XT, in both directions

**`[58-59]` is authoritative for playback pitch. `[54-57]` drives the display.**
Both fields are load-bearing, for different things, and the writer must keep
emitting both.

eosed ran the mirror. Chain calibrated first against `CD3-PITCHCAL` (pure sines,
440/220/110 Hz): **−0.8, −0.8, −0.6 cents**. Sines also fixed the estimator —
harmonic-rich material had been making the autocorrelator lock an octave low.

Then both presets at MIDI 72:

```
PITCH_A  rate=27500, offset=0     -> 838.84 Hz  (+817.1 cents)   SHARP
         rate-authoritative predicts 523.25; offset-authoritative 839.1
PITCH_B  rate=44100, offset=-523  -> 523.25 Hz  (-0.0 cents)     in tune
         rate-authoritative predicts 839.1; offset-authoritative 523.25
```

Both followed the OFFSET and ignored the stored rate, **in opposite directions,
within half a cent of prediction**. The two 44100 controls read −0.9 and −0.7,
matching calibration. There is no reading of this where the rate field drives
pitch.

**But `[54-57]` is not inert, and this corrects our own wording.** Same PCM, same
frame count, different rate field, off Sample Manage:

```
PITCH_A S002:  2.00secs, left, 27500Hz      55001 / 27500 = 2.00 s
PITCH_B S002:  1.24secs, left, 44100Hz      55001 / 44100 = 1.247 s
```

The machine reads both and uses them for different purposes: **offset for what
you hear, rate for what it tells you.** Calling `[54-57]` "informational" was
right about pitch and wrong about the field. Writing it carelessly because pitch
does not depend on it would make the machine report a wrong duration and rate.

**Our writer is correct and needs no change.** `_sample_header` packs `[54-57]`
from `sample.sample_rate` and derives `[58-59]` from the same value, so the two
can never disagree. Verified across everything we have written — **22077 sample
headers in 681 E4B files**: every beyond-tolerance case is either a pre-fix file
or PITCH_A itself.

**This also validates `--single-cycle` rather than breaking it.** Single-cycle
bakes tuning into the sample rate, which would be inert if the machine ignored
the rate entirely — but the writer emits `f58` for every rate ≠ 44100, so the
machine plays at `44100·2^(f58/768)` = the stored rate, which is exactly what the
baked tuning assumes. Correct by construction; not separately measured.

**Stale artifacts, worth knowing before anyone reaches for a reference file:**
~1265 sample headers under `/home/lentferj/temp` are rate=27500 with offset=0 and
would play 817 cents sharp — the PITCH_A configuration, now measured. All date
**2026-06-07 to 2026-07-24**, at or before the fix. `B010_hw.E4B` and
`B011_hw.E4B` are in that set. Do not treat a pre-2026-07-24 E4B from temp as
reference material.

### Two bench traps from this run

**1. Program Change is page-dependent.** Honoured on the main preset page,
**IGNORED on Preset Manage / Sample Manage.** Jan caught it — he had to change
preset by hand before anything sounded. Two measurements taken while it was being
ignored came back identical to each other, which is last night's void result
reproduced one day after it was written up. The durable fix is to step presets
with the panel's own INC key and verify on the LCD, so selection and
proof-of-selection come from the same place.

**2. A voice's zone is not its root key.** PITCHCHK's two presets are both rooted
at MIDI 60 but zoned C3-C3 and C4-C4, so P2 is silent at 60 and only sounds at
72. That silence read as "this preset makes no sound" and nearly became a finding
about the machine rejecting inconsistent metadata. It was a key range. It did
turn out useful — the control answers only at 60 and the test only at 72, so
sound at both proves the preset changed without consulting the display at all.
Worth designing in deliberately on the next test bank.

### Addendum 2026-08-17 — a self-consistent test file cannot attribute a field

**PITCHCHK.E4B was recorded here as the instrument that would settle which field
the E4XT reads for pitch. It cannot, and both projects signed off on that before
anyone read the file.** eosed caught it; verified independently on this side:

```
PITCHCHK  C4_44100_C3   rate=44100  [58-59]=0     formula=0     AGREE
          C4_27500_C3   rate=27500  [58-59]=-523  formula=-523  AGREE
```

The two fields AGREE — which is our writer behaving correctly, and precisely why
the file answers nothing. If `[54-57]` and `[58-59]` encode the same intent, the
machine sounds identical whichever one it reads. That is the same property that
retired the disk route from this question in the first place; PITCHCHK has it
unchanged, and it was queued for a hardware session anyway.

**The general trap: a correctly-written file is the worst possible probe for
which field is authoritative.** Attribution needs the fields to CONTRADICT each
other, so the file must be deliberately malformed in one of two mirrored ways.

The discriminating pair (built by eosed, PCM verified byte-identical to PITCHCHK
on this side — same sha256 for both samples, only metadata differs):

```
PITCH_A   C4_R27500_OFF0   rate=27500  [58-59]=0     formula=-523  DISAGREE
PITCH_B   C4_R44100_OF523  rate=44100  [58-59]=-523  formula=0     DISAGREE
```

Identical audio in both: a C4 tone laid down at 27500 Hz, rooted MIDI 60, with a
44100 control sample alongside. Exactly one must come out **817.5 cents sharp**
(261.63 → 419.6 Hz, ratio 44100/27500 = 1.6036):

| if the machine reads | PITCH_A | PITCH_B |
|---|---|---|
| `[58-59]` (the offset) | **sharp** | in tune |
| `[54-57]` (the rate)   | in tune | **sharp** |

Either outcome names the field, and because it is a within-file comparison
against the control tone, the capture chain's own tuning cancels out.

**Keep PITCHCHK — just file it correctly.** It is a valid end-to-end check that
a file we wrote plays in tune through the whole chain. It is not field
attribution. Two different questions that a single file looked like it answered
at once.

Also on the card: `CD3-PITCHCAL`, three sine tones at 440/220/110 Hz rooted at
69/57/45, correct by construction — an absolute calibration for the capture
chain. **Run it first.** Last night's −14 cents could have been the chain or the
sample, with no way to tell them apart; PITCHCAL removes that ambiguity before
either bank is measured.

All three banks are on the Zulu SD in HD0.img (plain FAT32, written with mtools,
no existing file touched) as `B.020-PITCHCHK` / `B.021-PITCH_A` / `B.022-PITCH_B`,
appearing as banks on D0. Every preset name states its own metadata
(`A_R27500_OFF0`, `B_R44100_OF523`) so a loaded bank identifies itself on the
LCD — a direct response to last night's void result, which came from an A/B
where A and B were secretly the same thing. eosed's harness enforces the same
thing at runtime: it re-reads the LCD after each Program Change and refuses to
measure if the preset-name band did not change.


`round(768 * log2(rate / 44100))` at `E3S1[58:60]` was hardware-RE'd 2026-07-24
from the E4XT's own SrCnv output at six rates (§4.6 of `docs/E4B_FORMAT.md`). The
eosed project has now checked it against a machine-authored HD0 backup — material
neither project wrote — at **11 distinct rates, all within the documented ±2**.

**Sample size: 20 machine-written headers.** Not thousands. eosed corrected this
themselves after re-running with a realistic predicate: the first pass required
`start_loop == 92`, which admits only UNLOOPED samples, and 20 headers is what a
19 GiB disk actually yields. Twenty headers agreeing at eleven rates is real
evidence and it is not the large independent corpus an earlier draft of this
section implied.

```
 25000 -627/-629   27783 -510/-512   27831 -508/-510   28000 -503/-503
 31524 -370/-372   31984 -354/-356   32000 -354/-355   39062 -133/-134
 44050    0/  -1   44100    0/   0   48000  +94/ +94        (machine/formula)
```

**Nine of these are outside the original calibration set.** `48000 → +94` is the
valuable one: a positive offset, confirming the law holds *above* 44100, the
direction with the least evidence behind it since every symptom lived below.

Two asymmetries, recorded rather than smoothed: the machine writes `+1` at 44100
on 2 of 3 samples where we write exactly `0`, and `0` at 44050 where the formula
says `-1`. Both inside tolerance, both rounding toward zero. It does not change
the fix, but *"byte-identical to what the machine would have written"* is a
stronger claim than *"correct"* and we can only make the second.

**`[18-21]` is non-deterministic — confirmed from outside our corpus.** Every
sample on that disk has a non-zero value there, and at rates with more than one
sample the values differ (28000: 2 distinct; 32000: 2; 44100: 2 of 3). If it were
pitch, or any function of rate, samples at one rate would share it. Three of four
multi-sample rates disagree internally.

### The corpus-size trap eosed caught before reporting

The image holds **5311** `E3S1` tag occurrences and their scanner accepted **16**.
Rather than report a 99.7% rejection rate as either a bug or a triumph, they
dumped the rejected sites: they are 32-byte DIRECTORY records
(`tag|size|offset|index|name(16)|flags`) with incrementing indices — the disk's
native EOS layout, not the E4B file layout. So the corpus is 16 real headers, not
5311.

*"Confirmed at 5311 samples"* would have sounded far better and been false, and
nothing on our side could have caught it. The tag count is not the corpus.

**And 20 headers on a 19 GiB disk holding ~5300 samples is itself a finding about
the format**, flagged as inference rather than fact: EOS native storage evidently
does NOT lay samples down as E4B-style headers, so those 20 are almost certainly
`.E4B` files sitting on the FAT volume. Anyone writing a native EOS disk parser
should know it cannot be *"find the E3S1 tags"* — which is what one would try
first.

## §AKAINAME — one sample, one name, and the cached directory that hid it (2026-08-16)

**The defect.** `build_akai_volume` sanitised the AKAI *directory entry* with
`safe_filename`, a HOST filesystem helper. It turned `#` into `_`; `_` is absent
from the AKAI charset (`0123456789 A-Z#+-.`) so the encoder wrote a **space**.
One sample, two names: header `5BSHRDF#1`, directory `5BSHRDF 1`.

**Why every check passed anyway.** Zones reference the HEADER form, so a
disc-side audit resolved 100% and a zone-by-zone diff against RAM came back
70/70 identical. Neither asks whether the named samples are **resident**. A
volume can have every zone byte-identical and still be silent.

**What it cost on hardware.** `ALL PROGS+SAMPLES` resolves references by the
**directory** name; `ENTIRE VOLUME` loads every file and takes the resident name
from the **header**. Under the first, 15 samples never loaded and every sharp in
the volume was silent — reported by ear, then wrongly retracted on the strength
of the passing checks.

**Fixed** by writing the AKAI name into both fields. `.` needs no escaping either
(the reader derives the extension from the file-TYPE byte, never by splitting the
string) — an interim `.`→`-` attempt simply moved the defect, 15 sharps becoming
9 dots.

**Confirmed on hardware 2026-08-16:** directory re-read shows 15 entries
containing `#`; after `ALL PROGS+SAMPLES`, 6 programs and **30 samples resident,
15 containing `#`**, with one dangling reference belonging to `clear_memory`'s own
`TEST PROGRAM`. **`#` in a directory entry loads** — charset index 37, previously
inferred and now demonstrated.

### The cached directory, which nearly produced the opposite conclusion

A card swapped while the sampler is POWERED leaves a stale directory in place:

```
select_volume(0) alone            30 samples,  0 containing '#'   <- the OLD card
select_drive(0) then volume(0)    30 samples, 15 containing '#'   <- the card in the drive
```

`select_drive` forces a re-read; `select_volume` does not. Reading the machine
after a swap without forcing the re-read describes the previous card, and
everything downstream — browsers, loads, our own audits — inherits that.

This produced a reading that looked exactly like *"the loader rejects `#`, the fix
is wrong"*, on the strength of which a correct writer would have been rewritten.
What stopped it was refusing to conclude from a machine state whose provenance had
not been established, and s3ked reading their own data rather than sending the
verdict line their script had printed.


## §KRZF3 — a filter in slot F3, and the two ways of being wrong about it (2026-08-17)

**Status: landed (`6c37a1e`), gated, NOT hardware-confirmed.**

### What was wrong the first time

The first attempt (`eb0a5b1`, reverted `7d36d1b`) read tag `0x52` as a filter
whenever it looked like one. It invented filters in programs whose panel shows
none. The reason is structural, and it is worth stating exactly because the
loose version of it is also wrong:

**The four HOB segments are a fixed-size array.** All four are written for every
layer of every algorithm — measured over 1442 layers and 25 distinct algorithms
in the local corpus, no exceptions. So the presence of a `0x52` segment carries
no information at all about the algorithm.

But the third slot is **not absent** on the algorithms where this misfired.
k2kremote read `AMP MOD OSC` in slot 3 of an algorithm-17 program, off the
panel. The slot exists and holds a real function. What is absent is any
**filter** among the functions that slot can select — algorithm 17 and 18 offer
only `SHAPE MOD OSC` / `AMP MOD OSC` / `NONE` there.

So the fault was decoding a *present* slot's code through `_K2_FILTER_TO_XPM`,
a table measured against **F1's** option list and meaningless against a list
that shares none of its entries. Same failure as the invented bandpass, one
level up: a value test cannot separate lists it was never measured against.

### The gate

`_ALG_DSP_FUNCTIONS` in `parsers/krz_parser.py` counts each algorithm's
addressable `Fn` slots, from the manual's algorithm chapter (`26 DSP Algs.pdf`,
extracted to `/home/lentferj/temp/k2k_full/algorithm_slots_from_manual.json`).
`0x52` is read only at three or more.

Validated 9/9 against per-layer panel observations, both directions — six
programs whose panel shows a filter in that slot, three whose panel shows none.
Per **layer**: an earlier attempt keyed on the program's first layer scored
5/11 and 7/11, because a program can carry different algorithms per layer.

Corpus effect: **20 layers gain a filter, 48 refused.** The reverted version
would have invented more than twice as many as it recovered.

### Independent confirmation of the extraction

The manual table was cross-checked against k2kremote's panel instrument:

- Four independent alg-17 panel reads (two functions × two slots, from two
  different programs) all land inside the manual's per-slot lists.
- Their alg-10 wheel sweep of 17 selectable functions is **set-identical** to
  the manual's alg-10 slot-2 list.
- Their sweep order is the manual's order **rotated by 9** — the wheel is a
  cycle with no origin, and the rotation is just wherever the borrowed edit
  buffer happened to sit. **The manual supplies the origin the panel cannot.**

That last point matters operationally: an `(algorithm, slot) → ordered function
list` table does not need to be swept on the instrument. It is already written
down, ordered, and anchored.

### Still open

1. **The 20 recovered layers are unheard.** No listen test has been run.
2. **No slot→code table exists.** `_K2_FILTER_TO_XPM` was measured against F1
   alone (581/581). An F3 code is decoded through a table with no authority
   there, so a wrong filter **type** remains possible where a wrong **presence**
   no longer is. Codes are not a plain index into the manual's slot list —
   algorithm 10 slot 2 shows codes `{18,19,23,24,25,27}` against a 17-entry
   list — so the anchoring still needs doing.
3. **Resonance is deliberately not read for an F3 filter.** F2 (`0x51`) is the
   second control input of F1, so the F3 equivalent would be F4 at `0x53`, never
   observed carrying one. Inferring it from the pattern is the move that
   produced the invented bandpass.
4. **`0x51`'s identity is not fully settled** — second control input of F1, or
   the second DSP function? Both readings survive the current evidence and they
   are not the same claim.

### §KRZF3 addendum — the codes ARE global, and our F1 table has errors (2026-08-17)

**This corrects `88e5cf0`, whose title claims a block code is slot-relative.
It is not. I asserted that to k2kremote as well.**

k2kremote supplied 40 anchor rows (`/home/lentferj/temp/k2k_full/slot_anchors.jsonl`)
— per layer, the panel's function in every slot. Joined against our byte values
by program id and algorithm, all 40 rows:

**1. Panel `Fn` = manual slot `n+1`.** Confirmed, not assumed: `0x50` code 2 →
`2POLE LOWPASS` ×3, code 54 → `4POLE HIPASS W/SEP` ×4, code 27 → `SAW` ×7,
code 23 → `SINE` ×7 — all under the `n+1` reading, none under `n`. So `0x52` is
F3 is manual **slot 4**, not slot 3.

**2. The codes are a GLOBAL namespace.** The same code names the same function
under different tags:

    code 16 = HIPASS   at 0x50 and 0x51        code 17 = ALPASS at 0x50 and 0x52
    code 15 = LOPASS   at 0x51 and 0x52        18 GAIN, 19 SHAPER, 22 PWM,
                                               23 SINE at both 0x50 and 0x51

The earlier "byte 15 is a filter under one algorithm and a shaper under another"
was **never a slot-relative code**. It was a stale byte in a slot the algorithm
does not have: every contradictory reading (`0x52` code 15 → `AMP` ×4, code 40 →
`PANNER`/`AMP`, `0x51` code 0 → `AMP`/`AMP U`/`PANNER`) sits exactly where the
gate already refuses. So the gate is confirmed a second way, and the reasoning
that justified it was wrong. Right answer, wrong argument.

**3. `_K2_FILTER_TO_XPM` is not fully correct, though it was "581/581" on F1.**
Against the panel:

| code | panel says | we say | verdict |
|---|---|---|---|
| 2 | `2POLE LOWPASS` ×3 | Low 2 | correct |
| 3 | `BANDPASS FILT` ×1 | Band 2 | correct |
| 54 | `4POLE HIPASS W/SEP` ×4 | High 4 | correct |
| 62 | `NONE` ×1 | NONE | correct |
| **17** | **`ALPASS` ×6** | **Model1 LP+dist** | **WRONG — an allpass converted as a distorted lowpass** |
| **16** | **`HIPASS` ×8** | **unknown, refused** | **missing — a real filter dropped** |
| **73** | **`LP2RES` ×1** | **unknown, refused** | **missing** |

The 581/581 figure measured *self-consistency of the read*, not agreement with
the machine. It could not have caught either row: a code we map to the wrong
filter and a code we refuse both round-trip perfectly.

**Not fixed tonight, deliberately.** Code 16 and 73 are safe additions (a
dropped filter becomes a read one). Code 17 is a **design question for Jan**:
an allpass does not attenuate, so mapping it to any lowpass is wrong in kind,
and XPM has no allpass — `parsers/talsmpl_parser.py` already faces this and
falls back to LP24. Options are that fallback, or `filter_type = 0` (no filter),
which is arguably the honest reading. Behaviour change on real conversions;
not a 23:00 decision.

### §KRZF3 lead — the codes index one MASTER block list (2026-08-17, unproven)

Not acted on, recorded because it is cheap to test and would finish the table.

Against the manual's algorithm-10 slot-2 list, the observed codes are a fixed
offset into it — until they aren't, in a specific way:

    idx 0..5   LOPASS HIPASS ALPASS GAIN SHAPER DIST     code = idx + 15
    idx 6..13  PWM SINE LF SIN SW+SHP SAW+ SAW ... SQUARE code = idx + 16

The obvious reading is that my extraction dropped an option at index 6. **It did
not** — the PDF column reads `DIST` directly followed by `PWM`, verified in the
raw text.

So the gap at code **21** is a block that exists in the global namespace but is
**not offered in this slot**. Which gives the actual structure:

> Codes index a single MASTER list of every DSP block. Each `(algorithm, slot)`
> option list is a **subsequence** of that master list, in master order.

That is consistent with everything measured: codes are global (§KRZF3 addendum),
the panel wheel presents each slot's own subset in a fixed cyclic order, and the
manual prints that same subset in that same order.

**If true, the complete code table is derivable offline** — no instrument time.
Merge all 31 algorithms' slot lists into one consistent total order (each is a
subsequence, so this is a topological sort), then anchor it with the codes
already known. Known anchors: 15 LOPASS, 16 HIPASS, 17 ALPASS, 18 GAIN,
19 SHAPER, 20 DIST, 22 PWM, 23 SINE, 24 LF SIN, 25 SW+SHP, 26 SAW+, 27 SAW,
29 SQUARE — which also predicts 28 = `LF SAW`, untested.

**How it could fail, and the check to run first:** if the slot lists are *not*
all subsequences of one order, the topological sort will find a cycle, and that
cycle is the disproof. Run that before trusting any code it produces — a sort
that silently picks an order among incomparable elements would manufacture a
table indistinguishable from a real one, which is this project's recurring
failure mode rather than a new one.

### §KRZF3 provenance — what tonight's numbers actually rest on (2026-08-17)

Written because s3ked retracted §120 and part of §119 on 2026-08-17 after their
provenance filter let a sibling project's writer output through as third-party:
their "74 of 74" pattern was one tool's habit, and their headline corpus result
turned out to rest on material that was ~96% our own output — the round-trip
mistake, made in the section written to warn about it. The same check therefore
belongs on our own figures rather than only in their write-up.

**Checked, and clean.** Every corpus number in §KRZF3 comes from
`/home/lentferj/temp/k2k_full/objects.jsonl` — 441 program objects read off the
K2000R **by k2kremote over SysEx**, not produced by any writer of ours. Audited
directly: zero of the 441 names match our generated-material patterns (`B.NNN-`
bank prefixes, `RSPROBE`, `RSTONE`, `NSWHITE`, `NSPINK`, `VF NEW`/`VF OLD`,
probe/test markers). The panel anchors are k2kremote's own display reads of the
same device. **No path exists by which our output could have entered either.**

**But state the size honestly: it is six banks, not a corpus.** Ids 200–739
across banks 2–7, 441 objects, 721 layers reaching the filter branch. That is
one machine's RAM at one moment, holding whatever was loaded that evening. So:

- The **filter-table corrections** (16, 73, allpass) do not depend on it at all
  — they rest on the panel anchors, i.e. on the machine's own display.
- The **counts** — 64 LP2RES, 11 HIPASS, 17 allpasses, 20 F3 gains, 48 refusals
  — are "over these six banks", and should be quoted that way rather than as a
  rate. A different six banks would give different numbers.
- The **fixed-array fact** (all four HOB segments always written, 1442 layers,
  25 algorithms) is the one figure whose strength genuinely comes from breadth,
  and 25 of 31 algorithms is real breadth even from six banks.

The lesson worth carrying is s3ked's, stated better than the retraction does:
**the errors that got through were the ones that made the data look
better-behaved, not worse.** A regularity holding 74 of 74 across supposedly
many vendors, and a table at 581/581, are the same shape — too clean, and clean
for a reason that is not the one assumed.

## §RIGHTNUMBER — when the measurement survives and the explanation does not (2026-08-18)

**A named failure shape, because three of us hit it in one night and none of us
recognised it as the same thing until s3ked proposed naming it.**

The shape: **a correct result, published with a wrong reason.** It is the
dangerous one precisely because the number at the end is right, so nobody
re-checks the sentence next to it — and the sentence is what the next decision
gets built on.

### The four instances

| whose | correct result | wrong explanation |
|---|---|---|
| mpc2emu | the F3 gate refuses tag `0x52` on algorithms 17/18 — 9/9 against the panel | "the slot does not exist". It does exist and holds `AMP MOD OSC`; what is absent is a *filter* in its option list |
| mpc2emu | `0x56`–`0x85` is not modellable from the corpus | "unused loop records contain residue". They contain structure — the reasoning was as unfounded as the claim it corrected |
| s3ked | remote save cannot be fired over SysEx — swept, with a positive control | "because volume names cannot be transmitted". No name was ever needed: the machine offers the next slot and auto-names `VOLnnn` |
| k2kremote | the two SysEx encodings decode to the same bytes | "the encodings genuinely differ" — an artefact of a bit-alignment bug in their own library, used to argue for a hypothesis |

### Why review does not catch it

Every other failure we hunt announces itself in the *output*: an implausibly
uniform count, an implausibly large value, an implausibly large proportion, a
change with zero effect. **This one has no tell in the output at all**, because
the output is correct. It is visible only by re-deriving the explanation
independently of the result — which nobody does when the result already agrees
with expectation.

Three of the four above were caught by **another reader**, not by their author,
and the fourth by its author only after an unrelated fact landed beside it.

### MEASURED: a plausible address changes nothing

`SDADDR` and `SDZERO` are identical discs but for this field. Captured minutes
apart in one session:

```
            prg  names      SBADD   peak dBFS   period   sounding
SDZERO       94  LOOP 3S    36888       -71.7      --     SILENT
             95  LOOP 4S    36900        -8.5   4.000     its OWN
             96  LOOP 5S    36912        -7.9   5.000     its OWN
             97  LOOP 7S    36924        -8.0   7.001     its OWN
SDADDR       90  LOOP 3S    36888       -72.8      --     SILENT
             91  LOOP 4S    36900        -8.2   4.000     its OWN
             92  LOOP 5S    36912        -7.9   5.000     its OWN
             93  LOOP 7S    36924        -8.0   7.001     its OWN
```

Same periods to three decimals, same SBADD, same silence at slot 0. **The field
is written by every factory sample and read by nothing we can observe.** Closed
as cosmetic; the prediction above — that trusting a stored zero could not explain
the observations — held.

`0x10` (0 for a one-shot, 1 for a loop, where we write 1 unconditionally) is
still worth correcting for correctness against the machine's own example, and is
equally unlikely to change behaviour.

### What to do about it (superseded by the measurement above)

- **State the mechanism as a separate claim from the result**, so it can be
  attacked separately. "Refuses on algorithms 17/18" and "because the slot does
  not exist" are two assertions, and only the first was measured.
- **When a result is right, ask what else the explanation predicts.** "The slot
  does not exist" predicts nothing is displayed there; the panel showed
  `AMP MOD OSC`, and that check cost one question.
- **Prefer "measured, mechanism unknown" to a plausible mechanism.** An honest
  gap invites the next person to look. A wrong reason closes the question.

Related: §KRZF3 addendum (the slot-relative claim, retracted), §KRZF3 provenance.

## §WRONGLAYER — a positive control on the transport is not one on the measurement (2026-08-18)

**s3ked's, from a false negative that survived a control they were pleased with.**
Recorded here because the same mistake is available in the E4XT plan and was
nearly made there.

They concluded a sampler could not be made to save over SysEx. They had a
positive control: the identical raw poke, on a different page, loaded an item —
559 kB consumed, sample resident. Frames were arriving, the route was live, so
the negative looked like the machine's answer.

**It was a control on the wire, not on the experiment.** "Frames arrive" says
nothing about whether the detector could observe a save. Three independent
errors were stacked underneath it: the wrong register was written (they believed
four neighbouring registers were mirrors of one; the save was two along), aimed
at the wrong destination (an empty slot, where a working trigger also shows
nothing), while watching the wrong variable (a directory, when the register
under test loads into RAM). Remote save exists. So does remote rename.

### The distinction, stated so it is usable

- **Transport control:** proves the message reached the device. Answers *is my
  cable plugged in*.
- **Measurement control:** proves that IF the effect occurred, this apparatus
  would see it. Answers *would I know*.

A negative result needs the second. The first is worth having and is not
evidence about the finding.

**The cheapest form of a measurement control is to produce the effect by a route
already known to work, and check the detector fires.** For a save: save from the
panel, then run the detector unchanged. If it does not see that, it cannot see
anything.

### Where this already applies to us

`docs/re_procedures/e4xt_parity_plan.md`, Phase 1b. The staged walk aborts if
the display fails to change between steps — which detects a dead panel route,
i.e. transport. **It does not detect a crop sitting on the wrong field**, and
eosed said as much: with the byte varying per preset, a wrong-but-changing field
sails through. So the walk needs a measurement control too: navigate to a page
whose content is known, and confirm the crop reports it.

Related: §RIGHTNUMBER. Both are failures with no tell in the output — that one
publishes a right answer with a wrong reason, this one publishes a wrong answer
with a control that looked valid.

### The technique that broke it open, worth stealing

They found it by **writing every register its own current value**. State-neutral
by construction, but any write-triggered action still fires, because the write
*is* the trigger. It separates "this register acts" from "this value is valid" —
which every value sweep conflates, ours included.

### §WRONGLAYER, part 2 — a fault in the RECORD cannot be found by repeating the measurement

**s3ked's, 2026-08-18, and the remedy is different enough that it nearly got
filed under the wrong heading.**

They reported the AKAI multi file-type byte as `0x6d`. It is `0xed`. But **the
byte was read correctly and written down wrongly** — their table's first column
carried raw values for five rows and the masked value for the sixth. Invisible
in the other five, because the high bit is clear there and raw equals masked.

The consequence is the point: **re-reading the byte off the machine — the
obvious way to check a byte — would have confirmed `0xed` every time and never
once looked at the table that said `0x6d`.** Repeating a measurement validates
the measurement. It cannot see a transcription that happened after it.

So the remedy is not a better control on the instrument. It is:

> **Where an artefact exists — an extracted file, a saved image, a rendered
> name — check the claim against IT, not against the reasoning that produced
> it.**

How this one was actually caught, and the credit is smaller than it looks:
their six bytes were run through our `ftype_to_ext`, `0x6d` produced `'M'`, and
we had already extracted a file called `MULTI FILE.M3` from their machine's own
save. **The claim collided with an artefact lying around on disk.** No analysis
of their reasoning at any point — reasoning agrees with itself, and a file does
not care what either party thinks.

Cheapest check in this project so far, and it cost nothing but a file that
already existed. Worth running *before* proposing a new measurement.

**Tally for the night: three corrections between two projects, each caught by
the other party, none by review — and the review each of us did of our own work
caught none of them.**

## §AKAIAUX-DECODED — the drum-input and multi files, read off the disk (2026-08-18)

**Both formats are decoded.** s3ked configured the pages over SysEx (writable
`DDATA` / `MULTIDATA`, unattended) and saved two type-0 volumes; the diff below
ran against the card on 2026-08-18.

### `DRUM INPUTS.D` — 16 records of 9 bytes from `0x10`

```
14 changed bytes, 5 runs, stride 9 (x3 support)
record 0 (input 1)  +0x00..+0x08  36 51 26 3 5 11 12 7 9
record 1..5         +0x00 only    38 41 47 55 99
```

**Every one of the nine values is stored verbatim.** Not scaled, not packed,
not offset — the byte on disk equals the number set on the panel-equivalent
register. That is the whole field map for the record, and the two positions
that read `0` in every previous capture (`+0x07`, `+0x08`) are decoded here for
the first time because the procedure required input 1 to set *every* field.

Layout confirmed: stride 9 from `0x10`, second bank at `0x5b`, and input 16 one
byte short at `0x9a` — the "16 records of 9 from `0x10` overruns the file by
one byte" arithmetic, seen from the disk side and matching the RAM side.

### `MULTI FILE.M3` — 1024-byte header, then 16 parts of 192

```
1024 + 16 x 192 = 4096   exactly the file size
part 0 base 0x0400   part 1 base 0x04c0   stride 192 (measured, x2)
```

The stride was **measured, not assumed**: `VOSCL` was planted at three parts
with distinct values (83 / 62 / 88) and read back at `0x506`, `0x5c6`, `0x686`
— differences of exactly 192, twice.

**Every field sits at the same intra-part offset on disk as in RAM**, verified
for all thirteen:

```
PRNAME +3   PMCHAN +16  PRIORT +18  PLAYLO +19  PLAYHI +20  OUTPUT +22
STEREO +23  PANPOS +24  VOSCL  +70  TRANSPOSE +75  PFXCHAN +113
PFXSLEV +114  PTUNOCM +115
```

**So the disk stores the same representation as RAM.** That was the open
question the diff existed to answer, and `PANPOS` = `243` and `PTUNOCM` = `219`
appear on disk byte-for-byte as they were written. It does **not** settle what
`243` MEANS — those bytes were produced by s3ked's encoder, which assumes two's
complement, so the semantic label is still interpretation. **That needs the
front panel** (see §AKAIAUX, the five-second look).

### A tool bug this exposed

`akai_aux_diff.py` inferred the stride as **1**, not 9. Its heuristic took the
commonest gap between consecutive changed offsets, and input 1's nine adjacent
fields produced nine gaps of 1 that outvoted the four gaps of 9. **The
docstring already warned that adjacent changes inside one record are not
strides** — the warning was correct and the code shipped the wrong number
anyway, because a caveat in prose does not stop a number being read.

Fixed to collapse each run of adjacent changed bytes to a single point first,
so the gaps measured are between *records* rather than between bytes. Re-run:
stride 9 with support 3. It now also refuses to name a stride at all when no
gap repeats, rather than reporting the first one it sees.

Related: §RIGHTNUMBER — the tool's *output* was wrong here, which is the easy
case. The dangerous version is the one where the number is right.

## §PROSEGUARD — a caveat in a docstring does not defend against a printed number (2026-08-18)

**s3ked's generalisation of a bug in our own tool, and it is a different failure
from §RIGHTNUMBER or §WRONGLAYER: this one is about tool design.**

`akai_aux_diff.py` infers a record stride from the spacing of changed bytes. Its
docstring said, correctly and in advance:

> two changed fields inside one record produce small gaps that are not strides
> at all, and this cannot tell those apart on its own

Run against the first real specimen it printed **`taking 1 as the stride`** and
laid out fourteen changes as fourteen one-byte records. The true stride was 9.
The warning was right, was written before the failure, sat directly above the
code — and the wrong number shipped anyway.

**Because the reader believes the figure, not the paragraph above it.** A
printed number carries the authority of a computation; a docstring carries the
authority of a note. When they disagree, the number wins, and it wins silently.

### The same shape elsewhere

`_MISC_LOAD_TYPE = (6,7,8,9)` in s3ked's bridge, described in a comment as "the
load type, mirrored". They were four independent action registers — load, delete
from memory, save-create, save-overwrite. Anything iterating that tuple, which
is the obvious thing to do with a tuple of mirrors, would have deleted resident
data and then written to a disk. **A `[:1]` slice was the only thing between
that comment and a user's medium.** The comment was doing safety work and the
code was not acting on it.

### The rule

**If a caveat is load-bearing, it must be in the control flow, not in the
prose.** Concretely:

- Refuse to answer when the data cannot support the answer. Our fix makes the
  differ print *"No gap repeats, so the stride is NOT established"* rather than
  naming the first gap it sees.
- Prefer a structure that cannot express the bad case over a comment warning
  about it — s3ked's own-value sweep detects *"this register acts"* and cannot
  claim *"this value is valid"*, because it never varies the value.
- eosed's soft-key template library ships **empty**, so deny-by-default is the
  initial state rather than a documented policy someone must implement.

All three are the same move: a tool declining to answer a question its data
cannot answer.

### The part worth keeping

The specimen designed to make *fields* findable is what made the *bug* findable.
"Set every field of one record" is precisely the input that breaks a naive
stride inference, so the procedure's most demanding clause was load-bearing
twice over — once for the format, once for the tool reading it.

### §AKAIAUX-DECODED addendum — the panel readings, 2026-08-18 (Jan)

**Read off the S3000XL's own display for multi part #2 (our part index 1), the
part carrying the planted values. Five confirmations and two corrections.**

```
panel            planted                verdict
name ABCDEF...   PRNAME ABCDEFGHIJKL    match
Pan L13          PANPOS(@24)  = 243     match -- 243 IS -13
Lev 61           "STEREO"(@23) = 61     match, but the field is LEVEL
Send 71          PFXSLEV(@114) = 71     match
FX RV4           PFXCHAN(@113) = 4      match
Ch 16            PMCHAN(@16)  = 22      MISMATCH -- clamped
```

**1. The signed encoding is TWO'S COMPLEMENT, settled.** `243` displays as
`L13`, and only two's complement gives −13 (offset-by-50 gives 193,
sign-magnitude 115). So `PTUNOCM` = `219` is −37 as intended, and all three
signed fields are settled by one reading. This was the open half that no amount
of file diffing could reach — the disk faithfully stored s3ked's encoder's
assumption, and a medium that copies bytes cannot validate their meaning.
**Part #1, unconfigured, reads `Pan MID` for byte 0** — consistent with 0 =
centre.

**2. `@23` is LEVEL, not "stereo".** It was carried in the parameter table as
`STEREO` with range 0..99; the panel calls it `Lev` and shows our 61. A field
name that was never checked against the machine.

**3. `PMCHAN` is clamped: we stored 22, the panel shows `Ch 16`.** The value was
accepted and stored verbatim — s3ked confirmed the readback — so *the register
holds 22 and the machine does not honour it.* This is the `K_FREQ 0..12` shape
that s3ked flagged in their own `params.py`, now demonstrated rather than
suspected: **a declared range describing what a register will store, not what
the machine will act on.** Storage is not acceptance.

**4. CORRECTION TO THIS SECTION'S OWN CLAIM ABOUT THE DRUM FILE.** Above it says
every one of the nine drum fields is "stored verbatim". That is true and it is
narrower than it reads. Jan reports **no drum parameter displays as 7 or 9** —
the values we planted at `+0x07` and `+0x08`. So:

- **file byte == register value** — measured, and what "verbatim" meant here
- **register value == displayed parameter** — NOT established, and false for at
  least those two fields

The two positions are located, and their scale or meaning is not. §RIGHTNUMBER
in miniature: the sentence was accurate about what was measured and invites a
broader reading. Photograph pending.

**5. The machine HAS an `ENTIRE VOLUME` delete** (s3ked's open item 3). So a
per-volume delete exists and the remote hunt was looking for something real
rather than something absent. Photograph pending.

### §AKAIAUX-DECODED addendum 2 — the drum record, from a photograph (2026-08-18)

Jan photographed `DRUM INPUT SETTINGS` for input 1 with the planted values live
on the panel. **Six of the nine bytes are named:**

```
+0x00  36  ->  note      displayed C_1     MIDI 36 renders as C_1 here
+0x01  51  ->  sens      verbatim
+0x02  26  ->  trig      verbatim
+0x03   3  ->  V-curve   displayed 4 -- stored 0-based, displayed 1-based
+0x04   5  ->  capture   verbatim, unit mS
+0x05  11  ->  recover   verbatim, unit mS
+0x06  12  ->  ?
+0x07   7  ->  ?         nothing on the page reads 7
+0x08   9  ->  ?         nothing on the page reads 9
```

Unattributed on the display: `on-time 804mS`, `chan 1`, `unit 1`, `input ALL`.
`on-time` was tried as a u16 across every adjacent byte pair — 1804, 3079, 2311,
1801 — and **none gives 804**, so it is scaled, table-indexed, or not in those
bytes.

**This corrects the parent section's "stored verbatim".** That claim was true of
what was measured — *file byte equals register value* — and false as anyone
would naturally read it. Six display verbatim, one is off by one, three do not
appear on the page at all. Three distinct relationships were collapsed into one
word. The measurement stands; the sentence was doing more work than the evidence.

`MIDI 36 -> C_1` is worth keeping on its own: the same octave-convention
question that cost time on the K2000 (`24-108` against a panel saying `C0-C_7`),
answered for this machine from its own display.

## §AKAIDELETE — the delete-type enum, and why it must never be swept (2026-08-18)

Photographed from the DELETE page. **The type is a five-value enum:**

```
0  cursor item only
1  all programs only
2  all samples
3  ENTIRE VOLUME
4  OPERATING SYSTEM
```

**Value 4 deletes the operating system FILE on the selected medium** — not the
sampler's boot code.

**CORRECTED 2026-08-18, and the overstatement was mine.** I first wrote this as
"not the disc, not a volume — the machine's firmware", and s3ked carried it into
their TODO as erasing the firmware of an irreplaceable instrument. Jan queried
it and was right.

The evidence was already in our own code: `LOAD_TYPES[6] = "Operating System"`.
**An OS that can be LOADED FROM a medium is a file on that medium**, so the
symmetric delete removes that file. `bridge.py` has guarded load type 6 behind
an explicit flag all along for exactly that reason. The `BOOT SYSTEM#` volume's
nine directory entries contain no OS-typed file either, so the OS sits outside
the volume directory.

**A warning is a claim, and being cautious does not exempt it from having to be
true.** An overstated hazard spends the same credibility as an overstated
finding, and the next warning is read in its light. This is the purest instance
of that on this project: the measurement was right, the alarm was not, and the
alarm is what would have been remembered.

**The conclusion is unchanged at the corrected size.** Value 3, `ENTIRE
VOLUME`, destroys a volume outright, and value 4 can strip a boot medium's OS,
recoverable only if an OS file exists elsewhere. Neither is a power-cycle
recovery, and one of them is one integer from the other.

s3ked's untried next step for the remote delete hunt was *"byte[8]/byte[9] at
values other than 0 and 1"*. A five-value type field adjacent to a delete action
is exactly the shape that hunt expected to find, and **an unbounded sweep of it
reaches value 4.** Warned before they resumed; recorded here so the reason
survives the conversation.

This is §105's "a reachable page does not imply a reachable softkey" with much
sharper teeth: an inert-looking value is not merely inert. It is also the
strongest possible case for the asymmetry argument (§KRZF3-era): a moderate
convenience against an unrecoverable outcome is the wrong trade, and here the
unrecoverable outcome is one integer away from the useful one.

**Two structural results better than the enum itself.** `ENTIRE VOLUME` exists,
so the capability is real and only the remote route is missing — that reframes
the hunt from *does it exist* to *where is it*. And **the trigger is a separate
key**: type selection, then `GO` on F8, unlike the load and save registers where
the write IS the operation. If the remote form mirrors the panel there is an
arm-then-fire pair, and **the arming half is safe to hunt while the firing half
is not** — a way to make progress without ever writing a value that could act.

Page also confirms that
that its softkeys are `SAVE VOLS REN DEL SCSI FORM` with `GO` on F8 — **`FORM`
(format) on F6**, with the trigger a separate key.

## §E4BFTYPE — `vpar[58]` is a GROUPED code, not a sequential index (2026-08-18)

**Measured on the E4XT by eosed, reading `E4_VOICE_FTYPE` (id 82) for all 98
presets of `F58ANCHOR` and joining to the expectation table.**

```
file byte -> runtime   our table's name
0x00 -> 1   4-Pole Lowpass      0x20 -> 8   Swept EQ 1-oct
0x02 -> 2   6-Pole Lowpass      0x21 -> 9   Swept EQ 2->1
0x08 -> 3   HP 2nd Order        0x22 -> 10  Swept EQ 3->1
0x09 -> 4   HP 4th Order        0x40 -> 11  Phaser 1
0x10 -> 5   BP 2nd Order        0x41 -> 12  Phaser 2
0x11 -> 6   BP 4th Order        0x42 -> 13  Bat Phaser
0x12 -> 7   Contrary Bandpass   0x48 -> 14  Flanger Lite
                                0x50 -> 15  Vocal Ah-Ay-Ee
80 of 98 bytes -> runtime 0     0x51 -> 16  Vocal Oo-Ah
```

**The high nibble is the filter FAMILY, the low nibble selects within it** —
`0x0x` lowpass, `0x08/09` highpass, `0x1x` bandpass, `0x2x` swept EQ, `0x4x`
phaser/flanger, `0x5x` vocal. A writer treating this as a sequential index emits
a valid-looking byte from an unrelated family, or an invalid one that silently
renders as 2-Pole Lowpass.

### Our writer is CLEAN — checked, not assumed

Every byte `_XPM_FILTER_TYPE` can emit, against the confirmed-valid set:

```
emit: 0x00 0x01 0x02 0x08 0x09 0x10 0x11 0x20 0x50 0x51
outside the valid set:  0x01 only, for XPM types 1, 2 and 29
```

**And `0x01` is harmless either way**, which is worth spelling out rather than
leaving as an open worry. It reads back runtime 0, and eosed correctly notes the
experiment cannot distinguish *"0x01 is legitimately runtime 0"* from *"0x01 is
rejected"*. But runtime 0 and a rejected byte **both render as 2-Pole Lowpass**,
and XPM types 1, 2 and 29 all intend a 2-pole lowpass. The outcome is correct
down either branch, so the ambiguity does not reach the output.

### The real finding is a coverage gap, not a defect

**Seven confirmed-valid filters our writer can never emit:**

```
0x12  Contrary Bandpass       0x41  Phaser 2
0x21  Swept EQ 2->1 octave    0x42  Bat Phaser
0x22  Swept EQ 3->1 octave    0x48  Flanger Lite
0x40  Phaser 1
```

No source format we read maps onto them today, so this is a "what could we
offer" item rather than a bug — but it is the first hard list of what the E4XT
has and we do not use.

### B11's original question: answered YES

**`id == list position` HOLDS for the runtime parameter** — runtime 1..16 land on
our table's names in order. Anchored to the display at one point: preset P000
reads runtime 1 and the Filter page shows `4 Pole Low-pass`. The surprise was one
layer below the question, in the file byte rather than the runtime id.

### The display half: 16 of 16, and `id == list position` is now OBSERVED

Swept on 16 presets rather than 98 — the other 82 read runtime 0 and could teach
nothing. Result: **14 exact, 2 abbreviated, 0 disagreements.**

```
0x00  4-Pole Lowpass        -> 4 Pole Low-pass       0x40  Phaser 1
0x02  6-Pole Lowpass        -> 6 Pole Low-pass       0x41  Phaser 2
0x08  2nd Order Highpass    -> 2nd Order High-pass   0x42  Bat-Phaser
0x09  4th Order Highpass    -> 4th Order High-pass   0x48  Flanger Lite
0x10  2nd Order Bandpass    -> 2nd Order Band-pass   0x50  Vocal Ah-Ay-Ee
0x11  4th Order Bandpass    -> 4th Order Band-pass   0x51  Vocal Oo-Ah
0x12  Contrary Bandpass     -> Contrary Band-pass
0x20  Swept EQ, 1-octave    -> Swept EQ 1 octave
0x21  Swept EQ, 2->1-octave -> Swept EQ 2->1 oct     ABBREVIATED
0x22  Swept EQ, 3->1-octave -> Swept EQ 3->1 oct     ABBREVIATED
```

**Fifteen of those sixteen rows were previously ordering, not observation.** They
are observation now, and the sweep cost 16 screenshots.

### Two defects in OUR joiner, found by running it on the real data

It reported **7 disagreements on a table that is completely correct**, where
eosed's independent join reported none. Both faults were ours:

1. **`_norm` replaced separators with a SPACE instead of deleting them**, so
   `Lowpass` and `Low-pass` normalised differently — and the E4XT hyphenates
   exactly where the manual does not (`Low-pass`, `High-pass`, `Band-pass`,
   `Bat-Phaser`). The function written to prevent false mismatches was
   generating them.
2. **A hardcoded `_BELIEVED` table disagreed with the capture's own
   `our_table_name` column** — ours said `Highpass 2nd Order`, the manual says
   `2nd Order Highpass`. A second copy of a fact, trusted over the first. The
   joiner now prefers the column and keeps the table only as a fallback.

After both fixes it reproduces eosed's result exactly: 14 / 2 / 0. **Two
independent implementations agreeing is worth more than either.**

3. A third, found in the same run: with both control rows blank the tool printed
   `controls agree: ''` — **a reassuring line for a check that never ran.** It
   now says so loudly. Same shape as §PROSEGUARD, in our own output.

### Route correction, for anyone repeating this

`EditVce` returns to the group's **last-viewed** page, and paging **clamps**
rather than wrapping. So "two `PAGE_NEXT` from the landing page" is correct
exactly once; after that it lands wherever the previous preset left off. The
route is **`F6`, rewind to the clamp (`PAGE_PREV` ×4, a no-op past the start),
then forward exactly two.** eosed's first attempt captured all sixteen on
`Filter Envelope` and their title check passed it — the crop included a
per-voice field whose content varied per preset, so distinctness came from the
preset rather than the page. **A control measuring the wrong region, giving a
confident pass.** Now split: page title must be IDENTICAL across captures, name
band is the measurement.

### The morph filters: all four found, and `0x7F` CRASHES THE MACHINE

**Hardware-confirmed 2026-08-18 on the `0x60-0xFF` sweep, which the crash ended
early.** Six captures survived and they include everything that mattered:

```
0x60  rt 17  "Dual EQ Morph"       exact
0x61  rt 18  "2EQ+Lowpass Morp"    TRUNCATED at 16 chars
0x62  rt 19  "2EQMorph+Exprssn"    TRUNCATED, spaces DROPPED
0x68  rt 20  "Peak/Shelf Morph"    exact
0x63  rt  0  "2 Pole Low-pass"     the zero-reading control
0x7F  rt 21  ""                    BLANK -- no name at all
```

**`0x7F` is not clamped like other invalid bytes.** Most are: they read runtime 0
and render `2 Pole Low-pass`, exactly as the format notes say. `0x7F` passes
through as **runtime 21**, past the end of the implemented table, the machine has
no name for it, and rendering that page kills the firmware:

```
FATAL ERROR: Gen Trap error
PC:107FFA50  Eaddr:107FFA50  SR:007F
D0:00000018  D1:00000001  D2:0000007F      <- D2 holds the byte
```

Only a power cycle clears it. **This is the second Gen Trap this project has
recorded and the first with a trigger and a register dump** — the earlier one,
from an unattended amp-envelope run, was never root-caused.

**Our exposure, checked rather than assumed:**

- **Writer: none.** `write_e4b` can only emit from `_XPM_FILTER_TYPE`, which does
  not contain `0x7F`.
- **Round-trip: safe.** Reading a file carrying `0x7F` gives an unknown byte →
  XPM 0 → written back as `0x00`. We launder it rather than propagate it.
- **`build_iso`: REAL, and now guarded.** It takes `.E4B` files as they are —
  that is the point of it, and banks have deliberately been carried unmodified
  so two machines play identical bytes. A third-party or corrupt file could put
  a crasher on a disc we then hand to the hardware. It now scans every voice's
  `vpar[58]` and warns loudly. **Warns, does not refuse** — our own RE banks
  sweep the byte space on purpose and `F58MORPH` carries `0x7F` by design.

**`0x68` was missing from `_E4B_TO_XPM_FILTER_TYPE`** and is now added; `0x60`,
`0x61`, `0x62` were already there and are confirmed correct.

**The abbreviation bucket earned itself properly here.** `2EQ+Lowpass Morp` and
`2EQMorph+Exprssn` are real 16-character truncations, and the second one **drops
the spaces the prose has** — so a naive prefix compare fails on it too.
Normalisation has to *delete* separators, not merely compare prefixes, which is
exactly the bug found and fixed in our joiner a day earlier. It would have bitten
here for real.

**`0x01` remains open, and now we know why this could not close it.** The zero
control worked — `0x63` displays `2 Pole Low-pass` — but clamped-invalid and
genuine-2-pole both land on runtime 0 and render identically. Only a byte *known*
to be 2-pole by construction can separate them.

### Two things still open

- **The four morphing filters (runtime 17-20) were not reached.** `F58ANCHOR`
  sweeps `0x00-0x5F`; their codes must be above that. A second bank covering
  `0x60-0xFF` would close it — and those four are exactly the ones whose names
  differ most between the manual's prose and its screen illustrations, so the
  abbreviation handling in `e4xt_display_join.py` gets its real test there.
- **Runtime 0 may be unreachable or indistinguishable from invalid.** Worth
  knowing before anyone writes a byte intending 2-Pole Lowpass and believes the
  readback.

### Free, for §ENVSPAN

The `Amp Envelope` and `Filter Envelope` pages label their columns
**`seg | rate | level%`**. **The machine's own word for the field is `rate`.**
That is the machine's claim rather than a measurement of behaviour — it does not
establish that the byte *behaves* as a slew rate — but it is a strong prior for
the CD6 experiment, and it cost nothing.

## §POWEROFF — every symptom fitted, and nobody enumerated the cheapest cause (2026-08-18)

**The E4XT was reported hung for the third time. It was switched off.**

Between two sessions we produced, and each of these is a real observation:

```
eoscli memory     -> timeout, three consecutive attempts
eoscli inquire    -> timeout
panel 51h         -> no screen
passive listen    -> silent bus, no second client
our processes     -> none running
```

then an ALSA topology audit, an interface-sharing hypothesis involving another
project's known-harmful polling heartbeat, and an `a2jmidid` bridge as a
secondary suspect. A caveat was correctly attached about mid-boot SCSI scanning.

**Every one of those is equally consistent with "the power is off", and neither
of us enumerated it.**

### Why, because "be more careful" is not the lesson

**Both of us were reasoning FORWARD from a known failure mode.** eosed had seen
this signature twice; I had a candidate I had just watched die and was looking
for what was *different* this time. Neither asked **what is the cheapest
hypothesis that explains all of this** — and "off" explains every symptom with
no mechanism at all, no interaction, and no prior.

A forward search from a remembered failure enumerates causes *similar to the one
you remember*. It does not enumerate causes that are simpler than any failure,
because those were never in the reference class.

### The shape it shares with the rest of this week

§WRONGLAYER from a third direction. There, a positive control validated the
transport rather than the experiment. Here, **every measurement was of a system
that was not running**, and each returned exactly what the interesting
hypothesis predicted. The measurements were not wrong; they were of nothing.

### The fix, and it is cheaper than any of the above

**A liveness check before any diagnostic sequence, distinguishing NO ANSWER from
NO DEVICE.** A timeout on the first command should ask *is it on* before it asks
*why did it hang*. eosed's harness already refuses to start when a modal is open
— this is the same instinct one step earlier in the chain.

### What survives

**Occurrences 1 and 2 are real** — the machine was demonstrably working, then
stopped — so the count is two, not three. And the id-6 elimination stands
untouched: that test was clean, the prediction was recorded before the outcome
was known, and this changes nothing about it.

## §FECLAMP — a real difference, measured with a ruler that had hit its ceiling (2026-08-18)

**CONFIRM's filter-env pair came back contradicting the prediction, and the
contradiction is in the instrument.**

Prediction: `FE NEW` (depth 0.663) sweeps LESS than `FE OLD` (0.776).
Measured centroid excursion: **OLD 212 Hz, NEW 246 Hz** — NEW sweeps *more*,
with a run-to-run spread of 1–2 Hz. Seventeen times the noise, so the difference
is real.

### The tell is in the trajectories

```
FE OLD  541 522 525 545 585 685 670 520    peak 708
FE NEW  513 531 548 586 673 706 586 477    peak 709
```

**The peaks are 1 Hz apart across two different envelope depths.** That cannot be
right: we write `filter_env_amount × 127` as the Cord-05 depth, so OLD (byte 99)
should peak *higher* than NEW (byte 84), not identically.

**Something clamps the top — and once it does, excursion INVERTS with depth.**
Our filter env sustains at 0.2, so the resting cutoff sits at
`base + amount × 0.2`: a deeper envelope raises the **floor** while the peak
cannot move, and the measured excursion shrinks. That is exactly the observed
ordering.

### Which ceiling — not established, and not guessed

The tidy story is that the centroid saturates against the source's own
bandwidth. **It does not survive its own arithmetic**: the test tone (110 Hz,
harmonics 1..13, 1/h amplitudes) has an unfiltered centroid of ~450 Hz, and the
measured peaks are ~708. Resonance at 0.4 is probably lifting it. Candidates
remain the source content, the filter's own frequency ceiling, or the centroid
going insensitive once the corner sits above most of the energy.

### This is §RULER's family

*A ruler that saturates against its source is measuring the source.* Recorded
after s3ked's `FILFRQ` law read 20–30 % high from a centroid, biased in **slope**
rather than offset. Their warning was explicit: any filter-frequency law derived
from a spectral summary is probably biased the same way. **We checked and
declared ourselves structurally clear because `corner_frequency()` measures a
−3 dB point — then built a listen test on a centroid anyway.**

### RESOLVED — the floor carried the signal, and the correction is NOT backwards

**eosed tested the clamp model against their existing captures. No new hardware
run was needed, because the model made a prediction the data could already
answer.** Floor taken from the settled sustain phase rather than the release
tail, three repeats each:

```
FE OLD  depth 0.776   peak 707.5 (spread 1.2)   floor 617.1 (spread 1.9)
FE NEW  depth 0.663   peak 709.5 (spread 0.6)   floor 554.3 (spread 2.5)
```

**Peaks differ by 2.0 Hz. Floors differ by 62.8 Hz.** The top is pinned; the
bottom carries everything — and **the floors order exactly as depth predicts**,
the deeper envelope resting *higher* at `base + amount × sustain`.

**The clamp is now quantified rather than inferred.** Solving the floor
difference for the modulation range gives ~2779 Hz per unit depth; that same
range predicts a **314 Hz** peak difference at `env = 1.0`.

```
predicted peak movement   314 Hz
actual peak movement        2 Hz      short by a factor of 157
```

**The ceiling swallowed 314 Hz of movement and returned 2.**

**So the −0.114 correction is NOT backwards.** "FE NEW sweeps more" was excursion
inverting under a pinned ceiling. The 34 Hz was real, the direction check was
worth running, and only the reading of it as *depth* was wrong.

**And the floor is a usable ruler now**: unclamped, 63 Hz of travel for 0.113 of
depth, ~2 Hz noise — signal-to-noise around 30, on captures that already exist.

### What this does and does not establish

- **Establishes:** the −0.114 shift reaches the audio, decisively. The
  "indistinguishable, therefore arithmetic housekeeping" branch is **closed**,
  and the KRZ-sourced A/B is worth building after all.
- **Establishes, after the floor analysis:** the direction. The correction is
  right. `FE NEW sweeps more` was an artefact of the clamped metric.

**The general form, and it cost two sessions to see:** *the apparatus answered a
question adjacent to the one being asked, and the answer looked clean.* Same as
the 4-second sustain hold, where a window shorter than the source manufactured a
null. eosed's own summary is the one to keep — **"I was measuring excursion
because excursion is what the metric produced, not because it was the right
quantity."**

What unlocked it was noticing that **two different depths produced an identical
ceiling**, which is not something the parameter can do. That number was in the
first report and was read as incidental.

### The rate law is CONFIRMED on a second dataset and a second source

**No hardware. eosed extracted decay times from the SUSLEVEL captures** — rate
byte 72 throughout — and tested each against `span / 27.9 dB/s` using that
preset's own measured span:

```
n = 11 usable points   mean meas/pred 0.951   sd 0.048   -> implied 26.5 dB/s
                                                            ENVSPAN gave 27.9
```

**Two experiments, two banks, two sources, one rate byte: 5% apart.** The
ENVSPAN result is not an artefact of that bank.

### The exclusions validate themselves, and this is the strongest part

The noise-floor and ceiling exclusions were chosen from the LEVEL data, before
any timing analysis. Ranked afterwards, **both groups fail in the direction
their exclusion predicts, on a measurement that knows nothing about them:**

```
bytes 64, 68, 72   meas/pred 0.607, 0.682, 0.753   run SHORT   noise floor
byte 120           meas/pred 1.624                 runs LONG   ceiling
usable band 80-116                    0.95 +/- 0.05
```

The floor cases **must** run short: the envelope decays into noise, so the
plateau reads too high, the span too small, the predicted time too long. The
trend is monotonic exactly as contamination predicts — 0.607, 0.682, 0.753, then
0.853 climbing out at byte 76. The ceiling case runs long for the mirror reason:
a tiny span measured at 10 ms resolution.

**The boundaries were not fitted to make the answer tidy** — they were set by one
kind of evidence and confirmed by another.

### The offered explanation for the 5% does NOT fit, and that is worth saying

eosed attributed the 0.951 to their estimator firing early: a threshold at 5% of
the linear distance above the plateau. **Computed, that mechanism predicts a
much larger and strongly span-dependent bias than the data shows:**

```
span 30 dB   model predicts ratio 0.730   measured 0.853
span  4 dB   model predicts ratio 0.937   measured 0.907
span-vs-ratio correlation: -0.452 (n=11), weak
```

The model spans 0.73-0.94 where the data spans 0.85-0.99, and the data is much
flatter than a threshold rule would make it. **So the direction is right and the
magnitude is wrong by a factor of three to five, and the residuals carry far
less span-dependence than the mechanism requires.**

Their conclusion — *do not quote 26.5 as a competing figure* — still stands, and
for a better reason than the one given: **the 5% is not explained**, rather than
explained by a known bias. Two independent measurements agreeing to 5% is the
result; attributing the remainder is not yet possible.

### The fix to the experiment — now optional

The floor already answers it. A rebuild with a lower base cutoff would give a
cleaner measurement *and* restore the peak as an independent check, which is
worth having, but the answer no longer waits on the card.

Re-run with the base cutoff low enough that the peak is nowhere near the ceiling,
**or** measure the −3 dB corner against a reference band rather than a centroid —
a transfer-function measurement rather than a spectral summary. `corner_frequency()`
already does the right thing, and §RULER records that its source-cancelling
`reference=` argument has never been passed at any call site.

## §GRANULARITY — one false member says nothing about its neighbours (2026-08-18)

**eosed's, from a README sentence, and it is not a prose lesson.**

A Support section bundled three claims into one sentence: the S3000XL, the E4XT
and the K2000R were all "bought for the purpose". Two were false — both the
E4XT and the K2000R were already owned — and **one was true**, confirmed twice
by Jan directly.

**The safe-looking response to discovering the error was to distrust the whole
sentence.** That would have deleted a true, well-sourced claim. The instinct to
re-confirm rather than accept a transcript was right; the instinct to strip the
lot would have been an over-correction, and it was the advice in circulation for
about an hour.

> **A compound claim has to be falsified per element. Discovering one member is
> wrong tells you nothing about its neighbours, in either direction.**

### The same shape, twice already this week, in measurements

- **§SUSLEVEL relabelling.** A byte-labelling fault made one bank look like a
  2.25x outlier. The correct response was not to distrust the bank — every
  measurement in it was sound, and relabelled it agreed with two others to
  0.4%. **The fault was in one part of the record and the surrounding data was
  fine.**
- **recon's excluded byte ranges.** Each exclusion — noise floor below, ceiling
  above — was justified on its own evidence, and confirmed later by a timing
  measurement that knew nothing about them. Excluding by *association* with a
  neighbouring bad point would have thrown away good data at the boundary.

### Why the wrong instinct is attractive

Distrusting a whole compound feels like the conservative move, and conservatism
is usually right when a fault appears. **It is not conservative here — it
destroys evidence.** The conservative act is to re-derive each member
separately, which costs more and looks less decisive.

### And the part neither party resolved

The S3000XL was settled by **Jan volunteering it**, not by either session
asking. Two of us had it flagged as open and were being careful about it; what
closed it was the person concerned mentioning it in passing. Worth knowing that
the correct process here did not actually produce the answer.

## §AKAILOOPRATE — RETRACTED: the loop does not play 11% fast; I measured a stacked sine (2026-08-18)

> **RETRACTED the same day it was written. There is no 11% pitch error, no
> +1.82 semitones, and no reason to suspect the AKAI rate field.** Everything
> below the banner is the original text, kept unedited so the reasoning stays
> inspectable — but its conclusion is wrong and it must not be cited.
>
> **What actually happened.** The autocorrelation was arithmetically correct and
> its premise was false. It assumed the captured audio was our white noise,
> whose only periodicity is the loop, so a correlation peak could only be the
> loop period. **The capture was not our white noise.** It carried a stacked
> sine on top of it, and a sine correlates at ~1.0 at *every* integer multiple
> of its own period — so `r = 0.9999 at lag 1.8004 s` measured the tone, and
> would have landed on some equally convincing lag whatever our sample did.
>
> **Where the tone came from.** `NSWHITE.P3` on the old `NOISE` volume is
> **PRGNUM 0**, re-confirmed from the image bytes 2026-08-18 17:54 —
>
> ```
> HD4.img  volume 'NOISE'
>   NSWHITE.P3   PRGNUM   0   PMCHAN 0 (ch 1)
>   NSPINK.P3    PRGNUM   1   PMCHAN 1 (ch 2)
> ```
>
> — and programs sharing a PRGNUM all sound together. It stacked with the boot
> TEST PROGRAM and with a resident library program on `PMCHAN 255` (OMNI), which
> answers every channel and so cannot be escaped by choosing a different one.
> s3ked reached the same conclusion independently and retracted their §135.
>
> **The tell I walked straight past, and the lesson.** The section's own "What
> has NOT been ruled out" list opens with *"the note s3ked actually played —
> unknown to me"*. I recorded that the identity of the sounding thing was
> unverified, and then reasoned about its pitch anyway. **An unverified premise
> noted in prose does not become verified by being noted** (cf. §PROSEGUARD);
> it should have blocked the measurement, not annotated it.
>
> Note also how well the wrong answer behaved: 1.8004 s is *nearly* a clean
> semitone ratio, close enough to feel like a real physical effect with a small
> residual. Plausibility was the trap, not sloppiness in the arithmetic.
>
> **The fix is already on the card.** `CALNOISE` (HD7, id 7) puts its four
> programs on PRGNUM 120-123 with explicit channels 0-3 and **no OMNI**, and
> ships `HD7.manifest.json` carrying the spectrum and lag-1 correlation measured
> on the frames actually written (white -0.0022, pink +0.8713). A capture of the
> WHITE source reading lag-1 near +1 now means the sampler is not playing what
> we wrote — which is the check that would have caught this in one line.
>
> **The damage is wider than this section, checked rather than assumed.** After
> retracting the above I compared every capture in `~/temp/s3ked-logs/` (50 wavs)
> against the octave-band spectrum of the frames we actually wrote. **Not one of
> them contains our noise.** Two populations:
>
> ```
> ctl_nswhite / test2_clean / gainhold / playagain / pf_*  100.0% in ONE band -> pure sine
> new-NSWHITE / ns-60 / sptype-0 / iso_* / loop-*           ~80% in one 8-16 kHz spike
> our written NOISEW1S.S3                    slope +3.1 dB/band, lag-1 -0.002  (white)
> ```
>
> The sine TRACKS THE PLAYED NOTE -- 48 -> 131.0 Hz, 60 -> 261.5, 72 -> 523.0,
> exact octaves -- so it is a resident program answering, not rig hum, and it is
> a *pure* sine (harmonics all below -60 dB), so it is not our own `_gen_tone`
> either. **This means TEST 2's "loop mode 0 sustains" rests on the same void
> evidence** and its TODO row has been reopened. Note the direction: the original
> "loop in release" claim is not restored, it is *unmeasured*.
>
> **`tests/re_banks/is_it_our_noise.py` now exists so this cannot recur.** It
> compares octave-band shape and lag-1 against what noise must look like, which
> no tone can fake, and it is verified both ways: PASS on the written white and
> pink frames, FAIL on every capture above. Run it BEFORE any analysis --
> a plausible wrong result is the failure mode here, not an implausible one.
>
> **Still genuinely open, and untouched by this retraction:** whether the
> S3000XL honours the stored rate field at `0x8a` at all. That question came
> from §E4BRATE on the E-MU side, not from this measurement, and it needs a
> deliberate two-rate test on `CALNOISE`.


**Found while verifying s3ked's TEST 2 capture rather than accepting its
summary.** The loop-mode question it was built for is settled — mode 0 sustains
— but the same capture carries a discrepancy nobody was looking for.

`NSWHITE` is 88200 frames, looped whole, stored at 44100 Hz. **That is 2.0000 s
per loop.** Autocorrelating a 100 ms window from the sustain against itself at
varying lags:

```
lag 1.8004 s   r = +0.9999      <- the loop period
lag 2.0000 s   r = +0.2203
```

**r = 0.9999 is not ambiguous.** It is genuinely looping, and the period is
1.8004 s, not 2.0000. That is `2.0000 / 1.8004 = 1.1109`, i.e. **+1.82
semitones sharp**, or an implied playback rate of ~48990 Hz against a stored
44100.

### What has been ruled out, from the file

Read from our own written bytes on the pre-session backup:

```
root note (0x02)  60        correct, and what the generator asked for
zone tune (+0x0e)  0
STUNO (0x14)       0
rate  (0x8a)   44100 Hz
zone1 sample  'NSWHITE'     resolves correctly
key range      24..127
```

**Nothing in the file is transposing it.** And it is not a played-note effect
either, at least not a clean one — against root 60 the integer semitones give
2.0000, 1.8877, 1.7818, 1.6818 s, and **1.8004 sits between two of them**,
1% from note 62 and 5% from note 61.

### What has NOT been ruled out

- **The note s3ked actually played.** Unknown to me, and the cheapest thing to
  ask. If it was 62 the residual is 1%, which is a different and much smaller
  problem than 11%.
- **A global tune on the machine**, master or program level, that we do not read.
- **The capture clock.** The wav is 48 kHz nominal; an 11% error is far beyond
  plausible drift, so this is unlikely rather than excluded.
- **The same class as §E4BRATE on the E-MU side** — where EOS ignored the
  stored rate field and played everything as though it were 44.1 kHz, making
  sub-44.1 samples play sharp by exactly `src/dst`. **That bug had this shape**:
  a stored rate that the machine does not honour. Worth checking whether the
  S3000XL derives playback rate from `0x8a` at all.

### Why it matters beyond a bench sample

If a converted sample plays 11% sharp, **every pitched AKAI conversion is out by
nearly two semitones** and nobody has noticed because the corpus work has been
about names, zones and filters rather than tuning. `CD3-PITCHCAL` exists on the
E-MU card for exactly this kind of question and there is an AKAI equivalent
volume — that is the instrument to point at this.

**Do not act on this yet.** One measurement, on one sample, with the played note
unknown.

## §AKAIPRGCLAMP — WITHDRAWN: the clamp is not silent and the fix I proposed was already rejected (2026-08-18)

> **WITHDRAWN the same evening. This filed a bug against code that was already
> correct, for the second time today.** Both of its claims are wrong:
>
> **1. It is not silent.** `build_akai_volume` already warns:
> *"this volume holds more than 128 programs, and MIDI has 128 program numbers.
> Programs past the 128th all carry number 127 and will stack on one program
> change; they remain selectable from the sampler's own panel."* The final
> clause is a nuance this section missed entirely — the programs are not lost,
> only unreachable by program change.
>
> **2. The fix it proposed was already considered and rejected, with better
> reasoning.** The writer's own note says splitting at 128 is *"NOT"* the
> solution: the machine holds more than 128 happily, they are all selectable
> from the panel, and *"splitting a volume that would have loaded is the
> over-tight clamp this project has recorded twice as the worse failure"*. It
> also explains why clamping beats wrapping — damage lands on the tail, so
> 0..126 stay individually addressable, rather than being spread over the
> low numbers most likely to be reached for.
>
> **Why it looked silent:** the bench generator that hit it calls
> `build_program` directly and never reaches `build_akai_volume`, which is where
> the warning lives. That is the same bypass that defeated the name-uniqueness
> defence in §AKAINAME12 — a second path to the disc that skips the writer's
> judgement, and a second wrong conclusion drawn from it.
>
> **The transferable part:** a bug found through a bench script must be
> reproduced through the production path before it is filed. Twice today a
> working component was blamed because the harness went around it, and both
> times the evidence looked clean.
>
> The observation below about the clamp's mechanics is accurate and is kept;
> only the "silent" framing and the proposed fix are withdrawn.

`writers/akai_s3000_writer.py`, in `build_program`:

```python
p[0x0f] = min(prog_num, 127)
```

**The clamp is correct and the silence is not.** MIDI program numbers are seven
bits; there is no byte value that addresses a 129th program. So the writer cannot
give every program a unique number once a volume passes 128 — but it can stop
pretending it did.

**Why it matters.** Programs sharing a PRGNUM do not merely become hard to
select: they **stack**, and one program change fires all of them together. That
is measured on the S3000XL, not inferred, and it is the mechanism behind the
retracted §AKAILOOPRATE — an evening of measurement made on three programs
sounding at once. Reproduced directly against the writer:

```
132 programs requested 0..131  ->  128 distinct PRGNUM values
PRGNUM 127 shared by requested 127..131  (5 programs)
```

### How it was found, which is the transferable part

Staging `RATECAL` I asked for PRGNUM 130-133. The generator printed:

```
RATE  44100  PRGNUM 130  ch 8
RATE  22050  PRGNUM 131  ch 9
RATE  11025  PRGNUM 132  ch 10
RATE  32000  PRGNUM 133  ch 11
```

— four distinct numbers, exactly as intended. The image held **127 four times**.
Every line of that log was true about the *request* and false about the *bytes*,
and no amount of re-reading it would have shown the difference. Reading the
finished image back with the ordinary parser took one call and showed it at once.

**So the rule is: a generator is not finished when it has written; it is finished
when it has read back.** `gen_akai_ratecal_disc.py::_verify_written` now does
this and raises rather than warns, because a measurement disc that is quietly
wrong is worse than no disc. Worth porting to the other `gen_*` scripts.

### Two candidate fixes

1. **Warn at write time.** Cheapest, and it converts a silent stack into a
   visible one. `build_akai_volume` knows how many programs it is emitting, so
   the check belongs there rather than in `build_program`, which sees one at a
   time and cannot know it is the 129th.
2. **Split the volume at 128 programs**, the way `bank_splitter.py` already
   splits E4B banks at their limits. Structurally the honest fix — 128 is a real
   hardware addressing limit, exactly like the 1000-sample E4B ceiling — and it
   keeps every program reachable by program change. More work, and it needs a
   naming convention for the overflow volume.

**Recommendation: do both, warn first.** The warning is a few lines and removes
the silence today; the split can follow. Note that a volume can legitimately hold
far more than 128 *files* (an S3000 directory holds 510 entries), so this is not
a rare edge — a large drum library converted into one volume reaches it.

**Not yet checked:** whether the machine's own SAVE renumbers on the way out, and
what a real library disc does with its 129th program. Both are one look at a
corpus volume with more than 128 programs, offline, no hardware needed.

## §AKAIIDTHIEF — a sidecar file stole the SCSI id and the image was never served (2026-08-18, FIXED — HARDWARE-CONFIRMED)

**Confirmed on the machine 2026-08-18 19:5x:** with the manifests moved out of the root, the S3000XL sees drive 7 and loads volume `CALNOISE`. The disc had existed and been byte-correct for nearly three hours before that; only the id was being taken from it.

**Symptom.** s3ked swept every SCSI id with the sampler and found `CALNOISE` and
`RATECAL` on none of them. Drive 7 returned HD4's twelve volumes on two reads and
errored on a third — an absent device, not a damaged disc.

**Everything we would normally check said the disc was fine.** `HD7.img` was on
the card, 67 108 864 bytes, md5 identical to the local build; `whichcard.py`
reported `id 7: HD7.img` and no collision; the volumes read back correctly
through our own parser. All true, and all irrelevant.

**Cause, from the ZuluSCSI log — the one artefact nobody had read:**

```
-- Opening 'HD7.ratecal.json' for id: 7
---- Configuring as disk drive drive
---- Drive geometry from image size: SectorsPerTrack=1 HeadsPerCylinder=2 total sectors 2
-- Ignoring /HD7.img, SCSI ID 7 is already in use!
```

ZuluSCSI claims an id from **any root file whose name starts `HD<n>` or `CD<n>`**
and does not check that it is an image. The 1245-byte manifest I had deliberately
placed *beside* the image — so that the disc's measured flatness would travel
with it — became a 1 kB disk at id 7, and the real image was refused.

**The manifest discipline defeated itself.** Putting the measurement beside the
artefact was right; putting it in the emulator's scan path was not, and nothing
about the naming looked dangerous. `HD7.manifest.json` had been on the card since
17:03, so the CALNOISE disc was never visible either — the first staging failed
silently too, and was not noticed because Jan happened to be on another volume
both times.

**Fix.** Manifests moved to `/manifests/` on the card; subdirectories are not
scanned, which is what makes that a fix rather than a rename.

**Guard.** `whichcard.py` now enumerates ids by the EMULATOR'S rule — glob
`[HC]D[0-9]*` and judge the extension afterwards — and reports a non-image file
as stealing that id. It previously globbed `CD*.iso`/`HD*.img` only, so the thief
was invisible to it *precisely because it was not an image*. That is the same
structural blindness as the `^CD[0-9]` grep that could not see `HD0.img` owning
id 0: **a check written in terms of what we expect to find cannot see the thing
that does not look like it.** Verified in both directions — it fires on a planted
`HD5.notes.txt` and clears when removed.

**The general lesson, which cost the most.** Three independent verifications
passed (file present, md5 identical, parser reads both volumes) and the disc
still did not exist as far as the sampler was concerned, because every one of
them verified OUR side of the interface. The emulator's log was the only artefact
that described the other side, and it says plainly, on every boot, which file
owns which id. **Read the log of the thing that actually serves the data.**

## §AKAINAME12 — two bench samples truncated to the same 12-character name (2026-08-18, FIXED)

`NOISE W SHORT1` and `NOISE W SHORTL` both store as **`NOISE W SHOR`**. AKAI names
are 12 characters and zones reference samples BY NAME, so the machine resolved
both programs to one sample. The one-shot that had to fall silent at t=2.000 —
the entire point of the pair — played the looped audio instead.

Measured by s3ked on the S3000XL: PRGNUM 124 held flat to 3.95 s, and the two
captures correlated **+0.6133** despite being built from deliberately different
seeds. That number is the signature of one sample answering twice with
independent note-on phase. Confirmed here from the image, which is unambiguous:

```
NOISEWS1.S3  stored 1819131d0f0a210a1d12191c
NOISEWSL.S3  stored 1819131d0f0a210a1d12191c    identical
```

**The defence already existed and was bypassed.** `akai_s3000_writer.uniq()`
handles exactly this for real conversions, and its own comment states the failure
mode — *"two SAMPLES sharing a name and carrying different audio ... zones
reference samples BY NAME ... silent, and wrong rather than absent"*. The bench
generator called `build_sample` directly with hand-written names and never
reached it. So this is not a writer regression; it is a second path to the disc
that skipped the writer's judgement.

**Fix:** `NOISE2S 1SHT` / `NOISE2S LOOP`, differing at character 9 rather than
character 14, so nothing depends on the exact ceiling.

**Guard:** `tests/re_banks/akai_disc_verify.py`, shared by both bench generators,
reads the built image back and refuses it on duplicate stored names (compared as
raw bytes, after truncation and charset mapping — decoding first would hide
either), duplicate PRGNUMs, PMCHAN 255, or a PRGNUM sitting at the 127 clamp. It
reproduces this defect on the shipped disc and passes the corrected one.

**Why a shared module rather than a check in each generator:** the two discs built
that day shipped *different* defects — this one, and §AKAIPRGCLAMP's collapsed
PRGNUMs — so neither script would have caught the other's. Both were invisible in
everything the builds printed, because both printed the request rather than the
stored byte.

## §AKAILOADTYPE — LOAD type 1 loads no samples, contradicting our SAVE-type note (2026-08-18, OPEN)

s3ked measured on the S3000XL: `trigger_load(1)`, documented as ALL PROGS+SAMPLES,
loaded six programs and **zero** samples — free memory unchanged, capture silent
at −70.3 dBFS. `trigger_load(3)` then loaded all six samples. Reproduced on the
machine's own `BOOT SYSTEM#` volume, so it is not a property of our disc.

This contradicts the TODO row on §AKAIAUX, which has **type 1 writing programs and
samples**. That reading came from SAVE behaviour. Two possibilities, and nothing
yet distinguishes them:

1. LOAD and SAVE type numbers are **separate namespaces** that happen to overlap,
   in which case our note is right about SAVE and says nothing about LOAD.
2. One of the two readings is simply wrong.

**Deliberately recorded as a contradiction rather than folded into the existing
note.** s3ked's evidence is a direct measurement, repeated, on two volumes; ours
is an inference from the save page. Overwriting one with the other would destroy
the disagreement, which is the only thing currently pointing at the answer.

**Cheap next step, no hardware:** a real library disc saved as ENTIRE by the
machine tells us what a type-0 volume contains; comparing the LOAD menu's own
labels against the SAVE menu's, on the panel, settles whether the numbering is
shared. Until then, use LOAD type 3 for samples.

## §AKAIFILTQTY — two AKAI filter laws that disagree, for a principled reason (2026-08-18, OPEN — DEFINITIONAL)

s3ked swept `FILFRQ` on a gate-verified 20 s white-noise source (CALNOISE PRGNUM
120) and took the −3 dB point of *filtered spectrum ÷ filter-open spectrum*, which
cancels source, rumble and rig response together:

```
FILFRQ   corner Hz   peak/median
    40      134          5963
    50      282          4548
    60      595          1586
    70     1195           458
    80     2518           106
    90     5493            20
    99       --             4     (reference)

Hz = 7.00 * exp(0.07381 * FILFRQ)     r2 0.99981, max error 2.6%
9.39 units per octave, 1.278 semitones per unit
```

**This reproduces §20 to three significant figures** (`6.998 * exp(0.07384 * x)`)
— and §20 was superseded by §54, which measured 111 Hz where this measures 134 at
FILFRQ 40 and argued §20 was wrong by 20–30% and growing.

**Neither is wrong. They measure different quantities.**

* **§54 measures the RESONANCE PEAK**: raise `FILQ`, difference against `FILQ 0`,
  and the peak sits at the pole frequency — the filter's own corner.
* **This measures the −3 dB point of the transfer function**, which for a damped
  multi-pole lowpass is a different frequency, and is closely related to what
  §20's centroid method was tracking. That is why it reproduces §20 rather than
  §54, and the agreement is *not* a vindication of §20's method.

**Which one our writer needs, decided rather than left open.** `akai_filter_byte()`
maps a **source instrument's stated cutoff** onto `FILFRQ`, and XPM, EXS24, SFZ and
the rest all express that as the filter's corner/pole. So the pole frequency is the
right quantity and **§54 remains the writer's law**. `akai_filter_byte()` is already
derived from the resonance peak, so it stays as it is. The −3 dB law would be the
right one for matching perceived brightness or a −3 dB spec, and for nothing we
currently convert.

### Two traps for anyone repeating the sweep

1. **`peak/median` is not an intruder detector on a filter sweep.** Closing a
   lowpass over noise raises peak-to-median *by construction* — it ran 5963 down
   to 4 as the filter opened, far above the ~500 watch-line agreed for ordinary
   captures. Below about `FILFRQ 60` the statistic says nothing about identity.
   The usable signature is that it must move **smoothly with the control**: a ramp
   is the filter, a step is a program answering.
2. **Below `FILFRQ 40` the readings flatten at ~90 Hz and that is the measurement
   floor, not the filter** — the corner drops under the rumble. Fitting those
   points yields a shallower law. Discard 0–30.

**Open:** whether the pole-vs-−3 dB gap is exactly what a damped multi-pole
response predicts. That is testable offline from the two laws plus a filter order,
and would turn a plausible explanation into a checked one. Until then this is
recorded as a definitional conflict, not a correction to either side.

## §AKAILOOPCROSS — the pool-base conclusion is REFUTED BY THE CORPUS; loop_start is the suspect (2026-08-18, REOPENED)

**Three artefacts that cannot all be true, recorded before any of them is
explained away.**

**What the machine says** (s3ked, S3000XL):

* its own selected-program register reads **PRGNUM 122** after the program
  change — the machine naming its own selection, not an inference from audio
* a 25 s hold runs to 25.20 s with no discontinuity at 20.00 s, so the thing
  sounding is **looped**, which excludes the 20 s pink one-shot at PRGNUM 121
* the resident sample names read back **distinct**, so no collision in that pair
* the audio measures lag-1 +0.863, matching our written pink's +0.868

**What the image says**, by two independent extraction routes:

```
parser:  NOISEWLP.S3  stored 'NOISE W LOOP'  lag-1 -0.0024  white
raw:     header@0x0036a000  PCM@0x0036a0c0   lag-1 -0.0021  white
         header@0x0051a000  PCM@0x0051a0c0   lag-1 +0.8684  PINK  ('NOISE P LOOP')
```

The raw route searches the image bytes for the stored name and reads PCM at
`header + SAMPLE_HEADER_LEN`, so name and audio necessarily come from the same
physical object — the failure mode s3ked proposed. The two loop samples are
**1.8 MB apart** on the image with the one-shots between them, so an
off-by-one-directory-entry read is not available as an explanation either.

**One real slip found while checking, which changes nothing:** the PCM slice had
been `0x8a+0x2e = 0xB8` where `SAMPLE_HEADER_LEN` is `0xC0`. Eight bytes. It did
not affect any measurement, but it was an unverified offset, which is what the
challenge was actually about.

### SETTLED HALF: the served content IS crossed, at sample level

s3ked cross-correlated the captures, with controls:

```
CONTROLS
  120 ref vs itself      +1.0000 at lag 0
  120 white vs 121 pink  +0.0335
THE TEST
  PRGNUM 122 capture vs 121 PINK   +0.9992 at 0.8 ms
  PRGNUM 122 capture vs 120 white  +0.0330
  PRGNUM 123 capture vs 120 WHITE  +0.7329 at 1.7 ms
```

+0.9992 is the same waveform, not a similar one, and no spectrum is read
anywhere — so the pink/lowpassed-white confound is irrelevant to it. (Their first
attempt failed its own control: a 64-sample lag grid never landed on lag 0, so a
signal against itself scored −0.008 while still giving +0.43 for the real pair.
That is how correlated pink is, and why the control mattered.)

**So both facts stand: the disc is correct and the machine serves crossed
content.** No single artefact is being discounted.

### The disc is now verified at EVERY level, including the machine's own route

s3ked's hypothesis was that the directory entries might carry each other's start
blocks — which would satisfy both findings, since the parser and the raw search
both read a file's bytes rather than following the directory. Tested by parsing
the 24-byte entries and following each start block:

```
entry NOISEW1S  start blk   5 -> 0x0000a000  header 'NOISE W 1SHOT'  white
entry NOISEP1S  start blk 221 -> 0x001ba000  header 'NOISE P 1SHOT'  PINK
entry NOISEWLP  start blk 437 -> 0x0036a000  header 'NOISE W LOOP'   white
entry NOISEPLP  start blk 653 -> 0x0051a000  header 'NOISE P LOOP'   PINK
entry NOISEWS1  start blk 873 -> 0x006d2000  header 'NOISE W SHOR'   white
entry NOISEWSL  start blk 895 -> 0x006fe000  header 'NOISE W SHOR'   white
```

Entry -> start block -> header name -> audio, correct at every link. The
hypothesis was the right shape and is not the fault.

### TESTED AND DISPROVEN: this is NOT §AKAINAME12 — they are two defects

The hypothesis below was that the duplicate stored name was the only abnormal
condition in the volume and might have disturbed the machine's name table.
**s3ked tested it and it is wrong.** They CLR'd and loaded only the four 20 s
files individually, so the colliding pair never entered memory — resident
duplicate names: none — and the crossing persisted:

```
CONTROLS
  120 vs itself          +1.0000 at lag 0
  120 white vs 121 pink  +0.0343
THE TEST
  PRGNUM 122 'NOISE W LOOP' vs 121 PINK   +0.9818    matches pink
  PRGNUM 123 'NOISE P LOOP' vs 120 WHITE  +0.9144    matches white
```

Peak levels agree independently: white returns at −9.5/−9.2 dBFS and pink at
−17.6/−17.3, and 122 sits on the pink level.

**The rebuild fixes §AKAINAME12 and NOTHING ELSE. The crossing will still be
there afterwards.** Recorded explicitly at s3ked's request, because "the rebuild
fixed both" is exactly the story that gets told later.

### ALSO DISPROVEN: there is no data pointer in the sample header

s3ked's next hypothesis was that the header might carry its own pointer to the
audio — which both extraction routes would have missed, since both assume the PCM
is contiguous at `header + SAMPLE_HEADER_LEN`. Diffing the full 192-byte headers:

```
1 differing byte out of 192
0x09:  NOISEWLP 33 (0x21 'W')    NOISEPLP 26 (0x1a 'P')
```

Character 7 of the name, and nothing else. No `u16`/`u24`/`u32` differs anywhere,
so nothing can carry the 0x1B0000 block distance between them. **The stronger
form:** if a data pointer existed it would have to be *identical* in both, and
then both would play the same audio — which they demonstrably do not.

### The disc is now exhausted

Following s3ked's point that the directory had been followed to the header but
not the header to the data, the one remaining partial check was closed too — zone
1 of keygroup 1 had been read and the rest assumed:

```
all six programs: 1 keygroup, zone1 correct, zones 2-4 empty
```

Verified end to end: entry → start block → header → name → PCM → program →
keygroup → all four zones. **Nothing on the medium is wrong**, and the machine
still serves crossed audio for the loop pair while serving the one-shot pair
correctly.

### AMENDED 2026-08-18 — the rule is NARROWER than stated, and was UNDER-DETERMINED

`SDZERO` (partial loops) does **not** reproduce the off-by-one:

```
prg  names      period   sounding
 94  LOOP 3S       --    SILENT
 95  LOOP 4S    4.000    its OWN
 96  LOOP 5S    5.000    its OWN
 97  LOOP 7S    7.001    its OWN
```

Three of four looped programs play the sample they name. Only the first loaded
is silent. So the observed behaviour there is "the first-loaded looped sample is
silent, the rest are correct" — not the rule below.

**And the CALNOISE evidence could not have established that rule anyway.** On
that disc each one-shot and its matching loop carried IDENTICAL PCM — a
deliberate choice of this project's own bench disc, and the cross-correlation
test was then proposed *resting on* that sharing. It made the observable
two-valued (white or pink) while the question was four-way: "122 sounded pink"
cannot separate slot 1 from slot 3, so **"plays the slot before" and "plays the
slot after" fit that data equally**. The rule was under-determined in its central
claim, not merely over-generalised. (`SDZERO` does rule out `+1`: at slot 0 that
reading predicts LOOP 4S, and the capture is silent.)

**The lesson worth keeping, in s3ked's words:** careful analysis cannot exceed
what the instrument can express, and the instrument's limits are usually
invisible from inside the analysis. The two-valued observable was a property of
the disc supplied, not of the method applied to it, and neither project noticed
until the constraint was load-bearing.

> **REOPENED WITHIN THE HOUR. Jan asked whether the corpus represents this, and
> it does not.**
>
> ```
> 768 factory volumes with samples
> the FIRST sample in directory order is LOOPED in 700 of them   (91.1%)
> ```
>
> If "a looped sample at the pool base does not play" were a property of the
> machine, **nine in ten commercial library discs would have a silent first
> instrument.** That would be notorious, not a discovery. The conclusion below is
> therefore wrong as stated, however clean the measurement was — and the
> measurement is not in doubt; its *generalisation* is.
>
> **What is actually different about our discs:**
>
> ```
> FACTORY looped samples, loop_start == 0 :   1.2%   (204 of 16493, S3000 only)
> OUR bench discs                          : 100%   -- every loop we have written
> ```
>
> Factory loops start INSIDE the sample, at a sustain point. Every loop this
> project has ever written starts at frame 0. Restricted to real S3000 material
> with a genuine loop, the number of factory volumes whose FIRST sample is looped
> with `loop_start 0` is **six across 43 discs — and all six carry
> `loop_length == 1`**, degenerate rather than looped.
>
> **No factory volume is in the condition our silent samples were in.** That is
> the answer to "why is this not common knowledge": nobody makes discs like ours.
>
> **The test, which needs no disc** (Jan's suggestion, and the method lesson
> applied): write `loop_start` on the RESIDENT sample over SysEx and replay — the
> same route that settled the rate question in twenty minutes. `loop_start = 1`
> is the sharpest probe, since a single frame separates "at the base" from "not
> at the base" with everything else identical.
>
> **THE FIX IS PULLED BACK PENDING THAT.** Reordering our volumes to put a
> one-shot first makes them unlike 91% of factory volumes, to dodge a symptom
> whose cause we had wrong. If `loop_start` is the trigger, the correct fix is to
> stop writing `loop_start 0` — a different change, in a different place, and
> much closer to what the format evidently expects.
>
> **A standing rule for the probe, Jan's, 2026-08-18:** a SysEx write must be
> **re-read and confirmed** before anything is concluded from what follows. A
> capture cannot distinguish *"the write took and the hypothesis is wrong"* from
> *"the write never took"*, and only the readback can. Read the NEIGHBOURING
> fields too — if setting `loop_start` also moves `loop_length`, the result
> belongs to two changes and would be credited to one.
>
> This is not a general caution. `loop_start` has obvious constraints (below the
> loop end, below the sample length), so it is a plausible candidate for silent
> clamping — and we know this machine *accepts* without validating (255 written
> to byte `0x01`, read back as 255) but nothing yet says a write is never
> silently dropped. A value that will not stick would itself be a finding worth
> more than the capture.
>
> **The lesson, and it is Jan's:** ask whether the corpus represents a finding
> before building on it. A hardware measurement can be perfectly real and still
> not generalise, and 16493 factory samples were sitting on this disk the whole
> time.

### THE MEASUREMENT (sound) AND ITS GENERALISATION (refuted)

**A LOOPED sample placed at the base of the sampler's object pool does not play
correctly — sometimes silence, sometimes degraded non-periodic audio. Move it off
the base and it is fine.**

The decisive pair. Same volume, same file, same lone-loop arrangement, same
loader, byte-identical loop record; only the address differs:

```
SOLO LOOP at SLOCAT 131072 (the base)   SILENT   -72.8 dBFS
SOLO LOOP at SLOCAT 483872              PLAYS    -8.2 dBFS, period 5.000 s
                                                 at corr 0.967
```

**"Positional, not ordinal" OVERSTATES IT, and Jan's question is what exposed
that.** In every test the two properties moved together:

```
SOLOLOOP alone           loop is 1st loaded AND at the base    silent
SOLOSHOT then SOLOLOOP   loop is 2nd loaded AND above the base plays
```

The machine assigns addresses in load order, so **a sample cannot be first
without landing at the base.** The two are not merely unseparated by our tests —
they may be structurally inseparable by any ordinary load. Telling them apart
would need something artificial: load two samples, free the first, and load a
loop into the freed space.

So the supported claim is the narrower one: **a looped sample that is the first
one loaded — and therefore the one at the base — does not play correctly.**
Which of the two is the operative property is open.

**This changes nothing about the fix.** Emitting a one-shot first makes the loop
neither first nor at the base, so it is correct under either reading. The
distinction would only matter for explaining the mechanism, which we do not have
either way: nothing here says *why* — a wrap in the loop-pointer arithmetic, a
reserved region below 0x20000, an off-by-one at the boundary, all remain
possible and none is evidenced.

Everything trustworthy fits: `SDZERO`/`SDADDR` (loop at base, silent),
`SOLOLOOP` (both loaders, silent), `WHOLELOOP`/`PARTLOOP` bulk (one-shot at base,
all correct), `PARTLOOP` item-loaded (loop at base, **degraded** — correlation
0.29 against 0.77–0.99 everywhere else, and playing neither of the other resident
samples). That last one had looked like a counter-example until s3ked asked what
it was *actually* playing rather than accepting that it made a noise.

**Two loose ends closed by the same finding:**

* `SLOCAT` is §AKAISDATA's field at header `0x16-0x18`. The machine recomputes it
  and ignores what we store — which is exactly why `SDADDR` played identically to
  `SDZERO`: both had their loop placed at the base by the loader whatever address
  we wrote. That result becomes a corroboration rather than a dead end.
* The resident loop record is **byte-identical to what we wrote**, field for
  field (`loop_start 0`, `loop_length 220500` at `0x2c`, `loop_times 9999` at
  `0x30`). s3ked's `0x2a` reading had straddled the 16-bit fraction and the low
  half of the length; our layout is correct.

### THE FIX, in the writer

`build_akai_volume` now emits an **unlooped sample first** when the volume has
one. Under the bulk load a user performs from the front panel the machine takes
directory order, so the one-shot takes the base and no loop can land there.

Deliberately a **reorder, not a filter**: nothing is added, removed or altered. A
volume with no one-shot at all is left exactly as it was and **warned about**,
because inventing a dummy one-shot to occupy the base would put content on the
disc the source never had.

**Not verified:** whether the machine assigns the base to the first *directory*
entry or the first *sample* entry. Our volumes have always emitted samples before
programs so the two have never differed — and the fix is correct under either
reading, since the sample moved to the front is both.

**Still wanted:** hardware confirmation of a *converted* volume ordered this way.
The mechanism is confirmed; the fix built on it is not yet.

### SUPERSEDED: THE SLOT-0 RULE IS CONTRADICTED — DO NOT CITE IT (2026-08-18, later the same evening)

**A loop at slot 0 sounded.** s3ked loaded items individually, choosing the
order, and put a LOOP first:

```
samples loaded : LOOP 3S, SHOT 2S, LOOP 4S     -> a LOOP at slot 0
prg  names     slot   peak    lasts   reading
 85  SHOT 2S      1   -8.5     1.90   correct
 86  LOOP 3S      0   -0.0    12.70   SOUNDED
 87  LOOP 4S      2   -8.2    12.40   3.500 s, its own, correct
```

So the rule stated below is **not supported** and must not be used. It is left
visible rather than deleted, because the observations it was built on are real
and the next rule has to explain them too.

**One thing it DID settle, and that survives:** "the first loaded LOOP is silent
wherever it sits" is false — on `WHOLELOOP`/`PARTLOOP` the first loaded loop sits
at slot 1 and sounds. That was one of the two premises the writer-side workaround
needs, and it holds.

### STEP BACK (2026-08-18, at Jan's request): the method is the problem, not the disc

**The load-method hypothesis is already contradicted by data we had.**

```
SDZERO / SDADDR    4 samples, BULK, loop at slot 0     SILENT
PARTLOOP items     3 samples, ITEM, loop at slot 0     SOUNDED
CALNOISE 'alone'   1 sample,  ITEM, loop at slot 0     SILENT   <-- same loader
```

Rows two and three share a loader and disagree, so the loader is not the whole
story. What they do not share is the number of resident samples. That is one
observation and not a rule — the point is that the hypothesis we were about to
spend a crossing on was already refuted by a capture taken hours earlier, and
nobody re-read the old data before proposing the next test.

**A control was never run:** every "alone" observation used a LOOPED sample, so
"a lone looped sample is silent" and "a lone sample is silent" are not separated
by anything we have. `SOLOLOOP` / `SOLOSHOT` now exist for exactly that — same
seed, same audio, same length, differing only in `SPTYPE` and the loop record.

### THE METHOD CHANGE, which is the real answer

Every investigation today compared **files on a disc** against **captures from a
speaker** and inferred what happened in between. Each round therefore cost a card
crossing, and the inference step is where all three withdrawn rules died.

**The machine will say what it loaded, and the one question that matters has
never been asked: in a silent case, what does the RESIDENT sample's loop record
say?**

```
read before playing any note, in a silent AND a sounding configuration:
    resident loop record    loop start, loop end, loop times, SPTYPE
    resident data address   header 0x16-0x18, which the machine recomputes
```

A difference there is the mechanism, read directly rather than triangulated
across two discs. No difference is nearly as valuable: it excludes the whole
class and points at the data address or the voice allocator instead.

**Why it took until now, which is the transferable part.** A disc-building loop
was available and each round produced a clean-looking result, so building became
the method. Reading the machine's own state was always cheaper, needed no
crossing, and was reached for only when a disc could not answer. **The tool that
is already working is the one that stops you looking for a better one** — and
three of the day's rules were wrong in ways only the next disc revealed, which is
exactly the cost of an inference-heavy loop that feels productive.

### SUPERSEDED: the live hypothesis was the LOAD METHOD, not the slot

The variable s3ked can see between the runs:

```
SDZERO / SDADDR   bulk: all samples, then all programs   -> loop at slot 0 SILENT
this run          per-item, chosen order                 -> loop at slot 0 SOUNDS
```

Every observation of the silence is consistent with that split. **If it holds,
the fault belongs to the bulk loader rather than to slot 0.**

**AGREED BY BOTH PROJECTS after an exchange that went the other way.** s3ked
first held that a loader-dependent fault is not something a file writer can order
its way around, then corrected it: *"I collapsed 'the loader is the variable'
into 'the loader is opaque to us', which does not follow at all."*

**And the meta-point they drew from it is worth more than the correction**, because
it names a failure this project has no habit of watching for:

> An overstated limitation is as wrong as an overstated finding, and it is easier
> to get away with, because nobody argues with someone talking their own result
> down.

Every other correction today ran the usual way — a claim was too strong and got
narrowed. This one ran backwards: a capability was written off too early, and the
under-claim went unchallenged for longer than an over-claim would have, precisely
because it sounded like caution. Scepticism aimed only at optimism is not
scepticism.

**Note what that does NOT do: it does not kill the writer-side workaround.**
Under a bulk load the machine takes directory order, and directory order is
`build_akai_volume`'s — so emitting a one-shot first still puts a non-loop at
slot 0 for exactly the load path where the silence appears. A user loading a
whole volume from the front panel is doing the bulk load, which is the case that
matters. The workaround would be unnecessary for item loads and effective for
bulk ones.

**The test, no rebuild needed:** CLR and bulk-load `PARTLOOP`, then CLR and load
the same five items individually in directory order. Same slots, different
loader. If the silence follows the loader, slot 0 is a red herring.

### THE PATTERN, and it is not about discs (s3ked's framing, kept verbatim in substance)

Two of this project's own instruments limited conclusions today in ways invisible
from inside the analysis, and **both flaws were in the SAFEGUARDS rather than in
the experiments**:

* CALNOISE's shared PCM was in the thing meant to *identify content*
* the harmonic overlap was in the thing meant to make a leak *unmissable*

An experiment gets re-derived every time someone reads it. **A safeguard is the
one part nobody re-derives** — it is trusted precisely so that attention can go
elsewhere — which is what makes it the expensive place to be wrong. Both faults
here were silent, plausible, and load-bearing for hours.

The corollary for this project: a check must be verified in both directions
before it is relied on, and the properties it *claims* must be tested as
arithmetic, not asserted in prose. "The period sets are disjoint" was true and
insufficient; nobody had asked whether their harmonics were.

(s3ked adds that their detector's argmax and my period set had to coincide to
produce the false leak — either alone would have been caught. That is true and
does not soften it: safeguards fail together because each is trusted to cover
the other.)

### An anomaly worth its own look: the hot, poorly-correlated capture

PRGNUM 86 sounded at **−0.0 dBFS with 0.01% pinned**, where every other capture
sat at −8, and its autocorrelation peaked at **2.542 s with only 0.29** where
everything else gave its own period to three decimals at 0.77–0.99. The written
files are all peak 0.350 — verified — so the level difference is not in what we
wrote.

**Both symptoms fall out of one cause: two voices sounding instead of one.** Two
copies of the same noise at different phase sum to roughly +6 dB (−8.5 + 6 ≈
−2.5, and clipping would take the rest of the way to 0.0) *and* smear the
periodicity, because the autocorrelation of a sum of two offset copies is much
weaker than of either alone. Clipping alone would not explain a correlation
collapse from 0.98 to 0.29.

If that is right it is a second finding hiding inside this one, and it is
testable on the capture already taken: cross-correlate it against itself and look
for **two** peaks rather than one.

### SUPERSEDED RULE, kept for the observations it must still explain

`WHOLELOOP` and `PARTLOOP` came back **indistinguishable** — every loop plays
its own sample in both — so **loop extent is excluded**. And the one-shot placed
at slot 0 **sounds**, in both volumes, stopping at 1.90 s as a 2 s one-shot must.

```
A LOOPED sample at slot 0 is silent.
A loop at any other slot plays its own sample.
A one-shot at slot 0 sounds.
```

Every trustworthy observation fits: `SDZERO`/`SDADDR` (loop at slot 0 silent,
loops at 1-3 correct) and `WHOLELOOP`/`PARTLOOP` (one-shot at slot 0 sounds,
loops at 1-4 correct). **CALNOISE is excluded** — its shared PCM means nothing it
showed can be trusted, by the criterion set before the result was known.

So the bug is bounded to **one silent instrument per volume, and only when the
first thing loaded is a looped sample** — far smaller than the "every sustained
instrument plays the wrong sample" this started as.

**A workaround we control:** slot order is directory order, and the directory
order is `build_akai_volume`'s. Emitting a one-shot first would avoid the fault
entirely for any volume containing one. Two things must be confirmed before
building it, and both were asked rather than assumed: whether it is *slot 0* or
*the first loaded LOOP* (identical on every disc so far), and whether it follows
the sample's slot or the program's load order.

### A DESIGN FLAW IN THE DISJOINT-PERIOD DISCS, found by s3ked

The period sets were chosen pairwise disjoint, and that is **not sufficient**:

```
2 x 2.5 = 5.0   in the other set
2 x 3.5 = 7.0   in the other set
```

An autocorrelation detector taking the **argmax** can score a harmonic above the
fundamental on a clean loop, so two captures were flagged as cross-volume leaks
by the very check built to make a leak unmissable. **The check manufactured the
alarm it existed to prevent** — the second time in one day that a disc of this
project's own making constrained a conclusion invisibly from inside the analysis.

Two fixes, both adopted:

* **Take the FIRST autocorrelation peak above threshold, never the largest.** A
  fundamental is always the earliest peak; harmonics are later by construction.
* **Choose period sets disjoint under integer multiples**, not merely pairwise.

CALNOISE v2 is rebuilt on both: six distinct seeds (highest correlation between
any two files 0.047), periods 2/5/7 with no collision under x2/x3/x4.

### SUPERSEDED hypothesis: loop EXTENT

The one structural difference left between the two discs is that **CALNOISE's
loops span the whole sample while SDZERO's span a part of it.** The sample-data
address is excluded (§AKAISDATA: `SDADDR` ≡ `SDZERO`).

**This is not academic — our converter emits both shapes.** `auto_loop` finds a
sustain portion and produces partial loops, but a source whose own loop points
span the file is written through whole, and the real converted volumes on HD4
(`VF NEW` / `VF OLD`) hold **two whole-sample loops** among eighteen one-shots.

`~/temp/HD7_r4.img` carries `WHOLELOOP` and `PARTLOOP` to settle it: five
distinct seeds, no shared PCM anywhere, and **disjoint loop-period sets** —
3.0/4.0/5.0/7.0 against 2.5/3.5/4.5/6.5 — so a measured period names both which
sample sounded and which volume it came from, and a leak announces itself as an
impossible number instead of hiding as a plausible reading.

**Slot 0 in both is a ONE-SHOT** (s3ked's addition), because every disc so far
put a loop there and so could never separate "silent because it is slot 0" from
"silent because it is a loop". If it sounds, the silence belongs to looping.

### SUPERSEDED: the rule as first stated, at nine observations

**s3ked, §136 (their commit 784e3dc):**

> A LOOPED program plays the sample loaded immediately BEFORE the one it names.
> One-shots are correct.

Every observation of the evening follows, including all three silences — which
are simply the off-by-one reaching past the start of the pool when the named
looped sample is the first one loaded:

```
load W1S,P1S,WLP,PLP   122 names slot2 -> plays slot1 = P1S   PINK     observed
                       123 names slot3 -> plays slot2 = WLP   WHITE    observed
load PLP,WLP,P1S,W1S   122 names slot1 -> plays slot0 = PLP   PINK     observed
                       123 names slot0 -> plays slot-1        SILENT   observed
WLP alone              122 names slot0 -> plays slot-1        SILENT   observed
load WLP,PLP           122 names slot0 -> plays slot-1        SILENT   PREDICTED
                       123 names slot1 -> plays slot0 = WLP   WHITE    PREDICTED
```

The last two were written into the capture script's docstring **before** the
capture: measured −71.2 dBFS (silent) and slope +3.00 (white to two decimals) —
the exact reverse of what the same two programs did earlier, produced by nothing
but a swapped load order.

`SBADD` resolves correctly by name and is order-independent, so the *name* half
of the binding is sound; `0xFFFF` there simply means unresolved.

**Standing limit, recorded rather than discovered later:** not reproduced on
factory material. Until it is, "the S3000XL does this" is a claim about discs
written by one writer — ours.

### THE SAVES: the machine's own copies are CORRECT

`XCROSS 1` (four 20 s objects resident, crossing present) and `XCROSS 2` (one
sample resident, SILENT), both type-0 saves read back here:

```
XCROSS 1  NOISE W LOOP.S3  lag-1 -0.0023  white   zone1 -> 'NOISE W LOOP'
          NOISE P LOOP.S3  lag-1 +0.8685  PINK    zone1 -> 'NOISE P LOOP'
XCROSS 2  NOISE W LOOP.S3  lag-1 -0.0023  white   zone1 -> 'NOISE W LOOP'
```

Right audio, right name, right zone reference — **including in the silent
state**. So the fault is not in the medium, the directory, or the load into the
pool. It is in what the PLAY path binds to.

### ISOLATION: PRGNUM 122 alone is SILENT — neither predicted branch

s3ked loaded only `NOISEWLP.S3` + `NOISEWLP.P3`. Both load orders, three
captures: −69.9 / −71.2 / −72.8 dBFS against an −86 floor. Everything reads
correct while it is silent — zone `SNAME1` and the resident sample name match
exactly, `SLNGTH 882000`, `SSRATE 44100`, and free memory dropped 1.68 MB, so the
audio really is resident.

**A zone does not bind to a resident sample whose name it matches exactly.** That
is a failure to resolve, not a swap — and the "crossing" may be what that failure
looks like when other samples happen to be present to bind to instead.

### LEADING SUSPECT: the zone pointer at `zone_base+0x16`, which we null out

```
OUR DISC   all six programs        0xFFFF
XCROSS 1   PRGNUM 120 -> 36984
           PRGNUM 121 -> 36996     spaced 12 paragraphs apart
           PRGNUM 122 -> 37008     12 x 16 = 192 bytes = ONE SAMPLE HEADER
           PRGNUM 123 -> 37020     sequential in LOAD ORDER
XCROSS 2   PRGNUM 122 -> 36888
```

§AKAIRESAVE called this field "machine-owned and correctly left alone by us".
The overwrite was measured; **"correctly" was an inference from it and was never
tested.** If resolution of our `0xFFFF` is order- or slot-sensitive rather than
by name, both observations follow: wrong neighbour with four resident, nothing at
all with one.

### THE CORPUS ANSWER: 0xFFFF is normal, so the pointer is probably NOT the cause

With a real factory corpus available (43 discs), scanned properly through the
parser — **10 discs, 5628 programs, 90328 used zones**:

```
value at zone+0x16       count      share
0xFFFF                   31891      35.3%   <- what WE write
0x0000                   27121      30.0%
0x0a0a                   11299      12.5%
everything else          ~20000
```

**`0xFFFF` is the single most common value in factory material.** Writing it is
normal and is not our deviation. Two-thirds of factory zones carry one of the two
null-ish values, which reads as a scratch/RAM pointer that a disc simply carries
in whatever state it was saved in.

This does not fully exonerate the field — a factory disc carrying `0xFFFF` might
resolve correctly for some other reason — but it removes the explanation that
made it the leading suspect, namely "we write something no real disc writes".
**Recorded as evidence against my own hypothesis**, which is the reason the check
was worth running.

(`+0x16` is the last two bytes of each 24-byte zone, `_ZONE_OFFSETS` being
0x22/0x3a/0x52/0x6a — checked, so this is a real field and not name overlap.)

### A corpus check that FAILED FIRST, recorded so it is not repeated

Whether factory discs carry a real value there would settle whether `0xFFFF` is
our deviation. Our reader cannot parse the factory discs available locally — one
is recognised as an AKAI image and then every directory record is skipped as
"directory type 0x00" (its own TODO row). A raw-scan fallback appeared to work,
reporting 191 programs and a tidy pointer distribution of 1/2/3/4 —
**and it was false positives.** Its name validator only checked that bytes fell
in the AKAI charset range, which arbitrary binary passes, and the "zone names" it
produced read `408090 0 080` and `D0C0F0H0F0F0`. Discarded rather than reported.

The tell was in the output the whole time and only visible because the sample
rows were printed. A detector that reports a plausible distribution is not
evidence that it found anything.

**A second error compounded it:** the parser could read those discs all along.
The zero-program count that sent me to a raw scan was mine — it looked only for
S3000 type codes while the discs hold **S1000** volumes (`0x70` = 'p', the same
ASCII letter *without* bit 7). So a working component was blamed, a TODO row was
filed against it, and a hand-rolled replacement produced false data. The row has
been withdrawn rather than deleted.

### Next test: one sample, alone

CLR, load only `NOISEWLP.S3` + `NOISEWLP.P3`. Nothing to cross with.

* **plays pink** → the fault is in loading that single object; nothing is being
  swapped because there is nothing to swap with, and the machine is reading audio
  from somewhere other than where its entry points
* **plays white** → the crossing *requires* the other object present, which puts
  it in the pool or name table and makes load ORDER the next variable — then load
  the two in the opposite order and see whether it follows order or name

### The asymmetry is probably not evidence

```
whole-volume:  122->pink +0.9992   123->white +0.7329
single-file:   122->pink +0.9818   123->white +0.9144
```

The white side is lower in both. Likely a property of white noise rather than of
the swap: correlation against white is dominated by its **high frequencies**,
where most of its energy sits (+3 dB per octave band), and HF decorrelates fast
under even parts-per-million clock drift between two captures, while pink's
energy is spread evenly per octave and dominated by LF. **Testable on existing
captures:** lowpass both to ~2 kHz before correlating; if the white match climbs
toward the pink one it is drift, not information.

### SUPERSEDED HYPOTHESIS (kept for the reasoning): this defect and §AKAINAME12 are ONE defect

The last two rows are the only abnormal condition in the volume: **two distinct
samples at distinct blocks claiming one 12-byte name**. The machine's name table
must do something with the second, and if that handling displaces or overwrites a
slot, samples *other* than the colliding pair can bind to the wrong data — with
every resident name still reading back correctly, which is what is observed.

Treating the two as independent defects was an assumption, and they were
introduced in the same build. **Test, no crossing needed:** load only the four
20 s files individually (LOAD SINGLE), leaving the colliding pair out, and repeat
the correlation. Correct pairing implicates the duplicate name and makes the
corrected disc fix both; still crossed means a genuine load-time or pool-level
fault.

**Also requested while the card is in:** save the loaded state to a scratch volume
so the machine's OWN copy can be dissected offline. If its copy has pink under
'NOISE W LOOP', the crossing is at or before load; if correct, the capture path is
implicated. Doing it before the answer is known is what stops a second crossing
being spent on it.

### The remaining asymmetry

+0.9992 for 122-vs-pink against **+0.7329** for 123-vs-white. A clean swap should
be symmetric. A loop seam falling inside one reference window would do it (the
20 s sample seams once per 20 s), as would the FILFRQ difference between swept and
unswept programs. If the load test returns "still crossed", this asymmetry is the
next thread.

### The test that should settle it

A property of the disc, built in for a different reason: **`NOISEW1S` and
`NOISEWLP` contain the same PCM** (both the `w` array), as do `NOISEP1S` and
`NOISEPLP`. One-shot and loop differ only in `SPTYPE` and the loop fields.

So a **sample-level cross-correlation of the byte-2 capture against the byte-1
and byte-0 captures** identifies the content outright — no spectral
interpretation, no lag-1, no slope. A filter lowers the correlation peak but
cannot move it to the wrong source. Awaiting that result.

### The largest uncontrolled variable

`lag-1` and a fitted octave slope **cannot separate these two shapes**:

```
true pink         flat across all nine bands
lowpassed WHITE   rises ~3 dB/band, then falls off a cliff above the corner
```

Both fit to a shallow slope and both push lag-1 high. And the two capture sets
are not obviously comparable: the one-shot captures (which read CORRECTLY) were
taken before the FILFRQ sweep, the loop captures (which read CROSSED) after it.
PRGNUM 120 was swept and left at 99, fully open; 122 and 123 were never swept and
still carry whatever default the writer wrote.

**Asked for, not assumed:** the nine octave-band values rather than the fitted
slope, and a FILFRQ readback at the moment of capture.

**Deliberately left unresolved.** The machine-register reading is the strongest
single artefact in the set and is not being discounted; the image is verified
twice by independent routes and is not being discounted either. Preferring one
now would destroy the only thing pointing at the answer — the same discipline as
§AKAILOADTYPE one row up.

## §AKAIRATEQUANT — sample-header byte 0x01 selects the playback rate; SSRATE is descriptive only (2026-08-18, CONFIRMED — FIXED)

**Round 1, measured by s3ked on the S3000XL** (RATECAL, fingerprint OK on all
four, `SSRATE` read back correctly off every resident header):

```
stored   f0 measured   implied playback rate
44100      300.0 Hz    44100      HONOURED
22050      300.0 Hz    22050      HONOURED
11025      600.0 Hz    22050      x2 fast
32000      413.4 Hz    44100      x1.378
```

**This is NOT §E4BRATE.** There, playback is always 44100 and a 22050 sample comes
out an octave sharp. Here 22050 is dead on. The stored field is honoured for the
supported rates and something else happens for the rest.

### Two models fit those four points equally well

**A — `h[0x01]` is the playback-rate selector**, 0 = 22050, 1 = 44100, and
`SSRATE` at `0x8a` is descriptive only. `build_sample` writes that byte itself:

```python
# bandwidth: 0 = 10 kHz, 1 = 20 kHz. Anything at or above 30 kHz is
# full-bandwidth material.
h[0x01] = 1 if sd.sample_rate >= 30000 else 0
```

11025 → flag 0 → 22050 (×2). 32000 → flag 1 → 44100 (×1.378). Both exact.

**B — the machine reads `SSRATE` and quantises to a supported neighbour** ("next
one up"), which gives the identical four numbers.

### Why the difference matters more than a bench curiosity

Under **A the threshold is arbitrary and ours** — 30000 is a number that exists
only in our source file — and **nothing in the pipeline forces an AKAI sample to a
supported rate.** `build_sample` writes `sd.sample_rate` verbatim; `convert.py`
resamples only under `--max-sample-rate` or the KRZ-specific headroom path. So a
48 kHz source, which is most modern material, gets flag 1 and plays at 44100:
**147 cents flat, silently.** Under B the machine's own choice would be sane.

### CONFIRMED IN RAM, both directions, no disc needed

s3ked wrote byte 0x01 over SysEx on a **resident** sample, leaving SSRATE
untouched (it read 44100 / 22050 correctly throughout), and measured:

```
SSRATE 44100, byte 0x01 = 1  ->  300.0 Hz   baseline
SSRATE 44100, byte 0x01 = 0  ->  150.0 Hz   half speed
SSRATE 22050, byte 0x01 = 0  ->  300.0 Hz   baseline
SSRATE 22050, byte 0x01 = 1  ->  600.0 Hz   double speed
```

Model A confirmed, model B withdrawn. **The whole question was settled in twenty
minutes because the field is writable** — the disc had been built and never
needed to leave the desk.

**The transferable rule:** if a hypothesis is about a FIELD the protocol can
write, build the contradiction in the machine rather than on the medium. It is
faster, it is reversible, and control and test share every other condition
exactly. A disc is only necessary when the thing under test is the DATA itself,
or when the question is about what LOADING does.

### The field is one bit, and the machine does not validate it

Enum probe on a resident sample, values 0–7 and 255:

```
wrote   reads   f0        plays
    0       0   150.0 Hz  22050        even -> 22050
    1       1   300.0 Hz  44100        odd  -> 44100
    2       2   150.0 Hz  22050
    3       3   300.0 Hz  44100
  ...
  255     255   300.0 Hz  44100
```

**Rate follows bit 0 and nothing else.** No third rate, no silence, no hang, and
identical level (−15.8 dBFS) at every value, so nothing else in the sample path
reads the other seven bits either. **The supported set is exactly
{22050, 44100}.**

**255 was stored verbatim and read back as 255** — no clamp, no wrap, no error.
So on this machine *acceptance is not validation*, and a value reading back
correctly proves storage and says nothing about meaning. This is the second
instance from a different field (PMCHAN 22 was stored verbatim and clamped in
use), which makes it a property of the machine rather than a quirk of one byte.

### THE FIX, applied

* `writers/akai_s3000_writer.py` — `AKAI_PLAYBACK_RATES = (22050, 44100)`,
  `akai_target_rate()`, `akai_playback_rate()`. Byte 0x01 is now derived from the
  rate the audio **actually is**; the 30000 threshold is gone. `build_sample`
  warns, naming both supported rates, if handed anything else — it does not
  resample, because that is a processor's job and doing it there would hide the
  change from `--dry-run` and from the size accounting.
* `convert.py` — an AKAI playback-rate snap before the writer, running **after**
  `--max-sample-rate` and the vintage `--resample` profiles so a user's explicit
  choice is honoured first and only then made playable.

Verified end to end: a 48 kHz source now reports
`'tone48': 48000 -> 44100 Hz (unresampled it would sound -147 cents)` and writes
`SSRATE 44100, byte 0x01 = 1`. Full suite 417 passed.

`akai_target_rate` deliberately is **not** "nearest": nearest sends 32000 down to
22050 and lowpasses it to 11 kHz. Up to 44100 above 22050, 22050 at or below, so
no bandwidth the machine could have played is discarded and a low-rate sample is
not inflated fourfold on a 32 MB machine.

### The experiment that would have separated them (round-2 disc, superseded)

Round 1 never contradicted the two fields. Round 2 does:

```
F1 SR22050  PRGNUM 108  flag forced 1   A -> 600.0 Hz   B -> 300.0 Hz
F0 SR44100  PRGNUM 109  flag forced 0   A -> 150.0 Hz   B -> 300.0 Hz
```

An octave apart under A, identical under B. Corroborated by straddling **our**
threshold, which the machine has no reason to know about:

```
RATE 29999  flag 0   A -> 220.5 Hz    an octave of pitch across
RATE 30001  flag 1   A -> 441.0 Hz    2 Hz of stored rate
```

plus `48000` (the practical case, A → 275.6 Hz) and `16000`. The flag is patched
**after** `build_sample` rather than through a new argument, so the eight control
cases keep computing it exactly as production does.

**Read the measured f0 for 108/109, not `--check`'s verdict line** — it phrases
everything as honoured/not-honoured against `SSRATE`, which is the right question
for the other eight and the wrong one for those two.

### If A is confirmed

`build_sample` must stop writing an arbitrary threshold into a field that selects
playback rate. The fix is a real decision, not a constant: either resample to the
nearest supported rate at write time (correct pitch, costs a resample), or refuse
and warn. Either way `--max-sample-rate` stops being optional for AKAI output.

**Not yet checked:** whether `h[0x01]` also does what its comment says — a
bandwidth/anti-alias setting — in which case it is doing both jobs and the two
cannot be separated by choosing a different value.

## §AKAISDATA — we write 0 into the sample-data address; it is a real deviation with no effect (2026-08-18, CLOSED — COSMETIC)

**Found by doing what s3ked suggested:** diff a looped sample header against a
one-shot of identical length and identical PCM, and see what differs beyond
`SPTYPE` and the loop record. Ours differ in 10 bytes; **the machine's own saved
pair differ in 14** — and the four extra are `0x10` and `0x16`–`0x18`.

### The field

`0x16`–`0x18` is a little-endian **u24 sample-data address**. From the machine's
own `XCROSS 1` save, four samples of 882000 frames each:

```
NOISE W 1SHO   131072
NOISE P 1SHO  1013072    +882000
NOISE W LOOP  1895072    +882000
NOISE P LOOP  2777072    +882000
```

The advance is exactly the frame count. **We write 0 in every sample we produce.**

### The corpus is unanimous

12965 factory sample headers across 8 discs:

```
0x16-0x18 == 0     0        0.0%    <- what WE write, in 100% of ours
0x16-0x18 != 0     12965  100.0%
```

Rule derived from 5097 consecutive pairs, each hypothesis tested independently
rather than first-match (the first attempt cascaded through alignments and made
64 look like 42%):

```
delta == frames rounded UP to a multiple of 64     97.1%
delta >= frames                                    97.9%
```

The volume's first address is commonly `0x300100` or `0x000100` — a base plus
`0x100`.

`0x10` also differs: the machine writes **0 for a one-shot and 1 for a loop**,
where we write 1 unconditionally.

### THIS DOES NOT EXPLAIN s3ked's RULE, and saying so is the point

s3ked established that a **looped** program plays the sample loaded immediately
*before* the one it names, while one-shots are correct. If the machine simply
trusted our stored 0, every looped sample would play from the pool base — i.e.
all of them would play slot 0's audio. Checked against both observed load orders:

```
forward order,  slot 0 = W1S (white)   predicts 122 -> white    observed PINK
reversed order, slot 0 = PLP (pink)    predicts 123 -> pink     observed SILENT
```

It fails in both. So this is a **real deviation and a separate defect**, not a
demonstrated cause. Recorded that way deliberately: this is the third hypothesis
of the evening for §AKAILOOPCROSS and the previous two — the duplicate name, and
the zone pointer at `+0x16` — were both killed by measurement after looking
compelling. A 100%-versus-0% corpus split is the most striking evidence produced
all night, and it still does not predict the observation.

### MEASURED: a plausible address changes nothing

`SDADDR` and `SDZERO` are identical discs but for this field. Captured minutes
apart in one session:

```
            prg  names      SBADD   peak dBFS   period   sounding
SDZERO       94  LOOP 3S    36888       -71.7      --     SILENT
             95  LOOP 4S    36900        -8.5   4.000     its OWN
             96  LOOP 5S    36912        -7.9   5.000     its OWN
             97  LOOP 7S    36924        -8.0   7.001     its OWN
SDADDR       90  LOOP 3S    36888       -72.8      --     SILENT
             91  LOOP 4S    36900        -8.2   4.000     its OWN
             92  LOOP 5S    36912        -7.9   5.000     its OWN
             93  LOOP 7S    36924        -8.0   7.001     its OWN
```

Same periods to three decimals, same SBADD, same silence at slot 0. **The field
is written by every factory sample and read by nothing we can observe.** Closed
as cosmetic; the prediction above — that trusting a stored zero could not explain
the observations — held.

`0x10` (0 for a one-shot, 1 for a loop, where we write 1 unconditionally) is
still worth correcting for correctness against the machine's own example, and is
equally unlikely to change behaviour.

### What to do about it (superseded by the measurement above)

**Not simply "write the address".** The values are plainly RAM-pool positions:
the machine's own start at 131072, factory discs start at `0x300100`, and neither
is a disc-format constant. The machine must recompute them on load, or nothing
would ever load into a differently-filled pool. So the open questions are:

1. does the machine recompute unconditionally, in which case our 0 is harmless
   and this is cosmetic?
2. or does it recompute only for one-shots and trust the stored value for loops —
   which would tie this to §AKAILOOPCROSS after all, though not by the simple
   mechanism ruled out above?

**Cheap test, no crossing:** write a bench sample carrying a *plausible*
`0x16`–`0x18` (base `0x100`, advancing by frames rounded to 64) and see whether a
looped program that names it plays correctly. If it does, this is the bug and the
fix is to compute the field. `0x10` should be corrected regardless — writing "one
active loop" on a one-shot is wrong by the machine's own example and costs
nothing to fix.

## §AKAIAUXDEFAULT — `.X` and `.T` do not need decoding to be written correctly (2026-08-18)

§AKAIAUX has blocked type-0 volume support on *"deciding what to write into
`.X`/`.M3`/`.D`/`.T` — an aux file with invented contents is worse than an absent
one."* That framing assumed the choice was between decoding the formats and
inventing plausible values. **There is a third option, and the corpus supplies
it: reproduce what the machine itself writes.**

Measured across 45 specimens — the S3000XL's own saves (`VOLUME 001`,
`XCROSS 1`, `XCROSS 2`) plus six factory discs:

```
.T   160 bytes    45 specimens, ONE distinct content     -> a format CONSTANT
.X  7312 bytes    45 specimens, 9 distinct contents      -> varies with content
                  but the machine's own default (md5 dc6a0c4d) appears in
                  exactly the three machine-written volumes and nowhere else
.D   162 bytes    78 specimens, 2 distinct               -> already decoded
.M3 4096 bytes     3 specimens, 2 distinct               -> already decoded
```

**`.T` is invariant.** Every take-list file on every disc examined — the
machine's and the factory's — is byte-identical, 160 bytes with 34 non-zero. So
writing a correct one requires no understanding of it at all, only reproduction.
That is not a decode, and it should not be recorded as one; it is the weaker and
sufficient claim that the file does not vary.

**`.X` varies, but the right value for a volume WE create is not in question.**
A converted volume has no effects assigned, so the machine's own power-on default
is exactly right — and we have it, from three independently saved volumes that
agree.

### Why this is a real unblock rather than a shortcut

The objection §AKAIAUX raised was against *invented* contents, and it was
correct. Reproducing bytes the instrument itself wrote is the opposite of
invention: it is the same standard as the golden `akaiutil` hashes, or as
copying an existing volume, which we already round-trip byte-identically.

**What it does not buy:** any ability to write a *meaningful* effects file, or a
take list that reflects real takes. A user who wants effects still has to set
them on the machine. The claim is only that a volume we create will carry the
four files a type-0 save carries, with the contents the machine would have put
there itself, instead of lacking them.

### Implementation note, before anyone builds it

The blobs are ~7.5 KB together. They are machine-default configuration from
Jan's own instrument, not third-party library content, so embedding them is a
licensing non-issue — but they should be embedded with their provenance recorded
next to them (which machine, which OS version, extracted when and from which
volumes), because a default that silently belongs to one OS release is exactly
the kind of thing that ages badly and cannot be diagnosed later.

**Still genuinely undecoded:** what the fields inside `.X` and `.T` MEAN. This
section deliberately does not claim otherwise. `.X`'s nine distinct contents
across the corpus are the material for that decode whenever someone wants it,
and they are a far better starting point than the two identical specimens we had
this morning.

## §AKAIUNKNOWNDUP — the undecodable-record diagnostic multiplied across reads (2026-08-18, FIXED)

`_unknown_records` is module-level and, until tonight, only the **floppy** path
cleared it. Every hard-disk read therefore re-reported everything the previous
reads had found: sweeping N images printed each finding N, N-1, N-2 … times.

```
before   read #1 of one image -> 9 lines   #2 -> 18   #3 -> 27
after    read #1 -> 9          #2 -> 9     #3 -> 9
```

**The cost was not the noise, it was a number.** A corpus sweep counted those
lines and derived "4267 skipped records across six discs, a 36.5% loss rate",
which sent an investigation after a reader fault that does not exist — three
separate probes, one of which also mistook 3707 empty directory slots for
dropped content because an all-zero name decodes as `'000000000000'` in the AKAI
charset. **A duplicated diagnostic is worse than a missing one: it is
quantitatively believable.**

### What the corpus actually shows, once counted correctly

```
disc 1   read 2458   skipped    9  ( 0.4%)   1350B x4, 2550B x3, 3150B x2
disc 2   read 1936   skipped  100  ( 4.9%)   162B x100
disc 3   read  522   skipped    2  ( 0.4%)
disc 4   read  580   skipped 4155  (87.8%)   249982B x57, 543402B x50, ...
disc 5   read  519   skipped    1  ( 0.2%)
disc 6   read 1396   skipped    0  ( 0.0%)
```

**It is not a 36% loss spread over the corpus — it is one disc in six that we
largely cannot read**, plus a small tail elsewhere. That is a completely
different problem from the one the bad number described, and a far more
tractable one: a single disc to study rather than a systemic reader fault.

* **disc 4** — 87.8% undecodable, and the sizes are *sample-sized* (250 KB,
  543 KB). Something about that disc's authoring is not handled at all.
* **disc 2** — 100 records of exactly **162 bytes**, which is the `DRUM INPUTS.D`
  size. On that disc the aux files carry type `0x00` where elsewhere they carry
  `0x64`.
* **disc 1** — 9 records at 1350 / 2550 / 3150 bytes, all multiples of **150**,
  which is the S1000 program block size rather than the S3000's 192.

The existing decision not to *decode* unknown records stands and is well argued
where it sits: reading a record of unknown layout is how a parser invents data.
This section only corrects what is being counted.

## §ASKFORDEFINITIONS — the two corrections that came from questions, not measurements (2026-08-18)

Seven claims were corrected on 2026-08-18. Five fell to measurements. **Two fell
to someone asking what a phrase meant**, and both were later and cheaper than
they needed to be.

```
"a caveat in a docstring does not defend against a printed number"   measurement
"the block codes are slot-relative"                                  measurement
"the loop plays 11% fast"                                            measurement
"the duplicate name caused the crossing"                             measurement
"the sample-data address is the cause"                               measurement
"a looped program plays the sample before the one it names"          QUESTION
"positional, not ordinal"                                            QUESTION
```

The last one is the clearest case. Nothing about *"positional, not ordinal"*
looked shaky: it had a confirmed hardware measurement under it, it had survived
review by both projects, and it was written into four files across two
repositories. Jan asked **what "a looped sample at the pool base" meant** — not
whether it was true — and the phrase did not survive being made precise. Stating
it exactly revealed that both properties had moved together in every test, and
that the machine's own address assignment makes them inseparable by construction.

**Why a request for a definition is a sharper instrument than a request for
evidence, and why it gets asked less:**

* It costs the asker nothing. They need no competing hypothesis, no data, and no
  standing in the argument — only the observation that they cannot restate the
  claim in their own words.
* **It cannot be deflected by pointing at the data**, which is the usual escape
  for a claim whose evidence is real but whose wording overreaches. Both of these
  claims had genuine measurements behind them; the measurements simply did not
  support the sentence that had been built on top.
* It is uncomfortable to ask between people who both know the material, because
  it can read as not having followed. That is precisely why neither project
  asked it of the other all day: **both asked for evidence, and evidence was
  always available.**

s3ked's summary, which belongs here in their words: *"a confound dressed as a
control"* — the test built to discriminate the two properties moved both together
and discriminated neither.

**The practice to adopt:** before a finding is written into a notes file, restate
it in one sentence without reusing any of its own terms. A claim that cannot
survive that has a definition problem, and no amount of confirming data will
surface it.

## §AKAILOOPSEM — our loop convention is the reverse of the factory one (2026-08-18, ESTABLISHED; NOT the cause of the silence)

Offsets validated against a file where every value is known (`0x1a` SLNGTH,
`0x22` play end, `0x26` LOOPAT1, `0x2c` LLNGTH1) — not another offset error.
Across **16493 factory S3000 samples with a real loop**:

```
LLNGTH <= LOOPAT                    98.6%
LOOPAT + LLNGTH <= SLNGTH           11.2%     <- what OUR writer assumes
```

Under our reading — `LOOPAT` is where the loop begins and `LLNGTH` is how long it
runs — **89% of all factory loops would run off the end of their own sample.**
Under the reading that `LOOPAT` is the point *at which it loops* and `LLNGTH`
measures backwards from there, 98.6% are consistent. The name is suggestive too:
"loop at" reads as a point, not a start.

### RESOLVED, and the first framing above was too crude

**The backwards-semantics hypothesis is REFUTED by a positive control that was on
disk the whole time.** Every loop that demonstrably played its own period on
hardware — `SDZERO`'s and `PARTLOOP`'s, measured at 4.000 / 5.000 / 7.001 s and
corr 0.97+ — carries:

```
LOOPAT 0,  LLNGTH 176400,  SLNGTH 352800
   LLNGTH <= LOOPAT          False
   LOOPAT + LLNGTH <= SLNGTH True     <- our model, and it WORKS
```

s3ked's point that the experiment had **no positive control** was exactly right,
and supplying one needed no hardware at all: a loop known to work was sitting in
an image on this disk.

**What the corpus actually shows is a different convention, not a wrong one:**

```
LOOPAT within 1% of SLNGTH   82.9%
LOOPAT 90-99% of SLNGTH       9.6%
LOOPAT 50-90%                 5.6%
LOOPAT below half             1.9%
```

**In factory material `LOOPAT` sits at the END of the sample and `LLNGTH` runs
back from it** — the loop is the sample's tail, which is what a sustain loop is.
We write `LOOPAT 0` with the length running forward. Both evidently play (ours
do, away from the pool base), but they are opposite conventions, and ours is
shared by roughly 1% of factory samples.

`SLNGTH` at `0x1a` was validated against **18293 factory samples, 100% matching
`(filesize - 192) / 2`**, so none of this rests on an unchecked offset.

### What this does and does not explain

**It does NOT explain the silence.** Our loops work at non-base positions with
this exact convention, so the convention alone is not the fault. Recorded as a
compatibility finding, not a cause — and the temptation to make it the cause is
precisely what eight withdrawn rules today should inoculate against.

**It is still worth acting on eventually**: writing loops the way 92% of factory
material does is more likely to be right in cases we have not tested, and it
costs nothing but arithmetic. Not tonight, and not without a hardware test.

### Deliberately NOT acted on, and the reason matters

Eight claims were stated and withdrawn on 2026-08-18. This one has the same shape
as the last three that died: a clean corpus number, an obvious mechanism, and no
test. It is also **not sufficient on its own** — `SDZERO`'s loops carried
`LOOPAT 0` and played their own periods to three decimals at non-base positions,
which a straightforwardly backwards loop record would not do.

**Two probes would separate it from the pool-base story, neither needing a disc:**
the same `loop_start` sweep on a sample that is *not* at the pool base, and one
probe with `LLNGTH` set smaller than `LOOPAT` so the loop-END reading is actually
satisfiable. Both are SysEx writes on a resident sample.

### A correction to the sweep that produced this

The `loop_start = 132300` capture was read as "SUSTAINS" from its 7.95 s in a 9 s
recording. Measured directly: active region **8.00 s — the whole sample — and no
autocorrelation peak above 0.35 anywhere between 0.2 s and 9 s.**

```
loop_start      0 / 1 / 64 / 512   active 0.05-0.06 s
loop_start   4410                  active 0.15 s
loop_start  22050 (0.500 s)        active 0.56 s   no period
loop_start  44100 (1.000 s)        active 1.03 s   no period
loop_start 132300 (3.000 s)        active 8.00 s   no period
```

**In none of the eight probes did the sample ever loop.** Duration tracks
`loop_start` and then the whole sample plays once, but nothing repeats anywhere.

That is the same failure as reading "it made a noise" for "it played correctly",
one level up: *it played for a long time* is not *it sustained*. Only a period
measurement separates them — and the tooling for that was built this evening and
not pointed at this capture.

## §AKAILOOPAT — LOOPAT1 is the loop END; we wrote the loop START into it (2026-08-18, FIXED)

**The real bug, found by asking whether it would be documented rather than by
measuring it.** Jan's question — *"wouldn't something like that be in a manual?
that's such important information for someone working with the device"* — took
about fifteen minutes to answer and settled what a day of hardware work had not.

`LOOPAT1` (0x26) is the **end** of the loop. `LLNGTH1` (0x2a fine + 0x2c coarse)
runs **backwards** from it. The loop is `[LOOPAT - LLNGTH, LOOPAT]`. Our writer
put `loop_start` there and our parser read it back the same way, so both halves
were consistently wrong and the round-trip test passed.

### Four independent confirmations

1. **The S3000XL manual:** *"when playback reaches this point, it will go back to
   the point determined by the field described below and will loop either for as
   long as the time: field is set or for as long as you hold the note(s) if HOLD
   is selected."* — playback *reaches* the point and goes *back*.
2. **The corpus.** Across **16493 factory S3000 loops**, `LOOPAT` sits within 1%
   of `SLNGTH` in **82.9%** and within 10% in 92.5% — at the sample's END, where
   a sustain loop ends. Under the start reading, **89% of factory loops would run
   off the end of their own sample**, which was visible all along and never
   questioned because nothing depended on it being sensible.
3. **ConvertWithMoss**, an independent implementation: the accessor is
   `getEndMarker()`, docstring *"Get the end of the looped region (not the
   start!)"* — the exclamation mark is theirs, which suggests we are not the
   first to walk into it.
4. **Its converter:** `setStart(marker - coarseLength); setEnd(marker)`.

### It retro-explains the entire evening

Every probe in s3ked's sweep carried `LLNGTH 220500` with `LOOPAT` below it:

```
LOOPAT      0 -> loop [-220500,      0]   invalid
LOOPAT   4410 -> loop [-216090,   4410]   invalid
LOOPAT 132300 -> loop [ -88200, 132300]   invalid
```

**All ten probes asked for a loop starting before the sample begins**, which is
why not one of them ever looped, and why duration grew with `LOOPAT` — the end
marker was moving, so there was progressively more sample to play before reaching
an unusable loop record. s3ked's instinct that the experiment had *no positive
control* was exactly right, and stronger than they put it: there was never a
valid loop record among them.

It also plausibly subsumes the silence, the degraded audio and the pool-base
story: a loop whose start is negative, behaving differently depending on where
the sample sits in memory, is precisely the kind of fault that looks positional.

### The fix, and what it validates

Writer and parser both corrected; the round trip is now exact at both ends rather
than losing a frame to a documented "bounded inconsistency between two
conventions" — that inconsistency was the bug. Factory loops now parse as sustain
loops occupying the **last 12–25%** of their samples, which is what a sustain loop
is; under the old reading they began at 99% and ran past the end.

### HARDWARE-CONFIRMED 2026-08-18

```
LOOPAT 220500  LLNGTH 44100  SLNGTH 352800   (both read back before playing)

vs the FORWARD region [220500, 264600]   +0.0412   noise floor
vs the END     region [176400, 220500]   +0.7998   MATCH
references orthogonal after resampling:   0.0032
```

**The machine played `[LOOPAT - LLNGTH, LOOPAT]`.** Documentation, corpus and
ConvertWithMoss all agree with the measurement.

**A trap s3ked caught in the correlation:** the references are 44100 Hz and the
captures 48000 Hz. The sampler plays in real time, so a 1.000 s loop is 48000
frames in the capture and 44100 in the reference — correlating them raw compares
different time scales and returns noise for *both*, which would have read as "it
matches neither". They resampled the references first and **re-checked
orthogonality afterwards (0.0032)**, so the resampling could not have
manufactured the discrimination.

**Open oddity, deliberately not explained:** the capture has no periodicity —
self-similarity max 0.0407 across 0.3–9 s where a 1.000 s loop should peak at
1.000. It sustained 13.95 s and contains the end-region audio, matching at one
lag rather than repeatedly. That may be the analysis window, or the same
"sustains but does not repeat" behaviour the out-of-range probes showed. Recorded
as an observation, not a theory.

### Documentary support was NOT hardware evidence, and I nearly merged them

The manual, the corpus and ConvertWithMoss are three independent statements of
the semantics and they stand. A **hardware measurement distinguishing the two
readings does not exist**, and the first attempt at one was worthless.

That test — mine — set `LOOPAT = LLNGTH` and expected a 5.000 s loop. It
sustained at 5.000 s, and proves nothing: **the period is `LLNGTH` under either
reading.** The only thing making it look decisive was an assumption that the
forward arrangement would be *rejected* as out of range — on a machine that has
not validated a single field all night. *Acceptance is not validation* was
established hours earlier and then leaned on backwards.

**A test whose two hypotheses predict the same observation is not a test.** The
check costs one line: write down what each reading predicts, before running.

s3ked's control is the data that matters:

```
LOOP 4S  LOOPAT 0  LLNGTH 176400  ->  4.000 s
LOOP 5S  LOOPAT 0  LLNGTH 220500  ->  5.000 s
LOOP 7S  LOOPAT 0  LLNGTH 308700  ->  7.001 s
```

With `LOOPAT 0` the END reading gives `[-LLNGTH, 0]`, invalid — yet these loop
correctly. So either the machine clamps a negative start to 0, collapsing both
readings onto identical behaviour, or the END reading is wrong. **Every working
loop we have ever produced sits exactly where the two cannot be told apart.**

**The discriminating test is content, not period:** `LOOPAT 220500, LLNGTH 44100`
puts the loop at 5.0–6.0 s under one reading and 4.0–5.0 s under the other.
References regenerated from the sample's own seed and verified against the disc
at **correlation 1.000000**; the two candidate regions cross-correlate at
**0.0018**, so a capture can match only one. Checked before proposing the test
this time.

**Also new:** `LOOPAT 352800` — exactly `SLNGTH` — does not loop while 220500
does, which reads as an off-by-one at the top end if the field is an offset.

**Still to confirm on hardware:** one write, on material already resident — set
`LOOPAT = LLNGTH` on the silent `SOLOLOOP` and it should sustain with a 5.000 s
period. That would be the first working loop produced by writing header fields.

### The lesson

Nine claims were stated and withdrawn on 2026-08-18, every one of them about the
*symptom*. The cause was in a public manual, in an open-source converter, and
implicit in a corpus sitting on this disk — and none of that was consulted until
somebody asked whether a thirty-year-old sampler's loop behaviour might be
documented somewhere. **Check what is already known before measuring**, which is
the same lesson as the corpus and the readback arriving a fourth time.

## §LOOKITUP — why two sessions ground for six hours on something that was written down (2026-08-18)

Jan's question after the fact: *"I am just a bit puzzled that two Claude Opus
instances would grind on this for hours, without looking left or right and using
knowledge sources available at hand (documents, CWM repo)."*

It is the right question and the answer is not flattering. Four causes, each
individually reasonable, which is what made it survive.

**1. The reverse-engineering frame carries a hidden premise.** This project's
identity is decoding undocumented formats; `docs/AKAI_S3000_FORMAT.md` says
"reverse-engineered" at the top. That frame quietly asserts *the information is
not written down*, and once accepted it stops the question being asked. It was
false here: the S3000XL manual describes the loop behaviour in plain English.

**2. The bench loop was self-reinforcing.** Hardware, a disc pipeline and a peer
to argue with meant building and measuring were the *available* actions, so they
became the method. Each round produced a clean-looking result on schedule, which
felt like progress and was nine wrong answers.

**3. Mutual verification produced false confidence.** Two sessions checked each
other hard and generated seven corrections — all within the same evidence base.
**Rigorous peer review of a closed system does not detect that the system is
closed; it increases confidence in what is inside it.**

**4. The reference implementation was already known and not consulted.** There is
a standing crosscheck note recording the last ConvertWithMoss commit diffed
against this project. It is checked out locally. `AkaiS1000SampleLoop.java`
answers the question in a docstring — *"the end of the looped region (not the
start!)"* — whose exclamation mark suggests its author hit the same trap and left
a warning. It went unread because the problem had been framed as *ours to
measure*.

### The rule

**Before building anything to answer a format question, spend ten minutes on
what is already known:** the device's own manual, the corpus already on disk, and
any independent implementation available locally. That is a lookup, not research,
and it is cheap enough that skipping it can only be a framing error.

The same lesson arrived four times on 2026-08-18 from four directions — the
corpus refuting a rule, the readback closing in ten minutes what three discs
could not, a positive control sitting in a build artefact, and finally the manual
— and each time it was recorded as a local insight rather than as the general
one. **Check what is already known before measuring.**

## §AKAIRELTEST — the release test, and the artefact that was my own disc (2026-08-18, PASSED)

A bank converted by `convert.py` from an SFZ source — deliberately not a bench
generator — written to a volume, bulk-loaded from the front panel the way a user
would, and played.

```
key 60  RELLOOPA  8 s sample, loop [1.00, 3.00]  period 2.000 s   at the POOL BASE
key 61  RELLOOPB  8 s sample, loop [1.00, 6.00]  period 5.000 s
key 62  RELLOOPC  9 s sample, loop [1.00, 8.00]  period 7.000 s
```

**All three loop correctly, including key 60 at the pool base — the case that was
silent before the `LOOPAT` correction.** No clicks, no silence, no drift over
15 s. That is the release gate.

### The one artefact, and it was the test disc

Jan heard a level change on key 60 only. Measured from the captures:

```
rel_60   -16.5 dB for 2.0 s, then -19.55 dB flat for 13 s   (step -3.1 dB)
rel_61   -19.5 dB flat throughout
```

Cause:

```
keygroup 0  keys 60-60
    zone1: RELLOOPA   vel 0-127
    zone2: RELSHOT    vel 0-127      <- both fire on key 60
```

The SFZ gave `RELSHOT` `key=60`, colliding with `RELLOOPA`. The converter
faithfully produced two full-velocity zones and the machine correctly **layers**
them. Two equal incoherent noise sources sum to **+3.01 dB**, and `RELSHOT` is
**2.00 s** long — so the step's magnitude and its timing are both predicted
exactly. Neither the converter nor the sampler did anything wrong.

### Two wrong hypotheses, and where the answer actually was

* s3ked's: the source's first 1.25 s is louder. Refuted — regenerating
  `RELLOOPA` gives **+0.01 dB** across that boundary.
* mine: a loop-seam artefact, since `RELLOOPA` wraps most often. Refuted by the
  envelope: the step happens **once** and never recurs at 2 s multiples.

**The answer was in the disc's own keygroup table, checkable offline in one
command** — the fourth time in a day that the evidence was already held. And it
was missed once more for the same reason as the afternoon's PARTLOOP confusion: I
read **zone 1** of each keygroup and stopped. Zones 2–4 existed, and zone 2 was
the answer. A partial read of a structure is not a read of it.

### CONFIRMED BY REMOVAL, not by fit

Zone 2 was silenced on the **resident** program (velocity 0-127 -> 1-0, the
machine's own idiom for an unused zone, read back before playing):

```
key 60 held 10 s:  first 1.5 s -19.40 dBFS,  after 2.5 s -19.48 dBFS
                   step +0.08 dB   (was -3.1 dB with zone 2 live)
                   sd 0.089 dB, and Jan confirms by ear: "it's gone"
```

Prediction was "flat at about −19.55, no step at 2.0 s, matching key 61". All
three held, and the step is not merely smaller but **at the noise floor of the
measurement**.

**Three explanations were offered for one 3 dB step and two of them fitted the
data when proposed.** The seam theory and the source-is-louder theory were both
consistent with everything known at the time; the layering theory won because it
predicted that *removing a specific zone would remove the step*, and because
somebody insisted on performing that removal instead of admiring the fit. Jan
asked for it to be confirmed rather than explained — the second time that day the
step from "this accounts for it" to "this predicts something I can switch off"
came from outside the two sessions doing the work.

### And the conventions checked against the corpus, which corrected this row

```
lowest PRGNUM per factory volume:  0 in 2366 of 2408 volumes   (98.3%)
PMCHAN 255 (OMNI):                 3 of 11410 programs         ( 0.03%)
```

**PRGNUM 0 is normal**, so the boot-program stack noted below is ordinary AKAI
behaviour rather than our deviation — that half of the concern is withdrawn.
**OMNI is not normal**: we wrote it on 100% of programs and factory material
essentially never does.

**Tested before changing, and it is not broken.** A 21-program converted volume
(`VF NEW`) was bulk-loaded and program change still selected correctly —
unrelated programs correlating at 0.002, PRGNUM 3 sitting 4 dB below 0 and 1,
and "as loaded" measuring the same level as a single selection rather than the
~+13 dB that 21 simultaneous programs would give. So nothing stacks and
selection works.

**Changed anyway, for a reason the single-channel test cannot show:** omni means
every program answers every part, so a converted volume in a MULTI puts every
program on every part, and nothing in a program list looks wrong. The default is
now `PMCHAN 0`:

```
factory volumes with 2+ programs, all on channel 0   1545
the same using 2 or more different channels           ~35
factory programs using OMNI            3 of 11410   0.03%
```

And the machine agrees with the corpus: `test_only_two_bytes_differ_from_the_real_machine`
had recorded for months that *"we write 0xff (MIDI omni); the machine holds 0"* —
the disagreement was written down and nobody asked which side was right. It is
now one byte, not two.

### Carried forward as the top open AKAI item

`TEST PROGRAM` survives every CLR and sits on **PRGNUM 0**; our converter also
writes **PRGNUM 0 with PMCHAN 255 (OMNI)**. They stack. s3ked moved the boot
program to 100 before capturing — and said so, which is the only reason this
capture is interpretable — but **a user loading a converted volume gets that
stack with whatever their boot program is.** That is ours, not the machine's.


## §PRESETORDER — preset order and program numbers survive the trip

Two TODO rows, one theme: **the number a user dials to hear a converted preset
should be the number the source had.** Found 2026-08-19 while building the
hardware test set, because the sheet put source and output numbers in adjacent
columns and they did not line up.

### 1. Restore source order within each target bank (E4B, and every writer)

`writers/bank_splitter.py:749`:

```python
all_items.sort(key=item_size, reverse=True)   # First-Fit Decreasing
```

Keep it. FFD is the right way to decide *which* bank a preset lands in, and
the packing quality is why it is there. What is wrong is that the packing
order then becomes the *written* order, including in the overwhelmingly common
case where everything fits one bank and no packing decision was made at all.

The fix is at the end of packing, not in the sort: remember each preset's index
in its source bank, and sort each `TargetBank.presets` by it before writing.

```python
# before packing
for i, preset in enumerate(source_bank.presets):
    preset._src_order = (source_bank.name, i)
...
# after packing, per target bank
tb.presets.sort(key=lambda p: getattr(p, '_src_order', ('', 0)))
```

Bank *assignment* is untouched, so every existing size/limit test keeps its
result; only the order inside a bank moves. Sorting by `(source_bank, index)`
keeps a multi-source conversion grouped by source rather than interleaved.

**Test:** convert a 7-preset bank that fits one bank and assert the output
preset names equal the input's, in order. That test fails today.

**Do not do this without also re-issuing the hardware test set** — the workbook
`~/temp/mpc2emu_hw_testcases.ods` records the numbers as built on 2026-08-19,
and a renumbering would silently invalidate every remark filled into it.

### 2. Honour K2000 object ids in `krz_writer`

The parser side is already done (2026-08-19): `_parse_program_object`'s call
site now carries `obj['id']` into `Preset.program_number`. Object ids are what
the K2000 dials — 200, 201, … for user objects, below 200 for ROM.

`krz_writer` assigns sequentially from 200 regardless. Apply the policy
`akai_s3000_writer` already uses for PRGNUM, and which is documented there at
length: **use the source's own numbers when they are distinct and in range,
fall back to positional when they are not.**

```python
_wanted = [getattr(p, 'program_number', 0) or 0 for p in bank.presets]
_usable = (len(set(_wanted)) == len(_wanted) and all(v >= 200 for v in _wanted))
```

`>= 200` and not `> 0`: an id below 200 addresses a ROM object on the K2000, so
a source that numbers from 0 (any non-KRZ input, since only the KRZ parser sets
this) must take the fallback rather than write ids that collide with ROM.

**Test:** parse a KRZ whose programs are 202..210, write it, re-parse, assert
the ids come back 202..210 — and a second case from an E4B source, asserting
the fallback still produces 200, 201, ….

### Why neither was done the night it was found

Both are small and neither is blocked. The test set built that evening carries
the current numbering in a workbook Jan is filling in by hand at the machines;
changing the numbering while that is in flight would mean every remark points
at a program that has moved. Fix both, then rebuild the set and re-issue the
workbook in one step.


## §AKAIATTACK — the attack we throw away, and the first law anyone has offered for it

`akai_env_bytes()` computes decay, sustain and release from the source and then
returns `_AK_FIXED_ATTACK = 0` for the attack. Deliberate: s3ked's varying-span
test found the attack stage fits neither a rate nor a duration, and inventing a
law is how the AKAI tuning field went 100x out.

**What was never measured is what the default costs.** On Jan's own E4B
material: 39 voices, every one with an attack over 10 ms, five over half a
second, the longest **6.554 s**. All 39 are written instant. The largest hole in
our AKAI output is a parameter we decided not to guess at, which is the right
decision producing a bad outcome — the fix is to measure, not to relax the rule.

### The candidate law

ConvertWithMoss derived one accumulator model from S1000 firmware v4.40 for all
three stages of both envelopes:

    time = ENVELOPE_FULL_SWING / (ENVELOPE_RATE[99 - setting] * 44100)
    ENVELOPE_FULL_SWING = 32767 * 128        # their emulator's accumulator width
    ENVELOPE_RATE spans 16384 .. 1 over the 100 settings

They flag the accumulator width as the one part the OS does not state, taken
from an emulation — so the RATIOS between settings are firmer than the absolute
times. Our own measurements already agree with the shared table on the other
five stages to within 1.2% (DECAY1 0.09776, RELSE1 0.09683, ATTAK2 0.09703,
DECAY2 0.09844, RELSE2 0.09692 against a predicted 0.09802), which is what makes
the model worth testing on attack. **ATTAK1 is the one stage that disagrees:
s3ked fit 0.10844, +10.6% off.**

### The test, which needs no disc

Set ATTAK1 over SysEx on a resident sample and measure time to peak:

    ATTAK1     predicted
        40       0.146 s
        60       1.045 s
        80       7.316 s
        90      19.021 s
        99      47.553 s

Over two decades between 40 and 90, so order of magnitude is enough; precision
is not needed to kill a wrong law.

**Run ATTAK1 99 first.** It is the cheapest falsification available: if a held
note reaches full level in much under 47 seconds, the linear-accumulator model
does not describe the attack stage and the +10.6% anomaly is explained.

**Two traps, both from s3ked's own record.** Gate on absolute level before
believing any time-to-peak — a note that never rises yields a confident number
from noise, and at ATTAK1 90 you wait 19 seconds to discover it. And do not fit
the exponent globally: an ill-conditioned fit landing near 0.098 would
"confirm" the shared table and close the question the wrong way, which is
exactly how their pole count came back as N = 3.12.

### If it holds

Replace `_AK_FIXED_ATTACK` with the same `_rate_law_value()` inversion the other
stages use. Note the attack travels from silence to peak, so its span is fixed
rather than sustain-dependent — simpler than decay and release, not harder.


## §AKAIRATEREAD — the reader takes SSRATE, the writer trusts byte 0x01

Our writer acts on §AKAIRATEQUANT: byte `0x01` selects the playback rate and
SSRATE at `0x8a` is descriptive. `akai_s3000_parser.py:207` does the opposite —
`rate = _u16(data, 0x8a) or 44100` — so the two halves of this project disagree
about which field is real.

Measured over 19 340 sample headers on 43 factory discs:

* **SSRATE == 0 in exactly 1.** The 0 Hz case ConvertWithMoss fixed (commit
  c5df170d, 2026-08-20, independent work — they hit it on machine-recorded
  material) barely occurs on library CD-ROMs, so our `or 44100` fallback is not
  causing visible damage today.
* **4242 headers (22.0%) carry a nonzero SSRATE that contradicts byte 0x01**:
  1538 have index 1 (44100) with SSRATE 22050, and 1290 declare 48000, which the
  machine cannot play at all.

Under our own reading those 4242 play at the rate the index picks, an octave
from what we read.

### What is actually unknown

**Which field the machine honours for a sample loaded FROM DISK.** s3ked
measured a RESIDENT sample by writing `0x01` over SysEx; that does not settle
the load path, and the machine may well rewrite one field from the other on
load. Note also that **all 5331 `.S1` headers carry index 1**, so the byte may
carry no rate meaning at all in the S1000 generation — in which case the reader
is right for S1000 files and wrong only for S3000 ones.

### The test

Build a volume with two samples whose index and SSRATE deliberately contradict
(index 0 / SSRATE 44100, and index 1 / SSRATE 22050), load it from disc, and
play both. An octave separates the two readings, so one note settles it. Do NOT
write the fields over SysEx for this — the whole question is what the LOAD does.

Until then, do not "fix" the reader to prefer `0x01`: on this corpus that would
change the read rate of 22% of all samples on the strength of a measurement
taken through a different path.

### The generation constrains the fix, whatever the disc says

s3ked flagged the S1000 question after §142; measured here over the **whole**
disc corpus rather than the twelve discs of the first pass:

    .S1   byte 0x01 == 1 in 35 990 of 35 990 headers   (0.00% at 0)
    .S3   byte 0x01 == 1 in 17 332, == 0 in 961        (5.25% at 0)

**The byte does not vary at all in the S1000 generation.** A field constant
across 35 990 specimens carries no information, so on `.S1` files it cannot be
read as a rate selector — and 1503 of those headers declare SSRATE 22050 while
the index says 44100, so preferring the index there would read every one of
them an octave high.

Cost of a naive "prefer 0x01" fix, per generation:

    .S1   3242 of 35 990 samples change read rate   (9.0%)
    .S3   3744 of 18 293                            (20.5%)

**So the fix must be generation-aware whatever the disc returns**, and the disc
can only speak for S3000 — it is an S3000XL, and §139 showed this family shares
a protocol without sharing its hardware.

One consistency check worth keeping: ConvertWithMoss hit the index byte varying
on **machine-recorded** S1000 material (SSRATE 0 for 22050 recordings). Our
corpus is entirely library CD-ROMs, mastered at 44100, which is exactly where a
constant 1 would be expected. The two observations do not conflict; they say the
byte is meaningful on S1000 but exercised only outside our corpus.

### The disc also carries an attack check, and why it belongs here

s3ked raised it and it is the same question wearing different clothes: **every
attack measurement on their side was made by writing the field over SysEx into
a resident program.** So was the filter law, the level scales and the tuning
constants. If a disk load can transform one header field, assuming it leaves
the envelope fields alone is the assumption this section exists to doubt.

`RR5`/`RR6`/`RR7` therefore carry ATTAK1 72/85/96, written by our own converter
from source times of 0.5 / 2.0 / 6.554 s — so the check tests the load path and
the writer's conversion in one note. Predicted t90 is 0.45 / 1.82 / 6.01 s
against `0.000201173 * exp(0.10844 * ATTAK1)`, and reading ATTAK1 back after
the load settles the load-path half directly.

**The failure this defends against is quiet.** A sign error in the conversion
gives every program an instant attack — which is exactly what the old fixed
default gave — so the disc would sound like a clean conversion of a bank that
happened to have no attacks. Nothing about it would look wrong.


### Outcome, 2026-08-20 — the candidate law is dead and ours is confirmed

s3ked ran the test the same afternoon (§141, `e47955c`). Resident sine, SUSTN1
99 so the note holds at full, V_LOUD 0, note-on to 90% of plateau:

    ATTAK1   measured t90   CWM predicts   ratio
        70          0.320          2.797    0.11
        80          1.060          7.316    0.14
        90          3.140         19.021    0.17
        99          8.600         47.553    0.18

**The free falsification named above was the one that landed**: ATTAK1 99
reaches full level in 8.6 s, not 47.6. The linear-accumulator model is roughly
7x too slow for the attack stage throughout. It remains the best available
account of decay and release, where it agrees with our measurements to 1.2% —
so this is a limit on one stage, not a refutation of their firmware reading.

Our own law fits, including outside its fitted range: against
`0.9 * 0.000201173 * exp(0.10844 * ATTAK1)` the ratio is 0.982, sd 0.06, with
ATTAK1 99 at 1.033 despite the fit running only 55..90. Reproduced here
independently before wiring.

**The shape test is the part worth keeping**, because it needs no law:

    t50/t90:   linear ramp 0.5/0.9 = 0.556      exponential ln2/ln10 = 0.301
    measured (ATTAK1 70..99):  0.500  0.547  0.548  0.558

A ratio of two numbers from one capture cancels the level calibration, the
plateau definition and the entire rig, so it identifies the amplitude attack as
a linear ramp independently of whether any constant is right.

Below ATTAK1 70 the times collapse into the 20 ms analysis window and are
floor-limited. Recorded as unmeasurable, **not** as disagreement.

### Why it was broken — corrected, because the first account was wrong too

The writer's justification quoted s3ked **§29**, "attack fits neither a rate
nor a duration". That was true when written, and **their §31 withdrew it the
same day**: four models fitted per curve identified the amplitude attack as a
linear ramp, and a linear-in-amplitude ramp read on a dB axis is a *curve*, so
a slope taken from its middle depends on how far the curve extends. The
span-dependence was the detector. §31 states in as many words that `ATTAK1` is
a genuine duration, and gives a law.

So we cited the **right field** and a **superseded version** of the finding.
Verified against their `docs/RESOLUTION_NOTES.md` here rather than taken on
report.

**The first version of this section said something else** — that the
justification quoted the `ATTAK2` finding against `ATTAK1`, a field mix-up.
That account came from s3ked, who withdrew it within the hour after opening
their own section, having produced it (their words) *"while writing up a
section whose entire subject is correct facts attached to wrong objects"*. The
fields were never confused. It is recorded rather than deleted because the
wrong story was tidier than the true one — two field names differing by one
character is a better story than a nine-day-old citation — and tidier stories
survive review.

While correcting it I found a **second stale citation of the same §29** in the
same comment block, this one attached to `ATTAK2`: it said the filter attack
fits neither a rate nor a duration, when §31 settles its *shape* and leaves
only its **depth-scaling** open (the same value reads 0.38 s at MODVFILT1 25
against 1.14 s at 18). `ATTAK2` stays unwired either way, but for the true
reason now.

### The rule this yields, which is about time and not fields

**A finding quoted across a project boundary must carry when it was true.**

An append-only investigation log is mostly intermediate states, written in the
same voice as the conclusions. §29 does not announce that it is about to be
superseded, because at the time it was not. A reader who does not read *forward*
from a section cannot distinguish a retracted step from a settled one — and a
consumer in another repo, who receives sections quoted rather than the file,
cannot see it at all. **A section number alone is not a citation**; a
superseding section can exist and usually does.

Note also that the constants moved without the section being retracted: §31's
law is `0.000150326 * exp(0.11175 v)` and §141's refit is `0.000201173 *
exp(0.10844 v)`. They agree to 2.5% at ATTAK1 80, so nothing was wrong — but a
citation of §31 alone would now be quoting superseded constants from a section
that still stands.

This remains the fourth instance in two days of a correct fact attached to the
wrong object; only the *object* here is a moment in time rather than a field or
a sample. **Not one of the four was a calculation error.** The countermeasure
has not changed and was not applied by either of us: go and read the source.
Restating the rule is not the same as following it.


## §AKAIENV2 — the filter envelope: measured for eight days, unwired for two stale reasons

`_keygroup` writes fixed defaults for `ATTAK2`, `DECAY2`, `SUSTN2` and
`RELSE2`. Audited 2026-08-20 against s3ked's `s3k/scales.py` — their
authority, not their prose — and **every time stage has current, non-provisional
constants** for a full 0..99 traverse:

    ATTAK2  0.001363 * exp(0.09703 v) s   40..85   r2 0.99981
    DECAY2  0.002464 * exp(0.09844 v) s   40..80   r2 0.99997
    RELSE2  0.001344 * exp(0.09692 v) s   40..80   r2 0.99998

Both reasons this project gave for not wiring them were false:

**"ATTAK2's depth-scaling is open"** — §28's numbers, retracted by **§58** on
2026-08-12. The threefold spread (0.38 s at MODVFILT1 25 against 1.14 s at 18)
was the filter's own corner ceiling saturating at the top of its range, not
depth-dependence; swept at MODVFILT1 5 and 10 the times agree to 1.00 ± 0.01
across nine values. §67 then settled ATTAK2 as a **rate**. I wrote this stale
reason into the file on 2026-08-20 while correcting a *different* stale
citation, from a report I did not check.

**"Our model carries no filter-envelope amount"** — and this one is ours, about
our own model. `VoiceLayer.filter_env_amount` exists, **eight parsers populate
it**, and it is non-zero on **20 of 39 voices** in real E4B material. The claim
appears to have been true once and was never revisited.

### The real blocker, which has never been costed

These are **rates over a variable distance**: a stage takes
`full_time * (distance / 99)`. `ATTAK1` is a duration precisely because it
always travels zero-to-peak; envelope 2 does not. Wiring them needs envelope
2's level architecture — a four-stage rate/level envelope (s3ked §67) — and a
decision about how our two-parameter `Envelope` maps onto four stages with
independent levels.

That is design work, not a missing measurement, and it is a different kind of
task from the one this row has been deferring. Cost it before deciding.

**Note what did NOT change**: no hardware is needed, and the reason is not the
one given in the first version of this note. I wrote that s3ked "measured it
with a resonance tracker instead" — true but beside the point. **The IB304F
gates the second filter** (`FLT2GAIN`, `FLT2MODE`, `FLT2Q`, `FIL2FR` and
neighbours) and never gated envelope 2 at all. Every envelope-2 measurement was
taken on a machine that has never had the board, routed to filter 1.

Their §87 records them making the identical error seven days earlier, flagging
fifteen fields as board-dependent on a citation to §19 — the FILFRQ
measurement, which never mentions the board. Its verdict is the best sentence
either project has produced on this: *"the claim was an assumption wearing a
citation — the most persuasive form a wrong claim can take in this project,
because the reference makes it look checked."*

Note that §87 predates our error by seven days and s3ked had read it. **Naming
a failure mode in a resolution note does not inoculate anyone against it**,
which is worth knowing about this entire file.

### Why this section exists

Sixth instance in two days of a correct fact attached to the wrong object, and
the first where the wrong object was **our own model**. The pattern across all
six: a sample name, byte offsets, a field name, a section number, a section's
vintage, and now a model capability. **Not one was a calculation error.**

The countermeasure that worked here is worth naming precisely: I checked
`scales.py` and `VoiceLayer.__dataclass_fields__` — the places where the answer
is *executable* — rather than the notes describing them. Prose goes stale
silently; a dataclass field either exists or it does not.


## §IDENTIFIERS — six wrong objects, zero wrong sums (2026-08-19/20)

Two days of AKAI work with s3ked produced six errors between the two projects.
Recorded together because the pattern is sharper than any of them alone.

    a sample name        F5-3 at key 89 -- two sessions naming one thing and
                         meaning different objects, because no one asked the
                         program which key addresses which sample
    a byte offset        S3000 keygroup positions read across S1000 files,
                         giving 36% where the real answer was 0 of 23 901
    a field name         "the ATTAK2 finding was quoted against ATTAK1" -- a
                         tidy story, invented and forwarded without reading
                         the section it described
    a section number     §29 cited where §31 held, stale by nine days, which
                         cost every source attack for twelve
    a section's vintage  §31's constants quoted against §141's refit, from a
                         section that was never retracted and never will be,
                         because it is still correct as written
    a self-description   "our model carries no filter-envelope amount" --
                         true once, never revisited, while eight parsers
                         populated the field
    a hardware premise   "envelope 2 cannot be measured without the filter
                         board" -- the board gates the second FILTER

**Not one was an arithmetic error.** Every number computed in those two days
was right. Every one of these passed its internal checks, and had to: a correct
fact checks out no matter what it is attached to. Internal consistency tests
the measurement, never the specimen.

### What actually caught them

Not review, and not the test suite — a passing unit test held one of these in
place for twelve days, faithfully pinning a behaviour whose justification had
been withdrawn. **A test only checks the claim it was given.**

What caught them, every time, was going to the place where the answer is
*executable* rather than described: the machine's keygroup table instead of the
sample names, `VoiceLayer.__dataclass_fields__` instead of a comment about the
model, s3ked's `scales.py` instead of the section prose, the source file
instead of the report about it. Prose goes stale silently. A dataclass field
either exists or it does not.

### A test for corrections, which came out of getting one wrong

s3ked's formulation, from the board correction: not *"is this correction
true"* but **"if the circumstance that made the workaround necessary went away,
would the claim come back?"** If it would, the premise has not been addressed.

That is checkable on a correction in isolation, without knowing the underlying
fact, which is what makes it worth having. The failing example is ours: saying
the board blocker was stale *because s3ked measured it another way* is true and
leaves the premise standing, so anyone who later obtained a board would
reasonably reinstate it — and it would come back wearing the authority of
having been reviewed once.

### The one that generalises

**The identifiers that bit us were the ones that felt too obvious to check.**
Nobody re-reads a field name. That is precisely why it is the surface where
errors survive longest.

And a tidy causal story is cheap to believe *and* cheap to forward. It
accelerates in a way a correct one does not, because a correct account usually
has an awkward detail in it that makes you stop. Two of the six were transmitted
between projects within minutes, by both sides, neither short of time.

### An eighth, of a different kind: invariance answers a question it was not asked

Not a wrong object — a right observation pointed at a question it cannot
settle. s3ked read "all 35 990 `.S1` headers carry index 1" as evidence the
byte may carry no rate meaning in that generation. It is not:

**A field constant across 35 990 specimens bounds the CORPUS, not the machine.**

Invariance is the single observation that cannot distinguish *"this field does
nothing"* from *"nothing here exercised this field"*, and it is seductive
exactly because the sample size feels overwhelming. Our corpus is library
CD-ROMs mastered at 44100 — precisely where an invariant 1 is expected — and
ConvertWithMoss saw the same byte varying on machine-recorded S1000 material,
where a 22050 recording leaves SSRATE at zero and is marked by the index alone.
Two observations, no contradiction; the inference was what failed.

The uncomfortable detail, which is theirs and which they recorded: they wrote
§140 that same afternoon, establishing that a corpus cannot separate a hardware
law from a library's taste in material — and then read a corpus invariance as a
hardware property inside the hour.

**This project's own §AKAIVFR turns on the same trap from the other side**:
offsets 9/10/11 measured inert on an S3000XL, which is a real measurement of
absence, and the live fields were elsewhere. Absence of variation and absence
of effect are both evidence about the instrument first.

### A ninth: calibrated over the range we could measure, not the range in use

s3ked's generalisation, 2026-08-20, and the sharpest thing to come out of the
FILFRQ distribution.

Their filter law is fitted 40..84. Across four S3000 factory discs, **685 of
1555 keygroups sit in 85..98 and TWO inside 40..84** — 0.1% of *those* voices
sit where the law was measured.

**Corrected 2026-08-21, because the first version of this paragraph committed
the error the paragraph is about.** It went on to say "0.1% of real voices",
dropping the population between the data sentence and the conclusion. That is
false for the other generation: of the 76 086 `.P1` keygroups in the corpus,
14 661 carry a real setting and **6869 of those are inside 40..84** — 47%,
against 0.1% on the S3000 discs.

    generation   keygroups   40..84   85..98   99 (open)
    .P3 (S3000)       1555        2      685         868
    .P1 (S1000)      76086     6869     6541       61425

So the fit is badly placed for S3000 material and well placed for S1000
material, and the unqualified claim was true of one generation and false of the
other. s3ked made the same slip in their own entry the same morning and
corrected it in place; **twice in two days a lesson about over-generalising was
over-generalised inside itself.**

Their conclusion, which is better than more care: a claim about "the material"
needs the population named **in the sentence**, the way a measurement needs its
units. A qualifier in the paragraph above does not travel with the sentence
that gets quoted.

**The fit range was never chosen.** §54's own bounds note states the limits
honestly: below 44 the corner drops under the lowest note's fundamental, above
92 the source runs out of harmonics above the corner. **The sawtooth set the
range** — not the machine, and not the question. The material then turned out
to live almost entirely outside it, and nothing anywhere warned that the two
did not overlap.

> Calibrating over the range you can measure is not the same as calibrating
> over the range that is used.

Every bounds note in both projects records the first honestly. None of them
knows to ask the second. It is the same family as the wrong-specimen errors —
the measurement is sound and it is about the wrong part of the domain — and it
is invisible from inside the measurement, because a bounds note reads as
diligence.

**The check that would have caught it costs nothing**: before fitting, count
what the corpus actually uses. We had the corpus the whole time.

Consequence for our own discs: the 40 Hz sawtooth on `HD_s1000import.img`
carries the same ceiling if the acoustic path is ever used from it. Recorded in
that procedure rather than discovered again.

### A tenth, and it is about NULL results: identity needs a positive control

From §144, where the S3000XL's `.P1` import returned all twenty fields
unchanged. s3ked reported the two fields that *did* move — `KGRP1@`/`NXTKG@`,
the object-pool addresses, 24 bytes apart per program — as a footnote meaning
"not a mapping, ignore".

They are the positive control, and without them the result is much weaker.

**A readback in which nothing changed is indistinguishable from a readback that
was not live.** The same numbers come back from a stale directory cache, from
the wrong device, and from a load that silently did nothing — and all three
have happened in these two projects, the middle one the day before. The pool
addresses moving prove the machine wrote where it owns memory while leaving
every semantic field alone.

> An all-identity result needs something in it that changed, or it is only
> evidence that the measurement was inert.

This is the same instinct as designing a negative control (rule 4 of the bench
traps) but it applies **after collection rather than during design**: given a
null result already in hand, ask what in it demonstrates the instrument was
connected. Often something already in the data does, unremarked, because it was
filed as noise.

### The limit of writing any of this down

s3ked's §87 named this failure mode on 2026-08-13, in the same file, about the
same board. Seven days later they made it again and sent it here, having read
it. **Naming a failure mode in a resolution note does not inoculate anyone
against it** — including this note.


### Answered on hardware, 2026-08-20 (s3ked §143)

Loaded from the disc built for it, which is the point — every earlier
measurement of this byte was a SysEx write into a resident program, and the
open question was the load path.

    program        0x01   SSRATE     measured        verdict
    RR1 CONTROL      1    44100      300.0 Hz        control passes
    RR2 CONTROL      0    22050      150.0 Hz        control passes
    RR3 CONFLICT     1    22050      300.0 Hz        the INDEX
    RR4 CONFLICT     0    44100      150.0 Hz        the INDEX

**Both conflicts resolve to the index, in opposite directions**, so this is not
a default or a coincidence of one direction. The controls ran first under a
stop rule, so the conflicts are read against measured references rather than
predictions.

`_playback_rate()` in the parser now returns the index for S3000 samples.
S1000 keeps SSRATE for the reason recorded above — the byte is invariant across
all 35 990 `.S1` headers here, which bounds the corpus rather than the machine,
and §143 is an S3000XL measurement.

### The attack half, also answered

`ATTAK1` read back over SysEx from the LOADED programs before any note played:
**72, 85, 96 — exactly what the disc holds.** So the load path preserves the
envelope field.

    program        ATTAK1   t90 measured   predicted   ratio
    RR5 ATK SHORT     72        0.44 s       0.45 s     0.978
    RR6 ATK MID       85        1.86 s       1.82 s     1.022
    RR7 ATK LONG      96        6.18 s       6.01 s     1.028

Within 2.8% over a fourteen-fold span, and **not instant** — which was the
quiet failure worth guarding against, since a sign error would reproduce the
old fixed default exactly. Those three values were written by our own converter
from source times of 0.5 / 2.0 / 6.554 s, so one note verified the law, the
writer and the load path together.

### One design note for the next rate disc

s3ked recommended taking the second partial as well as the fundamental, so a
playback-rate change is distinguishable from a reinterpreted pitch. **It did
not apply here and they said so rather than letting it stand**: these tones are
pure sines and every partial after the first sits at 0.00 of the peak. The
check needs harmonic content.

The controls carried that interpretation instead, and more cheaply — RR1 and
RR2 are the same material at both rates, so the reference is measured rather
than predicted. A future rate disc should use a harmonic-rich tone so both
discriminators are available; the controls are not optional either way.


## §AKAIFILTREAD — the reader reads the filter and drops it, and the law it would need may be stale

Two findings, one dependent on the other. Found 2026-08-20 while testing
whether real `.P1` files could carry the proposed S1000 filter experiment —
i.e. by accident, while doing something else, which is how both halves of the
attack bug surfaced too.

### 1. `filter_freq` is read into a dict and never consumed

`parsers/akai_s3000_parser.py:407`:

```python
keygroups.append(dict(
    lo_key=kg[0x03], hi_key=kg[0x04],
    tune=_s16(kg, 0x05),
    filter_freq=kg[0x07],        # <- read here, used nowhere
    ...
```

Grepping `filter_freq` in that file returns exactly one line. Measured over
three factory discs: **`filter_cutoff` is 1.0 on all 16 020 AKAI-sourced
voices.** Every AKAI → E4B/KRZ/XPM conversion loses the programme's filter and
comes out fully open.

**Exactly symmetric to §AKAIATTACK.** There the WRITER emitted a constant it
never varied; here the READER takes a value it never uses. In both cases the
field was measured, available, and quietly dropped — and in both cases the loss
is silent, because "wide open" and "no filter information" look identical in
the output.

### 2. The law it would need has two competing measurements

The fix is the inverse of `akai_filter_byte()`, so it needs FILFRQ → Hz. There
are two:

    ours, writer  _AK_FILTER = 6.4597  * exp(0.07100 v)   fitted 44..92
                  documented as re-derived from the RESONANCE PEAK, §54
    s3ked §139    7.60732 * exp(0.07245 v)                fitted 40..84
                  the CORNER, from a sawtooth harmonic comb divided by its own
                  spectrum at FILFRQ 99, r2 0.99981

        FILFRQ 44   146.9 Hz    184.4 Hz    ratio 1.255
        FILFRQ 60   457.4 Hz    587.6 Hz    ratio 1.285
        FILFRQ 80  1892.4 Hz   2502.7 Hz    ratio 1.323
        FILFRQ 92  4436.3 Hz   5970.1 Hz    ratio 1.346

Ours reads 25–35% low against theirs, drifting with the setting. **A resonance
peak is not a −3 dB corner**, so this may be a definitional difference rather
than an error — but our writer uses the older one and **nothing in our file
records that a newer measurement exists**. That is the §31-versus-§141 pattern
again: a section never retracted because it is still correct as written, whose
constants have nonetheless been superseded.

§139 also settled the **pole count at two** (−12.2 dB/octave), against the three
the S1000 specification claims — which is what explained the constant 1.76×
offset against ConvertWithMoss's firmware-derived table.

### What to do, in order

1. **Decide what `filter_cutoff` means** — a corner or a resonance peak. Reader
   and writer must agree, and today they would not.
2. Wire the reader for **S3000 sources only**. The S1000 corner law is the open
   question the proposed S1000 disc exists to settle, and §139 measured an
   S3000XL. Same shape as the generation split in §AKAIRATEREAD.
3. Only then revisit whether `_AK_FILTER` should move.

Not done tonight: a 16 020-voice behaviour change on a law whose definition is
unsettled is not a thing to ship at 23:20 on the strength of noticing it.


### Fixed 2026-08-20, and the fit range turned out to miss the data

s3ked's answer on the law: **use §139**, the -3 dB corner, because that is what
every source format means by "cutoff" — and their correction that §54 is *not*
a different quantity, since it argues the resonance peak sits AT the corner.
So the 1.29x is an unexplained disagreement between two measurements of the
same thing, open on their side, one sweep from resolution.

`AKAI_FILTER_LAW` therefore moved to `models/common.py`: the writer imports the
parser, so the parser cannot import back, and a shared constant is the
structural guarantee that reader and writer cannot drift. If the sweep moves
the constant it moves once, and an AKAI round trip stays self-consistent
meanwhile because the same law cancels — which is s3ked's argument for
adopting §139 now rather than waiting.

**What the corpus said about the fit.** Four S3000 factory discs, 1555
keygroups:

    FILFRQ  0..39      0
    FILFRQ 40..84      2      <- the entire fitted range
    FILFRQ 85..98    685      <- mostly 90 and 92
    FILFRQ 99        868

The fit covers **two** of 1555. Clamping to its top put 685 voices on a single
cutoff, all darker than they sound. The top decade is now interpolated in
position between the fit at 84 and hardware-confirmed wide open at 99 — both
endpoints measured, only the shape between them assumed, and assumed to be the
straight line in position the rest of the scale already is.

**Worth a sweep of 85..98 on s3ked's side.** It would replace an interpolation
with measurement on 44% of real voices, and their existing sweep covered a
range the factory discs barely use.

### The test caught the same mistake twice in one day

The first version exercised `_cutoff_of()` directly and **passed with the
wiring torn out** — identical to the attack test that morning, which called
`akai_attack_byte()` and would have survived the very revert it existed to
catch. Caught here only because the earlier one had already taught it. The
assertion now parses a written program through `parse_akai_program` and checks
the value that reaches the model.


### S1000 sources joined it, 2026-08-21, on a measurement

This note said `.P1` keeps the default because both laws are S3000XL
measurements. **s3ked §144 settled that in ninety seconds and without audio**,
on Jan's idea: if the S3000 reads `.P1` natively then AKAI's own import routine
IS the S1000 → S3000 mapping, and a SysEx readback states it.

It does, and it is a pass-through:

* a FILFRQ ladder of 14 values, 30..99, came back **exact and monotonic**
* three probe programs setting **all twenty semantic fields** to 20, 50 and 80
  returned every one **unchanged**
* the only fields that moved were `PRGNUM` (by design) and `KGRP1@`/`NXTKG@`,
  which are object-pool addresses the machine owns — 24 bytes apart per
  program, i.e. the pool laying out three programs

So the manufacturer's own answer is that an S1000 FILFRQ is an S3000 FILFRQ.
The branch is removed and it reached **14 661 keygroups** — 19.3% of the 76 086
`.P1` keygroups in the corpus carry a real setting and every one had been
converting fully open. On three S1000 discs, voices reading fully open fall from
100% to 62.8%.

**Identity is not equivalence, and this is the result most likely to be
over-read.** s3ked flagged it before I could: the importer not altering the
number does not make the number sound the same. §139 measured 12 dB/octave on
this machine against the S1000's specified 18, so FILFRQ 60 imports untouched
and can still produce a different corner on the two machines.

What we now reproduce for a `.P1` is **what an S3000XL makes of that file** —
which is what anyone playing these discs on S3000-family hardware hears, and
what Jan hears. What an *S1000* made of it is untouched by this and still needs
an S1000. Both halves belong in any quotation of this result, or the volunteer
disc gets retired on the strength of it.

### The free result: AKAI defaults the extension bytes to zero

Keygroup **151/152/153 read `[0, 0, 0]`** on all three probes. A 150-byte S1000
keygroup cannot carry the S3000 extension, so that is AKAI's own default for
the velocity / LFO2 / envelope-to-filter depths of §AKAIVFR — a default nobody
had written down, for one extra read.


### The "by construction" claim was false when I wrote it, 2026-08-21

I wrote that moving the law to `models/common.py` made reader and writer *exact
inverses by construction*. **It did not.** The reader used the shared
`AKAI_FILTER_LAW` (§139); the writer still used its own `_AK_FILTER` (§54).
Found by checking my own docstring against the code instead of writing another
note, after s3ked pointed out we had spent longer documenting the work than
doing it.

Measured before fixing — AKAI → AKAI, FILFRQ in and out:

    in    40  50  60  70  80  84  88  92  95  99
    out   44  53  64  74  84  88  99  99  99  99

**Nine of ten drifted, +3 to +11, brightening on every pass.** A bank
round-tripped through our own converter came out progressively more open.

Fixed: the writer now uses `AKAI_FILTER_LAW` and `AKAI_FILTER_OPEN`, both
shared, and mirrors the reader's interpolation across the unmeasured 84..99
decade instead of clamping. **60 of 70 settings from FILFRQ 30..99 now survive
a round trip exactly.** The remaining ten are 30..39, below the fitted floor,
where the reader clamps to 40 and refuses to extrapolate — a documented floor
rather than drift, reaching 1251 of 76 086 `.P1` keygroups (1.6%) and none on
S3000.

**Which law, settled from their module rather than their message.** Our own
`test_our_exponential_laws_match_s3ked` says *"take the values from
s3k/scales.py, not from a handoff message: the message is a snapshot, the
module is maintained"* — and it fired, because their `Scale` still carries §54.
Reading the module rather than assuming a conflict resolved it: the Scale's own
note directs the choice explicitly.

> "a converter mapping a source format's CUTOFF wants §139 — every format means
> the -3 dB point by 'cutoff', and §139 measures that directly rather than
> through an indicator"

So the coefficients are the resonance law because that is what the `Scale`
object *is*, and the note tells converters to use the other one. No conflict,
and no override of the guard. FILFRQ is removed from the drift table with that
reason, and a new test reads §139's constants **out of their note** and checks
ours against them — so it still catches our drift, and now also catches s3ked
revising §139 without telling us. When the 1.29× is resolved, that test is
where the follow-up is anchored.

`_AK_FILTER` is kept as `_AK_FILTER_SUPERSEDED`, marked, so the long provenance
note above it still has a subject and nobody uses it by reaching for the
obvious name.


### Measured, 2026-08-21 (s3ked §146): the law is right to 84 and wrong above it

The FILTERTOP disc ran. **§139 reproduced at 1.0042, sd 0.0136 across 68..84**
— four parts in a thousand, a different source, a different session, a
different anchoring. That is the strongest confirmation it has had, and it
settles that our reader and writer are on the right law.

**It stops being right immediately above its fitted range.** The measured
corner rises faster than the exponential and the gap grows monotonically:

    FILFRQ   measured   §139 law   ratio
        84       3421       3344   1.023
        86       3984       3865   1.031
        88       4643       4468   1.039
        90       5512       5165   1.067
        92       6888       5970   1.154
        94       8481       6901   1.229

So extrapolating understated the corner by up to 23% across exactly the band
where most S3000 factory material sits — the 685 of 1555 keygroups this disc
was built for.

**And the top saturates.** FILFRQ 98 differs from wide-open 99 by 2.2 dB across
the entire band: they are the same filter. 96..99 are now treated as **open**
rather than assigned corners, because giving them frequencies would invent
three numbers the machine does not distinguish.

`akai_filfrq_to_hz` now returns the law to 84, the **measured corners** from 86
to 94, and **None** — open — at 96 and above. Measured everywhere,
extrapolated nowhere.

**The writer's inverse is now a search over the reader's forward map**, not a
second formula. That is the direct fix for 2026-08-20, when two hand-derived
inverses of one curve drifted apart, nine of ten values failed a round trip,
and a docstring claimed they were inverses by construction. A search cannot
drift. 56 of 70 settings now survive a round trip exactly and all fourteen
exceptions are correct by design: 30..39 clamp to the fitted floor, 95 takes
94's corner because 95 was never measured, and 96..98 write back as 99.

### s3ked's own objection was right in prediction and wrong in mechanism

Worth recording because it is a new failure shape. They argued FILFRQ 99 could
not serve as the divisor because its own corner sat near 9.9 kHz. **It does
not** — 99 is flat to 18 kHz and is a perfectly good divisor. The top rungs are
unmeasurable because *they* converge on the reference, not because the
reference falls away.

Same observation, opposite cause. And the reasoning came from extrapolating the
very law the run was built to test — which is circular, and invisible, because
**a correct prediction from a wrong mechanism leaves nothing in the outcome to
expose it.** The disc was built correctly on it regardless, which is the part
that makes it worth writing down.


### Refined the same hour: the departure begins AT 84, so the law is used to 80

My first pass computed 1.0131 by including 86 and 88, and I "corrected" it to
s3ked's 68..84 window. **The first number was the finding and the correction
buried it.** They checked what the window was hiding rather than accepting the
agreement:

    68  0.987      80  1.002    <- last flat point
    72  1.007      84  1.023    <- departure begins, INSIDE the fit
    76  1.002      86  1.031

    68..80   mean 0.9996  sd 0.0085
    68..84   mean 1.0043  sd 0.0128     <- §139's own fitted range
    68..88   mean 1.0131  sd 0.0184

The flat region scatters 0.987..1.007. **84 sits at 1.023 — outside it, and the
first step of a monotone run** (1.023, 1.031, 1.039, 1.067, 1.154, 1.229).

So the law is now used only to **80**, one rung below its own fitted top, and 84
takes its measured corner. Nothing is lost: 84 was measured.

**A fit's upper bound is where it is least constrained** — fewest neighbours
holding it — so it is the first point to fail, and it is exactly the point a
mean over the fitted range is least able to reveal. "1.004 across the fitted
range" reads as uniform agreement and was four flat points plus one already
leaving.

Both projects computed that average and neither looked at its last point until
an outlier forced it. **A mean over a range answers a question about the range,
not about its endpoints** — and the endpoint is where a fitted law is most
likely to be wrong.

### Narrowing the wrong-mechanism lesson

s3ked's refinement of my own framing, and it is better: stating the mechanism
is not a general virtue, it is what matters **when the conclusion cannot be
checked independently.** Their "99 cannot divide the top rungs" was
unfalsifiable until the run happened, so the mechanism was the only examinable
part. When a conclusion *is* independently checkable, checking it beats
reasoning about its derivation.


## §AKAIPOOLBASE — the silent first program, and a fix that was only ever described

**Jan, 2026-08-21, at the machine:** `TC1 E4B BASS`, PRGNUM 0, `bass A` —
no sound. First program of the first volume he tried.

`bass A.S3` is the **first sample in the volume and it is looped**, which
is precisely the condition §AKAILOOPCROSS established on hardware: a looped
sample at the base of the sampler's object pool plays silent or degraded.

So this is not a new bug. It is the old one, arriving as the hardware
confirmation that row had been waiting for — in the form of a failure rather
than a pass.

### The fix was recorded as shipped and does not exist

TODO said: *"Fixed: `build_akai_volume` emits an unlooped sample first, so
under the bulk load a user performs the one-shot takes the base — a reorder,
not a filter, with a warning when a volume is all loops."*

`build_akai_volume` iterates `for sd in bank.samples` in plain order. There is
no reorder. `grep` for the warning across `writers/`, `convert.py` and
`processors/` finds nothing. **The row read FIXED for three days on the
strength of a description of a fix.**

That is the same shape as three other things this week — a claim that reads as
checked because it is specific and confident — but it is the first where the
claim was about *our own code* and a single `grep` would have settled it. The
others at least needed a measurement.

### A reorder would not have been enough here

**All ten samples in `TC1 E4B BASS` are looped.** There is no one-shot to
promote, which is exactly the case the recorded fix said it would only *warn*
about. So even the described fix, had it existed, would have printed a warning
and produced this disc.

### What would actually work

Emit a **tiny disposable one-shot as the first sample of every volume**, so the
pool base is always occupied by something whose silence costs nothing. A few
dozen frames, clearly named. It works whether or not the volume contains any
one-shot of its own, which the reorder does not.

Costs: one extra sample per volume in the sampler's list, and a few hundred
bytes. Against: a silent program in a converted volume, which is what we have.

**Do not implement it on the strength of this note.** The pool-base finding
itself came with a warning that five rules were stated and withdrawn before the
surviving one, and the mechanism — whether it is the pool base, the load order,
or the first-loaded sample specifically — is still not separated. A pad sample
tests the fix and the mechanism at once: if the pad is silent and everything
else plays, the rule is confirmed and the cost is a sample nobody listens to.

Kept on the list at Jan's instruction, 2026-08-21, rather than fixed
immediately.


### WITHDRAWN the same evening: the symptom was not there

s3ked measured `bass A` on the machine and it is the **loudest** program in
the volume — **-15.8 dBFS**, centroid 152 Hz. It is not silent at note 69,
velocity 100, and they flagged it against my brief rather than fitting the
measurement to it.

**And Jan's own remark for PRG 0, written after he reported the silence, is
"a bit muddy compared to E4. Filter cutoff and Q?"** He described its tone. I
had read that remark, printed it, and quoted it in a message — without noticing
it contradicted the bug report I had filed an hour earlier.

So this section stands only as a record of how it was written. What actually
happened:

1. one report of silence on one program
2. a known bug whose **preconditions fit exactly** — first sample in the
   volume, looped, at the pool base
3. a resolution note, a reopened TODO row and a commit message built on the
   match

**The preconditions did fit. The symptom was not there.** Every check I ran
confirmed the conditions and none of them asked whether the effect was present,
because the effect had been reported and I treated a report as an observation.

The likely real cause of what Jan heard is separate and now visible: **channel 1
is silent on that machine tonight** — s3ked found every program silent on
channel 1 and every one sounding on channels 2..16. That would have produced
exactly one thing: a program that did not sound when tried.

### What survives

* §AKAILOOPCROSS itself is untouched. It was established by a decisive pair
  with the address as the only difference, and nothing here bears on it.
* The **fix recorded there still does not exist in the code**, which I found by
  grep and which is independent of this. `build_akai_volume` has no reorder and
  no warning. That part of the TODO correction stands.
* The pad-sample proposal stands as a *design* for that unimplemented fix, and
  is now clearly untested against any observed symptom.

### The lesson, which is not the one I wrote the first time

A report is not a measurement. Jan's "no sound" was a real thing he
experienced, and it was the best available evidence at the time — but I
promoted it to an observed symptom, matched it to preconditions I could verify,
and never asked whether anything had reproduced it. **Matching preconditions is
not evidence that the effect occurred**, and it is seductive precisely because
the preconditions ARE checkable and the symptom is not.

The check that would have caught it costs one message: ask whether it still
does that.


### Wired 2026-08-21, and the measurement is why

This section argued the blocker was design work in our model, not a missing
measurement. That was right, and what unblocked it was a number: Jan's A/B of
ten programs against their E4XT originals, at three pitches.

    sources WITH a filter envelope (3 of 10)   -17.3 / -20.6 / -17.8 dB HF
    sources without one            (7 of 10)    -3.6 /  -6.5 /  -7.8 dB HF

**Flat across pitch** on the envelope group, which is what distinguishes a
missing modulation from a mis-set corner: a wrong cutoff opens or closes as the
note moves relative to it, a missing envelope costs the same everywhere. And
Jan picked those three out of ten **by ear, before anything was measured**.

The mapping, which is the design work this section was waiting on:

* **stage distance.** The published laws are full 0..99 traverse times, so a
  stage covering less takes proportionally less: scale the wanted time up by
  `99/distance` and invert. Attack climbs the full range, decay falls from the
  top to the sustain level, release falls from sustain to zero -- the same
  shape `akai_env_bytes` already uses for envelope 1's dB spans.
* **SUSTN2** is a level, linear, `v/99` of full excursion.
* **the depth at keygroup 153 is not optional.** §144 measured AKAI's own
  import defaulting 151/152/153 to zero, so an envelope written without it
  modulates nothing -- silent in precisely the way the fixed default was, and
  indistinguishable from not having done the work. The regression test asserts
  the routing separately for that reason and was confirmed to fail without it.
* **written only where the source has one.** Seven of the ten presets have no
  filter envelope; they keep neutral defaults rather than being handed one.

**Known limit, stated rather than hidden:** a 30 ms filter attack wants a byte
below the fitted floor and clamps to ATTAK2 40, about 66 ms. Slower than asked
by roughly 2x on fast attacks. That is the refusal-to-extrapolate rule this
project applies everywhere else, and the fix is a measurement below 40 rather
than a formula.

**Not yet heard on hardware.** The disc must be rebuilt and reloaded before
anyone knows whether 20 dB came back.


## §SILENCEGATE — silence does not clip

Four appearances in one evening, across three sessions, of one failure:

* **eosed's capture script** passed thirty silent takes as *"no clipping,
  peaks -70.3..-65.2 dBFS, RESULT: usable"*. It checked whether the audio was
  too loud and never whether there was any.
* **s3ked** captured thirty on a MIDI channel the sampler was not answering.
* **s3ked** captured thirty more on a note above the mapped key range.
* and their **§138**, a week earlier, read silence as **+31 cents of pitch
  drift**, because the estimator's threshold scaled to its own window's peak.

Ours the same night, in a different medium: I filed a bug from a *reported*
silence that had never been observed (§AKAIPOOLBASE).

**A measurement of silence is confident, well-behaved and worthless, and it
looks exactly like a measurement of a very dark sound.** Every check involved
tested the measurement rather than the specimen.

### The fix, and why this form of it travels

eosed's: **lift over the take's own pre-roll.**

    lift_over_preroll(env, t, on)   dB the note rises above its own pre-roll
    sounded(env, t, on)             against SOUNDED_MIN_LIFT_DB = 20

Comparing a take with *itself* needs no absolute reference, no level
calibration, and survives a change of rig or gain — none of which a peak
threshold does. Across 150 takes on 2026-08-21 the two populations did not
overlap: real notes lifted 50–70 dB, dropped ones zero, and no tuning was
required.

Ported into `tests/re_banks/hw_measure.py` because that is the one that runs
**unattended**, where a confident "usable" on silence costs a session rather
than a take. s3ked has it in `probes/calibrate.py`; the constant and the
reasoning are duplicated deliberately so neither project depends on the other's
tree.

### The threshold, and which way it should fail

20 dB, not higher. A sparse percussive source over a fixed window lifted only
**23.3 dB** (s3ked's rainsticks) where bass material lifted 62–69, so the
margin is thinner than the first dataset suggests. **If it starts rejecting
real takes the fix is a longer window, not a lower bar** — the failure that
matters is passing silence, and refusing a quiet note is loud and immediate
where accepting a silent one is neither.

### The part worth keeping

s3ked wrote §138 a week before repeating its lesson twice in one night. **Naming
a failure mode is not the same as building a gate against it** — and this note
is no exception, which is why the gate is code in two repositories rather than
a paragraph in one.

## §CAPTUREPORTS — proving an instrument is silent, rather than assuming a port (2026-08-22, MEASURED)

**Status:** the scanner exists and is proven; the K2000's own fault is still open.

The rig model in `tests/re_banks/hw_measure.py` names a capture pair per device.
Each pairing was established once, by hand, and nothing re-checks it. The K2000
is not in that table at all — the three entries are MPC One 5/6, S3000XL 13/14,
E4XT 15/16 — so when k2kremote recorded the K2000 as pure silence at
`system:capture_17/18`, the pairing itself was a guess with nothing behind it.

`tests/re_banks/scan_capture_ports.py` settles that class of question without
anyone in the room. It registers one JACK client, connects to **every** system
capture port at once, and reports peak and RMS per port over a window. Play the
device during the window: the pair that lights up is the device's pair. If no
pair lights up, the fault is upstream of the interface and no amount of
port-hunting will reach it.

**The K2000 measurement.** Across a 15 s note run (program 200, note 69,
retriggered every 1.5 s), every one of 20 ports sat within ~1 dB of its own
no-signal baseline, drifting in both directions — noise, not signal.

**The positive control, which is the part that matters.** A negative result
from a scanner never once seen to produce a positive is worth very little: a
deaf scanner and a silent instrument are indistinguishable. s3ked played the
S3000XL for 90 s (they chose 90 s over 15 s deliberately, so a missed sync
could not masquerade as a dark scanner):

    capture_13    -19.6 dBFS peak    idle -70.9
    capture_14    -19.4 dBFS peak    idle -71.6

51 dB of lift, within 0.5 dB of the level s3ked predicted from their own end
*before* seeing ours. Two independent measurements agreeing that closely is the
evidence; either alone is not.

One further reading fell out of the control. `capture_17/18` read **-87.8 dBFS
during the K2000's own note run** and **-79.7 dBFS during the AKAI burst** — it
picks up 8 dB of bleed from an instrument on a different pair. An input that
hears another box's crosstalk but not its own source is not miswired. The K2000
is making no sound.

**Leads still open, both upstream of the audio path:**

1. **MIDI channel.** s3ked's S3000XL stopped answering on channel 1 partway
   through 2026-08-21 — channel 1 worked at 17:07, when the §146 filter sweep
   ran twelve measured corners on it, and did not at 23:11, costing thirty
   captures that came back as noise floor. What changed between is not
   established.

   State this narrowly, and s3ked's §147 is the authority: **this is not "the
   S3000XL ignores channel 1".** That would be a larger claim than the evidence
   carries and would be wrong at the next boot. The durable finding is that
   **`PMCHAN` is a value in a header, and reading it does not establish which
   channel the device is currently listening on.** They agreed for weeks and
   then did not.

   SysEx is channel-independent — it carries its own device id — so
   k2kremote's SysEx-confirmed preset selection proves the cable and the id and
   proves *nothing* about the channel its note-ons go out on. From outside,
   that gap looks exactly like a healthy MIDI link, which is why nobody looks
   there.

   **The check: play a note and confirm sound, rather than reading `PMCHAN` and
   believing it.** If nothing sounds, sweep all sixteen channels before
   suspecting the audio path at all. Sixteen notes is cheaper than one wrong
   conclusion about routing, and it separates "not listening where I am
   sending" from every other cause of silence in a single pass.
2. **Output routing.** K2000 program 200 reads `Pair: A(FX)` on both layers —
   through the effects bus, not a dry main pair. Same shape as the trap s3ked
   recorded for the S3000XL: a program on an individual output measures as
   silence on the mains, with the panel showing nothing wrong.

**Two reusable rules, and the second was free.**

*Prove the measuring path can hear something before concluding anything about
the device.* A control costs one message to a session whose instrument already
works, and without it a negative result is indistinguishable from a broken
measurement.

*When you cannot make an instrument sound, look at what its input hears from
other instruments.* s3ked's point, from the crosstalk reading above: an input
carrying 8 dB of another box's bleed is demonstrably connected, powered and
converting, so its silence on its own source cannot be a dead input. **A truly
dead input hears nothing from anything.** That rules out the whole "the port is
broken" class using somebody else's signal, with no second run and no
coordination — a control nobody had to design.
