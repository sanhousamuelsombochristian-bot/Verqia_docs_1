"""Porte de fermeture de la couche Application : chaque invariant AP a une PREUVE identifiable, et une mutation capable de la casser.

  python architecture_registry/verify_ap.py                 structure : chaque AP a sa preuve, chaque référence se résout, aucune preuve orpheline
  python architecture_registry/verify_ap.py --run           + exécute les tests et les injections référencés : chaque AP est PASS ou FAIL
  python architecture_registry/verify_ap.py --mutate        + exécute les mutations de code : chacune doit être TUÉE (un motif introuvable est une erreur)
  python architecture_registry/verify_ap.py --doc           réécrit APPLICATION_PROOFS_V1.md ; `--check-doc` compare

Sortie : le tableau AP × (statique, tests, mutations, état) et `AP_COUNT / PROVEN_AP / UNTESTED_AP`. Code de sortie 1 s'il existe une erreur.
Un AP ajouté au catalogue sans preuve fait échouer la porte : la couverture n'est pas « il existe un test quelque part ».
"""
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

import ap_catalogue  # noqa: E402
import ap_mutations  # noqa: E402
import ap_proofs  # noqa: E402
import gen_contracts as G  # noqa: E402

REAL_APP = G.DEFAULT_OUT
DOC = os.path.abspath(os.path.join(HERE, '..', 'APPLICATION_PROOFS_V1.md'))
HELPER = os.path.join(HERE, 'ap_run_tests.py')
SUITE_CWD = {'reg': HERE, 'run': REAL_APP}
STATIC_CODES = None


def static_codes():
    """Les propriétés que `verify_application.py` déclare dans son en-tête (A1 à A13, H, H2)."""
    global STATIC_CODES
    if STATIC_CODES is None:
        with io.open(os.path.join(HERE, 'verify_application.py'), encoding='utf-8') as f:
            head = f.read().split('"""')[1]
        STATIC_CODES = set(re.findall(r'^  (A\d+|H2?)\s', head, re.M))
    return STATIC_CODES


def split(ref):
    suite, _, ident = ref.partition(':')
    return suite, ident


def helper(suite, mode, ids):
    """Exécute `ap_run_tests.py` dans un processus isolé (le répertoire courant fixe la suite) ; les identifiants passent par un fichier."""
    fd, path = tempfile.mkstemp(suffix='.txt')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ids))
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        proc = subprocess.run([sys.executable, HELPER, mode, '@' + path], cwd=SUITE_CWD[suite], capture_output=True, text=True, encoding='utf-8', env=env)
    finally:
        os.remove(path)
    last = [ln for ln in proc.stdout.strip().split('\n') if ln.strip()][-1:] or ['{}']
    try:
        return json.loads(last[0])
    except ValueError:
        raise RuntimeError('sortie illisible du processus de tests (%s) : %s' % (suite, (proc.stderr or proc.stdout)[-400:]))


def refs_of(proof):
    """(tests, injections, mutations de code) d'un AP."""
    inject = [m[len('inject:'):] for m in proof.get('mutations', ()) if m.startswith('inject:')]
    code = [m[len('code:'):] for m in proof.get('mutations', ()) if m.startswith('code:')]
    other = [m for m in proof.get('mutations', ()) if not m.startswith(('inject:', 'code:'))]
    return list(proof.get('tests', ())), inject, code, other


def check(catalogue=None, proofs=None, mutations=None, resolve=True):
    """Structure de la preuve. Retourne (erreurs, détail par AP) : `detail[ap]` = {'tests': [...feuilles], 'inject': [...], 'code': [...], 'errors': [...]}."""
    catalogue = ap_catalogue.INVARIANTS if catalogue is None else catalogue
    proofs = ap_proofs.PROOFS if proofs is None else proofs
    mutations = ap_mutations.MUTATIONS if mutations is None else mutations
    ids = [a for a, _, _ in catalogue]
    known = {m.id: m for m in mutations}
    detail = {ap: {'tests': [], 'inject': [], 'code': [], 'errors': []} for ap in ids}
    errors = []

    def fail(ap, message):
        errors.append('%s : %s' % (ap, message))
        if ap in detail:
            detail[ap]['errors'].append(message)

    if len(ids) != len(set(ids)):
        errors.append('catalogue : identifiants dupliqués')
    for ap in ids:
        if ap not in proofs:
            fail(ap, 'aucune preuve : invariant NON PROUVÉ (ajouter sa preuve à `ap_proofs.py`)')
    for ap in proofs:
        if ap not in ids:
            errors.append('%s : preuve ORPHELINE (aucun invariant de ce nom dans le catalogue)' % ap)
    codes = static_codes()
    referenced_mutations = set()
    to_resolve = {'reg': set(), 'run': set()}
    for ap in ids:
        proof = proofs.get(ap)
        if proof is None:
            continue
        if not proof.get('static'):
            fail(ap, "aucune vérification statique référencée")
        for c in proof.get('static', ()):
            if c not in codes:
                fail(ap, "propriété statique inconnue `%s` (connues : %s)" % (c, ', '.join(sorted(codes))))
        tests, inject, code, other = refs_of(proof)
        if not tests:
            fail(ap, 'aucun test : invariant SANS TEST')
        if not (inject or code):
            fail(ap, 'aucune mutation : la preuve n\'est pas démontrée capable d\'échouer')
        for o in other:
            fail(ap, 'mutation de forme inconnue `%s` (attendu `inject:` ou `code:`)' % o)
        for t in tests + inject:
            suite, ident = split(t)
            if suite not in to_resolve:
                fail(ap, 'suite inconnue dans `%s`' % t)
            else:
                to_resolve[suite].add(ident)
        for m in code:
            referenced_mutations.add(m)
            if m not in known:
                fail(ap, 'mutation de code `%s` inexistante' % m)
    for m in mutations:
        if m.id not in referenced_mutations:
            errors.append('%s : mutation ORPHELINE (aucun AP ne la référence)' % m.id)
        elif ('code:' + m.id) not in proofs.get(m.ap, {}).get('mutations', ()):
            errors.append('%s : la mutation n\'est pas référencée par son propre AP (%s)' % (m.id, m.ap))
    if resolve:
        resolved = {}
        for suite, idents in to_resolve.items():
            if idents:
                out = helper(suite, 'list', sorted(idents))
                for ident, message in out.get('errors', {}).items():
                    resolved[(suite, ident)] = message
                for ident, leaves in out.get('ids', {}).items():
                    resolved[(suite, ident)] = leaves
        for ap in ids:
            proof = proofs.get(ap)
            if proof is None:
                continue
            tests, inject, _, _ = refs_of(proof)
            for kind, refs in (('tests', tests), ('inject', inject)):
                for t in refs:
                    suite, ident = split(t)
                    got = resolved.get((suite, ident))
                    if got is None or isinstance(got, str):
                        fail(ap, 'référence introuvable `%s` : %s' % (t, got or 'non résolue'))
                    else:
                        detail[ap][kind].extend('%s:%s' % (suite, leaf) for leaf in got)
            detail[ap]['code'] = [m for m in refs_of(proof)[2]]
    return errors, detail


# ---------------------------------------------------------------------------------------------- exécution
def run_all(detail):
    """Exécute chaque test et chaque injection référencés ; retourne {ap: {'ok': n, 'ko': [feuilles]}}."""
    leaves = {'reg': set(), 'run': set()}
    for d in detail.values():
        for full in d['tests'] + d['inject']:
            suite, leaf = split(full)
            leaves[suite].add(leaf)
    outcome = {}
    for suite, ids in leaves.items():
        if ids:
            for leaf, status in helper(suite, 'run', sorted(ids)).items():
                outcome[(suite, leaf)] = status
    state = {}
    for ap, d in detail.items():
        mine = d['tests'] + d['inject']
        bad = [f for f in mine if outcome.get(split(f)) != 'ok']
        state[ap] = {'ok': len(mine) - len(bad), 'ko': bad}
    return state


def apply_mutation(m, root):
    for rel, old, new, count in m.edits:
        path = os.path.join(root, rel.replace('/', os.sep))
        with io.open(path, encoding='utf-8') as f:              # fins de ligne normalisées : un motif multi-lignes se trouve aussi dans un fichier CRLF
            text = f.read()
        if text.count(old) != count:
            return 'motif introuvable dans %s (attendu %d occurrence(s), trouvé %d)' % (rel, count, text.count(old))
        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(text.replace(old, new))
    return None


def run_mutation(m, app_root=None):
    """Retourne ('killed' | 'survived' | 'invalid', détail)."""
    app_root = app_root or REAL_APP
    tmp = tempfile.mkdtemp(prefix='verqia_mut_')
    try:
        for d in ('verqia', 'application_runner'):
            shutil.copytree(os.path.join(app_root, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns('__pycache__'))
        problem = apply_mutation(m, tmp)
        if problem:
            return 'invalid', problem
        env = dict(os.environ, PYTHONPATH=tmp, PYTHONIOENCODING='utf-8')
        proc = subprocess.run([sys.executable, '-m', 'unittest', *m.kill], cwd=tmp, capture_output=True, text=True, encoding='utf-8', env=env)
        out = proc.stdout + proc.stderr
        if proc.returncode == 0:
            return 'survived', 'les tests désignés passent malgré la mutation'
        if re.search(r'Ran 0 tests|Failed to import test module|SyntaxError|ModuleNotFoundError', out):
            return 'invalid', 'la mutation casse le chargement, elle ne démontre rien : %s' % out[-200:].replace('\n', ' ')
        m2 = re.search(r'FAILED \((.*?)\)', out)
        return 'killed', m2.group(1) if m2 else 'échec'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def baseline_of_kills(mutations):
    """Les tests désignés PASSENT sans mutation (sinon « tué » ne voudrait rien dire)."""
    ids = sorted({k for m in mutations for k in m.kill})
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    proc = subprocess.run([sys.executable, '-m', 'unittest', *ids], cwd=REAL_APP, capture_output=True, text=True, encoding='utf-8', env=env)
    return proc.returncode == 0, (proc.stderr or proc.stdout)[-300:]


# ---------------------------------------------------------------------------------------------- rapport
def render_doc(detail):
    cat = {a: (t, v) for a, t, v in ap_catalogue.INVARIANTS}
    w = []
    a = w.append
    a('# VERQIA : Application Proofs V1')
    a('')
    a('> Généré par `architecture_registry/verify_ap.py --doc` depuis `ap_catalogue.py` (les invariants), `ap_proofs.py` (les preuves) et `ap_mutations.py` (les mutations de code). Ne pas modifier à la main.')
    a('> **Porte de fermeture de la couche Application** : `verify_ap.py --run --mutate` exécute chaque preuve et tue chaque mutation.')
    a('')
    a('Un invariant n\'est pas couvert parce qu\'un test existe quelque part : il l\'est quand **(1)** une vérification statique le contrôle, **(2)** des tests le démontrent, **(3)** une mutation sait '
      'le casser et **(4)** chaque référence se résout, chaque test passe et chaque mutation est tuée. Un AP ajouté au catalogue sans sa preuve fait échouer la porte.')
    a('')
    a('| Invariant | Statique | Tests | Injections de données | Mutations de code | Exécution |')
    a('|---|---|---:|---:|---:|---|')
    for ap, _, _ in ap_catalogue.INVARIANTS:
        d = detail[ap]
        a('| %s | %s | %d | %d | %d | `verify_ap.py --run --mutate` |' % (ap, ', '.join(ap_proofs.PROOFS[ap]['static']), len(d['tests']), len(d['inject']), len(d['code'])))
    a('')
    n = len(ap_catalogue.INVARIANTS)
    proven = sum(1 for ap in detail if not detail[ap]['errors'])
    a('```text')
    a('AP_COUNT    = %d' % n)
    a('PROVEN_AP   = %d' % proven)
    a('UNTESTED_AP = %d' % sum(1 for ap in detail if not detail[ap]['tests']))
    a('```')
    a('')
    a('Les deux colonnes de mutations sont de nature différente : une **injection de données** corrompt les spécifications générées et exige que la vérification statique échoue ; '
      'une **mutation de code** retire une garde du coureur ou d\'un double et exige que les tests désignés échouent. Une mutation dont le motif est introuvable est une erreur de la porte, jamais un succès.')
    a('')
    for ap, text, verified in ap_catalogue.INVARIANTS:
        d = detail[ap]
        proof = ap_proofs.PROOFS[ap]
        a('## %s' % ap)
        a('')
        a(text)
        a('')
        a('- **Statique** : %s' % ', '.join('`%s`' % c for c in proof['static']))
        a('- **Tests** (%d) : %s' % (len(d['tests']), '; '.join('`%s`' % t for t in proof['tests'])))
        inject = [m[len('inject:'):] for m in proof['mutations'] if m.startswith('inject:')]
        a('- **Injections de données** (%d tests) : %s' % (len(d['inject']), '; '.join('`%s`' % t for t in inject) or '—'))
        code = [m for m in d['code']]
        a('- **Mutations de code** (%d) : %s' % (len(code), '; '.join('`%s`' % m for m in code) or '—'))
        a('')
    return '\n'.join(w) + '\n'


def main():
    args = sys.argv[1:]
    errors, detail = check()
    state = None
    if '--run' in args:
        state = run_all(detail)
        for ap, s in state.items():
            if s['ko']:
                errors.append('%s : %d test(s) en échec : %s' % (ap, len(s['ko']), ', '.join(s['ko'][:3])))
    mutation_results = {}
    if '--mutate' in args:
        ok, tail = baseline_of_kills(ap_mutations.MUTATIONS)
        if not ok:
            errors.append('mutations : les tests désignés échouent SANS mutation : %s' % tail)
        else:
            for m in ap_mutations.MUTATIONS:
                status, note = run_mutation(m)
                mutation_results[m.id] = (status, note)
                if status != 'killed':
                    errors.append('%s : mutation %s (%s)' % (m.id, status.upper(), note))
    if '--doc' in args:
        with io.open(DOC, 'w', encoding='utf-8', newline='') as f:
            f.write(render_doc(detail))
        print('écrit :', DOC)
    if '--check-doc' in args:
        with io.open(DOC, encoding='utf-8', newline='') as f:
            if f.read() != render_doc(detail):
                errors.append('APPLICATION_PROOFS_V1.md diffère du générateur')
    print('| Invariant | Statique | Tests | Injections | Mutations de code | État |')
    print('|---|---|---:|---:|---:|---|')
    for ap, _, _ in ap_catalogue.INVARIANTS:
        d = detail[ap]
        killed = sum(1 for m in d['code'] if mutation_results.get(m, ('', ''))[0] == 'killed')
        if d['errors']:
            etat = 'NON PROUVÉ'
        elif state is not None and state[ap]['ko']:
            etat = 'FAIL'
        elif state is not None:
            etat = 'PASS' + (' (%d/%d mutations tuées)' % (killed, len(d['code'])) if mutation_results else '')
        else:
            etat = 'référencé'
        print('| %s | %s | %d | %d | %d | %s |' % (ap, ', '.join(ap_proofs.PROOFS.get(ap, {}).get('static', ())), len(d['tests']), len(d['inject']), len(d['code']), etat))
    proven = sum(1 for ap, d in detail.items() if not d['errors'] and (state is None or not state[ap]['ko']))
    print('AP_COUNT = %d · PROVEN_AP = %d · UNTESTED_AP = %d' % (len(detail), proven, sum(1 for d in detail.values() if not d['tests'])))
    if mutation_results:
        print('mutations : %d exécutées · %d tuées' % (len(mutation_results), sum(1 for s, _ in mutation_results.values() if s == 'killed')))
    print('erreurs : %d' % len(errors))
    for e in errors:
        print('  -', e)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
