"""Tests d'injection de violation (TA-34) : chaque règle des registres doit faire ÉCHOUER la porte quand on la viole.

Une règle qui n'a jamais été vue échouer n'est pas prouvée. Lancement : python -m unittest architecture_registry.test_registry
(depuis la racine de verqia-docs) ou `python -m unittest` dans ce dossier.
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_registry as B  # noqa: E402
import commands as K  # noqa: E402
import events as EV  # noqa: E402
import locks as L  # noqa: E402
import modules as M  # noqa: E402


def errors_after(mutate):
    """Applique `mutate` aux registres, exécute les vérifications, puis restaure. Renvoie la liste des erreurs."""
    saved = (list(K.COMMANDS), copy.deepcopy(M.MODULES), dict(L.OPERATIONS), copy.deepcopy(K.STATES), dict(EV.NO_SUBSCRIBER), dict(EV.PENDING_CATALOGUE_ADDITIONS), copy.deepcopy(M.SCHEMA_DEPS))
    try:
        mutate()
        B.run()
        return list(B.errors)
    finally:
        K.COMMANDS[:] = saved[0]
        M.MODULES.clear()
        M.MODULES.update(saved[1])
        L.OPERATIONS.clear()
        L.OPERATIONS.update(saved[2])
        K.STATES.clear()
        K.STATES.update(saved[3])
        EV.NO_SUBSCRIBER.clear()
        EV.NO_SUBSCRIBER.update(saved[4])
        EV.PENDING_CATALOGUE_ADDITIONS.clear()
        EV.PENDING_CATALOGUE_ADDITIONS.update(saved[5])
        M.SCHEMA_DEPS.clear()
        M.SCHEMA_DEPS.update(saved[6])
        B.run()


def cmd(name, module=None):
    return next(c for c in K.COMMANDS if c.name == name and (module is None or c.module == module))


def replace(c, **kw):
    i = K.COMMANDS.index(c)
    K.COMMANDS[i] = c._replace(**kw)


class TestBaseline(unittest.TestCase):
    def test_registries_are_consistent(self):
        B.run()
        self.assertEqual(B.errors, [])

    def test_frozen_ec5_chain_is_compatible_and_first_draft_is_not(self):
        self.assertTrue(L.consistent(L.FROZEN_EC5)[0])
        self.assertFalse(L.consistent(L.FIRST_DRAFT_TD27)[0])

    def test_ladder_respects_every_registered_operation(self):
        order, cycle = L.canonical()
        self.assertIsNone(cycle)
        rank = {r: i for i, r in enumerate(order)}
        for name in L.OPERATIONS:
            seq = [r for r, _ in L.op_sequence(name)]
            self.assertEqual(seq, sorted(seq, key=lambda r: rank[r]), name)

    def test_advisory_lock_is_always_first_and_receipt_always_last(self):
        for name in L.OPERATIONS:
            seq = [r for r, _ in L.op_sequence(name)]
            if 'advisory' in seq:
                self.assertEqual(seq[0], 'advisory', name)
            if 'event_receipts' in seq:
                self.assertEqual(seq[-1], 'event_receipts', name)


class TestInjectedViolations(unittest.TestCase):
    def test_lock_order_cycle_is_detected(self):
        def m():
            L.OPERATIONS['Bad'] = ('automation', [('automation_executions', 'U'), ('payments', 'U')], set(), 'test')
        self.assertTrue(any('cycle de verrous' in e or 'incompatible' in e or 'impossible' in e for e in errors_after(m)))

    def test_execution_then_action_in_one_transaction_contradicts_ec5(self):
        def m():
            L.OPERATIONS['Bad'] = ('automation', [('automation_executions', 'U'), ('collection_actions', 'I')], set(), 'test')
        self.assertTrue(any('EC5' in e for e in errors_after(m)))

    def test_write_outside_owner_without_c12_is_detected(self):
        def m():
            c = cmd('RunExecutionStep')
            replace(c, writes=c.writes + ('collection.action_status',))
        self.assertTrue(any('écriture hors propriétaire' in e for e in errors_after(m)))

    def test_state_without_writer_is_detected(self):
        def m():
            K.STATES['orphan.state'] = ('invoices', 'état', 'test')
        self.assertTrue(any('sans écrivain' in e for e in errors_after(m)))

    def test_event_without_producer_is_detected(self):
        def m():
            c = cmd('VoidInvoice')
            replace(c, emits=())
        self.assertTrue(any('sans producteur' in e for e in errors_after(m)))

    def test_event_produced_by_wrong_module_is_detected(self):
        def m():
            c = cmd('CreatePayment')
            replace(c, emits=c.emits + ('INVOICE_PAID',))
        self.assertTrue(any('produit par' in e for e in errors_after(m)))

    def test_request_event_with_two_recipients_is_detected(self):
        def m():
            c = cmd('RecomputePriority')
            replace(c, subscribes=c.subscribes + ('RISK_RECALCULATION_REQUESTED',))
        self.assertTrue(any('REQUEST' in e for e in errors_after(m)))

    def test_undeclared_dependency_is_detected(self):
        def m():
            c = cmd('PromiseBreachScan')
            replace(c, calls=c.calls + ('collection.CreateCollectionAction',))
        self.assertTrue(any('dépendance requise non déclarée : promises → collection' in e for e in errors_after(m)))

    def test_dependency_cycle_is_detected(self):
        def m():
            M.MODULES['invoices']['deps'].append('payments')
            c = cmd('IssueInvoice')
            replace(c, calls=c.calls + ('payments.PaymentFacts',))
        self.assertTrue(any('cycle' in e for e in errors_after(m)))

    def test_cross_module_transaction_outside_c12_is_detected(self):
        def m():
            c = cmd('CreateInvoice')
            replace(c, calls=c.calls + ('payments.CreatePayment',))
            M.MODULES['invoices']['deps'].append('payments')
        self.assertTrue(any('même transaction sans exception' in e for e in errors_after(m)))

    def test_unowned_table_is_detected(self):
        def m():
            M.MODULES['customers']['owns'].remove('customer_contacts')
        self.assertTrue(any('propriétaire(s)' in e for e in errors_after(m)))

    def test_unknown_event_subscription_is_detected(self):
        def m():
            c = cmd('SuppressOnInvoicePaid')
            replace(c, subscribes=('INVOICE_PAYD',))
        self.assertTrue(any('événement inconnu' in e for e in errors_after(m)))

    def test_refresh_list_drift_is_detected(self):
        def m():
            K.RISK_REFRESH.append('INVOICE_DUE')
            c = cmd('RequestRiskRecalc')
            replace(c, subscribes=tuple(K.RISK_REFRESH))
        saved = list(K.RISK_REFRESH)
        try:
            self.assertTrue(any('RISK_REFRESH' in e for e in errors_after(m)))
        finally:
            K.RISK_REFRESH[:] = saved


class TestRoundThreeRules(unittest.TestCase):
    """Règles ajoutées par la revue G à M."""

    def test_cross_module_call_in_the_same_transaction_is_detected(self):
        def m():
            c = cmd('CreateCollectionAction')
            replace(c, calls=c.calls + ('approvals.RequestApproval',))
        self.assertTrue(any('même transaction sans exception C12 nominative' in e for e in errors_after(m)))

    def test_own_transaction_prefix_makes_the_same_call_legitimate(self):
        def m():
            c = cmd('CreateCollectionAction')
            replace(c, calls=c.calls + ('own:approvals.RequestApproval',))
        self.assertFalse(any('même transaction' in e for e in errors_after(m)))

    def test_c12_list_is_closed_and_nominative(self):
        def m():
            c = cmd('CreateOrganization')
            replace(c, c12=True)
        self.assertTrue(any('drapeau C12 hors des exceptions nommées' in e for e in errors_after(m)))

    def test_composition_job_must_call_use_cases_in_their_own_transaction(self):
        def m():
            c = cmd('ImportReleaser', 'jobs')
            replace(c, calls=('automation.ReleaseImportTranche',))
        self.assertTrue(any('un travail de composition' in e for e in errors_after(m)))

    def test_event_without_subscriber_must_be_classified(self):
        def m():
            del EV.NO_SUBSCRIBER['INVOICE_CREATED']
        self.assertTrue(any('sans abonné et sans classement' in e for e in errors_after(m)))

    def test_forgotten_event_class_c_fails_the_gate(self):
        def m():
            EV.NO_SUBSCRIBER['INVOICE_CREATED'] = ('C', 'oublié')
        self.assertTrue(any('classé C' in e for e in errors_after(m)))

    def test_classified_event_that_has_a_subscriber_is_inconsistent(self):
        def m():
            EV.NO_SUBSCRIBER['INVOICE_PAID'] = ('A', 'test')
        self.assertTrue(any('classé « sans abonné » mais abonné' in e for e in errors_after(m)))

    def test_contractual_event_absent_from_catalogue_and_unclassified_is_detected(self):
        def m():
            c = cmd('CreateCustomer')
            replace(c, emits=c.emits + ('FAKE_CONTRACT_EVENT',))
        self.assertTrue(any('événement émis inconnu du catalogue' in e for e in errors_after(m)))

    def test_pending_catalogue_entry_already_catalogued_is_detected(self):
        def m():
            EV.PENDING_CATALOGUE_ADDITIONS['USER_CREATED'] = 'test'
        self.assertTrue(any('est déjà au catalogue' in e for e in errors_after(m)))

    def test_call_graph_cycle_is_detected(self):
        def m():
            c = cmd('RecomputeRisk')
            replace(c, calls=c.calls + ('priority.PriorityLevel',))
            M.MODULES['risk']['deps'].append('priority')
        self.assertTrue(any('cycle sur le graphe des APPELS' in e for e in errors_after(m)))

    def test_schema_cycle_is_detected(self):
        def m():
            M.SCHEMA_DEPS['organizations'] = ['invoices']
        self.assertTrue(any('cycle sur les dépendances de SCHÉMA' in e for e in errors_after(m)))

    def test_provisioning_steps_are_implemented_by_their_owners_not_called_by_organizations(self):
        B.run()
        org_calls = {t for c in K.COMMANDS if c.module == 'organizations' for t in c.calls}
        self.assertTrue(all(not t.startswith(('own:identity', 'own:billing', 'own:automation', 'identity.', 'billing.', 'automation.')) for t in org_calls))
        self.assertIn('organizations', M.MODULES['identity']['deps'])
        self.assertNotIn('automation', M.MODULES['organizations']['deps'])

    def test_no_command_name_is_provisional_at_freeze(self):
        self.assertFalse(any(c.src.startswith('PROPOSED') for c in K.COMMANDS))

    def test_freeze_is_impossible_while_a_command_name_is_provisional(self):
        c = cmd('CreatePayment')
        replace(c, src='PROPOSED')
        try:
            self.assertTrue(any(x.src.startswith('PROPOSED') for x in K.COMMANDS))
        finally:
            K.COMMANDS[K.COMMANDS.index(next(x for x in K.COMMANDS if x.name == 'CreatePayment'))] = c

    def test_request_emitter_must_declare_the_dependency_on_the_engine(self):
        def m():
            M.MODULES['imports']['deps'].remove('cashflow')
        self.assertTrue(any('dépendance requise non déclarée : imports → cashflow' in e for e in errors_after(m)))

    def test_provision_prefix_is_reserved_to_provisioning_steps(self):
        def m():
            c = cmd('ProvisionDefaultAutomations')
            replace(c, name='InstallDefaultAutomations', implements=c.implements)
            d = cmd('ProvisionTrialSubscription')
            replace(d, implements=())
        errs = errors_after(m)
        self.assertTrue(any('`Provision` est réservé' in e for e in errs))

    def test_complete_prefix_designates_a_process_completion(self):
        def m():
            c = cmd('CompleteProvisioning')
            replace(c, kind='command')
        self.assertTrue(any('`Complete*`' in e for e in errors_after(m)))

    def test_read_prefix_requires_a_reader_port(self):
        def m():
            c = cmd('ReadApprovalTarget', 'collection')
            replace(c, implements=())
        self.assertTrue(any('`Read*`' in e for e in errors_after(m)))

    def test_command_verb_must_align_with_the_emitted_event(self):
        def m():
            c = cmd('CreateCustomer')
            replace(c, emits=('CUSTOMER_UPDATED',))
        self.assertTrue(any('doit s\'aligner' in e for e in errors_after(m)))

    def test_cashflow_org_settings_subscription_is_registered_with_a_filter(self):
        c = cmd('RequestCashflowRecalc')
        self.assertIn('ORG_SETTINGS_CHANGED', c.subscribes)
        self.assertEqual(len(K.CASHFLOW_REFRESH_EVENTS), 14)
        self.assertEqual(K.CASHFLOW_ORG_SETTINGS_RELEVANT, ())


if __name__ == '__main__':
    unittest.main()
