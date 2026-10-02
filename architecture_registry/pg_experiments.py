"""TA-12 : expériences sur PostgreSQL RÉEL (serveur embarqué `pgserver`), deux transactions concurrentes chacune.

Chaque expérience confronte une affirmation du document d'architecture au comportement observé. Le résultat est écrit dans
`pg_results.json`, repris par `build_registry.py` (ARCHITECTURE_REGISTRY_V1.md §7).

Usage : python architecture_registry/pg_experiments.py
Dépendances : pip install pgserver "psycopg[binary]"
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time

import psycopg
from psycopg import errors

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []


def record(id_, title, expected, observed, ok):
    RESULTS.append({'id': id_, 'title': title, 'expected': expected, 'observed': observed, 'ok': bool(ok)})


class DB:
    def __init__(self, uri):
        self.uri = uri

    def conn(self):
        c = psycopg.connect(self.uri, autocommit=False)
        return c

    def admin(self, sql, *args):
        with psycopg.connect(self.uri, autocommit=True) as c:
            return c.execute(sql, args).fetchall() if sql.strip().lower().startswith('select') else c.execute(sql, args)


def reset(db):
    db.admin('DROP SCHEMA IF EXISTS public CASCADE')
    db.admin('CREATE SCHEMA public')
    db.admin("""
      CREATE TABLE parent (organization_id int NOT NULL, id int PRIMARY KEY, status text NOT NULL DEFAULT 'SCHEDULED', dedup_key text, name text,
                           UNIQUE (organization_id, id));
      CREATE UNIQUE INDEX uq_parent_dedup ON parent (organization_id, dedup_key) WHERE status NOT IN ('CANCELLED', 'SUPPRESSED');
      CREATE TABLE child (organization_id int NOT NULL, id serial PRIMARY KEY, parent_id int NOT NULL,
                          FOREIGN KEY (organization_id, parent_id) REFERENCES parent (organization_id, id));
      CREATE TABLE src (v int);
      CREATE TABLE act (id int PRIMARY KEY, status text);
      INSERT INTO parent VALUES (1, 1, 'SCHEDULED', 'k1', 'n'), (1, 2, 'SCHEDULED', 'k2', 'n'), (2, 3, 'SCHEDULED', 'k3', 'n');
      INSERT INTO act VALUES (1, 'SCHEDULED');
    """)


def blocked_by(db, holder_sql, other_sql, timeout_ms=400):
    """Une transaction tient `holder_sql` ; une seconde exécute `other_sql`. Vrai si la seconde attend au-delà du délai."""
    a, b = db.conn(), db.conn()
    try:
        a.execute(holder_sql)
        b.execute("SET lock_timeout = %d" % timeout_ms)
        try:
            b.execute(other_sql)
            return False
        except errors.LockNotAvailable:
            return True
    finally:
        for c in (b, a):
            try:
                c.rollback()
            finally:
                c.close()


def e1_fk_insert_vs_lock_modes(db):
    modes = {'FOR UPDATE': True, 'FOR NO KEY UPDATE': False, 'FOR SHARE': False, 'FOR KEY SHARE': False}
    obs, ok = [], True
    for mode, expect in modes.items():
        got = blocked_by(db, "SELECT 1 FROM parent WHERE id = 1 %s" % mode, "INSERT INTO child (organization_id, parent_id) VALUES (1, 1)")
        obs.append('%s : %s' % (mode, 'bloque' if got else 'ne bloque pas'))
        ok &= (got == expect)
    record('PG-01', 'Une clé étrangère prend `FOR KEY SHARE` sur la ligne référencée : qui bloque l\'insertion d\'un enfant ?',
           'seul `FOR UPDATE` bloque ; `FOR NO KEY UPDATE`, `FOR SHARE` et `FOR KEY SHARE` ne bloquent pas', ' ; '.join(obs), ok)


def e2_update_columns(db):
    cases = [('colonne ordinaire (`name`)', "UPDATE parent SET name = 'x' WHERE id = 1"),
             ('colonne du prédicat d\'un index unique partiel (`status`)', "UPDATE parent SET status = 'DONE' WHERE id = 1"),
             ('colonne clé d\'un index unique partiel (`dedup_key`)', "UPDATE parent SET dedup_key = 'kz' WHERE id = 1")]
    obs = []
    ordinary_ok = None
    for label, sql in cases:
        got = blocked_by(db, sql, "INSERT INTO child (organization_id, parent_id) VALUES (1, 1)")
        obs.append('%s : %s' % (label, 'bloque les enfants' if got else 'ne bloque pas'))
        if ordinary_ok is None:
            ordinary_ok = not got
    record('PG-02', 'Quel verrou prend un `UPDATE` selon la colonne modifiée ? (une modification d\'état ne doit pas bloquer les insertions qui référencent la ligne)',
           'colonne ordinaire : ne bloque pas ; les autres cas sont à MESURER (ils décident du mode de verrou réellement pris par les changements d\'état)',
           ' ; '.join(obs), ordinary_ok)


def e3_locker_conflicts(db):
    pairs = [('FOR NO KEY UPDATE', 'FOR NO KEY UPDATE', True), ('FOR SHARE', 'FOR NO KEY UPDATE', True), ('FOR KEY SHARE', 'FOR NO KEY UPDATE', False),
             ('FOR UPDATE', 'FOR KEY SHARE', True)]
    obs, ok = [], True
    for h, o, expect in pairs:
        got = blocked_by(db, "SELECT 1 FROM parent WHERE id = 1 %s" % h, "SELECT 1 FROM parent WHERE id = 1 %s" % o)
        obs.append('%s puis %s : %s' % (h, o, 'conflit' if got else 'compatible'))
        ok &= (got == expect)
    record('PG-03', 'Conflits entre modes de verrou de ligne (base de TD27)', 'deux `NO KEY UPDATE` et `SHARE` / `NO KEY UPDATE` conflictuent ; `KEY SHARE` / `NO KEY UPDATE` sont compatibles ; `UPDATE` / `KEY SHARE` conflictuent',
           ' ; '.join(obs), ok)


def deadlock_run(db, order_a, order_b):
    results, barrier = {}, threading.Barrier(2)

    def worker(name, order):
        c = db.conn()
        try:
            c.execute("SET deadlock_timeout = '200ms'")
            c.execute("SELECT 1 FROM parent WHERE id = %s FOR NO KEY UPDATE", (order[0],))
            if order_a != order_b:
                barrier.wait(timeout=5)
            time.sleep(0.15)
            c.execute("SELECT 1 FROM parent WHERE id = %s FOR NO KEY UPDATE", (order[1],))
            c.commit()
            results[name] = 'ok'
        except errors.DeadlockDetected:
            results[name] = 'deadlock'
            c.rollback()
        except Exception as e:  # noqa: BLE001
            results[name] = type(e).__name__
            c.rollback()
        finally:
            c.close()

    ts = [threading.Thread(target=worker, args=('A', order_a)), threading.Thread(target=worker, args=('B', order_b))]
    [t.start() for t in ts]
    [t.join(timeout=15) for t in ts]
    return results


def e4_deadlock(db):
    bad = deadlock_run(db, (1, 2), (2, 1))
    good = deadlock_run(db, (1, 2), (1, 2))
    ok = sorted(bad.values()) == ['deadlock', 'ok'] and sorted(good.values()) == ['ok', 'ok']
    record('PG-04', 'Ordre croisé et ordre commun sur deux lignes', 'ordre croisé : un interblocage détecté (`40P01`) ; même ordre : aucun',
           'ordre croisé : %s ; même ordre : %s' % (sorted(bad.values()), sorted(good.values())), ok)


def snapshot_run(db, isolation):
    a = db.conn()
    out = {}
    db.admin('TRUNCATE src')
    a.execute('SELECT pg_advisory_xact_lock(42)')

    def waiter():
        b = db.conn()
        try:
            b.execute('BEGIN ISOLATION LEVEL %s' % isolation) if False else None
            b.execute('SET TRANSACTION ISOLATION LEVEL %s' % isolation)
            b.execute('SELECT pg_advisory_xact_lock(42)')
            out['count'] = b.execute('SELECT count(*) FROM src').fetchone()[0]
            b.commit()
        finally:
            b.close()
    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.4)
    a.execute('INSERT INTO src VALUES (1)')
    a.commit()
    a.close()
    t.join(timeout=10)
    return out.get('count')


def e5_advisory_snapshot(db):
    rr = snapshot_run(db, 'REPEATABLE READ')
    rc = snapshot_run(db, 'READ COMMITTED')
    record('PG-05', 'Verrou consultatif pris en PREMIÈRE instruction d\'une transaction `REPEATABLE READ` (TD29) : quand l\'instantané est-il pris ?',
           'à la demande du verrou, avant l\'attente : après l\'attente, la transaction ne voit PAS ce que le détenteur précédent a validé pendant ce temps ; en `READ COMMITTED`, elle le voit',
           '`REPEATABLE READ` : %s ligne(s) visible(s) ; `READ COMMITTED` : %s' % (rr, rc), rr == 0 and rc == 1)


def e6_guarded_update(db):
    db.admin("UPDATE act SET status = 'SCHEDULED'")
    a, res = db.conn(), {}
    cur = a.execute("UPDATE act SET status = 'EXECUTING' WHERE id = 1 AND status = 'SCHEDULED'")
    first = cur.rowcount

    def other():
        b = db.conn()
        try:
            res['n'] = b.execute("UPDATE act SET status = 'EXECUTING' WHERE id = 1 AND status = 'SCHEDULED'").rowcount
            b.commit()
        finally:
            b.close()
    t = threading.Thread(target=other)
    t.start()
    time.sleep(0.3)
    a.commit()
    a.close()
    t.join(timeout=10)
    record('PG-06', '`UPDATE … WHERE état = ancien` : deux travailleurs réclament la même action (H4)', 'le premier obtient 1 ligne ; le second attend puis obtient 0 ligne',
           'premier : %s ligne ; second : %s ligne' % (first, res.get('n')), first == 1 and res.get('n') == 0)


def e7_unique_insert_waits(db):
    a, b = db.conn(), db.conn()
    try:
        a.execute("INSERT INTO parent VALUES (1, 10, 'SCHEDULED', 'same')")
        b.execute('SET lock_timeout = 400')
        waited = False
        try:
            b.execute("INSERT INTO parent VALUES (1, 11, 'SCHEDULED', 'same')")
        except errors.LockNotAvailable:
            waited = True
            b.rollback()
        a.commit()
        b.execute('SET lock_timeout = 0')
        after = None
        try:
            b.execute("INSERT INTO parent VALUES (1, 11, 'SCHEDULED', 'same')")
            after = 'insertion acceptée'
        except errors.UniqueViolation:
            after = 'violation d\'unicité'
            b.rollback()
    finally:
        a.close()
        b.close()
    record('PG-07', 'Un `INSERT` sur une clé unique déjà insérée par une transaction non validée (l\'`INSERT` est une acquisition, mode `I`)', 'le second attend la première ; après validation : violation d\'unicité (traduite en `REPLAY`)',
           'attente : %s ; après validation : %s' % ('oui' if waited else 'non', after), waited and after == 'violation d\'unicité')


def e8_skip_locked(db):
    a, b = db.conn(), db.conn()
    try:
        ra = a.execute('SELECT id FROM parent ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED').fetchone()[0]
        rb = b.execute('SELECT id FROM parent ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED').fetchone()[0]
    finally:
        a.rollback()
        b.rollback()
        a.close()
        b.close()
    record('PG-08', 'Réclamation concurrente par `FOR UPDATE SKIP LOCKED` (relais, `ExecutionWorker`)', 'deux travailleurs obtiennent deux lignes différentes', 'A : %s ; B : %s' % (ra, rb), ra != rb)


def e9_rls(db):
    db.admin("""
      DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN CREATE ROLE app_user NOLOGIN; END IF;
      END $$;
      DROP TABLE IF EXISTS t_rls, rc, rp CASCADE;
      CREATE TABLE t_rls (organization_id int NOT NULL, v int);
      INSERT INTO t_rls VALUES (1, 10), (2, 20);
      ALTER TABLE t_rls ENABLE ROW LEVEL SECURITY;
      CREATE POLICY p ON t_rls USING (organization_id = nullif(current_setting('app.organization_id', true), '')::int);
      GRANT USAGE ON SCHEMA public TO app_user;
      GRANT SELECT ON t_rls TO app_user;
      CREATE TABLE rp (organization_id int NOT NULL, id int PRIMARY KEY, UNIQUE (organization_id, id));
      INSERT INTO rp VALUES (1, 1);
      ALTER TABLE rp ENABLE ROW LEVEL SECURITY;
      CREATE POLICY none ON rp USING (false);
      CREATE TABLE rc (organization_id int NOT NULL, parent_id int NOT NULL, FOREIGN KEY (organization_id, parent_id) REFERENCES rp (organization_id, id));
      GRANT SELECT, INSERT ON rc TO app_user;
      GRANT SELECT ON rp TO app_user;
    """)
    c = db.conn()
    try:
        c.execute('SET ROLE app_user')
        none = c.execute('SELECT count(*) FROM t_rls').fetchone()[0]
        c.execute("SELECT set_config('app.organization_id', '1', true)")
        with_ctx = c.execute('SELECT count(*) FROM t_rls').fetchone()[0]
        c.commit()
        after = c.execute("SELECT coalesce(current_setting('app.organization_id', true), 'NULL')").fetchone()[0]
        after_rows = c.execute('SELECT count(*) FROM t_rls').fetchone()[0]
        c.commit()
    finally:
        c.close()
    record('PG-09', 'RLS échoue fermé et le réglage `set_config(..., true)` est local à la transaction (TD17, TD26)',
           'sans organisation posée : 0 ligne ; avec : 1 ligne ; après COMMIT le réglage est vide et 0 ligne à nouveau (compatible pooler en mode transaction)',
           'sans réglage : %s ; avec : %s ; après COMMIT : réglage « %s », %s ligne(s)' % (none, with_ctx, after or 'vide', after_rows),
           none == 0 and with_ctx == 1 and after_rows == 0)
    c = db.conn()
    try:
        c.execute('SET ROLE app_user')
        seen = c.execute('SELECT count(*) FROM rp').fetchone()[0]
        try:
            c.execute('INSERT INTO rc VALUES (1, 1)')
            fk = 'insertion acceptée'
        except Exception as e:  # noqa: BLE001
            fk = type(e).__name__
        c.rollback()
    finally:
        c.close()
    record('PG-10', 'Les vérifications de clé étrangère ne passent pas par RLS (TD17 : les FK composites gardent l\'intégrité même si RLS masque le parent)',
           'le parent est invisible (0 ligne) mais l\'insertion d\'un enfant valide est acceptée', 'parent visible : %s ligne(s) ; insertion de l\'enfant : %s' % (seen, fk), seen == 0 and fk == 'insertion acceptée')


def main():
    import pgserver
    d = tempfile.mkdtemp(prefix='verqia_pg_')
    srv = pgserver.get_server(d, cleanup_mode='stop')
    try:
        db = DB(srv.get_uri())
        version = db.admin('select version()')[0][0].split(',')[0]
        for fn in (e1_fk_insert_vs_lock_modes, e2_update_columns, e3_locker_conflicts, e4_deadlock, e6_guarded_update, e7_unique_insert_waits, e8_skip_locked, e5_advisory_snapshot, e9_rls):
            reset(db)
            fn(db)
    finally:
        srv.cleanup()
        shutil.rmtree(d, ignore_errors=True)
    RESULTS.sort(key=lambda r: r['id'])
    with open(os.path.join(HERE, 'pg_results.json'), 'w', encoding='utf-8') as f:
        json.dump({'server': version, 'experiments': RESULTS}, f, ensure_ascii=False, indent=1)
    for r in RESULTS:
        print(('OK ' if r['ok'] else 'KO '), r['id'], '|', r['observed'])
    sys.exit(0 if all(r['ok'] for r in RESULTS) else 1)


if __name__ == '__main__':
    main()
