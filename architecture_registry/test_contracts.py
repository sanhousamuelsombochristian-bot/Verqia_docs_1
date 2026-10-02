"""Registry ↔ Contracts : baseline verte, puis INJECTION de violations sur une copie des contrats : chaque propriété doit échouer.

Lancement : python -m unittest test_contracts (dans architecture_registry/)
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_contracts as G  # noqa: E402
import verify_contracts as V  # noqa: E402

REAL = G.DEFAULT_OUT


def read(root, rel):
    with io.open(os.path.join(root, rel.replace('/', os.sep)), encoding='utf-8', newline='') as f:
        return f.read()


def write(root, rel, text):
    with io.open(os.path.join(root, rel.replace('/', os.sep)), 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def errors_after(mutate):
    tmp = tempfile.mkdtemp(prefix='verqia_contracts_')
    try:
        shutil.copytree(os.path.join(REAL, 'verqia'), os.path.join(tmp, 'verqia'))
        mutate(tmp)
        errors, _, _ = V.verify(tmp)
        return errors
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestBaseline(unittest.TestCase):
    def test_generated_contracts_are_faithful_to_the_registries(self):
        errors, findings, stats = V.verify(REAL)
        self.assertEqual(errors, [])
        self.assertEqual(stats['events'], 77)
        self.assertEqual(stats['commands'] + stats['handlers'], 122)
        self.assertEqual(stats['error_codes'], 109)

    def test_generation_is_deterministic(self):
        a, _ = G.generate()
        b, _ = G.generate()
        self.assertEqual(a, b)

    def test_no_empty_contract_file_is_generated(self):
        files, _ = G.generate()
        for rel, text in files.items():
            if rel.endswith('/contracts/__init__.py') or rel.endswith('__init__.py'):
                continue
            self.assertGreater(len(text.strip().split('\n')), 4, rel)

    def test_module_without_commands_has_no_commands_file(self):
        files, _ = G.generate()
        self.assertNotIn('verqia/rules/contracts/commands.py', files)          # rules n'a que des requêtes
        self.assertNotIn('verqia/kernel/contracts/commands.py', files)
        self.assertNotIn('verqia/config/contracts/__init__.py', files)         # config : racine de composition, aucun contrat

    def test_no_finding_remains_after_the_request_amendment(self):
        _, findings, _ = V.verify(REAL)
        self.assertEqual(findings, [])

    def test_request_emitters_import_the_engine_contracts_and_nothing_else(self):
        for m, engines in (('imports', {'risk', 'priority', 'cashflow'}), ('automation', {'cashflow'})):
            self.assertTrue(engines <= set(V.M.MODULES[m]['deps']), m)


class TestInjectedViolations(unittest.TestCase):
    def test_p1_missing_command_contract(self):
        def m(root):
            os.remove(os.path.join(root, 'verqia', 'customers', 'contracts', 'commands.py'))
        self.assertTrue(any(e.startswith('P1 customers') for e in errors_after(m)))

    def test_p1_metadata_drift(self):
        def m(root):
            rel = 'verqia/customers/contracts/commands.py'
            write(root, rel, read(root, rel).replace("('customers.record',)", "('invoices.body',)", 1))
        errs = errors_after(m)
        self.assertTrue(any('P1 customers.' in e and 'WRITES' in e for e in errs))

    def test_p1_handler_subscription_changed(self):
        def m(root):
            rel = 'verqia/promises/contracts/events.py'
            write(root, rel, read(root, rel).replace('subscribes=(InvoicePaid,)', 'subscribes=(InvoiceVoided,)', 1))
        self.assertTrue(any(e.startswith('P1 promises.') for e in errors_after(m)))

    def test_p2_duplicate_canonical_event_definition(self):
        def m(root):
            rel = 'verqia/customers/contracts/events.py'
            write(root, rel, read(root, rel) + "\n\n@dataclass(frozen=True)\nclass InvoicePaidAgain(Event):\n    TYPE: ClassVar[str] = 'INVOICE_PAID'\n"
                  "    CATEGORY: ClassVar[EventCategory] = EventCategory.TRANSITION\n    AGGREGATE: ClassVar[str] = 'invoice'\n    SCHEMA_VERSION: ClassVar[int] = 1\n")
        self.assertTrue(any(e.startswith('P2 INVOICE_PAID') for e in errors_after(m)))

    def test_p2_event_in_the_wrong_module(self):
        def m(root):
            src = read(root, 'verqia/payments/contracts/events.py')
            self.assertIn('class PaymentCreated', src)
            write(root, 'verqia/payments/contracts/events.py', src.replace("TYPE: ClassVar[str] = 'PAYMENT_CREATED'", "TYPE: ClassVar[str] = 'PAYMENT_MADE'", 1))
        errs = errors_after(m)
        self.assertTrue(any('PAYMENT_MADE' in e or 'PAYMENT_CREATED' in e for e in errs))

    def test_p2_fact_event_disguised_as_a_request(self):
        def m(root):
            rel = 'verqia/invoices/contracts/events.py'
            write(root, rel, read(root, rel).replace('class InvoicePaid(Event)', 'class InvoicePaymentRequested(Event)', 1))
        self.assertTrue(any('INVOICE_PAID' in e and ('demande' in e or 'nom' in e) for e in errors_after(m)))

    def test_p2_category_changed(self):
        def m(root):
            rel = 'verqia/invoices/contracts/events.py'
            src = read(root, rel)
            i = src.index("TYPE: ClassVar[str] = 'INVOICE_PAID'")
            j = src.index('EventCategory.', i)
            k = src.index('\n', j)
            write(root, rel, src[:j] + 'EventCategory.REQUEST' + src[k:])
        self.assertTrue(any('INVOICE_PAID' in e and 'catégorie' in e for e in errors_after(m)))

    def test_p2_payload_field_removed(self):
        def m(root):
            rel = 'verqia/invoices/contracts/events.py'
            src = read(root, rel)
            i = src.index("class InvoiceCreated")
            j = src.index('    total_minor: int\n', i)
            write(root, rel, src[:j] + src[j + len('    total_minor: int\n'):])
        self.assertTrue(any('INVOICE_CREATED' in e and 'payload' in e for e in errors_after(m)))

    def test_p3_port_declared_in_the_wrong_module(self):
        def m(root):
            rel = 'verqia/organizations/contracts/ports.py'
            write(root, rel, read(root, rel) + "\n\nclass Clock(Protocol):\n    def as_of(self) -> None: ...\n")
        self.assertTrue(any(e.startswith('P3 organizations') for e in errors_after(m)))

    def test_p3_port_outside_a_ports_file(self):
        def m(root):
            rel = 'verqia/customers/contracts/commands.py'
            write(root, rel, read(root, rel) + "\n\nfrom typing import Protocol\n\n\nclass Sneaky(Protocol):\n    def go(self) -> None: ...\n")
        self.assertTrue(any('hors d\'un fichier `ports.py`' in e for e in errors_after(m)))

    def test_p4_import_of_an_undeclared_dependency(self):
        def m(root):
            rel = 'verqia/customers/contracts/commands.py'
            write(root, rel, read(root, rel) + "\nfrom verqia.collection.contracts.events import CollectionActionSuppressed\n")
        self.assertTrue(any('dépendance interdite `customers → collection`' in e for e in errors_after(m)))

    def test_p4_import_of_another_modules_internals(self):
        def m(root):
            rel = 'verqia/payments/contracts/commands.py'
            write(root, rel, read(root, rel) + "\nfrom verqia.invoices.domain.invoice import Invoice\n")
        self.assertTrue(any('ne s\'importe que par `contracts`' in e for e in errors_after(m)))

    def test_h_framework_import_is_forbidden(self):
        for stmt in ('from django.db import models', 'import redis', 'from psycopg import connect', 'import requests'):
            def m(root, stmt=stmt):
                rel = 'verqia/kernel/types.py'
                write(root, rel, read(root, rel) + '\n' + stmt + '\n')
            self.assertTrue(any('import interdit' in e for e in errors_after(m)), stmt)

    def test_h_behaviour_is_forbidden_at_this_level(self):
        def m(root):
            rel = 'verqia/invoices/contracts/commands.py'
            write(root, rel, read(root, rel) + "\n\ndef validate(x):\n    if x:\n        return True\n    return False\n")
        errs = errors_after(m)
        self.assertTrue(any('fonction de module interdite' in e for e in errs))
        self.assertTrue(any('comportement interdit' in e for e in errs))

    def test_h_port_with_a_body_is_forbidden(self):
        def m(root):
            rel = 'verqia/kernel/ports.py'
            write(root, rel, read(root, rel).replace('    def as_of(self) -> datetime: ...', '    def as_of(self) -> datetime:\n        return None', 1))
        self.assertTrue(any('a un corps' in e for e in errors_after(m)))

    def test_h_models_file_is_refused(self):
        def m(root):
            write(root, 'verqia/customers/models.py', '"""interdit à cette étape."""\n')
        self.assertTrue(any('fichier en trop' in e and 'models.py' in e for e in errors_after(m)))

    def test_h_hand_edit_is_detected_as_drift(self):
        def m(root):
            rel = 'verqia/rules/contracts/queries.py'
            write(root, rel, read(root, rel) + '\n# modification manuelle\n')
        self.assertTrue(any('dérive' in e and 'rules/contracts/queries.py' in e for e in errors_after(m)))

    def test_h_organization_is_never_a_command_field(self):
        files, _ = G.generate()
        for rel, text in files.items():
            if rel.endswith('/contracts/commands.py'):
                self.assertNotIn('organization_id:', text, rel)


if __name__ == '__main__':
    unittest.main()
