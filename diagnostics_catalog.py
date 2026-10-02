"""Extract the published diagnostic catalogue from the source, as JSON."""
import ast, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent
SKIP = {'tests', 'tools', 'docs', '__pycache__', '.git', 'fixtures'}

def const(n):
    return n.value if isinstance(n, ast.Constant) else None


def _expand_template(node, stages):
    """Codes a `f'AKAI_{stage}_EXTRAPOLATED'`-shaped argument stands for.

    Only the shape `'LITERAL_{name}_LITERAL'` with a single bare-name hole is
    expanded. Anything else returns [] and is skipped exactly as before — a
    general f-string evaluator here would be a new source of wrong answers in
    the one file whose whole job is to be true.
    """
    if not stages:
        return []
    parts, holes = [], []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(('lit', v.value))
        elif isinstance(v, ast.FormattedValue):
            expr = v.value
            name = expr.id if isinstance(expr, ast.Name) else None
            if name is None:
                return []          # attribute/subscript/anything computed
            holes.append(name)
        else:
            return []              # a conversion or format spec we won't model
    if len(holes) != 1:
        return []
    hole = holes[0]
    # Rebuild the literal template with one named hole, then substitute.
    template = ''
    for v in node.values:
        if isinstance(v, ast.Constant):
            template += v.value
        else:
            template += '{%s}' % hole
    return [template.replace('{%s}' % hole, s) for s in stages]


def _stage_names(trees, files):
    """Stage names passed to the envelope solver, read from the source.

    Derived rather than hard-coded so a new stage cannot be added to the writer
    without the catalogue following it — which is the failure being fixed.
    """
    names = set()
    for tree in trees:
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
                continue
            for kw in n.keywords or []:
                if kw.arg == 'stage':
                    v = const(kw.value)
                    if isinstance(v, str) and v:
                        names.add(v)
                    elif isinstance(kw.value, ast.IfExp):
                        # `stage='' if quiet else 'RELSE1'` — a IfExp is the
                        # normal way a stage is made conditional, and skipping
                        # it found the stage set EMPTY on 2026-10-02. Read
                        # both arms: the true arm is the stage, the false arm
                        # is the empty string that means "suppress".
                        for arm in (kw.value.body, kw.value.orelse):
                            a = const(arm)
                            if isinstance(a, str) and a:
                                names.add(a)
    return sorted(names)


def _add(out, code, sev, n, f):
    """Fold one `_diag(...)` call into the catalogue entry for `code`."""
    sv = n.args[0]
    entry = out.setdefault(code, {
        'code': code, 'severity': None, 'content_lost': None,
        'detail_keys': [], 'emitted_from': []})
    entry['severity'] = sev.get(getattr(sv, 'id', None), entry['severity'])
    src = str(f.relative_to(ROOT))
    if src not in entry['emitted_from']:
        entry['emitted_from'].append(src)
    for kw in n.keywords or []:
        if kw.arg == 'content_lost':
            v = const(kw.value)
            if isinstance(v, bool):
                # A code emitted from two sites with different literals
                # is as variable as a computed one.
                if entry['content_lost'] in (None, v):
                    entry['content_lost'] = v
                else:
                    entry['content_lost'] = 'varies'
            else:
                # COMPUTED, e.g. `len(voices) > _MAX_KRZ_LAYERS`. Saying
                # 'varies' is the honest catalogue entry: the value is
                # real and per-call, so a consumer must read the RECORD
                # and must not decide from this file. Null would read as
                # "undeclared", which is a different and worse claim.
                entry['content_lost'] = 'varies'
        elif kw.arg == 'detail' and isinstance(kw.value, ast.Dict):
            for k in kw.value.keys:
                kv = const(k)
                if isinstance(kv, str) and kv not in entry['detail_keys']:
                    entry['detail_keys'].append(kv)


def catalog():
    sev = {'_W': 'warning', '_I': 'info', '_E': 'error',
           'WARNING': 'warning', 'INFO': 'info', 'ERROR': 'error'}
    out = {}
    files, trees = [], []
    for f in sorted(ROOT.rglob('*.py')):
        if SKIP & set(f.relative_to(ROOT).parts):
            continue
        try:
            tree = ast.parse(f.read_text(encoding='utf-8'), filename=str(f))
        except SyntaxError:
            continue
        files.append(f)
        trees.append(tree)
    stages = _stage_names(trees, files)
    for f, tree in zip(files, trees):
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in ('_diag', 'emit')):
                continue
            if len(n.args) < 2:
                continue
            code = const(n.args[1])
            if code is None and isinstance(n.args[1], ast.JoinedStr):
                # A TEMPLATED CODE, e.g. `f'AKAI_{stage}_EXTRAPOLATED'`.
                #
                # ⚠ These were SILENTLY DROPPED until 2026-10-02, found because
                # VinSamLib reported a diagnostic we could not find in
                # docs/diagnostics.json: AKAI_RELSE1_EXTRAPOLATED, which the
                # writer really does emit. `const()` returns None for an
                # ast.JoinedStr, and `None` was read as "not a code", so seven
                # real codes were absent from a file that exists to be a
                # contract. A consumer asserting against the catalogue — which
                # is what VinSamLib does — could not see them, and had no way
                # to learn they existed except by reading our source.
                #
                # `AKAI_ATTACK_CEILING` and friends are literal and were always
                # fine, so the catalogue looked complete.
                for _code in _expand_template(n.args[1], stages):
                    _add(out, _code, sev, n, f)
                continue
            if not isinstance(code, str):
                continue
            _add(out, code, sev, n, f)
    for e in out.values():
        e['detail_keys'].sort()
        e['emitted_from'].sort()
    return {'schema': 1,
            'note': ('Generated from the source by diagnostics_catalog.py. '
                     'Consumers key on `code` and `detail_keys`; both are part '
                     'of the contract and are not changed silently.'),
            'codes': [out[k] for k in sorted(out)]}

if __name__ == '__main__':
    print(json.dumps(catalog(), indent=2))
