"""R-12 / PG-11 : la course de création dédupliquée sur PostgreSQL RÉEL (serveur embarqué `pgserver`).

Ce script CONSTATE ; il ne décide rien. Il rejoue, avec de vraies transactions concurrentes, le protocole que le coureur suppose (A+C) :
T1 insère une `dedup_key` ; T2 insère la même et attend ; T1 valide (ou annule) ; T2 reçoit (ou non) la violation ; T2 annule ; une transaction de reprise
relit l'occupant de la contrainte par son prédicat partiel. Script SÉPARÉ de `pg_experiments.py` (TA-12) : il n'alimente ni `pg_results.json` ni le registre gelé.

Le nom de contrainte `uq_r12_probe_dedup_key` est un nom de SONDE : il ne fixe pas le nom de la migration (R12-O3).

Usage : python architecture_registry/r12_pg_experiments.py      (écrit `r12_pg_results.json` ; code 1 si une affirmation est contredite)
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time

from psycopg import errors

from pg_experiments import DB

HERE = os.path.dirname(os.path.abspath(__file__))
CONSTRAINT = 'uq_r12_probe_dedup_key'
RESULTS = []
LEVELS = ('READ COMMITTED', 'REPEATABLE READ', 'SERIALIZABLE')


def record(id_, kind, title, expected, observed, ok):
    """`kind` : `affirmation` (ce sur quoi R-12 repose : un échec fait échouer le script) ou `constat` (observé, rien n'est affirmé)."""
    RESULTS.append({'id': id_, 'kind': kind, 'title': title, 'expected': expected, 'observed': observed, 'ok': bool(ok)})


def reset(db):
    db.admin('DROP SCHEMA IF EXISTS public CASCADE')
    db.admin('CREATE SCHEMA public')
    db.admin("""
      CREATE TABLE probe_actions (organization_id int NOT NULL, id int NOT NULL, dedup_key text NOT NULL, status text NOT NULL,
                                  CONSTRAINT probe_actions_pkey PRIMARY KEY (id));
      CREATE UNIQUE INDEX %s ON probe_actions (organization_id, dedup_key) WHERE status NOT IN ('CANCELLED', 'SUPPRESSED');
    """ % CONSTRAINT)


def live_occupant(db, isolation, org, key):
    """La lecture de reprise de C : une NOUVELLE transaction, même isolation, lit l'occupant par le prédicat de l'index."""
    c = db.conn()
    try:
        c.execute('SET TRANSACTION ISOLATION LEVEL %s' % isolation)
        row = c.execute("SELECT id, status FROM probe_actions WHERE organization_id = %s AND dedup_key = %s AND status NOT IN ('CANCELLED', 'SUPPRESSED')",
                        (org, key)).fetchone()
        c.commit()
        return row
    finally:
        c.close()


def waiting(db, pid):
    row = db.admin('select wait_event_type from pg_stat_activity where pid = %s', pid)
    return bool(row) and row[0][0] == 'Lock'


def race(db, isolation, winner_ends, between=None, loser_row=(1, 11, 'K', 'PROPOSED'), fast_path=False):
    """T1 insère (1, 10, 'K') ; T2 (isolation donnée) insère `loser_row` dans un fil ; T1 se termine par `winner_ends` ; `between` s'exécute
    après la fin de T2 et avant la reprise. Rend ce que T2 a vécu et ce que la reprise lit."""
    t1, t2 = db.conn(), db.conn()
    out = {}
    try:
        t2.execute('SET TRANSACTION ISOLATION LEVEL %s' % isolation)
        if fast_path:                                                  # le chemin rapide A : T2 LIT la clé (vide) avant que T1 n'insère
            t2.execute("SELECT id FROM probe_actions WHERE organization_id = 1 AND dedup_key = 'K' AND status NOT IN ('CANCELLED', 'SUPPRESSED')").fetchall()
        else:
            t2.execute('SELECT 1')                                     # instantané de T2 pris AVANT l'insertion de T1 (le cas défavorable)
        pid2 = t2.info.backend_pid
        t1.execute("INSERT INTO probe_actions VALUES (1, 10, 'K', 'PROPOSED')")

        def loser():
            try:
                t2.execute('INSERT INTO probe_actions VALUES (%s, %s, %s, %s)', loser_row)
                out['t2'] = ('inserted', None, None)
                t2.commit()
            except errors.Error as e:
                out['t2'] = (type(e).__name__, e.sqlstate, getattr(e.diag, 'constraint_name', None))
                t2.rollback()
        th = threading.Thread(target=loser)
        th.start()
        deadline = time.time() + 5
        while time.time() < deadline and not waiting(db, pid2):
            time.sleep(0.02)
        out['waited'] = waiting(db, pid2)
        if winner_ends == 'commit':
            t1.commit()
        else:
            t1.rollback()
        th.join(timeout=10)
        out['joined'] = not th.is_alive()
    finally:
        t1.close()
        t2.close()
    if between:
        between(db)
    out['recovery'] = live_occupant(db, isolation, 1, 'K')
    return out


def pg11_committed_winner(db):
    for level in LEVELS:
        reset(db)
        r = race(db, level, 'commit')
        kind, state, name = r.get('t2', (None, None, None))
        tag = level.replace(' ', '_')
        observed = 'T2 a attendu : %s ; T2 : %s, SQLSTATE %s, contrainte %s ; reprise : %s' % ('oui' if r['waited'] else 'non', kind, state, name, r['recovery'])
        if level == 'READ COMMITTED':
            record('PG-11a', 'affirmation', "READ COMMITTED : l'`INSERT` BLOQUÉ de T2 reçoit lui-même 23505, avec le nom de la contrainte partielle ; la reprise voit le gagnant",
                   "attente oui ; 23505 ; %s ; reprise (10, 'PROPOSED')" % CONSTRAINT, observed,
                   r['waited'] and r['joined'] and state == '23505' and name == CONSTRAINT and r['recovery'] == (10, 'PROPOSED'))
        else:
            record('PG-11a-%s' % tag, 'constat', "%s, instantané de T2 antérieur à l'insertion de T1 : ce que reçoit l'`INSERT` bloqué ; ce que lit la reprise" % level,
                   'à constater (23505 avec le nom, ou 40001 de sérialisation)', observed, r['joined'] and state in ('23505', '40001') and r['recovery'] == (10, 'PROPOSED'))


def pg11_fast_path_then_insert(db):
    """Le protocole RÉEL du coureur : A lit la clé (absente), puis l'écriture. Ce que reçoit l'`INSERT` bloqué, par isolation."""
    for level in LEVELS:
        reset(db)
        r = race(db, level, 'commit', fast_path=True)
        kind, state, name = r.get('t2', (None, None, None))
        observed = 'T2 a attendu : %s ; T2 : %s, SQLSTATE %s, contrainte %s ; reprise : %s' % ('oui' if r['waited'] else 'non', kind, state, name, r['recovery'])
        record('PG-11g-%s' % level.replace(' ', '_'), 'constat', "%s, A puis INSERT : ce que reçoit l'`INSERT` bloqué après la validation du gagnant" % level,
               'à constater (23505 avec le nom, ou 40001 de sérialisation)', observed, r['joined'] and state in ('23505', '40001') and r['recovery'] == (10, 'PROPOSED'))


def pg11_rolled_back_winner(db):
    for level in LEVELS:
        reset(db)
        r = race(db, level, 'rollback')
        observed = 'T2 a attendu : %s ; T2 : %s ; reprise : %s' % ('oui' if r['waited'] else 'non', r.get('t2'), r['recovery'])
        record('PG-11b' + ('' if level == 'READ COMMITTED' else '-' + level.replace(' ', '_')), 'affirmation',
               "%s : T1 annule ; l'`INSERT` bloqué de T2 réussit, aucune violation (un 23505 n'est jamais dû à une ligne non validée)" % level,
               "attente oui ; T2 inséré ; occupant (11, 'PROPOSED')", observed,
               r['waited'] and r.get('t2', ('',))[0] == 'inserted' and r['recovery'] == (11, 'PROPOSED'))


def pg11_vanished_winner(db):
    def cancel(d):
        d.admin("UPDATE probe_actions SET status = 'CANCELLED' WHERE id = 10")
    reset(db)
    r = race(db, 'READ COMMITTED', 'commit', between=cancel)
    observed = 'T2 : %s ; T3 annule le gagnant ; reprise : %s' % (r.get('t2'), r['recovery'])
    record('PG-11c', 'constat', "« Gagnant introuvable » (R12-O1) : T1 valide, T2 reçoit 23505, PUIS une 3e transaction annule le gagnant avant la reprise",
           "à constater : le cas est-il atteignable ?", observed, r.get('t2', (None, None))[1] == '23505' and r['recovery'] is None)
    reset(db)
    r = race(db, 'READ COMMITTED', 'commit')
    record('PG-11d', 'affirmation', "Sans transition concurrente hors de l'index entre la violation et la reprise, le gagnant est TOUJOURS relu",
           "reprise (10, 'PROPOSED')", 'reprise : %s' % (r['recovery'],), r['recovery'] == (10, 'PROPOSED'))


def pg11_other_constraint(db):
    reset(db)
    r = race(db, 'READ COMMITTED', 'commit', loser_row=(1, 10, 'OTHER', 'PROPOSED'))
    kind, state, name = r.get('t2', (None, None, None))
    record('PG-11e', 'affirmation', "Une AUTRE contrainte d'unicité (clé primaire) donne aussi 23505, mais avec SON nom : le nom seul distingue la dédup",
           '23505 ; probe_actions_pkey', 'SQLSTATE %s, contrainte %s' % (state, name), state == '23505' and name == 'probe_actions_pkey')


def pg11_excluded_statuses_do_not_block(db):
    reset(db)
    seen = {}
    for status in ('CANCELLED', 'SUPPRESSED', 'DONE', 'FAILED'):
        db.admin('DELETE FROM probe_actions')
        db.admin("INSERT INTO probe_actions VALUES (1, 10, 'K', %s)", status)
        try:
            db.admin("INSERT INTO probe_actions VALUES (1, 11, 'K', 'PROPOSED')")
            seen[status] = 'acceptée'
        except errors.UniqueViolation as e:
            seen[status] = '23505 %s' % e.diag.constraint_name
    record('PG-11f', 'affirmation', "Prédicat partiel (DATA_CONTRACT §6.1) : `CANCELLED` et `SUPPRESSED` ne bloquent pas ; `DONE` et `FAILED` bloquent",
           'CANCELLED, SUPPRESSED acceptées ; DONE, FAILED : 23505', ' ; '.join('%s : %s' % kv for kv in seen.items()),
           seen['CANCELLED'] == seen['SUPPRESSED'] == 'acceptée' and seen['DONE'] == seen['FAILED'] == '23505 %s' % CONSTRAINT)


def main():
    import pgserver
    d = tempfile.mkdtemp(prefix='verqia_r12_pg_')
    srv = pgserver.get_server(d, cleanup_mode='stop')
    try:
        db = DB(srv.get_uri())
        version = db.admin('select version()')[0][0].split(',')[0]
        for fn in (pg11_committed_winner, pg11_fast_path_then_insert, pg11_rolled_back_winner, pg11_vanished_winner, pg11_other_constraint, pg11_excluded_statuses_do_not_block):
            fn(db)
    finally:
        srv.cleanup()
        shutil.rmtree(d, ignore_errors=True)
    with open(os.path.join(HERE, 'r12_pg_results.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'server': version, 'experiments': RESULTS}, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(version)
    for r in RESULTS:
        print(('OK ' if r['ok'] else 'KO '), r['id'], '[%s]' % r['kind'], '|', r['observed'])
    sys.exit(0 if all(r['ok'] for r in RESULTS if r['kind'] == 'affirmation') else 1)


if __name__ == '__main__':
    main()
