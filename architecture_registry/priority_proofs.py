"""Registre des PREUVES des invariants du Priority Domain V1 : pour chaque invariant, ce qui le vérifie
STATIQUEMENT, les tests qui le démontrent et les mutations qui savent le casser. Un invariant n'est couvert que si
la relation ci-dessous est complète, que chaque test désigné se RÉSOUT et PASSE, et que chaque mutation désignée
est TUÉE (`verify_priority_domain.py --run --mutate`).

  static     règles statiques du Domain Priority : P-R1 imports (AR-01-équivalent), P-R2 horloge/aléa/flottant (AR-02-équivalent)
  tests      identifiants `domain_tests.priority.<module>.<Classe>[.<test>]` qui DÉMONTRENT l'invariant
  mutations  identifiants de `priority_mutations.py`
"""
TAB = 'domain_tests.priority.test_dt_priority_tables.'
DEC = 'domain_tests.priority.test_dt_priority_decisions.'
PROP = 'domain_tests.priority.test_dt_priority_properties.'
PUR = 'domain_tests.priority.test_dt_priority_purity.'
REF = 'domain_tests.priority.test_dt_priority_reference.'
RUN = 'domain_tests.priority.test_dt_priority_runner.'
INT = 'domain_tests.priority.test_dt_priority_integration.'

PROOFS = {
    'PI1': dict(static=(), tests=(TAB + 'TestRankScore',), mutations=('PM1-rank-score-drops-attention',)),
    'PI2': dict(static=(), tests=(TAB + 'TestAmountPoints', TAB + 'TestDelayPoints', TAB + 'TestDuePoints', TAB + 'TestAttentionPoints', TAB + 'TestRiskPoints'),
                mutations=('PM2-amount-points-wrong-multiplier',)),
    'PI3': dict(static=(), tests=(PROP + 'TestMonotonicity',), mutations=('PM5-risk-level-ignored',)),
    'PI4': dict(static=(), tests=(PROP + 'TestRP14StyleStabilization', INT + 'TestINT_P5_Hysteresis'), mutations=('PM4-hysteresis-ignores-the-real-previous-level',)),
    'PI5': dict(static=(), tests=(REF + 'TestDecisionChainAgreesWithReferenceAndGolden',), mutations=('PM18-steady-state-branch-disabled',)),
    'PI5bis': dict(static=(), tests=(INT + 'TestINT_P2_Convergence',), mutations=('PM15-input-hash-becomes-a-constant',)),
    'PI6': dict(static=(), tests=(DEC + 'TestPI6ReasonsNeverCarryRawValues',), mutations=('PM19-reasons-factor-format-drops-the-pts-prefix',)),
    'PI7': dict(static=(), tests=(TAB + 'TestHysteresis', INT + 'TestINT_P4_LevelChange'), mutations=('PM3-stabilise-drops-the-hysteresis-reprieve',)),
    'PI8': dict(static=(), tests=(TAB + 'TestHysteresis.test_boundary_equality_stays_never_descends', INT + 'TestINT_P5_Hysteresis'), mutations=('PM12-threshold-boundary-shifted',)),
    'PI9': dict(static=(), tests=(DEC + 'TestPN5ToPN7Caps', INT + 'TestINT_P6_Caps'), mutations=('PM6-promise-or-hold-cap-removed', 'PM7-dispute-cap-condition-inverted')),
    'PI10': dict(static=(), tests=(REF + 'TestGoldenPriorityJsonSelfContainedFamilies.test_caps',), mutations=('PM7-dispute-cap-condition-inverted',)),
    'PI11': dict(static=(), tests=(INT + 'TestINT_P6_Caps.test_a_dispute_with_positive_collectible_is_not_derived_as_dispute_no_collectible',), mutations=('PM8-dispute-no-collectible-drops-the-collectible-check',)),
    'PI12': dict(static=(), tests=(DEC + 'TestPN5ToPN7Caps.test_pn7_reconciliation_signal_no_effect_on_score_or_level', INT + 'TestINT_P7_Reconciliation'), mutations=('PM9-reconciliation-pending-leaks-into-the-score',)),
    'PI13': dict(static=(), tests=(PROP + 'TestScoreChangesLevelDoesNot', INT + 'TestINT_P4_LevelChange'), mutations=('PM13-event-emitted-on-score-only-change',)),
    'PI14': dict(static=(), tests=(DEC + 'TestPN8FirstCalculation', REF + 'TestDecisionChainAgreesWithReferenceAndGolden'), mutations=('PM18-steady-state-branch-disabled',)),
    'PI15': dict(static=(), tests=(DEC + 'TestPN10DraftInvoice', DEC + 'TestPN9NonOpenInvoice', INT + 'TestINT_P13_ThreeEligibilityStatesThroughTheRealRunner'),
                 mutations=('PM10-draft-treated-as-active', 'PM11-closed-invoice-treated-as-active')),
    'PI16': dict(static=('P-R1', 'P-R2'), tests=(PROP + 'TestDeterminism', PUR + 'TestPurity'), mutations=('PM1-rank-score-drops-attention',)),
    'PI17': dict(static=(), tests=(RUN + 'TestScopeResolutionStaysOutOfTheDomain', INT + 'TestINT_P11_CustomerScope', INT + 'TestINT_P12_InvoiceScope'), mutations=('PM14-customer-batch-cap-removed',)),
    'PI18': dict(static=(), tests=(RUN + 'TestTenantIsolation', INT + 'TestINT_P9_TenantIsolation'), mutations=('PM16-events-leak-across-organizations',)),
    'PI19': dict(static=(), tests=(INT + 'TestINT_P8_RiskToPriorityRealComposition',), mutations=('PM17-the-risk-level-read-is-silently-dropped',)),
    'PI20': dict(static=('P-R1',), tests=(RUN + 'TestTheFiveDeclaredReadsAreReallyWired', PUR + 'TestContractFit'), mutations=('PM17-the-risk-level-read-is-silently-dropped',)),
}
