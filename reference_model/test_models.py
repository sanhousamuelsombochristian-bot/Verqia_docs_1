"""Tests de propriétés et tests d'or du modèle de référence. Lancement : python -m unittest -v"""
import itertools
import json
import os
import random
import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP

import verqia_models as m

HERE = os.path.dirname(os.path.abspath(__file__))
C = 1_000_000


def golden():
    with open(os.path.join(HERE, 'golden_cases.json'), encoding='utf-8') as f:
        return json.load(f)


# Les tests exigent que golden_cases.json existe : python gen_golden.py (une seule fois, puis versionné).


class TestGolden(unittest.TestCase):
    def test_risk(self):
        for g in golden()['risk']:
            r = m.risk_evaluate('org-1', g['name'], g['previous_level'], *g['inputs'])
            self.assertEqual((r['score'], r['level'], r['input_hash']), (g['score'], g['level'], g['input_hash']), g['name'])
            self.assertEqual(r['factors'], g['factors'], g['name'])

    def test_priority(self):
        for g in golden()['priority']:
            r = m.prio_evaluate('org-1', g['name'], g['previous_level'], *g['inputs'],
                                promise_or_hold=g['promise_or_hold'], dispute_no_collectible=g['dispute_no_collectible'],
                                reconciliation_pending=g['reconciliation_pending'])
            self.assertEqual((r['rank_score'], r['level'], r['caps'], r['signals'], r['input_hash']),
                             (g['rank_score'], g['level'], g['caps'], g['signals'], g['input_hash']), g['name'])

    def test_expected_values_stated_in_the_documents(self):
        g = golden()
        self.assertEqual([(x['score'], x['level']) for x in g['risk']],
                         [(6, 'LOW'), (53, 'HIGH'), (98, 'CRITICAL'), (2, 'LOW'), (41, 'MEDIUM')])
        self.assertEqual([(x['rank_score'], x['level']) for x in g['priority'][:4]],
                         [(81, 'CRITICAL'), (6, 'NONE'), (28, 'WATCH'), (66, 'PRIORITY')])
        c = g['cashflow']
        self.assertEqual(c['C1 non echue BASE']['lines'][0]['weighted'], 450_000)
        self.assertEqual(c['C3 non echue PESSIMISTIC']['lines'][0]['date'], '2026-10-31')
        self.assertEqual(c['C8 66 jours de retard HIGH']['lines'][0]['weighted'], 206_250)
        self.assertEqual(c['C9 non alloue 200 000 (FIFO)']['reserved_minor'], 200_000)
        self.assertEqual(sum(l['amount'] for l in c['C9 non alloue 200 000 (FIFO)']['lines']), 600_000)
        self.assertEqual(c['C10 non alloue couvre tout']['lines'], [])

    def test_file_is_reproduced_exactly_by_the_model(self):
        # le fichier d'or est la spécification : le modèle doit le reproduire à l'identique, sans le réécrire
        import gen_golden
        self.assertEqual(gen_golden.to_jsonable(gen_golden.build_golden()), golden())


class TestRisk(unittest.TestCase):
    def score(self, **kw):
        base = dict(D=0, n=5, L=400, M=10, B=0, Eo=0, C=C, R=0, T=0)
        base.update(kw)
        return m.risk_score(m.risk_points(base['D'], base['n'], base['L'], base['M'], base['B'], base['Eo'], base['C'], base['R'], base['T']))

    def test_maximum_is_exactly_100(self):
        self.assertEqual(self.score(D=61, n=3, L=1000, M=30, B=3, Eo=10 ** 9, R=2, T=10), 100)

    def test_bounds(self):
        for D, n, L, M, B, Eo, R, T in itertools.product([0, 5, 40, 90], [0, 3, 12], [0, 500, 1000], [-3, 0, 30, 60],
                                                         [0, 2, 9], [0, C, 10 ** 8], [0, 4], [None, -5, 0, 10, 40]):
            s = self.score(D=D, n=n, L=L, M=M, B=B, Eo=Eo, R=R, T=T)
            self.assertTrue(0 <= s <= 100)

    def test_monotone(self):
        for key, values in [('D', range(0, 91)), ('L', range(0, 1001, 25)), ('M', range(0, 61)), ('B', range(0, 7)),
                            ('Eo', range(0, 2 * C, C // 8)), ('R', range(0, 5)), ('T', range(0, 30))]:
            prev = -1
            for v in values:
                s = self.score(**{key: v})
                self.assertGreaterEqual(s, prev, (key, v))
                prev = s

    def test_insufficient_history_contributes_zero(self):
        a = m.risk_points(0, 2, 1000, 60, 0, 0, C, 0, 0)
        self.assertEqual((a['history_late_pts'], a['history_delay_pts'], a['confidence']), (0, 0, 'LOW'))

    def test_hysteresis_reduces_level_changes(self):
        rnd = random.Random(7)
        for _ in range(200):
            scores = [rnd.choice([44, 45, 46, 47, 48, 49, 50, 51, 52, 53]) for _ in range(40)]
            prev, changes_h = None, 0
            for s in scores:
                lv = m.stabilise(s, prev, m.RISK_THRESHOLDS)
                changes_h += prev is not None and lv != prev
                prev = lv
            raw = [m.level_index(s, m.RISK_THRESHOLDS) for s in scores]
            changes_raw = sum(1 for a, b in zip(raw, raw[1:]) if a != b)
            self.assertLessEqual(changes_h, changes_raw)

    def test_documented_hysteresis_example(self):
        seq = [44, 46, 49, 51, 48, 47, 49, 50, 46, 45, 44]
        prev, out = None, ''
        for s in seq:
            prev = m.stabilise(s, prev, m.RISK_THRESHOLDS)
            out += m.RISK_LEVELS[prev][0]
        self.assertEqual(out, 'MMMHHHHHMMM')

    def test_hash_stable_inside_a_bucket_and_distinct_across_buckets(self):
        h = lambda D: m.risk_evaluate('o', 'c', None, D, 5, 400, 10, 0, 0, C, 0, 0)['input_hash']
        self.assertEqual(h(17), h(18))            # même tranche 16-30
        self.assertNotEqual(h(15), h(16))         # tranches différentes
        self.assertNotEqual(m.risk_evaluate('o', 'c', 1, 17, 5, 400, 10, 0, 0, C, 0, 0)['input_hash'],
                            m.risk_evaluate('o', 'c', 2, 17, 5, 400, 10, 0, 0, C, 0, 0)['input_hash'])  # niveau précédent inclus

    def test_snapshot_content_depends_only_on_normalized_inputs(self):
        a = m.risk_evaluate('o', 'c', None, 17, 5, 400, 10, 0, 0, C, 0, 0)
        b = m.risk_evaluate('o', 'c', None, 18, 5, 400, 10, 0, 0, C, 0, 0)
        self.assertEqual(a['input_hash'], b['input_hash'])
        self.assertEqual(a['factors'], b['factors'])
        self.assertEqual((a['score'], a['level']), (b['score'], b['level']))


class TestPriority(unittest.TestCase):
    def test_bounds_and_maximum(self):
        best = 0
        for A, Dd, risk, since, overdue in itertools.product([0, C // 2, 10 ** 9], [0, 3, 12, 25, 60], list(m.RISK_PTS),
                                                             [None, 0, 6, 12], [True, False]):
            pts = m.prio_points(A, C, Dd if overdue else 0, 2 if not overdue else -Dd, risk, since, overdue)
            s = m.prio_score(pts)
            best = max(best, s)
            self.assertTrue(0 <= s <= m.PRIO_MAX_SCORE)
        self.assertEqual(best, m.PRIO_MAX_SCORE)

    def test_caps_applied_after_stabilisation_and_published_level_is_the_reference(self):
        # niveau publié précédent CRITICAL (4), score 85, promesse active -> publié WATCH
        lv, caps = m.prio_publish(85, 4, True, False)
        self.assertEqual((m.PRIO_LEVELS[lv], caps), ('WATCH', ['PROMISE_OR_HOLD']))
        # la promesse disparaît : le niveau précédent est le niveau PUBLIÉ (WATCH) ; le brut CRITICAL remonte aussitôt
        lv2, _ = m.prio_publish(85, lv, False, False)
        self.assertEqual(m.PRIO_LEVELS[lv2], 'CRITICAL')
        # litige : plafond ACTION
        lv3, caps3 = m.prio_publish(85, 4, False, True)
        self.assertEqual((m.PRIO_LEVELS[lv3], caps3), ('ACTION', ['DISPUTED']))

    def test_cap_never_raises_a_level(self):
        for score in range(0, 96):
            for prev in [None, 0, 1, 2, 3, 4]:
                raw = m.stabilise(score, prev, m.PRIO_THRESHOLDS)
                lv, _ = m.prio_publish(score, prev, True, True)
                self.assertLessEqual(lv, raw)
                self.assertLessEqual(lv, m.CAP_WATCH)

    def test_reconciliation_signal_never_changes_score_or_level(self):
        # RP23 : un paiement non alloué est un signal explicatif, sans effet sur le score ni sur le niveau
        for args in [(1_200_000, C, 20, -20, 'HIGH', 12, True), (50_000, C, 0, 2, 'LOW', None, False), (400_000, C, 5, -5, 'MEDIUM', 2, True)]:
            for prev in (None, 0, 2, 4):
                a = m.prio_evaluate('o', 'i', prev, *args)
                b = m.prio_evaluate('o', 'i', prev, *args, reconciliation_pending=True)
                self.assertEqual((a['rank_score'], a['level'], a['caps']), (b['rank_score'], b['level'], b['caps']))
                self.assertNotEqual(a['input_hash'], b['input_hash'])      # le signal fait partie du snapshot
                self.assertEqual(b['signals'], ['RECONCILIATION_PENDING'])
                self.assertEqual(a['signals'], [])

    def test_hash_includes_previous_published_level_and_caps(self):
        base = (1_200_000, C, 20, -20, 'HIGH', 12, True)
        h = lambda prev, **kw: m.prio_evaluate('o', 'i', prev, *base, **kw)['input_hash']
        self.assertNotEqual(h(1), h(2))
        self.assertNotEqual(h(1), h(1, promise_or_hold=True))


class TestCashflow(unittest.TestCase):
    def test_weighted_equals_decimal_round_half_up(self):
        rnd = random.Random(3)
        for _ in range(20000):
            amount = rnd.randint(0, 10 ** 9)
            p = rnd.randint(0, 10000)
            expected = int((Decimal(amount) * Decimal(p) / Decimal(10000)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            self.assertEqual(m.weighted(amount, p), expected)

    def test_probability_in_range_and_order_of_operations(self):
        for risk, scen, dod in itertools.product(list(m.P_RISK_BP), list(m.SCEN_ADJ_BP), [0, 10, 20, 45, 70, 200]):
            p = m.probability_bp(risk, scen, dod)
            self.assertTrue(0 <= p <= 10000)
        # clamp avant la décote : LOW + OPTIMISTIC = 10 200 -> 10 000
        self.assertEqual(m.probability_bp('LOW', 'OPTIMISTIC', 0), 10000)
        # CRITICAL + PESSIMISTIC = 3 500, puis décote 3 500 / 10 000
        self.assertEqual(m.probability_bp('CRITICAL', 'PESSIMISTIC', 200), 1225)
        # part contestée : floor(p / 2) ; MEDIUM, BASE, 10 jours de retard : p = 9 000, donc 4 500
        self.assertEqual(m.probability_bp('MEDIUM', 'BASE', 10) // 2, 4500)
        # au-delà de 15 jours de retard la décote s'applique avant la division par deux
        self.assertEqual(m.probability_bp('MEDIUM', 'BASE', 20), 8100)

    def rnd_invoices(self, rnd, n):
        return [{'id': 'I%02d' % i, 'due': date(2026, 9, 1) + timedelta(days=rnd.randint(0, 90)),
                 'outstanding': rnd.randint(1, 900_000), 'disputed': rnd.choice([0, 0, rnd.randint(0, 400_000)])} for i in range(n)]

    def test_conservation_per_invoice_and_per_customer(self):
        rnd = random.Random(11)
        as_of = date(2026, 10, 20)
        for _ in range(400):
            invs = self.rnd_invoices(rnd, rnd.randint(1, 6))
            unalloc = rnd.choice([0, rnd.randint(0, 2_000_000)])
            risk = rnd.choice(list(m.P_RISK_BP))
            scen = rnd.choice(list(m.SCEN_ADJ_BP))
            promises = {}
            if rnd.random() < 0.4:
                promises[invs[0]['id']] = (as_of + timedelta(days=rnd.randint(0, 20)), rnd.randint(1, 900_000))
            lines, reserved = m.customer_forecast(as_of, rnd.choice([7, 30, 90]), scen, invs, unalloc, risk, rnd.randint(0, 40), promises, rnd.randint(0, 3))
            total_out = sum(i['outstanding'] for i in invs)
            self.assertLessEqual(reserved, unalloc)
            self.assertLessEqual(reserved, total_out)
            self.assertLessEqual(sum(l['amount'] for l in lines) + reserved, total_out)
            for i in invs:
                self.assertLessEqual(sum(l['amount'] for l in lines if l['invoice'] == i['id']), i['outstanding'])
            if unalloc >= total_out:
                self.assertEqual(lines, [])
            for l in lines:
                self.assertNotEqual(l['category'], 'REALIZED')
                self.assertTrue(0 <= l['p_bp'] <= 10000)

    def test_unallocated_cash_is_never_forecast_a_second_time(self):
        inv = [{'id': 'I1', 'due': date(2026, 10, 10), 'outstanding': 300_000, 'disputed': 0},
               {'id': 'I2', 'due': date(2026, 10, 15), 'outstanding': 500_000, 'disputed': 0}]
        no_reserve, _ = m.customer_forecast(date(2026, 10, 20), 30, 'BASE', inv, 0, 'MEDIUM', 6)
        with_reserve, r = m.customer_forecast(date(2026, 10, 20), 30, 'BASE', inv, 200_000, 'MEDIUM', 6)
        self.assertEqual(sum(l['amount'] for l in no_reserve) - sum(l['amount'] for l in with_reserve), 200_000)
        self.assertEqual(r, 200_000)
        # FIFO : la réserve est prise sur la facture la plus ancienne
        self.assertEqual([l['amount'] for l in with_reserve if l['invoice'] == 'I1'], [100_000])

    def test_reserve_takes_collectible_before_disputed(self):
        out = m.reserve_unallocated([{'id': 'A', 'due': date(2026, 10, 1), 'outstanding': 500_000, 'disputed': 200_000}], 350_000)
        self.assertEqual(out['A'], (0, 150_000, 350_000))

    def test_deterministic_and_dates_inside_window(self):
        as_of = date(2026, 10, 20)
        inv = [{'id': 'I', 'due': date(2026, 10, 15), 'outstanding': 500_000, 'disputed': 0}]
        for scen in m.SCEN_ADJ_BP:
            a = m.customer_forecast(as_of, 30, scen, inv, 0, 'MEDIUM', 6)
            b = m.customer_forecast(as_of, 30, scen, inv, 0, 'MEDIUM', 6)
            self.assertEqual(a, b)
            for l in a[0]:
                if l['date']:
                    self.assertTrue(as_of <= l['date'] <= as_of + timedelta(days=30))

    def test_promotion_is_monotone(self):
        older = (date(2026, 10, 20), '2026-10-20T05:00')
        newer = (date(2026, 10, 21), '2026-10-21T05:00')
        self.assertTrue(m.promote_current(None, older))
        self.assertTrue(m.promote_current(older, newer))
        self.assertFalse(m.promote_current(newer, older))     # un run retardataire ne remplace pas un run plus récent
        self.assertFalse(m.promote_current(newer, newer))


class TestReconciliation(unittest.TestCase):
    """Collection V1.2 : le paiement non alloué est un signal à résoudre, pas une conclusion."""

    @staticmethod
    def pay(**k):
        base = dict(id='P1', customer='c1', currency='XOF', amount=100_000, allocated=0, status='RECEIVED',
                    value_date=date(2026, 10, 19), recorded=date(2026, 10, 19))
        base.update(k)
        return base

    INV = dict(id='A', customer='c1', currency='XOF', issue_date=date(2026, 10, 1), is_open=True)

    def test_golden_reconciliation_cases(self):
        for c in golden()['reconciliation']:
            if 'timezone' in c:
                continue                                                # cas à instants : test_golden_instant_cases
            inv = dict(c['invoice'], issue_date=date.fromisoformat(c['invoice']['issue_date']))
            pays = [dict(p, value_date=date.fromisoformat(p['value_date']), recorded=date.fromisoformat(p['recorded'])) for p in c['payments']]
            hol = frozenset(date.fromisoformat(h) for h in c['holidays'])
            for chk in c['checks']:
                r = m.reconciliation_state(inv, pays, date.fromisoformat(chk['as_of']), holidays=hol)
                self.assertEqual({k: r[k] for k in ('pending', 'pending_minor', 'payments', 'review_due', 'stale')},
                                 {k: chk[k] for k in ('pending', 'pending_minor', 'payments', 'review_due', 'stale')}, c['name'])

    def test_documented_dates(self):
        self.assertEqual(m.window_last_day(self.pay()), date(2026, 10, 22))            # 3 jours ouvrés après lundi 19
        self.assertEqual(m.window_last_day(self.pay(recorded=date(2026, 10, 23)), holidays={date(2026, 10, 26)}), date(2026, 10, 29))
        self.assertTrue(m.reconciliation_state(self.INV, [self.pay()], date(2026, 10, 22))['pending'])
        self.assertFalse(m.reconciliation_state(self.INV, [self.pay()], date(2026, 10, 23))['pending'])

    def test_business_day_arithmetic(self):
        rnd = random.Random(5)
        hol = {date(2026, 10, 26), date(2026, 11, 2)}
        for _ in range(500):
            d = date(2026, 9, 1) + timedelta(days=rnd.randint(0, 120))
            n = rnd.randint(0, 8)
            r = m.add_business_days(d, n, holidays=hol)
            self.assertGreaterEqual(r, d)
            if n:
                self.assertTrue(m.is_business_day(r, holidays=hol))
            k = sum(1 for i in range(1, (r - d).days + 1) if m.is_business_day(d + timedelta(days=i), holidays=hol))
            self.assertEqual(k, n)

    def test_no_presumption_all_candidates_are_held_equally(self):
        # exemple de la revue : deux factures ouvertes (100 000 et 500 000), 100 000 non alloués
        a = dict(self.INV, id='A')
        b = dict(self.INV, id='B', issue_date=date(2026, 10, 5))
        pays = [self.pay()]
        ra = m.reconciliation_state(a, pays, date(2026, 10, 20))
        rb = m.reconciliation_state(b, pays, date(2026, 10, 20))
        self.assertTrue(ra['pending'] and rb['pending'])              # aucune facture n'est choisie à la place de l'autre
        self.assertEqual(ra['pending_minor'], rb['pending_minor'])

    def test_barrier_never_outlives_its_window_and_never_exceeds_unallocated(self):
        rnd = random.Random(9)
        for _ in range(2000):
            pays = [self.pay(id='P%d' % i, amount=rnd.randint(1, 500_000), allocated=0, recorded=date(2026, 10, 1) + timedelta(days=rnd.randint(0, 20)),
                             value_date=date(2026, 10, 1) + timedelta(days=rnd.randint(0, 20)),
                             status=rnd.choice(['RECEIVED', 'PARTIALLY_ALLOCATED', 'ALLOCATED', 'REVERSED'])) for i in range(rnd.randint(0, 4))]
            for p in pays:
                p['allocated'] = rnd.randint(0, p['amount']) if p['status'] == 'PARTIALLY_ALLOCATED' else (p['amount'] if p['status'] == 'ALLOCATED' else 0)
            as_of = date(2026, 10, 1) + timedelta(days=rnd.randint(0, 40))
            r = m.reconciliation_state(self.INV, pays, as_of)
            by = {p['id']: p for p in pays}
            self.assertLessEqual(r['pending_minor'], sum(m.unallocated_of(p) for p in pays))
            for pid in r['payments']:
                self.assertTrue(as_of <= m.window_last_day(by[pid]))
                self.assertIn(by[pid]['status'], m.UNALLOCATED_STATUSES)
            for pid in r['stale']:
                self.assertTrue(as_of > m.window_last_day(by[pid]))
            self.assertFalse(set(r['payments']) & set(r['stale']))

    def test_time_only_lifts_the_barrier_and_allocation_never_raises_it(self):
        p = self.pay()
        prev = True
        for d in range(0, 12):
            cur = m.reconciliation_state(self.INV, [p], date(2026, 10, 19) + timedelta(days=d))['pending']
            self.assertTrue(prev or not cur)                          # une fois levée, la barrière ne revient pas avec le seul temps
            prev = cur
        more = m.reconciliation_state(self.INV, [dict(p, allocated=30_000, status='PARTIALLY_ALLOCATED')], date(2026, 10, 20))
        less = m.reconciliation_state(self.INV, [p], date(2026, 10, 20))
        self.assertLessEqual(more['pending_minor'], less['pending_minor'])


    # --- RN5 : fuseau, calendrier de l'organisation, minuit local, indépendance vis-à-vis de l'heure du job
    @staticmethod
    def utc(x):
        return datetime.fromisoformat(x.replace('Z', '+00:00'))

    def test_golden_instant_cases(self):
        found = 0
        for c in golden()['reconciliation']:
            if 'timezone' not in c:
                continue
            found += 1
            tz = ZoneInfo(c['timezone'])
            inv = dict(c['invoice'], issue_date=date.fromisoformat(c['invoice']['issue_date']))
            pays = [dict(p, value_date=date.fromisoformat(p['value_date']), created_at=self.utc(p['created_at'])) for p in c['payments']]
            hol = frozenset(date.fromisoformat(h) for h in c['holidays'])
            for p in pays:
                self.assertEqual(m.local_date(p['created_at'], tz).isoformat(), c['local_recorded'][p['id']], c['name'])
                self.assertEqual(m.add_business_days(m.local_date(p['created_at'], tz), 3, holidays=hol).isoformat(), c['window_last_day'][p['id']], c['name'])
                self.assertEqual(m.barrier_lifted_at(p['created_at'], tz, holidays=hol).strftime('%Y-%m-%dT%H:%M:%SZ'), c['barrier_lifted_at_utc'][p['id']], c['name'])
            for chk in c['checks']:
                now = self.utc(chk['now_utc'])
                r = m.reconciliation_state_at(inv, pays, now, tz, holidays=hol)
                self.assertEqual(m.local_date(now, tz).isoformat(), chk['local_date'], c['name'])
                self.assertEqual({k: r[k] for k in ('pending', 'pending_minor', 'payments', 'review_due', 'stale')},
                                 {k: chk[k] for k in ('pending', 'pending_minor', 'payments', 'review_due', 'stale')}, c['name'] + ' ' + chk['now_utc'])
        self.assertEqual(found, 4)

    def test_result_never_depends_on_the_hour_of_evaluation(self):
        # toutes les minutes d'une journée locale donnent le même résultat : le job horaire ne décide de rien
        for tzname in ('Europe/Paris', 'America/New_York', 'Asia/Kolkata', 'Pacific/Auckland'):
            tz = ZoneInfo(tzname)
            created = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
            pays = [self.pay(created_at=created)]
            for day in range(0, 10):
                d = m.local_date(created, tz) + timedelta(days=day)
                start = datetime.combine(d, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
                end = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
                seen = set()
                t = start
                while t < end:
                    r = m.reconciliation_state_at(self.INV, pays, t, tz)
                    seen.add((r['pending'], tuple(r['stale']), tuple(r['review_due'])))
                    t += timedelta(minutes=30)
                seen.add((lambda r: (r['pending'], tuple(r['stale']), tuple(r['review_due'])))(m.reconciliation_state_at(self.INV, pays, end - timedelta(seconds=1), tz)))
                self.assertEqual(len(seen), 1, (tzname, d))

    def test_barrier_lifts_exactly_at_the_next_local_midnight(self):
        for tzname in ('Europe/Paris', 'America/New_York', 'Asia/Kolkata'):
            tz = ZoneInfo(tzname)
            for h in (0, 5, 11, 17, 23):
                created = datetime(2026, 10, 21, h, 15, tzinfo=timezone.utc)
                pays = [self.pay(created_at=created)]
                lifted = m.barrier_lifted_at(created, tz)
                before = m.reconciliation_state_at(self.INV, pays, lifted - timedelta(seconds=1), tz)
                after = m.reconciliation_state_at(self.INV, pays, lifted, tz)
                self.assertTrue(before['pending'] and not before['stale'], (tzname, h))
                self.assertTrue(not after['pending'] and after['stale'] == ['P1'], (tzname, h))
                self.assertEqual(lifted.astimezone(tz).time(), datetime.min.time())

    def test_utc_date_is_never_used_and_naive_instants_are_refused(self):
        tz = ZoneInfo('Europe/Paris')
        created = datetime(2026, 10, 23, 22, 30, tzinfo=timezone.utc)      # vendredi UTC, samedi à Paris
        self.assertEqual(m.local_date(created, tz), date(2026, 10, 24))
        self.assertEqual(m.window_last_day({'recorded': m.local_date(created, tz)}), date(2026, 10, 28))
        ny = ZoneInfo('America/New_York')                                   # mardi 02:00 UTC = lundi 22:00 à New York
        late = datetime(2026, 10, 20, 2, 0, tzinfo=timezone.utc)
        self.assertEqual(m.window_last_day({'recorded': m.local_date(late, ny)}), date(2026, 10, 22))
        self.assertEqual(m.window_last_day({'recorded': late.date()}), date(2026, 10, 23))      # la date UTC donnerait un jour de trop
        self.assertNotEqual(m.reconciliation_state_at(self.INV, [self.pay(created_at=created)], datetime(2026, 10, 24, 12, tzinfo=timezone.utc), tz)['review_due'], ['P1'])
        with self.assertRaises(ValueError):
            m.local_date(datetime(2026, 10, 23, 22, 30), tz)


class TestIntegerHelpers(unittest.TestCase):
    def test_round_half_up_div_for_signed_sums(self):
        self.assertEqual(m.round_half_up_div(5, 2), 3)
        self.assertEqual(m.round_half_up_div(-5, 2), -2)    # -2,5 -> -2 (demi vers le haut)
        self.assertEqual(m.round_half_up_div(7, 3), 2)
        self.assertEqual(m.round_half_up_div(-7, 3), -2)


if __name__ == '__main__':
    unittest.main()
