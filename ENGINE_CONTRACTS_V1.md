# VERQIA — Engine Contracts V1

Références : Data Contract V1.3 (figé), Invariants V1.2, State Machines V1, Rule Engine V1.1, Collection Engine V1.1, Automation Engine V1.1.
Statut : **V1.1 — EC1 à EC10 VALIDÉES**, avec cinq précisions de verrouillage (§10). Les amendements sont appliqués au contrat V1.3 et aux Invariants ; les précisions issues de la passe Risk / Priority / Cashflow (jobs de fraîcheur, `RunCashflow`, portée du hash) y sont intégrées (EC-03, EC-14, X17).

Objet : transformer les moteurs et les modules en **contrats d'interface** vérifiables : entrées, sorties, préconditions, invariants, erreurs, idempotence, transactions, événements, dépendances. C'est le dernier document avant la matrice de tests globale et l'architecture technique.

Périmètre : ce document fixe les **frontières**. Il ne spécifie pas les modèles de score de Risk / Priority ni les prévisions de Cashflow : leurs contrats d'interface (§4, EC-14) sont posés, leurs calculs viennent dans leurs passes propres.

---

## 0. Conventions

### 0.1 Gabarit d'un contrat

Chaque contrat précise : **Rôle · Appelant → appelé · Entrée · Sortie · Préconditions · Postconditions et invariants · Erreurs · Idempotence · Transaction · Événements · Dépendances**.

### 0.2 Contexte d'appel (`CallContext`), obligatoire pour tout contrat

| Champ | Sens |
|---|---|
| `organization_id` | tenant ; **toujours** vérifié contre le sujet (jamais implicite) |
| `actor` | `{type: USER \| SYSTEM \| AUTOMATION, id?, role?}` |
| `correlation_id` | identifiant de la chaîne événement → exécution → action |
| `causation_id`, `causation_depth` | parent et profondeur (≤ 20) |
| `as_of` | instant d'évaluation, **injecté** par un port `Clock` de la couche Application ; jamais lu par le Domain |
| `idempotency_key` | présent sur toute commande exposée à un rejeu |

### 0.3 Issues d'un appel

| Issue | Sens | Exemple |
|---|---|---|
| `OK` | effet réalisé | action créée |
| `REPLAY` | déjà fait ; l'objet existant est renvoyé | même `dedup_key` |
| `SKIPPED` | rien à faire, légitimement | événement obsolète ; étape sans objet |
| `DEFERRED` | à refaire plus tard (`retry_at`) | hors fenêtre de communication |
| **erreur** | règle violée ou incident : `DomainError{code, classe, retryable, détails}` | `ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING` |

### 0.4 Classes d'erreur

| Classe | HTTP | Nouvelle tentative ? | Sens |
|---|---|---|---|
| `VALIDATION` | 400 / 422 | non | entrée mal formée ou définition invalide |
| `BUSINESS_RULE` | 422 | non | règle métier violée |
| `NOT_FOUND` | 404 | non | objet absent **ou d'une autre organisation** (jamais 403, pour ne pas révéler son existence) |
| `FORBIDDEN` | 403 | non | rôle insuffisant pour une commande dont l'objet est visible |
| `CONFLICT` | 409 | selon le code | état incompatible, version, unicité |
| `RATE_LIMITED` | 429 | oui, plus tard | limite de sécurité atteinte |
| `TRANSIENT` | 503 | **oui** | incident technique passager |
| `INTERNAL` | 500 | non | défaut de programmation ; alerte |

Le catalogue complet des codes, avec leur classe, est généré en **Annexe A**.

### 0.5 Ports et adaptateurs

Un **port** est une interface (protocole) définie côté Domain ou Application ; un **adaptateur** l'implémente dans l'infrastructure. Le Domain ne connaît que des ports : `Clock`, `EventOutbox`, `AuditWriter`, `NotificationSender`, `FactReader`, `Repositories`.

---

## 1. Carte des dépendances

### 1.1 Couches d'appel (les appels ne montent jamais)

```
Orchestration ............ automation
        │ appelle
        ▼
Action ................... approvals · collection · notifications
        │ appelle
        ▼
Décision ................. rules (Rule Engine, sans table)
        │ lit (ports de lecture)
        ▼
Sources de vérité ........ organizations · customers · invoices · payments · promises · imports
Projections .............. risk · priority · cashflow   (lisent les sources, écrivent leurs projections)
Socle .................... core (events, audit, idempotency, clock, tenancy)   ← utilisé par tous
```

### 1.2 Règles de dépendance

*Glossaire : dans l'architecture technique, le module `collections` de ce document s'appelle `collection` (un paquet `collections` masquerait la bibliothèque standard de Python). `approvals` est un module à part entière (couche Action) : les approbations servent `collection` et `automation`.*

| # | Règle |
|---|---|
| DR1 | Le Domain n'importe ni Django, ni Redis, ni un fournisseur : uniquement des ports. |
| DR2 | Un module **ne lit pas** les tables d'un autre. Il passe par un port de lecture (`FactReader`, requêtes de module). |
| DR3 | Une **écriture** inter-modules passe par un événement, **sauf** les opérations nommées de la règle C12 (liste fermée, deux familles) : `AllocatePayment`, `ReverseAllocation`, `ReversePayment` ; `NormalizeImportBatch` (EC1). `CreateOrganization` n'en fait plus partie : plan de provisioning, une transaction par étape (TD59). |
| DR4 | Aucun appel ascendant : `rules` n'appelle ni `collection` ni `automation` ; `collection` n'appelle pas `automation` (elle publie des événements) ; les sources n'appellent aucun moteur (elles publient). **Précision** : implémenter un port déclaré par `rules.contracts` (fournisseur de faits) est une dépendance d'**interface**, pas un appel d'une source vers un moteur ; `rules` n'importe aucun autre module. |
| DR5 | Aucun cycle de dépendance entre modules. |
| DR6 | Une projection (`risk`, `priority`, `cashflow`) n'est écrite que par son moteur ; aucun moteur d'action ne l'écrit. |
| DR7 | La couche API ne contient aucune règle ; elle authentifie, vérifie le tenant, valide la forme, appelle un cas d'usage. |
| DR8 | Un adaptateur d'infrastructure implémente un port ; il ne contient aucune règle métier. |
| DR9 | Ces règles sont **vérifiées automatiquement** en intégration continue (test d'architecture : EC9). |

### 1.3 Arêtes d'appel synchrone autorisées

| Appelant | Peut appeler |
|---|---|
| `automation` | `rules`, `collections` (création d'actions), `notifications` (création), `core.events` (émission de demandes) |
| `collections` | `rules`, `notifications`, `core` |
| `rules` | ports de lecture des sources et des projections (aucune écriture) |
| `risk`, `priority`, `cashflow` | ports de lecture des sources ; écriture de **leur** projection ; `core.events` |
| `payments` | `invoices` — **uniquement** pour `AllocatePayment` (C12) |
| `imports` | `customers`, `invoices`, `payments` — **uniquement** pour `NormalizeImportBatch` (C12, EC1) |
| Jobs planifiés | les cas d'usage de leur module propriétaire |
| Tout module | `core` |

---

## 2. Contrats d'infrastructure

### EC-01 · Émission d'un événement (`EventOutbox.emit`)

| Rubrique | Contrat |
|---|---|
| **Rôle** | inscrire un événement dans l'outbox, dans la transaction de l'appelant |
| **Appelant → appelé** | tout cas d'usage du Domain → `core.events` |
| **Entrée** | `{type, category, aggregate_type, aggregate_id, aggregate_version?, payload, import_batch_id?}` + `CallContext` |
| **Sortie** | `event_id` (UUIDv7) |
| **Préconditions** | transaction ouverte ; `payload` conforme au schéma du type (liste blanche de champs, sans donnée personnelle) ; `schema_version` connue |
| **Postconditions** | ligne `events` écrite **dans la transaction de l'appelant** ; visible du publieur seulement après validation ; `causation_depth` propagée |
| **Erreurs** | `EVENT_SCHEMA_INVALID` · `EVENT_PAYLOAD_NOT_WHITELISTED` · `CAUSATION_DEPTH_EXCEEDED` |
| **Idempotence** | l'émission suit celle du cas d'usage ; les événements du Scheduler ne sont émis que sur une transition **gardée** (`UPDATE … WHERE état = ancien`) |
| **Transaction** | celle de l'appelant ; aucune émission hors transaction |
| **Événements** | — |
| **Dépendances** | `core` uniquement |

### EC-02 · Consommation d'un événement (`EventHandler`)

| Rubrique | Contrat |
|---|---|
| **Rôle** | réagir à un événement de façon idempotente et à l'épreuve du désordre |
| **Appelant → appelé** | publieur (worker) → handler nommé (`handler_name` stable) |
| **Entrée** | l'événement complet |
| **Sortie** | `PROCESSED` (effet réalisé, reçu écrit), `SKIPPED` (rien à faire, reçu écrit) ou `REPLAY` (reçu déjà présent : rien n'est écrit, l'appel est compté) |
| **Préconditions** | handler enregistré avec ses types d'événements ; catégorie `REQUEST` : **un seul** handler destinataire |
| **Comportement obligatoire** | (1) lire le reçu `(event_id, handler_name)` : reçu **terminal** (`PROCESSED`, `SKIPPED`) présent → `REPLAY` ; reçu `RETRYING` présent → laissé à la boucle de reprise ; (2) **relire l'état à la source** (P5) ; (3) comparer `aggregate_version` : plus ancien que l'état courant → `SKIPPED` ; (4) agir de façon idempotente ; (5) écrire le reçu **dans la même transaction que l'effet** |
| **Erreurs** | `TRANSIENT` → nouvelle tentative (10 s, 1 min, 5 min, 30 min, 2 h) ; échec permanent ou tentatives épuisées → le reçu passe à **`DEAD`** |
| **Reçu** | `event_receipts.outcome` ∈ `PROCESSED`, `SKIPPED`, `RETRYING`, `DEAD` (+ `attempts`, `last_error`, et `available_at` pour `RETRYING`). `RETRYING` et `DEAD` sont des **états techniques** propres à **un handler** : la publication d'un événement ne dépend jamais de la réussite d'un handler. `DEAD` : l'événement reste identifiable et rejouable ; il n'est **jamais** retraité automatiquement, seule la commande `ReplayDeadEvent` le relance |
| **Idempotence** | reçu `(event_id, handler_name)` |
| **Transaction** | une par événement et par handler ; aucun appel à un fournisseur dans la transaction |
| **Ordre** | garanti seulement au sein d'un `(aggregate_type, aggregate_id)`, par `aggregate_version` ; jamais entre agrégats : un handler **ne suppose aucun ordre** |
| **Dépendances** | selon le handler |

### EC-03 · Jobs planifiés

Contrat commun : **idempotent par construction** ; verrou consultatif par `(job, organisation)` (une seule instance active) ; **isolation par organisation** (l'échec d'une organisation n'arrête pas les autres) ; **fuseau de l'organisation** pour toute date courante (C10) ; rattrapage borné après un arrêt ; métriques de retard.

| Job | Cadence | Clé d'idempotence / garde | Rattrapage après arrêt |
|---|---|---|---|
| `OutboxPublisher` | continu | `events.published_at IS NULL`, `FOR UPDATE SKIP LOCKED` | traite l'arriéré par `available_at` ; la **boucle de reprise** réclame aussi les reçus `RETRYING` échus |
| `InvoiceLifecycleScan` | 15 min ; par organisation dont la date locale a changé | `UPDATE … WHERE lifecycle_state = ancien AND …` | rattrape toutes les transitions dues (vers l'avant, sauts permis) |
| `PromiseBreachScan` | horaire | `UPDATE … WHERE status = 'ACTIVE' AND date > promised_date + grace` | idem |
| `HoldExpiryScan`, `ApprovalExpiryScan` | 5 min | garde d'état | idem |
| `TimeTriggerScanner` | 15 min | `trigger_key` (Automation §3) | instants manqués rattrapés dans la tolérance de 48 h, sinon écartés et comptés |
| `ExecutionWorker` | continu (sondage 30 s) | `(status, resume_at)`, `SKIP LOCKED` | — |
| `ExecuteDueActions` | 1 min | `(organization_id, status, scheduled_for)`, `SKIP LOCKED` | — |
| `Reaper` | 5 min | exécutions `RUNNING` > 10 min ; actions `EXECUTING` > 15 min | — |
| `ImportReleaser`, `EnrollmentRunner` | continu | `trigger_key` d'import / d'inscription | — |
| `ProjectionDailyRefresh` | quotidien à 05:00, heure locale de chaque organisation | recalcul de toutes les projections des sujets actifs (facteurs dépendant du jour) ; `input_hash` | SLO : 99 % des projections actives calculées le jour local courant à 08:00 |
| `ProjectionSafetyNet` | toutes les 2 h | projections de sujets actifs dont `computed_at` a plus de 24 h (filet contre un événement perdu) ; `input_hash` | SLO : âge p99 ≤ 26 h ; alerte au-delà de 36 h (objectif mesuré, pas une garantie absolue) |
| `ReconciliationWindowScan` (Collection V1.2) | horaire, par organisation dont la date locale a changé ou dont une fenêtre expire | notifications `reconciliation:{payment_id}:review:{user_id}` et `:overdue:{user_id}` ; reprise par garde d'état ; **le résultat ne dépend jamais de l'heure du passage** (dates locales, calendrier de l'organisation) | tout ce qui est dû est traité au passage suivant ; **composé par `jobs`** en deux cas d'usage (`collection`, puis `automation`), chacun dans sa transaction |
| `CashflowScheduler` | quotidien par organisation, plus regroupement des demandes | `input_hash` | — |
| `PartitionManager` | quotidien | crée les trois prochaines partitions mensuelles de `events` et `audit_logs` ; alerte si la partition par défaut reçoit une ligne | — |
| `TechnicalPurge` | quotidien | `idempotency_keys` expirées ; `event_receipts` de plus de 90 jours (données techniques, pas métier) | — |

### EC-04 · Envoi d'un message (`NotificationSender`, port)

| Rubrique | Contrat |
|---|---|
| **Rôle** | remettre une notification à un fournisseur (adaptateur `EMAIL` en V1) |
| **Appelant → appelé** | worker de notifications → adaptateur |
| **Entrée** | `notification_id`, `attempt_no`, contenu rendu, destinataire |
| **Sortie** | `SendResult{ACCEPTED \| TRANSIENT_ERROR \| PERMANENT_ERROR, provider_ref?}` |
| **Rapport de livraison** (entrant) | `DeliveryReport{notification_id, provider_ref, outcome: DELIVERED \| BOUNCED \| FAILED}` |
| **Idempotence** | clé fournisseur `{notification_id}:{attempt_no}` ; rapport idempotent par `(provider_ref, outcome)` |
| **Transaction** | **hors** transaction de base ; le résultat est écrit ensuite dans sa propre transaction |
| **Erreurs** | `CHANNEL_NOT_ENABLED` · `TEMPLATE_UNAVAILABLE` (configuration, sans nouvelle tentative) · `TRANSIENT` (nouvelle tentative) |
| **Garantie** | **au moins une fois** ; le doublon résiduel est limité par l'idempotence du fournisseur (passe Intégrations) |
| **Événements** | `NOTIFICATION_SENT`, `NOTIFICATION_FAILED` |

---

## 3. Contrats de commandes financières

### EC-05 · `AllocatePayment`, `ReverseAllocation`, `ReversePayment`

| Rubrique | Contrat |
|---|---|
| **Rôle** | seul chemin d'écriture du solde d'une facture |
| **Appelant → appelé** | API / rapprochement automatique → `payments` (qui met à jour `invoices` : exception C12) |
| **Entrée** | `AllocatePayment{payment_id, allocations[{invoice_id, amount_minor}]}` ; `ReverseAllocation{allocation_id, amount_minor, reason}` ; `ReversePayment{payment_id, reason_code, reason}` ; `CallContext.idempotency_key` **obligatoire** |
| **Sortie** | identifiants des allocations créées, résumé du paiement et des factures touchées |
| **Préconditions** | rôle suffisant ; organisation `ACTIVE` ; règles de l'Invariants §5 |
| **Postconditions** | T1, T2, T4, T5, T6, T10 vérifiées en fin de transaction ; `paid_minor`, `settlement_state`, `settled_on`, `allocated_minor`, `status` cohérents ; `collection_cycle` mis à jour si le règlement d'une facture `OVERDUE` est annulé ; **si le règlement d'une facture `PAID` est annulé, son cycle de vie est recalculé en avant, dans la même transaction, depuis `due_date` (Invariants §3.1 ; B3-a)** |
| **Erreurs** | Invariants §5 : `ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE`, `ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING`, `ALLOCATION_CUSTOMER_MISMATCH`, `ALLOCATION_CURRENCY_MISMATCH`, `ALLOCATION_INVOICE_NOT_PAYABLE`, `ALLOCATION_PAYMENT_REVERSED`, `REVERSAL_EXCEEDS_ORIGINAL`, `REVERSAL_REASON_REQUIRED`, `CONCURRENT_MODIFICATION` |
| **Idempotence** | `idempotency_keys` : même clé et même contenu → première réponse ; même clé, contenu différent → `IDEMPOTENCY_KEY_REUSED` |
| **Transaction** | **une seule** ; verrous dans l'ordre global (EC5) ; les événements sont écrits dans la même transaction |
| **Événements** | `PAYMENT_ALLOCATED` / `PAYMENT_ALLOCATION_REVERSED` / `PAYMENT_REVERSED` (agrégat `PAYMENT`) ; `INVOICE_PARTIALLY_PAID`, `INVOICE_PAID`, `INVOICE_SETTLEMENT_REVERTED`, et, si le cycle de vie est recalculé, `INVOICE_DUE_SOON` / `INVOICE_DUE` / `INVOICE_OVERDUE` (agrégat `INVOICE`) selon la transition |
| **Dépendances** | `invoices` (écriture, C12), `core` |

### EC-06 · Transitions du cycle de vie d'une facture

| Rubrique | Contrat |
|---|---|
| **Rôle** | faire avancer `lifecycle_state` (`DRAFT → ISSUED` par un utilisateur ; transitions temporelles par `InvoiceLifecycleScan`) |
| **Entrée** | facture, `as_of`, `CallContext` |
| **Préconditions** | gardes de State Machines §3 ; règlement ≠ `PAID` pour une transition temporelle |
| **Postconditions** | ligne `invoice_state_history` ; événement de la transition ; à l'émission : **rattrapage** des transitions déjà applicables, dans la même transaction |
| **Erreurs** | `INVALID_TRANSITION` · `INVOICE_EMPTY` · `INVOICE_TOTAL_MUST_BE_POSITIVE` · `CUSTOMER_INACTIVE` / `CUSTOMER_ARCHIVED` · `INVOICE_HAS_PAYMENTS` · `INVOICE_HAS_OPEN_DISPUTE` (`VOID`) |
| **Idempotence** | garde d'état : `UPDATE … WHERE lifecycle_state = ancien` ; zéro ligne → `SKIPPED` (déjà fait) |
| **Transaction** | une par facture |
| **Événements** | `INVOICE_ISSUED`, `_DUE_SOON`, `_DUE`, `_OVERDUE`, `_VOIDED`, `_CANCELLED` |

### EC-07 · `NormalizeImportBatch`

| Rubrique | Contrat |
|---|---|
| **Rôle** | matérialiser un lot d'import validé (clients, factures, paiements, allocations) |
| **Appelant → appelé** | `imports` (worker) → `customers`, `invoices`, `payments` (exception C12, EC1) |
| **Entrée** | `batch_id` (état `COMMITTED`) |
| **Postconditions** | tout ou rien : toutes les entités portent `import_batch_id` et `origin='IMPORTED'` ; états historiques reconstruits avec leurs lignes d'historique ; événements émis avec `import_batch_id` ; lot `NORMALIZED`, ou `FAILED` **sans aucune donnée créée** |
| **Erreurs** | `IMPORT_NORMALIZATION_FAILED` · `IMPORT_BATCH_NOT_READY` |
| **Idempotence** | transition gardée `COMMITTED → NORMALIZING` ; un lot ne se normalise qu'une fois |
| **Transaction** | une, pour tout le lot (limite de taille à spécifier) ; verrous dans l'ordre global |
| **Événements** | `IMPORT_BATCH_NORMALIZED` et ceux des entités créées, avec `import_batch_id` |

---

## 4. Contrats des moteurs

### EC-08 · Chargement des faits (`FactReader.load`)

| Rubrique | Contrat |
|---|---|
| **Rôle** | fournir au Rule Engine les faits d'un ou plusieurs sujets |
| **Entrée** | `organization_id`, `subjects[]`, `fact_names[]` (issus de `required_facts`), `as_of` |
| **Sortie** | `FactSet{fait → valeur \| UNKNOWN, métadonnées (`computed_at` pour une projection)}` |
| **Préconditions** | noms de faits présents au catalogue (Rule Engine §2.2) |
| **Postconditions** | lecture seule ; tous les faits d'un appel viennent du **même instantané** |
| **Erreurs** | `SUBJECT_NOT_FOUND` (sujet absent ou d'une autre organisation) · `FACT_UNKNOWN_NAME` |
| **Idempotence** | lecture pure |
| **Transaction** | lecture seule, instantané stable (`REPEATABLE READ`) ; chargement **par lots** |
| **Dépendances** | ports de lecture de `organizations`, `customers`, `invoices`, `promises`, `collections`, `risk`, `priority`, `imports` |

### EC-09 · Évaluation (`RuleEngine.evaluate`)

| Rubrique | Contrat |
|---|---|
| **Rôle** | fonction pure `évaluer(faits, définition, as_of) → Décision` |
| **Appelant → appelé** | `automation` (contextes A, B), `collections` (C, D), interface (E) → `rules` |
| **Entrée** | `EvaluationRequest{context, subject_ref, definition_ref \| garde-fous seuls, action_kind?, channel?, origin: AUTOMATIC \| MANUAL, override_grants[], trigger_event?{id, type, occurred_at}}` + `CallContext` |
| **Sortie** | `Decision` (Rule Engine §6.2) : `outcome`, `primary_exception`, `exceptions_trace[]`, `conditions_trace`, `facts_snapshot`, `levels`, `rule_refs`, `overrides[]`, `requires_approval`, `proposed_actions[]`, `decision_id` |
| **Préconditions** | `as_of` fourni ; définition validée ; grants d'override **typés** produits par `AuthorizeOverride` |
| **Postconditions** | **aucune écriture** ; déterministe : mêmes entrées, même `decision_id` ; aucune donnée personnelle dans la trace |
| **Erreurs** | `SUBJECT_NOT_FOUND` · `DEFINITION_NOT_FOUND` · `ENGINE_INTERNAL_ERROR` |
| **Idempotence** | pure |
| **Transaction** | lecture seule, instantané stable |
| **Événements** | aucun |
| **Compatibilité** | la structure de `Decision` porte un `schema_version` ; évolution additive seulement (EC6) |

### EC-10 · Autorisation d'un override (`AuthorizeOverride`)

| Rubrique | Contrat |
|---|---|
| **Rôle** | transformer une **demande** d'override en `OverrideGrant` typée, ou la refuser |
| **Appelant → appelé** | API / `collections` (action manuelle) → Application |
| **Entrée** | `{action_ref, exception_code, reason_code, reason_text}` + `CallContext` (acteur et rôle) |
| **Sortie** | `OverrideGrant{exception_code, actor_id, actor_role, reason_code, reason_text, granted_at}` |
| **Préconditions** | origine `MANUAL` ; **acteur de type `USER`** (jamais `SYSTEM` ni `AUTOMATION`) ; exception contournable ; rôle ≥ rôle minimal ; hold non `LEGAL` ; motif non vide ; organisation `ACTIVE` |
| **Erreurs** | `OVERRIDE_NOT_ALLOWED` · `OVERRIDE_ROLE_INSUFFICIENT` · `OVERRIDE_REASON_REQUIRED` · `OVERRIDE_ORIGIN_NOT_MANUAL` |
| **Idempotence** | sans effet propre ; l'audit est écrit à la création de l'action, **puis à chaque vérification du grant à l'exécution** (`ExecuteDueAction`, Collection V1.2 G8) ; le grant est lié à une action et à un code d'exception |
| **Transaction** | lecture seule |

### EC-11 · Collection Engine

| Contrat | Entrée | Sortie / postconditions | Erreurs principales | Idempotence | Transaction |
|---|---|---|---|---|---|
| `CreateCollectionAction` | contexte d'exécution (`execution_id`, `step_id`), sujet, type, canal | `PROPOSED` / `SCHEDULED` / `PENDING_APPROVAL` / `SUPPRESSED`, ou `SKIPPED` / `DEFERRED` ; `decision_snapshot` écrit ; `occurrence` **lue** dans le contexte d'exécution | `SUBJECT_NOT_FOUND` · `ACTION_LEVEL_INVALID` · `ACTION_LEVEL_BELOW_MINIMUM` | `dedup_key` → `REPLAY` | **une par module propriétaire** (action `PROPOSED`, puis approbation, puis transition : TD58) ; l'évaluation à la création est **indicative** (EC8) |
| `CreateManualAction` | sujet, type, niveau, canal, `OverrideGrant[]?` | idem, avec audit | idem + `OVERRIDE_*` | `manual:{idempotency_key}` | une |
| `ExecuteDueAction` (worker) | action `SCHEDULED` échue | revalidation complète (contexte D), dont la **revérification des grants** (acteur actif, rôle courant, organisation, exception encore contournable : Collection V1.2 G4) ; puis `EXECUTING` (transaction de claim) ; la notification est créée ensuite, dans la transaction de `notifications` ; ou `SUPPRESSED` / `DEFERRED` | `TEMPLATE_UNAVAILABLE` | verrou de ligne + garde d'état | une par action ; **envoi hors transaction** |
| `HandleSendResult` | résultat d'envoi | `DONE` / retour `SCHEDULED` (tentative) / `FAILED` ; ligne d'essai | — | `(notification_id, attempt_no)` | une |
| `CompleteTask` | tâche `SCHEDULED`, issue (liste fermée) | `DONE` | `ACTION_INVALID_TRANSITION` · `INSUFFICIENT_ROLE` | garde d'état | une |
| `ClaimTask` | tâche de pool | `assigned_to` renseigné | `CONCURRENT_MODIFICATION` | une seule réclamation gagne (`UPDATE … WHERE assigned_to IS NULL`) | une |
| `CancelAction`, `RescheduleAction` | action non terminale | `CANCELLED` (`USER_CANCELLED`) ou nouveau `scheduled_for` | `ACTION_INVALID_TRANSITION` | garde d'état | une |

Événements produits : `COLLECTION_ACTION_PROPOSED`, `_SCHEDULED`, `_EXECUTED`, `_FAILED`, `_CANCELLED`, `_SUPPRESSED`. Dépendances : `rules`, `notifications`, `core`.

### EC-12 · Automation Engine

| Contrat | Entrée | Postconditions | Erreurs principales | Idempotence | Transaction |
|---|---|---|---|---|---|
| `DispatchEvent` | événement | exécution créée, ou `SKIPPED` (`EXECUTION_IN_PROGRESS`, non rétroactif, obsolète) | — | `trigger_key = event:{id}` ; UQ d'exécution | une par événement et par automatisation |
| `ScanTimeTriggers` | fenêtre `(dernier balayage, as_of]` | exécutions créées | — | `trigger_key` temporel | une par lot |
| `RunExecutionStep` | exécution `PENDING` ou `WAITING` échue | une étape : effet, ligne d'étape, nouvel état | `EXECUTION_RATE_LIMITED` | effets idempotents ; garde d'état | **trois** : réclamer (`RUNNING`, qui sert de bail), effet dans la transaction du module propriétaire, enregistrer (ligne d'étape et nouvel état) |
| `PauseExecution` / `ResumeExecutions` | exécution, cause / événement de levée | `PAUSED` avec cause ; reprise en `PENDING` (`LATEST_ONLY`) | `INSUFFICIENT_ROLE` | garde d'état | une par exécution |
| `PreviewEnrollment` | version, mode, `as_of` | `{as_of, nombre, répartition, empreinte}` ; **aucune écriture** | — | pure | lecture seule, instantané |
| `ActivateAutomation` | version, `enrollment_mode`, `(as_of, nombre attendu, empreinte)?` | vérification atomique de l'empreinte ; création des exécutions ; **`active_since = as_of` de l'aperçu** ; `ACTIVE`. Empreinte différente : **rien n'est écrit**, aucune inscription partielle n'est conservée | `AUTOMATION_PRECONDITIONS_NOT_MET` · `ENROLLMENT_PREVIEW_STALE` · `AUTOMATION_SET_LOOP_DETECTED` · `INSUFFICIENT_ROLE` | garde d'état `DRAFT/PAUSED → ACTIVE` | **une**, instantané stable ; tout ou rien ; `SERIALIZATION_FAILURE` rejouable (EC10) |
| `ReleaseImportBatch` | lot `NORMALIZED` | exécutions **toutes créées** en `WAITING`, `resume_at` étalés | `IMPORT_BATCH_NOT_READY` | `trigger_key = import-release:…` | une par tranche |
| `RetryExecution` | exécution `FAILED` | nouvelle exécution `retry:{id}` | `INSUFFICIENT_ROLE` | `trigger_key` | une |

Événements produits : `AUTOMATION_*`, `AUTOMATION_EXECUTION_*`, événements `REQUEST`. Dépendances : `rules`, `collections`, `notifications`, `core`.

### EC-13 · Approbations

| Rubrique | Contrat |
|---|---|
| **`RequestApproval`** | entrée : cible (action ou exécution), `kind`, destinataire (utilisateur **ou** rôle), motif, `context`, `expires_at` ; sortie : `PENDING` ; événement `APPROVAL_REQUESTED` ; idempotence par cible et étape |
| **`DecideApproval`** | entrée : approbation, décision, commentaire (obligatoire au refus) ; préconditions : rôle `MANAGER` ou plus, limite d'approbation ≥ montant, ≠ demandeur si la politique l'impose ; **une seule décision** ; erreurs : `APPROVER_NOT_ELIGIBLE`, `APPROVAL_ALREADY_DECIDED`, `APPROVAL_EXPIRED`, `SELF_APPROVAL_FORBIDDEN` ; événements `APPROVAL_GRANTED` / `_REJECTED` |
| **Expiration** | `ApprovalExpiryScan` : `PENDING → EXPIRED` ; cible résolue : `approvals` interroge la cible par le port `ApprovalTargetReader` (implémenté par `collection` et `automation`) et passe l'approbation `EXPIRED` avec `TARGET_RESOLVED` ; l'action est `SUPPRESSED` par `collection`, dans **sa** transaction |
| **Transaction** | une ; la reprise de l'action ou de l'exécution suit **par événement** |

### EC-14 · Moteurs de projection (Risk, Priority, Cashflow) — interface seulement

| Rubrique | Contrat |
|---|---|
| **Rôle** | recalculer et publier une projection ; les modèles sont spécifiés dans leurs passes |
| **Déclencheurs** | les `refresh_events` du contrat de projection (Rule Engine §2.3), les événements `REQUEST` correspondants, et `ProjectionSafetyNet` |
| **Entrée** | sujet (client, facture, organisation), événement déclencheur, `as_of` |
| **Postconditions** | projection courante **mise à jour avec `computed_at` à chaque recalcul**, même à entrée inchangée ; **nouveau snapshot et événement `RESULT` seulement si le niveau change** ; `input_hash` et `model_version` enregistrés **Portée du hash** : Risk et Priority hachent des entrées **normalisées** (snapshot compact, RP14) ; Cashflow hache des entrées **brutes** du run (objet complet et daté). |
| **Erreurs** | `RISK_MODEL_UNKNOWN` · `PRIORITY_MODEL_UNKNOWN` · `CASHFLOW_MODEL_UNKNOWN` · `CASHFLOW_RUN_CONFLICT` · `CONCURRENT_MODIFICATION` (rejoué) |
| **Idempotence** | `input_hash` ; les demandes multiples pour une même cible sont **regroupées** |
| **Transaction** | une par sujet ; lit les sources en instantané stable |
| **Contrats propres** | `RecomputePriority` : demande de portée client traitée par **lots reprenables** de 200 factures (une transaction par lot). `RunCashflow` : **au plus un run `is_current`** par `(organisation, horizon, scénario)` ; promotion atomique sous verrou consultatif et **monotone** (`(as_of, computed_at)` plus récent) ; un run `FAILED` n'est jamais courant |
| **Événements** | `RISK_CHANGED`, `PRIORITY_CHANGED`, `CASHFLOW_UPDATED` (catégorie `RESULT`) |
| **Dépendances** | lecture des sources ; jamais d'écriture dans une source (DR6) |

---

## 5. Matrice d'idempotence

| Contrat | Mécanisme | Réponse à un rejeu |
|---|---|---|
| Commandes financières (EC-05) | `idempotency_keys` (clé + empreinte de la requête) | première réponse (`REPLAY`) ; contenu différent : `IDEMPOTENCY_KEY_REUSED` |
| Handler d'événement (EC-02) | reçu `(event_id, handler_name)` : `PROCESSED` ou `SKIPPED` | `REPLAY` (compté, distinct de `SKIPPED`) |
| Handler en échec définitif | reçu `DEAD` | aucun retraitement automatique ; `ReplayDeadEvent` explicite |
| Transition d'état | garde d'état en base | `SKIPPED` |
| Création d'action | `dedup_key` (partiel : hors `CANCELLED` et `SUPPRESSED`) | `REPLAY` |
| Création d'exécution | `UNIQUE (automation_id, trigger_key, subject_id)` + UQ d'exécution active | `SKIPPED` |
| Notification | `dedup_key` (hors `CANCELLED`) | `REPLAY` |
| Envoi fournisseur | clé `{notification_id}:{attempt_no}` | pas de second envoi (garantie du fournisseur) |
| Rapport de livraison | `(provider_ref, outcome)` | ignoré |
| Projection | `input_hash` | `computed_at` avancé, rien d'autre |
| Demande de recalcul | regroupement par cible | fusionnée |
| Événement du Scheduler | transition gardée | émis une seule fois |
| Lot d'import | transition gardée `COMMITTED → NORMALIZING` | `SKIPPED` |
| Job planifié | verrou consultatif + garde propre | sans effet |

---

## 6. Transactions, isolation, verrous

| Contrat | Unité de travail | Isolation | Hors transaction |
|---|---|---|---|
| Commandes financières (EC-05) | une transaction | `READ COMMITTED` + verrous de ligne explicites | — |
| Handler d'événement | une par événement et handler | `READ COMMITTED` | appels fournisseur |
| Évaluation du Rule Engine, chargement des faits | lecture seule | `REPEATABLE READ` (instantané) | — |
| Étape d'exécution | une par étape | `READ COMMITTED` | appels fournisseur |
| `ActivateAutomation` (avec inscription) | une | `REPEATABLE READ` ; un échec de sérialisation est rejoué (EC10) | — |
| `NormalizeImportBatch` | une pour le lot | `READ COMMITTED` + verrous | — |
| Envoi de message | notification créée en transaction ; envoi **hors** transaction | — | l'envoi lui-même |

**Ordre global des verrous (EC5)** : `payments` → `invoices` (par identifiant croissant) → `promises` → `collection_actions` → `automation_executions` → `notifications`. Tout code qui verrouille plusieurs lignes respecte cet ordre ; c'est ce qui exclut les interblocages.

---

## 7. Événements : production, consommation, versionnement

**Production** : tout événement passe par EC-01 ; catégorie et payload suivent le catalogue (Invariants §10) ; aucune donnée personnelle (C9).
**Consommation** : tout handler suit EC-02.
**Versionnement (EC6)** :
- chaque type d'événement et la structure `Decision` portent un `schema_version` ;
- une évolution est **additive** (nouveaux champs facultatifs) : les consommateurs ignorent ce qu'ils ne connaissent pas ;
- un changement incompatible crée une **nouvelle version** (nouveau type ou nouvelle `schema_version`), publiée **en parallèle** de l'ancienne le temps de migrer les consommateurs ;
- un registre des schémas (un fichier par type) est vérifié par les tests de contrat.

---

## 8. Invariants inter-moteurs

| # | Invariant |
|---|---|
| X1 | Un fait se lit à la **source de vérité**, jamais dans un payload d'événement. |
| X2 | Toute décision persistée référence `engine_version`, `automation_version_id` et les versions de modèles. |
| X3 | Une action ne passe en `EXECUTING` qu'après une revalidation complète (contexte D) dans la même transaction. |
| X4 | Une exécution ne crée d'action que par le Collection Engine. |
| X5 | Aucun moteur d'action n'écrit une projection, et aucun moteur de projection n'écrit une action. |
| X6 | Toute cascade réactive est idempotente (reçus). |
| X7 | `causation_depth ≤ 20` partout où un événement en provoque un autre. |
| X8 | Les opérations inter-agrégats synchrones sont exactement celles de C12. |
| X9 | Les événements d'un lot d'import n'atteignent aucune automatisation avant `RELEASING`. |
| X10 | Aucune donnée personnelle dans `events`, `decision_snapshot`, ni les traces du Rule Engine. |
| X11 | Chaque contrat vérifie que le sujet appartient à `organization_id`. |
| X12 | Aucune date courante n'est lue dans le Domain : `as_of` est injecté. |
| X13 | Un envoi de message n'a jamais lieu dans une transaction de base. |
| X14 | Un événement ne modifie jamais l'état d'un agrégat autrement que par le cas d'usage propriétaire. |
| X15 | Une sélection `LATEST_ONLY` n'est **jamais** une autorisation d'exécution : l'étape retenue repasse par le Rule Engine puis le Collection Engine. |
| X16 | `DEAD` n'est pas un état métier ; `REPLAY` et `SKIPPED` sont distincts dans les résultats, les reçus et les métriques. |
| X17 | La règle « snapshot dérivé des seules entrées normalisées » (RP14) vaut pour Risk et Priority ; le hash de Cashflow porte sur des entrées brutes, par conception. |

---

## 9. Tests de contrat

| Famille | Contenu |
|---|---|
| **Contrats pilotés par les consommateurs** | pour chaque événement : le consommateur déclare les champs qu'il lit ; le test échoue si le producteur les retire ou les renomme |
| **Registre de schémas** | chaque type d'événement et `Decision` ont un schéma versionné ; toute évolution non additive fait échouer la validation |
| **Tests d'architecture** | les règles DR1 à DR8 sont exprimées comme règles d'import automatiquement vérifiées (EC9) |
| **Rejeu et désordre** | chaque handler : événement livré deux fois, dans le désordre, après une panne avant l'écriture du reçu → même état final Les résultats `PROCESSED`, `SKIPPED`, `REPLAY`, `DEAD` sont chacun vérifiés et comptés séparément. |
| **Idempotence des commandes** | chaque commande rejouée avec la même clé (même contenu, contenu différent) |
| **Concurrence** | deux allocations simultanées sur le même paiement ; deux workers sur la même action ; réclamation simultanée d'une tâche |
| **Isolation tenant** | chaque contrat appelé avec un sujet d'une autre organisation : `NOT_FOUND`, aucune ligne lue |
| **Transactions** | panne simulée entre chaque étape d'un cas d'usage : soit tout est écrit, soit rien |
| **Déterminisme** | l'évaluation du Rule Engine, le calcul de créneau, la sélection `LATEST_ONLY` avec horloge injectée |
| **Jobs** | rattrapage après arrêt (30 h, 5 jours) ; isolation par organisation ; fuseaux |
| **Erreurs** | chaque code de l'Annexe A est produit par au moins un test ; sa classe HTTP est vérifiée |

La **matrice de tests globale** (passe suivante) assemble ces familles avec celles des passes précédentes.

---

## 10. Décisions (V1.1)

**EC1 à EC10 : VALIDÉES.** Aucune modification d'architecture ; cinq précisions de rédaction ont été verrouillées.

| # | Décision validée | Amendement appliqué |
|---|---|---|
| **EC1** | `NormalizeImportBatch` devient explicitement la troisième exception de la règle **C12** | Invariants : règle C12 |
| **EC2** | `DEAD` est un **état technique** de suivi et de rejeu d'un handler ; nouvelles tentatives à 10 s, 1 min, 5 min, 30 min, 2 h | Contrat §12.2 : `event_receipts.outcome` = `PROCESSED`, `SKIPPED`, `DEAD` ; colonnes `attempts` et `last_error` |
| **EC3** | `CallContext` et port `Clock` contractuels | — |
| **EC4** | Modèle d'erreur commun ; catalogue généré (Annexe A) | — |
| **EC5** | Ordre global des verrous obligatoire | — |
| **EC6** | Versionnement additif ; nouvelle version en cas de rupture | — |
| **EC7** | Contrat commun des jobs planifiés ; `ProjectionSafetyNet` | — |
| **EC8** | L'évaluation à la création d'une action est indicative ; la revalidation avant effet est la garantie | — |
| **EC9** | Règles de dépendance vérifiées en intégration continue | — |
| **EC10** | `SERIALIZATION_FAILURE` : conflit rejouable, nombre de tentatives borné | — |

### Précisions de verrouillage

| # | Précision |
|---|---|
| **P1** | **`DEAD` n'est pas un état métier.** `event_receipts.outcome` vaut `PROCESSED`, `SKIPPED` ou `DEAD`. `DEAD` signifie : *le handler n'a pas réussi à traiter l'événement après la politique de nouvelles tentatives ; l'événement reste identifiable et rejouable manuellement.* Il ne signifie **jamais** que l'événement métier est perdu. Un événement dont le reçu est `DEAD` n'est pas retraité automatiquement : seule la commande explicite `ReplayDeadEvent` le relance et met le reçu à jour. |
| **P2** | **`REPLAY` et `SKIPPED` restent distincts**, y compris dans les métriques. `REPLAY` : l'effet avait **déjà été réalisé** (le reçu `PROCESSED` ou `SKIPPED` existe déjà ; rien n'est écrit). `SKIPPED` : l'événement est reçu pour la première fois mais **aucune action n'était nécessaire** (état courant plus récent, cible résolue…). Le reçu enregistre `PROCESSED` ou `SKIPPED` ; `REPLAY` n'est pas stocké, il est compté. |
| **P3** | **La sélection `LATEST_ONLY` n'est jamais une autorisation d'exécution** : elle passe toujours par le Rule Engine puis le Collection Engine (invariant X15). |
| **P4** | **`preview_as_of = active_since`** pour une activation issue d'un aperçu ; si l'empreinte a changé, `ENROLLMENT_PREVIEW_STALE` et **aucune inscription partielle n'est conservée** : l'activation est tout ou rien. |
| **P5** | Ordre des passes : **Risk / Priority / Cashflow** avant la matrice de tests globale et l'architecture technique. |

---

---

---

---

## Annexe A · Catalogue des erreurs (généré)

Généré à partir des lignes « Erreurs » des Invariants, du tableau de validation du Rule Engine, des passes Collection, Automation et de ce document. **La classification est une proposition à relire** (EC4).

Sources : `INV` Invariants · `RULE` Rule Engine · `COL` Collection Engine · `AUT` Automation Engine · `ENG` Engine Contracts · `ARCH` Architecture technique (erreurs techniques internes).

Répartition : BUSINESS_RULE 37 · CONFLICT 24 · FORBIDDEN 5 · INTERNAL 7 · NOT_FOUND 2 · RATE_LIMITED 1 · VALIDATION 33 — **total 109 codes**.

| Code | Classe | HTTP | Nouvelle tentative | Sources |
|---|---|---|---|---|
| `ACTION_APPROVAL_REQUIRED` | BUSINESS_RULE | 422 | non | INV |
| `ACTION_INVALID_TRANSITION` | CONFLICT | 409 | non | INV |
| `ACTION_LEVEL_BELOW_MINIMUM` | BUSINESS_RULE | 422 | non | COL, INV |
| `ACTION_LEVEL_INVALID` | VALIDATION | 400/422 | non | COL, INV |
| `ACTION_LEVEL_REGRESSION` | BUSINESS_RULE | 422 | non | INV |
| `ACTION_MAX_ATTEMPTS_REACHED` | BUSINESS_RULE | 422 | non | INV |
| `ALLOCATION_CURRENCY_MISMATCH` | BUSINESS_RULE | 422 | non | INV |
| `ALLOCATION_CUSTOMER_MISMATCH` | BUSINESS_RULE | 422 | non | INV |
| `ALLOCATION_EXCEEDS_INVOICE_OUTSTANDING` | BUSINESS_RULE | 422 | non | INV |
| `ALLOCATION_EXCEEDS_PAYMENT_AVAILABLE` | BUSINESS_RULE | 422 | non | INV |
| `ALLOCATION_INVOICE_NOT_PAYABLE` | BUSINESS_RULE | 422 | non | INV |
| `ALLOCATION_PAYMENT_REVERSED` | BUSINESS_RULE | 422 | non | INV |
| `APPROVAL_ALREADY_DECIDED` | CONFLICT | 409 | non | INV |
| `APPROVAL_COMMENT_REQUIRED` | VALIDATION | 400/422 | non | INV |
| `APPROVAL_EXPIRED` | BUSINESS_RULE | 422 | non | INV |
| `APPROVER_NOT_ELIGIBLE` | FORBIDDEN | 403 | non | INV |
| `AUTOMATION_PRECONDITIONS_NOT_MET` | BUSINESS_RULE | 422 | non | AUT |
| `AUTOMATION_SET_LOOP_DETECTED` | BUSINESS_RULE | 422 | non | AUT |
| `CASHFLOW_HORIZON_INVALID` | VALIDATION | 400/422 | non | INV |
| `CASHFLOW_INPUT_INCONSISTENT` | BUSINESS_RULE | 422 | non | INV |
| `CASHFLOW_MODEL_UNKNOWN` | INTERNAL | 500 | non | INV |
| `CASHFLOW_RUN_CONFLICT` | CONFLICT | 409 | non | INV |
| `CASHFLOW_SCENARIO_INVALID` | VALIDATION | 400/422 | non | INV |
| `CAUSATION_DEPTH_EXCEEDED` | BUSINESS_RULE | 422 | non | ENG |
| `CHANNEL_NOT_ENABLED` | BUSINESS_RULE | 422 | non | ENG |
| `CONCURRENT_MODIFICATION` | CONFLICT | 409 | oui | ENG, INV |
| `CONTACT_INVALID_VALUE` | VALIDATION | 400/422 | non | INV |
| `CONTACT_PRIMARY_CONFLICT` | CONFLICT | 409 | non | INV |
| `CUSTOMER_ARCHIVED` | BUSINESS_RULE | 422 | non | INV |
| `CUSTOMER_CODE_TAKEN` | CONFLICT | 409 | non | INV |
| `CUSTOMER_HAS_OPEN_INVOICES` | BUSINESS_RULE | 422 | non | INV |
| `CUSTOMER_INACTIVE` | BUSINESS_RULE | 422 | non | INV |
| `DB_INVARIANT_VIOLATED` | INTERNAL | 500 | non | ARCH |
| `DEFINITION_ACTION_NOT_ALLOWED` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_ACTION_SUBJECT_MISMATCH` | VALIDATION | 400/422 | non | AUT |
| `DEFINITION_BUILTIN_EXCEPTION_OVERRIDE` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_CHANNEL_NOT_ENABLED` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_LEVEL_TYPE_INCOMPATIBLE` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_NOT_FOUND` | NOT_FOUND | 404 | non | ENG |
| `DEFINITION_PROJECTION_TRIGGER_MISMATCH` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_SCHEMA_INVALID` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_STEP_LEVEL_RANGE_INVALID` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_TOO_COMPLEX` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_TRIGGER_LOOP` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_TYPE_MISMATCH` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_UNKNOWN_FACT` | VALIDATION | 400/422 | non | RULE |
| `DEFINITION_VALUE_OUT_OF_RANGE` | VALIDATION | 400/422 | non | RULE |
| `DISPUTE_ALREADY_OPEN` | CONFLICT | 409 | non | INV |
| `DISPUTE_AMOUNT_EXCEEDS_TOTAL` | BUSINESS_RULE | 422 | non | INV |
| `DISPUTE_INVOICE_NOT_DISPUTABLE` | BUSINESS_RULE | 422 | non | INV |
| `DISPUTE_REASON_REQUIRED` | VALIDATION | 400/422 | non | INV |
| `ENGINE_INTERNAL_ERROR` | INTERNAL | 500 | non | ENG |
| `ENROLLMENT_PREVIEW_STALE` | CONFLICT | 409 | non | AUT |
| `EVENT_PAYLOAD_NOT_WHITELISTED` | VALIDATION | 400/422 | non | ENG |
| `EVENT_SCHEMA_INVALID` | VALIDATION | 400/422 | non | ENG |
| `EXECUTION_RATE_LIMITED` | RATE_LIMITED | 429 | oui | AUT |
| `FACT_UNKNOWN_NAME` | VALIDATION | 400/422 | non | ENG |
| `HOLD_NOT_ACTIVE` | CONFLICT | 409 | non | INV |
| `HOLD_OVERLAP` | BUSINESS_RULE | 422 | non | INV |
| `HOLD_REASON_REQUIRED` | VALIDATION | 400/422 | non | INV |
| `HOLD_TARGET_MISMATCH` | VALIDATION | 400/422 | non | INV |
| `IDEMPOTENCY_KEY_REUSED` | CONFLICT | 409 | non | ENG, INV |
| `IMPORT_APPROVAL_REQUIRED` | BUSINESS_RULE | 422 | non | INV |
| `IMPORT_BATCH_COMMITTED` | CONFLICT | 409 | non | INV |
| `IMPORT_BATCH_NOT_READY` | CONFLICT | 409 | non | INV |
| `IMPORT_FILE_ALREADY_IMPORTED` | CONFLICT | 409 | non | INV |
| `IMPORT_NORMALIZATION_FAILED` | BUSINESS_RULE | 422 | non | INV |
| `IMPORT_RELEASE_MODE_INVALID` | VALIDATION | 400/422 | non | INV |
| `IMPORT_VALIDATION_FAILED` | BUSINESS_RULE | 422 | non | INV |
| `INSUFFICIENT_ROLE` | FORBIDDEN | 403 | non | ENG, INV |
| `INVALID_TRANSITION` | CONFLICT | 409 | non | ENG, INV |
| `INVOICE_DATES_INVALID` | VALIDATION | 400/422 | non | INV |
| `INVOICE_EMPTY` | BUSINESS_RULE | 422 | non | INV |
| `INVOICE_FIELD_LOCKED` | CONFLICT | 409 | non | INV |
| `INVOICE_HAS_OPEN_DISPUTE` | BUSINESS_RULE | 422 | non | INV |
| `INVOICE_HAS_PAYMENTS` | BUSINESS_RULE | 422 | non | INV |
| `INVOICE_NUMBER_TAKEN` | CONFLICT | 409 | non | INV |
| `INVOICE_TOTAL_MUST_BE_POSITIVE` | BUSINESS_RULE | 422 | non | INV |
| `LAST_OWNER_REQUIRED` | BUSINESS_RULE | 422 | non | INV |
| `LOCK_ORDER_VIOLATION` | INTERNAL | 500 | non | ARCH |
| `ORG_CURRENCY_LOCKED` | CONFLICT | 409 | non | INV |
| `ORG_NOT_ACTIVE` | CONFLICT | 409 | non | INV |
| `ORG_SLUG_TAKEN` | CONFLICT | 409 | non | INV |
| `ORG_TIMEZONE_INVALID` | VALIDATION | 400/422 | non | INV |
| `OVERRIDE_NOT_ALLOWED` | FORBIDDEN | 403 | non | RULE |
| `OVERRIDE_ORIGIN_NOT_MANUAL` | BUSINESS_RULE | 422 | non | RULE |
| `OVERRIDE_REASON_REQUIRED` | VALIDATION | 400/422 | non | RULE |
| `OVERRIDE_ROLE_INSUFFICIENT` | FORBIDDEN | 403 | non | RULE |
| `PAYMENT_ALREADY_REVERSED` | CONFLICT | 409 | non | INV |
| `PAYMENT_AMOUNT_INVALID` | VALIDATION | 400/422 | non | INV |
| `PAYMENT_CURRENCY_MISMATCH` | VALIDATION | 400/422 | non | INV |
| `PAYMENT_DATE_IN_FUTURE` | BUSINESS_RULE | 422 | non | INV |
| `PAYMENT_DUPLICATE_REFERENCE` | CONFLICT | 409 | non | INV |
| `PAYMENT_REVERSAL_REASON_REQUIRED` | VALIDATION | 400/422 | non | INV |
| `PRIORITY_MODEL_UNKNOWN` | INTERNAL | 500 | non | INV |
| `PROMISE_ALREADY_ACTIVE` | CONFLICT | 409 | non | INV |
| `PROMISE_AMOUNT_EXCEEDS_OUTSTANDING` | BUSINESS_RULE | 422 | non | INV |
| `PROMISE_AMOUNT_INVALID` | VALIDATION | 400/422 | non | INV |
| `PROMISE_DATE_IN_PAST` | BUSINESS_RULE | 422 | non | INV |
| `PROMISE_INVOICE_NOT_OPEN` | BUSINESS_RULE | 422 | non | INV |
| `PROMISE_NOT_ACTIVE` | CONFLICT | 409 | non | INV |
| `REVERSAL_EXCEEDS_ORIGINAL` | BUSINESS_RULE | 422 | non | INV |
| `REVERSAL_REASON_REQUIRED` | VALIDATION | 400/422 | non | INV |
| `RISK_MODEL_UNKNOWN` | INTERNAL | 500 | non | INV |
| `SELF_APPROVAL_FORBIDDEN` | FORBIDDEN | 403 | non | INV |
| `SERIALIZATION_FAILURE` | CONFLICT | 409 | oui | ENG |
| `SUBJECT_NOT_FOUND` | NOT_FOUND | 404 | non | COL, ENG, RULE |
| `TEMPLATE_UNAVAILABLE` | BUSINESS_RULE | 422 | non | COL, ENG |
| `TENANT_CONTEXT_MISSING` | INTERNAL | 500 | non | ARCH |
