#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright (C) 2025-2026  mpc2emu contributors
#
# Written by the k2kremote project (~/git-repos/k2kremote) and contributed here
# because it is what produces docs/K2000_ALGORITHMS.md and
# docs/re_procedures/k2000_algorithms.json from the Kurzweil Reference Guide.
# Kept so the table can be regenerated rather than trusted.

"""Parse chapter 26 (DSP Algorithms) of the K2000 Reference Guide into JSON.

Source: "26 DSP Algs.pdf" -> pdftotext -layout. Two algorithms per row of the
page, so the split column is taken from the second "Algorithm|N" header.
"""
import json, re, sys

lines = open('26_dsp_algs.txt', encoding='utf-8').read().split('\n')
hdr = re.compile(r'Algorithm\|(\d+)')

blocks = []          # (algno, col_start, col_end, first_line, last_line)
starts = []
for i, ln in enumerate(lines):
    ms = list(hdr.finditer(ln))
    if ms:
        starts.append((i, [(int(m.group(1)), m.start()) for m in ms]))

for k, (i, algs) in enumerate(starts):
    end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
    for j, (no, col) in enumerate(algs):
        c0 = col
        c1 = algs[j + 1][1] if j + 1 < len(algs) else 10_000
        blocks.append((no, c0, c1, i, end))

out = {}
for no, c0, c1, i, end in blocks:
    chunk = [ln[c0:c1].rstrip() if len(ln) > c0 else '' for ln in lines[i:end]]
    glyphs = [c for c in chunk[1:5]]
    body = [c for c in chunk[5:] if c.strip()
            and not re.match(r'^\s*26-\d+\s*$', c)
            and 'DSP Algorithms' not in c]
    if not body:
        continue
    chain_line = body[0]
    # block labels: 2+ spaces separate them, but "x AMP" / "SHAPE MOD OSC" keep
    # their internal single spaces
    cols = [(m.start(), m.group().strip())
            for m in re.finditer(r'\S+(?: \S+)*', chain_line)]
    names, bounds = [], []
    for n, (pos, txt) in enumerate(cols):
        names.append(txt)
        bounds.append((pos, cols[n + 1][0] if n + 1 < len(cols) else 10_000))
    # keyed by POSITION, not by name: algorithms 8-15 carry two blocks both
    # labelled LOPASS and a name-keyed dict silently merges their function lists
    funcs = [[] for _ in names]
    for ln in body[1:]:
        for n, (a, b) in enumerate(bounds):
            cell = ln[a:b].strip() if len(ln) > a else ''
            if cell:
                funcs[n].append(cell)

    # Stage widths, derived from the diagram's input-arrow row: five 8-char
    # stage cells, and a cell whose separator is 'r' means the block continues
    # into the next stage. DERIVED, NOT VERIFIED ON THE DEVICE.
    arrows = glyphs[1] if len(glyphs) > 1 else ''
    pad = len(arrows) - len(arrows.lstrip('|'))
    cells = [arrows[pad + 8 * k:pad + 8 * (k + 1)] for k in range(5)]
    widths, seps = [], []
    for c in cells:
        if len(c) < 8:
            break
        if widths and c[7] != 't' and seps and seps[-1] == 'r':
            pass
        if widths and seps and seps[-1] == 'r':
            widths[-1] += 1
        else:
            widths.append(1)
        seps.append(c[7])

    n_stages = 5 if no <= 25 else 4
    consistent = (len(widths) == len(names) and sum(widths) == n_stages)

    out[no] = {'chain': names,
               'stage_widths_consistent': consistent,
               'functions': [{'block': nm, 'choices': f}
                             for nm, f in zip(names, funcs)],
               'stage_widths_derived': widths,
               'stage_separators': ''.join(seps),
               'diagram': glyphs}

print(f'parsed {len(out)} algorithms: {sorted(out)}', file=sys.stderr)
with open('k2000_algorithms.json', 'w', encoding='utf-8') as _fh:
    json.dump(out, _fh, indent=1)
