# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# TAL-Sampler preset (.talsmpl) default-parameter template.
#
# These are the neutral default values of a TAL-Sampler v11 program (the synth
# section — 3 oscillators/filters/LFOs, mod matrix, FX, tuning tables — that
# mpc2emu does not model).  They were read off a freshly-saved "Startup" preset
# and are reproduced here as *format defaults* (functional interop data) so the
# writer can emit a complete, loadable program and override only the handful of
# attributes mpc2emu actually controls.  No TAL preset file is bundled.
#
# TAL-Sampler is © Patrick Kunz / Togu Audio Line; the .talsmpl format is their
# work.  This module only encodes the default parameter values needed to write a
# compatible file.

import xml.etree.ElementTree as ET

TAL_VERSION = '11'

# Default <program> attributes (v11).  Overridden per-preset by the writer.
_PROG_DEFAULTS = {
    'RR2': '0.5', 'RR3': '0.0', 'adsrampattack': '0.0', 'adsrampcrush': '0.0',
    'adsrampdecay': '0.0', 'adsramphold': '0.0', 'adsramprelease': '0.0',
    'adsrampsustain': '1.0', 'adsrmodattack': '0.0', 'adsrmodcrush': '0.0',
    'adsrmoddecay': '0.0', 'adsrmodhold': '0.0', 'adsrmodrelease': '0.0',
    'adsrmodsustain': '1.0', 'adsrvcfattack': '0.0', 'adsrvcfcrush': '0.0',
    'adsrvcfdecay': '0.0', 'adsrvcfhold': '0.0', 'adsrvcfrelease': '0.0',
    'adsrvcfsustain': '1.0', 'category': '', 'chorusenabled': '0.0', 'choruslock': '0.0',
    'chorusone': '0.0', 'chorustwo': '0.0', 'daclock': '0.0', 'delaylock': '0.0',
    'effectdelayamount': '0.5', 'effectdelaydepth': '0.0', 'effectdelayfeedback': '0.5',
    'effectdelayhigh': '0.0', 'effectdelaylow': '1.0', 'effectdelayon': '0.0',
    'effectdelayrate': '0.0', 'effectdelayspread': '0.0', 'effectdelaysync': '0.0',
    'effectdelaytime': '0.5', 'effectdelaytimespread': '0.5', 'effecteq1amount': '0.5',
    'effecteq1enabled': '0.0', 'effecteq1freq': '0.5', 'effecteq1q': '0.5',
    'effecteqhp': '0.0', 'effectreverbamount': '0.5', 'effectreverbdelay': '0.0',
    'effectreverbhigh': '0.0', 'effectreverblow': '1.0', 'effectreverbon': '0.0',
    'effectreverbsize': '0.5', 'eqlock': '0.0', 'filtercutoff': '1.0', 'filterenvelope': '0.5',
    'filterkeyboardvalue': '0.5', 'filterlayera': '0.0', 'filterlayerb': '0.0',
    'filterlayerc': '0.0', 'filterlayerd': '0.0', 'filterlock': '0.0', 'filtermode': '0.0',
    'filtermodea': '0.0', 'filtermodeb': '0.0', 'filtermodec': '0.0', 'filtermoded': '0.0',
    'filterresonance': '0.0', 'globalpitchbendrange': '0.0', 'globalvelocity': '0.0',
    'graindensitya': '0.0', 'graindensityb': '0.0', 'graindensityc': '0.0',
    'graindensityd': '0.0', 'graindirectiona': '0.0', 'graindirectionb': '0.0',
    'graindirectionc': '0.0', 'graindirectiond': '0.0', 'grainpitchspreada': '0.0',
    'grainpitchspreadb': '0.0', 'grainpitchspreadc': '0.0', 'grainpitchspreadd': '0.0',
    'grainpositionspreada': '0.0', 'grainpositionspreadb': '0.0',
    'grainpositionspreadc': '0.0', 'grainpositionspreadd': '0.0', 'grainrandomoctavea': '0.0',
    'grainrandomoctaveb': '0.0', 'grainrandomoctavec': '0.0', 'grainrandomoctaved': '0.0',
    'grainstereospreada': '0.0', 'grainstereospreadb': '0.0', 'grainstereospreadc': '0.0',
    'grainstereospreadd': '0.0', 'grainwindowtypea': '0.0', 'grainwindowtypeb': '0.0',
    'grainwindowtypec': '0.0', 'grainwindowtyped': '0.0', 'highPassa': '0.0',
    'highPassb': '0.0', 'highPassc': '0.0', 'highPassd': '0.0', 'includewaveinpreset': '0.0',
    'layertransposea': '0.5', 'layertransposeb': '0.5', 'layertransposec': '0.5',
    'layertransposed': '0.5', 'lfophase1': '0.0', 'lfophase2': '0.0', 'lfophase3': '0.0',
    'lforate1': '0.300000011920929', 'lforate2': '0.300000011920929',
    'lforate3': '0.300000011920929', 'lfosync1': '0.0', 'lfosync2': '0.0', 'lfosync3': '0.0',
    'lfotrigger1': '0.0', 'lfotrigger2': '0.0', 'lfotrigger3': '0.0', 'lfounipolar1': '0.0',
    'lfounipolar2': '0.0', 'lfounipolar3': '0.0', 'lfowaveform1': '0.0', 'lfowaveform2': '0.0',
    'lfowaveform3': '0.0', 'lowPassa': '0.0', 'lowPassb': '0.0', 'lowPassc': '0.0',
    'lowPassd': '0.0', 'masterlock': '0.0', 'mastertune': '0.5', 'matrixlock': '0.0',
    'microtuningFileName': '', 'modulation': '0.0', 'modulationsamplestretcha': '0.0',
    'modulationsamplestretchb': '0.0', 'modulationsamplestretchc': '0.0',
    'modulationsamplestretchd': '0.0', 'modulationsamplestretchsizea': '0.0',
    'modulationsamplestretchsizeb': '0.0', 'modulationsamplestretchsizec': '0.0',
    'modulationsamplestretchsized': '0.0', 'mpeEnabled': '0.0', 'mtsenabled': '0.0',
    'numvoices': '0.3636363744735718', 'oneshot': '0.0', 'paramReserved24': '0.0',
    'paramReserved34': '0.0', 'paramReserved44': '0.0', 'parammodmatrix0': '0.0',
    'parammodmatrix1': '0.0', 'parammodmatrix2': '0.5', 'parammodmatrix3': '0.5', 'path': '',
    'polymode': '1.0', 'portamentointensity': '0.0', 'portamentomode': '0.0',
    'portamentotime': '0.0', 'programname': 'Startup', 'reserved0b': '0.0',
    'resonancea': '0.0', 'resonanceb': '0.0', 'resonancec': '0.0', 'resonanced': '0.0',
    'reverblock': '0.0', 'sampleadcq': '1.0', 'sampleasymemuii': '1.0', 'samplebits': '1.0',
    'sampledacq': '1.0', 'sampledacvolume': '1.0', 'sampledelaya': '0.0',
    'sampledelayb': '0.0', 'sampledelayc': '0.0', 'sampledelayd': '0.0',
    'sampleenableda': '1.0', 'sampleenabledb': '0.0', 'sampleenabledc': '0.0',
    'sampleenabledd': '0.0', 'sampleenda': '0.0', 'sampleendb': '0.0', 'sampleendc': '0.0',
    'sampleendd': '0.0', 'sampleendui': '0.0', 'samplefilteroff': '0.0',
    'samplefinetunea': '0.5', 'samplefinetuneb': '0.5', 'samplefinetunec': '0.5',
    'samplefinetuned': '0.5', 'samplehiss': '0.0', 'samplejitter': '0.0',
    'sampleloopenda': '0.0', 'sampleloopendb': '0.0', 'sampleloopendc': '0.0',
    'sampleloopendd': '0.0', 'sampleloopendui': '0.0', 'sampleloopfadea': '0.0',
    'sampleloopfadeb': '0.0', 'sampleloopfadec': '0.0', 'sampleloopfaded': '0.0',
    'sampleloopstarta': '0.0', 'sampleloopstartb': '0.0', 'sampleloopstartc': '0.0',
    'sampleloopstartd': '0.0', 'sampleloopstartui': '0.0', 'samplepana': '0.5',
    'samplepanb': '0.5', 'samplepanc': '0.5', 'samplepand': '0.5',
    'sampleresamplermode': '0.0', 'samplesamplerate': '1.0', 'samplesaturation': '0.0',
    'samplestarta': '0.0', 'samplestartb': '0.0', 'samplestartc': '0.0', 'samplestartd': '0.0',
    'samplestartui': '0.0', 'samplestretcha': '0.5', 'samplestretchb': '0.5',
    'samplestretchc': '0.5', 'samplestretchd': '0.5', 'samplestretchfollowa': '0.0',
    'samplestretchfollowb': '0.0', 'samplestretchfollowc': '0.0',
    'samplestretchfollowd': '0.0', 'samplestretchsizea': '0.5', 'samplestretchsizeb': '0.5',
    'samplestretchsizec': '0.5', 'samplestretchsized': '0.5', 'sampletunea': '0.5',
    'sampletuneb': '0.5', 'sampletunec': '0.5', 'sampletuned': '0.5', 'samplevolumea': '0.5',
    'samplevolumeb': '0.5', 'samplevolumec': '0.5', 'samplevolumed': '0.5',
    'velocitycurve': '0.5', 'volume': '0.5',
}

# Default <multisample> attributes (v11).
_MS_DEFAULTS = {
    'attack': '0.0', 'detune': '0.5', 'endsample': '8255', 'fadeinsamples': '0.0',
    'filtercutoff': '0.0', 'filterhighpass': '1.0', 'filterkeyfollow': '0.0',
    'filtermode': '0', 'filterresonance': '0.0', 'graindensity': '0.5',
    'graindirection': '0.0', 'grainpitchspread': '0.2000000029802322',
    'grainpositionspread': '0.2000000029802322', 'grainrandomoctave': '0.0',
    'grainstereospread': '0.0', 'grainwindowtype': '0.0', 'highkey': '127', 'isromsample': '1',
    'loopenabled': '1', 'loopendsample': '8255', 'loopstartsample': '0', 'lowkey': '0',
    'mutegroup': '0', 'pan': '0.5', 'phaseinverse': '0', 'pingpongloop': '0', 'release': '0.0',
    'reverse': '0', 'rootkey': '60', 'slice': '0', 'startsample': '0', 'stereoinverse': '0',
    'stretchgrainsize': '0.5', 'stretchmode': '0', 'stretchvalue': '0.0', 'track': '1',
    'transpose': '0.5', 'url': 'Saw', 'urlRelativeToPresetDirectory': '', 'velocityend': '127',
    'velocitystart': '0', 'volume': '1.0',
}


def new_multisample() -> ET.Element:
    """A fresh <multisample> with all v11 defaults (caller overrides per zone)."""
    return ET.Element('multisample', dict(_MS_DEFAULTS))


def new_tal_root():
    """Build a complete <tal>/<programs>/<program> tree with v11 defaults: 4
    sample layers (each one default multisample), and the voicetunings/modmatrix/
    tuningtable child blocks. Returns (tal_root, program_element).

    The <programs> wrapper is required: TAL-Sampler (JUCE) resolves the program
    via tal→programs→program by name, so a <tal><program> file loads silently
    as empty."""
    tal = ET.Element('tal', {'curprogram': '0', 'version': TAL_VERSION})
    programs = ET.SubElement(tal, 'programs')
    prog = ET.SubElement(programs, 'program', dict(_PROG_DEFAULTS))
    for i in range(4):
        sl = ET.SubElement(prog, f'samplelayer{i}')
        ms_cont = ET.SubElement(sl, 'multisamples')
        ms_cont.append(new_multisample())
    vt = ET.SubElement(prog, 'voicetunings')
    for _ in range(12):
        ET.SubElement(vt, 'voicetuning',
                      {'cutoff': '0.5', 'detune': '0.5', 'attack': '0.5',
                       'decay': '0.5', 'release': '0.5'})
    mm = ET.SubElement(prog, 'modmatrix')
    for _ in range(10):
        ET.SubElement(mm, 'entry',
                      {'parameterid': '-1', 'modmatrixsourceid': '0',
                       'modmatrixamount': '0.5'})
    tt = ET.SubElement(prog, 'tuningtable')
    for _ in range(128):
        ET.SubElement(tt, 'entry', {'tuning': '0.0'})
    return tal, prog
