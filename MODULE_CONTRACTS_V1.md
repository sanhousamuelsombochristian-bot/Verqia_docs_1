# VERQIA — Module Contracts V1.1

Statut : **V1.1 — VALIDÉ le 2026-09-19** : C1 à C9 validées ; **C10 gelée comme surface candidate de Kernel V1** (toute modification ultérieure doit être provoquée par un besoin démontré d'un cas d'usage Application et faire l'objet d'un amendement explicite) ; option 1 du §8 confirmée. Généré depuis `ARCHITECTURE_REGISTRY_V1.1` (gel V1 + amendements A1 à A3 tracés dans son journal). **Généré** par `architecture_registry/gen_contracts.py` depuis les quatre registres gelés (`ARCHITECTURE_REGISTRY_V1.md`) ; **ne pas modifier à la main** : `verify_contracts.py` détecte toute dérive. Code généré : `verqia-app/verqia/` (à côté de `verqia-docs/`).

Objet : donner à chacun des 22 modules sa **surface publique** (`contracts/`, TD4), framework-free, avant tout cas d'usage, tout Domain et tout modèle PostgreSQL. **Aucun `models.py`, aucune migration, aucun endpoint, aucun travailleur métier** à cette étape.

## 1. Trois niveaux, jamais mélangés

| Niveau | Contenu | Dans cette étape |
|---|---|---|
| **A — structurel** | une classe par commande, événement, requête et port ; métadonnées issues du registre (module, type, source, verrou, écritures, événements émis, idempotence, transaction) | **oui** |
| **B — types contractuels** | identifiants typés (`OrganizationId`…), `MoneyMinor`, `Currency`, `CallContext`, `DomainError` et le catalogue des 104 codes ; types **explicitement figés** par les contrats d'interface (EC-04, EC-05, EC-10, EC-11, EC-12, EC-13) | **oui**, seulement ce qui est figé |
| **C — comportement** | invariants, transitions, validations, forme des résultats | **non** : étape Application + Domain |

## 2. Chiffres

| | |
|---|---:|
| Unités (dont `kernel` et `config`) | 22 |
| Fichiers de contrats générés (noyau inclus) | 87 |
| Contrats de commande (hors handlers) | 94 |
| Abonnements de handler (`HandlerSpec`) | 28 |
| Événements canoniques (une définition chacun) | 77 |
| Requêtes publiées | 28 |
| Ports publics (noyau inclus) | 17 |
| Commandes à charge utile figée par un contrat d'interface | 19 (+ la requête `rules.Evaluate`) |

## 3. Ce que contient chaque module

Seuls les fichiers **nécessaires** existent : un module sans commande n'a pas de `commands.py`.

| Module | Groupe | Fichiers de `contracts/` | Commandes | Handlers | Événements produits | Requêtes | Ports |
|---|---|---|---:|---:|---:|---:|---:|
| `kernel` | Socle | types, context, errors, events, ports (à plat : le noyau est son propre contrat) | — | — | — | — | 12 |
| `platform` | Socle | commands | 3 | 0 | 0 | 0 | 0 |
| `events` | Socle | commands | 3 | 0 | 0 | 0 | 0 |
| `audit` | Socle | commands | 2 | 0 | 0 | 0 | 0 |
| `identity` | Identité | commands, events, queries | 7 | 0 | 5 | 2 | 0 |
| `organizations` | Identité | commands, events, ports, queries | 8 | 0 | 6 | 3 | 1 |
| `customers` | Sources | commands, events, queries | 8 | 0 | 7 | 2 | 0 |
| `invoices` | Sources | commands, events, queries | 8 | 0 | 12 | 4 | 0 |
| `payments` | Sources | commands, events, queries, types | 4 | 0 | 4 | 3 | 0 |
| `promises` | Sources | commands, events, queries | 3 | 4 | 4 | 2 | 0 |
| `imports` | Sources | commands, events, queries | 6 | 3 | 8 | 2 | 0 |
| `rules` | Décision | ports, queries, types | 0 | 0 | 0 | 2 | 1 |
| `risk` | Projections | commands, events, queries | 1 | 2 | 2 | 1 | 0 |
| `priority` | Projections | commands, events, queries | 1 | 2 | 2 | 1 | 0 |
| `cashflow` | Projections | commands, events, queries | 1 | 2 | 2 | 1 | 0 |
| `approvals` | Action | commands, events, ports, queries, types | 3 | 0 | 3 | 1 | 1 |
| `collection` | Action | commands, events, queries | 16 | 9 | 8 | 2 | 0 |
| `notifications` | Action | commands, events, ports, queries, types | 3 | 1 | 3 | 1 | 1 |
| `automation` | Orchestration | commands, events, queries, types | 14 | 5 | 10 | 1 | 0 |
| `billing` | Commerce | commands, events | 1 | 0 | 1 | 0 | 0 |
| `jobs` | Pilotage | commands, ports | 2 | 0 | 0 | 0 | 1 |
| `config` | Pilotage | *aucun : racine de composition* | 0 | 0 | 0 | 0 | 0 |

## 4. Décisions (C1 à C10), validées le 2026-09-19

| # | Décision | Pourquoi |
|---|---|---|
| **C1** | **L'organisation n'est jamais un champ de commande** : elle vient du `CallContext`. | K14 : « quelle organisation ? » a pour propriétaire le `TransactionManager` et RLS ; un champ dupliquerait l'information et ouvrirait une divergence (commande pour A, contexte de B). |
| **C2** | Un **handler** n'a pas de classe de commande : son contrat est un `HandlerSpec` (nom stable, événements écoutés, effets), déclaré dans `events.py` du module (TD13). | Un handler est appelé par le relais, jamais par un autre module ; sa surface publique est ce qu'il écoute. |
| **C3** | Tout autre élément du registre (commande, service, système, travail, travailleur) a **une classe de commande** et une seule. | Propriété P1 : « chaque commande du registre possède exactement un contrat public ». |
| **C4** | Les événements sont des **faits passés** (`MUTATION`, `TRANSITION`, `RESULT`) ou des **demandes** (`REQUEST`, nom en `…Requested`, un seul destinataire) ; la catégorie est un `ClassVar` vérifié. **Exception nommée** : `ApprovalRequested` est un fait (la demande existe déjà) ; toute autre exception échoue la porte. | Ne pas confondre fait et demande, y compris quand le nom se ressemble. |
| **C5** | Un port est une **capacité** (`Clock`, `ProvisioningStep`, `ApprovalTargetReader`, `NotificationSender`), jamais une implémentation ; son propriétaire est le module qui le **déclare**, les autres l'implémentent. | Les adaptateurs (`Django…`, `Postgres…`, `Redis…`) appartiennent à l'infrastructure. |
| **C6** | Le noyau (`kernel`) est **à plat** (`types`, `context`, `errors`, `events`, `ports`) : ce n'est pas un module métier. Il porte les 12 ports partagés. | Les ports partagés sont déclarés dans `kernel` (TA §8.2). |
| **C7** | `billing` existe **comme contrat seulement** (`ProvisionTrialSubscription`, `SubscriptionChanged`) : aucune règle d'autorisation avant S7. `config` n'a aucun contrat. | Écart I du §13.1 de l'architecture. |
| **C8** | Les charges utiles ne sont figées que là où un contrat d'interface les fige (20 commandes, `rules.Evaluate`) ; les autres commandes sont des **classes structurelles sans champ** (niveau C plus tard). | Éviter de transformer trop tôt les registres en beaucoup de code inventé. |
| **C9** | Le payload d'un événement vient du **catalogue des Invariants §10.3** ; les types sont inférés par le nom du champ (`*_id` → identifiant typé, `*_minor` → entier, `*_date` → date, `[]` → tuple, `?` → optionnel). | Une seule source pour les champs. |
| **C10** | Les 12 signatures de ports du noyau (§6) sont **gelées comme surface candidate de Kernel V1**. **Règle** : toute modification ultérieure est provoquée par un **besoin démontré d'un cas d'usage Application** et fait l'objet d'un **amendement explicite** (journal des amendements). | Éviter deux erreurs opposées : inventer des abstractions dont Application n'a pas besoin, ou modifier le noyau en silence au milieu de la construction des cas d'usage. |

## 5. Les quatre propriétés Registry ↔ Contracts

| # | Propriété | Vérifiée par |
|---|---|---|
| **P1** | chaque commande du registre a **exactement un** contrat public (classe, ou `HandlerSpec`), avec les mêmes métadonnées ; rien en trop | classes de `commands.py` et `HANDLERS` comparés au registre |
| **P2** | chaque événement du catalogue a **exactement une** définition canonique, dans le module propriétaire, avec sa catégorie, son agrégat, son payload (obligatoire ou optionnel) ; un nom en `…Requested` est une demande, sauf exception nommée | import réel de tous les `events.py` |
| **P3** | chaque port public appartient à son module propriétaire ; aucun port hors d'un `ports.py` | Protocols définis ↔ `PORT_REGISTRY` |
| **P4** | aucun contrat ne dépend d'un module interdit par TD10 ni d'autre chose que `contracts` d'un autre module | analyse syntaxique des imports ↔ dépendances déclarées |
| **H** | bibliothèque standard + `verqia` seulement (aucun cadre logiciel : DR1), **aucun comportement** (niveau C), aucune dérive du générateur, aucun fichier en trop (`models.py` refusé) | analyse syntaxique + régénération comparée |

`python architecture_registry/verify_contracts.py` (code de sortie 1 s'il existe une erreur). `test_contracts.py` **injecte** des violations dans une copie des contrats et vérifie que chacune fait échouer la porte : une règle jamais vue échouer n'est pas prouvée.

## 6. Ports du noyau : signatures proposées (C10)

| Port | Capacité | Signature proposée |
|---|---|---|
| `Clock` | `as_of` de l'unité de travail (TD23) | as_of() → datetime |
| `IdGenerator` | identifiants UUIDv7, instant tiré du Clock | new_id() → UUID |
| `TransactionManager` | unité de travail : organisation, isolation, délais (TD25, TD26) | atomic(ctx, isolation, scope) → contexte ; ctx : CallContext (TENANT), SystemContext (SYSTEM) ou CreationContext (NEW) ; scope ∈ TENANT, SYSTEM, NEW |
| `LockManager` | verrous ordonnés par opération enregistrée (TD27) | lock_rows(operation, resource, ids) · lock_advisory(operation, key) |
| `TenantContext` | organisation courante ; refus si absente (TD17) | organization_id() → OrganizationId · bind_new(organization_id) (unité NEW seulement) |
| `EventOutbox` | émettre un événement dans la transaction de l'appelant (EC-01) | emit(ctx, event, aggregate_id, aggregate_version?) → EventId |
| `AuditWriter` | écrire l'audit dans la transaction (D3) | write(ctx, action, entity_type, entity_id, before?, after?, reason?) |
| `IdempotencyStore` | clés d'idempotence des commandes (TD32) | begin(scope, scope_id, key, route, request_hash) → réponse stockée ? · complete(scope, scope_id, key, route, status, body) ; scope ∈ ORGANIZATION, ACTOR |
| `RateLimiter` | limitation d'API et étranglement d'envoi (TD49) | allow(key, limit, window_seconds) → bool |
| `Metrics` | compteurs et histogrammes, sans donnée personnelle | count(name, value, **labels) · observe(name, value, **labels) |
| `Tracer` | traces rattachées à la chaîne événement / exécution / action | span(name, ctx) → contexte |
| `Logger` | journaux structurés, sans donnée personnelle | log(level, message, ctx, **fields) |

### 6.1 Journal des amendements du noyau (règle C10)

| # | Date | Objet | Besoin démontré par | Validé |
|---|---|---|---|---|
| K1 | 2026-09-20 | `TransactionManager.atomic(ctx, isolation, scope)` avec `TransactionScope` `TENANT` / `SYSTEM` ; `SystemContext` (sans organisation) ; `CallContext.organization_id` reste obligatoire ; la portée est fixée par le contrat Application (`transaction_scope`), jamais par l'appelant | coureur : `OutboxPublisher` (`RELAY`) et `PartitionManager` (`NONE`) n'étaient pas exprimables (`tenant_unscoped_pending`) | oui, 2026-09-20 |
| K2 | 2026-09-20 | `IdempotencyStore.begin/complete(scope, scope_id, key, route, ...)` avec `IdempotencyScope` `ORGANIZATION` / `ACTOR` ; jamais un `organization_id` nul par convention | coureur : `CreateOrganization` s'exécute avant l'existence de l'organisation (AP-14) | oui, 2026-09-20 |
| K3 | 2026-09-20 | `TransactionScope.NEW` (troisième régime, distinct de `TENANT` et `SYSTEM`) ; `CreationContext` sans champ d'organisation ; `TenantContext.bind_new(organization_id)` : liaison typée, unique, réservée à l'unité `NEW`, d'un identifiant venant d'être généré ; une fois liée, l'organisation ne change plus dans l'unité de travail | coureur, étape 11 : `CreateOrganization` recevait un `CallContext` dont l'organisation était ignorée puis remplacée (`organization_id` à valeur ambiguë) | oui, 2026-09-20 |

## 7. Charges utiles figées

| Module | Contrat | Figée par |
|---|---|---|
| `payments` | `AllocatePayment(payment_id, allocations)` | EC-05 |
| `payments` | `ReverseAllocation(allocation_id, amount_minor, reason)` | EC-05 |
| `payments` | `ReversePayment(payment_id, reason_code, reason)` | EC-05 |
| `imports` | `NormalizeImportBatch(batch_id)` | EC-07 |
| `invoices` | `IssueInvoice(invoice_id)` | EC-06 |
| `invoices` | `CancelInvoice(invoice_id, reason_code)` | EC-06 |
| `invoices` | `VoidInvoice(invoice_id, reason_code)` | EC-06 |
| `approvals` | `RequestApproval(target, kind, reason, context, expires_at, requested_from_user, requested_role)` | EC-13 |
| `approvals` | `DecideApproval(approval_id, decision, comment)` | EC-13 |
| `collection` | `CreateCollectionAction(subject, type, channel, execution_id, step_id)` | EC-11 |
| `collection` | `CreateManualAction(subject, type, level, channel, override_grants)` | EC-11 |
| `collection` | `ExecuteDueAction(action_id)` | EC-11 |
| `collection` | `AuthorizeOverride(action_ref, exception_code, reason_code, reason_text)` | EC-10 |
| `notifications` | `HandleSendResult(notification_id, attempt_no, result)` | EC-04 |
| `automation` | `ActivateAutomation(version_id, enrollment_mode, preview)` | EC-12 |
| `automation` | `RunExecutionStep(execution_id)` | EC-12 |
| `automation` | `RetryExecution(execution_id)` | EC-12 |
| `automation` | `ReleaseImportTranche(batch_id)` | EC-12 |
| `events` | `ReplayDeadEvent(event_id, handler_name)` | EC-02 |
| `rules` | requête `Evaluate(subject, origin, definition_ref, action_kind, channel, override_grants, trigger_event)` | EC-09 |

## 8. Constat pour l'étape Application : qui émet une demande (REQUEST) ?

Quatre émissions de `REQUEST` traversent un module : `imports` émet `RISK_`, `PRIORITY_` et `CASHFLOW_RECALCULATION_REQUESTED` (normalisation d'un lot), `automation` émet `CASHFLOW_RECALCULATION_REQUESTED`. La classe canonique de ces événements est dans `risk`, `priority` et `cashflow` (le destinataire, TD13), **hors des dépendances déclarées** d'`imports` et d'`automation`. Ce n'est **pas** une erreur des contrats (qui ne portent que des noms d'événements émis) : c'est un choix à faire **avant** d'écrire le premier cas d'usage.

| Option | Effet |
|---|---|
| **1. Ajouter les arêtes** `imports → risk, priority, cashflow` et `automation → cashflow` au Module Registry | amendement d'un registre gelé ; le graphe d'appels reste sans cycle (vérifiable) |
| **2. Port de demande** : un `RecalculationRequester` du noyau, qui émet la demande par son nom de type | aucune arête nouvelle ; un port de plus (à justifier par un contre-exemple, S1) |

**Décision retenue : option 1, appliquée au Module Registry** (amendement du 2026-09-19 : `imports → risk, priority, cashflow` et `automation → cashflow`). Le graphe d'appels reste sans cycle ; le constat a disparu de `verify_contracts.py`. Raison : mécaniquement vérifiable, aucun mécanisme ajouté (S1, S4).

## 9. Ce qui n'est volontairement pas là

Modèles Django et migrations · cas d'usage (Application) · entités et transitions (Domain) · adaptateurs · API · travailleurs · forme des résultats de requête · charges utiles au-delà des contrats d'interface.

## 10. Régénérer et vérifier

```bash
python architecture_registry/gen_contracts.py          # écrit verqia-app/verqia/ et ce document
python architecture_registry/gen_contracts.py --check  # dérive ?
python architecture_registry/verify_contracts.py       # P1 à P4 et hygiène
```

