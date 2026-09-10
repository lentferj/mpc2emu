# mpc2emu — Open Items

**Bench note (2026-08-31): `~/autostartaudio.sh minimal` does NOT start mididings.**
The whole mididings block sits inside `if [ "$1" != "minimal" ]`, so a minimal
restart leaves all eight instances dead -- including `mididings_k2000r.py`, the
MIDI routing to the K2000R. The failure is silent: JACK returns healthy, the
recorder connects, captures succeed, and note-ons never reach the sampler, so
you get clean recordings of the noise floor. After a minimal restart, bring the
one you need back by hand (`~/.local/bin/mididings -f ~/mididings_k2000r.py &`)
and confirm with `ps -ef | grep mididings_k2000r` before trusting any capture.
See [[reference_mididings_configs]] -- these files are channel filtering only,
so restarting one changes nothing about how notes are shaped.

| **Filter-2: what is still unmeasured** | *(2026-09-10, §AKAIFIL2CLOSE)* **Status: OPEN, none of it needs a card swap, none of it is blocking.** Weighted by six library discs, 891 active filter-2 keygroups. ~~**`FIL2FR` 89..93 — 8.4% of material**~~ **MEASURED 2026-09-10 (§205).** No breakpoint: rung 89 is already +1.6% off, so the bound at 88 was placed exactly right and one byte further would have been wrong. **The region is not fittable** -- the per-byte steps alternate, four at ~1.090 and two at ~1.058 against 1.0729 predicted, a 3.1% step-to-step difference against 0.58% mode spread. Shipped as measured points with geometric interpolation; a local fit would have hidden +-3% steps behind a 1.1% residual. ~~**EQ depth on an interpolated `FLT2Q` — 8.0%**~~ **CLOSED 2026-09-10 (§206): all 32 values measured**, raw 1.465 Hz bins, nothing interpolated. The curve is three monotonic segments with a discontinuity between them, so it never could have been interpolated. ~~**New open item in its place: filter 2's RESONANCE GAIN is not consumed at all.**~~ **CLOSED 2026-09-10 (§207)** — measured in the model's own quantity (peak dB above each curve's own passband) and consumed: when filter 2 carries the shape, its `FLT2Q` resonance is used instead of filter 1's `FILQ`. **One open remainder: bandpass has no passband**, so the model's quantity is undefined for it — its skirts fall away on both sides (−20.15 dB at f0/8, −20.38 at f0×8 against a peak of −11.33). BP borrows the highpass curve and says so. Giving it its own reference or treating its resonance as shape is a **modelling decision, not a measurement one**; ~4% of board use. |
| ~~**Is the highpass passband bump a resonance?**~~ | **RESOLVED 2026-09-10, from captures already in hand and no bench time.** It is the resonance, unambiguously. The `FLT2Q` sweep at `FIL2FR` 80 already covered mode 2 at Q 0/16/31 and nobody connected it to the bump question: the peak strengthens monotonically (**+0.28 → +1.98 → +20.13 dB**) and descends onto f0 (**1895.5 Hz against the bandpass's 1889.6 at the same rung**). So the weak +1.1 dB feature at ~3.8x the corner at `FLT2Q` 0 is a high-sitting, barely-excited resonance, not a structural quirk of the highpass path. **The question was answerable the whole time from data both projects held** — the cost was not bench time, it was nobody asking the two results about each other. |
| **What an `FX1`..`FX4` value selects — corpus evidence, 169 multis** | *(2026-09-10, answering s3ked §215's open question from files)* **Status: narrowed, not settled.** All 169 multis in the 64-image corpus, bytes 16–19: <br><br>`FX1` 7 distinct values, **max 37** &nbsp;·&nbsp; `FX2` 8, max 27 &nbsp;·&nbsp; `FX3` 9, max 37 &nbsp;·&nbsp; `FX4` 8, **max 44**. <br>**Zero values anywhere above 204**, so nothing in real material comes near the one value known to panic the firmware. **CORRECTED 2026-09-11 (§217 supersedes §215):** the trigger is **205**, not 239 — 239 writes cleanly and reads back 239. And **there is no "refused band"**: what was recorded as 34 refusals at 205–238 was **34 consecutive timeouts logged as data**. Writing 205 produces no reply at all, SysEx down, panel panic, and the byte stored anyway. Only *"accepts 0–204"* survives from the original probe, and that is the part the fence rests on. <br><br>**120 of 169 multis have all four slots at 0.** The remaining 49 are sparse and repetitive — one configuration (`FX1`=37, `FX2`=24, `FX3`=5, `FX4`=13) accounts for ~36 of them, matching the 36-file md5 cluster exactly, so it is one authoring house's default rather than 36 independent choices. <br><br>**The inference the corpus supports: these are intrinsic codes, not indices into a named file.** `FXFILENAME` (bytes 20–31) decodes as all-zero on **every one of the 169** — no multi in this corpus names an effects file at all. So whatever an `FX` value selects, it is not a slot in an external file that the material ever names. A range of 0–44 observed against a 0–204 domain is consistent with a type code or a built-in slot list, and inconsistent with a dense index. <br><br>**Not settled**: 49 non-zero multis, most sharing one configuration, is thin evidence for a meaning. |
| **Effects assignment is a MULTI parameter, so our 23.3% may be the wrong copy** | *(filed 2026-09-10, from Jan asking whether s3ked has Multi edit)* **Status: OPEN, blocked on the multipart record layout.** Our own format doc already carries the precedence, quoting the manual: *"stereo level, pan, output and **effects assignment** are MULTI parameters, these are not accessible in EDIT MULTI"* — **the part's copies win in MULTI, the program's own apply in SINGLE.** So the 23.3% of programs selecting a bus is what governs in SINGLE mode; in MULTI it is the multipart copy at the same offsets (113/114) that decides. <br><br>**And the two declarations disagree by design** (s3ked): `program 114 PFXSLEV desc="Not used"` against `multipart 114 PFXSLEV desc="Effects send level"` — **same byte, opposite documentation, both transcribed from Akai's text.** That independently explains this corpus's `PFXSLEV` non-zero on 62% of programs: it is stored and ignored *there*, and live in the multi. <br><br>**Corpus, all 64 images: 169 multi files across 4253 volumes — 4.0%**, all 4096 bytes bar four. **They are not boilerplate**: the commonest md5 covers only 36 of 169, so ~79% carry per-volume content. <br><br>**What is missing is the multipart record's offset and size inside the `.M3`.** Without it the FX fields cannot be read, and guessing an offset is precisely what produced a "KFXCHAN" distribution running to 204 earlier this evening. s3ked's bridge declares the multipart fields, so the layout exists on their side. |
| **EB16 / effects: 23.3% of programs select a bus — MORE than the filter board's 6.1%** | *(2026-09-10; this replaces two earlier sets of figures, both wrong)* **Status: OPEN as a feature, and it now outranks the filter work on prevalence.** **Full local corpus, 64 images, 9442 programs, 52,034 keygroups** — the earlier passes scanned **6 images, 9% of it**, and neither said so: <br><br>`PFXCHAN` selects a legal bus on **2204 programs — 23.3%** (values 1/2/3/4 at 1939/171/31/63). `PFXSLEV` non-zero on **62.0%**. `KFXSLEV` non-zero on **44.1%**. `KFXCHAN` non-zero and in range on **118 keygroups, 0.2%**. Filter 2 active on **6.1%**, which is the one earlier figure that held (6.4% on the small sample). <br><br>**THE `KFXCHAN` OFF-BY-ONE IS SETTLED BY THE CORPUS, and s3ked's reading is right.** The spec documents byte 161 twice — `0=OFF 1=FX1 2=FX2 3=RV3 4=RV4` (legal 0–4) or `0=PRG 1=OFF 2=FX1 3=FX2 4=RV3 5=RV4` (legal 0–5). **Two independent arguments, and the second is the strong one:** five keygroups carry the value **5**, which the first enumeration cannot produce; and **51,780 keygroups carry 0**, which under the first reading would mean every one of them overrides its program to *no effects* — leaving the 2204 programs that select a bus unable to be heard. **`0 = PRG` is the only reading under which a program-level effects setting can do anything**, and 23.3% of programs make one. <br><br>**We still read and write none of these fields**, and the model has no effects-send field on `VoiceLayer` or `Preset`. At 23.3% this is now the largest unread field in the AKAI path. |
| **Is there a file-level EB16 detector, and is our embedded `.X` a no-board default?** | *(filed 2026-09-10, board fitted the same evening)* **Status: OPEN.** The EB16 has **no `requires` flag anywhere in `params.py`**, so nothing on the wire distinguishes a fitted board from an unfitted one — the same hole the IB-304F had, which was only closed by Jan telling us the board was in. **But a file-level detector may exist where the filter board had none:** if fitting the EB16 changes what a type-0 save writes into `EFFECTS FILE.X`, that is a real detector — and it would mean the default `.X` embedded in every type-0 volume we build is a **no-board default** and should say so. Recorded pre-fit: **7312 bytes, md5 `dc6a0c4d`**. **THE CONFOUND, and it decides whether the answer is worth anything** (s3ked): a difference in md5 is only a board detector *if nothing else about the two saves differs*, and the recorded file's provenance is not a fresh save's — so a difference could be the board, the save path, or anything the machine stamps in. **The clean experiment is two fresh saves under identical conditions**, which now means one with the board in and one after it comes out; anything else is the weaker comparison and must be reported as such. A type-0 save is a **disk write to the sampler** and needs Jan's word directly. |
| **`FIL2FR` needs a ladder per `FLT2MODE`** | *(filed 2026-09-09, §AKAIFIL2, after the first hardware test of the filter-2 path)* **Status: OPEN, top bench ask.** Blocked on: bench time. Every point of the `FIL2FR` corner law was measured in **mode 0, which is 7% of real board use**; EQ is 50% and HP 39%. Hardware now shows the feature frequency moves a long way with mode — **HP 0.688x, BP and EQ-cut 1.653x, EQ-boost 1.515x** the mode-0 law at the same byte. Those are recorded in `AKAI_FIL2FR_MODE_FACTOR` and quoted by the `AKAI_FIL2FR_MODE_UNCALIBRATED` diagnostic but **deliberately not applied**: HP, BP and EQ-cut rest on one byte each, and only EQ-boost has two (74 and 80, agreeing to 0.8%). Applying a one-byte ratio across 0..99 is the mistake this table already undid once. Three ladders (HP, BP, EQ) at the same rungs as the mode-0 sweep would close it; **procedure written 2026-09-09: `docs/re_procedures/akai_fil2fr_mode_ladders.md`**, with the rungs derived, the predicted feature frequency per rung, the source to use at each (the two volumes fail at opposite ends), and the falsifier stated as a per-rung ratio rather than a mean. No card needed — all four fields are SysEx-writable. **Also worth the same trip:** `FIL2FR` 88..94, our largest interpolation gap (2073→5904 Hz, 2.85x) across the region the sweep found steepening — the best candidate for program 45's 4.7% corner error. |
| ~~**Filter 2 (IB-304F) may not be a 2-pole section**~~ | **RESOLVED SAME DAY, 2026-09-09 (§AKAIFIL2POLES) — it IS 2-pole and `Low 4` stands.** No model change. Filter 2's local slope passes 6 dB/oct by 1.4 kHz and reaches **10.6 by 6 kHz**; a 1-pole asymptotes at 6 and can never exceed it. **It is a 2-pole with a very wide knee** — filter 1 is within 1 dB of its asymptote **one octave** above its corner, filter 2 is still 1.4 dB short **three octaves** up. **My "three independent observations" were not independent: all three were taken inside that knee**, so they measured one wide transition band three times rather than converging on a missing pole. Candidate mechanism, untested: two staggered real poles rather than a complex-conjugate pair, which produces exactly this extended −6 dB/oct region before −12 takes over. Resolved from captures already in hand, with no new bench time. |
| ~~Filter-envelope depth scale~~ | **FIXED 2026-08-22 (§ENV2DEPTH2).** Both halves measured and both machines multiply envelope LEVEL by depth, so the sustain cancels and one constant maps between them: `AKAI_ENV2_DEPTH_MAX = 19.88`, **derived in code** from `5.14e-4` (eosed §46, 12 levels / 132 captures) and `0.002837` (s3ked §148, products 250–1980). The old 50 was a guess and delivered **2.8x** the sweep the source asked for. Two regression tests, both confirmed to fail with 50 restored. **Not hardware-confirmed end to end** — the laws are measured, the arithmetic joining them has not been listened to. |

| ~~KRZ filter cutoff is written on the wrong scale~~ | **fixed `58363c0` and HARDWARE-CONFIRMED 2026-08-22** (§KRZCUTCAL). Was stretching the model's 0..1 position linearly across the K2000's byte range, out by up to **1.80 octaves** and worst exactly where filtered material lives. Now routed through Hz. k2kremote read each program's own filter page off the device: all eleven `4P LOPASS`, and the `Coarse:` Hz labels match our law to **max 0.46%, mean 0.08%** — 0.0067 octaves. The remaining 1.29% mean against what the model asked is the integer-semitone quantisation of the byte itself, i.e. the format's floor. |
| ~~**KRZ filter-envelope depth is an unmeasured linear scaling**~~ | **FIXED 2026-08-22 (§KRZENVDEPTH2).** k2kremote read the depth byte at every consecutive value; it is a 0–127 index whose "cents" is a nonlinear panel display, ceiling 10800 ct = exactly 9.000 octaves. `round(amt * 127)` treated that ceiling as full amount — but the error was a **shape** error, not a scale one: because the curve is compressed near zero it wrote **23× too little** at amount 0.10 and 1.75× too much at 1.0, crossing over near 0.5. Subtle filter envelopes were effectively absent from every KRZ we wrote. The **reader** had the same error mirrored (`/10800`), so reader and writer were exact inverses and 433 tests saw nothing — self-consistency is not correctness. Law now lives once in `models/common.py`; four tests, three confirmed to fail when reverted. **Not hardware-confirmed end to end** — §MATRIX checks it. |
| ~~**KRZ LFO→pitch depth is an unmeasured linear scaling**~~ | **FIXED 2026-08-22 (§KRZLFOPITCH).** k2kremote walked CAL[22] byte by byte; ceiling is byte 123 = 7200 ct = 6 octaves. `round(amt * 79)` put full vibrato at byte 79 = **exactly 1200 ct, a clean 1.000 octave** — which is why this one was hard to see: the endpoint looked right. It is the value `LFO_PITCH_FULL_CENTS` (1593 ct, ±16 semitones, E4XT-measured) **already exists to replace**, and says so in its own comment. Below full scale the curve tracks cents 1:1, so small vibratos were written **20× too shallow** — 4 cents where 80 were wanted. Reader mirrored the error. Four tests, two confirmed to fail when reverted. **Byte↔cents now HARDWARE-CONFIRMED by audio at both ends** — byte 79 measured 2404.7 ct p-p against 2×1200 (0.2%), byte 41 measured 161.4 against 2×80 (0.9%). Those also establish that the K2000 panel's Depth is a **± half-swing**; `LFO_PITCH_FULL_CENTS` is specified the same way ("one-sided cents"), so the conventions match and no factor of 2 enters — a seam that would have validated on both sides separately while being wrong in the join. Byte 4 sits below the tracker's ~9–10 ct resolution and is reported as unresolvable rather than measured. **End to end still unconfirmed** — §MATRIX. |
| ~~**`FILTER_ENV_FULL_CENTS` disagrees with `E4B_FENV_OCT_PER_UNIT` by 41%**~~ **RESOLVED 2026-08-25 -- the quantity is not a constant (§SSCENTSDEPTHS)** | *(filed 2026-08-22, §FENVFULLSCALE)* Two constants for one quantity -- what a full FilterEnv->Filter-Freq cord is worth on the E4XT: **4383 ct (3.65 oct)** on the *input* path against **6168 ct (5.14 oct)** on the *output* path, composing rather than cancelling so an SFZ asking for 4383 ct reached an AKAI or K2000 as 6168. **The question as filed -- "does eosed §46 supersede MOD_DEPTH_CAL, or do they measure different paths?" -- had a third answer neither option allowed: they measure the same path from different BASE CUTOFFS, and the answer depends on the base.** The cord moves the cutoff BYTE linearly (`E4XT_FENV_BYTE_PER_UNIT = 2.506`, eosed 2026-08-24) and the byte->Hz curve is not a pure exponential, so a full cord saturates from essentially any base and "octaves per full cord" is just `log2(20 kHz / base)`. That reproduces **both** disputed figures: 3.65 oct <-> base byte ~193 (1559 Hz), 5.14 oct <-> base byte ~104 (549 Hz). Neither measurement was wrong; the name was. **The answer was already in the tree** -- `E4XT_FENV_BYTE_PER_UNIT`'s own comment, written two days after this row was filed, says the octave figure is base-dependent and calls it an artefact -- and nobody connected it to this row. **Fixed by removing the need for the constant:** `filter_env_cents` carries cents, the E4XT converts through its own corner (`e4xt_cents_to_cord_amount`), and the AKAI and KRZ writers use their own measured laws with no E-MU number in the path. Both constants survive as NOMINAL input spans for sources that state only a fraction, renamed in their comments to say so. |

| ~~**KRZ two-leg release wrote an upward "release" when sustain sits below the knee**~~ **FIXED 2026-08-27 (§KRZRELKNEE)** | *(found while confirming the AKAI->KRZ release-rate fix by ear)* `_fill_env`'s two-leg release always aimed Rel1 at a fixed **33% knee**, validated 2026-06-24 (AlphaPad #200) at a sustain comfortably above that. An AKAI source converted at **sustain 3.3%** (the key-tracked test EP, voices 1-3) writes Rel1 as "climb from 3.3% *up* to 33% over 5.2s" -- not a release, since a release only ever decreases, and undefined on real hardware. Measured on the bench: the audible tail collapsed to the noise floor by ~2.5-3s instead of the intended ~6.5s, matching neither leg's own nominal duration -- which is what read as "the release fix didn't work" before this was found. **Fixed:** when sustain is already below the knee, skip the two-leg shape and fade straight from sustain to 0 over the full release time (monotonic by construction); the high-sustain path (AlphaPad #200's case) is untouched. `test_krz_writer.py`/`test_krz_roundtrip.py` unaffected (18/18). **Confirmed on hardware the shape is now genuinely gradual** (a 7s-hold capture, past the 5.1s decay stage so release starts from a settled sustain, shows a real multi-second decline rather than a crash) **but the decline does not match the intended ~15.3 dB/s / 6.5s law** -- see §KRZLONGENVGRID below, which this finding exposed and is now blocking the audible confirmation of the release-rate fix itself. |

| ~~A KRZ envelope held past its own Att+Dec+Rel total RE-CYCLES instead of holding at silence~~ **FIXED AND HW-CONFIRMED 2026-08-31 (§KRZENVLOOP)** | **RESOLVED AND HW-CONFIRMED 2026-08-31, read this note FIRST:** k2kremote loaded the rebuilt `FROM_S3.KRZ` into a fresh, never-touched bank (program 302), read the raw AMPENV before touching anything (Dec1=0.06 correctly holds the decay value, Att3 back to a normal floor value, **Loop=Off**, clean), then isolated Layer 1 and held note 48 for 6s: one clean attack burst, decays over ~150ms, then flat at the noise floor (mean 2.8e-5, max 1.6e-4) for the entire remaining ~5.7s hold -- zero retriggering, matching the earlier clean hand-programmed control exactly. The old 10.03Hz retrigger is gone. **This closes §KRZENVLOOP: a real, fixed converter bug, not a K2000 hardware limit.** the ENV/ENC segment's real byte layout is byte 0 = loop flag, then seven `(level, time)` pairs from byte 1 -- NOT seven `(time, level)` pairs from byte 0 as `docs/KRZ_FORMAT.md` §4.4 claimed (falsely "HW-confirmed 2026-06-24"). Triple-confirmed 2026-08-31: k2kremote's controlled 991/992 single-byte DUMP diff, the reference preset Layer 2's own correctly-sounding envelope, and a genuine untouched ROM factory object (program 1, "Acoustic Piano", 7 independently distinguishable values matching field-for-field). `_env_time_byte` floors at raw value 3, so under the old (wrong) layout this writer put that floored value into what is *actually* the loop-flag byte on nearly every short/zero-attack envelope -- `3` there means an active loop back to Att3, which is the entire re-cycle mechanism below, start to finish. Not a K2000 firmware defect at all: a self-inflicted byte-layout bug in this converter's entire K2000-writing history. **Fixed in `writers/krz_writer.py::_fill_env`** (write side, now writes byte 0 = 0 explicitly and the seven pairs as `(level, time)` from byte 1) **and `parsers/krz_parser.py::_decode_env`** (read side, carried the identical error so re-reading an affected bank looked correct). New regression test `tests/test_krz_roundtrip.py::test_decode_env_rom_acoustic_piano_matches_the_corrected_byte_layout` uses the real ROM bytes and is confirmed to fail with the fix reverted. `docs/KRZ_FORMAT.md` §4.4 and `README.md`'s "Fixed defects" section updated. Full suite: 538 passed (same 2 pre-existing citation failures, unrelated). **Not yet HW re-confirmed**: rebuild the combined KRZ with this fix, reload on the K2000R, and have k2kremote re-test the reference preset Layer 1 -- expected to now hold cleanly at silence instead of re-cycling at ~10Hz. Everything below this note is the investigation trace that led here; superseded where it conflicts with this note, kept for the record.

**CORRECTED 2026-08-31, read this note FIRST (superseded by the RESOLVED note above, kept for the trace):** everything below was written when this was believed to be a general K2000 firmware defect. A clean control test settled that it is NOT: a hand-programmed envelope with the identical short decay, entered from the panel with no converter or SysEx involvement at all, does NOT retrigger, on the K2000R's actual final firmware (OS 3.87 -- there is no later version this could have been silently fixed in). So Kurzweil never needed to fix this, because a normally-programmed patch never exhibits it -- it is specific to something in the byte pattern this project's own writer produces, most likely the ENV loop-flag byte (found reading 0="Off" in the written file while the device's panel showed "Loop: seg3F/Inf" for that exact object -- a live contradiction not yet resolved, see the the reference preset entry below for the active thread). The timing formula (period = decay + ~41.7ms) and the "sustain doesn't hold" finding below are still real measurements, just not evidence of a firmware defect -- they are symptoms of whatever our writer is doing wrong. *(2026-08-27, §KRZENVLOOP, k2kremote co-investigated live over SysEx/panel)* `SPACE_ISO2` (real 5.1s decay, real 6.5s release, the §KRZRELKNEE shape fix applied) held for 22s: decays and releases cleanly on schedule, reaches the noise floor by ~11.5s after onset -- then **rises back toward peak over the next several seconds, plateaus around t=15-18s, and decays a SECOND time**, back to the floor by ~t=22s. Not a short glitch: a full second Att+Dec+Rel-shaped cycle, period ~11.6s, matching the encoded Dec1+Rel1+Rel2 total closely. Reproduces on a normal, real-source envelope, not just a synthetic edge case, so it plausibly affects every KRZ file this converter has ever written whenever a note is held longer than that preset's own envelope total. **Three causes ruled out on hardware, not just by reasoning:** (1) ENV segment **byte 14** ("loop flag" per `docs/KRZ_FORMAT.md` §4.4) -- k2kremote read the AMPENV panel's real Loop field (Type=Off/seg1F/etc, separate from the 7 time/level pairs; the K2000 manual, `~/temp/k2000_manual.txt` lines ~3780-3810, documents 7 values and states loop only ever revisits an ATTACK segment, and release is always gated on Note Off "regardless of loop type"). A matched A/B, same note/hold, Loop=Off vs Loop=seg1F on object 906: **both show the same unexplained recurrence at the same time**, seg1F only adds ITS OWN extra burst on top, exactly matching the manual's documented behavior. Loop-Type is not the cause. (2) A too-quiet sustain misread as silence -- ruled out from the data itself: the level passes straight through the 3% sustain band and keeps falling to the noise floor, on a timeline matching decay+release, not a plateau. (3) The MIDI routing layer (`mididings_k2000r`) synthesizing a spurious Note Off/On -- ruled out with a direct wire capture (`aseqdump` on the port actually feeding the K2000): one Note On, one Note Off, nothing else, for the entire 20s hold. **So this is real K2000 firmware/engine behavior, internal to the instrument, contradicting its own manual's "release starts only at Note Off" -- for envelopes whose Dec+Rel total reaches roughly this length.** Sample loop points checked and look sane (its component sample: loop 51646-51982 of 52483, forward, well-formed) -- not yet ruled out as a contributor, but no evidence pointing at it either. **Blocked on:** finding the actual trigger condition (does a shorter total avoid it? is there a hardware timeout/voice-management mechanism unrelated to the documented envelope model?) or accepting it as a hardware limit and keeping written envelope totals safely under it. Do not trust ANY KRZ-written envelope, long or short, to hold at sustain/silence past roughly its own Att+Dec+Rel duration until this is settled or a safe ceiling is established. **Candidate connection, not yet checked (2026-08-30):** both KRZ-involving routes in the confidence-matrix rebuild show envelope/sustain matching getting WORSE with today's code -- KRZ->E4B (reading KRZ envelopes) 8/12 FURTHER, E4B->KRZ (writing them, k2kremote) 8/10 FURTHER, confirmed above this row's own ~0.06 noise floor on both. The AKAI route improved (6/10 closer) with the same-era release-rate fix. If this envelope re-cycle bug is quietly affecting where a fixed-time-offset sustain sample lands on either side of a KRZ round trip, it would explain both "regressions" as one bug rather than two -- worth checking before chasing either separately. **Checked directly (2026-08-30, k2kremote, live AMPENV reads on 8 of 10 E4B->KRZ patches): partial support, not the whole story.** The three worst FURTHER regressions (PC 406/407/408) all have total envelope durations well under measure.py's 1.6s sample point (0.18-1.06s) -- exactly the re-cycle-risk shape, and 406's envelope (0.18s total) is by far the largest regression in the whole set. But three long-envelope patches (402/403/405, totals 6.4-8.2s, safely past any re-cycle) still split 2 closer / 1 further -- so KRZENVLOOP plausibly explains most of the worst cases but not a smaller effect underneath on patches where it cannot apply. **Reads best as two effects layered together, neither fully proven from this alone:** the re-cycle bug catching a wrong point on short envelopes, and a separate, smaller, still-uncharacterised writer-side sustain effect on longer ones. Two patches (400, 409) not read due to bench/tool issues, not gaps in the hypothesis -- recoverable if worth another pass. **MECHANISM CHARACTERIZED, 2026-08-31, via the reference preset's own Layer 1 (the mute-cut click voice, decay=0.058s -- see the the reference preset entry below for the full trace):** k2kremote measured the flutter rate at three decay settings (0.040s, 0.058s, 0.100s) against three competing models s3ked proposed after their own first prediction was refuted by the data. Result: **`period = decay_time + ~41.7ms`** fits all three points to within 0.1-1.7% (12.29/9.86/7.05 Hz measured against 12.24/10.03/7.06 Hz predicted); the two competing models (proportional scaling, and a rate independent of decay time entirely) are both clearly excluded. **This answers "does a shorter total avoid it?" from this row's own original blocked-on: no -- the fixed +41.7ms overhead means EVERY envelope re-cycles eventually, including the original 11.6s `SPACE_ISO2` case (11.6s decay+release + 41.7ms is consistent with the ~11.6s period originally measured, to within the precision either measurement had). A longer envelope does not escape the bug, it only slows it -- lengthening a too-short envelope is a real, substantial mitigation (a slow, infrequent pulse instead of an audible flutter) but not a fix. The root firmware cause of WHY the K2000 re-cycles at all, and what the +41.7ms overhead physically corresponds to, remains open.** **s3ked's structural-fix candidate (nonzero sustain stops a completion-triggered re-cycle) REFUTED same afternoon:** Dec1%% 0->30 on the same layer, held 5s, retrigger rate unchanged (9.99Hz either way) right to note-off -- the re-cycle is genuinely time-based, not completion-based. **So there is currently NO known way to eliminate this bug via envelope shaping, only slow it.** Root cause search would need deeper firmware reverse engineering than this session had room for. **Formula CONFIRMED EVEN MORE STRONGLY, same afternoon, at a 4th point (T=1.0s, 25x the smallest T tested): after retracting an intermediate mis-read caused by a spurious onset-detection bug in a one-off script (see the the reference preset entry below), a clean re-run with WALL-CLOCK-VERIFIED note-on/off timing found 7 onsets at ~1040ms spacing (std 4ms) = 0.96Hz, matching `period=T+41.7ms`'s 0.96Hz prediction almost exactly, running continuously for the entire 8s hold.** Separately, confirmed on the same clean capture: **sustain genuinely does not hold** on this layer (trough 0.8-0.9%% of peak during an unambiguously-held note) -- a real, separate finding, independent of the re-cycle bug, potentially affecting every sustaining K2000 patch this project has converted. Not yet scoped or chased further. |
| ~~**`KRZ_ENV_TIME_GRID`'s 5-10s step (0.10 s/byte) may not be hardware-validated at these durations**~~ **CLOSED 2026-08-31 -- THE WHOLE GRID IS HW-CONFIRMED, EVERY BAND, BOTH AXES** -- *(k2kremote, sawtooth rig)* displayed step size click-mapped end to end with no audio interpretation: **0.020 s/click from 0.020-2.000, 0.040 from 2.000-5.000, 0.100 from 5.000-10.000, 0.500 above 10** -- every step exact, no drift, no irregular transition, matching `KRZ_ENV_TIME_GRID` in full. Displayed-vs-ACTUAL time audio-measured in the long band: 6.000 s -> 5.986, 8.000 -> 8.026, 10.000 -> 9.976, **mean ratio 0.9995, sd 0.0027 -- within 0.3%.** **The earlier 3% figure was k2kremote's own measurement systematic, not a device offset, and they said so unprompted:** extrapolating a dB-linear fit into the rounded bottom of a short decay overshoots proportionally more when the whole decay is 160 ms, so 1.031 (sd 0.0063) is the error bar on the short end rather than a real device error. The grid reads as accurate throughout. `r2 = 0.995` at all three long settings, so **dB-linear holds across the full 0.16-10 s range**, not only where it was first found. **the reference preset's own 5.1 s pad decay therefore now sits inside a verified band**, so tonight's pad-envelope conclusions no longer rest on an unverified grid. **BOTTOM STEPS ALSO AUDIO-VERIFIED (2026-09-01):** displayed 0.020 s measures ~21 ms and displayed 0.040 s measures ~42 ms, both within ~5% of nominal. The obstacle had been physical, not methodological, and naming it was the fix: at note 48 one period is 7.65 ms, so a 20 ms decay spans under 3 cycles and no envelope method can resolve it. Playing **note 96 (2093 Hz, period 0.48 ms)** puts ~42 cycles inside a 20 ms decay and makes a 1 ms window meaningful. Validated by re-measuring 0.200 s and 0.100 s on the new rig first (203.0/103.8 ms, reproducing the earlier band results), then agreeing across three independent window sizes at every setting -- and the 5 ms window correctly reported *unresolved* at 20 ms rather than inventing a number. **This closes the last 'click-map-confirmed but audio-unverified' gap sitting under a decision Jan will hear:** the smallest expressible step really is 20 ms, so a 5 ms hold and a 12 ms knee genuinely are unrepresentable and 12 ms really does round into the same byte as 30 ms -- the reasoning that killed the two-segment choke refinement stands. Also: **dB-linear now holds at r2 >= 0.995 from 20 ms to 10 s, nearly three decades**, so that law is no longer an observation from one band. *(superseded status:* 0-2s AND 2-5s BANDS NOW HW-CONFIRMED EXACT (2026-08-31); 5-10s STILL OPEN and being measured*)* -- *(2026-08-31, k2kremote, sawtooth rig)* click-counting gives exactly 0.020 s/step from 0.020 through 2.000 s and 0.040 s/step above it, matching the table's claim for both bands with no exceptions. Displayed-vs-actual time tracks to **~3% (mean ratio 1.031, sd 0.0063 across 13 points spanning 0.16-2.8 s)** with no offset and no band-dependent break. Independent cross-check: measured decay rate x displayed time is constant at 28.0 dB across the whole sweep, against the separately-measured `KRZ_LEVEL_PCT_DB` figure of -28.03 dB for 100%->25% -- **two independently measured tables agreeing to 0.1 dB.** Also settled here, correcting an earlier claim of k2kremote's own: the decay segment is **dB-LINEAR** (constant amplitude ratio per unit time; dB-vs-time fit r2 0.986 against 0.69 amplitude-linear), not amplitude-linear as briefly reported -- that shape decides between "we linger" and "we lack attack" on the choke, so it mattered. **Remaining holes:** the 5-10 s band (where the reference preset's own 5.1 s decay sits) is being measured now; and the bottom two steps (0.020/0.040 s) decayed faster than a 10 ms analysis window could resolve, so their ACTUAL times are unverified -- load-bearing, because tonight's "the AKAI choke shape is unrepresentable on this grid" conclusion rests on the bottom step really being 20 ms. Incidental: visible stair-stepping at 2.8 s (flat runs of ~0.42 s between drops, well above floor) suggests the envelope generator quantises its updates coarsely at long times. **Original note:** | *(2026-08-27, §KRZLONGENVGRID, found chasing §KRZRELKNEE)* This week's "K2000 is a rate machine" work (§CORPUSRT) measured Rel1 at **1.00s and 3.00s** -- both inside the grid's finer 0-2s/2-5s bands. The key-tracked test EP's isolated voice (release fixed to write **5.1s decay + 6.5s release**, both in the coarser 5-10s band) shows a real bench capture that is neither: a fast ~14 dB drop in the first 0.2s, then an unusually SHALLOW tail (~0.8 dB/s, not the intended ~15.3 dB/s) that has only reached -20 dB by 8s. **This shape is now explained by §KRZENVLOOP's retriggering aliasing against sparse sampling, not a grid-step error** -- a bench sweep built to isolate the grid (`gen_krz_envgrid_cal.py`) hit the SAME retrigger on every point, confirming the grid could not be cleanly measured until the loop is understood. The grid question is not closed, only deferred behind it: once byte 14 is settled, re-run `tests/re_banks/measure_krz_envgrid.py` and this row's original two hypotheses are still the ones to check. |

| **AKAI filter-envelope attack: the field is live below byte 40** | *(2026-08-22, §ATKMEAS)* Measured across `ATTAK2` 0→72, ten programs, three takes. **The field IS live below 40** — the 0→40 range spans about 20 ms — so our clamp at byte 40 costs that much attack range and §ENV2FLOOR is answered. **The shipped law is NOT shown to be wrong:** an initial claim that its slope was 45% out was withdrawn after a 4× finer re-run — the fit had been contaminated by points at the resolution limit and by byte 72, whose rise is 22.6 dB against ~33 elsewhere. On well-resolved points the slope agrees to 17%, and the remaining ~4× prefactor ratio is the observable: HF energy reaches 90% of its rise well before the envelope reaches level 99, so a partial traverse was being compared to a full one (§ENVRATESLOPE). Open only in that the clamp could be lowered; no law change indicated. |

## Open at a glance (2026-08-01)

This file is long and mostly archive — resolved entries are kept for their
reasoning. What is actually **open**, grouped by what unblocks it:

### Needs the E4XT / K2000 bench

| item | note |
|------|------|
| **SF2 static filter** | the gain half is resolved and verified; the *filter* half still has no hardware A/B |
| **VinSamLib confirmation batch** | needs rebuilding first — it predates the stereo decode fix and the zone-reducer fixes, so the images test code that no longer exists. **Also predates the KRZ keymap `i+12` fix**, so any multisample KRZ bank in it is one of the banks §KRZKEYMAP says must be regenerated — rebuilding is now required for correctness, not just coverage |
| **Two third-party banks may share our old keymap off-by-12** | A guitar bank on a commercial K2000 CD-ROM library (`library disc T`, 11 of 13 zones) and one on a third-party K2000 floppy soundset (`soundset F1`, 2 of 3) are the only 2 of 2289 hardware-sourced banks that VinSamLib's `tools/check_krz_banks.py` flags as keymap-shifted, and both carry *our* exact keymap write form (method `0x13`, basePitch 0, 100 cents, 128 entries, entrySize 5) despite being third-party conversions. Play adjacent keys and listen for one sample key-tracking. **Either outcome is worth having:** if they are shifted, a third-party converter made the same `i+12` mistake and that is a format-knowledge datum like the CWM findings; if they are fine, the root-inside-zone heuristic has a ~2/2289 false-positive rate and VinSamLib's scanner should say so |
| **KRZ program params, bandpass silence, the wide-drone preset** | several K2000-side items, all needing the K2000R |
| ~~**K2000R LFO1->pitch depth distorts away from a voice's root key**~~ **WITHDRAWN 2026-08-31, same day -- see the dedicated row below** | was an analysis-window artifact (the sideband tool's default window too short to resolve this program's ~2Hz LFO rate), not a real effect. §KRZROOTLFO |
| **K2000R "Object → Delete" lockup** | needs factory resets; root cause was traced to k2kremote, not this project |
| **K2000R sustain LEVEL is rendered far quieter than programmed -- the TIMING is exact, only the level is wrong (2026-08-31, re-scoped; the earlier "sustain does not hold" framing was measured on the click layer and is withdrawn) -- general blast radius not yet scoped** | trough at 0.8-0.9%% of peak during an unambiguously-held note (verified MIDI on/off timing); may affect every sustaining K2000 patch this project has converted, not just the choke/re-cycle case it was found in. **Ruled out as the same root cause as §KRZENVLOOP, 2026-08-31:** k2kremote re-ran the identical Dec1%%=30 test on the reference preset Layer 1 AFTER the byte-layout fix landed (Loop now correctly Off, Dec1 time correctly 0.06s) and got the same pattern as before the fix -- quick decay to a low floor (mean 1.5%, max 5.1% of peak over a 0.5-5.3s window), no real 30% plateau. Persists identically on the corrected object, so this is a genuinely separate, still-open bug, not a symptom of the loop-flag mis-write. Needs its own investigation. §KRZENVLOOP **RE-SCOPED 2026-08-31, late: the original framing was wrong because it was measured on the wrong layer.** Both this row and §KRZENVLOOP's "release stages advance regardless of note-off" mechanism had been measured on Layer 1 ONLY -- the choke click, whose envelope is designed to reach silence in 0.24s and would look identical whether either claim were true or false. Tested properly on Layer 2 (k2kremote, isolated, 18s hold, verified MIDI timing): the level settles by ~3s and holds FLAT for the remaining 15s, straight through 5.1s and 10.3s, unchanged across note-off. **The release stages do NOT run while a note is held, and §KRZENVLOOP's mechanism does not generalise beyond the click layer.** A dedicated timing test (Dec1 5.10s @ 50%, Att1 0, Layer 2 solo, note 48 vel 127, 9s hold) then confirmed the decay's SECONDS are exact: plateau reached within 0.5dB at t+4.97s against a programmed 5.10s, ~1%. A rate-machine hypothesis (that Dec1's time means seconds-to-cross-a-fixed-span, as the RELEASE does per §CORPUSRT) predicted 0.30s and is refuted; the staged code change for it was fully reverted. **What remains is purely a LEVEL error:** that same capture's plateau reads -31.84dB where a 50% sustain should be about -6dB, and ~16dB is unexplained even after allowing the sample's own loop content (-9.5dB below its early peak). At the real patch value of 3% the plateau lands at or below the rig noise floor (-54dB, measured against 6s of recorded silence at identical gain) and is simply inaudible -- which is exactly Jan's report that the AKAI's sustain is "louder and more prominent". Also settled in passing (answers s3ked's open question): the K2000's decay segment falls straight in AMPLITUDE, not in dB -- steepest early, shallowing toward the plateau. **ROOT CAUSE FOUND 2026-08-31 (§KRZLEVELCURVE): the K2000's envelope LEVEL field is DB-LINEAR, not the linear amplitude percent `_lvl_byte` writes.** Measured on a purpose-built RAM-only rig (sawtooth ROM keymap, filter NONE, no LFO, only Dec1's level swept, everything referenced to the 100% capture's own plateau): 50% displayed is -18.07dB, not -6dB; 25% is -28.02dB, not -12dB. Over 25-71% the field is dB-linear at **0.398 dB per displayed-% unit**, fitting to within 0.02dB at four points, then breaking at both ends (+1.83dB at 100%, +4.28dB at 12%) -- dB-linear in the middle, a curve at the extremes. **Third instance of one pattern in this writer** (after §KRZENVDEPTH2 and §KRZLFOPITCH, both plausible-linear-mapping-onto-an-actual-curve, both fixed with a measured table + interpolation). Note the symmetry: the AKAI's own SUSTN1 is dB-linear too (0.60676 dB/unit, `_AK_SUSTAIN_DB_PER_UNIT`, measured since August) -- **both machines store sustain in dB and only the K2000 side was read as linear amplitude.** For the reference preset: the AKAI's -29.73dB sustain needs Dec1 ~= 20.7%, we write 3%, which measures at or below the rig noise floor -- 7 to 15dB too quiet, exactly Jan's complaint. **FIXED 2026-08-31** from a full 25-point measured sweep: `KRZ_LEVEL_PCT_DB` + `krz_level_pct_to_db`/`krz_db_to_level_pct` in models/common.py, consumed by `krz_writer._fill_env` (sustain now converted through the curve, not multiplied by 100) and mirrored in `krz_parser._decode_env` (the ratio of two displayed percents is not an amplitude ratio -- that error read every K2000 program's sustain far too HIGH, affecting every K2000 source we read). **the reference preset's pad sustain now writes 21%, measuring -29.84dB against the AKAI's own -29.73dB: 0.11dB.** Was 3% / -69dB, i.e. ~39dB too quiet. Suite green at 543; tests confirmed to fail if the table is swapped for a naive linear-dB law, so they pin the curve's shape rather than mere reader/writer agreement. **Shape:** two dB-linear segments (0.335 dB/unit above 75%, 0.398 from 71 to 25%) then an accelerating collapse (0.70 at 22%, 1.34 at 12%, 5.96 at 6%, 9.09 at 4%). 2% and 1% were floor-limited and non-monotonic and are excluded from the table rather than recorded as values. **Free hardware finding from the method:** F4 AMP Adjust saturates well before its 48dB maximum on a full-level signal (at 36dB, 100% vs 50% differed by 3.7dB instead of 18). **Knock-on deliberately NOT applied:** `_REL_KNEE_PCT = 33` was chosen meaning -9.6dB and actually measures -24.8dB, so the two-leg release knee has always sat ~15dB below its label -- but that shape was validated BY EAR (AlphaPad #200), so what a listener approved is what the constant really produces. Label corrected in code, sound untouched, re-derivation left for the next by-ear release validation. **Still open:** whether the same curve governs the ATTACK and RELEASE stage levels or only Dec1 (`_fill_env` writes all seven through one encoder, and the filter envelope 0x22 uses the identical function) -- on the night-run list. *(superseded note:* fitting from six usable points that break at both ends would extrapolate into 3-12%, which is where real material lives and where the data is weakest.*)* **Blocked on:** a fuller sweep -- the low end lifted off the noise floor (12/9/6/4/3/2/1%), the top end where the 100->71 step is steepest (100/95/90/85/80/75%), mid-range fill-in (60/45/40/30/22%) -- plus one question that decides the fix's width: does the same curve govern the ATTACK and RELEASE stage levels, or only Dec1? `_fill_env` writes all seven stage levels through one encoder and the filter envelope (0x22) uses the identical function. *(superseded blocked-on:* a reference-free level-law calibration -- a purpose-built RAM-only program on a flat sustained ROM waveform, Att1 0, Dec1 time fixed, sweeping ONLY Dec1's level (100/71/50/35/25/18/12/6/3%). Consecutive differences must be 6.02dB per halving if the field is linear amplitude percent; any reference or sample-contour error cancels in the differences. If the law is a curve rather than linear percent, this is the same shape of defect as §KRZENVDEPTH2 and §KRZLFOPITCH. Next suspect after that: the AMP block's own VelTrk=35dB / Adjust=6dB, inherited wholesale from the #199 template and never deliberately set by this writer.)* |
| ~~**AKAI: we write PMCHAN 255 (OMNI) on every program**~~ | **FIXED 2026-08-18 — default is now PMCHAN 0.** Across 11410 factory S3000 programs, 3 use OMNI (0.03%), and 1545 factory volumes with 2+ programs put **every program on channel 0** against ~35 using several. The real machine's own program holds 0 too — `test_only_two_bytes_differ_from_the_real_machine` had recorded that disagreement for months without anyone asking which side was right; it is now one byte. **Tested before changing:** a 21-program converted volume bulk-loaded on the S3000XL selected correctly under OMNI, nothing stacked, so this was not a bug fix. Changed because omni makes MULTITIMBRAL use impossible — every program answers every part, invisibly. `--` bench discs keep the per-program channel override they need. §AKAIRELTEST |
| ~~**KRZ reader under-reads envelope attack time**~~ / ~~**E4B→KRZ lands 10 cents sharp**~~ | **BOTH WITHDRAWN 2026-08-22, same evening they were raised (§MATRIXRESULT).** Neither survived drilling into it; all three signals were my instrument, by three different mechanisms. **(1) The analysis window was 0.45 s early on every machine and 0.60 s early on the K2000**, because the schedule reconstruction omitted `record_program`'s program-change settle (and the K2000's extra bank-select wait). A *different* offset per machine, in a comparison whose subject is cross-machine agreement. Fixing it collapsed the tuning claim from **+9.5 ct to +0.1 ct** — and the mechanism is instructive: the K2000 conversions now carry 100 ct of vibrato (tonight's LFO fix), so sampling 0.15 s later than the source read a different **LFO phase**. It was never tuning. **(2) The attack metric is transient-sensitive**: 10→90% of smoothed peak, where one onset frame grazing the peak makes a slow organ swell measure as instant. A transient-robust redefinition flipped the row median from **−0.77 to +3.27 octaves** — two defensible definitions, opposite signs, so neither measures a real property of this material. **(3) Spectral centroid disagrees with 85% rolloff** on the same captures (−0.98 oct vs 0.00), because centroid is dominated by HF tails and therefore by noise-floor differences between machines. **What survives is a positive result:** with the window corrected, every one of the six rows is tuning-accurate to within **1.4 cents**, and across 56 conversions there were no silent patches, no octave errors and no dropped notes. Before any of this is re-raised, the harness needs an envelope-shape comparison that does not reduce to a scalar, and a brightness measure robust to the noise floor. |
| ~~**Does the XPM reader read the AMPLITUDE envelope?**~~ | **ANSWERED 2026-08-23, THE SAME HOUR IT WAS RAISED — yes, correctly, no bug.** Raised on a `grep -c "amp_env"` returning 0 in `xpm_parser.py`. That was the flaw, not the parser: it reads `VolumeAttack/Decay/Sustain/Release` into locals and passes them under different constructor names, so the literal string never appears. Verified end to end against a real MPC-authored keygroup program from Jan's backup — `VolumeRelease 0.0229` in the file arrives as `amp_env.release = 0.000988 s` in the model. **Also settles the units question:** XPM stores envelope times as **normalised 0.0–1.0 controls, not seconds** — the milliseconds are the firmware's *display*, which is how the 3.x curve was calibrated (dial detents read against that display). Both generations carry hardware-measured constants; see §MPCENV. **Fourth instrument error of the night** — the pattern is now unmistakable: a negative grep is not evidence of absence. |
| ~~XPM input unaffected by the cents-depth conflict~~ | **CHECKED 2026-08-23, no action.** §FENVFULLSCALE (the 3.65 vs 5.14 octave disagreement) only bites sources that specify depth in **cents** — sfz `fileg_depth`, sf2 `modEnvToFilterFc`. The XPM parser reads `FilterEnvAmt`, `LfoPitch` and `VelocityToFilter` as **direct 0..1 amounts** and touches none of the cents helpers, so XPM input is not exposed to it. Recorded so the question is not re-opened. **Conversely the KRZ writer fixes DO reach XPM→KRZ**: `filter_env_amount` and `lfo1_to_pitch` are exactly the two fields whose KRZ mapping was wrong, so any XPM-sourced KRZ with a filter envelope or vibrato carried the same 23x/20x errors and is fixed by §KRZENVDEPTH2 / §KRZLFOPITCH. Same for `AKAI_ENV2_DEPTH_MAX` on XPM→AKAI. |
| **`AKAI_ENV2_DEPTH_MAX` over-delivers by 2.5–6.7×, and it is not a single constant** | *(2026-08-23, §AKAIENV2DEPTH)* Found by measuring the two machines against each other rather than arguing from laws. The AKAI's transient carries a **resonant peak at 6–10 kHz** (+10.8 dB over its own 500–1000 Hz band, with the bands either side 10–20 dB below it); our E4XT conversion has **nothing there** (−7.7 dB), and both machines roll off alike above 12 kHz so it is not a bandwidth difference. Cause: `18.30` makes the source's ENV2 depth 25 worth **7.02 octaves**, which sweeps our corner **past 19 kHz** — out of the audio band, where the resonance is inaudible no matter what Q we write. **That retires the Q ceiling and the cord clamp as explanations** and explains why four filter tests in a row returned clean nulls: the filter was never in circuit. eosed then aimed at the corner instead of a number and measured the amounts three octave voices actually want — **32, 15 and 39** where we write 100 — producing a peak in the 4–10 kHz band and a drop above 10 kHz, the same shape as the AKAI. **The spread is the finding:** the same octave shift from three different base cutoffs needs three different amounts, so whatever replaces 18.30 has to interact with the base and cannot be one number. Do not fit one constant to these three points; the depth law itself is unmeasured. The unison layers still sweep past 19 kHz and are the next place to look. |
| ~~**AKAI reader never assigns `amp_env` — every AKAI-sourced voice gets the default envelope**~~ | **FIXED 2026-08-23, with tests.**  *(2026-08-23, §AKAIAMPENV)* **Third defect on the same function, found by Jan's ears after the first two were fixed live on hardware.** `build_preset_from_program` sets `filter_cutoff` and `filter_env` and never touches `amp_env`; the keygroup's `amp_attack/decay/sustain/release` are parsed at line 506 and never read. The source's six keygroups carry two distinct envelopes and our E4B gives all six the same default. **Scope confirmed on the device by eosed:** the amp envelope is byte-identical across all six voices while the FILTER envelope correctly differs, so it is specifically ENV1→amplitude that is lost. **My first explanation was wrong and Jan caught it** — I blamed a 31 ms attack, but the writer clamps fast attacks to rate 0 (instant) and the 31 ms was my own parser's readback of rate 0, an extrapolation one step below the calibrated range whose own comment says "rate 0 = instant". The real fault is that the envelope **never decays**: sustain reads 96% on the machine and the one slow stage travels four percentage points, so the voice jumps to full and holds. The source wants sustain byte 6 of 99, a percussive decay to nothing — that is the missing "metallic klick", a click that never stops. **It also explains "still one octave low", which is not a pitch error:** the source's unison layer decays to nothing (sustain byte 6/99) while the octave layer sustains, so the ear takes its pitch from the octave; we give both a sustain of 0.821, so the unison layer wrongly sustains and carries the perceived pitch an octave down while every stored pitch value is correct. **Resolves §AKAICAPTUREGAP** — the mid-note analysis window found no fundamental because the unison layer had already decayed; the measurement was right and the inference was wrong. Fix: invert `akai_env_bytes`. Not applied mid-audit. |
| ~~**AKAI reader drops per-zone loudness and writes +1 dB where it means unity**~~ | **FIXED 2026-08-23, with tests.**  *(2026-08-23, §AKAIZONELOUD)* Predicted by s3ked while reviewing the tune bug, confirmed the same minute from the file and then **HARDWARE-CONFIRMED ON BOTH PANELS** — the AKAI shows non-zero `loud` on the +12 keygroups, the E4XT shows `+1` on every voice volume, which is the `volume=1.0` constant displayed as the +1 dB it actually means. Very likely also the second symptom Jan heard** — he described the difference as "in tuning ... and in high frequencies", and an octave layer rendered 20 dB hot is the bright half of the patch. The filter path is a second candidate and is not excluded. `build_preset_from_program` constructs every zone with `volume=1.0`: the source's VLOUD1 is read into the zone dict and then ignored, **and** `ZoneMapping.volume` is documented `# dB, -96..+12` where unity is `0.0`, so the constant adds a spurious +1 dB to every AKAI-sourced zone. The writer has carried the measured law since 2026-08-17 (`dB = 0.60576*VLOUD1 - 20.1778`, r² 0.9999) and its own comment records that **14.8% of corpus zones** carry an offset. **Second instance of one pattern:** tune fixed in the writer 2026-08-11, loudness 2026-08-17, reader left alone both times — worth the rule that correcting a writer's unit includes the reader for that field. Neither would survive an AKAI→AKAI round-trip test, now asked for by two findings. Fix: `volume=z.get('loudness', 0) * 0.60576`. Not applied mid-audit. |
| **The capture that started the tune finding does not match the file** | *(2026-08-23, §AKAICAPTUREGAP)* Kept separate because the reader bug is proven without it and this is not proven at all. The file says both layers sound at full level on every note and velocity — LOVEL 0/HIVEL 127, CP 0, SPITCH matching the key ranges, SSRATE uniform, both samples present — and s3ked confirmed all of it through their own parameter table. The capture shows the source's fundamental **57–72 dB below** its octave with the odd harmonics down 70–81 dB while the even ones are strong. s3ked's proposed explanation (an octave layer reinforcing even harmonics of a weak-fundamental EP) is refuted by that odd/even structure — reinforcement cannot suppress 3f by 70 dB — so the unison layer really is absent from that capture. **Why is open.** Three candidates, none favoured: the card's MX3 is not the staging image we read (s3ked identified those volumes by content, not by name); something silenced the layer at play time; or the capture is mislabelled. Ruling out the first needs a card read, not a listen, and comes first. Must not be cited as evidence for anything else meanwhile. |
| **Cutoff and resonance are not independent on the E4XT, and our cutoff table is 0.4 octaves dark above byte 64** | *(2026-08-24, §E4XTQSHIFT)* **Two findings, both measured, neither fixed.** (1) Twelve bytes measured at Q 0 against `_E4XT_CUTOFF_TABLE`: only byte 4 agrees, and from byte 64 up we are 0.38–0.73 octaves too DARK. Every E4B we write has its filter a third of an octave low — and the 2026-08-23 end-to-end check passed only because it was done at byte 4. Not fixed: the table feeds formats with no hardware calibration and its own comment warns that moving it moves them silently. (2) **Setting Q moves the corner** — up to a full octave at byte 135 between Q 0 and Q 112 — and both the peak and the −3 dB crossing move, so it is real. Items 3 and 4 wire cutoff and resonance independently and on this machine they are not. Re-aiming at each voice's real Q left **no residual** (0.964/1.005/1.007), so a Q-aware correction is the only thing between the law and the machine. The shift is close to **separable** (`f(Q)·g(byte)`, same shape to ~8%), so a product of two 1-D curves would likely do — but 3 bytes × 4 Q values is not enough to fit. **Also a policy question:** an AKAI keygroup whose FILQ lifts the corner above its FILFRQ target is unreachable (measured: target 207 Hz, floor 523 Hz at cord 0), and the writer must choose between matching the sweep, clamping, or dropping resonance. |
| ~~**`akai_env2_stage_seconds` scales every stage by `distance/99` and nobody has measured that it should**~~ **ANSWERED 2026-08-24: it is a rate, measured** | *(2026-08-24)* The constants are documented as *"times for a FULL 0..99 traverse"* and the comment says *"A stage covering less than the full range takes proportionally less"* -- **stated as a fact with no measurement cited**. For ENV1 that property was **established**, by the varying-span test that holds the value and changes the distance (rate constant to CV 0.27% on DECAY1 while the time moved 18.8%); that test is what withdrew every ENV1 timing constant we had. **Answer: half.** It HAD been run on ATTAK2 (distance varied 4.76x, seconds-per-octave holding to 4-9%). It had **never** been run on RELSE2 -- that stage's measurement varied the VALUE and never the DISTANCE, and inherited the conclusion from a closing sentence. **Now measured (s3ked, 2026-08-24):** at RELSE2 65 and 75, distance x2.02 gives TIME x1.93 / x1.87 and RATE x1.11 / x1.15 -- time tracks distance, the rate does not move, two independent settings agreeing. **Our `distance/99` is correct.** Free cross-check: the two settings' full-distance ratio is 2.707 measured against 2.636 predicted by a law not fitted to this run, **2.7%**. And the generalisation was NOT safe even though it held -- envelope 3's release scales at 0.762 of its decay where envelope 1's is 1.004, so stages of one envelope need not agree. Matters more than it looks: the filter's share of an audible fall can exceed the amplitude envelope's by 1.8x on a bright transposed sample. **Corpus scan says the RANGE question is nearly closed** (26979 keygroups, 21 discs): RELSE2 only **9.1%** outside its fit against RELSE1's 79.8%, DECAY2 ~2% once byte-0 'instant' is excluded. **ATTAK2 is the exception** -- ~25% of keygroups sit in bytes 1..39 below the fitted floor, byte 30 alone being 15.7% of the corpus, so a narrow 10..45 sweep would cover a sixth of all real material. `tests/re_banks/corpus_scan_env2.py`. |
| ~~**`*->AKAI` MERGES LAYERED KEYGROUPS INTO ONE**~~ **FIXED 2026-08-24** | *(2026-08-24, found by the conversion-matrix regression check -- PRE-EXISTING, not from that day's fixes)* A source preset whose layers differ in ENVELOPE is written as **one keygroup with two zones**, and the second layer's envelope is **discarded**. Measured on an AKAI->AKAI round trip: source has **6 keygroups** in 3 pairs, each pair one percussive layer (SUSTN1 6, RELSE1 45) and one sustaining layer (SUSTN1 50, RELSE1 75). Output has **3 keygroups**, all carrying **SUSTN1 0, RELSE1 45** -- the click layer's envelope on both zones. The sustaining half of the preset loses its sustain and its release entirely. Both zones are also written at **velocity 0-127** in the same keygroup, so they overlap. **The source used six keygroups precisely because two layers needing different envelopes cannot share one.** **FIXED:** grouping is now keyed on (key range, keygroup-settings fingerprint), and the fingerprint is produced by *calling* `_keygroup` with an empty zone list rather than by listing the fields it reads -- a hand-kept list would be a second copy of the rule, which is what most of this week's defects were. One shared `_group_zones_into_keygroups` now serves both the writer and `keygroup_count`, so the object budget and the file cannot disagree. **Cost, measured on four sources: only the layered one moved, 24 -> 27 keygroups -- which is the SOURCE's own count, so the round trip preserves GROUPS exactly.** Object budget is not a constraint at this scale (s3ked measured the pool exactly: 6 programs + 27 keygroups + 16 samples = 49 of 1006 blocks). **Still open for a dense multisample:** a 12-program stereo volume at ~20 keygroups each would double past half the pool, so that case wants a budget check rather than an unconditional split. |
| ~~**AKAI filter-envelope attack: ~25% of keygroups sit below the fitted floor**~~ **CLOSED 2026-08-24: leave it alone** | *(s3ked §164)* Swept 0..45 with byte 0 included, after a **control run** established the rig cannot resolve below **10 ms**. **Byte 0 is instant to within that**, and the law's own prediction for it is **1.4 ms** -- so our special-case-to-zero is safe and we are not inventing a transient. Better: the law reaches 10 ms at **ATTAK2 21**, so bytes **0..20 are instant-or-indistinguishable by the law AND by measurement**, two independent routes agreeing a whole region does not matter. **So the 25% is not 25% of exposure** -- only bytes 21..39 are real, and byte 30 (15.7% of the corpus by itself) measured 30 ms against the law's 25, so the extrapolation is roughly right where it matters most. **Not widening the fit:** the two points inside the fitted range agree to ~10% while the two below it read 1.20 and 0.74 -- scatter, not a trend, with 35 reading faster than 30, which is the instrument. The fit's floor (40) and the rig's floor (~21) leave almost no room to work in; closing it needs a faster instrument, not more points. |
| **AKAI->AKAI re-interprets a mute group into envelope values it did not need to** | *(2026-08-24, raised by s3ked)* The mute-group re-model flattens the losing layer's envelope and writes `KGMUTE` 255. That is right for a target with **no** mute groups and wrong for the AKAI itself: the destination expresses the group perfectly, so the faithful output for AKAI->AKAI is the input -- `KGMUTE` 0 and the source's own `SUSTN1`. **It is also one-way:** once flattened, the original cannot be recovered and a second pass cannot tell a flattened program from one authored that way. **Blocked on a modelling decision, not a bug fix:** we do not carry mute groups in the model at all (`_KGMUTE_DEFAULT` is written unconditionally), so making this faithful means the model holds a mute group, which then has to mean something for every other target. Decide it deliberately. |
| ~~**The release fix reaches E4B and AKAI only**~~ **KRZ CLOSED 2026-08-25, measured. EIII and TAL still open** | *(2026-08-24)* `release_rate_db_per_s` is consumed by `e4b_writer` and `akai_s3000_writer`. `krz_writer` uses `env.release * _KRZ_RELEASE_FACTOR`, and for an AKAI source those seconds are computed over the **60.07 dB** scale -- one of the two parameter-scale artifacts the E4B fix exists to stop matching across. **So AKAI->KRZ carries the pre-fix behaviour, byte-identical to before** (confirmed by the conversion-matrix diff). **MEASURED 2026-08-24: the K2000 IS A RATE MACHINE.** One release setting, slope fitted well above the floor: **-112.0 dB/s at sustain 100% and -106.9 at 50%**, ~5% apart, r2 > 0.997, no curvature. A duration machine would have to slew faster from a higher sustain to cover more distance in the same time, so the slope would scale with the distance; it does not. (Sustain 15% excluded rather than forced -- its start level sits 18 dB above the floor and leaves no window to fit in.) **The arrival-time metric could not have answered this** -- 0.545 / 0.385 / 0.200 s fits neither hypothesis, because time to floor conflates where the fall starts with how fast it falls. **Confirmed on a full clean run:** slopes reproduce to ~1% (-110.6/-106.2 at Rel1 1.00 s), sustain-invariance holds at BOTH settings (~5% and ~3%), captures printed and clear of the fall, sustain 15% excluded at both for want of a window. **The LAW is still open and the FIT QUALITY is why.** At Rel1 3.00 s the same method on the same rig returns r2 0.93/0.85 with rmse 1.7-2.5 dB against 0.999 and 0.19-0.31 at the fast setting -- **that is not a straight line with noise on it**, and a single slope fitted to a curved fall is a window-dependent average. Implied spans: the two fast readings agree at ~108 dB, the two slow ones agree with each other **14% below** it (93.0, 96.0). **If the span is fixed at ~108 dB the true slow slope is 36.1 dB/s -- the written prediction -- and a fitted average running 14% low is what a curved fall produces.** **Thirds done, and the prediction is REFUTED: first thirds came back at -42.5 and -53.9 dB/s against a predicted 36 -- overshooting, not landing.** So "fixed ~108 dB span" as framed is not what this is. **The discriminator is in the data itself: the overall slopes agree to 3% while the FIRST THIRDS disagree by 27%.** Sustain-invariance holds on the whole fit and breaks in the first third -- and an envelope generator cannot do that, because a falling envelope does not know what the sustain level was. **Something that is not the envelope is contributing, differently depending on where the fall starts**, and it bites the slow setting harder because the direct signal spends 3x longer in the region where it can dominate. A fall that starts steep and flattens is two summed components; the program is single-layer, so the next candidate is **FX**. **FX ELIMINATED** -- the program reads `Sweet Hall` at **0% wet**, fully dry, so a reverb tail under the direct signal is not it. **AND THE 'ENVELOPE CANNOT DO THAT' ARGUMENT WAS WRONG, my error:** the two captures' windows are **[-38.3,-71.8] and [-56.7,-71.7] dB** -- their first thirds are **18 dB apart** and are measuring different parts of the same fall. If the curvature is a function of LEVEL, they must differ, with no external contributor needed. The direction fits: the lower window came back steeper (-53.9 against -42.5), which is what a release **linear in AMPLITUDE** looks like in dB. **BOTH RE-ANALYSES FAILED, and how they failed is the finding.** Restricted to a common window the wide capture gives **r2 0.51** with 2.7 dB rmse over 93 points; refitted in linear amplitude both give **0.69/0.72**, WORSE than the 0.93/0.85 in dB. **When every model fits badly and the fast capture on the same subject fits at 0.999, the problem is not the model.** 2.7 dB of rmse is +/-18% in amplitude, on a rig that returned 0.19 dB an hour earlier. **HYPOTHESIS: the subject BEATS.** `ObSt lowp kl.lay` is a detuned Oberheim STACK, and beating explains every number: the fast release crosses 33 dB in ~0.3 s and sees a fraction of a cycle (clean); the slow one takes ~1 s and rides whole cycles; a narrower window has less real trend against the same modulation; and changing the y-axis cannot fix modulation. **The monotone thirds may be where the beats fell, not curvature** -- which would make the whole curvature line, mine included, an artefact. **CONFIRMED BEATING** -- residuals periodic at 22.4x peak-to-mean, components at 1 : 1.5 : 2 of ~1.96 Hz, spanning -8.2 to +3.1 dB. Every slow-fit number is withdrawn and the curvature enquiry closes as an artefact. **The rate-machine conclusion stands on the FAST pair alone** (r2 0.999, -110.6 vs -106.2 across a doubling of distance). **NEXT, and Jan's suggestion: BUILD the subject rather than hunt for one** -- a noise or simple saw preset off `199 Default Program`, which he says has been done before. One layer, one ROM waveform, nothing detuned; filter open, no filter envelope, no LFO, no cords; FX read and confirmed dry; envelope jumping straight to sustain so the release is the only thing moving; two well-separated sustain levels for the span check; a slow release setting since the law is what is open. **Qualify the subject BEFORE using it** -- run the periodicity check on its residuals first, because tonight we fitted first and diagnosed after and it cost an evening. **Prefer a saw over noise:** its harmonic content shows whether the SPECTRUM changes during the fall, which distinguishes a filter or sample artefact from an amplitude envelope; noise cannot. **BUILT AND QUALIFIED 2026-08-25:** program 199's live edit buffer, **algorithm 1 = PITCH->NONE->AMP, no filter stage at all** (better than 'filter wide open' -- a filter set open is one you are trusting), ROM Sawtooth keymap, no cords, FX read and confirmed dry. **AMPENV had to be switched from Natural to User** -- 199 ships with a Grand Piano keymap and therefore in Natural mode, which ignores the ENV bytes and plays the sample's own envelope, so the whole run would have produced numbers while measuring nothing. Caught by checking, not by failing. **Acceptance test passed:** r2 **0.9996**, rmse **0.211 dB** (against 0.93/0.85 and 2.47 dB on the beating stack, and matching the 0.19-0.31 dB baseline of the clean fast pair). **THE LAW: -33.02 dB/s at Rel1 3.00 s -> implied span 99.1 dB.** The stack's fast pair implied 106-110 dB, but that is a different PROGRAM as well as a different setting. **CLOSED. Rel1 1.00 s on the same saw: -99.68 dB/s over its top third, r2 0.9974 -> span 99.68 dB against the slow setting's 99.06. TWO SETTINGS, ONE SUBJECT, 0.62% APART.** The K2000's displayed release time is the seconds to cross a fixed **~99.4 dB**. (The fast setting had to be fitted over its top 12 dB: across the whole window it reads -89.4, because the fall bends and a straight line across a bend is a chord.) **Wired:** `KRZ_RELEASE_SPAN_DB = 99.37`, and `krz_writer` prefers a carried rate over the seconds path. **AUDIBLE CHANGE -- wants a listen:** an AKAI source at 15.33 dB/s went to 3.76 s and now goes to **6.48 s**. `_KRZ_RELEASE_FACTOR` stays as the fallback for duration-only sources. **Old text:** Near 99 -> span fixed, wire it. Near 106-110 -> the span depends on the program, which would be the more interesting answer. **Old free test, superseded:** Periodic = beating, every slow-fit number tonight is contaminated, and the fix is a different subject rather than a different fit -- the same file's `mo` (mono) programs, ids 807 and 809, against the `st` (stack) ones. Aperiodic = real curvature survives. **The rate-machine conclusion is untouched by any of this**, resting on sustain-invariance of the overall fits at both settings. **DO NOT wire a rate law from this** -- the rate-machine conclusion stands on sustain-invariance of the overall fits and is not in question, but the LAW is undetermined and the number would come from a fit with r2 0.85. So the fix is the same carrier, and only the span they are measured over is wrong. `_KRZ_RELEASE_FACTOR = 2.63/1.39` was derived from the machine's *displayed* release, which hints at a duration but does not settle it. **Ask what the K2000 was metered for before deciding what to preserve** -- the same question that took a full session to get right on the E4XT side. EIII and TAL have not been looked at at all. |
| ~~**`akai_filfrq_to_hz` flattened 29% of all keygroups onto one cutoff**~~ **FIXED + HW-MEASURED 2026-08-24** | It clamped FILFRQ below the fitted floor of 40, so **every byte from 0 to 40 returned the same 137.9 Hz** -- **29.4% of real keygroups** across the library discs, ordering destroyed within the whole region. **Measured (s3ked, 2026-08-24; their section number omitted until it lands in their repo -- our citation test checks every s3ked reference resolves there):** the corner keeps descending to FILFRQ 0 with **no plateau anywhere** -- monotonic across 41 dB, and the exponential (fitted 44..92, never measured below) predicts it to within ~2 dB all the way down. At byte 0 the corner is ~7 Hz and the filter attenuates 41 dB at 80 Hz: a real, usable, very dark setting. **`AKAI_FILTER_FLOOR_HZ = 100.0` was almost certainly an artefact of a measurement nobody took:** s3ked's first pass normalised each curve to its own 60-120 Hz band and got a floor at 111.3 Hz, because once the corner drops below the normalisation band the 0 dB reference sits ON THE SLOPE and every setting reads the same -3 dB point. **A passband reference is only a passband reference while the corner is above it.** Constant renamed `AKAI_ENV2_SWEEP_FLOOR_HZ` -- it is a modelling bound on a downward env2 sweep, not a property of the machine. **Fifth instance of the clamp-to-a-fit class this week, and the largest span of the five.** |
| **A K2000 program with >3 SPLIT layers is a drum program -- we can now reduce the count but not always below 4** | *(2026-08-24, Jan diagnosed it from the format's logic)* A converted electric piano was **silent on the K2000R** and every internal check was clean. k2kremote confirmed both ends: `DrumChan = 8` so drum channels are 1-8 and channel 9 is not one, and a JACK capture at the machine's OWN output read noise floor -- correctly refusing to play. The display had shown `200*(the converted preset's name)` **in parentheses** from the first query, which the manual says means exactly that. **ROOT CAUSE, and Jan had it before any measurement: a K2000 keymap IS the multisample container** -- measured, **20.7% of 1584 keymaps in 201 real third-party soundsets hold more than one sample, up to 64** -- while we emitted one keymap and one layer per voice, and the AKAI parser emitted one voice per keygroup. **FIXED in part:** `_merge_identical_voices` collapses voices differing only in key coverage, lossless by construction (6 layers -> 4 here). **STILL OPEN:** those 4 are still over the threshold, because this preset's three octave ranges carry **different authored filter settings** (FILFRQ 65/70/62, FILQ 14/15/13) and a K2000 filter is per-layer. Getting to 3 means approximating three authored settings with one -- a deliberate loss, not a restructuring. **Decide:** leave it a drum program and say so loudly at build time, collapse the nearest layers with a warning, or make it a flag. |
| **`Envelope`/`VoiceLayer.filter_keytrack` is stored in the E4XT's CORD units, so a physical ratio is quantised by one machine's parameter scale** | *(2026-08-24)* Found immediately after wiring AKAI `K_FREQ`. The field means "EOS cord amount, -1..+1", and the E4XT's Key->Filter cord at 100% tracks **0.713 oct/oct** (measured, r=0.9994 -- not 1:1). So an AKAI keygroup asking for **full 1:1 tracking saturates**, and an AKAI->AKAI round trip returns **K_FREQ 12 as 9** and **10 as 9**. **K_FREQ 12 is 27.1% of the corpus** -- the single commonest non-zero value -- so this is not a corner. **The E4XT saturation is real hardware and unavoidable; the ROUND-TRIP loss is ours**, and it is the same shape as the release defect fixed the same day: a physical quantity routed through one machine's parameter scale. **Fix:** store **oct/oct** in the model and convert at the point of use with the existing `key_track_to_filter_amount`. Touches `e4b_writer` (consumes it as a cord amount), `krz_parser` and `exs24_parser` (both set it in cord units), plus the AKAI reader/writer. **Not wired the same evening as fifteen other changes** -- a semantic change to a shared field wants its own pass. **And when it is wired, the E4XT saturation should be REPORTED rather than silent:** asking for 1:1 and getting 0.713 is a real audible difference the user never hears about today. |
| **`e4xt_resonance_byte` ignores `poles`, and is not the inverse of `e4xt_byte_to_resonance` -- E4B->E4B RESONANCE CLIMBS** | *(2026-08-24, code review, HIGH)* It scales **both** target and table by `poles/2` so the factor cancels: `(0.5, 2)` and `(0.5, 4)` both return 86. The reader applies the scale **one-sided**, so a 4-pole voice repacked twice goes byte 40 -> 0.38 -> 67 -> 0.998 -> **112, pinned at max**. Also `filter_type` 0/23/24/25 write `poles=2` but map to `vpar[58]=0x00`, which reads back as `poles=4`, so a filter-OFF voice **gains resonance on every round trip**. |
| **`_akai_env2_depth` clamps a DOWNWARD sweep against the headroom ABOVE its base** | *(2026-08-24, code review)* `copysign` is applied after the clamp, so a negative depth is bounded by the wrong side. Reproduced: FILFRQ 90 / SUSTN2 50 / depth -20 (2.6 octaves down) round-trips as **-4** (0.5 octaves); 70/50/-30 comes back as -21. The reader's `_env2_amount` bounds negatives against the floor correctly, so this is another one-sided pair. Small negatives survive, which is why it passed casual checking. |
| **`_or_default` exists precisely for this and the envelope path does not use it** | *(2026-08-24, code review)* `getattr(env,'decay',0.3) or 0.3` and `... or 0.5` treat a legitimate **0.0** as missing. A source stating an instant release (XPM `VolumeRelease` 0, sfz `ampeg_release=0`) gets the 0.5 s default -- RELSE1 ~56, a half-second tail on a patch that asked to stop dead. |
| ~~**`keygroup_count` under-counts, so the 1006-object pool is under-budgeted**~~ **ALREADY FIXED — row was stale, verified 2026-09-10.** It calls `build_program`'s own grouping rather than restating it; a 10-zone preset gives `keygroup_count() == 10` against 10 emitted. | *(2026-08-24, code review)* It returns `len(_group_zones_into_keygroups(preset))`, but `build_program` splits again afterwards: >4 zones per keygroup spill into extra keygroups, and `stereo_right` doubles every stereo zone first. Verified: 8 velocity layers on one key range gives `keygroup_count == 1` while the file says 2. `bank_splitter.akai_object_count()` is the only consumer, so dense or stereo banks can be split into volumes the S3000XL cannot hold. |
| **AKAI capacity counts `SampleData` objects, but a stereo sample costs TWO** | *(2026-08-24, code review)* `bank_splitter`'s `(509, 509, 510)` check ignores the `-L`/`-R` split, and `sample_voice_cost()` already exists in that file for exactly this and is not used. 300 stereo samples pass at 300 and produce 600 files; `build_akai_hd_image` then raises **after the split is committed**, and the loose-file path has no check at all. |
| **Program header names skip `safe_filename`, so two programs can collide to one directory entry** | *(2026-08-24, code review)* The filename goes through `safe_filename` and the header name does not. `#` and `+` both map to `_`, which is outside the AKAI charset and encodes as a space: `F#Bass` and `F+Bass` both write `F_BASS.P3` while `uniq` keeps them distinct by `str_to_akai` bytes. A load replaces a resident item of the same name, so **one program is silently lost** -- the exact defect already fixed for samples. Related: `uniq()` preserves leading spaces in the header while the filename is `nm.strip()`, so `' Kick'` writes `KICK.S3` and no zone asks for it. |
| ~~**STUNO decodes as cents/256 while the writer stores cents x 2.56**~~ **FIXED 2026-09-10.** The field is 1/256-SEMITONE units, 2.56 per cent. The reader's `// 256` produced floored semitones and called them cents, so +50 read back 0 and −50 read back −1 (floor division breaks sign symmetry as well as scale). Now `_s16 / AKAI_TUNE_UNITS_PER_CENT`, with whole semitones folded into `root_note` since `SampleData` has no coarse field. Two regression tests, both confirmed to fail with the old line restored. **The writer had it right all along**, so an AKAI→AKAI round trip flattened every fine tune and agreed with itself — the asymmetry class a round trip cannot see. | *(2026-08-24, code review)* `fine = _s16(data,0x14) // 256` against `AKAI_TUNE_UNITS_PER_SEMITONE = 256`. Measured: `fine_tune=+50` stores 128 and reads back **0**; `-50` reads **-1** (floor division also breaks sign symmetry). Every sub-semitone sample tuning on a real disc reads as zero. |
| **`octave_shift` and PTUNO are parsed and never used** | *(2026-08-24, code review)* `build_preset_from_program` sums only `kg['tune'] + z['tune']`. A factory program with PTUNO +5 semitones or an octave shift converts at the wrong pitch, silently. |
| **AKAI S3000->E4B: one test patch persistently ~29 cents flat, unaffected by this week's fixes** | *(2026-08-29, confidence-matrix rebuild, eosed)* Of the six S3000->E4B EP-family test patches, five are within a few cents (below audibility) or have a baseline too scattered to trust (see below). One, the multi-layer 11-voice patch, measures **-29.3 cents flat on 2026-08-22's baseline and -29.1 cents on a fresh conversion with today's code** -- unchanged, both readings tight (scatter 1.2-1.4 cents, i.e. a real, solid number both times, not noise. **This is the one genuine tuning defect in the AKAI->E4B route** and none of this week's cutoff/envelope/release/key-follow work touched it. Not yet root-caused. Two other findings from the same pass, NOT bugs: the octave-shift flag on the key-tracked test EP is now CONFIRMED FIXED (checked against the source's own spectrum, not just the pitch tracker -- the AKAI original itself plays an octave above its written pitch, and the fresh conversion now agrees); and one patch's old baseline `d_cents` (+0.5, "within 3.4 cents" tier) turns out to rest on ~46-50 cents of scatter across its four probe notes -- a median of a bimodal reading, never a real tuning measurement, and a caution for reading the OLD worklist's numbers on the remaining two routes without checking scatter first. |

| **The matrix harness's clipping check (`peak_db`) cannot see clipping, and it has been wrong all session** | *(2026-08-30, found when Jan heard real distortion live)* Jan reported the E4XT distorting during the KRZ->E4B measurement pass. Real: a sample-level census (`max(abs(sample)) >= full scale`) found **4 of 7 captures clipped**, one with 761 runs of 3+ consecutive full-scale samples -- not headroom being grazed, the waveform genuinely squared off. Cause: `MASTER_HCHIP_BOOST` (the E4XT's own +12 dB output boost) is on, and this route's source material is hot enough that boost pushes it over. **Checking the fix exposed a bigger problem: two captures from the EARLIER, already-reported AKAI->E4B pass were ALSO clipped** (PC 7, PC 11) and had been reported clean ("PC 2 and PC 9 peak at -0.8/-0.7 dBFS, nothing clipped"). The reason: `measure.py`'s `peak_db` is a **5 ms moving average of the signal**, and a clipped burst is typically under 1 ms -- the average erases it almost completely. **Every "no clipping" assurance this harness has given, this session included, was reading a statistic structurally incapable of answering that question.** Fixed by testing `max(abs(sample))` directly instead, which found everything above in one pass. **Consequence:** PC 11's (preset 4) release-fix "overshoot" verdict from the AKAI route is withdrawn pending re-capture on clean audio -- not disproven, just resting on corrupted data. PC 15's stands (verified clean, zero full-scale samples). **Resolved same night:** Jan set the E4XT's own analog output level by ear (holding the worst-clipping patch), which eosed then measured precisely (-9.27 dB, two clean anchor programs agreeing to 0.01 dB) rather than leaving it as an unlabelled bench change -- a THIRD gain generation on this one machine, since the E4XT's capture chain is independent of the AKAI's and K2000's. **A follow-on false alarm from this, caught and retracted the same session:** comparing the fresh KRZ->E4B conversion against the 22-Aug baseline first looked like a uniform +15.28 dB converter regression (12 programs agreeing to 0.12 dB -- exactly the shape of a systematic bug). It was not: a byte-for-byte diff of the converted files (zone volume, envelope, filter, raw PCM) found nothing different, and checking an UNCHANGED reference preset captured in both epochs showed it moved by the same ~+16-17 dB -- i.e. gain generation #1 (22-Aug baseline, predates `CAPTURES.md`'s "held since 2026-08-24" statement, was never covered by it) against generation #3, plus a second confound (0.8s vs 3.0s inter-note gap making whole-file RMS incomparable). **No level-based comparison against the 22-Aug baseline (RESULTS.json) is safe, corrected or not -- only ratio-based measures (sustain ratio, dB/s decay, cents, third-octave distance) survive across all three generations.** The durable lesson, now in CAPTURES.md: an unchanged control captured in both epochs is what tells a converter change apart from a bench change, and it should be checked BEFORE reporting a uniform-looking regression, not after. |

| ~~**KRZ->AKAI: 8 of 12 patches mistuned by a rate-conversion error, real, serious, was invisible to the pitch tracker the whole time -- reaches organ patches too**~~ **RESOLVED 2026-08-30 -- was a card-transfer defect (see §AKAICARDTRANSFER below), not a converter bug; re-transferred and HW-CONFIRMED FIXED.** s3ked re-captured the corrected `MX2 KRZ V2` off the actual machine: 48/48 sounded on the default notes, 60/60 on the spanning set, and **all 12 of 12 patches now match the old known-good build's spectral-presence fraction exactly** -- the 8 regressions are gone, and the 4 patches that were never clean (organ family, pre-existing damage) are unchanged at their old values, not over-corrected. `FAT PROT. B3 ORG`'s residual fault is confirmed the SEPARATE, older, still-open problem it was predicted to be -- same value in both the old build and the corrected one. **New finding surfaced by this re-check, still open:** on the spanning note set those same 4 "damaged" organ patches read 0.80 (4/5) rather than 0.25 -- the default 4-note set (36/43/48/55) happens to land on the drawbar's weak point, so the true severity of that pre-existing organ fault is uncertain; the `krorig` source has no capture at the spanning notes to compare against, so this needs a fresh K2000 source capture at those notes (k2kremote's side) before `FAT PROT. B3`'s ticket can be sized correctly. See below for the transfer-bug history. **CORRECTED AGAIN, 2026-08-30, s3ked: the "6 of 12, clean organ/non-organ split" below was an artifact of a separate `octave_check.py` bug (a 0.35-0.80x f0 "floor" band that is not actually empty -- it straddles the sub-octave, f0/2, where a sub layer, 12-string lower course or organ 16' drawbar routinely lands; same shape as §165).** With that floor removed (verdict now: is h1 within 20 dB of the take's own strongest partial, nothing below f0 consulted) and the whole corpus regression-run against it, **the real per-patch table is 8 faulty of 12, not 6:** PROTEUS B3 ORGAN and JAZZY B3 ORGAN match (0/4->0/4), GREEN B3 ORGAN matches (1/4->1/4), OCT.PROT. B3 differs (4/4->1/4) -- but **FAT PROT. B3 ORG and SINE B3 ORGAN, both previously read as clean, are FAULTY** (4/4->0/4 and 2/4->0/4). The "perfect organ/non-organ split used as corroboration for the krorig<->patch pairing" is WITHDRAWN -- `krorig_603` measured directly has h1 at -15.3 dB under a dominant h3 (a real drawbar registration with a present fundamental), not the absent-fundamental case the split assumed. **The pairing conclusion itself still stands, but now rests only on its other leg** (`patch_map.json` documents `key: "writer-order"`, independently verified) -- the organ split was corroboration, not the primary evidence, and should not have been leaned on as hard as it was. **Consequence for the trace:** "only certain sample families" (12-string/the Phantasia family) is no longer a valid narrowing hypothesis for `akai_target_rate()` -- the bug reaches organ patches too, so whatever is wrong is not family-specific. **Confirmed unaffected by this correction:** the fifth-down ratio (0.729x / -547 cents) itself, measured directly off the harmonic series, never came from `octave_check` and stands exactly as before, as does the 22050/44100-vs-30000 rate-mismatch hypothesis and the blocked-on trace of `akai_target_rate()`. `octave_check.py`'s old floor-band blind spot is now fixed (backup at `octave_check.py.bak-2026-08-30`). **UPDATE, same evening: it IS wired into `score.py`/`report.py` now** (a presence-only fallback, used only when the YIN tracker itself declines to verdict a patch -- `octave`/`cents`/`pitch_ok` still mean the tracker's own answer everywhere else; see `score.py`'s `spectrum_frac`/`_spectrum_frac`, `octave_check.written_pitch_flags`/`classify`). The line above describing it as unwired is now stale, kept for the trace.

**REGRESSION FOUND, 2026-08-30, s3ked, using the newly-wired fallback:** `report.py`'s own `patch_map` join lets the old (pre-2026-08-30) KRZ->AKAI build be compared against fresh V2 on the SAME `krorig` source captures. **8 of 12 patches regress -- correct in the old build, broken in V2. The other 4 (the organ patches already flagged faulty above) were already damaged before V2 and are now worse or unchanged -- 0 patches are unaffected.** Control: the `src` column (spectrum-presence on the krorig captures) is byte-identical between the two comparisons, months apart through the same measurement code, which is what makes the conversion-column difference trustworthy rather than measurement drift. Per-patch table (spectrum-presence fraction, source / old conversion / V2 conversion): Proteus 12String 1.00/1.00/0.00, Prot. Phantasia 1.00/1.00/0.00, Oct.Prot. B3 Org 1.00/1.00/0.25, Green B3 Organ 0.25/1.00/0.25, Oct.Prot. 12Str. 1.00/1.00/0.00, Prot. 12Str. Lyr 1.00/1.00/0.00, St. Phantasia 1.00/1.00/0.00, St. PhantaVox 1.00/1.00/0.00 (all 8 REGRESSIONS); Fat Prot. B3 Org 1.00/0.25/0.00, Sine B3 Organ 0.50/0.25/0.00, Proteus B3 Organ 0.00/0.25/0.00, Jazzy B3 Organ 0.00/0.25/0.00 (already damaged pre-V2, worse now). **This changes the trace materially: the bug is NEW, introduced in code changed between the old build and today's V2 rebuild, not a long-standing defect** -- and it is not family-specific, since 12-strings, Phantasias and organs all regress together. A first git-log sweep of `writers/akai_s3000_writer.py`, `parsers/krz_parser.py` and `processors/resampler.py` since 2026-08-19 (the old build's approximate date) found no commit obviously touching `akai_target_rate()`, the SSRATE/byte-0x01 rate-selection logic, or the resample path itself -- **the specific commit is NOT yet identified**, this only narrows the search window. **Blocked on, updated:** the byte-level trace described above (written AKAI sample header rate vs the PCM's actual rate, one isolated Phantz1 zone and one isolated 12STR zone) is still the next step, now with a known-good reference to diff against (the old build's AKAI image, if still on disk, would show the correct header for the same source sample).

**CRITICAL REDIRECT, 2026-08-30 18:53, this session, checked directly against the loose files convert.py actually wrote:** `~/temp/matrix/out_MXKRtoAKAI_v2/EMU_BANK_01/*.S3` -- the exact volume s3ked read from the machine -- **already has the correct headers.** Read byte 0x01 and SSRATE (0x8a, `<H`) directly from every affected sample file: `A13 12STR1.S3`/`A11 B3 1.S3`/`A44 PHANTZ1.S3` all read byte0x01=1, SSRATE=44100; `A12 B3 3.S3`/`A44 PHANTZ2.S3`/`A44 PHANTZ3.S3` all read byte0x01=0, SSRATE=22050 -- every one matches `_AKAI_RATE_FLAG` and the old (good) build's own values, none show 30000/15000/15001/7499. **`akai_target_rate()`, `resample_to_rate()` and `build_sample()` are not the bug -- confirmed by reading the actual bytes they produced, not by re-reading the code.** The build's own log (`log_MXKRtoAKAI.txt`, but note that file is dated 22-Aug -- the OLD build, not V2; no separate V2 log currently exists) shows the same "N sample(s) snapped" clean accounting with no `[ERROR]`s.

**So the corruption happens between these correct on-disk files and whatever s3ked read off the machine.** Two live possibilities, neither yet checked: (1) the append/transfer step that put `out_MXKRtoAKAI_v2` onto the SD card (`append_akai_volumes` or equivalent) altered the bytes in transit; (2) the card already held an OLDER, broken "MX2 KRZ V2"-named volume from an earlier attempt this session and the corrected rebuild was never actually re-transferred over it -- same-name volumes silently replace on this format (see `write_akai_output`'s own docstring on that), so a skipped re-transfer would look identical to a successful one from the log alone. **This also retracts the "bug is new, introduced in code changed since 8/19" framing two entries up** -- that inference assumed the regression was in the converter, and the converter's own output is now shown clean. The regression against the old build is still real (s3ked's spectrum measurements off the actual machine are not in question) -- only WHERE it is introduced has changed. **Corrected blocked-on: diff `out_MXKRtoAKAI_v2`'s actual file bytes (now confirmed correct) against whatever is read back off the card for the same volume, rather than against convert.py's code.**

**ESCALATION, 2026-08-30 19:03, s3ked: NOT a one-off. `MX1 E4XT V2` (appended 2026-08-28, same unknown transfer mechanism) carries the identical defect** -- native source rates written instead of resampled 44100/22050 (bass A at 44050, bass F at 44084, several at 44001/44100, bass J C2 at **23939** where the machine plays 22050). It escaped detection until now because 9 of its 10 samples were already within a few cents of 44.1 kHz natively, so the same bug cost 0-4 cents there against 547-655 cents on MX2's lower-rate KRZ material -- **inaudible on one volume, severe on the other, same root cause.** bass J's -142.3 predicted cents (1200*log2(22050/23939)) is confirmed against the capture at -149.5/-144.6/-143.1 across three notes (spread 6 ct) -- this is real and has been on the card, mistuned, since the 28th. **Every volume this unknown append command touched needs re-checking, not just these two** -- scope not yet established. **Consequence for tonight's confidence-matrix work: the fresh "V2" measurements on BOTH the E4B->AKAI and KRZ->AKAI rows are suspect** -- they may have measured this transfer defect rather than the current converter, since MX1 E4XT V2 backs the E4B->AKAI V2 row. Treat those rows' "closer/further" conclusions as unconfirmed until re-measured against a verified-clean transfer.

**BLAST RADIUS CLOSED, 2026-08-30 19:37, s3ked's full card sweep:** 18 volumes, 364 samples. 16 volumes / 344 samples all exactly 22050 or 44100 -- every TC-series volume, both native reference volumes (MX3/MX4), and both ORIGINAL MX1/MX2 conversions. Only `MX1 E4XT V2` and `MX2 KRZ V2` are off-rate -- exactly the two the unknown append wrote. **Nothing else on the card is affected.** The direct HD-image build path (`build_akai_hd_image`, used for every clean volume) does not share this bug.

**MECHANISM FOUND: one header field copied correctly, the adjacent one overwritten from the wrong source.** s3ked read SBANDW (byte 0x01, the rate-SELECT flag) alongside SSRATE (0x8a) on both broken volumes: **SBANDW is correct on every sample in both volumes and matches the `.S3` files exactly** -- only SSRATE is wrong, and it consistently reads back the sample's ORIGINAL (KRZ/E4B) native rate rather than the resampled target. That is also why MX1 looked clean at a glance: its sources were mostly already near 44100 natively, so the wrong (native) value it wrote happened to be close to the right one; MX2's sources were at 30000/7499, far from any AKAI rate, so the same bug was severe there. One bug, one mechanism, two very different-looking symptoms depending on how far the source rate sat from the target.

**Checked against the codebase, 2026-08-30 19:37: `append_akai_volumes()` (`writers/akai_s3000_image.py:677`) is not the bug.** Read its body directly -- it copies each file's bytes into disk blocks completely verbatim (`data[o:o+HD_BLOCK] = chunk + ...`), with no field-level access to SSRATE, SBANDW, or any other header byte. It cannot selectively preserve one field and overwrite the other; it does not look inside the file at all. So the corruption happened to the `fdata` bytes **before** they reached `append_akai_volumes` -- in whatever process assembled or modified them between a correct `build_akai_volume()` output (already proven correct, `out_MXKRtoAKAI_v2/*.S3` on disk) and the call that wrote them to the card. That process is not `convert.py --add-to` in a single run either: that path hands `build_akai_volume`'s in-memory output straight to `append_akai_volumes` with no file re-read and no intermediate step that could touch a header byte. **The actual command used for this append could not be recovered** (run earlier this session, before a context compaction, not logged to any file found by grep) -- so the specific bad script/step is unidentified and likely unrecoverable, not just unfound.

**Recommendation, given the mechanism is understood even without the exact culprit: redo the transfer via a single `convert.py --format akai --add-to <image>` run, nothing else in between.** Both ends of that path are now independently verified correct in isolation (`build_akai_volume`'s output bytes, and `append_akai_volumes`'s verbatim block copy), so a single-command transfer cannot reproduce this specific failure shape. Whatever multi-step process was used before should not be reused even if it can be reconstructed from memory later.

**CONFIRMED FROM THE OTHER BUILD PATH TOO, 2026-08-30 19:39, s3ked: MX1's `out_MXE4toAKAI_v2/EMU_BANK.hda` (the `build_akai_hd_image` path, not the loose-`.S3`-file path checked above) is also uniformly correct -- all ten samples at 44100 inside the image.** The card's six wrong values (44050/44084/44001 x3/23939) match none of the image's values; they are each sample's ORIGINAL source rate, not a stale or dropped field. **This sharpens the mechanism: not "SSRATE failed to copy" but "something re-derived SSRATE from the original E4B/KRZ source material and wrote that instead of the build's own value."** A verbatim block copy (which is all `append_akai_volumes` does, confirmed above) cannot do this -- it never looks at a source file, only at the already-built bytes it's handed. Whatever ran between the build and the card had its own access to the original sources, independent of the build output, and used it. `SBANDW` matches on both broken volumes in both directions, so this is specific to the SSRATE field alone, not a general header rewrite. Both build paths (`build_akai_volume`/loose files for MX2, `build_akai_hd_image`/`.hda` for MX1) are now independently confirmed correct -- the TC-series baseline being clean is a real baseline, not a coincidence of which path they happened to use. **RE-TRANSFERRED AND VERIFIED, 2026-08-30 19:50.** Card mounted, Jan approved the write. Backed up the live image first (`~/temp/HD4-before-retransfer.img`), then wrote both volumes via `append_akai_volumes(on_duplicate='overwrite')` directly on the already-verified-correct bytes -- MX2's loose `.S3` files as-is, MX1's files lifted straight out of its own correct `.hda`'s FAT via `read_akai_image()` (byte-identical, not reconverted or re-derived). Read the result back off the live image immediately after: **all 20 samples across both volumes now read 22050 or 44100 with byte 0x01 matching, 0 off-rate.** 18 volumes total on the card, unchanged from before except these two. **Root mechanism understood, exact culprit script not recoverable (ran before a context compaction, unlogged) -- not pursued further since the fix is confirmed working. HW-CONFIRMED 2026-08-30, BOTH VOLUMES: MX2 KRZ V2 re-measured 12 of 12 patches matching the old good build on spectral presence; MX1 E4XT V2 re-measured 10 of 10 patches matching the old good build within 2 cents on tuning -- bass J's -142 cent fault (the one that looked like a real conversion defect) collapsed to -12.1 ct, exactly the old build's own value including its odd per-note shape, confirming the residual was a property of the patch, not a second bug. The E4B->AKAI and KRZ->AKAI matrix rows are no longer suspect -- both confirmed clean on the corrected media.** §AKAICARDTRANSFER — CLOSED |
| *(superseded by the row above, kept for the trace history)* **KRZ->AKAI: 6 of 12 patches mistuned by a rate-conversion error, real, serious, was invisible to the pitch tracker the whole time** | *(2026-08-30, confidence-matrix rebuild, AKAI<->KRZ leg, s3ked -- corrected same session, see below)* **CORRECTED: this is a fifth DOWN (ratio ~0.729, ~-547 cents) on one group of zones and a fourth-plus-octave UP (ratio ~1.460, +655 cents) on another, not the "3x/+1902 cents" first reported.** The two ratios are exactly one octave apart (1.4597/0.7292 = 2.0018), i.e. one underlying error surfacing at two octaves depending on the zone. **Both ratios sit within ~13 cents of an exact rate mismatch against the samples' true 30000 Hz source rate: 22050/30000 = 0.735 (-533 ct) and 44100/30000 = 1.470 (+667 ct).** `akai_target_rate()` is very likely the right place to look -- it resamples anything above 22050 Hz to 44100 and anything at or below to 22050, and these numbers are exactly what a same-family bug (wrong target bucket, or a resample that changes the header without actually resampling the PCM) would produce. **Original write-up below, still true except the ratio/direction:** All six 12-string/the Phantasia family-family patches (source has a real fundamental) are mistuned on the fresh KRZ->AKAI conversion; all six B3-organ patches (drawbar registration, no fundamental in the source at all) show no fault -- the split tracks a real musical property of the source exactly, ruling out a program/patch mismapping. Confirmed by spectrum, not by the tracker -- and the tracker's own `octave_check` has a documented blind spot here: it only looks at bands centred on 1x/2x/3x/4x the written f0, so a fundamental BELOW the written pitch aliases into whichever band its nearest harmonic happens to land near (a fifth down puts its 4th harmonic 49 cents from the 3x band, which is what first read as "h3 dominant, twelfth up"). Measuring the true series on its own terms gives a clean harmonic set 50-70 dB above the floor at the corrected ratio. **The old baseline never caught this at all**, because its pitch tracker locks to partials on this material and reported `octave_shift: 0` with `d_cents` -2.6 to +44.2 on patches that were badly mistuned the whole time -- the same "check the check" failure mode as every tracker issue found this session, just with a much larger, more audible consequence. **Ruled out by reading the AKAI program structure directly:** keygroup ranges, per-zone sample assignment order, and each zone's root note (SPITCH 50/62/74/86 for the 12-string family) are all correct and sit inside their own keygroup -- nothing addressable through the program header explains it. **Ruled out by this session's own check of the KRZ source:** the affected samples' root_key is parsed correctly and uniformly (60 for all three Phantz decimated copies, matching their AKAI SPITCH) -- the KRZ parser's own root-note computation is not obviously at fault. **The source samples carry K2000-style decimated multi-rate copies of one waveform** (Phantz1/2/3 at 30000/15001/7499 Hz, all SPITCH 60; the four 12STR samples all at a uniform 30000 Hz; similarly for the B3 samples) -- `akai_target_rate()` should resample everything above 22050 Hz to 44100 and everything at or below to 22050, and the corrected ratios above land within ~13 cents of exactly that mismatch in both directions, one octave apart. **Actual mechanism (wrong target bucket vs. header relabelled without resampling the PCM vs. something else) not yet found.** Two program numbers on this volume also collide (PRGNUM 0, `TEST PROGRAM` vs the first patch) -- same build defect as MX1 E4XT V2, not yet investigated either (see the earlier "not a bug" entry above for how the choke-logic scare turned out; this PRGNUM collision has NOT been checked the same way and should not be assumed harmless). **Blocked on:** tracing `akai_target_rate`/the resample step against one of the affected samples directly -- compare the written AKAI sample header's actual byte 0x01/SSRATE against what the PCM data's own real playback rate implies, on a single isolated Phantz1 zone and a single isolated 12STR zone (they may not share the same bug, given they land on opposite sides of the octave split), before touching the writer. This is a real, ship-blocking defect on the KRZ->AKAI path, independent of and more serious than anything else found this session. **Tool caveat, recorded so it is not re-hit:** `octave_check`/the harmonic-band pitch checks in this harness cannot see a fundamental below the written pitch and will alias it into a higher band -- a fifth down can read as "an octave (or more) up" in the verdict line. Good for the question it was built for (energy at the written fundamental or an octave above), wrong tool for a fundamental that moved down. |

| **KRZ->E4B envelope/sustain moved the WRONG direction on 8 of 12 patches -- opposite of the AKAI->E4B route, real (ratio-based, survives the gain-generation confusion above)** | *(2026-08-30, confidence-matrix rebuild, eosed)* Sustain-ratio error against the source: 8 of 12 KRZ-sourced E4XT patches got FURTHER from the source with today's code than the 22-Aug baseline, 3 closer, 1 unchanged. Largest moves: old PC 13 (new PC 3) +0.114 -> +0.208, old PC 14 (new PC 4) +0.074 -> +0.206. This is the opposite of what the AKAI->E4B route showed the same night (8 of 10 CLOSER, large win from the release-rate fix) -- so whatever moved this route's envelope handling is either KRZ-source-specific, or the AKAI route's fix has a KRZ-side side effect nobody has looked for yet. Not yet investigated. Tuning: unchanged and still not measurable on 9 of 12 (baseline too scattered, per the pre-flight check); the one solid tuning number, old PC 20 (+44.2 cents), is UNCHANGED at +44.9 -- a real, persistent tuning defect on this route, not touched by anything fixed this week. |
| ~~**`append_akai_volumes` allocates past EOF and appends instead of writing**~~ **FIXED 2026-09-10.** Two guards, wanted separately because they fail at different times: the allocator now clamps each partition's declared size to what the file actually contains, so an impossible block is never handed out; and `_put_block` refuses a write falling outside the image rather than letting a bytearray slice-assign append. Regression test truncates a built image to an eighth while the table still declares the full size, and asserts the append **raises** and the file does not grow — confirmed to corrupt silently before the fix. **Tonight's live card write was not exposed** (full-size 300 MB image, and all 1400 pre-existing files verified byte-identical afterwards), but this function is used on the only copy of things and reported success while corrupting. | *(2026-08-24, code review)* It uses the *declared* partition size without checking `len(data)`; past EOF a bytearray slice-assign appends. Reproduced on a truncated image: grew by 1 block instead of 3, directory pointed at block 14 while data landed at 13, and the call **reported success**. |
| ~~**`krz_parser` VelTrk is accumulated and then overwritten 25 lines later**~~ **ALREADY FIXED — row was stale, verified 2026-09-10.** Both Src1/Src2 sites now use `+=` (`krz_parser.py:945` and `:987`), so the seg[4] VelTrk is summed as the comment requires rather than discarded. | *(2026-08-24, code review)* The Src1/Src2 loop does `cur.velocity_to_filter = _amt`, discarding the seg[4] VelTrk the preceding comment says must be *added* because "they sum on the machine" -- and calls VelTrk the dominant mechanism (19 of 91 slots against 1). |
| ~~**`krz_parser` F2 branch reads the F1 tag, so an F3 filter takes its resonance from a shaper**~~ **ALREADY ADDRESSED — row was stale, verified 2026-09-10.** The parser now states the position deliberately: resonance is **not** read for an F3 filter, because F2 is F1's second control input and the F3 equivalent would be F4 at 0x53, which has never been observed carrying one. Inferring it from the pattern is named in the code as the move that produced the invented bandpass. | *(2026-08-24, code review)* Tag 0x50 is written for every layer, so with the new F3 path a layer whose real filter is in F3 gets resonance (up to 24 dB) from F1's second control input -- e.g. an `EVN (2P SHAPER)` in F1. Latent before the F3 work because `filter_type` stayed 0. |
| ~~**`e4xt_cutoff_byte_to_position` says bytes 252-255 are all fully open**~~ **still true, but HARMLESS on real content -- see below** | *(2026-08-24, eosed)* 8-16 kHz band energy at bytes 248..255 climbs **monotonically at ~0.35-0.46 dB per byte and is still rising at 255**. Byte 252 is **2.7 dB** from 255; byte 254 is **1.0 dB** from it. **The two-level control says it is the filter, not clipping:** the pattern did not move when the source dropped 12 dB, and a positive control at byte 200 differs from 255 by 45.8 dB. **Jan's clipping warning was justified -- the FIRST pass was clipped** (bytes 251-255 hitting full scale with up to 172 clipped samples) and would have been reported as saturation. **Our writer's fix is still correct** (it writes 255 for a fully open request and never snaps down -- verified), but the READER flattens 252/253/254 onto 1.0 and loses up to 2.7 dB. **CROSS-CHECKED ON THE MACHINE'S OWN HD0 (2026-08-25):** a third-party bank read back **cutoff 255 on all seven of its wide-open presets** -- so authored content sits at the top and 252/253/254 are not values a human stops at on the panel. The flattening has been harmless in practice; the fix still matters for ROUND-TRIPPING a file that arrives at 252. **Filter-type decode CONFIRMED on the panel** -- our canonical 3 and the machine's parameter id 1 are two scales naming `4 Pole Low-pass`, so the `vpar[58] = 0x00` decode is right and there is no filter-order error. **And the same read confirmed the whole byte->position table on four points:** machine bytes 0 / 18 / 173 / 255 against our 0.1446 / 0.1727 / 0.5155 / 1.0000, exact on all four, on content nobody calibrated against. Byte 0 -> 0.1446 is not a floor bug: the E4XT's minimum cutoff really is ~133 Hz on the nominal scale. **742 voices on the E4XT's own hard disk sit at position 1.0**, so this is the commonest setting there is. Fix: extend the table. |
| **`_E4XT_Q_TABLE`'s shape is wrong in 88..112 -- the machine is FLAT there and then STEPS** | *(2026-08-24, eosed)* Measured peak height against a Q=0 reference: **20.56 / 20.25 / 20.67 / 20.72 / 21.03 / 21.05 / 21.05 dB at bytes 88..110** -- 0.8 dB across 22 bytes -- then a **2.62 dB STEP between 110 and 112**, then flat again. Our table has a gradient across that whole region. **So the '108 vs 104 transcription' question barely matters** (a mis-placed anchor interpolates across a region with no gradient) and **the step at 112 is the real feature**. eosed's metric differs from ours in absolute terms (20.6 dB at byte 96 against our 14.39) so the numbers are not directly comparable -- **the SHAPE is the finding**. |
| **`parse_krz` reports one preset MORE than the file's object table lists** | *(2026-08-24)* A real soundset carries **9** type-36 program objects and the parser returns **10 presets**. The extra one has the envelope signature `0.001 / 0.30 / 0.80 / 0.50` -- the model's own `Envelope()` defaults, the same marker that means "AMPENV Natural mode, not decoded". So it is a preset the file does not list, carrying values the file does not state. **Found by comparing the object table against the parser's output while picking bench material** -- neither alone would have shown it. Harmless on a listen (one extra program that plays something) and not harmless in a conversion, where it becomes a real preset in the output. |
| ~~**`filter_cutoff` is an E4B POSITION, so every AKAI corner below 57 Hz collapses to one byte**~~ **FIXED 2026-08-25, with tests (§CUTOFFHZ)** | *(found 2026-08-25, full corpus sweep)* The model stored cutoff as a position on the E-MU's 57 Hz..20 kHz scale, so **every AKAI FILFRQ below 28 mapped to position 0 and came back as 28** -- and FILFRQ < 28 is **29.4% of the corpus**. **This was the LAST of the three 'physical quantity in one machine's parameter scale' defects**; the release span and the key-follow units were both fixed 2026-08-24/25 and both cost about a third of the corpus in the same way. **`VoiceLayer.filter_cutoff` now carries HERTZ.** Ten parsers and four writers moved: the six that already knew their source's Hz stopped converting it away, the four normalised-knob sources call `nominal_knob_to_hz` explicitly, and each writer converts at the point of use. The AKAI writer's FILFRQ search runs in **log Hz** rather than on positions, and the KRZ writer's velocity fold happens in octaves (`E4B_CUTOFF_RANGE_OCT`) so it no longer clamps a dark source up to the E4B floor first. **Measured, same sweep:** AKAI `filter_freq` **16.1% -> 1.7%** of zones, E4B `filter_cutoff` **100% -> 0.1%**, KRZ **61.3% -> 49.3%** (the rest is a separate defect, next row). What is left on the AKAI side is the **94/95 collision** -- FILFRQ 95 has no measurement of its own and takes 94's corner, which is irreducible until s3ked measures it. |
| ~~The AKAI mute cut needs a HOLD stage and `Envelope` has no way to say it~~ **FIXED FOR K2000, 2026-08-31 (§AKAICHOKECURVE) -- E4B/EIII still carry the old, safe single-stage model, unverified whether they need the same fix** | *(2026-08-25, §155 amendment)* s3ked measured the choke at 2 ms resolution: the cut layer stays at **FULL LEVEL for 4-5 ms**, then ramps to -20 dB by 12 ms. Our `Envelope` is four parameters, so with attack 0 and sustain 0 the level falls from t=0 at a constant rate and the hold is unrepresentable. `AKAI_MUTE_CUT_SECONDS` is now set from the measured RAMP (0.058 s = 97 dB at the rate reaching -20 dB at 12 ms), which leaves a **known residual of about 3.6 dB** over the first 30 ms. **Do not close it by refitting the constant** -- matching the energy instead needs 80 ms and puts the ramp 4.5 ms late, trading a shape error for a timing error. The fix is a model that can express a hold: the E4XT's own envelope has two attack and two decay stages and could render it exactly, and the AKAI writer would round-trip it. **Blocked on** deciding whether `Envelope` grows a hold field or whether the mute cut becomes a separate carried quantity like `release_rate_db_per_s`. *(RESOLVED for K2000, 2026-08-31, found while chasing "the reference preset Layer 1 sounds less metallic/lower pitch than the AKAI original" -- see the the reference preset investigation below.)* The gate ("blocked on deciding") is resolved by NOT growing `Envelope` or changing the shared AKAI-side model at all: `_apply_mute_groups` still hands out the plain single-stage `cut_env` to every format, since only the K2000 is proven to run its release stages to completion regardless of note-off (the whole §KRZENVLOOP investigation depends on that being true) -- E4B/EIII are presumed standard ADSR (note-off-gated release) and UNVERIFIED, so writing a nonzero sustain there risks a WORSE bug (an audible choke held indefinitely). `writers/krz_writer.py::_krz_choke_env` matches the exact mute-cut signature and substitutes s3ked's re-measured two-stage curve (§155 amendment's later, more careful pass: fast fall to **-23.4dB by 12ms**, then **366 dB/s** for the slower second stage, s3ked's own single-rate fallback fit, 12-80ms window, +-5.2dB worst case) ONLY for K2000 output. Test added (`test_akai_mute_cut_gets_the_real_two_stage_curve_on_k2000`), confirmed to fail on revert. **Still open:** whether E4B/EIII gate release on note-off (if NOT, the same fix could extend there; if so, today's shorter-but-safe model is already correct for them and nothing needs to change) -- not yet checked. |
| **AKAI filter key-follow: the law is now measured and fixed for the negative side, and it STILL DOES NOT SHIP -- the real problem is a resonant peak, not the corner law** | *(2026-08-25 -> 2026-08-27, bench, §AKAIKEYFOLLOWHW)* `filter_keytrack` landed 2026-08-24 (`9ff8a7d`) and had never been heard. Measured 2026-08-25 on a controlled pair: turning key tracking on made the key-tracked test EP's conversion much worse (level error at note 96 +8.7 -> -8.4 dB, note 80 +7.4 -> +12.5, non-monotonic response). **2026-08-27: `K_FREQ/12` measured directly, isolated from the resonance confound** (a 14-program bench sweep, Q forced to minimum, wide-open reference to divide out the source) -- confirmed ~1.6x too strong on the NEGATIVE side specifically (the only side ever shipped): K_FREQ -4/-8/-12/-18 gave -0.186/-0.385/-0.585/-0.977 oct/oct against -0.333/-0.667/-1.000/-1.500 predicted, a consistent ~0.59-0.65x undershoot (least-squares 0.622, r2 0.95-0.99). Wired as `AKAI_KEYFOLLOW_NEG_SCALE`. Positive side overshoots instead (~1.4-1.9x, non-constant) and is deliberately NOT corrected -- no clean single factor yet. Same sweep found the AKAI's own pivot clusters near note ~70, not the assumed 64 -- recorded, not yet acted on. **Sent to hardware same night (eosed): the test EP has TWO key-tracking voices, not one -- voice 2 (-12% -> -7%) as well as voice 3 (-46% -> -29%), caught by eosed cross-checking the shipped body's own values rather than trusting the scaled number.** Third-octave distance to the AKAI source, mean across 7 notes: OLD law 7.64 dB, NEW (0.622) law 6.20 dB, NO key tracking 4.97 dB. **The fix is real -- note 80 improves 13.03->8.98 dB, note 96 15.52->9.04 dB -- and it still loses to shipping nothing, by 3.8-4.75 dB at the two notes that matter.** **The reason, confirmed rather than guessed at:** note 96's LEVEL is non-monotonic in cord amount -- 0% -> +6.2 dB, -29% -> +10.0 dB (LOUDER), -46% -> -10.8 dB (collapsed) -- while the third-octave DISTANCE is monotonic (4.30 -> 9.04 -> 15.52 dB). Level and timbre disagree about which direction is better, which is the signature of a corner-frequency control sweeping a RESONANT PEAK: **the calibration bench forced Q to minimum to measure the corner law cleanly; the shipping conversion writes Q 0.59-0.70 on these exact voices.** So 0.622 is plausibly the right law for the corner's POSITION, and the audible result stays wrong because it is dominated by the peak riding on that moving corner, which no scalar correction to `filter_keytrack` alone can fix. **STILL DO NOT SHIP -- and the root cause is now identified, not just fenced off.** *(2026-08-27, finer sweep, six arms 0/-10/-20/-29/-40/-46)* Third-octave distance is **monotonic in cord magnitude and ZERO IS THE OPTIMUM** -- 4.92 dB mean at cord 0 rising to 7.64 at -46, no intermediate value beats zero, so this is not "0.622 undercorrects", there is no scale factor that helps. Level error at note 96 shows a CLIFF between -29 (+10.0 dB) and -40 (-5.7 dB) -- a cord amount exists that matches the AKAI's level, at ~10-12 dB spectral distance against 4.72 at zero, so level-matching and timbre-matching point opposite directions on a mapped curve, not just three points. **The actual mechanism, found by resolving the response in TIME, not just frequency:** voice 3 also carries `FilterEnv->FilterFreq` at 50% depth, so the corner is not static -- it SWEEPS during the note, and the key cord only sets where that sweep starts. At cord -29, the dominant 4 kHz band is +11.8 dB at 50 ms into the note and -12.5 dB at 1150 ms -- a 24 dB swing inside ONE note, against 8 dB at cord 0. **This is a genuine model-shape gap, not a miscalibration: `filter_keytrack` and `filter_env_cents` are independent static fields, but on real AKAI hardware a key-tracked, envelope-modulated filter is a single coupled sweep whose audible result depends on where the envelope excursion happens to land relative to the note's own partials -- which the bench calibration could not see, because it measured K_FREQ with Q at minimum AND NO ENVELOPE IN PLAY, removing both of the things that make the shipping path misbehave.** Caveat on the record (eosed): note 96 is a near-pure tone, "an excellent detector and a poor place to read magnitudes" -- maximally sensitive to exactly where a resonance lands, so some of the non-monotonicity is the 1-second averaging window reading a moving transient, not a stable law; note 80 shows a milder version of the same shape. Does not change the verdict (zero is still optimum on the monotonic metric) but matters before fitting anything further to these numbers. **Blocked on:** a genuinely joint corner+envelope-excursion model, or (pragmatic middle ground, not yet tried) scoping `filter_keytrack` to voices where `filter_env_cents` is near zero, since the coupling only bites when both are active on the same destination at once. *(2026-08-28, joint session with s3ked and eosed)* **The real program has 6 keygroups, not 4 -- our reader collapsed three K_FREQ-0 layers into one "voice 0".** Three note ranges, each covered by an untracked twin (K_FREQ 0) and a tracked twin (K_FREQ -1/-4), identical key AND velocity span, `KGMUTE 0` on all six -- a textbook §155 choke pair our reader does not resolve (see the new row below). **Which twin survives was unverified until now: measured live on hardware, the TRACKED twin wins** (kg5, the slow/soft one) -- confirmed two independent ways, release slope (15.06-15.10 dB/s matching kg5 alone, 20x apart from kg4 alone) AND peak level (mix equals kg5-alone exactly, so kg4 contributes nothing once choked). **This kills the "choke explains the release-too-long complaint" idea directly** -- the AKAI's own surviving release is already the slow layer, so stacking both would sound fuller at the attack, not longer. Initially thought to also explain the masking finding above; **then tested directly (eosed, voice 3 alone vs stacked, positive control confirmed the edit worked): at notes 80/96 voice 0 is completely inaudible (0.05 dB difference stacked vs solo) -- the masking hypothesis is REFUTED at the two notes this whole investigation has been run on.** (May still hold below key 72, where voice 0 measures 47-52 dB of real signal solo -- untested.) **With voice 0 out of the picture, one clean finding remains: our converted voice 3's own release is 1.6-1.8x too fast against the AKAI's surviving tracked layer** -- 23.5-27.5 dB/s (E4XT, cord 0, notes 80/96) vs 15.1 dB/s (AKAI, s3ked, live) -- independent of key-tracking entirely, and worse at -20% cord (47 dB/s at note 96). **This is a separate, general AKAI->E4B release-mapping bug, not a key-follow bug — see the new row below for it, not here.** Still contradicts Jan's own listening report (he hears the E4XT release as longer; three independent measurements now agree it is faster) -- unresolved, needs to know exactly what he is listening for before trusting any of these metrics over his ears. Separately, `AKAI_KEYFOLLOW_NEG_SCALE = 0.622` was checked against **four independent hypotheses for why it disagrees with s3ked's own K_FREQ/12-confirming measurement (§167, unscaled, r2 96-103% across ten points)** -- masking (ruled out, the calibration bank has no second layer to blend with), band-limited compression (ruled out, the residual is flat across a 4.5x magnitude range instead of growing), a pivot error (ruled out, the fit is an ordinary least-squares slope with no origin term, provably pivot-independent), and a fixed-frequency anchor in the corner estimator's reference band (the precondition is real -- `ref_lo=50, ref_hi=150 Hz` is genuinely fixed -- but s3ked simulated the mechanism against a real filter shape and it has only two stable states, ~1.0 or ~0, with a cliff at k~1 dB/oct; 0.622 sits in neither). **All four refuted. The discrepancy stays open and unexplained** -- next step, if picked up, is running the same sweep design on s3ked's own rig against a difference-based corner estimator (source cancels exactly, immune to this whole class of bias) rather than an absolute threshold, same physical instrument either way since there is only one S3000XL on the bench. |

| ~~**The AKAI mute-group choke is not applied when both keygroups cover the IDENTICAL key range**~~ **NOT A BUG -- checked against the actual code and data, 2026-08-28, before touching anything** | Hypothesised alongside §AKAIKEYFOLLOWHW after s3ked found the real program's three note ranges are each covered by two same-range, same-velocity, `KGMUTE 0` keygroups. Before writing a fix, ran our own reader against the real source (`parse_akai_image` on the actual bank) and checked directly: **the choke already fires correctly for every one of the three pairs.** The three "loser" keygroups (short/bright, lower index in each pair) are already merged into one voice carrying the click-cut envelope (`decay=0.058s, release=None`, exactly `AKAI_MUTE_CUT_SECONDS`); the three "winner" keygroups (tracked, long/soft, higher index) each keep their own full envelope (`release_rate=15.33 dB/s`, matching s3ked's live 15.1 dB/s) AND their own `filter_keytrack` (0 / -0.052 / -0.207, matching K_FREQ 0/-1/-4 through the negative-scale law exactly). `_apply_mute_groups`'s "loser = min(a,b)" assumption happens to pick the right keygroup here because the source authors it that way, and eosed's own solo-vs-stacked measurement already showed the surviving click is inaudible (0.05 dB) at the notes tested -- there was nothing to fix. Recorded so the next reader does not re-propose this from the same premise. |

| ~~**AKAI->E4B release rate reads ~1.6-1.8x too fast, independent of key-tracking**~~ **CONFIRMED FIXED across a real 22-patch set, with two overshoot exceptions -- 2026-08-29** | *(2026-08-28, eosed, isolating voice 3 from the masking layer above)* With the masking layer confirmed silent at the notes tested, the converted voice's own release measured 23.5-27.5 dB/s against the AKAI's own surviving tracked layer at 15.1 dB/s (s3ked, live) -- a genuine AKAI->E4B release-time mapping error. **The listening contradiction that blocked this row was resolved 2026-08-28: Jan had a different AKAI preset sounding on the bench, not the one under test -- no real contradiction, all measurements stood.** *(2026-08-29, confidence-matrix rebuild)* Re-measured across the whole 10-PD TapemakerKAI->E4B set (6 EP-family + 4 pitched bass), sustain-level error against the source (old vs fresh conversion, source term cancels): **8 of 10 patches move 6-10x closer to the source**, `decay_half_ms` lengthening 1.4-5.6x on the EP family -- exactly the direction the too-fast finding called for, confirmed working on real material, not just the one test voice. **Two patches overshoot instead:** PC 11 (sustain error -0.058 -> -0.249) and PC 15 (+0.087 -> -0.313; source sustain 0.398, conversion went 0.485 -> 0.085) -- both were already close to the source (within +/-0.09) before this fix and are now roughly 4x too far the other way. Not yet root-caused; possibly these two had little error to correct and the fix over-applies when the starting point was already near-correct. PC 20 and PC 21 are percussive with no sustain phase on either side, unaffected either way. **PC 11's clipped capture was re-shot clean, 2026-08-30 -- its overshoot verdict is CONFIRMED, not withdrawn** (d_sus -0.058 -> -0.269 on the clean re-capture, clipping was not what produced the FURTHER verdict). Both PC 11 and PC 15 overshoot for real. See the new row below for the clipping finding and why it mattered anyway (it found a second, independent problem). **Second correction, same re-capture session: the "8 of 10 closer" headline needs softening to 6 of 10.** Re-capturing SIX unchanged (control) patches found `sustain_ratio` itself has ~0.06 of between-session noise -- the metric samples the envelope at `ipk + 0.8*(hold_n - ipk)`, anchored to where the ATTACK PEAK lands, so a patch with a flat-ish envelope shifts a long way in the ratio from a small change in peak position alone, unrelated to anything in the conversion. Two of the eight "closer" patches (shift 0.069 and 0.090) sit inside that noise floor and are WITHDRAWN as evidence either way; the other six (0.101-0.227) comfortably clear it and stand. **Net: 6 of 10 closer, 2 further (confirmed), 2 unresolved** -- direction and headline hold, the tail does not. Any other conclusion in this project resting on a sustain-ratio difference under ~0.06 has the same exposure and should be re-checked. Anchoring the metric to note-on instead of the peak would remove this but costs comparability with every existing number -- not done, flagged as a design decision for whoever picks it up. **Third correction, 2026-08-30: the "6 of 10" softening above was itself wrong -- restore to 8 of 10.** *(eosed, recomputing from raw features after unrelated score.py work prompted a recheck)* PC 17's cited shift of 0.090 came off a table that mixed two different note sets, already superseded by a fix made an hour earlier the same evening; recomputed from raw features its real shift is 0.133, comfortably clear of the 0.058 noise floor. All ten patches recomputed fresh: PC 10 0.169, PC 12 0.101, PC 13 0.069 (marginal but clears it), PC 14 0.108, PC 16 0.142, PC 17 0.133, PC 18 0.195, PC 19 0.208 -- eight closer, none newly withdrawn. **Net, corrected: 8 of 10 closer, 2 further (PC 11, PC 15, both confirmed) -- no unresolved tail.** The noise-floor finding itself stands (0.058 is real and PC 13 needed it to be checked); what failed was applying a new rule to an already-superseded table instead of recomputing from raw data. |
| ~~**The KRZ writer destroys a K2000's own velocity->filter cord and smears it into the cutoff**~~ **FIXED 2026-08-25, with tests (§KRZVELFOLD)** | *(found 2026-08-25, KRZ corpus sweep)* `krz_writer._patch_layer` folded `max(0, velocity_to_filter)` into the static cutoff and wrote no cord, so a K2000 program read and rewritten lost the cord it had -- **46.7% of zones**, and it was also what kept `filter_cutoff` at 49.3% instead of its 3.5% floor. **The premise behind the fold was wrong about the DESTINATION, not about the source.** It avoided "a VelTrk sweep from the K2000's 16 Hz floor, which would mute softly-played notes the MPC keeps audible" -- but `hob_f1[4]` is **unipolar from the resting corner** (the reader has recorded it as `(0, VelTrk)` since 2026-08-17), so soft notes sit at the voice's own cutoff and hard notes at cutoff + depth. That is exactly the MPC semantics Jan checked on hardware. Writing the cord serves the source the fold was designed for AND stops destroying a K2000's own, so **no source-semantics flag was needed** -- the two cases were never different. The fold also took `max(0, ...)`, dropping every DARKENING routing; the K2000 has those (observed at -4600 ct) and they are now written signed. A source with a nonzero velocity FLOOR still folds, because VelTrk has no floor byte -- **0 of 1383 velocity routings in the corpus take that branch**, and it prints when it does. **Measured: `velocity_to_filter_cents` 46.7% -> 0%, `filter_cutoff` 49.3% -> 0%.** The model's 20 kHz ceiling was the last 3.5% and is also gone: the K2000's byte reaches 25088 Hz and the writer now clamps to its own range instead of the E-MU's. |

| **The MPC's velocity->volume curve is NOT dB-linear and all three targets are, so the scalar swing we carry is 14 dB RMS wrong in the middle of the range** | *(2026-09-04, §MPCVELSHAPE, found by an end-to-end check meant only to confirm the `Vel+` wiring)* `VoiceLayer.velocity_to_volume_db` is one scalar -- the v1..v127 span in dB -- which describes a response completely only if it is straight in dB. AKAI (1.19557 dB/unit), K2000 (0.27618 dB/unit, r2 0.999996) and E4XT (0.75097 dB/unit) all are. **The MPC is not:** `gain = (1-s) + s*(v/127)` is amplitude-linear, so in dB it is LOGARITHMIC, and a single span cannot describe it. Converting a real MPC keygroup and evaluating both laws: the two agree at v1 and v127 and diverge by **19.75 dB at v32, 15.09 at v64, 7.92 at v96** -- the range people actually play. **The span we pick is the worst available one:** anchoring on v1 lets one extreme point at the bottom of a log curve set the slope for everything. RMS against the true curve is **14.03 dB**; the best dB-linear fit over v1..v127 is 18.9 dB swing at 4.18 RMS, over v32..v127 **13.0 dB swing at 0.76 RMS**, over v64..v127 10.9 dB at 0.21. **NOT caused by the `Vel+` change and not fixed by reverting it** -- the same comparison under `Vel<` gives the same errors, since the mismatch is between a logarithmic source and a dB-linear destination and the pivot only decides where they are pinned together. Present since the MPC law was wired 2026-09-01, and it reaches the K2000 and AKAI targets too. **Not a defect in the MPC law**, which is measured to 0.033 dB RMS -- the defect is the model field it is squeezed through. **MEASURED ON JAN'S OWN LIBRARY 2026-09-04** (3,776 presets carrying the field, off the MPC One's SD-card backup under `EXPANSIONS/`; `KEYGROUPS/` is ConvertWithMoss output where 0 of 60 carry it): **66.5 % sit at uniform 1.0**, i.e. exactly the logarithmic extreme this row is about and 14 dB RMS off before the fit; 16.9 % ask for none; 12.3 % a uniform other value (3.3-11.3 dB); **4.2 % (157) MIXED within one preset**, the part no scalar can rescue -- one 7-voice piano pairs voices at 0.0 dB with voices at 42.1 dB in the same preset. Supersedes the earlier 263-preset sample. **RESOLVED 2026-09-04 by option (2), Jan's call** -- the model now carries the curve and each writer fits it; see the `feat:` commit. Original options were: (1) fit over v32..v127 instead of taking the v1..v127 span -- one line in `xpm_parser`, RMS 14.03 -> 0.76, gives up a v1 endpoint that sits 30 dB below v32 and is inaudible; (2) carry a curve descriptor in the model beside the scalar so each writer can decide -- more honest, much more work, worth it only if a second non-linear source appears; (3) leave and document. **Method note: this is the second finding of the day that no unit test could have caught** -- the tests pin what the writer writes, not whether what it writes SOUNDS like the source, because nothing in them knows the source machine's law. |
| **Every K2000 voice we write inherits #199's 35 dB velocity->amplitude, and the model has no field to carry the source's own** | *(2026-09-01, §KRZAMPVEL, found by the `_TPL_LAYER` audit)* `_patch_layer` writes exactly ONE byte of the F4/AMP segment (0x53): byte 14, the pan nibble. Bytes 0-13 are inherited verbatim from `_TPL_LAYER`, which is a faithful capture of ROM #199 -- **confirmed byte-for-byte against today's ROM object, zero drift** (k2kremote dumped #199 and diffed all 18 layer segments plus both globals programmatically against the arrays in the source; every one identical). So this is NOT template drift. The finding is that **#199 is not a neutral donor**: its byte[4] is `35` = VelTrk **35 dB** and byte[1] is `6` = Adjust **6 dB**, and 35 dB of velocity-to-amplitude is a substantial musical choice where neutral would be 0. **Not a double-application** -- checked: the KRZ writer encodes velocity->amplitude nowhere else, and `models.common` has no `velocity_to_volume`-style field at all, so this inherited 35 dB is the ONLY velocity->amplitude in our K2000 output. **The gap is that it comes from a template rather than from the source.** Every voice gets the same dynamic response regardless of what the source program specified, and the AKAI's own velocity->level behaviour (it has one; the reader currently takes `V_LOUD` only as a static per-zone `volume`) cannot be honoured because there is nowhere in the model to put it. **Blocked on** two things, in order: measuring the AKAI's own velocity->amplitude law on hardware so there is something real to carry, and then a model field to carry it (which every other writer would also have to honour, so it is not a KRZ-local change). **Until then 35 dB is an unexamined default, not a chosen one** -- and it may well be a reasonable default, which is the honest position rather than the alarmed one. Low audible risk at high velocities (where Jan plays, 100-127, everything is near the top of the curve either way); the exposure is at soft velocities. |
| ~~**The KRZ writer emits pan and the KRZ reader never reads it**~~ **ALREADY FIXED — row was stale, verified 2026-09-10 by round trip.** Mono pan round-trips exactly (0.0, ±1.0 all recover; 0.5 → 0.571 is the 7-step grid). **And the interaction the row warned about is handled correctly**: a stereo layer's byte 14 carries channel routing (0x94, high nibble −7) and would read as hard left, so the parser gates on the SAMPLE's own `channels >= 2` — a real field, after an earlier attempt guarded on an attribute no dataclass has and silently never fired. Verified by building a genuinely stereo voice; a first attempt at this check used `channels=1` and never triggered the stereo path at all. | *(2026-09-01, §KRZPANREAD, from the cross-format field-coverage audit)* `_patch_layer` writes pan into HOB `0x53` byte 14's high nibble as a -7..+7 step; `krz_parser` never inverts it, so every zone comes back `pan = 0.0`. **Measured on 40 real K2000 banks: 1715 of 2504 layers carry a non-zero pan (68%)**, so this is not a corner case -- hard-left (-7) alone appears 412 times. Same family as §AKAIZONELOUD / §AKAITUNEREAD / the `0x1a` velocity-loudness hardcode: a field written but never read. **One interaction to respect:** the stereo path also uses byte 14 (`s53[14] = 0x90 if stereo`), where the high nibble is channel routing rather than a user pan, so a naive inversion would report hard-left on every stereo layer. |
| **The E4B writer does not DROP velocity->volume -- it imposes a CONSTANT one, 23.6%, on every voice, inherited from the template and never chosen** | *(2026-09-01, §KRZAMPVEL follow-up)* The AKAI reader populates it and the AKAI writer consumes it; KRZ and EIII do neither. **CORRECTION 2026-09-01 (eosed, read off the machine): the E4B case is NOT a dropped field, it is an imposed one, which is worse because a dropped field is silent and this is audible.** `_MOD_TMPL` slot 0 is `0x0C 0x40 0x1E` = **`Vel<` -> `AmpVol` at amount 30/127 = 23.6%**, and `_write_voice` copies that template verbatim whenever `needs_mod` is true. Confirmed on hardware: cord slot 0 of every voice of all 22 resident presets reads `Vel< -> AmpVol 24`, template and machine agreeing to the byte. **So an AKAI program with `V_LOUD` 0 -- which s3ked measured in §171 as GENUINELY neutral, 0.00001 dB/unit -- arrives on the E4XT carrying a velocity->volume response it never asked for.** **And it is inconsistent rather than merely constant:** `needs_mod` gates whether the template is written at all, so a voice with no filter envelope, no key-track, no velocity->filter and no LFO gets no mod table and therefore NO velocity->volume cord -- the velocity response of a converted program depends on whether some unrelated cord happened to be non-zero. Flagged as a code-path reading rather than an observation: on the material checked it never fires (0 of 31 voices on MXS3, 0 of 12 converted presets resident on the E4XT), so it is latent, not seen. **Same shape as §KRZAMPVEL one format over** -- the K2000 inherits VelTrk 35 dB from ROM #199 the same way -- so BOTH non-AKAI writers impose an unchosen velocity->amplitude law, from two different templates, in two different conventions. **Settled empirically at the same time: the E4XT's own default convention is `Vel<`, the INVERTED source** -- neutral at 127, attenuating downward, i.e. the **K2000's** pivot and not the AKAI's. Unlike the factory Velocity->FilFreq default (amount 0, never heard), this one is at 23.6% on every voice and is sounding. Blocked on: what 23.6% of `Vel<` is worth in dB -- now a more useful number than before, since it is the swing the converter currently imposes on everything. The K2000 half is deliberately held pending Jan's decision on the pivot-asymmetry offset, but **E4B and EIII have no plan at all** -- and the E4XT certainly has a velocity->amplitude control, so this is a genuine hole rather than a target limitation. Blocked on: an E4XT-side law (eosed), then plumbing.**THE LAW LANDED 2026-09-01 (eosed §83) AND THE IMPOSED SWING IS 22.37 dB.** `swing_dB(v1->v127) = 0.9470 * amount_percent`, linear in velocity (r2 0.9997+) and in the setting, three amounts agreeing to +/-0.07 %; amount 0 is genuinely neutral at 0.01 dB, which also proves this cord is the only velocity->volume path in the voice. So the template's 23.62 % is **22.37 dB of velocity swing imposed on every converted voice**, and on an AKAI source with `V_LOUD` 0 -- measured genuinely neutral -- all 22.37 dB of it is unrequested. Recorded as `E4XT_VEL_AMPVOL_DB_PER_PERCENT` / `E4XT_IMPOSED_VEL_AMPVOL_SWING_DB`. **AND THE FIX IS NOT 'PICK THE RIGHT SOURCE'.** Pivots measured in the same run: `Vel+` at velocity 0, `Vel<` at 127, and **`Vel~` at 89.4 -- NOT 64**, with the same ~9.5 dB span as the unipolar sources rather than twice it, so it is not `2*Vel+ - 1` either and no mechanism is offered for 89.4. **No E4XT source pivots at 64**, so the AKAI's pivot-64 swing has to be CONSTRUCTED: `Vel+` at amount `A = swing/0.9470`, plus a static volume trim of `-swing/2` to move the pivot. Two hazards, both measured rather than supposed: (a) the trim must go through `e4xt_volume_byte`, NOT be written as dB -- `E4_GEN_VOLUME` asked -12 moved the capture -8.86 dB, which independently confirms our own `e4xt_byte_to_volume_db` (predicts -9.172) from a completely unrelated path; (b) 43 dB of AKAI swing needs -21.5 dB of trim against an `E4XT_VOL_MEASURED_FLOOR_DB` of -22.90, so the loudest real sources sit at the edge of the calibrated range. Blocked on: Jan's call on whether to construct the pivot or accept the K2000-convention swing, then plumbing. **FIXED 2026-09-01 (Jan's decision).** The writer now has THREE states instead of an unconditional write: a known swing is written; a source that asks for a response without stating a measurable one keeps the template value; a source that states nothing gets **no velocity->volume cord at all**. **Jan's instinct drove the shape of this** -- asked to choose a default, he asked why the other readers did not populate the field instead, and the answer was that they all could: KRZ (`AMP VelTrk`, 0x53[4], measured 1 dB/unit, pivot 127), E4B (the cord table this parser already walked for four other routings) and XPM (`VelocitySensitivity`, present in every keygroup of every file) were all specified and simply unread. All three now are. **Measured impact over 10,933 real AKAI programs: 998 (9.1 %) have V_LOUD 0 and were receiving 22.37 dB of swing they explicitly declined, and 4,202 (38.4 %) had a swing differing from the imposed value by more than 3 dB.** Over 263 real MPC presets: 13.7 % ask for none, and 8.7 % vary keygroup-to-keygroup, which a single template cord cannot express at all. **Still open, and deliberately:** ~~(a) MPC's dB law for a non-zero `VelocitySensitivity` is unmeasured, so those keep the target default rather than an invented constant -- one MPC One bench session closes it~~ **CLOSED 2026-09-01 at that very session: `gain = (1-s) + s*(v/127)` in AMPLITUDE, RMS residual 0.033 dB over 81 points, pivot 127. Wired as `mpc_velsens_swing_db`; sensitivity 1.0 = 42.08 dB, which fits every target's field. Still listed as open in this row and in the parser comment until 2026-09-04, when re-reading it caused me to report it to Jan as open a second time -- a stale 'blocked on' outlives the block and costs someone the same question twice;** (b) the cord is written as `Vel<` (pivot 127), so an AKAI pivot-64 swing is carried at the destination's convention rather than the source's. Constructing the source pivot needs `Vel+` plus a -swing/2 static trim and runs out of range against `E4XT_VOL_MEASURED_FLOOR_DB` on the loudest real sources; ~~eosed's framing is that `Vel<` is not a lossy fallback but the convention the machine and its whole factory library use~~ **REFUTED 2026-09-04 by the corpus census Jan asked for (§E4XTVELSRC): a commercial EOS-native library CD-ROM is 96.9 % `Vel+` -- 11,449 of 11,806 voices over 2,035 presets -- against 0 in the 23 vintage-synth ROM conversions on the E4XT's own disk, which are tool output and were the population the original claim actually rested on (22 presets resident in the machine's memory, including our own conversions). `Vel<` IS the machine's default source for a NEUTRAL cord (every one of the 573 amount-0 cords names it), which is the true statement the false one was built from. The clipping objection goes with it: those 11,449 `Vel+` voices budget NO headroom for the swing -- mean static level -2.9 dB against a mean swing of 28.6, correlation +0.068 -- so nominal is not a ceiling on this machine.** Blocked now on ONE measurement rather than a decision: whether a `Vel+` voice at velocity 127 and nominal level actually has that headroom on the E4XT, answerable by one capture at two velocities on a library `Vel+` preset. **THE DISC IS BUILT AND STAGED (2026-09-04), `CD1-VELPLUS.iso` on the EMU card at SCSI id 1** -- procedure in `docs/re_procedures/e4xt_velplus_headroom.md`, generator `tests/re_banks/gen_e4xt_velplus_headroom.py`, runner `tests/re_banks/measure_e4xt_velplus.py`. ONE preset with THIRTEEN voices on keys 48-60 differing only in the cord, so it is ONE capture and no program changes (13 presets would have been 13 captures against a JACK client ceiling near 8, and would have needed walk-desync controls). Two sample levels -- full scale and the same sine 20 dB down -- so an ENGINE ceiling (both series cap at one absolute level) is separable from a SAMPLE-headroom one (the quiet series stays clean 20 dB further); a single level would leave the two tangled. Sine rather than the usual harmonic tone because the deciding observable is THD, not level: 'declined to get louder' and 'got louder and broke' are different answers. Verified by re-reading the bank back OFF the card: 13 voices on keys 48-60, 10 `Vel+`, 1 `Vel<` fingerprint, 2 no-cord controls. Awaiting one ~2.5 minute capture. **MEASURED 2026-09-04, SAME DAY (§VELPLUSHDRM): `Vel+` DOES NOT CLIP.** 65 notes, one capture, controls agreeing to 0.02 dB and the no-cord control velocity-flat to 0.08 dB. Every `Vel+` cell tracks prediction to within a few TENTHS of a dB up to **+43.1 dB above nominal**, with THD 0-1 % throughout -- nothing in the bank clipped at any velocity or level. There is a soft ceiling at **+47.6 dB of cord contribution**, and the two sample levels earned their place: A and B stop at the SAME contribution while sitting exactly 20 dB apart in absolute level, so **the ceiling is in the CORD, not the output** -- a quieter sample buys no more swing and a louder one loses none. The library's mean swing of 28.6 dB (p90 38.7) is inside the linear range with 15 dB to spare, so its 11,449 no-headroom `Vel+` voices are not living dangerously. **Both arguments that decided this field are now gone** -- the premise refuted by census, the clipping objection by measurement -- so if `Vel<` stays it should be for the one honest reason left, that it needs no static trim, and not for either of those. Still Jan's call; nothing about the pivot being a pure LEVEL choice has changed. **HALF-FIXED 2026-09-04 (§VELPIVOT): the pivot ERROR is now corrected even though the cord source is not changed.** Writing `S` about 127 when the source pivots at 64 is wrong by a constant `S*(127-64)/126 = S/2` at EVERY velocity, so it is a level rather than a curve -- applied through `e4xt_volume_byte` at both level sites (`vpar[54]` single-zone, per-zone `entry[15]` multi-zone), with the whole preset shifted DOWN by its largest offset so the correction fits in the direction the field has range in. 96 % of 10,933 real presets fit; the other 4.5 % clamp at `E4XT_VOL_MEASURED_FLOOR_DB` and now SAY SO in the conversion log. What remains open is only whether to construct `Vel+`+trim so the source's pivot is native rather than compensated. |
| ~~**Every MPC filter constant was an E4XT number**~~ **MEASURED AND WIRED 2026-09-01 (§MPCFILTER)** | The XPM path converted cutoff through an unmeasured nominal scale, filter-envelope depth through the E4XT's 4383 cents, velocity->filter through its 9120, and resonance through its 25.51 dB applied LINEARLY -- none of which had any claim to describe an MPC. All measured on Jan's MPC One in one session. **Filter-frequency modulation is one law: every destination adds in KNOB units at full efficiency, so full depth = the whole knob range = 11409 cents**, confirmed three ways to 0.8 % (velocity 11409, envelope Depth 64 -> 11394, Depth 96 -> 11485). The envelope constant was **2.60x too small on the 41.6 % of real keygroups that use one** -- they were all converting at 38 % of their true sweep. Resonance is per filter type and non-linear (`Low 2: 0.15 + 18.21*res^0.502`, `MPC LP: 2.15 + 20.54*res^0.390`); the old linear E4XT treatment was wrong in BOTH directions, understating gentle resonance ~2.7 dB and overstating strong resonance ~7.6 dB with the error changing sign mid-range. **MPC LP is not neutral at resonance 0** (+2.15 dB inherent). `KB>FLT` at max is 0.945 oct/oct, not 1.000. **And §MPCCUTOFF's curve now applies to the CLASSIC XML path**, which it did not before: that split was drawn on file format when the curve belongs to the ENGINE, and a classic XPM on a modern MPC runs the same legacy keygroup engine -- confirmed at two knob positions to 0.8 %, which matters because the local corpus is 6,079 classic XPMs. Wired in `xpm_parser`, six tests in `tests/test_xpm_filter_laws.py`, each confirmed to fail on revert. **Note this was the FIRST test to exercise `parse_xpm` at all** -- changing the envelope depth by 2.6x had broken nothing. **NOT YET LISTENED TO:** the corrections are large and MPC-sourced conversions will sound materially different; A/B before anything goes near a card. |
| **The KRZ writer imposes ROM #199's `AMP VelTrk 35 dB` on every voice, and the model now KNOWS the source's value** | *(2026-09-02, Jan by ear on a converted MPC bass: "the source has no velocity->volume, the conversion products have")* Confirmed end to end: the source XPM carries `VelocitySensitivity 0.000000` on every keygroup, our reader correctly records `velocity_to_volume_db = 0.0, pivot 127`, and `krz_writer` writes **AMP VelTrk = 35 dB** anyway -- inherited from the `_TPL_LAYER` donor and never overwritten. 35 dB is not a trim, it is the patch's whole dynamic response, invented. **THE PIVOT BLOCKER DOES NOT APPLY TO MPC SOURCES.** §KRZAMPVEL was held because the AKAI rotates about velocity 64 while the K2000 attenuates from 127, so carrying the swing across would sit half the swing low at every velocity -- a real problem needing Jan's decision. But the **MPC's own pivot is 127** (measured 2026-09-01: gain = (1-s) + s*(v/127), unity at v127), which is the K2000's convention exactly. So for MPC sources there is no asymmetry to resolve and the write is unambiguous: `hob_f4[4] = round(swing_dB)`, the byte being the v1..v127 swing 1:1 (k2kremote, ten settings, max deviation 0.21 dB). AKAI sources stay blocked on the pivot question; MPC and KRZ sources do not. **PIVOT UNBLOCKED 2026-09-04 (§VELPIVOT), so AKAI sources are no longer held.** The mismatch is a CONSTANT `S*(P_dst-P_src)/126` -- no velocity in it, 0.0000 dB of spread over v1..v127 -- so it is a level, and the level moves DOWN: the whole preset is shifted by its own largest offset (Jan's fourth option) rather than compensated upward past the Adjust knee. Wired in `_preset_layers` + `_patch_layer(level_offset_db=)`, sharing one clamped write with the tremolo trim. Over 10,933 real programs: median shift 12.0 dB, max 29.9, all fitting. **And it is a no-op on every AKAI source we hold, measured by byte-diff rather than argued: `V_LOUD` is per PROGRAM, so all of a preset's voices carry the same swing, so the offset equals the shift and the difference is zero** -- a real 157-preset card converts byte-identically with the correction disabled, `AMP Adjust` staying at the template 6 on all 190 layers. The pivot mismatch is a FLAT ~12 dB level difference, which is a knob; the thing a knob could not fix was the swing, and that is what changed here -- the same card now writes VelTrk 24/12/30/36/43 from the source instead of the inherited 35. So this row's audible fix is the swing; the pivot work is a correctness guarantee with a measured zero blast radius. **Not wired** -- Jan filed it as "a finding for later", and it changes the dynamics of every MPC->KRZ conversion, so it wants its own listen rather than riding along. Note it did NOT affect the 402/403 A/B judgement: both presets carry the same inherited 35, so the comparison was clean. |
| **MPC 3.9 KEYGROUPS have TWO filters, serial or parallel; our reader maps ONE and ignores the routing** | *(2026-09-01, Jan at the bench)* **Terminology, because this project uses "MPC 3" for the FILE FORMAT and it is not the same axis as the filter engine:** a 3.9-firmware machine offers 3.9 keygroups (two filters, serial or parallel) and LEGACY keygroups (one filter). Legacy is still MPC 3 software. Every measurement this project has taken -- §MPCCUTOFF and the 2026-09-01 velocity→filter run alike -- was on LEGACY keygroups. The MPC 3 JSON path reads `filterType` / `filterCutoff` / `filterResonance` / `filterEnvelopeAmount` / `filterKeytrack` / `filterVelocity` -- one filter's worth -- and nothing else. There is no second-filter read and no read of the routing/blend that decides how the two combine; §MPCCUTOFF already noted a `filterBlend` field in the same JSON that this project has never parsed. **So a 3.9 program using both filters converts as though only one existed, silently, and if the program leans on filter 2 the cutoff we carry may be the wrong filter's entirely.** Not a regression -- it has always been so -- but it was unrecorded. **Priority is genuinely low and the reason is worth keeping:** Jan's assessment is that 3.9 filters are far more complex and there is little source material in the wild yet, and the local corpus is 6,079 CLASSIC XPMs, all of which play in legacy mode with a single filter and convert correctly. **A cheap diagnostic exists** if this is ever picked up: the fitted roll-off slope says how many poles are in circuit -- ~12 dB/oct is one 2-pole, ~24 is two in series. §MPCCUTOFF's slopes were -11.6 / -12.5 / -11.8, which retroactively confirms only one filter was active for that measurement, so that constant is clean. Blocked on: source material to test against, and a model decision -- `VoiceLayer` has one filter, so a serial pair has nowhere to go without either cascading into one approximate corner or adding a second filter to the model, which every writer would then have to honour. |
| **`lfo1_to_volume` (tremolo) is populated by NO hardware reader** | *(2026-09-01, same audit)* Only `sfz_parser` and `sf2_parser` ever set it, and the AKAI, E4B, KRZ and EIII readers all ignore tremolo. **CORRECTION to this row's first version, which said the KRZ writer could emit it: it cannot.** Its single mention in `krz_writer` is inside `_VOICE_FIT_FIELDS`, the list of continuous fields AVERAGED during layer fusion -- so the field is carefully key-span-weighted on merge and then written to no byte by any writer. A field read from two soft formats, averaged correctly, and discarded. The false positive came from grepping for the field NAME rather than for an actual byte write, which is worth remembering when auditing coverage this way. So tremolo is lost from every hardware source we read, and can only ever arrive from a soft-format source. Worth checking per format whether the field exists to be read before assuming it is a reader bug: the AKAI's LFO depth routes via `L_PTCH` to pitch and may have no loudness destination at all, in which case the gap is real for E4B/KRZ but not AKAI. **UPDATE 2026-09-01 (k2kremote, §KRZF4AMPDEPTH): the K2000 WRITE side is now specified.** `F4 AMP` carries `Src1` at byte offset 262 (OFF=0, LFO1=114) and `Depth` at 263, signed i8, measured at **1.0 dB/unit** with panel rails **±96** -- so the long-standing "blocked on RE'ing the real E4B/K2000 LFO->Volume cord-destination byte" (see the 2026-07-28 entry below) is half unblocked. **The scale was not derivable and guessing it would have failed silently:** `F2 RES KeyTrk`, two pages over on the same panel, is 0.02 dB/unit -- 50x finer -- so an extrapolated tremolo would have been inaudible rather than visibly wrong. **Still blocked on two things, one per side.** (a) WRITE: the swing DIRECTION is unmeasured -- if the modulated peak rises above the un-modulated level the depth costs headroom and can clip a zone near full scale; if it only ducks down it costs none. `lfo_volume_depth_to_amount`'s docstring asserted the downward reading from 2026-07-28 to 2026-09-01 with nothing behind it; the claim is now retracted in the source and the question is out to k2kremote (K2000) and s3ked (AKAI) together, since the two boxes already disagree about velocity pivots and may disagree here too. (b) A LATENT COUPLING that must be fixed BEFORE anyone measures EOS: `LFO_VOLUME_FULL_DB = 24.0` is documented as an EOS-specific full-scale but is used by `lfo_volume_depth_to_amount` as the model's universal dB<->amount convention, so editing it to a measured EOS value would silently change the depth of every SFZ and SF2 tremolo on every target. Split it into a format constant and a model convention first, then change the format one. **AKAI read side: asked of s3ked 2026-09-01** -- whether an LFO1->LEVEL destination exists at all on the S3000XL, and its byte(s) and dB/unit; if it does not, the gap is real for E4B/KRZ only, as this row's first version guessed. **BOTH HARDWARE READS ARE NOW DONE (2026-09-01).** KRZ reads LFO1/LFO2 -> volume from the F4 segment; AKAI reads LFO1 -> loudness from the mod matrix, gated on the MODSAMP source byte and scaled by the measured PRODUCT law `0.010068 * LFODEP * amount` (§AKAILFOAMP). **The corpus check found a defect the law did not:** `LFO_VOLUME_MODEL_FULL_DB` was 24.0 and 6 of the 25 real AKAI keygroups that use tremolo exceed it -- the deepest, 49.84 dB, was being truncated to 24 -- so the model's 'arbitrary unit' was a ceiling below the material. Raised to 96.0 (the K2000's own rail), which is safe only because the EOS/model split above was done first. **Still open: the WRITE side on both formats**, for two different reasons. KRZ: Depth is bipolar, so writing D dB costs the full D dB of headroom and clips a zone near full scale -- a budgeting decision on real material, not a byte. AKAI: the K2000 has no second multiplier, so AKAI->KRZ must collapse `LFODEP x amount` into one number, which is not invertible AND not neutral -- `LFODEP` is program-wide and also drives the pitch LFO, so normalising it rescales the VIBRATO while normalising the amount rescales the TREMOLO, and on a patch using both there is no single correct collapse. |
| **`velocity_to_filter_min_cents` -- the FLOORED sweep -- is dropped by the E4B and EIII writers** | *(2026-09-01, same audit)* Consumed by the AKAI and KRZ writers only. A source that moves its filter corner even at velocity zero (the shape §AKAICHOKEFILTER exists for, and which the reference preset has) converts to E4B/EIII with the floor discarded, so its resting corner is wrong. The AKAI and KRZ paths both had to solve this; the other two have not been looked at. |
| **The EIII reader populates NONE of the DSP fields** | *(2026-09-01, same audit)* Zero hits for `filter_keytrack`, `velocity_to_filter_cents`, `lfo1_to_pitch`, `coarse_tune` or `release_rate_db_per_s` in `eiii_parser`. So EIII->anything is currently geometry-and-samples only: every filter, envelope-rate and modulation routing the source carries is dropped. Largest of the five gaps by field count, though its payoff depends on how much EIII material is actually converted. |
| **IDEA, blocked on a measurement: model per-key DSP on the K2000 with `F2 RES KeyTrk` / a FUN, so fusion stops being lossy** | *(2026-09-01, §KRZRESKEYTRK, Jan's idea after hearing the over-fusion)* The `F2 RES` page carries its own **`KeyTrk: 0.00dB/key`**, so a monotonic resonance-vs-key needs no FUN at all -- and our writer never touches the field, inheriting 0 from `_TPL_LAYER`. `KeyNum` is also an explicit FUN input and `F2 RES` exposes `Src1`/`Depth`, so a FUN can drive resonance; **the reference preset's own non-monotonic shape is reachable** via `|a-b|` with `a=KeyNum` (a V, inverted by negative Depth into a peak). **Limits:** one KeyTrk and a few FUNs per layer, so a fused layer gets ONE shaped curve per DSP parameter -- a line or one bump, not arbitrary per-zone values -- and the equation set has no min/max, quantise or piecewise, so no true step function. **Why it matters:** not to reproduce the reference preset (v15 already gets that exact by fusing less) but to **raise the ceiling on fusion** -- today merging averages DSP params, which is the defect Jan heard, and a source like preset 6 collapsing 11 voices into 3 pays it heavily. **BLOCKED ON MEASURING THE LAW, Jan's call:** where does `KeyTrk` pivot, is it linear in key AND in setting, what does the displayed dB/key mean, is 0 genuinely neutral. A displayed unit has been read wrong three times on this machine already (§KRZLEVELCURVE, §KRZENVDEPTH2, §KRZLFOPITCH) and a panel field's rails once (keymap `VolumeAdjust` stopping at -63.5, not -64.0). Gate the sweep on HEADROOM as well as the noise floor, and treat any null result as a broken experiment until the manipulation is shown live. |
| **the reference preset's velocity architecture is level + FILTER-ENVELOPE DEPTH + ATTACK RATE, and we carry only the level** | *(2026-09-01, §AKAIVELARCH, s3ked)* Reading every velocity route on the reference preset's kg0/kg1: **`V_ENV2` = +25 on both layers** (velocity scales ENVELOPE 2, the filter envelope -- so the patch gets BRIGHTER with velocity, not merely louder), **`V_ATT1` = -6 on both** (velocity -> envelope-1 attack rate), `VLOUD1` 0/-20 (static level, already carried), `VFREQ1` 0. And the two layers' attacks differ enormously: **`ATTAK1` 5 against 40**. **Neither `V_ENV2` nor `V_ATT1` is read by our parser at all** -- confirmed by grep, the only mention of `V_ATT1` is a passing comment about pivot conventions -- and the model has no field for either (`velocity_to_filter_cents` is VFREQ1, a static corner offset, not an envelope scaling). **So a converted patch with the level exactly right will still not track the original across velocity**, and the difference is a TIMBRE change, not a loudness one. **This also bounds what the §KRZVELOFFSET cross-machine run can show:** a level comparison reads a brightness difference as a level difference, so any residual it finds is partly this. **Blocked on:** measuring `V_ENV2`'s law (and `V_ATT1`'s), then two new model fields, then writers for each target. **PRIORITY REVERSED BY MEASUREMENT 2026-09-01, by the person who first recommended it.** s3ked had put this ahead of everything on the strength of crest factor, then observed that crest shows *that* shape moves and not *what it sounds like*, and measured brightness directly. Against the AKAI, with the mod-matrix velocity->filter route already correctly carried (k2kremote verified 7500/8200 ct to ~45 ct), the centroid difference is **-256 cents at v32 but under 8 cents at every velocity from 64 up** -- inaudible above v64 and inside the run-to-run spread. Total lost centroid swing **248 cents (0.21 octaves)**, essentially all below v64. **The sign is the opposite of expectation:** dropping `V_ENV2` makes the conversion BRIGHTER at low velocity, because `V_ENV2` +25 scales the filter envelope WITH velocity so the AKAI darkens at soft velocities while we stay open -- the audible symptom is **soft notes too bright**, not dull. **So: LOW PRIORITY, behind §KRZSHAREDGAIN** (0.21 octaves below v64, against up to 8 dB of key-dependent level error in shipping output). If built it wants to be an ENVELOPE-SCALING field; a `velocity_to_volume`-shaped one would carry none of it, the level effect being under 0.3 dB above v64. Caveats kept: one patch at one operating point (`V_ENV2` +25, law unmeasured, do not extrapolate), and **v1 excluded as floor-limited -- which is exactly where the effect was still growing**, so the bottom of the range is likely worse than measured. |
| ~~Per-zone gain is averaged across PRESETS into one per-sample byte, so a sample shared at different levels comes out wrong in every preset using it~~ **FIXED 2026-09-01 (§KRZSHAREDGAIN), not yet heard on hardware** -- the K2000 keymap's per-KEY-RANGE `volumeAdjust` (method `0x17`, 6-byte entries, volume byte between tuning and sampleID) now carries each zone's residual on top of the per-sample mean, so a shared sample round-trips every zone exactly. Written **selectively**: v13 used `0x13` on all 15 keymaps, v14 uses `0x17` on the 8 that need it and `0x13` on the rest, so unaffected banks stay byte-identical and the HW-verified unity banks cannot regress. the reference preset's three zones go from -6.461/-0.969/-4.038 dB (up to **8.08 dB too loud**) to -12.00/-5.00/-12.00 against a source of -12.115/-4.846/-12.115 -- residual error now only the field's own 0.5 dB quantisation. Step and rails HW-measured (0.5 dB/click, -63.5..+63.5, so clamp +-127 and never 0x80). `test_sample_gain` had been **pinning the bug**, asserting two zones sharing a sample should both read back as their mean; it now asserts both round-trip exactly. | *(2026-09-01, §KRZSHAREDGAIN, found while checking whether layer fusion loses the AKAI's per-keygroup level offset -- it does not; this does)* The K2000's `Soundfilehead.volumeAdjust` is **per sample**; our `ZoneMapping.volume` is **per zone**. `write_krz` bridges that by taking the MEAN of every zone referencing a sample **across the whole bank, not within a preset**. Its own comment calls the lossy case "rare" because MPC material is 1 zone : 1 sample. **That premise does not hold for AKAI banks, where presets routinely share samples at different levels -- it is not rare, it is the normal case.** Measured on the reference preset, whose samples are shared with preset 5 and preset 4: `sample A` asks -12.115 dB and is written -6.461 (**+5.65 dB too loud**), `sample B` asks -4.846 and is written -0.969 (**+3.88**), `sample C` asks -12.115 and is written -4.038 (**+8.08**). All three are on **L2, the layer that survives the choke**, i.e. most of what a listener hears. The error is not symmetric noise: averaging with louder uses always pulls a quiet zone UP, so the balance between the reference preset's two layers is compressed and its quiet layer is systematically too prominent. **Layer fusion is NOT the cause:** `volume` is deliberately absent from `_VOICE_FIT_FIELDS`, zones are concatenated rather than averaged, and each zone keeps its source value intact right up to this aggregation. **Fix direction (not implemented):** the K2000's AMP `Adjust` is **per layer**, so per-layer gain IS representable and the per-sample byte is currently the only place we use. Carrying the key-span-weighted layer gain in `Adjust` and leaving only the within-layer residual to `volumeAdjust` would make the shared-sample case exact whenever a layer's zones agree. **Blocked on** how to split the two, and on the Adjust knee (linear to +6, knee at +12, clamp from +24) bounding what it can absorb. **Also contaminates §KRZVELOFFSET** -- a level comparison would read this as part of the pivot-asymmetry residual. |
| ~~The AKAI writer HARDCODES velocity->loudness to 20 and the reader never reads it at all~~ **FIXED 2026-09-01 on the AKAI path (§KRZAMPVEL / s3ked §171); K2000 half deliberately still open** -- law measured on a white-noise program with VLOUD1/VFREQ1/V_ATT1 all zeroed (each would otherwise contaminate the reading): **`swing_dB = 1.19557 * V_LOUD`, r2 0.9999816**, the response ROTATING about velocity 64 rather than scaling from silence (level at v64 identical at V_LOUD 0/25/50 -- same pivot `K_FREQ` uses), and **V_LOUD 0 genuinely neutral** (0.00001 dB/unit, r2 0.029). Per end about the pivot that is 0.598 dB/unit, against VLOUD1's 0.60576 and PRLOUD's 0.603 -- all three AKAI loudness fields step ~0.6 dB/unit. **An apparent compressive collapse at the loud end is NOT in the law:** a full-range fit gives r2 0.987 with +-5.5 dB residuals in a W, caused by a ceiling -- tested rather than asserted, since lowering PRLOUD buys headroom and moved the clamp while leaving the slope alone (PRLOUD 80: 20 clean/30 clipped; PRLOUD 60: 40 within 0.4 dB/only 50 clipped; ceiling -25.62 dBFS at both). So the law has no ends and a converter should carry the source's number, not a curve fitted from a clipped sweep. **RE-CHARACTERISED 2026-09-04: it is a GAIN ceiling, not an absolute output one, hence SAMPLE-DEPENDENT** -- two samples froze 5.47 dB apart with the crest factor unmoved, so nothing is clipped and the gain coefficient just stops rising. The -25.62 dBFS figure was one sample's freeze point, not the machine's. No shipped behaviour changes (we only ever use the nominal law), but "how much headroom does the AKAI have" has no single answer per machine, and a new target must match the NOMINAL law rather than a realised range. **Wired:** `AKAI_VLOUD_SWING_DB_PER_UNIT`, new model field `VoiceLayer.velocity_to_volume_db` (a SWING about a pivot, not a slope from silence), reader reads byte 0x1a signed so a negative value survives, writer emits the source's own value and keeps 20 only as the fallback for sources that state nothing. Verified against the real disc: the reference preset 23.91 dB, preset 3 29.89, preset 5 35.87, preset 6 43.04. **K2000 LAW NOW MEASURED (2026-09-01, k2kremote) -- AND IT DOES NOT MATCH THE AKAI'S SHAPE, so mapping the field across unmeasured would have been wrong.** Pivot is **velocity 127, not 64**: the K2000 attenuates downward from full velocity (delta against VelTrk 0 grows monotonically from -34.80 dB at v1 to -0.00 at v127; nothing else is stationary). Linear in velocity (0.27618 dB/unit at VelTrk 35, r2 0.999996) AND linear in setting, with the displayed dB being the full v1..v127 swing already -- measured 34.79 dB at VelTrk 35, and 1:1 across ten settings 0-48 (max deviation **0.21 dB**, r2 0.9999928), so the byte is simply `round(swing_dB)` and needs no table. VelTrk 0 is neutral and means FULL level; the field only ever attenuates. Ceiling, chain-independent parts only: **38.2 dB of usable range below the clamp**, linear 1:1 to Adjust +6, knee at +12, hard clamp from +24 (k2kremote correctly flagged their absolute dBFS clamp figure as folding in their own capture-chain gain and NOT comparable to s3ked's -25.6 dBFS). **THE BLOCKER IS NOW THE PIVOT ASYMMETRY, NOT THE LAW.** For a given swing both machines share the same per-unit slope, so their response lines are PARALLEL -- and with the AKAI referencing nominal at v64 and the K2000 at v127, our conversion would sit **half the swing below the AKAI at EVERY velocity**, uniformly (~12 dB for the reference preset). Writing the source swing would still be strictly better than the inherited 35 (the swing becomes correct, and the deficit becomes a flat ~12.0 dB instead of today's velocity-dependent 23.05 at v1 falling to 11.96 at v127) -- an earlier claim of mine that it would be "the worst option" was wrong and is retracted. Full compensation would want Adjust 6->18 dB, past the knee, where ~4.6 of the 12 dB does not arrive and the top of the range distorts. **Jan's call 2026-09-01: HOLD AND MEASURE rather than compensate on algebra.** Nothing is written to VelTrk yet, not even the swing. The ~12 dB follows only IF the K2000's "full level" corresponds to the AKAI's "nominal level" *in our actual conversion* -- our converter derives K2000 level from the AKAI's own volume fields and whether that alignment holds is unverified; the real deficit could be larger, smaller or absent. **Blocked on:** a chain-independent comparison of what the two machines actually PRODUCE for the same content at the same note and velocity -- each side measuring its subject against its OWN reference through an identical path and reporting subject-minus-reference, so the ratios compare without needing one physical chain or matched trims. Requested jointly of k2kremote and s3ked, with the choice of a reference that means the same thing on both machines left to them as the genuinely hard part. **SUPERSEDED 2026-09-04 (§VELPIVOT) -- the comparison is no longer a blocker, because the fix does not depend on the answer.** The pivot error is `S*(P_dst-P_src)/126`, constant in velocity, and the repair is a static level; shifting the whole PRESET down by its largest offset makes the correction fit without knowing how the two machines' absolute levels line up, since only the RELATIVE balance inside a preset is claimed. If the alignment question is ever answered it changes the preset's overall loudness -- a knob -- and nothing else. The joint measurement would still be worth having; it is no longer on the critical path. *(original:* | *(2026-09-01, §KRZAMPVEL's AKAI half, found chasing the K2000 template question)* Program byte **0x1a is "velocity > loudness"**, the AKAI's own velocity-to-amplitude sensitivity. `writers/akai_s3000_writer.py` writes `p[0x1a] = 20` unconditionally, and `parsers/akai_s3000_parser.py` never reads offset 0x1a at any point -- so the value is **discarded on read and invented on write**. **It is real, varying content, not a constant that could be ignored:** across the six MXS3 programs alone it takes four distinct values -- preset 1 20, the reference preset 20, preset 3 25, preset 4 25, preset 5 30, preset 6 36. So an AKAI->AKAI round trip silently flattens every program's dynamic response to 20, and any other source's velocity sensitivity is lost entirely. (the reference preset happens to be 20 already, which is why tonight's subject showed nothing.) Same family of defect as §AKAIZONELOUD, §AKAITUNEREAD and §AKAIAMPENV -- a field read as nothing and written as a fixed default -- and the third such found on this path. **Blocked on** the same measurement as §KRZAMPVEL: the law for `0x1a -> dB of velocity swing`, requested from s3ked, plus whether the response is linear in dB across velocity or a curve. Fix sequence once measured: model field -> AKAI writer honours the source instead of 20 -> KRZ writer honours it instead of #199's inherited 35 dB. **Measure first** -- replacing one unmeasured constant with another would not be an improvement.*)* |
| **`_TPL_GLOBAL` omits 24 bytes that ROM #199 carries between PGM and FX -- probably four zero-bodied segments, not confirmed** | *(2026-09-01, same audit)* Between PGM (ends @16) and FX (starts @40) ROM #199 has 24 bytes our template does not contain: `11 00 00 00 00 00 00 00 19 00 00 00 15 00 00 00 00 00 00 00 1b 00 00 00`. The non-zero bytes are tags **0x11, 0x19, 0x15, 0x1B** at offsets 16/24/28/36 -- ASR2, FUN2, LFO2, FUN4, i.e. the "second" of each paired module, each with an all-zero body, and the lengths line up with the template's own lengths for those tags. **Explicitly NOT confirmed**, and k2kremote flagged the ambiguity rather than asserting it: apart from the four tag bytes the region is entirely zeros, so "four zero-bodied segments" cannot be distinguished from "24 bytes of padding that happen to contain those values". What argues for segments is that the tags are real, non-zero and in a coherent 2-variant order. **Probably harmless either way:** our writer omits them and the K2000 accepts our objects, which it demonstrably does, so they look optional. Worth resolving only if an object is ever rejected or a paired module (ASR2/FUN2/LFO2/FUN4) needs writing. |
| ~~The fold branch's floor can itself be below the K2000's own 16 Hz byte floor, and nothing compensated the depth when it clamped~~ **FIXED 2026-08-31 (§AKAICHOKEFILTER)** | *(found chasing the reference preset's remaining ~24% brightness gap after §KRZENVLOOP/§AKAICHOKECURVE)* The fold branch above (0 of 1383 corpus routings, real on the reference preset's Layer 1: base 96 Hz, +/-4390 ct swing) computes a floored resting corner via `hz * 2**(vel_min_ct/1200)` -- for Layer 1, 7.6 Hz. `_cutoff_byte_hz` correctly clamps the WRITTEN byte up to the K2000's own 16.35 Hz floor when a source asks for something the hardware genuinely cannot represent -- unavoidable. But until now nothing adjusted the velocity DEPTH to match: it stayed computed against the un-clamped 7.6 Hz floor, so the TOP of the sweep also came out brighter than intended, by the same 1.1 octaves the floor got compressed -- avoidable, not a hardware limit, just an uncompensated side effect. Layer 1's true ceiling (96 Hz * 2^(4390/1200) ~= 1210 Hz) was written as ~2.6 kHz. **Fixed:** when the floored corner falls below the K2000's own representable minimum, the lost headroom (in cents) is subtracted from the velocity depth before encoding, so the ceiling lands back near the source's true value regardless of where the floor had to clamp. Test added (`test_velocity_floor_fold_compensates_when_the_floor_clamps`), confirmed to fail on revert. **Not yet HW re-confirmed** -- rebuild (v9) done, awaiting transfer/listen. |
| **Zone loudness is clamped at +20 on a corpus claim the wider corpus contradicts** | *(2026-08-25, full corpus sweep)* The clamp's own comment says *"real sources sit far below it: the corpus spans -12.5..+2.5 dB, about -21..+4 units"*. The library discs carry zone loudness **50**, and it is flattened to 20 on ~1% of zones (`MILD VIBRA.P3: 50 -> 20`, `HARPSICHRD B.P3: 50 -> 20`). **The clamp may still be right** -- it was set because the usable top moves with PRLOUD, so writing +50 looks like gain and delivers none -- **but the evidence cited for it is now known to be a small-corpus claim.** Re-measure the ceiling, or restate the reason without the corpus argument. |
| **THE CAPTURE GAIN MUST NOT BE TOUCHED -- 68 MB of irreplaceable recordings depend on it** | *(2026-08-25)* `~/temp/e4xt_ref/preerase/` (18 files) and `ab/` (9) are the only recording of the pre-fix E4XT state, and one set -- the `pc36_` prefix -- captures the conversion with five of six voices bound to **another bank's samples**. That state needed two banks resident whose name collision has since been removed, **so it cannot be recreated even by reloading the old file.** It is the only record of what Jan's "release is too short" verdict was actually describing. **The audio interface gain has been untouched since 2026-08-24 17:00 and must stay that way**, or nothing captured later compares to any of it. Conditions are written up in `~/temp/e4xt_ref/CAPTURES.md`: velocity 100, hold 3.0 s, 0.5 s pre-roll used as the floor reference, tail 8 s (14-16 in `ab/`), E4XT output pair, no external processing, 10 ms RMS windows. **A recording without the pre-roll cannot be analysed the same way** -- every measurement this week uses the lead-in as its own noise floor. |
| **The E4B filter envelope's span is in the wrong unit -- currently harmless, and here is the signal that means act** | *(2026-08-24, §E4BFENVUNIT)* The writer feeds a signed-percentage level byte to the **amplitude** sustain-byte law, subtracts it from the **amplitude** full span in dB, and drives it with the **amplitude** rate law -- for an envelope the E4XT runs on a **cutoff byte** scale. It lands within **2-3 rate bytes** of the machine's own measured filter law across 30 sustain/release combinations (worst 1.19x in time) because the unit error and a 0.52x prefactor difference nearly cancel. Near-constant offset = **shape right, anchor off**. Also in the same six lines: attack uses the time-alone law, decay and release use the span law. **DELIBERATELY NOT FIXED:** the reference (§43) was measured on a transition UPWARD to target 100 and the release segment was never measured, so correcting a 1.19x error against it risks making it 1.4x. Warning is in the code at the lines that would be edited, not only here. **THE TRIGGER -- act when this happens:** a listening test on a rebuilt bank reports something the amplitude release does not explain. §E4BFENVUNIT's caveat says that residual would *look* like an amplitude error and would not be one. **Then:** eosed measures a downward traversal (add a FEnv->FilFreq cord in RAM to a calibration-bank noise preset, park the envelope so release is the only stage moving, time to a COMPLETION instant not a t10 -- the corner's low end is invisible), and only then does the converter change. |
| **The AKAI filter envelope may not need the §AKAIRELSPAN treatment at all -- establish before deciding** | *(2026-08-24)* The AKAI's env2 stages are fitted as **times** (`a*exp(b*byte)` seconds) while the E4XT's are **rates**. So unlike the amplitude release, matching *seconds* across that pair may be **correct** -- `akai_env2_stage_seconds` already carries the distance. Not started deliberately: the amplitude fix took a whole session to get right precisely because nobody asked what each machine had been metered for before choosing what to preserve. Ask that first here. |
| ~~**AKAI->E4B releases are ~1.8x too fast**~~ **FIXED + HARDWARE-CONFIRMED 2026-08-24** | *(2026-08-24, §AKAIRELSPAN)* **Measured on both sides.** Source is 15.22 dB/s (s3ked) and our own AKAI law agrees at 15.33; the E4XT delivers 27.2-28.6 (eosed, clean load). The reader converts RELSE1 over a 60.07 dB scale, the writer converts back over 97.82 dB. **The decay agrees to 1-7% and only the release is out** -- decay runs peak->sustain, where both machines' level laws agree, while release runs sustain->*silence*, and neither 60.07 nor 97.82 was ever measured. Both are parameter-scale artifacts. **FIXED:** `Envelope.release_rate_db_per_s` carries the rate; `None` on sources that really do specify a duration (MPC/XPM), whose path is unchanged. RELSE1 75 now emits **byte 80** where it emitted 67-71, matching the bench solve of 80.04. **CONFIRMED ON THE MACHINE:** the converted bank measures **15.30 / 14.59 dB/s** against the source's 15.224 (+0.5% / -4.2%, was 87% fast), voices reading Rls1 80 where they read 69, and the audible fall lengthened **1.49-2.03x** at every note inside the +/-11-semitone window where the envelope dominates. **And the old path made the emitted rate depend on the SUSTAIN**, which the AKAI's own law says it does not -- four sustain levels gave four bytes at one RELSE1. That is the sharpest evidence the arithmetic was wrong rather than miscalibrated. Also noted, not fixed: the decay spans diverge 1.38x at SUSTN1 90 and 1.83x at 95. |
| ~~**Our EOS envelope rate law is 18-25% fast**~~ **FIXED 2026-08-24, swept 60-100** | *(2026-08-24, §E4BRATEANCHOR)* We carry `dB/s = 27.9*2**(-(byte-72)/12.3)`. eosed's four fresh hardware points: byte 69 -> 27.36/27.97 measured against our 33.04; byte 80 -> 13.44/14.24 against our 17.78. The **slope** is right (12.3 vs ln2/0.0565 = 12.27) -- it is the anchor, ~3 bytes' worth. Inverting for 15.224 dB/s: eosed's law 79.7, their direct solve 78.1/78.9, ours 82.8. **The smell was already in the file and written off** as *"5%, unexplained and not worth chasing"*. Invisible to our 499 tests because every path uses this law in BOTH directions, so a round trip through our own code cancels it exactly. **Seven hardware points now, bytes 69/80/99.** Refitting our own parameterisation to all of them gives **halving 12.519, 23.882 dB/s at byte 72** and holds every point within **2.3%**; our current 12.3/27.9 is **13-19% fast uniformly**, the signature of a pure anchor error with the slope right all along. Three independent inversions agree the AKAI's release rate lands on **byte 80** (79.79 / 80.13 / 80.04); ours says 82.75. An earlier reading of 78-79 was withdrawn -- the fits ran down to floor+6 dB and the noise floor levered the slope, worst at the slowest byte. **FIXED:** swept on a stationary looped-noise subject, bytes 60/72/88/100 measured at 46.48/23.70/9.67/4.84 against 46.59/23.65/9.58/4.86 -- **every byte to 1%**, and byte 100 is twelve outside the original fit window. Constants are now `1382 x exp(-0.0565 x byte)` with halving and reference DERIVED from those two rather than maintained by hand. Our own 7-point refit was **rejected**: two of its points came from fits standing in the noise floor. |
| **`Preset.program_number` reaches the TOC only -- it does NOT place the preset on the machine** | *(2026-08-24)* `write_e4b` builds each preset body with the **enumerate index** (`_build_preset_body(p, i, ...)`) while the TOC entry gets `midi_prog=p.program_number`. Setting `program_number = 10` on the first preset of a bank therefore writes **body index 0, TOC midi_prog 10** -- the two disagree inside one file, and a bank cannot be asked to place its presets at chosen slots. Found while trying to keep a calibration bank clear of P000 so it could be MERGED onto a machine already holding the preset under test; the change looked applied (the generator printed PC10-15) and was inert where it mattered. **Which field the E4XT honours on load is not known** and is one bank-scan away from being known. **Until it is, do not rely on preset numbering for anything a measurement depends on** -- identify presets by scanning names and verifying a field the machine actually uses (root key), which is what the bench side now does. |
| **E4B sample names can collide with an already-loaded bank, and the E4XT silently rebinds to the old samples** | *(2026-08-24, §E4BNAMEDEDUP)* **Measured, and it invalidated a listening verdict before anyone acted on it.** Merging a revised bank onto a machine holding an older one with the same sample names bound **five of six voices to the OLD samples** — voice→sample came back `24/54/25/22/26/23` merged against `4/1/5/2/6/3` loaded alone, i.e. exactly +20 on five of them. The merge added **one** sample, not sixteen. Not a memory shortage: 121 MB free at the time. The two banks differ in **exactly one bit** (loop-in-release), so a name or name+size matcher matches all sixteen and a content matcher matches none — which leaves index 0 being the lone exception **unexplained**. **Invisible to every check we have:** the preset's parameters are right, the bank on disc is right, only the sound is wrong — and it looked exactly like a converter defect. **Fix:** give written sample names something a previously-loaded bank cannot collide with. Not wired yet — a naming change alters every conversion and wants its own listen. **Also note:** while two banks share sample names, an A/B with both resident may be structurally impossible in either order; capture one side to audio instead. |
| **The AKAI writer ignores `filter_type` entirely, and the IB-304F needs an option** | *(2026-08-24, §AKAIFILT2)* Two things, one live now and one waiting on hardware. **LIVE:** `writers/akai_s3000_writer.py` never looks at `filter_type`, so a 2-pole source and a 4-pole source produce byte-identical AKAI output — the same shape as this week's reader defects, in the other direction. Recommended: keep the CORNER and accept 12 dB/oct less rolloff, because the resonant peak sits at the corner and moving it trades a slope error for a misplaced-resonance error, which is far more audible (§AKAIENV2DEPTH). Say so in the conversion log. **WAITING ON THE BOARD** (ordered 2026-08-17): `--akai-filter-board`, default OFF, never populating FILTER2/TONE/ENV3 when off since s3ked crashed an S3000XL twice exercising that area, and nothing on the wire distinguishes a fitted machine. Two 2-pole sections DO make 24 dB/oct, but two *identical* ones give Linkwitz-Riley (−6 dB at the corner), not Butterworth — a proper 4-pole needs Q 0.5412 and 1.3065 at the same corner. **Measure `FLT2Q`'s law first:** 0.5412 is below `FILQ 0`'s Q of 1.067, so a Butterworth 4-pole may not be reachable at all, which would invalidate the approach. |
| **Eight findings from 2026-08-23 are NOT applied — see §AKAIFIXPLAN2 for the plan** | *(2026-08-23)* The seven reader items are fixed and tested; these are what was found and deliberately left. In order of reach: **(1)** the E4B reader decodes envelope rates without the span the writer encodes with, so they are not inverses and it touches every E4B-sourced conversion (§E4BENVSPAN) — and may be eosed's unexplained ~1.9×; ~~**(2)** KGMUTE is never written~~ — **DONE 2026-08-24**: the golden test already had the mechanism, `no_hw_defaults`, with three existing precedents; the answer was in its docstring; **(3)** the E4B resonance writer is `round(res*127)` on a non-linear field, the same shape as the K2000 depth bug — eosed's measured curve now exists (§E4XTQCAL); **(4)** the FilterEnv depth composes two laws measured on two machines and over-delivers 2.5–6.7×, needing two calibrations and a reformulation in terms of corner positions (§AKAIENV2DEPTH); **(5)** an audit of every fitted law for evaluation outside its calibrated range, three instances found in one evening; **(6)** an AKAI→AKAI round-trip test and a saturation invariant, which between them would have caught most of tonight; **(7)** two parked hardware jobs; **(8)** ~~one commit message 342 commits back that names a vendor~~ — **Jan's call 2026-08-24: leave it.** Not worth rewriting 342 commits for one word in a July message; everything downstream of it is clean. |
| ~~**AKAI reader divides zone tune by 16 instead of 2.56, and never fills `coarse_tune`**~~ | **FIXED 2026-08-23, with tests.**  *(2026-08-23, §AKAITUNEREAD)* **Found from the audio during the listening audit, and HARDWARE-CONFIRMED BY EAR the same evening** — Jan played source against conversion and reported both predicted symptoms unprompted: the conversion sounds significantly lower than the source, and it beats against itself. `parsers/akai_s3000_parser.py:626` writes `fine_tune=(kg['tune'] + z['tune']) // 16`. AKAI tune units are **1/256 semitone**, so cents are `/2.56` — every AKAI-sourced detune arrives at **16% of what the source asked for**. Worse, `fine_tune` is documented ±100 cents and `coarse_tune` (semitones) is never populated, so anything ≥1 semitone saturates. Traced end to end on real files: an octave-stacked EP program's `VTUNO 3072` (+1200 ct) reaches the model as `fine_tune 192` and the written E4B as **98 cents** — an octave layer becomes a semitone layer, which changes the chord rather than detuning it. **The writer was fixed 2026-08-11** and `_akai_tune_units` states the factor is "2.56, NOT 256 and NOT 16" — the read half was missed, so the two are not inverses and no test closes the loop (§KRZENVDEPTH2 with the sign flipped: there they shared an error and were exact inverses; here they disagree and still nothing looks). **Corpus scale:** 22343 programs, 42.2% carry zone tuning; of 258992 zones, 33.0% are tuned, 11.4% by ≥1 semitone, and **14124 are exact octave layers** — the largest non-zero bucket by 4×. **Deliberately not fixed mid-audit**: Jan is comparing material built with the current reader. Fix + a regression test that fails with `//16` restored + an AKAI→AKAI round-trip test, which is the shape that would have caught it on the day the writer was fixed. |
| **AKAI: the service manual caps a volume at 255 samples / 254 programs; we allow 509 of each** | *(2026-08-23, §AKAIOBJCAPS)* Both AKAI spec sheets — the S2000/S3000XL/S3200XL service manual Jan pointed at in the Bibliothek, and independently the S3000XL owner's manual — give `Maximum sample number 255` / `Maximum program number 254`. `bank_splitter.py:160` carries `'akai': (509, 509, 510)`, which is the **volume directory** budget and was never meant to be the resident one — the same gap `_AKAI_OBJECT_POOL` exists to cover. A 300-sample volume passes every check we have and would load **partially**, the quiet failure. **Corpus is consistent but cannot confirm it:** 4253 authored volumes on the local AKAI ISOs top out at 191 samples / 128 programs, so they look identical under either cap — recorded as corroboration only, per §AGREEMENT. **Not tightened unilaterally**, because if 255 is wrong we split banks that would have loaded whole. Needs one volume of 260 tiny samples on the S3000XL; procedure in the section. Note 255 + 254 = 509 exactly, which may mean one budget written twice or nothing at all. **Strengthened the same day by the S1000 manual:** it states its own, *different* pair — 200 samples / 100 programs — and splitting the corpus scan by generation shows the two populations separating at exactly that boundary (S1000: 2803 volumes, max 120 samples / **43** programs; S3000: 1433 volumes, max 191 / **128**). No S1000 volume passes the S1000's stated cap and only S3000 volumes pass it, which is the discrimination the flat scan could not give. Also explains why this never bit: an S1000 volume directory holds **126** entries, so its 200-sample cap is unreachable within one volume — the S3000's 510 is what makes 255 the binding limit. |
| **`build_k2000_disk` names every bank after the VOLUME, so a multi-bank disc is unpickable** | *(2026-08-22)* Filenames come out `PREFIX_01.KRZ`, `PREFIX_02.KRZ` … where the prefix is the first five alnum characters of `volume_label`. On the K2000 you choose a bank **by filename**, so a disc built to compare three conversions offered `MATRI_01/02/03` and there was no way to tell which was which at the panel. The matrix disc was rebuilt by calling `fat16` directly with `FROM_E4/S1/S3.KRZ`. Fix: derive each 8.3 name from that file's own basename (uniquified), falling back to the volume prefix only on a collision. Cheap, and it makes every multi-bank K2000 disc usable rather than just this one. |
| ~~**`convert.py --add-to` hangs silently on a duplicate volume name**~~ **FIXED 2026-09-10.** `on_duplicate='prompt'` called `input()` unconditionally; in a pipeline or script — where `--add-to` mostly runs — that blocks with nobody to answer, or raises EOFError inside a write with the image half-considered. Now checks `stdin.isatty()`, takes the conservative branch, and says why; `EOFError` is caught as well. Regression test relies on pytest's own captured stdin, so it exercises the real path. | With the default `--on-duplicate prompt` and no TTY, the run blocks on stdin with **no output and 0% CPU** — it looked like a slow conversion for 16 minutes on 2026-08-18 before `ps` showed STAT S. `--on-duplicate overwrite` avoids it, but a non-interactive run should not wait forever for input it cannot receive: detect a non-tty stdin and either fail with the reason or print the prompt before blocking. Cheap, and the failure mode is indistinguishable from a hang. |
| **AKAI: a large `--hda` presents as several 60 MB partitions, and only one is visible at a time** | Not a bug — 60 MB is the sampler's partition maximum — but it changes how a disc is MET. A 400 MB image built 2026-08-18 became 7 partitions, and the S3000XL showed only partition A's 6 volumes; the other 5 sat in B and C and looked missing. **The build should say so**: `--hda` prints the volume list as one flat set, which is what a user reads and then contradicts at the front panel. Print the partition each volume lands in, and consider ordering so the volumes a user most wants sit in partition A. |
| ~~AKAI resident P/K/S pool~~ | **ANSWERED 2026-08-14 (s3ked §98), and the converter already models it.** The pool is `STAT.free_blocks`, one shared pool, and **a keygroup costs exactly what a program and a sample cost**: `blocks = programs + keygroups + samples`, ceiling `STAT.max_blocks` = 1006 on a 32 MB S3000XL. Measured exactly (2 programs + 58 keygroups + 62 samples = 122 used) and confirmed in a second setting. Independently corroborated on Jan's machine: a 967-object volume left `free P/K/S: 39`, and 967 + 39 = 1006 to the unit. `bank_splitter.akai_object_count()` has counted programs + keygroups + samples all along, with `--akai-max-objects` defaulting to 1006. **This row described a defect that no longer existed, and on 2026-08-22 I proposed a hardware experiment on the strength of it — for a question I had helped answer. s3ked checked the record before running it. See §STALEREPORT.** |

### Needs the MPC (not the E4XT)

| item | note |
|------|------|
| **MPC 3.x parameter checklist** | ~25 items in `docs/re_procedures/mpc3_xpm_params.md`. The structure is verified; the parameter *scales* are not. A2 is settled, A1/A4 narrowed |
| **XPM envelope-time curve** | **MPC 3 half FIXED 2026-08-03** — measured 1 ms–30 s, `t(v) = 0.001005·e^(10.3022v)` (§MPCENV). **Still open:** the MPC **2.x** curve is unchanged and unverified against 3.x's finding that the encoding differs; Hold/Delay assumed rather than measured |

### Software only — no hardware needed

| item | note |
|------|------|
| ~~KRZ stereo~~ | **done 2026-08-02, hardware-confirmed** — planar layout, second keymap slot and HOB channel routing; header 0 is the left channel. See RESOLUTION_NOTES §KRZSTEREO / §KRZSTEREO2 |
| **Normalised-knob cutoff sources** | **MPC 3 half FIXED 2026-08-03** — knob → Hz measured on hardware (§MPCCUTOFF), parser converts through `hz_to_e4b_cutoff`. **Still open, but re-scoped 2026-08-25 (§CUTOFFHZ):** TAL, MPC1000 (`pgm`), the MPC **2.x** XML path and `gig` no longer pass the raw knob through -- each now calls `nominal_knob_to_hz`, so the value in the model is a frequency and every writer treats it as one. What is still missing is a **measurement**: that helper puts the knob on the E-MU's 57 Hz..20 kHz curve because it is the one curve we have, which is a stated assumption, not a calibration. The four are named at their call sites. The defect that made this urgent (a knob silently meaning a position) is gone; what is left is an accuracy question per source |
| ~~Bank sizing ignores stereo voice cost~~ | **implemented 2026-08-01** — the estimator counts per-note voices and warns; one decision left on whether `--auto-fit` should act on it |
| ~~Corpus scan may count sampler OS files as banks~~ | **measured 2026-08-01** — 1118 raw hits are 1017 real banks; 100 were free-space leftovers, 1 an OS file. Figures corrected |
| ~~`resample_to_rate` aliased badly~~ | **fixed 2026-08-02** — 2-pole prefilter + linear interpolation aliased at −5.3 dB; windowed sinc now −89 dB. Ran by default on the KRZ path. Also fixed stereo channel bleed + loop-point frame math in the same function |
| **GIG→E4B fine-tune / per-zone volume** | both dropped on the way to the zone entry |
| **AIFF not decoded**, **EXS24 first velocity layer only**, **SFZ keyswitches / overlapping regions**, **XPM slice playback** | parser feature gaps |
| ~~Non-PCM WAV format codes rejected~~ | **fixed 2026-08-02** — own RIFF walk replaces stdlib `wave`; 32-bit/64-bit float and `WAVE_FORMAT_EXTENSIBLE` now read, Ogg-in-WAV refused cleanly. Also recovered tails that `wave` silently truncated. See §WAVFMT |
| ~~FLAC as a sample input~~ | **declined 2026-08-02** — needs a decoder dependency, and mpc2emu stays small and self-contained. No sample container mpc2emu reads embeds FLAC; folder input can be converted by the user beforehand. Do not re-raise. See §WAVFMT "FLAC" |
| **AKAI filter ENVELOPE is still fixed** (cutoff and amp envelope are not) | **Corrected 2026-08-14 — this row overstated the gap and was left stale by the work that closed most of it.** It used to say the writer hardcodes `FILFRQ 99` and every envelope, discarding the source preset's cutoff and envelope entirely. That is no longer true on two counts of three: `_keygroup` now writes `FILFRQ` from `voice.filter_cutoff` through `akai_filter_byte()` (the law re-derived from the resonance peak), and the amp envelope from `voice.amp_env` through `akai_env_bytes()`. What remains fixed is **envelope 2, the filter envelope**, and deliberately: s3ked measured envelope 1 only, and applying envelope 1's laws to envelope 2 would be an assumption wearing a measurement's clothes. Our model does carry a filter envelope, so wiring it is a small change the moment envelope 2 is measured. ~~**Blocked on: the additional filter board, which Jan ordered 2026-08-17.** Envelope 2 cannot be measured without it.~~ **FALSE, corrected 2026-08-20.** The IB304F gates the **second filter** — `FLT2GAIN`, `FLT2MODE`, `FLT2Q`, `FIL2FR` and neighbours. It does not gate envelope 2 or envelope 3. Every envelope-2 measurement s3ked has (§58 depth-independence, §67 rate-not-duration, the constants in `scales.py`) was taken **on a machine that has never had the board**, routed to filter 1 — as was §139's filter sweep. Their own §87 records them making this exact error first, flagging fifteen fields as board-dependent on a citation to §19, which is the FILFRQ measurement and never mentions the board: *"an assumption wearing a citation — the most persuasive form a wrong claim can take, because the reference makes it look checked."* Nothing here is blocked on hardware. See §AKAIENV2 for what actually blocks it. **Deliberately parked until the board arrives**; wiring it is a small change once envelope 2 is measured, since the model already carries a filter envelope. Found 2026-08-08, corrected 2026-08-14, re-scoped 2026-08-17 |
| ~~EIII name fields~~ / **SF2 / MPC60 still decode as ASCII** | **EIII settled 2026-08-08: leave it ASCII.** VinSamLib walked 1 019 EIII/ESI banks out of its EMU3 images — 30 935 sample names, 19 423 preset names — and found 6 banks holding any byte above 0x7E, none of them plausible text (high bytes interleaved with control characters throughout, consistent with deleted-bank content in free space). No evidence the charset is used, so no unverified byte gets pushed at hardware. Same verdict as KRZ, now on the same kind of evidence. The E4B and EMU3 halves were **fixed 2026-08-08** (§NAMEBYTE) — a real E4XT writes bytes above 0x7E into a name field and `errors='replace'` destroyed them on read. The same `ascii`/`replace` pair still sits in `sf2_parser` (6 sites) and `mpc60_parser` (3). SF2 is spec'd ASCII and may be right as it stands. **Blocked on:** a corpus to measure each against. Decide per format, do not blanket-replace — the EIII answer shows why: the E-MU-lineage prior said it probably wanted latin-1, and a thousand real banks said otherwise |
| ~~**E4B attack rate runs 1.84x slow; reader and writer were not inverses on it**~~ **FIXED 2026-09-07, and CONFIRMED END TO END ON HARDWARE the same evening: a bank built with the corrected direction reads `Atk1 rate 91` off the machine (exactly the derived byte) and plays at t_peak ~11.6 s against the source's 11.40 s, where the old build was -11%.** | `env_seconds_to_rate()` asks for an attack time and the E4XT reaches full level **1.838x later** -- eight-point ladder over the Atk1 rate byte, rise from audio, hold and window scaled per point, `t_peak/intended = 1.838 sd 0.050` above 2 s. **A scalar is valid for ATTACK ONLY**: the byte is a slew rate (§ENVSPAN) so one constant corrects it only where the span is fixed, and attack alone always travels 0->100. Decay (100->sustain) and release (sustain->0) stay **blocked** on the sustain-level sweep. Reader corrected in the same change -- correcting only the writer makes them non-inverses and an E4B->E4B round trip would shrink every attack 1.84x per pass; verified stable at 11.268 s across a round trip. **`amp_env.attack` changed meaning**: it now denotes the time the MACHINE takes, not the time the rate law asks for -- so this was never only an E4B-target bug, E4B->AKAI and E4B->KRZ inherited the short attack too. Note this and the MPC law error were **partly cancelling** (~2x short read against 1.84x long write), which is why the shipped result looked only ~30% off; fixing either alone made it worse. See §E4BATKRATE. |
| **The AKAI `ATTAK1` law predicts a captured level 2x wrong** | *(2026-09-07)* §141's law maps `ATTAK1` -> t90 and was fitted from values read off the machine's own display, not from captured audio. Using it to predict how much level a probe MISSES partway up the ramp fails by a factor of two on the only case with ground truth: for `ATTAK1` 99 it predicts a hold-2 -> hold-12 gain of **+7.29 dB** and s3ked measured **+14.90 dB**. So the attack is not a single exponential, or `t90` is not the right handle on it. **Same shape as the MPC envelope law fixed earlier the same day** -- a curve validated against a firmware DISPLAY and never against audio on the segment that mattered (§MPCENV, §ATTACKTRUNCATION). **Status:** open. **Consequence:** any level comparison between two builds whose `ATTAK1` differs contains an artefact of unstated size -- MX10 program 0 is 94 against MX14's 99, so that pair is affected. **MEASURED 2026-09-07, both arms, both holds -- and the factor of two is now CONSISTENT rather than isolated:**

    ATTAK1 94   hold 2 -43.30   hold 12 -32.30   gain +11.00 dB   law predicts +4.21
    ATTAK1 99   hold 2 -48.25   hold 12 -33.35   gain +14.90 dB   law predicts +7.29

**Two audio points, both ~2x above the law.** A consistent factor across two different `ATTAK1` values is a systematic error, not noise -- which is exactly the shape that invites a fudge factor. **DO NOT FIT ONE**: two points cannot distinguish a wrong exponent from a wrong handle, and §141's `t90` may simply not be the quantity a probe integrates. **The artefact itself is now measured rather than modelled: +3.90 dB**, so the two arms differ by 1.05 dB on the plateau where they appeared to differ by 4.95 at the default hold. **Blocked on:** a proper sweep if the law is ever needed for prediction rather than for ordering. |
| ~~**MPC envelope curve selected by container format, not by playing firmware**~~ **FIXED 2026-09-07, hardware-measured** | *(`parsers/xpm_parser.py`)* The envelope law was chosen by `is_mpc3_xpm()`, which tests whether the .xpm is gzip+JSON (3.x) or XML (2.x). **But 3.x firmware loads and plays XML programs and times them with ITS curve**, so every XML program played on a 3.x machine converted with envelope times roughly HALF what the instrument produces. Measured on an MPC One running 3.9.1.2 playing an XML program -- `XPM_VOL_ATTACK`, nine keygroups sweeping `VolumeAttack` 0..1, 35 s hold, rise measured from audio: **measured/law = 0.704, sd 0.005 across four decades**, within 0.4% of the 3.x curve for v>=0.75. That is also the **first acoustic confirmation of the curve's ATTACK segment** -- §MPCENV fitted it from decay values read off the firmware's *display* and verified it acoustically on a decay only, recording attack as "read at 32 clicks". Fix: law now follows `MPC_ENV_FIRMWARE` (default 3), not the container. Regression test asserts it and fails with the default reverted. |
| **KRZ->X: a ~30 dB voice trim is written to ONE sample family and not the other, on every target** | *(2026-09-07, this session, from the re-measurement)* Converting one 12-preset KRZ source, every preset of the organ-type family gets voice volume **0.0 dB** while every preset of the other family gets **-29.6 or -32.5 dB**. Measured against the source on two independent targets the families separate by **+16.8 dB (E4XT)** and **+10.4 dB (AKAI)** -- same direction, no overlap at all on the E4XT (one family +5.5..+11.8, the other -10.3..-5.5). Two different writers showing the same family-dependent split points UPSTREAM of both, i.e. at the KRZ read path, not at either writer. **ROOT-CAUSED 2026-09-07, same day, and it is ours.** The build log names it: *"the velocity-pivot trim puts N level(s) up to 8.3-11.4 dB below the measured volume floor (-22.9 dB). Written by extrapolation -- monotonic, but not a measured dB."* Six such lines, one per affected preset, none for any organ. -22.9 less 8.3..11.4 lands at -31.2..-34.3, i.e. the values written. **The split is by VELOCITY LAYERS, not by family** -- in this bank the two coincide. The source was read off the panel and carries the OPPOSITE intent: organs at OUTPUT Gain 0 dB / AMP Adjust -4..-7, the other family at Gain **12 dB** / Adjust -2..+6, no overlap, i.e. the source favours them by ~+22 dB and we write them down by ~30. The reader is NOT the cause -- parsing the source gives zone volumes of 0.0. **RETRACTION, same day: only ONE defect, and the trim is not it.** This row first named the velocity-pivot trim as the first of two causes. It had **already been refuted on hardware** in the row *"KRZ->E4B: a 12-string renders 40 dB below a B3 organ"* -- the quadratic holds to byte -60 at +/-0.5 dB (so -22.9 is a conservative LABEL, not a boundary) and the trim cancels to **-0.33 dB** measured P000 against itself. The build log's six INFO lines matched the affected family 6/6, which is what a CORRECTLY applied trim looks like: **a log line naming a mechanism as it fires shows the mechanism RAN, never that it caused the outcome.** **The one real defect:** the reader takes zone volume from `Soundfilehead.volumeAdjust` -- the SAMPLE's gain -- and never reads the program's OUTPUT Gain / AMP Adjust at all, so a deliberate program-level boost is dropped. k2kremote's panel read supplies the missing evidence the older row was blocked on: organs at OUTPUT Gain 0 dB / AMP Adjust -4..-7, the other family at Gain **12 dB** / Adjust -2..+6, i.e. ~+22 dB of the **~25 dB that row lists as unattributed**. **Status:** open, fix not written. **Blocked on:** the byte offsets of those two fields, which a parameter-edit + program-dump diff on the K2000 settles. See §KRZFAMILYTRIM. |
| **E4B velocity windows that all end at 127 lose their layering through KRZ** | An E4B preset layering "in from velocity X" writes windows like `(0,127) (1,127) (9,127) (50,127) (86,127)` — every pair OVERLAPS, so `_voices_stacked` correctly calls it a unison stack and the 3-layer cap applies: 3 layers stay in the main preset and the rest go to an orphan preset. Nothing is lost (all samples remain reachable) but the dynamic layering is, and two of the three survivors quantise to the same `ppp` mark, so the bank reads back with **2** distinct windows from 5. Not a bug — `_voices_stacked`'s note records that a stricter test flipped 7 melodic patches to drum-channel-only — but it is the shape where the cap costs most, and it was not written down. **Blocked on:** a K2000R audition of the same preset rendered as a drum program, to judge which is worse. Raised by VinSamLib 2026-08-09. **NOT resolved by §KRZVELSPLIT below** -- that fix only reaches `_fit_layers`'s branch (velocity bands that are mutually DISJOINT, `_voices_stacked`==False); this case's cascading `(x,127)` windows mutually overlap in velocity too, so `_voices_stacked`==True and it still routes to `_spread_pick`'s drop-not-thin behaviour, unchanged. |
| ~~**AKAI->KRZ: velocity-split layers (preset 4, preset 6) become unplayable-except-on-a-drum-channel programs instead of being reduced to 3 layers**~~ **FIXED 2026-08-30, same evening as the hardware finding above (§KRZVELSPLIT)** | *(motivated directly by tonight's K2000R panel finding: preset 4/preset 6, 4-layer velocity stacks, silent except on the drum channel)* `_fit_layers`'s disjoint-only fuse had nothing to do with a pure velocity split (every layer shares the same key range, so no pair is ever disjoint) and fell through to leaving it a >3-layer drum program -- correct for a real drum kit, wrong for an expressive keyboard patch that just wants softer/harder dynamics. Added `_group_overlapping` (union-find on `_spans_disjoint`, since what survives `_fit_layers` can be one or more overlapping clusters, not necessarily one) and `_thin_velocity_voices` (reuses `zone_reducer._thin_and_redistribute`, the same primitive `--reduce-velocity-layers` already uses, so the project has one velocity-reduction implementation, not two) to `writers/krz_writer.py`. Wired in narrowly: only fires when disjoint fusion still leaves more than the 3-layer limit AND every remaining voice belongs to a SINGLE overlapping cluster -- deliberately scoped to avoid the exact mistake `_voices_stacked`'s own note already recorded ("a stricter test... flipped 7 melodic patches to drum-channel-only... too broad to apply unsupervised"), applied to the opposite axis: a real drum kit surviving as several small overlapping clusters (distinct pads) is left as a drum program rather than having its per-pad velocity layers thinned unasked. Verified against both shapes: a synthetic 4-layer velocity stack correctly thins to 3 with velocity ranges redistributed to still cover 0-127; a synthetic 2-pad kit with incompatible filter types (so it can't cross-fuse) correctly stays untouched, 2 separate groups. New test `test_velocity_split_layers_thin_instead_of_becoming_a_drum_program` in `tests/test_krz_writer.py`, confirmed to fail (ImportError) with the fix reverted. Full suite: 507 passed, the two pre-existing `test_citations_resolve.py` failures (a stale docs index, unrelated) confirmed present before this change too. **Not yet hardware-confirmed** -- needs a fresh AKAI->KRZ build of preset 4/preset 6 loaded and listened to on the actual K2000R before this can be marked HW-verified. |

| ~~A partial layer fusion left a hole in the merged voice's keymap, patched by gap-fill with the wrong neighbouring sample -- an unintended doubling where the source only plays one voice~~ **FIXED 2026-08-31 (§AKAILAYERGAP)** | *(found by Jan, listening on the K2000R: "why does Layer 3 only cover one octave?")* the reference preset's own AKAI structure is 6 keygroups in 3 identical-shape choke pairs (24-59/60-71/72-127), which our reader already collapses to 4 voices (1 merged click + 3 disjoint, identically-shaped pad survivors) before `_fit_layers` runs. `_fit_layers`'s single greedy pass fused only the MINIMUM pairs needed to reach the K2000's 3-layer limit -- for these 4 voices, exactly one fusion, picking the two NON-adjacent pads (24-59 and 72-127, closest by continuous-parameter distance) and leaving the middle pad (60-71) standing alone. The fused voice's own keymap now had a real hole at 60-71 (neither of ITS zones covers it), which `_build_keymap_entries`'s mandatory delete-lockup-avoidance gap-fill (HW-confirmed 2026-06-24, a real K2000 hazard, correct and non-negotiable in isolation) patched by extending the 24-59 zone's sample across 60-71 -- the exact range the third, un-fused pad voice ALSO correctly covers with its own sample. Result: two layers sounding together over that one octave, where the AKAI source only ever plays one -- confirmed by Jan hearing that range as fuller/closer to the original than the rest of the keyboard, which is the tell (the accidental doubling was adding back some of the brightness the rest of the conversion was genuinely missing, not a coincidence). **Fixed:** `_fit_layers` now runs in two passes -- PASS 1 closes every ADJACENT (`_spans_adjacent`, touching, no key between them), envelope-matching fusion first, repeatedly, with NO regard for the layer limit, since an adjacent fusion can never create a hole; PASS 2, only if still over the limit afterward, falls back to the old behaviour (closest fusable pair regardless of adjacency) for cases with no gap-free option. the reference preset: 4 voices -> 2 clean layers (click + one fully-merged pad spanning 24-127 with all three original samples in their own correct zones), not 3 lossy ones -- using FEWER of the K2000's available layers, not more, because two of them tile perfectly. New test `test_fit_layers_closes_every_gap_free_fusion_even_past_the_limit`, confirmed to fail (reproduces the old 3-layer/hole shape exactly) with the two-pass logic reverted to one pass. Full suite: 541 passed, same 2 pre-existing citation failures. **Not yet HW-confirmed** -- rebuilt (v10, includes this fix plus the two filter/envelope fixes from earlier tonight) and transferred to the SD card; awaiting reload and listen. |
| ~~GIG: only the first dimension region is read; per-key instruments transpose~~ | **BOTH FIXED 2026-08-09.** A GIG region carries one dimension region per combination of its dimensions, each with its **own sample**; `gig_parser` read `[0]` and stopped, so every velocity layer but one vanished. It now parses `3lnk` and emits one zone per velocity zone: corpus-wide **910 → 1 575 samples, 2 698 → 6 190 zones, 0 → 11 files carrying velocity layers**; a 939 MB concert grand goes 154 → 512 samples with 8 layers per sustain preset. And `PitchTrack` (dimension region's `3ewa` byte 108) is honoured: LinuxSampler skips the whole `(key - UnityNote)` term when it is off, so an untracked zone is written with **root = the key it covers**, since E4B/KRZ/EIII have no unpitched flag. A multi-key untracked zone cannot be represented on any target and warns. Diagnosed by VinSamLib from `gigdump` and LinuxSampler's own `Voice.cpp`/`AbstractVoice.cpp` |
| **Zone reducer not velocity-aware** | `--reduce-key-zones` can leave velocity holes |
| **HDA directory block limited to 16 entries** | guard is applied — `build_hda` drops the excess with a loud `[ERROR]`. §11's "needs hardware RE to confirm the chaining convention" is stale: there is no chaining, the folder entry carries a 7-slot block list |
| ~~EMU3 CD image silently keeps only the first 16 banks~~ | **fixed `7942c61`** — `build_iso` now writes up to `EMU3_BLOCKS_PER_DIR` (7) dir-content blocks, so the limit is the structural `EMU3_MAX_FILES_PER_DIR = 112`, not 16. Past that it is **not silent**: it prints `[ERROR]`, names every dropped file and points at splitting across images or `--hda`, and the truncation happens before the layout is computed so no dead clusters are written. **This row stayed open long after the fix landed**, and on 2026-08-22 I warned eosed off a 20-bank disc on the strength of it; they checked the tree and corrected me. See §STALEREPORT. |
| ~~MPC 3 project with several keygroup programs converts only the first~~ | **fixed 2026-08-03** — `parse_xpm` now builds one preset per keygroup program with a shared sample pool, so an `.xpj` converts like an E4B bank. See §MPC3BANK |
| ~~A drum program converts to nothing~~ | **fixed 2026-08-03** — a drum program now converts as one-key zones whose root equals their key, so each pad plays at native pitch; neither writer needed a new feature. 90 corpus files that produced nothing now yield 956 zones / 907 samples, with the keygroup path byte-for-byte unchanged (970 zones). The MPC 3 `padNoteMap` is honoured (31 of 56 kits use a custom/GM layout); MPC 2.x does not store one, so those fall back to consecutive-from-36 **with a warning**. Sample-free program types (MIDI/Plugin/Audio/CV/Clip — 399 files) now refuse with a clear error instead of returning an empty preset. See §XPMDRUM |
| ~~An MPC 2.x project (`.xpj`) gathered only its keygroup programs~~ | **fixed 2026-08-04** — the 2.x branch now gathers `*.Keygroup.xpm` **and** `*.Drum.xpm`, matching what the MPC 3 path takes, with keygroups first so an already-converting project keeps its preset numbering. 2.x projects converting went 62 → 94 of 97, the 32 drum-only ones no longer refuse, and 2 197 sampled pads the `.xpj` route could not reach are now reachable. Also skips a preset with no sampled content (55 of 224 drum programs are unfilled kits). See §XPMDRUM2X |
| ~~The MPC 3 refusal message still said a drum track cannot convert~~ | **fixed 2026-08-04** — both halves were stale from `27ff6a4` and the 2.x twin had already been reworded in `9a2c78b`, so the two generations contradicted each other. The message now names what the container *does* hold rather than what it lacks ("it holds output, return, submix, type 3, none of which carries sample data"), which matters because VinSamLib shows it verbatim in a greyed row's tooltip. The stale `"N keygroup programs → one bank"` line beside it was wrong the same way and now counts by kind. Program types 3 and 4 stay unnamed — they appear only in MIDI-controller and multi-interface templates and were not pinned down, so they print as `type N` instead of being guessed. Behaviour unchanged: the same 4 files refuse, correctly |
| ~~Truncated-name dedup left two samples sharing one name, silently dropping the second~~ | **fixed 2026-08-04** — `_unique_sample_name` advances against the names actually taken, not a per-base count, so neither failure mode survives (a base already ending in the appended digit, or a rewrite landing on a different real sample). The measured program goes from 57 distinct names for 97 samples — 40 zones sounding a namesake — to 97/97 with 0 unreachable; corpus-wide 0 programs with duplicate names, from 140. `parse_xpm` now also checks after building that names are unique and every zone resolves. Note the proposed guard ("zones ≤ distinct samples") was **not** used: many zones legitimately share a sample, so it would fire on healthy banks. See §XPMNAMES |
| ~~Sample names kept the tail even when the head identifies them~~ | **fixed 2026-08-04** — `_prefers_tail` picks head-vs-tail **per program** from that program's own name set, ties to the tail so today's behaviour survives wherever it worked. A global flip was rejected on the numbers: all-head takes renames from 8 694 to 71 030. Per-program takes them to 5 665, improves 101 programs, and turns the 14-sample Drumulator kit from `Drumulator Clean`/`Clea1`/…/`Cle10` into BD/SD/Clap/Cymbal/CH/OH/… It also composes with §XPMNAMES: the auto-sampled program that collapsed 97→57 under the tail now converts with 0 renames instead of 40. Same pass fixed a false positive in that entry's own invariant, which fired on 11 files whose WAVs are merely missing. See §XPMTRUNC |
| ~~`sampledir_parser` named samples by its own rules~~ | **fixed 2026-08-04** — it now calls the same three helpers as the XPM path. `_prefers_tail` decides head-vs-tail per folder, which matters in both directions: over a 6 710-folder library the tail wins 3 015 folders and the **head still wins 585**, so a global flip would have been wrong too. Forced renames fall **106 382 → 16 740**. `_safe_name` sanitises and counts characters, so `Bäss Ünïcode C3` keeps the `C3` it used to lose to byte-cutting and a literal tab no longer reaches the name field. `_unique_sample_name` cannot outgrow 16 characters — verified on 130 colliding names where the old counter emitted 17. Found via VinSamLib |
| ~~A vintage resample profile destroys an E4B bank of STEREO samples~~ | **fixed 2026-08-07 — and the cause was worse than the symptom.** VinSamLib found that `resample_bank` left stereo PCM a half-frame long and `write_e4b` then declared an `E3S1` chunk two bytes shorter than it wrote, misaligning every later chunk so a 77-sample bank read back as **1 sample with 77 orphaned zones**, silently. Reproduced exactly. The root cause is that **`resample_vintage` never handled stereo at all**: it ran the whole chain — filters, decimation, quantisation — over the *interleaved* buffer, and consecutive samples of an interleaved buffer alternate L,R,L,R. Measured: a pair with **digital silence on the right came back with the right at 16542 against the left's 16590**, i.e. very nearly mono. The half-frame was a side effect of the same mistake. `resample_to_rate` had split channels for exactly this reason; the vintage path never did. Now split per channel with **one shared gain** (normalising each channel independently would move the stereo image of a hard-panned pair), and `_pcm_bytes_written()` makes the E4B chunk size come from the bytes written rather than an upstream buffer. Right-channel bleed now 318 (emulator2) / 10 (emax1) against a left of ~21000 — the quantiser noise floor. Six regression tests, each confirmed to fail with the fix reverted. Found via VinSamLib 2026-08-07 |
| ~~`resample_vintage` raises `NameError: peak` on its non-pooled path~~ | **fixed 2026-08-08.** Exactly as reported: `662dbf8` hoisted the gain calculation above the per-channel loop and renamed `peak` to `_peak`, but the `[3/6] Gain-stage` verbose print still said `peak`. It sits inside `if verbose:`, and `resample_bank` passes `verbose=False` only on the **pool** path — a one-sample bank, `workers=1`, or a one-core machine takes the branch that uses the `verbose=True` default and raises. Reproduced, then fixed. **The tests could not have caught it:** every resampler test called `resample_vintage(verbose=False)` directly or went through the pool, so nothing referenced only inside `if verbose:` was ever executed. A regression test now drives `resample_bank` with a single sample and asserts the verbose output appears — confirmed to fail with the rename reverted. Found via VinSamLib 2026-08-08 |
| ~~AKAI keygroup zone 3 is read and written one byte too late~~ | **fixed 2026-08-06 in `debb20f`** — `_ZONE_OFFSETS` is now `(0x22, 0x3a, 0x52, 0x6a)`, verified in the code 2026-08-07. Kept for the reasoning: it was `(0x22, 0x3a, 0x53, 0x6a)` from Ohsaki's spec, whose deltas `0x18/0x19/0x17` are why the comment says the stride is not uniform. **It is uniform, and 0x53 should be 0x52** — 12 name bytes plus a 12-byte record, 0x18 throughout. Measured over 29 372 keygroups on the eight library discs, three independent ways: **(1)** zones fill in order, so slot 3 is populated only when 1 and 2 are — 99.1 % at 0x52, 50.9 % at 0x53; **(2)** zones 1 and 2 end their record with `ff ff ff ff`, and at 0x52 so does slot 3 in 25 842 keygroups, at 0x53 in **none**; **(3)** of the slot-3 zones whose record is coherent at 0x52, **547 of 550 (99.5 %)** name a sample on their own volume, against slot 1's own 88.5 % baseline — at 0x53, **0 of 29 180**, every name carrying a spurious trailing `0`, which is what `0x00` decodes to. Reading there shifts that zone's name *and* every parameter by a byte; `writers/akai_s3000_writer.py` puts the name where the sampler will not look, so any program with 3+ velocity zones is written wrong. Affects both files. Found via VinSamLib 2026-08-05 |
| ~~AKAI pan is read at half width, and the reader disagrees with the writer~~ | **fixed 2026-08-07** — and the finding was bigger than reported. VinSamLib's patch (`0.5 + pan/100`) keeps a **0..1 scale**, but `ZoneMapping.pan` is documented `-1.0 (L) .. +1.0 (R)` centred on **0.0**, which is what `e4xt_pan_byte` and `eiii_writer` use. So the AKAI pair was on the wrong scale entirely: a centred AKAI zone read as 0.5 became **half right** in E4B. Worse on the writer — it subtracted 0.5 before scaling, so every *centred* model zone was written **hard left**; that was masked by `getattr(z,'pan',0.5) or 0.5`, since 0.0 is falsy and got rewritten to 0.5. Removing the falsy default is what exposed it. Now `/50` and `*50` respectively, verified exact round-trip at -1.0/-0.5/0.0/+0.5/+1.0. Corpus re-measured at 54 654 zones (min -50, max +50 but for 2 junk zones). Raised via VinSamLib 2026-08-05 |
| ~~`_pcm_is_signed` false-positives on real hardware data~~ | **fixed 2026-08-07 — the heuristic is gone.** Measured over **21 503 real samples**: it fires on 36 (0.17%), and they are `SQUARE.S3` and `PULSE.S3` — oscillator waveforms whose edges are *meant* to be discontinuous, which is precisely what a continuity test reads as unsigned. The rewrite turned a leading 0 into -32768, the full-scale noise the check existed to prevent. S1000/S3000 PCM is signed and akaiutil converts sign only for S900 *compressed* data, which this reader does not handle, so there is nothing left for the guard to do. Raised via VinSamLib 2026-08-05 |
| ~~An S1000 program block is 0x96, not 0xC0~~ | **fixed 2026-08-06 in `debb20f`** — `S1000_BLOCK_LEN`/`_block_len()` now size by generation, verified in the code 2026-08-07. Kept for the reasoning: `PROGRAM_COMMON_LEN` and `KEYGROUP_LEN` were both `0xC0` unconditionally, but that is the **S3000** shape. The S3000 program is an extension of the S1000 one and "extension" is literal — it appends 42 bytes per block — so an S1000 common block and each of its keygroups are **0x96 (150)**. Measured on the S1000 library disc: **93 of 93** programs satisfy `len(file) == 0x96 + keygroups × 0x96` exactly, and none fits the S3000 shape. With 0xC0, keygroup 0 is looked for at byte 192 of a program whose first keygroup starts at 150, so names read out of the middle of neighbouring fields — `002.5##00.00`, `.0...1` — and only **19.2 %** of that disc's 2 266 zone names resolved to a sample on their own volume. With 0x96: **99.9 %**. The zone offsets inside a keygroup are unchanged (0x22/0x3a/0x52/0x6a, the S3000's extra bytes going after them), confirmed by sliding a 12-byte window over all 1 669 keygroups: 0x22 names a real sample in 1 667 of them and nothing hits anywhere unexpected. Same root cause as the volume-directory fix in `aa8f99c` — the S1000 needs its own shape, not the S3000's. Found via VinSamLib 2026-08-05 |
| ~~`_find_sample` can load a program file as audio~~ | **fixed 2026-08-07** — the stem-matching fallback now requires the extension to name a sample type (`.S3/.S1/.a3s/.s3s/.wav`). Previously a program whose own name matched a wanted sample loaded its own header as PCM and converted to a bank of noise, silently; real, 1 of 5 246 programs on the corpus. Raised via VinSamLib 2026-08-05 |
| ~~A typed AKAI file must not fall through to a header sniff~~ | **fixed 2026-08-07** — `parse_akai_program`/`parse_akai_sample` refuse a file whose extension names a different kind, and `.X/.Q/.D/.T/.CD/.M3` are registered in `PARSERS` so they fail with a reason instead of reaching whatever the caller tries next. An effects file opens with the same block id a program does, which read 90 `.X` files on one disc as 90 phantom programs with key ranges like 200-0. Raised via VinSamLib 2026-08-05 |
| ~~**AKAI S3000 support is cross-verified but not hardware-verified**~~ | **HARDWARE-VERIFIED 2026-08-18.** `VF NEW` — 21 programs and 9 samples produced by our converter — was loaded on the S3000XL and read back off the machine: **velocity 0..127 fully covered on every program, no gaps; every zone's named sample resident, no dangling references; key ranges 24-108 as written.** So this is agreement with Akai's ROM, not only with `akaiutil`'s interpretation. **And a corroboration nobody designed:** the layer counts match the program NAMES — `6-VEL…` reads back 6 layers, `3-VEL…` 3, single-layer names 1. The name is a semantic claim the converter never computed, so the ROM's reading of our bytes agrees with a third party. **Two detector faults were caught before reporting**, both s3ked's: a first pass read only velocity zone 1 per keygroup and would have declared success on a quarter of the zone data, and a coverage check tested keygroups separately and flagged six phantom gaps where the 6-VEL programs split velocity ACROSS two keygroups sharing one key range. **The `akai-s3000xl` branch is unblocked.** |
| ~~AKAI PCM signedness~~ | **settled 2026-08-05: it is SIGNED.** Ohsaki's spec says unsigned; akaiutil copies S3000 PCM straight into a (signed) WAV buffer and converts sign only for S900 *compressed* data, and a sample we wrote as signed came back through akaiutil's exporter **byte-identical**. `_pcm_is_signed()` stays as a guard against odd files rather than a coin flip. §AKAI_S3000_FORMAT |
| ~~AKAI S3000 disk images are not read or written~~ | **done 2026-08-05** — `writers/akai_s3000_image.py` builds partitioned SCSI/ZuluSCSI hard-disk images (`--format akai --hda`) and 800 KB / 1.6 MB AKAI floppies (`--floppy`); `parsers/akai_image_parser.py` reads either, plus disks written by anything else, `--add-to` appends a volume in place; and `.img`/`.hda` dispatch on content. Our images are **byte-identical** to `akaiutil`'s for the same content (whole file, both media) — hashes pinned in `tests/test_akai_image.py`. Still not hardware-verified; see the row above. §AKAI_S3000_FORMAT |
| ~~AKAI CD-ROM (CD3000) images are not written~~ | **done 2026-08-05** — `--format akai --iso` builds a CD3000 disc image (volumes typed `0x07`, three reserved blocks holding the partition's file index), and `--add-to` rebuilds that index so it cannot go stale. **Byte-identical to `akaiutil`'s** `formatharddisk3cd`+`mkvol3cd`+`setcdinfo` output; hash pinned in `tests/test_akai_image.py`. Not ISO 9660 — burned as a raw data image. Still not hardware-verified. §AKAIIMG |
| **AKAI auxiliary file types: `.M3` only, `.D` closed** | Volumes hold `.T` (take list), `.X` (effects), `.D` (drum inputs) and `.M3` (multi); we name and round-trip all four byte-identically. **`.D` is closed as not-worth-reading:** drum inputs are a trigger-to-MIDI interface — `sens`/`trig`/`capture`/`recover`/`on-time`/`V-curve` are analog envelope-detection parameters turning a pad spike into a MIDI note. Nothing we convert is affected and no target has an equivalent, so round-tripping it unchanged is the entire correct behaviour. Its layout was decoded for free from a photo of the page anyway (8 of 9 fields, two of them 0-based; `unit 1/2` explains the two banks of eight). **`.M3` is the one with real value** — the AKAI multi carries program assignments, which conversion currently drops. Machine-authored examples of all four are at `~/temp/akai_resave_results/VOLUME_005/`. §AKAIAUX |
| **MPC60 SET / floppy has no end-to-end coverage** | Every one of the 10 local `.SET` files is a **720K-truncated copy**, and the local MPC60 `.img` floppies contain those same SETs. `parse_mpc60_set` correctly refuses them ("magic byte 0x00, expected 0x02"), so the *intact* path is exercised by nothing — it is the only input format in `tests/release_matrix.py` that fails for want of a fixture rather than for want of code. **Blocked on:** one intact MPC60 SET or a non-truncated floppy image. Noted 2026-08-07. §RELEASE_MATRIX |
| ~~An unexplained test flake, seen twice~~ | **explained 2026-08-07: `/tmp` was full.** The suite needs **~420 MB** of free space on the filesystem behind `tempfile.gettempdir()` (measured peak 416 MB), nearly all of it the AKAI image tests, which build 16 MB images — several must, since their golden hashes are of 16 MB images `akaiutil` produced. `/tmp` here is its own 4.7 GB volume and another project was filling it. Confirmed by capping file size with `ulimit -f`: the failures land on **exactly** the AKAI image tests and nothing else (22-25 under a hard cap; 8-9 when only some writes cross a partially-full boundary, which is what was seen). Failure is a loud `OSError`, so nothing incorrect can pass because of it. **If failures cluster in `test_akai_image.py`, check `df` before reading a diff.** §RELEASE_MATRIX |
| **`c605fab` carries a VinSamLib commit message** | A chained `cd ~/git-repos/mpc2emu && … && git commit` in VinSamLib's tooling carried the working directory into the commit, so a commit intended for that repo landed here: *"Establish matrix A and D from scratch -- and find three real faults"* on a one-line `TODO.md` edit. **The content is legitimate** — it is the resample finding above — but the message describes work done in another repository. VinSamLib asked for a reword; **not done deliberately**, following Jan's decision on the earlier branch-name case that a misleading message is not worth a history rewrite and should be folded into later work. Recorded here so the message is not read as a record of anything done in this repo. VinSamLib has moved to `git -C <path>` so it cannot recur. Noted 2026-08-07 |
| ~~AKAI stereo samples are mixed down to mono~~ | **implemented 2026-08-22.** Default is now source-preserving: a mono source converts to mono, a stereo source to a hard-panned `-L`/`-R` sample pair in ONE keygroup (zone 1 pan -50, zone 2 pan +50, both full velocity) — the layout read off a real S3000 library volume, §AKAISTEREO2. `--mono mix|left|right` forces the old mixdown and now applies to every format alike. Carries its own both-halves check, because §AKAISTEREO measured that a program naming only the left half loads cleanly, raises nothing and plays mono. Costs two of four velocity zones per stereo keygroup and 2x sample memory. Eight regression tests, each confirmed to fail with its own fix reverted; verified end-to-end through `convert.py` on a real stereo bank (13 stereo keygroups, 0 dangling). **HARDWARE-CONFIRMED 2026-08-22** (§AKAISTEREO3): TC9 loaded clean on first try and measured genuinely stereo -- L/R correlation 0.46/0.48 against a `--mono` control at exactly 1.0000 with side content 33 dB down, so the image is real and not rig imbalance. |
| ~~No per-note polyphony warning for AKAI~~ | **answered 2026-08-17 by Jan: 32.** Polyphony is settable per program within a multi and 32 is the maximum there, matching the machine's 32-voice architecture. `akai` added to `_VOICES_PER_NOTE` in `writers/bank_splitter.py`. **Recorded as an architectural ceiling, not a bench measurement** like the E4XT's 32 and the K2000's 24 — but it is the same reasoning that gives krz its 24 (that machine's whole voice budget), and it is an upper bound either way: a program allocated fewer voices in a multi steals SOONER, so this warns late, never early. Verified the path actually fires (silent at 24, warns at 33 and 40) — the corpus produced no warnings at all, which would have hidden a dead code path. |
| **AKAI volume load numbers are always off** | The root-directory entry carries a load number (1–128) that makes a volume loadable by number — the nearest analogue to E4B's `--bank-start` volume prefix. We always write 0 (off). All eight real library discs also leave it off, so there is no observed convention to copy and no evidence it is worth setting. Cosmetic; noted so it is not mistaken for an oversight. Noted 2026-08-05 |
| **AKAI files are written with OS version 17.00 and no tags** | Real library discs carry **16.50** and non-zero tags (`05 11`); we write the S3000 maximum and leave all four tag slots clear. `akaiutil` reads both back identically and nothing is known to depend on either. Listed only so the difference is on record when hardware testing starts. Noted 2026-08-05 |
| ~~AKAI S3000 writer: the `??` regions are still guesses~~ | **ANSWERED 2026-08-17 on the S3000XL.** Jan loaded `RESAVE` with LOAD ENTIRE VOLUME + CLR and saved it back to `VOLUME 005`; the two were byte-diffed. **Our zero-fill is safe.** Of the stamped bytes, **107 of 120** in the program common `??` span and **all 168** in the keygroup spans came back verbatim — nothing rewritten, nothing moved. The only validated field inside that span is the 13-byte modulation-source matrix `0x4c`–`0x58`, where illegal source codes are zeroed: values **0–13 kept, ≥24 cleared**, boundary in 14–23 untested. **Two stamp patterns were necessary** — `offset` alone showed all 13 cleared ('the machine rebuilds this field'), `offset^0x55` alone showed 9 of 13 kept ('it does not care'); only together do they show a value-dependent rule. Not validated: `0x49 B_PTCHD` kept 73 against a documented 0–12, and the filter-2 sources `0x63`–`0x65` kept bogus values (**hypothesis:** no filter board fitted — recheck when Jan's arrives). Two internal pointers are machine-owned and correctly left alone by us: block base `0x01`-`0x02` (relocated, but the `0x0c` stride matches ours exactly) and a per-USED-zone pointer at `zone_base+0x16` where our `0xFFFF` null is resolved to a RAM address. §AKAIRESAVE |
| **MPC 2.x drum kits with a custom pad layout land on the wrong keys** | MPC 2.x XML stores no pad→note map — all 11 520 `<PadNote>` bodies in the corpus are empty, and `ProgramPads-v2.10` holds pad colours, not notes — so a 2.x kit using a GM layout is laid out consecutively from MIDI 36 instead. It warns. **Blocked on:** finding where (or whether) 2.x records it; `_pad_note_map` already reads a populated `<PadNote>` if one ever appears. §XPMDRUM |
| **K2000 drum kits sound the neighbouring hit on the keys between pads** | `krz_writer` must fill keymap holes — a hole locks the K2000 up on Master→Delete — and the fill copies the neighbour's entry verbatim, so gap keys play that hit transposed rather than staying silent. Documented trade-off, not a fault; revisit only if a hardware audition shows it is worse than the lockup risk. §XPMDRUM |
| **Two doc lines name the development branch instead of the feature** | `docs/RESOLUTION_NOTES.md` §XPMGAPS and `docs/re_procedures/mpc3_xpm_params.md` (the hardware-confirmation-plan heading) both identify the work by its throwaway local branch name rather than by what it is. Replace with a plain description — "the reverse / loop-crossfade work" — **folded into the next substantive edit of those sections, not as a commit of its own**: a standalone cleanup commit would put the name into a fresh public commit message and defeat the point. Purely cosmetic, no behaviour. Noted 2026-08-04 |
| **`e4b_parser` does not read a preset's MIDI program number back** | the writer stores it (TOC byte 31, verified) but `parse_e4b` builds `Preset(...)` without `program_number`, so every preset reads back as 0 and an E4B→E4B round trip silently loses the assignment. Cosmetic for conversion, wrong for round-tripping. Found 2026-08-03 |
| ~~XPM `direction` (reverse playback)~~ | **fixed 2026-08-03, HW-CONFIRMED 2026-08-04** — reversal baked into the PCM after slicing, loop points mirrored, byte-exact against a real reversed sample and through both writers. **HW-1 confirms the MPC does the same:** all 10 measured hits move their energy peak later when Direction is set, and the amp envelope stays on the forward time axis. `Direction` lives in Program Edit, is honoured by 3.9, and is not a loop setting. See §XPMREV |
| ~~XPM loop crossfade~~ | **HW-2 answered 2026-08-04 — implementation falsified, crossfade no longer applied.** A program carrying `SliceLoopCrossFadeLength=128` plays with **no blend at all** at the loop seam: residual vs the raw sample 0.02421, vs our rendering 0.03052, vs symmetric 0.02812, with 10× measurement headroom. Cause: the MPC gates its crossfade behind a separate **Tail Length** control (`Off, 100…5000 ms`, field `SliceTailLength` = 0 here), so the frame-length field alone must not trigger a blend. The renderer and tests are kept for when a tail-enabled measurement lands. See §XPMXFADE |
| **XPM `loopFineTune` is ignored** | meaning unknown and `0` in all 69 808 corpus layers, so there is nothing to calibrate against. Warns if a non-zero one ever appears. **Blocked on:** a real file or a hardware test — **HW-3**. §XPMGAPS |
| **XPM `ZonePlay = 2` (random) could map to EOS Crossfade Random** | currently warned and dropped. The EOS 4.0 manual p.320 documents Crossfade Random as *designed* for randomly switching between voices on the same key — a genuine equivalent. Needs realtime crossfade windows plus a cord per voice, so it is writer-side work wanting a hardware audition. `ZonePlay = 0` (cycle) has **no** EOS equivalent and stays dropped. Audition is **HW-5**, on the E4XT not the MPC. §XPMGAPS |
| ~~KRZ per-entry sample assignment~~ | **fixed 2026-08-02** — the K2000 sounds keymap entry `i` at key `i+12`; we wrote `entry[key]`. See §KRZKEYMAP |
| **`_note_of_entry`'s basePitch/cents generality is untested** | it handles arbitrary `base_pitch`/`cents_per_entry`, but nothing in reach varies: **all 1584 keymaps across a 201-file K2000 library are basePitch 0 / 100 cents / 128 keys** (measured for VinSamLib 2026-08-03). So the `i+12` hardware confirmation only ever exercised the degenerate case, and the general formula rests on the arithmetic being obviously right rather than on evidence. Low priority — flagged so nobody mistakes it for corpus-verified |
| ~~`--from-samples` drops samples that share a root note~~ | **fixed 2026-08-02** — a collided group is spread onto consecutive keys, roots moved with them so pitch is unchanged; distinct-root multisamples untouched |

### Decisions / personal actions

| item | note |
|------|------|
| **New `vpar` fields from SysEx hunting** | found and documented; whether to implement is a judgement call |

### Known-unexplained, not worth hunting

| item | note |
|------|------|
| **The ~2 dB gain-dataset anomaly** | key, velocity and transposition all measured flat. Isolated to one early measurement that four later independent runs contradict. Recorded in case it recurs |

---

## AKAI reader may emit phantom files from junk in unallocated directory slots

**Status:** MEASURED 2026-08-14 — exposure is theoretical **in this corpus**,
and the reason it is theoretical is the part that matters. **Open decision:**
whether to add the positive guard below.

`_volume_files` is length-bounded — it walks a fixed entry count over a
fixed-size directory region — which is the right shape and protects us from the
run-past-the-end phantom that a heuristic stop condition produces. The cost is
that we also walk every UNALLOCATED slot, and those are not empty.

VinSamLib measured what is in them across 441 498 slots on 21 discs: **27 544
entries of type 0x00 with a non-zero size**, sizes running to 0xFFFFFF, tail
bytes taking hundreds of distinct values that look like x86 code. Stale bytes
left in directory capacity that was never written.

We skip `ftype == 0x00`, which covers those. The gap is a junk slot whose type
byte happens to land on a real value:

| condition | odds |
|---|---|
| `ftype` is 0x70 / 0x73 (or the S1000 pair) | ~2 in 256 of random bytes |
| `0 < size <= blocksize` | a small stale size, e.g. the 900 seen in their data |
| `start < nblocks` | anywhere inside the volume |

`_chain` does **not** raise when a chain runs off its end — free or reserved
block, it returns the blocks it has. So a one-block chain comes back, we read a
block and truncate to `size`, and the `len(raw) < size` guard never fires
because `size` is under a block. **A phantom file is emitted with garbage
content and nothing reports it.**

A phantom program largely self-destructs: `parse_program_bytes` rejects it and
the caller warns. **A phantom sample does not** — it is raw PCM by definition,
so garbage audio enters the bank as an ordinary sample.

**Do not "fix" this by adding a stop condition.** That trades our failure mode
for the one s3ked spent today retracting, and theirs is worse: a heuristic stop
invents records that are not there AND hides real ones past the first junk
slot. If a guard is wanted it should be a positive test on the entry itself —
a chain that terminates properly, a size consistent with the type, a name that
decodes — not a decision about where the list ends.

### The measurement, and why the answer is not reassuring

VinSamLib ran it over 21 discs, 1843 volumes, 441 498 slots, using a boundary
independent of the emit test (first slot with `type == 0 AND size == 0`):

| past the boundary | count |
|---|---|
| slots | 375 623 |
| with a non-zero type byte | **0** |
| ...and non-zero size | 0 |
| ...and `start < nblocks` (emittable) | 0 |

Set of type values seen past the boundary: **empty**.

**Why: the type byte is the one field the authoring tools reliably clear, and
nothing else is.** The rest of the record is left stale — sizes to 0xFFFFFF,
tails that look like x86 code. Both readers key on precisely the field that
gets cleared, which is why neither has ever emitted a phantom.

**That is a property of the tools that wrote these discs, not of the format.**
A disc written by something that clears the type byte less thoroughly puts any
length-bounded reader straight into the scenario above. Unobserved across 21
discs is not impossible, and the mechanism on our side is intact: `_chain`
still returns a short chain rather than raising, and the truncation guard still
cannot fire for a size under one block.

VinSamLib also measured chain delivery across all 49 984 entries their reader
emits: **0** with a chain too short for the declared size. Same non-raising
`_chain` behaviour as ours; it simply never meets a malformed entry.

### The guard, not yet added

Require a properly terminated chain covering the declared size before emitting.
That makes a phantom impossible rather than merely unobserved, and on their
corpus it changes **0** entries.

Not added here, for a reason worth stating: it is a behaviour change to a
reader, and it cannot be validated on this machine because the AKAI corpus is
not on this disk. VinSamLib reached the same conclusion independently and has
put it to Jan rather than acting. **Do NOT instead add a stop condition** —
that trades this failure mode for the one s3ked spent 2026-08-14 retracting,
and theirs is worse: a heuristic stop invents records that are not there and
hides real ones behind the first junk slot.

### Our corpus figure: CONFIRMED, not inflated

VinSamLib's reader emits **49 984 files across 1843 volumes** over 21 disc
images — our quoted figure exactly, both numbers, and with no entry past the
boundary and none short-chained, it contains no phantoms. The figure stands and
can keep being quoted. (Theirs is 21 images; the separate "375 unnamed files"
figure came from 8.) Raised and answered 2026-08-14.


## AKAI: the resident P/K/S object pool is not modelled — keygroups are counted nowhere

**Status:** open, likely a real fitting gap. **Blocked on:** what the LOAD
page's "free P/K/S" number actually counts.

Jan noticed the S3000XL's LOAD menu carries a row reading `free P/K/S: 1004`,
which reads as a budget over Programs, Keygroups and Samples. We model no such
thing. For AKAI we enforce three ceilings and this is not among them:

| ceiling | value | counts keygroups? |
|---|---|---|
| volume directory entries | 510, samples and programs competing | no |
| keygroups per program | 99, the width of program-common `0x2a` | per program only |
| sample RAM | 32 MB, `(size_bytes - 150) / 2` words | no |

**Keygroups appear in no budget at all**, and they dominate the object count. A
six-program test volume converted from E4B uses 21 directory entries and
contains 112 P/K/S objects, 91 of them keygroups — roughly four keygroups per
file. Filled to our own 509-entry cap at that ratio a volume would carry about
4300 objects. If 1004 is a shared pool it binds more than four times tighter
than the limit we do enforce, and nothing in the pipeline would notice.

The failure mode is the one already documented for the RAM ceiling: an
over-budget load reports once and then behaves normally, leaving programs
resident, selectable and silent.

**Not known, and not to be guessed:**

1. Is `1004` one shared pool, or the first of three figures on one row?
2. What is the total, and does it move with memory fitted?
3. Does a keygroup cost what a program does?

**Cheapest way to settle it:** watch the number while loading two volumes with
deliberately lopsided counts — few programs of many keygroups each, against
many programs of one keygroup. If it falls by the keygroup count, it is shared
and we must count keygroups. Asked of s3ked 2026-08-14; they have the machine.

Do not cap on a guess. An over-tight clamp silently splits banks that would
have loaded, and this project has already recorded that as the worse bug,
because only the loose kind announces itself. Raised 2026-08-14.


## Name fields destroyed a byte a real E4XT wrote — FIXED for E4B + EMU3 (2026-08-08)

**Status: E4B read/write and EMU3 directory entries fixed (`57a909b`,
`149e2b9`). Open for EIII, SF2 and MPC60 — one decision each, not a blanket
replace.** Fix strategy and the measurement: `docs/RESOLUTION_NOTES.md`
§NAMEBYTE.

`_decode_name` read the 16-byte E4B name field as ASCII with
`errors='replace'`, so every byte above 0x7E became U+FFFD before reaching the
`Bank` model — unrecoverable, and written into every bank produced from that
parse. Real hardware-authored content does use those bytes: 0xA5 as a
separator between an articulation label and a note name, 19 times in one local
third-party bank, 413 times across a separately measured 131-bank library.

The writer had to move with the reader, and two more sites one level up: EMU3
directory entries were written ASCII and read back latin-1 a few lines away,
and the ISO 9660 identifier sanitiser let latin-1 *letters* through to a bare
`encode('ascii')` that raises. Reported by VinSamLib; the `rstrip()` detail
and the ISO 9660 crash were found here.

**Still open, blocked on corpora:** `eiii_parser`/`eiii_writer` (symmetric
ASCII today — same E-MU lineage, so it probably wants the same fix, but no
local EIII corpus to measure), `sf2_parser`, `mpc60_parser`. Deliberately not
changed: `krz_writer`'s ASCII encode against `krz_parser`'s latin-1 decode —
zero of 238 local `.KRZ` files carry such a byte in an object name.

## EMU3 CD image silently drops banks past the 16th — FIXED 2026-08-09

`writers/iso_builder.py::build_iso` — the `--iso` output for `--format e4b`
and `--format eiii` — writes exactly **one** dir-content block:

```python
root   = _root_block("Default Folder  ", _DIRCON_START)   # block_list = [11, -1 × 6]
dircon = _dircon_block(file_infos)                        # slices files[:16]
```

`_dircon_block` silently truncates with `files[:EMU3_ENTRIES_PER_BLOCK]`, and
`_folder_entry` records a single dir-content block. Everything else in the
image is built from the **full** file list: cluster allocation, the FAT
chains and the file data all cover every bank. So banks 17+ are physically
present on the disc and occupy space, but no directory entry references them
— the E4XT cannot see or load them. Nothing warns; `build_iso`'s own
per-file console listing prints all of them as if written.

`convert.py:1111` passes every produced bank into one image
(`iso_fn(out_paths, iso_path, bank_name)`), so any library that splits into
more than 16 banks — routine with `--max-bank-size` — hits this.

**Reproduced 2026-08-03** (20 × 200 KB dummy banks): image 10.1 MB, all 20
allocated clusters 1–20, folder `block_list=(11, 65535 × 6)`, 16 entries
readable, `BANK16..BANK19` missing.

The module already knows the real limit —
`EMU3_MAX_FILES_PER_DIR = 112` is defined at line 83 and never used by this
path — and our own `build_emu_hdd` in the same file already writes
multi-block dir content properly (7 blocks per folder, 100 banks per folder,
multiple folders beyond that). Only the CD path was left on the single-block
assumption.

**Status: FIXED 2026-08-09.** The CD path now writes one dir-content block
per 16 banks and lists them in the folder entry's 7-slot block list — the
shape `build_emu_hdd` already writes and our hardware-confirmed HDD images
use. The 2-digit file id runs across the whole folder (`_dircon_block`'s
fallback is the *within-block* index, which past 16 banks would have numbered
each block 00–15 again). Anything past the structural 112 is still dropped,
now with the count named.

**Verified in software:** a 16-bank image is **byte-identical** to the one the
old code produced (sha `836eab0cb89271a7`), so nothing already confirmed on
hardware changed; a 20-bank image lists blocks `[11, 12]` with all 20 banks
referenced, ids 0–19 unique, clusters contiguous; 112 fills all 7 blocks; 113
drops exactly one with the error. Regression test
`test_emu3_cd_directory_spans_blocks`, confirmed to fail with the fix
reverted.

**HW-CONFIRMED 2026-08-10 (E4XT, Jan)** — disc `CD2-DIRCON.iso`, 20 banks,
1-16 in dir-content block 11 and 17-20 in block 12
(`tests/re_banks/gen_emu3_dircon_bank.py`).

- The CD browser lists all 20 banks including `DIRCON20`. Under the old code
  the listing would have stopped at `DIRCON16` — block 12 did not exist. So
  the reader walks the folder's 7-slot block list.
- B16-B19 (the four block-12 banks) load, and sending one MIDI note from an
  MPC One plays a **different pitch on each preset**. That rules out the
  failure a listing cannot show: entries that are listed correctly but all
  resolve to the same data. Each block-12 entry resolves to its own bank.

Together with the software check — 20 distinct start clusters, and the data
at each cluster byte-matching its source bank — the E4XT's CD reader handles
multi-block directories the same way its hardware-confirmed HDD reader does.
**The CD bank limit is the structural 112, not 16.**

**The first version of this test was worthless and the mistake is recorded in
the generator's header.** It gave every sample a `root_note` equal to its own
recorded pitch; a sampler transposes from `root_note`, so the two cancel and
all 20 banks sounded identical at any key. Jan reported exactly that, twice,
which was the correct reading of a broken disc. v2 fixes it by sharing
`root_note = 60` across all banks and varying only the recorded frequency.



Found by cross-referencing ConvertWithMoss `3dbd378f` (2026-08-03), which
extends the same filesystem writer from 16 to 112 files using the identical
7-slot folder block list. Their commit is not hardware-verified.

---

## Cutoff: design frequency vs −3 dB corner — SETTLED, no change needed (2026-08-01)

The concern was that E-mu's spec documents a closed-form cutoff byte → Hz
curve disagreeing with our measured −3 dB corner by up to 3×, and that since
source formats specify a *design* frequency, our calibration might be
systematically low.

**Measured, and the premise was wrong.** The worry assumed the E4XT's 4-pole
lowpass is a cascade of 1-pole sections, where the −3 dB point sits far below
the design frequency. It is not:

| raw byte | −3 dB corner | asymptote slope | extrapolated f₀ | spec T3 |
|---------:|-------------:|----------------:|----------------:|--------:|
| 96 | 554 Hz | −25.0 dB/oct | 567 Hz | 570 Hz |
| 128 | 879 Hz | −23.9 dB/oct | 927 Hz | 1027 Hz |
| 160 | 1244 Hz | −21.3 dB/oct | 1480 Hz | 1833 Hz |

The slope is ~24 dB/oct — a genuine 4-pole — and f₀, obtained by extrapolating
the asymptote back to unity gain (topology-independent), lands within 5–19% of
the −3 dB corner. **The two conventions name almost the same frequency, so the
question dissolves.** Our calibration targets the right quantity and stands
unchanged.

Two secondary results:

- **The spec's tables do not describe this filter well.** T3 (10000, 1006) is
  clearly closest — an exact hit at byte 96 — but drifts to 24% off by byte
  160. T1 and T2 are much further out. So the closed form is *not* the better
  mapping after all, despite covering all 256 bytes.
- **Filter order, not table assignment, explains the per-type differences.**
  The same byte on Low 2/4/6-pole gives 1037 / 872 / 734 Hz — monotonic with
  pole count, which is physics. Three arbitrarily-assigned tables would not
  produce a monotonic progression. (The duplicate 6-pole key measured
  924/924 Hz against its twin, confirming repeatability.)

**Method note.** An earlier attempt to settle this by re-analysing existing
recordings failed: the best table/response-point pairing still varied 39%
across bytes and the slope estimate ranged 10–36 dB/oct. Longer holds and
4× overlap-averaged FFTs fixed it — the slope came back at ~24 dB/oct where it
belongs. The lesson is that the earlier disagreement was measurement
resolution, not a real property.

**Status:** settled. Optionally still worth reading the front panel once at a
known byte: if it displays T3's numbers, the device's own readout over-reads
by up to 24%, which matters when comparing against panel values in future RE.

## Normalised-knob sources violate the `filter_cutoff` contract (OPEN, 2026-08-01)

**This is the one place the E4XT calibration work changed behaviour that had
not been asked about, so it is worth stating plainly.**

The shared internal `filter_cutoff` (0–1) is contractually a **position on the
57 Hz – 20 kHz exponential**, defined by `hz_to_e4b_cutoff`. Parsers that know
their source's cutoff in Hz honour it — `sf2_parser`, `exs24_parser`,
`krz_parser`, `eiii_parser` all call `hz_to_e4b_cutoff(hz)` — and for those the
2026-07-31 correction is unambiguously right: a request in Hz now lands within
a few percent on the E4XT, where it used to be up to an octave and a half dark.

But three parsers assign a **source's own normalised knob** straight into that
field, treating it as "whatever 0–1 the source used":

| parser | line | value |
|--------|------|-------|
| `xpm_parser` | `filt_cutoff` from MPC `<Cutoff>` | MPC's 0–1 control |
| `talsmpl_parser` | `float(prog['filtercutoff'])` | TAL's 0–1 knob |
| `pgm_parser` | `min(1.0, f1_freq / 99.0)` | MPC1000's 0–99 scaled |

That was always a contract violation, but it was **invisible** while the
writer mapped position to byte linearly. Now the writer interprets the
position precisely, so those sources shifted:

| knob | old byte → Hz | new byte → Hz |
|------|---------------|---------------|
| 0.25 | 64 → 301 Hz | 53 → 247 Hz |
| 0.50 | 128 → 760 Hz | 153 → 1068 Hz |
| 0.75 | 191 → 1504 Hz | 237 → **4552 Hz** |

**Neither column is grounded** — the MPC's and TAL's own knob-to-Hz curves have
never been measured, so there is no basis for calling either right. What is
certain is that MPC/TAL/MPC1000-sourced filters now sound different from
before, in a direction nobody verified.

**The fix is a mapping, not a hack:** measure (or find) each source's
knob → Hz curve and convert through `hz_to_e4b_cutoff` like every other
parser. For MPC that is a bench task on the MPC itself and belongs with the
MPC 3.x parameter checklist, which already lists `filterCutoff` scale as item
A3.

**Status:** open. **Blocked on:** the source-side curves. Until then the three
parsers remain uncalibrated — as they always were, just now with a different
wrong answer.

**Update 2026-08-03:** ConvertWithMoss now carries a candidate MPC knob → Hz
curve (a 140-semitone log scale, 32.7 Hz – 106.3 kHz). It is their reading, not
a measurement, and it disagrees sharply with our current numbers at the top of
the range. Recorded with its consequences in `docs/RESOLUTION_NOTES.md`
§CUTOFFKNOB. Does **not** unblock this item — A3 still needs the MPC — but the
bench task is now "confirm or refute this curve" rather than "measure from
scratch". Nothing for TAL or MPC1000.

## Bank sizing does not know a stereo sample costs two voices — IMPLEMENTED, one decision left (2026-08-01)

Measured 2026-07-31: on the E4XT a **stereo sample consumes two voices**, and
there is a **~32-voice limit per NOTE** (global polyphony of 128 is intact —
32 voices on each of four keys all sound).

Neither fact reached the code that reasons about size and fit.
`writers/bank_splitter.py` and `processors/zone_reducer.py` contained no
stereo or voice-count awareness at all, so a preset stacking more than
**16 stereo layers on one key** (or 32 mono) had voices silently stolen on
playback, and nothing warned. That matters more since stereo became the
default: presets that used to be downmixed now carry twice the voice cost.

**Status: implemented 2026-08-01.** `bank_splitter` gained
`sample_voice_cost` / `peak_note_voices` / `polyphony_warnings`, and
`convert.py` prints the warnings alongside the split warnings. Verified end
to end on an 18-layer stereo SFZ: reports 36 voices, and both flags it
suggests (`--mono`, `--reduce-velocity-layers`) do clear it. Covered by
`tests/test_polyphony.py` (21 assertions).

Two things worth knowing about what was *not* wrong:

- **The byte estimate was already correct.** Stereo PCM is naturally twice
  the bytes and `len(sample.data)` counts it, so `--max-preset-size` never
  under-counted *size*. What was missing was voice accounting, which is a
  separate ceiling — a preset can be tiny in bytes and still over budget.
- **Zones inside one voice layer do not stack.** An E4B voice sounds only one
  matching zone per note, so a 155-zone single-layer SFZ import costs one
  voice, not 155. Counting zones would have produced nonsense warnings.

**Left open — a decision, not a gap:** the fit assistant (`--auto-fit`) still
triggers on bytes only, so an over-budget preset that fits by size is warned
about but not auto-thinned. See §POLY in `docs/RESOLUTION_NOTES.md` for the
argument either way; it needs Jan's call, not more measurement.

## Corpus scan counted 101 non-banks — MEASURED AND CORRECTED (2026-08-01)

From ConvertWithMoss `d94bde27`: an E-mu volume's **operating system file**
(`E3 Main Code`, dircon type `0x80`) is a memory dump whose content can itself
begin with an EIII bank identifier. CWM's reader skips type `0x80` for exactly
this reason, and mpc2emu's corpus scan — which searched raw image bytes for the
three identifier strings — could not skip anything.

**Audited by writing the EMU3 filesystem reader the project never had**
(`tests/re_banks/emu3_os_file_audit.py`): parse the superblock for the real
geometry, walk the dir-content blocks for every entry and its type byte, follow
each file's FAT chain for its true extent, then place every identifier hit in
the file that owns those bytes. Reproduces the original scan **exactly** —
1118 raw hits across the 22 volumes — so the two numbers are comparable
directly:

| where the hit lands | count |
|---|---:|
| head of a real, directory-listed bank | **1017** |
| in FAT-**free** space (deleted / leftover data) | 100 |
| inside an OS file (type `0x80`) | 1 |
| embedded in a bank's own data, file slack, allocated-but-unlisted | 0 |

**So the corpus is 1017 banks, not 1118 — 9.0% inflation.** The dominant cause
is *not* the mechanism CWM flagged: that one accounts for a single hit. It is
free-space data the discs' directories no longer reference.

**The read-side validation is not weakened.** All 100 free-space hits were
re-parsed and every one is a structurally valid bank with a sensible name,
presets and samples (1496 presets, 2193 samples between them) — deleted or
left over from mastering, not garbage. So "the parser read 1118 real bank
images with zero failures" remains true and is still the right claim to make
about the *parser*. What was wrong is using that number as a count of
*library banks*, which is 1017.

Two incidental findings worth keeping:

- **The original scan's glob was case-sensitive** and silently skipped five
  `.ISO` volumes. Correcting it is what makes the raw count land on 1118 —
  before that, only 17 of the 22 volumes were read.
- **A coincidence to not be fooled by:** the 22 volumes also hold exactly 1118
  directory entries (1017 EIII banks + 76 E4B banks + 25 OS files). The two
  1118s are unrelated.

**Status: resolved.** Figures corrected in `README.md`, `README_de.md`,
`parsers/eiii_parser.py`, `docs/EIII_FORMAT.md` and §EIII. Method and full
per-volume results in `docs/RESOLUTION_NOTES.md` §OSFILE.


## Combined open-HW-RE bank — SESSION DONE (2026-07-31), 2 presets rebuilt since

**Not a code task — a bench-session vehicle.** One bank + ISO covering every
open hardware-RE item that can be settled on the E4XT, so a single session
closes all of them instead of one per trip.

Built by `tests/re_banks/gen_open_hw_re_bank.py` into
`~/temp/open_hw_re/` — `OPENHWRE_01.E4B` (6.28 MB), `OPENHWRE.iso`, and
`MANIFEST.md` with **31 test points across 6 presets** and empty **Done** /
**Remarks** columns to fill in during the session. Each preset is one open
item; each key is one data point, from C3 upward.

| Preset | Covers |
|--------|--------|
| `P1STIMAGE` | §E4BSTEREO 1–3: does a stereo bank load, play in stereo, and in the right channel order |
| `P2STPAN` | §E4BSTEREO 5: does zone pan balance a stereo image or collapse it |
| `P3STVOICES` | §E4BSTEREO 4: does one stereo sample cost one voice or two |
| `P4ENVTIME` | "XPM envelope-time curve under-reads vs MPC display" — the deferred `_xpm_env_to_seconds` recalibration |
| `P5FLTGAIN` | "SF2 static filter + zone gain/tune — needs hardware A/B" |
| `P6TRIMATK` | "`--trim-start` needs re-verification against SLOW-attack material" — was blocked on material, synthesised here |

**P1 is the priority**: channel order is the only item no amount of offline
work can settle — it rests entirely on emu3bm and the EIII naming the first
PCM block left. Its material is deliberately asymmetric (tone-left-only,
tone-right-only, A4-left/E5-right, plus a pre-summed mono reference), so a
mono-sum, a swapped pair and a one-side-only bug each sound *different* and a
failure names itself rather than just failing.

Verified in software before shipping: the bank re-parses to 6 presets / 11
samples / 31 zones with 5 stereo + 6 mono, and each stereo sample's per-channel
content measures as designed (440 Hz left + silence, silence + 440 Hz right,
440 Hz left + 659 Hz right).

**Status: SESSION DONE 2026-07-31 — 4 of 6 presets answered, 2 need a rebuilt
bank.** Everything was *measured*, not judged by ear: notes driven over MIDI
to the E4XT, audio captured from JACK, analysed offline. The harness is
`tests/re_banks/hw_measure.py` and it is the reusable part of this — the
existing `ENV_RATE`, `MOD_DEPTH_CAL` and `AMP_LEVEL` constants were all fitted
from 4-6 hand-timed points, and this can sweep 128 unattended.

| preset | result |
|--------|--------|
| `P1STIMAGE` | ✅ **Channel order correct**, stereo plays as stereo. See §E4BSTEREO. |
| `P2STPAN` | ✅ **Pan mono-sums a stereo voice** onto the pan position. See §E4BSTEREO. |
| `P4ENVTIME` | ✅ **`env_seconds_to_rate` confirmed** — attack ~20% long, release ~15% short, monotonic across 0.1-5 s. |
| `P5FLTGAIN` | ⚠️ **Zone gain under-delivers** (below). Cutoff/resonance not measurable — see the test-design faults. |
| `P6TRIMATK` | ✅ Reference pair reproduces, and now has a **numeric** acceptance criterion: a genuine slow swell starts at **1.7%** of its peak, the mis-trimmed copy at **50.8%**. |
| `P3STVOICES` | ⏭ **Unanswerable as built** — no polyphony counter on the E4XT (below). |

**Two test-design faults of mine, both worth fixing before the next bank:**

- **`P3STVOICES` cannot work.** It assumed a voice/polyphony readout; the
  E4XT has none, and at 128-voice polyphony you would need 65+ held notes to
  reach the ceiling by hand. Replace with a preset stacking ~40 voices on a
  SINGLE key: one keypress crosses the ceiling and the note count where
  stealing begins gives the stereo-vs-mono ratio directly.
- **`P5FLTGAIN`'s filter source is too band-limited.** A 110 Hz saw with 24
  harmonics runs out of content at 2.6 kHz, so cutoff 0.60 and 1.00 had
  nothing left to filter and no corner could be found; only 0.15 (~330 Hz) and
  0.35 (~550 Hz) were measurable, and the resonance analysis was invalid.
  Use **white noise** instead — energy at every frequency makes the corner
  measurable across the whole range and turns resonance into a clean peak.

Also: `P2STPAN`'s three keys are transposed copies (all three zones carry
`root_key=C3` while sitting on different keys). Harmless there, but it briefly
sent the pan analysis down a wrong path — see the method note in §E4BSTEREO.

**Blocked on:** a rebuilt bank for the two open presets. The SD card is in the
hardware, so that is a next-session item.

## EOS: pan and chorus laws rest on panel evidence, never measured (OPEN, 2026-07-31)

Found by auditing every "hardware-confirmed" claim that concerns a level or
amount, after **two** of them turned out to mean something weaker than they
sounded.

`vpar[55]` **Pan** is documented as *"HARDWARE-CONFIRMED 2026-07-26 via a
7-voice differential save … Pan +63/−64/+32/−32 → `vpar[55]` exactly"*. That
is the same save, and the same reasoning, that carried `vpar[54]` **Volume** —
and volume then measured as under-delivering by up to **6.5 dB**, because the
evidence only ever showed that the front panel displays the byte we write.

So we do not know that pan −64 produces full-left, nor that the law between
the endpoints is linear. `vpar[42]` **Chorus Amount** is the same class of
claim (UI percentage vs byte, verified against saved banks, never played).

**MEASURED 2026-07-31 — pan was wrong, exactly as the audit suspected.**
Sweeping pan and reading the two channels separately shows **full deflection
is reached at byte ±32, not ±64**. Our `pan × 64` mapping therefore threw away
half the range: anything past ±0.5 collapsed to hard-panned, so a preset at
−0.6 sounded identical to one at −1.0. Fixed to `× 32` in writer, parser and
model; the panel really does show ±64, which is precisely why panel agreement
could never have caught this.

### The pan LEVEL law — measured, and now a user choice (2026-08-01)

Panning the E4XT makes it louder: **+2.88 dB at pan 0.5, +4.32 dB at 1.0**,
fitted as `4.54 · |pan|^0.75`. The prerequisite for compensating it is
satisfied — the excess curve is **identical at every volume** (spread
0.00 / 0.00 / 0.21 dB across 0, −6 and −12 dB) and **unchanged by the filter**
(+2.83 / +4.22 half-closed), so one curve does describe it.

**Exposed as `--pan-law {hardware,constant-power}`, defaulting to
`hardware`** — i.e. current behaviour is unchanged unless asked for.

The default is not a preference, it follows from what the correction *is*.
The cutoff and gain fixes correct a **mapping**: the source names a value, the
hardware wasn't delivering it, and parser and writer stay exact inverses, so
they are always-on and round-trip cleanly. Pan compensation is different — it
alters the **material**, subtracting the excess from each voice's volume byte,
where it becomes indistinguishable from a volume the user set deliberately.
The parser cannot undo it, so an E4B→E4B pass would drift further every time.
That puts it with `--mono`, `--resample` and `--trim-start`: opt-in, one-way,
applied in the pipeline rather than in the writer.

`constant-power` is the right choice when source fidelity matters — SFZ and
SF2 assume roughly constant power, so a hard-panned voice otherwise arrives
~4.5 dB hotter than its author intended relative to a centred one. `hardware`
is right when the converted preset should behave like one panned on the front
panel.

E4B only; the law was measured on an E4XT and says nothing about the K2000 or
EIII.

**HARDWARE-VERIFIED 2026-08-01.** Two banks built from one source, differing
only in `--pan-law`:

| pan | `hardware` | `constant-power` |
|-----|-----------|------------------|
| 0.25 | +1.07 dB | −0.40 dB |
| 0.50 | +2.88 dB | −0.36 dB |
| 0.75 | +3.94 dB | −0.28 dB |
| 1.00 | +4.32 dB | −0.47 dB |

Worst deviation from flat: **0.47 dB**, against 4.32 dB uncompensated — a 9×
reduction, and close to the ±0.25 dB predicted from the pan-excess and gain
laws separately. The residual is byte quantisation (volume steps ~0.767 dB).

**Chorus (`vpar[42]`) MEASURED 2026-08-01 — and it is correct.** Amount maps
linearly to detune depth: spectral width 0.45 / 4.55 / 9.09 / 13.64 / 19.09 Hz
at 0 / 25 / 50 / 75 / 100%, with the beat rate tracking it (3.74 / 8.56 /
12.83 / 18.72 Hz). Those are two independent readings of the same physical
quantity — a chorus detuning a copy by Δf produces a beat at Δf and a spread
of ~Δf — so their agreement is what makes the reading trustworthy. The linear
UI-to-byte mapping therefore does produce a linear audible effect. Unlike
volume and pan, this panel-derived claim survived measurement.

**No EOS parameter this project writes now rests on panel evidence alone.**

Caveat recorded in `writers/e4b_writer.py` at the claim itself: panel
agreement is not sufficient evidence for a level or amount law.

## KRZ stereo — DONE, hardware-confirmed (2026-08-02)

Both directions implemented and confirmed on a K2000R. `krz_writer` emits the
planar two-block layout plus the three fields the K2000 needs to play it as
stereo (`LYR[8]` 0x20, the `CAL[7,8]` second keymap slot, and HOB `0x52`/`0x53`
channel routing); `krz_parser` reads both blocks back as interleaved stereo.
Header 0 is the left channel.

Verified on synthetic tones, on converted real audio, and against a negative
control (byte-identical channels come back correlated). Full detail in
`docs/RESOLUTION_NOTES.md` §KRZSTEREO / §KRZSTEREO2 and the measured results in
`docs/re_procedures/krz_stereo.md`.

Voice cost measured 2026-08-02: **a stereo sample costs two voices** (stereo
plateaus at 12 simultaneous notes, mono reaches 24), so
`bank_splitter._VOICES_PER_NOTE` now carries `'krz': 24`.

Pan measured 2026-08-02 (it is on the **Output** page, not the layer page):
the K2000 pan law is **constant power** — hard pan raises the live channel
+3.0 dB with 0.00 dB total-power excess once the rig's own imbalance is
subtracted, against the E4XT's +4.5 dB, so the two cannot share a
`--pan-law`. The RAM byte is decoded: **bits 2..5 of byte 270, 4-bit signed,
-7..+7**. The FILE byte is the **high nibble of HOB `0x53` byte 14** (4-bit signed,
-7..+7), found by saving one program at three pan settings and byte-diffing —
one differing byte in 252, validated over 27k corpus fields. mpc2emu now
writes `ZoneMapping.pan` for mono layers; stereo layers keep the hard -7/+7
split that places their two channels. **KRZ pan is done.**

## E4B per-zone GAIN under-delivers — measured, unfixed (2026-07-31)

`ZoneMapping.volume` is documented as dB, but the E4XT does not produce the
requested attenuation. Measured on the open-HW-RE bank with an identical
source and an open filter across all three zones, so only zone volume varies:

| requested | measured RMS | measured Δ |
|-----------|--------------|------------|
| 0 dB   | 0.02216 | — |
| −6 dB  | 0.01515 | **−3.3 dB** |
| −12 dB | 0.00865 | **−8.2 dB** |

Roughly half to two-thirds of the requested attenuation arrives, and the
ratio is not constant (0.55 then 0.68), so this is a **curve mismatch, not a
scale factor**. Distinct from §E4BLEVEL, which is the amp-envelope sustain
level; this is the per-zone volume byte.

This is the gain half of the "SF2 static filter + zone gain/tune — needs
hardware A/B" item, which can now be considered answered in the negative: the
path reaches the writer, but the value it lands on is wrong.

**Re-measured 2026-07-31 with 13 points** (bank 2, `P_GAIN`): the delivered
fraction climbs from 0.46 at −2 dB to 0.75 at −24 dB, confirming a curve
rather than an offset. Root cause identified: `_zone_entry` / `vpar[54]`
writes the dB value straight in, and the "hardware-confirmed 2026-07-26" note
against `vpar[54]` established only that the **front panel displays** what we
write — never that the audio matches. Same trap as §E4BLEVEL. Full table in
`docs/RESOLUTION_NOTES.md` §E4BFILTCAL.

**RESOLVED + HW-VERIFIED 2026-07-31.** The law is almost exactly linear
(~0.767 dB per byte unit), not the curve the first ladder suggested — that
dataset was contaminated. Applied in `e4b_writer` and inverted in
`e4b_parser`; replayed on the E4XT at 7 points, **max error 0.34 dB** against
6.5 dB uncorrected.

**Still unexplained, but now isolated.** The two gain datasets disagree by
~2 dB in the middle while agreeing at both endpoints. Three candidate causes
have been measured and eliminated: level depends on neither **key** (±0.00 dB
across C1–C6), **velocity** (+0.00 dB, 5→125), nor **transposition** (2026-08-01,
the same 13 gains on transposing vs non-transposing keys differ by ≤0.66 dB,
mostly 0.20).

That exhausts the structural differences between the two datasets. The
reasonable conclusion is not that the discrepancy is understood but that it is
**isolated to one anomalous early measurement**, which four later independent
runs — different presets, different selection mechanisms, different sessions —
all contradict. The shipped linear law verifies on hardware at 7/7 within
0.34 dB. Left open in case it ever recurs; not worth further hunting.

## E4B cutoff position → Hz — RESOLVED + HW-VERIFIED (2026-07-31/08-01)

Measured on the E4XT with white noise (bank 2, `P_FLT`, 11 points): the real
curve is **`Hz = 125.9 · e^(3.494 · position)`** (r = 0.9958) with position
1.0 acting as a **bypass** (>20 kHz), against the 57 Hz → 20 kHz single
exponential that `hz_to_e4b_cutoff` assumes.

The error is small below ~400 Hz and reaches **3×** at the top: a source
asking for 3.4 kHz gets position 0.70, which the hardware renders at
**1.2 kHz** — about an octave and a half too dark. This affects every parser
that specifies cutoff in Hz (SF2, EXS24, GIG, SFZ).

Resonance, measured in the same pass, is fine — monotonic 0 → +37 dB peak
boost with the peak converging on the corner, no self-oscillation at 0.95.
No change needed there.

Full tables in `docs/RESOLUTION_NOTES.md` §E4BFILTCAL.

**RESOLVED + HW-VERIFIED 2026-07-31.** The writer now converts the shared
nominal position to the frequency it means and asks for the position the E4XT
actually renders there; the parser inverts it. Replayed at 10 points from
150 Hz to 12 kHz: **10/10 pass**, every reachable request within ±14%, both
clamped keys identical, bypass confirmed.

**Known limit:** the fit covers positions 0.0–0.9 only, so the honest
reachable range is 126 Hz – 2920 Hz with bypass above 7.6 kHz; a 3–4 kHz
request clamps rather than being extrapolated. Filling in 0.9–1.0 needs one
more sweep.

## MPC 3.x writes gzip+JSON `.xpm` — IMPLEMENTED (2026-07-30)

Found by checking ConvertWithMoss for MPC-related work over the last 3 months.
Their `58933a2c` (2026-05-18) added *"support to read JSON based .xpm files"*
and merged their Keygroup/Project detectors into one "Akai MPC Modern".

**MPC 3.x changed the container.** A modern `.xpm` is no longer XML: it is
**gzip-compressed**, with a 5-line plain-text header followed by JSON —

```
ACVS
3.9.0.31
SerialisableProgramData        (or SerialisableTrackData / ...ProjectData)
json
Linux
{ "data": { "version": 6, "name": "...", "programPads": { "pads": {128}, ... } } }
```

`parsers/xpm_parser.parse_xpm()` calls `xml.etree.ElementTree` directly, so it
raises `ParseError: not well-formed (invalid token): line 1, column 0` — the
file is not partially read, it is completely unreadable.

**Already present in Jan's library:** 3 files
(`~/temp/SamplerExports/K2-0{1,2,3}.xpm`, header `ACVS / 3.9.0.31 /
SerialisableProgramData / json / Linux`), i.e. exported from his own MPC. So
this is a live gap, not a hypothetical one. The other 564 `.xpm` in the
library are classic XML and unaffected. (101 more are X11 pixmaps — same
extension, unrelated format; worth a magic-byte guard so they are skipped
with a clear message rather than an XML error.)

**Status: IMPLEMENTED.** `parse_xpm()` sniffs the gzip magic and converts the
JSON program into the SAME element tree the XML path already parses
(`_mpc3_to_xml`), so the envelope/filter/LFO curves and the lane allocation
that splits overlapping layers into parallel voices are reused rather than
duplicated — one mapping, no drift.

Verified against all three real 3.9.0.31 files: every key range, root note and
velocity range matches the JSON exactly, and all 71 root notes independently
agree with the note number in each sample's own filename (the JSON `rootNote`
is 1-based, like MPC 2.x XML). A full conversion of `K2-01.xpm` produces a
7.06 MB E4B with 21 zones covering keys 0-127 and PCM in every sample.

**Validation is narrow, though** — those three are MPC Auto Sampler output:
one layer per keygroup, full-range velocity, no loops, no filter/LFO in use,
every per-layer tune/volume/pan at default. The structure is well covered; the
parameter scales are only covered *structurally*, since every value was a
default. A program using velocity layers, loops, real filter settings or
articulation switching should be re-checked against a real file. See the
"Validation scope" note in §MPC3XPM.

The X11-pixmap guard landed with it: a `.xpm` that is neither gzip nor XML now
raises a message naming the real format instead of an opaque XML error.

**Loops implemented** following ConvertWithMoss's two-tier scheme
(`layerLoopModeOverridesSliceLoopMode` picks between the layer's loop and
`sliceInfo`'s), adopted on their authority since no local file exercises it.
**Still missing vs CWM:** `direction` (reverse), Track/Project payloads,
`samples[].metadata.tune`, pitch-bend range.

**Parameter verification plan: `docs/re_procedures/mpc3_xpm_params.md`** — a
checklist of ~25 items across five groups (confirm what is assumed / verify
what we read / decide what we drop / cover non-auto-sampler shapes /
hardware-free cross-checks), with `tests/re_banks/mpc3_xpm_diff.py` as the
executable lever. Because MPC 3 programs are gzip+JSON rather than binary,
the one-parameter-at-a-time differential needs no byte hunting: change one
control, export, diff. **Highest priority is A1**, the `filterType`
enumeration — until that is confirmed, a converted program that actually uses
a filter cannot be trusted.

**Checklist item E1 (ConvertWithMoss crosscheck) DONE 2026-07-31** — the one
group that needed no hardware. It confirmed the filter enumeration, the
`{value0,value1}` slot reading, AD ⇒ sustain 0 and the loop scheme against a
second implementation; **settled A2** (root note is 1-based — proven from
inside the file, since `samples[].metadata.rootNote` encodes the same fact
0-based, agreeing on 71/71 layers); downgraded **A1** from "cannot be trusted"
to "corroborated, wants one sweep"; and narrowed **A4** to the top of the time
range (same exponential law both sides, 13.9 s vs 100 s at v=1 — ours is
hardware-measured, theirs is round numbers).

It also found **two real losses on our side, now fixed**: program/keygroup
`transpose` was dropped entirely, and `samples[].metadata` (`rootNote`
fallback + `tune`) was unread. Both are 0/default in every local file, so they
were verified by mutating a real file; conversion of the three unmodified
files is byte-identical to before. And **three bugs in CWM's MPC 3 reader** —
see `docs/RESOLUTION_NOTES.md` §MPC3XPM. Remaining checklist items all need
the MPC.

**Read the full official MPC v3.9 User Guide** — see §MPC3XPM "Full sweep".
Implemented from it: **AD-mode envelopes now import with sustain 0** (the
manual is explicit that AD mode decays to zero with no sustain, so reading
`Sustain` regardless inverted the behaviour), and **LFO 2 is mapped** to the
`lfo2_*` fields `VoiceLayer` already had. Next candidates, in value order:
envelope **Hold/Delay** (E4B envelopes are 6-stage, so the target can hold
them — needs a model change), **Filter 2** + blend + serial routing,
`pitchEnvelope`, `direction` (reverse), and Track/Project payloads.
**Unverified:** whether MPC 3's `filterType` integers still match MPC 2's
ordering — the manual defers to a glossary that does not extract cleanly.

**Corrected 2026-07-30 from the official MPC v3.9 User Guide:** the JSON's
`{value0, value1}` wrappers are **slots, not articulations** — MPC 3 has TWO
filters (with Blend and Parallel/Serial controls) and TWO LFOs. So taking
`value0` means taking Filter 1 / LFO 1, which is defensible rather than
arbitrary. **Dropped:** Filter 2 + blend + serial routing, and LFO 2 — the
latter is cheap to add, since `VoiceLayer` already has `lfo2_*` fields the XML
path fills. See §MPC3XPM.
See `docs/RESOLUTION_NOTES.md` §MPC3XPM.

## sampledir_parser: WAV smpl-chunk fine-tune read but never reaches the zone (FIXED, 2026-07-29)

Found from the VinSamLib side while checking whether `6c463c4` (`load_wav()`
now reads a WAV `smpl` chunk's `MIDIPitchFraction` into `SampleData.fine_tune`)
actually benefits the folder-of-WAVs import path, which that commit's own
message calls out as the main beneficiary ("the smpl chunk is the only tuning
metadata a sample carries" there).

**It doesn't reach a written file.** `parsers/sampledir_parser.py`'s
`parse_sample_dir()` builds each preset zone as:

```python
zones.append(ZoneMapping(sample_name=sd.name, lo_key=lo, hi_key=hi,
                         lo_vel=0, hi_vel=127, root_key=root))
```

— never copying `sd.fine_tune` across. Every writer (`e4b_writer.py`,
`krz_writer.py`, `eiii_writer.py`) reads `zone.fine_tune`
(`ZoneMapping.fine_tune`), not `sample.fine_tune`, so the value `load_wav()`
correctly populates is silently dropped one function later.

**Verified with a synthetic WAV** (`smpl` chunk: `MIDIUnityNote=60`,
`MIDIPitchFraction=0x80000000` → +50 cents, same fraction `6c463c4`'s own
round-trip note uses): `parse_sample_dir()` on a one-file folder gives
`SampleData.fine_tune == 50` but `ZoneMapping.fine_tune == 0`. Confirmed
downstream too, through VinSamLib's real `File > Import Sample Folder...`
pipeline (`build/sampledir_import.import_sample_dir()` → E4B write): the
written file's zone-table fine-tune byte decodes to 0 cents, not ~50.

**Fix:** pass `fine_tune=sd.fine_tune` into the `ZoneMapping(...)` call above.
**Status: FIXED** — reproduced exactly as reported (`SampleData.fine_tune == 50`
but `ZoneMapping.fine_tune == 0`), then fixed and verified one step further than
the report: a written E4B now round-trips back to 50 cents, so the value reaches
the FILE, not just the model.

## Stereo samples — E4B DONE (read+write), KRZ/EIII still downmix (PARTIAL, 2026-07-29)

Raised by Jan: *"I can sample in stereo on the hardware"* — correct, and
mpc2emu throws that away. Every source stereo sample is downmixed to mono
(`xpm_parser._stereo_to_mono`, reached by all six sample-loading parsers via
`load_wav`, plus `gig_parser`), and every parser hardcodes
`SampleData(channels=1)` even though the field exists.

**All three targets support stereo; we simply never emit it:**

- **E4B / EOS.** The E3S1 sample struct is the Emulator III's and stores every
  position *twice*, once per channel: start/end/loop-start/loop-end at offsets
  22/30/38/46 (left) and 26/34/42/50 (right), with `options` bit `0x0020` =
  left and `0x0040` = right. `parsers/e4b_parser._parse_sample` **already
  decodes right-channel-only objects** — it has to, because reading the left
  field unconditionally yields nonsensical loop points (6 of 73 looped
  right-channel-only samples in the local corpus). `writers/e4b_writer.py`
  hardcodes `0x0020`/`0x0031` (MONO_L).
- **EIII / ESI.** Same lineage, explicit constants already in
  `writers/eiii_writer.py`: `OPTION_CHANNEL_LEFT = 0x0020`,
  `OPTION_CHANNEL_RIGHT = 0x0040`, `OPTION_STEREO = LEFT | RIGHT`, and
  `SAMPLE_{START,END,LOOP_START,LOOP_END}_{LEFT,RIGHT}`. The writer sets
  `options = OPTION_CHANNEL_LEFT` and writes `0` to every RIGHT field.
- **K2000 / KRZ.** `numHeaders` + one `Soundfilehead` per channel; see
  `docs/KRZ_FORMAT.md` §3.1/§7.5, which already documents exactly what a
  stereo sample would need (`numHeaders = 1`, `flags` bit 0 set, second
  `Soundfilehead`).

**Cost of the gap:** a stereo capture converts to a mono preset — half the
recorded information discarded, silently. This is the single largest
fidelity loss in the pipeline that is not a hardware limit.

**Status: PARTIAL — the E4B path is done on branch `stereoE2E`.**

- **Fixed (bug):** `e4b_parser` read a stereo object's two channel blocks as
  ONE mono block, so stereo samples imported at double length and played
  left-then-right — ~23.6% of the local corpus. Layout RE'd from 473 banks;
  see `docs/RESOLUTION_NOTES.md` §E4BSTEREO. Always on, it is a bug fix.
- **Done (feature):** `e4b_writer` emits stereo, and `--stereo` carries
  stereo from source WAVs through to E4B output. Opt-in, because stereo
  doubles every sample against the 128 MB bank cap.
- **Safe:** `krz_writer`/`eiii_writer` now downmix explicitly at entry and
  say so, instead of mis-measuring interleaved PCM as mono.

**Still open:** KRZ stereo (second `Soundfilehead`, `numHeaders`) and EIII
stereo (`OPTION_CHANNEL_RIGHT` + the RIGHT half of each position pair). Both
encodings are already documented; neither is implemented.

**Hardware confirmation still required for the WRITE side** — the offline
evidence is strong but not conclusive (§E4BSTEREO "Offline confirmation
round"): our header reproduces E-mu's own bytes on 509 real stereo samples
for every field that carries meaning, and the fields that differ differ
identically for mono, which is hardware-confirmed. The EOS manual (p.93)
independently confirms one-object-per-stereo-sample, that right-side
parameters are ignored, and implies one stereo sample = ONE voice. What
remains is a 6-point bench checklist in §E4BSTEREO: does it load, does it
play in stereo, is the channel ORDER right, does it cost one voice or two,
what does pan do to a stereo voice, do both sides loop in sync.

**Default is now stereo-in/stereo-out** (2026-07-29, Jan's call): parsers
preserve channels and `--mono [mix|left|right]` is a vintage-fit reduction
rather than the default. `--mono auto` was investigated and rejected on the
data — see `docs/RESOLUTION_NOTES.md` §MONO — replaced by a correlation
advisory that warns when averaging would cancel signal.

**Channel order can be settled without hardware** — four real stereo samples
are exported to `~/temp/stereo_audition/` as stereo WAVs; if L/R were
swapped they play mirrored, which is audible on a familiar library.

**ConvertWithMoss has the same decode bug** (`Emulator4Detector` hardcodes
1 channel and reads both blocks as one mono region) and downmixes on write,
so there is no second implementation to check against — and this is
reportable upstream if Jan wants to.

**Blocked on / open questions before implementing:**

1. ~~**How EOS actually lays out a stereo sample**~~ — **ANSWERED** from the
   corpus without needing hardware: ONE object with both channel bits
   (`0x0020 | 0x0040`) carrying two SEQUENTIAL PCM blocks, addressed by the
   L/R halves of each position pair, with per-channel loop points.
   4803 of 20383 objects across 473 banks. See §E4BSTEREO.
2. ~~**Model change.**~~ **NOT NEEDED** — the processors already honour
   `channels` (`resampler`, `start_trim`, `tail_trim`, `auto_loop`,
   `loop_renderer` all compute frames as `len(data) // (2 * channels)`); only
   the parsers never set it. Original concern, kept for the record:
   `SampleData.channels` exists but nothing honours it;
   `data` is assumed interleaved-free mono 16-bit throughout the processors
   (resampler, auto-loop, trim, single-cycle all index frames as `data[i*2]`).
   Stereo would touch all of them, so scope this deliberately — possibly
   "carry stereo through to the writer, but keep processors mono-only and
   downmix when a processor is requested."
3. **Zone/pan interaction.** A stereo sample plus a per-zone pan setting is
   ambiguous; check what EOS does with pan on a stereo voice before choosing.

Not blocked on anything external — this is our own work, just not small.

## SF2 static filter + zone gain/tune — gain half RESOLVED + HW-VERIFIED; filter half still OPEN (2026-07-29)

`parsers/sf2_parser.py` previously read **no** static filter and **no**
preset-level generators, so every SF2 import arrived with the filter wide
open and zone gain/tune at defaults. As of `ea74e45` it reads gen 8/9
(`initialFilterFc`/`initialFilterQ`) and gens 17/48/51/52 (pan,
attenuation, coarse, fine) including the preset global-zone offsets — see
`docs/RESOLUTION_NOTES.md` §EIII-CWM.

**Why this is a writer-side concern despite being a read-side change:**
those fields are *already* consumed by both writers (`e4b_writer._build_voice`
writes `vpar[58]/[60]/[61]` from `filter_type`/`filter_cutoff`/
`filter_resonance`, and `vpar[36]/[54]/[55]` or the zone-entry bytes from
`fine_tune`/`volume`/`pan`; `krz_writer._patch_layer` maps the filter onto
the K2000 4POLE LOPASS and folds `fine_tune` into the keymap tuning). So
converted output **changes audibly** for any SF2 source that carries a
filter or non-default zone gain — a bank that used to render wide-open now
renders with the SF2's intended cutoff/Q.

That is the *correct* behaviour and matches every other reader we have,
but it is **not hardware-confirmed**: the whole path was validated only
against file-level expectations plus the system GM soundfont (3 of 20
presets carry a real filter), never played on an E4XT or K2000R.

Two specific things the mapping could get wrong, neither yet measured:

- **Q normalization.** `filter_resonance = q_cb / 960.0` uses the
  generator's full legal 0–960 centibel (0–96 dB) range from the spec.
  That's a *software format* range, not an E4XT-measured one — unlike our
  hardware-calibrated cutoff/mod constants in `models/common.py`. If SF2
  banks in practice only ever use a fraction of that range, imported
  resonance will read systematically too low.
- **Filter type / slope.** SF2 defines one fixed 2-pole (12 dB/oct)
  resonant lowpass, mapped to XPM type `1` (LP12). On E4B that becomes
  `vpar[58]=0x01` (2PLP), an exact slope match. On KRZ it does **not**:
  `krz_writer._k2_filter_plan` sends XPM type 1 to Alg 16 1-pole LOPASS
  (6 dB/oct, fixed -3 dB resonance) because the K2000 has no 2-pole
  option — Alg 1 is 4-pole/24 dB. So an SF2 filter renders half as steep
  on K2000 and loses Q control. That mapping predates this change and is
  a reasonable pick between 6 and 24 dB, but SF2 is the first source
  format to hit it routinely, so it is worth an ear before assuming
  24 dB/oct wouldn't sound closer.

**Status:** OPEN — read side shipped and corpus/file verified; the
writer path it now feeds is unverified on hardware.
**Blocked on:** an A/B on real hardware — convert one filter-carrying SF2
(e.g. a `default-GM.sf2` preset that has gen 8 set) to both `.E4B` and
`.KRZ`, play against the SF2 rendered in a soft sampler, and check the
cutoff/Q land in the right place. If Q reads consistently thin, calibrate
`q_cb` against a measured range the way `FILTER_ENV_FULL_CENTS` and
`VEL_FILTER_FULL_CENTS` were done (see `docs/RESOLUTION_NOTES.md` §19).

## SFZ/SF2 parsers: volume LFO (tremolo) not read — RESOLVED, read-side only (2026-07-28)

Cross-referencing ConvertWithMoss PRs
[#216](https://github.com/git-moss/ConvertWithMoss/pull/216)/[#233](https://github.com/git-moss/ConvertWithMoss/pull/233)/[#239](https://github.com/git-moss/ConvertWithMoss/pull/239)/[#240](https://github.com/git-moss/ConvertWithMoss/pull/240):
neither `parsers/sfz_parser.py` nor `parsers/sf2_parser.py` read an
LFO->Volume (tremolo) modulation, only LFO->Pitch (vibrato) and LFO->Filter.
SFZ v1 carries this as `amplfo_depth`/`amplfo_freq` (a third, independent
oscillator alongside `pitchlfo_*`/`fillfo_*`); SF2 carries it as generator id
13 `modLfoToVolume` (centibels), sharing the *same* "Mod LFO" oscillator as
generators 5 (`modLfoToPitch`) and 10 (`modLfoToFilterFc`) — that's SF2's own
convention, not a mpc2emu simplification.

**Fixed (read side):** added `lfo1_to_volume`/`lfo2_to_volume` fields to
`VoiceLayer` (`models/common.py`), plus `LFO_VOLUME_FULL_DB = 24.0` and
`lfo_volume_depth_to_amount()`. `LFO_VOLUME_FULL_DB` is **not**
hardware-calibrated (no MOD_DEPTH_CAL-style measurement exists for a tremolo
depth, unlike `LFO_PITCH_FULL_CENTS`) — treat it as a reasonable placeholder
until/unless it matters.

- `sf2_parser.py` reads generator 13 into the existing Mod-LFO block (already
  feeds `lfo1_*`) — no fallback logic needed, it's the same oscillator.
- `sfz_parser.py` reads `amplfo_depth`/`amplfo_freq` (v1) or
  `lfoNN_gain`/`lfoNN_freq` (v2) and, since the model only has two LFO slots
  (matching E4B/EOS's real 2-LFO hardware) but SFZ can specify three
  independent LFOs, claims LFO2 if free, else LFO1 if free, else **drops**
  the tremolo rather than overwriting an existing pitch/filter LFO.

Verified via `tests/test_lfo_volume.py` (new): depth<->amount conversion,
SFZ claims-LFO2, SFZ falls-back-to-LFO1, SFZ drops-when-both-taken. SF2 path
verified only by import/structural review — no binary SF2 fixture was built
(no existing SF2 test file to extend).

**Not wired into either writer (E4B or KRZ) — deliberately.** Neither format
has a hardware-confirmed "LFO->Volume" mod-destination byte in
`docs/E4B_FORMAT.md`/`docs/KRZ_FORMAT.md`, and ConvertWithMoss's own
Emulator4/Kurzweil writers don't implement one either (checked
`Emulator4Constants.java` — no VOLUME/AMP destination constant). Writing a
guessed destination byte risks misrouting modulation in a real hardware file.
Blocked on: RE'ing the real E4B/K2000 LFO->Volume cord-destination byte
(live-SysEx parameter-hunt method, same as used for the E4B sustain-byte and
`vpar` finds this session) before a writer can act on these new fields.

Also open, bigger, separate: `parsers/gig_parser.py` has **zero** LFO support
of any kind (no pitch, filter, or volume) — not touched here.

## KRZ: unused decay stage read as silent sustain — RESOLVED (2026-07-28)

Cross-referencing ConvertWithMoss PR #232 (fixed 2026-07-27, same bug in
their Kurzweil reader) found `parsers/krz_parser._decode_env` read a
decay stage with raw time AND level bytes both `0` — the device's own
"unused, hold the previous (attack) stage's level" convention — literally
as `sustain = level/peak = 0`, converting the preset to hold at silence.
Real corpus impact (201 local `.KRZ` files, 7228 voices): the fix drops
voices reading `sustain==0.0` from **30.6% to 1.6%** — a much bigger scale
than CWM's own writeup suggested (they cited specific "FM bass" examples).
Fixed by checking the raw bytes directly (`seg[6]==0 and seg[7]==0`) and
setting `sustain=1.0` (holds at the attack peak) in that case; the attack
and release stage loops already handled a mid-sequence `(0,0)` stage
correctly without needing the same explicit check (see
`docs/KRZ_FORMAT.md` §4.4 for the full writeup). New regression test
`test_decode_env_unused_decay_stage_holds_peak` added to
`tests/test_krz_roundtrip.py`; full existing suite still passes.

**Not yet hardware-confirmed** — verified against the real corpus and a
synthetic unit test, not yet played back on a real K2000/K2000R.

## zone_reducer: aggressive reduce_velocity_layers_pct collapses KEY coverage too — RESOLVED + HW-CONFIRMED (2026-07-28)

Found via real E4XT hardware confirmation of VinSamLib's own HW test matrix
(row 11, `reduce_velocity_layers_pct=75.0` on the 78-voice string preset -- the same preset the earlier `efe130c`
zone-reducer fix used). At 40% reduction (row 10), voice count goes
78 -> 22, spread reasonably across the keyboard. At 75% (row 11), voice
count collapsed to just **1 surviving voice**, covering **only MIDI keys
63-66** (a 4-semitone sliver) -- everywhere else on the keyboard had zero
zones. Confirmed on real E4XT hardware: silence everywhere except that
one narrow range, where the lone remaining sample (real, intact PCM,
715664 bytes/44.1kHz/16-bit -- not corrupted) played fine.

**Root cause (see `docs/RESOLUTION_NOTES.md` CR-21 for the full writeup):**
this preset's 5 velocity bands are wildly uneven -- 1/36/1/20/20 voices.
`_thin_and_redistribute`'s `keep_count==1` case picked the band at the
*middle sorted-index position*, with no regard for how many voices/keys it
actually covers -- which landed exactly on the 1-voice/4-key outlier band.
Row 10's "looks fine" 78->22 result was equally miscalculated (evenly-spaced
indices {0,2,4} happened to include both tiny outlier bands plus one real
20-voice band) -- it just wasn't visibly broken by luck.

**Fixed:** `_thin_and_redistribute` gained an optional per-item weight
(default unweighted, so existing key-zone/single-voice callers are
byte-for-byte unaffected); `thin_velocity_layers` now weights each band by
its voice count when selecting survivors. Verified against the real repro
file: 75% reduction now keeps the 36-voice band (80 keys, range 48-127)
instead of the outlier; 40% now keeps 41 voices spanning the *full* 0-127
range (up from 22, and genuinely complete this time). Two new regression
tests added to `tests/test_zone_reducer.py`; full existing suite still
passes.

**Hardware-confirmed 2026-07-28.** Rebuilt the exact repro case (real file,
75% reduction, fixed code) as `CD1-VL75FIX.iso` and loaded it on the real
E4XT: plays across the full keyboard (C2-D8, MPC-One octave numbering),
not just the previous 4-key silent-everywhere-else sliver. Heavy aliasing
at the pitch-shifted extremes is expected/correct for a 75% reduction, not
a regression. Closed.

Also: the VinSamLib images already staged on the SD card this session
(rows 08-12, part of the consolidated batch) were extracted from
VinSamLib's own pre-built `.hda` files (built before this fix existed) --
they still reflect the old buggy thinning and would need rebuilding
downstream in VinSamLib to pick up the corrected behavior.


## New E4B `vpar` fields found via live-SysEx parameter hunting (2026-07-28) — features to consider

While chasing `VOLENV_DEPTH`'s byte offset for the sustain-level item below,
did a broader live-SysEx hunt (method + full findings in
`docs/RESOLUTION_NOTES.md` §E4BPARAMHUNT) that found several previously-
unknown `vpar` bytes, now documented in `docs/E4B_FORMAT.md` §4.1/§4.2.
None of these are read or written by mpc2emu yet — logged here as
candidate features/gaps, not bugs:

- **Assign Group** (`vpar[27]`) — likely the "choke group" field already
  flagged as missing in the instrument-params TODO item below.
- **Glide Rate/Curve** (`vpar[37]`/`[53]`) — portamento, not modeled at all.
- **Realtime Xfade Low/LowFade/High/HighFade** (`vpar[22:25]`) — name
  suggests a round-robin/realtime key-crossfade zone, also flagged as
  missing in that same TODO item; meaning not yet cross-checked against
  the manual.
- **Auxiliary Envelope** (`PZT[28:40]`, a third full envelope generator
  alongside amp/filter) — entirely unmodeled; would need its own
  `Envelope` slot on `VoiceLayer` plus a decision on which XPM/SFZ/etc.
  source concept (if any) it should carry.
- **Voice Delay, Sample Start Offset, Chorus Width/X, Solo mode, Latch
  Mode, Filter Gen Params 1-8** — all now located, none modeled or judged
  for priority yet.

**Status:** offsets found and documented; whether/which of these are worth
implementing as mpc2emu features is an open product decision, not a
technical blocker.

## E4B amp-envelope 2-stage combination fix — RESOLVED + HW-CONFIRMED (2026-07-28)

**Context:** cross-referencing ConvertWithMoss PR #242 (independent E4B
reader) found `parsers/e4b_parser.py` only read stage 1 of each PZT envelope
pair (Attack1/Decay1/Release1), discarding the second stage entirely. For a
small but real fraction of local third-party content (0.9% of 32,558
voices) this made a voice that should decay to silence over many seconds
read as "holds near-full forever" instead (a `a commercial SFX` SFX bank,
verified byte-for-byte before fixing). Fixed in both amp and filter envelope
decode — see `docs/RESOLUTION_NOTES.md` §E4BREAD2 for the full
corpus-validation writeup, root-cause math, and regression tests
(`tests/test_e4b_parser.py`).

**Status:** code fix applied, corpus-validated (0 crashes across 141 local
files re-parsed before/after), and **hardware-confirmed 2026-07-28** — a
listen-control bank with the exact WALKER C1 raw bytes patched onto a plain
held sine tone (bypassing our own parser entirely) genuinely fades to
silence on a real E4XT, matching the new interpretation. Closed.

## E4B amp-envelope sustain LEVEL byte is exponential/dB-law, not linear — WRITER FIXED + HW-CONFIRMED, parser scope still open (2026-07-28)

**Context:** found while hardware-confirming the §E4BREAD2 envelope fix. A
calibration preset with `sustain=0.5` (linearly encoded as PZT level byte
64 by `models/common.py:env_level_to_byte`) was audible on the E4XT but
far quieter than "half volume" — needed the hardware volume knob raised
from ~45% to 100% to hear the sustain clearly.

**Root-caused and measured 2026-07-28** via a file-based 9-key sweep bank
(`tests/re_banks/gen_amp_level_cal.py` -> `AMPLVLCAL.E4B`, normal write
path, no live parameter edits) recorded on the real E4XT. First pass
(broadband RMS) pinned the bottom 3 of 9 points at an identical noise-floor
value; re-recording at higher hardware volume made them look *worse*, not
better — the signature of a fixed recording-noise floor, not real
measurements. Switched to a narrowband measurement at the test tone's own
220 Hz, which recovered clean monotonic data across the **full** 0-100%
range. Fits an excellent exponential/dB-law curve:
**`measured_dB ≈ 1.010 × target_pct − 98.74`** (R²=0.996, all 9 points). A
"linear 50%" target byte measures at only **-46.5 dB (0.47% actual
amplitude)** — confirms the bug's magnitude exactly (matches the "needed
to crank the volume" symptom). Full data table, fit, and the inverted fix
formula in `docs/RESOLUTION_NOTES.md` §E4BLEVEL.

**Status: writer fixed AND hardware-confirmed 2026-07-28.**
`models/common.py` gained `env_sustain_to_byte()` (inverts the measured
curve; both endpoints 0.0/1.0 special-cased to exact byte 0/127, avoiding
a ~0.3 dB artifact from curve-fit noise at the edges) and
`writers/e4b_writer.py`'s amp-envelope sustain encoding now calls it
instead of the plain linear `env_level_to_byte`. Existing tests
(`tests/test_e4b_parser.py`) still pass — expected, since only the
writer's *encode* side changed. **Deliberately scoped to the amp-envelope
sustain field only:**
- **Filter-envelope sustain is UNCHANGED** (same `_fenv_level(sus)` linear
  codec as before) — it's written inert/`filter_env_amount=0` by default
  so not currently audible, and applying the same fix there is a separate,
  not-yet-made decision.
- **The parser (`env_byte_to_level`) is UNCHANGED.** This is the important
  remaining open question: mpc2emu's own future E4B output will now sound
  correct, but reading an *existing* third-party E4B's sustain byte still
  assumes the old linear mapping — meaning mpc2emu currently **under-reads
  how loud a third-party preset's sustain really is** wherever that byte
  is non-trivial (e.g. carried through to KRZ/EIII conversion, or shown in
  `--info`). Fixing the parser too would change interpretation of every
  third-party E4B ever converted, not just new output — needs its own
  explicit decision, not a default "fix both sides" assumption.

**Hardware-confirmed** via `tests/re_banks/gen_hw_confirm_batch.py`
(`HWCONFIRM.E4B`, keys 48-52 = sustain 0/25/50/75/100%, normal writer path)
recorded on the real E4XT and narrowband-measured against the 100% key's
own plateau: **0%→0%, 25%→22.7%, 50%→45.6%, 75%→67.3%, 100%→100%** — an
approximately linear response, night-and-day from the pre-fix behavior
(a "linear 50%" target used to measure at 0.47% actual amplitude). Small
residual deviations are consistent with the calibration curve's own ~2 dB
fit residual, not a broken mechanism. Closed.

**Aside — the live-SysEx calibration attempt that was abandoned first:**
three rounds of live parameter-edit automation via the sibling
`../eosed` project produced incoherent, non-monotonic results (and one
device crash, "Gen Trap error", recovered by power-cycling) before this
file-based approach worked cleanly on the first try. See
`../eosed/docs/RESOLUTION_NOTES.md` §14/§15 and `../eosed/TODO.md`
for what went wrong there (`PRESET_SELECT` isn't "select for playback";
the crash's exact trigger is still unconfirmed) — useful context for
anyone tempted to script eosed against real hardware again, but not
relevant to the (now-resolved) calibration data itself.

## Follow-up: EIII/E3B import for VinSamLib (OPEN, 2026-07-28)

Requested by Jan once EIII/EIIIX/ESI output was confirmed working on real
E4XT hardware — **now done** (2026-07-28, see `docs/RESOLUTION_NOTES.md`
§EIII "Hardware confirmation"). Unblocked: port EIII/E3B import to
`../VinSamLib` (separate repo), on its own branch there too.

## KRZ->KRZ->KRZ: coverage-remap not idempotent across generations (OPEN, low priority, 2026-07-27)

**Found via `tools/krz_to_krz_check.py`** (parse → write → parse → write →
parse, checking gen2 vs gen3 for a fixed point) while adding KRZ as a source
format. 10 of 593 local `.KRZ` files drift in preset/zone count between the
2nd and 3rd generation — all of them this project's own synthetic multi-voice
octave-slice pad-stack test/demo banks (`JRSLO*`, `K2KFEATDEMO*`,
`krz_staging/VPO_BRASSACC|BRASSNOR|VIOLINKS`, `SCSYNTH_01`). **Zero real
commercial-library files are affected** — the 12 third-party soundset files that WERE
unstable here are now fixed (see the up-pitch-ceiling bug below).

**Root cause:** `writers/krz_writer._coverage_remap_voices()` (the octave-
slice-stack rebuild, §7.3 of `docs/KRZ_FORMAT.md`) regroups samples by root
note differently when it's handed its OWN previous output a second time, so
a second re-encode can leave a different subset of samples unreferenced by
any keymap. `parsers/krz_parser.py`'s orphan recovery correctly rescues them
each time, but that means a new tiny recovery preset can appear every
generation instead of the set settling to a fixed point.

**Status:** documented, not fixed — a real user's conversion only passes
through the writer once (KRZ→E4B, or any format→KRZ), so this only bites a
repeated KRZ→KRZ→KRZ chain of this specific stacked-pad content, which no
real library in the local corpus exercises. **Blocked on:** deciding whether
`_coverage_remap_voices` is worth making idempotent (or gating off when its
input is already coverage-remapped output) — a design question, not a quick
fix. Full root-cause writeup: `docs/RESOLUTION_NOTES.md` §KRZ-READER.

**Risk-assessment update (2026-07-27):** VinSamLib separately found a real
`struct.error` crash re-processing a single real commercial preset through
`_coverage_remap_voices()` in ONE pass (no repeated generations needed),
which looked at first like it might mean this "low priority" framing was
wrong. Root-caused as **two separate bugs, both now fixed**, neither of
which changes this entry's risk assessment:
1. `parsers/krz_parser.py` was fabricating a phantom 0-length `SampleData`
   for a sample whose `start_w` pointed outside the file's own PCM region
   (the source file is a multi-disk soundset, "<soundset>/**Disk1**" —
   the sample's real PCM lives on a different disk). Fixed: treated like
   ROM/absent, same as any other unavailable sample.
2. `_coverage_remap_voices()` computed `zz.hi_key = max(lo, ceil)` with
   **no clamp** to the hardware's 0..127 key range — unlike
   `_build_keymap_entries`'s zone-level ceiling check (which can only
   ever *reduce* `hi_key`), this path can push it to 128+ for a
   legitimate high-root/low-rate combination, overflowing the fixed
   128-key keymap buffer. This is the actual crash mechanism, reproduced
   independently with plain synthetic data (no phantom sample needed) —
   confirmed by matching VinSamLib's exact `struct.error` message. Fixed
   with a `min(NUM_KEYS - 1, ...)` clamp (+ matching defensive clamp in
   `_build_keymap_entries`). Regression test:
   `tests/test_krz_writer.py::test_coverage_remap_ceiling_overflow`.
Verified: full 589-file local corpus + 3-generation KRZ→KRZ→KRZ sweep both
show **zero exceptions** after these fixes (previously already zero
exceptions before finding this, since no real corpus file happened to
trigger the ceiling≥128 condition — VinSamLib's report was the first real
trigger found). The *idempotency drift* this entry describes is a
genuinely separate, cosmetic, non-crashing issue — confirmed still present
at the same 10-file count, unrelated to either bug above.

## VinSamLib real-hardware confirmation batch ready — testing PENDING (2026-07-27)

**Not a code task — a tracking note for real E4XT/K2000R testing Jan is
doing separately, tomorrow.** `VinSamLib/tests/manual_hw_convert_matrix.py`
(a sibling project's own script) built a 16-image batch under
`~/temp/VinSamLib_Test/` — 12 E4B `.hda` images (resample profiles,
bandpass/gain isolation, key-zone/velocity-layer reduction at two
aggressiveness levels, one combined case) and 4 K2000 Gotek `.img`
floppies (plain KRZ conversion, both resample profiles, max-sample-rate
limiting) — each generated through VinSamLib's real GUI code paths, not
just `build/convert.py` in isolation. `00_MANIFEST.txt` in that same
directory documents exactly what's on each image and what to check for
by ear/by eye on real hardware.

This batch is also the intended real-hardware verification vehicle for
the two open bugs directly above/below this entry
(`thin_key_zones()`/`thin_velocity_layers()` band-grouping) — images
#08-12 on the E4XT specifically exercise the reduce paths, with the
known `thin_key_zones()` no-op already disclosed in the manifest itself
rather than hidden, so testing isn't blocked on that fix landing first.

**Status:** images built and spot-verified in software (re-parsed,
zone/format checks passed); **real hardware confirmation not yet
done**. **Blocked on:** Jan's own hardware session (E4XT + K2000R via
ZuluSCSI/Gotek), scheduled for the day after this entry was written.

---

## E4B `loop_end` off-by-one fix — RESOLVED + HW-CONFIRMED (2026-07-28)

**Context:** cross-referencing ConvertWithMoss's independent E4B reader (PR #220
commit `2ccefea`) found `loop_end_l` stores the frame *before* the true
inclusive last loop frame, not the frame itself. Fixed in both
`writers/e4b_writer.py` and `parsers/e4b_parser.py` together (kept as exact
inverses, so mpc2emu's own write→parse round-trip is unaffected) — see
`docs/RESOLUTION_NOTES.md §E4BREAD` for the full writeup and verification
already done (synthetic round-trip + on-disk byte check + existing test
suite, all passing).

**Status:** code fix applied, verified in software, and **hardware-confirmed
2026-07-28** via `tests/re_banks/gen_hw_confirm_batch.py` — a 100 Hz sine
looped over exactly 20 whole periods (44.1 kHz → 441 samples/cycle, an
integer, so any loop-point error would show as a phase discontinuity at
the seam), held for 9s (~45 loop repeats) on the real E4XT and recorded.
Direct waveform check at every loop-boundary crossing found the
sample-to-sample delta there (0.0011-0.0018) *smaller* than the typical
mid-cycle variation elsewhere in the same recording (0.0083) — i.e. no
discontinuity, a clean seamless loop. Closed.

## ConvertWithMoss's E-mu format PRs (2026-07-26, #230/#231 now merged 2026-07-28)

Flagged by Jan; worth tracking since they overlap mpc2emu's own E-mu RE work:

- **[PR #220](https://github.com/git-moss/ConvertWithMoss/pull/220)** — E4B
  (Emulator IV/E4X/E4XT/E4K/e-Synth/e-6400) read+write, including reading
  banks straight out of `.iso`/`.img`/`.hda` EOS-filesystem images. Says it
  "handles older bank formats lacking EMSt chunks and oversized FORM
  sizes" — consistent with the mega-bank/optional-TOC1 quirks above. States
  it validated against **mpc2emu's own reference parser**, and against a
  hardware-created third-party bank (198 presets/1980 zones) with
  byte-identical PCM reconstruction. Zone-entry byte offsets described
  (fine-tune `[12:14]` BE i16, volume `[15]`, pan `[16]`, absolute-not-delta
  within a multi-zone voice) match what's already confirmed + shipped here
  (see the entry above this file's very first one). Not yet hardware-tested
  by its own author.
- **[PR #230](https://github.com/git-moss/ConvertWithMoss/pull/230)** —
  E-mu Emulator III / EIIIX / ESI-32/2000/4000 (E3B) read+write. **Merged**
  (`41835fd`), and now the basis of this project's own EIII support — see
  "EIII writer needs hardware confirmation on the E4XT" above. Its 3
  corrections to `emu3bm` (empty keymap/sample-table slots are holes not
  list-end markers; ESI variants pack flag bits into the upper bits of a
  zone's sample index; filter-type storage exists only on ESI, not EIIIX)
  are all incorporated into `writers/eiii_writer.py`/`parsers/eiii_parser.py`.
  Its own claimed validation (22 commercial CD-ROMs, 3,424 presets / 8,073
  samples) is now exceeded by this project's independent read-only run (1118
  banks / 19,040 presets — see above); still not hardware-verified by either
  project.
- **[PR #231](https://github.com/git-moss/ConvertWithMoss/pull/231)** —
  **Merged** (`3952110`), stacked on #230/#220: reads EIII banks directly
  from `.iso`/`.img`/`.hda` images, reusing the EOS filesystem code from
  #220. Not needed here — this project already builds EMU3/EOS images for
  E4B (`writers/iso_builder.py`/`writers/hda_builder.py`), and those
  builders are bank-content-agnostic, so they carry `.e3x` files unchanged;
  no direct-image-read path was needed. Its noted disk-geometry variants (2
  vs 6 root blocks; 256 KB vs 1 MB clusters) could be a useful cross-
  reference if EMU3 disk-geometry support ever needs to widen.

#220's independent validation against `e4b_parser.py` remains a nice
confirmation this project's E4B model is solid from an outside perspective.

## E4B per-zone fine-tune/volume/pan (multi-zone voices) — RESOLVED + HW-CONFIRMED (2026-07-26)

**DONE — hardware-confirmed on the E4XT, four-stage investigation, one
wrong turn corrected.** Chased as a ConvertWithMoss PR #220 cross-reference
(commit `7ce000f`, 2026-07-25) claiming the E4B secondary zone entry
carries fine-tune/volume/pan at `[12:14]`/`[15]`/`[16]` for a multi-zone
voice (a normal multisampled instrument — several keygroups/velocity
layers sharing one voice, which is what `xpm_parser.py`/`sfz_parser.py`
already build today via "lane allocation").

1. `B.012 "Vce VolPan"` (7 *single-zone* voices, distinct front-panel
   Volume/Pan each) — every zone entry stayed zero; `vpar[54]`/`[55]`
   (whole-voice) matched exactly. `vpar[54]` had already been hardware-RE'd
   2026-06-13, just never wired into the writer (hardcoded `0x00`);
   `vpar[55]` (Pan) was new.
2. `B.013 "MultiSZpVce"` (**one voice, 7 sample zones**) — zone entries ARE
   used for multi-zone voices, matching CWM's offsets. Its zone volumes
   were already asymmetric (`+10,0,0,-96,0,0,0`) yet `vpar[54]` stayed `0`
   — a first hint against a delta model, but every symmetric test built
   here up to that point (by design, min = -max) also landed on a
   representative of exactly 0, so "delta from a nonzero voice value" and
   "absolute value, voice unused" remained indistinguishable.
3. **First implementation attempt used a delta model** (voice value =
   range midpoint of its zones, each zone entry = its own delta from that)
   — internally consistent, passed every synthetic round-trip test, but
   WRONG. `ASYMTEST` (one voice, two zones with deliberately ASYMMETRIC
   values so the midpoint was nonzero, `+26`/`+10dB`/`+32`) — built by
   mpc2emu's own writer — showed the E4XT displaying the RAW delta bytes
   per zone, not the reconstructed absolute values. Jan caught the testing
   gap ("did we ever test a nonzero voice baseline?") before this shipped.
4. **Corrected to the simpler, now fully-evidenced absolute model:** a
   single-zone voice writes its value into `vpar[36]`/`[54]`/`[55]` (zone
   entry stays zero); a multi-zone voice leaves `vpar[36]`/`[54]`/`[55]`
   at zero and writes each zone's ABSOLUTE fine-tune/volume/pan directly
   into its own zone entry. Re-confirmed on hardware through this exact
   writer: `ZONEOFFSET` (5 single-zone voices), `MULTIZONE` (1 voice/3
   zones), `MULTIVOICE` (3 voices, DIFFERENT zone counts 3/4/2 — the
   voice-packing boundary case), and `ASYMTEST` all matched exactly.

See `docs/E4B_FORMAT.md` §4.1 (`vpar[54]`/`[55]`) and §4.5 (zone entry) for
the full writeup, including the disproven delta model kept as a documented
dead end so it isn't tried again.

**Implemented** in `writers/e4b_writer.py` (`_build_voice`/`_zone_entry`)
and `parsers/e4b_parser.py`. Verified: synthetic round-trip covering a
single-zone voice and a 3-zone voice with deliberately asymmetric absolute
values; real WAV-folder conversion with no source volume/pan/tune data
round-trips to all-zero bytes (no regression). Existing test suite
(11 tests) passes.

## `--trim-start` over-trimmed slow attacks — FIXED + VALIDATED (2026-07-31)

`processors/start_trim.py`'s onset detector was built and tuned against fast
synth-attack material (a Behringer K2-MKII capture via the MPC ONE
Autosampler, `~/temp/SamplerExports/K2-01_[ProgramData]`) — a two-stage
coarse-then-refine scheme (see `_start_cut_frame` docstring) that landed
within 2-4 ms of Jan's Audacity-measured onsets across 5 octaves (C1-C5) once
two real bugs were fixed: (1) the coarse window degenerates to a 1-sample
read at frame 0, so a single noise/dither spike right at the start could
spuriously trigger and return cut=0, defeating the whole trim; (2) backing
off by the *entire* coarse window (20 ms default) overshot consistently —
these are fast transients, not gradual swells.

**Not yet verified against genuinely SLOW-attack material** (bowed strings,
pads, organ swells, anything with a multi-hundred-ms attack) — only fast
synth/percussive-style onsets have been checked. The refine stage assumes the
true onset sits inside the coarse window and can be localized with a short
(3 ms default) re-scan; for a slow swell the "onset" is inherently fuzzy
(there's no sharp transient to localize), so the coarse-crossing point itself
— not the refine step — determines the cut, and that has never been checked
against a real slow-attack capture or an Audacity-measured target.

**ROOT-CAUSED 2026-07-31 — reproduced in software, fix NOT yet found.**
*(SUPERSEDED — this paragraph and the two below it are the investigation
trail. The fix was found and validated; see "FIXED + VALIDATED" below and
the heading of this section. Marked because a grep landing here reads as a
live open item, which has already cost one session's time.)*

The blocker is gone: slow-attack material now exists (synthesised — a 6 s tone
with a 3 s linear swell), and the hardware session produced a numeric
acceptance criterion, since a genuine swell starts at **1.7%** of its peak and
a mis-trimmed one at **50.8%** (§E4BSTEREO bank, `P6TRIMATK`).

**Confirmed failure:** `--trim-start` cuts **1.16 s off a 3 s swell**, leaving
it starting at 37% of peak instead of 0.8%. A 1 s swell is correctly left
alone.

**Cause,** instrumented rather than guessed. `_signal_threshold` takes
`max(peak−72 dB, floor+6 dB)`, and the floor is `_windowed_ms`'s
**10th-percentile window energy over the whole sample** — deliberately "robust
to the loud body". That is right for tail-trim, where the quiet part really is
the noise floor, and wrong for a gradual attack, where the quiet part **is the
signal**. On the 3 s swell the floor reads **−20.6 dB** instead of digital
silence, so the threshold lands at −14.6 dB rather than the intended
−78.4 dB — 64 dB too high — and the detector fires 39% into the attack. The
detector's own docstring names the assumption: it was tuned on *"fast synth/
percussive attacks, not gradual swells"*.

**A naive fix does not work, and was measured failing.** Replacing the
percentile with the minimum windowed energy (the lead-in floor) fixes the
swell exactly — 37% back to 0.8% — but **regresses real material**: on the MPC
autosampler corpus it drops from trimming 21/21 samples (~1.5 s) to 8/21
(~0.5 s), keeping ~45 ms of extra silence on 19 of 21. Real captures often
contain a genuinely silent window, which makes the minimum ~0 and disables the
adaptive floor entirely. So it trades over-trimming swells for under-trimming
everything else, and was reverted.

**What a real fix needs:** a floor estimated from the pre-onset region only,
or detection of the monotonic-rise case so the floor branch can be suppressed
just for it — while leaving the Audacity-validated fast-attack behaviour
byte-identical. Both test corpora now exist to check that.

**FIXED + VALIDATED 2026-07-31.** The floor is now estimated over the leading
`_LEAD_FRACTION` (10%) of the sample rather than the whole of it. A real
capture's lead-in silence still dominates that region's low percentile, so the
adaptive floor is unchanged; a swell's leading tenth is its own quietest part,
so the floor stays near silence and the intended peak-relative threshold
decides.

Validated in both directions, which is what the earlier attempt failed:

- **3 s swell:** onset 37% → **3.7%** of peak (mis-trimmed reference: 50.8%).
- **1 s swell:** 2.5% → 11.1%, still far below the failure mark.
- **Real MPC autosampler corpus:** trims **21/21 samples, ~1.5 s — identical
  to the original behaviour**, with exactly one sample differing, by one
  frame. The Audacity-validated fast-attack path is effectively untouched.

`tests/test_trim_slow_attack.py` pins both directions; reverting the fix fails
two of its three tests.

## A third-party two-stage E4B attack is decoded by a law fitted to neither stage (OPEN 2026-09-08)

`parsers/e4b_parser.py` decodes the attack as
`_fenv_rate_inv(pzt[0]) * _E4XT_ATK_SLOWDOWN + _stage2_seconds(pzt[2])` —
stage 1 carries the measured 1.838x correction and stage 2 does not.

**The magnitude is real:** with both stage bytes equal the total reads **22.8 %
short**, rising to **41.5 %** when stage 2 dominates, and it propagates into
every KRZ/AKAI/EIII conversion of that bank.

**But applying the scalar to stage 2 is NOT the fix, and was tried and
reverted.** `_E4XT_ATK_SLOWDOWN` corrects a **rate**, and a stage's time is
span/rate, so one constant corrects a rate only where the **span is fixed**.
Atk1 always travels 0 → 100, which is why a scalar works there. **Atk2 travels
from `pzt[1]`'s level to `pzt[3]`'s — a variable span** — so a scalar is the
wrong shape of correction. `tests/test_e4b_parser.py::test_two_stage_envelope_combines`
pins the current behaviour and rejected the change, correctly.

**Not reachable from our own output:** `e4b_writer` emits `pzt[2] = 0` always
(Atk2 holds full), so our files have no second attack stage and reader and
writer remain inverses. The exposed case is a bank written by an E4XT or
another tool.

**What would settle it:** a rate sweep on Atk2 with a KNOWN, non-trivial stage
split — set `pzt[1]` to a mid level so Atk2 has a real span, sweep its rate
byte, and measure time-to-full. That gives the span/rate law for a partial
stage, which is the missing piece for decay and release stage 2 as well (both
take the same time-alone path today).

**Status:** open. **Blocked on:** an E4XT rate sweep. Note `eosed` can send
whole presets over SysEx, so this needs no card crossing.

## AKAI program pan: combination rule with zone pan unmeasured (OPEN 2026-09-08)

Found by reading [ConvertWithMoss PR #400](https://github.com/git-moss/ConvertWithMoss/pull/400),
which implements the same three fields on their side. Independent work — the
offsets were already in their parser — but it points straight at three gaps of
ours.

| Field | Offset | Our state |
|---|---|---|
| Octave shift | `0x15` | **Parsed and never used.** `akai_s3000_parser.py:734` puts `octave_shift` in the program dict; nothing reads it. The writer emits a fixed `0`. |
| Stereo level | `0x17` | **Not read at all.** The writer emits a fixed `99` (full). |
| Program pan | `0x18` | **Parsed and never used** (`:742`). Only the per-zone pan at keygroup `0x12` survives; the program's own is dropped. |

**Consequences, in order of audibility:**

1. **Octave shift is a pitch error of up to two octaves.** It transposes the
   whole program: a key plays what is mapped an octave below or above it, so
   the key ranges move against the shift and the tuning with it. A program
   using it converts to the wrong notes, not merely a wrong tone.
2. **Stereo level is a level error.** A program authored below full level
   converts too loud. CWM measured **1,465 zones 0.7 dB lower** on one
   commercial CD-ROM once applied — small per zone, systematic across a bank.
3. **Program pan is dropped**, so a program panned as a whole flattens to
   whatever its zones say.

All three are **program-scope**, so each lands on every voice — the same shape
as `vel_loudness`, which sat unread until §KRZAMPVEL for the same reason.

**Semantics are settled by the manual, not assumed** (S3000XL Operator's
Manual, SINGLE page): `LEVEL` is *"the level of the program as it appears at
the left/right stereo outputs ... the equivalent of a mixer's fader"*, and
`PAN` runs *"L50 through MID (00) to R50"*. Note also that these are **MULTI
parameters**: a part's own values override in MULTI mode, so the program's
stored values apply in SINGLE — which is how a converted program is normally
auditioned, so they are audible, not vestigial.

**What still needs the bench, and it is small.** Decoding costs nothing; three
*laws* are currently assumptions and each is one measurement:

1. **Octave shift sign.** "Key ranges move against the shift and the tuning
   with it" is CWM's description, not ours. Getting it backwards transposes the
   wrong way, which is worse than dropping it. Set `OCTAVE` +1, play, check.
2. **Does stereo level reuse the measured loudness law?**
   (`dB = 0.642719 x PRLOUD - 87.63`, r2 0.9933.) CWM assumes it does. Two
   settings and a level reading either confirm it or produce a second law.
3. **Does program pan reuse the constant-power zone-pan law?** Same shape of
   check.

None needs a card swap — s3ked's probes set program parameters over SysEx —
and all three fit in one short session. **Do not apply any of the three until
its law is checked**; a wrong sign or a borrowed law is worse than the current
honest drop.

**Worth a corpus scan first**, as with the mute group: how many library
programs set a non-default octave shift or stereo level decides whether this is
a footnote or a systematic level error across every AKAI-sourced conversion.

## EIII per-zone LFO, tremolo and velocity-to-cutoff are not decoded (OPEN 2026-09-08)

Found by reading [ConvertWithMoss PR #403](https://github.com/git-moss/ConvertWithMoss/pull/403).
It names **zone 37 for tremolo and zone 38 for the filter LFO**, which is more
than our EIII format notes carry.

`parsers/eiii_parser.py:54` records this as a deliberate scope decision —
*"Per-zone LFO, key-tracking and velocity-to-cutoff are not decoded"* — and
`writers/eiii_writer.py:503` writes the LFO shape byte as a flat `0`. So an
EIII source's tremolo and filter LFO are lost on read, and nothing is written
on the way out either.

**What changes now:** the offsets were the expensive part and the PR supplies
them, so this drops from "RE project" to "decode two zone bytes".

**What does NOT transfer from that PR: its scaling.** It uses *"24 dB and 5,100
cents at full"*, which are their figures, not measurements we hold — and this
project has **no EIII hardware calibration at all** (`eiii_writer.py` says so
where it deliberately leaves key-tracking and velocity-to-cutoff neutral rather
than invent a conversion). Take the offsets, verify the scales, and do not
adopt a constant because it is written down somewhere.

**Not a gap:** Emax LFO-to-cutoff and the Emulator II write path, also in that
PR. Emax is a *resampling model* here (`--vintage emax1`), not an input format,
and there is no EII writer — nothing to be missing.

**Hardware answer, and it is the opposite of the AKAI case: there is none to
be had.** This project has **no EIII or ESI machine**, which is precisely why
`eiii_writer.py` leaves key-tracking and velocity-to-cutoff neutral rather than
converting them. So:

- **Read path: no hardware needed.** Decoding zones 37 and 38 into the model is
  free, and the model already carries LFO fields the other writers use. An
  EIII source's tremolo and filter LFO would then survive into E4B and KRZ,
  which is where they can actually be rendered.
- **Write path: cannot be confirmed at all.** Any depth we write to an EIII
  bank is unverifiable with the hardware we have.

The E4XT loads EIII banks through its own backward-compatibility loader, so it
is a tempting proxy — **it is not one.** It would measure the E4XT's
interpretation of an EIII bank, not an EIII's, and this project has already
been caught once treating one machine's rendering as another's.

**Status:** open. **Blocked on:** nothing for the read path. The write path is
blocked on hardware that does not exist here, so it should stay neutral rather
than adopt someone else's constants.

## Two AKAI header fields are documented but do nothing on this machine (OPEN 2026-09-08)

Both found during the 2026-09-08 bench session (s3ked, S3000XL):

- **`OSHIFT` (0x15)** — the byte is stored and read back, and **the pitch does
  not move**: 0.0 cents across −1/0/+1 on two independent detectors. The S1000
  document calls it a ±2 octave shift; the S2800/S3000 document says
  *"Range: 0. Description: Not used"*.
- **`PLAYLO`/`PLAYHI` (0x13/0x14)** — narrowed to 60–62 and read back as
  stored, **notes 48 and 72 sounded at full level**. The range does not gate.

**Neither costs us anything today** — `OSHIFT` is now an INFO note rather than
applied, and nothing consumes the play range. But the play range half means the
gate that would naturally have been used to measure a key-range shift **does
not gate**, so that question is open by a different route than expected.

**The pattern is the point: two fields in one header that are documented as
functional and are inert in silicon.** Before any further AKAI field is wired
up from documentation alone, it should be shown to *do* something — the S1000
and S3000-family documents disagree in at least these two places, and the
**S3000-family one has been right both times**.

**Next candidates, named rather than left implicit** (s3ked's suggestion):
`PRIORT` and `POLYPH`, both described in the S1000 struct and both plausibly
retired in the S3000 document. We parse `POLYPH` and consume it nowhere, so we
are accidentally correct there too — which is luck until someone wires it up.
**Check that a field does something before honouring it**, on this machine
family specifically.

**Status:** open, low priority. **Blocked on:** nothing; it is a caution, not a
defect.

## AKAI IB-304F second filter board not supported (OPEN 2026-09-08)

The base S3000XL filter is **2-pole**; most sources we convert carry 4-pole,
and that slope is lost today. The optional **IB-304F** adds FILTER 2 in series
with FILTER 1 — set both to LOWPASS and it is a genuine 24 dB/oct — plus a TONE
tilt section and ENV3.

**Nothing in the converter knows about it.** The fifteen keygroup fields live
only in a peer handoff; `docs/AKAI_S3000_FORMAT.md` has no FILTER 2, TONE or
ENV3 rows, so our writer cannot address them and our reader silently drops them.

**PHASE 0 IS DONE (2026-09-08).** The offsets are in
`docs/AKAI_S3000_FORMAT.md` — 23 fields at keygroup 168–190, from s3ked's
table, with the board-requirement split — and corpus-validated:

- **831 of 4,436 S3000 programs (18.7 %) have the second filter ENABLED**, but
  **only 333 (7.5 %) have one that is audibly doing anything** — 60 % of enabled
  keygroups are LP at frequency 99 with resonance 0 and no modulation, i.e. a
  pass-through. **7.5 % is the figure to plan against**; quoting 18.7 % as lost
  material overstates it by 2.5×. (Jan's question: "do those programs also have
  other parameters set, so filter 2 actually gets to work?")
- The 983 active keygroups are deliberately configured — most with three to six
  non-default parameters — and cluster in **EQ (469) and HP (374)**, the modes
  audible regardless of corner frequency.

**The halving does not lower the priority, and arguably raises it** (s3ked's
framing): the half that vanished was the *inert* half, so what remains is
material somebody sat down and configured three-to-six parameters at a time.
One library program in thirteen, and they are the ones whose author cared most.
The claim got smaller and the case got better.
- Where enabled, `FLT2MODE` spreads **LP 64.0 %, EQ 19.1 %, HP 15.2 %,
  BP 1.6 %**; where disabled it is 0 in 99.5 %. That correlation is what proves
  the read is aligned.
- **S1000 programs have no such offsets** (150-byte keygroup), which is what
  broke the first scan — 16,106 out-of-range values until it was restricted to
  S3000.

**So the READ path is unblocked and needs no hardware.** Decoding filter 2,
tone and ENV3 into the model would let that 18.7 % survive into E4B and KRZ,
where it can be rendered.

**The enable question is ANSWERED (2026-09-08): `LSI2_ON = 0` is an exact
bypass** — `FIL2FR` swept 20→99 with the enable off gives a **0.00 dB span** on
level and brightness, against 38 dB with it on. Our zero-filled programs are
unaffected, everything on the test card still means what it meant, and prior
baselines stand.

**THE EQ MODE IS CLOSED (2026-09-08).** Eleven captures, all restored and
verified: the mode enum measured from response shape, the sign crossing at
`FLT2Q` ≈ 23.1 (not the manual's 16), depths across every populated value,
`FLT2Q` 16 confirmed a singular notch from both neighbours, `FLT2GAIN` a
level-neutral switch, headroom +22 dB above bypass, and the arm-dependent
centre-frequency caveat. See `docs/AKAI_S3000_FORMAT.md`.

**NONE OF IT IS IN THE CONVERSION PATH YET.** The laws are measured; the code
uses none of them. Today the AKAI writer does not reference `filter_type` at
all, so a source HP, BP or 4-pole LP all collapse onto the machine's single
2-pole lowpass, and the parser reads no filter-2 field, so an AKAI second
filter is dropped entirely.

**ONE MEASUREMENT GATES BOTH DIRECTIONS: `FIL2FR` → Hz.** It is unmeasured
except at a single point, and **filter 2 does not share filter 1's corner law** —
our `FILFRQ` law gives **2503 Hz at byte 80** where filter 2 measures
**~2200 Hz** on the cut arm (0.88×). Without that law neither direction can
place a corner:

- **read** (AKAI → E4B/KRZ): mode, sign rule, depths and gain are all settled;
  the centre frequency is not.
- **write** (→ AKAI, behind `--akai-ib304f`): same gap, plus the 4-pole check
  is still unrun.

**Usefully, it is the same sweep already listed as open** — `FIL2FR` varied at
fixed `FLT2Q` on each arm. That one run separates the cut/boost topologies
*and* yields the corner law, and it must cover **both arms** because the centre
steps ~17 % across the sign change.

**Remaining after that:** `FLT2Q` 22/23 for the last 14 keygroups, which nothing
depends on.

**The WRITE path still needs the remaining laws**, and two sweeps gate it:

1. **`FLT2GAIN` — the more valuable one.** Enabling filter 2 costs **6.04 dB
   even fully open** (`FIL2FR` 99, `FLT2GAIN` 0 which the panel shows as
   +0 dB), with brightness identical either way, so it is level not tone. A
   4-pole conversion therefore arrives 6 dB quiet unless compensated — and
   whether the compensation belongs in `FLT2GAIN` or the zone level depends on
   whether 0 is simply not unity, or the filter has real insertion loss.
2. **`FLT2MODE` verification**, reading the field back at each setting: the
   enum is currently a panel photo plus a corpus distribution, which is two
   weak sources agreeing rather than a measurement.

**One open oddity, deliberately not modelled:** brightness is non-monotonic at
the dark end (`FIL2FR` 20 reads 13.7 dB brighter than 40, orderly from 40 up).
Candidates are resonance at a low corner, `FLT2MODE = 0` not being LP, or — my
hypothesis — the corner falling below the whole analysis band, where the ratio
compares two stopband regions and stops describing the filter.
The write policy is unchanged and is settled by a fact, not a preference:
**nothing on the wire distinguishes a fitted machine from an unfitted one**, and
`LSI2_ON` cannot detect the board — it reads back 1 with no board present. So
mapping a 4-pole source across both filters is correct on a fitted machine and
half-filtered on an unfitted one. A flag (`--akai-ib304f`), never a default.

**Status:** open. **Blocked on:** Phase 0 on nothing; Phase 1 on the board
being installed. Procedure:
`docs/re_procedures/akai_ib304f_filter_board.md`. Manual: S3000XL Operator's
Manual pp. 103–111 (local copy under `~/Seafile/Bibliothek/Handbücher`).

## AKAI CD3000 ISO mirror built for the --iso path's first hardware test (OPEN 2026-09-08)

`--iso` has never been read by a sampler; the disk-image path has been, many
times. `~/temp/HD4-MIRROR.iso` is the live test card's **exact content** —
34 volumes, 1400 files, 184.6 MB — rebuilt through `build_akai_hd_image(...,
cdrom=True)` and verified byte-identical to `HD4-work-v14.img` on every file.

Same content is the point: the card is a **control** that has been measured off
the machine repeatedly, so anything that differs on the CD is the **CD path**,
not the material. 360 MB / 6 partitions (34 volumes need 5; the 240 MB default
gives only 4), comfortably inside a CD.

**Status:** built, awaiting a card swap. **Blocked on:** bench time.

## E4B zero-sustain release is inferred, not measured (OPEN 2026-09-08)

At `env_sustain = 0` the release span is zero and `_env_span_rate(0, t)`
returned the INSTANT rate for any requested time — every release a dead cut,
audible whenever a key is lifted during the decay of a percussive one-shot.
Fixed 2026-09-08 by using the full span as the reference distance, plus the
minimum-audible floor the decay already carried.

**The full-span reference is a model choice, not a measured law.** It is
strictly better than a dead cut and it has never been in front of the machine.

**Status:** open, **material ready**. **Blocked on:** bench time only — no card
crossing needed, `eosed` sends whole presets over SysEx.
Procedure: `docs/re_procedures/e4xt_zero_sustain_release.md`.
Bank: `~/temp/HWCHK_REL.E4B` (generator
`tests/re_banks/build_hwcheck_e4xt_release.py`), six presets including a
pre-fix BEFORE case with `Rls1` forced to 0.

**Note the failure mode of the probe itself:** note-off must land INSIDE the
decay. A note held to its own silence measures nothing and reports a clean pass,
which is the same reason the defect went unnoticed.

## AKAI ENV2 downward-sweep floor is an unmeasured bound (OPEN 2026-09-08)

`AKAI_ENV2_SWEEP_FLOOR_HZ = 100.0` bounds how far down a negative ENV2 depth is
modelled to sweep, and its own docstring says it is **almost certainly an
artefact** of a normalisation that put the 0 dB reference on the slope once the
corner dropped below the measurement band.

Meanwhile `akai_filfrq_to_hz` is deliberately unclamped and descends to ~7.6 Hz,
so the two disagree by nearly four octaves. That disagreement produced a
sign inversion (fixed 2026-09-08: the headroom went negative and swept corners
below 100 Hz *upward*), and the fix clamps the headroom at zero — meaning
**every corner below 100 Hz now gets no downward sweep at all**, which is an
under-sweep rather than a wrong direction.

**What a real fix needs:** the actual lowest corner an ENV2 downward sweep
reaches on the S3000XL. The obvious candidate is the corner law's own bottom
(~7.6 Hz), which would deepen every sweep the bound currently limits — a
behaviour change across a large share of the corpus, so it needs measuring
rather than assuming.

**Status:** open, **material ready**. **Blocked on:** bench time only — no card
crossing needed. Procedure: `docs/re_procedures/akai_env2_downward_floor.md`.
Volume: `~/temp/HWCHK_ENV2/` (generator `tests/re_banks/build_hwcheck_akai_env2.py`).
Primary route is SysEx via `s3ked`'s probes; the volume is the fallback.

## Input-parser feature-parity gaps found via ConvertWithMoss 19.1.0 (ENHANCEMENT, OPEN 2026-07-25)

Cross-referenced ConvertWithMoss's [19.1.0 release notes](https://github.com/git-moss/ConvertWithMoss/releases/tag/19.1.0)
against our own EXS24/SFZ/TAL/SF2 parsers. **None of the fixes in that release are
live bugs here** — spot-checked the analogous logic in each of our parsers and it
already handles the case correctly (see `docs/RESOLUTION_NOTES.md §CWM19` for the
per-item comparison). What's left is a short list of **input fields/features CWM's
importers now extract that ours don't** — parity gaps, not correctness bugs.

Low priority; no user-facing complaint driving this, just recorded so it isn't
re-discovered from scratch next time CWM is cross-referenced.

**Status:** open, unscheduled. **Blocked on:** nothing — pick up any item
independently when there's a concrete need (a source file that actually uses the
field) or spare cycles. Fix strategy / CWM source citations in
`docs/RESOLUTION_NOTES.md §CWM19`.

## E4B resample pitch — RESOLVED + HW-CONFIRMED (2026-07-24)

**DONE — hardware-confirmed on the E4XT.** EOS4 pitches from E3S1 **`[58-59]` =
round(768·log2(rate/44100))** (1/64-semitone), NOT from `[54-57]`; we wrote it 0 →
sub-44.1kHz samples played sharp by 44100/rate. `[18-21]` is a non-deterministic
token (not pitch), left 0. Fix in `writers/e4b_writer._sample_header`. Full RE in
`docs/RESOLUTION_NOTES.md §E4BRATE`. **Commit-ready.** (Kept here as a record; safe
to delete.) Historical RE detail below.

### (was) EOS4 ignores our sample-rate field — needs HW diff

Any E4B sample stored **below the E4XT native 44.1 kHz** plays **sharp by exactly
`src_rate/dst_rate`**. HW-confirmed on K2-01/02/03 autosampler banks
(`K2_AUTOSAMP.iso`): plain (44100) and `--single-cycle` (~44–45 kHz, baked) are in
tune; every `--resample` variant (emax1/emulator2 → 27500 Hz: E2/EX/E2SC/EXSC) is
+8.18 st (= 44100/27500 → C3 sounds G#3), whether looped or one-shot.

**Not a resampling-quality bug and NOT fixable by upsampling** (that discards the
RAM saving that is the point). The E4XT *does* honor low rates — EOS "Sample Rate
Convert" (Sample Edit → Tools1 → SrCnv) lowers a sample's rate for "saving memory /
increasing upward transposition range" and **keeps pitch** (4.0 manual p.211-212).
So the bug is that `write_e4b` stores the rate **only at E3S1 `[54-57]`** — an
offset taken from **emu3bm (EOS *3*)**, never HW-verified for EOS *4* — and EOS4
reads the playback rate from a **different field** (candidates: `[58-59]`
playback_rate or one of `parameters[6]` at `[70-93]`, all currently written 0).
Plain works only because 44.1 kHz is EOS4's implicit default.

**Status:** root-caused to the E4B writer's sample-rate field. KRZ/K2000 path is
unaffected (different writer; K2000 honors rate via the `maxPitch` formula).
**Blocked on:** a hardware artifact to diff — see `docs/RESOLUTION_NOTES.md §E4BRATE`
for the SrCnv capture procedure and `tests/re_banks/diff_sample_rate_field.py`.

## MPC Standalone 3.9.0 `.xpm` — gzipped-JSON "ACVS" format (SUPERSEDED — see the IMPLEMENTED entry at the top)

Programs saved by **MPC Standalone firmware 3.9.0** (hardware — MPC ONE etc.) are
**not** the XML `.xpm` `parsers/xpm_parser.py` expects. They are **gzip-compressed**
(magic `1f 8b 08`); decompressed they start with a small text header
`ACVS\n3.9.0.31\nSerialisableProgramData\njson\nLinux\n` followed by a large **JSON**
document (`{"data":{"version":6,"name":...,"type":...,"programPads":{...}}}`).
`xpm_parser` chokes with `not well-formed (invalid token): line 1, column 0`.

**Impact:** these programs can only be converted today via their sidecar
`<name>_[ProgramData]/` folder of note-named WAVs (`convert.py <dir> --from-samples`),
which loses the program's synth params (filter/env/LFO/zones) — only the samples +
auto-mapped key zones survive. Reference files: `/media/lentferj/3433-6435/
SamplerExports/K2-0{1,2,3}.xpm` (+ their `_[ProgramData]` folders).

**Status:** unresolved — needs a new parser (gunzip → strip header → parse JSON →
map to the `Bank`/`Preset`/`VoiceLayer` model). Fix strategy in
`docs/RESOLUTION_NOTES.md §MPC39`.

**Blocked on:** RE of the 3.9.0 JSON schema (field→model mapping). Decompressed
sample dumped at ~1 MB/program; keys under `data` need cataloguing.

## ~~MPC filter dropped at max cutoff~~ (FIXED 2026-08-31)

`parsers/pgm_parser.py` (`if f1_type in _PGM_FILTER_XPM and f1_freq < 100`) set
`filter_type=0` when an MPC1000-family pad's cutoff was fully open, discarding
the pad's **resonance** (and any filter-envelope modulation) along with the
closure. Fixed: the filter is now created whenever `f1_type` names a real
type, regardless of cutoff position -- matches ConvertWithMoss `c7b9641`.
`parsers/xpm_parser.py`'s MPC 2.x/3.x path was checked for the same
cutoff-gates-the-filter pattern (per this row's original note) and does not
have it -- `filt_type` there is never conditioned on the cutoff value, so no
change was needed there. `tests/test_pgm_parser.py` (new file, since
pgm_parser had no dedicated tests before this): 3 tests, a synthetic
single-pad `.pgm` built directly against the module's own documented byte
layout; the fully-open case confirmed to fail with the fix reverted. See
`docs/RESOLUTION_NOTES.md §MPCFILT`.

## Carry more instrument params: choke groups, one-shot, key-track, round-robin (ENHANCEMENT — OPEN 2026-07-24)

Our model (`models/common.py`) doesn't carry several params many source formats
provide (cf. ConvertWithMoss `6fcc346` #212, which added them to its neutral model):
- **Exclusive / choke group** (highest value — closed hi-hat cutting an open one;
  useful for MPC/SFZ drum kits → E4B/K2000 if the targets support a mute/exclusive
  group). Not modelled.
- **One-shot** as a first-class flag (we only infer it via a release-time heuristic
  in `pgm_parser`; formats collapse it into "no loop").
- **Amplitude key-tracking** (we have filter keytrack, not amp).
- **Random / round-robin** play logic.
Each = parse from source + map to the E4B/KRZ writer where expressible.
**Status:** not started (larger, per-format). **Blocked on:** confirming which the
E4XT/K2000 actually support (esp. exclusive groups). See `docs/RESOLUTION_NOTES.md
§MODELPARAMS`.

## Auto-loop sustained samples — RESOLVED + HW-CONFIRMED (2026-07-25)

**DONE — merged to main, hardware-confirmed on the E4XT.** Places a **clean
sustain loop** in the steady region of a sustained sample (organ, strings,
pads, choir, brass, analog synth) so a held note sustains indefinitely — the
autosampler follow-on to `--trim-tail` (trim the dead tail, then loop the
body). `processors/auto_loop.py` + `--auto-loop [auto|MS]` (and
`--auto-loop-xfade/-max-ms/-min-quality/-force/-trim/-dump-dir`), wired after
`--trim-tail` in the pipeline; loops round-trip through both E4B and KRZ
writers.

**As-built** (see `docs/RESOLUTION_NOTES.md §AUTOLOOP` for the details): click-free
splice by CONSTRUCTION (equal-power crossfade ending exactly on the sample before
loop-start → the wrap reproduces the natural waveform run; measured click ~-240 dB,
synth sawtooth edges included). **Adaptive length**: prefers the LONGEST
transparent loop so the sustain sounds organic, snapped to a whole number of
modulation cycles when the tone beats/vibratos. Objective sweep + full local
audition across the mellotron/VPO/prophet/K2 test set: solo/pure timbres
(flute, cello, clean choir, analog synth) loop excellently (match <0.07);
dense ensemble / noisy analog is inherently hard (0.2-0.55) and gets a longer
crossfade + a `[weak match — audition]` advisory or a skip.

Possible follow-ups (not blocking): pitch-based vibrato detection
(amp-envelope misses pure vibrato); tuning the quality threshold.

## K2000R "Object → Delete" LOCKUP — RESOLVED, and it was never our converter

Deleting a program loaded from a converted KRZ locked up the K2000R (~2
factory-reset cycles to recover).

**Root cause: `k2kremote`'s ~2–3 s `GETGRAPHICS` heartbeat**, which polls the
machine for its LCD contents. Arriving while the K2000 is mid-delete, it
crashes it. With k2kremote closed, deleting programs from converted banks is
clean — including the banks that originally triggered this entry.

**Nothing to fix here.** The fix belongs in `k2kremote` (suppress or defer the
heartbeat while a destructive panel operation is in flight). Full detail in
the `project_k2000_delete_lockup` memory.

This entry sat marked "unresolved, paused mid-investigation" well after the
cause was found — worth noting as the failure mode of a long TODO file, not
just a stale line.

Key points: isolated to deleting a PROGRAM object (keymap-only delete is clean);
**reproduces on REAL soundsets** (a commercial soundset, authored `disk 1 of a two-disk soundset`) — so likely
**K2000-side, not our converter**. Our program/keymap/sample objects are byte-for-byte
valid vs real banks (DFLT/CUTLO/a third-party bank/a two-disk soundset/soundset). Leading theory: deleting a
program loaded **individually** (partial dependency chain) corrupts the K2000 object
table. Open: confirm whole-bank-load deletes are reliable; test `PPNOLOOP.img`; check
OS version / another unit. Uncommitted `_build_keymap_entries` gap-fill (sampleId=0)
did NOT fix it — reconsider reverting. See memory for tests, artifacts, next steps.

## Code-review findings (2026-06-10) — high-effort multi-agent review

**Status: ALL RESOLVED (2026-06-10 → 2026-06-12).** CR-1 through CR-18 are all
fixed & pipeline-verified, or marked false-positive / N-A (CR-11b, CR-18 #2).
No open code-review items remain — this section is kept as a record only.
Fix strategies + patches in `docs/RESOLUTION_NOTES.md` §CR (Code Review).

**Resolved 2026-06-10:** CR-2, CR-4, CR-5, CR-8, CR-9, CR-11, CR-12 — fixed &
pipeline-verified. **CR-11b — FALSE POSITIVE** (MPC2000 sample-index 0 *is* the
"unassigned" sentinel: `names[0]=''`, 50/64 pads use it; the `0 < sn` guard is
correct). **Resolved 2026-06-11:** CR-3 — `write_talsmpl` rewritten to the real
TAL v11 schema (clones a full default `<program>` from `parsers/tal_template.py`,
overrides only modelled attrs; external-WAV refs); write→parse round-trip
lossless. **TAL-Sampler load test PASSED 2026-06-11** (real MPC drum kit) —
uncovered & fixed 5 more writer bugs (`<programs>` wrapper, layer bin-packing,
`track`/`stereoinverse`="0" for one-shots, neutral filter, CRLF); only the
absolute volume/cutoff law approximations remain — see
`docs/RESOLUTION_NOTES.md §CR`. **Also 2026-06-11:**
CR-1, CR-10, CR-11c — KRZ writer: one keymap + one layer per voice (no more N×
stacking; per-layer key/vel range so velocity layers modelled as separate voices
now split correctly); loop end written as `sampleEnd`; ping-pong baked like
`write_e4b`. See `docs/RESOLUTION_NOTES.md §CR`. **Also 2026-06-11:** CR-6
(zone-reducer overlap guard) and CR-7/7b/7c (sample-name collisions) — fixed &
verified. See `docs/RESOLUTION_NOTES.md §CR`.

**All P0 code-review items are now resolved.**

---

## KRZ: program parameters — FILTER + ENVELOPES + LFO IMPLEMENTED (2026-06-15)

`writers/krz_writer.py` now clones the K2000 #199 "Default Program" template
(`_TPL_GLOBAL`/`_TPL_LAYER`, RE'd via Gotek disk-save — see
`docs/re_procedures/krz_program_re.md` §16) and patches per-voice values:
**4-pole lowpass (cutoff+resonance), amp envelope, filter envelope, LFO1 vibrato.**
All round-trip-verified against the file format. **HW load-test DONE 2026-06-16**
(converted MPC banks on the K2000R) → found+fixed two writer bugs (doc §17c):
one-shot samples were force-looped (loop bit is 0x80: clear=on; fix `0x70 if
looped else 0xF0`), and MPC Velocity→Filter was ignored, muting Cutoff=0 basses
(fix: fold `velocity_to_filter` into the effective cutoff).

### Feature gaps — input features we cannot yet map to KRZ (TODO)

**Filter — highpass / bandpass / notch now IMPLEMENTED (2026-06-16).**
- **HW-VERIFIED via floppy demo banks 2026-06-21** (by-ear, Jan): all four
  filter-type demos read correctly on the K2000R — filter-TYPE *and* cutoff-Hz
  mapping confirmed on hardware (not just round-trip):
  - `4PoleHP` (Synth-Pulse-Synt, src FilterType=7, Cutoff=0.41) → **4-pole
    high-pass @ ~330 Hz**
  - `2PoleBP` (Synth-MS20-Patch, FilterType=11, Cutoff=0.46) → **band-pass @ ~466 Hz**
  - `Notch` (Synth-MS20-Patch, FilterType=18, Cutoff=0.04, Resonance=0.89) →
    **Double Notch w/SEP, FRQ Coarse 22 Hz**
  - (1PoleLP / Bass-Pulse-Bass verified separately — see the floppy clamp item.)
  The three cutoff points (0.04→22, 0.41→330, 0.46→466 Hz) lie on one exponential
  curve → the **Cutoff-Hz mapping is faithful**, confirming the §"sonically
  CONFIRMED" note below with explicit Hz readouts.
- Filter-type bytes hardware-RE'd from `FILTERS.KRZ` (K2000R disk-save of progs
  312-315) and wired into `writers/krz_writer.py` (`_k2_filter_byte` +
  `_patch_layer`): `HOB0[0]` = **LP 50, HP 54, BP 55, NOTCH 56, NONE 62**.
  XPM `filter_type` families map: Low/Model/MPC→LP, High→HP, Band/Band-boost→BP,
  BS notch→NOTCH. End-to-end round-trip verified (write_krz → krz_reader).
- Remaining lossiness (acceptable): K2000 has one slope per family, so multi-pole
  source variants (2/4/6/8-pole) collapse onto the single 4-pole type; Vocal
  formant sources (XPM 26-28) have no Algorithm-1 analogue → fall back to LP.
- Cutoff (signed semitones) + resonance (`round(dB×2)`) encodings are
  sonically CONFIRMED on hardware (centroid tracks cutoff; resonant-peak boost
  ≈ display dB). Cutoff Hz curve is faithful, not just an approximation.

**Modulation routings (mod wheel / pressure / velocity / keytrack)**
- **Routing byte OFFSETS now located** (2026-06-16, doc §17k) by corpus analysis of
  14212 real layers: filter Src1=HOB0[5]/depth[6] (ENV2 filter-env — implemented),
  filter Src2=HOB0[7] (velocity=100/mod-wheel=1 go here), amp Src2=HOB3[7]
  (vel/mwheel→amp), amp LFO=HOB3[10] (tremolo), pitch Src CAL[21]/[26] (vibrato).
  Control-source CODES all known from the manual (doc §17e). **Remaining blocker for
  implementing any of these: the depth byte↔(cents/dB) calibration** — needs HW
  (disk-save or audio-rig at known displayed values; the F1 Src-depth range is
  ±10800 ct but the byte curve isn't pinned). **New candidate lead (2026-07-27):**
  ConvertWithMoss [PR #232](https://github.com/git-moss/ConvertWithMoss/pull/232)
  (merged) independently implemented KRZ velocity(AttVel=100)→cutoff read+write
  with a round-trip they claim reproduces a real K2000-saved program, using
  `MAX_VELOCITY_MODULATION_CENTS = 9600` (8 octaves) for the F1-page depth byte —
  a different number from our own unconfirmed ±10800 ct estimate above. Worth a
  disk-save cross-check against this value before trusting either. Not yet used
  here — still needs our own HW confirmation per project convention.
- **Mod-wheel → vibrato depth** and **mod-wheel → filter** (very common in sources). NOT mapped.
- **Velocity → filter cutoff** (`velocity_to_filter`): partially mapped 2026-06-16 —
  folded into the static effective cutoff (`min(1, cutoff + velocity_to_filter)`),
  HW-validated against the MPC ("VelToFilter pushes cutoff up very far"). A true
  per-note VelTrk sweep is deferred (VelTrk located on the F1 page; a sweep from the
  16 Hz floor would re-mute soft notes). **Velocity → amp**: still NOT mapped.
- **Keytrack → filter** (`filter_keytrack`). NOT mapped.
- Aftertouch/pressure routings. NOT mapped.
- (These all live as source+depth on the function pages / CAL, like the two we
  decoded.  **Control-source CODES are now all known** from the manual (doc §17e),
  validated against RE: AttVel=100, MWheel=1, MPress=33, PWheel=35, KeyNum=98,
  LFO1=114, LFO2=116, ENV2=121, ENV3=122, AMPENV=120.  Only the per-page Src/Depth
  byte OFFSETS + depth calibration still need a disk-save.)

**Filter slope — 2-pole lowpass IMPLEMENTED (2026-06-16, doc §17g).** Low1/Low2 now
map to the K2000's gentler 12 dB 2POLE LOWPASS (Algorithm 3) instead of the 24 dB
4-pole. Decoded from POLE2LP.KRZ: only 3 bytes differ from the 4-pole path
(HOB0[0]=2, HOB2[0]=39 BAL, CAL[29]=3); same layout, no separate template.
`_k2_filter_plan` in krz_writer; byte-exact to HW #320/#322. Still 4-pole (2-pole
bytes not yet RE'd): High1/2, Band2, notch — another disk-save batch if wanted.

**Envelopes**
- **Pitch envelope (ENV3)** — segment + encoding known, not yet wired.
- Only ADSR; source **delay/hold** (DAHDSR) stages dropped.
- Filter-env depth + LFO→pitch depth are **approximate** (2-point linear fits;
  need a low-end data point for exact cents).

**LFO**
- **LFO2** (second LFO) not written (only LFO1).
- **LFO → filter** (filter wobble) and **LFO → amp** (tremolo) not mapped (vibrato only).
- LFO **delay/fade-in**, **tempo-sync**, **MxRate** not mapped.
- **LFO shapes — DONE 2026-06-17** (live K2000R SysEx probe): all 26 shapes
  mapped (0=Sine…4=Triangle…6=Rise…8=Fall…20=8 Step). `_LFO_SHAPE` updated.

**Other**
- **Pan** (per-zone) not mapped to the K2000 pan (F4/output).
- Velocity → pitch.

---

## KRZ: fidelity gaps found via ConvertWithMoss cross-reference (OPEN, 2026-07-22)

ConvertWithMoss (git-moss) added a KurzFiler-derived K2000/K2500/K2600 reader+
writer in 2026 (`format/kurzweil/`, not HW-tested). A full byte-level compare
against `krz_writer.py` found **nothing to learn on the VAST program side** (we
decode filter/env/LFO; CWM writes a flat default program — and in two spots CWM's
writer is *wrong* where ours is HW-corrected: it writes `LYR[6]=hiVel` when that
byte is the Enable source, and writes the keymap id into `CAL[7,8]` which silences
4+-layer programs). The gaps run the **other** way — container/keymap/sample-header
fidelity we don't yet emit. Fix recipes in `docs/RESOLUTION_NOTES.md` §KRZ-CWM.

- **Per-sample gain — DONE + HW-CONFIRMED (2026-07-23).** `Soundfilehead.volumeAdjust`
  (byte 2) is a signed i8 in **0.5 dB steps**; `write_krz` now aggregates the
  referencing zones' `ZoneMapping.volume` (mean) per sample and `_write_sample_object`
  writes `round(gain_dB × 2)` (`_vol_adjust_byte`, clamped ±i8) into volumeAdjust +
  altVolumeAdjust. 0 dB → 0, so unity banks stay byte-identical (HW-verified filter
  floppies unaffected). **HW check on the K2000R** (`tests/re_banks/gen_volume_adjust_test.py`
  → `VOLADJ` floppy): three constant-pitch key-blocks at 0/−6/−12 dB stepped down in
  loudness exactly as intended → the K2000 honours the field and the 0.5 dB/step scale
  is right. (Note: K2000 labels middle C = MIDI 60 as **C3**; our `_note_name` uses the
  C4=60 scientific convention — a one-octave display-only difference, no byte impact.)
- **Partial key-tracking not expressible.** `_build_keymap_entries` writes a
  *constant* per-zone tuning → implicitly 100 % chromatic tracking. A source with
  reduced/zero key-tracking (drum maps) needs the per-key form
  `round((keyTracking − 1)·(note − rootkey)·100) + fine_tune`. *Blocked on:* a
  source that actually carries a keytrack ≠ 1 to test against.
- **Native 8-level multi-table keymap not used.** The K2000 keymap `Level[8]`
  can address up to 8 velocity tables in *one* keymap (level `j` = velocity
  `j·16…+15`). We instead split every velocity band into a separate keymap +
  program layer (`_split_voice_by_velocity`), which burns layers against the
  32-layer cap and the "3 regular layers" rule. Adopting the native form would
  fold velocity layers back into one keymap. *Blocked on:* design decision +
  HW confirm (larger change; weigh against current layer-splitting, which is
  HW-verified). Bit-layout HW-documented but the multi-table write path is untested.
- **Stereo / multi-root sample objects.** We emit mono, single-header only. The
  generalization is `numHeaders = N−1`, `flags` bit 0 = stereo (L/R header pairs,
  even index = left), and envelope offsets `(numHeaders−1−i)·32 + 8/+6` instead
  of the hardcoded `8/6`. *Blocked on:* stereo handling is a broader converter
  feature; HW confirm needed.
- **Doc-only:** our `hash >> 10` object-type decode mislabels the FX/song/QA
  objects (types > 42 use the 8-bit `hash >> 8` decode when the 0x8000 bit is
  clear). We never emit them, so this only matters for a future reader — noted in
  `docs/KRZ_FORMAT.md` §2.2.
- **Entry-index base — evidence gathered, not HW-closed (2026-07-27).** While
  building `parsers/krz_parser.py` (KRZ-as-source-format), checked CWM's claim
  that entry `i` sits at note `i+12` against 577 local `.KRZ` files: a
  root-inside-zone test over 8,010 multisample entry-runs favors `note = i`
  (39.6%) over `note = i+12` (26.4%) — i.e. **mpc2emu's own convention (raw MIDI
  note) looks right, CWM's `BASE_NOTE=12` looks wrong**. Software evidence only;
  not conclusive enough to close without an aural/HW check on real K2000
  content (see the parser's verification plan). See also the CAL-keymap-slot
  finding below, and the personal-outreach item further up this file.

---

## KRZ: program parameters (envelopes / filter / LFOs) — OPEN (2026-06-14)

**Status:** strategy + tooling complete; hardware RE not yet started.
**Blocked on:** hardware iteration on the K2000R (and, ideally, a PC↔K2000R MIDI
link to enable the scripted-SysEx approach — open question for Jan).

We can convert sample mapping + tuning to KRZ (HW-confirmed sounding) but **not**
envelopes / filter / cutoff / resonance / LFOs the way the E4XT path does. We
have the program object's *structure* (segment skeleton, the Algorithm-1
`PITCH → 4POLE LOPASS W/SEP → AMP` target, the uniform 4×HOB DSP-function-page
layout) but not the *byte semantics* — those need RE.

The plan, three RE strategies (scripted SysEx / forward-RE test banks /
create-on-HW + diff), per-parameter checklists, the corpus analysis, and the
full toolkit are in **`docs/re_procedures/krz_program_re.md`**. New tools:
`tests/re_banks/krz_reader.py`, `gen_krz_program_re.py`, `krz_sysex_probe.py`.
Start with the **amp envelope** (`KRZ_ENVLOC` bank, no MIDI needed). The 64 MB
K2000 sample-RAM ceiling is already enforced (`convert.py` clamp + splitter).

Resolution strategy + open questions: `docs/RESOLUTION_NOTES.md` §KRZ-PROG.

---

## KRZ: converted banks load but emit NO SOUND — RESOLVED (2026-06-14)

Converted KRZs (ABASBASS / BLKSAW / SF2SET) loaded on the K2000R and created
their presets, but **played silent**, while pre-existing soundsets played fine.
Root-caused against KurzFiler source (`~/git-repos/kurzfiler`) +
ground-truth dumps of real RAM-sample soundsets (a third-party `soundset 002`). The
sample/keymap/program *framing* was already byte-correct; the bugs were all in
**sample header field values** the program-only test banks never exercised:

1. **Soundfilehead.flags = `0x40` → must be `0x70`.** This is THE silence cause.
   `0x40` is needsLoad alone; a playable RAM sample needs the `0x10`+`0x20`
   playback-enable bits too (`LoadWaveMethod` always writes `0x70`). `0x40` loads
   the sample but produces no output.
2. **KSample object `flags` = `0x40` → must be `0`** (bit0 = stereo; `0x40` is
   meaningless) and **`baseID` = obj_id → must be `1`** (every real soundset).
3. **Keymap entry `tuning` double-counted the per-key transposition.** Old:
   `100*(root−12−key)` for every key — but the K2000 already transposes each key
   from the sample rootkey + `centsPerEntry=100`, so high keys hit −72 semitones
   (out of range → also silent). Fixed to a *constant* per-zone offset
   `100*(R_sample − R_zone) + fine_tune` (0 in the common case).
4. **`altSampleStart`** was loopStart → must equal `sampleStart` (real files).
5. **`maxPitch`** formula corrected to `100*root + 1200*log2(48000/sr)` (the
   48 kHz transpose ceiling; RE'd from soundset 002).

Fix in `writers/krz_writer.py` (`_write_sample_object`, `_build_keymap_entries`,
`_compute_max_pitch`). Verified structurally identical to real soundsets with
the new `krzdump.py` reader. **HW-CONFIRMED 2026-06-14:** ABASBASS_01.img loaded
on the K2000R via Gotek — all 5 presets play sound. See `docs/RESOLUTION_NOTES.md`.

---

## Aural-comparison fidelity (2026-06-13) — see `docs/aural_notes.md`

By-ear A/B of converted E4XT presets vs MPC originals.

**Implemented (no RE):** LFO rate curve (§C), root-from-WAV-unity / +36 fix
(§E/§F), filter-env always written (§O), S&H→Hemi-quaver (§Q), ODS mapping (§N).

**Implemented from RE_SUITE2 hardware data (2026-06-14); verified on the E4XT
via `VERIFY_emu.hda`:**
- **Voice key-window (§G) — DONE + HW-CONFIRMED.** `vpar[14]`=key low,
  `vpar[17]`=key high (were 0/127 = C-2..G8); writer sets them from each voice's
  min/max zone key. HW: C2–C3 sample → B1↓ silent, C2–C3 sound, C#3↑ silent.
- **Band-stop → Swept EQ 1-oct (§K/§L) — DONE + HW-CONFIRMED.** `vpar[58]=0x20`,
  `vpar[60]`=freq (cutoff law), `vpar[61]`=gain where **gain_dB=(byte−64)×0.375**
  (byte 0=−24 dB cut). MPC band-stop (15-18) → 0x20, cut depth −12..−24 dB from
  resonance. HW: band-stop preset reads as Swept EQ cut.
- **Triangle phase (§S) — DONE + HW-CONFIRMED.** E4XT triangle rises first;
  MPC falls first → writer negates a triangle LFO's cord amounts (all dests).
  HW: triangle LFO→pitch (rate 0.08 Hz) sweeps down first.

- **Tempo-synced LFO rate (§D/§P) — DONE (rate-based).** The MPC `<Sync>` index→
  division table is now known (Jan, 2026-06-14, full table in `xpm_parser
  _MPC_SYNC_DIV`). The MPC ignores `<Rate>` when synced (stuck at ~0.5 ≈ 2 Hz =
  the bug). Fix: `xpm_parser` reads `<Sync>` and sets the LFO rate to the
  division's frequency at a reference tempo (`_mpc_sync_hz`).
  **Why not the clock cord (confirmed by the EOS 4.0 manual p.260):** the clock
  source has exactly **six divisions** (dbl-whole/whole/half/quarter/8th/16th =
  the ids 0x90–0x95) — no dotted/triplet/multi-bar — and the clock→LFO-Trigger
  cord only **resets** the LFO ("the LFO wave resets to zero every time the clock
  wave goes low … if the two rates are far apart, the waveform … will be mildly
  or radically altered").  So EOS does **not** tempo-follow even straight
  divisions (unlike the Proteus 2000's 25-division synced-LFO mode, which EOS
  lacks).  The BPM also lives in the MPC *project*, not the XPM.  So a fixed rate
  at a reference tempo is the faithful best — right speed for all 20 divisions,
  robust at any E4XT tempo; a clock cord would add no follow and would *worsen*
  the wave at off-reference tempos.  (RE'd clock ids kept in
  `docs/re_procedures/re_suite2.md`.)  Configurable via **`--lfo-sync-bpm`**
  (default 120, the MPC/DAW new-
  project default); convert.py prints a note when synced LFOs are converted;
  per-tempo lookup table in **`docs/lfo_sync_rates.md`** (60–200 BPM).

**Open — need data:** **SawDown** waveform (§B); **envelope-time calibration** (§J).

### Enhancements (no behaviour change)

**Parser performance pass — DONE 2026-07-29.** Benchmarked all input parsers
over real files; the cost was not spread out but concentrated in a handful of
per-sample Python loops plus two repeated directory walks. Every change is
byte-identical **except** the `_find_wav` glob-vs-literal fix noted at the end,
which is intentional. Full writeup in `docs/RESOLUTION_NOTES.md` §PARSERPERF.
- **`_stereo_to_mono` was 99.5% of XPM/SFZ/EXS24 parse time** (40M `struct`
  calls for 31 samples) — now `audioop` + `array` fallback. Reached by six
  parsers via `load_wav`, so this one fix carries xpm/sfz/exs24/pgm/talsmpl/
  sampledir. Supersedes CR-16's "avoided audioop" note above.
- **AIFF 24-/32-bit downscale**: both are "keep the top two bytes as a BE
  int16" (the sign correction and the arithmetic shift cancel — proof in the
  docstring), so a strided copy + one byteswap replaces an unpack/pack loop.
- **KRZ `_extract_pcm`**: per-byte-pair swap loop → `array.byteswap()`.
- **O(n²) sample dedup** in `sf2_parser`/`gig_parser`: `{s.name for s in
  bank.samples}` was rebuilt for *every zone*; now an incremental set.
- **De-duplicated** gig's second stereo-downmix copy into the shared helper
  (CR-13/CR-17 lesson: duplicated codecs drift).
- **WAV 24-bit** (`_convert_24_to_16`, the little-endian twin of the AIFF
  path) was a *second* missed loop — 87% of SFZ/EXS24 time. Caught only by
  re-measuring after the first fix, when those two formats showed no gain.
- **Directory walks**, a different class of hotspot: `exs24._find_indexed`
  (97% of exs24 time) and `xpm._find_wav` both re-walked whole trees per
  lookup; now a first-occurrence index memoized per directory.
- **One deliberate behaviour change** (Jan-confirmed): `_find_wav` matched
  sample names as glob *patterns*, so `Bass[12].wav` could resolve to
  `Bass1.wav`. Lookups are now literal.

**DONE 2026-06-11:** CR-13, CR-14, CR-15, CR-17, and the CR-18 cord-builder —
fixed & pipeline-verified (details in `docs/RESOLUTION_NOTES.md §CR`).

- **CR-16 Perf — DONE 2026-06-11 (all four; each byte-identical).**
  - **#1 gig decode:** 24-bit→16-bit is a bulk `bytearray` slice (drop the low
    byte of each frame; ~200× faster), 8-bit→16-bit a bulk `bytes.translate`
    (sign-flip) — were per-sample `struct.pack_into` loops. (Stereo downmix was
    already `array`-based.)
  - **#2 `write_e4b` memory:** streams each sample's header+PCM straight to disk
    (was ~5 PCM copies via join/concat → ~1×).
  - **#3 resampler:** bulk `array('h')` de/encode (~2×/1.3×; per-element float
    math is the floor without numpy — the earlier ~30-50× estimate was wrong).
  - **#4 ISO/HDA:** copy embedded files in 1 MB chunks + pad separately (was
    read-whole-file then build a 2nd padded copy).
  - *(Avoided `audioop` — byte-identical to the manual loops but deprecated/
    removed in Python 3.13.)* **Superseded 2026-07-29 — see "Parser
    performance pass" below.** CR-16 optimized only the *gig* decode and left
    `xpm_parser._stereo_to_mono` a per-frame `struct` loop; profiling later
    showed that one function was **99.5%** of XPM/SFZ/EXS24 parse time, since
    all six sample-loading parsers reach it through `load_wav`. `audioop` is
    now used there *with* a byte-identical `array` fallback, which answers the
    3.13 objection instead of paying 100x for it.
- **CR-18 — DONE 2026-06-12.**
  - **#1 `Envelope` dataclass — DONE.** `VoiceLayer` now stores `amp_env` and
    `filter_env` as `Envelope(attack, decay, sustain, release)` with
    backward-compatible `env_*`/`filter_env_*` property accessors, so every
    existing parser/writer field access keeps working.  Round-trip across XPM /
    SFZ / SF2 / EXS → E4B shows **zero feature diffs**.
  - **#2 EXS24 walker unify — N/A as written; replaced by concrete EXS fixes.**
    The premise ("validate a merged classic+v11 walker on real classic files")
    is unsatisfiable: the local corpus is **1717 v1.1 + 0 classic** `.exs`
    files, so the classic path can't be exercised at all.  Investigating it
    instead surfaced three real v1.1 bugs, now fixed in `exs24_parser.py`:
    1. **`0x40000101` flag variant rejected.** 14 files (Samples-/Drums-From-
       Mars packs) set bit `0x40000000` on the magic AND every chunk type, so
       the magic read `0x40000101` and the parser raised "Not a valid EXS24".
       Now masked off (`_V11_TYPE_FLAG`) at dispatch + every chunk compare.
    2. **Long-common-prefix multisamples collapsed to 1 sample.** `_safe_name`
       truncated the sample-cache key to 16 chars, so 36 `DX100 Classic Bass-*`
       zones all mapped to one sample.  Parser now keeps the full stem
       (E4B maps zones by index, not name; 16-char limit applied at write).
    3. **`.aif` references with `.wav` twins didn't resolve.** `load_wav` is
       WAV-only; the ancestor index now keeps a stem→`.wav` fallback so an
       `.aif` reference lands on its sibling WAV copy.
    All 14 formerly-rejected files now round-trip ERROR→PASS through E4B.

---

## TAL writer: keytracked external-sample RANGE zones play silent (OPEN)

**Status:** open — stashed 2026-06-11.  Per-note single-key zones (`track="0"`)
work perfectly in TAL-Sampler (drum kits + melodic per-note multisamples,
confirmed in tune).  A **range** zone (`low≠high`, `track="1"`, one external WAV
keytracked across keys) is **silent**, even at its root key.

**Investigated, not solved:**
- The sample has audio; `track="0"` plays it; `track="1"` silences it.
- Progression across attempts: keytracked → `-48` semitones off (wrong root) →
  added WAV `smpl` MIDIUnityNote (TAL keytracks off the WAV root) → crash → after
  `endsample = n_frames-1` fix → silent → after removing the `smpl` LOOP (kept
  root) → still silent (Jan, last test before stashing).
- **No real TAL preset in Jan's library keytracks an external sample over a
  range** — they all use per-note single-key samples or ROM oscillators
  (`isromsample=1`).  Possible TAL limitation or a deeper resampler interaction.

**Fixes that DID land from this (keep):** `<programs>` wrapper, layer bin-packing,
`track`/`stereoinverse` explicit for one-shots, neutral per-sample filter, CRLF,
`endsample=n_frames-1`, WAV `smpl` root note.

**Pragmatic fallback if not solved:** emit range zones as `track="0"` (plays at
native pitch across the range — audible, not pitch-shifted) instead of silent;
or split a ranged source zone into per-key single-key zones.  Decide with Jan.

---

## E4B writer: amplitude envelope — RESOLVED (2026-06-08)

The full 6-stage amp envelope (`PZT[0:12]`) is now written and parsed. The
decay rate byte was the last unknown; it is **`PZT[4]`**, confirmed on hardware:

- `AMPENV_SETME.E4B` (E4XT-saved baseline) pins the 12-byte layout.
- `AMP_DECAY_CAL.E4B` isolates it — across 6 voices only `PZT[4]` changes
  (`08 10 18 20 30 40`), and the same sweep calibrated rate→time (see below).

The earlier corpus-RE guess (vpar[0]=attack / vpar[1]=sustain) was wrong: those
bytes are 0 in every hardware-saved bank. The amp envelope lives entirely in the
`PZT[0:12]` rate/level block. See `docs/RESOLUTION_NOTES.md` §1.

**`vpar[42]`** is now resolved — it is per-voice Chorus Amount (see below).

---

## E4B: filter-envelope reproduction — RESOLVED (2026-06-09)

The 6-stage filter envelope (`PZT[14:26]`) is written, round-trips, and is now
hardware-confirmed to sweep on the E4XT. Three things were resolved:

- **Routing (Gap 0):** the envelope shape alone is inert — it reaches the cutoff
  through the **FilterEnv→FilterFreq mod cord** (E4XT "Cord 05", default 0 %).
  Our KT voices wrote an all-zero mod matrix → no sweep (all `FLT_DECAY_CAL`
  presets sounded identical). Fixed: `e4b_writer` writes the EOS default cord
  table for filter-env voices and puts `filter_env_amount` (signed) in the cord
  amount byte `mod[30]`; `e4b_parser` mirrors it. Hardware-confirmed.
- **Calibration (Gap A):** measured `FLT_DECAY_CAL` on the E4XT — the filter
  Decay-1 rate→time follows the **amp curve** (low rates match exactly; highs
  noisy from the centroid metric). Writer already reuses `_fenv_rate()` → correct.
- **Source mapping (Gap B):** XPM, SFZ, SF2, GIG, EXS24 all set
  `filter_env_amount` → Cord 05. Details in `docs/RESOLUTION_NOTES.md` §17.

Cord amount encoding confirmed from `B.010-CordAmountTest.E4B`:
`amount = round(pct/100 × 127)` signed (+100 %=127, −100 %=−127), cord layout
`[src, dst, amount, flag]`. Matches the writer/parser exactly.

---

## XPM parser: envelope values 0–1 → seconds — RESOLVED (2026-06-09)

`xpm_parser` previously passed `VolumeAttack/Decay/Release` and the `Filter*` env
times through as seconds, but MPC stores them as normalised **0.0–1.0** controls.
Measured on the **MPC One** (recorded `XPM_VOL_DECAY` + `XPM_FLT_DECAY`, analysed
with `analyze_envelope_recording.py`): steep exponential
`seconds ≈ 0.00079·e^(9.78·value)`, and the filter envelope confirmed to share the
**same exponent** (one curve for all segments). Applied as `_xpm_env_to_seconds()`
in `xpm_parser.py`. Details in `docs/RESOLUTION_NOTES.md` §18.

---

## E4B writer: `vpar[42]` = Chorus Amount — RESOLVED (2026-06-08)

`vpar[42]` is the per-voice **Chorus Amount** (Voice/Tuning page), UI 0–100 %
mapped linearly to byte 0–127 (`round(pct/100*127)`). Confirmed on the E4XT
(commercial-bank reads + a 25/50/75/100 % → 32/64/95/127 sweep) and wired into
`VoiceLayer.chorus_amount`, `_build_voice()`, and `_parse_voice()`. Details in
`docs/RESOLUTION_NOTES.md` §13.

**Note:** Chorus *stereo width* is a separate, still-unlocated byte (was 100 %
in every sample, so it never varied). Only worth chasing if a source format
ever needs per-voice width.

---

## E4B writer: `_fenv_rate()` calibration — RESOLVED (2026-06-08)

Calibrated from 6 Decay-1 decay-to-silence measurements on the E4XT
(`AMP_DECAY_CAL.E4B`). The earlier `round(80.0 / (t + 0.01))` formula had the
direction backwards; hardware shows **rate 0 = fastest (instant), higher =
slower** (rate 127 ≈ 47 s):

| rate | time   | rate | time    |
|-----:|-------:|-----:|--------:|
|    8 | 0.034 s|   32 | 0.198 s |
|   16 | 0.098 s|   48 | 0.454 s |
|   24 | 0.169 s|   64 | 1.225 s |

Log-linear fit (R²=0.96): `time_s = 0.0310 · e^(0.0581 · rate)`. Applied as
`_ENV_RATE_A`/`_ENV_RATE_K` + `_fenv_rate()`/`_fenv_seconds()` in
`writers/e4b_writer.py`, with the matching inverse `_fenv_rate_inv()` in
`parsers/e4b_parser.py`. Details in `docs/RESOLUTION_NOTES.md` §2.

---

## E4B writer: E4XT filter type bytes — RESOLVED (2026-06-08)

All 21 EOS filter `vpar[58]` bytes reverse-engineered from
`B.005-FILTERTYPES.E4B` (one preset per filter type, set on hardware and saved).
Encoding: `byte = group_base | variant`. Full table in
`writers/e4b_writer.py:_E4XT_FILTER_BYTES` and `docs/E4B_FORMAT.md` §4.4
(LP `0x00`, HP `0x08`, BP `0x10`, Swept `0x20`, Phaser `0x40`, Flanger `0x48`,
Vocal `0x50`, Morph `0x60`, Peak/Shelf `0x68`).

Applied: MPC Vocal-formant types now map to the E4XT Vocal filters (`0x50`/
`0x51`) instead of LP; `e4b_parser` reverse-map updated. Swept/Phaser/Flanger/
Morph have no MPC-XPM source equivalent, so they're documented but not reachable
from current inputs (reverse-mapped lossily when parsing hardware banks).

---

## GIG→E4B: `fine_tune` not written to zone entry

**Status:** parser side complete; writer side blocked on hardware RE.

The GIG parser now extracts per-zone `fine_tune` in cents (DLS `sFineTune`,
signed 16-bit) and stores it correctly in `ZoneMapping.fine_tune`. However
`_zone_entry()` in `writers/e4b_writer.py` does not write this value — the
byte offset for fine_tune in the 22-byte secondary zone entry has not been
reverse-engineered yet.

**To resolve:** on the E4XT create two otherwise identical presets with
fine_tune = 0 and fine_tune = +50 cents, save as E4B, binary-diff the zone
entry bytes. The changing byte(s) are the field.

---

## GIG→E4B: per-zone volume (gain_db) not written to zone entry

**Status:** parser side complete; writer side blocked on hardware RE.

DLS `lAttenuation` (millibels) is parsed and stored in `ZoneMapping.volume`
(dB). `_zone_entry()` in `writers/e4b_writer.py` does not write it — the
byte offset in the 22-byte secondary zone entry is unknown.

**To resolve:** same approach as fine_tune above — diff presets with
differing per-zone volume (e.g. 0 dB vs −12 dB).

---

## ~~Sample loader: AIFF (`.aif`/`.aiff`) not decoded~~ (ALREADY IMPLEMENTED — entry was stale)

**Found stale 2026-08-31** while looking for unblocked non-hardware work: this
entry described a gap (opened 2026-06-12) that turns out to already be fully
closed in the code, just never updated here and never independently tested.
`parsers/xpm_parser.py::_load_aiff` reads `FORM/AIFF` and `FORM/AIFC`, `COMM`
for rate/channels/bit depth (including the 80-bit extended-float rate field),
`SSND` for the PCM payload (8/16/24/32-bit, byte-swapped to LE16; AIFF 8-bit
correctly treated as SIGNED, unlike WAV's unsigned-centred-at-128), AIFC
`'sowt'` (already-LE, no swap) with other AIFC compressions correctly
refused rather than mis-decoded, and `MARK`+`INST` for loop points and base
note — everything this entry asked for, including the loop-point parity
with WAV's `smpl` chunk. `load_wav` already dispatches `.aif`/`.aiff` (any
case) to it by suffix.

**What WAS missing: test coverage.** No test file exercised `_load_aiff` at
all. Added `tests/test_aiff_loader.py` (10 tests): plain 16-bit decode,
8-bit signed-not-unsigned, 24-bit downscale, AIFC `sowt`, AIFC unsupported
compression refused, `INST` base note, forward and ping-pong loops from
`MARK`+`INST`, a non-AIFF file refused, and `load_wav`'s suffix dispatch for
all four case variants. All pass against the existing code; two loop-point
tests initially failed against my OWN test fixture (a missing per-marker
word-alignment pad byte inside the `MARK` chunk body), not the parser --
confirms the loader's chunk walk is correct rather than merely
"consistent with my first guess at the fixture."

---

## EXS24 parser: multi-velocity layers — first layer only

**Status:** known limitation; positional zone mapping.

EXS24 v1.1 instruments can have multiple velocity layers per key zone. The
current parser uses a positional zone-mapping approach and only reliably
captures the first velocity layer. Additional layers may be silently dropped.

Note: the tested corpus (101 From Mars, Acid From Mars, 2600 From Mars) uses
GROUP chunks exclusively for L/R stereo separation — not for velocity layers.
All observed zones have `vel_hi=127` and no velocity-split. True velocity-layered
instruments may exist in other packs but were not found in this test set.

**To fix:** implement a proper velocity-aware zone grouping pass in the EXS24
parser, similar to the `vel_to_voice` grouping logic in `xpm_parser.py`.

---

## E4B writer: LFO modulation routing (partial)

**Status:** E4B-side LFO1+LFO2 encoding + all LFO→{Pitch,Filter,Q} cords +
round-trip DONE (2026-06-10); Key/Vel→Filter DONE (2026-06-09); **input-format
LFO source mapping DONE for XPM / SFZ / SF2 (2026-06-10)**. **Only remaining gap:
GIG LFO mapping** (deferred — needs a test `.gig` + libgig 3ewa LFO byte offsets).
See the DONE blocks below.
**Wanted (Jan, 2026-06-09):** at least **LFO→Pitch, LFO→Filter-Freq,
LFO→Filter-Q (resonance)**, **Key→Filter-Freq (filter keyboard tracking)**, and
**Velocity→Filter-Freq** — written when the input format actually provides them.

Most input formats carry these routings: XPM (`LfoPitch`, `LfoCutoff`,
`LfoVolume`, `LfoPan`, **`FilterKeytrack`**, **`VelocityToFilter`** + `<LFO>`
Rate/Type), SF2 (`modLfoToPitch`, `modLfoToFilterFc`, `modLfoToVolume`,
`vibLfoToPitch`, default **Velocity→FilterCutoff** modulator), SFZ (`pitchlfo_*`,
`fillfo_*`, `amplfo_*`, **`fil_keytrack`**, **`fil_veltrack`**), GIG (LFO1/2/3 →
pitch/filter/amp, **`VCFKeyboardTracking`**, **`VCFVelocityScale`**), EXS24 (LFO
block, **`FILTER1_KEYTRACK` id 0x2e**, velocity-to-filter). We currently write
none of it — KT voices get an all-zero mod table, NT voices the fixed `_MOD_TMPL`.

**Cord format decoded** (`[src, dst, amount, flag]`, amount `= round(pct/100 ×
127)` signed, UI cord N = storage slot N — see `RESOLUTION_NOTES.md` §4.3/§15).
**Ids decoded 2026-06-09:** sources LFO1=`0x60`, Velocity=`0x0C`, Key=`0x08`,
FilterEnv=`0x50`; dests Pitch=`0x30`, Filter-Freq=`0x38`. `_MOD_TMPL` already
carries the cords at amount 0: slot 2 LFO1→Pitch (`mod[10]`), slot 4
Velocity→Filter (`mod[18]`), slot 5 FilterEnv→Filter (`mod[22]`, done), slot 6
Key→Filter (`mod[26]`).

**DONE 2026-06-09:** **Key→Filter (cord 06)** and **Velocity→Filter (cord 04)** —
`VoiceLayer.filter_keytrack` / `velocity_to_filter` (signed ±1 → `mod[26]`/
`mod[18]`), read back by the parser, mapped from GIG (`VCFKeyboardTracking`,
`VCFVelocityScale`, real data verified), SFZ (`fil_keytrack`/`fil_veltrack`), XPM
(`FilterKeytrack`/`VelocityToFilter`), EXS24 (`FILTER1_KEYTRACK`, scaling
unverified). SF2 skipped (velocity→filter is a fixed default modulator).

**DONE 2026-06-10 — LFO1 + LFO2 encoding & all LFO routing cords (E4B side).**
RE'd from `B.011-LFO1 settings.E4B` (`E4B_FORMAT.md` §4.2/§4.3,
`RESOLUTION_NOTES.md` §15); full E4B→E4B round-trip, validated against the
hardware bank:
- `VoiceLayer.lfo{1,2}_{rate,shape,delay,variation,sync}` (all `Optional`,
  `None` = leave EOS default so non-LFO voices stay byte-identical). LFO2 is the
  `PZT[50:54]` +8 mirror of LFO1 `PZT[42:46]`.
- **Rate in Hz** — byte↔Hz calibrated from the E4XT menu readout (0=0.08, 64=4.12,
  127=18.01 Hz); log-quadratic fit `models.common.lfo_rate_hz_to_byte` /
  `lfo_rate_byte_to_hz` (3-point, refineable with intermediate readouts).
- **Sine=1 confirmed** (`LFO1+2 SINE` preset: `PZT[43]`+`PZT[51]`=01).
- Routing cords: `lfo1_to_pitch` (default cord 02 `mod[10]`); `lfo1_to_filter`
  (`0x60→0x38`), `lfo1_to_filter_q` (`0x60→0x39`), `lfo2_to_pitch` (`0x68→0x30`),
  `lfo2_to_filter` (`0x68→0x38`), `lfo2_to_filter_q` (`0x68→0x39`) written into
  free cord slots 8+. New ids: **Filter-Q dest `0x39`**, VEnvDcy `0x4A`, LFO2~
  `0x68`/LFO2+ `0x69`. LFO1~`0x60` doubly confirmed; **Lag0=`PZT[57]`,
  Lag1=`PZT[59]`**.

**DONE 2026-06-10 — input-format LFO source mapping (XPM / SFZ / SF2).** The
shared rate curve lives in `models/common.py` (`lfo_rate_byte_to_hz` /
`lfo_rate_hz_to_byte` / `lfo_knob_to_hz` / `lfo_pitch_depth_to_amount`), used by
the writer, the E4B parser and all source parsers:
- **XPM** (`xpm_parser._xpm_lfo_shape`): single keygroup `<LFO>` → LFO1.
  `<Rate>` knob 0–1 → Hz via `lfo_knob_to_hz`; `<Type>` → shape; `<Reset>` →
  Sync (True=key-sync); `LfoPitch`→`lfo1_to_pitch`, `LfoCutoff`→`lfo1_to_filter`.
  Emitted only when a routing is non-zero.
- **SFZ** (`sfz_parser._sfz_lfo_wave`): v1 `pitchlfo_*`→LFO1 / `fillfo_*`→LFO2
  (sine); v2 `lfo01_*`/`lfo02_*` with `_pitch`/`_cutoff` targets + `_wave`.
- **SF2**: triangle Mod-LFO (gens 22/5/10) → LFO1, Vib-LFO (gens 24/6) → LFO2;
  absolute-cents freq → Hz (`8.176·2^(c/1200)`).

**Remaining — GIG LFO mapping (deferred):** needs a test `.gig` to validate
against, plus the libgig 3ewa LFO1/2/3 (amp/filter/pitch) byte offsets — the
current `_decode_3ewa` only reads EG1/EG2/VCF. Other open sub-items: LFO→Amp/Pan/
VEnv dests if a format needs them; cord-amount↔musical-unit absolute scaling is
proportional pass-through (unverified — see the dedicated issue below); only the
bipolar `~` sources are wired (the musical default).

---

## E4B: Mod-cord depth scaling — RESOLVED (2026-06-12, measured + applied)

**Status:** **RESOLVED 2026-06-12** — all five cords measured AND applied.
`models/common.py` now carries the hardware constants (`LFO_PITCH_FULL_CENTS=1593`,
`FILTER_ENV_FULL_CENTS=4383`, `VEL_FILTER_FULL_CENTS=9120`, `KEY_FILTER_OCT_PER_OCT
=0.713`) + helpers `velocity_filter_depth_to_amount` / `key_track_to_filter_amount`.
Cents-based filter mods (SF2 + SFZ filter-env & LFO→filter) are auto-corrected by
the 9600→4383 flip; SFZ velocity/keytrack go through the new scalings; XPM/GIG/EXS
stay proportional passthroughs (their inputs are fractional knobs/flags, not
absolute units).  RE methodology preserved in RESOLUTION_NOTES §19 for re-runs.
**Bonus bug fixed:** Velocity→Filter shipped the wrong polarity (`Vel<` subtract
→ now `Vel+` add, 0x0A).

We RE'd *which* cord routes *where* and the amount encoding (`round(depth×127)`,
±127=±100 %), and have now **measured** what each amount does in real units —
all four filter cords agree on one `0x38` sensitivity (3.65 oct/source-unit):

| Cord | Code constant | Status |
|---|---|---|
| LFO→Pitch | `LFO_PITCH_FULL_CENTS=1593` (`models/common.py`) | **MEASURED**: 100 % = ±1593 c (±16 st), linear |
| LFO→Filter-Freq | proportional 0–1 | **MEASURED**: 100 % = ±3.65 oct (noise take, σ0.16); apply `oct/3.65` |
| FilterEnv→Filter | `FILTER_ENV_FULL_CENTS` was 9600 | **→ reset to ≈4383** (shared 0x38 sensitivity = ±3.65 oct, ~2.2× too high) |
| Key→Filter | `filter_keytrack` ±1 | **MEASURED**: 100 % = 0.713 oct/oct (~0.71:1, NOT 1:1); r=0.9994 |
| Velocity→Filter | `velocity_to_filter` ±1 | **MEASURED + polarity fixed** (`Vel+` 0x0A): 100 % = ~7.6 oct over vel 0→127, linear r=0.9999 |

**RE strategy (full procedure: `docs/re_procedures/mod_cord_depth.md`; fix
recipe: `RESOLUTION_NOTES.md §19`):** drive the destination with a **square**
LFO at a known cord amount so the parameter hops between two steady states — the
gap between them is `amount/100` of full-scale. Sweep 25/50/75/100 % to check
linearity and pin each constant.

- Generate: `python3 tests/re_banks/gen_mod_depth_test.py` → `MOD_DEPTH_CAL.E4B`
  /`.iso` (10 presets: PitchDepth×4, FiltDepth×4, KeyTrk 100, VelTrk 100).
- Record each sustained note (≥3 LFO cycles; KeyTrk play C1..C6; VelTrk vel
  1/64/127).
- Analyse: `python3 tests/re_banks/analyze_mod_depth.py <rec.wav> --mode
  pitch|filter` → low/high state, peak-to-peak cents/octaves, one-sided depth
  (validated against a synthetic ±100 c signal).
- Apply: set `LFO_PITCH_FULL_CENTS` to the measured 100 % one-sided cents; add an
  `lfo_filter_depth_to_amount()` for the cutoff octaves-per-100 %; reconcile
  `FILTER_ENV_FULL_CENTS`; verify Key→Filter 100 % ≈ 1:1.

---

## XPM parser: MPC binary `.pgm` — MPC1000/2500 + MPC60 DONE; MPC2000 open

**MPC500/1000/2500 and MPC60 `.pgm` are implemented** in `parsers/pgm_parser.py`
(`parse_pgm` dispatches by magic; wired into `convert.py`):
- **MPC1000/2500** (`MPC1000 PGM 1.00`): 64 pads → voices at their MIDI notes; 4
  per-pad samples → velocity layers; amp env / filter1 / mixer mapped. Validated
  against all 8 From Mars kits + a synthetic kit (vel-split/filter/tuning/pan/
  play-mode); non-MPC1000 `.pgm` (e.g. `BD12`) rejected cleanly.
- **MPC60** (byte 0 = `0x07`, 2026-06-08): sample-name list → external 12-bit
  `.SND` samples decoded to 40 kHz mono (verified clean decaying drum envelopes,
  PCM round-trips through E4B identically). Samples map to sequential keys from
  C1; per-pad note/vol/pan/tuning params not yet decoded (single test file).

Both informed by ConvertWithMoss (`format/akai/mpc1000`, `format/akai/mpc60`),
independent impl + attribution. The MPC60 `.PGM`/`.SND` container was RE'd from a
real kit (ConvertWithMoss only reads the MPC60 *SET* variant).

**DONE — MPC2000 / MPC2000XL (2026-06-08):** implemented in `pgm_parser.py`
(`_parse_mpc2000`, magic `0x07 0x04`). Header → sample-name list, 64 × 25-byte
pads (+6-byte mixer) + 64-byte note table; each pad's `sampleNumber` → a
key-tracking voice at its MIDI note, with tune/level/pan/envelope mapped.
Samples are standard external `.WAV` (not 12-bit). Validated against an Akai
MPC2000XL factory CD (AMBIENCE_SET — 13 sounds, correct GM notes, E4B written).
MPC2000 and MPC2000XL use the **same** `.pgm` layout (one parser).

**Still open — MPC3000 `.pgm`:** ConvertWithMoss's `mpc2000` package also reads
MPC3000 (`0x07 0x00`, `byte2==0x00`) — but that magic collides with our MPC60
`.PGM` (also `0x07 0x00`); they'd need a body-level discriminator. Low priority
(no MPC3000 test file). Also possible: read MPC2000 `.iso`/disk images directly
(currently extract with `7z` first), and decode the MPC60 PGM per-pad params.

**DONE — MPC60 SET + floppy (`.set` / `.img`), 2026-06-08:** implemented in
`parsers/mpc60_parser.py` (wired into `convert.py`). The intact "800K" SET
(magic byte 0x02) is the standard ConvertWithMoss layout: pads at 0x05 (0x3B
each, name@+0, start@+18, length@+22 in frames), 12-bit sample block from 0xBFF
(2 frames per 3 bytes). Each pad → a sample at sample_block[start:start+len];
32 pad slots are de-duplicated to the unique sounds and mapped to sequential
keys from C1. `.img` floppies are read directly (built-in FAT12 reader extracts
the `.SET`). **Validated** against the *Akai MPC60 to WAV* reference decoder —
decoded PCM correlates 0.99 (tonal) with its WAVs (the residual is the tool's
per-sample gain, which the E4XT applies itself).

The earlier confusion was that the user's first disks were **720K copies of
800K originals** (truncated → magic byte 0x00, garbled header) — those are
flagged and skipped; the intact 800K images decode perfectly. Truncated tails
on individual samples are handled gracefully (clamped).

---

## XPM→E4B: TuneCoarse / TuneFine dropped entirely (no transpose, no detune)

**Status:** **RESOLVED 2026-06-13.**

All three E4XT per-voice tuning bytes are now RE'd and implemented:
- `vpar[34]` = Key Transpose (keyboard pitch remap, signed byte semitones)
- `vpar[35]` = Coarse Tune (sample repitch, signed byte semitones) ← RE'd 2026-06-13
- `vpar[36]` = Fine Tune (signed byte in 1/64-semitone units; cents × 64/100)

XPM `TuneCoarse` (inst + layer summed) → `ZoneMapping.coarse_tune` → vpar[35].
XPM `TuneFine` (inst + layer summed, cents) → `ZoneMapping.fine_tune` → vpar[36]
with proper unit conversion.

The detuned-stack "split" character from detuned stacked instruments is now
correctly written. Feature-demo banks can be rebuilt to reflect this.

**⚠ Demo-bank rebuild pending:** `DETUNESPLIT`, `WIDEDRONE`, `RISINGSPLIT`
need a rebuild to pick up the new tuning output.

---

## XPM parser: long-common-prefix sample names collide on 16-char truncation

**Status:** **RESOLVED 2026-06-12.** `_safe_name(..., tail=True)` keeps the
distinguishing *tail* for sample names (preset/bank names still head-truncate).
Verified: the detuned-stack split preset samples keep distinct `…_C1_A`-style names.

When many samples share a >16-char common prefix, `_safe_name`'s 16-char
truncation destroys the distinguishing suffix and the dedup counter replaces it
with a meaningless index. `the detuned-stack split preset.xpm` references
`Inst-Pad-LazSp-UniPanBass_C1_A … _C4_C` (26-char shared prefix) → all become
`Inst-Pad-LazSp-U`, `…-1`, `…-2`, … (Jan: "S222-S233 often have the same
names"). They stay unique but lose the C1_A/C2_B identity and look like
duplicates on the E4XT.

The EXS24 parser already solved the analogous problem (RESOLUTION_NOTES §CR-18:
keep the full stem, map zones by index, apply the 16-char limit only at write
with a *suffix*-preserving scheme). Apply the same to `xpm_parser` /
`_safe_name`: truncate keeping the tail (or hash the prefix) so `…C1_A` vs
`…C2_B` stay distinguishable.

---

## XPM→E4B: `KeygroupWheelToLfo` ignored → LFO modulation always at full depth

**Status:** **RE COMPLETE 2026-06-13 — implementing faithful gating.**
RE bytes from `B.013- RE_SUITE CrdAmt.E4B` (hardware save):
- **ModWheel source id = `0x11`** (Cord 00 of saved MW PITCH: `src=0x11 dst=0x30`;
  also the default `src=0x11 dst=0xaa +13%` cord 03 Jan flagged). `0x10` = Pitch
  Wheel (adjacent in the EOS source list).
- **Cord-N-Amount destination id = `0xA8 + N`** (linear): `C02Amt`=`0xAA` (cord 09
  of saved MW LFO1), `C08Amt`=`0xB0` (cord 09 of saved MW LFO2). Range `0xA8..0xBF`
  for cords 0..23 — the manual's 24 consecutive "Cord 0-23 Amount" destinations.

Cord layout reminder: 4-byte cords `src, dst, amt(signed byte), 0x00` at
voice[190:270]; amount is the single signed byte (`+127` = +100%).

**Faithful fix (in progress):** for each LFO→dest cord at slot N with intended
depth D and a voice `KeygroupWheelToLfo = Kw`:
  - set that LFO cord's static amount to `round(D * (1 - Kw))` (always-on part);
  - add a cord `src=0x11 (ModWheel), dst=0xA8+N, amt=round(D * Kw)` (wheel-added
    part) in a free slot.
At wheel 0 → cord N amount = `D*(1-Kw)`; at full wheel → `D` (programmed depth).
This generalises the interim `(1-wheel)` static scaling (which dropped the
wheel-controlled part entirely).

**Interim (superseded):** `xpm_parser` scaled static LFO depth by `(1 - wheel)`
so a 100%-gated LFO wrote near-silent instead of full-on.

The MPC program-level field **`<KeygroupWheelToLfo>`** (0–1, the UI "WHEEL→LFO"
amount) scales how much the mod wheel gates the LFO's modulation depth. At
`1.0` (100%) the LFO→Pitch / LFO→Filter / LFO→Vol routings contribute **nothing
at rest** and only reach their programmed depth as the wheel is raised.

Reported by Jan on `Bass-MS20 Antima Acoustik.xpm` ("too much LFO→Pitch"): it has
`KeygroupWheelToLfo=1.0`, `LfoPitch=0.055`, `LfoCutoff=0.291`, LFO rate ~5 Hz —
so on the MPC the vibrato is wheel-gated (silent until you push the wheel).

Known LFO cord src/dst (for picking the cords to gate): LFO1=`0x60`, LFO2=`0x68`;
dests Pitch=`0x30`, Filter=`0x38`, Q=`0x39`. ModWheel=`0x11`, CordNAmt=`0xA8+N`.

Related to the LFO routing work ([[E4B-LFO-routing]]) — this is the missing
"depth controller" layer on top of the already-working LFO→dest cords.

---

## Fixed (un-gated) LFO→Filter on MS-20 patches — aural check needed

**Status:** open (2026-06-13). **Blocked on:** Jan's by-ears check on the E4XT.

`FEATUREDEMO_02 P003 Bass-MS20 Antima-Patch` (= `Bass-MS20 Antima-Patch 2c.xpm`) plays its
LFO1→Filter at a **fixed** amount (cord 08 `0x60→0x38` = +42 ≈ 33%), not
wheel-gated. **This is faithful to the source:** the XPM has
`KeygroupWheelToLfo=0.0`, `LfoCutoff=0.33`, `LfoPitch=0` — so the MPC does not
wheel-gate it, and a real MS-20's MG→VCF LFO is always-on too. Confirmed in
phase-1 staging (cord 8 = +42, cord 9 empty) — not a repack loss.

Jan flagged it as "not 100%" and will **judge by ear** whether:
1. it's correct as-is (faithful fixed LFO — most likely), or
2. the fixed filter LFO is too strong → the `LfoCutoff → cord-amount` mapping
   needs a calibration constant (currently linear `amt=round(depth*127)`, no
   `LFO_FILTER_FULL_*` analogue to `LFO_PITCH_FULL_CENTS=1593`), or
3. he wants LFO→Filter wheel-gated regardless of `KeygroupWheelToLfo` (a
   deliberate deviation from the MPC source).

(Aside: cord 03 `ModWheel→C02Amt @16` on this voice is the EOS template default
sitting on an absent pitch LFO — gates a zero cord, audibly nothing. Could be
suppressed when LFO1→Pitch is 0, but that changes the hardware-extracted
`_MOD_TMPL` byte output — left as-is pending the same aural pass.)

---

## XPM parser: `RootNote=0` wrongly treated as non-transpose → mistuned

**Status:** **RESOLVED 2026-06-12; root source REFINED 2026-06-13.**  Option B
(wide-keygroup non-transpose) implemented.  **2026-06-13 (aural §E):** for a
tracking `RootNote=0` zone the root now comes from the sample's **WAV `smpl`
unity note** (`load_wav` reads it; `xpm_parser` uses it), falling back to the
keygroup low note only when the WAV carries no unity note.  This fixed the **+36
transpose** on Jupiter-Rising patches (lowest sample rooted at C1=36, but
lo_key=0).  Verified: the detuned-stack split preset now root_keys 36/48/60/72 (was 0).  See
`docs/aural_notes.md` §E/§F.

`xpm_parser.py:331` decides key-tracking from `smp_mode = (raw_root == 0)`. This
is wrong: `RootNote=0` is the MPC "root unset" sentinel, **not** a non-transpose
flag. The real non-transpose signal is the instrument-level **`IgnoreBaseNote`**
(authoritative: ConvertWithMoss `MPCModernDetector.java:486` only honours the
per-layer `KeyTrack` field *when `IgnoreBaseNote` is True*; otherwise the zone
key-tracks). When a zone tracks with `RootNote=0`, the root should fall back to
the keygroup **LowNote** (CWM writer `MPCKeygroupCreator.java:223` does exactly
this: `RootNote = (keyRoot || keyLow) + 1`).

Symptom (reported by Jan on `Bass-MS20 Antima-Patch 2c.xpm`): "metallic, out of tune."
Cause: the 15 narrow multisample keygroups (kg36-38 → sample "036 C1", …, root =
LowNote) all have `RootNote=0`, so the parser routes them through the SMP path →
**one voice, 15 zones all spanning key 0-127 with root=60** → the E4XT stretches
a single sample across the whole keyboard from the wrong root → severe
pitch-shift/aliasing.

**Verified non-regressions to preserve:** genuine non-transpose layers use
`IgnoreBaseNote=True` (F9 Disco Rhodes, DX7 "Chain-Noise"). The one ambiguous
case is `RootNote=0 + IgnoreBaseNote=False + full-range kg0-127` (DX7
"Chain-Synth Oscillators") — see the design note in `docs/RESOLUTION_NOTES.md`.

Related: [[MS20-tuning]] is the same root-derivation gap that the slice-playback
SMP-tuning sub-item touches. Fix strategy + CWM citations in RESOLUTION_NOTES.

---

## SFZ parser: keyswitch articulations discarded (only default kept)

**Status:** **RESOLVED 2026-06-12.** Each `sw_last` articulation → its own preset
(named `<inst>-<label>`, keyswitch keys dropped).  Verified:
`1st-violin-SOLO-KS-C2.sfz` → 6 presets (Sustain, Tremolo, Normal, Accent,
Staccato, Pizzicato).

`sfz_parser.py:256-272` keeps only the group whose `sw_last == sw_default` and
**discards every other articulation**. SFZs with keyswitches (e.g.
`1st-violin-SOLO-KS-C2.sfz`: 9 groups — C2 Sustain, C#2 Tremolo, D2 Normal,
D#2 Accent, E2 Staccato, **F2 Pizzicato**, all on the same playable range) come
out as a single articulation transposed across the keyboard. Jan: "CWM plays
different styles … ours just plays the same sound transposed." CWM keeps all
articulations (ignores keyswitches, stacks ~4 overlapping per key).

**Agreed E4XT mapping:** emit **one E4B preset per keyswitch articulation**
(`<base>-Sustain`, `<base>-Pizzicato`, …) — most faithful and usable on the
preset-based E4XT — and **drop the keyswitch keys** (C2-F2) like CWM, so each
preset's playable range is the real instrument range. Fix strategy in
`docs/RESOLUTION_NOTES.md`.

Distinct from (but related to) [[sfz-stacking]]: that item is about
*simultaneous* overlapping instruments (brass — correct to stack into parallel
voices); this one is *mutually-exclusive* articulations (must NOT stack — split
into separate presets). The discriminator is the presence of `sw_last`.

---

## E4XT per-preset voice limit — RESOLVED 2026-06-13; per-NOTE limit ~32 measured 2026-07-31

**Status:** **RESOLVED 2026-06-13 — no cap found; HARDWARE-CONFIRMED.**

E4XT RE via `RE_SUITE.iso`: `20 VOICES` loads all 20, `24 VOICES` loads all 24,
and `MZ 14V 11Z` (154 zones) loads all 14 — so there is **no general per-preset
voice-count, voice-data-byte, or zone-count limit**.  Jan confirmed 2026-06-13
on the rebuilt FEATUREDEMO ISO: `P001 all-brass-SEC-ac` shows all **15 voices**
(SFZ overlapping-region stacking + no cap → full 15-voice load). The original 15-voice
SFZ-brass preset showing only V1–V10 was **specific to that preset's
construction**, not a hardware ceiling. `MAX_VOICES_PER_PRESET` is therefore
`None` (cap disabled); `cap_voices_by_coverage` is a no-op pass-through unless a
cap is ever explicitly set. No writer change needed.

**Consolidated RE bank:** `RE_SUITE.iso` still carries the test presets for the
one remaining open RE task — **KeygroupWheelToLfo gating** (ModWheel source id +
PatchCord-amount dest id); see that item below and §3/§4 of
`docs/re_procedures/re_suite.md`.

---

## Zone reducer: `--reduce-key-zones` not velocity-aware → velocity holes

**Status:** **RESOLVED 2026-06-13.** `thin_key_zones` ran over a voice's whole
key-sorted zone list; after the XPM parser change packs non-overlapping velocity
layers into one voice, that interleaved the bands and tore holes in the velocity
coverage (Jan: Alpha Pad G#4-C#5 silent at high velocity, "holes" in the
hardware Vces-VelWin). Fixed: `thin_key_zones` now groups zones by velocity band
and thins + re-spreads each band to full keyboard coverage independently.
Verified: DSI Alpha Pad at `--reduce-key-zones 35` → every velocity band spans
0-127 with zero holes.

---

## SFZ parser: overlapping regions collapsed to one voice (no stacking)

**Status:** **RESOLVED 2026-06-12.** Regions lane-allocate into parallel voices
(overlapping key+vel → separate voices); same-param non-overlapping regions
share a voice.  Verified: `all-brass-SEC-accent.sfz` → 15 stacked voices (was 1).

`sfz_parser.parse_sfz` builds a **single** `VoiceLayer` and appends every
`<region>` to it as a zone (`parsers/sfz_parser.py:232` + `:387`). When an SFZ
overlays several instruments/dynamic layers on the same key+velocity range
(e.g. `all-brass-SEC-accent.sfz`: tuba + horns + trombone + trumpet, 14 groups,
up to 14 regions sounding at one key), the E4XT only plays **one** zone per note
(a voice selects a single matching zone), so the stack is lost and the preset
sounds thin. ConvertWithMoss reproduces it by building MPC keygroups with up to
4 simultaneous **Layers** (its hardware cap); the E4XT equivalent is multiple
overlapping **voices**, which we currently never emit (`1 layer(s), 155 zones`).

Each SFZ `<group>` here is a self-contained keymap (one instrument/dynamic
layer), so the natural fix is **one voice per overlapping stream** instead of one
voice for the whole file. Fix strategy + the group-vs-overlap-lane design
decision in `docs/RESOLUTION_NOTES.md`.

Note: this is the same "thin vs thick" class of issue as the XPM 122× unison
stack ([[the wide-drone preset]] slice item) — both come down to the E4B needing parallel
voices to stack.

---

## XPM parser: slice-based sample playback not honoured

**Status:** **RESOLVED 2026-06-12.** `_apply_slice()` trims to Pad-Start/End and
sets a forward (or ping-pong) loop from the Loop Position; slice-keyed sample
cache.  122× identical unison stacks are deduped.  Degenerate
`SliceLoopStart==SliceEnd` still falls back to whole-slice loop (unconfirmed on
HW — see RESOLUTION_NOTES).

MPC XPM `<Layer>` elements carry `<SliceStart>`, `<SliceEnd>`, `<SliceLoopStart>`
and `<SliceLoop>` (Pad Loop mode: 0=Off, 1=Forward, 2=Reverse, 3=Alternating)
fields that select a sub-range of the referenced WAV in **sample frames** and
loop from the Loop Position (`SliceLoopStart`) to the Pad End (`SliceEnd`). The
current parser ignores all of these — it loads the full WAV and creates no loop
points. Presets built on slice-based layers (e.g. `Inst-Synth-the wide-drone preset.xpm`, which loops 7 short drone segments and stacks one 122×) sound
"metallic and distorted" because the full, non-looped WAV bears no resemblance to
the intended looping slice.

Secondary: instrument-level `<TuneCoarse>` / `<TuneFine>` are not applied to
zones created from SMP-mode layers (RootNote=0). Affects all slice-based presets.

Field semantics verified against the MPC 3.7 manual + measured WAV frame counts;
the degenerate `SliceLoopStart == SliceEnd` case still needs ear/hardware
confirmation. Full fix strategy + field table in `docs/RESOLUTION_NOTES.md`.

---

## HDA: EMU-fs works; FAT layout corrected to EOS-native — both RE'd 2026-06-14

**Status:** **BOTH HDA filesystems HARDWARE-CONFIRMED (2026-06-14).** Jan loaded
banks from both `FEATUREDEMO_emu1gb.hda` (properly disk-sized EMU-fs, free space,
`build_emu_hdd`) and `FEATUREDEMO_fat.hda` (EOS-native FAT16/MBR, `build_hda_fat`)
on the E4XT.  EMU-fs HDD geometry confirmed against 1/2/4 GB EOS references;
bank-count-per-folder (≤100, multi-block dircon) RE'd from emu3fs + implemented.
Full RE in `docs/re_procedures/emu_hdd_fs.md`.

### EMU-fs (`--hda-fs emu`) — WORKS + now properly disk-sized (free space)
`build_hda_emu` → `iso_builder.build_emu_hdd`: a real **disk-sized** EMU3 image
(honours `--hda-size`) with the banks in a `Default Folder` and the rest of the
clusters **free** (so EOS can save onto it).  Geometry RE'd & **confirmed across
EOS-formatted 1/2/4 GB references** (`HD1-FEATUREDEMO_emufs.hda`,
`HD1-2GBemufs.hda`, `HD2-4GBemufs.hda`): it is a **second fixed profile** of the
EMU3 fs — directory geometry constant (`fat=4 root=7 dircon=169 start_data=182
total_clusters=1023`), only the **cluster size scales** (cse 4/5/6/7 =
512 MB/1/2/4 GB, keeping clusters ≤ 1023).  `build_emu_hdd` output's **superblock
and Default-Folder entry are byte-identical to the references**.  Full table +
the 2-digit (EMU-fs slot) vs 3-digit (FAT filename) numbering rule in the RE doc.
**HW-CONFIRMED:** disk-sized image loads on the E4XT (Jan, 2026-06-14).
**Multi-block dircon DONE + HW-confirmed:** up to **100 banks/folder** across
`ceil(N/16)` dircon blocks via `block_list[7]` (RE'd from emu3fs `emu3_fs.h`:
`EMU3_BLOCKS_PER_DIR=7`, 16 entries/block).  `MULTIBLOCK20_emu.hda` SLOT16 &
SLOT19 (2nd dircon block) loaded on hardware.

**Multi-folder DONE + HW-CONFIRMED (2026-06-14):** >100 banks now spill from the
system "Default Folder" (id 0x80, banks 0–99) into additional root folders
"Folder 2", "Folder 3", … (id 0x40), each ≤100 banks with per-folder slots reset
to 0.  dircon blocks allocated sequentially across folders; next-free pointer
set.  Limited by disk capacity (≤1023 clusters) / root (112 folders) / dircon
pool (169 blocks).  Verified: 150 banks → Default Folder(100) + Folder 2(50);
4-bank output byte-identical to the HW reference.  **HW**: on
`MULTIFOLDER105_emu.hda` Jan loaded RICH00 from "Folder 2" — presets work.

### FAT (`--hda-fs fat`, default) — corrected to EOS native, was wrong
The first attempt (partitionless **FAT32** superfloppy) was **rejected by EOS**
("No Banks Exist in Folder!").  An EOS-formatted reference (`HD1-FEATUREDEMO.hda`)
shows EOS actually writes:
- an **MBR partition table** (zeroed boot code, 0x55AA), partition 1 at **LBA 63,
  type 0x06 (FAT16)** — *not* partitionless, *not* FAT32;
- **FAT16**, **32 KB clusters** (64 sec/clus), **32 reserved sectors**, 2 FATs,
  512 root entries; OEM **`E-MU SYS`**;
- banks `B.NNN-NAME.E4B` in the partition **root** (and optionally sub-folders).
`build_hda_fat` rewritten to this exact layout (hand-written MBR + `mformat
-c 64 -R 32` + OEM patch + `mcopy`); `FEATUREDEMO_fat.hda` **HW-CONFIRMED** (Jan
loaded a bank, 2026-06-14).  (The HD0.img reference used earlier was a PC-made
FAT32, which misled the first attempt — the E4XT's own format is FAT16/MBR.)

### Append to an existing image (`--add-to`) — IMPLEMENTED 2026-06-14
`convert.py --add-to <image> [--folder NAME] [--on-duplicate ...]` appends the
converted bank(s) to an existing .hda (FAT or EMU-fs, auto-detected via
`detect_hda_fs`) without overwriting existing banks/folders; creates the folder
if absent.  EMU-fs: `iso_builder.emu_hdd_append` (read-modify-write — finds free
clusters/slots, spills dircon blocks, bumps next-free, superblock untouched).
FAT: `hda_builder.fat_hda_append` (pure-Python `writers/fat16.py`, next free
B.NNN).  Duplicate policy: prompt (default) / add-new / skip / overwrite.
**Append HW-CONFIRMED for BOTH filesystems** (2026-06-14): EMU-fs — APPENDED_BANK
from a new ADDED folder; FAT — a bank from the appended `Added` folder on
`FEATUREDEMO_fat_py.hda`.  Presets work from appended banks in both.

## FAT path is pure-Python — mtools dependency removed (Windows-ready) 2026-06-14
`writers/fat16.py` is a from-scratch FAT16 reader/writer (MBR + FAT16 + VFAT long
names, EOS-native layout) used by `build_hda_fat` + `fat_hda_append`.  **No
external tools** — the whole converter is now pure Python stdlib (no third-party
libs, no binaries), so it runs natively on **Windows** (the resampler's
ProcessPoolExecutor was already spawn-safe).  **HW-CONFIRMED 2026-06-14**: on
`FEATUREDEMO_fat_py.hda` (built+appended purely in Python) Jan loaded banks from
the root AND the appended `Added` folder on the E4XT — presets work.  Also
mtools-validated, BPB matches EOS, bank bytes round-trip byte-identical.
(mtools retained in dev only as an independent cross-check.)

**FAT32 added 2026-06-14** (`writers/fat32.py`): EOS uses FAT32 above ~1 GB (4.7
addendum p.3), so `build_hda_fat` now auto-selects **FAT16 ≤1 GB / FAT32 >1 GB**
and `fat_hda_append` detects the type.  FAT32: MBR type 0x0C, adaptive 16/32 KB
clusters (largest yielding ≥65525 clusters), FSInfo + backup boot, cluster-chain
root/folders.  mtools-validated at 1152 MB & 4 GB; build/append/folders work;
bytes round-trip identical.  **HW-CONFIRMED 2026-06-14** (Jan loaded a bank + played presets off the 4 GB FAT32 FEATUREDEMO.hda). (Was validated only
against mtools — no EOS-formatted FAT32 reference yet).  The whole FEATUREDEMO was
rebuilt with this session's aural fixes onto a **4 GB FAT32 HDA** (sparse 441 MB
on disk), ISO + colour-preserved ODS regenerated.

---

## KRZ #204 the wide-drone preset — structure fixes 2026-06-24 (junk KGs, +12); gaps remain

Deep-dived with Jan A/B-ing on the K2000R. The XPM is **8 keygroups** (4 key-bands
× A/B pan pair, samples UniDrone C1/C2/C3/C4, unity 36/48/60/72) but pads to **128
Instrument slots** — KG9–128 are 120 identical junk copies (24–47 C1). All 8 KGs:
**KeyTrack ON, Semi +12, Pan ∓50 (A=L/B=R)**, identical env + LFO (0.54 Hz → Pan22
/ Pitch3 / FiltEnvDepth10).

**FIXED (xpm_parser):**
- **Junk KGs dropped** — honor `<KeygroupNumKeygroups>` (8); was keeping a junk
  voice that the K2000 3-layer cap then *kept while dropping a real one*.
- **Per-keygroup Pan** now read (instrument-level `<Pan>` + layer, summed).
- **Semi +12** confirmed already applied (roots = unity−12); staging E4B was just
  stale → regenerated `feature_staging/WIDEDRONE_01.E4B` and rebuilt the ISO.

**ALSO FIXED — coverage multisample remap (2026-06-24, Jan's idea).** Wide-range
octave-slice stacks can't keytrack past the K2000 up-pitch ceiling (~1 octave
above root at 24 kHz), so high keys went silent (L1 died ~C2). New
`krz_writer._coverage_remap_voices`: lays the C1/C2/C3/C4 slices side-by-side as
a COVERAGE multisample (each slice keys 0/handoff→its ceiling, next slice takes
over), in ≤3 parallel layers (any-channel). #204 now plays **gap-free 0–72**,
correct octave. Auto-applies to the sibling stacks too (F9 Rhodes, JR AFX/JP8/
Warm/1V — they reach keys 109–120). Scoped tight: only fires for all-overlapping,
**full-velocity**, ≥2-octave-root, ceiling-overflowing stacks (a velocity guard
keeps it off Bass-DX7 etc.).

**STILL OPEN / deferred (all need Jan or HW):**
1. **Pan not delivered to K2000** — `write_e4b`/`parse_e4b` drop per-zone pan, and
   `krz_writer` doesn't render pan at all. So the L/R width (and LFO→Pan,
   LFO→FilterEnvDepth) is lost. Needs: E4B pan round-trip + KRZ pan byte (RE) +
   LFO→pan/→filt-env-depth cords. (The coverage remap is currently mono; once pan
   is delivered it can split the doubling layers L/R.)
2. **#204 top keys 73–127 silent** — its highest slice is C4 (root 60 after +12,
   ceiling 72 at 24 kHz) and there's no higher slice; the source plays these on
   the MPC (no ceiling). Only fix is heavier downsampling (`--max-sample-rate`)
   to raise the ceiling, at a quality cost. (Sibling stacks reach 109–120 — they
   have higher-rooted slices.)
3. **Sibling JR drones' staging is stale** — the coverage remap (writer) helps
   them, but the junk-KG-drop / +12 / pan PARSER fixes only apply when their
   staging E4B is regenerated; only the wide-drone preset's was this round. Regenerate
   `JR_*` staging from XPM to apply those uniformly.

## Band-Boost (BB) filters map to BANDPASS — RESOLVED 2026-06-25 (E4B + KRZ)

**Both writers fixed.** E4B: BB 19-22 → Swept EQ 1-oct (`0x20`) with +gain (the
band-stop mapping, gain sign flipped). KRZ: BB 19-22 → **Alg 2 PARA MID** parametric
boost, hardware-RE'd 2026-06-25 (PARAJLZ.KRZ disk-save diff): `CAL[29]=2`,
F1(0x50)[0]=**51** (PARA MID FRQ), F1[1]=center freq = existing `_cutoff_byte`
(16 Hz/C0=−48 … 25088 Hz/G10=+79), F2(0x51)[0]=**16** (AMP block), F2[1]=**gain in
dB, 1:1 signed** (boost = `+12..+24 dB` from MPC resonance), F3(0x52)[0]=**40** (None).
Verified end-to-end: #204 Bass-MS20 Antima-Patch (FilterType=19) → ALG2/51/AMP+20 dB.
Procedure + byte table: `docs/re_procedures/krz_paramid.md`; details in
`docs/RESOLUTION_NOTES.md §BB`.  (Possible later refinement: measure the MPC's true
BB gain law to calibrate the dB depth; FRQ already exact.)

---

## (was) Band-Boost (BB) filters map to BANDPASS — wrong sound (2026-06-25)

MPC FilterType **19–22 = "BB 2P/4P/6P/8P" (Band Boost** — a parametric/peaking EQ
that passes the full-range signal and *boosts* a band). Both writers approximate it
as a **bandpass** ("closest resonant emphasis; no exact match"), which instead
*removes* everything outside the band → thin/hollow. Confirmed audibly wrong on
`K2KFEATDEMO` **#204 Bass-MS20 Antima-Patch 2c** (src FilterType=19, Cutoff=0.27, Reson=0.65):
the K2000 conversion sounds very different from the MPC original (Jan, 2026-06-25).
(NB the on-HW bank Jan tested is a *stale* build showing 4-pole LP; current code already
emits 2-pole BANDPASS — still wrong.)

- **E4B — FIXABLE NOW (no RE):** EOS **Swept EQ 1-oct** (`vpar[58]=0x20`) is a
  parametric band gain whose law is already HW-RE'd (`gain_dB=(byte−64)×0.375`). Band-
  *stop* (15–18) already maps there with a *negative* gain; Band-*boost* is the **same
  filter with positive gain**. Patch in `docs/RESOLUTION_NOTES.md §BB`.
- **KRZ/K2000 — needs HW RE:** the right target is a K2000 **parametric-EQ DSP block
  (PARA MID / PARA BASS)**, not yet reverse-engineered (bandpass is just the nearest
  RE'd block). RE the function byte + algorithm + freq/gain/width mapping (FILTERS.KRZ
  disk-save method, same as the 2026-06-16 filter-type RE). **Status: blocked on RE.**

---

## KRZ: bandpass + filter-env-sweep preset plays silent (OPEN, 2026-06-21)

`K2KFEATDEMO` #204 "the wide-drone preset" emits no sound on the K2000R.
Diagnosed: samples (UniDrone, root C1) have audio + loops, keymap keys assigned, amp
env fine. The **2-pole bandpass** (HOB0[0]=3) is centered at cutoff byte **−12 (≈130 Hz**,
from source `Cutoff=0.285`) and swept by the filter env (HOB0[5]=121 ENV2, depth 60); on
the low drone it parks where ~nothing passes → silent. **Not caused by the keytrack/cap/
downsample work** (filter bytes come straight from the source; unchanged). Belongs to the
known "KRZ filter-env depth + LFO→filter depth are approximate / need HW calibration"
gap — a bandpass-sweep is the first source that makes it fully inaudible rather than just
off. **To fix:** RE the 2-pole bandpass center/width + ENV2→filter depth+direction on HW
(disk-save trick, like the keytrack fix) so the sweep opens audibly. Likely also affects
other bandpass + slow-filter-env sources. Possible interim: widen the bandpass (HOB1[1])
or floor the static cutoff so it's audible before the sweep.

---

## KRZ single-sample keymaps don't keytrack — FIXED 2026-06-21 (up-pitch ceiling cap)

Surfaced on the K2000R: **single-sample presets (#202 PingPong_Vox, #203 Ab-e1) played
at FIXED pitch** while multisample presets (#200/#201) tracked.

**Root cause (RE'd from a hardware-edited save, `TRACK203.KRZ`):** the writer stretched a
single sample across the WHOLE keyboard (zone 0–127). The sample (33 kHz, root 60) can
only transpose UP to the K2000's 48 kHz ceiling = `maxPitch//100` = root + 12·log2(48000/sr)
≈ key 66. Assigning it to keys far beyond that (up to 127) makes the K2000 **drop
keytracking for the ENTIRE keymap** (plays one fixed pitch). Jan's fix-by-hand narrowed
the keymap range; the diff showed that was the *only* change (same method 0x13, same
sample, same program, same per-key tuning). Two effects confirmed on HW: (A) extreme
overshoot → whole keymap goes fixed; (B) even when tracking, keys above the ceiling clamp
to one pitch (C5==C4). (My earlier method-0x11 / WAVEFAZE-`defaultSampleID` theory was
WRONG — the K2000 re-saved as 0x13; reverted.)

**Fix (`writers/krz_writer._build_keymap_entries`):** cap each zone's assigned keys at the
sample's up-pitch ceiling (`_compute_max_pitch(sr, root)//100`). Keys above the ceiling go
SILENT instead of playing the wrong pitch, and the rest of the keymap keytracks. Multisample
unaffected except already-clamping top keys of the highest sample (verified vs RegalLead:
only keys 120–127 of its top run, which already clamped, are trimmed). To extend the
playable range UPWARD, downsample via `--max-sample-rate` (raises the ceiling — same lever
as the KRZ floppy banks). **HW retest:** `FLOPPIES/SF2FIX_01.img` (5 single-sample bass
presets, keys 0–66) on the Gotek.

**Ping-pong loop "audible seam" (#202) — NOT a bug.** Re-analysis of the baked PCM:
`PCM[sampleEnd]=L+1`, `PCM[loopStart]=L` → the seam is a correct, value-continuous
ping-pong turnaround (…L+1, L, L+1…). The audible artifact is the inherent *slope*
discontinuity at a ping-pong turnaround (same on E4XT). Optional future enhancement: a
short crossfade at the turnarounds to soften it. The bake (`loop_renderer`, 2n−2 frames,
inclusive `loop_end`) and the KRZ loop-point math are correct.

---

## KRZ `--iso` produced unreadable ISO 9660 — RESOLVED (2026-06-21): K2000 wants FAT16

**Symptom:** the K2000 demo CD built with `convert.py --format krz --iso` was rejected
on the K2000R ("Disk must be in K2000 format"), even on **OS v3.87** (which *does* read
ISO 9660 — but its reader is picky about our xorriso-built image).

**Root cause + fix:** the K2000/K2500 SCSI CD/disk format is a **FAT16 "disk-image
copy", not ISO 9660** — RE'd from a working factory CD (`CD1-E_Bomb.iso`) + the Kurzweil
`SCSI.txt` + the v3.87 release notes (all in `~/Dokumente/SYNTHS/K2000R`):
FAT16, **BPB at sector 0, NO MBR/partition**, OEM `KCDM1.2`, fsType `FAT16   `, 8.3
filenames, KRZ files in a subdirectory. ISO 9660 needs OS v3.87+; the FAT16 image works
on **every** OS version (older OS "require an image of a Kurzweil/DOS-formatted disk").

Implemented: `fat16.format_new(partition=False, oem=, spc=)` (no-MBR layout) + a clean
8.3-no-LFN path in `fat16.add_file`/`makedir`; new `iso_builder.build_k2000_disk`;
`convert.py --iso` for krz now builds the FAT16 disk image (E4XT `--hda`/EMU3 paths
unchanged, regression-checked). Also fixed `_iso9660_unique_names` hardcoding ext=`E4B`
(KRZ ISOs got `.E4B` filenames). Verified byte-identical extraction via mtools; the demo
CD `K2KFEATDEMO.iso` matches the factory CD's BPB. **HW-CONFIRMED 2026-06-21:** the
K2000R reads the FAT16 CD and loaded bank _01 (64486K ≈ 62.97 MB sample data) to
completion. FAT16 disk-image is the correct K2000 CD format.

---

## KRZ floppy multisamples: up-pitch clamp at 44.1 kHz (FIX SHIPPED + ALL BANKS HW-VERIFIED)

**Status:** root cause fixed in converter (2026-06-18); all 6 `FLOPPY_JOBS`
banks HW-verified (last one, RegalLead, confirmed 2026-06-21). Only the
low-priority headroom-aware rate-picker enhancement remains open (see bottom).

**Symptom (HW, audio-measured):** wide key zones at 44.1 kHz played groups of
adjacent keys at the *same* pitch — the K2000 can only pitch a 44.1 kHz sample
UP ~1.46 st before hitting its 48 kHz playback ceiling (`maxPitch`), so every
key >~1.5 st above its sample root clamped flat. Confirmed via
`tests/re_banks/pitch_sweep.py` (5-zone build: 11-key dead zones 20 st apart =
sample-root spacing). Pitching DOWN is unlimited.

**Fix:** new `convert.py --max-sample-rate HZ` (clean linear downsample in
`resampler.resample_to_rate`). Lower rate buys up-pitch headroom
(log2(48000/HZ) octaves) AND shrinks the bank to fit a floppy. SYNTHBONES at
12 kHz / 16 zones (+24 st headroom) = HW-CONFIRMED 2026-06-18: F#2–E7 track
within +10 c, no clamping. Reducing zone COUNT at high rate (the old
`--reduce-key-zones 70`) was exactly wrong.

**DONE 2026-06-18:** `rebuild_krz_floppies.py` rewritten to drop --reduce and
instead pick the highest RATE_CANDIDATE that fits the floppy at reduce=0. All 10
banks rebuilt + redeployed to the Gotek (FLOPPIES/ + FILTERTYPES/). Rates landed:
Bass/Organ 22 kHz, Synth/Timeless 16 kHz, filter-synths 7–9 kHz — all with ample
headroom for their narrow 16/21-zone maps.

**HW-VERIFIED 2026-06-18** (autonomous audio sweep, `tests/re_banks/verify_programs.py`,
programs #200–205 on ch9): Bass-MD Ace 60/60, Organ-PRO5 Coming 56/61 (92%),
Synth-PRO5 Bones 61/61, Keys Timeless 61/61 keys in tune (±60c) — all PASS, no
clamp. AxeLead clamps (2-sample source, unfixable by rate). PercDynobel pitch test
inconclusive (short one-shot percussion defeats pitch detection) but structurally
clamp-free (30 kHz → +8 st headroom > 4 st zones).

**HW-VERIFIED 2026-06-21 — RegalLead:** the MS20 lead that replaced the degenerate
AxeLead (16 samples, roots 31-106, 22 kHz) **tracks chromatically across the FULL
MIDI range C-2…G8 (notes 0–127) with no clamping** (by-ear, Jan, program #200,
"Lead-MS20 Regal"). Confirms the rate-over-reduce strategy end-to-end. All
`FLOPPY_JOBS` banks are now HW-verified.

**Also HW-verified 2026-06-21 — 1PoleLP (Bass-Pulse-Bass):** the 1PoleLP
filter-demo bank also tracks chromatically C1–C6 with no clamping (first program
tested this session, before the RegalLead re-test).

**Remaining script gap (low priority):** the fit-driven selection ignores
HEADROOM for banks that already fit at a high rate. Two needed manual rates this
round: AxeLead (2 samples on one full-keyboard zone — degenerate source, forced
to 12 kHz for ~2 oct tracking; can't be fully fixed without more samples) and
PercDynobel (16 one-shot perc zones, 5 keys wide — kept high quality at 30 kHz,
+8 st headroom). Proper fix: make the rate picker headroom-aware — parse each
voice's max (hi_key − sample_root) and cap rate so log2(48000/rate)·12 ≥ that.

## HDA builder: directory block limited to 16 entries

**Status:** low priority; silent-data-loss already guarded (2026-06-08 —
`build_hda()` warns + truncates to 16, no invisible sectors written).

The remaining work is to actually *support* more than 16 E4B files per HDA
image via multi-block directory support — chain additional 512-byte directory
blocks beyond the single root block.

**To implement:** needs hardware RE to confirm the block-chaining convention
(how the E4XT locates the next directory block).

## KRZ: clean velocity-SPLIT layers collapse to ONE layer — FIXED 2026-06-24

**Status:** FIXED in `writers/krz_writer.py` (`_split_voice_by_velocity`,
wired into `write_krz`); KRZ-writer tests pass; verified on the AlphaPad
staging E4B (program #200 now 3 layers, vel windows 0-64/65-96/97-127).
**Pending: K2000R HW A/B re-test by Jan** (soft notes should now play the
darker low-velocity layer). Rebuild K2KFEATDEMO to ship it.
Found by Jan loading K2KFEATDEMO to K2000R bank 200, `#200 Alpha Pad`.

**Symptom:** the MPC One original has **3 velocity layers** (split 0-64 /
65-96 / 97-127); the converted KRZ program has only **1 layer**. Audibly the
K2000 plays too bright at all velocities (the top/loudest layer always wins) —
Jan's "lots less high frequencies on the original, although the filter is fully
open … probably the velocity-triggered layers."

**Root cause:** *not* the KRZ writer's layer support (which already writes
per-layer `loVel`/`hiVel`, CR-1) and *not* the E4B path (the staging E4B is
correct: 1 voice / 141 zones, each zone carrying its own vel range — the E4XT
plays one zone per note by key+vel). The break is the interaction between two
correct-in-isolation pieces:

1. `xpm_parser._overlaps()` (lane-allocator, ~line 811) splits zones into
   separate voices only when they overlap in key **AND** velocity. AlphaPad's
   three velocity bands are mutually exclusive (0-64 vs 65-96 don't overlap),
   so all 219→141 zones collapse into **one voice**. (CR-1 only ever split
   velocity layers that *also* overlap; clean splits were never exercised.)
2. `krz_writer._build_keymap_entries()` builds one keymap per voice using
   **only `lo_key`/`hi_key`** — it ignores `lo_vel`/`hi_vel`. Three zones on
   the same key (one per vel band) all write the same keymap slot; the last
   one (top velocity = brightest) wins. Result: 1 layer, vel 0-127, brightest
   sample on every key.

This is the KRZ analogue of the SMP-parser bug already documented in
`docs/RESOLUTION_NOTES.md §10` ("one voice per distinct vel range").

**Fix:** see `docs/RESOLUTION_NOTES.md` §"KRZ velocity-split layers" — split
each KRZ voice's zones by distinct (lo_vel,hi_vel) band into separate K2000
layers + keymaps at write time (the writer already accepts per-layer vel
range, so this stays a writer-only change and leaves E4B untouched).

## KRZ: LYR velocity range + Enable — FIXED 2026-06-24 (HW-confirmed)

**Symptom (Jan, K2000R, AlphaPad #200):** intermittent / no sound; Layer page
showed `Enable: Sustain / Note St / ON` and wrong LoVel/HiVel.

**Two bugs, both fixed:**
1. **Enable clobber.** The writer wrote hiVel into LYR `data[6]`, but `data[6]`
   is the layer **Enable control source** (every real K2000 layer = 127 = ON;
   KurzFiler/a third-party bank/a programs-only bank all confirm). hiVel 64/96 there set Enable to
   Sustain(64)/Note St(96) → gated layers. Fix: keep `data[6]=127`.
2. **Velocity encoding.** Both LoVel and HiVel are packed into the SINGLE byte
   `data[5]`, as 0–7 dynamic marks (ppp=0…fff=7): **bits 3–5 = LoVel mark,
   bits 0–2 = HiVel mark stored INVERTED (7−mark)** → `data[5] =
   (loMark<<3) | (7−hiMark)`. So full-range = 0 (why it was invisible in static
   files). HW-confirmed by diffing `VELAYRE.KRZ` (3 layers saved on the K2000R:
   ppp/fff→0, mf/fff→32, ppp/mf→3). Implemented as `_vel_byte()`.

**Confirmed LYR map:** `[1]=0x18 [3]=loKey [4]=hiKey [5]=packed vel (see
_vel_byte) [6]=Enable(127=ON) [8]=flags(0x04 mono/0x24 stereo)`.

**Result:** AlphaPad #200 → 3 layers, all Enable ON, LoVel/HiVel ppp–mf / mf–f /
f–fff (MPC 0-64/65-96/97-127 quantised to the K2000's 8 marks). Bands touch at
mf/f due to the 8-step granularity (minor overlap; acceptable). Reference: the
packed-byte map is also in the `reference_krz_format` memory.
**HW playback CONFIRMED on K2000R (Jan, 2026-06-24): velocity split is in place.**
Shipped in K2KFEATDEMO.iso. Optional future tweak: nudge each layer's HiVel down
one mark for strictly non-overlapping bands.

## KRZ: AMPENV segment offset + flat release — FIXED 2026-06-24

**Status:** FIXED in `writers/krz_writer._fill_env`; tests pass; verified on
AlphaPad #200. **Pending K2000R HW A/B.**

**Bug 1 — segment offset (the big one).** `_fill_env` wrote its `(time,level)`
pairs starting at byte **2** of the 0x21/0x22 ENV segment, but the K2000 packs
the 7 pairs `Att1 Att2 Att3 Dec1 Rel1 Rel2 Rel3` from byte **0** (times on even
bytes, levels on odd; byte 14 = loop flag). HW-confirmed by Jan reading the
AMPENV LCD: levels Att1..Rel2 all 100 % except Rel2=0. Effect: our decay→sustain
landed in Rel1 (so Rel1 read 100 %, never faded) and the release fade landed in
Rel2 → "held then cut" instead of a fade. Masked earlier for sustain=100 %
patches. Fix: write pairs from byte 0; leave byte 14.

**Bug 2 — release shape.** A single linear Rel1 sus→0 doesn't match the MPC's
~exponential (dB-linear) release. Now a two-leg approximation: Rel1 fades to a
**33 % knee** over **80 %** of the release time, Rel2 tails 33 %→0 over the
remaining 20 % (`_REL_KNEE_PCT`, `_REL1_TIME_FRAC`). Knee + split validated by
ear (Jan, AlphaPad: Rel1 2.16 s→33 %, Rel2 0.5 s→0 %).

NB: the *absolute* release duration is still ~1.9× short — that's the shared
time-curve item below, not this fix.

## XPM envelope-time curve under-reads vs MPC display — KRZ patched; global recalibration DEFERRED (by-ear)

**Status:** KRZ side handled (2026-06-24) with a writer-only ×1.9 release
multiplier (`_KRZ_RELEASE_FACTOR` in `krz_writer.py`). **Global recalibration of
the shared `_xpm_env_to_seconds` curve is deferred pending a by-ear E4B/E4XT
check (Jan).**

**Authoritative data (MPC One AMPENV display, Jan 2026-06-24):** `#200 Alpha
Pad`, XPM `<VolumeRelease>0.763780</VolumeRelease>` → MPC display **2.63 s**;
our curve gives **1.39 s** (`0.00079·e^(9.78·v)`) → **×1.90 short**. Jan's
by-ear K2000 match (Rel1 2.16 s→33 %, Rel2 0.5 s→0 %; total ≈2.66 s) agrees with
the MPC display, confirming the gap is a uniform ~1.9× under-read, NOT a K2000
perceptual difference. (The earlier "by-ear 3.48 s / ×1.3 perceptual factor"
guess is RETRACTED — it was measured on the pre-fix mis-mapped envelope.)

**Why the curve is low:** §18 (2026-06-09) fit it to **audio time-to-−40 dB**,
not the MPC's displayed segment time. An exponential release passes −40 dB
before the segment ends, so the display reads longer by a ~constant factor
(both scale with the same time-constant). §18 itself noted the threshold only
shifts the **constant**, not the 9.78 exponent.

**DEFERRED TODO — global curve recalibration (needs by-ear check):**
- `_xpm_env_to_seconds`: rescale **A 0.00079 → ~0.0015** (= `2.63/e^(9.78·0.764)`,
  exponent unchanged) so ALL segments (attack/decay/release + filter, all
  formats) match the MPC's *displayed* times.
- **Blocked on:** Jan A/B-ing a few E4B presets on the E4XT after the rescale —
  it lengthens every E4B envelope 1.9×, which was never scrutinised for release
  length. Ideally also read MPC-displayed seconds at ≥3 `XPM_VOL_DECAY` sweep
  values to confirm the exponent before refitting.
- When done, **drop the KRZ-only `_KRZ_RELEASE_FACTOR`** (the global fix
  subsumes it). See `docs/RESOLUTION_NOTES.md` §"XPM release-time recalibration".

---

## KRZ keymap: `base_pitch` is threaded but never used for entry placement

**Status:** open, dormant — no wrong output today.

`_build_keymap_entries` takes `base_pitch`, and `_write_keymap_object` writes
it into the KKeymap header, but entry placement is hardcoded `key - 12`
(`FIRST_MAPPABLE_KEY`). `write_krz` sets `base_pitch = 0`, so the two agree and
nothing is wrong. Set it non-zero and the header and the entry table disagree:
every zone lands `base_pitch/100` semitones off.

Per `docs/KRZ_FORMAT.md`, `note = 12 + round((basePitch + i·centsPerEntry)/100)`.
A `basePitch` of −1200 would map the 128 entries onto keys 0–127 and remove the
key-12 floor entirely, which is also why the floor is a *writer default*, not a
hardware limit — the dropped-zone warning is worded accordingly.

**Blocked on:** nothing in code; wants a K2000R confirmation that a non-zero
basePitch keymap loads and sounds where intended before we rely on it.

## KRZ keymap: the up-pitch ceiling clamp drops keys silently — FIXED 2026-08-09

`_build_keymap_entries` clamps `hi_key` to `_compute_max_pitch`. When the
ceiling falls below `lo_key` the whole zone vanished, with nothing said.

**Measured first, deliberately** (7 082 zones over 120 E4B banks + 25 GIG
files), because the low-key warning shipped earlier the same day fired on
nearly every bank and had to be narrowed:

| outcome | zones | share |
|---|---|---|
| entirely lost (`ceiling < lo_key`) | 527 | 7.4 % |
| merely clipped at the top | 3 056 | 43.2 % |
| untouched | 3 499 | 49.4 % |

Reporting the clipped 43 % would have been exactly that noise. Only the
entirely-lost 7.4 % is reported, as a second category on the existing
dropped-zone message rather than a second warning.

**Those keys are not silent.** The hole-filling pass extends a neighbouring
zone over them (it must — a keymap hole locks up the K2000 on Master→Delete),
so they sound the *wrong sample*. The message says so, and points at
`--max-sample-rate`, which downsamples and thereby raises the ceiling.

The reference `cp80.gig` conversion reports 34 such zones; it had been losing
them silently all along. Covered by
`test_zones_lost_above_the_pitch_ceiling_are_reported`, confirmed to fail with
the fix reverted, with both negative controls.

**Open question for Jan, unchanged:** whether dropping is right at all, or
whether the zone should be kept and allowed to play flat above the ceiling.
That is a hardware-audible judgement call.


---

## KRZ object ids stop at 999 — HW-confirmed, writer refuses and splitter splits

**Status: DONE 2026-08-10** — writer refuses, splitter splits on the same
number, both halves hardware-informed.

`_hash(type, id) = (type << 10) + id` packs the id into the low 10 bits with
no mask, so an id of 1024 carries into the TYPE field: a sample (type 38)
numbered 1024 hashes to 39936, which reads back as **type 39, id 0**. Not a
sample with a wrong id — not a sample. Silent and total.

**HW-CONFIRMED 2026-08-10 (K2000R):** there are *two* ceilings and the lower
one binds.

| condition | what the machine does |
|---|---|
| `id > 999` | **clamps** — every further object lands on 999, each overwriting the last, silently |
| `id > 1023` | the id carries into the type field; the object reads back as a different type |

Ids start at `base_id = 200`, so the usable count is **800 per type**
(200–999), not the 824 the hash can encode. `write_krz` raises past it
(800 OK, 801 refused).

The same session confirmed **per-type numbering is right on hardware**: a bank
with samples, keymaps and programs all numbered 200–205 loaded on a cleared
K2000 and all six programs played their own sound, including three built so
the keymap number and sample number deliberately differ. The machine resolves
a reference by the slot it sits in, not a shared id space.

**A bank can also be too big to load at all — MEASURED 2026-08-10 (K2000R,
disc `K2KLIMIT`, `tests/re_banks/gen_k2000_loadlimit_disk.py`).**

Two axes kept separate, because our writer emits one keymap per voice: a
program costs ~2 objects, a sample 1. Samples ~11 ms so RAM could not
confound the count — the largest bank reported `Memory: 690K`.

| bank | samples | presets | objects | result |
|---|---|---|---|---|
| S200–S600 | 200–600 | 1 | 202–602 | load |
| **S800** | **800** | 1 | 802 | **loads**, top object on id **999** |
| P200 | 8 | 200 | 408 | loads, fast |
| P400 | 8 | 400 | 808 | loads, noticeably slower |
| **P600** | 8 | **600** | 1208 | **loads, ~20 s on "Please wait ..."** |

**No failure was found on either axis.** The full id range 200–999 is usable —
the machine listed `999*S0799-C 4` — and every object count matched exactly
(`Sel: 0/408`, `Sel: 0/808`).

**The real limit is PRAM, and it is per-machine — this is what the object
counts above were actually measuring.** A K2000 keeps its *objects* (programs,
keymaps, sample headers) in PRAM, separately from sample RAM. Measured cost,
matching the machine's own object list:

| object | bytes |
|---|---|
| sample header | 84 |
| program | 272 |
| keymap | 688 |

We emit one keymap per voice, so a preset costs `272 + voices × 688` — 960 B
for a plain one. That is why the preset axis runs out first: 800 samples are
only 66 K, but 600 presets are 562 K.

**It explains the hang exactly.** 796 presets × 960 B = **746 K against that
machine's 760 K** — 98 % full. Never an object-count limit.

**And it invalidates generalising from this machine.** The K2000R used for
these tests has a **760 K expansion**; an original K2000 has 128 K fitted,
**~116 K usable**, and most commercial banks were authored for it (our
K2KFEATDEMO banks run 8–38 K). A 600-preset bank needs 562 K and simply will
not load on a stock machine.

Applied: the splitter now caps on **estimated PRAM bytes**, default **110 K**
(the stock ~116 K less headroom for setups and effects), overridable with
`--pram KB`. That gives ~117 one-voice presets per bank by default and ~810
with `--pram 760`. `write_krz` warns against the same stock figure. The
object-id ceiling (800 per type) still applies underneath and binds the sample
axis.

**Still open:** where between 600 and 796 it actually breaks. A P700 bank
would halve the gap. It only matters for libraries producing more than 600
presets in one bank, which is rare — every bank in either local library is far
below it.

---

## KRZ keymap sharing — implemented, OFF by default, awaiting one disc

**Status:** `krz_writer.SHARE_IDENTICAL_KEYMAPS`, default `False`.

A keymap is **688 bytes** of PRAM against a program's 272, and we emit one per
voice. A bank of presets that share a layout therefore spends most of its PRAM
on byte-identical duplicates — 300 such presets carry **201 K** of them. Real
K2000 banks share: a re-assembled bank measured 796 programs against 52
keymaps.

With the flag on, voices whose keymap entries come out byte-identical get one
object. Default output is unchanged — the reference GIG→KRZ still hashes
`e173c03e9caa0c23`.

**HW-MEASURED 2026-08-10 (K2000R, disc `K2KSHKM`).** N programs all pointing
at ONE keymap, timed:

| programs | keymaps | load time |
|---|---|---|
| 200 | 1 | **< 2 s** |
| 600 | 1 | **11–12 s** |
| 796 | 1 | **18–20 s** |
| 600 | 600 (disc `K2KLIMIT`) | ~20 s |

**Sharing works and is worth shipping.** 796 programs sharing one keymap load
normally, so the machine does treat a shared keymap as one object. And it is
not only a PRAM saving: holding programs at 600, going from 600 keymaps to 1
takes the load from ~20 s to 11.5 s — **nearly half**.

**Load time is superlinear in program count:** `t ∝ n^1.71` (exponents of 1.69
and 1.78 between consecutive pairs — a stable fit). Extrapolating, ~1000
programs ≈ 28 s and ~1500 ≈ 56 s. There is no cliff; a large enough bank simply
takes unbounded time, which is what "hang" looks like from the front panel.

**The 796-preset hang is NOT explained by count.** This model predicts ~20 s
for VinSamLib's 796 programs + 52 keymaps, and it hung for several minutes. So
the cost is in what those programs *reference* — their ROM keymap references
are the surviving suspect, and still the axis nobody has varied.

**Left to decide before making sharing the default:** it changes the bytes of
every multi-preset bank we have hardware-confirmed, and it changes *behaviour*
for the user — editing one shared keymap on the machine then affects every
program using it. Real K2000 banks do share (796/52 in the wild), so that is
arguably expected rather than a regression, but it is Jan's call rather than a
silent default flip.

---

## "Hang" is slowness — a real bank loaded in 11 MINUTES (2026-08-10)

**Observed on the K2000R, first-hand.** A real (non-synthetic) bank finished
loading after **11 minutes**. It did not hang. This closes the question that
started the whole PRAM/limit investigation: past a certain size, *"the machine
hung"* and *"the load had not finished yet"* are the same observation from the
front panel.

From the object browser:

| | |
|---|---|
| total objects | **1048** |
| programs | ids **200–999** — 800, exactly the per-type ceiling |
| PRAM in use | **273 K** |
| program sizes | 224 – 714 B |
| keymap sizes | 178 – 1332 B |
| effects | present, 60–68 B (ids 200–203, 908–909) |
| samples | `Grand Piano G#1  0K` — **ROM references**, no PCM in the bank |

**Load cost is driven by program CONTENT, not program count.** Our synthetic
`SK796` — 796 programs, one shared keymap, one zone each — loads in **19 s**.
This bank, at essentially the same program count, takes **660 s**: **35×**
slower. Whatever the machine does per program scales with how much the program
*refers to*, not how many there are.

That also makes the ROM-reference suspicion concrete rather than a guess: this
bank carries ROM sample references (the `0K` samples), which is exactly the
axis VinSamLib nominated and neither project has varied.

**Two corrections to our own model, neither affecting the splitter:**

- **Object sizes are not fixed.** We assume program 272 B / keymap 688 B /
  sample 84 B. Those are *our writer's* shapes and remain correct for
  estimating *our* output — which is all `bank_pram_bytes()` is used for. Real
  banks range 224–714 B for programs and **178–1332 B** for keymaps, so the
  model must not be pointed at third-party banks without saying so.
- **800 programs is confirmed on a real bank.** Ids run 200–999 exactly, which
  independently corroborates the per-type ceiling measured synthetically.

**Open:** which bank this was (VinSamLib reported theirs as 796 programs / 52
keymaps / 11 samples = 859 objects; this one is 1048 with effects, so it may be
a different one). Worth pinning down before the 11-minute figure is attached to
their hang specifically.

## KRZ looped samples may carry PCM the K2000 can never reach

**Status:** open question, not a known bug. **Blocked on:** a corpus of real
K2000 soundsets, which is not on this disk.

A KRZ Soundfilehead's loop end and the sample's own end are the SAME field, so
for a looped sample `krz_writer` sets `sample_end_field = abs_loop_end` — which
is correct and hardware-derived (the K2000 defines the loop as
`[sampleLoopStart, sampleEnd]`, and declaring the true PCM end makes it loop
over the decay tail instead). Independently confirmed by VinSamLib 2026-08-14.

But we still write the FULL PCM, so every looped sample carries whatever
followed the loop end — audio the sampler can never play, in a machine that
loads samples into RAM. If real banks do not carry that tail, we are spending
the user's sample memory on silence they cannot hear, which matters because
the AKAI/K2000 memory ceilings are exactly what `bank_splitter` fits against.

**What would settle it:** in real (not converted) K2000 soundsets, does the PCM
of a looped sample end at `sampleEnd`, or does a tail follow it? Measuring 943
looped samples across 60 local `.KRZ` files gave 168 with a tail — but every
one of those files is this project's own output (`krz_batch`, `gig_e2e`,
`k2000_loadlimit`, …), so that figure measures our writer and says nothing
about the format. All 271 local `.KRZ` files are ours. The "201 real soundsets"
the KRZ work was verified against are not currently on this machine.

Do not truncate on the strength of the reasoning alone: the KRZ writer is
hardware-confirmed as it stands, and a tail that real banks also carry is a
convention rather than waste. Raised 2026-08-14.
| **KRZ: 5 DSP block codes still unidentified** | `seg[0]` codes 20, 23, 30, 31, 61 — **1.7%** of F1 slots across 80 banks. They now REFUSE (leave the filter at default) rather than decoding to an invented bandpass, which was the defect. Identifying them needs a K2000 page read of a program carrying each; the largest is code 61 at 42 occurrences. Low value — the harm was the fabrication, not the gap. §K2DSP. Noted 2026-08-16 |
| ~~KRZ: resonance dropped on ~6% of lowpass programs~~ | **fixed 2026-08-16 — and the 6% was a fourfold undercount.** Measured on F1 code 2 and layer 1 only. Across ALL filter types and ALL layers: 801 of 3612 filter layer-pairs carry resonance (22.2%), the old `seg[0] == 16` gate read 37 of them (1.0%), so 764 were dropped. Real banks now go from ~1% to **25.0% of voices carrying resonance** (169 of 677 across 28 sample-bearing banks). F2 is the second control INPUT of the F1 block, not a block of its own, which is why its byte 0 is almost always zero. Scale confirmed at dB×2 on 30 distinct displayed values from −15.0 to +24.0 dB — `krz_reson_byte_to_01`'s docstring had it right all along. §K2DSP |
| **model: `filter_resonance` cannot carry a CUT** | 204 of the 801 measured K2000 resonance values are negative (−15.0 to −1.0 dB) and `VoiceLayer.filter_resonance` is 0..1, so they clamp to 0.0. That is a model limit, not a reader one: fixing it means a signed range that every writer would then have to honour. Deliberately not done as part of the reader fix. Noted 2026-08-16 |
| ~~superseded row~~ | The F2 handler reads resonance only when `0x51[0] == 16`, which is true in **2 of 627** plain-lowpass programs; `0x51[1]` is non-zero in 40 of them. So real resonance data is present and unread. **Deliberately not fixed:** reading `0x51[1]` as resonance because it sits in the right position is the same inference that produced the invented-bandpass bug. `0x51`'s byte 0 is 0 in 606/627, which fits neither "per block" nor "per input" as either project guessed. **Blocked on:** a K2000 page read of a program with visible non-zero resonance, correlated against its `0x51` bytes. §K2DSP. Noted 2026-08-16 |
| ~~**AKAI: sample rate is written verbatim and the sampler may only play 44100/22050**~~ | **CONFIRMED AND FIXED 2026-08-18.** s3ked wrote sample-header byte 0x01 over SysEx on a *resident* sample, SSRATE untouched: 44100/flag 0 -> 150 Hz, 22050/flag 1 -> 600 Hz. **Byte 0x01 selects playback rate; SSRATE at 0x8a is descriptive only.** Enum probe 0-7 and 255: rate follows **bit 0 alone**, set is exactly {22050, 44100}, and 255 stored+read back verbatim — *acceptance is not validation on this machine*. Our writer had set that byte from `1 if sample_rate >= 30000`, a threshold existing only in our source, so a 48 kHz source played **147 cents flat with a header that read back perfectly correct**. Fixed: flag now derived from the actual rate, plus an AKAI rate-snap in `convert.py` (after `--max-sample-rate`, so an explicit user choice is honoured first). Verified end to end; 417 tests pass. **Settled in 20 minutes with no crossing because the field is writable — the disc built for it never left the desk.** §AKAIRATEQUANT | **Round 1 measured on hardware 2026-08-18** (s3ked): stored 44100 and 22050 are **honoured exactly** — so this is NOT the EOS §E4BRATE failure — while 11025 plays at 22050 (×2 fast) and 32000 at 44100 (×1.378). Two models fit: the machine quantises `SSRATE` to a supported neighbour, **or** `h[0x01]` is the playback-rate selector and our writer sets it from a threshold of its own invention (`1 if sample_rate >= 30000`, commented as "bandwidth"). **If the latter, this is a live bug in every conversion whose source is not 44100/22050:** nothing forces an AKAI sample to a supported rate, so a 48 kHz source — most modern material — plays 147 cents flat, silently. Round-2 disc built and verified (`~/temp/HD7_r2.img`): two programs deliberately contradict `SSRATE` and the flag, giving an octave's difference under one model and none under the other. **Blocked on:** one crossing plus two captures. §AKAIRATEQUANT |
| ~~**AKAI: we write 0 into the sample-data address at header `0x16`-`0x18`**~~ | **CLOSED 2026-08-18 — real deviation, no effect.** 12965 factory sample headers carry a non-zero u24 there (advance = frames rounded up to 64, 97.1% of 5097 pairs) and 100% of ours carry zero — but `SDADDR` and `SDZERO`, identical discs but for that field, played **identically program-for-program to three decimals**. Cosmetic. Still worth fixing eventually for fidelity to the format, along with `0x10` (the machine writes 0 for a one-shot and 1 for a loop; we write 1 unconditionally). §AKAISDATA |
| **AKAI: the zone pointer at `zone_base+0x16` is written 0xFFFF and never validated** | We write `0xFFFF` in every zone; the machine overwrites it with a real address on load (§AKAIRESAVE, which called it "machine-owned and correctly left alone by us" — where **"correctly" was an inference from the overwrite, never a measurement**). Read off the machine's own saves 2026-08-18: `XCROSS 1` carries 36984 / 36996 / 37008 / 37020 for PRGNUM 120–123, **spaced 12 paragraphs = 192 bytes = exactly one sample header**, sequential in load order. That is a slot-like binding attached to a field we null out, and it is the leading suspect for §AKAILOOPCROSS — resolution to the wrong neighbour with several samples resident, to nothing at all with one. **ANSWERED 2026-08-18 and it argues AGAINST this being the cause:** across 10 factory discs (5628 programs, 90328 used zones) **`0xFFFF` is the single most common value at 35.3%**, with `0x0000` a further 30% — so writing `0xFFFF` is entirely normal and is not our deviation. The field reads as a scratch/RAM pointer that a disc carries in whatever state it was saved in. This does not fully exonerate it (a factory disc carrying 0xFFFF might work for some other reason) but it removes "we write something no real disc writes" as the explanation. Our reader cannot parse the factory discs available locally (see the row below), and a raw-scan fallback produced false positives — its "zone names" came back as `408090 0 080`, so its tidy 1/2/3/4 distribution was arbitrary binary, not evidence. §AKAILOOPCROSS |
| ~~**AKAI: our reader skips every directory record on some factory CD-ROMs**~~ | **WITHDRAWN 2026-08-18 — my error, not the reader's.** I filed this after counting zero programs on a factory disc. The reader parses those discs correctly; **the count was mine and it was wrong**, because it looked only for S3000 type codes (0xF0 program, 0xF3 sample) while these are **S1000 volumes** (root type byte `0x01`) whose files are typed with the bare ASCII letter — `0x70` = 'p', `0x73` = 's', i.e. the same letter *without* bit 7. Re-run with both generations' codes: **10 discs, 5628 programs, 90328 used zones**, parsed cleanly. What the reader really skips is a minority of records that genuinely are type `0x00` (aux files such as `DRUM INPUTS`, plus some odd ones) — worth a look eventually, but it blocks nothing. Left visible rather than deleted: a bug filed against a component that was working is worth the same scrutiny as one that was not. |
| **AKAI: the pool-base fix was never written** (the silence report is WITHDRAWN) | **SOLVED AND FIXED 2026-08-18.** A LOOPED sample at the base of the sampler's object pool does not play correctly — silence, or degraded non-periodic audio. Decisive pair, same file and byte-identical loop record with only the address differing: `SLOCAT 131072` silent at −72.8 dBFS, `SLOCAT 483872` plays at −8.2 dBFS with its own 5.000 s period at corr 0.967. **"Positional, not ordinal" was overstated** — the machine assigns addresses in load order, so a sample cannot be first without landing at the base, and no test we can easily run separates the two. The supported claim is that a looped sample which is the FIRST one loaded fails. The fix is correct under either reading. Five rules were stated and withdrawn before this one; it survived because a control separated position from order. **Fixed:** `build_akai_volume` emits an unlooped sample first, so under the bulk load a user performs the one-shot takes the base — a reorder, not a filter, with a warning when a volume is all loops. Closes §AKAISDATA too: `SLOCAT` is that field, recomputed by the machine, which is why SDADDR ≡ SDZERO. ~~**Still wanted: hardware confirmation of a converted volume ordered this way.**~~ **REOPENED 2026-08-21, and the confirmation arrived as a failure.** Jan loaded `TC1 E4B BASS` on the S3000XL and reported **PRGNUM 0 — no sound**. That program's sample is the first in the volume and it is LOOPED, which is exactly the condition this row describes. **The fix recorded above does not exist in the code.** `build_akai_volume` iterates `for sd in bank.samples` in plain order; there is no reorder, and `grep` for the promised warning finds nothing in `writers/`, `convert.py` or `processors/`. The row said FIXED for three days on the strength of a description. **And a reorder alone would not have saved this volume anyway: all ten of its samples are looped**, so there is no one-shot to promote — which is the case the recorded fix explicitly said it would only warn about. **SILENCE REPORT WITHDRAWN 2026-08-21, same evening.** s3ked measured that same program at **-15.8 dBFS, the loudest in the volume** -- not silent at all. And Jan's own remark for that program, written after the report, describes its tone (*"a bit muddy compared to E4"*), which I had read and quoted without noticing it contradicted the bug I had just filed. The likely real cause: **channel 1 was silent on that machine that evening** -- every program silent on channel 1, every one sounding on 2..16. **What stands is only the grep**: `build_akai_volume` has no reorder and no warning, so the fix recorded as shipped is still absent -- but it is now an unimplemented fix for a bug with no observed symptom on this disc, not an explanation for anything. §AKAILOOPCROSS §AKAIPOOLBASE |
| **AKAI: LOAD type 1 loads programs but no samples — contradicts our SAVE-type note** | Measured by s3ked on the S3000XL 2026-08-18: `trigger_load(1)` ("ALL PROGS+SAMPLES") loaded six programs and **zero** samples, free memory unchanged, capture silent at −70.3 dBFS; `trigger_load(3)` then loaded all six. Reproduced on the machine's own `BOOT SYSTEM#` volume, so it is not our disc. Our §AKAIAUX row has type 1 as "programs and samples", from SAVE behaviour — so either LOAD and SAVE numbers are separate namespaces, or one reading is wrong. **Kept as an open contradiction on purpose:** the disagreement is the only thing pointing at the answer, and folding one into the other would destroy it. Use LOAD type 3 meanwhile. **Blocked on:** one panel comparison of the LOAD and SAVE menus' own labels. §AKAILOADTYPE |
| ~~**AKAI: a volume with more than 128 programs silently collapses them onto PRGNUM 127**~~ | **WITHDRAWN 2026-08-18 — filed against code that was already correct.** It is **not silent**: `build_akai_volume` warns, and adds the nuance this row missed — the extra programs *"remain selectable from the sampler's own panel"*, so they are unreachable by program change rather than lost. And the fix proposed here (split the volume at 128) is explicitly rejected in the writer's own note, because the machine holds more than 128 happily and *"splitting a volume that would have loaded is the over-tight clamp this project has recorded twice as the worse failure"*. It looked silent because the bench generator calls `build_program` directly and never reaches the warning — the same bypass that defeated the name-uniqueness defence in §AKAINAME12. **Lesson: reproduce through the production path before filing.** §AKAIPRGCLAMP |
| **AKAI: every looped sample is written "loop in release", probably wrong** | **REOPENED 2026-08-18 — the falsification is withdrawn, its evidence was not our sample.** This row was marked FALSIFIED ON HARDWARE earlier the same day: `NSWHITE` held five seconds flat at −1.7 dBFS with no collapse at t=2.000s, plus an autocorrelation r=+0.9999 at the loop lag. **Both of those measurements were made on audio that does not contain `NSWHITE`.** Checked against the frames we actually wrote, `test2_nswhite.wav` and the "clean" re-run `test2_clean.wav` are **100.0% of their energy in one 250–500 Hz band** — a pure sine at the played note (48→131 Hz, 60→261.5, 72→523.0), a resident program answering because ours shared its PRGNUM and one neighbour was on PMCHAN 255 (OMNI). A held sine has a flat envelope, so it *reads* as "the loop sustains"; that is why nothing looked wrong. **The original claim is not re-established either — it is simply unmeasured.** Re-run on `CALNOISE` (HD7, id 7, PRGNUM 120–123, no OMNI), and gate the capture on `python3 tests/re_banks/is_it_our_noise.py` **before** analysing it — it PASSes the written frames (white slope +3.1 dB/band, lag-1 −0.002) and FAILs every capture in `~/temp/s3ked-logs/`. See §AKAILOOPRATE (retracted). |
| **KRZ writer folds velocity→filter into a static cutoff — on a premise tonight disproved** | `krz_writer` does not emit a velocity sweep at all. It adds the positive part of `velocity_to_filter` to the cutoff and writes a static corner, and the recorded reason is *"rather than a VelTrk sweep from the K2000's 16 Hz floor (which would mute softly-played notes)"* — the exact failure found on the AKAI 2026-08-17, anticipated and side-stepped. **The premise is wrong.** `MinDpt = 0` does not sweep from a 16 Hz floor; it anchors the modulation AT the cutoff, so velocity only ever opens upward from it. Verified against a real source: `Coarse` 196 Hz with `MinDpt 0 / MaxDpt 10800` plays 196 Hz at velocity 0. So a faithful sweep is writable — `Cutoff = X, Src2 = AttVel, MinDpt = 0, MaxDpt = Y` — and the fold costs every KRZ-targeted conversion its velocity dynamics for nothing. **Care needed on `DptCtl`:** it SCALES the range, and all 47 corpus routings use `DptCtl = ENV2`, so a pure velocity sweep needs a constant-max controller rather than an envelope. **Not blocked** — this is implementable once the `DptCtl` convention is chosen, and it is a fidelity gain on every KRZ output, not just K2000 sources. Found 2026-08-17 by checking whether the sibling writers shared the AKAI fault. §AKAIVELFILT |
| ~~Do the E4B and EIII writers share the AKAI velocity→filter fault?~~ | **No, checked 2026-08-17.** `e4b_writer` uses `_SRC_VEL_PLUS`, documented as *"ADD, anchored at base for vel 0"* — a unipolar source that matches the K2000's `MinDpt = 0` semantics exactly, so E4B output is already correct. Its comment records that an earlier `Vel<` default anchored HARD notes at base and was wrong, which is the same class of error solved independently before the AKAI one existed. Only the AKAI's `MODVFILT1` is bipolar about a velocity pivot and needed re-centring |
| **AKAI: `.D` and `.M3` are DECODED; `.X` and `.T` remain** | Done 2026-08-18 off the card. **`DRUM INPUTS.D`**: 16 records of 9 from `0x10`, second bank `0x5b`, input 16 one byte short — and all nine fields stored **verbatim**, not scaled or packed. The two positions that read `0` in every earlier capture are decoded, because the procedure made input 1 set every field. **`MULTI FILE.M3`**: 1024-byte header + 16 parts × 192 = 4096 exactly, stride **measured** from `VOSCL` planted at three parts (0x506 / 0x5c6 / 0x686), and every one of the thirteen fields at the **same intra-part offset as RAM** — so the disk stores the RAM representation. **Still open:** what `243` MEANS for `PANPOS` (written via s3ked's encoder, which assumes two's complement — needs one look at the panel), and `.X` (7312 bytes) and `.T` (160 bytes), both still at defaults. §AKAIAUX-DECODED |
| **AKAI: one factory disc in six is largely unreadable (87.8% of its records)** | Measured 2026-08-18 after fixing a diagnostic that had been multiplying its output across reads (§AKAIUNKNOWNDUP) and inflating this into a phantom "36% corpus-wide loss". The real distribution is **0.0-4.9% on five discs and 87.8% on one**: 4155 of that disc's 4735 records carry directory type `0x00` with *sample-sized* payloads (250 KB, 543 KB). A smaller tail elsewhere: 100 records of exactly 162 bytes on another disc (the `DRUM INPUTS.D` size, typed `0x00` where other discs use `0x64`), and 9 records at multiples of **150** bytes — the S1000 program block size, not the S3000's 192. **One disc to study, not a systemic reader fault.** Not blocked on hardware. |
| **AKAI: a volume we build fresh is a type-1 save, not a type-0** | **UNBLOCKED 2026-08-18 — the blocker's premise was wrong.** This was blocked on "deciding what to write into `.X`/`.M3`/`.D`/`.T`, since an aux file with invented contents is worse than an absent one" — which assumed the choice was decode-or-invent. There is a third option: reproduce what the machine itself writes. Measured over 45 specimens (the S3000XL's own saves plus six factory discs): **`.T` is a format CONSTANT — one distinct content in all 45**, so a correct one needs no understanding at all; and `.X`'s machine default (md5 `dc6a0c4d`) appears in exactly the three machine-written volumes, which is the right value for a volume we create because a converted volume has no effects assigned. `.D` and `.M3` were already decoded. **Not blocked on hardware.** Embed the blobs with provenance (machine, OS version, source volumes) recorded beside them. Note this does NOT decode what the fields mean — only that they need not be decoded to be written. §AKAIAUXDEFAULT |

| **Preset ORDER is scrambled by the bank splitter even when nothing needs splitting** | `writers/bank_splitter.py:749` sorts every preset by estimated size descending (First-Fit Decreasing) before packing, and the order that falls out of the packing is the order written. So a 7-preset source that fits one bank with room to spare still comes out reordered: measured on a real bank, source order `Spirit Profit, V Bass Wheel Wah, Touch Brass, Sync or Swim, Moving Waves, Zarathusynth, P5 Hard Sync 1` was written as `Zarathusynth, Spirit Profit, Sync or Swim, P5 Hard Sync 1, Moving Waves, Touch Brass, V Bass Wheel Wah`. E4B has no per-preset program field (byte 31 of the TOC entry reads 0 on every hardware-written bank measured here), so **position IS the number the E4XT shows** — the user dials a different number than the source had, for no reason the format required. **Not a packing bug:** FFD decides which bank a preset lands in and that is worth keeping; the order WITHIN a bank is free, so the fix is to restore source order per target bank after packing. Deliberately not done 2026-08-19 — the hardware test set built that night carries these numbers, and renumbering mid-comparison would invalidate the sheet Jan is filling in. §PRESETORDER |
| **KRZ writer renumbers programs instead of keeping the source's object ids** | The KRZ parser now carries the K2000 object id into `Preset.program_number` (fixed 2026-08-19 — it had been dropped, so every KRZ-sourced preset reached the model as program 0), but `krz_writer` still assigns ids sequentially from 200. Measured: a source program at id **202** is written as **200**. The K2000 dials programs by that id, so a rebuild of a bank the user already owns answers on different numbers than the original — exactly the 1:1 comparison the test set exists to make easy. Honouring the source ids needs only that they are unique and in the user range (>=200); the existing sequential assignment stays as the fallback, which is the same policy `akai_s3000_writer` already applies to PRGNUM. **Not blocked on hardware.** §PRESETORDER |

| ~~**AKAI: the reader takes SSRATE and ignores the playback-rate byte the writer trusts**~~ | **ANSWERED AND FIXED ON HARDWARE 2026-08-20 (s3ked §143).** Loaded from a disc -- not written over SysEx, which is the whole point -- two programs with byte `0x01` and SSRATE deliberately contradictory **both resolved to the index, in opposite directions**: `0x01=1`/SSRATE 22050 played 300.0 Hz, `0x01=0`/SSRATE 44100 played 150.0 Hz, with controls at 300.0 and 150.0 passing first under a stop rule. The loader reads byte `0x01`; SSRATE is descriptive. `_playback_rate()` now returns the index for S3000 samples, which stops 22.0% of factory headers being read at a rate the sampler never produces (1290 of them declared 48000, which it cannot play at all). **S1000 deliberately excluded**: the byte reads 1 in 35 990 of 35 990 `.S1` headers, so it carries no information in this corpus, and preferring it would move 3242 read rates on an inference from the other generation -- there it is a fallback for an absent SSRATE only. Remaining: the same test with `.S1` files. | `akai_s3000_parser.py:207` reads `rate = _u16(data, 0x8a) or 44100`, so a sample whose SSRATE is 0 is assumed 44100. Our own §AKAIRATEQUANT finding says byte `0x01` is what SELECTS playback rate and SSRATE is descriptive only -- the writer acts on that, the reader does not. **Measured over the local disc corpus (19 340 sample headers): SSRATE == 0 in just 1**, so the 0 Hz case ConvertWithMoss fixed (LGPL-3.0, commit c5df170d, 2026-08-20, independent work -- they hit it on machine-recorded material) barely occurs on library CD-ROMs. **But 4242 headers (22.0%) carry a nonzero SSRATE that disagrees with byte 0x01**: 1538 have idx=1 (44100) with SSRATE 22050, and 1290 declare 48000, which the machine cannot play at all. Under our own reading those all play at the rate the index picks, an octave from what we read. **The open question is which field the machine honours for a sample loaded FROM DISK** -- s3ked measured a RESIDENT sample over SysEx, which does not settle the load path, and the machine may well rewrite one field from the other on load. Also note every one of the 5331 `.S1` headers has idx=1, so the byte may not carry this meaning at all in the S1000 generation. **Blocked on:** one hardware test -- load a disc carrying a sample with idx and SSRATE deliberately contradictory, and hear which wins. Found 2026-08-20 while checking whether CWM's S-series work overlapped ours. §AKAIRATEREAD |

| ~~**AKAI: the source attack time is discarded on every voice**~~ | **FIXED AND HARDWARE-CONFIRMED 2026-08-20, and the reason it was ever broken is worth more than the fix.** The writer emitted `_AK_FIXED_ATTACK = 0` on the strength of a note quoting s3ked §29, *"attack fits neither a rate nor a duration"* -- **which was true when written and withdrawn the same day by their §31**, once four models were fitted per curve: a linear-in-amplitude ramp read on a dB axis is a curve, so a slope from its middle depends on how far the curve extends, and the span-dependence was the detector. §31 names `ATTAK1` a genuine duration. We cited the right field and a superseded version of the finding, and a citation stale by nine days cost every source attack for twelve. **An earlier version of this row blamed an `ATTAK1`/`ATTAK2` field mix-up; that account came from s3ked, who withdrew it within the hour after reading their own section, and the fields were never confused.** s3ked (§141) then killed the candidate law and confirmed ours: ConvertWithMoss's linear-accumulator model predicts 47.55 s at ATTAK1 99 and the machine reaches full level in **8.6 s** -- 7x out, ratio 0.14 sd 0.03 throughout -- while `t = 0.000201173 * exp(0.10844 * ATTAK1)` fits the measured t90 at 0.982, sd 0.06, including ATTAK1 99 which was never in the 55..90 fit. The ramp is **linear in amplitude**, established with no fitted constant at all: t50/t90 measured 0.50..0.56 against 0.556 predicted for a linear ramp and 0.301 for an exponential approach. Wired through `akai_attack_byte()`; the 6.554 s swell that came out instant is now ATTAK1 96. §AKAIATTACK | That row says the amp envelope now follows `voice.amp_env` through `akai_env_bytes()`. Two thirds of it does: `akai_env_bytes` returns `_AK_FIXED_ATTACK = 0` unconditionally, so **ATTAK1 is a constant and the source attack never reaches the machine**. That is deliberate and documented -- s3ked's varying-span test found attack fits neither a rate nor a duration, so there was no law to convert with -- but the CONSEQUENCE was never quantified. Measured 2026-08-20 on Jan's own E4B material: **39 voices, all 39 carrying an attack over 10 ms, 5 over half a second, the longest 6.554 s -- every one written as ATTAK1 0, i.e. instant.** A six-second pad swell converts to a click. This is the largest remaining fidelity hole in AKAI output, larger than the parked envelope-2 item, because envelope 2 affects the filter while this affects every amplitude. **A candidate law now exists**: ConvertWithMoss (LGPL-3.0, 2026-08-20) models attack, decay and release from one linear accumulator, `time = 32767*128 / (rate * 44100)` with the rate looked up at `99 - setting`. It predicts ATTAK1 40 = 0.146 s, 60 = 1.045 s, 80 = 7.316 s, 99 = 47.55 s -- over two decades across the range, so a wrong law cannot survive five points. **Blocked on:** one SysEx sweep and capture, no disc needed (set ATTAK1 on a resident sample, measure time to peak, gate on absolute level first). Start with ATTAK1 99: if a held note reaches full level in anything much under 47 s the model is dead for attack and s3ked's +10.6% exponent anomaly needs no further explanation. §AKAIATTACK |

| ~~**AKAI: the filter envelope is measured and unwired**~~ | **WIRED 2026-08-21, on a measured deficit rather than a decision.** Jan A/B-ed ten converted programs against their E4XT originals at three pitches: the three whose source carries a filter envelope came back **~20 dB darker in HF and FLAT across pitch** -- the signature of a missing modulation, not a mis-set corner -- and he identified those three out of ten by ear before any measurement. `akai_filter_env_bytes()` now converts ATTAK2/DECAY2/SUSTN2/RELSE2 from `voice.filter_env` through s3ked's full-traverse laws, scaling each stage by the distance it actually travels (`full_time * distance/99`), **and writes the depth at keygroup 153** -- §144 measured AKAI's own import defaulting 151/152/153 to zero, so an unrouted envelope is silent in exactly the way the fixed default was. Written only where the source has one: the other seven programs keep neutral defaults rather than being given an envelope they never asked for. Known limit: a 30 ms filter attack clamps to ATTAK2 40 (~66 ms), the bottom of the fitted range, rather than extrapolating. §AKAIENV2 | `_keygroup` writes fixed `ATTAK2`/`DECAY2`/`SUSTN2`/`RELSE2`. Audited 2026-08-20 against s3ked's `s3k/scales.py` rather than their prose: **all three time stages have current, non-provisional constants** (ATTAK2 `0.001363*exp(0.09703v)`, DECAY2 `0.002464*exp(0.09844v)`, RELSE2 `0.001344*exp(0.09692v)`, r2 >= 0.9998). The reason this file gave -- ATTAK2's depth-scaling -- is **§28's, retracted by §58 on 2026-08-12** (the threefold spread was the filter's corner ceiling, not depth); §67 then settled ATTAK2 as a rate. The second reason, *"our model carries no filter-envelope amount"*, **is ours and is also false**: `VoiceLayer.filter_env_amount` exists, eight parsers set it, and it is non-zero on 20 of 39 voices in real E4B material. **No hardware is needed** -- the filter board ordered 2026-08-17 was recorded as the blocker for measuring envelope 2 and s3ked measured it with a resonance tracker instead. The real blocker is design, never costed: these are RATES over a VARIABLE distance (`full_time * distance/99`), so wiring them needs envelope 2's four-stage rate/level architecture (§67) and a decision about how our two-parameter `Envelope` maps onto it. Retake the decision on current information. §AKAIENV2 |

| **AKAI: every calibration we rely on was measured on a RESIDENT program, never on a loaded one** | s3ked's point 2026-08-20, and it generalises further than they put it. Their filter law, envelope laws, level scales and tuning constants were all established by writing fields over SysEx into a program already in RAM. **§AKAIRATEREAD questions exactly that path for the rate byte** -- whether a DISK LOAD honours byte 0x01 or SSRATE, and whether the machine rewrites one from the other on load. If the load path can transform one header field it can transform others, so assuming the envelope and filter fields are immune is the same assumption in a different place. **Not a claim that anything is wrong:** several of our behaviours are disc-confirmed end to end (the loop-at-pool-base fix, the release test, the rate snap), so much of the load path demonstrably preserves what we write. What is missing is a direct read-back. **Cheap to settle and now carried on the disc**: `HD8_rateread.img` holds RR5/RR6/RR7 with ATTAK1 72/85/96 written by our own converter from source times of 0.5/2.0/6.554 s, so one crossing reads the field back after the load, compares it with what the disc holds, and times the ramp against `0.000201173*exp(0.10844*ATTAK1)` -- predicted t90 0.45 / 1.82 / 6.01 s. Filed 2026-08-20. §AKAIRATEREAD |

| ~~**AKAI: the reader reads FILFRQ and throws it away**~~ | **FIXED 2026-08-20.** `_cutoff_of()` now carries the keygroup's FILFRQ to `VoiceLayer.filter_cutoff`, using `AKAI_FILTER_LAW` moved into `models/common.py` so the reader and writer are **exact inverses by construction** rather than by agreement (the writer imports the parser, so the parser could not import back). s3ked's answer on which law: **§139**, the -3 dB corner, because that is what every source format means by cutoff. **S1000 keeps the default deliberately** -- both laws are S3000XL and §139 measured 12 dB/octave there against the S1000's specified 18. **The fitted range turned out to miss the data**: across four S3000 factory discs, 685 of 1555 keygroups sit in FILFRQ 85..98 and only **2** inside the fitted 40..84, so clamping put 44% of voices on one value. The top decade is now interpolated in POSITION between two measured endpoints -- the fit at 84 and hardware-confirmed wide open at 99 -- which is not the unsampled extrapolation this project has been burned by, since both ends are known. §AKAIFILTREAD | `akai_s3000_parser.py:407` puts `filter_freq=kg[0x07]` into the keygroup dict and **nothing ever consumes it**. Measured 2026-08-20 over three factory discs: `filter_cutoff` is **1.0 on all 16 020 AKAI-sourced voices**. So every AKAI -> E4B/KRZ/XPM conversion loses the programme's filter entirely and comes out fully open. Exactly symmetric to §AKAIATTACK, where the WRITER discarded the source attack: one side of the pipeline reads a field it never uses, the other wrote a constant it never varied, and in both cases the field was measured and available. Found while testing whether real `.P1` files could carry the S1000 filter experiment. **Blocked on nothing for S3000** -- the inverse of `akai_filter_byte()` is the fix -- but see the row below before choosing the law, and note the S1000 corner law is the open question the S1000 disc would settle, so `.S1` sources should stay unconverted until it is. §AKAIFILTREAD |
| **AKAI: our FILFRQ->Hz law may be superseded, and the two disagree by a third** | `_AK_FILTER = (6.4597, 0.07100, 44, 92)` in the writer is documented as re-derived from the **resonance peak** (s3ked §54, 2026-08-12). Their §139 (2026-08-20) measured the corner directly from a sawtooth harmonic comb divided by its own spectrum at FILFRQ 99, giving `7.60732 * exp(0.07245 v)` fitted 40..84, r2 0.99981 -- **and established the pole count as TWO (-12.2 dB/octave), not the three the S1000 specification claims**, which is what explained the constant 1.76x offset against ConvertWithMoss's firmware table. Ours reads 25.5% low at FILFRQ 44 rising to 34.6% low at 92. Two different measurements of the same field, and a resonance peak is not a -3 dB corner, so this may be a definitional difference rather than an error -- **but our writer is using the older one and nothing records that a newer exists.** This is the §31-versus-§141 pattern again: a section that was never retracted because it is still correct as written. Decide which quantity `filter_cutoff` should mean before wiring §AKAIFILTREAD, since the reader and writer must agree. §AKAIFILTREAD |

| ~~**AKAI: `.P1` sources convert with no filter at all**~~ | **CLOSED 2026-08-21 by measurement, not by inference.** The reader excluded S1000 from §AKAIFILTREAD because both filter laws are S3000XL. Jan's idea settled it without an S1000 and without audio: if the S3000 reads `.P1` natively, its own import routine IS the mapping. s3ked §144 loaded a 14-rung FILFRQ ladder and three probe programs setting all twenty semantic fields to 20/50/80 — **every field came back unchanged, the ladder exact and monotonic.** AKAI's importer is a pass-through, so an S1000 FILFRQ is an S3000 FILFRQ. Reached **14 661 keygroups** (19.3% of 76 086 `.P1` keygroups carry a real setting); voices reading fully open on three S1000 discs fall from 100% to 62.8%. **Identity is not equivalence** — §139's 12 dB/octave against the S1000's specified 18 means the same number can still sound different, so this reproduces what an S3000XL makes of the file, not what an S1000 made of it. Free result: keygroup 151/152/153 default to `[0,0,0]` on import. §AKAIFILTREAD |
| ~~**AKAI writer's default PRGNUM numbering starts at 0**~~ **FIXED 2026-09-10.** The fallback counted from 0, so the FIRST program of every volume built without usable source numbers landed on PRGNUM 0 — occupied by the boot-resident TEST PROGRAM, which survives every memory clear. Now counts from 1. Two existing tests encoded the old behaviour and were updated with the reason. | *(2026-08-30, s3ked + Jan, found by eye on the panel: two entries both displaying as "Program 1")* `_pnum = (getattr(preset, 'program_number', 0) or 0) if _usable else n_written` in `build_akai_volume` (`writers/akai_s3000_writer.py:3118`) falls back to `n_written`, a sequential counter starting at 0 -- landing the first program in any volume on PRGNUM 0. **PRGNUM 0 is not a free slot**: `TEST PROGRAM` is a machine-native object that survives every `CLR` and boots resident on every S3000XL, confirmed live on the bench (`TEST PROGRAM` and the volume's own first patch both at PRGNUM 0/PMCHAN 0, panel showing two "Program 1"s). Confirmed on all three V2 volumes built tonight. **This project already knew the fix** -- `tests/re_banks/gen_akai_rateread_disc.py:45` picks its PRGNUM base explicitly "NOT 0: the machine's own `TEST PROGRAM` survives every CLR", and `gen_akai_calnoise_disc.py` names the same hazard -- but that lesson lives only in the RE test-bank generators, never made it into the production writer's own numbering. **No capture was affected by this** (confirmed both by parking + independently by `TEST PROGRAM` referencing a `SINE` sample that ships absent from every affected volume, so it cannot sound regardless -- see the JACK/PRGNUM-0 exchange this session), so this is a real, low-severity fix rather than a scramble: change the fallback numbering to start at 1 (or explicitly skip 0), matching what the RE generators already do. **CORRECTED, s3ked, same evening: `TEST PROGRAM` is not content shipped in the volume -- it is the machine.** A memory clear on the S3000XL leaves exactly one program resident regardless of what was loaded (`clear_memory`'s own docstring: "the last program cannot be deleted... the list stays at one"), and that survivor is `TEST PROGRAM`, at PRGNUM 0, silent (references a `SINE` sample never resident). So PRGNUM 0 is never free on this machine, full stop -- it would collide with any writer's from-0 numbering on any volume, not something specific to these three builds. Whether the survivor is literally the loaded copy or a firmware default with that name is unconfirmed (one data point; not worth the machine churn to settle tonight) but doesn't change the fix. **Same lesson learned twice, in two repos, neither time in the place that needed it** -- `gen_akai_rateread_disc.py` avoided PRGNUM 0 without that reaching the production writer, and s3ked's own tooling had recorded THAT one program survives a clear without recording WHAT it is or WHERE it sits, which is the half that would have caught this earlier. Also explains why `report.py`'s patch pairing needed care around PRGNUM 0 specifically -- a volume whose patch 1 shares a number with a silent boot program is one bad program-change away from a mislabelled row. **FULL SCOPE CONFIRMED, s3ked, same evening: 4 of 18 card volumes collide (MX1 E4XT V2, MX2 KRZ V2, and -- correcting an earlier "three V2 volumes" misstatement -- the two NATIVE reference volumes MX3 S3000 OR and MX4 S1000 OR), and the natives collide for a different reason than the writer bug: they are commercial-library source material that never went through our writer at all, numbering from 0 same as the factory library generally does. So numbering from 0 is normal Akai practice; what makes it collide is entirely the machine's boot-resident occupant, not anything specific to our fallback -- our writer's from-0 default is one instance of a wider pattern, not its origin. The old (pre-V2) MX1/MX2 builds, on explicit PRGNUM 70-91, are confirmed structurally unaffected, exactly as traced above.** **No measurement anywhere on the card is affected, tonight's or older**, for two independent reasons: `TEST PROGRAM` references a sample literally named `SINE`, and a full sweep of all 364 samples across all 18 card volumes found none by that exact name (nearest is `SINE WAVE E4`, not a match, distinct 12-char AKAI names) -- so it cannot sound on THIS card regardless of the PRGNUM clash; independently, `unstack.py` parked it before every capture taken tonight (MX1/MX2/MX3/MX4 and both fixed re-measurements) and refuses to proceed if a clash remains. **Caveat worth keeping: this is true only because no sample on this specific card is named `SINE`.** A future volume that does carry a same-named sample would make `TEST PROGRAM` audible, turning a from-0 collision into a real contamination rather than a cosmetic one -- the writer fix (start numbering at 1) removes that possibility outright rather than relying on this card's naming luck to keep holding. |
| ~~**AKAI->KRZ: two S3000 patches silent**~~ **NOT A BUG, RESOLVED 2026-08-30 -- test-rig channel mismatch, not a conversion defect** | *(2026-08-30, k2kremote's first-ever AKAI->KRZ baseline pass, PRGNUM 800-811, test notes 36/43/48/55 @ vel100)* preset 4 (800) and preset 6 (801) read 0/4 sounded, peak -87 dB, against 10 of 12 sounding normally. Went through an offset-by-2 mapping theory (raised and refuted the same evening -- DIRBANK-before-load count confirmed 800-805=S3000/806-811=S1000 as originally mapped) and a velocity-range hypothesis before Jan's actual explanation landed: **the K2000 has a separate "drum channel" setting distinct from a program's own receive channel, and 800/801 specifically were configured to receive on it while 802-811 use the standard Basic Channel.** measure.py sends all its test notes on channel 9; the K2000's drum-channel setting wasn't pointed at 9 for these two. Jan switched it at the hardware and both programs sounded immediately. **Not a conversion defect of any kind** -- samples, keygroups, and the S3000->KRZ mapping are all fine; this was a test-rig/device-configuration mismatch specific to how these two programs happen to be routed. **Tooling note for whoever owns `measure.py`/`hw_measure.py` (k2kremote's rig, not this repo):** a "0/4 sounded" result on this rig does not necessarily mean silence in the conversion -- it can mean a channel mismatch between the capture script and the device's own routing. Worth having the harness check or report the device's drum-channel setting before concluding a real fault, so this exact false alarm doesn't recur on some other AKAI-sourced patch. **the reference preset's vibrato is the one item that survived this thread as real** -- Jan played the reference preset (802) by ear and reports way too much vibrato, possibly the same class of defect as the already-fixed AKAI-side vibrato-depth bug (measured 6x too much there) but for a DIFFERENT target machine/path, so it needs its own check against the KRZ writer's own LFO/pitch-depth mapping rather than assumed to be the same fix. Blocked on tracing the KRZ writer's LFO code or checking LFO1 depth on the panel. |
| **AKAI->KRZ: preset 4 has two separate, real velocity-dependent audio bugs, one root-caused, one open** | *(2026-08-30, found chasing the K2000 velocity-thinning fix's hardware verification, extensive s3ked/k2kremote collaboration)* Two independent symptoms on the same patch, confirmed genuinely separate by structure (not two views of one bug):

~~**(1) v=100 exactly: all 4 test notes go completely silent; v=99 and v=110 both fully clean.**~~ **FIXED AND HW-CONFIRMED, 2026-08-30 (§KRZVELBOUND).** A precise, complete dropout at one exact velocity value with both neighbours working -- not a partial boundary miss, a K2000 firmware edge case at an exact dynamic-mark threshold. AKAI side ruled out as the cause (s3ked's spectral read: the AKAI's own zone-2 boundary is inclusive exactly at velocity 100, matching the writer's own `round(100/127*7)=6` -- the arithmetic was correct on both ends, the K2000 firmware just can't resolve a note landing exactly on the mark it defines). **Confirmed surgically by k2kremote**: nudging the live program's affected layer's mark from 6 to 5 via SysEx, nothing else changed, took velocity-100 from 0/4 to 4/4 sounded. **Fixed in `writers/krz_writer.py::_vel_byte()`**: `lo_mark` now floors instead of rounds to nearest, `hi_mark` mirrors with ceil -- every velocity-split boundary now lands a few units off the fragile mark edge instead of exactly on it. Full test suite passes (507, only pre-existing unrelated failures). `hi_mark`'s ceil() side follows by symmetry, not independently HW-tested. Full writeup at §KRZVELBOUND in `docs/RESOLUTION_NOTES.md`. **Re-confirmed the same evening by applying the code-equivalent nudge live and leaving it (not reverting the test this time)**: velocity 100 across all 4 notes, 4/4 sounded, matching the first surgical confirmation exactly.

**(2) v=40: 3 of 4 test notes silent (only the highest note sounds).** ROOT-CAUSED, not yet fixed. The AKAI source is NOT silent at v40 on any note (s3ked measured all 4 audible, -34 to -49 dBFS, 39-54 dB above the noise floor) -- so this is a real conversion defect, not faithful reproduction of something quiet. Mechanism, hardware-confirmed piece by piece:
  - `K_FREQ` (filter key-follow) correctly drags kg0's filter ~2 octaves down at low notes (already modeled in this project, `filter_keytrack`) -- s3ked proved this carries 8.9 of the measured 12.7 dB gap by toggling kg0's `K_FREQ` 10->0 on the machine and re-measuring (v40 lifted 8.91 dB, v99 moved 0.04 dB -- noise).
  - The AKAI compensates for this at low velocity via a velocity-to-filter-envelope modulation that opens the filter more as velocity drops from its own baseline -- **and this project's AKAI PARSER never reads it.** Confirmed directly: every parsed voice in preset 4 shows `velocity_to_filter_cents=0.0`. Not a fresh discovery -- `writers/akai_s3000_writer.py:496` already has a comment stating outright "the AKAI reader does not populate `velocity_to_filter_cents`", dated from an unrelated 2026-08-25 writer-bug writeup, never turned into a read-side fix. The byte layout for the WRITE direction is documented at §AKAIVFR (keygroup bytes 151/152/153, S3000-extension-only, ±50 clamp, saturates past ~12-25 depending on base FILFRQ) and has been implemented for AKAI-as-target since 2026-08-16 -- never for AKAI-as-source.
  - **CORRECTED, same evening, before any code was written:** bytes 151/152/153 are NOT fixed "velocity/LFO2/env2" slots. They are amounts for three PROGRAM-level ASSIGNABLE modulation sources (`MODSFILT1/2/3`, program bytes 84/85/86, selecting from 15 possible sources: none, modwheel, bend, pressure, external, velocity, key, LFO1, LFO2, env1, env2, three inverted variants, env3). On preset 4 specifically, slot 1 happens to be velocity (`MODSFILT1=5`) -- but a reader that assumes byte 151 is always velocity would silently misattribute an LFO or envelope depth to velocity on any program where the assignment differs. **The read-side fix needs the program-level source byte read alongside the keygroup amount byte; they are only meaningful as a pair.**
  - **Reading byte 151 correctly will not, by itself, fully close this patch's gap.** `MODVFILT1` (the velocity-slot amount) is 19/20/20/20 across kg0-kg3 -- uniform, not what distinguishes the quiet keygroups from the loud ones. What DOES differ is `MODVFILT3` (env2's own filter-frequency amount): 30/30 on the quiet keygroups (kg0/kg1) against 39/39 on the loud ones (kg2/kg3). **RESOLVED, same evening: `MODVFILT3`/byte153 is already correctly read and modeled** -- it IS `env2_depth`/`filter_env_cents` (`AKAI_ENV2_DEPTH_OFFSET = 153`, same byte), not a separate or redundant field, so there was never a second path to reconcile. s3ked's own §156 law (`octaves = 0.002612 x SUSTN2 x depth`, measured with the envelope parked at sustain) initially looked like it disagreed with this project's `filter_env_cents` values (kg0 9005 ct vs kg1 8628 ct despite identical `MODVFILT3`=30, `SUSTN2`=12) -- traced to `_env2_amount()` (`parsers/akai_s3000_parser.py:283`) deliberately computing the envelope's PEAK excursion rather than its sustain-settled value, per an EARLIER, already hardware-confirmed fix (§AKAIENV2PEAK, 2026-08-25 -- the old sustain-based version audibly removed the attack transient, "the click is gone" on a converted EP). Two different quantities measured correctly by two different (correct) methods, not a bug. The peak-excursion formula clamps to an absolute Hz ceiling and derives its amount from each keygroup's own FILFRQ base, which is why kg0 (FILFRQ position 43.29) and kg1 (53.80) diverge despite identical `MODVFILT3`/`SUSTN2`. **No code needed here.**

**Status: (1) v=100 FIXED and HW-confirmed same evening (see above). (2) v=40 root-caused but deliberately not implemented tonight** (Jan's call, given the hour and that it touches AKAI-as-source broadly, not just this one patch) -- scope for whoever picks it up: read the program-level `MODSFILT1/2/3` assignable-source bytes (84/85/86) alongside the keygroup amount bytes (151/152/153), and only populate `velocity_to_filter_cents` when the relevant slot's source is actually velocity. `env2_depth`/`filter_env_cents` (byte153/`MODVFILT3`) needs no change -- confirmed already correct, not a second field to reconcile. Next session should start from this entry rather than re-derive it. |
| **AKAI->KRZ: the reference preset has "way too much vibrato" by ear (Jan) -- three real causes checked and ruled out, no explanation found yet** | *(2026-08-30/31, extensive s3ked collaboration, following on from the split patch 1 / split patch 3 velocity-thinning work)* Jan's own listening on the K2000 side: the reference preset's pitch modulation reads as far too extreme against the AKAI reference. Three independent, real, correctly-measured mechanisms were checked and each ruled out as the (sole) explanation:

  1. **LFO depth scaling** -- confirmed correct. `AKAI_LFO_RMS_CENTS_PER_PRODUCT = 0.13127` (this project's own constant) matches s3ked's fresh §160 hardware measurement to 5 decimal places; computed RMS cents for the reference preset's real LFODEP=8/L_PTCH=7 (7.351) matches s3ked's measured 7.35 almost exactly. The multiplicative L_PTCH gate-and-scale law is already correctly implemented (a nearby docstring in `models/common.py::akai_lfo_depth_to_pitch` still says "does not yet SCALE" -- that text is stale, the code already does; worth fixing the comment separately).
  2. **LFO waveform shape -- FIXED 2026-08-31 (§AKAILFOWAVE), confirmed to NOT move the reference preset.** The AKAI parser now reads `LFO1WAVE` (program byte 97) and both selects the matching K2000/E4B shape (`voice.lfo1_shape`) and the correct RMS-to-peak factor (`models/common.py` `AKAI_LFO_WAVE_RMS_TO_PEAK`). s3ked's §46 hardware measurement (pitch-tracking LFO1's own output shape) gives the real mapping: 0=triangle, 1=sawtooth (same sqrt(3) factor as triangle), 2=square (1.0, a 73% LOWER factor than the triangle guess every prior conversion used), 3=random (named from the S3000XL manual itself, flitemedia.com S3000XL.PDF p.80, Jan 2026-08-31, after §46's own pitch-shape measurement could get it real but not name it) -- factor left at sqrt(3) as an UNMEASURED stand-in; a same-night uniform-distribution derivation was proposed and withdrawn (s3ked: §46's own 0.16 "time near centre" reading rules out uniform, most likely meaning sqrt(3) OVER-estimates value 3's peak -- direction known, number not; s3ked has offered a 10-minute direct measurement, not yet run, doesn't touch the reference preset). the reference preset's own `LFO1WAVE=0` (triangle) was already the hardcoded assumption, so this closes a real bug for OTHER programs (square in particular, previously 73% too loud) without changing the reference preset's own numbers at all. **New open question raised by Jan:** the K2000-side factors (sqrt(3)/1.0) are still textbook math against a byte<->LCD-LABEL confirmation only (2026-06-17) -- nobody has audio-measured what the K2000's own "Square"/"Triangle" LFO shapes actually output the way §46 did for the AKAI. Asked of k2kremote, queued behind the current CAL[22] sweep.
  3. **Mute-choke handling -- structurally different from the AKAI, but small in practice.** The AKAI source is 3 identical-key-span `KGMUTE` 0 pairs (confirmed both via s3ked's live SysEx read and this project's own raw keygroup parse -- 6 keygroups, `24-59`x2/`60-71`x2/`72-127`x2, all `mute_group=0`); only ONE voice per pair survives choke, and per §168 it's always the higher-index (vibrato'd) keygroup, so nothing dry ever sounds on the real machine. This project's `_apply_mute_groups` deliberately does NOT delete the losing keygroup -- it reshapes its envelope into a fast click-to-silence cut and KEEPS it as a separate voice (by design, to model the choke's exact timing rather than approximate it), so the converted output carries a 4th voice the AKAI doesn't have (the three losers, disjoint-key-fused into one). Checked the actual envelope on that extra voice: `attack=0, decay=0.058s, sustain=0, release=0` -- and separately verified `AKAI_MUTE_CUT_SECONDS=0.058` is a LINEAR-IN-DB ramp (97 dB over 58ms) already calibrated to match §155's own hardware curve almost exactly (13.4/20.1 dB down at 8/12ms against §155's measured 13.1/20.7 -- a near-exact match, NOT the ~18dB gap a same-evening amplitude-linear miscalculation briefly suggested and then correctly withdrew). So the extra voice is real and structurally different from the source, but its audible footprint should be a brief, correctly-timed click, not a sustained dry layer under the vibrato.

  **None of the three, individually or combined, obviously explains "way too much".** Reusable AKAI-side reference measurements (s3ked, `~/temp/s3ked-logs/lforate/`), **CORRECTED 2026-08-31 (second pass, `TC10 NOISE`, time-domain centroid oscillation, not sideband spacing)**: **LFO1 rate 3.757 Hz** -- the ORIGINAL sideband measurement (4.120 Hz) is WITHDRAWN, it was measuring the distance to a detuned beating partial in the electric-piano material, not the LFO sideband; the fitted law `Hz = 0.11867*LFORAT - 0.04` needs no correction after all, confirmed to +-0.016 Hz mean error against a clean noise carrier across 4 LFORAT values. **~8.7 cents peak / ~6.2 cents RMS** (revised from the same rate correction; still approximate, from the same possibly-contaminated spectrum, but agrees with §160's independently-predicted 7.35 cents RMS within 16%).

  **MAJOR FINDING, 2026-08-31, actual K2000-side measurement (k2kremote, eosed's sideband tool on captured audio from the live program):** the tool REFUSED to give a clean number for note 48 on the loaded the reference preset (802) -- the actual deviation is too large for its safe integration-band range, which is itself informative rather than a failure. Rough estimate from the refused band width: **~180 cents RMS, roughly 27-29x the AKAI reference.** This is finally in "way too much" territory, unlike any of the three ruled-out mechanisms above.

  **Writer confirmed innocent of the depth math**: computed the exact CAL[22] byte my code would write for the reference preset's real depth (0.008 fraction) -- **byte 13** -- which decodes back through this project's own reader table to "13 cents", matching k2kremote's live panel readback (`Depth=13ct`) exactly. So the programmed value is correct; the gap is downstream of a correctly-written byte.

  **Leading hypothesis: the LFO-depth byte<->cents calibration table (§KRZLFOPITCH) was only ever hardware-confirmed by real audio at TWO points -- byte 79 and byte 41.** Everything below that assumes a straight ("1:1") line from byte 0, unverified -- and §KRZLFOPITCH's own writeup already records that the one attempt to confirm a low byte (byte 4) came back "below the tracker's ~9-10 ct resolution... unresolvable rather than measured" at the time. Byte 13 (what the reference preset actually uses) sits in that same never-validated region. If the true curve is not 1:1 down there -- plausible, this shape of curve is often compressed near zero, and this project has been burned by exactly this shape of error before on OTHER envelope/depth fields -- byte 13 could genuinely produce far more than 13 cents on real hardware, matching the ~180 ct estimate.

  **First sweep run 2026-08-31, on the WRONG material -- withdrawn, superseded below.** k2kremote's first pass swept CAL[22] bytes 5/10/13/20 on the reference preset's own Layer 2 (note 48) and read every byte as 5-10x its nominal value, non-monotonically -- but on the SAME electric-piano material whose beating/detuned partials had already fooled s3ked's rate measurement earlier that evening. Not trusted, and correctly not trusted: see below.

  **CALIBRATION TABLE CLEARED, 2026-08-31 late, clean re-measurement.** k2kremote re-swept the same 4 bytes on the rebuilt clean-material test program (ROM keymap 151 Sawtooth, LFO1 wired to pitch), throttled correctly this time (>=150ms, root cause of an intervening K2000 MIDI-flood hang fixed): byte5 rms 3.60+/-0.10ct, byte10 rms 7.13+/-0.20ct, byte13 rms 9.16+/-0.22ct, byte20 rms 14.16+/-0.39ct. Converting each to a peak assuming a SINE-shaped LFO (rms*sqrt(2)) gives 5.09/10.09/12.95/20.03 -- **peak_cents == byte, essentially exactly, at all 4 points, tight error bars throughout.** `KRZ_LFO_PITCH_CENTS`'s low-byte region is NOT miscalibrated. The leading hypothesis from the last several hours is **RULED OUT**. The first sweep's 5-10x-too-large, non-monotonic numbers are now understood as pure contamination from the reference preset's own material, the same failure mode as s3ked's rate mismeasurement, confirmed on the depth axis too.

  **So the ~180ct/27-29x gap is real (the K2000-side sideband measurement was on live the reference preset audio, not a calculation that could inherit this contamination) and its cause is NOT in the byte-to-cents table.** Two live leads instead, neither chased yet:
  1. **A rate discrepancy on the SAME clean test program, found incidentally.** Measured LFO rate reads a consistent 3.01 Hz regardless of the panel's `MnRate` field (tried at both 2.00 Hz and 1.00 Hz displayed, measured rate didn't move) -- panel and actual output disagree. Not yet chased. Could matter here specifically because a rate this project's own writer *thinks* it is producing, if it differs from what the machine actually does, might interact with the depth or with the sideband tool's own frequency-domain analysis in a way that reads as "more vibrato" than the true peak-cents figure alone would predict -- untested, not confirmed, just a live thread.
  2. **Isolating the reference preset's own vibrato'd layer directly**, proposed by k2kremote and the natural next step now that the generic calibration is cleared: use the Enable field to silence every keygroup except the one LFO1 actually reaches, and do a longer, cleaner capture on it alone -- removes whatever about the full electric-piano mix (other layers, the mute-cut click voice, beating partials) might be inflating the sideband tool's estimate on the real patch, the same way clean material fixed the last two false leads.

  **Isolated-layer capture done, 2026-08-31 late/09-01 early -- rules out layer contamination cleanly.** k2kremote silenced every keygroup except the vibrato'd one (Enable=OFF on Layer 1) and captured Layer 2 alone, note 48, 8s hold: same refusal as the unisolated capture (`53 Hz needed, reaches the 130 Hz neighbour` vs the original `57 Hz`/`131 Hz` unisolated numbers -- same shape). **The huge deviation is intrinsic to Layer 2 itself, not layer-interaction or beating with Layer 1/the mute-cut click voice.** Layer 2's PITCH page reads identical in structure to the clean sawtooth test program that measured correctly (Coarse=0ST, Src1=LFO1, Depth=13ct, nothing else touching pitch) -- same parameters, wildly different behaviour, which is what sent the search toward the zone/keymap content itself rather than any modulation-routing field.

  **FOUND, same session: real bug, `writers/krz_writer.py` never read `zone.coarse_tune` (§KRZCOARSETUNE, FIXED 2026-08-31).** Reading the reference preset's AKAI source directly (`MXS3.hda`) rather than guessing: the surviving vibrato'd keygroup covering note 48 (`sample A`, root 48) carries `coarse_tune=12` -- a full OCTAVE of AKAI TUNE. The E4B and AKAI writers both already read this field; the K2000 writer silently dropped it, so this zone was written to K2000 output missing its intended +1200 cents entirely. Fixed: `tuning` now includes `coarse_tune*100`, and the up-pitch ceiling check (which must stay consistent with what `tuning` contains) now evaluates against `r_zone - coarse_tune`. New test `tests/test_krz_writer.py::test_coarse_tune_reaches_the_keymap_entry`, confirmed to fail on revert.

  **Whether this explains the vibrato-depth gap is NOT established -- and the fix does not cleanly resolve even the pitch question for THIS specific zone.** LFO-to-pitch modulation is proportional (cents), so a static octave error should not, on its own, inflate a correctly-measured cents figure -- if there's a connection, it is more likely that a wrong-octave carrier throws off the sideband tool's own harmonic-neighbour band assumptions (which is the exact shape of its refusal: a required integration band reaching an unexpected neighbour). **Computed directly, not assumed:** with the fix applied, `sample A` (44100 Hz, root 48, coarse_tune=12) needs an effective ~88.2kHz playback rate at its own root note -- genuinely over the K2000's 48kHz internal ceiling. Note 48 (the exact note tested all night) lands at key 48, ceiling computes to key 37 -- **so even fixed, note 48 does not get a clean, fully key-tracked +1 octave; it gets the existing ceiling-clamp behaviour** (tuning frozen at key 37's value, same as any other zone whose top keys exceed their sample's up-pitch ceiling). Keys 24-37 of this zone DO get the correct, fully key-tracked result. This may be a genuine AKAI/K2000 hardware-capability gap (the S3000XL's own playback-rate ceiling, if it has a comparable one, is not established) rather than a further converter bug -- not yet checked.

  **Rebuilt, transferred, re-measured, 2026-08-31 morning.** Rebuilt `FROM_S3.KRZ` with ONLY the coarse_tune fix (the v40 velocity->filter fix was deliberately stashed out of the build first, to avoid confounding this specific re-measurement -- same discipline as the original v40 hold-back decision), wrote it into `HD5-MATRIX.hda`'s `BANKS/FROM_S3.KRZ` on the card (backed up first, write verified byte-identical on read-back), card physically swapped back into the K2000 by Jan. k2kremote reloaded and redid the isolated-layer capture on note 48:

  ```
  CANNOT MEASURE: the band needed (77 Hz) would reach the neighbouring harmonic at 150 Hz
  ```

  **The fix is confirmed active** -- the carrier moved from 130 Hz (pre-fix) to 150 Hz (post-fix), real movement, not a no-op, and consistent with a PARTIAL correction (150 Hz is nowhere near the ~261 Hz a full clean octave-up would put it at, matching the predicted ceiling-clamp at this specific note). **But the underlying refusal is NOT resolved** -- still cannot measure, if anything the needed band grew in absolute Hz (though that may just track the higher carrier rather than reflect a larger relative/cents deviation; not computed either way since it never resolved to a number). **So coarse_tune was real and worth fixing, but it is NOT (by itself) the explanation for the "way too much vibrato" gap, at least not provably at note 48 specifically** -- which was never a fair test of the fix anyway, since it sits above this zone's up-pitch ceiling regardless.

  **Next, proposed by k2kremote, approved:** test a note comfortably inside the ceiling (24-37, e.g. note 30) with the same isolated-layer setup. This is the first CLEAN test of the coarse_tune fix (no clamp involved) and separately answers whether the persistent refusal is a general property of this vibrato'd layer (would also show up on a fully-corrected note, meaning coarse_tune was a red herring for the depth mystery) or specific to the ceiling-clamped/hole-filled region (would measure cleanly in-range, pointing at some interaction between LFO modulation and a frozen, non-keytracking tuning value at the clamp boundary).

  **Note 30 (in-range, isolated Layer 2 only) run, 2026-08-31 morning: SETTLES IT -- coarse_tune was a red herring.** Carrier locked to 92 Hz, exactly 2x the naive ~46 Hz expectation for note 30 -- confirms the fix applied a full, clean +12-semitone correction here with NO ceiling clamp, the fair test. Same refusal anyway: `53 Hz needed, reaches the 92 Hz neighbour` -- essentially the same magnitude as note 48's clamped case. **The coarse_tune fix is real, worth keeping, and confirmed correct where it applies cleanly -- but it is NOT the cause of the vibrato-depth mystery.** Back to square one on WHY Layer 2's real pitch deviation runs so much higher than its own Depth=13ct parameter predicts: confirmed correct on the clean sawtooth (calibration table cleared), confirmed not layer-1/beating contamination (isolated capture, same result both times), now confirmed not tuning/ceiling-clamp related either (clean in-range note, same result).

  **New hypothesis, 2026-08-31 morning, not yet tested: the filter envelope, not the LFO, may be what the sideband tool is actually reacting to.** Reading Layer 2's FULL parameter set (not just the PITCH page) off the AKAI source: `filter_env_cents` ~3862 (almost 4 octaves of cutoff sweep), decay 3.86s, release 1.27s, resonance 0.73 -- a large, continuously-evolving change to the voice's spectral envelope, active on the same multi-second timescale as the whole 8s capture window, entirely independent of the LFO1->pitch routing. A sideband-based FM-depth estimator generally assumes a roughly static spectral envelope; a filter sweep this large moving through the capture could plausibly read as broadband spectral movement and get misattributed to pitch deviation, or push the tool into exactly the "needed band reaches the neighbouring harmonic" refusal shape it keeps hitting -- independent of what the LFO is actually doing.

  **Filter envelope zeroed on note 30, isolated Layer 2, 2026-08-31 morning: ALSO ruled out.** Same refusal exactly (`53 Hz needed, reaches 92 Hz`) with the filter envelope depth at 0 -- peak level dropped (0.0086 vs 0.015, confirming the change genuinely took effect and altered the sound) but the pitch-deviation measurement itself did not move at all. In hindsight this tracks: a sideband/phase-tracking method locked onto the fundamental shouldn't be affected by the filter reshaping OTHER harmonics' amplitudes. **Four things now ruled out: calibration table, layer-1 contamination, coarse_tune/ceiling clamp, filter envelope sweep.** Whatever is actually driving this remains unidentified and has survived every control applied so far.

  **Second coarse_tune bug found and fixed the same morning, upstream of the first: `convert.py`'s resample-headroom step had the identical gap.** It also computed required up-pitch headroom from `hi_key - root_note` alone, missing `zone.coarse_tune` -- so `sample A` got resampled to 25427 Hz (enough for 11 semitones) instead of the ~24000 Hz floor its real 23-semitone requirement needs. This is WHY the first coarse_tune fix (the keymap-tuning half) still left note 48 hitting the up-pitch ceiling: the ceiling was computed correctly from the sample's rate, but the rate itself was wrong going in. Fixed (extracted into `krz_needed_up_semitones()` in `convert.py`, unit-tested, 5 tests, confirmed to fail on revert) -- with both fixes together, the math says note 48 should land exactly at the ceiling boundary (fully covered) instead of clamped at key 37. Rebuilt (still excluding the v40 fix) and transferred to the card. **Note 48 (both fixes), 2026-08-31: FIRST CLEAN MEASUREMENT ALL NIGHT.** `carrier 260.78 Hz, mod 3.79 Hz, rms 9.66+/-0.73 ct, peak-sine 13.66ct, C/N 116.6dB, contained 100%` -- no refusal, clean full 100%-contained integration. Carrier is a clean octave-up (260.78 Hz, ~C4), confirming the ceiling is now fully cleared as predicted. Peak-sine (13.66ct) matches the programmed Depth=13ct within the measurement's own uncertainty.

  **But note 30, retested on the SAME fully-fixed build: byte-for-byte identical failure to before -- unchanged by either fix.** `53 Hz needed, reaches 92 Hz` -- exactly the same numbers as the pre-downsample-fix run. So the earlier "coarse_tune is a red herring" conclusion (drawn from an incompletely-fixed build) was itself premature, but not simply wrong either: **note 48 goes from totally broken to clean with both fixes; note 30, same zone, same fixes, stays exactly as broken as it always was.**

  **Sharper hypothesis, 2026-08-31 late morning, not yet tested: this may be about real-time key-tracking auto-transpose, not the AKAI content at all.** Note 30 and note 48 are the SAME single zone (no keygroup/zone boundary between them) -- but they ask the K2000 for very different things: note 48 = root_key exactly, so the whole +12-semitone shift comes from the STATIC `coarse_tune` field alone, with ZERO real-time auto-transpose. Note 30's total shift is `(30-48)+12 = -6` semitones, made of a real `-18` semitones of live key-tracking auto-transpose partially cancelled by the same `+12` coarse_tune. **If LFO-to-pitch depth is only correctly "byte=cents" when no real-time auto-transpose is happening underneath it, and distorts once the K2000 is ALSO doing its own pitch-shift interpolation on the same voice, that would be a general K2000 hardware behavior, unrelated to AKAI content or coarse_tune specifically.** Sharpest possible test: run the ALREADY-validated clean sawtooth test program (peak_cents==byte at bytes 5/10/13/20, but always tested AT its own root key) at a note AWAY from its root instead. If byte=cents breaks down there too, this is confirmed as a general effect and explains everything seen tonight without any further AKAI-specific theory needed. **CONFIRMED, 2026-08-31, on clean synthetic material -- this is real and it is not a converter bug.** k2kremote rebuilt the calibration test program (the earlier one was wiped by Master->Delete->Everything) and tested it at its own root key (note 48: matches the original calibration exactly, rms 3.60ct) and 6 semitones off root (note 42, same program, same Depth=5): carrier correctly locked to 92Hz (so playback pitch itself is fine) but **CANNOT MEASURE, same refusal shape as every failed the reference preset reading tonight** -- on a synthesized sawtooth with zero AKAI heritage, zero coarse_tune, zero resample history. **This is a general K2000R hardware behavior, not specific to the reference preset, AKAI content, or anything this project's writer does.** Full write-up moved to its own entry, §KRZROOTLFO below -- this one closes here: the reference preset's coarse_tune fixes are real, correct, and hardware-confirmed; whether they're "enough" for Jan's actual complaint now depends on where in the keymap he plays it, which is a listening question, not a further measurement one.

  **Before the next listening pass: verify the A/B comparison conditions themselves** (s3ked's suggestion, worth doing first, costs nothing) -- same program, same notes, same velocity, matched output levels between the AKAI and K2000 sides. Tonight's earlier release-length investigation (see the AKAI->E4B release-rate entries above) dissolved for hours before it turned out Jan had been comparing against a different AKAI preset on channel 16 -- a listening comparison is a measurement with its own failure modes, and confirming the comparison itself is set up correctly is cheaper than another round of parameter measurement.

  **UPDATE: no longer blocked on a listen -- superseded by the actual measurement above.** k2kremote read the panel directly (rate/depth both checked, neither an obvious smoking gun on paper) and then captured and analysed the real audio, which is what found the ~27x gap. See the calibration-table hypothesis and its own blocked-on, immediately above. |
| ~~**K2000R LFO1->pitch depth reads correctly only at (or near) a voice's own root key**~~ **WITHDRAWN 2026-08-31, same day -- was the checker's own analysis window, not a hardware effect (§KRZROOTLFO)** | *(2026-08-31, found and withdrawn the same day while investigating the reference preset's vibrato)* Originally reported "HW-confirmed, general, not converter-specific" on the strength of a K2000-native calibration program measuring clean at its own root key but refusing 6 semitones off root. **k2kremote caught their own false positive on re-check:** the sideband tool's analysis window defaulted too short (~2.25s) to resolve this program's actual ~2Hz LFO rate (a slow modulation needs several full cycles -- "2.5 bins" -- to resolve, which a short window doesn't give it). Every refusal attributed to root-vs-transposed position, including the original note-42 capture, **resolves cleanly once the window is extended to match the LFO period** -- note 42 (6 semitones off root): rms~3.6ct, peak-sine~5.1ct, matching Depth=5's calibration almost exactly. **A full 11-point sweep at Depth=2 across +/-12 semitones (the characterisation Jan asked for, "essential to proceed"), captured correctly and analysed with a properly extended window, resolved CLEANLY AT EVERY POINT: rms 1.26-2.0ct throughout, matching calibration, no distortion anywhere in the range.** There is no root-vs-transposed LFO depth effect. Caught by the same discipline (extend the window, see if the refusal survives) k2kremote had already applied earlier the same night to the ORIGINAL calibration sweep's Depth=13/20 refusals, which DID survive that check and are not implicated here.

  **the reference preset's own refusals are NOT withdrawn by this -- they are a structurally different failure mode** (a "band needed X Hz reaches the neighbouring harmonic Y Hz" bandwidth/harmonic-collision limit, not the "under N bins" window-resolution limit that caused this false finding), and several already persisted at a window as long as t1=7.5s -- some evidence they are not simply the same artifact. But given how confidently wrong this finding was, that should not be treated as settled without deliberately checking whether the reference preset's own refusals shrink or persist as ITS analysis window is pushed further, the exact same check that caught this one. **Systematic re-check done, 2026-08-31 midday: note 30's refusal is REAL, not the window artifact.** Seven runs at t1 = 2.6/3.5/4.5/5.5/6.5/7.5/8.5s, t0=0.35 throughout: identical refusal every time (`53-54 Hz needed, reaches 92 Hz`). k2kremote's own physical argument for why this is a genuinely different failure class, not a rerun of the same mistake: the window-artifact refusal was "modulation rate under 2.5 bins in a sub-window" -- a frequency-resolution problem where `bin_hz = sr/sub_len` shrinks (and the refusal clears) as the window grows. THIS refusal is "required sideband bandwidth collides with the neighbouring harmonic" -- both the needed bandwidth (fixed by modulation depth/rate) and the neighbour's frequency (fixed by the carrier) are independent of window length by construction, so there is no adjustable quantity a longer window changes. Confirmed real, not an artifact of this specific kind.

**Hypothesis raised (sample's own natural character) and superseded the same day -- SOLVED, 2026-08-31 afternoon: it was a second, unrelated bug in the sideband tool itself, not the K2000, the converter, or the sample.** A loop-boundary click in `sample A` was found and checked directly (a real, small ~1.7-2% discontinuity, present identically in both the original 44.1kHz recording and the resampled 24kHz output -- our resampler carries it through faithfully, doesn't introduce it) but ruled out cleanly: the loop is EXACTLY one fundamental period (336 samples @ 44100Hz = 1/131.25Hz), so mathematically a click there can only add energy AT the harmonics, not at a separate frequency the tool could see as an anomalous "neighbour." A ROM-native acoustic piano at the same Depth measured cleanly across a full octave off-root, arguing against a general real-timbre effect too.

  **The actual mechanism, found by eosed reading their own tool's source rather than reasoning about it from outside:** a hard-coded guard, `half = 14*mod; refuse if half >= carrier*0.40` -- equivalent to refusing whenever `mod >= carrier/35`. At note 30's 92 Hz carrier that is a ceiling of **2.63 Hz** of measurable LFO rate; the reference preset's own LFO runs at ~3.76 Hz. **This zone was never measurable by this tool, at any depth, independent of coarse_tune, the octave fix, the sample, or anything about the K2000** -- the octave-correction fix actually made it MORE measurable, not less (at the old, un-fixed 46 Hz pitch the ceiling would have been 1.3 Hz). Two real bugs in the tool surfaced by this: its refusal message prints the CARRIER frequency labelled as "the neighbouring harmonic" (which is what made this look like a harmonic-collision problem for hours), and `carrier_lo` defaults to 150 Hz, so any run using tool defaults against a sub-150Hz carrier would silently lock onto the wrong peak.

  **Conclusion: nothing further to chase.** Both real converter bugs found tonight (the keymap-tuning and resample-headroom halves of §KRZCOARSETUNE) are fixed, tested, and hardware-confirmed correct where actually measurable (note 48: clean, matches the programmed 13ct). Note 30's persistent refusal is fully accounted for by a measurement-tool limitation, not a defect anywhere in this project's output or on the K2000. eosed's own suggestion, and the right one: don't spend more hardware time on this specific note with this tool -- treat the LFO rate as voice-global (already measured cleanly at note 48) rather than trying to force a number out of a carrier this tool cannot resolve. **The remaining open question is Jan's own, by ear:** does the corrected the reference preset build sound acceptably close to the AKAI reference now, across the range he actually plays it. Not a further measurement question.

**Loose end from eosed's own fix, CLOSED same afternoon:** `carrier_lo` defaults to 150 Hz, and a run relying on that default against a carrier below 150 Hz would have silently locked onto a harmonic instead -- checkable-after-the-fact, and checked. k2kremote grepped the actual `measure()` calls in all three scripts directly rather than trusting memory: the Depth=2 sweep scales `carrier_lo = expected_hz*0.75` per offset (the -12 semitone point got `carrier_lo=49.0`, not 150), both ROM instrument tests use `hz*0.6`, and even the original note-30 re-check passed `carrier_lo=30.0` explicit. None of tonight's runs ever hit the default. Every "clean" result stands as measured.

**REOPENED, 2026-08-31 afternoon -- Jan's own listening test on the combined build finds the vibrato survives with Layers 2/3 disabled, i.e. it is coming from LAYER 1, not the layer this entire night's investigation was built around.** Jan isolated K2000 Layer 1 alone and confirms it "throws this conversion over the edge" by itself; handed the lead over for about an hour. Layer 1 is the mute-cut "click" voice (§AKAIMUTESCOPE) -- `lfo1_to_pitch=0`, envelope `attack=0, decay=0.058s, sustain=0, release=0` -- checked its actual written bytes directly (not assumed): `cal[21]=0` (LFO1->pitch cord genuinely off, matches the #199 template default, never patched since the AKAI-side gate that sets `lfo1_to_pitch` was false for this voice). The nonzero `lfo1_rate`/`lfo1_shape` a naive readback shows are template leftovers on an UNROUTED cord -- harmless, not a bug (verified against `_TPL_LAYER`'s own default CAL bytes in `writers/krz_writer.py`). So this is NOT the LFO1-depth story from the rest of tonight.

**Leading hypothesis: §KRZENVLOOP, not a new bug -- Layer 1's envelope is close to a worst case for an already-documented, already-HW-confirmed K2000 defect.** §KRZENVLOOP (2026-08-27, this file, above) found a KRZ envelope held past its own Att+Dec+Rel total RE-CYCLES instead of holding at silence -- confirmed genuine K2000 firmware behavior, not this project's bug, cause still open. **Its own original test case, `SPACE_ISO2`, was built around the EXACT SAME component sample as the reference preset's Layer 2/3 zones** (loop points 51646-51982 match `sample A` exactly) -- this the reference preset investigation and that one share a sample, previously unnoticed. That measurement found a ~11.6s re-cycle period on a 5.1s decay + 6.5s release envelope -- period roughly EQUAL to the envelope's own Dec+Rel total (11.6/(5.1+6.5) approx 1.0). If the same ratio holds, Layer 1's 0.058s decay (and 0 release) predicts a re-cycle period on that same order -- **roughly 15-20 Hz of repeated amplitude retriggering**, squarely in "sounds like an unwanted vibrato/flutter" territory, on a voice explicitly designed to be a brief click and never meant to be held. This would also mean the re-cycle bug, not LFO1 depth, may be a real contributor to the ORIGINAL "way too much vibrato" complaint in the full mix, not just Layer 1 in isolation.

**Sharpened by s3ked into a falsifiable, two-point test rather than one confirmation.** `1/0.058s = 17.24Hz`, dead centre of the predicted 15-20Hz band -- not a coincidence to argue for, since if this is the re-cycle bug the flutter frequency IS the envelope's own repeat rate. The real test: set Layer 1's decay to 0.040s (predicts 25Hz flutter) and separately to 0.100s (predicts 10Hz) -- one panel edit per point, no rebuild. **If the flutter frequency tracks 1/T across those two points, that is about as strong a confirmation as this gets; if it stays put regardless of T, the hypothesis dies cheaply and this needs a different explanation.** Sent to k2kremote, not yet run.

**Explicitly NOT a decision to change `AKAI_MUTE_CUT_SECONDS` (0.058s) yet, and s3ked's own framing on this is the one to keep:** that constant is a MEASUREMENT of the AKAI (§155, linear-in-dB fit to hardware data), not a tuning knob -- if the re-cycle hypothesis confirms and a workaround is ever adopted, it must be recorded as a deliberate K2000-target-specific deviation from the source figure, with its own reason, never as a refinement of what the AKAI actually does. s3ked also flagged a real gap in their own §155 measurement worth having before any such decision: the AKAI-side data floors at -21.56dB/30ms (a limit of the OLD measurement technique -- the choke's surviving layer was only quieted, not silenced, so below ~-20dB relative the technique was measuring the wrong layer), so the AKAI's true cut duration past 12ms is presently unmeasured, and that number is exactly what would bound how far any workaround duration could reasonably go. **s3ked has a better technique ready** (make the choke's SURVIVING layer close its own amplitude envelope instantly -- ATTAK1 0, fastest DECAY1, SUSTN1 0 -- so it still chokes but stops masking the cut layer's tail) and can run it inside half an hour, but is correctly holding until the re-cycle hypothesis is confirmed or killed first, since if it's killed the whole question of moving 0.058s doesn't arise.

**Strong confirmation, 2026-08-31 afternoon, before the two-point test even ran.** k2kremote isolated Layer 1 exactly as Jan had (verified Enable state on the device before capturing), held note 48 for 6s, measured the raw RMS envelope: **clean, rock-solid periodic retriggering at 10.03Hz (std 2.9ms), 61 bursts across the hold, first at 0.379s, last at 6.361s (right up against note-off).** Not a decaying single click at all -- a repeating attack-decay burst for the ENTIRE duration, easily visible in the raw envelope with no signal processing needed. The device's own AMPENV page also shows `Loop: seg3F / Inf` explicitly set on this envelope (not `Off`) -- an actual infinite loop mode, not just an ambiguous "held past total" state; whether that's causally what triggers the recurrence (vs. incidental to it, given the original §KRZENVLOOP investigation found the SAME recurrence with Loop=Off explicitly set on a different object) is not yet resolved and worth checking for consistency across other layers later.

**A second, striking anomaly found while confirming which field to edit for s3ked's test: our writer may be putting the decay value in the wrong envelope stage.** `_fill_env` (`writers/krz_writer.py`) intends a mute-cut envelope (attack=0, decay=0.058, sustain=0, release=0) to write `(Att1,Att2,Att3,Dec1,Rel1,Rel2,Rel3) = (0,0,0,0.058,0,0,0)` -- the 0.058s value in **Dec1**. k2kremote's panel readout (`0.01 0.01 0.06 0.01 0.01 0.01 0s`) instead shows the large value at **Att3** and a near-zero floor at Dec1 -- every other field matches the expected "near-zero floor" pattern cleanly, so this reads as a clean two-field SWAP (Att3<->Dec1), not a general shift. Possibly a real, separate writer bug (distinct from the re-cycle question) -- not yet confirmed at the byte level, and not blocking the flutter test since Att3 is empirically where the 0.058s value actually landed regardless of what it should be called.

**A possible resolution that fixes AKAI fidelity and the K2000 issue as the same change, found in parallel by s3ked while waiting -- §155's own measurement floor closed.** The old technique (quieting the choke's surviving layer via `VLOUD1`) floored at -21.56dB/30ms because below there it was measuring the wrong (quiet-but-still-triggering) layer. New technique (silence the survivor via ITS OWN envelope instead -- `ATTAK1 0, DECAY1 0, SUSTN1 0` -- so it still chokes but stops masking the cut layer's tail), control-checked (a real -23.18dB cut at 12ms against the uncut reference, confirming the choke fires regardless of what the survivor's own envelope does): **the AKAI's real cut is NOT one linear ramp -- it is fast fall to ~-23dB by 12ms, a PLATEAU to ~30ms, then a much slower second fall reaching -60dB by 200ms and still audible past that.** Our current model (0.058s, linear-in-dB, matches to 0.3dB at 8ms) is only right for the first ~12ms and is 40+dB too quiet by 80ms -- it goes fully silent at 58ms while the real machine is still audible past 200ms. **If modeled as a proper two-stage curve instead of one short ramp, the resulting K2000 envelope would naturally run far longer than 58ms** -- plausibly past whatever threshold triggers §KRZENVLOOP, with no deliberate K2000-specific workaround needed at all; the AKAI-accuracy fix and the hardware-bug fix would be the same change. Three caveats on the new measurement, all explicitly flagged by s3ked rather than glossed: first 5ms contaminated (survivor still fires a brief attack before self-silencing), 12-30ms region noisy (~3dB scatter, real EP attack transient), 200ms point floor-limited again (a lower bound, not a reading). Not yet acted on -- correctly held pending the flutter-rate confirmation below, since if the re-cycle hypothesis is wrong this motivation goes away (though the AKAI-fidelity improvement would still stand on its own separate merit).

**s3ked's original 25Hz/10Hz predictions REFUTED by the very data point they were meant to explain, caught and corrected before it could mislead the test.** period=T (their first model) predicts 17.24Hz at T=0.058s; k2kremote measured 10.03Hz. Three models now compete instead: (b) `period = T + 41.7ms` (fixed per-cycle overhead), (c) `period = 1.719*T` (proportional, envelope runs long), (d) a fixed ~10.03Hz rate independent of T entirely -- which would kill the whole re-cycle hypothesis. Predictions at the two test points: (b) 12.24Hz/7.06Hz, (c) 14.54Hz/5.82Hz, (d) 10.03Hz/10.03Hz -- (b) and (c) still differ from each other by ~20% at both points and from (d) at a glance, so the same two-point test still discriminates cleanly, just against corrected numbers. Relayed to k2kremote before they finished interpreting their run.

**CONFIRMED, 2026-08-31, definitively -- Jan's "the vibrato is coming from Layer 1" is real, and the cause is §KRZENVLOOP, not an LFO/pitch bug at all.** k2kremote measured all three points (switching mid-run from peak-picking to onset-detection when the 0.100s capture's multi-lobed bursts confused the peak-picker; re-ran the 0.058s point through the same corrected method as a cross-check, not mixing techniques across points): 12.29/9.86/7.05 Hz at Att3=0.040/0.058/0.100s, against model (b)'s 12.24/10.03/7.06 Hz -- 0.1-1.7% error across all three, (c) and (d) both clearly excluded. See the main §KRZENVLOOP row (top of this file) for the general mechanism now characterized from this data (`period = decay + ~41.7ms fixed overhead`) and what it does and does not imply for a fix.

**So: Layer 1's own LFO1-pitch routing is genuinely off (confirmed earlier by direct byte inspection), and the "vibrato" Jan hears from it in isolation is actually amplitude re-triggering at ~10Hz from an already-known, now-precisely-characterized K2000 firmware defect, on a voice whose envelope (0.058s, designed as a brief choke click, never meant to be held) is about as bad a fit for it as this project has ever written.** Not yet resolved whether/how to change anything -- lengthening the envelope (e.g. via s3ked's more accurate two-stage AKAI choke-cut curve, found in parallel) would slow the re-cycle substantially but not eliminate it, per the fixed-overhead finding above. Decision on what to actually change belongs to Jan.

**Att3/Dec1 "swap" RETRACTED, 2026-08-31, by reading the actual file bytes directly (not the panel label).** Layer 1's ENV(0x21) segment: `Att1=(3,100) Att2=(3,100) Att3=(3,100) Dec1=(6,0) Rel1=(3,0) Rel2=(3,0) Rel3=(3,0)`. The time-byte encoder floors literal 0.0s at byte=3 (confirmed in code), so every pair reading exactly 3 is a real zero, and Dec1's 6 (not Att3's 3) is the one genuine nonzero value -- correctly placed, matching the writer's own intent. The earlier "swap" was misreading which panel label corresponds to which byte position, not a real writer bug -- dropped.

**REOPENED, sharper, 2026-08-31: the file's own byte 14 (loop flag) reads 0, matching what should mean "Off" -- but the device's panel showed "Loop: seg3F / Inf" for this exact object.** Direct contradiction between the file and the live device, and possibly THE key to why hand-programmed envelopes (confirmed clean, no retrigger, on the final firmware) differ from converted ones.

**Edit-buffer drift RULED OUT** by a fresh-reload control (a never-touched object, DUMP'd before the panel was ever opened, then panel opened for the first time): identical disagreement (Att3-vs-Dec1 placement, Loop=seg3F vs file's 0) reproduces from the very first view. Real and reproducible, not testing history. **AMPENV mode (Natural vs User) RULED OUT from code**, no hardware needed: `_patch_layer` unconditionally forces User mode for every voice, confirmed, no exceptions.

**"Panel vs DUMP disagree" RETRACTED by k2kremote -- their own segment-layout misparse, not a device quirk.** Corrected layout, re-verified against the clean 991/992 single-byte diff: loop byte FIRST (right after the tag), then 7 pairs in (level,time) order -- not (time first, loop last) as assumed. With that fix, device bytes for the reference preset's Layer 1 (602 and fresh-loaded 702, identical) match the live panel exactly, field for field. No display bug.

**What's real instead: a genuine FILE-vs-DEVICE difference.** This project's file bytes (`_fill_env`: time,level pairs, loop last) put the real value at Dec1 with loop=0. The verified device bytes (loop first, level,time pairs) put that same value at Att3 with loop=3. Something between this writer's `.KRZ` output and the K2000's live RAM object is not a straight copy -- reordering pair components and/or shifting which stage the value lands in, and toggling loop non-zero. This is this project's own file-format-vs-RAM-format territory to trace next, not further hardware probing alone.

**Open:** is this specific to Layer 1's DEGENERATE envelope (six near-identical floor-value stages, one real value), or does every envelope this writer produces shift the same way, just invisibly (normal envelopes have no repeated stages to expose it on)? Requested of k2kremote: DUMP Layer 2 (the reference preset's real, non-degenerate, KNOWN-correct electric-piano envelope: decay 5.1s, release ~2.7s) with the corrected parsing and compare against this project's own file bytes for it. Not yet run.

**s3ked's structural-fix idea (nonzero sustain stops the re-cycle if it's completion-triggered) REFUTED, 2026-08-31, cleanly.** k2kremote set Dec1%% 0->30 on the same layer, held 5s: retrigger rate unchanged (9.99Hz either setting), persisting to note-off. Time-based, not completion-based -- see the main §KRZENVLOOP row for the full writeup. **So there is currently no known way to eliminate the re-cycle via envelope shaping, only slow it.**

**Follow-up test (long decay + sustain) initially mis-read a rig bug as two findings; s3ked's suspicion about WHICH one was right, but the two split.** First capture (Att3=1.00s, Dec1%%=30, nominal 5s hold): onset-detection found a spurious first-crossing at t=4.135s absolute instead of the real note-on near 0.4s -- so "collapses at 1.275s, stays flat" was actually just note-off at 5.4s arriving on schedule. **Root-caused directly (not just inferred), per s3ked's follow-up:** t=4.135s is a real acoustic event, and the capture's file ran 10.069s against a requested ~5.9s -- almost exactly the missing ~4.1s is excess leading silence. That one-off script spun up a fresh MIDI/JACK client per call instead of this project's established persistent-recorder pattern (the exact client-churn issue it exists to avoid) -- a capture-pipeline artifact, confirmed, not a detector bug and not real envelope behavior. **k2kremote re-ran clean with an 8s hold and WALL-CLOCK-VERIFIED note-on/off (0.400s/8.401s, from the MIDI send calls directly, not inferred from audio):**

- **"Doesn't extrapolate past T=1.0s" -- RETRACTED.** 7 onsets, evenly spaced at ~1040ms (std 4ms) = 0.96Hz, running continuously from t=1.519s to t=7.761s -- the entire hold, not stopping. Matches `period=T+41.7ms`'s 0.96Hz prediction almost exactly. **The formula is now confirmed at FOUR points spanning a 25x range in T, stronger than before, not weaker.**
- **"Sustain doesn't hold" -- CONFIRMED, cleanly, on the same wall-clock-verified capture.** Trough 0.8-0.9%% of peak during an unambiguously-held note. **This part of the finding stands** -- a real, separate problem independent of the re-cycle bug, potentially affecting every sustaining K2000 patch this project has converted. Not yet scoped or chased further -- past the Layer-1-vibrato scope this investigation started from, needs Jan's priority call on whether/how to pursue it.
| **`--resample` (vintage profiles) chained into an AKAI target: not yet checked whether it respects the AKAI's rate/bit limits** | *(2026-08-30, Jan, recorded for later -- not investigated yet, no repro run)* `--resample emulator2`/`emax1` (`processors/resampler.py::resample_vintage`) stores its output at the profile's own rate -- **27.5 kHz for both current profiles** -- and keeps `bit_depth=16` regardless of the profile's nominal 8-/12-bit character, since "quantization noise is baked in as signal" rather than the container shrinking (see that function's docstring). Neither 27500 is an AKAI-legal rate, so any `--resample`'d sample bound for `--format akai` necessarily takes a SECOND hop through the `[[step_n]] AKAI playback-rate snap` in `convert.py` (`akai_target_rate(27500) == 44100`, an upsample via `resample_to_rate`) before it ever reaches `build_sample`. Two things nobody has checked: (1) whether that second, clean sinc upsample preserves the vintage profile's deliberately-introduced quantization/aliasing character, or smooths it -- band-limiting theory says a proper upsample from a signal already limited to the profile's own bandwidth should be transparent, but that has not been verified against real output, and the `--no-bandpass`/bandpass-coloring stage sits in the middle of the chain and its interaction with a later resample is unexamined; (2) whether **bit rate** in Jan's sense (not `bit_depth`, which stays 16 throughout by design) means something else worth checking here -- e.g. whether the AKAI writer's own bit-depth field/flags read correctly off a vintage-resampled-then-snapped sample, given the sample never actually changes container width. **Blocked on:** nobody has run `convert.py --resample emulator2/emax1 --format akai` end to end and listened to or measured the result; do that first, on a source sample the vintage profile visibly colors, before assuming either the chaining or the character survives it. |

## E4XT velocity→filter cord: the saturation detector never fires

**Status:** open, found 2026-09-04, not yet fixed.
**Blocked on:** nothing — needs a decision on which limit is authoritative.

`e4xt_cord_saturates()` takes `(base_byte, amount, level_percent)` and has **no
`source_units` parameter**, so for a velocity cord it under-estimates the reach
by `E4XT_VEL_SOURCE_UNITS` = 2.08x. From base byte 92 with amount 31.27 it
computes a reach of 170.4 against a ceiling of 250 and returns `False` — while
the true reach at full velocity is 92 + 2.506·31.27·2.08 = **255.0**, past the
ceiling. The cord saturates and the detector says it does not.

It is not a near miss. The detector cannot fire below amount 63.0, and
`e4xt_cents_to_cord_amount` asymptotes at ~31.3 for that base, so for velocity
cords **it is unreachable by construction** — dead code that reads like a guard.

**Consequence:** the `_cord()` re-saturation in `e4b_writer.py:1215` never
applies to velocity→filter. That guard exists to stop a third-party bank's
full-amount cord being rewritten smaller on every round trip (36.5 % of nonzero
filter depths in 60 real banks saturate), and velocity cords are unprotected by
it. Round-tripping a saturating velocity→filter cord of 100 rewrites it near
31: sounds identical, reads different, shrinks again next time.

**Not yet established:** whether a written amount of ~31 is *audibly* correct.
The arithmetic says it reaches the byte ceiling and therefore the same cutoff,
which would make this a fidelity-of-representation bug rather than a sound bug.
That needs an E4XT measurement, not more arithmetic.

See `docs/RESOLUTION_NOTES.md` §E4XTCORDSAT.

## hw_measure leaked ALSA sequencer clients (FIXED)

**Status:** fixed 2026-09-04 in `tests/re_banks/hw_measure.py`.

`_midi_out()` created an `rtmidi.MidiOut()` per call with no cache and no
`delete()`. A matrix run accumulated 22 clients and exhausted the ALSA
sequencer **machine-wide**, breaking a sibling session's K2000 autodetect with
`Cannot allocate memory` / `no K2000 answered on any of 38 output ports` — a
failure indistinguishable from the instrument being switched off. Same bug this
project recorded on 2026-07-12: `close_port()` does not free the backend client,
`delete()` must be called. Now one cached MidiOut per port match plus an atexit
release. See §E4XTCORDSAT's neighbour note in RESOLUTION_NOTES.

## build_matrix_v4: the three target paths use different source lists

**Status:** open, found 2026-09-04. Worked around for tonight by matching on
program name; the build is still wrong.

One build run emitted two different program sets:

    target  built     Keys-VP Rico Key LD TUBE PIPE rows usable vs the MPC
    e4b     21:10:29      no             yes              10
    krz     21:13:44      no             yes              10
    akai    21:13         YES            no               11 of 11

`ch6` (`the ch6 keys program`) exists on the MPC and in the AKAI volume only, so
it can never appear in the E4B or KRZ columns of the matrix. `LD Tube Pipe` is
in two targets and on no MPC track, so it is unmeasurable in every column.

Not a staleness/clock problem — the KRZ and AKAI were built inside the same
minute. Whatever chooses the source list is not shared between the three target
paths. The fix is for the builder to take the project'a kit sample's own `[ProjectData]` folder. The E4B
conversion sounds on all 16 keys. **So the conversion is faithful to the file
and the MPC is not playing what the file contains.**

Key 39 (`crash`) **sounded earlier the same evening** — it was captured as a
2.25 s crash for the velocity ladder — so this is a change in machine state
during the session, not a permanent property of the program.

**Consequence for the matrix:** those three keys are UNMEASURABLE, not faults.
Scoring them as "conversion sounds where source is silent" would record a
converter defect that does not exist. Ask Jan to check pad state / mute / track
state on track 11 before the next drum run.

## KRZ loading procedure (RESOLVED — documentation, not a writer bug)

**Status:** resolved 2026-09-04 by hardware control experiment. Needs writing up
in `docs/KRZ_FORMAT.md` and in the disc loading instructions.

Loading `MX_mpc_to_krz.KRZ` (149 samples, ids 200..348) into **bank 900** with
mode **Fill** silently dropped 49 samples: ids 200-299 filled 900-999 and the
rest had nowhere to go. Reloading the SAME FILE with destination **Everything**,
mode **Fill** on an empty machine:

    Program     bank 2:  11   ids 200..210
    Keymap      bank 2:  22   ids 200..221
    Soundblock  bank 2: 100   ids 200..299
    Soundblock  bank 3:  49   ids 300..348
    RAM 65536K -> 39983K = 25,553K consumed, against 24.8 MB of PCM in the file

**All 149 loaded, ids exactly as the file specifies.** So `_MAX_OBJ_ID = 999` in
`krz_writer` is correct as written and nothing needs splitting or capping.

**The rule for users:** load as **Everything/Fill**, or into a low bank with
**Overwrt**. Loading a bank with >100 objects of a type into a *specific* bank
with **Fill** truncates silently, and into bank 9 it cannot work in any mode —
Overwrt spills into "the bank following the just filled bank" and there is no
bank 10.

**Consequence for the night's data:** the first KRZ grid was measured on the
truncated load and is invalid — not only missing its top keys but playing wrong
samples in the middle (k36 -9.87 -> -3.92 and k60 -14.86 -> -30.54 between the
two loads, same program, same notes). Re-run in progress; the old grid is kept
at `~/temp/k2k_mxgrid/` as evidence about the truncation failure mode.

## KRZ writer loses 56 of 128 keys: outer zones are not extended

**Status:** open, confirmed 2026-09-05 from the file and on hardware.
**Supersedes an earlier, wrong diagnosis — see the correction note below.**

`the ch7 bass program`:

    MPC source covers keys   0-127
    KRZ conversion covers    12-83
    LOST: 56 keys  (0-11 at the bottom, 84-127 at the top)

The writer applies a per-zone pitch-stretch window — the lowest sample (root 26)
starts its zone at key 12, i.e. -14 semitones; the highest (root 71) ends at 83,
i.e. +12 — and then **does not extend the outermost zones to the keyboard
edges**, so everything past them is uncovered and silent. Most samplers stretch
the edge zones to 0 and 127.

k2kremote measured the consequence on a correctly-loaded bank: keys 84 and 96
silent, key 72 fine, unchanged across two different load methods.

**CORRECTION — the earlier entry here claimed the top zone ran to key 127 and
was silenced by `_KRZ_RATE_FLOOR` stretching it past the hardware's playback
ceiling.** That was wrong. It came from reading raw keymap objects and indexing
`entries[key]` directly, which ignores that each VOICE has its own key range
selecting the portion of a full-128-key table that applies. The rate floor is
still involved — it is plausibly what sets the +12 limit — but the fault is the
missing edge extension, not a stretched zone failing to play.

## WITHDRAWN: "KRZ writer collapses a drum kit's key map"

**Status:** withdrawn 2026-09-05. **The finding was wrong.** Kept as a record
because the reasoning failure is worth more than the claim was.

Claimed: the KRZ drum keymap assigned 16 keys to only 6 distinct samples, where
the E4B used 16. Checked with the top-level parser instead of raw keymap
objects:

    KRZ 'DRUM PROBE'   keys 36-51 -> 16 DISTINCT SAMPLES   correct
    E4B 'DRUM PROBE'   keys 36-51 -> 16 distinct samples   correct

**Both writers are correct and there was never a collapse.**

**Why it looked real.** Raw keymap objects hold a full 128-key table, and the
drum program has three voices. Each voice's own key range selects which part of
its table applies. Indexing `entries[key]` across the whole table therefore
reports one sample spanning the keyboard for every layer, which is exactly what
a collapse would look like.

**And it had corroboration that was itself an artifact.** k2kremote measured a
smooth 0.02 dB/key ramp across nine keys — the signature of one sample
transposed — and that agreement was treated as confirmation. On a correctly
loaded bank the same keys measure scattered (-2.65 to -17.66 dB), as a kit
should. Their ramp was the truncated bank playing clamped references. **Two
independent lines of evidence agreed and both were wrong**, which is a sharper
lesson than either being wrong alone: agreement between two measurements is not
evidence when both inherit the same broken input.

The one guard that held was the E4B control, and it is what should have been
believed when it disagreed — it said 16, and it was right.
## KRZ program 909 `the ch10 lead program` is silent on the K2000 — cause unknown

**Status:** open, 2026-09-04. Several causes ruled out from the file.

k2kremote: no sound on any key 0-96 at v127 (all readings -75.8 to -76.9
against a -90.7 silent floor). They ruled out key range (layers cover 0-35 and
36-127), velocity range, `Enable:ON` on all eight layers, amp settings
(identical `Adjust 6dB` to program 900 which sounds), and confirmed the
keymaps and soundblocks are present at normal size.

**Ruled out from the bank file here:**

- Sample data is REAL. Ids 269-276; id 269 has 28,341 non-zero words, peak
  13,660/32,767 (about -7.6 dBFS).
- Extents are sane (start/end contiguous, 32k-35k words each).
- **Not truncation** — they start at 9.19M words, inside the loaded region.
- **`flags` is a red herring.** These carry 240 (0xF0) against 112 (0x70) on
  the Acid samples, but 138 of 165 samples in the bank carry 240 including
  ones confirmed to play.

Distinguishing feature not yet explained: `looped=False` with
`loop_start_w == end_w`, and `max_pitch` 3500/4000 against 4100-6500 on the
working Acid samples.

## KRZ writer collapses a drum kit's key map: 16 keys -> 6 samples

**Status:** open, found 2026-09-04. **Independent of the bank-load question.**
Verified from the file and corroborated on hardware.

The same source kit, converted in the same run by two writers:

    E4B  keys 36-51 -> 16 distinct samples   correct
    KRZ  keys 36-51 ->  6 distinct samples   collapsed

The KRZ drum keymaps assign one sample across long key runs:

    keymap 219   key 36 -> 342 'Snare Snr3';  keys 37-51 -> 346 'Clap Clp2'
    keymap 220   keys 36-51 -> 340 'Melodic Fx2'   (all sixteen)
    keymap 221   36-37 -> 345; 38 -> 347; keys 39-51 -> 348 'Melodic Syn4'

**Corroborated on hardware before it was found in the file.** k2kremote measured
the drum probe across keys 36-51 and reported nine keys marching in a smooth
0.02 dB/key ramp — the signature of ONE sample transposed, where a kit should
give scattered levels because every key is a different instrument. Their
measurement and this file reading were produced independently and agree, which
is also what makes both parser readings trustworthy here.

**Not the truncation, and not the id ceiling.** Those concern which objects
reach the machine. This is what our own file says before anything is loaded:
the key-to-sample assignment is wrong on disk. The 12 kit samples that survive
in the bank (ids 333-343, 346) are simply not referenced by the keymap.

**Not `_KRZ_RATE_FLOOR` hole-fill either**, which was the first guess on both
sides. Hole-fill substitutes a neighbour above a zone's up-pitch ceiling; this
collapses the map across the whole range including the root keys.

**Next step:** find where `krz_writer` builds keymap entry runs — `_entry_runs`
and the keymap emit path — and determine whether a run is being extended past
its intended end, or whether zones are being merged before the keymap is built.
A 16-zone unpitched program is the test case; the E4B path handles it correctly,
so the model carries the right data and only the KRZ writer loses it.

## KRZ writer orphans a zone's sample in a PITCHED program

**Status:** open, found 2026-09-04. Confirmed from the file.

Exactly **one sample of 149** in `MX_mpc_to_krz.KRZ` is never referenced by any
keymap: id **244 `bass-061 Db3`** (root 61) in `the ch7 bass program`. It is
written into the bank, occupies space, and can never sound. Its key range was
absorbed by its neighbour:

    keymap 205   keys 55-56 -> 245 (root 66)
                 keys 57-66 -> 246 (root 71)      <- 244 skipped entirely

k2kremote spotted its absence from the K2000's panel — "the `-061` that belongs
in that sequence is not there" — before it was found in the file.

**This is a PITCHED program**, so it refutes the earlier claim that only the
many-zone unpitched drum program is affected by keymap construction faults.
Likely the same root cause as the drum collapse (a key run extended past its
intended end, swallowing the following zone), which would make the drum case
the extreme of a general defect rather than a separate one — but that is a
hypothesis and the two should be confirmed to share a cause, not assumed to.

## KRZ writer assigns the WRONG SAMPLE to a zone (noise into a bass keymap)

**Status:** open, confirmed from the file 2026-09-04. **Resolved: this and the
"orphan" below are ONE bug.**

`the ch7 bass program`, keymap 205, full run structure:

    keys   0- 16   237  bass-026 D0    root 26
    keys  17- 21   238  bass-031 G0    root 31
    keys  22- 26   239  bass-036 C1    root 36
    keys  27- 31   240  bass-041 F1    root 41
    keys  32- 36   241  bass-046 Bb1    root 46
    keys  37- 41   242  bass-051 Eb2    root 51
    keys  42- 46   243  bass-056 Ab2    root 56
    keys  47- 51   236  a noise sample    <-- WRONG SAMPLE
    keys  52- 56   245  bass-066 Gb3    root 66
    keys  57-127   246  bass-071 B3    root 71

The sequence should read 243(56) -> **244(61)** -> 245(66). Sample **244
`bass-061 Db3` was replaced by 236 `Generator-Noise White`**, a sample from
an entirely different program. That one wrong assignment explains both symptoms:
it orphans 244 (the only unreferenced sample of 149) **and** puts white noise
five keys wide into a bass program.

k2kremote measured the audible consequence independently — `Bass-Dark-The Po` at key 60
reads peak -24.05..-14.86 where keys 48 and 72 read -8.61..-3.03 and
-7.30..-4.96 — and read the wrong reference off the K2000's panel before it was
found in the file.

**Note ranges differ by 12 semitones** between our parser's numbering and the
K2000 display (their `B 3-D#4` against our keys 47-51). A naming convention
offset, not a content disagreement.

**This is a PITCHED program.** Together with the drum keymap collapse it means
keymap construction is unreliable in general, not only for many-zone unpitched
programs. Whether the two share a root cause is still a hypothesis.

**Process note.** This was first reported here as "the file does NOT reference
the noise sample", because only keys 55-66 were inspected — the range the peer
named — and a partial view was stated with the confidence of a complete one.
The peer then went looking for faults in their own instrument on the strength of
that error. **Dump the whole structure before characterising it.**

## AKAI cutoff curve is unmeasured below FILFRQ 44 — dark programs land there

**Status:** open, 2026-09-05. **This is the actionable half of §AKAIFILTSWEEP.**
Blocked on: a hardware calibration sweep (s3ked has the kit).

`akai_filter_byte`'s measured S3000XL curve covers **FILFRQ 40..84 = 138 Hz to
3.3 kHz**. Below 147 Hz the writer returns the floor byte, because 0..43 has
never been measured and the E4B precedent says an unsampled extrapolation can
be wrong by 5x.

**Every AKAI row that scores 0.000 sweeps below that floor; every row that
scores well strays only above the ceiling:**

    program        corner@v1   corner@v127   FILFRQ    outside band
    ch2/3/8 FAIL       58 Hz       1099 Hz   28..69    bottom below 138 Hz
    ch10    FAIL       41 Hz        606 Hz   23..60    bottom below 138 Hz
    ch7    0.712      703 Hz       1065 Hz   62..68    inside
    ch5    0.852      473 Hz       8902 Hz   57..99    top above 3.3 kHz
    ch4    0.830     2626 Hz      65550 Hz   81..99    top above 3.3 kHz
    ch9    0.923     1359 Hz     989150 Hz   72..99    top above 3.3 kHz

**The asymmetry is the finding.** Extrapolating UP is benign — past ~3.3 kHz a
filter is open and stays open, so the error lands where nothing is attenuated.
Extrapolating DOWN is not: the gap between a 58 Hz source corner and the 138 Hz
floor we substitute is the difference between a note sounding and not. Test A
demonstrated exactly that by silencing key 84 outright.

**The fix is a measurement, not a heuristic:** sweep FILFRQ 0..44 and record the
corner per byte, as the 40..84 curve was taken. Two cautions the upper band did
not face — the corner may stop moving before byte 0 (if so, clamp deliberately
rather than interpolate), and the measurement gets hard as it gets dark, so
each point needs its noise floor stated and points without margin refused.

**Interim trade, untested:** Test B showed opening the corner to FILFRQ 99
collapsed the source mismatch from 4.01 to 0.36 — the conversion matched
BETTER by being LESS faithful to the parameter. 99 discards the filter
character entirely. Whether lifting only into the measured band (FILFRQ 40)
recovers most of that gain while staying dark is an open question and a
one-test experiment.

## AKAI card rebuild — verification procedure (needs Jan; peers may not write disks)

**Status:** designed and ready 2026-09-05. **Blocked on Jan** — the rebuild
writes a disk image, which is outside the peer sessions' standing grant (RAM
loads, CLR and program deletes only; not image writes, volume renames/deletes
or formats). s3ked declined it correctly and it must not be asked of them.

**ALL of today's AKAI verification patched RAM over the wire.** Every reading in
s3ked's §171-§178, and every condition behind §AKAICORNER, set parameters by
SysEx on a resident program. **Not one exercised the path that generates those
values.** So the whole body of work is structurally blind to the class of fault
that cost this morning: a value that is correct in RAM and wrong in the writer
(`env2_depth`, §AKAIENV2GATE). The rebuild is the only test that closes it.

**Method — compare the two CONVERTED states, not each against the source.**
Same programs, same keys, same rig: the only thing differing is the bytes the
writer emitted, so no source term and no per-key normalisation is needed. Same-
key deltas between the patched-RAM condition and the rebuilt volume should be
**≈0 on every program**; any program where they are not has a value that is
right in RAM and wrong on the path that generates it.

**Three conditions the pairing depends on (s3ked):**

1. **Confirm program identity after the load.** A volume load APPENDS rather
   than replaces (§94) and CLR leaves one program behind (§152), so indices can
   shift. Capture the RAM condition, do the load, then **re-read the same
   programs by index and confirm they are the ones measured** before trusting
   any delta. Otherwise the two sides differ in more than the writer's bytes.
2. **Fix capture gain explicitly across both sides**, rather than assuming it
   held. Common-mode gain is the one term the pairing still relies on.
3. **Two keys minimum**, as everywhere else in this work.

**Expected values from the fixed writer** (`akai_velocity_filter` corner floor):
ch2/3/5/8 -> FILFRQ 99, ch7 -> 89, ch10 -> 86, ch4/6/9 unchanged at 99. These
match what was patched by hand and verified on hardware, so a non-zero delta
anywhere is a writer-path fault rather than a new question about the rule.

## WITHDRAWN: "E4XT samples under ~80 ms do not sound"

**Status:** withdrawn 2026-09-05, within the hour it was filed. **There is no
such effect.** Kept because how it was reached is worth more than the claim.

**The claim.** The drum kit's samples separated perfectly by duration against a
peer's list of silent keys — everything under 80 ms silent, everything from
234 ms up sounding, nothing in the gap. Filed as a writer-or-machine fault.

**The refutation, from the peer who supplied the silent list.** Those keys are
not silent; they sit 42-46 dB over the floor in the ATTACK window with peaks at
-24 to -28 dBFS. They vanish only from an `early` window that opens at **100 ms**
— after a 55-80 ms sample has already finished. **The 80-234 ms gap that made
the separation look so clean contains 100 ms, which is that window's opening
time.** The boundary was an analysis window, not a property of anything.

**AND OUR OWN DATA SAID SO BEFORE THE ENTRY WAS WRITTEN.** The matrix scores on
PEAK (§PEAKFORPERC), which is immune to this. Our scoring of the same captures
reports **all sixteen keys at 5/5 cells, 50-64 dB SNR** — no silence anywhere,
zero dropped notes, and the drum row scored 0.751 on that basis. Those numbers
were computed, printed and in hand before the finding was filed.

**So the failure was not believing a peer. It was believing a peer's SUMMARY
over our own MEASUREMENT of the same captures without checking whether the two
disagreed** — and then finding a mechanism that fitted the summary. A clean
pattern is not evidence of a cause; "perfect separation" made it more
persuasive, not more true.

**What survives:** MPC keys 39, 41 and 50 are dead at SOURCE. Measured on our
own captures, unrelated to any of the above, still open.

**Why the drum row was never affected:** it scores on peak, so it never saw the
artifact. That choice was made for an unrelated reason (§PEAKFORPERC) and is
what kept the column correct while the prose around it was wrong.

## Attack time is copied verbatim between machines with different ramp shapes

**Status:** open, measured both ends, NOT ready to fix.
**Blocked on:** the E4XT normalised ramp out to t/T = 2.5 (request with `eosed`;
their existing 14 s captures already contain it). Without that there is no
measured crossing point and any correction factor would be invented.

At its own nominal attack time the MPC has delivered 89 % of amplitude and the
E4XT 28 %. We copy the number across, which is faithful to the parameter and
not to the sound. Error is negligible for short attacks and ~24 dB for a 5.58 s
one. ~8 dB of the channel-5 deficit remains unexplained even after shape and
asymptote are accounted for.

See `docs/RESOLUTION_NOTES.md` §ATTACKSHAPE. Related: §ANCHOR.

## XPM: a sparse layer shifts every later layer into the wrong voice

**Status:** open. Symptom hardware-confirmed (+29.96 dB); ROOT CAUSE FOUND
2026-09-05 in `parsers/xpm_parser.py:2085`, not in the KRZ writer.
**Blocked on:** Jan's sign-off — the fix changes voice allocation for every
format and every XPM, so it needs its own regression pass.

Zones are allocated to voices by first fit on key overlap, with no notion that
XPM Layer 1 and Layer 2 are different roles. When one instrument omits Layer 1,
every later layer lands one lane off and a noise texture ends up inside a
pitched multisample ladder. Affects E4B and AKAI as well as KRZ.

See `docs/RESOLUTION_NOTES.md` §XPMLANEMIX and §KRZWRONGSAMPLE.

## The attack-shape ramp numbers need re-measuring on unmodulated material

**Status:** open. §ATTACKSHAPE stands in direction; its numbers do not.
**Blocked on:** a small calibration bank — one steady sine sample, one preset
per attack rate (0/40/70/89/94/110). `eosed` will capture it once it exists.

`the ch5 slow-attack pad` is amplitude-modulated (0.70 s on the E4XT, 0.17 s lag and
11.7 dB peak-to-trough on the MPC), which sets the bin level past t/T ~ 1
instead of the attack. No correction factor may be derived until this is
re-measured.

See `docs/RESOLUTION_NOTES.md` §RAMPSUBJECT.

## SF2/GIG import silently truncates at the default preset limit

**Status:** now WARNED (`SF2_PRESETS_TRUNCATED`), not yet fixed.
**Blocked on:** a decision — should `--max-presets` default to "all", with the
limit only as an opt-in guard?

`convert.py --max-presets` defaults to **64** (`convert.py:700`) and GIG to 32
(`parsers/registry.py:71`). Measured over the local library: **12 of 504
SoundFonts hold more than 64 presets, the largest listing 444** — converting it
through the shipping command silently discarded 380 of them, with no message at
all until today. Four files list 200 or more.

The diagnostic makes it visible. Whether the DEFAULT is right is a separate
question and Jan's call — a limit that silently discards three quarters of a
file is a poor default even when it is documented.

See `docs/RESOLUTION_NOTES.md` §DIAGIFACE.

## Five RE scripts open a MIDI client per capture and survive only on refcounting

**Status:** open, not urgent — measured NOT leaking today.
**Blocked on:** nothing; it is a small edit to five files.

`krz_audio_measure.py`, `verify_pitch.py`, `pitch_sweep.py`, `verify_programs.py`
and `krz_sysex_live.py` all call a `_midi_out()` helper that constructs
`rtmidi.MidiOut()` **inside a per-capture function**. That is the pattern that
took the ALSA sequencer client table from 22 to 51 in `cap_full.py`, killing one
run two captures short and blocking another session entirely — with an error
(`no K2000 answered on any of 38 output ports`) that reads exactly like a dead
instrument.

**Measured 2026-09-06: seq clients stayed at 30 across 305+ notes**, so the
ports are being released — CPython destroys the object at function exit and
rtmidi closes the port. **It works because of prompt refcount collection, not
because anything closes it.** One retained reference anywhere and it is
yesterday's failure again.

Fix is the one already applied to `hw_measure.py`: cache the client and release
it at exit — **one client per RUN, not per capture** (k2kremote's rule, and the
right one: serialising sessions does not protect against a leak inside a single
run).

The ALSA seq table is the shared resource with a body count here — not JACK
client concurrency. JACK's own recorded failure is *client churn* wedging a
Berkeley DB mutex region in `/dev/shm` that survives a jackd restart.

## KRZ→E4B: a 12-string renders 40 dB below a B3 organ — correct or ours?

**Status:** open. Both proposed causes REFUTED on hardware. ~25 dB unattributed.
**Blocked on:** one preset pair measured on the K2000 (the KRZ original).

The velocity-pivot trim is NOT the cause and must not be changed: it cancels to
−0.33 dB on hardware, and the volume-law extrapolation it relies on is accurate
to ±0.5 dB well past the −22.9 dB label. Cord routing is correct
(`slot 0, Vel+ → AmpVol`), confirmed against the machine.

With the trim removed, P000 still sits 40 dB below P003. Source material
accounts for 8.5 dB (12-string −19.7 vs organ −11.2 rms, peaks identical) and
the amp envelope for ~7 dB. **~25 dB unexplained.**

**The test:** if the K2000 renders that preset pair ~8.5 dB apart while our E4B
renders them 40 apart, it is a ~31 dB conversion finding. If the K2000 also
renders them 40 apart, the material is simply like that.

See `docs/RESOLUTION_NOTES.md` §KR2E4LEVEL.

## Capture the fixed E4B column — prediction PRE-REGISTERED before the run

**Status:** blocked on a card crossing. Neither this session nor `eosed` has
asked Jan for one; it can ride with `ATKSHAPE`, the corrected KRZ bank and
`MXKRSRC.KRZ`.

The whole E4B column was built with the double-written velocity trim
(§E4BDOUBLETRIM) and rebuilt through the fixed writer. The rebuilt banks are in
`~/temp/matrix_v7/rows/`, pre-fix banks kept alongside as `*_pre.E4B`.

**CAPTURE `MX9 S3-E4` FIRST, and here is the prediction, recorded before the
capture exists:**

    S3-E4   30 of 36 trimmed voices UNCHANGED   (single-zone: no zone byte,
                                                 so the trim MUST stay on
                                                 vpar[54] and the fix must not
                                                 touch it)
             6 of 36 RISEN by ~29 dB            (multi-zone: the zone copy
                                                 carries the trim, the voice
                                                 copy was the duplicate)

    IF 30 COME BACK RISEN, the single-zone classification is wrong and the
    conditional is doing something other than what both projects believe.
    That outcome falsifies this side's reading of the source, NOT the fix.

**Why S3-E4 and not KR-E4.** KR-E4 asks only whether the fix did *something* —
all nine of its trimmed voices are multi-zone, so the right fix and an
unconditional one emit identical bytes there. **S3-E4 can fail in two
directions**, as an overshoot (30 too loud) or as a no-op.

**Already ruled out without hardware:** every changed byte across all four rows
goes TO zero and none lands on a non-zero value, so the fix only ever REMOVES a
trim — a bug that added one somewhere is excluded by the diff alone.

**Requirements:** same grid and same session gain as the pre-fix sets, or the
comparison is not one. Pre-fix captures are kept, not cleared — once the medium
is rewritten there is no route back to the pre-fix state.

See `docs/RESOLUTION_NOTES.md` §E4BDOUBLETRIM.

## FIXED: the K2000 LFO rate law was one segment of five — 77.5% of corpus rates were wrong

**Status: FIXED 2026-09-07, measured table adopted. Needs a rebuild to reach the
media.** `krz_writer` asserted `byte = 26 + 10*Hz` in one undocumented line. It
turns out to be **segment 3 of a five-segment ladder, character for character** —
`36 + (Hz-1.00)/0.10` is identical to it — so it was the CORRECT law for
1.00-10.00 Hz and wrong everywhere else.

Measured by k2kremote off the K2000's own LFO1 MnRate field, 185 rows, one per
byte, and the segments reproduce every row exactly (verified here before adopting,
so it is a lossless encoding rather than a fit):

    byte   0..20    0.01 Hz/byte     0.00 ..  0.20 Hz
    byte  20..36    0.05 Hz/byte     0.20 ..  1.00 Hz
    byte  36..126   0.10 Hz/byte     1.00 .. 10.00 Hz     <- the old law
    byte 126..176   0.20 Hz/byte    10.00 .. 20.00 Hz
    byte 176..184   0.50 Hz/byte    20.00 .. 24.00 Hz

**Audio corroborates the panel at four bytes across three segments** (5.00, 10.00,
16.00, 22.00 Hz, two reps each). The 0.11 and 0.22 residuals at the top are FFT
bin quantisation at 0.556 Hz spacing — k2kremote's instrument, not the machine's.
**Do not read a trend into them.**

**Byte 184 is the ceiling.** The old writer clamped to 255, permitting bytes the
panel cannot reach and nobody has tested.

### Corpus damage, measured over 320 sampled XPMs (391 LFO rates)

    band          n    median wanted   median got   median ratio
    below 1 Hz    17          0.14         0.55           3.88
    1-10 Hz       88          5.51         5.50           1.00
    above 10 Hz  286         12.61        15.20           1.21

**303 of 391 rates — 77.5% — were written wrong by more than 0.05 Hz.**

**Scope, checked rather than assumed (k2kremote's boundary on their own result):**
the ladder was measured on **LFO1 `MnRate`** and has not been checked against
`GLFO2`, `LFO2` or `MxRate`. `krz_writer` has exactly one rate call site —
`lfo[2] = krz_lfo_rate_hz_to_byte(voice.lfo1_rate)` — and emits no second-LFO
rate and no `MxRate`, so every one of the 391 sampled rates is LFO1 `MnRate` and
none inherits a law measured elsewhere.

Two distinct failures, and the smaller band is the worse one:

- **Above 10 Hz (73% of all rates):** the machine spends one byte per 0.2 Hz where
  the old law spent one per 0.1, so the offset from 10 Hz was roughly doubled.
  Median 12.61 Hz written as 15.20.
- **Below 1 Hz (4.3%): proportionally catastrophic.** The old law's intercept puts
  0.042 Hz at byte 26, which is 0.50 Hz — **11.9x too fast**. 0.088 -> 0.55 Hz,
  0.142 -> 0.55 Hz. **Slow LFOs are what a listener notices**: "that should be a
  slow sweep and it is warbling."

Only the 1-10 Hz band came through correct, which is exactly the band the law was
silently calibrated for and the only band anyone had checked.

## CONFIRMED IN THE SHIPPING PATH: the K2000 panner wire fix (2026-09-07)

Controlled A/B, both arms on the same instrument, same key and velocity, same
analyser, RAM cleared to zero between banks, audio path proven immediately before
each capture (floor -90.7 dBFS, note -8.2):

    MX10MPC  wires U->left, L->right      MX9MPC9  wires both left
    L -25.2  R -29.0   gap  3.8 dB        L -19.7  R -79.3   gap 59.7 dB
    balance sd 5.05 / 5.17 / 4.94 dB      balance sd UNINTERPRETABLE
    peak-to-peak 17.8 / 15.7 / 17.7 dB      (right channel at the floor)
    peak 8.89 Hz at x107 / x113 / x106     peak 0.56 Hz = drift, lowest bin

8.89 Hz is one FFT bin from LFO1's 8.70 at that window — **LFO1's rate, not a
discrepancy**, and it should be written that way so nobody later treats 0.19 Hz
as a finding.

**The two arms differ in KIND, not degree, and the claim must say so.** The
treatment is a stereo signal whose balance swings ~17 dB peak-to-peak at the LFO
rate, both channels live. The control is a MONO signal in the left channel with
60 dB of nothing in the right. So the correct statement is **not** "the panner
moves in one and not the other" but *"one has a stereo image to modulate and the
other has no image at all"* — which is exactly the p284 mechanism and exactly what
the four-byte wire change does.

**Subject verified on both arms, and it had to be by the OUTPUT page:** the panner
bytes are byte-identical between the banks (F3 40, Src1 114, Depth 26, Adjust 0 in
each), so nothing in the panner block could say which file was in RAM. Only the
wire pan markers differ — both on `L` in the control, opposite in the treatment.

**What it closes:** the file path end to end — XPM, parser, `krz_writer`, card,
load, audio — with four bytes as the only difference, verified as the only
difference from the build side before the disc was made. The writer produces the
sweep.

**What it does NOT close:** `MX10GRAT`, which carries a panner for the first time
at a different depth (19 rather than 26). That wants its own measurement rather
than an assumption.

## CONFIRMED IN THE SHIPPING PATH: the AKAI rate fix (2026-09-07)

`AKAI_LFO2_RATE_HZ_PER_UNIT = 0.11913` verified by a **fourth** route, and the
one that matters — the writer chose the byte, not a hand-set parameter:

    PRG  amt  PANRAT   predicted   measured   frames   resol   floor%
      8   26      73        8.70       8.63      163    0.61      0%
      5    9      35        4.17       4.33       97    1.03      0%
      1   36      61        7.27          -       34       -      0%

**PRG 8 has both arms and doubles cleanly:** PANRAT 37 -> 4.35 Hz on MX9 MPC8 01,
PANRAT 73 -> 8.63 Hz on MX10 MPC 01. Ratio 1.98 against the source's 8.7. PRG 5
lands inside its own 1.03 Hz resolution. Byte check passed too: amounts unchanged
at 36/9/26, rates exactly doubled, 176 samples, `ACID` names intact.

**PRG 1 is UNMEASURED, not passed** — it sustains ~0.35 s, too short to resolve
7.27 Hz. A cross-note workaround produced a confident 6.66 Hz and was discarded as
an artefact; see §SAMPLINGSCHEME. Its rate byte is verifiably correct in the
header; whether the LFO reaches pan on it is open.

## The E4B LFO rate map is wrong between its anchors — every LFO rate we write is off

**Status: OPEN, measured 2026-09-07 (eosed). Do NOT refit yet.** `cnv_lfo_rate`
in `models/common.py` was calibrated 2026-06-10 from the E4XT rate MENU at three
points (byte 0 = 0.08 Hz, 64 = 4.12 Hz, 127 = 18.01 Hz) and fitted as a
log-quadratic **exact at those three by construction**. Its own comment says it
is "refineable with intermediate readouts". There has never been an intermediate
readout.

Measured by sweeping the rate byte in RAM and reading the actual modulation:

    byte    our map   measured   ratio    note
      40      1.25      1.98      0.63
      60      3.46      3.74      0.93    near the 64 anchor
      75      6.33      5.49      1.15
      85      8.78      7.02      1.25
      95     11.47      8.85      1.30    midpoint of the 64-127 gap
     105     14.11     11.14      1.27
     115     16.34     14.04      1.16    near the 127 anchor

**Not a constant offset — the shape is wrong**, and the agreement is best beside
the anchors and worst between them. That is the signature of a bad interpolation
through correct anchors rather than a lying display. The measured points fit
`exp(-0.000074821*b^2 + 0.0373635*b - 0.679590)` to 2.6%, and above byte 85 a
pure exponential `exp(0.023096*b - 0.0142)` with residuals +-0.004 Hz.

**Concretely: GRATER shipped at byte 95 and modulates at 8.85 Hz where the source
asks 11.46. For 11.46 the byte is 105.**

**REACH IS WIDER THAN THE WRITER.** That map is used by the E4B writer *and the
parser*, so it also mis-READS the rate of every E4B SOURCE — the error propagates
into KRZ and AKAI conversions built from E4B material, not just into E4B output.
It applies to pitch and filter LFOs as well as pan. The K2000 and AKAI have their
own rate laws and are not affected directly.

**RESOLVED 2026-09-07: the panel is honest and the fit is wrong.** Panel display
read against the audio measurement at five bytes, including byte 40 where the
disagreement runs the other way — the chosen discriminator:

    byte    panel   measured   our map   map error
      40     1.98     1.98       1.25      -36.9%
      60     3.74     3.74       3.46       -7.5%
      95     8.85     8.85      11.47      +29.6%
     105    11.14    11.14      14.11      +26.7%
     115    14.04    14.04      16.34      +16.4%

Panel equals measured to two decimal places at every point. So the display is not
lying; the three-point interpolation is simply the wrong shape through the middle.

**That also discharges two caveats by measurement rather than argument:** the
balance frequency IS the LFO rate 1:1 (panel and audio agree to three significant
figures), and it holds across five bytes rather than one. The remaining caveat is
one preset / one voice, and three or four spot bytes on a second preset settles
it — a full second sweep is not needed.

**THE FIX IS A TABLE, NOT A BETTER CURVE.** The curve exists because in June a
129-entry display table looked untranscribable, so a log-quadratic through three
readings was the affordable approximation. The panel is readable at every byte and
the audio measurement is now proven equal to it, **so the constraint that
justified the fit is gone**. A refitted curve would still approximate something
exactly enumerable. Replace `_LFO_RATE_A/B/C` with a lookup plus an explicit
inverse, and mark the constants dead rather than tuned.

**This is not a defect received from eosed — both projects independently fitted
the same wrong curve to the same three anchors** (0 = 0.08, 64 = 4.12,
127 = 18.01 Hz, 2026-06-10).

### Why neither project noticed for three months

**Each validated the fit against the same three anchors it was fitted to.** A
log-quadratic forced through 0/64/127 reproduces 0/64/127 exactly, by
construction, forever. Every check either project ran was a check the instrument
could not fail — the residual at a calibration point of an exactly-determined fit
is identically zero whatever the true curve does in between.

That is k2kremote's rule in a different costume: *a measurement is not evidence
until the apparatus has been shown able to produce a reading that CONTRADICTS the
one you got.* A three-point fit checked at its three points is an instrument that
only says yes. **The first reading ever taken between the anchors disagreed by
30%.**

Generalisation worth carrying: **a fitted law must be validated somewhere it was
not fitted.** If a calibration has N free parameters and N anchors, then N
agreements prove nothing at all; the (N+1)th point is the entire test. Both
projects shipped for three months on N.

### Scope of the swap, when the table arrives

Small and data-only:

    models/common.py    _LFO_RATE_A/B/C, lfo_rate_byte_to_hz, lfo_rate_hz_to_byte
    parsers/e4b_parser.py   pzt[42] -> lfo1_rate, pzt[50] -> lfo2_rate
    writers/e4b_writer.py   pzt[base] = lfo_rate_hz_to_byte(rate)
    tests/test_law_consistency.py   asserts the byte<->Hz round-trip

Two functions replaced by a lookup plus an explicit inverse; every call site keeps
its signature.

**CLOSED 2026-09-07 — confirmed in the shipping path, caveat discharged.**

    MX10 GRATER  byte  95   table  8.85   measured  8.85 Hz
    MX11 GRATER  byte 106   table 11.44   measured 11.44 Hz

Both arms on one disc, one byte apart, measured at CC1 = 0 and 127, 750 frames
each at 0.27 Hz resolution. **The balance swings are unchanged across the pair**
(27.05 → 26.74 dB and 66.19 → 65.21), so only the rate moved — asserted when the
disc was built, measured now.

**The one-preset caveat is discharged rather than argued away:** a different bank,
preset, voice and LFO *shape* (triangle against the A/B's sine) matched the table
at bytes 30, 70, 100 and 120 exactly. The mapping is a global property of the LFO,
not per-voice and not shape-dependent. Four points, not a second sweep.

**11.44 against a 11.50 request is honest quantisation, not error** — the grid
cannot express 11.50, and the writer now reports what it achieved. That is only
legible *because* it reports it: under the old behaviour this would have shown as
a 0.06 Hz mystery sitting on top of a 2.6 Hz one.

**Do not adopt eosed's curve yet** (their caveats, kept): one preset, one voice,
one key; balance frequency assumed equal to LFO frequency 1:1; seven points from a
single sweep. Wanted before refitting: panel readings at the same bytes, and a
second preset to show the rate does not depend on the program.

## ISO bank ORDER is not stable across builds — selecting by index loads a different bank

**Found 2026-09-07 (eosed) on the first load of CD3-MATRIX10.iso.** The builder
writes banks in `sorted()` order; the previous disc was written in the order the
banks were added. Same five names, same disc id, different indices:

    MATRIX9   B000 KR-E4   B001 S3-E4   B002 S1-E4   B003 MPC-E4B  B004 GRATER
    MATRIX10  B000 GRATER  B001 KR-E4   B002 MPC-E4B B003 S1-E4    B004 S3-E4

**Selecting B003 today loads S1-E4 where yesterday it loaded MPC-E4B**, with no
indication — the names are unchanged, so nothing looks wrong. Any harness or
person selecting by remembered index gets a different bank silently.

Two consequences:

- **Any driver that addresses banks by index must be re-pointed per disc**, or
  better, select by name and verify by bytes.
- **It is also an unfakeable freshness proof**: a cached directory cannot show a
  reordering, so "the order changed" is positive evidence of a live read in a way
  that matching names are not.

Worth deciding whether `build_iso` should preserve insertion order rather than
sorting — stable indices across generations are what make an A/B addressable —
but the safer habit either way is name-plus-bytes, never index.

## FIXED: `RootNote 0` no longer freezes pitch — 70.5% of the library was resting on a WAV chunk

**Status: FIXED 2026-09-07 in `parsers/xpm_parser.py`. Not yet hardware-tested on
a rebuilt bank (needs a card write).** §XPMNOROOTFIXED, escalated from one preset
to most of the library.

`non_transpose = ignore_base or (raw_root == 0 and full_range)` treated MPC's
"unspecified root" as "fixed pitch". Measured over the 6082-XPM backup:

    RootNote 0 anywhere:                     78.1%   (900 sampled)
    RootNote 0 AND full range 0-127:         70.5%   <- hits the trigger
    of trigger-hitting, no WAV `smpl` chunk:  5.6%   (54 checkable)

Seven in ten programs hit it — organ, pad and bass multisamples across several
libraries. They converted correctly **only** because a WAV `smpl`
unity note rescued them, so correctness rested on a chunk the XPM does not
control. The 5.6% with no `smpl` shipped playing ONE PITCH across the keyboard —
a solo brass patch and a keys patch among them.

**Hardware-proven before the fix, not inferred (eosed):** on the E4XT, voice 0 of
such a program carries `NON_TRANSPOSE = 1` and plays 262.6 Hz at every key across
four octaves; setting parameter id 57 to 0 makes it track to within 0.4%
(65.2 / 262.6 / 1050.3 at k36/60/84); restoring brings the fault back. One byte,
one voice. That also confirms `E4_VOICE_NON_TRANSPOSE = 57` on hardware, which was
a spec transcription until then.

**The fix:** when the `smpl` rescue cannot fire, still do not freeze — track with
root 60 (MPC's own default; the keygroup low note is 0 here by construction, so
rooting there would play everything five octaves up). `IgnoreBaseNote` still
freezes, which is the case that actually asked for it. *A pitched instrument
frozen on one note is wrong at every key; a texture that tracks is wrong only if
someone plays it across the keyboard.*

**Verified end to end:** shipped bank P010 `vpar[38] = 1`; rebuilt with the fix,
`vpar[38] = 0`. It was the only preset in that bank carrying the flag.

**HARDWARE-CONFIRMED 2026-09-07 on the rebuilt disc (eosed).** `NON_TRANSPOSE`
(id 57) reads 0 on all 11 presets across voices 0-3, and the audio agrees —
fundamental at k36 / k60 / k84, where a perfect tracker over that span gives 16:

    P010    65.2  262.6  1050.3   ratio 16.11   TRACKS  (was 262.6/262.6/262.6, 1.00)
    P007   130.7  524.4  2102.8   ratio 16.08   tracks
    P004    49.1  130.7   522.9   ratio 10.66   tracks
    P001   131.1  265.5  1041.5   ratio  7.94   tracks

**The fix did not over-reach:** every neighbour reads the same as before it to
within estimator jitter, so the only material change in the bank is P010. And
P000 still reads a constant 93.8 Hz at -86 dBFS *identically before and after* —
which is what an estimator noise-floor artefact does and what a fixed-pitch
program would not.

**Only P010 was flat on the shipped bank** (eosed measured every preset's
fundamental across k36-k84) — so the diagnosis is complete rather than partial.

**A detector trap worth keeping:** P000 reads a constant 93.8 Hz at every key,
ratio 1.00, the identical signature to P010 — at **-86 dBFS**. That is the
estimator's noise-floor constant, not a fixed-pitch program. **Constant frequency
across keys is necessary and not sufficient; it needs the level check beside it.**

## GRATER carries NO pan modulation on ANY of the three cards — all three volumes are pre-pan-writer builds

**Status: CAUSE ESTABLISHED 2026-09-07, needs a rebuild + card write (Jan's).**
eosed measured GRATER->E4XT as a total pan loss: R-L +0.42 dB (the interface
trim) at every key and both wheel positions, swing 0.01-0.04 dB. They then read
the cords before concluding and found **no AmpPan cord at all** — LFO1 exists and
is routed to *Pitch*.

**It is not a writer defect. The bank on the card predates the writer's pan
support.** Rebuilt from the same source with the current writer:

    REBUILT now    E4P1 720 bytes -> AmpPan cord at offset 304, amount 24
    ON THE CARD    E4P1 720 bytes -> no AmpPan cord

24 is exactly right: `lfo1_to_pan 0.370079 x (1 - wheel_to_lfo 0.5) x 127 = 23.5`.
The parser reads the source correctly (Application_Version 2.10.1.85, nested
`<LFO LfoNum="0">` layout, `LfoPan 0.370079`, `VelocityToPan 0.055118`).

**How it happened, and it is a process fault worth naming.** `MX9 GRATER_01` was
built at 20:22 for CD3-MATRIX8b, *before* the AmpPan cords existed in the writer.
When CD3-MATRIX9 was assembled the MPC row was rebuilt and GRATER was **carried
over unchanged** — correctly for the three rows verified byte-identical on
purpose, wrongly for this one, because nobody asked whether it predated the fix.
**Carrying a bank forward is only safe if you know what changed since it was
built.**

**AND IT IS ALL THREE TARGETS, not just the E4XT.** Checked against the volumes
actually on the cards tonight:

    E4XT   MX9 GRATER_01   no AmpPan cord            (rebuild has one, amount 24)
    K2000  MX9GRAT.KRZ     0 programs with a PANNER
    AKAI   MX9 GRATER.P3   MODVPAN1 = 0, PANRAT = 1  (i.e. the hardware default)

All three were built at 20:22, before their respective pan paths were finished.
**The 12th input was added to the matrix specifically to carry pan modulation,
and the pan modulation is absent from every copy of it we shipped.**

**A stale claim of mine went round with them.** I told all three sessions to
expect GRATER stationary "because no writer emits the depth". That was true when
the banks were built and became false during the same evening as each writer was
fixed. The prediction was right and the stated reason was wrong — which is worse
than being wrong outright, because it would have been confirmed by the
measurement and filed as understood.

**Fix:** rebuild GRATER for all three targets and write all three cards. Needs
card writes, so it waits for Jan.

**The null is attributable, and only because four alternatives were excluded
first** (eosed) — worth recording with the entry rather than logging a bare zero:

    chain sums, no pan can appear       excluded by the id1/id3 gate (-59.48 vs +0.41)
    envelope aliased the modulation     excluded by 10 ms frames (Nyquist 50 Hz)
    balance measured in silence         excluded by the 20 dB level gate
    the pan path does not work          excluded by three programs panning on this bank

Three hours earlier the same table would have been uninterpretable.

**Incidental confirmation:** CC1 = 0 and 127 agree to 0.01 dB at every key, so the
`ModWl -> C02Amt` cord gates the pitch LFO and does not touch pan — consistent
with the cord table read.

## E4XT pan modulation CONFIRMED WORKING — and a zero-depth cord that is faithful, not broken

**Status: CONFIRMED 2026-09-06 (eosed, 66 captures, 10 ms frames).** The E4B
writer's LFO->AmpPan path works on hardware. Audio and parameters agree exactly:

    preset            median swing   AmpPan cord   amount
    P001 (wheel 0.0)     ~100 dB     src 96          72
    P005 (wheel 0.5)     12.39 dB    src 96          -9
    P008 (wheel 1.0)      0.02 dB    src 96           0     <- wired, zero depth
    (5 presets with no cord)  0.01-0.08 dB, i.e. the +0.42 dB interface trim

**P008's zero is CORRECT and traced to source.** Its XPM carries
`lfo1_to_pan 0.5276` **and `wheel_to_lfo 1.0`** — the whole depth is mod-wheel
gated. Our writer splits every LFO depth into a static part `D*(1-Kw)` plus a
ModWheel->CordN-Amount cord of `D*Kw`; at Kw=1.0 the static part is exactly zero.
So with the wheel down there is no pan, faithfully to the MPC. The other two
confirm the mechanism rather than merely fitting it:

    P001  0.7244  wheel 0.0  -> static 0.7244 x127 = 92    measured 92
    P005  0.1890  wheel 0.5  -> static 0.0945, triangle    measured -9
    P008  0.5276  wheel 1.0  -> static 0                   measured 0

**CONFIRMED 2026-09-06 23:55.** P008 pans with the wheel up, and the
ModWheel->cord-amount gate is now hardware-tested for the first time:

    CC1     level    R-L median   swing     dom Hz
      0    -33.98        0.42      0.02      31.30
     64    -33.92        0.87     39.67       6.92
    127    -33.67       -1.17    131.70       6.61

Stationary at the interface trim with the wheel down; sweeping at ~6.6-6.9 Hz
with it up. The zero-amount cord is faithful and the gate works.

**BUT THOSE SWING FIGURES ARE FLOOR-LIMITED, NOT DEPTHS** (eosed). At both wheel
positions the pan reaches an extreme where one channel drops into the noise
floor — 120/285 frames below -80 dBFS at CC1 64, 168/285 at 127 — so the number
is bounded by the floor, not by the modulation. **39.67 -> 131.70 must NOT be
read as "depth doubled with the wheel"**; it mostly reflects how many frames sit
at the extremes and how deep into the floor they go. What is solid is the
ordering: 0.02 dB at wheel 0, full-scale panning at 64 and 127.

**RIG CEILING, applies to every pan number in the matrix:** on this chain, with a
-33 dB signal and a -89 dB floor, **any swing much past ~60 dB is the noise floor
talking rather than the pan.** A real depth metric has to exclude frames where
either channel is at the floor — a different measurement, to be defined
deliberately rather than derived from these captures. Same caveat class as
P001's ~100 dB over 8-19 surviving frames.

**A THIRD FAILURE CATEGORY, and a warning about our own diagnostic (eosed).**
The K2000 work offered two branches for a stationary image — modulation not
arriving, or the block not reaching the outputs. This is a third: **correctly
wired, zero depth.** And the static-offset test proposed for telling the first
two apart would have MISLED here — a static offset moves the image, which reads
as "block fine, modulation missing", sending someone after an LFO fault that
does not exist. **Reading the cord amount cost one round trip and separated a
case no capture could.** Read the parameter before designing the experiment.

**Two caveats kept rather than quoted past:** P001's ~100 dB rests on 8-19 frames
surviving the level gate and is NOT a magnitude — record "modulates, magnitude
not established", with amount 72 as independent support. And no cord COUNT is
available: reads past a preset's real voice count return plausible values rather
than failing, so P005 and P008 return identical contents for voices 1-7 and the
read cannot say whether that is true or an echo. Presence/absence rests on voice
0 and is safe.

**Three interfaces in one night where the read never fails cleanly:** this one,
the K2000's refused function codes returning another legal function, and the
AKAI returning 19 volumes of non-printable garbage past the last partition.

## The E4B reader never reads AmpPan cords back, so E4B-sourced pan modulation is lost silently

**Status: OPEN, found 2026-09-06 while auditing.** `parsers/e4b_parser.py`
contains **zero** references to `lfo1_to_pan` / `lfo2_to_pan`. The writer emits
LFO->AmpPan cords at destination `0x41` (hardware-confirmed, 122 dB of swing),
but nothing reads them back.

Consequences, in order of reach:

- **An E4B source with pan modulation converts to anything else with the pan
  modulation dropped**, silently. Same class as the KRZ reader gap, opposite
  direction.
- **A round-trip test cannot see it.** E4B -> model -> E4B preserves the cords
  only because the writer re-derives them from a model field the reader never
  filled — i.e. it preserves them by writing zero.
- **It defeats verification of our own output.** Checking a built bank for
  "does it carry pan?" by parsing it returns 0 whatever the file holds. This
  bit the author of this note tonight: a headroom audit over the shipped
  MPC->E4B row reported "0 voices with a pan LFO" and the correct reading was
  "the reader does not populate the field". A third instance in one evening of
  a null that measured nothing — see [[feedback-check-the-check]].

**Fix:** read the mod-cord table for destination `0x41` and populate
`lfo1_to_pan` / `lfo2_to_pan`, inverting the writer's `_lfo1_sign` /
`_lfo2_sign` triangle negation. Mirror of the existing filter-cord reader.

## Pan-modulation headroom against a hard base pan — AUDITED, currently clear

**Status: NO DEFECT FOUND, recorded so it is not re-audited blind.** A pan LFO
sweeping from a base pan already near a rail is clipped on one side: an analogue
of the K2000 wire problem, where the modulation exists and cannot be heard.
Checked over the 11 matrix sources: **4 voices carry a pan LFO and all 4 sit at
base pan 0.000 with full headroom** (depths 0.528, 0.189, 0.724, 0.724). So
nothing is clipped today.

Worth a guard anyway, because the combination is legal and our own KRZ reader
was until recently producing hard-panned zones (§KRZPANNIBBLE) — a hard-panned
source plus a pan LFO is exactly the input that would have hit this. s3ked
confirmed the AKAI side independently: `PANPOS` is 0 on all three pan programs.

## AKAI: `AKAI_LFO2_RATE_HZ_PER_UNIT` is a factor of two too large — every pan program runs at half rate

**Status: REFUTED BY MEASUREMENT 2026-09-06 (s3ked, §AKAILFO2RATE). Do NOT refit
yet — treat LFO2's rate as UNMEASURED.** `models/common.py` carries
`AKAI_LFO2_RATE_HZ_PER_UNIT = 0.23708`, from §52's "LFO2 runs at exactly twice
LFO1". Measured through PAN rather than through the filter, it does not:

    PRG 5  amt  9  rat 18   swing 12.67 dB   peak 2.20 Hz
    PRG 8  amt 26  rat 37   swing 28.80 dB   peak 4.70 Hz
    NEG    amt  0           swing  0.28 dB   does not move
    POS    amt 40  rat 25   swing 77.20 dB   peak 2.99 Hz     restore byte-identical

Ratios to prediction: 0.515, 0.536, 0.504. **The falsification is the absence,
not the peak:** §52 documents a half-rate FFT artefact, so s3ked looked for the
fundamental — at PANRAT 37 the predicted 8.77 Hz is **40.7 dB below** the 4.67 Hz
peak. A subharmonic artefact leaves the fundamental present; there is nothing
there at all.

**Likely mechanism, and it is the centroid trap's twin:** §52 measured LFO2
**through the filter**, where a bipolar sweep presents *two* brightness
excursions per cycle to a detector that responds to magnitude rather than sign.
Measured through pan, where balance is signed, the rate is LFO1's.

**Consequence, live on a card:** all three pan programs on `MX9 MPC8 01` run at
half their intended rate. PRG 8 wants 8.7 Hz and gets ~4.4. Reaching 8.7 Hz
needs PANRAT 73, not 37.

**Why not to refit now:** 150 usable frames at 0.67 Hz resolution. The factor of
two is unambiguous; the constant is not. §52's value has failed once already
tonight — replacing it from coarse data would just be the next thing to fail.
A proper sweep is running.

**AND A CORRECTION OF THIS PROJECT'S OWN CLAIM.** Earlier the same evening this
file's author asserted that s3ked's `PANRAT 37 -> 8.77 Hz` and our KRZ's parsed
`lfo1_rate 8.7` were "the same number arriving by two routes that share nothing",
and called §52 externally validated. **They are not independent.** Both descend
from the same source program; what agreed was our conversion constant with
itself. The *source* value 8.7 Hz was corroborated; the constant that turns it
into a byte was never tested by that comparison and is the thing that is wrong.
A check that confirms a mechanism ran rather than what it did — the same failure
this project spent the day warning others about. See [[feedback-check-the-check]].

## K2000: we write a PANNER and never spread its two wires, so it is silent

**Status: ROOT-CAUSED AND HARDWARE-CONFIRMED 2026-09-06 (§K2PANWIRES). Writer
fix not yet applied.** Our first PANNER emission produced a completely
stationary image. Every byte was correct; the fault is a field we never write.

**The manual says it outright** (K2000 Series Musician's Guide p284, PANNER):

> By itself the PANNER doesn't change the pan position of the sound. It just
> defines what percentage of the currently selected layer's sound goes to each
> wire. ... So when you use the PANNER function, you'll also want to adjust the
> Pan parameters on the OUTPUT page, setting the upper wire's pan fully right,
> and the lower wire's pan fully left. This will enable you to hear the effect
> of the PANNER function.

PANNER is a **single wire in, DOUBLE wire out** — it splits the layer between an
"upper" and a "lower" wire and does NOT itself position anything. The OUTPUT
page then pans each wire. **If both wires sit centred, they sum and the panner
is inaudible no matter how it is driven.** We wrote `Src1 = LFO1`, `Depth 26`
(52 %) and left the OUTPUT page at its inherited default: both wires centred.

**Measured, on program 263 (MX9MPC8's 2-pole bass source) against 208 (pre-fix twin):**

    Adjust +50%, wires centred        image moved  0.01 dB   <- static, still nothing
    Src1 = LFO1 Depth 52%, centred    balance sd  0.015 dB
    Src2 = RandV2 MaxDpt 100%, MW127  balance sd  0.045 dB
    wires SPREAD                      balance sd 10.118 dB, peak 8.70 Hz / 13.29 dB

8.70 Hz is LFO1's own rate, so the modulation we wrote was always there and
never reached the outputs. The factory panner in the source bank (program 246,
Src2 = GLFO2, DptCtl = MWheel) moves as expected — sd 1.94 at MWheel 0, 6.49 at
MWheel 127 — and its OUTPUT page has the wires at hard left and hard right.
**That contrast is the whole finding.**

**Why every earlier check passed:** the panel renders algorithm 2, F3 block 40
PANNER, Src1 LFO1, Depth 52 % — all correct, because they ARE correct. The
missing setting lives on a different page, in a field whose default is benign
for every algorithm that does not split the signal.

**The subject check that made it interpretable.** Before believing the null I
verified the edits were reaching the program being recorded, by pushing the
panner's own `Pad` from 0 dB to 18 dB: level moved **-18.08 dB**. `Pad` is a
PANNER field, so this simultaneously proved the block was in the audio path and
that the panner's gain stage worked while its pan did nothing. An earlier
attempt at the same check pressed `Pad` DOWNWARD, where its range floors at 0,
so nothing moved and the reading was inconclusive rather than negative — worth
remembering: **a control that cannot move is not evidence that nothing responds.**

**THE FIX (corrected 2026-09-06 23:09, after the first attempt shipped wrong):**
the two wire pans must carry OPPOSITE signs — `0x52[14] |= 0x70` (+7, right) and
`0x53[14] |= 0x90` (-7, left), low nibbles preserved, byte 2 untouched. The first
attempt reused the stereo path's `0x90`/`0x94`, which are **both -7**, putting
both wires hard left — which sums exactly as centre does, so the bank shipped with
the same symptom it was meant to fix (measured on the card: L-R +63.66 dB, nothing
at the LFO rate). Both-left and both-centre are indistinguishable, so a test that
asks only "did the bytes change" passes; it has to ask whether the two wires
differ in SIGN.

**THE FIX:** when the writer emits a PANNER it must also set the layer's OUTPUT
page wire pans — upper fully right, lower fully left — not just Src1/Depth.
Ranges from p284: Adjust ±100 %, KeyTrk ±16 %/key, VelTrk ±200 %, Pad 0/6/12/18
dB, Src1/Src2 depths ±200 %. p284 also confirms independently that PANNER exists
only in algorithms **2, 13, 24, 26**, which matches `_ALG_WITH_PANNER` in the
KRZ parser — the two were derived separately and agree.

**This is the fifth instance in one day of "the route is wired and something on
it is at zero"** (s3ked's observation): MODVPAN1 zero with the source wired,
MODVFILT3 against SUSTN2 zero, an envelope depth times zero sustain, and now
two output wires summing at centre. The pattern is that our writers carry
sources and primary depths across and leave secondary/destination fields at
whatever the target block happened to hold. **An audit of every writer for
unset secondary fields is now indicated, rather than five separate patches.**

## AKAI: reading past the last partition returns plausible garbage, not an error

**Status: MACHINE BEHAVIOUR, not our bug — but it defeats the freshness rule we
had been using.** Found by s3ked 2026-09-06 on HD4-work-v12 (300 MB, five real
partitions A–E).

    partition F   echoes E                      (the known stale-echo case)
    partition G   19 "volumes", names such as
                  '??????X?K?J?'  '0???????????'  '??Y?????????'  'O?????U?????'

Beyond the last real partition the S3000XL does **not** error and does **not**
return empty: it reads past the partition table and returns plausible-SHAPED
garbage. Our own image is not at fault — `read_akai_image` on the same file
reports exactly A:20, B:5, C:1, D:1, E:1 — so this is the machine offering A–H
regardless of how many exist.

**Why it matters: our freshness rule is necessary but not sufficient.** We had
been telling every session "a listing identical to the previous one means
ABSENT, not present". G's listing is *not* identical to F's, so the rule passes
it, and a checker that counts volumes would report "partition G holds 19
volumes" and be entirely wrong.

**The reliable tell is the NAMES, not the count** (s3ked). Real volume names are
printable ASCII in a fixed 12-character field; these are mostly non-printable.
**Validate name bytes rather than only comparing listings** — one check that
catches both the echo and the garbage. Worth adding to any partition sweep.

Same family as the echo itself: the machine's directory read never fails
cleanly, it always returns *something shaped like an answer*.

## AKAI: a filter envelope with sustain 0 converts as no envelope at all

**Status: NOT A WRITER BUG. Patch applied and reverted the same hour, measured
inert.** The machine gates on SUSTN2 exactly as the writer did — §156 makes the
shift the product of SUSTN2 and depth, §177 says SUSTN2 0 mutes the route — so
a depth written at sustain 0 changes bytes and no sound (0.03/0.08 dB on a rig
reproducing to 0.02). A recurrence: s3ked stopped the same patch two days ago.

**What remains open, restated:** an S3000XL cannot represent a filter envelope
with sustain 0 and a long decay. That is a LIMITATION wanting a diagnostic
(`content_lost=True`), not a byte. A two-byte alternative (depth + SUSTN2 60)
would change the envelope's shape and is a fidelity decision, not a fix.

**Separate bug found on the way:** `_env2_amount` in the AKAI reader ignores
SUSTN2, so it over-reads a muted filter route as a large envelope. The
writer/reader asymmetry should be fixed on the reader side. Found by static reading 2026-09-06, confirmed same day.
**Blocked on:** one measurement — no new card crossing needed if the existing
KR→AK captures can be split by program.

**2026-09-06 — THE PRODUCT LAW IS REFUTED AT THESE VALUES (s3ked, §AKAISUSTSAT).**
The ceiling run drove PRG 9 (found at SUSTN2 0 / MODVFILT3 0) through four
states and back. **SUSTN2 60 and 99 are indistinguishable** — at both depths,
on all three keys:

    state          k36 centroid / peak      k60 cen   k84 cen
    as found        217 Hz  -30.6            1019      2755
    sus60 dep33     152 Hz  -21.6             875      2641
    sus99 dep33     153 Hz  -21.6             871      2737
    sus60 dep50     129 Hz  -16.7             757      2662
    sus99 dep50     129 Hz  -16.7             758      2539
    restored        219 Hz  -30.6             998      2744   (byte-identical)

This project predicted **813 Hz against 7858 Hz** for the 60/99 pair — 3.3
octaves apart. It is not there. **Depth does scale** (33→50 gives +4.9 dB and
moves the centroid 152→129 Hz), so the depth term is live and the SUSTN2 term
**saturates at or below 60**. Either §156's `octaves = 0.002612 x SUSTN2 x depth`
does not hold at these values, or the resting corner is not the 22.55 Hz the
arithmetic assumes.

**The honest position is that we have no working model of this route**, not that
we have one needing a constant refitted. Two predictions have now failed on it
in one day: one withdrawn for being ~3x too steep, this one refuted outright.
Do not fit to these five points either — they establish saturation, not a law.

**One consequence worth keeping:** the two-byte alternative below wanted
SUSTN2 60. These data say 60 and 99 buy the same thing, so if that route is ever
taken, 60 is not a compromise value — it is already at the ceiling.

**DETECTOR WARNING, and it generalises (s3ked).** On this material the
**centroid FALLS as the filter opens** — 217 → 152 → 129 Hz while the level
rises 13.9 dB. Opening a ~22 Hz corner on bass first admits the fundamental,
which then dominates the spectrum and pulls the centroid down. **Centroid is
close to a reverse indicator here; level is the better detector.** Same family
as the day's other traps: a detector that looks right, moves plausibly, and is
measuring something other than what its name says.

**Lifting the gate is not by itself the fix.** The AKAI scales the ENV2 corner
by the envelope's level, so writing a depth with SUSTN2 0 leaves the sustained
corner where it was (22.6 Hz) and buys only a transient. Matching a K2000
program that holds its corner open for 9.4-35 s needs the depth AND a long
enough DEC2, and the decay rate law tops out near 40 s — the 35 s program is at
the machine's edge. That law was also measured on the amplitude envelope; that
ENV2 shares it is unverified.

`akai_filter_env_depth` returns depth 0 whenever the source's filter-envelope
sustain is 0, on the grounds that a zero-depth envelope is inaudible. A sustain
of 0 does not mean zero depth: it means percussive. On the KRZ matrix source six
of twelve programs have sustain 0 with decays of 9.4–35 seconds over a resting
corner of 23.2 Hz, so the K2000 plays them open for the whole note and we write
them shut. 52 of 97 keygroups get DEPTH 0.

**Pass-1 evidence is in and is weaker than it first looked.** Strings slope
−28.52 dB against organs −6.07, but the three groups have different keygroup
geometry — the 4-keygroup strings are measured across three sample changes at
near-native pitch, the 3-keygroup strings through four octaves of stretch inside
one keygroup, and the organs across a boundary — so cross-group slopes are not
like-for-like and **no target-side magnitude should be quoted**. Three were
derived and all three withdrawn. The organ step at k72→k84 also sits inside one
keygroup, so sample stretch explains it as well as a corner crossing does. DEPTH
remains collinear with instrument family. **The A/B/A byte change is the only
test here that is immune** — same program, keys, keygroups and samples, one byte
different, so every geometric confound appears in both arms and cancels.

Candidate cause of the §178 KR→AK darkness (s3ked measured −17.29 dB across
k36→k84). **The obvious check does not work:** the six sustain-0 programs are
exactly the six string/pad programs and the six sustain-0.61 ones are exactly
the six organs, so splitting by depth is the same as splitting by instrument.
That can falsify the hypothesis but cannot support it. The isolating test is to
write a non-zero depth to one DEPTH-0 program in RAM and re-measure the same
program — s3ked has this staged and it needs no card crossing.

Not the corner floor — that is reached correctly on every path that has a
velocity sweep, and KRZ has none. See `docs/RESOLUTION_NOTES.md`
§AKAIENV2SUSTAIN and §AKAIFLOORSPAN.

## MPC: a pitched sample with no WAV `smpl` chunk converts as fixed-pitch

**Status:** open, found 2026-09-06 from a two-generation file diff, not yet
hardware-confirmed (but eosed measured the program moving, which is consistent).
**Blocked on:** a decision on the fallback, not on hardware.

`xpm_parser.py:1921` sets `non_transpose = ignore_base or (raw_root == 0 and
full_range)`, and the rescue at `:2040` only clears it when the WAV carries a
`smpl` unity note. A pitched sample whose root was never recorded and whose WAV
has no `smpl` chunk therefore converts as **fixed pitch across the whole
keyboard** — `vpar[38] = 1` on E4B. Whole-program fidelity loss, and silent.

Found on the v7 MPC-E4 row: a single-zone lead is the only preset whose chunk
differs from the v5 build, by exactly that one byte. The XPM is byte-identical
between generations, so the WAV is the only differing input; the v7 copy has
only `fmt ` and `data`.

The `else` branch below already has the right fallback — WAV unity note, else
the keygroup low note — but it is unreachable once the flag is set. The
heuristic reads "no root + full range" as "fixed-pitch one-shot" when it can
equally mean "pitched sample, root not recorded".

Prevalence in the 11-program matrix set: 7 XPMs have `RootNote` 0 throughout
with `IgnoreBaseNote` False, 7 of 152 WAVs lack `smpl`, and 1 program lands in
the intersection.

See `docs/RESOLUTION_NOTES.md` §XPMNOROOTFIXED.

## KRZ: zones ship above their own computed up-pitch ceiling

**Status:** open, hardware-confirmed 2026-09-06 (k2kremote). Symptom located
precisely; the reason the clamp does not fire is NOT yet established.
**Blocked on:** nothing — this is a code question, not a hardware one.

`_compute_playback_ceiling()` is correct and `krz_writer.py:626-629` applies it
as `hi_key = min(hi_key, ceiling)`. Yet six of the ten E4B-sourced programs in
`MX9E4KR` ship with `hi_key` 79 against their own ceiling of 74 or 72:

    preset          zone    root  rate     ceiling   shipped
    bass A          21-79    50   24000       74        79    5 wrong keys
    bass B          21-79    50   24000       74        79
    bass C          21-79    50   24000       74        79
    bass D          21-79    48   24000       72        79    7 wrong keys
    bass E          21-79    48   24000       72        79
    bass F          21-79    48   24000       72        79
    bass G/H   , JP4 21-79    57   26939       79        79    correct
    bass J          21-79    60   23939       84        79    5 keys lost

**Confirmed on hardware:** `bass A` tracks pitch through k74 and plays k75
to k79 at a FROZEN wrong pitch — full level, clean, ~1.5 semitones flat by k79.
`bass B` reproduces it exactly. `bass G` and `bass J` are clean
through 79 as predicted. **A level check passes every frozen key** (−14.8 dBFS);
only a pitch sweep finds them.

Note the constant is wrong in BOTH directions: too high for six programs
(frozen keys) and too low for `bass J` (five keys lost that would track).

**Next step is to find why the clamp does not bind** — candidates: the sample
lookup returning None so the `if sample is not None` branch is skipped; a later
pass (`_coverage_remap_voices`, called at :2670) extending zones after the clamp;
or `r_zone - zone.coarse_tune` differing from the zone root. Not yet checked.

See `docs/RESOLUTION_NOTES.md` §KRZCEILINGUNCLAMPED.

---

## AKAI writer never writes `LFODEP` — converted vibrato is still silent (§AKAILFODEP)

**Status:** open (2026-09-06), found by code inspection while building
`docs/MODULATION_MATRIX.md`. **Not hardware-confirmed** — the claim below is an
absence in our own source, and the silence it predicts has not been measured.
**Blocked on:** an S3000XL A/B, and a decision on whether `LFO1WAVE` ships with
it (see below).

`writers/akai_s3000_writer.py:2118` writes the LFO→pitch **gate**:

    k[_AKAI_LPTCH_OFFSET] = (AKAI_LFO_DEPTH_CAL_LPTCH if _vib > 0.0 else 0)

but the **depth** byte `LFODEP` (program offset `0x22`) is written **nowhere**
and is absent from `_PROGRAM_HW_DEFAULTS` (`:1798-1826`). Both verified by grep.

The measured law is `rms_cents = 0.13127 · LFODEP · L_PTCH`
(`models/common.py:1014`, s3ked §160), and `akai_lfo_depth_to_pitch`'s own
docstring records the two-sided gate established in the same run: **`LFODEP=0`
with `L_PTCH=50` produces no vibrato**, just as `L_PTCH=0` with `LFODEP=99`
produces none.

So the 2026-08-24 fix (§AKAILPTCH) restored the routing and left the depth at
zero. It is the same defect one byte over, and the comment at `:2100-2116`
describing the L_PTCH half reads as a complete account of a problem that is
still half present.

This is exactly the failure shape the writer's own `_PROGRAM_HW_DEFAULTS` note
warns about at `:1511-1513` — "an amount without its matching source is silently
inert" — inverted: here it is a source without its matching amount.

Fix strategy: `docs/RESOLUTION_NOTES.md` §AKAILFODEP.

---

## KRZ writer drops a negative `LfoPitch` (§KRZLFOSIGN)

**Status:** open (2026-09-06), found by code inspection while building
`docs/MODULATION_MATRIX.md`. **Not hardware-confirmed.**
**Blocked on:** nothing to diagnose; it wants a bench pass before pushing
because it changes emitted bytes on real material.

`writers/krz_writer.py:2222` gates the LFO→pitch cord on

    if getattr(voice, 'lfo1_to_pitch', 0.0) > 0.0:

— **strictly positive**. `parsers/xpm_parser.py:1798` clamps `LfoPitch` to
−1..+1, and `parsers/akai_s3000_parser.py` and `parsers/e4b_parser.py` both
produce signed depths (the E4B one deliberately, for the triangle-phase fix at
`e4b_parser.py:571-580`). Any source asking for an inverted-phase vibrato
therefore reaches the K2000 with **no vibrato at all**, rather than with the
phase flipped.

Inconsistent with its two neighbours in the same function, both of which were
made explicitly signed on 2026-08-25: the filter-envelope depth
(`krz_writer.py:2212`) and the velocity→filter depth (`:2143-2148`).

Fix strategy: `docs/RESOLUTION_NOTES.md` §KRZLFOSIGN.

## KRZ: pan read a panner WIRE, not the layer's pan — FIXED, rebuild pending

**Status: cause identified and FIXED 2026-09-06** (algorithm gate in
`krz_parser`, `_ALG_WITH_PANNER = {2, 13, 24, 26}` per the K2000 manual Ch.14,
verified against the PDF by Jan and against the panel by k2kremote).
**Remaining work: rebuild the KRZ→E4B and KRZ→AKAI rows and re-capture.**

Every zone of `MXKR.KRZ` parses as pan −1.0, so KRZ→E4B writes zone pan −32 and
KRZ→AKAI writes −50, on all 58 zones, while the S3-, S1- and E4B-sourced rows
are centred. The E4XT captures of that row consequently have a dead right
channel — found because Jan looked at his AD converter and said so twice while
two sessions told him the rig was fine.

The field is byte 14's high nibble of the F4 HOB segment; `MXKR` carries `0x94`
throughout. Two's complement (0 = centre) makes that hard left; offset binary
(8 = centre) makes it nearly centred. **Files cannot decide**: the reader and
writer share the convention, so they round-trip perfectly either way.

**Do not change the decode before the hardware reading** — if the bank really is
hard-panned, the "fix" breaks every correct conversion. If it is offset binary,
our decode is wrong by 8 steps on every KRZ bank ever read.

Rebuild of the KRZ→E4B and KRZ→AKAI rows follows a fix, and eosed wants the E4B
row re-captured regardless: the one-sided path costs ~6 dB at the quiet end of
every velocity ramp, so its low-velocity numbers are floor-limited.

See `docs/RESOLUTION_NOTES.md` §KRZPANNIBBLE.

## Dynamic panning: the K2000 has it, and so do both targets

**Status:** open, scoped 2026-09-06. **All three machines can carry it** — the
"which targets can represent it" question is answered and the answer is
favourable.
**Blocked on:** the K2000 being free, for the source-side field RE.

The K2000's PANNER (algorithms 2, 13, 24, 26) is a DYNAMIC panner: it splits a
layer across two wires panned hard left and hard right, and sweeps the balance
with `Adjust`, `KeyTrk` (±16%/key), `VelTrk` (±200%) and two modulation sources
with min/max depth. Two of six programs measured on the panel run `Src2 = LFO2`
with `MinDpt 4%` / `MaxDpt 56%` — auto-pan under the mod wheel.

We now write those layers as centred (§KRZPANNIBBLE), which is the right static
position, but **the movement is dropped entirely** — key-tracked pan, velocity
pan and LFO auto-pan all convert to a stationary centre image. No target is
given any of it.

**TARGET SUPPORT, established from the manuals rather than assumed:**

    E4XT   "Amplifier Volume, Amp Pan" is in the EOS 4.0 modulation-destination
           list, so a PatchCord can drive pan. The destination ID is NOT in
           E4B_FORMAT.md and needs one RE step (set the cord on the panel, dump
           over SysEx, read the byte).

    AKAI   S3000XL Operator's Manual p.75, EDIT PROGRAM / PAN PAGE: "the
           characteristics of the AUTO PANNING functions", three modulation
           inputs, each +/-50 --
             Lfo2 > pan   "the classic auto panner effect ... moving between
                          left and right at a rate set by LFO 2"
             Key  > pan   "+50 the sound will pan from left to right across the
                          keyboard", -50 the reverse
             Bend > pan   via the modulation wheel
           and "any combination of controllers can be mixed together", with
           Bend, Pressure, External, Velocity and LFO1 all named as sources.

**The AKAI is arguably the closest match of the three to the K2000's panner:**
`Key > pan` is the K2000's `KeyTrk`, `Lfo2 > pan` is `Src2 = LFO2`, and velocity
is available as a source where the K2000 has `VelTrk`.

**This also makes the "route is dead" finding suspect.** §52 measured LFO→pan as
dead. The panel has a `Lfo2 > pan` DEPTH field separate from `PANRAT` (the LFO's
rate), and Jan's photograph shows it at **+00** on a resident program. Driving
the rate while the depth is zero produces exactly a dead route — the same shape
as §AKAIENV2SUSTAIN (patch inert because the machine gates elsewhere) and
§AKAILFODEP (we write the gate and never the depth). **Re-measurement with the
depth explicitly non-zero is queued with s3ked.**

**A hardware caveat to carry into any implementation**, from the same page:
"Due to limitations with the panning hardware, whilst slow sweeps work well,
fast sweeps may, on some sounds, introduce some 'zipper noise'." So a fast K2000
auto-pan may not translate cleanly even when the routing does.

Wants a diagnostic carrying `content_lost` for whatever cannot be carried, same
class as the unrepresentable filter envelope in §AKAIENV2SUSTAIN.

## K2000: map every algorithm's blocks and function codes (long overnight run)

**Status: PARKED 2026-09-06 by Jan — specified, deliberately not started.**
Nothing is blocking it: it is RAM-only, the procedure is complete, and the three
cross-checking sources are identified. It is deferred because it wants a long
uninterrupted run, not because anything is missing.

**Do not start this without Jan saying so.** No peer session has been asked for
it and none should pick it up from this file.
**Scale:** 31 algorithms x up to 4 blocks x up to ~17 functions. Hours, hence
overnight.

**What we have today is four algorithms out of thirty-one, hand-transcribed from
the manual** (`krz_writer.py`, the filter-function table). It carries names, not
byte codes, and only for algorithms 1, 2, 5 and 16 — the ones the writer already
emits. Every algorithm choice the writer makes is therefore constrained by what
was convenient to read rather than by what the machine offers.

**Goal:** a byte-level lookup table — for each algorithm, which function each
block can hold, and the code that selects it. That turns `_k2_filter_plan` from a
hand-written mapping of four cases into a lookup over the real space, and it is
the prerequisite for choosing an algorithm on the merits (slope, resonance,
separation, panner, shaper) rather than from the handful we happen to know.

**Method** (extends the panner diff that worked on 2026-09-06):

    for each algorithm 1..31:
        set CAL[29] = algorithm, confirm on the panel
        for each block F1..F4:
            walk the function list with the wheel
            record the PANEL NAME and the byte at that block's offset
            dump the object and diff after each step

See `docs/RESOLUTION_NOTES.md` §K2ALGWALK for the full procedure, the validation
rules and the traps — several of which cost real time on 2026-09-06 and are not
obvious.
