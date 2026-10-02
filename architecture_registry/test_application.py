"""Registry ↔ Application : baseline verte, puis INJECTION de violations sur une copie : chaque propriété A1..A8 et l'hygiène doivent échouer.

Lancement : python -m unittest test_application (dans architecture_registry/)
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_contracts as G  # noqa: E402
import verify_application as V  # noqa: E402

REAL = G.DEFAULT_OUT


def read(root, rel):
    with io.open(os.path.join(root, rel.replace('/', os.sep)), encoding='utf-8', newline='') as f:
        return f.read()


def write(root, rel, text):
    with io.open(os.path.join(root, rel.replace('/', os.sep)), 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def errors_after(mutate):
    tmp = tempfile.mkdtemp(prefix='verqia_application_')
    try:
        shutil.copytree(os.path.join(REAL, 'verqia'), os.path.join(tmp, 'verqia'), ignore=shutil.ignore_patterns('__pycache__'))
        mutate(tmp)
        errors, _ = V.verify(tmp)
        return errors
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sub(rel, old, new, count=1):
    def f(root):
        t = read(root, rel)
        assert old in t, (rel, old)
        write(root, rel, t.replace(old, new, count))
    return f


def append_text(rel, text):
    def f(root):
        t = read(root, rel)
        write(root, rel, t + chr(10) + text + chr(10))
    return f


def has(errors, prefix, needle=''):
    return any(e.startswith(prefix) and needle in e for e in errors)


PAY = 'verqia/payments/application/specs.py'
ALLOC = "name='AllocatePayment'"
ORG = 'verqia/organizations/application/specs.py'
AUTO = 'verqia/automation/application/specs.py'
EVT = 'verqia/events/application/specs.py'
COL = 'verqia/collection/application/specs.py'
INV = 'verqia/invoices/application/specs.py'


def block(text, name):
    """Bornes du `UseCaseSpec(` d'un cas d'usage."""
    i = text.index("name='%s'," % name)
    i = text.rindex('    UseCaseSpec(', 0, i)
    j = text.index('\n    ),', i)
    return i, j


def in_block(rel, name, old, new, count=1):
    def f(root):
        t = read(root, rel)
        i, j = block(t, name)
        b = t[i:j]
        assert old in b, (name, old)
        write(root, rel, t[:i] + b.replace(old, new, count) + t[j:])
    return f


class patched:
    """Altère un registre en mémoire, le temps d'une vérification."""
    def __init__(self, fn):
        self.fn = fn

    def __enter__(self):
        import commands as K
        import modules as M
        self.k, self.m = list(K.COMMANDS), {k: dict(v, deps=list(v['deps'])) for k, v in M.MODULES.items()}
        self.fn(K, M)

    def __exit__(self, *a):
        import commands as K
        import modules as M
        K.COMMANDS[:] = self.k
        M.MODULES.clear()
        M.MODULES.update(self.m)


class TestBaseline(unittest.TestCase):
    def test_application_contracts_are_faithful(self):
        errors, stats = V.verify(REAL)
        self.assertEqual(errors, [])
        self.assertEqual(stats['specs'], 122)
        self.assertEqual(stats['locked'], 103)
        self.assertEqual(stats['phased'], 12)
        self.assertEqual(stats['entries'], {'PUBLIC': 51, 'REACTION': 28, 'BACKGROUND': 23, 'INTERNAL': 17, 'PROVISIONING_STEP': 3})

    def test_every_error_code_named_by_a_use_case_is_in_annex_a(self):
        import gen_application as GA
        from verqia.kernel import errors as KE
        V.verify(REAL)
        for name, codes in GA.ERRORS.items():
            for c in codes:
                self.assertIn(c, KE.ERROR_CATALOGUE, '%s cite %s' % (name, c))

    def test_document_is_in_sync_with_the_generator(self):
        import gen_application_doc as D
        with io.open(D.DOC, encoding='utf-8', newline='') as f:
            self.assertEqual(f.read(), D.render())

    def test_generation_is_deterministic(self):
        a, _ = G.generate()
        b, _ = G.generate()
        self.assertEqual(a, b)


class TestReview(unittest.TestCase):
    """Corrections de revue RV1 à RV8 : chacune a son test d'injection."""

    def test_rv1_create_organization_is_not_an_ordinary_tenant_case(self):
        e = errors_after(in_block(ORG, 'CreateOrganization', 'tenant=TenantMode.NEW', 'tenant=TenantMode.REQUIRED'))
        self.assertTrue(has(e, 'A4', 'CreateOrganization'))

    def test_rv1_new_tenant_is_nominative(self):
        e = errors_after(in_block(ORG, 'CompleteProvisioning', 'tenant=TenantMode.REQUIRED', 'tenant=TenantMode.NEW'))
        self.assertTrue(has(e, 'A4', 'CompleteProvisioning'))

    def test_rv2_public_command_needs_audit_and_non_public_needs_a_name(self):
        e = errors_after(in_block(ORG, 'CreateOrganization', 'audit=AuditMode.REQUIRED', 'audit=AuditMode.NONE'))
        self.assertTrue(has(e, 'A6', 'CreateOrganization'))
        e = errors_after(in_block(ORG, 'CompleteProvisioning', 'audit=AuditMode.NONE', 'audit=AuditMode.REQUIRED'))
        self.assertTrue(has(e, 'A6', 'CompleteProvisioning'))

    def test_rv3_provisioning_step_is_not_an_ordinary_command(self):
        e = errors_after(in_block('verqia/identity/application/specs.py', 'ProvisionOwnerMembership', 'entry=Entry.PROVISIONING_STEP', 'entry=Entry.INTERNAL'))
        self.assertTrue(has(e, 'A10', 'ProvisionOwnerMembership'))
        e = errors_after(in_block('verqia/billing/application/specs.py', 'ProvisionTrialSubscription', 'audit=AuditMode.NONE', 'audit=AuditMode.REQUIRED'))
        self.assertTrue(has(e, 'A10') or has(e, 'A6'))

    def test_rv4_the_relay_claims_then_runs_handlers_then_marks_published(self):
        e = errors_after(in_block(EVT, 'OutboxPublisher', 'role=PhaseRole.CLAIM', 'role=PhaseRole.WRITE'))
        self.assertTrue(has(e, 'A11', 'OutboxPublisher'))
        e = errors_after(in_block(EVT, 'OutboxPublisher', "effects=('events.receipts',)", "effects=('events.receipts', 'audit')", 1))
        self.assertTrue(has(e, 'A11', 'OutboxPublisher'))

    def test_rv4_registry_amendment_a4_is_in_the_registry(self):
        import commands as K
        c = [x for x in K.COMMANDS if x.name == 'OutboxPublisher'][0]
        self.assertTrue(c.txn.startswith('trois'))

    def test_rv5_collection_composition_is_not_a_single_transaction(self):
        e = errors_after(in_block(COL, 'CreateCollectionAction', "calls=('collection.AdvanceProposedAction',)", 'calls=()'))
        self.assertTrue(has(e, 'A11', 'CreateCollectionAction'))

    def test_rv5_approvals_own_transaction_is_declared(self):
        e = errors_after(in_block(COL, 'AdvanceProposedAction', "modules=('approvals',)", "modules=('collection',)"))
        self.assertTrue(has(e, 'A11', 'AdvanceProposedAction'))

    def test_rv6_no_effect_before_a_valid_claim(self):
        # l'effet passe en première phase : plus de réclamation en tête
        def swap(root):
            t = read(root, AUTO)
            i, j = block(t, 'RunExecutionStep')
            b = t[i:j].replace('role=PhaseRole.CLAIM', 'role=PhaseRole.TMP').replace('role=PhaseRole.EFFECT', 'role=PhaseRole.CLAIM').replace('role=PhaseRole.TMP', 'role=PhaseRole.EFFECT')
            write(root, AUTO, t[:i] + b + t[j:])
        self.assertTrue(has(errors_after(swap), 'A11', 'AP-10'))

    def test_rv6_finalize_must_belong_to_the_claim_module(self):
        def m(root):
            t = read(root, AUTO)
            i, j = block(t, 'RunExecutionStep')
            b = t[i:j]
            k = b.rindex("modules=('automation',)")
            write(root, AUTO, t[:i] + b[:k] + "modules=('collection',)" + b[k + len("modules=('automation',)"):] + t[j:])
        self.assertTrue(has(errors_after(m), 'A11', 'même module'))

    def test_rv6_a_worker_without_claim_is_refused(self):
        def m(root):
            t = read(root, AUTO)
            i, j = block(t, 'RunExecutionStep')
            b = t[i:j].replace('role=PhaseRole.CLAIM', 'role=PhaseRole.WRITE')
            write(root, AUTO, t[:i] + b + t[j:])
        self.assertTrue(has(errors_after(m), 'A11', 'CLAIM obligatoire'))

    def test_rv6_an_external_effect_never_sits_in_a_transaction(self):
        e = errors_after(in_block(COL, 'ExecuteDueAction', "role=PhaseRole.EXTERNAL, modules=('notifications',), calls=(), effects=()",
                                  "role=PhaseRole.EXTERNAL, modules=('notifications',), calls=(), effects=('collection.attempts',)"))
        self.assertTrue(has(e, 'A11', 'EXTERNAL'))

    def test_rv6_phases_are_required_for_composed_use_cases(self):
        def m(root):
            t = read(root, AUTO)
            i, j = block(t, 'RunExecutionStep')
            k = t.index('phases=(', i)
            write(root, AUTO, t[:k] + 'phases=(),' + t[j:])
        self.assertTrue(has(errors_after(m), 'A11', 'RunExecutionStep'))

    def test_rv7_replay_is_not_universal(self):
        e = errors_after(in_block(COL, 'ResumeProposedActions', "outcomes=('OK', 'SKIPPED')", "outcomes=('OK', 'SKIPPED', 'REPLAY')"))
        self.assertTrue(has(e, 'A9', 'REPLAY'))
        e = errors_after(in_block('verqia/risk/application/specs.py', 'RecomputeRisk', "outcomes=('PROCESSED', 'SKIPPED', 'RETRYING', 'DEAD')",
                                  "outcomes=('PROCESSED', 'SKIPPED', 'RETRYING', 'DEAD', 'REPLAY')"))
        self.assertTrue(has(e, 'A9'))
        e = errors_after(in_block('verqia/payments/application/specs.py', 'CreatePayment', "outcomes=('OK', 'REPLAY')", "outcomes=('OK',)"))
        self.assertTrue(has(e, 'A9', 'manquantes'))

    def test_rv7_a_service_has_no_outcome_of_its_own(self):
        e = errors_after(in_block(INV, 'ApplySettlement', 'outcomes=()', "outcomes=('OK',)"))
        self.assertTrue(has(e, 'A9', 'ApplySettlement'))

    def test_rv8_settlement_direction_payments_to_invoices_never_back(self):
        e = errors_after(in_block(INV, 'ApplySettlement', 'cross_module=()', "cross_module=('payments.CreatePayment',)"))
        self.assertTrue(has(e, 'A8', 'payments.CreatePayment'))
        self.assertTrue(any('sens contraire' in x for x in e))

    def test_rv8_own_target_must_own_the_state_it_writes(self):
        def alter(K, M):
            K.COMMANDS[:] = [c._replace(writes=('payments.record',)) if c.name == 'AdvanceProposedAction' else c for c in K.COMMANDS]
        with patched(alter):
            errors, _ = V.verify(REAL)
        self.assertTrue(any(x.startswith('A8') and 'ne possède pas cet état' in x for x in errors))

    def test_rv8_own_target_must_write_something(self):
        def alter(K, M):
            K.COMMANDS[:] = [c._replace(writes=()) if c.name == 'RequestApproval' else c for c in K.COMMANDS]
        with patched(alter):
            errors, _ = V.verify(REAL)
        self.assertTrue(any(x.startswith('A8') and "n'écrit aucun état" in x for x in errors))

    def test_rv8_the_four_amended_edges_must_be_in_the_module_registry(self):
        def alter(K, M):
            M.MODULES['imports']['deps'].remove('risk')
        with patched(alter):
            errors, _ = V.verify(REAL)
        self.assertTrue(any(x.startswith('A8') and 'imports → risk' in x for x in errors))

    def test_registry_and_application_agree_on_undeclared_own_calls(self):
        def alter(K, M):
            K.COMMANDS[:] = [c._replace(calls=c.calls + ('own:approvals.RequestApproval',)) if c.name == 'ScanReconciliationReviews' else c for c in K.COMMANDS]
        with patched(alter):
            errors, _ = V.verify(REAL)
        self.assertTrue(any(x.startswith('A11') and 'ScanReconciliationReviews' in x for x in errors))


class TestIdempotencyScope(unittest.TestCase):
    """AP-14 : la portée d'idempotence de CreateOrganization est une exception nommée, testée."""

    def test_create_organization_is_actor_scoped_everything_else_is_organization_scoped(self):
        import gen_application as GA
        import commands as K
        import build_registry as B
        B.run()
        got = {(c.module, c.name): GA.scope_for(c) for c in K.COMMANDS}
        self.assertEqual(got[('organizations', 'CreateOrganization')], 'ACTOR')
        self.assertEqual([k for k, v in got.items() if v == 'ACTOR'], [('organizations', 'CreateOrganization')])
        self.assertGreaterEqual(sum(1 for v in got.values() if v == 'ORGANIZATION'), 5)

    def test_actor_scope_and_new_tenant_go_together(self):
        e = errors_after(in_block(ORG, 'CreateOrganization', 'idempotency_scope=IdempotencyScope.ACTOR', 'idempotency_scope=IdempotencyScope.ORGANIZATION'))
        self.assertTrue(has(e, 'A12', 'CreateOrganization'))

    def test_actor_scope_is_not_available_to_other_commands(self):
        e = errors_after(in_block('verqia/payments/application/specs.py', 'CreatePayment', 'idempotency_scope=IdempotencyScope.ORGANIZATION',
                                  'idempotency_scope=IdempotencyScope.ACTOR'))
        self.assertTrue(has(e, 'A12', 'CreatePayment'))

    def test_a_command_with_a_key_cannot_drop_its_scope(self):
        e = errors_after(in_block('verqia/payments/application/specs.py', 'CreatePayment', 'idempotency_scope=IdempotencyScope.ORGANIZATION',
                                  'idempotency_scope=None'))
        self.assertTrue(has(e, 'A12', 'CreatePayment'))

    def test_the_request_key_is_read_from_the_lock_operation_not_from_free_text(self):
        """Défaut corrigé (B1) : 38 commandes prennent `K` ; le texte libre du registre n'en désignait que 11."""
        import build_registry as B
        import commands as K
        import gen_application as GA
        B.run()
        keyed = [c for c in K.COMMANDS if GA.has_request_key(c)]
        self.assertEqual(len(keyed), 38)
        self.assertEqual(len([c for c in keyed if 'idempotence' in (c.idem or '')]), 11)     # le texte libre ne suffisait pas
        self.assertEqual([c.name for c in keyed if GA.scope_for(c) == 'ACTOR'], ['CreateOrganization'])

    def test_a_scope_on_a_command_without_the_key_lock_is_refused(self):
        import build_registry as B
        import commands as K
        import gen_application as GA
        import locks as L
        B.run()
        c = [x for x in K.COMMANDS if x.kind == 'command' and not GA.has_request_key(x)][0]
        rel = 'verqia/%s/application/specs.py' % c.module
        e = errors_after(in_block(rel, c.name, 'idempotency_scope=None', 'idempotency_scope=IdempotencyScope.ORGANIZATION'))
        self.assertTrue(has(e, 'A12', c.name))

    def test_a_keyed_command_without_the_key_effect_breaks_atomicity(self):
        e = errors_after(in_block('verqia/customers/application/specs.py', 'CreateCustomer', '"clé d\'idempotence"', "'autre effet'"))
        self.assertTrue(has(e, 'A7', 'CreateCustomer'))

    def test_a_composed_keyed_command_puts_the_key_in_its_first_phase(self):
        e = errors_after(in_block(COL, 'CreateCollectionAction', "'audit', \"clé d'idempotence\"), what=", "'audit'), what="))
        self.assertTrue(has(e, 'A11', 'première phase') or has(e, 'A11', 'CreateCollectionAction'))


class TestTransactionScope(unittest.TestCase):
    """AP-15 (K1) : la portée de transaction se déduit du régime d'organisation."""

    def test_a_required_command_cannot_be_system(self):
        e = errors_after(in_block(PAY, 'CreatePayment', 'transaction_scope=TransactionScope.TENANT', 'transaction_scope=TransactionScope.SYSTEM'))
        self.assertTrue(has(e, 'A13', 'CreatePayment'))

    def test_the_relay_cannot_be_tenant(self):
        e = errors_after(in_block(EVT, 'OutboxPublisher', 'transaction_scope=TransactionScope.SYSTEM', 'transaction_scope=TransactionScope.TENANT'))
        self.assertTrue(has(e, 'A13', 'OutboxPublisher'))

    def test_the_generated_scope_table_cannot_be_bent(self):
        def m(root):
            t = read(root, 'verqia/kernel/application.py')
            assert 'TenantMode.REQUIRED: TransactionScope.TENANT' in t
            write(root, 'verqia/kernel/application.py', t.replace('TenantMode.REQUIRED: TransactionScope.TENANT', 'TenantMode.REQUIRED: TransactionScope.SYSTEM'))
        e = errors_after(m)
        self.assertTrue(has(e, 'A13', 'SCOPE_OF_TENANT'))
        self.assertTrue(has(e, 'dérive'))

    def test_create_organization_is_new_and_only_it(self):
        e = errors_after(in_block(ORG, 'CreateOrganization', 'transaction_scope=TransactionScope.NEW', 'transaction_scope=TransactionScope.TENANT'))
        self.assertTrue(has(e, 'A13', 'CreateOrganization'))
        e = errors_after(in_block(PAY, 'CreatePayment', 'transaction_scope=TransactionScope.TENANT', 'transaction_scope=TransactionScope.NEW'))
        self.assertTrue(has(e, 'A13', 'CreatePayment'))

    def test_the_new_regime_cannot_be_folded_into_tenant_in_the_generated_table(self):
        def m(root):
            t = read(root, 'verqia/kernel/application.py')
            assert 'TenantMode.NEW: TransactionScope.NEW' in t
            write(root, 'verqia/kernel/application.py', t.replace('TenantMode.NEW: TransactionScope.NEW', 'TenantMode.NEW: TransactionScope.TENANT'))
        e = errors_after(m)
        self.assertTrue(has(e, 'A13', 'SCOPE_OF_TENANT'))

    def test_exactly_two_use_cases_are_system(self):
        errors, stats = V.verify(REAL)
        import verify_application
        specs = verify_application.load_specs(REAL)
        system = sorted(k for k, v in specs.items() if v[0].transaction_scope.value == 'SYSTEM')
        self.assertEqual(system, [('events', 'OutboxPublisher'), ('platform', 'PartitionManager')])


class TestKernelAmendments(unittest.TestCase):
    def test_the_application_journal_records_b1_to_b9(self):
        import application_freeze as FZ
        self.assertEqual([a[0] for a in FZ.AMENDMENTS], ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9'])
        self.assertEqual(FZ.read_freeze()['amendments'], 9)

    def test_the_kernel_journal_records_k1_and_k2(self):
        import gen_contracts_doc as CD
        self.assertEqual([a[0] for a in CD.KERNEL_AMENDMENTS], ['K1', 'K2', 'K3'])
        with io.open(os.path.join(os.path.dirname(V.HERE), 'MODULE_CONTRACTS_V1.md'), encoding='utf-8', newline='') as f:
            doc = f.read()
        self.assertIn('| K1 |', doc)
        self.assertIn('| K2 |', doc)
        self.assertIn('| K3 |', doc)

    def test_the_kernel_carries_the_typed_scopes_and_the_system_context(self):
        import verify_contracts
        verify_contracts.purge()
        sys.path.insert(0, REAL)
        from verqia.kernel import context, types
        self.assertEqual({m.value for m in types.TransactionScope}, {'TENANT', 'SYSTEM', 'NEW'})
        self.assertEqual({m.value for m in types.IdempotencyScope}, {'ORGANIZATION', 'ACTOR'})
        self.assertTrue(hasattr(context, 'SystemContext'))
        self.assertFalse(hasattr(context.SystemContext, 'organization_id'))
        self.assertFalse(hasattr(context.CreationContext, 'organization_id'))
        self.assertIn('organization_id', context.CallContext.__dataclass_fields__)


class TestFreeze(unittest.TestCase):
    """Le gel est mécanique : toute dérive des données Application casse l'empreinte."""

    def setUp(self):
        import application_freeze as FZ
        self.FZ = FZ
        self.real = FZ.FREEZE_FILE
        self.tmp = tempfile.mkdtemp(prefix='verqia_freeze_')
        FZ.FREEZE_FILE = os.path.join(self.tmp, 'freeze.json')

    def tearDown(self):
        self.FZ.FREEZE_FILE = self.real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repository_is_frozen(self):
        self.FZ.FREEZE_FILE = self.real
        self.assertEqual(self.FZ.check_freeze(), [])

    def test_missing_freeze_file_is_reported(self):
        self.assertTrue(any('absent' in e for e in self.FZ.check_freeze()))

    def test_fingerprint_is_stable_and_detects_a_data_change(self):
        import gen_application as GA
        self.FZ.write_freeze('2026-01-01')
        self.assertEqual(self.FZ.check_freeze(), [])
        old = dict(GA.PHASES)
        try:
            GA.PHASES[('collection', 'ResumeProposedActions')] = (
                ('EFFECT', ('collection',), ('collection.AdvanceProposedAction',), (), 'autre contenu'),)
            self.assertTrue(any('amendement non journalisé' in e for e in self.FZ.check_freeze()))
        finally:
            GA.PHASES.clear()
            GA.PHASES.update(old)
        self.assertEqual(self.FZ.check_freeze(), [])

    def test_an_amendment_must_be_journalled(self):
        self.FZ.write_freeze('2026-01-01')
        self.FZ.AMENDMENTS.append(('B1', '2026-01-02', 'x', 'y', 'z'))
        try:
            self.assertTrue(any('journal' in e for e in self.FZ.check_freeze()))
        finally:
            self.FZ.AMENDMENTS.pop()


class TestInjection(unittest.TestCase):
    def test_a1_missing_spec(self):
        def m(root):
            t = read(root, PAY)
            i = t.index('    UseCaseSpec(', t.index("name='CreatePayment'") - 60)
            j = t.index('    UseCaseSpec(', i + 10)
            write(root, PAY, t[:i] + t[j:])
        self.assertTrue(has(errors_after(m), 'A1', 'CreatePayment'))

    def test_a1_extra_spec(self):
        def m(root):
            t = read(root, PAY)
            i = t.index('    UseCaseSpec(')
            j = t.index('    UseCaseSpec(', i + 10)
            write(root, PAY, t[:j] + t[i:j] + t[j:])
        self.assertTrue(has(errors_after(m), 'A1', '2 spécifications'))

    def test_a2_transaction_drift(self):
        self.assertTrue(has(errors_after(sub(PAY, "transaction='une'", "transaction='deux'")), 'A2', 'transaction'))

    def test_a2_events_drift(self):
        self.assertTrue(has(errors_after(sub(PAY, "emits=('PAYMENT_CREATED',)", "emits=()")), 'A2', 'événements'))

    def test_a2_domain_write_drift(self):
        self.assertTrue(has(errors_after(sub(PAY, "domain=('payments.record',)", "domain=('payments.record', 'invoices.body')")), 'A2', 'Domain'))

    def test_a3_lock_sequence_unsorted(self):
        e = errors_after(sub(PAY, "lock_sequence=(('idempotency_keys', 'K'), ('payments', 'U'), ('invoices', 'U'))",
                             "lock_sequence=(('idempotency_keys', 'K'), ('invoices', 'U'), ('payments', 'U'))"))
        self.assertTrue(has(e, 'A3', 'AllocatePayment'))
        self.assertTrue(any('rang strictement croissant' in x for x in e))

    def test_a3_unknown_resource(self):
        e = errors_after(sub(PAY, "('customers', 'S')", "('customerz', 'S')"))
        self.assertTrue(has(e, 'A3', 'absente de l\'échelle'))

    def test_a3_generated_ladder_tampered(self):
        def m(root):
            t = read(root, 'verqia/kernel/lock_registry.py')
            write(root, 'verqia/kernel/lock_registry.py', t.replace("'customers': 70", "'customers': 95"))
        self.assertTrue(has(errors_after(m), 'dérive'))

    def test_a3_lock_operation_removed(self):
        e = errors_after(sub(PAY, "lock_operation='CreatePayment'", "lock_operation=None"))
        self.assertTrue(has(e, 'A3'))

    def test_a4_tenant_regime(self):
        e = errors_after(sub(PAY, 'tenant=TenantMode.REQUIRED', 'tenant=TenantMode.NONE'))
        self.assertTrue(has(e, 'A4', 'régime d\'organisation'))

    def test_a4_relay_exception_is_nominative(self):
        def m(root):
            p = 'verqia/notifications/application/specs.py'
            t = read(root, p)
            write(root, p, t.replace('tenant=TenantMode.REQUIRED', 'tenant=TenantMode.RELAY', 1))
        self.assertTrue(has(errors_after(m), 'A4'))

    def test_a5_invented_error_code(self):
        e = errors_after(sub(PAY, "'ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE'", "'ALLOCATION_TOO_BIG'"))
        self.assertTrue(has(e, 'A5', 'ALLOCATION_TOO_BIG'))

    def test_a5_unknown_error_class(self):
        e = errors_after(sub(PAY, "error_classes=('VALIDATION',", "error_classes=('WHATEVER', 'VALIDATION',"))
        self.assertTrue(has(e, 'A5', 'WHATEVER'))

    def test_a6_command_without_audit(self):
        e = errors_after(sub(PAY, 'audit=AuditMode.REQUIRED', 'audit=AuditMode.NONE'))
        self.assertTrue(has(e, 'A6', 'CreatePayment'))

    def test_a6_handler_with_audit(self):
        def m(root):
            p = 'verqia/risk/application/specs.py'
            t = read(root, p)
            i = t.index("kind='handler'")
            j = t.index('audit=AuditMode.NONE', i)
            write(root, p, t[:j] + 'audit=AuditMode.REQUIRED' + t[j + len('audit=AuditMode.NONE'):])
        self.assertTrue(has(errors_after(m), 'A6', 'REACTION'))

    def test_a7_effect_outside_the_atomic_unit(self):
        e = errors_after(sub(PAY, "atomic_effects=('payments.record', 'événements', 'audit', \"clé d'idempotence\")",
                             "atomic_effects=('payments.record', 'audit', \"clé d'idempotence\")"))
        self.assertTrue(has(e, 'A7', 'événements'))

    def test_a7_external_effect_inside_the_atomic_unit(self):
        e = errors_after(sub(PAY, "atomic_effects=('payments.record', 'événements'", "atomic_effects=('payments.record', 'envoi de courriel', 'événements'"))
        self.assertTrue(has(e, 'A7', 'inattendu'))

    def test_a8_unknown_cross_module_target(self):
        e = errors_after(sub(PAY, "cross_module=('invoices.ApplySettlement',)", "cross_module=('invoices.ApplyEverything',)"))
        self.assertTrue(has(e, 'A8', 'ApplyEverything'))

    def test_a8_undeclared_dependency(self):
        e = errors_after(sub(PAY, "cross_module=('invoices.ApplySettlement',)", "cross_module=('invoices.ApplySettlement', 'billing.Subscribe')"))
        self.assertTrue(has(e, 'A8'))

    def test_h_control_flow_forbidden(self):
        e = errors_after(sub(PAY, 'USE_CASES: tuple[UseCaseSpec, ...] = (', 'if True:\n    pass\nUSE_CASES: tuple[UseCaseSpec, ...] = ('))
        self.assertTrue(any('comportement interdit' in x for x in e))

    def test_h_framework_import_forbidden(self):
        e = errors_after(sub(PAY, 'from __future__ import annotations', 'from __future__ import annotations\nimport django'))
        self.assertTrue(any('django' in x for x in e))

    def test_h_other_module_only_through_contracts(self):
        e = errors_after(sub(PAY, 'from __future__ import annotations', 'from __future__ import annotations\nfrom verqia.invoices.domain import x'))
        self.assertTrue(any('contracts' in x for x in e))

    def test_a1_module_deleted(self):
        def m(root):
            shutil.rmtree(os.path.join(root, 'verqia', 'risk', 'application'))
        e = errors_after(m)
        self.assertTrue(has(e, 'A1') or has(e, 'fichier attendu absent'))


if __name__ == '__main__':
    unittest.main()
