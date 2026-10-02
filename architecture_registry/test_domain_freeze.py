"""Gel du Domain V1, tranche 1 : l'empreinte tient, elle couvre ce qu'elle doit, et elle détecte toute modification non journalisée."""
import os
import tempfile
import unittest
from unittest import mock

import domain_freeze as FZ


class TestDomainFreeze(unittest.TestCase):
    def test_the_frozen_fingerprint_matches_the_files(self):
        self.assertEqual(FZ.check_freeze(), [])

    def test_the_journal_starts_empty_and_agrees_with_the_freeze(self):
        self.assertEqual(FZ.AMENDMENTS, [])
        self.assertEqual(FZ.read_freeze()['amendments'], 0)

    def test_the_fingerprint_covers_the_domain_the_reference_the_tests_and_the_gate(self):
        rels = {os.path.relpath(p, os.path.dirname(FZ.APP)).replace(os.sep, '/') for p in FZ.files()}
        for expected in ('verqia-app/verqia/invoices/domain/settlement.py', 'verqia-app/verqia/payments/domain/allocations.py', 'verqia-app/verqia/kernel/decision.py',
                         'verqia-app/verqia/invoices/contracts/facts.py', 'verqia-docs/reference_model/finance_ref.py', 'verqia-docs/reference_model/golden_finance.json',
                         'verqia-app/domain_tests/test_dt_reference.py', 'verqia-app/domain_tests/runner_wiring.py', 'verqia-docs/architecture_registry/domain_mutations.py'):
            self.assertIn(expected, rels)

    def test_a_modified_or_added_file_breaks_the_freeze(self):
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write('# fichier ajouté sans amendement\n')
        try:
            with mock.patch.object(FZ, 'files', lambda: _with_extra(f.name)):
                errors = FZ.check_freeze()
            self.assertTrue(any('amendement non journalisé' in e for e in errors), errors)
        finally:
            os.unlink(f.name)

    def test_line_endings_do_not_change_the_fingerprint(self):
        import hashlib
        a = hashlib.sha256('x\ny\n'.encode()).hexdigest()
        b = hashlib.sha256('x\r\ny\r\n'.replace('\r\n', '\n').encode()).hexdigest()
        self.assertEqual(a, b)


_real_files = FZ.files


def _with_extra(path):
    return _real_files() + [path]


if __name__ == '__main__':
    unittest.main()
