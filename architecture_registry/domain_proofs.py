"""Registre des PREUVES des invariants du Domain V1 (tranche 1) : pour chaque invariant, ce qui le vérifie STATIQUEMENT, les tests qui le démontrent et les mutations qui savent le casser.

Un invariant n'est pas « couvert parce qu'un test existe quelque part » : il l'est quand la relation ci-dessous est complète, que chaque test désigné se RÉSOUT et PASSE, et que
chaque mutation désignée est TUÉE (`verify_domain.py --run --mutate`). Ajouter un invariant au catalogue sans sa preuve fait échouer la porte.

  static     règles statiques du Domain : R-D1 imports, R-D2 horloge et aléa, R-D3 aucun flottant, R-D4 écritures par `derive_*`/`transition`, R-D5 faits financiers dans un module
  tests      identifiants `domain_tests.<module>.<Classe>[.<test>]` qui DÉMONTRENT l'invariant
  mutations  identifiants de `domain_mutations.py`
"""
DEC, REF, TAB, PRO, PUR = ('domain_tests.test_dt_%s.' % n for n in ('decisions', 'reference', 'tables_due', 'properties', 'purity_contracts'))
NOM, REFU, LIM = DEC + 'TestNominal', DEC + 'TestRefusals', DEC + 'TestLimits'
PROP = PRO + 'TestProperties.test_random_sequences_keep_every_invariant_and_every_refusal_is_closed'
GOLD = REF + 'TestGoldenTimelines'
FACTS = REF + 'TestFactsAgainstTheReference'
RUN = 'domain_tests.test_dt_runner.'
AGREES = RUN + 'TestTheRunnerAgreesWithTheMinimalInterpreter'        # le vrai coureur aboutit au meme etat, aux memes evenements, au meme historique
ALL_STATES = (PROP, GOLD)

PROOFS = {
    'IF1': dict(static=('R-D3',), tests=(REFU + '.test_c20_settlement_service_defends_the_bounds',) + ALL_STATES, mutations=('M-IF1-bounds-unchecked',)),
    'IF2': dict(static=('R-D4',), tests=(FACTS + '.test_settlement_and_status_match_the_reference',) + ALL_STATES, mutations=('M-IF2-partial-includes-total',)),
    'IF3': dict(static=('R-D4',), tests=(LIM + '.test_l23_settled_on_is_the_latest_value_date_whatever_the_order', PRO + 'TestProperties.test_settled_on_is_independent_of_the_order_of_allocation_for_every_permutation') + ALL_STATES,
                mutations=('M-IF3-settled-on-without-full-payment', 'M-IF3-settled-on-earliest-instead-of-latest')),
    'IF4': dict(static=('R-D4',), tests=(REFU + '.test_c20_settlement_service_defends_the_bounds', REFU + '.test_c5_c6_void_guards'), mutations=('M-IF4-positive-settlement-on-unpayable', 'M-IF4-void-with-payments')),
    'IF5': dict(static=(), tests=(REFU + '.test_c2_issue_guards_and_their_precedence',), mutations=('M-IF5-zero-total-issued',)),
    'IF6': dict(static=(), tests=(NOM + '.test_n2_to_n5_issue_and_catch_up',) + ALL_STATES, mutations=('M-IF6-issued-at-not-written',)),
    'IF7': dict(static=(), tests=(NOM + '.test_n18_to_n21_dispute_void_cancel',) + ALL_STATES, mutations=('M-IF7-cancel-reason-not-written',)),
    'IF8': dict(static=(), tests=(REFU + '.test_create_invoice_guards',), mutations=('M-IF8-dates-unchecked',)),
    'IF9': dict(static=('R-D3',), tests=(FACTS + '.test_line_rounding_matches_the_reference', LIM + '.test_l14_rounding', NOM + '.test_n1_create_invoice'), mutations=('M-IF9-rounding-down',)),
    'IF10': dict(static=(), tests=(NOM + '.test_n2_to_n5_issue_and_catch_up',) + ALL_STATES, mutations=('M-IF10-body-rewritten',)),
    'IF11': dict(static=('R-D4',), tests=(TAB + 'TestTransitionTables', TAB + 'TestTablesAgainstTheFrozenDocument', TAB + 'TestDueFunctions', PRO + 'TestProperties.test_the_lifecycle_never_goes_back_and_the_cycle_never_decreases'),
                 mutations=('M-IF11-lifecycle-can-go-back', 'M-IF11-due-soon-window-off-by-one')),
    'IF12': dict(static=(), tests=(NOM + '.test_n2_to_n5_issue_and_catch_up', NOM + '.test_n15_to_n17_reversals', PRO + 'TestProperties.test_the_lifecycle_never_goes_back_and_the_cycle_never_decreases') + ALL_STATES,
                 mutations=('M-IF12-cycle-incremented-by-two', 'M-IF12-rule-a-missing', 'M-IF12-rule-b-counted-twice')),
    'IF13': dict(static=(), tests=(PROP, GOLD, AGREES, RUN + 'TestGoldenTimelinesThroughTheRunner'), mutations=('M-IF13-scan-without-event',)),
    'IF14': dict(static=(), tests=(REFU + '.test_c5_c6_void_guards', NOM + '.test_n18_to_n21_dispute_void_cancel'), mutations=('M-IF14-void-with-open-dispute',)),
    'IF15': dict(static=(), tests=(REFU + '.test_c8_c19_dispute_guards',), mutations=('M-IF15-second-open-dispute',)),
    'IF16': dict(static=(), tests=(NOM + '.test_n6_to_n9_scans', GOLD), mutations=('M-IF16-scan-touches-paid-invoices', 'M-IF16-no-recalculation-after-reversal')),
    'IP1': dict(static=(), tests=(REFU + '.test_c9_to_c14_allocation_guards', PROP), mutations=('M-IP1-payment-overallocated',)),
    'IP2': dict(static=(), tests=(NOM + '.test_n15_to_n17_reversals', PROP, AGREES), mutations=('M-IP2-allocated-off-by-one',)),
    'IP3': dict(static=('R-D4',), tests=(FACTS + '.test_settlement_and_status_match_the_reference', NOM + '.test_n11_to_n14_allocations', PROP), mutations=('M-IP3-status-never-allocated',)),
    'IP4': dict(static=(), tests=(REFU + '.test_c13_c15_c17_reversal_guards',), mutations=('M-IP4-reversed-payment-accepts-allocation',)),
    'IP5': dict(static=(), tests=(NOM + '.test_n11_to_n14_allocations', PROP), mutations=('M-IP5-amount-rewritten',)),
    'IA1': dict(static=(), tests=(NOM + '.test_n15_to_n17_reversals', PROP), mutations=('M-IA1-reversal-without-reason',)),
    'IA2': dict(static=(), tests=(REFU + '.test_c13_c15_c17_reversal_guards',), mutations=('M-IA2-reversal-beyond-origin',)),
    'IA3': dict(static=(), tests=(REFU + '.test_c9_to_c14_allocation_guards',), mutations=('M-IA3-allocation-to-unpayable-invoice',)),
    'IA4': dict(static=(), tests=(REFU + '.test_c9_to_c14_allocation_guards',), mutations=('M-IA4-customer-unchecked',)),
    'IA5': dict(static=(), tests=(DEC + 'TestAppendOnlyRegistry',), mutations=('M-IA5-ledger-rewritten',)),
    'IA6': dict(static=(), tests=(REFU + '.test_c9_to_c14_allocation_guards', PROP), mutations=('M-IA6-invoice-overallocated',)),
    'IX1': dict(static=(), tests=(PROP, GOLD, AGREES, RUN + 'TestTheRealPipeline.test_all_or_nothing_across_payment_and_invoice_at_every_fault_point'), mutations=('M-IX1-reversal-adds-money',)),
    'IX2': dict(static=(), tests=(REFU + '.test_c9_to_c14_allocation_guards', PROP), mutations=('M-IP1-payment-overallocated',)),
    'IX3': dict(static=(), tests=(NOM + '.test_n15_to_n17_reversals', PRO + 'TestProperties.test_reverse_payment_returns_every_touched_invoice_to_its_previous_sums'),
                mutations=('M-IX3-reverse-payment-forgets-allocations',)),
    'IN1': dict(static=('R-D2',), tests=(PRO + 'TestProperties.test_every_decision_is_deterministic', LIM + '.test_l25_the_same_input_gives_the_same_decision', AGREES), mutations=('M-IN1-nondeterministic-result',)),
    'IN2': dict(static=(), tests=(PUR + 'TestPurity.test_the_input_state_is_read_only', LIM + '.test_a_decision_never_mutates_its_input'), mutations=('M-IN2-input-mutated',)),
    'IN3': dict(static=('R-D2',), tests=(PUR + 'TestPurity.test_ar02_no_clock_no_float_no_randomness_no_io', PUR + 'TestPurity.test_a_full_scenario_never_touches_the_clock_or_randomness',
                                          TAB + 'TestDueFunctions.test_local_day_in_the_organisation_timezone', TAB + 'TestDueFunctions.test_same_local_day_gives_the_same_decision_whatever_the_hour'),
                mutations=('M-IN3-utc-day-instead-of-local-day',)),
    'IN4': dict(static=(), tests=(PROP, GOLD), mutations=('M-IF6-issued-at-not-written', 'M-IF7-cancel-reason-not-written')),
    'IN5': dict(static=('R-D1',), tests=(PUR + 'TestContractFit', PUR + 'TestPurity.test_ar01_domain_imports_only_the_standard_library_the_kernel_and_contracts'), mutations=('M-IN5-undeclared-event',)),
}
