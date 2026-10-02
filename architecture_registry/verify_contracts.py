"""Vérifie Registry ↔ Contracts : les contrats générés sont fidèles aux quatre registres gelés et respectent TD4, TD10, DR1.

Quatre propriétés (plus l'hygiène de code) :
  P1  chaque commande du registre a exactement un contrat public (classe de commande, ou abonnement de handler) ; rien en trop
  P2  chaque événement du catalogue a exactement une définition canonique, dans le module propriétaire, avec sa catégorie, son agrégat, son payload
  P3  chaque port public appartient à son module propriétaire ; aucun port ailleurs
  P4  aucun contrat ne dépend d'un module interdit par TD10 (dépendances déclarées) ni d'autre chose que `contracts` d'un autre module
  H   hygiène : bibliothèque standard + `verqia` seulement (pas de cadre logiciel), aucun comportement (niveau C), aucune dérive du générateur

Usage : python architecture_registry/verify_contracts.py [--root DIR]      (code de sortie 1 s'il existe une erreur)
"""
import ast
import dataclasses
import importlib
import io
import os
import re
import sys
import typing

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(DOCS, 'test_matrix'))

import build_registry as B  # noqa: E402
import commands as K  # noqa: E402
import events as EV  # noqa: E402
import gen_contracts as G  # noqa: E402
import modules as M  # noqa: E402
import universe  # noqa: E402

FORBIDDEN_NODES = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith, ast.Lambda, ast.Raise, ast.ListComp, ast.SetComp,
                   ast.DictComp, ast.GeneratorExp, ast.Assert, ast.Delete, ast.Global, ast.Nonlocal, ast.Await, ast.Yield, ast.YieldFrom)
if hasattr(ast, 'Match'):
    FORBIDDEN_NODES += (ast.Match,)
STDLIB = set(sys.stdlib_module_names)


def is_protocol_class(node):
    return any((isinstance(b, ast.Name) and b.id == 'Protocol') or (isinstance(b, ast.Attribute) and b.attr == 'Protocol') for b in node.bases)


def body_is_empty_stub(fn):
    for st in fn.body:
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue
        return False
    return True


def module_of_path(rel):
    parts = rel.split('/')
    return parts[1] if len(parts) > 1 else None


def check_hygiene(rel, text, errors):
    """Bibliothèque standard + verqia ; imports autorisés ; aucun comportement."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        errors.append('%s : syntaxe invalide (%s)' % (rel, e))
        return set()
    mod = module_of_path(rel)
    deps = set(M.MODULES.get(mod, {}).get('deps', [])) if mod else set()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split('.')[0]
                if top not in STDLIB and top != 'verqia':
                    errors.append('%s : import interdit `%s` (cadre logiciel ou bibliothèque tierce : DR1)' % (rel, a.name))
                if top == 'verqia':
                    errors.append('%s : `import verqia...` interdit, utiliser `from verqia.<module>.contracts...`' % rel)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ''
            top = name.split('.')[0]
            if node.level:
                errors.append('%s : import relatif interdit' % rel)
            elif top not in STDLIB and top != 'verqia':
                errors.append('%s : import interdit `%s` (cadre logiciel ou bibliothèque tierce : DR1)' % (rel, name))
            elif top == 'verqia':
                parts = name.split('.')
                if len(parts) < 2:
                    errors.append('%s : `from verqia import` interdit' % rel)
                    continue
                target = parts[1]
                if target == 'kernel':
                    continue
                if target not in M.MODULES:
                    errors.append('%s : module inconnu `%s`' % (rel, target))
                    continue
                if len(parts) < 3 or parts[2] != 'contracts':
                    errors.append('%s : un autre module ne s\'importe que par `contracts` (TD4) : `%s`' % (rel, name))
                if target != mod:
                    imported.add(target)
                    if target not in deps:
                        errors.append('%s : dépendance interdite `%s → %s` (TD10 : non déclarée au Module Registry)' % (rel, mod, target))
        elif isinstance(node, FORBIDDEN_NODES):
            errors.append('%s : comportement interdit (niveau C) : `%s` ligne %d' % (rel, type(node).__name__, getattr(node, 'lineno', 0)))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            errors.append('%s : fonction de module interdite `%s` (niveau C)' % (rel, node.name))
        elif isinstance(node, ast.ClassDef):
            for st in ast.walk(node):
                if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not is_protocol_class(node):
                        errors.append('%s : méthode dans `%s` hors d\'un Protocol (niveau C)' % (rel, node.name))
                    elif not body_is_empty_stub(st):
                        errors.append('%s : le port `%s.%s` a un corps : un port n\'est qu\'une signature' % (rel, node.name, st.name))
    return imported


def purge():
    for k in [k for k in sys.modules if k == 'verqia' or k.startswith('verqia.')]:
        del sys.modules[k]


def load_module(name):
    return importlib.import_module(name)


def defined_in(mod, base=None):
    out = {}
    for n, v in vars(mod).items():
        if isinstance(v, type) and v.__module__ == mod.__name__:
            if base is None or (issubclass(v, base) and v is not base):
                out[n] = v
    return out


def verify(root, check_drift=True):
    errors, findings, stats = [], [], {}
    B.run()
    files, gstats = G.generate()
    # ------------------------------------------------------------ fichiers présents et dérive
    actual = {}
    base = os.path.join(root, 'verqia')
    for r, _, names in os.walk(base):
        for n in names:
            if n.endswith('.py'):
                rel = os.path.relpath(os.path.join(r, n), root).replace(os.sep, '/')
                with io.open(os.path.join(r, n), encoding='utf-8', newline='') as f:
                    actual[rel] = f.read()
    if check_drift:
        for rel, text in files.items():
            if rel not in actual:
                errors.append('fichier attendu absent : %s' % rel)
            elif actual[rel] != text:
                errors.append('dérive : %s diffère du générateur (ne pas modifier à la main)' % rel)
        for rel in actual:
            if rel not in files and not G.is_handwritten(rel):
                errors.append('fichier en trop (aucun registre ne le demande) : %s' % rel)
    # ------------------------------------------------------------ hygiène + P4 (imports)
    for rel, text in actual.items():
        if rel in G.HANDWRITTEN or G.is_domain(rel):
            continue
        check_hygiene(rel, text, errors)
    # ------------------------------------------------------------ import réel des contrats
    purge()
    sys.path.insert(0, root)
    try:
        modules_loaded = {}
        for rel in sorted(actual):
            if rel.endswith('__init__.py') or rel in G.HANDWRITTEN or G.is_domain(rel):
                continue
            name = rel[:-3].replace('/', '.')
            try:
                modules_loaded[name] = load_module(name)
            except Exception as e:  # noqa: BLE001
                errors.append('import impossible : %s (%s: %s)' % (name, type(e).__name__, str(e)[:100]))
        try:
            from verqia.kernel import events as kev  # noqa: E402
            from verqia.kernel import types as kty  # noqa: E402
        except Exception as e:  # noqa: BLE001
            errors.append('le kernel ne s\'importe pas : les propriétés P1 à P3 ne peuvent pas être vérifiées (%s: %s)' % (type(e).__name__, str(e)[:80]))
            stats.update(files=len(actual), contract_files=len([r for r in actual if '/contracts/' in r]), commands=0, handlers=0, events=0, ports=0, queries=0, error_codes=0)
            return errors, findings, stats
        Event, HandlerSpec, Command, Query = kev.Event, kev.HandlerSpec, kty.Command, kty.Query
        # ------------------------------------------------------ P1 : commandes et handlers
        n_cmd = n_handler = 0
        for m in M.MODULES:
            if m in ('kernel', 'config'):
                continue
            regs = [c for c in K.COMMANDS if c.module == m and c.kind != 'handler']
            hands = [c for c in K.COMMANDS if c.module == m and c.kind == 'handler']
            cmod = modules_loaded.get('verqia.%s.contracts.commands' % m)
            emod = modules_loaded.get('verqia.%s.contracts.events' % m)
            classes = defined_in(cmod, Command) if cmod else {}
            if set(classes) != {c.name for c in regs}:
                errors.append('P1 %s : commandes du registre %s ≠ classes de contrat %s' % (m, sorted({c.name for c in regs}), sorted(classes)))
            for c in regs:
                k = classes.get(c.name)
                if not k:
                    continue
                n_cmd += 1
                exp = dict(MODULE=m, KIND=c.kind, SOURCE=c.src, LOCK=c.lock, WRITES=tuple(c.writes), EMITS=tuple(c.emits), CALLS=tuple(c.calls),
                           IMPLEMENTS=tuple(c.implements), IDEMPOTENCY=c.idem, TRANSACTION=c.txn, C12=c.c12)
                for a, v in exp.items():
                    if getattr(k, a, None) != v:
                        errors.append('P1 %s.%s : métadonnée `%s` ≠ registre (%r ≠ %r)' % (m, c.name, a, getattr(k, a, None), v))
            specs = {}
            if emod is not None and hasattr(emod, 'HANDLERS'):
                for h in emod.HANDLERS:
                    if h.name in specs:
                        errors.append('P1 %s : handler déclaré deux fois : %s' % (m, h.name))
                    specs[h.name] = h
            if set(specs) != {'%s.%s' % (m, c.name) for c in hands}:
                errors.append('P1 %s : handlers du registre %s ≠ abonnements de contrat %s' % (m, sorted(c.name for c in hands), sorted(specs)))
            for c in hands:
                h = specs.get('%s.%s' % (m, c.name))
                if not h:
                    continue
                n_handler += 1
                if {e.TYPE for e in h.subscribes} != set(c.subscribes):
                    errors.append('P1 %s.%s : abonnements du contrat ≠ registre' % (m, c.name))
                if tuple(h.emits) != tuple(c.emits) or tuple(h.writes) != tuple(c.writes) or h.lock != c.lock:
                    errors.append('P1 %s.%s : effets déclarés ≠ registre' % (m, c.name))
                if h.single_recipient != any(B.EVT[e][0] == 'REQUEST' for e in c.subscribes):
                    errors.append('P1 %s.%s : `single_recipient` incohérent avec la catégorie REQUEST' % (m, c.name))
        stats['commands'] = n_cmd
        stats['handlers'] = n_handler
        # ------------------------------------------------------ P2 : événements
        catalogue = G.load_catalogue_full()
        cons = {}
        for c in K.COMMANDS:
            for e in c.subscribes:
                cons.setdefault(e, []).append('%s.%s' % (c.module, c.name))
        seen = {}
        for name, mod in modules_loaded.items():
            if not name.endswith('.contracts.events'):
                continue
            for cn, cls in defined_in(mod, Event).items():
                t = cls.TYPE
                seen.setdefault(t, []).append((name.split('.')[1], cn, cls))
        expected = {ev['type']: ev for ev in catalogue}
        for t, defs in seen.items():
            if t not in expected:
                errors.append('P2 événement inconnu du catalogue : %s (%s)' % (t, defs[0][1]))
        for t, ev in expected.items():
            defs = seen.get(t, [])
            if len(defs) != 1:
                errors.append('P2 %s : %d définition(s) canonique(s) (attendu : 1)' % (t, len(defs)))
                continue
            mod, cn, cls = defs[0]
            owner = G.event_module(ev, cons)
            if mod != owner:
                errors.append('P2 %s : défini dans `%s`, propriétaire `%s`' % (t, mod, owner))
            if cn != G.camel(t):
                errors.append('P2 %s : nom de classe `%s` ≠ `%s`' % (t, cn, G.camel(t)))
            if cls.CATEGORY.value != ev['category']:
                errors.append('P2 %s : catégorie %s ≠ %s' % (t, cls.CATEGORY.value, ev['category']))
            if ev['category'] != 'REQUEST' and cls.AGGREGATE != ev['aggregate']:
                errors.append('P2 %s : agrégat %s ≠ %s' % (t, cls.AGGREGATE, ev['aggregate']))
            is_req_name = cn.endswith('Requested')
            if ev['category'] == 'REQUEST' and not is_req_name:
                errors.append('P2 %s : une demande (REQUEST) doit se nommer `…Requested` : `%s`' % (t, cn))
            if ev['category'] != 'REQUEST' and is_req_name and t not in EV.FACT_EVENTS_NAMED_REQUESTED:
                errors.append('P2 %s : le nom `%s` se lit comme une demande mais la catégorie est %s (exception à nommer dans FACT_EVENTS_NAMED_REQUESTED)' % (t, cn, ev['category']))
            fields = {f.name: f for f in dataclasses.fields(cls)}
            want = {n: opt for n, _, opt in ev['payload']}
            if set(fields) != set(want):
                errors.append('P2 %s : payload %s ≠ catalogue %s' % (t, sorted(fields), sorted(want)))
            else:
                for n, opt in want.items():
                    has_default = fields[n].default is not dataclasses.MISSING
                    if has_default != opt:
                        errors.append('P2 %s.%s : optionnel=%s ≠ catalogue (%s)' % (t, n, has_default, opt))
        stats['events'] = len(expected)
        # ------------------------------------------------------ P3 : ports
        stats['ports'] = 0
        for name, mod in modules_loaded.items():
            if not name.endswith('.contracts.ports') and name != 'verqia.kernel.ports':
                continue
            owner = 'kernel' if name == 'verqia.kernel.ports' else name.split('.')[1]
            defined = {n for n, v in vars(mod).items() if isinstance(v, type) and v.__module__ == name and getattr(v, '_is_protocol', False)}
            want = {k.split('.', 1)[1] for k, v in M.PORT_REGISTRY.items() if v[0] == owner}
            if defined != want:
                errors.append('P3 %s : ports définis %s ≠ ports que le registre lui attribue %s' % (owner, sorted(defined), sorted(want)))
            stats['ports'] += len(defined)
        for k, (owner, _) in M.PORT_REGISTRY.items():
            if owner not in M.MODULES:
                errors.append('P3 %s : propriétaire inconnu' % k)
        for name, mod in modules_loaded.items():
            if name.endswith('.ports') or name.endswith('.contracts.ports'):
                continue
            for n, v in vars(mod).items():
                if isinstance(v, type) and v.__module__ == name and getattr(v, '_is_protocol', False):
                    errors.append('P3 %s.%s : un port hors d\'un fichier `ports.py`' % (name, n))
        # ------------------------------------------------------ requêtes
        n_q = 0
        for m, d in M.MODULES.items():
            qmod = modules_loaded.get('verqia.%s.contracts.queries' % m)
            classes = defined_in(qmod, Query) if qmod else {}
            if set(classes) != set(d['queries']):
                errors.append('Q %s : requêtes du registre %s ≠ contrats %s' % (m, sorted(d['queries']), sorted(classes)))
            n_q += len(classes)
        stats['queries'] = n_q
        # ------------------------------------------------------ erreurs et exceptions
        eng = universe.rd('ENGINE_CONTRACTS_V1.md')
        annex = set(re.findall(r'^\| `([A-Z_]+)` \| \w+ \| [0-9/]+ \| (?:oui|non) \|', eng[eng.index('## Annexe A'):], re.M))
        kerr = modules_loaded['verqia.kernel.errors']
        if set(kerr.ERROR_CATALOGUE) != annex:
            errors.append('E catalogue d\'erreurs du kernel ≠ Annexe A (%s)' % sorted(set(kerr.ERROR_CATALOGUE) ^ annex)[:5])
        stats['error_codes'] = len(annex)
        rt = modules_loaded['verqia.rules.contracts.types']
        if [m.value for m in rt.ExceptionCode] != G.exception_codes() or len(rt.ExceptionCode) != 13:
            errors.append('E exceptions du Rule Engine ≠ contrat')
    finally:
        sys.path.remove(root)
        purge()
    # ------------------------------------------------------------ constat : émetteurs de REQUEST hors du module propriétaire
    home = {ev['type']: G.event_module(ev, {e: v for e, v in cons.items()}) for ev in catalogue}
    need = {}
    for c in K.COMMANDS:
        if c.module in M.DRIVERS:
            continue
        for e in c.emits:
            h = home.get(e)
            if h and h != c.module and h not in M.MODULES[c.module]['deps']:
                need.setdefault((c.module, h), set()).add(e)
    for (m, h), evs in sorted(need.items()):
        findings.append('constat pour l\'étape Application : `%s` émet %s, dont la classe canonique est dans `%s`, hors de ses dépendances déclarées (TD10)' % (m, ', '.join(sorted(evs)), h))
    stats['files'] = len(actual)
    stats['contract_files'] = len([r for r in actual if '/contracts/' in r])
    return errors, findings, stats


def main():
    root = G.DEFAULT_OUT
    if '--root' in sys.argv:
        root = sys.argv[sys.argv.index('--root') + 1]
    errors, findings, stats = verify(root)
    print('fichiers : %(files)d (dont %(contract_files)d de contrats) · commandes %(commands)d · handlers %(handlers)d · événements %(events)d · '
          'ports %(ports)d · requêtes %(queries)d · codes d\'erreur %(error_codes)d' % stats)
    print('erreurs : %d · constats : %d' % (len(errors), len(findings)))
    for e in errors:
        print('  ERREUR', e)
    for f in findings:
        print('  ', f)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
