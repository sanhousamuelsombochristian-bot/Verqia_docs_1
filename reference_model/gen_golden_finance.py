"""Cas d'or financiers F1… : entrées déclaratives, sorties calculées par `finance_ref` (jamais par le Domain).

Usage : python gen_golden_finance.py [--check]     (écrit / vérifie golden_finance.json)
"""
import io
import json
import os
import sys
from datetime import datetime, timezone

import finance_ref as R

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'golden_finance.json')

DUE = '2026-09-30'
F1 = dict(total=11501, issue='2026-09-01', due=DUE, due_soon_days=7)


def timeline(cid, title, ops, **over):
    args = dict(F1, **over)
    return {'id': cid, 'title': title, 'input': dict(args, ops=ops),
            'expect': R.run_timeline(args['total'], args['issue'], args['due'], args['due_soon_days'], ops)}


def build():
    g = {}
    g['line_total'] = [{'id': 'F-LT%02d' % i, 'input': {'quantity_e4': q, 'unit_price_minor': p}, 'expect': R.line_total(q, p)}
                       for i, (q, p) in enumerate([(20000, 5000), (5000, 3001), (1, 4999), (1, 5000), (10000, 7), (3, 3333), (3, 3334), (5, 1000), (4, 1000)])]
    g['settlement'] = [{'id': 'F-ST%02d' % i, 'input': {'paid': p, 'total': t}, 'expect': R.settlement_of(p, t)}
                       for i, (p, t) in enumerate([(0, 100), (1, 100), (99, 100), (100, 100), (0, 1), (1, 1)])]
    grid = []
    for dsd in (0, 1, 7, 90):
        for today in ('2026-07-01', '2026-07-02', '2026-09-22', '2026-09-23', '2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01', '2026-11-15'):
            grid.append({'id': 'F-PO%02d' % len(grid), 'input': {'due': DUE, 'today': today, 'due_soon_days': dsd}, 'expect': R.position_of(
                R.date.fromisoformat(DUE), R.date.fromisoformat(today), dsd)})
    g['position'] = grid
    bd = []
    for instant, tz in [('2026-09-29T23:30:00+00:00', 'Pacific/Auckland'), ('2026-10-01T05:00:00+00:00', 'America/Los_Angeles'),
                        ('2026-03-28T23:30:00+00:00', 'Europe/Paris'), ('2026-03-29T21:59:00+00:00', 'Europe/Paris'), ('2026-03-29T22:30:00+00:00', 'Europe/Paris'),
                        ('2026-09-30T09:00:00+00:00', 'UTC')]:
        bd.append({'id': 'F-BD%02d' % len(bd), 'input': {'instant': instant, 'tz': tz},
                   'expect': R.business_date(datetime.fromisoformat(instant), tz).isoformat()})
    g['business_date'] = bd
    g['collectible'] = [{'id': 'F-CO%02d' % i, 'input': {'outstanding': o, 'dispute': d},
                         'expect': {'collectible': R.collectible_of(o, d), 'disputed_part': R.disputed_part_of(o, d)}}
                        for i, (o, d) in enumerate([(6501, None), (6501, {'amount': None}), (6501, {'amount': 4000}), (501, {'amount': 4000}), (6501, {'amount': 6501}), (0, {'amount': None})])]
    g['timeline'] = [
        timeline('F-TL01', 'N2 émission dans les temps', [['issue', '2026-09-10']]),
        timeline('F-TL02', 'N3 émission dans la fenêtre : un saut, deux événements', [['issue', '2026-09-25']]),
        timeline('F-TL03', 'N4 émission en retard : cycle 1', [['issue', '2026-10-05']]),
        timeline('F-TL04', 'N5 émission le jour de l’échéance', [['issue', DUE]]),
        timeline('F-TL05', 'N6 N7 balayages successifs', [['issue', '2026-09-10'], ['scan', '2026-09-22'], ['scan', '2026-09-23'], ['scan', DUE], ['scan', '2026-10-01'], ['scan', '2026-10-02']]),
        timeline('F-TL06', 'N8 balayage manqué : saut direct à OVERDUE', [['issue', '2026-09-10'], ['scan', '2026-10-15']]),
        timeline('F-TL07', 'N12 règlement en deux temps', [['issue', '2026-09-10'], ['alloc', '2026-09-10', 'P1', 5000, '2026-09-10'], ['alloc', '2026-09-12', 'P2', 6501, '2026-09-12']]),
        timeline('F-TL08', 'N15 reversal partiel : aucun événement de facture', [['issue', '2026-09-10'], ['alloc', '2026-09-10', 'P1', 5000, '2026-09-10'], ['reverse', '2026-09-11', 0, 2000]]),
        timeline('F-TL09', 'L9 gel PAID puis annulation après l’échéance : recalcul en avant, cycle +1 une fois',
                 [['issue', '2026-09-10'], ['alloc', '2026-09-20', 'P1', 11501, '2026-09-20'], ['scan', '2026-10-05'], ['reverse', '2026-10-06', 0, 1501]]),
        timeline('F-TL10', 'L10 déjà OVERDUE : cycle +1, aucun événement OVERDUE',
                 [['issue', '2026-10-05'], ['alloc', '2026-10-06', 'P1', 11501, '2026-10-06'], ['reverse', '2026-10-07', 0, 1501]]),
        timeline('F-TL11', 'L11 PARTIALLY_PAID vers UNPAID : cycle inchangé',
                 [['issue', '2026-10-05'], ['alloc', '2026-10-06', 'P1', 5000, '2026-10-06'], ['reverse', '2026-10-07', 0, 5000]]),
        timeline('F-TL12', 'L8 horloge en retard : aucun recul', [['issue', '2026-09-10'], ['scan', '2026-10-15'], ['scan', '2026-09-01'], ['scan', '2026-09-25']]),
        timeline('F-TL13', 'L1 due_soon_days = 0', [['issue', '2026-09-10'], ['scan', '2026-09-29'], ['scan', DUE]], due_soon_days=0),
        timeline('F-TL14', 'L3 émission le jour de l’échéance (issue = due)', [['issue', DUE]], total=100, issue=DUE),
        timeline('F-TL15', 'L7 année bissextile', [['issue', '2028-02-01'], ['scan', '2028-02-21'], ['scan', '2028-02-22'], ['scan', '2028-02-29'], ['scan', '2028-03-01']],
                 issue='2028-02-01', due='2028-02-29'),
        timeline('F-TL16', 'V7 ordre A puis B (dates de valeur J+5 puis J+2)',
                 [['issue', '2026-09-10'], ['alloc', '2026-09-20', 'A', 6000, '2026-09-25'], ['alloc', '2026-09-21', 'B', 5501, '2026-09-22']]),
        timeline('F-TL17', 'V7 ordre B puis A',
                 [['issue', '2026-09-10'], ['alloc', '2026-09-20', 'B', 5501, '2026-09-22'], ['alloc', '2026-09-21', 'A', 6000, '2026-09-25']]),
        timeline('F-TL18', 'V7 reversal du paiement le plus tardif puis nouveau règlement',
                 [['issue', '2026-09-10'], ['alloc', '2026-09-20', 'A', 6000, '2026-09-25'], ['alloc', '2026-09-21', 'B', 5501, '2026-09-22'],
                  ['reverse', '2026-09-26', 0, 6000], ['alloc', '2026-09-27', 'C', 6000, '2026-09-27']]),
    ]
    inv = lambda **k: dict(dict(lifecycle='DRAFT', total=11501, paid=0, settlement='UNPAID', lines=[10000, 1501], issue='2026-09-01', due=DUE), **k)   # noqa: E731
    pay = dict(customer='C1', currency='EUR', amount=20000, allocated=0, status='RECEIVED')
    invs = {'F1': dict(customer='C1', currency='EUR', lifecycle='ISSUED', total=11501, paid=0), 'F2': dict(customer='C1', currency='EUR', lifecycle='OVERDUE', total=9000, paid=0),
            'X': dict(customer='C2', currency='EUR', lifecycle='ISSUED', total=500, paid=0), 'U': dict(customer='C1', currency='USD', lifecycle='ISSUED', total=500, paid=0),
            'D': dict(customer='C1', currency='EUR', lifecycle='DRAFT', total=500, paid=0), 'PD': dict(customer='C1', currency='EUR', lifecycle='ISSUED', total=500, paid=500)}
    led = [{'id': 'L0', 'payment': 'P', 'invoice': 'F1', 'amount': 5000, 'reverses': None}, {'id': 'L1', 'payment': 'P', 'invoice': 'F2', 'amount': 3000, 'reverses': None},
           {'id': 'L2', 'payment': 'P', 'invoice': 'F1', 'amount': -2000, 'reverses': 'L0'}]
    now = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)
    today = R.date(2026, 9, 10)
    checks = [
        ('issue', lambda: R.check_issue(inv(lifecycle='ISSUED'), True, 'ACTIVE'), 'INVALID_TRANSITION'),
        ('issue', lambda: R.check_issue(inv(lifecycle='DRAFT', lines=[]), True, 'ACTIVE'), 'INVOICE_EMPTY'),
        ('issue', lambda: R.check_issue(inv(total=0, lines=[0]), True, 'ACTIVE'), 'INVOICE_TOTAL_MUST_BE_POSITIVE'),
        ('issue', lambda: R.check_issue(inv(), True, 'INACTIVE'), 'CUSTOMER_INACTIVE'),
        ('issue', lambda: R.check_issue(inv(), True, 'ARCHIVED'), 'CUSTOMER_ARCHIVED'),
        ('issue', lambda: R.check_issue(inv(), False, 'ARCHIVED'), 'ORG_NOT_ACTIVE'),
        ('issue', lambda: R.check_issue(inv(), True, 'ACTIVE'), None),
        ('cancel', lambda: R.check_cancel(inv(lifecycle='ISSUED')), 'INVALID_TRANSITION'),
        ('void', lambda: R.check_void(inv(lifecycle='DRAFT'), False), 'INVALID_TRANSITION'),
        ('void', lambda: R.check_void(inv(lifecycle='ISSUED', paid=1, settlement='PARTIALLY_PAID'), True), 'INVOICE_HAS_PAYMENTS'),
        ('void', lambda: R.check_void(inv(lifecycle='ISSUED'), True), 'INVOICE_HAS_OPEN_DISPUTE'),
        ('void', lambda: R.check_void(inv(lifecycle='OVERDUE'), False), None),
        ('open_dispute', lambda: R.check_open_dispute(inv(lifecycle='ISSUED', paid=11501, settlement='PAID'), False, 'x', None), 'DISPUTE_INVOICE_NOT_DISPUTABLE'),
        ('open_dispute', lambda: R.check_open_dispute(inv(lifecycle='ISSUED'), True, 'x', None), 'DISPUTE_ALREADY_OPEN'),
        ('open_dispute', lambda: R.check_open_dispute(inv(lifecycle='ISSUED'), False, '  ', None), 'DISPUTE_REASON_REQUIRED'),
        ('open_dispute', lambda: R.check_open_dispute(inv(lifecycle='ISSUED'), False, 'x', 11502), 'DISPUTE_AMOUNT_EXCEEDS_TOTAL'),
        ('open_dispute', lambda: R.check_open_dispute(inv(lifecycle='ISSUED'), False, 'x', 11501), None),
        ('create_payment', lambda: R.check_create_payment('ARCHIVED', 5000, 'EUR', 'EUR', today, now, today, now, False), 'CUSTOMER_ARCHIVED'),
        ('create_payment', lambda: R.check_create_payment('INACTIVE', 5000, 'EUR', 'EUR', today, now, today, now, False), None),
        ('create_payment', lambda: R.check_create_payment('ACTIVE', 0, 'EUR', 'EUR', today, now, today, now, False), 'PAYMENT_AMOUNT_INVALID'),
        ('create_payment', lambda: R.check_create_payment('ACTIVE', 5, 'USD', 'EUR', today, now, today, now, False), 'PAYMENT_CURRENCY_MISMATCH'),
        ('create_payment', lambda: R.check_create_payment('ACTIVE', 5, 'EUR', 'EUR', R.date(2026, 9, 11), now, today, now, False), 'PAYMENT_DATE_IN_FUTURE'),
        ('create_payment', lambda: R.check_create_payment('ACTIVE', 5, 'EUR', 'EUR', today, now.replace(hour=10), today, now, False), 'PAYMENT_DATE_IN_FUTURE'),
        ('create_payment', lambda: R.check_create_payment('ACTIVE', 5, 'EUR', 'EUR', today, now, today, now, True), 'PAYMENT_DUPLICATE_REFERENCE'),
        ('allocate', lambda: R.check_allocation(False, pay, invs, [('F1', 1)]), 'ORG_NOT_ACTIVE'),
        ('allocate', lambda: R.check_allocation(True, dict(pay, status='REVERSED'), invs, [('F1', 1)]), 'ALLOCATION_PAYMENT_REVERSED'),
        ('allocate', lambda: R.check_allocation(True, pay, invs, [('D', 1)]), 'ALLOCATION_INVOICE_NOT_PAYABLE'),
        ('allocate', lambda: R.check_allocation(True, pay, invs, [('X', 1)]), 'ALLOCATION_CUSTOMER_MISMATCH'),
        ('allocate', lambda: R.check_allocation(True, pay, invs, [('U', 1)]), 'ALLOCATION_CURRENCY_MISMATCH'),
        ('allocate', lambda: R.check_allocation(True, pay, invs, [('PD', 1)]), 'ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING'),
        ('allocate', lambda: R.check_allocation(True, pay, invs, [('F1', 11502)]), 'ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING'),
        ('allocate', lambda: R.check_allocation(True, pay, invs, [('F1', 11501), ('F2', 8500)]), 'ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE'),
        ('allocate', lambda: R.check_allocation(True, pay, invs, [('F1', 11501), ('F2', 8499)]), None),
        ('allocate', lambda: R.check_allocation(True, pay, invs, [('F1', 1), ('F2', 1), ('D', 1)]), 'ALLOCATION_INVOICE_NOT_PAYABLE'),
        ('reverse_allocation', lambda: R.check_reverse_allocation(True, led, 'L0', 3001, 'x'), 'REVERSAL_EXCEEDS_ORIGINAL'),
        ('reverse_allocation', lambda: R.check_reverse_allocation(True, led, 'L0', 3000, 'x'), None),
        ('reverse_allocation', lambda: R.check_reverse_allocation(True, led, 'L2', 1, 'x'), 'REVERSAL_EXCEEDS_ORIGINAL'),
        ('reverse_allocation', lambda: R.check_reverse_allocation(True, led, 'L0', 1, ' '), 'REVERSAL_REASON_REQUIRED'),
        ('reverse_payment', lambda: R.check_reverse_payment(True, 'REVERSED', 'x'), 'PAYMENT_ALREADY_REVERSED'),
        ('reverse_payment', lambda: R.check_reverse_payment(True, 'ALLOCATED', ''), 'PAYMENT_REVERSAL_REASON_REQUIRED'),
        ('reverse_payment', lambda: R.check_reverse_payment(False, 'ALLOCATED', 'x'), 'ORG_NOT_ACTIVE'),
        ('reverse_payment', lambda: R.check_reverse_payment(True, 'RECEIVED', 'x'), None),
    ]
    g['checks'] = [{'id': 'F-CK%02d' % i, 'rule': name, 'expect': fn()} for i, (name, fn, _hand) in enumerate(checks)]
    g['reverse_payment_effects'] = [
        {'id': 'F-RP01', 'input': {'ledger': led, 'payment': 'P'}, 'expect': R.reverse_payment_effects(led, 'P')},
        {'id': 'F-RP02', 'input': {'ledger': [{'id': 'L0', 'payment': 'P', 'invoice': 'F1', 'amount': 2000, 'reverses': None},
                                              {'id': 'L1', 'payment': 'P', 'invoice': 'F1', 'amount': 1000, 'reverses': None}], 'payment': 'P'},
         'expect': R.reverse_payment_effects([{'id': 'L0', 'payment': 'P', 'invoice': 'F1', 'amount': 2000, 'reverses': None},
                                              {'id': 'L1', 'payment': 'P', 'invoice': 'F1', 'amount': 1000, 'reverses': None}], 'P')},
        {'id': 'F-RP03', 'input': {'ledger': [], 'payment': 'P'}, 'expect': R.reverse_payment_effects([], 'P')},
    ]
    g['_hand_checks'] = [hand for _, _, hand in checks]          # oracle écrit à la main, comparé au résultat de la référence par les tests
    return g


def render(g):
    public = {k: v for k, v in g.items() if not k.startswith('_')}
    return json.dumps(public, sort_keys=True, indent=1, ensure_ascii=False, default=str) + '\n'


if __name__ == '__main__':
    text = render(build())
    if '--check' in sys.argv:
        with io.open(OUT, encoding='utf-8', newline='') as f:
            current = f.read().replace('\r\n', '\n')
        sys.exit(0 if current == text else 'golden_finance.json est en dérive : relancer gen_golden_finance.py')
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print('écrit', OUT, len(text), 'octets')
