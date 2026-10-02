"""Gel du Domain V1, tranche 1 (Facture / Échéance / Paiement) : empreinte des fichiers qui DÉFINISSENT ce que le Domain décide, journal des amendements.

L'empreinte couvre : le code du Domain (`invoices.domain`, `payments.domain`), ses types de sortie et ses faits (`kernel/decision.py`, `calendar.py`, `facts.py`,
`contracts/facts.py`), la référence indépendante (`finance_ref.py`, ses cas d'or), les tests du Domain, et la porte de fermeture (catalogue, preuves, mutations).
Toute modification, même légitime, change l'empreinte : elle passe par une ligne du journal `AMENDMENTS` et un `--write` explicite. Rien ne se gèle ni ne se dégèle par accident.
Les fins de ligne sont normalisées : l'empreinte ne dépend pas du système de fichiers.

Usage : python architecture_registry/domain_freeze.py [--write DATE]
"""
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.abspath(os.path.join(HERE, '..'))
APP = os.path.abspath(os.path.join(DOCS, '..', 'verqia-app'))
FREEZE_FILE = os.path.join(HERE, 'domain_freeze.json')

# Journal des amendements du Domain V1 tranche 1 depuis son gel : (id, date, objet, nature, validé). Vide au gel.
AMENDMENTS = []


def _py(directory):
    return sorted(os.path.join(directory, f) for f in os.listdir(directory) if f.endswith('.py'))


def files():
    out = []
    for module in ('invoices', 'payments'):
        out += _py(os.path.join(APP, 'verqia', module, 'domain'))
        out.append(os.path.join(APP, 'verqia', module, 'contracts', 'facts.py'))
    out += [os.path.join(APP, 'verqia', 'kernel', f) for f in ('decision.py', 'calendar.py', 'facts.py')]
    out += _py(os.path.join(APP, 'domain_tests'))
    out += [os.path.join(DOCS, 'reference_model', f) for f in ('finance_ref.py', 'gen_golden_finance.py', 'golden_finance.json', 'test_finance_ref.py')]
    out += [os.path.join(HERE, f) for f in ('domain_catalogue.py', 'domain_proofs.py', 'domain_mutations.py')]
    return out


def fingerprint():
    h = hashlib.sha256()
    listed = files()
    for path in listed:
        rel = os.path.relpath(path, os.path.dirname(APP)).replace(os.sep, '/')
        with io.open(path, encoding='utf-8', newline='') as f:
            text = f.read().replace('\r\n', '\n')
        h.update(rel.encode('utf-8'))
        h.update(b'\0')
        h.update(text.encode('utf-8'))
        h.update(b'\0')
    return h.hexdigest(), len(listed)


def read_freeze():
    if not os.path.exists(FREEZE_FILE):
        return None
    with io.open(FREEZE_FILE, encoding='utf-8') as f:
        return json.load(f)


def check_freeze():
    """Erreurs de gel : fichier absent, empreinte différente, journal incohérent."""
    frozen = read_freeze()
    if frozen is None:
        return ['gel : `domain_freeze.json` absent (Domain V1 tranche 1 non gelé)']
    sha, n = fingerprint()
    errors = []
    if frozen.get('sha256') != sha or frozen.get('files') != n:
        errors.append('gel : les fichiers du Domain ne correspondent plus à l\'empreinte gelée (%s…) : amendement non journalisé' % frozen.get('sha256', '')[:12])
    if frozen.get('amendments') != len(AMENDMENTS):
        errors.append('gel : le nombre d\'amendements du journal (%d) diffère de celui du gel (%s)' % (len(AMENDMENTS), frozen.get('amendments')))
    return errors


def write_freeze(date):
    sha, n = fingerprint()
    with io.open(FREEZE_FILE, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'frozen': date, 'sha256': sha, 'files': n, 'amendments': len(AMENDMENTS)}, f, indent=2)
        f.write('\n')
    return sha, n


if __name__ == '__main__':
    if '--write' in sys.argv:
        sha, n = write_freeze(sys.argv[sys.argv.index('--write') + 1])
        print('gel écrit :', sha, n)
    else:
        errors = check_freeze()
        for e in errors:
            print(e)
        print('gel : OK' if not errors else 'gel : ÉCHEC')
        sys.exit(1 if errors else 0)
