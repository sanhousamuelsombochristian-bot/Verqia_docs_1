"""Vérifie que le coureur `application_runner/` reste un HARNAIS et ne devient pas une source de vérité (règles AR sur du code écrit à la main).

  R1  imports : bibliothèque standard, `verqia.kernel.*`, `verqia` (découverte des spécifications) et `application_runner.*` seulement ;
      ni Django, ni PostgreSQL, ni Redis, ni aucune bibliothèque tierce ; jamais le Domain, l'infrastructure, l'API ou les modèles d'un module
  R2  aucun nom de ressource de verrou ni d'opération du Lock Registry n'est écrit dans le coureur (l'ordre vient du registre généré)
  R3  le coureur et le double de verrous importent l'échelle générée `verqia.kernel.lock_registry` (la source existe et est utilisée)
  R4  aucun nom de cas d'usage du Command Registry n'est écrit dans le code du coureur (les cas d'usage viennent des spécifications générées)
  R5  aucune heure d'hôte : ni `datetime.now()`, `utcnow()`, `today()`, ni `time.time()` et voisins, ni `import time` : le temps métier vient du port `Clock` (TD23)

Usage : python architecture_registry/verify_runner.py [--root DIR]      (code de sortie 1 s'il existe une erreur)
"""
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import commands as K  # noqa: E402
import locks as L  # noqa: E402

STDLIB = set(sys.stdlib_module_names)
FORBIDDEN_TOP = {'django', 'psycopg', 'psycopg2', 'redis', 'sqlalchemy', 'celery', 'rest_framework'}
FORBIDDEN_LAYERS = {'domain', 'infrastructure', 'api', 'models'}
HOST_TIME_ATTRS = {'now', 'utcnow', 'today', 'time', 'time_ns', 'monotonic', 'perf_counter', 'localtime', 'gmtime'}
HOST_TIME_OWNERS = {'datetime', 'date', 'time'}
MUST_IMPORT_LADDER = ('application_runner/runner.py', 'application_runner/doubles/locks.py')


def sources(root):
    base = os.path.join(root, 'application_runner')
    for r, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('tests', '__pycache__')]
        for n in names:
            if n.endswith('.py'):
                p = os.path.join(r, n)
                with io.open(p, encoding='utf-8', newline='') as f:
                    yield os.path.relpath(p, root).replace(os.sep, '/'), f.read()


def forbidden_names():
    names = set(L.RESOURCES) | set(L.OPERATIONS)
    return names


def verify(root):
    errors = []
    banned_locks = forbidden_names()
    banned_use_cases = {c.name for c in K.COMMANDS}
    found = {}
    for rel, text in sources(root):
        found[rel] = text
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            errors.append('%s : syntaxe invalide (%s)' % (rel, e))
            continue
        imports_ladder = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split('.')[0]
                    if top == 'time':
                        errors.append("R5 : %s : `import time` : le temps métier vient du port `Clock` (TD23)" % rel)
                    if top in FORBIDDEN_TOP or (top not in STDLIB and top not in ('verqia', 'application_runner')):
                        errors.append('R1 : %s : import interdit `%s` (cadre logiciel ou bibliothèque tierce)' % (rel, a.name))
                    if top == 'verqia' and a.name != 'verqia':
                        errors.append('R1 : %s : `import %s` : utiliser `from verqia.kernel...`' % (rel, a.name))
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ''
                parts = name.split('.')
                top = parts[0]
                if top == 'time':
                    errors.append("R5 : %s : `from time import` : le temps métier vient du port `Clock` (TD23)" % rel)
                if node.level:
                    errors.append('R1 : %s : import relatif interdit' % rel)
                elif top in FORBIDDEN_TOP or (top not in STDLIB and top not in ('verqia', 'application_runner')):
                    errors.append('R1 : %s : import interdit `%s` (cadre logiciel ou bibliothèque tierce)' % (rel, name))
                elif top == 'verqia':
                    if len(parts) < 2 or parts[1] != 'kernel':
                        errors.append('R1 : %s : le coureur ne dépend que de `verqia.kernel` (importé : `%s`)' % (rel, name))
                    elif len(parts) > 2 and parts[2] in FORBIDDEN_LAYERS:
                        errors.append('R1 : %s : import de couche interdit `%s`' % (rel, name))
                    if name == 'verqia.kernel.lock_registry' or (name == 'verqia.kernel' and any(a.name == 'lock_registry' for a in node.names)):
                        imports_ladder = True
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in HOST_TIME_ATTRS:
                owner = node.func.value
                name = owner.id if isinstance(owner, ast.Name) else owner.attr if isinstance(owner, ast.Attribute) else ''
                if name in HOST_TIME_OWNERS:
                    errors.append("R5 : %s : heure d'hôte `%s.%s()` (ligne %d) : le temps métier vient du port `Clock` (TD23)" % (rel, name, node.func.attr, node.lineno))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in banned_locks:
                    errors.append('R2 : %s : le nom `%s` est un verrou ou une opération du Lock Registry : il ne s\'écrit pas dans le coureur (ligne %d)' % (rel, node.value, node.lineno))
                if node.value in banned_use_cases:
                    errors.append('R4 : %s : le nom `%s` est un cas d\'usage du Command Registry : il ne s\'écrit pas dans le coureur (ligne %d)' % (rel, node.value, node.lineno))
        if rel in MUST_IMPORT_LADDER and not imports_ladder:
            errors.append('R3 : %s : doit importer l\'échelle générée `verqia.kernel.lock_registry`' % rel)
    for rel in MUST_IMPORT_LADDER:
        if rel not in found:
            errors.append('R3 : fichier absent : %s' % rel)
    return errors, len(found)


def main():
    root = os.path.abspath(os.path.join(HERE, '..', '..', 'verqia-app'))
    if '--root' in sys.argv:
        root = sys.argv[sys.argv.index('--root') + 1]
    errors, n = verify(root)
    print('coureur : %d fichiers écrits à la main vérifiés · erreurs : %d' % (n, len(errors)))
    for e in errors:
        print('  -', e)
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
