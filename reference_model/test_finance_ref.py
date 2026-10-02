"""Tests de la référence financière : son oracle est ÉCRIT À LA MAIN à partir des textes gelés et du document du Domain (cas N, C, L), jamais copié de sa sortie.

Ce fichier ne touche pas aux 35 tests de `test_models.py`. Usage : python -m unittest test_finance_ref
"""
import ast
import io
import os
import random
import unittest
from datetime import date, datetime, timezone

import finance_ref as R
import gen_golden_finance as G
import verqia_models as V   # la référence existante : sert UNIQUEMENT à recouper les faits qu'elle consomme

HERE = os.path.dirname(os.path.abspath(__file__))
D = date.fromisoformat


class TestMoneyAndSettlement(unittest.TestCase):
    def test_line_rounding_half_up(self):
        for q, p, want in [(20000, 5000, 10000), (5000, 3001, 1501), (1, 4999, 0), (1, 5000, 1), (10000, 7, 7), (5, 1000, 1), (4, 1000, 0)]:
            self.assertEqual(R.line_total(q, p), want, (q, p))
        self.assertEqual(R.line_total(20000, 5000) + R.line_total(5000, 3001), 11501)          # N1

    def test_settlement_branches(self):
        for paid, total, want in [(0, 100, 'UNPAID'), (1, 100, 'PARTIALLY_PAID'), (99, 100, 'PARTIALLY_PAID'), (100, 100, 'PAID'), (1, 1, 'PAID')]:
            self.assertEqual(R.settlement_of(paid, total), want)
        for bad in [(101, 100), (-1, 100)]:
            with self.assertRaises(ValueError):
                R.settlement_of(*bad)
        self.assertEqual(R.settlement_of(0, 0), 'UNPAID')      # une facture à zéro n'est jamais PAID : total > 0 est exigé pour PAID

    def test_payment_status(self):
        self.assertEqual(R.payment_status_of(100, 0, False), 'RECEIVED')
        self.assertEqual(R.payment_status_of(100, 40, False), 'PARTIALLY_ALLOCATED')
        self.assertEqual(R.payment_status_of(100, 100, False), 'ALLOCATED')
        self.assertEqual(R.payment_status_of(100, 0, True), 'REVERSED')
        self.assertEqual(R.payment_available(100, 0, 'REVERSED'), 0)
        self.assertEqual(R.payment_available(100, 40, 'PARTIALLY_ALLOCATED'), 60)


class TestDue(unittest.TestCase):
    DUE = D('2026-09-30')

    def test_position_grid(self):
        cases = [(7, '2026-09-22', 'NOT_YET'), (7, '2026-09-23', 'DUE_SOON'), (7, '2026-09-29', 'DUE_SOON'), (7, '2026-09-30', 'DUE'), (7, '2026-10-01', 'OVERDUE'),
                 (0, '2026-09-29', 'NOT_YET'), (0, '2026-09-30', 'DUE'),                                            # L1 : DUE_SOON inatteignable
                 (1, '2026-09-28', 'NOT_YET'), (1, '2026-09-29', 'DUE_SOON'),
                 (90, '2026-07-01', 'NOT_YET'), (90, '2026-07-02', 'DUE_SOON')]
        for dsd, today, want in cases:
            self.assertEqual(R.position_of(self.DUE, D(today), dsd), want, (dsd, today))

    def test_lateness_is_a_function_of_dates(self):
        self.assertEqual((R.days_late(self.DUE, D('2026-09-30')), R.days_late(self.DUE, D('2026-10-03'))), (0, 3))
        self.assertEqual(R.days_to_due(self.DUE, D('2026-09-25')), 5)
        self.assertFalse(R.is_late(self.DUE, D('2026-09-30')))
        self.assertTrue(R.is_late(self.DUE, D('2026-10-01')))

    def test_local_date(self):
        for instant, tz, want in [('2026-09-29T23:30:00+00:00', 'Pacific/Auckland', '2026-09-30'),                # L4
                                  ('2026-10-01T05:00:00+00:00', 'America/Los_Angeles', '2026-09-30'),              # L5
                                  ('2026-03-28T23:30:00+00:00', 'Europe/Paris', '2026-03-29'),
                                  ('2026-03-29T21:59:00+00:00', 'Europe/Paris', '2026-03-29'),                     # dernière minute du 29 en heure d'été
                                  ('2026-03-29T22:30:00+00:00', 'Europe/Paris', '2026-03-30')]:
            self.assertEqual(R.business_date(datetime.fromisoformat(instant), tz).isoformat(), want, (instant, tz))
        with self.assertRaises(ValueError):
            R.business_date(datetime(2026, 9, 30, 9, 0), 'UTC')

    def test_same_as_existing_reference_local_date(self):
        tz = R.ZoneInfo('Europe/Paris')
        for instant in ['2026-03-28T23:30:00+00:00', '2026-10-25T00:30:00+00:00', '2026-10-25T01:30:00+00:00']:
            i = datetime.fromisoformat(instant)
            self.assertEqual(R.business_date(i, 'Europe/Paris'), V.local_date(i, tz))


class TestDispute(unittest.TestCase):
    def test_collectible_and_disputed_part(self):
        for out, dispute, coll, part in [(6501, None, 6501, 0), (6501, {'amount': None}, 0, 6501), (6501, {'amount': 4000}, 2501, 4000),
                                         (501, {'amount': 4000}, 0, 501), (6501, {'amount': 6501}, 0, 6501), (0, {'amount': None}, 0, 0)]:
            self.assertEqual((R.collectible_of(out, dispute), R.disputed_part_of(out, dispute)), (coll, part), (out, dispute))

    def test_agrees_with_the_existing_reference_that_consumes_these_facts(self):
        """`reserve_unallocated` reçoit `disputed` et rend `coll` ; sans non-alloué, `coll` doit être le montant recouvrable."""
        for out, dispute in [(6501, None), (6501, {'amount': None}), (6501, {'amount': 4000}), (501, {'amount': 4000}), (6501, {'amount': 6501})]:
            inv = {'id': 'x', 'due': D('2026-09-30'), 'outstanding': out, 'disputed': R.disputed_part_of(out, dispute)}
            coll, disp, reserved = V.reserve_unallocated([inv], 0)['x']
            self.assertEqual((coll, disp, reserved), (R.collectible_of(out, dispute), R.disputed_part_of(out, dispute), 0), (out, dispute))

    def test_unallocated_of_agrees_off_reversed_payments(self):
        for amount, allocated in [(100, 0), (100, 40), (100, 100)]:
            self.assertEqual(V.unallocated_of({'amount': amount, 'allocated': allocated}), R.payment_available(amount, allocated, 'RECEIVED'))


class TestLedger(unittest.TestCase):
    LED = [{'id': 'L0', 'payment': 'P', 'invoice': 'F1', 'amount': 5000, 'reverses': None},
           {'id': 'L1', 'payment': 'P', 'invoice': 'F2', 'amount': 3000, 'reverses': None},
           {'id': 'L2', 'payment': 'P', 'invoice': 'F1', 'amount': -2000, 'reverses': 'L0'}]

    def test_sums_and_reversible(self):
        self.assertEqual((R.net_to_invoice(self.LED, 'F1'), R.net_to_invoice(self.LED, 'F2'), R.net_of_payment(self.LED, 'P')), (3000, 3000, 6000))
        self.assertEqual((R.reversible_of(self.LED, 'L0'), R.reversible_of(self.LED, 'L1'), R.reversible_of(self.LED, 'L2')), (3000, 3000, 0))
        self.assertEqual([r['id'] for r in R.active_allocations(self.LED, 'P')], ['L0', 'L1'])

    def test_reverse_payment_effects(self):
        e = R.reverse_payment_effects(self.LED, 'P')
        self.assertEqual((e['reversals'], e['per_invoice'], e['count']), ([('L0', 'F1', 3000), ('L1', 'F2', 3000)], {'F1': -3000, 'F2': -3000}, 2))
        same = [{'id': 'L0', 'payment': 'P', 'invoice': 'F1', 'amount': 2000, 'reverses': None}, {'id': 'L1', 'payment': 'P', 'invoice': 'F1', 'amount': 1000, 'reverses': None}]
        e = R.reverse_payment_effects(same, 'P')
        self.assertEqual((e['per_invoice'], e['count']), ({'F1': -3000}, 2))        # L19 : deux allocations, un seul delta
        self.assertEqual(R.reverse_payment_effects([], 'P')['count'], 0)              # L18


class TestTimelines(unittest.TestCase):
    F1 = dict(total=11501, issue='2026-09-01', due='2026-09-30', due_soon_days=7)

    def run_(self, ops, **over):
        a = dict(self.F1, **over)
        return R.run_timeline(a['total'], a['issue'], a['due'], a['due_soon_days'], ops)

    def test_issue_and_catch_up_is_a_single_jump(self):
        r = self.run_([['issue', '2026-09-10']])
        self.assertEqual((r['lifecycle'], r['events'], r['cycle']), ('ISSUED', [['2026-09-10', 'INVOICE_ISSUED']], 0))                                          # N2
        r = self.run_([['issue', '2026-09-25']])
        self.assertEqual((r['lifecycle'], r['events'], r['cycle']), ('DUE_SOON', [['2026-09-25', 'INVOICE_ISSUED'], ['2026-09-25', 'INVOICE_DUE_SOON']], 0))      # N3
        r = self.run_([['issue', '2026-10-05']])
        self.assertEqual((r['lifecycle'], r['events'], r['cycle']), ('OVERDUE', [['2026-10-05', 'INVOICE_ISSUED'], ['2026-10-05', 'INVOICE_OVERDUE']], 1))        # N4
        r = self.run_([['issue', '2026-09-30']])
        self.assertEqual((r['lifecycle'], r['events'][-1]), ('DUE', ['2026-09-30', 'INVOICE_DUE']))                                                            # N5

    def test_scans(self):
        r = self.run_([['issue', '2026-09-10'], ['scan', '2026-09-22'], ['scan', '2026-09-23'], ['scan', '2026-09-30'], ['scan', '2026-10-01'], ['scan', '2026-10-02']])
        self.assertEqual(r['outcomes'], ['OK', 'SKIPPED', 'OK', 'OK', 'OK', 'SKIPPED'])                                                                         # N6, N7
        self.assertEqual([e[1] for e in r['events']], ['INVOICE_ISSUED', 'INVOICE_DUE_SOON', 'INVOICE_DUE', 'INVOICE_OVERDUE'])
        self.assertEqual((r['lifecycle'], r['cycle']), ('OVERDUE', 1))
        r = self.run_([['issue', '2026-09-10'], ['scan', '2026-10-15']])
        self.assertEqual(([e[1] for e in r['events']], r['cycle']), (['INVOICE_ISSUED', 'INVOICE_OVERDUE'], 1))                                                   # N8

    def test_partial_settlement_then_paid(self):
        r = self.run_([['issue', '2026-09-10'], ['alloc', '2026-09-10', 'P1', 5000, '2026-09-10'], ['alloc', '2026-09-12', 'P2', 6501, '2026-09-12']])
        self.assertEqual((r['settlement'], r['paid'], r['settled_on'], r['lifecycle']), ('PAID', 11501, '2026-09-12', 'ISSUED'))                                 # N12
        self.assertEqual([e[1] for e in r['events']], ['INVOICE_ISSUED', 'INVOICE_PARTIALLY_PAID', 'INVOICE_PAID'])

    def test_partial_reversal_emits_no_invoice_event(self):
        r = self.run_([['issue', '2026-09-10'], ['alloc', '2026-09-10', 'P1', 5000, '2026-09-10'], ['reverse', '2026-09-11', 0, 2000]])
        self.assertEqual((r['settlement'], r['paid']), ('PARTIALLY_PAID', 3000))                                                                                 # N15
        self.assertEqual([e[1] for e in r['events']], ['INVOICE_ISSUED', 'INVOICE_PARTIALLY_PAID'])

    def test_paid_frozen_then_reverted_after_due_recomputes_forward_once(self):
        r = self.run_([['issue', '2026-09-10'], ['alloc', '2026-09-20', 'P1', 11501, '2026-09-20'], ['scan', '2026-10-05'], ['reverse', '2026-10-06', 0, 1501]])
        self.assertEqual(r['outcomes'], ['OK', 'OK', 'SKIPPED', 'OK'])                                                                                           # C7 : le scan ne touche pas une facture PAID
        self.assertEqual([e[1] for e in r['events']], ['INVOICE_ISSUED', 'INVOICE_PAID', 'INVOICE_SETTLEMENT_REVERTED', 'INVOICE_OVERDUE'])                     # L9
        self.assertEqual((r['lifecycle'], r['cycle'], r['settlement'], r['settled_on']), ('OVERDUE', 1, 'PARTIALLY_PAID', None))

    def test_already_overdue_gets_the_cycle_without_a_transition(self):
        r = self.run_([['issue', '2026-10-05'], ['alloc', '2026-10-06', 'P1', 11501, '2026-10-06'], ['reverse', '2026-10-07', 0, 1501]])
        self.assertEqual(r['events'][-1], ['2026-10-07', 'INVOICE_SETTLEMENT_REVERTED'])                                                                        # L10
        self.assertEqual((r['lifecycle'], r['cycle']), ('OVERDUE', 2))

    def test_partial_to_unpaid_does_not_increment_the_cycle(self):
        r = self.run_([['issue', '2026-10-05'], ['alloc', '2026-10-06', 'P1', 5000, '2026-10-06'], ['reverse', '2026-10-07', 0, 5000]])
        self.assertEqual((r['settlement'], r['cycle'], r['events'][-1][1]), ('UNPAID', 1, 'INVOICE_SETTLEMENT_REVERTED'))                                          # L11

    def test_clock_regression_never_goes_backwards(self):
        r = self.run_([['issue', '2026-09-10'], ['scan', '2026-10-15'], ['scan', '2026-09-01'], ['scan', '2026-09-25']])
        self.assertEqual((r['lifecycle'], r['cycle'], r['outcomes']), ('OVERDUE', 1, ['OK', 'OK', 'SKIPPED', 'SKIPPED']))                                          # L8

    def test_due_soon_days_zero(self):
        r = self.run_([['issue', '2026-09-10'], ['scan', '2026-09-29'], ['scan', '2026-09-30']], due_soon_days=0)
        self.assertEqual(([e[1] for e in r['events']], r['outcomes']), (['INVOICE_ISSUED', 'INVOICE_DUE'], ['OK', 'SKIPPED', 'OK']))                              # L1

    def test_issue_on_due_date(self):
        r = self.run_([['issue', '2026-09-30']], total=100, issue='2026-09-30')
        self.assertEqual([e[1] for e in r['events']], ['INVOICE_ISSUED', 'INVOICE_DUE'])                                                                         # L3

    def test_leap_year_and_month_boundary(self):
        r = self.run_([['issue', '2028-02-01'], ['scan', '2028-02-21'], ['scan', '2028-02-22'], ['scan', '2028-02-29'], ['scan', '2028-03-01']], issue='2028-02-01', due='2028-02-29')
        self.assertEqual(r['outcomes'], ['OK', 'SKIPPED', 'OK', 'OK', 'OK'])                                                                                      # L7
        self.assertEqual([e[1] for e in r['events']], ['INVOICE_ISSUED', 'INVOICE_DUE_SOON', 'INVOICE_DUE', 'INVOICE_OVERDUE'])
        r = self.run_([['issue', '2026-02-01'], ['scan', '2026-02-23'], ['scan', '2026-02-24']], issue='2026-02-01', due='2026-03-03')
        self.assertEqual(r['outcomes'], ['OK', 'SKIPPED', 'OK'])

    def test_settled_on_does_not_depend_on_the_order_of_allocation(self):
        """V7 : A (valeur J+5) et B (valeur J+2), dans les deux ordres, et après un reversal du plus tardif."""
        ab = self.run_([['issue', '2026-09-10'], ['alloc', '2026-09-20', 'A', 6000, '2026-09-25'], ['alloc', '2026-09-21', 'B', 5501, '2026-09-22']])
        ba = self.run_([['issue', '2026-09-10'], ['alloc', '2026-09-20', 'B', 5501, '2026-09-22'], ['alloc', '2026-09-21', 'A', 6000, '2026-09-25']])
        self.assertEqual((ab['settled_on'], ba['settled_on']), ('2026-09-25', '2026-09-25'))
        self.assertEqual((ab['settlement'], ba['settlement'], ab['paid'], ba['paid']), ('PAID', 'PAID', 11501, 11501))
        self.assertEqual([e[1] for e in ab['events']], [e[1] for e in ba['events']])
        redone = self.run_([['issue', '2026-09-10'], ['alloc', '2026-09-20', 'A', 6000, '2026-09-25'], ['alloc', '2026-09-21', 'B', 5501, '2026-09-22'],
                            ['reverse', '2026-09-26', 0, 6000], ['alloc', '2026-09-27', 'C', 6000, '2026-09-27']])
        self.assertEqual(redone['settled_on'], '2026-09-27')

    def test_settled_on_is_the_latest_value_date_for_every_permutation(self):
        rnd = random.Random(20260921)
        for _ in range(200):
            n = rnd.randint(2, 5)
            parts = [rnd.randint(1, 3000) for _ in range(n)]
            total = sum(parts)
            dates = [date(2026, 9, 1 + rnd.randint(0, 25)) for _ in range(n)]
            order = list(range(n))
            rnd.shuffle(order)
            ops = [['issue', '2026-08-30']] + [['alloc', '2026-09-28', 'P%d' % i, parts[i], dates[i].isoformat()] for i in order]
            r = R.run_timeline(total, '2026-08-01', '2026-10-30', 7, ops)
            self.assertEqual((r['settlement'], r['settled_on']), ('PAID', max(dates).isoformat()))

    def test_random_timelines_keep_every_state_invariant(self):
        """Le référentiel doit être cohérent avec lui-même : IF1 à IF7, monotonie du cycle de vie, cycle jamais décroissant, un événement par changement."""
        rnd = random.Random(7)
        order = R.LIFECYCLE_ORDER
        for _ in range(300):
            total = rnd.randint(1, 5000)
            ops, day, alloc_count, paid, reversible = [['issue', '2026-08-25']], date(2026, 8, 25), 0, 0, []
            for _step in range(rnd.randint(1, 12)):
                day = day.fromordinal(day.toordinal() + rnd.randint(0, 9))
                kind = rnd.choice(['scan', 'alloc', 'reverse'])
                if kind == 'alloc' and total - paid > 0:
                    amt = rnd.randint(1, total - paid)
                    ops.append(['alloc', day.isoformat(), 'P%d' % alloc_count, amt, (day.replace(day=max(1, day.day - 1))).isoformat()])
                    reversible.append([alloc_count, amt])
                    alloc_count += 1
                    paid += amt
                elif kind == 'reverse' and any(x[1] > 0 for x in reversible):
                    idx = rnd.choice([i for i, x in enumerate(reversible) if x[1] > 0])
                    amt = rnd.randint(1, reversible[idx][1])
                    ops.append(['reverse', day.isoformat(), idx, amt])
                    reversible[idx][1] -= amt
                    paid -= amt
                else:
                    ops.append(['scan', day.isoformat()])
            r = R.run_timeline(total, '2026-08-01', '2026-09-15', 7, ops)
            self.assertTrue(0 <= r['paid'] <= total)
            self.assertEqual(r['settlement'], R.settlement_of(r['paid'], total))
            self.assertEqual(r['settled_on'] is not None, r['settlement'] == 'PAID')
            self.assertEqual(r['paid'], paid)
            self.assertIn(r['lifecycle'], order)
            names = [e[1] for e in r['events']]
            self.assertEqual(names[0], 'INVOICE_ISSUED')
            lifecycle_events = [n for n in names if n in ('INVOICE_DUE_SOON', 'INVOICE_DUE', 'INVOICE_OVERDUE')]
            ranks = [order.index(n[len('INVOICE_'):]) for n in lifecycle_events]
            self.assertEqual(ranks, sorted(set(ranks)), 'le cycle de vie ne recule ni ne répète un état')
            self.assertGreaterEqual(r['cycle'], names.count('INVOICE_OVERDUE'))       # le cycle de la règle (b) s'ajoute aux entrées en OVERDUE (cas L9 à L11)


class TestChecks(unittest.TestCase):
    def test_every_golden_check_matches_the_hand_written_oracle(self):
        built = G.build()
        got = [c['expect'] for c in built['checks']]
        self.assertEqual(got, built['_hand_checks'])
        self.assertEqual(len(got), 42)

    def test_all_business_codes_of_the_slice_are_produced(self):
        produced = {c['expect'] for c in G.build()['checks'] if c['expect']}
        for code in ['INVALID_TRANSITION', 'INVOICE_EMPTY', 'INVOICE_TOTAL_MUST_BE_POSITIVE', 'CUSTOMER_INACTIVE', 'CUSTOMER_ARCHIVED', 'ORG_NOT_ACTIVE',
                     'INVOICE_HAS_PAYMENTS', 'INVOICE_HAS_OPEN_DISPUTE', 'DISPUTE_INVOICE_NOT_DISPUTABLE', 'DISPUTE_ALREADY_OPEN', 'DISPUTE_REASON_REQUIRED',
                     'DISPUTE_AMOUNT_EXCEEDS_TOTAL', 'PAYMENT_AMOUNT_INVALID', 'PAYMENT_CURRENCY_MISMATCH', 'PAYMENT_DATE_IN_FUTURE', 'PAYMENT_DUPLICATE_REFERENCE',
                     'ALLOCATION_PAYMENT_REVERSED', 'ALLOCATION_INVOICE_NOT_PAYABLE', 'ALLOCATION_CUSTOMER_MISMATCH', 'ALLOCATION_CURRENCY_MISMATCH',
                     'ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING', 'ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE', 'REVERSAL_EXCEEDS_ORIGINAL', 'REVERSAL_REASON_REQUIRED',
                     'PAYMENT_ALREADY_REVERSED', 'PAYMENT_REVERSAL_REASON_REQUIRED']:
            self.assertIn(code, produced, code)


class TestGoldenAndIndependence(unittest.TestCase):
    def test_golden_file_is_up_to_date(self):
        with io.open(os.path.join(HERE, 'golden_finance.json'), encoding='utf-8', newline='') as f:
            self.assertEqual(f.read().replace('\r\n', '\n'), G.render(G.build()))

    def test_reference_imports_only_the_standard_library(self):
        """Indépendance : la référence n'importe ni `verqia`, ni le Domain, ni `verqia_models`."""
        with io.open(os.path.join(HERE, 'finance_ref.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
        self.assertEqual(modules, {'datetime', 'zoneinfo'})

    def test_reference_uses_no_float_no_division_no_clock(self):
        with io.open(os.path.join(HERE, 'finance_ref.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, ast.Div)
            if isinstance(node, ast.Constant):
                self.assertNotIsInstance(node.value, float)
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, ('now', 'today', 'utcnow', 'time'))
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, ('float', 'random', 'time'))


if __name__ == '__main__':
    unittest.main()
