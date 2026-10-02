"""Mesure PostgreSQL PAR PHASE, sans écrire dans le dépôt (on n'appelle pas `pg_experiments.main`, qui écrit `pg_results.json`).

Phases : import de pgserver ; démarrage à froid (initdb + démarrage) ; connexion ; remise à zéro du schéma (DROP/CREATE + fixtures) ; chaque expérience ;
arrêt ; nettoyage du répertoire ; puis redémarrage à chaud du même répertoire (démarrage seul) pour séparer initdb du démarrage ; latence d'une requête et d'une connexion.
Usage : python diag_pg.py SORTIE.json   (répertoire courant : architecture_registry)
"""
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.getcwd())
T = {}
SLEEPS = []


def timed(label, fn, *a, **k):
    t = time.perf_counter()
    try:
        return fn(*a, **k)
    finally:
        T[label] = T.get(label, 0.0) + (time.perf_counter() - t)


def main():
    out = sys.argv[1]
    t_all = time.perf_counter()
    t = time.perf_counter()
    import pgserver
    import psycopg
    T['import'] = time.perf_counter() - t
    import pg_experiments as X
    real_sleep = time.sleep

    def spy(s):
        SLEEPS.append(s)
        return real_sleep(s)
    X.time.sleep = spy                      # les attentes VOLONTAIRES des expériences (mesurées, pas supposées)

    d = tempfile.mkdtemp(prefix='verqia_diag_pg_')
    srv = timed('demarrage_a_froid (initdb + start)', pgserver.get_server, d, cleanup_mode='stop')
    try:
        db = X.DB(srv.get_uri())
        version = timed('connexion + select version', lambda: db.admin('select version()')[0][0].split(',')[0])
        # latences unitaires
        t = time.perf_counter()
        with psycopg.connect(db.uri, autocommit=True) as c:
            for _ in range(200):
                c.execute('select 1').fetchall()
        T['latence_requete_ms (moyenne de 200)'] = (time.perf_counter() - t) / 200 * 1000
        t = time.perf_counter()
        for _ in range(20):
            psycopg.connect(db.uri).close()
        T['latence_connexion_ms (moyenne de 20)'] = (time.perf_counter() - t) / 20 * 1000
        experiments = {}
        for fn in (X.e1_fk_insert_vs_lock_modes, X.e2_update_columns, X.e3_locker_conflicts, X.e4_deadlock, X.e6_guarded_update,
                   X.e7_unique_insert_waits, X.e8_skip_locked, X.e9_rls, X.e5_advisory_snapshot):
            timed('remise_a_zero_schema (DROP/CREATE + fixtures)', X.reset, db)
            t = time.perf_counter()
            fn(db)
            experiments[fn.__name__] = time.perf_counter() - t
    finally:
        timed('arret_du_serveur', srv.cleanup)
        timed('nettoyage_repertoire', shutil.rmtree, d, ignore_errors=True)
    # redémarrage à chaud : même répertoire recréé par un premier démarrage, puis arrêt, puis démarrage seul
    d2 = tempfile.mkdtemp(prefix='verqia_diag_pg2_')
    s = pgserver.get_server(d2, cleanup_mode='stop')
    s.cleanup()
    t = time.perf_counter()
    s = pgserver.get_server(d2, cleanup_mode='stop')
    T['redemarrage_a_chaud (start seul)'] = time.perf_counter() - t
    s.cleanup()
    shutil.rmtree(d2, ignore_errors=True)
    T['total'] = time.perf_counter() - t_all
    T['attentes_volontaires_des_experiences (sleep)'] = sum(SLEEPS)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'server': version, 'phases': T, 'experiments': experiments, 'results_ok': all(r['ok'] for r in X.RESULTS), 'experiments_run': len(X.RESULTS)}, f, ensure_ascii=False)
    print(json.dumps({'phases': T, 'experiments': experiments}))


if __name__ == '__main__':
    main()
