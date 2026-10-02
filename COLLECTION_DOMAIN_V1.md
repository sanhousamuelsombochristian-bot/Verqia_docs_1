# VERQIA — Collection Domain V1

Spécification du Domain `collection` : 22 cas d'usage (Action Lifecycle A1-A12, Hold B1-B3, Suppression C1-C7).

**Hiérarchie de vérité.** `DATA_CONTRACT_V1.md` → `INVARIANTS_V1.md` → `STATE_MACHINES_V1.md` →
`RULE_ENGINE_V1.md` → `COLLECTION_ENGINE_V1.x` → `AUTOMATION_ENGINE_V1.1` → `ENGINE_CONTRACTS_V1.x` →
`ARCHITECTURE_REGISTRY_V1.md` → `APPLICATION_CONTRACT_V1.md` → `COLLECTION_DOMAIN_V1_MATRIX.md` → ce document.
En cas de divergence, la source la plus haute gagne ; ce document ne gagne jamais.
`COLLECTION_DOMAIN_V1_MATRIX.md` reste la source analytique des 22 cas d'usage.

**Niveaux de confiance**, portés par chaque affirmation :
- **EXPLICIT** — énoncé par une source gelée, sans interprétation.
- **DERIVED** — déduit de plusieurs sources cohérentes ; la dérivation est indiquée avec sa source.
- **OPEN** — non tranchable sans arbitrage. Jamais fermé par hypothèse. Qualifié `BLOCKER` ou `NON BLOCKING`.

**Règle de lecture.** Une affirmation non marquée est EXPLICIT ou DERIVED et vérifiable par §16 ; toute réserve est
en §17. Quatre catégories jamais mélangées : **écart constaté** (divergence entre sources) ≠ **OPEN** (question non
tranchée) ≠ **DERIVED** (conclusion étayée) ≠ **décision DV4/OPEN-0x** (arbitrage déjà accepté).

**Séparation métier / infrastructure.** Les propriétés d'Application ou d'architecture (opérations de verrou, modes
`A/K/S/U/G/I`, phases de transaction, compteurs du registre, cadences de scheduler) ne sont **pas** des règles
métier et n'apparaissent ici que lorsqu'une règle métier en dépend explicitement.

---

## 1. Purpose and Scope

Le Domain `collection` répond à une seule question métier : **quelle action de recouvrement doit exister, dans quel
état, à quel moment, pour une facture donnée — et quand doit-elle cesser d'exister**.

Dans le périmètre : le cycle de vie des actions (`collection_actions`), les tâches humaines et leur attribution, les
suspensions explicites (`collection_holds`), et les réactions de suppression aux événements métier.

Hors périmètre, avec le propriétaire : l'évaluation des règles (`rules`), le calcul du risque (`risk`) et de la
priorité (`priority`), l'orchestration des parcours (`automation`), les approbations (`approvals`), l'envoi des
messages et la résolution du gabarit et du contact (`notifications`), la production des grants d'override
(`AuthorizeOverride`).

## 2. Domain Responsibility

**Collection décide de l'existence et de l'état d'une action. Il ne décide jamais d'une règle.**

| Collection fait | Collection ne fait pas |
|---|---|
| Créer une action dans l'état que la décision reçue impose (`PROPOSED` ou `SUPPRESSED`) | Évaluer les garde-fous, les niveaux, les exceptions — c'est `rules` (DV4-1, gelé) |
| Faire progresser, exécuter, réclamer, terminer, replanifier, annuler | Recalculer un niveau de risque ou de priorité — ce sont des faits reçus via `RuleDecision.levels` |
| Suspendre une action quand une exception métier s'applique | Décider *si* une exception s'applique — `rules` le fait ; Collection applique le verdict |
| Poser, libérer, faire expirer un hold | Reprendre les parcours suspendus — c'est `automation` (§11 de `COLLECTION_ENGINE_V1.md`) |
| Calculer un créneau valide via `SlotCalculator` (fonction pure, §14) | Lire le calendrier lui-même : les faits calendaires lui sont fournis (voir §13) |

**Interdit par construction** : toute logique qui ferait de Collection un second Rule Engine. Un `decision_snapshot`
historique n'est **jamais** relu comme autorité pour une décision ultérieure — chaque point de revalidation demande
une **nouvelle** évaluation (A2, A6).

## 3. Core Concepts

### 3.1 Collection Action

Soit un **envoi système** (`REMINDER`, ou `ESCALATION` par message), soit une **tâche humaine** (`CALL_TASK`,
`FOLLOW_UP`, `ESCALATION` assignée). Porte `level` (1-5), `origin` (`AUTOMATION`/`MANUAL`), `dedup_key`, et
`decision_snapshot` — trace figée de la décision qui a autorisé sa création.

Frontière structurelle, imposée par le contrat de données (`DATA_CONTRACT_V1.md` §6.1, `CHECK`) :
`type='REMINDER' ⇒ assigned_to IS NULL AND assigned_role IS NULL` ;
`type ∈ {CALL_TASK, FOLLOW_UP, ESCALATION} ⇒ assigned_to IS NOT NULL OR assigned_role IS NOT NULL`.
C'est cette contrainte — pas une convention — qui borne A10/A11 aux seules tâches humaines. **EXPLICIT**

Une tâche humaine est **de pool** (`assigned_role` renseigné, `assigned_to` NULL) ou **assignée nommément**.
`ClaimTask` (A10) fait passer de la première forme à la seconde ; ce n'est **pas** une précondition pour terminer
(A11). **EXPLICIT** (`STATE_MACHINES_V1.md` §8)

### 3.2 Collection Hold

Suspension explicite du recouvrement, de portée `INVOICE`/`CUSTOMER`/`ORGANIZATION`, éventuellement restreinte à une
automatisation (`automation_id`). Trois responsabilités **strictement distinctes** :

| Responsabilité | Propriétaire | Niveau |
|---|---|---|
| Créer / libérer / faire expirer le hold | B1 / B2 / B3 — écrivent `collection_holds` **seulement** | EXPLICIT |
| Suspendre les actions couvertes par la portée | **C5** `SuppressOnHoldPlaced`, en réaction à `COLLECTION_HOLD_PLACED` | EXPLICIT (§12) |
| Reprendre les parcours après lever de cause | `automation` (`COLLECTION_ENGINE_V1.md` §11) | EXPLICIT |

Un hold est **hors vigueur dès `ends_at` dépassé**, indépendamment du passage du balayage : B3 matérialise, il ne
décide pas. **EXPLICIT** (`DATA_CONTRACT_V1.md` §6.3, `STATE_MACHINES_V1.md` §9)

### 3.3 RuleDecision — donnée reçue, jamais produite ici

Produite par `évaluer(faits, définition, as_of) → RuleDecision`, fonction pure du Domain `rules`. Champs :
`decision_id`, `subject`, `evaluated_at`, `as_of`, `org_timezone`, `outcome` (`PROCEED`/`SUPPRESS`/`SKIP`/`DEFER`),
`suppression_code`, `skip_reason`, `retry_at`, `primary_exception`, `exceptions_trace[]`, `overrides[]`,
`requires_approval`, `approval_reason`, `conditions_trace`, `facts_snapshot`, `levels`, `rule_refs`,
`proposed_actions[]`, `input_hash`.

**Sous-ensemble persisté** dans `decision_snapshot` (liste fermée, `DATA_CONTRACT_V1.md` §6.1) : `risk_level`,
`priority_level`, `collection_rules_ref`, `level`, `primary_exception`, `exceptions_trace[]`, `overrides[]`.
**Jamais consommés par aucun cas d'usage** : `decision_id`, `evaluated_at`, `as_of` propre, `org_timezone`,
`conditions_trace`, `facts_snapshot`, `proposed_actions[]`, `input_hash`. **EXPLICIT — OPEN-06 RÉSOLU**

Treize exceptions L1, ordre fixe (`RULE_ENGINE_V1.md` §3) : `ORG_INACTIVE`, `CUSTOMER_ARCHIVED`,
`CUSTOMER_INACTIVE`, `VOIDED`, `PAID`, `DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE`, `IMPORT_HELD`,
`FREQUENCY_LIMIT`, `NO_CONTACT`, `NO_CONSENT`, `RECONCILIATION_PENDING` (V1.2).

### 3.4 OverrideGrant — une preuve vérifiable, pas une autorité

`AuthorizeOverride` **vérifie la validité actuelle** d'un grant (acteur actif, rôle courant, organisation active,
motif, exception encore contournable — G4) et produit un **fait**. `rules.Evaluate` reste la seule autorité qui
décide de son effet (G3 : l'autorité est recalculée à chaque évaluation). Le grant est audité à la création **et à
chaque vérification à l'exécution** (G8). **EXPLICIT — OPEN-05 ACCEPTÉ**

Collection ne fabrique jamais un grant. A4 reçoit des grants *demandés* par l'utilisateur et appelle
`AuthorizeOverride` pour les faire vérifier ; A6 les fait re-vérifier à chaque tentative.
**EXPLICIT** (`ARCHITECTURE_REGISTRY_V1.md` : `CreateManualAction` et `ExecuteDueAction` appellent tous deux
`collection.AuthorizeOverride`)

### 3.5 Canaux — validés en amont, jamais à l'exécution

`SMS` et `WHATSAPP` existent au schéma mais ne sont pas activables en V1 : une définition d'automatisation qui les
référence est **rejetée à sa création**, par le Rule Engine, avec `DEFINITION_CHANNEL_NOT_ENABLED` (erreur de classe
`VALIDATION`, moteur `RULE`). Collection ne vérifie donc **jamais** l'activation d'un canal au moment d'agir : une
définition invalide ne l'atteint pas. **EXPLICIT** (`COLLECTION_ENGINE_V1.md` §2 ; `RULE_ENGINE_V1.md` §5 ;
`ENGINE_CONTRACTS_V1.md` catalogue d'erreurs)

En V1 : un seul canal externe (`EMAIL`) ; `IN_APP` ne joint jamais le client ; `PHONE` est une tâche humaine
(`CALL_TASK`) qui exige un contact joignable mais pas de consentement (N4).

## 4. Action Lifecycle (A1-A12)

Chaque fiche donne : entrée → garde → décision → écriture → sortie. Les erreurs sont en §12, l'idempotence en §9,
les acteurs en §11.

### A1 · `CreateCollectionAction`
Déclenchée par l'Automation Engine, jamais par un humain (**DERIVED** : `origin` implicite automatique, absence
d'`override_grants` en entrée, contrairement à A4). Cherche la `dedup_key` (existante ⇒ `REPLAY`), vérifie l'absence
de rejet antérieur dans le cycle, puis applique le verdict reçu : `SUPPRESS` ⇒ écrit **directement** `SUPPRESSED`
avec `suppression_code` et `decision_snapshot` (une seule ligne, jamais deux écritures) ; `SKIP` ⇒ rien (compteur,
hors Domain) ; `DEFER` ⇒ rien, l'appelant réessaiera à `retry_at` ; `PROCEED` ⇒ écrit `PROPOSED`, puis enchaîne A2.
**EXPLICIT** (§4)

### A2 · `AdvanceProposedAction`
Interne, jamais appelée directement. Garde d'état : agit sur `PROPOSED` uniquement, sinon `SKIPPED`. Effectue une
**nouvelle** évaluation — décision fermée, non réouvrable : `STATE_MACHINES_V1.md` §8 énumère pour
`PROPOSED → SCHEDULED` la séquence complète des exceptions, ce qui n'a de sens que réexécuté, pas relu.
`requires_approval` ⇒ `PENDING_APPROVAL` (la demande d'approbation est créée dans la transaction d'`approvals`) ;
sinon ⇒ créneau calculé par `SlotCalculator` puis `SCHEDULED` ; revalidation défavorable ⇒ `SUPPRESSED`.
**EXPLICIT**

### A3 · `ResumeProposedActions`
Balayage : énumère les lignes restées `PROPOSED` (interrompues avant composition) et rejoue A2 sur chacune, sous la
même garde. Aucune décision propre. Cadence non spécifiée : **OPEN-02, NON BLOCKING** — §8 établit que la cadence
d'un balayage est une propriété d'Application, pas du Domain. **EXPLICIT** sauf cadence

### A4 · `CreateManualAction`
Même mécanique de décision qu'A1, déclenchée par un `USER` (`COLLECTOR`+), avec un niveau choisi dans la plage du
type et des `override_grants` demandés. A4 **appelle** `AuthorizeOverride` pour les faire vérifier, puis transmet le
fait obtenu à l'évaluation ; il ne fabrique aucun grant et ne décide pas de son effet (§3.4). Une exception
contournable par un grant valide devient `OVERRIDDEN` dans la trace au lieu de bloquer. Mêmes plancher et
non-régression qu'une action automatique. Audit **toujours** requis. **EXPLICIT**

### A5 · `CancelCollectionAction`
Accepte **tout état non terminal**, y compris `EXECUTING`. Écrit `CANCELLED` avec motif obligatoire et **libère la
`dedup_key`** — asymétrie volontaire avec `FAILED`, qui la conserve. Aucune évaluation de règle.
**EXPLICIT** (`STATE_MACHINES_V1.md` §8 ; `INVARIANTS_V1.md` §7.1)

### A6 · `ExecuteDueAction` (worker, composé)
Seul point de **revalidation complète** à chaque tentative (contexte D), incluant la re-vérification des grants
(§3.4). Quatre phases : **CLAIM** — revalidation puis `SCHEDULED → EXECUTING`, ou `SUPPRESSED`, ou replanification
sur `DEFER` ; **EFFECT** — création de la notification dans la transaction de `notifications`, qui résout elle-même
gabarit, langue, contact et variables autorisées (**DERIVED** : `notifications` déclare les lectures
`customers.ContactDirectory` et `organizations.OrgSettings` ; `TemplateResolver` est nommé en §14) ; **EXTERNAL** —
envoi hors de toute transaction ; **FINALIZE** — enregistrement.

La transition finale n'appartient **pas** à A6 : le résultat de l'envoi est asynchrone et traité par A9. A6 n'émet
que `COLLECTION_ACTION_SUPPRESSED`. **EXPLICIT** (`ARCHITECTURE_REGISTRY_V1.md` : `emits` d'A6 ne contient ni
`_EXECUTED` ni `_FAILED` ; §8.1 étape 5)

### A7 · `ReapActions` (watchdog)
Une action `EXECUTING` depuis **plus de 15 minutes** sans résultat **est** une tentative transitoire échouée (worker
interrompu) : le seuil est une règle métier du Domain — son franchissement a une sémantique — tandis que la cadence
du balayage (5 min) est une propriété d'Application. **EXPLICIT — OPEN-03 ACCEPTÉ** (`ENGINE_CONTRACTS_V1.md`
§EC-03 ; §8.3)

Conséquences : une nouvelle tentative est recréée, idempotente, y compris si la notification n'a jamais été créée ;
et **une ligne d'essai clôturant l'essai abandonné est écrite** (`outcome=FAILED`, `finished_at=as_of`).
**DERIVED, déterministe** — convergence de trois sources : §8.3 qualifie la situation de « tentative échouée
transitoire », §9 prescrit pour une transitoire « tentative enregistrée (`collection_action_attempts`) », et le
registre déclare `ReapActions` écrivant `collection.attempts`. Reste ouvert : aucun code nommé pour la cause
« worker interrompu » (§17, NON BLOCKING).

N'émet aucun événement sur reprise : A6 détecte la reprise par `scheduled_for`. Même transition ≠ obligation que
tous les chemins d'entrée émettent. **EXPLICIT — OPEN-04 ACCEPTÉ**

### A8 · `OnApprovalDecided`
Réaction à `APPROVAL_GRANTED`/`_REJECTED`. Ne rappelle pas `rules.Evaluate` : la revalidation de la cible appartient
à `approvals.DecideApproval`, qui interroge `ApprovalTargetReader` **avant** d'émettre. `GRANTED` ⇒
`PENDING_APPROVAL → SCHEDULED` ; `REJECTED` ⇒ `→ CANCELLED` (issue `APPROVAL_REJECTED`, aucune nouvelle proposition
dans le cycle). **EXPLICIT — DV4-5 ACCEPTÉ**

### A9 · `OnNotificationResult`
Réaction à `NOTIFICATION_SENT`/`_FAILED` — **c'est ici que la boucle d'exécution se referme**. Livraison acceptée ⇒
`EXECUTING → DONE` (issue `SENT`) ; erreur transitoire ⇒ `→ SCHEDULED` avec `next_retry_at` (5 min / 30 min / 2 h),
ligne d'essai enregistrée ; erreur permanente ou de configuration ⇒ `→ FAILED` ; gabarit introuvable ⇒ `FAILED`
immédiat, sans réessai. La classification d'erreur est un fait reçu. **EXPLICIT** (§8.1, §9)

Si l'action n'est plus `EXECUTING` (annulée entre-temps, §15) : le handler revalide l'état avant d'agir et conclut
`SKIPPED`. **DERIVED, déterministe** (§12 préambule ; issues de nature `handler`)

### A10 · `ClaimTask`
Réclamation d'une **tâche de pool** (`SCHEDULED`, type humain, `assigned_to IS NULL`) par un membre actif du pool
dont le rôle courant atteint `assigned_role`. Assignation atomique gardée : une seule réclamation gagne, la
concurrente reçoit `CONCURRENT_MODIFICATION`. **EXPLICIT** (`ENGINE_CONTRACTS_V1.md` §EC-11, mot pour mot :
« une seule réclamation gagne (`UPDATE … WHERE assigned_to IS NULL`) » ; §5 pour la composition du pool)

**Aucune transition de `status`** : l'action reste `SCHEDULED`, seul `assigned_to` change — c'est une colonne
modifiable, pas une transition, ce qui explique son absence des machines à états. **EXPLICIT**
(`INVARIANTS_V1.md` §7.1). Aucune évaluation de règle : réclamer n'est pas décider d'agir. **DERIVED** (absence de
revalidation dans EC-11, contrairement à A1/A6).

Réserves : aucun événement ni audit dédié identifié dans les sources examinées (§17, NON BLOCKING).

### A11 · `CompleteTask`
`SCHEDULED → DONE`, tâches humaines uniquement, par l'acteur **assigné ou** un membre autorisé du pool — la
réclamation préalable n'est pas une contrainte métier. `outcome` **obligatoire**, dans le sous-ensemble « tâche
humaine » de la liste fermée : `CONTACTED`, `NO_ANSWER`, `PROMISE_OBTAINED`, `DISPUTE_RAISED`, `REFUSED`,
`WRONG_CONTACT`, `OTHER`. **Revalidation non requise** — l'action humaine est déjà accomplie. Écrit `status`,
`outcome`, `outcome_note`, `executed_at` ; émet `COLLECTION_ACTION_EXECUTED`, le même événement qu'un envoi réussi.
**EXPLICIT** (`STATE_MACHINES_V1.md` §8 ; §8.2, §13 ; `DATA_CONTRACT_V1.md` §6.1 : `status='DONE' ⇒ outcome IS NOT
NULL`)

`PROMISE_OBTAINED` et `DISPUTE_RAISED` **suggèrent** à l'interface de créer la promesse ou le litige ; elles ne les
créent jamais — ces cas d'usage exigent leurs propres données. **EXPLICIT**

`collection_action_attempts` n'est pas concerné : cette table documente les tentatives d'envoi système.
**DERIVED** (schéma `provider`/`provider_ref`/`outcome ∈ {SUCCEEDED, FAILED}` ; jamais mentionnée pour une tâche)

Réserve : aucun audit dédié identifié au-delà du régime générique des commandes (§17, NON BLOCKING).

### A12 · `RescheduleAction`
Recalcule `scheduled_for` par le `SlotCalculator`, avec **les mêmes règles de placement** qu'à la création : fenêtre
de communication, jour ouvré, lissage du débit — sauf tâches humaines et escalades, qui n'ont pas de fenêtre
(§7 point 5). Aucune évaluation de règle : « les mêmes règles » désigne le `SlotCalculator`, pas le Rule Engine.
**Aucune transition de `status`.** **EXPLICIT** (§7)

**État d'entrée : `status ∈ {PROPOSED, SCHEDULED}`, tous types d'action.** Trois sources semblaient diverger ; la
règle de mutabilité de champ les referme sans en écarter aucune :

| Source | Ce qu'elle dit | Ce qu'elle est |
|---|---|---|
| `COLLECTION_ENGINE_V1.md` §7 | « une action `SCHEDULED` peut être replanifiée » | exemple exact mais incomplet (omet `PROPOSED`) |
| `ENGINE_CONTRACTS_V1.md` §EC-11 | « action non terminale » | ligne **groupée** avec `CancelAction`, dont c'est la précondition réelle |
| `INVARIANTS_V1.md` §7.1 « 2 Modifier » | « `scheduled_for` tant que `PROPOSED`/`SCHEDULED` » | **règle de mutabilité de champ — la borne exhaustive** |

`PENDING_APPROVAL` et `EXECUTING` sont donc **exclus** de A12, alors que A5 les accepte. **EXPLICIT**

**Cible de replanification — règle normative.** La cible fournie par l'utilisateur est une *demande*, pas un
créneau : elle est toujours normalisée, jamais refusée.

1. Hors jour ouvré ou hors fenêtre de communication ⇒ avancée jusqu'au prochain créneau valide. **Ce n'est pas une
   erreur.** **EXPLICIT** (`COLLECTION_ENGINE_V1.md` §7 point 2, mot pour mot : « Ce n'est **pas une erreur**
   (`DEFER`) »)
2. Au-delà du débit `send_rate_per_hour` ⇒ décalage d'une heure. **EXPLICIT** (§7 point 4)
3. Tâche humaine ou escalade ⇒ pas de fenêtre de communication ; jour ouvré conservé par défaut. **EXPLICIT**
   (§7 point 5)
4. **Cible dans le passé ⇒ la normalisation s'ancre à `max(cible, as_of)`**, jamais à la cible seule. Une
   replanification ne peut donc jamais produire un `scheduled_for` antérieur à l'instant de la commande.
   **DÉCISION NORMATIVE (2026-09-29), traçable** — arbitrage de BLOCKER-1 : §7 ne définit pas d'ancrage, et
   normaliser depuis une cible passée produirait un créneau immédiatement échu, donc un envoi effectué hors de la
   fenêtre de communication (contradiction avec le point 1) et un état que nul autre chemin du système ne produit —
   la planification initiale calculant toujours vers l'avant depuis l'événement déclencheur. L'ancrage est l'ajout
   minimal qui préserve une règle gelée. Aucun refus, aucun code d'erreur nouveau : `ACTION_INVALID_TRANSITION`
   reste la seule erreur d'A12, et porte sur l'état, pas sur la cible.

Réserve restante : aucun événement identifié (§17, NON BLOCKING).

## 5. Hold Domain (B1-B3)

| UC | Garde | Écrit | Émet | Niveau |
|---|---|---|---|---|
| **B1 `PlaceHold`** | rôle `MANAGER`+ ; motif non vide ; portée cohérente avec la cible (`INVOICE`⇒`invoice_id`, `CUSTOMER`⇒`customer_id`, `ORGANIZATION`⇒aucun) ; aucun chevauchement (même cible + `automation_id` + `kind`, plages sécantes, holds `ACTIVE`) | `collection_holds` **seulement** | `COLLECTION_HOLD_PLACED` **seulement** | EXPLICIT |
| **B2 `ReleaseHold`** | hold `ACTIVE` ; `release_reason` non vide ; rôle `MANAGER`+ | `status`, `released_by`, `released_at`, `release_reason` | `COLLECTION_HOLD_RELEASED` (cause `RELEASED`) | EXPLICIT |
| **B3 `HoldExpiryScan`** | `ends_at <= as_of` sur un hold `ACTIVE` | `status` | `COLLECTION_HOLD_RELEASED` (cause `EXPIRED`) | EXPLICIT |

B1 **ne suspend aucune action** : c'est C5 qui le fait, en réaction à l'événement. B3 ne décide rien : le hold était
déjà hors vigueur dès `ends_at`. Aucun audit pour B3 (transition purement temporelle).

**Réserve B2** : `COLLECTION_ENGINE_V1.md` §11 indique que l'action `SUPPRESSED` libère sa clé et que c'est
l'Automation Engine qui réévalue à la levée de la cause — ce qui suggère fortement qu'aucun effet côté action ne
part de la transaction de `ReleaseHold`, sans l'énoncer aussi explicitement que pour B1/C5. **DERIVED, réserve
résiduelle** (§17, NON BLOCKING).

## 6. Suppression Domain (C1-C7)

Forme commune : `événement → relire la cible → condition → SUPPRESSED ou no-op`. Toutes : aucune évaluation de
règle, idempotence par reçu, aucun audit, portée « actions concernées » = `PROPOSED`, `SCHEDULED`,
`PENDING_APPROVAL` de la cible. **EXPLICIT** (§12 préambule)

**DV4-6 ACCEPTÉ** : aucune ne rappelle `rules.Evaluate`. L'événement **est** lui-même la condition de l'exception
L1 ; la revalidation complète reste garantie en aval par A6. Ce n'est pas un contournement de la discipline du
moteur, c'est sa répartition : défense en profondeur au point d'exécution, raccourci réactif en amont.

| # | Événement(s) | Condition | Résultat |
|---|---|---|---|
| C1 | `INVOICE_PAID` | — | `SUPPRESSED (PAID)` |
| C2 | `INVOICE_VOIDED`, `INVOICE_CANCELLED` | — | `SUPPRESSED (VOIDED)` |
| C3 | `INVOICE_DISPUTED` | **seulement si `collectible_minor = 0`** (litige total, D1) ; litige partiel ⇒ le recouvrement continue sur le montant recouvrable | `SUPPRESSED (DISPUTED)` |
| C4 | `PROMISE_CREATED` | portée lue dans le payload (`invoice_id` présent ⇒ `INVOICE`, absent ⇒ `CUSTOMER`) ; filtrage direct par `customer_id`, colonne `NN` native | `SUPPRESSED (PROMISE_ACTIVE)` |
| C5 | `COLLECTION_HOLD_PLACED` | portée du hold | `SUPPRESSED (HOLD_ACTIVE)` |
| C6 | `CUSTOMER_DEACTIVATED`, `CUSTOMER_ARCHIVED` | selon l'événement | `SUPPRESSED (CUSTOMER_INACTIVE` / `CUSTOMER_ARCHIVED)` |
| C7 | `ORGANIZATION_SUSPENDED`, `ORGANIZATION_CLOSED` | les deux traités identiquement | `SUPPRESSED (ORG_INACTIVE)` |

C3 est la seule à lire hors de son état : `collectible_minor` est absent du payload de `INVOICE_DISPUTED` et non
dérivable localement, d'où une lecture `invoices.InvoiceFacts`. **EXPLICIT — DV4-8, amendement appliqué.**
C7 traite `ORGANIZATION_CLOSED` comme `_SUSPENDED` : **DV4-7 ACCEPTÉ**, décision déjà validée par
`STATE_MACHINES_V1.md` §1 et la note S10. C4 : **OPEN-01/DV4-9 ACCEPTÉ**, aucune orchestration Application requise.

## 7. RuleDecision Contract and Revalidation

Quatre points de revalidation, et quatre seulement : **A1** (création), **A2** (progression), **A4** (création
manuelle), **A6** (chaque tentative d'exécution). Partout ailleurs — A3, A5, A7, A8, A9, A10, A11, A12, B1-B3,
C1-C7 — aucune évaluation de règle n'a lieu, et chaque absence est justifiée par une source :

| Absence | Justification | Niveau |
|---|---|---|
| A3 | délègue intégralement à A2 | EXPLICIT |
| A5, A10, A12 | annuler, réclamer, replanifier ne sont pas des décisions d'agir | DERIVED (EC-11 : aucune revalidation mentionnée, contrairement à A1/A6) |
| A11 | « revalidation non requise : l'action humaine est déjà accomplie » | **EXPLICIT, mot pour mot** (`STATE_MACHINES_V1.md` §8) |
| A7 | constat temporel | EXPLICIT |
| A8 | la cible est revalidée par `approvals` avant l'événement | EXPLICIT (DV4-5) |
| A9 | résultat d'envoi = fait reçu | EXPLICIT |
| B1-B3 | le hold ne consulte aucune règle | EXPLICIT |
| C1-C7 | l'événement est la condition | EXPLICIT (DV4-6) |

**Contrat d'appel.** Le Domain reçoit une `RuleDecision` **déjà produite** ; l'assemblage des faits qui la
nourrissent est une responsabilité d'Application. **DERIVED, déterministe** — trois appuis : DV4-1 (gelé) ; le
module `rules` ne déclare **aucune lecture** (les faits lui sont poussés par les fournisseurs de faits, dont
`collection` lui-même) ; et le précédent gelé de Risk et Priority, où les paramètres sont assemblés par
l'Application et le Domain reste pur.

**Conséquence d'implémentation** : une fonction du Domain Collection ne « va pas chercher » une décision — elle la
reçoit en argument, avec les faits déjà résolus dont elle a besoin. C'est ce qui rend le Domain testable sans
infrastructure, exactement comme `evaluate_risk` et `evaluate_priority`.

## 8. Temporal Semantics

| Règle | Propriétaire | Niveau |
|---|---|---|
| `as_of` injecté est la **seule** source de « maintenant » ; le Domain ne lit jamais d'horloge | Domain | EXPLICIT (convention noyau) |
| Seuil `EXECUTING > 15 min` ⇒ tentative transitoire échouée | **Domain** (le franchissement a une sémantique) | EXPLICIT — OPEN-03 |
| Cadence des balayages (`Reaper` 5 min, `HoldExpiryScan` 5 min) | **Application/scheduler**, jamais Domain | EXPLICIT (§EC-03) |
| Cadence de `ResumeProposedActions` | Application — **valeur non spécifiée** | OPEN-02, NON BLOCKING |
| Hold hors vigueur dès `ends_at`, indépendamment du balayage | Domain (règle de lecture) | EXPLICIT |
| Réessais d'envoi : 5 min / 30 min / 2 h ; `max_attempts` 3 par défaut | Domain | EXPLICIT (§9) |
| Placement d'un créneau : fenêtre de communication, jours ouvrés, jours fériés, `send_rate_per_hour` ; tâches humaines et escalades sans fenêtre | `SlotCalculator`, fonction **pure** du Domain, faits calendaires fournis en entrée | EXPLICIT pour les règles (§7) ; DERIVED pour la couche |
| Replanification : la normalisation s'ancre à `max(cible, as_of)` ; un `scheduled_for` antérieur à la commande est impossible | Domain (A12) | **DÉCISION NORMATIVE** — voir §4, A12, point 4 |
| Un résultat de balayage ne dépend jamais de l'heure d'exécution : « le prochain passage rattrape » | Domain | EXPLICIT |

## 9. Idempotency and Deduplication

Trois notions distinctes, jamais interchangeables : **déduplication d'événement** (reçu `event_receipts`) ≠
**convergence d'`input_hash`** (propriété de `RuleDecision`, non consommée ici) ≠ **idempotence métier**
(`dedup_key`, gardes d'état).

| Mécanisme | UC | Niveau |
|---|---|---|
| `dedup_key = {invoice_id}:{type}:L{level}:C{cycle}:R{occurrence}`, portée organisation ; `occurrence` **toujours** produite par l'Automation Engine, jamais choisie ici ni acceptée d'un appelant | A1 | EXPLICIT — DV4-4, AM-01 appliqué |
| `manual:{idempotency_key}` — formule distincte | A4 | EXPLICIT |
| Garde d'état `PROPOSED` | A2, A3 | EXPLICIT |
| Garde d'état sur état terminal ⇒ `REPLAY` | A5, A11 | EXPLICIT |
| Réclamation gardée : une seule gagne ; même acteur déjà assigné ⇒ `REPLAY` ; autre acteur ⇒ `CONCURRENT_MODIFICATION` | A10 | EXPLICIT / DERIVED |
| Garde d'état `PROPOSED`/`SCHEDULED` | A12 | EXPLICIT |
| Claim gardé + revalidation | A6 | EXPLICIT |
| Transition gardée (balayage) | A7, B3 | EXPLICIT |
| Clé d'idempotence de commande + contrainte d'exclusion de chevauchement | B1 | EXPLICIT |
| Garde d'état `ACTIVE` | B2 | EXPLICIT |
| Reçu par `(event_id, handler_name)` | A8, A9, C1-C7 | EXPLICIT |

**Libération de clé** : `CANCELLED` et `SUPPRESSED` libèrent la `dedup_key` ; `FAILED` la conserve. Un échec
définitif ne peut donc pas être recréé silencieusement sous la même clé ; une suppression, si.
**EXPLICIT** (`DATA_CONTRACT_V1.md` §6.1, index unique partiel)

## 10. Events

**Produits** : `COLLECTION_ACTION_PROPOSED`, `_SCHEDULED`, `_EXECUTED`, `_FAILED`, `_CANCELLED`, `_SUPPRESSED`,
`COLLECTION_HOLD_PLACED`, `_RELEASED`. Aucun autre. **EXPLICIT** (`INVARIANTS_V1.md` §10)

| Événement | Émis par |
|---|---|
| `_PROPOSED` | A1, A4 |
| `_SCHEDULED` | A2, A8 |
| `_EXECUTED` | A9 (envoi accepté), **A11** (tâche humaine terminée) |
| `_FAILED` | A9 |
| `_CANCELLED` | A5, A8 |
| `_SUPPRESSED` | A1, A2, A4, A6, C1-C7 |
| `COLLECTION_HOLD_PLACED` | B1 |
| `COLLECTION_HOLD_RELEASED` | B2 (cause `RELEASED`), B3 (cause `EXPIRED`) |

**A10 et A12** : *aucun événement explicitement identifié dans les sources examinées*. Cette absence n'est **pas**
convertie en règle « aucun événement n'est émis » : elle reste une réserve (§17). Un implémenteur n'émet donc rien
aujourd'hui, et l'ajout éventuel d'un événement ne sera pas une correction mais une décision de spécification.

**A7** : n'émet rien sur reprise, et c'est ici une **décision arbitrée** (OPEN-04 ACCEPTÉ), non une absence de
preuve — la distinction importe.

**Consommés** : `APPROVAL_GRANTED`/`_REJECTED` (A8) · `NOTIFICATION_SENT`/`_FAILED` (A9) · `INVOICE_PAID` (C1) ·
`INVOICE_VOIDED`/`_CANCELLED` (C2) · `INVOICE_DISPUTED` (C3) · `PROMISE_CREATED` (C4) · `COLLECTION_HOLD_PLACED`
(C5) · `CUSTOMER_DEACTIVATED`/`_ARCHIVED` (C6) · `ORGANIZATION_SUSPENDED`/`_CLOSED` (C7).
Sans réaction (évaluation paresseuse, V1.2) : `PAYMENT_CREATED`, `_ALLOCATED`, `_REVERSED`,
`_ALLOCATION_REVERSED` — les points de revalidation relisent la source de vérité et appliquent
`RECONCILIATION_PENDING`. **EXPLICIT**

## 11. Authorization

| Acteur | UC | Borne |
|---|---|---|
| Automation Engine | A1 | aucun acteur humain |
| `SYSTEM` (interne / worker / balayage) | A2, A3, A6, A7, A8, A9, B3 | jamais appelable directement par un utilisateur |
| `USER` `COLLECTOR`+ | A4 | niveau dans la plage du type ; grants vérifiés |
| `USER` | A5, **A12** | rôle non précisé par les sources au-delà de « commande » — **OPEN, NON BLOCKING** |
| `USER`, membre actif du pool, rôle courant ≥ `assigned_role` | **A10** | tâches humaines de pool uniquement |
| `USER`, **assigné ou** membre autorisé du pool | **A11** | tâches humaines uniquement ; `INSUFFICIENT_ROLE` sinon |
| `USER` `MANAGER`+ | B1, B2 | `INSUFFICIENT_ROLE` sinon |

**A10 et A11 sont indépendants.** A10 sert à éviter qu'un même travail soit traité deux fois ; A11 peut être exécuté
par tout membre autorisé, tâche réclamée ou non. Ce n'est pas une séquence obligatoire. **EXPLICIT**

## 12. Errors and Failure Semantics

**Catalogue de l'action** (`INVARIANTS_V1.md` §7.1) : `ACTION_APPROVAL_REQUIRED`, `ACTION_MAX_ATTEMPTS_REACHED`,
`ACTION_LEVEL_REGRESSION`, `ACTION_LEVEL_BELOW_MINIMUM`, `ACTION_INVALID_TRANSITION`, `ACTION_LEVEL_INVALID`,
`CUSTOMER_INACTIVE`/`CUSTOMER_ARCHIVED` (création manuelle).

| UC | Erreurs nommées | Niveau |
|---|---|---|
| A1 | `SUBJECT_NOT_FOUND`, `ACTION_LEVEL_INVALID`, `ACTION_LEVEL_BELOW_MINIMUM` | EXPLICIT |
| A4 | idem A1 + `OVERRIDE_NOT_ALLOWED`, `OVERRIDE_ROLE_INSUFFICIENT`, `OVERRIDE_REASON_REQUIRED`, `OVERRIDE_ORIGIN_NOT_MANUAL`, `CUSTOMER_INACTIVE`/`CUSTOMER_ARCHIVED` | EXPLICIT |
| A6 | `TEMPLATE_UNAVAILABLE` | EXPLICIT |
| **A10** | `CONCURRENT_MODIFICATION` | EXPLICIT (EC-11) |
| **A11** | `ACTION_INVALID_TRANSITION`, `INSUFFICIENT_ROLE` | EXPLICIT (EC-11) |
| **A12** | `ACTION_INVALID_TRANSITION` | EXPLICIT (EC-11) |
| B1 | `HOLD_REASON_REQUIRED`, `HOLD_OVERLAP`, `HOLD_TARGET_MISMATCH`, `INSUFFICIENT_ROLE` | EXPLICIT |
| B2 | `HOLD_NOT_ACTIVE`, `INSUFFICIENT_ROLE` | EXPLICIT |
| A2, A3, A5, A7, A8, A9, B3, C1-C7 | aucune erreur nommée — les classes génériques de la nature du cas d'usage suffisent | EXPLICIT |

**Trois codes du catalogue sans propriétaire déclaré** : `ACTION_APPROVAL_REQUIRED`, `ACTION_MAX_ATTEMPTS_REACHED`,
`ACTION_LEVEL_REGRESSION`. Lecture la plus probable : `ACTION_MAX_ATTEMPTS_REACHED` n'est pas une erreur rendue à un
appelant mais l'état `FAILED` (§9 : « tentatives épuisées → `FAILED` ») ; `ACTION_LEVEL_REGRESSION` concernerait une
création manuelle tentant une régression, là où une création automatique répond `REPLAY` sans erreur (§11).
**DERIVED, non déterminé — réserve NON BLOCKING** (§17), volontairement non converti en règle.

**Issues non fautives** (`INVARIANTS_V1.md` §7.1, C11) : `REPLAY` — action déjà existante pour la même `dedup_key`,
l'existante est renvoyée ; `SKIPPED` — action créée directement en `SUPPRESSED` avec son `suppression_code`.
Ni l'une ni l'autre n'est un échec.

**Classes d'échec d'envoi** (§9) : **transitoire** ⇒ essai enregistré, retour en `SCHEDULED` avec `next_retry_at`,
revalidation à chaque tentative ; **permanente** ⇒ `FAILED` immédiat ; **configuration** ⇒ `FAILED`, alerte, aucune
répétition ; **exception métier** ⇒ **ce n'est pas un échec** : `SUPPRESSED`. Un `FAILED` ne compte pas comme niveau
atteint mais conserve sa clé, alerte le pool `MANAGER`, et déclenche le repli humain si l'action était un `REMINDER`
(§10 : une action de repli n'a pas elle-même de repli).

## 13. Cross-Domain Boundaries

| Frontière | Sens | UC | Niveau |
|---|---|---|---|
| `rules.Evaluate` | décision reçue | A1, A2, A4, A6 | EXPLICIT |
| `collection.AuthorizeOverride` | fait de validité d'un grant | A4, A6 | EXPLICIT |
| `invoices.InvoiceFacts` | lecture (`collectible_minor`) | C3 | EXPLICIT (DV4-8) |
| `approvals.RequestApproval` puis événement `APPROVAL_*` | appel dans la transaction d'`approvals`, puis réaction | A2 → A8 | EXPLICIT |
| `notifications.CreateNotification` puis événement `NOTIFICATION_*` | appel dans la transaction de `notifications` (qui résout gabarit et contact), puis réaction | A6 → A9 | EXPLICIT / DERIVED |
| `automation` | reprise des parcours après lever de cause — **jamais** Collection | B2, C1-C7 | EXPLICIT (§11) |
| Faits calendaires (`organizations.CalendarReader`) | entrée du `SlotCalculator` | A2, A12 | **voir réserve structurelle ci-dessous** |

**Réserve structurelle (traçabilité de registre).** Le `SlotCalculator` de §7 exige deux familles de faits, de deux
lectures distinctes :

| Fait | Emplacement | Lecture |
|---|---|---|
| jours ouvrés et fériés (`org.is_business_day`) | `org_holidays` + logique calendaire | `organizations.CalendarReader` |
| fenêtre de communication (`comm_window_start`/`comm_window_end`, colonnes `NN`) | `org_settings` | `organizations.OrgSettings` |
| débit d'envoi (`extra.send_rate_per_hour`) | `org_settings.extra` | `organizations.OrgSettings` |

`collection` déclare `organizations.CalendarReader` dans ses lectures **de module**, mais **pas**
`organizations.OrgSettings` ; et **aucun cas d'usage** ne déclare ni l'une ni l'autre, alors qu'A2 et A12 ne peuvent
pas produire un `scheduled_for` conforme à §7 sans elles. **AMENDMENT REQUIRED** — voir §17 et §19. Le modèle métier
n'en dépend pas ; la traçabilité du registre, si.

## 14. Domain Invariants

1. **Non-régression (R9)** — dans un `(facture, cycle)`, jamais de niveau inférieur au plus haut niveau déjà
   `SCHEDULED`, `EXECUTING` ou `DONE`. Une escalade dépendant du risque peut donc légitimement ne pas se produire.
2. **Exemplaire unique** — un seul par `(facture, type, niveau, cycle, répétition)` ; la même clé répond `REPLAY`.
3. **Immuabilité** — `invoice_id`, `customer_id`, `type`, `level`, `origin`, `decision_snapshot`, `dedup_key` ne
   changent jamais. Changer de niveau = annuler et recréer.
4. **Mutabilité fermée** — seuls `scheduled_for` (tant que `PROPOSED`/`SCHEDULED` : borne d'A12), `assigned_to`
   (A10), `outcome` et `outcome_note` (A11) peuvent changer. Cette liste **est** la surface d'écriture du Domain
   hors transitions de `status`.
5. **`SUPPRESSED` ≠ `CANCELLED`** — le premier constate qu'une exception métier s'applique (le système empêche), le
   second est la décision d'un acteur (l'acteur annule).
6. **Asymétrie des clés** — `CANCELLED`/`SUPPRESSED` libèrent la `dedup_key`, `FAILED` la conserve.
7. **Étanchéité envoi/tâche** — un `REMINDER` n'a jamais d'assignation ; une tâche humaine en a toujours une (pool
   ou nommée). Frontière imposée par contrainte de données, pas par convention.
8. **Origine de la reprise** — après suppression, la clé est libérée et c'est l'Automation Engine qui réévalue à la
   levée de la cause (§11). L'invariant porte sur l'**origine** de la reprise ; ce que §11 n'énonce pas, c'est si la
   transaction qui lève une cause produit malgré tout un effet local (réserve B2, §17).
9. **Un seul `decision_snapshot` par action** — écrit à la création, jamais mis à jour ; les revalidations
   ultérieures ne le réécrivent pas et ne s'y réfèrent pas comme autorité.

Sources : `INVARIANTS_V1.md` §7.1 (1, 2, 3, 4) · `DATA_CONTRACT_V1.md` §6.1 (2, 4, 6, 7) ·
`STATE_MACHINES_V1.md` §8 (5) · `COLLECTION_ENGINE_V1.md` §11 (1, 2, 8) · DV4-1 (9).

## 15. Concurrency and Determinism

Six courses réelles, toutes tranchées par les sources — aucune n'exige d'invention.

| # | Course | Résolution | Niveau |
|---|---|---|---|
| 1 | Une réaction de suppression (C1-C7) arrive pendant qu'une action est `EXECUTING` | La portée des réactions est **fermée** à `PROPOSED`/`SCHEDULED`/`PENDING_APPROVAL` : une action `EXECUTING` n'est jamais suppressible par réaction. C'est la revalidation d'A6 qui traite le cas, au prochain point de décision. | EXPLICIT (§12 préambule) |
| 2 | Deux workers prennent la même action échue | Verrou de ligne + garde d'état : un seul obtient le claim, l'autre observe un état déjà changé. | EXPLICIT (§EC-11) |
| 3 | Deux membres du pool réclament la même tâche | `UPDATE … WHERE assigned_to IS NULL` : un seul gagne, l'autre reçoit `CONCURRENT_MODIFICATION`. | EXPLICIT (§EC-11 ; `GLOBAL_TEST_MATRIX_V1.md` CO-07) |
| 4 | Une annulation (A5) arrive pendant qu'un envoi est en vol | A5 accepte `EXECUTING`. L'envoi a déjà quitté la transaction ; quand A9 arrive, l'action est terminale : le handler revalide et conclut `SKIPPED`. Aucune transition depuis un état terminal. | DERIVED, déterministe (§12 préambule ; issues de nature `handler`) |
| 5 | Le fournisseur a accepté l'envoi mais la transaction locale n'est pas validée | Garantie **au moins une fois** assumée : un doublon est possible dans cette fenêtre, limité par la clé d'idempotence envoyée au fournisseur. | EXPLICIT (§8.3) — la clé fournisseur reste à confirmer par la passe Intégrations (§17) |
| 6 | Un worker meurt après le claim | Après 15 minutes, A7 requalifie en tentative transitoire échouée, écrit l'essai clos et rend l'action réessayable. | EXPLICIT (§8.3) + DERIVED pour l'essai clos (§4, A7) |

**Déterminisme temporel.** Aucun résultat ne dépend de l'heure à laquelle un balayage passe : les gardes portent sur
l'état et sur `as_of`, jamais sur la fréquence. Un balayage manqué est rattrapé au passage suivant, sans effet
différent. **EXPLICIT**

**Déterminisme de décision.** À faits et décision identiques, un cas d'usage produit le même état : les seules
sources de non-déterminisme admises sont la concurrence ci-dessus et l'horloge, cette dernière étant confinée à
`as_of`.

## 16. Traceability

| UC | Sources |
|---|---|
| A1 | `COLLECTION_ENGINE_V1.md` §1, §2, §3.1bis, §4 · `STATE_MACHINES_V1.md` §8 · `INVARIANTS_V1.md` §7.1 · `RULE_ENGINE_V1.md` §6.1 |
| A2 | `COLLECTION_ENGINE_V1.md` §4 étape 7, §6, §7 · `STATE_MACHINES_V1.md` §8 |
| A3 | `COLLECTION_ENGINE_V1.md` §4 (note de balayage) · `ENGINE_CONTRACTS_V1.md` §EC-03 (par absence) |
| A4 | `COLLECTION_ENGINE_V1.md` §4 · `RULE_ENGINE_V1.md` §3, §3.1, §3.3 · `ARCHITECTURE_REGISTRY_V1.md` (`calls`) |
| A5 | `STATE_MACHINES_V1.md` §8 · `INVARIANTS_V1.md` §7.1 |
| A6 | `COLLECTION_ENGINE_V1.md` §8.1, §8.3, §9 · `RULE_ENGINE_V1.md` §7, §3.3 · `COLLECTION_ENGINE_V1_2.md` §3.3, §4 (G1-G9) · `ENGINE_CONTRACTS_V1.md` §EC-11 |
| A7 | `COLLECTION_ENGINE_V1.md` §8.3, §9 · `ENGINE_CONTRACTS_V1.md` §EC-03 · `ARCHITECTURE_REGISTRY_V1.md` (`writes`) |
| A8 | `COLLECTION_ENGINE_V1.md` §6 · `STATE_MACHINES_V1.md` §8 |
| A9 | `COLLECTION_ENGINE_V1.md` §8.1, §9, §10 · `STATE_MACHINES_V1.md` §8 |
| **A10** | `ENGINE_CONTRACTS_V1.md` §EC-11 · `COLLECTION_ENGINE_V1.md` §5, §14 · `DATA_CONTRACT_V1.md` §6.1 · `INVARIANTS_V1.md` §7.1 · `GLOBAL_TEST_MATRIX_V1.md` CO-07 |
| **A11** | `ENGINE_CONTRACTS_V1.md` §EC-11 · `STATE_MACHINES_V1.md` §8 · `COLLECTION_ENGINE_V1.md` §8.2, §13, §14 · `DATA_CONTRACT_V1.md` §6.1 |
| **A12** | `ENGINE_CONTRACTS_V1.md` §EC-11 · `COLLECTION_ENGINE_V1.md` §7, §14 · `INVARIANTS_V1.md` §7.1 |
| B1 | `DATA_CONTRACT_V1.md` §6.3 · `STATE_MACHINES_V1.md` §9 · `INVARIANTS_V1.md` §7.2 |
| B2 | idem B1 + `COLLECTION_ENGINE_V1.md` §11 |
| B3 | idem B1 + `INVARIANTS_V1.md` §3 · `ENGINE_CONTRACTS_V1.md` §EC-03 |
| C1-C7 | `COLLECTION_ENGINE_V1.md` §12 · `RULE_ENGINE_V1.md` §2.2, §3 · `INVARIANTS_V1.md` §10 · C3 : `invoices.InvoiceFacts` (DV4-8) |
| §3.5 canaux | `COLLECTION_ENGINE_V1.md` §2 · `RULE_ENGINE_V1.md` §5 · `ENGINE_CONTRACTS_V1.md` (catalogue d'erreurs) |

**Blocs transversaux (§7 à §15).** Ils n'ont pas de sources propres : ils réorganisent par thème les données déjà
tracées ci-dessus, et chacun porte une colonne « UC » ou des références explicites qui y renvoient. §14 cite ses
sources invariant par invariant.

**Décisions déjà arbitrées, non réouvrables** : DV4-1 à DV4-9 (dont AM-01, AM-02, AM-03 appliqués) et OPEN-01,
OPEN-03, OPEN-04, OPEN-05, OPEN-06. Détail et rationale : `COLLECTION_DOMAIN_V1_MATRIX.md`.

## 17. Open Issues and Reserves

Aucune n'est fermée par hypothèse. **Aucune bloquante ne subsiste** ; dix réserves non bloquantes restent ouvertes.

### Bloquants — tous deux fermés le 2026-09-29

| # | Sujet | Comment il a été fermé |
|---|---|---|
| ~~**BLOCKER-1**~~ | Comportement d'A12 sur une cible de replanification invalide | **FERMÉ par décision normative** : les cas hors jour ouvré et hors fenêtre étaient déjà tranchés par §7 (normalisation, « ce n'est pas une erreur ») ; seule une cible dans le passé restait indéterminée. Règle adoptée : **la normalisation s'ancre à `max(cible, as_of)`** — voir §4 A12 point 4 pour la règle et son rationale. Aucun refus, aucun code d'erreur nouveau. |
| ~~**BLOCKER-2**~~ | A2/A12 utilisaient des faits calendaires et des réglages d'organisation sans les déclarer | **FERMÉ par l'amendement de registre B9** (2026-09-29, forme B5/B6) : `organizations.CalendarReader` et `organizations.OrgSettings` déclarées dans les `calls` d'A2 et d'A12, `organizations.OrgSettings` ajoutée aux lectures de module de `collection`. Régénéré, gel réécrit (9 amendements), régression complète verte, aucune dépendance de module nouvelle. |

### Non bloquantes

| # | Sujet | UC | Nature |
|---|---|---|---|
| OPEN-02 | Cadence de `ResumeProposedActions` absente de toute source | A3 | gap de spécification réel, mais cadence = Application (OPEN-03) ⇒ le Domain est complet sans elle |
| R-1 | Aucun événement explicitement identifié pour la réclamation | A10 | absence de preuve, **non** convertie en règle |
| R-2 | Aucun audit dédié identifié au-delà du régime générique des commandes | A10 | idem |
| R-3 | Idem | A11 | idem |
| R-4 | Aucun événement explicitement identifié pour la replanification | A12 | idem |
| R-5 | Aucun code nommé pour la cause « worker interrompu » de l'essai clos | A7 | nommage manquant ; l'écriture de l'essai elle-même est établie (§4, A7) |
| R-6 | Qui résout le sujet (`SUBJECT_NOT_FOUND`) : pré-résolution par l'Application ou lecture du Domain ? | A1 | ambiguïté de couche, sans effet sur le résultat |
| R-7 | `ACTION_APPROVAL_REQUIRED`, `ACTION_MAX_ATTEMPTS_REACHED`, `ACTION_LEVEL_REGRESSION` : au catalogue des invariants, rattachés à aucun cas d'usage | A1, A4, A6 | **NON-CRITICAL GAP** ; rattachement probable en §12, non converti en règle |
| R-8 | `customers.ContactDirectory` déclaré dans les lectures de module de `collection` sans consommateur — la résolution du contact appartient à `notifications`, qui déclare déjà cette lecture | — | **NON-CRITICAL GAP** (hygiène de registre) ; **AMENDMENT CANDIDATE** |
| R-9 | Effet éventuel, dans la transaction qui lève une cause, côté action | B2 | **DERIVED, réserve résiduelle** ; §11 suggère « aucun » sans l'énoncer |
| R-10 | Clé d'idempotence envoyée au fournisseur, bornant le doublon de la fenêtre « accepté / non validé » | A6 | renvoyé explicitement à la passe Intégrations (§8.3) |

**Capability gaps constatés, volontairement non transformés en cas d'usage** : aucune opération de **dé-réclamation**
d'une tâche (rendre au pool) n'existe dans les sources ; aucune reprise manuelle d'une action `FAILED` n'existe non
plus. Classés **NON-CRITICAL GAP**. Créer un 23ᵉ cas d'usage pour l'un ou l'autre serait une invention.

## 18. Implementation Readiness

| Dimension | Verdict | Condition |
|---|---|---|
| Modèle de domaine | **READY FOR IMPLEMENTATION** | 22 UC, 3 sous-domaines, frontières fermées |
| 22 cas d'usage | **READY** | chacun a entrée, garde, décision, écriture, sortie, erreurs, idempotence |
| Transitions d'état | **READY** | §6 des machines à états couvert ; A10/A12 identifiés comme mutations de champ, pas transitions |
| Frontière `RuleDecision` | **READY** | quatre points de revalidation, dix-huit absences justifiées |
| Sémantique temporelle | **READY** — réserve non bloquante | seuils métier déterminés ; une cadence d'Application non spécifiée (OPEN-02) |
| Idempotence | **READY** | un mécanisme nommé par cas d'usage, trois notions séparées |
| Événements | **READY** | catalogue fermé ; deux absences qualifiées comme réserves, pas comme règles |
| Autorisation | **READY** | bornes connues ; rôle non précisé pour A5/A12, sans effet sur la décision |
| Sémantique d'erreur | **READY** | codes nommés là où les sources les nomment, classes génériques ailleurs |
| Concurrence | **READY** | six courses tranchées par les sources |
| Frontières inter-domaines | **READY** | BLOCKER-2 fermé par B9 : les deux lectures sont déclarées au niveau des cas d'usage |
| **Bloquants critiques** | **0** | BLOCKER-1 fermé par décision normative · BLOCKER-2 fermé par B9 |
| **Gel architectural** | **ARCHITECTURALLY FROZEN** (2026-09-29) | registre 0 erreur · gel Application `6146da5d…`, 9 amendements · 186 + 208 tests verts · gels Domain V1 (35/35) et Risk (18/18) intacts |

**Les 22 cas d'usage sont implémentables.** Aucun n'attend plus une décision ou un amendement.

**Ce que « frozen » signifie ici** : le modèle, ses frontières, ses transitions, son idempotence, ses événements,
ses erreurs et ses règles temporelles ne changent plus sans passer par §19. Les dix réserves de §17 sont des points
d'extension ou de confirmation, aucune n'empêche d'écrire le code d'un cas d'usage.

**Ce que « frozen » ne signifie pas** : ni que le Domain a été implémenté, ni que ses tests de domaine existent. La
suite du travail — oracle indépendant, code du Domain, runner, intégration, mutations, gel du Domain proprement dit —
suit la même séquence que Risk et Priority, et n'a pas commencé.

## 19. Versioning and Amendment Policy

**Statut de ce document : Collection Domain V3 — READY FOR IMPLEMENTATION / ARCHITECTURALLY FROZEN (2026-09-29).**
Aucun bloquant ne subsiste. Dix réserves non bloquantes restent explicitement ouvertes (§17) : elles n'empêchent
aucun cas d'usage d'être codé, et aucune n'est fermée par hypothèse.

Règles de gouvernance, héritées de la méthode appliquée aux tranches déjà gelées :
1. **Rien ne se corrige silencieusement.** Une divergence découverte se journalise comme réserve ou amendement, puis
   se traite dans une passe dédiée et explicitement autorisée.
2. **La matrice fait foi.** En cas de divergence entre ce document et `COLLECTION_DOMAIN_V1_MATRIX.md`, c'est le
   document qui est corrigé, jamais la matrice pour lui donner raison.
3. **Un amendement de document gelé est une opération séparée**, journalisée, avec sa justification et sa
   vérification. Ce document signale les amendements nécessaires ; il ne les applique pas.
4. **Une absence de spécification n'est jamais une spécification négative.** La formule retenue est « aucun X
   explicitement identifié dans les sources examinées ».
5. **Aucune responsabilité ne se déplace entre moteurs sans preuve documentaire.** En particulier, aucune règle du
   Rule Engine ne migre ici, sous aucune forme et pour aucune commodité d'implémentation.
6. **Journal des fermetures.**

   | Date | Objet | Forme |
   |---|---|---|
   | 2026-09-26 | AM-01, AM-02 (documents gelés), AM-03 / B7 (registre) — arbitrages DV4-4, DV4-7, DV4-8 | amendements |
   | 2026-09-26 | B8 — enregistrement d'A10, A11, A12, absents du registre (AUDIT-01) | amendement de registre |
   | 2026-09-29 | **BLOCKER-1** — ancrage `max(cible, as_of)` de la replanification (A12) | **décision normative** |
   | 2026-09-29 | **B9** — déclaration de `CalendarReader` et `OrgSettings` pour A2 et A12 | **amendement de registre** |

7. **Amendements candidats restants, non requis** : R-7 (trois codes d'erreur du catalogue des invariants sans cas
   d'usage déclaré) et R-8 (`customers.ContactDirectory` déclaré dans les lectures de module de `collection` sans
   consommateur — la résolution du contact appartient à `notifications`). Aucun des deux n'empêche l'implémentation ;
   ni l'un ni l'autre ne doit être traité par opportunisme au détour d'un autre chantier.
8. **Séquence suivante, inchangée par ce gel** : oracle indépendant → code du Domain → runner → intégration →
   mutations → gel du Domain, exactement comme pour Risk et Priority. Aucune couche technique (persistance,
   transport, interface, cache, déploiement) n'est engagée par ce document.
