# VERQIA : Application Contract V1

> **Statut : V1 — GELÉ le 2026-10-04** (empreinte `a96bda3b0691…`, 40 fichiers). Corrections de revue RV1–RV8, D-AP1, O1 et O2 tranchées ; toute modification passe par le journal des amendements (§6). Généré par `architecture_registry/gen_application_doc.py` depuis les quatre registres gelés ; vérifié par `verify_application.py` (A1–A13) et `test_application.py`. Ne pas modifier à la main.
> Aucun modèle, aucune migration, aucun point d'entrée, aucun travailleur métier à cette étape. Les corrections de revue sont nommées **RV1–RV8** pour ne pas les confondre avec les propriétés de vérification A1–A13.

## Corrections de revue

| # | Correction | Où |
|---|---|---|
| RV1 | `CreateOrganization` : régime d'organisation `NEW` (l'organisation n'existe pas encore), et non `REQUIRED` | §3.2, A4 |
| RV2 | AP-06 réconcilié : audit obligatoire pour les commandes **publiques** ; autres entrées seulement si nommées (D3) ; `CompleteProvisioning` : voir D-AP1 | AP-06, §3.2, A6 |
| RV3 | Commande publique et étape de provisioning distinguées (entrée dérivée et vérifiée) | AP-11, §3.2, A10 |
| RV4 | `OutboxPublisher` : réclamer / handlers dans leur transaction / poser publié (registre amendé A4, TD33) | §3.3, A11 |
| RV5 | `CreateCollectionAction` : composition orchestrée (TD58), non « une transaction par module » | §3.3, A11 |
| RV6 | `RunExecutionStep` : T1 réclame, T2 effet, T3 finalise ; AP-10 | AP-10, §3.3, A11 |
| RV7 | `REPLAY` selon la nature ; issues par nature | AP-12, §3.1, A9 |
| RV8 | AP-08 renforcé : cible, dépendance, sens du graphe, phase `own:`, possession de l'état | AP-08, A8, A11 |

### Décisions de gel (2026-09-19)

| Point | Décision |
|---|---|
| RV1–RV8, AP-10, AP-12, phases | **validés** |
| D-AP1 | **acceptée** : `CompleteProvisioning` reste un cas d'usage `system`, sans audit direct. Règle : audit obligatoire pour les commandes publiques ; pour les autres entrées, seulement si D3 ou un contrat l'exige explicitement |
| O1 | **fixé au contrat** (AP-14) : `CreateOrganization` a une portée d'idempotence `(acteur, clé, route)` ; la clé d'idempotence n'engendre jamais l'identifiant d'organisation |
| F1, F2 (2026-09-20) | **tranchés** : `TransactionScope` `TENANT` / `SYSTEM` (organisation obligatoire dans `CallContext`, `SystemContext` sans organisation) ; `IdempotencyScope` `ORGANIZATION` / `ACTOR`, typé ; amendements de noyau K1 et K2, amendement Application B1 |
| Frontières transactionnelles (2026-09-20) | **option 1, gel conservé** : `A → B.own:` = unités de travail SÉPARÉES ; la transaction de B est ouverte par le propriétaire de B ; l'appelant ne la couvre pas ; le tenant reste cohérent entre phases ; l'échec d'une phase n'annule pas les phases validées ; une phase rejouée est idempotente. TD58 et AP-13 inchangés ; aucun amendement |
| Phases sans verrou propre (2026-09-20) | **acceptée pour V1, sans amendement de TD27** : une unité secondaire d'un cas d'usage reprend la séquence de verrous de son opération, sans `K`. La séquence est DÉRIVÉE du Lock Registry généré (`Runner.unit_lock_sequence`) ; le coureur n'en détient aucune liste, et un test modifie le registre pour montrer que la dérivation le suit |
| O2 | **corrigé** : quatre rappels obsolètes (synthèse et justification de TD1 dans `TECHNICAL_ARCHITECTURE_V1.md`, DR3 dans `ENGINE_CONTRACTS_V1.md`, ligne `AR-04` de la matrice), sans rouvrir aucune décision |

## 0. Où se situe cette couche

| Couche | Répond à |
|---|---|
| Registry | ce qui existe |
| Contracts | ce qui est publiquement exposé |
| **Application** | **comment une opération traverse le système** |
| Domain | quelles règles métier sont vraies |
| PostgreSQL | comment l'état est finalement persisté |

Un cas d'usage **n'invente rien** : il ordonne. Il ne décide aucune règle métier (Domain) et ne connaît aucune table (infrastructure). Ses seize éléments sont de la **donnée** dérivée des registres, consommée par un seul coureur (à venir) : le pipeline n'est pas recopié dans chaque cas d'usage.

## 1. Le pipeline d'un cas d'usage

```
Command ─▶ CallContext ─▶ validation d'entrée ─▶ clé d'idempotence ─▶ transaction + TenantContext ─▶ verrous (échelle)
   ─▶ lectures par ports ─▶ Domain décide ─▶ appels inter-modules (contrats) ─▶ écritures + EventOutbox + Audit ─▶ COMMIT ─▶ résultat
```

| # | Étape | Règle | Fondement |
|---|---|---|---|
| P1 | Réception (api) | traduit le transport en `Command` et `CallContext` ; aucune règle métier ; l'organisation ne vient JAMAIS d'un champ de la commande | K14, TD4 |
| P2 | CallContext | organisation, acteur, corrélation, causalité et **`as_of` lu sur le port `Clock`** ; l'heure de l'hôte n'est jamais du temps métier | TD23 |
| P3 | Validation d'entrée | structure seulement (types, présence, formats) ; sans lecture de base ; échec = `VALIDATION` | EC §0.3 |
| P4 | Clé d'idempotence | première ressource de l'échelle ; un rejeu renvoie le résultat enregistré (`REPLAY`) sans aucun effet ; portée `(organisation, clé, route)`, sauf `CreateOrganization` : `(acteur, clé, route)`, consultée **avant** de générer l'organisation (AP-14) | TD32, TD27, AP-14 |
| P5 | Transaction + TenantContext | la transaction s'ouvre, l'organisation est posée **avant toute lecture** ; sans organisation, refus (fermé par défaut) ; **deux régimes distincts** : `NEW` (`CreateOrganization` : l'identifiant est généré puis lié par `TenantContext.bind_new`, §3.2) et `SYSTEM` (aucune organisation, §3.4) | TD26, TD59, K1, K3 |
| P6 | Verrous | la séquence du Lock Registry, rang strictement croissant ; jamais d'ordre local | TD27 |
| P7 | Lectures | par ports ; **après** les verrous ; une lecture n'est jamais un cache de décision | X1, TD27 |
| P8 | Domain | fonction pure de (état lu, commande, `as_of`) qui rend une décision ou lève une `DomainError` du catalogue ; aucune entrée-sortie | DR1 |
| P9 | Inter-modules | par contrats uniquement ; appel simple = dans la transaction de l'appelant ; `own:` = dans la transaction du propriétaire de l'état | TD4, TD10, TD55, TD58 |
| P10 | Écritures atomiques | états + `EventOutbox` + audit + résultat d'idempotence (ou reçu du handler) dans **une même transaction** | TD25, TD32 |
| P11 | Après COMMIT | seulement : publication par le relais, envois externes ; aucun effet externe dans la transaction | TD33, TD31 |
| P12 | Résultat | une issue **propre à la nature du cas d'usage** (§3.1), ou une erreur du catalogue ; jamais d'erreur hors Annexe A ; `REPLAY` n'est pas une issue universelle | EC §0.3, Annexe A |

### 1.1 Les seize éléments d'un cas d'usage

| Élément | Contenu | Source |
|---|---|---|
| Commande | la classe publique (`contracts/commands.py`) ; vide pour un handler | Contracts |
| Use case | nom unique `module.Nom` | Command Registry |
| Entrée | charge utile figée (EC-xx) ou « niveau C » : à figer avec le Domain | Contracts |
| Transaction | une, par organisation, par pas, trois (automatisation)… | Command Registry |
| Organisation | requise / de l'événement / énumérée / relais nommé / aucune | TD26 |
| Idempotence | mécanisme propre au cas d'usage | Command Registry |
| Verrous | séquence ressource:mode dans l'échelle générée | Lock Registry |
| Lectures | requêtes publiées d'un autre module (`module.Requête`) | Command Registry |
| Domain | états écrits (clés d'état), dont les seules exceptions C12 | TD55 |
| Inter-modules | appels par contrats, `own:`, ports implémentés | TD10, TD58 |
| Événements | événements émis dans l'outbox | Event Registry |
| Audit | requis / conditionnel motivé / aucun | D3 |
| Erreurs | codes de l'Annexe A nommés par les contrats d'interface + classes possibles | Annexe A |
| Résultat | issue et contenu renvoyé | EC-xx |
| Reprise | TD30 commandes, TD35 handlers, TD43 travaux de niveau, TD31 travailleurs à bail | TD30, TD31, TD35, TD43 |
| Atomicité | l'ensemble écritures + événements + audit + idempotence/reçu, indivisible | TD25 |

## 2. Invariants du contrat (AP)

| Id | Invariant | Vérifié par |
|---|---|---|
| AP-01 | Chaque entrée du Command Registry a exactement une spécification ; aucune spécification sans entrée | A1 |
| AP-02 | Transaction, idempotence, événements, écritures et abonnements sont ceux du registre | A2 |
| AP-03 | La séquence de verrous est celle du Lock Registry, en rang strictement croissant sur l'échelle générée (jamais écrite à la main) | A3 |
| AP-04 | Régime d'organisation : `REQUIRED` pour tout cas d'usage appelé, `EVENT` pour un handler, `ENUMERATOR` pour un travail ; exceptions fermées : relais d'outbox (`RELAY`), gestionnaire de partitions (`NONE`) | A4 |
| AP-05 | Un code d'erreur cité existe à l'Annexe A ; aucune erreur inventée par un cas d'usage | A5 |
| AP-06 | Toute commande **publique** (entrée `PUBLIC`, nature `command`) a un audit. Toute autre entrée (étape de provisioning, interne, réaction, travail) n'en produit un que si elle figure dans la liste nominative de D3 ; un audit conditionnel porte son motif | A6, A10 |
| AP-07 | Écritures, événements, audit, idempotence et reçu forment une seule unité ; aucun effet externe n'y figure | A7 |
| AP-08 | Tout appel inter-modules a : (1) une cible existante ; (2) une dépendance déclarée (TD10, pilotes `jobs` et `config` dispensés) ; (3) un sens compatible avec le graphe (jamais de retour vers un module qui dépend déjà de l'appelant) ; (4) une transaction compatible avec TD58 : tout `own:` a sa phase ; (5) une cible `own:` qui possède réellement l'état qu'elle écrit | A8, A11 |
| AP-09 | Les spécifications sont de la donnée : ni fonction, ni contrôle de flux, ni cadre logiciel | hygiène |
| AP-10 | Réclamer → Effet → Finaliser. Un cas d'usage à réclamation (`CLAIM`) l'ouvre en première phase ; l'effet (`EFFECT`, dans la transaction du propriétaire, idempotent) n'est autorisé qu'après une réclamation valide ; `FINALIZE` clôt, dans le module de la réclamation, et ne finalise qu'une exécution dont la réclamation correspond | A11 |
| AP-11 | Les entrées sont distinguées : commande publique, étape de provisioning, interne, réaction, travail. Une étape de provisioning est un service idempotent par (organisation, étape), à verrou, dans sa transaction, sans audit direct | A10 |
| AP-12 | `REPLAY` n'existe que pour une commande ; les issues d'un handler sont celles de son reçu ; chaque nature n'a que ses issues (§3.1) | A9 |
| AP-13 | Un cas d'usage composé déclare ses phases ordonnées, une transaction chacune ; un effet extérieur n'est dans aucune transaction ; l'état d'un autre module n'est écrit que dans sa transaction (TD55, TD58) | A11 |
| AP-14 | Portée d'idempotence, **typée** (`IdempotencyScope`, K2). Une commande qui insère la clé de requête `K` a la portée `ORGANIZATION` : `(organisation, clé, route)` (TD32). `CreateOrganization` est l'exception nommée : `(acteur, clé, route)`, consultée avant toute création ; sur rejeu, le résultat mémorisé est restitué et aucun identifiant n'est généré. La clé d'idempotence est une identité technique de requête et n'engendre jamais `organization_id`, identité métier | A12 |
| AP-15 | Portée de transaction (K1). `TransactionScope` **`TENANT`** (`CallContext`, organisation obligatoire), **`SYSTEM`** (`SystemContext`, aucune organisation) ou **`NEW`** (`CreationContext`, organisation liée par `TenantContext.bind_new`). Elle est **déduite du régime d'organisation** par le contrat (`SCOPE_OF_TENANT`), jamais choisie par l'appelant : `SYSTEM` pour `RELAY` et `NONE`, `NEW` pour `NEW`. Ce sont trois régimes, pas trois variantes d'un `organization_id` nul : `CallContext.organization_id` reste obligatoire, et une fois liée l'organisation ne change plus dans l'unité de travail | A13 |

## 3. Règles transversales

- **Reprise.** Commande : rejeu borné (3) sur `40001`/`40P01`, avant tout effet externe (TD30). Handler : `RETRYING` à 10 s, 1 min, 5 min, 30 min, 2 h, puis `DEAD` (TD35). Travail : de niveau, le passage suivant rattrape (TD43). Travailleur : bail repris par le Reaper, livraison au moins une fois (TD31).
- **Audit (D3).** Requis pour toute commande et pour les actions sensibles : `AnonymizeAuditLogs`, `AnonymizeCustomer`, `AnonymizeUser`, `AuthorizeOverride`, `ReplayDeadEvent`. Conditionnel : `CreateCollectionAction` (seulement si l'action est manuelle ou porte un override (Collection §4, D3)); `ExecuteDueAction` (à chaque vérification d'un grant d'override à l'exécution (V1.2, G8)). Aucun pour handlers, travaux et services (historique et événements suffisent).
- **Erreurs.** Une classe possible ne veut pas dire un code : les codes nommés (25 cas d'usage) sont ceux que les contrats d'interface figent ; pour les autres, seule la classe est déclarée. Les codes manquants se figeront avec le Domain (niveau C).

### 3.1 Issues par nature (RV7)

| Nature | Issues | Remarque |
|---|---|---|
| commande | `OK`, `REPLAY` ; `SKIPPED`, `DEFERRED` seulement si le contrat le prévoit (`CreateCollectionAction`, `CreateManualAction`, EC-11) | `REPLAY` : rejeu d'une clé d'idempotence |
| handler | `PROCESSED`, `SKIPPED`, `RETRYING`, `DEAD` | ce sont les issues du reçu ; un `REPLAY` de handler est compté, non stocké (EC-02) |
| travail | `OK`, `SKIPPED` | de niveau : le passage suivant rattrape |
| travailleur | `OK`, `RETRYING`, `DEFERRED` | l'échec suit le contrat |
| système | `OK`, `SKIPPED` | garde d'état |
| service | celles de l'appelant | aucune issue propre |

### 3.2 Entrées et provisioning (RV1, RV2, RV3)

| Entrée | Nature | Règles |
|---|---|---|
| `PUBLIC` | commande | clé d'idempotence, audit, transaction, Domain, événement |
| `PROVISIONING_STEP` | service implémentant `organizations.ProvisioningStep` | `(organisation, étape)`, transaction du module propriétaire, événement ; **pas d'audit direct** ; jamais appelée par l'API |
| `INTERNAL` | système ou service | appelée par un autre cas d'usage ou un balayage ; garde d'état ou transaction de l'appelant ; audit seulement s'il est nommé (D3) |
| `REACTION` | handler | reçu `(événement, handler)` ; jamais d'audit direct |
| `BACKGROUND` | travail ou travailleur | de niveau ou à bail |

`CreateOrganization` est **la seule** commande dont l'organisation n'existe pas encore : son régime est `NEW` (T1 pose l'identifiant généré à la réception comme tenant), puis chaque étape et `CompleteProvisioning` sont des cas d'usage `REQUIRED` de l'organisation créée, à l'état `PROVISIONING`. `CompleteProvisioning` est de nature **système** (State Machines §1 : acteur `SYSTEM`) : D3 réserve l'audit aux commandes d'un utilisateur ou d'une automatisation ; l'audit de la création est porté par `CreateOrganization`, et la transition est tracée par ses événements. Cette lecture est à confirmer (**décision D-AP1**).

**Idempotence de création (AP-14).** `CreateOrganization` consulte `(acteur, clé, route)` **avant toute génération** ; sur rejeu il restitue le résultat mémorisé (`REPLAY`) et aucun identifiant n'est généré ; sinon il génère `organization_id`, le lie par `TenantContext.bind_new`, crée l'organisation `PROVISIONING`, enregistre l'idempotence et rend le résultat. Après la création, `organization_id` est la référence de toutes les opérations suivantes. La portée `ACTOR` et le régime `NEW` vont **ensemble et seulement ensemble** (A12).

**Clé de requête (AP-14).** Le texte libre d'idempotence du registre décrit le mécanisme du cas d'usage ; la **clé de requête d'API** se lit dans son opération de verrous : une commande qui insère `K` la prend. Un cas d'usage système ou service qui partage l'opération d'une commande (`ApplySettlement`, `AnonymizeUser`) hérite de la clé de son appelant.

### 3.3 Cas d'usage composés : phases ordonnées (RV4, RV5, RV6)

Chaque phase est **une transaction, ordonnée, non interchangeable** ; une phase `EXTERNAL` n'est dans aucune transaction (TD31). L'état d'un autre module n'est écrit que dans sa transaction (`own:`, TD58).

| Cas d'usage | # | Rôle | Module(s) | Appel `own:` | Écrit lui-même | Contenu |
|---|---:|---|---|---|---|---|
| `organizations.CreateOrganization` | 1 | WRITE | organizations | — | organizations.record, organizations.settings, organizations.status, audit, clé d'idempotence | organisation et réglages, état PROVISIONING ; aucune commande métier n'y est acceptée (TD59) |
|  | 2 | EFFECT | identity, automation, billing | `organizations.ProvisioningStep` | — | une transaction par étape, dans son module propriétaire, idempotente par (organisation, étape) |
|  | 3 | FINALIZE | organizations | `organizations.CompleteProvisioning` | — | PROVISIONING → ACTIVE et ORGANIZATION_CREATED, quand toutes les étapes sont faites |
| `organizations.ResumeProvisioning` | 1 | EFFECT | identity, automation, billing | `organizations.ProvisioningStep` | — | reprise étape par étape, chacune dans sa transaction |
|  | 2 | FINALIZE | organizations | `organizations.CompleteProvisioning` | — | PROVISIONING → ACTIVE |
| `collection.CreateCollectionAction` | 1 | WRITE | collection | — | collection.action_status, événements, audit, clé d'idempotence | l'action est créée PROPOSED (transaction de collection) |
|  | 2 | EFFECT | collection | `collection.AdvanceProposedAction` | — | composition orchestrée (TD58) : approbation demandée dans la transaction d'approvals, puis transition dans celle de collection |
| `collection.AdvanceProposedAction` | 1 | EFFECT | approvals | `approvals.RequestApproval` | — | demande d'approbation dans la transaction d'approvals |
|  | 2 | FINALIZE | collection | — | collection.action_status, événements | transition PROPOSED → SCHEDULED, PENDING_APPROVAL ou SUPPRESSED, selon le résultat |
| `collection.ResumeProposedActions` | 1 | EFFECT | collection | `collection.AdvanceProposedAction` | — | un balayage relance chaque action PROPOSED interrompue |
| `collection.CreateManualAction` | 1 | WRITE | collection | — | collection.action_status, événements, audit, clé d'idempotence | l'action est créée PROPOSED (transaction de collection) |
|  | 2 | EFFECT | collection | `collection.AdvanceProposedAction` | — | composition orchestrée (TD58) : approbation demandée dans la transaction d'approvals, puis transition dans celle de collection |
| `collection.ExecuteDueAction` | 1 | CLAIM | collection | — | collection.action_status, collection.attempts, audit | claim gardé et revalidation complète (audit des grants vérifiés) |
|  | 2 | EFFECT | notifications | `notifications.CreateNotification` | — | notification créée dans la transaction de notifications |
|  | 3 | EXTERNAL | notifications | — | — | envoi : hors de toute transaction (TD31) |
|  | 4 | FINALIZE | collection | — | événements | enregistrement du résultat |
| `collection.ScanReconciliationReviews` | 1 | EFFECT | notifications | `notifications.CreateNotification` | — | notification dans la transaction de notifications |
| `automation.RunExecutionStep` | 1 | CLAIM | automation | — | automation.execution | T1 : execution → RUNNING ; seul le porteur de la réclamation peut atteindre le propriétaire de l'effet |
|  | 2 | EFFECT | collection, notifications, approvals | `collection.CreateCollectionAction`, `notifications.CreateNotification`, `approvals.RequestApproval` | — | T2 : effet dans la transaction du module propriétaire, idempotent |
|  | 3 | FINALIZE | automation | — | automation.execution, événements | T3 : résultat ; ne finalise que l'exécution dont la réclamation correspond |
| `jobs.ImportReleaser` | 1 | EFFECT | automation | `automation.ReleaseImportTranche` | — | tranche libérée dans la transaction d'automation |
|  | 2 | EFFECT | imports | `imports.CompleteImportRelease` | — | lot marqué RELEASED dans la transaction d'imports |
| `jobs.ReconciliationWindowScan` | 1 | EFFECT | collection | `collection.ScanReconciliationReviews` | — | revues de rapprochement, transaction de collection |
|  | 2 | EFFECT | automation | `automation.ResumeReconciliationPaused` | — | reprise des exécutions en pause, transaction d'automation |
| `events.OutboxPublisher` | 1 | CLAIM | events | — | events.publication | bail court (available_at, publish_attempts), SKIP LOCKED |
|  | 2 | EFFECT | * | — | events.receipts | chaque handler abonné dans sa propre transaction, son reçu écrit par lui ; jamais de verrou tenu pendant un handler |
|  | 3 | FINALIZE | events | — | events.publication | published_at quand chaque handler a pris en charge, quel que soit le résultat (TD33) |

**Exécution (démontrée par le coureur, étape 12).** Chaque phase à appel `own:` est une unité de travail distincte, dans la transaction du module propriétaire ; l'orchestrateur ne possède jamais l'état d'un autre module ; un `own:` n'a aucune porte dans une unité ouverte ; une clé de requête n'est prise que dans la première unité ; une phase rejouée reçoit la même clé déterministe.

Trois précisions :

- **`RunExecutionStep` (AP-10).** T1 réclame (`execution → RUNNING`) ; T2 exécute l'effet dans le module propriétaire, idempotent, et n'est autorisée que pour le porteur de T1 ; T3 finalise seulement l'exécution dont la réclamation correspond. Sans réclamation valide, aucun effet ne peut atteindre le propriétaire.
- **`OutboxPublisher` (RV4, TD33).** Le relais ne fait **aucune** publication dans une transaction métier : T1 réclame par bail (courte, `SKIP LOCKED`) ; chaque handler s'exécute ensuite **dans sa propre transaction** et écrit son propre reçu ; T3 pose `published_at` quand chaque handler a pris en charge l'événement, quel qu'en soit le résultat. Le registre le disait « une transaction » : amendement **A4** du registre (V1.2).
- **`CreateCollectionAction` (RV5, TD58).** Composition orchestrée, pas « une transaction par module » : `collection` crée l'action `PROPOSED` ; `approvals` enregistre la demande dans **sa** transaction (`own:approvals.RequestApproval`, via `AdvanceProposedAction`) ; `collection` transitionne selon le résultat. Un balayage (`ResumeProposedActions`) reprend un processus interrompu.

### 3.4 Portée de transaction (F1, K1)

| Régime d'organisation | Portée | Contexte | Cas d'usage |
|---|---|---|---|
| `REQUIRED`, `EVENT`, `ENUMERATOR` | `TENANT` | `CallContext` : `organization_id` obligatoire, refus fermé si absent | tous, sauf ci-dessous |
| `NEW` | `NEW` | `CreationContext` : **aucun champ d'organisation** ; liée par `TenantContext.bind_new` après la clé d'idempotence et la génération de l'identifiant | `CreateOrganization` |
| `RELAY`, `NONE` | `SYSTEM` | `SystemContext` : **aucun champ d'organisation** | `OutboxPublisher`, `PartitionManager` |

Le coureur a démontré le besoin : ces deux cas d'usage n'étaient pas exprimables par `TransactionManager.atomic(ctx)` sans rendre `organization_id` optionnel, ce qui aurait permis une opération tenant-scoped sans tenant. La portée est fixée par le contrat, pas par l'appelant : une commande `REQUIRED` ne peut pas demander `SYSTEM`.

## 4. Application Contract V1 : les 119 cas d'usage

Légende : verrous `ressource:mode` (A consultatif, K clé d'idempotence, S FOR SHARE, U FOR NO KEY UPDATE, G UPDATE gardé, I INSERT) dans l'ordre d'acquisition ; reprise = fondement de la règle (TD30 commandes, TD35 handlers, TD43 travaux, TD31 travailleurs). Nature : 51 command, 28 handler, 19 job, 12 service, 8 system, 4 worker.

### 4.1 `platform`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `StoreIdempotencyKey` | `StoreIdempotencyKey` (interne) | niveau C | une | requise | UNIQUE (organisation, clé, route) | — | — | platform.idempotency | — | — | — | classes | celles de l'appelant | appelant | platform.idempotency |
| `PartitionManager` | `PartitionManager` (travail) | niveau C | une | aucune (SYSTEM) | IF NOT EXISTS | — | — | — | — | — | — | classes | OK, SKIPPED | TD43 | — |
| `TechnicalPurge` | `TechnicalPurge` (travail) | niveau C | une | énumérée | borne par date | — | — | — | — | — | — | classes | OK, SKIPPED | TD43 | — |

### 4.2 `events`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `OutboxPublisher` | `OutboxPublisher` (travail) | niveau C | trois : réclamer par bail ; chaque handler dans sa transaction ; poser publié | relais nommé (SYSTEM) | bail + reçus | advisory:A | — | events.publication, events.receipts | — | — | — | classes | OK, RETRYING, DEFERRED | TD31 | par phase : T1 claim (events) → T2 effect (*) → T3 finalize (events) |
| `ReplayDeadEvent` | `ReplayDeadEvent` (publique) | figée : event_id, handler_name | une | requise | clé d'idempotence | idempotency_keys:K → event_receipts:U | — | events.receipts | — | — | requis | classes | OK, REPLAY | TD30 | events.receipts + audit + clé d'idempotence |
| `EmitEvent` | `EmitEvent` (interne) | niveau C | une | requise | suit le cas d usage | — | — | events.publication | — | — | — | 3 codes | celles de l'appelant | appelant | events.publication |

### 4.3 `audit`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `AnonymizeAuditLogs` | `AnonymizeAuditLogs` (interne) | niveau C | une | requise | colonnes before, after, reason seulement | — | — | audit.log | — | — | requis | classes | OK, SKIPPED | garde | audit.log + audit |
| `WriteAuditLog` | `WriteAuditLog` (interne) | niveau C | une | requise | dans la transaction | — | — | audit.log | — | — | — | classes | celles de l'appelant | appelant | audit.log |

### 4.4 `identity`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `CreateUser` | `CreateUser` (publique) | niveau C | une | requise | e-mail unique | idempotency_keys:K → identity_members:U | — | identity.user | — | USER_CREATED | requis | classes | OK, REPLAY | TD30 | identity.user + événements + audit + clé d'idempotence |
| `ChangeUserStatus` | `ChangeUserStatus` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → identity_members:U | — | identity.user | — | USER_STATUS_CHANGED | requis | classes | OK, REPLAY | TD30 | identity.user + événements + audit + clé d'idempotence |
| `AddMember` | `AddMember` (publique) | niveau C | une | requise | unicité (organisation, utilisateur) | idempotency_keys:K → identity_members:U | — | identity.membership | — | MEMBER_ADDED | requis | classes | OK, REPLAY | TD30 | identity.membership + événements + audit + clé d'idempotence |
| `ProvisionOwnerMembership` | `ProvisionOwnerMembership` (étape) | niveau C | une | requise | (organisation, étape) | identity_members:I | — | identity.membership | implémente:organizations.ProvisioningStep | MEMBER_ADDED | — | classes | celles de l'appelant | appelant | identity.membership + événements |
| `ChangeMemberRole` | `ChangeMemberRole` (publique) | niveau C | une | requise | version | idempotency_keys:K → identity_members:U | — | identity.membership | — | MEMBER_ROLE_CHANGED | requis | classes | OK, REPLAY | TD30 | identity.membership + événements + audit + clé d'idempotence |
| `RemoveMember` | `RemoveMember` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → identity_members:U | — | identity.membership | — | MEMBER_REMOVED | requis | classes | OK, REPLAY | TD30 | identity.membership + événements + audit + clé d'idempotence |
| `AnonymizeUser` | `AnonymizeUser` (interne) | niveau C | une | requise | anonymized_at ; audit PII_ANONYMIZED | idempotency_keys:K → identity_members:U | — | identity.user | — | — | requis | classes | OK, SKIPPED | garde | identity.user + audit |

### 4.5 `organizations`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `CreateOrganization` | `CreateOrganization` (publique) | niveau C | une par étape (plan de provisioning) | créée (NEW) | clé d'idempotence | idempotency_keys:K → organizations:I | — | organizations.record, organizations.settings, organizations.status | own:organizations.ProvisioningStep | — | requis | classes | OK, REPLAY | TD30 | par phase : T1 write (organizations) → T2 effect (identity, automation, billing) → T3 finalize (organizations) |
| `CompleteProvisioning` | `CompleteProvisioning` (interne) | niveau C | une | requise | garde d'état PROVISIONING → ACTIVE | organizations:G | — | organizations.status | — | ORGANIZATION_CREATED | — | classes | OK, SKIPPED | garde | organizations.status + événements |
| `ResumeProvisioning` | `ResumeProvisioning` (travail) | niveau C | une | énumérée | idempotence par étape | — | — | — | own:organizations.ProvisioningStep | — | — | classes | OK, SKIPPED | TD43 | par phase : T1 effect (identity, automation, billing) → T2 finalize (organizations) |
| `UpdateOrganization` | `UpdateOrganization` (publique) | niveau C | une | requise | version | idempotency_keys:K → organizations:U | — | organizations.record | — | ORGANIZATION_UPDATED | requis | classes | OK, REPLAY | TD30 | organizations.record + événements + audit + clé d'idempotence |
| `ChangeOrgSettings` | `ChangeOrgSettings` (publique) | niveau C | une | requise | version | idempotency_keys:K → organizations:U | — | organizations.settings | — | ORG_SETTINGS_CHANGED | requis | classes | OK, REPLAY | TD30 | organizations.settings + événements + audit + clé d'idempotence |
| `SuspendOrganization` | `SuspendOrganization` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → organizations:U | — | organizations.status | — | ORGANIZATION_SUSPENDED | requis | classes | OK, REPLAY | TD30 | organizations.status + événements + audit + clé d'idempotence |
| `ReactivateOrganization` | `ReactivateOrganization` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → organizations:U | — | organizations.status | — | ORGANIZATION_REACTIVATED | requis | classes | OK, REPLAY | TD30 | organizations.status + événements + audit + clé d'idempotence |
| `CloseOrganization` | `CloseOrganization` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → organizations:U | — | organizations.status | — | ORGANIZATION_CLOSED | requis | classes | OK, REPLAY | TD30 | organizations.status + événements + audit + clé d'idempotence |

### 4.6 `customers`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `CreateCustomer` | `CreateCustomer` (publique) | niveau C | une | requise | external_ref unique | idempotency_keys:K → customers:U | — | customers.record | — | CUSTOMER_CREATED | requis | classes | OK, REPLAY | TD30 | customers.record + événements + audit + clé d'idempotence |
| `UpdateCustomer` | `UpdateCustomer` (publique) | niveau C | une | requise | version | idempotency_keys:K → customers:U | — | customers.record | — | CUSTOMER_UPDATED | requis | classes | OK, REPLAY | TD30 | customers.record + événements + audit + clé d'idempotence |
| `DeactivateCustomer` | `DeactivateCustomer` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → customers:U | — | customers.status | — | CUSTOMER_DEACTIVATED | requis | classes | OK, REPLAY | TD30 | customers.status + événements + audit + clé d'idempotence |
| `ArchiveCustomer` | `ArchiveCustomer` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → customers:U | — | customers.status | — | CUSTOMER_ARCHIVED | requis | classes | OK, REPLAY | TD30 | customers.status + événements + audit + clé d'idempotence |
| `ReactivateCustomer` | `ReactivateCustomer` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → customers:U | — | customers.status | — | CUSTOMER_REACTIVATED | requis | classes | OK, REPLAY | TD30 | customers.status + événements + audit + clé d'idempotence |
| `AddCustomerContact` | `AddCustomerContact` (publique) | niveau C | une | requise | unicité contact actif | idempotency_keys:K → customers:U | — | customers.record | — | CUSTOMER_CONTACT_ADDED | requis | classes | OK, REPLAY | TD30 | customers.record + événements + audit + clé d'idempotence |
| `UpdateCustomerContact` | `UpdateCustomerContact` (publique) | niveau C | une | requise | version | idempotency_keys:K → customers:U | — | customers.record | — | CUSTOMER_CONTACT_UPDATED | requis | classes | OK, REPLAY | TD30 | customers.record + événements + audit + clé d'idempotence |
| `AnonymizeCustomer` | `AnonymizeCustomer` (interne) | niveau C | une | requise | anonymized_at ; audit PII_ANONYMIZED | customers:U | — | customers.record | — | — | requis | classes | OK, SKIPPED | garde | customers.record + audit |

### 4.7 `invoices`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `CreateInvoice` | `CreateInvoice` (publique) | niveau C | une | requise | clé d'idempotence | idempotency_keys:K → customers:S → invoices:I | customers.CustomerFacts, organizations.OrgStatus | invoices.body | — | INVOICE_CREATED | requis | 4 codes | OK, REPLAY | TD30 | invoices.body + événements + audit + clé d'idempotence |
| `IssueInvoice` | `IssueInvoice` (publique) | figée : invoice_id | une | requise | garde d'état | idempotency_keys:K → customers:S → invoices:U | customers.CustomerFacts, organizations.OrgStatus | invoices.lifecycle, invoices.collection_cycle | — | INVOICE_ISSUED, INVOICE_DUE_SOON, INVOICE_DUE, INVOICE_OVERDUE | requis | 7 codes | OK, REPLAY | TD30 | invoices.lifecycle + invoices.collection_cycle + événements + audit + clé d'idempotence |
| `CancelInvoice` | `CancelInvoice` (publique) | figée : invoice_id, reason_code | une | requise | garde d'état | invoices:G | — | invoices.lifecycle | — | INVOICE_CANCELLED | requis | 1 codes | OK, REPLAY | TD30 | invoices.lifecycle + événements + audit |
| `VoidInvoice` | `VoidInvoice` (publique) | figée : invoice_id, reason_code | une | requise | garde d'état | invoices:G | — | invoices.lifecycle | — | INVOICE_VOIDED | requis | 3 codes | OK, REPLAY | TD30 | invoices.lifecycle + événements + audit |
| `OpenInvoiceDispute` | `OpenInvoiceDispute` (publique) | niveau C | une | requise | clé d'idempotence | idempotency_keys:K → invoices:U → invoice_disputes:U | — | invoices.dispute | — | INVOICE_DISPUTED | requis | 4 codes | OK, REPLAY | TD30 | invoices.dispute + événements + audit + clé d'idempotence |
| `ResolveInvoiceDispute` | `ResolveInvoiceDispute` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → invoices:U → invoice_disputes:U | — | invoices.dispute | — | INVOICE_DISPUTE_RESOLVED | requis | 1 codes | OK, REPLAY | TD30 | invoices.dispute + événements + audit + clé d'idempotence |
| `InvoiceLifecycleScan` | `InvoiceLifecycleScan` (travail) | niveau C | une par facture | énumérée | UPDATE … WHERE état = ancien | invoices:G | organizations.OrgStatus | invoices.lifecycle, invoices.collection_cycle | — | INVOICE_DUE_SOON, INVOICE_DUE, INVOICE_OVERDUE | — | classes | OK, SKIPPED | TD43 | invoices.lifecycle + invoices.collection_cycle + événements |
| `ApplySettlement` | `ApplySettlement` (interne) | niveau C | une | requise | dans la transaction de l'appelant | idempotency_keys:K → payments:U → invoices:U | organizations.OrgStatus | invoices.settlement, invoices.collection_cycle, invoices.lifecycle | — | INVOICE_PARTIALLY_PAID, INVOICE_PAID, INVOICE_SETTLEMENT_REVERTED, INVOICE_DUE_SOON, INVOICE_DUE, INVOICE_OVERDUE | — | classes | celles de l'appelant | appelant | invoices.settlement + invoices.collection_cycle + invoices.lifecycle + événements |

### 4.8 `payments`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `CreatePayment` | `CreatePayment` (publique) | niveau C | une | requise | clé d'idempotence | idempotency_keys:K → customers:S → payments:I | customers.CustomerFacts, organizations.OrgStatus | payments.record | — | PAYMENT_CREATED | requis | 5 codes | OK, REPLAY | TD30 | payments.record + événements + audit + clé d'idempotence |
| `AllocatePayment` | `AllocatePayment` (publique) | figée : payment_id, allocations | une | requise | clé d'idempotence | idempotency_keys:K → payments:U → invoices:U | invoices.InvoiceFacts, organizations.OrgStatus | payments.allocations, payments.allocated, invoices.settlement, invoices.collection_cycle | invoices.ApplySettlement | PAYMENT_ALLOCATED | requis | 8 codes | OK, REPLAY | TD30 | payments.allocations + payments.allocated + invoices.settlement + invoices.collection_cycle + événements + audit + clé d'idempotence |
| `ReverseAllocation` | `ReverseAllocation` (publique) | figée : allocation_id, amount_minor, reason | une | requise | clé d'idempotence | idempotency_keys:K → payments:U → invoices:U | organizations.OrgStatus | payments.allocations, payments.allocated, invoices.settlement, invoices.collection_cycle, invoices.lifecycle | invoices.ApplySettlement | PAYMENT_ALLOCATION_REVERSED | requis | 4 codes | OK, REPLAY | TD30 | payments.allocations + payments.allocated + invoices.settlement + invoices.collection_cycle + invoices.lifecycle + événements + audit + clé d'idempotence |
| `ReversePayment` | `ReversePayment` (publique) | figée : payment_id, reason_code, reason | une | requise | clé d'idempotence | idempotency_keys:K → payments:U → invoices:U | organizations.OrgStatus | payments.allocations, payments.allocated, invoices.settlement, invoices.collection_cycle, invoices.lifecycle | invoices.ApplySettlement | PAYMENT_REVERSED, PAYMENT_ALLOCATION_REVERSED | requis | 4 codes | OK, REPLAY | TD30 | payments.allocations + payments.allocated + invoices.settlement + invoices.collection_cycle + invoices.lifecycle + événements + audit + clé d'idempotence |

### 4.9 `promises`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `CreatePromise` | `CreatePromise` (publique) | niveau C | une | requise | clé d'idempotence | idempotency_keys:K → customers:S → invoices:S → promises:I | — | promises.status | — | PROMISE_CREATED | requis | classes | OK, REPLAY | TD30 | promises.status + événements + audit + clé d'idempotence |
| `CancelPromise` | `CancelPromise` (publique) | niveau C | une | requise | garde d'état | promises:U | — | promises.status | — | PROMISE_CANCELLED | requis | classes | OK, REPLAY | TD30 | promises.status + événements + audit |
| — | `FulfillPromiseOnInvoicePaid` (réaction) | événements | une | de l'événement | reçu | promises:U | — | promises.status | — | PROMISE_FULFILLED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | promises.status + événements + reçu |
| — | `FulfillPromiseOnAllocation` (réaction) | événements | une | de l'événement | reçu | promises:U | — | promises.status | — | PROMISE_FULFILLED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | promises.status + événements + reçu |
| — | `CancelPromiseOnInvoiceEnded` (réaction) | événements | une | de l'événement | reçu | promises:U | — | promises.status | — | PROMISE_CANCELLED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | promises.status + événements + reçu |
| — | `CancelPromiseOnCustomerArchived` (réaction) | événements | une | de l'événement | reçu | promises:U | — | promises.status | — | PROMISE_CANCELLED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | promises.status + événements + reçu |
| `PromiseBreachScan` | `PromiseBreachScan` (travail) | niveau C | une | énumérée | UPDATE … WHERE état = ancien | promises:U | — | promises.status | — | PROMISE_BROKEN | — | classes | OK, SKIPPED | TD43 | promises.status + événements |

### 4.10 `imports`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `UploadImportBatch` | `UploadImportBatch` (publique) | niveau C | une | requise | file_hash unique | import_batches:G | — | imports.batch | — | IMPORT_BATCH_UPLOADED | requis | classes | OK, REPLAY | TD30 | imports.batch + événements + audit |
| — | `ValidateImportBatch` (réaction) | événements | une | de l'événement | garde d'état | import_batches:G → event_receipts:I | — | imports.batch | — | IMPORT_BATCH_READY, IMPORT_BATCH_FAILED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | imports.batch + événements + reçu |
| `ApproveImportBatch` | `ApproveImportBatch` (publique) | niveau C | une | requise | garde d'état | import_batches:G | — | imports.batch | — | IMPORT_BATCH_APPROVED | requis | classes | OK, REPLAY | TD30 | imports.batch + événements + audit |
| `CommitImportBatch` | `CommitImportBatch` (publique) | niveau C | une | requise | garde d'état | import_batches:G | — | imports.batch | — | IMPORT_BATCH_COMMITTED | requis | classes | OK, REPLAY | TD30 | imports.batch + événements + audit |
| `CancelImportBatch` | `CancelImportBatch` (publique) | niveau C | une | requise | garde d'état | import_batches:G | — | imports.batch | — | IMPORT_BATCH_CANCELLED | requis | classes | OK, REPLAY | TD30 | imports.batch + événements + audit |
| — | `NormalizeImportBatch` (réaction) | événements | une | de l'événement | garde d'état COMMITTED → NORMALIZING | import_batches:U → customers:I → payments:I → invoices:I → event_receipts:I | — | imports.batch, customers.record, invoices.body, invoices.lifecycle, invoices.settlement, payments.record, payments.allocations, payments.allocated | customers.CreateCustomer, invoices.CreateInvoice, payments.CreatePayment, payments.AllocatePayment | IMPORT_BATCH_NORMALIZED, IMPORT_BATCH_FAILED, RISK_RECALCULATION_REQUESTED, PRIORITY_RECALCULATION_REQUESTED, CASHFLOW_RECALCULATION_REQUESTED | — | 2 codes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | imports.batch + customers.record + invoices.body + invoices.lifecycle + invoices.settlement + payments.record + payments.allocations + payments.allocated + événements + reçu |
| — | `StartImportRelease` (réaction) | événements | une | de l'événement | garde d'état NORMALIZED → RELEASING | import_batches:G → event_receipts:I | — | imports.batch | — | — | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | imports.batch + reçu |
| `CompleteImportRelease` | `CompleteImportRelease` (interne) | niveau C | une | requise | garde d'état RELEASING → RELEASED | import_batches:G | — | imports.batch | — | IMPORT_BATCH_RELEASED | — | classes | OK, SKIPPED | garde | imports.batch + événements |
| `PurgeImportStaging` | `PurgeImportStaging` (travail) | niveau C | une | énumérée | borne par date | import_batches:G | — | imports.batch | — | — | — | classes | OK, SKIPPED | TD43 | imports.batch |

### 4.11 `risk`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| — | `RequestRiskRecalc` (réaction) | événements | une | de l'événement | regroupement par cible | — | — | — | — | RISK_RECALCULATION_REQUESTED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | événements + reçu |
| — | `RecomputeRisk` (réaction) | événements | une | de l'événement | input_hash | advisory:A → projections:U → event_receipts:I | invoices.EverIssuedOfCustomer, invoices.OpenInvoicesOfCustomer, invoices.SettledInvoicesOfCustomer, organizations.CalendarReader, organizations.OrgSettings, payments.ReversedPaymentsOfCustomer, promises.BrokenPromisesOfCustomer | risk.profile | — | RISK_CHANGED | — | 2 codes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | risk.profile + événements + reçu |
| `RequestDailyRiskRefresh` | `RequestDailyRiskRefresh` (travail) | niveau C | une | énumérée | regroupement par cible | — | — | — | — | RISK_RECALCULATION_REQUESTED | — | classes | OK, SKIPPED | TD43 | événements |

### 4.12 `priority`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| — | `RequestPriorityRecalc` (réaction) | événements | une | de l'événement | regroupement par cible | — | — | — | — | PRIORITY_RECALCULATION_REQUESTED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | événements + reçu |
| — | `RecomputePriority` (réaction) | événements | une | de l'événement | input_hash | advisory:A → projections:U → event_receipts:I | collection.CollectionFacts, invoices.InvoiceFacts, organizations.OrgSettings, promises.PromiseFacts, risk.RiskLevel | priority.item | — | PRIORITY_CHANGED | — | 2 codes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | priority.item + événements + reçu |
| `RequestDailyPriorityRefresh` | `RequestDailyPriorityRefresh` (travail) | niveau C | une | énumérée | regroupement par cible | — | — | — | — | PRIORITY_RECALCULATION_REQUESTED | — | classes | OK, SKIPPED | TD43 | événements |

### 4.13 `cashflow`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| — | `RequestCashflowRecalc` (réaction) | événements | une | de l'événement | portée : organisation ; horizons 30 et 90 jours, scénario BASE ; regroupement 5 min (Cashflow §4.8) ; ORG_SETTINGS_CHANGED filtré sur CASHFLOW_ORG_SETTINGS_RELEVANT | — | — | — | — | CASHFLOW_RECALCULATION_REQUESTED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | événements + reçu |
| — | `RunCashflow` (réaction) | événements | une | de l'événement | input_hash + promotion monotone | advisory:A → projections:U → event_receipts:I | — | cashflow.run | — | CASHFLOW_UPDATED | — | 2 codes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | cashflow.run + événements + reçu |
| `CashflowScheduler` | `CashflowScheduler` (travail) | niveau C | une | énumérée | input_hash | — | — | — | — | CASHFLOW_RECALCULATION_REQUESTED | — | classes | OK, SKIPPED | TD43 | événements |

### 4.14 `approvals`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `RequestApproval` | `RequestApproval` (interne) | figée : target, kind, reason, context, expires_at, requested_from_user, requested_role | une | requise | par cible et étape | approvals:I | — | approvals.status | approvals.ApprovalTargetReader | APPROVAL_REQUESTED | — | classes | celles de l'appelant | appelant | approvals.status + événements |
| `DecideApproval` | `DecideApproval` (publique) | figée : approval_id, decision, comment | une | requise | une seule décision | idempotency_keys:K → approvals:U | — | approvals.status | approvals.ApprovalTargetReader | APPROVAL_GRANTED, APPROVAL_REJECTED | requis | 4 codes | OK, REPLAY | TD30 | approvals.status + événements + audit + clé d'idempotence |
| `ApprovalExpiryScan` | `ApprovalExpiryScan` (travail) | niveau C | une | énumérée | UPDATE … WHERE état = ancien | approvals:G | — | approvals.status | approvals.ApprovalTargetReader | — | — | classes | OK, SKIPPED | TD43 | approvals.status |

### 4.15 `collection`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `CreateCollectionAction` | `CreateCollectionAction` (publique) | figée : subject, type, channel, execution_id, step_id | une par module propriétaire : action, puis approbation, puis transition | requise | dedup_key | idempotency_keys:K → collection_actions:I | rules.Evaluate | collection.action_status | — | COLLECTION_ACTION_PROPOSED, COLLECTION_ACTION_SUPPRESSED | conditionnel | 4 codes | OK, REPLAY, SKIPPED, DEFERRED | TD30 | par phase : T1 write (collection) → T2 effect (collection) |
| `AdvanceProposedAction` | `AdvanceProposedAction` (interne) | niveau C | une | requise | garde d'état PROPOSED | collection_actions:U | organizations.CalendarReader, organizations.OrgSettings, rules.Evaluate | collection.action_status | own:approvals.RequestApproval | COLLECTION_ACTION_SCHEDULED, COLLECTION_ACTION_SUPPRESSED | — | classes | OK, SKIPPED | garde | par phase : T1 effect (approvals) → T2 finalize (collection) |
| `ResumeProposedActions` | `ResumeProposedActions` (travail) | niveau C | une | énumérée | garde d'état PROPOSED | collection_actions:U | — | collection.action_status | — | — | — | classes | OK, SKIPPED | TD43 | par phase : T1 effect (collection) |
| `CreateManualAction` | `CreateManualAction` (publique) | figée : subject, type, level, channel, override_grants | une par module propriétaire | requise | manual:{clé} | idempotency_keys:K → collection_actions:I | rules.Evaluate | collection.action_status | — | COLLECTION_ACTION_PROPOSED, COLLECTION_ACTION_SUPPRESSED | requis | 8 codes | OK, REPLAY, SKIPPED, DEFERRED | TD30 | par phase : T1 write (collection) → T2 effect (collection) |
| `AuthorizeOverride` | `AuthorizeOverride` (interne) | figée : action_ref, exception_code, reason_code, reason_text | une | requise | sans effet propre ; audit à la création puis à chaque vérification | — | — | — | — | — | requis | 4 codes | celles de l'appelant | appelant | audit |
| `CancelCollectionAction` | `CancelCollectionAction` (publique) | niveau C | une | requise | garde d'état | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_CANCELLED | requis | classes | OK, REPLAY, SKIPPED | TD30 | collection.action_status + événements + audit |
| `ClaimTask` | `ClaimTask` (publique) | niveau C | une | requise | une seule réclamation gagne (UPDATE … WHERE assigned_to IS NULL) | collection_actions:G | — | collection.action_status | — | — | requis | classes | OK, REPLAY | TD30 | collection.action_status + audit |
| `CompleteTask` | `CompleteTask` (publique) | niveau C | une | requise | garde d'état | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_EXECUTED | requis | classes | OK, REPLAY, SKIPPED | TD30 | collection.action_status + événements + audit |
| `RescheduleAction` | `RescheduleAction` (publique) | niveau C | une | requise | garde d'état | collection_actions:G | organizations.CalendarReader, organizations.OrgSettings | collection.action_status | — | — | requis | classes | OK, REPLAY | TD30 | collection.action_status + audit |
| `ExecuteDueAction` | `ExecuteDueAction` (travail) | figée : action_id | claim + revalidation ; notification ; envoi hors transaction ; résultat | requise | claim gardé | collection_actions:U | rules.Evaluate | collection.action_status, collection.attempts | own:notifications.CreateNotification | COLLECTION_ACTION_SUPPRESSED | conditionnel | 1 codes | OK, RETRYING, DEFERRED | TD31 | par phase : T1 claim (collection) → T2 effect (notifications) → T3 external → T4 finalize (collection) |
| `ReapActions` | `ReapActions` (travail) | niveau C | une | énumérée | transition gardée | collection_actions:G | — | collection.action_status, collection.attempts | — | — | — | classes | OK, SKIPPED | TD43 | collection.action_status + collection.attempts |
| — | `SuppressOnInvoicePaid` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_SUPPRESSED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + événements + reçu |
| — | `SuppressOnInvoiceEnded` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_SUPPRESSED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + événements + reçu |
| — | `SuppressOnInvoiceDisputed` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | invoices.InvoiceFacts | collection.action_status | — | COLLECTION_ACTION_SUPPRESSED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + événements + reçu |
| — | `SuppressOnPromiseCreated` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_SUPPRESSED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + événements + reçu |
| — | `SuppressOnHoldPlaced` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_SUPPRESSED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + événements + reçu |
| — | `SuppressOnCustomerInactive` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_SUPPRESSED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + événements + reçu |
| — | `SuppressOnOrgSuspended` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_SUPPRESSED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + événements + reçu |
| — | `OnApprovalDecided` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | — | collection.action_status | — | COLLECTION_ACTION_SCHEDULED, COLLECTION_ACTION_CANCELLED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + événements + reçu |
| — | `OnNotificationResult` (réaction) | événements | une | de l'événement | reçu | collection_actions:U → event_receipts:I | — | collection.action_status, collection.attempts | — | COLLECTION_ACTION_EXECUTED, COLLECTION_ACTION_FAILED, COLLECTION_ACTION_SCHEDULED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | collection.action_status + collection.attempts + événements + reçu |
| `PlaceHold` | `PlaceHold` (publique) | niveau C | une | requise | clé d'idempotence + EXCLUDE | idempotency_keys:K → collection_holds:I | — | collection.hold_status | — | COLLECTION_HOLD_PLACED | requis | classes | OK, REPLAY | TD30 | collection.hold_status + événements + audit + clé d'idempotence |
| `ReleaseHold` | `ReleaseHold` (publique) | niveau C | une | requise | garde d'état | collection_holds:G | — | collection.hold_status | — | COLLECTION_HOLD_RELEASED | requis | classes | OK, REPLAY, SKIPPED | TD30 | collection.hold_status + événements + audit |
| `HoldExpiryScan` | `HoldExpiryScan` (travail) | niveau C | une | énumérée | UPDATE … WHERE état = ancien | collection_holds:G | — | collection.hold_status | — | COLLECTION_HOLD_RELEASED | — | classes | OK, SKIPPED | TD43 | collection.hold_status + événements |
| `ScanReconciliationReviews` | `ScanReconciliationReviews` (travail) | niveau C | par organisation | énumérée | dedup_key | — | — | — | own:notifications.CreateNotification | — | — | classes | OK, SKIPPED | TD43 | par phase : T1 effect (notifications) |
| `ReadApprovalTarget` | `ReadApprovalTarget` (interne) | niveau C | une | requise | lecture seule | — | — | — | implémente:approvals.ApprovalTargetReader | — | — | classes | celles de l'appelant | appelant | — |

### 4.16 `notifications`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `CreateNotification` | `CreateNotification` (interne) | niveau C | une | requise | dedup_key | notifications:I | — | notifications.status | — | NOTIFICATION_CREATED | — | classes | celles de l'appelant | appelant | notifications.status + événements |
| `HandleSendResult` | `HandleSendResult` (travail) | figée : notification_id, attempt_no, result | une, hors envoi | requise | (notification_id, attempt_no) | notifications:U | — | notifications.status | — | NOTIFICATION_SENT, NOTIFICATION_FAILED | — | classes | OK, RETRYING, DEFERRED | TD31 | notifications.status + événements |
| — | `NotifyApprovers` (réaction) | événements | une | de l'événement | dedup_key | notifications:I → event_receipts:I | — | notifications.status | — | NOTIFICATION_CREATED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | notifications.status + événements + reçu |
| `CleanNotificationPayloads` | `CleanNotificationPayloads` (interne) | niveau C | une | requise | anonymized_at | notifications:U | — | notifications.status | — | — | — | classes | OK, SKIPPED | garde | notifications.status |

### 4.17 `automation`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ProvisionDefaultAutomations` | `ProvisionDefaultAutomations` (étape) | niveau C | une | requise | (organisation, étape) | automations:I | — | automation.definition | implémente:organizations.ProvisioningStep | AUTOMATION_CREATED | — | classes | celles de l'appelant | appelant | automation.definition + événements |
| `ReadApprovalTarget` | `ReadApprovalTarget` (interne) | niveau C | une | requise | lecture seule | — | — | — | implémente:approvals.ApprovalTargetReader | — | — | classes | celles de l'appelant | appelant | — |
| `CreateAutomation` | `CreateAutomation` (publique) | niveau C | une | requise | clé d'idempotence | idempotency_keys:K → automations:U | — | automation.definition | — | AUTOMATION_CREATED | requis | classes | OK, REPLAY | TD30 | automation.definition + événements + audit + clé d'idempotence |
| `CreateAutomationVersion` | `CreateAutomationVersion` (publique) | niveau C | une | requise | version | idempotency_keys:K → automations:U | — | automation.definition | — | AUTOMATION_VERSION_CREATED | requis | classes | OK, REPLAY | TD30 | automation.definition + événements + audit + clé d'idempotence |
| `ActivateAutomation` | `ActivateAutomation` (publique) | figée : version_id, enrollment_mode, preview | une | requise | garde d'état + empreinte | idempotency_keys:K → automations:U → automation_executions:I | — | automation.definition, automation.execution | — | AUTOMATION_ACTIVATED | requis | 4 codes | OK, REPLAY | TD30 | automation.definition + automation.execution + événements + audit + clé d'idempotence |
| `PauseAutomation` | `PauseAutomation` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → automations:U | — | automation.definition | — | AUTOMATION_PAUSED | requis | 1 codes | OK, REPLAY | TD30 | automation.definition + événements + audit + clé d'idempotence |
| `DisableAutomation` | `DisableAutomation` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → automations:U | — | automation.definition | — | AUTOMATION_DISABLED | requis | classes | OK, REPLAY | TD30 | automation.definition + événements + audit + clé d'idempotence |
| `ArchiveAutomation` | `ArchiveAutomation` (publique) | niveau C | une | requise | garde d'état | idempotency_keys:K → automations:U | — | automation.definition | — | AUTOMATION_ARCHIVED | requis | classes | OK, REPLAY | TD30 | automation.definition + événements + audit + clé d'idempotence |
| — | `DispatchEvent` (réaction) | événements | une | de l'événement | trigger_key = event:{id} | automation_executions:I → event_receipts:I | — | automation.execution | — | — | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | automation.execution + reçu |
| `ScanTimeTriggers` | `ScanTimeTriggers` (travail) | niveau C | une | énumérée | trigger_key temporel | automation_executions:I → event_receipts:I | — | automation.execution | — | — | — | classes | OK, SKIPPED | TD43 | automation.execution |
| `RunExecutionStep` | `RunExecutionStep` (travail) | figée : execution_id | trois : réclamer, effet dans la transaction du module propriétaire, enregistrer | requise | effets idempotents + garde d'état | automation_executions:U | rules.Evaluate | automation.execution | own:collection.CreateCollectionAction, own:notifications.CreateNotification, own:approvals.RequestApproval | AUTOMATION_EXECUTION_STARTED, AUTOMATION_EXECUTION_COMPLETED, AUTOMATION_EXECUTION_FAILED, RISK_RECALCULATION_REQUESTED, PRIORITY_RECALCULATION_REQUESTED, CASHFLOW_RECALCULATION_REQUESTED | — | 1 codes | OK, RETRYING, DEFERRED | TD31 | par phase : T1 claim (automation) → T2 effect (collection, notifications, approvals) → T3 finalize (automation) |
| — | `PauseOrCancelOnSubjectChange` (réaction) | événements | une | de l'événement | reçu | automation_executions:U → event_receipts:I | — | automation.execution | — | AUTOMATION_EXECUTION_CANCELLED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | automation.execution + événements + reçu |
| — | `OnAutomationPausedOrDisabled` (réaction) | événements | une | de l'événement | reçu | automation_executions:U → event_receipts:I | — | automation.execution | — | AUTOMATION_EXECUTION_CANCELLED | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | automation.execution + événements + reçu |
| — | `ResumeOnCauseLifted` (réaction) | événements | une | de l'événement | reçu | automation_executions:U → event_receipts:I | — | automation.execution | — | — | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | automation.execution + reçu |
| — | `OnApprovalDecidedForExecution` (réaction) | événements | une | de l'événement | reçu | automation_executions:U → event_receipts:I | — | automation.execution | — | — | — | classes | PROCESSED, SKIPPED, RETRYING, DEAD | TD35 | automation.execution + reçu |
| `ResumeReconciliationPaused` | `ResumeReconciliationPaused` (travail) | niveau C | par organisation | énumérée | garde d'état | automation_executions:U → event_receipts:I | rules.Evaluate | automation.execution | — | — | — | classes | OK, SKIPPED | TD43 | automation.execution |
| `ReleaseImportTranche` | `ReleaseImportTranche` (interne) | figée : batch_id | une par tranche | requise | trigger_key = import-release:… | automation_executions:I | imports.ImportReleaseFacts | automation.execution | — | — | — | 1 codes | OK, SKIPPED | garde | automation.execution |
| `ReapExecutions` | `ReapExecutions` (travail) | niveau C | une | énumérée | transition gardée | automation_executions:G | — | automation.execution | — | — | — | classes | OK, SKIPPED | TD43 | automation.execution |
| `RetryExecution` | `RetryExecution` (publique) | figée : execution_id | une | requise | trigger_key = retry:{id} | automation_executions:I → event_receipts:I | — | automation.execution | — | — | requis | 1 codes | OK, REPLAY | TD30 | automation.execution + audit |

### 4.18 `billing`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ProvisionTrialSubscription` | `ProvisionTrialSubscription` (étape) | niveau C | une | requise | (organisation, étape) | subscriptions:I | — | billing.subscription | implémente:organizations.ProvisioningStep | SUBSCRIPTION_CHANGED | — | classes | celles de l'appelant | appelant | billing.subscription + événements |

### 4.19 `jobs`

| Commande | Use case | Entrée | Transaction | Organisation | Idempotence | Verrous | Lectures | Domain | Inter-modules | Événements | Audit | Erreurs | Résultat | Reprise | Atomicité |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ImportReleaser` | `ImportReleaser` (travail) | niveau C | une par pas | énumérée | composition ; chaque pas est idempotent | — | automation.ReleaseProgress | — | own:automation.ReleaseImportTranche, own:imports.CompleteImportRelease | — | — | classes | OK, SKIPPED | TD43 | par phase : T1 effect (automation) → T2 effect (imports) |
| `ReconciliationWindowScan` | `ReconciliationWindowScan` (travail) | niveau C | une par pas | énumérée | composition ; chaque pas est idempotent | — | — | — | own:collection.ScanReconciliationReviews, own:automation.ResumeReconciliationPaused | — | — | classes | OK, SKIPPED | TD43 | par phase : T1 effect (collection) → T2 effect (automation) |

## 5. Ce que ce contrat ne fige pas encore

- **Entrées** : 18 cas d'usage sur 119 ont une charge utile figée (EC-xx) ; les autres sont « niveau C ». Elles se figeront avec le Domain, cas d'usage par cas d'usage, sans toucher aux registres.
- **Erreurs** : seuls 25 cas d'usage nomment des codes ; les autres n'ont que leurs classes.
- **Coureur et doubles en mémoire** : le pipeline §1 est décrit ici et non encore exécuté. Prochaine étape, avant Django : le coureur sans cadre logiciel avec des doubles en mémoire des ports du noyau, pour **exécuter** P1–P12 et faire échouer une échelle de verrous non respectée.
- **Persistance** : aucune table, aucune migration ; PostgreSQL n'est décrit que par les registres.

### 5.1 Ce que le coureur a démontré, et la suite

- **F1 et F2 tranchés le 2026-09-20** : portée de transaction `SYSTEM` explicite (K1, AP-15) et portée d'idempotence typée `ORGANIZATION` / `ACTOR` (K2, AP-14), sans rendre `organization_id` optionnel ni le remplacer par une valeur nulle. Amendements du noyau K1 et K2 (Module Contracts, §6.1) et amendement Application B1 (§6).
- **Défaut de dérivation corrigé (B1).** La portée d'idempotence se lisait dans le texte libre du registre (11 commandes) ; elle se lit dans l'opération de verrous, qui insère `K` : **38 commandes**. Le coureur l'a révélé en exécutant les 119 cas d'usage.
- **Schéma (étape PostgreSQL).** `idempotency_keys` devra accueillir l'exception `ACTOR` de TD32 (consigné en §13.2 du document d'architecture).

## 6. Gel et amendements

L'empreinte SHA-256 de `kernel/application.py`, `kernel/lock_registry.py` et des `specs.py` de chaque module est conservée dans `architecture_registry/application_freeze.json` ; `verify_application.py` échoue si elle diffère. Une modification n'est possible que par une ligne du journal ci-dessous et un `application_freeze.py --write` explicite.

| # | Date | Objet | Nature | Validé |
|---|---|---|---|---|
| B1 | 2026-09-20 | `UseCaseSpec.transaction_scope` (`TENANT` / `SYSTEM`, déduit du régime d'organisation, `SCOPE_OF_TENANT`) ; `idempotency_scope` typé `IdempotencyScope | None` (type déplacé au noyau, K2) et dérivé de la présence du verrou `K` : 38 commandes, non 11 ; clé d'idempotence dans la première phase des cas d'usage composés | donnée générée ; le coureur a démontré F1 (relais et partitions inexprimables), F2 (`CreateOrganization`) et l'erreur de dérivation de l'idempotence ; noyau K1 et K2 | oui, 2026-09-20 |
| B2 | 2026-09-20 | `CreateOrganization` : `transaction_scope` `NEW` (et non `TENANT`) ; `SCOPE_OF_TENANT[NEW]` = `NEW` | donnée générée ; étape 11 du coureur : le régime `NEW` est distinct de `TENANT` et de `SYSTEM` ; noyau K3 | oui, 2026-09-20 |
| B3 | 2026-09-21 | **B3-a** `ApplySettlement`, `ReverseAllocation` et `ReversePayment` écrivent `invoices.lifecycle` ; `ApplySettlement` émet `INVOICE_DUE_SOON` / `_DUE` / `_OVERDUE` : recalcul immédiat du cycle de vie après annulation d'un règlement (Invariants §3.1) ; **B3-b** lectures déclarées : `OrgStatus`, `CustomerFacts`, `InvoiceFacts` pour `CreateInvoice`, `IssueInvoice`, `InvoiceLifecycleScan`, `ApplySettlement`, `CreatePayment`, `AllocatePayment`, `ReverseAllocation`, `ReversePayment` ; **B3-c** erreurs déclarées de la tranche Facture / Paiement ; catalogue : 4 codes de litige (Invariants §3.3) et `INVOICE_HAS_OPEN_DISPUTE` (T15), soit 109 codes | donnée générée ; Domain V1 tranche 1 (§11, V1 à V3) : les gardes gelées exigeaient des écritures, des lectures et des codes que les registres ne déclaraient pas. Aucune règle métier nouvelle ; défaut du générateur d'Annexe A corrigé | oui, 2026-09-21 |
| B4 | 2026-09-21 | **B4-a** `IssueInvoice` et `InvoiceLifecycleScan` écrivent `invoices.collection_cycle` (règle (a) des Invariants §3.1 bis : `+ 1` dans la transaction de la transition vers `OVERDUE`) ; **B4-b** `ReverseAllocation` et `ReversePayment` ne déclarent plus la lecture `invoices.InvoiceFacts` (DD23 : un reversal est autorisé quel que soit l'état de la facture) | donnée générée ; Domain V1 tranche 1 (§13, DV1-1 et DV1-2) : le Domain a révélé un état écrit non déclaré et une lecture déclarée inutilisée. Aucune règle métier, aucune modification de C12, des verrous ni des machines à états | oui, 2026-09-21 |
| B5 | 2026-09-22 | `RecomputeRisk` déclare ses 7 lectures (RD2.3/RD2.4) : `organizations.CalendarReader`, `organizations.OrgSettings` (nouvellement consommée par `risk`), `invoices.OpenInvoicesOfCustomer` (premier consommateur), `invoices.SettledInvoicesOfCustomer` et `invoices.EverIssuedOfCustomer` (nouvelles requêtes, module `invoices`), `payments.ReversedPaymentsOfCustomer` (nouvelle, module `payments`), `promises.BrokenPromisesOfCustomer` (nouvelle, module `promises`) ; retrait de `customers` des dépendances de `risk` (`risk-1.0` ne lit aucun fait client) | donnée générée ; Risk Domain V1 (RISK_DOMAIN_V1.md, DV2-1 à DV2-5, confirmées par `reference_model/risk_ref.py`) : les lectures déclarées correspondent exactement à la signature de `evaluate_risk`, ni plus ni moins. Aucune règle métier, aucune modification de `risk-1.0`, des seuils, de l'hystérésis ni de l'agrégation validée par la référence | oui, 2026-09-22 |
| B6 | 2026-09-23 | `RecomputePriority` déclare ses 5 lectures (PD2.2/PD2.3) : `organizations.OrgSettings` (`critical_amount_minor`, sans `CalendarReader` : `prio-1.0` ne calcule aucune fenêtre temporelle, PD2.3), `invoices.InvoiceFacts`, `risk.RiskLevel` (réutilisation pure de Risk, RP-E), `promises.PromiseFacts` (§ DV3-1, fournisseur potentiellement STUB), `collection.CollectionFacts` (§ DV3-2, idem) ; retrait de `customers` des dépendances de `priority` (`prio-1.0` ne lit aucun fait client, comme `risk` en B5) ; `payments` et `rules` restent déclarés (abonnement de `RequestPriorityRecalc` aux événements `payments.*` ; `priority` fait partie de `FACT_PROVIDERS`), bien qu'aucun des deux ne soit lu par `RecomputePriority` elle-même | donnée générée ; Priority Domain V1 (PRIORITY_DOMAIN_V1.md, PD2.2 à PD2.4, DV3-8, confirmé par `reference_model/priority_ref.py`) : les lectures déclarées correspondent exactement à la signature de `evaluate_priority`, ni plus ni moins. Aucune règle métier, aucune modification de `prio-1.0`, du barème, de l'hystérésis ni des plafonds validés par la référence | oui, 2026-09-23 |
| B7 | 2026-09-26 | `SuppressOnInvoiceDisputed` déclare la lecture `invoices.InvoiceFacts`, absente jusqu'ici (`reads=()`) | donnée générée ; passe Collection Domain V1 (matrice des 19 cas d'usage, DV4-8) : la règle de suspension (`COLLECTION_ENGINE_V1.md §12`, D1 — suspendre SSI `collectible_minor = 0`) dépend d'une donnée absente du payload de l'événement `INVOICE_DISPUTED` (`dispute_id`, `disputed_amount_minor?` seulement, `INVARIANTS_V1.md §10`) ; aucune dérivation locale n'est possible (`outstanding_minor` est également absent du payload). `invoices.InvoiceFacts` était déjà un module-level dependency déclaré de `collection` (`modules.py`, `deps`/`READS`) : seul `commands.py` (le `calls=` de ce cas d'usage précis) manquait. Aucune règle métier nouvelle, aucune modification du contrat `InvoiceFacts` (`collectible_minor` y existait déjà) | oui, 2026-09-26 |
| B8 | 2026-09-26 | Ajout de trois cas d'usage `collection` absents du registre malgré leur exigence par le corpus gelé (AUDIT-01) : `ClaimTask` (`assigned_to` renseigné, réclamation gardée `UPDATE … WHERE assigned_to IS NULL`), `CompleteTask` (`SCHEDULED → DONE`, acteur `USER` assigné ou membre du pool, `COLLECTION_ACTION_EXECUTED`), `RescheduleAction` (`scheduled_for` recalculé par `SlotCalculator`, garde `status ∈ {PROPOSED, SCHEDULED}`) ; conséquences techniques nécessaires, sans règle métier nouvelle : deux opérations de verrou ajoutées à `locks.py` (`ClaimTask`, `RescheduleAction`, mode `G` déjà existant sur la ressource déjà déclarée `collection_actions`) et une exception nominative et fermée à la convention de nommage `Complete*` dans `build_registry.py` (`CompleteTask` est un command `USER`, jamais un system/job, contrairement aux deux seuls précédents `CompleteProvisioning`/`CompleteImportRelease`) | donnée générée ; passe Collection Domain V1 (AUDIT-01, Phase 6B) : `ENGINE_CONTRACTS_V1.md §EC-11`, `STATE_MACHINES_V1.md §7/§8`, `COLLECTION_ENGINE_V1.md §7/§8.2/§13/§14`, `INVARIANTS_V1.md §7.1` exigeaient ces trois cas d'usage, absents de `commands.py` et de `verqia/collection/application/specs.py` ; aucune trace d'un report explicite (`COLLECTION_ENGINE_V1.md §17`). Réserves documentées et non closes par cet amendement (traçabilité, pas de règle inventée) : événement éventuel de `ClaimTask`/`RescheduleAction`, audit dédié au-delà du régime générique D3 des commands, erreur de créneau cible invalide pour `RescheduleAction` (AUDIT-01.a/.b/.c/.e/.f) | oui, 2026-09-26 |
| B9 | 2026-09-29 | `AdvanceProposedAction` (A2) et `RescheduleAction` (A12) déclarent les deux lectures qu'exige le `SlotCalculator` : `organizations.CalendarReader` (jours ouvrés et fériés, `org.is_business_day`) et `organizations.OrgSettings` (fenêtre de communication `comm_window_start`/`comm_window_end`, débit `extra.send_rate_per_hour`) ; `organizations.OrgSettings` ajoutée aux lectures de module de `collection` (`modules.py`), où seule `CalendarReader` figurait | donnée générée ; audit V3 de `COLLECTION_DOMAIN_V1.md` (BLOCKER-2) : `COLLECTION_ENGINE_V1.md` §7 énonce les règles de placement d'un créneau (jour ouvré, fenêtre de communication, lissage du débit) ; A2 les applique à la planification initiale et A12 à la replanification (« le nouveau créneau repasse par les mêmes règles »), mais aucun des deux cas d'usage ne déclarait la moindre lecture calendaire, et `organizations.OrgSettings` n'était déclarée nulle part pour `collection`. Même espèce d'écart que B5/B6 (lecture réelle du Domain non déclarée) : `priority` avait gagné `organizations.OrgSettings` en B6 pour `critical_amount_minor`. Aucune règle métier nouvelle, aucune modification d'un document gelé, aucun changement de machine à états ni de contrat de données | oui, 2026-09-29 |
| B10 | 2026-10-04 | `CancelCollectionAction` (A5), `CompleteTask` (A11) et `ReleaseHold` (B2) ajoutent `SKIPPED` à leurs issues (`OUTCOME_EXTRAS`) : rejouer la MÊME transition (A5 sur `CANCELLED`, A11 sur `DONE`, B2 sur `RELEASED`) est un no-op légitime, tandis qu'une transition réellement invalide reste l'erreur d'EC-11 (`ACTION_INVALID_TRANSITION`, `HOLD_NOT_ACTIVE`) | donnée générée ; DV5-2 bis, relevé en écrivant le Collection Domain : `ENGINE_CONTRACTS_V1.md` §5 (matrice d'idempotence) dit « Transition d'état | garde d'état en base | `SKIPPED` », alors que les issues par nature d'un `command` n'admettaient que `OK` et `REPLAY` ; ces trois commandes n'ont pas de clé d'idempotence (`idempotency_scope=None`), le coureur ne peut donc pas produire `REPLAY` pour elles. Même mécanisme que les issues supplémentaires d'A1/A4. Aucune règle métier nouvelle, aucun document gelé modifié | oui, 2026-10-04 |
| B11 | 2026-10-04 | `CreateCollectionAction` (A1) et `CreateManualAction` (A4) déclarent l'erreur `DEDUP_REPLAY_UNAVAILABLE` (`CONFLICT`, 409, retryable) : la contrainte de déduplication a établi le doublon, mais l'objet nécessaire au `REPLAY` n'est plus récupérable à la lecture de reprise (R12-O1, option B). Produite uniquement par le coureur dans l'unité de reprise, jamais par un Domain ; aucune nouvelle tentative automatique : l'appelant retente sur l'état courant | données générées ; amendement préalable de `ENGINE_CONTRACTS_V1.md` (Annexe A via `test_matrix/gen_errors.py`, EC-11, journal « Amendements après V1.1 », R12-B) ; catalogue : 110 codes ; classes d'erreurs d'A1/A4 inchangées (`CONFLICT` déjà déclarée) ; aucune règle métier nouvelle ; Domain, primitives et oracle inchangés ; voir `R12_O1_FICHE_B.md` | oui, 2026-10-04 |

