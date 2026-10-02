"""Preuves complémentaires des invariants AP : ce que la porte de fermeture a montré comme non démontré jusque-là.

Chaque classe répond à un AP ; les tests `test_a_*` / `*_is_refused_*` sont des INJECTIONS : ils corrompent les spécifications GÉNÉRÉES d'une copie et exigent que la vérification échoue.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_registry as B  # noqa: E402
import commands as K  # noqa: E402
import verify_application as V  # noqa: E402
from test_application import (COL, EVT, INV, ORG, PAY, REAL, append_text, errors_after, has, in_block, sub)  # noqa: E402


def real_specs():
    return {k: v[0] for k, v in V.load_specs(REAL).items()}


def spec_path(module):
    return 'verqia/%s/application/specs.py' % module


class TestAP01OneSpecPerEntry(unittest.TestCase):
    def test_every_registry_entry_has_exactly_one_spec_and_no_other_exists(self):
        B.run()
        specs = real_specs()
        self.assertEqual(sorted(specs), sorted((c.module, c.name) for c in K.COMMANDS))
        self.assertEqual(len(specs), 122)

    def test_an_orphan_spec_is_refused(self):
        """Une spécification dont le nom n'est pas au registre : `payments.CreatePayment` n'a plus de spécification ET `payments.CreatePaymentX` n'a pas d'entrée."""
        e = errors_after(sub(PAY, "name='CreatePayment',", "name='CreatePaymentX',"))
        self.assertTrue(has(e, 'A1', 'CreatePayment a 0'))
        self.assertTrue(has(e, 'A1', 'sans entrée de registre'))

    def test_a_duplicated_spec_is_refused(self):
        def m(root):
            from test_application import read, write
            t = read(root, PAY)
            i = t.index('    UseCaseSpec(')
            j = t.index('    UseCaseSpec(', i + 10)
            write(root, PAY, t[:j] + t[i:j] + t[j:])
        self.assertTrue(has(errors_after(m), 'A1', '2 spécifications'))


class TestAP02Fidelity(unittest.TestCase):
    def test_the_real_specs_are_faithful(self):
        errors, stats = V.verify(REAL)
        self.assertEqual(errors, [])

    def test_a_drift_of_the_idempotency_mechanism_is_refused(self):
        e = errors_after(in_block(PAY, 'CreatePayment', 'idempotency="clé d\'idempotence"', "idempotency='autre mécanisme'"))
        self.assertTrue(has(e, 'A2', 'idempotence'))

    def test_a_drift_of_the_subscriptions_is_refused(self):
        handler = next(c for c in K.COMMANDS if c.module == 'risk' and c.kind == 'handler')
        e = errors_after(in_block(spec_path('risk'), handler.name, "input='événements : ", "input='événements : EVENEMENT_INVENTE, "))
        self.assertTrue(has(e, 'A2', 'abonnements'))

    def test_a_drift_of_the_reads_is_refused(self):
        e = errors_after(in_block(INV, 'CreateInvoice', "reads=('customers.CustomerFacts', 'organizations.OrgStatus')", 'reads=()'))
        self.assertTrue(has(e, 'A2', 'lectures'))

    def test_a_drift_of_the_cross_module_calls_is_refused(self):
        e = errors_after(in_block(PAY, 'AllocatePayment', "cross_module=('invoices.ApplySettlement',)", 'cross_module=()'))
        self.assertTrue(has(e, 'A2', 'appels inter-modules'))

    def test_a_drift_of_the_nature_is_refused(self):
        e = errors_after(in_block(PAY, 'CreatePayment', "kind='command'", "kind='service'"))
        self.assertTrue(has(e, 'A2', 'nature'))

    def test_a_drift_of_the_module_or_name_is_refused(self):
        e = errors_after(in_block(PAY, 'CreatePayment', "module='payments'", "module='invoices'"))
        self.assertTrue(has(e, 'A1', 'CreatePayment'))          # l'identité d'une spécification est son couple (module, nom) : une dérive se voit comme A1


class TestAP04Regimes(unittest.TestCase):
    def test_the_real_specs_carry_the_six_regimes(self):
        regimes = {s.tenant.value for s in real_specs().values()}
        self.assertEqual(regimes, {'REQUIRED', 'EVENT', 'ENUMERATOR', 'RELAY', 'NONE', 'NEW'})

    def wrong(self, regime):
        spec = next(s for s in real_specs().values() if s.tenant.value == regime)
        other = 'EVENT' if regime != 'EVENT' else 'REQUIRED'
        e = errors_after(in_block(spec_path(spec.module), spec.name, 'tenant=TenantMode.%s' % regime, 'tenant=TenantMode.%s' % other))
        self.assertTrue(has(e, 'A4', spec.name), (regime, e[:3]))

    def test_a_wrong_regime_is_refused_for_required(self):
        self.wrong('REQUIRED')

    def test_a_wrong_regime_is_refused_for_event(self):
        self.wrong('EVENT')

    def test_a_wrong_regime_is_refused_for_enumerator(self):
        self.wrong('ENUMERATOR')

    def test_a_wrong_regime_is_refused_for_relay(self):
        self.wrong('RELAY')

    def test_a_wrong_regime_is_refused_for_none(self):
        self.wrong('NONE')

    def test_a_wrong_regime_is_refused_for_new(self):
        self.wrong('NEW')


class TestAP05Catalogue(unittest.TestCase):
    def test_a_generic_invented_code_is_refused(self):
        e = errors_after(sub(PAY, "'ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE'", "'GENERIC_INVALID_INPUT'"))
        self.assertTrue(has(e, 'A5', 'GENERIC_INVALID_INPUT'))

    def test_the_catalogue_has_no_generic_structural_code(self):
        """Constat F3 : l'Annexe A ne contient aucun code générique de rejet structurel ; la porte refuse d'en inventer un."""
        import verify_application
        verify_application.VC.purge()
        sys.path.insert(0, REAL)
        from verqia.kernel.errors import ERROR_CATALOGUE
        for invented in ('GENERIC_INVALID_INPUT', 'VALIDATION_FAILED', 'INVALID_REQUEST', 'BAD_REQUEST', 'INVALID_PAYLOAD'):
            self.assertNotIn(invented, ERROR_CATALOGUE)


class TestAP06Audit(unittest.TestCase):
    def test_every_public_command_requires_an_audit_and_no_other_entry_does_unless_named(self):
        for key, s in real_specs().items():
            if s.entry.value == 'PUBLIC':
                self.assertNotEqual(s.audit.value, 'NONE', key)
            elif s.audit.value != 'NONE':
                self.assertIn(s.name, V.AUDIT_NOMINATIVE, key)
        self.assertEqual({s.name for s in real_specs().values() if s.entry.value != 'PUBLIC' and s.audit.value != 'NONE'} - V.AUDIT_NOMINATIVE, set())

    def test_a_service_cannot_carry_an_audit_that_d3_does_not_name(self):
        e = errors_after(in_block(INV, 'ApplySettlement', 'audit=AuditMode.NONE', 'audit=AuditMode.REQUIRED'))
        self.assertTrue(has(e, 'A6', 'ApplySettlement'))

    def test_a_provisioning_step_cannot_carry_an_audit(self):
        e = errors_after(in_block(spec_path('identity'), 'ProvisionOwnerMembership', 'audit=AuditMode.NONE', 'audit=AuditMode.REQUIRED'))
        self.assertTrue(has(e, 'A6') or has(e, 'A10'))

    def test_a_conditional_audit_needs_its_basis(self):
        spec = real_specs()[('collection', 'ExecuteDueAction')]
        e = errors_after(in_block(COL, 'ExecuteDueAction', 'audit_basis=%r' % spec.audit_basis, "audit_basis=''"))
        self.assertTrue(has(e, 'A6', 'sans motif'))

    def test_a_public_command_loses_its_audit_is_refused(self):
        e = errors_after(in_block(ORG, 'CreateOrganization', 'audit=AuditMode.REQUIRED', 'audit=AuditMode.NONE'))
        self.assertTrue(has(e, 'A6', 'CreateOrganization'))


class TestAP09DataOnly(unittest.TestCase):
    def refused(self, statement):
        e = errors_after(append_text(PAY, statement))
        self.assertTrue(has(e, 'H2'), statement)

    def test_the_real_specs_pass_the_data_only_whitelist(self):
        import io
        errors = []
        checked = 0
        for module in sorted({c.module for c in K.COMMANDS}):
            path = os.path.join(REAL, 'verqia', module, 'application', 'specs.py')
            if os.path.exists(path):
                with io.open(path, encoding='utf-8') as f:
                    V.check_data_only(module, f.read(), errors)
                checked += 1
        self.assertEqual(errors, [])
        self.assertGreaterEqual(checked, 19)

    def test_a_lambda_is_not_data(self):
        self.refused('X = (lambda: 1)()')

    def test_a_function_call_is_not_data(self):
        self.refused("X = print('effet')")

    def test_a_hidden_import_is_not_data(self):
        self.refused("X = __import__('os')")

    def test_a_comprehension_is_not_data(self):
        self.refused('X = [i for i in range(3)]')

    def test_an_f_string_is_not_data(self):
        self.refused("X = f'{1 + 1}'")

    def test_a_conditional_expression_is_not_data(self):
        self.refused('X = 1 if True else 2')

    def test_an_operator_is_not_data(self):
        self.refused('X = 1 + 2')

    def test_a_bare_call_statement_is_not_data(self):
        self.refused("open('secret')")

    def test_a_callable_hidden_in_a_field_is_not_data(self):
        e = errors_after(in_block(PAY, 'CreatePayment', "result='OK ou REPLAY, identifiants créés (niveau C)'", 'result=str(1)'))
        self.assertTrue(has(e, 'H2', 'str'))

    def test_a_framework_import_is_not_data(self):
        e = errors_after(append_text(PAY, 'import django'))
        self.assertTrue(has(e, 'import interdit') or any('django' in x for x in e))


class TestAP11Entries(unittest.TestCase):
    def test_the_real_entries_follow_the_nature(self):
        expected = {'command': 'PUBLIC', 'handler': 'REACTION', 'job': 'BACKGROUND', 'worker': 'BACKGROUND', 'system': 'INTERNAL', 'service': 'INTERNAL'}
        for key, s in real_specs().items():
            step = 'organizations.ProvisioningStep' in next(c for c in K.COMMANDS if (c.module, c.name) == key).implements
            self.assertEqual(s.entry.value, 'PROVISIONING_STEP' if step else expected[s.kind], key)

    def test_a_public_command_cannot_be_demoted_to_internal(self):
        e = errors_after(in_block(PAY, 'CreatePayment', 'entry=Entry.PUBLIC', 'entry=Entry.INTERNAL'))
        self.assertTrue(has(e, 'A10', 'CreatePayment'))

    def test_a_reaction_cannot_be_promoted_to_public(self):
        handler = next(c for c in K.COMMANDS if c.module == 'risk' and c.kind == 'handler')
        e = errors_after(in_block(spec_path('risk'), handler.name, 'entry=Entry.REACTION', 'entry=Entry.PUBLIC'))
        self.assertTrue(has(e, 'A10', handler.name))


if __name__ == '__main__':
    unittest.main()
