"""Extract the published diagnostic catalogue from the source, as JSON."""
import ast, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent
SKIP = {'tests', 'tools', 'docs', '__pycache__', '.git', 'fixtures'}

def const(n):
    return n.value if isinstance(n, ast.Constant) else None

def catalog():
    sev = {'_W': 'warning', '_I': 'info', '_E': 'error',
           'WARNING': 'warning', 'INFO': 'info', 'ERROR': 'error'}
    out = {}
    for f in sorted(ROOT.rglob('*.py')):
        if SKIP & set(f.relative_to(ROOT).parts):
            continue
        try:
            tree = ast.parse(f.read_text(encoding='utf-8'), filename=str(f))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in ('_diag', 'emit')):
                continue
            if len(n.args) < 2:
                continue
            code = const(n.args[1])
            if not isinstance(code, str):
                continue
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
