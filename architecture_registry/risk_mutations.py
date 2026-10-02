"""Mutations de CODE du Risk Domain V1 : chacune retire ou corrompt UNE règle ; les tests désignés doivent alors ÉCHOUER
(« tuer » la mutation). Format : Mutation(id, edits, kill) ; `edits` = ((fichier relatif à verqia-app, motif, remplacement,
occurrences attendues), ...) ; `kill` = identifiants de tests de `domain_tests` qui doivent tomber.

M1-M7 mutent le Domain PUR (`verqia/risk/domain/*.py`, futur périmètre du gel Risk). M8-M11 mutent délibérément le
HARNAIS (`domain_tests/risk/runner_wiring.py`) : ce n'est pas encore un module Application réel, mais c'est aujourd'hui
la SEULE représentation exécutable de la façon dont l'Application assemble/persiste les faits Risk — une régression y
introduite est exactement ce qu'une vraie régression d'Application produirait (§ RI5bis, RI15, RI16, RI17 de
`risk_catalogue.py`). La relation invariant → mutations est dans `risk_proofs.py`.
"""
from collections import namedtuple

Mutation = namedtuple('Mutation', 'id edits kill')

SCO = 'verqia/risk/domain/scoring.py'
AGG = 'verqia/risk/domain/aggregation.py'
FAC = 'verqia/risk/domain/facts.py'
PRO = 'verqia/risk/domain/profile.py'
WIRE = 'domain_tests/risk/runner_wiring.py'

TAB = 'domain_tests.risk.test_dt_risk_tables.'
AGGT = 'domain_tests.risk.test_dt_risk_aggregation.'
DEC = 'domain_tests.risk.test_dt_risk_decisions.'
FACT = 'domain_tests.risk.test_dt_risk_facts.'
RUN = 'domain_tests.risk.test_dt_risk_runner.'
INT = 'domain_tests.risk.test_dt_risk_integration.'

MUTATIONS = [
    # ---- M1 scoring (RD5, RI1)
    Mutation('M1-score-drops-a-component',
             ((SCO, "return delay_pts + history_late_pts + history_delay_pts + broken_pts + exposure_pts + reversed_pts + trend_pts",
               "return delay_pts + history_late_pts + history_delay_pts + broken_pts + exposure_pts + reversed_pts", 1),),
             (FACT + 'TestRI1MaximumScore.test_the_maximum_of_every_factor_together_reaches_exactly_100',)),
    # ---- M2 agrégation (RD2.2, RI2)
    Mutation('M2-aggregate-d-eo-drops-the-is-late-filter',
             ((AGG, "late = [f for f in open_invoices if f.is_open and f.is_late]", "late = [f for f in open_invoices if f.is_open]", 1),),
             (AGGT + 'TestAggregateDEo.test_no_late_invoice',)),
    # ---- M3 stabilisation / RP14 (RD7, RI8, RI9)
    Mutation('M3-stabilise-drops-the-hysteresis-reprieve',
             ((SCO, "    return max(raw, level_index(score + MARGIN))", "    return raw", 1),),
             (TAB + 'TestHysteresis.test_rl10_score_plus_margin_exactly_on_threshold_stays',)),
    # ---- M4 éligibilité (RD3, RI14)
    Mutation('M4-eligibility-always-true',
             ((PRO, "    return bool(has_ever_issued)", "    return True", 1),),
             (DEC + 'TestRC1NeverIssued.test_no_profile_is_ever_produced',)),
    # ---- M5 facteurs / points (RD4, RI2)
    Mutation('M5-broken-points-wrong-multiplier',
             ((SCO, "    return min(15, 5 * B)", "    return min(15, 4 * B)", 1),),
             (TAB + 'TestOtherFactors.test_broken_points_caps_at_15',)),
    # ---- M6 décision RD11 (RI5, RI11, RI12)
    Mutation('M6-steady-state-branch-disabled',
             ((PRO, "    if previous is not None and ni == previous.normalized_inputs:", "    if False and previous is not None and ni == previous.normalized_inputs:", 1),),
             (DEC + 'TestRN7SteadyState.test_identical_normalized_inputs_yields_an_empty_decision',)),
    # ---- M7 snapshot / RISK_CHANGED (RD11.2, RI10)
    Mutation('M7-event-emitted-without-a-level-change',
             ((PRO, "    if previous is not None and level != previous.level:", "    if previous is not None:", 1),),
             (DEC + 'TestRN8SameLevelDifferentInputs.test_a_write_without_an_event_when_the_level_does_not_change',)),
    # ---- M8 input_hash hors Domain (RD10.2, RI5bis)
    Mutation('M8-input-hash-becomes-a-constant',
             ((WIRE, "        h = input_hash_of(self.org, customer_id, ni)", "        h = 'x'", 1),),
             (INT + 'TestINT_R3_InputHash.test_one_changed_input_gives_a_new_hash_and_exactly_one_new_snapshot',)),
    # ---- M9 isolation tenant (TD17/TD26, RI15)
    Mutation('M9-events-leak-across-organizations',
             ((WIRE, "        return [e for e in self.world.outbox.events if e[0] == self.org]", "        return list(self.world.outbox.events)", 1),),
             (INT + 'TestINT_R6_TenantIsolation.test_a_risk_changed_produced_only_in_a_never_leaks_into_b',)),
    # ---- M10 atomicité profil/snapshot (DV2-9, RI16)
    Mutation('M10-snapshot-duplication-disabled',
             ((WIRE, "out[(org, 'risk_snapshots', snapshot_id)] = RiskSnapshotRow", "out[(org, 'risk_snapshots_off', snapshot_id)] = RiskSnapshotRow", 1),),
             (RUN + 'TestRP14ThroughTheRealRunner.test_three_calls_same_facts_two_writes_then_steady_state',)),
    # ---- M11 coureur / intégration (B5, RI17)
    Mutation('M11-a-declared-read-is-silently-dropped',
             ((WIRE, "Read('has_ever_issued', 'ever_issued_of_customer', key={'customer_id': cid}),\n           ", "", 1),),
             (RUN + 'TestTheSevenDeclaredReadsAreReallyWired.test_never_issued_customer_has_no_profile',)),
]
