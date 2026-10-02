"""Cas d'or Priority (Domain V1, tranche Priority) : entrées déclaratives, sorties calculées par `priority_ref`
(jamais par le Domain).

Usage : python gen_golden_priority.py [--check]     (écrit / vérifie golden_priority.json)
"""
import io
import json
import os
import sys

import priority_ref as R

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'golden_priority.json')

C = 1_000_000


def build():
    g = {}

    # ---- G1 (P1-P7), reproduits depuis golden_cases.json['priority'] (contrôle croisé, déjà indépendant)
    with io.open(os.path.join(HERE, 'golden_cases.json'), encoding='utf-8') as f:
        existing = json.load(f)['priority']
    g['formula'] = []
    for c in existing:
        A, Dd, Dj, risk_level, since_action, overdue = c['inputs'][0], c['inputs'][2], c['inputs'][3], c['inputs'][4], c['inputs'][5], c['inputs'][6]
        prev = R.LEVELS[c['previous_level']] if c['previous_level'] is not None else None
        out = R.score_and_level(A, c['inputs'][1], overdue, Dd, Dj, risk_level, since_action, prev, c['promise_or_hold'], c['dispute_no_collectible'])
        g['formula'].append({'id': 'P-SC-%s' % c['name'].split(' ')[0], 'input': {'A': A, 'C': c['inputs'][1], 'overdue': overdue, 'Dd': Dd, 'Dj': Dj,
                                                                                  'risk_level': risk_level, 'S': since_action, 'previous_level': prev,
                                                                                  'promise_or_hold': c['promise_or_hold'], 'dispute_no_collectible': c['dispute_no_collectible']},
                             'expect': {'score': out['score'], 'level': out['level'], 'caps': out['caps']}})

    # ---- points, bornes (RD4-équivalent)
    g['points'] = [
        {'id': 'P-PT-amt%02d' % i, 'input': {'A': A, 'C': C}, 'expect': R.amount_points(A, C)}
        for i, A in enumerate([0, 1, 500_000, 999_999, 1_000_000, 2_000_000])
    ] + [
        {'id': 'P-PT-del%02d' % i, 'input': {'Dd': Dd}, 'expect': R.delay_points(Dd)}
        for i, Dd in enumerate([0, 1, 7, 8, 15, 16, 30, 31, 60, 61, 200])
    ] + [
        {'id': 'P-PT-due%02d' % i, 'input': {'Dj': Dj}, 'expect': R.due_points(Dj)}
        for i, Dj in enumerate([-1, 0, 3, 4, 7, 8, 100])
    ] + [
        {'id': 'P-PT-att%02d' % i, 'input': {'S': S}, 'expect': R.attention_points(S)}
        for i, S in enumerate([None, 0, 4, 5, 9, 10, 100])
    ] + [
        {'id': 'P-PT-risk%02d' % i, 'input': {'risk_level': rl}, 'expect': R.RISK_PTS[rl]}
        for i, rl in enumerate(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL', None])
    ]

    # ---- niveaux (bornes des seuils)
    g['levels'] = [{'id': 'P-LV%02d' % s, 'input': {'score': s}, 'expect': R.LEVELS[R.level_index(s)]} for s in (0, 19, 20, 39, 40, 59, 60, 79, 80, 95)]

    # ---- hystérésis : même séquence documentée que Risk (§1.3), seuil ACTION=40 cette fois (index 2)
    # frontière choisie autour du seuil PRIORITY=60 (index 3) pour varier de l'exemple Risk
    sequence = [54, 56, 59, 61, 58, 57, 59, 60, 56, 55, 54]
    levels_seq, prev = [], None
    for s in sequence:
        idx = R.stabilise(s, R.LEVELS.index(prev) if prev is not None else None)
        prev = R.LEVELS[idx]
        levels_seq.append(prev)
    g['hysteresis_example'] = {'id': 'P-HY01', 'input': {'scores': sequence},
                               'expect': {'levels': levels_seq, 'changes': sum(1 for a, b in zip([None] + levels_seq, levels_seq) if a != b) - 1}}

    # ---- hystérésis à la limite exacte (RL10-équivalent pour Priority, seuil PRIORITY=60)
    g['hysteresis_boundary'] = [
        {'id': 'P-HY-B01', 'title': 'score+MARGIN == seuil : reste (57+3=60)', 'input': {'score': 57, 'previous_level': 'PRIORITY'},
         'expect': R.LEVELS[R.stabilise(57, R.LEVELS.index('PRIORITY'))]},
        {'id': 'P-HY-B02', 'title': 'score+MARGIN < seuil : descend (56+3=59<60)', 'input': {'score': 56, 'previous_level': 'PRIORITY'},
         'expect': R.LEVELS[R.stabilise(56, R.LEVELS.index('PRIORITY'))]},
    ]

    # ---- éligibilité à trois états (PD3)
    g['eligibility'] = [
        {'id': 'P-EL-draft', 'input': {'is_draft': True, 'is_open': False}, 'expect': R.eligibility_of(True, False)},
        {'id': 'P-EL-closed', 'input': {'is_draft': False, 'is_open': False}, 'expect': R.eligibility_of(False, False)},
        {'id': 'P-EL-active', 'input': {'is_draft': False, 'is_open': True}, 'expect': R.eligibility_of(False, True)},
    ]

    # ---- dérivation dispute_no_collectible (§ DV3-5)
    g['dispute_derivation'] = [
        {'id': 'P-DD01', 'input': {'has_open_dispute': True, 'collectible_minor': 0}, 'expect': R.dispute_no_collectible_of(True, 0)},
        {'id': 'P-DD02', 'input': {'has_open_dispute': True, 'collectible_minor': 500}, 'expect': R.dispute_no_collectible_of(True, 500)},
        {'id': 'P-DD03', 'input': {'has_open_dispute': False, 'collectible_minor': 0}, 'expect': R.dispute_no_collectible_of(False, 0)},
    ]

    # ---- plafonds : individuels et combinés (§3.4)
    def cap_case(cid, promise, hold, dispute_nc):
        out = R.apply_caps(4, promise or hold, dispute_nc)          # stabilisé = CRITICAL (4) avant plafond
        return {'id': cid, 'input': {'promise': promise, 'hold': hold, 'dispute_no_collectible': dispute_nc},
               'expect': {'level': R.LEVELS[out[0]], 'caps': out[1]}}

    g['caps'] = [
        cap_case('P-CAP-none', False, False, False),
        cap_case('P-CAP-promise', True, False, False),
        cap_case('P-CAP-hold', False, True, False),
        cap_case('P-CAP-promise-and-hold', True, True, False),
        cap_case('P-CAP-dispute', False, False, True),
        cap_case('P-CAP-promise-and-dispute', True, False, True),               # WATCH (le plus bas) l'emporte sur ACTION
    ]

    # ---- decision : succession d'appels evaluate_priority (RP14-équivalent, premier calcul sans PRIORITY_CHANGED,
    # score change mais niveau publié inchangé, signal de réconciliation sans effet sur score/niveau)
    def step(previous, **kw):
        base = dict(is_draft=False, is_open=True, critical_amount_minor=C, outstanding_minor=400_000, is_late=True,
                   days_late=5, days_to_due=-5, collectible_minor=400_000, has_open_dispute=False, risk_level='MEDIUM',
                   days_since_last_action=2, active_promise=False, hold_active=False, reconciliation_pending=False)
        base.update(kw)
        return R.evaluate_priority(previous, **base)

    def published(o):
        return {'level': o['level'], 'normalized_inputs': o['normalized_inputs']}

    o1 = step(None)                                                  # premier calcul
    o2 = step(published(o1))                                         # même facts : previous_level None->réel, change quand même
    o3 = step(published(o2))                                         # régime stationnaire
    o4 = step(published(o3), outstanding_minor=450_000)               # amount_pts 12->13 (change réel de tranche) : score change, niveau reste WATCH
    o5 = step(published(o4), outstanding_minor=450_000, reconciliation_pending=True)   # signal seul (montant maintenu) : hash/reasons changent, score/niveau non
    o6 = step(published(o5), days_late=40, outstanding_minor=1_500_000, reconciliation_pending=True)  # gros changement : niveau publié change
    o7 = R.evaluate_priority(None, is_draft=True, is_open=False, critical_amount_minor=C, outstanding_minor=0, is_late=False,
                             days_late=0, days_to_due=0, collectible_minor=0, has_open_dispute=False, risk_level=None,
                             days_since_last_action=None, active_promise=False, hold_active=False, reconciliation_pending=False)
    o8 = R.evaluate_priority(None, is_draft=False, is_open=False, critical_amount_minor=C, outstanding_minor=0, is_late=False,
                             days_late=0, days_to_due=0, collectible_minor=0, has_open_dispute=False, risk_level=None,
                             days_since_last_action=None, active_promise=False, hold_active=False, reconciliation_pending=False)

    g['decision'] = [
        {'id': 'P-DC01', 'title': 'premier calcul : élément créé, aucun PRIORITY_CHANGED', 'expect': {'eligible': o1['eligible'], 'changed': o1['changed'], 'event': o1['event'], 'level': o1['level']}},
        {'id': 'P-DC02', 'title': 'second calcul, mêmes facts : previous_level None->réel change quand même les entrées normalisées', 'expect': {'changed': o2['changed'], 'event': o2['event'], 'level': o2['level']}},
        {'id': 'P-DC03', 'title': 'troisième calcul, mêmes facts, previous_level stable : régime stationnaire', 'expect': {'changed': o3['changed'], 'event': o3['event']}},
        {'id': 'P-DC04', 'title': 'le score change (montant) mais le niveau publié reste identique : écriture sans événement', 'expect': {'changed': o4['changed'], 'event': o4['event'], 'level': o4['level'], 'score': o4['score']}},
        {'id': 'P-DC05', 'title': 'signal de réconciliation seul : hash/reasons changent, score et niveau non', 'expect': {'changed': o5['changed'], 'event': o5['event'], 'level': o5['level'], 'score': o5['score']}},
        {'id': 'P-DC06', 'title': 'changement important : niveau publié change, PRIORITY_CHANGED émis', 'expect': {'changed': o6['changed'], 'event': o6['event'], 'level': o6['level']}},
        {'id': 'P-DC07', 'title': 'facture DRAFT : aucun élément', 'expect': o7},
        {'id': 'P-DC08', 'title': 'facture fermée, premier calcul : élément NONE/CLOSED, aucun événement', 'expect': {'eligible': o8['eligible'], 'is_closed': o8['is_closed'], 'score': o8['score'], 'level': o8['level'], 'changed': o8['changed'], 'event': o8['event']}},
    ]

    return g


def render(g):
    return json.dumps(g, sort_keys=True, indent=1, ensure_ascii=False, default=str) + '\n'


if __name__ == '__main__':
    text = render(build())
    if '--check' in sys.argv:
        with io.open(OUT, encoding='utf-8', newline='') as f:
            current = f.read().replace('\r\n', '\n')
        sys.exit(0 if current == text else 'golden_priority.json est en dérive : relancer gen_golden_priority.py')
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print('écrit', OUT, len(text), 'octets')
