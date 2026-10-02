"""Gel du Priority Domain V1 : empreinte des fichiers qui DÉFINISSENT ce que ce Domain décide, journal des
amendements.

Séparé du gel de la tranche 1 (`domain_freeze.py`/`domain_freeze.json`) et du gel du Risk Domain
(`risk_domain_freeze.py`/`.json`) : ce fichier ne les importe pas, ne les modifie pas, et sa liste de fichiers ne
recoupe la leur QUE sur `kernel/decision.py` (dépendance partagée, déjà gelée par la tranche 1 — toute modification
y casserait DÉJÀ ce gel-là ; ce fichier ne fait que l'observer aussi, pour la même raison de dépendance, jamais pour
en revendiquer la propriété). Contrairement à Risk, Priority ne dépend PAS de `kernel/calendar.py` (`prio-1.0` ne
calcule aucune fenêtre temporelle, PD2.3) : il n'est donc pas dans cette liste.

L'empreinte couvre : le code du Domain Priority (`verqia/priority/domain/`), le type de fait niveau C écrit hors du
gel de la tranche 1 (`priority/contracts/facts.py` — `PriorityParameters`), la référence indépendante
(`priority_ref.py`, ses cas d'or), les tests du Domain (`domain_tests/priority/`, y compris `runner_wiring.py`), et
la porte de fermeture (`priority_catalogue.py`, `priority_proofs.py`, `priority_mutations.py` — jamais
`verify_priority_domain.py` lui-même, comme pour Risk et la tranche 1). Toute modification, même légitime, change
l'empreinte : elle passe par une ligne du journal `AMENDMENTS` et un `--write` explicite. Rien ne se gèle ni ne se
dégèle par accident. Les fins de ligne sont normalisées : l'empreinte ne dépend pas du système de fichiers.

Usage : python architecture_registry/priority_domain_freeze.py [--write DATE]
"""
import hashlib
import io
import json
import os
import sys
*$


HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.abspath(os.path.join(HERE, '..'))
APP = os.path.abspath(os.path.join(DOCS, '..', 'verqia-app'))
FREEZE_FILE = os.path.join(HERE, 'priority_domain_freeze.json')

# Journal des amendements du Priority Domain V1 depuis son gel : (id, date, objet, nature, validé). Vide au gel.
AMENDMENTS = []

# État de fermeture au moment du gel (informatif : ne participe pas à l'empreinte, jamais revérifié mécaniquement
# après coup — c'est une PHOTOGRAPHIE de ce qui a été démontré, pas une assertion vivante).
CLOSURE_STATE = {
    'priority_domain_version': 'V1',
    'invariants': '21/21',
    'mutations': '19/19',
    'integration_tests': '27/27',
    'priority_tests': '102/102',
    'global_regression': 'GREEN',
}


def _py(directory):
    return sorted(os.path.join(directory, f) for f in os.listdir(directory) if f.endswith('.py'))


def files():
    out = []
    out += _py(os.path.join(APP, 'verqia', 'priority', 'domain'))
    out += [os.path.join(APP, 'verqia', 'priority', 'contracts', 'facts.py')]
    out += [os.path.join(APP, 'verqia', 'kernel', 'decision.py')]                                      # dépendance partagée, déjà gelée par la tranche 1
    out += _py(os.path.join(APP, 'domain_tests', 'priority'))
    out += [os.path.join(DOCS, 'reference_model', f) for f in ('priority_ref.py', 'gen_golden_priority.py', 'golden_priority.json', 'test_priority_ref.py')]
    out += [os.path.join(HERE, f) for f in ('priority_catalogue.py', 'priority_proofs.py', 'priority_mutations.py')]
    return out


def read(path):
    with io.open(path, encoding='utf-8') as f:
        return f.read().replace('\r\n', '\n')


def fingerprint():
    h = hashlib.sha256()
    paths = files()
    for path in paths:
        rel = os.path.relpath(path, os.path.dirname(APP)).replace(os.sep, '/')
        h.update(rel.encode('utf-8'))
        h.update(b'\0')
        h.update(read(path).encode('utf-8'))
        h.update(b'\0')
    return h.hexdigest(), len(paths)


def read_freeze():
    if not os.path.exists(FREEZE_FILE):
        return None
    with io.open(FREEZE_FILE, encoding='utf-8') as f:
        return json.load(f)


def check_freeze():
    """Erreurs de gel : fichier absent, empreinte différente, journal incohérent."""
    frozen = read_freeze()
    if frozen is None:
        return ['gel Priority : `priority_domain_freeze.json` absent (Priority Domain V1 non gelé)']
    sha, n = fingerprint()
    errors = []
    if frozen.get('sha256') != sha or frozen.get('files') != n:
        errors.append('gel Priority : les fichiers ne correspondent plus à l\'empreinte gelée (%s…) : amendement non journalisé' % frozen.get('sha256', '')[:12])
    if frozen.get('amendments') != len(AMENDMENTS):
        errors.append('gel Priority : le nombre d\'amendements du journal (%d) diffère de celui du gel (%s)' % (len(AMENDMENTS), frozen.get('amendments')))
    return errors


def write_freeze(date):
    sha, n = fingerprint()
    payload = dict(CLOSURE_STATE, status='FROZEN', frozen_at=date, sha256=sha, files=n, amendments=len(AMENDMENTS))
    with io.open(FREEZE_FILE, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write('\n')
    return sha, n


if __name__ == '__main__':
    if '--write' in sys.argv:
        print('gel Priority écrit :', *write_freeze(sys.argv[sys.argv.index('--write') + 1]))
    else:
        errs = check_freeze()
        print('\n'.join(errs) or 'gel Priority : OK')
        sys.exit(1 if errs else 0)
