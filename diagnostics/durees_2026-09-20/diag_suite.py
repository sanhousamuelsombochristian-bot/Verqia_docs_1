"""Mesure par test de la suite `architecture_registry` SANS la modifier : enveloppes posées de l'extérieur.

Pour chaque test : durée murale (perf_counter ET horloge système), temps CPU du processus, et temps passé dans les frontières coûteuses (outermost-only) :
copytree (copie du dépôt), subprocess.run (processus fils), génération/vérification (generate, verify, registry run, render).
Usage : python diag_suite.py SORTIE.json   (répertoire courant : architecture_registry)
"""
import json
import os
import shutil
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.getcwd())
MODULES = ['test_registry', 'test_contracts', 'test_application', 'test_ap_gaps', 'test_ap_gate', 'test_runner_architecture', 'test_pg_locks']
MODULES = os.environ.get('DIAG_MODULES', ','.join(MODULES)).split(',')

ACC = {}          # accumulateurs du test courant
DEPTH = {}


def wrap(owner, name, key):
    original = getattr(owner, name)

    def wrapper(*a, **k):
        DEPTH[key] = DEPTH.get(key, 0) + 1
        t = time.perf_counter()
        try:
            return original(*a, **k)
        finally:
            DEPTH[key] -= 1
            if DEPTH[key] == 0:
                ACC[key + '_s'] = ACC.get(key + '_s', 0.0) + (time.perf_counter() - t)
                ACC[key + '_n'] = ACC.get(key + '_n', 0) + 1
    wrapper.__wrapped__ = original
    setattr(owner, name, wrapper)


import build_registry  # noqa: E402
import gen_application_doc  # noqa: E402
import gen_contracts  # noqa: E402
import verify_application  # noqa: E402
import verify_contracts  # noqa: E402

wrap(shutil, 'copytree', 'copytree')
wrap(subprocess, 'run', 'subprocess')
wrap(gen_contracts, 'generate', 'gen')
wrap(build_registry, 'run', 'reg')
wrap(verify_application, 'verify', 'verify')
wrap(verify_contracts, 'verify', 'verify')
wrap(gen_application_doc, 'render', 'gen')


class Timed(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.rows = []

    def startTest(self, test):
        super().startTest(test)
        ACC.clear()
        DEPTH.clear()
        self._t = time.perf_counter()
        self._w = time.time()
        self._c = time.process_time()

    def stopTest(self, test):
        super().stopTest(test)
        row = {'id': test.id(), 'wall': time.perf_counter() - self._t, 'wall_clock': time.time() - self._w, 'cpu': time.process_time() - self._c}
        row.update({k: v for k, v in ACC.items()})
        self.rows.append(row)


def category(row):
    tid = row['id']
    if '.test_pg_locks.' in tid or tid.startswith('test_pg_locks.'):
        return 'postgresql'
    if 'TestTheMutationEngine' in tid:
        return 'mutation'
    if row.get('copytree_n', 0):
        return 'injection'
    if row.get('subprocess_s', 0) > 0.5 * row['wall']:
        return 'sous-processus (résolution, gate)'
    if row.get('verify_s', 0) + row.get('gen_s', 0) + row.get('reg_s', 0) > 0.4 * row['wall']:
        return 'génération/vérification'
    return 'pur'


def main():
    out = sys.argv[1]
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES)
    import io
    stream = io.StringIO()
    t0, w0, c0 = time.perf_counter(), time.time(), time.process_time()
    result = unittest.TextTestRunner(stream=stream, resultclass=Timed, verbosity=0).run(suite)
    total = {'wall': time.perf_counter() - t0, 'wall_clock': time.time() - w0, 'cpu_main': time.process_time() - c0,
             'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped)}
    for r in result.rows:
        r['category'] = category(r)
    cats = {}
    for r in result.rows:
        c = cats.setdefault(r['category'], {'tests': 0, 'wall': 0.0, 'cpu': 0.0, 'copytree_s': 0.0, 'copytree_n': 0, 'subprocess_s': 0.0, 'subprocess_n': 0})
        c['tests'] += 1
        c['wall'] += r['wall']
        c['cpu'] += r['cpu']
        for k in ('copytree_s', 'copytree_n', 'subprocess_s', 'subprocess_n'):
            c[k] += r.get(k, 0)
    mods = {}
    for r in result.rows:
        m = r['id'].split('.')[0]
        mm = mods.setdefault(m, {'tests': 0, 'wall': 0.0})
        mm['tests'] += 1
        mm['wall'] += r['wall']
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'total': total, 'categories': cats, 'modules': mods, 'rows': result.rows}, f, ensure_ascii=False)
    print(json.dumps({'total': total, 'categories': cats, 'modules': mods}))


if __name__ == '__main__':
    main()
