"""R-12 / PG-11 exécuté : chaque AFFIRMATION sur laquelle repose le mécanisme A+C doit être confirmée par PostgreSQL réel ; les CONSTATS sont observés.
Ignoré si `pgserver` n'est pas installé (pip install pgserver "psycopg[binary]")."""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class TestR12OnRealPostgres(unittest.TestCase):
    def test_every_r12_affirmation_holds_on_real_postgres(self):
        try:
            import pgserver  # noqa: F401
        except ImportError:
            self.skipTest('pgserver absent')
        env = dict(os.environ, PYTHONIOENCODING='utf-8')            # sous Windows, la sortie du fils se décode sinon dans la page de code locale
        r = subprocess.run([sys.executable, os.path.join(HERE, 'r12_pg_experiments.py')], capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertEqual(r.returncode, 0, (r.stdout or '') + (r.stderr or ''))
        with open(os.path.join(HERE, 'r12_pg_results.json'), encoding='utf-8') as f:
            results = {x['id']: x for x in json.load(f)['experiments']}
        for id_ in ('PG-11a', 'PG-11b', 'PG-11d', 'PG-11e', 'PG-11f'):
            self.assertEqual(results[id_]['kind'], 'affirmation', id_)
            self.assertTrue(results[id_]['ok'], results[id_]['observed'])
        self.assertEqual(results['PG-11c']['kind'], 'constat')        # « gagnant introuvable » : atteignable, OBSERVÉ, aucune issue affirmée (R12-O1)


if __name__ == '__main__':
    unittest.main()
