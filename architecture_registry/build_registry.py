"""Vérifie les quatre registres d'architecture et génère ARCHITECTURE_REGISTRY_V1.md.

Usage : python architecture_registry/build_registry.py [--check]
Code de sortie 1 s'il existe une ERREUR (incohérence interne, ou écart avec un document figé sur un point vérifiable
mécaniquement). Les CONSTATS sont des écarts à décider (ils alimentent les amendements) et n'échouent pas la porte.
"""
import io
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(DOCS, 'test_matrix'))

import commands as K  # noqa: E402
import locks as L  # noqa: E402
import modules as M  # noqa: E402
import events as EV  # noqa: E402
import universe  # noqa: E402

PORTS = {k: v[0] for k, v in M.PORT_REGISTRY.items()}
# Exceptions C12 : FERMÉES et NOMINATIVES. Aucune formule du type « et opérations similaires ».
C12_NAMES = {'AllocatePayment', 'ReverseAllocation', 'ReversePayment', 'NormalizeImportBatch', 'ApplySettlement'}
# Convention de nommage (revue 3). Chaque préfixe a un sens vérifié par la porte.
NAMING = {
    'Provision': 'implémentation d\'une ProvisioningStep',
    'Create/Add/Update/Change': 'commande métier, verbe aligné sur l\'événement émis',
    'Start': 'démarrage d\'un processus',
    'Complete': 'achèvement d\'un processus',
    'Resume': 'reprise par balayage',
    'Read': 'service de lecture / port reader',
    'Notify': 'handler de notification',
}
VERB_EVENT = {'Create': 'CREATED', 'Add': 'ADDED', 'Update': 'UPDATED', 'Change': 'CHANGED'}
# Exception nominative et FERMÉE (B8) à la convention `Complete*` : `CompleteTask` est un command `USER` (pas un
# achèvement de processus interne), nom fixé par ENGINE_CONTRACTS_V1.md §EC-11 / STATE_MACHINES_V1.md §8 (C6). La
# convention `Complete*` = system/job n'a que deux précédents (`CompleteProvisioning`, `CompleteImportRelease`), tous
# deux des processus internes multi-étapes : elle n'a jamais été pensée pour ce cas. Ne pas étendre cette liste sans
# la même vérification de source qu'ici.
COMPLETE_TASK_EXCEPTION = {'CompleteTask'}
RETRY = '10 s · 1 min · 5 min · 30 min · 2 h, puis DEAD'
errors, findings = [], []

# Journal des amendements du Module Registry depuis le gel V1 (2026-09-18). Toute modification des registres s'y inscrit.
AMENDMENTS = [
    ('A1', '2026-09-19', "`PORT_REGISTRY` : les 17 ports publics (12 du noyau + `ProvisioningStep`, `FactProvider`, `ApprovalTargetReader`, `NotificationSender`, `JobRunner`)", 'ajout de données ; nécessaire à la propriété P3 (Module Contracts) ; aucune entrée existante modifiée', 'implicitement, avec Module Contracts V1'),
    ('A2', '2026-09-19', "dépendances `imports → risk, priority, cashflow` et `automation → cashflow` (émission d'une demande `REQUEST` : classe canonique chez le moteur destinataire)", 'donnée : `deps` du Module Registry (constat §8, option 1) ; TD10 intact : dépendance vers `contracts`, jamais vers l\'implémentation', 'oui, 2026-09-19'),
    ('A3', '2026-09-19', "le générateur compte l'émission d'un événement d'un autre module comme dépendance requise", 'outil (vérification) ; aucune donnée', 'oui, avec A2'),
    ('A4', '2026-09-19', "`events.OutboxPublisher` : champ `txn` `une` → `trois : réclamer par bail ; chaque handler dans sa transaction ; poser publié`", 'donnée : texte de transaction, aligné sur TD33 (frozen) ; aucune écriture, aucun verrou, aucun événement modifié', 'à valider avec Application Contract V1'),
]


def err(m):
    errors.append(m)


def find(m):
    findings.append(m)


# ------------------------------------------------------------------ catalogue d'événements (Invariants §10.3)
def load_catalogue():
    inv = universe.rd('INVARIANTS_V1.md')
    cat = universe.section(inv, '### 10.3', '\n---\n')
    events, category = [], None
    for line in cat.split('\n'):
        if line.startswith('**'):
            category = line.strip('* ').split('*')[0].split(' ')[0]
            continue
        if not line.startswith('| `'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        prefix = None
        for t in re.findall(r'`(_?[A-Z][A-Z0-9_]+)`', cells[0]):
            name = prefix + t if t.startswith('_') else t
            if not t.startswith('_'):
                prefix = t.rsplit('_', 1)[0]
            events.append((name, category, cells[1]))
    return events


CATALOGUE = load_catalogue()
EVT = {n: (c, a) for n, c, a in CATALOGUE}
CMD = {(c.module, c.name): c for c in K.COMMANDS}
BY_NAME = defaultdict(list)
for c in K.COMMANDS:
    BY_NAME[c.name].append(c)


def event_owner(e):
    if e in M.PRODUCER_OVERRIDE:
        return M.PRODUCER_OVERRIDE[e]
    if e not in EVT:
        return None
    cat, agg = EVT[e]
    return M.AGGREGATE_OWNER.get(agg)


# ------------------------------------------------------------------ 1. modules et tables
def check_modules():
    names = list(M.MODULES)
    for n, d in M.MODULES.items():
        for x in d['deps']:
            if x not in M.MODULES:
                err('module %s : dépendance inconnue %s' % (n, x))
    # cycle des dépendances déclarées
    g = {n: set(d['deps']) - M.DRIVERS for n, d in M.MODULES.items() if n not in M.DRIVERS}
    state = {}

    def dfs(n, path):
        state[n] = 1
        for m in g.get(n, ()):
            if state.get(m) == 1:
                err('cycle de dépendances déclarées : %s' % ' → '.join(path + [n, m]))
            elif m not in state:
                dfs(m, path + [n])
        state[n] = 2
    for n in g:
        if n not in state:
            dfs(n, [])
    ct = universe.rd('DATA_CONTRACT_V1.md')
    tables = re.findall(r'^### \d+\.\d+ `(\w+)`', ct, re.M)
    owner = defaultdict(list)
    for n, d in M.MODULES.items():
        for t in d['owns']:
            owner[t].append(n)
    for t in tables:
        if len(owner[t]) != 1:
            err('table %s : %d propriétaire(s) (%s)' % (t, len(owner[t]), owner[t]))
    for t in owner:
        if t not in tables:
            err('table %s attribuée mais absente du contrat' % t)
    return tables


# ------------------------------------------------------------------ 2. commandes
def resolve_call(c, target):
    own = target.startswith('own:')
    target = target[4:] if own else target
    mod, name = target.split('.', 1)
    if target in PORTS:
        return ('port', mod, name, own)
    if (mod, name) in CMD:
        return (CMD[(mod, name)].kind, mod, name, own)
    if mod in M.MODULES and name in M.MODULES[mod]['queries']:
        return ('query', mod, name, own)
    return None


def check_name(c):
    n = c.name
    step = 'organizations.ProvisioningStep' in c.implements
    if n.startswith('Provision') != step:
        err('nommage : %s.%s : le préfixe `Provision` est réservé aux implémentations de ProvisioningStep (et inversement)' % (c.module, n))
    if n.startswith('Complete') and c.kind not in ('system', 'job') and n not in COMPLETE_TASK_EXCEPTION:
        err('nommage : %s.%s : `Complete*` désigne l\'achèvement d\'un processus (système ou travail)' % (c.module, n))
    if n.startswith('Resume') and c.kind not in ('job', 'handler'):
        err('nommage : %s.%s : `Resume*` désigne une reprise par balayage (travail)' % (c.module, n))
    if n.startswith('Start') and c.kind not in ('system', 'handler'):
        err('nommage : %s.%s : `Start*` désigne le démarrage d\'un processus' % (c.module, n))
    if n.startswith('Read') and not any(p.endswith('Reader') for p in c.implements):
        err('nommage : %s.%s : `Read*` implémente un port `*Reader`' % (c.module, n))
    if n.startswith('Notify') and c.kind != 'handler':
        err('nommage : %s.%s : `Notify*` désigne un handler de notification' % (c.module, n))
    if c.src.startswith('NOM FIGÉ') and c.kind == 'command' and c.emits:
        for verb, suffix in VERB_EVENT.items():
            if n.startswith(verb) and not any(e.endswith(suffix) for e in c.emits):
                err('nommage : %s.%s : le verbe `%s` doit s\'aligner sur un événement `*_%s` (émis : %s)' % (c.module, n, verb, suffix, ', '.join(c.emits)))


def check_commands():
    seen = set()
    for c in K.COMMANDS:
        if (c.module, c.name) in seen:
            err('commande dupliquée : %s.%s' % (c.module, c.name))
        seen.add((c.module, c.name))
        if c.module not in M.MODULES:
            err('%s.%s : module inconnu' % (c.module, c.name))
        if c.lock and c.lock not in L.OPERATIONS:
            err('%s.%s : opération de verrou inconnue %s' % (c.module, c.name, c.lock))
        for w in c.writes:
            if w not in K.STATES:
                err('%s.%s : état inconnu %s' % (c.module, c.name, w))
        for e in c.subscribes:
            if e not in EVT:
                err('%s.%s : abonnement à un événement inconnu %s' % (c.module, c.name, e))
        for e in c.emits:
            if e not in EVT:
                pass  # traité par check_contract_events
        for t in c.calls:
            if resolve_call(c, t) is None:
                err('%s.%s : appel inconnu %s' % (c.module, c.name, t))
        for p in c.implements:
            if p not in PORTS:
                err('%s.%s : port inconnu %s' % (c.module, c.name, p))
        check_name(c)
        if c.c12 and c.name not in C12_NAMES:
            err('%s.%s : drapeau C12 hors des exceptions nommées' % (c.module, c.name))
    for op, (mod, seq, flags, src) in L.OPERATIONS.items():
        for r, mode in seq:
            if r not in L.RESOURCES or mode not in L.MODES:
                err('opération %s : ressource ou mode invalide (%s, %s)' % (op, r, mode))


# ------------------------------------------------------------------ 3. propriété des écritures
def check_write_ownership():
    writers = defaultdict(list)
    for c in K.COMMANDS:
        for w in c.writes:
            owner = K.STATES[w][0]
            writers[w].append(c)
            if owner != c.module and not c.c12:
                err('écriture hors propriétaire : %s.%s écrit %s (propriétaire %s) sans exception C12' % (c.module, c.name, w, owner))
    for k, (owner, nature, _) in K.STATES.items():
        if not writers[k]:
            err('état sans écrivain : %s' % k)
    return writers


# ------------------------------------------------------------------ 4. événements
def check_events():
    prod, cons = defaultdict(set), defaultdict(list)
    for c in K.COMMANDS:
        for e in c.emits:
            prod[e].add(c.module)
        for e in c.subscribes:
            cons[e].append('%s.%s' % (c.module, c.name))
    for e, (cat, agg) in EVT.items():
        if not prod[e]:
            err('événement sans producteur : %s' % e)
        if cat != 'REQUEST':
            own = event_owner(e)
            if own is None:
                err('événement %s : agrégat %s sans module propriétaire' % (e, agg))
            elif prod[e] - {own}:
                err('événement %s produit par %s (propriétaire %s)' % (e, sorted(prod[e]), own))
        else:
            if len(cons[e]) != 1:
                err('événement REQUEST %s : %d destinataire(s) (attendu : 1)' % (e, len(cons[e])))
    for e in EVT:
        if EVT[e][0] == 'REQUEST':
            continue
        if not cons[e]:
            find_no_consumer.append(e)
            cls = EV.NO_SUBSCRIBER.get(e)
            if cls is None:
                err('événement sans abonné et sans classement : %s (A volontaire, B autre passe, C oublié)' % e)
            elif cls[0] == 'C':
                err('événement sans abonné classé C (oublié) : %s' % e)
    for e, (cls, why) in EV.NO_SUBSCRIBER.items():
        if e not in EVT:
            err('classement d\'un événement inconnu : %s' % e)
        elif cons.get(e):
            err('événement classé « sans abonné » mais abonné : %s' % e)
        if cls not in ('A', 'B', 'C') or not why:
            err('classement invalide pour %s' % e)
    return prod, cons


def check_contract_events():
    """Tout événement contractuel est dans le catalogue normatif, ou classé technique, ou en attente d'amendement."""
    ct = universe.rd('DATA_CONTRACT_V1.md')
    named = set()
    for line in ct.split('\n'):
        if 'Événements :' in line:
            part = line.split('Événements :', 1)[1]
            prefix = None
            for t in re.findall(r'`(_?[A-Z][A-Z0-9_]+)`', part):
                name = prefix + t if t.startswith('_') else t
                if not t.startswith('_'):
                    prefix = t.rsplit('_', 1)[0]
                named.add(name)
    for e in sorted(named):
        if e in EVT or e in EV.TECHNICAL_EVENTS:
            continue
        if e in EV.PENDING_CATALOGUE_ADDITIONS:
            find('événement contractuel absent du catalogue des Invariants §10.3 (amendement en attente) : %s' % e)
        else:
            err('événement contractuel absent du catalogue et non classé : %s' % e)
    emitted = {e for c in K.COMMANDS for e in c.emits}
    for e in sorted(emitted):
        if e not in EVT and e not in EV.PENDING_CATALOGUE_ADDITIONS and e not in EV.TECHNICAL_EVENTS:
            err('événement émis inconnu du catalogue : %s' % e)
    for e in EV.PENDING_CATALOGUE_ADDITIONS:
        if e in EVT:
            err('%s est déjà au catalogue : retirer de PENDING_CATALOGUE_ADDITIONS' % e)



find_no_consumer = []


# ------------------------------------------------------------------ 5. listes figées
def check_frozen_lists():
    rpc = universe.rd('RISK_PRIORITY_CASHFLOW_V1.md')
    sec = rpc[rpc.index('### 1.4'):rpc.index('Ajouts en gras')]

    def ev(t):
        return set(re.findall(r'`([A-Z]+_[A-Z_]+)`', t))
    r = ev(sec[sec.index('`risk_profiles`'):sec.index('`priority_items`')]) - {'RISK_RECALCULATION_REQUESTED'}
    p = ev(sec[sec.index('`priority_items`'):]) - {'PRIORITY_RECALCULATION_REQUESTED'}
    r -= {'RISK_RECALCULATION_REQUESTED'}
    if set(K.RISK_REFRESH) != r - {'risk_profiles'}:
        err('RISK_REFRESH ≠ document (%s | %s)' % (sorted(set(K.RISK_REFRESH) - r), sorted(r - set(K.RISK_REFRESH))))
    if set(K.PRIORITY_REFRESH) != p:
        err('PRIORITY_REFRESH ≠ document (%s | %s)' % (sorted(set(K.PRIORITY_REFRESH) - p), sorted(p - set(K.PRIORITY_REFRESH))))
    aut = universe.rd('AUTOMATION_ENGINE_V1.md')
    a = aut[aut.index('**Événements utilisables comme déclencheur (V1)**'):aut.index('- Les événements de catégorie `REQUEST`')]
    if set(K.AUTOMATION_TRIGGERS) != ev(a):
        err('AUTOMATION_TRIGGERS ≠ document (%s | %s)' % (sorted(set(K.AUTOMATION_TRIGGERS) - ev(a)), sorted(ev(a) - set(K.AUTOMATION_TRIGGERS))))
    col = universe.rd('COLLECTION_ENGINE_V1.md')
    s12 = col[col.index('## 12. Réactions aux événements'):col.index('**Événements produits**')]
    docev = set(re.findall(r'`([A-Z]+_[A-Z_]+)`', ' '.join(l.split('|')[1] for l in s12.split('\n') if l.startswith('| `'))))
    rows = [l for l in s12.split(chr(10)) if l.startswith('| `') and not l.split('|')[2].strip().strip('*').startswith('aucune')]
    docev = set(re.findall(r'`([A-Z]+_[A-Z_]+)`', ' '.join(l.split('|')[1] for l in rows)))
    mine = {e for c in K.COMMANDS if c.module == 'collection' for e in c.subscribes}
    if not docev <= mine:
        err('Collection §12 : événements du document non abonnés %s' % sorted(docev - mine))


# ------------------------------------------------------------------ 6. trois graphes : appel, événement, schéma
def graphs():
    call, event = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
    request_owner = {e: c.module for c in K.COMMANDS for e in c.subscribes if e in EVT and EVT[e][0] == 'REQUEST'}
    for c in K.COMMANDS:
        if c.module in M.DRIVERS:
            continue
        for e in c.emits:
            o = event_owner(e) or request_owner.get(e)
            if o and o != c.module:
                call[c.module][o].append('émet %s (classe canonique dans %s)' % (e, o))
        for t in c.calls:
            r = resolve_call(c, t)
            if r and r[1] != c.module:
                call[c.module][r[1]].append('appel %s' % t)
        for p in c.implements:
            if PORTS[p] != c.module:
                call[c.module][PORTS[p]].append('implémente %s' % p)
        for e in c.subscribes:
            o = event_owner(e)
            if o and o != c.module:
                event[c.module][o].append(e)
    for m in M.FACT_PROVIDERS:
        call[m]['rules'].append('fournisseur de faits')
    for m, d in M.MODULES.items():
        for r in d['reads']:
            t, q = r.split('.', 1)
            if t not in M.MODULES or q not in M.MODULES[t]['queries']:
                err('%s : lecture inconnue %s' % (m, r))
            elif t != m:
                call[m][t].append('lecture %s' % r)
    schema = {m: set(v) for m, v in M.SCHEMA_DEPS.items()}
    return call, event, schema


def find_cycle(g):
    state, out = {}, []

    def dfs(n, path):
        state[n] = 1
        for x in sorted(g.get(n, ())):
            if state.get(x) == 1:
                out.append(path + [n, x])
            elif x not in state:
                dfs(x, path + [n])
        state[n] = 2
    for n in sorted(g):
        if n not in state:
            dfs(n, [])
    return out


def levels(g):
    memo = {}

    def depth(n, seen=()):
        if n in memo:
            return memo[n]
        if n in seen:
            return 0
        memo[n] = 1 + max([depth(x, seen + (n,)) for x in g.get(n, ())] or [-1])
        return memo[n]
    for n in M.MODULES:
        depth(n)
    return memo


def check_dependencies():
    call, event, schema = graphs()
    cg = {m: set(v) for m, v in call.items()}
    eg = {m: set(v) for m, v in event.items()}
    for cyc in find_cycle(cg):
        err('cycle sur le graphe des APPELS (contrats synchrones) : %s' % ' → '.join(cyc))
    union = {m: cg.get(m, set()) | eg.get(m, set()) for m in set(cg) | set(eg)}
    for cyc in find_cycle(union):
        if not find_cycle(cg):
            find('cycle uniquement événementiel : %s (admis si `contracts.events` est une feuille : types seuls)' % ' → '.join(cyc))
    for cyc in find_cycle(schema):
        err('cycle sur les dépendances de SCHÉMA (migrations) : %s' % ' → '.join(cyc))
    for m, ts in schema.items():
        for t in ts | {m}:
            if t not in M.MODULES:
                err('schéma : module inconnu %s' % t)
    for m, ts in list(union.items()):
        if m in M.DRIVERS:
            continue
        declared = set(M.MODULES[m]['deps'])
        for t in sorted(ts):
            if t not in declared:
                why = (call.get(m, {}).get(t) or []) + (event.get(m, {}).get(t) or [])
                err('dépendance requise non déclarée : %s → %s (%s)' % (m, t, ', '.join(why[:3])))
    for m, d in M.MODULES.items():
        if m in M.DRIVERS or m == 'kernel':
            continue
        extra = set(d['deps']) - union.get(m, set()) - {'kernel', 'platform'}
        if extra:
            find('dépendance déclarée mais non requise par les registres : %s → %s' % (m, sorted(extra)))
    return call, event, schema


# ------------------------------------------------------------------ 7. verrous
def check_locks():
    order, cycle = L.derive()
    if cycle:
        err('cycle de verrous entre les opérations : %s' % cycle)
    ok, cyc = L.consistent(L.FROZEN_EC5)
    if not ok:
        err('la chaîne gelée EC5 est incompatible avec les opérations : %s' % cyc)
    canon, cycle2 = L.canonical()
    if cycle2:
        err('échelle canonique impossible : %s' % cycle2)
    ok2, cyc2 = L.consistent(L.FIRST_DRAFT_TD27)
    if not ok2:
        find('l\'ordre proposé au premier jet de TD27 est incompatible avec les opérations (cycle : %s)' % ', '.join(cyc2))
    # appels de même transaction entre modules : interdits hors des exceptions C12 nominatives
    for c in K.COMMANDS:
        if c.module in M.DRIVERS:
            for t in c.calls:
                if not t.startswith('own:') and resolve_call(c, t) and resolve_call(c, t)[0] not in ('query', 'port'):
                    err('%s.%s : un travail de composition n\'appelle que des cas d\'usage dans leur propre transaction (%s)' % (c.module, c.name, t))
            continue
        for t in c.calls:
            r = resolve_call(c, t)
            if r is None or r[0] in ('query', 'port') or r[3] or r[1] == c.module:
                continue
            if not c.c12:
                err('écriture inter-modules dans la même transaction sans exception C12 nominative : %s.%s → %s.%s (préfixer `own:` pour une transaction propre au module appelé)' % (c.module, c.name, r[1], r[2]))
    # une opération qui acquiert un verrou doit être enregistrée
    for c in K.COMMANDS:
        if c.lock is None and c.writes and c.kind not in ('service',) and c.module not in ('events', 'audit', 'platform'):
            find('commande qui écrit sans opération de verrou enregistrée : %s.%s' % (c.module, c.name))
    return canon


# ------------------------------------------------------------------ génération
def md_escape(s):
    return str(s).replace('|', '\\|')


def render(tables, prod, cons, req, canon, writers):
    o = []
    w = o.append
    w('# VERQIA — Architecture Registry V1.2\n')
    w('## Journal des amendements (depuis le gel V1 du 2026-09-18)\n')
    w('| # | Date | Objet | Nature | Validé |\n|---|---|---|---|---|')
    for a in AMENDMENTS:
        w('| %s | %s | %s | %s | %s |' % a)
    w('\nRien d\'autre n\'a changé dans les quatre registres depuis le gel.\n')
    w('Statut : **généré** par `architecture_registry/build_registry.py` à partir de `commands.py`, `modules.py`, `locks.py` et du catalogue d\'événements des Invariants. **Ne pas modifier à la main.** **V1 gelé** avec `TECHNICAL_ARCHITECTURE_V1.md` (2026-09-18) : toute modification passe par un amendement daté.\n')
    w('Ces quatre registres rendent l\'architecture **exécutable** : les tests d\'architecture (`AR-*`) sont générés depuis eux. Ordre de travail : registres → tests d\'architecture → structure Django → schéma PostgreSQL.\n')
    w('- **Erreurs** : %d · **Constats** (écarts à décider) : %d\n' % (len(errors), len(findings)))
    w('| Registre | Contenu | Éléments |\n|---|---|---:|')
    w('| Module | propriété, dépendances, requêtes | %d |' % len(M.MODULES))
    w('| Commande | cas d\'usage, handlers, travaux, services | %d |' % len(K.COMMANDS))
    w('| Événement | catalogue des Invariants, producteurs, consommateurs | %d |' % len(EVT))
    w('| Verrou | ressources, opérations, échelle dérivée | %d ressources · %d opérations |' % (len(L.RESOURCES), len(L.OPERATIONS)))
    w('')
    # -------- modules
    w('## 1. Module Registry\n')
    w('Chaque module déclare : **ce qu\'il possède**, **ce qu\'il écrit** (commandes), **ce qu\'il lit** (requêtes publiées), **ce qu\'il publie et consomme** (événements). Les colonnes commandes et événements sont dérivées du Command Registry.\n')
    w('| Module | Groupe | Couches | Possède | Requêtes publiées | Dépend de (contracts) |\n|---|---|---|---|---|---|')
    for n, d in M.MODULES.items():
        w('| `%s` | %s | %s | %s | %s | %s |' % (n, d['group'], d['layers'], ', '.join('`%s`' % t for t in d['owns']) or '—',
                                               ', '.join('`%s`' % q for q in d['queries']) or '—', ', '.join('`%s`' % x for x in d['deps']) or '—'))
    w('')
    w('### 1.1 Publication et consommation par module\n')
    w('| Module | Commandes et travaux | Événements produits | Événements consommés |\n|---|---|---|---|')
    for n in M.MODULES:
        cs = [c for c in K.COMMANDS if c.module == n]
        pe = sorted({e for c in cs for e in c.emits})
        ce = sorted({e for c in cs for e in c.subscribes})
        w('| `%s` | %s | %s | %s |' % (n, ', '.join(c.name for c in cs) or '—', ', '.join(pe) or '—', ', '.join(ce) or '—'))
    w('')
    w('### 1.2 Dépendances requises et raison (appels, lectures, ports, événements)\n')
    call, event, _schema = req
    w('| Module | Dépendances requises et raison |\n|---|---|')
    for m in M.MODULES:
        byt = defaultdict(list)
        for t, ws in call.get(m, {}).items():
            byt[t] += ws
        for t, ws in event.get(m, {}).items():
            byt[t] += ['événement %s' % e for e in ws]
        if byt:
            w('| `%s` | %s |' % (m, md_escape(' ; '.join('**%s** (%s)' % (t, ', '.join(ws[:3]) + (' …' if len(ws) > 3 else '')) for t, ws in sorted(byt.items())))))
    w('')
    # -------- commandes
    w('## 2. Command Registry\n')
    w('`src` : `EC-nn`, `SM`, `INV`… = figé dans un document ; **`NOM FIGÉ`** = nom créé par les registres et figé en revue ; `PROPOSED` = nom encore provisoire. `lock` renvoie au Lock Registry. `writes` : états écrits (§2.2). Un appel préfixé `own:` s\'exécute dans **sa propre transaction**.\n')
    w('| Module | Commande | Type | Source | Transaction | Verrou | Écrit | Émet | Idempotence | Appelle |\n|---|---|---|---|---|---|---|---|---|---|')
    for c in K.COMMANDS:
        w('| `%s` | **%s** | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            c.module, c.name, c.kind, '**PROPOSED**' if c.src.startswith('PROPOSED') else c.src, md_escape(c.txn) + (' · **C12**' if c.c12 else ''), c.lock or '—',
            md_escape(', '.join(c.writes) or '—'), md_escape(', '.join(c.emits) or '—'), md_escape(c.idem or '—'),
            md_escape(', '.join(c.calls + tuple('implémente ' + p for p in c.implements)) or '—')))
    w('')
    w('### 2.1 Handlers : abonnements\n')
    w('| Handler | Événements | Reçu | Reprise |\n|---|---|---|---|')
    for c in K.COMMANDS:
        if c.subscribes:
            w('| `%s.%s` | %s | `(event_id, handler_name)` | %s |' % (c.module, c.name, md_escape(', '.join(c.subscribes)), RETRY))
    w('')
    w('### 2.2 Propriété des écritures\n')
    w('**Règle.** Un état métier n\'est écrit que par les cas d\'usage **de son module propriétaire**, par la **fonction de transition du Domain**. Seules les opérations nommées de C12 franchissent un module. Aucun autre code ne peut assigner ces états (`invoice.outstanding_minor` est une colonne générée : elle ne peut littéralement pas être assignée).\n')
    w('| État | Propriétaire | Nature | Écrit par | Détail |\n|---|---|---|---|---|')
    for k, (own, nat, desc) in K.STATES.items():
        ws = writers.get(k, [])
        w('| `%s` | `%s` | %s | %s | %s |' % (k, own, nat, ', '.join('%s%s' % (c.name, ' (C12)' if c.module != own else '') for c in ws), md_escape(desc)))
    w('')
    # -------- événements
    w('## 3. Event Registry\n')
    w('Politique commune : un événement est **publiable** dès le `COMMIT` ; chaque handler a son **propre** reçu et sa **propre** reprise (`%s`) ; aucun handler ne suppose d\'ordre ; le schéma vit dans `schemas/<TYPE>.v1.json`.\n' % RETRY)
    w('| Événement | Catégorie | Agrégat | Producteur(s) | Consommateur(s) | Politique de reçu |\n|---|---|---|---|---|---|')
    for e, (cat, agg) in EVT.items():
        cs = cons.get(e, [])
        pol = 'un seul destinataire ; regroupement 2 s ; reçus `PROCESSED` + `SKIPPED`' if cat == 'REQUEST' else ('diffusé à tous les abonnés' + ('' if cs else ' (aucun abonné en V1)'))
        w('| `%s` | %s | %s | %s | %s | %s |' % (e, cat, agg, ', '.join('`%s`' % p for p in sorted(prod.get(e, []))) or '—', md_escape(', '.join('`%s`' % x for x in cs) or '—'), pol))
    w('')
    # -------- verrous
    w('## 4. Lock Registry\n')
    w('**L\'ordre est dérivé, pas décrété.** Chaque opération déclare la suite de ressources qu\'elle acquiert ; le générateur en tire un graphe de précédence, vérifie qu\'il est sans cycle, et produit l\'échelle. Une opération nouvelle qui contredirait l\'échelle fait échouer la porte.\n')
    w('Modes : `A` verrou consultatif de transaction (première instruction) · `K` clé d\'idempotence · `S` `FOR SHARE` · `U` `FOR NO KEY UPDATE` · `G` `UPDATE` gardé · `I` `INSERT` (clé unique, clé étrangère).\n')
    w('### 4.1 Échelle publiée (compatible avec la chaîne gelée EC5)\n')
    w("Règle : une transaction n'acquiert une ressource que d'un rang **supérieur** à celles qu'elle détient déjà ; à l'intérieur d'une ressource, par identifiant croissant.\n")
    w('| Rang | Ressource | Tables | Remarque |\n|---:|---|---|---|')
    for i, r in enumerate(canon):
        w('| %d | `%s` | %s | %s |' % ((i + 1) * 10, r, L.RESOURCES[r][0], L.RESOURCES[r][1] or '—'))
    w('')
    w('Chaîne gelée EC5 : `%s` → **compatible** avec toutes les opérations enregistrées.\n' % ' → '.join(L.FROZEN_EC5))
    w('### 4.2 Opérations enregistrées\n')
    w('| Opération | Module | Séquence d\'acquisition | Source |\n|---|---|---|---|')
    for name, (mod, seq, flags, src) in L.OPERATIONS.items():
        full = L.op_sequence(name)
        w('| **%s** | `%s` | %s | %s |' % (name, mod, ' → '.join('`%s`(%s)' % (r, m) for r, m in full), md_escape(src)))
    w('')
    w('### 4.3 Arêtes de précédence et opérations qui les imposent\n')
    w('| Avant | Après | Imposée par |\n|---|---|---|')
    for (a, b), ops in sorted(L.precedence_edges().items()):
        w('| `%s` | `%s` | %s |' % (a, b, ', '.join(sorted(set(ops)))))
    w('')
    # -------- constats
    render_graphs(w, req)
    render_names(w)
    render_pg(w)
    w('## 5. Constats (écarts à décider)\n')
    if errors:
        w('### Erreurs\n')
        for e in errors:
            w('- **ERREUR** : %s' % e)
        w('')
    w('### Constats\n')
    for f in sorted(set(findings)):
        w('- %s' % f)
    if find_no_consumer:
        w('- événements sans abonné déclaré en V1 (à confirmer : simple journal ou consommateur manquant) : %s' % ', '.join(sorted(find_no_consumer)))
    props = [c for c in K.COMMANDS if c.src.startswith('PROPOSED')]
    w('- commandes au nom **créé par les registres** (figé en revue, hors documents figés antérieurs) : %d sur %d : %s' % (len(props), len(K.COMMANDS), ', '.join('%s.%s' % (c.module, c.name) for c in props)))
    return '\n'.join(o) + '\n'


def run():
    """Exécute toutes les vérifications sur l'état COURANT des registres (les tests d'injection le modifient)."""
    global CMD
    errors.clear()
    findings.clear()
    find_no_consumer.clear()
    CMD = {(c.module, c.name): c for c in K.COMMANDS}
    tables = check_modules()
    check_commands()
    writers = check_write_ownership()
    prod, cons = check_events()
    check_contract_events()
    check_frozen_lists()
    req = check_dependencies()
    canon = check_locks()
    return tables, writers, prod, cons, req, canon


def render_graphs(w, graphs_result):
    call, event, schema = graphs_result
    w('## 5. Graphes de dépendances\n')
    w('Trois graphes **séparés**, parce qu\'une dépendance d\'événement n\'est pas une dépendance d\'appel : un module qui *écoute* un autre ne l\'*appelle* pas. Le graphe des **appels** doit être sans cycle ; le graphe de **schéma** aussi (ordre des migrations).\n')
    cg = {m: set(v) for m, v in call.items()}
    lv = levels(cg)
    w('### 5.1 Appels, lectures, ports et fournisseurs de faits (sans cycle)\n')
    w('| Niveau | Module | Appelle / lit / implémente |\n|---:|---|---|')
    for m in sorted(M.MODULES, key=lambda x: (lv.get(x, 0), x)):
        if m in M.DRIVERS:
            continue
        w('| %d | `%s` | %s |' % (lv.get(m, 0), m, md_escape(', '.join('`%s`' % t for t in sorted(call.get(m, {}))) or '—')))
    w('')
    w('### 5.2 Événements (qui écoute qui)\n')
    w('| Module | Écoute les événements de |\n|---|---|')
    for m in sorted(event):
        w('| `%s` | %s |' % (m, md_escape(', '.join('`%s` (%d)' % (t, len(v)) for t, v in sorted(event[m].items())))))
    w('')
    w('### 5.3 Schéma (ordre des migrations)\n')
    w('| Module | Références de clé étrangère vers |\n|---|---|')
    for m in sorted(schema):
        w('| `%s` | %s |' % (m, ', '.join('`%s`' % t for t in sorted(schema[m])) or '—'))
    w('')
    w('### 5.4 Événements sans abonné, classés\n')
    w('A volontaire · B autre passe · C oublié (interdit : la porte échoue).\n')
    w('| Événement | Classe | Raison |\n|---|---|---|')
    for e in sorted(EV.NO_SUBSCRIBER):
        c, why = EV.NO_SUBSCRIBER[e]
        w('| `%s` | %s | %s |' % (e, c, md_escape(why)))
    w('')


def render_names(w):
    props = [c for c in K.COMMANDS if c.src.startswith('NOM FIGÉ') or c.src.startswith('PROPOSED')]
    w('## 6. Noms de commandes\n')
    w("Le nom d'une commande fait partie du contrat. **Aucun nom provisoire n'entre dans la structure Django** : `build_registry.py --freeze` échoue tant qu'un nom est `PROPOSED`.\n")
    w('**Convention de nommage** (figée en revue) :\n')
    w('| Préfixe | Sens |\n|---|---|')
    for k, v in NAMING.items():
        w('| `%s*` | %s |' % (k, v))
    w('')
    w("L'unicité d'un nom n'est pas un invariant d'architecture : le couple `(module, nom)` identifie le composant (`ReadApprovalTarget` existe dans `collection` et dans `automation`).\n")
    w('| ID | Module | Nom | Type | Émet | Statut |\n|---|---|---|---|---|---|')
    for i, c in enumerate(sorted(props, key=lambda c: (c.module, c.name)), 1):
        w('| N%02d | `%s` | `%s` | %s | %s | %s |' % (i, c.module, c.name, c.kind, md_escape(', '.join(c.emits) or '—'), 'à figer' if c.src.startswith('PROPOSED') else '**figé**'))
    w('')


def render_pg(w):
    path = os.path.join(HERE, 'pg_results.json')
    w('## 7. Vérifications sur PostgreSQL réel (TA-12)\n')
    if not os.path.exists(path):
        w('Non exécutées : `python architecture_registry/pg_experiments.py` produit `pg_results.json`.\n')
        return
    import json
    r = json.load(io.open(path, encoding='utf-8'))
    w('Serveur : **%s**. Chaque ligne est une **expérience exécutée**, avec deux transactions concurrentes ; l\'attendu vient des décisions du document d\'architecture.\n' % r['server'])
    w('| # | Expérience | Attendu | Observé | Verdict |\n|---|---|---|---|---|')
    for e in r['experiments']:
        w('| %s | %s | %s | %s | %s |' % (e['id'], md_escape(e['title']), md_escape(e['expected']), md_escape(e['observed']), '✅' if e['ok'] else '❌'))
    w('')


def main():
    tables, writers, prod, cons, req, canon = run()
    text = render(tables, prod, cons, req, canon, writers)
    out = os.path.join(DOCS, 'ARCHITECTURE_REGISTRY_V1.md')
    io.open(out, 'w', encoding='utf-8').write(text)
    print('modules %d · commandes %d · événements %d · ressources de verrou %d · opérations %d' % (len(M.MODULES), len(K.COMMANDS), len(EVT), len(L.RESOURCES), len(L.OPERATIONS)))
    print('erreurs : %d · constats : %d' % (len(errors), len(set(findings))))
    for e in errors:
        print('  ERREUR', e)
    for f in sorted(set(findings)):
        print('  constat', f)
    if find_no_consumer:
        print('  sans abonné :', ', '.join(sorted(find_no_consumer)))
    print('écrit :', out)
    if '--freeze' in sys.argv:
        props = [c for c in K.COMMANDS if c.src.startswith('PROPOSED')]
        if errors:
            print('  GEL IMPOSSIBLE : %d erreur(s)' % len(errors))
            sys.exit(1)
        if props:
            print('  GEL IMPOSSIBLE : %d commandes au nom non figé' % len(props))
            sys.exit(2)
        print('  GEL POSSIBLE : 0 erreur, 0 nom provisoire')
    if '--check' in sys.argv and errors:
        sys.exit(1)


if __name__ == '__main__':
    main()
