"""Porte de fermeture du Priority Domain V1 : chaque invariant (`priority_catalogue.py`, PD1-PD11 + DV3 + PI17-PI20)
a une PREUVE identifiable, et une mutation capable de la casser.

  python architecture_registry/verify_priority_domain.py                 structure : chaque invariant a sa preuve, chaque référence se résout, règles statiques P-R1/P-R2
  python architecture_registry/verify_priority_domain.py --run           + exécute les tests désignés : chaque invariant est PASS ou FAIL
  python architecture_registry/verify_priority_domain.py --mutate        + exécute les mutations de code : chacune doit être TUÉE (un motif introuvable est une erreur)
  python architecture_registry/verify_priority_domain.py --doc           réécrit PRIORITY_DOMAIN_PROOFS_V1.md ; `--check-doc` compare

Sortie : le tableau invariant × (statique, tests, mutations, état) et `PRIORITY_DOMAIN_COUNT / PROVEN / UNTESTED`.
Code de sortie 1 s'il existe une erreur. Vérifie AUSSI que les DEUX empreintes déjà posées (`domain_freeze.json`
tranche 1, `risk_domain_freeze.json`) restent intactes : le Priority Domain n'est pas encore gelé lui-même, mais
rien de ce travail ne doit rouvrir la tranche 1 ni le Risk Domain.
"""
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DOCS = os.path.abspath(os.path.join(HERE, '..'))
APP = os.path.abspath(os.path.join(DOCS, '..', 'verqia-app'))
REFERENCE = os.path.join(DOCS, 'reference_model')
DOC = os.path.join(DOCS, 'PRIORITY_DOMAIN_PROOFS_V1.md')

import priority_catalogue as CAT  # noqa: E402
import priority_mutations as MUT  # noqa: E402
import priority_proofs as PRF  # noqa: E402

STATIC_RULES = {'P-R1': "imports : bibliothèque standard, noyau, `priority` (propre module) et `contracts` des autres seulement (AR-01-équivalent, DR2)",
                'P-R2': 'aucune horloge, aucun aléa, aucun flottant, aucune entrée-sortie (AR-02-équivalent)'}
DOMAIN_DIR = os.path.join(APP, 'verqia', 'priority', 'domain')


def domain_files():
    return sorted(os.path.join(DOMAIN_DIR, f) for f in os.listdir(DOMAIN_DIR) if f.endswith('.py'))


def read(path):
    with io.open(path, encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------------------------------------- règles statiques
def static_errors():
    errors = []
    stdlib = {'__future__', 'dataclasses', 'datetime', 'typing', 'collections', 'uuid', 'zoneinfo', 'itertools'}
    for path in domain_files():
        rel = os.path.relpath(path, APP).replace(os.sep, '/')
        text = read(path)
        tree = ast.parse(text)
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for name in names:
                top = name.split('.')[0]
                if top != 'verqia':
                    if top not in stdlib:
                        errors.append('P-R1 %s : import hors bibliothèque standard : %s' % (rel, name))
                    continue
                parts = name.split('.')
                if parts[1] != 'kernel' and parts[1] != 'priority' and (len(parts) < 3 or parts[2] != 'contracts'):
                    errors.append("P-R1 %s : import d'un autre module que `contracts` : %s" % (rel, name))
            if isinstance(node, ast.Attribute) and node.attr in ('now', 'today', 'utcnow', 'time', 'monotonic', 'urandom', 'uuid1', 'uuid4', 'random', 'getenv', 'system'):
                errors.append('P-R2 %s:%d : source de temps ou d\'aléa : .%s' % (rel, node.lineno, node.attr))
            if isinstance(node, ast.Name) and node.id in ('open', 'print', 'input', 'random', 'time'):
                errors.append('P-R2 %s:%d : entrée-sortie ou aléa : %s' % (rel, node.lineno, node.id))
            if (isinstance(node, ast.Constant) and isinstance(node.value, float)) or (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)) or (isinstance(node, ast.Name) and node.id == 'float'):
                errors.append('P-R2 %s:%d : flottant ou division réelle' % (rel, getattr(node, 'lineno', 0)))
    return errors


# ---------------------------------------------------------------------------------------------- structure et résolution
def helper(mode, ids, cwd=APP, env_extra=None):
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write('\n'.join(ids))
        path = f.name
    try:
        env = dict(os.environ, PYTHONIOENCODING='utf-8', VERQIA_REFERENCE=REFERENCE, **(env_extra or {}))
        proc = subprocess.run([sys.executable, os.path.join(HERE, 'ap_run_tests.py'), mode, '@' + path], cwd=cwd, capture_output=True, text=True, encoding='utf-8', env=env)
        return json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {'errors': {'*': proc.stderr[-300:]}}
    finally:
        os.unlink(path)


def structure(resolve=True):
    errors, detail = [], {}
    ids = [i[0] for i in CAT.INVARIANTS]
    if len(set(ids)) != len(ids):
        errors.append('catalogue : identifiants dupliqués')
    mut_ids = {m.id for m in MUT.MUTATIONS}
    for inv in ids:
        proof = PRF.PROOFS.get(inv)
        if proof is None:
            errors.append('%s : AUCUNE PREUVE (invariant non démontré)' % inv)
            continue
        if not proof['tests']:
            errors.append('%s : aucun test désigné' % inv)
        if not proof['mutations']:
            errors.append('%s : aucune mutation désignée' % inv)
        for m in proof['mutations']:
            if m not in mut_ids:
                errors.append('%s : mutation inconnue %s' % (inv, m))
        for r in proof['static']:
            if r not in STATIC_RULES:
                errors.append('%s : règle statique inconnue %s' % (inv, r))
        detail[inv] = proof
    for inv in PRF.PROOFS:
        if inv not in ids:
            errors.append('preuve orpheline : %s n\'est pas au catalogue' % inv)
    used = {m for p in PRF.PROOFS.values() for m in p['mutations']}
    for m in mut_ids - used:
        errors.append('mutation orpheline : %s ne prouve aucun invariant' % m)
    if resolve:
        tests = sorted({t for p in PRF.PROOFS.values() for t in p['tests']} | {k for m in MUT.MUTATIONS for k in m.kill})
        out = helper('list', tests)
        for t, why in out.get('errors', {}).items():
            errors.append('référence de test introuvable : %s (%s)' % (t, why))
    errors += static_errors()
    return errors, detail


def run_all():
    tests = sorted({t for p in PRF.PROOFS.values() for t in p['tests']})
    leaves = helper('list', tests)['ids']
    flat = sorted({leaf for v in leaves.values() for leaf in v})
    outcomes = helper('run', flat)
    state = {}
    for inv, proof in PRF.PROOFS.items():
        mine = [leaf for t in proof['tests'] for leaf in leaves.get(t, [])]
        bad = [leaf for leaf in mine if outcomes.get(leaf) != 'ok']
        state[inv] = {'ok': len(mine) - len(bad), 'ko': bad}
    return state


# ---------------------------------------------------------------------------------------------- mutations
def apply_mutation(m, root):
    for rel, old, new, count in m.edits:
        path = os.path.join(root, rel.replace('/', os.sep))
        text = read(path)
        if text.count(old) != count:
            return 'motif introuvable dans %s (attendu %d occurrence(s), trouvé %d)' % (rel, count, text.count(old))
        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(text.replace(old, new))
    return None


def run_mutation(m):
    tmp = tempfile.mkdtemp(prefix='verqia_priomut_')
    try:
        for d in ('verqia', 'application_runner', 'domain_tests'):
            shutil.copytree(os.path.join(APP, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns('__pycache__'))
        problem = apply_mutation(m, tmp)
        if problem:
            return 'invalid', problem
        env = dict(os.environ, PYTHONPATH=tmp, PYTHONIOENCODING='utf-8', VERQIA_REFERENCE=REFERENCE)
        proc = subprocess.run([sys.executable, '-m', 'unittest', *m.kill], cwd=tmp, capture_output=True, text=True, encoding='utf-8', env=env)
        out = proc.stdout + proc.stderr
        if proc.returncode == 0:
            return 'survived', 'les tests désignés passent malgré la mutation'
        if re.search(r'Ran 0 tests|Failed to import test module|SyntaxError|ModuleNotFoundError', out):
            return 'invalid', 'la mutation casse le chargement, elle ne démontre rien : %s' % out[-200:].replace('\n', ' ')
        found = re.search(r'FAILED \((.*?)\)', out)
        return 'killed', found.group(1) if found else 'échec'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def baseline_of_kills():
    """Les tests désignés PASSENT sans mutation (sinon « tué » ne voudrait rien dire)."""
    ids = sorted({k for m in MUT.MUTATIONS for k in m.kill})
    env = dict(os.environ, PYTHONIOENCODING='utf-8', VERQIA_REFERENCE=REFERENCE)
    proc = subprocess.run([sys.executable, '-m', 'unittest', *ids], cwd=APP, capture_output=True, text=True, encoding='utf-8', env=env)
    return proc.returncode == 0, (proc.stderr or proc.stdout)[-300:]


# ---------------------------------------------------------------------------------------------- rapport
def render(detail, run_state=None, mutation_state=None):
    lines = ['| Invariant | Nature | Statique | Tests | Mutations | État |', '|---|---|---|---|---|---|']
    proven = 0
    for inv, statement, nature, source in CAT.INVARIANTS:
        p = detail.get(inv)
        if p is None:
            lines.append('| %s | %s | — | 0 | 0 | **NON PROUVÉ** |' % (inv, nature))
            continue
        state = 'référencé'
        ok = True
        if run_state is not None:
            r = run_state[inv]
            ok = not r['ko'] and r['ok'] > 0
            state = 'PASS' if ok else 'FAIL (%d)' % len(r['ko'])
        if mutation_state is not None:
            mine = [mutation_state.get(m) for m in p['mutations']]
            killed = sum(1 for s in mine if s and s[0] == 'killed')
            ok = ok and killed == len(mine)
            state += ' (%d/%d mutations tuées)' % (killed, len(mine)) if run_state is not None else ' (%d/%d)' % (killed, len(mine))
        proven += bool(ok and (run_state is not None or mutation_state is not None))
        lines.append('| %s | %s | %s | %d | %d | %s |' % (inv, nature, ', '.join(p['static']) or '—', len(p['tests']), len(p['mutations']), state))
    return lines, proven


def render_doc(detail):
    out = ['# VERQIA — Preuves des invariants du Priority Domain V1 (généré)', '',
           'Généré par `architecture_registry/verify_priority_domain.py --doc` à partir de `priority_catalogue.py`, `priority_proofs.py` et `priority_mutations.py`. Ne pas modifier à la main.', '',
           'Chaque invariant (`PRIORITY_DOMAIN_V1.md`, PD1-PD11 + DV3, + PI17-PI20 d\'infrastructure) a : une règle statique éventuelle, des tests qui le démontrent et des mutations de code qui savent le casser.',
           'Un invariant n\'est **prouvé** que si ses tests passent et si chacune de ses mutations est **tuée** (`--run --mutate`).', '',
           'Règles statiques : ' + ' · '.join('**%s** %s' % (k, v) for k, v in STATIC_RULES.items()), '',
           '## Invariants', '', '| # | Invariant | Nature | Source | Tests | Mutations |', '|---|---|---|---|---|---|']
    for inv, statement, nature, source in CAT.INVARIANTS:
        p = detail[inv]
        out.append('| %s | %s | %s | %s | %d | %s |' % (inv, statement, nature, source, len(p['tests']), ', '.join('`%s`' % m for m in p['mutations'])))
    out += ['', '## Mutations', '', '| Mutation | Fichiers | Tests qui doivent tomber |', '|---|---|---|']
    for m in MUT.MUTATIONS:
        out.append('| `%s` | %s | %d |' % (m.id, ', '.join(sorted({e[0].split('/')[-1] for e in m.edits})), len(m.kill)))
    out += ['', '`PRIORITY_DOMAIN_COUNT = %d` invariants · `MUTATIONS = %d`.' % (len(CAT.INVARIANTS), len(MUT.MUTATIONS)), '']
    return '\n'.join(out) + '\n'


def main():
    args = sys.argv[1:]
    errors, detail = structure()
    import domain_freeze                                                # la tranche 1 doit rester intacte pendant tout ce travail
    errors += domain_freeze.check_freeze()
    import risk_domain_freeze                                           # le Risk Domain, déjà gelé, doit lui aussi rester intact
    errors += risk_domain_freeze.check_freeze()
    import priority_domain_freeze                                       # le Priority Domain a sa PROPRE empreinte, distincte des deux précédentes
    errors += priority_domain_freeze.check_freeze()
    run_state = mutation_state = None
    if '--run' in args or '--mutate' in args:
        run_state = run_all() if '--run' in args else None
        for inv, r in (run_state or {}).items():
            if r['ko']:
                errors.append('%s : %d test(s) désigné(s) échouent : %s' % (inv, len(r['ko']), r['ko'][:2]))
    if '--mutate' in args:
        ok, tail = baseline_of_kills()
        if not ok:
            errors.append('les tests désignés par les mutations n\'ont pas une base verte : %s' % tail)
        mutation_state = {}
        for m in MUT.MUTATIONS:
            mutation_state[m.id] = run_mutation(m)
            if mutation_state[m.id][0] != 'killed':
                errors.append('mutation %s : %s (%s)' % (m.id, mutation_state[m.id][0], mutation_state[m.id][1]))
    if '--doc' in args:
        with io.open(DOC, 'w', encoding='utf-8', newline='\n') as f:
            f.write(render_doc(detail))
        print('écrit :', DOC)
    if '--check-doc' in args:
        cur = read(DOC).replace('\r\n', '\n') if os.path.exists(DOC) else ''
        if cur != render_doc(detail):
            errors.append('PRIORITY_DOMAIN_PROOFS_V1.md n\'est pas à jour : relancer --doc')
    lines, proven = render(detail, run_state, mutation_state)
    print('\n'.join(lines))
    print('PRIORITY_DOMAIN_COUNT = %d · PROVEN = %d · UNTESTED = %d' % (len(CAT.INVARIANTS), proven if (run_state is not None or mutation_state is not None) else len(detail),
                                                                        len(CAT.INVARIANTS) - (proven if (run_state is not None or mutation_state is not None) else len(detail))))
    if mutation_state is not None:
        print('mutations : %d exécutées · %d tuées' % (len(mutation_state), sum(1 for s in mutation_state.values() if s[0] == 'killed')))
    print('erreurs : %d' % len(errors))
    for e in errors:
        print('  -', e)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
