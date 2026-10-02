"""Registre des PREUVES des invariants du Risk Domain V1 : pour chaque invariant, ce qui le vérifie STATIQUEMENT, les
tests qui le démontrent et les mutations qui savent le casser. Un invariant n'est couvert que si la relation ci-dessous
est complète, que chaque test désigné se RÉSOUT et PASSE, et que chaque mutation désignée est TUÉE
(`verify_risk_domain.py --run --mutate`).

  static     règles statiques du Domain Risk : R-R1 imports (AR-01), R-R2 horloge/aléa/flottant (AR-02)
  tests      identifiants `domain_tests.risk.<module>.<Classe>[.<test>]` qui DÉMONTRENT l'invariant
  mutations  identifiants de `risk_mutations.py`
"""
TAB = 'domain_tests.risk.test_dt_risk_tables.'
AGG = 'domain_tests.risk.test_dt_risk_aggregation.'
DEC = 'domain_tests.risk.test_dt_risk_decisions.'
PRO = 'domain_tests.risk.test_dt_risk_properties.'
PUR = 'domain_tests.risk.test_dt_risk_purity.'
REF = 'domain_tests.risk.test_dt_risk_reference.'
RUN = 'domain_tests.risk.test_dt_risk_runner.'
INT = 'domain_tests.risk.test_dt_risk_integration.'
FAC = 'domain_tests.risk.test_dt_risk_facts.'

MONO = PRO + 'TestMonotonicity'
GOLDEN_G = REF + 'TestGoldenScoreCasesG1ToG5'

PROOFS = {
    'RI1': dict(static=(), tests=(FAC + 'TestRI1MaximumScore',), mutations=('M1-score-drops-a-component',)),
    'RI2': dict(static=(), tests=(TAB + 'TestDelayPoints', TAB + 'TestHistoryPoints', TAB + 'TestOtherFactors', AGG + 'TestAggregateDEo'),
                mutations=('M5-broken-points-wrong-multiplier', 'M2-aggregate-d-eo-drops-the-is-late-filter')),
    'RI3': dict(static=(), tests=(MONO,), mutations=('M5-broken-points-wrong-multiplier',)),
    'RI4': dict(static=(), tests=(TAB + 'TestHistoryPoints.test_ri4_below_minimum_sample_is_zero_on_both_components', TAB + 'TestOtherFactors.test_confidence_of'),
                mutations=('M5-broken-points-wrong-multiplier',)),
    'RI5': dict(static=(), tests=(DEC + 'TestRN7SteadyState', DEC + 'TestRN8SameLevelDifferentInputs', PRO + 'TestRP14StabilizesOnTheThirdCall'), mutations=('M6-steady-state-branch-disabled',)),
    'RI5bis': dict(static=(), tests=(INT + 'TestINT_R3_InputHash',), mutations=('M8-input-hash-becomes-a-constant',)),
    'RI6': dict(static=(), tests=(FAC + 'TestRI6BracketStabilityAndPreviousLevelSensitivity',), mutations=('M1-score-drops-a-component',)),
    'RI7': dict(static=(), tests=(FAC + 'TestRI7FactorsNeverCarryRawValuesOrSampleSize',), mutations=('M5-broken-points-wrong-multiplier',)),
    'RI8': dict(static=(), tests=(TAB + 'TestHysteresis', DEC + 'TestRN9LevelChange'), mutations=('M3-stabilise-drops-the-hysteresis-reprieve',)),
    'RI9': dict(static=(), tests=(PRO + 'TestRI9NoCapForRisk',), mutations=('M3-stabilise-drops-the-hysteresis-reprieve',)),
    'RI10': dict(static=(), tests=(DEC + 'TestRN6FirstCalculation', DEC + 'TestRN9LevelChange', INT + 'TestINT_R5_Events'), mutations=('M7-event-emitted-without-a-level-change',)),
    'RI11': dict(static=(), tests=(DEC + 'TestRN7SteadyState', DEC + 'TestRN8SameLevelDifferentInputs', DEC + 'TestRN9LevelChange'), mutations=('M6-steady-state-branch-disabled',)),
    'RI12': dict(static=(), tests=(DEC + 'TestRN6FirstCalculation.test_ri12_computed_at_never_appears_anywhere_in_the_decision',
                                    DEC + 'TestRN7SteadyState.test_ri12_an_unchanged_decision_is_totally_empty_and_carries_no_computed_at'),
                 mutations=('M6-steady-state-branch-disabled',)),
    'RI13': dict(static=('R-R2',), tests=(PRO + 'TestDeterminism', PUR + 'TestPurity'), mutations=('M4-eligibility-always-true',)),
    'RI14': dict(static=(), tests=(DEC + 'TestRC1NeverIssued', DEC + 'TestRN12AllVoidInvoices'), mutations=('M4-eligibility-always-true',)),
    'RI15': dict(static=(), tests=(INT + 'TestINT_R6_TenantIsolation',), mutations=('M9-events-leak-across-organizations',)),
    'RI16': dict(static=(), tests=(RUN + 'TestRP14ThroughTheRealRunner',), mutations=('M10-snapshot-duplication-disabled',)),
    'RI17': dict(static=('R-R1',), tests=(RUN + 'TestTheSevenDeclaredReadsAreReallyWired', PUR + 'TestContractFit'), mutations=('M11-a-declared-read-is-silently-dropped',)),
}
