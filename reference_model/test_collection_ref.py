"""Tests de `collection_ref.py` SEUL : l'oracle est-il fidèle à la spécification gelée, et cohérent avec lui-même ?

Aucune importation de `verqia` : à ce stade, il n'existe aucune implémentation du Collection Domain à comparer.
Trois familles :
  * CR-A : les listes fermées et les tables coïncident avec les sources gelées ;
  * CR-B : les deux transcriptions du `SlotCalculator` (§7) sont d'accord — c'est la protection contre une erreur
    de lecture du document, avant toute implémentation ;
  * CR-C : les 22 cas d'usage produisent le contrat observable attendu, dont le scénario d'or §11 et ses variantes.

Lancement : python -m unittest test_collection_ref (dans reference_model/).
"""
import itertools
import random
import unittest
from datetime import date, datetime, time, timedelta

import collection_ref as R


def action(**kw):
    base = dict(action_id='A', invoice_id='INV-1', customer_id='CUS-1', type='REMINDER', level=3)
    base.update(kw)
    return R.ReferenceAction(**base)


DEC_PROCEED = R.ReferenceRuleDecision(outcome='PROCEED', level=3)
RULES = R.GOLDEN_RULES


# --------------------------------------------------------------------------- CR-A : listes fermées

class TestClosedLists(unittest.TestCase):
    def test_statuses_and_terminals_match_the_state_machine(self):
        self.assertEqual(R.STATUSES, ('PROPOSED', 'SCHEDULED', 'PENDING_APPROVAL', 'EXECUTING',
                                      'DONE', 'FAILED', 'CANCELLED', 'SUPPRESSED'))
        self.assertEqual(R.TERMINAL, ('DONE', 'FAILED', 'CANCELLED', 'SUPPRESSED'))
        for s in R.TERMINAL:
            self.assertIn(s, R.STATUSES)
        # la portée des réactions est un sous-ensemble STRICT des non-terminaux (EXECUTING en est exclu, §12)
        self.assertEqual(set(R.SUPPRESSIBLE), {'PROPOSED', 'SCHEDULED', 'PENDING_APPROVAL'})
        self.assertNotIn('EXECUTING', R.SUPPRESSIBLE)

    def test_outcome_families_are_disjoint_and_closed(self):
        fams = (R.OUTCOMES_SEND, R.OUTCOMES_TASK, R.OUTCOMES_CANCEL)
        for a, b in itertools.combinations(fams, 2):
            self.assertEqual(set(a) & set(b), set())
        self.assertEqual(len(R.OUTCOMES_ALL), sum(len(f) for f in fams))
        self.assertEqual(R.OUTCOMES_TASK, ('CONTACTED', 'NO_ANSWER', 'PROMISE_OBTAINED', 'DISPUTE_RAISED',
                                           'REFUSED', 'WRONG_CONTACT', 'OTHER'))

    def test_every_event_is_in_the_frozen_catalogue(self):
        self.assertEqual(len(R.EVENTS), 8)
        for e in R.EVENTS:
            self.assertTrue(e.startswith('COLLECTION_'))

    def test_every_suppression_mapping_targets_a_known_code(self):
        for event, code in R.SUPPRESSION_ON_EVENT.items():
            self.assertIn(code, R.SUPPRESSION_CODES, event)
        # DV4-7 : les deux événements d'organisation donnent le MÊME code
        self.assertEqual(R.SUPPRESSION_ON_EVENT['ORGANIZATION_CLOSED'],
                         R.SUPPRESSION_ON_EVENT['ORGANIZATION_SUSPENDED'])

    def test_human_task_types_exclude_reminder(self):
        self.assertNotIn('REMINDER', R.HUMAN_TASK_TYPES)
        self.assertEqual(R.CLIENT_FACING_TYPES, ('REMINDER',))
        for t in R.HUMAN_TASK_TYPES:
            self.assertIn(t, R.ACTION_TYPES)

    def test_dedup_key_formula_carries_occurrence(self):
        self.assertEqual(R.dedup_key('INV-1', 'REMINDER', 3, 1, 0), 'INV-1:REMINDER:L3:C1:R0')
        self.assertTrue(R.manual_dedup_key('k1').startswith('manual:'))

    def test_only_cancelled_and_suppressed_release_the_key(self):
        for s in ('PROPOSED', 'SCHEDULED', 'PENDING_APPROVAL', 'EXECUTING', 'DONE', 'FAILED'):
            self.assertTrue(R.key_blocks_duplicate(s), s)
        for s in ('CANCELLED', 'SUPPRESSED'):
            self.assertFalse(R.key_blocks_duplicate(s), s)


# --------------------------------------------------------------------------- CR-B : REF_A == REF_B (§7)

class TestSlotCalculatorDoubleTranscription(unittest.TestCase):
    def _both(self, **kw):
        a = R.next_slot_a(**kw)
        b = R.next_slot_b(**kw)
        self.assertEqual(a, b, 'REF_A != REF_B pour %r' % (kw,))
        return a

    def test_in_window_business_day_is_unchanged(self):
        at = self._both(as_of=datetime(2026, 10, 1, 8, 0), target=datetime(2026, 10, 1, 9, 0),
                        rules=RULES, client_facing=True)
        self.assertEqual(at, datetime(2026, 10, 1, 9, 0))

    def test_sunday_moves_to_next_business_day_at_send_hour(self):
        at = self._both(as_of=datetime(2026, 10, 18, 7, 0), target=datetime(2026, 10, 18, 9, 0),
                        rules=RULES, client_facing=True)
        self.assertEqual(at, datetime(2026, 10, 19, 9, 0))

    def test_before_window_moves_to_window_start_same_day(self):
        at = self._both(as_of=datetime(2026, 10, 1, 5, 0), target=datetime(2026, 10, 1, 6, 30),
                        rules=RULES, client_facing=True)
        self.assertEqual(at, datetime(2026, 10, 1, 8, 0))

    def test_after_window_moves_to_next_business_day(self):
        at = self._both(as_of=datetime(2026, 10, 1, 19, 0), target=datetime(2026, 10, 1, 19, 0),
                        rules=RULES, client_facing=True)
        self.assertEqual(at, datetime(2026, 10, 2, 9, 0))

    def test_friday_after_window_skips_the_weekend(self):
        at = self._both(as_of=datetime(2026, 10, 30, 19, 0), target=datetime(2026, 10, 30, 19, 0),
                        rules=RULES, client_facing=True)
        self.assertEqual(at.date(), date(2026, 11, 2))          # lundi
        self.assertEqual(at.time(), time(9, 0))

    def test_customer_daily_cap_moves_to_next_business_day(self):
        at = self._both(as_of=datetime(2026, 10, 1, 8, 0), target=datetime(2026, 10, 1, 9, 0),
                        rules=RULES, client_facing=True, messages_that_day=2)
        self.assertEqual(at, datetime(2026, 10, 2, 9, 0))

    def test_hourly_throttle_shifts_by_one_hour(self):
        at = self._both(as_of=datetime(2026, 10, 1, 8, 0), target=datetime(2026, 10, 1, 9, 0),
                        rules=RULES, client_facing=True, sends_that_hour=200)
        self.assertEqual(at, datetime(2026, 10, 1, 10, 0))

    def test_holiday_is_not_a_business_day(self):
        rules = R.ReferenceOrgRules(holidays=frozenset({date(2026, 10, 1)}))
        at = self._both(as_of=datetime(2026, 10, 1, 7, 0), target=datetime(2026, 10, 1, 9, 0),
                        rules=rules, client_facing=True)
        self.assertEqual(at, datetime(2026, 10, 2, 9, 0))

    def test_human_task_ignores_the_window_and_keeps_the_business_day(self):
        at = self._both(as_of=datetime(2026, 10, 25, 7, 0), target=datetime(2026, 10, 25, 9, 0),
                        rules=RULES, client_facing=False, task_due_date=date(2026, 10, 25))
        self.assertEqual(at, datetime(2026, 10, 26, 9, 0))      # dimanche -> lundi, heure conservée

    def test_a_send_hour_outside_the_window_is_refused_by_both_transcriptions(self):
        """CONSTAT relevé par l'oracle : §7 ne termine pas si l'heure visée (catégorie B) tombe hors de la
        fenêtre (catégorie C). Aucune source ne l'interdit, aucune ne définit de repli : refus explicite."""
        rules = R.ReferenceOrgRules(comm_window_start=time(8, 0), comm_window_end=time(18, 0), send_hour=time(20, 0))
        for fn in (R.next_slot_a, R.next_slot_b):
            with self.assertRaises(R.PlacementRulesInconsistent):
                fn(as_of=datetime(2026, 10, 1, 7, 0), target=datetime(2026, 10, 1, 20, 0),
                   rules=rules, client_facing=True)

    def test_a_send_hour_outside_the_window_does_not_block_a_human_task(self):
        """Point 5 : une tâche humaine n'a pas de fenêtre — la contradiction ne la concerne donc pas."""
        rules = R.ReferenceOrgRules(comm_window_start=time(8, 0), comm_window_end=time(18, 0), send_hour=time(20, 0))
        at = self._both(as_of=datetime(2026, 10, 25, 7, 0), target=datetime(2026, 10, 25, 20, 0),
                        rules=rules, client_facing=False, task_due_date=date(2026, 10, 26))
        self.assertEqual(at, datetime(2026, 10, 26, 20, 0))

    def test_the_two_transcriptions_agree_on_a_large_random_grid(self):
        """5 000 configurations tirées : c'est ce balayage qui a détecté cinq divergences de transcription."""
        rng = random.Random(1234567)
        compared = 0
        for _ in range(5000):
            target = datetime(2026, 1, 1) + timedelta(
                days=rng.randrange(0, 400), hours=rng.randrange(0, 24), minutes=rng.choice([0, 7, 15, 30, 45, 59]))
            rules = R.ReferenceOrgRules(
                comm_window_start=time(rng.choice([0, 6, 8, 9]), rng.choice([0, 30])),
                comm_window_end=time(rng.choice([13, 17, 18, 19, 23]), rng.choice([0, 30])),
                business_weekdays=rng.choice([(0, 1, 2, 3, 4), (0, 1, 2, 3, 4, 5), (1, 2, 3), (0,)]),
                holidays=frozenset({date(2026, 1, 1), date(2026, 5, 1), date(2026, 12, 25)}),
                send_hour=time(rng.choice([8, 9, 10, 12]), rng.choice([0, 30])),
                max_customer_messages_per_day=rng.choice([0, 1, 2, 5]),
                send_rate_per_hour=rng.choice([0, 1, 200]))
            if not rules.send_hour_inside_window():
                continue                                    # configuration refusée : constat séparé, testé ci-dessus
            self._both(as_of=target - timedelta(hours=rng.randrange(0, 72)), target=target, rules=rules,
                       client_facing=rng.choice([True, False]), task_due_date=target.date(),
                       messages_that_day=rng.randrange(0, 4), sends_that_hour=rng.choice([0, 1, 5, 200, 999]))
            compared += 1
        self.assertGreater(compared, 3000)                  # le filtre ne doit pas vider le balayage

    def test_the_two_transcriptions_agree_on_a_random_grid(self):
        rng = random.Random(20260929)
        for _ in range(400):
            target = datetime(2026, 10, 1, 0, 0) + timedelta(
                days=rng.randrange(0, 60), hours=rng.randrange(0, 24), minutes=rng.choice([0, 15, 30, 45]))
            rules = R.ReferenceOrgRules(
                comm_window_start=time(rng.choice([7, 8, 9]), 0),
                comm_window_end=time(rng.choice([17, 18, 19]), 0),
                business_weekdays=rng.choice([(0, 1, 2, 3, 4), (0, 1, 2, 3, 4, 5), (1, 2, 3)]),
                holidays=frozenset({date(2026, 10, 12), date(2026, 11, 11)}),
                send_hour=time(rng.choice([9, 10, 14]), 0),
                max_customer_messages_per_day=rng.choice([1, 2, 5]),
                send_rate_per_hour=rng.choice([1, 200]))
            self._both(as_of=target - timedelta(hours=2), target=target, rules=rules,
                       client_facing=rng.choice([True, False]), task_due_date=target.date(),
                       messages_that_day=rng.randrange(0, 3), sends_that_hour=rng.choice([0, 1, 200]))

    def test_a_slot_is_always_a_business_day_inside_the_window(self):
        rng = random.Random(7)
        for _ in range(200):
            target = datetime(2026, 10, 1) + timedelta(days=rng.randrange(0, 90), hours=rng.randrange(0, 24))
            at = R.next_slot_a(as_of=target, target=target, rules=RULES, client_facing=True)
            self.assertTrue(RULES.is_business_day(at.date()))
            self.assertTrue(RULES.comm_window_start <= at.time() < RULES.comm_window_end)
            self.assertGreaterEqual(at, target)                 # jamais en arrière


class TestRescheduleAnchor(unittest.TestCase):
    """BLOCKER-1, décision normative du 2026-09-29."""

    def test_a_future_target_is_used_as_is(self):
        as_of = datetime(2026, 10, 1, 9, 0)
        self.assertEqual(R.anchored_target(datetime(2026, 10, 5, 9, 0), as_of), datetime(2026, 10, 5, 9, 0))

    def test_a_past_target_is_anchored_at_as_of(self):
        as_of = datetime(2026, 10, 1, 9, 0)
        self.assertEqual(R.anchored_target(datetime(2026, 9, 1, 9, 0), as_of), as_of)

    def test_rescheduling_to_the_past_never_produces_a_slot_before_the_command(self):
        as_of = datetime(2026, 10, 1, 10, 30)
        d = R.reschedule_action(action(status='SCHEDULED', scheduled_for=datetime(2026, 10, 9, 9, 0)),
                                target=datetime(2026, 8, 1, 9, 0), as_of=as_of, rules=RULES)
        slot = dict(d.writes)['scheduled_for']
        self.assertGreaterEqual(slot, as_of)
        self.assertTrue(RULES.comm_window_start <= slot.time() < RULES.comm_window_end)


# --------------------------------------------------------------------------- CR-C : contrats observables

class TestCreation(unittest.TestCase):
    def test_proceed_creates_proposed_and_emits_proposed(self):
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='REMINDER', level=1, cycle=0, occurrence=0)
        d = R.create_collection_action([], cmd, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 1, 9, 0), RULES)
        self.assertEqual((d.issue, d.transition, d.events), ('OK', (None, 'PROPOSED'), ('COLLECTION_ACTION_PROPOSED',)))
        self.assertEqual(d.dedup_key, 'INV-1:REMINDER:L1:C0:R0')

    def test_suppress_writes_a_single_suppressed_row(self):
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='REMINDER', level=1, cycle=0, occurrence=0)
        dec = R.ReferenceRuleDecision(outcome='SUPPRESS', level=1, suppression_code='PAID')
        d = R.create_collection_action([], cmd, dec, R.ReferenceFacts(), datetime(2026, 10, 1, 9, 0), RULES)
        self.assertEqual((d.issue, d.transition, d.suppression), ('SKIPPED', (None, 'SUPPRESSED'), 'PAID'))
        self.assertEqual(d.events, ('COLLECTION_ACTION_SUPPRESSED',))

    def test_an_existing_live_key_gives_replay(self):
        a = action(level=1, status='SCHEDULED', occurrence=0, cycle=0)
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='REMINDER', level=1, cycle=0, occurrence=0)
        d = R.create_collection_action([a], cmd, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 1), RULES)
        self.assertEqual(d.issue, 'REPLAY')

    def test_a_cancelled_row_releases_the_key(self):
        a = action(level=1, status='CANCELLED')
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='REMINDER', level=1, cycle=0, occurrence=0)
        d = R.create_collection_action([a], cmd, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 1), RULES)
        self.assertEqual(d.issue, 'OK')

    def test_level_out_of_range_and_below_floor_are_refused_but_never_computed(self):
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='REMINDER', level=9, cycle=0, occurrence=0)
        d = R.create_collection_action([], cmd, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 1), RULES)
        self.assertEqual(d.refusal, 'ACTION_LEVEL_INVALID')
        cmd2 = dict(cmd, level=2)
        d2 = R.create_collection_action([], cmd2, DEC_PROCEED,
                                        R.ReferenceFacts(invoice_overdue=True), datetime(2026, 10, 1), RULES)
        self.assertEqual(d2.refusal, 'ACTION_LEVEL_BELOW_MINIMUM')

    def test_level_regression_is_refused_with_its_open_reserve_not_an_invented_code(self):
        a = action(level=4, status='DONE')
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='REMINDER', level=3, cycle=0, occurrence=1)
        d = R.create_collection_action([a], cmd, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 1), RULES)
        self.assertEqual(d.issue, 'REFUSED')
        self.assertIsNone(d.refusal)                            # aucun code inventé
        self.assertTrue(any('R-7' in r for r in d.reserves))

    def test_manual_creation_always_audits_and_uses_its_own_key(self):
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='CALL_TASK', level=3, cycle=1,
                   occurrence=0, idempotency_key='k1')
        d = R.create_collection_action([], cmd, DEC_PROCEED, R.ReferenceFacts(invoice_overdue=True),
                                       datetime(2026, 10, 20), RULES, manual=True)
        self.assertTrue(d.audit)
        self.assertEqual(d.dedup_key, 'manual:k1')


class TestAdvanceAndApproval(unittest.TestCase):
    def test_guard_is_proposed_only(self):
        for s in ('SCHEDULED', 'EXECUTING', 'DONE', 'CANCELLED'):
            d = R.advance_proposed_action(action(status=s), DEC_PROCEED, R.ReferenceFacts(),
                                          datetime(2026, 10, 1, 9, 0), RULES)
            self.assertEqual(d.issue, 'SKIPPED', s)

    def test_requires_approval_goes_to_pending_approval(self):
        dec = R.ReferenceRuleDecision(outcome='PROCEED', level=3, requires_approval=True)
        d = R.advance_proposed_action(action(status='PROPOSED'), dec, R.ReferenceFacts(),
                                      datetime(2026, 10, 1, 9, 0), RULES)
        self.assertEqual(d.transition, ('PROPOSED', 'PENDING_APPROVAL'))
        self.assertEqual(d.events, ())                          # aucun événement pour cette transition

    def test_a_human_task_never_requires_approval(self):
        dec = R.ReferenceRuleDecision(outcome='PROCEED', level=4, requires_approval=True)
        d = R.advance_proposed_action(action(status='PROPOSED', type='ESCALATION'), dec, R.ReferenceFacts(),
                                      datetime(2026, 10, 30, 7, 0), RULES)
        self.assertEqual(d.transition, ('PROPOSED', 'SCHEDULED'))

    def test_approval_granted_schedules_and_rejected_cancels_with_its_issue(self):
        a = action(status='PENDING_APPROVAL')
        ok = R.on_approval_decided(a, True, datetime(2026, 10, 1, 7, 0), RULES)
        self.assertEqual(ok.transition, ('PENDING_APPROVAL', 'SCHEDULED'))
        ko = R.on_approval_decided(a, False, datetime(2026, 10, 1, 7, 0), RULES)
        self.assertEqual(ko.transition, ('PENDING_APPROVAL', 'CANCELLED'))
        self.assertEqual(dict(ko.writes)['outcome'], 'APPROVAL_REJECTED')


class TestExecutionLoop(unittest.TestCase):
    def test_claim_requires_a_due_scheduled_action(self):
        a = action(status='SCHEDULED', scheduled_for=datetime(2026, 10, 2, 9, 0))
        self.assertEqual(R.execute_due_action(a, DEC_PROCEED, R.ReferenceFacts(),
                                              datetime(2026, 10, 1, 9, 0), RULES).issue, 'SKIPPED')
        d = R.execute_due_action(a, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 2, 9, 0), RULES)
        self.assertEqual(d.transition, ('SCHEDULED', 'EXECUTING'))
        self.assertEqual(dict(d.writes)['attempts'], 1)

    def test_execute_never_emits_executed_or_failed(self):
        a = action(status='SCHEDULED', scheduled_for=datetime(2026, 10, 2, 9, 0))
        d = R.execute_due_action(a, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 2, 9, 0), RULES)
        self.assertNotIn('COLLECTION_ACTION_EXECUTED', d.events)
        self.assertNotIn('COLLECTION_ACTION_FAILED', d.events)

    def test_the_loop_closes_in_on_notification_result(self):
        a = action(status='EXECUTING', attempts=1, executing_since=datetime(2026, 10, 2, 9, 0))
        ok = R.on_notification_result(a, 'SENT', datetime(2026, 10, 2, 9, 1), RULES)
        self.assertEqual((ok.transition, ok.events, dict(ok.writes)['outcome']),
                         (('EXECUTING', 'DONE'), ('COLLECTION_ACTION_EXECUTED',), 'SENT'))

    def test_transient_error_reschedules_with_the_documented_delays(self):
        for attempts, delay in ((1, timedelta(minutes=5)), (2, timedelta(minutes=30)), (3, timedelta(hours=2))):
            a = action(status='EXECUTING', attempts=attempts, executing_since=datetime(2026, 10, 2, 9, 0))
            d = R.on_notification_result(a, 'FAILED', datetime(2026, 10, 2, 9, 5), RULES, error_class='TRANSIENT')
            if attempts < R.MAX_ATTEMPTS:
                self.assertEqual(d.retry_at, datetime(2026, 10, 2, 9, 5) + delay, attempts)
            else:
                self.assertEqual(d.transition, ('EXECUTING', 'FAILED'))

    def test_permanent_and_configuration_errors_fail_immediately(self):
        for cls in ('PERMANENT', 'CONFIGURATION'):
            a = action(status='EXECUTING', attempts=1, executing_since=datetime(2026, 10, 2, 9, 0))
            d = R.on_notification_result(a, 'FAILED', datetime(2026, 10, 2, 9, 5), RULES, error_class=cls)
            self.assertEqual(d.transition, ('EXECUTING', 'FAILED'), cls)

    def test_a_result_arriving_on_a_terminal_action_is_skipped(self):
        a = action(status='CANCELLED')
        self.assertEqual(R.on_notification_result(a, 'SENT', datetime(2026, 10, 2, 9, 1), RULES).issue, 'SKIPPED')

    def test_reaper_threshold_is_fifteen_minutes_and_closes_the_attempt(self):
        since = datetime(2026, 10, 2, 9, 0)
        a = action(status='EXECUTING', attempts=1, executing_since=since)
        self.assertEqual(R.reap_actions(a, since + timedelta(minutes=15)).issue, 'SKIPPED')
        d = R.reap_actions(a, since + timedelta(minutes=16))
        self.assertEqual(d.transition, ('EXECUTING', 'SCHEDULED'))
        self.assertEqual(dict(d.writes)['attempt_closed'][0], 'FAILED')
        self.assertEqual(d.events, ())                          # OPEN-04 : aucun événement sur reprise
        self.assertTrue(any('R-5' in r for r in d.reserves))


class TestHumanTasks(unittest.TestCase):
    def test_claim_is_refused_on_a_reminder(self):
        d = R.claim_task(action(type='REMINDER', status='SCHEDULED', assigned_role='COLLECTOR'),
                         'u1', 'COLLECTOR', datetime(2026, 10, 26, 9, 0))
        self.assertEqual(d.refusal, 'ACTION_INVALID_TRANSITION')

    def test_claim_assigns_without_any_status_transition(self):
        a = action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR')
        d = R.claim_task(a, 'u1', 'COLLECTOR', datetime(2026, 10, 26, 9, 0))
        self.assertEqual((d.issue, d.transition), ('OK', None))
        self.assertEqual(dict(d.writes), {'assigned_to': 'u1'})
        self.assertEqual(d.events, ())                          # R-1 : aucun événement identifié

    def test_a_second_claimant_loses_and_the_same_one_replays(self):
        a = action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR', assigned_to='u1')
        self.assertEqual(R.claim_task(a, 'u2', 'COLLECTOR', datetime(2026, 10, 26)).refusal,
                         'CONCURRENT_MODIFICATION')
        self.assertEqual(R.claim_task(a, 'u1', 'COLLECTOR', datetime(2026, 10, 26)).issue, 'REPLAY')

    def test_an_insufficient_role_cannot_claim(self):
        a = action(type='ESCALATION', status='SCHEDULED', assigned_role='MANAGER')
        self.assertEqual(R.claim_task(a, 'u1', 'COLLECTOR', datetime(2026, 10, 30)).issue, 'REFUSED')

    def test_completing_needs_no_prior_claim(self):
        a = action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR', assigned_to=None)
        d = R.complete_task(a, 'u9', 'COLLECTOR', 'CONTACTED', datetime(2026, 10, 26, 11, 0))
        self.assertEqual((d.issue, d.transition, d.events),
                         ('OK', ('SCHEDULED', 'DONE'), ('COLLECTION_ACTION_EXECUTED',)))

    def test_the_assignee_may_complete_even_without_the_pool_role(self):
        a = action(type='ESCALATION', status='SCHEDULED', assigned_role='MANAGER', assigned_to='u1')
        d = R.complete_task(a, 'u1', 'COLLECTOR', 'CONTACTED', datetime(2026, 10, 30, 11, 0))
        self.assertEqual(d.issue, 'OK')

    def test_a_stranger_without_the_role_is_refused(self):
        a = action(type='ESCALATION', status='SCHEDULED', assigned_role='MANAGER', assigned_to='u1')
        self.assertEqual(R.complete_task(a, 'u2', 'COLLECTOR', 'CONTACTED', datetime(2026, 10, 30)).refusal,
                         'INSUFFICIENT_ROLE')

    def test_outcome_must_belong_to_the_human_task_family(self):
        a = action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR')
        for bad in ('SENT', 'USER_CANCELLED', 'NOPE'):
            self.assertEqual(R.complete_task(a, 'u1', 'COLLECTOR', bad, datetime(2026, 10, 26)).issue,
                             'REFUSED', bad)

    def test_suggesting_outcomes_only_carry_a_reserve_never_a_creation(self):
        a = action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR')
        d = R.complete_task(a, 'u1', 'COLLECTOR', 'PROMISE_OBTAINED', datetime(2026, 10, 26, 11, 0))
        self.assertEqual(d.events, ('COLLECTION_ACTION_EXECUTED',))     # jamais PROMISE_CREATED
        self.assertTrue(any('SUGGÈRE' in r for r in d.reserves))


class TestRescheduleGuards(unittest.TestCase):
    def test_entry_states_are_closed_to_proposed_and_scheduled(self):
        for s in ('PROPOSED', 'SCHEDULED'):
            d = R.reschedule_action(action(status=s), datetime(2026, 10, 9, 9, 0),
                                    datetime(2026, 10, 1, 9, 0), RULES)
            self.assertEqual(d.issue, 'OK', s)
        for s in ('PENDING_APPROVAL', 'EXECUTING', 'DONE', 'FAILED', 'CANCELLED', 'SUPPRESSED'):
            d = R.reschedule_action(action(status=s), datetime(2026, 10, 9, 9, 0),
                                    datetime(2026, 10, 1, 9, 0), RULES)
            self.assertEqual(d.refusal, 'ACTION_INVALID_TRANSITION', s)

    def test_reschedule_never_transitions_the_status(self):
        d = R.reschedule_action(action(status='SCHEDULED'), datetime(2026, 10, 9, 9, 0),
                                datetime(2026, 10, 1, 9, 0), RULES)
        self.assertIsNone(d.transition)
        self.assertEqual(set(dict(d.writes)), {'scheduled_for'})

    def test_cancel_accepts_executing_but_reschedule_does_not(self):
        a = action(status='EXECUTING', executing_since=datetime(2026, 10, 2, 9, 0))
        self.assertEqual(R.cancel_collection_action(a, 'motif', datetime(2026, 10, 2, 9, 5)).transition,
                         ('EXECUTING', 'CANCELLED'))
        self.assertEqual(R.reschedule_action(a, datetime(2026, 10, 9, 9, 0),
                                            datetime(2026, 10, 2, 9, 5), RULES).issue, 'REFUSED')


class TestHolds(unittest.TestCase):
    def hold(self, **kw):
        base = dict(hold_id='H1', scope='INVOICE', invoice_id='INV-1', reason='r',
                    starts_at=datetime(2026, 10, 1), ends_at=datetime(2026, 10, 31))
        base.update(kw)
        return R.ReferenceHold(**base)

    def test_manager_role_is_required_to_place_and_release(self):
        h = self.hold()
        self.assertEqual(R.place_hold([], h, 'COLLECTOR', datetime(2026, 10, 1)).refusal, 'INSUFFICIENT_ROLE')
        self.assertEqual(R.release_hold(h, 'COLLECTOR', 'r', datetime(2026, 10, 2)).refusal, 'INSUFFICIENT_ROLE')

    def test_place_hold_only_writes_the_hold_and_emits_only_hold_placed(self):
        d = R.place_hold([], self.hold(), 'MANAGER', datetime(2026, 10, 1))
        self.assertEqual(d.events, ('COLLECTION_HOLD_PLACED',))
        self.assertIsNone(d.suppression)                        # la suppression des actions appartient à C5

    def test_overlap_on_the_same_target_is_refused(self):
        existing = self.hold()
        d = R.place_hold([existing], self.hold(hold_id='H2', starts_at=datetime(2026, 10, 15),
                                              ends_at=datetime(2026, 11, 15)), 'MANAGER', datetime(2026, 10, 15))
        self.assertEqual(d.refusal, 'HOLD_OVERLAP')

    def test_a_disjoint_range_is_accepted(self):
        existing = self.hold()
        d = R.place_hold([existing], self.hold(hold_id='H2', starts_at=datetime(2026, 11, 1),
                                              ends_at=datetime(2026, 11, 15)), 'MANAGER', datetime(2026, 11, 1))
        self.assertEqual(d.issue, 'OK')

    def test_scope_must_match_the_target(self):
        self.assertEqual(R.place_hold([], self.hold(scope='CUSTOMER', invoice_id='INV-1', customer_id='CUS-1'),
                                      'MANAGER', datetime(2026, 10, 1)).refusal, 'HOLD_TARGET_MISMATCH')
        self.assertEqual(R.place_hold([], self.hold(scope='ORGANIZATION'), 'MANAGER',
                                      datetime(2026, 10, 1)).refusal, 'HOLD_TARGET_MISMATCH')

    def test_expiry_is_effective_before_the_scan_materialises_it(self):
        h = self.hold()
        after = datetime(2026, 11, 1)
        self.assertFalse(R.hold_in_force(h, after))             # déjà hors vigueur
        self.assertEqual(R.hold_expiry_scan(h, after).transition, ('ACTIVE', 'EXPIRED'))
        self.assertEqual(R.hold_expiry_scan(h, datetime(2026, 10, 15)).issue, 'SKIPPED')

    def test_release_and_expiry_share_the_event_but_not_the_cause(self):
        h = self.hold()
        rel = R.release_hold(h, 'MANAGER', 'fini', datetime(2026, 10, 10))
        exp = R.hold_expiry_scan(h, datetime(2026, 11, 1))
        self.assertEqual(rel.events, exp.events)
        self.assertEqual(dict(rel.writes)['status'], 'RELEASED')
        self.assertEqual(dict(exp.writes)['status'], 'EXPIRED')
        self.assertTrue(rel.audit)
        self.assertFalse(exp.audit)                             # transition temporelle : aucun audit


class TestSuppressionReactions(unittest.TestCase):
    def test_executing_is_never_suppressed_by_a_reaction(self):
        a = action(status='EXECUTING', executing_since=datetime(2026, 10, 2, 9, 0))
        d = R.suppress_on_event(a, 'INVOICE_PAID', {'invoice_id': 'INV-1'}, R.ReferenceFacts(),
                                datetime(2026, 10, 2, 9, 5))
        self.assertEqual(d.issue, 'SKIPPED')

    def test_each_reaction_maps_to_its_code(self):
        for event, code in R.SUPPRESSION_ON_EVENT.items():
            payload = {'invoice_id': 'INV-1', 'customer_id': 'CUS-1'}
            facts = R.ReferenceFacts(collectible_minor=0)
            hold = R.ReferenceHold(hold_id='H', scope='INVOICE', invoice_id='INV-1',
                                   starts_at=datetime(2026, 10, 1))
            d = R.suppress_on_event(action(status='SCHEDULED'), event, payload, facts,
                                    datetime(2026, 10, 2), hold=hold)
            self.assertEqual((d.issue, d.suppression), ('PROCESSED', code), event)
            self.assertEqual(d.events, ('COLLECTION_ACTION_SUPPRESSED',), event)

    def test_partial_dispute_does_not_suppress(self):
        facts = R.ReferenceFacts(collectible_minor=250000)
        d = R.suppress_on_event(action(status='SCHEDULED'), 'INVOICE_DISPUTED', {'invoice_id': 'INV-1'},
                                facts, datetime(2026, 10, 2))
        self.assertEqual(d.issue, 'SKIPPED')

    def test_total_dispute_suppresses(self):
        facts = R.ReferenceFacts(collectible_minor=0)
        d = R.suppress_on_event(action(status='SCHEDULED'), 'INVOICE_DISPUTED', {'invoice_id': 'INV-1'},
                                facts, datetime(2026, 10, 2))
        self.assertEqual(d.suppression, 'DISPUTED')

    def test_promise_scope_comes_from_the_payload(self):
        sched = action(status='SCHEDULED')
        invoice_scoped = R.suppress_on_event(sched, 'PROMISE_CREATED', {'invoice_id': 'INV-1', 'customer_id': 'CUS-1'},
                                             R.ReferenceFacts(), datetime(2026, 10, 20))
        other_invoice = R.suppress_on_event(sched, 'PROMISE_CREATED', {'invoice_id': 'INV-9', 'customer_id': 'CUS-1'},
                                            R.ReferenceFacts(), datetime(2026, 10, 20))
        customer_scoped = R.suppress_on_event(sched, 'PROMISE_CREATED', {'customer_id': 'CUS-1'},
                                              R.ReferenceFacts(), datetime(2026, 10, 20))
        self.assertEqual(invoice_scoped.suppression, 'PROMISE_ACTIVE')
        self.assertEqual(other_invoice.issue, 'SKIPPED')
        self.assertEqual(customer_scoped.suppression, 'PROMISE_ACTIVE')

    def test_hold_scope_is_honoured(self):
        sched = action(status='SCHEDULED')
        elsewhere = R.ReferenceHold(hold_id='H', scope='INVOICE', invoice_id='INV-9',
                                    starts_at=datetime(2026, 10, 1))
        org = R.ReferenceHold(hold_id='H', scope='ORGANIZATION', starts_at=datetime(2026, 10, 1))
        self.assertEqual(R.suppress_on_event(sched, 'COLLECTION_HOLD_PLACED', {}, R.ReferenceFacts(),
                                             datetime(2026, 10, 2), hold=elsewhere).issue, 'SKIPPED')
        self.assertEqual(R.suppress_on_event(sched, 'COLLECTION_HOLD_PLACED', {}, R.ReferenceFacts(),
                                             datetime(2026, 10, 2), hold=org).suppression, 'HOLD_ACTIVE')


# --------------------------------------------------------------------------- scénario d'or §11

class TestGoldenScenario(unittest.TestCase):
    """`COLLECTION_ENGINE_V1.md` §11, « test d'or de bout en bout ». Les NIVEAUX sont reçus, jamais recalculés."""

    def test_the_documented_weekdays_are_the_real_ones(self):
        """Le document nomme les jours : si le calendrier les contredit, c'est un constat à remonter."""
        expected = {date(2026, 9, 28): 0, date(2026, 10, 15): 3, date(2026, 10, 1): 3, date(2026, 10, 8): 3,
                    date(2026, 10, 16): 4, date(2026, 10, 18): 6, date(2026, 10, 19): 0, date(2026, 10, 25): 6,
                    date(2026, 10, 26): 0, date(2026, 10, 30): 4, date(2026, 11, 14): 5}
        for d, wd in expected.items():
            self.assertEqual(d.weekday(), wd, d)

    def test_each_documented_step_lands_on_its_documented_slot(self):
        for step, trigger, level, type_, expected in R.GOLDEN_STEPS:
            a = action(type=type_, level=level, status='PROPOSED', cycle=1 if level >= 3 else 0)
            dec = R.ReferenceRuleDecision(outcome='PROCEED', level=level, risk_level='MEDIUM')
            task_due = expected.date() if type_ in R.HUMAN_TASK_TYPES else None
            d = R.advance_proposed_action(a, dec, R.ReferenceFacts(invoice_overdue=level >= 3),
                                          trigger, R.GOLDEN_RULES,
                                          target=datetime.combine(trigger.date(), R.GOLDEN_RULES.send_hour),
                                          task_due_date=task_due)
            self.assertEqual(d.transition, ('PROPOSED', 'SCHEDULED'), step)
            self.assertEqual(dict(d.writes)['scheduled_for'], expected, step)

    def test_s3_sunday_is_moved_to_monday_nine(self):
        step, trigger, level, type_, expected = R.GOLDEN_STEPS[2]
        self.assertEqual(step, 'S3')
        self.assertEqual(trigger.date().weekday(), 6)
        self.assertEqual(expected, datetime(2026, 10, 19, 9, 0))

    def test_s6_replays_on_the_key_already_reached_by_s5(self):
        s5 = action(action_id='S5', type='ESCALATION', level=4, cycle=1, occurrence=0, status='SCHEDULED')
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='ESCALATION', level=4, cycle=1, occurrence=0)
        dec = R.ReferenceRuleDecision(outcome='PROCEED', level=4, risk_level='MEDIUM')
        d = R.create_collection_action([s5], cmd, dec, R.ReferenceFacts(invoice_overdue=True),
                                       R.GOLDEN_S6[1], R.GOLDEN_RULES)
        self.assertEqual(d.issue, 'REPLAY')
        self.assertEqual(d.events, ())
        self.assertEqual(R.GOLDEN_S6[4], 'REPLAY')

    def test_variant_settlement_suppresses_everything_that_follows(self):
        """§11 variante : règlement complet le 2026-10-22 -> tout ce qui suit est SUPPRESSED (PAID) ou annulé."""
        paid_at = datetime(2026, 10, 22, 10, 0)
        for status in R.SUPPRESSIBLE:
            d = R.suppress_on_event(action(status=status, level=3, cycle=1), 'INVOICE_PAID',
                                    {'invoice_id': 'INV-1'}, R.ReferenceFacts(), paid_at)
            self.assertEqual((d.issue, d.suppression), ('PROCESSED', 'PAID'), status)

    def test_variant_promise_suppresses_s4_and_s5(self):
        """§11 variante : promesse créée le 2026-10-20 -> S4 et S5 SUPPRESSED (PROMISE_ACTIVE)."""
        at = datetime(2026, 10, 20, 9, 0)
        for aid, type_, level in (('S4', 'CALL_TASK', 3), ('S5', 'ESCALATION', 4)):
            a = action(action_id=aid, type=type_, level=level, cycle=1, status='SCHEDULED',
                       assigned_role='COLLECTOR')
            d = R.suppress_on_event(a, 'PROMISE_CREATED', {'invoice_id': 'INV-1', 'customer_id': 'CUS-1'},
                                    R.ReferenceFacts(), at)
            self.assertEqual(d.suppression, 'PROMISE_ACTIVE', aid)

    def test_variant_high_risk_level_five_is_received_not_computed(self):
        """§11 variante : à risque HIGH, S6 donne le niveau 5. L'oracle le REÇOIT et le valide, ne le calcule pas."""
        cmd = dict(invoice_id='INV-1', customer_id='CUS-1', type='ESCALATION', level=5, cycle=1, occurrence=0)
        dec = R.ReferenceRuleDecision(outcome='PROCEED', level=5, risk_level='HIGH')
        d = R.create_collection_action([], cmd, dec, R.ReferenceFacts(invoice_overdue=True),
                                       R.GOLDEN_S6[1], R.GOLDEN_RULES)
        self.assertEqual((d.issue, d.transition), ('OK', (None, 'PROPOSED')))
        self.assertEqual(d.dedup_key, 'INV-1:ESCALATION:L5:C1:R0')


# --------------------------------------------------------------------------- propriétés transversales

class TestCrossCuttingProperties(unittest.TestCase):
    def test_no_decision_ever_emits_an_event_outside_the_frozen_catalogue(self):
        calls = [
            R.create_collection_action([], dict(invoice_id='I', customer_id='C', type='REMINDER', level=1,
                                                cycle=0, occurrence=0), DEC_PROCEED, R.ReferenceFacts(),
                                        datetime(2026, 10, 1, 9, 0), RULES),
            R.advance_proposed_action(action(status='PROPOSED'), DEC_PROCEED, R.ReferenceFacts(),
                                      datetime(2026, 10, 1, 9, 0), RULES),
            R.cancel_collection_action(action(status='SCHEDULED'), 'm', datetime(2026, 10, 1)),
            R.execute_due_action(action(status='SCHEDULED', scheduled_for=datetime(2026, 10, 1, 9, 0)),
                                 DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 1, 9, 0), RULES),
            R.on_notification_result(action(status='EXECUTING', attempts=1), 'SENT', datetime(2026, 10, 1, 9, 1), RULES),
            R.on_approval_decided(action(status='PENDING_APPROVAL'), True, datetime(2026, 10, 1, 7, 0), RULES),
            R.claim_task(action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR'), 'u', 'COLLECTOR',
                         datetime(2026, 10, 1)),
            R.complete_task(action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR'), 'u', 'COLLECTOR',
                            'CONTACTED', datetime(2026, 10, 1)),
            R.reschedule_action(action(status='SCHEDULED'), datetime(2026, 10, 9, 9, 0), datetime(2026, 10, 1), RULES),
        ]
        for d in calls:
            for e in d.events:
                self.assertIn(e, R.EVENTS, d.use_case)

    def test_no_decision_ever_returns_a_status_outside_the_closed_list(self):
        for d in (R.advance_proposed_action(action(status='PROPOSED'), DEC_PROCEED, R.ReferenceFacts(),
                                            datetime(2026, 10, 1, 9, 0), RULES),
                  R.complete_task(action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR'),
                                  'u', 'COLLECTOR', 'CONTACTED', datetime(2026, 10, 1))):
            if d.transition:
                before, after = d.transition
                self.assertIn(after, R.STATUSES)
                if before is not None:
                    self.assertIn(before, R.STATUSES)

    def test_a_terminal_action_never_transitions_again(self):
        for s in R.TERMINAL:
            a = action(status=s, type='CALL_TASK', assigned_role='COLLECTOR')
            for d in (R.advance_proposed_action(a, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 1, 9, 0), RULES),
                      R.execute_due_action(a, DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 1, 9, 0), RULES),
                      R.reap_actions(a, datetime(2026, 10, 1, 9, 30)),
                      R.on_notification_result(a, 'SENT', datetime(2026, 10, 1, 9, 1), RULES),
                      R.on_approval_decided(a, True, datetime(2026, 10, 1, 7, 0), RULES),
                      R.suppress_on_event(a, 'INVOICE_PAID', {'invoice_id': 'INV-1'}, R.ReferenceFacts(),
                                          datetime(2026, 10, 1))):
                self.assertIsNone(d.transition, '%s / %s' % (s, d.use_case))

    def test_every_use_case_that_writes_a_done_status_sets_an_outcome(self):
        """`DATA_CONTRACT_V1.md` §6.1 : `status='DONE' ⇒ outcome IS NOT NULL`."""
        done = [R.complete_task(action(type='CALL_TASK', status='SCHEDULED', assigned_role='COLLECTOR'),
                                'u', 'COLLECTOR', 'CONTACTED', datetime(2026, 10, 1)),
                R.on_notification_result(action(status='EXECUTING', attempts=1), 'SENT',
                                         datetime(2026, 10, 1, 9, 1), RULES)]
        for d in done:
            w = dict(d.writes)
            self.assertEqual(w['status'], 'DONE', d.use_case)
            self.assertIn(w.get('outcome'), R.OUTCOMES_ALL, d.use_case)

    def test_a_cancelled_status_always_carries_a_cancellation_family_outcome(self):
        """`DATA_CONTRACT_V1.md` §6.1 : `status='CANCELLED' ⇒ outcome IN (famille annulation)`."""
        for d in (R.cancel_collection_action(action(status='SCHEDULED'), 'm', datetime(2026, 10, 1)),
                  R.on_approval_decided(action(status='PENDING_APPROVAL'), False, datetime(2026, 10, 1), RULES)):
            self.assertIn(dict(d.writes)['outcome'], R.OUTCOMES_CANCEL, d.use_case)

    def test_suppression_always_carries_a_code(self):
        for event in R.SUPPRESSION_ON_EVENT:
            hold = R.ReferenceHold(hold_id='H', scope='ORGANIZATION', starts_at=datetime(2026, 10, 1))
            d = R.suppress_on_event(action(status='SCHEDULED'), event,
                                    {'invoice_id': 'INV-1', 'customer_id': 'CUS-1'},
                                    R.ReferenceFacts(collectible_minor=0), datetime(2026, 10, 2), hold=hold)
            if d.transition:
                self.assertIsNotNone(d.suppression, event)
                self.assertEqual(dict(d.writes)['suppression_code'], d.suppression, event)

    def test_the_oracle_is_deterministic(self):
        args = (action(status='PROPOSED'), DEC_PROCEED, R.ReferenceFacts(), datetime(2026, 10, 18, 7, 0), RULES)
        self.assertEqual(R.advance_proposed_action(*args), R.advance_proposed_action(*args))

    def test_the_oracle_has_no_clock_and_no_verqia_import(self):
        """Vérification par AST : les mentions en docstring (« jamais `datetime.now()` ») ne doivent pas compter."""
        import ast
        import io
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'collection_ref.py')
        with io.open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read())

        forbidden_modules = {'verqia', 'risk_ref', 'priority_ref', 'finance_ref', 'verqia_models', 'random', 'os', 'io'}
        forbidden_calls = {('datetime', 'now'), ('date', 'today'), ('datetime', 'utcnow'), ('time', 'time')}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split('.')[0], forbidden_modules, alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or '').split('.')[0], forbidden_modules, node.module)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if isinstance(owner, ast.Name):
                    self.assertNotIn((owner.id, node.func.attr), forbidden_calls,
                                     '%s.%s' % (owner.id, node.func.attr))


if __name__ == '__main__':
    unittest.main()
