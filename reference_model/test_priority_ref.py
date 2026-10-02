"""Tests de `priority_ref.py` : oracles dérivés à la main de `RISK_PRIORITY_CASHFLOW_V1.md` §3 et
`PRIORITY_DOMAIN_V1.md` (jamais copiés depuis la sortie du module), plus vérification d'indépendance (AST) et
comparaison avec `golden_priority.json` / `golden_cases.json['priority']` (P1-P7)."""
import ast
import io
import json
import os
import unittest

import priority_ref as R
from gen_golden_priority import build as build_golden, render as render_golden

HERE = os.path.dirname(os.path.abspath(__file__))
C = 1_000_000


class TestPointsAndScore(unittest.TestCase):
    def test_amount_points_brackets(self):
        cases = [(0, 0), (100_000, 3), (500_000, 15), (999_999, 29), (1_000_000, 30), (2_000_000, 30)]
        for A, expected in cases:
            self.assertEqual(R.amount_points(A, C), expected, A)

    def test_amount_points_zero_critical_is_not_an_error(self):
        self.assertEqual(R.amount_points(500_000, 0), 0)
        self.assertEqual(R.amount_points(500_000, -1), 0)

    def test_delay_points_brackets(self):
        cases = [(0, 0), (1, 8), (7, 8), (8, 16), (15, 16), (16, 24), (30, 24), (31, 30), (60, 30), (61, 30)]
        for Dd, expected in cases:
            self.assertEqual(R.delay_points(Dd), expected, Dd)

    def test_due_points_brackets(self):
        cases = [(-1, 0), (0, 5), (3, 5), (4, 2), (7, 2), (8, 0), (100, 0)]
        for Dj, expected in cases:
            self.assertEqual(R.due_points(Dj), expected, Dj)

    def test_attention_points(self):
        cases = [(None, 0), (0, 0), (4, 0), (5, 5), (9, 5), (10, 10), (100, 10)]
        for S, expected in cases:
            self.assertEqual(R.attention_points(S), expected, S)

    def test_risk_points_known_and_unknown(self):
        self.assertEqual(R.RISK_PTS['LOW'], 0)
        self.assertEqual(R.RISK_PTS['MEDIUM'], 8)
        self.assertEqual(R.RISK_PTS['HIGH'], 17)
        self.assertEqual(R.RISK_PTS['CRITICAL'], 25)
        self.assertEqual(R.RISK_PTS[None], 5)

    def test_overdue_excludes_delay_and_due_and_attention_is_only_when_overdue(self):
        pts_overdue = R.points_of(A=0, C=C, overdue=True, Dd=5, Dj=2, risk_level=None, S=10)
        self.assertGreater(pts_overdue['delay_pts'], 0)
        self.assertEqual(pts_overdue['due_pts'], 0)
        self.assertGreater(pts_overdue['attention_pts'], 0)
        pts_not_overdue = R.points_of(A=0, C=C, overdue=False, Dd=5, Dj=2, risk_level=None, S=10)
        self.assertEqual(pts_not_overdue['delay_pts'], 0)
        self.assertGreater(pts_not_overdue['due_pts'], 0)
        self.assertEqual(pts_not_overdue['attention_pts'], 0)

    def test_maximum_score_reaches_exactly_95(self):
        """§3.3 : 30(montant)+30(retard)+25(risque)+0(échéance, exclue par retard)+10(attention) = 95."""
        pts = R.points_of(A=10**7, C=1, overdue=True, Dd=1000, Dj=0, risk_level='CRITICAL', S=100)
        self.assertEqual(R.rank_score(pts), 95)

    def test_score_never_negative(self):
        pts = R.points_of(A=0, C=C, overdue=False, Dd=0, Dj=1000, risk_level='LOW', S=None)
        self.assertGreaterEqual(R.rank_score(pts), 0)


class TestLevelsAndHysteresis(unittest.TestCase):
    def test_thresholds(self):
        cases = [(0, 'NONE'), (19, 'NONE'), (20, 'WATCH'), (39, 'WATCH'), (40, 'ACTION'), (59, 'ACTION'),
                 (60, 'PRIORITY'), (79, 'PRIORITY'), (80, 'CRITICAL'), (95, 'CRITICAL')]
        for score, level in cases:
            self.assertEqual(R.LEVELS[R.level_index(score)], level, score)

    def test_first_calculation_has_no_previous_level(self):
        self.assertEqual(R.stabilise(35, None), R.level_index(35))

    def test_rise_is_immediate(self):
        self.assertEqual(R.stabilise(65, R.LEVELS.index('ACTION')), R.level_index(65))

    def test_fall_needs_strictly_below_threshold_with_margin(self):
        # seuil PRIORITY = 60, previous = PRIORITY (index 3)
        self.assertEqual(R.stabilise(57, 3), 3)   # 57+3=60 == seuil : RESTE (comme RL10/Risk)
        self.assertEqual(R.stabilise(56, 3), 2)   # 56+3=59 < 60 : descend

    def test_documented_style_example_two_changes(self):
        with io.open(os.path.join(HERE, 'golden_priority.json'), encoding='utf-8') as f:
            g = json.load(f)['hysteresis_example']
        levels, prev = [], None
        for s in g['input']['scores']:
            idx = R.stabilise(s, R.LEVELS.index(prev) if prev is not None else None)
            prev = R.LEVELS[idx]
            levels.append(prev)
        self.assertEqual(levels, g['expect']['levels'])
        changes = sum(1 for a, b in zip([None] + levels, levels) if a != b) - 1
        self.assertEqual(changes, g['expect']['changes'])
        self.assertEqual(changes, 2)


class TestCapsAndDerivations(unittest.TestCase):
    def test_no_cap_reaches_raw_critical(self):
        idx, caps = R.apply_caps(4, False, False)
        self.assertEqual((R.LEVELS[idx], caps), ('CRITICAL', []))

    def test_promise_or_hold_caps_at_watch(self):
        for promise, hold in [(True, False), (False, True), (True, True)]:
            idx, caps = R.apply_caps(4, promise or hold, False)
            self.assertEqual((R.LEVELS[idx], caps), ('WATCH', ['PROMISE_OR_HOLD']))

    def test_dispute_caps_at_action(self):
        idx, caps = R.apply_caps(4, False, True)
        self.assertEqual((R.LEVELS[idx], caps), ('ACTION', ['DISPUTED']))

    def test_both_caps_active_the_lowest_wins(self):
        idx, caps = R.apply_caps(4, True, True)
        self.assertEqual(R.LEVELS[idx], 'WATCH')                # WATCH(1) < ACTION(2)
        self.assertEqual(set(caps), {'PROMISE_OR_HOLD', 'DISPUTED'})

    def test_a_cap_never_raises_a_level(self):
        """Un plafond ne relève jamais : un niveau stabilisé déjà sous le plafond reste inchangé — même si la
        CONDITION du plafond est active et donc listée dans `caps` (signal explicatif, comme `verqia_models.prio_publish`
        déjà gelé : la présence dans `caps` signale que la condition est vraie, pas qu'elle a contraint le résultat)."""
        idx, caps = R.apply_caps(0, True, False)                 # stabilisé = NONE (0), plafond WATCH (1)
        self.assertEqual(R.LEVELS[idx], 'NONE')                   # inchangé : le plafond n'a rien contraint
        self.assertEqual(caps, ['PROMISE_OR_HOLD'])                # mais la condition reste signalée

    def test_dispute_no_collectible_derivation(self):
        self.assertTrue(R.dispute_no_collectible_of(True, 0))
        self.assertFalse(R.dispute_no_collectible_of(True, 1))
        self.assertFalse(R.dispute_no_collectible_of(False, 0))
        self.assertFalse(R.dispute_no_collectible_of(False, 500))


class TestEligibility(unittest.TestCase):
    def test_three_states(self):
        self.assertEqual(R.eligibility_of(is_draft=True, is_open=False), 'draft')
        self.assertEqual(R.eligibility_of(is_draft=True, is_open=True), 'draft')     # DRAFT l'emporte, quel que soit is_open
        self.assertEqual(R.eligibility_of(is_draft=False, is_open=False), 'closed')
        self.assertEqual(R.eligibility_of(is_draft=False, is_open=True), 'active')


BASE_KW = dict(is_draft=False, is_open=True, critical_amount_minor=C, outstanding_minor=400_000, is_late=True,
              days_late=5, days_to_due=-5, collectible_minor=400_000, has_open_dispute=False, risk_level='MEDIUM',
              days_since_last_action=2, active_promise=False, hold_active=False, reconciliation_pending=False)


class TestDecision(unittest.TestCase):
    def test_pn8_first_call_creation_no_event(self):
        out = R.evaluate_priority(None, **BASE_KW)
        self.assertTrue(out['eligible'])
        self.assertTrue(out['changed'])
        self.assertIsNone(out['event'])

    def test_pn9_non_open_invoice_is_none_closed(self):
        kw = dict(BASE_KW, is_open=False)
        out = R.evaluate_priority(None, **kw)
        self.assertTrue(out['is_closed'])
        self.assertEqual(out['level'], 'NONE')
        self.assertEqual(out['score'], 0)

    def test_pn10_draft_invoice_has_no_element(self):
        kw = dict(BASE_KW, is_draft=True)
        out = R.evaluate_priority(None, **kw)
        self.assertFalse(out['eligible'])
        self.assertFalse(out['changed'])
        self.assertIsNone(out['level'])

    def test_pn11_a_disappearing_cap_rises_immediately(self):
        p1 = R.evaluate_priority(None, **dict(BASE_KW, days_late=65, outstanding_minor=1_000_000, active_promise=True))
        previous = {'level': p1['level'], 'normalized_inputs': p1['normalized_inputs']}
        p2 = R.evaluate_priority(previous, **dict(BASE_KW, days_late=65, outstanding_minor=1_000_000, active_promise=False))
        self.assertEqual(p1['level'], 'WATCH')                    # plafonné
        self.assertNotEqual(p2['level'], 'WATCH')                 # remonte immédiatement au niveau brut

    def test_rp14_style_three_calls_to_reach_a_steady_state(self):
        """Comme Risk (RP14) : previous_level fait partie des entrées normalisées (PD10.1) — le 2e appel change
        toujours, même à facts strictement identiques ; le régime stationnaire n'apparaît qu'au 3e appel."""
        o1 = R.evaluate_priority(None, **BASE_KW)
        p1 = {'level': o1['level'], 'normalized_inputs': o1['normalized_inputs']}
        o2 = R.evaluate_priority(p1, **BASE_KW)
        self.assertTrue(o2['changed'])
        p2 = {'level': o2['level'], 'normalized_inputs': o2['normalized_inputs']}
        o3 = R.evaluate_priority(p2, **BASE_KW)
        self.assertFalse(o3['changed'])
        self.assertEqual(o2['level'], o3['level'])

    def test_score_can_change_while_published_level_does_not_no_event(self):
        o1 = R.evaluate_priority(None, **BASE_KW)
        p1 = {'level': o1['level'], 'normalized_inputs': o1['normalized_inputs']}
        o2 = R.evaluate_priority(p1, **BASE_KW)
        p2 = {'level': o2['level'], 'normalized_inputs': o2['normalized_inputs']}
        o3 = R.evaluate_priority(p2, **BASE_KW)                    # stationnaire
        p3 = {'level': o3['level'], 'normalized_inputs': o3['normalized_inputs']}
        kw4 = dict(BASE_KW, outstanding_minor=450_000)             # change amount_pts d'une tranche, reste dans le même niveau
        o4 = R.evaluate_priority(p3, **kw4)
        self.assertTrue(o4['changed'])
        self.assertIsNone(o4['event'])
        self.assertEqual(o4['level'], o3['level'])
        self.assertNotEqual(o4['score'], o3['score'])

    def test_reconciliation_signal_alone_changes_normalized_inputs_never_score_or_level(self):
        o1 = R.evaluate_priority(None, **BASE_KW)
        p1 = {'level': o1['level'], 'normalized_inputs': o1['normalized_inputs']}
        kw2 = dict(BASE_KW, reconciliation_pending=True)
        o2 = R.evaluate_priority(p1, **kw2)
        self.assertTrue(o2['changed'])
        self.assertIsNone(o2['event'])
        self.assertEqual(o2['level'], o1['level'])
        self.assertEqual(o2['score'], o1['score'])
        self.assertIn('RECONCILIATION_PENDING', o2['reasons']['signals'])
        self.assertNotIn('RECONCILIATION_PENDING', o1['reasons']['signals'])

    def test_level_change_emits_the_right_event(self):
        o1 = R.evaluate_priority(None, **BASE_KW)
        p1 = {'level': o1['level'], 'normalized_inputs': o1['normalized_inputs']}
        kw2 = dict(BASE_KW, days_late=90, outstanding_minor=2_000_000, risk_level='CRITICAL')
        o2 = R.evaluate_priority(p1, **kw2)
        self.assertNotEqual(o2['level'], o1['level'])
        self.assertIsNotNone(o2['event'])
        self.assertEqual(o2['event']['from_level'], o1['level'])
        self.assertEqual(o2['event']['to_level'], o2['level'])
        self.assertEqual(o2['event']['rank_score'], o2['score'])

    def test_s_none_falls_back_to_days_late(self):
        kw = dict(BASE_KW, days_since_last_action=None, days_late=12)
        out = R.evaluate_priority(None, **kw)
        self.assertEqual(out['normalized_inputs']['attention_pts'], R.attention_points(12))

    def test_risk_level_none_uses_the_unknown_points(self):
        kw = dict(BASE_KW, risk_level=None)
        out = R.evaluate_priority(None, **kw)
        self.assertEqual(out['normalized_inputs']['risk_pts'], R.RISK_PTS[None])


class TestGoldenScoreMatchesTheExistingReference(unittest.TestCase):
    """P1-P7 : `priority_ref` reproduit exactement `golden_cases.json['priority']` (déjà vérifié indépendamment
    contre `verqia_models.prio_evaluate` avant ce fichier)."""

    @classmethod
    def setUpClass(cls):
        with io.open(os.path.join(HERE, 'golden_cases.json'), encoding='utf-8') as f:
            cls.cases = json.load(f)['priority']

    def test_each_case(self):
        for c in self.cases:
            A, Cc, Dd, Dj, risk_level, since_action, overdue = c['inputs']
            prev = R.LEVELS[c['previous_level']] if c['previous_level'] is not None else None
            out = R.score_and_level(A, Cc, overdue, Dd, Dj, risk_level, since_action, prev, c['promise_or_hold'], c['dispute_no_collectible'])
            self.assertEqual(out['score'], c['rank_score'], c['name'])
            self.assertEqual(out['level'], c['level'], c['name'])
            self.assertEqual(sorted(out['caps']), sorted(c['caps']), c['name'])


class TestGoldenFileAndIndependence(unittest.TestCase):
    def test_golden_file_is_up_to_date(self):
        with io.open(os.path.join(HERE, 'golden_priority.json'), encoding='utf-8', newline='') as f:
            current = f.read().replace('\r\n', '\n')
        self.assertEqual(current, render_golden(build_golden()))

    def test_priority_ref_imports_only_the_standard_library(self):
        """Aucune importation de `verqia`, du Domain, de `verqia_models` ni de `risk_ref` — bibliothèque standard
        uniquement (ici : aucune importation du tout)."""
        with io.open(os.path.join(HERE, 'priority_ref.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        found = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                found.append(node)
        self.assertEqual(found, [])

    def test_no_floats_no_real_division(self):
        with io.open(os.path.join(HERE, 'priority_ref.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                self.fail('flottant trouvé : ligne %d' % node.lineno)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                self.fail('division réelle trouvée : ligne %d' % node.lineno)


if __name__ == '__main__':
    unittest.main()
