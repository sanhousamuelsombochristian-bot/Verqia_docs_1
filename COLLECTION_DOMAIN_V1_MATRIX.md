# VERQIA — Collection Domain V1 : matrice des 22 cas d'usage (Étape 1)

Document de TRAVAIL (pas encore une spécification figée). Construit strictement depuis les sources déjà gelées :
`COLLECTION_ENGINE_V1.md`, `COLLECTION_ENGINE_V1_2.md`, `RULE_ENGINE_V1.md`, `STATE_MACHINES_V1.md` (§8 Collection
Action, §9 Collection Hold), `INVARIANTS_V1.md` (§7.1, §7.2), `DATA_CONTRACT_V1.md` (§6.3 `collection_holds`),
`ENGINE_CONTRACTS_V1.md`, et l'état RÉEL déjà généré `verqia/collection/application/specs.py` (25 cas d'usage,
22 touchent l'état Collection — les 3 restants, `AuthorizeOverride`/`ScanReconciliationReviews`/`ReadApprovalTarget`,
n'écrivent aucune des trois clés d'état Collection et sont donc hors de cette matrice).

**Reconsolidation post-B8 (2026-09-26)** : 19 → 22 cas d'usage. `ClaimTask` (A10), `CompleteTask` (A11) et
`RescheduleAction` (A12) ont été ajoutés au registre par l'amendement `B8` (AUDIT-01, Phase 6B) et sont désormais
intégrés à cette matrice, dans le sous-domaine A (opérations utilisateur sur une action existante), avec les mêmes
niveaux EXPLICIT/DERIVED/OPEN que le reste du document. Aucun champ technique du registre (compteurs de `locks.py`,
`kind`, exception de nommage) n'est traité comme une règle métier : seul ce que les sources métier gelées énoncent
l'est.

**Niveaux de confiance**, portés par CHAQUE champ :
- **EXPLICIT** — directement énoncé par une source figée, sans interprétation.
- **DERIVED** — déduit mécaniquement en combinant plusieurs sources cohérentes entre elles.
- **OPEN** — ne peut pas être tranché sans arbitrage.

**État des arbitrages DV4** (voir la section dédiée en fin de document pour le détail
Question → Sources → Arbitrage → Rationale → Impact → Amendement requis) :

| DV | Arbitrage | Statut décisionnel | Amendement de document gelé |
|---|---|---|---|
| DV4-1 | `RuleDecision` externe, jamais recalculée | ACCEPTÉ | aucun |
| DV4-2 | Hold | RÉSOLU | aucun |
| DV4-3 | Découpage en 3 sous-domaines | ACCEPTÉ | aucun |
| DV4-4 | `dedup_key` conserve `:R{occurrence}` | ACCEPTÉ | **AM-01 APPLIQUÉ** — `INVARIANTS_V1.md` §7.1, journalisé `DATA_CONTRACT_V1.md` #25 |
| DV4-5 | `OnApprovalDecided` ne rappelle pas `rules.Evaluate` | ACCEPTÉ | aucun (clarification `COLLECTION_DOMAIN_V1.md` seulement) |
| DV4-6 | Les 7 `SuppressOn*` ne rappellent pas `rules.Evaluate` | ACCEPTÉ | aucun (clarification `COLLECTION_DOMAIN_V1.md` seulement) |
| DV4-7 | `ORGANIZATION_CLOSED` = `ORGANIZATION_SUSPENDED` pour Collection | ACCEPTÉ | **AM-02 APPLIQUÉ** — `COLLECTION_ENGINE_V1.md` §12, journalisé `DATA_CONTRACT_V1.md` #26 |
| DV4-8 | `SuppressOnInvoiceDisputed` a besoin d'une lecture `invoices.InvoiceFacts` | ACCEPTÉ (architecture) | **AM-03 APPLIQUÉ** — registre (`commands.py`), régénéré, journalisé `application_freeze.py` B7 |

**Passe « Amendments post-DV4 » CLÔTURÉE (2026-09-26)** : AM-01, AM-02, AM-03 tous appliqués et vérifiés. Voir le
rapport d'amendements séparé pour le détail des vérifications et des anomalies résiduelles.

---

## Sous-domaine A — Action Lifecycle (12 cas d'usage)

### A1. `CreateCollectionAction`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `CreateCollectionAction{subject(invoice_id), type, channel, execution_id, step_id}` | EXPLICIT (specs.py) |
| Actor | Automation Engine (pas d'acteur humain ; `origin` implicite = automatique) | DERIVED (§4 préambule « contextes C » + absence d'`origin`/`override_grants` dans l'entrée, contrairement à `CreateManualAction`) |
| State(s) lus | `collection.action_status` (recherche par `dedup_key` pour REPLAY ; « rejet antérieur » : une ligne `CANCELLED`/`APPROVAL_REJECTED` de même clé dans le cycle) | DERIVED (§4 étapes 4-5) |
| Facts requis | sujet = facture émise (`SUBJECT_NOT_FOUND` sinon) | EXPLICIT (§4 étape 1) |
| RuleDecision | Oui | EXPLICIT (`reads=('rules.Evaluate',)`) |
| Champs RuleDecision consommés | `outcome`, `suppression_code` (si `SUPPRESS`), `retry_at` (si `DEFER`), `requires_approval`, `levels.collection_level`, `levels.risk_level`, `levels.priority_level`, `rule_refs.automation_version_id`, `primary_exception`, `exceptions_trace[]`, `overrides[]` (structurellement présent, vide en pratique — A1 est toujours automatique) | **EXPLICIT — FERMÉ (OPEN-06)** : liste établie depuis la forme exacte de `decision_snapshot` (`DATA_CONTRACT_V1.md` §6.1 ligne 402 : « contient séparément `risk_level`, `priority_level`, `collection_rules_ref`, `level`, ainsi que `primary_exception`, `exceptions_trace[]` et `overrides[]` »). Champs NON consommés : `decision_id`, `evaluated_at`, `as_of` (propre à `RuleDecision`), `org_timezone`, `conditions_trace`, `facts_snapshot`, `proposed_actions[]`, `input_hash`. |
| Reads | `rules.Evaluate` | EXPLICIT |
| as_of | injecté (convention noyau, jamais lu) | EXPLICIT |
| Preconditions | canal activé pour ce type/cette étape (§1, §2) ; `dedup_key` libre ou REPLAY ; pas de rejet antérieur (§4-4) | DERIVED |
| Decision | `SUPPRESS`→écrire directement en `SUPPRESSED` (`decision_snapshot`, `suppression_code`) ; `SKIP`→rien (compteur seul, hors Domain) ; `DEFER`→rien, l'appelant réessaie à `retry_at` ; `PROCEED`→écrire `PROPOSED` puis enchaîner `AdvanceProposedAction` (phase 2, orchestration) | EXPLICIT (§4 étape 3, 7 ; phases specs.py) |
| State transition | `(création) → PROPOSED` **ou** `(création) → SUPPRESSED` directement (une seule ligne, jamais deux écritures) | DERIVED (STATE_MACHINES §8 + §4 « créée directement en SUPPRESSED, pour l'explicabilité ») |
| Writes | `collection.action_status` : `invoice_id`, `type`, `channel`, `level`, `origin`, `dedup_key`, `decision_snapshot`, `status` | EXPLICIT/DERIVED |
| Events | `COLLECTION_ACTION_PROPOSED` (si `PROPOSED`) ou `COLLECTION_ACTION_SUPPRESSED` (si `SUPPRESS`) | EXPLICIT (`emits=`) |
| Audit | `CONDITIONAL` déclaré, mais cette UC est **toujours automatique** (jamais `MANUAL`, jamais d'override — réservés à `CreateManualAction`) : en pratique l'audit ne se déclenche donc probablement jamais ici | DERIVED — **OPEN** : à confirmer que `CreateCollectionAction` ne porte jamais d'override |
| Errors | `SUBJECT_NOT_FOUND`, `ACTION_LEVEL_INVALID`, `ACTION_LEVEL_BELOW_MINIMUM` | EXPLICIT |
| Idempotency / déduplication | `dedup_key = {invoice_id}:{type}:L{level}:C{cycle}:R{occurrence}`, portée `ORGANIZATION` | **ACCEPTÉ (DV4-4)** — amendement `INVARIANTS_V1.md` §7.1 appliqué (AM-01) |
| Dependencies | `rules.Evaluate` (RuleDecision) ; `invoices.InvoiceFacts` (sujet) ; état propre pour REPLAY/rejet antérieur | DERIVED |
| Open questions | liste exacte et complète des champs `RuleDecision` consommés (à figer seulement après la matrice complète, par consigne explicite) ; le contrôle « canal activé » est-il fait par l'Application avant l'appel au Domain, ou par le Domain lui-même ? | OPEN |
| Sources | `COLLECTION_ENGINE_V1.md` §1, §2, §3.1bis, §4 ; `STATE_MACHINES_V1.md` §8 ; `INVARIANTS_V1.md` §7.1 ; `RULE_ENGINE_V1.md` §6.1, §7bis ; `specs.py` |

### A2. `AdvanceProposedAction`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `AdvanceProposedAction` (niveau C, pas de contrat de commande dédié) | EXPLICIT |
| Actor | `SYSTEM` (appelé en composition, jamais directement — `kind='system'`, `entry=INTERNAL`) | EXPLICIT |
| State(s) lus | `collection.action_status` (la ligne `PROPOSED` à faire avancer) | EXPLICIT (`lock_sequence=(('collection_actions','U'),)`) |
| Facts requis | aucun fait facture/client direct : dépend entièrement de la `RuleDecision` déjà produite à la création | DERIVED |
| RuleDecision | Oui | EXPLICIT (`reads=('rules.Evaluate',)`) |
| Champs RuleDecision consommés | **EXPLICIT — FERMÉ (OPEN-06/A2)** : `AdvanceProposedAction` effectue une **nouvelle évaluation** `rules.Evaluate` lors de la revalidation `PROPOSED → SCHEDULED` (`requires_approval`, `outcome`/`suppression_code`, `levels.*`, `primary_exception`, `exceptions_trace[]`, `overrides[]`). Le `decision_snapshot` de création reste un état historique/audit, jamais l'autorité pour la planification. | ACCEPTÉ — `STATE_MACHINES_V1.md` §8, ligne `PROPOSED → SCHEDULED` : « revalidation (ordre : organisation, client, facture, litige, promesse, hold, fréquence, contact, consentement) » — reprend explicitement la séquence des 13 exceptions du Rule Engine ; n'a de sens que si réellement réexécutée, pas relue. |
| Reads | `rules.Evaluate` | EXPLICIT |
| as_of | injecté | EXPLICIT |
| Preconditions | garde d'état : la ligne doit être `PROPOSED` (sinon `SKIPPED`) | EXPLICIT (`idempotency="garde d'état PROPOSED"`) |
| Decision | si `requires_approval` → écrire `PENDING_APPROVAL` (ligne `approvals` créée en phase 1, `own:approvals.RequestApproval`) ; sinon → planifier (Sous-domaine A, cf. A-planification) et écrire `SCHEDULED` | EXPLICIT (§4 étape 7 ; STATE_MACHINES §8) |
| State transition | `PROPOSED → PENDING_APPROVAL` ou `PROPOSED → SCHEDULED` (ou `→ SUPPRESSED` si la revalidation échoue) | EXPLICIT (STATE_MACHINES §8) |
| Writes | `collection.action_status.status` (+ `scheduled_for` si `SCHEDULED`) | DERIVED |
| Events | `COLLECTION_ACTION_SCHEDULED` ou `COLLECTION_ACTION_SUPPRESSED` | EXPLICIT |
| Audit | aucun (réaction/transition, D3) | EXPLICIT |
| Errors | aucune déclarée | EXPLICIT |
| Idempotency / déduplication | garde d'état (`PROPOSED` uniquement) ; sans lien direct avec `dedup_key` | EXPLICIT |
| Dependencies | `rules.Evaluate` ; `approvals.RequestApproval` (cross-module, sa propre transaction, TD58) ; fonction de planification (`SlotCalculator`, §7) si `SCHEDULED` | DERIVED |
| Open questions | RuleDecision relue ou transmise depuis la création ? Le calcul de créneau (`SlotCalculator`) fait-il partie de CETTE décision Domain, ou est-il assemblé par l'Application et fourni comme fait déjà résolu (comme pour Risk/Priority) ? | OPEN |
| Sources | `COLLECTION_ENGINE_V1.md` §4 étape 7, §6, §7 ; `STATE_MACHINES_V1.md` §8 ; `specs.py` (phases) |

### A3. `ResumeProposedActions`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `ResumeProposedActions` (niveau C, job) | EXPLICIT |
| Actor | `SYSTEM` (balayage, `kind='job'`, `entry=BACKGROUND`, `tenant=ENUMERATOR`) | EXPLICIT |
| State(s) lus | `collection.action_status` : toute ligne restée `PROPOSED` (interrompue avant sa composition) | EXPLICIT (`lock_operation='AdvanceProposedAction'`, même verrou que A2) |
| Facts requis | aucun propre au job ; délègue entièrement à `AdvanceProposedAction` par organisation | EXPLICIT (phase unique : `calls=('collection.AdvanceProposedAction',)`) |
| RuleDecision | non lue par CE cas d'usage (déléguée à A2) | DERIVED (`reads=()`) |
| Champs RuleDecision consommés | — (voir A2) | — |
| Reads | aucune | EXPLICIT |
| as_of | injecté | EXPLICIT |
| Preconditions | garde d'état `PROPOSED` (même garde que A2, réappliquée à chaque ligne) | EXPLICIT |
| Decision | pas de décision propre : c'est une **énumération** qui rejoue A2 pour chaque ligne encore `PROPOSED` | EXPLICIT |
| State transition | aucune directement ; via A2 pour chaque ligne | DERIVED |
| Writes | aucun direct (via A2) | DERIVED |
| Events | aucun direct | EXPLICIT (`emits=()`) |
| Audit | aucun | EXPLICIT |
| Errors | aucune | EXPLICIT |
| Idempotency / déduplication | garde d'état ; « le prochain passage rattrape » (pas d'horaire figé qui conditionne le résultat, W6-style) | EXPLICIT |
| Dependencies | `AdvanceProposedAction` (A2) | EXPLICIT |
| Open questions | cadence du job non trouvée dans `ENGINE_CONTRACTS_V1.md` (contrairement à `HoldExpiryScan`/`ApprovalExpiryScan` qui ont une cadence de 5 min explicite) — à vérifier | OPEN |
| Sources | `specs.py` ; `COLLECTION_ENGINE_V1.md` §4 note « un balayage reprend une action restée PROPOSED » |

### A4. `CreateManualAction`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `CreateManualAction{subject, type, level, channel, override_grants}` | EXPLICIT |
| Actor | `USER` (rôle `COLLECTOR` ou plus) | EXPLICIT (§4 « Actions manuelles ») |
| State(s) lus | `collection.action_status` (dedup_key `manual:{clé}`) | EXPLICIT (`idempotency='manual:{clé}'`) |
| Facts requis | sujet = facture émise ; niveau choisi par l'utilisateur **dans la plage du type** (C11) | EXPLICIT |
| RuleDecision | Oui | EXPLICIT |
| Champs RuleDecision consommés | même ensemble qu'A1 (`outcome`, `suppression_code`, `retry_at`, `requires_approval`, `levels.*`, `rule_refs.automation_version_id`, `primary_exception`, `exceptions_trace[]`, `overrides[]`) | **EXPLICIT — FERMÉ (OPEN-06)**, avec `overrides[]` et `exceptions_trace[]` réellement significatifs ici (grants manuels réels, entrées `OVERRIDDEN` possibles) — contrairement à A1 où ces champs sont structurellement présents mais vides en pratique. |
| Reads | `rules.Evaluate` | EXPLICIT |
| as_of | injecté | EXPLICIT |
| Preconditions | mêmes garde-fous et même plancher (niveau ≥ 3 dès `OVERDUE`) et même non-régression qu'une action automatique ; `override_grants` valides (voir `AuthorizeOverride`, hors Domain Collection lui-même — produit par un AUTRE cas d'usage) | EXPLICIT |
| Decision | identique à A1 (`SUPPRESS`/`SKIP`/`DEFER`/`PROCEED`), sauf que les exceptions contournables avec un grant valide passent en `OVERRIDDEN` dans la trace et n'empêchent pas `PROCEED` | EXPLICIT (§4, `RULE_ENGINE_V1.md` §3.3) |
| State transition | identique à A1 | DERIVED |
| Writes | identique à A1 + `origin='MANUAL'` | DERIVED |
| Events | `COLLECTION_ACTION_PROPOSED` ou `_SUPPRESSED` | EXPLICIT |
| Audit | **toujours** requis ici (commande d'un utilisateur, D3) | EXPLICIT (`AuditMode.REQUIRED`, contrairement à A1) |
| Errors | `SUBJECT_NOT_FOUND`, `ACTION_LEVEL_INVALID`, `ACTION_LEVEL_BELOW_MINIMUM`, `OVERRIDE_NOT_ALLOWED`, `OVERRIDE_ROLE_INSUFFICIENT`, `OVERRIDE_REASON_REQUIRED`, `OVERRIDE_ORIGIN_NOT_MANUAL` | EXPLICIT |
| Idempotency / déduplication | `manual:{idempotency_key}` — **différent** de `dedup_key` automatique ; DV4-4 (ACCEPTÉ) ne s'applique pas directement ici (formule différente, déjà sans ambiguïté) | EXPLICIT |
| Dependencies | `rules.Evaluate` ; `AuthorizeOverride` (grants déjà produits, fournis en entrée — `CreateManualAction` ne les fabrique pas) ; `invoices.InvoiceFacts` | DERIVED |
| Open questions | le Domain Collection reçoit-il des `OverrideGrant` déjà validés (produits par `AuthorizeOverride` avant l'appel), ou valide-t-il lui-même leur structure ? Le §3.3 du Rule Engine dit que c'est `AuthorizeOverride` qui les PRODUIT — donc Collection les reçoit tels quels, ne les fabrique jamais ; à confirmer que Collection ne fait que les TRANSMETTRE au Rule Engine sans les interpréter lui-même (cohérent avec DV4-1) | OPEN (confirmation, pas contradiction) |
| Sources | `COLLECTION_ENGINE_V1.md` §4 ; `RULE_ENGINE_V1.md` §3, §3.1, §3.3 ; `specs.py` |

### A5. `CancelCollectionAction`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `CancelCollectionAction` (niveau C : identifiant d'action + motif) | EXPLICIT |
| Actor | `USER` | EXPLICIT (`entry=PUBLIC`, commande) |
| State(s) lus | `collection.action_status` (l'action ciblée) | EXPLICIT |
| Facts requis | aucun fait externe ; uniquement l'état courant de l'action | DERIVED |
| RuleDecision | **Non** | EXPLICIT (`reads=()`) |
| Champs RuleDecision consommés | — | — |
| Reads | aucune | EXPLICIT |
| as_of | injecté | EXPLICIT |
| Preconditions | l'action est dans un état **non terminal** (`DONE`/`FAILED`/`CANCELLED`/`SUPPRESSED` refusés) | EXPLICIT (STATE_MACHINES §8 « tout état non terminal → CANCELLED ») |
| Decision | annuler avec motif ; libère la `dedup_key` (contrairement à `FAILED`) | EXPLICIT (STATE_MACHINES §8 note ; INVARIANTS §7.1 « les états … CANCELLED, SUPPRESSED et FAILED ne comptent pas », mais seul `CANCELLED`/`SUPPRESSED` libèrent la clé — `FAILED` la garde) |
| State transition | tout état non terminal → `CANCELLED` | EXPLICIT |
| Writes | `collection.action_status.status='CANCELLED'` + motif | EXPLICIT |
| Events | `COLLECTION_ACTION_CANCELLED` | EXPLICIT |
| Audit | requis (commande d'un utilisateur, D3) | EXPLICIT |
| Errors | aucune déclarée spécifiquement (au-delà des classes génériques) | EXPLICIT |
| Idempotency / déduplication | garde d'état : rejouer la **même** transition (action déjà `CANCELLED`) → **`SKIPPED`** ; transition réellement invalide (depuis `DONE`, `FAILED`, `SUPPRESSED`) → `ACTION_INVALID_TRANSITION` | EXPLICIT — `SKIPPED` : `ENGINE_CONTRACTS_V1.md` §5 (« Transition d'état \| garde d'état en base \| `SKIPPED` ») ; erreur : EC-11. **CORRIGÉ (traçabilité, 2026-10-04)** : la version antérieure disait `REPLAY`, étiqueté EXPLICIT d'après le *vocabulaire* `outcomes=('OK','REPLAY')` ; aucune source gelée ne le porte. Aucun changement métier ; l'issue `SKIPPED` est admise par l'amendement Application B10 |
| Dependencies | aucune externe | EXPLICIT |
| Open questions | aucune identifiée | — |
| Sources | `STATE_MACHINES_V1.md` §8 ; `INVARIANTS_V1.md` §7.1 ; `specs.py` |

### A6. `ExecuteDueAction` (worker, composé en 4 phases)

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `ExecuteDueAction{action_id}` | EXPLICIT |
| Actor | `SYSTEM` (worker, `entry=BACKGROUND`) | EXPLICIT |
| State(s) lus | `collection.action_status` (l'action `SCHEDULED`) ; `collection.attempts` (compteur de tentatives) | EXPLICIT |
| Facts requis | contact de référence, gabarit actif, variables autorisées (numéro de facture, `collectible_minor`, échéance, jours de retard, nom organisation/contact) — pour `REMINDER`/`EMAIL` (§8.1 étape 3) | EXPLICIT (§8.1) — mais ce sont des faits **niveau C** assemblés par l'Application (`TemplateResolver`, §14, couche Application), pas par le Domain lui-même |
| RuleDecision | Oui, **revalidation complète** (contexte D) | EXPLICIT (§8.1 étape 1, `reads=('rules.Evaluate',)`) |
| Champs RuleDecision consommés | **EXPLICIT — FERMÉ (OPEN-05/06)** : `outcome` (`SUPPRESS`→`SUPPRESSED` ; `DEFER`→replanification ; `PROCEED`→suite), `suppression_code` (si `SUPPRESS`), `retry_at` (si `DEFER`), et `overrides[]`/`exceptions_trace[]` pour un grant manuel. **Non consommés** : `requires_approval`, `levels.*` (déjà fixés à la création). | ACCEPTÉ : `collection.AuthorizeOverride` (même service qu'à la création, `specs.py` : « audit à la création puis à chaque vérification », mot pour mot G8) vérifie la **validité actuelle** du grant (G4 : acteur actif, rôle courant, organisation active, motif, exception encore contournable) — un FAIT, pas une décision. Ce fait est ensuite consommé par `rules.Evaluate`, seule autorité qui produit `exceptions_trace`/`overrides[]`/`outcome` (G3 : « l'autorité est recalculée à CHAQUE évaluation »). Pas de double source de vérité, même schéma que Risk→Priority (fournisseur de fait, jamais recalcul). Aucun changement de `calls` ni de Domain nécessaire. |
| Reads | `rules.Evaluate` | EXPLICIT |
| as_of | injecté | EXPLICIT |
| Preconditions | `scheduled_for <= maintenant` ; tentatives `< max_attempts` ; claim gardé (idempotence) | EXPLICIT |
| Decision | phase 1 (CLAIM) : revalidation complète + `SCHEDULED → EXECUTING` (ou `SUPPRESSED`/replanification) ; phase 2 (EFFECT) : `notifications.CreateNotification` dans SA transaction ; phase 3 (EXTERNAL) : envoi hors transaction ; phase 4 (FINALIZE) : `EXECUTING → DONE` (succès), `→ SCHEDULED` avec `next_retry_at` (échec transitoire), ou `→ FAILED` (tentatives épuisées) | EXPLICIT (§8.1, §8.3, §9 ; `specs.py` phases) |
| State transition | `SCHEDULED → EXECUTING` (phase 1) ; `EXECUTING → DONE / SCHEDULED(retry) / FAILED` (phase 4, mais **résultat asynchrone** — §8.1 étape 5 dit le résultat vient d'un événement, donc la transition finale n'est peut-être pas dans CE cas d'usage mais dans `OnNotificationResult` (A9) | OPEN — à clarifier : `ExecuteDueAction` s'arrête-t-il à `EXECUTING` (`emits=('COLLECTION_ACTION_SUPPRESSED',)` seulement — pas de `_EXECUTED`/`_FAILED` dans ses `emits` !), et c'est `OnNotificationResult` qui referme la boucle ? |
| Writes | `collection.action_status` (statut, `executed_at`?) ; `collection.attempts` (nouvelle tentative) | DERIVED |
| Events | `COLLECTION_ACTION_SUPPRESSED` **seulement** (confirmé par `specs.py` : `_EXECUTED`/`_FAILED` ne sont PAS dans les `emits` de cette UC) | EXPLICIT — renforce l'hypothèse ci-dessus : le résultat final passe par A9 |
| Audit | conditionnel, uniquement à chaque vérification d'un grant d'override (G8) | EXPLICIT |
| Errors | `TEMPLATE_UNAVAILABLE` | EXPLICIT |
| Idempotency / déduplication | claim gardé (pas `dedup_key` directement — DV4-4 sans impact ici) | EXPLICIT |
| Dependencies | `rules.Evaluate` ; `notifications.CreateNotification` (cross-module, sa transaction) ; `collection.attempts` | EXPLICIT |
| Open questions | la transition finale (`DONE`/`FAILED`) est-elle dans CE cas d'usage ou dans `OnNotificationResult` (A9) ? La revérification G4 est-elle un second appel au Rule Engine ou fait-elle partie de la même évaluation contexte D ? Comment les faits niveau C (`TemplateResolver`) sont-ils fournis au Domain — comme faits déjà résolus (façon Priority) ? | OPEN |
| Sources | `COLLECTION_ENGINE_V1.md` §8.1, §8.3, §9 ; `RULE_ENGINE_V1.md` §7, §3.3 ; Collection V1.2 §3.3, §4 (G1-G9) ; `specs.py` (phases + `emits` réels) |

### A7. `ReapActions` (job, watchdog `EXECUTING`)

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `ReapActions` (niveau C, job) | EXPLICIT |
| Actor | `SYSTEM` (`entry=BACKGROUND`, `tenant=ENUMERATOR`) | EXPLICIT |
| State(s) lus | `collection.action_status` (`EXECUTING` depuis plus de 15 min) ; `collection.attempts` | EXPLICIT |
| Facts requis | durée écoulée depuis le passage à `EXECUTING` (comparée à `as_of`, jamais une horloge lue par le Domain) | **ACCEPTÉ (OPEN-03)** : `EXPLICIT` — `ENGINE_CONTRACTS_V1.md` §EC-03 (`Reaper \| 5 min \| ... actions EXECUTING > 15 min`), cohérent avec §8.3. Le seuil de 15 min est une **règle métier du Domain** (le franchissement a une sémantique : « tentative transitoire échouée »), pas une simple optimisation de requête ; l'Application/`Reaper` peut pré-filtrer par SQL pour l'efficacité, sans que cela transfère la définition de la règle. Cadence du job (`Reaper`, 5 min) : Application/scheduler uniquement, hors Domain. |
| RuleDecision | Non | EXPLICIT (`reads=()`) |
| Champs RuleDecision consommés | — | — |
| Reads | aucune | EXPLICIT |
| as_of | injecté ; SEULE source de « maintenant » (jamais une horloge système, AR-02-équivalent attendu) | DERIVED |
| Preconditions | `EXECUTING` depuis `> 15 min` sans résultat | EXPLICIT |
| Decision | tentative transitoire échouée (worker interrompu) → nouvelle tentative recréée, **idempotente**, y compris si la notification n'a jamais été créée | EXPLICIT (§8.3) |
| State transition | `EXECUTING → SCHEDULED` (avec `next_retry_at`) ou reste `EXECUTING` si dans la fenêtre de tolérance | DERIVED |
| Writes | `collection.action_status`, `collection.attempts` | EXPLICIT (`atomic_effects`) |
| Events | aucun déclaré | EXPLICIT (`emits=()`) — **OPEN** : pas de `COLLECTION_ACTION_SCHEDULED` sur reprise ? à confirmer que c'est voulu (le job ne re-signale pas, seul le prochain `ExecuteDueAction` le fera) |
| Audit | aucun | EXPLICIT |
| Errors | aucune | EXPLICIT |
| Idempotency / déduplication | transition gardée (`lock_operation='ReapActions'`, verrou `G` — balayage global) | EXPLICIT |
| Dependencies | aucune externe | EXPLICIT |
| Open questions | absence d'événement émis en cas de reprise — **OPEN-04, en cours d'arbitrage séparé**. | OPEN-04 |
| Sources | `COLLECTION_ENGINE_V1.md` §8.3 ; `specs.py` |

### A8. `OnApprovalDecided`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | aucun (`command=None`, handler d'événement) | EXPLICIT |
| Actor | `SYSTEM` (réaction à `APPROVAL_GRANTED`/`APPROVAL_REJECTED`) | EXPLICIT |
| State(s) lus | `collection.action_status` (l'action `PENDING_APPROVAL` liée) | EXPLICIT |
| Facts requis | aucun fait externe nouveau | DERIVED |
| RuleDecision | **Non** — `reads=()` confirmé correct | **ACCEPTÉ (DV4-5)** : la revalidation de la cible (§6, STATE_MACHINES §8) appartient à `approvals.DecideApproval`, qui interroge `ApprovalTargetReader` (déjà implémenté par `collection.ReadApprovalTarget`) **avant** d'émettre `APPROVAL_GRANTED`. `OnApprovalDecided` reçoit une cible déjà revalidée ; sa transition est inconditionnelle. |
| Champs RuleDecision consommés | — (aucune RuleDecision consommée ici) | ACCEPTÉ |
| Reads | déclaré vide dans `specs.py`, confirmé correct | ACCEPTÉ (DV4-5) |
| as_of | injecté | EXPLICIT |
| Preconditions | l'action est `PENDING_APPROVAL` | EXPLICIT |
| Decision | `APPROVAL_GRANTED` → (re)validation puis `SCHEDULED` ; `APPROVAL_REJECTED` → `CANCELLED` (issue `APPROVAL_REJECTED`, pas de nouvelle proposition dans le cycle, §4 étape 4) | EXPLICIT (§6, STATE_MACHINES §8) |
| State transition | `PENDING_APPROVAL → SCHEDULED` ou `PENDING_APPROVAL → CANCELLED` | EXPLICIT |
| Writes | `collection.action_status.status` | EXPLICIT |
| Events | `COLLECTION_ACTION_SCHEDULED` ou `COLLECTION_ACTION_CANCELLED` | EXPLICIT |
| Audit | aucun | EXPLICIT |
| Errors | aucune | EXPLICIT |
| Idempotency / déduplication | reçu (idempotence événementielle standard) | EXPLICIT |
| Dependencies | `approvals` (émetteur de l'événement, revalide la cible avant `APPROVAL_GRANTED`) | ACCEPTÉ (DV4-5) |
| Open questions | aucune — résolue par DV4-5. À noter dans le texte de `COLLECTION_DOMAIN_V1.md` (pas dans un document gelé) : QUI revalide (`approvals`, pas `collection`). | — |
| Sources | `COLLECTION_ENGINE_V1.md` §6 ; `STATE_MACHINES_V1.md` §8 ; `specs.py` |

### A9. `OnNotificationResult`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | aucun (`command=None`, handler d'événement) | EXPLICIT |
| Actor | `SYSTEM` (réaction à `NOTIFICATION_SENT`/`NOTIFICATION_FAILED`) | EXPLICIT |
| State(s) lus | `collection.action_status` (via `source_action_id`) ; `collection.attempts` | EXPLICIT |
| Facts requis | résultat du fournisseur (livraison acceptée / erreur, classe d'erreur transitoire/permanente/configuration) | EXPLICIT (§8.1 étape 5, §9) |
| RuleDecision | Non | EXPLICIT (`reads=()`) |
| Champs RuleDecision consommés | — | — |
| Reads | aucune | EXPLICIT |
| as_of | injecté | EXPLICIT |
| Preconditions | action `EXECUTING` (ligne d'essai ouverte) | DERIVED |
| Decision | livraison acceptée → `DONE` (issue `SENT`) ; erreur transitoire → `SCHEDULED` avec `next_retry_at` (5 min/30 min/2 h) ; erreur permanente/configuration → `FAILED` (alerte responsable, hors Domain) ; gabarit introuvable → `FAILED` immédiat sans réessai | EXPLICIT (§8.1, §9) |
| State transition | `EXECUTING → DONE` / `EXECUTING → SCHEDULED` (retry) / `EXECUTING → FAILED` | EXPLICIT (STATE_MACHINES §8) — **confirme l'hypothèse d'A6** : c'est BIEN ici que la boucle se referme, pas dans `ExecuteDueAction` |
| Writes | `collection.action_status`, `collection.attempts` (nouvelle ligne de tentative en cas d'erreur transitoire) | EXPLICIT |
| Events | `COLLECTION_ACTION_EXECUTED`, `COLLECTION_ACTION_FAILED`, `COLLECTION_ACTION_SCHEDULED` | EXPLICIT |
| Audit | aucun | EXPLICIT |
| Errors | aucune déclarée (la classification d'erreur est un fait reçu, pas une erreur de ce cas d'usage) | EXPLICIT |
| Idempotency / déduplication | reçu | EXPLICIT |
| Dependencies | `notifications` (émetteur) | EXPLICIT |
| Open questions | aucune majeure ; confirme la répartition A6/A9 ci-dessus | — |
| Sources | `COLLECTION_ENGINE_V1.md` §8.1, §9 ; `STATE_MACHINES_V1.md` §8 ; `specs.py` |

### A10. `ClaimTask` (ajouté par B8, AUDIT-01)

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `ClaimTask{action_id}` (niveau C) | EXPLICIT (`ENGINE_CONTRACTS_V1.md` §EC-11) |
| Actor | `USER`, membre actif du pool, rôle courant ≥ `assigned_role` de l'action | EXPLICIT (`COLLECTION_ENGINE_V1.md` §5 : « pool comprend les utilisateurs actifs dont le rôle est au moins égal au rôle du pool ») |
| State(s) lus | `collection.action_status` (action `SCHEDULED`, `type ∈ {CALL_TASK, FOLLOW_UP, ESCALATION}`, `assigned_to IS NULL`) | EXPLICIT (`DATA_CONTRACT_V1.md` §6.1 CK) |
| Facts requis | rôle courant de l'acteur (appartenance au pool) | DERIVED |
| RuleDecision | **Non** | DERIVED — absente de la ligne EC-11 (contrairement à `CreateCollectionAction`/`ExecuteDueAction`, qui mentionnent explicitement une revalidation) |
| Champs RuleDecision consommés | — | — |
| Reads | aucune | EXPLICIT |
| as_of | injecté, non exploité (aucune règle à évaluer) | DERIVED |
| Preconditions | acteur actif, rôle courant ≥ rôle du pool ; `assigned_to IS NULL` au moment de l'écriture | EXPLICIT |
| Decision | `UPDATE collection_actions SET assigned_to=:actor WHERE id=:action_id AND assigned_to IS NULL` — assignation atomique, une seule réclamation gagne | **EXPLICIT, mot pour mot** (EC-11) |
| State transition | **aucune** — l'action reste `SCHEDULED` ; seul `assigned_to` change | EXPLICIT (`INVARIANTS_V1.md` §7.1 « 2 Modifier » : `assigned_to` est une colonne modifiable, pas une transition ; absent de `STATE_MACHINES_V1.md` §8 en conséquence — cohérent, pas un oubli) |
| Writes | `collection.action_status.assigned_to` | EXPLICIT |
| Events | aucun déclaré (`emits=()`, B8/`specs.py`) | DERIVED — **OPEN (AUDIT-01.a)** : absence de preuve d'un événement ≠ preuve d'absence |
| Audit | `REQUIRED` au niveau Application (régime générique D3 : commande d'un utilisateur, B8/`specs.py`) | EXPLICIT (registre) — **OPEN (AUDIT-01.b)** : aucune mention métier d'un audit dédié au-delà de ce régime générique dans les sources |
| Errors | `CONCURRENT_MODIFICATION` | EXPLICIT (EC-11) |
| Idempotency / déduplication | une seule réclamation gagne (`UPDATE … WHERE assigned_to IS NULL`) ; réclamation par le même acteur déjà assigné → probablement `REPLAY` (garde d'état), par un autre acteur → `CONCURRENT_MODIFICATION` | EXPLICIT/DERIVED (EC-11 ; cohérent avec `GLOBAL_TEST_MATRIX_V1.md` CO-07 : « réclamation simultanée par deux membres : une seule gagne ») |
| Dependencies | aucune externe | EXPLICIT |
| Open questions | **AUDIT-01.a** (événement éventuel), **AUDIT-01.b** (audit dédié éventuel) — réserves ouvertes, non closes par B8 | OPEN |
| Sources | `ENGINE_CONTRACTS_V1.md` §EC-11 ; `COLLECTION_ENGINE_V1.md` §5, §14 ; `DATA_CONTRACT_V1.md` §6.1 ; `INVARIANTS_V1.md` §7.1 ; `GLOBAL_TEST_MATRIX_V1.md` CO-07 ; registre (`commands.py`, `locks.py`, B8) |

### A11. `CompleteTask` (ajouté par B8, AUDIT-01)

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `CompleteTask{action_id, outcome, outcome_note?}` (niveau C) | EXPLICIT (EC-11) |
| Actor | `USER` — **assigné OU membre du pool** ; la réclamation préalable via `ClaimTask` n'est **pas** une contrainte métier | **EXPLICIT, mot pour mot** (`STATE_MACHINES_V1.md` §8, ligne `SCHEDULED → DONE` : « Déclencheur : `USER` (assigné ou membre du pool) ») |
| State(s) lus | `collection.action_status` (action `SCHEDULED`, `type ∈ {CALL_TASK, FOLLOW_UP, ESCALATION}`) | EXPLICIT |
| Facts requis | aucun fait externe ; l'issue est fournie par l'exécutant lui-même | DERIVED |
| RuleDecision | **Non** — « revalidation non requise (l'action humaine est déjà accomplie) » | **EXPLICIT, mot pour mot** (`STATE_MACHINES_V1.md` §8) — contraste net avec `ExecuteDueAction` (A6, « revalidation complète ») |
| Champs RuleDecision consommés | — | — |
| Reads | aucune | EXPLICIT |
| as_of | injecté, non exploité | DERIVED |
| Preconditions | acteur = `assigned_to` OU (actif, rôle courant ≥ `assigned_role`) ; `outcome` fourni, appartenant au sous-ensemble « tâche humaine » de la liste fermée (`CONTACTED`, `NO_ANSWER`, `PROMISE_OBTAINED`, `DISPUTE_RAISED`, `REFUSED`, `WRONG_CONTACT`, `OTHER`) | EXPLICIT (`COLLECTION_ENGINE_V1.md` §8.2, §13 ; `DATA_CONTRACT_V1.md` §6.1 CK `status='DONE' ⇒ outcome IS NOT NULL`) |
| Decision | pas de calcul métier : validation de la garde, puis écriture de l'`outcome` fourni par l'exécutant | DERIVED |
| State transition | `SCHEDULED → DONE` | EXPLICIT |
| Writes | `collection.action_status.status`, `.outcome` (obligatoire), `.outcome_note` (facultatif), `.executed_at` | EXPLICIT (STATE_MACHINES §8 « Effets » ; `DATA_CONTRACT_V1.md` §6.1 CK) |
| Events | `COLLECTION_ACTION_EXECUTED` | **EXPLICIT** (STATE_MACHINES §8 « Effets » — même événement que la complétion d'un envoi automatique, A9) |
| Effet dérivé (non automatique) | `outcome = PROMISE_OBTAINED`/`DISPUTE_RAISED` **suggère** à l'interface de créer la promesse/le litige, sans les créer automatiquement | EXPLICIT (§8.2, répété STATE_MACHINES §8) |
| Audit | `REQUIRED` au niveau Application (régime générique D3, B8/`specs.py`) | EXPLICIT (registre) — **OPEN (AUDIT-01.c)** : aucune mention métier d'un audit dédié au-delà de ce régime générique |
| Errors | `ACTION_INVALID_TRANSITION`, `INSUFFICIENT_ROLE` | EXPLICIT (EC-11) |
| Idempotency / déduplication | garde d'état : rejouer la **même** transition (tâche déjà `DONE`) → **`SKIPPED`** ; transition réellement invalide (action `CANCELLED`, `FAILED`, `SUPPRESSED`, ou `REMINDER`) → `ACTION_INVALID_TRANSITION` | EXPLICIT — `SKIPPED` : `ENGINE_CONTRACTS_V1.md` §5 ; erreur : EC-11. **CORRIGÉ (traçabilité, 2026-10-04)** : la version antérieure disait « `DONE` = `REPLAY` », étiqueté « EXPLICIT (EC-11) » ; la ligne EC-11 de `CompleteTask` ne dit pas cela (« garde d'état », erreurs `ACTION_INVALID_TRANSITION` · `INSUFFICIENT_ROLE`). Aucun changement métier ; `SKIPPED` admis par B10 |
| Dependencies | aucune externe ; `collection_action_attempts` **non concerné** (cette table documente les tentatives d'envoi automatique, jamais mentionnée en lien avec `CompleteTask`) | DERIVED |
| Open questions | **AUDIT-01.c** (audit dédié éventuel) — réserve ouverte, non close par B8 | OPEN |
| Sources | `ENGINE_CONTRACTS_V1.md` §EC-11 ; `STATE_MACHINES_V1.md` §8 ; `COLLECTION_ENGINE_V1.md` §8.2, §13, §14 ; `DATA_CONTRACT_V1.md` §6.1 ; registre (B8) |

### A12. `RescheduleAction` (ajouté par B8, AUDIT-01)

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `RescheduleAction{action_id, target}` (niveau C) | EXPLICIT (EC-11) |
| Actor | `USER` (rôle non précisé par les sources) | EXPLICIT (`COLLECTION_ENGINE_V1.md` §7 : « replanifiée par un utilisateur ») |
| State(s) lus | `collection.action_status` — action `status ∈ {PROPOSED, SCHEDULED}`, **tous types** (pas seulement les tâches humaines) | **EXPLICIT** — `INVARIANTS_V1.md` §7.1 « 2 Modifier » (« `scheduled_for` tant que `PROPOSED`/`SCHEDULED` ») tranche la tension entre §7 (« `SCHEDULED` », prose d'exemple incomplète) et `ENGINE_CONTRACTS_V1.md` §EC-11 (« action non terminale », ligne groupée avec `CancelAction`, sur-généralisée par compression de tableau) — voir note ci-dessous |
| Facts requis | aucun fait externe | DERIVED |
| RuleDecision | **Non** — « repasse par les mêmes règles » renvoie au `SlotCalculator` (fenêtre de communication, jour ouvré, lissage), **pas** au Rule Engine | DERIVED (absence de mention dans EC-11 ; §7 est entièrement consacré au `SlotCalculator`) |
| Champs RuleDecision consommés | — | — |
| Reads | aucune règle métier ; dépendance fonctionnelle au `SlotCalculator` (fonction pure, §14) | EXPLICIT |
| as_of | injecté, non exploité | DERIVED |
| Preconditions | `status ∈ {PROPOSED, SCHEDULED}` ; nouveau créneau valide selon les règles du `SlotCalculator` | EXPLICIT |
| Decision | `SlotCalculator` recalcule un `scheduled_for` valide à partir de la cible demandée (mêmes règles qu'à la création : fenêtre, jour ouvré, lissage — sauf tâches humaines/escalades, §7 point 5, qui n'ont pas de fenêtre de communication) | EXPLICIT (§7 points 1-5) |
| State transition | **aucune** — seul `scheduled_for` change, le `status` reste inchangé | DERIVED (même schéma qu'A10 `ClaimTask`) |
| Writes | `collection.action_status.scheduled_for` | EXPLICIT |
| Events | aucun déclaré (`emits=()`, B8/`specs.py`) | DERIVED — **OPEN (AUDIT-01.e)** |
| Audit | `REQUIRED` au niveau Application (régime générique D3, B8/`specs.py`) | EXPLICIT (registre) |
| Errors | `ACTION_INVALID_TRANSITION` | EXPLICIT (EC-11) — **OPEN (AUDIT-01.f)** : aucune erreur déclarée pour un créneau cible invalide (ex. date passée) ; lacune normative potentielle, pas seulement une absence de preuve |
| Idempotency / déduplication | garde d'état | EXPLICIT (EC-11) |
| Dependencies | `SlotCalculator` (fonction pure) | EXPLICIT |
| Open questions | **AUDIT-01.e** (événement éventuel), **AUDIT-01.f** (erreur de créneau invalide, réserve de nature différente — possible lacune normative) — réserves ouvertes, non closes par B8 | OPEN |
| Sources | `ENGINE_CONTRACTS_V1.md` §EC-11 ; `COLLECTION_ENGINE_V1.md` §7, §14 ; `INVARIANTS_V1.md` §7.1 ; registre (B8) |

**Note — résolution de la tension d'état d'entrée (A12).** Trois sources semblaient diverger : `COLLECTION_ENGINE_V1.md`
§7 dit « `SCHEDULED` » (exemple, incomplet) ; `ENGINE_CONTRACTS_V1.md` §EC-11 dit « action non terminale » (ligne
groupée avec `CancelAction`, dont c'est la vraie précondition — confirmée `STATE_MACHINES_V1.md` §8 : « tout état
non terminal → `CANCELLED` »). Aucune des deux n'est fausse : ce n'est pas une contradiction à départager par
préférence de source, c'est une règle de mutabilité de champ (`INVARIANTS_V1.md` §7.1) qui referme les deux
descriptions imprécises. `PENDING_APPROVAL` et `EXECUTING` sont donc explicitement exclus de `RescheduleAction`,
contrairement à `CancelAction` qui les accepte.

---

## Sous-domaine B — Hold (3 cas d'usage, DV4-2 résolu)

### B1. `PlaceHold`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `PlaceHold` (niveau C : portée, cible, `automation_id?`, `kind`, `reason`, `starts_at`, `ends_at?`) | DERIVED (`DATA_CONTRACT_V1.md` §6.3, colonnes non-générées) |
| Actor | `USER`, rôle `MANAGER` ou plus | EXPLICIT (STATE_MACHINES §9, INVARIANTS §7.2) |
| State(s) lus | `collection.hold_status` (pour la contrainte de chevauchement) | **CORRIGÉ (audit Phase 6)** : la mention antérieure de `collection.action_status` était incohérente avec la résolution C5 (ci-dessous) et avec `specs.py` (`PlaceHold.domain=('collection.hold_status',)` seul) — retirée. |
| Facts requis | cohérence portée/cible (`INVOICE⇒invoice_id`, `CUSTOMER⇒customer_id`, `ORGANIZATION⇒aucun des deux`) | EXPLICIT (Data Contract CK) |
| RuleDecision | Non | EXPLICIT (`reads=()`) |
| Champs RuleDecision consommés | — | — |
| Reads | aucune | EXPLICIT |
| as_of | injecté (`starts_at` par défaut = maintenant) | DERIVED |
| Preconditions | rôle `MANAGER`+ ; motif non vide ; portée cohérente avec la cible ; pas de chevauchement (même cible + même `automation_id` + même `kind`, plages qui se recoupent, sur les holds `ACTIVE`) | EXPLICIT (STATE_MACHINES §9, INVARIANTS §7.2, Data Contract EXCLUDE) |
| Decision | créer le hold `ACTIVE` ; la suspension des actions concernées est déléguée à `SuppressOnHoldPlaced` (C5), pas faite ici | **CORRIGÉ (audit Phase 6)** |
| State transition | `(création) → ACTIVE` (pour le hold lui-même seulement — la state machine §9 décrit l'effet MÉTIER global du hold, réparti sur deux transactions distinctes : celle-ci pour `collection.hold_status`, celle de C5 pour `collection.action_status`) | EXPLICIT |
| Writes | `collection.hold_status` (nouvelle ligne) SEULEMENT | **CORRIGÉ (audit Phase 6)** : ne touche jamais `collection.action_status` — cohérent avec `specs.py` et avec C5. |
| Events | `COLLECTION_HOLD_PLACED` SEULEMENT | **CORRIGÉ (audit Phase 6)** : `COLLECTION_ACTION_SUPPRESSED` est émis par `SuppressOnHoldPlaced` (C5), jamais par `PlaceHold` — confirmé par `specs.py` (`PlaceHold.emits=('COLLECTION_HOLD_PLACED',)` seul). |
| Audit | requis (D3 : holds explicitement listés) | EXPLICIT |
| Errors | `HOLD_REASON_REQUIRED`, `HOLD_OVERLAP`, `HOLD_TARGET_MISMATCH`, `INSUFFICIENT_ROLE` | EXPLICIT (INVARIANTS §7.2 — `HOLD_NOT_ACTIVE` s'applique plutôt à `ReleaseHold`) |
| Idempotency / déduplication | clé d'idempotence (commande standard) + contrainte `EXCLUDE` (pas de `dedup_key` façon action) | EXPLICIT |
| Dependencies | aucune externe au module | EXPLICIT |
| Open questions | aucune — résolue par C5 (confirmé, audit Phase 6) | — |
| Sources | `DATA_CONTRACT_V1.md` §6.3 ; `STATE_MACHINES_V1.md` §9 ; `INVARIANTS_V1.md` §7.2 ; `specs.py` |

### B2. `ReleaseHold`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `ReleaseHold` (niveau C : identifiant du hold, `release_reason`) | DERIVED |
| Actor | `USER`, rôle `MANAGER` ou plus | EXPLICIT |
| State(s) lus | `collection.hold_status` (le hold ciblé) | EXPLICIT |
| Facts requis | aucun | DERIVED |
| RuleDecision | Non | EXPLICIT |
| Reads | aucune | EXPLICIT |
| as_of | injecté | EXPLICIT |
| Preconditions | le hold est `ACTIVE` (sinon `HOLD_NOT_ACTIVE`) ; `release_reason` non vide | EXPLICIT |
| Decision | libérer le hold ; reprise des exécutions suspendues pour cette cause | EXPLICIT (STATE_MACHINES §9) |
| State transition | `ACTIVE → RELEASED` | EXPLICIT |
| Writes | `collection.hold_status` (`status`, `released_by`, `released_at`, `release_reason`) | EXPLICIT (Data Contract, colonnes immuables/modifiables) |
| Events | `COLLECTION_HOLD_RELEASED` (`cause='RELEASED'`) | EXPLICIT |
| Audit | requis | EXPLICIT |
| Errors | `HOLD_NOT_ACTIVE`, `INSUFFICIENT_ROLE` | EXPLICIT |
| Idempotency / déduplication | garde d'état (`ACTIVE` requis) | EXPLICIT |
| Dependencies | aucune | EXPLICIT |
| Open questions | même question que B1 : la reprise des exécutions suspendues (et la remise en état des actions `SUPPRESSED(HOLD_ACTIVE)`, si applicable) est-elle dans CETTE transaction ou déléguée à un mécanisme réactif ? Le Collection Engine V1.1 (§11) dit « l'action SUPPRESSED libère sa clé. Lorsque la cause est levée, l'Automation Engine réévalue » — suggère que la reprise n'est PAS automatique côté action, seulement côté exécution d'automatisation | DERIVED (mais confirme plutôt « pas de réaction automatique côté action » — donc pas un OPEN aussi grave que pour B1) |
| Sources | `DATA_CONTRACT_V1.md` §6.3 ; `STATE_MACHINES_V1.md` §9 ; `INVARIANTS_V1.md` §7.2 ; `COLLECTION_ENGINE_V1.md` §11 ; `specs.py` |

### B3. `HoldExpiryScan`

| Champ | Valeur | Niveau |
|---|---|---|
| Command | `HoldExpiryScan` (niveau C, job) | EXPLICIT |
| Actor | `SYSTEM` (Scheduler) | EXPLICIT (STATE_MACHINES §9) |
| State(s) lus | `collection.hold_status` (`ACTIVE` avec `ends_at <= maintenant`) | EXPLICIT |
| Facts requis | aucun | DERIVED |
| RuleDecision | Non | EXPLICIT |
| Reads | aucune | EXPLICIT |
| as_of | injecté ; SEULE source de « maintenant » | DERIVED |
| Preconditions | `ends_at <= as_of` sur un hold `ACTIVE` | EXPLICIT |
| Decision | **matérialisation** de l'expiration — ne DÉCIDE rien de nouveau : le hold était déjà hors-vigueur dès `ends_at` dépassé (règle de lecture indépendante du balayage, Data Contract) ; ce job constate et clôt | EXPLICIT (Data Contract, STATE_MACHINES §9 : « indépendamment du balayage EXPIRED ») |
| State transition | `ACTIVE → EXPIRED` | EXPLICIT |
| Writes | `collection.hold_status.status` | EXPLICIT |
| Events | `COLLECTION_HOLD_RELEASED` (`cause='EXPIRED'`) | EXPLICIT |
| Audit | aucun (transition temporelle du Scheduler, D3) | EXPLICIT (INVARIANTS §3, C13 : « transitions purement temporelles… sans doublon d'audit ») |
| Errors | aucune | EXPLICIT |
| Idempotency / déduplication | `UPDATE … WHERE état = ancien` (garde d'état, cadence 5 min, rattrapage après arrêt) | EXPLICIT (`ENGINE_CONTRACTS_V1.md`) |
| Dependencies | aucune | EXPLICIT |
| Open questions | aucune | — |
| Sources | `DATA_CONTRACT_V1.md` §6.3 ; `STATE_MACHINES_V1.md` §9 ; `INVARIANTS_V1.md` §3, §7.2 ; `ENGINE_CONTRACTS_V1.md` ; `specs.py` |

---

## Sous-domaine C — Suppression / réactions aux événements (7 cas d'usage)

Tous partagent la MÊME forme (`EVENT → relire la cible → condition de suppression → SUPPRESSED ou no-op`), mais avec
des **conditions individuelles distinctes** — comme demandé, chacune est spécifiée séparément plutôt que fusionnée.
Tous : `reads=()`, pas de `RuleDecision`, `entry=REACTION`, `lock_operation='CollectionReaction'`, aucun audit
(D3 : réaction événementielle), idempotence par reçu (`event_receipts`).

**DV4-6 ACCEPTÉ** pour les 7 : aucun ne rappelle `rules.Evaluate`. Le préambule §12 sur la revalidation contexte D
décrit la discipline générale du moteur (créée à la création, avant exécution) ; ces 7 réactions implémentent un
raccourci direct où l'événement lui-même EST la condition de l'exception L1, sans réévaluation dynamique — la
revalidation complète reste garantie en aval par `ExecuteDueAction` (contexte D réel, `reads=('rules.Evaluate',)`).

### C1. `SuppressOnInvoicePaid` — événement `INVOICE_PAID`

| Champ | Valeur | Niveau |
|---|---|---|
| State(s) lus | `collection.action_status` — actions concernées : `PROPOSED`, `SCHEDULED`, `PENDING_APPROVAL` de la facture | EXPLICIT (§12, préambule « Actions concernées ») |
| Facts requis | aucun au-delà de l'événement (`invoice_id`) | EXPLICIT |
| Preconditions | l'action est dans un des trois états concernés | EXPLICIT |
| Decision | → `SUPPRESSED` (`PAID`) | EXPLICIT (§12) |
| Writes / Events | `collection.action_status.status='SUPPRESSED'` ; `COLLECTION_ACTION_SUPPRESSED` | EXPLICIT |
| Idempotency | reçu ; ne rappelle pas `rules.Evaluate` | **ACCEPTÉ (DV4-6)** |
| Sources | `COLLECTION_ENGINE_V1.md` §12 ; `specs.py` |

### C2. `SuppressOnInvoiceEnded` — événements `INVOICE_VOIDED`, `INVOICE_CANCELLED`

| Champ | Valeur | Niveau |
|---|---|---|
| Decision | → `SUPPRESSED` (`VOIDED`) | EXPLICIT (§12) |
| Reste | identique à C1 (mêmes états concernés, même mécanique) | DERIVED |
| Sources | `COLLECTION_ENGINE_V1.md` §12 ; `specs.py` |

### C3. `SuppressOnInvoiceDisputed` — événement `INVOICE_DISPUTED`

| Champ | Valeur | Niveau |
|---|---|---|
| Facts requis | `collectible_minor` de la facture au moment de la réaction (pas seulement l'événement) | EXPLICIT (§12 : « si `collectible_minor = 0`) |
| Decision | **conditionnelle** : → `SUPPRESSED` (`DISPUTED`) **seulement si** `collectible_minor = 0` (litige total) ; sinon aucune suppression (litige partiel : le recouvrement continue sur le montant recouvrable, D1) | EXPLICIT (§12, D1) |
| Reads | `invoices.InvoiceFacts` (`collectible_minor`) | **ACCEPTÉ ET APPLIQUÉ (DV4-8, AM-03)** : le payload `INVOICE_DISPUTED` (`dispute_id`, `disputed_amount_minor?`) ne suffisait pas (pas d'`outstanding_minor` non plus). Amendement de `commands.py` (`calls=['invoices.InvoiceFacts']`), régénéré, vérifié 0 erreur ; `application_freeze` B7 journalisé. `invoices.InvoiceFacts` était déjà un module-level dependency de `collection` (`modules.py`) — seul `commands.py` manquait. |
| Sources | `COLLECTION_ENGINE_V1.md` §12, D1 ; `specs.py` |

### C4. `SuppressOnPromiseCreated` — événement `PROMISE_CREATED`

| Champ | Valeur | Niveau |
|---|---|---|
| Decision | → `SUPPRESSED` (`PROMISE_ACTIVE`) — pour la **portée** de la promesse (facture spécifique ou, à défaut, toutes les factures ouvertes du client, `promise_scope`) | DERIVED (§12 + `RULE_ENGINE_V1.md` §2.2 `invoice.promise_scope`) |
| Vérifié | payload de `PROMISE_CREATED` (`INVARIANTS_V1.md` §10) : `invoice_id?`, `customer_id`, `promised_amount_minor`, `promised_date` — **la portée est directement lisible dans l'événement** (`invoice_id` présent ⇒ `INVOICE` ; absent ⇒ `CUSTOMER`), pas besoin de relire `promises.PromiseFacts` pour CETTE distinction | DERIVED — réduit l'OPEN |
| Open questions | **ACCEPTÉ (DV4-9)** : `collection_actions.customer_id` est une colonne `NN` toujours renseignée (`DATA_CONTRACT_V1.md` §6.1) — pour la portée `CUSTOMER`, filtrage DIRECT de `collection.action_status WHERE customer_id = :customer_id AND status IN (PROPOSED, SCHEDULED, PENDING_APPROVAL)`, aucune énumération de factures ni orchestration Application (contrairement à Priority, qui énumère des entités d'un AUTRE module). `reads=()` reste correct. | ACCEPTÉ — aucun amendement de registre |
| Sources | `COLLECTION_ENGINE_V1.md` §12 ; `RULE_ENGINE_V1.md` §2.2 ; `specs.py` |

### C5. `SuppressOnHoldPlaced` — événement `COLLECTION_HOLD_PLACED`

| Champ | Valeur | Niveau |
|---|---|---|
| Decision | → `SUPPRESSED` (`HOLD_ACTIVE`) **pour la portée du hold** (`INVOICE`/`CUSTOMER`/`ORGANIZATION`, `automation_id` si renseigné) | EXPLICIT (§12 : « pour la portée du hold ») |
| Confirme | l'hypothèse d'B1 : c'est **CE** cas d'usage, réactif, qui suspend effectivement les actions — pas `PlaceHold` lui-même, qui ne touche que `collection.hold_status` | DERIVED — **résout partiellement l'OPEN de B1** |
| Sources | `COLLECTION_ENGINE_V1.md` §12 ; `specs.py` (confirmé : `PlaceHold.domain=('collection.hold_status',)` seul, `SuppressOnHoldPlaced.domain=('collection.action_status',)` seul) |

### C6. `SuppressOnCustomerInactive` — événements `CUSTOMER_DEACTIVATED`, `CUSTOMER_ARCHIVED`

| Champ | Valeur | Niveau |
|---|---|---|
| Decision | → `SUPPRESSED` (`CUSTOMER_INACTIVE` ou `CUSTOMER_ARCHIVED`, selon l'événement) | EXPLICIT (§12) |
| Sources | `COLLECTION_ENGINE_V1.md` §12 ; `RULE_ENGINE_V1.md` §3 exceptions 2-3 ; `specs.py` |

### C7. `SuppressOnOrgSuspended` — événements `ORGANIZATION_SUSPENDED`, `ORGANIZATION_CLOSED`

| Champ | Valeur | Niveau |
|---|---|---|
| Decision | → `SUPPRESSED` (`ORG_INACTIVE`) pour les deux événements | EXPLICIT pour `ORGANIZATION_SUSPENDED` (§12) ; **ACCEPTÉ (DV4-7)** pour `ORGANIZATION_CLOSED`, traité identiquement |
| Open questions | aucune — résolue par DV4-7. Amendement `COLLECTION_ENGINE_V1.md` §12 (ajouter `ORGANIZATION_CLOSED` à la table) en attente, opération séparée. | — |
| Sources | `COLLECTION_ENGINE_V1.md` §12 ; `INVARIANTS_V1.md` §10 (événement `ORGANIZATION_CLOSED` catalogué, gelé) ; `specs.py` |

---

## Arbitrage DV4-4 → DV4-8 (verrouillé)

Chaque entrée : Question → Sources → Arbitrage → Rationale → Impact → Amendement requis.

### DV4-4 — Formule de `dedup_key`

- **Question** : `dedup_key` inclut-il `:R{occurrence}` ou non ?
- **Sources** : `COLLECTION_ENGINE_V1.md` §4 (avec occurrence, précision C4 déjà intégrée, §19) ; `INVARIANTS_V1.md` §7.1 (sans).
- **Arbitrage** : **ACCEPTÉ** — `dedup_key = {invoice_id}:{type}:L{level}:C{cycle}:R{occurrence}`.
- **Rationale** : `INVARIANTS_V1.md` §7.1 est considéré comme obsolète par rapport à la correction C4, jamais répercutée dans ce document après coup. Sans occurrence, une répétition d'étape explicitement définie (§17 point 3) tomberait systématiquement en `REPLAY`, ce qui contredirait la capacité de répétition documentée.
- **Impact** : préserve la capacité de répéter une étape lorsque l'occurrence change ; aucun autre cas d'usage de cette matrice n'est affecté hormis A1 (référence directe).
- **Amendement requis** : **oui** — `INVARIANTS_V1.md` §7.1. **APPLIQUÉ (AM-01, 2026-09-26)**, journalisé `DATA_CONTRACT_V1.md` #25. Vérification interne : aucune autre occurrence de la formule sans occurrence trouvée dans `INVARIANTS_V1.md`.

### DV4-5 — `OnApprovalDecided` et le Rule Engine

- **Question** : `OnApprovalDecided` doit-il rappeler `rules.Evaluate` avant `PENDING_APPROVAL → SCHEDULED` ?
- **Sources** : `COLLECTION_ENGINE_V1.md` §6 (table, ligne « Cible résolue pendant l'attente… `DecideApproval` vérifie la cible au moment de décider, C6 ») ; `specs.py` (`ReadApprovalTarget` implémente déjà `approvals.ApprovalTargetReader`).
- **Arbitrage** : **ACCEPTÉ avec clarification documentaire** — `OnApprovalDecided` ne rappelle PAS `rules.Evaluate`.
- **Rationale** : la revalidation de la cible appartient à `approvals.DecideApproval`, qui interroge `ApprovalTargetReader` **avant** d'émettre `APPROVAL_GRANTED`. Par le temps où `OnApprovalDecided` réagit, la cible est déjà revalidée ; ajouter un second appel serait redondant.
- **Impact** : `specs.py` (`reads=()`) reste correct tel quel, aucune correction de registre nécessaire.
- **Amendement requis** : **aucun** sur un document gelé. Une clarification (qui revalide, et où) devra figurer dans le texte de `COLLECTION_DOMAIN_V1.md` lui-même.

### DV4-6 — Revalidation contexte D pour les 7 `SuppressOn*`

- **Question** : le préambule §12 (revalidation Rule Engine, contexte D) engage-t-il littéralement les 7 réactions, malgré `reads=()` partout ?
- **Sources** : `COLLECTION_ENGINE_V1.md` §12 préambule + table ; `specs.py` (les 7).
- **Arbitrage** : **ACCEPTÉ** — les 7 `SuppressOn*` ne rappellent pas le Rule Engine.
- **Rationale** : l'événement constitue lui-même le fait déclencheur (une des 13 exceptions L1, câblée directement) ; la revalidation complète intervient dans le flux d'exécution approprié (`ExecuteDueAction`, contexte D réel, qui lui déclare `reads=('rules.Evaluate',)`). Défense en profondeur, pas redondance requise en amont.
- **Impact** : les 7 réactions restent des raccourcis directs event→suppression, sans dépendance au Rule Engine.
- **Amendement requis** : **aucun** sur un document gelé. Clarification dans `COLLECTION_DOMAIN_V1.md`.

### DV4-7 — `ORGANIZATION_CLOSED`

- **Question** : omission de rédaction dans `COLLECTION_ENGINE_V1.md` §12, ou traitement volontairement différent de `ORGANIZATION_SUSPENDED` ?
- **Sources** : `INVARIANTS_V1.md` §10 (événement catalogué et gelé, payload `from_status`/`to_status`) ; `COLLECTION_ENGINE_V1.md` §12 (ne mentionne que `_SUSPENDED`) ; `specs.py` (traite déjà les deux identiquement).
- **Arbitrage** : **ACCEPTÉ** — `ORGANIZATION_CLOSED` traité comme `ORGANIZATION_SUSPENDED` pour Collection : `SUPPRESSED(ORG_INACTIVE)`.
- **Rationale** : une organisation `CLOSED` est au moins aussi terminale que `SUSPENDED` ; aucune source ne suggère un traitement différent.
- **Impact** : `specs.py` a déjà raison ; c'est `COLLECTION_ENGINE_V1.md` qui est incomplet.
- **Amendement requis** : **oui** — `COLLECTION_ENGINE_V1.md` §12. **APPLIQUÉ (AM-02, 2026-09-26)**, journalisé `DATA_CONTRACT_V1.md` #26. Découverte en vérifiant la cohérence avec les state machines (demandée pour AM-02) : la décision était **déjà validée** ailleurs (`STATE_MACHINES_V1.md` §1 ligne 277 + note S10, Architecture technique TD59) — ce n'était pas une nouvelle règle, seulement `COLLECTION_ENGINE_V1.md` §12 était resté incomplet.

### DV4-8 — `collectible_minor` absent du payload `INVOICE_DISPUTED`

- **Question** : `SuppressOnInvoiceDisputed` a besoin de `invoice.collectible_minor`, absent du payload de l'événement (`dispute_id`, `disputed_amount_minor?`) et de `specs.py` (`reads=()`). D'où vient-il ?
- **Sources** : `INVARIANTS_V1.md` §10 (payload) ; `COLLECTION_ENGINE_V1.md` §12, D1 ; `specs.py`.
- **Arbitrage** : **ACCEPTÉ sur le plan architectural** — `SuppressOnInvoiceDisputed` doit disposer d'une lecture `invoices.InvoiceFacts`.
- **Rationale** : ni le payload de l'événement ni une dérivation locale (il manque aussi `outstanding_minor`) ne permettent d'obtenir `collectible_minor` sans lecture. Ce n'est pas une question de préférence architecturale : la règle métier (D1, §12) dépend d'une donnée que seule une lecture peut fournir.
- **Impact** : c'est le point le plus sérieux des cinq — un écart réel entre un contrat déjà généré et la règle métier qui en dépend, pas une simple question de compréhension.
- **Amendement requis** : **oui**, opération séparée et journalisée, distincte de la décision elle-même. **APPLIQUÉ (AM-03, 2026-09-26)** : contrat `invoices.InvoiceFacts` vérifié (`collectible_minor: int` présent, frozen tranche-1, inchangé) ; `invoices.InvoiceFacts` était déjà un module-level dependency de `collection` (`modules.py`, `deps`/`READS`) — seul `commands.py` (`calls=` du cas d'usage précis) manquait, contrairement à B5/B6 qui touchaient aussi `modules.py`. Régénéré (`build_registry`/`gen_contracts`/`gen_application`, 0 erreur), journalisé `application_freeze.py` amendement B7, gel réécrit (`amendments=7`).

---

## Points arbitrés hors de la passe DV4-4→DV4-8 (OPEN-01 à OPEN-06)

| # | Sujet | Où |
|---|---|---|
| OPEN-01 (DV4-9) | **ACCEPTÉ** — filtrage direct de `collection_actions` par `customer_id` ; aucune orchestration Application ni lecture cross-module requise (`collection_actions.customer_id` est `NN`, native) | C4 |
| **OPEN-02** | **OPEN — seul point non résolu.** Cadence de `ResumeProposedActions` absente de `ENGINE_CONTRACTS_V1.md` §EC-03 et de toute autre source. Gap de spécification réel, pas une ambiguïté d'architecture : nécessite une décision/amendement, pas une lecture croisée. | A3 |
| OPEN-03 | **ACCEPTÉ** — seuil de 15 min = règle métier Domain (le franchissement a une sémantique, pas une optimisation SQL) ; cadence `Reaper` = 5 min, Application uniquement (`ENGINE_CONTRACTS_V1.md` §EC-03) | A7 |
| OPEN-04 | **ACCEPTÉ** — `ReapActions.emits=()` intentionnel : `EXECUTING → SCHEDULED` ne requiert pas d'événement, `ExecuteDueActions` (polling 1 min) détecte la reprise via `scheduled_for`. Même transition d'état ≠ obligation que tous les chemins d'entrée émettent le même événement. Aucun amendement. | A7 |
| OPEN-05 | **ACCEPTÉ** — `collection.AuthorizeOverride` vérifie la validité ACTUELLE du grant (fait, G4) ; `rules.Evaluate` reste l'autorité finale qui consomme ce fait (G3). Pas de double source de vérité. Source explicite : `specs.py` d'`AuthorizeOverride`, « audit à la création puis à chaque vérification » = G8 mot pour mot. Aucun changement de `calls` ni de Domain. | A6 |
| OPEN-06 | **RÉSOLU** — A1/A4 : `EXPLICIT` (liste établie depuis `decision_snapshot`, `DATA_CONTRACT_V1.md` §6.1). A2 : `EXPLICIT` (nouvelle évaluation, `STATE_MACHINES_V1.md` §8 : la revalidation `PROPOSED → SCHEDULED` reprend explicitement l'ordre des 13 exceptions). A6 : `EXPLICIT` (résolu via OPEN-05). Champs jamais consommés par aucune UC : `decision_id`, `evaluated_at`, `as_of` (propre), `org_timezone`, `conditions_trace`, `facts_snapshot`, `proposed_actions[]`, `input_hash`. | A1, A2, A4, A6 |

---

## Journal des corrections de traçabilité

| Date | Ligne | Correction | Nature |
|---|---|---|---|
| 2026-10-04 | A5 `CancelCollectionAction`, idempotence | « rejeu = `REPLAY` » (EXPLICIT d'après le vocabulaire des issues) → `SKIPPED` pour la même transition (`ENGINE_CONTRACTS_V1.md` §5), erreur EC-11 pour une transition invalide | traçabilité — aucune règle métier changée ; issue admise par B10 |
| 2026-10-04 | A11 `CompleteTask`, idempotence | « `DONE` = `REPLAY` » étiqueté « EXPLICIT (EC-11) », qu'EC-11 ne dit pas → même correction | traçabilité — idem |

Relevé non corrigé, hors du périmètre autorisé : la ligne A10 (`ClaimTask`, idempotence) annonce « probablement `REPLAY` » pour une
réclamation par l'assigné lui-même, alors que DV5-2 a décidé `CONCURRENT_MODIFICATION`.

---

## Phase 6 — Audit final des 19 UC (2026-09-26)

Audité contre les 10 points demandés (précondition déterminée, `RuleDecision` identifiée, lectures justifiées,
transitions cohérentes avec les State Machines, écritures couvertes par le Data Contract, événements cohérents avec
les invariants, erreurs définies, idempotence déterminée, dépendances inter-domaines cohérentes, aucune question
cachée). **Aucun fichier gelé modifié pendant cet audit.**

### AUDIT-01 (majeur) — Trois cas d'usage manquent entièrement au registre

`COLLECTION_ENGINE_V1.md` §14 (table « Exécutable ») liste explicitement, comme « opérations utilisateur » au même
rang que `CancelAction` (= `CancelCollectionAction`, déjà enregistré) :

```
RescheduleAction, CancelAction, ClaimTask, CompleteTask
```

Et `STATE_MACHINES_V1.md` §5 (réclamation de tâche par un membre de pool), §7 (« une action `SCHEDULED` peut être
**replanifiée** par un utilisateur ; le nouveau créneau repasse par les mêmes règles ») et §8 (transition
`SCHEDULED → DONE`, « tâche humaine uniquement… par un utilisateur, issue obligatoire ») exigent leur existence.

**Vérifié directement dans le code** (`grep` sur `commands.py` et `verqia/collection/`) : `ClaimTask`,
`CompleteTask` et `RescheduleAction` **n'existent nulle part** — ni dans `commands.py` (22 cas d'usage `collection`
exactement, tous déjà comptés dans cette matrice), ni dans `verqia/collection/application/specs.py`, ni ailleurs.

Aucune trace non plus d'un report explicite de ces trois use cases dans `COLLECTION_ENGINE_V1.md` §17 (limites
connues de la V1) — ce n'est donc pas un choix de périmètre documenté, c'est une absence.

**Conséquence** : la matrice des « 19 cas d'usage » couvre tout ce qui existe **déjà généré**, mais pas tout ce que
`COLLECTION_ENGINE_V1.md`/`STATE_MACHINES_V1.md` exigent pour un Domain V1 complet. Une facture dont une tâche
humaine (`CALL_TASK`/`FOLLOW_UP`/`ESCALATION`) est `SCHEDULED` ne peut aujourd'hui être ni réclamée par un membre du
pool, ni terminée (`SCHEDULED → DONE`), ni replanifiée — trois mécanismes déjà décrits en détail dans les sources
mais absents du registre.

**Aucune décision prise ici** : ceci est un constat, pas un arbitrage. Trancher si ces trois use cases entrent dans
le périmètre V1 de `COLLECTION_DOMAIN_V1.md` (et donc dans un futur amendement de registre, style B5/B6/AM-03) ou
s'ils sont volontairement différés est une décision qui te revient.

#### Phase 6B — Reconstruction et résolution (2026-09-26) : **RÉSOLU**

Les trois cas d'usage ont été reconstruits un par un (`ClaimTask` → `CompleteTask` → `RescheduleAction`), avant tout
amendement, à partir d'`ENGINE_CONTRACTS_V1.md` §EC-11 (table faisant autorité, donnant Entrée/Sortie/Erreurs/
Idempotence/Transaction pour les trois), croisée avec `STATE_MACHINES_V1.md` §7/§8, `COLLECTION_ENGINE_V1.md` §5/
§7/§8.2/§13/§14, `INVARIANTS_V1.md` §7.1 et `DATA_CONTRACT_V1.md` §6.1. Voir A10, A11, A12 ci-dessus pour le détail
champ par champ.

Amendement **B8** appliqué et vérifié (registre `commands.py` + `locks.py` + exception nominative `build_registry.py`
+ `specs.py` régénéré + `application_freeze.py` journalisé/réécrit + `APPLICATION_CONTRACT_V1.md` régénéré + tests
mis à jour, régression complète verte). Deux conséquences techniques nécessaires, découvertes seulement à
l'exécution et non anticipées à la rédaction des trois lignes de `commands.py` :
- `locks.py` : deux opérations de verrou nommées (`ClaimTask`, `RescheduleAction`, mode `G` déjà existant sur la
  ressource déjà déclarée `collection_actions`) — aucune ressource ni mode nouveau ;
- `build_registry.py` : une exception nominative et fermée à la convention `Complete*` (réservée à `system`/`job`)
  pour `CompleteTask`, qui est authentiquement un command `USER` (`STATE_MACHINES_V1.md` §8, C6) — la convention
  n'avait que deux précédents (`CompleteProvisioning`, `CompleteImportRelease`), tous deux des processus internes,
  et n'avait jamais été pensée pour ce cas.

Aucune de ces deux conséquences n'introduit de règle métier : elles reclassent une mutation déjà décrite dans un
vocabulaire déjà existant du registre.

**AUDIT-01 est donc RÉSOLU sur l'existence et le contrat des trois UC.** Cinq réserves mineures restent
explicitement `OPEN` — absence de preuve, jamais transformée en règle métier — et ne sont **pas** closes par B8 :
`AUDIT-01.a` (événement `ClaimTask`), `AUDIT-01.b` (audit dédié `ClaimTask`), `AUDIT-01.c` (audit dédié
`CompleteTask`), `AUDIT-01.e` (événement `RescheduleAction`), `AUDIT-01.f` (erreur de créneau invalide pour
`RescheduleAction` — de nature différente : lacune normative possible, pas seulement absence de preuve).

### AUDIT-02 (mineur) — `collection_action_attempts` et `ReapActions`

`DATA_CONTRACT_V1.md` §6.2 : `collection_action_attempts.finished_at` et `.outcome` sont `NN` (obligatoires,
`outcome ∈ {SUCCEEDED, FAILED}`). Mais `ReapActions` (A7) « recrée » une tentative jugée transitoirement échouée
sans qu'aucun résultat concret (succès/échec fournisseur) n'ait jamais été observé — juste un silence de plus de 15
minutes. Question non résolue : `ReapActions` écrit-il une ligne `collection_action_attempts` (avec `outcome=FAILED`,
un `error_code` du type `WORKER_INTERRUPTED`, `finished_at=as_of`) pour clore proprement l'essai abandonné, ou
laisse-t-il cet essai sans ligne de journal du tout ? Aucune source ne le précise explicitement. Signalé, non
tranché.

### Points 1 à 9 de la checklist — résultat

Sur les 19 UC initiaux, en dehors d'AUDIT-01/02 et des points déjà `OPEN` documentés (OPEN-02 pour A3), aucune autre
incohérence trouvée entre : préconditions, `RuleDecision` consommée, lectures déclarées, transitions (`STATE_MACHINES_V1.md`
§8/§9), écritures (`DATA_CONTRACT_V1.md` §6.1-6.3), événements (`INVARIANTS_V1.md` §10), erreurs déclarées,
idempotence, et dépendances inter-domaines. La correction B1 ci-dessus était la seule question « cachée dans une
entrée apparemment fermée » trouvée (point 10).

---

## Reconsolidation post-B8 (2026-09-26) — 19 → 22 cas d'usage

`ClaimTask` (A10), `CompleteTask` (A11), `RescheduleAction` (A12) sont désormais dans le registre (B8) et dans cette
matrice, avec la même discipline EXPLICIT/DERIVED/OPEN que les 19 UC initiaux. Vérification de non-régression :

- **Aucun doublon d'identifiant** : A1-A9, B1-B3, C1-C7 inchangés ; A10-A12 sont de nouveaux identifiants, aucun
  réemploi.
- **Aucun trou** : les 22 UC qui touchent un état Collection (`collection.action_status`/`collection.hold_status`)
  sont tous couverts ; les 3 UC `collection` qui n'en touchent aucun (`AuthorizeOverride`,
  `ScanReconciliationReviews`, `ReadApprovalTarget`) restent, comme avant B8, hors matrice — ce n'est pas un oubli,
  c'est le même critère d'inclusion qu'au départ (voir l'introduction du document).
- **Aucune contradiction** : A10/A12 ne transitionnent jamais `status` (seuls `assigned_to`/`scheduled_for`
  changent) — cohérent avec `STATE_MACHINES_V1.md` §8, qui ne les liste pas parmi ses transitions. A11 transitionne
  `SCHEDULED → DONE`, explicitement listée. Aucun champ technique du registre (B8 : 122 commandes / 51 `PUBLIC` /
  103 verrouillées) n'a été reproduit comme règle métier — ces chiffres décrivent l'Application/l'architecture, pas
  le Domain.
- Les réserves `AUDIT-01.a/.b/.c/.e/.f` restent `OPEN`, portées par A10/A11/A12 ci-dessus, non absorbées dans
  AUDIT-01 comme s'il s'agissait d'un unique gros bloc `OPEN` indistinct.

## Prochaine étape

**Amendments post-DV4 CLÔTURÉE (2026-09-26)** — AM-01, AM-02, AM-03 appliqués, régénérés et vérifiés. **Passe
OPEN-01→OPEN-06 CLÔTURÉE** — cinq arbitrages ACCEPTÉS/RÉSOLUS par lecture croisée des sources déjà gelées, sans
invention ni amendement. **AUDIT-01 RÉSOLU** (Phase 6B, amendement B8, régression complète verte). La matrice
couvre maintenant les 22 UC réels du registre.

**Points réellement ouverts, indépendants entre eux, non traités ici :**
- **OPEN-02** (cadence de `ResumeProposedActions`) : pas une ambiguïté d'architecture à arbitrer, mais une
  information manquante dans le corpus gelé — nécessite une décision de spécification (valeur à fixer), suivie,
  si retenue, d'un amendement de `ENGINE_CONTRACTS_V1.md` §EC-03.
- **AUDIT-02** (traçabilité `ReapActions`/`collection_action_attempts`) : lacune de traçabilité signalée, non
  tranchée.
- **AUDIT-01.a/.b/.c/.e/.f** : réserves mineures (événements/audit non prouvés) et une réserve de nature différente
  (`.f`, erreur de créneau invalide — possible lacune normative).

**Ces trois catégories restent volontairement hors du périmètre de `COLLECTION_DOMAIN_V1.md`** : la rédaction du
document de spécification lui-même n'a pas encore commencé et ne doit pas être engagée avant une décision explicite
séparée.
