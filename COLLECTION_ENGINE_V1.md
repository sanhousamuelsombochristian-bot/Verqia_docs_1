# VERQIA — Collection Engine V1

Références : Data Contract V1.3 (figé), Invariants V1.2, State Machines V1, Rule Engine V1.1 (verrouillé).
Statut : **V1.1 — C1 à C13 VALIDÉES**, avec trois précisions intégrées (C4, C6, C9/C10). Les amendements sont appliqués au contrat V1.3, aux State Machines, aux Invariants et au Rule Engine (§19).

Périmètre : transformer une **décision** du Rule Engine en **action de recouvrement**, la planifier, l'exécuter, la réessayer, la clore, et publier ses événements. Hors périmètre : orchestration des workflows et déclencheurs (Automation Engine), scores (Risk / Priority), fournisseurs d'envoi (passe Intégrations).

---

## 0. Position et principes

```
Decision → Eligibility → Revalidation → Level → Strategy → Channel → Dedup
        → Action → Scheduling → Execution → Retry / Failure → Result → Event
```

| # | Principe |
|---|---|
| CP1 | Le Collection Engine ne décide pas **si** agir (Rule Engine) ; il matérialise et conduit l'action. |
| CP2 | Une action est une **décision matérialisée** : elle porte son `decision_snapshot`. |
| CP3 | **Revalidation à chaque frontière** : création, planification, exécution, chaque nouvelle tentative (contextes C et D du Rule Engine). |
| CP4 | **Idempotence partout** : `dedup_key` pour les actions, clé d'idempotence envers le fournisseur d'envoi. |
| CP5 | **Aucun envoi hors fenêtre** de communication ni hors jour ouvert ; le calcul de créneau est une fonction pure à horloge injectée. |
| CP6 | **Un échec n'est jamais silencieux** : alerte interne et repli humain. |
| CP7 | Les **canaux sont des capacités activées par la plateforme**, pas un choix de l'organisation. |

Répartition avec les autres moteurs (rappel, Rule Engine §7 bis) : le Rule Engine décide (garde-fous, conditions, niveau, `requires_approval`) ; le Collection Engine choisit canal, gabarit et assignation, crée, planifie, exécute, réessaie ; l'Automation Engine orchestre étapes, délais et reprises.

---

## 1. Canaux

| Canal | Nature | Destinataire | V1 |
|---|---|---|---|
| `EMAIL` | envoi par le système | **contact du client** (contact de référence) | **actif** |
| `IN_APP` | notification interne | **utilisateur de l'organisation** (jamais le client) | **actif** |
| `PHONE` | **tâche humaine** (appel), aucun envoi système | contact du client, appelé par un utilisateur | **actif** (aucun fournisseur requis) |
| `SMS` | envoi par le système | contact du client | **désactivé** |
| `WHATSAPP` | envoi par le système | contact du client | **désactivé** |

- `SMS` et `WHATSAPP` restent dans le schéma et les énumérations mais **ne sont pas activables dans une stratégie V1**. Activation : constante de plateforme, pas un réglage d'organisation. Une définition qui les référence est rejetée à la création : `DEFINITION_CHANNEL_NOT_ENABLED`.
- **`IN_APP` ne joint jamais le client** : le client n'est pas un utilisateur de VERQIA. En V1, **un seul canal externe** existe donc : `EMAIL`. Le « repli de canal » est par conséquent un **repli humain** (§10), pas un second canal.
- `PHONE` figure au contrat comme canal d'action ; en V1 c'est une **tâche** (`CALL_TASK`) réalisée par une personne, qui a besoin d'un contact avec un numéro (`usable_contact(PHONE)`), mais pas de consentement (N4).

---

## 2. Types d'action

| Type | Nature | Niveaux autorisés | Canal | Destinataire / exécutant | Exceptions de livraison applicables | Exécution |
|---|---|---|---|---|---|---|
| `REMINDER` | message au client | 1 à 4 | `EMAIL` (V1) | contact de référence | `FREQUENCY_LIMIT`, `NO_CONTACT`, `NO_CONSENT` | **worker** (envoi) |
| `CALL_TASK` | tâche d'appel | 3 à 5 | `PHONE` | pool de rôle ou utilisateur | `NO_CONTACT` (numéro) | **humaine** |
| `FOLLOW_UP` | tâche de suivi générique | 3 à 5 | aucun (`NULL`) | pool de rôle ou utilisateur | aucune | **humaine** |
| `ESCALATION` | remise du dossier à un responsable | 4 à 5 | aucun (interne) | pool de rôle (`MANAGER` ou plus) | aucune | **humaine** (+ notification interne `MANAGER_ALERT`, D5) |

- Toutes les **exceptions métier** (`DISPUTED`, `PROMISE_ACTIVE`, `HOLD_ACTIVE`, `IMPORT_HELD`, `RECONCILIATION_PENDING` (V1.2)) et d'**intégrité** s'appliquent aux quatre types.
- Les niveaux 1 et 2 ne concernent que des factures non échues ; à partir de `OVERDUE`, plancher 3 (N7). L'ensemble des couples (niveau, type) ci-dessus est vérifié à la validation d'une définition (`DEFINITION_LEVEL_TYPE_INCOMPATIBLE`).
- **Alerte responsable (D5)** : une notification interne (`notifications.type = MANAGER_ALERT`, canal `IN_APP`), créée pour chaque membre du pool concerné, dédupliquée par `{action_id}:{user_id}`. Ce n'est jamais un type d'action.

---

## 3. Stratégie de recouvrement

### 3.1 Structure

La stratégie vit dans la **définition d'automatisation versionnée** (aucune nouvelle table). Elle a deux parties :

| Partie | Contenu | Évaluée par |
|---|---|---|
| **Table de niveaux** | liste ordonnée `(niveau, condition)`, du plus haut au plus bas, premier appariement | Rule Engine (§8) |
| **Étapes** (`steps`) | pour chaque étape : déclencheur, plage de niveaux acceptés, type d'action, canaux, gabarit, assignation, approbation (`NEVER`, `POLICY`, `ALWAYS`) | Automation Engine (déclenchement) puis Collection Engine (matérialisation) |

Une étape produit son action **seulement si** le niveau calculé appartient à sa plage ; sinon `SKIP` (`STEP_LEVEL_OUT_OF_RANGE`). Le niveau ne se déduit jamais du type, ni l'inverse.

### 3.1 bis Trois catégories de règles (C10)

| Catégorie | Nature | Où elle vit | Exemples |
|---|---|---|---|
| **A. Invariants structurels du moteur** | non configurables | code (Rule Engine, Collection Engine) et base de données | niveau minimal 3 dès `OVERDUE` ; non-régression ; ordre des niveaux ; matrice niveau × type (§2) ; exceptions L1 non désactivables ; canaux limités aux canaux activés ; déduplication |
| **B. Paramètres de stratégie** | configurables **par version de définition** | définition d'automatisation versionnée | seuils en jours (14, 15, 30, 7 pour le risque élevé) ; instants des étapes ; plages de niveaux par étape ; heure d'envoi ; gabarits ; assignation ; mode d'approbation ; bornes de répétition |
| **C. Réglages d'organisation** | configurables par l'organisation, **communs à toutes ses automatisations** | `org_settings` (colonnes et `extra`) | fenêtre de communication ; jours ouvrés et fériés ; `critical_amount_minor` ; `due_soon_days` ; `max_reminders_per_30d` ; `approval_min_risk_level` ; plafonds opérationnels (§3.3) |

Modifier la catégorie B = créer et activer une **nouvelle version** de la définition ; aucune colonne n'est ajoutée pour la rendre configurable.
La catégorie C protège les clients de l'organisation **quel que soit le nombre d'automatisations** (un plafond quotidien vaut toutes automatisations confondues) : il ne peut donc pas vivre dans une seule définition. `due_soon_days` et `critical_amount_minor` restent des réglages d'organisation parce que d'autres moteurs les utilisent aussi (Scheduler, Priority) ; les conditions les référencent par `param.*`.

**Chevauchement volontaire des niveaux 1 et 2.** Les conditions des niveaux 1 et 2 se recouvrent sur `days_to_due <= due_soon_days`. C'est intentionnel : la table est évaluée **du plus haut niveau au plus bas** et le premier appariement l'emporte, donc le niveau 2 est testé avant le niveau 1.

| Jours avant l'échéance (`due_soon_days = 7`) | Niveau |
|---:|---:|
| 14 à 8 | 1 |
| 7 à 0 | 2 |
| au-delà de 14 | aucun (`SKIP`, `NO_LEVEL_MATCHED`) |
| facture en retard | 3 ou plus |

Si `due_soon_days` change, la frontière 1/2 se déplace avec lui.

### 3.2 Gabarit par défaut (créé en `DRAFT` à l'ouverture de l'organisation, N13)

**Table de niveaux** (conditions sur les faits du Rule Engine ; `param.*` = colonnes d'`org_settings`)

| Niveau | Condition par défaut |
|---|---|
| 5 | `is_overdue` **et** `days_overdue >= 15` **et** `customer.risk_level >= HIGH` **et** `customer.overdue_exposure_minor >= param.critical_amount_minor` |
| 4 | `is_overdue` **et** (`days_overdue >= 15` **ou** (`customer.risk_level >= HIGH` **et** `days_overdue >= 7`)) |
| 3 | `is_overdue` |
| 2 | non `is_overdue` **et** `days_to_due <= param.due_soon_days` |
| 1 | non `is_overdue` **et** `days_to_due <= 14` |

Un `risk_level` inconnu rend `UNKNOWN` les conditions qui l'utilisent : elles ne sont pas satisfaites, et le niveau retombe sur celui que donnent les jours de retard (§4 du Rule Engine).

**Étapes**

| # | Déclencheur | Plage | Type | Canal | Gabarit | Assignation | Approbation |
|---|---|---|---|---|---|---|---|
| S1 Prévention | échéance − 14 j | 1 | `REMINDER` | `EMAIL` | `reminder_l1_preventive` | — | `POLICY` |
| S2 Échéance proche | échéance − `due_soon_days` (soit `INVOICE_DUE_SOON`) | 2 | `REMINDER` | `EMAIL` | `reminder_l2_due_soon` | — | `POLICY` |
| S3 Retard constaté | échéance + 3 j | 3–4 | `REMINDER` | `EMAIL` | `reminder_l3_overdue` | — | `POLICY` |
| S4 Appel | échéance + 10 j | 3–4 | `CALL_TASK` | `PHONE` | — | pool `COLLECTOR` | `NEVER` |
| S5 Escalade responsable | échéance + 15 j | 4 | `ESCALATION` | — | `alert_manager` | pool `MANAGER` | `NEVER` |
| S6 Escalade direction | échéance + 30 j | 5 | `ESCALATION` | — | `alert_management` | pool `ADMIN` | `NEVER` |

Les instants sont exprimés par rapport à l'échéance. Leur mise en œuvre (une exécution datée par facture, non rétroactivité, reprise) est spécifiée par l'Automation Engine.

**Gabarits de message** : les gabarits par défaut sont créés en `DRAFT`. Activer l'automatisation exige des gabarits `ACTIVE` pour les canaux utilisés (N13) : l'organisation relit donc les textes avant tout envoi.

### 3.3 Valeurs par défaut

| Paramètre | Valeur | Catégorie | Emplacement |
|---|---|---|---|
| Fenêtre de communication | 08:00 à 18:00, heure de l'organisation | C | `org_settings.comm_window_*` |
| Jours ouvrés | lundi à vendredi, hors jours fériés | C | `org_settings.business_days`, `org_holidays` |
| Limite de rappels par facture | 4 sur 30 jours | C | `org_settings.max_reminders_per_30d` |
| Approbation requise dès le risque | `CRITICAL` | C | `org_settings.approval_min_risk_level` |
| Montant critique, `due_soon_days` | selon l'organisation | C | `org_settings.critical_amount_minor`, `org_settings.due_soon_days` |
| Plafond de messages sortants par client et par jour | 2 | C (opérationnel) | `org_settings.extra.max_customer_messages_per_day` |
| Débit d'envoi maximal | 200 par heure et par organisation | C (opérationnel) | `org_settings.extra.send_rate_per_hour` |
| Délai d'approbation | 72 h | C (opérationnel) | `org_settings.extra.approval_expiry_hours` |
| Délai cible d'une tâche humaine | 3 jours après `scheduled_for` | C (opérationnel) | `org_settings.extra.task_sla_days` |
| Seuils de la table de niveaux (§3.2) | 14, 7, 15, 30 jours | B | définition |
| Instants des étapes, heure d'envoi visée (09:00) | voir §3.2 | B | définition |
| Tentatives d'envoi | 3, à 5 min, 30 min, 2 h | A (plateforme) | constantes |

*Les valeurs de catégorie B se changent en créant une nouvelle version de la définition ; celles de catégorie C dans les réglages de l'organisation. Aucune ne demande de colonne.*

---

## 4. Création d'une action

Use case `CreateCollectionAction` (contextes C du Rule Engine). Étapes, dans l'ordre :

1. **Sujet** : facture émise de l'organisation (`SUBJECT_NOT_FOUND` sinon).
2. **Canal** : déterminé par le type et l'étape (§2) ; la stratégie ne peut proposer qu'un canal activé (§1).
3. **Rule Engine** : garde-fous pour ce canal et ce type, conditions, niveau (avec plancher et non-régression), `requires_approval`. Issues :
   - `SUPPRESS` → action créée directement en `SUPPRESSED` (`suppression_code`), pour l'explicabilité ;
   - `SKIP` → rien n'est créé (compteur seulement) ;
   - `DEFER` → aucune action ; l'appelant (Automation Engine) réessaie à `retry_at` ;
   - `PROCEED` → suite.
4. **Rejet antérieur** : si une action de même clé a été `CANCELLED` avec l'issue `APPROVAL_REJECTED`, on ne repropose pas dans le cycle (`SKIP`, `APPROVAL_PREVIOUSLY_REJECTED`) (C8).
5. **Déduplication** : `dedup_key = {invoice_id}:{type}:L{level}:C{cycle}:R{occurrence}` (C4). `occurrence` n'est **jamais fourni par un appelant** : le Collection Engine le lit dans le contexte de l'exécution d'automatisation qui demande l'action (indice du déclencheur récurrent dans son `trigger_key`, indice de répétition de l'étape ; `0.0` par défaut), produit par l'Automation Engine. Une action manuelle utilise `manual:{idempotency_key}` (un humain peut créer deux tâches distinctes). Une action existante non `CANCELLED` et non `SUPPRESSED` avec la même clé est renvoyée telle quelle (**REPLAY**, pas d'erreur).
6. **Assignation** (tâches) : utilisateur nommé, ou **pool de rôle** (§5).
7. **Écriture** : `PROPOSED`, avec `decision_snapshot` (contrat §6.1 : niveaux séparés, `primary_exception`, `exceptions_trace[]`, `overrides[]`, versions), puis :
   - approbation requise → **trois temps, chacun dans la transaction de son module** (TD58) : l'action reste `PROPOSED` ; `approvals` enregistre la demande (idempotente par cible et étape) ; l'action passe `PENDING_APPROVAL`. Un balayage reprend une action restée `PROPOSED` ;
   - sinon → planification (§7) et `SCHEDULED`.
8. Audit si l'action est manuelle ou porte un override (D3) ; événement `COLLECTION_ACTION_PROPOSED`.

**Actions manuelles** (`origin='MANUAL'`, rôle `COLLECTOR` ou plus) : mêmes garde-fous, même plancher (dès `OVERDUE`, niveau minimal 3), même non-régression. Elles peuvent utiliser un `OverrideGrant` (Rule Engine §3.3). Le niveau d'une action manuelle est un choix de l'utilisateur dans la plage du type (C11). **Le grant est revérifié à l'exécution** (V1.2, RN3) : une action manuelle `SCHEDULED` n'est envoyée que si l'acteur, son rôle courant et l'exception le permettent encore ; sinon `SUPPRESSED` avec le code de l'exception.

---

## 5. Assignation par pool de rôle

Une tâche humaine est assignée soit à un utilisateur (`assigned_to`), soit à un **pool de rôle** (`assigned_role`, C5). Un pool comprend les utilisateurs actifs dont le rôle est **au moins** égal au rôle du pool (`OWNER > ADMIN > MANAGER > COLLECTOR`).

- L'organisation a toujours un `OWNER` : aucun pool n'est jamais vide.
- Une tâche de pool est **réclamée** par un membre (`assigned_to` renseigné, atomique : une seule réclamation gagne).
- Alertes internes d'un pool : une notification `IN_APP` par membre.
- File de travail d'un utilisateur : ses tâches assignées, plus les tâches de pool de son rôle non réclamées, triées par priorité de la facture (`priority_items.rank_score`), puis niveau décroissant, puis échéance.

---

## 6. Approbation

Décidée par le Rule Engine (`requires_approval`) :

`requires_approval = action envoyée au client par le système` **et** (`approval = ALWAYS` **ou** (`approval = POLICY` **et** `customer.risk_level >= org_settings.approval_min_risk_level`)).

Les tâches humaines et les escalades n'exigent pas d'approbation (elles sont elles-mêmes destinées à un responsable).

| Événement | Effet |
|---|---|
| `APPROVAL_GRANTED` | revalidation, puis `SCHEDULED` |
| `APPROVAL_REJECTED` | action `CANCELLED`, issue `APPROVAL_REJECTED` ; **pas de re-proposition dans le cycle** |
| Expiration (`approval_expiry_hours`) | action `CANCELLED`, issue `APPROVAL_EXPIRED` ; une nouvelle occurrence de déclencheur peut la re-proposer |
| Cible résolue pendant l'attente (facture payée, annulée…) | action `SUPPRESSED` (code correspondant) par `collection` ; approbation `EXPIRED` avec commentaire `TARGET_RESOLVED` par `approvals`, qui interroge la cible (port `ApprovalTargetReader`) au plus une cadence de balayage plus tard ; `DecideApproval` vérifie la cible au moment de décider (C6) |

Éligibilité de l'approbateur (contrat §8.5) : rôle `MANAGER` ou plus, `approval_limit_minor >=` montant recouvrable, différent du demandeur si la politique l'impose.

---

## 7. Planification

Fonction pure `prochain_créneau(as_of, heure_visée, règles)` (horloge injectée, fuseau de l'organisation, C10) :

1. Partir de l'instant visé (heure d'envoi visée du jour, ou `retry_at`).
2. **Actions envoyées au client** : avancer jusqu'à un jour ouvré (`org.is_business_day`) puis jusqu'à l'intérieur de la fenêtre de communication. Ce n'est **pas une erreur** (`DEFER`).
3. **Plafond par client** : si le client a déjà reçu ou a déjà planifié `max_customer_messages_per_day` messages ce jour-là, passer au jour ouvré suivant.
4. **Lissage** : respecter le débit `send_rate_per_hour` de l'organisation ; au-delà, décaler d'une heure.
5. **Tâches humaines et escalades** : pas de fenêtre de communication (elles ne contactent pas le client) ; `scheduled_for` = date d'échéance de la tâche ; jour ouvré conservé par défaut.

Le résultat est stocké dans `scheduled_for`. Une action `SCHEDULED` peut être **replanifiée** par un utilisateur ; le nouveau créneau repasse par les mêmes règles.

---

## 8. Exécution

### 8.1 Envoi système (`REMINDER` par `EMAIL`)

Le worker sélectionne les actions `SCHEDULED` dont `scheduled_for <= maintenant`, par lots, avec verrouillage sans blocage (`FOR UPDATE SKIP LOCKED`). Pour chacune, en **quatre temps, chacun dans la transaction de son module** (TD58) : **(A) claim** = les étapes 1 et 2, dans une transaction de `collection` ; **(B) notification** = les étapes 3 et 4, `collection` demandant à `notifications` de créer la notification dans **sa** transaction (idempotente par `dedup_key`) ; **(C) envoi** hors transaction ; **(D) résultat**. Les étapes :

1. **Revalidation complète** (contexte D). `SUPPRESS` → `SUPPRESSED` ; `DEFER` (hors fenêtre) → replanification ; `PROCEED` → suite.
2. `SCHEDULED → EXECUTING`.
3. Résolution du **contact de référence**, du gabarit actif (code, canal, langue du contact, à défaut celle de l'organisation) et des variables autorisées : numéro de facture, **montant recouvrable** (`collectible_minor`, donc la part non contestée en cas de litige partiel, D1), échéance, jours de retard, nom de l'organisation, nom du contact.
4. Création d'une **notification** `EMAIL` (`PENDING`, `source_action_id`, `dedup_key`) : c'est le point de sortie vers le fournisseur (passe Intégrations), envoyé **hors de la transaction** par le worker de notifications, avec clé d'idempotence `{notification_id}:{attempt_no}`.
5. Résultat asynchrone : livraison acceptée → `DONE` (`executed_at`, issue `SENT`) ; erreur → §9.

Un gabarit introuvable est une **erreur de configuration** (`TEMPLATE_UNAVAILABLE`) : l'action passe en `FAILED` avec alerte, sans tentative répétée.

### 8.2 Tâches humaines

Pas de worker d'exécution : à l'échéance, la tâche apparaît dans la file de travail et une notification `IN_APP` est envoyée à l'assigné (ou aux membres du pool). L'exécutant la **termine** (`SCHEDULED → DONE`, par un utilisateur, issue obligatoire, C6). Issues d'une tâche : `CONTACTED`, `NO_ANSWER`, `PROMISE_OBTAINED`, `DISPUTE_RAISED`, `REFUSED`, `WRONG_CONTACT`, `OTHER`. Les issues `PROMISE_OBTAINED` et `DISPUTE_RAISED` **suggèrent** à l'interface de créer la promesse ou le litige ; elles ne les créent pas automatiquement (les use cases correspondants exigent leurs propres données).

Une tâche non terminée à `scheduled_for + task_sla_days` déclenche une alerte interne (au responsable) ; **son statut ne change pas**.

### 8.3 Reprise après incident

Une action `EXECUTING` depuis plus de 15 minutes sans résultat est considérée comme une **tentative échouée transitoire** (worker interrompu), y compris avant la création de la notification : la nouvelle tentative la recrée (idempotente). Garantie d'envoi : **au moins une fois** ; le doublon possible dans la fenêtre « fournisseur a accepté / base non validée » est limité par la clé d'idempotence envers le fournisseur (à confirmer avec la passe Intégrations).

---

## 9. Réessai et échec

| Classe d'erreur | Exemples | Traitement |
|---|---|---|
| **Transitoire** | fournisseur indisponible, délai dépassé, limitation de débit | tentative enregistrée (`collection_action_attempts`), `EXECUTING → SCHEDULED` avec `next_retry_at` (5 min, 30 min, 2 h), **revalidation à chaque tentative** ; les réessais respectent la fenêtre de communication |
| **Permanente** | adresse invalide, rejet définitif du fournisseur | `FAILED` immédiatement, sans réessai |
| **Configuration** | gabarit introuvable, canal désactivé | `FAILED`, alerte, aucune répétition |
| **Exception métier** | facture payée entre-temps, hold posé | **pas un échec** : `SUPPRESSED` |

Tentatives épuisées (`max_attempts`, 3 par défaut) → `FAILED`. Un `FAILED` :
- ne compte pas comme niveau atteint (R9) mais conserve sa `dedup_key` ;
- envoie une alerte interne au pool `MANAGER` ;
- déclenche le **repli humain** (§10) si l'action était un `REMINDER`.

---

## 10. Repli et rebond

**Repli de canal (C2).** Comme un seul canal externe existe en V1, le repli est humain : lorsqu'un `REMINDER` est `SUPPRESSED` pour `NO_CONTACT` ou `NO_CONSENT`, ou passe en `FAILED`, le Collection Engine crée **une** action `FOLLOW_UP` de même niveau (`origin='AUTOMATION'`, pool `COLLECTOR`), qui n'est soumise à aucune exception de livraison. Le repli ne se répète pas : une action de repli n'a pas de repli.

**Rebond** (retour tardif du fournisseur indiquant un e-mail non remis) : l'action reste `DONE` (le message avait bien été accepté), son issue devient `BOUNCED`, une alerte interne est envoyée au pool `COLLECTOR` et une action `FOLLOW_UP` de suivi est créée (C13).

Quand la passe Intégrations activera `SMS` ou `WHATSAPP`, la chaîne de canaux d'une étape (`channels: [EMAIL, SMS]`) s'insérera **avant** le repli humain, sans changement de modèle.

---

## 11. Cycles, non-régression, réévaluation

- **Cycle** : `invoices.collection_cycle`, incrémenté à l'entrée en `OVERDUE` ou à l'annulation d'un règlement sur une facture déjà `OVERDUE`. Les actions de niveaux 1–2 appartiennent au cycle 0.
- **Non-régression** : dans un `(facture, cycle)`, pas de niveau inférieur au plus haut niveau `SCHEDULED`, `EXECUTING` ou `DONE` (R9).
- **Un seul exemplaire** par `(facture, type, niveau, cycle, répétition)`. Une escalade dépendant du risque peut donc **ne pas se produire** : à risque `MEDIUM`, l'étape S6 calcule le niveau 4, déjà atteint par S5, et ne crée rien (REPLAY).
- **Après suppression** (litige, promesse, hold) : l'action `SUPPRESSED` libère sa clé. Lorsque la cause est levée, l'Automation Engine réévalue (reprise de l'exécution `PAUSED`) et une nouvelle action équivalente peut être créée.
- Une promesse `BROKEN` ne relance pas automatiquement une action : elle lève la suspension ; la reprise vient de l'Automation Engine.

### Scénario de référence (test d'or de bout en bout)

Organisation `Africa/Abidjan`, fenêtre 08:00–18:00, jours ouvrés lundi–vendredi, `due_soon_days = 7`, `critical_amount_minor = 1 000 000`. Facture de 500 000, émise le lundi 2026-09-28, échéance le jeudi 2026-10-15. Client à risque `MEDIUM`, aucun litige, aucune promesse, e-mail principal avec consentement, téléphone présent.

| Date | Événement | Étape | Niveau calculé | Résultat |
|---|---|---|---|---|
| jeu 2026-10-01 | échéance − 14 j (`days_to_due = 14`) | S1 | 1 | `REMINDER` `EMAIL`, planifié à 09:00 |
| jeu 2026-10-08 | `INVOICE_DUE_SOON` (`days_to_due = 7`) | S2 | 2 | `REMINDER` `EMAIL`, 09:00 |
| ven 2026-10-16 | `INVOICE_OVERDUE` ; `collection_cycle = 1` | — | 3 (plancher) | aucune étape ; rien ne part avant J+3 |
| dim 2026-10-18 | échéance + 3 j | S3 | 3 | prochain jour ouvré : **lun 2026-10-19 09:00**, `REMINDER` |
| dim 2026-10-25 | échéance + 10 j (`days_overdue = 10`) | S4 | 3 | `CALL_TASK` (pool `COLLECTOR`), échéance **lun 2026-10-26** |
| ven 2026-10-30 | échéance + 15 j (`days_overdue = 15`) | S5 | 4 | `ESCALATION` (pool `MANAGER`) + alerte `IN_APP` |
| sam 2026-11-14 | échéance + 30 j | S6 | 4 (risque `MEDIUM` < `HIGH`) | même clé que S5 : **REPLAY**, aucune action |

Variantes dérivées du même scénario : risque `HIGH` → S6 donne le niveau 5 (si l'exposition en retard atteint 1 000 000) ; règlement complet le 2026-10-22 → tout ce qui suit est `SUPPRESSED` (`PAID`) ou annulé ; promesse créée le 2026-10-20 → S4 et S5 `SUPPRESSED` (`PROMISE_ACTIVE`).

---

## 12. Réactions aux événements

Chaque réaction est **idempotente** (`event_receipts`) et revalide l'état avant d'agir (Rule Engine, contexte D). « Actions concernées » : `PROPOSED`, `SCHEDULED`, `PENDING_APPROVAL` de la cible.

| Événement | Réaction |
|---|---|
| `INVOICE_PAID` | actions concernées → `SUPPRESSED` (`PAID`) |
| `INVOICE_VOIDED`, `INVOICE_CANCELLED` | → `SUPPRESSED` (`VOIDED`) |
| `INVOICE_SETTLEMENT_REVERTED` | aucune suppression ; nouveau cycle éventuel ; la reprise vient de l'Automation Engine |
| `INVOICE_DISPUTED` | si `collectible_minor = 0` : → `SUPPRESSED` (`DISPUTED`) |
| `PROMISE_CREATED` | → `SUPPRESSED` (`PROMISE_ACTIVE`) |
| `COLLECTION_HOLD_PLACED` | → `SUPPRESSED` (`HOLD_ACTIVE`) pour la portée du hold |
| `CUSTOMER_DEACTIVATED`, `CUSTOMER_ARCHIVED` | → `SUPPRESSED` (`CUSTOMER_INACTIVE`, `CUSTOMER_ARCHIVED`) |
| `ORGANIZATION_SUSPENDED`, `ORGANIZATION_CLOSED` | → `SUPPRESSED` (`ORG_INACTIVE`) |
| `APPROVAL_GRANTED`, `_REJECTED` | §6 |
| `NOTIFICATION_SENT`, `NOTIFICATION_FAILED` | résultat de l'envoi : §8.1 et §9 |
| `IMPORT_BATCH_RELEASED` | aucune (les actions naissent de la libération par l'Automation Engine) |
| `PAYMENT_CREATED`, `PAYMENT_ALLOCATED`, `PAYMENT_REVERSED`, `PAYMENT_ALLOCATION_REVERSED` (V1.2) | **aucune suppression en cascade** : évaluation paresseuse ; les points de revalidation (création, exécution, réveil) relisent la source de vérité et appliquent l'exception `RECONCILIATION_PENDING` (`COLLECTION_ENGINE_V1_2.md`) |

**Événements produits** : `COLLECTION_ACTION_PROPOSED`, `_SCHEDULED`, `_EXECUTED`, `_FAILED`, `_CANCELLED`, `_SUPPRESSED`, `COLLECTION_HOLD_PLACED`, `_RELEASED` (catalogue Invariants §10).

---

## 13. Issues (`collection_actions.outcome`) — liste fermée proposée (C7)

| Famille | Codes |
|---|---|
| Envoi | `SENT`, `BOUNCED` |
| Tâche humaine | `CONTACTED`, `NO_ANSWER`, `PROMISE_OBTAINED`, `DISPUTE_RAISED`, `REFUSED`, `WRONG_CONTACT`, `OTHER` |
| Annulation | `USER_CANCELLED`, `APPROVAL_REJECTED`, `APPROVAL_EXPIRED` |

---

## 14. Exécutable

| Composant | Rôle |
|---|---|
| `CreateCollectionAction`, `CreateManualAction` | création (§4) |
| `ApproveAction` / `RejectAction` | délégué au module d'approbation, résultat traité ici |
| `RescheduleAction`, `CancelAction`, `ClaimTask`, `CompleteTask` | opérations utilisateur |
| `ExecuteDueActions` (worker) | envoi système, tentatives, reprise après incident |
| `SlotCalculator` | fonction pure de planification |
| `ChannelRegistry` | canaux activés, nature (envoi système / tâche humaine / interne) |
| `TemplateResolver` | gabarit, langue, variables autorisées |
| `EventReactions` | §12 |
| `EscalationNotifier` | alertes internes par pool |

Couche **Application** ; le Domain reste sans dépendance à un fournisseur : l'envoi passe par une **interface de notification** (adaptateur `EMAIL`, passe Intégrations).
Index utilisés (contrat V1.3) : `(organization_id, status, scheduled_for)` pour le worker ; `(organization_id, assigned_to, status)` pour les files ; `(organization_id, invoice_id, status)` pour les faits du Rule Engine.
Le worker traite par lots et jamais une action à la fois hors verrou ; les traitements longs sortent de la requête HTTP.

---

## 15. Testable

| Famille | Contenu |
|---|---|
| **Scénario de référence** | la chronologie du §11 rejouée avec une horloge injectée, comparée action par action (date, niveau, type, statut) |
| **Variantes** | risque `HIGH` (niveau 5) ; paiement à J+7 ; promesse à J+5 ; litige partiel (montant recouvrable dans le message) ; client `INACTIVE` en cours de route |
| **Planification** | week-end et jour férié ; hors fenêtre ; plafond quotidien par client ; lissage du débit ; fuseaux avec heure d'été |
| **Déduplication** | même événement rejoué ; deux automatisations visant la même action ; action manuelle en double ; `SUPPRESSED` puis nouvelle action ; rejet d'approbation puis nouvelle occurrence |
| **Réessai** | erreur transitoire puis succès ; épuisement des tentatives ; erreur permanente ; revalidation entre deux tentatives (facture payée entre-temps) ; worker interrompu |
| **Repli** | `NO_CONTACT`, `NO_CONSENT`, `FAILED` → une seule tâche de repli, sans repli du repli ; rebond |
| **Approbation** | accordée, rejetée, expirée, cible résolue pendant l'attente |
| **Tâches** | réclamation simultanée par deux membres du pool ; achèvement sans issue (refusé) ; alerte de retard sans changement de statut |
| **Stratégie** | `SMS` référencé (rejeté) ; couple niveau/type incompatible (rejeté) ; plage de niveaux d'étape non respectée |
| **Sécurité** | isolation tenant sur pools et files ; aucune donnée personnelle dans `decision_snapshot` |
| **Différentiel** | le fait `highest_level_reached` et le calcul de créneau comparés à une implémentation naïve |

---

## 16. Observable

| Signal | Contenu |
|---|---|
| **Compteurs** | actions par statut, type et niveau ; suppressions par code ; replis par cause ; issues de tâches ; rebonds |
| **Délais** | écart `scheduled_for → executed_at` (retard du worker) ; durée d'approbation ; durée de traitement d'une tâche |
| **Files** | actions `SCHEDULED` en retard ; tâches non terminées après leur délai cible ; approbations proches de l'expiration |
| **Qualité** | taux d'échec par code d'erreur ; taux de rebond ; part des actions créées `SUPPRESSED` (un pic de `NO_CONSENT` signale un problème de données) |
| **Alertes** | retard du worker au-delà d'un seuil ; hausse des `FAILED` ; tâches en retard ; approbations expirées ; envoi hors fenêtre détecté (doit rester à zéro) |
| **Journaux** | un enregistrement par changement de statut : `organization_id`, `correlation_id`, `action_id`, `dedup_key`, durée ; jamais de donnée personnelle |

---

## 17. Limites connues de la V1

1. **Pas de consolidation multi-factures.** V1 ne consolide pas plusieurs factures dans un même message : chaque relance concerne **une facture**. Les répétitions restent possibles **uniquement lorsqu'elles sont explicitement définies par l'Automation Engine** (répétition d'une étape, avec bornes). Le plafond quotidien par client (§7) étale les envois d'un client qui a plusieurs factures en retard, sans les regrouper. La consolidation (relevé de compte par client) est reportée : elle demande un lien entre une notification et plusieurs actions, absent du modèle actuel.
2. **Aucun repli vers un second canal externe** (un seul canal externe).
3. **Pas de répétition implicite** : une relance ne se répète que si la définition le prévoit.
4. **Garantie d'envoi « au moins une fois »** (§8.3).

---

## 18. Ce que reçoivent les passes suivantes

- **Automation Engine** : les étapes et leurs instants (§3.2), la production de l'`occurrence` (§4), la répétition explicite, la reprise après pause, la libération d'un lot d'import, les déclencheurs non rétroactifs.
- **Risk / Priority** : la priorité de facture sert de tri des files ; `RISK_CHANGED` relance l'évaluation.
- **Intégrations** : l'interface de notification et l'adaptateur `EMAIL` ; la clé d'idempotence ; les retours de livraison et de rebond.

---

## 19. Décisions (V1.1)

**C1 à C13 : VALIDÉES.** Précisions intégrées à la demande de la revue :

| # | Précision |
|---|---|
| **C4** | `occurrence` est **déterministe** et produit par l'Automation Engine à partir du `trigger_key` de l'exécution (et, pour une répétition d'étape, de son indice). Le Collection Engine ne choisit **jamais** un numéro de répétition et n'en accepte aucun d'un appelant. |
| **C6** | Transitions ajoutées explicitement aux State Machines et aux Invariants : `SCHEDULED → DONE` (tâche humaine, par un utilisateur, issue obligatoire) ; `PENDING_APPROVAL → SUPPRESSED` ; approbation `EXPIRED` avec `TARGET_RESOLVED`. `SUPPRESSED` = le système a empêché l'action parce que le contexte métier l'exigeait ; `CANCELLED` = un acteur ou une décision explicite annule. |
| **C9** | Reformulée (§17) : V1 ne consolide pas plusieurs factures dans un même message ; chaque relance concerne une facture ; les répétitions restent possibles seulement si l'Automation Engine les définit. |
| **C10** | Distinction explicite entre invariants structurels, paramètres de stratégie et réglages d'organisation (§3.1 bis) ; chevauchement volontaire des niveaux 1 et 2 documenté. |

**Amendements appliqués** (contrat V1.3 et documents liés) :

| Amendement | Où |
|---|---|
| `collection_actions.assigned_role` et contraintes associées (C5) | Contrat §6.1 |
| Formule de `dedup_key` avec `R{occurrence}` et clé manuelle (C4) | Contrat §6.1 |
| `CHECK` fermé sur `outcome` (C7) | Contrat §6.1 |
| `SCHEDULED → DONE`, `PENDING_APPROVAL → SUPPRESSED`, `TARGET_RESOLVED` (C6) | State Machines §8, §10, §17 ; Invariants §7 |
| Codes `DEFINITION_CHANNEL_NOT_ENABLED`, `DEFINITION_LEVEL_TYPE_INCOMPATIBLE`, `DEFINITION_STEP_LEVEL_RANGE_INVALID` ; raisons de `SKIP` `STEP_LEVEL_OUT_OF_RANGE`, `APPROVAL_PREVIOUSLY_REJECTED` (C1, C3, C8) | Rule Engine §5, §6.1 |
