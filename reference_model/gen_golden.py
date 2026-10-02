"""Génère golden_cases.json depuis le modèle de référence. Toute modification du fichier doit être délibérée."""
import json
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import verqia_models as m

C = 1_000_000
ORG = 'org-1'


def risk_case(name, prev, *args):
    r = m.risk_evaluate(ORG, name, prev, *args)
    return {'name': name, 'previous_level': prev, 'inputs': list(args), 'score': r['score'], 'level': r['level'],
            'input_hash': r['input_hash'], 'factors': r['factors']}


def prio_case(name, prev, args, promise_or_hold=False, dispute=False, recon=False):
    r = m.prio_evaluate(ORG, name, prev, *args, promise_or_hold=promise_or_hold, dispute_no_collectible=dispute,
                        reconciliation_pending=recon)
    return {'name': name, 'previous_level': prev, 'inputs': list(args), 'promise_or_hold': promise_or_hold,
            'dispute_no_collectible': dispute, 'reconciliation_pending': recon, 'rank_score': r['rank_score'],
            'level': r['level'], 'caps': r['caps'], 'signals': r['signals'], 'input_hash': r['input_hash']}


def cash_lines(as_of, scenario, invoices, unallocated, risk, d, promises=None, broken=0, horizon=30):
    inv = [dict(i, due=date.fromisoformat(i['due'])) for i in invoices]
    pr = {k: (date.fromisoformat(v[0]), v[1]) for k, v in (promises or {}).items()}
    lines, reserved = m.customer_forecast(date.fromisoformat(as_of), horizon, scenario, inv, unallocated, risk, d, pr, broken)
    return {'reserved_minor': reserved,
            'lines': [{'invoice': l['invoice'], 'category': l['category'], 'amount': l['amount'], 'p_bp': l['p_bp'],
                       'date': l['date'].isoformat() if l['date'] else None, 'weighted': l['weighted'], 'basis': l['basis']}
                      for l in lines]}


inv500 = [{'id': 'I2', 'due': '2026-10-15', 'outstanding': 500_000, 'disputed': 0}]


def _d(x):
    return date.fromisoformat(x)


def rc_case(name, invoice, payments, as_ofs, holidays=()):
    """Cas de rapprochement : pour chaque date `as_of`, le fait `invoice.reconciliation_pending` et ses compléments."""
    inv = dict(invoice, issue_date=_d(invoice['issue_date']))
    pays = [dict(p, value_date=_d(p['value_date']), recorded=_d(p['recorded'])) for p in payments]
    hol = frozenset(_d(h) for h in holidays)
    checks = []
    for a in as_ofs:
        r = m.reconciliation_state(inv, pays, _d(a), holidays=hol)
        checks.append({'as_of': a, **r})
    last = {p['id']: m.window_last_day(dict(p, recorded=_d(p['recorded'])), holidays=hol).isoformat() for p in payments}
    return {'name': name, 'invoice': invoice, 'payments': payments, 'holidays': list(holidays), 'window_last_day': last, 'checks': checks}


def rc_case_at(name, tzname, invoice, payments, nows, holidays=()):
    """Cas de rapprochement à partir d'INSTANTS (UTC) : fuseau de l'organisation, date locale, fin de fenêtre."""
    tz = ZoneInfo(tzname)
    inv = dict(invoice, issue_date=_d(invoice['issue_date']))
    hol = frozenset(_d(h) for h in holidays)
    pays = [dict(p, value_date=_d(p['value_date']), created_at=datetime.fromisoformat(p['created_at'].replace('Z', '+00:00'))) for p in payments]
    checks = []
    for x in nows:
        now = datetime.fromisoformat(x.replace('Z', '+00:00'))
        r = m.reconciliation_state_at(inv, pays, now, tz, holidays=hol)
        checks.append({'now_utc': x, 'local_date': m.local_date(now, tz).isoformat(), **r})
    return {'name': name, 'timezone': tzname, 'invoice': invoice, 'payments': payments, 'holidays': list(holidays),
            'local_recorded': {p['id']: m.local_date(p['created_at'], tz).isoformat() for p in pays},
            'window_last_day': {p['id']: m.add_business_days(m.local_date(p['created_at'], tz), 3, holidays=hol).isoformat() for p in pays},
            'barrier_lifted_at_utc': {p['id']: m.barrier_lifted_at(p['created_at'], tz, holidays=hol).strftime('%Y-%m-%dT%H:%M:%SZ') for p in pays},
            'checks': checks}


def _pay(**k):
    base = dict(id='P1', customer='c1', currency='XOF', amount=100_000, allocated=0, status='RECEIVED',
                value_date='2026-10-19', recorded='2026-10-19')
    base.update(k)
    return base


_INV_A = {'id': 'A', 'customer': 'c1', 'currency': 'XOF', 'issue_date': '2026-10-01', 'is_open': True}


def build_reconciliation():
    return [
        rc_case('R1 paiement non alloué, facture candidate', _INV_A, [_pay()],
                ['2026-10-19', '2026-10-20', '2026-10-22', '2026-10-23']),
        rc_case('R2 paiement antérieur à l’émission de la facture', _INV_A, [_pay(value_date='2026-09-30', recorded='2026-10-19')], ['2026-10-19']),
        rc_case('R3 paiement entièrement alloué', _INV_A, [_pay(allocated=100_000, status='ALLOCATED')], ['2026-10-19']),
        rc_case('R4 paiement annulé', _INV_A, [_pay(status='REVERSED')], ['2026-10-19']),
        rc_case('R5 allocation partielle : reliquat de 40 000', _INV_A, [_pay(allocated=60_000, status='PARTIALLY_ALLOCATED')], ['2026-10-19']),
        rc_case('R6 jour férié dans la fenêtre', _INV_A, [_pay(value_date='2026-10-23', recorded='2026-10-23')],
                ['2026-10-26', '2026-10-29', '2026-10-30'], holidays=['2026-10-26']),
        rc_case('R7 deux paiements non alloués', _INV_A, [_pay(), _pay(id='P2', amount=20_000, value_date='2026-10-20', recorded='2026-10-20')],
                ['2026-10-20', '2026-10-23', '2026-10-26']),
        rc_case('R8 devise différente', _INV_A, [_pay(currency='EUR')], ['2026-10-19']),
        rc_case('R9 facture non ouverte', dict(_INV_A, is_open=False), [_pay()], ['2026-10-19']),
        rc_case('R10 paiement enregistré tard (date de valeur ancienne)', _INV_A,
                [_pay(value_date='2026-10-01', recorded='2026-10-21')], ['2026-10-21', '2026-10-26']),
        # --- RN5 : instants, fuseau de l'organisation, minuit local (la date UTC ne compte jamais)
        rc_case_at('R11 enregistré vendredi soir UTC, samedi côté Paris', 'Europe/Paris', _INV_A,
                   [_pay(value_date='2026-10-23', created_at='2026-10-23T22:30:00Z')],
                   ['2026-10-23T22:30:00Z', '2026-10-27T21:59:59Z', '2026-10-28T22:59:59Z', '2026-10-28T23:00:00Z']),
        rc_case_at('R12 enregistré mardi UTC, lundi soir côté New York', 'America/New_York', _INV_A,
                   [_pay(value_date='2026-10-19', created_at='2026-10-20T02:00:00Z')],
                   ['2026-10-20T02:00:00Z', '2026-10-23T03:59:59Z', '2026-10-23T04:00:00Z', '2026-10-24T03:59:59Z']),
        rc_case_at('R13 frontière de minuit local (Paris, heure d’été)', 'Europe/Paris', _INV_A,
                   [_pay(created_at='2026-10-19T09:00:00Z')],
                   ['2026-10-22T09:00:00Z', '2026-10-22T21:59:59Z', '2026-10-22T22:00:00Z', '2026-10-23T09:00:00Z']),
        rc_case_at('R14 changement d’heure dans la fenêtre (Paris, 25 octobre)', 'Europe/Paris', _INV_A,
                   [_pay(value_date='2026-10-23', created_at='2026-10-23T08:00:00Z')],
                   ['2026-10-28T22:00:00Z', '2026-10-28T22:59:59Z', '2026-10-28T23:00:00Z']),
    ]


def build_golden():
  return {
    'risk': [
        risk_case('G1', None, 3, 0, 0, 0, 0, 100_000, C, 0, None),
        risk_case('G2', None, 20, 8, 750, 20, 1, 600_000, C, 0, 4),
        risk_case('G3', None, 70, 10, 900, 40, 3, 2_000_000, C, 2, 10),
        risk_case('G4', None, 0, 12, 100, 3, 0, 0, C, 0, 0),
        risk_case('G5', None, 35, 2, 1000, 45, 0, 1_500_000, C, 0, None),
    ],
    'priority': [
        prio_case('P1', None, (1_200_000, C, 20, -20, 'HIGH', 12, True)),
        prio_case('P2', None, (50_000, C, 0, 2, 'LOW', None, False)),
        prio_case('P3', None, (400_000, C, 5, -5, 'MEDIUM', 2, True)),
        prio_case('P4', None, (700_000, C, 40, -40, None, 40, True)),
        prio_case('P5 plafond promesse', 4, (1_200_000, C, 20, -20, 'HIGH', 12, True), promise_or_hold=True),
        prio_case('P6 plafond litige', 4, (1_200_000, C, 20, -20, 'HIGH', 12, True), dispute=True),
        prio_case('P7 rapprochement en attente (signal seul)', None, (1_200_000, C, 20, -20, 'HIGH', 12, True), recon=True),
    ],
    'reconciliation': build_reconciliation(),
    'cashflow': {
        'C1 non echue BASE': cash_lines('2026-10-01', 'BASE', inv500, 0, 'MEDIUM', 6),
        'C2 non echue OPTIMISTIC': cash_lines('2026-10-01', 'OPTIMISTIC', inv500, 0, 'MEDIUM', 6),
        'C3 non echue PESSIMISTIC': cash_lines('2026-10-01', 'PESSIMISTIC', inv500, 0, 'MEDIUM', 6),
        'C4 echue BASE': cash_lines('2026-10-20', 'BASE', inv500, 0, 'MEDIUM', 6),
        'C5 echue OPTIMISTIC': cash_lines('2026-10-20', 'OPTIMISTIC', inv500, 0, 'MEDIUM', 6),
        'C6 echue PESSIMISTIC': cash_lines('2026-10-20', 'PESSIMISTIC', inv500, 0, 'MEDIUM', 6),
        'C7 promesse et litige': cash_lines('2026-10-20', 'BASE', [{'id': 'I2', 'due': '2026-10-15', 'outstanding': 500_000, 'disputed': 200_000}],
                                            0, 'MEDIUM', 6, promises={'I2': ('2026-10-25', 150_000)}, broken=1),
        'C8 66 jours de retard HIGH': cash_lines('2026-12-20', 'BASE', inv500, 0, 'HIGH', 6),
        'C9 non alloue 200 000 (FIFO)': cash_lines('2026-10-20', 'BASE', [
            {'id': 'I1', 'due': '2026-10-10', 'outstanding': 300_000, 'disputed': 0},
            {'id': 'I2', 'due': '2026-10-15', 'outstanding': 500_000, 'disputed': 0}], 200_000, 'MEDIUM', 6),
        'C10 non alloue couvre tout': cash_lines('2026-10-20', 'BASE', [
            {'id': 'I1', 'due': '2026-10-10', 'outstanding': 300_000, 'disputed': 0}], 400_000, 'MEDIUM', 6),
    },
}


def to_jsonable(obj):
    """Normalise (tuples -> listes, clés triées) exactement comme le fichier JSON."""
    return json.loads(json.dumps(obj, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    golden = build_golden()
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'golden_cases.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(golden, f, ensure_ascii=False, indent=1, sort_keys=True)
    print('golden_cases.json ecrit :', len(golden['risk']), 'cas de risque,', len(golden['priority']), 'de priorite,',
          len(golden['cashflow']), 'de tresorerie,', len(golden['reconciliation']), 'de rapprochement')
