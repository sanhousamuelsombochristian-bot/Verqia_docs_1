"""Cas d'or Risk (Domain V1, tranche Risk) : entrées déclaratives, sorties calculées par `risk_ref` (jamais par le Domain).

Usage : python gen_golden_risk.py [--check]     (écrit / vérifie golden_risk.json)
"""
import io
import json
import os
import sys
from datetime import date, datetime, timezone

import risk_ref as R

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'golden_risk.json')

PARAMS = {'critical_amount_minor': 1000000, 'timezone': 'UTC'}
NOW = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)


def inv(is_open, is_late, days_late=0, outstanding=0):
    return {'is_open': is_open, 'is_late': is_late, 'days_late': days_late, 'outstanding_minor': outstanding}


def settled(delay, settled_on):
    return {'is_open': False, 'is_late': False, 'days_late': 0, 'outstanding_minor': 0,
            'settlement_delay_days': delay, 'settled_on': date.fromisoformat(settled_on)}


def build():
    g = {}

    # ---- G1 à G5, reproduits depuis golden_cases.json['risk'] (contrôle croisé avec verqia_models, déjà indépendant)
    with io.open(os.path.join(HERE, 'golden_cases.json'), encoding='utf-8') as f:
        existing = json.load(f)['risk']
    g['formula'] = []
    for c in existing:
        D, n, L, M, B, Eo, C, Rv, T = c['inputs']
        out = R.score_and_level(D, n, L, M, B, Eo, C, Rv, T, c['previous_level'])
        g['formula'].append({'id': 'R-SC-%s' % c['name'], 'input': {'D': D, 'n': n, 'L': L, 'M': M, 'B': B, 'Eo': Eo, 'C': C, 'R': Rv, 'T': T,
                                                                    'previous_level': c['previous_level']}, 'expect': out})

    # ---- points, bornes et arrondis (RD4, RD15)
    g['points'] = [
        {'id': 'R-PT%02d' % i, 'input': {'D': D}, 'expect': R.delay_points(D)}
        for i, D in enumerate([0, 1, 7, 8, 15, 16, 17, 18, 30, 31, 60, 61, 200])
    ] + [
        {'id': 'R-PT-hist%02d' % i, 'input': {'n': n, 'L': L, 'M': M}, 'expect': list(R.history_points(n, L, M))}
        for i, (n, L, M) in enumerate([(2, 999, 30), (3, 0, 0), (3, 1000, 30), (3, 1000, 35), (3, 500, -10), (3, 500, 29)])
    ] + [
        {'id': 'R-PT-exp%02d' % i, 'input': {'Eo': Eo, 'C': C}, 'expect': R.exposure_points(Eo, C)}
        for i, (Eo, C) in enumerate([(0, 0), (0, 1000000), (500000, 0), (1000000, 1000000), (2000000, 1000000)])
    ] + [
        {'id': 'R-PT-trend%02d' % i, 'input': {'T': T}, 'expect': R.trend_points(T)}
        for i, T in enumerate([None, -5, 0, 1, 10, 100])
    ]

    # ---- niveaux et hystérésis (RD6, RD7, §1.3 exemple documenté)
    g['levels'] = [{'id': 'R-LV%02d' % s, 'input': {'score': s}, 'expect': R.LEVELS[R.level_index(s)]} for s in (0, 24, 25, 49, 50, 74, 75, 100)]
    sequence = [44, 46, 49, 51, 48, 47, 49, 50, 46, 45, 44]
    levels_seq, prev = [], None
    for s in sequence:
        idx = R.stabilise(s, R.LEVELS.index(prev) if prev is not None else None)
        prev = R.LEVELS[idx]
        levels_seq.append(prev)
    g['hysteresis_example'] = {'id': 'R-HY01', 'input': {'scores': sequence}, 'expect': {'levels': levels_seq, 'changes': sum(1 for a, b in zip([None] + levels_seq, levels_seq) if a != b) - 1}}

    # ---- agrégation (RD2.2) : D, Eo depuis des factures ouvertes
    open_a = [inv(True, True, 5, 100), inv(True, True, 20, 300), inv(True, False, 0, 50), inv(False, True, 999, 999)]
    g['aggregate_D_Eo'] = [{'id': 'R-AG01', 'input': 'open_a', 'expect': list(R.aggregate_D_Eo(open_a))},
                           {'id': 'R-AG02', 'input': 'aucune facture en retard', 'expect': list(R.aggregate_D_Eo([inv(True, False, 0, 100)]))},
                           {'id': 'R-AG03', 'input': 'aucune facture ouverte', 'expect': list(R.aggregate_D_Eo([]))}]

    # ---- n, L, M (RD2.2, fenêtre de 12 mois déjà résolue par l'Application)
    s3 = [settled(5, '2026-08-01'), settled(-2, '2026-07-01'), settled(10, '2026-06-01')]
    g['aggregate_n_L_M'] = [
        {'id': 'R-AG10', 'input': 'n=3 mixte', 'expect': list(R.aggregate_n_L_M(s3))},
        {'id': 'R-AG11', 'input': 'n=2 (insuffisant)', 'expect': list(R.aggregate_n_L_M(s3[:2]))},
        {'id': 'R-AG12', 'input': 'n=0', 'expect': list(R.aggregate_n_L_M([]))},
        {'id': 'R-AG13', 'input': 'tous en retard', 'expect': list(R.aggregate_n_L_M([settled(1, '2026-08-01'), settled(2, '2026-08-02'), settled(3, '2026-08-03')]))},
    ]

    # ---- T (RD2.4, deux sous-fenêtres de 90 jours, filtrage par settled_on)
    today = date(2026, 9, 22)
    recent2 = [settled(4, '2026-08-01'), settled(6, '2026-07-01')]     # dans les 90 derniers jours (52 et 83 jours avant `today`)
    prior2 = [settled(10, '2026-05-25'), settled(20, '2026-04-25')]    # dans les 90 jours précédents (120 et 150 jours avant `today`, ∈ [91,180])
    g['aggregate_T'] = [
        {'id': 'R-AG20', 'input': 'deux fenêtres suffisantes', 'expect': R.aggregate_T(recent2 + prior2, today)},
        {'id': 'R-AG21', 'input': 'fenêtre récente insuffisante (1 seule)', 'expect': R.aggregate_T(recent2[:1] + prior2, today)},
        {'id': 'R-AG22', 'input': 'fenêtre précédente insuffisante (1 seule)', 'expect': R.aggregate_T(recent2 + prior2[:1], today)},
        {'id': 'R-AG23', 'input': 'aucune facture', 'expect': R.aggregate_T([], today)},
    ]

    # ---- B, R (RD2.2, comptes simples)
    g['aggregate_B_R'] = [
        {'id': 'R-AG30', 'input': {'promises': 3, 'reversed': 2}, 'expect': {'B': R.aggregate_B([{}] * 3), 'R': R.aggregate_R([{}] * 2)}},
        {'id': 'R-AG31', 'input': {'promises': 0, 'reversed': 0}, 'expect': {'B': R.aggregate_B([]), 'R': R.aggregate_R([])}},
    ]

    # ---- éligibilité (RD3)
    g['eligibility'] = [{'id': 'R-EL%02d' % i, 'input': {'has_ever_issued': h}, 'expect': R.is_eligible(h)} for i, h in enumerate([True, False])]

    # ---- decision : succession d'appels evaluate_risk (RD11, snapshot vs événement, premier calcul sans RISK_CHANGED)
    # `previous_level` fait PARTIE des entrées normalisées (RP14) : il passe de `None` à une valeur réelle entre le premier
    # et le second calcul, donc le SECOND calcul change lui aussi les entrées normalisées même à facts identiques — un
    # nouveau snapshot sans événement, pas un no-op. Le régime stationnaire (`changed=False`) n'apparaît qu'au TROISIÈME appel.
    p1 = PARAMS

    def step(previous, invoices):
        return R.evaluate_risk(previous, p1, True, invoices, [], [], [], NOW)

    def published(o):
        return {'level': o['level'], 'normalized_inputs': o['normalized_inputs']}

    o1 = step(None, open_a)                                    # premier calcul : profil créé
    o2 = step(published(o1), open_a)                           # même facts, previous_level None→LOW : change quand même (RP14)
    o3 = step(published(o2), open_a)                            # même facts, previous_level stable : régime stationnaire
    open_b = [inv(True, True, 65, 2000000)]                     # score bien plus haut
    o4 = step(published(o3), open_b)                            # niveau publié change
    o5 = R.evaluate_risk(None, p1, False, [], [], [], [], NOW)  # pas éligible
    g['decision'] = [
        {'id': 'R-DC01', 'title': 'premier calcul : profil créé, aucun RISK_CHANGED', 'expect': {'eligible': o1['eligible'], 'changed': o1['changed'], 'event': o1['event'], 'level': o1['level']}},
        {'id': 'R-DC02', 'title': 'second calcul, mêmes facts : previous_level None→LOW change les entrées normalisées (RP14)', 'expect': {'changed': o2['changed'], 'event': o2['event'], 'level': o2['level']}},
        {'id': 'R-DC03', 'title': 'troisième calcul, mêmes facts, previous_level stable : régime stationnaire', 'expect': {'changed': o3['changed'], 'event': o3['event']}},
        {'id': 'R-DC04', 'title': 'niveau publié change : RISK_CHANGED', 'expect': {'changed': o4['changed'], 'event': o4['event'], 'level': o4['level']}},
        {'id': 'R-DC05', 'title': 'client jamais émis : pas de profil', 'expect': o5},
    ]

    return g


def render(g):
    return json.dumps(g, sort_keys=True, indent=1, ensure_ascii=False, default=str) + '\n'


if __name__ == '__main__':
    text = render(build())
    if '--check' in sys.argv:
        with io.open(OUT, encoding='utf-8', newline='') as f:
            current = f.read().replace('\r\n', '\n')
        sys.exit(0 if current == text else 'golden_risk.json est en dérive : relancer gen_golden_risk.py')
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print('écrit', OUT, len(text), 'octets')
