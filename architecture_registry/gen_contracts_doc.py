"""Rendu de MODULE_CONTRACTS_V1.md à partir des contrats générés et des registres."""
import gen_contracts as G
import commands as K
import modules as M


# Amendements de la surface C10 depuis sa mise en candidat (2026-09-19) : chacun est provoqué par un besoin démontré du coureur Application.
KERNEL_AMENDMENTS = [
    ('K1', '2026-09-20', "`TransactionManager.atomic(ctx, isolation, scope)` avec `TransactionScope` `TENANT` / `SYSTEM` ; `SystemContext` (sans organisation) ; `CallContext.organization_id` reste obligatoire ; la portée est fixée par le contrat Application (`transaction_scope`), jamais par l'appelant",
     "coureur : `OutboxPublisher` (`RELAY`) et `PartitionManager` (`NONE`) n'étaient pas exprimables (`tenant_unscoped_pending`)", 'oui, 2026-09-20'),
    ('K2', '2026-09-20', "`IdempotencyStore.begin/complete(scope, scope_id, key, route, ...)` avec `IdempotencyScope` `ORGANIZATION` / `ACTOR` ; jamais un `organization_id` nul par convention",
     "coureur : `CreateOrganization` s'exécute avant l'existence de l'organisation (AP-14)", 'oui, 2026-09-20'),
    ('K3', '2026-09-20', "`TransactionScope.NEW` (troisième régime, distinct de `TENANT` et `SYSTEM`) ; `CreationContext` sans champ d'organisation ; `TenantContext.bind_new(organization_id)` : liaison typée, unique, réservée à l'unité `NEW`, d'un identifiant venant d'être généré ; une fois liée, l'organisation ne change plus dans l'unité de travail",
     "coureur, étape 11 : `CreateOrganization` recevait un `CallContext` dont l'organisation était ignorée puis remplacée (`organization_id` à valeur ambiguë)", 'oui, 2026-09-20'),
]


def render_doc(files):
    o = []
    w = o.append
    catalogue = G.load_catalogue_full()
    cons = {}
    for c in K.COMMANDS:
        for e in c.subscribes:
            cons.setdefault(e, []).append('%s.%s' % (c.module, c.name))
    home = {ev['type']: G.event_module(ev, cons) for ev in catalogue}
    n_cmd = len([c for c in K.COMMANDS if c.kind != 'handler'])
    n_hand = len([c for c in K.COMMANDS if c.kind == 'handler'])
    n_files = len([f for f in files if '/contracts/' in f or f.startswith('verqia/kernel/')])

    w('# VERQIA — Module Contracts V1.1\n')
    w("Statut : **V1.1 — VALIDÉ le 2026-09-19** : C1 à C9 validées ; **C10 gelée comme surface candidate de Kernel V1** (toute modification ultérieure doit être provoquée par un besoin démontré d'un cas d'usage Application et faire l'objet d'un amendement explicite) ; option 1 du §8 confirmée. Généré depuis `ARCHITECTURE_REGISTRY_V1.1` (gel V1 + amendements A1 à A3 tracés dans son journal). **Généré** par `architecture_registry/gen_contracts.py` depuis les quatre registres gelés (`ARCHITECTURE_REGISTRY_V1.md`) ; **ne pas modifier à la main** : `verify_contracts.py` détecte toute dérive. Code généré : `verqia-app/verqia/` (à côté de `verqia-docs/`).\n")
    w("Objet : donner à chacun des 22 modules sa **surface publique** (`contracts/`, TD4), framework-free, avant tout cas d'usage, tout Domain et tout modèle PostgreSQL. **Aucun `models.py`, aucune migration, aucun endpoint, aucun travailleur métier** à cette étape.\n")

    w('## 1. Trois niveaux, jamais mélangés\n')
    w('| Niveau | Contenu | Dans cette étape |\n|---|---|---|')
    w("| **A — structurel** | une classe par commande, événement, requête et port ; métadonnées issues du registre (module, type, source, verrou, écritures, événements émis, idempotence, transaction) | **oui** |")
    w("| **B — types contractuels** | identifiants typés (`OrganizationId`…), `MoneyMinor`, `Currency`, `CallContext`, `DomainError` et le catalogue des 104 codes ; types **explicitement figés** par les contrats d'interface (EC-04, EC-05, EC-10, EC-11, EC-12, EC-13) | **oui**, seulement ce qui est figé |")
    w("| **C — comportement** | invariants, transitions, validations, forme des résultats | **non** : étape Application + Domain |\n")

    w('## 2. Chiffres\n')
    w('| | |\n|---|---:|')
    w('| Unités (dont `kernel` et `config`) | %d |' % len(M.MODULES))
    w('| Fichiers de contrats générés (noyau inclus) | %d |' % n_files)
    w('| Contrats de commande (hors handlers) | %d |' % n_cmd)
    w('| Abonnements de handler (`HandlerSpec`) | %d |' % n_hand)
    w('| Événements canoniques (une définition chacun) | %d |' % len(catalogue))
    w('| Requêtes publiées | %d |' % sum(len(d['queries']) for d in M.MODULES.values()))
    w('| Ports publics (noyau inclus) | %d |' % len(M.PORT_REGISTRY))
    w("| Commandes à charge utile figée par un contrat d'interface | %d (+ la requête `rules.Evaluate`) |" % len(G.PAYLOADS))
    w('')

    w('## 3. Ce que contient chaque module\n')
    w("Seuls les fichiers **nécessaires** existent : un module sans commande n'a pas de `commands.py`.\n")
    w('| Module | Groupe | Fichiers de `contracts/` | Commandes | Handlers | Événements produits | Requêtes | Ports |\n|---|---|---|---:|---:|---:|---:|---:|')
    for m, d in M.MODULES.items():
        if m == 'kernel':
            w('| `kernel` | %s | types, context, errors, events, ports (à plat : le noyau est son propre contrat) | — | — | — | — | %d |' % (
                d['group'], len([k for k, v in M.PORT_REGISTRY.items() if v[0] == 'kernel'])))
            continue
        fl = sorted(f.split('/')[-1][:-3] for f in files if f.startswith('verqia/%s/contracts/' % m) and not f.endswith('__init__.py'))
        w('| `%s` | %s | %s | %d | %d | %d | %d | %d |' % (
            m, d['group'], ', '.join(fl) or '*aucun : racine de composition*',
            len([c for c in K.COMMANDS if c.module == m and c.kind != 'handler']),
            len([c for c in K.COMMANDS if c.module == m and c.kind == 'handler']),
            len([e for e in catalogue if home[e['type']] == m]), len(d['queries']),
            len([k for k, v in M.PORT_REGISTRY.items() if v[0] == m])))
    w('')

    w('## 4. Décisions (C1 à C10), validées le 2026-09-19\n')
    w('| # | Décision | Pourquoi |\n|---|---|---|')
    w("| **C1** | **L'organisation n'est jamais un champ de commande** : elle vient du `CallContext`. | K14 : « quelle organisation ? » a pour propriétaire le `TransactionManager` et RLS ; un champ dupliquerait l'information et ouvrirait une divergence (commande pour A, contexte de B). |")
    w("| **C2** | Un **handler** n'a pas de classe de commande : son contrat est un `HandlerSpec` (nom stable, événements écoutés, effets), déclaré dans `events.py` du module (TD13). | Un handler est appelé par le relais, jamais par un autre module ; sa surface publique est ce qu'il écoute. |")
    w("| **C3** | Tout autre élément du registre (commande, service, système, travail, travailleur) a **une classe de commande** et une seule. | Propriété P1 : « chaque commande du registre possède exactement un contrat public ». |")
    w("| **C4** | Les événements sont des **faits passés** (`MUTATION`, `TRANSITION`, `RESULT`) ou des **demandes** (`REQUEST`, nom en `…Requested`, un seul destinataire) ; la catégorie est un `ClassVar` vérifié. **Exception nommée** : `ApprovalRequested` est un fait (la demande existe déjà) ; toute autre exception échoue la porte. | Ne pas confondre fait et demande, y compris quand le nom se ressemble. |")
    w("| **C5** | Un port est une **capacité** (`Clock`, `ProvisioningStep`, `ApprovalTargetReader`, `NotificationSender`), jamais une implémentation ; son propriétaire est le module qui le **déclare**, les autres l'implémentent. | Les adaptateurs (`Django…`, `Postgres…`, `Redis…`) appartiennent à l'infrastructure. |")
    w("| **C6** | Le noyau (`kernel`) est **à plat** (`types`, `context`, `errors`, `events`, `ports`) : ce n'est pas un module métier. Il porte les 12 ports partagés. | Les ports partagés sont déclarés dans `kernel` (TA §8.2). |")
    w("| **C7** | `billing` existe **comme contrat seulement** (`ProvisionTrialSubscription`, `SubscriptionChanged`) : aucune règle d'autorisation avant S7. `config` n'a aucun contrat. | Écart I du §13.1 de l'architecture. |")
    w("| **C8** | Les charges utiles ne sont figées que là où un contrat d'interface les fige (20 commandes, `rules.Evaluate`) ; les autres commandes sont des **classes structurelles sans champ** (niveau C plus tard). | Éviter de transformer trop tôt les registres en beaucoup de code inventé. |")
    w("| **C9** | Le payload d'un événement vient du **catalogue des Invariants §10.3** ; les types sont inférés par le nom du champ (`*_id` → identifiant typé, `*_minor` → entier, `*_date` → date, `[]` → tuple, `?` → optionnel). | Une seule source pour les champs. |")
    w("| **C10** | Les 12 signatures de ports du noyau (§6) sont **gelées comme surface candidate de Kernel V1**. **Règle** : toute modification ultérieure est provoquée par un **besoin démontré d'un cas d'usage Application** et fait l'objet d'un **amendement explicite** (journal des amendements). | Éviter deux erreurs opposées : inventer des abstractions dont Application n'a pas besoin, ou modifier le noyau en silence au milieu de la construction des cas d'usage. |")
    w('')

    w('## 5. Les quatre propriétés Registry ↔ Contracts\n')
    w('| # | Propriété | Vérifiée par |\n|---|---|---|')
    w("| **P1** | chaque commande du registre a **exactement un** contrat public (classe, ou `HandlerSpec`), avec les mêmes métadonnées ; rien en trop | classes de `commands.py` et `HANDLERS` comparés au registre |")
    w("| **P2** | chaque événement du catalogue a **exactement une** définition canonique, dans le module propriétaire, avec sa catégorie, son agrégat, son payload (obligatoire ou optionnel) ; un nom en `…Requested` est une demande, sauf exception nommée | import réel de tous les `events.py` |")
    w("| **P3** | chaque port public appartient à son module propriétaire ; aucun port hors d'un `ports.py` | Protocols définis ↔ `PORT_REGISTRY` |")
    w("| **P4** | aucun contrat ne dépend d'un module interdit par TD10 ni d'autre chose que `contracts` d'un autre module | analyse syntaxique des imports ↔ dépendances déclarées |")
    w("| **H** | bibliothèque standard + `verqia` seulement (aucun cadre logiciel : DR1), **aucun comportement** (niveau C), aucune dérive du générateur, aucun fichier en trop (`models.py` refusé) | analyse syntaxique + régénération comparée |")
    w('')
    w("`python architecture_registry/verify_contracts.py` (code de sortie 1 s'il existe une erreur). `test_contracts.py` **injecte** des violations dans une copie des contrats et vérifie que chacune fait échouer la porte : une règle jamais vue échouer n'est pas prouvée.\n")

    w('## 6. Ports du noyau : signatures proposées (C10)\n')
    w('| Port | Capacité | Signature proposée |\n|---|---|---|')
    sig = {'Clock': 'as_of() → datetime', 'IdGenerator': 'new_id() → UUID', 'TransactionManager': 'atomic(ctx, isolation, scope) → contexte ; ctx : CallContext (TENANT), SystemContext (SYSTEM) ou CreationContext (NEW) ; scope ∈ TENANT, SYSTEM, NEW',
           'LockManager': 'lock_rows(operation, resource, ids) · lock_advisory(operation, key)', 'TenantContext': 'organization_id() → OrganizationId · bind_new(organization_id) (unité NEW seulement)',
           'EventOutbox': 'emit(ctx, event, aggregate_id, aggregate_version?) → EventId',
           'AuditWriter': 'write(ctx, action, entity_type, entity_id, before?, after?, reason?)',
           'IdempotencyStore': 'begin(scope, scope_id, key, route, request_hash) → réponse stockée ? · complete(scope, scope_id, key, route, status, body) ; scope ∈ ORGANIZATION, ACTOR',
           'RateLimiter': 'allow(key, limit, window_seconds) → bool', 'Metrics': 'count(name, value, **labels) · observe(name, value, **labels)',
           'Tracer': 'span(name, ctx) → contexte', 'Logger': 'log(level, message, ctx, **fields)'}
    for k, (mod, why) in M.PORT_REGISTRY.items():
        if mod == 'kernel':
            w('| `%s` | %s | %s |' % (k.split('.')[1], why, sig[k.split('.')[1]]))
    w('')

    w('### 6.1 Journal des amendements du noyau (règle C10)\n')
    w('| # | Date | Objet | Besoin démontré par | Validé |\n|---|---|---|---|---|')
    for row in KERNEL_AMENDMENTS:
        w('| %s | %s | %s | %s | %s |' % row)
    w('')

    w('## 7. Charges utiles figées\n')
    w('| Module | Contrat | Figée par |\n|---|---|---|')
    for (m, n), (src, fields) in G.PAYLOADS.items():
        w('| `%s` | `%s(%s)` | %s |' % (m, n, ', '.join(f[0] for f in fields), src))
    for (m, n), (src, fields) in G.QUERY_PAYLOADS.items():
        w('| `%s` | requête `%s(%s)` | %s |' % (m, n, ', '.join(f[0] for f in fields), src))
    w('')

    w("## 8. Constat pour l'étape Application : qui émet une demande (REQUEST) ?\n")
    w("Quatre émissions de `REQUEST` traversent un module : `imports` émet `RISK_`, `PRIORITY_` et `CASHFLOW_RECALCULATION_REQUESTED` (normalisation d'un lot), `automation` émet `CASHFLOW_RECALCULATION_REQUESTED`. La classe canonique de ces événements est dans `risk`, `priority` et `cashflow` (le destinataire, TD13), **hors des dépendances déclarées** d'`imports` et d'`automation`. Ce n'est **pas** une erreur des contrats (qui ne portent que des noms d'événements émis) : c'est un choix à faire **avant** d'écrire le premier cas d'usage.\n")
    w('| Option | Effet |\n|---|---|')
    w("| **1. Ajouter les arêtes** `imports → risk, priority, cashflow` et `automation → cashflow` au Module Registry | amendement d'un registre gelé ; le graphe d'appels reste sans cycle (vérifiable) |")
    w("| **2. Port de demande** : un `RecalculationRequester` du noyau, qui émet la demande par son nom de type | aucune arête nouvelle ; un port de plus (à justifier par un contre-exemple, S1) |")
    w('')
    w("**Décision retenue : option 1, appliquée au Module Registry** (amendement du 2026-09-19 : `imports → risk, priority, cashflow` et `automation → cashflow`). Le graphe d'appels reste sans cycle ; le constat a disparu de `verify_contracts.py`. Raison : mécaniquement vérifiable, aucun mécanisme ajouté (S1, S4).\n")

    w("## 9. Ce qui n'est volontairement pas là\n")
    w("Modèles Django et migrations · cas d'usage (Application) · entités et transitions (Domain) · adaptateurs · API · travailleurs · forme des résultats de requête · charges utiles au-delà des contrats d'interface.\n")

    w('## 10. Régénérer et vérifier\n')
    w('```bash\npython architecture_registry/gen_contracts.py          # écrit verqia-app/verqia/ et ce document\npython architecture_registry/gen_contracts.py --check  # dérive ?\npython architecture_registry/verify_contracts.py       # P1 à P4 et hygiène\n```\n')
    return '\n'.join(o) + '\n'
