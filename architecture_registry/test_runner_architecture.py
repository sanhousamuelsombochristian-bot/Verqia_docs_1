"""Le coureur reste un harnais : baseline verte, puis INJECTION de violations sur une copie ; chaque règle R1..R5 doit échouer.

Lancement : python -m unittest test_runner_architecture (dans architecture_registry/)
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_contracts as G  # noqa: E402
import locks as L  # noqa: E402
import verify_runner as V  # noqa: E402

REAL = G.DEFAULT_OUT


def errors_after(mutate):
    tmp = tempfile.mkdtemp(prefix='verqia_runner_')
    try:
        shutil.copytree(os.path.join(REAL, 'application_runner'), os.path.join(tmp, 'application_runner'), ignore=shutil.ignore_patterns('__pycache__'))
        mutate(tmp)
        errors, _ = V.verify(tmp)
        return errors
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def append(rel, text):
    def f(root):
        p = os.path.join(root, rel.replace('/', os.sep))
        with io.open(p, 'a', encoding='utf-8', newline='') as fh:
            fh.write('\n' + text + '\n')
    return f


def replace(rel, old, new):
    def f(root):
        p = os.path.join(root, rel.replace('/', os.sep))
        with io.open(p, encoding='utf-8', newline='') as fh:
            s = fh.read()
        assert old in s, (rel, old)
        with io.open(p, 'w', encoding='utf-8', newline='') as fh:
            fh.write(s.replace(old, new, 1))
    return f


def has(errors, prefix, needle=''):
    return any(e.startswith(prefix) and needle in e for e in errors)


RUNNER = 'application_runner/runner.py'
LOCKS = 'application_runner/doubles/locks.py'


class TestBaseline(unittest.TestCase):
    def test_the_runner_is_a_harness(self):
        errors, n = V.verify(REAL)
        self.assertEqual(errors, [])
        self.assertGreaterEqual(n, 10)

    def test_tests_are_not_scanned_but_sources_are(self):
        errors, n = V.verify(REAL)
        rels = [rel for rel, _ in V.sources(REAL)]
        self.assertTrue(all('/tests/' not in r for r in rels))
        self.assertIn(RUNNER, rels)


class TestInjection(unittest.TestCase):
    def test_r1_framework_import(self):
        self.assertTrue(has(errors_after(append(RUNNER, 'import django')), 'R1', 'django'))
        self.assertTrue(has(errors_after(append(RUNNER, 'from psycopg import connect')), 'R1', 'psycopg'))
        self.assertTrue(has(errors_after(append(RUNNER, 'import redis')), 'R1', 'redis'))

    def test_r1_third_party_import(self):
        self.assertTrue(has(errors_after(append(RUNNER, 'import requests')), 'R1', 'requests'))

    def test_r1_module_layers_are_forbidden(self):
        self.assertTrue(has(errors_after(append(RUNNER, 'from verqia.payments.domain import x')), 'R1', 'verqia.kernel'))
        self.assertTrue(has(errors_after(append(RUNNER, 'from verqia.kernel.domain import x')), 'R1', 'couche'))

    def test_r1_relative_import(self):
        self.assertTrue(has(errors_after(append(RUNNER, 'from . import errors')), 'R1', 'relatif'))

    def test_r2_a_hand_written_lock_resource(self):
        resource = sorted(L.RESOURCES)[1]
        self.assertTrue(has(errors_after(append(LOCKS, 'HAND = (%r,)' % resource)), 'R2', resource))

    def test_r2_a_hand_written_lock_operation(self):
        op = sorted(L.OPERATIONS)[0]
        self.assertTrue(has(errors_after(append(RUNNER, 'OP = %r' % op)), 'R2', op))

    def test_r2_a_hand_written_ladder_is_refused(self):
        ladder = tuple(sorted(L.RESOURCES)[:3])
        self.assertTrue(has(errors_after(append(LOCKS, 'ORDER = %r' % (ladder,))), 'R2'))

    def test_r3_the_generated_ladder_must_be_used(self):
        e = errors_after(replace(LOCKS, 'from verqia.kernel import lock_registry as LR', 'from verqia.kernel import errors as LR'))
        self.assertTrue(has(e, 'R3', 'lock_registry'))
        e = errors_after(replace(RUNNER, 'from verqia.kernel import lock_registry as LR', 'from verqia.kernel import errors as LR'))
        self.assertTrue(has(e, 'R3', 'runner.py'))

    def test_r3_missing_file(self):
        def m(root):
            os.remove(os.path.join(root, 'application_runner', 'doubles', 'locks.py'))
        self.assertTrue(has(errors_after(m), 'R3', 'absent'))

    def test_r5_the_host_clock_is_forbidden(self):
        self.assertTrue(has(errors_after(append(RUNNER, 'import time')), 'R5', 'import time'))
        self.assertTrue(has(errors_after(append(RUNNER, 'from time import monotonic')), 'R5', 'from time'))
        self.assertTrue(has(errors_after(append(RUNNER, 'X = datetime.now()')), 'R5', 'datetime.now'))
        self.assertTrue(has(errors_after(append(RUNNER, 'X = datetime.datetime.utcnow()')), 'R5', 'utcnow'))
        self.assertTrue(has(errors_after(append(RUNNER, 'X = date.today()')), 'R5', 'today'))
        self.assertTrue(has(errors_after(append('application_runner/transport.py', 'X = time.time()')), 'R5', 'time.time'))

    def test_the_causation_limit_of_the_runner_is_the_frozen_invariant_x7(self):
        import re
        sys.path.insert(0, REAL)
        import verify_contracts
        verify_contracts.purge()
        from application_runner.transport import MAX_CAUSATION_DEPTH
        with io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ENGINE_CONTRACTS_V1.md'), encoding='utf-8') as f:
            text = f.read()
        m = re.search(r'\| X7 \| `causation_depth ≤ (\d+)`', text)
        self.assertIsNotNone(m)
        self.assertEqual(MAX_CAUSATION_DEPTH, int(m.group(1)))

    def test_r4_a_hand_written_use_case_name(self):
        self.assertTrue(has(errors_after(append(RUNNER, "UC = 'AllocatePayment'")), 'R4', 'AllocatePayment'))


if __name__ == '__main__':
    unittest.main()
