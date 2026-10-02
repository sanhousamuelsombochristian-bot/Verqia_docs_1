"""Mutations de CODE du coureur et de ses doubles : chacune retire UNE garde d'un invariant AP ; les tests désignés doivent alors ÉCHOUER.

Une mutation dont le motif est introuvable est une ERREUR de la porte (jamais un « OK ») : c'est ce qui manquait quand une mutation mal appliquée avait laissé passer une suite verte.
Les mutations de DONNÉES (spécifications générées) sont les tests d'injection de `test_application.py` : ils figurent au registre des preuves sous `inject:`.

Format : Mutation(id, ap, edits, kill) ; `edits` = ((fichier relatif à verqia-app, motif, remplacement, occurrences attendues), ...) ; `kill` = tests du coureur qui doivent tomber.
"""
from collections import namedtuple

Mutation = namedtuple('Mutation', 'id ap edits kill')

R = 'application_runner/runner.py'
T = 'application_runner/transport.py'
LOCKS = 'application_runner/doubles/locks.py'
TENANT = 'application_runner/doubles/tenant.py'
TX = 'application_runner/doubles/transaction.py'
STORE = 'application_runner/doubles/store.py'
IDEM = 'application_runner/doubles/idempotency.py'
P = 'application_runner.tests.'

MUTATIONS = [
    Mutation('M-AP01-unknown-use-case-accepted', 'AP-01',
             ((R, "            raise ArchitectureViolation('unknown_use_case', '%s.%s' % (module, name))", "            return None", 3),),
             (P + 'test_lock_order.TestRunnerDrivesTheGeneratedSequence.test_an_unknown_use_case_is_refused',)),
    # ---------------------------------------------------------------------------------------------- AP-03 verrous
    Mutation('M-AP03-rank-check-off', 'AP-03', ((LOCKS, "        if rank <= uow.last_rank:", "        if False:", 1),), (P + 'test_lock_order.TestLadderComesFromTheRegistry',)),
    Mutation('M-AP03-secondary-unit-keeps-the-key', 'AP-03',
             ((R, "        return tuple(registered) if first else tuple(step for step in registered if step[1] != KEY_MODE)", "        return tuple(registered)", 1),),
             (P + 'test_lock_derivation', P + 'test_composition.TestT121SeparateTransactions.test_the_request_key_belongs_to_the_first_unit_only')),
    Mutation('M-AP03-runner-ignores-the-registry-mismatch', 'AP-03',
             ((R, "        if tuple(spec.lock_sequence) != tuple(registered):", "        if False:", 1),), (P + 'test_lock_derivation.TestDerivedFromTheRegistry.test_a_specification_that_no_longer_matches_the_registry_is_refused_before_any_transaction',)),
    # ---------------------------------------------------------------------------------------------- AP-04 régimes d'organisation
    Mutation('M-AP04-rebind-allowed', 'AP-04',
             ((TENANT, "        elif self._organization != organization:", "        elif False:", 1),), (P + 'test_tenant_context.TestT114Immutability',)),
    Mutation('M-AP04-missing-organization-accepted', 'AP-04',
             ((R, "        if isinstance(ctx, CallContext) and ctx.organization_id is None:", "        if False:", 2),
              (TX, "        if scope is TransactionScope.TENANT and organization is None:", "        if False:", 1),
              (TENANT, "        if organization is None:\n            raise ArchitectureViolation('tenant_absent', \"organisation absente : refus fermé, aucune organisation par défaut (TD17)\")\n", "", 1)),
             (P + 'test_tenant_context.TestT111ClosedRefusal',)),
    Mutation('M-AP04-system-sees-a-tenant', 'AP-04',
             ((TENANT, "        if self._scope is TransactionScope.SYSTEM:\n            raise ArchitectureViolation('tenant_absent', \"unité SYSTEM : aucun accès tenant (K1)\")\n",
               "        if self._scope is TransactionScope.SYSTEM:\n            return OrganizationId(__import__('uuid').UUID(int=1))\n", 1),),
             (P + 'test_tenant_context.TestT112SystemIsAReallyIsolated',)),
    Mutation('M-AP04-cross-tenant-detection-off', 'AP-04',
             ((STORE, "if not isinstance(ctx, CallContext) or ctx.organization_id != organization:", "if False:", 2),), (P + 'test_tenant_context.TestCrossTenantCalls',)),
    # ---------------------------------------------------------------------------------------------- AP-05 erreurs du catalogue
    Mutation('M-AP05-invented-error-code', 'AP-05',
             ((T, "def coerce(value: object, hint: object, path: str):", "def _invented():\n    return domain_error('GENERIC_INVALID_INPUT')\n\n\ndef coerce(value: object, hint: object, path: str):", 1),),
             (P + 'test_ap_runner.TestAP05ErrorsComeFromTheCatalogue',)),
    # ---------------------------------------------------------------------------------------------- AP-06 audit
    Mutation('M-AP06-required-audit-not-checked', 'AP-06',
             ((R, "        if spec.audit.value == 'REQUIRED' and not decision.audit:", "        if False:", 1),), (P + 'test_p10_atomicity.TestTheSpecificationDecidesWhatADecisionMayContain',)),
    Mutation('M-AP06-forbidden-audit-accepted', 'AP-06',
             ((R, "        if spec.audit.value == 'NONE' and decision.audit:", "        if False:", 1),), (P + 'test_p10_atomicity.TestTheSpecificationDecidesWhatADecisionMayContain',)),
    # ---------------------------------------------------------------------------------------------- AP-07 atomicité
    Mutation('M-AP07-event-written-immediately', 'AP-07',
             ((STORE, "        self.tx.current.on_commit.append(lambda: self.events.append(row))", "        self.events.append(row)", 1),), (P + 'test_p10_atomicity',)),
    Mutation('M-AP07-audit-written-immediately', 'AP-07',
             ((STORE, "        self.tx.current.on_commit.append(lambda: self.rows.append(row))", "        self.rows.append(row)", 1),), (P + 'test_p10_atomicity',)),
    Mutation('M-AP07-key-never-completed', 'AP-07',
             ((R, "        if first:\n            self._complete_key(spec, ctx, decision.result, organization)\n        if spec.kind == 'handler':", "        if spec.kind == 'handler':", 1),), (P + 'test_p10_atomicity',)),
    Mutation('M-AP07-receipt-not-written', 'AP-07',
             ((R, "            self.world.receipts.record(event_id, handler_name, outcome)", "            pass", 1),), (P + 'test_p10_atomicity.TestHandlerAtomicity',)),
    Mutation('M-AP07-external-effect-inside-the-transaction', 'AP-07',
             ((R, "                    self._apply(spec, phase, ctx, decision, first, organization, event_id, handler_name, outcome, served)\n",
               "                    self._apply(spec, phase, ctx, decision, first, organization, event_id, handler_name, outcome, served)\n                    self._external_effects(decision)\n", 1),),
             (P + 'test_p11_p12.TestP11AfterCommit',)),
    # ---------------------------------------------------------------------------------------------- AP-08 inter-modules
    Mutation('M-AP08-undeclared-call-accepted', 'AP-08',
             ((R, "        if self.spec is None or (target not in self.spec.reads and target not in self.spec.cross_module):", "        if False:", 1),), (P + 'test_p7_p8_p9.TestP9InterModuleCalls',)),
    Mutation('M-AP08-cross-module-read-accepted', 'AP-08',
             ((R, "        if self.spec is not None and state_key.split('.', 1)[0] != self.spec.module and state_key not in self.spec.domain:", "        if False:", 1),),
             (P + 'test_p7_p8_p9.TestP9InterModuleCalls',)),
    Mutation('M-AP08-state-ownership-off', 'AP-08',
             ((R, "    if state_key not in allowed or (owner != spec.module and owner not in same_tx_modules):", "    if False:", 1),),
             (P + 'test_p7_p8_p9.TestP9InterModuleCalls', P + 'test_composition.TestT122TheOwnerOpensItsTransaction')),
    Mutation('M-AP08-own-callee-scope-unchecked', 'AP-08',
             ((R, "                if callee.transaction_scope is not TransactionScope.TENANT:", "                if False:", 1),),
             (P + 'test_composition.TestT123TenantAcrossPhases.test_an_own_call_must_target_an_organization_unit',)),
    # ---------------------------------------------------------------------------------------------- AP-10 réclamer, agir, finaliser
    Mutation('M-AP10-resume-without-claim-evidence', 'AP-10',
             ((R, "            self._check_claim_evidence(spec, claim, comp, progress)", "            pass", 1),), (P + 'test_ap_runner.TestAP10ClaimEffectFinalize',)),
    Mutation('M-AP10-evidence-of-another-organization-accepted', 'AP-10',
             ((R, "        if progress.organization != comp.organization:", "        if False:", 1),), (P + 'test_ap_runner.TestAP10ClaimEffectFinalize',)),
    Mutation('M-AP10-evidence-of-another-use-case-accepted', 'AP-10',
             ((R, "        if progress is None or (progress.module, progress.name) != (spec.module, spec.name):", "        if False:", 1),), (P + 'test_ap_runner.TestAP10ClaimEffectFinalize',)),
    Mutation('M-AP10-a-claim-that-never-committed-is-evidence', 'AP-10',
             ((R, "        if record is None or not record.units:", "        if False:", 1),), (P + 'test_ap_runner.TestAP10ClaimEffectFinalize',)),
    # ---------------------------------------------------------------------------------------------- AP-11 entrées
    Mutation('M-AP11-non-public-route-reachable', 'AP-11',
             ((T, "        if spec.entry.value != 'PUBLIC':", "        if False:", 1),), (P + 'test_p1_p3_transport.TestP1Transport',)),
    Mutation('M-AP11-provisioning-steps-not-derived', 'AP-11',
             ((R, "                    steps += [Step(k) for k, s in self.specs.items() if 'implémente:' + target in s.cross_module]", "                    steps += []", 1),),
             (P + 'test_composition.TestT123TenantAcrossPhases.test_a_new_composition_establishes_the_identity_in_the_first_phase_then_keeps_it',)),
    # ---------------------------------------------------------------------------------------------- AP-12 issues
    Mutation('M-AP12-undeclared-outcome-accepted', 'AP-12',
             ((R, "        if proposed is not None and proposed not in spec.outcomes:", "        if False:", 1),), (P + 'test_p11_p12.TestP12IssuesAreValidatedAgainstTheSpecification',)),
    Mutation('M-AP12-replay-proposable-by-the-domain', 'AP-12',
             ((R, "        if proposed == 'REPLAY':", "        if False:", 1),), (P + 'test_p11_p12.TestP12IssuesAreValidatedAgainstTheSpecification',)),
    # ---------------------------------------------------------------------------------------------- AP-13 composition : une transaction par phase
    Mutation('M-AP13-nested-units-allowed', 'AP-13',
             ((TENANT, "        if self._scope is not None:\n            raise ArchitectureViolation('unit_already_open'", "        if False:\n            raise ArchitectureViolation('unit_already_open'", 1),),
             (P + 'test_composition.TestT121SeparateTransactions',)),
    Mutation('M-AP13-single-begin-for-the-whole-composition', 'AP-13',
             ((TENANT, "        if self._scope is not None:\n            raise ArchitectureViolation('unit_already_open'", "        if False:\n            raise ArchitectureViolation('unit_already_open'", 1),
               (TX, "        expected = CONTEXT_OF_SCOPE.get(scope)\n", "        if self.current is not None:\n            yield\n            return\n        expected = CONTEXT_OF_SCOPE.get(scope)\n", 1),
               (R, "        unit_started = False\n        claim = next(", "        unit_started = False\n        if isinstance(ctx, CallContext):\n            self.world.tx.atomic(ctx, isolation, spec.transaction_scope).__enter__()\n        claim = next(", 1)),
             (P + 'test_composition.TestT121SeparateTransactions',)),
    Mutation('M-AP13-failure-rolls-back-earlier-phases', 'AP-13',
             ((R, "                if not comp.units():\n                    raise", "                self.world.tx.committed.clear(); self.world.store.tenant_rows.clear()\n                if not comp.units():\n                    raise", 1),),
             (P + 'test_composition.TestT124FailureOfALaterPhase',)),
    Mutation('M-AP13-own-call-door-open', 'AP-13',
             ((R, "        raise ArchitectureViolation('own_inside_transaction', \"un appel `own:` ne s'exécute jamais dans la transaction de l'appelant : c'est une frontière de composition (TD58)\")", "        return None", 1),),
             (P + 'test_composition.TestT122TheOwnerOpensItsTransaction.test_an_own_call_has_no_door_inside_a_unit_of_work',)),
    Mutation('M-AP13-tenant-coherence-off', 'AP-13',
             ((R, "                if org != comp.organization:", "                if False:", 1),), (P + 'test_composition.TestT123TenantAcrossPhases',)),
    Mutation('M-AP13-external-effect-in-transaction-allowed', 'AP-13',
             ((R, "            if self.world.tx.current is not None:\n                raise ArchitectureViolation('external_inside_transaction', \"un effet extérieur n'a lieu dans aucune transaction (TD31)\")\n            try:", "            try:", 1),
              ("application_runner/doubles/external.py", "        if self.tx.current is not None:\n            raise ArchitectureViolation('external_inside_transaction', \"aucun effet extérieur dans une transaction (TD31) : d'abord le COMMIT\")\n", "", 1)),
             (P + 'test_p11_p12.TestP11AfterCommit.test_the_provider_refuses_any_call_made_inside_a_unit_of_work',)),
    # ---------------------------------------------------------------------------------------------- AP-14 idempotence typée
    Mutation('M-AP14-scope-id-ignored', 'AP-14',
             ((IDEM, "        k = (scope, scope_id, key, route)\n", "        k = (scope, None, key, route)\n", 1), (IDEM, "uow.pending.get((scope, scope_id, key, route))", "uow.pending.get((scope, None, key, route))", 1)),
             (P + 'test_idempotency',)),
    Mutation('M-AP14-actor-scope-detached-from-new', 'AP-14',
             ((R, "        if (spec.tenant is TenantMode.NEW) != (scope is IdempotencyScope.ACTOR):", "        if False:", 1),), (P + 'test_idempotency.TestScopeConsistency',)),
    Mutation('M-AP14-key-not-first-write', 'AP-14',
             ((IDEM, "        if uow.last_rank >= LR.RANK[resource]:", "        if False:", 1),), (P + 'test_idempotency.TestKeyedCommands.test_a_key_inserted_after_another_lock_is_refused',)),
    # ---------------------------------------------------------------------------------------------- AP-15 portée de transaction
    Mutation('M-AP15-context-type-not-checked', 'AP-15',
             ((TX, "        if not isinstance(ctx, expected):", "        if False:", 1),), (P + 'test_transaction_scope', P + 'test_tenant_context')),
    Mutation('M-AP15-scope-not-deduced-from-the-regime', 'AP-15',
             ((R, "        if SCOPE_OF_TENANT[spec.tenant] is not spec.transaction_scope:", "        if False:", 1),), (P + 'test_transaction_scope.TestScopeIsFixedByTheContract',)),
    Mutation('M-AP15-bind-new-outside-a-new-unit', 'AP-15',
             ((TENANT, "        if self._scope is not TransactionScope.NEW:\n            raise ArchitectureViolation('bind_new_forbidden'", "        if False:\n            raise ArchitectureViolation('bind_new_forbidden'", 1),),
             (P + 'test_tenant_context.TestT113NewRegime',)),
]
