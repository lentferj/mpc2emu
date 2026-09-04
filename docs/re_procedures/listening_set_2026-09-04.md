# The listening set, rebuilt 2026-09-04

**Status:** built, written to the AKAI and EMU cards. KRZ leg awaiting the card swap.
**Builder:** `tests/re_banks/build_listen3.py`
**Artefacts:** `~/temp/listen3/` — `LISTEN3.E4B`, `LISTEN3.KRZ`, `TC13_LISTEN/`

## Why a rebuild

The set staged earlier the same day predates two writer changes that move
exactly what it exists to judge — the `Vel+` cord source (§E4XTVELSRC) and the
velocity-curve fit (§MPCVELSHAPE). Banks built before those are evidence about
a pipeline that no longer exists. The AKAI leg had never been written to the
card, which is the only reason it wasn't stale on hardware too.

## The comparison

**Source versus conversion, not old versus new.** Every source lives on its own
machine already, so the A/B is: play it there, play the conversion on the
target, listen. One bank per target with every source in it as a preset, so
switching is a program change and only the *bank load* needs a human.

| preset | swing | what it exercises |
|---|---|---|
| `MPC MIXED` | 0.0 / 17.2 / 19.0 dB across 4 voices | one voice asking for **no** velocity response beside two asking for 17–19. A single template cord gets this wrong in both directions at once, at any setting. |
| `MPC SOFT` | uniform 5.9 dB | ordinary material, where a few dB of error is still audible |
| `MPC FULL` | uniform 42.1 dB (`VelocitySensitivity` 1.0) | the logarithmic-curve extreme the fit was built for — 69 % of the sampled corpus |
| `AKAI VEL` | 35.9 dB about velocity 64 | the pivot case `Vel+` was chosen for |

Sources are MPC-authored programs from the MPC's own SD-card backup under
`EXPANSIONS/`, so the identical program can be played on the MPC. Jan's
pointer: `KEYGROUPS/` is older ConvertWithMoss output and **0 of 60** files
there carry `VelocitySensitivity` at all; `EXPANSIONS/` is MPC-authored and
**3,776 of 3,801** do. Sampling 140 gives 96 uniform 1.0, 19 at zero, 18 at
another uniform value and 6 mixed — so all four cases are real material.

## Where it lives

| target | location |
|---|---|
| E4XT | EMU card, `CD1-E4XTWORK.iso`, bank `LISTEN3` (with VELPLUS and VOLCAL) |
| AKAI | HD4, volume `TC13 LISTEN`, PRGNUM **94 / 95 / 96** |
| K2000 | `~/temp/listen3/LISTEN3.KRZ` — awaiting the card swap |

## Four things that had to be measured rather than assumed

**The mixed source was chosen by playable range, not by being first.** Of the
six mixed-swing presets found, four are unusable on a K2000 after the
downsample — reliable only to keys 35, 35 and 11. `Bass-DX7 Release` is the one
that stays playable to key 127. Above the up-pitch ceiling the KRZ writer's
hole-fill extends a **neighbouring** sample over those keys, so such a preset
does not fall silent, it plays the wrong thing — which in a listening test is
worse than absent, because it invites the listener to blame the conversion.

**The uniform-1.0 source was chosen by size.** "First alphabetically" is a
reproducible rule that selected a 40 MB multisample — 80 % of a bank against
the K2000's 64 MB sample-RAM ceiling. Now "smallest qualifying", equally
reproducible and unable to blow the budget. Final KRZ: **23.3 MB**.

**The AKAI source was chosen by swing *and* range together.** The card's
largest swing (43.0 dB) is reliable only to key 37 once converted. The 35.9 dB
program reaches key 71.

**The KRZ leg goes through `convert.py`'s own headroom downsample**, mirrored
in `build_listen_banks`. The 2026-09-02 set skipped it, every key landed above
its sample's ceiling, and Jan heard it: *"note 71 and below play something that
is not key tracked."*

## Card handling

`TC13 LISTEN` was appended **in place** to a local working copy first. Before
the card was written, the working image was read back and checked: all 18
pre-existing volumes keep their names and file counts, PRGNUM 94/95/96 are
owned by the new volume alone, and the card's own `HD4.img` was backed up
byte-verified to `~/temp/HD4-card-live-20260904.img`.

On the EMU card the listening bank joined `VELPLUS` and `VOLCAL` on one disc
rather than displacing either — both are still awaiting measurement. Both card
manifests updated.
