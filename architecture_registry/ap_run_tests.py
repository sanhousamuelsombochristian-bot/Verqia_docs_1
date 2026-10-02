"""Résout ou exécute des identifiants de tests DANS UN PROCESSUS ISOLÉ (le répertoire courant fixe la suite : `architecture_registry` ou `verqia-app`).

  python ap_run_tests.py list  ID... | @fichier     → JSON {"ids": {id: [feuilles]}, "errors": {id: message}}
  python ap_run_tests.py run   ID...     → JSON {feuille: "ok" | "fail" | "error" | "skip"}      (les identifiants sont des FEUILLES)

Un identifiant peut se terminer par `*` sur le nom de test (`Classe.test_rv6_*`).
"""
import fnmatch
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.getcwd())


def flatten(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from flatten(t)
        else:
            yield t


def expand(loader, ident):
    head, _, last = ident.rpartition('.')
    if '*' in last:
        leaves = [t for t in flatten(loader.loadTestsFromName(head)) if fnmatch.fnmatch(t.id().rsplit('.', 1)[-1], last)]
        if not leaves:
            raise ValueError('aucun test ne correspond au motif')
    else:
        leaves = list(flatten(loader.loadTestsFromName(ident)))
    bad = [t for t in leaves if isinstance(t, unittest.loader._FailedTest)]
    if bad:
        raise ValueError(str(bad[0]._exception)[:200] if hasattr(bad[0], '_exception') else 'introuvable')
    if not leaves:
        raise ValueError('aucun test')
    return [t.id() for t in leaves]


class Recorder(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.outcomes = {}

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes[test.id()] = 'ok'

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[test.id()] = 'fail'

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[test.id()] = 'error'

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[test.id()] = 'skip'


def main():
    mode, ids = sys.argv[1], sys.argv[2:]
    if len(ids) == 1 and ids[0].startswith('@'):                     # liste dans un fichier : la ligne de commande a une taille limitée
        with io.open(ids[0][1:], encoding='utf-8') as f:
            ids = [line.strip() for line in f if line.strip()]
    loader = unittest.TestLoader()
    if mode == 'list':
        out = {'ids': {}, 'errors': {}}
        for ident in ids:
            try:
                out['ids'][ident] = expand(loader, ident)
            except Exception as e:                                       # noqa: BLE001
                out['errors'][ident] = '%s: %s' % (type(e).__name__, e)
        print(json.dumps(out))
        return
    suite = unittest.TestSuite(loader.loadTestsFromName(i) for i in ids)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, resultclass=Recorder, verbosity=0).run(suite)
    print(json.dumps(result.outcomes))


if __name__ == '__main__':
    main()
