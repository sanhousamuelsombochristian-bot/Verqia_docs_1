"""Mesure la porte AP (`verify_ap`) étape par étape, SANS la modifier : résolution des références, exécution des preuves, base de référence des mutations, chaque mutation
(copie du dépôt / application / exécution des tests). Enveloppes posées de l'extérieur sur shutil.copytree et subprocess.run.
Usage : python diag_gate.py SORTIE.json   (répertoire courant : architecture_registry)
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.getcwd())
import ap_mutations  # noqa: E402
import verify_ap as V  # noqa: E402

ACC = {}
_copy, _run = shutil.copytree, subprocess.run


def copytree(*a, **k):
    t = time.perf_counter()
    try:
        return _copy(*a, **k)
    finally:
        ACC['copy'] = ACC.get('copy', 0.0) + time.perf_counter() - t


def run(*a, **k):
    t = time.perf_counter()
    try:
        return _run(*a, **k)
    finally:
        ACC['sub'] = ACC.get('sub', 0.0) + time.perf_counter() - t
        ACC['sub_n'] = ACC.get('sub_n', 0) + 1


shutil.copytree, subprocess.run = copytree, run


def timed(fn, *a, **k):
    ACC.clear()
    t = time.perf_counter()
    r = fn(*a, **k)
    d = {'wall': time.perf_counter() - t, 'copy': ACC.get('copy', 0.0), 'subprocess': ACC.get('sub', 0.0), 'subprocess_n': ACC.get('sub_n', 0)}
    return r, d


def main():
    out = sys.argv[1]
    res = {}
    (errors, detail), res['resolution (subprocess list)'] = timed(V.check)
    state, res['exécution des preuves (tests + injections)'] = timed(V.run_all, detail)
    _, res['base de référence des mutations'] = timed(V.baseline_of_kills, ap_mutations.MUTATIONS)
    per = {}
    tot = {'wall': 0.0, 'copy': 0.0, 'subprocess': 0.0, 'subprocess_n': 0}
    killed = 0
    for m in ap_mutations.MUTATIONS:
        (status, _), d = timed(V.run_mutation, m)
        per[m.id] = dict(d, status=status)
        killed += status == 'killed'
        for k in tot:
            tot[k] += d[k]
    res['40 mutations (copie + application + tests)'] = tot
    res['ap_errors'] = len(errors)
    res['mutations_killed'] = killed
    res['mutations_total'] = len(ap_mutations.MUTATIONS)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'phases': res, 'per_mutation': per}, f, ensure_ascii=False)
    print(json.dumps(res))


if __name__ == '__main__':
    main()
