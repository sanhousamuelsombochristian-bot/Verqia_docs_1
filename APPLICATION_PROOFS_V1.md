# VERQIA : Application Proofs V1

> Généré par `architecture_registry/verify_ap.py --doc` depuis `ap_catalogue.py` (les invariants), `ap_proofs.py` (les preuves) et `ap_mutations.py` (les mutations de code). Ne pas modifier à la main.
> **Porte de fermeture de la couche Application** : `verify_ap.py --run --mutate` exécute chaque preuve et tue chaque mutation.

Un invariant n'est pas couvert parce qu'un test existe quelque part : il l'est quand **(1)** une vérification statique le contrôle, **(2)** des tests le démontrent, **(3)** une mutation sait le casser et **(4)** chaque référence se résout, chaque test passe et chaque mutation est tuée. Un AP ajouté au catalogue sans sa preuve fait échouer la porte.

| Invariant | Statique | Tests | Injections de données | Mutations de code | Exécution |
|---|---|---:|---:|---:|---|
| AP-01 | A1 | 5 | 4 | 1 | `verify_ap.py --run --mutate` |
| AP-02 | A2 | 5 | 9 | 0 | `verify_ap.py --run --mutate` |
| AP-03 | A3 | 22 | 4 | 3 | `verify_ap.py --run --mutate` |
| AP-04 | A4 | 28 | 10 | 4 | `verify_ap.py --run --mutate` |
| AP-05 | A5 | 5 | 3 | 1 | `verify_ap.py --run --mutate` |
| AP-06 | A6, A10 | 7 | 7 | 2 | `verify_ap.py --run --mutate` |
| AP-07 | A7 | 21 | 2 | 5 | `verify_ap.py --run --mutate` |
| AP-08 | A8, A11 | 12 | 7 | 4 | `verify_ap.py --run --mutate` |
| AP-09 | H2, H | 9 | 13 | 0 | `verify_ap.py --run --mutate` |
| AP-10 | A11 | 16 | 5 | 4 | `verify_ap.py --run --mutate` |
| AP-11 | A10 | 7 | 2 | 2 | `verify_ap.py --run --mutate` |
| AP-12 | A9 | 6 | 2 | 2 | `verify_ap.py --run --mutate` |
| AP-13 | A11 | 27 | 4 | 6 | `verify_ap.py --run --mutate` |
| AP-14 | A12 | 23 | 6 | 3 | `verify_ap.py --run --mutate` |
| AP-15 | A13 | 25 | 5 | 3 | `verify_ap.py --run --mutate` |

```text
AP_COUNT    = 15
PROVEN_AP   = 15
UNTESTED_AP = 0
```

Les deux colonnes de mutations sont de nature différente : une **injection de données** corrompt les spécifications générées et exige que la vérification statique échoue ; une **mutation de code** retire une garde du coureur ou d'un double et exige que les tests désignés échouent. Une mutation dont le motif est introuvable est une erreur de la porte, jamais un succès.

## AP-01

Chaque entrée du Command Registry a exactement une spécification ; aucune spécification sans entrée

- **Statique** : `A1`
- **Tests** (5) : `reg:test_application.TestBaseline.test_application_contracts_are_faithful`; `reg:test_ap_gaps.TestAP01OneSpecPerEntry`; `run:application_runner.tests.test_lock_order.TestRunnerDrivesTheGeneratedSequence.test_an_unknown_use_case_is_refused`
- **Injections de données** (4 tests) : `reg:test_application.TestInjection.test_a1_*`; `reg:test_ap_gaps.TestAP01OneSpecPerEntry.test_an_orphan_spec_is_refused`
- **Mutations de code** (1) : `M-AP01-unknown-use-case-accepted`

## AP-02

Transaction, idempotence, événements, écritures et abonnements sont ceux du registre

- **Statique** : `A2`
- **Tests** (5) : `reg:test_application.TestBaseline`; `reg:test_ap_gaps.TestAP02Fidelity.test_the_real_specs_are_faithful`
- **Injections de données** (9 tests) : `reg:test_application.TestInjection.test_a2_*`; `reg:test_ap_gaps.TestAP02Fidelity.test_a_drift_of_*`
- **Mutations de code** (0) : —

## AP-03

La séquence de verrous est celle du Lock Registry, en rang strictement croissant sur l'échelle générée (jamais écrite à la main)

- **Statique** : `A3`
- **Tests** (22) : `run:application_runner.tests.test_lock_order`; `run:application_runner.tests.test_lock_derivation`
- **Injections de données** (4 tests) : `reg:test_application.TestInjection.test_a3_*`
- **Mutations de code** (3) : `M-AP03-rank-check-off`; `M-AP03-secondary-unit-keeps-the-key`; `M-AP03-runner-ignores-the-registry-mismatch`

## AP-04

Régime d'organisation : `REQUIRED` pour tout cas d'usage appelé, `EVENT` pour un handler, `ENUMERATOR` pour un travail ; exceptions fermées : relais d'outbox (`RELAY`), gestionnaire de partitions (`NONE`)

- **Statique** : `A4`
- **Tests** (28) : `run:application_runner.tests.test_tenant_context`; `reg:test_ap_gaps.TestAP04Regimes.test_the_real_specs_carry_the_six_regimes`
- **Injections de données** (10 tests) : `reg:test_application.TestInjection.test_a4_*`; `reg:test_application.TestReview.test_rv1_*`; `reg:test_ap_gaps.TestAP04Regimes.test_a_wrong_regime_is_refused_for_*`
- **Mutations de code** (4) : `M-AP04-rebind-allowed`; `M-AP04-missing-organization-accepted`; `M-AP04-system-sees-a-tenant`; `M-AP04-cross-tenant-detection-off`

## AP-05

Un code d'erreur cité existe à l'Annexe A ; aucune erreur inventée par un cas d'usage

- **Statique** : `A5`
- **Tests** (5) : `reg:test_application.TestBaseline.test_every_error_code_named_by_a_use_case_is_in_annex_a`; `run:application_runner.tests.test_ap_runner.TestAP05ErrorsComeFromTheCatalogue`; `run:application_runner.tests.test_p1_p3_transport.TestP2Context.test_a_principal_without_organization_is_refused_closed_with_the_catalogue_code`
- **Injections de données** (3 tests) : `reg:test_application.TestInjection.test_a5_*`; `reg:test_ap_gaps.TestAP05Catalogue.test_a_generic_invented_code_is_refused`
- **Mutations de code** (1) : `M-AP05-invented-error-code`

## AP-06

Toute commande **publique** (entrée `PUBLIC`, nature `command`) a un audit. Toute autre entrée (étape de provisioning, interne, réaction, travail) n'en produit un que si elle figure dans la liste nominative de D3 ; un audit conditionnel porte son motif

- **Statique** : `A6`, `A10`
- **Tests** (7) : `reg:test_ap_gaps.TestAP06Audit.test_every_public_command_requires_an_audit_and_no_other_entry_does_unless_named`; `run:application_runner.tests.test_p10_atomicity.TestTheSpecificationDecidesWhatADecisionMayContain`
- **Injections de données** (7 tests) : `reg:test_application.TestInjection.test_a6_*`; `reg:test_application.TestReview.test_rv2_*`; `reg:test_ap_gaps.TestAP06Audit.test_a_*`
- **Mutations de code** (2) : `M-AP06-required-audit-not-checked`; `M-AP06-forbidden-audit-accepted`

## AP-07

Écritures, événements, audit, idempotence et reçu forment une seule unité ; aucun effet externe n'y figure

- **Statique** : `A7`
- **Tests** (21) : `run:application_runner.tests.test_p10_atomicity`; `run:application_runner.tests.test_pipeline_transversal.TestAFaultAtEveryFrontier`
- **Injections de données** (2 tests) : `reg:test_application.TestInjection.test_a7_*`
- **Mutations de code** (5) : `M-AP07-event-written-immediately`; `M-AP07-audit-written-immediately`; `M-AP07-key-never-completed`; `M-AP07-receipt-not-written`; `M-AP07-external-effect-inside-the-transaction`

## AP-08

Tout appel inter-modules a : (1) une cible existante ; (2) une dépendance déclarée (TD10, pilotes `jobs` et `config` dispensés) ; (3) un sens compatible avec le graphe (jamais de retour vers un module qui dépend déjà de l'appelant) ; (4) une transaction compatible avec TD58 : tout `own:` a sa phase ; (5) une cible `own:` qui possède réellement l'état qu'elle écrit

- **Statique** : `A8`, `A11`
- **Tests** (12) : `run:application_runner.tests.test_p7_p8_p9.TestP9InterModuleCalls`; `reg:test_application.TestReview.test_rv8_*`
- **Injections de données** (7 tests) : `reg:test_application.TestInjection.test_a8_*`; `reg:test_application.TestReview.test_rv8_*`; `reg:test_application.TestReview.test_registry_and_application_agree_on_undeclared_own_calls`
- **Mutations de code** (4) : `M-AP08-undeclared-call-accepted`; `M-AP08-cross-module-read-accepted`; `M-AP08-state-ownership-off`; `M-AP08-own-callee-scope-unchecked`

## AP-09

Les spécifications sont de la donnée : ni fonction, ni contrôle de flux, ni cadre logiciel

- **Statique** : `H2`, `H`
- **Tests** (9) : `reg:test_ap_gaps.TestAP09DataOnly.test_the_real_specs_pass_the_data_only_whitelist`; `run:application_runner.tests.test_ap_runner.TestAP09SpecsAreData`; `reg:test_application.TestFreeze`
- **Injections de données** (13 tests) : `reg:test_application.TestInjection.test_h_*`; `reg:test_ap_gaps.TestAP09DataOnly.test_*_is_not_data`
- **Mutations de code** (0) : —

## AP-10

Réclamer → Effet → Finaliser. Un cas d'usage à réclamation (`CLAIM`) l'ouvre en première phase ; l'effet (`EFFECT`, dans la transaction du propriétaire, idempotent) n'est autorisé qu'après une réclamation valide ; `FINALIZE` clôt, dans le module de la réclamation, et ne finalise qu'une exécution dont la réclamation correspond

- **Statique** : `A11`
- **Tests** (16) : `run:application_runner.tests.test_ap_runner.TestAP10ClaimEffectFinalize`; `run:application_runner.tests.test_composition.TestT125IdempotentPhases`
- **Injections de données** (5 tests) : `reg:test_application.TestReview.test_rv6_*`
- **Mutations de code** (4) : `M-AP10-resume-without-claim-evidence`; `M-AP10-evidence-of-another-organization-accepted`; `M-AP10-evidence-of-another-use-case-accepted`; `M-AP10-a-claim-that-never-committed-is-evidence`

## AP-11

Les entrées sont distinguées : commande publique, étape de provisioning, interne, réaction, travail. Une étape de provisioning est un service idempotent par (organisation, étape), à verrou, dans sa transaction, sans audit direct

- **Statique** : `A10`
- **Tests** (7) : `run:application_runner.tests.test_p1_p3_transport.TestP1Transport`; `reg:test_ap_gaps.TestAP11Entries.test_the_real_entries_follow_the_nature`
- **Injections de données** (2 tests) : `reg:test_application.TestReview.test_rv3_*`; `reg:test_ap_gaps.TestAP11Entries.test_a_public_command_cannot_be_demoted_to_internal`
- **Mutations de code** (2) : `M-AP11-non-public-route-reachable`; `M-AP11-provisioning-steps-not-derived`

## AP-12

`REPLAY` n'existe que pour une commande ; les issues d'un handler sont celles de son reçu ; chaque nature n'a que ses issues (§3.1)

- **Statique** : `A9`
- **Tests** (6) : `run:application_runner.tests.test_p11_p12.TestP12IssuesAreValidatedAgainstTheSpecification`
- **Injections de données** (2 tests) : `reg:test_application.TestReview.test_rv7_*`
- **Mutations de code** (2) : `M-AP12-undeclared-outcome-accepted`; `M-AP12-replay-proposable-by-the-domain`

## AP-13

Un cas d'usage composé déclare ses phases ordonnées, une transaction chacune ; un effet extérieur n'est dans aucune transaction ; l'état d'un autre module n'est écrit que dans sa transaction (TD55, TD58)

- **Statique** : `A11`
- **Tests** (27) : `run:application_runner.tests.test_composition.TestT121SeparateTransactions`; `run:application_runner.tests.test_composition.TestT122TheOwnerOpensItsTransaction`; `run:application_runner.tests.test_composition.TestT123TenantAcrossPhases`; `run:application_runner.tests.test_composition.TestT124FailureOfALaterPhase`
- **Injections de données** (4 tests) : `reg:test_application.TestReview.test_rv4_*`; `reg:test_application.TestReview.test_rv5_*`
- **Mutations de code** (6) : `M-AP13-nested-units-allowed`; `M-AP13-single-begin-for-the-whole-composition`; `M-AP13-failure-rolls-back-earlier-phases`; `M-AP13-own-call-door-open`; `M-AP13-tenant-coherence-off`; `M-AP13-external-effect-in-transaction-allowed`

## AP-14

Portée d'idempotence, **typée** (`IdempotencyScope`, K2). Une commande qui insère la clé de requête `K` a la portée `ORGANIZATION` : `(organisation, clé, route)` (TD32). `CreateOrganization` est l'exception nommée : `(acteur, clé, route)`, consultée avant toute création ; sur rejeu, le résultat mémorisé est restitué et aucun identifiant n'est généré. La clé d'idempotence est une identité technique de requête et n'engendre jamais `organization_id`, identité métier

- **Statique** : `A12`
- **Tests** (23) : `run:application_runner.tests.test_idempotency`; `reg:test_application.TestIdempotencyScope.test_create_organization_is_actor_scoped_everything_else_is_organization_scoped`; `reg:test_application.TestIdempotencyScope.test_the_request_key_is_read_from_the_lock_operation_not_from_free_text`
- **Injections de données** (6 tests) : `reg:test_application.TestIdempotencyScope.test_actor_scope_*`; `reg:test_application.TestIdempotencyScope.test_a_*`
- **Mutations de code** (3) : `M-AP14-scope-id-ignored`; `M-AP14-actor-scope-detached-from-new`; `M-AP14-key-not-first-write`

## AP-15

Portée de transaction (K1). `TransactionScope` **`TENANT`** (`CallContext`, organisation obligatoire), **`SYSTEM`** (`SystemContext`, aucune organisation) ou **`NEW`** (`CreationContext`, organisation liée par `TenantContext.bind_new`). Elle est **déduite du régime d'organisation** par le contrat (`SCOPE_OF_TENANT`), jamais choisie par l'appelant : `SYSTEM` pour `RELAY` et `NONE`, `NEW` pour `NEW`. Ce sont trois régimes, pas trois variantes d'un `organization_id` nul : `CallContext.organization_id` reste obligatoire, et une fois liée l'organisation ne change plus dans l'unité de travail

- **Statique** : `A13`
- **Tests** (25) : `run:application_runner.tests.test_transaction_scope`; `run:application_runner.tests.test_tenant_context.TestT112SystemIsAReallyIsolated`; `reg:test_application.TestTransactionScope.test_exactly_two_use_cases_are_system`
- **Injections de données** (5 tests) : `reg:test_application.TestTransactionScope.test_a_required_command_cannot_be_system`; `reg:test_application.TestTransactionScope.test_the_relay_cannot_be_tenant`; `reg:test_application.TestTransactionScope.test_the_generated_scope_table_cannot_be_bent`; `reg:test_application.TestTransactionScope.test_create_organization_is_new_and_only_it`; `reg:test_application.TestTransactionScope.test_the_new_regime_cannot_be_folded_into_tenant_in_the_generated_table`
- **Mutations de code** (3) : `M-AP15-context-type-not-checked`; `M-AP15-scope-not-deduced-from-the-regime`; `M-AP15-bind-new-outside-a-new-unit`

