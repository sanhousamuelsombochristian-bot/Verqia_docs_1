"""Agrège les passes de mesure en tableaux comparables (durées, catégories, PostgreSQL, porte AP, veilles) et calcule les écarts."""
import glob
import json
import os
import statistics
import sys

OUT = sys.argv[1]
passes = sorted(os.path.basename(p)[:-len('_pass.json')] for p in glob.glob(os.path.join(OUT, '*_pass.json')))


def load(name, kind):
    with open(os.path.join(OUT, '%s_%s.json' % (name, kind)), encoding='utf-8') as f:
        return json.load(f)


P = {n: {'pass': load(n, 'pass'), 'suite': load(n, 'suite'), 'pg': load(n, 'pg'), 'gate': load(n, 'gate')} for n in passes}


def row(label, values, fmt='%8.1f'):
    return '| %-52s | ' % label + ' | '.join(fmt % v if isinstance(v, (int, float)) else '%8s' % v for v in values) + ' |'


def header(cols):
    return '| %-52s | ' % '' + ' | '.join('%8s' % c for c in cols) + ' |\n|' + '-' * 54 + '|' + '|'.join('-' * 10 for _ in cols) + '|'


def stats(values):
    return [statistics.mean(values), max(values) - min(values), (max(values) - min(values)) / statistics.mean(values) * 100]


cols = passes + ['moy.', 'écart', 'écart %']


def table(title, rows):
    print('\n### ' + title + '\n')
    print(header(cols))
    for label, values in rows:
        s = stats(values)
        print(row(label, values + [s[0], s[1], s[2]]))


# ---------------------------------------------------------------- niveau 1
print('## Niveau 1 : global\n')
print(header(passes))
print(row('durée totale de la passe (s)', [P[n]['pass']['wall'] for n in passes]))
print(row('  dont veille de la machine chevauchant la passe (s)', [P[n]['pass']['sleep_overlap_s'] for n in passes]))
print(row('  suite architecture_registry (s)', [P[n]['suite']['total']['wall'] for n in passes]))
print(row('  PostgreSQL diag (s)', [P[n]['pg']['phases']['total'] for n in passes]))
print(row('  porte AP diag (s)', [sum(v['wall'] for k, v in P[n]['gate']['phases'].items() if isinstance(v, dict)) for n in passes]))
print(row('tests exécutés', [P[n]['suite']['total']['tests'] for n in passes], '%8d'))
print(row('échecs + erreurs', [P[n]['suite']['total']['failures'] + P[n]['suite']['total']['errors'] for n in passes], '%8d'))
print(row('processus fils lancés par la suite (subprocess.run)', [sum(c['subprocess_n'] for c in P[n]['suite']['categories'].values()) for n in passes], '%8d'))
print(row('copies du dépôt par la suite (copytree)', [sum(c['copytree_n'] for c in P[n]['suite']['categories'].values()) for n in passes], '%8d'))
print(row('CPU du processus principal de la suite (s)', [P[n]['suite']['total']['cpu_main'] for n in passes]))
print('\nInstantané avant chaque passe : ' + '; '.join('%s : CPU %s %%, RAM libre %s Mo, %s processus python' % (
    n, P[n]['pass']['snapshot_before']['cpu_load_pct'], P[n]['pass']['snapshot_before']['ram_libre_mo'], P[n]['pass']['snapshot_before']['processus_python']) for n in passes))

# ---------------------------------------------------------------- niveau 2
cats = sorted({c for n in passes for c in P[n]['suite']['categories']})
table('Niveau 2 : suite par catégorie, durée murale cumulée (s)', [(c, [P[n]['suite']['categories'].get(c, {'wall': 0.0})['wall'] for n in passes]) for c in cats])
print('\nNombre de tests par catégorie (passe %s) : ' % passes[0] + ', '.join('%s %d' % (c, P[passes[0]]['suite']['categories'].get(c, {'tests': 0})['tests']) for c in cats))
mods = sorted({m for n in passes for m in P[n]['suite']['modules']})
table('Par module de test (s)', [(m, [P[n]['suite']['modules'].get(m, {'wall': 0.0})['wall'] for n in passes]) for m in mods])
print('\nTests par module : ' + ', '.join('%s %d' % (m, P[passes[0]]['suite']['modules'].get(m, {'tests': 0})['tests']) for m in mods))
table('Coût moyen d\'un test d\'injection (s) et de sa copie du dépôt (s)', [
    ('durée moyenne par test d\'injection', [P[n]['suite']['categories']['injection']['wall'] / max(1, P[n]['suite']['categories']['injection']['tests']) for n in passes]),
    ('dont copie du dépôt par test', [P[n]['suite']['categories']['injection']['copytree_s'] / max(1, P[n]['suite']['categories']['injection']['tests']) for n in passes])])

# les 10 tests les plus lents (passe A) et leur stabilité
rows = {}
for n in passes:
    for r in P[n]['suite']['rows']:
        rows.setdefault(r['id'], []).append(r['wall'])
slow = sorted(rows.items(), key=lambda kv: -statistics.mean(kv[1]))[:10]
print('\n### Les 10 tests les plus lents (durée par passe, s)\n')
for tid, v in slow:
    print('- `%s` : %s' % (tid, ' / '.join('%.1f' % x for x in v)))

# ---------------------------------------------------------------- niveau 3
phases = list(P[passes[0]]['pg']['phases'].keys())
table('Niveau 3 : PostgreSQL par phase (s, sauf indication)', [(p, [P[n]['pg']['phases'][p] for n in passes]) for p in phases])
exps = list(P[passes[0]]['pg']['experiments'].keys())
table('Expériences PostgreSQL (s)', [(e, [P[n]['pg']['experiments'][e] for n in passes]) for e in exps])
print('\nPostgreSQL : %s ; expériences exécutées : %s ; toutes confirmées : %s' % (P[passes[0]]['pg']['server'], P[passes[0]]['pg']['experiments_run'], all(P[n]['pg']['results_ok'] for n in passes)))

# ---------------------------------------------------------------- porte AP / mutations
gate_phases = [k for k, v in P[passes[0]]['gate']['phases'].items() if isinstance(v, dict)]
table('Porte AP par étape (s)', [(p, [P[n]['gate']['phases'][p]['wall'] for n in passes]) for p in gate_phases])
table('40 mutations : ventilation (s)', [
    ('copie du dépôt', [P[n]['gate']['phases']['40 mutations (copie + application + tests)']['copy'] for n in passes]),
    ('processus de tests (unittest en sous-processus)', [P[n]['gate']['phases']['40 mutations (copie + application + tests)']['subprocess'] for n in passes])])
print('\nMutations tuées : ' + ' / '.join('%d sur %d' % (P[n]['gate']['phases']['mutations_killed'], P[n]['gate']['phases']['mutations_total']) for n in passes))

# ---------------------------------------------------------------- écarts
print('\n## Écarts entre passes\n')
walls = [P[n]['suite']['total']['wall'] for n in passes]
print('suite : min %.1f s, max %.1f s, écart %.1f s (%.1f %% de la moyenne)' % (min(walls), max(walls), max(walls) - min(walls), (max(walls) - min(walls)) / statistics.mean(walls) * 100))
