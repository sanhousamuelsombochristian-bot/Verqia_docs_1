"""TA-12 exécuté : chaque expérience PostgreSQL doit confirmer l'affirmation du document d'architecture.
Ignoré si `pgserver` n'est pas installé (pip install pgserver "psycopg[binary]")."""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class TestPostgresLocks(unittest.TestCase):
    def test_all_experiments_confirm_the_architecture(self):
        try:
            import pgserver  # noqa: F401
        except ImportError:
            self.skipTest('pgserver absent')
        r = subprocess.run([sys.executable, os.path.join(HERE, 'pg_experiments.py')], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
