"""Vérifie Registry ↔ Application : chaque cas d'usage du registre a exactement un `UseCaseSpec` fidèle aux quatre registres gelés.

Propriétés :
  A1  une spécification par entrée du registre, aucune en trop
  A2  fidélité : nature, transaction, idempotence, événements, écritures, abonnements, lectures et appels sont recalculés depuis le registre
  A3  verrous : la séquence d'un cas d'usage est celle du Lock Registry, en rang STRICTEMENT croissant sur l'échelle générée
  A4  organisation : régime cohérent avec la nature ; exceptions nominatives et fermées (relais d'outbox, gestionnaire de partitions, création d'organisation)
  A5  erreurs : tout code cité existe à l'Annexe A ; classes valides ; aucune erreur inventée
  A6  audit : une commande PUBLIQUE a toujours un audit ; toute autre entrée n'en produit un que si elle est nommée (D3) ; un audit conditionnel est motivé
  A7  atomicité : écritures, événements, audit, clé d'idempotence, reçu : une seule unité par transaction ; aucun effet extérieur listé
  A8  inter-modules (AP-08) : cible existante ; dépendance déclarée ; sens compatible avec le graphe (jamais de retour) ; `own:` seulement vers l'état que la cible possède
  A9  issues (AP-12) : `REPLAY` seulement pour une commande ; les issues d'un handler sont celles de son reçu ; issues autorisées par nature
  A10 entrée (AP-11) : commande publique / étape de provisioning / interne / réaction / travail : la distinction est dérivée et vérifiée
  A11 phases (AP-10, AP-13) : tout cas d'usage à appels `own:` ou à transactions multiples déclare ses phases ordonnées ; CLAIM → EFFECT → FINALIZE ;
      un effet extérieur n'est dans aucune transaction
  A12 idempotence (AP-14) : une commande qui insère `K` a une portée typée `ORGANIZATION` ; exception nominative `ACTOR` pour `CreateOrganization`, liée au régime `NEW` ; aucune autre n'en a
  A13 portée de transaction (AP-15) : `TENANT` ; `SYSTEM` pour les régimes `RELAY` et `NONE` ; `NEW` pour le régime `NEW` ; jamais choisie par le cas d'usage ; `SCOPE_OF_TENANT` conforme
  H2  donnée seulement (AP-09) : un `specs.py` n'est fait que de constantes, tuples, énumérés et de deux constructeurs (`UseCaseSpec`, `Phase`) ; aucun appel, lambda,
      condition, boucle, compréhension, f-string ou opérateur : liste blanche de nœuds, pas liste noire
  H   hygiène : les fichiers générés n'ont aucune fonction, aucun contrôle de flux, aucune importation hors bibliothèque standard et `verqia.kernel`

Usage : python architecture_registry/verify_application.py [--root DIR]
"""
import ast
import importlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_registry as B  # noqa: E402
import commands as K  # noqa: E402
import application_freeze as FZ  # noqa: E402
import gen_application as GA  # noqa: E402
import gen_contracts as G  # noqa: E402
import locks as L  # noqa: E402
import modules as M  # noqa: E402
import verify_contracts as VC  # noqa: E402

# Énoncés INDÉPENDANTS du générateur : si le générateur dérive, ces tables le contredisent.
TENANT_EXCEPTIONS = {('events', 'OutboxPublisher'): 'RELAY', ('platform', 'PartitionManager'): 'NONE', ('organizations', 'CreateOrganization'): 'NEW'}
ERROR_CLASSES = {'VALIDATION', 'BUSINESS_RULE', 'NOT_FOUND', 'FORBIDDEN', 'CONFLICT', 'RATE_LIMITED', 'TRANSIENT', 'INTERNAL'}
AUDIT_NOMINATIVE = {'AnonymizeCustomer', 'AnonymizeUser', 'AnonymizeAuditLogs', 'AuthorizeOverride', 'ReplayDeadEvent', 'CreateCollectionAction', 'ExecuteDueAction'}
OUTCOMES_DEFAULT = {'command': {'OK', 'REPLAY'}, 'handler': {'PROCESSED', 'SKIPPED', 'RETRYING', 'DEAD'}, 'job': {'OK', 'SKIPPED'},
                    'worker': {'OK', 'RETRYING', 'DEFERRED'}, 'system': {'OK', 'SKIPPED'}, 'service': set()}
OUTCOMES_ALLOWED = {'command': {'OK', 'REPLAY', 'SKIPPED', 'DEFERRED'}, 'handler': {'PROCESSED', 'SKIPPED', 'RETRYING', 'DEAD'}, 'job': {'OK', 'SKIPPED'},
                    'worker': {'OK', 'RETRYING', 'DEFERRED'}, 'system': {'OK', 'SKIPPED'}, 'service': set()}
OUTCOME_EXTRA_NAMES = {'CreateCollectionAction', 'CreateManualAction'}
ENTRY_OF_KIND = {'command': 'PUBLIC', 'handler': 'REACTION', 'job': 'BACKGROUND', 'worker': 'BACKGROUND', 'system': 'INTERNAL', 'service': 'INTERNAL'}
SINGLE_TXN = {'une', 'par organisation', 'une par pas', 'une par tranche', 'une par facture', 'une, hors envoi'}
GUARD_WORDS = ('idempot', 'garde', 'claim', 'bail')
AMENDED_EDGES = (('imports', 'risk'), ('imports', 'priority'), ('imports', 'cashflow'), ('automation', 'cashflow'))
ACTOR_SCOPED = {('organizations', 'CreateOrganization')}   # énoncé indépendant du générateur
DATA_NODES = (ast.Module, ast.Expr, ast.ImportFrom, ast.alias, ast.AnnAssign, ast.Name, ast.Load, ast.Store, ast.Subscript, ast.Tuple, ast.Constant, ast.Attribute,
              ast.keyword)
DATA_CALLS = {'UseCaseSpec', 'Phase'}
PHASE_EFFECTS_OK = {'événements', 'audit', "clé d'idempotence", 'reçu'}


def keyed(c):
    """Commande qui insère la clé de requête `K` (TD32) : énoncé indépendant du générateur."""
    return c.kind == 'command' and bool(c.lock) and any(mode == 'K' for _, mode in L.op_sequence(c.lock))


SYSTEM_TENANT_MODES = {'RELAY', 'NONE'}


def scope_of(mode):
    """Portée attendue d'un régime : énoncé indépendant du générateur."""
    return 'SYSTEM' if mode in SYSTEM_TENANT_MODES else ('NEW' if mode == 'NEW' else 'TENANT')


def closure(m, seen=None):
    seen = seen if seen is not None else set()
    for d in M.MODULES[m]['deps']:
        if d not in seen and d not in M.DRIVERS:
            seen.add(d)
            closure(d, seen)
    return seen


def check_data_only(rel, text, errors):
    """AP-09 : LISTE BLANCHE de nœuds. Tout ce qui n'est pas une constante, un tuple, un énuméré ou un constructeur de donnée est refusé : un appel déguisé,
    une lambda, une condition, une compréhension, une f-string ne passent pas."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        errors.append('H2 : %s : syntaxe invalide (%s)' % (rel, e))
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name not in DATA_CALLS:
                errors.append('H2 : %s : appel `%s(...)` (ligne %d) : une spécification est de la donnée (AP-09)' % (rel, name or ast.dump(node.func)[:30], node.lineno))
        elif isinstance(node, ast.Expr):
            if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                errors.append('H2 : %s : expression `%s` (ligne %d) : seule la docstring est permise (AP-09)' % (rel, type(node.value).__name__, node.lineno))
        elif not isinstance(node, DATA_NODES):
            errors.append('H2 : %s : nœud `%s` (ligne %d) : ni fonction, ni contrôle de flux, ni calcul dans une spécification (AP-09)' % (rel, type(node).__name__, getattr(node, 'lineno', 0)))


def load_specs(root):
    VC.purge()
    sys.path.insert(0, root)
    specs = {}
    for m in M.MODULES:
        name = 'verqia.%s.application.specs' % m
        path = os.path.join(root, 'verqia', m, 'application', 'specs.py')
        if not os.path.exists(path):
            continue
        mod = importlib.import_module(name)
        for s in mod.USE_CASES:
            specs.setdefault((s.module, s.name), []).append(s)
    return specs


def registry_calls(c):
    """Appels inter-modules et lectures recalculés depuis le registre (sans passer par le générateur)."""
    reads, cross = set(), []
    for t in c.calls:
        r = B.resolve_call(c, t)
        if r is None:
            continue
        if r[0] == 'query':
            reads.add('%s.%s' % (r[1], r[2]))
        elif r[1] != c.module or r[0] == 'port':
            cross.append(t)
    cross += ['implémente:' + p for p in c.implements]
    return tuple(sorted(reads)), tuple(cross)


def check_phases(who, c, s, errors):
    own = [t for t in c.calls if t.startswith('own:')]
    required = bool(own) or c.txn not in SINGLE_TXN
    ph = list(s.phases)
    if required and not ph:
        errors.append('A11 : %s : appels `own:` ou transactions multiples sans phases déclarées (TD58)' % who)
        return
    if not required and ph:
        errors.append("A11 : %s : phases déclarées pour un cas d'usage à une seule transaction" % who)
        return
    if not ph:
        return
    if [p.order for p in ph] != list(range(1, len(ph) + 1)):
        errors.append('A11 : %s : ordre des phases non consécutif' % who)
    roles = [p.role.value for p in ph]
    covered = []
    for p in ph:
        for t in p.calls:
            if 'own:' + t not in c.calls:
                errors.append("A11 : %s : la phase %d appelle `%s` qui n'est pas un appel `own:` du registre" % (who, p.order, t))
            covered.append(t)
        if p.role.value == 'EXTERNAL' and (p.calls or p.effects):
            errors.append("A11 : %s : la phase EXTERNAL %d n'écrit rien et n'appelle rien : elle est hors transaction" % (who, p.order))
        if p.calls and p.effects:
            errors.append("A11 : %s : la phase %d appelle un propriétaire ET écrit : l'état du propriétaire est écrit dans sa transaction (TD55, TD58)" % (who, p.order))
        for e in p.effects:
            if e not in c.writes and e not in PHASE_EFFECTS_OK:
                errors.append("A11 : %s : la phase %d écrit `%s` qui n'est pas une écriture du registre" % (who, p.order, e))
            if e == 'audit' and s.audit.value == 'NONE':
                errors.append("A11 : %s : la phase %d écrit un audit que le cas d'usage ne produit pas" % (who, p.order))
            if e == 'événements' and not c.emits:
                errors.append("A11 : %s : la phase %d émet des événements que le registre n'attribue pas au cas d'usage" % (who, p.order))
            if e == "clé d'idempotence" and not keyed(c):
                errors.append("A11 : %s : la phase %d écrit une clé d'idempotence que le cas d'usage n'a pas" % (who, p.order))
        if p.role.value == 'EFFECT' and not p.modules:
            errors.append("A11 : %s : la phase EFFECT %d n'a pas de module propriétaire" % (who, p.order))
        if '*' in p.modules and (c.module, c.name) != ('events', 'OutboxPublisher'):
            errors.append("A11 : %s : `*` (tous les handlers abonnés) n'existe que pour le relais d'outbox" % who)
        target_modules = set()
        for t in p.calls:
            if t == 'organizations.ProvisioningStep':
                target_modules |= {x.module for x in K.COMMANDS if 'organizations.ProvisioningStep' in x.implements}
            else:
                target_modules.add(t.split('.', 1)[0])
        if p.calls and set(p.modules) != target_modules:
            errors.append('A11 : %s : la phase %d déclare les modules %s, les cibles appartiennent à %s' % (who, p.order, sorted(p.modules), sorted(target_modules)))
    for t in own:
        if covered.count(t[4:]) != 1:
            errors.append("A11 : %s : l'appel `%s` doit figurer dans exactement une phase (%d)" % (who, t, covered.count(t[4:])))
    union = {e for p in ph for e in p.effects}
    delegated = set()  # états écrits par le propriétaire appelé (`own:`), dans SA transaction
    for t in own:
        r = B.resolve_call(c, t)
        if r and r[0] not in ('port', 'query'):
            delegated |= {w for x in K.COMMANDS if (x.module, x.name) == (r[1], r[2]) for w in x.writes}
    for w in c.writes:
        if w not in union and w not in delegated:
            errors.append("A11 : %s : l'écriture %s n'appartient à aucune phase" % (who, w))
    if c.emits and 'événements' not in union:
        errors.append("A11 : %s : les événements émis n'appartiennent à aucune phase" % who)
    if keyed(c) and (not ph or "clé d'idempotence" not in ph[0].effects):
        errors.append("A11 : %s : la clé d'idempotence est la première écriture : elle appartient à la première phase (TD32)" % who)
    if s.audit.value != 'NONE' and 'audit' not in union:
        errors.append("A11 : %s : l'audit n'appartient à aucune phase" % who)
    if c.kind == 'worker' and 'CLAIM' not in roles:
        errors.append('A11 : %s : un travailleur réclame son travail (bail, RUNNING) : phase CLAIM obligatoire (TD31)' % who)
    # AP-10 : Claim → Effect → Finalize
    if 'CLAIM' in roles or 'EXTERNAL' in roles:
        if roles.count('CLAIM') != 1 or roles[0] != 'CLAIM':
            errors.append('A11 : %s : AP-10 : une réclamation (CLAIM) unique doit ouvrir les phases' % who)
        if roles.count('FINALIZE') != 1 or roles[-1] != 'FINALIZE':
            errors.append('A11 : %s : AP-10 : une finalisation (FINALIZE) unique doit clore les phases' % who)
        if not any(r in ('EFFECT', 'EXTERNAL') for r in roles[1:-1]):
            errors.append("A11 : %s : AP-10 : aucune phase d'effet entre CLAIM et FINALIZE" % who)
        if roles.count('CLAIM') == 1 and roles.count('FINALIZE') == 1 and ph[0].modules != ph[-1].modules:
            errors.append('A11 : %s : AP-10 : CLAIM et FINALIZE doivent appartenir au même module (la finalisation ne vaut que pour sa réclamation)' % who)
        if not any(w in (c.idem or '') for w in GUARD_WORDS):
            errors.append("A11 : %s : AP-10 : un effet après réclamation doit être idempotent et gardé (idempotence du registre : « %s »)" % (who, c.idem))
    elif 'FINALIZE' in roles and roles[-1] != 'FINALIZE':
        errors.append('A11 : %s : FINALIZE doit être la dernière phase' % who)


def verify(root):
    errors = []
    B.run()
    reg = {(c.module, c.name): c for c in K.COMMANDS}
    G.generate()  # met à jour l'état du registre
    for rel in ('verqia/kernel/application.py', 'verqia/kernel/lock_registry.py'):
        if not os.path.exists(os.path.join(root, rel)):
            errors.append('fichier absent : %s' % rel)
    if errors:
        return errors, {}
    # ------------------------------------------------------------ dérive du générateur
    expected = GA.add_files({})
    for rel, text in expected.items():
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            errors.append('fichier attendu absent : %s' % rel)
            continue
        with io.open(p, encoding='utf-8', newline='') as f:
            if f.read() != text:
                errors.append('dérive : %s diffère du générateur' % rel)
    # ------------------------------------------------------------ hygiène des fichiers RÉELS (pas du texte attendu)
    hygiene = []
    for rel in expected:
        p = os.path.join(root, rel)
        if os.path.exists(p) and (rel.endswith('/specs.py') or rel.endswith('application.py') or rel.endswith('lock_registry.py')):
            with io.open(p, encoding='utf-8', newline='') as f:
                text = f.read()
            VC.check_hygiene(rel, text, hygiene)
            if rel.endswith('/application/specs.py'):
                check_data_only(rel, text, hygiene)
    errors += hygiene
    if hygiene:  # un fichier qui n'est plus de la donnée ne doit pas être importé
        return errors, {}
    specs = load_specs(root)
    from verqia.kernel.application import SCOPE_OF_TENANT
    for mode, scope in SCOPE_OF_TENANT.items():
        if scope.value != scope_of(mode.value):
            errors.append('A13 : `SCOPE_OF_TENANT[%s]` = %s : incompatible avec la règle (SYSTEM pour RELAY et NONE, NEW pour NEW, TENANT sinon)' % (mode.value, scope.value))
    # ------------------------------------------------------------ A1
    for k in reg:
        n = len(specs.get(k, []))
        if n != 1:
            errors.append('A1 : %s.%s a %d spécifications (attendu 1)' % (k[0], k[1], n))
    for k in specs:
        if k not in reg:
            errors.append('A1 : spécification sans entrée de registre : %s.%s' % k)
    from verqia.kernel import errors as KE
    from verqia.kernel import lock_registry as LR
    catalogue = set(KE.ERROR_CATALOGUE)
    # ------------------------------------------------------------ échelle générée = Lock Registry
    canon, cycle = L.canonical()
    if cycle or tuple(canon) != tuple(LR.LADDER):
        errors.append("A3 : `lock_registry.LADDER` ne correspond pas à l'échelle dérivée du Lock Registry")
    for op in L.OPERATIONS:
        if tuple(L.op_sequence(op)) != tuple(LR.OPERATIONS.get(op, ())):
            errors.append('A3 : opération de verrous `%s` : séquence différente du Lock Registry' % op)
    if set(LR.OPERATIONS) != set(L.OPERATIONS):
        errors.append('A3 : opérations de verrous différentes du Lock Registry')
    # ------------------------------------------------------------ A8 : arêtes de l'amendement A2 présentes avant génération
    for a, b in AMENDED_EDGES:
        if b not in M.MODULES[a]['deps']:
            errors.append('A8 : arête `%s → %s` (amendement A2) absente du Module Registry' % (a, b))
    # ------------------------------------------------------------ propriétés par cas d'usage
    stats = {'specs': 0, 'locked': 0, 'audit_required': 0, 'audit_conditional': 0, 'errors_named': 0, 'phased': 0, 'entries': {}}
    for k, lst in specs.items():
        c = reg.get(k)
        if not c or len(lst) != 1:
            continue
        s = lst[0]
        stats['specs'] += 1
        stats['entries'][s.entry.value] = stats['entries'].get(s.entry.value, 0) + 1
        who = '%s.%s' % k
        # A2
        if s.module != c.module or s.name != c.name:
            errors.append('A2 : %s : module ou nom différents du registre' % who)
        if s.kind != c.kind:
            errors.append('A2 : %s : nature %s ≠ registre %s' % (who, s.kind, c.kind))
        if s.transaction != c.txn:
            errors.append('A2 : %s : transaction différente du registre' % who)
        if s.idempotency != (c.idem or '—'):
            errors.append('A2 : %s : idempotence différente du registre' % who)
        if tuple(s.emits) != tuple(c.emits):
            errors.append('A2 : %s : événements émis différents du registre' % who)
        if tuple(s.domain) != tuple(c.writes):
            errors.append('A2 : %s : écritures Domain différentes du registre' % who)
        reads, cross = registry_calls(c)
        if tuple(s.reads) != reads:
            errors.append('A2 : %s : lectures différentes du registre' % who)
        if tuple(s.cross_module) != cross:
            errors.append('A2 : %s : appels inter-modules différents du registre' % who)
        if c.kind == 'handler':
            if s.command is not None:
                errors.append("A2 : %s : un handler n'est pas une commande" % who)
            if s.input != 'événements : ' + ', '.join(c.subscribes):
                errors.append('A2 : %s : abonnements différents du registre' % who)
        elif s.command != c.name:
            errors.append("A2 : %s : `command` doit valoir le nom du cas d'usage" % who)
        # A3
        if s.lock_operation != c.lock:
            errors.append('A3 : %s : opération de verrous différente du registre' % who)
        if c.lock:
            stats['locked'] += 1
            seq = tuple(L.op_sequence(c.lock))
            if tuple(s.lock_sequence) != seq:
                errors.append('A3 : %s : séquence de verrous différente du Lock Registry' % who)
            ranks = []
            for res, _ in s.lock_sequence:
                if res not in LR.RANK:
                    errors.append("A3 : %s : ressource `%s` absente de l'échelle" % (who, res))
                else:
                    ranks.append(LR.RANK[res])
            if any(b <= a for a, b in zip(ranks, ranks[1:])):
                errors.append("A3 : %s : la séquence n'est pas en rang strictement croissant (%s)" % (who, [r for r, _ in s.lock_sequence]))
        elif s.lock_sequence:
            errors.append('A3 : %s : séquence de verrous sans opération' % who)
        # A4
        want = TENANT_EXCEPTIONS.get(k) or ('EVENT' if c.kind == 'handler' else ('ENUMERATOR' if c.kind == 'job' else 'REQUIRED'))
        if s.tenant.value != want:
            errors.append("A4 : %s : régime d'organisation %s (attendu %s)" % (who, s.tenant.value, want))
        # A5
        for code in s.errors:
            if code not in catalogue:
                errors.append("A5 : %s : code d'erreur inconnu `%s` (Annexe A)" % (who, code))
            else:
                stats['errors_named'] += 1
        for cl in s.error_classes:
            if cl not in ERROR_CLASSES:
                errors.append("A5 : %s : classe d'erreur inconnue `%s`" % (who, cl))
        if c.kind != 'handler' and not s.error_classes:
            errors.append("A5 : %s : aucune classe d'erreur" % who)
        # A6
        if s.entry.value == 'PUBLIC' and s.audit.value == 'NONE':
            errors.append('A6 : %s : une commande publique a toujours un audit (D3)' % who)
        if s.entry.value != 'PUBLIC' and s.audit.value != 'NONE' and c.name not in AUDIT_NOMINATIVE:
            errors.append("A6 : %s : entrée %s : pas d'audit direct, hors liste nominative D3 (historique et événements suffisent)" % (who, s.entry.value))
        if s.audit.value == 'REQUIRED':
            stats['audit_required'] += 1
        if s.audit.value == 'CONDITIONAL':
            stats['audit_conditional'] += 1
            if not s.audit_basis:
                errors.append('A6 : %s : audit conditionnel sans motif' % who)
        # A7
        eff = set(s.atomic_effects)
        for w in c.writes:
            if w not in eff:
                errors.append("A7 : %s : écriture %s hors de l'unité atomique" % (who, w))
        if c.emits and 'événements' not in eff:
            errors.append("A7 : %s : événements émis hors de l'unité atomique" % who)
        if s.audit.value == 'REQUIRED' and 'audit' not in eff:
            errors.append("A7 : %s : audit requis hors de l'unité atomique" % who)
        if keyed(c) and "clé d'idempotence" not in eff:
            errors.append("A7 : %s : clé d'idempotence hors de l'unité atomique" % who)
        if c.kind == 'handler' and 'reçu' not in eff:
            errors.append("A7 : %s : reçu hors de l'unité atomique" % who)
        for e in eff:
            if e not in c.writes and e not in ('événements', 'audit', "clé d'idempotence", 'reçu'):
                errors.append("A7 : %s : effet inattendu `%s` dans l'unité atomique" % (who, e))
        # A8
        mod_deps = set(M.MODULES[c.module]['deps'])
        for t in s.cross_module:
            if t.startswith('implémente:'):
                continue
            r = B.resolve_call(c, t)
            if r is None:
                errors.append("A8 : %s : cible d'appel inconnue `%s`" % (who, t))
                continue
            if c.module not in M.DRIVERS and r[1] != c.module:
                if r[1] not in mod_deps:
                    errors.append('A8 : %s : appel de %s : dépendance non déclarée (TD10)' % (who, t))
                if c.module in closure(r[1]):
                    errors.append('A8 : %s : appel de %s : sens contraire au graphe (%s dépend déjà de %s)' % (who, t, r[1], c.module))
        # A8 (5) : un `own:` (même module compris) vise un cas d'usage qui possède réellement l'état qu'il écrit
        for t in c.calls:
            if not t.startswith('own:'):
                continue
            r = B.resolve_call(c, t)
            if r is None:
                errors.append("A8 : %s : cible d'appel inconnue `%s`" % (who, t))
            elif r[0] not in ('command', 'service', 'system', 'job', 'worker', 'port'):
                errors.append("A8 : %s : `own:` sur une cible qui n'est pas un cas d'usage (%s)" % (who, t))
            elif r[0] != 'port':
                callee = reg[(r[1], r[2])]
                for w in callee.writes:
                    if K.STATES[w][0] != callee.module:
                        errors.append("A8 : %s : `own:%s.%s` écrit %s qui appartient à %s : la cible ne possède pas cet état" % (who, r[1], r[2], w, K.STATES[w][0]))
                if callee.kind in ('command', 'service', 'system') and not callee.writes:
                    errors.append("A8 : %s : `own:%s.%s` n'écrit aucun état : rien à posséder" % (who, r[1], r[2]))
        # A9
        outs = set(s.outcomes)
        if not OUTCOMES_DEFAULT[c.kind] <= outs:
            errors.append('A9 : %s : issues manquantes pour la nature %s : %s' % (who, c.kind, sorted(OUTCOMES_DEFAULT[c.kind] - outs)))
        bad = outs - OUTCOMES_ALLOWED[c.kind]
        if bad:
            errors.append('A9 : %s : issues %s interdites pour la nature %s (`REPLAY` : commandes seulement)' % (who, sorted(bad), c.kind))
        if outs - OUTCOMES_DEFAULT[c.kind] and c.name not in OUTCOME_EXTRA_NAMES:
            errors.append('A9 : %s : issues supplémentaires %s non autorisées par un contrat' % (who, sorted(outs - OUTCOMES_DEFAULT[c.kind])))
        if 'REPLAY' in outs and c.kind != 'command':
            errors.append("A9 : %s : `REPLAY` n'est pas une issue universelle" % who)
        # A10
        step = 'organizations.ProvisioningStep' in c.implements
        want_entry = 'PROVISIONING_STEP' if step else ENTRY_OF_KIND[c.kind]
        if s.entry.value != want_entry:
            errors.append('A10 : %s : entrée %s (attendu %s)' % (who, s.entry.value, want_entry))
        if step and (c.kind != 'service' or c.idem != '(organisation, étape)' or s.audit.value != 'NONE' or not c.lock or s.tenant.value != 'REQUIRED' or s.phases):
            errors.append('A10 : %s : une étape de provisioning est un service idempotent par (organisation, étape), sans audit direct, à verrou, dans sa propre transaction' % who)
        # A12
        want_scope = ('ACTOR' if k in ACTOR_SCOPED else 'ORGANIZATION') if keyed(c) else None
        got_scope = s.idempotency_scope.value if s.idempotency_scope is not None else None
        if got_scope != want_scope:
            errors.append('A12 : %s : portée d\'idempotence %s (attendu %s)' % (who, got_scope, want_scope))
        if any(m == 'K' for _, m in s.lock_sequence) and c.kind != 'command' and s.entry.value != 'INTERNAL':
            errors.append('A12 : %s : un cas d\'usage non-commande qui insère `K` est interne : il hérite de la clé de son appelant' % who)
        if (s.tenant.value == 'NEW') != (got_scope == 'ACTOR'):
            errors.append('A12 : %s : la portée `ACTOR` et le régime `NEW` vont ensemble (l\'organisation n\'existe pas encore) et seulement ensemble' % who)
        # A13
        want_tx = scope_of(s.tenant.value)
        if s.transaction_scope.value != want_tx:
            errors.append('A13 : %s : portée de transaction %s (attendu %s : elle se déduit du régime d\'organisation %s)' % (who, s.transaction_scope.value, want_tx, s.tenant.value))
        # A11
        check_phases(who, c, s, errors)
        if s.phases:
            stats['phased'] += 1
    return errors, stats


def main():
    root = os.path.abspath(os.path.join(HERE, '..', '..', 'verqia-app'))
    if '--root' in sys.argv:
        root = sys.argv[sys.argv.index('--root') + 1]
    errors, stats = verify(root)
    errors += FZ.check_freeze()
    if stats:
        print("cas d'usage : %d · avec verrous : %d · composés (phases) : %d · audit requis : %d · conditionnel : %d · codes d'erreur nommés : %d" %
              (stats['specs'], stats['locked'], stats['phased'], stats['audit_required'], stats['audit_conditional'], stats['errors_named']))
        print('entrées : ' + ', '.join('%s %d' % kv for kv in sorted(stats['entries'].items())))
    print('erreurs : %d' % len(errors))
    for e in errors:
        print('  -', e)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
