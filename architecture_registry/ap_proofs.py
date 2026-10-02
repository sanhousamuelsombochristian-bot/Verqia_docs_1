"""Registre des PREUVES des invariants AP-01 à AP-15 : pour chaque invariant, ce qui le vérifie STATIQUEMENT, les tests qui le démontrent et les mutations qui savent le casser.

Un invariant n'est pas « couvert parce qu'un test existe quelque part » : il l'est quand la relation ci-dessous est complète, que chaque référence se RÉSOUT, que chaque test
PASSE et que chaque mutation est TUÉE (`verify_ap.py --run --mutate`). Ajouter un AP au catalogue sans sa preuve fait échouer la porte.

  static     codes de propriétés de `verify_application.py` (A1 à A13, H, H2)
  tests      tests qui DÉMONTRENT l'invariant (`reg:` = suite d'architecture_registry ; `run:` = suite du coureur ; `Classe.test_*` = motif)
  mutations  `inject:<test>` : test d'injection qui corrompt les DONNÉES générées et exige que la porte échoue ; `code:<id>` : mutation du code du coureur (`ap_mutations.py`)
"""
REG = 'reg:'
RUN = 'run:application_runner.tests.'
APP = REG + 'test_application.'
GAP = REG + 'test_ap_gaps.'

PROOFS = {
    'AP-01': dict(
        static=('A1',),
        tests=(APP + 'TestBaseline.test_application_contracts_are_faithful', GAP + 'TestAP01OneSpecPerEntry',
               RUN + 'test_lock_order.TestRunnerDrivesTheGeneratedSequence.test_an_unknown_use_case_is_refused'),
        mutations=('inject:' + APP + 'TestInjection.test_a1_*', 'inject:' + GAP + 'TestAP01OneSpecPerEntry.test_an_orphan_spec_is_refused',
                   'code:M-AP01-unknown-use-case-accepted')),
    'AP-02': dict(
        static=('A2',),
        tests=(APP + 'TestBaseline', GAP + 'TestAP02Fidelity.test_the_real_specs_are_faithful'),
        mutations=('inject:' + APP + 'TestInjection.test_a2_*', 'inject:' + GAP + 'TestAP02Fidelity.test_a_drift_of_*')),
    'AP-03': dict(
        static=('A3',),
        tests=(RUN + 'test_lock_order', RUN + 'test_lock_derivation'),
        mutations=('inject:' + APP + 'TestInjection.test_a3_*', 'code:M-AP03-rank-check-off', 'code:M-AP03-secondary-unit-keeps-the-key',
                   'code:M-AP03-runner-ignores-the-registry-mismatch')),
    'AP-04': dict(
        static=('A4',),
        tests=(RUN + 'test_tenant_context', GAP + 'TestAP04Regimes.test_the_real_specs_carry_the_six_regimes'),
        mutations=('inject:' + APP + 'TestInjection.test_a4_*', 'inject:' + APP + 'TestReview.test_rv1_*', 'inject:' + GAP + 'TestAP04Regimes.test_a_wrong_regime_is_refused_for_*',
                   'code:M-AP04-rebind-allowed', 'code:M-AP04-missing-organization-accepted', 'code:M-AP04-system-sees-a-tenant',
                   'code:M-AP04-cross-tenant-detection-off')),
    'AP-05': dict(
        static=('A5',),
        tests=(APP + 'TestBaseline.test_every_error_code_named_by_a_use_case_is_in_annex_a', RUN + 'test_ap_runner.TestAP05ErrorsComeFromTheCatalogue',
               RUN + 'test_p1_p3_transport.TestP2Context.test_a_principal_without_organization_is_refused_closed_with_the_catalogue_code'),
        mutations=('inject:' + APP + 'TestInjection.test_a5_*', 'inject:' + GAP + 'TestAP05Catalogue.test_a_generic_invented_code_is_refused',
                   'code:M-AP05-invented-error-code')),
    'AP-06': dict(
        static=('A6', 'A10'),
        tests=(GAP + 'TestAP06Audit.test_every_public_command_requires_an_audit_and_no_other_entry_does_unless_named',
               RUN + 'test_p10_atomicity.TestTheSpecificationDecidesWhatADecisionMayContain'),
        mutations=('inject:' + APP + 'TestInjection.test_a6_*', 'inject:' + APP + 'TestReview.test_rv2_*', 'inject:' + GAP + 'TestAP06Audit.test_a_*',
                   'code:M-AP06-required-audit-not-checked', 'code:M-AP06-forbidden-audit-accepted')),
    'AP-07': dict(
        static=('A7',),
        tests=(RUN + 'test_p10_atomicity', RUN + 'test_pipeline_transversal.TestAFaultAtEveryFrontier'),
        mutations=('inject:' + APP + 'TestInjection.test_a7_*', 'code:M-AP07-event-written-immediately', 'code:M-AP07-audit-written-immediately',
                   'code:M-AP07-key-never-completed', 'code:M-AP07-receipt-not-written', 'code:M-AP07-external-effect-inside-the-transaction')),
    'AP-08': dict(
        static=('A8', 'A11'),
        tests=(RUN + 'test_p7_p8_p9.TestP9InterModuleCalls', APP + 'TestReview.test_rv8_*'),
        mutations=('inject:' + APP + 'TestInjection.test_a8_*', 'inject:' + APP + 'TestReview.test_rv8_*', 'inject:' + APP + 'TestReview.test_registry_and_application_agree_on_undeclared_own_calls',
                   'code:M-AP08-undeclared-call-accepted', 'code:M-AP08-cross-module-read-accepted', 'code:M-AP08-state-ownership-off',
                   'code:M-AP08-own-callee-scope-unchecked')),
    'AP-09': dict(
        static=('H2', 'H'),
        tests=(GAP + 'TestAP09DataOnly.test_the_real_specs_pass_the_data_only_whitelist', RUN + 'test_ap_runner.TestAP09SpecsAreData', APP + 'TestFreeze'),
        mutations=('inject:' + APP + 'TestInjection.test_h_*', 'inject:' + GAP + 'TestAP09DataOnly.test_*_is_not_data')),
    'AP-10': dict(
        static=('A11',),
        tests=(RUN + 'test_ap_runner.TestAP10ClaimEffectFinalize', RUN + 'test_composition.TestT125IdempotentPhases'),
        mutations=('inject:' + APP + 'TestReview.test_rv6_*', 'code:M-AP10-resume-without-claim-evidence', 'code:M-AP10-evidence-of-another-organization-accepted',
                   'code:M-AP10-evidence-of-another-use-case-accepted', 'code:M-AP10-a-claim-that-never-committed-is-evidence')),
    'AP-11': dict(
        static=('A10',),
        tests=(RUN + 'test_p1_p3_transport.TestP1Transport', GAP + 'TestAP11Entries.test_the_real_entries_follow_the_nature'),
        mutations=('inject:' + APP + 'TestReview.test_rv3_*', 'inject:' + GAP + 'TestAP11Entries.test_a_public_command_cannot_be_demoted_to_internal',
                   'code:M-AP11-non-public-route-reachable', 'code:M-AP11-provisioning-steps-not-derived')),
    'AP-12': dict(
        static=('A9',),
        tests=(RUN + 'test_p11_p12.TestP12IssuesAreValidatedAgainstTheSpecification',),
        mutations=('inject:' + APP + 'TestReview.test_rv7_*', 'code:M-AP12-undeclared-outcome-accepted', 'code:M-AP12-replay-proposable-by-the-domain')),
    'AP-13': dict(
        static=('A11',),
        tests=(RUN + 'test_composition.TestT121SeparateTransactions', RUN + 'test_composition.TestT122TheOwnerOpensItsTransaction',
               RUN + 'test_composition.TestT123TenantAcrossPhases', RUN + 'test_composition.TestT124FailureOfALaterPhase'),
        mutations=('inject:' + APP + 'TestReview.test_rv4_*', 'inject:' + APP + 'TestReview.test_rv5_*', 'code:M-AP13-nested-units-allowed',
                   'code:M-AP13-single-begin-for-the-whole-composition', 'code:M-AP13-failure-rolls-back-earlier-phases', 'code:M-AP13-own-call-door-open',
                   'code:M-AP13-tenant-coherence-off', 'code:M-AP13-external-effect-in-transaction-allowed')),
    'AP-14': dict(
        static=('A12',),
        tests=(RUN + 'test_idempotency', APP + 'TestIdempotencyScope.test_create_organization_is_actor_scoped_everything_else_is_organization_scoped',
               APP + 'TestIdempotencyScope.test_the_request_key_is_read_from_the_lock_operation_not_from_free_text'),
        mutations=('inject:' + APP + 'TestIdempotencyScope.test_actor_scope_*', 'inject:' + APP + 'TestIdempotencyScope.test_a_*', 'code:M-AP14-scope-id-ignored',
                   'code:M-AP14-actor-scope-detached-from-new', 'code:M-AP14-key-not-first-write')),
    'AP-15': dict(
        static=('A13',),
        tests=(RUN + 'test_transaction_scope', RUN + 'test_tenant_context.TestT112SystemIsAReallyIsolated', APP + 'TestTransactionScope.test_exactly_two_use_cases_are_system'),
        mutations=('inject:' + APP + 'TestTransactionScope.test_a_required_command_cannot_be_system', 'inject:' + APP + 'TestTransactionScope.test_the_relay_cannot_be_tenant',
                   'inject:' + APP + 'TestTransactionScope.test_the_generated_scope_table_cannot_be_bent', 'inject:' + APP + 'TestTransactionScope.test_create_organization_is_new_and_only_it',
                   'inject:' + APP + 'TestTransactionScope.test_the_new_regime_cannot_be_folded_into_tenant_in_the_generated_table',
                   'code:M-AP15-context-type-not-checked', 'code:M-AP15-scope-not-deduced-from-the-regime', 'code:M-AP15-bind-new-outside-a-new-unit')),
}
