"""Tests de la référence Risk : son oracle est ÉCRIT À LA MAIN à partir de `RISK_PRIORITY_CASHFLOW_V1.md` et de `RISK_DOMAIN_V1.md`
(cas RN, RC, RL), jamais copié de la sortie de `risk_ref`. Ce fichier ne touche pas aux 35 tests de `test_models.py` ni aux 31 de
`test_finance_ref.py`. Usage : python -m unittest test_risk_ref
"""
import ast
import io
import json
import os
import random
import unittest
from datetime import date, datetime, timedelta, timezone

import gen_golden_risk as G
import risk_ref as R
import verqia_models as V   # la référence existante (formule) : recoupement croisé UNIQUEMENT, jamais d'import inverse

HERE = os.path.dirname(os.path.abspath(__file__))
UTC = timezone.utc


def inv(is_open, is_late, days_late=0, outstanding=0):
    return {'is_open': is_open, 'is_late': is_late, 'days_late': days_late, 'outstanding_minor': outstanding}


def settled(delay, settled_on):
    return {'is_open': False, 'is_late': False, 'days_late': 0, 'outstanding_minor': 0,
            'settlement_delay_days': delay, 'settled_on': date.fromisoformat(settled_on)}


class TestPointsAndScore(unittest.TestCase):
    def test_delay_points_tranches(self):
        for D, want in [(0, 0), (1, 5), (7, 5), (8, 12), (15, 12), (16, 20), (30, 20), (31, 26), (60, 26), (61, 30), (200, 30)]:
            self.assertEqual(R.delay_points(D), want, D)

    def test_history_points_needs_the_minimum_sample(self):
        self.assertEqual(R.history_points(2, 999, 30), (0, 0))          # RL2 : n<3, historique ignoré
        self.assertEqual(R.history_points(3, 0, 0), (0, 0))
        self.assertEqual(R.history_points(3, 1000, 30), (15, 10))       # bornes maximales : L=100%, M>=30
        self.assertEqual(R.history_points(3, 999, 30), (14, 10))        # floor(999*15/1000) = 14

    def test_history_points_clamps_m_before_dividing(self):
        self.assertEqual(R.history_points(3, 500, 35)[1], R.history_points(3, 500, 30)[1])   # RL8 : M=35 plafonné à 30
        self.assertEqual(R.history_points(3, 500, -10)[1], 0)                                 # RL7 : M négatif -> 0 (max(M,0))

    def test_broken_and_reversed_points_cap(self):
        self.assertEqual([R.broken_points(b) for b in (0, 1, 2, 3, 10)], [0, 5, 10, 15, 15])
        self.assertEqual([R.reversed_points(r) for r in (0, 1, 2, 10)], [0, 5, 10, 10])

    def test_exposure_points(self):
        self.assertEqual(R.exposure_points(0, 0), 0)
        self.assertEqual(R.exposure_points(500000, 0), 0)               # RC4 : C<=0 -> 0, jamais une division par zéro
        self.assertEqual(R.exposure_points(1000000, 1000000), 15)
        self.assertEqual(R.exposure_points(2000000, 1000000), 15)       # plafonné

    def test_trend_points_none_and_non_positive_both_give_zero(self):
        for T in (None, -5, 0):
            self.assertEqual(R.trend_points(T), 0)
        self.assertEqual(R.trend_points(10), 5)
        self.assertEqual(R.trend_points(100), 5)                        # plafonné

    def test_confidence(self):
        self.assertEqual(R.confidence_of(2), 'LOW')
        self.assertEqual(R.confidence_of(3), 'HIGH')

    def test_score_maximum_is_exactly_100(self):
        pts = R.points_of(D=200, n=3, L=1000, M=30, B=10, Eo=10**9, C=1, R=10, T=100)
        self.assertEqual(R.risk_score(pts), 100)

    def test_score_never_exceeds_100_over_a_wide_random_grid(self):
        rnd = random.Random(1)
        for _ in range(500):
            D, n, L, M, B, Eo, C, Rv, T = (rnd.randint(0, 300), rnd.randint(0, 20), rnd.randint(0, 1000), rnd.randint(-60, 60),
                                           rnd.randint(0, 20), rnd.randint(0, 5_000_000), rnd.choice([0, 1, 1000000]),
                                           rnd.randint(0, 20), rnd.choice([None, rnd.randint(-50, 200)]))
            pts = R.points_of(D, n, L, M, B, Eo, C, Rv, T)
            self.assertGreaterEqual(R.risk_score(pts), 0)
            self.assertLessEqual(R.risk_score(pts), 100)


class TestMonotonicity(unittest.TestCase):
    def test_each_factor_is_monotone_in_its_own_raw_input(self):
        self.assertLessEqual(R.delay_points(5), R.delay_points(50))
        for L in (0, 500, 999):
            self.assertLessEqual(R.history_points(3, L, 15)[0], R.history_points(3, L + 1, 15)[0])
        for M in (-5, 10, 29):
            self.assertLessEqual(R.history_points(3, 500, M)[1], R.history_points(3, 500, M + 1)[1])
        self.assertLessEqual(R.broken_points(2), R.broken_points(3))
        self.assertLessEqual(R.exposure_points(400000, 1000000), R.exposure_points(500000, 1000000))
        self.assertLessEqual(R.reversed_points(1), R.reversed_points(2))
        self.assertLessEqual(R.trend_points(5), R.trend_points(6))


class TestLevelsAndHysteresis(unittest.TestCase):
    def test_thresholds(self):
        for s, want in [(0, 'LOW'), (24, 'LOW'), (25, 'MEDIUM'), (49, 'MEDIUM'), (50, 'HIGH'), (74, 'HIGH'), (75, 'CRITICAL'), (100, 'CRITICAL')]:
            self.assertEqual(R.LEVELS[R.level_index(s)], want, s)

    def test_documented_example_gives_exactly_two_changes(self):
        """§1.3 : scores 44,46,49,51,48,47,49,50,46,45,44 avec hystérésis -> MMMHHHHHMMM (2 changements)."""
        sequence = [44, 46, 49, 51, 48, 47, 49, 50, 46, 45, 44]
        levels, prev = [], None
        for s in sequence:
            idx = R.stabilise(s, R.LEVELS.index(prev) if prev is not None else None)
            prev = R.LEVELS[idx]
            levels.append(prev[0])
        self.assertEqual(''.join(levels), 'MMMHHHHHMMM')

    def test_descent_requires_strictly_below_the_threshold_with_the_margin(self):
        """RL10 : la comparaison est `score + 3 <` seuil ; égal ne suffit pas à rester en haut."""
        self.assertEqual(R.stabilise(47, R.LEVELS.index('HIGH')), R.LEVELS.index('HIGH'))     # 47+3=50=seuil : reste HIGH
        self.assertEqual(R.stabilise(46, R.LEVELS.index('HIGH')), R.LEVELS.index('MEDIUM'))   # 46+3=49<50 : descend

    def test_no_hysteresis_on_the_first_calculation(self):
        self.assertEqual(R.stabilise(30, None), R.level_index(30))

    def test_hysteresis_never_produces_more_changes_than_the_raw_level(self):
        """Repris à l'identique de `test_models.TestRisk.test_hysteresis_reduces_level_changes` (déjà validée, 25 tests) :
        la propriété est démontrée pour des scores qui oscillent autour d'UN seuil, pas pour un tirage sur tout `[0,100]`
        (qui peut faire franchir plusieurs seuils à la fois et n'est pas ce que §7 promet)."""
        rnd = random.Random(2)
        for _ in range(200):
            scores = [rnd.choice([44, 45, 46, 47, 48, 49, 50, 51, 52, 53]) for _ in range(30)]
            raw_changes = sum(1 for a, b in zip(scores, scores[1:]) if R.level_index(a) != R.level_index(b))
            prev, changes = None, 0
            for s in scores:
                idx = R.stabilise(s, R.LEVELS.index(prev) if prev is not None else None)
                lvl = R.LEVELS[idx]
                if lvl != prev and prev is not None:
                    changes += 1
                prev = lvl
            self.assertLessEqual(changes, raw_changes)


class TestGoldenScoreMatchesTheExistingReference(unittest.TestCase):
    """G1 à G5 (`golden_cases.json`) : `risk_ref`, transcrite indépendamment, doit reproduire EXACTEMENT ce que `verqia_models`
    (déjà testé, 25 tests) et le document gelé donnent. Deux transcriptions indépendantes qui s'accordent."""

    def test_the_five_golden_cases(self):
        with io.open(os.path.join(HERE, 'golden_cases.json'), encoding='utf-8') as f:
            golden = json.load(f)['risk']
        self.assertEqual(len(golden), 5)
        for c in golden:
            D, n, L, M, B, Eo, C, Rv, T = c['inputs']
            out = R.score_and_level(D, n, L, M, B, Eo, C, Rv, T, c['previous_level'])
            self.assertEqual((out['score'], out['level']), (c['score'], c['level']), c['name'])
            self.assertEqual(out['factors'], c['factors'], c['name'])

    def test_agrees_with_verqia_models_over_a_random_grid(self):
        rnd = random.Random(3)
        for _ in range(300):
            D, n, L, M, B, Eo, C, Rv, T = (rnd.randint(0, 200), rnd.randint(0, 15), rnd.randint(0, 1000), rnd.randint(-30, 60),
                                           rnd.randint(0, 10), rnd.randint(0, 3_000_000), rnd.choice([0, 500000, 1000000]),
                                           rnd.randint(0, 10), rnd.choice([None, rnd.randint(-20, 150)]))
            previous_level = rnd.choice([None] + R.LEVELS)
            got = R.score_and_level(D, n, L, M, B, Eo, C, Rv, T, previous_level)
            previous_index = R.LEVELS.index(previous_level) if previous_level is not None else None   # verqia_models attend un INDICE, pas un nom
            want = V.risk_evaluate('org', 'cust', previous_index, D, n, L, M, B, Eo, C, Rv, T)
            self.assertEqual((got['score'], got['level'], got['factors']), (want['score'], want['level'], want['factors']),
                             (D, n, L, M, B, Eo, C, Rv, T, previous_level))


class TestAggregation(unittest.TestCase):
    def test_d_and_eo_only_count_open_and_late_invoices(self):
        invoices = [inv(True, True, 5, 100), inv(True, True, 20, 300), inv(True, False, 0, 50), inv(False, True, 999, 999)]
        self.assertEqual(R.aggregate_D_Eo(invoices), (20, 400))

    def test_d_and_eo_are_zero_without_a_late_open_invoice(self):
        self.assertEqual(R.aggregate_D_Eo([inv(True, False, 0, 100)]), (0, 0))
        self.assertEqual(R.aggregate_D_Eo([]), (0, 0))

    def test_n_l_m_below_the_minimum_sample(self):
        self.assertEqual(R.aggregate_n_L_M([settled(5, '2026-08-01'), settled(-2, '2026-07-01')]), (2, None, None))
        self.assertEqual(R.aggregate_n_L_M([]), (0, None, None))

    def test_n_l_m_at_the_minimum_sample(self):
        n, L, M = R.aggregate_n_L_M([settled(5, '2026-08-01'), settled(-2, '2026-07-01'), settled(10, '2026-06-01')])
        self.assertEqual(n, 3)
        self.assertEqual(L, 666)                                        # floor(1000 * 2/3) : 2 factures en retard (5, 10) sur 3
        self.assertEqual(M, 4)                                          # floor((2*13+3)/6) = floor(29/6) = 4

    def test_avg_days_to_pay_rounds_half_up_and_allows_negative(self):
        self.assertIsNone(R.avg_days_to_pay([]))
        self.assertEqual(R.avg_days_to_pay([1]), 1)
        self.assertEqual(R.avg_days_to_pay([1, 2]), 2)                  # (2*3+2)/4 = 2 (demi vers le haut)
        self.assertEqual(R.avg_days_to_pay([-3, -1]), -2)               # (2*-4+2)/4 = -1.5 -> floor(-6/4)= -2 (demi vers le haut négatif)

    def test_t_needs_at_least_two_settled_invoices_in_each_90_day_window(self):
        today = date(2026, 9, 22)
        recent2 = [settled(4, '2026-08-01'), settled(6, '2026-07-01')]
        prior2 = [settled(10, '2026-05-25'), settled(20, '2026-04-25')]
        self.assertEqual(R.aggregate_T(recent2 + prior2, today), -10)   # avg(4,6)=5, avg(10,20)=15, 5-15=-10
        self.assertIsNone(R.aggregate_T(recent2[:1] + prior2, today))
        self.assertIsNone(R.aggregate_T(recent2 + prior2[:1], today))
        self.assertIsNone(R.aggregate_T([], today))

    def test_t_window_boundaries_are_inclusive_and_exclusive_correctly(self):
        """0 et 90 jours appartiennent à la fenêtre récente ; 91 et 180 à la précédente ; 181 n'appartient à aucune."""
        today = date(2026, 9, 22)
        on_boundary_recent = settled(1, (today - timedelta(days=90)).isoformat())
        on_boundary_prior_low = settled(1, (today - timedelta(days=91)).isoformat())
        on_boundary_prior_high = settled(1, (today - timedelta(days=180)).isoformat())
        outside = settled(1, (today - timedelta(days=181)).isoformat())
        two_recent = [settled(1, today.isoformat()), on_boundary_recent]
        two_prior = [on_boundary_prior_low, on_boundary_prior_high]
        self.assertIsNotNone(R.aggregate_T(two_recent + two_prior, today))
        self.assertIsNone(R.aggregate_T(two_recent + [outside, on_boundary_prior_low], today))

    def test_b_and_r_are_plain_counts(self):
        self.assertEqual(R.aggregate_B([{'broken_at': date(2026, 1, 1)}] * 3), 3)
        self.assertEqual(R.aggregate_R([]), 0)


class TestEligibility(unittest.TestCase):
    def test_only_has_ever_issued_decides(self):
        self.assertTrue(R.is_eligible(True))
        self.assertFalse(R.is_eligible(False))


class TestDecision(unittest.TestCase):
    PARAMS = {'critical_amount_minor': 1000000, 'timezone': 'UTC'}
    NOW = datetime(2026, 9, 22, 9, 0, tzinfo=UTC)

    def published(self, o):
        return {'level': o['level'], 'normalized_inputs': o['normalized_inputs']}

    def test_ineligible_customer_gets_no_profile(self):
        out = R.evaluate_risk(None, self.PARAMS, False, [inv(True, True, 999, 999999)], [], [], [], self.NOW)
        self.assertEqual(out, {'eligible': False, 'score': None, 'level': None, 'factors': None, 'normalized_inputs': None, 'changed': False, 'event': None})

    def test_first_calculation_creates_a_profile_without_an_event(self):
        """DV2-7 : `RiskChanged.from_level` est un `str` non optionnel ; la première décision n'émet rien."""
        out = R.evaluate_risk(None, self.PARAMS, True, [inv(True, True, 3, 100000)], [], [], [], self.NOW)
        self.assertTrue(out['eligible'])
        self.assertTrue(out['changed'])
        self.assertIsNone(out['event'])
        self.assertEqual(out['level'], 'LOW')

    def test_second_calculation_still_changes_because_previous_level_is_now_populated(self):
        """RP14 : `previous_level` fait partie des entrées normalisées ; il passe de `None` à une valeur réelle entre le
        premier et le second calcul, donc le second calcul change les entrées normalisées même à faits strictement identiques."""
        invoices = [inv(True, True, 3, 100000)]
        o1 = R.evaluate_risk(None, self.PARAMS, True, invoices, [], [], [], self.NOW)
        o2 = R.evaluate_risk(self.published(o1), self.PARAMS, True, invoices, [], [], [], self.NOW)
        self.assertTrue(o2['changed'])
        self.assertIsNone(o2['event'])                         # le niveau ne change pas, seule la métadonnée previous_level change
        self.assertEqual(o2['level'], o1['level'])

    def test_third_calculation_reaches_the_steady_state(self):
        invoices = [inv(True, True, 3, 100000)]
        o1 = R.evaluate_risk(None, self.PARAMS, True, invoices, [], [], [], self.NOW)
        o2 = R.evaluate_risk(self.published(o1), self.PARAMS, True, invoices, [], [], [], self.NOW)
        o3 = R.evaluate_risk(self.published(o2), self.PARAMS, True, invoices, [], [], [], self.NOW)
        self.assertFalse(o3['changed'])
        self.assertIsNone(o3['event'])
        self.assertEqual(o3['normalized_inputs'], o2['normalized_inputs'])

    def test_a_level_change_emits_the_event_with_the_right_direction(self):
        invoices = [inv(True, True, 3, 100000)]
        o1 = R.evaluate_risk(None, self.PARAMS, True, invoices, [], [], [], self.NOW)
        o2 = R.evaluate_risk(self.published(o1), self.PARAMS, True, invoices, [], [], [], self.NOW)
        worse = [inv(True, True, 65, 2000000)]
        o3 = R.evaluate_risk(self.published(o2), self.PARAMS, True, worse, [], [], [], self.NOW)
        self.assertTrue(o3['changed'])
        self.assertEqual(o3['event'], {'from_level': o2['level'], 'to_level': o3['level'], 'score': o3['score']})
        self.assertNotEqual(o2['level'], o3['level'])

    def test_previous_level_keeps_changing_the_snapshot_until_it_stabilises_across_two_calls(self):
        """`previous_level` fait partie des entrées normalisées (RP14) : après un aller-retour léger -> lourd -> léger, le
        niveau publié peut redevenir identique à celui d'avant (o3.level == o1.level), mais `changed` reste `True` tant que
        `previous_level` lui-même n'a pas cessé de bouger d'un appel à l'autre — il faut DEUX appels consécutifs à faits ET
        niveau publié stables pour atteindre `changed=False`, pas un seul. C'est une conséquence non triviale de RP14,
        démontrée ici avant tout code du Domain (c'est précisément le rôle de cette référence, RD17)."""
        light, heavy = [inv(True, True, 3, 100000)], [inv(True, True, 65, 2000000)]
        o1 = R.evaluate_risk(None, self.PARAMS, True, light, [], [], [], self.NOW)
        o2 = R.evaluate_risk(self.published(o1), self.PARAMS, True, heavy, [], [], [], self.NOW)
        o3 = R.evaluate_risk(self.published(o2), self.PARAMS, True, light, [], [], [], self.NOW)
        o4 = R.evaluate_risk(self.published(o3), self.PARAMS, True, light, [], [], [], self.NOW)
        o5 = R.evaluate_risk(self.published(o4), self.PARAMS, True, light, [], [], [], self.NOW)
        self.assertEqual((o1['level'], o3['level'], o4['level']), ('LOW', 'LOW', 'LOW'))     # le niveau publié revient bien à LOW dès o3
        self.assertTrue(o4['changed'])                                                       # mais previous_level (MEDIUM chez o3) vient encore de changer
        self.assertFalse(o5['changed'])                                                       # deux appels de suite à previous_level stable : régime atteint

    def test_business_date_uses_the_organisation_timezone(self):
        far_east = dict(self.PARAMS, timezone='Pacific/Auckland')
        out = R.evaluate_risk(None, far_east, True, [], [], [], [], datetime(2026, 9, 21, 23, 30, tzinfo=UTC))
        self.assertTrue(out['eligible'])   # ne lève pas : la conversion de fuseau a eu lieu

    def test_a_naive_instant_is_refused(self):
        with self.assertRaises(ValueError):
            R.evaluate_risk(None, self.PARAMS, True, [], [], [], [], datetime(2026, 9, 22, 9, 0))


class TestGoldenFileAndIndependence(unittest.TestCase):
    def test_golden_file_is_up_to_date(self):
        with io.open(os.path.join(HERE, 'golden_risk.json'), encoding='utf-8', newline='') as f:
            self.assertEqual(f.read().replace('\r\n', '\n'), G.render(G.build()))

    def test_reference_imports_only_the_standard_library(self):
        with io.open(os.path.join(HERE, 'risk_ref.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or '').split('.')[0])
        self.assertEqual(modules, {'datetime', 'zoneinfo'})

    def test_reference_uses_no_float_no_division_no_clock(self):
        with io.open(os.path.join(HERE, 'risk_ref.py'), encoding='utf-8') as f:
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
