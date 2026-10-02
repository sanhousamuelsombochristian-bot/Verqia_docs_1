"""Univers de traçabilité VERQIA : extrait des documents figés la liste de TOUT ce que la matrice de tests doit couvrir.

Chaque élément est un jeton `FAMILLE:IDENTIFIANT`. La matrice (matrix_rows.py) déclare, pour chaque test, les jetons qu'il couvre ;
build_matrix.py vérifie qu'aucun jeton de l'univers n'est laissé sans test.
"""
import io
import json
import os
import re

DOCS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def rd(name):
    with io.open(os.path.join(DOCS, name), encoding='utf-8') as f:
        return f.read()


def section(text, start, end=None):
    i = text.index(start)
    j = text.index(end, i + 1) if end else len(text)
    return text[i:j]


def build():
    U = {}
    ct, inv, sm = rd('DATA_CONTRACT_V1.md'), rd('INVARIANTS_V1.md'), rd('STATE_MACHINES_V1.md')
    rule, col, aut = rd('RULE_ENGINE_V1.md'), rd('COLLECTION_ENGINE_V1.md'), rd('AUTOMATION_ENGINE_V1.md')
    eng, rpc = rd('ENGINE_CONTRACTS_V1.md'), rd('RISK_PRIORITY_CASHFLOW_V1.md')

    # --- Data Contract
    U['CON'] = sorted({'CON:' + m for m in re.findall(r'^\| (T\d+) \|', section(ct, '## 14.', '## 15.'), re.M)}, key=lambda s: int(s.split('T')[1]))
    U['TAB'] = ['TAB:' + t for t in re.findall(r'^### \d+\.\d+ `(\w+)`', ct, re.M)]
    outcome_row = re.search(r'^\| outcome \| text \| NULL[^\n]*', ct, re.M).group(0)
    U['OUT'] = ['OUT:' + t.strip() for chunk in re.findall(r'`([A-Z_, ]+)`', outcome_row) for t in chunk.split(',') if t.strip()]
    reason_row = re.search(r'^\| status_reason \|[^\n]*', ct, re.M).group(0)
    U['RSN'] = ['RSN:' + t for t in re.findall(r"'([A-Z_]+)'", reason_row)]

    # --- Invariants
    U['INV'] = ['INV:' + m for m in re.findall(r'^\| (C\d+) \|', section(inv, '## Règles communes', '## 1. Organization'), re.M)]
    dec = section(inv, '## 11. État des décisions')
    U['INV'] += ['INV:' + m for m in dict.fromkeys(re.findall(r'^\| ((?:N|D)\d+)(?:[–, ][^|]*)? \|', dec, re.M))]
    # décisions N1–N5, N8–N10 sont groupées dans une ligne : on les déclare explicitement
    U['INV'] += ['INV:N%d' % i for i in range(1, 15) if 'INV:N%d' % i not in U['INV']]
    U['INV'] = list(dict.fromkeys(U['INV']))
    U['INV'] += ['INV:D%d' % i for i in range(1, 10) if 'INV:D%d' % i not in U['INV']]

    # --- State Machines
    U['SM'] = ['SM:%d' % n for n in range(1, 16)]
    U['SM'] += ['SM:' + s for s in re.findall(r'^\| (S\d+) \|', section(sm, '## 17.'), re.M)]
    casc = section(sm, '## 16.', '## 17.')
    n_casc = len([l for l in casc.split('\n') if l.startswith('| ') and not l.startswith('| Transition source') and not l.startswith('|---')])
    U['SMX'] = ['SMX:%d' % i for i in range(1, n_casc + 1)]

    # --- Rule Engine
    r12 = section(rule, '## 12. Décisions', '## 13.')
    U['RULE'] = ['RULE:' + m for m in dict.fromkeys(re.findall(r'^\| (R\d+) \|', r12, re.M))]
    U['RULE'] += ['RULE:' + m for m in re.findall(r'^\| (P\d) \|', section(rule, '## 0.', '## 1.'), re.M)]
    U['EXC'] = ['EXC:' + m for m in re.findall(r'^\| \d+ \| `([A-Z_]+)` \|', section(rule, '## 3.', '### 3.1'), re.M)]
    U['RE'] = ['RE:%02d' % int(m) for m in re.findall(r'^\| (\d+) \| ', section(rule, '### 10.2', '## 11.'), re.M)]

    # --- Collection Engine
    U['COL'] = ['COL:C%d' % i for i in range(1, 14)] + ['COL:' + m for m in re.findall(r'^\| (CP\d) \|', section(col, '## 0.', '## 1.'), re.M)]

    # --- Automation Engine
    U['AUT'] = ['AUT:AU%d' % i for i in range(1, 13)] + ['AUT:' + m for m in re.findall(r'^\| (AP\d) \|', section(aut, '## 0.', '## 1.'), re.M)]

    # --- Engine Contracts
    e10 = section(eng, '## 10.', '## Annexe A')
    U['ENG'] = ['ENG:' + m for m in re.findall(r'^\| \*\*(EC\d+)\*\* \|', e10, re.M)]
    U['ENG'] += ['ENG:' + m for m in re.findall(r'^\| \*\*(P\d)\*\* \|', e10, re.M)]
    U['ENG'] += ['ENG:' + m for m in re.findall(r'^### (EC-\d\d)', eng, re.M)]
    U['ENG'] += ['ENG:' + m for m in re.findall(r'^\| (X\d+) \|', section(eng, '## 8.', '## 9.'), re.M)]
    U['ENG'] += ['ENG:' + m for m in re.findall(r'^\| (DR\d) \|', section(eng, '### 1.2', '### 1.3'), re.M)]
    jobs = []
    for line in section(eng, '### EC-03', '### EC-04').split('\n'):
        if line.startswith('| `'):
            jobs += re.findall(r'`(\w+)`', line.split('|')[1])
    U['JOB'] = ['JOB:' + m for m in dict.fromkeys(jobs)]
    ann = section(eng, '## Annexe A')
    U['ERR'] = ['ERR:' + m for m in re.findall(r'^\| `([A-Z_]+)` \| \w+ \|', ann, re.M)]

    # --- Risk / Priority / Cashflow
    r12 = section(rpc, '## 12. Décisions')
    U['RPC'] = ['RPC:' + m for m in dict.fromkeys(re.findall(r'^\| (?:\*\*)?(RP\d+)(?:\*\*)? \|', r12, re.M))]
    U['RPC'] += ['RPC:P' + m for m in re.findall(r'^\| RP-([A-H]) \|', rpc, re.M)]
    U['RPC'] += ['RPC:' + m for m in re.findall(r'^\| \*\*(CF\d)\*\* \|', rpc, re.M)]
    with io.open(os.path.join(DOCS, 'reference_model', 'golden_cases.json'), encoding='utf-8') as f:
        g = json.load(f)
    U['GOLD'] = ['GOLD:' + x['name'].split()[0] for x in g['risk']] + ['GOLD:' + x['name'].split()[0] for x in g['priority']] \
        + ['GOLD:' + k.split()[0] for k in g['cashflow']]

    # --- Collection Engine V1.2 (rapprochement)
    v12 = rd('COLLECTION_ENGINE_V1_2.md')
    U['RCN'] = ['RCN:' + m for m in re.findall(r'^\| \*\*(RN\d+)\*\* \|', v12, re.M)]
    U['GOLD'] += ['GOLD:' + c['name'].split()[0] for c in g['reconciliation']]

    # --- Architecture technique (décisions TD, invariants TI, règles AR)
    ta = rd('TECHNICAL_ARCHITECTURE_V1.md')
    td = {int(x) for x in re.findall(r'^\| \*\*TD(\d+)\*\* \|', ta, re.M)} | {int(x) for x in re.findall(r'^\*\*TD(\d+)\.\*\*', ta, re.M)}
    U['TD'] = ['TD:%d' % n for n in sorted(td)]
    U['TI'] = ['TI:%d' % int(n) for n in re.findall(r'^\| \*\*TI(\d+)\*\* \|', ta, re.M)]
    U['AR'] = ['AR:%02d' % int(n) for n in re.findall(r'^\| \*\*AR-(\d+)\*\* \|', ta, re.M)]

    # --- Événements (catalogue des Invariants §10.3)
    cat = section(inv, '### 10.3', '\n---\n')
    events = []
    for line in cat.split('\n'):
        if not line.startswith('| `'):
            continue
        cell = line.split('|')[1]
        prefix = None
        for t in re.findall(r'`(_?[A-Z][A-Z0-9_]+)`', cell):
            if t.startswith('_'):
                events.append(prefix + t)
            else:
                events.append(t)
                prefix = t.rsplit('_', 1)[0]
    U['EVT'] = ['EVT:' + e for e in dict.fromkeys(events)]
    return U


if __name__ == '__main__':
    u = build()
    for k, v in u.items():
        print('%-5s %3d' % (k, len(v)))
    print('TOTAL', sum(len(v) for v in u.values()))
