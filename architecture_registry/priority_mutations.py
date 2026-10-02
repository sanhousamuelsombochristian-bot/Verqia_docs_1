"""Mutations de CODE du Priority Domain V1 : chacune retire ou corrompt UNE règle ; les tests désignés doivent alors
ÉCHOUER (« tuer » la mutation). Format : Mutation(id, edits, kill) ; `edits` = ((fichier relatif à verqia-app, motif,
remplacement, occurrences attendues), ...) ; `kill` = identifiants de tests de `domain_tests` qui doivent tomber.

PM1-PM11 mutent le Domain PUR (`verqia/priority/domain/*.py`, futur périmètre du gel Priority). PM12-PM15 mutent
délibérément le HARNAIS (`domain_tests/priority/runner_wiring.py`) : ce n'est pas encore un module Application réel,
mais c'est aujourd'hui la SEULE représentation exécutable de la façon dont l'Application assemble/persiste les faits
Priority — une régression y introduite est exactement ce qu'une vraie régression d'Application produirait (§ PI5bis,
PI17, PI18, PI20 de `priority_catalogue.py`). La relation invariant → mutations est dans `priority_proofs.py`.
"""
from collections import namedtuple

Mutation = namedtuple('Mutation', 'id edits kill')

SCO = 'verqia/priority/domain/scoring.py'
FAC = 'verqia/priority/domain/facts.py'
MOD = 'verqia/priority/domain/model.py'
PRO = 'verqia/priority/domain/profile.py'
WIRE = 'domain_tests/priority/runner_wiring.py'

TAB = 'domain_tests.priority.test_dt_priority_tables.'
DEC = 'domain_tests.priority.test_dt_priority_decisions.'
PROP = 'domain_tests.priority.test_dt_priority_properties.'
REF = 'domain_tests.priority.test_dt_priority_reference.'
RUN = 'domain_tests.priority.test_dt_priority_runner.'
INT = 'domain_tests.priority.test_dt_priority_integration.'

MUTATIONS = [
    # ---- PM1 barème / score maximum (PD5, PI1)
    Mutation('PM1-rank-score-drops-attention',
             ((SCO, "    return amount_pts + delay_pts + risk_pts + due_pts + attention_pts", "    return amount_pts + delay_pts + risk_pts + due_pts", 1),),
             (TAB + 'TestRankScore.test_maximum_is_exactly_95',)),
    # ---- PM2 facteur montant (PD4, PI2)
    Mutation('PM2-amount-points-wrong-multiplier',
             ((SCO, "    return min(30, (A * 30) // C)", "    return min(30, (A * 20) // C)", 1),),
             (TAB + 'TestAmountPoints.test_brackets',)),
    # ---- PM3 hystérésis (PD7, PI7/PI8)
    Mutation('PM3-stabilise-drops-the-hysteresis-reprieve',
             ((SCO, "    return max(raw, level_index(score + MARGIN))", "    return raw", 1),),
             (TAB + 'TestHysteresis.test_boundary_equality_stays_never_descends',)),
    # ---- PM4 previous_level ignoré par l'hystérésis (PD7, PI4)
    Mutation('PM4-hysteresis-ignores-the-real-previous-level',
             ((PRO, "        stabilised = stabilise(raw_score, level_index_of(previous_level))", "        stabilised = stabilise(raw_score, None)", 1),),
             (INT + 'TestINT_P5_Hysteresis.test_the_margin_boundary_holds_then_descends_through_real_recomputes',)),
    # ---- PM5 risque ignoré (PD4, PI3)
    Mutation('PM5-risk-level-ignored',
             ((SCO, "RISK_PTS = {'LOW': 0, 'MEDIUM': 8, 'HIGH': 17, 'CRITICAL': 25, None: 5}", "RISK_PTS = {'LOW': 5, 'MEDIUM': 5, 'HIGH': 5, 'CRITICAL': 5, None: 5}", 1),),
             (DEC + 'TestPN1ToPN4GoldenCases.test_pn1_critical',)),
    # ---- PM6 plafond promesse/hold retiré (§3.4, PI9)
    Mutation('PM6-promise-or-hold-cap-removed',
             ((SCO, "    if promise_or_hold:", "    if False:", 1),),
             (DEC + 'TestPN5ToPN7Caps.test_pn5_promise_caps_at_watch',)),
    # ---- PM7 condition du plafond litige inversée (§3.4, PI9)
    Mutation('PM7-dispute-cap-condition-inverted',
             ((SCO, "    if dispute_no_collectible:", "    if not dispute_no_collectible:", 1),),
             (DEC + 'TestPN5ToPN7Caps.test_pn6_dispute_caps_at_action',)),
    # ---- PM8 dérivation dispute_no_collectible tronquée (§ DV3-5, PI11)
    Mutation('PM8-dispute-no-collectible-drops-the-collectible-check',
             ((PRO, "    return invoice.has_open_dispute and invoice.collectible_minor == 0", "    return invoice.has_open_dispute", 1),),
             (INT + 'TestINT_P6_Caps.test_a_dispute_with_positive_collectible_is_not_derived_as_dispute_no_collectible',)),
    # ---- PM9 réconciliation affecte le score (PD9, PI12)
    Mutation('PM9-reconciliation-pending-leaks-into-the-score',
             ((FAC, "        amount_pts=amount_points(A, C), delay_pts=delay_pts, risk_pts=risk_points(risk_level),",
               "        amount_pts=amount_points(A, C) + (1 if reconciliation_pending else 0), delay_pts=delay_pts, risk_pts=risk_points(risk_level),", 1),),
             (DEC + 'TestPN5ToPN7Caps.test_pn7_reconciliation_signal_no_effect_on_score_or_level',)),
    # ---- PM10 DRAFT traité comme actif (PD3, PI15)
    Mutation('PM10-draft-treated-as-active',
             ((PRO, "    return invoice.lifecycle_state == 'DRAFT'", "    return False", 1),),
             (DEC + 'TestPN10DraftInvoice.test_no_writes_no_events',)),
    # ---- PM11 facture fermée traitée comme active (PD3, PI15)
    Mutation('PM11-closed-invoice-treated-as-active',
             ((PRO, "    if not invoice.is_open:", "    if False:", 1),),
             (DEC + 'TestPN9NonOpenInvoice.test_none_closed_is_a_real_write_not_an_absence_of_decision',)),
    # ---- PM12 frontière de seuil déplacée (PD6, PI8)
    Mutation('PM12-threshold-boundary-shifted',
             ((MOD, "THRESHOLDS = (0, 20, 40, 60, 80)        # PD6", "THRESHOLDS = (0, 20, 40, 61, 80)        # PD6", 1),),
             (TAB + 'TestLevels.test_the_five_thresholds',)),
    # ---- PM13 PRIORITY_CHANGED émis sur un changement de score seul (PD11.2, PI13)
    Mutation('PM13-event-emitted-on-score-only-change',
             ((PRO, "    if previous is not None and level != previous.level:                                           # PD11.2, § DV2-7-équivalent",
               "    if previous is not None:                                           # PD11.2, § DV2-7-équivalent", 1),),
             (PROP + 'TestScoreChangesLevelDoesNot.test_a_small_amount_change_within_the_same_bracket_writes_without_an_event',)),
    # ---- PM14 lot CUSTOMER non borné (§ DV3-9/PD11.5, PI17)
    Mutation('PM14-customer-batch-cap-removed',
             ((WIRE, "if f.customer_id == event.customer_id and f.is_open][:200]", "if f.customer_id == event.customer_id and f.is_open]", 1),),
             (RUN + 'TestScopeResolutionStaysOutOfTheDomain.test_pr14_customer_scope_is_capped_at_two_hundred',)),
    # ---- PM15 input_hash devient une constante, hors Domain (PD10.2, PI5bis)
    Mutation('PM15-input-hash-becomes-a-constant',
             ((WIRE, "        h = input_hash_of(self.org, invoice_id, ni)", "        h = 'x'", 1),),
             (INT + 'TestINT_P2_Convergence.test_one_changed_input_gives_a_new_hash_and_exactly_one_new_snapshot',)),
    # ---- PM16 isolation tenant : événements fuient entre organisations (TD17/TD26, PI18)
    Mutation('PM16-events-leak-across-organizations',
             ((WIRE, "        return [e for e in self.world.outbox.events if e[0] == self.org]", "        return list(self.world.outbox.events)", 1),),
             (INT + 'TestINT_P9_TenantIsolation.test_a_priority_changed_produced_only_in_a_never_leaks_into_b',)),
    # ---- PM17 une lecture déclarée (DV3-8/B6) discrètement supprimée du coureur (PI19/PI20)
    Mutation('PM17-the-risk-level-read-is-silently-dropped',
             ((WIRE, "           Read('risk_level', 'risk_level_of_invoice', key={'invoice_id': iid}),                      # risk.RiskLevel\n", "", 1),),
             (RUN + 'TestTheFiveDeclaredReadsAreReallyWired.test_pr01_invoice_facts_reach_the_domain_through_the_declared_read',)),
    # ---- PM18 régime stationnaire désactivé (PD11.1, PI5/PI14)
    Mutation('PM18-steady-state-branch-disabled',
             ((PRO, "    if previous is not None and ni == previous.normalized_inputs:", "    if False and previous is not None and ni == previous.normalized_inputs:", 1),),
             (REF + 'TestDecisionChainAgreesWithReferenceAndGolden.test_the_eight_step_scenario',)),
    # ---- PM19 `reasons.factors` perd son format normalisé prescrit (PD10.2, PI6)
    Mutation('PM19-reasons-factor-format-drops-the-pts-prefix',
             ((FAC, "'normalized_input': 'pts=%d' % pts} for name, pts in rows]", "'normalized_input': '%d' % pts} for name, pts in rows]", 1),),
             (DEC + 'TestPI6ReasonsNeverCarryRawValues.test_every_factor_is_a_normalized_points_string',)),
]
